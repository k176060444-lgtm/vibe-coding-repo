#!/usr/bin/env python3
"""Tests for model_pool_drift.py — Layer 1 drift detection."""

import ast
import json
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import yaml

from model_pool_drift import (
    detect_drift_layer1,
    self_check,
    _normalize_node,
    LEGACY_NODE_ALIASES,
)


# ── Test fixtures ──────────────────────────────────────────────────────────


def _mk_pool(model_ids, allowed_nodes_map=None, lifecycle_map=None,
             enabled_map=None):
    """Create a minimal pool fixture."""
    models = []
    for mid in model_ids:
        allowed = (allowed_nodes_map or {}).get(mid, [])
        ls = (lifecycle_map or {}).get(mid, "enabled_assigned")
        enabled = (enabled_map or {}).get(mid, True) if enabled_map else True
        models.append({
            "id": mid,
            "alias": [mid.split("-")[-1]],
            "enabled": enabled,
            "allowed_nodes": allowed,
            "lifecycle_status": ls,
            "canonical_provider": "test",
            "provider_namespace": "test",
        })
    return {"schema_version": "1.2", "models": models}


def _mk_nmc(matrix_map):
    """Create a minimal NMC fixture."""
    nodes = {}
    for node, model_ids in matrix_map.items():
        nodes[node] = {
            "runtime_provider": "test",
            "total_entries": len(model_ids),
            "matrix": [{"model_id": m, "declared": True} for m in model_ids],
        }
    return {"schema_version": "1.1", "nodes": nodes, "skipped_models": {"count": 0, "ids": []}}


# ── Normalize tests ────────────────────────────────────────────────────────


class TestNormalizeNode(unittest.TestCase):
    def test_21bao(self):
        self.assertEqual(_normalize_node("21bao"), "21bao")

    def test_5bao(self):
        self.assertEqual(_normalize_node("5bao"), "5bao")

    def test_9bao(self):
        self.assertEqual(_normalize_node("9bao"), "9bao")

    def test_win_legacy(self):
        self.assertEqual(_normalize_node("win"), "21bao")

    def test_invalid_node(self):
        self.assertIsNone(_normalize_node("10bao"))

    def test_empty(self):
        self.assertIsNone(_normalize_node(""))


# ── No-drift cases ────────────────────────────────────────────────────────


class TestNoDrift(unittest.TestCase):
    def test_clean_pool_matrix(self):
        pool = _mk_pool(
            ["opencode-go-mimo-v2-5", "opencode-go-glm-5-2"],
            allowed_nodes_map={
                "opencode-go-mimo-v2-5": ["5bao", "9bao", "win"],
                "opencode-go-glm-5-2": ["5bao", "9bao", "win"],
            },
            lifecycle_map={
                "opencode-go-mimo-v2-5": "operator_requested",
                "opencode-go-glm-5-2": "enabled_assigned",
            },
        )
        nmc = _mk_nmc({
            "21bao": ["opencode-go-mimo-v2-5", "opencode-go-glm-5-2"],
            "5bao": ["opencode-go-mimo-v2-5", "opencode-go-glm-5-2"],
            "9bao": ["opencode-go-mimo-v2-5", "opencode-go-glm-5-2"],
        })
        report = detect_drift_layer1(pool=pool, nmc=nmc, manifest={})
        self.assertFalse(report["drift_detected"])
        self.assertEqual(report["drift_count"], 0)


# ── BLOCK drift cases ─────────────────────────────────────────────────────


class TestMissingMatrixEntry(unittest.TestCase):
    def test_pool_model_missing_from_matrix(self):
        pool = _mk_pool(
            ["opencode-go-glm-5-2", "opencode-go-mimo-v2-5"],
            allowed_nodes_map={
                "opencode-go-glm-5-2": ["5bao", "9bao", "win"],
                "opencode-go-mimo-v2-5": ["5bao", "9bao", "win"],
            },
        )
        # mimo missing from 21bao matrix
        nmc = _mk_nmc({
            "21bao": ["opencode-go-glm-5-2"],  # mimo missing
            "5bao": ["opencode-go-glm-5-2", "opencode-go-mimo-v2-5"],
            "9bao": ["opencode-go-glm-5-2", "opencode-go-mimo-v2-5"],
        })
        report = detect_drift_layer1(pool=pool, nmc=nmc, manifest={})
        self.assertTrue(report["drift_detected"])
        cats = [d["category"] for d in report["details"]]
        self.assertIn("missing_matrix_entry", cats)


