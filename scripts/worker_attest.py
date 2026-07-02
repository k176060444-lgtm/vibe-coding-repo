#!/usr/bin/env python3
"""
VibeDev Worker Attestation Schema — read-only fixture parser and validator.

Phase 3 PR-4A. Establishes the attestation JSON format for future drift
Layer 2-4 (central pool vs worker runtime config). Pure deterministic
functions — NO SSH, NO subprocess, NO real worker access, NO env read.

=== Schema v1.0 Fields ===
Top-level:
- schema_version: str        (must be "1.0")
- node: str                  (must be 21bao, 5bao, 9bao)
- generated_at: str          (ISO timestamp)
- opencode_config_present: bool
- opencode_env_present: bool
- model_aliases: list[dict]  (see ModelAliasEntry)

model_alias_entry:
- model_id: str
- alias: str
- provider_namespace: str
- lifecycle_status: str
- credential_status: str
- endpoint_ref: str
- key_env: str               (NAME only — NEVER value)
- base_url_env: str          (NAME only — NEVER value)
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Constants ────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
VALID_NODES = frozenset({"21bao", "5bao", "9bao"})
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0"})
REQUIRED_TOP_FIELDS = frozenset({
    "schema_version", "node", "generated_at",
    "opencode_config_present", "opencode_env_present", "model_aliases",
})
REQUIRED_ALIAS_FIELDS = frozenset({
    "model_id", "alias", "provider_namespace", "lifecycle_status",
    "credential_status", "endpoint_ref", "key_env", "base_url_env",
})
# Secret-like value indicators (for detection, never output values)
SECRET_PATTERNS = [
    "sk-", "sk-ant-", "sk-proj-", "ghp_", "gho_", "glpat-", "xai-",
]
URL_PATTERNS = ["http://", "https://"]

# ── Validation ───────────────────────────────────────────────────────────────


def _string_value(value: Any) -> str:
    """Safely convert to string for pattern matching."""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _has_secret_pattern(value: Any) -> bool:
    """Check if a value matches secret-like patterns. Returns True/False only
    — never outputs the matched value."""
    s = _string_value(value)
    if not s:
        return False
    for pat in SECRET_PATTERNS:
        if pat in s:
            return True
    return False


def _has_url_pattern(value: Any) -> bool:
    """Check if a value matches URL-like patterns. Returns True/False only
    — never outputs the matched URL value."""
    s = _string_value(value)
    if not s:
        return False
    for pat in URL_PATTERNS:
        if pat in s:
            return True
    return False


def validate_worker_attestation(data: dict) -> dict:
    """Validate worker attestation JSON data against schema v1.0.

    Args:
        data: Parsed JSON dict from attestation file.

    Returns:
        dict with keys:
        - valid: bool
        - errors: list[str]
        - warnings: list[str]
        - node: str or None
        - model_count: int
        - detail: str
    """
    errors: list[str] = []
    warnings: list[str] = []

    # ── Check top-level required fields ──
    for field in REQUIRED_TOP_FIELDS:
        if field not in data:
            errors.append(f"Missing required top-level field: '{field}'")

    if errors:
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "node": data.get("node"),
            "model_count": 0,
            "detail": "Required top-level field(s) missing",
        }

    # ── Schema version ──
    sv = str(data.get("schema_version", ""))
    if sv not in SUPPORTED_SCHEMA_VERSIONS:
        errors.append(f"Unsupported schema_version '{sv}'. Supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}")

    # ── Node ──
    node = data.get("node", "")
    if node not in VALID_NODES:
        errors.append(f"Invalid node '{node}'. Must be one of: {sorted(VALID_NODES)}")

    # ── Boolean fields ──
    for bool_field in ["opencode_config_present", "opencode_env_present"]:
        val = data.get(bool_field)
        if not isinstance(val, bool):
            errors.append(f"Field '{bool_field}' must be boolean, got {type(val).__name__}")

    # ── Model aliases ──
    aliases = data.get("model_aliases", [])
    if not isinstance(aliases, list):
        errors.append("model_aliases must be a list")
        aliases = []

    if len(aliases) == 0:
        warnings.append("model_aliases is empty")

    for i, entry in enumerate(aliases):
        prefix = f"model_aliases[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix}: must be a dict, got {type(entry).__name__}")
            continue

        # Check required alias fields
        for field in REQUIRED_ALIAS_FIELDS:
            if field not in entry:
                errors.append(f"{prefix}: missing required field '{field}'")

        # Check for secret-like values in key_env and base_url_env
        for secret_field in ["key_env", "base_url_env"]:
            val = entry.get(secret_field)
            if _has_secret_pattern(val):
                errors.append(
                    f"{prefix}: {secret_field} contains secret-like value "
                    f"(expected NAME only, not value)"
                )
            if _has_url_pattern(val):
                errors.append(
                    f"{prefix}: {secret_field} contains URL-like value "
                    f"(expected NAME only, not URL)"
                )

        # Check for secret/URL in any other string field
        for field in ["model_id", "alias", "provider_namespace",
                       "lifecycle_status", "credential_status", "endpoint_ref"]:
            val = entry.get(field)
            if _has_secret_pattern(val):
                errors.append(f"{prefix}: {field} contains secret-like value")
            if _has_url_pattern(val):
                errors.append(f"{prefix}: {field} contains URL-like value")

    valid = len(errors) == 0

    report = {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "node": node,
        "model_count": len(aliases),
        "detail": "PASS" if valid else f"FAIL: {len(errors)} error(s)",
    }

    return report


def self_check() -> dict:
    """Verify import + basic logic work. No file access, no env read."""
    checks = []

    # Test valid attestation
    valid_data = {
        "schema_version": "1.0",
        "node": "21bao",
        "generated_at": "2026-07-02T01:30:00Z",
        "opencode_config_present": True,
        "opencode_env_present": True,
        "model_aliases": [
            {
                "model_id": "opencode-go-mimo-v2-5",
                "alias": "opencode-mimo",
                "provider_namespace": "opencode-go",
                "lifecycle_status": "operator_requested",
                "credential_status": "present",
                "endpoint_ref": "base_url_env",
                "key_env": "OPENCODE_GO_API_KEY",
                "base_url_env": "OPENCODE_GO_BASE_URL",
            }
        ],
    }
    r = validate_worker_attestation(valid_data)
    checks.append({
        "name": "valid_attestation",
        "passed": r["valid"],
        "detail": f"{r['detail']} node={r['node']} models={r['model_count']}",
    })

    # Test invalid node
    invalid_node = dict(valid_data)
    invalid_node["node"] = "10bao"
    r2 = validate_worker_attestation(invalid_node)
    checks.append({
        "name": "invalid_node",
        "passed": not r2["valid"] and any("Invalid node" in e for e in r2["errors"]),
        "detail": f"blocked as expected: {r2['errors']}",
    })

    # Test secret leak detection
    secret_data = dict(valid_data)
    secret_data["model_aliases"][0] = dict(valid_data["model_aliases"][0])
    secret_data["model_aliases"][0]["key_env"] = "sk-ant-test123"
    r3 = validate_worker_attestation(secret_data)
    checks.append({
        "name": "secret_leak_detected",
        "passed": not r3["valid"] and any("secret-like" in e for e in r3["errors"]),
        "detail": f"blocked as expected: {[e for e in r3['errors'] if 'secret' in e]}",
    })

    # Test URL leak detection
    url_data = dict(valid_data)
    url_data["model_aliases"][0] = dict(valid_data["model_aliases"][0])
    url_data["model_aliases"][0]["base_url_env"] = "https://api.example.com/v1"
    r4 = validate_worker_attestation(url_data)
    checks.append({
        "name": "url_leak_detected",
        "passed": not r4["valid"] and any("URL-like" in e for e in r4["errors"]),
        "detail": f"blocked as expected: {[e for e in r4['errors'] if 'URL' in e]}",
    })

    # Test missing field
    missing = dict(valid_data)
    del missing["opencode_config_present"]
    r5 = validate_worker_attestation(missing)
    checks.append({
        "name": "missing_field_detected",
        "passed": not r5["valid"] and any("Missing" in e for e in r5["errors"]),
        "detail": f"blocked as expected: {[e for e in r5['errors'] if 'Missing' in e]}",
    })

    # Test unsupported schema
    bad_schema = dict(valid_data)
    bad_schema["schema_version"] = "0.5"
    r6 = validate_worker_attestation(bad_schema)
    checks.append({
        "name": "unsupported_schema",
        "passed": not r6["valid"] and any("Unsupported" in e for e in r6["errors"]),
        "detail": f"blocked as expected: {[e for e in r6['errors'] if 'Unsupported' in e]}",
    })

    # Test no env read
    checks.append({
        "name": "no_env_read",
        "passed": "environ" not in __import__("inspect").getsource(validate_worker_attestation),
        "detail": "ok" if "environ" not in dir() else "environ accessed",
    })

    all_pass = all(c["passed"] for c in checks)
    return {
        "status": "PASS" if all_pass else "FAIL",
        "version": "1.0.0",
        "checks": checks,
        "detail": f"{sum(1 for c in checks if c['passed'])}/{len(checks)} passed",
    }


# ── CLI ──────────────────────────────────────────────────────────────────────


def cli_validate(path: str) -> int:
    """Validate an attestation fixture JSON file."""
    p = Path(path)
    if not p.exists():
        print(json.dumps({"valid": False, "errors": [f"File not found: {p}"]}))
        return 1
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(json.dumps({"valid": False, "errors": [f"JSON parse error: {e}"]}))
        return 1

    report = validate_worker_attestation(data)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["valid"] else 1


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/worker_attest.py validate <fixture.json>")
        print("  python scripts/worker_attest.py self-check")
        return

    cmd = sys.argv[1]

    if cmd == "validate":
        if len(sys.argv) < 3:
            print("Usage: python scripts/worker_attest.py validate <fixture.json>")
            sys.exit(1)
        sys.exit(cli_validate(sys.argv[2]))

    elif cmd == "self-check":
        result = self_check()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result["status"] == "PASS" else 1)

    else:
        print(f"Unknown command: {cmd}")
        print("Available: validate, self-check")
        sys.exit(1)


if __name__ == "__main__":
    main()
