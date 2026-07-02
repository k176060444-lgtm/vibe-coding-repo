#!/usr/bin/env python3
"""
VibeDev Model Resolver — call-time central pool resolution (Phase 3 PR-2).

Pure function, no side effects, no SSH, no model call, no credential read.
Reads central model_pool.yaml and node_model_capability.yaml to resolve
model_ref (alias / primary_alias / model_id) into a model entry, respecting
lifecycle_status gate, node constraints, and readiness states.

=== Design (Phase 2 §1) ===
- Produces resolution_receipt with audit-safe fields (no secret value)
- Blocks on disallowed lifecycle_status with explicit reason
- Blocks on unknown model_ref
- Blocks on node mismatch
- No wildcard/empty resolution
- No silent fallback
"""

import hashlib
import sys
import json
import yaml
from pathlib import Path
from datetime import datetime, timezone
from collections import OrderedDict

# ── Constants ──────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
POOL_PATH = SCRIPT_DIR / "model_pool.yaml"
NMC_PATH = SCRIPT_DIR / "node_model_capability.yaml"

VALID_NODES = frozenset({"21bao", "5bao", "9bao"})

# lifecycle_status values that permit resolution (must be explicit, fail-closed)
ALLOWED_LIFECYCLE_STATUSES = frozenset({"operator_requested", "enabled_assigned"})

# lifecycle_status values that are blocked with specific reasons
BLOCKED_LIFECYCLE_REASONS = {
    "declared_enabled_unassigned": (
        "provider/model scope: D-B decision pending; "
        "model is declared_enabled_unassigned (allowed_nodes=[]; "
        "operator decision required before resolution)"
    ),
    "candidate": (
        "model is in candidate mode; not enabled and not assigned "
        "to any node (D-A decision pending)"
    ),
    "disabled": "model is disabled explicitly; no resolution possible",
    "historical": "model is historical/retired; no resolution possible",
    "remove_pending": "model is pending removal from pool; no resolution possible",
    "required": "required lifecycle_status not assigned to any model; no-op",
}

# Implicit classification rules (for v1.1 backward compat: no lifecycle_status)
IMPLICIT_CANDIDATE_NS = frozenset({"volcengine", "deepseek-plan", "minimax-plan"})
IMPLICIT_HISTORICAL_PROVIDERS = frozenset({"xiaomi", "minimax"})


def _implicit_status(model: dict) -> str | None:
    """Determine implicit lifecycle_status for v1.1 backward compat.

    Used only when lifecycle_status field is absent from a model entry.
    Mimics model_pool_manager.auto_classify() but self-contained.
    """
    mid = model.get("id", "")
    enabled = bool(model.get("enabled", False))
    allowed_nodes = model.get("allowed_nodes") or []
    cp = model.get("canonical_provider", "")

    # The only explicit operator_requested model
    if mid == "opencode-go-mimo-v2-5":
        return "operator_requested"

    if enabled:
        return "enabled_assigned" if allowed_nodes else "declared_enabled_unassigned"

    ns = model.get("provider_namespace", "")
    if ns in IMPLICIT_CANDIDATE_NS or cp in IMPLICIT_CANDIDATE_NS:
        return "candidate"
    if ns == "opencode" or cp == "opencode":
        return "remove_pending"
    if cp in IMPLICIT_HISTORICAL_PROVIDERS:
        return "historical"
    return "disabled"


# ── Public API ─────────────────────────────────────────────────────────────