class TestExtraMatrixEntry(unittest.TestCase):
    def test_unknown_model_in_matrix(self):
        pool = _mk_pool(["opencode-go-glm-5-2"])
        nmc = _mk_nmc({
            "21bao": ["opencode-go-glm-5-2", "bogus-model-not-in-pool"],
        })
        report = detect_drift_layer1(pool=pool, nmc=nmc, manifest={})
        self.assertTrue(report["drift_detected"])
        cats = [d["category"] for d in report["details"]]
        self.assertIn("extra_matrix_entry", cats)


class TestAllowedNodesMismatch(unittest.TestCase):
    def test_matrix_has_model_not_in_allowed(self):
        """A non-declared_enabled_unassigned enabled model in matrix for node
        not in pool.allowed_nodes should be BLOCK.
        """
        pool = _mk_pool(
            ["opencode-go-glm-5-2"],
            allowed_nodes_map={"opencode-go-glm-5-2": ["5bao"]},  # only 5bao
            lifecycle_map={"opencode-go-glm-5-2": "enabled_assigned"},
        )
        nmc = _mk_nmc({
            "21bao": ["opencode-go-glm-5-2"],  # in matrix but pool says only 5bao
        })
        report = detect_drift_layer1(pool=pool, nmc=nmc, manifest={})
        self.assertTrue(report["drift_detected"])
        cats = [d["category"] for d in report["details"]]
        self.assertIn("allowed_nodes_mismatch", cats)


class TestDisabledInMatrix(unittest.TestCase):
    def test_disabled_model_in_matrix_blocks(self):
        pool = _mk_pool(
            ["opencode-go-glm-5-2"],
            allowed_nodes_map={"opencode-go-glm-5-2": ["5bao"]},
            lifecycle_map={"opencode-go-glm-5-2": "disabled"},
            enabled_map={"opencode-go-glm-5-2": False},
        )
        nmc = _mk_nmc({"5bao": ["opencode-go-glm-5-2"]})
        report = detect_drift_layer1(pool=pool, nmc=nmc, manifest={})
        self.assertTrue(report["drift_detected"])
        cats = [d["category"] for d in report["details"]]
        self.assertIn("lifecycle_in_matrix", cats)


class TestRemovePendingInMatrix(unittest.TestCase):
    def test_remove_pending_model_in_matrix_blocks(self):
        pool = _mk_pool(
            ["opencode-big-pickle"],
            allowed_nodes_map={"opencode-big-pickle": ["5bao"]},
            lifecycle_map={"opencode-big-pickle": "remove_pending"},
            enabled_map={"opencode-big-pickle": False},
        )
        nmc = _mk_nmc({"5bao": ["opencode-big-pickle"]})
        report = detect_drift_layer1(pool=pool, nmc=nmc, manifest={})
        self.assertTrue(report["drift_detected"])
        cats = [d["category"] for d in report["details"]]
        self.assertIn("lifecycle_in_matrix", cats)


class TestDeclaredEnabledUnassignedInMatrix(unittest.TestCase):
    """declared_enabled_unassigned in matrix is WARN, not BLOCK."""

    def test_deu_in_matrix_is_warn(self):
        pool = _mk_pool(
            ["anthropic-claude-sonnet-4"],
            allowed_nodes_map={"anthropic-claude-sonnet-4": []},
            lifecycle_map={"anthropic-claude-sonnet-4": "declared_enabled_unassigned"},
        )
        nmc = _mk_nmc({"21bao": ["anthropic-claude-sonnet-4"]})
        report = detect_drift_layer1(pool=pool, nmc=nmc, manifest={})
        # WARN only, not drift
        self.assertFalse(report["drift_detected"])
        self.assertGreater(report["warn_count"], 0)
        self.assertIn("lifecycle_in_matrix_warn", report["warn_categories"])


