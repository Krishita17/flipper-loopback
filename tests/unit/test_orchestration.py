"""Offline orchestration tests against FakeFlipper (see its docstring: NOT hardware)."""

from __future__ import annotations

import pytest

from flci.cli import FlipperCLI
from flci.devices import Device, DeviceRole
from flci.errors import FlciRegionRestricted, FlciUnsupported
from flci.fixtures import load_fixtures
from flci.rig import Rig
from flci.schema import Fixture
from flci.soak import SoakReport, run_soak

from .fake_flipper import Air, FakeFlipper


def _rig(emt_fake: FakeFlipper, dut_fake: FakeFlipper) -> Rig:
    emitter, dut = Device(DeviceRole.EMITTER, "fake-emt"), Device(DeviceRole.DUT, "fake-dut")
    emitter.transport._factory = emt_fake
    dut.transport._factory = dut_fake
    emitter.open()
    dut.open()
    return Rig(emitter, dut)


@pytest.fixture
def fake_rig(monkeypatch: pytest.MonkeyPatch) -> tuple[Rig, FakeFlipper, FakeFlipper]:
    monkeypatch.setattr(FlipperCLI, "settle", lambda self, s: None)  # no real radio to wait on
    air = Air()
    emt_fake, dut_fake = FakeFlipper("Emt", air), FakeFlipper("Dut", air)
    return _rig(emt_fake, dut_fake), emt_fake, dut_fake


SIMULATED = ["subghz", "infrared", "ibutton", "rfid", "gpio"]


@pytest.mark.parametrize(
    "fixture,direction",
    [
        pytest.param(f, d, id=f"{f.id}@{d}")
        for s in SIMULATED
        for f in load_fixtures(s)
        for d in ("dut_rx", "dut_tx")
        if not (f.expect_no_decode and d == "dut_tx")  # silence is symmetric; save time
    ],
)
def test_round_trip_orchestration(
    fake_rig: tuple[Rig, FakeFlipper, FakeFlipper], fixture: Fixture, direction: str
) -> None:
    rig, _, _ = fake_rig
    result = rig.round_trip(fixture, direction)
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
    rig, emt, _ = fake_rig
    rig.round_trip(next(f for f in load_fixtures("subghz") if f.id == "princeton_433_92"))
    log = emt.air.log
    rx = log.index(("Dut", "subghz rx 433920000 0"))
    tx = log.index(("Emt", "subghz tx 123456 433920000 400 10 0"))
    assert rx < tx, "DUT must be listening before the emitter transmits"


def test_command_order_emitter_first(fake_rig: tuple[Rig, FakeFlipper, FakeFlipper]) -> None:
    rig, emt, _ = fake_rig
    rig.round_trip(next(f for f in load_fixtures("rfid") if f.id == "rfid_em4100"))
    log = emt.air.log
    assert log.index(("Emt", "rfid emulate EM4100 DC69660F12")) < log.index(
        ("Dut", "rfid read normal")
    )


def test_missing_cli_command_is_environment_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FlipperCLI, "settle", lambda self, s: None)
    air = Air()
    emt = FakeFlipper("Emt", air)
    dut = FakeFlipper("Dut", air, commands={"help", "device_info", "info", "storage"})
    rig = _rig(emt, dut)
    with pytest.raises(FlciUnsupported, match="no CLI command"):
        rig.round_trip(load_fixtures("infrared")[0])
    assert not any(c.startswith("ir ") for _, c in air.log), "must stop before touching IR"


def test_region_lock_is_environment_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FlipperCLI, "settle", lambda self, s: None)
    air = Air()
    rig = _rig(FakeFlipper("Emt", air, region_blocked_hz={300000000}), FakeFlipper("Dut", air))
    with pytest.raises(FlciRegionRestricted):
        rig.round_trip(next(f for f in load_fixtures("subghz") if f.id == "linear_10bit_300"))
    # the DUT receiver was still stopped cleanly
    assert rig.dut.cli.device_info()["hardware_name"] == "Dut"


