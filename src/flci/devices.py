"""Device discovery and role assignment (EMITTER vs DUT).

Roles are never guessed: the DUT runs the candidate firmware, so swapping the two would
silently test the wrong build. Set them explicitly with environment variables:

    FLCI_DUT=/dev/cu.usbmodemflip_Dut1     # serial port path, or the device's name
    FLCI_EMITTER=/dev/cu.usbmodemflip_Emt2
"""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass, field

from serial.tools import list_ports

from flci.cli import FlipperCLI
from flci.errors import FlciError
from flci.transport import SerialTransport

# STMicroelectronics VCP IDs used by the Flipper Zero USB CDC interface.
FLIPPER_VID = 0x0483
FLIPPER_PID = 0x5740

ENV_DUT = "FLCI_DUT"
ENV_EMITTER = "FLCI_EMITTER"


class DeviceRole(enum.Enum):
    EMITTER = "emitter"
    DUT = "dut"


@dataclass
class PortInfo:
    port: str
    serial_number: str | None
    description: str


def find_flipper_ports() -> list[PortInfo]:
    found = []
    for p in list_ports.comports():
        if p.vid == FLIPPER_VID and p.pid == FLIPPER_PID:
            found.append(PortInfo(p.device, p.serial_number, p.description or ""))
    return sorted(found, key=lambda p: p.port)


@dataclass
class Device:
    role: DeviceRole
    port: str
    transport: SerialTransport = field(init=False)
    cli: FlipperCLI = field(init=False)
    info: dict[str, str] = field(default_factory=dict)
    commands: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.transport = SerialTransport(self.port, name=f"{self.role.value}@{self.port}")
        self.cli = FlipperCLI(self.transport)

    def open(self) -> None:
        self.transport.open()
        self.info = self.cli.device_info()
        name = self.info.get("hardware_name", "?")
        self.transport.name = f"{self.role.value}:{name}@{self.port}"
        self.commands = self.cli.commands()

    def battery_percent(self) -> int | None:
        try:
            return int(self.cli.power_info().get("charge.level", ""))
        except (ValueError, FlciError):
            return None

    def close(self) -> None:
        self.transport.close()

    @property
    def firmware(self) -> str:
        return self.info.get("firmware_version", "unknown")


class RoleConfigError(Exception):
    """Hardware present but roles aren't unambiguous. Tests should skip with this message."""


def _resolve(selector: str, ports: list[PortInfo]) -> str:
    """Accept a port path directly, or match a Flipper's name inside its port/serial."""
    if os.path.exists(selector) or selector.upper().startswith("COM"):
        return selector
    hits = [
        p.port
        for p in ports
        if selector.lower() in p.port.lower() or selector.lower() in (p.serial_number or "").lower()
    ]
    if len(hits) != 1:
        raise RoleConfigError(f"selector {selector!r} matched {len(hits)} ports: {hits}")
    return hits[0]


def resolve_roles(ports: list[PortInfo] | None = None) -> tuple[str, str]:
    """Return (emitter_port, dut_port) or raise RoleConfigError explaining what to set."""
    ports = find_flipper_ports() if ports is None else ports
    dut_sel, emt_sel = os.environ.get(ENV_DUT), os.environ.get(ENV_EMITTER)
    if not dut_sel or not emt_sel:
        seen = ", ".join(p.port for p in ports) or "none"
        raise RoleConfigError(
            f"Set {ENV_DUT} and {ENV_EMITTER} (port path or device name). Flippers seen: {seen}"
        )
    dut, emt = _resolve(dut_sel, ports), _resolve(emt_sel, ports)
    if dut == emt:
        raise RoleConfigError(f"{ENV_DUT} and {ENV_EMITTER} both resolve to {dut}")
    return emt, dut
