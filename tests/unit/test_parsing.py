"""Offline tests for parsers and schema. These check our text handling, not the radio.

Sample output is built from the firmware's own format strings (see src/flci/cli.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from flci.cli import parse_device_info, parse_subghz_decodes
from flci.devices import PortInfo, RoleConfigError, resolve_roles
from flci.fixtures import FixtureError, load_fixture, load_fixtures
from flci.schema import NormalizedDecode, normalize_hex
from flci.transport import SerialTransport

RX_OUTPUT = (
    "..Princeton 24bit\r\n"
    "Key:0x00123456\r\n"
    "Yek:0x006A2C48\r\n"
    "Sn:0x12345 Btn:6\r\n"
    "Te:398us  GT:Te*31\r\n"
    ".\r\n"
    "Princeton 24bit\r\n"
    "Key:0x00123456\r\n"
    "Yek:0x006A2C48\r\n"
    "Sn:0x12345 Btn:6\r\n"
    "Te:401us  GT:Te*31\r\n"
    "\r\nPackets received 2\r\n"
)


def test_parse_subghz_decodes() -> None:
    decodes = parse_subghz_decodes(RX_OUTPUT, 433920000)
    assert len(decodes) == 2
    d = decodes[0]
    assert (d.protocol, d.bits, d.payload, d.frequency_hz) == ("Princeton", 24, "123456", 433920000)


def test_parse_protocol_with_space() -> None:
    [d] = parse_subghz_decodes("Nice FLO 12bit\r\nKey:0x00000ABC\r\n")
    assert (d.protocol, d.bits, d.payload) == ("Nice FLO", 12, "ABC")


def test_parse_nothing() -> None:
    assert parse_subghz_decodes("....\r\nPackets received 0\r\n") == []


def test_parse_device_info() -> None:
    text = (
        f"{'hardware_name':<30}: Dut1\r\n"
        f"{'firmware_version':<30}: 1.4.0\r\n"
        f"{'firmware_commit_hash':<30}: abc123\r\n"
    )
    info = parse_device_info(text)
    assert info["hardware_name"] == "Dut1"
    assert info["firmware_version"] == "1.4.0"


@pytest.mark.parametrize(
    "value,bits,want",
    [
        ("0x00123456", 24, "123456"),
        ("00 12 34 56", 24, "123456"),
        (0xABC, 12, "ABC"),
        ("0x5", 8, "05"),
    ],
)
def test_normalize_hex(value: str | int, bits: int, want: str) -> None:
    assert normalize_hex(value, bits) == want


def test_matches_ignores_raw_but_not_payload() -> None:
    a = NormalizedDecode(subsystem="subghz", protocol="Princeton", payload="123456", bits=24)
    b = a.model_copy(update={"raw": {"x": 1}, "payload": "0x00123456"})
    c = a.model_copy(update={"payload": "123457"})
    assert a.matches(b)
    assert not a.matches(c)


def test_transport_clean_strips_echo_and_prompt() -> None:
    raw = "device_info\r\nhardware_name : X\r\n\r\n>: "
    assert SerialTransport._clean(raw, "device_info") == "hardware_name : X"


def test_shipped_fixtures_load() -> None:
    fixtures = load_fixtures("subghz")
    assert fixtures, "no Sub-GHz fixtures found"
    for f in fixtures:
        assert f.stimulus_path is not None and f.stimulus_path.is_file()


def test_corrupted_fixture_fails_loudly(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: x\nsubsystem: subghz\nstimulus: {}\nexpected: {subsystem: subghz}\n")
    with pytest.raises(FixtureError, match="bad.yaml"):
        load_fixture(bad)


def test_roles_must_be_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FLCI_DUT", raising=False)
    monkeypatch.delenv("FLCI_EMITTER", raising=False)
    ports = [PortInfo("/dev/a", None, ""), PortInfo("/dev/b", None, "")]
    with pytest.raises(RoleConfigError, match="FLCI_DUT"):
        resolve_roles(ports)


def test_roles_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLCI_DUT", "Dut1")
    monkeypatch.setenv("FLCI_EMITTER", "Emt2")
    ports = [
        PortInfo("/dev/cu.usbmodemflip_Dut11", None, ""),
        PortInfo("/dev/cu.usbmodemflip_Emt21", None, ""),
    ]
    assert resolve_roles(ports) == ("/dev/cu.usbmodemflip_Emt21", "/dev/cu.usbmodemflip_Dut11")
