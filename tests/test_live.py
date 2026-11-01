"""Optional live check against the public Network API: python -m pytest -m live"""
import pytest
import requests

from satnogs_verify import checks
from satnogs_verify.network import NETWORK_URL, HttpSource

pytestmark = pytest.mark.live


def test_recent_good_observation_verifies():
    obs = requests.get(f"{NETWORK_URL}/api/observations/", params={"status": "good"}, timeout=60).json()
    obs = next((o for o in obs if o["status"] == "good" and o["payload"] and o["waterfall"]), None)
    if obs is None:
        pytest.skip("no suitable observation on the first page")
    r = checks.run(obs["id"], HttpSource(), {})
    names = {c["name"]: c["status"] for c in r["checks"]}
    assert names["Observation record exists"] == "PASS"
    assert names["Waterfall generated"] == "INFO" and names["Audio generated"] == "INFO"
