"""iButton: emitter runs ``ikey emulate``; DUT runs one ``ikey read``.

Wire both Flippers' 1-Wire/iButton line (GPIO header pin 17) together plus GND
(pin 18). See hardware/WIRING.md.
"""

from __future__ import annotations

from flci.cli import FlipperCLI
from flci.schema import Fixture, NormalizedDecode
from flci.subsystems.base import EmitterFirst, as_int


class IButton(EmitterFirst):
    name = "ibutton"
    required_commands = ("ikey",)
    kinds = ("emulate",)

    def start_emit(self, emitter: FlipperCLI, fixture: Fixture) -> None:
        self.kind(fixture)
        s = fixture.stimulus
        emitter.ibutton_emulate_start(str(s["key_type"]), str(s["key_data"]).replace(" ", ""))

    def read(self, dut: FlipperCLI, fixture: Fixture) -> tuple[list[NormalizedDecode], str]:
        return dut.ibutton_read(timeout_s=as_int(fixture.stimulus.get("read_timeout_s", 10)))

    def stop_emit(self, emitter: FlipperCLI) -> None:
        emitter.t.stop_stream()
