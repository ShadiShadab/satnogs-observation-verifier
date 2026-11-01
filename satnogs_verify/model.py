from __future__ import annotations

from dataclasses import asdict, dataclass

# Status vocabulary (subset of the one used in station QA):
# PASS / FAIL       - judged against an explicit baseline or a hard rule
# INFO              - raw value reported; no threshold given, so none is invented
# BLOCKED           - the environment invalidates the window (connectivity probe failures)
# NOT EVALUATED     - input missing (e.g. no log supplied)
PASS, FAIL, INFO, BLOCKED, NOT_EVALUATED = "PASS", "FAIL", "INFO", "BLOCKED", "NOT EVALUATED"


@dataclass
class Check:
    item: str          # regression item number, e.g. "7"
    name: str
    status: str
    detail: str
    evidence: str      # where the value came from: API, HTTP, LOG, PROBE

    def as_dict(self) -> dict:
        return asdict(self)
