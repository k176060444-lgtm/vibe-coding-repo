#!/usr/bin/env python3
"""Tests for Execution Approval Binding Gate v1.0.0 (V1.21.11).

Covers all 18 required test scenarios from the V1.21.11 specification,
plus the #50719 incident regression fixture.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from execution_approval_gate import (
    ALL_VERDICTS,
    APPROVAL_BOUND,
    APPROVAL_REQUIRED,
    BLOCKED_ACTION_NOT_APPROVED,
    BLOCKED_APPROVAL_NOT_BOUND_TO_PROPOSAL,
    BLOCKED_CLARIFICATION_NOT_APPROVAL,
    BLOCKED_EXECUTION_WITHOUT_APPROVAL,
    BLOCKED_STALE_APPROVAL,
    EXECUTION_ACTIONS,
    PASS_READ_ONLY,
    READ_ONLY_ACTIONS,
    check_execution_approval,
    classify_action,
    detect_clarification_not_approval,
    validate_approval_record,
)


def _make_approval(
    approved_actions=None,
    proposal_id="proposal-001",
    proposal_hash="abc123def456",
    changed_files=None,
    allowed_patterns=None,
    timestamp=None,
):
    """Helper: create a valid approval record."""
    ts = timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    if approved_actions is None:
        approved_actions = [
            "code_modify", "branch_create", "commit", "push_feature_branch",
            "create_draft_pr",
        ]
    return {
        "approval_id": "approval-test-001",
        "proposal_id": proposal_id,
        "proposal_hash": proposal_hash,
        "approved_actions": approved_actions,
        "risk_level": "medium",
        "changed_files": changed_files or ["scripts/foo.py", "tests/test_foo.py"],
        "allowed_file_patterns": allowed_patterns or ["scripts/*.py", "tests/*.py"],
        "role_model_matrix_hash": "rmatrix_abc123",
        "operator_message_raw": "批准执行：实现 foo 功能",
        "operator_confirmation_phrase": "批准执行",
        "timestamp": ts,
        "approval_scope": "scripts/ and tests/ only",
    }


# ── Test 1: read-only research -> PASS_READ_ONLY ─────────────────────


class TestReadOnlyPasses:
    """Read-only research actions should always PASS_READ_ONLY."""

    def test_research_action(self):
        r = check_execution_approval(action="research")
        assert r["verdict"] == PASS_READ_ONLY
        assert r["action_class"] == "read_only"

    def test_explore_action(self):
        r = check_execution_approval(action="explore")
        assert r["verdict"] == PASS_READ_ONLY

    def test_diff_action(self):
        r = check_execution_approval(action="diff")
        assert r["verdict"] == PASS_READ_ONLY

    def test_search_action(self):
        r = check_execution_approval(action="search")
        assert r["verdict"] == PASS_READ_ONLY

    def test_self_check_action(self):
        r = check_execution_approval(action="self_check")
        assert r["verdict"] == PASS_READ_ONLY


# ── Test 2-6: execution actions without approval -> BLOCKED ───────────


class TestExecutionWithoutApproval:
    """Execution actions without any approval must be BLOCKED."""

    def test_code_modify_no_approval(self):
        """Test 2: code_modify without approval -> BLOCKED."""
        r = check_execution_approval(action="code_modify")
        assert r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL

    def test_branch_create_no_approval(self):
        """Test 3: branch_create without approval -> BLOCKED."""
        r = check_execution_approval(action="branch_create")
        assert r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL

    def test_commit_no_approval(self):
        """Test 4: commit without approval -> BLOCKED."""
        r = check_execution_approval(action="commit")
        assert r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL

    def test_push_feature_branch_no_approval(self):
        """Test 5: push_feature_branch without approval -> BLOCKED."""
        r = check_execution_approval(action="push_feature_branch")
        assert r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL

    def test_create_draft_pr_no_approval(self):
        """Test 6: create_draft_pr without approval -> BLOCKED."""
        r = check_execution_approval(action="create_draft_pr")
        assert r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL


# ── Test 7-8: clarification answers misinterpreted as approval ────────


class TestClarificationNotApproval:
    """Clarification answers must NOT be treated as execution approval."""

    def test_option_selection_pattern(self):
        """Test 7: "1.A 2.A 3.A 4.A 5.A 6.A" -> BLOCKED."""
        r = check_execution_approval(
            action="code_modify",
            operator_message="1.A 2.A 3.A 4.A 5.A 6.A",
        )
        assert r["verdict"] == BLOCKED_CLARIFICATION_NOT_APPROVAL

    def test_rhetorical_question(self):
        """Test 8: "你应该知道怎么提PR吧？" -> BLOCKED."""
        r = check_execution_approval(
            action="pr_create",
            operator_message="你应该知道怎么提PR吧？",
        )
        assert r["verdict"] == BLOCKED_CLARIFICATION_NOT_APPROVAL

    def test_vague_agreement_continue(self):
        """"可以继续" -> BLOCKED."""
        r = check_execution_approval(
            action="code_modify",
            operator_message="可以继续",
        )
        assert r["verdict"] == BLOCKED_CLARIFICATION_NOT_APPROVAL

    def test_vague_agreement_do_it(self):
        """"按你说的做" -> BLOCKED."""
        r = check_execution_approval(
            action="branch_create",
            operator_message="按你说的做",
        )
        assert r["verdict"] == BLOCKED_CLARIFICATION_NOT_APPROVAL

    def test_delegation_question_en(self):
        """"you should know how to do this" -> BLOCKED."""
        r = check_execution_approval(
            action="pr_create",
            operator_message="you should know how to create a PR, right?",
        )
        assert r["verdict"] == BLOCKED_CLARIFICATION_NOT_APPROVAL


# ── Test 9: proposal exists but no approval -> APPROVAL_REQUIRED ──────


class TestProposalNoApproval:
    """When a proposal exists but no approval is given, should require approval."""

    def test_proposal_exists_no_approval(self):
        """Test 9: proposal exists, no approval -> BLOCKED (no approval record)."""
        r = check_execution_approval(
            action="code_modify",
            proposal_exists=True,
        )
        # Without an approval record, it's still BLOCKED_EXECUTION_WITHOUT_APPROVAL
        assert r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL


# ── Test 10: approval not bound to proposal ───────────────────────────


class TestApprovalNotBound:
    """Approval without proposal binding must be BLOCKED."""

    def test_approval_no_proposal_hash_or_id(self):
        """Test 10: approval exists but no proposal_id/proposal_hash -> BLOCKED."""
        bad_approval = {
            "approval_id": "approval-bad-001",
            "approved_actions": ["code_modify"],
            "risk_level": "medium",
            "operator_message_raw": "approved",
            "operator_confirmation_phrase": "approved",
            "timestamp": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S+00:00"
            ),
            "approval_scope": "all",
        }
        r = check_execution_approval(
            action="code_modify",
            approval=bad_approval,
        )
        assert r["verdict"] == BLOCKED_APPROVAL_NOT_BOUND_TO_PROPOSAL


# ── Test 11: action not in approved_actions ───────────────────────────


class TestActionNotApproved:
    """Action not in the approved list must be BLOCKED."""

    def test_code_modify_not_in_approved(self):
        """Test 11: approval only has 'commit', trying 'code_modify' -> BLOCKED."""
        approval = _make_approval(approved_actions=["commit"])
        r = check_execution_approval(
            action="code_modify",
            approval=approval,
            proposal_hash="abc123def456",
        )
        assert r["verdict"] == BLOCKED_ACTION_NOT_APPROVED

    def test_push_not_in_approved(self):
        """push_feature_branch not in approved -> BLOCKED."""
        approval = _make_approval(approved_actions=["code_modify", "commit"])
        r = check_execution_approval(
            action="push_feature_branch",
            approval=approval,
            proposal_hash="abc123def456",
        )
        assert r["verdict"] == BLOCKED_ACTION_NOT_APPROVED


# ── Test 12: changed file outside approved scope ──────────────────────


class TestFileScopeEnforcement:
    """Files outside approval scope must be BLOCKED."""

    def test_file_outside_explicit_list(self):
        """Test 12: changed file not in approved files -> BLOCKED."""
        approval = _make_approval()
        r = check_execution_approval(
            action="code_modify",
            approval=approval,
            proposal_hash="abc123def456",
            changed_files=["scripts/foo.py", "secrets/credentials.json"],
        )
        assert r["verdict"] == BLOCKED_ACTION_NOT_APPROVED

    def test_file_within_scope(self):
        """Files within approved scope -> APPROVAL_BOUND."""
        approval = _make_approval()
        r = check_execution_approval(
            action="code_modify",
            approval=approval,
            proposal_hash="abc123def456",
            changed_files=["scripts/foo.py", "tests/test_foo.py"],
        )
        assert r["verdict"] == APPROVAL_BOUND


# ── Test 13: proper approval -> APPROVAL_BOUND ────────────────────────


class TestProperApproval:
    """Proper approval with all checks should APPROVAL_BOUND."""

    def test_all_checks_pass(self):
        """Test 13: proper approval + allowed action -> APPROVAL_BOUND."""
        approval = _make_approval()
        r = check_execution_approval(
            action="code_modify",
            approval=approval,
            proposal_hash="abc123def456",
        )
        assert r["verdict"] == APPROVAL_BOUND
        assert r["approval_id"] == "approval-test-001"

    def test_push_with_approval(self):
        """Test 17: push with approval and files in scope -> APPROVAL_BOUND."""
        approval = _make_approval(
            approved_actions=[
                "code_modify", "branch_create", "commit", "push_feature_branch",
            ]
        )
        r = check_execution_approval(
            action="push_feature_branch",
            approval=approval,
            proposal_hash="abc123def456",
            changed_files=["scripts/foo.py", "tests/test_foo.py"],
        )
        assert r["verdict"] == APPROVAL_BOUND


# ── Test 14: Draft PR still requires execution approval ───────────────


class TestDraftPRRequiresApproval:
    """Draft PR auto-allowed policy does NOT exempt execution approval."""

    def test_draft_pr_no_approval(self):
        """Test 14: create_draft_pr without approval -> BLOCKED."""
        r = check_execution_approval(action="create_draft_pr")
        assert r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL

    def test_update_draft_pr_no_approval(self):
        """update_draft_pr without approval -> BLOCKED."""
        r = check_execution_approval(action="update_draft_pr")
        assert r["verdict"] == BLOCKED_EXECUTION_WITHOUT_APPROVAL

    def test_draft_pr_with_approval(self):
        """create_draft_pr with proper approval -> APPROVAL_BOUND."""
        approval = _make_approval(
            approved_actions=["create_draft_pr", "push_feature_branch"]
        )
        r = check_execution_approval(
            action="create_draft_pr",
            approval=approval,
            proposal_hash="abc123def456",
        )
        assert r["verdict"] == APPROVAL_BOUND


# ── Test 15: report schema includes execution_approval ────────────────


class TestReportSchemaIntegration:
    """Report schema should recognize execution_approval section."""

    def test_execution_approval_in_optional_sections(self):
        """Test 15: execution_approval should be in optional sections."""
        # Import report schema to verify
        from vibe_report_schema import OPTIONAL_SECTIONS
        assert "execution_approval" in OPTIONAL_SECTIONS


# ── Test 16: router aliases work ──────────────────────────────────────


class TestRouterAliases:
    """Command router should have execution-approval-check aliases."""

    def test_router_has_command(self):
        """Test 16: router has execution-approval-check command."""
        from vibe_command_router import COMMAND_SCRIPTS, ALIASES
        assert "execution-approval-check" in COMMAND_SCRIPTS
        assert COMMAND_SCRIPTS["execution-approval-check"] == "execution_approval_gate.py"

    def test_router_aliases(self):
        """Router has eac and abc aliases."""
        from vibe_command_router import ALIASES, COMMAND_SCRIPTS
        assert ALIASES.get("eac") == "execution-approval-check"
        assert ALIASES.get("abc") == "approval-bind-check"
        assert "approval-bind-check" in COMMAND_SCRIPTS


# ── Test 17: V1.21.6/8/9/10 self-checks still pass ──────────────────


class TestRegressionSelfChecks:
    """Existing gate self-checks should still pass."""

    def test_conversational_intake_self_check(self):
        """V1.21.6 conversational_intake_gate self-check."""
        from conversational_intake_gate import self_check
        result = self_check()
        assert result.get("passed", False), f"intake self-check failed: {result}"

    def test_report_schema_self_check(self):
        """V1.21.8 report schema self-check."""
        from vibe_report_schema import self_check
        result = self_check()
        assert result["overall"] == "PASS", f"report schema self-check failed: {result}"

    def test_git_pr_approval_self_check(self):
        """V1.21.10 git_pr_approval_gate self-check."""
        from git_pr_approval_gate import self_check
        result = self_check()
        assert result.get("result") in ("PASS", "PASSED"), f"git pr approval self-check failed: {result}"


# ── Test 18: #50719 incident regression fixture ───────────────────────


class TestIncident50719Regression:
    """Regression test for the #50719 incident.

    The exact operator message from the incident must be detected as
    clarification, NOT approval.
    """

    def test_exact_incident_message(self):
        """Test 18: exact #50719 operator message -> BLOCKED."""
        r = check_execution_approval(
            action="pr_create",
            operator_message=(
                "1.A 2.A 3.A 4.A 5.A 6.A。另外，这个功能的实现是需要给 "
                "Hermes 官方提 PR 的。关于如何提出 PR，你应该是知道的吧？"
            ),
        )
        assert r["verdict"] == BLOCKED_CLARIFICATION_NOT_APPROVAL

    def test_option_selection_only(self):
        """Pure option selection -> BLOCKED."""
        r = check_execution_approval(
            action="code_modify",
            operator_message="1.A 2.A 3.A 4.A 5.A 6.A",
        )
        assert r["verdict"] == BLOCKED_CLARIFICATION_NOT_APPROVAL

    def test_rhetorical_with_context(self):
        """Rhetorical question with context -> BLOCKED."""
        r = check_execution_approval(
            action="push",
            operator_message="你应该是知道的吧？",
        )
        assert r["verdict"] == BLOCKED_CLARIFICATION_NOT_APPROVAL


