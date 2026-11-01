from __future__ import annotations

import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

_FRACTION = re.compile(r"(\.\d{6})\d+")


def parse_iso(value: str) -> datetime:
    """Parse ISO-8601 with 'Z' and up to nanosecond precision (as written by `docker logs -t`)."""
    value = _FRACTION.sub(r"\1", value.strip()).replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def parse_http_date(value: str) -> datetime:
    return parsedate_to_datetime(value)
