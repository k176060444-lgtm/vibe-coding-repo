#!/usr/bin/env python3
"""Tests for vibe_model_resolver.py — call-time central pool resolution."""

import json
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import yaml

from vibe_model_resolver import (
    resolve_model,
    self_check,
    VALID_NODES,
    ALLOWED_LIFECYCLE_STATUSES,
    BLOCKED_LIFECYCLE_REASONS,
)


# Known data from model_pool.yaml + node_model_capability.yaml
KNOWN_OPERATOR_REQUESTED_ID = "opencode-go-mimo-v2-5"
KNOWN_OPERATOR_REQUESTED_ALIAS = "opencode-mimo"
KNOWN_ENABLED_ASSIGNED_ALIAS = "opencode-glm52"
KNOWN_ENABLED_ASSIGNED_ID = "opencode-go-glm-5-2"
KNOWN_DEU_ALIAS = "haiku"
KNOWN_DEU_ID = "anthropic-claude-3-5-haiku-20241022"
KNOWN_DISABLED_ID = "deepseek-deepseek-chat"
KNOWN_REMOVEPEND_ID = "opencode-big-pickle"
KNOWN_HISTORICAL_ID = "xiaomi-mimo-v2-5-payg"
KNOWN_CANDIDATE_ID = "volcengine-doubao-1-5-pro-256k"


class TestSelfCheck(unittest.TestCase):
    """Resolver self-check must pass."""

    def test_self_check_passes(self):
        result = self_check()
        self.assertEqual(result["status"], "PASS",
                         f"Self-check failed: {result}")
        self.assertGreaterEqual(result["checks"][0]["detail"], "38 models")


class TestResolveByModelID(unittest.TestCase):
    """Test resolution by exact model_id."""

    def test_operator_requested_by_id(self):
        r = resolve_model(KNOWN_OPERATOR_REQUESTED_ID, "21bao")
        self.assertTrue(r["resolved"])
        self.assertEqual(r["resolved_model_id"], KNOWN_OPERATOR_REQUESTED_ID)
        self.assertEqual(r["resolved_by"], "model_id")
        self.assertEqual(r["lifecycle_status"], "operator_requested")
        self.assertIsNone(r["blocked_reason"])

    def test_enabled_assigned_by_id(self):
        r = resolve_model(KNOWN_ENABLED_ASSIGNED_ID, "5bao")
        self.assertTrue(r["resolved"])
        self.assertEqual(r["resolved_model_id"], KNOWN_ENABLED_ASSIGNED_ID)
        self.assertEqual(r["resolved_by"], "model_id")
        self.assertEqual(r["lifecycle_status"], "enabled_assigned")
        self.assertIsNone(r["blocked_reason"])

    def test_operator_requested_on_all_nodes(self):
        for node in VALID_NODES:
            r = resolve_model(KNOWN_OPERATOR_REQUESTED_ID, node)
            self.assertTrue(r["resolved"], f"Failed on node={node}: {r.get('blocked_reason')}")
            self.assertEqual(r["node"], node)


class TestResolveByAlias(unittest.TestCase):
    """Test resolution by alias from the model's alias list."""

    def test_enabled_assigned_by_alias(self):
        r = resolve_model(KNOWN_ENABLED_ASSIGNED_ALIAS, "21bao")
        self.assertTrue(r["resolved"])
        self.assertEqual(r["resolved_model_id"], KNOWN_ENABLED_ASSIGNED_ID)
        self.assertEqual(r["resolved_by"], "alias")

    def test_operator_requested_by_alias(self):
        r = resolve_model(KNOWN_OPERATOR_REQUESTED_ALIAS, "5bao")
        self.assertTrue(r["resolved"])
        self.assertEqual(r["resolved_model_id"], KNOWN_OPERATOR_REQUESTED_ID)
        self.assertEqual(r["resolved_by"], "alias")


class TestResolveByPrimaryAlias(unittest.TestCase):
    """Test resolution by primary_alias (haiku → anthropic)."""

    def test_primary_alias_found(self):
        r = resolve_model(KNOWN_DEU_ALIAS, "21bao")
        # Should find it, but block on lifecycle_status
        self.assertFalse(r["resolved"])
        self.assertEqual(r["resolved_by"], "blocked")
        self.assertIn("declared_enabled_unassigned", r["blocked_reason"])


class TestFailClosed(unittest.TestCase):
    """Test fail-closed conditions."""

    def test_declared_enabled_unassigned_blocked(self):
        r = resolve_model(KNOWN_DEU_ID, "21bao")
        self.assertFalse(r["resolved"])
        self.assertEqual(r["lifecycle_status"], "declared_enabled_unassigned")
        self.assertIn("D-B decision pending", r["blocked_reason"])

    def test_disabled_blocked(self):
        r = resolve_model(KNOWN_DISABLED_ID, "21bao")
        self.assertFalse(r["resolved"])
        self.assertEqual(r["lifecycle_status"], "disabled")
        self.assertIn("disabled explicitly", r["blocked_reason"])

    def test_remove_pending_blocked(self):
        r = resolve_model(KNOWN_REMOVEPEND_ID, "21bao")
        self.assertFalse(r["resolved"])
        self.assertEqual(r["lifecycle_status"], "remove_pending")
        self.assertIn("pending removal", r["blocked_reason"])

    def test_historical_blocked(self):
        r = resolve_model(KNOWN_HISTORICAL_ID, "21bao")
        self.assertFalse(r["resolved"])
        self.assertEqual(r["lifecycle_status"], "historical")
        self.assertIn("historical/retired", r["blocked_reason"])

    def test_candidate_blocked(self):
        r = resolve_model(KNOWN_CANDIDATE_ID, "21bao")
        self.assertFalse(r["resolved"])
        self.assertEqual(r["lifecycle_status"], "candidate")
        self.assertIn("candidate mode", r["blocked_reason"])

    def test_nonexistent_blocked(self):
        r = resolve_model("nonexistent-model-xyz", "21bao")
        self.assertFalse(r["resolved"])
        self.assertIsNone(r["lifecycle_status"])
        self.assertIn("not found in central pool", r["blocked_reason"])

    def test_empty_ref_blocked(self):
        r = resolve_model("", "21bao")
        self.assertFalse(r["resolved"])
        self.assertIn("non-empty string", r["blocked_reason"])

    def test_invalid_node_blocked(self):
        r = resolve_model(KNOWN_OPERATOR_REQUESTED_ID, "win")
        self.assertFalse(r["resolved"])
        self.assertIn("invalid node", r["blocked_reason"])