def test_battery_recorded(fake_rig: tuple[Rig, FakeFlipper, FakeFlipper]) -> None:
    rig, _, _ = fake_rig
    r = rig.round_trip(load_fixtures("gpio")[0])
    assert r.battery == {"emitter": 87, "dut": 87}


def test_soak_counts(fake_rig: tuple[Rig, FakeFlipper, FakeFlipper]) -> None:
    rig, _, _ = fake_rig
    fx = next(f for f in load_fixtures("subghz") if f.id == "princeton_433_92")
    wrong = fx.model_copy(
        update={"id": "wrong", "expected": fx.expected.model_copy(update={"payload": "1"})}
    )
    report = run_soak(rig, [fx, wrong], runs=3, progress=lambda _: None)
    good, bad = report.fixtures
    assert (good.runs, good.passed, good.pass_rate) == (3, 3, 1.0)
    assert (bad.passed, bad.failed, bad.flaky) == (0, 3, False)
    assert "| subghz | 2 | 6 | 3 | 0 | 1.4.0 |" in report.evidence_table()
    assert good.case_id == "princeton_433_92@dut_rx"
    assert good.suggested_budget_s() is None  # fewer than 10 samples
    again = SoakReport.from_json(report.to_json())
    assert again.fixtures[0].passed == 3


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


def test_dut_tx_swaps_roles(fake_rig: tuple[Rig, FakeFlipper, FakeFlipper]) -> None:
    rig, emt, _ = fake_rig
    fx = next(f for f in load_fixtures("subghz") if f.id == "princeton_433_92")
    result = rig.round_trip(fx, "dut_tx")
    assert result.passed and result.direction == "dut_tx"
    log = emt.air.log
    assert log.index(("Emt", "subghz rx 433920000 0")) < log.index(
        ("Dut", "subghz tx 123456 433920000 400 10 0")
    ), "in dut_tx the known-good emitter listens and the DUT transmits"
    assert "DUT -> emitter (testing DUT transmit)" in result.explain()


def test_file_upload_goes_to_sender(fake_rig: tuple[Rig, FakeFlipper, FakeFlipper]) -> None:
    rig, emt, dut = fake_rig
    fx = next(f for f in load_fixtures("subghz") if f.id == "came_12bit_433_92")
    assert rig.round_trip(fx, "dut_tx").passed
    assert "/ext/flci/subghz/came_12bit_433_92.sub" in dut.files
    assert "/ext/flci/subghz/came_12bit_433_92.sub" not in emt.files


def test_negative_fixture_fails_on_ghost_decode(
    fake_rig: tuple[Rig, FakeFlipper, FakeFlipper], monkeypatch: pytest.MonkeyPatch
) -> None:
    rig, emt, _ = fake_rig
    fx = next(f for f in load_fixtures("infrared") if f.id == "ir_silence")
    assert rig.round_trip(fx).passed

    def ghost(self: FlipperCLI, seconds: float) -> None:  # noise arrives while listening
        emt.air.ir.append("NEC, A:0x01, C:0x02\r\n")

    monkeypatch.setattr(FlipperCLI, "settle", ghost)
    result = rig.round_trip(fx)
    assert not result.passed
    assert "expected: no decode at all" in result.explain()
    assert "infrared:NEC 1-2" in result.explain()


def test_timing_budget(fake_rig: tuple[Rig, FakeFlipper, FakeFlipper]) -> None:
    rig, _, _ = fake_rig
    fx = load_fixtures("gpio")[0]
    tight = fx.model_copy(update={"max_duration_s": 1e-6})
    result = rig.round_trip(tight)
    assert not result.passed and result.over_budget
    assert "EXCEEDED" in result.explain()
    assert rig.round_trip(fx.model_copy(update={"max_duration_s": 60})).passed


def test_direction_validation(fake_rig: tuple[Rig, FakeFlipper, FakeFlipper]) -> None:
    rig, _, _ = fake_rig
    with pytest.raises(ValueError, match="only runs"):
        rig.round_trip(load_fixtures("badusb")[0], "dut_rx")
    with pytest.raises(ValueError, match="direction must be"):
        rig.round_trip(load_fixtures("gpio")[0], "sideways")
