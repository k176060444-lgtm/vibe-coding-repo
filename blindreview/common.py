"""Versioned review contracts and canonical, cross-platform report bytes."""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
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
BINDING_FIELDS = ("job_id", "task_id", "commit_sha", "role", "contract_sha256", "harness", "model")

class ProtocolError(ValueError):
    """Invalid or inconsistent request, response or artifact."""

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)

def report_bytes(value: dict[str, Any]) -> bytes:
    return (canonical_json(value) + "\n").encode("utf-8")

def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def local_host_fingerprint() -> str:
    """Best-effort stable OS host fingerprint for independent-node sanity checks.

    This detects duplicate Workers on one honest OS installation. It is not
    remote hardware attestation; trusted node enrollment and unique credentials
    are still required. Never accept this value from caller configuration.
    """
    system = platform.system()
    machine_id = ""
    if system == "Windows":
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Cryptography") as key:
            machine_id = winreg.QueryValueEx(key, "MachineGuid")[0]
    elif system == "Linux":
        for source in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                machine_id = Path(source).read_text(encoding="ascii").strip()
            except OSError:
                continue
            if machine_id:
                break
    elif system == "Darwin":
        result = subprocess.run(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"],
                                capture_output=True, text=True, check=True, timeout=8)
        match = re.search(r'"IOPlatformUUID"\s*=\s*"([^"]+)"', result.stdout)
        machine_id = match.group(1) if match else ""
    if not isinstance(machine_id, str) or len(machine_id.strip()) < 8:
        raise RuntimeError("No trusted local OS machine identity; refusing to start review Worker")
    return sha256_bytes(("blind-review-host-v1:" + system + ":" + machine_id.strip()).encode("utf-8"))


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

def bind_worker_report(raw: Any, request: dict[str, str], node_id: str,
                       physical_host_id: str) -> dict[str, Any]:
    """Envelope metadata is set by Worker, not invented by the reviewer/model.

    Explicit conflicting reviewer metadata is rejected rather than overwritten.
    The physical_host_id is an OPERATOR assertion, not hardware attestation.
    """
    if not isinstance(raw, dict):
        raise ProtocolError("Review report must be a JSON object")
    out = dict(raw)
    bindings = {key: request[key] for key in BINDING_FIELDS}
    bindings.update({"node_id": node_id, "physical_host_id": physical_host_id})
    for key, value in bindings.items():
        if key in out and out[key] != value:
            raise ProtocolError(f"Review output conflicts with approved {key}")
        out[key] = value
    return validate_report(out, request, node_id, physical_host_id)

def validate_report(raw: Any, job: dict[str, str], node_id: str | None = None,
                    physical_host_id: str | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ProtocolError("Review report must be a JSON object")
    required = set(BINDING_FIELDS) | {"node_id", "physical_host_id", "verdict", "summary", "findings"}
    if not required.issubset(raw):
        raise ProtocolError("Missing report fields: " + ", ".join(sorted(required - set(raw))))
    for key in BINDING_FIELDS:
        if not isinstance(raw[key], str) or raw[key] != job[key]:
            raise ProtocolError(f"Report {key} does not match the approved job")
    ensure_pattern("report.node_id", raw["node_id"], NAME)
    ensure_pattern("report.physical_host_id", raw["physical_host_id"], NAME)
    if node_id is not None and raw["node_id"] != node_id:
        raise ProtocolError("Report node identity differs from registered endpoint")
    if physical_host_id is not None and raw["physical_host_id"] != physical_host_id:
        raise ProtocolError("Report physical host declaration differs from registered endpoint")
    if not isinstance(raw["verdict"], str) or raw["verdict"] not in VERDICTS:
        raise ProtocolError("Invalid verdict")
    if not isinstance(raw["summary"], str) or not raw["summary"].strip():
        raise ProtocolError("Empty summary")
    if not isinstance(raw["findings"], list) or len(raw["findings"]) > 500:
        raise ProtocolError("findings must be an array with at most 500 entries")
    for finding in raw["findings"]:
        if not isinstance(finding, dict) or not isinstance(finding.get("severity"), str) or finding["severity"] not in SEVERITIES:
            raise ProtocolError("Invalid finding severity")
        if not isinstance(finding.get("description"), str) or not finding["description"].strip():
            raise ProtocolError("Finding missing description")
        if not isinstance(finding.get("location"), str) or not finding["location"].strip():
            raise ProtocolError("Finding missing file:line or evidence location")
        location = finding["location"]
        if not (re.fullmatch(r"[^\s:][^\n\r]*:[1-9][0-9]*(?:-[1-9][0-9]*)?", location)
                or location.startswith("evidence://")):
            raise ProtocolError("Finding location must be path:line or evidence:// reference")
    return raw
