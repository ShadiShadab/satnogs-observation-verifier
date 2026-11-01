"""The checks, mapped to the release-regression items they automate.

Item numbers follow the 11-item regression suite:
4 client retrieves job · 5 SDR initialises · 6 flowgraph executes · 7 artifact generated ·
8 upload succeeds · 9 observation appears and reviews.

Thresholds come only from the baseline file. Without a threshold the raw value is
reported as INFO; no tolerance is invented.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from .logs import LogLine, window
from .model import BLOCKED, FAIL, INFO, NOT_EVALUATED, PASS, Check
from .network import HeadResult, Source
from .timeutil import parse_http_date, parse_iso

DEFAULT_PATTERNS = {
    "start_anchor": r"ZMQ .*SUB Connecting",
    "sdr_open": r"Opening Generic RTL2832U",
    "sdr_stream": r"Using format CF32",
    "sdr_required": [r"Opening Generic RTL2832U", r"Using format CF32"],
    "flowgraph_end": r"netrigctl_close: done",
    "error": r"\bERROR\b|Traceback",
    "error_ignore": r"Fetching jobs|Max retries",
}


def triage(obs: dict) -> str:
    """Read the status + artifacts tuple (method CM-06 from station QA)."""
    status = obs.get("status")
    has_art = bool(obs.get("payload") or obs.get("waterfall"))
    meta = bool(obs.get("client_metadata"))
    if status == "future":
        return "not finished yet, or checked too early"
    if status == "unknown":
        return "completed, not yet vetted" if has_art else "interrupted or never executed (no artifacts)"
    if status == "failed":
        if has_art:
            return "failed, partial data preserved"
        return "execution-stage failure" if meta else "retrieval-stage failure"
    if status in ("good", "bad"):
        return f"vetted {status}"
    return f"unrecognised status {status!r}"


def _range(value: float, rng: list | None) -> str | None:
    if not rng:
        return None
    lo, hi = rng
    return PASS if lo <= value <= hi else FAIL


def check_record(obs: dict | None, obs_id: int, now: datetime) -> list[Check]:
    if obs is None:
        return [Check("9", "Observation record exists", FAIL, f"observation {obs_id} not found (HTTP 404)", "API")]
    end = parse_iso(obs["end"])
    finished = end < now and obs.get("status") != "future"
    return [
        Check("9", "Observation record exists", PASS, f"station {obs['ground_station']}, "
              f"{obs['start']} → {obs['end']}", "API"),
        Check("9", "Observation finished", PASS if finished else FAIL,
              f"status {obs.get('status')!r}; {triage(obs)}", "API"),
    ]


def check_artifact(obs: dict, key: str, label: str, src: Source, baseline: dict) -> tuple[Check, HeadResult | None]:
    url = obs.get(key)
    if not url:
        return Check("7", f"{label} present", FAIL, f"`{key}` is null", "API"), None
    h = src.head(url)
    if h.status != 200 or not h.size:
        return Check("7", f"{label} reachable", FAIL, f"HEAD {h.status}, size {h.size}", "HTTP"), h
    detail = f"HTTP 200, {h.size:,} bytes"
    status = INFO
    if key == "waterfall":
        status = _range(h.size, baseline.get("waterfall_bytes")) or INFO
    else:
        mode = _mode(obs)
        per_mode = baseline.get("audio_bytes_per_second", {}).get(mode or "")
        dur = (parse_iso(obs["end"]) - parse_iso(obs["start"])).total_seconds()
        if dur > 0:
            bps = h.size / dur
            detail += f", {bps:,.0f} B/s over {dur:.0f} s (mode {mode or 'unknown'})"
            status = _range(bps, per_mode) or INFO
    if status == INFO:
        detail += "; no baseline for this value"
    return Check("7", f"{label} generated", status, detail, "HTTP"), h


def _mode(obs: dict) -> str | None:
    try:
        return json.loads(obs.get("client_metadata") or "{}")["radio"]["parameters"]["mode"]
    except (ValueError, KeyError, TypeError):
        return obs.get("transmitter_mode")


def check_upload(obs: dict, heads: list[HeadResult], baseline: dict) -> Check:
    stamps = [parse_http_date(h.last_modified) for h in heads if h and h.status == 200 and h.last_modified]
    if not stamps:
        return Check("8", "Upload latency", NOT_EVALUATED, "no Last-Modified header on artifacts", "HTTP")
    latest = max(stamps)
    minutes = (latest - parse_iso(obs["end"])).total_seconds() / 60
    limit = baseline.get("upload_max_minutes")
    detail = f"last artifact uploaded {minutes:.1f} min after end ({latest:%Y-%m-%d %H:%M:%S} UTC)"
    if limit is None:
        return Check("8", "Upload latency", INFO, detail + "; no baseline", "HTTP")
    return Check("8", "Upload latency", PASS if 0 <= minutes <= limit else FAIL, detail + f"; limit {limit} min", "HTTP")


def check_metadata(obs: dict) -> Check:
    """Pass-end metadata. Empty values after a successful upload were a defect candidate (D1)."""
    version = obs.get("client_version")
    raw = obs.get("client_metadata")
    try:
        params = json.loads(raw)["radio"]["parameters"] if raw else None
    except (ValueError, KeyError, TypeError):
        params = None
    if version and params:
        return Check("9", "Client metadata written", PASS,
                     f"client {version}, mode {params.get('mode')}, gain {params.get('gain')}", "API")
    missing = [n for n, v in (("client_version", version), ("client_metadata.radio.parameters", params)) if not v]
    return Check("9", "Client metadata written", FAIL, "missing: " + ", ".join(missing), "API")


def check_review(obs: dict) -> list[Check]:
    demod = obs.get("demoddata") or []
    return [
        Check("9", "Review status", INFO, triage(obs) +
              (f", certainty {obs['status_certainty']}" if obs.get("status_certainty") is not None else ""), "API"),
        Check("9", "Demodulated data", INFO, f"{len(demod)} file(s)", "API"),
    ]


def check_logs(obs: dict, lines: list[LogLine] | None, baseline: dict) -> list[Check]:
    names = ["Client start offset", "SDR initialised", "Flowgraph ran to end", "No errors after pass"]
    items = ["4", "5", "6", "8"]
    if lines is None:
        return [Check(i, n, NOT_EVALUATED, "no client log supplied", "LOG") for i, n in zip(items, names)]
    p = {**DEFAULT_PATTERNS, **baseline.get("patterns", {})}
    start, end = parse_iso(obs["start"]), parse_iso(obs["end"])
    w = window(lines, start - timedelta(minutes=2), end + timedelta(minutes=2))
    if not w:
        return [Check(i, n, NOT_EVALUATED, "log does not cover the observation window", "LOG")
                for i, n in zip(items, names)]
    out = []

    # Item 4: first start anchor vs scheduled start
    anchor = next((l for l in w if l.ts >= start - timedelta(seconds=60) and re.search(p["start_anchor"], l.text)), None)
    if anchor is None:
        out.append(Check("4", names[0], FAIL, "start anchor line not found", "LOG"))
    else:
        d = (anchor.ts - start).total_seconds()
        lim = baseline.get("start_offset_max_s")
        st = INFO if lim is None else (PASS if -1 <= d <= lim else FAIL)
        out.append(Check("4", names[0], st, f"{d:+.2f} s after scheduled start" + ("" if lim is None else f"; limit {lim} s"), "LOG"))

    # Item 5: required SDR lines and open → stream gap
    missing = [pat for pat in p["sdr_required"] if not any(re.search(pat, l.text) for l in w)]
    opened = next((l for l in w if re.search(p["sdr_open"], l.text)), None)
    stream = next((l for l in w if opened and l.ts >= opened.ts and re.search(p["sdr_stream"], l.text)), None)
    if missing:
        out.append(Check("5", names[1], FAIL, "missing: " + ", ".join(missing), "LOG"))
    else:
        gap = (stream.ts - opened.ts).total_seconds() if stream else float("nan")
        lim = baseline.get("sdr_open_to_stream_max_s")
        st = INFO if lim is None else (PASS if gap <= lim else FAIL)
        out.append(Check("5", names[1], st, f"open → stream {gap:.2f} s" + ("" if lim is None else f"; limit {lim} s"), "LOG"))

    # Item 6: flowgraph closed near the scheduled end
    tol = baseline.get("flowgraph_end_tolerance_s")
    closes = [l for l in w if re.search(p["flowgraph_end"], l.text)]
    if not closes:
        out.append(Check("6", names[2], FAIL, "no end-of-flowgraph line in the window", "LOG"))
    else:
        d = (closes[-1].ts - end).total_seconds()
        st = INFO if tol is None else (PASS if abs(d) <= tol else FAIL)
        out.append(Check("6", names[2], st, f"{len(closes)} close line(s), last {d:+.1f} s from scheduled end", "LOG"))

    # Item 8: success is silent, so any error after the pass is a failure
    after = window(lines, end, end + timedelta(minutes=baseline.get("upload_max_minutes") or 10))
    errs = [l for l in after if re.search(p["error"], l.text) and not re.search(p["error_ignore"], l.text)]
    out.append(Check("8", names[3], FAIL if errs else PASS,
                     f"{len(errs)} error line(s)" + (f"; first: {errs[0].text[:120]}" if errs else ""), "LOG"))
    return out


def apply_probe(checks: list[Check], failures: list[str] | None) -> tuple[list[Check], Check]:
    """Validity rule: any probe FAIL in the window makes failed results BLOCKED, never FAIL."""
    if failures is None:
        return checks, Check("-", "Connectivity probe", NOT_EVALUATED, "no probe log supplied", "PROBE")
    if not failures:
        return checks, Check("-", "Connectivity probe", PASS, "no FAIL samples in the window", "PROBE")
    for c in checks:
        if c.status == FAIL:
            c.status, c.detail = BLOCKED, c.detail + " (window invalid: probe failures)"
    return checks, Check("-", "Connectivity probe", BLOCKED, f"{len(failures)} FAIL sample(s); first: {failures[0]}", "PROBE")


def verdict(checks: list[Check], probe: Check) -> str:
    if probe.status == BLOCKED:
        return BLOCKED
    if any(c.status == FAIL for c in checks):
        return FAIL
    return PASS


def run(obs_id: int, src: Source, baseline: dict, log_lines: list[LogLine] | None = None,
        probe_lines: list[str] | None = None, now: datetime | None = None) -> dict:
    from .logs import probe_failures

    now = now or datetime.now(timezone.utc)
    obs = src.observation(obs_id)
    checks = check_record(obs, obs_id, now)
    if obs is None:
        return {"observation": obs_id, "verdict": FAIL, "checks": [c.as_dict() for c in checks]}
    wf, wf_head = check_artifact(obs, "waterfall", "Waterfall", src, baseline)
    au, au_head = check_artifact(obs, "payload", "Audio", src, baseline)
    checks += [wf, au, check_upload(obs, [wf_head, au_head], baseline), check_metadata(obs)]
    checks += check_review(obs)
    checks += check_logs(obs, log_lines, baseline)
    failures = None
    if probe_lines is not None:
        failures = probe_failures(probe_lines, parse_iso(obs["start"]) - timedelta(minutes=10),
                                  parse_iso(obs["end"]) + timedelta(minutes=baseline.get("upload_max_minutes") or 10))
    checks, probe = apply_probe(checks, failures)
    order = {"4": 0, "5": 1, "6": 2, "7": 3, "8": 4, "9": 5}
    checks.sort(key=lambda c: order.get(c.item, 9))
    return {
        "observation": obs_id,
        "url": f"https://network.satnogs.org/observations/{obs_id}/",
        "verdict": verdict(checks, probe),
        "checks": [c.as_dict() for c in checks] + [probe.as_dict()],
    }
