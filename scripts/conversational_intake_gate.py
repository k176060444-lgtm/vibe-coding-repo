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

__version__ = "1.4.0"

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

try:
    from execution_approval_gate import (
        check_execution_approval,
        EXECUTION_ACTIONS as _EAG_EXECUTION_ACTIONS,
        ACTION_SPECIFIC_ACTIONS as _EAG_ACTION_SPECIFIC_ACTIONS,
        BLOCKED_EXECUTION_WITHOUT_APPROVAL as _EAG_BLOCKED_NO_APPROVAL,
        BLOCKED_APPROVAL_NOT_BOUND_TO_PROPOSAL as _EAG_BLOCKED_NO_PROPOSAL,
        BLOCKED_ACTION_NOT_APPROVED as _EAG_BLOCKED_ACTION,
        BLOCKED_CLARIFICATION_NOT_APPROVAL as _EAG_BLOCKED_CLARIFICATION,
        BLOCKED_STALE_APPROVAL as _EAG_BLOCKED_STALE,
        BLOCKED_ACTION_SPECIFIC_FIELDS_MISSING as _EAG_BLOCKED_AS_FIELDS_MISSING,
        BLOCKED_ACTION_SPECIFIC_FIELD_INVALID as _EAG_BLOCKED_AS_FIELD_INVALID,
        BLOCKED_SERVICE_ADMIN_REQUIRES_DEDICATED_APPROVAL as _EAG_BLOCKED_SERVICE_ADMIN,
    )
    _EXECUTION_APPROVAL_GATE_AVAILABLE = True
    # Known EAG block verdicts (not errors — legitimate blocks)
    _EAG_KNOWN_BLOCK_VERDICTS = {
        _EAG_BLOCKED_NO_APPROVAL,
        _EAG_BLOCKED_NO_PROPOSAL,
        _EAG_BLOCKED_ACTION,
        _EAG_BLOCKED_CLARIFICATION,
        _EAG_BLOCKED_STALE,
        _EAG_BLOCKED_AS_FIELDS_MISSING,
        _EAG_BLOCKED_AS_FIELD_INVALID,
        _EAG_BLOCKED_SERVICE_ADMIN,
    }
except ImportError:
    check_execution_approval = None
    _EAG_EXECUTION_ACTIONS = set()
    _EAG_ACTION_SPECIFIC_ACTIONS = set()
    _EXECUTION_APPROVAL_GATE_AVAILABLE = False
    _EAG_KNOWN_BLOCK_VERDICTS = set()

# V1.21.19: Deferred action registry glue
try:
    from vibe_workorder_registry import (
        register_deferred_action as _register_deferred_action,
        DEFERRED_ACTION_TYPES as _DEFERRED_ACTION_TYPES,
    )
    _DEFERRED_ACTION_REGISTRY_AVAILABLE = True
except ImportError:
    _register_deferred_action = None
    _DEFERRED_ACTION_TYPES = set()
    _DEFERRED_ACTION_REGISTRY_AVAILABLE = False

# ── EAG result persistence (V1.21.17) ────────────────────────────────

_EAG_RESULT_DIR = ".vibe"
_EAG_RESULT_FILE = "eag_result.json"


