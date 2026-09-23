#!/usr/bin/env python3
"""Turn a real signal (or a saved Flipper file) into a new fixture: stimulus + expected YAML.

Two modes:

  From a saved file (offline, deterministic):
    record_fixture.py from-sub  path/to/remote.sub  --id garage_433
    record_fixture.py from-ir   path/to/tv.ir --signal Power --id tv_power

  Live capture on one Flipper (whatever it decodes first becomes the expectation):
    record_fixture.py live subghz  --port /dev/cu.usbmodemflip_X1 --frequency 433920000 --id x
    record_fixture.py live infrared --port ... --id x
    record_fixture.py live ibutton  --port ... --id x
    record_fixture.py live rfid     --port ... --id x

Review the YAML before committing it: a fixture is a claim about what correct looks like.
Only record signals from devices you own.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from flci.cli import FlipperCLI
from flci.fixtures import DEFAULT_ROOT, load_fixture
from flci.schema import NormalizedDecode, normalize_hex
from flci.transport import SerialTransport


def _kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line and not line.startswith("#"):
            k, v = line.split(":", 1)
            out.setdefault(k.strip(), v.strip())
    return out


def _write(fixture: dict[str, Any], root: Path, stimulus_file: Path | None = None) -> Path:
    sub = fixture["subsystem"]
    target_dir = root / sub
    target_dir.mkdir(parents=True, exist_ok=True)
    if stimulus_file is not None:
        dest = target_dir / f"{fixture['id']}{stimulus_file.suffix}"
        shutil.copyfile(stimulus_file, dest)
        fixture["stimulus_path"] = dest.name
    path = target_dir / f"{fixture['id']}.yaml"
    if path.exists():
        sys.exit(f"refusing to overwrite {path}")
    path.write_text(yaml.safe_dump(fixture, sort_keys=False))
    load_fixture(path)  # validate what we just wrote, loudly
    return path


def from_sub(args: argparse.Namespace) -> dict[str, Any]:
    kv = _kv(Path(args.file).read_text())
    if kv.get("Filetype") != "Flipper SubGhz Key File":
        sys.exit("only decoded key files are supported (RAW files have no expected decode)")
    bits = int(kv["Bit"])
    return {
        "id": args.id,
        "subsystem": "subghz",
        "description": args.description or f"Recorded from {Path(args.file).name}",
        "stimulus": {"kind": "file", "frequency_hz": int(kv["Frequency"]), "bursts": 3},
        "expected": {
            "subsystem": "subghz",
            "protocol": kv["Protocol"],
            "frequency_hz": int(kv["Frequency"]),
            "bits": bits,
            "payload": normalize_hex(kv["Key"], bits),
        },
        "tags": ["recorded"],
    }


def _le_hex(field: str) -> str:
    """Flipper .ir files store address/command as little-endian bytes: '04 00 00 00'."""
    return f"0x{int.from_bytes(bytes.fromhex(field.replace(' ', '')), 'little'):X}"


def from_ir(args: argparse.Namespace) -> dict[str, Any]:
    blocks = re.split(r"^#.*$", Path(args.file).read_text(), flags=re.M)
    for block in blocks:
        kv = _kv(block)
        if kv.get("name") == args.signal:
            break
    else:
        sys.exit(f"signal {args.signal!r} not found in {args.file}")
    if kv.get("type") != "parsed":
        sys.exit("only parsed IR signals are supported (raw has no protocol decode)")
    addr, cmd = _le_hex(kv["address"]), _le_hex(kv["command"])
    return {
        "id": args.id,
        "subsystem": "infrared",
        "description": args.description or f"{args.signal} from {Path(args.file).name}",
        "stimulus": {
            "kind": "message",
            "protocol": kv["protocol"],
            "address": addr,
            "command": cmd,
            "bursts": 3,
        },
        "expected": {
            "subsystem": "infrared",
            "protocol": kv["protocol"],
            "payload": f"{normalize_hex(addr)}-{normalize_hex(cmd)}",
        },
        "tags": ["recorded"],
    }


def _live_decode(args: argparse.Namespace) -> NormalizedDecode:
    with SerialTransport(args.port) as t:
        cli = FlipperCLI(t)
        print(f"listening on {args.port} for {args.seconds}s - trigger the signal now")
        if args.subsystem == "subghz":
            cli.subghz_rx_start(args.frequency)
            time.sleep(args.seconds)
            decodes, _ = cli.subghz_rx_stop(args.frequency)
        elif args.subsystem == "infrared":
            cli.ir_rx_start()
            time.sleep(args.seconds)
            decodes, _ = cli.ir_rx_stop()
        elif args.subsystem == "ibutton":
            decodes, _ = cli.ibutton_read(timeout_s=args.seconds)
        else:
            decodes, _ = cli.rfid_read(timeout_s=args.seconds)
    if not decodes:
        sys.exit("nothing decoded; nothing written")
    distinct = {d.short() for d in decodes}
    if len(distinct) > 1:
        print(f"warning: {len(distinct)} different decodes seen, using the first: {distinct}")
    return decodes[0]


def live(args: argparse.Namespace) -> dict[str, Any]:
    d = _live_decode(args)
    expected = d.model_dump(exclude={"raw"}, exclude_none=True)
    if args.subsystem == "subghz":
        if d.protocol != "Princeton" or d.bits != 24:
            sys.exit(
                f"decoded {d.short()}; only Princeton 24-bit can be re-sent without a key file. "
                "Save the signal on the Flipper and use `from-sub` instead."
            )
        stimulus = {
            "kind": "princeton_tx",
            "key": f"0x{d.payload}",
            "frequency_hz": args.frequency,
            "te_us": 400,
            "repeat": 10,
        }
    elif args.subsystem == "infrared":
        a, c = d.payload.split("-")
        stimulus = {
            "kind": "message",
            "protocol": d.protocol,
            "address": f"0x{a}",
            "command": f"0x{c}",
            "bursts": 3,
        }
    elif args.subsystem == "ibutton":
        stimulus = {"kind": "emulate", "key_type": d.protocol, "key_data": d.payload}
    else:
        stimulus = {"kind": "emulate", "protocol": d.protocol, "data": d.payload}
    return {
        "id": args.id,
        "subsystem": args.subsystem,
        "description": args.description or f"Live capture: {d.short()}",
        "stimulus": stimulus,
        "expected": expected,
        "tags": ["recorded"],
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    sp = p.add_subparsers(dest="mode", required=True)

    s = sp.add_parser("from-sub")
    s.add_argument("file")
    s.add_argument("--id", required=True)
    s.add_argument("--description")

    i = sp.add_parser("from-ir")
    i.add_argument("file")
    i.add_argument("--signal", required=True)
    i.add_argument("--id", required=True)
    i.add_argument("--description")

    lv = sp.add_parser("live")
    lv.add_argument("subsystem", choices=["subghz", "infrared", "ibutton", "rfid"])
    lv.add_argument("--port", required=True)
    lv.add_argument("--id", required=True)
    lv.add_argument("--frequency", type=int, default=433920000)
    lv.add_argument("--seconds", type=float, default=10.0)
    lv.add_argument("--description")

    args = p.parse_args()
    if args.mode == "from-sub":
        path = _write(from_sub(args), args.root, Path(args.file))
    elif args.mode == "from-ir":
        path = _write(from_ir(args), args.root)
    else:
        path = _write(live(args), args.root)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
