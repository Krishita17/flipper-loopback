"""JUnit summary / regression compare / flci CLI, offline."""

from __future__ import annotations

from pathlib import Path

import pytest

from flci.__main__ import main
from flci.cli import parse_help
from flci.report import compare, comparison_markdown, parse_junit, summary_markdown


def _junit(tmp_path: Path, name: str, cases: dict[str, str]) -> Path:
    body = []
    for case, status in cases.items():
        sub = case.split("_")[0]
        inner = {
            "pass": "",
            "fail": '<failure message="expected X, got Y">trace</failure>',
            "skip": '<skipped message="hardware: need 2 Flippers" />',
        }[status]
        body.append(
            f'<testcase classname="tests.test_{sub}_loopback" '
            f'name="test_{sub}_round_trip[{case}]">'
            f'<properties><property name="dut_firmware" value="1.4.0"/></properties>{inner}'
            "</testcase>"
        )
    body.append('<testcase classname="tests.unit.test_parsing" name="test_x" />')
    path = tmp_path / name
    path.write_text(
        f'<testsuites><testsuite name="pytest">{"".join(body)}</testsuite></testsuites>'
    )
    return path


def test_parse_and_summarise(tmp_path: Path) -> None:
    j = _junit(tmp_path, "a.xml", {"subghz_a": "pass", "subghz_b": "fail", "rfid_c": "skip"})
    results = parse_junit(j)
    assert set(results) == {"subghz_a", "subghz_b", "rfid_c"}  # unit tests ignored
    md = summary_markdown(results)
    assert "| subghz | 1 | 1 | 0 | 0 |" in md
    assert "`subghz_b`: expected X, got Y" in md
    assert "DUT fw 1.4.0" in md


def test_compare_finds_regressions(tmp_path: Path) -> None:
    base = _junit(tmp_path, "b.xml", {"subghz_a": "pass", "subghz_b": "fail", "ir_c": "pass"})
    cand = _junit(tmp_path, "c.xml", {"subghz_a": "fail", "subghz_b": "pass", "ir_c": "skip"})
    c = compare(parse_junit(base), parse_junit(cand))
    assert c.regressions == ["subghz_a"]
    assert c.fixed == ["subghz_b"]
    assert c.coverage_lost == ["ir_c"]
    assert not c.ok
    assert "Regressions vs baseline" in comparison_markdown(c, parse_junit(cand))
    assert main(["compare", str(base), str(cand)]) == 1
    assert main(["compare", str(base), str(base)]) == 0


def test_parse_help() -> None:
    text = (
        "Available commands:\r\n\x1b[32m"
        + "".join(f"{c:<30}" for c in ["!", "?", "device_info"])
        + "\r\nsubghz                        ir\r\n\x1b[0m\r\nFind out more: https://docs"
    )
    assert {"device_info", "subghz", "ir", "?"} <= parse_help(text)
    assert "https://docs" not in parse_help(text)


def test_cli_entrypoint(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["fixtures"]) == 0
    out = capsys.readouterr().out
    assert "fixtures OK" in out and "linear_10bit_300" in out
    assert main(["nope"]) == 2
