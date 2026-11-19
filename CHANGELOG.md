# Changelog

## 0.6.0
- Both directions: every case runs as `@dut_rx` (DUT decodes) and `@dut_tx` (DUT transmits, the known-good emitter decodes); `FLCI_DIRECTIONS` / `--direction` narrow it
- Negative fixtures: stimulus kind `silence` + `expect_no_decode: true` (IR, RFID, iButton, NFC; Sub-GHz as an opt-in `environment` check)
- Timing budgets: `max_duration_s` per fixture; soak suggests budgets from p95
- `flci doctor [--probe]`: bench diagnostics with concrete fixes; runs first in the HIL workflow
- `flci report --html`: self-contained HTML report for runs and soaks, uploaded by CI
- Dependabot, pre-commit config, and a tag-triggered release workflow
- `FLCI_EXCLUDE_TAGS` (default `environment`)

## 0.5.0
- `flci` command: `detect`, `fixtures`, `soak`, `report`, `compare`, `record`, `flash` (the old `scripts/*.py` still work as shims)
- Soak mode for flakiness: pass rate, p50/p95, distinct decodes, RFC evidence rows
- Regression comparison between runs; the HIL workflow compares against the last green `main` run and writes a job summary
- Preflight: missing CLI commands (via `help`) and region-locked frequencies become skips with a reason (`FLCI_STRICT=1` makes them failures)
- Battery level recorded with every result
- New fixtures: Nice FLO, Linear 300 MHz (decoder display quirk), RC6, Pioneer, RCA, Indala26 (PSK), IoProxXSF
- Fix: comparison summary no longer crashes on an empty failure message

## 0.4.0
- Phases 2–4: Infrared, iButton, RFID, GPIO, partial NFC and BadUSB; file-based Sub-GHz TX; `record_fixture`, `flash_dut`; self-hosted HIL workflow; OpenSCAD jig; RFC draft

## 0.1.0
- Phase 1 walking skeleton: Sub-GHz round trip, clean skip without hardware