def write_eag_result(eag_result, repo_root=None):
    """Persist EAG result to .vibe/eag_result.json for report auto-discovery.

    Graceful: never raises — write failures are silently ignored.
    """
    try:
        if repo_root is None:
            repo_root = os.getcwd()
        vibe_dir = os.path.join(repo_root, _EAG_RESULT_DIR)
        os.makedirs(vibe_dir, exist_ok=True)
        result_path = os.path.join(vibe_dir, _EAG_RESULT_FILE)
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(eag_result, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # Graceful — never affects gate verdict


# ── Verdicts ──────────────────────────────────────────────────────────

VERDICT_INTAKE_REQUIRED = "INTAKE_REQUIRED"
VERDICT_NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
VERDICT_PROPOSAL_READY = "PROPOSAL_READY"
VERDICT_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
VERDICT_APPROVED_FOR_EXECUTION = "APPROVED_FOR_EXECUTION"
VERDICT_BLOCKED_UNAPPROVED = "BLOCKED_UNAPPROVED_ACTION"
VERDICT_BLOCKED_EAG_ERROR = "BLOCKED_EXECUTION_APPROVAL_GATE_ERROR"
VERDICT_BLOCKED_AS_FIELDS_MISSING = "BLOCKED_ACTION_SPECIFIC_FIELDS_MISSING"
VERDICT_BLOCKED_AS_FIELD_INVALID = "BLOCKED_ACTION_SPECIFIC_FIELD_INVALID"
VERDICT_BLOCKED_SERVICE_ADMIN = "BLOCKED_SERVICE_ADMIN_REQUIRES_DEDICATED_APPROVAL"
VERDICT_BLOCKED_CROSS_REPO_PREAPPROVAL = "BLOCKED_CROSS_REPO_PREAPPROVAL_VIOLATION"

ALL_VERDICTS = {
    VERDICT_INTAKE_REQUIRED,
    VERDICT_NEEDS_CLARIFICATION,
    VERDICT_PROPOSAL_READY,
    VERDICT_APPROVAL_REQUIRED,
    VERDICT_APPROVED_FOR_EXECUTION,
    VERDICT_BLOCKED_UNAPPROVED,
    VERDICT_BLOCKED_EAG_ERROR,
    VERDICT_BLOCKED_AS_FIELDS_MISSING,
    VERDICT_BLOCKED_AS_FIELD_INVALID,
    VERDICT_BLOCKED_SERVICE_ADMIN,
    VERDICT_BLOCKED_CROSS_REPO_PREAPPROVAL,
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
    # V1.21.28A: Test file paths (e.g. tests/test_xxx.py)
    r"(?i)tests?[/\w]*\.(py|js|ts)",
]

# Patterns that do NOT require intake (read-only / informational)
# V1.21.28A correction: removed overly broad ^帮我(看看|查看|检查|看下|查下)
# which incorrectly exempted coding requests like "帮我检查这个 PR".
# Coding signals are now checked BEFORE exemptions (see detect_intake_required).
NO_INTAKE_PATTERNS = [
    r"(?i)^what\s+(is|are|was|were|do|does)",
    r"(?i)^how\s+(does|do|did|is|are)",
    r"(?i)^(show|list|display|print|get|fetch|read|check)\s",
    r"(?i)^status",
    r"(?i)^explain",
    r"(?i)^(help|usage|docs)",
    r"(?i)^research\b",
    r"^调研",
    # Chinese informational / read-only patterns
    r"^什么是",
    r"^告诉我",
    r"^解释(一下|下)?",
    r"^说明(一下|下)?",
    # "是什么意思" = pure informational question ("what does X mean")
    r"(帮我)?(看看|查看|检查|查下|看下)?是什么意思",
    # "帮我看看/查看/看下 + object" = informational (coding signals already filtered)
    r"^帮我(看看|查看|看下)\s*(这个|那个)?\s*\S+",
]

# V1.21.28A: Chinese coding keywords — checked as substring before exemptions.
# Note: \b does NOT work for Chinese characters (they are non-word chars).
CN_CODING_KEYWORDS = ["代码", "测试", "仓库", "分支", "功能"]


# ── Core functions ────────────────────────────────────────────────────


def detect_intake_required(text: str) -> dict:
    """Detect whether user input requires conversational intake.

    V1.21.28A correction: coding signals are checked BEFORE informational
    exemptions. This prevents coding requests like "帮我检查这个 PR" from
    being incorrectly exempted.

    Detection order:
        0. "是什么意思" → always informational (overrides all signals)
        1. English coding signals (regex with \\b)
        2. Chinese coding keywords (substring, since \\b doesn't work for CJK)
        3. Informational exemptions (NO_INTAKE_PATTERNS)
        4. Default: require intake for safety

    Returns:
        {
            "intake_required": bool,
            "reason": str,
            "matched_pattern": str or None,
            "exempt_pattern": str or None,
        }
    """
    import re

    # Step 0: Pure informational patterns — overrides ALL coding signals
    # Chinese: "是什么意思", "告诉我/说明/解释...是什么"
    # English: "what is/are/was/were/do/does", "how does/do/did/is/are",
    #          "show/list/display/print/get/fetch/read/check", "status",
    #          "explain", "help/usage/docs", "research"
    if "是什么意思" in text:
        return {
            "intake_required": False,
            "reason": "Informational question ('是什么意思') — intake not required",
            "matched_pattern": None,
            "exempt_pattern": "是什么意思",
        }
    # V1.21.28B: "告诉我/说明/解释 X 是什么" = informational question
    # e.g. "告诉我 Vibe Coding workflow 是什么" / "说明 intake 是什么"
    # Does NOT match actionable: "告诉我这个 PR 怎么修" / "告诉我这个 bug 怎么修"
    import re as _re2
    if _re2.search(r"(告诉我|说明|解释).{0,30}是什么$", text):
        return {
            "intake_required": False,
            "reason": "Informational question (告诉我/说明/解释...是什么) — intake not required",
            "matched_pattern": None,
            "exempt_pattern": "(告诉我|说明|解释).{0,30}是什么$",
        }
    _info_prefixes = [
        r"(?i)^what\s+(is|are|was|were|do|does)",
        r"(?i)^how\s+(does|do|did|is|are)",
        r"(?i)^(show|list|display|print|get|fetch|read|check)\s",
        r"(?i)^status",
        r"(?i)^explain",
        r"(?i)^(help|usage|docs)",
        r"(?i)^research\b",
        r"^调研",
    ]
    import re as _re
    for _ip in _info_prefixes:
        if _re.search(_ip, text):
            return {
                "intake_required": False,
                "reason": "Informational prefix detected — intake not required",
                "matched_pattern": None,
                "exempt_pattern": _ip,
            }

    # Step 1: Check English coding signals (regex with \b)
    for pat in INTAKE_REQUIRED_PATTERNS:
        if re.search(pat, text):
            return {
                "intake_required": True,
                "reason": "Action/modification request detected — intake required",
                "matched_pattern": pat,
                "exempt_pattern": None,
            }

    # Step 2: Check Chinese coding keywords (substring match)
    for kw in CN_CODING_KEYWORDS:
        if kw in text:
            return {
                "intake_required": True,
                "reason": f"Chinese coding keyword '{kw}' detected — intake required",
                "matched_pattern": kw,
                "exempt_pattern": None,
            }

    # Step 3: Check informational exemptions (read-only / informational)
    for pat in NO_INTAKE_PATTERNS:
        if re.search(pat, text):
            return {
                "intake_required": False,
                "reason": "Read-only or informational request — intake not required",
                "matched_pattern": None,
                "exempt_pattern": pat,
            }

    # Step 4: Default — if uncertain, require intake for safety
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
        # V1.21.14A: Also route action-specific actions through EAG
        if _EXECUTION_APPROVAL_GATE_AVAILABLE and (
            action in _EAG_EXECUTION_ACTIONS or action in _EAG_ACTION_SPECIFIC_ACTIONS
        ):
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
                    "verdict": VERDICT_BLOCKED_EAG_ERROR,
                    "detail": (
                        f"Execution approval gate error for action '{action}': "
                        f"{type(e).__name__}: {e}. Action blocked (fail-closed)."
                    ),
                }
            if eag_result is None:
                return {
                    "allowed": False,
                    "verdict": VERDICT_BLOCKED_EAG_ERROR,
                    "detail": (
                        f"Execution approval gate returned None for action '{action}'. "
                        f"Action blocked (fail-closed)."
                    ),
                }
            # V1.21.17: Persist EAG result for report auto-discovery
            write_eag_result(eag_result)
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
                    # V1.21.19: Registry glue for deferred actions
                    if (_DEFERRED_ACTION_REGISTRY_AVAILABLE
                            and action in _DEFERRED_ACTION_TYPES):
                        _register_deferred_action(
                            action=action,
                            eag_result=eag_result,
                            approval=approval,
                        )
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
            # V1.21.14A: Pass through action-specific verdicts verbatim
            _ACTION_SPECIFIC_VERDICTS = {
                "BLOCKED_ACTION_SPECIFIC_FIELDS_MISSING",
                "BLOCKED_ACTION_SPECIFIC_FIELD_INVALID",
                "BLOCKED_SERVICE_ADMIN_REQUIRES_DEDICATED_APPROVAL",
            }
            if eag_verdict in _ACTION_SPECIFIC_VERDICTS:
                return {
                    "allowed": False,
                    "verdict": eag_verdict,
                    "detail": eag_result["detail"],
                }
            # All other EAG verdicts: known blocks → UNAPPROVED, unknown → EAG_ERROR
            if eag_verdict in _EAG_KNOWN_BLOCK_VERDICTS:
                return {
                    "allowed": False,
                    "verdict": VERDICT_BLOCKED_UNAPPROVED,
                    "detail": eag_result["detail"],
                }
            # Truly unknown verdict → EAG error (fail-closed)
            return {
                "allowed": False,
                "verdict": VERDICT_BLOCKED_EAG_ERROR,
                "detail": (
                    f"Execution approval gate returned unknown verdict "
                    f"'{eag_verdict}' for action '{action}'. "
                    f"Action blocked (fail-closed)."
                ),
            }

        # FAIL-CLOSED: EAG not available → block execution actions (V1.21.12)
        # V1.21.14A: Also block action-specific actions
        if not _EXECUTION_APPROVAL_GATE_AVAILABLE and (
            action in _EAG_EXECUTION_ACTIONS or action in _EAG_ACTION_SPECIFIC_ACTIONS
        ):
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

    # cig-24: 11 verdicts defined (V1.21.30D: added CROSS_REPO_PREAPPROVAL)
    check("cig-24-verdicts-count", len(ALL_VERDICTS) == 11,
          f"count={len(ALL_VERDICTS)}")

    # cig-25: blocked actions count
    check("cig-25-blocked-actions-count",
          len(BLOCKED_ACTIONS_BEFORE_APPROVAL) >= 12,
          f"count={len(BLOCKED_ACTIONS_BEFORE_APPROVAL)}")

    # cig-26: V1.21.30D — verdicts count (now 11 with CROSS_REPO_PREAPPROVAL)
    check("cig-26-verdicts-count-v12130d", len(ALL_VERDICTS) == 11,
          f"count={len(ALL_VERDICTS)}")

    # cig-27: generate_mode_session_id format
    msid = generate_mode_session_id()
    check("cig-27-mode-session-id-format",
          msid.startswith("mode-") and len(msid.split("-")) >= 3,
          f"msid={msid}")

    # cig-28: generate_approval_id format
    aid = generate_approval_id("V1.21.30D")
    check("cig-28-approval-id-format",
          aid.startswith("approval-v1.21.30d-"),
          f"aid={aid}")

    # cig-29: compile_natural_language_approval — "可以执行" → approved
    nl_approval = compile_natural_language_approval("可以执行", "plan_approval", "V1.21.30D")
    check("cig-29-nl-approval-can-exec",
          nl_approval["approved"] is True,
          f"confidence={nl_approval['confidence']}")
    check("cig-29-nl-approval-source",
          nl_approval["approval_source"] == "natural_language",
          f"source={nl_approval['approval_source']}")

    # cig-30: compile_natural_language_approval — "批准" → approved
    nl_approval2 = compile_natural_language_approval("批准", "plan_approval", "V1.21.30D")
    check("cig-30-nl-approval-pi-zhun",
          nl_approval2["approved"] is True)

    # cig-31: compile_natural_language_approval — "merge 吧" → merge approved
    nl_merge = compile_natural_language_approval("merge 吧", "merge_approval", "V1.21.30D")
    check("cig-31-nl-merge-approval",
          nl_merge["approved"] is True,
          f"gate={nl_merge['gate_type']}")

    # cig-32: compile_natural_language_approval — random text → not approved
    nl_random = compile_natural_language_approval("今天天气不错", "plan_approval", "V1.21.30D")
    check("cig-32-nl-random-not-approved",
          nl_random["approved"] is False)

    # cig-33: check_preapproval_read_guard — gh pr list → violation
    guard1 = check_preapproval_read_guard("gh pr list --state open", has_approval=False)
    check("cig-33-preapproval-gh-pr-list",
          guard1["violation_detected"] is True,
          f"type={guard1['violation_type']}")

    # cig-34: check_preapproval_read_guard — with approval → pass
    guard2 = check_preapproval_read_guard("gh pr list --state open", has_approval=True)
    check("cig-34-preapproval-with-approval",
          guard2["guard_passed"] is True)

    # cig-35: check_preapproval_read_guard — git fetch hermes → violation
    guard3 = check_preapproval_read_guard("git fetch origin main", has_approval=False)
    # Note: this should pass because it doesn't mention hermes/opencode
    check("cig-35-preapproval-local-fetch-ok",
          guard3["guard_passed"] is True)

    # cig-36: plan_approval_request has approval_source
    compiled_test = compile_casual_prompt("实现新功能")
    par_test = generate_plan_approval_request(
        phase_id="V1.21.30D",
        approval_id="",
        compiled_prompt=compiled_test,
    )
    check("cig-36-par-has-approval-source",
          par_test.get("approval_source") == "agent_generated",
          f"source={par_test.get('approval_source')}")
    check("cig-36-par-has-mode-session-id",
          "mode_session_id" in par_test,
          f"msid={par_test.get('mode_session_id', 'MISSING')}")

    return {
        "version": __version__,
        "passed": passed == total,
        "total_tests": total,
        "passed_count": passed,
        "failed_count": total - passed,
        "checks": checks,
        "exit_code": 0 if passed == total else 1,
    }


