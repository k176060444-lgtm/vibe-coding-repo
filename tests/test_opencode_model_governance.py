#!/usr/bin/env python3
"""Tests for Model Pool Governance Wrapper.

Covers:
- Schema new fields (endpoint, protocol, secret_ref, credential_status, quarantine_status)
- add_model accepts non-secret endpoint/protocol/secret_ref
- add_model rejects real key / token-like input
- endpoint with token/api_key/password query rejected
- export_sanitized includes new fields, no real keys
- delete_model not found → blocked
- delete_model conservative block (no approval)
- active reference → blocked even with force
- valid approval + no active reference → delete succeeds
- governance add/enable/disable/retire/delete without approval_id → approval_required
- governance with approval_id → executes
- invalid approval / invalid action → blocked
- audit fields complete
- renderer integration can consume new fields

Contract: docs/MODEL_POOL_DISTRIBUTION_CONTRACT.md
"""
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from opencode_model_pool import (
    ModelPool,
    new_model_entry,
    _validate_endpoint_no_secrets,
    _validate_secret_ref_placeholder,
    _validate_no_dangerous_fields,
)
from opencode_model_governance import (
    execute_governance,
    generate_action_plan,
    self_check,
    validate_action,
)


# --- Fixtures ---


@pytest.fixture
def tmp_pool(tmp_path):
    """Create a temporary ModelPool."""
    pool_path = str(tmp_path / "test_pool.json")
    return ModelPool(pool_path)


@pytest.fixture
def populated_pool(tmp_path):
    """Create a ModelPool with some models."""
    pool_path = str(tmp_path / "pop_pool.json")
    pool = ModelPool(pool_path)
    pool.add_model("opencode/mimo-v2.5-free", alias="mimo-free", cost_tag="free",
                    endpoint="https://api.opencode.example.com/v1",
                    secret_ref="secret:opencode:mimo-free")
    pool.add_model("deepseek-plan/deepseek-v4-pro", alias="ds-v4-pro", cost_tag="paid",
                    endpoint="https://api.deepseek.example.com/v1",
                    secret_ref="secret:deepseek:api-key", credential_status="valid")
    return pool


# --- Schema Tests ---


class TestSchemaNewFields:
    """new_model_entry must include new fields."""

    def test_endpoint_field(self):
        entry = new_model_entry("test/model", endpoint="https://example.com/v1")
        assert entry["endpoint"] == "https://example.com/v1"

    def test_protocol_field(self):
        entry = new_model_entry("test/model", protocol="custom")
        assert entry["protocol"] == "custom"

    def test_protocol_default(self):
        entry = new_model_entry("test/model")
        assert entry["protocol"] == "openai-compatible"

    def test_secret_ref_field(self):
        entry = new_model_entry("test/model", secret_ref="secret:test:model")
        assert entry["secret_ref"] == "secret:test:model"

    def test_credential_status_field(self):
        entry = new_model_entry("test/model", credential_status="valid")
        assert entry["credential_status"] == "valid"

    def test_credential_status_default(self):
        entry = new_model_entry("test/model")
        assert entry["credential_status"] == "missing"

    def test_quarantine_status_field(self):
        entry = new_model_entry("test/model", quarantine_status="quarantined")
        assert entry["quarantine_status"] == "quarantined"

    def test_quarantine_status_default(self):
        entry = new_model_entry("test/model")
        assert entry["quarantine_status"] == "none"


# --- add_model Tests ---


class TestAddModelNewFields:
    """add_model must accept new fields."""

    def test_add_with_endpoint(self, tmp_pool):
        result = tmp_pool.add_model("test/model", endpoint="https://example.com/v1")
        assert result["action"] == "added"
        assert tmp_pool.models["test/model"]["endpoint"] == "https://example.com/v1"

    def test_add_with_protocol(self, tmp_pool):
        result = tmp_pool.add_model("test/model", protocol="custom")
        assert result["action"] == "added"
        assert tmp_pool.models["test/model"]["protocol"] == "custom"

    def test_add_with_secret_ref(self, tmp_pool):
        result = tmp_pool.add_model("test/model", secret_ref="secret:test:model")
        assert result["action"] == "added"
        assert tmp_pool.models["test/model"]["secret_ref"] == "secret:test:model"

    def test_add_with_credential_status(self, tmp_pool):
        result = tmp_pool.add_model("test/model", credential_status="valid")
        assert result["action"] == "added"
        assert tmp_pool.models["test/model"]["credential_status"] == "valid"


