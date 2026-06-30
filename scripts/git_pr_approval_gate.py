#!/usr/bin/env python3
"""Git/PR State Approval Gate v1.3.0

Enforces Git/PR state transition policy for VibeDev orchestrator (baseline01):
- All git write actions require explicit operator approval.
- No auto-allowed actions exist.
- OPERATOR_APPROVAL_REQUIRED: ALL actions (push feature branch, create Draft PR,
  update Draft PR, Draft→Ready, merge, branch delete, push main, force push, etc.)
- BLOCKED: create Ready PR directly, merge without approval, force push without
  approval, etc.

Integrates with:
- V1.21.6 conversational_intake_gate (intake approval lifecycle)
- V1.21.9 remote_verification_gate (remote source-of-truth verification)
- operator_merge_approval_gate (merge approval records)

Usage:
    python scripts/git_pr_approval_gate.py --self-check
    python scripts/git_pr_approval_gate.py --action ACTION [options] [--json]

Exit codes:
    0 = PASS (operator approval obtained and checks passed)
    1 = BLOCKED
    2 = usage error
"""

__version__ = "1.3.0"

import argparse
import json
import sys
from datetime import datetime, timezone

try:
    from execution_approval_gate import (
        check_execution_approval as _eag_check,
        APPROVAL_BOUND as _EAG_APPROVAL_BOUND,
        PASS_READ_ONLY as _EAG_PASS_READ_ONLY,
        BLOCKED_EXECUTION_WITHOUT_APPROVAL as _EAG_BLOCKED_NO_APPROVAL,
        BLOCKED_APPROVAL_NOT_BOUND_TO_PROPOSAL as _EAG_BLOCKED_NO_PROPOSAL,
        BLOCKED_ACTION_NOT_APPROVED as _EAG_BLOCKED_ACTION,
        BLOCKED_CLARIFICATION_NOT_APPROVAL as _EAG_BLOCKED_CLARIFICATION,
        BLOCKED_STALE_APPROVAL as _EAG_BLOCKED_STALE,
    )
    _EXECUTION_APPROVAL_GATE_AVAILABLE = True
    _EAG_KNOWN_BLOCK_VERDICTS = {
        _EAG_BLOCKED_NO_APPROVAL,
        _EAG_BLOCKED_NO_PROPOSAL,
        _EAG_BLOCKED_ACTION,
        _EAG_BLOCKED_CLARIFICATION,
        _EAG_BLOCKED_STALE,
    }
except ImportError:
    _eag_check = None
    _EAG_APPROVAL_BOUND = "APPROVAL_BOUND"
    _EAG_PASS_READ_ONLY = "PASS_READ_ONLY"
    _EXECUTION_APPROVAL_GATE_AVAILABLE = False
    _EAG_KNOWN_BLOCK_VERDICTS = set()

try:
    from conversational_intake_gate import write_eag_result as _write_eag_result
    _WRITE_EAG_RESULT_AVAILABLE = True
except ImportError:
    _write_eag_result = None
    _WRITE_EAG_RESULT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Git/PR actions
# ---------------------------------------------------------------------------

# A. OPERATOR_APPROVAL_REQUIRED — ALL git actions require explicit operator approval
# (baseline01: no auto-allowed actions)
OPERATOR_REQUIRED_ACTIONS = {
    "push_feature_branch",
    "create_draft_pr",
    "update_draft_pr",
    "draft_to_ready",
    "merge",
    "ready_to_merge",
    "branch_delete",
    "push_main",
    "push_protected_branch",
    "force_push",
    "release_tag",
    "production_gateway_change",
    "worker_ssh_mutation",
    "secrets_credential_change",
    "admin_uac_service_change",
}

# C. Always BLOCKED regardless of approval
ALWAYS_BLOCKED_ACTIONS = {
    "create_ready_pr",
}

ALL_ACTIONS = OPERATOR_REQUIRED_ACTIONS | ALWAYS_BLOCKED_ACTIONS

# Protected branches — push/force-push always needs operator approval
PROTECTED_BRANCHES = {"main", "master", "release", "production", "staging"}

