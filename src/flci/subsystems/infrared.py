"""Infrared: DUT runs ``ir rx``; emitter runs ``ir tx <protocol> <address> <command>``.

The Flipper IR LED and receiver are on the top edge; point the two top edges at each other
(the jig's ``head_to_head`` mode).
"""

from __future__ import annotations

from flci.cli import FlipperCLI
from flci.schema import Fixture, NormalizedDecode
from flci.subsystems.base import ReceiverFirst, as_int

RX_SETTLE_S = 0.2
TAIL_S = 0.4


class Infrared(ReceiverFirst):
    name = "infrared"
    kinds = ("message",)

    def arm(self, dut: FlipperCLI, fixture: Fixture) -> None:
        self.kind(fixture)
        dut.ir_rx_start()
        dut.settle(RX_SETTLE_S)

    def emit(self, emitter: FlipperCLI, fixture: Fixture) -> None:
        s = fixture.stimulus
        for _ in range(as_int(s.get("bursts", 3))):
            emitter.ir_tx(str(s["protocol"]), as_int(s["address"]), as_int(s["command"]))
            emitter.settle(0.15)

    def collect(self, dut: FlipperCLI, fixture: Fixture) -> tuple[list[NormalizedDecode], str]:
        dut.settle(TAIL_S)
        return dut.ir_rx_stop()