# ── V1.21.30B: Mode Entry Detection ─────────────────────────────────

# Mode entry triggers — when ANY of these match, agent enters MODE_ACTIVE
MODE_ENTRY_TRIGGERS = [
    # Chinese explicit entry
    r"进入.*vibe.?coding",
    r"进入.*vibe\s*coding",
    r"启动.*vibe.?coding",
    r"开始.*vibe.?coding",
    r"vibe.?coding.*模式",
    r"vibe\s*coding\s*模式",
    # English explicit entry
    r"(?i)enter\s+vibe\s*coding\s*mode",
    r"(?i)start\s+vibe\s*coding",
    r"(?i)activate\s+vibe\s*coding",
    r"(?i)vibe\s*coding\s*mode",
    # Version execution triggers
    r"(?i)run\s+V\d+\.\d+",
    r"(?i)execute\s+version",
]

# Cross-repo indicators — when request involves repos other than vibe-coding-repo-clean
CROSS_REPO_INDICATORS = [
    r"(?i)hermes[-_]?agent",
    r"(?i)NousResearch/hermes",
    r"(?i)k176060444-lgtm/hermes",
    r"(?i)\bupstream\b.*\bhermes\b",
    r"(?i)\bhermes\b.*\b(upstream|official|PR|merge)\b",
    r"(?i)\bopencode\b.*\b(config|env|wrapper)\b",
    # Add more cross-repo patterns as needed
]