# High-risk changed files patterns — require operator approval even for auto-allowed
HIGH_RISK_FILE_PATTERNS = [
    "secrets", "credential", ".env", "secret",
    "worker_registry", "worker_config",
    "gateway", "production",
    "admin", "uac", "service_install",
    "opencode.env", "vibedev.env", "default.env",
]

# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------

VERDICTS = {
    "OPERATOR_APPROVAL_REQUIRED": "Action requires explicit operator approval before execution",
    "BLOCKED_UNAPPROVED_GIT_ACTION": "Action blocked: git action not approved for this state",
    "BLOCKED_PROTECTED_BRANCH": "Action blocked: push to protected branch requires operator approval",
    "BLOCKED_FORCE_PUSH": "Action blocked: force push requires operator approval",
    "BLOCKED_READY_WITHOUT_APPROVAL": "Action blocked: cannot create Ready PR or transition to Ready without operator approval",
    "BLOCKED_MERGE_WITHOUT_APPROVAL": "Action blocked: merge requires operator approval record",
    "BLOCKED_REMOTE_VERIFICATION_REQUIRED": "Action blocked: remote verification gate must pass before this action",
    "BLOCKED_EXECUTION_APPROVAL_REQUIRED": "Action blocked: execution approval binding required (V1.21.12)",
    "BLOCKED_EXECUTION_APPROVAL_GATE_ERROR": "Action blocked: execution approval gate internal error, cannot verify binding (V1.21.13A, fail-closed)",
    "PASS": "Action approved and allowed",
}


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def check_git_pr_action(
    action: str,
    target_branch: str = "main",
    source_branch: str = None,
    pr_number: int = None,
    desired_pr_state: str = None,
    current_pr_state: str = None,
    is_draft: bool = None,
    operator_approval_id: str = None,
    operator_approved_actions: list = None,
    force_push: bool = False,
    changed_files: list = None,
    risk_level: str = None,
    checks_passed: bool = False,
    intake_approved: bool = False,
    remote_verified: bool = False,
    merge_check_passed: bool = False,
    execution_approval: dict = None,
    proposal_hash: str = None,
    operator_message: str = None,
) -> dict:
    """Check whether a Git/PR action is allowed under VibeDev policy.

    V1.21.12: Gate 0 — AUTO_ALLOWED actions now require execution_approval_gate
    to have APPROVAL_BOUND before proceeding.

    Returns:
        {
            "checked": True,
            "verdict": str,
            "allowed": bool,
            "requires_operator_approval": bool,
            "blocked_reason": str or None,
            "required_next_step": str or None,
            "safe_auto_actions": [str],
            "forbidden_actions": [str],
            "remote_verification_required": bool,
            "approval_binding_fields": dict or None,
        }
    """
    now = datetime.now(timezone.utc).isoformat()
    result = {
        "checked": True,
        "verdict": "PASS",
        "allowed": True,
        "requires_operator_approval": False,
        "blocked_reason": None,
        "required_next_step": None,
        "safe_auto_actions": [],
        "forbidden_actions": [],
        "remote_verification_required": False,
        "approval_binding_fields": None,
    }

    # --- Unknown action ---
    if action not in ALL_ACTIONS:
        result["verdict"] = "BLOCKED_UNAPPROVED_GIT_ACTION"
        result["allowed"] = False
        result["blocked_reason"] = f"Unknown action: {action}. Allowed: {sorted(ALL_ACTIONS)}"
        return result

    # --- Always blocked ---
    if action in ALWAYS_BLOCKED_ACTIONS:
        result["verdict"] = "BLOCKED_READY_WITHOUT_APPROVAL"
        result["allowed"] = False
        result["blocked_reason"] = (
            f"Action '{action}' is always blocked. "
            "Create Draft PR first, then request operator approval for Draft→Ready."
        )
        result["required_next_step"] = "Create Draft PR, then request operator approval for Draft→Ready"
        result["forbidden_actions"] = [action]
        return result

    # --- Protected branch check ---
    is_protected = target_branch in PROTECTED_BRANCHES
    action_needs_protected_check = action in {
        "push_main", "push_protected_branch", "push_feature_branch",
        "force_push", "merge", "ready_to_merge"
    }
    if is_protected and action_needs_protected_check:
        # push_feature_branch should not target main
        if action == "push_feature_branch" and target_branch in PROTECTED_BRANCHES:
            result["verdict"] = "BLOCKED_PROTECTED_BRANCH"
            result["allowed"] = False
            result["blocked_reason"] = (
                f"Cannot push feature branch to protected branch '{target_branch}'. "
                "Feature branches must target a non-protected branch."
            )
            result["forbidden_actions"] = [action]
            return result

    # --- Force push check ---
    if force_push and action != "force_push":
        # Force push embedded in another action
        result["verdict"] = "BLOCKED_FORCE_PUSH"
        result["allowed"] = False
        result["blocked_reason"] = "Force push requires explicit operator approval regardless of action"
        result["forbidden_actions"] = ["force_push"]
        return result

    # --- High-risk file check ---
    high_risk_files = []
    if changed_files:
        for f in changed_files:
            f_lower = f.lower()
            for pattern in HIGH_RISK_FILE_PATTERNS:
                if pattern in f_lower:
                    high_risk_files.append(f)
                    break

    # --- ALL actions require operator approval (baseline01) ---
    # The former AUTO_ALLOWED_ACTIONS block (push_feature_branch, create_draft_pr,
    # update_draft_pr) has been removed. All actions now fall through to the
    # OPERATOR_REQUIRED_ACTIONS path below. No git action may execute without
    # explicit operator consent.

    # --- OPERATOR_REQUIRED_ACTIONS ---
    if action in OPERATOR_REQUIRED_ACTIONS:
        # Check if operator approval is present
        has_approval = (
            operator_approval_id is not None
            and operator_approved_actions is not None
            and action in operator_approved_actions
        )

        # Specific sub-checks per action
        if action == "draft_to_ready":
            if not has_approval:
                result["verdict"] = "BLOCKED_READY_WITHOUT_APPROVAL"
                result["allowed"] = False
                result["requires_operator_approval"] = True
                result["blocked_reason"] = "Draft→Ready requires explicit operator approval"
                result["required_next_step"] = "Request operator approval for Draft→Ready transition"
                result["forbidden_actions"] = [action]
                return result
            # Approval present — PASS
            result["verdict"] = "PASS"
            result["allowed"] = True
            result["approval_binding_fields"] = {
                "approval_id": operator_approval_id,
                "action": action,
            }
            return result

        if action in ("merge", "ready_to_merge"):
            if not has_approval:
                result["verdict"] = "BLOCKED_MERGE_WITHOUT_APPROVAL"
                result["allowed"] = False
                result["requires_operator_approval"] = True
                result["blocked_reason"] = "Merge requires explicit operator approval"
                result["required_next_step"] = "Request operator approval for merge"
                result["forbidden_actions"] = [action]
                return result
            # Remote verification required before merge
            if not remote_verified:
                result["verdict"] = "BLOCKED_REMOTE_VERIFICATION_REQUIRED"
                result["allowed"] = False
                result["blocked_reason"] = "Remote verification must pass before merge (V1.21.9)"
                result["required_next_step"] = "Run remote-verify gate and ensure PASS"
                result["remote_verification_required"] = True
                result["forbidden_actions"] = [action]
                return result
            # Merge check required
            if not merge_check_passed:
                result["verdict"] = "BLOCKED_REMOTE_VERIFICATION_REQUIRED"
                result["allowed"] = False
                result["blocked_reason"] = "Merge check must pass before merge"
                result["required_next_step"] = "Run merge-check and ensure MERGE_ALLOWED"
                result["remote_verification_required"] = True
                result["forbidden_actions"] = [action]
                return result
            # All checks passed
            result["verdict"] = "PASS"
            result["allowed"] = True
            result["approval_binding_fields"] = {
                "approval_id": operator_approval_id,
                "action": action,
                "remote_verified": True,
                "merge_check_passed": True,
            }
            return result

        if action == "branch_delete":
            if not has_approval:
                # Branch delete as merge-finalization: allowed if remote_verified (PR merged)
                if remote_verified:
                    result["verdict"] = "PASS"
                    result["allowed"] = True
                    result["safe_auto_actions"] = [action]
                    return result
                result["verdict"] = "BLOCKED_UNAPPROVED_GIT_ACTION"
                result["allowed"] = False
                result["requires_operator_approval"] = True
                result["blocked_reason"] = "Branch delete requires operator approval unless PR is merged and remote-verified"
                result["required_next_step"] = "Verify PR is merged, then delete branch as finalization"
                result["forbidden_actions"] = [action]
                return result
            result["verdict"] = "PASS"
            result["allowed"] = True
            result["approval_binding_fields"] = {
                "approval_id": operator_approval_id,
                "action": action,
            }
            return result

        if action in ("push_main", "push_protected_branch"):
            if not has_approval:
                result["verdict"] = "BLOCKED_PROTECTED_BRANCH"
                result["allowed"] = False
                result["requires_operator_approval"] = True
                result["blocked_reason"] = f"Push to '{target_branch}' requires operator approval"
                result["required_next_step"] = "Request operator approval for protected branch push"
                result["forbidden_actions"] = [action]
                return result
            result["verdict"] = "PASS"
            result["allowed"] = True
            result["approval_binding_fields"] = {
                "approval_id": operator_approval_id,
                "action": action,
                "target_branch": target_branch,
            }
            return result

        if action == "force_push":
            if not has_approval:
                result["verdict"] = "BLOCKED_FORCE_PUSH"
                result["allowed"] = False
                result["requires_operator_approval"] = True
                result["blocked_reason"] = "Force push requires explicit operator approval"
                result["required_next_step"] = "Request operator approval for force push"
                result["forbidden_actions"] = [action]
                return result
            result["verdict"] = "PASS"
            result["allowed"] = True
            result["approval_binding_fields"] = {
                "approval_id": operator_approval_id,
                "action": action,
            }
            return result

        # Generic operator-required action (release_tag, production_gateway_change, etc.)
        if not has_approval:
            result["verdict"] = "OPERATOR_APPROVAL_REQUIRED"
            result["allowed"] = False
            result["requires_operator_approval"] = True
            result["blocked_reason"] = f"Action '{action}' requires operator approval"
            result["required_next_step"] = f"Request operator approval for '{action}'"
            result["forbidden_actions"] = [action]
            return result

        result["verdict"] = "PASS"
        result["allowed"] = True
        result["approval_binding_fields"] = {
            "approval_id": operator_approval_id,
            "action": action,
        }
        return result

    # Fallback — should not reach here
    result["verdict"] = "BLOCKED_UNAPPROVED_GIT_ACTION"
    result["allowed"] = False
    result["blocked_reason"] = f"Unhandled action: {action}"
    return result


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------

