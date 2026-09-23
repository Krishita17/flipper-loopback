# Architecture

```
tests/test_subghz_loopback.py
        │  parametrized over fixtures/subghz/*.yaml
        ▼
flci.rig.Rig.round_trip(fixture)
        │  reset both → subsystem.arm(DUT) → subsystem.emit(emitter) → subsystem.collect(DUT)
        ▼
flci.subsystems.<name>          one class per subsystem (Subsystem ABC)
        ▼
flci.cli.FlipperCLI             every firmware command string + output parser
        ▼
flci.transport.SerialTransport  bytes, prompt detection, Ctrl+C, timeouts
        ▼
USB CDC serial → stock Flipper firmware CLI
```

| Module | Responsibility | Knows firmware strings? |
|---|---|---|
| `transport.py` | open/reset/run/stream, `>: ` prompt, ANSI stripping, timeouts | only the prompt |
| `cli.py` | typed verbs + parsers (`device_info`, `subghz tx/rx`) | **yes, only here** |
| `devices.py` | USB discovery (VID 0483 / PID 5740), explicit roles | no |
| `schema.py` | `NormalizedDecode`, `Fixture`, hex normalisation | no |
| `fixtures.py` | YAML loading + validation, loud errors | no |
| `subsystems/` | arm / emit / collect per subsystem | no |
| `rig.py` | orchestration + `RoundTripResult.explain()` | no |

## Design decisions

- **Stock DUT.** The DUT only ever receives CLI commands. It never runs a test build.
- **Explicit roles.** With two identical Flippers, guessing which is the DUT would silently test the wrong firmware. The runner skips until `FLCI_DUT` / `FLCI_EMITTER` are set.
- **Parameter stimulus in Phase 1.** `subghz tx` has Princeton 24-bit built in, so the emitter needs no SD card files. Fixtures also carry an equivalent `.sub` file for Phase 2's `tx_from_file`.
- **Match any packet.** The emitter repeats 10 times. The test passes if any decoded packet equals the expected decode, and every packet is reported.
