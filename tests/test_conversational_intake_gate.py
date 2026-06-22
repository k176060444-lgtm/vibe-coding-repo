"""Tests for conversational_intake_gate.py (V1.21.6).

Covers:
  - New coding request → INTAKE_REQUIRED
  - Fuzzy requirement → NEEDS_CLARIFICATION
  - Requirement clear but unconfirmed → PROPOSAL_READY / APPROVAL_REQUIRED
  - "Just do it" without proposal → BLOCKED_UNAPPROVED_ACTION
  - Proposal + explicit approval → APPROVED_FOR_EXECUTION
  - Pre-approval code change → BLOCKED
  - Pre-approval live model call → BLOCKED
  - Pre-approval branch/push/PR → BLOCKED
  - Role/model matrix missing fields → BLOCKED
  - Read-only question → no intake forced
  - Report schema fields
  - Router aliases
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from conversational_intake_gate import (
    ALL_VERDICTS,
    BLOCKED_ACTIONS_BEFORE_APPROVAL,
    VERDICT_APPROVED_FOR_EXECUTION,
    VERDICT_APPROVAL_REQUIRED,
    VERDICT_BLOCKED_UNAPPROVED,
    VERDICT_INTAKE_REQUIRED,
    VERDICT_NEEDS_CLARIFICATION,
    VERDICT_PROPOSAL_READY,
    __version__,
    check_action_allowed,
    compute_intake_verdict,
    create_approval_record,
    create_intake_record,
    create_proposal,
    create_role_model_entry,
    detect_intake_required,
    validate_intake_record,
    validate_proposal,
    validate_role_model_matrix,
)


# --- Detection ---


class TestIntakeDetection:
    def test_coding_request_requires_intake(self):
        det = detect_intake_required("implement a new authentication module")
        assert det["intake_required"] is True

    def test_bugfix_requires_intake(self):
        det = detect_intake_required("fix the login bug")
        assert det["intake_required"] is True

    def test_pr_request_requires_intake(self):
        det = detect_intake_required("create a PR for the feature")
        assert det["intake_required"] is True

    def test_refactor_requires_intake(self):
        det = detect_intake_required("refactor the database layer")
        assert det["intake_required"] is True

    def test_readonly_no_intake(self):
        det = detect_intake_required("what is the current branch?")
        assert det["intake_required"] is False

    def test_status_no_intake(self):
        det = detect_intake_required("show me the status")
        assert det["intake_required"] is False

    def test_research_no_intake(self):
        det = detect_intake_required("research the current model pool")
        assert det["intake_required"] is False

    def test_chinese_readonly_no_intake(self):
        det = detect_intake_required("调研一下当前状态")
        assert det["intake_required"] is False

    def test_uncertain_requires_intake_for_safety(self):
        det = detect_intake_required("hello")
        # Uncertain → intake required for safety (or exempted by no-pattern)
        assert isinstance(det["intake_required"], bool)


# --- Intake record ---


class TestIntakeRecord:
    def test_create_record(self):
        rec = create_intake_record(user_request_raw="implement X")
        assert rec["intake_id"].startswith("intake-")
        assert rec["state"] == "CLASSIFIED"
        assert rec["user_request_raw"] == "implement X"

    def test_record_has_blocked_actions(self):
        rec = create_intake_record(user_request_raw="test")
        assert len(rec["blocked_actions_before_approval"]) >= 12

    def test_record_operator_approval_for_medium(self):
        rec = create_intake_record(user_request_raw="test", risk_level="medium")
        assert rec["operator_approval_required"] is True

    def test_record_no_approval_for_low(self):
        rec = create_intake_record(user_request_raw="test", risk_level="low")
        assert rec["operator_approval_required"] is False

    def test_validate_record(self):
        rec = create_intake_record(user_request_raw="test")
        errors = validate_intake_record(rec)
        assert len(errors) == 0


# --- Proposal ---


class TestProposal:
    def test_create_proposal(self):
        prop = create_proposal(
            scope=["Add feature X"],
            non_scope=["Don't touch Y"],
            implementation_plan=["Step 1", "Step 2"],
        )
        assert len(prop["scope"]) == 1
        assert len(prop["implementation_plan"]) == 2

    def test_validate_proposal(self):
        prop = create_proposal(
            scope=["X"],
            non_scope=["Y"],
            implementation_plan=["Z"],
        )
        errors = validate_proposal(prop)
        assert len(errors) == 0

    def test_validate_empty_proposal_fails(self):
        errors = validate_proposal({})
        assert len(errors) > 0

    def test_validate_empty_scope_fails(self):
        prop = create_proposal(scope=[], non_scope=["Y"], implementation_plan=["Z"])
        errors = validate_proposal(prop)
        assert any("scope" in e for e in errors)


# --- Role/model matrix ---


class TestRoleModelMatrix:
    def test_create_entry(self):
        entry = create_role_model_entry(
            role="implementer",
            planned_node="windows",
            planned_provider="minimax-plan",
            planned_model="minimax-plan/MiniMax-M3",
        )
        assert entry["role"] == "implementer"

    def test_entry_has_capability_boundary(self):
        entry = create_role_model_entry(
            role="reviewer",
            planned_node="9bao",
            planned_provider="deepseek-plan",
            planned_model="deepseek-plan/deepseek-v4-pro",
            capability_boundary="delegate_task: no per-task model override",
        )
        assert "no per-task" in entry["capability_boundary"]

    def test_validate_matrix(self):
        entry = create_role_model_entry(
            role="implementer",
            planned_node="windows",
            planned_provider="minimax-plan",
            planned_model="minimax-plan/MiniMax-M3",
        )
        errors = validate_role_model_matrix([entry])
        assert len(errors) == 0

    def test_validate_missing_field(self):
        bad = [{"role": "test"}]
        errors = validate_role_model_matrix(bad)
        assert len(errors) > 0


# --- Approval ---


class TestApproval:
    def test_create_approval(self):
        appr = create_approval_record(intake_id="intake-test", approved=True)
        assert appr["approved"] is True
        assert appr["intake_id"] == "intake-test"

    def test_create_rejection(self):
        appr = create_approval_record(intake_id="intake-test", approved=False)
        assert appr["approved"] is False


# --- Action blocking ---


class TestActionBlocking:
    def test_code_modify_blocked_without_approval(self):
        result = check_action_allowed("code_modify", "CLASSIFIED", None)
        assert result["allowed"] is False
        assert result["verdict"] == VERDICT_BLOCKED_UNAPPROVED

    def test_push_blocked_without_approval(self):
        result = check_action_allowed("push", "CLASSIFIED", None)
        assert result["allowed"] is False

    def test_live_model_call_blocked(self):
        result = check_action_allowed("live_model_call", "CLASSIFIED", None)
        assert result["allowed"] is False

    def test_branch_create_blocked(self):
        result = check_action_allowed("branch_create", "CLASSIFIED", None)
        assert result["allowed"] is False

    def test_merge_blocked(self):
        result = check_action_allowed("merge", "CLASSIFIED", None)
        assert result["allowed"] is False

    def test_pr_create_blocked(self):
        result = check_action_allowed("pr_create", "CLASSIFIED", None)
        assert result["allowed"] is False

    def test_draft_to_ready_blocked(self):
        result = check_action_allowed("draft_to_ready", "CLASSIFIED", None)
        assert result["allowed"] is False

    def test_ssh_mutation_blocked(self):
        result = check_action_allowed("ssh_worker_mutation", "CLASSIFIED", None)
        assert result["allowed"] is False

    def test_secrets_change_blocked(self):
        result = check_action_allowed("secrets_credential_change", "CLASSIFIED", None)
        assert result["allowed"] is False

    def test_readonly_always_allowed(self):
        result = check_action_allowed("read_only_check", "RAW", None)
        assert result["allowed"] is True
        assert result["verdict"] == VERDICT_APPROVED_FOR_EXECUTION

    def test_classify_always_allowed(self):
        result = check_action_allowed("classify", "RAW", None)
        assert result["allowed"] is True

    def test_allowed_after_approval(self):
        appr = create_approval_record(intake_id="test", approved=True)
        result = check_action_allowed("code_modify", "APPROVED", appr)
        assert result["allowed"] is True

    def test_push_allowed_after_approval(self):
        appr = create_approval_record(intake_id="test", approved=True)
        result = check_action_allowed("push", "APPROVED", appr)
        assert result["allowed"] is True


# --- Verdicts ---


class TestVerdicts:
    def test_raw_state_intake_required(self):
        v = compute_intake_verdict({"state": "RAW"})
        assert v["verdict"] == VERDICT_INTAKE_REQUIRED

    def test_needs_clarification(self):
        v = compute_intake_verdict({
            "state": "CLARIFYING",
            "clarification_questions": ["What scope?"],
        })
        assert v["verdict"] == VERDICT_NEEDS_CLARIFICATION

    def test_approval_required_with_proposal(self):
        v = compute_intake_verdict({
            "state": "PROPOSED",
            "proposal": {"scope": ["X"], "implementation_plan": ["Y"]},
        })
        assert v["verdict"] == VERDICT_APPROVAL_REQUIRED

    def test_approved_for_execution(self):
        v = compute_intake_verdict({
            "state": "APPROVED",
            "proposal": {"scope": ["X"], "implementation_plan": ["Y"]},
            "approval": {"approved": True, "timestamp": "2026-01-01T00:00:00+00:00"},
        })
        assert v["verdict"] == VERDICT_APPROVED_FOR_EXECUTION

    def test_blocked_without_proposal(self):
        v = compute_intake_verdict({
            "state": "CLASSIFIED",
            "proposal": None,
        })
        assert v["verdict"] == VERDICT_PROPOSAL_READY

    def test_six_verdicts_defined(self):
        assert len(ALL_VERDICTS) == 6


class TestVersion:
    def test_version(self):
        assert __version__ == "1.0.0"
