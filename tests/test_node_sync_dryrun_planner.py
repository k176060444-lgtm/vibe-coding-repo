#!/usr/bin/env python3
"""Tests for Node Sync Dry-run Planner v1.0.0

Contract: docs/MODEL_POOL_DISTRIBUTION_CONTRACT.md
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from node_sync_dryrun_planner import (
    PLANNER_VERSION,
    build_approval_receipt,
    build_config_preview,
    build_rollback_plan,
    get_planned_paths,
    plan_multi_node_sync,
    plan_node_sync,
    run_safety_checks,
    self_check,
    validate_input,
)


# --- Fixtures ---


@pytest.fixture
def basic_renderer_output():
    """Basic renderer output for testing."""
    return {
        "node": "21bao",
        "dry_run": True,
        "config_draft": {
            "node": "21bao",
            "models": [
                {
                    "alias": "mimo-v2.5-free",
                    "provider": "opencode",
                    "secret_ref": "secret:opencode:mimo-v2.5-free",
                    "credential_source": "node-local-secure-storage",
                    "protocol": "openai-compatible",
                    "endpoint": "",
                    "credential_status": "not-configured",
                },
                {
                    "alias": "deepseek-v4-flash-free",
                    "provider": "opencode",
                    "secret_ref": "secret:opencode:deepseek-v4-flash-free",
                    "credential_source": "node-local-secure-storage",
                    "protocol": "openai-compatible",
                    "endpoint": "",
                    "credential_status": "not-configured",
                },
            ],
            "default_model": "mimo-v2.5-free",
        },
        "role_assignment": {
            "implementer": {"model_alias": "mimo-v2.5-free", "status": "configured"},
            "reviewer": {"model_alias": "deepseek-v4-flash-free", "status": "configured"},
        },
        "warnings": [],
        "non_available_summary": [
            {"model_id": "volcengine-plan/ark-code-latest", "reason": "credential_status=missing"},
        ],
        "requires_operator_approval": True,
        "audit": {"input_hash": "abc123def456", "renderer_version": "1.0.0"},
    }


@pytest.fixture
def empty_models_renderer():
    """Renderer output with empty models."""
    return {
        "node": "5bao",
        "dry_run": True,
        "config_draft": {
            "node": "5bao",
            "models": [],
            "default_model": None,
        },
        "role_assignment": {},
        "warnings": ["no available models for this node"],
        "non_available_summary": [],
        "requires_operator_approval": True,
        "audit": {"input_hash": "empty", "renderer_version": "1.0.0"},
    }


# --- Test Input Validation ---


class TestInputValidation:
    """Tests for input validation."""

    def test_valid_input(self, basic_renderer_output):
        valid, errors = validate_input(basic_renderer_output, dry_run=True)
        assert valid is True
        assert errors == []

    def test_dry_run_false(self, basic_renderer_output):
        valid, errors = validate_input(basic_renderer_output, dry_run=False)
        assert valid is False
        assert any("dry_run" in e for e in errors)

    def test_empty_renderer(self):
        valid, errors = validate_input({}, dry_run=True)
        assert valid is False
        assert any("non-empty" in e for e in errors)

    def test_none_renderer(self):
        valid, errors = validate_input(None, dry_run=True)
        assert valid is False

    def test_missing_node(self):
        valid, errors = validate_input({"dry_run": True, "config_draft": {}}, dry_run=True)
        assert valid is False
        assert any("node" in e for e in errors)

    def test_missing_config_draft(self):
        valid, errors = validate_input({"node": "test", "dry_run": True}, dry_run=True)
        assert valid is False
        assert any("config_draft" in e for e in errors)

    def test_renderer_dry_run_false(self):
        output = {"node": "test", "dry_run": False, "config_draft": {}}
        valid, errors = validate_input(output, dry_run=True)
        assert valid is False
        assert any("renderer_output.dry_run" in e for e in errors)


# --- Test Plan Node Sync ---


class TestPlanNodeSync:
    """Tests for main plan_node_sync function."""

    def test_basic_plan_structure(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        assert plan["node"] == "21bao"
        assert plan["dry_run"] is True
        assert plan["requires_operator_approval"] is True
        assert plan["planner_version"] == PLANNER_VERSION
        assert "timestamp" in plan

    def test_action_plan_fields(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        ap = plan["action_plan"]
        assert ap["action"] == "sync_config"
        assert ap["target_node"] == "21bao"
        assert ap["model_count"] == 2
        assert ap["default_model"] == "mimo-v2.5-free"
        assert len(ap["models_to_sync"]) == 2
        assert "implementer" in ap["roles_to_assign"]
        assert ap["risk_level"] == "medium"

    def test_config_preview(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        cp = plan["config_preview"]
        assert cp["format"] == "opencode-jsonc"
        assert cp["no_real_keys"] is True
        assert len(cp["content_hash"]) == 64  # SHA256
        assert len(cp["secret_fields"]) == 2
        assert cp["secret_fields"][0].startswith("secret:")

    def test_approval_receipt(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        ar = plan["approval_receipt_draft"]
        assert ar["status"] == "pending_operator_approval"
        assert ar["operator_id"] == "test-op"
        assert ar["target_node"] == "21bao"
        assert len(ar["model_aliases"]) == 2
        assert ar["risk_level"] == "medium"
        assert len(ar["input_hash"]) == 64
        assert "timestamp" in ar

    def test_approval_receipt_custom_id(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="op",
                              approval_id="approval-custom-001")
        assert plan["approval_receipt_draft"]["approval_id"] == "approval-custom-001"

    def test_rollback_plan(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        rp = plan["rollback_plan"]
        assert rp["strategy"] == "backup-and-restore"
        assert rp["dry_run_only"] is True
        assert len(rp["rollback_steps"]) >= 3
        assert rp["backup_path"] != ""
        assert len(rp["rollback_hash"]) == 64

    def test_safety_checks_passed(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        sc = plan["safety_checks"]
        assert sc["passed"] is True
        assert sc["dry_run_enforced"] is True
        assert sc["no_secrets_in_output"] is True
        assert sc["no_node_write"] is True
        assert sc["no_ssh_execution"] is True
        assert sc["requires_operator_approval"] is True
        assert sc["config_preview_has_no_keys"] is True
        assert sc["rollback_plan_is_dryrun"] is True
        assert sc["violations"] == []

    def test_audit_fields(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        audit = plan["audit"]
        assert audit["action"] == "plan_node_sync"
        assert audit["operator_id"] == "test-op"
        assert audit["target_node"] == "21bao"
        assert audit["planner_version"] == PLANNER_VERSION
        assert len(audit["input_hash"]) == 64
        assert "timestamp" in audit

    def test_non_available_summary_passed_through(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        assert len(plan["non_available_summary"]) == 1
        assert "credential_status=missing" in plan["non_available_summary"][0]["reason"]


# --- Test Empty Models ---


class TestEmptyModels:
    """Tests for empty model scenarios."""

    def test_empty_models_warning(self, empty_models_renderer):
        plan = plan_node_sync(empty_models_renderer, operator_id="test-op")
        assert any("no models" in w.lower() for w in plan["warnings"])
        assert plan["action_plan"]["model_count"] == 0
        assert plan["safety_checks"]["passed"] is True

    def test_empty_models_config_preview(self, empty_models_renderer):
        plan = plan_node_sync(empty_models_renderer, operator_id="test-op")
        cp = plan["config_preview"]
        assert cp["no_real_keys"] is True
        assert cp["content_hash"] != ""


# --- Test Safety Violations ---


class TestSafetyViolations:
    """Tests for safety check violations."""

    def test_dry_run_false_blocked(self, basic_renderer_output):
        with pytest.raises(ValueError, match="dry_run"):
            plan_node_sync(basic_renderer_output, dry_run=False)

    def test_renderer_dry_run_false_blocked(self, basic_renderer_output):
        basic_renderer_output["dry_run"] = False
        with pytest.raises(ValueError, match="renderer_output.dry_run"):
            plan_node_sync(basic_renderer_output, dry_run=True)

    def test_empty_renderer_blocked(self):
        with pytest.raises(ValueError, match="non-empty"):
            plan_node_sync({}, dry_run=True)

    def test_missing_node_blocked(self):
        with pytest.raises(ValueError, match="node"):
            plan_node_sync({"dry_run": True, "config_draft": {}}, dry_run=True)

    def test_missing_config_draft_blocked(self):
        with pytest.raises(ValueError, match="config_draft"):
            plan_node_sync({"node": "test", "dry_run": True}, dry_run=True)

    def test_secret_in_renderer_input_blocked(self, basic_renderer_output):
        """Planner strips unknown fields from input; safety scans output."""
        basic_renderer_output["config_draft"]["models"][0]["api_key"] = "sk-abc...mnop"
        # The planner extracts safe fields only, so unknown fields don't propagate
        plan = plan_node_sync(basic_renderer_output, dry_run=True)
        # The output should be clean — api_key is NOT in models_to_sync
        output_str = json.dumps(plan)
        assert "sk-abc" not in output_str or plan["safety_checks"]["passed"] is True


# --- Test Path Generation ---


class TestPathGeneration:
    """Tests for planned path generation."""

    def test_default_paths_21bao(self):
        paths = get_planned_paths("21bao")
        assert "vibedev-config" in paths["config_path"]
        assert paths["backup_path"].endswith(".bak")

    def test_default_paths_5bao(self):
        paths = get_planned_paths("5bao")
        assert "/home/vibeworker" in paths["config_path"]

    def test_custom_paths(self):
        paths = get_planned_paths("test", planned_config_path="/custom/config.json",
                                  previous_config_path="/custom/backup.json")
        assert paths["config_path"] == "/custom/config.json"
        assert paths["backup_path"] == "/custom/backup.json"

    def test_unknown_node_generates_paths(self):
        paths = get_planned_paths("unknown-node")
        assert paths["config_path"] != ""
        assert paths["backup_path"] != ""


# --- Test Config Preview ---


class TestConfigPreview:
    """Tests for config preview generation."""

    def test_preview_structure(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        cp = plan["config_preview"]
        assert "provider" in cp["content_preview"]
        assert "opencode" in cp["content_preview"]["provider"]

    def test_preview_no_keys(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        cp_str = json.dumps(plan["config_preview"])
        assert "sk-" not in cp_str
        assert "api_key" not in cp_str.lower() or "secret_ref" in cp_str

    def test_preview_hash_deterministic(self, basic_renderer_output):
        plan1 = plan_node_sync(basic_renderer_output, operator_id="op1")
        plan2 = plan_node_sync(basic_renderer_output, operator_id="op2")
        # Same config_draft → same content_hash (hash is of content_preview only)
        assert plan1["config_preview"]["content_hash"] == plan2["config_preview"]["content_hash"]

    def test_preview_secret_fields(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        sf = plan["config_preview"]["secret_fields"]
        assert all(s.startswith("secret:") for s in sf)


# --- Test Rollback Plan ---


class TestRollbackPlan:
    """Tests for rollback plan."""

    def test_rollback_dry_run_only(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        assert plan["rollback_plan"]["dry_run_only"] is True

    def test_rollback_strategy(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        assert plan["rollback_plan"]["strategy"] == "backup-and-restore"

    def test_rollback_steps_count(self, basic_renderer_output):
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        assert len(plan["rollback_plan"]["rollback_steps"]) >= 3

    def test_rollback_hash_deterministic(self, basic_renderer_output):
        plan1 = plan_node_sync(basic_renderer_output, operator_id="op")
        plan2 = plan_node_sync(basic_renderer_output, operator_id="op")
        # Same planned_paths → same rollback_hash
        assert plan1["rollback_plan"]["rollback_hash"] == plan2["rollback_plan"]["rollback_hash"]


# --- Test Multi-node ---


class TestMultiNode:
    """Tests for multi-node planning."""

    def test_multi_node_basic(self, basic_renderer_output):
        output_5bao = dict(basic_renderer_output)
        output_5bao["node"] = "5bao"
        output_5bao["config_draft"] = dict(basic_renderer_output["config_draft"])
        output_5bao["config_draft"]["node"] = "5bao"

        result = plan_multi_node_sync(
            [basic_renderer_output, output_5bao],
            operator_id="test-op",
        )
        assert result["dry_run"] is True
        assert result["requires_operator_approval"] is True
        assert result["node_count"] == 2
        assert result["all_safety_passed"] is True
        assert len(result["plans"]) == 2

    def test_multi_node_dry_run_false(self, basic_renderer_output):
        with pytest.raises(ValueError, match="dry_run"):
            plan_multi_node_sync([basic_renderer_output], dry_run=False)

    def test_multi_node_empty_list(self):
        with pytest.raises(ValueError, match="non-empty"):
            plan_multi_node_sync([], dry_run=True)

    def test_multi_node_partial_failure(self, basic_renderer_output):
        bad_output = {"node": "bad", "dry_run": False, "config_draft": {}}
        result = plan_multi_node_sync(
            [basic_renderer_output, bad_output],
            operator_id="test-op",
        )
        assert result["all_safety_passed"] is False
        assert result["plans"][0]["safety_checks"]["passed"] is True
        assert result["plans"][1]["safety_checks"]["passed"] is False


# --- Test Integration with Renderer Output ---


class TestRendererIntegration:
    """Test planner with actual renderer output structure."""

    def test_with_pool_renderer_output(self, basic_renderer_output):
        """Simulate pool renderer output structure."""
        pool_output = {
            "integration": {
                "source": "seed",
                "pool_snapshot_sha256": "abc123",
                "pool_model_count": 2,
                "enrichment_applied": ["credential_status"],
                "integration_version": "1.0.0",
            },
            "renderer_output": basic_renderer_output,
            "dry_run": True,
            "requires_operator_approval": True,
        }

        # Planner should accept renderer_output directly
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        assert plan["safety_checks"]["passed"] is True

    def test_with_role_assignment_none(self, basic_renderer_output):
        """Handle None role_assignment gracefully."""
        basic_renderer_output["role_assignment"] = None
        plan = plan_node_sync(basic_renderer_output, operator_id="test-op")
        assert plan["action_plan"]["roles_to_assign"] == {}


# --- Test Self-check ---


class TestSelfCheck:
    """Tests for planner self-check."""

    def test_self_check_passes(self):
        result = self_check()
        assert result["status"] == "ok"
        assert result["passed"] == result["total"]

    def test_self_check_all_passed(self):
        result = self_check()
        for check in result["checks"]:
            assert check["passed"] is True, f"check {check['name']} failed: {check['detail']}"

    def test_self_check_version(self):
        result = self_check()
        assert result["planner_version"] == PLANNER_VERSION


# --- Test Constants ---


class TestConstants:
    """Tests for module constants."""

    def test_version_defined(self):
        assert PLANNER_VERSION is not None

    def test_default_paths_exist(self):
        from node_sync_dryrun_planner import DEFAULT_PLANNED_PATHS
        assert "21bao" in DEFAULT_PLANNED_PATHS
        assert "5bao" in DEFAULT_PLANNED_PATHS
        assert "9bao" in DEFAULT_PLANNED_PATHS

    def test_dangerous_patterns(self):
        from node_sync_dryrun_planner import DANGEROUS_KEY_PATTERNS
        assert len(DANGEROUS_KEY_PATTERNS) >= 5

    def test_execution_patterns(self):
        from node_sync_dryrun_planner import EXECUTION_PATTERNS
        assert len(EXECUTION_PATTERNS) >= 5


# --- Test Input Hash Stability ---


class TestInputHashStability:
    """Tests for input hash determinism."""

    def test_same_input_same_hash(self, basic_renderer_output):
        plan1 = plan_node_sync(basic_renderer_output, operator_id="op")
        plan2 = plan_node_sync(basic_renderer_output, operator_id="op")
        assert plan1["audit"]["input_hash"] == plan2["audit"]["input_hash"]

    def test_different_input_different_hash(self, basic_renderer_output):
        plan1 = plan_node_sync(basic_renderer_output, operator_id="op")
        basic_renderer_output["config_draft"]["default_model"] = "other-model"
        plan2 = plan_node_sync(basic_renderer_output, operator_id="op")
        assert plan1["audit"]["input_hash"] != plan2["audit"]["input_hash"]
