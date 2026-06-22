#!/usr/bin/env python3
"""Execution Approval Binding Gate v1.0.0

Enforces the critical distinction between:
  - Clarification answer ≠ execution approval
  - Option selection ≠ execution approval
  - Proposal ready ≠ approved
  - Draft PR auto-allowed ≠ implementation auto-approved

Every execution-class action MUST be bound to an explicit approval record.
Without binding, the action is BLOCKED.

Verdicts:
  PASS_READ_ONLY                          — read-only research, no approval needed
  APPROVAL_REQUIRED                       — proposal exists, approval not yet given
  APPROVAL_BOUND                          — proper approval bound to proposal, action allowed
  BLOCKED_EXECUTION_WITHOUT_APPROVAL      — execution action attempted with no approval at all
  BLOCKED_APPROVAL_NOT_BOUND_TO_PROPOSAL  — approval exists but not bound to any proposal
  BLOCKED_ACTION_NOT_APPROVED             — approval exists but action not in approved_actions
  BLOCKED_CLARIFICATION_NOT_APPROVAL      — user answer to clarification misinterpreted as approval
  BLOCKED_STALE_APPROVAL                  — approval exists but is stale (proposal changed after approval)

Usage:
    python scripts/execution_approval_gate.py --self-check [--json]
    python scripts/execution_approval_gate.py check --action code_modify [--json]
    python scripts/execution_approval_gate.py check --action code_modify \
        --approval-json '{"approval_id":"...","proposal_hash":"...","approved_actions":["code_modify"],...}' \
        --proposal-hash abc123 [--json]

Exit codes:
    0 = PASS_READ_ONLY or APPROVAL_BOUND
    1 = any BLOCKED verdict or APPROVAL_REQUIRED
    2 = usage error
"""

__version__ = "1.1.0"

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone

# ── Verdicts ──────────────────────────────────────────────────────────

PASS_READ_ONLY = "PASS_READ_ONLY"
APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
APPROVAL_BOUND = "APPROVAL_BOUND"
BLOCKED_EXECUTION_WITHOUT_APPROVAL = "BLOCKED_EXECUTION_WITHOUT_APPROVAL"
BLOCKED_APPROVAL_NOT_BOUND_TO_PROPOSAL = "BLOCKED_APPROVAL_NOT_BOUND_TO_PROPOSAL"
BLOCKED_ACTION_NOT_APPROVED = "BLOCKED_ACTION_NOT_APPROVED"
BLOCKED_CLARIFICATION_NOT_APPROVAL = "BLOCKED_CLARIFICATION_NOT_APPROVAL"
BLOCKED_STALE_APPROVAL = "BLOCKED_STALE_APPROVAL"

ALL_VERDICTS = {
    PASS_READ_ONLY,
    APPROVAL_REQUIRED,
    APPROVAL_BOUND,
    BLOCKED_EXECUTION_WITHOUT_APPROVAL,
    BLOCKED_APPROVAL_NOT_BOUND_TO_PROPOSAL,
    BLOCKED_ACTION_NOT_APPROVED,
    BLOCKED_CLARIFICATION_NOT_APPROVAL,
    BLOCKED_STALE_APPROVAL,
}

# ── Action classification ─────────────────────────────────────────────

# Execution actions — require explicit approval binding
EXECUTION_ACTIONS = {
    "code_modify",
    "branch_create",
    "commit",
    "push_feature_branch",
    "create_draft_pr",
    "update_draft_pr",
    "pr_create",
    "test_write_artifact",
    "push",
    "merge",
    "force_push",
    "draft_to_ready",
    "deploy",
    "release",
    "ssh_worker_mutation",
    "secrets_credential_change",
    "production_gateway_change",
}

# Read-only actions — never need approval
READ_ONLY_ACTIONS = {
    "read_only_check",
    "status_query",
    "classify",
    "research",
    "explore",
    "list",
    "show",
    "diff",
    "log",
    "blame",
    "grep",
    "search",
    "self_check",
    "help",
    "version",
    "snapshot",
    "health",
}

# ── Clarification detection patterns ──────────────────────────────────
# Patterns in operator messages that indicate clarification answers,
# NOT execution approval.

