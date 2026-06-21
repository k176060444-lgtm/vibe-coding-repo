#!/usr/bin/env python3
"""test_role_assignment_gate.py — Tests for V1.21.2 Workflow Role Assignment Gate.

Hard requirements tested:
  1. Missing reviewer blocks coding workflow
  2. High-risk task recommends two reviewers
  3. Tester/checker must be explicit
  4. Main-agent-as-tester requires explicit approval
  5. Assignment matrix includes model/node/provider/cost/reason/call budget
  6. Planned vs actual ledger is produced
  7. Risk classification rules
  8. Operator approval gate
"""

import json
import sys
import os
import unittest

# Ensure scripts directory is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from vibe_role_assignment_gate import (
    classify_risk,
    needs_dual_reviewer,
    get_required_roles,
    create_role_assignment,
    create_assignment_matrix,
    validate_assignment_entry,
    validate_assignment_matrix,
    generate_planned_vs_actual_ledger,
    self_check,
    REQUIRED_ASSIGNMENT_FIELDS,
    VALID_ROLES,
    VALID_FALLBACK_POLICIES,
    DUAL_REVIEWER_TAGS,
)


def _make_valid_low_matrix() -> dict:
    """Create a valid low-risk matrix for reuse."""
    m = create_assignment_matrix("low", task_id="test-low")
    m["assignments"] = [
        create_role_assignment(
            "implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek",
            cost_tag="imp-001", reason="implement feature",
            call_budget=100, fallback_policy="disabled",
        ),
        create_role_assignment(
            "reviewer", "9bao", "opencode/deepseek-v4-pro", "deepseek",
            cost_tag="rev-001", reason="blind review",
            call_budget=50, fallback_policy="disabled",
        ),
        create_role_assignment(
            "checker", "21bao", "opencode/deepseek-v4-pro", "deepseek",
            cost_tag="chk-001", reason="quality check",
            call_budget=30, fallback_policy="disabled",
        ),
    ]
    m["operator_approved"] = True
    m["operator_approval_timestamp"] = "2026-06-21T12:00:00Z"
    return m


def _make_valid_high_matrix() -> dict:
    """Create a valid high-risk matrix for reuse."""
    m = create_assignment_matrix("high", tags=["upstream"], task_id="test-high")
    m["assignments"] = [
        create_role_assignment(
            "implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek",
            cost_tag="imp-001", reason="implement upstream change",
            call_budget=200, fallback_policy="disabled",
        ),
        create_role_assignment(
            "reviewer-1", "9bao", "opencode/deepseek-v4-pro", "deepseek",
            cost_tag="rev1-001", reason="blind review 1",
            call_budget=80, fallback_policy="disabled",
        ),
        create_role_assignment(
            "reviewer-2", "5bao", "opencode/mimo-v2.5-pro", "xiaomi",
            cost_tag="rev2-001", reason="blind review 2 (different model)",
            call_budget=80, fallback_policy="disabled",
        ),
        create_role_assignment(
            "tester-checker", "21bao", "opencode/deepseek-v4-pro", "deepseek",
            cost_tag="test-001", reason="test and quality check",
            call_budget=100, fallback_policy="disabled",
        ),
    ]
    m["operator_approved"] = True
    m["operator_approval_timestamp"] = "2026-06-21T12:00:00Z"
    return m


