"""Summaries and regression diffs from pytest JUnit XML (hardware round-trip tests only)."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

_CASE = re.compile(r"test_(?P<sub>[a-z]+)_round_trip\[(?P<fixture>[^\]]+)\]")
ICON = {"pass": "✅", "fail": "❌", "error": "💥", "skip": "⏭️"}


def first_line(text: str, limit: int = 200) -> str:
    return next((ln.strip() for ln in text.splitlines() if ln.strip()), "")[:limit]


@dataclass
class CaseResult:
    fixture_id: str
    subsystem: str
    status: str  # pass | fail | error | skip
    message: str = ""
    properties: dict[str, str] = field(default_factory=dict)


def parse_junit(path: Path) -> dict[str, CaseResult]:
    root = ET.parse(path).getroot()
    out: dict[str, CaseResult] = {}
    for tc in root.iter("testcase"):
        m = _CASE.search(tc.get("name", ""))
        if not m:
            continue  # unit tests etc.
        status, message = "pass", ""
        for tag, st in (("failure", "fail"), ("error", "error"), ("skipped", "skip")):
            el = tc.find(tag)
            if el is not None:
                status = st
                message = (el.get("message") or el.text or "").strip()
                break
        props = {p.get("name", ""): p.get("value", "") for p in tc.iter("property")}
        out[m.group("fixture")] = CaseResult(
            m.group("fixture"), m.group("sub"), status, message, props
        )
    return out


def summary_markdown(results: dict[str, CaseResult], title: str = "HIL results") -> str:
    by_sub: dict[str, list[CaseResult]] = {}
    for r in results.values():
        by_sub.setdefault(r.subsystem, []).append(r)
    fw = next((r.properties.get("dut_firmware") for r in results.values() if r.properties), None)
    lines = [f"## {title}" + (f" (DUT fw {fw})" if fw else ""), ""]
    if not results:
        return "\n".join(lines + ["No hardware round-trip tests in this report."])
    lines += ["| Subsystem | ✅ | ❌ | 💥 | ⏭️ |", "|---|---:|---:|---:|---:|"]
    for sub, rs in sorted(by_sub.items()):
        c = {k: sum(r.status == k for r in rs) for k in ICON}
        lines.append(f"| {sub} | {c['pass']} | {c['fail']} | {c['error']} | {c['skip']} |")
    bad = [r for r in results.values() if r.status in ("fail", "error")]
    if bad:
        lines += ["", "### Failures", ""]
        for r in bad:
            first = first_line(r.message)
            got = r.properties.get("decodes", "")
            lines.append(
                f"- {ICON[r.status]} `{r.fixture_id}`: {first}" + (f" (got: {got})" if got else "")
            )
    skips = {first_line(r.message, 160) for r in results.values() if r.status == "skip"}
    if skips:
        lines += ["", "<details><summary>Skip reasons</summary>", ""]
        lines += [f"- {s}" for s in sorted(skips)] + ["", "</details>"]
    return "\n".join(lines)


@dataclass
class Comparison:
    regressions: list[str]  # pass -> fail/error
    fixed: list[str]  # fail/error -> pass
    still_failing: list[str]
    new_cases: list[str]
    removed_cases: list[str]
    coverage_lost: list[str]  # pass -> skip

    @property
    def ok(self) -> bool:
        return not self.regressions


def compare(baseline: dict[str, CaseResult], candidate: dict[str, CaseResult]) -> Comparison:
    bad = ("fail", "error")
    both = baseline.keys() & candidate.keys()
    return Comparison(
        regressions=sorted(
            k for k in both if baseline[k].status == "pass" and candidate[k].status in bad
        ),
        fixed=sorted(
            k for k in both if baseline[k].status in bad and candidate[k].status == "pass"
        ),
        still_failing=sorted(
            k for k in both if baseline[k].status in bad and candidate[k].status in bad
        ),
        new_cases=sorted(candidate.keys() - baseline.keys()),
        removed_cases=sorted(baseline.keys() - candidate.keys()),
        coverage_lost=sorted(
            k for k in both if baseline[k].status == "pass" and candidate[k].status == "skip"
        ),
    )


def comparison_markdown(c: Comparison, candidate: dict[str, CaseResult]) -> str:
    head = "## ❌ Regressions vs baseline" if c.regressions else "## ✅ No regressions vs baseline"
    lines = [head, ""]
    for label, items in (
        ("Regressed (passed before, fails now)", c.regressions),
        ("Fixed", c.fixed),
        ("Still failing", c.still_failing),
        ("Passed before, skipped now", c.coverage_lost),
        ("New cases", c.new_cases),
        ("Removed cases", c.removed_cases),
    ):
        if items:
            lines.append(f"**{label}** ({len(items)})")
            for k in items:
                msg = first_line(candidate[k].message, 160) if k in candidate else ""
                lines.append(f"- `{k}`" + (f": {msg}" if msg and label.startswith("Regr") else ""))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
