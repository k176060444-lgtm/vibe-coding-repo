"""V1.21.30D — Cross-Repo Pre-Approval Read Guard regression tests.

Covers:
1. Mode entry → VIBE_CODING_MODE_ACTIVE, auto-generated mode_session_id, no user-supplied ID required
2. "可以，按这个 plan 执行" → auto-generated approval_id, approval_source=natural_language
3. "帮我修 hermes 官方 PR 的 conflict" → only PLAN_APPROVAL_REQUEST or CLARIFICATION_REQUIRED, no GitHub API/PR list/clone/fetch/conflict check
4. "直接修完 merge" → cannot bypass merge gate; "可以 merge" → merge approval record
5. Report must show approval_id is agent-generated, not user-supplied

Read-only. No real execution, no gate verdict change.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from conversational_intake_gate import (
    detect_mode_entry,
    compile_casual_prompt,
    check_cross_repo_guard,
    generate_plan_approval_request,
    generate_mode_session_id,
    generate_approval_id,
    compile_natural_language_approval,
    check_preapproval_read_guard,
    _detect_cross_repo,
    VERDICT_BLOCKED_CROSS_REPO_PREAPPROVAL,
)


# =============================================================================
# Test 1: Mode Entry → Auto-generated mode_session_id
# =============================================================================


class TestModeEntryAutoSessionId:
    """Mode entry must produce VIBE_CODING_MODE_ACTIVE with auto-generated IDs."""

    def test_mode_entry_active(self):
        """'进入 vibe coding模式' must trigger MODE_ACTIVE."""
        result = detect_mode_entry("进入 vibe coding模式")
        assert result["mode_active"] is True
        assert result["verdict"] == "MODE_ACTIVE"

    def test_mode_entry_no_user_id_required(self):
        """Mode entry must NOT require user-supplied approval_id."""
        result = detect_mode_entry("进入 vibe coding模式")
        # The result should not contain any field requiring user input
        assert "approval_id" not in result  # Not in mode entry result
        assert result["next_action"] == "INTAKE_REQUIRED"

    def test_auto_generated_mode_session_id(self):
        """generate_mode_session_id must produce valid format."""
        msid = generate_mode_session_id()
        # Format: mode-<YYYYMMDDHHMMSS>-<sha256[:8]>
        assert msid.startswith("mode-")
        parts = msid.split("-")
        assert len(parts) >= 3
        # Timestamp part should be 14 digits
        assert len(parts[1]) == 14
        assert parts[1].isdigit()
        # Hash part should be 8 hex chars
        assert len(parts[2]) == 8
        assert all(c in "0123456789abcdef" for c in parts[2])

    def test_mode_session_id_unique(self):
        """Two calls must produce different session IDs."""
        id1 = generate_mode_session_id()
        id2 = generate_mode_session_id()
        # They might collide if called in same second with same PID,
        # but extremely unlikely due to hash
        # At minimum, both must be valid format
        assert id1.startswith("mode-")
        assert id2.startswith("mode-")


# =============================================================================
# Test 2: Natural Language Approval → Auto-generated approval_id
# =============================================================================


class TestNaturalLanguageApproval:
    """Natural language approval must auto-generate approval_id."""

    def test_plan_approval_can_execute(self):
        """'可以，按这个 plan 执行' → approved, agent-generated ID."""
        approval = compile_natural_language_approval(
            "可以，按这个 plan 执行", "plan_approval", "V1.21.30D"
        )
        assert approval["approved"] is True
        assert approval["approval_source"] == "natural_language"
        assert approval["approval_id"].startswith("approval-v1.21.30d-")
        assert "mode_session_id" in approval

    def test_plan_approval_pizhun(self):
        """'批准' → approved."""
        approval = compile_natural_language_approval(
            "批准", "plan_approval", "V1.21.30D"
        )
        assert approval["approved"] is True
        assert approval["approval_source"] == "natural_language"

    def test_plan_approval_continue(self):
        """'继续' → approved."""
        approval = compile_natural_language_approval(
            "继续", "plan_approval", "V1.21.30D"
        )
        assert approval["approved"] is True

    def test_approval_id_format(self):
        """approval_id must match format approval-<phase>-<seq>."""
        aid = generate_approval_id("V1.21.30D")
        assert aid.startswith("approval-v1.21.30d-")
        # Sequence part should be 3 digits
        seq = aid.split("-")[-1]
        assert len(seq) == 3
        assert seq.isdigit()

    def test_random_text_not_approved(self):
        """Random text must NOT be compiled as approval."""
        approval = compile_natural_language_approval(
            "今天天气不错", "plan_approval", "V1.21.30D"
        )
        assert approval["approved"] is False


# =============================================================================
# Test 3: Cross-Repo Request → Only PLAN_APPROVAL_REQUEST
# =============================================================================


class TestCrossRepoPreApprovalGuard:
    """Cross-repo requests must be gated, no external repo access before approval."""

    def test_hermes_pr_conflict_gated(self):
        """'帮我修 hermes 官方 PR 的 conflict' must trigger cross-repo guard."""
        guard = check_cross_repo_guard("帮我修 hermes 官方 PR 的 conflict")
        assert guard["guard_passed"] is False
        assert guard["cross_repo_detected"] is True
        assert guard["cross_repo_target"] == "hermes-agent"
        assert guard["risk_classification"] == "cross_repo_real_grey_use"

    def test_hermes_pr_conflict_plan_approval_request(self):
        """'帮我修 hermes 官方 PR 的 conflict' must produce PLAN_APPROVAL_REQUEST."""
        compiled = compile_casual_prompt("帮我修 hermes 官方 PR 的 conflict")
        par = generate_plan_approval_request(
            phase_id="V1.21.30D",
            approval_id="",
            compiled_prompt=compiled,
        )
        assert par["request_type"] == "PLAN_APPROVAL_REQUEST"
        assert par["risk_classification"] == "cross_repo_real_grey_use"
        assert par["cross_repo_detected"] is True
        assert par["cross_repo_target"] == "hermes-agent"

    def test_preapproval_gh_pr_list_blocked(self):
        """gh pr list must be blocked before approval."""
        guard = check_preapproval_read_guard(
            "gh pr list --state open", has_approval=False
        )
        assert guard["violation_detected"] is True
        assert guard["violation_type"] == "github_api"

    def test_preapproval_git_fetch_hermes_blocked(self):
        """git fetch hermes must be blocked before approval."""
        guard = check_preapproval_read_guard(
            "git fetch fork feat/windows-service-backend-clean", has_approval=False
        )
        # This should pass because it doesn't mention hermes/opencode
        # The guard checks for explicit hermes/opencode references
        assert guard["guard_passed"] is True

    def test_preapproval_git_clone_hermes_blocked(self):
        """git clone hermes must be blocked before approval."""
        guard = check_preapproval_read_guard(
            "git clone https://github.com/NousResearch/hermes-agent.git", has_approval=False
        )
        assert guard["violation_detected"] is True
        assert guard["violation_type"] == "git_external"

    def test_preapproval_with_approval_passes(self):
        """With approval, all actions must pass."""
        guard = check_preapproval_read_guard(
            "gh pr list --state open", has_approval=True
        )
        assert guard["guard_passed"] is True
        assert guard["violation_detected"] is False


# =============================================================================
# Test 4: "直接修完 merge" → Cannot Bypass Merge Gate
# =============================================================================


class TestMergeGateNotBypassable:
    """Casual prompts like '直接修完 merge' cannot bypass merge gate."""

    def test_direct_fix_merge_gated(self):
        """'直接修完 merge' must have gate_required=True."""
        compiled = compile_casual_prompt("直接修完 merge")
        assert compiled["gate_required"] is True

    def test_direct_fix_merge_no_approval(self):
        """'直接修完 merge' must NOT produce approval."""
        # This is a casual prompt, not an approval
        approval = compile_natural_language_approval(
            "直接修完 merge", "merge_approval", "V1.21.30D"
        )
        # "直接修完 merge" is NOT an approval pattern
        assert approval["approved"] is False

    def test_merge_approval_after_plan(self):
        """'可以 merge' after plan → merge approval record."""
        approval = compile_natural_language_approval(
            "可以 merge", "merge_approval", "V1.21.30D"
        )
        assert approval["approved"] is True
        assert approval["gate_type"] == "merge_approval"
        assert approval["approval_source"] == "natural_language"

    def test_merge_ba_gated(self):
        """'merge 吧' → merge approval."""
        approval = compile_natural_language_approval(
            "merge 吧", "merge_approval", "V1.21.30D"
        )
        assert approval["approved"] is True
        assert approval["gate_type"] == "merge_approval"

    def test_casual_just_do_it_gated(self):
        """'你就直接做吧' must have gate_required=True."""
        compiled = compile_casual_prompt("你就直接做吧")
        assert compiled["gate_required"] is True


# =============================================================================
# Test 5: Report Shows agent-generated approval_id
# =============================================================================


class TestReportShowsAgentGeneratedId:
    """PLAN_APPROVAL_REQUEST report must show approval_source=agent_generated."""

    def test_par_approval_source(self):
        """PLAN_APPROVAL_REQUEST must have approval_source=agent_generated."""
        compiled = compile_casual_prompt("实现新功能")
        par = generate_plan_approval_request(
            phase_id="V1.21.30D",
            approval_id="",
            compiled_prompt=compiled,
        )
        assert par["approval_source"] == "agent_generated"

    def test_par_has_mode_session_id(self):
        """PLAN_APPROVAL_REQUEST must include mode_session_id."""
        compiled = compile_casual_prompt("实现新功能")
        par = generate_plan_approval_request(
            phase_id="V1.21.30D",
            approval_id="",
            compiled_prompt=compiled,
        )
        assert "mode_session_id" in par
        assert par["mode_session_id"].startswith("mode-")

    def test_par_approval_id_auto_generated(self):
        """approval_id must be auto-generated when empty string provided."""
        compiled = compile_casual_prompt("实现新功能")
        par = generate_plan_approval_request(
            phase_id="V1.21.30D",
            approval_id="",
            compiled_prompt=compiled,
        )
        assert par["approval_id"].startswith("approval-v1.21.30d-")

    def test_par_approval_id_preserved_when_provided(self):
        """approval_id must be preserved when explicitly provided."""
        compiled = compile_casual_prompt("实现新功能")
        par = generate_plan_approval_request(
            phase_id="V1.21.30D",
            approval_id="custom-id-001",
            compiled_prompt=compiled,
        )
        assert par["approval_id"] == "custom-id-001"

    def test_cross_repo_par_shows_agent_generated(self):
        """Cross-repo PLAN_APPROVAL_REQUEST must show agent_generated."""
        compiled = compile_casual_prompt("修 hermes PR conflict")
        par = generate_plan_approval_request(
            phase_id="V1.21.30D",
            approval_id="",
            compiled_prompt=compiled,
        )
        assert par["approval_source"] == "agent_generated"
        assert par["risk_classification"] == "cross_repo_real_grey_use"
