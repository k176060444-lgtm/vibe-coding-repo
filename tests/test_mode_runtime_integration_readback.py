"""V1.21.30B — Runtime Integration Readback tests.

Verifies that:
1. VIBE_CODING_MODE_CONTRACT.md references runtime integration
2. VIBE_CODING_MODE_RUNTIME_INTEGRATION.md exists and is valid
3. Integration points are documented with correct function signatures
4. CLI integration works end-to-end
5. Agent workflow cannot bypass mode entry detection

Read-only. No real execution.
"""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")
CONTRACT_PATH = os.path.join(REPO_ROOT, "docs", "VIBE_CODING_MODE_CONTRACT.md")
INTEGRATION_PATH = os.path.join(REPO_ROOT, "docs", "VIBE_CODING_MODE_RUNTIME_INTEGRATION.md")


# =============================================================================
# Contract Integration
# =============================================================================


class TestContractIntegration:
    """VIBE_CODING_MODE_CONTRACT.md must reference runtime integration."""

    def test_contract_has_runtime_enforcement_section(self):
        """Contract must have §10 Runtime Enforcement."""
        text = open(CONTRACT_PATH, encoding="utf-8").read()
        assert "Runtime Enforcement" in text
        assert "runtime_enforcement" in text

    def test_contract_references_integration_doc(self):
        """Contract must reference VIBE_CODING_MODE_RUNTIME_INTEGRATION.md."""
        text = open(CONTRACT_PATH, encoding="utf-8").read()
        assert "VIBE_CODING_MODE_RUNTIME_INTEGRATION.md" in text

    def test_contract_lists_mandatory_functions(self):
        """Contract §10 must list all 4 mandatory functions."""
        text = open(CONTRACT_PATH, encoding="utf-8").read()
        assert "detect_mode_entry" in text
        assert "check_cross_repo_guard" in text
        assert "compile_casual_prompt" in text
        assert "generate_plan_approval_request" in text

    def test_contract_non_bypassable_enforcement(self):
        """Contract §10.3 must define non-bypassable rules."""
        text = open(CONTRACT_PATH, encoding="utf-8").read()
        assert "MUST call `detect_mode_entry()`" in text
        assert "MUST NOT" in text


# =============================================================================
# Integration Document
# =============================================================================


class TestIntegrationDocument:
    """VIBE_CODING_MODE_RUNTIME_INTEGRATION.md must exist and be valid."""

    def test_integration_doc_exists(self):
        """Integration doc must exist."""
        assert os.path.exists(INTEGRATION_PATH)

    def test_integration_doc_non_trivial(self):
        """Integration doc must be substantive."""
        text = open(INTEGRATION_PATH, encoding="utf-8").read()
        assert len(text) > 3000

    def test_integration_doc_has_all_sections(self):
        """Integration doc must have all required sections."""
        text = open(INTEGRATION_PATH, encoding="utf-8").read()
        for section in [
            "Mode Entry Detection",
            "Cross-Repo Guard",
            "Casual Prompt Compilation",
            "PLAN_APPROVAL_REQUEST Generation",
            "Forbidden Actions",
            "Integration Verification",
        ]:
            assert section in text, f"Missing section: {section}"

    def test_integration_doc_has_cli_examples(self):
        """Integration doc must include CLI usage examples."""
        text = open(INTEGRATION_PATH, encoding="utf-8").read()
        assert "detect-mode" in text
        assert "compile-prompt" in text
        assert "plan-approval-request" in text

    def test_integration_doc_has_function_signatures(self):
        """Integration doc must document function signatures."""
        text = open(INTEGRATION_PATH, encoding="utf-8").read()
        assert "detect_mode_entry(text: str) -> dict" in text
        assert "check_cross_repo_guard(text:" in text
        assert "compile_casual_prompt(text: str) -> dict" in text
        assert "generate_plan_approval_request(" in text


# =============================================================================
# CLI End-to-End Integration
# =============================================================================


class TestCLIEndToEnd:
    """CLI must work end-to-end for all integration points."""

    def _run_cli(self, *args):
        result = subprocess.run(
            [sys.executable, "scripts/conversational_intake_gate.py", "--json"] + list(args),
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        return json.loads(result.stdout), result.returncode

    def test_mode_entry_e2e(self):
        """detect-mode must return MODE_ACTIVE for entry trigger."""
        data, code = self._run_cli("detect-mode", "--text", "进入vibe coding模式")
        assert code == 0
        assert data["mode_active"] is True
        assert data["verdict"] == "MODE_ACTIVE"
        assert data["next_action"] == "INTAKE_REQUIRED"

    def test_cross_repo_hermes_e2e(self):
        """plan-approval-request with hermes must flag cross_repo_real_grey_use."""
        data, code = self._run_cli(
            "plan-approval-request",
            "--text", "进入vibe coding模式，帮我修 hermes PR #xxx conflict",
            "--phase-id", "V1.21.30B",
        )
        assert code == 0
        assert data["cross_repo_detected"] is True
        assert data["risk_classification"] == "cross_repo_real_grey_use"
        assert data["role_model_matrix_required"] is True

    def test_casual_bypass_e2e(self):
        """compile-prompt with casual bypass attempt must have gate_required=True."""
        data, code = self._run_cli("compile-prompt", "--text", "直接修完merge")
        assert code == 0
        assert data["gate_required"] is True
        assert len(data["forbidden_actions"]) > 0

    def test_full_workflow_e2e(self):
        """Full workflow: mode entry → cross-repo guard → plan approval request."""
        # Step 1: Mode entry
        mode_data, _ = self._run_cli("detect-mode", "--text", "进入vibe coding模式")
        assert mode_data["mode_active"] is True

        # Step 2: Cross-repo guard on subsequent request
        plan_data, _ = self._run_cli(
            "plan-approval-request",
            "--text", "修 hermes PR conflict",
            "--phase-id", "V1.21.30B",
        )
        assert plan_data["cross_repo_detected"] is True
        assert "BLOCK" in plan_data["operator_action_needed"]

    def test_schema_has_required_fields(self):
        """PLAN_APPROVAL_REQUEST must have all required fields."""
        data, _ = self._run_cli(
            "plan-approval-request",
            "--text", "实现新功能",
            "--phase-id", "V1.21.30B",
        )
        required = [
            "phase_id", "approval_id", "request_type", "goal",
            "risk_classification", "cross_repo_detected", "scope",
            "forbidden_actions", "role_model_matrix_required",
            "operator_action_needed", "next_step",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"


# =============================================================================
# Workflow Contract Reference
# =============================================================================


class TestWorkflowContractReference:
    """VIBE_CODING_WORKFLOW_CONTRACT.md must be consistent."""

    def test_workflow_contract_exists(self):
        """Workflow contract must exist."""
        path = os.path.join(REPO_ROOT, "docs", "VIBE_CODING_WORKFLOW_CONTRACT.md")
        assert os.path.exists(path)

    def test_workflow_contract_step0(self):
        """Workflow contract must define Step 0 (Enter Vibe Coding Role)."""
        path = os.path.join(REPO_ROOT, "docs", "VIBE_CODING_WORKFLOW_CONTRACT.md")
        text = open(path, encoding="utf-8").read()
        assert "Step 0" in text
        assert "进入" in text or "enter" in text.lower()
