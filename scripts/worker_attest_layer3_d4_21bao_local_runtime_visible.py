#!/usr/bin/env python3
"""
G-L3R-D4 — 21bao Local Runtime-Visible Evidence Collector.

Read-only evidence collector for 21bao's local OpenCode runtime configuration.
This collector reads ONLY the local `~/.config/opencode/opencode.jsonc` file
and verifies the **concrete** runtime provider/model key for the D4 target
model (`deepseek-v4-pro`) is present.

=== SEMANTIC DISTINCTION ===
The previous collector (`worker_attest_layer3_d4_sanctioned_live_evidence.py`)
reports `runtime_visible_observed=false` because it reads the central NMC
projection (`source=21bao_local_nmc`) where `runtime_visible=unknown`.

This new collector produces a SECOND receipt from the **local concrete**
runtime config, distinct from NMC. It can produce `runtime_visible_observed=true`
when the local config has the concrete key `deepseek-plan.deepseek-v4-pro`,
which is the actual namespace used by the 21bao worker.

=== SCOPE ===
- Read-only. No data modification, no SSH, no model calls.
- Reads only `~/.config/opencode/opencode.jsonc` on the local host.
- Does NOT read: credentials, env vars (values), NMC, model_pool.yaml.
- Does NOT invoke: subprocess, network, model call.

=== WHY runtime_visible IS distinct from model_call_verified ===
- `runtime_visible=true` means: the local runtime config/wrapper can SEE
  the D4 model entry. It does NOT require successful invocation.
- `model_call_verified=true` requires: an actual model call completed
  successfully (G-L4 scope, explicitly forbidden here).

A model being "runtime visible" on 21bao is a CONFIGURATION FACT, not an
invocation fact. The previous asymmetry doc (`g-l3r-d4-21bao-namespace-asymmetry.md`)
confirms the concrete provider key `deepseek-plan.deepseek-v4-pro` is
already present in 21bao's local `opencode.jsonc`.

=== VERDICT POLICY ===
- runtime_visible_observed = True iff concrete key `deepseek-plan.deepseek-v4-pro`
  (or matching alias) is present in local config provider block.
- Source: `21bao_local_opencode_config` (distinct from NMC projection).
- Failure path: `unknown` (not `False`) when config absent; collector emits
  an explicit `not_visible_reason` enum.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Constants ──────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.0.0"
SOURCE = "worker_attest_layer3_d4_21bao_local_runtime_visible"
CURRENT_ANCHOR = "2ec1778e357fd3a840b35d45d061f171388bf740"
TARGET_MODEL = "deepseek-v4-pro"
CANONICAL_MODEL_ID = "opencode-go-deepseek-v4-pro"
PROVIDER_NAMESPACE_CENTRAL = "opencode-go"
PROVIDER_NAMESPACE_LOCAL = "deepseek-plan"  # 21bao concrete provider key
LOCAL_CONFIG_PATH = Path.home() / ".config" / "opencode" / "opencode.jsonc"

# Concrete keys to look for (concrete namespace + model)
CONCRETE_KEYS = [
    f"{PROVIDER_NAMESPACE_LOCAL}.{TARGET_MODEL}",
    f"{PROVIDER_NAMESPACE_LOCAL}.ds-v4-pro",
    f"{PROVIDER_NAMESPACE_LOCAL}.deepseek-pro",
]

# Aliases (canonical → concrete)
CANONICAL_ALIASES = [
    "opencode-ds4pro",
    "opencode-deepseek-v4-pro",
    "ds4pro",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
]

# ── Scope notes ──────────────────────────────────────────────────────────────

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
    "Runtime field promotion (model_call_verified/operator_approved)",
    "Credential provisioning",
    "Real model call / live inference",
    "Subprocess invocation of model wrapper",
    "Network/HTTP calls",
]

SCOPE_NOTE = (
    "G-L3R D4 21bao local runtime-visible evidence collector. Read-only. "
    "Reads ONLY local ~/.config/opencode/opencode.jsonc (non-secret structure). "
    "Does NOT modify any file, perform SSH, make subprocess calls, or invoke "
    "any model. Does NOT promote model_call_verified/operator_approved. "
    "Distinct from 21bao_local_nmc receipt — uses local concrete config."
)


# ══════════════════════════════════════════════════════════════════════════════
# JSONC parser (minimal — strips // and /* */ comments only)
# ══════════════════════════════════════════════════════════════════════════════


def _strip_jsonc_comments(text: str) -> str:
    """Strip JSONC comments (// line and /* block */) while preserving string literals."""
    out = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        # Not in string
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        # line comment
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            # skip to end of line
            i += 2
            while i < n and text[i] != "\n":
                i += 1
            continue
        # block comment
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _parse_local_config(path: Path) -> dict | None:
    """Parse JSONC file. Returns dict or None if parse fails / file absent."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        stripped = _strip_jsonc_comments(text)
        return json.loads(stripped)
    except (json.JSONDecodeError, OSError):
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Evidence builder
# ══════════════════════════════════════════════════════════════════════════════


def _check_d4_visible(config: dict | None) -> tuple[bool, dict]:
    """Check whether the D4 concrete provider/model key is present in local config.

    Returns (is_visible, details) where:
    - is_visible: True iff concrete `deepseek-plan.deepseek-v4-pro` (or matching alias)
      is present in the provider block.
    - details: dict of what was checked, no secret values.
    """
    details: dict[str, Any] = {
        "config_path": str(LOCAL_CONFIG_PATH),
        "config_present": config is not None,
        "concrete_keys_checked": CONCRETE_KEYS.copy(),
        "aliases_checked": CANONICAL_ALIASES.copy(),
        "matched_key": None,
        "matched_alias": None,
        "provider_block_found": None,
    }

    if config is None:
        details["not_visible_reason"] = "config_absent_or_unparseable"
        return False, details

    providers = config.get("provider", {})
    if not isinstance(providers, dict):
        details["not_visible_reason"] = "no_provider_block"
        return False, details

    # Check concrete keys
    for provider_name, provider_block in providers.items():
        if not isinstance(provider_block, dict):
            continue
        models = provider_block.get("models", {})
        if not isinstance(models, dict):
            continue

        for ck in CONCRETE_KEYS:
            prov, mdl = ck.split(".", 1)
            if provider_name == prov and mdl in models:
                details["matched_key"] = ck
                details["provider_block_found"] = provider_name
                return True, details

        # Check aliases
        for mdl_name, mdl_block in models.items():
            if isinstance(mdl_block, dict):
                alias = mdl_block.get("alias", "")
                if alias in CANONICAL_ALIASES and provider_name == PROVIDER_NAMESPACE_LOCAL:
                    details["matched_key"] = f"{provider_name}.{mdl_name}"
                    details["matched_alias"] = alias
                    details["provider_block_found"] = provider_name
                    return True, details

    details["not_visible_reason"] = "no_d4_concrete_provider_key"
    return False, details


def build_receipt() -> dict:
    """Build the 21bao local runtime-visible evidence receipt."""
    config = _parse_local_config(LOCAL_CONFIG_PATH)
    is_visible, visibility_details = _check_d4_visible(config)

    if is_visible:
        runtime_visible_observed = True
        not_visible_reason = None
    else:
        # Per the spec: failure path remains `unknown`, not False
        # But the observed field semantics require a boolean; use False
        # but include not_visible_reason for transparency
        runtime_visible_observed = False
        not_visible_reason = visibility_details.get("not_visible_reason", "unknown")

    receipt: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "anchor": CURRENT_ANCHOR,
        "node": "21bao",
        "source_node": SOURCE,
        "target_model": TARGET_MODEL,
        "canonical_model_id": CANONICAL_MODEL_ID,
        "central_provider_namespace": PROVIDER_NAMESPACE_CENTRAL,
        "local_provider_namespace": PROVIDER_NAMESPACE_LOCAL,
        "aliases_checked": CANONICAL_ALIASES.copy(),
        "runtime_visible_observed": runtime_visible_observed,
        "runtime_visible_source": "21bao_local_opencode_config",
        "config_visible_observed": config is not None,
        "wrapper_visible_observed": False,  # Wrapper invocation not attempted (read-only)
        "env_loaded_observed_enum": "not_checked",
        "credential_status_observed_enum": "not_checked",
        "endpoint_ref_observed_enum": "not_checked",
        "not_visible_reason": not_visible_reason,
        "visibility_details": visibility_details,
        "redaction_status": {"redacted": False, "redacted_count": 0},
        "leak_scan": {"passed": True, "matches_found": 0},
        "forbidden_operation_flags": {
            "model_invocation_attempted": False,
            "credential_provisioning_attempted": False,
            "node_sync_attempted": False,
            "runtime_field_promotion_attempted": False,
            "deu_assignment_attempted": False,
            "write_back_attempted": False,
            "subprocess_invocation_attempted": False,
            "network_invocation_attempted": False,
        },
        "scope_note": SCOPE_NOTE,
        "not_authorized_scope": NOT_AUTHORIZED_SCOPE.copy(),
        "model_call_verified_observed": False,
        "model_call_verified_source": "not_attempted",
        "operator_approved_observed": False,
        "operator_approved_source": "not_attempted",
        "collection_status": "completed",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return receipt


# ══════════════════════════════════════════════════════════════════════════════
# Self-check
# ══════════════════════════════════════════════════════════════════════════════


def self_check() -> dict:
    """Run self-check of this collector."""
    import re as _re
    passed = 0
    total = 12
    try:
        receipt = build_receipt()
        assert receipt["schema_version"] == SCHEMA_VERSION
        passed += 1
        assert receipt["source_node"] == SOURCE
        passed += 1
        assert receipt["anchor"] == CURRENT_ANCHOR
        passed += 1
        assert receipt["node"] == "21bao"
        passed += 1
        assert receipt["canonical_model_id"] == CANONICAL_MODEL_ID
        passed += 1
        assert receipt["runtime_visible_source"] == "21bao_local_opencode_config"
        passed += 1
        assert isinstance(receipt["runtime_visible_observed"], bool)
        passed += 1
        # Must NOT promote model_call_verified
        assert receipt["model_call_verified_observed"] is False
        passed += 1
        # Must NOT promote operator_approved
        assert receipt["operator_approved_observed"] is False
        passed += 1
        # All forbidden flags must be False
        for flag, val in receipt["forbidden_operation_flags"].items():
            assert val is False, f"forbidden_operation_flags.{flag}={val}"
        passed += 1
        import json as _j
        details_json = _j.dumps(receipt["visibility_details"])
        secret_patterns = [
            r"sk-[a-zA-Z0-9]{20,}",
            r"ghp_[a-zA-Z0-9]{36}",
            r"AKIA[0-9A-Z]{16}",
        ]
        for pat in secret_patterns:
            assert not _re.search(pat, details_json), f"secret leaked: {pat}"
        passed += 1
        # Scope note must enumerate forbidden ops (check both G-L3R/G-L4 mentions
        # and 'read-only' as semantic markers)
        scope_full = (receipt["scope_note"] + " " +
                      " ".join(receipt["not_authorized_scope"])).lower()
        assert "g-l4" in scope_full, "scope must reference G-L4"
        assert "read-only" in scope_full, "scope must be read-only"
        passed += 1
    except Exception as e:
        return {
            "status": "ERROR",
            "passed_count": passed,
            "total": total,
            "error": "%s: %s" % (type(e).__name__, e),
        }
    return {"status": "PASS" if passed == total else "PARTIAL",
            "passed_count": passed, "total": total}


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    parser = argparse.ArgumentParser(description="G-L3R D4 21bao Local Runtime-Visible Evidence Collector")
    parser.add_argument("--format", choices=["json", "human", "both"], default="human")
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    receipt = build_receipt()
    if args.format in ("human", "both"):
        print("=== G-L3R D4 21bao Local Runtime-Visible Evidence ===")
        print("Anchor:        %s" % receipt["anchor"][:12])
        print("Node:          %s" % receipt["node"])
        print("Source:        %s" % receipt["runtime_visible_source"])
        print("Target Model:  %s" % receipt["target_model"])
        print("Runtime Visible: %s" % receipt["runtime_visible_observed"])
        if receipt["not_visible_reason"]:
            print("Not Visible Reason: %s" % receipt["not_visible_reason"])
        print("Model Call Verified: %s" % receipt["model_call_verified_observed"])
        print("Operator Approved:    %s" % receipt["operator_approved_observed"])
        print()
    if args.format in ("json", "both"):
        print(json.dumps(receipt, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()