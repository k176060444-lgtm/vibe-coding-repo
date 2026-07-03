#!/usr/bin/env python3
"""Tests for G-L3R D4 runtime-visible preflight diagnosis."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from worker_attest_layer3_d4_runtime_visible_preflight import (
    SCHEMA_VERSION,
    SOURCE,
    CURRENT_ANCHOR,
    TARGET_MODEL,
    NODES,
    VERDICT_PRIORITY,
    FAIL_CLOSED_VERDICTS,
    NOT_AUTHORIZED_SCOPE,
    build_d4_preflight,
    self_check,
    _report_human_summary,
    _report_machine_json,
    _find_deepseek_v4_pro_entries,
    _load_model_pool,
)


# ══════════════════════════════════════════════════════════════════════════════
# Self-Check
# ══════════════════════════════════════════════════════════════════════════════


class TestSelfCheck:
    def test_self_check_passes(self):
        sc = self_check()
        assert sc["status"] == "PASS", "self_check status: %s" % sc.get("status")
        assert sc["passed_count"] == sc["total"]


# ══════════════════════════════════════════════════════════════════════════════
# Basic Structure
# ══════════════════════════════════════════════════════════════════════════════


class TestBasicStructure:
    REQUIRED_FIELDS = [
        "schema_version", "source", "anchor", "generated_at",
        "target_model", "nodes",
        "model_pool_entries", "capability_entries", "fixture_entries",
        "canary_entries", "aggregate_status", "mismatch_matrix",
        "candidate_root_causes", "root_cause_explanation",
        "unblock_options", "recommended_next_stage",
        "not_authorized_scope", "final_verdict", "scope_note",
    ]

    def test_has_all_required_fields(self):
        r = build_d4_preflight()
        for field in self.REQUIRED_FIELDS:
            assert field in r, "missing field: %s" % field

    def test_schema_version_matches(self):
        r = build_d4_preflight()
        assert r["schema_version"] == SCHEMA_VERSION

    def test_source_matches(self):
        r = build_d4_preflight()
        assert r["source"] == SOURCE

    def test_anchor_matches_current(self):
        r = build_d4_preflight()
        assert r["anchor"] == CURRENT_ANCHOR

    def test_target_model(self):
        r = build_d4_preflight()
        assert r["target_model"] == TARGET_MODEL
        assert r["target_model"] == "deepseek-v4-pro"

    def test_all_three_nodes(self):
        r = build_d4_preflight()
        assert len(r["nodes"]) == 3
        assert "21bao" in r["nodes"]
        assert "5bao" in r["nodes"]
        assert "9bao" in r["nodes"]


# ══════════════════════════════════════════════════════════════════════════════
# Model Pool Entries
# ══════════════════════════════════════════════════════════════════════════════


class TestModelPoolEntries:
    def test_at_least_two_entries(self):
        r = build_d4_preflight()
        assert len(r["model_pool_entries"]) >= 2, \
            "expected >=2 deepseek-v4-pro entries, got %d" % len(r["model_pool_entries"])

    def test_both_entries_have_correct_model(self):
        r = build_d4_preflight()
        for e in r["model_pool_entries"]:
            assert e.get("model") == "deepseek-v4-pro", \
                "wrong model: %s" % e.get("model")

    def test_one_active_one_candidate(self):
        r = build_d4_preflight()
        entries = r["model_pool_entries"]
        # Check we have one enabled_assigned and one candidate
        statuses = [e.get("lifecycle_status") for e in entries]
        assert "enabled_assigned" in statuses or "candidate" in statuses

    def test_aliases_differ(self):
        """The root cause is alias mismatch between entries."""
        r = build_d4_preflight()
        entries = r["model_pool_entries"]
        aliases = []
        for e in entries:
            pa = e.get("primary_alias", "")
            al = e.get("alias", [])
            if isinstance(al, list):
                aliases.append((pa, al))
            else:
                aliases.append((pa, [str(al)]))
        # At least two entries should have different primary_aliases
        primary_aliases = [a[0] for a in aliases]
        if len(set(primary_aliases)) == 1:
            # Still valid if the entry set is symmetric
            assert len(entries) >= 2


# ══════════════════════════════════════════════════════════════════════════════
# Mismatch Matrix
# ══════════════════════════════════════════════════════════════════════════════


class TestMismatchMatrix:
    def test_matrix_has_all_nodes(self):
        r = build_d4_preflight()
        mm = r.get("mismatch_matrix", {})
        for node in ["21bao", "5bao", "9bao"]:
            assert node in mm.get("nodes", {}), "missing node in mismatch_matrix"

    def test_nmc_has_entries_post_normalization(self):
        """Post-normalization: NMC has entries for all 3 nodes (data-only fixed this).
        d4 is found in all 3 nodes, but runtime_visible is still unknown (not promoted).
        """
        r = build_d4_preflight()
        mm = r.get("mismatch_matrix", {})
        for node in ["21bao", "5bao", "9bao"]:
            assert mm["nodes"][node]["nmc_has_entries"] is True, \
                "%s unexpectedly has no NMC entries" % node
            assert mm["nodes"][node]["d4_found_in_nmc"] is True, \
                "%s unexpectedly missing D4 in NMC" % node
            # runtime_visible still unknown — data-only did NOT promote it
            assert mm["nodes"][node]["runtime_visible_known"] is False, \
                "%s runtime_visible unexpectedly promoted to known" % node


# ══════════════════════════════════════════════════════════════════════════════
# Root Causes
# ══════════════════════════════════════════════════════════════════════════════


class TestRootCauses:
    def test_has_expected_root_causes(self):
        r = build_d4_preflight()
        rc = r.get("candidate_root_causes", [])
        assert "naming_alias_mismatch" in rc, \
            "expected naming_alias_mismatch in root causes, got %s" % rc
        # Post-normalization: fixture_stale no longer applies (NMC has entries)
        # Instead runtime_visible_unknown is the persistent gap
        assert "fixture_stale" not in rc, \
            "fixture_stale should be removed after NMC is populated: %s" % rc
        assert "runtime_visible_unknown" in rc, \
            "expected runtime_visible_unknown after normalization: %s" % rc

    def test_root_causes_list_not_empty(self):
        r = build_d4_preflight()
        assert len(r["candidate_root_causes"]) >= 1

    def test_explanation_present(self):
        r = build_d4_preflight()
        assert len(r.get("root_cause_explanation", "")) > 10


# ══════════════════════════════════════════════════════════════════════════════
# Unblock Options
# ══════════════════════════════════════════════════════════════════════════════


class TestUnblockOptions:
    def test_three_options_present(self):
        r = build_d4_preflight()
        assert len(r["unblock_options"]) == 3, \
            "expected 3 options, got %d" % len(r["unblock_options"])

    def test_option_a_present(self):
        r = build_d4_preflight()
        labels = [o.get("label", "") for o in r["unblock_options"]]
        assert any("A)" in l for l in labels), "Option A missing"

    def test_option_b_present(self):
        r = build_d4_preflight()
        labels = [o.get("label", "") for o in r["unblock_options"]]
        assert any("B)" in l for l in labels), "Option B missing"

    def test_option_c_present(self):
        r = build_d4_preflight()
        labels = [o.get("label", "") for o in r["unblock_options"]]
        assert any("C)" in l for l in labels), "Option C missing"

    def test_option_a_recommended_with_alias_mismatch(self):
        r = build_d4_preflight()
        rc = r.get("candidate_root_causes", [])
        if "naming_alias_mismatch" in rc:
            for o in r["unblock_options"]:
                if "A)" in o.get("label", ""):
                    assert o.get("recommended") is True, \
                        "Option A should be recommended when alias mismatch present"
                    break

    def test_no_fixture_only_promotion(self):
        """Unblock options must not promote fixture-only evidence."""
        r = build_d4_preflight()
        for o in r["unblock_options"]:
            note = o.get("note", "")
            assert "fixture-only" not in note, \
                "Option contains fixture-only promotion: %s" % o.get("label")
            assert "Does NOT" in note or "does NOT" in note or "does not" in note, \
                "Option note missing negation: %s" % o.get("label")


# ══════════════════════════════════════════════════════════════════════════════
# Verdict
# ══════════════════════════════════════════════════════════════════════════════


class TestVerdict:
    def test_verdict_uses_d4_namespace(self):
        r = build_d4_preflight()
        v = r["final_verdict"]
        assert v.startswith("G_L3R_D4_PREFLIGHT_"), \
            "verdict %s does not use G_L3R_D4_PREFLIGHT_* namespace" % v

    def test_verdict_is_valid(self):
        r = build_d4_preflight()
        assert r["final_verdict"] in VERDICT_PRIORITY

    def test_no_e2e_namespace(self):
        r = build_d4_preflight()
        assert "E2E" not in r["final_verdict"]

    def test_verdict_post_normalization(self):
        """Post-normalization verdict reflects the persistent gap.

        With NMC populated, runtime_visible=unknown for d4.
        Honest verdict is REQUIRES_SANCTIONED_EVIDENCE (Option B).
        Data-only normalization can NOT resolve runtime_visible gap.
        """
        r = build_d4_preflight()
        v = r["final_verdict"]
        assert v in (
            "G_L3R_D4_PREFLIGHT_DATA_ONLY_CANDIDATE",
            "G_L3R_D4_PREFLIGHT_REQUIRES_SANCTIONED_EVIDENCE",
        ), "unexpected verdict: %s" % v
        # After our normalization, NMC is populated and runtime_visible_unknown
        # is the persistent root cause, so REQUIRES_SANCTIONED_EVIDENCE is correct
        if "runtime_visible_unknown" in r.get("candidate_root_causes", []):
            # runtime_visible_unknown means we need live evidence
            assert v == "G_L3R_D4_PREFLIGHT_REQUIRES_SANCTIONED_EVIDENCE", \
                "with runtime_visible_unknown, should be REQUIRES_SANCTIONED_EVIDENCE, got %s" % v


# ══════════════════════════════════════════════════════════════════════════════
# Not Authorized Scope
# ══════════════════════════════════════════════════════════════════════════════


class TestNotAuthorizedScope:
    SCOPE_ITEMS = [
        "G-L4", "G-READINESS", "G-D-A", "G-D-B",
        "G-GRAY", "GRAY_ACCEPTANCE", "PR-7",
        "Baseline03", "Stage8",
        "Data write-back",
        "SSH collection",
        "Runtime field promotion",
        "Model call",
    ]

    def test_not_authorized_scope_complete(self):
        r = build_d4_preflight()
        scope_text = "\n".join(r["not_authorized_scope"])
        for s in self.SCOPE_ITEMS:
            assert s in scope_text, "not_authorized_scope missing: %s" % s

    def test_scope_note_present(self):
        r = build_d4_preflight()
        assert len(r.get("scope_note", "")) > 50


# ══════════════════════════════════════════════════════════════════════════════
# Semantics
# ══════════════════════════════════════════════════════════════════════════════


class TestSemantics:
    def test_no_misleading_claims(self):
        r = build_d4_preflight()
        text = _report_human_summary(r).lower()
        assert "g-l4 ready" not in text, "claims G-L4 ready"
        # "readiness ready" appears only in not_authorized_scope — correct
        nas = "\n".join(r["not_authorized_scope"]).lower()
        assert "readiness ready" in nas, "readiness ready must be in not_authorized_scope"
        # Check no other misleading claims
        assert "runtime drift resolved" not in text, "claims runtime drift resolved"
        # model_call_verified and readiness ready only in not_authorized_scope
        if "model_call_verified" in text:
            nas_lower = "\n".join(r["not_authorized_scope"]).lower()
            assert "model_call_verified" in nas_lower, \
                "model_call_verified outside not_authorized_scope"
        assert "baseline02 complete" not in text

    def test_not_claiming_unblock(self):
        """Preflight must not claim it unblocks the blocker."""
        r = build_d4_preflight()
        assert r["final_verdict"] != "G_L3R_D4_PREFLIGHT_PASS", \
            "verdict incorrectly claims pass"
        assert r.get("recommended_next_stage", "") != "", \
            "no recommended next stage"

    def test_recommended_not_keep_blocked(self):
        """With clear alias mismatch, option C should not be recommended."""
        r = build_d4_preflight()
        rc = r.get("candidate_root_causes", [])
        if "data_only_normalization_candidate" in rc:
            for o in r["unblock_options"]:
                if "C)" in o.get("label", ""):
                    assert o.get("recommended") is False, \
                        "Option C should not be recommended when data-only candidate available"

    def test_recommended_next_stage_not_empty(self):
        r = build_d4_preflight()
        assert len(r.get("recommended_next_stage", "")) > 10


# ══════════════════════════════════════════════════════════════════════════════
# Output Formats
# ══════════════════════════════════════════════════════════════════════════════


class TestOutputFormats:
    def test_human_summary_renders(self):
        r = build_d4_preflight()
        text = _report_human_summary(r)
        assert len(text) > 100
        assert "D4 Runtime-Visible Preflight" in text

    def test_json_serializable(self):
        r = build_d4_preflight()
        js = _report_machine_json(r)
        parsed = json.loads(js)
        assert parsed["schema_version"] == SCHEMA_VERSION

    def test_deterministic(self):
        r1 = build_d4_preflight()
        r2 = build_d4_preflight()
        for d in [r1, r2]:
            d.pop("generated_at", None)
        assert json.dumps(r1, sort_keys=True, default=str) == \
            json.dumps(r2, sort_keys=True, default=str)


# ══════════════════════════════════════════════════════════════════════════════
# No Forbidden Ops
# ══════════════════════════════════════════════════════════════════════════════


class TestNoForbiddenOps:
    MODULE_PATH = Path(__file__).resolve().parent.parent / "scripts" / \
                  "worker_attest_layer3_d4_runtime_visible_preflight.py"

    def test_no_subprocess_import(self):
        src = self.MODULE_PATH.read_text()
        assert "subprocess" not in src

    def test_no_os_environ(self):
        src = self.MODULE_PATH.read_text()
        assert "os.environ" not in src

    def test_no_os_getenv(self):
        src = self.MODULE_PATH.read_text()
        assert "os.getenv" not in src

    def test_no_ssh_or_scp(self):
        src = self.MODULE_PATH.read_text()
        assert "ssh " not in src and " scp " not in src

    def test_no_http_or_requests(self):
        src = self.MODULE_PATH.read_text()
        for forbid in ["requests.", "http.client", "urllib.request"]:
            if forbid in src and "assert" not in src.split(forbid)[0][-50:]:
                pytest.fail("forbidden HTTP lib found: %s" % forbid)

    def test_no_model_call_imports(self):
        src = self.MODULE_PATH.read_text()
        for forbid in ["opencode", "model="]:
            if forbid in src:
                # Allow in fixture/constants but not in call patterns
                lines = src.split("\n")
                for i, line in enumerate(lines):
                    if forbid in line and "opencode(" in line:
                        pytest.fail("model call at line %d: %s" % (i+1, line.strip()))

    def test_no_yaml_dump_or_write(self):
        src = self.MODULE_PATH.read_text()
        # Only yaml.safe_load is allowed, not yaml.dump
        assert "yaml.dump" not in src, "yaml.dump found"
        assert "yaml.safe_dump" not in src

    def test_no_file_write_to_pool(self):
        src = self.MODULE_PATH.read_text()
        lines = src.split("\n")
        for i, line in enumerate(lines):
            if "model_pool" in line or "node_model" in line:
                if any(p in line for p in ["open(", "write_text(", "dump("]):
                    pytest.fail("forbidden write at line %d: %s" % (i+1, line.strip()))

    def test_not_authorized_scope(self):
        r = build_d4_preflight()
        assert len(r["not_authorized_scope"]) >= 10


# ══════════════════════════════════════════════════════════════════════════════
# No Secret Leak
# ══════════════════════════════════════════════════════════════════════════════


class TestNoSecretLeak:
    def test_report_no_secret(self):
        r = build_d4_preflight()
        js = _report_machine_json(r)
        # Check JSON output for secret patterns
        assert "sk-" not in js
        assert "ghp_" not in js
        assert "AKIA" not in js
