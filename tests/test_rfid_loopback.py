"""RFID 125 kHz: emitter emulates a card, DUT reads it back to back."""

from __future__ import annotations

import pytest
from conftest import fixture_params, run_round_trip

from flci.rig import Rig
from flci.schema import Fixture


@pytest.mark.parametrize("fixture,direction", fixture_params("rfid"))
def test_rfid_round_trip(
    rig: Rig, fixture: Fixture, direction: str, record_property: object
) -> None:
    run_round_trip(rig, fixture, direction, record_property)
