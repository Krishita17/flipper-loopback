"""Typed wrappers around the stock Flipper Zero serial CLI.

ALL firmware-specific command strings and output formats live in this file. When the
firmware changes its CLI, this is the only file that should need an edit.

Verified against flipperdevices/flipperzero-firmware `dev` (Sept 2026):

- device identity: ``device_info`` prints ``key<pad>: value`` lines
  (applications/services/cli/cli_main_commands.c, targets/f7/furi_hal/furi_hal_info.c)
- subghz transmit: ``subghz tx <key hex> <freq Hz> <te us> <repeat> <device>``
  (applications/main/subghz/subghz_cli.c)
- subghz receive: ``subghz rx <freq Hz> <device>``, streams decodes until Ctrl+C
  (applications/main/subghz/subghz_cli.c)
- decode text: ``"%s %dbit\\r\\nKey:0x%08lX..."`` (lib/subghz/protocols/princeton.c)

``subghz tx`` always sends Princeton 24-bit (hard-coded in the firmware), which is exactly
the Phase 1 stimulus. File-based TX (``subghz tx_from_file``) is Phase 2.
"""

from __future__ import annotations

import re
import time

from flci.errors import FlciCommandError
from flci.schema import NormalizedDecode, normalize_hex
from flci.transport import SerialTransport

SUBGHZ_DEVICE_INTERNAL = 0  # 0 - CC1101_INT, 1 - CC1101_EXT
SUBGHZ_RX_READY = "Press CTRL+C to stop"

_INFO_LINE = re.compile(r"^\s*([A-Za-z0-9_.]+)\s*:\s?(.*?)\s*$")
# "Princeton 24bit\nKey:0x00ABCDEF" - protocol names may contain spaces ("Nice FLO").
# The leading class excludes '.', which the receiver prints as a reset marker.
_SUBGHZ_DECODE = re.compile(
    r"(?P<protocol>[A-Za-z][A-Za-z0-9 _\-]*?)\s(?P<bits>\d+)bit\s*\n"
    r"\s*Key:\s?0x(?P<key>[0-9A-Fa-f]+)"
)
_TX_REFUSED = (
    "Frequency must be in",
    "restricted in your region",
    "can only be used for RX",
    "Usage:",
)


def parse_device_info(text: str) -> dict[str, str]:
    info: dict[str, str] = {}
    for line in text.splitlines():
        m = _INFO_LINE.match(line)
        if m:
            info[m.group(1)] = m.group(2)
    return info


def parse_subghz_decodes(text: str, frequency_hz: int | None = None) -> list[NormalizedDecode]:
    """Extract every decoded packet from ``subghz rx`` output."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    out: list[NormalizedDecode] = []
    for m in _SUBGHZ_DECODE.finditer(text):
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


class FlipperCLI:
    """One verb per method. Knows the firmware's words; the transport knows the wire."""

    def __init__(self, transport: SerialTransport):
        self.t = transport

    @property
    def name(self) -> str:
        return self.t.name

    # -- identity ----------------------------------------------------------------

    def device_info(self) -> dict[str, str]:
        out = self.t.run("device_info", timeout_s=5.0)
        info = parse_device_info(out)
        if "hardware_name" not in info and "firmware_version" not in info:
            raise FlciCommandError(self.name, "device_info", "key: value lines", out)
        return info

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
        if any(s in out for s in _TX_REFUSED) or "Transmitting at" not in out:
            raise FlciCommandError(self.name, cmd, "'Transmitting at ...' and a clean exit", out)
        return out

    def subghz_rx_start(self, frequency_hz: int, device: int = SUBGHZ_DEVICE_INTERNAL) -> None:
        cmd = f"subghz rx {frequency_hz} {device}"
        head = self.t.start_stream(cmd, SUBGHZ_RX_READY, timeout_s=5.0)
        if "Frequency must be in" in head:
            raise FlciCommandError(self.name, cmd, "receiver to start", head)

    def subghz_rx_stop(self, frequency_hz: int | None = None) -> tuple[list[NormalizedDecode], str]:
        out = self.t.stop_stream(timeout_s=5.0)
        return parse_subghz_decodes(out, frequency_hz), out

    def settle(self, seconds: float) -> None:
        """Deliberate, named wait so every sleep in the harness is greppable."""
        time.sleep(seconds)
