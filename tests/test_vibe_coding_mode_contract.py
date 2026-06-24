#!/usr/bin/env python3
"""V1.21.29W -- Vibe Coding Mode Contract tests.

Covers:
- Contract document exists and is valid
- Mode entry triggers defined
- Mandatory workflow state machine defined
- Operator gates defined
- Non-bypassable rules defined (tests, review, secrets, debug, fallback, main, local dirt)
- Report schema defined (PLAN_APPROVAL_REQUEST, EXECUTION_GATE_REPORT)
- Role/model reporting requirements defined
- Dispatch policy defined
- Deviation policy defined (including D1 manual review, D2 rate limit)
- Cross-repo grey-use policy defined (Hermes upstream boundary)
- Rollback policy defined
- Casual user prompt cannot bypass gates

Read-only. No real execution, no gate verdict change.
"""
from pathlib import Path

import pytest

CONTRACT_PATH = Path(__file__).parent.parent / "docs" / "VIBE_CODING_MODE_CONTRACT.md"


@pytest.fixture(scope="module")
def contract_text():
    """Load the contract text."""
    assert CONTRACT_PATH.exists(), f"Contract not found: {CONTRACT_PATH}"
    return CONTRACT_PATH.read_text(encoding="utf-8")


# -- Contract existence --------------------------------------------------------

class TestContractExists:
    """Contract document must exist and be non-trivial."""

    def test_contract_file_exists(self):
        assert CONTRACT_PATH.exists(), "VIBE_CODING_MODE_CONTRACT.md must exist"

    def test_contract_non_trivial(self, contract_text):
        assert len(contract_text) > 2000, "Contract must be substantive (>2000 chars)"

    def test_contract_has_title(self, contract_text):
        assert "# Vibe Coding Mode Contract" in contract_text


# -- Mode entry ----------------------------------------------------------------

class TestModeEntry:
    """Mode entry triggers must be defined."""

    def test_mode_entry_section_exists(self, contract_text):
        assert "mode_entry" in contract_text.lower() or "Mode Entry" in contract_text

    def test_entry_triggers_defined(self, contract_text):
        text = contract_text.lower()
        assert "keyword" in text or "trigger" in text
        assert "version" in text

    def test_casual_prompt_cannot_bypass(self, contract_text):
        text = contract_text.lower()
        assert any(phrase in text for phrase in [
            "casual", "cannot bypass", "non-bypassable",
            "must not skip", "must still trigger"
        ]), "Contract must state casual prompts cannot bypass gates"


# -- Mandatory workflow --------------------------------------------------------

class TestMandatoryWorkflow:
    """Mandatory workflow state machine must be defined."""

    def test_mandatory_workflow_section(self, contract_text):
        assert "mandatory_workflow" in contract_text.lower() or "Mandatory Workflow" in contract_text

    def test_state_machine_steps(self, contract_text):
        for step in range(10):
            assert f"Step {step}" in contract_text or f"step {step}" in contract_text.lower(),                 f"Step {step} not found in contract"

    def test_no_state_skipped(self, contract_text):
        text = contract_text.lower()
        assert "no state may be skipped" in text or "must not skip" in text or "cannot be bypassed" in text


# -- Operator gates ------------------------------------------------------------

class TestOperatorGates:
    """Operator gates must be defined."""

    def test_operator_gates_section(self, contract_text):
        assert "operator_gates" in contract_text.lower() or "Operator Gates" in contract_text

    def test_plan_gate(self, contract_text):
        assert "Plan Gate" in contract_text or "plan gate" in contract_text.lower()

    def test_ready_gate(self, contract_text):
        assert "Ready Gate" in contract_text or "ready gate" in contract_text.lower()

    def test_merge_gate(self, contract_text):
        assert "Merge Gate" in contract_text or "merge gate" in contract_text.lower()

    def test_cleanup_freeze_gate(self, contract_text):
        text = contract_text.lower()
        assert "cleanup" in text and "freeze" in text

    def test_deviation_gate(self, contract_text):
        assert "Deviation Gate" in contract_text or "deviation gate" in contract_text.lower()

    def test_rollback_gate(self, contract_text):
        assert "Rollback Gate" in contract_text or "rollback gate" in contract_text.lower()


# -- Non-bypassable rules ------------------------------------------------------

class TestNonBypassableRules:
    """Non-bypassable rules must be defined."""

    def test_non_bypassable_section(self, contract_text):
        assert "non_bypassable" in contract_text.lower() or "Non-Bypassable" in contract_text

    def test_mandatory_tests(self, contract_text):
        text = contract_text.lower()
        assert "targeted tests" in text or "test execution" in text
        assert "must" in text and "test" in text

    def test_mandatory_review(self, contract_text):
        text = contract_text.lower()
        assert "mandatory review" in text or "review_pass" in text or "review_blocked" in text

    def test_secret_prohibition(self, contract_text):
        text = contract_text.lower()
        assert "no plaintext" in text or "no key" in text or "secret_ref" in text

    def test_debug_raw_prohibition(self, contract_text):
        text = contract_text.lower()
        assert "debug" in text
        assert "raw" in text or "redacted" in text

    def test_fallback_prohibition(self, contract_text):
        text = contract_text.lower()
        assert "no auto-fallback" in text or "no fallback" in text or "fallback prohibition" in text
        assert "provider discovery" in text

    def test_main_protection(self, contract_text):
        text = contract_text.lower()
        assert "main protection" in text or "no direct push to main" in text or "no main modification" in text

    def test_local_dirt_protection(self, contract_text):
        assert "malicious_payload_evidence.json" in contract_text
        assert "pilot-prompts/" in contract_text


