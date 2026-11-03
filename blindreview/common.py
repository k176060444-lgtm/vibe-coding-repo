"""Protocol and validation shared by the coordinator and review workers."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")
MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:+-]{0,159}$")
GIT_SHA = re.compile(r"^(?:[a-f0-9]{40}|[a-f0-9]{64})$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
TERMINAL = frozenset({"COMPLETED", "FAILED", "TIMED_OUT", "CANCELLED", "INTERRUPTED"})
VERDICTS = frozenset({"APPROVE", "APPROVE_WITH_COMMENTS", "REQUEST_CHANGES", "NEEDS_SPECIALIST"})
SEVERITIES = frozenset({"BLOCKER", "IMPORTANT", "QUESTION", "NIT", "OPTIONAL", "FYI"})


class ProtocolError(ValueError):
    """Invalid or inconsistent request, response or artifact."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_pattern(name: str, value: Any, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ProtocolError(f"Invalid {name}")
    return value


def validate_request(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ProtocolError("Request must be an object")
    required = {
        "job_id": JOB_ID, "task_id": NAME, "repository": NAME,
        "commit_sha": GIT_SHA, "role": NAME, "harness": NAME,
        "model": MODEL, "contract_sha256": SHA256,
    }
    if set(raw) != set(required):
        raise ProtocolError(f"Request keys must be exactly: {', '.join(sorted(required))}")
    result = {key: ensure_pattern(key, raw[key], regex) for key, regex in required.items()}
    if result["role"] != "blind-review":
        raise ProtocolError("This P0 executor accepts the blind-review role only")
    return result


def validate_report(raw: Any, job: dict[str, str]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProtocolError("Review report must be a JSON object")
    required = {"job_id", "commit_sha", "role", "verdict", "summary", "findings"}
    if not required.issubset(raw.keys()):
        raise ProtocolError("Missing report fields: " + ", ".join(sorted(required - set(raw))))
    for key in ("job_id", "commit_sha", "role"):
        if raw[key] != job[key]:
            raise ProtocolError(f"Report {key} does not match the approved job")
    if raw["verdict"] not in VERDICTS:
        raise ProtocolError("Invalid verdict")
    if not isinstance(raw["summary"], str) or not raw["summary"].strip():
        raise ProtocolError("Empty summary")
    if not isinstance(raw["findings"], list) or len(raw["findings"]) > 500:
        raise ProtocolError("findings must be an array with at most 500 entries")
    for finding in raw["findings"]:
        if not isinstance(finding, dict) or finding.get("severity") not in SEVERITIES:
            raise ProtocolError("Invalid finding severity")
        if not isinstance(finding.get("description"), str) or not finding["description"].strip():
            raise ProtocolError("Finding missing description")
        if not isinstance(finding.get("location"), str) or not finding["location"].strip():
            raise ProtocolError("Finding missing file:line or evidence location")
    return raw
