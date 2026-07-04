#!/usr/bin/env python3
"""
G-L3R D4 Receipt-to-NMC Normalization: update NMC runtime_visible field
for all 3 nodes based on canonical evidence.

Usage:
    python scripts/normalize_g_l3r_d4_runtime_visible.py
    python scripts/normalize_g_l3r_d4_runtime_visible.py --self-check

This is a bounded data-only normalization. It:
- Reads scripts/node_model_capability.yaml (NMC)
- Sets runtime_visible=true for the D4 entry (opencode-go-deepseek-v4-pro)
  on all 3 nodes (21bao/5bao/9bao) backed by canonical evidence:
    * 5bao/9bao: PR #332 clean-main sanctioned live evidence (clean-main)
    * 21bao:     PR #336 local runtime-visible evidence (local config)
- Adds a `runtime_visible_evidence` block to each promoted entry,
  pointing back to its source PR, approval_id, and evidence anchor.
- NEVER modifies:
    * scripts/model_pool.yaml (provider identity, lifecycle, enablement)
    * model_call_verified / operator_approved / env_loaded (must stay non-promoted)
    * any other NMC entries

It is a regeneration script: re-running it produces an idempotent result.
The YAML file is rewritten to preserve structure (deterministic, sorted).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).parent.parent
NMC_PATH = REPO / "scripts/node_model_capability.yaml"
POOL_PATH = REPO / "scripts/model_pool.yaml"

# ── Constants ──────────────────────────────────────────────────────────────────

TARGET_MODEL_ID = "opencode-go-deepseek-v4-pro"
NODES = ["21bao", "5bao", "9bao"]

# Evidence blocks per node. 5bao/9bao share PR #332 evidence; 21bao uses PR #336
# local config evidence. These dicts must remain enumerable and redactable.
EVIDENCE_5BAO_9BAO = {
    "source": "PR #332 clean-main sanctioned live evidence",
    "approval_id": "OPERATOR-20260703-G-L3R-D4-LIVE-EVIDENCE-003",
    "evidence_anchor": "09b1d97f0cab774e3eb023c9768a40d8165a1d46",
    "closure_anchor": "cde599d6fb1584942499ddf4ffe12a6f901a72d2",
    "collector": "5bao_ssh_opencode_config / 9bao_ssh_opencode_config",
}

EVIDENCE_21BAO = {
    "source": "PR #336 21bao local runtime-visible evidence",
    "approval_id": "OPERATOR-20260704-G-L3R-D4-21BAO-LOCAL-RT-EVIDENCE-005",
    "evidence_anchor": "2ec1778e357fd3a840b35d45d061f171388bf740",
    "merge_commit": "0a932be4fd6d12760e8c5e6400044644864e003c",
    "collector": "worker_attest_layer3_d4_21bao_local_runtime_visible",
    "matched_key": "deepseek-plan.deepseek-v4-pro",
    "runtime_visible_source": "21bao_local_opencode_config",
    "note": (
        "21bao local concrete opencode.jsonc has `deepseek-plan` provider "
        "block with `deepseek-v4-pro` model entry. Distinct from central "
        "opencode-go namespace. See PR #336 for full evidence."
    ),
}


def normalize() -> dict[str, Any]:
    """Normalize NMC D4 entries based on canonical evidence per node.

    Returns a report dict with: modified_nodes, unchanged_nodes, skipped, errors.
    """
    if not NMC_PATH.exists():
        print(f"ERROR: NMC file not found: {NMC_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(NMC_PATH, "r", encoding="utf-8") as f:
        nmc = yaml.safe_load(f) or {}

    if not isinstance(nmc.get("nodes"), dict):
        print("ERROR: NMC missing top-level 'nodes' mapping", file=sys.stderr)
        sys.exit(2)

    modified_nodes: list[str] = []
    unchanged_nodes: list[str] = []
    skipped_nodes: list[str] = []
    errors: list[str] = []

    for node in NODES:
        node_block = nmc.get("nodes", {}).get(node)
        if not isinstance(node_block, dict):
            errors.append(f"{node}: missing or non-dict node block")
            continue

        matrix = node_block.get("matrix", [])
        if not isinstance(matrix, list):
            errors.append(f"{node}: matrix is not a list")
            continue

        target_found = False
        for entry in matrix:
            if not isinstance(entry, dict):
                continue
            if entry.get("model_id") != TARGET_MODEL_ID:
                continue

            target_found = True
            old_rv = entry.get("runtime_visible")
            old_model_call = entry.get("model_call_verified")
            old_op_approved = entry.get("operator_approved")
            old_env_loaded = entry.get("env_loaded")

            # Set runtime_visible=True and add evidence per node
            if node == "21bao":
                entry["runtime_visible"] = True
                entry["runtime_visible_evidence"] = dict(EVIDENCE_21BAO)
                # Drop the legacy R8 residual note (replaced by evidence)
                entry.pop("notes", None)
                modified_nodes.append(node)
                print(
                    f"  {node}: runtime_visible {old_rv!r} -> True "
                    f"(PR #336 local evidence, matched_key="
                    f"{EVIDENCE_21BAO['matched_key']})"
                )
            elif node in ("5bao", "9bao"):
                entry["runtime_visible"] = True
                entry["runtime_visible_evidence"] = dict(EVIDENCE_5BAO_9BAO)
                modified_nodes.append(node)
                print(
                    f"  {node}: runtime_visible {old_rv!r} -> True "
                    f"(PR #332 clean-main evidence)"
                )
            else:
                skipped_nodes.append(node)

            # ── Forbidden-promotion assertions ───────────────────────────
            # These MUST always hold. The script asserts them on every run
            # so a future change cannot accidentally promote these fields.
            if entry.get("model_call_verified") is True:
                errors.append(
                    f"{node}: model_call_verified promoted (must stay non-True)"
                )
            if entry.get("operator_approved") is True:
                errors.append(
                    f"{node}: operator_approved promoted (must stay non-True)"
                )
            # env_loaded: 21bao was "unknown", may now also stay non-promoted
            # (we only changed runtime_visible). If env_loaded was True before,
            # we preserve it; we never introduce a promotion.
            if entry.get("env_loaded") is True and old_env_loaded is not True:
                errors.append(
                    f"{node}: env_loaded newly promoted (must stay)"
                )
            break  # one D4 entry per node

        if not target_found:
            skipped_nodes.append(node)
            print(
                f"  {node}: WARNING — D4 ({TARGET_MODEL_ID}) not found in NMC"
            )

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(3)

    # ── Update header notes ─────────────────────────────────────────────
    nodes_str = ", ".join(modified_nodes) if modified_nodes else "none"
    skipped_str = ", ".join(skipped_nodes) if skipped_nodes else ""
    skipped_clause = f" {skipped_str} skipped." if skipped_str else ""

    nmc["notes"] = (
        f"G-L3R D4 normalization applied: {nodes_str} "
        f"runtime_visible=true per evidence refs (PR #332 for 5bao/9bao, "
        f"PR #336 for 21bao). evidence_anchor for 21bao=2ec1778e, "
        f"merge_commit=0a932be.{skipped_clause}"
    )

    # ── Write back deterministically ────────────────────────────────────
    with open(NMC_PATH, "w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(
            nmc, f, default_flow_style=False, allow_unicode=True,
            sort_keys=False,
        )

    print("\nNormalization complete.")
    print(f"  Modified: {', '.join(modified_nodes) or 'none'}")
    print(f"  Skipped:  {', '.join(skipped_nodes) or 'none'}")
    return {
        "modified_nodes": modified_nodes,
        "skipped_nodes": skipped_nodes,
        "errors": errors,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Self-check (no file modification)
# ══════════════════════════════════════════════════════════════════════════════


def self_check() -> dict[str, Any]:
    """Verify the normalization is structurally sound and consistent.

    Checks:
    - NMC parses
    - All 3 nodes have D4 entry
    - 21bao D4 entry has runtime_visible=True + runtime_visible_evidence
      pointing to PR #336 with merge_commit=0a932be and evidence_anchor=2ec1778e
    - 5bao/9bao D4 entries have runtime_visible=True + runtime_visible_evidence
      pointing to PR #332 with evidence_anchor=09b1d97
    - model_pool.yaml untouched (no smoke_results, no 21bao entries added)
    - All 3 entries: model_call_verified != True, operator_approved != True
    - Forbidden scope: no G-L4 / readiness / model_call_verified ready claims
    """
    passed = 0
    total = 0
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, total
        total += 1
        if cond:
            passed += 1
        else:
            failures.append(f"{name}: {detail}")

    if not NMC_PATH.exists():
        return {"status": "ERROR", "error": f"missing: {NMC_PATH}"}

    with open(NMC_PATH, "r", encoding="utf-8") as f:
        nmc = yaml.safe_load(f) or {}

    check("nmc_parses", isinstance(nmc, dict), "not a dict")
    check("nmc_has_nodes", "nodes" in nmc, "missing 'nodes'")

    # Per-node assertions
    expected_anchors = {
        "21bao": ("2ec1778", "0a932be"),   # PR #336 anchors
        "5bao":  ("09b1d97", None),         # PR #332 anchors
        "9bao":  ("09b1d97", None),         # PR #332 anchors
    }
    for node in NODES:
        matrix = nmc.get("nodes", {}).get(node, {}).get("matrix", [])
        d4 = None
        for e in matrix:
            if isinstance(e, dict) and e.get("model_id") == TARGET_MODEL_ID:
                d4 = e
                break
        check(f"{node}_d4_present", d4 is not None, f"no D4 entry")

        if d4 is None:
            continue

        check(
            f"{node}_runtime_visible_true",
            d4.get("runtime_visible") is True,
            f"runtime_visible={d4.get('runtime_visible')!r}",
        )

        ev = d4.get("runtime_visible_evidence")
        check(f"{node}_has_evidence", isinstance(ev, dict), f"no evidence block")

        if isinstance(ev, dict):
            ev_anchor_hit = expected_anchors[node][0]
            check(
                f"{node}_evidence_anchor_ref",
                ev_anchor_hit in str(ev.get("evidence_anchor", "")),
                f"expected anchor containing {ev_anchor_hit!r}",
            )
            if expected_anchors[node][1] and "merge_commit" in ev:
                check(
                    f"{node}_merge_commit_ref",
                    expected_anchors[node][1] in str(ev.get("merge_commit", "")),
                    f"expected merge_commit containing "
                    f"{expected_anchors[node][1]!r}",
                )

        # Forbidden promotions
        check(
            f"{node}_model_call_verified_not_promoted",
            d4.get("model_call_verified") is not True,
            f"model_call_verified={d4.get('model_call_verified')!r}",
        )
        check(
            f"{node}_operator_approved_not_promoted",
            d4.get("operator_approved") is not True,
            f"operator_approved={d4.get('operator_approved')!r}",
        )

    # model_pool.yaml unchanged (no smoke_results on D4 entry)
    if POOL_PATH.exists():
        with open(POOL_PATH, "r", encoding="utf-8") as f:
            pool = yaml.safe_load(f) or {}
        d4_pool = None
        for m in (pool.get("models") or []):
            if isinstance(m, dict) and m.get("id") == TARGET_MODEL_ID:
                d4_pool = m
                break
        check("pool_d4_present", d4_pool is not None, "no D4 pool entry")
        if d4_pool is not None:
            smoke = d4_pool.get("smoke_results", {}) or {}
            check(
                "pool_no_21bao_smoke",
                "21bao" not in smoke,
                f"smoke_results has 21bao: {smoke}",
            )
            check(
                "pool_no_runtime_visible_field",
                "runtime_visible" not in d4_pool,
                "pool entry has runtime_visible field",
            )
            check(
                "pool_no_model_call_verified_field",
                "model_call_verified" not in d4_pool,
                "pool entry has model_call_verified field",
            )

    # NMC notes should not claim G-L4 / readiness
    notes_str = str(nmc.get("notes", ""))
    check(
        "notes_no_g_l4_ready",
        "G-L4 ready" not in notes_str and "g-l4 ready" not in notes_str.lower(),
        f"notes: {notes_str}",
    )
    check(
        "notes_no_readiness_ready",
        "readiness ready" not in notes_str.lower(),
        f"notes: {notes_str}",
    )

    status = "PASS" if passed == total else "PARTIAL" if passed > 0 else "FAIL"
    return {
        "status": status,
        "passed_count": passed,
        "total": total,
        "failures": failures,
    }


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "G-L3R D4 NMC runtime_visible normalization "
            "(5bao/9bao via PR #332, 21bao via PR #336)"
        ),
    )
    parser.add_argument(
        "--self-check", action="store_true",
        help="Verify normalization invariants without modifying the file",
    )
    parser.add_argument(
        "--format", choices=("human", "json"), default="human",
        help="Output format",
    )
    args = parser.parse_args()

    if args.self_check:
        if args.format == "json":
            import json
            print(json.dumps(self_check(), indent=2, ensure_ascii=False))
        else:
            r = self_check()
            print(f"Status: {r['status']}")
            print(f"Passed: {r['passed_count']}/{r['total']}")
            if r.get("failures"):
                print("Failures:")
                for f in r["failures"]:
                    print(f"  - {f}")
        return

    result = normalize()
    if args.format == "json":
        import json
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