# ── Helper function tests ─────────────────────────────────────────────


class TestClassifyAction:
    """Action classification tests."""

    def test_execution_actions(self):
        for action in EXECUTION_ACTIONS:
            assert classify_action(action) == "execution", f"{action} should be execution"

    def test_read_only_actions(self):
        for action in READ_ONLY_ACTIONS:
            assert classify_action(action) == "read_only", f"{action} should be read_only"

    def test_unknown_action(self):
        assert classify_action("totally_unknown_action") == "unknown"


class TestDetectClarification:
    """Clarification detection tests."""

    def test_empty_message(self):
        r = detect_clarification_not_approval("")
        assert r["is_clarification"] is False

    def test_option_selection(self):
        r = detect_clarification_not_approval("1.A 2.B 3.C")
        assert r["is_clarification"] is True
        assert r["pattern_type"] == "option_selection"

    def test_normal_approval_message(self):
        r = detect_clarification_not_approval("批准执行，开始实施")
        assert r["is_clarification"] is False

    def test_chinese_option_selection(self):
        r = detect_clarification_not_approval("选A")
        assert r["is_clarification"] is True


class TestValidateApprovalRecord:
    """Approval record validation tests."""

    def test_valid_record(self):
        approval = _make_approval()
        r = validate_approval_record(approval)
        assert r["valid"] is True
        assert len(r["errors"]) == 0

    def test_none_record(self):
        r = validate_approval_record(None)
        assert r["valid"] is False

    def test_missing_proposal_binding(self):
        approval = _make_approval()
        del approval["proposal_id"]
        del approval["proposal_hash"]
        r = validate_approval_record(approval)
        assert r["valid"] is False
        assert any("proposal" in e for e in r["errors"])

    def test_empty_approved_actions(self):
        approval = _make_approval(approved_actions=[])
        r = validate_approval_record(approval)
        assert r["valid"] is False


