#!/usr/bin/env python3
"""conversational_intake_gate.py — Conversational Intake Gate v1.0.0

Manages the conversational intake workflow: natural language request →
clarification → proposal → role/model matrix → operator approval →
execution authorization.

This gate ensures that:
  1. Users don't need to copy long prompts — natural language triggers intake
  2. System clarifies, restates, and proposes before executing
  3. Role/model matrix is generated with capability boundaries
  4. All write/modify/dispatch actions are BLOCKED until explicit approval
  5. "Just do it" without structured approval is always BLOCKED

Why new module instead of extending vibe_task_intake.py:
  - vibe_task_intake.py is a CLASSIFIER (text → risk/op/type). No state.
  - This module is a WORKFLOW ORCHESTRATOR (state machine + approval + blocking).
  - Different concerns: classification vs lifecycle management.
  - This module CALLS vibe_task_intake.py for classification.

Verdicts:
  INTAKE_REQUIRED           — new request detected, intake not started
  NEEDS_CLARIFICATION       — intake started, questions pending
  PROPOSAL_READY            — proposal generated, awaiting operator review
  APPROVAL_REQUIRED         — proposal reviewed, explicit approval needed
  APPROVED_FOR_EXECUTION    — operator approved, execution authorized
  BLOCKED_UNAPPROVED_ACTION — action requires approval but none given

Usage:
    python scripts/conversational_intake_gate.py classify --text "implement X"
    python scripts/conversational_intake_gate.py intake --text "implement X" --json
    python scripts/conversational_intake_gate.py check-action --action code_modify --state PROPOSAL_READY --json
    python scripts/conversational_intake_gate.py approve --intake-id task-XYZ --json
    python scripts/conversational_intake_gate.py --self-check [--json]

Exit codes:
    0 = gate passed / approved
    1 = gate blocked / needs action
    2 = usage error
"""

__version__ = "1.2.0"

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone

try:
    from execution_approval_gate import (
        check_execution_approval,
        EXECUTION_ACTIONS as _EAG_EXECUTION_ACTIONS,
    )
    _EXECUTION_APPROVAL_GATE_AVAILABLE = True
except ImportError:
    check_execution_approval = None
    _EAG_EXECUTION_ACTIONS = set()
    _EXECUTION_APPROVAL_GATE_AVAILABLE = False

# ── Verdicts ──────────────────────────────────────────────────────────

VERDICT_INTAKE_REQUIRED = "INTAKE_REQUIRED"
VERDICT_NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
VERDICT_PROPOSAL_READY = "PROPOSAL_READY"
VERDICT_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
VERDICT_APPROVED_FOR_EXECUTION = "APPROVED_FOR_EXECUTION"
VERDICT_BLOCKED_UNAPPROVED = "BLOCKED_UNAPPROVED_ACTION"

ALL_VERDICTS = {
    VERDICT_INTAKE_REQUIRED,
    VERDICT_NEEDS_CLARIFICATION,
    VERDICT_PROPOSAL_READY,
    VERDICT_APPROVAL_REQUIRED,
    VERDICT_APPROVED_FOR_EXECUTION,
    VERDICT_BLOCKED_UNAPPROVED,
}

# ── State machine ─────────────────────────────────────────────────────

INTAKE_STATES = [
    "RAW",              # User request received, not yet classified
    "CLASSIFIED",       # Risk/op/type classified
    "CLARIFYING",       # Questions generated, waiting for user answers
    "PROPOSED",         # Proposal generated, waiting for operator review
    "APPROVED",         # Operator explicitly approved
    "EXECUTING",        # Execution in progress
    "COMPLETED",        # Execution finished
    "BLOCKED",          # Blocked at some stage
]

# ── Actions that require approval ─────────────────────────────────────

BLOCKED_ACTIONS_BEFORE_APPROVAL = {
    "live_model_call",
    "delegate_task_dispatch",
    "code_modify",
    "branch_create",
    "commit",
    "push",
    "pr_create",
    "draft_to_ready",
    "merge",
    "ssh_worker_mutation",
    "service_admin_uac",
    "secrets_credential_change",
    "production_gateway_change",
}

