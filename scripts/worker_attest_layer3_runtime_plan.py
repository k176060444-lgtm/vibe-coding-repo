#!/usr/bin/env python3
"""
G-L3R — Layer3 Live Runtime Drift Evidence Plan (PLAN ONLY, no execution).

G-L3R is the LIVE runtime counterpart of G-L3F. While G-L3F compares
declared intent against FIXTURE evidence (advisory), G-L3R defines the
schema, gate semantics, and validator for SANCTIONED LIVE runtime
receipt collection.

THIS MODULE DOES NOT EXECUTE LIVE COLLECTION. It defines:
  1. The boundary between G-L3F (fixture) and G-L3R (live).
  2. The required fields and enums of a live runtime receipt.
  3. The operator-gate contract that must hold before any live
     collection can be authorized.
  4. The validation rules and verdict enum for a live receipt.
  5. Fail-closed semantics for active-model mismatch, missing
     authorized receipt, forbidden operations, leaks, and schema drift.

A separate operator-authorized PR is required to actually run live
collection. This module is the design / protocol / gate definition.

=== SCOPE (HARD LIMITS) ===
- No SSH, no subprocess, no os.environ / os.getenv, no HTTP.
- No model calls, no credential provisioning, no node sync.
- No readiness expansion, no DEU assignment, no new namespace.
- No automatic promotion of runtime_visible / env_loaded /
  model_call_verified / operator_approved.
- DeepSeek V4 Pro is NOT special-cased; it follows the same
  active-model rule as every other active model.

=== VERDICTS (G_L3R_* namespace — does NOT reuse G_L3F_* or E2E_*) ===
  G_L3R_NOT_COLLECTED         — no live collection authorized yet
  G_L3R_PASS                  — sanctioned live receipts match declared
  G_L3R_PASS_WITH_WARN        — DEU live evidence observed (WARN)
  G_L3R_BLOCKED               — active model mismatch OR forbidden flag
  G_L3R_STOP_SECRET_RISK      — redaction false or leak detected
  G_L3R_STOP_AND_REANCHOR     — schema/anchor disagreement

=== OPERATOR GATES ===
- Approval is required per call: approval_id (non-empty string).
- Approval is required per node: node must be in {21bao, 5bao, 9bao}.
- Approval is required per collector_mode: dry_run | real_read | ssh_canary.
- Approval forbids model_call_verified/operator_approved promotion.
- Approval forbids automatic write-back to node_model_capability.yaml.

=== COST STRATEGY (comment-only; G-L3R does not call models) ===
If a future G-L4 live-validation phase ever runs:
  Default: DeepSeek V4 Flash, Mimo V2.5 (low cost).
  Expensive models: bounded smoke + explicit operator authorization only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ── Constants ─────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.0"

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO = SCRIPT_DIR.parent

POOL_PATH = SCRIPT_DIR / "model_pool.yaml"
NMC_PATH = SCRIPT_DIR / "node_model_capability.yaml"

VALID_NODES = frozenset({"21bao", "5bao", "9bao"})

# Lifecycle classification — reused from G-L3F for consistency.
ACTIVE_LIFECYCLE_STATUSES = frozenset({"enabled_assigned", "operator_requested"})
DEU_LIFECYCLE_STATUSES = frozenset({"declared_enabled_unassigned"})
NON_ACTIVE_LIFECYCLE_STATUSES = frozenset(
    {"disabled", "historical", "remove_pending", "candidate", "required"}
)

# Allowed collector_modes — operator must approve one per live call.
VALID_COLLECTOR_MODES = frozenset({"dry_run", "real_read", "ssh_canary"})

# Allowed collection_status values on a live receipt.
VALID_COLLECTION_STATUS = frozenset({
    "not_collected",      # authorized but not yet executed
    "collected",          # executed successfully
    "skipped",            # operator gate skipped execution
    "error",              # execution attempted but failed
    "blocked",            # gate blocked execution
})

# Verdict priority (highest → lowest; must match G-L3R validator logic).
_VERDICT_PRIORITY = {
    "G_L3R_STOP_SECRET_RISK": 7,
    "G_L3R_STOP_AND_REANCHOR": 6,
    "G_L3R_BLOCKED": 5,
    "G_L3R_NOT_COLLECTED": 4,
    "G_L3R_PASS_WITH_WARN": 2,
    "G_L3R_PASS": 1,
}

_FAIL_CLOSED_VERDICTS = frozenset({
    "G_L3R_STOP_SECRET_RISK",
    "G_L3R_STOP_AND_REANCHOR",
    "G_L3R_BLOCKED",
})

_ADVISORY_VERDICTS = frozenset({
    "G_L3R_NOT_COLLECTED",
    "G_L3R_PASS_WITH_WARN",
    "G_L3R_PASS",
})

# Redaction sub-flags (must all be True on a live receipt).
REDACTION_SUBFLAGS = (
    "no_secret_value",
    "no_env_value",
    "no_base_url_value",
    "no_real_endpoint_url",
    "no_key_length",
)

# Forbidden operation flags (must all be False on a live receipt).
FORBIDDEN_FLAGS = (
    "ssh_attempted",
    "subprocess_attempted",
    "os_environ_read_attempted",
    "real_path_read_attempted",
    "model_call_attempted",
    "credential_provisioning_attempted",
)

# Required fields for a live runtime receipt (G-L3R schema).
LIVE_RECEIPT_REQUIRED_FIELDS = frozenset({
    "schema_version",                  # must equal SCHEMA_VERSION
    "node",                            # one of VALID_NODES
    "model_id",                        # id from model_pool.yaml
    "provider_namespace",              # e.g. "opencode-go"
    "runtime_provider",                # e.g. "opencode-go"
    "alias",                           # primary_alias
    "runtime_visible_observed",        # bool (true/false)
    "env_loaded_observed",             # bool
    "credential_status_observed",      # "present" | "absent" | "unknown"
    "endpoint_ref_observed",           # env-var name (label only)
    "redaction_status",                # dict with REDACTION_SUBFLAGS
    "forbidden_operation_flags",       # dict with FORBIDDEN_FLAGS
    "collector_mode",                  # dry_run | real_read | ssh_canary
    "operator_approval_id",            # non-empty string, MUST be present
    "receipt_anchor",                  # opaque anchor (sha-prefix or uuid)
    "source_node",                     # which node produced the evidence
    "collection_status",               # see VALID_COLLECTION_STATUS
    "generated_at",                    # ISO timestamp
})

# Runtime fields that G-L3R MUST NEVER write to.
RUNTIME_FIELDS_FORBIDDEN_TO_WRITE = frozenset({
    "runtime_visible",
    "env_loaded",
    "model_call_verified",
    "operator_approved",
})

# Leak scanners (defensive copy from existing modules).
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|"
    r"glpat-[A-Za-z0-9_\-]{20,}|xai-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
_URL_RE = re.compile(r"https?://[A-Za-z0-9][A-Za-z0-9.\-]{1,}(?::\d+)?(?:/[^\s\"']*)?")
_PATH_RE = re.compile(
    r"(?:/home/[A-Za-z0-9_\-]+|/root/|C:\\Users\\[A-Za-z0-9_\-]+|"
    r"opencode\.env)"
)


# ═══════════════════════════════════════════════════════════════════════════════
# G-L3F / G-L3R boundary definitions
# ═══════════════════════════════════════════════════════════════════════════════


def get_l3f_l3r_boundary() -> dict:
    """Return the canonical boundary definition between G-L3F and G-L3R.

    This is a documentation-only API; no live collection is performed."""
    return {
        "G_L3F": {
            "evidence_source": "fixture_only",
            "scope": "scripts/worker_attest_layer3_drift.py",
            "verdict_namespace": "G_L3F_*",
            "verdicts": [
                "G_L3F_PASS", "G_L3F_PASS_WITH_WARN",
                "G_L3F_CANDIDATE_DRIFT", "G_L3F_BLOCKED",
                "G_L3F_STOP_SECRET_RISK", "G_L3F_STOP_AND_REANCHOR",
            ],
            "merge_blocking_verdicts": [
                "G_L3F_STOP_SECRET_RISK",
                "G_L3F_STOP_AND_REANCHOR",
                "G_L3F_BLOCKED",
            ],
            "merge_advisory_verdicts": [
                "G_L3F_PASS", "G_L3F_PASS_WITH_WARN",
                "G_L3F_CANDIDATE_DRIFT",
            ],
            "claims": "fixture-evidence data gaps, NOT live runtime clean",
            "can_be_run_now": True,
        },
        "G_L3R": {
            "evidence_source": "sanctioned_live_runtime",
            "scope": "scripts/worker_attest_layer3_runtime_plan.py (this module)",
            "verdict_namespace": "G_L3R_*",
            "verdicts": [
                "G_L3R_NOT_COLLECTED",
                "G_L3R_PASS", "G_L3R_PASS_WITH_WARN",
                "G_L3R_BLOCKED",
                "G_L3R_STOP_SECRET_RISK", "G_L3R_STOP_AND_REANCHOR",
            ],
            "merge_blocking_verdicts": [
                "G_L3R_STOP_SECRET_RISK",
                "G_L3R_STOP_AND_REANCHOR",
                "G_L3R_BLOCKED",
            ],
            "merge_advisory_verdicts": [
                "G_L3R_NOT_COLLECTED",
                "G_L3R_PASS_WITH_WARN",
                "G_L3R_PASS",
            ],
            "claims": "live runtime receipt validation, requires explicit operator approval",
            "can_be_run_now": False,
            "live_collection_in_this_pr": False,
            "operator_gates_required": [
                "explicit operator approval_id (non-empty string)",
                "node scope bounded to {21bao, 5bao, 9bao}",
                "collector_mode bounded to {dry_run, real_read, ssh_canary}",
                "forbidden: model_call_verified / operator_approved promotion",
                "forbidden: automatic write-back to node_model_capability.yaml",
            ],
        },
        "boundary_rules": [
            "G-L3F never reads live runtime data; only fixture JSON.",
            "G-L3R never reads fixture JSON as authority; only as auxiliary context.",
            "A live receipt's collection_status='collected' implies it was produced by a separately authorized live collection call.",
            "G-L3R verdicts are advisory until a separate operator authorization enables live collection.",
            "G-L3F and G-L3R verdicts are reported independently; no cross-promotion.",
            "DeepSeek V4 Pro follows the same active-model rules in both G-L3F and G-L3R; no special-casing.",
        ],
    }


def get_operator_gate_contract() -> dict:
    """Return the canonical operator gate contract for authorizing live collection."""
    return {
        "approval_required_fields": {
            "operator_approval_id": "non-empty string; opaque identifier",
            "node": sorted(VALID_NODES),
            "collector_mode": sorted(VALID_COLLECTOR_MODES),
            "scope_constraint": "must be bounded — no implicit wildcard",
        },
        "forbidden_in_authorized_collection": {
            "model_call_promotion": [
                "cannot flip model_call_verified from 'unknown'/'no' to 'ok'/'yes'",
                "cannot flip operator_approved from 'unknown'/'no' to 'ok'/'yes'",
            ],
            "runtime_field_writeback": [
                "cannot modify runtime_visible in node_model_capability.yaml",
                "cannot modify env_loaded in node_model_capability.yaml",
                "cannot modify model_call_verified in node_model_capability.yaml",
                "cannot modify operator_approved in node_model_capability.yaml",
            ],
            "data_promotion": [
                "cannot silently promote DEU models to enabled_assigned",
                "cannot introduce a new provider_namespace not already in the frozen set",
                "cannot modify model_pool.yaml without a separate D-A/D-B PR",
            ],
        },
        "allowed_under_authorization": [
            "read-only inspection of declared capability (model_pool.yaml + node_model_capability.yaml)",
            "receipt validation per G-L3R rules",
            "verdict emission in G_L3R_* namespace",
        ],
        "post_collection_discipline": [
            "live receipts that pass validation are stored for audit, not written back to YAML",
            "any promotion of runtime_visible / env_loaded requires a separate operator D-A/D-B PR",
            "G-L3R does not imply G-READINESS expansion; that requires another bounded PR",
        ],
    }


def get_cost_strategy() -> dict:
    """Return the canonical cost strategy for any future live validation phase.

    G-L3R itself does NOT call models. This is documentation-only."""
    return {
        "current_phase": "G-L3R-PLAN (no model calls)",
        "future_phase_if_any": "G-L4 (live validation)",
        "default_models_for_g_l4": [
            "opencode-go-deepseek-v4-flash",
            "opencode-go-mimo-v2-5",
        ],
        "rationale": "low-cost models first; expensive models only for bounded smoke",
        "expensive_models_requiring_extra_authorization": [
            "opencode-go-deepseek-v4-pro",
            "opencode-go-glm-5-1",
            "opencode-go-glm-5-2",
            "opencode-go-kimi-k2-6",
            "opencode-go-qwen3-7-max",
            "opencode-go-qwen3-7-plus",
            "opencode-go-mimo-v2-5-pro",
        ],
        "rule": "expensive model calls require bounded smoke + explicit operator authorization in a separate PR",
        "deepseek_v4_pro_handling": "treated identically to all other active models in G-L3R; no special privilege",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Receipt validation (pure function — no I/O, no collection)
# ═══════════════════════════════════════════════════════════════════════════════


def _flatten_text(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(obj)


def _scan_leaks(payload: Any) -> dict:
    text = _flatten_text(payload)
    result = {
        "secret_leak": bool(_SECRET_RE.search(text)),
        "url_leak": bool(_URL_RE.search(text)),
        "path_leak": bool(_PATH_RE.search(text)),
    }
    result["any_leak"] = any(result.values())
    return result


def validate_live_receipt_schema(receipt: Any) -> dict:
    """Validate the structure of a live runtime receipt.

    Pure function: validates schema only, no verdict emission.
    Returns {valid, errors, warnings}."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(receipt, dict):
        return {
            "valid": False,
            "errors": ["receipt must be a dict"],
            "warnings": warnings,
        }

    # Required fields
    for f in LIVE_RECEIPT_REQUIRED_FIELDS:
        if f not in receipt:
            errors.append(f"Missing required field: '{f}'")

    # schema_version
    sv = receipt.get("schema_version", "")
    if sv != SCHEMA_VERSION:
        errors.append(
            f"schema_version must be '{SCHEMA_VERSION}', got '{sv}'"
        )

    # node
    node = receipt.get("node", "")
    if node and node not in VALID_NODES:
        errors.append(f"Invalid node '{node}'")

    # source_node
    sn = receipt.get("source_node", "")
    if sn and sn not in VALID_NODES:
        errors.append(f"Invalid source_node '{sn}'")

    # collector_mode
    cm = receipt.get("collector_mode", "")
    if cm and cm not in VALID_COLLECTOR_MODES:
        errors.append(f"Invalid collector_mode '{cm}'")

    # collection_status
    cs = receipt.get("collection_status", "")
    if cs and cs not in VALID_COLLECTION_STATUS:
        errors.append(f"Invalid collection_status '{cs}'")

    # operator_approval_id must be non-empty when present
    oa = receipt.get("operator_approval_id", "")
    if not isinstance(oa, str) or not oa.strip():
        errors.append("operator_approval_id must be non-empty string")

    # redaction_status must have all REDACTION_SUBFLAGS
    rs = receipt.get("redaction_status", {})
    if not isinstance(rs, dict):
        errors.append("redaction_status must be a dict")
    else:
        for sf in REDACTION_SUBFLAGS:
            if sf not in rs:
                errors.append(f"redaction_status missing subflag: '{sf}'")

    # forbidden_operation_flags must have all FORBIDDEN_FLAGS
    ff = receipt.get("forbidden_operation_flags", {})
    if not isinstance(ff, dict):
        errors.append("forbidden_operation_flags must be a dict")
    else:
        for flag in FORBIDDEN_FLAGS:
            if flag not in ff:
                errors.append(f"forbidden_operation_flags missing: '{flag}'")

    # runtime_visible_observed / env_loaded_observed must be bool
    for bf in ("runtime_visible_observed", "env_loaded_observed"):
        v = receipt.get(bf)
        if v is not None and not isinstance(v, bool):
            errors.append(f"{bf} must be bool or absent")

    # credential_status_observed
    cso = receipt.get("credential_status_observed", "")
    if cso and cso not in ("present", "absent", "unknown"):
        errors.append(
            f"credential_status_observed must be 'present'|'absent'|'unknown'"
        )

    # endpoint_ref_observed must be a string label (never a URL or path)
    ero = receipt.get("endpoint_ref_observed", "")
    if isinstance(ero, str) and ero:
        # If endpoint_ref_observed looks like a URL or real path, reject.
        if _URL_RE.search(ero) or _PATH_RE.search(ero):
            errors.append(
                "endpoint_ref_observed must be a label, not a URL or real path"
            )

    return {"valid": not errors, "errors": errors, "warnings": warnings}


