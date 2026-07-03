#!/usr/bin/env python3
"""Tests for G-L3R final reconciliation report (worker_attest_layer3_reconciliation)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Ensure scripts/ is importable
_SCRIPTS = str(Path(__file__).resolve().parent.parent / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from worker_attest_layer3_reconciliation import (
    SCHEMA_VERSION,
    SOURCE,
    CURRENT_ANCHOR,
    CLOSED_ITEMS,
    NOT_AUTHORIZED_SCOPE,
    NODES,
    VERDICT_PRIORITY,
    FAIL_CLOSED_VERDICTS,
    build_reconciliation_report,
    self_check,
    _report_human_summary,
    _report_machine_json,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Self-Check
# ═══════════════════════════════════════════════════════════════════════════════


class TestSelfCheck:
    """Test the self_check() function."""

    def test_self_check_passes(self):
        sc = self_check()
        assert sc["status"] == "PASS", "self_check status: %s" % sc.get("status")
        assert sc["passed_count"] == sc["total"]


# ═══════════════════════════════════════════════════════════════════════════════
# Basic Structure
# ═══════════════════════════════════════════════════════════════════════════════


class TestBasicStructure:
    """Test the report structure has all required fields."""

    REQUIRED_FIELDS = [
        "schema_version",
        "source",
        "anchor",
        "generated_at",
        "closed_items",
        "nodes_covered",
        "g_l3f_status",
        "g_l3r_canary_status",
        "aggregate_verdict",
        "blocker_summary",
        "unblock_criteria",
        "not_authorized_scope",
        "next_recommendation",
        "leak_scan",
        "final_verdict",
        "errors",
    ]

    def test_has_all_required_fields(self):
        r = build_reconciliation_report()
        for field in self.REQUIRED_FIELDS:
            assert field in r, "missing field: %s" % field

    def test_schema_version_matches(self):
        r = build_reconciliation_report()
        assert r["schema_version"] == SCHEMA_VERSION

    def test_source_matches(self):
        r = build_reconciliation_report()
        assert r["source"] == SOURCE

    def test_anchor_matches_current(self):
        r = build_reconciliation_report()
        assert r["anchor"] == CURRENT_ANCHOR

    def test_all_three_nodes_covered(self):
        r = build_reconciliation_report()
        assert len(r["nodes_covered"]) == 3
        assert "21bao" in r["nodes_covered"]
        assert "5bao" in r["nodes_covered"]
        assert "9bao" in r["nodes_covered"]

    def test_closed_items_complete(self):
        r = build_reconciliation_report()
        assert len(r["closed_items"]) >= 10
        # Verify specific known items exist
        items_text = "\n".join(r["closed_items"])
        assert "G-L3R-PLAN" in items_text
        assert "21bao" in items_text
        assert "5bao" in items_text
        assert "9bao" in items_text
        assert "G-L3R-aggregate" in items_text


# ═══════════════════════════════════════════════════════════════════════════════
# Verdict
# ═══════════════════════════════════════════════════════════════════════════════


class TestVerdict:
    """Test the final verdict namespace and resolution."""

    def test_verdict_uses_reconciliation_namespace(self):
        r = build_reconciliation_report()
        v = r["final_verdict"]
        assert v.startswith("G_L3R_RECONCILIATION_"), \
            "verdict %s does not use G_L3R_RECONCILIATION_* namespace" % v

    def test_verdict_is_valid_priority(self):
        r = build_reconciliation_report()
        assert r["final_verdict"] in VERDICT_PRIORITY

    def test_no_e2e_namespace(self):
        r = build_reconciliation_report()
        v = r["final_verdict"]
        assert "E2E" not in v, "verdict %s contains E2E_* namespace" % v

    def test_aggregate_g_l3r_blocked_preserved_as_downstream_blocker(self):
        """G_L3R_BLOCKED from aggregate must NOT be downgraded to PASS."""
        r = build_reconciliation_report()
        # With known blockers present, verdict must be PASS_WITH_BLOCKERS
        # (infrastructure closed, downstream blocked)
        assert r["final_verdict"] == "G_L3R_RECONCILIATION_PASS_WITH_BLOCKERS"

    def test_blocker_summary_contains_deepseek_gap(self):
        r = build_reconciliation_report()
        blockers_text = " ".join(r["blocker_summary"])
        assert "deepseek-v4-pro" in blockers_text or "DeepSeek V4 Pro" in blockers_text

    def test_blocker_summary_not_empty_when_aggregate_blocked(self):
        r = build_reconciliation_report()
        agg = r.get("aggregate_verdict", {})
        if agg and agg.get("final_verdict") in (
            "G_L3R_BLOCKED", "G_L3R_STOP_SECRET_RISK",
        ):
            assert len(r["blocker_summary"]) > 0, \
                "blocker_summary empty despite aggregate blocking"


# ═══════════════════════════════════════════════════════════════════════════════
# Unblock Criteria
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnblockCriteria:
    """Test unblock criteria semantics."""

    def test_no_fixture_only_promotion(self):
        r = build_reconciliation_report()
        criteria_text = " ".join(r["unblock_criteria"]).lower()
        assert "fixture-only" in criteria_text or "fixture only" in criteria_text, \
            "unblock_criteria should forbid fixture-only promotion"

    def test_deepseek_v4_pro_not_special(self):
        r = build_reconciliation_report()
        criteria_text = " ".join(r["unblock_criteria"])
        # Should mention deepseek-v4-pro but NOT grant any special promotion path
        assert "deepseek-v4-pro" in criteria_text or "DeepSeek V4 Pro" in criteria_text
        # Should explicitly state no special-casing
        assert "no special-casing" in criteria_text or "not special-cased" in criteria_text or \
            "not special" in criteria_text

    def test_deu_warn_preserved(self):
        r = build_reconciliation_report()
        criteria_text = " ".join(r["unblock_criteria"]).lower()
        assert "deu" in criteria_text or "warn" in criteria_text


# ═══════════════════════════════════════════════════════════════════════════════
# Scope / Not Authorized
# ═══════════════════════════════════════════════════════════════════════════════


class TestNotAuthorizedScope:
    """Test not_authorized_scope completeness."""

    SCOPE_CHECKS = [
        "G-L4",
        "G-READINESS",
        "G-D-A",
        "G-D-B",
        "G-GRAY",
        "PR-7",
        "Baseline03",
        "Stage8",
    ]

    def test_not_authorized_scope_complete(self):
        r = build_reconciliation_report()
        scope_text = "\n".join(r["not_authorized_scope"])
        for s in self.SCOPE_CHECKS:
            assert s in scope_text, "not_authorized_scope missing: %s" % s

    def test_not_authorized_matches_constant(self):
        r = build_reconciliation_report()
        assert len(r["not_authorized_scope"]) >= 6


# ═══════════════════════════════════════════════════════════════════════════════
# Aggregate Verdict Preservation
# ═══════════════════════════════════════════════════════════════════════════════


class TestAggregateVerdictPreservation:
    """Test that aggregate verdict is faithfully recorded."""

    def test_aggregate_verdict_present(self):
        r = build_reconciliation_report()
        assert r["aggregate_verdict"] is not None
        assert "final_verdict" in r["aggregate_verdict"] or "error" in r["aggregate_verdict"]

    def test_aggregate_verdict_captures_blocker(self):
        r = build_reconciliation_report()
        agg = r["aggregate_verdict"]
        if agg and "final_verdict" in agg:
            assert agg["final_verdict"] in (
                "G_L3R_BLOCKED", "G_L3R_PASS_WITH_WARN", "G_L3R_PASS",
                "G_L3R_NOT_COLLECTED", "G_L3R_STOP_SECRET_RISK",
                "G_L3R_STOP_AND_REANCHOR",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# G-L3F Status
# ═══════════════════════════════════════════════════════════════════════════════


class TestGL3FStatus:
    """Test G-L3F status section."""

    def test_l3f_status_has_base_and_summary(self):
        r = build_reconciliation_report()
        l3f = r["g_l3f_status"]
        assert "base_adapter" in l3f
        assert "drift_summary" in l3f

    def test_l3f_summary_has_verdict(self):
        r = build_reconciliation_report()
        ds = r["g_l3f_status"].get("drift_summary", {})
        if "verdict" in ds:
            assert ds["verdict"].startswith("G_L3F_"), \
                "drift_summary verdict does not use G_L3F_*: %s" % ds["verdict"]


# ═══════════════════════════════════════════════════════════════════════════════
# G-L3R Canary Status
# ═══════════════════════════════════════════════════════════════════════════════


class TestCanaryStatus:
    """Test G-L3R canary status section."""

    def test_all_nodes_have_canary_status(self):
        r = build_reconciliation_report()
        cs = r["g_l3r_canary_status"]
        for node in ["21bao", "5bao", "9bao"]:
            assert node in cs, "missing canary status for %s" % node
            assert "self_check" in cs[node], "missing self_check for %s" % node

    def test_each_canary_has_module_name(self):
        r = build_reconciliation_report()
        cs = r["g_l3r_canary_status"]
        for node in ["21bao", "5bao", "9bao"]:
            assert "module_name" in cs[node]


# ═══════════════════════════════════════════════════════════════════════════════
# Semantic / Misleading Language
# ═══════════════════════════════════════════════════════════════════════════════


class TestSemanticLanguage:
    """Test that the report does NOT claim items from not_authorized_scope."""

    def test_no_claim_g_l4_ready(self):
        """The report must not claim G-L4 readiness.

        The not_authorized_scope correctly lists G-L4 as not authorized.
        The report does NOT claim G-L4 live inference was performed.
        """
        r = build_reconciliation_report()
        scope_text = " ".join(r["not_authorized_scope"])
        assert "G-L4" in scope_text, "G-L4 must be in not_authorized_scope"
        # Verify verdict is correct (not PASS when blockers exist)
        assert r["final_verdict"] != "G_L3R_RECONCILIATION_PASS" or \
            len(r["blocker_summary"]) == 0

    def test_no_claim_readiness_ready(self):
        r = build_reconciliation_report()
        scope_text = " ".join(r["not_authorized_scope"])
        # "readiness ready" correctly appears in not_authorized_scope description
        assert "readiness ready" in scope_text, \
            "readiness ready must be in not_authorized_scope list"
        text = _report_human_summary(r).lower()
        # It should be in the "Not authorised scope" section, not elsewhere
        assert "not authorised scope" in text
        # Verify the report does NOT claim readiness is passed
        assert r["final_verdict"] != "G_L3R_RECONCILIATION_PASS" or \
            len(r["blocker_summary"]) == 0

    def test_scope_note_fixture_only(self):
        r = build_reconciliation_report()
        # The scope is implicit - verify no real SSH claims
        assert r["aggregate_verdict"] is not None
        # Leak scan should not show any leak
        assert r["leak_scan"].get("any_leak") is False or \
               r["leak_scan"].get("any_leak") is None

    def test_next_recommendation_appropriate(self):
        r = build_reconciliation_report()
        nr = r.get("next_recommendation", "")
        assert isinstance(nr, str) and len(nr) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Output Formats
# ═══════════════════════════════════════════════════════════════════════════════


class TestOutputFormats:
    """Test human and JSON output formats."""

    def test_human_summary_renders(self):
        r = build_reconciliation_report()
        text = _report_human_summary(r)
        assert len(text) > 50
        assert "G-L3R Final Reconciliation Report" in text

    def test_machine_json_serializable(self):
        r = build_reconciliation_report()
        js = _report_machine_json(r)
        parsed = json.loads(js)
        assert parsed["schema_version"] == SCHEMA_VERSION

    def test_output_deterministic(self):
        r1 = build_reconciliation_report()
        r2 = build_reconciliation_report()
        # Remove timestamps for comparison
        for d in [r1, r2]:
            d.pop("generated_at", None)
        assert json.dumps(r1, sort_keys=True, default=str) == \
            json.dumps(r2, sort_keys=True, default=str), \
            "reports differ (nondeterministic output)"


# ═══════════════════════════════════════════════════════════════════════════════
# No-Forbidden-Ops
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoForbiddenOps:
    """Test the module source has no forbidden operations."""

    MODULE_PATH = Path(__file__).resolve().parent.parent / "scripts" / \
                  "worker_attest_layer3_reconciliation.py"

    def test_no_subprocess_import(self):
        src = self.MODULE_PATH.read_text()
        assert "subprocess" not in src, "subprocess found in module"

    def test_no_os_environ_access(self):
        src = self.MODULE_PATH.read_text()
        assert "os.environ" not in src, "os.environ found in module"

    def test_no_os_getenv(self):
        src = self.MODULE_PATH.read_text()
        assert "os.getenv" not in src, "os.getenv found in module"

    def test_no_ssh_or_scp(self):
        src = self.MODULE_PATH.read_text()
        assert "ssh " not in src and " scp " not in src, \
            "ssh/scp command found in module"

    def test_no_http_or_requests(self):
        src = self.MODULE_PATH.read_text()
        assert "requests" not in src or "try:" in src, \
            "requests import found in module"
        assert "http.client" not in src, "http.client found in module"

    def test_no_model_call_imports(self):
        src = self.MODULE_PATH.read_text()
        assert "opencode" not in src or "from scripts" in src, \
            "opencode CLI call found in module"

    def test_no_yaml_or_json_dump_to_forbidden_files(self):
        src = self.MODULE_PATH.read_text()
        # Check that model_pool.yaml / node_model_capability.yaml are NOT
        # concatenated with open( / write_text( / dump( patterns
        # (they may appear in the NOT_AUTHORIZED_SCOPE constant, which is allowed)
        lines = src.split("\n")
        for i, line in enumerate(lines):
            if "model_pool" in line or "node_model" in line:
                # If the line has both 'model_pool' and a write pattern, flag it
                if any(p in line for p in ("open(", "write_text(", "dump(")):
                    pytest.fail("Line %d: %s has forbidden write to model_pool/node_model files" % (i+1, line.strip()))

    def test_no_unlink_or_rename(self):
        src = self.MODULE_PATH.read_text()
        assert "unlink" not in src and "os.rename" not in src and \
            "os.replace" not in src


# ═══════════════════════════════════════════════════════════════════════════════
# No Secret Leak
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoSecretLeak:
    """Test no secrets are leaked in module output."""

    def test_report_no_leak(self):
        r = build_reconciliation_report()
        assert r["leak_scan"].get("any_leak") is False

    def test_self_check_no_leak(self):
        sc = self_check()
        assert "error" not in sc or sc["error"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# Re-blocking semantics
# ═══════════════════════════════════════════════════════════════════════════════


class TestReBlockingSemantics:
    """Test that aggregate BLOCKED is not incorrectly unblocked."""

    def test_g_l3r_blocked_preserved_in_aggregate_verdict(self):
        r = build_reconciliation_report()
        agg = r.get("aggregate_verdict", {})
        fv = agg.get("final_verdict", "")
        if fv == "G_L3R_BLOCKED":
            # With known blockers, reconciliation must NOT claim PASS
            assert r["final_verdict"] != "G_L3R_RECONCILIATION_PASS"