# Actions allowed without approval (read-only / planning)
ALLOWED_WITHOUT_APPROVAL = {
    "read_only_check",
    "status_query",
    "classify",
    "propose",
    "clarify",
    "self_check",
}

# ── Required intake fields ────────────────────────────────────────────

REQUIRED_INTAKE_FIELDS = [
    "user_request_raw",
    "interpreted_goal",
    "risk_level",
    "operation_type",
    "affected_area",
    "operator_approval_required",
    "blocked_actions_before_approval",
]

REQUIRED_CLARIFICATION_FIELDS = [
    "clarification_questions",
    "assumptions",
    "non_goals",
]

REQUIRED_PROPOSAL_FIELDS = [
    "scope",
    "non_scope",
    "implementation_plan",
    "files_likely_to_change",
    "tests_checks",
    "rollback_stop_conditions",
    "risk_gates",
    "expected_report_fields",
]

REQUIRED_ROLE_MATRIX_FIELDS = [
    "role",
    "planned_node",
    "planned_provider",
    "planned_model",
    "fallback_policy",
    "cost_tag",
    "call_budget",
    "capability_boundary",
    "operator_approval_required",
]

# ── Intake detection patterns ─────────────────────────────────────────

INTAKE_REQUIRED_PATTERNS = [
    # New feature / implementation
    r"(?i)\b(implement|create|add|build|develop|write|make)\b",
    # Bugfix
    r"(?i)\b(fix|bug|patch|hotfix|repair|resolve)\b",
    # PR / repo modification
    r"(?i)\b(PR|pull\s*request|merge|push|commit|branch)\b",
    # Agent/workflow modification
    r"(?i)\b(agent|workflow|pipeline|gate|orchestrat)\b",
    # Toolchain changes
    r"(?i)\b(tool|script|config|setup|install)\b",
    # Test/verification
    r"(?i)\b(test|verify|validate|check|audit)\b.*\b(code|change|modify|new)\b",
    # Any mention of code changes
    r"(?i)\b(refactor|migrate|upgrade|update|extend|expand)\b",
]

# Patterns that do NOT require intake (read-only / informational)
NO_INTAKE_PATTERNS = [
    r"(?i)^what\s+(is|are|was|were|do|does)",
    r"(?i)^how\s+(does|do|did|is|are)",
    r"(?i)^(show|list|display|print|get|fetch|read|check)\s",
    r"(?i)^status",
    r"(?i)^explain",
    r"(?i)^(help|usage|docs)",
    r"(?i)^research\b",
    r"(?i)^调研",
]


# ── Core functions ────────────────────────────────────────────────────


def detect_intake_required(text: str) -> dict:
    """Detect whether user input requires conversational intake.

    Returns:
        {
            "intake_required": bool,
            "reason": str,
            "matched_pattern": str or None,
            "exempt_pattern": str or None,
        }
    """
    import re

    # Check exemptions first (read-only / informational)
    for pat in NO_INTAKE_PATTERNS:
        if re.search(pat, text):
            return {
                "intake_required": False,
                "reason": "Read-only or informational request — intake not required",
                "matched_pattern": None,
                "exempt_pattern": pat,
            }

    # Check intake-required patterns
    for pat in INTAKE_REQUIRED_PATTERNS:
        if re.search(pat, text):
            return {
                "intake_required": True,
                "reason": "Action/modification request detected — intake required",
                "matched_pattern": pat,
                "exempt_pattern": None,
            }

    # Default: if uncertain, require intake for safety
    return {
        "intake_required": True,
        "reason": "Request type uncertain — intake required for safety",
        "matched_pattern": None,
        "exempt_pattern": None,
    }


