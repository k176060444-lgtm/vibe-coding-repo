#!/usr/bin/env python3
"""Credential Status Resolver v1.0.0

Resolves secret_ref placeholders to credential_status + safe metadata.
Never reads, returns, stores, or prints real keys.

Backends:
    - fixture: inline dict or JSON file with secret_ref → status mapping
    - env-status: checks if named env vars exist (presence only, no value read)
    - file: loads fixture data from JSON file

Usage:
    python scripts/credential_status_resolver.py --self-check
    python scripts/credential_status_resolver.py resolve --secret-ref secret:deepseek-plan:deepseek-v4-pro
    python scripts/credential_status_resolver.py resolve --secret-ref secret:deepseek-plan:deepseek-v4-pro --backend env-status

Contract: docs/MODEL_POOL_DISTRIBUTION_CONTRACT.md
"""

__version__ = "1.0.0"

import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Optional

# --- Constants ---

RESOLVER_VERSION = __version__

VALID_CREDENTIAL_STATUSES = {"valid", "expired", "missing", "not-configured", "unknown"}

VALID_BACKENDS = {"fixture", "file", "env-status"}

# Patterns that indicate a real key (not a placeholder)
DANGEROUS_KEY_PATTERNS = [
    r"sk-[a-zA-Z0-9]{10,}",
    r"AKIA[A-Z0-9]{16}",
    r"Bearer [a-zA-Z0-9]{10,}",
    r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH)\s+PRIVATE\s+KEY-----",
]

# Sensitive field names that must never appear in output
SENSITIVE_FIELD_NAMES = {
    "key", "api_key", "token", "secret_value", "password", "access_token",
    "OPENAI_API_KEY", "DEEPSEEK_API_KEY", "VOLCENGINE_API_KEY",
    "XIAOMI_API_KEY", "MINIMAX_API_KEY", "secret_key", "private_key",
    "auth_token", "authorization", "bearer",
}

# Provider → env var name mapping for env-status backend
PROVIDER_ENV_MAP = {
    "deepseek-plan": "DEEPSEEK_API_KEY",
    "volcengine-plan": "VOLCENGINE_API_KEY",
    "xiaomi-plan": "XIAOMI_API_KEY",
    "minimax-plan": "MINIMAX_CN_API_KEY",
}


# --- Validation ---


def validate_secret_ref(secret_ref: str) -> tuple[bool, str]:
    """Validate secret_ref is a safe placeholder.

    Returns (valid, error_message).
    """
    if not secret_ref or not isinstance(secret_ref, str):
        return False, "secret_ref must be a non-empty string"

    # Must start with secret:
    if not secret_ref.startswith("secret:"):
        return False, f"secret_ref must start with 'secret:' or be empty, got: {secret_ref[:30]}..."

    # Must have exactly 3 parts: secret:<provider>:<alias>
    parts = secret_ref.split(":")
    if len(parts) < 3:
        return False, f"secret_ref must have format 'secret:<provider>:<alias>', got: {secret_ref[:50]}"

    # Check for dangerous key patterns
    for pattern in DANGEROUS_KEY_PATTERNS:
        if re.search(pattern, secret_ref, re.IGNORECASE):
            return False, "secret_ref contains suspected real key pattern"

    # Check for suspiciously long values (real tokens are usually long)
    if len(secret_ref) > 200:
        return False, "secret_ref too long (suspected real token)"

    return True, ""


def validate_backend(backend: str) -> tuple[bool, str]:
    """Validate backend is recognized."""
    if backend not in VALID_BACKENDS:
        return False, f"invalid backend: {backend}. Valid: {sorted(VALID_BACKENDS)}"
    return True, ""


def parse_secret_ref(secret_ref: str) -> tuple[str, str]:
    """Parse secret_ref into (provider, alias).

    Assumes secret_ref is already validated.
    """
    parts = secret_ref.split(":", 2)
    # parts[0] = "secret", parts[1] = provider, parts[2] = alias
    provider = parts[1] if len(parts) > 1 else "unknown"
    alias = parts[2] if len(parts) > 2 else "unknown"
    return provider, alias


# --- Output Safety ---


def validate_output_safety(output: dict) -> tuple[bool, list[str]]:
    """Validate resolver output contains no sensitive fields.

    Returns (safe, violations).
    """
    violations = []

    # Check top-level keys
    for key in output:
        if key.lower() in {f.lower() for f in SENSITIVE_FIELD_NAMES}:
            violations.append(f"sensitive top-level key: {key}")

    # Check metadata keys
    metadata = output.get("metadata", {})
    if isinstance(metadata, dict):
        for key in metadata:
            if key.lower() in {f.lower() for f in SENSITIVE_FIELD_NAMES}:
                violations.append(f"sensitive metadata key: {key}")

    # Check for dangerous patterns in serialized output
    output_str = json.dumps(output, ensure_ascii=False)
    for pattern in DANGEROUS_KEY_PATTERNS:
        if re.search(pattern, output_str, re.IGNORECASE):
            violations.append(f"dangerous pattern in output: {pattern}")

    return len(violations) == 0, violations