# ── F-01: Risk-aware role_model_matrix_hash ──────────────────────────


class TestF01RiskAwareRoleModelMatrixHash:
    """F-01: role_model_matrix_hash missing must BLOCK for high/critical,
    WARN for low/medium."""

    def test_high_risk_no_hash_blocked(self):
        """T-01: high risk + missing hash -> BLOCKED."""
        approval = _make_approval()
        del approval["role_model_matrix_hash"]
        approval["risk_level"] = "high"
        r = check_execution_approval(
            action="code_modify",
            approval=approval,
            proposal_hash="abc123def456",
        )
        assert r["verdict"] == BLOCKED_ACTION_NOT_APPROVED

    def test_critical_risk_no_hash_blocked(self):
        """T-02: critical risk + missing hash -> BLOCKED."""
        approval = _make_approval()
        del approval["role_model_matrix_hash"]
        approval["risk_level"] = "critical"
        r = check_execution_approval(
            action="code_modify",
            approval=approval,
            proposal_hash="abc123def456",
        )
        assert r["verdict"] == BLOCKED_ACTION_NOT_APPROVED

    def test_medium_risk_no_hash_warn(self):
        """T-03: medium risk + missing hash -> WARN (APPROVAL_BOUND)."""
        approval = _make_approval()
        del approval["role_model_matrix_hash"]
        approval["risk_level"] = "medium"
        r = check_execution_approval(
            action="code_modify",
            approval=approval,
            proposal_hash="abc123def456",
        )
        assert r["verdict"] == APPROVAL_BOUND
        # Check that WARN was emitted
        rm_checks = [c for c in r["checks"] if c["name"] == "role_model_matrix"]
        assert rm_checks[0]["result"] == "WARN"

    def test_low_risk_no_hash_warn(self):
        """T-04: low risk + missing hash -> WARN (APPROVAL_BOUND)."""
        approval = _make_approval()
        del approval["role_model_matrix_hash"]
        approval["risk_level"] = "low"
        r = check_execution_approval(
            action="code_modify",
            approval=approval,
            proposal_hash="abc123def456",
        )
        assert r["verdict"] == APPROVAL_BOUND
        rm_checks = [c for c in r["checks"] if c["name"] == "role_model_matrix"]
        assert rm_checks[0]["result"] == "WARN"

    def test_hash_present_any_risk_passes(self):
        """T-05: hash present + any risk -> PASS."""
        for risk in ("low", "medium", "high", "critical"):
            approval = _make_approval()
            approval["risk_level"] = risk
            r = check_execution_approval(
                action="code_modify",
                approval=approval,
                proposal_hash="abc123def456",
            )
            assert r["verdict"] == APPROVAL_BOUND, f"Failed for risk_level={risk}"


