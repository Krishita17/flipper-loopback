"""Subsystem contract: arm the DUT, fire the emitter, collect what the DUT decoded."""

from __future__ import annotations

from abc import ABC, abstractmethod

from flci.cli import FlipperCLI
from flci.schema import Fixture, NormalizedDecode


class Subsystem(ABC):
    name: str

    @abstractmethod
    def arm(self, dut: FlipperCLI, fixture: Fixture) -> None:
        """Put the DUT into receive mode for this fixture."""

    @abstractmethod
    def emit(self, emitter: FlipperCLI, fixture: Fixture) -> None:
        """Make the emitter produce the fixture's stimulus. Blocks until done."""

    @abstractmethod
    def collect(self, dut: FlipperCLI, fixture: Fixture) -> tuple[list[NormalizedDecode], str]:
        """Stop receiving; return (decodes, raw DUT output)."""
