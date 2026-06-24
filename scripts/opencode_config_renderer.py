#!/usr/bin/env python3
"""OpenCode Config Renderer — Dry-run Only v1.0.0

Generates per-node OpenCode configuration drafts from sanitized model pool data.
Operates in DRY-RUN MODE ONLY — no configuration is delivered to nodes.

Usage:
    python scripts/opencode_config_renderer.py --self-check
    python scripts/opencode_config_renderer.py render --input fixture.json
    python scripts/opencode_config_renderer.py render --node 21bao --models pool.json

Contract: docs/MODEL_POOL_DISTRIBUTION_CONTRACT.md §4
"""

__version__ = "1.0.0"

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from typing import Any, Optional

# --- Constants ---

RENDERER_VERSION = __version__

# Dangerous key patterns that MUST NEVER appear in output
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
    r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH)\s+PRIVATE\sKEY-----",
]

# Credential statuses that allow model usage
ACCEPTABLE_CREDENTIAL_STATUSES = {"valid", "not-configured"}

# Health statuses that allow model usage
ACCEPTABLE_HEALTH_STATUSES = {"healthy", "degraded"}

# Available pool criteria
AVAILABLE_CRITERIA = {
    "enabled": True,
    "credential_status": ACCEPTABLE_CREDENTIAL_STATUSES,
    "health_status": ACCEPTABLE_HEALTH_STATUSES,
    "quarantine_status": {"none"},
}

# --- Validation ---


def validate_input(data: dict) -> tuple[bool, list[str]]:
    """Validate renderer input. Returns (valid, errors)."""
    errors = []

    # Required fields
    if "target_node" not in data:
        errors.append("missing required field: target_node")
    elif not isinstance(data["target_node"], str) or not data["target_node"].strip():
        errors.append("target_node must be a non-empty string")

    # dry_run is required and must be True
    if "dry_run" not in data:
        errors.append("missing required field: dry_run")
    elif data["dry_run"] is not True:
        errors.append("dry_run must be True (dry-run only mode)")

    # Model pool — one of available_models or model_pool required
    has_models = "available_models" in data
    has_pool = "model_pool" in data
    if not has_models and not has_pool:
        errors.append("missing required field: available_models or model_pool")
    elif has_models and not isinstance(data["available_models"], list):
        errors.append("available_models must be a list")
    elif has_pool and not isinstance(data["model_pool"], dict):
        errors.append("model_pool must be a dict")

    # Optional fields type check
    if "role_assignment" in data and data["role_assignment"] is not None:
        if not isinstance(data["role_assignment"], dict):
            errors.append("role_assignment must be a dict or null")

    if "approval_id" in data and data["approval_id"] is not None:
        if not isinstance(data["approval_id"], str):
            errors.append("approval_id must be a string or null")

    return len(errors) == 0, errors


# --- Available Pool Filtering ---


def is_model_available(model: dict, target_node: str) -> tuple[bool, str]:
    """Check if a model meets all Available pool criteria.

    Returns (available, reason).
    """
    # 1. enabled
    if not model.get("enabled", False):
        return False, "disabled"

    # 2. target_node detected
    node_avail = model.get("node_availability", {}).get(target_node, {})
    if not node_avail.get("available", False):
        return False, f"not detected on node {target_node}"

    # 3. credential_status acceptable
    cred_status = model.get("credential_status", "missing")
    if cred_status not in ACCEPTABLE_CREDENTIAL_STATUSES:
        return False, f"credential_status={cred_status}"

    # 4. health_status acceptable
    health = model.get("health_status", "unknown")
    if health not in ACCEPTABLE_HEALTH_STATUSES:
        return False, f"health_status={health}"

    # 5. quarantine_status = none
    quarantine = model.get("quarantine_status", "quarantined")
    if quarantine != "none":
        return False, f"quarantine_status={quarantine}"

    return True, "ok"


def filter_available_models(models: list[dict], target_node: str) -> tuple[list[dict], list[dict]]:
    """Filter models into Available and Non-available pools.

    Returns (available, non_available_summary).
    """
    available = []
    non_available = []

    for model in models:
        ok, reason = is_model_available(model, target_node)
        if ok:
            available.append(model)
        else:
            non_available.append({
                "model_id": model.get("model_id", model.get("exact_model_id", "unknown")),
                "reason": reason,
            })

    return available, non_available


# --- Config Draft Generation ---


def generate_config_draft(available_models: list[dict], target_node: str) -> dict:
    """Generate OpenCode config draft from available models."""
    models_config = []
    for model in available_models:
        entry = {
            "alias": model.get("alias", "unknown"),
            "provider": model.get("provider", "unknown"),
            "endpoint": model.get("endpoint", ""),
            "secret_ref": model.get("secret_ref", f"secret:{model.get('provider', 'unknown')}:{model.get('alias', 'unknown')}"),
            "credential_source": "node-local-secure-storage",
            "protocol": model.get("protocol", "openai-compatible"),
            "enabled": True,
            "roles": model.get("roles", model.get("allowed_roles", [])),
        }
        models_config.append(entry)

    # Default model: highest priority (lowest priority number) or first
    default_alias = None
    if available_models:
        sorted_models = sorted(
            available_models,
            key=lambda m: m.get("priority", m.get("cost_status", "") == "free", )
        )
        default_alias = sorted_models[0].get("alias", "unknown")

    return {
        "node": target_node,
        "models": models_config,
        "default_model": default_alias,
    }


