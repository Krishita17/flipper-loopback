# Contributing

## Bench reports (most wanted)
Run `pytest -m hardware -v` on two Flippers and open a *Bench report* issue. Include firmware versions, jig mode/spacing, and pass/fail/flaky counts per subsystem. These numbers replace the estimates in `docs/ROADMAP.md` and the RFC.

## New fixtures
1. Add `fixtures/<subsystem>/<id>.yaml` (plus a stimulus file if the kind needs one), or use `scripts/record_fixture.py`.
2. Use synthetic keys/IDs, or ones from devices you own. Never commit someone else's credentials.
3. Run `pytest`. The loader validates every fixture and the offline orchestration tests exercise it.

## Code
- Firmware command strings go in `src/flci/cli.py` **only**, with the firmware source file that confirms them.
- Every serial read needs a timeout. Every error names the device, the command, and expected vs. got.
- Never make a hardware test pass without hardware. Skip, and say why.
- Before pushing, run `ruff check . && black --check . && mypy && pytest`.
