"""Command line entry point.

    satnogs-verify 15222675
    satnogs-verify 15222675 --log client.log --probe dns_probe.log --baseline baseline.json --json out.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import checks, report
from .logs import read_client_log


def _lines(path: str | None) -> list[str] | None:
    if not path:
        return None
    with open(path, errors="replace") as fh:
        return fh.readlines()


def main(argv: list[str] | None = None, source=None) -> int:
    ap = argparse.ArgumentParser(prog="satnogs-verify", description="Verify one SatNOGS observation end to end.")
    ap.add_argument("observation_id", type=int)
    ap.add_argument("--log", action="append", help="saved `docker logs -t` client log (repeatable)")
    ap.add_argument("--probe", help="connectivity probe log ('<ISO> host=ok container=ok' lines)")
    ap.add_argument("--baseline", help="baseline JSON with thresholds (see baseline.example.json)")
    ap.add_argument("--json", help="also write the result as JSON to this file")
    args = ap.parse_args(argv)

    baseline = json.loads(Path(args.baseline).read_text()) if args.baseline else {}
    log_lines = None
    if args.log:
        raw = [l for p in args.log for l in _lines(p)]
        log_lines = read_client_log(raw)
    if source is None:
        from .network import HttpSource
        source = HttpSource()

    result = checks.run(args.observation_id, source, baseline, log_lines, _lines(args.probe))
    sys.stdout.write(report.markdown(result))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2))
    return {"PASS": 0, "FAIL": 1, "BLOCKED": 2}[result["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())
