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
| Sub-GHz | 2nd Flipper `subghz tx` / `tx_from_file` | protocol, bits, key, frequency | strong | 6 |
| Infrared | 2nd Flipper `ir tx` | protocol, address, command | strong | 8 |
| iButton | 2nd Flipper `ikey emulate`, wired 1-Wire | key type, ID | strong | 2 |
| RFID 125 kHz | 2nd Flipper `rfid emulate` (ASK, FSK, PSK) | protocol, data | strong | 4 |
| GPIO | 2nd Flipper `gpio set`, wired | pin level | strong | 2 |
| NFC 13.56 MHz | 2nd Flipper `nfc emulate` (.nfc upload) | tag type, UID | **partial** | 1 |
| BadUSB | host captures HID via evdev | typed text | **partial**, operator-assisted | 1 |
| Screen / UI | none | none | manual, out of scope | none |

Every serial command is checked against the firmware source (file references are in [`src/flci/cli.py`](src/flci/cli.py)). **Nothing has been run on a physical bench yet.** Bench reports are the most useful contribution right now (see [Contributing](#contributing)).

## Features

- **Stock-firmware DUT**: driven only over the USB CLI; no test build, no SWD.
- **24 fixtures across 7 subsystems**, all YAML. Adding a case needs no code.
- **Preflight**: if the DUT firmware lacks a needed CLI command, or its region blocks a frequency, the test is *skipped with the reason* instead of reported as a decode failure (`FLCI_STRICT=1` turns those into failures).
- **Flakiness measurement**: `flci soak --runs 20` gives per-fixture pass rates, p50/p95 timings, every distinct decode, and the RFC evidence table.
- **Regression gate**: `flci compare base.xml candidate.xml` lists what broke, what got fixed and what lost coverage. CI compares every run against the last green `main`.
- **Battery logging**: each result records both devices' charge level, since low charge shortens RF/RFID range.
- **CI**: self-hosted bench workflow, DUT flashing via `update install`, JUnit check run plus a Markdown job summary.
- **Hardware**: parametric OpenSCAD jig (STL rendered in CI) and a wiring guide.

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
flci detect                                   # list Flippers, firmware, ports
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
| `FLCI_STRICT=1` | Treat missing CLI commands and region locks as failures instead of skips |

A failing round trip prints what was expected, every packet the DUT decoded, both firmware versions, and the tail of the DUT's raw output.

### The `flci` command

| Command | What it does |
|---|---|
| `flci detect` | List connected Flippers, firmware versions and assigned roles |
| `flci fixtures` | List and validate every fixture |
| `flci soak --runs 20 [--subsystem rfid] [--tag smoke]` | Repeat fixtures, write `reports/soak.{json,md}` |
| `flci report reports/junit.xml` | Markdown summary of a run (or `--soak reports/soak.json`) |
| `flci compare base.xml cand.xml` | Regressions between two runs; exit code 1 if any |
| `flci record from-sub/from-ir/live ...` | Create a fixture from a saved file or a live capture |
| `flci flash PACKAGE` | Flash the DUT from an update package and verify it |

Comparing two firmware builds on one bench:

```bash
flci flash old-update.tgz && pytest -m hardware --junitxml=reports/base.xml
flci flash new-update.tgz && pytest -m hardware --junitxml=reports/cand.xml
flci compare reports/base.xml reports/cand.xml
```

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
flci record from-sub  my_remote.sub --id gate_433
flci record from-ir   tv.ir --signal Power --id tv_power
flci record live rfid --port "$FLCI_DUT" --id my_fob
```

A broken fixture (bad YAML, unknown subsystem, missing stimulus file, duplicate id) stops the run with the file name and the reason.

## CI on a bench

[`.github/workflows/hil.yml`](.github/workflows/hil.yml) runs the suite on a **self-hosted** runner with both Flippers attached, optionally flashes the DUT first (`flci flash`, stock `update install`, no DFU), publishes JUnit as a **HIL results** check, writes a Markdown job summary, and **compares against the last green `main` run** to flag regressions. A manual run can also soak every fixture N times. It runs one job at a time (there's only one bench) and never runs fork PRs. Setup is in [docs/CI.md](docs/CI.md).

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

The most useful thing right now is a **bench report**: run `flci soak --runs 20` and [open an issue](https://github.com/Krishita17/flipper-loopback/issues/new?template=bench_report.md) with the generated `reports/soak.md`, your firmware versions and jig spacing. New fixtures and CLI fixes are welcome too (see [CONTRIBUTING.md](CONTRIBUTING.md)).

## License

MIT