class TestRiskClassification(unittest.TestCase):
    """Test risk classification rules."""

    def test_low_risk(self):
        self.assertEqual(classify_risk("low"), "low")

    def test_medium_risk(self):
        self.assertEqual(classify_risk("medium"), "medium")

    def test_high_risk(self):
        self.assertEqual(classify_risk("high"), "high")

    def test_critical_risk(self):
        self.assertEqual(classify_risk("critical"), "critical")

    def test_tag_escalation_to_high(self):
        """Requirement: upstream/security/admin tags escalate to high."""
        for tag in ["upstream", "security", "admin", "credential",
                     "command-execution", "permission", "hermes-agent"]:
            result = classify_risk("low", [tag])
            self.assertEqual(result, "high", f"tag '{tag}' should escalate low -> high")

    def test_tag_escalation_preserves_critical(self):
        self.assertEqual(classify_risk("critical", ["upstream"]), "critical")

    def test_no_tags_stays_low(self):
        self.assertEqual(classify_risk("low", []), "low")
        self.assertEqual(classify_risk("low", None), "low")

    def test_unknown_tag_stays_low(self):
        self.assertEqual(classify_risk("low", ["documentation"]), "low")

    def test_needs_dual_reviewer_high(self):
        self.assertTrue(needs_dual_reviewer("high"))

    def test_needs_dual_reviewer_critical(self):
        self.assertTrue(needs_dual_reviewer("critical"))

    def test_needs_dual_reviewer_low(self):
        self.assertFalse(needs_dual_reviewer("low"))

    def test_needs_dual_reviewer_medium(self):
        self.assertFalse(needs_dual_reviewer("medium"))

    def test_needs_dual_reviewer_via_tag(self):
        """Requirement: upstream tag triggers dual reviewer."""
        self.assertTrue(needs_dual_reviewer("low", ["upstream"]))


class TestRequiredRoles(unittest.TestCase):
    """Test required roles by risk level."""

    def test_low_risk_roles(self):
        """Requirement: small low-risk = implementer + reviewer + checker."""
        req = get_required_roles("low")
        self.assertIn("implementer", req["required_roles"])
        self.assertIn("reviewer", req["required_roles"])
        self.assertIn("checker", req["required_roles"])
        self.assertFalse(req["requires_dual_reviewer"])

    def test_medium_risk_roles(self):
        """Requirement: medium = implementer + reviewer + tester/checker."""
        req = get_required_roles("medium")
        self.assertIn("implementer", req["required_roles"])
        self.assertIn("reviewer", req["required_roles"])
        self.assertIn("tester-checker", req["required_roles"])
        self.assertFalse(req["requires_dual_reviewer"])

    def test_high_risk_roles(self):
        """Requirement: high-risk = implementer + reviewer-1 + reviewer-2 + tester-checker."""
        req = get_required_roles("high")
        self.assertIn("implementer", req["required_roles"])
        self.assertIn("reviewer-1", req["required_roles"])
        self.assertIn("reviewer-2", req["required_roles"])
        self.assertIn("tester-checker", req["required_roles"])
        self.assertTrue(req["requires_dual_reviewer"])

    def test_high_risk_optional_docs_helper(self):
        req = get_required_roles("high")
        self.assertIn("docs-helper", req["optional_roles"])

    def test_critical_risk_roles(self):
        req = get_required_roles("critical")
        self.assertTrue(req["requires_dual_reviewer"])
        self.assertIn("reviewer-1", req["required_roles"])
        self.assertIn("reviewer-2", req["required_roles"])

    def test_tag_escalation_changes_roles(self):
        """Requirement: upstream tag escalates low to high, changing required roles."""
        req = get_required_roles("low", ["upstream"])
        self.assertTrue(req["requires_dual_reviewer"])
        self.assertIn("reviewer-1", req["required_roles"])


