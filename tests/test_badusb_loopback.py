"""BadUSB (PARTIAL, operator-assisted): DUT types into the host, host captures via evdev.

Needs ``FLCI_OPERATOR=1``, ``badusb`` in FLCI_CAPABILITIES, Linux + evdev, and ``pytest -s``
so the operator prompts are visible. Never runs unattended in CI.
"""

from __future__ import annotations

import os

import pytest
from conftest import fixture_params, run_round_trip

from flci.hostio.hid_capture import HidCaptureUnavailable, _evdev
from flci.rig import Rig
from flci.schema import Fixture


@pytest.mark.parametrize("fixture", fixture_params("badusb"))
def test_badusb_round_trip(rig: Rig, fixture: Fixture, record_property: object) -> None:
    if os.environ.get("FLCI_OPERATOR") != "1":
        pytest.skip("BadUSB needs a human to press OK/Back on the DUT: set FLCI_OPERATOR=1")
    try:
        _evdev()
    except HidCaptureUnavailable as e:
        pytest.skip(f"BadUSB host capture unavailable: {e}")
    run_round_trip(rig, fixture, record_property)
