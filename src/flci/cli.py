"""Typed wrappers around the stock Flipper Zero serial CLI.

ALL firmware-specific command strings and output formats live in this file. When the
firmware changes its CLI, this is the only file that should need an edit.

Verified against flipperdevices/flipperzero-firmware ``dev`` (Sept 2026). Source files:

- ``device_info``: key/value lines
  (applications/services/cli/cli_main_commands.c, targets/f7/furi_hal/furi_hal_info.c)
- ``storage remove|mkdir|md5``, ``storage write_chunk <path> <size>`` -> ``Ready`` then raw
  bytes, opened in APPEND mode (applications/services/storage/storage_cli.c)
- ``subghz tx <key hex> <freq> <te> <repeat> <dev>``: Princeton 24-bit, returns when done
- ``subghz tx_from_file <path> <repeat> <dev>``: prints ``Frequency=..., Protocol=...``
- ``subghz rx <freq> <dev>``: streams ``"%s %dbit\\r\\nKey:0x%08lX..."`` until Ctrl+C
  (applications/main/subghz/subghz_cli.c, lib/subghz/protocols/princeton.c)
- ``ir tx <protocol> <addr hex> <cmd hex>``: silent on success, ``Wrong arguments.`` on error
- ``ir rx``: streams ``"<Proto>, A:0x<addr>, C:0x<cmd>[ R]"`` until Ctrl+C
  (applications/main/infrared/infrared_cli.c)
- ``ikey emulate <type> <hex>``: streams until Ctrl+C; ``ikey read``: prints
  ``"<Dallas|Cyfral|Metakom> <HEX>"`` then returns (applications/main/ibutton/ibutton_cli.c)
- ``rfid emulate <protocol> <hex>``: streams; ``rfid read``: prints ``"<Protocol> <HEX>"``
  then ``Reading stopped`` (applications/main/lfrfid/lfrfid_cli.c)
- ``gpio mode <pin> <0|1>``, ``gpio set <pin> <0|1>``, ``gpio read <pin>`` ->
  ``"Pin PA7 <= 1"`` (applications/services/cli/cli_command_gpio.c)
- ``nfc`` opens a subshell with prompt ``[nfc]>: ``; inside it ``emulate -f <path>``
  streams, ``mfu info`` prints ``Type: ...`` and ``UID: 04 ...``; ``exit`` leaves it
  (applications/main/nfc/cli/, lib/toolbox/cli/shell/cli_shell.c)
- ``loader open <app> [args]``, ``input send <key> <type>``
  (applications/services/loader/loader_cli.c, applications/services/input/input_cli.c)
- ``update install <manifest>`` -> ``OK.`` then reboot
  (applications/system/updater/cli/updater_cli.c)
"""

from __future__ import annotations

import hashlib
import re
import time
from pathlib import PurePosixPath

from flci.errors import FlciCommandError
from flci.schema import NormalizedDecode, normalize_hex
from flci.transport import SerialTransport

SUBGHZ_DEVICE_INTERNAL = 0  # 0 - CC1101_INT, 1 - CC1101_EXT
SUBGHZ_RX_READY = "Press CTRL+C to stop"
ABORT_READY = "Press Ctrl+C to abort"  # ir rx, ikey, rfid, nfc emulate
NFC_EMULATE_READY = "Emulating. Press Ctrl+C to abort"
REMOTE_ROOT = "/ext/flci"

_INFO_LINE = re.compile(r"^\s*([A-Za-z0-9_.]+)\s*:\s?(.*?)\s*$")
# "Princeton 24bit\nKey:0x00ABCDEF" - protocol names may contain spaces ("Nice FLO").
# The leading class excludes '.', which the receiver prints as a reset marker.
_SUBGHZ_DECODE = re.compile(
    r"(?P<protocol>[A-Za-z][A-Za-z0-9 _\-]*?)\s(?P<bits>\d+)bit\s*\n"
    r"\s*Key:\s?0x(?P<key>[0-9A-Fa-f]+)"
)
_IR_DECODE = re.compile(
    r"(?P<protocol>[A-Za-z0-9_]+), A:0x(?P<addr>[0-9A-Fa-f]+), C:0x(?P<cmd>[0-9A-Fa-f]+)"
    r"(?P<repeat> R)?"
)
_KEY_LINE = re.compile(r"^(?P<protocol>[A-Za-z][A-Za-z0-9_/\-]*) (?P<data>[0-9A-F]{2,})$")
_GPIO_READ = re.compile(r"Pin (?P<pin>P[A-C]\d+) <= (?P<level>[01])")
_NFC_TYPE = re.compile(r"^Type:\s*(?P<type>.+?)\s*$", re.M)
_NFC_UID = re.compile(r"^UID:\s*(?P<uid>(?:[0-9A-Fa-f]{2}\s*)+)$", re.M)
_TX_REFUSED = (
    "Frequency must be in",
    "restricted in your region",
    "can only be used for RX",
    "Usage:",
)
_SUBGHZ_FILE_ERR = "subghz tx_from_file"
# Pins on the external header that are not SWD/debug (debug pins prompt y/n).
SAFE_GPIO_PINS = {"PA7", "PA6", "PA4", "PB3", "PB2", "PC3", "PC1", "PC0"}


