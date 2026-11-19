"""Infrared: the receiver runs ``ir rx``; the sender runs ``ir tx <protocol> <address> <command>``.

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
    required_commands = ("ir",)
    kinds = ("message", "silence")

    def arm(self, receiver: FlipperCLI, fixture: Fixture) -> None:
        self.kind(fixture)
        receiver.ir_rx_start()
        receiver.settle(RX_SETTLE_S)

    def emit(self, sender: FlipperCLI, fixture: Fixture) -> None:
        s = fixture.stimulus
        for _ in range(as_int(s.get("bursts", 3))):
            sender.ir_tx(str(s["protocol"]), as_int(s["address"]), as_int(s["command"]))
            sender.settle(0.15)

    def collect(self, receiver: FlipperCLI, fixture: Fixture) -> tuple[list[NormalizedDecode], str]:
        receiver.settle(TAIL_S)
        return receiver.ir_rx_stop()