# Local repos that are always safe (no gate needed)
SAFE_LOCAL_REPOS = [
    "vibe-coding-repo-clean",
    "vibe-coding-repo",
]

# Forbidden actions that must NEVER execute
FORBIDDEN_ACTIONS = {
    "debug_config_raw_output",
    "output_key_value",
    "output_token",
    "clean_malicious_payload_evidence",
    "commit_malicious_payload_evidence",
    "clean_pilot_prompts",
    "commit_pilot_prompts",
}


def detect_mode_entry(text: str) -> dict:
    """Detect whether user input triggers Vibe Coding mode entry.

    V1.21.30B: This function detects explicit mode entry triggers like
    "进入vibe coding模式" and returns mode state + next required action.

    Detection order:
        1. Mode entry triggers (keyword/regex match)
        2. Cross-repo indicators (if mode active)
        3. Default: not a mode entry

    Returns:
        {
            "mode_active": bool,          # True if mode entry detected
            "trigger": str or None,       # Matched trigger pattern
            "cross_repo_detected": bool,  # True if request involves external repo
            "cross_repo_target": str or None,  # Which external repo
            "next_action": str,           # What agent must do next
            "verdict": str,               # MODE_ACTIVE or NOT_MODE_ENTRY
        }
    """
    import re

    # Step 1: Check mode entry triggers
    for trigger in MODE_ENTRY_TRIGGERS:
        if re.search(trigger, text):
            # Step 2: Check if request also involves cross-repo
            cross_repo = _detect_cross_repo(text)
            return {
                "mode_active": True,
                "trigger": trigger,
                "cross_repo_detected": cross_repo["detected"],
                "cross_repo_target": cross_repo.get("target"),
                "next_action": "INTAKE_REQUIRED",
                "verdict": "MODE_ACTIVE",
            }

    return {
        "mode_active": False,
        "trigger": None,
        "cross_repo_detected": False,
        "cross_repo_target": None,
        "next_action": "NONE",
        "verdict": "NOT_MODE_ENTRY",
    }