class TestAssignmentEntryValidation(unittest.TestCase):
    """Test individual assignment entry validation."""

    def test_valid_entry(self):
        entry = create_role_assignment(
            "implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek",
            cost_tag="imp-001", reason="implement", call_budget=100,
        )
        errors = validate_assignment_entry(entry, 0)
        self.assertEqual(errors, [])

    def test_all_required_fields_present(self):
        """Requirement: each assignment has role/node/model/provider/cost/reason/call_budget/fallback."""
        entry = create_role_assignment(
            "implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek",
            cost_tag="imp-001", reason="implement", call_budget=100,
        )
        for field in REQUIRED_ASSIGNMENT_FIELDS:
            self.assertIn(field, entry, f"missing required field: {field}")

    def test_missing_role(self):
        entry = create_role_assignment(
            "implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek",
        )
        del entry["role"]
        errors = validate_assignment_entry(entry, 0)
        self.assertTrue(any("role" in e for e in errors))

    def test_invalid_role(self):
        entry = create_role_assignment(
            "nonexistent", "21bao", "opencode/deepseek-v4-pro", "deepseek",
        )
        errors = validate_assignment_entry(entry, 0)
        self.assertTrue(any("invalid role" in e for e in errors))

    def test_invalid_fallback_policy(self):
        entry = create_role_assignment(
            "implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek",
            fallback_policy="invalid_policy",
        )
        errors = validate_assignment_entry(entry, 0)
        self.assertTrue(any("fallback_policy" in e for e in errors))

    def test_invalid_call_budget_zero(self):
        entry = create_role_assignment(
            "implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek",
            call_budget=0,
        )
        errors = validate_assignment_entry(entry, 0)
        self.assertTrue(any("call_budget" in e for e in errors))

    def test_empty_node(self):
        entry = create_role_assignment(
            "implementer", "", "opencode/deepseek-v4-pro", "deepseek",
        )
        errors = validate_assignment_entry(entry, 0)
        self.assertTrue(any("node" in e for e in errors))

    def test_valid_fallback_policies(self):
        for policy in VALID_FALLBACK_POLICIES:
            entry = create_role_assignment(
                "implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek",
                fallback_policy=policy,
            )
            errors = validate_assignment_entry(entry, 0)
            fb_errors = [e for e in errors if "fallback" in e]
            self.assertEqual(fb_errors, [], f"policy '{policy}' should be valid")