# ── Integration: conversational_intake_gate wiring ────────────────────


class TestIntakeGateWiring:
    """T-14/T-15/T-16/T-18: conversational_intake_gate + execution_approval_gate integration."""

    def test_intake_approved_with_binding(self):
        """T-14: check_action_allowed with valid approval + binding -> allowed."""
        from conversational_intake_gate import check_action_allowed, create_approval_record, create_intake_record
        intake = create_intake_record(user_request_raw="test", risk_level="medium")
        approval = create_approval_record(
            intake_id=intake["intake_id"],
            approved=True,
            approved_actions=["code_modify"],
        )
        # Add required fields for execution_approval_gate
        approval["approval_id"] = "approval-test-001"
        approval["proposal_id"] = "p1"
        approval["proposal_hash"] = "abc123"
        approval["risk_level"] = "medium"
        approval["operator_message_raw"] = "approved"
        approval["operator_confirmation_phrase"] = "approved"
        approval["approval_scope"] = "all"
        r = check_action_allowed(
            action="code_modify",
            state="APPROVED",
            approval=approval,
            proposal_hash="abc123",
        )
        assert r["allowed"] is True

    def test_intake_no_binding_blocked(self):
        """T-15: check_action_allowed with approval but no binding -> blocked."""
        from conversational_intake_gate import check_action_allowed, create_approval_record, create_intake_record
        intake = create_intake_record(user_request_raw="test", risk_level="medium")
        approval = create_approval_record(
            intake_id=intake["intake_id"],
            approved=True,
            approved_actions=["code_modify"],
        )
        # No proposal_id/proposal_hash — should be blocked by EAG
        r = check_action_allowed(
            action="code_modify",
            state="APPROVED",
            approval=approval,
        )
        assert r["allowed"] is False

    def test_intake_clarification_blocked(self):
        """T-08: #50719 flow — clarification answer via intake gate -> blocked."""
        from conversational_intake_gate import check_action_allowed
        r = check_action_allowed(
            action="code_modify",
            state="APPROVED",
            approval={"approved": True},
            operator_message="1.A 2.A 3.A 4.A 5.A 6.A",
        )
        assert r["allowed"] is False
        assert "clarification" in r["detail"].lower() or "BLOCKED" in r["verdict"]

    def test_intake_proposal_state_blocked(self):
        """T-16: check_action_allowed in PROPOSED state -> blocked."""
        from conversational_intake_gate import check_action_allowed
        r = check_action_allowed(
            action="push",
            state="PROPOSED",
            approval=None,
        )
        assert r["allowed"] is False


