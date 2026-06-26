#!/usr/bin/env python3
"""V1.21.29A — Model Pool Distribution Contract tests.

Covers:
- Contract file exists
- Contract declares registry does not store real keys
- Contract uses secret_ref / credential_status
- Contract defines Orchestrator unified add/delete/enable/disable
- Contract defines OpenCode Config Renderer dry-run
- Contract defines Node Sync requires operator approval
- Contract defines dynamic available model pool
- Contract defines OpenCode free/Go availability rules
- Contract defines unavailable/disabled/quarantine not as execution candidates
- Contract does not contain example plaintext keys
- Workflow contract references model pool distribution contract

Read-only. No real execution, no secret writes, no node dispatch.
"""
import re
from pathlib import Path

import pytest

# Paths
REPO_ROOT = Path(__file__).parent.parent
CONTRACT_PATH = REPO_ROOT / "docs" / "MODEL_POOL_DISTRIBUTION_CONTRACT.md"
WORKFLOW_CONTRACT_PATH = REPO_ROOT / "docs" / "VIBE_CODING_WORKFLOW_CONTRACT.md"


@pytest.fixture
def contract_text():
    """Load contract text."""
    assert CONTRACT_PATH.exists(), f"Contract not found: {CONTRACT_PATH}"
    return CONTRACT_PATH.read_text(encoding="utf-8")


@pytest.fixture
def workflow_text():
    """Load workflow contract text."""
    assert WORKFLOW_CONTRACT_PATH.exists(), f"Workflow contract not found: {WORKFLOW_CONTRACT_PATH}"
    return WORKFLOW_CONTRACT_PATH.read_text(encoding="utf-8")


class TestContractExists:
    """Contract file must exist."""

    def test_contract_file_exists(self):
        """MODEL_POOL_DISTRIBUTION_CONTRACT.md must exist."""
        assert CONTRACT_PATH.exists(), "MODEL_POOL_DISTRIBUTION_CONTRACT.md not found in docs/"


class TestRegistryNoRealKeys:
    """Contract must declare registry does not store real keys."""

    def test_registry_no_real_keys_declaration(self, contract_text):
        """Contract explicitly states registry stores no plaintext keys."""
        # Look for statements about registry not storing keys
        patterns = [
            r"never stores plaintext",
            r"no plaintext",
            r"MUST NOT contain",
            r"not.*store.*key",
            r"registry.*metadata.*only",
            r"no.*secret.*key",
        ]
        found = any(re.search(p, contract_text, re.IGNORECASE) for p in patterns)
        assert found, "Contract must declare registry does not store real keys"


class TestSecretRefAndCredentialStatus:
    """Contract must use secret_ref and credential_status."""

    def test_uses_secret_ref(self, contract_text):
        """Contract references secret_ref field."""
        assert "secret_ref" in contract_text, "Contract must reference secret_ref"

    def test_uses_credential_status(self, contract_text):
        """Contract references credential_status field."""
        assert "credential_status" in contract_text, "Contract must reference credential_status"

    def test_secret_ref_is_reference_only(self, contract_text):
        """Contract declares secret_ref is a reference, not actual key."""
        patterns = [
            r"secret_ref.*reference",
            r"reference.*only",
            r"identifier only",
            r"MUST NOT contain.*key",
        ]
        found = any(re.search(p, contract_text, re.IGNORECASE) for p in patterns)
        assert found, "Contract must declare secret_ref is reference only"


class TestOrchestratorGovernance:
    """Contract must define Orchestrator unified add/delete/enable/disable."""

    def test_orchestrator_governance(self, contract_text):
        """Contract defines Orchestrator as sole governance authority."""
        patterns = [
            r"Orchestrator.*governance",
            r"Orchestrator.*add.*delete.*enable.*disable",
            r"Orchestrator.*unified",
            r"sole governance authority",
        ]
        found = any(re.search(p, contract_text, re.IGNORECASE) for p in patterns)
        assert found, "Contract must define Orchestrator governance for add/delete/enable/disable"

    def test_lifecycle_workflows_defined(self, contract_text):
        """Contract defines add, delete, enable, disable workflows."""
        for action in ["Add Model", "Delete Model", "Enable Model", "Disable Model"]:
            assert action in contract_text, f"Contract must define {action} workflow"


class TestConfigRendererDryRun:
    """Contract must define OpenCode Config Renderer dry-run."""

    def test_renderer_dry_run_defined(self, contract_text):
        """Contract defines OpenCode Config Renderer dry-run."""
        patterns = [
            r"dry.?run",
            r"Config Renderer.*dry",
            r"dry.?run.*mode",
        ]
        found = any(re.search(p, contract_text, re.IGNORECASE) for p in patterns)
        assert found, "Contract must define OpenCode Config Renderer dry-run"

    def test_dry_run_example_no_keys(self, contract_text):
        """Dry-run example must not contain real keys."""
        # Find the dry-run output example section
        dry_run_section = contract_text[contract_text.find("Output (Dry-Run)"):]
        if len(dry_run_section) > 2000:
            dry_run_section = dry_run_section[:2000]

        # Check no real key patterns in dry-run example
        key_patterns = [
            r"sk-[a-zA-Z0-9]{20,}",
            r"AKIA[A-Z0-9]{16}",
            r"Bearer [a-zA-Z0-9]{20,}",
        ]
        for pattern in key_patterns:
            match = re.search(pattern, dry_run_section)
            assert not match, f"Dry-run example must not contain real key pattern: {match}"


