#!/usr/bin/env python3
"""vibe_role_assignment_gate.py — Workflow Role Assignment Gate v1.0.0

Enforces that every coding PR/workflow starts with a complete role/model/node
plan.  Execution is blocked until the operator confirms the assignment matrix.

Hard requirements (V1.21.2):
  1. Every coding PR must have a reviewer.
  2. Medium/high-risk / upstream / security / admin / credential /
     command-execution / permission-related PRs must recommend two independent
     reviewers where possible.
  3. Tester/checker must be an explicit role.  The main agent may only act as
     tester if the operator explicitly approves that assignment.
  4. Role architecture is recommended based on task size/risk.
  5. Each role assignment must include: role, node, model, provider, cost_tag,
     reason, call_budget, fallback_policy.
  6. Operator must approve the assignment matrix before live model calls.
  7. Final report must include planned vs actual ledger.

Usage:
    python scripts/vibe_role_assignment_gate.py --self-check
    python scripts/vibe_role_assignment_gate.py validate --matrix MATRIX_JSON
    python scripts/vibe_role_assignment_gate.py recommend --risk low --task-type coding
    python scripts/vibe_role_assignment_gate.py recommend --risk high --tags upstream,admin
"""

__version__ = "1.1.0"

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import List, Optional

# ── Constants ──────────────────────────────────────────────────────────

VALID_RISK_LEVELS = {"low", "medium", "high", "critical"}
VALID_ROLES = {
    "implementer", "reviewer", "reviewer-1", "reviewer-2",
    "tester", "checker", "tester-checker",
    "docs-helper", "planner", "smoke",
}
# v1.0.0 baseline (8 fields). Kept for backward compatibility — v1.0.0 callers
# (vibe_execution_gate.py, vibe_wo_compiler.py) still pass matrices without
# the v1.1.0 fields and must not be broken.
REQUIRED_ASSIGNMENT_FIELDS = [
    "role", "node", "model", "provider",
    "cost_tag", "reason", "call_budget", "fallback_policy",
]
# v1.1.0 spec §4.2 (Baseline02 Stage 2) requires 7 additional fields per
# assignment_receipt. When present in an entry, they are validated by
# validate_assignment_entry_v11(). Required only when
# `matrix["spec_version"] >= "1.1.0"` is set OR all entries already declare
# the v1.1.0 fields. Soft-by-default to keep baseline01 callers running.
REQUIRED_ASSIGNMENT_FIELDS_V11 = [
    "assignment_id",
    "provider_namespace",
    "operator_approval_timestamp",
    "operator_approval_signature",
    "node_whitelist_verified",
    "model_pool_source_verified",
    "base_sha",
]
# v1.1.0 union (informational; not enforced as a hard list)
REQUIRED_ASSIGNMENT_FIELDS_FULL = REQUIRED_ASSIGNMENT_FIELDS + REQUIRED_ASSIGNMENT_FIELDS_V11
VALID_FALLBACK_POLICIES = {"disabled", "operator_selects", "same_provider_different_model"}

# v1.1.0: Cluster node whitelist per docs/VIBECODING_RUNTIME_FLOW_SPEC.md §2.
# 21bao = Windows local-exec/control host (NOT a remote worker); 5bao/9bao =
# remote SSH workers. The string "win" is intentionally NOT in this whitelist
# (see spec §2: "21bao IS the Windows local host; cannot be split"). The
# string "main-agent" is preserved for the existing main-agent-as-tester
# behavior (tester role can run on the operator's local agent, which is not a
# cluster node).
CLUSTER_NODE_WHITELIST = {"21bao", "5bao", "9bao"}
LEGACY_AGENT_NODE = "main-agent"  # backwards-compat for main-agent-as-tester
ALLOWED_NODE_VALUES = CLUSTER_NODE_WHITELIST | {LEGACY_AGENT_NODE}

# v1.1.0 strict: spec §2 + operator §3 acceptance criterion. The v1.1.0 strict
# node whitelist is INDEPENDENT from the legacy ALLOWED_NODE_VALUES and only
# contains cluster nodes. main-agent is NOT a cluster node (it is the
# operator's local Hermes agent, see docs/OPERATOR_ORCHESTRATOR_CONTRACT.md
# §2) and is therefore REJECTED by any v1.1.0 strict assignment, regardless
# of role. The legacy v1.0.0 path (validate_assignment_matrix → is_node_whitelisted)
# preserves the main-agent-as-tester behavior for backward compatibility with
# baseline01 callers; v1.1.0 callers must use validate_assignment_matrix_strict
# which routes through is_v11_strict_node_accepted.
V11_STRICT_NODE_WHITELIST = frozenset({"21bao", "5bao", "9bao"})

# v1.1.0: Provider namespace is an enumerated token (spec §4.2). Stage 3
# accepts the values declared in scripts/model_pool.yaml; Stage 4-5 will
# additionally reject `unknown` at the readiness gate (FCR-1 / GAP-L5-1).
VALID_PROVIDER_NAMESPACES_HINT = {
    "opencode", "anthropic", "xiaomi", "volcengine", "minimax",
    "deepseek", "openai", "google", "moonshot", "dashscope", "xai",
    "unknown",  # accepted at Stage 3; rejected at Stage 4-5 readiness
}

# High-risk tags that trigger dual reviewer requirement
DUAL_REVIEWER_TAGS = {
    "upstream", "security", "admin", "credential",
    "command-execution", "permission", "hermes-agent",
}

# ── Spec version detection ─────────────────────────────────────────────

def detect_spec_version(matrix: dict) -> str:
    """Return the spec version the matrix opts into.

    Returns "1.1.0" if the matrix declares `spec_version` >= "1.1.0" OR if
    every assignment entry already carries every v1.1.0 required field.
    Otherwise returns "1.0.0" (soft mode, baseline01 callers).
    """
    declared = (matrix or {}).get("spec_version")
    if isinstance(declared, str) and declared.strip():
        if declared.strip() >= "1.1.0":
            return declared.strip()
    entries = (matrix or {}).get("assignments", [])
    if entries and all(
        all(field in (entry or {}) for field in REQUIRED_ASSIGNMENT_FIELDS_V11)
        for entry in entries
    ):
        return "1.1.0"
    return "1.0.0"

# ── Central model pool (declarations only) ────────────────────────────

_MODEL_POOL_DECL_CACHE: Optional[dict] = None

