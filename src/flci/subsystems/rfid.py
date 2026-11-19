"""RFID 125 kHz: the sender runs ``rfid emulate``; the receiver runs one ``rfid read``.

Place the Flippers back to back (the 125 kHz coil is behind the back cover).
"""

from __future__ import annotations

from flci.cli import FlipperCLI
from flci.schema import Fixture, NormalizedDecode
from flci.subsystems.base import EmitterFirst, as_int


class Rfid(EmitterFirst):
    name = "rfid"
    required_commands = ("rfid",)
    kinds = ("emulate", "silence")

    def start_emit(self, sender: FlipperCLI, fixture: Fixture) -> None:
        self.kind(fixture)
        s = fixture.stimulus
        sender.rfid_emulate_start(str(s["protocol"]), str(s["data"]).replace(" ", ""))

    def read(self, receiver: FlipperCLI, fixture: Fixture) -> tuple[list[NormalizedDecode], str]:
        s = fixture.stimulus
        return receiver.rfid_read(
            mode=str(s.get("read_mode", "normal")),
            timeout_s=as_int(s.get("read_timeout_s", 10)),
        )

    def stop_emit(self, sender: FlipperCLI) -> None:
        sender.t.stop_stream()
