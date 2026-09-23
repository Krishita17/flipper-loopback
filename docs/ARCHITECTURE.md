# Architecture

```
tests/test_<subsystem>_loopback.py   parametrized over fixtures/<subsystem>/*.yaml
        │  capability gate (FLCI_CAPABILITIES) → skip, never fake-pass
        ▼
flci.rig.Rig.round_trip(fixture)
        │  reset both → prepare (uploads) → exchange → cleanup (always)
        ▼
flci.subsystems.<name>        ReceiverFirst:  arm(DUT) → emit(emitter) → collect(DUT)
                              EmitterFirst:   start_emit → read(DUT, bounded) → stop_emit
                              custom:         GPIO (wired), BadUSB (host HID)
        ▼
flci.cli.FlipperCLI           every firmware command string + output parser
        ▼
flci.transport.SerialTransport   bytes, `>: ` prompt, Ctrl+C, run / run_bounded / stream / payload
        ▼
USB CDC serial → stock Flipper firmware CLI
```

| Module | Responsibility | Knows firmware strings? |
|---|---|---|
| `transport.py` | open/reset/run/stream/upload, prompt detection, ANSI stripping, timeouts | only the prompt |
| `cli.py` | typed verbs + pure parsers for every subsystem | **yes, only here** |
| `devices.py` | USB discovery (VID 0483 / PID 5740), explicit roles | no |
| `schema.py` | `NormalizedDecode`, `Fixture`, payload normalisation | no |
| `fixtures.py` | YAML loading + validation, loud errors | no |
| `subsystems/` | how each subsystem crosses the gap | no |
| `hostio/hid_capture.py` | host-side HID keyboard capture (BadUSB) | no |
| `rig.py` | orchestration + `RoundTripResult.explain()` | no |

## Payload normalisation

| Subsystem | `protocol` | `payload` |
|---|---|---|
| subghz | decoder name (`Princeton`, `CAME`) | key hex, padded to `bits` |
| infrared | `NEC`, `RC5`, ... | `<address>-<command>`, each unpadded hex |
| ibutton / rfid | `Dallas`, `EM4100`, ... | data bytes hex |
| nfc | tag type (`NTAG213`) | UID hex |
| gpio | `level` | `0` / `1` |
| badusb | `keystrokes` | UTF-8 hex of captured text |

## Design decisions

- **Stock DUT.** The DUT only ever receives CLI commands. It never runs a test build.
- **Explicit roles.** With two identical Flippers, guessing which is the DUT would silently test the wrong firmware.
- **Bench capabilities.** Wired and operator subsystems are opt-in, so an unwired bench skips those tests instead of failing them.
- **Upload with verification.** `storage write_chunk` appends, so the harness removes the file first and checks MD5 afterwards.
- **Match any packet.** Emitters repeat. A test passes if any decoded packet equals the expectation, and every packet is reported.
- **Offline tests are labelled.** `tests/unit/fake_flipper.py` simulates the CLI wire protocol to test orchestration. It never counts as a hardware result.