def evaluate_live_receipt(receipt: dict, declared: dict | None = None) -> dict:
    """Evaluate a single live runtime receipt and emit a G_L3R_* verdict.

    Args:
        receipt: a dict that passed validate_live_receipt_schema()
        declared: optional declared intent (model_id → lifecycle_status, expected provider_namespace, etc.)

    Returns:
        dict with verdict (G_L3R_*), findings, leak_scan.
    """
    findings: list[dict] = []

    # ── 1. Leak scan on whole receipt ────────────────────────────────────
    leak = _scan_leaks(receipt)
    if leak["any_leak"]:
        findings.append({
            "type": "leak_detected",
            "severity": "stop_secret_risk",
            "detail": f"leak_scan={leak}",
        })

    # ── 2. Forbidden operation flags ─────────────────────────────────────
    ff = receipt.get("forbidden_operation_flags", {})
    for flag in FORBIDDEN_FLAGS:
        if ff.get(flag) is True:
            findings.append({
                "type": f"forbidden_flag_{flag}",
                "severity": "blocked",
                "detail": f"Forbidden operation flag '{flag}' is True",
            })

    # ── 3. Redaction status ──────────────────────────────────────────────
    rs = receipt.get("redaction_status", {})
    for sf in REDACTION_SUBFLAGS:
        if rs.get(sf) is False:
            findings.append({
                "type": f"redaction_fail_{sf}",
                "severity": "stop_secret_risk",
                "detail": f"Redaction subflag '{sf}' is False",
            })

    # ── 4. Schema-level checks (anchor / version) ───────────────────────
    sv = receipt.get("schema_version", "")
    if sv != SCHEMA_VERSION:
        findings.append({
            "type": "schema_version_mismatch",
            "severity": "stop_and_reanchor",
            "detail": f"schema_version='{sv}' expected '{SCHEMA_VERSION}'",
        })

    # receipt_anchor must be non-empty
    anchor = receipt.get("receipt_anchor", "")
    if not isinstance(anchor, str) or not anchor.strip():
        findings.append({
            "type": "missing_anchor",
            "severity": "stop_and_reanchor",
            "detail": "receipt_anchor must be non-empty string",
        })

    # ── 5. Declared-vs-observed comparison (if declared provided) ────────
    if declared is not None:
        mid = receipt.get("model_id", "")
        declared_lc = declared.get("lifecycle_status", "")
        lc_class = _classify_lifecycle(declared_lc)

        # Active model: if collection was authorized but receipt not collected → BLOCK
        if lc_class == "active":
            cs = receipt.get("collection_status", "")
            if cs != "collected":
                findings.append({
                    "type": "worker_attest_missing",
                    "severity": "blocked",
                    "detail": (
                        f"Active model '{mid}' has collection_status='{cs}' "
                        f"(expected 'collected'). Worker attestation was not "
                        f"produced despite authorized collection."
                    ),
                    "model_id": mid,
                })

        # Active model: observed runtime_visible must be True, observed
        # credential_status must be 'present'
        if lc_class == "active":
            rv_obs = receipt.get("runtime_visible_observed")
            env_obs = receipt.get("env_loaded_observed")
            cs_obs = receipt.get("credential_status_observed", "")

            if rv_obs is False:
                findings.append({
                    "type": "active_runtime_not_visible",
                    "severity": "blocked",
                    "detail": (
                        f"Active model '{mid}' observed runtime_visible=False "
                        f"(expected True)"
                    ),
                    "model_id": mid,
                })
            if env_obs is False:
                findings.append({
                    "type": "active_env_not_loaded",
                    "severity": "blocked",
                    "detail": (
                        f"Active model '{mid}' observed env_loaded=False "
                        f"(expected True)"
                    ),
                    "model_id": mid,
                })
            if cs_obs == "absent":
                findings.append({
                    "type": "active_credential_absent",
                    "severity": "blocked",
                    "detail": (
                        f"Active model '{mid}' observed credential_status='absent'"
                    ),
                    "model_id": mid,
                })

            # Provider namespace mismatch
            declared_pn = declared.get("provider_namespace", "")
            observed_pn = receipt.get("provider_namespace", "")
            if declared_pn and observed_pn and declared_pn != observed_pn:
                findings.append({
                    "type": "namespace_mismatch",
                    "severity": "blocked",
                    "detail": (
                        f"Declared provider_namespace='{declared_pn}' "
                        f"!= observed='{observed_pn}' for '{mid}'"
                    ),
                    "model_id": mid,
                })

            # Unknown namespace
            if observed_pn and observed_pn not in (
                "anthropic", "dashscope", "deepseek", "deepseek-plan",
                "google", "minimax", "minimax-plan", "moonshot",
                "openai", "opencode", "opencode-go", "volcengine",
                "xai", "xiaomi"
            ):
                findings.append({
                    "type": "unknown_namespace",
                    "severity": "blocked",
                    "detail": (
                        f"Observed provider_namespace='{observed_pn}' is not in frozen set"
                    ),
                    "model_id": mid,
                })

        elif lc_class == "deu":
            # DEU: live evidence is informational, never promotion
            findings.append({
                "type": "deu_live_evidence",
                "severity": "warn",
                "detail": (
                    f"DEU model '{mid}' has live runtime evidence "
                    f"(informational only; no promotion)"
                ),
                "model_id": mid,
            })

    # ── 6. Resolve verdict ───────────────────────────────────────────────
    severities = {f.get("severity", "") for f in findings}
    if "stop_secret_risk" in severities:
        verdict = "G_L3R_STOP_SECRET_RISK"
    elif "stop_and_reanchor" in severities:
        verdict = "G_L3R_STOP_AND_REANCHOR"
    elif "blocked" in severities:
        verdict = "G_L3R_BLOCKED"
    elif "warn" in severities:
        verdict = "G_L3R_PASS_WITH_WARN"
    else:
        verdict = "G_L3R_PASS"

    return {
        "verdict": verdict,
        "findings": findings,
        "leak_scan": leak,
        "verdict_priority_rank": _VERDICT_PRIORITY.get(verdict, 0),
        "is_merge_blocker": verdict in _FAIL_CLOSED_VERDICTS,
    }


