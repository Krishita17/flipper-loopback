# flipper-loopback

**Hardware-in-the-loop regression testing for Flipper Zero firmware.** Two Flippers, one air gap, a pass/fail result.

[![CI](https://github.com/Krishita17/flipper-loopback/actions/workflows/ci.yml/badge.svg)](https://github.com/Krishita17/flipper-loopback/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![status](https://img.shields.io/badge/status-phase%201%20walking%20skeleton-orange)

Flipper's [integration test cases](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/documentation/testing/integration_tests.md) are run by hand today. You can't mock radio in software, so this project uses a second physical device instead. One Flipper (the **emitter**) sends a known signal. The other (the **DUT**, running the candidate firmware *unmodified*) receives and decodes it. A Python/pytest runner checks the decode against a versioned fixture and writes JUnit XML that any CI system can read.

```
┌────────────────┐   USB serial CLI    ┌───────────────────────┐
│                │────────────────────▶│ EMITTER  (Flipper #2) │
│  HOST RUNNER   │                     └──────────┬────────────┘
│  Python+pytest │                                │ Sub-GHz / IR / RFID ...
│                │                        air gap │ (fixed by a jig)
│                │   USB serial CLI               ▼
│                │────────────────────▶┌───────────────────────┐
│                │◀──── decoded ───────│ DUT  (candidate fw)   │
└───────┬────────┘                     │ stock CLI, no test fw │
        │ JUnit XML                    └───────────────────────┘
        ▼
   CI / PR check
```

## Status

| Phase | What | State |
|---|---|---|
| 1 | Walking skeleton: one Sub-GHz round trip, clean skip with no hardware | **done** (needs bench validation) |
| 2 | Fixture format + Sub-GHz / Infrared / iButton suites, `record_fixture.py` | planned |
| 3 | Self-hosted HIL runner, PR status checks, 3D-printed jig | planned |
| 4 | RFID 125 kHz, partial NFC / BadUSB, upstream RFC | planned |

See [docs/ROADMAP.md](docs/ROADMAP.md) for the coverage matrix and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the data flow.

## Install

```bash
git clone https://github.com/Krishita17/flipper-loopback
cd flipper-loopback
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
```

## Run

With **no hardware** attached, the hardware tests are *skipped* with a reason. They never report a pass:

```bash
pytest
```

With **two Flippers** on USB (close qFlipper first, since it holds the serial port):

```bash
python scripts/detect_devices.py            # list Flippers, firmware, ports
export FLCI_DUT=<port or device name>       # the one flashed with the build under test
export FLCI_EMITTER=<port or device name>   # the known-good counterpart
pytest -m hardware -v                       # JUnit XML -> reports/junit.xml
```

A failing round trip prints what was expected, every packet the DUT actually decoded, both firmware versions, and the tail of the DUT's raw serial output.

## How a test works

1. Both devices are reset to a clean CLI prompt (Ctrl+C, drain, re-prompt).
2. DUT: `subghz rx 433920000 0` waits until it prints `Press CTRL+C to stop`.
3. Emitter: `subghz tx 123456 433920000 400 10 0` transmits Princeton 24-bit and returns.
4. DUT: Ctrl+C, then the output is parsed (`Princeton 24bit / Key:0x00123456`) into a `NormalizedDecode`.
5. Pass if any decoded packet matches `fixtures/subghz/princeton_433_92.yaml`.

Every command string the harness uses is in [`src/flci/cli.py`](src/flci/cli.py), and each one was checked against the firmware source (file references are in that module). If the firmware CLI changes, that is the only file to edit.

## Adding a fixture

Put a YAML file in `fixtures/<subsystem>/`. You don't need to change any code:

```yaml
id: princeton_315
subsystem: subghz
stimulus: { kind: princeton_tx, key: "0xABCDEF", frequency_hz: 315000000, te_us: 400, repeat: 10 }
expected: { subsystem: subghz, protocol: Princeton, bits: 24, payload: "ABCDEF", frequency_hz: 315000000 }
tags: [regression]
```

## Safety

- Only use hardware and signals you own.
- Keep TX power low and use shielding or short distances so a bench rig doesn't transmit onto other people's devices or licensed bands. Follow your region's rules. The firmware enforces region locks and the harness treats a refused TX as an error. It never works around one.
- This project checks **decode correctness** of firmware. It is not a way to defeat any security system.

## Contributing

Bench reports are the most useful contribution right now: your firmware versions, distance and pass/fail counts. Please open an issue.

## License

MIT
