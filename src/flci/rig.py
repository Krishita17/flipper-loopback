"""The rig: one emitter, one DUT, one air gap. ``round_trip`` is the whole test."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from flci.devices import Device
from flci.schema import Fixture, NormalizedDecode
from flci.subsystems import REGISTRY

log = logging.getLogger(__name__)


@dataclass
class RoundTripResult:
    fixture_id: str
    passed: bool
    expected: NormalizedDecode
    decodes: list[NormalizedDecode]
    dut_output: str
    duration_s: float
    emitter_fw: str
    dut_fw: str
    notes: list[str] = field(default_factory=list)

    def explain(self) -> str:
        got = "\n    ".join(d.short() for d in self.decodes) or "<no decodes>"
        return (
            f"fixture {self.fixture_id}: {'PASS' if self.passed else 'FAIL'} "
            f"in {self.duration_s:.2f}s (emitter fw {self.emitter_fw}, DUT fw {self.dut_fw})\n"
            f"  expected: {self.expected.short()}\n"
            f"  DUT decoded:\n    {got}\n"
            f"  raw DUT output (tail):\n{self.dut_output[-800:]}"
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

    def round_trip(self, fixture: Fixture) -> RoundTripResult:
        sub = REGISTRY[fixture.subsystem]()
        self.reset()
        sub.prepare(self.emitter.cli, self.dut.cli, fixture)
        start = time.monotonic()
        try:
            ex = sub.exchange(self.emitter.cli, self.dut.cli, fixture)
        finally:
            sub.cleanup(self.emitter.cli, self.dut.cli)
        decodes, raw = ex.decodes, ex.dut_output
        passed = any(d.matches(fixture.expected) for d in decodes)
        result = RoundTripResult(
            fixture_id=fixture.id,
            passed=passed,
            expected=fixture.expected,
            decodes=decodes,
            dut_output=raw,
            duration_s=time.monotonic() - start,
            emitter_fw=self.emitter.firmware,
            dut_fw=self.dut.firmware,
            notes=ex.notes,
        )
        log.info(result.explain())
        return result
