"""V1.21.30B — Mode Runtime Enforcement Core tests.

Covers:
- Mode entry detection (Chinese/English triggers)
- Cross-repo grey-use guard (hermes-agent, opencode)
- Casual prompt cannot bypass gates
- Incident regression: exact messages from the 2026-06-24 incident
- PLAN_APPROVAL_REQUEST schema enforcement
- Forbidden actions enforcement
- Per-role model reporting schema existence

Read-only. No real execution, no gate verdict change.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from conversational_intake_gate import (
    MODE_ENTRY_TRIGGERS,
    CROSS_REPO_INDICATORS,
    FORBIDDEN_ACTIONS,
    detect_mode_entry,
    compile_casual_prompt,
    check_cross_repo_guard,
    generate_plan_approval_request,
    _detect_cross_repo,
    _guess_scope,
)


# =============================================================================
# Mode Entry Detection
# =============================================================================


class TestModeEntryDetection:
    """detect_mode_entry must recognize vibe coding mode triggers."""

    def test_chinese_explicit_entry(self):
        """'现在我们要进入vibe coding模式' must trigger MODE_ACTIVE."""
        result = detect_mode_entry("现在我们要进入vibe coding模式")
        assert result["mode_active"] is True
        assert result["verdict"] == "MODE_ACTIVE"
        assert result["next_action"] == "INTAKE_REQUIRED"

    def test_chinese_entry_variant_2(self):
        """'进入 vibe coding 模式' must trigger."""
        result = detect_mode_entry("进入 vibe coding 模式")
        assert result["mode_active"] is True

    def test_chinese_entry_variant_3(self):
        """'启动vibe coding模式' must trigger."""
        result = detect_mode_entry("启动vibe coding模式")
        assert result["mode_active"] is True

    def test_chinese_entry_variant_4(self):
        """'开始vibe coding' must trigger."""
        result = detect_mode_entry("开始vibe coding")
        assert result["mode_active"] is True

    def test_english_entry(self):
        """'enter vibe coding mode' must trigger."""
        result = detect_mode_entry("enter vibe coding mode")
        assert result["mode_active"] is True
        assert result["verdict"] == "MODE_ACTIVE"

    def test_english_start(self):
        """'start vibe coding' must trigger."""
        result = detect_mode_entry("start vibe coding")
        assert result["mode_active"] is True

    def test_english_activate(self):
        """'activate vibe coding' must trigger."""
        result = detect_mode_entry("activate vibe coding")
        assert result["mode_active"] is True

    def test_version_execution_trigger(self):
        """'run V1.21.29' must trigger mode entry."""
        result = detect_mode_entry("run V1.21.29")
        assert result["mode_active"] is True

    def test_no_trigger_casual(self):
        """'你好' must NOT trigger mode entry."""
        result = detect_mode_entry("你好")
        assert result["mode_active"] is False
        assert result["verdict"] == "NOT_MODE_ENTRY"

    def test_no_trigger_question(self):
        """'what is vibe coding?' must NOT trigger mode entry."""
        result = detect_mode_entry("what is vibe coding?")
        assert result["mode_active"] is False

    def test_no_trigger_research(self):
        """'research vibe coding' must NOT trigger mode entry."""
        result = detect_mode_entry("research vibe coding")
        assert result["mode_active"] is False


# =============================================================================
# Cross-Repo Guard
# =============================================================================


class TestCrossRepoGuard:
    """check_cross_repo_guard must detect external repo references."""

    def test_hermes_agent_detected(self):
        """'hermes-agent' in request must trigger cross-repo guard."""
        guard = check_cross_repo_guard("帮我修 hermes-agent 的 PR")
        assert guard["guard_passed"] is False
        assert guard["cross_repo_detected"] is True
        assert guard["cross_repo_target"] == "hermes-agent"
        assert guard["risk_classification"] == "cross_repo_real_grey_use"

    def test_hermes_pr_detected(self):
        """'hermes PR' must trigger cross-repo guard."""
        guard = check_cross_repo_guard("review hermes PR #123")
        assert guard["guard_passed"] is False
        assert guard["cross_repo_detected"] is True

    def test_nousresearch_detected(self):
        """'NousResearch/hermes' must trigger cross-repo guard."""
        guard = check_cross_repo_guard("clone NousResearch/hermes-agent")
        assert guard["guard_passed"] is False
        assert guard["cross_repo_detected"] is True

    def test_opencode_config_detected(self):
        """'opencode config' must trigger cross-repo guard."""
        guard = check_cross_repo_guard("修改 opencode config")
        assert guard["guard_passed"] is False
        assert guard["cross_repo_detected"] is True

    def test_local_repo_safe(self):
        """Local repo requests must pass guard."""
        guard = check_cross_repo_guard("实现 vibe_cluster_text 的新功能")
        assert guard["guard_passed"] is True
        assert guard["cross_repo_detected"] is False
        assert guard["risk_classification"] == "local_safe"

    def test_operator_action_blocked_for_hermes(self):
        """Hermes cross-repo must require APPROVE_REAL_EXEC."""
        guard = check_cross_repo_guard("hermes PR conflict")
        assert "BLOCK" in guard["operator_action_needed"]
        assert "APPROVE_REAL_EXEC" in guard["operator_action_needed"]


# =============================================================================
# Casual Prompt Cannot Bypass Gates
# =============================================================================


class TestCasualPromptCannotBypass:
    """Casual/voice prompts must still go through PLAN_APPROVAL_REQUEST."""

    def test_direct_fix_merge_must_gate(self):
        """'直接修完 merge' must have gate_required=True."""
        compiled = compile_casual_prompt("直接修完 merge")
        assert compiled["gate_required"] is True
        assert compiled["forbidden_actions"]  # non-empty

    def test_just_do_it_must_gate(self):
        """'你就直接做吧' must have gate_required=True."""
        compiled = compile_casual_prompt("你就直接做吧")
        assert compiled["gate_required"] is True

    def test_quick_fix_must_gate(self):
        """'quick fix' must have gate_required=True."""
        compiled = compile_casual_prompt("quick fix this bug")
        assert compiled["gate_required"] is True

    def test_voice_transcription_must_gate(self):
        """Voice transcription (informal Chinese) must gate."""
        compiled = compile_casual_prompt("帮我把那个斜杠命令搞一下")
        assert compiled["gate_required"] is True

    def test_urgent_bypass_attempt_must_gate(self):
        """'紧急！直接修直接merge' must still gate."""
        compiled = compile_casual_prompt("紧急！直接修直接merge")
        assert compiled["gate_required"] is True


# =============================================================================
# Incident Regression: 2026-06-24 Exact Messages
# =============================================================================


class TestIncidentRegression:
    """Reproduce the exact messages from the incident.

    The agent MUST detect mode entry and produce PLAN_APPROVAL_REQUEST.
    It MUST NOT proceed to research/clone/install/write directly.
    """

    # Message T1: User enters vibe coding mode
    INCIDENT_T1 = "现在我们要进入vibe coding模式"

    # Message T2: User asks about QQBot slash commands
    INCIDENT_T2 = "他那个斜杠QQ-BOT命令是不是不行的"

    # Message T3: User says continue research
    INCIDENT_T3 = "继续深入调研具体实现方案"

    # Message T4: User approves plan A
    INCIDENT_T4 = "方案A是可以的，提出你的详细计划"

    # Message T5: User specifies nodes/models
    INCIDENT_T5 = "执行者的话，用5宝这个节点，然后模型使用m Pro这个模型"

    def test_t1_must_detect_mode_entry(self):
        """T1: '进入vibe coding模式' must trigger MODE_ACTIVE."""
        result = detect_mode_entry(self.INCIDENT_T1)
        assert result["mode_active"] is True
        assert result["verdict"] == "MODE_ACTIVE"
        assert result["next_action"] == "INTAKE_REQUIRED"

    def test_t2_casual_prompt_must_gate(self):
        """T2: Casual question about QQBot must require gate."""
        compiled = compile_casual_prompt(self.INCIDENT_T2)
        assert compiled["gate_required"] is True

    def test_t3_research_must_not_bypass(self):
        """T3: '继续深入调研' must not bypass gate."""
        compiled = compile_casual_prompt(self.INCIDENT_T3)
        assert compiled["gate_required"] is True

    def test_t4_approval_must_be_structured(self):
        """T4: '方案A是可以的' must produce structured approval."""
        compiled = compile_casual_prompt(self.INCIDENT_T4)
        assert compiled["gate_required"] is True

    def test_t5_model_spec_must_gate(self):
        """T5: Model specification must still require gate."""
        compiled = compile_casual_prompt(self.INCIDENT_T5)
        assert compiled["gate_required"] is True

    def test_plan_approval_request_schema(self):
        """PLAN_APPROVAL_REQUEST must have all required fields."""
        compiled = compile_casual_prompt(self.INCIDENT_T1)
        par = generate_plan_approval_request(
            phase_id="V1.21.30B",
            approval_id="test-001",
            compiled_prompt=compiled,
        )
        required_fields = [
            "phase_id", "approval_id", "request_type", "goal",
            "risk_classification", "cross_repo_detected", "scope",
            "forbidden_actions", "role_model_matrix_required",
            "operator_action_needed", "next_step",
        ]
        for field in required_fields:
            assert field in par, f"Missing required field: {field}"
        assert par["request_type"] == "PLAN_APPROVAL_REQUEST"
        assert par["role_model_matrix_required"] is True


# =============================================================================
# Report Schema Enforcement
# =============================================================================


class TestReportSchemaEnforcement:
    """PLAN_APPROVAL_REQUEST must contain all required fields."""

    def test_local_request_schema(self):
        """Local request must have full schema."""
        compiled = compile_casual_prompt("实现一个新功能")
        par = generate_plan_approval_request(
            phase_id="V1.21.30B",
            approval_id="test-local-001",
            compiled_prompt=compiled,
        )
        assert par["request_type"] == "PLAN_APPROVAL_REQUEST"
        assert par["role_model_matrix_required"] is True
        assert "APPROVE_PLAN" in par["operator_action_needed"]

    def test_cross_repo_request_schema(self):
        """Cross-repo request must flag risk correctly."""
        compiled = compile_casual_prompt("修 hermes PR conflict")
        par = generate_plan_approval_request(
            phase_id="V1.21.30B",
            approval_id="test-cross-001",
            compiled_prompt=compiled,
        )
        assert par["risk_classification"] == "cross_repo_real_grey_use"
        assert par["cross_repo_detected"] is True
        assert par["cross_repo_target"] == "hermes-agent"
        assert "BLOCK" in par["operator_action_needed"]

    def test_role_model_matrix_fields_mentioned(self):
        """next_step must mention role/model matrix fields."""
        compiled = compile_casual_prompt("实现功能")
        par = generate_plan_approval_request(
            phase_id="V1.21.30B",
            approval_id="test-001",
            compiled_prompt=compiled,
        )
        next_step = par["next_step"].lower()
        for keyword in ["role", "node", "model", "scope", "cost_tag", "call_budget", "fallback"]:
            assert keyword in next_step, f"next_step missing keyword: {keyword}"


# =============================================================================
# Forbidden Actions
# =============================================================================


class TestForbiddenActions:
    """Forbidden actions must be in every compiled prompt."""

    def test_forbidden_actions_non_empty(self):
        """FORBIDDEN_ACTIONS set must be non-empty."""
        assert len(FORBIDDEN_ACTIONS) > 0

    def test_forbidden_includes_debug_raw(self):
        """Must forbid debug_config_raw_output."""
        assert "debug_config_raw_output" in FORBIDDEN_ACTIONS

    def test_forbidden_includes_key_output(self):
        """Must forbid output_key_value."""
        assert "output_key_value" in FORBIDDEN_ACTIONS

    def test_forbidden_includes_malicious_cleanup(self):
        """Must forbid cleaning malicious_payload_evidence.json."""
        assert "clean_malicious_payload_evidence" in FORBIDDEN_ACTIONS
        assert "commit_malicious_payload_evidence" in FORBIDDEN_ACTIONS

    def test_forbidden_includes_pilot_cleanup(self):
        """Must forbid cleaning pilot-prompts/."""
        assert "clean_pilot_prompts" in FORBIDDEN_ACTIONS
        assert "commit_pilot_prompts" in FORBIDDEN_ACTIONS

    def test_compiled_prompt_includes_forbidden(self):
        """Every compiled prompt must include forbidden_actions."""
        compiled = compile_casual_prompt("随便做什么")
        for action in FORBIDDEN_ACTIONS:
            assert action in compiled["forbidden_actions"]


# =============================================================================
# Scope Guessing
# =============================================================================


class TestScopeGuessing:
    """_guess_scope must detect relevant areas."""

    def test_slash_command_scope(self):
        """QQBot slash commands must be detected."""
        scopes = _guess_scope("实现斜杠命令 bot-ping")
        assert "qqbot-slash-commands" in scopes

    def test_git_workflow_scope(self):
        """PR/merge must be detected."""
        scopes = _guess_scope("创建 PR 合并分支")
        assert "git-workflow" in scopes

    def test_testing_scope(self):
        """Test-related must be detected."""
        scopes = _guess_scope("写测试 verify 代码")
        assert "testing" in scopes

    def test_default_scope(self):
        """Unrecognized must default to 'general'."""
        scopes = _guess_scope("随便聊聊")
        assert "general" in scopes


# =============================================================================
# CLI Integration
# =============================================================================


class TestCLIIntegration:
    """CLI subcommands must work correctly."""

    def test_detect_mode_cli(self):
        """detect-mode CLI must return mode_active=True for entry trigger."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/conversational_intake_gate.py",
             "--json", "detect-mode", "--text", "进入vibe coding模式"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        assert result.returncode == 0
        import json
        data = json.loads(result.stdout)
        assert data["mode_active"] is True
        assert data["verdict"] == "MODE_ACTIVE"

    def test_compile_prompt_cli(self):
        """compile-prompt CLI must return gate_required=True."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/conversational_intake_gate.py",
             "--json", "compile-prompt", "--text", "直接修完merge"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        assert result.returncode == 0
        import json
        data = json.loads(result.stdout)
        assert data["gate_required"] is True

    def test_plan_approval_request_cli(self):
        """plan-approval-request CLI must produce full schema."""
        import subprocess
        result = subprocess.run(
            [sys.executable, "scripts/conversational_intake_gate.py",
             "--json", "plan-approval-request",
             "--text", "进入vibe coding模式，修 hermes PR",
             "--phase-id", "V1.21.30B"],
            capture_output=True, text=True,
            cwd=os.path.join(os.path.dirname(__file__), ".."),
        )
        assert result.returncode == 0
        import json
        data = json.loads(result.stdout)
        assert data["request_type"] == "PLAN_APPROVAL_REQUEST"
        assert data["cross_repo_detected"] is True
        assert data["risk_classification"] == "cross_repo_real_grey_use"
        assert "BLOCK" in data["operator_action_needed"]
