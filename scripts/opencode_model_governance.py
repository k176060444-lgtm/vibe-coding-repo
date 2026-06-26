#!/usr/bin/env python3
"""Model Pool Governance Wrapper v1.0.0

Unified governance entry point for all model pool mutations:
add / delete / enable / disable / retire.

Enforces approval boundary: no state-changing mutation without valid approval_id.
Integrates credential status resolver for add/enable actions.

Usage:
    python scripts/opencode_model_governance.py --self-check
    python scripts/opencode_model_governance.py plan --action add --model-id ID
    python scripts/opencode_model_governance.py execute --action add --model-id ID --approval-id ID --operator-id ID

Contract: docs/MODEL_POOL_DISTRIBUTION_CONTRACT.md
"""

__version__ = "1.0.0"

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(__file__))

from opencode_model_pool import ModelPool, DANGEROUS_FIELD_NAMES, DANGEROUS_KEY_PATTERNS
from credential_status_resolver import resolve_credential, validate_secret_ref

# --- Constants ---

GOVERNANCE_VERSION = __version__

VALID_ACTIONS = {"add", "delete", "enable", "disable", "retire"}

RISK_LEVELS = {
    "add": "medium",
    "delete": "high",
    "enable": "medium",
    "disable": "medium",
    "retire": "medium",
}

# --- Validation ---


def validate_action(action: str) -> tuple[bool, str]:
    """Validate action is recognized."""
    if action not in VALID_ACTIONS:
        return False, f"invalid action: {action}. Valid: {sorted(VALID_ACTIONS)}"
    return True, ""


def validate_approval_id(approval_id: str) -> tuple[bool, str]:
    """Validate approval_id format (basic check)."""
    if not approval_id or not isinstance(approval_id, str):
        return False, "approval_id must be a non-empty string"
    if len(approval_id) < 5:
        return False, "approval_id too short"
    return True, ""


# --- Credential Validation ---


def validate_credential_for_action(
    action: str,
    model_entry: Optional[dict] = None,
    secret_ref: str = "",
    resolver_backend: str = "fixture",
    resolver_fixture: Optional[dict] = None,
    resolver_fixture_path: Optional[str] = None,
) -> dict:
    """Validate credential status for governance action.

    Args:
        action: Governance action (add/enable/disable/retire/delete)
        model_entry: Existing model entry (for enable/disable/retire/delete)
        secret_ref: Secret reference to validate (for add)
        resolver_backend: Backend for resolver
        resolver_fixture: Inline fixture data
        resolver_fixture_path: Path to fixture file

    Returns:
        {
            "valid": bool,
            "credential_status": str,
            "metadata": dict or None,
            "warning": str or None,
            "effective_available": bool,
        }
    """
    # Determine which secret_ref to check
    ref_to_check = secret_ref
    if not ref_to_check and model_entry:
        ref_to_check = model_entry.get("secret_ref", "")

    # If no secret_ref, nothing to validate
    if not ref_to_check:
        return {
            "valid": True,
            "credential_status": "unknown",
            "metadata": None,
            "warning": "no secret_ref to validate",
            "effective_available": False,
        }

    # Validate secret_ref format
    valid, err = validate_secret_ref(ref_to_check)
    if not valid:
        return {
            "valid": False,
            "credential_status": "unknown",
            "metadata": None,
            "warning": f"invalid secret_ref: {err}",
            "effective_available": False,
        }

    # Resolve credential
    try:
        result = resolve_credential(
            ref_to_check,
            backend=resolver_backend,
            fixture_data=resolver_fixture,
            fixture_path=resolver_fixture_path,
        )
    except (ValueError, RuntimeError) as e:
        return {
            "valid": False,
            "credential_status": "unknown",
            "metadata": None,
            "warning": f"resolver error: {str(e)[:100]}",
            "effective_available": False,
        }

    cred_status = result.get("credential_status", "unknown")
    metadata = result.get("metadata", {})

    # Safe metadata subset (no sensitive fields)
    safe_metadata = {
        "provider": metadata.get("provider", "unknown"),
        "alias": metadata.get("alias", "unknown"),
        "source": metadata.get("source", "unknown"),
        "last_checked": metadata.get("last_checked", ""),
        "status_reason": metadata.get("status_reason", ""),
        "resolver_version": metadata.get("resolver_version", ""),
    }

    # Determine effective_available
    effective_available = cred_status in ("valid", "not-configured")

    # Generate warning for non-available statuses
    warning = None
    if cred_status in ("missing", "expired", "unknown"):
        warning = f"credential_status={cred_status}; model will not be available for execution"
        if action == "enable":
            warning += "; effective_available=false"

    return {
        "valid": True,  # resolver succeeded (even if status is missing/expired)
        "credential_status": cred_status,
        "metadata": safe_metadata,
        "warning": warning,
        "effective_available": effective_available,
    }


# --- Action Plan ---


def generate_action_plan(action: str, model_id: str,
                         pool: ModelPool,
                         approval_id: str = None) -> dict:
    """Generate action plan without executing mutation.

    Returns action plan with risk_level, requires_approval, and blocked_reason.
    """
    valid, err = validate_action(action)
    if not valid:
        return {"error": err, "status": "invalid"}

    risk_level = RISK_LEVELS.get(action, "medium")
    requires_approval = True  # All actions require approval

    # Check if model exists (for non-add actions)
    if action != "add":
        if model_id not in pool.models:
            return {
                "action": action,
                "model_id": model_id,
                "status": "blocked",
                "blocked_reason": "model_not_found",
                "risk_level": risk_level,
                "requires_approval": requires_approval,
            }

    # For add, check if model already exists
    if action == "add":
        if model_id in pool.models:
            return {
                "action": action,
                "model_id": model_id,
                "status": "blocked",
                "blocked_reason": "model_already_exists",
                "risk_level": risk_level,
                "requires_approval": requires_approval,
            }

    # If approval required but not provided
    if requires_approval and not approval_id:
        return {
            "action": action,
            "model_id": model_id,
            "status": "approval_required",
            "risk_level": risk_level,
            "requires_approval": True,
            "message": f"action '{action}' requires approval_id",
        }

    return {
        "action": action,
        "model_id": model_id,
        "status": "ready",
        "risk_level": risk_level,
        "requires_approval": requires_approval,
    }


