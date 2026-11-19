"""flci doctor against simulated devices (offline)."""

from __future__ import annotations

import pytest

from flci.cli import FlipperCLI
from flci.devices import Device, DeviceRole
from flci.rig import Rig
from flci.tools.doctor import Doctor

from .fake_flipper import Air, FakeFlipper


def _dev(role: DeviceRole, fake: FakeFlipper) -> Device:
    d = Device(role, f"fake-{role.value}")
    d.transport._factory = fake
    return d


def test_healthy_device_passes() -> None:
    doc = Doctor(emit=lambda _: None)
    assert doc.device(_dev(DeviceRole.DUT, FakeFlipper("Dut", Air())), {"subghz", "rfid"})
    assert not doc.failed
    names = {c.name: c for c in doc.checks}
    assert names["dut SD card"].detail.endswith("MiB free")
    assert names["dut battery"].level == "ok"


def test_problems_are_named() -> None:
    doc = Doctor(emit=lambda _: None)
    fake = FakeFlipper(
        "Dut",
        Air(),
        commands={"help", "device_info", "info", "storage"},
        sd_card=False,
        battery_pct=12,
    )
    doc.device(_dev(DeviceRole.DUT, fake), {"subghz"})
    by = {c.name: c for c in doc.checks}
    assert by["dut CLI"].level == "fail" and "subghz" in by["dut CLI"].detail
    assert by["dut SD card"].level == "fail"  # subghz file TX needs the SD card
    assert by["dut battery"].level == "warn" and "12%" in by["dut battery"].detail
    assert doc.failed


def test_probe_runs_smoke_fixtures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FlipperCLI, "settle", lambda self, s: None)
    air = Air()
    emt, dut = _dev(DeviceRole.EMITTER, FakeFlipper("Emt", air)), _dev(
        DeviceRole.DUT, FakeFlipper("Dut", air)
    )
    emt.open()
    dut.open()
    doc = Doctor(emit=lambda _: None)
    doc.probe(Rig(emt, dut), {"subghz", "gpio", "rfid"})
    probes = [c for c in doc.checks if c.name.startswith("probe")]
    assert [c.level for c in probes] == ["ok", "ok", "ok"]
