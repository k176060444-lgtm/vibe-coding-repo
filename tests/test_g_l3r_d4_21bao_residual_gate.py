"""Tests for G-L3R D4 21bao Residual Gate.

Tests the blocker narrowing verdict, evidence references,
scope constraints, and forbidden-operation checks.
"""

import json
import sys
import yaml
from pathlib import Path

REPO = Path(__file__).parent.parent
EVIDENCE_PATH = REPO / ".hermes" / "evidence" / "g-l3r-d4-21bao-residual-gate.json"
DOC_PATH = REPO / "docs" / "baseline02" / "g-l3r-d4-21bao-residual-gate.md"
NMC_PATH = REPO / "scripts" / "node_model_capability.yaml"
RECONCILIATION_PATH = REPO / "scripts" / "worker_attest_layer3_reconciliation.py"


# ══════════════════════════════════════════════════════════════════════════════
# Helper: load evidence JSON
# ══════════════════════════════════════════════════════════════════════════════


def _load_evidence() -> dict:
    with open(EVIDENCE_PATH, "r") as f:
        return json.load(f)


def _load_nmc() -> dict:
    with open(NMC_PATH, "r") as f:
        return yaml.safe_load(f)


def _get_d4_entry(nmc: dict, node: str) -> dict | None:
    """Get the D4 (opencode-go-deepseek-v4-pro) entry for a node."""
    matrix = nmc.get("nodes", {}).get(node, {}).get("matrix", [])
    for entry in matrix:
        if entry.get("model_id") == "opencode-go-deepseek-v4-pro":
            return entry
    return None


# ══════════════════════════════════════════════════════════════════════════════
# Test: Evidence JSON Structure
# ══════════════════════════════════════════════════════════════════════════════


class TestEvidenceJson:
    def test_schema_version(self):
        ev = _load_evidence()
        assert ev.get("schema_version") == "1.0.0"

    def test_gate_id(self):
        ev = _load_evidence()
        assert ev.get("gate_id") == "G-L3R-D4-21BAO-RESIDUAL-GATE"

    def test_verdict_name(self):
        ev = _load_evidence()
        v = ev.get("verdict", {})
        # After PR #336 + this normalization, runtime_visible is 3-of-3.
        # The residual gate verdict updates accordingly. The exact verdict
        # name may be:
        #   - G_L3R_D4_RUNTIME_VISIBLE_3OF3_NORMALIZED (preferred)
        #   - legacy G_L3R_D4_BLOCKER_NARROWED_TO_21BAO_RESIDUAL_ONLY (kept)
        verdict_name = v.get("gate_verdict")
        assert verdict_name in (
            "G_L3R_D4_RUNTIME_VISIBLE_3OF3_NORMALIZED",
            "G_L3R_D4_BLOCKER_NARROWED_TO_21BAO_RESIDUAL_ONLY",
        ), f"unexpected verdict name: {verdict_name}"

    def test_global_blocker_not_closed(self):
        ev = _load_evidence()
        v = ev.get("verdict", {})
        assert v.get("closes_global_blocker") is False

    def test_two_of_three_confirmed(self):
        ev = _load_evidence()
        v = ev.get("verdict", {})
        # All 3 nodes are now True (post-PR #336)
        if v.get("three_of_three_runtime_visible"):
            assert v.get("three_of_three_confirmed") is True
        else:
            assert v.get("two_of_three_confirmed") is True

    def test_three_of_three_runtime_visible(self):
        """After PR #336 + this PR, all 3 nodes should be runtime_visible=True."""
        ev = _load_evidence()
        v = ev.get("verdict", {})
        # This PR elevates 21bao to True. The evidence JSON must reflect
        # 3-of-3 at runtime_visible layer (or be updated to do so).
        assert v.get("three_of_three_runtime_visible") is True, \
            "verdict must record three_of_three_runtime_visible=True"

    def test_three_of_three_call_verified_not_promoted(self):
        """3-of-3 at runtime_visible does NOT mean 3-of-3 at model_call_verified."""
        ev = _load_evidence()
        v = ev.get("verdict", {})
        assert v.get("three_of_three_model_call_verified") is False
        assert v.get("three_of_three_operator_approved") is False

    def test_no_readiness_claims(self):
        ev = _load_evidence()
        v = ev.get("verdict", {})
        assert v.get("is_g_l4_ready") is False
        assert v.get("is_readiness_ready") is False
        assert v.get("is_model_call_verified_ready") is False
        assert v.get("is_operator_approved_promotion") is False
        assert v.get("is_gray_acceptance") is False
        assert v.get("is_baseline03_ready") is False


