# Contributing

## Bench reports (most wanted)
Run `flci soak --runs 20` on two Flippers and open a *Bench report* issue with the generated `reports/soak.md`, firmware versions and jig mode/spacing. These numbers replace the estimates in `docs/ROADMAP.md` and the RFC.

## New fixtures
1. Add `fixtures/<subsystem>/<id>.yaml` (plus a stimulus file if the kind needs one), or use `flci record`.
2. Use synthetic keys/IDs, or ones from devices you own. Never commit someone else's credentials.
3. Run `flci fixtures` and `pytest`. The loader validates every fixture and the offline orchestration tests exercise it.

## Code
- Firmware command strings go in `src/flci/cli.py` **only**, with the firmware source file that confirms them.
- Every serial read needs a timeout. Every error names the device, the command, and expected vs. got.
- Never make a hardware test pass without hardware. Skip, and say why.
- Before pushing, run `ruff check . && black --check . && mypy && pytest`.
