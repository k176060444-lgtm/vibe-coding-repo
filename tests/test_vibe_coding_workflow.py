#!/usr/bin/env python3
"""V1.21.28A — Vibe Coding Workflow Alignment tests.

Covers:
- Intake gate detects typical Vibe Coding opening phrases
- Intake gate exempts pure informational / read-only requests
- Intake record structure includes workflow alignment fields
- Workflow contract doc exists and is valid
- PR policy: default Draft, no auto-Ready

Read-only. No real execution, no gate verdict change.
"""
import sys
from pathlib import Path

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ── Intake gate: Vibe Coding entry detection ────────────────────────────────

class TestVibeCodingEntryDetection:
    """Intake gate must detect typical Vibe Coding opening phrases."""

    def test_enter_vibe_coding_mode(self):
        """'进入 vibe coding 模式' → intake required."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("进入 vibe coding 模式")
        assert result["intake_required"] is True

    def test_continue_vibe_coding_project(self):
        """'继续 Vibe Coding 项目' → intake required."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("继续 Vibe Coding 项目")
        assert result["intake_required"] is True

    def test_continue_cluster(self):
        """'继续小集群' → intake required."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("继续小集群")
        assert result["intake_required"] is True

    def test_start_version_execution(self):
        """'开始 V1.21.28 执行' → intake required."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("开始 V1.21.28 执行")
        assert result["intake_required"] is True

    def test_fix_bug(self):
        """'帮我修复这个 bug' → intake required."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("帮我修复这个 bug")
        assert result["intake_required"] is True

    def test_implement_feature(self):
        """'实现这个功能' → intake required."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("实现这个功能")
        assert result["intake_required"] is True

    def test_review_pr(self):
        """'审查这个 PR' → intake required."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("审查这个 PR")
        assert result["intake_required"] is True

    def test_implement_create_build(self):
        """'implement/create/add/build' keywords → intake required."""
        from conversational_intake_gate import detect_intake_required
        for keyword in ["implement", "create", "add", "build"]:
            result = detect_intake_required(f"Please {keyword} a new feature")
            assert result["intake_required"] is True, f"Failed for keyword: {keyword}"


# ── Intake gate: informational exemption ─────────────────────────────────────

class TestInformationalExemption:
    """Intake gate must NOT require intake for pure informational requests."""

    def test_what_is_vibe_coding(self):
        """'什么是 Vibe Coding' → no intake."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("什么是 Vibe Coding")
        assert result["intake_required"] is False

    def test_tell_me_status(self):
        """'告诉我当前状态' → no intake."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("告诉我当前状态")
        assert result["intake_required"] is False

    def test_explain_function(self):
        """'解释一下这个函数' → no intake."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("解释一下这个函数")
        assert result["intake_required"] is False

    def test_what_is_english(self):
        """'what is Vibe Coding' → no intake (English)."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("what is Vibe Coding")
        assert result["intake_required"] is False

    def test_show_status(self):
        """'show status' → no intake."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("show status")
        assert result["intake_required"] is False

    def test_research(self):
        """'research this topic' → no intake."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("research this topic")
        assert result["intake_required"] is False

    def test_diaoyan(self):
        """'调研一下' → no intake."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("调研一下")
        assert result["intake_required"] is False

    def test_help_me_look_at_file(self):
        """'帮我看看这个文件' → no intake (no coding signal)."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("帮我看看这个文件")
        assert result["intake_required"] is False

    def test_help_me_look_at_concept(self):
        """'帮我看看这个概念是什么意思' → no intake (informational)."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("帮我看看这个概念是什么意思")
        assert result["intake_required"] is False


# ── V1.21.28A Correction: coding signal must NOT be exempted ────────────

