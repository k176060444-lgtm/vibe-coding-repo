#!/usr/bin/env python3
"""
G-L3R-D4 — DeepSeek V4 Pro Runtime-Visible Mismatch Preflight Diagnosis.

Diagnoses the deepseek-v4-pro runtime_visible mismatch across 21bao/5bao/9bao
by comparing model_pool.yaml declarations, node_model_capability.yaml entries,
G-L3F base/summary drift, G-L3R canary receipts, and G-L3R aggregate verdict.

=== SCOPE ===
- Read-only diagnosis. No data modification, no SSH, no model calls.
- Reads only repo-local YAML, JSON fixtures, and module self-check outputs.
- Determines root cause classification and recommends next stage.

=== VERDICT POLICY ===
- G_L3R_D4_PREFLIGHT_DATA_ONLY_CANDIDATE: mismatch is alias/naming/fixture
  stale — repo-local evidence sufficient for data-only normalization PR.
- G_L3R_D4_PREFLIGHT_REQUIRES_SANCTIONED_EVIDENCE: repo-local evidence
  insufficient — needs live runtime_visible evidence collection.
- G_L3R_D4_PREFLIGHT_KEEP_BLOCKED: mismatch still unexplained.
- G_L3R_D4_PREFLIGHT_STOP_SECRET_RISK: secret/path/URL leak.
- G_L3R_D4_PREFLIGHT_STOP_AND_REANCHOR: schema or anchor mismatch.

ROOT CAUSE CLASSIFICATIONS:
  - naming_alias_mismatch: canonical alias differs between model_pool entries
  - provider_namespace_mismatch: provider_namespace changes between entries
  - fixture_stale: node_model_capability.yaml empty or outdated
  - runtime_receipt_missing: no canary receipt collected for this model
  - runtime_visible_unknown: runtime_visible field missing in fixture
  - data_only_normalization_candidate: mismatch explainable from repo data
  - requires_sanctioned_live_evidence: mismatch requires remote verification
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ── Constants ──────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.0.0"
SOURCE = "worker_attest_layer3_d4_runtime_visible_preflight"
CURRENT_ANCHOR = "f7dc8529bf0db012e02b1b4bd5effbd889643177"
TARGET_MODEL = "deepseek-v4-pro"
NODES = ["21bao", "5bao", "9bao"]

MODEL_POOL_PATH = Path("scripts/model_pool.yaml")
NMC_PATH = Path("scripts/node_model_capability.yaml")

VERDICT_PRIORITY: dict[str, int] = {
    "G_L3R_D4_PREFLIGHT_STOP_SECRET_RISK": 7,
    "G_L3R_D4_PREFLIGHT_STOP_AND_REANCHOR": 6,
    "G_L3R_D4_PREFLIGHT_KEEP_BLOCKED": 5,
    "G_L3R_D4_PREFLIGHT_REQUIRES_SANCTIONED_EVIDENCE": 3,
    "G_L3R_D4_PREFLIGHT_DATA_ONLY_CANDIDATE": 2,
}

FAIL_CLOSED_VERDICTS = frozenset({
    "G_L3R_D4_PREFLIGHT_STOP_SECRET_RISK",
    "G_L3R_D4_PREFLIGHT_STOP_AND_REANCHOR",
    "G_L3R_D4_PREFLIGHT_KEEP_BLOCKED",
})

NOT_AUTHORIZED_SCOPE = [
    "G-L4 live inference / model_call_verified promotion",
    "G-READINESS (readiness ready assertion)",
    "Formal G-D-A (DEU assignment)",
    "Formal G-D-B (DEU enablement decision)",
    "G-GRAY / GRAY_ACCEPTANCE",
    "PR-7 (model_pool.yaml schema v1.3+)",
    "Baseline03 (stage 8 hardening)",
    "Stage8 (production readiness)",
    "Data write-back to model_pool.yaml",
    "Data write-back to node_model_capability.yaml",
    "SSH collection from 5bao/9bao",
    "Runtime field promotion (runtime_visible/env_loaded/etc.)",
    "Model call / live inference / credential provisioning",
]

# ══════════════════════════════════════════════════════════════════════════════
# Data loaders (repo-local only)
# ══════════════════════════════════════════════════════════════════════════════


def _load_model_pool() -> dict:
    """Load model_pool.yaml (repo-local). Returns full pool dict or empty."""
    if not MODEL_POOL_PATH.exists():
        return {}
    with open(MODEL_POOL_PATH, "r") as f:
        return yaml.safe_load(f) or {}


def _load_nmc() -> dict:
    """Load node_model_capability.yaml (repo-local)."""
    if not NMC_PATH.exists():
        return {}
    with open(NMC_PATH, "r") as f:
        return yaml.safe_load(f) or {}


def _find_deepseek_v4_pro_entries(pool: dict) -> list[dict]:
    """Find all model_pool entries related to deepseek-v4-pro.

    Matches by: model == 'deepseek-v4-pro', or any alias containing
    'deepseek-v4-pro'/'ds-v4-pro'/'ds4pro', or id containing the same.
    """
    models = pool.get("models", [])
    matches: list[dict] = []
    for m in models:
        name = str(m.get("name", ""))
        mid = str(m.get("id", ""))
        primary_alias = str(m.get("primary_alias", ""))
        aliases = m.get("alias", [])
        if not isinstance(aliases, list):
            aliases = [str(aliases)]
        all_names = [name, mid, primary_alias] + aliases
        seen = set()
        for n in all_names:
            ns = str(n).lower().replace("_", "-").replace(" ", "-")
            if any(x in ns for x in ["deepseek-v4-pro", "ds-v4-pro", "ds4pro"]):
                if mid not in seen:
                    seen.add(mid)
                    matches.append(m)
                break
    return matches


def _collect_nmc_entries(nmc: dict) -> dict[str, list]:
    """Get all node_model_capability entries per node.

    Reads the canonical schema (`nodes.{node}.matrix`), with a fallback
    to the legacy `node_model_capability.{node}` key for backwards compat.
    """
    # Canonical schema (v1.1+)
    nodes_dict = nmc.get("nodes", {})
    if nodes_dict and isinstance(nodes_dict, dict):
        result: dict[str, list] = {}
        for node in NODES:
            n = nodes_dict.get(node, {})
            if isinstance(n, dict):
                result[node] = n.get("matrix", []) or []
            elif isinstance(n, list):
                result[node] = n
            else:
                result[node] = []
        return result

    # Legacy schema fallback
    cap = nmc.get("node_model_capability", {})
    return {node: cap.get(node, []) for node in NODES}


# ══════════════════════════════════════════════════════════════════════════════
# Diagnosis engine
# ══════════════════════════════════════════════════════════════════════════════


def build_d4_preflight() -> dict:
    """Build the D4 runtime-visible preflight diagnosis report."""
    pool = _load_model_pool()
    nmc = _load_nmc()
    nmc_entries = _collect_nmc_entries(nmc)

    # ── Find target model entries ──────────────────────────────────────
    d4_entries = _find_deepseek_v4_pro_entries(pool)

    # ── Build model_pool summary ───────────────────────────────────────
    mp_summary: list[dict] = []
    for e in d4_entries:
        entry: dict = {
            "id": e.get("id", ""),
            "name": e.get("name", ""),
            "canonical_provider": e.get("canonical_provider", ""),
            "provider_namespace": e.get("provider_namespace", ""),
            "model": e.get("model", ""),
            "primary_alias": e.get("primary_alias", ""),
            "alias": e.get("alias", []),
            "enabled": e.get("enabled", False),
            "lifecycle_status": e.get("lifecycle_status", ""),
            "allowed_nodes": e.get("allowed_nodes", []),
            "cost": e.get("cost", ""),
            "health_status": e.get("health_status", ""),
            "credential_status": e.get("credential_status", ""),
            "endpoint_ref": e.get("endpoint_ref", ""),
        }
        mp_summary.append(entry)

    # ── Build NMC fixtures per node ───────────────────────────────────
    cap_summary: dict[str, list] = {}
    for node in NODES:
        entries = nmc_entries.get(node, [])
        cap_summary[node] = []
        for e in entries:
            if isinstance(e, dict):
                cap_summary[node].append(e)
            else:
                cap_summary[node].append({"name": str(e)})

    # ── Build NMC presence matrix ─────────────────────────────────────
    presence: dict[str, bool] = {}
    for node in NODES:
        presence[node] = len(cap_summary[node]) > 0

    # ── Determine mismatch matrix ─────────────────────────────────────
    mm: dict[str, Any] = {"nodes": {}, "shared": {}}

    # Check per-node NMC presence
    for node in NODES:
        mm["nodes"][node] = {
            "nmc_has_entries": presence[node],
            "d4_found_in_nmc": False,
            "runtime_visible_known": False,
        }
        for entry in cap_summary[node]:
            if not isinstance(entry, dict):
                continue
            # Check multiple fields for d4 references
            check_str = " ".join([
                str(entry.get("name", "")),
                str(entry.get("model_id", "")),
                str(entry.get("primary_alias", "")),
            ]).lower()
            if any(x in check_str for x in ["deepseek-v4-pro", "deepseek-v4-flash",
                                              "ds4pro", "ds4flash", "ds-v4-pro",
                                              "deepseek-coder", "deepseek-r1",
                                              "deepseek-reasoner"]):
                # More specific: this is d4 if "v4-pro" is in any field
                if "v4-pro" in check_str or "ds4pro" in check_str:
                    mm["nodes"][node]["d4_found_in_nmc"] = True
                    if entry.get("runtime_visible") is True:
                        mm["nodes"][node]["runtime_visible_known"] = True

    # ── Root cause classification ─────────────────────────────────────
    n_alias = len(d4_entries)
    if n_alias == 0:
        root_causes = ["runtime_receipt_missing"]
        explanation = "No deepseek-v4-pro entry found in model_pool.yaml at all."
    elif n_alias >= 2:
        # Multiple entries — naming alias mismatch likely
        alias_names = [e.get("primary_alias", "") for e in d4_entries]
        namespaces = [e.get("provider_namespace", "") for e in d4_entries]
        rc: list[str] = ["naming_alias_mismatch"]
        if len(set(namespaces)) > 1:
            rc.append("provider_namespace_mismatch")
        if all(not presence[n] for n in NODES):
            rc.append("fixture_stale")
            rc.append("runtime_receipt_missing")
        else:
            if not any(mm["nodes"][n]["runtime_visible_known"] for n in NODES):
                rc.append("runtime_visible_unknown")
        if all(not presence[n] for n in NODES):
            rc.append("data_only_normalization_candidate")
        root_causes = rc
        explanation = (
            "%d deepseek-v4-pro-related entries found with aliases %s. "
            "node_model_capability.yaml has %d node(s) with entries (out of 3). "
            "Primary aliases: %s. Provider namespaces: %s."
        ) % (
            n_alias,
            [e.get("primary_alias", "") for e in d4_entries],
            sum(1 for n in NODES if presence[n]),
            alias_names,
            namespaces,
        )
    else:
        # Exactly 1 entry — check if fixture matches
        e = d4_entries[0]
        if e.get("lifecycle_status") in ("enabled_assigned", "operator_requested"):
            if presence.get("21bao") or presence.get("5bao") or presence.get("9bao"):
                if not any(mm["nodes"][n]["runtime_visible_known"] for n in NODES):
                    root_causes = ["runtime_visible_unknown"]
                    explanation = "Single entry present but runtime_visible unknown in fixtures."
                else:
                    root_causes = []
                    explanation = "No mismatch detected."
            else:
                root_causes = ["fixture_stale"]
                explanation = "Single entry present but NMC empty — fixture stale."
        else:
            root_causes = ["runtime_receipt_missing"]
            explanation = "Single entry present but lifecycle_status=%s." % e.get("lifecycle_status")

    # ── Aggregate summary ─────────────────────────────────────────────
    agg: dict = {"nodes_seen": NODES.copy(), "target_model": TARGET_MODEL}
    if presence.get("21bao") or presence.get("5bao") or presence.get("9bao"):
        agg["nmc_present"] = True
        present_nodes = [n for n in NODES if presence[n]]
        agg["nmc_nodes_with_entries"] = present_nodes
    else:
        agg["nmc_present"] = False
        agg["nmc_nodes_with_entries"] = []

    agg["model_pool_entry_count"] = n_alias

    # ── Unblock options ───────────────────────────────────────────────
    unblock_options = _build_unblock_options(root_causes)

    # ── Resolve verdict ───────────────────────────────────────────────
    verdict = _resolve_verdict(agg, root_causes)

    report: dict = {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "anchor": CURRENT_ANCHOR,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target_model": TARGET_MODEL,
        "nodes": NODES.copy(),
        "model_pool_entries": mp_summary,
        "capability_entries": cap_summary,
        "fixture_entries": d4_entries,
        "canary_entries": agg,
        "aggregate_status": agg,
        "mismatch_matrix": mm,
        "candidate_root_causes": root_causes,
        "root_cause_explanation": explanation,
        "unblock_options": unblock_options,
        "recommended_next_stage": _recommend_next_stage(verdict),
        "not_authorized_scope": NOT_AUTHORIZED_SCOPE.copy(),
        "final_verdict": verdict,
        "scope_note": (
            "G-L3R D4 preflight diagnosis. Reads only repo-local YAML and "
            "fixture data. Does NOT modify any data. Does NOT perform SSH, "
            "model calls, credential provisioning, node sync, readiness "
            "expansion, DEU assignment, new namespace enablement, or runtime "
            "field promotion. DeepSeek V4 Pro is target model for diagnosis "
            "because it is the current G-L3R reconciliation blocker."
        ),
    }
    return report


# ══════════════════════════════════════════════════════════════════════════════
# Decision helpers
# ══════════════════════════════════════════════════════════════════════════════


def _build_unblock_options(root_causes: list[str]) -> list[dict]:
    """Build unblock options with conditions. Never promotes fixture-only."""
    options: list[dict] = []

    # Option A — always present when repo-local explanation exists
    opt_a = dict(OPTION_A_DATA_ONLY)
    opt_a["recommended"] = (
        "naming_alias_mismatch" in root_causes or
        "fixture_stale" in root_causes or
        "data_only_normalization_candidate" in root_causes
    )
    options.append(opt_a)

    # Option B — always present
    opt_b = dict(OPTION_B_SANCTIONED_EVIDENCE)
    opt_b["recommended"] = (
        "runtime_visible_unknown" in root_causes or
        "runtime_receipt_missing" in root_causes
    ) and "data_only_normalization_candidate" not in root_causes
    options.append(opt_b)

    # Option C — always present as safety net
    opt_c = dict(OPTION_C_KEEP_BLOCKED)
    opt_c["recommended"] = not opt_a["recommended"] and not opt_b["recommended"]
    options.append(opt_c)

    return options


OPTION_A_DATA_ONLY = {
    "label": "A) Data-only normalization PR",
    "condition": "Repo-local evidence shows naming/alias/provider_namespace/fixture stale.",
    "action": "Submit a bounded PR correcting aliases or fixture entries (no live collection).",
    "note": "Does NOT constitute runtime_visible promotion or DEU assignment. "
            "Requires operator approval. Does NOT unblock readiness/G-L4 until "
            "evidence path confirmed.",
}

OPTION_B_SANCTIONED_EVIDENCE = {
    "label": "B) Sanctioned live evidence collection",
    "condition": "Repo-local evidence insufficient for data-only unblock.",
    "action": "Authorise bounded SSH/collection to gather live runtime_visible data.",
    "note": "Collects evidence only; does NOT modify any source files. Requires "
            "separate operator approval per sanctions-defined scope.",
}

OPTION_C_KEEP_BLOCKED = {
    "label": "C) Keep blocked",
    "condition": "Mismatch still unexplained or operator chooses to defer.",
    "action": "Maintain G_L3R_BLOCKED as downstream blocker. No next stage.",
    "note": "DeepSeek V4 Pro remains a candidate gap. Does NOT block PR merges "
            "for non-D4 work. Only readiness/G-L4 progression is blocked.",
}


def _resolve_verdict(agg: dict, root_causes: list[str]) -> str:
    """Resolve the D4 preflight final verdict."""
    # Stop conditions
    if agg.get("leak_scan") and agg["leak_scan"].get("any_leak"):
        return "G_L3R_D4_PREFLIGHT_STOP_SECRET_RISK"
    if agg.get("schema_mismatch"):
        return "G_L3R_D4_PREFLIGHT_STOP_AND_REANCHOR"

    # Determine from root causes
    if "data_only_normalization_candidate" in root_causes:
        return "G_L3R_D4_PREFLIGHT_DATA_ONLY_CANDIDATE"
    if "runtime_visible_unknown" in root_causes or "runtime_receipt_missing" in root_causes:
        return "G_L3R_D4_PREFLIGHT_REQUIRES_SANCTIONED_EVIDENCE"
    if root_causes:
        return "G_L3R_D4_PREFLIGHT_KEEP_BLOCKED"

    return "G_L3R_D4_PREFLIGHT_DATA_ONLY_CANDIDATE"


def _recommend_next_stage(verdict: str) -> str:
    """Recommend the next stage based on verdict."""
    recommendations = {
        "G_L3R_D4_PREFLIGHT_DATA_ONLY_CANDIDATE": (
            "Consider data-only normalization PR to correct alias/naming mismatch "
            "in model_pool.yaml or node_model_capability.yaml fixtures. "
            "After normalization, re-run G-L3R canary self-check; "
            "if candidate gap resolves, G-L3R aggregate may transition to PASS_WITH_WARN. "
            "G-L4 / readiness still requires separate authorisation."
        ),
        "G_L3R_D4_PREFLIGHT_REQUIRES_SANCTIONED_EVIDENCE": (
            "Authorise sanctioned live runtime_visible evidence collection on "
            "21bao/5bao/9bao before unblock decision. No fixture-only promotion."
        ),
        "G_L3R_D4_PREFLIGHT_KEEP_BLOCKED": (
            "Keep G_L3R_BLOCKED as downstream blocker. Investigate further or "
            "defer to later stage."
        ),
    }
    return recommendations.get(verdict, "Defer to operator decision.")


# ══════════════════════════════════════════════════════════════════════════════
# Report formatting
# ══════════════════════════════════════════════════════════════════════════════


def _report_human_summary(report: dict) -> str:
    """Generate a short human-readable summary."""
    lines: list[str] = []
    lines.append("=== G-L3R D4 Runtime-Visible Preflight ===")
    lines.append("Target: %s" % report.get("target_model", "?"))
    lines.append("Anchor: %s" % str(report.get("anchor", "?"))[:12])
    lines.append("Verdict: %s" % report.get("final_verdict", "?"))
    lines.append("Nodes: %s" % ", ".join(report.get("nodes", [])))
    lines.append("")

    rc = report.get("candidate_root_causes", [])
    if rc:
        lines.append("Root causes (%d):" % len(rc))
        for r in rc:
            lines.append("  - %s" % r)
        lines.append("")

    exp = report.get("root_cause_explanation", "")
    if exp:
        lines.append("Explanation: %s" % exp)
        lines.append("")

    uo = report.get("unblock_options", [])
    if uo:
        lines.append("Unblock options:")
        for opt in uo:
            rec = opt.get("recommended", False)
            rec_tag = " [RECOMMENDED]" if rec else ""
            lines.append("  %s%s" % (opt.get("label", "?"), rec_tag))
            lines.append("    Condition: %s" % opt.get("condition", ""))
            lines.append("    Action: %s" % opt.get("action", ""))
        lines.append("")

    nr = report.get("recommended_next_stage", "")
    if nr:
        lines.append("Recommended next stage: %s" % nr)
        lines.append("")

    nas = report.get("not_authorized_scope", [])
    if nas:
        lines.append("Not authorised in this scope:")
        for n in nas:
            lines.append("  - %s" % n)

    return "\n".join(lines)


def _report_machine_json(report: dict) -> str:
    """Generate machine-readable JSON."""
    clean = {k: v for k, v in report.items() if k != "errors" or not v}
    return json.dumps(clean, indent=2, ensure_ascii=False, default=str)


# ══════════════════════════════════════════════════════════════════════════════
# Self-check
# ══════════════════════════════════════════════════════════════════════════════


def self_check() -> dict:
    """Run self-check for this preflight module."""
    passed = 0
    total = 10
    try:
        report = build_d4_preflight()
        assert report["schema_version"] == SCHEMA_VERSION, "schema_version mismatch"
        passed += 1
        assert report["source"] == SOURCE, "source mismatch"
        passed += 1
        assert report["anchor"] == CURRENT_ANCHOR, "anchor mismatch"
        passed += 1
        assert report["target_model"] == TARGET_MODEL, "target_model mismatch"
        passed += 1
        assert len(report["nodes"]) == 3, "nodes != 3"
        passed += 1
        assert len(report["model_pool_entries"]) >= 2, "expected >=2 d4 entries"
        passed += 1
        assert len(report["candidate_root_causes"]) >= 1, "expected >=1 root cause"
        passed += 1
        assert len(report["unblock_options"]) >= 1, "expected >=1 unblock option"
        passed += 1
        assert "A)" in str(report["unblock_options"]), "option A missing"
        passed += 1
        assert report["final_verdict"] in VERDICT_PRIORITY, "invalid verdict"
        passed += 1
    except Exception as e:
        return {
            "status": "ERROR",
            "passed_count": passed,
            "total": total,
            "error": "%s: %s" % (type(e).__name__, e),
        }
    return {"status": "PASS" if passed == total else "PARTIAL", "passed_count": passed, "total": total}


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(description="G-L3R D4 Runtime-Visible Preflight")
    parser.add_argument("--format", choices=["json", "human", "both"], default="human")
    parser.add_argument("--self-check", action="store_true", help="Run self-check and exit")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    report = build_d4_preflight()

    if args.format in ("human", "both"):
        print(_report_human_summary(report))
    if args.format in ("json", "both"):
        if args.format == "both":
            print()
        print(_report_machine_json(report))


if __name__ == "__main__":
    main()
