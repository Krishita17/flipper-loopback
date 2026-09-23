"""Offline orchestration tests against FakeFlipper (see its docstring: NOT hardware)."""

from __future__ import annotations

import pytest

from flci.cli import FlipperCLI
from flci.devices import Device, DeviceRole
from flci.fixtures import load_fixtures
from flci.rig import Rig
from flci.schema import Fixture

from .fake_flipper import Air, FakeFlipper


@pytest.fixture
def fake_rig(monkeypatch: pytest.MonkeyPatch) -> tuple[Rig, FakeFlipper, FakeFlipper]:
    monkeypatch.setattr(FlipperCLI, "settle", lambda self, s: None)  # no real radio to wait on
    air = Air()
    emt_fake, dut_fake = FakeFlipper("Emt", air), FakeFlipper("Dut", air)
    emitter, dut = Device(DeviceRole.EMITTER, "fake-emt"), Device(DeviceRole.DUT, "fake-dut")
    emitter.transport._factory = emt_fake
    dut.transport._factory = dut_fake
    emitter.open()
    dut.open()
    return Rig(emitter, dut), emt_fake, dut_fake


SIMULATED = ["subghz", "infrared", "ibutton", "rfid", "gpio"]


@pytest.mark.parametrize(
    "fixture",
    [pytest.param(f, id=f.id) for s in SIMULATED for f in load_fixtures(s)],
)
def test_round_trip_orchestration(
    fake_rig: tuple[Rig, FakeFlipper, FakeFlipper], fixture: Fixture
) -> None:
    rig, _, _ = fake_rig
    result = rig.round_trip(fixture)
    assert result.passed, result.explain()
    assert result.dut_fw == "1.4.0"


def test_wrong_expectation_fails_loudly(fake_rig: tuple[Rig, FakeFlipper, FakeFlipper]) -> None:
    rig, _, _ = fake_rig
    good = next(f for f in load_fixtures("subghz") if f.id == "princeton_433_92")
    bad = good.model_copy(
        update={"expected": good.expected.model_copy(update={"payload": "FFFFFF"})}
    )
    result = rig.round_trip(bad)
    assert not result.passed
    assert "expected: subghz:Princeton 24bit FFFFFF" in result.explain()
    assert "123456" in result.explain()


def test_command_order_receiver_first(fake_rig: tuple[Rig, FakeFlipper, FakeFlipper]) -> None:
    rig, emt, dut = fake_rig
    rig.round_trip(next(f for f in load_fixtures("subghz") if f.id == "princeton_433_92"))
    assert dut.commands[-1] == "subghz rx 433920000 0"
    assert emt.commands[-1] == "subghz tx 123456 433920000 400 10 0"


def test_file_stimulus_is_uploaded_and_verified(
    fake_rig: tuple[Rig, FakeFlipper, FakeFlipper],
) -> None:
    rig, emt, _ = fake_rig
    fx = next(f for f in load_fixtures("subghz") if f.id == "came_12bit_433_92")
    assert rig.round_trip(fx).passed
    assert fx.stimulus_path is not None
    assert emt.files["/ext/flci/subghz/came_12bit_433_92.sub"] == fx.stimulus_path.read_bytes()
    assert any(c.startswith("storage md5") for c in emt.commands)


def test_one_shot_read_times_out_cleanly(fake_rig: tuple[Rig, FakeFlipper, FakeFlipper]) -> None:
    rig, _, _ = fake_rig
    out, completed = rig.dut.transport.run_bounded("ikey read", timeout_s=0.3)
    assert not completed
    assert "Press Ctrl+C to abort" in out
    assert rig.dut.cli.device_info()["hardware_name"] == "Dut"  # CLI still usable