CLARIFICATION_PATTERNS = [
    # Option selection patterns: "1.A 2.B 3.C", "A B C", "选A", "选择第一个"
    (r"^[\d\.\s]*[A-Da-d][\s,]+[\d\.\s]*[A-Da-d]", "option_selection"),
    (r"^(选|选择|我选|我选择)\s*[A-Da-d\d]", "option_selection_cn"),
    # Vague agreement without binding
    (r"^(可以继续|继续|按你说的做|你来吧|你看着办|go ahead|proceed|continue|do it)$",
     "vague_agreement"),
    # Question disguised as statement
    (r"(你应该|你应该是|你知道|你应该知道|you should know|you know how)",
     "rhetorical_question"),
    # Delegation question
    (r"(你应该是知道的[吧吗呢？?]?$|you should know how to|right\??$)",
     "delegation_question"),
]

# ── Required approval record fields ───────────────────────────────────

REQUIRED_APPROVAL_FIELDS = [
    "approval_id",
    "proposal_id",
    "approved_actions",
    "risk_level",
    "operator_message_raw",
    "operator_confirmation_phrase",
    "timestamp",
    "approval_scope",
]

# Optional but recommended
RECOMMENDED_APPROVAL_FIELDS = [
    "changed_files",
    "allowed_file_patterns",
    "role_model_matrix_hash",
    "proposal_hash",
]


# ── Core functions ────────────────────────────────────────────────────


def classify_action(action: str) -> str:
    """Classify an action as 'execution', 'read_only', or 'unknown'."""
    if action in EXECUTION_ACTIONS:
        return "execution"
    if action in READ_ONLY_ACTIONS:
        return "read_only"
    return "unknown"


def detect_clarification_not_approval(operator_message: str) -> dict:
    """Detect whether an operator message is a clarification answer
    rather than an execution approval.

    Returns:
        {
            "is_clarification": bool,
            "pattern_type": str or None,
            "detail": str,
        }
    """
    import re

    if not operator_message:
        return {
            "is_clarification": False,
            "pattern_type": None,
            "detail": "Empty message",
        }

    stripped = operator_message.strip()

    # Check for pure option selection: "1.A 2.A 3.A 4.A 5.A 6.A"
    if re.match(r"^[\d\.\s]*[A-Da-d]", stripped):
        tokens = stripped.split()
        if len(tokens) >= 2 and all(
            re.match(r"^[\d\.\s]*[A-Da-d]$", t) for t in tokens
        ):
            return {
                "is_clarification": True,
                "pattern_type": "option_selection",
                "detail": (
                    f"Message '{stripped[:60]}' is option selection, not approval"
                ),
            }

    # Check known patterns
    for pattern, pattern_type in CLARIFICATION_PATTERNS:
        if re.search(pattern, stripped, re.IGNORECASE):
            return {
                "is_clarification": True,
                "pattern_type": pattern_type,
                "detail": (
                    f"Message matches clarification pattern '{pattern_type}': "
                    f"'{stripped[:60]}'"
                ),
            }

    return {
        "is_clarification": False,
        "pattern_type": None,
        "detail": "No clarification pattern matched",
    }


def validate_approval_record(approval: dict) -> dict:
    """Validate an approval record has all required fields.

    Returns:
        {
            "valid": bool,
            "errors": list[str],
            "warnings": list[str],
        }
    """
    errors = []
    warnings = []

    if not approval or not isinstance(approval, dict):
        return {
            "valid": False,
            "errors": ["approval record is None or not a dict"],
            "warnings": [],
        }

    for field in REQUIRED_APPROVAL_FIELDS:
        if field not in approval:
            errors.append(f"approval: missing required field '{field}'")

    # proposal_id or proposal_hash must be present and non-empty
    pid = approval.get("proposal_id", "")
    phash = approval.get("proposal_hash", "")
    if not pid and not phash:
        errors.append(
            "approval: neither proposal_id nor proposal_hash is set — "
            "approval is not bound to any proposal"
        )

    # approved_actions must be non-empty list
    actions = approval.get("approved_actions")
    if not isinstance(actions, list) or len(actions) == 0:
        errors.append(
            "approval: approved_actions must be a non-empty list"
        )

    for field in RECOMMENDED_APPROVAL_FIELDS:
        if field not in approval:
            warnings.append(f"approval: recommended field '{field}' missing")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }


def compute_proposal_hash(proposal: dict) -> str:
    """Compute SHA256 hash of a proposal dict."""
    data = json.dumps(proposal, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def check_execution_approval(
    action: str,
    approval: dict = None,
    proposal_hash: str = None,
    proposal_exists: bool = False,
    operator_message: str = None,
    changed_files: list = None,
    max_approval_age_seconds: int = 86400,
) -> dict:
    """Check whether an execution action has proper approval binding.

    Args:
        action: The action being attempted (e.g. "code_modify")
        approval: The approval record dict (if any)
        proposal_hash: The hash of the current proposal
        proposal_exists: Whether a proposal has been generated
        operator_message: Raw operator message (to detect clarification vs approval)
        changed_files: Files being changed (to check scope)
        max_approval_age_seconds: Max age before approval is stale (default 24h)

    Returns:
        {
            "verdict": str,
            "action": str,
            "action_class": str,
            "detail": str,
            "approval_id": str or None,
            "checks": list[dict],
        }
    """
    action_class = classify_action(action)
    checks = []

    # ── Rule 1: Read-only actions always pass ──
    if action_class == "read_only":
        checks.append({
            "name": "action_classification",
            "result": "PASS",
            "detail": f"Action '{action}' is read-only",
        })
        return {
            "verdict": PASS_READ_ONLY,
            "action": action,
            "action_class": action_class,
            "detail": f"Read-only action '{action}' — no approval needed",
            "approval_id": None,
            "checks": checks,
        }

    # ── Rule 7: Detect clarification misinterpretation ──
    if operator_message:
        cl_result = detect_clarification_not_approval(operator_message)
        if cl_result["is_clarification"]:
            checks.append({
                "name": "clarification_detection",
                "result": "BLOCK",
                "detail": cl_result["detail"],
            })
            return {
                "verdict": BLOCKED_CLARIFICATION_NOT_APPROVAL,
                "action": action,
                "action_class": action_class,
                "detail": (
                    f"Operator message is a clarification answer, not execution "
                    f"approval. Pattern: {cl_result['pattern_type']}. "
                    f"{cl_result['detail']}"
                ),
                "approval_id": None,
                "checks": checks,
            }

    # ── Rule 2: Execution action with no approval at all ──
    if action_class == "execution" and (not approval or not isinstance(approval, dict)):
        checks.append({
            "name": "approval_exists",
            "result": "BLOCK",
            "detail": f"No approval record for execution action '{action}'",
        })
        return {
            "verdict": BLOCKED_EXECUTION_WITHOUT_APPROVAL,
            "action": action,
            "action_class": action_class,
            "detail": (
                f"Execution action '{action}' requires explicit approval. "
                f"No approval record provided."
            ),
            "approval_id": None,
            "checks": checks,
        }

    # ── From here, approval exists ──
    approval_id = approval.get("approval_id", "unknown")

    # ── Validate approval record structure ──
    val_result = validate_approval_record(approval)
    if not val_result["valid"]:
        checks.append({
            "name": "approval_validation",
            "result": "BLOCK",
            "detail": f"Invalid approval: {val_result['errors']}",
        })
        # Rule 3: Check if specifically missing proposal binding
        has_proposal_binding = bool(
            approval.get("proposal_id") or approval.get("proposal_hash")
        )
        if not has_proposal_binding:
            return {
                "verdict": BLOCKED_APPROVAL_NOT_BOUND_TO_PROPOSAL,
                "action": action,
                "action_class": action_class,
                "detail": (
                    f"Approval '{approval_id}' is not bound to any proposal. "
                    f"Missing both proposal_id and proposal_hash."
                ),
                "approval_id": approval_id,
                "checks": checks,
            }
        return {
            "verdict": BLOCKED_EXECUTION_WITHOUT_APPROVAL,
            "action": action,
            "action_class": action_class,
            "detail": (
                f"Approval record '{approval_id}' is invalid: "
                f"{'; '.join(val_result['errors'])}"
            ),
            "approval_id": approval_id,
            "checks": checks,
        }

    checks.append({
        "name": "approval_validation",
        "result": "PASS",
        "detail": f"Approval '{approval_id}' has all required fields",
    })

    # ── Rule 3: Approval must be bound to proposal ──
    approval_proposal_hash = approval.get("proposal_hash", "")
    if proposal_hash and approval_proposal_hash:
        if approval_proposal_hash != proposal_hash:
            checks.append({
                "name": "proposal_binding",
                "result": "BLOCK",
                "detail": (
                    f"Approval proposal_hash '{approval_proposal_hash[:16]}...' "
                    f"!= current proposal_hash '{proposal_hash[:16]}...'"
                ),
            })
            return {
                "verdict": BLOCKED_STALE_APPROVAL,
                "action": action,
                "action_class": action_class,
                "detail": (
                    f"Approval '{approval_id}' is bound to a different proposal "
                    f"(hash mismatch). Proposal may have changed after approval."
                ),
                "approval_id": approval_id,
                "checks": checks,
            }

    if not approval.get("proposal_id") and not approval.get("proposal_hash"):
        checks.append({
            "name": "proposal_binding",
            "result": "BLOCK",
            "detail": "Approval not bound to any proposal",
        })
        return {
            "verdict": BLOCKED_APPROVAL_NOT_BOUND_TO_PROPOSAL,
            "action": action,
            "action_class": action_class,
            "detail": (
                f"Approval '{approval_id}' has no proposal_id or proposal_hash. "
                f"Cannot verify it is bound to the current proposal."
            ),
            "approval_id": approval_id,
            "checks": checks,
        }

    checks.append({
        "name": "proposal_binding",
        "result": "PASS",
        "detail": (
            f"Approval bound to proposal "
            f"(id={approval.get('proposal_id', 'N/A')}, "
            f"hash={approval_proposal_hash[:16] if approval_proposal_hash else 'N/A'}...)"
        ),
    })

    # ── Rule 4: Action must be in approved_actions ──
    approved_actions = approval.get("approved_actions", [])
    if action not in approved_actions:
        checks.append({
            "name": "action_approved",
            "result": "BLOCK",
            "detail": (
                f"Action '{action}' not in approved_actions {approved_actions}"
            ),
        })
        return {
            "verdict": BLOCKED_ACTION_NOT_APPROVED,
            "action": action,
            "action_class": action_class,
            "detail": (
                f"Action '{action}' is not in the approved actions list. "
                f"Approved: {approved_actions}"
            ),
            "approval_id": approval_id,
            "checks": checks,
        }

    checks.append({
        "name": "action_approved",
        "result": "PASS",
        "detail": f"Action '{action}' is in approved_actions",
    })

    # ── Rule 5: Changed files must be within approval scope ──
    if changed_files:
        approved_files = approval.get("changed_files", [])
        allowed_patterns = approval.get("allowed_file_patterns", [])
        approval_scope = approval.get("approval_scope", "")

        if approved_files:
            # Explicit file list — check each changed file is in approved list
            outside_scope = [
                f for f in changed_files if f not in approved_files
            ]
            if outside_scope:
                checks.append({
                    "name": "file_scope",
                    "result": "BLOCK",
                    "detail": (
                        f"Files outside approved scope: {outside_scope}"
                    ),
                })
                return {
                    "verdict": BLOCKED_ACTION_NOT_APPROVED,
                    "action": action,
                    "action_class": action_class,
                    "detail": (
                        f"Changed files {outside_scope} are not in the "
                        f"approved file list."
                    ),
                    "approval_id": approval_id,
                    "checks": checks,
                }
        elif allowed_patterns:
            import fnmatch
            outside = []
            for f in changed_files:
                if not any(
                    fnmatch.fnmatch(f, p) for p in allowed_patterns
                ):
                    outside.append(f)
            if outside:
                checks.append({
                    "name": "file_scope",
                    "result": "BLOCK",
                    "detail": (
                        f"Files outside allowed patterns: {outside}"
                    ),
                })
                return {
                    "verdict": BLOCKED_ACTION_NOT_APPROVED,
                    "action": action,
                    "action_class": action_class,
                    "detail": (
                        f"Changed files {outside} do not match allowed "
                        f"file patterns."
                    ),
                    "approval_id": approval_id,
                    "checks": checks,
                }

        checks.append({
            "name": "file_scope",
            "result": "PASS",
            "detail": "Changed files within approval scope",
        })

    # ── Rule 6: Role/model matrix hash check ──
    rm_hash = approval.get("role_model_matrix_hash")
    risk_level = approval.get("risk_level", "medium")
    if rm_hash:
        checks.append({
            "name": "role_model_matrix",
            "result": "PASS",
            "detail": f"role_model_matrix_hash present: {rm_hash[:16]}...",
        })
    elif risk_level in ("high", "critical"):
        # F-01: high/critical without role_model_matrix_hash → BLOCK
        checks.append({
            "name": "role_model_matrix",
            "result": "BLOCK",
            "detail": (
                f"role_model_matrix_hash missing for risk_level={risk_level}. "
                f"High/critical tasks require role_model_matrix_hash."
            ),
        })
        return {
            "verdict": BLOCKED_ACTION_NOT_APPROVED,
            "action": action,
            "action_class": action_class,
            "detail": (
                f"Approval '{approval_id}' missing role_model_matrix_hash "
                f"for risk_level={risk_level}. "
                f"High/critical tasks must declare role/model matrix."
            ),
            "approval_id": approval_id,
            "checks": checks,
        }
    else:
        # low/medium: WARN, not block (same-model downgrade acceptable)
        checks.append({
            "name": "role_model_matrix",
            "result": "WARN",
            "detail": (
                f"role_model_matrix_hash not set (risk_level={risk_level}) — "
                "assuming same-model downgrade approval"
            ),
        })

    # ── Rule 8: Approval age check ──
    approval_ts = approval.get("timestamp", "")
    if approval_ts:
        try:
            approval_time = datetime.fromisoformat(
                approval_ts.replace("Z", "+00:00")
            )
            now = datetime.now(timezone.utc)
            age = (now - approval_time).total_seconds()
            if age > max_approval_age_seconds:
                checks.append({
                    "name": "approval_staleness",
                    "result": "BLOCK",
                    "detail": (
                        f"Approval is {age:.0f}s old "
                        f"(max {max_approval_age_seconds}s)"
                    ),
                })
                return {
                    "verdict": BLOCKED_STALE_APPROVAL,
                    "action": action,
                    "action_class": action_class,
                    "detail": (
                        f"Approval '{approval_id}' is stale: "
                        f"{age:.0f}s old (max {max_approval_age_seconds}s)"
                    ),
                    "approval_id": approval_id,
                    "checks": checks,
                }
            checks.append({
                "name": "approval_staleness",
                "result": "PASS",
                "detail": f"Approval age: {age:.0f}s (max {max_approval_age_seconds}s)",
            })
        except (ValueError, TypeError):
            checks.append({
                "name": "approval_staleness",
                "result": "WARN",
                "detail": f"Cannot parse approval timestamp: {approval_ts}",
            })

    # ── All checks passed ──
    return {
        "verdict": APPROVAL_BOUND,
        "action": action,
        "action_class": action_class,
        "detail": (
            f"Action '{action}' is bound to approval '{approval_id}'. "
            f"All checks passed."
        ),
        "approval_id": approval_id,
        "checks": checks,
    }


# ── Self-check ────────────────────────────────────────────────────────


def _make_valid_approval(
    approved_actions=None,
    proposal_id="proposal-001",
    proposal_hash=None,
):
    """Create a valid approval record for testing."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    return {
        "approval_id": "approval-test-001",
        "proposal_id": proposal_id,
        "proposal_hash": proposal_hash or "abc123def456",
        "approved_actions": approved_actions or ["code_modify", "branch_create", "commit"],
        "risk_level": "medium",
        "changed_files": ["scripts/foo.py", "tests/test_foo.py"],
        "allowed_file_patterns": ["scripts/*.py", "tests/*.py"],
        "role_model_matrix_hash": "rmatrix_abc123",
        "operator_message_raw": "批准执行：实现 foo 功能",
        "operator_confirmation_phrase": "批准执行",
        "timestamp": ts,
        "approval_scope": "scripts/ and tests/ only",
    }


def self_check(output_json=False):
    """Run self-check tests for the execution approval gate."""
    checks = []
    checks.append({"name": "version", "passed": True, "message": __version__})

    # Test 1: read_only -> PASS_READ_ONLY
    r = check_execution_approval(action="research")
    checks.append({
        "name": "read_only_passes",
        "passed": r["verdict"] == PASS_READ_ONLY,
        "message": f"verdict={r['verdict']}",
    })

    # Test 2: code_modify without approval -> BLOCKED_EXECUTION_WITHOUT_APPROVAL
    r = check_execution_approval(action="code_modify")
    checks.append({
        "name": "code_modify_no_approval_blocked",
        "passed": r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL,
        "message": f"verdict={r['verdict']}",
    })

    # Test 3: branch_create without approval -> BLOCKED_EXECUTION_WITHOUT_APPROVAL
    r = check_execution_approval(action="branch_create")
    checks.append({
        "name": "branch_create_no_approval_blocked",
        "passed": r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL,
        "message": f"verdict={r['verdict']}",
    })

    # Test 4: commit without approval -> BLOCKED_EXECUTION_WITHOUT_APPROVAL
    r = check_execution_approval(action="commit")
    checks.append({
        "name": "commit_no_approval_blocked",
        "passed": r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL,
        "message": f"verdict={r['verdict']}",
    })

    # Test 5: push_feature_branch without approval -> BLOCKED_EXECUTION_WITHOUT_APPROVAL
    r = check_execution_approval(action="push_feature_branch")
    checks.append({
        "name": "push_no_approval_blocked",
        "passed": r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL,
        "message": f"verdict={r['verdict']}",
    })

    # Test 6: create_draft_pr without approval -> BLOCKED_EXECUTION_WITHOUT_APPROVAL
    r = check_execution_approval(action="create_draft_pr")
    checks.append({
        "name": "draft_pr_no_approval_blocked",
        "passed": r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL,
        "message": f"verdict={r['verdict']}",
    })

    # Test 7: clarification answer -> BLOCKED_CLARIFICATION_NOT_APPROVAL
    r = check_execution_approval(
        action="code_modify",
        operator_message="1.A 2.A 3.A 4.A 5.A 6.A",
    )
    checks.append({
        "name": "clarification_option_selection_blocked",
        "passed": r["verdict"] == BLOCKED_CLARIFICATION_NOT_APPROVAL,
        "message": f"verdict={r['verdict']}",
    })

    # Test 8: rhetorical question -> BLOCKED_CLARIFICATION_NOT_APPROVAL
    r = check_execution_approval(
        action="pr_create",
        operator_message="你应该知道怎么提PR吧？",
    )
    checks.append({
        "name": "rhetorical_question_blocked",
        "passed": r["verdict"] == BLOCKED_CLARIFICATION_NOT_APPROVAL,
        "message": f"verdict={r['verdict']}",
    })

    # Test 9: proposal exists but no approval -> APPROVAL_REQUIRED
    r = check_execution_approval(
        action="code_modify",
        proposal_exists=True,
    )
    checks.append({
        "name": "proposal_no_approval_requires",
        "passed": r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL,
        "message": f"verdict={r['verdict']}",
    })

    # Test 10: approval exists but no proposal hash -> BLOCKED_APPROVAL_NOT_BOUND_TO_PROPOSAL
    bad_approval = {
        "approval_id": "approval-bad-001",
        "approved_actions": ["code_modify"],
        "risk_level": "medium",
        "operator_message_raw": "approved",
        "operator_confirmation_phrase": "approved",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "approval_scope": "all",
    }
    r = check_execution_approval(
        action="code_modify",
        approval=bad_approval,
    )
    checks.append({
        "name": "approval_no_proposal_blocked",
        "passed": r["verdict"] == BLOCKED_APPROVAL_NOT_BOUND_TO_PROPOSAL,
        "message": f"verdict={r['verdict']}",
    })

    # Test 11: approval exists but action not in approved_actions
    approval_limited = _make_valid_approval(approved_actions=["commit"])
    r = check_execution_approval(
        action="code_modify",
        approval=approval_limited,
        proposal_hash="abc123def456",
    )
    checks.append({
        "name": "action_not_approved_blocked",
        "passed": r["verdict"] == BLOCKED_ACTION_NOT_APPROVED,
        "message": f"verdict={r['verdict']}",
    })

    # Test 12: changed file outside approved scope
    approval_files = _make_valid_approval()
    r = check_execution_approval(
        action="code_modify",
        approval=approval_files,
        proposal_hash="abc123def456",
        changed_files=["scripts/foo.py", "secrets/credentials.json"],
    )
    checks.append({
        "name": "file_outside_scope_blocked",
        "passed": r["verdict"] == BLOCKED_ACTION_NOT_APPROVED,
        "message": f"verdict={r['verdict']}",
    })

    # Test 13: proper approval + allowed action -> APPROVAL_BOUND
    approval_ok = _make_valid_approval()
    r = check_execution_approval(
        action="code_modify",
        approval=approval_ok,
        proposal_hash="abc123def456",
    )
    checks.append({
        "name": "proper_approval_bound",
        "passed": r["verdict"] == APPROVAL_BOUND,
        "message": f"verdict={r['verdict']}",
    })

    # Test 14: Draft PR still requires execution approval
    r = check_execution_approval(action="create_draft_pr")
    checks.append({
        "name": "draft_pr_requires_execution_approval",
        "passed": r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL,
        "message": f"verdict={r['verdict']}",
    })

    # Test 15: stale approval (proposal hash mismatch)
    approval_stale = _make_valid_approval(proposal_hash="old_hash_123")
    r = check_execution_approval(
        action="code_modify",
        approval=approval_stale,
        proposal_hash="new_hash_456",
    )
    checks.append({
        "name": "stale_approval_blocked",
        "passed": r["verdict"] == BLOCKED_STALE_APPROVAL,
        "message": f"verdict={r['verdict']}",
    })

    # Test 16: vague agreement -> BLOCKED_CLARIFICATION_NOT_APPROVAL
    r = check_execution_approval(
        action="code_modify",
        operator_message="可以继续",
    )
    checks.append({
        "name": "vague_agreement_blocked",
        "passed": r["verdict"] == BLOCKED_CLARIFICATION_NOT_APPROVAL,
        "message": f"verdict={r['verdict']}",
    })

    # Test 17: proper approval with files in scope
    approval_full = _make_valid_approval(
        approved_actions=["code_modify", "branch_create", "commit", "push_feature_branch"]
    )
    r = check_execution_approval(
        action="push_feature_branch",
        approval=approval_full,
        proposal_hash="abc123def456",
        changed_files=["scripts/foo.py", "tests/test_foo.py"],
    )
    checks.append({
        "name": "push_with_approval_and_scope",
        "passed": r["verdict"] == APPROVAL_BOUND,
        "message": f"verdict={r['verdict']}",
    })

    # Test 18: #50719 regression — option selection not approval
    r = check_execution_approval(
        action="pr_create",
        operator_message="1.A 2.A 3.A 4.A 5.A 6.A。另外，这个功能的实现是需要给 Hermes 官方提 PR 的。关于如何提出 PR，你应该是知道的吧？",
    )
    checks.append({
        "name": "incident_50719_regression",
        "passed": r["verdict"] == BLOCKED_CLARIFICATION_NOT_APPROVAL,
        "message": f"verdict={r['verdict']}",
    })

    # Test 19: F-01 — high risk + missing role_model_matrix_hash -> BLOCKED
    approval_high_no_hash = _make_valid_approval()
    del approval_high_no_hash["role_model_matrix_hash"]
    approval_high_no_hash["risk_level"] = "high"
    r = check_execution_approval(
        action="code_modify",
        approval=approval_high_no_hash,
        proposal_hash="abc123def456",
    )
    checks.append({
        "name": "f01_high_no_hash_blocked",
        "passed": r["verdict"] == BLOCKED_ACTION_NOT_APPROVED,
        "message": f"verdict={r['verdict']}",
    })

    # Test 20: F-01 — critical risk + missing role_model_matrix_hash -> BLOCKED
    approval_crit_no_hash = _make_valid_approval()
    del approval_crit_no_hash["role_model_matrix_hash"]
    approval_crit_no_hash["risk_level"] = "critical"
    r = check_execution_approval(
        action="code_modify",
        approval=approval_crit_no_hash,
        proposal_hash="abc123def456",
    )
    checks.append({
        "name": "f01_critical_no_hash_blocked",
        "passed": r["verdict"] == BLOCKED_ACTION_NOT_APPROVED,
        "message": f"verdict={r['verdict']}",
    })

    # Test 21: F-01 — medium risk + missing role_model_matrix_hash -> WARN (not blocked)
    approval_med_no_hash = _make_valid_approval()
    del approval_med_no_hash["role_model_matrix_hash"]
    approval_med_no_hash["risk_level"] = "medium"
    r = check_execution_approval(
        action="code_modify",
        approval=approval_med_no_hash,
        proposal_hash="abc123def456",
    )
    checks.append({
        "name": "f01_medium_no_hash_warn",
        "passed": r["verdict"] == APPROVAL_BOUND,
        "message": f"verdict={r['verdict']}",
    })

    # Test 22: F-01 — low risk + missing role_model_matrix_hash -> WARN (not blocked)
    approval_low_no_hash = _make_valid_approval()
    del approval_low_no_hash["role_model_matrix_hash"]
    approval_low_no_hash["risk_level"] = "low"
    r = check_execution_approval(
        action="code_modify",
        approval=approval_low_no_hash,
        proposal_hash="abc123def456",
    )
    checks.append({
        "name": "f01_low_no_hash_warn",
        "passed": r["verdict"] == APPROVAL_BOUND,
        "message": f"verdict={r['verdict']}",
    })

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    return {
        "overall": "PASS" if passed == total else "FAIL",
        "passed": passed,
        "total": total,
        "checks": checks,
    }


# ── CLI ───────────────────────────────────────────────────────────────


def build_parser():
    """Build argument parser."""
    p = argparse.ArgumentParser(
        prog="execution_approval_gate",
        description="Execution Approval Binding Gate — enforce approval binding for execution actions",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--json", dest="output_json", action="store_true")
    p.add_argument("--self-check", dest="self_check_flag", action="store_true")

    sub = p.add_subparsers(dest="command")

    ck = sub.add_parser("check", help="Check execution approval for an action")
    ck.add_argument("--action", required=True, help="Action to check")
    ck.add_argument("--approval-json", help="JSON string of approval record")
    ck.add_argument("--proposal-hash", help="Current proposal hash")
    ck.add_argument("--proposal-exists", action="store_true",
                     help="Whether a proposal has been generated")
    ck.add_argument("--operator-message", help="Raw operator message text")
    ck.add_argument("--changed-files", nargs="*", help="Files being changed")
    ck.add_argument("--max-age", type=int, default=86400,
                     help="Max approval age in seconds (default 86400)")

    return p


def main(argv=None):
    """Main entry point."""
    p = build_parser()
    args = p.parse_args(argv)

    if args.self_check_flag:
        result = self_check(args.output_json)
        if args.output_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Overall: {result['overall']} ({result['passed']}/{result['total']})")
            for c in result.get("checks", []):
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  [{icon}] {c['name']}: {c['message']}")
        return 0 if result["overall"] == "PASS" else 1

    if args.command == "check":
        approval = None
        if args.approval_json:
            try:
                approval = json.loads(args.approval_json)
            except json.JSONDecodeError as e:
                print(f"ERROR: Invalid --approval-json: {e}", file=sys.stderr)
                return 2

        result = check_execution_approval(
            action=args.action,
            approval=approval,
            proposal_hash=args.proposal_hash,
            proposal_exists=args.proposal_exists,
            operator_message=args.operator_message,
            changed_files=args.changed_files,
            max_approval_age_seconds=args.max_age,
        )

        if args.output_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Verdict: {result['verdict']}")
            print(f"  Action: {result['action']} ({result['action_class']})")
            print(f"  Detail: {result['detail']}")
            if result.get("approval_id"):
                print(f"  Approval: {result['approval_id']}")
            for c in result.get("checks", []):
                print(f"  [{c['result']}] {c['name']}: {c['detail']}")

        if result["verdict"] in (APPROVAL_BOUND, PASS_READ_ONLY):
            return 0
        return 1

    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
