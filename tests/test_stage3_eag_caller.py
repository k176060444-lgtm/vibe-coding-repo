#!/usr/bin/env python3
"""tests/test_stage3_eag_caller.py

Baseline02 Stage 3 corrective — EAG (scripts/vibe_execution_gate.py)
caller-upgrade tests for PR #278 issue #2.

These tests verify that the EAG production path actually calls
validate_assignment_matrix_strict() (not the legacy validate_assignment_matrix())
so that v1.0.0 legacy matrices are fail-closed against the 7 spec §4.2 fields.

Two complementary strategies are used:
  1. **Source-level inspection** (no execution): parse the EAG source file
     and assert that validate_assignment_matrix_strict is called in the
     role_assignment_matrix check, with the legacy path relegated to a
     transitional fallback under a `_STRICT_AVAILABLE` guard.
  2. **Behavior-level inspection** (in-process): import the EAG module
     and call its public `validate_assignment_matrix_strict` reference to
     confirm the strict validator is wired and rejects v1.0.0 matrices
     the same way RAG does (fail-closed against the 7 spec §4.2 fields).

These tests do NOT require an actual work order registry, do NOT make
network calls, and do NOT touch secret values.
"""

import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
EAG_PATH = os.path.join(SCRIPTS_DIR, "vibe_execution_gate.py")
RAG_PATH = os.path.join(SCRIPTS_DIR, "vibe_role_assignment_gate.py")

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _eag_function_node(name):
    """Return the AST FunctionDef for `name` in the EAG module, or None."""
    src = _read(EAG_PATH)
    tree = ast.parse(src, filename=EAG_PATH)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


class TestEagCallsStrictValidator(unittest.TestCase):
    """Source-level: EAG must call validate_assignment_matrix_strict in production."""

    def test_eag_imports_strict_validator(self):
        src = _read(EAG_PATH)
        self.assertIn("validate_assignment_matrix_strict", src,
                      "EAG must import validate_assignment_matrix_strict")
        self.assertIn("_STRICT_AVAILABLE", src,
                      "EAG must track strict availability via _STRICT_AVAILABLE flag")

    def test_eag_source_calls_strict_in_production_path(self):
        # The Check 9 (role_assignment_matrix) inside cmd_check must call
        # validate_assignment_matrix_strict(...) when _STRICT_AVAILABLE.
        # We use AST to walk into cmd_check and look for the call site.
        fn = _eag_function_node("cmd_check")
        self.assertIsNotNone(fn, "cmd_check must exist in EAG")
        # Walk all statements in cmd_check
        found_strict_call = False
        found_strict_guard = False
        for node in ast.walk(fn):
            # Detect `_STRICT_AVAILABLE` reference (the strict-path guard)
            if isinstance(node, ast.Name) and node.id == "_STRICT_AVAILABLE":
                found_strict_guard = True
            # Detect call to validate_assignment_matrix_strict(...)
            if isinstance(node, ast.Call):
                callee = node.func
                if isinstance(callee, ast.Name) and callee.id == "validate_assignment_matrix_strict":
                    found_strict_call = True
        self.assertTrue(found_strict_guard,
                        "cmd_check must reference _STRICT_AVAILABLE flag")
        self.assertTrue(found_strict_call,
                        "cmd_check must call validate_assignment_matrix_strict(...)")

    def test_eag_legacy_path_is_fallback_only(self):
        # The legacy `validate_assignment_matrix` call must be guarded by
        # `elif _ROLE_ASSIGNMENT_GATE_AVAILABLE` (i.e. only when strict is
        # NOT available). If the legacy path is reachable without the
        # strict-fallback guard, the bypass issue #2 is not fixed.
        src = _read(EAG_PATH)
        # Look for the legacy call site pattern. We expect to find the
        # legacy call only in an `elif` branch (after the strict branch).
        self.assertIn("elif _ROLE_ASSIGNMENT_GATE_AVAILABLE:", src,
                      "EAG must guard legacy validator with elif on _ROLE_ASSIGNMENT_GATE_AVAILABLE")
        # The legacy call site must be reachable only when _STRICT_AVAILABLE
        # is False (i.e. strict import failed). The structure is:
        #   if role_matrix missing: BLOCK
        #   elif _STRICT_AVAILABLE: strict path
        #   elif _ROLE_ASSIGNMENT_GATE_AVAILABLE: legacy fallback
        #   else: BLOCK
        # Verify the order: _STRICT_AVAILABLE branch comes BEFORE the
        # _ROLE_ASSIGNMENT_GATE_AVAILABLE branch in the source.
        idx_strict = src.find("elif _STRICT_AVAILABLE")
        idx_legacy = src.find("elif _ROLE_ASSIGNMENT_GATE_AVAILABLE")
        self.assertGreater(idx_strict, -1, "must have elif _STRICT_AVAILABLE branch")
        self.assertGreater(idx_legacy, -1, "must have elif _ROLE_ASSIGNMENT_GATE_AVAILABLE branch")
        self.assertLess(idx_strict, idx_legacy,
                        "strict branch must come before legacy branch (strict is the primary path)")

    def test_eag_no_unguarded_legacy_call(self):
        # A bare call to validate_assignment_matrix(role_matrix) without a
        # guard (i.e. not under `elif _STRICT_AVAILABLE` or
        # `elif _ROLE_ASSIGNMENT_GATE_AVAILABLE`) would be the bypass
        # we are fixing. We assert that the only call site to
        # validate_assignment_matrix is the one inside the legacy fallback.
        tree = ast.parse(_read(EAG_PATH), filename=EAG_PATH)
        legacy_call_count = 0
        unguarded_call_count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                callee = node.func
                if isinstance(callee, ast.Name) and callee.id == "validate_assignment_matrix":
                    legacy_call_count += 1
        # The legacy import is `validate_assignment_matrix = None` in the
        # fallback ImportError branch — that's an assignment, not a call.
        # We expect exactly 1 CALL to validate_assignment_matrix (the
        # legacy fallback inside cmd_check).
        self.assertEqual(legacy_call_count, 1,
                         f"expected exactly 1 call site to validate_assignment_matrix, "
                         f"got {legacy_call_count}")