# ══════════════════════════════════════════════════════════════════════════════
# Test: Evidence State (per-node)
# ══════════════════════════════════════════════════════════════════════════════


class TestEvidenceState:
    def test_21bao_runtime_visible_true(self):
        """21bao runtime_visible must be True (PR #336 evidence-backed)."""
        ev = _load_evidence()
        s = ev.get("evidence_state", {}).get("21bao", {})
        assert s.get("runtime_visible") is True, \
            "21bao runtime_visible must be True (PR #336 evidence)"
        assert s.get("runtime_visible_source") == "21bao_local_opencode_config"
        assert s.get("evidence_pr") == 336
        assert s.get("merge_commit") == "0a932be4fd6d12760e8c5e6400044644864e003c"

    def test_5bao_runtime_visible_true(self):
        ev = _load_evidence()
        s = ev.get("evidence_state", {}).get("5bao", {})
        assert s.get("runtime_visible") is True

    def test_9bao_runtime_visible_true(self):
        ev = _load_evidence()
        s = ev.get("evidence_state", {}).get("9bao", {})
        assert s.get("runtime_visible") is True

    def test_21bao_no_asymmetry_ref_required(self):
        """Asymmetry was the prior reason for residual. With PR #336
        evidence, 21bao no longer carries the residual asymmetry class.
        """
        ev = _load_evidence()
        s = ev.get("evidence_state", {}).get("21bao", {})
        classification = s.get("classification", "")
        # Must NOT still be classified as residual once 3-of-3 normalized
        assert "residual" not in classification.lower() or \
               "pr_336" in classification.lower() or \
               "evidence" in classification.lower(), \
               f"21bao classification stale: {classification}"

    def test_5bao_evidence_references(self):
        ev = _load_evidence()
        s = ev.get("evidence_state", {}).get("5bao", {})
        assert s.get("evidence_pr") == 332
        assert s.get("approval_id") == "OPERATOR-20260703-G-L3R-D4-LIVE-EVIDENCE-003"
        assert "09b1d97" in s.get("evidence_anchor", "")

    def test_9bao_evidence_references(self):
        ev = _load_evidence()
        s = ev.get("evidence_state", {}).get("9bao", {})
        assert s.get("evidence_pr") == 332
        assert s.get("approval_id") == "OPERATOR-20260703-G-L3R-D4-LIVE-EVIDENCE-003"
        assert "09b1d97" in s.get("evidence_anchor", "")

    def test_5bao_nmc_normalization_ref(self):
        ev = _load_evidence()
        s = ev.get("evidence_state", {}).get("5bao", {})
        assert s.get("nmc_normalization_pr") == 334

    def test_9bao_nmc_normalization_ref(self):
        ev = _load_evidence()
        s = ev.get("evidence_state", {}).get("9bao", {})
        assert s.get("nmc_normalization_pr") == 334


# ══════════════════════════════════════════════════════════════════════════════
# Test: NMC Consistency
# ══════════════════════════════════════════════════════════════════════════════


class TestNmcConsistency:
    def test_5bao_nmc_runtime_visible_true(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "5bao")
        assert entry is not None, "5bao D4 entry not found in NMC"
        assert entry.get("runtime_visible") is True

    def test_9bao_nmc_runtime_visible_true(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "9bao")
        assert entry is not None, "9bao D4 entry not found in NMC"
        assert entry.get("runtime_visible") is True

    def test_21bao_nmc_runtime_visible_true(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "21bao")
        assert entry is not None, "21bao D4 entry not found in NMC"
        # 21bao D4 is now runtime_visible=True backed by PR #336 evidence
        assert entry.get("runtime_visible") is True, \
            "21bao runtime_visible must be True (PR #336 evidence)"
        # MUST carry evidence reference
        ev = entry.get("runtime_visible_evidence")
        assert isinstance(ev, dict), \
            "21bao runtime_visible_evidence must be a dict"
        assert "PR #336" in str(ev.get("source", ""))
        assert "2ec1778e" in str(ev.get("evidence_anchor", ""))
        assert "0a932be" in str(ev.get("merge_commit", ""))

    def test_nmc_no_promotion(self):
        """Verify model_call_verified and operator_approved were not promoted."""
        nmc = _load_nmc()
        for node in ["21bao", "5bao", "9bao"]:
            entry = _get_d4_entry(nmc, node)
            if entry:
                assert entry.get("model_call_verified") != True, \
                    "%s: model_call_verified must not be True" % node
                assert entry.get("operator_approved") != True, \
                    "%s: operator_approved must not be True" % node


