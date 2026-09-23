# Roadmap

## Phases

### Phase 1: Walking skeleton (current)
- [x] Serial transport with timeouts on every read (`FlciTimeout`)
- [x] `FlipperCLI` with commands checked against firmware source
- [x] Device discovery + explicit DUT/EMITTER roles
- [x] `NormalizedDecode` / `Fixture` schema, YAML fixtures
- [x] One Sub-GHz fixture (Princeton 24-bit, 433.92 MHz)
- [x] Hardware tests skip cleanly with 0 devices; JUnit XML output
- [ ] Validate on a real 2-device bench and record timings/flakiness below

### Phase 2: Fixture format + RF/IR/iButton
File-based TX (`subghz tx_from_file`), Infrared (`ir tx` / `ir rx`), iButton (`ikey emulate` / `ikey read`), `scripts/record_fixture.py`.

### Phase 3: CI integration
`.github/workflows/hil.yml` on a self-hosted runner with USB passthrough; 3D-printed jig in `hardware/jig/`.

### Phase 4: Expand + upstream
RFID 125 kHz, partial NFC and BadUSB, RFC to the firmware maintainers ([draft](RFC.md)).

## Coverage matrix (estimates until bench numbers replace them)

| Subsystem     | Counterpart                | Assert on          | Fit     | Note                               |
|---------------|----------------------------|--------------------|---------|------------------------------------|
| Sub-GHz       | 2nd Flipper / ESP32+CC1101 | protocol + payload | STRONG  | Many protocols, text decode        |
| Infrared      | 2nd Flipper IR TX          | protocol + hex     | STRONG  | Jig removes angle flakiness        |
| iButton       | 2nd Flipper / wired 1-Wire | key type + ID      | STRONG  | Wired = zero RF noise              |
| RFID 125kHz   | 2nd Flipper emulate        | card type + data   | STRONG  | Read + emulate round trip          |
| NFC 13.56MHz  | Flipper emulate / PN532    | UID + parsed data  | PARTIAL | Emulation coverage uneven          |
| GPIO / UART   | Host or 2nd MCU            | pin state / bytes  | STRONG  | Fully wired, most deterministic    |
| BadUSB        | Host as HID target         | keystrokes         | PARTIAL | Host captures HID output           |
| Screen / UI   | none                       | pixels / feel      | MANUAL  | Needs camera + CV; out of scope v1 |

## Known nondeterminism

| Where | What | Mitigation |
|---|---|---|
| Sub-GHz RX start | Short delay between "ready" text and radio listening | `RX_SETTLE_S = 0.3` (to be measured) |
| Sub-GHz RX tail | Last packet may still be decoding when TX returns | `TAIL_S = 0.5`; pass if *any* packet of 10 repeats matches |
| Serial port | qFlipper or another monitor holding the port | `detect_devices.py` reports the open error |

No retries are in place yet. Any retry that gets added will be logged and justified here.