def _detect_cross_repo(text: str) -> dict:
    """Detect if a request involves non-local repos.

    Returns:
        {
            "detected": bool,
            "target": str or None,  # e.g. "hermes-agent"
        }
    """
    import re
    for pattern in CROSS_REPO_INDICATORS:
        if re.search(pattern, text):
            # Determine target
            if "hermes" in pattern.lower() or "hermes" in text.lower():
                return {"detected": True, "target": "hermes-agent"}
            return {"detected": True, "target": "unknown"}
    return {"detected": False, "target": None}


def check_cross_repo_guard(text: str, current_repo: str = "vibe-coding-repo-clean") -> dict:
    """Cross-Repo Grey-Use Guard.

    When a request involves repos other than the current safe repo,
    the agent must first output PLAN_APPROVAL_REQUEST before doing
    ANY research, clone, install, or modification.

    Returns:
        {
            "guard_passed": bool,      # True if request is within safe scope
            "cross_repo_detected": bool,
            "cross_repo_target": str or None,
            "risk_classification": str,  # "local_safe" | "cross_repo_grey_use" | "cross_repo_real_grey_use"
            "operator_action_needed": str,
            "detail": str,
        }
    """
    cross = _detect_cross_repo(text)
    if cross["detected"]:
        # Determine risk level
        target = cross.get("target", "unknown")
        if target == "hermes-agent":
            risk = "cross_repo_real_grey_use"
            action = "APPROVE_REAL_EXEC / REQUEST_REVISION / BLOCK"
        else:
            risk = "cross_repo_grey_use"
            action = "APPROVE_CROSS_REPO / REQUEST_REVISION / BLOCK"
        return {
            "guard_passed": False,
            "cross_repo_detected": True,
            "cross_repo_target": target,
            "risk_classification": risk,
            "operator_action_needed": action,
            "detail": (
                f"Request involves external repo '{target}'. "
                f"Agent must output PLAN_APPROVAL_REQUEST before any research, "
                f"clone, install, or modification."
            ),
        }
    return {
        "guard_passed": True,
        "cross_repo_detected": False,
        "cross_repo_target": None,
        "risk_classification": "local_safe",
        "operator_action_needed": "NONE",
        "detail": "Request is within safe local repo scope.",
    }