# --- Security Tests ---


class TestSecurityRejectKeys:
    """add_model / new_model_entry must reject real keys."""

    def test_reject_sk_key_in_endpoint(self):
        with pytest.raises(ValueError, match="endpoint contains suspected secret"):
            new_model_entry("test/model", endpoint="https://api.example.com/v1?api_key=sk-abc123def456ghi789")

    def test_reject_bearer_in_secret_ref(self):
        with pytest.raises(ValueError, match="secret_ref contains suspected real key"):
            new_model_entry("test/model", secret_ref="Bearer abc123def456ghi789jkl012")

    def test_reject_akia_in_secret_ref(self):
        with pytest.raises(ValueError, match="secret_ref contains suspected real key"):
            new_model_entry("test/model", secret_ref="AKIAIOSFODNN7EXAMPLE")

    def test_reject_private_key_in_secret_ref(self):
        with pytest.raises(ValueError, match="secret_ref contains suspected real key"):
            new_model_entry("test/model", secret_ref="-----BEGIN RSA PRIVATE KEY-----")

    def test_reject_secret_ref_not_starting_with_secret(self):
        with pytest.raises(ValueError, match="secret_ref must start with"):
            new_model_entry("test/model", secret_ref="some-random-value")

    def test_accept_valid_secret_ref(self):
        entry = new_model_entry("test/model", secret_ref="secret:deepseek:api-key")
        assert entry["secret_ref"] == "secret:deepseek:api-key"

    def test_reject_dangerous_field_name(self):
        with pytest.raises(ValueError, match="dangerous field name rejected"):
            _validate_no_dangerous_fields({"api_key": "value"})

    def test_reject_password_field(self):
        with pytest.raises(ValueError, match="dangerous field name rejected"):
            _validate_no_dangerous_fields({"password": "value"})

    def test_reject_endpoint_with_token_query(self):
        with pytest.raises(ValueError, match="endpoint contains suspected secret"):
            _validate_endpoint_no_secrets("https://api.example.com/v1?token=abc123")

    def test_reject_endpoint_with_password_userinfo(self):
        with pytest.raises(ValueError, match="endpoint contains suspected secret"):
            _validate_endpoint_no_secrets("https://user:password@api.example.com/v1")

    def test_accept_clean_endpoint(self):
        _validate_endpoint_no_secrets("https://api.example.com/v1")  # Should not raise


# --- export_sanitized Tests ---


class TestExportSanitized:
    """export_sanitized must include new fields, no real keys."""

    def test_export_has_endpoint(self, populated_pool):
        exported = populated_pool.export_sanitized()
        for mid, entry in exported["models"].items():
            assert "endpoint" in entry

    def test_export_has_protocol(self, populated_pool):
        exported = populated_pool.export_sanitized()
        for mid, entry in exported["models"].items():
            assert "protocol" in entry

    def test_export_has_secret_ref(self, populated_pool):
        exported = populated_pool.export_sanitized()
        for mid, entry in exported["models"].items():
            assert "secret_ref" in entry

    def test_export_has_credential_status(self, populated_pool):
        exported = populated_pool.export_sanitized()
        for mid, entry in exported["models"].items():
            assert "credential_status" in entry

    def test_export_has_quarantine_status(self, populated_pool):
        exported = populated_pool.export_sanitized()
        for mid, entry in exported["models"].items():
            assert "quarantine_status" in entry

    def test_export_no_real_keys(self, populated_pool):
        exported = populated_pool.export_sanitized()
        exported_str = json.dumps(exported)
        assert "sk-" not in exported_str
        assert "AKIA" not in exported_str


# --- delete_model Tests ---


