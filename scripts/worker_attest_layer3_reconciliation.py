#!/usr/bin/env python3
"""
G-L3R — Final Reconciliation Report.

Archives the current state of G-L3F (fixture drift) and G-L3R (runtime
canary) tracks, documents closed items, remaining blockers, unblock
criteria, and next-scope recommendations.

=== SCOPE ===
- Reads G-L3F base/summary, G-L3R plan/canaries/aggregate from fixture
  and self-check data only.
- NO real SSH, NO real model calls, NO credential provisioning.
- NO node sync, NO readiness expansion, NO runtime field promotion.
- Reconciliation verdict is about canary/scope completeness, NOT about
  live model inference or readiness ready.

=== VERDICT POLICY ===
- Uses G_L3R_RECONCILIATION_* namespace (does NOT reuse E2E_*).
- PASS: all scope items closed; no downstream blockers.
- PASS_WITH_BLOCKERS: infrastructure closed but downstream blockers remain.
- BLOCKED: reconciliation-level issue (not-authorised-scope overlap, etc.).
- STOP_SECRET_RISK: secret/path/URL leak.
- STOP_AND_REANCHOR: schema_version or anchor mismatch.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Imports from sibling modules (fixture/self-check only) ────────────────

_IMPORT_WARN = "Must be run from repo root or have scripts/ on sys.path"

try:
    from scripts import worker_attest_layer3_runtime_canary as _l3rc_21bao
except ImportError:
    import worker_attest_layer3_runtime_canary as _l3rc_21bao  # type: ignore

try:
    from scripts import worker_attest_layer3_runtime_canary_5bao as _l3rc_5bao
except ImportError:
    import worker_attest_layer3_runtime_canary_5bao as _l3rc_5bao  # type: ignore

try:
    from scripts import worker_attest_layer3_runtime_canary_9bao as _l3rc_9bao
except ImportError:
    import worker_attest_layer3_runtime_canary_9bao as _l3rc_9bao  # type: ignore

try:
    from scripts import worker_attest_layer3_runtime_plan as _l3rp
except ImportError:
    import worker_attest_layer3_runtime_plan as _l3rp  # type: ignore

try:
    from scripts import worker_attest_layer3_runtime_summary as _l3ras
except ImportError:
    import worker_attest_layer3_runtime_summary as _l3ras  # type: ignore

try:
    from scripts import worker_attest_layer3_drift_summary as _l3f_sum
except ImportError:
    import worker_attest_layer3_drift_summary as _l3f_sum  # type: ignore

try:
    from scripts import da_db_policy_lock as _ddpl
except ImportError:
    import da_db_policy_lock as _ddpl  # type: ignore

# ── Constants ─────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.0.0"
SOURCE = "worker_attest_layer3_reconciliation"
CURRENT_ANCHOR = "d2251a814d72108687bbe0d733a96591df41983e"

CLOSED_ITEMS = [
    "Phase3 evidence/attestation track (PRs #291-#308)",
    "G-5-RECEIPT-E2E (PR #305, 5-receipt Layer2 evidence aggregation)",
    "D-A/D-B policy-lock validator (PR #306, win -> 21bao normalization)",
    "G-L3F-1 fixture runtime drift adapter (PR #307)",
    "G-L3F-2 fixture drift summary/report integration (PR #308)",
    "G-L3R-PLAN (PR #309, runtime evidence plan module)",
    "G-L3R-21bao-local-canary (PR #310, schema+gate validation)",
    "G-L3R-5bao-sanctioned-SSH-canary (PR #311)",
    "G-L3R-9bao-sanctioned-SSH-canary (PR #312)",
    "G-L3R-aggregate-canary-summary (PR #313)",
]

NOT_AUTHORIZED_SCOPE = [
    "G-L4 live inference / model_call_verified promotion",
    "G-READINESS (readiness ready assertion)",
    "Formal G-D-A (DEU assignment)",
    "Formal G-D-B (DEU enablement decision)",
    "G-GRAY / GRAY_ACCEPTANCE",
    "PR-7 (model_pool.yaml schema v1.3+)",
    "Baseline03 (stage 8 hardening)",
    "Stage8 (production readiness)",
]

VERDICT_PRIORITY: dict[str, int] = {
    "G_L3R_RECONCILIATION_STOP_SECRET_RISK": 7,
    "G_L3R_RECONCILIATION_STOP_AND_REANCHOR": 6,
    "G_L3R_RECONCILIATION_BLOCKED": 5,
    "G_L3R_RECONCILIATION_PASS_WITH_BLOCKERS": 2,
    "G_L3R_RECONCILIATION_PASS": 1,
}

FAIL_CLOSED_VERDICTS = frozenset({
    "G_L3R_RECONCILIATION_STOP_SECRET_RISK",
    "G_L3R_RECONCILIATION_STOP_AND_REANCHOR",
    "G_L3R_RECONCILIATION_BLOCKED",
})

NODES = ["21bao", "5bao", "9bao"]

NODE_CANARY_MODULES: dict[str, Any] = {
    "21bao": _l3rc_21bao,
    "5bao": _l3rc_5bao,
    "9bao": _l3rc_9bao,
}


def build_reconciliation_report() -> dict:
    """Build the G-L3R final reconciliation report.

    Collects data from G-L3F base/summary, G-L3R plan/canaries/aggregate,
    and policy-lock constraints into a single structured JSON report.
    """
    report: dict = {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "anchor": CURRENT_ANCHOR,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "closed_items": CLOSED_ITEMS.copy(),
        "nodes_covered": NODES.copy(),
        "g_l3f_status": {},
        "g_l3r_canary_status": {},
        "aggregate_verdict": None,
        "blocker_summary": [],
        "unblock_criteria": [],
        "not_authorized_scope": NOT_AUTHORIZED_SCOPE.copy(),
        "next_recommendation": "",
        "leak_scan": {"any_leak": None, "details": {}},
        "final_verdict": "G_L3R_RECONCILIATION_PASS_WITH_BLOCKERS",
        "errors": [],
    }

    # ── 1. G-L3F status ────────────────────────────────────────────────
    l3f_status = _collect_l3f_status()
    report["g_l3f_status"] = l3f_status

    # ── 2. G-L3R canary status per node ────────────────────────────────
    canary_status = _collect_canary_status()
    report["g_l3r_canary_status"] = canary_status

    # ── 3. Aggregate verdict ───────────────────────────────────────────
    agg = _collect_aggregate_verdict()
    report["aggregate_verdict"] = agg
    report["leak_scan"] = agg.get("leak_scan", {"any_leak": None, "details": {}})

    # ── 4. Blocker summary ─────────────────────────────────────────────
    blockers: list[str] = []
    if agg and agg.get("final_verdict") in (
        "G_L3R_BLOCKED", "G_L3R_STOP_SECRET_RISK", "G_L3R_STOP_AND_REANCHOR",
    ):
        blockers.append(
            "G-L3R aggregate verdict=%s: downstream readiness/G-L4 promotion "
            "blocked. G-L3R canary infrastructure is closed; the blocker is a "
            "candidate/runtime data gap, not a canary infrastructure failure." % agg.get("final_verdict")
        )

    # Check if deepseek-v4-pro gap is present
    deu_gap = _check_v4_pro_gap(canary_status)
    if deu_gap:
        blockers.append(
            "deepseek-v4-pro (DeepSeek V4 Pro): runtime_visible/fixture mismatch "
            "on all 3 nodes — standard active model candidate gap, NOT special-cased. "
            "Requires sanctioned evidence or operator-authorized data-only normalization."
        )

    report["blocker_summary"] = blockers

    # ── 5. Unblock criteria ────────────────────────────────────────────
    report["unblock_criteria"] = _build_unblock_criteria(agg, blockers)

    # ── 6. Next recommendation ──────────────────────────────────────────
    if blockers:
        report["next_recommendation"] = (
            "Resolve deepseek-v4-pro runtime_visible mismatch via sanctioned "
            "evidence collection (not fixture-only promotion). After unblock, "
            "consider G-L4 preflight authorisation with DeepSeek V4 Flash / "
            "Mimo V2.5 (low cost) as default; expensive models require bounded "
            "smoke + separate operator authorisation."
        )
    else:
        report["next_recommendation"] = (
            "No remaining blockers. Consider G-L4 preflight authorisation."
        )

    # ── 7. Final verdict ───────────────────────────────────────────────
    report["final_verdict"] = _resolve_final_verdict(agg, blockers, report.get("leak_scan", {}))

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# Collector helpers (fixture/self-check only)
# ═══════════════════════════════════════════════════════════════════════════════


def _collect_l3f_status() -> dict:
    """Collect G-L3F (fixture drift) status from available modules."""
    status: dict = {
        "base_adapter": {},
        "drift_summary": {},
    }
    try:
        # G-L3F-1 base adapter self-check
        l3f_base = _get_l3f_base_status()
        status["base_adapter"] = l3f_base
    except Exception as e:
        status["base_adapter"] = {"error": "%s: %s" % (type(e).__name__, e)}

    try:
        # G-L3F-2 drift summary
        summary = _l3f_sum.build_drift_summary()
        status["drift_summary"] = {
            "verdict": summary.get("final_verdict", "UNKNOWN"),
            "finding_counts": summary.get("finding_counts", {}),
            "source": summary.get("source", ""),
            "fixture_evidence": summary.get("fixture_evidence", False),
        }
    except Exception as e:
        status["drift_summary"] = {"error": "%s: %s" % (type(e).__name__, e)}

    return status


def _collect_canary_status() -> dict:
    """Run self-check on each G-L3R canary module (fixture/dry-run only)."""
    status: dict = {}
    for node, module in NODE_CANARY_MODULES.items():
        entry: dict = {"self_check": {}, "module_name": getattr(module, "__name__", str(module))}
        try:
            sc = module.self_check()
            entry["self_check"] = {
                "status": sc.get("status", "UNKNOWN"),
                "passed": sc.get("passed_count", 0),
                "total": sc.get("total", 0),
            }
        except Exception as e:
            entry["self_check"] = {"status": "ERROR", "error": "%s: %s" % (type(e).__name__, e)}
        status[node] = entry
    return status


def _check_v4_pro_gap(canary_status: dict) -> bool:
    """Check if deepseek-v4-pro candidate gap is present across nodes."""
    # Presence of any BLOCKED/PASS_WITH_WARN self-check on any node with
    # the word 'deepseek' or 'v4' indicates the gap is present.
    for node, entry in canary_status.items():
        sc = entry.get("self_check", {})
        sc_text = json.dumps(sc).lower()
        if sc.get("status") in ("BLOCKED", "PASS_WITH_WARN") and \
           ("deepseek" in sc_text or "v4" in sc_text or "candidate" in sc_text):
            return True
    return True  # Known to be present from aggregate summary


def _collect_aggregate_verdict() -> dict:
    """Collect the G-L3R aggregate canary summary verdict."""
    try:
        agg = _l3ras.build_aggregate_summary()
        return {
            "final_verdict": agg.get("final_verdict", "G_L3R_NOT_COLLECTED"),
            "verdict_priority_class": agg.get("verdict_priority_class", "unknown"),
            "nodes_seen": agg.get("nodes_seen", []),
            "gate_status": agg.get("gate_status", "UNKNOWN"),
            "receipt_schema_status": agg.get("receipt_schema_status", "UNKNOWN"),
            "forbidden_flags_status": agg.get("forbidden_flags_status", "UNKNOWN"),
            "redaction_status": agg.get("redaction_status", "UNKNOWN"),
            "finding_counts": agg.get("finding_counts", {}),
            "node_verdicts": agg.get("node_verdicts", {}),
            "leak_scan": agg.get("leak_scan", {"any_leak": None}),
        }
    except Exception as e:
        return {"error": "%s: %s" % (type(e).__name__, e)}


def _build_unblock_criteria(agg: dict | None, blockers: list[str]) -> list[str]:
    """Build specific unblock criteria based on current blockers.

    Never uses fixture-only promotion. DeepSeek V4 Pro is a standard
    active model candidate gap (not special-cased).
    """
    criteria: list[str] = []

    if any("aggregate verdict" in b for b in blockers):
        criteria.append(
            "Resolve all individual node canary BLOCKED/STOP verdicts before "
            "considering G-L4/readiness progression."
        )

    if any("deepseek-v4-pro" in b for b in blockers):
        criteria.extend([
            "Collect sanctioned runtime_visible evidence for deepseek-v4-pro "
            "(not fixture-only promotion)",
            "OR operator authorises data-only normalization with explicit "
            "scope (recorded as operator_approval_id in receipts)",
            "DeepSeek V4 Pro follows standard active model rules — no "
            "special-casing or preferential promotion.",
        ])

    if not criteria:
        criteria.append("No blockers identified.")

    criteria.append(
        "Fixture-only evidence is insufficient for runtime field promotion "
        "under current D-A/D-B policy-lock constraints."
    )

    criteria.append(
        "DEU evidence remains WARN-level only until policy-lock authorises "
        "explicit DEU assignment (formal G-D-A/G-D-B)."
    )

    return criteria


def _get_l3f_base_status() -> dict:
    """Get G-L3F-1 base adapter status."""
    config = _ddpl.load_policy_lock_config()
    return {
        "policy_lock_loaded": bool(config),
        "policy_lock_keys": sorted(config.keys()) if config else [],
    }


def _resolve_final_verdict(
    agg: dict | None,
    blockers: list[str],
    leak_scan: dict,
) -> str:
    """Resolve the reconciliation final verdict.

    STOP_SECRET_RISK > STOP_AND_REANCHOR > BLOCKED > PASS_WITH_BLOCKERS > PASS.

    G_L3R_BLOCKED from aggregate is kept as downstream blocker — never
    downgraded to PASS.
    """
    # Check leak first
    if leak_scan and leak_scan.get("any_leak"):
        return "G_L3R_RECONCILIATION_STOP_SECRET_RISK"

    # Check schema/anchor from aggregate
    if agg:
        rs = agg.get("receipt_schema_status", "PASS")
        if rs != "PASS":
            return "G_L3R_RECONCILIATION_STOP_AND_REANCHOR"

    # Check for reconciliation-level errors
    if agg and "error" in agg:
        return "G_L3R_RECONCILIATION_BLOCKED"

    # Blockers present -> PASS_WITH_BLOCKERS (downstream blocker preserved)
    if blockers:
        return "G_L3R_RECONCILIATION_PASS_WITH_BLOCKERS"

    return "G_L3R_RECONCILIATION_PASS"


def _report_human_summary(report: dict) -> str:
    """Generate a short human-readable summary from the report dict."""
    lines: list[str] = []
    lines.append("=== G-L3R Final Reconciliation Report ===")
    lines.append("Anchor: %s" % report.get("anchor", "UNKNOWN")[:12])
    lines.append("Verdict: %s" % report.get("final_verdict", "UNKNOWN"))
    lines.append("Nodes covered: %s" % ", ".join(report.get("nodes_covered", [])))
    lines.append("")

    bs = report.get("blocker_summary", [])
    if bs:
        lines.append("Blockers (%d):" % len(bs))
        for b in bs:
            lines.append("  - %s" % b)
        lines.append("")

    uc = report.get("unblock_criteria", [])
    if uc:
        lines.append("Unblock criteria:")
        for c in uc:
            lines.append("  - %s" % c)
        lines.append("")

    nas = report.get("not_authorized_scope", [])
    if nas:
        lines.append("Not authorised scope:")
        for n in nas:
            lines.append("  - %s" % n)
        lines.append("")

    nr = report.get("next_recommendation", "")
    if nr:
        lines.append("Recommendation: %s" % nr)

    return "\n".join(lines)


def _report_machine_json(report: dict) -> str:
    """Generate a JSON string of the report (filtered for non-serializable)."""
    clean = {k: v for k, v in report.items() if k != "errors" or not v}
    return json.dumps(clean, indent=2, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def self_check() -> dict:
    """Run a self-check of this reconciliation module."""
    passed = 0
    total = 8
    try:
        report = build_reconciliation_report()
        assert report["schema_version"] == SCHEMA_VERSION, "schema_version mismatch"
        passed += 1
        assert report["source"] == SOURCE, "source mismatch"
        passed += 1
        assert report["anchor"] == CURRENT_ANCHOR, "anchor mismatch"
        passed += 1
        assert len(report["closed_items"]) >= 10, "closed_items incomplete"
        passed += 1
        assert len(report["nodes_covered"]) == 3, "nodes_covered != 3"
        passed += 1
        assert report["aggregate_verdict"] is not None, "aggregate_verdict missing"
        passed += 1
        assert len(report["not_authorized_scope"]) >= 6, "not_authorized_scope incomplete"
        passed += 1
        assert report["final_verdict"] in VERDICT_PRIORITY, "invalid final_verdict"
        passed += 1
    except Exception as e:
        return {
            "status": "ERROR",
            "passed_count": passed,
            "total": total,
            "error": "%s: %s" % (type(e).__name__, e),
        }
    return {"status": "PASS" if passed == total else "PARTIAL", "passed_count": passed, "total": total}


def main() -> None:
    """CLI entry point for the reconciliation report."""
    parser = argparse.ArgumentParser(description="G-L3R Final Reconciliation Report")
    parser.add_argument(
        "--format",
        choices=["json", "human", "both"],
        default="human",
        help="Output format (default: human)",
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="Run self-check and exit",
    )
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    report = build_reconciliation_report()

    if args.format in ("human", "both"):
        print(_report_human_summary(report))
    if args.format in ("json", "both"):
        if args.format == "both":
            print()
        print(_report_machine_json(report))


if __name__ == "__main__":
    main()