# -- parsers (pure functions, unit-tested offline) ---------------------------------------


def parse_device_info(text: str) -> dict[str, str]:
    info: dict[str, str] = {}
    for line in text.splitlines():
        m = _INFO_LINE.match(line)
        if m:
            info[m.group(1)] = m.group(2)
    return info


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def parse_subghz_decodes(text: str, frequency_hz: int | None = None) -> list[NormalizedDecode]:
    """Extract every decoded packet from ``subghz rx`` output."""
    out: list[NormalizedDecode] = []
    for m in _SUBGHZ_DECODE.finditer(_norm(text)):
        bits = int(m.group("bits"))
        out.append(
            NormalizedDecode(
                subsystem="subghz",
                protocol=m.group("protocol").strip(),
                frequency_hz=frequency_hz,
                payload=normalize_hex(m.group("key"), bits),
                bits=bits,
                raw={"match": m.group(0)},
            )
        )
    return out


def ir_payload(address: int | str, command: int | str) -> str:
    """Infrared payload is ``<address>-<command>``, each as unpadded uppercase hex."""
    return f"{normalize_hex(address)}-{normalize_hex(command)}"


def parse_ir_decodes(text: str) -> list[NormalizedDecode]:
    out = []
    for m in _IR_DECODE.finditer(_norm(text)):
        out.append(
            NormalizedDecode(
                subsystem="infrared",
                protocol=m.group("protocol"),
                payload=ir_payload(m.group("addr"), m.group("cmd")),
                raw={"match": m.group(0), "repeat": bool(m.group("repeat"))},
            )
        )
    return out


def parse_key_lines(text: str, subsystem: str) -> list[NormalizedDecode]:
    """``ikey read`` / ``rfid read`` print one ``<Protocol> <HEX>`` line per key."""
    out = []
    for line in _norm(text).split("\n"):
        m = _KEY_LINE.match(line.strip())
        if m:
            data = m.group("data")
            out.append(
                NormalizedDecode(
                    subsystem=subsystem,
                    protocol=m.group("protocol"),
                    payload=data,
                    bits=len(data) * 4,
                    raw={"line": line.strip()},
                )
            )
    return out


def parse_gpio_read(text: str) -> NormalizedDecode | None:
    m = _GPIO_READ.search(text)
    if not m:
        return None
    return NormalizedDecode(
        subsystem="gpio",
        protocol="level",
        payload=m.group("level"),
        bits=1,
        raw={"pin": m.group("pin"), "line": m.group(0)},
    )


def parse_nfc_mfu_info(text: str) -> list[NormalizedDecode]:
    t, u = _NFC_TYPE.search(_norm(text)), _NFC_UID.search(_norm(text))
    if not u:
        return []
    uid = u.group("uid").replace(" ", "").strip().upper()
    return [
        NormalizedDecode(
            subsystem="nfc",
            protocol=t.group("type") if t else "unknown",
            payload=uid,
            bits=len(uid) * 4,
            raw={"type_line": t.group(0) if t else None, "uid_line": u.group(0)},
        )
    ]


# -- the CLI ------------------------------------------------------------------------------