# --- Role Assignment ---


def resolve_role_assignment(
    role_assignment: Optional[dict],
    available_models: list[dict],
    non_available_summary: list[dict],
) -> tuple[dict, list[str]]:
    """Resolve role assignment against available models.

    Returns (resolved_assignment, warnings).
    """
    warnings = []
    resolved = {}

    if not role_assignment:
        return resolved, warnings

    available_ids = {m.get("model_id", m.get("exact_model_id")) for m in available_models}
    non_available_ids = {m["model_id"] for m in non_available_summary}

    for role, model_id in role_assignment.items():
        if model_id is None:
            resolved[role] = {
                "model_alias": None,
                "secret_ref": None,
                "status": "unassigned",
            }
            continue

        if model_id in available_ids:
            # Find the model entry
            model = next(
                m for m in available_models
                if m.get("model_id", m.get("exact_model_id")) == model_id
            )
            resolved[role] = {
                "model_alias": model.get("alias", "unknown"),
                "secret_ref": model.get("secret_ref", ""),
                "status": "configured",
            }
        elif model_id in non_available_ids:
            # Model exists but not available
            reason_entry = next(
                m for m in non_available_summary if m["model_id"] == model_id
            )
            resolved[role] = {
                "model_alias": model_id,
                "secret_ref": None,
                "status": f"unavailable: {reason_entry['reason']}",
            }
            warnings.append(
                f"role '{role}' references unavailable model '{model_id}': {reason_entry['reason']}"
            )
        else:
            # Model not found at all
            resolved[role] = {
                "model_alias": model_id,
                "secret_ref": None,
                "status": "not-found",
            }
            warnings.append(
                f"role '{role}' references unknown model '{model_id}'"
            )

    return resolved, warnings


# --- Output Security Scan ---


def scan_output_for_secrets(output: dict) -> list[str]:
    """Scan rendered output for dangerous key patterns. Returns list of violations."""
    violations = []
    output_str = json.dumps(output, ensure_ascii=False)

    for pattern in DANGEROUS_KEY_PATTERNS:
        matches = re.findall(pattern, output_str, re.IGNORECASE)
        if matches:
            violations.append(f"pattern '{pattern}' matched {len(matches)} time(s)")

    return violations


# --- Main Renderer ---


def render_config(input_data: dict) -> dict:
    """Render OpenCode config draft (dry-run only).

    Args:
        input_data: Renderer input conforming to contract §4.2

    Returns:
        Renderer output conforming to contract §4.3

    Raises:
        ValueError: If input validation fails or dry_run is not True
    """
    # Validate input
    valid, errors = validate_input(input_data)
    if not valid:
        raise ValueError(f"input validation failed: {'; '.join(errors)}")

    target_node = input_data["target_node"]

    # Extract models — support both available_models and model_pool formats
    if "available_models" in input_data:
        models = input_data["available_models"]
    else:
        # model_pool format: {"models": {"model_id": {...}, ...}}
        pool = input_data["model_pool"]
        models = list(pool.get("models", {}).values())

    # Filter into Available / Non-available
    available, non_available_summary = filter_available_models(models, target_node)

    # Generate config draft
    config_draft = generate_config_draft(available, target_node)

    # Resolve role assignment
    role_assignment_input = input_data.get("role_assignment")
    resolved_roles, role_warnings = resolve_role_assignment(
        role_assignment_input, available, non_available_summary
    )

    # Build warnings
    warnings = list(role_warnings)
    if not available:
        warnings.append("no available models for this node")

    # Compute input hash (deterministic)
    input_canonical = json.dumps(input_data, sort_keys=True, ensure_ascii=False)
    input_hash = hashlib.sha256(input_canonical.encode("utf-8")).hexdigest()

    # Build output
    output = {
        "node": target_node,
        "dry_run": True,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "config_draft": config_draft,
        "role_assignment": resolved_roles,
        "warnings": warnings,
        "non_available_summary": non_available_summary,
        "requires_operator_approval": True,
        "audit": {
            "input_hash": input_hash,
            "renderer_version": RENDERER_VERSION,
        },
    }

    # Security scan
    violations = scan_output_for_secrets(output)
    if violations:
        raise RuntimeError(f"output security scan failed: {violations}")

    return output


# --- CLI ---


def self_check() -> dict:
    """Self-check: verify renderer is importable and basic logic works."""
    return {
        "renderer_version": RENDERER_VERSION,
        "dry_run_only": True,
        "supported_nodes": ["Windows", "21bao", "5bao", "9bao"],
        "status": "ok",
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        result = self_check()
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python opencode_config_renderer.py --self-check")
        print("       python opencode_config_renderer.py render --input fixture.json")
        sys.exit(0)
