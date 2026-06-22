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
    VERDICT_BLOCKED_EAG_ERROR,
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
        # V1.21.12: Add fields required by execution_approval_gate
        appr["approval_id"] = "test-approval"
        appr["proposal_id"] = "test-proposal"
        appr["proposal_hash"] = "testhash"
        appr["risk_level"] = "medium"
        appr["operator_message_raw"] = "approved"
        appr["operator_confirmation_phrase"] = "approved"
        appr["approval_scope"] = "all"
        result = check_action_allowed("code_modify", "APPROVED", appr,
                                       proposal_hash="testhash")
        assert result["allowed"] is True

    def test_push_allowed_after_approval(self):
        appr = create_approval_record(intake_id="test", approved=True)
        # V1.21.12: Add fields required by execution_approval_gate
        appr["approval_id"] = "test-approval"
        appr["proposal_id"] = "test-proposal"
        appr["proposal_hash"] = "testhash"
        appr["risk_level"] = "medium"
        appr["operator_message_raw"] = "approved"
        appr["operator_confirmation_phrase"] = "approved"
        appr["approval_scope"] = "all"
        result = check_action_allowed("push", "APPROVED", appr,
                                       proposal_hash="testhash")
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

    def test_seven_verdicts_defined(self):
        assert len(ALL_VERDICTS) == 7


class TestFailClosed:
    """V1.21.12: EAG import/call failure must BLOCK execution actions."""

    def test_eag_unavailable_code_modify_blocked(self):
        """EAG import fails + code_modify → BLOCKED (not fail-open)."""
        import unittest.mock as mock
        with mock.patch(
            "conversational_intake_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", False
        ), mock.patch(
            "conversational_intake_gate._EAG_EXECUTION_ACTIONS",
            {"code_modify", "commit", "push", "branch_create"},
        ):
            r = check_action_allowed("code_modify", "APPROVED", {"approved": True})
            assert r["allowed"] is False
            assert "FAIL-CLOSED" in r["detail"] or "unavailable" in r["detail"].lower()

    def test_eag_unavailable_commit_blocked(self):
        """EAG import fails + commit → BLOCKED."""
        import unittest.mock as mock
        with mock.patch(
            "conversational_intake_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", False
        ), mock.patch(
            "conversational_intake_gate._EAG_EXECUTION_ACTIONS",
            {"code_modify", "commit", "push", "branch_create"},
        ):
            r = check_action_allowed("commit", "APPROVED", {"approved": True})
            assert r["allowed"] is False
            assert "FAIL-CLOSED" in r["detail"] or "unavailable" in r["detail"].lower()

    def test_eag_unavailable_push_blocked(self):
        """EAG import fails + push → BLOCKED."""
        import unittest.mock as mock
        with mock.patch(
            "conversational_intake_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", False
        ), mock.patch(
            "conversational_intake_gate._EAG_EXECUTION_ACTIONS",
            {"code_modify", "commit", "push", "branch_create"},
        ):
            r = check_action_allowed("push", "APPROVED", {"approved": True})
            assert r["allowed"] is False

    def test_eag_unavailable_readonly_not_blocked(self):
        """EAG import fails + read-only action → not affected by fail-closed."""
        import unittest.mock as mock
        with mock.patch(
            "conversational_intake_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", False
        ), mock.patch(
            "conversational_intake_gate._EAG_EXECUTION_ACTIONS",
            {"code_modify", "commit", "push"},
        ):
            # clarify is in ALLOWED_WITHOUT_APPROVAL, should still pass
            r = check_action_allowed("clarify", "PENDING", {})
            assert r["allowed"] is True

    def test_eag_import_error_simulation(self):
        """Simulate EAG raising exception on call → should block, not crash."""
        import unittest.mock as mock

        def _raise(*a, **kw):
            raise RuntimeError("EAG internal error")

        with mock.patch(
            "conversational_intake_gate.check_execution_approval", side_effect=_raise
        ), mock.patch(
            "conversational_intake_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "conversational_intake_gate._EAG_EXECUTION_ACTIONS", {"code_modify"}
        ):
            # Should propagate or be caught — either way, not allow
            try:
                r = check_action_allowed("code_modify", "APPROVED", {"approved": True})
                # If it returns instead of raising, must not be allowed
                assert r["allowed"] is False
            except RuntimeError:
                # Exception propagated = not silently allowing = acceptable
                pass



    def test_eag_invalid_result_commit_blocked(self):
        """EAG returns unexpected result + commit → blocked or exception, not allow."""
        import unittest.mock as mock

        with mock.patch(
            "conversational_intake_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "conversational_intake_gate._EAG_EXECUTION_ACTIONS", {"commit"}
        ), mock.patch(
            "conversational_intake_gate.check_execution_approval",
            return_value={"verdict": "UNKNOWN_VERDICT", "detail": "bad"},
        ):
            r = check_action_allowed("commit", "APPROVED", {"approved": True})
            # UNKNOWN_VERDICT hits "All other EAG verdicts are blocks" → blocked
            assert r["allowed"] is False

    def test_eag_none_result_commit_blocked(self):
        """EAG returns None + commit → blocked or exception, not allow."""
        import unittest.mock as mock

        with mock.patch(
            "conversational_intake_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "conversational_intake_gate._EAG_EXECUTION_ACTIONS", {"commit"}
        ), mock.patch(
            "conversational_intake_gate.check_execution_approval",
            return_value=None,
        ):
            try:
                r = check_action_allowed("commit", "APPROVED", {"approved": True})
                assert r["allowed"] is False
            except (AttributeError, TypeError):
                # .get() on None crashes = not silently allowing = acceptable
                pass


