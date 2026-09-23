#!/usr/bin/env python3
"""Flash the DUT with a firmware update package over its serial CLI, then verify it.

Takes an unpacked update package directory (the ``f7-update-*`` folder from a firmware
build or ``*.tgz`` release, containing ``update.fuf``), uploads it to
``/ext/update/<name>/``, runs ``update install``, waits for the reboot and checks
``device_info`` again.

    flash_dut.py dist/f7-C/f7-update-local --port "$FLCI_DUT" [--expect-commit abc1234]
    flash_dut.py flipper-z-f7-update-1.4.0.tgz --port ...

Uses stock firmware features only; no DFU/SWD needed.
"""

from __future__ import annotations

import argparse
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from flci.cli import FlipperCLI
from flci.devices import resolve_roles
from flci.errors import FlciError
from flci.transport import SerialTransport


def _package_dir(path: Path, workdir: Path) -> Path:
    if path.is_dir():
        pkg = path
    else:
        with tarfile.open(path) as tar:
            tar.extractall(workdir, filter="data")
        pkg = workdir
    manifests = list(pkg.rglob("update.fuf"))
    if len(manifests) != 1:
        sys.exit(f"expected exactly one update.fuf under {path}, found {len(manifests)}")
    return manifests[0].parent


def _reopen(port: str, timeout_s: float) -> SerialTransport:
    deadline = time.monotonic() + timeout_s
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            t = SerialTransport(port, name=f"dut@{port}")
            t.open()
            return t
        except (OSError, FlciError) as e:
            last = e
            time.sleep(2.0)
    sys.exit(f"DUT did not come back on {port} within {timeout_s}s: {last}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("package", type=Path)
    p.add_argument("--port", help="DUT port (default: resolve FLCI_DUT)")
    p.add_argument("--expect-commit", help="firmware_commit prefix the DUT must report after")
    p.add_argument("--reboot-timeout", type=float, default=300.0)
    args = p.parse_args()

    port = args.port or resolve_roles()[1]
    with tempfile.TemporaryDirectory() as tmp:
        pkg = _package_dir(args.package, Path(tmp))
        remote = f"/ext/update/{pkg.name}"
        with SerialTransport(port, name=f"dut@{port}") as t:
            cli = FlipperCLI(t)
            before = cli.device_info()
            print(f"DUT before: {before.get('firmware_version')} {before.get('firmware_commit')}")
            files = sorted(f for f in pkg.rglob("*") if f.is_file())
            for n, f in enumerate(files, 1):
                rel = f.relative_to(pkg).as_posix()
                print(f"  [{n}/{len(files)}] {rel} ({f.stat().st_size} B)")
                cli.storage_upload(f.read_bytes(), f"{remote}/{rel}")
            print(cli.update_install(f"{remote}/update.fuf").strip())
        time.sleep(10)  # the port disappears during the update; don't catch the old one
        t = _reopen(port, args.reboot_timeout)
        try:
            after = FlipperCLI(t).device_info()
        finally:
            t.close()
    commit = after.get("firmware_commit", "")
    print(f"DUT after:  {after.get('firmware_version')} {commit}")
    want = (args.expect_commit or "").lower()
    got = commit.lower()
    if want and not (got and (got.startswith(want) or want.startswith(got))):
        sys.exit(f"DUT reports commit {commit!r}, expected {args.expect_commit!r}")


if __name__ == "__main__":
    main()
