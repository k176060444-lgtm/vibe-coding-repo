#!/usr/bin/env python3
"""Current UTC time as ISO 8601 string or structured dict."""

import json
import sys
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string (e.g. 2026-06-21T04:00:00Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_structured() -> dict:
    """Return dict with iso, unix, date, time keys."""
    now = datetime.now(timezone.utc)
    return {
        "iso": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "unix": int(now.timestamp()),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
    }


if __name__ == "__main__":
    if "--json" in sys.argv:
        print(json.dumps(utc_now_structured()))
    else:
        print(utc_now_iso())