class TestNodeConstraint(unittest.TestCase):
    """Test node validation: only 21bao/5bao/9bao allowed."""

    def test_21bao_accepted(self):
        r = resolve_model(KNOWN_OPERATOR_REQUESTED_ID, "21bao")
        self.assertTrue(r["resolved"])

    def test_5bao_accepted(self):
        r = resolve_model(KNOWN_OPERATOR_REQUESTED_ID, "5bao")
        self.assertTrue(r["resolved"])

    def test_9bao_accepted(self):
        r = resolve_model(KNOWN_OPERATOR_REQUESTED_ID, "9bao")
        self.assertTrue(r["resolved"])

    def test_node_10bao_blocked(self):
        r = resolve_model(KNOWN_OPERATOR_REQUESTED_ID, "10bao")
        self.assertFalse(r["resolved"])
        self.assertIn("invalid node", r["blocked_reason"])


class TestAuditSafeFields(unittest.TestCase):
    """Resolution receipt must contain audit-safe fields only."""

    def test_receipt_has_all_fields(self):
        r = resolve_model(KNOWN_OPERATOR_REQUESTED_ID, "21bao")
        self.assertIn("resolution_id", r)
        self.assertIn("requested_alias", r)
        self.assertIn("resolved_model_id", r)
        self.assertIn("node", r)
        self.assertIn("provider_namespace", r)
        self.assertIn("canonical_provider", r)
        self.assertIn("lifecycle_status", r)
        self.assertIn("endpoint_ref", r)
        self.assertIn("secret_ref", r)
        self.assertIn("readiness_states", r)
        self.assertIn("blocked_reason", r)

    def test_no_secret_value(self):
        r = resolve_model(KNOWN_OPERATOR_REQUESTED_ID, "21bao")
        output = json.dumps(r)
        # Only env var NAMES allowed, not values
        self.assertNotIn("sk-", output,
                         "Secret value leaked in resolution receipt")
        # API key value shouldn't appear
        self.assertNotIn("=***", output,
                         "API key value leaked")
        self.assertNotIn("http://", output,
                         "Base URL value leaked")


class TestReadinessStates(unittest.TestCase):
    """Readiness states must come from node_model_capability.yaml."""

    def test_readiness_has_declared_true(self):
        r = resolve_model(KNOWN_OPERATOR_REQUESTED_ID, "21bao")
        self.assertEqual(r["readiness_states"]["declared"], True)

    def test_readiness_has_synced_true(self):
        r = resolve_model(KNOWN_OPERATOR_REQUESTED_ID, "21bao")
        self.assertEqual(r["readiness_states"]["synced"], True)

    def test_readiness_has_approved_unknown(self):
        r = resolve_model(KNOWN_ENABLED_ASSIGNED_ID, "21bao")
        # mimo-v2.5 has operator_approved=true, enabled_assigned has unknown
        self.assertEqual(r["readiness_states"]["operator_approved"], "unknown")


class TestNoWildcardNoSilentFallback(unittest.TestCase):
    """No wildcard/empty/bulk resolution; no silent fallback."""

    def test_wildcard_asterisk_blocked(self):
        r = resolve_model("*", "21bao")
        self.assertFalse(r["resolved"])
        self.assertIsNotNone(r["blocked_reason"])
        self.assertIn("not found in central pool", r["blocked_reason"])

    def test_silent_fallback_blocked(self):
        """Every unresolved model_ref must have a blocked_reason."""
        r = resolve_model("totally-fake-model-007", "5bao")
        self.assertFalse(r["resolved"])
        self.assertIsNotNone(r["blocked_reason"])
        self.assertGreater(len(r["blocked_reason"]), 5)


class TestLifecycleBlockedReasons(unittest.TestCase):
    """All disallowed lifecycle_statuses must have specific blocked reasons."""

    def test_all_blocked_reason_found(self):
        """Every disallowed lifecycle_status has a reason in BLOCKED_LIFECYCLE_REASONS."""
        for ls, reason in BLOCKED_LIFECYCLE_REASONS.items():
            self.assertGreater(len(reason), 10,
                               f"Blocked reason for '{ls}' is too short")


class Test21baoTaxonomy(unittest.TestCase):
    """21bao must not be treated as remote SSH worker."""

    def test_21bao_resolves_normally(self):
        r = resolve_model(KNOWN_OPERATOR_REQUESTED_ID, "21bao")
        self.assertTrue(r["resolved"])
        self.assertEqual(r["node"], "21bao")
        # Should NOT try to SSH; no transport field in receipt
        self.assertNotIn("transport", r)


if __name__ == "__main__":
    unittest.main()
