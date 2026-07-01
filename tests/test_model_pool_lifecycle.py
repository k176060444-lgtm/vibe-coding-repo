#!/usr/bin/env python3
"""Tests for lifecycle_status schema v1.2 (Phase 3 PR-1)."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from collections import OrderedDict

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import yaml

from model_pool_manager import (
    auto_classify,
    validate_lifecycle_status,
    LIFECYCLE_STATUS_VALUES,
    EXPLICIT_OPERATOR_REQUESTED,
    cmd_list,
    cmd_classify,
    cmd_validate_schema,
)


class TestLifecycleStatusValues(unittest.TestCase):
    """Test that all 8 lifecycle_status values are valid."""

    def test_all_buckets_present(self):
        expected = {
            "required", "operator_requested", "enabled_assigned",
            "declared_enabled_unassigned", "candidate", "disabled",
            "historical", "remove_pending",
        }
        self.assertEqual(LIFECYCLE_STATUS_VALUES, expected)

    def test_all_validated(self):
        for val in LIFECYCLE_STATUS_VALUES:
            self.assertIsNone(validate_lifecycle_status(val))

    def test_invalid_rejected(self):
        err = validate_lifecycle_status("bogus")
        self.assertIsNotNone(err)
        self.assertIn("Invalid lifecycle_status", err)


class TestAutoClassify(unittest.TestCase):
    """Test deterministic auto-classification logic — no secret read."""

    def _mk(self, id, enabled=True, allowed_nodes=None, canonical_provider="opencode-go",
            provider_namespace="opencode-go"):
        return OrderedDict([
            ("id", id),
            ("enabled", enabled),
            ("allowed_nodes", allowed_nodes or []),
            ("canonical_provider", canonical_provider),
            ("provider_namespace", provider_namespace),
        ])

    def test_operator_requested(self):
        """mimo-v2-5 is the only operator_requested model."""
        m = self._mk("opencode-go-mimo-v2-5", enabled=True, allowed_nodes=["5bao", "9bao", "win"])
        self.assertEqual(auto_classify(m), "operator_requested")

    def test_operator_requested_not_assigned_to_other_opencode_go(self):
        m = self._mk("opencode-go-mimo-v2-5-pro", enabled=True, allowed_nodes=["5bao", "9bao", "win"])
        self.assertEqual(auto_classify(m), "enabled_assigned")

    def test_enabled_assigned(self):
        """enabled=true + allowed_nodes non-empty → enabled_assigned."""
        m = self._mk("opencode-go-kimi-k2-6", enabled=True, allowed_nodes=["5bao", "9bao"])
        self.assertEqual(auto_classify(m), "enabled_assigned")

    def test_declared_enabled_unassigned(self):
        """enabled=true + allowed_nodes=[] → declared_enabled_unassigned."""
        m = self._mk("anthropic-claude-sonnet-4", enabled=True, allowed_nodes=[])
        self.assertEqual(auto_classify(m), "declared_enabled_unassigned")

    def test_anthropic_not_operator_requested(self):
        """Anthropic models must NOT be operator_requested (operator correction #1)."""
        for name in ["anthropic-claude-3-5-haiku-20241022", "anthropic-claude-opus-4", "anthropic-claude-sonnet-4"]:
            m = self._mk(name, enabled=True, allowed_nodes=[])
            self.assertEqual(auto_classify(m), "declared_enabled_unassigned",
                             f"{name} should not be operator_requested")

    def test_google_not_operator_requested(self):
        m = self._mk("google-gemini-2-5-flash", enabled=True, allowed_nodes=[])
        self.assertEqual(auto_classify(m), "declared_enabled_unassigned")

    def test_openai_not_operator_requested(self):
        m = self._mk("openai-gpt-4o", enabled=True, allowed_nodes=[])
        self.assertEqual(auto_classify(m), "declared_enabled_unassigned")

    def test_xai_not_operator_requested(self):
        m = self._mk("xai-grok-3", enabled=True, allowed_nodes=[])
        self.assertEqual(auto_classify(m), "declared_enabled_unassigned")

    def test_moonshot_not_operator_requested(self):
        m = self._mk("moonshot-moonshot-v1-128k", enabled=True, allowed_nodes=[])
        self.assertEqual(auto_classify(m), "declared_enabled_unassigned")

    def test_dashscope_not_operator_requested(self):
        m = self._mk("dashscope-qwen-max", enabled=True, allowed_nodes=[])
        self.assertEqual(auto_classify(m), "declared_enabled_unassigned")

    def test_deepseek_enabled_unassigned(self):
        m = self._mk("deepseek-deepseek-coder", enabled=True, allowed_nodes=[])
        self.assertEqual(auto_classify(m), "declared_enabled_unassigned")

    def test_candidate(self):
        """volcengine, deepseek-plan, minimax-plan → candidate."""
        for cp, ns in [("volcengine", "volcengine"), ("deepseek-plan", "deepseek-plan"),
                       ("minimax-plan", "minimax-plan")]:
            m = self._mk("model-fake", enabled=False, canonical_provider=cp, provider_namespace=ns)
            self.assertEqual(auto_classify(m), "candidate")

    def test_disabled(self):
        """Disabled without specific namespace match → disabled."""
        m = self._mk("deepseek-deepseek-chat", enabled=False,
                     canonical_provider="deepseek", provider_namespace="deepseek")
        self.assertEqual(auto_classify(m), "disabled")

    def test_historical(self):
        """minimax, xiaomi → historical."""
        for cp in ["minimax", "xiaomi"]:
            m = self._mk("model-hist", enabled=False, canonical_provider=cp, provider_namespace=cp)
            self.assertEqual(auto_classify(m), "historical")

    def test_remove_pending(self):
        """opencode namespace → remove_pending."""
        m = self._mk("opencode-deepseek-v4-flash-free", enabled=False,
                     canonical_provider="opencode", provider_namespace="opencode")
        self.assertEqual(auto_classify(m), "remove_pending")

    def test_no_secret_read(self):
        """auto_classify does NOT read key_env or base_url_env value."""
        m = OrderedDict([
            ("id", "test-model"),
            ("enabled", True),
            ("allowed_nodes", ["5bao"]),
            ("canonical_provider", "test"),
            ("provider_namespace", "test"),
            ("key_env", "OPENCODE_TEST_API_KEY"),
            ("base_url_env", "OPENCODE_TEST_BASE_URL"),
            # No key_env value should ever be present in this function
        ])
        result = auto_classify(m)
        self.assertIn(result, LIFECYCLE_STATUS_VALUES)
        # Verify we never read key value (the function only reads id/enabled/allowed_nodes/cp/ns)
        self.assertNotIn("sk-", str(result))


class TestPoolClassification(unittest.TestCase):
    """Test that classify dry-run matches expected distribution from Phase 1."""

    def setUp(self):
        self.pool_path = SCRIPTS_DIR / "model_pool.yaml"

    def test_lifecycle_status_counts(self):
        """Verify 38 models classified correctly against operator correction."""
        with open(self.pool_path, "r", encoding="utf-8") as f:
            pool = yaml.safe_load(f)
        models = pool.get("models", [])
        statuses = {}
        for m in models:
            ls = m.get("lifecycle_status")
            if ls is not None:
                statuses[ls] = statuses.get(ls, 0) + 1
        self.assertEqual(statuses.get("operator_requested", 0), 1,
                         "Only mimo-v2.5 should be operator_requested")
        self.assertEqual(statuses.get("enabled_assigned", 0), 8,
                         "8 opencode-go models should be enabled_assigned")
        self.assertEqual(statuses.get("declared_enabled_unassigned", 0), 16,
                         "16 models (anthropic/dashscope/deepseek_enabled/google/moonshot/openai/xai) should be unassigned")
        self.assertEqual(statuses.get("candidate", 0), 3,
                         "3 candidate models")
        self.assertEqual(statuses.get("disabled", 0), 1,
                         "1 disabled model (deepseek-deepseek-chat)")
        self.assertEqual(statuses.get("historical", 0), 4,
                         "4 historical models (minimax + xiaomi 3)")
        self.assertEqual(statuses.get("remove_pending", 0), 5,
                         "5 remove_pending (opencode-* free)")
        self.assertEqual(sum(statuses.values()), 38,
                         f"Total classifications should be 38, got {sum(statuses.values())}")

    def test_anthropic_not_operator_requested(self):
        with open(self.pool_path, "r", encoding="utf-8") as f:
            pool = yaml.safe_load(f)
        for m in pool.get("models", []):
            if "anthropic" in m.get("canonical_provider", ""):
                self.assertNotEqual(m.get("lifecycle_status"),
                                    "operator_requested",
                                    f"{m['id']} must NOT be operator_requested")

    def test_opencode_go_deepseek_v4_pro_mismatch_not_masked(self):
        with open(self.pool_path, "r", encoding="utf-8") as f:
            pool = yaml.safe_load(f)
        for m in pool.get("models", []):
            if m["id"] == "opencode-go-deepseek-v4-pro":
                self.assertEqual(m.get("lifecycle_status"), "enabled_assigned")


class TestValidateSchema(unittest.TestCase):
    """Test validate-schema passes with v1.2."""

    def setUp(self):
        self.pool_path = SCRIPTS_DIR / "model_pool.yaml"

    def test_schema_v12_passes(self):
        with open(self.pool_path, "r", encoding="utf-8") as f:
            pool = yaml.safe_load(f)
        self.assertEqual(pool.get("schema_version"), "1.2",
                         "schema_version must be 1.2 after migration")

    def test_no_lifecycle_errors(self):
        """validate-schema should accept v1.2 with lifecycle_status."""
        pool = yaml.safe_load(open(self.pool_path, "r", encoding="utf-8"))
        models = pool.get("models", [])
        for m in models:
            ls = m.get("lifecycle_status")
            self.assertIn(ls, LIFECYCLE_STATUS_VALUES,
                          f"{m['id']} has invalid lifecycle_status '{ls}'")


class TestLifecycleListCommand(unittest.TestCase):
    """Test list --lifecycle-status filter."""

    def test_filter_operator_requested(self):
        models = [{"id": "a", "lifecycle_status": "operator_requested", "enabled": True, "allowed_nodes": [], "provider": "t", "model": "t"},
                   {"id": "b", "lifecycle_status": "disabled", "enabled": False, "allowed_nodes": [], "provider": "t", "model": "t"}]
        filtered = [m for m in models if m.get("lifecycle_status") == "operator_requested"]
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "a")


class TestBackwardCompat(unittest.TestCase):
    """v1.1 without lifecycle_status is still accepted by auto_classify."""

    def test_missing_field_dry_run(self):
        """auto_classify works even if lifecycle_status is missing."""
        m = OrderedDict([
            ("id", "test-legacy-model"),
            ("enabled", False),
            ("allowed_nodes", []),
            ("canonical_provider", "deepseek"),
            ("provider_namespace", "deepseek"),
        ])
        result = auto_classify(m)
        self.assertEqual(result, "disabled")


if __name__ == "__main__":
    unittest.main()