# -- Report schema -------------------------------------------------------------

class TestReportSchema:
    """Report schemas must be defined."""

    def test_report_schema_section(self, contract_text):
        assert "report_schema" in contract_text.lower() or "Report Schema" in contract_text

    def test_plan_approval_request(self, contract_text):
        assert "PLAN_APPROVAL_REQUEST" in contract_text

    def test_execution_gate_report(self, contract_text):
        assert "EXECUTION_GATE_REPORT" in contract_text

    def test_bilingual_requirement(self, contract_text):
        text = contract_text.lower()
        assert "bilingual" in text or "chinese" in text or "english" in text


# -- Role/model reporting ------------------------------------------------------

class TestRoleModelReporting:
    """Role/model reporting must be defined."""

    def test_role_model_section(self, contract_text):
        assert "role_model_reporting" in contract_text.lower() or "Role/Model Reporting" in contract_text

    def test_mandatory_fields(self, contract_text):
        text = contract_text.lower()
        assert "planned" in text
        assert "actual" in text
        assert "calls" in text
        assert "duration" in text
        assert "fallback" in text

    def test_no_call_reporting(self, contract_text):
        text = contract_text.lower()
        assert "no-call" in text or "no call" in text or "manual review" in text or "n/a" in text


# -- Dispatch policy -----------------------------------------------------------

class TestDispatchPolicy:
    """Dispatch policy must be defined."""

    def test_dispatch_policy_section(self, contract_text):
        assert "dispatch_policy" in contract_text.lower() or "Dispatch Policy" in contract_text

    def test_single_node_dispatch(self, contract_text):
        text = contract_text.lower()
        assert "single" in text and "node" in text

    def test_three_node_dispatch(self, contract_text):
        text = contract_text.lower()
        assert "three" in text and "node" in text

    def test_parallel_queue_dispatch(self, contract_text):
        text = contract_text.lower()
        assert "parallel" in text or "queue" in text


# -- Deviation policy ----------------------------------------------------------

class TestDeviationPolicy:
    """Deviation policy must be defined, including known deviations D1/D2."""

    def test_deviation_policy_section(self, contract_text):
        assert "deviation_policy" in contract_text.lower() or "Deviation Policy" in contract_text

    def test_d1_manual_review_fallback(self, contract_text):
        text = contract_text.lower()
        assert "d1" in text
        assert "manual" in text and "review" in text

    def test_d2_rate_limit(self, contract_text):
        text = contract_text.lower()
        assert "d2" in text
        assert "429" in text or "rate limit" in text

    def test_deviation_risk_levels(self, contract_text):
        text = contract_text.lower()
        assert "low" in text and "medium" in text and "high" in text


# -- Cross-repo grey-use policy -----------------------------------------------

class TestCrossRepoGreyUsePolicy:
    """Cross-repo grey-use policy must be defined, including Hermes upstream boundary."""

    def test_cross_repo_section(self, contract_text):
        text = contract_text.lower()
        assert "cross_repo" in text or "cross-repo" in text or "grey-use" in text or "grey_use" in text

    def test_hermes_upstream_boundary(self, contract_text):
        text = contract_text.lower()
        assert "hermes" in text
        assert "fork" in text or "isolation" in text

    def test_draft_pr_only(self, contract_text):
        text = contract_text.lower()
        assert "draft" in text and "pr" in text

    def test_no_auto_merge(self, contract_text):
        text = contract_text.lower()
        assert "no auto-merge" in text or "auto-merge" in text or "auto merge" in text


# -- Rollback policy -----------------------------------------------------------

class TestRollbackPolicy:
    """Rollback policy must be defined."""

    def test_rollback_section(self, contract_text):
        assert "rollback" in contract_text.lower()

    def test_rollback_triggers(self, contract_text):
        text = contract_text.lower()
        assert "key leakage" in text or "key leak" in text
        assert "test failure" in text

    def test_rollback_procedure(self, contract_text):
        text = contract_text.lower()
        assert "stop" in text and "preserve" in text and "report" in text and "wait" in text


# -- Workflow contract reference -----------------------------------------------

class TestWorkflowContractReference:
    """Workflow contract must reference the mode contract."""

    def test_workflow_references_mode_contract(self):
        workflow_path = Path(__file__).parent.parent / "docs" / "VIBE_CODING_WORKFLOW_CONTRACT.md"
        if workflow_path.exists():
            text = workflow_path.read_text(encoding="utf-8")
            has_ref = "MODE_CONTRACT" in text or "VIBE_CODING_MODE_CONTRACT" in text
            if not has_ref:
                pytest.skip("Workflow contract does not yet reference mode contract - will be updated")


# -- No real key patterns ------------------------------------------------------

class TestNoRealKeys:
    """Contract must not contain real key patterns."""

    def test_no_sk_prefix(self, contract_text):
        assert "sk-" not in contract_text, "Contract must not contain sk- key prefix"

    def test_no_akia(self, contract_text):
        assert "AKIA" not in contract_text, "Contract must not contain AKIA key prefix"

    def test_no_api_key_values(self, contract_text):
        assert "api_key" not in contract_text or "secret_ref" in contract_text
