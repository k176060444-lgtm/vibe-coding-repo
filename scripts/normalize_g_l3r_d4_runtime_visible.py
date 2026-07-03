#!/usr/bin/env python3
"""
G-L3R D4 Receipt-to-NMC Normalization: update NMC entries for 5bao/9bao
to reflect clean-main sanctioned D4 live evidence (PR #332).

Usage: python scripts/normalize_g_l3r_d4_runtime_visible.py
"""
import sys
import os
import yaml

from pathlib import Path

REPO = Path(__file__).parent.parent
NMC_PATH = REPO / "scripts/node_model_capability.yaml"

TARGET_MODEL_ID = "opencode-go-deepseek-v4-pro"

EVIDENCE = {
    "runtime_visible_evidence": {
        "source": "PR #332 clean-main sanctioned live evidence",
        "approval_id": "OPERATOR-20260703-G-L3R-D4-LIVE-EVIDENCE-003",
        "evidence_anchor": "09b1d97f0cab774e3eb023c9768a40d8165a1d46",
        "closure_anchor": "cde599d6fb1584942499ddf4ffe12a6f901a72d2",
        "collector": "5bao_ssh_opencode_config / 9bao_ssh_opencode_config",
    }
}

def normalize():
    if not NMC_PATH.exists():
        print(f"ERROR: NMC file not found: {NMC_PATH}")
        sys.exit(1)

    with open(NMC_PATH, "r", encoding="utf-8") as f:
        nmc = yaml.safe_load(f) or {}

    modified_nodes = []
    unchanged_nodes = []

    for node in ["21bao", "5bao", "9bao"]:
        matrix = nmc.get("nodes", {}).get(node, {}).get("matrix", [])
        found = False
        for entry in matrix:
            if entry.get("model_id") == TARGET_MODEL_ID:
                found = True
                old_rv = entry.get("runtime_visible")

                if node == "21bao":
                    # 21bao MUST remain unknown/false/residual
                    entry["runtime_visible"] = "unknown"  # ensure not True
                    # Remove any evidence_ref if accidentally added
                    entry.pop("runtime_visible_evidence", None)
                    entry["notes"] = (
                        "R8 documented residual: 21bao local opencode.jsonc has no "
                        "opencode-go provider block. See docs/baseline02/"
                        "g-l3r-d4-21bao-namespace-asymmetry.md"
                    )
                    unchanged_nodes.append(node)
                    print(f"  {node}: runtime_visible unchanged (residual)")
                else:
                    # 5bao / 9bao — add evidence-based runtime_visible=True
                    entry["runtime_visible"] = True
                    entry["runtime_visible_evidence"] = EVIDENCE["runtime_visible_evidence"]
                    modified_nodes.append(node)
                    print(f"  {node}: runtime_visible changed {old_rv!r} -> True")

                # Must NOT change these fields
                assert entry.get("model_call_verified") in ("unknown", None, False), \
                    f"{node}: model_call_verified must not be promoted"
                assert entry.get("operator_approved") in ("unknown", None, False), \
                    f"{node}: operator_approved must not be promoted"
                assert entry.get("env_loaded") in (True, "True", "unknown"), \
                    f"{node}: env_loaded must not be promoted to False"
                break

        if not found:
            print(f"  {node}: WARNING — D4 model not found in NMC matrix")

    # Update header notes
    header = nmc.get("notes", "")
    norm_note = (
        f"G-L3R D4 normalization applied: {', '.join(modified_nodes)} "
        f"runtime_visible=true per PR #332 evidence anchor 09b1d97. "
        f"{', '.join(unchanged_nodes)} residual unchanged."
    )
    nmc["notes"] = norm_note

    # Write back with comments preserved (ruamel is not available, use standard yaml)
    with open(NMC_PATH, "w", encoding="utf-8", newline="\n") as f:
        yaml.dump(nmc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    print(f"\nNormalization complete.")
    print(f"  Modified: {', '.join(modified_nodes)}")
    print(f"  Unchanged: {', '.join(unchanged_nodes)}")
    return modified_nodes, unchanged_nodes


if __name__ == "__main__":
    normalize()