class TestCodingSignalNotExempted:
    """Coding/workflow signals must trigger intake even with '帮我' prefix.

    This corrects the overly broad NO_INTAKE_PATTERNS from initial V1.21.28A
    that exempted '帮我(看看|查看|检查|看下|查下)' globally.
    """

    def test_check_pr_requires_intake(self):
        """'帮我检查这个 PR' → intake required (PR = coding signal)."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("帮我检查这个 PR")
        assert result["intake_required"] is True

    def test_check_code_requires_intake(self):
        """'帮我检查这段代码' → intake required (代码 = coding keyword)."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("帮我检查这段代码")
        assert result["intake_required"] is True

    def test_look_at_bug_requires_intake(self):
        """'帮我看看这个 bug' → intake required (bug = coding signal)."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("帮我看看这个 bug")
        assert result["intake_required"] is True

    def test_check_repo_test_failure(self):
        """'帮我查看这个仓库为什么测试失败' → intake required (仓库+测试)."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("帮我查看这个仓库为什么测试失败")
        assert result["intake_required"] is True

    def test_check_branch_merge(self):
        """'帮我查下这个分支能不能 merge' → intake required (分支+merge)."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("帮我查下这个分支能不能 merge")
        assert result["intake_required"] is True

    def test_look_at_test_file(self):
        """'帮我看下 tests/test_vibe_coding_workflow.py' → intake required (test file)."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("帮我看下 tests/test_vibe_coding_workflow.py")
        assert result["intake_required"] is True

    def test_check_code_requires_intake_cn(self):
        """'帮我检查一下代码' → intake required (代码 = coding keyword)."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("帮我检查一下代码")
        assert result["intake_required"] is True

    def test_what_is_vibe_coding_no_intake(self):
        """'什么是 Vibe Coding' → no intake (informational)."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("什么是 Vibe Coding")
        assert result["intake_required"] is False

    def test_explain_intake_meaning(self):
        """'解释一下 intake 是什么意思' → no intake (是什么意思 override)."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("解释一下 intake 是什么意思")
        assert result["intake_required"] is False

    def test_look_at_concept_meaning(self):
        """'帮我看看这个概念是什么意思' → no intake (是什么意思 override)."""
        from conversational_intake_gate import detect_intake_required
        result = detect_intake_required("帮我看看这个概念是什么意思")
        assert result["intake_required"] is False


# ── Intake record structure ─────────────────────────────────────────────────

class TestIntakeRecordStructure:
    """Intake record must include workflow alignment fields."""

    def test_record_has_alignment_fields(self):
        """Intake record has all workflow alignment fields."""
        from conversational_intake_gate import create_intake_record
        record = create_intake_record("test request")
        # Workflow alignment fields
        assert "proposed_plan" in record
        assert "role_assignment_required" in record
        assert "model_selection_required" in record
        assert "operator_approval_required" in record
        assert "blocked_actions_before_approval" in record
        assert "role_model_matrix" in record
        assert "approval" in record

    def test_role_model_matrix_initially_none(self):
        """role_model_matrix is None until explicitly set."""
        from conversational_intake_gate import create_intake_record
        record = create_intake_record("test request")
        assert record["role_model_matrix"] is None

    def test_approval_initially_none(self):
        """approval is None until operator approves."""
        from conversational_intake_gate import create_intake_record
        record = create_intake_record("test request")
        assert record["approval"] is None

    def test_role_assignment_required_default_true(self):
        """role_assignment_required defaults to True."""
        from conversational_intake_gate import create_intake_record
        record = create_intake_record("test request")
        assert record["role_assignment_required"] is True

    def test_model_selection_required_default_true(self):
        """model_selection_required defaults to True."""
        from conversational_intake_gate import create_intake_record
        record = create_intake_record("test request")
        assert record["model_selection_required"] is True

    def test_proposed_plan_default_empty(self):
        """proposed_plan defaults to empty list."""
        from conversational_intake_gate import create_intake_record
        record = create_intake_record("test request")
        assert record["proposed_plan"] == []

    def test_blocked_actions_is_list(self):
        """blocked_actions_before_approval is a list."""
        from conversational_intake_gate import create_intake_record
        record = create_intake_record("test request")
        assert isinstance(record["blocked_actions_before_approval"], list)


# ── Workflow contract doc ───────────────────────────────────────────────────

class TestWorkflowContractDoc:
    """Workflow contract doc must exist and contain key sections."""

    def test_contract_doc_exists(self):
        """VIBE_CODING_WORKFLOW_CONTRACT.md exists."""
        contract_path = Path(__file__).parent.parent / "docs" / "VIBE_CODING_WORKFLOW_CONTRACT.md"
        assert contract_path.is_file(), "VIBE_CODING_WORKFLOW_CONTRACT.md not found"

    def test_contract_has_step_0(self):
        """Contract defines Step 0: Enter Vibe Coding Role."""
        contract_path = Path(__file__).parent.parent / "docs" / "VIBE_CODING_WORKFLOW_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert "Step 0" in content
        assert "Enter" in content or "进入" in content

    def test_contract_has_step_1(self):
        """Contract defines Step 1: Requirement Alignment."""
        contract_path = Path(__file__).parent.parent / "docs" / "VIBE_CODING_WORKFLOW_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert "Step 1" in content
        assert "Requirement" in content or "需求" in content

    def test_contract_has_step_2(self):
        """Contract defines Step 2: Technical Plan + Model Pool."""
        contract_path = Path(__file__).parent.parent / "docs" / "VIBE_CODING_WORKFLOW_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert "Step 2" in content
        assert "Model Pool" in content or "模型池" in content

    def test_contract_has_draft_pr_rule(self):
        """Contract states PR defaults to Draft."""
        contract_path = Path(__file__).parent.parent / "docs" / "VIBE_CODING_WORKFLOW_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert "Draft" in content
        assert "默认" in content or "default" in content.lower()

    def test_contract_has_no_auto_ready(self):
        """Contract forbids automatic Ready."""
        contract_path = Path(__file__).parent.parent / "docs" / "VIBE_CODING_WORKFLOW_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert "Ready" in content
        assert "FORBIDDEN" in content or "禁止" in content or "严禁" in content

    def test_contract_has_model_pool_table(self):
        """Contract contains model pool table with providers."""
        contract_path = Path(__file__).parent.parent / "docs" / "VIBE_CODING_WORKFLOW_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert "deepseek" in content.lower()
        assert "xiaomi" in content.lower() or "mimo" in content.lower()
        assert "volcengine" in content.lower() or "ark" in content.lower()

    def test_contract_has_role_matrix(self):
        """Contract defines role assignment matrix."""
        contract_path = Path(__file__).parent.parent / "docs" / "VIBE_CODING_WORKFLOW_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert "Orchestrator" in content or "Planner" in content
        assert "Implementer" in content
        assert "Reviewer" in content

    def test_contract_has_approval_record(self):
        """Contract defines approval record structure."""
        contract_path = Path(__file__).parent.parent / "docs" / "VIBE_CODING_WORKFLOW_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        assert "approval_id" in content or "approval record" in content.lower()


# ── PR policy ───────────────────────────────────────────────────────────────

class TestPrPolicy:
    """PR policy: default Draft, no auto-Ready."""

    def test_contract_forbids_auto_ready(self):
        """Workflow contract explicitly forbids auto-Ready."""
        contract_path = Path(__file__).parent.parent / "docs" / "VIBE_CODING_WORKFLOW_CONTRACT.md"
        content = contract_path.read_text(encoding="utf-8")
        # Must state that auto-Ready is forbidden
        assert any(phrase in content for phrase in [
            "自动 Ready", "auto-Ready", "Automatic Ready", "自动Ready",
            "FORBIDDEN", "严禁", "禁止"
        ])


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
