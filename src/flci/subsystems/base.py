"""Subsystem contract.

Every subsystem turns a fixture into one exchange across the air gap (or wire) and returns
what the DUT decoded. Two shapes cover everything so far:

- ``ReceiverFirst``: the DUT listens, the emitter fires once, the DUT stops listening
  (Sub-GHz, Infrared).
- ``EmitterFirst``: the emitter keeps presenting a key/card, the DUT does a one-shot read,
  the emitter stops (iButton, RFID, NFC).

Wired, instantaneous subsystems (GPIO) override ``exchange`` directly.
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


def as_int(v: Any) -> int:
    return int(v, 0) if isinstance(v, str) else int(v)


class Subsystem(ABC):
    name: str
    #: stimulus kinds this subsystem understands; "kind" defaults to the first one
    kinds: tuple[str, ...] = ()

    def kind(self, fixture: Fixture) -> str:
        k = str(fixture.stimulus.get("kind", self.kinds[0]))
        if k not in self.kinds:
            raise ValueError(f"{self.name}: unknown stimulus kind {k!r}; know {self.kinds}")
        return k

    def prepare(self, emitter: FlipperCLI, dut: FlipperCLI, fixture: Fixture) -> None:  # noqa: B027
        """One-time setup before the exchange, e.g. uploading a stimulus file."""

    def cleanup(self, emitter: FlipperCLI, dut: FlipperCLI) -> None:  # noqa: B027
        """Always runs after the exchange, pass or fail."""

    @abstractmethod
    def exchange(self, emitter: FlipperCLI, dut: FlipperCLI, fixture: Fixture) -> Exchange: ...


class ReceiverFirst(Subsystem):
    @abstractmethod
    def arm(self, dut: FlipperCLI, fixture: Fixture) -> None: ...

    @abstractmethod
    def emit(self, emitter: FlipperCLI, fixture: Fixture) -> None: ...

    @abstractmethod
    def collect(self, dut: FlipperCLI, fixture: Fixture) -> tuple[list[NormalizedDecode], str]: ...

    def exchange(self, emitter: FlipperCLI, dut: FlipperCLI, fixture: Fixture) -> Exchange:
        self.arm(dut, fixture)
        try:
            self.emit(emitter, fixture)
        finally:
            # Always stop the DUT receiver, even if TX blew up, so the next test starts clean.
            decodes, raw = self.collect(dut, fixture)
        return Exchange(decodes, raw)


class EmitterFirst(Subsystem):
    @abstractmethod
    def start_emit(self, emitter: FlipperCLI, fixture: Fixture) -> None: ...

    @abstractmethod
    def read(self, dut: FlipperCLI, fixture: Fixture) -> tuple[list[NormalizedDecode], str]: ...

    @abstractmethod
    def stop_emit(self, emitter: FlipperCLI) -> None: ...

    def exchange(self, emitter: FlipperCLI, dut: FlipperCLI, fixture: Fixture) -> Exchange:
        self.start_emit(emitter, fixture)
        try:
            emitter.settle(0.3)
            decodes, raw = self.read(dut, fixture)
        finally:
            self.stop_emit(emitter)
        return Exchange(decodes, raw)