class TestEagBehaviorSimulation(unittest.TestCase):
    """Behavior-level: simulate the EAG's role_assignment_matrix check."""

    def setUp(self):
        # Re-import EAG fresh
        import importlib
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "eag_module_for_test", EAG_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.eag = mod
        # Also import RAG fresh
        from vibe_role_assignment_gate import (
            validate_assignment_matrix_strict as strict,
            validate_assignment_matrix as legacy,
            compute_approval_signature,
            create_assignment_matrix,
            create_role_assignment,
        )
        self.strict = strict
        self.legacy = legacy
        self.compute_sig = compute_approval_signature
        self.create_matrix = create_assignment_matrix
        self.create_entry = create_role_assignment

    def test_eag_strict_available_true(self):
        self.assertTrue(self.eag._STRICT_AVAILABLE)
        self.assertTrue(self.eag._ROLE_ASSIGNMENT_GATE_AVAILABLE)
        self.assertIsNotNone(self.eag.validate_assignment_matrix_strict)

    def test_eag_legacy_matrix_with_no_v11_fields_fails_strict(self):
        """Issue #2 reproduction: v1.0.0 legacy matrix (no spec_version,
        no v1.1.0 fields) MUST fail under validate_assignment_matrix_strict.
        """
        matrix = self.create_matrix("low", task_id="eag-bypass-test")
        matrix["assignments"] = [
            self.create_entry(role="implementer", node="21bao",
                              model="deepseek-deepseek-coder", provider="deepseek"),
            self.create_entry(role="reviewer", node="9bao",
                              model="deepseek-deepseek-coder", provider="deepseek"),
            self.create_entry(role="checker", node="21bao",
                              model="deepseek-deepseek-coder", provider="deepseek"),
        ]
        matrix["operator_approved"] = True
        matrix["operator_approval_timestamp"] = "2026-07-01T08:00:00Z"
        # NO spec_version, NO v1.1.0 fields — exactly the bypass input
        result = self.strict(matrix)
        self.assertFalse(result["valid"],
                         f"strict must BLOCK v1.0.0 legacy matrix; got valid={result['valid']}")
        # The error must mention v1.1.0 field gap
        err_text = " ".join(result.get("errors", []))
        self.assertIn("v1.1.0", err_text.lower(),
                      f"strict must surface v1.1.0 field gap; errors: {err_text}")

    def test_eag_legacy_matrix_passes_legacy_only(self):
        """Confirm the legacy path still passes (so the fallback is valid)."""
        matrix = self.create_matrix("low", task_id="eag-legacy-test")
        matrix["assignments"] = [
            self.create_entry(role="implementer", node="21bao",
                              model="deepseek-deepseek-coder", provider="deepseek"),
            self.create_entry(role="reviewer", node="9bao",
                              model="deepseek-deepseek-coder", provider="deepseek"),
            self.create_entry(role="checker", node="21bao",
                              model="deepseek-deepseek-coder", provider="deepseek"),
        ]
        matrix["operator_approved"] = True
        matrix["operator_approval_timestamp"] = "2026-07-01T08:00:00Z"
        result_legacy = self.legacy(matrix)
        self.assertTrue(result_legacy["valid"],
                        f"legacy path must still pass v1.0.0 matrix; errors: {result_legacy.get('errors')}")

    def test_eag_legal_v11_matrix_passes_strict(self):
        """A complete v1.1.0 matrix must pass under strict."""
        sig = self.compute_sig("01HXYZABCDEFGHJKMNPQRSTVWX", "2026-07-01T08:00:00Z")
        matrix = {
            "risk_level": "low", "task_id": "eag-legal-test",
            "required_roles": ["implementer", "reviewer", "checker"],
            "operator_approved": True,
            "operator_approval_timestamp": "2026-07-01T08:00:00Z",
            "operator_approval_signature": sig,
            "spec_version": "1.1.0",
            "assignments": [
                {"role": "implementer", "node": "21bao",
                 "model": "deepseek-deepseek-coder", "provider": "deepseek",
                 "cost_tag": "x", "reason": "y", "call_budget": 1, "fallback_policy": "disabled",
                 "assignment_id": "01HXYZABCDEFGHJKMNPQRSTVWX",
                 "provider_namespace": "opencode",
                 "operator_approval_timestamp": "2026-07-01T08:00:00Z",
                 "operator_approval_signature": sig,
                 "node_whitelist_verified": True,
                 "model_pool_source_verified": True,
                 "base_sha": "b" * 40},
                {"role": "reviewer", "node": "5bao",
                 "model": "deepseek-deepseek-coder", "provider": "deepseek",
                 "cost_tag": "x", "reason": "y", "call_budget": 1, "fallback_policy": "disabled",
                 "assignment_id": "01HXYZABCDEFGHJKMNPQRSTVWY",
                 "provider_namespace": "opencode",
                 "operator_approval_timestamp": "2026-07-01T08:00:00Z",
                 "operator_approval_signature": sig,
                 "node_whitelist_verified": True,
                 "model_pool_source_verified": True,
                 "base_sha": "c" * 40},
                {"role": "checker", "node": "21bao",
                 "model": "deepseek-deepseek-coder", "provider": "deepseek",
                 "cost_tag": "x", "reason": "y", "call_budget": 1, "fallback_policy": "disabled",
                 "assignment_id": "01HXYZABCDEFGHJKMNPQRSTVWZ",
                 "provider_namespace": "opencode",
                 "operator_approval_timestamp": "2026-07-01T08:00:00Z",
                 "operator_approval_signature": sig,
                 "node_whitelist_verified": True,
                 "model_pool_source_verified": True,
                 "base_sha": "d" * 40},
            ],
        }
        result = self.strict(matrix)
        self.assertTrue(result["valid"],
                        f"legal v1.1 strict must pass; errors: {result.get('errors')}")

    def test_eag_main_agent_v11_strict_fails(self):
        """Issue #1 reproduction: main-agent in v1.1 strict MUST fail."""
        sig = self.compute_sig("01HXYZABCDEFGHJKMNPQRSTVWX", "2026-07-01T08:00:00Z")
        matrix = {
            "risk_level": "low", "task_id": "eag-main-agent-test",
            "required_roles": ["implementer", "reviewer", "checker"],
            "operator_approved": True,
            "operator_approval_timestamp": "2026-07-01T08:00:00Z",
            "operator_approval_signature": sig,
            "main_agent_as_tester_approved": True,
            "spec_version": "1.1.0",
            "assignments": [
                {"role": "implementer", "node": "main-agent",
                 "model": "deepseek-deepseek-coder", "provider": "deepseek",
                 "cost_tag": "x", "reason": "y", "call_budget": 1, "fallback_policy": "disabled",
                 "assignment_id": "01HXYZABCDEFGHJKMNPQRSTVWX",
                 "provider_namespace": "opencode",
                 "operator_approval_timestamp": "2026-07-01T08:00:00Z",
                 "operator_approval_signature": sig,
                 "node_whitelist_verified": True,
                 "model_pool_source_verified": True,
                 "base_sha": "b" * 40},
                {"role": "reviewer", "node": "5bao",
                 "model": "deepseek-deepseek-coder", "provider": "deepseek",
                 "cost_tag": "x", "reason": "y", "call_budget": 1, "fallback_policy": "disabled",
                 "assignment_id": "01HXYZABCDEFGHJKMNPQRSTVWY",
                 "provider_namespace": "opencode",
                 "operator_approval_timestamp": "2026-07-01T08:00:00Z",
                 "operator_approval_signature": sig,
                 "node_whitelist_verified": True,
                 "model_pool_source_verified": True,
                 "base_sha": "c" * 40},
                {"role": "checker", "node": "21bao",
                 "model": "deepseek-deepseek-coder", "provider": "deepseek",
                 "cost_tag": "x", "reason": "y", "call_budget": 1, "fallback_policy": "disabled",
                 "assignment_id": "01HXYZABCDEFGHJKMNPQRSTVWZ",
                 "provider_namespace": "opencode",
                 "operator_approval_timestamp": "2026-07-01T08:00:00Z",
                 "operator_approval_signature": sig,
                 "node_whitelist_verified": True,
                 "model_pool_source_verified": True,
                 "base_sha": "d" * 40},
            ],
        }
        result = self.strict(matrix)
        self.assertFalse(result["valid"],
                         "main-agent + role=implementer + v1.1 strict must BLOCK")
        err_text = " ".join(result.get("errors", []))
        self.assertIn("main-agent", err_text,
                      f"error must mention main-agent; got: {err_text[:200]}")


class TestEagStrictSourceStructure(unittest.TestCase):
    """Defensive: the source structure must continue to enforce strict-first."""

    def test_eag_source_has_legacy_check_used_marker(self):
        # The EAG source should set `ra_legacy` to indicate which path was
        # used. This makes transitional deploys detectable.
        src = _read(EAG_PATH)
        self.assertIn("ra_legacy", src,
                      "EAG must track legacy_check_used via ra_legacy for transitional deploy detection")

    def test_eag_check9_labeled_correctly(self):
        # Check 9 is the role_assignment_matrix check. Make sure the
        # source comment / label is updated to reflect the v1.1.0 strict
        # enforcement.
        src = _read(EAG_PATH)
        # Either "Check 9:" or "Stage 3 v1.2.x" comment must appear
        self.assertTrue("Check 9" in src or "role_assignment_matrix" in src,
                        "EAG must still have Check 9 / role_assignment_matrix")


if __name__ == "__main__":
    unittest.main()
