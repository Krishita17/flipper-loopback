# flipper-loopback

**Hardware-in-the-loop regression testing for Flipper Zero firmware.** Two Flippers, one air gap, a pass/fail result.

[![CI](https://github.com/Krishita17/flipper-loopback/actions/workflows/ci.yml/badge.svg)](https://github.com/Krishita17/flipper-loopback/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)
![bench](https://img.shields.io/badge/bench%20validation-wanted-orange)

Flipper's [integration test cases](https://github.com/flipperdevices/flipperzero-firmware/blob/dev/documentation/testing/integration_tests.md) are run by hand today. You can't mock radio in software, so this project uses a second physical device instead. One Flipper (the **emitter**) sends a known signal. The other (the **DUT**, running the candidate firmware *unmodified*) receives and decodes it. A Python/pytest runner checks the decode against a versioned fixture and writes JUnit XML that any CI system can read.

```
┌────────────────┐   USB serial CLI    ┌───────────────────────┐
│                │────────────────────▶│ EMITTER  (Flipper #2) │
│  HOST RUNNER   │                     └──────────┬────────────┘
│  Python+pytest │                                │ Sub-GHz / IR / RFID / NFC
│                │                  air gap / wire │ (spacing fixed by a jig)
│                │   USB serial CLI               ▼
│                │────────────────────▶┌───────────────────────┐
│                │◀──── decoded ───────│ DUT  (candidate fw)   │
└───────┬────────┘                     │ stock CLI, no test fw │
        │ JUnit XML                    └───────────────────────┘
        ▼
   PR status check (self-hosted bench runner)
```

## Coverage

| Subsystem | Counterpart | Asserts | Fit | Fixtures |
|---|---|---|---|---:|
| Sub-GHz | 2nd Flipper `subghz tx` / `tx_from_file` | protocol, bits, key, frequency | strong | 4 |
| Infrared | 2nd Flipper `ir tx` | protocol, address, command | strong | 5 |
| iButton | 2nd Flipper `ikey emulate`, wired 1-Wire | key type, ID | strong | 2 |
| RFID 125 kHz | 2nd Flipper `rfid emulate` | protocol, data | strong | 2 |
| GPIO | 2nd Flipper `gpio set`, wired | pin level | strong | 2 |
| NFC 13.56 MHz | 2nd Flipper `nfc emulate` (.nfc upload) | tag type, UID | **partial** | 1 |
| BadUSB | host captures HID via evdev | typed text | **partial**, operator-assisted | 1 |
| Screen / UI | none | none | manual, out of scope | none |

Every serial command is checked against the firmware source (file references are in [`src/flci/cli.py`](src/flci/cli.py)). **Nothing has been run on a physical bench yet.** Bench reports are the most useful contribution right now (see [Contributing](#contributing)).

## Install

```bash
git clone https://github.com/Krishita17/flipper-loopback
cd flipper-loopback
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'          # add ,badusb on Linux for HID capture
```

## Run

With **no hardware**, the parser and orchestration tests run and the hardware tests are *skipped* with a reason. A skip is never reported as a pass:

```bash
pytest
```

With **two Flippers** on USB (close qFlipper first, since it holds the serial port):

```bash
python scripts/detect_devices.py              # list Flippers, firmware, ports
export FLCI_DUT=<port or device name>         # flashed with the build under test
export FLCI_EMITTER=<port or device name>     # known-good counterpart
export FLCI_CAPABILITIES=subghz,infrared,rfid,nfc   # what your bench is set up for
pytest -m hardware -v                         # JUnit XML -> reports/junit.xml
```

| Variable | Meaning |
|---|---|
| `FLCI_DUT`, `FLCI_EMITTER` | Required. Port path or Flipper name. Roles are never guessed |
| `FLCI_CAPABILITIES` | Subsystems this bench supports. Default `subghz,infrared,rfid,nfc`; add `ibutton`, `gpio` once [wired](hardware/WIRING.md), and `badusb` for operator runs |
| `FLCI_TAGS` | Only run fixtures with these tags, e.g. `smoke` |
| `FLCI_OPERATOR=1` | Allow the operator-assisted BadUSB test (run with `pytest -s`) |

A failing round trip prints what was expected, every packet the DUT decoded, both firmware versions, and the tail of the DUT's raw output.

## Fixtures

Each test case is a YAML file in `fixtures/<subsystem>/`, sometimes with a stimulus file (`.sub`, `.nfc`, BadUSB `.txt`) next to it. Adding a case doesn't need any code changes:

```yaml
id: ir_nec_04_08
subsystem: infrared
stimulus: { kind: message, protocol: NEC, address: "0x04", command: "0x08", bursts: 3 }
expected: { subsystem: infrared, protocol: NEC, payload: "04-08" }
tags: [smoke]
```

You can also record fixtures from real captures or saved Flipper files:

```bash
python scripts/record_fixture.py from-sub  my_remote.sub --id gate_433
python scripts/record_fixture.py from-ir   tv.ir --signal Power --id tv_power
python scripts/record_fixture.py live rfid --port "$FLCI_DUT" --id my_fob
```

A broken fixture (bad YAML, unknown subsystem, missing stimulus file, duplicate id) stops the run with the file name and the reason.

## CI on a bench

[`.github/workflows/hil.yml`](.github/workflows/hil.yml) runs the suite on a **self-hosted** runner with both Flippers attached, optionally flashes the DUT first ([`scripts/flash_dut.py`](scripts/flash_dut.py), stock `update install`, no DFU), and publishes JUnit as a **HIL results** check. It runs one job at a time (there's only one bench) and never runs fork PRs. Setup is in [docs/CI.md](docs/CI.md).

## Hardware

- [hardware/jig/](hardware/jig/): parametric OpenSCAD jig (back-to-back for RF/RFID/NFC, head-to-head for IR). CI renders the STLs.
- [hardware/WIRING.md](hardware/WIRING.md): GPIO and iButton jumpers.

## Docs

[Architecture](docs/ARCHITECTURE.md) · [Roadmap & nondeterminism log](docs/ROADMAP.md) · [CI setup](docs/CI.md) · [Upstream RFC](docs/RFC.md)

## Safety

- Only use hardware and signals you own.
- Keep TX power low and use shielding or short distances so a bench rig doesn't transmit onto other people's devices or licensed bands. Follow your region's rules. The firmware enforces region locks and the harness treats a refused TX as an error. It never works around one.
- This project checks **decode correctness** of firmware. It is not a way to defeat any security system. Fixture keys and IDs are synthetic test values.

## Contributing

The most useful thing right now is a **bench report**: run `pytest -m hardware` and [open an issue](https://github.com/Krishita17/flipper-loopback/issues/new?template=bench_report.md) with your firmware versions, jig spacing and pass/fail/flake counts. New fixtures and CLI fixes are welcome too (see [CONTRIBUTING.md](CONTRIBUTING.md)).

## License

MIT
