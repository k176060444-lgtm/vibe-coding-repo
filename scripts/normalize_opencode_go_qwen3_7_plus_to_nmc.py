#!/usr/bin/env python3
"""
G-L4 / Stage4 Class B — opencode-go-qwen3-7-plus NMC normalization.

This bounded normalization adds the opencode-go-qwen3-7-plus entry to
the NMC matrices for each node listed in its pool allowed_nodes
(currently 21bao, 5bao, 9bao). All 6 runtime state fields are set to
'unknown' — no promotion.

Usage:
    python scripts/normalize_opencode_go_qwen3_7_plus_to_nmc.py --self-check
    python scripts/normalize_opencode_go_qwen3_7_plus_to_nmc.py

Hard rules:
- Does NOT modify scripts/model_pool.yaml.
- Does NOT promote any runtime state (synced / runtime_visible /
  env_loaded / wrapper_valid / model_call_verified / operator_approved).
- Smoke evidence from pool is preserved as metadata only.
- Idempotent: re-running produces identical NMC.
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

TARGET_MODEL_ID = "opencode-go-qwen3-7-plus"
REQUIRED_ALLOWED_NODES = ["5bao", "9bao", "21bao"]
REQUIRED_LIFECYCLE_STATUS = "enabled_assigned"


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _dump_yaml(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            data, f, sort_keys=False, allow_unicode=True,
            default_flow_style=False, width=120,
        )


def _verify_pool_entry(pool: dict) -> dict:
    """Verify the pool entry for TARGET_MODEL_ID is eligible.

    Returns the pool entry on success. Raises SystemExit with
    STOP_AND_REANCHOR on failure.
    """
    models = pool.get("models") or []
    entry = next((m for m in models if m.get("id") == TARGET_MODEL_ID), None)
    if entry is None:
        print(f"STOP_AND_REANCHOR: {TARGET_MODEL_ID} not found in pool")
        sys.exit(2)

    if entry.get("enabled") is not True:
        print(
            f"STOP_AND_REANCHOR: {TARGET_MODEL_ID} enabled is "
            f"{entry.get('enabled')!r}, expected True"
        )
        sys.exit(2)

    allowed = list(entry.get("allowed_nodes") or [])
    if allowed != REQUIRED_ALLOWED_NODES:
        print(
            f"STOP_AND_REANCHOR: {TARGET_MODEL_ID} allowed_nodes={allowed!r}, "
            f"expected {REQUIRED_ALLOWED_NODES!r}"
        )
        sys.exit(2)

    lifecycle = entry.get("lifecycle_status")
    if lifecycle != REQUIRED_LIFECYCLE_STATUS:
        print(
            f"STOP_AND_REANCHOR: {TARGET_MODEL_ID} lifecycle_status={lifecycle!r}, "
            f"expected {REQUIRED_LIFECYCLE_STATUS!r}"
        )
        sys.exit(2)

    return entry


def _build_new_entry(pool_entry: dict) -> dict:
    """Build a new NMC matrix entry with all runtime states = 'unknown'."""
    smoke = pool_entry.get("smoke_results") or {}
    entry: dict[str, Any] = {
        "model_id": TARGET_MODEL_ID,
        "canonical_provider": pool_entry.get("canonical_provider"),
        "provider_namespace": pool_entry.get("provider_namespace"),
        "runtime_provider": pool_entry.get("canonical_provider"),
        "declared": True,
        "synced": "unknown",
        "runtime_visible": "unknown",
        "env_loaded": "unknown",
        "wrapper_valid": "unknown",
        "model_call_verified": "unknown",
        "operator_approved": "unknown",
    }
    if smoke:
        entry["smoke_evidence_pool"] = {
            node: {
                "status": info.get("status"),
                "last_verified": info.get("last_verified"),
                "smoke_phase": info.get("smoke_phase"),
                "wrapper": info.get("wrapper"),
                "invocation": info.get("invocation"),
            }
            for node, info in smoke.items()
        }
    return entry


def _ensure_node_entry(nmc: dict, node: str, pool_entry: dict) -> bool:
    """Ensure TARGET_MODEL_ID exists in nmc['nodes'][node]['matrix'].

    Returns True if a new entry was added, False if it was already present.
    """
    nodes = nmc.setdefault("nodes", {})
    nd = nodes.setdefault(node, {})
    matrix = nd.setdefault("matrix", [])
    for existing in matrix:
        if existing.get("model_id") == TARGET_MODEL_ID:
            return False
    new_entry = _build_new_entry(pool_entry)
    matrix.append(new_entry)
    nd["total_entries"] = len(matrix)
    return True


def self_check(pool: dict, nmc: dict) -> int:
    """Self-check: verify preconditions and report whether NMC already
    has the entry for each required node. Does not modify NMC."""
    _verify_pool_entry(pool)
    nodes = nmc.get("nodes") or {}
    print(f"self-check passed: pool entry eligible")
    print(f"required nodes: {REQUIRED_ALLOWED_NODES}")
    for node in REQUIRED_ALLOWED_NODES:
        nd = nodes.get(node) or {}
        matrix = nd.get("matrix") or []
        present = any(e.get("model_id") == TARGET_MODEL_ID for e in matrix)
        print(f"  {node}: {TARGET_MODEL_ID} {'already present' if present else 'NOT present'}")
    return 0


def apply(pool: dict, nmc: dict) -> tuple[dict, int]:
    """Apply normalization idempotently. Returns (nmc, added_count)."""
    pool_entry = _verify_pool_entry(pool)
    added = 0
    for node in REQUIRED_ALLOWED_NODES:
        if _ensure_node_entry(nmc, node, pool_entry):
            added += 1
            print(f"added {TARGET_MODEL_ID} to {node} matrix")
        else:
            print(f"{TARGET_MODEL_ID} already in {node} matrix (idempotent)")
    return nmc, added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--self-check", action="store_true",
        help="Only verify preconditions; do not modify NMC",
    )
    args = parser.parse_args()

    pool = _load_yaml(POOL_PATH)
    nmc = _load_yaml(NMC_PATH)

    if args.self_check:
        return self_check(pool, nmc)

    nmc, added = apply(pool, nmc)
    if added > 0:
        _dump_yaml(NMC_PATH, nmc)
        print(f"NMC written: {NMC_PATH}")
        print(f"total new entries added: {added}")
    else:
        print("no changes; NMC already up-to-date")
    return 0


if __name__ == "__main__":
    sys.exit(main())