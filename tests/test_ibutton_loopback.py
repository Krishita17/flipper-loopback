"""iButton: emitter emulates a key, DUT reads it over a wired 1-Wire line."""

from __future__ import annotations

import pytest
from conftest import fixture_params, run_round_trip

from flci.rig import Rig
from flci.schema import Fixture


@pytest.mark.parametrize("fixture,direction", fixture_params("ibutton"))
def test_ibutton_round_trip(
    rig: Rig, fixture: Fixture, direction: str, record_property: object
) -> None:
    run_round_trip(rig, fixture, direction, record_property)