def resolve_model(
    model_ref: str,
    node: str,
    pool: dict | None = None,
    nmc: dict | None = None,
) -> dict:
    """Resolve model_ref to a model entry from the central pool.

    Pure function. No SSH, no model call, no credential read, no side-effects.

    Args:
        model_ref: model_id, alias, or primary_alias to resolve.
        node:      21bao, 5bao, or 9bao.
        pool:      Pre-loaded model_pool dict (optional; loaded from POOL_PATH if None).
        nmc:       Pre-loaded node_model_capability dict (optional).

    Returns:
        resolution_receipt dict with resolved fields or blocked_reason.

    Raises:
        ValueError: If pool or nmc is not loadable.
    """
    # --- Load data ---
    if pool is None:
        pool = _load_yaml(POOL_PATH)
    if nmc is None:
        nmc = _load_yaml(NMC_PATH)

    # Generate deterministic resolution ID
    resolution_id = _generate_resolution_id(model_ref, node)

    # --- Validate node ---
    if node not in VALID_NODES:
        return _blocked(resolution_id, model_ref, node,
                        f"invalid node '{node}': must be one of {sorted(VALID_NODES)}")

    # --- Validate model_ref ---
    if not model_ref or not isinstance(model_ref, str) or len(model_ref.strip()) == 0:
        return _blocked(resolution_id, model_ref, node,
                        "model_ref must be a non-empty string; wildcard/empty resolution blocked")

    model_ref_clean = model_ref.strip()

    # --- Build resolution index ---
    models = pool.get("models", [])
    model_entry, resolved_by = _find_model_entry(models, model_ref_clean)
    if model_entry is None:
        return _blocked(resolution_id, model_ref_clean, node,
                        f"model_ref '{model_ref_clean}' not found in central pool "
                        f"(checked id, aliases, and primary_aliases)")

    resolved_model_id = model_entry["id"]

    # --- Check lifecycle_status ---
    lifecycle_status = model_entry.get("lifecycle_status")
    if lifecycle_status is None or lifecycle_status == "":
        # v1.1 backward compat: auto-classify
        lifecycle_status = _implicit_status(model_entry)

    if lifecycle_status not in ALLOWED_LIFECYCLE_STATUSES:
        reason = BLOCKED_LIFECYCLE_REASONS.get(
            lifecycle_status,
            f"lifecycle_status '{lifecycle_status}' does not permit resolution"
        )
        return _blocked(resolution_id, model_ref_clean, node, reason,
                        lifecycle_status=lifecycle_status)

    # --- Find matrix entry for node ---
    matrix_entry = _find_matrix_entry(nmc, node, resolved_model_id)

    # --- Build receipt ---
    receipt = {
        "resolved": True,
        "resolution_id": resolution_id,
        "requested_alias": model_ref_clean,
        "resolved_model_id": resolved_model_id,
        "resolved_by": resolved_by,
        "node": node,
        "provider_namespace": model_entry.get("provider_namespace", ""),
        "canonical_provider": model_entry.get("canonical_provider", ""),
        "lifecycle_status": lifecycle_status,
        "endpoint_ref": model_entry.get("base_url_env", ""),
        "secret_ref": model_entry.get("key_env", ""),
        "readiness_states": {},
        "blocked_reason": None,
        "resolved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Fill readiness states from matrix (if available)
    if matrix_entry:
        for state_field in [
            "declared", "synced", "wrapper_valid",
            "runtime_visible", "env_loaded",
            "model_call_verified", "operator_approved",
        ]:
            val = matrix_entry.get(state_field, "unknown")
            receipt["readiness_states"][state_field] = val
    else:
        receipt["readiness_states"] = {"node_match": "missing"}
        receipt["blocked_reason"] = (
            f"model '{resolved_model_id}' not found in node '{node}' matrix entry"
        )
        receipt["resolved"] = False

    return receipt


# ── Internal helpers (all pure, no side effects) ───────────────────────────


def _load_yaml(path: Path) -> dict:
    """Load a YAML file. Raises ValueError on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"{path} is not a valid YAML dict")
        return data
    except FileNotFoundError:
        raise ValueError(f"file not found: {path}")
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse error in {path}: {e}")


def _generate_resolution_id(model_ref: str, node: str) -> str:
    """Deterministic resolution ID from inputs."""
    raw = f"{model_ref}@{node}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:12]
    return f"rsv_{h}"


def _find_model_entry(models: list[dict], ref: str) -> tuple[dict | None, str]:
    """Find model entry by model_id, alias, or primary_alias.

    Returns (model_entry, resolved_by: 'model_id' | 'alias' | 'primary_alias' | None).
    """
    # 1. Exact model_id
    for m in models:
        if m.get("id") == ref:
            return m, "model_id"

    # 2. Alias (from alias list)
    for m in models:
        for alias in (m.get("alias") or []):
            if alias == ref:
                return m, "alias"

    # 3. Primary alias
    for m in models:
        if m.get("primary_alias") == ref:
            return m, "primary_alias"

    return None, "not_found"


def _find_matrix_entry(nmc: dict, node: str, model_id: str) -> dict | None:
    """Find model_id in node's matrix within node_model_capability."""
    nd = nmc.get("nodes", {}).get(node)
    if not nd:
        return None
    for e in nd.get("matrix", []):
        if e.get("model_id") == model_id:
            return e
    return None


def _blocked(
    resolution_id: str,
    model_ref: str,
    node: str,
    reason: str,
    lifecycle_status: str | None = None,
) -> dict:
    """Build a blocked resolution receipt."""
    receipt = {
        "resolved": False,
        "resolution_id": resolution_id,
        "requested_alias": model_ref,
        "resolved_model_id": None,
        "resolved_by": "blocked",
        "node": node,
        "provider_namespace": None,
        "canonical_provider": None,
        "lifecycle_status": lifecycle_status,
        "endpoint_ref": None,
        "secret_ref": None,
        "readiness_states": {},
        "blocked_reason": reason,
        "resolved_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return receipt


# ── Self-check ──────────────────────────────────────────────────────────────


def self_check() -> dict:
    """Verify resolver is importable and basic logic works."""
    checks = []

    # Load pool
    try:
        pool = _load_yaml(POOL_PATH)
        models = pool.get("models", [])
        checks.append({"name": "pool_loaded", "passed": len(models) > 0,
                        "detail": f"{len(models)} models"})
    except ValueError as e:
        checks.append({"name": "pool_loaded", "passed": False, "detail": str(e)})

    # Load NMC
    try:
        nmc = _load_yaml(NMC_PATH)
        nodes = list(nmc.get("nodes", {}).keys())
        checks.append({"name": "nmc_loaded", "passed": len(nodes) > 0,
                        "detail": f"nodes={nodes}"})
    except ValueError as e:
        checks.append({"name": "nmc_loaded", "passed": False, "detail": str(e)})

    # Resolve a known model
    try:
        result = resolve_model("opencode-go-mimo-v2-5", "21bao")
        checks.append({"name": "resolve_known", "passed": result["resolved"],
                        "detail": f"model_id={result.get('resolved_model_id')}"})
    except Exception as e:
        checks.append({"name": "resolve_known", "passed": False, "detail": str(e)})

    # Resolve unknown alias → blocked
    try:
        result = resolve_model("nonexistent-model-xyz", "21bao")
        checks.append({"name": "resolve_unknown_blocked",
                        "passed": not result["resolved"],
                        "detail": result.get("blocked_reason", "?")})
    except Exception as e:
        checks.append({"name": "resolve_unknown_blocked", "passed": False, "detail": str(e)})

    # No secret leak in output
    try:
        result = resolve_model("opencode-go-mimo-v2-5", "21bao")
        output_str = json.dumps(result)
        leaked = any(pattern in output_str for pattern in ["sk-", "key_value", "secret_value"])
        checks.append({"name": "no_secret_leak", "passed": not leaked,
                        "detail": "ok" if not leaked else "SECRET LEAK DETECTED"})
    except Exception as e:
        checks.append({"name": "no_secret_leak", "passed": False, "detail": str(e)})

    all_pass = all(c["passed"] for c in checks)
    return {
        "status": "PASS" if all_pass else "FAIL",
        "version": "1.0.0",
        "checks": checks,
        "detail": f"{sum(1 for c in checks if c['passed'])}/{len(checks)} passed",
    }


# ── CLI ────────────────────────────────────────────────────────────────────


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "PASS" else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "resolve":
        if len(sys.argv) < 4:
            print("Usage: python vibe_model_resolver.py resolve <model_ref> <node>")
            sys.exit(1)
        model_ref = sys.argv[2]
        node = sys.argv[3]
        result = resolve_model(model_ref, node)
        print(json.dumps(result, indent=2))
    else:
        print("Usage:")
        print("  python vibe_model_resolver.py --self-check")
        print("  python vibe_model_resolver.py resolve <model_ref> <node>")
        sys.exit(0)


if __name__ == "__main__":
    main()
