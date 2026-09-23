"""BadUSB (PARTIAL, operator-assisted): DUT types a script, the host captures it.

Why partial: the stock Bad USB app switches the DUT's USB port from CDC serial to HID
(applications/main/bad_usb/bad_usb_app.c), so the CLI we drive it with disappears the
moment the app opens. The script only starts on an OK press and the app only exits on
Back, and neither can be sent once the CLI is gone. So a human presses OK, then Back.
The harness does everything else: upload, launch, HID capture, reconnect, assert.

Opt in with ``FLCI_OPERATOR=1`` on a Linux host with ``evdev``.
"""

from __future__ import annotations

import time

from flci.cli import FlipperCLI
from flci.errors import FlciError
from flci.hostio.hid_capture import capture_text, find_keyboard
from flci.schema import Fixture, NormalizedDecode
from flci.subsystems.base import Exchange, Subsystem, as_int

REMOTE_DIR = "/ext/badusb"


def remote_path(fixture: Fixture) -> str:
    return f"{REMOTE_DIR}/flci_{fixture.id}.txt"


def text_payload(text: str) -> str:
    return text.encode().hex().upper() or "00"


def _say(msg: str) -> None:
    print(f"\n>>> OPERATOR: {msg}", flush=True)


class BadUsb(Subsystem):
    name = "badusb"
    required_commands = ("loader", "storage")
    kinds = ("script",)

    def prepare(self, emitter: FlipperCLI, dut: FlipperCLI, fixture: Fixture) -> None:
        self.kind(fixture)
        if fixture.stimulus_path is None:
            raise ValueError(f"{fixture.id}: BadUSB fixtures need stimulus_path (.txt script)")
        dut.storage_upload(fixture.stimulus_path.read_bytes(), remote_path(fixture))

    def exchange(self, emitter: FlipperCLI, dut: FlipperCLI, fixture: Fixture) -> Exchange:
        s = fixture.stimulus
        vid, pid = (int(x, 16) for x in str(s["hid_id"]).split(":"))
        dut.loader_open("Bad USB", remote_path(fixture))
        dut.t.close()  # the CDC port is about to vanish
        kb = find_keyboard(vid, pid, timeout_s=as_int(s.get("enumerate_timeout_s", 30)))
        _say("press OK on the DUT to run the script")
        try:
            text = capture_text(kb, first_key_timeout_s=as_int(s.get("operator_timeout_s", 60)))
        finally:
            kb.close()
        _say("press BACK on the DUT (twice) to exit Bad USB")
        self._reconnect(dut, timeout_s=as_int(s.get("operator_timeout_s", 60)))
        decode = NormalizedDecode(
            subsystem="badusb",
            protocol="keystrokes",
            payload=text_payload(text),
            raw={"text": text},
        )
        return Exchange([decode], f"captured text: {text!r}")

    @staticmethod
    def _reconnect(dut: FlipperCLI, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                dut.t.open()
                return
            except (OSError, FlciError) as e:
                last = e
                time.sleep(1.0)
        raise FlciError(f"[{dut.name}] CLI did not come back after Bad USB: {last}")
