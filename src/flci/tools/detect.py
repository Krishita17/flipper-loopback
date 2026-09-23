"""List connected Flippers with firmware/hardware versions and the role each would get."""

from __future__ import annotations

import os

from flci.cli import FlipperCLI
from flci.devices import ENV_DUT, ENV_EMITTER, RoleConfigError, find_flipper_ports, resolve_roles
from flci.errors import FlciError
from flci.transport import SerialTransport


def main(argv: list[str] | None = None) -> int:
    ports = find_flipper_ports()
    if not ports:
        print("No Flipper Zero found on USB (VID 0483 / PID 5740).")
        print("Close qFlipper / other serial monitors, check the cable carries data.")
        return 1
    try:
        emt, dut = resolve_roles(ports)
        roles = {emt: "EMITTER", dut: "DUT"}
    except RoleConfigError as e:
        roles = {}
        print(f"roles: not assigned ({e})")
    print(f"{'port':40} {'role':8} {'name':12} {'firmware':14} {'hw_target':9}")
    for p in ports:
        try:
            with SerialTransport(p.port) as t:
                info = FlipperCLI(t).device_info()
        except (FlciError, OSError) as e:
            print(f"{p.port:40} {roles.get(p.port, '-'):8} ERROR: {e}")
            continue
        print(
            f"{p.port:40} {roles.get(p.port, '-'):8} {info.get('hardware_name', '?'):12} "
            f"{info.get('firmware_version', '?'):14} {info.get('hardware_target', '?'):9}"
        )
    if not roles:
        print(f"\nexport {ENV_DUT}=<port or name>  {ENV_EMITTER}=<port or name>")
    elif os.environ.get("CI"):
        print(f"::notice::DUT={dut} EMITTER={emt}")
    return 0
