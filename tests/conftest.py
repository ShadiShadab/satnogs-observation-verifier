import json
from pathlib import Path

import pytest

from satnogs_verify.network import HeadResult

FIX = Path(__file__).parent / "fixtures"


class FakeSource:
    def __init__(self, obs, heads=None):
        self.obs = obs
        self.heads = heads or {}

    def observation(self, obs_id):
        return self.obs

    def head(self, url):
        return self.heads.get(url, HeadResult(404, None, None))


@pytest.fixture
def fix():
    return FIX


@pytest.fixture
def good_obs():
    return json.loads((FIX / "observation_good.json").read_text())


@pytest.fixture
def good_source(good_obs):
    heads = {
        good_obs["waterfall"]: HeadResult(200, 1_650_000, "Fri, 16 Oct 2026 16:45:30 GMT"),
        good_obs["payload"]: HeadResult(200, 4_140_000, "Fri, 16 Oct 2026 16:45:10 GMT"),
    }
    return FakeSource(good_obs, heads)
