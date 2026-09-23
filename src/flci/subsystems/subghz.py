"""Sub-GHz loopback: emitter runs ``subghz tx``, DUT runs ``subghz rx``."""

from __future__ import annotations

from typing import Any

from flci.cli import SUBGHZ_DEVICE_INTERNAL, FlipperCLI
from flci.schema import Fixture, NormalizedDecode
from flci.subsystems.base import Subsystem

# Time between the DUT printing "ready" and the radio actually listening, and between
# the last TX burst and stopping RX. Measured conservatively; see docs/ROADMAP.md.
RX_SETTLE_S = 0.3
TAIL_S = 0.5


def _int(v: Any) -> int:
    return int(v, 0) if isinstance(v, str) else int(v)


class SubGhz(Subsystem):
    name = "subghz"

    def arm(self, dut: FlipperCLI, fixture: Fixture) -> None:
        s = fixture.stimulus
        device = _int(s.get("rx_device", SUBGHZ_DEVICE_INTERNAL))
        dut.subghz_rx_start(_int(s["frequency_hz"]), device)
        dut.settle(RX_SETTLE_S)

    def emit(self, emitter: FlipperCLI, fixture: Fixture) -> None:
        s = fixture.stimulus
        kind = s.get("kind", "princeton_tx")
        if kind != "princeton_tx":
            raise NotImplementedError(f"subghz stimulus kind {kind!r} lands in Phase 2")
        emitter.subghz_tx(
            key=_int(s["key"]),
            frequency_hz=_int(s["frequency_hz"]),
            te_us=_int(s.get("te_us", 400)),
            repeat=_int(s.get("repeat", 10)),
            device=_int(s.get("tx_device", SUBGHZ_DEVICE_INTERNAL)),
        )

    def collect(self, dut: FlipperCLI, fixture: Fixture) -> tuple[list[NormalizedDecode], str]:
        dut.settle(TAIL_S)
        return dut.subghz_rx_stop(_int(fixture.stimulus["frequency_hz"]))