def create_intake_record(
    user_request_raw: str,
    interpreted_goal: str = "",
    clarification_questions: list = None,
    assumptions: list = None,
    non_goals: list = None,
    acceptance_criteria: list = None,
    risk_level: str = "medium",
    operation_type: str = "planning",
    affected_area: str = "",
    proposed_plan: list = None,
    role_assignment_required: bool = True,
    model_selection_required: bool = True,
) -> dict:
    """Create a structured intake record.

    This produces the full intake schema that the orchestrator must populate
    before execution is authorized.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    task_hash = hashlib.sha256(user_request_raw.encode()).hexdigest()[:8]
    intake_id = f"intake-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{task_hash}"

    return {
        "version": __version__,
        "intake_id": intake_id,
        "timestamp": ts,
        "state": "CLASSIFIED",
        "user_request_raw": user_request_raw,
        "interpreted_goal": interpreted_goal or user_request_raw[:200],
        "clarification_questions": clarification_questions or [],
        "assumptions": assumptions or [],
        "non_goals": non_goals or [],
        "acceptance_criteria": acceptance_criteria or [],
        "risk_level": risk_level,
        "operation_type": operation_type,
        "affected_area": affected_area,
        "proposed_plan": proposed_plan or [],
        "role_assignment_required": role_assignment_required,
        "model_selection_required": model_selection_required,
        "operator_approval_required": risk_level in ("critical", "high", "medium"),
        "blocked_actions_before_approval": sorted(BLOCKED_ACTIONS_BEFORE_APPROVAL),
        "proposal": None,
        "role_model_matrix": None,
        "approval": None,
    }


def create_proposal(
    scope: list,
    non_scope: list,
    implementation_plan: list,
    files_likely_to_change: list = None,
    tests_checks: list = None,
    rollback_stop_conditions: list = None,
    risk_gates: list = None,
    expected_report_fields: list = None,
) -> dict:
    """Create a structured proposal for operator review."""
    return {
        "scope": scope,
        "non_scope": non_scope,
        "implementation_plan": implementation_plan,
        "files_likely_to_change": files_likely_to_change or [],
        "tests_checks": tests_checks or [],
        "rollback_stop_conditions": rollback_stop_conditions or [],
        "risk_gates": risk_gates or [],
        "expected_report_fields": expected_report_fields or [
            "branch", "base_head", "result_head", "changed_files",
            "tests_passed", "reviewer_verdict", "role_assignment_matrix",
        ],
    }


def create_role_model_entry(
    role: str,
    planned_node: str,
    planned_provider: str,
    planned_model: str,
    fallback_policy: str = "disabled",
    cost_tag: str = "💰",
    call_budget: int = 20,
    capability_boundary: str = "",
    operator_approval_required: bool = False,
) -> dict:
    """Create a role/model matrix entry with capability boundary."""
    return {
        "role": role,
        "planned_node": planned_node,
        "planned_provider": planned_provider,
        "planned_model": planned_model,
        "fallback_policy": fallback_policy,
        "cost_tag": cost_tag,
        "call_budget": call_budget,
        "capability_boundary": capability_boundary,
        "operator_approval_required": operator_approval_required,
    }


def create_approval_record(
    intake_id: str,
    approved: bool,
    operator_notes: str = "",
    approved_actions: list = None,
) -> dict:
    """Create an operator approval record."""
    return {
        "intake_id": intake_id,
        "approved": approved,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "operator_notes": operator_notes,
        "approved_actions": approved_actions or sorted(BLOCKED_ACTIONS_BEFORE_APPROVAL),
    }


# ── Validation ────────────────────────────────────────────────────────


def validate_intake_record(record: dict) -> list:
    """Validate an intake record. Returns list of errors."""
    errors = []

    for field in REQUIRED_INTAKE_FIELDS:
        if field not in record:
            errors.append(f"intake: missing required field '{field}'")

    state = record.get("state", "")
    if state not in INTAKE_STATES:
        errors.append(f"intake: invalid state '{state}' (valid: {INTAKE_STATES})")

    risk = record.get("risk_level", "")
    if risk and risk not in ("critical", "high", "medium", "low"):
        errors.append(f"intake: invalid risk_level '{risk}'")

    return errors


def validate_proposal(proposal: dict) -> list:
    """Validate a proposal. Returns list of errors."""
    errors = []
    for field in REQUIRED_PROPOSAL_FIELDS:
        if field not in proposal:
            errors.append(f"proposal: missing required field '{field}'")

    # scope and implementation_plan must be non-empty lists
    if not proposal.get("scope"):
        errors.append("proposal: scope must be non-empty")
    if not proposal.get("implementation_plan"):
        errors.append("proposal: implementation_plan must be non-empty")

    return errors


def validate_role_model_matrix(matrix: list) -> list:
    """Validate role/model matrix entries. Returns list of errors."""
    errors = []
    for i, entry in enumerate(matrix):
        for field in REQUIRED_ROLE_MATRIX_FIELDS:
            if field not in entry:
                errors.append(f"role_matrix[{i}]: missing required field '{field}'")
    return errors


# ── Action blocking ───────────────────────────────────────────────────


def check_action_allowed(action: str, state: str, approval: dict = None,
                         proposal_hash: str = None,
                         changed_files: list = None,
                         operator_message: str = None) -> dict:
    """Check whether an action is allowed in the current intake state.

    V1.21.12: For execution actions, additionally validates approval binding
    via execution_approval_gate (proposal_hash, approved_actions, file scope,
    role_model_matrix_hash risk-aware check, clarification detection).

    Args:
        action: Action name (e.g. "code_modify", "push")
        state: Current intake state (e.g. "CLASSIFIED", "APPROVED")
        approval: Approval record dict (if exists)
        proposal_hash: Current proposal hash (for binding validation)
        changed_files: Files being changed (for scope check)
        operator_message: Raw operator message (for clarification detection)

    Returns:
        {
            "allowed": bool,
            "verdict": str,
            "detail": str,
        }
    """
    # Always-allowed actions
    if action in ALLOWED_WITHOUT_APPROVAL:
        return {
            "allowed": True,
            "verdict": VERDICT_APPROVED_FOR_EXECUTION,
            "detail": f"Action '{action}' is always allowed (read-only/planning).",
        }

    # Blocked actions require approval
    if action in BLOCKED_ACTIONS_BEFORE_APPROVAL:
        # V1.21.12: Run execution_approval_gate for execution actions
        # V1.21.13A: Exception clean block — catch EAG errors, return clean verdict
        if _EXECUTION_APPROVAL_GATE_AVAILABLE and action in _EAG_EXECUTION_ACTIONS:
            try:
                eag_result = check_execution_approval(
                    action=action,
                    approval=approval,
                    proposal_hash=proposal_hash,
                    operator_message=operator_message,
                    changed_files=changed_files,
                )
            except Exception as e:
                return {
                    "allowed": False,
                    "verdict": VERDICT_BLOCKED_UNAPPROVED,
                    "detail": (
                        f"Execution approval gate error for action '{action}': "
                        f"{type(e).__name__}: {e}. Action blocked (fail-closed)."
                    ),
                }
            if eag_result is None:
                return {
                    "allowed": False,
                    "verdict": VERDICT_BLOCKED_UNAPPROVED,
                    "detail": (
                        f"Execution approval gate returned None for action '{action}'. "
                        f"Action blocked (fail-closed)."
                    ),
                }
            eag_verdict = eag_result.get("verdict", "")
            # Map EAG verdicts to intake gate verdicts
            if eag_verdict == "PASS_READ_ONLY":
                return {
                    "allowed": True,
                    "verdict": VERDICT_APPROVED_FOR_EXECUTION,
                    "detail": eag_result["detail"],
                }
            if eag_verdict == "APPROVAL_BOUND":
                # EAG approved — also check intake state
                if state == "APPROVED" and approval and approval.get("approved"):
                    return {
                        "allowed": True,
                        "verdict": VERDICT_APPROVED_FOR_EXECUTION,
                        "detail": (
                            f"Action '{action}' approved by operator "
                            f"and bound to approval '{eag_result.get('approval_id', '?')}'."
                        ),
                    }
                # EAG passed but intake state not APPROVED
                return {
                    "allowed": False,
                    "verdict": VERDICT_APPROVAL_REQUIRED,
                    "detail": (
                        f"Approval binding valid but intake state is '{state}', "
                        f"not 'APPROVED'."
                    ),
                }
            # All other EAG verdicts are blocks
            return {
                "allowed": False,
                "verdict": VERDICT_BLOCKED_UNAPPROVED,
                "detail": eag_result["detail"],
            }

        # FAIL-CLOSED: EAG not available → block execution actions (V1.21.12)
        if not _EXECUTION_APPROVAL_GATE_AVAILABLE and action in _EAG_EXECUTION_ACTIONS:
            return {
                "allowed": False,
                "verdict": VERDICT_BLOCKED_UNAPPROVED,
                "detail": (
                    f"Execution approval gate unavailable — cannot verify "
                    f"approval binding for execution action '{action}'. "
                    f"FAIL-CLOSED: action blocked."
                ),
            }

        # Fallback: original logic if EAG not available (read-only actions only)
        if state == "APPROVED" and approval and approval.get("approved"):
            approved_actions = approval.get("approved_actions", [])
            if action in approved_actions or not approved_actions:
                return {
                    "allowed": True,
                    "verdict": VERDICT_APPROVED_FOR_EXECUTION,
                    "detail": (
                        f"Action '{action}' approved by operator "
                        f"at {approval.get('timestamp', '?')}."
                    ),
                }

        # Not approved → blocked
        return {
            "allowed": False,
            "verdict": VERDICT_BLOCKED_UNAPPROVED,
            "detail": (
                f"Action '{action}' requires operator approval. "
                f"Current state: '{state}'. "
                f"Complete intake → proposal → approval before executing."
            ),
        }

    # Unknown action — block for safety
    return {
        "allowed": False,
        "verdict": VERDICT_BLOCKED_UNAPPROVED,
        "detail": (
            f"Unknown action '{action}' — blocked for safety. "
            f"Add to ALLOWED_WITHOUT_APPROVAL or BLOCKED_ACTIONS_BEFORE_APPROVAL."
        ),
    }


# ── Verdict computation ───────────────────────────────────────────────


def compute_intake_verdict(record: dict) -> dict:
    """Compute the current verdict for an intake record.

    Returns:
        {
            "verdict": str,
            "state": str,
            "detail": str,
            "next_action": str,
        }
    """
    state = record.get("state", "RAW")
    approval = record.get("approval")
    proposal = record.get("proposal")
    questions = record.get("clarification_questions", [])
    answers = record.get("clarification_answers")

    if state == "APPROVED" and approval and approval.get("approved"):
        return {
            "verdict": VERDICT_APPROVED_FOR_EXECUTION,
            "state": state,
            "detail": "Operator approved. Execution authorized.",
            "next_action": "proceed_to_execution_gate",
        }

    if state == "BLOCKED":
        return {
            "verdict": VERDICT_BLOCKED_UNAPPROVED,
            "state": state,
            "detail": "Intake is blocked. Check blocked_reason for details.",
            "next_action": "resolve_blocker",
        }

    if proposal and not approval:
        return {
            "verdict": VERDICT_APPROVAL_REQUIRED,
            "state": state,
            "detail": "Proposal ready. Waiting for explicit operator approval.",
            "next_action": "request_operator_approval",
        }

    if proposal and approval and not approval.get("approved"):
        return {
            "verdict": VERDICT_BLOCKED_UNAPPROVED,
            "state": state,
            "detail": "Operator rejected proposal. Revise and resubmit.",
            "next_action": "revise_proposal",
        }

    if questions and not answers:
        return {
            "verdict": VERDICT_NEEDS_CLARIFICATION,
            "state": state,
            "detail": f"{len(questions)} clarification questions pending.",
            "next_action": "answer_clarification_questions",
        }

    if state == "CLASSIFIED" and not proposal:
        return {
            "verdict": VERDICT_PROPOSAL_READY,
            "state": state,
            "detail": "Request classified. Generate proposal for operator review.",
            "next_action": "generate_proposal",
        }

    return {
        "verdict": VERDICT_INTAKE_REQUIRED,
        "state": state,
        "detail": "Intake not yet started or incomplete.",
        "next_action": "start_intake",
    }


# ── Self-check ────────────────────────────────────────────────────────


def self_check() -> dict:
    """Run self-check with synthetic scenarios. No network calls."""
    checks = []
    passed = 0
    total = 0

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal passed, total
        total += 1
        if ok:
            passed += 1
        checks.append({"name": name, "passed": ok, "detail": detail})

    # cig-01: version
    check("cig-01-version", bool(__version__), __version__)

    # cig-02: coding request → intake required
    det = detect_intake_required("implement a new feature for user auth")
    check("cig-02-coding-intake-required", det["intake_required"] is True,
          f"reason={det['reason'][:50]}")

    # cig-03: bugfix → intake required
    det2 = detect_intake_required("fix the login bug on mobile")
    check("cig-03-bugfix-intake-required", det2["intake_required"] is True)

    # cig-04: read-only question → no intake
    det3 = detect_intake_required("what is the current branch?")
    check("cig-04-readonly-no-intake", det3["intake_required"] is False,
          f"exempt={det3['exempt_pattern']}")

    # cig-05: research → no intake
    det4 = detect_intake_required("调研一下当前模型池状态")
    check("cig-05-research-no-intake", det4["intake_required"] is False)

    # cig-06: status query → no intake
    det5 = detect_intake_required("show me the current status")
    check("cig-06-status-no-intake", det5["intake_required"] is False)

    # cig-07: intake record creation
    rec = create_intake_record(
        user_request_raw="implement V1.21.6 intake gate",
        interpreted_goal="Add conversational intake gate to VibeDev",
        risk_level="medium",
        operation_type="coding",
        affected_area="scripts/",
    )
    check("cig-07-intake-record-created", rec["intake_id"].startswith("intake-"))
    check("cig-07-intake-has-blocked-actions",
          len(rec["blocked_actions_before_approval"]) > 0,
          f"count={len(rec['blocked_actions_before_approval'])}")

    # cig-08: proposal creation
    prop = create_proposal(
        scope=["Add intake gate module", "Router integration"],
        non_scope=["delegate_task core", "worker SSH"],
        implementation_plan=["Create module", "Add tests", "Commit"],
    )
    check("cig-08-proposal-created", len(prop["scope"]) == 2)

    # cig-09: role/model entry
    rme = create_role_model_entry(
        role="implementer",
        planned_node="windows",
        planned_provider="minimax-plan",
        planned_model="minimax-plan/MiniMax-M3",
        capability_boundary="delegate_task: no per-task model override",
    )
    check("cig-09-role-model-entry", rme["role"] == "implementer")
    check("cig-09-has-capability-boundary",
          "no per-task" in rme["capability_boundary"])

    # cig-10: approval record
    appr = create_approval_record(intake_id="intake-test", approved=True)
    # V1.21.12: Add fields required by execution_approval_gate
    appr["approval_id"] = "approval-intake-test"
    appr["proposal_id"] = "proposal-test"
    appr["proposal_hash"] = "testhash123"
    appr["risk_level"] = "medium"
    appr["operator_message_raw"] = "approved for self-check"
    appr["operator_confirmation_phrase"] = "approved"
    appr["approval_scope"] = "scripts/"
    appr["role_model_matrix_hash"] = "testrmatrix"
    check("cig-10-approval-record", appr["approved"] is True)

    # cig-11: validate intake record
    errors = validate_intake_record(rec)
    check("cig-11-validate-intake", len(errors) == 0, str(errors))

    # cig-12: validate proposal
    prop_errors = validate_proposal(prop)
    check("cig-12-validate-proposal", len(prop_errors) == 0, str(prop_errors))

    # cig-13: validate role/model matrix
    rm_errors = validate_role_model_matrix([rme])
    check("cig-13-validate-role-matrix", len(rm_errors) == 0, str(rm_errors))

    # cig-14: action blocking — code_modify blocked without approval
    rec_no_approval = {**rec, "state": "CLASSIFIED", "approval": None}
    block = check_action_allowed("code_modify", "CLASSIFIED", None)
    check("cig-14-code-modify-blocked", block["allowed"] is False,
          f"verdict={block['verdict']}")

    # cig-15: action blocking — push blocked without approval
    block2 = check_action_allowed("push", "CLASSIFIED", None)
    check("cig-15-push-blocked", block2["allowed"] is False)

    # cig-16: action blocking — live_model_call blocked
    block3 = check_action_allowed("live_model_call", "CLASSIFIED", None)
    check("cig-16-live-model-blocked", block3["allowed"] is False)

    # cig-17: action allowed after approval (V1.21.12: needs proposal_hash for binding)
    allow = check_action_allowed("code_modify", "APPROVED", appr,
                                  proposal_hash="testhash123")
    check("cig-17-code-modify-allowed-after-approval", allow["allowed"] is True)

    # cig-18: read-only always allowed
    allow2 = check_action_allowed("read_only_check", "RAW", None)
    check("cig-18-readonly-always-allowed", allow2["allowed"] is True)

    # cig-19: verdict — intake required
    v1 = compute_intake_verdict({"state": "RAW"})
    check("cig-19-verdict-intake-required",
          v1["verdict"] == VERDICT_INTAKE_REQUIRED,
          f"verdict={v1['verdict']}")

    # cig-20: verdict — needs clarification
    v2 = compute_intake_verdict({
        "state": "CLARIFYING",
        "clarification_questions": ["What scope?"],
    })
    check("cig-20-verdict-needs-clarification",
          v2["verdict"] == VERDICT_NEEDS_CLARIFICATION,
          f"verdict={v2['verdict']}")

    # cig-21: verdict — proposal ready / approval required
    v3 = compute_intake_verdict({
        "state": "PROPOSED",
        "proposal": {"scope": ["X"], "implementation_plan": ["Y"]},
    })
    check("cig-21-verdict-approval-required",
          v3["verdict"] == VERDICT_APPROVAL_REQUIRED,
          f"verdict={v3['verdict']}")

    # cig-22: verdict — approved
    v4 = compute_intake_verdict({
        "state": "APPROVED",
        "proposal": {"scope": ["X"], "implementation_plan": ["Y"]},
        "approval": {"approved": True, "timestamp": "2026-01-01T00:00:00+00:00"},
    })
    check("cig-22-verdict-approved",
          v4["verdict"] == VERDICT_APPROVED_FOR_EXECUTION,
          f"verdict={v4['verdict']}")

    # cig-23: "just do it" without proposal → BLOCKED
    block4 = check_action_allowed("code_modify", "CLASSIFIED", None)
    check("cig-23-just-do-it-blocked",
          block4["verdict"] == VERDICT_BLOCKED_UNAPPROVED)

    # cig-24: 6 verdicts defined
    check("cig-24-verdicts-count", len(ALL_VERDICTS) == 6,
          f"count={len(ALL_VERDICTS)}")

    # cig-25: blocked actions count
    check("cig-25-blocked-actions-count",
          len(BLOCKED_ACTIONS_BEFORE_APPROVAL) >= 12,
          f"count={len(BLOCKED_ACTIONS_BEFORE_APPROVAL)}")

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


def main():
    parser = argparse.ArgumentParser(
        description="Conversational Intake Gate — structured intake before execution")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    sub = parser.add_subparsers(dest="command")

    # classify
    cl = sub.add_parser("classify", help="Detect if intake is required")
    cl.add_argument("--text", required=True, help="User request text")

    # intake
    it = sub.add_parser("intake", help="Create intake record")
    it.add_argument("--text", required=True, help="User request text")
    it.add_argument("--goal", default="", help="Interpreted goal")
    it.add_argument("--risk", default="medium", help="Risk level")
    it.add_argument("--op", default="planning", help="Operation type")
    it.add_argument("--area", default="", help="Affected area")

    # check-action
    ca = sub.add_parser("check-action", help="Check if action is allowed")
    ca.add_argument("--action", required=True, help="Action name")
    ca.add_argument("--state", required=True, help="Intake state")
    ca.add_argument("--approval-json", default=None, help="Approval record JSON")

    # approve
    ap = sub.add_parser("approve", help="Create approval record")
    ap.add_argument("--intake-id", required=True, help="Intake ID")
    ap.add_argument("--approved", action="store_true", help="Approved")
    ap.add_argument("--notes", default="", help="Operator notes")

    # validate
    va = sub.add_parser("validate", help="Validate intake/proposal/matrix")
    va.add_argument("--intake-json", default=None, help="Intake record JSON")
    va.add_argument("--proposal-json", default=None, help="Proposal JSON")
    va.add_argument("--matrix-json", default=None, help="Role/model matrix JSON")

    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"=== CONVERSATIONAL INTAKE GATE SELF-CHECK (v{__version__}) ===")
            print(f"  Total: {result['total_tests']}")
            print(f"  Passed: {result['passed_count']}")
            print(f"  Failed: {result['failed_count']}")
            for c in result["checks"]:
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  {icon}  {c['name']}: {c['detail']}")
            print(f"\n  Self-check: {'PASSED' if result['passed'] else 'FAILED'}")
        sys.exit(result["exit_code"])

    if args.command == "classify":
        result = detect_intake_required(args.text)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Intake required: {result['intake_required']}")
            print(f"  Reason: {result['reason']}")
        sys.exit(0 if not result["intake_required"] else 1)

    if args.command == "intake":
        det = detect_intake_required(args.text)
        rec = create_intake_record(
            user_request_raw=args.text,
            interpreted_goal=args.goal or args.text[:200],
            risk_level=args.risk,
            operation_type=args.op,
            affected_area=args.area,
        )
        verdict = compute_intake_verdict(rec)
        result = {
            "intake": rec,
            "detection": det,
            "verdict": verdict,
        }
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Intake: {rec['intake_id']}")
            print(f"  Verdict: {verdict['verdict']}")
            print(f"  Next: {verdict['next_action']}")
        sys.exit(0 if verdict["verdict"] in (
            VERDICT_APPROVED_FOR_EXECUTION, VERDICT_PROPOSAL_READY
        ) else 1)

    if args.command == "check-action":
        approval = None
        if args.approval_json:
            approval = json.loads(args.approval_json)
        result = check_action_allowed(args.action, args.state, approval)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Action '{args.action}': {'ALLOWED' if result['allowed'] else 'BLOCKED'}")
            print(f"  Verdict: {result['verdict']}")
            print(f"  Detail: {result['detail']}")
        sys.exit(0 if result["allowed"] else 1)

    if args.command == "approve":
        result = create_approval_record(
            intake_id=args.intake_id,
            approved=args.approved,
            operator_notes=args.notes,
        )
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Approval: {'APPROVED' if result['approved'] else 'REJECTED'}")
            print(f"  Intake: {result['intake_id']}")
            print(f"  Time: {result['timestamp']}")
        sys.exit(0 if result["approved"] else 1)

    if args.command == "validate":
        errors = []
        if args.intake_json:
            errors.extend(validate_intake_record(json.loads(args.intake_json)))
        if args.proposal_json:
            errors.extend(validate_proposal(json.loads(args.proposal_json)))
        if args.matrix_json:
            errors.extend(validate_role_model_matrix(json.loads(args.matrix_json)))
        result = {"valid": len(errors) == 0, "errors": errors}
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            if result["valid"]:
                print("Validation: PASS")
            else:
                print(f"Validation: FAIL ({len(errors)} errors)")
                for e in errors:
                    print(f"  - {e}")
        sys.exit(0 if result["valid"] else 1)

    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
