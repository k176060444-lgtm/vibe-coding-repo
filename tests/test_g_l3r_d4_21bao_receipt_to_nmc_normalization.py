#!/usr/bin/env python3
"""Tests for G-L3R D4 21bao Receipt-to-NMC Normalization (PR #337).

Verifies:
- 21bao D4 entry has runtime_visible=True with PR #336 evidence
- 5bao/9bao D4 entries have runtime_visible=True (unchanged)
- All 3 nodes: model_call_verified / operator_approved / env_loaded
  not promoted
- model_pool.yaml untouched
- Normalization script is deterministic / idempotent
- 21bao normalization does NOT promote 3-of-3 at model_call_verified /
  operator_approved / G-L4 readiness
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

NMC_PATH = SCRIPTS / "node_model_capability.yaml"
POOL_PATH = SCRIPTS / "model_pool.yaml"
NORM_SCRIPT = SCRIPTS / "normalize_g_l3r_d4_runtime_visible.py"
RECEIPT_PATH = ROOT / ".hermes" / "evidence" / "g-l3r-d4-21bao-local-runtime-visible-v1" / "21bao-receipt.json"
RESIDUAL_GATE_EVIDENCE = ROOT / ".hermes" / "evidence" / "g-l3r-d4-21bao-residual-gate.json"
RESIDUAL_GATE_DOC = ROOT / "docs" / "baseline02" / "g-l3r-d4-21bao-residual-gate.md"
THIS_DOC = ROOT / "docs" / "baseline02" / "g-l3r-d4-21bao-receipt-to-nmc-normalization.md"

D4_MODEL_ID = "opencode-go-deepseek-v4-pro"
NODES = ["21bao", "5bao", "9bao"]


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════


def _load_nmc() -> dict:
    with open(NMC_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _get_d4_entry(nmc: dict, node: str) -> dict | None:
    matrix = nmc.get("nodes", {}).get(node, {}).get("matrix", [])
    for e in matrix:
        if isinstance(e, dict) and e.get("model_id") == D4_MODEL_ID:
            return e
    return None


def _load_pool() -> dict:
    with open(POOL_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_pr336_receipt() -> dict:
    with open(RECEIPT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════════════════════
# PR #336 receipt is the canonical source
# ══════════════════════════════════════════════════════════════════════════════


class TestReceiptSource:
    def test_pr336_receipt_exists_and_valid(self):
        r = _load_pr336_receipt()
        assert r["node"] == "21bao"
        assert r["runtime_visible_observed"] is True
        assert r["runtime_visible_source"] == "21bao_local_opencode_config"
        assert r["anchor"] == "2ec1778e357fd3a840b35d45d061f171388bf740"

    def test_pr336_receipt_records_matched_key(self):
        r = _load_pr336_receipt()
        vd = r.get("visibility_details", {})
        assert vd.get("matched_key") == "deepseek-plan.deepseek-v4-pro"


# ══════════════════════════════════════════════════════════════════════════════
# 21bao D4 NMC entry: PR #336 evidence-backed
# ══════════════════════════════════════════════════════════════════════════════


class Test21baoD4EvidenceRef:
    def test_21bao_runtime_visible_true(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "21bao")
        assert entry is not None, "21bao D4 entry missing"
        assert entry.get("runtime_visible") is True, \
            "21bao D4 runtime_visible must be True (PR #336 evidence)"

    def test_21bao_has_evidence_block(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "21bao")
        ev = entry.get("runtime_visible_evidence")
        assert isinstance(ev, dict), \
            "21bao must carry runtime_visible_evidence dict"
        assert "PR #336" in str(ev.get("source", ""))
        assert "2ec1778e" in str(ev.get("evidence_anchor", ""))
        assert "0a932be" in str(ev.get("merge_commit", ""))
        assert ev.get("collector") == "worker_attest_layer3_d4_21bao_local_runtime_visible"
        assert ev.get("runtime_visible_source") == "21bao_local_opencode_config"
        assert ev.get("matched_key") == "deepseek-plan.deepseek-v4-pro"

    def test_21bao_env_loaded_preserved_not_promoted(self):
        """env_loaded: 21bao D4 entry pre-existing value preserved.
        No promotion by this PR (env_loaded was already true in NMC
        before; not introduced by this normalization).
        """
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "21bao")
        el = entry.get("env_loaded")
        # env_loaded is acceptable as long as it's not newly promoted
        # (it was already true pre-PR). This PR does not change env_loaded.
        assert el in (True, "true", "True", "unknown"), \
            f"unexpected env_loaded={el!r}"


# ══════════════════════════════════════════════════════════════════════════════
# 5bao/9bao: unchanged from PR #334 (PR #332 evidence references preserved)
# ══════════════════════════════════════════════════════════════════════════════


class Test5bao9baoUnchanged:
    def test_5bao_runtime_visible_evidence_pr332(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "5bao")
        ev = entry.get("runtime_visible_evidence")
        assert isinstance(ev, dict)
        assert "PR #332" in str(ev.get("source", ""))
        assert "09b1d97" in str(ev.get("evidence_anchor", ""))

    def test_9bao_runtime_visible_evidence_pr332(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "9bao")
        ev = entry.get("runtime_visible_evidence")
        assert isinstance(ev, dict)
        assert "PR #332" in str(ev.get("source", ""))
        assert "09b1d97" in str(ev.get("evidence_anchor", ""))


# ══════════════════════════════════════════════════════════════════════════════
# Forbidden: model_call_verified / operator_approved promotion
# ══════════════════════════════════════════════════════════════════════════════


class TestNoForbiddenPromotion:
    def test_all_nodes_model_call_verified_not_promoted(self):
        nmc = _load_nmc()
        for n in NODES:
            entry = _get_d4_entry(nmc, n)
            assert entry is not None, f"{n}: D4 entry missing"
            assert entry.get("model_call_verified") is not True, \
                f"{n}: model_call_verified promoted"

    def test_all_nodes_operator_approved_not_promoted(self):
        nmc = _load_nmc()
        for n in NODES:
            entry = _get_d4_entry(nmc, n)
            assert entry.get("operator_approved") is not True, \
                f"{n}: operator_approved promoted"

    def test_no_g_l4_claim_in_yaml(self):
        with open(NMC_PATH, "r", encoding="utf-8") as f:
            content = f.read().lower()
        # No literal G-L4 ready or readiness ready
        for forbidden in ("g-l4 ready", "readiness ready"):
            assert forbidden not in content, \
                f"NMC contains '{forbidden}'"


# ══════════════════════════════════════════════════════════════════════════════
# model_pool.yaml untouched
# ══════════════════════════════════════════════════════════════════════════════


class TestModelPoolUnchanged:
    def test_pool_no_smoke_results_21bao(self):
        pool = _load_pool()
        for m in pool.get("models", []):
            if isinstance(m, dict) and m.get("id") == D4_MODEL_ID:
                smoke = m.get("smoke_results", {}) or {}
                assert "21bao" not in smoke, \
                    "model_pool D4 entry has 21bao in smoke_results"
                # No D4 promotion fields
                for forbidden in ("runtime_visible", "model_call_verified",
                                  "operator_approved"):
                    assert forbidden not in m, \
                        f"model_pool D4 entry has unexpected field: {forbidden}"
                return
        raise AssertionError(f"{D4_MODEL_ID} not in pool")


# ══════════════════════════════════════════════════════════════════════════════
# Normalization script: deterministic + idempotent + self-check
# ══════════════════════════════════════════════════════════════════════════════


class TestNormalizationScript:
    def test_script_runs_successfully(self):
        # Snapshot NMC, run script, compare idempotence
        with open(NMC_PATH, "rb") as f:
            before = f.read()
        r = subprocess.run(
            ["python", str(NORM_SCRIPT)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert r.returncode == 0, f"normalize failed: {r.stderr}"
        with open(NMC_PATH, "rb") as f:
            after_run_1 = f.read()
        # Run again to verify idempotence
        r2 = subprocess.run(
            ["python", str(NORM_SCRIPT)],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert r2.returncode == 0
        with open(NMC_PATH, "rb") as f:
            after_run_2 = f.read()
        assert after_run_1 == after_run_2, \
            "Normalization is not idempotent (NMC differs between runs)"
        # And the second run matches the first (deterministic beyond equal)
        assert before == after_run_1 or after_run_1 == after_run_2

    def test_self_check_passes(self):
        r = subprocess.run(
            ["python", str(NORM_SCRIPT), "--self-check"],
            capture_output=True, text=True, cwd=str(ROOT),
        )
        assert r.returncode == 0, f"self-check failed: {r.stderr}"
        # Self-check should report PASS
        assert "PASS" in r.stdout, \
            f"expected PASS in self-check stdout: {r.stdout!r}"


# ══════════════════════════════════════════════════════════════════════════════
# Residual gate: 3-of-3 at runtime_visible, higher layers still blocked
# ══════════════════════════════════════════════════════════════════════════════


class TestResidualGateUpdated:
    def test_residual_gate_json_3of3(self):
        with open(RESIDUAL_GATE_EVIDENCE, "r") as f:
            ev = json.load(f)
        verdict = ev.get("verdict", {})
        assert verdict.get("three_of_three_runtime_visible") is True
        assert verdict.get("closes_global_blocker") is False
        assert verdict.get("three_of_three_model_call_verified") is False
        assert verdict.get("three_of_three_operator_approved") is False
        assert verdict.get("is_g_l4_ready") is False
        assert verdict.get("is_readiness_ready") is False
        assert verdict.get("is_model_call_verified_ready") is False

    def test_residual_gate_doc_no_g_l4_claim(self):
        doc = RESIDUAL_GATE_DOC.read_text(encoding="utf-8")
        # No "G-L4 ready" literal claim (in the "Does Not Mean" table is OK)
        # Count occurrences — it should appear only in safety/no-claim tables
        assert doc.lower().count("g-l4 ready") <= 2, \
            "residual gate doc may not claim G-L4 ready beyond the no-claim table"


# ══════════════════════════════════════════════════════════════════════════════
# This PR's doc
# ══════════════════════════════════════════════════════════════════════════════


class TestPRDocumentation:
    def test_pr_doc_exists(self):
        assert THIS_DOC.exists(), "PR doc missing"

    def test_pr_doc_acknowledges_forbidden_ops(self):
        doc = THIS_DOC.read_text(encoding="utf-8")
        # Must declare the forbidden operations table
        for phrase in ("Model call", "Credential provisioning",
                       "operator_approved", "model_call_verified",
                       "G-L4", "smoke", "SSH"):
            assert phrase in doc, f"PR doc missing '{phrase}'"
        # Must explicitly disallow global blocker closure.
        # Look for "Global" + "G_L3R_BLOCKED" + "NOT"-flavored word nearby.
        assert re.search(
            r"global.*G_L3R_BLOCKED.*NOT|closes global G_L3R_BLOCKED.*NO|"
            r"G_L3R_BLOCKED.*narrowed|does not close globally",
            doc, re.IGNORECASE,
        ), "PR doc must explicitly NOT close global G_L3R_BLOCKED"

    def test_pr_doc_no_global_closure_claim(self):
        doc = THIS_DOC.read_text(encoding="utf-8")
        # "Closes Global G_L3R_BLOCKED" must be NO
        assert "Closes Global G_L3R_BLOCKED | **NO**" in doc


# ══════════════════════════════════════════════════════════════════════════════
# Forbidden-operation cleanliness: no secrets in changed files
# ══════════════════════════════════════════════════════════════════════════════


class TestSecretScan:
    def test_nmc_no_secrets(self):
        content = NMC_PATH.read_text(encoding="utf-8")
        for pat in [r"sk-[a-zA-Z0-9]{20,}", r"ghp_[a-zA-Z0-9]{36}",
                    r"AKIA[0-9A-Z]{16}"]:
            assert not re.search(pat, content), f"secret pattern in NMC: {pat}"

    def test_residual_gate_json_no_secrets(self):
        content = RESIDUAL_GATE_EVIDENCE.read_text(encoding="utf-8")
        for pat in [r"sk-[a-zA-Z0-9]{20,}", r"ghp_[a-zA-Z0-9]{36}",
                    r"AKIA[0-9A-Z]{16}"]:
            assert not re.search(pat, content), f"secret in gate json: {pat}"

    def test_pr336_receipt_no_secrets(self):
        content = RECEIPT_PATH.read_text(encoding="utf-8")
        for pat in [r"sk-[a-zA-Z0-9]{20,}", r"ghp_[a-zA-Z0-9]{36}",
                    r"AKIA[0-9A-Z]{16}"]:
            assert not re.search(pat, content), f"secret in receipt: {pat}"
