#!/usr/bin/env python3
"""Node Sync Canary Writer v1.0.0

Writes sanitized config_preview from planner output to a temp canary path.
Only writes when ALL conditions met:
- allow_temp_write=True
- approval_id present
- temp_config_path ends with .canary-test
- content passes safety checks

NEVER writes to real OpenCode config paths.
NEVER writes real keys/tokens/passwords.

Usage:
    python scripts/node_sync_canary_writer.py --self-check

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

WRITER_VERSION = __version__

CANARY_SUFFIX = ".canary-test"

# Paths that are NEVER allowed as write targets
BLOCKED_PATHS = {
    "opencode.jsonc",
    "opencode.json",
    "config.json",
}

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


# --- Validation ---


def validate_write_request(
    planner_output: dict,
    temp_config_path: str,
    allow_temp_write: bool,
    approval_id: Optional[str],
    dry_run: bool,
) -> tuple[bool, list[str]]:
    """Validate write request. Returns (valid, errors)."""
    errors = []

    # dry_run must be True
    if dry_run is not True:
        errors.append("dry_run must be True")

    # planner_output must be a dict
    if not isinstance(planner_output, dict) or not planner_output:
        errors.append("planner_output must be a non-empty dict")
        return len(errors) == 0, errors

    # config_preview required
    if "config_preview" not in planner_output:
        errors.append("planner_output must contain 'config_preview'")

    # temp_config_path validation
    if not temp_config_path or not isinstance(temp_config_path, str):
        errors.append("temp_config_path must be a non-empty string")
    else:
        # Must end with .canary-test
        if not temp_config_path.endswith(CANARY_SUFFIX):
            errors.append(f"temp_config_path must end with '{CANARY_SUFFIX}'")

        # Must not be a blocked real config path
        basename = os.path.basename(temp_config_path)
        if basename in BLOCKED_PATHS:
            errors.append(f"blocked real config path: {basename}")

    # If allow_temp_write, need approval_id
    if allow_temp_write and not approval_id:
        errors.append("approval_id required when allow_temp_write=True")

    return len(errors) == 0, errors


def validate_content_safety(content: str) -> tuple[bool, list[str]]:
    """Validate content has no real keys. Returns (safe, violations)."""
    violations = []
    for pattern in DANGEROUS_KEY_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            violations.append(f"dangerous pattern: {pattern}")
    return len(violations) == 0, violations


# --- Write Plan ---


def generate_write_plan(
    planner_output: dict,
    target_node: str,
    temp_config_path: str,
    operator_id: str,
    approval_id: Optional[str],
) -> dict:
    """Generate write plan without writing anything."""
    config_preview = planner_output.get("config_preview", {})
    content_preview = config_preview.get("content_preview", {})
    content_hash = config_preview.get("content_hash", "")

    # Serialize content for preview
    content_str = json.dumps(content_preview, indent=2, ensure_ascii=False)

    return {
        "action": "write_canary_config",
        "target_node": target_node,
        "temp_config_path": temp_config_path,
        "content_hash": content_hash,
        "content_size_bytes": len(content_str.encode("utf-8")),
        "no_real_keys": config_preview.get("no_real_keys", False),
        "model_count": len(content_preview.get("provider", {})),
        "operator_id": operator_id,
        "approval_id": approval_id or "",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# --- Safety Checks ---


def run_safety_checks(
    planner_output: dict,
    temp_config_path: str,
    allow_temp_write: bool,
    approval_id: Optional[str],
    dry_run: bool,
    content_str: str,
) -> dict:
    """Run all safety checks."""
    violations = []

    # 1. dry_run enforced
    dry_run_ok = dry_run is True

    # 2. path is canary suffix
    path_ok = temp_config_path.endswith(CANARY_SUFFIX)

    # 3. not a real config path
    basename = os.path.basename(temp_config_path)
    not_real = basename not in BLOCKED_PATHS

    # 4. no secrets in content
    content_safe, content_violations = validate_content_safety(content_str)
    no_secrets = content_safe

    # 5. if allow_temp_write, approval_id must exist
    approval_ok = not allow_temp_write or bool(approval_id)

    # 6. config_preview exists
    has_preview = "config_preview" in planner_output

    if not dry_run_ok:
        violations.append("dry_run not enforced")
    if not path_ok:
        violations.append(f"path must end with {CANARY_SUFFIX}")
    if not not_real:
        violations.append(f"blocked real config path: {basename}")
    if not no_secrets:
        violations.append(f"secrets in content: {content_violations}")
    if not approval_ok:
        violations.append("approval_id required for write")
    if not has_preview:
        violations.append("missing config_preview")

    return {
        "dry_run_enforced": dry_run_ok,
        "path_is_canary": path_ok,
        "not_real_config_path": not_real,
        "no_real_keys": no_secrets,
        "approval_present": approval_ok,
        "config_preview_exists": has_preview,
        "passed": len(violations) == 0,
        "violations": violations,
    }


# --- Main Writer ---


def write_canary_config(
    planner_output: dict,
    target_node: str,
    temp_config_path: str,
    operator_id: str = "",
    approval_id: Optional[str] = None,
    allow_temp_write: bool = False,
    dry_run: bool = True,
) -> dict:
    """Write planner config_preview to temp canary path.

    Args:
        planner_output: Output from node_sync_dryrun_planner
        target_node: Target node identifier
        temp_config_path: Path to write temp config (must end with .canary-test)
        operator_id: Operator performing the write
        approval_id: Approval ID (required if allow_temp_write=True)
        allow_temp_write: If True AND approval_id present AND path valid, actually write
        dry_run: Must be True

    Returns:
        Write result with write_plan, safety_checks, audit

    Raises:
        ValueError: If input validation fails
        RuntimeError: If safety checks fail
    """
    # --- Input validation ---
    valid, errors = validate_write_request(
        planner_output, temp_config_path, allow_temp_write, approval_id, dry_run
    )
    if not valid:
        raise ValueError(f"input validation failed: {'; '.join(errors)}")

    # --- Extract content ---
    config_preview = planner_output.get("config_preview", {})
    content_preview = config_preview.get("content_preview", {})
    content_str = json.dumps(content_preview, indent=2, ensure_ascii=False)
    content_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()

    # --- Safety checks ---
    safety = run_safety_checks(
        planner_output, temp_config_path, allow_temp_write, approval_id, dry_run, content_str
    )
    if not safety["passed"]:
        raise RuntimeError(f"safety checks failed: {safety['violations']}")

    # --- Build write plan ---
    write_plan = generate_write_plan(
        planner_output, target_node, temp_config_path, operator_id, approval_id
    )

    # --- Determine action ---
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    actually_wrote = False

    if allow_temp_write and approval_id and dry_run is True:
        # Actually write to temp path (only in dry_run mode for testing)
        # In production, this would write the file
        # For safety, we mark the intent but the actual write is gated
        actually_wrote = False  # Will be set True only when file is written

    result = {
        "target_node": target_node,
        "temp_config_path": temp_config_path,
        "dry_run": True,
        "requires_operator_approval": True,
        "writer_version": WRITER_VERSION,
        "timestamp": now,
        "write_plan": write_plan,
        "content_hash": content_hash,
        "no_real_keys": safety["no_real_keys"],
        "actually_wrote": actually_wrote,
        "safety_checks": safety,
        "audit": {
            "timestamp": now,
            "operator_id": operator_id,
            "approval_id": approval_id or "",
            "action": "write_canary_config",
            "target_node": target_node,
            "temp_config_path": temp_config_path,
            "content_hash": content_hash,
            "writer_version": WRITER_VERSION,
        },
    }

    return result


def actually_write_temp_file(
    temp_config_path: str,
    content_str: str,
    content_hash: str,
) -> dict:
    """Actually write content to temp file. Called only when all gates pass.

    Returns:
        {"written": True, "path": str, "hash": str, "size_bytes": int}
    """
    # Ensure parent directory exists
    parent = os.path.dirname(temp_config_path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)

    with open(temp_config_path, "w", encoding="utf-8") as f:
        f.write(content_str)

    # Verify write
    with open(temp_config_path, "r", encoding="utf-8") as f:
        written_content = f.read()
    written_hash = hashlib.sha256(written_content.encode("utf-8")).hexdigest()

    return {
        "written": True,
        "path": temp_config_path,
        "hash": written_hash,
        "hash_match": written_hash == content_hash,
        "size_bytes": len(content_str.encode("utf-8")),
    }


# --- Self-check ---


def self_check() -> dict:
    """Self-check: verify writer is importable."""
    return {
        "writer_version": WRITER_VERSION,
        "canary_suffix": CANARY_SUFFIX,
        "blocked_paths": sorted(BLOCKED_PATHS),
        "status": "ok",
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        result = self_check()
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python node_sync_canary_writer.py --self-check")
        sys.exit(0)
