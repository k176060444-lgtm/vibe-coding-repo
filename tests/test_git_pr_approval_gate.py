#!/usr/bin/env python3
"""Tests for Git/PR State Approval Gate v1.1.0 (V1.21.12)."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from git_pr_approval_gate import (
    ALL_ACTIONS,
    ALWAYS_BLOCKED_ACTIONS,
    AUTO_ALLOWED_ACTIONS,
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


class TestAutoAllowedPushFeature:
    """AUTO_ALLOWED_WITH_GATES: push feature branch."""

    def test_push_feature_gates_passed(self):
        """Push feature branch + all gates passed → AUTO_ALLOWED_WITH_GATES."""
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            source_branch="feat/test",
            checks_passed=True,
            intake_approved=True,
            execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "AUTO_ALLOWED_WITH_GATES"
        assert r["allowed"] is True
        assert "push_feature_branch" in r["safe_auto_actions"]

    def test_push_feature_intake_not_approved(self):
        """Push feature without intake → BLOCKED."""
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            checks_passed=True,
            intake_approved=False,
            execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "BLOCKED_UNAPPROVED_GIT_ACTION"
        assert r["allowed"] is False

    def test_push_feature_checks_not_passed(self):
        """Push feature without checks → BLOCKED."""
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            checks_passed=False,
            intake_approved=True,
            execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "BLOCKED_UNAPPROVED_GIT_ACTION"
        assert r["allowed"] is False

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


class TestAutoAllowedDraftPR:
    """AUTO_ALLOWED_WITH_GATES: create/update Draft PR."""

    def test_create_draft_pr_gates_passed(self):
        """Create Draft PR + all gates passed → AUTO_ALLOWED_WITH_GATES."""
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
        assert r["verdict"] == "AUTO_ALLOWED_WITH_GATES"
        assert r["allowed"] is True

    def test_update_draft_pr_gates_passed(self):
        """Update Draft PR + all gates passed → AUTO_ALLOWED_WITH_GATES."""
        r = check_git_pr_action(
            action="update_draft_pr",
            target_branch="main",
            desired_pr_state="DRAFT",
            checks_passed=True,
            intake_approved=True,
                    execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "AUTO_ALLOWED_WITH_GATES"
        assert r["allowed"] is True

    def test_create_draft_with_open_state_blocked(self):
        """Create Draft PR with desired state OPEN → BLOCKED."""
        r = check_git_pr_action(
            action="create_draft_pr",
            target_branch="main",
            desired_pr_state="OPEN",
            checks_passed=True,
            intake_approved=True,
                    execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "BLOCKED_READY_WITHOUT_APPROVAL"
        assert r["allowed"] is False


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

    def test_no_high_risk_files(self):
        """No high-risk files → AUTO_ALLOWED."""
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
        assert r["verdict"] == "AUTO_ALLOWED_WITH_GATES"
        assert r["allowed"] is True


class TestIntakeIntegration:
    """V1.21.6 intake approval integration."""

    def test_no_intake_blocked(self):
        """Git action without intake approval → BLOCKED."""
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            checks_passed=True,
            intake_approved=False,
                    execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "BLOCKED_UNAPPROVED_GIT_ACTION"
        assert r["blocked_reason"] is not None
        assert "intake" in r["blocked_reason"].lower()

    def test_with_intake_allowed(self):
        """Git action with intake approval + checks → AUTO_ALLOWED."""
        r = check_git_pr_action(
            action="push_feature_branch",
            target_branch="feat/test",
            checks_passed=True,
            intake_approved=True,
                    execution_approval=_EAG_APPROVAL,
            proposal_hash="testhash",
        )
        assert r["verdict"] == "AUTO_ALLOWED_WITH_GATES"


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
    """Policy constant validation."""

    def test_verdicts_count(self):
        assert len(VERDICTS) == 10

    def test_auto_allowed_count(self):
        assert len(AUTO_ALLOWED_ACTIONS) == 3

    def test_operator_required_count(self):
        assert len(OPERATOR_REQUIRED_ACTIONS) == 12

    def test_always_blocked_count(self):
        assert len(ALWAYS_BLOCKED_ACTIONS) == 1

    def test_protected_branches_count(self):
        assert len(PROTECTED_BRANCHES) == 5
        assert "main" in PROTECTED_BRANCHES
        assert "production" in PROTECTED_BRANCHES

    def test_all_actions_union(self):
        """ALL_ACTIONS is the union of all categories."""
        assert ALL_ACTIONS == AUTO_ALLOWED_ACTIONS | OPERATOR_REQUIRED_ACTIONS | ALWAYS_BLOCKED_ACTIONS


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


class TestSelfCheck:
    """Self-check validation."""