def _default_model_pool_path() -> str:
    """Return default path to scripts/model_pool.yaml.

    Stage 3 only reads declaration-layer fields. The `key_env` and
    `base_url_env` fields are NEVER resolved or returned.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "model_pool.yaml")


def load_model_pool_declarations(path: Optional[str] = None) -> dict:
    """Load scripts/model_pool.yaml declaration layer (no secret values).

    Returns a dict with:
      - `path`: source path (for diagnostics only)
      - `schema_version`: pool schema version
      - `model_ids`: set[str]  (id values)
      - `aliases`: set[str]    (union of all alias entries; list values expanded)
      - `primary_aliases`: set[str]
      - `canonical_providers`: set[str]
      - `provider_namespaces`: set[str]
      - `models_by_id`: dict[id -> declaration]
      - `models_by_alias`: dict[alias -> declaration]

    CRITICAL: This function NEVER returns `key_env`, `base_url_env`, or any
    field that would require resolving a secret value. The `key_env` field is
    a STRING (env var NAME), not a value — but to enforce the spec invariant
    (no secret read), we strip it from the returned declarations.
    """
    global _MODEL_POOL_DECL_CACHE
    if _MODEL_POOL_DECL_CACHE is not None and (path is None or path == _MODEL_POOL_DECL_CACHE.get("path")):
        return _MODEL_POOL_DECL_CACHE
    target = path or _default_model_pool_path()
    try:
        import yaml  # PyYAML; available in CI / dev venv
    except ImportError as e:
        raise RuntimeError(f"PyYAML required to load model_pool declarations: {e}")
    with open(target, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise RuntimeError(f"model_pool.yaml top-level must be a dict: {target}")
    models = raw.get("models", [])
    if not isinstance(models, list):
        raise RuntimeError(f"model_pool.yaml 'models' must be a list: {target}")

    model_ids = set()
    aliases = set()
    primary_aliases = set()
    canonical_providers = set()
    provider_namespaces = set()
    models_by_id = {}
    models_by_alias = {}
    for m in models:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        if isinstance(mid, str) and mid:
            model_ids.add(mid)
            models_by_id[mid] = {k: v for k, v in m.items() if k not in ("key_env", "base_url_env")}
        al = m.get("alias")
        if isinstance(al, list):
            for a in al:
                if isinstance(a, str) and a:
                    aliases.add(a)
                    models_by_alias[a] = {k: v for k, v in m.items() if k not in ("key_env", "base_url_env")}
        elif isinstance(al, str) and al:
            aliases.add(al)
            models_by_alias[al] = {k: v for k, v in m.items() if k not in ("key_env", "base_url_env")}
        pa = m.get("primary_alias")
        if isinstance(pa, str) and pa:
            primary_aliases.add(pa)
        cp = m.get("canonical_provider")
        if isinstance(cp, str) and cp:
            canonical_providers.add(cp)
        pn = m.get("provider_namespace")
        if isinstance(pn, str) and pn:
            provider_namespaces.add(pn)
    out = {
        "path": target,
        "schema_version": raw.get("schema_version", "unknown"),
        "model_ids": model_ids,
        "aliases": aliases,
        "primary_aliases": primary_aliases,
        "canonical_providers": canonical_providers,
        "provider_namespaces": provider_namespaces,
        "models_by_id": models_by_id,
        "models_by_alias": models_by_alias,
    }
    _MODEL_POOL_DECL_CACHE = out
    return out


def reset_model_pool_cache() -> None:
    """Clear the cached model_pool declarations. For tests only."""
    global _MODEL_POOL_DECL_CACHE
    _MODEL_POOL_DECL_CACHE = None


# ── v1.1.0 helpers ────────────────────────────────────────────────────

HEX_SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# ULID canonical charset (Crockford Base32, excludes I, L, O, U):
# chars = 0123456789ABCDEFGHJKMNPQRSTVWXYZ  (X is allowed at position 23).
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
ULID_CHARSET = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")

def is_valid_ulid(s: str) -> bool:
    return bool(isinstance(s, str) and ULID_RE.match(s))


def is_node_whitelisted(node: str) -> bool:
    """True iff node ∈ {21bao, 5bao, 9bao, main-agent (legacy)}.

    Spec §2: win+21bao is one node; "win" is NOT an accepted cluster node
    string at the RAG level. Use "21bao" for the Windows local-exec/control
    host. main-agent is preserved for main-agent-as-tester (tester role).

    This is the LEGACY v1.0.0 path. For v1.1.0 strict assignments, use
    is_v11_strict_node_accepted() instead — main-agent is NOT accepted
    in v1.1.0 strict (operator §3 acceptance criterion).
    """
    return isinstance(node, str) and node in ALLOWED_NODE_VALUES


def is_v11_strict_node_accepted(node: str) -> bool:
    """True iff node ∈ {21bao, 5bao, 9bao} for v1.1.0 strict assignments.

    Spec §2 + operator §3: v1.1.0 strict assignments only accept cluster
    nodes. main-agent is the operator's local Hermes agent (see
    docs/OPERATOR_ORCHESTRATOR_CONTRACT.md §2) and is NOT a cluster node;
    it is rejected by v1.1.0 strict regardless of role. The legacy v1.0.0
    path (is_node_whitelisted) still accepts main-agent for the
    main-agent-as-tester baseline01 behavior, but v1.1.0 strict callers
    must use this strict whitelist.

    The v1.0.0 callers (e.g. scripts/vibe_execution_gate.py pre-fix) that
    call validate_assignment_matrix() directly are NOT upgraded by this
    function; the EAG-side upgrade is required (see issue #2 corrective).
    """
    return isinstance(node, str) and node in V11_STRICT_NODE_WHITELIST


def is_model_in_pool(model: str, decl: Optional[dict] = None) -> bool:
    """True iff model matches an id, alias, or primary_alias in model_pool.yaml.

    Lookup precedence: id → alias → primary_alias. All case-sensitive.
    Does NOT resolve `key_env`; never returns secret values.
    """
    if not isinstance(model, str) or not model:
        return False
    if decl is None:
        decl = load_model_pool_declarations()
    if model in decl["model_ids"]:
        return True
    if model in decl["aliases"]:
        return True
    if model in decl["primary_aliases"]:
        return True
    return False


def find_pool_model_for(model: str, decl: Optional[dict] = None) -> Optional[dict]:
    """Return the declaration dict for the given model id/alias, or None.

    Returned dict NEVER contains `key_env` or `base_url_env`.
    """
    if not isinstance(model, str) or not model:
        return None
    if decl is None:
        decl = load_model_pool_declarations()
    return (
        decl["models_by_id"].get(model)
        or decl["models_by_alias"].get(model)
    )


def compute_approval_signature(approval_id: str, timestamp: str) -> str:
    """Compute spec §4.2 operator_approval_signature (hex SHA256).

    The signature is a SHA256 hex digest of the approval_id concatenated with
    the timestamp string. This helper exists so callers and tests can produce
    a deterministic value. RAG itself only validates the FORMAT of the
    signature; it does not authenticate identity.
    """
    if not isinstance(approval_id, str) or not isinstance(timestamp, str):
        return ""
    h = hashlib.sha256()
    h.update(approval_id.encode("utf-8"))
    h.update(timestamp.encode("utf-8"))
    return h.hexdigest()

# ── Risk Classification ───────────────────────────────────────────────

def classify_risk(risk_level: str, tags: list = None) -> str:
    """Return effective risk tier: low, medium, high, critical.

    Classification rules:
      - low:     small, self-contained, local-only changes
      - medium:  moderate scope, multiple files, internal tools
      - high:    upstream PRs, security, admin, credentials, permissions
      - critical: production deployment, gateway restart, credential rotation
    """
    tags = set(tags or [])
    risk_level = (risk_level or "low").lower()

    if risk_level == "critical":
        return "critical"
    if risk_level == "high" or tags & DUAL_REVIEWER_TAGS:
        return "high"
    if risk_level == "medium":
        return "medium"
    return "low"


def needs_dual_reviewer(risk_level: str, tags: list = None) -> bool:
    """Check if task requires two independent reviewers."""
    effective = classify_risk(risk_level, tags)
    return effective in ("high", "critical")


# ── Required Roles by Risk ────────────────────────────────────────────

def get_required_roles(risk_level: str, tags: list = None) -> dict:
    """Return required role structure for a given risk level.

    Returns:
        {
            "risk_level": str,
            "effective_risk": str,
            "required_roles": [str],
            "optional_roles": [str],
            "requires_dual_reviewer": bool,
            "main_agent_as_tester_requires_approval": bool,
        }
    """
    effective = classify_risk(risk_level, tags)

    if effective == "low":
        return {
            "risk_level": risk_level,
            "effective_risk": effective,
            "required_roles": ["implementer", "reviewer", "checker"],
            "optional_roles": [],
            "requires_dual_reviewer": False,
            "main_agent_as_tester_requires_approval": True,
        }
    elif effective == "medium":
        return {
            "risk_level": risk_level,
            "effective_risk": effective,
            "required_roles": ["implementer", "reviewer", "tester-checker"],
            "optional_roles": [],
            "requires_dual_reviewer": False,
            "main_agent_as_tester_requires_approval": True,
        }
    else:  # high or critical
        return {
            "risk_level": risk_level,
            "effective_risk": effective,
            "required_roles": ["implementer", "reviewer-1", "reviewer-2", "tester-checker"],
            "optional_roles": ["docs-helper"],
            "requires_dual_reviewer": True,
            "main_agent_as_tester_requires_approval": True,
        }


# ── Role Assignment Schema ────────────────────────────────────────────

def create_role_assignment(
    role: str,
    node: str,
    model: str,
    provider: str,
    cost_tag: str = "",
    reason: str = "",
    call_budget: int = 100,
    fallback_policy: str = "disabled",
) -> dict:
    """Create a single role assignment entry."""
    return {
        "role": role,
        "node": node,
        "model": model,
        "provider": provider,
        "cost_tag": cost_tag,
        "reason": reason,
        "call_budget": call_budget,
        "fallback_policy": fallback_policy,
    }


def create_assignment_matrix(
    risk_level: str,
    tags: list = None,
    task_id: str = "",
    task_type: str = "coding",
) -> dict:
    """Create an empty assignment matrix template for the given risk level."""
    required = get_required_roles(risk_level, tags)
    return {
        "version": __version__,
        "task_id": task_id,
        "task_type": task_type,
        "risk_level": risk_level,
        "effective_risk": required["effective_risk"],
        "tags": tags or [],
        "required_roles": required["required_roles"],
        "optional_roles": required["optional_roles"],
        "requires_dual_reviewer": required["requires_dual_reviewer"],
        "assignments": [],  # to be filled by operator
        "operator_approved": False,
        "operator_approval_timestamp": None,
        "operator_approval_signature": None,
        "main_agent_as_tester_approved": False,
    }


# ── Validation ────────────────────────────────────────────────────────

def validate_assignment_entry(entry: dict, index: int) -> list:
    """Validate a single assignment entry. Returns list of errors."""
    errors = []
    for field in REQUIRED_ASSIGNMENT_FIELDS:
        if field not in entry:
            errors.append(f"assignment[{index}]: missing required field '{field}'")

    # Validate role
    role = entry.get("role", "")
    if role not in VALID_ROLES:
        errors.append(f"assignment[{index}]: invalid role '{role}' (valid: {VALID_ROLES})")

    # Validate fallback_policy
    fb = entry.get("fallback_policy", "")
    if fb not in VALID_FALLBACK_POLICIES:
        errors.append(f"assignment[{index}]: invalid fallback_policy '{fb}'")

    # Validate call_budget
    cb = entry.get("call_budget", 0)
    if not isinstance(cb, int) or cb < 1:
        errors.append(f"assignment[{index}]: call_budget must be positive integer, got {cb}")

    # node, model, provider must be non-empty strings
    for field in ("node", "model", "provider"):
        val = str(entry.get(field, "")).strip()
        if not val:
            errors.append(f"assignment[{index}]: {field} must not be empty")

    return errors


# ── v1.1.0 spec §4.2 entry validation ────────────────────────────────

def validate_assignment_entry_v11(entry: dict, index: int, decl: Optional[dict] = None) -> list:
    """Validate v1.1.0 spec §4.2 fields on an assignment entry.

    Returns a list of human-readable errors. Empty list = no errors.
    Performs ONLY structural and format checks; the gate does not authenticate
    identity. It does NOT block `provider_namespace == "unknown"` (Stage 4-5
    readiness gate concern). It does NOT resolve `key_env` from model_pool.

    Field-level checks (spec §4.2):
      - assignment_id            : required, ULID-format (26 chars Crockford)
      - provider_namespace       : required, non-empty string
      - operator_approval_timestamp : required, ISO-8601 UTC string
      - operator_approval_signature : required, 64-char lowercase hex (sha256)
      - node_whitelist_verified  : required, must be True (bool)
      - model_pool_source_verified: required, must be True (bool)
      - base_sha                 : required, 40-char lowercase hex (sha1)
    Cross-field:
      - node (in v1.0.0 fields)  : must be in {21bao, 5bao, 9bao, main-agent}
      - model (in v1.0.0 fields) : must be in central model_pool (id/alias/primary_alias)
      - if node_whitelist_verified=True, node must also pass is_node_whitelisted
      - if model_pool_source_verified=True, model must also pass is_model_in_pool
    """
    errors = []
    if not isinstance(entry, dict):
        return [f"assignment[{index}]: must be a dict"]

    # assignment_id (ULID)
    aid = entry.get("assignment_id")
    if not aid:
        errors.append(f"assignment[{index}]: missing v1.1.0 required field 'assignment_id'")
    elif not is_valid_ulid(aid):
        errors.append(
            f"assignment[{index}]: assignment_id must be 26-char ULID (Crockford alphabet), got {aid!r}"
        )

    # provider_namespace
    pn = entry.get("provider_namespace")
    if pn is None or pn == "":
        errors.append(f"assignment[{index}]: missing v1.1.0 required field 'provider_namespace'")
    elif not isinstance(pn, str):
        errors.append(f"assignment[{index}]: provider_namespace must be a string, got {type(pn).__name__}")
    # Stage 3 does NOT reject "unknown" here (Stage 4-5 readiness concern).

    # operator_approval_timestamp (ISO-8601)
    ots = entry.get("operator_approval_timestamp")
    if not ots:
        errors.append(f"assignment[{index}]: missing v1.1.0 required field 'operator_approval_timestamp'")
    elif not isinstance(ots, str):
        errors.append(f"assignment[{index}]: operator_approval_timestamp must be ISO-8601 string")
    else:
        # Lenient: accept anything ending in 'Z' or matching YYYY-MM-DDTHH:MM:SS prefix.
        # Strict parsing is left to Stage 4-5 cross-receipt linkage.
        if not (ots.endswith("Z") or re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", ots)):
            errors.append(
                f"assignment[{index}]: operator_approval_timestamp must be ISO-8601 UTC, got {ots!r}"
            )

    # operator_approval_signature (hex SHA256, 64 chars)
    sig = entry.get("operator_approval_signature")
    if not sig:
        errors.append(f"assignment[{index}]: missing v1.1.0 required field 'operator_approval_signature'")
    elif not isinstance(sig, str) or not HEX_SHA256_RE.match(sig):
        errors.append(
            f"assignment[{index}]: operator_approval_signature must be 64-char lowercase hex SHA256, got {sig!r}"
        )

    # node_whitelist_verified (bool True)
    nwv = entry.get("node_whitelist_verified")
    if nwv is None:
        errors.append(f"assignment[{index}]: missing v1.1.0 required field 'node_whitelist_verified'")
    elif nwv is not True:
        errors.append(
            f"assignment[{index}]: node_whitelist_verified must be True (got {nwv!r}) — failure closed"
        )

    # model_pool_source_verified (bool True)
    mpv = entry.get("model_pool_source_verified")
    if mpv is None:
        errors.append(f"assignment[{index}]: missing v1.1.0 required field 'model_pool_source_verified'")
    elif mpv is not True:
        errors.append(
            f"assignment[{index}]: model_pool_source_verified must be True (got {mpv!r}) — failure closed"
        )

    # base_sha (hex SHA1, 40 chars)
    bsha = entry.get("base_sha")
    if not bsha:
        errors.append(f"assignment[{index}]: missing v1.1.0 required field 'base_sha'")
    elif not isinstance(bsha, str) or not HEX_SHA1_RE.match(bsha):
        errors.append(
            f"assignment[{index}]: base_sha must be 40-char lowercase hex SHA1, got {bsha!r}"
        )

    # Cross-field: node must be in v1.1 strict cluster whitelist.
    # v1.1.0 strict (operator §3 acceptance criterion) only accepts
    # {21bao, 5bao, 9bao}. main-agent, win, and any other host string
    # are REJECTED in v1.1 strict regardless of role. The legacy
    # main-agent-as-tester behavior is preserved only on the v1.0.0
    # path (validate_assignment_matrix → is_node_whitelisted).
    node = entry.get("node")
    if isinstance(node, str) and node and not is_v11_strict_node_accepted(node):
        errors.append(
            f"assignment[{index}]: node '{node}' is not in the v1.1.0 strict "
            f"cluster whitelist {sorted(V11_STRICT_NODE_WHITELIST)} "
            f"(spec §2; 'win', 'main-agent', and any other host are rejected "
            f"in v1.1.0 strict regardless of role; main-agent is allowed "
            f"only via the v1.0.0 legacy path)"
        )
    if nwv is True and isinstance(node, str) and node and not is_v11_strict_node_accepted(node):
        # Belt-and-suspenders: even if the boolean was set, the literal node string
        # must match the v1.1 strict whitelist. Mismatch = inconsistency in the entry.
        errors.append(
            f"assignment[{index}]: node_whitelist_verified=True but node '{node}' is not in the v1.1.0 strict cluster whitelist"
        )

    # Cross-field: model must be in central model pool (when source verified)
    model = entry.get("model")
    if mpv is True and isinstance(model, str) and model:
        if not is_model_in_pool(model, decl=decl):
            errors.append(
                f"assignment[{index}]: model_pool_source_verified=True but model '{model}' "
                f"is not in the central model pool (id/alias/primary_alias)"
            )

    return errors


def aggregate_v11_entry_errors(entries: list, decl: Optional[dict] = None) -> list:
    """Run v1.1.0 validation across all entries. Returns flat error list."""
    errors = []
    for i, entry in enumerate(entries or []):
        errors.extend(validate_assignment_entry_v11(entry, i, decl=decl))
    return errors


def validate_assignment_matrix_v11(matrix: dict, decl: Optional[dict] = None) -> dict:
    """Full v1.1.0 entry validation result.

    Always runs (regardless of detect_spec_version result) for transparency.
    When the matrix is in v1.0.0 mode (no spec_version, no v1.1.0 fields in
    entries), the v1.0.0 self-check path remains authoritative. When the
    matrix opts into v1.1.0, v1.0.0 fields still must be present (existing
    REQUIRED_ASSIGNMENT_FIELDS) AND v1.1.0 fields must be present.
    """
    errors = []
    checks = []
    entries = (matrix or {}).get("assignments", [])
    if not entries:
        # No entries → v1.1.0 entry checks are vacuous; defer to v1.0.0 path
        checks.append({
            "name": "v11_entry_validation",
            "result": "PASS",
            "detail": "no entries to validate",
        })
    else:
        v11_errors = aggregate_v11_entry_errors(entries, decl=decl)
        errors.extend(v11_errors)
        if v11_errors:
            checks.append({
                "name": "v11_entry_validation",
                "result": "BLOCK",
                "detail": f"{len(v11_errors)} v1.1.0 field errors",
            })
        else:
            checks.append({
                "name": "v11_entry_validation",
                "result": "PASS",
                "detail": f"all {len(entries)} entries pass v1.1.0 spec §4.2 fields",
            })

    verdict = "BLOCK" if any(c["result"] == "BLOCK" for c in checks) else "ALLOW"
    return {
        "valid": len(errors) == 0,
        "verdict": verdict,
        "errors": errors,
        "checks": checks,
        "summary": {
            "total": len(checks),
            "pass": sum(1 for c in checks if c["result"] == "PASS"),
            "block": sum(1 for c in checks if c["result"] == "BLOCK"),
        },
    }


def validate_assignment_matrix_strict(matrix: dict, decl: Optional[dict] = None) -> dict:
    """Strict v1.1.0 validator. ALWAYS enforces 7 spec §4.2 fields.

    Behavior:
      - For matrices that opt into spec_version >= "1.1.0" OR have all
        v1.1.0 fields present: runs v1.0.0 baseline + v1.1.0 entry checks
        (any v1.1.0 field error → BLOCK).
      - For matrices that do NOT opt in (legacy v1.0.0 form: no
        spec_version, missing v1.1.0 fields): the v1.0.0 path runs, but
        the missing v1.1.0 fields are reported as BLOCK errors (not
        warnings). This is the fail-closed production enforcement per
        Stage 3 corrective (PR #278 acceptance FAIL, issue #2): the
        operator's spec §4.2 mandate applies to ALL production coding
        tasks, including those whose work-order compiler did not yet
        inject spec_version=1.1.0.

    Backward compat note: callers (e.g. scripts/vibe_execution_gate.py)
    that used to call validate_assignment_matrix() will now fail-closed
    for v1.0.0 matrices. The legacy validator remains available for
    pre-production / non-coding-task use; production coding tasks must
    use this strict validator.

    The v1.0.0 callers that cannot import the strict validator (RAG
    < v1.1.0) should be marked as non-production transitional by the
    caller (see EAG `_STRICT_AVAILABLE` flag).
    """
    base = validate_assignment_matrix(matrix)
    entries = (matrix or {}).get("assignments", [])
    spec_version = detect_spec_version(matrix or {})
    v11_entry_errors = aggregate_v11_entry_errors(entries, decl=decl) if entries else []

    if spec_version == "1.1.0":
        # Spec-in: v1.0.0 + v1.1.0 both run. v1.1.0 errors are BLOCKs.
        v11 = validate_assignment_matrix_v11(matrix, decl=decl)
        merged_errors = list(base.get("errors", [])) + list(v11.get("errors", []))
        merged_checks = list(base.get("checks", [])) + list(v11.get("checks", []))
    else:
        # Spec-out (legacy v1.0.0 form): v1.0.0 baseline runs (may pass);
        # missing v1.1.0 fields are reported as BLOCK errors (fail-closed
        # for spec §4.2 compliance). This is the Stage 3 corrective
        # production enforcement: callers cannot bypass v1.1.0 fields
        # by simply omitting them.
        merged_errors = list(base.get("errors", []))
        for v11_err in v11_entry_errors:
            merged_errors.append(f"missing v1.1.0 required field (fail-closed): {v11_err}")
        merged_checks = list(base.get("checks", []))
        if v11_entry_errors:
            merged_checks.append({
                "name": "v11_strict_enforcement",
                "result": "BLOCK",
                "detail": f"{len(v11_entry_errors)} v1.1.0 required field gap(s) — "
                          f"spec §4.2 mandate (Stage 3 corrective, issue #2)",
            })
    verdict = "BLOCK" if any(c["result"] == "BLOCK" for c in merged_checks) else "ALLOW"
    return {
        "valid": len(merged_errors) == 0,
        "verdict": verdict,
        "errors": merged_errors,
        "checks": merged_checks,
        "summary": {
            "total": len(merged_checks),
            "pass": sum(1 for c in merged_checks if c["result"] == "PASS"),
            "block": sum(1 for c in merged_checks if c["result"] == "BLOCK"),
        },
        "spec_version": spec_version,
    }


def validate_assignment_matrix(matrix: dict) -> dict:
    """Validate a complete assignment matrix.

    Returns:
        {
            "valid": bool,
            "errors": [str],
            "warnings": [str],
            "checks": [{name, result, detail}],
        }
    """
    errors = []
    warnings = []
    checks = []

    # Check 1: Has risk_level
    risk = matrix.get("risk_level", "")
    if risk not in VALID_RISK_LEVELS:
        errors.append(f"invalid risk_level: '{risk}'")
        checks.append({"name": "risk_level", "result": "BLOCK", "detail": f"invalid: {risk}"})
    else:
        checks.append({"name": "risk_level", "result": "PASS", "detail": risk})

    # Check 2: Has required roles
    required_roles = matrix.get("required_roles", [])
    if not required_roles:
        errors.append("missing required_roles")
        checks.append({"name": "required_roles", "result": "BLOCK", "detail": "missing"})
    else:
        checks.append({"name": "required_roles", "result": "PASS", "detail": f"{len(required_roles)} roles"})

    # Check 3: Has assignments
    assignments = matrix.get("assignments", [])
    if not assignments:
        errors.append("no assignments provided")
        checks.append({"name": "has_assignments", "result": "BLOCK", "detail": "empty"})
    else:
        checks.append({"name": "has_assignments", "result": "PASS", "detail": f"{len(assignments)} entries"})

    # Check 4: Each assignment entry is valid
    for i, entry in enumerate(assignments):
        entry_errors = validate_assignment_entry(entry, i)
        errors.extend(entry_errors)
    if not errors:
        checks.append({"name": "assignment_entries_valid", "result": "PASS", "detail": "all valid"})
    else:
        checks.append({"name": "assignment_entries_valid", "result": "BLOCK", "detail": f"{len(errors)} errors"})

    # Check 5: Every coding PR must have a reviewer
    has_reviewer = any(
        a.get("role", "").startswith("reviewer")
        for a in assignments
    )
    if not has_reviewer:
        errors.append("BLOCK: no reviewer assigned — every coding PR must have a reviewer")
        checks.append({"name": "has_reviewer", "result": "BLOCK", "detail": "no reviewer"})
    else:
        checks.append({"name": "has_reviewer", "result": "PASS", "detail": "reviewer present"})

    # Check 6: High-risk requires dual reviewer
    requires_dual = matrix.get("requires_dual_reviewer", False)
    reviewer_count = sum(
        1 for a in assignments
        if a.get("role", "").startswith("reviewer")
    )
    if requires_dual and reviewer_count < 2:
        errors.append(
            f"BLOCK: high-risk/critical task requires 2 independent reviewers, "
            f"found {reviewer_count}"
        )
        checks.append({
            "name": "dual_reviewer",
            "result": "BLOCK",
            "detail": f"requires 2, found {reviewer_count}",
        })
    elif requires_dual:
        checks.append({
            "name": "dual_reviewer",
            "result": "PASS",
            "detail": f"{reviewer_count} reviewers",
        })
    else:
        checks.append({
            "name": "dual_reviewer",
            "result": "PASS",
            "detail": f"not required (risk={matrix.get('risk_level')})",
        })

    # Check 7: Tester/checker must be explicit
    has_tester = any(
        a.get("role", "") in ("tester", "checker", "tester-checker")
        for a in assignments
    )
    if not has_tester:
        errors.append("BLOCK: tester/checker must be an explicit role assignment")
        checks.append({"name": "tester_explicit", "result": "BLOCK", "detail": "no tester/checker"})
    else:
        checks.append({"name": "tester_explicit", "result": "PASS", "detail": "tester/checker present"})

    # Check 8: Main agent as tester requires explicit approval
    main_as_tester = any(
        a.get("role", "") in ("tester", "tester-checker")
        and a.get("node", "") == "main-agent"
        for a in assignments
    )
    if main_as_tester and not matrix.get("main_agent_as_tester_approved", False):
        errors.append(
            "BLOCK: main agent assigned as tester but operator has not "
            "explicitly approved this assignment"
        )
        checks.append({
            "name": "main_agent_as_tester",
            "result": "BLOCK",
            "detail": "main-agent-as-tester not approved",
        })
    elif main_as_tester:
        checks.append({
            "name": "main_agent_as_tester",
            "result": "PASS",
            "detail": "operator approved main-agent-as-tester",
        })
    else:
        checks.append({
            "name": "main_agent_as_tester",
            "result": "PASS",
            "detail": "main agent not assigned as tester",
        })

    # Check 9: Operator approval
    if not matrix.get("operator_approved", False):
        errors.append("BLOCK: operator has not approved the assignment matrix")
        checks.append({
            "name": "operator_approved",
            "result": "BLOCK",
            "detail": "not approved",
        })
    else:
        checks.append({
            "name": "operator_approved",
            "result": "PASS",
            "detail": f"approved at {matrix.get('operator_approval_timestamp', '?')}",
        })

    # Determine verdict
    has_block = any(c["result"] == "BLOCK" for c in checks)
    verdict = "BLOCK" if has_block else "ALLOW"

    return {
        "valid": len(errors) == 0,
        "verdict": verdict,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "summary": {
            "total": len(checks),
            "pass": sum(1 for c in checks if c["result"] == "PASS"),
            "block": sum(1 for c in checks if c["result"] == "BLOCK"),
        },
    }


# ── Planned vs Actual Ledger ──────────────────────────────────────────

def generate_planned_vs_actual_ledger(
    matrix: dict,
    actual_entries: list,
) -> dict:
    """Generate planned vs actual comparison ledger.

    Args:
        matrix: The approved assignment matrix (planned).
        actual_entries: List of actual execution records, each with:
            {role, node, model, provider, call_count, duration, exit_code,
             fallback_used, final_status, evidence_path}

    Returns:
        {
            "planned_roles": [...],
            "actual_roles": [...],
            "discrepancies": [...],
            "ledger": [{role, planned_model, actual_model, planned_node,
                       actual_node, planned_provider, actual_provider,
                       match, call_count, duration, exit_code, final_status}],
        }
    """
    planned = {a["role"]: a for a in matrix.get("assignments", [])}
    actual = {a["role"]: a for a in actual_entries}

    all_roles = sorted(set(planned.keys()) | set(actual.keys()))

    ledger = []
    discrepancies = []

    for role in all_roles:
        p = planned.get(role, {})
        a = actual.get(role, {})

        model_match = p.get("model") == a.get("model")
        node_match = p.get("node") == a.get("node")
        provider_match = p.get("provider") == a.get("provider")

        entry = {
            "role": role,
            "planned_model": p.get("model", "N/A"),
            "actual_model": a.get("model", "N/A"),
            "planned_node": p.get("node", "N/A"),
            "actual_node": a.get("node", "N/A"),
            "planned_provider": p.get("provider", "N/A"),
            "actual_provider": a.get("provider", "N/A"),
            "model_match": model_match,
            "node_match": node_match,
            "provider_match": provider_match,
            "call_count": a.get("call_count", 0),
            "duration": a.get("duration", "N/A"),
            "exit_code": a.get("exit_code", None),
            "final_status": a.get("final_status", "N/A"),
        }
        ledger.append(entry)

        if not model_match:
            discrepancies.append(f"{role}: model {p.get('model')} -> {a.get('model')}")
        if not node_match:
            discrepancies.append(f"{role}: node {p.get('node')} -> {a.get('node')}")
        if not provider_match:
            discrepancies.append(f"{role}: provider {p.get('provider')} -> {a.get('provider')}")

    return {
        "planned_roles": sorted(planned.keys()),
        "actual_roles": sorted(actual.keys()),
        "missing_actual": sorted(set(planned.keys()) - set(actual.keys())),
        "extra_actual": sorted(set(actual.keys()) - set(planned.keys())),
        "discrepancies": discrepancies,
        "ledger": ledger,
    }


# ── Self-Check ────────────────────────────────────────────────────────

def self_check() -> dict:
    """Run comprehensive self-check."""
    checks = []
    passed = 0
    total = 0

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal passed, total
        total += 1
        if ok:
            passed += 1
        checks.append({"name": name, "passed": ok, "detail": detail})

    # rag-01: version
    check("rag-01-version", bool(__version__), __version__)

    # rag-02: low risk classification
    check("rag-02-low-risk", classify_risk("low") == "low")

    # rag-03: medium risk classification
    check("rag-03-medium-risk", classify_risk("medium") == "medium")

    # rag-04: high risk classification
    check("rag-04-high-risk", classify_risk("high") == "high")

    # rag-05: tag-based escalation
    check("rag-05-tag-escalation", classify_risk("low", ["upstream"]) == "high")

    # rag-06: dual reviewer needed for high risk
    check("rag-06-dual-reviewer", needs_dual_reviewer("high"))

    # rag-07: dual reviewer not needed for low risk
    check("rag-07-no-dual-low", not needs_dual_reviewer("low"))

    # rag-08: low risk requires reviewer
    req_low = get_required_roles("low")
    check("rag-08-low-has-reviewer", "reviewer" in req_low["required_roles"])

    # rag-09: low risk requires checker
    check("rag-09-low-has-checker", "checker" in req_low["required_roles"])

    # rag-10: medium risk requires tester-checker
    req_med = get_required_roles("medium")
    check("rag-10-med-has-tester-checker", "tester-checker" in req_med["required_roles"])

    # rag-11: high risk requires dual reviewer
    req_high = get_required_roles("high")
    check("rag-11-high-dual-reviewer",
          "reviewer-1" in req_high["required_roles"] and
          "reviewer-2" in req_high["required_roles"])

    # rag-12: high risk has optional docs-helper
    check("rag-12-high-docs-helper", "docs-helper" in req_high["optional_roles"])

    # rag-13: assignment entry validation
    good_entry = create_role_assignment(
        role="implementer", node="21bao",
        model="opencode/deepseek-v4-pro", provider="deepseek",
        cost_tag="implementer-001", reason="code implementation",
        call_budget=100, fallback_policy="disabled",
    )
    entry_errors = validate_assignment_entry(good_entry, 0)
    check("rag-13-good-entry-valid", len(entry_errors) == 0, str(entry_errors))

    # rag-14: bad entry missing role
    bad_entry = {k: v for k, v in good_entry.items() if k != "role"}
    bad_errors = validate_assignment_entry(bad_entry, 0)
    check("rag-14-missing-role-invalid", len(bad_errors) > 0)

    # rag-15: valid matrix with approvals
    matrix = create_assignment_matrix("low", task_id="test-001")
    matrix["assignments"] = [
        create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek",
                               cost_tag="imp-001", reason="implement"),
        create_role_assignment("reviewer", "9bao", "opencode/deepseek-v4-pro", "deepseek",
                               cost_tag="rev-001", reason="review"),
        create_role_assignment("checker", "21bao", "opencode/deepseek-v4-pro", "deepseek",
                               cost_tag="chk-001", reason="check"),
    ]
    matrix["operator_approved"] = True
    matrix["operator_approval_timestamp"] = "2026-06-21T00:00:00Z"
    result = validate_assignment_matrix(matrix)
    check("rag-15-valid-matrix", result["valid"], str(result["errors"]))

    # rag-16: missing reviewer blocks
    matrix_no_rev = dict(matrix)
    matrix_no_rev["assignments"] = [
        create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("checker", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
    ]
    result_no_rev = validate_assignment_matrix(matrix_no_rev)
    check("rag-16-missing-reviewer-blocks", not result_no_rev["valid"])

    # rag-17: high risk needs 2 reviewers
    matrix_high = create_assignment_matrix("high", task_id="test-high")
    matrix_high["assignments"] = [
        create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("reviewer-1", "9bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("reviewer-2", "5bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("tester-checker", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
    ]
    matrix_high["operator_approved"] = True
    matrix_high["operator_approval_timestamp"] = "2026-06-21T00:00:00Z"
    result_high = validate_assignment_matrix(matrix_high)
    check("rag-17-high-dual-reviewer-valid", result_high["valid"], str(result_high["errors"]))

    # rag-18: high risk with 1 reviewer blocks
    matrix_high_1rev = dict(matrix_high)
    matrix_high_1rev["assignments"] = [
        create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("reviewer", "9bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("tester-checker", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
    ]
    result_high_1rev = validate_assignment_matrix(matrix_high_1rev)
    check("rag-18-high-one-reviewer-blocks", not result_high_1rev["valid"])

    # rag-19: missing tester blocks
    matrix_no_tester = dict(matrix)
    matrix_no_tester["assignments"] = [
        create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("reviewer", "9bao", "opencode/deepseek-v4-pro", "deepseek"),
    ]
    result_no_tester = validate_assignment_matrix(matrix_no_tester)
    check("rag-19-missing-tester-blocks", not result_no_tester["valid"])

    # rag-20: main-agent-as-tester requires approval
    matrix_main_tester = create_assignment_matrix("low", task_id="test-main-tester")
    matrix_main_tester["assignments"] = [
        create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("reviewer", "9bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("tester-checker", "main-agent", "hermes/mimo-v2.5-pro", "xiaomi"),
    ]
    matrix_main_tester["operator_approved"] = True
    matrix_main_tester["operator_approval_timestamp"] = "2026-06-21T00:00:00Z"
    # Without main_agent_as_tester_approved
    result_main = validate_assignment_matrix(matrix_main_tester)
    check("rag-20-main-tester-blocks-without-approval", not result_main["valid"])

    # rag-21: main-agent-as-tester with approval
    matrix_main_tester_approved = dict(matrix_main_tester)
    matrix_main_tester_approved["main_agent_as_tester_approved"] = True
    result_main_ok = validate_assignment_matrix(matrix_main_tester_approved)
    check("rag-21-main-tester-allowed-with-approval", result_main_ok["valid"])

    # rag-22: unapproved matrix blocks
    matrix_unapproved = dict(matrix)
    matrix_unapproved["operator_approved"] = False
    result_unapp = validate_assignment_matrix(matrix_unapproved)
    check("rag-22-unapproved-blocks", not result_unapp["valid"])

    # rag-23: planned vs actual ledger
    actual = [
        {"role": "implementer", "node": "21bao", "model": "opencode/deepseek-v4-pro",
         "provider": "deepseek", "call_count": 5, "duration": "30s", "exit_code": 0,
         "final_status": "PASS"},
        {"role": "reviewer", "node": "9bao", "model": "opencode/deepseek-v4-pro",
         "provider": "deepseek", "call_count": 2, "duration": "10s", "exit_code": 0,
         "final_status": "PASS"},
        {"role": "checker", "node": "21bao", "model": "opencode/deepseek-v4-pro",
         "provider": "deepseek", "call_count": 1, "duration": "5s", "exit_code": 0,
         "final_status": "PASS"},
    ]
    ledger = generate_planned_vs_actual_ledger(matrix, actual)
    check("rag-23-ledger-has-discrepancies-key", "discrepancies" in ledger)
    check("rag-24-ledger-has-entries", len(ledger["ledger"]) == 3)
    check("rag-25-ledger-model-match", ledger["ledger"][0]["model_match"])
    check("rag-26-ledger-no-discrepancies", len(ledger["discrepancies"]) == 0)

    # rag-27: planned vs actual with mismatch
    actual_mismatch = [
        {"role": "implementer", "node": "9bao", "model": "opencode/mimo-v2.5-pro",
         "provider": "xiaomi", "call_count": 5, "duration": "30s", "exit_code": 0,
         "final_status": "PASS"},
        {"role": "reviewer", "node": "9bao", "model": "opencode/deepseek-v4-pro",
         "provider": "deepseek", "call_count": 2, "duration": "10s", "exit_code": 0,
         "final_status": "PASS"},
        {"role": "checker", "node": "21bao", "model": "opencode/deepseek-v4-pro",
         "provider": "deepseek", "call_count": 1, "duration": "5s", "exit_code": 0,
         "final_status": "PASS"},
    ]
    ledger_mismatch = generate_planned_vs_actual_ledger(matrix, actual_mismatch)
    check("rag-27-mismatch-detected", len(ledger_mismatch["discrepancies"]) > 0)
    impl_entry = [e for e in ledger_mismatch["ledger"] if e["role"] == "implementer"][0]
    check("rag-28-mismatch-model", not impl_entry["model_match"])

    # rag-29: all required fields check
    check("rag-29-required-fields-count",
          len(REQUIRED_ASSIGNMENT_FIELDS) >= 8,
          f"count={len(REQUIRED_ASSIGNMENT_FIELDS)}")

    # rag-30: valid roles set
    check("rag-30-valid-roles-count", len(VALID_ROLES) >= 8)

    # ── v1.1.0 spec §4.2 self-check (Baseline02 Stage 3) ─────────────

    # Helpers
    valid_ulid = "01HXYZABCDEFGHJKMNPQRSTVWX"  # 26 chars, no I/L/O/U
    valid_sha256 = "a" * 64
    valid_sha1 = "b" * 40
    valid_iso = "2026-07-01T08:00:00Z"
    real_model_id = "deepseek-deepseek-coder"  # must be in scripts/model_pool.yaml

    def make_v11_entry(role="implementer", node="21bao", model=real_model_id,
                       provider="deepseek", provider_namespace="opencode",
                       approval_id=valid_ulid,
                       override=None):
        sig = compute_approval_signature(approval_id, valid_iso)
        e = {
            "role": role, "node": node, "model": model, "provider": provider,
            "cost_tag": "v11-001", "reason": "v1.1.0 spec test",
            "call_budget": 100, "fallback_policy": "disabled",
            "assignment_id": valid_ulid,
            "provider_namespace": provider_namespace,
            "operator_approval_timestamp": valid_iso,
            "operator_approval_signature": sig,
            "node_whitelist_verified": True,
            "model_pool_source_verified": True,
            "base_sha": valid_sha1,
        }
        if override:
            e.update(override)
        return e

    # v11-01: detect_spec_version defaults to 1.0.0 when no opt-in
    check("v11-01-detect-default-1.0.0", detect_spec_version({}) == "1.0.0")

    # v11-02: detect_spec_version honors explicit spec_version
    check("v11-02-detect-explicit-1.1.0",
          detect_spec_version({"spec_version": "1.1.0"}) == "1.1.0")

    # v11-03: detect_spec_version auto-detects v1.1.0 when all entries opt in
    matrix_full = {
        "version": "1.0.0", "task_id": "v11-detect", "risk_level": "low",
        "assignments": [make_v11_entry(), make_v11_entry(role="reviewer", node="5bao")],
    }
    check("v11-03-detect-auto-from-entries",
          detect_spec_version(matrix_full) == "1.1.0")

    # v11-04: is_node_whitelisted accepts all 3 cluster nodes
    check("v11-04-whitelist-21bao", is_node_whitelisted("21bao"))
    check("v11-05-whitelist-5bao", is_node_whitelisted("5bao"))
    check("v11-06-whitelist-9bao", is_node_whitelisted("9bao"))

    # v11-07: is_node_whitelisted rejects "win"
    check("v11-07-whitelist-rejects-win", not is_node_whitelisted("win"))

    # v11-08: is_node_whitelisted rejects other strings
    for bad in ("Win", "WIN", "21bao ", " 21bao", "21Bao", "10bao", "main", "agent"):
        check(f"v11-08-rejects-{bad!r}", not is_node_whitelisted(bad))

    # v11-09: main-agent (legacy) is allowed (for tester role backwards-compat)
    check("v11-09-main-agent-allowed", is_node_whitelisted("main-agent"))

    # v11-10: load_model_pool_declarations returns declaration layer only
    decl = load_model_pool_declarations()
    check("v11-10-pool-loaded", len(decl["model_ids"]) > 0)
    # CRITICAL: no key_env in any returned model entry
    leaked = []
    for mid, m in decl["models_by_id"].items():
        if "key_env" in m or "base_url_env" in m:
            leaked.append(mid)
    check("v11-11-pool-no-secret-leak", len(leaked) == 0, f"leaked: {leaked}")
    check("v11-12-pool-has-canonical-providers", len(decl["canonical_providers"]) > 0)
    check("v11-13-pool-has-provider-namespaces", len(decl["provider_namespaces"]) > 0)

    # v11-14: is_model_in_pool accepts model_id
    sample_id = next(iter(decl["model_ids"]))
    check("v11-14-model-in-pool-by-id", is_model_in_pool(sample_id, decl=decl))

    # v11-15: is_model_in_pool rejects bogus model
    check("v11-15-model-not-in-pool", not is_model_in_pool("bogus/imaginary-model-99", decl=decl))

    # v11-16: compute_approval_signature is deterministic 64-char hex
    sig_a = compute_approval_signature("01HXYZABCDEFGHJKMNPQRSTVWX", valid_iso)
    sig_b = compute_approval_signature("01HXYZABCDEFGHJKMNPQRSTVWX", valid_iso)
    check("v11-16-sig-deterministic", sig_a == sig_b)
    check("v11-17-sig-64-char-hex", HEX_SHA256_RE.match(sig_a) is not None)

    # v11-18: validate_assignment_entry_v11 passes for a legal entry
    # Use a real model_id from the central pool (e.g. "deepseek-deepseek-coder")
    real_model_id = "deepseek-deepseek-coder"
    assert is_model_in_pool(real_model_id, decl=decl), "fixture model must be in pool"
    good_entry = make_v11_entry(model=real_model_id)
    errs = validate_assignment_entry_v11(good_entry, 0, decl=decl)
    check("v11-18-good-entry-no-errors", len(errs) == 0, str(errs))

    # v11-19: missing assignment_id blocks
    bad = make_v11_entry(override={"assignment_id": None})
    errs = validate_assignment_entry_v11(bad, 0, decl=decl)
    check("v11-19-missing-assignment-id", any("assignment_id" in e for e in errs))

    # v11-20: invalid assignment_id format blocks
    bad = make_v11_entry(override={"assignment_id": "not-a-ulid"})
    errs = validate_assignment_entry_v11(bad, 0, decl=decl)
    check("v11-20-invalid-ulid-format", any("ULID" in e for e in errs))

    # v11-21: missing operator_approval_signature blocks
    bad = make_v11_entry(override={"operator_approval_signature": None})
    errs = validate_assignment_entry_v11(bad, 0, decl=decl)
    check("v11-21-missing-signature", any("operator_approval_signature" in e for e in errs))

    # v11-22: signature must be 64-char hex
    bad = make_v11_entry(override={"operator_approval_signature": "tooshort"})
    errs = validate_assignment_entry_v11(bad, 0, decl=decl)
    check("v11-22-signature-bad-format", any("64-char" in e for e in errs))

    # v11-23: node_whitelist_verified=False blocks
    bad = make_v11_entry(override={"node_whitelist_verified": False})
    errs = validate_assignment_entry_v11(bad, 0, decl=decl)
    check("v11-23-node-verified-false-blocks", any("node_whitelist_verified" in e for e in errs))

    # v11-24: model_pool_source_verified=False blocks
    bad = make_v11_entry(override={"model_pool_source_verified": False})
    errs = validate_assignment_entry_v11(bad, 0, decl=decl)
    check("v11-24-pool-source-false-blocks", any("model_pool_source_verified" in e for e in errs))

    # v11-25: model not in pool with verified=True blocks (cross-field)
    bad = make_v11_entry(override={"model": "opencode/bogus-model-zzz"})
    errs = validate_assignment_entry_v11(bad, 0, decl=decl)
    check("v11-25-model-not-in-pool-blocks", any("not in the central model pool" in e for e in errs))

    # v11-26: node="win" rejected (architecture drift guard)
    bad = make_v11_entry(override={"node": "win"})
    errs = validate_assignment_entry_v11(bad, 0, decl=decl)
    check("v11-26-node-win-rejected", any("v1.1.0 strict cluster whitelist" in e for e in errs))

    # v11-27: node="21bao" with model not in pool blocks (cross-field)
    bad = make_v11_entry(override={"node": "21bao", "model": "anthropic/imaginary"})
    errs = validate_assignment_entry_v11(bad, 0, decl=decl)
    check("v11-27-cross-field-bogus-model", any("not in the central model pool" in e for e in errs))

    # v11-28: bad base_sha format blocks
    bad = make_v11_entry(override={"base_sha": "tooshort"})
    errs = validate_assignment_entry_v11(bad, 0, decl=decl)
    check("v11-28-base-sha-bad-format", any("40-char" in e for e in errs))

    # v11-29: validate_assignment_matrix_strict on v1.1.0 matrix with all 7 fields
    matrix_strict = create_assignment_matrix("low", task_id="v11-strict")
    matrix_strict["assignments"] = [
        make_v11_entry(role="implementer", node="21bao"),
        make_v11_entry(role="reviewer", node="9bao"),
        make_v11_entry(role="checker", node="21bao"),
    ]
    matrix_strict["operator_approved"] = True
    matrix_strict["operator_approval_timestamp"] = valid_iso
    matrix_strict["operator_approval_signature"] = compute_approval_signature(valid_ulid, valid_iso)
    matrix_strict["spec_version"] = "1.1.0"
    result_strict = validate_assignment_matrix_strict(matrix_strict)
    check("v11-29-strict-full-v11-passes", result_strict["valid"],
          f"errors: {result_strict['errors']}")

    # v11-30: validate_assignment_matrix_strict on v1.1.0 matrix with bogus node blocks
    matrix_bad_node = create_assignment_matrix("low", task_id="v11-bad-node")
    matrix_bad_node["assignments"] = [
        make_v11_entry(role="implementer", node="win"),
    ]
    matrix_bad_node["operator_approved"] = True
    matrix_bad_node["operator_approval_timestamp"] = valid_iso
    matrix_bad_node["operator_approval_signature"] = valid_sha256
    matrix_bad_node["spec_version"] = "1.1.0"
    result_bad_node = validate_assignment_matrix_strict(matrix_bad_node)
    check("v11-30-strict-bad-node-blocks", not result_bad_node["valid"])

    # v11-31: validate_assignment_matrix (v1.0.0) on legacy matrix still passes (backward compat)
    matrix_legacy = create_assignment_matrix("low", task_id="v11-legacy")
    matrix_legacy["assignments"] = [
        create_role_assignment(role="implementer", node="21bao",
                               model=real_model_id, provider="deepseek"),
        create_role_assignment(role="reviewer", node="9bao",
                               model=real_model_id, provider="deepseek"),
        create_role_assignment(role="checker", node="21bao",
                               model=real_model_id, provider="deepseek"),
    ]
    matrix_legacy["operator_approved"] = True
    matrix_legacy["operator_approval_timestamp"] = "2026-06-21T00:00:00Z"
    result_legacy = validate_assignment_matrix(matrix_legacy)
    check("v11-31-legacy-matrix-still-passes-v10", result_legacy["valid"])

    # v11-32: fallback_policy edge cases
    for fp in ("disabled", "operator_selects", "same_provider_different_model"):
        e = make_v11_entry(override={"fallback_policy": fp})
        errs = validate_assignment_entry_v11(e, 0, decl=decl)
        check(f"v11-32-fb-{fp}-ok", len(errs) == 0)
    for fp in ("", "auto", "Disabled", "DISABLED", "none", None):
        e = make_v11_entry(override={"fallback_policy": fp})
        # v11 entry check only checks v1.1.0 fields; fb policy is v1.0.0
        # But we want to confirm v1.0.0 still catches bad fp.
        # Use validate_assignment_entry (v1.0.0) for that.
        errs10 = validate_assignment_entry(e, 0)
        check(f"v11-33-fb-{fp!r}-v10-blocks", len(errs10) > 0)

    # v11-34: low-risk no-bypass
    matrix_low = create_assignment_matrix("low", task_id="v11-low-nobypass")
    matrix_low["assignments"] = [
        make_v11_entry(role="implementer", node="21bao"),
        make_v11_entry(role="reviewer", node="5bao"),
        make_v11_entry(role="checker", node="21bao"),
    ]
    # operator_approved intentionally False
    matrix_low["spec_version"] = "1.1.0"
    result_low = validate_assignment_matrix_strict(matrix_low)
    check("v11-34-low-no-bypass-blocks", not result_low["valid"])

    # ── v1.1.0 corrective (PR #278 acceptance FAIL, issue #1) ─────────

    # v11-35: is_v11_strict_node_accepted accepts only cluster nodes
    check("v11-35-strict-accepts-21bao", is_v11_strict_node_accepted("21bao"))
    check("v11-36-strict-accepts-5bao", is_v11_strict_node_accepted("5bao"))
    check("v11-37-strict-accepts-9bao", is_v11_strict_node_accepted("9bao"))

    # v11-38: is_v11_strict_node_accepted rejects main-agent (operator §3)
    check("v11-38-strict-rejects-main-agent",
          not is_v11_strict_node_accepted("main-agent"))

    # v11-39: is_v11_strict_node_accepted rejects win/other
    for bad in ("win", "Win", "10bao", "hermes", "agent", ""):
        check(f"v11-39-strict-rejects-{bad!r}", not is_v11_strict_node_accepted(bad))

    # v11-40: legacy is_node_whitelisted preserves main-agent for v1.0.0 compat
    check("v11-40-legacy-keeps-main-agent", is_node_whitelisted("main-agent"))

    # v11-41: v1.1 strict + node=main-agent + role=implementer BLOCKS (issue #1)
    matrix_main_imp = {
        "risk_level": "low", "task_id": "v11-main-agent-imp",
        "required_roles": ["implementer", "reviewer", "checker"],
        "operator_approved": True,
        "operator_approval_timestamp": valid_iso,
        "operator_approval_signature": valid_sha256,
        "main_agent_as_tester_approved": True,
        "spec_version": "1.1.0",
        "assignments": [
            make_v11_entry(role="implementer", node="main-agent"),
            make_v11_entry(role="reviewer", node="5bao"),
            make_v11_entry(role="checker", node="21bao"),
        ],
    }
    result_main_imp = validate_assignment_matrix_strict(matrix_main_imp)
    check("v11-41-strict-main-agent-imp-blocks",
          not result_main_imp["valid"] and any("main-agent" in e for e in result_main_imp.get("errors", [])),
          f"got: {result_main_imp}")

    # v11-42: v1.1 strict + node=main-agent + role=tester BLOCKS (issue #1)
    matrix_main_tester = {
        "risk_level": "low", "task_id": "v11-main-agent-tester",
        "required_roles": ["implementer", "reviewer", "tester-checker"],
        "operator_approved": True,
        "operator_approval_timestamp": valid_iso,
        "operator_approval_signature": valid_sha256,
        "main_agent_as_tester_approved": True,
        "spec_version": "1.1.0",
        "assignments": [
            make_v11_entry(role="implementer", node="21bao"),
            make_v11_entry(role="reviewer", node="5bao"),
            make_v11_entry(role="tester-checker", node="main-agent"),
        ],
    }
    result_main_tester = validate_assignment_matrix_strict(matrix_main_tester)
    check("v11-42-strict-main-agent-tester-blocks",
          not result_main_tester["valid"] and any("main-agent" in e for e in result_main_tester.get("errors", [])),
          f"got: {result_main_tester}")

    # ── v1.1.0 corrective (PR #278 acceptance FAIL, issue #2) ─────────

    # v11-43: v1.0.0 legacy matrix (no spec_version, no v1.1.0 fields) in
    # strict validator now BLOCKS (issue #2 fail-closed production enforcement)
    matrix_v10_legacy = create_assignment_matrix("low", task_id="v11-v10-legacy")
    matrix_v10_legacy["assignments"] = [
        create_role_assignment(role="implementer", node="21bao",
                               model=real_model_id, provider="deepseek"),
        create_role_assignment(role="reviewer", node="5bao",
                               model=real_model_id, provider="deepseek"),
        create_role_assignment(role="checker", node="21bao",
                               model=real_model_id, provider="deepseek"),
    ]
    matrix_v10_legacy["operator_approved"] = True
    matrix_v10_legacy["operator_approval_timestamp"] = "2026-06-21T00:00:00Z"
    result_v10_strict = validate_assignment_matrix_strict(matrix_v10_legacy)
    check("v11-43-strict-v10-legacy-blocks", not result_v10_strict["valid"])
    # v11_strict_enforcement check must be present
    v11_block_check = [c for c in result_v10_strict.get("checks", [])
                       if c.get("name") == "v11_strict_enforcement"]
    check("v11-44-strict-v10-legacy-has-v11-enforcement-block",
          len(v11_block_check) == 1 and v11_block_check[0]["result"] == "BLOCK",
          f"got checks: {result_v10_strict.get('checks')}")

    # v11-45: pure v1.0.0 path (validate_assignment_matrix) unchanged for legacy
    result_v10_pure = validate_assignment_matrix(matrix_v10_legacy)
    check("v11-45-pure-v10-path-still-passes-legacy", result_v10_pure["valid"])

    # v11-46: legal v1.1 strict still passes (sanity)
    matrix_legal_v11 = {
        "risk_level": "low", "task_id": "v11-legal-strict",
        "required_roles": ["implementer", "reviewer", "checker"],
        "operator_approved": True,
        "operator_approval_timestamp": valid_iso,
        "operator_approval_signature": valid_sha256,
        "spec_version": "1.1.0",
        "assignments": [
            make_v11_entry(role="implementer", node="21bao"),
            make_v11_entry(role="reviewer", node="5bao"),
            make_v11_entry(role="checker", node="21bao"),
        ],
    }
    result_legal = validate_assignment_matrix_strict(matrix_legal_v11)
    check("v11-46-legal-v11-strict-passes", result_legal["valid"],
          f"errors: {result_legal.get('errors')}")

    return {
        "version": __version__,
        "passed": passed == total,
        "total_tests": total,
        "passed_count": passed,
        "failed_count": total - passed,
        "checks": checks,
        "exit_code": 0 if passed == total else 1,
    }


# ── CLI ───────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        description="Workflow Role Assignment Gate — enforce role plans before execution",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--json", dest="output_json", action="store_true")
    parser.add_argument("--self-check", dest="self_check_flag", action="store_true")

    sub = parser.add_subparsers(dest="command")

    p_val = sub.add_parser("validate", help="Validate assignment matrix")
    p_val.add_argument("--matrix", required=True, help="Path to assignment matrix JSON")

    p_rec = sub.add_parser("recommend", help="Recommend role structure")
    p_rec.add_argument("--risk", default="low", help="Risk level (low/medium/high/critical)")
    p_rec.add_argument("--tags", default="", help="Comma-separated tags")
    p_rec.add_argument("--task-type", default="coding", help="Task type")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_check_flag:
        result = self_check()
        if args.output_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"=== SELF-CHECK (v{__version__}) ===")
            print(f"  Total: {result['total_tests']}")
            print(f"  Passed: {result['passed_count']}")
            print(f"  Failed: {result['failed_count']}")
            for c in result["checks"]:
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  [{icon}] {c['name']}: {c['detail']}")
            print(f"\n  Self-check: {'PASSED' if result['passed'] else 'FAILED'}")
        sys.exit(result["exit_code"])

    if args.command == "validate":
        with open(args.matrix, "r", encoding="utf-8") as f:
            matrix = json.load(f)
        result = validate_assignment_matrix(matrix)
        if args.output_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Verdict: {result['verdict']}")
            for c in result["checks"]:
                icon = "PASS" if c["result"] == "PASS" else "BLOCK"
                print(f"  [{icon}] {c['name']}: {c['detail']}")
            for e in result["errors"]:
                print(f"  ERROR: {e}")
        sys.exit(0 if result["valid"] else 1)

    if args.command == "recommend":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        result = get_required_roles(args.risk, tags)
        result["tags"] = tags
        result["task_type"] = args.task_type
        if args.output_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Risk: {args.risk} → Effective: {result['effective_risk']}")
            print(f"Required: {', '.join(result['required_roles'])}")
            print(f"Optional: {', '.join(result['optional_roles']) if result['optional_roles'] else 'none'}")
            print(f"Dual reviewer: {result['requires_dual_reviewer']}")
            print(f"Main-agent-as-tester requires approval: {result['main_agent_as_tester_requires_approval']}")
        sys.exit(0)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
