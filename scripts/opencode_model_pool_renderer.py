#!/usr/bin/env python3
"""Model Pool → Renderer Integration — Dry-run Only v1.0.0

Bridges opencode_model_pool.py (sanitized export) with
opencode_config_renderer.py (per-node config draft generation).

Operates in DRY-RUN MODE ONLY — no provider discovery, no node write,
no OpenCode/API calls, no real key exposure.

Usage:
    python scripts/opencode_model_pool_renderer.py --self-check
    python scripts/opencode_model_pool_renderer.py render --node 21bao
    python scripts/opencode_model_pool_renderer.py render --node 5bao --source seed
    python scripts/opencode_model_pool_renderer.py render --node 9bao --source file --pool-path .opencode_model_pool.json

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

# Add scripts to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from opencode_config_renderer import render_config
from opencode_model_pool import KNOWN_QUARANTINE, KNOWN_MODELS_SEED, ModelPool

# --- Constants ---

INTEGRATION_VERSION = __version__

# Dangerous key patterns — must never appear in output
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


# --- Enrichment ---


def enrich_model_entry(entry: dict) -> dict:
    """Enrich a pool model entry with fields required by the renderer.

    Conservative approach:
    - credential_status: use existing if present; otherwise infer cautiously
    - quarantine_status: map from KNOWN_QUARANTINE; default "none"
    - secret_ref: generate placeholder from provider+alias
    - protocol: default "openai-compatible"
    - endpoint: use existing or empty string (placeholder)
    """
    enriched = dict(entry)  # shallow copy

    # model_id normalization: pool uses exact_model_id, renderer uses model_id
    if "model_id" not in enriched:
        enriched["model_id"] = enriched.get("exact_model_id", "unknown")

    # quarantine_status: from KNOWN_QUARANTINE or default "none"
    if "quarantine_status" not in enriched:
        model_id = enriched.get("model_id", enriched.get("exact_model_id", ""))
        if model_id in KNOWN_QUARANTINE:
            enriched["quarantine_status"] = "quarantined"
        else:
            enriched["quarantine_status"] = "none"

    # credential_status: conservative
    if "credential_status" not in enriched:
        source_flags = set(enriched.get("source_flags", []))
        cost_tag = enriched.get("cost_tag", "unknown")

        if "opencode-free" in source_flags or "opencode_discovered" in source_flags:
            # Free/discovered models don't need credentials
            enriched["credential_status"] = "not-configured"
        elif cost_tag == "free":
            # Free models generally don't need credentials
            enriched["credential_status"] = "not-configured"
        else:
            # Paid/user_configured: we don't know if credentials are valid
            # Conservative: mark as missing so it goes to non_available_summary
            # unless the entry explicitly says otherwise
            enriched["credential_status"] = "missing"

    # secret_ref: generate placeholder if not present
    if "secret_ref" not in enriched:
        provider = enriched.get("provider", "unknown")
        alias = enriched.get("alias", enriched.get("model_id", "unknown"))
        enriched["secret_ref"] = f"secret:{provider}:{alias}"

    # protocol: default
    if "protocol" not in enriched:
        enriched["protocol"] = "openai-compatible"

    # endpoint: placeholder if not present
    if "endpoint" not in enriched:
        enriched["endpoint"] = ""

    # allowed_roles: alias for roles if not present
    if "allowed_roles" not in enriched:
        enriched["allowed_roles"] = enriched.get("roles", [])

    return enriched


def enrich_model_list(models: list[dict]) -> tuple[list[dict], list[str]]:
    """Enrich a list of model entries. Returns (enriched_models, enrichment_applied)."""
    enrichment_applied = set()
    enriched = []

    for entry in models:
        original_keys = set(entry.keys())
        enriched_entry = enrich_model_entry(entry)
        new_keys = set(enriched_entry.keys()) - original_keys
        enrichment_applied.update(new_keys)
        enriched.append(enriched_entry)

    return enriched, sorted(enrichment_applied)


# --- Data Sources ---


def load_from_seed() -> list[dict]:
    """Load models from KNOWN_MODELS_SEED (static, no discovery)."""
    return list(KNOWN_MODELS_SEED)


def load_from_fixture(fixture_models: list[dict]) -> list[dict]:
    """Load models from an inline fixture (for testing)."""
    return list(fixture_models)


def load_from_file(pool_path: str) -> tuple[list[dict], Optional[str]]:
    """Load models from a pool JSON snapshot file (read-only)."""
    if not os.path.exists(pool_path):
        raise FileNotFoundError(f"pool file not found: {pool_path}")

    with open(pool_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Support both export_sanitized format (dict of models) and flat list
    if isinstance(data.get("models"), dict):
        models = list(data["models"].values())
    elif isinstance(data.get("models"), list):
        models = data["models"]
    else:
        raise ValueError(f"unrecognized pool format in {pool_path}")

    snapshot_sha256 = data.get("snapshot_sha256")
    return models, snapshot_sha256


# --- Main Integration ---


def render_from_pool(
    target_node: str,
    source: str = "seed",
    pool_path: Optional[str] = None,
    fixture_models: Optional[list[dict]] = None,
    role_assignment: Optional[dict] = None,
    approval_id: Optional[str] = None,
    dry_run: bool = True,
) -> dict:
    """Render per-node config draft from model pool data.

    Args:
        target_node: Target node for config generation
        source: Data source — "seed", "fixture", or "file"
        pool_path: Path to pool JSON file (when source="file")
        fixture_models: Inline model list (when source="fixture")
        role_assignment: Optional role→model mapping
        approval_id: Optional approval identifier
        dry_run: Must be True

    Returns:
        Integration output with renderer_output embedded

    Raises:
        ValueError: If dry_run is not True or input is invalid
    """
    # --- Validate ---
    if dry_run is not True:
        raise ValueError("dry_run must be True (integration is dry-run only)")

    if not target_node or not isinstance(target_node, str):
        raise ValueError("target_node must be a non-empty string")

    if source not in ("seed", "fixture", "file"):
        raise ValueError(f"source must be 'seed', 'fixture', or 'file', got '{source}'")

    # --- Load models from source ---
    pool_snapshot_sha256 = None

    if source == "seed":
        raw_models = load_from_seed()
    elif source == "fixture":
        if fixture_models is None:
            raise ValueError("fixture_models required when source='fixture'")
        raw_models = load_from_fixture(fixture_models)
    elif source == "file":
        if pool_path is None:
            raise ValueError("pool_path required when source='file'")
        raw_models, pool_snapshot_sha256 = load_from_file(pool_path)

    # --- Enrich models ---
    enriched_models, enrichment_applied = enrich_model_list(raw_models)

    # --- Build renderer input ---
    renderer_input = {
        "target_node": target_node,
        "available_models": enriched_models,
        "dry_run": True,
    }

    if role_assignment:
        renderer_input["role_assignment"] = role_assignment

    if approval_id:
        renderer_input["approval_id"] = approval_id

    # --- Call renderer ---
    renderer_output = render_config(renderer_input)

    # --- Build integration output ---
    output = {
        "integration": {
            "source": source,
            "pool_snapshot_sha256": pool_snapshot_sha256,
            "pool_model_count": len(raw_models),
            "enrichment_applied": enrichment_applied,
            "integration_version": INTEGRATION_VERSION,
        },
        "renderer_output": renderer_output,
        "dry_run": True,
        "requires_operator_approval": True,
    }

    # --- Security scan ---
    violations = scan_output_for_secrets(output)
    if violations:
        raise RuntimeError(f"output security scan failed: {violations}")

    return output


# --- Security ---


def scan_output_for_secrets(output: dict) -> list[str]:
    """Scan output for dangerous key patterns."""
    violations = []
    output_str = json.dumps(output, ensure_ascii=False)

    for pattern in DANGEROUS_KEY_PATTERNS:
        matches = re.findall(pattern, output_str, re.IGNORECASE)
        if matches:
            violations.append(f"pattern '{pattern}' matched {len(matches)} time(s)")

    return violations


# --- CLI ---


def self_check() -> dict:
    """Self-check: verify integration is importable."""
    return {
        "integration_version": INTEGRATION_VERSION,
        "dry_run_only": True,
        "supported_sources": ["seed", "fixture", "file"],
        "supported_nodes": ["Windows", "21bao", "5bao", "9bao"],
        "status": "ok",
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        result = self_check()
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python opencode_model_pool_renderer.py --self-check")
        print("       python opencode_model_pool_renderer.py render --node 21bao")
        sys.exit(0)