# ── Integration: git_pr_approval_gate Gate 0 ──────────────────────────


class TestGitPrGate0:
    """T-10/T-11/T-12/T-13/T-17/T-19: git_pr_approval_gate Gate 0 wiring."""

    def test_push_without_execution_approval_blocked(self):
        """T-11: push_feature_branch without execution approval -> BLOCKED."""
        from git_pr_approval_gate import check_git_pr_action
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            source_branch="feat/test",
            checks_passed=True,
            intake_approved=True,
            execution_approval=None,
        )
        assert r["allowed"] is False
        assert r["verdict"] == "BLOCKED_EXECUTION_APPROVAL_REQUIRED"

    def test_push_with_execution_approval_allowed(self):
        """T-12: push_feature_branch with execution approval -> AUTO_ALLOWED."""
        from git_pr_approval_gate import check_git_pr_action
        approval = _make_approval(
            approved_actions=["push_feature_branch", "create_draft_pr"],
        )
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            source_branch="feat/test",
            checks_passed=True,
            intake_approved=True,
            execution_approval=approval,
            proposal_hash="abc123def456",
        )
        assert r["allowed"] is True
        assert r["verdict"] == "AUTO_ALLOWED_WITH_GATES"

    def test_draft_pr_without_execution_approval_blocked(self):
        """T-13: create_draft_pr without execution approval -> BLOCKED."""
        from git_pr_approval_gate import check_git_pr_action
        r = check_git_pr_action(
            action="create_draft_pr",
            checks_passed=True,
            intake_approved=True,
            execution_approval=None,
        )
        assert r["allowed"] is False
        assert r["verdict"] == "BLOCKED_EXECUTION_APPROVAL_REQUIRED"

    def test_draft_pr_with_execution_approval_allowed(self):
        """T-14 git: create_draft_pr with execution approval -> AUTO_ALLOWED."""
        from git_pr_approval_gate import check_git_pr_action
        approval = _make_approval(
            approved_actions=["push_feature_branch", "create_draft_pr"],
        )
        r = check_git_pr_action(
            action="create_draft_pr",
            checks_passed=True,
            intake_approved=True,
            execution_approval=approval,
            proposal_hash="abc123def456",
        )
        assert r["allowed"] is True
        assert r["verdict"] == "AUTO_ALLOWED_WITH_GATES"

    def test_gate0_high_risk_no_hash_blocked(self):
        """T-19: high risk + missing hash via git flow -> BLOCKED."""
        from git_pr_approval_gate import check_git_pr_action
        approval = _make_approval(
            approved_actions=["push_feature_branch"],
        )
        del approval["role_model_matrix_hash"]
        approval["risk_level"] = "high"
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            source_branch="feat/test",
            checks_passed=True,
            intake_approved=True,
            execution_approval=approval,
            proposal_hash="abc123def456",
        )
        assert r["allowed"] is False

    def test_clarification_via_git_flow_blocked(self):
        """T-10: #50719 — clarification answer via git flow -> BLOCKED."""
        from git_pr_approval_gate import check_git_pr_action
        r = check_git_pr_action(
            action="create_draft_pr",
            checks_passed=True,
            intake_approved=True,
            operator_message="1.A 2.A 3.A 4.A 5.A 6.A",
        )
        assert r["allowed"] is False
