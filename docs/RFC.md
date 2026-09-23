# RFC: Automated hardware-in-the-loop (HIL) regression testing for firmware

> **Draft.** This will be posted to flipperdevices/flipperzero-firmware after the Phase 1 bench run produces real numbers. Check every claim below before posting.

## Summary
This RFC proposes a community-maintained hardware-in-the-loop test rig that automates the manual integration test cases in `documentation/testing/integration_tests.md`. It uses two devices on opposite sides of a physical air gap. One sends a known stimulus. The other runs the candidate firmware (stock CLI only), receives the stimulus and decodes it. A host runner checks that the decode matches a versioned fixture and writes JUnit XML for CI.

## Motivation
The integration test cases are run by hand today. The firmware roadmap requires changes to pass them and asks the community for help with regression testing. The physical-layer tests have no automation because radio/IR/NFC behavior can't be mocked in software. With a second physical device on the other side of the air gap, those tests can be scripted and still check the same thing.

## Proposal
- **Two-device loopback**: a counterpart (a second Flipper, or an ESP32/PN532) sends; the DUT decodes; the host checks the result. The DUT runs STOCK firmware and is driven only through the existing USB serial CLI, with no special test build.
- **Fixtures**: each case is a stimulus file (`.sub`/`.ir`/`.nfc`) plus a YAML file with the expected normalized decode, versioned next to the tests.
- **Output**: JUnit XML, shown as a PR status check from a self-hosted bench runner.
- **Jig**: a 3D-printed mount keeps the two devices at a fixed spacing so RF/IR results don't vary between runs.

## Scope
| Subsystem | Fit | Notes |
|-----------|-----|-------|
| Sub-GHz, Infrared, iButton, RFID 125kHz, GPIO/UART | Strong | wired or clean RF/IR round trip |
| NFC 13.56MHz, BadUSB | Partial | emulation/HID coverage is uneven |
| Screen / UI | Manual | needs camera + CV; out of scope for v1 |

## Non-goals
- Replacing manual UI and feel testing.
- Defeating any security system. The rig only checks decode correctness, on hardware the tester owns.

## Prior art
Existing serial harnesses drive a single Flipper to test their own tooling. As far as I know, none does a two-device physical loopback against the firmware's own integration test cases.

## Open questions for maintainers
1. Would you want to adopt or endorse an automated HIL suite upstream?
2. Is anyone already working on this?
3. Are the current `subghz` / `ir` / `ikey` CLI commands stable enough to build assertions on, or would you prefer a documented test-oriented CLI surface?
4. Would you accept a self-hosted runner integration, and under what constraints?

## Rollout
Phase 1 walking skeleton (one Sub-GHz round trip passing) → RF/IR/iButton → CI integration + jig → RFID and partial NFC/BadUSB. I'm happy to start with a proof-of-concept PR if there's interest.

Reference implementation: https://github.com/Krishita17/flipper-loopback