class TestMissingReviewerBlocks(unittest.TestCase):
    """Requirement 1: Missing reviewer blocks coding workflow."""

    def test_no_reviewer_blocks(self):
        m = _make_valid_low_matrix()
        m["assignments"] = [
            create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
            create_role_assignment("checker", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
        ]
        result = validate_assignment_matrix(m)
        self.assertFalse(result["valid"])
        self.assertTrue(any("reviewer" in e.lower() for e in result["errors"]))

    def test_with_reviewer_passes(self):
        m = _make_valid_low_matrix()
        result = validate_assignment_matrix(m)
        reviewer_check = [c for c in result["checks"] if c["name"] == "has_reviewer"]
        self.assertEqual(reviewer_check[0]["result"], "PASS")

    def test_reviewer_1_counts(self):
        m = _make_valid_high_matrix()
        result = validate_assignment_matrix(m)
        reviewer_check = [c for c in result["checks"] if c["name"] == "has_reviewer"]
        self.assertEqual(reviewer_check[0]["result"], "PASS")


class TestHighRiskDualReviewer(unittest.TestCase):
    """Requirement 2: High-risk recommends two independent reviewers."""

    def test_high_risk_two_reviewers_valid(self):
        m = _make_valid_high_matrix()
        result = validate_assignment_matrix(m)
        dual_check = [c for c in result["checks"] if c["name"] == "dual_reviewer"]
        self.assertEqual(dual_check[0]["result"], "PASS")

    def test_high_risk_one_reviewer_blocks(self):
        m = _make_valid_high_matrix()
        m["assignments"] = [
            create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
            create_role_assignment("reviewer", "9bao", "opencode/deepseek-v4-pro", "deepseek"),
            create_role_assignment("tester-checker", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
        ]
        result = validate_assignment_matrix(m)
        self.assertFalse(result["valid"])
        self.assertTrue(any("2 independent reviewers" in e for e in result["errors"]))

    def test_upstream_tag_triggers_dual_reviewer(self):
        m = create_assignment_matrix("low", tags=["upstream"], task_id="test")
        m["assignments"] = [
            create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
            create_role_assignment("reviewer", "9bao", "opencode/deepseek-v4-pro", "deepseek"),
            create_role_assignment("checker", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
        ]
        m["operator_approved"] = True
        m["operator_approval_timestamp"] = "2026-06-21T12:00:00Z"
        result = validate_assignment_matrix(m)
        self.assertFalse(result["valid"])
        self.assertTrue(any("2 independent reviewers" in e for e in result["errors"]))


class TestTesterCheckerExplicit(unittest.TestCase):
    """Requirement 3: Tester/checker must be an explicit role."""

    def test_missing_tester_blocks(self):
        m = _make_valid_low_matrix()
        m["assignments"] = [
            create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
            create_role_assignment("reviewer", "9bao", "opencode/deepseek-v4-pro", "deepseek"),
        ]
        result = validate_assignment_matrix(m)
        self.assertFalse(result["valid"])
        self.assertTrue(any("tester" in e.lower() or "checker" in e.lower()
                          for e in result["errors"]))

    def test_checker_role_valid(self):
        m = _make_valid_low_matrix()
        result = validate_assignment_matrix(m)
        tester_check = [c for c in result["checks"] if c["name"] == "tester_explicit"]
        self.assertEqual(tester_check[0]["result"], "PASS")

    def test_tester_role_valid(self):
        m = _make_valid_low_matrix()
        m["assignments"][2] = create_role_assignment(
            "tester", "21bao", "opencode/deepseek-v4-pro", "deepseek",
            cost_tag="test-001", reason="test",
        )
        result = validate_assignment_matrix(m)
        tester_check = [c for c in result["checks"] if c["name"] == "tester_explicit"]
        self.assertEqual(tester_check[0]["result"], "PASS")

    def test_tester_checker_combined_valid(self):
        m = _make_valid_low_matrix()
        m["assignments"][2] = create_role_assignment(
            "tester-checker", "21bao", "opencode/deepseek-v4-pro", "deepseek",
            cost_tag="tc-001", reason="test and check",
        )
        result = validate_assignment_matrix(m)
        tester_check = [c for c in result["checks"] if c["name"] == "tester_explicit"]
        self.assertEqual(tester_check[0]["result"], "PASS")


class TestMainAgentAsTester(unittest.TestCase):
    """Requirement 4: Main-agent-as-tester requires explicit approval."""

    def test_main_agent_tester_blocks_without_approval(self):
        m = _make_valid_low_matrix()
        m["assignments"][2] = create_role_assignment(
            "tester-checker", "main-agent", "hermes/mimo-v2.5-pro", "xiaomi",
            cost_tag="main-test", reason="main agent testing",
        )
        m["main_agent_as_tester_approved"] = False
        result = validate_assignment_matrix(m)
        self.assertFalse(result["valid"])
        self.assertTrue(any("main agent" in e.lower() for e in result["errors"]))

    def test_main_agent_tester_passes_with_approval(self):
        m = _make_valid_low_matrix()
        m["assignments"][2] = create_role_assignment(
            "tester-checker", "main-agent", "hermes/mimo-v2.5-pro", "xiaomi",
            cost_tag="main-test", reason="main agent testing",
        )
        m["main_agent_as_tester_approved"] = True
        result = validate_assignment_matrix(m)
        tester_check = [c for c in result["checks"] if c["name"] == "main_agent_as_tester"]
        self.assertEqual(tester_check[0]["result"], "PASS")

    def test_main_agent_tester_role_blocks(self):
        m = _make_valid_low_matrix()
        m["assignments"][2] = create_role_assignment(
            "tester", "main-agent", "hermes/mimo-v2.5-pro", "xiaomi",
            cost_tag="main-test", reason="main agent testing",
        )
        result = validate_assignment_matrix(m)
        self.assertFalse(result["valid"])


class TestAssignmentMatrixFields(unittest.TestCase):
    """Requirement 5: Each assignment has model/node/provider/cost/reason/call_budget."""

    def test_create_role_assignment_has_all_fields(self):
        entry = create_role_assignment(
            "implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek",
            cost_tag="imp-001", reason="implement feature", call_budget=100,
            fallback_policy="disabled",
        )
        self.assertEqual(entry["role"], "implementer")
        self.assertEqual(entry["node"], "21bao")
        self.assertEqual(entry["model"], "opencode/deepseek-v4-pro")
        self.assertEqual(entry["provider"], "deepseek")
        self.assertEqual(entry["cost_tag"], "imp-001")
        self.assertEqual(entry["reason"], "implement feature")
        self.assertEqual(entry["call_budget"], 100)
        self.assertEqual(entry["fallback_policy"], "disabled")

    def test_create_assignment_matrix_has_required_roles(self):
        m = create_assignment_matrix("low")
        self.assertIn("required_roles", m)
        self.assertIn("optional_roles", m)

    def test_matrix_has_task_metadata(self):
        m = create_assignment_matrix("low", task_id="wo-test-001", task_type="coding")
        self.assertEqual(m["task_id"], "wo-test-001")
        self.assertEqual(m["task_type"], "coding")


class TestOperatorApprovalGate(unittest.TestCase):
    """Requirement 6: Operator must approve before execution."""

    def test_unapproved_matrix_blocks(self):
        m = _make_valid_low_matrix()
        m["operator_approved"] = False
        result = validate_assignment_matrix(m)
        self.assertFalse(result["valid"])
        self.assertTrue(any("operator" in e.lower() and "approved" in e.lower()
                          for e in result["errors"]))

    def test_approved_matrix_passes(self):
        m = _make_valid_low_matrix()
        result = validate_assignment_matrix(m)
        op_check = [c for c in result["checks"] if c["name"] == "operator_approved"]
        self.assertEqual(op_check[0]["result"], "PASS")


class TestPlannedVsActualLedger(unittest.TestCase):
    """Requirement 7: Planned vs actual ledger is produced."""

    def test_ledger_structure(self):
        m = _make_valid_low_matrix()
        actual = [
            {"role": "implementer", "node": "21bao", "model": "opencode/deepseek-v4-pro",
             "provider": "deepseek", "call_count": 5, "duration": "30s", "exit_code": 0,
             "final_status": "PASS"},
            {"role": "reviewer", "node": "9bao", "model": "opencode/deepseek-v4-pro",
             "provider": "deepseek", "call_count": 2, "duration": "10s", "exit_code": 0,
             "final_status": "PASS"},
            {"role": "checker", "node": "21bao", "model": "opencode/deepseek-v4-pro",
             "provider": "deepseek", "call_count": 1, "duration": "5s", "exit_code": 0,
             "final_status": "PASS"},
        ]
        ledger = generate_planned_vs_actual_ledger(m, actual)
        self.assertIn("planned_roles", ledger)
        self.assertIn("actual_roles", ledger)
        self.assertIn("discrepancies", ledger)
        self.assertIn("ledger", ledger)
        self.assertIn("missing_actual", ledger)
        self.assertIn("extra_actual", ledger)

    def test_ledger_entries_match_planned(self):
        m = _make_valid_low_matrix()
        actual = [
            {"role": "implementer", "node": "21bao", "model": "opencode/deepseek-v4-pro",
             "provider": "deepseek", "call_count": 5, "duration": "30s", "exit_code": 0,
             "final_status": "PASS"},
            {"role": "reviewer", "node": "9bao", "model": "opencode/deepseek-v4-pro",
             "provider": "deepseek", "call_count": 2, "duration": "10s", "exit_code": 0,
             "final_status": "PASS"},
            {"role": "checker", "node": "21bao", "model": "opencode/deepseek-v4-pro",
             "provider": "deepseek", "call_count": 1, "duration": "5s", "exit_code": 0,
             "final_status": "PASS"},
        ]
        ledger = generate_planned_vs_actual_ledger(m, actual)
        self.assertEqual(len(ledger["discrepancies"]), 0)
        for entry in ledger["ledger"]:
            self.assertTrue(entry["model_match"])
            self.assertTrue(entry["node_match"])
            self.assertTrue(entry["provider_match"])

    def test_ledger_detects_model_mismatch(self):
        m = _make_valid_low_matrix()
        actual = [
            {"role": "implementer", "node": "21bao", "model": "opencode/mimo-v2.5-pro",
             "provider": "xiaomi", "call_count": 5, "duration": "30s", "exit_code": 0,
             "final_status": "PASS"},
            {"role": "reviewer", "node": "9bao", "model": "opencode/deepseek-v4-pro",
             "provider": "deepseek", "call_count": 2, "duration": "10s", "exit_code": 0,
             "final_status": "PASS"},
            {"role": "checker", "node": "21bao", "model": "opencode/deepseek-v4-pro",
             "provider": "deepseek", "call_count": 1, "duration": "5s", "exit_code": 0,
             "final_status": "PASS"},
        ]
        ledger = generate_planned_vs_actual_ledger(m, actual)
        self.assertTrue(len(ledger["discrepancies"]) > 0)
        impl_entry = [e for e in ledger["ledger"] if e["role"] == "implementer"][0]
        self.assertFalse(impl_entry["model_match"])

    def test_ledger_detects_missing_actual(self):
        m = _make_valid_low_matrix()
        actual = [
            {"role": "implementer", "node": "21bao", "model": "opencode/deepseek-v4-pro",
             "provider": "deepseek", "call_count": 5, "duration": "30s", "exit_code": 0,
             "final_status": "PASS"},
        ]
        ledger = generate_planned_vs_actual_ledger(m, actual)
        self.assertIn("reviewer", ledger["missing_actual"])
        self.assertIn("checker", ledger["missing_actual"])


class TestMatrixCreation(unittest.TestCase):
    """Test matrix creation helpers."""

    def test_create_assignment_matrix_low(self):
        m = create_assignment_matrix("low", task_id="test-001")
        self.assertEqual(m["risk_level"], "low")
        self.assertEqual(m["effective_risk"], "low")
        self.assertFalse(m["requires_dual_reviewer"])
        self.assertFalse(m["operator_approved"])
        self.assertEqual(m["assignments"], [])

    def test_create_assignment_matrix_high(self):
        m = create_assignment_matrix("high", tags=["upstream"])
        self.assertTrue(m["requires_dual_reviewer"])

    def test_create_assignment_matrix_with_tags(self):
        m = create_assignment_matrix("low", tags=["security", "admin"])
        self.assertIn("security", m["tags"])
        self.assertIn("admin", m["tags"])
        self.assertTrue(m["requires_dual_reviewer"])  # escalated to high


class TestSelfCheck(unittest.TestCase):
    """Test the built-in self-check."""

    def test_self_check_passes(self):
        result = self_check()
        self.assertTrue(result["passed"], f"Self-check failed: {[c for c in result['checks'] if not c['passed']]}")
        self.assertEqual(result["failed_count"], 0)

    def test_self_check_has_all_checks(self):
        result = self_check()
        self.assertTrue(result["total_tests"] >= 30, f"Expected >=30 checks, got {result['total_tests']}")

    def test_self_check_version(self):
        result = self_check()
        self.assertEqual(result["version"], "1.0.0")


class TestFullValidMatrix(unittest.TestCase):
    """Integration: full valid matrix passes all checks."""

    def test_low_risk_full(self):
        m = _make_valid_low_matrix()
        result = validate_assignment_matrix(m)
        self.assertTrue(result["valid"], f"Errors: {result['errors']}")
        self.assertEqual(result["verdict"], "ALLOW")
        self.assertEqual(result["summary"]["block"], 0)

    def test_high_risk_full(self):
        m = _make_valid_high_matrix()
        result = validate_assignment_matrix(m)
        self.assertTrue(result["valid"], f"Errors: {result['errors']}")
        self.assertEqual(result["verdict"], "ALLOW")
        self.assertEqual(result["summary"]["block"], 0)

    def test_medium_risk_full(self):
        m = create_assignment_matrix("medium", task_id="test-med")
        m["assignments"] = [
            create_role_assignment(
                "implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek",
                cost_tag="imp-001", reason="implement",
                call_budget=100, fallback_policy="disabled",
            ),
            create_role_assignment(
                "reviewer", "9bao", "opencode/deepseek-v4-pro", "deepseek",
                cost_tag="rev-001", reason="review",
                call_budget=50, fallback_policy="disabled",
            ),
            create_role_assignment(
                "tester-checker", "21bao", "opencode/deepseek-v4-pro", "deepseek",
                cost_tag="tc-001", reason="test and check",
                call_budget=80, fallback_policy="disabled",
            ),
        ]
        m["operator_approved"] = True
        m["operator_approval_timestamp"] = "2026-06-21T12:00:00Z"
        result = validate_assignment_matrix(m)
        self.assertTrue(result["valid"], f"Errors: {result['errors']}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