# --- Backends ---


def _resolve_fixture(secret_ref: str, fixture_data: dict) -> dict:
    """Resolve from inline fixture dict.

    Fixture format:
    {
        "credentials": {
            "secret:provider:alias": {
                "credential_status": "valid",
                "status_reason": "configured"
            }
        }
    }
    """
    credentials = fixture_data.get("credentials", {})

    if secret_ref in credentials:
        entry = credentials[secret_ref]
        return {
            "credential_status": entry.get("credential_status", "unknown"),
            "status_reason": entry.get("status_reason", "fixture match"),
        }

    # No match → unknown
    return {
        "credential_status": "unknown",
        "status_reason": f"secret_ref not found in fixture",
    }


def _resolve_env_status(secret_ref: str) -> dict:
    """Resolve by checking if provider env var exists.

    Only checks existence (name in os.environ), never reads the value.
    """
    provider, alias = parse_secret_ref(secret_ref)

    # Map provider to env var name
    env_var = PROVIDER_ENV_MAP.get(provider)

    if env_var is None:
        # Try common pattern
        env_var = f"{provider.upper().replace('-', '_')}_API_KEY"

    exists = env_var in os.environ

    return {
        "credential_status": "valid" if exists else "missing",
        "status_reason": f"env var {env_var} {'found' if exists else 'not found'}",
    }