# --- Governance Execute ---


def execute_governance(action: str, model_id: str,
                       operator_id: str,
                       pool: ModelPool,
                       approval_id: str = None,
                       model_params: dict = None,
                       active_model_ids: set = None,
                       resolver_backend: str = "fixture",
                       resolver_fixture: dict = None,
                       resolver_fixture_path: str = None) -> dict:
    """Execute governance action with approval boundary.

    Args:
        action: One of add/delete/enable/disable/retire
        model_id: exact_model_id
        operator_id: Operator performing the action
        pool: ModelPool instance
        approval_id: Approval ID (required for delete)
        model_params: Parameters for add_model (endpoint, protocol, etc.)
        active_model_ids: Set of model IDs in active jobs (blocks delete)
        resolver_backend: Backend for credential resolver
        resolver_fixture: Inline fixture data for resolver
        resolver_fixture_path: Path to fixture file for resolver

    Returns:
        Governance result with action_plan, result, and audit
    """
    # Validate action
    valid, err = validate_action(action)
    if not valid:
        return {"error": err, "status": "invalid"}

    # Generate action plan
    plan = generate_action_plan(action, model_id, pool, approval_id)
    if plan.get("status") in ("invalid", "blocked"):
        return {
            "action": action,
            "model_id": model_id,
            "status": plan["status"],
            "action_plan": plan,
            "result": None,
            "audit": _build_audit(action, model_id, operator_id, approval_id, pool),
        }

    # If approval required but not provided
    if plan.get("requires_approval") and not approval_id:
        return {
            "action": action,
            "model_id": model_id,
            "status": "approval_required",
            "action_plan": plan,
            "result": None,
            "audit": _build_audit(action, model_id, operator_id, None, pool),
        }

    # --- Credential validation for add/enable ---
    credential_validation = None
    if action in ("add", "enable"):
        params = model_params or {}
        secret_ref = params.get("secret_ref", "")
        model_entry = pool.models.get(model_id) if action == "enable" else None

        credential_validation = validate_credential_for_action(
            action=action,
            model_entry=model_entry,
            secret_ref=secret_ref,
            resolver_backend=resolver_backend,
            resolver_fixture=resolver_fixture,
            resolver_fixture_path=resolver_fixture_path,
        )

        # If secret_ref validation failed (format/safety), block
        if not credential_validation["valid"]:
            return {
                "action": action,
                "model_id": model_id,
                "status": "blocked",
                "action_plan": plan,
                "result": {"error": credential_validation["warning"], "status": "blocked"},
                "credential_validation": credential_validation,
                "audit": _build_audit(action, model_id, operator_id, approval_id, pool),
            }

    # Execute mutation
    result = _execute_action(action, model_id, pool, model_params, active_model_ids,
                             approval_context={"approval_id": approval_id, "operator_id": operator_id})

    # Build response
    response = {
        "action": action,
        "model_id": model_id,
        "status": result.get("status", "executed"),
        "action_plan": plan,
        "result": result,
        "audit": _build_audit(action, model_id, operator_id, approval_id, pool),
    }

    # Attach credential validation if performed
    if credential_validation is not None:
        response["credential_validation"] = {
            "credential_status": credential_validation["credential_status"],
            "metadata": credential_validation["metadata"],
            "warning": credential_validation["warning"],
            "effective_available": credential_validation["effective_available"],
        }

        # For add: update the model entry's credential_status
        if action == "add" and "exact_model_id" in result:
            added_id = result["exact_model_id"]
            if added_id in pool.models:
                pool.models[added_id]["credential_status"] = credential_validation["credential_status"]
                pool.save()

    return response


def _execute_action(action: str, model_id: str, pool: ModelPool,
                    model_params: dict = None, active_model_ids: set = None,
                    approval_context: dict = None) -> dict:
    """Execute the actual pool mutation."""
    try:
        if action == "add":
            params = model_params or {}
            return pool.add_model(model_id, **params)
        elif action == "delete":
            return pool.delete_model(model_id, active_model_ids=active_model_ids,
                                     approval_context=approval_context)
        elif action == "enable":
            return pool.enable_model(model_id)
        elif action == "disable":
            return pool.disable_model(model_id)
        elif action == "retire":
            return pool.retire_model(model_id)
        else:
            return {"error": f"unknown action: {action}", "status": "invalid"}
    except ValueError as e:
        return {"error": str(e), "status": "blocked"}


def _build_audit(action: str, model_id: str, operator_id: str,
                 approval_id: str, pool: ModelPool) -> dict:
    """Build audit record."""
    return {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "operator_id": operator_id,
        "approval_id": approval_id,
        "action": action,
        "model_id": model_id,
        "pool_snapshot_sha256": pool.snapshot_sha256,
        "governance_version": GOVERNANCE_VERSION,
    }


# --- CLI ---


def self_check() -> dict:
    """Self-check: verify governance is importable."""
    return {
        "governance_version": GOVERNANCE_VERSION,
        "valid_actions": sorted(VALID_ACTIONS),
        "risk_levels": RISK_LEVELS,
        "status": "ok",
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        result = self_check()
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python opencode_model_governance.py --self-check")
        sys.exit(0)
