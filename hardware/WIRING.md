# Bench wiring

Air-gap subsystems (Sub-GHz, IR, RFID, NFC) need no wires between the devices, only USB to the host. Wired subsystems need the jumpers below. Always connect GND first.

Flipper Zero GPIO header (top edge), pin numbers as printed on the case:

| Pin | Signal | Used for |
|----:|--------|----------|
| 2 | PA7 | GPIO loopback |
| 8, 11, 18 | GND | common ground |
| 17 | 1W (iButton / 1-Wire) | iButton loopback |

## GPIO (`FLCI_CAPABILITIES` includes `gpio`)

```
EMITTER pin 2 (PA7) ──[ 1 kΩ ]── DUT pin 2 (PA7)
EMITTER pin 8 (GND) ──────────── DUT pin 8 (GND)
```

The 1 kΩ series resistor limits current if both sides are ever outputs at once. The harness always sets the DUT to input *before* making the emitter an output, and sets the emitter back to input afterwards. Only non-debug pins are allowed (`SAFE_GPIO_PINS` in `src/flci/cli.py`), and the harness refuses PA13/PA14 (SWD).

## iButton (`FLCI_CAPABILITIES` includes `ibutton`)

```
EMITTER pin 17 (1W)  ──────────── DUT pin 17 (1W)
EMITTER pin 18 (GND) ──────────── DUT pin 18 (GND)
```

Pin 17 is the same net as the iButton contact pad on the front, so this is equivalent to touching the two pads together, but it's repeatable.

## Never

- Connect 5V (pin 1) between devices.
- Wire anything to pins 10/12 (SWC/SIO debug).
- Leave the RF bench transmitting unattended without shielding or at more than the needed range.
