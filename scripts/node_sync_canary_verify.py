#!/usr/bin/env python3
"""Node Sync Canary Verify v1.0.0

Offline verification of canary config files:
- File existence check
- Hash match against expected
- Schema basic parse (JSON valid, has provider structure)
- No real keys in content

NEVER calls OpenCode process.
NEVER reads/writes real keys.

Usage:
    python scripts/node_sync_canary_verify.py --self-check

Contract: docs/MODEL_POOL_DISTRIBUTION_CONTRACT.md
"""

__version__ = "1.0.0"

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Optional

# --- Constants ---

VERIFY_VERSION = __version__

DANGEROUS_KEY_PATTERNS = [
    r"sk-[a-zA-Z0-9]{10,}",
    r"AKIA[A-Z0-9]{16}",
    r"Bearer [a-zA-Z0-9]{10,}",
    r"api[_-]?key\s*[:=]\s*[\"'][a-zA-Z0-9]{10,}",
    r"access[_-]?token\s*[:=]\s*[\"'][a-zA-Z0-9]{10,}",
    r"OPENAI_API_KEY\s*=\s*[a-zA-Z0-9-]{10,}",
    r"DEEPSEEK_API_KEY\s*=\s*[a-zA-Z0-9-]{10,}",
    r"password\s*[:=]\s*[\"'][^\"']{6,}",
    r"secret[_-]?value\s*[:=]\s*[\"'][^\"']{6,}",
    r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH)\s+PRIVATE\s+KEY-----",
]


# --- Verification ---


def verify_canary_config(
    temp_config_path: str,
    expected_hash: str = "",
    operator_id: str = "",
) -> dict:
    """Verify a canary config file offline.

    Args:
        temp_config_path: Path to the canary config file
        expected_hash: Expected SHA256 hash (empty = skip hash check)
        operator_id: Operator performing verification

    Returns:
        Verification result with exists, hash_match, schema_valid,
        no_real_keys, would_be_loadable_offline, violations, audit
    """
    violations = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. File existence
    exists = os.path.isfile(temp_config_path)

    if not exists:
        return {
            "exists": False,
            "hash_match": False,
            "schema_valid": False,
            "no_real_keys": False,
            "would_be_loadable_offline": False,
            "violations": ["file does not exist"],
            "audit": {
                "timestamp": now,
                "operator_id": operator_id,
                "action": "verify_canary_config",
                "path": temp_config_path,
                "verify_version": VERIFY_VERSION,
            },
        }

    # 2. Read content
    with open(temp_config_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 3. Hash check
    actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    hash_match = True
    if expected_hash:
        hash_match = actual_hash == expected_hash
        if not hash_match:
            violations.append(f"hash mismatch: expected {expected_hash[:16]}... got {actual_hash[:16]}...")

    # 4. No real keys
    no_real_keys = True
    for pattern in DANGEROUS_KEY_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            no_real_keys = False
            violations.append(f"dangerous pattern detected: {pattern}")

    # 5. Schema basic parse
    schema_valid = False
    would_be_loadable = False
    try:
        # Strip // comments for jsonc
        lines = []
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("//"):
                continue
            if "//" in stripped:
                in_str = False
                for i, ch in enumerate(stripped):
                    if ch == '"':
                        in_str = not in_str
                    elif not in_str and stripped[i:i+2] == "//":
                        stripped = stripped[:i]
                        break
            lines.append(stripped)

        cleaned = "\n".join(lines)
        data = json.loads(cleaned)
        schema_valid = isinstance(data, dict)

        # Basic structure check
        if schema_valid:
            has_provider = "provider" in data
            has_model = "model" in data or "default_model" in data
            would_be_loadable = has_provider or has_model
            if not would_be_loadable:
                violations.append("missing provider or model field")

    except json.JSONDecodeError as e:
        violations.append(f"JSON parse error: {str(e)[:100]}")

    return {
        "exists": exists,
        "hash_match": hash_match,
        "schema_valid": schema_valid,
        "no_real_keys": no_real_keys,
        "would_be_loadable_offline": would_be_loadable,
        "actual_hash": actual_hash,
        "violations": violations,
        "audit": {
            "timestamp": now,
            "operator_id": operator_id,
            "action": "verify_canary_config",
            "path": temp_config_path,
            "expected_hash": expected_hash or "(not provided)",
            "actual_hash": actual_hash,
            "verify_version": VERIFY_VERSION,
        },
    }


# --- Self-check ---


def self_check() -> dict:
    """Self-check: verify module is importable."""
    return {
        "verify_version": VERIFY_VERSION,
        "status": "ok",
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        result = self_check()
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python node_sync_canary_verify.py --self-check")
        sys.exit(0)
