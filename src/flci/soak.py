"""Soak runs: every fixture N times, to measure flakiness instead of guessing it.

Output feeds docs/ROADMAP.md ("Known nondeterminism") and the RFC evidence table.
"""

from __future__ import annotations

import json
import math
import statistics
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field

from flci.errors import FlciEnvironmentSkip, FlciError
from flci.rig import Rig
from flci.schema import Fixture


@dataclass
class FixtureStats:
    fixture_id: str
    subsystem: str
    direction: str = "dut_rx"
    runs: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped_reason: str | None = None
    durations_s: list[float] = field(default_factory=list)
    distinct_decodes: dict[str, int] = field(default_factory=dict)
    error_messages: list[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.runs if self.runs else 0.0

    @property
    def flaky(self) -> bool:
        return 0 < self.passed < self.runs

    @property
    def case_id(self) -> str:
        return f"{self.fixture_id}@{self.direction}"

    def suggested_budget_s(self) -> float | None:
        """p95 x 1.5, rounded up to 0.5 s; only once there are enough samples to mean it."""
        p95 = self.p(0.95)
        if p95 is None or len(self.durations_s) < 10:
            return None
        return math.ceil(p95 * 1.5 * 2) / 2

    def p(self, q: float) -> float | None:
        if not self.durations_s:
            return None
        xs = sorted(self.durations_s)
        return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


@dataclass
class SoakReport:
    started: str
    runs_per_fixture: int
    emitter_fw: str
    dut_fw: str
    fixtures: list[FixtureStats]

    def to_json(self) -> str:
        return json.dumps(
            {**asdict(self), "fixtures": [asdict(f) for f in self.fixtures]}, indent=2
        )

    @classmethod
    def from_json(cls, text: str) -> SoakReport:
        d = json.loads(text)
        d["fixtures"] = [FixtureStats(**f) for f in d["fixtures"]]
        return cls(**d)

    def markdown(self) -> str:
        lines = [
            f"### Soak: {self.runs_per_fixture} runs/fixture "
            f"(DUT fw {self.dut_fw}, emitter fw {self.emitter_fw}, {self.started})",
            "",
            "| Case | Subsystem | Runs | Pass | Fail | Err | Rate | p50 s | p95 s "
            "| Budget? | Decodes |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        for f in self.fixtures:
            if f.skipped_reason:
                lines.append(f"| {f.case_id} | {f.subsystem} | skipped: {f.skipped_reason} |")
                continue
            p50, p95 = f.p(0.5), f.p(0.95)
            budget = f.suggested_budget_s()
            budget_txt = f"{budget:.1f}" if budget is not None else "n<10"
            decodes = "; ".join(f"{k} ×{v}" for k, v in f.distinct_decodes.items()) or "none"
            flag = " ⚠️ flaky" if f.flaky else ""
            lines.append(
                f"| {f.case_id}{flag} | {f.subsystem} | {f.runs} | {f.passed} | {f.failed} | "
                f"{f.errors} | {f.pass_rate:.0%} | {p50 or 0:.2f} | {p95 or 0:.2f} | "
                f"{budget_txt} | {decodes} |"
            )
        return "\n".join(lines)

    def evidence_table(self) -> str:
        """Per-subsystem rows in the format of the RFC's *Evidence* table."""
        by_sub: dict[str, list[FixtureStats]] = {}
        for f in self.fixtures:
            if not f.skipped_reason:
                by_sub.setdefault(f.subsystem, []).append(f)
        lines = [
            "| Subsystem | Cases | Runs | Pass | Flaky | Firmware |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for sub, fs in sorted(by_sub.items()):
            lines.append(
                f"| {sub} | {len(fs)} | {sum(f.runs for f in fs)} | "
                f"{sum(f.passed for f in fs)} | {sum(f.flaky for f in fs)} | {self.dut_fw} |"
            )
        return "\n".join(lines)


def run_soak(
    rig: Rig,
    fixtures: Iterable[Fixture],
    runs: int,
    progress: Callable[[str], None] = print,
    directions: Iterable[str] = ("dut_rx",),
) -> SoakReport:
    from flci.subsystems import REGISTRY

    dirs = list(directions)
    report = SoakReport(
        started=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        runs_per_fixture=runs,
        emitter_fw=rig.emitter.firmware,
        dut_fw=rig.dut.firmware,
        fixtures=[],
    )
    cases = [(fx, d) for fx in fixtures for d in dirs if d in REGISTRY[fx.subsystem].directions]
    for fx, direction in cases:
        st = FixtureStats(fixture_id=fx.id, subsystem=fx.subsystem, direction=direction)
        report.fixtures.append(st)
        label = st.case_id
        for i in range(runs):
            try:
                r = rig.round_trip(fx, direction)
            except FlciEnvironmentSkip as e:
                st.skipped_reason = str(e)
                progress(f"{label}: skipped ({e})")
                break
            except FlciError as e:
                st.runs += 1
                st.errors += 1
                st.error_messages.append(str(e)[:300])
                progress(f"{label} [{i + 1}/{runs}] ERROR {e}")
                continue
            st.runs += 1
            st.durations_s.append(round(r.duration_s, 3))
            st.passed += r.passed
            st.failed += not r.passed
            for d in r.decodes:
                st.distinct_decodes[d.short()] = st.distinct_decodes.get(d.short(), 0) + 1
            progress(f"{label} [{i + 1}/{runs}] {'pass' if r.passed else 'FAIL'}")
        if st.durations_s:
            progress(
                f"{fx.id}: {st.passed}/{st.runs} median {statistics.median(st.durations_s):.2f}s"
            )
    return report