def compile_casual_prompt(text: str) -> dict:
    """Compile a casual/voice user prompt into structured intake fields.

    V1.21.30B: Converts informal Chinese/voice into structured intake.
    The agent MUST use this output as the basis for PLAN_APPROVAL_REQUEST,
    NOT execute the casual prompt directly.

    Returns:
        {
            "original": str,
            "compiled_goal": str,
            "scope_guess": list[str],
            "risk_classification": str,
            "cross_repo_detected": bool,
            "cross_repo_target": str or None,
            "gate_required": bool,
            "forbidden_actions": list[str],
        }
    """
    import re

    # Detect cross-repo
    cross = _detect_cross_repo(text)
    risk = "local_safe"
    if cross["detected"]:
        risk = "cross_repo_real_grey_use" if cross["target"] == "hermes-agent" else "cross_repo_grey_use"

    # Extract goal from casual text
    goal = text.strip()
    # Strip common prefixes
    for prefix in ["帮我", "帮我来", "你来", "我们来", "请", "麻烦", "能不能"]:
        if goal.startswith(prefix):
            goal = goal[len(prefix):].lstrip()
    # Strip mode entry text
    goal = re.sub(r"(?i)(进入|启动|开始)?\s*vibe\s*coding\s*(模式)?\s*[，,]?\s*", "", goal).strip()
    if not goal:
        goal = text[:200]

    return {
        "original": text,
        "compiled_goal": goal,
        "scope_guess": _guess_scope(text),
        "risk_classification": risk,
        "cross_repo_detected": cross["detected"],
        "cross_repo_target": cross.get("target"),
        "gate_required": True,  # Always true in vibe coding mode
        "forbidden_actions": sorted(FORBIDDEN_ACTIONS),
    }


def _guess_scope(text: str) -> list:
    """Guess scope from casual text. Returns list of area hints."""
    import re
    scopes = []
    scope_patterns = [
        (r"(?i)(slash\s*command|斜杠|bot-ping|bot-version|bot-help)", "qqbot-slash-commands"),
        (r"(?i)(PR|pull\s*request|merge|push)", "git-workflow"),
        (r"(?i)(test|测试|verify|验证)", "testing"),
        (r"(?i)(config|配置|setup)", "configuration"),
        (r"(?i)(model|模型|provider)", "model-routing"),
        (r"(?i)(gateway|网关|messaging)", "gateway"),
    ]
    for pat, area in scope_patterns:
        if re.search(pat, text):
            scopes.append(area)
    if not scopes:
        scopes.append("general")
    return scopes


def generate_plan_approval_request(
    phase_id: str,
    approval_id: str,
    compiled_prompt: dict,
    intake_record: dict = None,
) -> dict:
    """Generate a PLAN_APPROVAL_REQUEST structure.

    V1.21.30B: This is the structured output the agent MUST produce
    before any execution in vibe coding mode.

    V1.21.30D: approval_id and mode_session_id are auto-generated.
    Users NEVER need to provide these IDs.

    Returns:
        {
            "phase_id": str,
            "approval_id": str,
            "mode_session_id": str,
            "request_type": "PLAN_APPROVAL_REQUEST",
            "goal": str,
            "risk_classification": str,
            "cross_repo_detected": bool,
            "cross_repo_target": str or None,
            "scope": list[str],
            "forbidden_actions": list[str],
            "role_model_matrix_required": bool,
            "operator_action_needed": str,
            "approval_source": str,
            "next_step": str,
        }
    """
    risk = compiled_prompt.get("risk_classification", "local_safe")
    cross_repo = compiled_prompt.get("cross_repo_detected", False)
    cross_target = compiled_prompt.get("cross_repo_target")

    # Determine operator action based on risk
    if risk == "cross_repo_real_grey_use":
        action = "APPROVE_REAL_EXEC / REQUEST_REVISION / BLOCK"
    elif risk == "cross_repo_grey_use":
        action = "APPROVE_CROSS_REPO / REQUEST_REVISION / BLOCK"
    else:
        action = "APPROVE_PLAN / REQUEST_REVISION / BLOCK"

    # V1.21.30D: Auto-generate IDs if not provided
    if not approval_id:
        approval_id = generate_approval_id(phase_id)
    mode_session_id = generate_mode_session_id()

    return {
        "phase_id": phase_id,
        "approval_id": approval_id,
        "mode_session_id": mode_session_id,
        "request_type": "PLAN_APPROVAL_REQUEST",
        "goal": compiled_prompt.get("compiled_goal", ""),
        "risk_classification": risk,
        "cross_repo_detected": cross_repo,
        "cross_repo_target": cross_target,
        "scope": compiled_prompt.get("scope_guess", []),
        "forbidden_actions": compiled_prompt.get("forbidden_actions", []),
        "role_model_matrix_required": True,
        "operator_action_needed": action,
        "approval_source": "agent_generated",
        "next_step": (
            "Operator must approve plan before execution. "
            "Agent must produce role/model matrix with: "
            "Role, Node, Model, Task Scope, cost_tag, call_budget, fallback_policy."
        ),
    }