def _classify_lifecycle(status: str) -> str:
    if status in ACTIVE_LIFECYCLE_STATUSES:
        return "active"
    if status in DEU_LIFECYCLE_STATUSES:
        return "deu"
    return "other"


def validate_operator_gate(gate: dict) -> dict:
    """Validate that a proposed operator gate satisfies the G-L3R contract.

    Pure validation: checks fields, does NOT authorize anything."""
    errors: list[str] = []

    if not isinstance(gate, dict):
        return {"valid": False, "errors": ["gate must be a dict"]}

    required = ("operator_approval_id", "node", "collector_mode")
    for f in required:
        if f not in gate:
            errors.append(f"Missing required field: '{f}'")

    oa = gate.get("operator_approval_id", "")
    if not isinstance(oa, str) or not oa.strip():
        errors.append("operator_approval_id must be non-empty string")

    node = gate.get("node", "")
    if node and node not in VALID_NODES:
        errors.append(f"Invalid node '{node}'")

    cm = gate.get("collector_mode", "")
    if cm and cm not in VALID_COLLECTOR_MODES:
        errors.append(f"Invalid collector_mode '{cm}'")

    # Forbidden: model_call_verified / operator_approved promotion
    if gate.get("promote_model_call_verified"):
        errors.append(
            "Gate must NOT enable model_call_verified promotion"
        )
    if gate.get("promote_operator_approved"):
        errors.append(
            "Gate must NOT enable operator_approved promotion"
        )

    # Forbidden: automatic write-back
    if gate.get("write_back_to_capability_yaml"):
        errors.append(
            "Gate must NOT enable write-back to node_model_capability.yaml"
        )

    return {"valid": not errors, "errors": errors}