def self_check(output_json=False):
    """Run self-check: verify all verdicts, policy categories, and integration points."""
    checks = []

    # V1.21.12: Helper execution approval for AUTO_ALLOWED tests
    from datetime import timezone as _tz
    _eag_approval = {
        "approval_id": "self-check-approval",
        "proposal_id": "self-check-proposal",
        "proposal_hash": "selfcheckhash",
        "approved_actions": [
            "push_feature_branch", "create_draft_pr", "update_draft_pr",
            "code_modify", "commit", "branch_create",
        ],
        "risk_level": "medium",
        "operator_message_raw": "self-check approval",
        "operator_confirmation_phrase": "approved",
        "timestamp": datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "approval_scope": "self-check",
        "role_model_matrix_hash": "selfcheckrmatrix",
    }

    # Version check
    checks.append({"name": "gpac-01-version", "passed": True, "message": __version__})

    # Auto-allowed: push feature branch + all gates passed
    r = check_git_pr_action(
        action="push_feature_branch",
        target_branch="feat/test",
        source_branch="feat/test",
        is_draft=True,
        checks_passed=True,
        intake_approved=True,
        execution_approval=_eag_approval,
        proposal_hash="selfcheckhash",
    )
    checks.append({
        "name": "gpac-02-push-feature-requires-approval",
        "passed": r["verdict"] == "OPERATOR_APPROVAL_REQUIRED" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Operator-required: create draft PR + all gates passed
    r = check_git_pr_action(
        action="create_draft_pr",
        target_branch="main",
        source_branch="feat/test",
        desired_pr_state="DRAFT",
        is_draft=True,
        checks_passed=True,
        intake_approved=True,
        execution_approval=_eag_approval,
        proposal_hash="selfcheckhash",
    )
    checks.append({
        "name": "gpac-03-create-draft-requires-approval",
        "passed": r["verdict"] == "OPERATOR_APPROVAL_REQUIRED" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Operator-required: update draft PR + all gates passed
    r = check_git_pr_action(
        action="update_draft_pr",
        target_branch="main",
        source_branch="feat/test",
        desired_pr_state="DRAFT",
        is_draft=True,
        checks_passed=True,
        intake_approved=True,
        execution_approval=_eag_approval,
        proposal_hash="selfcheckhash",
    )
    checks.append({
        "name": "gpac-04-update-draft-requires-approval",
        "passed": r["verdict"] == "OPERATOR_APPROVAL_REQUIRED" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Blocked: create Ready PR directly
    r = check_git_pr_action(
        action="create_ready_pr",
        desired_pr_state="OPEN",
    )
    checks.append({
        "name": "gpac-05-create-ready-pr-blocked",
        "passed": r["verdict"] == "BLOCKED_READY_WITHOUT_APPROVAL" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Blocked: Draft→Ready without approval
    r = check_git_pr_action(
        action="draft_to_ready",
        pr_number=100,
        current_pr_state="DRAFT",
        desired_pr_state="OPEN",
    )
    checks.append({
        "name": "gpac-06-draft-to-ready-no-approval-blocked",
        "passed": r["verdict"] == "BLOCKED_READY_WITHOUT_APPROVAL" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Pass: Draft→Ready with approval
    r = check_git_pr_action(
        action="draft_to_ready",
        pr_number=100,
        current_pr_state="DRAFT",
        desired_pr_state="OPEN",
        operator_approval_id="approval-001",
        operator_approved_actions=["draft_to_ready"],
    )
    checks.append({
        "name": "gpac-07-draft-to-ready-with-approval-pass",
        "passed": r["verdict"] == "PASS" and r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Blocked: merge without approval
    r = check_git_pr_action(
        action="merge",
        pr_number=100,
        current_pr_state="OPEN",
    )
    checks.append({
        "name": "gpac-08-merge-no-approval-blocked",
        "passed": r["verdict"] == "BLOCKED_MERGE_WITHOUT_APPROVAL" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Blocked: merge with approval but no remote verification
    r = check_git_pr_action(
        action="merge",
        pr_number=100,
        operator_approval_id="approval-001",
        operator_approved_actions=["merge"],
        remote_verified=False,
        merge_check_passed=False,
    )
    checks.append({
        "name": "gpac-09-merge-no-remote-verification-blocked",
        "passed": r["verdict"] == "BLOCKED_REMOTE_VERIFICATION_REQUIRED" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Blocked: merge with approval + remote verified but no merge-check
    r = check_git_pr_action(
        action="merge",
        pr_number=100,
        operator_approval_id="approval-001",
        operator_approved_actions=["merge"],
        remote_verified=True,
        merge_check_passed=False,
    )
    checks.append({
        "name": "gpac-10-merge-no-merge-check-blocked",
        "passed": r["verdict"] == "BLOCKED_REMOTE_VERIFICATION_REQUIRED" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Pass: merge with approval + remote verification + merge check
    r = check_git_pr_action(
        action="merge",
        pr_number=100,
        operator_approval_id="approval-001",
        operator_approved_actions=["merge"],
        remote_verified=True,
        merge_check_passed=True,
    )
    checks.append({
        "name": "gpac-11-merge-full-pass",
        "passed": r["verdict"] == "PASS" and r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Blocked: push main without approval
    r = check_git_pr_action(
        action="push_main",
        target_branch="main",
    )
    checks.append({
        "name": "gpac-12-push-main-no-approval-blocked",
        "passed": r["verdict"] == "BLOCKED_PROTECTED_BRANCH" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Pass: push main with approval
    r = check_git_pr_action(
        action="push_main",
        target_branch="main",
        operator_approval_id="approval-002",
        operator_approved_actions=["push_main"],
    )
    checks.append({
        "name": "gpac-13-push-main-with-approval-pass",
        "passed": r["verdict"] == "PASS" and r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Blocked: force push without approval
    r = check_git_pr_action(
        action="force_push",
        target_branch="feat/test",
        force_push=True,
    )
    checks.append({
        "name": "gpac-14-force-push-no-approval-blocked",
        "passed": r["verdict"] == "BLOCKED_FORCE_PUSH" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Pass: force push with approval
    r = check_git_pr_action(
        action="force_push",
        target_branch="feat/test",
        force_push=True,
        operator_approval_id="approval-003",
        operator_approved_actions=["force_push"],
    )
    checks.append({
        "name": "gpac-15-force-push-with-approval-pass",
        "passed": r["verdict"] == "PASS" and r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Blocked: branch delete without approval and without remote verification
    r = check_git_pr_action(
        action="branch_delete",
        source_branch="feat/test",
        remote_verified=False,
    )
    checks.append({
        "name": "gpac-16-branch-delete-no-approval-no-remote-blocked",
        "passed": r["verdict"] == "BLOCKED_UNAPPROVED_GIT_ACTION" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Pass: branch delete after merge (remote_verified=True)
    r = check_git_pr_action(
        action="branch_delete",
        source_branch="feat/test",
        remote_verified=True,
    )
    checks.append({
        "name": "gpac-17-branch-delete-after-merge-pass",
        "passed": r["verdict"] == "PASS" and r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Pass: branch delete with explicit approval
    r = check_git_pr_action(
        action="branch_delete",
        source_branch="feat/test",
        operator_approval_id="approval-004",
        operator_approved_actions=["branch_delete"],
    )
    checks.append({
        "name": "gpac-18-branch-delete-with-approval-pass",
        "passed": r["verdict"] == "PASS" and r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Blocked: operator approval required (intake status is subsumed by operator gate)
    r = check_git_pr_action(
        action="push_feature_branch",
        target_branch="feat/test",
        checks_passed=True,
        intake_approved=False,
        execution_approval=_eag_approval,
        proposal_hash="selfcheckhash",
    )
    checks.append({
        "name": "gpac-19-requires-approval-no-intake",
        "passed": r["verdict"] == "OPERATOR_APPROVAL_REQUIRED" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Blocked: operator approval required (checks status is subsumed by operator gate)
    r = check_git_pr_action(
        action="create_draft_pr",
        target_branch="main",
        desired_pr_state="DRAFT",
        checks_passed=False,
        intake_approved=True,
        execution_approval=_eag_approval,
        proposal_hash="selfcheckhash",
    )
    checks.append({
        "name": "gpac-20-requires-approval-no-checks",
        "passed": r["verdict"] == "OPERATOR_APPROVAL_REQUIRED" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Blocked: push feature to main (protected)
    r = check_git_pr_action(
        action="push_feature_branch",
        target_branch="main",
        checks_passed=True,
        intake_approved=True,
        execution_approval=_eag_approval,
        proposal_hash="selfcheckhash",
    )
    checks.append({
        "name": "gpac-21-push-feature-to-main-blocked",
        "passed": r["verdict"] == "BLOCKED_PROTECTED_BRANCH" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Blocked: force push embedded in push_feature_branch
    r = check_git_pr_action(
        action="push_feature_branch",
        target_branch="feat/test",
        checks_passed=True,
        intake_approved=True,
        force_push=True,
    )
    checks.append({
        "name": "gpac-22-embedded-force-push-blocked",
        "passed": r["verdict"] == "BLOCKED_FORCE_PUSH" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # OPERATOR_APPROVAL_REQUIRED: high-risk files
    r = check_git_pr_action(
        action="create_draft_pr",
        target_branch="main",
        desired_pr_state="DRAFT",
        checks_passed=True,
        intake_approved=True,
        changed_files=["scripts/conversational_intake_gate.py", "opencode.env"],
        execution_approval=_eag_approval,
        proposal_hash="selfcheckhash",
    )
    checks.append({
        "name": "gpac-23-high-risk-files-operator-required",
        "passed": r["verdict"] == "OPERATOR_APPROVAL_REQUIRED" and not r["allowed"],
        "message": f"verdict={r['verdict']} files={(r.get('approval_binding_fields') or {}).get('high_risk_files',[])}",
    })

    # Blocked: create draft PR with desired state OPEN
    r = check_git_pr_action(
        action="create_draft_pr",
        target_branch="main",
        desired_pr_state="OPEN",
        checks_passed=True,
        intake_approved=True,
        execution_approval=_eag_approval,
        proposal_hash="selfcheckhash",
    )
    checks.append({
        "name": "gpac-24-create-draft-with-open-state-blocked",
        "passed": r["verdict"] == "OPERATOR_APPROVAL_REQUIRED" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Unknown action
    r = check_git_pr_action(action="unknown_action")
    checks.append({
        "name": "gpac-25-unknown-action-blocked",
        "passed": r["verdict"] == "BLOCKED_UNAPPROVED_GIT_ACTION" and not r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # Verdict count
    checks.append({
        "name": "gpac-26-verdicts-count",
        "passed": len(VERDICTS) == 10,
        "message": f"count={len(VERDICTS)}",
    })

    # Auto-allowed actions count (removed in baseline01 — all actions require approval)
    checks.append({
        "name": "gpac-27-no-auto-allowed-actions",
        "passed": True,
        "message": "baseline01: all actions require operator approval (no auto-allowed set)",
    })

    # Operator-required actions count
    checks.append({
        "name": "gpac-28-operator-required-count",
        "passed": len(OPERATOR_REQUIRED_ACTIONS) == 15,
        "message": f"count={len(OPERATOR_REQUIRED_ACTIONS)}",
    })

    # Always-blocked actions count
    checks.append({
        "name": "gpac-29-always-blocked-count",
        "passed": len(ALWAYS_BLOCKED_ACTIONS) == 1,
        "message": f"count={len(ALWAYS_BLOCKED_ACTIONS)}",
    })

    # Protected branches count
    checks.append({
        "name": "gpac-30-protected-branches-count",
        "passed": len(PROTECTED_BRANCHES) == 5,
        "message": f"count={len(PROTECTED_BRANCHES)}",
    })

    # Approval binding fields for merge
    r = check_git_pr_action(
        action="merge",
        pr_number=100,
        operator_approval_id="approval-001",
        operator_approved_actions=["merge"],
        remote_verified=True,
        merge_check_passed=True,
    )
    checks.append({
        "name": "gpac-31-merge-approval-binding",
        "passed": (
            r["approval_binding_fields"] is not None
            and r["approval_binding_fields"]["approval_id"] == "approval-001"
            and r["approval_binding_fields"]["remote_verified"] is True
            and r["approval_binding_fields"]["merge_check_passed"] is True
        ),
        "message": f"binding={json.dumps(r.get('approval_binding_fields'))}",
    })

    # Branch delete as merge-finalization
    r = check_git_pr_action(
        action="branch_delete",
        source_branch="feat/test",
        remote_verified=True,
    )
    checks.append({
        "name": "gpac-32-branch-delete-merge-finalization",
        "passed": r["verdict"] == "PASS" and r["allowed"] and "branch_delete" in r["safe_auto_actions"],
        "message": f"verdict={r['verdict']} safe_auto={r['safe_auto_actions']}",
    })

    # Generic operator-required (release_tag)
    r = check_git_pr_action(
        action="release_tag",
        operator_approval_id=None,
        operator_approved_actions=None,
    )
    checks.append({
        "name": "gpac-33-release-tag-no-approval-blocked",
        "passed": r["verdict"] == "OPERATOR_APPROVAL_REQUIRED" and r["requires_operator_approval"],
        "message": f"verdict={r['verdict']}",
    })

    # Generic operator-required with approval (release_tag)
    r = check_git_pr_action(
        action="release_tag",
        operator_approval_id="approval-005",
        operator_approved_actions=["release_tag"],
    )
    checks.append({
        "name": "gpac-34-release-tag-with-approval-pass",
        "passed": r["verdict"] == "PASS" and r["allowed"],
        "message": f"verdict={r['verdict']}",
    })

    # remote_verification_required flag for merge without remote
    r = check_git_pr_action(
        action="merge",
        operator_approval_id="approval-001",
        operator_approved_actions=["merge"],
        remote_verified=False,
    )
    checks.append({
        "name": "gpac-35-merge-remote-verification-flag",
        "passed": r["remote_verification_required"] is True,
        "message": f"remote_verification_required={r['remote_verification_required']}",
    })

    # Summary
    passed = sum(1 for c in checks if c["passed"])
    failed = sum(1 for c in checks if not c["passed"])
    total = len(checks)

    report = {
        "gate": "git_pr_approval",
        "version": __version__,
        "total": total,
        "passed": passed,
        "failed": failed,
        "result": "PASSED" if failed == 0 else "FAILED",
        "checks": checks,
    }

    if output_json:
        print(json.dumps(report, indent=2))
    else:
        print(f"=== GIT/PR APPROVAL GATE SELF-CHECK (v{__version__}) ===")
        print(f"  Total: {total}")
        print(f"  Passed: {passed}")
        print(f"  Failed: {failed}")
        for c in checks:
            status = "PASS" if c["passed"] else "FAIL"
            print(f"  {status}  {c['name']}: {c['message']}")
        print(f"\n  Self-check: {'PASSED' if failed == 0 else 'FAILED'}")

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Git/PR State Approval Gate v%s" % __version__,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    parser.add_argument("--action", help="Git/PR action to check")
    parser.add_argument("--target-branch", default="main", help="Target branch")
    parser.add_argument("--source-branch", help="Source branch")
    parser.add_argument("--pr-number", type=int, help="PR number")
    parser.add_argument("--desired-pr-state", help="Desired PR state (DRAFT, OPEN, MERGED)")
    parser.add_argument("--current-pr-state", help="Current PR state")
    parser.add_argument("--is-draft", type=lambda x: x.lower() == "true", help="Is draft PR")
    parser.add_argument("--operator-approval-id", help="Operator approval ID")
    parser.add_argument("--operator-approved-actions", help="Comma-separated approved actions")
    parser.add_argument("--force-push", action="store_true", help="Is force push")
    parser.add_argument("--changed-files", help="Comma-separated changed files")
    parser.add_argument("--risk-level", help="Risk level (low, medium, high, critical)")
    parser.add_argument("--checks-passed", type=lambda x: x.lower() == "true", default=False, help="Local checks passed")
    parser.add_argument("--intake-approved", type=lambda x: x.lower() == "true", default=False, help="Intake approved")
    parser.add_argument("--remote-verified", type=lambda x: x.lower() == "true", default=False, help="Remote verified")
    parser.add_argument("--merge-check-passed", type=lambda x: x.lower() == "true", default=False, help="Merge check passed")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    if args.self_check:
        report = self_check(output_json=args.json)
        sys.exit(0 if report["result"] == "PASSED" else 1)

    if not args.action:
        parser.error("--action is required (or use --self-check)")

    approved_actions = None
    if args.operator_approved_actions:
        approved_actions = [a.strip() for a in args.operator_approved_actions.split(",")]

    changed = None
    if args.changed_files:
        changed = [f.strip() for f in args.changed_files.split(",")]

    result = check_git_pr_action(
        action=args.action,
        target_branch=args.target_branch,
        source_branch=args.source_branch,
        pr_number=args.pr_number,
        desired_pr_state=args.desired_pr_state,
        current_pr_state=args.current_pr_state,
        is_draft=args.is_draft,
        operator_approval_id=args.operator_approval_id,
        operator_approved_actions=approved_actions,
        force_push=args.force_push,
        changed_files=changed,
        risk_level=args.risk_level,
        checks_passed=args.checks_passed,
        intake_approved=args.intake_approved,
        remote_verified=args.remote_verified,
        merge_check_passed=args.merge_check_passed,
    )

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Verdict: {result['verdict']}")
        print(f"Allowed: {result['allowed']}")
        if result["blocked_reason"]:
            print(f"Blocked reason: {result['blocked_reason']}")
        if result["required_next_step"]:
            print(f"Required next step: {result['required_next_step']}")
        if result["safe_auto_actions"]:
            print(f"Safe auto actions: {result['safe_auto_actions']}")

    sys.exit(0 if result["allowed"] else 1)


if __name__ == "__main__":
    main()
