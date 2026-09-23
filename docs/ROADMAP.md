# Roadmap

All four phases are implemented in code. **None of it has been validated on a physical bench yet.** Items marked *bench* need real devices.

## Phase 1: Walking skeleton
- [x] Serial transport, timeouts on every read (`FlciTimeout`), Ctrl+C recovery
- [x] `FlipperCLI` with every command checked against firmware source
- [x] Explicit DUT/EMITTER roles; clean skip with 0 devices; JUnit XML
- [ ] *bench* First green Sub-GHz round trip on two devices

## Phase 2: Fixture format + RF/IR/iButton
- [x] `Subsystem` ABC with `ReceiverFirst` / `EmitterFirst` shapes
- [x] Sub-GHz: built-in Princeton TX **and** file TX (`.sub` upload + MD5 check + `tx_from_file`)
- [x] Infrared: `ir tx` → `ir rx` (NEC, NECext, Samsung32, RC5, SIRC fixtures)
- [x] iButton: `ikey emulate` → `ikey read` over wired 1-Wire (Dallas w/ valid CRC, Cyfral)
- [x] `scripts/record_fixture.py`: from `.sub`, from `.ir`, or live capture
- [x] Adding a fixture needs no code; corrupted fixtures fail loudly (unit-tested)
- [ ] *bench* Flakiness numbers per subsystem (fill in the table below)

## Phase 3: CI integration
- [x] `hil.yml`: self-hosted runner, bench mutex, fork-PR guard, JUnit → check run
- [x] `scripts/flash_dut.py`: flash DUT from an update package via `update install`
- [x] Reusable via `workflow_call` so a firmware fork can run this bench after its build
- [x] Parametric jig (`hardware/jig/flipper_jig.scad`), STL rendered in CI; wiring guide
- [ ] *bench* Test-print the jig; confirm run-to-run repeatability

## Phase 4: Expand + upstream
- [x] RFID 125 kHz: `rfid emulate` → `rfid read` (EM4100, H10301)
- [x] GPIO: wired level loopback (both levels)
- [x] NFC (**partial**): NTAG213 emulated from uploaded `.nfc`; asserts type + UID only
- [x] BadUSB (**partial**, operator-assisted): host HID capture via evdev
- [x] [RFC](RFC.md) ready to post
- [ ] *bench* Replace the estimates below with measured numbers, then post the RFC

## Coverage matrix

| Subsystem     | Counterpart                 | Assert on            | Fit     | Why not "strong" |
|---------------|-----------------------------|----------------------|---------|------------------|
| Sub-GHz       | 2nd Flipper                 | protocol+bits+key    | STRONG  | |
| Infrared      | 2nd Flipper IR TX           | protocol+addr+cmd    | STRONG  | |
| iButton       | 2nd Flipper, wired 1-Wire   | key type + ID        | STRONG  | |
| RFID 125kHz   | 2nd Flipper emulate         | protocol + data      | STRONG  | |
| GPIO          | 2nd Flipper, wired          | pin level            | STRONG  | |
| NFC 13.56MHz  | 2nd Flipper emulate         | type + UID           | PARTIAL | Only Ultralight/NTAG via `mfu info`; the CLI `scanner` reports protocol but not UID for other families, and emulation support differs by protocol |
| BadUSB        | Linux host (evdev)          | typed text           | PARTIAL | The Bad USB app switches USB from CDC to HID, dropping the CLI, so OK/Back must be pressed by a human |
| Screen / UI   | none                        | none                 | MANUAL  | Needs camera + CV; out of scope v1 |

## Known nondeterminism

| Where | What | Mitigation | Measured? |
|---|---|---|---|
| Sub-GHz RX start | gap between "ready" text and radio listening | `RX_SETTLE_S = 0.3` | no |
| Sub-GHz RX tail | last packet may still be decoding when TX returns | `TAIL_S = 0.5`; pass if any of N repeats matches | no |
| IR | angle/ambient light | jig `head_to_head`, 3 bursts | no |
| RFID/NFC/iButton read | reader may never see the key | one-shot read with hard timeout, then Ctrl+C | no |
| Serial port | qFlipper or a monitor holding the port | `detect_devices.py` reports the open error | n/a |
| Fixed sleeps | every wait is `FlipperCLI.settle()`, greppable | tune from bench data | no |

No retries are in place. If one gets added, it will be logged in the test output and justified in this table.
