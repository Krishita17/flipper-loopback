"""Hardware discovery. With no bench attached, hardware tests SKIP with a reason, never pass."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from flci.devices import Device, DeviceRole, RoleConfigError, find_flipper_ports, resolve_roles
from flci.rig import Rig


@pytest.fixture(scope="session")
def rig() -> Iterator[Rig]:
    ports = find_flipper_ports()
    if len(ports) < 2:
        pytest.skip(
            f"hardware: need 2 Flippers on USB, found {len(ports)} "
            f"({', '.join(p.port for p in ports) or 'none'}). Not a pass - no hardware ran."
        )
    try:
        emitter_port, dut_port = resolve_roles(ports)
    except RoleConfigError as e:
        pytest.skip(f"hardware: {e}")

    emitter = Device(DeviceRole.EMITTER, emitter_port)
    dut = Device(DeviceRole.DUT, dut_port)
    emitter.open()
    try:
        dut.open()
    except Exception:
        emitter.close()
        raise
    try:
        yield Rig(emitter, dut)
    finally:
        emitter.close()
        dut.close()


def pytest_report_header(config: pytest.Config) -> str:
    ports = find_flipper_ports()
    return f"flipper-loopback: {len(ports)} Flipper(s) on USB: {[p.port for p in ports]}"
