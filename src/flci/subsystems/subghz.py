"""Sub-GHz: DUT runs ``subghz rx``; emitter runs ``subghz tx`` or ``subghz tx_from_file``."""

from __future__ import annotations

from flci.cli import REMOTE_ROOT, SUBGHZ_DEVICE_INTERNAL, FlipperCLI
from flci.schema import Fixture, NormalizedDecode
from flci.subsystems.base import ReceiverFirst, as_int

# Time between the DUT printing "ready" and the radio actually listening, and between
# the last TX burst and stopping RX. Conservative; see docs/ROADMAP.md.
RX_SETTLE_S = 0.3
TAIL_S = 0.5


def remote_path(fixture: Fixture) -> str:
    return f"{REMOTE_ROOT}/subghz/{fixture.id}.sub"


class SubGhz(ReceiverFirst):
    name = "subghz"
    kinds = ("princeton_tx", "file")

    def _freq(self, fixture: Fixture) -> int:
        if "frequency_hz" in fixture.stimulus:
            return as_int(fixture.stimulus["frequency_hz"])
        if fixture.expected.frequency_hz:
            return fixture.expected.frequency_hz
        raise ValueError(f"{fixture.id}: need stimulus.frequency_hz or expected.frequency_hz")

    def prepare(self, emitter: FlipperCLI, dut: FlipperCLI, fixture: Fixture) -> None:
        if self.kind(fixture) == "file":
            if fixture.stimulus_path is None:
                raise ValueError(f"{fixture.id}: kind 'file' needs stimulus_path")
            emitter.storage_upload(fixture.stimulus_path.read_bytes(), remote_path(fixture))

    def arm(self, dut: FlipperCLI, fixture: Fixture) -> None:
        device = as_int(fixture.stimulus.get("rx_device", SUBGHZ_DEVICE_INTERNAL))
        dut.subghz_rx_start(self._freq(fixture), device)
        dut.settle(RX_SETTLE_S)

    def emit(self, emitter: FlipperCLI, fixture: Fixture) -> None:
        s = fixture.stimulus
        device = as_int(s.get("tx_device", SUBGHZ_DEVICE_INTERNAL))
        if self.kind(fixture) == "princeton_tx":
            emitter.subghz_tx(
                key=as_int(s["key"]),
                frequency_hz=self._freq(fixture),
                te_us=as_int(s.get("te_us", 400)),
                repeat=as_int(s.get("repeat", 10)),
                device=device,
            )
        else:
            # Key files transmit their own repeat count; send the file a few times.
            for _ in range(as_int(s.get("bursts", 3))):
                emitter.subghz_tx_file(remote_path(fixture), 1, device)

    def collect(self, dut: FlipperCLI, fixture: Fixture) -> tuple[list[NormalizedDecode], str]:
        dut.settle(TAIL_S)
        return dut.subghz_rx_stop(self._freq(fixture))
