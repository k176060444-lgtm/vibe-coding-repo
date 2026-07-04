#!/usr/bin/env python3
"""
Idempotent NMC normalization script for opencode-go-mimo-v2-5.

Scope (EXACT — no other entries or fields):

  For each of (21bao, 5bao, 9bao) / opencode-go-mimo-v2-5:

    wrapper_valid:      false → true   (if currently False)
    model_call_verified: unknown → true (if currently 'unknown')

  operator_approved must remain 'unknown'.  No other entry (including
  opencode-go-mimo-v2-5-pro, opencode-go-qwen3-7-plus × 3, etc.) is touched.
  No other field (declared, synced, runtime_visible, env_loaded, …) is touched.

Evidence:
  wrapper_valid=true      — 418a40d/b80a757/5685a0d (Stage5 promotion per-node)
  model_call_verified=true — f30c55b (Batch D-R2 canary)

Current false/unknown state was a collateral regression in e39b8c0 (PR #344).

Usage:
    python scripts/normalize_opencode_go_mimo_v2_5_to_nmc.py        # apply
    python scripts/normalize_opencode_go_mimo_v2_5_to_nmc.py 2>&1   # self-check
"""

import copy
import json
import sys
import yaml

NMC_PATH = "scripts/node_model_capability.yaml"
TARGET_NODES = ("21bao", "5bao", "9bao")
TARGET_MODEL = "opencode-go-mimo-v2-5"

ALLOWED_FIELD_CHANGES = {
    "wrapper_valid": {False: True, True: None},       # false→true only
    "model_call_verified": {"unknown": True, True: None},  # unknown→true only
}

FORBIDDEN_FIELDS = ("operator_approved",)


def load_nmc(path: str = NMC_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_nmc(nmc: dict, path: str = NMC_PATH) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(nmc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def check_and_apply(nmc: dict, dry_run: bool = False) -> dict:
    """
    Scan each target node for the target model_id.
    Return a result dict with:
      - changes_found: bool (whether any field needs changing)
      - entries_modified: list of {node, field, old, new}
      - forbidden_attempt: list of errors if trying to touch forbidden field
      - unknown_field: list of errors if field value not in allowed transitions
      - errors: list of all errors (empty = pass)
    """
    result = {
        "entries_found": 0,
        "entries_modified": [],
        "forbidden_attempt": [],
        "unknown_field": [],
        "errors": [],
    }

    for node in TARGET_NODES:
        node_obj = nmc.get("nodes", {}).get(node)
        if not node_obj:
            result["errors"].append(f"node '{node}' not found in NMC")
            continue
        matrix = node_obj.get("matrix", [])
        found = False
        for entry in matrix:
            if entry.get("model_id") == TARGET_MODEL:
                found = True
                result["entries_found"] += 1
                model_entry = entry
                break
        if not found:
            result["errors"].append(f"{node}/{TARGET_MODEL} not found in NMC matrix")
            continue

        # Check forbidden fields first
        for ff in FORBIDDEN_FIELDS:
            if ff in model_entry:
                old_val = model_entry.get(ff)
                # We expect old_val == 'unknown'. If not, it's been externally changed — abort.
                if old_val != "unknown":
                    result["forbidden_attempt"].append(
                        f"{node}/{TARGET_MODEL}.{ff} = {old_val!r} (expected 'unknown'); "
                        "will not touch"
                    )

        # Check and apply allowed fields
        for field, transition_map in ALLOWED_FIELD_CHANGES.items():
            old_val = model_entry.get(field)
            if old_val in transition_map:
                new_val = transition_map[old_val]
                if new_val is not None:  # None means unchanged
                    result["entries_modified"].append({
                        "node": node,
                        "field": field,
                        "old": old_val,
                        "new": new_val,
                    })
                    if not dry_run:
                        model_entry[field] = new_val
                # else: already in desired state (True) — no-op
            else:
                result["unknown_field"].append(
                    f"{node}/{TARGET_MODEL}.{field} = {old_val!r} (not in allowed "
                    f"transitions {transition_map})"
                )

    return result


def self_check() -> dict:
    nmc = load_nmc()
    result = check_and_apply(nmc, dry_run=True)
    return result


def apply() -> dict:
    nmc = load_nmc()
    result = check_and_apply(nmc, dry_run=False)

    if result["errors"]:
        result["applied"] = False
        return result

    if result["forbidden_attempt"]:
        result["applied"] = False
        return result

    if result["unknown_field"]:
        result["applied"] = False
        return result

    if not result["entries_modified"]:
        result["applied"] = True
        result["idempotent"] = True
        return result

    save_nmc(nmc)
    result["applied"] = True
    result["idempotent"] = False
    return result


# === CLI ===
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Idempotent NMC normalization for opencode-go-mimo-v2-5"
    )
    parser.add_argument("--self-check", action="store_true",
                        help="check what would change (dry-run); exit 0 if anything would change")
    parser.add_argument("--json", action="store_true",
                        help="output JSON")

    args = parser.parse_args()

    if args.self_check:
        r = self_check()
        print(json.dumps(r, indent=2, default=str))
        sys.exit(0 if r["entries_modified"] else (0 if not r["errors"] else 1))
    else:
        r = apply()
        print(json.dumps(r, indent=2, default=str))
        if r.get("applied") and not r.get("idempotent"):
            print("\nNMC modified — please verify with git diff")
        elif r.get("applied") and r.get("idempotent"):
            print("\nNMC already up to date — no changes (idempotent)")
        sys.exit(0 if r.get("applied") else 1)
