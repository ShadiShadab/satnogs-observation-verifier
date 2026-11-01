"""Thin, read-only access to the public SatNOGS Network API."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

NETWORK_URL = os.environ.get("SATNOGS_NETWORK_URL", "https://network.satnogs.org").rstrip("/")
USER_AGENT = "satnogs-observation-verifier/0.1"


@dataclass
class HeadResult:
    status: int
    size: int | None
    last_modified: str | None


class Source(Protocol):
    def observation(self, obs_id: int) -> dict | None: ...
    def head(self, url: str) -> HeadResult: ...


class HttpSource:
    """Real data source. Only GET and HEAD are used."""

    def __init__(self, timeout: float = 60.0) -> None:
        import requests

        self._s = requests.Session()
        self._s.headers["User-Agent"] = USER_AGENT
        self._timeout = timeout

    def observation(self, obs_id: int) -> dict | None:
        r = self._s.get(f"{NETWORK_URL}/api/observations/{obs_id}/", timeout=self._timeout)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def head(self, url: str) -> HeadResult:
        r = self._s.head(url, timeout=self._timeout, allow_redirects=True)
        size = r.headers.get("Content-Length")
        return HeadResult(r.status_code, int(size) if size else None, r.headers.get("Last-Modified"))