class TestDeleteModel:
    """delete_model conservative strategy."""

    def test_delete_not_found(self, tmp_pool):
        result = tmp_pool.delete_model("nonexistent/model")
        assert result["status"] == "blocked"
        assert "not found" in result["error"]

    def test_delete_requires_approval(self, populated_pool):
        result = populated_pool.delete_model("opencode/mimo-v2.5-free")
        assert result["status"] == "approval_required"
        assert result["requires_approval"] is True
        # Model should still exist
        assert "opencode/mimo-v2.5-free" in populated_pool.models

    def test_delete_active_reference_blocked(self, populated_pool):
        """Active reference blocks delete even with force."""
        result = populated_pool.delete_model(
            "opencode/mimo-v2.5-free",
            force=True,
            active_model_ids={"opencode/mimo-v2.5-free"},
            approval_context={"approval_id": "test-001"},
        )
        assert result["status"] == "blocked"
        assert "active_job_reference" in result.get("blocked_reason", "")
        # Model should still exist
        assert "opencode/mimo-v2.5-free" in populated_pool.models

    def test_delete_with_approval_succeeds(self, populated_pool):
        result = populated_pool.delete_model(
            "opencode/mimo-v2.5-free",
            approval_context={"approval_id": "test-001"},
        )
        assert result["status"] == "executed"
        assert result["action"] == "deleted"
        # Model should be removed
        assert "opencode/mimo-v2.5-free" not in populated_pool.models

    def test_delete_no_active_reference_with_approval(self, populated_pool):
        """Delete with approval and no active references succeeds."""
        result = populated_pool.delete_model(
            "opencode/mimo-v2.5-free",
            active_model_ids=set(),  # No active references
            approval_context={"approval_id": "test-001"},
        )
        assert result["status"] == "executed"
        assert "opencode/mimo-v2.5-free" not in populated_pool.models


# --- Governance Tests ---


class TestGovernanceActionPlan:
    """Governance must generate action plans."""

    def test_add_plan(self, populated_pool):
        plan = generate_action_plan("add", "new/model", populated_pool)
        assert plan["action"] == "add"
        assert plan["status"] == "approval_required"
        assert plan["risk_level"] == "medium"

    def test_delete_plan_requires_approval(self, populated_pool):
        plan = generate_action_plan("delete", "opencode/mimo-v2.5-free", populated_pool)
        assert plan["requires_approval"] is True
        assert plan["risk_level"] == "high"

    def test_enable_plan(self, populated_pool):
        plan = generate_action_plan("enable", "opencode/mimo-v2.5-free", populated_pool)
        assert plan["action"] == "enable"
        assert plan["status"] == "approval_required"

    def test_invalid_action(self, populated_pool):
        plan = generate_action_plan("invalid", "test/model", populated_pool)
        assert plan["status"] == "invalid"

    def test_add_existing_model_blocked(self, populated_pool):
        plan = generate_action_plan("add", "opencode/mimo-v2.5-free", populated_pool)
        assert plan["status"] == "blocked"
        assert "already_exists" in plan.get("blocked_reason", "")

    def test_enable_nonexistent_blocked(self, tmp_pool):
        plan = generate_action_plan("enable", "nonexistent/model", tmp_pool)
        assert plan["status"] == "blocked"
        assert "not_found" in plan.get("blocked_reason", "")


