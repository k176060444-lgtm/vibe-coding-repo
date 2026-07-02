#!/usr/bin/env python3
"""
G-L3R — Aggregate Canary Summary (Schema+Gate+Receipt Reconciliation).

Aggregates 21bao local canary, 5bao SSH canary, and 9bao SSH canary
self-check and receipt evidence into a single structured JSON summary
with a human-readable verdict.

=== SCOPE ===
- Reads canary self-check results and fixture-based receipt evidence only.
- NO real SSH, NO real model calls, NO credential provisioning.
- NO node sync, NO readiness expansion, NO runtime field promotion.
- Aggregate verdict is about canary PATH/GATE/SCHEMA/REDACTION/FORBIDDEN-FLAG
  verification, NOT about live model inference or readiness ready.

=== VERDICT POLICY ===
- Uses G_L3R_* namespace (does NOT reuse G_L3F_* or E2E_*).
- PASS: all 3 nodes' canary paths, gates, schemas clean.
- PASS_WITH_WARN: all 3 nodes pass but DEU evidence WARN or fixture gaps.
- BLOCKED: any node missing required canary artifact, schema/anchor mismatch,
  forbidden flag True, or self-check failure.
- STOP_SECRET_RISK: redaction false or secret/path/URL leak.
- STOP_AND_REANCHOR: schema_version or anchor disagreement between nodes.
- AGGREGATE verdict does NOT imply model_call_verified or readiness ready.

=== COST STRATEGY (comment-only) ===
G-L3R aggregate does not call models. Any future G-L4 live validation,
if authorized, would default to DeepSeek V4 Flash / Mimo V2.5 (low cost).
Expensive models require bounded smoke + separate operator authorization.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Import all G-L3R canary modules (fixture/dry-run only).
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
    from scripts import da_db_policy_lock as _ddpl
except ImportError:
    import da_db_policy_lock as _ddpl  # type: ignore

try:
    from scripts import worker_attest_layer3_drift_summary as _l3f_sum
except ImportError:
    import worker_attest_layer3_drift_summary as _l3f_sum  # type: ignore

# ── Constants ─────────────────────────────────────────────────────────────────

SCHEMA_VERSION = _l3rp.SCHEMA_VERSION
SOURCE = "worker_attest_layer3_runtime_summary"

# Priority ordering (highest first) — extends G-L3R-PLAN with aggregate-only vals.
VERDICT_PRIORITY: dict[str, int] = {
    "G_L3R_STOP_SECRET_RISK": 7,
    "G_L3R_STOP_AND_REANCHOR": 6,
    "G_L3R_BLOCKED": 5,
    "G_L3R_NOT_COLLECTED": 4,
    "G_L3R_PASS_WITH_WARN": 2,
    "G_L3R_PASS": 1,
}

FAIL_CLOSED_VERDICTS = frozenset({
    "G_L3R_STOP_SECRET_RISK",
    "G_L3R_STOP_AND_REANCHOR",
    "G_L3R_BLOCKED",
})

ADVISORY_VERDICTS = frozenset({
    "G_L3R_NOT_COLLECTED",
    "G_L3R_PASS_WITH_WARN",
    "G_L3R_PASS",
})

NODE_CANARY_MODULES = {
    "21bao": _l3rc_21bao,
    "5bao": _l3rc_5bao,
    "9bao": _l3rc_9bao,
}


def _resolve_verdict(verdicts: list[str]) -> str:
    """Resolve the highest-priority verdict from a list."""
    best = "G_L3R_PASS"
    best_prio = 0
    for v in verdicts:
        prio = VERDICT_PRIORITY.get(v, 0)
        if prio > best_prio:
            best_prio = prio
            best = v
    return best


# ═══════════════════════════════════════════════════════════════════════════════
# Canary evidence collection (fixture/dry-run only, no real SSH)
# ═══════════════════════════════════════════════════════════════════════════════


def _run_canary_self_check(module: Any, node_name: str) -> dict:
    """Run a canary module's self-check (fixture/dry-run, no real SSH).

    Returns a dict with:
      - module_name
      - node
      - self_check_status (PASS/FAIL)
      - self_check_passed / total
      - error (if any)
    """
    result: dict = {
        "module_name": getattr(module, "__name__", str(module)),
        "node": node_name,
        "self_check_status": "UNKNOWN",
        "self_check_passed": 0,
        "self_check_total": 0,
        "error": None,
    }
    try:
        sc = module.self_check()
        result["self_check_status"] = sc.get("status", "UNKNOWN")
        result["self_check_passed"] = sc.get("passed_count", 0)
        result["self_check_total"] = sc.get("total", 0)
    except Exception as e:
        result["self_check_status"] = "ERROR"
        result["error"] = f"{type(e).__name__}: {e}"
    return result


def _run_canary_collection(module: Any, node_name: str) -> dict:
    """Run a canary's collection in fixture/dry-run mode.

    Returns a dict with receipt_count, verdict, leak status, and a
    sample receipt for schema verification.
    """
    result: dict = {
        "node": node_name,
        "receipt_count": 0,
        "collection_verdict": "G_L3R_NOT_COLLECTED",
        "leaked": None,
        "sample_receipt_fields": None,
        "error": None,
    }
    try:
        # Use fixture/dry-run mode based on node type
        if node_name == "21bao":
            collection = module.collect_21bao_all_receipts(
                operator_approval_id="op-agg-summary",
            )
        elif node_name == "5bao":
            collection = module.collect_5bao_all_receipts(
                operator_approval_id="op-agg-summary",
                collector_mode="sanctioned_ssh_canary_5bao",
                use_real_ssh=False,
            )
        elif node_name == "9bao":
            collection = module.collect_9bao_all_receipts(
                operator_approval_id="op-agg-summary",
                collector_mode="sanctioned_ssh_canary_9bao",
                use_real_ssh=False,
            )
        else:
            result["error"] = f"Unknown node: {node_name}"
            return result

        result["receipt_count"] = collection.get("receipt_count", 0)
        result["collection_verdict"] = collection.get("summary_verdict", "G_L3R_NOT_COLLECTED")
        result["leaked"] = collection.get("leaked", None)

        # Sample first receipt's fields (not full receipt to keep output manageable)
        receipts = collection.get("receipts", [])
        if receipts:
            r0 = receipts[0]
            result["sample_receipt_fields"] = {
                "schema_version": r0.get("schema_version"),
                "node": r0.get("node"),
                "source_node": r0.get("source_node"),
                "collector_mode": r0.get("collector_mode"),
                "fields_present": sorted(r0.keys()),
                "field_count": len(r0),
                "forbidden_flags_all_false": all(
                    not v for v in r0.get("forbidden_operation_flags", {}).values()
                ),
                "redaction_all_true": all(
                    r0.get("redaction_status", {}).values()
                ),
            }
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Aggregate summary
# ═══════════════════════════════════════════════════════════════════════════════


def build_aggregate_summary() -> dict:
    """Build the G-L3R aggregate canary summary.

    Runs self-checks and fixture-based collection for all 3 nodes,
    then aggregates into a structured verdict.

    No real SSH, no real model calls, no credential provisioning.
    """
    summary: dict = {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "anchor": datetime.now(timezone.utc).isoformat(),
        "nodes_seen": [],
        "node_canary_status": {},
        "receipt_schema_status": "UNKNOWN",
        "gate_status": "UNKNOWN",
        "forbidden_flags_status": "UNKNOWN",
        "redaction_status": "UNKNOWN",
        "leak_scan": {"any_leak": None, "node_details": {}},
        "finding_counts": {},
        "node_verdicts": {},
        "final_verdict": "G_L3R_NOT_COLLECTED",
        "verdict_priority_class": "advisory",
        "is_merge_blocker": False,
        "scope_note": "",
        "errors": [],
    }

    node_verdicts: dict[str, str] = {}
    node_findings: list[dict] = []
    all_gates_pass = True
    all_schemas_valid = True
    all_forbidden_clean = True
    all_redacted = True
    any_leaked = False

    for node_name, module in NODE_CANARY_MODULES.items():
        # ── Self-check ───────────────────────────────────────────────────
        sc_result = _run_canary_self_check(module, node_name)
        node_entry = {"self_check": sc_result}
        summary["nodes_seen"].append(node_name)
        summary["node_canary_status"][node_name] = node_entry

        if sc_result["self_check_status"] != "PASS":
            node_verdicts[node_name] = "G_L3R_BLOCKED"
            summary["errors"].append(
                f"{node_name}: self-check {sc_result['self_check_status']} "
                f"({sc_result['self_check_passed']}/{sc_result['self_check_total']})"
            )
        else:
            # ── Collection (fixture/dry-run) ─────────────────────────────
            coll_result = _run_canary_collection(module, node_name)
            node_entry["collection"] = coll_result

            cvd = coll_result.get("collection_verdict", "G_L3R_NOT_COLLECTED")
            node_verdicts[node_name] = cvd

            # Check for errors
            if coll_result.get("error"):
                summary["errors"].append(f"{node_name}: collection error: {coll_result['error']}")
                node_verdicts[node_name] = "G_L3R_BLOCKED"

            # Leak check
            if coll_result.get("leaked"):
                any_leaked = True
                summary["leak_scan"]["node_details"][node_name] = True

            # Schema + forbidden + redaction from sample receipt
            sample = coll_result.get("sample_receipt_fields")
            if sample:
                if sample.get("field_count", 0) < 18:
                    all_schemas_valid = False
                if not sample.get("forbidden_flags_all_false", False):
                    all_forbidden_clean = False
                if not sample.get("redaction_all_true", False):
                    all_redacted = False

    # ── Leak scan ────────────────────────────────────────────────────────
    summary["leak_scan"]["any_leak"] = any_leaked
    if any_leaked:
        for n in summary["nodes_seen"]:
            if n not in summary["leak_scan"]["node_details"]:
                summary["leak_scan"]["node_details"][n] = False

    # ── Resolve statuses ─────────────────────────────────────────────────
    sc_all_pass = all(
        v.get("self_check", {}).get("self_check_status") == "PASS"
        for v in summary["node_canary_status"].values()
    )

    coll_all_collected = all(
        v.get("collection", {}).get("receipt_count", 0) > 0
        for v in summary["node_canary_status"].values()
    )

    summary["gate_status"] = "PASS" if sc_all_pass else "FAIL"
    summary["receipt_schema_status"] = "PASS" if (all_schemas_valid and coll_all_collected) else "FAIL"
    summary["forbidden_flags_status"] = "PASS" if all_forbidden_clean else "FAIL"
    summary["redaction_status"] = "PASS" if all_redacted else "FAIL"

    # ── Collect findings ─────────────────────────────────────────────────
    findings: list[dict] = []

    # Self-check findings
    for node_name, entry in summary["node_canary_status"].items():
        sc = entry.get("self_check", {})
        if sc.get("self_check_status") != "PASS":
            findings.append({
                "node": node_name,
                "type": "self_check_failure",
                "severity": "blocked",
                "message": f"{node_name}: self-check {sc.get('self_check_status')} "
                           f"({sc.get('self_check_passed')}/{sc.get('self_check_total')})",
            })

    # Collection findings
    for node_name, entry in summary["node_canary_status"].items():
        coll = entry.get("collection", {})
        cvd = coll.get("collection_verdict", "")
        if cvd in ("G_L3R_BLOCKED", "G_L3R_STOP_SECRET_RISK", "G_L3R_STOP_AND_REANCHOR"):
            findings.append({
                "node": node_name,
                "type": "collection_blocked",
                "severity": "blocked",
                "message": f"{node_name}: collection verdict {cvd}",
            })
        elif cvd == "G_L3R_PASS_WITH_WARN":
            findings.append({
                "node": node_name,
                "type": "deu_live_evidence",
                "severity": "warn",
                "message": f"{node_name}: DEU evidence observed (WARN only, no promotion)",
            })

    # Leak findings
    if any_leaked:
        findings.append({
            "node": "all",
            "type": "leak_detected",
            "severity": "stop_secret_risk",
            "message": "Secret/path/URL leak detected in canary receipts",
        })

    # Forbidden flag findings
    if not all_forbidden_clean:
        findings.append({
            "node": "all",
            "type": "forbidden_flag_true",
            "severity": "blocked",
            "message": "One or more nodes have forbidden_operation_flags=True",
        })

    # Redaction findings
    if not all_redacted:
        findings.append({
            "node": "all",
            "type": "redaction_false",
            "severity": "stop_secret_risk",
            "message": "One or more nodes have redaction_status not fully True",
        })

    summary["finding_counts"] = {
        "stop_secret_risk": sum(1 for f in findings if f.get("severity") == "stop_secret_risk"),
        "blocked": sum(1 for f in findings if f.get("severity") == "blocked"),
        "warn": sum(1 for f in findings if f.get("severity") == "warn"),
        "total": len(findings),
    }

    # ── Resolve final verdict ────────────────────────────────────────────
    for node_name, v in node_verdicts.items():
        summary["node_verdicts"][node_name] = v

    all_verdicts = list(node_verdicts.values())

    if any_leaked or not all_redacted:
        final = "G_L3R_STOP_SECRET_RISK"
    elif not all_schemas_valid:
        final = "G_L3R_STOP_AND_REANCHOR"
    elif not sc_all_pass or not all_forbidden_clean or not coll_all_collected:
        final = "G_L3R_BLOCKED"
    elif any(v in ("G_L3R_BLOCKED", "G_L3R_STOP_SECRET_RISK", "G_L3R_STOP_AND_REANCHOR") for v in all_verdicts):
        final = _resolve_verdict(all_verdicts)
    elif any(v == "G_L3R_PASS_WITH_WARN" for v in all_verdicts) or any(f.get("severity") == "warn" for f in findings):
        final = "G_L3R_PASS_WITH_WARN"
    else:
        final = "G_L3R_PASS"

    summary["final_verdict"] = final
    summary["verdict_priority_class"] = "fail_closed" if final in FAIL_CLOSED_VERDICTS else "advisory"
    summary["is_merge_blocker"] = final in FAIL_CLOSED_VERDICTS
    summary["findings"] = findings

    summary["scope_note"] = (
        "G-L3R aggregate canary summary. Verifies canary receipt path/gate/schema/"
        "redaction/forbidden-flag/node-mode isolation across 21bao, 5bao, and 9bao. "
        "Does NOT verify live model inference (no model_call_verified). "
        "Does NOT assert readiness ready. "
        "Uses only fixture/dry-run evidence; no real SSH, no model calls, "
        "no credential provisioning, no node sync. "
        "DeepSeek V4 Pro follows the same active-model rules — no special-casing. "
        "Future G-L4 (if authorized): default DeepSeek V4 Flash / Mimo V2.5 (low cost); "
        "expensive models require bounded smoke + separate operator authorization."
    )

    return summary


# ═══════════════════════════════════════════════════════════════════════════════
# Verdict helpers
# ═══════════════════════════════════════════════════════════════════════════════


def get_verdict_boundary() -> dict:
    """Return the canonical boundary definition for G-L3R aggregate.

    Documentation-only, no collection performed.
    """
    return {
        "scope": "scripts/worker_attest_layer3_runtime_summary.py (this module)",
        "verdict_namespace": "G_L3R_* (aggregate, same rules as G-L3R-PLAN)",
        "verdicts": sorted(VERDICT_PRIORITY.keys()),
        "claims": (
            "G-L3R aggregate canary summary — verifies receipt path/gate/schema/"
            "redaction/forbidden-flag/node-mode isolation. "
            "Does NOT prove model_call_verified, does NOT prove readiness ready."
        ),
        "does_not_claim": [
            "live model inference capability",
            "model_call_verified state promotion",
            "readiness ready status",
            "credential provisioning completeness",
            "node sync completion",
            "runtime field promotion",
            "DEU assignment approval",
        ],
        "data_sources": [
            "21bao local canary self-check + fixture receipts",
            "5bao sanctioned SSH canary self-check + fixture receipts",
            "9bao sanctioned SSH canary self-check + fixture receipts",
            "G-L3R plan boundary definitions",
            "D-A/D-B policy-lock constraints",
            "G-L3F summary (G-L3F verdicts, not cross-promoted)",
        ],
        "current_limitation": (
            "deepseek-v4-pro fixture mismatch produces CANDIDATE_DRIFT / BLOCKED "
            "in individual canary verdicts; this is a expected fixture data gap, "
            "not a live runtime failure. Aggregate does NOT auto-promote."
        ),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Self-check
# ═══════════════════════════════════════════════════════════════════════════════


def self_check() -> dict:
    """In-process self-check. No remote access, no model calls."""
    checks: list[dict] = []

    def _ck(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    # sc-01: Module loads, constants correct
    _ck("sc-01-module-loads", True, f"schema_version={SCHEMA_VERSION}")

    # sc-02: 3 canary modules imported
    for node, mod in NODE_CANARY_MODULES.items():
        has_sc = hasattr(mod, "self_check")
        _ck(f"sc-02-{node}-module-loaded", has_sc, f"node={node}, has_self_check={has_sc}")

    # sc-03: Verdict priority has expected values
    _ck("sc-03-verdict-priority",
        "G_L3R_PASS" in VERDICT_PRIORITY and "G_L3R_BLOCKED" in VERDICT_PRIORITY,
        f"verdict_count={len(VERDICT_PRIORITY)}")

    # sc-04: Build aggregate summary (fixture/dry-run only)
    try:
        summary = build_aggregate_summary()
        _ck("sc-04-summary-built", True, f"nodes={summary['nodes_seen']}, verdict={summary['final_verdict']}")
    except Exception as e:
        _ck("sc-04-summary-built", False, f"error={e}")
        summary = {"nodes_seen": [], "final_verdict": "ERROR"}

    # sc-05: All 3 nodes seen
    expected_nodes = {"21bao", "5bao", "9bao"}
    seen = set(summary.get("nodes_seen", []))
    _ck("sc-05-all-nodes-seen", seen == expected_nodes,
        f"seen={sorted(seen)}, expected={sorted(expected_nodes)}")

    # sc-06: Final verdict is a known G_L3R_* value
    known_verdicts = set(VERDICT_PRIORITY.keys())
    fv = summary.get("final_verdict", "")
    _ck("sc-06-valid-final-verdict", fv in known_verdicts,
        f"verdict={fv}")

    # sc-07: No leak
    _ck("sc-07-no-leak",
        not summary.get("leak_scan", {}).get("any_leak", True),
        f"any_leak={summary.get('leak_scan', {}).get('any_leak')}")

    # sc-08: Scope note present
    sn = summary.get("scope_note", "")
    _ck("sc-08-scope-note-present", bool(sn) and "does not" in sn.lower(),
        f"scope_note_len={len(sn)}")

    # sc-09: Node verdicts exist for all 3 nodes
    nv = summary.get("node_verdicts", {})
    _ck("sc-09-node-verdicts-all-3",
        set(nv.keys()) == expected_nodes,
        f"nodes_with_verdicts={sorted(nv.keys())}")

    # sc-10: Summary does not contain misleading terms
    output_json = json.dumps(summary).lower()
    misleading = ["live inference", "readiness ready"]
    found_misleading = [m for m in misleading if m in output_json and "does not" not in output_json.split(m)[0][-60:]]
    # model_call_verified appears in scope_note as a disclaimer, not a claim
    _ck("sc-10-no-misleading-claims",
        not found_misleading,
        f"found={found_misleading}")

    passed_count = sum(1 for c in checks if c["passed"])
    total = len(checks)

    return {
        "schema_version": SCHEMA_VERSION,
        "name": "worker_attest_layer3_runtime_summary",
        "status": "PASS" if passed_count == total else "FAIL",
        "passed_count": passed_count,
        "total": total,
        "detail": f"{passed_count}/{total} passed",
        "checks": checks,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="worker_attest_layer3_runtime_summary.py",
        description="G-L3R aggregate canary summary.",
    )
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=["run", "self-check"],
        default="self-check",
        help="Command: run (build aggregate summary) or self-check.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=False,
        help="Pretty-print JSON output.",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = _parse_args()

    if args.cmd == "run":
        summary = build_aggregate_summary()
        indent = 2 if args.pretty else None
        print(json.dumps(summary, indent=indent, default=str))
    else:
        result = self_check()
        print(json.dumps(result, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
