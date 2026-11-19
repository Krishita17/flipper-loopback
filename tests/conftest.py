"""Hardware discovery. With no bench attached, hardware tests SKIP with a reason, never pass.

A bench declares what it is physically set up for with ``FLCI_CAPABILITIES`` (comma list).
Default is the air-gap-only set; wired and operator subsystems must be opted into, because
running them on a bench without the wiring would produce false failures.

Every case runs in each direction in ``FLCI_DIRECTIONS`` (default both): ``dut_rx`` tests the
candidate firmware's receive path, ``dut_tx`` its transmit/emulate path.
Fixtures tagged with anything in ``FLCI_EXCLUDE_TAGS`` (default ``environment``) are left out.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from flci.devices import Device, DeviceRole, RoleConfigError, find_flipper_ports, resolve_roles
from flci.errors import FlciEnvironmentSkip
from flci.fixtures import load_fixtures
from flci.rig import Rig
from flci.schema import Fixture
from flci.subsystems import REGISTRY

DEFAULT_CAPABILITIES = "subghz,infrared,rfid,nfc"
OPT_IN = {
    "ibutton": "wire pin 17 <-> 17 and GND (hardware/WIRING.md)",
    "gpio": "wire PA7 <-> 1k <-> PA7 and GND (hardware/WIRING.md)",
    "badusb": "Linux host with evdev and FLCI_OPERATOR=1 (a human presses OK/Back)",
}


def capabilities() -> set[str]:
    raw = os.environ.get("FLCI_CAPABILITIES", DEFAULT_CAPABILITIES)
    return {c.strip() for c in raw.split(",") if c.strip()}


def _env_set(name: str, default: str = "") -> set[str]:
    return {t.strip() for t in os.environ.get(name, default).split(",") if t.strip()}


def directions() -> list[str]:
    return [d for d in ("dut_rx", "dut_tx") if d in _env_set("FLCI_DIRECTIONS", "dut_rx,dut_tx")]


def fixture_params(subsystem: str) -> list[object]:
    """Parametrize over (fixture, direction), honouring FLCI_TAGS / FLCI_EXCLUDE_TAGS."""
    tags = _env_set("FLCI_TAGS")
    exclude = _env_set("FLCI_EXCLUDE_TAGS", "environment") - tags
    fixtures = [f for f in load_fixtures(subsystem, tags=tags or None) if not exclude & set(f.tags)]
    sub_dirs = REGISTRY[subsystem].directions
    params = []
    for f in fixtures:
        marks = [getattr(pytest.mark, subsystem), pytest.mark.hardware]
        if "partial" in f.tags:
            marks.append(pytest.mark.partial)
        if f.expect_no_decode:
            marks.append(pytest.mark.negative)
        for d in directions():
            if d in sub_dirs:
                params.append(pytest.param(f, d, id=f"{f.id}@{d}", marks=marks))
    return params


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


def run_round_trip(rig: Rig, fixture: Fixture, direction: str, record_property: object) -> None:
    """Shared body of every loopback test."""
    if fixture.subsystem not in capabilities():
        hint = OPT_IN.get(fixture.subsystem, "add it to FLCI_CAPABILITIES")
        pytest.skip(f"bench not set up for {fixture.subsystem}: {hint}")
    try:
        result = rig.round_trip(fixture, direction)
    except FlciEnvironmentSkip as e:
        if os.environ.get("FLCI_STRICT") == "1":
            raise
        pytest.skip(f"environment: {e}")
    if callable(record_property):
        for role, pct in result.battery.items():
            if pct is not None:
                record_property(f"{role}_battery_pct", pct)
        record_property("dut_firmware", result.dut_fw)
        record_property("emitter_firmware", result.emitter_fw)
        record_property("decodes", "; ".join(d.short() for d in result.decodes))
        record_property("duration_s", f"{result.duration_s:.2f}")
        record_property("direction", direction)
    assert result.passed, result.explain()


def pytest_report_header(config: pytest.Config) -> list[str]:
    ports = find_flipper_ports()
    return [
        f"flipper-loopback: {len(ports)} Flipper(s) on USB: {[p.port for p in ports]}",
        f"flipper-loopback: bench capabilities: {sorted(capabilities())}",
    ]