class FlipperCLI:
    """One verb per method. Knows the firmware's words; the transport knows the wire."""

    def __init__(self, transport: SerialTransport):
        self.t = transport
        self.in_nfc_shell = False

    @property
    def name(self) -> str:
        return self.t.name

    def settle(self, seconds: float) -> None:
        """Deliberate, named wait so every sleep in the harness is greppable."""
        time.sleep(seconds)

    def _check(self, cmd: str, out: str, bad: tuple[str, ...], expected: str) -> str:
        if any(b in out for b in bad):
            raise FlciCommandError(self.name, cmd, expected, out)
        return out

    # -- identity ----------------------------------------------------------------

    def device_info(self) -> dict[str, str]:
        out = self.t.run("device_info", timeout_s=5.0)
        info = parse_device_info(out)
        if "hardware_name" not in info and "firmware_version" not in info:
            raise FlciCommandError(self.name, "device_info", "key: value lines", out)
        return info

    # -- storage -----------------------------------------------------------------

    def storage_upload(self, data: bytes, remote_path: str) -> None:
        """Write ``data`` to ``remote_path`` (replacing it) and verify by MD5."""
        parent = str(PurePosixPath(remote_path).parent)
        parts = PurePosixPath(parent).parts  # ('/', 'ext', 'flci', ...)
        for i in range(3, len(parts) + 1):
            self.t.run(f"storage mkdir {PurePosixPath(*parts[:i])}")  # "exists" is fine
        self.t.run(f"storage remove {remote_path}")  # write_chunk appends; start empty
        cmd = f"storage write_chunk {remote_path} {len(data)}"
        out = self.t.run_with_payload(cmd, "Ready", data, timeout_s=15.0)
        if "Storage error" in out or "Usage" in out:
            raise FlciCommandError(self.name, cmd, "clean write", out)
        want = hashlib.md5(data).hexdigest()
        got = self.t.run(f"storage md5 {remote_path}").strip().lower()
        if want not in got:
            raise FlciCommandError(self.name, f"storage md5 {remote_path}", want, got)

    # -- Sub-GHz -----------------------------------------------------------------

    def subghz_tx(
        self,
        key: int,
        frequency_hz: int,
        te_us: int = 400,
        repeat: int = 10,
        device: int = SUBGHZ_DEVICE_INTERNAL,
        timeout_s: float = 20.0,
    ) -> str:
        """Transmit a Princeton 24-bit key. Blocks until the firmware finishes sending."""
        if not 0 <= key <= 0xFFFFFF:
            raise ValueError(f"subghz tx key must fit 24 bits, got {key:#x}")
        cmd = f"subghz tx {key:06X} {frequency_hz} {te_us} {repeat} {device}"
        out = self.t.run(cmd, timeout_s=timeout_s)
        if "Transmitting at" not in out:
            raise FlciCommandError(self.name, cmd, "'Transmitting at ...'", out)
        return self._check(cmd, out, _TX_REFUSED, "a clean transmit")

    def subghz_tx_file(
        self,
        remote_path: str,
        repeat: int = 1,
        device: int = SUBGHZ_DEVICE_INTERNAL,
        timeout_s: float = 30.0,
    ) -> str:
        cmd = f"subghz tx_from_file {remote_path} {repeat} {device}"
        out = self.t.run(cmd, timeout_s=timeout_s)
        if "Frequency=" not in out:
            raise FlciCommandError(self.name, cmd, "'Frequency=..., Protocol=...'", out)
        return self._check(cmd, out, _TX_REFUSED + (_SUBGHZ_FILE_ERR,), "a clean transmit")

    def subghz_rx_start(self, frequency_hz: int, device: int = SUBGHZ_DEVICE_INTERNAL) -> None:
        cmd = f"subghz rx {frequency_hz} {device}"
        head = self.t.start_stream(cmd, SUBGHZ_RX_READY, timeout_s=5.0)
        self._check(cmd, head, ("Frequency must be in",), "receiver to start")

    def subghz_rx_stop(self, frequency_hz: int | None = None) -> tuple[list[NormalizedDecode], str]:
        out = self.t.stop_stream(timeout_s=5.0)
        return parse_subghz_decodes(out, frequency_hz), out

    # -- Infrared ----------------------------------------------------------------

    def ir_tx(self, protocol: str, address: int, command: int) -> str:
        cmd = f"ir tx {protocol} {address:X} {command:X}"
        out = self.t.run(cmd, timeout_s=10.0)
        return self._check(cmd, out, ("Wrong arguments", "busy"), "a silent transmit")

    def ir_rx_start(self) -> None:
        self.t.start_stream("ir rx", ABORT_READY, timeout_s=5.0)

    def ir_rx_stop(self) -> tuple[list[NormalizedDecode], str]:
        out = self.t.stop_stream()
        return parse_ir_decodes(out), out

    # -- iButton -----------------------------------------------------------------

    def ibutton_emulate_start(self, key_type: str, key_hex: str) -> None:
        cmd = f"ikey emulate {key_type} {key_hex}"
        head = self.t.start_stream(cmd, ABORT_READY, timeout_s=5.0)
        self._check(cmd, head, ("Usage:",), "emulation to start")

    def ibutton_read(self, timeout_s: float = 10.0) -> tuple[list[NormalizedDecode], str]:
        out, _ = self.t.run_bounded("ikey read", timeout_s)
        return parse_key_lines(out, "ibutton"), out

    # -- RFID 125 kHz ------------------------------------------------------------

    def rfid_emulate_start(self, protocol: str, data_hex: str) -> None:
        cmd = f"rfid emulate {protocol} {data_hex}"
        head = self.t.start_stream(cmd, ABORT_READY, timeout_s=5.0)
        self._check(cmd, head, ("Usage:", "not supported", "Wrong"), "emulation to start")

    def rfid_read(
        self, mode: str = "normal", timeout_s: float = 10.0
    ) -> tuple[list[NormalizedDecode], str]:
        out, _ = self.t.run_bounded(f"rfid read {mode}", timeout_s)
        return parse_key_lines(out, "rfid"), out

    # -- GPIO --------------------------------------------------------------------

    def _safe_pin(self, pin: str) -> str:
        if pin not in SAFE_GPIO_PINS:
            raise ValueError(f"pin {pin} is not in the safe set {sorted(SAFE_GPIO_PINS)}")
        return pin

    def gpio_mode(self, pin: str, output: bool) -> str:
        cmd = f"gpio mode {self._safe_pin(pin)} {1 if output else 0}"
        out = self.t.run(cmd)
        want = "is now an output" if output else "is now an input"
        if want not in out:
            raise FlciCommandError(self.name, cmd, repr(want), out)
        return out

    def gpio_set(self, pin: str, level: int) -> str:
        cmd = f"gpio set {self._safe_pin(pin)} {1 if level else 0}"
        out = self.t.run(cmd)
        if "=>" not in out:
            raise FlciCommandError(self.name, cmd, "'Pin .. => ..'", out)
        return out

    def gpio_read(self, pin: str) -> tuple[list[NormalizedDecode], str]:
        out = self.t.run(f"gpio read {self._safe_pin(pin)}")
        d = parse_gpio_read(out)
        return ([d] if d else []), out

    # -- NFC (subshell) ----------------------------------------------------------

    def nfc_enter(self) -> None:
        if not self.in_nfc_shell:
            self.t.run("nfc", timeout_s=5.0)
            self.in_nfc_shell = True

    def nfc_exit(self) -> None:
        if self.in_nfc_shell:
            self.t.reset()
            self.t.run("exit", timeout_s=5.0)
            self.in_nfc_shell = False

    def nfc_emulate_start(self, remote_path: str) -> None:
        self.nfc_enter()
        cmd = f"emulate -f {remote_path}"
        head = self.t.start_stream(cmd, NFC_EMULATE_READY, timeout_s=10.0)
        self._check(cmd, head, ("Wrong path", "Failed to load", "not supported"), "emulation")

    def nfc_emulate_stop(self) -> str:
        return self.t.stop_stream()

    def nfc_mfu_info(self, timeout_s: float = 10.0) -> tuple[list[NormalizedDecode], str]:
        self.nfc_enter()
        out, _ = self.t.run_bounded("mfu info", timeout_s)
        return parse_nfc_mfu_info(out), out

    # -- apps / input / update ---------------------------------------------------

    def loader_open(self, app: str, arg: str | None = None) -> None:
        """Opens an app. NOTE: some apps (Bad USB) take over USB and drop this CLI."""
        cmd = f'loader open "{app}"' + (f" {arg}" if arg else "")
        self.t._send_line(cmd)

    def input_send(self, key: str, kind: str = "short") -> str:
        return self.t.run(f"input send {key} {kind}")

    def update_install(self, manifest_path: str) -> str:
        """Start a firmware update. On success the device reboots and the port goes away."""
        cmd = f"update install {manifest_path}"
        self.t._send_line(cmd)
        ok, out = self.t._try_read_until("BRB", 60.0)
        if not ok:
            raise FlciCommandError(self.name, cmd, "'OK. Restarting to apply update. BRB'", out)
        return out
