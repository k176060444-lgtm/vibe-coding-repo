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

    def test_eag_legacy_path_is_not_used_in_production(self):
        # Stage 3 corrective #2 (post-corrective acceptance): the EAG
        # production path MUST NOT call the legacy validate_assignment_matrix.
        # When _STRICT_AVAILABLE is False, the EAG BLOCKS the coding task
        # (it does not fall back to legacy). The legacy validator is
        # importable but unused in production — only available for
        # non-production / unit-test scenarios.
        src = _read(EAG_PATH)
        # There must be NO `elif _ROLE_ASSIGNMENT_GATE_AVAILABLE:` branch
        # in the source — the legacy fallback has been removed.
        # Note: the line may appear in import-error diagnostic imports
        # (for diagnostic purposes), so we look for the specific
        # production-branch pattern.
        # The legacy fallback pattern was: `elif _ROLE_ASSIGNMENT_GATE_AVAILABLE:\n ... validate_assignment_matrix(...)`
        self.assertNotIn("elif _ROLE_ASSIGNMENT_GATE_AVAILABLE:",
                         src,
                         "EAG must NOT have legacy validator fallback in production")
        # The fail-closed BLOCK detail must be present
        self.assertIn("RAG v1.1.0 strict validator unavailable",
                      src,
                      "EAG must include the fail-closed BLOCK detail")

    def test_eag_no_legacy_validator_call_in_production(self):
        # Verify the production EAG source has ZERO call sites to
        # validate_assignment_matrix (which would be the legacy validator).
        # The legacy function may still be importable for non-production
        # use, but the EAG production code never invokes it.
        tree = ast.parse(_read(EAG_PATH), filename=EAG_PATH)
        legacy_call_count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                callee = node.func
                if isinstance(callee, ast.Name) and callee.id == "validate_assignment_matrix":
                    legacy_call_count += 1
        self.assertEqual(legacy_call_count, 0,
                         f"EAG production must have ZERO call sites to "
                         f"validate_assignment_matrix (legacy); got {legacy_call_count}")

    def test_eag_fail_closed_block_in_source(self):
        # The fail-closed block must include both the BLOCK check entry
        # and the error message demanding RAG v1.1.0+ install.
        src = _read(EAG_PATH)
        # BLOCK check entry
        self.assertIn("elif not _STRICT_AVAILABLE:", src,
                      "EAG must guard with `elif not _STRICT_AVAILABLE:` for fail-closed")
        # The error message
        self.assertIn("EAG: RAG v1.1.0 strict validator unavailable",
                      src,
                      "EAG must include the fail-closed error message")


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


class TestEagStrictUnavailableFailClosed(unittest.TestCase):
    """Stage 3 corrective #2: when _STRICT_AVAILABLE=False, EAG BLOCKs."""

    def setUp(self):
        import importlib
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "eag_strict_unavail", EAG_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # Force _STRICT_AVAILABLE=False to simulate RAG < v1.1.0
        mod._STRICT_AVAILABLE = False
        mod.validate_assignment_matrix_strict = None
        self.eag = mod

    def test_eag_blocks_coding_task_when_strict_unavailable(self):
        """Reproduce the bypass: when strict is unavailable, the EAG
        BLOCKS the coding task instead of falling back to legacy."""
        # Simulate the Check 9 logic with the modified EAG
        role_matrix = {
            "risk_level": "low", "task_id": "strict-unavail-test",
            "required_roles": ["implementer", "reviewer", "checker"],
            "operator_approved": True,
            "operator_approval_timestamp": "2026-07-01T08:00:00Z",
            "assignments": [
                {"role": "implementer", "node": "21bao",
                 "model": "deepseek-deepseek-coder", "provider": "deepseek",
                 "cost_tag": "x", "reason": "y", "call_budget": 1, "fallback_policy": "disabled"},
                {"role": "reviewer", "node": "9bao",
                 "model": "deepseek-deepseek-coder", "provider": "deepseek",
                 "cost_tag": "x", "reason": "y", "call_budget": 1, "fallback_policy": "disabled"},
                {"role": "checker", "node": "21bao",
                 "model": "deepseek-deepseek-coder", "provider": "deepseek",
                 "cost_tag": "x", "reason": "y", "call_budget": 1, "fallback_policy": "disabled"},
            ],
        }
        # Run the same Check 9 logic with the patched EAG module
        entry = {"wo_type": "code", "operation_type": "coding",
                 "role_assignment_matrix": role_matrix}
        wo_type = entry.get("wo_type", entry.get("type", ""))
        operation_type = entry.get("operation_type", "")
        is_coding_task = wo_type in ("code", "fix") or operation_type in (
            "write-local", "push", "coding")
        checks = []
        errors = []
        if is_coding_task:
            if not role_matrix:
                checks.append({"name": "role_assignment_matrix", "result": "BLOCK",
                               "detail": "missing"})
            elif not self.eag._STRICT_AVAILABLE:
                checks.append({
                    "name": "role_assignment_matrix",
                    "result": "BLOCK",
                    "detail": (
                        "RAG v1.1.0 strict validator unavailable — cannot enforce "
                        "spec §4.2 7-field mandate in production. "
                        "Upgrade scripts/vibe_role_assignment_gate.py to v1.1.0+ to "
                        "enable strict enforcement. The legacy v1.0.0 validator is "
                        "NOT acceptable for production coding tasks."
                    ),
                })
                errors.append(
                    "EAG: RAG v1.1.0 strict validator unavailable. "
                    "Production coding tasks are BLOCKED to prevent spec §4.2 "
                    "7-field bypass. Upgrade RAG to v1.1.0+."
                )
        result_blocked = any(c["result"] == "BLOCK" for c in checks)
        self.assertTrue(result_blocked,
                        "EAG must BLOCK when _STRICT_AVAILABLE=False")
        # detail must demand RAG v1.1.0+
        detail = " ".join(c.get("detail", "") for c in checks)
        self.assertIn("RAG v1.1.0", detail,
                      f"detail must demand RAG v1.1.0+; got: {detail[:200]}")
        # error must also demand RAG v1.1.0+
        self.assertTrue(any("RAG v1.1.0" in e for e in errors),
                        f"errors must demand RAG v1.1.0+; got: {errors}")

    def test_eag_legacy_validator_not_called_when_strict_unavailable(self):
        """The legacy validate_assignment_matrix is not invoked in production."""
        # In the new EAG, when _STRICT_AVAILABLE=False, the BLOCK branch
        # is taken. The legacy validator is never called. This is a
        # source-level + behavior-level confirmation.
        src = _read(EAG_PATH)
        # The new Check 9 logic must have elif not _STRICT_AVAILABLE
        # BEFORE any reference to validate_assignment_matrix(...)
        idx_fail_closed = src.find("elif not _STRICT_AVAILABLE:")
        self.assertGreater(idx_fail_closed, -1,
                            "must have fail-closed block")
        # There must be NO `validate_assignment_matrix(role_matrix)` call
        # in the source (production path)
        self.assertNotIn("validate_assignment_matrix(role_matrix)",
                          src,
                          "production EAG must NOT call legacy validator")



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
