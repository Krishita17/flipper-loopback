"""Check that a bench is ready, and say exactly what to fix if it isn't.

    flci doctor            environment, ports, roles, firmware, SD card, battery
    flci doctor --probe    also run one smoke fixture per capability (DUT receive path)

Exit status is 1 if any check failed (warnings don't count).
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

import serial

from flci.devices import (
    ENV_DUT,
    ENV_EMITTER,
    Device,
    DeviceRole,
    RoleConfigError,
    find_flipper_ports,
    resolve_roles,
)
from flci.errors import FlciError
from flci.fixtures import load_fixtures
from flci.rig import Rig
from flci.subsystems import REGISTRY

DEFAULT_CAPABILITIES = "subghz,infrared,rfid,nfc"
LOW_BATTERY_PCT = 30
MIN_SD_FREE_KIB = 1024


@dataclass
class Check:
    level: str  # ok | warn | fail | info
    name: str
    detail: str

    def line(self) -> str:
        icon = {"ok": "✓", "warn": "⚠", "fail": "✗", "info": "·"}[self.level]
        return f"{icon} {self.name:24} {self.detail}"


class Doctor:
    def __init__(self, emit: Callable[[str], None] = print):
        self.checks: list[Check] = []
        self.emit = emit

    def add(self, level: str, name: str, detail: str) -> None:
        c = Check(level, name, detail)
        self.checks.append(c)
        self.emit(c.line())

    @property
    def failed(self) -> bool:
        return any(c.level == "fail" for c in self.checks)

    # -- host -----------------------------------------------------------------------

    def host(self) -> None:
        v = sys.version_info
        self.add("ok", "python", f"{v.major}.{v.minor}.{v.micro}")
        self.add("ok", "pyserial", getattr(serial, "__version__", "?"))
        if shutil.which("pgrep"):
            r = subprocess.run(["pgrep", "-if", "qflipper"], capture_output=True, text=True)
            if r.stdout.strip():
                self.add("fail", "qFlipper", "running: it holds the serial port. Quit it first.")
            else:
                self.add("ok", "qFlipper", "not running")

    def capabilities(self) -> set[str]:
        caps = {
            c.strip()
            for c in os.environ.get("FLCI_CAPABILITIES", DEFAULT_CAPABILITIES).split(",")
            if c.strip()
        }
        unknown = caps - set(REGISTRY)
        if unknown:
            self.add("fail", "FLCI_CAPABILITIES", f"unknown subsystem(s) {sorted(unknown)}")
        self.add("info", "capabilities", ", ".join(sorted(caps & set(REGISTRY))))
        return caps & set(REGISTRY)

    # -- ports and roles -------------------------------------------------------------

    def ports(self) -> tuple[str, str] | None:
        ports = find_flipper_ports()
        level = "ok" if len(ports) >= 2 else "fail"
        listing = ", ".join(p.port for p in ports) or "none"
        self.add(level, "flippers on USB", f"{len(ports)} ({listing})")
        if sys.platform.startswith("linux"):
            for p in ports:
                if not os.access(p.port, os.R_OK | os.W_OK):
                    self.add(
                        "fail",
                        "port permission",
                        f"{p.port}: no read/write. `sudo usermod -aG dialout $USER`, re-login",
                    )
        if len(ports) < 2:
            return None
        try:
            emt, dut = resolve_roles(ports)
        except RoleConfigError as e:
            self.add("fail", "roles", str(e))
            return None
        self.add("ok", "roles", f"{ENV_EMITTER}={emt}  {ENV_DUT}={dut}")
        return emt, dut

    # -- devices --------------------------------------------------------------------

    def device(self, dev: Device, caps: set[str]) -> bool:
        label = dev.role.value
        try:
            dev.open()
        except (OSError, FlciError) as e:
            self.add("fail", f"{label} open", f"{dev.port}: {e}")
            return False
        info = dev.info
        self.add(
            "ok",
            f"{label} identity",
            f"{info.get('hardware_name', '?')} fw {dev.firmware} "
            f"({info.get('firmware_commit', '?')}, {info.get('firmware_branch', '?')})",
        )
        if "hardware_region" in info:
            self.add("info", f"{label} region", info["hardware_region"])
        needed = sorted({c for s in caps for c in REGISTRY[s].required_commands})
        if not dev.commands:
            self.add("warn", f"{label} CLI", "`help` output not understood; preflight disabled")
        else:
            missing = [c for c in needed if c not in dev.commands]
            if missing:
                self.add("fail", f"{label} CLI", f"missing commands {missing}")
            else:
                self.add("ok", f"{label} CLI", f"has {', '.join(needed)}")
        try:
            free = dev.cli.sd_free_kib()
        except FlciError as e:
            free, err = None, str(e)
        else:
            err = "no SD card (or unreadable)"
        if free is None:
            needs_sd = caps & {"subghz", "nfc", "badusb"}
            self.add("fail" if needs_sd else "warn", f"{label} SD card", err)
        else:
            lvl = "ok" if free >= MIN_SD_FREE_KIB else "warn"
            self.add(lvl, f"{label} SD card", f"{free // 1024} MiB free")
        pct = dev.battery_percent()
        if pct is None:
            self.add("warn", f"{label} battery", "unknown")
        else:
            lvl = "ok" if pct >= LOW_BATTERY_PCT else "warn"
            hint = "" if lvl == "ok" else " (low charge shortens RF/RFID range; charge it)"
            self.add(lvl, f"{label} battery", f"{pct}%{hint}")
        return True

    def firmware_pair(self, emitter: Device, dut: Device) -> None:
        if emitter.firmware == dut.firmware:
            self.add(
                "info",
                "firmware pair",
                f"both run {dut.firmware}; fine for a baseline, flash the DUT to test a change",
            )
        else:
            self.add("info", "firmware pair", f"emitter {emitter.firmware} / DUT {dut.firmware}")

    # -- probes ---------------------------------------------------------------------

    def probe(self, rig: Rig, caps: set[str]) -> None:
        for sub in sorted(caps - {"badusb"}):
            fixtures = [f for f in load_fixtures(sub) if not f.expect_no_decode]
            smoke = [f for f in fixtures if "smoke" in f.tags] or fixtures[:1]
            if not smoke:
                continue
            fx = smoke[0]
            try:
                r = rig.round_trip(fx, "dut_rx")
            except FlciError as e:
                self.add("fail", f"probe {sub}", f"{fx.id}: {e}")
                continue
            if r.passed:
                self.add("ok", f"probe {sub}", f"{fx.id} in {r.duration_s:.1f}s")
            else:
                got = "; ".join(d.short() for d in r.decodes) or "nothing"
                hint = " check wiring (hardware/WIRING.md)" if sub in ("gpio", "ibutton") else ""
                self.add("fail", f"probe {sub}", f"{fx.id}: got {got}.{hint}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="flci doctor", description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    p.add_argument("--probe", action="store_true", help="run one smoke fixture per capability")
    a = p.parse_args(argv)

    doc = Doctor()
    doc.host()
    caps = doc.capabilities()
    roles = doc.ports()
    if roles is not None:
        emitter, dut = Device(DeviceRole.EMITTER, roles[0]), Device(DeviceRole.DUT, roles[1])
        try:
            ok = doc.device(emitter, caps) & doc.device(dut, caps)
            if ok:
                doc.firmware_pair(emitter, dut)
                if a.probe:
                    doc.probe(Rig(emitter, dut), caps)
        finally:
            emitter.close()
            dut.close()
    n_fail = sum(c.level == "fail" for c in doc.checks)
    n_warn = sum(c.level == "warn" for c in doc.checks)
    print(f"\n{n_fail} failed, {n_warn} warnings")
    return 1 if doc.failed else 0
