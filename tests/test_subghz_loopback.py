"""Sub-GHz loopback: emitter transmits, DUT decodes, we compare against the fixture."""

from __future__ import annotations

import pytest

from flci.fixtures import load_fixtures
from flci.rig import Rig
from flci.schema import Fixture

FIXTURES = load_fixtures("subghz")


@pytest.mark.hardware
@pytest.mark.subghz
@pytest.mark.parametrize("fixture", FIXTURES, ids=[f.id for f in FIXTURES])
def test_subghz_round_trip(rig: Rig, fixture: Fixture, record_property: object) -> None:
    result = rig.round_trip(fixture)
    if callable(record_property):
        record_property("dut_firmware", result.dut_fw)
        record_property("emitter_firmware", result.emitter_fw)
        record_property("decodes", "; ".join(d.short() for d in result.decodes))
    assert result.passed, result.explain()
