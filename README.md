# SatNOGS Observation Verifier

[![tests](https://github.com/ShadiShadab/satnogs-observation-verifier/actions/workflows/tests.yml/badge.svg)](https://github.com/ShadiShadab/satnogs-observation-verifier/actions/workflows/tests.yml)

A command-line tool that checks **one [SatNOGS](https://satnogs.org) observation end to end** and prints a PASS/FAIL table: the Network record, the waterfall and audio artifacts, upload timing, client metadata, review status and, if you supply them, the station's client log and a connectivity-probe log.

## Why

During a SatNOGS client release regression, each observation was verified by hand: a dozen `curl`, `grep` and `docker logs` commands per pass, then a judgement against baseline values. This tool automates that **per-observation verification** (regression items 4–9), so every pass can be checked the same way and results are comparable between releases.

It is the "main value" step of the automation roadmap from my SatNOGS ground-station QA work.

## What it checks

| Item | Check | Source | Judged against |
|---|---|---|---|
| 4 | Client start offset: first `ZMQ … SUB Connecting` line vs scheduled start | client log | `start_offset_max_s` |
| 5 | SDR initialised: required lines present; time from SDR open to stream start | client log | `sdr_open_to_stream_max_s` |
| 6 | Flowgraph ran to the end: `netrigctl_close: done` near the scheduled end | client log | `flowgraph_end_tolerance_s` |
| 7 | Waterfall present, reachable (`HEAD 200`), size | Network API, HTTP | `waterfall_bytes` range |
| 7 | Audio present, reachable, bytes per second for the mode | Network API, HTTP | `audio_bytes_per_second[mode]` range |
| 8 | Upload latency: artifact `Last-Modified` minus scheduled end | HTTP | `upload_max_minutes` |
| 8 | No errors after the pass (success is silent; known noise is ignored) | client log | hard rule |
| 9 | Record exists and has finished; status triage | Network API | hard rule |
| 9 | Client metadata written (`client_version`, `client_metadata.radio.parameters`) | Network API | hard rule |
| 9 | Review status, demodulated data count | Network API | reported only |
| – | Connectivity probe: any FAIL from 10 min before start until upload | probe log | validity rule |

## Status rules

- **PASS / FAIL** only when there is a baseline value or a hard rule. **No threshold is invented**: without a baseline, a value is reported as **INFO**.
- **NOT EVALUATED** when an input is missing (no log, or the log does not cover the window). The report says so, and the verdict covers only what was evaluated.
- **BLOCKED** when the connectivity probe shows failures in the window: an unreliable uplink is an environment problem, not a product failure, so failed checks become BLOCKED instead of FAIL.
- Status triage reads the `status` + artifacts + metadata tuple, for example "`unknown` with artifacts = completed, not yet vetted" and "`unknown` without artifacts = interrupted or never executed".

## Usage

```bash
pip install .
satnogs-verify 15135603                     # Network record and artifacts only

# full verification on the station host
docker logs -t satnogs_satnogs-client > client.log 2>&1
satnogs-verify 15135603 --log client.log --probe dns_probe.log \
    --baseline baseline.example.json --json result.json
```

Exit code: `0` PASS, `1` FAIL, `2` BLOCKED, so it can gate a script or CI job.

Example (public observation, no log supplied):

```text
## Observation 15135603 — verdict: **PASS**
INFO: 5 · NOT EVALUATED: 5 · PASS: 3
| 7 | Waterfall generated | INFO | HTTP 200, 1,647,227 bytes; no baseline for this value | HTTP |
| 7 | Audio generated | INFO | HTTP 200, 2,360,399 bytes, 6,902 B/s over 342 s (mode FSK); no baseline ... | HTTP |
| 8 | Upload latency | INFO | last artifact uploaded 2.6 min after end ... | HTTP |
| 9 | Client metadata written | PASS | client 2.1.2, mode FSK, gain 40.5 | API |
| 9 | Review status | INFO | vetted bad, certainty 100 | API |
```

### Baseline file

[baseline.example.json](baseline.example.json) holds the values measured on one reference station (RTL-SDR Blog V4, client 2.1.x, October 2026). **Measure your own station before using thresholds**; they depend on hardware, mode and uplink. Log patterns can be overridden under `"patterns"` for other SDRs.

### Probe log format

One line per sample: `2026-10-16T16:30:00Z host=ok container=ok` (any `FAIL` marks the sample as failed).

## Design

- **Read-only:** only `GET` and `HEAD` against the public Network API. No token is needed or accepted.
- **Testable:** the data source is injected, so the unit tests run offline on synthetic fixtures (no real station data). One optional live test verifies a recent public observation.
- **Thresholds are data, not code:** all limits live in the baseline JSON.

```bash
pip install -e ".[test]"
python -m pytest            # offline
python -m pytest -m live    # one live check
```

## Limitations and next steps

- Log checks assume the SatNOGS Client 2.1.x log lines with an RTL-SDR; other SDRs need pattern overrides.
- It does not open the waterfall image to judge it visually; that stays a human step.
- Next: trigger it automatically at the end of each pass, and add the flowgraph-name capture.

## License

[GNU Affero General Public License v3.0](LICENSE), the same licence as the SatNOGS Client. SatNOGS is a project of Libre Space Foundation; this repository is independent and not endorsed by it.