def _resolve_file(secret_ref: str, file_path: str) -> dict:
    """Resolve from fixture JSON file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"fixture file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return _resolve_fixture(secret_ref, data)


# --- Main Resolver ---


def resolve_credential(
    secret_ref: str,
    backend: str = "fixture",
    fixture_data: Optional[dict] = None,
    fixture_path: Optional[str] = None,
) -> dict:
    """Resolve secret_ref to credential_status + safe metadata.

    Args:
        secret_ref: Placeholder reference, format "secret:<provider>:<alias>"
        backend: Resolution backend — "fixture", "file", or "env-status"
        fixture_data: Inline fixture dict (for backend="fixture")
        fixture_path: Path to fixture JSON file (for backend="file")

    Returns:
        {
            "secret_ref": str,
            "credential_status": "valid"|"expired"|"missing"|"not-configured"|"unknown",
            "metadata": {
                "provider": str,
                "alias": str,
                "source": str,
                "last_checked": str (ISO timestamp),
                "status_reason": str,
                "resolver_version": str,
            },
            "resolved_at": str,
            "resolver_version": str,
        }

    Raises:
        ValueError: If secret_ref or backend is invalid
    """
    # Validate secret_ref
    valid, err = validate_secret_ref(secret_ref)
    if not valid:
        raise ValueError(f"invalid secret_ref: {err}")

    # Validate backend
    valid, err = validate_backend(backend)
    if not valid:
        raise ValueError(f"invalid backend: {err}")

    # Parse secret_ref
    provider, alias = parse_secret_ref(secret_ref)

    # Resolve based on backend
    if backend == "fixture":
        if fixture_data is None:
            # Empty fixture → unknown
            raw = {"credential_status": "unknown", "status_reason": "no fixture data provided"}
        else:
            raw = _resolve_fixture(secret_ref, fixture_data)
    elif backend == "file":
        if fixture_path is None:
            raise ValueError("fixture_path required for backend='file'")
        raw = _resolve_file(secret_ref, fixture_path)
    elif backend == "env-status":
        raw = _resolve_env_status(secret_ref)
    else:
        raise ValueError(f"unsupported backend: {backend}")

    # Build output
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    output = {
        "secret_ref": secret_ref,
        "credential_status": raw.get("credential_status", "unknown"),
        "metadata": {
            "provider": provider,
            "alias": alias,
            "source": backend,
            "last_checked": now,
            "status_reason": raw.get("status_reason", ""),
            "resolver_version": RESOLVER_VERSION,
        },
        "resolved_at": now,
        "resolver_version": RESOLVER_VERSION,
    }

    # Safety check
    safe, violations = validate_output_safety(output)
    if not safe:
        raise RuntimeError(f"resolver output safety check failed: {violations}")

    return output


# --- Batch Resolve ---


def resolve_batch(
    secret_refs: list[str],
    backend: str = "fixture",
    fixture_data: Optional[dict] = None,
    fixture_path: Optional[str] = None,
) -> list[dict]:
    """Resolve multiple secret_refs. Returns list of results."""
    results = []
    for ref in secret_refs:
        try:
            result = resolve_credential(
                ref, backend=backend,
                fixture_data=fixture_data, fixture_path=fixture_path,
            )
            results.append(result)
        except (ValueError, RuntimeError) as e:
            results.append({
                "secret_ref": ref,
                "credential_status": "unknown",
                "metadata": {
                    "provider": "unknown",
                    "alias": "unknown",
                    "source": backend,
                    "last_checked": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "status_reason": f"resolver error: {str(e)[:100]}",
                    "resolver_version": RESOLVER_VERSION,
                },
                "resolved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "resolver_version": RESOLVER_VERSION,
                "error": str(e)[:200],
            })
    return results


# --- Self-check ---


def self_check() -> dict:
    """Self-check: verify resolver is importable and core logic works."""
    checks = []
    passed = 0
    total = 0

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal passed, total
        total += 1
        if ok:
            passed += 1
        checks.append({"name": name, "passed": ok, "detail": detail})

    # sc-01: version
    check("sc-01-version", bool(RESOLVER_VERSION), RESOLVER_VERSION)

    # sc-02: valid secret_ref
    valid, _ = validate_secret_ref("secret:test-provider:test-model")
    check("sc-02-valid-ref", valid)

    # sc-03: reject empty
    valid, _ = validate_secret_ref("")
    check("sc-03-reject-empty", not valid)

    # sc-04: reject non-secret prefix
    valid, _ = validate_secret_ref("sk-abcdefghijklmnop")
    check("sc-04-reject-sk", not valid)

    # sc-05: reject AKIA
    valid, _ = validate_secret_ref("secret:test:AKIAIOSFODNN7EXAMPLE")
    check("sc-05-reject-akia", not valid)

    # sc-06: fixture resolve
    fixture = {
        "credentials": {
            "secret:test-prov:test-model": {
                "credential_status": "valid",
                "status_reason": "test fixture",
            }
        }
    }
    result = resolve_credential("secret:test-prov:test-model", backend="fixture", fixture_data=fixture)
    check("sc-06-fixture-valid", result["credential_status"] == "valid", str(result["credential_status"]))

    # sc-07: fixture missing
    result2 = resolve_credential("secret:test-prov:nonexistent", backend="fixture", fixture_data=fixture)
    check("sc-07-fixture-unknown", result2["credential_status"] == "unknown")

    # sc-08: env-status backend
    result3 = resolve_credential("secret:deepseek-plan:deepseek-v4-pro", backend="env-status")
    check("sc-08-env-status", result3["credential_status"] in ("valid", "missing"),
          result3["credential_status"])

    # sc-09: output safety
    safe, violations = validate_output_safety(result)
    check("sc-09-output-safe", safe, str(violations))

    # sc-10: invalid backend
    try:
        resolve_credential("secret:test:model", backend="invalid")
        check("sc-10-invalid-backend", False, "should have raised")
    except ValueError:
        check("sc-10-invalid-backend", True)

    # sc-11: batch resolve
    results = resolve_batch(
        ["secret:test-prov:test-model", "secret:test-prov:nonexistent"],
        backend="fixture", fixture_data=fixture,
    )
    check("sc-11-batch", len(results) == 2)

    # sc-12: metadata fields
    meta = result["metadata"]
    check("sc-12-metadata-provider", meta["provider"] == "test-prov")
    check("sc-12-metadata-alias", meta["alias"] == "test-model")
    check("sc-12-metadata-source", meta["source"] == "fixture")
    check("sc-12-metadata-resolver-version", meta["resolver_version"] == RESOLVER_VERSION)

    return {
        "resolver_version": RESOLVER_VERSION,
        "checks": checks,
        "passed": passed,
        "total": total,
        "status": "ok" if passed == total else "FAIL",
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        result = self_check()
        print(json.dumps(result, indent=2))
    elif len(sys.argv) > 1 and sys.argv[1] == "resolve":
        # Simple CLI: resolve --secret-ref X [--backend Y]
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--secret-ref", required=True)
        parser.add_argument("--backend", default="fixture")
        args = parser.parse_args(sys.argv[2:])
        try:
            result = resolve_credential(args.secret_ref, backend=args.backend)
            print(json.dumps(result, indent=2))
        except (ValueError, RuntimeError) as e:
            print(json.dumps({"error": str(e)}))
            sys.exit(1)
    else:
        print("Usage: python credential_status_resolver.py --self-check")
        print("       python credential_status_resolver.py resolve --secret-ref secret:provider:alias")
        sys.exit(0)
