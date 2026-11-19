"""``flci``: command-line entry point for the flipper-loopback harness.

flci detect                          list Flippers, firmware, roles
flci doctor [--probe]                check the bench is ready, say what to fix
flci soak --runs 20 [--subsystem X]  repeat fixtures, measure flakiness
flci report reports/hil-junit.xml    Markdown summary of a run (--html for a shareable page)
flci compare base.xml cand.xml       regressions between two runs (exit 1 if any)
flci record ...                      make a fixture from a file or live capture
flci flash PACKAGE                   flash the DUT from an update package
flci fixtures [--subsystem X]        list fixtures and validate them
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from flci import __version__


def _soak(argv: list[str]) -> int:
    from flci.devices import Device, DeviceRole, resolve_roles
    from flci.fixtures import load_fixtures
    from flci.rig import Rig
    from flci.soak import run_soak
    from flci.subsystems import REGISTRY

    p = argparse.ArgumentParser(prog="flci soak", description="Repeat fixtures N times.")
    p.add_argument("--runs", type=int, default=20)
    p.add_argument("--subsystem", action="append", choices=sorted(REGISTRY))
    p.add_argument("--tag", action="append", help="only fixtures with this tag")
    p.add_argument(
        "--direction",
        action="append",
        choices=["dut_rx", "dut_tx"],
        help="default: both (DUT receive and DUT transmit paths)",
    )
    p.add_argument("--json", type=Path, default=Path("reports/soak.json"))
    p.add_argument("--markdown", type=Path, default=Path("reports/soak.md"))
    a = p.parse_args(argv)

    caps = os.environ.get("FLCI_CAPABILITIES", "subghz,infrared,rfid,nfc").split(",")
    subs = a.subsystem or [s for s in sorted(REGISTRY) if s in caps and s != "badusb"]
    exclude = set() if a.tag and "environment" in a.tag else {"environment"}
    fixtures = [
        f
        for s in subs
        for f in load_fixtures(s, tags=set(a.tag) if a.tag else None)
        if not exclude & set(f.tags)
    ]
    emt_port, dut_port = resolve_roles()
    emitter, dut = Device(DeviceRole.EMITTER, emt_port), Device(DeviceRole.DUT, dut_port)
    emitter.open()
    dut.open()
    try:
        dirs = a.direction or ["dut_rx", "dut_tx"]
        report = run_soak(Rig(emitter, dut), fixtures, a.runs, directions=dirs)
    finally:
        emitter.close()
        dut.close()
    a.json.parent.mkdir(parents=True, exist_ok=True)
    a.json.write_text(report.to_json())
    md = report.markdown() + "\n\n#### RFC evidence rows\n\n" + report.evidence_table() + "\n"
    a.markdown.write_text(md)
    print(md)
    return 0 if all(f.pass_rate == 1.0 for f in report.fixtures if not f.skipped_reason) else 1


def _report(argv: list[str]) -> int:
    from flci.report import parse_junit, summary_markdown
    from flci.soak import SoakReport

    p = argparse.ArgumentParser(prog="flci report")
    p.add_argument("junit", type=Path, nargs="?")
    p.add_argument("--soak", type=Path, help="render a soak JSON instead")
    p.add_argument("--title", default="HIL results")
    p.add_argument("--html", type=Path, help="also write a self-contained HTML report here")
    a = p.parse_args(argv)
    from flci.html_report import junit_html, soak_html

    if a.soak:
        r = SoakReport.from_json(a.soak.read_text())
        print(r.markdown() + "\n\n" + r.evidence_table())
        if a.html:
            a.html.write_text(soak_html(r, "Soak report"))
        return 0
    if not a.junit:
        p.error("give a JUnit XML path or --soak")
    results = parse_junit(a.junit)
    print(summary_markdown(results, a.title))
    if a.html:
        a.html.write_text(junit_html(results, a.title))
    return 0


def _compare(argv: list[str]) -> int:
    from flci.report import compare, comparison_markdown, parse_junit

    p = argparse.ArgumentParser(prog="flci compare", description="Diff two HIL JUnit runs.")
    p.add_argument("baseline", type=Path)
    p.add_argument("candidate", type=Path)
    a = p.parse_args(argv)
    cand = parse_junit(a.candidate)
    c = compare(parse_junit(a.baseline), cand)
    print(comparison_markdown(c, cand))
    return 0 if c.ok else 1


def _fixtures(argv: list[str]) -> int:
    from flci.fixtures import load_fixtures
    from flci.subsystems import REGISTRY

    p = argparse.ArgumentParser(prog="flci fixtures")
    p.add_argument("--subsystem", action="append", choices=sorted(REGISTRY))
    a = p.parse_args(argv)
    total = 0
    for s in a.subsystem or sorted(REGISTRY):
        for f in load_fixtures(s):
            REGISTRY[s]().kind(f)
            total += 1
            print(f"{s:9} {f.id:32} {f.describe_expectation():48} [{', '.join(f.tags)}]")
    print(f"{total} fixtures OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {
        "detect": lambda rest: __import__("flci.tools.detect", fromlist=["main"]).main(rest),
        "doctor": lambda rest: __import__("flci.tools.doctor", fromlist=["main"]).main(rest),
        "record": lambda rest: __import__("flci.tools.record", fromlist=["main"]).main(rest) or 0,
        "flash": lambda rest: __import__("flci.tools.flash", fromlist=["main"]).main(rest) or 0,
        "soak": _soak,
        "report": _report,
        "compare": _compare,
        "fixtures": _fixtures,
    }
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--version":
        print(f"flipper-loopback {__version__}")
        return 0
    if argv[0] not in commands:
        print(f"unknown command {argv[0]!r}\n{__doc__}", file=sys.stderr)
        return 2
    return int(commands[argv[0]](argv[1:]))


if __name__ == "__main__":
    sys.exit(main())