# ═══════════════════════════════════════════════════════════════════════════════
# Plan rendering
# ═══════════════════════════════════════════════════════════════════════════════


def build_plan() -> dict:
    """Build the canonical G-L3R plan document.

    No live collection; this is a plan / schema / validator."""
    return {
        "schema_version": SCHEMA_VERSION,
        "source": "worker_attest_layer3_runtime_plan",
        "kind": "plan_only_no_execution",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope_note": (
            "G-L3R plan/schema/validator. Defines sanctioned live runtime "
            "receipt semantics. Does NOT perform live collection, SSH, model "
            "calls, credential provisioning, node sync, readiness expansion, "
            "DEU assignment, new namespace enablement, or runtime field "
            "promotion. A separate operator-authorized PR is required to "
            "actually run live collection."
        ),
        "boundary": get_l3f_l3r_boundary(),
        "operator_gates": get_operator_gate_contract(),
        "cost_strategy": get_cost_strategy(),
        "live_receipt_required_fields": sorted(LIVE_RECEIPT_REQUIRED_FIELDS),
        "live_receipt_redaction_subflags": list(REDACTION_SUBFLAGS),
        "live_receipt_forbidden_flags": list(FORBIDDEN_FLAGS),
        "valid_nodes": sorted(VALID_NODES),
        "valid_collector_modes": sorted(VALID_COLLECTOR_MODES),
        "valid_collection_status": sorted(VALID_COLLECTION_STATUS),
        "verdict_namespace": "G_L3R_*",
        "verdicts": [
            "G_L3R_NOT_COLLECTED",
            "G_L3R_PASS",
            "G_L3R_PASS_WITH_WARN",
            "G_L3R_BLOCKED",
            "G_L3R_STOP_SECRET_RISK",
            "G_L3R_STOP_AND_REANCHOR",
        ],
        "verdict_priority": {
            k: _VERDICT_PRIORITY[k] for k in sorted(
                _VERDICT_PRIORITY.keys(),
                key=lambda x: -_VERDICT_PRIORITY[x]
            )
        },
        "merge_blocking_verdicts": [
            "G_L3R_STOP_SECRET_RISK",
            "G_L3R_STOP_AND_REANCHOR",
            "G_L3R_BLOCKED",
        ],
        "runtime_fields_forbidden_to_write": sorted(RUNTIME_FIELDS_FORBIDDEN_TO_WRITE),
        "deepseek_v4_pro_handling": (
            "Identical to all other active models in G-L3R; no special-casing."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Self-check
# ═══════════════════════════════════════════════════════════════════════════════


def self_check() -> dict:
    """In-process self-check. No live collection, no I/O beyond import."""
    checks: list[dict] = []

    # sc-01: schema_version present
    checks.append({
        "name": "sc-01-schema-version",
        "passed": SCHEMA_VERSION == "1.0",
        "detail": f"schema={SCHEMA_VERSION}",
    })

    # sc-02: build_plan produces a valid dict
    try:
        plan = build_plan()
        ok = isinstance(plan, dict) and "boundary" in plan
        checks.append({
            "name": "sc-02-build-plan",
            "passed": ok,
            "detail": f"plan keys={len(plan)}",
        })
    except Exception as e:
        checks.append({
            "name": "sc-02-build-plan",
            "passed": False,
            "detail": f"error={type(e).__name__}: {e}",
        })
        plan = {}

    # sc-03: G_L3F_* verdicts are NOT in G_L3R verdict list
    g_l3r_verdicts = plan.get("verdicts", [])
    g_l3f_leak = any(v.startswith("G_L3F_") for v in g_l3r_verdicts)
    g_l3r_leak = any(v.startswith("E2E_") for v in g_l3r_verdicts)
    checks.append({
        "name": "sc-03-verdict-namespace-isolation",
        "passed": not g_l3f_leak and not g_l3r_leak,
        "detail": f"G_L3R namespace={'CLEAN' if (not g_l3f_leak and not g_l3r_leak) else 'POLLUTED'}",
    })

    # sc-04: G_L3F vs G_L3R boundary documented
    boundary = plan.get("boundary", {})
    checks.append({
        "name": "sc-04-boundary-documented",
        "passed": "G_L3F" in boundary and "G_L3R" in boundary,
        "detail": "G_L3F/G_L3R both present in boundary",
    })

    # sc-05: Operator gates documented
    gates = plan.get("operator_gates", {})
    checks.append({
        "name": "sc-05-operator-gates-documented",
        "passed": "approval_required_fields" in gates,
        "detail": f"gates keys={list(gates.keys())[:3]}",
    })

    # sc-06: Cost strategy documents default low-cost models
    cost = plan.get("cost_strategy", {})
    defaults = cost.get("default_models_for_g_l4", [])
    checks.append({
        "name": "sc-06-cost-strategy-low-cost-default",
        "passed": any("deepseek" in m.lower() or "mimo" in m.lower() for m in defaults),
        "detail": f"defaults={defaults}",
    })

    # sc-07: Receipt validation rejects malformed receipt
    bad_receipt = {"schema_version": "1.0"}  # missing fields
    v = validate_live_receipt_schema(bad_receipt)
    checks.append({
        "name": "sc-07-receipt-validation-rejects-malformed",
        "passed": not v["valid"] and len(v["errors"]) > 0,
        "detail": f"errors={len(v['errors'])}",
    })

    # sc-08: Receipt validation accepts well-formed receipt
    good_receipt = {
        "schema_version": SCHEMA_VERSION,
        "node": "21bao",
        "model_id": "opencode-go-deepseek-v4-flash",
        "provider_namespace": "opencode-go",
        "runtime_provider": "opencode-go",
        "alias": "opencode-ds4flash",
        "runtime_visible_observed": True,
        "env_loaded_observed": True,
        "credential_status_observed": "present",
        "endpoint_ref_observed": "OPENCODE_GO_BASE_URL",
        "redaction_status": {sf: True for sf in REDACTION_SUBFLAGS},
        "forbidden_operation_flags": {f: False for f in FORBIDDEN_FLAGS},
        "collector_mode": "real_read",
        "operator_approval_id": "op-approval-test-001",
        "receipt_anchor": "rcpt-anchor-abc123",
        "source_node": "21bao",
        "collection_status": "collected",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    v = validate_live_receipt_schema(good_receipt)
    checks.append({
        "name": "sc-08-receipt-validation-accepts-good",
        "passed": v["valid"] and not v["errors"],
        "detail": f"errors={len(v['errors'])} warnings={len(v['warnings'])}",
    })

    # sc-09: evaluate_live_receipt emits G_L3R_* verdict
    declared = {
        "lifecycle_status": "enabled_assigned",
        "provider_namespace": "opencode-go",
    }
    eval_result = evaluate_live_receipt(good_receipt, declared)
    checks.append({
        "name": "sc-09-evaluate-emits-g-l3r-verdict",
        "passed": eval_result["verdict"].startswith("G_L3R_"),
        "detail": f"verdict={eval_result['verdict']}",
    })

    # sc-10: Operator gate validation rejects missing approval_id
    bad_gate = {"node": "21bao", "collector_mode": "real_read"}
    gv = validate_operator_gate(bad_gate)
    checks.append({
        "name": "sc-10-gate-rejects-missing-approval",
        "passed": not gv["valid"],
        "detail": f"errors={len(gv['errors'])}",
    })

    # sc-11: DeepSeek V4 Pro treated same as other active models
    v4_receipt = dict(good_receipt)
    v4_receipt["model_id"] = "opencode-go-deepseek-v4-pro"
    v4_declared = {"lifecycle_status": "enabled_assigned",
                   "provider_namespace": "opencode-go"}
    v4_eval = evaluate_live_receipt(v4_receipt, v4_declared)
    other_receipt = dict(good_receipt)
    other_receipt["model_id"] = "opencode-go-glm-5-1"
    other_eval = evaluate_live_receipt(other_receipt, declared)
    checks.append({
        "name": "sc-11-v4-pro-not-special-cased",
        "passed": v4_eval["verdict"] == other_eval["verdict"],
        "detail": f"v4_pro={v4_eval['verdict']} other={other_eval['verdict']}",
    })

    # sc-12: No leak in plan output
    plan_text = _flatten_text(plan)
    plan_leak = _scan_leaks(plan_text)
    checks.append({
        "name": "sc-12-no-leak-in-plan",
        "passed": not plan_leak["any_leak"],
        "detail": f"secret={plan_leak['secret_leak']} url={plan_leak['url_leak']} path={plan_leak['path_leak']}",
    })

    # sc-13: Verdict priority ordering
    p = _VERDICT_PRIORITY
    ordering_ok = (
        p["G_L3R_STOP_SECRET_RISK"] > p["G_L3R_STOP_AND_REANCHOR"] >
        p["G_L3R_BLOCKED"] > p["G_L3R_NOT_COLLECTED"] >
        p["G_L3R_PASS_WITH_WARN"] > p["G_L3R_PASS"]
    )
    checks.append({
        "name": "sc-13-verdict-priority-ordering",
        "passed": ordering_ok,
        "detail": "ordering matches STOP_SECRET_RISK > STOP_AND_REANCHOR > BLOCKED > NOT_COLLECTED > PASS_WITH_WARN > PASS",
    })

    # sc-14: Runtime fields forbidden_to_write documented
    rf = plan.get("runtime_fields_forbidden_to_write", [])
    expected = {"runtime_visible", "env_loaded", "model_call_verified", "operator_approved"}
    checks.append({
        "name": "sc-14-runtime-fields-forbidden",
        "passed": expected.issubset(set(rf)),
        "detail": f"forbidden={rf}",
    })

    # sc-15: DEU live evidence is WARN only
    deu_receipt = dict(good_receipt)
    deu_receipt["model_id"] = "anthropic-claude-opus-4"
    deu_receipt["provider_namespace"] = "anthropic"
    deu_declared = {
        "lifecycle_status": "declared_enabled_unassigned",
        "provider_namespace": "anthropic",
    }
    deu_eval = evaluate_live_receipt(deu_receipt, deu_declared)
    deu_is_warn = any(f.get("severity") == "warn" for f in deu_eval["findings"])
    deu_not_blocked = not any(f.get("severity") == "blocked" for f in deu_eval["findings"])
    deu_not_stop = not any(f.get("severity") in ("stop_secret_risk", "stop_and_reanchor") for f in deu_eval["findings"])
    checks.append({
        "name": "sc-15-deu-live-evidence-warn-only",
        "passed": deu_is_warn and deu_not_blocked and deu_not_stop,
        "detail": f"DEU verdict={deu_eval['verdict']} (expected PASS_WITH_WARN)",
    })

    # sc-16: worker_attest_missing when active model collection_status != 'collected'
    missing_receipt = dict(good_receipt)
    missing_receipt["collection_status"] = "not_collected"
    missing_eval = evaluate_live_receipt(missing_receipt, declared)
    missing_has_error = any(f.get("type") == "worker_attest_missing" for f in missing_eval["findings"])
    checks.append({
        "name": "sc-16-worker-attest-missing-blocks",
        "passed": missing_has_error,
        "detail": f"collection_status=not_collected → {'BLOCKED' if missing_has_error else 'NOT_BLOCKED'}",
    })

    passed_count = sum(1 for c in checks if c["passed"])
    total = len(checks)

    return {
        "schema_version": SCHEMA_VERSION,
        "name": "worker_attest_layer3_runtime_plan",
        "status": "PASS" if passed_count == total else "FAIL",
        "passed_count": passed_count,
        "total": total,
        "detail": f"{passed_count}/{total} passed",
        "checks": checks,
        "plan_kind": "plan_only_no_execution",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="worker_attest_layer3_runtime_plan.py",
        description="G-L3R plan/schema/validator (plan only, no live execution).",
    )
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=["run", "self-check", "boundary", "gates", "cost", "validate-receipt"],
        default="self-check",
        help="Command: run (full plan) / self-check / boundary / gates / cost / validate-receipt",
    )
    parser.add_argument(
        "--receipt-file",
        default=None,
        help="Path to receipt JSON (for validate-receipt)",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = _parse_args()

    if args.cmd == "run":
        plan = build_plan()
        print(json.dumps(plan, indent=2, default=str))
    elif args.cmd == "boundary":
        print(json.dumps(get_l3f_l3r_boundary(), indent=2, default=str))
    elif args.cmd == "gates":
        print(json.dumps(get_operator_gate_contract(), indent=2, default=str))
    elif args.cmd == "cost":
        print(json.dumps(get_cost_strategy(), indent=2, default=str))
    elif args.cmd == "validate-receipt":
        if not args.receipt_file:
            print("error: --receipt-file required", file=sys.stderr)
            return 2
        try:
            with open(args.receipt_file, "r", encoding="utf-8") as f:
                receipt = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(json.dumps({"valid": False, "errors": [f"load error: {e}"]}))
            return 1
        schema_result = validate_live_receipt_schema(receipt)
        eval_result = evaluate_live_receipt(receipt)
        print(json.dumps(
            {"schema_validation": schema_result, "evaluation": eval_result},
            indent=2, default=str,
        ))
    else:
        result = self_check()
        print(json.dumps(result, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())