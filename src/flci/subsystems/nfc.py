"""NFC 13.56 MHz (PARTIAL): the sender emulates an uploaded ``.nfc``; the receiver
runs ``mfu info``.

Scope: MIFARE Ultralight / NTAG only, asserting tag type + UID. Other protocols need
different reader commands and emulation support is uneven; see docs/ROADMAP.md.
"""

from __future__ import annotations

from flci.cli import REMOTE_ROOT, FlipperCLI
from flci.schema import Fixture, NormalizedDecode
from flci.subsystems.base import EmitterFirst, as_int


def remote_path(fixture: Fixture) -> str:
    return f"{REMOTE_ROOT}/nfc/{fixture.id}.nfc"


class Nfc(EmitterFirst):
    name = "nfc"
    required_commands = ("nfc", "storage")
    kinds = ("emulate_file", "silence")

    def prepare(self, sender: FlipperCLI, receiver: FlipperCLI, fixture: Fixture) -> None:
        if self.is_silence(fixture):
            return
        if fixture.stimulus_path is None:
            raise ValueError(f"{fixture.id}: NFC fixtures need stimulus_path (.nfc file)")
        sender.storage_upload(fixture.stimulus_path.read_bytes(), remote_path(fixture))

    def start_emit(self, sender: FlipperCLI, fixture: Fixture) -> None:
        sender.nfc_emulate_start(remote_path(fixture))

    def read(self, receiver: FlipperCLI, fixture: Fixture) -> tuple[list[NormalizedDecode], str]:
        return receiver.nfc_mfu_info(timeout_s=as_int(fixture.stimulus.get("read_timeout_s", 10)))

    def stop_emit(self, sender: FlipperCLI) -> None:
        sender.nfc_emulate_stop()

    def cleanup(self, sender: FlipperCLI, receiver: FlipperCLI) -> None:
        sender.nfc_exit()
        receiver.nfc_exit()