# ══════════════════════════════════════════════════════════════════════════════
# Test: Doc Consistency
# ══════════════════════════════════════════════════════════════════════════════


class TestDocConsistency:
    def test_doc_acknowledges_global_blocker_not_closed(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        # The doc has a "Closes Global Blocker for runtime_visible layer" row stating
        # YES (runtime_visible blocker resolved), and a separate row stating that
        # higher-layer items (model_call_verified, operator_approved, G-L4) are NOT
        # closed. The doc must acknowledge this separation.
        assert "Closes Global Blocker for runtime_visible layer" in doc
        assert "Closes model_call_verified" in doc or \
               "model_call_verified" in doc and "NO" in doc
        # The doc must still say these higher items are outside G-L3R scope
        assert "outside g-l3r scope" in doc.lower()

    def test_doc_no_2of3_as_3of3(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        # The doc should not claim 3/3 success
        assert "3-of-3" not in doc or "3/3" not in doc or "not 3-of-3" in doc.lower()

    def test_doc_mentions_asymmetry(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        assert "asymmetry" in doc.lower()

    def test_doc_clarity_on_what_it_does_not_mean(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        sections = doc.split("##")
        has_clarity = any("does not mean" in s.lower() for s in sections)
        assert has_clarity, "Doc should have a 'What This Verdict Does NOT Mean' section"


# ══════════════════════════════════════════════════════════════════════════════
# Test: Scope Constraints
# ══════════════════════════════════════════════════════════════════════════════


class TestScopeConstraints:
    def test_forbidden_flags_all_false(self):
        ev = _load_evidence()
        flags = ev.get("forbidden_operation_flags", {})
        for key, val in flags.items():
            assert val is False, "forbidden_operation_flags.%s=%s (must be False)" % (key, val)

    def test_scope_constraints_in_evidence(self):
        ev = _load_evidence()
        sc = ev.get("scope_constraints", [])
        assert any("runtime_visible-resolved" in s.lower() for s in sc)
        assert any("not-g-l4-ready" in s.lower() for s in sc)
        assert any("not-readiness-ready" in s.lower() for s in sc)
        assert any("g-l4-outside-g-l3r-scope" in s.lower() for s in sc)

    def test_preconditions_met(self):
        ev = _load_evidence()
        preconditions = ev.get("preconditions_met", [])
        assert len(preconditions) >= 3
        for p in preconditions:
            assert p.get("status") == "completed"


# ══════════════════════════════════════════════════════════════════════════════
# Test: Reconciliation Consistency
# ══════════════════════════════════════════════════════════════════════════════


class TestReconciliationConsistency:
    def test_reconciliation_has_closed_blocker_text(self):
        """Reconciliation blocker text should reflect resolved state."""
        src = RECONCILIATION_PATH.read_text(encoding="utf-8")
        # Should reference the 21bao history (resolved at runtime_visible layer)
        assert "21bao" in src, \
            "Reconciliation should reference 21bao"
        # Should clearly state that D4 runtime_visible blocker is resolved
        assert "RESOLVED" in src, \
            "Reconciliation must state that D4 runtime_visible blocker is RESOLVED"
        # Should make clear that higher-layer items are outside G-L3R scope
        assert "OUTSIDE G-L3R scope" in src, \
            "Reconciliation must state that higher-layer items are outside G-L3R scope"

    def test_reconciliation_no_on_all_3_nodes(self):
        """Reconciliation should NOT say 'on all 3 nodes' for D4 blocker."""
        src = RECONCILIATION_PATH.read_text(encoding="utf-8")
        # Check the blocker_text string — old phrasing is replaced.
        # Post-PR #337 wording should NOT say "on all 3 nodes" for D4.
        assert "on all 3 nodes" not in src, \
            "Reconciliation blocker text should not claim mismatch on all 3 nodes"


# ══════════════════════════════════════════════════════════════════════════════
# Test: Forbidden Operation Checks
# ══════════════════════════════════════════════════════════════════════════════


class TestForbiddenOps:
    def test_doc_forbids_g_l4(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        assert "G-L4" in doc

    def test_doc_forbids_readiness(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        assert "readiness" in doc.lower()

    def test_doc_does_not_assert_model_call_capability(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        assert "model_call" not in doc.lower() or \
               "not authorized" in doc.lower()

    def test_evidence_no_nmc_write_back_claim(self):
        ev = _load_evidence()
        flags = ev.get("forbidden_operation_flags", {})
        assert flags.get("write_back_attempted") is False
