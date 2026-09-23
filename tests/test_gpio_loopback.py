"""GPIO: emitter drives a pin, DUT reads the wired pin."""

from __future__ import annotations

import pytest
from conftest import fixture_params, run_round_trip

from flci.rig import Rig
from flci.schema import Fixture


@pytest.mark.parametrize("fixture", fixture_params("gpio"))
def test_gpio_round_trip(rig: Rig, fixture: Fixture, record_property: object) -> None:
    run_round_trip(rig, fixture, record_property)