# ── Manifest drift ────────────────────────────────────────────────────────


class TestManifestMismatch(unittest.TestCase):
    def test_manifest_mismatch_reported(self):
        pool = _mk_pool(["x"])
        nmc = _mk_nmc({})
        manifest = {"files": {"model_pool.yaml": {"sha256": "wrongsha"}}}
        report = detect_drift_layer1(pool=pool, nmc=nmc, manifest=manifest)
        # Manifest mismatch reported but not a BLOCK (it's an advisory)
        # In real runs we compute SHA; in tests we accept the mismatch as drift
        cats = [d["category"] for d in report["details"]]
        self.assertIn("manifest_mismatch", cats)


# ── Pure / local-only checks ──────────────────────────────────────────────


class TestLocalOnly(unittest.TestCase):
    """Verify detector is local-only and audit-safe."""

    def test_no_secret_leak_in_output(self):
        # Build pool with key_env NAME (not value)
        pool = {
            "schema_version": "1.2",
            "models": [{
                "id": "test-model",
                "enabled": True,
                "allowed_nodes": ["5bao"],
                "lifecycle_status": "enabled_assigned",
                "key_env": "OPENCODE_TEST_API_KEY",
                "base_url_env": "OPENCODE_TEST_BASE_URL",
                "canonical_provider": "test",
                "provider_namespace": "test",
            }],
        }
        nmc = _mk_nmc({"5bao": ["test-model"]})
        report = detect_drift_layer1(pool=pool, nmc=nmc, manifest={})
        output = json.dumps(report)
        self.assertNotIn("sk-", output)
        self.assertNotIn("http://", output)
        self.assertNotIn("https://", output)
        self.assertNotIn("=***", output)
        self.assertNotIn("OPENCODE_TEST_API_KEY=", output + "=")  # NAME alone is OK

    def test_no_ssh_imports(self):
        """Source code must not contain subprocess/SSH/HTTP imports."""
        src = Path(SCRIPTS_DIR / "model_pool_drift.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        forbidden = {"subprocess", "paramiko", "fabric", "requests",
                     "urllib", "socket", "http.client"}
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in forbidden:
                        violations.append(f"import {alias.name}")
            if isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod in forbidden:
                    violations.append(f"from {node.module} import ...")
        self.assertEqual(violations, [],
                         f"Forbidden imports detected: {violations}")

    def test_no_file_writes(self):
        """No file writes — only open() with mode='r' or 'rb' allowed."""
        src = Path(SCRIPTS_DIR / "model_pool_drift.py").read_text(encoding="utf-8")
        tree = ast.parse(src)
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    # Determine mode
                    mode_arg = None
                    for kw in node.keywords:
                        if kw.arg == "mode":
                            mode_arg = (kw.value.value
                                        if isinstance(kw.value, ast.Constant) else None)
                    if mode_arg is None and len(node.args) >= 2:
                        mode_arg = (node.args[1].value
                                    if isinstance(node.args[1], ast.Constant) else None)
                    if mode_arg and mode_arg not in ("r", "rb"):
                        violations.append(f"open() with mode='{mode_arg}'")
        self.assertEqual(violations, [], f"Forbidden writes: {violations}")


class TestLegacyCompatibility(unittest.TestCase):
    def test_win_alias_normalized(self):
        """A pool model with allowed_nodes=['win'] should map to 21bao."""
        pool = _mk_pool(
            ["opencode-go-glm-5-2"],
            allowed_nodes_map={"opencode-go-glm-5-2": ["win"]},  # legacy
            lifecycle_map={"opencode-go-glm-5-2": "enabled_assigned"},
        )
        nmc = _mk_nmc({"21bao": ["opencode-go-glm-5-2"]})
        report = detect_drift_layer1(pool=pool, nmc=nmc, manifest={})
        # win → 21bao normalized, no allowed_nodes_mismatch
        self.assertFalse(report["drift_detected"])


class TestSelfCheck(unittest.TestCase):
    def test_self_check_passes(self):
        result = self_check()
        self.assertEqual(result["status"], "PASS", f"Self-check failed: {result}")


if __name__ == "__main__":
    unittest.main()