# ── V1.21.30D: Auto-generated IDs ────────────────────────────────────


def generate_mode_session_id() -> str:
    """Generate a unique mode_session_id.

    Format: mode-<YYYYMMDDHHMMSS>-<sha256[:8]>
    Example: mode-20260624233657-a1b2c3d4
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    entropy = hashlib.sha256(f"{ts}-{os.getpid()}".encode()).hexdigest()[:8]
    return f"mode-{ts}-{entropy}"


def generate_approval_id(phase_id: str) -> str:
    """Generate a unique approval_id.

    Format: approval-<phase_id_lower>-<3digit_seq>
    Example: approval-v12130d-001

    The sequence is derived from a hash to avoid collisions.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    seq_hash = hashlib.sha256(f"{phase_id}-{ts}".encode()).hexdigest()[:3]
    # Convert to numeric for readability
    seq_num = int(seq_hash, 16) % 1000
    return f"approval-{phase_id.lower()}-{seq_num:03d}"


# ── V1.21.30D: Natural Language Approval Compiler ────────────────────

# Natural language patterns that indicate approval
NL_APPROVAL_PATTERNS = {
    "plan_approval": [
        r"(?i)^(可以执行|批准|按.*plan.*来|继续|可以开始|开始执行|执行吧|go|approved?|yes|可以)$",
        r"(?i)^可以[，,]?\s*(执行|开始|按.*来|按.*执行)",
        r"(?i)^(行|好的?|没问题|ok|okay)[，,]?\s*(执行|开始|继续|按.*来)",
        r"(?i)^可以[，,]?\s*按.*plan.*执行",
    ],
    "merge_approval": [
        r"(?i)^可以\s*merge",
        r"(?i)^merge\s*(吧|了|掉)",
        r"(?i)^合并(吧|了|掉)?",
    ],
    "ready_approval": [
        r"(?i)^可以\s*ready",
        r"(?i)^ready\s*(吧|了)",
        r"(?i)^(转为?|标记为?)\s*ready",
    ],
    "cleanup_approval": [
        r"(?i)^可以(清理|freeze)",
        r"(?i)^(清理|freeze)\s*(吧|了)",
    ],
}


def compile_natural_language_approval(
    text: str,
    gate_type: str = "plan_approval",
    phase_id: str = "",
) -> dict:
    """Compile natural language user approval into structured approval record.

    V1.21.30D: Users NEVER need to provide approval_id. Agent auto-generates.

    Args:
        text: User's natural language message (e.g. "可以执行", "批准", "merge 吧")
        gate_type: Which gate this approval is for (plan_approval, merge_approval, etc.)
        phase_id: Current phase ID for auto-generating approval_id

    Returns:
        {
            "approval_id": str,           # agent-generated
            "gate_type": str,
            "approval_source": "natural_language",
            "operator_message_raw": str,
            "approved": bool,
            "compiled_at": str,           # ISO timestamp
            "mode_session_id": str,       # agent-generated
            "confidence": float,          # 0.0-1.0, how confident the match is
            "matched_pattern": str or None,
        }
    """
    import re

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    approval_id = generate_approval_id(phase_id or "unknown")
    mode_session_id = generate_mode_session_id()

    # Check if text matches approval patterns for the requested gate type
    patterns = NL_APPROVAL_PATTERNS.get(gate_type, [])
    matched = None
    confidence = 0.0

    for pat in patterns:
        if re.search(pat, text.strip()):
            matched = pat
            confidence = 0.9
            break

    # Also check if it's a general approval that could apply to any gate
    if not matched:
        general_patterns = NL_APPROVAL_PATTERNS.get("plan_approval", [])
        for pat in general_patterns:
            if re.search(pat, text.strip()):
                matched = pat
                confidence = 0.7
                break

    return {
        "approval_id": approval_id,
        "gate_type": gate_type,
        "approval_source": "natural_language",
        "operator_message_raw": text,
        "approved": matched is not None,
        "compiled_at": ts,
        "mode_session_id": mode_session_id,
        "confidence": confidence,
        "matched_pattern": matched,
    }