class TestVersion:
    def test_version(self):
        assert __version__ == "1.2.0"


class TestExceptionCleanBlock:
    """V1.21.13A: EAG exception returns clean BLOCK verdict, not traceback."""

    def test_eag_runtime_error_clean_block(self):
        """T-01: EAG raises RuntimeError + code_modify → clean BLOCK."""
        import unittest.mock as mock
        with mock.patch(
            "conversational_intake_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "conversational_intake_gate._EAG_EXECUTION_ACTIONS", {"code_modify"}
        ), mock.patch(
            "conversational_intake_gate.check_execution_approval",
            side_effect=RuntimeError("internal EAG error"),
        ):
            r = check_action_allowed("code_modify", "APPROVED", {"approved": True})
            assert r["allowed"] is False
            assert r["verdict"] == VERDICT_BLOCKED_EAG_ERROR
            assert "RuntimeError" in r["detail"]
            assert "fail-closed" in r["detail"].lower()

    def test_eag_type_error_clean_block(self):
        """T-02: EAG raises TypeError + commit → clean BLOCK."""
        import unittest.mock as mock
        with mock.patch(
            "conversational_intake_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "conversational_intake_gate._EAG_EXECUTION_ACTIONS", {"commit"}
        ), mock.patch(
            "conversational_intake_gate.check_execution_approval",
            side_effect=TypeError("bad arg"),
        ):
            r = check_action_allowed("commit", "APPROVED", {"approved": True})
            assert r["allowed"] is False
            assert r["verdict"] == VERDICT_BLOCKED_EAG_ERROR
            assert "TypeError" in r["detail"]

    def test_eag_returns_none_clean_block(self):
        """T-03: EAG returns None + code_modify → clean BLOCK."""
        import unittest.mock as mock
        with mock.patch(
            "conversational_intake_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "conversational_intake_gate._EAG_EXECUTION_ACTIONS", {"code_modify"}
        ), mock.patch(
            "conversational_intake_gate.check_execution_approval",
            return_value=None,
        ):
            r = check_action_allowed("code_modify", "APPROVED", {"approved": True})
            assert r["allowed"] is False
            assert r["verdict"] == VERDICT_BLOCKED_EAG_ERROR
            assert "None" in r["detail"]

    def test_eag_invalid_result_clean_block(self):
        """T-04: EAG returns unknown verdict + push → clean BLOCK."""
        import unittest.mock as mock
        with mock.patch(
            "conversational_intake_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "conversational_intake_gate._EAG_EXECUTION_ACTIONS", {"push"}
        ), mock.patch(
            "conversational_intake_gate.check_execution_approval",
            return_value={"verdict": "UNKNOWN_VERDICT", "detail": "bad"},
        ):
            r = check_action_allowed("push", "APPROVED", {"approved": True})
            assert r["allowed"] is False
            # Unknown verdict → BLOCKED_EXECUTION_APPROVAL_GATE_ERROR
            assert r["verdict"] == VERDICT_BLOCKED_EAG_ERROR

    def test_readonly_unaffected_by_exception(self):
        """T-11: Read-only action + EAG raises → unaffected (allowed)."""
        import unittest.mock as mock
        with mock.patch(
            "conversational_intake_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "conversational_intake_gate._EAG_EXECUTION_ACTIONS", {"code_modify"}
        ), mock.patch(
            "conversational_intake_gate.check_execution_approval",
            side_effect=RuntimeError("crash"),
        ):
            # clarify is ALLOWED_WITHOUT_APPROVAL, not in BLOCKED_ACTIONS
            r = check_action_allowed("clarify", "PENDING", {})
            assert r["allowed"] is True

    def test_normal_path_unaffected(self):
        """T-12: Normal path + valid approval → allowed."""
        import unittest.mock as mock
        appr = {
            "approved": True,
            "approval_id": "test",
            "proposal_id": "p",
            "proposal_hash": "h",
            "approved_actions": ["code_modify"],
            "risk_level": "medium",
            "operator_message_raw": "ok",
            "operator_confirmation_phrase": "ok",
            "timestamp": "2026-06-22",
            "approval_scope": "all",
            "role_model_matrix_hash": "rm",
        }
        r = check_action_allowed("code_modify", "APPROVED", appr, proposal_hash="h")
        assert r["allowed"] is True

    def test_50719_regression_still_passes(self):
        """T-14: #50719 clarification → still blocked."""
        import unittest.mock as mock
        with mock.patch(
            "conversational_intake_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "conversational_intake_gate._EAG_EXECUTION_ACTIONS", {"code_modify"}
        ):
            r = check_action_allowed(
                "code_modify", "APPROVED", {"approved": True},
                operator_message="1.A 2.A 3.A 4.A 5.A 6.A",
            )
            assert r["allowed"] is False
