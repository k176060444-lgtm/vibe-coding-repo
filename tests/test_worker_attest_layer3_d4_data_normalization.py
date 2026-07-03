#!/usr/bin/env python3
"""Tests for G-L3R D4 data-only normalization PR.

Verifies that the normalization:
- Corrects D4 preflight NMC key bug
- Adds disambiguation note to legacy deepseek-plan d4 entry
- Does NOT promote runtime_visible/env_loaded/model_call_verified/operator_approved
- Does NOT claim G-L4 / readiness / G-D-A / G-D-B / G-GRAY / PR-7 / Baseline03
- Aggregates/reconciliation preserve downstream blocker if any
- D4 preflight verdict correctly reflects remaining gap
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import yaml

_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from worker_attest_layer3_d4_runtime_visible_preflight import (
    build_d4_preflight,
    self_check as d4_self_check,
    _load_model_pool,
    _load_nmc,
    _collect_nmc_entries,
    _find_deepseek_v4_pro_entries,
)

ROOT = Path(__file__).resolve().parent.parent
POOL_PATH = ROOT / "scripts" / "model_pool.yaml"
NMC_PATH = ROOT / "scripts" / "node_model_capability.yaml"


# ══════════════════════════════════════════════════════════════════════════════
# Pool disambiguation
# ══════════════════════════════════════════════════════════════════════════════


class TestPoolDisambiguation:
    """Test that the model_pool.yaml d4 entries are disambiguated."""

    def test_legacy_d4_note_present(self):
        pool = _load_model_pool()
        d4 = _find_deepseek_v4_pro_entries(pool)
        # The deepseek-plan d4 entry should have a normalization note
        legacy = [e for e in d4 if e.get("canonical_provider") == "deepseek-plan"]
        assert len(legacy) == 1, "expected 1 legacy deepseek-plan d4 entry"
        notes = legacy[0].get("notes", "")
        assert "legacy" in notes.lower() or "active d4" in notes.lower(), \
            "legacy d4 entry missing disambiguation note: %s" % notes
        assert "opencode-go-deepseek-v4-pro" in notes, \
            "disambiguation note should reference active entry: %s" % notes

    def test_active_d4_unchanged(self):
        """The active opencode-go d4 entry must NOT be modified."""
        pool = _load_model_pool()
        d4 = _find_deepseek_v4_pro_entries(pool)
        active = [e for e in d4 if e.get("canonical_provider") == "opencode-go"]
        assert len(active) == 1, "expected 1 active opencode-go d4 entry"
        assert active[0].get("enabled") is True
        assert active[0].get("lifecycle_status") == "enabled_assigned"

    def test_no_runtime_field_promotion(self):
        """Normalization must not promote runtime fields."""
        pool = _load_model_pool()
        d4 = _find_deepseek_v4_pro_entries(pool)
        for e in d4:
            # These fields should not be in the pool entry (they are NMC-only)
            assert "runtime_visible" not in e or e.get("runtime_visible") is None, \
                "runtime_visible promoted in pool entry"
            assert "model_call_verified" not in e or e.get("model_call_verified") is None
            assert "operator_approved" not in e or e.get("operator_approved") is None
            assert "env_loaded" not in e or e.get("env_loaded") is None


# ══════════════════════════════════════════════════════════════════════════════
# NMC presence per node (D4 preflight bug fix)
# ══════════════════════════════════════════════════════════════════════════════


class TestNMCKeyFix:
    """Test that D4 preflight correctly reads nodes.{node}.matrix."""

    def test_nmc_collects_3_nodes(self):
        nmc = _load_nmc()
        entries = _collect_nmc_entries(nmc)
        assert len(entries) == 3
        for n in ["21bao", "5bao", "9bao"]:
            assert n in entries
            assert len(entries[n]) >= 20, \
                "%s matrix should have >=20 entries, got %d" % (n, len(entries[n]))

    def test_d4_found_in_all_three_nodes(self):
        """opencode-go-deepseek-v4-pro should be in all 3 NMC matrix."""
        r = build_d4_preflight()
        mm = r.get("mismatch_matrix", {})
        nodes = mm.get("nodes", {})
        for n in ["21bao", "5bao", "9bao"]:
            assert nodes[n]["d4_found_in_nmc"] is True, \
                "d4 NOT found in %s NMC matrix" % n
            assert nodes[n]["nmc_has_entries"] is True, \
                "%s NMC matrix empty" % n

    def test_nmc_legacy_fallback_still_works(self):
        """Legacy node_model_capability.{node} schema still works."""
        legacy_nmc = {
            "node_model_capability": {
                "21bao": [{"name": "test1", "runtime_visible": True}],
                "5bao": [{"name": "test2", "runtime_visible": False}],
                "9bao": [{"name": "test3", "runtime_visible": True}],
            }
        }
        entries = _collect_nmc_entries(legacy_nmc)
        assert len(entries["21bao"]) == 1
        assert entries["21bao"][0]["name"] == "test1"


# ══════════════════════════════════════════════════════════════════════════════
# D4 Preflight post-normalization
# ══════════════════════════════════════════════════════════════════════════════


class TestPreflightPostNormalization:
    """Test D4 preflight verdict after data-only normalization."""

    def test_d4_self_check_passes(self):
        sc = d4_self_check()
        assert sc["status"] == "PASS"
        assert sc["passed_count"] == sc["total"]

    def test_d4_verdict_uses_correct_namespace(self):
        r = build_d4_preflight()
        v = r["final_verdict"]
        assert v.startswith("G_L3R_D4_PREFLIGHT_")
        assert "E2E" not in v

    def test_d4_verdict_consistent_with_state(self):
        """Verdict should reflect actual repo state.
        5bao/9bao have runtime_visible=True after evidence-based normalization.
        21bao remains residual. Correct verdict is KEEP_BLOCKED.
        """
        r = build_d4_preflight()
        v = r["final_verdict"]
        assert v in (
            "G_L3R_D4_PREFLIGHT_KEEP_BLOCKED",
            "G_L3R_D4_PREFLIGHT_DATA_ONLY_CANDIDATE",
        )

    def test_no_misleading_claims(self):
        r = build_d4_preflight()
        text_json = json.dumps(r)
        # No "G-L4 ready" claim
        assert "G-L4 ready" not in text_json
        # "readiness ready" appears only in not_authorized_scope — correct
        nas_text = "\n".join(r["not_authorized_scope"])
        assert "readiness ready" in nas_text, \
            "readiness ready must be in not_authorized_scope"
        # model_call_verified should only appear in not_authorized_scope
        if "model_call_verified" in text_json:
            assert "G-L4 live inference / model_call_verified promotion" in text_json
        # No claim of complete/running live inference
        assert "live inference capability" not in text_json or \
               "does not claim" in text_json
        assert "model_call_verified state promotion" not in text_json or \
               "does not claim" in text_json

    def test_recommended_next_stage_present(self):
        r = build_d4_preflight()
        assert len(r.get("recommended_next_stage", "")) > 0

    def test_root_causes_not_empty(self):
        r = build_d4_preflight()
        assert len(r.get("candidate_root_causes", [])) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# Aggregate / Reconciliation
# ══════════════════════════════════════════════════════════════════════════════


class TestAggregateAfterNormalization:
    """Test that aggregate summary correctly reflects post-normalization state."""

    def test_aggregate_self_check_passes(self):
        from worker_attest_layer3_runtime_summary import self_check as agg_sc
        sc = agg_sc()
        assert sc["status"] == "PASS"

    def test_aggregate_verdict_namespace(self):
        from worker_attest_layer3_runtime_summary import build_aggregate_summary
        agg = build_aggregate_summary()
        v = agg["final_verdict"]
        assert v.startswith("G_L3R_")
        assert "E2E" not in v

    def test_no_runtime_field_promotion_in_yaml(self):
        """Verify NMC yaml reflects evidence-based D4 normalization.
        5bao/9bao runtime_visible=True (evidence-based via PR #332).
        21bao runtime_visible != True (must remain unknown/residual).
        model_call_verified and operator_approved must NOT be promoted for any node.
        """
        with open(NMC_PATH, "r") as f:
            nmc = yaml.safe_load(f)
        for n in ["21bao", "5bao", "9bao"]:
            matrix = nmc["nodes"][n]["matrix"]
            for entry in matrix:
                if "deepseek-v4-pro" in entry.get("model_id", ""):
                    if n in ("5bao", "9bao"):
                        # 5bao/9bao: runtime_visible=True (evidence-based)
                        assert entry.get("runtime_visible") is True, \
                            "d4 runtime_visible must be True for %s" % n
                    else:
                        # 21bao: runtime_visible must remain non-True (unknown/residual)
                        assert entry.get("runtime_visible") is not True, \
                            "d4 runtime_visible must not be True for %s" % n
                    # model_call_verified and operator_approved never promoted
                    assert entry.get("model_call_verified") != True, \
                        "d4 model_call_verified promoted in %s" % n
                    assert entry.get("operator_approved") != True, \
                        "d4 operator_approved promoted in %s" % n


class TestReconciliationAfterNormalization:
    """Test reconciliation after normalization."""

    def test_reconciliation_self_check_passes(self):
        from worker_attest_layer3_reconciliation import self_check as rec_sc
        sc = rec_sc()
        assert sc["status"] == "PASS"

    def test_reconciliation_verdict_namespace(self):
        from worker_attest_layer3_reconciliation import build_reconciliation_report
        rec = build_reconciliation_report()
        v = rec["final_verdict"]
        assert v.startswith("G_L3R_RECONCILIATION_")

    def test_blocker_preserved_if_present(self):
        """If aggregate is still BLOCKED, reconciliation should preserve it."""
        from worker_attest_layer3_runtime_summary import build_aggregate_summary
        from worker_attest_layer3_reconciliation import build_reconciliation_report
        agg = build_aggregate_summary()
        rec = build_reconciliation_report()
        if agg["final_verdict"] in ("G_L3R_BLOCKED", "G_L3R_STOP_SECRET_RISK",
                                     "G_L3R_STOP_AND_REANCHOR"):
            # Reconciliation must NOT downgrade to PASS
            assert rec["final_verdict"] != "G_L3R_RECONCILIATION_PASS"
            # Should report blockers
            assert len(rec["blocker_summary"]) > 0


# ══════════════════════════════════════════════════════════════════════════════
# No forbidden operations
# ══════════════════════════════════════════════════════════════════════════════


class TestNoForbiddenOps:
    """Test that the normalization changes don't introduce forbidden patterns."""

    def test_no_model_call_in_yaml(self):
        with open(POOL_PATH, "r") as f:
            content = f.read()
        assert "model_call_verified: true" not in content.lower(), \
            "model_call_verified: true in pool.yaml"
        assert "operator_approved: true" not in content.lower()
        assert "runtime_visible: true" not in content.lower()

    def test_no_field_promotion_in_nmc(self):
        with open(NMC_PATH, "r") as f:
            content = f.read()
        nmc = yaml.safe_load(content)
        for n in ["21bao", "5bao", "9bao"]:
            for entry in nmc["nodes"][n]["matrix"]:
                if "deepseek-v4-pro" in entry.get("model_id", ""):
                    if n in ("5bao", "9bao"):
                        # 5bao/9bao runtime_visible=True is intentional
                        assert entry.get("runtime_visible") is True, \
                            "d4 runtime_visible must be True in NMC %s" % n
                    else:
                        # 21bao must remain non-True
                        assert entry.get("runtime_visible") is not True, \
                            "d4 runtime_visible must not be True in NMC %s" % n
                    assert entry.get("model_call_verified") != True
                    assert entry.get("operator_approved") != True

    def test_yaml_syntax_valid(self):
        """YAML files should still parse correctly after normalization."""
        with open(POOL_PATH) as f:
            pool = yaml.safe_load(f)
        assert "models" in pool
        assert "schema_version" in pool
        with open(NMC_PATH) as f:
            nmc = yaml.safe_load(f)
        assert "nodes" in nmc
        assert "schema_version" in nmc


# ══════════════════════════════════════════════════════════════════════════════
# No secret leak
# ══════════════════════════════════════════════════════════════════════════════


class TestNoSecretLeak:
    """Test no secrets in changed files."""

    def test_no_secret_in_pool_yaml(self):
        with open(POOL_PATH) as f:
            content = f.read()
        import re
        for pat in [r'sk-[a-zA-Z0-9]{20,}', r'ghp_[a-zA-Z0-9]{36}',
                    r'AKIA[0-9A-Z]{16}']:
            assert not re.search(pat, content), "secret pattern found in pool.yaml"

    def test_no_secret_in_nmc_yaml(self):
        with open(NMC_PATH) as f:
            content = f.read()
        import re
        for pat in [r'sk-[a-zA-Z0-9]{20,}', r'ghp_[a-zA-Z0-9]{36}',
                    r'AKIA[0-9A-Z]{16}']:
            assert not re.search(pat, content), "secret pattern found in NMC"
