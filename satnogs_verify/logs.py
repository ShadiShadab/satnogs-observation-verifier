"""Read saved client logs (`docker logs -t`) and connectivity-probe logs."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .timeutil import parse_iso

_TS = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+(.*)$")


@dataclass
class LogLine:
    ts: datetime
    text: str


def read_client_log(lines: Iterable[str]) -> list[LogLine]:
    """Keep timestamped lines only, de-duplicated (overlapping saved logs are common), sorted."""
    seen, out = set(), []
    for raw in lines:
        m = _TS.match(raw.rstrip("\n"))
        if not m or raw in seen:
            continue
        seen.add(raw)
        out.append(LogLine(parse_iso(m.group(1)), m.group(2)))
    return sorted(out, key=lambda l: l.ts)


def window(lines: list[LogLine], start: datetime, end: datetime) -> list[LogLine]:
    return [l for l in lines if start <= l.ts <= end]


def probe_failures(lines: Iterable[str], start: datetime, end: datetime) -> list[str]:
    """Probe format: '<ISO time> host=ok|FAIL container=ok|FAIL'. Return FAIL samples in the window."""
    bad = []
    for raw in lines:
        parts = raw.split()
        if not parts:
            continue
        try:
            ts = parse_iso(parts[0])
        except ValueError:
            continue
        if start <= ts <= end and "FAIL" in raw:
            bad.append(raw.strip())
    return bad
