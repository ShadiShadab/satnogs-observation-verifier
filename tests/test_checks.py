import json
from datetime import datetime, timezone

from satnogs_verify import checks
from satnogs_verify.logs import read_client_log
from satnogs_verify.network import HeadResult
from tests.conftest import FakeSource

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)
BASELINE = json.loads(open("baseline.example.json").read())


def by_name(result):
    return {c["name"]: c for c in result["checks"]}


def log(fix, name):
    return read_client_log((fix / name).read_text().splitlines(keepends=True))


def test_clean_observation_passes_against_baseline(good_source, fix):
    r = checks.run(100001, good_source, BASELINE, log(fix, "client_good.log"),
                   (fix / "probe_ok.log").read_text().splitlines(), now=NOW)
    c = by_name(r)
    assert r["verdict"] == "PASS", r
    assert c["Client start offset"]["status"] == "PASS" and "+1.75 s" in c["Client start offset"]["detail"]
    assert c["SDR initialised"]["detail"].startswith("open → stream 0.95 s")
    assert c["Flowgraph ran to end"]["status"] == "PASS"
    assert c["Upload latency"]["detail"].startswith("last artifact uploaded 3.5 min after end")
    assert c["Audio generated"]["status"] == "PASS"   # 4.14 MB / 600 s = 6,900 B/s, FSK baseline
    assert c["Connectivity probe"]["status"] == "PASS"


def test_without_baseline_values_are_reported_not_judged(good_source, fix):
    r = checks.run(100001, good_source, {}, log(fix, "client_good.log"), now=NOW)
    c = by_name(r)
    for name in ("Waterfall generated", "Audio generated", "Upload latency", "Client start offset", "SDR initialised"):
        assert c[name]["status"] == "INFO", name
    assert r["verdict"] == "PASS"


def test_missing_inputs_are_not_evaluated(good_source):
    c = by_name(checks.run(100001, good_source, {}, now=NOW))
    assert c["Client start offset"]["status"] == "NOT EVALUATED"
    assert c["Connectivity probe"]["status"] == "NOT EVALUATED"


def test_unknown_observation_fails():
    r = checks.run(5, FakeSource(None), {}, now=NOW)
    assert r["verdict"] == "FAIL" and "not found" in r["checks"][0]["detail"]


def test_missing_metadata_is_flagged(good_obs):
    good_obs["client_version"], good_obs["client_metadata"] = "", ""
    assert checks.check_metadata(good_obs).status == "FAIL"


def test_missing_artifact_fails(good_obs):
    good_obs["waterfall"] = None
    r = checks.run(100001, FakeSource(good_obs), {}, now=NOW)
    assert by_name(r)["Waterfall present"]["status"] == "FAIL"
    assert r["verdict"] == "FAIL"


def test_error_after_pass_fails_but_noise_is_ignored(good_source, fix):
    lines = (fix / "client_good.log").read_text().splitlines(keepends=True)
    lines.append("2026-10-16T16:43:00.000000000Z Fetching jobs ERROR Max retries exceeded\n")
    c = by_name(checks.run(100001, good_source, {}, read_client_log(lines), now=NOW))
    assert c["No errors after pass"]["status"] == "PASS"
    lines.append("2026-10-16T16:44:00.000000000Z ERROR upload failed: HTTP 500\n")
    c = by_name(checks.run(100001, good_source, {}, read_client_log(lines), now=NOW))
    assert c["No errors after pass"]["status"] == "FAIL"


def test_probe_failure_turns_failures_into_blocked(good_obs, fix):
    good_obs["waterfall"] = None
    r = checks.run(100001, FakeSource(good_obs), {}, probe_lines=(fix / "probe_fail.log").read_text().splitlines(), now=NOW)
    c = by_name(r)
    assert r["verdict"] == "BLOCKED"
    assert c["Waterfall present"]["status"] == "BLOCKED"


def test_overlapping_logs_are_deduplicated(fix):
    raw = (fix / "client_good.log").read_text().splitlines(keepends=True)
    assert len(read_client_log(raw + raw)) == len(read_client_log(raw))


def test_triage_tuples():
    assert checks.triage({"status": "unknown", "payload": "x"}) == "completed, not yet vetted"
    assert checks.triage({"status": "unknown"}) == "interrupted or never executed (no artifacts)"
    assert checks.triage({"status": "failed", "client_metadata": "{}x"}) == "execution-stage failure"
    assert checks.triage({"status": "failed", "waterfall": "x"}) == "failed, partial data preserved"
    assert checks.triage({"status": "future"}).startswith("not finished")