class TestGovernanceExecute:
    """Governance execute must enforce approval boundary."""

    def test_add_without_approval(self, tmp_pool):
        """add without approval_id → approval_required."""
        result = execute_governance("add", "test/model", "operator-1", tmp_pool)
        assert result["status"] == "approval_required"
        # Model should not exist
        assert "test/model" not in tmp_pool.models

    def test_add_with_approval(self, tmp_pool):
        """add with approval_id → executes."""
        result = execute_governance("add", "test/model", "operator-1", tmp_pool,
                                     approval_id="approval-001",
                                     model_params={"endpoint": "https://example.com/v1"})
        assert result["status"] == "executed"
        assert result["result"]["action"] == "added"
        assert "test/model" in tmp_pool.models

    def test_enable_without_approval(self, populated_pool):
        """enable without approval_id → approval_required."""
        populated_pool.disable_model("opencode/mimo-v2.5-free")
        result = execute_governance("enable", "opencode/mimo-v2.5-free", "operator-1", populated_pool)
        assert result["status"] == "approval_required"

    def test_enable_with_approval(self, populated_pool):
        """enable with approval_id → executes."""
        populated_pool.disable_model("opencode/mimo-v2.5-free")
        result = execute_governance("enable", "opencode/mimo-v2.5-free", "operator-1", populated_pool,
                                     approval_id="approval-002")
        assert result["status"] == "executed"
        assert result["result"]["action"] == "enabled"

    def test_disable_without_approval(self, populated_pool):
        """disable without approval_id → approval_required."""
        result = execute_governance("disable", "opencode/mimo-v2.5-free", "operator-1", populated_pool)
        assert result["status"] == "approval_required"

    def test_disable_with_approval(self, populated_pool):
        """disable with approval_id → executes."""
        result = execute_governance("disable", "opencode/mimo-v2.5-free", "operator-1", populated_pool,
                                     approval_id="approval-003")
        assert result["status"] == "executed"
        assert result["result"]["action"] == "disabled"

    def test_retire_without_approval(self, populated_pool):
        """retire without approval_id → approval_required."""
        result = execute_governance("retire", "opencode/mimo-v2.5-free", "operator-1", populated_pool)
        assert result["status"] == "approval_required"

    def test_retire_with_approval(self, populated_pool):
        """retire with approval_id → executes."""
        result = execute_governance("retire", "opencode/mimo-v2.5-free", "operator-1", populated_pool,
                                     approval_id="approval-004")
        assert result["status"] == "executed"
        assert result["result"]["action"] == "retired"

    def test_delete_without_approval(self, populated_pool):
        """delete without approval_id → approval_required."""
        result = execute_governance("delete", "opencode/mimo-v2.5-free", "operator-1", populated_pool)
        assert result["status"] == "approval_required"
        # Model should still exist
        assert "opencode/mimo-v2.5-free" in populated_pool.models

    def test_delete_with_approval(self, populated_pool):
        """delete with approval_id → executes."""
        result = execute_governance("delete", "opencode/mimo-v2.5-free", "operator-1", populated_pool,
                                     approval_id="approval-005")
        assert result["status"] == "executed"
        assert result["result"]["action"] == "deleted"
        # Model should be removed
        assert "opencode/mimo-v2.5-free" not in populated_pool.models

    def test_invalid_action_blocked(self, populated_pool):
        """invalid action → invalid."""
        result = execute_governance("invalid", "test/model", "operator-1", populated_pool)
        assert result["status"] == "invalid"

    def test_delete_nonexistent_blocked(self, tmp_pool):
        """delete nonexistent model → blocked."""
        result = execute_governance("delete", "nonexistent/model", "operator-1", tmp_pool,
                                     approval_id="approval-006")
        assert result["status"] == "blocked"


class TestGovernanceAudit:
    """Governance audit fields must be complete."""

    def test_audit_fields_present(self, populated_pool):
        result = execute_governance("add", "new/model", "operator-1", populated_pool,
                                     approval_id="approval-001")
        audit = result["audit"]
        assert "timestamp" in audit
        assert audit["operator_id"] == "operator-1"
        assert audit["approval_id"] == "approval-001"
        assert audit["action"] == "add"
        assert audit["model_id"] == "new/model"
        assert "pool_snapshot_sha256" in audit
        assert "governance_version" in audit

    def test_audit_on_approval_required(self, populated_pool):
        result = execute_governance("delete", "opencode/mimo-v2.5-free", "operator-1", populated_pool)
        audit = result["audit"]
        assert audit["approval_id"] is None
        assert audit["action"] == "delete"


class TestGovernanceSecurity:
    """Governance must reject dangerous inputs."""

    def test_reject_dangerous_model_params(self, tmp_pool):
        """Governance must reject dangerous field names in model_params."""
        result = execute_governance("add", "test/model", "operator-1", tmp_pool,
                                     approval_id="approval-001",
                                     model_params={"api_key": "sk-abc123"})
        # Should fail due to dangerous field name
        assert result["status"] == "blocked"
        assert "dangerous field name" in result.get("result", {}).get("error", "")


class TestSelfCheck:
    """Self-check must return ok."""

    def test_self_check(self):
        result = self_check()
        assert result["status"] == "ok"
        assert "valid_actions" in result
        assert "risk_levels" in result
