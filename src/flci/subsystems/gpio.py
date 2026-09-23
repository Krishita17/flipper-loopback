"""GPIO: emitter drives a pin; DUT reads the wired pin. Fully deterministic.

Wiring (hardware/WIRING.md): emitter ``out_pin`` -> 1 kOhm -> DUT ``in_pin``; GND-GND.
Only non-debug header pins are allowed (``SAFE_GPIO_PINS`` in cli.py).
"""

from __future__ import annotations

from flci.cli import FlipperCLI
from flci.schema import Fixture
from flci.subsystems.base import Exchange, Subsystem, as_int


class Gpio(Subsystem):
    name = "gpio"
    kinds = ("level",)

    def exchange(self, emitter: FlipperCLI, dut: FlipperCLI, fixture: Fixture) -> Exchange:
        self.kind(fixture)
        s = fixture.stimulus
        out_pin, in_pin = str(s["out_pin"]), str(s.get("in_pin", s["out_pin"]))
        dut.gpio_mode(in_pin, output=False)  # DUT first: never two outputs fighting
        emitter.gpio_mode(out_pin, output=True)
        try:
            emitter.gpio_set(out_pin, as_int(s["level"]))
            emitter.settle(0.02)
            decodes, raw = dut.gpio_read(in_pin)
        finally:
            emitter.gpio_mode(out_pin, output=False)  # leave the bus high-impedance
        return Exchange(decodes, raw)