class TestNodeSyncApproval:
    """Contract must define Node Sync requires operator approval."""

    def test_node_sync_operator_approval(self, contract_text):
        """Contract defines Node Sync requires operator approval."""
        patterns = [
            r"Node Sync.*operator.*approval",
            r"operator.*approval.*Node Sync",
            r"requires.*operator.*approval",
            r"MUST NOT.*without.*approval",
        ]
        found = any(re.search(p, contract_text, re.IGNORECASE) for p in patterns)
        assert found, "Contract must define Node Sync requires operator approval"


class TestDynamicAvailablePool:
    """Contract must define dynamic available model pool."""

    def test_dynamic_available_pool_defined(self, contract_text):
        """Contract defines dynamic available model pool."""
        patterns = [
            r"Available Model Pool",
            r"dynamic.*available.*pool",
            r"Available.*criteria",
        ]
        found = any(re.search(p, contract_text, re.IGNORECASE) for p in patterns)
        assert found, "Contract must define dynamic available model pool"

    def test_available_pool_criteria(self, contract_text):
        """Contract defines criteria for available pool inclusion."""
        # Must mention enabled, credential_status, health_status, quarantine_status
        required_terms = ["enabled", "credential_status", "health_status", "quarantine_status"]
        for term in required_terms:
            assert term in contract_text, f"Contract must reference {term} in available pool criteria"


class TestOpenCodeFreeGoRules:
    """Contract must define OpenCode free and Go availability rules."""

    def test_opencode_free_rules(self, contract_text):
        """Contract defines OpenCode free model availability rules."""
        patterns = [
            r"OpenCode Free Models",
            r"opencode.*free.*model",
            r"free.*available",
        ]
        found = any(re.search(p, contract_text, re.IGNORECASE) for p in patterns)
        assert found, "Contract must define OpenCode free model rules"

    def test_opencode_go_rules(self, contract_text):
        """Contract defines OpenCode Go model availability rules."""
        patterns = [
            r"OpenCode Go Models",
            r"opencode.*go.*model",
            r"go.*available",
        ]
        found = any(re.search(p, contract_text, re.IGNORECASE) for p in patterns)
        assert found, "Contract must define OpenCode Go model rules"


class TestNonAvailableExclusion:
    """Contract must define unavailable/disabled/quarantine not as execution candidates."""

    def test_non_available_exclusion(self, contract_text):
        """Contract defines non-available models excluded from execution."""
        patterns = [
            r"Non-available",
            r"not.*execution.*candidate",
            r"excluded.*execution",
            r"Non-available.*summary",
        ]
        found = any(re.search(p, contract_text, re.IGNORECASE) for p in patterns)
        assert found, "Contract must define non-available models excluded from execution"

    def test_quarantine_exclusion(self, contract_text):
        """Contract defines quarantined models excluded."""
        patterns = [
            r"quarantine.*excluded",
            r"quarantine.*Non-available",
            r"quarantine.*not.*available",
        ]
        found = any(re.search(p, contract_text, re.IGNORECASE) for p in patterns)
        assert found, "Contract must define quarantined models excluded from available pool"


class TestNoPlaintextKeys:
    """Contract must not contain example plaintext keys."""

    def test_no_sk_keys(self, contract_text):
        """Contract must not contain sk- prefixed keys."""
        # Allow secret_ref patterns like secret:xxx but not actual keys
        sk_pattern = r"sk-[a-zA-Z0-9]{20,}"
        matches = re.findall(sk_pattern, contract_text)
        assert len(matches) == 0, f"Contract must not contain sk- keys: {matches}"

    def test_no_akia_keys(self, contract_text):
        """Contract must not contain AKIA AWS keys."""
        akia_pattern = r"AKIA[A-Z0-9]{16}"
        matches = re.findall(akia_pattern, contract_text)
        assert len(matches) == 0, f"Contract must not contain AKIA keys: {matches}"

    def test_no_bearer_tokens(self, contract_text):
        """Contract must not contain Bearer tokens."""
        bearer_pattern = r"Bearer [a-zA-Z0-9]{20,}"
        matches = re.findall(bearer_pattern, contract_text)
        assert len(matches) == 0, f"Contract must not contain Bearer tokens: {matches}"

    def test_no_generic_api_keys(self, contract_text):
        """Contract must not contain generic API key patterns."""
        # Check for common API key patterns
        patterns = [
            r"api[_-]?key[\"']?\s*[:=]\s*[\"'][a-zA-Z0-9]{20,}",
            r"secret[\"']?\s*[:=]\s*[\"'][a-zA-Z0-9]{20,}",
        ]
        for pattern in patterns:
            matches = re.findall(pattern, contract_text, re.IGNORECASE)
            assert len(matches) == 0, f"Contract must not contain generic API key patterns: {matches}"


class TestWorkflowContractReference:
    """Workflow contract must reference model pool distribution contract."""

    def test_workflow_references_distribution_contract(self, workflow_text):
        """Workflow contract references MODEL_POOL_DISTRIBUTION_CONTRACT."""
        assert "MODEL_POOL_DISTRIBUTION_CONTRACT" in workflow_text, \
            "Workflow contract must reference MODEL_POOL_DISTRIBUTION_CONTRACT"
