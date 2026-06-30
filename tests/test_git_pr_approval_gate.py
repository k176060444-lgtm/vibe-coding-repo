#!/usr/bin/env python3
"""Tests for Git/PR State Approval Gate v1.3.0 (baseline01 fail-closed).

baseline01 G3: all git write actions (push_feature_branch, create_draft_pr,
update_draft_pr, draft_to_ready, merge, branch_delete, force_push, release_tag,
push_main, push_protected_branch, ready_to_merge, production_gateway_change,
worker_ssh_mutation, secrets_credential_change, admin_uac_service_change) are
operator-required. There is no AUTO_ALLOWED set and no AUTO_ALLOWED_WITH_GATES
verdict. Every gate test below asserts fail-closed semantics:
    verdict == "OPERATOR_APPROVAL_REQUIRED" (or a more specific BLOCK verdict)
    allowed is False
    requires_operator_approval is True (when operator approval is the binding
    reason)
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from git_pr_approval_gate import (
    ALL_ACTIONS,
    ALWAYS_BLOCKED_ACTIONS,
    OPERATOR_REQUIRED_ACTIONS,
    PROTECTED_BRANCHES,
    VERDICTS,
    check_git_pr_action,
)


# V1.21.12: Helper execution approval for tests
_EAG_APPROVAL = {
    "approval_id": "test-approval",
    "proposal_id": "test-proposal",
    "proposal_hash": "testhash",
    "approved_actions": [
        "push_feature_branch", "create_draft_pr", "update_draft_pr",
        "code_modify", "commit", "branch_create",
    ],
    "risk_level": "medium",
    "operator_message_raw": "test approval",
    "operator_confirmation_phrase": "approved",
    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
    "approval_scope": "test",
    "role_model_matrix_hash": "testrmatrix",
}


class TestPushFeatureOperatorRequired:
    """baseline01 G3: push_feature_branch is OPERATOR_REQUIRED.

    Pre-baseline01 the same action could resolve to AUTO_ALLOWED_WITH_GATES when
    checks + intake + execution approval were all green. After PR #270 the
    action is folded into OPERATOR_REQUIRED_ACTIONS and must always return
    OPERATOR_APPROVAL_REQUIRED with allowed=False.
    """

    def test_push_feature_gates_passed_still_operator_required(self):
        """Push feature branch + all gates passed → OPERATOR_APPROVAL_REQUIRED (fail-closed)."""
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            source_branch="feat/test",
            checks_passed=True,
            intake_approved=True,
            execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["allowed"] is False
        assert r["requires_operator_approval"] is True
        assert "safe_auto_actions" not in r or "push_feature_branch" not in r.get("safe_auto_actions", [])

    def test_push_feature_intake_not_approved(self):
        """Push feature without intake → OPERATOR_APPROVAL_REQUIRED (operator gate first).

        Pre-baseline01 this case resolved to BLOCKED_UNAPPROVED_GIT_ACTION at
        the intake gate. After PR #270 push_feature_branch is OPERATOR_REQUIRED;
        the operator gate runs first and the action is blocked regardless of
        intake/checks status.
        """
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            checks_passed=True,
            intake_approved=False,
            execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["allowed"] is False
        assert r["requires_operator_approval"] is True

    def test_push_feature_checks_not_passed(self):
        """Push feature without checks → OPERATOR_APPROVAL_REQUIRED (operator gate first)."""
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            checks_passed=False,
            intake_approved=True,
            execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["allowed"] is False
        assert r["requires_operator_approval"] is True

    def test_push_feature_to_main_blocked(self):
        """Push feature to main → BLOCKED_PROTECTED_BRANCH."""
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="main",
            checks_passed=True,
            intake_approved=True,
            execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "BLOCKED_PROTECTED_BRANCH"
        assert r["allowed"] is False


class TestDraftPROperatorRequired:
    """baseline01 G3: create_draft_pr / update_draft_pr are OPERATOR_REQUIRED.

    Pre-baseline01 these actions could resolve to AUTO_ALLOWED_WITH_GATES when
    checks + intake + execution approval were green. After PR #270 they are
    folded into OPERATOR_REQUIRED_ACTIONS and must always require operator
    approval, regardless of gate outcomes.
    """

    def test_create_draft_pr_gates_passed_still_operator_required(self):
        """Create Draft PR + all gates passed → OPERATOR_APPROVAL_REQUIRED (fail-closed)."""
        r = check_git_pr_action(
            action="create_draft_pr",
            target_branch="main",
            source_branch="feat/test",
            desired_pr_state="DRAFT",
            checks_passed=True,
            intake_approved=True,
                    execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["allowed"] is False
        assert r["requires_operator_approval"] is True

    def test_update_draft_pr_gates_passed_still_operator_required(self):
        """Update Draft PR + all gates passed → OPERATOR_APPROVAL_REQUIRED (fail-closed)."""
        r = check_git_pr_action(
            action="update_draft_pr",
            target_branch="main",
            desired_pr_state="DRAFT",
            checks_passed=True,
            intake_approved=True,
                    execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["allowed"] is False
        assert r["requires_operator_approval"] is True

    def test_create_draft_with_open_state_blocked(self):
        """Create Draft PR with desired state OPEN → OPERATOR_APPROVAL_REQUIRED (operator gate first).

        Pre-baseline01 this case resolved to BLOCKED_READY_WITHOUT_APPROVAL
        via the desired-state check. After PR #270 create_draft_pr is
        OPERATOR_REQUIRED; the operator gate runs first and the action is
        blocked regardless of desired_pr_state.
        """
        r = check_git_pr_action(
            action="create_draft_pr",
            target_branch="main",
            desired_pr_state="OPEN",
            checks_passed=True,
            intake_approved=True,
                    execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["allowed"] is False
        assert r["requires_operator_approval"] is True


class TestBlockedCreateReadyPR:
    """BLOCKED: create Ready PR directly."""

    def test_create_ready_pr_blocked(self):
        """Create Ready PR directly → BLOCKED."""
        r = check_git_pr_action(action="create_ready_pr", desired_pr_state="OPEN")
        assert r["verdict"] == "BLOCKED_READY_WITHOUT_APPROVAL"
        assert r["allowed"] is False


class TestDraftToReady:
    """Draft → Ready transition."""

    def test_draft_to_ready_no_approval(self):
        """Draft→Ready without approval → BLOCKED."""
        r = check_git_pr_action(
            action="draft_to_ready",
            pr_number=100,
            current_pr_state="DRAFT",
            desired_pr_state="OPEN",
        )
        assert r["verdict"] == "BLOCKED_READY_WITHOUT_APPROVAL"
        assert r["allowed"] is False
        assert r["requires_operator_approval"] is True

    def test_draft_to_ready_with_approval(self):
        """Draft→Ready with approval → PASS."""
        r = check_git_pr_action(
            action="draft_to_ready",
            pr_number=100,
            current_pr_state="DRAFT",
            desired_pr_state="OPEN",
            operator_approval_id="approval-001",
            operator_approved_actions=["draft_to_ready"],
        )
        assert r["verdict"] == "PASS"
        assert r["allowed"] is True


class TestMerge:
    """Merge approval flow."""

    def test_merge_no_approval(self):
        """Merge without approval → BLOCKED."""
        r = check_git_pr_action(action="merge", pr_number=100)
        assert r["verdict"] == "BLOCKED_MERGE_WITHOUT_APPROVAL"
        assert r["allowed"] is False

    def test_merge_approval_no_remote_verification(self):
        """Merge with approval but no remote verification → BLOCKED."""
        r = check_git_pr_action(
            action="merge",
            pr_number=100,
            operator_approval_id="approval-001",
            operator_approved_actions=["merge"],
            remote_verified=False,
            merge_check_passed=False,
        )
        assert r["verdict"] == "BLOCKED_REMOTE_VERIFICATION_REQUIRED"
        assert r["allowed"] is False
        assert r["remote_verification_required"] is True

    def test_merge_approval_remote_verified_no_merge_check(self):
        """Merge with approval + remote verified but no merge check → BLOCKED."""
        r = check_git_pr_action(
            action="merge",
            pr_number=100,
            operator_approval_id="approval-001",
            operator_approved_actions=["merge"],
            remote_verified=True,
            merge_check_passed=False,
        )
        assert r["verdict"] == "BLOCKED_REMOTE_VERIFICATION_REQUIRED"
        assert r["allowed"] is False

    def test_merge_full_pass(self):
        """Merge with approval + remote verification + merge check → PASS."""
        r = check_git_pr_action(
            action="merge",
            pr_number=100,
            operator_approval_id="approval-001",
            operator_approved_actions=["merge"],
            remote_verified=True,
            merge_check_passed=True,
        )
        assert r["verdict"] == "PASS"
        assert r["allowed"] is True
        assert r["approval_binding_fields"]["approval_id"] == "approval-001"
        assert r["approval_binding_fields"]["remote_verified"] is True
        assert r["approval_binding_fields"]["merge_check_passed"] is True

    def test_merge_wrong_approval_action(self):
        """Merge with approval for different action → BLOCKED."""
        r = check_git_pr_action(
            action="merge",
            pr_number=100,
            operator_approval_id="approval-001",
            operator_approved_actions=["draft_to_ready"],
            remote_verified=True,
            merge_check_passed=True,
        )
        assert r["verdict"] == "BLOCKED_MERGE_WITHOUT_APPROVAL"
        assert r["allowed"] is False


class TestProtectedBranch:
    """Push to protected branch."""

    def test_push_main_no_approval(self):
        """Push main without approval → BLOCKED."""
        r = check_git_pr_action(action="push_main", target_branch="main")
        assert r["verdict"] == "BLOCKED_PROTECTED_BRANCH"
        assert r["allowed"] is False

    def test_push_main_with_approval(self):
        """Push main with approval → PASS."""
        r = check_git_pr_action(
            action="push_main",
            target_branch="main",
            operator_approval_id="approval-002",
            operator_approved_actions=["push_main"],
        )
        assert r["verdict"] == "PASS"
        assert r["allowed"] is True

    def test_push_protected_staging(self):
        """Push to staging without approval → BLOCKED."""
        r = check_git_pr_action(
            action="push_protected_branch",
            target_branch="staging",
        )
        assert r["verdict"] == "BLOCKED_PROTECTED_BRANCH"
        assert r["allowed"] is False


class TestForcePush:
    """Force push."""

    def test_force_push_no_approval(self):
        """Force push without approval → BLOCKED."""
        r = check_git_pr_action(action="force_push", force_push=True)
        assert r["verdict"] == "BLOCKED_FORCE_PUSH"
        assert r["allowed"] is False

    def test_force_push_with_approval(self):
        """Force push with approval → PASS."""
        r = check_git_pr_action(
            action="force_push",
            force_push=True,
            operator_approval_id="approval-003",
            operator_approved_actions=["force_push"],
        )
        assert r["verdict"] == "PASS"
        assert r["allowed"] is True

    def test_embedded_force_push_blocked(self):
        """Force push embedded in push_feature_branch → BLOCKED."""
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            checks_passed=True,
            intake_approved=True,
            force_push=True,
                    execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "BLOCKED_FORCE_PUSH"
        assert r["allowed"] is False


class TestBranchDelete:
    """Branch delete."""

    def test_branch_delete_no_approval_no_remote(self):
        """Branch delete without approval and without remote verification → BLOCKED."""
        r = check_git_pr_action(
            action="branch_delete",
            source_branch="feat/test",
            remote_verified=False,
        )
        assert r["verdict"] == "BLOCKED_UNAPPROVED_GIT_ACTION"
        assert r["allowed"] is False

    def test_branch_delete_after_merge(self):
        """Branch delete after merge (remote_verified) → PASS."""
        r = check_git_pr_action(
            action="branch_delete",
            source_branch="feat/test",
            remote_verified=True,
        )
        assert r["verdict"] == "PASS"
        assert r["allowed"] is True
        assert "branch_delete" in r["safe_auto_actions"]

    def test_branch_delete_with_approval(self):
        """Branch delete with explicit approval → PASS."""
        r = check_git_pr_action(
            action="branch_delete",
            source_branch="feat/test",
            operator_approval_id="approval-004",
            operator_approved_actions=["branch_delete"],
        )
        assert r["verdict"] == "PASS"
        assert r["allowed"] is True


class TestHighRiskFiles:
    """High-risk changed files."""

    def test_high_risk_secrets_file(self):
        """Changed files include secrets → OPERATOR_APPROVAL_REQUIRED."""
        r = check_git_pr_action(
            action="create_draft_pr",
            target_branch="main",
            desired_pr_state="DRAFT",
            checks_passed=True,
            intake_approved=True,
            changed_files=["scripts/conversational_intake_gate.py", "opencode.env"],
                    execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["allowed"] is False
        assert r["requires_operator_approval"] is True

    def test_high_risk_gateway_file(self):
        """Changed files include gateway → OPERATOR_APPROVAL_REQUIRED."""
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            checks_passed=True,
            intake_approved=True,
            changed_files=["scripts/gateway_windows.py"],
                    execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["allowed"] is False

    def test_no_high_risk_files_still_operator_required(self):
        """No high-risk files + all gates passed → OPERATOR_APPROVAL_REQUIRED (fail-closed).

        Pre-baseline01 this case resolved to AUTO_ALLOWED_WITH_GATES. After
        PR #270 create_draft_pr is OPERATOR_REQUIRED; the action is blocked
        at the operator gate regardless of file risk.
        """
        r = check_git_pr_action(
            action="create_draft_pr",
            target_branch="main",
            desired_pr_state="DRAFT",
            checks_passed=True,
            intake_approved=True,
            changed_files=["scripts/git_pr_approval_gate.py", "tests/test_git_pr_approval_gate.py"],
                    execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["allowed"] is False
        assert r["requires_operator_approval"] is True


class TestIntakeIntegration:
    """V1.21.6 intake approval integration."""

    def test_no_intake_still_operator_required(self):
        """Git action without intake approval → OPERATOR_APPROVAL_REQUIRED (operator gate first).

        Pre-baseline01 this case resolved to BLOCKED_UNAPPROVED_GIT_ACTION at
        the intake gate. After PR #270 the operator gate runs first; the
        action is blocked regardless of intake_approved status.
        """
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            checks_passed=True,
            intake_approved=False,
                    execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["allowed"] is False
        assert r["requires_operator_approval"] is True

    def test_with_intake_still_operator_required(self):
        """Git action with intake approval + checks → OPERATOR_APPROVAL_REQUIRED (fail-closed).

        Pre-baseline01 this case resolved to AUTO_ALLOWED_WITH_GATES. After
        PR #270 push_feature_branch is OPERATOR_REQUIRED regardless of intake
        status.
        """
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            checks_passed=True,
            intake_approved=True,
                    execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["allowed"] is False
        assert r["requires_operator_approval"] is True


class TestUnknownAction:
    """Unknown action handling."""

    def test_unknown_action_blocked(self):
        """Unknown action → BLOCKED."""
        r = check_git_pr_action(action="nonexistent_action")
        assert r["verdict"] == "BLOCKED_UNAPPROVED_GIT_ACTION"
        assert r["allowed"] is False


class TestGenericOperatorRequired:
    """Generic operator-required actions."""

    def test_release_tag_no_approval(self):
        """Release tag without approval → OPERATOR_APPROVAL_REQUIRED."""
        r = check_git_pr_action(action="release_tag")
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["requires_operator_approval"] is True

    def test_release_tag_with_approval(self):
        """Release tag with approval → PASS."""
        r = check_git_pr_action(
            action="release_tag",
            operator_approval_id="approval-005",
            operator_approved_actions=["release_tag"],
        )
        assert r["verdict"] == "PASS"
        assert r["allowed"] is True

    def test_production_gateway_no_approval(self):
        """Production gateway change without approval → BLOCKED."""
        r = check_git_pr_action(action="production_gateway_change")
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["requires_operator_approval"] is True

    def test_worker_ssh_no_approval(self):
        """Worker SSH mutation without approval → BLOCKED."""
        r = check_git_pr_action(action="worker_ssh_mutation")
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["requires_operator_approval"] is True

    def test_secrets_change_no_approval(self):
        """Secrets change without approval → BLOCKED."""
        r = check_git_pr_action(action="secrets_credential_change")
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["requires_operator_approval"] is True

    def test_admin_uac_no_approval(self):
        """Admin/UAC change without approval → BLOCKED."""
        r = check_git_pr_action(action="admin_uac_service_change")
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["requires_operator_approval"] is True


class TestPolicyConstants:
    """Policy constant validation (baseline01 G3 fail-closed)."""

    def test_verdicts_count(self):
        # baseline01 (PR #270): 10 verdicts, no AUTO_ALLOWED_WITH_GATES
        assert len(VERDICTS) == 10
        assert "AUTO_ALLOWED_WITH_GATES" not in VERDICTS
        assert "OPERATOR_APPROVAL_REQUIRED" in VERDICTS
        assert "PASS" in VERDICTS

    def test_no_auto_allowed_set(self):
        """baseline01: AUTO_ALLOWED_ACTIONS set must not exist on the module."""
        import git_pr_approval_gate as g
        assert not hasattr(g, "AUTO_ALLOWED_ACTIONS"), (
            "AUTO_ALLOWED_ACTIONS must be removed (baseline01 G3 fail-closed)"
        )

    def test_operator_required_count(self):
        # baseline01 (PR #270): 15 operator-required actions, including the
        # former auto-allowed set folded in
        assert len(OPERATOR_REQUIRED_ACTIONS) == 15
        # Sanity: the three former auto-allowed actions are now operator-required
        assert "push_feature_branch" in OPERATOR_REQUIRED_ACTIONS
        assert "create_draft_pr" in OPERATOR_REQUIRED_ACTIONS
        assert "update_draft_pr" in OPERATOR_REQUIRED_ACTIONS

    def test_always_blocked_count(self):
        assert len(ALWAYS_BLOCKED_ACTIONS) == 1
        assert "create_ready_pr" in ALWAYS_BLOCKED_ACTIONS

    def test_protected_branches_count(self):
        assert len(PROTECTED_BRANCHES) == 5
        assert "main" in PROTECTED_BRANCHES
        assert "production" in PROTECTED_BRANCHES

    def test_all_actions_equals_operator_plus_always_blocked(self):
        """ALL_ACTIONS is the union of OPERATOR_REQUIRED + ALWAYS_BLOCKED (no auto set)."""
        assert ALL_ACTIONS == OPERATOR_REQUIRED_ACTIONS | ALWAYS_BLOCKED_ACTIONS


class TestApprovalBinding:
    """Approval binding fields."""

    def test_merge_binding_fields(self):
        """Merge approval includes binding fields."""
        r = check_git_pr_action(
            action="merge",
            pr_number=100,
            operator_approval_id="approval-001",
            operator_approved_actions=["merge"],
            remote_verified=True,
            merge_check_passed=True,
        )
        assert r["approval_binding_fields"] is not None
        assert r["approval_binding_fields"]["approval_id"] == "approval-001"
        assert r["approval_binding_fields"]["action"] == "merge"
        assert r["approval_binding_fields"]["remote_verified"] is True
        assert r["approval_binding_fields"]["merge_check_passed"] is True

    def test_draft_to_ready_binding_fields(self):
        """Draft→Ready approval includes binding fields."""
        r = check_git_pr_action(
            action="draft_to_ready",
            operator_approval_id="approval-001",
            operator_approved_actions=["draft_to_ready"],
        )
        assert r["approval_binding_fields"] is not None
        assert r["approval_binding_fields"]["approval_id"] == "approval-001"

    def test_no_binding_when_no_approval(self):
        """No binding fields when no approval."""
        r = check_git_pr_action(action="merge")
        assert r["approval_binding_fields"] is None


class TestFailClosed:
    """baseline01 (PR #270): all git write actions are operator-required.

    Pre-baseline01 this class verified the EAG (Execution Approval Gate)
    fail-closed behavior for AUTO_ALLOWED actions. After PR #270 there is
    no AUTO_ALLOWED set, so the EAG layer is no longer the binding
    constraint. The tests below verify the new contract: even with
    execution_approval bound, push_feature_branch / create_draft_pr /
    update_draft_pr are blocked at the operator gate.
    """

    def test_push_feature_no_operator_approval_blocked(self):
        """push_feature_branch + no operator approval → OPERATOR_APPROVAL_REQUIRED (operator gate first).

        With no operator_approval_id, the action is blocked at the operator
        gate before any other gate can run. EAG unavailability does not
        change the verdict.
        """
        import unittest.mock as mock
        with mock.patch(
            "git_pr_approval_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", False
        ):
            r = check_git_pr_action(
                action="push_feature_branch",
                target_branch="feat-branch",
                source_branch="feat/v12112",
                intake_approved=True,
            )
            # baseline01: operator gate runs first; verdict is
            # OPERATOR_APPROVAL_REQUIRED regardless of EAG availability
            assert r["allowed"] is False
            assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
            assert r["requires_operator_approval"] is True

    def test_create_draft_pr_no_operator_approval_blocked(self):
        """create_draft_pr + no operator approval → OPERATOR_APPROVAL_REQUIRED."""
        import unittest.mock as mock
        with mock.patch(
            "git_pr_approval_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", False
        ):
            r = check_git_pr_action(
                action="create_draft_pr",
                target_branch="main",
                source_branch="feat/v12112",
                intake_approved=True,
            )
            assert r["allowed"] is False
            assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
            assert r["requires_operator_approval"] is True

    def test_update_draft_pr_no_operator_approval_blocked(self):
        """update_draft_pr + no operator approval → OPERATOR_APPROVAL_REQUIRED."""
        import unittest.mock as mock
        with mock.patch(
            "git_pr_approval_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", False
        ):
            r = check_git_pr_action(
                action="update_draft_pr",
                target_branch="main",
                source_branch="feat/v12112",
                pr_number=203,
                intake_approved=True,
            )
            assert r["allowed"] is False
            assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
            assert r["requires_operator_approval"] is True

    def test_eag_unavailable_merge_still_blocked(self):
        """merge (operator-required) → BLOCKED_MERGE_WITHOUT_APPROVAL (not Gate 0)."""
        import unittest.mock as mock
        with mock.patch(
            "git_pr_approval_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", False
        ):
            r = check_git_pr_action(
                action="merge",
                target_branch="main",
                operator_approval_id=None,
                operator_approved_actions=[],
            )
            # merge is OPERATOR_REQUIRED, blocked for missing operator approval
            assert r["allowed"] is False
            assert r["verdict"] == "BLOCKED_MERGE_WITHOUT_APPROVAL"

    def test_eag_unavailable_force_push_still_blocked(self):
        """force_push → BLOCKED (force_push is ALWAYS_BLOCKED regardless of EAG)."""
        import unittest.mock as mock
        with mock.patch(
            "git_pr_approval_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", False
        ):
            r = check_git_pr_action(action="force_push")
            assert r["allowed"] is False
            # force_push is always blocked
            assert "blocked" in r["verdict"].lower() or "always" in r["verdict"].lower()

    def test_eag_call_exception_no_operator_approval_still_blocked(self):
        """EAG raises + push_feature_branch + no operator approval → still OPERATOR_APPROVAL_REQUIRED.

        After PR #270 the EAG layer is not invoked for push_feature_branch;
        the operator gate runs first. The mocked exception never reaches
        production code. We verify the action is still operator-required.
        """
        import unittest.mock as mock

        def _raise(*a, **kw):
            raise RuntimeError("EAG crash")

        with mock.patch(
            "git_pr_approval_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "git_pr_approval_gate._eag_check", side_effect=_raise
        ):
            r = check_git_pr_action(
                action="push_feature_branch",
                target_branch="feat-branch",
                source_branch="feat/v12112",
                intake_approved=True,
                execution_approval=_EAG_APPROVAL,
            )
            # baseline01: operator gate returns OPERATOR_APPROVAL_REQUIRED
            # before EAG is consulted. The EAG exception is never reached
            # for this action path.
            assert r["allowed"] is False
            assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
            assert r["requires_operator_approval"] is True

    def test_eag_returns_none_no_operator_approval_still_blocked(self):
        """EAG returns None + push_feature_branch + no operator approval → still OPERATOR_APPROVAL_REQUIRED.

        Same as the exception case: the operator gate runs first; the EAG
        layer is not invoked for OPERATOR_REQUIRED actions.
        """
        import unittest.mock as mock

        with mock.patch(
            "git_pr_approval_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "git_pr_approval_gate._eag_check", return_value=None
        ):
            r = check_git_pr_action(
                action="push_feature_branch",
                target_branch="feat-branch",
                source_branch="feat/v12112",
                intake_approved=True,
                execution_approval=_EAG_APPROVAL,
            )
            assert r["allowed"] is False
            assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
            assert r["requires_operator_approval"] is True


class TestSelfCheck:
    """Self-check validation."""



class TestExceptionCleanBlock:
    """baseline01 (PR #270): EAG exception path is not reachable for operator-required actions.

    Pre-baseline01 this class verified that the EAG layer returns a clean
    BLOCKED_EXECUTION_APPROVAL_GATE_ERROR verdict when it raises, instead of
    propagating the exception or silently allowing. After PR #270 the EAG
    layer is no longer invoked for push_feature_branch / create_draft_pr /
    update_draft_pr — those actions are blocked at the operator gate, which
    runs first. The tests below verify the new contract: even with EAG
    mocked to raise, the action is operator-required and does not propagate
    the exception.
    """

    def test_eag_runtime_error_does_not_propagate(self):
        """T-05: EAG raises RuntimeError + push_feature_branch + no operator approval → OPERATOR_APPROVAL_REQUIRED (no traceback).

        The mocked EAG exception is never reached by the production code
        because the operator gate runs first. No exception propagates to
        the caller and the verdict is the operator gate verdict.
        """
        import unittest.mock as mock
        with mock.patch(
            "git_pr_approval_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "git_pr_approval_gate._eag_check",
            side_effect=RuntimeError("EAG crash"),
        ):
            r = check_git_pr_action(
                action="push_feature_branch",
                target_branch="feat/t",
                source_branch="feat/t",
                checks_passed=True,
                intake_approved=True,
                execution_approval=_EAG_APPROVAL,
                proposal_hash="testhash",
            )
            # baseline01: operator gate runs first; EAG exception never reached
            assert r["allowed"] is False
            assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
            assert r["requires_operator_approval"] is True

    def test_eag_attribute_error_does_not_propagate(self):
        """T-06: EAG raises AttributeError + create_draft_pr + no operator approval → OPERATOR_APPROVAL_REQUIRED (no traceback)."""
        import unittest.mock as mock
        with mock.patch(
            "git_pr_approval_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "git_pr_approval_gate._eag_check",
            side_effect=AttributeError("None.get"),
        ):
            r = check_git_pr_action(
                action="create_draft_pr",
                checks_passed=True,
                intake_approved=True,
                execution_approval=_EAG_APPROVAL,
                proposal_hash="testhash",
            )
            assert r["allowed"] is False
            assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
            assert r["requires_operator_approval"] is True

    def test_eag_returns_none_does_not_propagate(self):
        """T-07: EAG returns None + push_feature_branch + no operator approval → OPERATOR_APPROVAL_REQUIRED (no AttributeError)."""
        import unittest.mock as mock
        with mock.patch(
            "git_pr_approval_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "git_pr_approval_gate._eag_check",
            return_value=None,
        ):
            r = check_git_pr_action(
                action="push_feature_branch",
                target_branch="feat/t",
                source_branch="feat/t",
                checks_passed=True,
                intake_approved=True,
                execution_approval=_EAG_APPROVAL,
                proposal_hash="testhash",
            )
            assert r["allowed"] is False
            assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
            assert r["requires_operator_approval"] is True

    def test_eag_invalid_result_does_not_propagate(self):
        """T-08: EAG returns invalid result + create_draft_pr + no operator approval → OPERATOR_APPROVAL_REQUIRED (no traceback)."""
        import unittest.mock as mock
        with mock.patch(
            "git_pr_approval_gate._EXECUTION_APPROVAL_GATE_AVAILABLE", True
        ), mock.patch(
            "git_pr_approval_gate._eag_check",
            return_value={"verdict": "UNKNOWN", "detail": "bad"},
        ):
            r = check_git_pr_action(
                action="create_draft_pr",
                checks_passed=True,
                intake_approved=True,
                execution_approval=_EAG_APPROVAL,
                proposal_hash="testhash",
            )
            assert r["allowed"] is False
            assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
            assert r["requires_operator_approval"] is True

    def test_normal_path_operator_required(self):
        """T-13: Normal path + valid approval → OPERATOR_APPROVAL_REQUIRED (fail-closed).

        Pre-baseline01 this case resolved to AUTO_ALLOWED_WITH_GATES. After
        PR #270 push_feature_branch is OPERATOR_REQUIRED; no execution approval
        can auto-allow the action. The action is blocked at the operator gate.
        """
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/t",
            source_branch="feat/t",
            checks_passed=True,
            intake_approved=True,
            execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["allowed"] is False
        assert r["verdict"] == "OPERATOR_APPROVAL_REQUIRED"
        assert r["requires_operator_approval"] is True
