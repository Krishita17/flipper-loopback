# Running the HIL suite in CI

The hardware suite needs a machine with both Flippers plugged in, so it runs on a **self-hosted GitHub Actions runner**. Hosted runners run only lint, types, the offline tests and the jig render (`ci.yml`).

## 1. Bench machine

A Raspberry Pi 4/5, a mini PC, or a laptop running Linux. macOS also works except for BadUSB capture.

```bash
# Linux: let the runner user open the serial ports (and read HID for BadUSB)
sudo usermod -aG dialout,input "$USER"
# Stable names instead of /dev/ttyACM0/1 swapping on reboot:
ls -l /dev/serial/by-id/   # use these paths for FLCI_DUT / FLCI_EMITTER
```

Close or uninstall qFlipper on this machine, because it grabs the serial port.

## 2. Register the runner

Repo → Settings → Actions → Runners → *New self-hosted runner*. Follow the steps, then add the label **`flipper-hil`**. Run it as a service.

## 3. Repository variables

Settings → Secrets and variables → Actions → **Variables**:

| Variable | Example |
|---|---|
| `FLCI_DUT` | `/dev/serial/by-id/usb-Flipper_Devices_Inc._Flipper_Dut1_flip_Dut1-if00` |
| `FLCI_EMITTER` | `/dev/serial/by-id/usb-Flipper_Devices_Inc._Flipper_Emt2_flip_Emt2-if00` |
| `FLCI_CAPABILITIES` | `subghz,infrared,rfid,nfc,gpio,ibutton` |

## 4. Triggers

The job is skipped entirely until `FLCI_DUT` is set, so a repo without a bench never has a job stuck waiting for a runner.

| Event | Runs? |
|---|---|
| push to `main` | yes |
| PR from this repo **with label `hil`** | yes |
| PR from a fork | **no**: a self-hosted runner would execute untrusted code on your machine. Review the PR, then run it with *workflow_dispatch* |
| workflow_dispatch | yes; optional `firmware_url` (update `.tgz`) to flash the DUT first, optional `tags` |
| workflow_call | yes; lets a firmware repo pass a built `f7-update-*` artifact |

Only one job uses the bench at a time (`concurrency: flipper-hil-bench`).

## 5. Calling from a firmware fork

```yaml
jobs:
  build:
    # ... build and upload the update package as artifact "fw-update"
  hil:
    needs: build
    uses: Krishita17/flipper-loopback/.github/workflows/hil.yml@main
    with:
      firmware_artifact: fw-update
      tags: smoke
```

The runner must be registered where the calling workflow can reach it (same repo or org).

## Regression gate

Every run that isn't on `main` downloads the `hil-junit` artifact from the latest successful HIL run on `main` and runs `flci compare` against it. The job summary lists regressions (passed on main, fails now), fixes, and cases that lost coverage (passed on main, skipped now). The first run on `main` sets the baseline.

## Soak runs

*Actions → HIL → Run workflow* with `soak_runs: 20` also repeats every fixture 20 times after the normal suite. The pass-rate table (and the RFC evidence rows) appear in the job summary and in `reports/soak.{json,md}`.

## Results

JUnit XML is published as a **HIL results** check run with a per-fixture summary, plus a Markdown job summary from `flci report`. Each test case records the DUT/emitter firmware versions and the decodes the DUT saw (`record_property`), and the raw XML is uploaded as an artifact.
