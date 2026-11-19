"""The rig: one emitter, one DUT, one air gap. ``round_trip`` is the whole test.

``direction`` picks who transmits:

- ``dut_rx``: the known-good emitter sends, the candidate DUT decodes (receive path).
- ``dut_tx``: the candidate DUT sends, the known-good emitter decodes (transmit path).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from flci.devices import Device
from flci.errors import FlciUnsupported
from flci.schema import Fixture, NormalizedDecode
from flci.subsystems import REGISTRY
from flci.subsystems.base import DIRECTIONS

log = logging.getLogger(__name__)


@dataclass
class RoundTripResult:
    fixture_id: str
    passed: bool
    expected: NormalizedDecode | None
    decodes: list[NormalizedDecode]
    dut_output: str  # raw output of whichever device received
    duration_s: float
    emitter_fw: str
    dut_fw: str
    direction: str = "dut_rx"
    expect_no_decode: bool = False
    over_budget: bool = False
    max_duration_s: float | None = None
    notes: list[str] = field(default_factory=list)
    battery: dict[str, int | None] = field(default_factory=dict)

    @property
    def receiver_label(self) -> str:
        return "DUT" if self.direction == "dut_rx" else "emitter (known-good)"

    def explain(self) -> str:
        got = "\n    ".join(d.short() for d in self.decodes) or "<no decodes>"
        want = "no decode at all" if self.expected is None else self.expected.short()
        way = (
            "emitter -> DUT (testing DUT receive)"
            if self.direction == "dut_rx"
            else "DUT -> emitter (testing DUT transmit)"
        )
        budget = ""
        if self.max_duration_s is not None:
            flag = " EXCEEDED" if self.over_budget else ""
            budget = f" (budget {self.max_duration_s:.1f}s{flag})"
        notes = "".join(f"\n  note: {n}" for n in self.notes)
        return (
            f"fixture {self.fixture_id} [{way}]: {'PASS' if self.passed else 'FAIL'} "
            f"in {self.duration_s:.2f}s{budget} "
            f"(emitter fw {self.emitter_fw}, DUT fw {self.dut_fw})\n"
            f"  expected: {want}\n"
            f"  {self.receiver_label} decoded:\n    {got}{notes}\n"
            f"  raw {self.receiver_label} output (tail):\n{self.dut_output[-800:]}"
        )


class Rig:
    def __init__(self, emitter: Device, dut: Device):
        self.emitter = emitter
        self.dut = dut

    def reset(self) -> None:
        """Explicit clean state on both sides before every test."""
        for dev in (self.emitter, self.dut):
            if dev.transport.is_open:
                dev.cli.nfc_exit()
                dev.transport.reset()

    def preflight(self, required: tuple[str, ...]) -> None:
        """Fail fast (as a skip) if either firmware lacks a CLI command we need."""
        for dev in (self.emitter, self.dut):
            if not dev.commands:  # `help` unparsable: don't block, the command will tell us
                continue
            missing = [c for c in required if c not in dev.commands]
            if missing:
                raise FlciUnsupported(
                    f"{dev.role.value} firmware {dev.firmware} has no CLI command(s) {missing}"
                )

    def round_trip(self, fixture: Fixture, direction: str = "dut_rx") -> RoundTripResult:
        sub = REGISTRY[fixture.subsystem]()
        if direction not in DIRECTIONS:
            raise ValueError(f"direction must be one of {DIRECTIONS}, got {direction!r}")
        if direction not in sub.directions:
            raise ValueError(f"{fixture.subsystem} only runs {sub.directions}, not {direction}")
        sender, receiver = (
            (self.emitter, self.dut) if direction == "dut_rx" else (self.dut, self.emitter)
        )
        self.preflight(sub.required_commands)
        self.reset()
        sub.prepare(sender.cli, receiver.cli, fixture)
        start = time.monotonic()
        try:
            ex = sub.exchange(sender.cli, receiver.cli, fixture)
        finally:
            sub.cleanup(sender.cli, receiver.cli)
        duration = time.monotonic() - start
        decodes, raw = ex.decodes, ex.dut_output
        if fixture.expected is None:
            passed = not decodes
        else:
            passed = any(d.matches(fixture.expected) for d in decodes)
        over = fixture.max_duration_s is not None and duration > fixture.max_duration_s
        notes = list(ex.notes)
        if over:
            notes.append(f"decode correct but took {duration:.2f}s > {fixture.max_duration_s}s")
            passed = False
        result = RoundTripResult(
            fixture_id=fixture.id,
            passed=passed,
            expected=fixture.expected,
            decodes=decodes,
            dut_output=raw,
            duration_s=duration,
            emitter_fw=self.emitter.firmware,
            dut_fw=self.dut.firmware,
            direction=direction,
            expect_no_decode=fixture.expect_no_decode,
            over_budget=over,
            max_duration_s=fixture.max_duration_s,
            notes=notes,
            battery={
                "emitter": self.emitter.battery_percent(),
                "dut": self.dut.battery_percent(),
            },
        )
        log.info(result.explain())
        return result
