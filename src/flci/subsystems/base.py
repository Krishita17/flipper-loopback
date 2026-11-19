"""Subsystem contract.

Every subsystem turns a fixture into one exchange between a **sender** and a **receiver**
and returns what the receiver decoded. The rig decides who is who: normally the emitter
sends and the DUT receives (``dut_rx``); with ``dut_tx`` the candidate firmware sends and
the known-good emitter decodes, which tests the firmware's transmit/emulate path.

Two shapes cover most subsystems:

- ``ReceiverFirst``: receiver listens, sender fires, receiver stops (Sub-GHz, Infrared).
- ``EmitterFirst``: sender keeps presenting a key/card, receiver does a one-shot read,
  sender stops (iButton, RFID, NFC).

Wired, instantaneous subsystems (GPIO) override ``exchange`` directly.

The stimulus kind ``silence`` sends nothing at all: the receiver listens (or reads) for
``listen_s`` seconds and the fixture expects *no* decode. That catches ghost decodes from
noise or a stuck decoder, which "did it decode the right thing" tests can't see.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from flci.cli import FlipperCLI
from flci.schema import Fixture, NormalizedDecode


@dataclass
class Exchange:
    decodes: list[NormalizedDecode]
    dut_output: str
    notes: list[str] = field(default_factory=list)


SILENCE = "silence"
DIRECTIONS = ("dut_rx", "dut_tx")


def as_int(v: Any) -> int:
    return int(v, 0) if isinstance(v, str) else int(v)


class Subsystem(ABC):
    name: str
    #: stimulus kinds this subsystem understands; "kind" defaults to the first one
    kinds: tuple[str, ...] = ()
    #: top-level CLI commands that must exist on the devices (checked before each test)
    required_commands: tuple[str, ...] = ()
    #: which way(s) this subsystem can be run; see module docstring
    directions: tuple[str, ...] = ("dut_rx", "dut_tx")

    def kind(self, fixture: Fixture) -> str:
        k = str(fixture.stimulus.get("kind", self.kinds[0]))
        if k not in self.kinds:
            raise ValueError(f"{self.name}: unknown stimulus kind {k!r}; know {self.kinds}")
        return k

    def is_silence(self, fixture: Fixture) -> bool:
        return self.kind(fixture) == SILENCE

    def prepare(  # noqa: B027
        self, sender: FlipperCLI, receiver: FlipperCLI, fixture: Fixture
    ) -> None:
        """One-time setup before the exchange, e.g. uploading a stimulus file."""

    def cleanup(self, sender: FlipperCLI, receiver: FlipperCLI) -> None:  # noqa: B027
        """Always runs after the exchange, pass or fail."""

    @abstractmethod
    def exchange(self, sender: FlipperCLI, receiver: FlipperCLI, fixture: Fixture) -> Exchange: ...


class ReceiverFirst(Subsystem):
    @abstractmethod
    def arm(self, receiver: FlipperCLI, fixture: Fixture) -> None: ...

    @abstractmethod
    def emit(self, sender: FlipperCLI, fixture: Fixture) -> None: ...

    @abstractmethod
    def collect(
        self, receiver: FlipperCLI, fixture: Fixture
    ) -> tuple[list[NormalizedDecode], str]: ...

    def exchange(self, sender: FlipperCLI, receiver: FlipperCLI, fixture: Fixture) -> Exchange:
        self.arm(receiver, fixture)
        try:
            if self.is_silence(fixture):
                receiver.settle(float(fixture.stimulus.get("listen_s", 3)))
            else:
                self.emit(sender, fixture)
        finally:
            # Always stop the receiver, even if TX blew up, so the next test starts clean.
            decodes, raw = self.collect(receiver, fixture)
        return Exchange(decodes, raw)


class EmitterFirst(Subsystem):
    @abstractmethod
    def start_emit(self, sender: FlipperCLI, fixture: Fixture) -> None: ...

    @abstractmethod
    def read(
        self, receiver: FlipperCLI, fixture: Fixture
    ) -> tuple[list[NormalizedDecode], str]: ...

    @abstractmethod
    def stop_emit(self, sender: FlipperCLI) -> None: ...

    def exchange(self, sender: FlipperCLI, receiver: FlipperCLI, fixture: Fixture) -> Exchange:
        if self.is_silence(fixture):
            return Exchange(*self.read(receiver, fixture))
        self.start_emit(sender, fixture)
        try:
            sender.settle(0.3)
            decodes, raw = self.read(receiver, fixture)
        finally:
            self.stop_emit(sender)
        return Exchange(decodes, raw)