def check_preapproval_read_guard(text: str, has_approval: bool = False) -> dict:
    """Cross-Repo Pre-Approval Read Guard.

    V1.21.30D: Blocks all external repo read/research operations
    before natural language authorization is received.

    Args:
        text: User request text or agent action description
        has_approval: Whether approval has been received

    Returns:
        {
            "guard_passed": bool,
            "violation_detected": bool,
            "violation_type": str or None,
            "detail": str,
        }
    """
    if has_approval:
        return {
            "guard_passed": True,
            "violation_detected": False,
            "violation_type": None,
            "detail": "Approval received — read guard lifted.",
        }

    # Check if the text describes a forbidden pre-approval action
    forbidden_indicators = [
        (r"(?i)gh\s+pr\s+(list|view|checks)", "github_api"),
        (r"(?i)gh\s+api", "github_api"),
        (r"(?i)git\s+(clone|fetch|rebase|merge).*hermes", "git_external"),
        (r"(?i)git\s+(clone|fetch|rebase|merge).*opencode", "git_external"),
        (r"(?i)git\s+merge-tree", "conflict_check"),
        (r"(?i)git\s+diff\s+--check.*hermes", "conflict_check"),
        (r"(?i)delegate_task.*hermes", "background_external"),
        (r"(?i)delegate_task.*检查.*冲突", "background_external"),
    ]

    import re
    for pattern, violation_type in forbidden_indicators:
        if re.search(pattern, text):
            return {
                "guard_passed": False,
                "violation_detected": True,
                "violation_type": violation_type,
                "detail": (
                    f"Cross-repo pre-approval read guard violation: "
                    f"'{violation_type}' detected before approval. "
                    f"Agent must obtain natural language authorization first."
                ),
            }

    return {
        "guard_passed": True,
        "violation_detected": False,
        "violation_type": None,
        "detail": "No forbidden pre-approval actions detected.",
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

    # detect-mode (V1.21.30B)
    dm = sub.add_parser("detect-mode", help="Detect vibe coding mode entry")
    dm.add_argument("--text", required=True, help="User input text")

    # compile-prompt (V1.21.30B)
    cp = sub.add_parser("compile-prompt", help="Compile casual prompt to structured intake")
    cp.add_argument("--text", required=True, help="User input text")

    # plan-approval-request (V1.21.30B)
    par = sub.add_parser("plan-approval-request", help="Generate PLAN_APPROVAL_REQUEST")
    par.add_argument("--text", required=True, help="User input text")
    par.add_argument("--phase-id", default="V1.21.30B", help="Phase ID")
    par.add_argument("--approval-id", default="", help="Approval ID")

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

    if args.command == "detect-mode":
        result = detect_mode_entry(args.text)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Mode Active: {result['mode_active']}")
            print(f"  Trigger: {result['trigger']}")
            print(f"  Next Action: {result['next_action']}")
            print(f"  Verdict: {result['verdict']}")
            if result['cross_repo_detected']:
                print(f"  Cross-Repo: {result['cross_repo_target']}")
        sys.exit(0 if result["mode_active"] else 1)

    if args.command == "compile-prompt":
        result = compile_casual_prompt(args.text)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Goal: {result['compiled_goal']}")
            print(f"  Risk: {result['risk_classification']}")
            print(f"  Scope: {result['scope_guess']}")
            print(f"  Gate Required: {result['gate_required']}")
        sys.exit(0)

    if args.command == "plan-approval-request":
        compiled = compile_casual_prompt(args.text)
        aid = args.approval_id or f"approval-{args.phase_id.lower()}-001"
        result = generate_plan_approval_request(
            phase_id=args.phase_id,
            approval_id=aid,
            compiled_prompt=compiled,
        )
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"PLAN_APPROVAL_REQUEST")
            print(f"  Phase: {result['phase_id']}")
            print(f"  Approval: {result['approval_id']}")
            print(f"  Goal: {result['goal']}")
            print(f"  Risk: {result['risk_classification']}")
            print(f"  Action: {result['operator_action_needed']}")
        sys.exit(0)

    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
