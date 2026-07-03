#!/usr/bin/env python3
"""
G-L3R-D4 — Sanctioned Live Evidence Collection for deepseek-v4-pro.

Implements Option B step 1: read-only runtime-visible evidence collection
for the deepseek-v4-pro (opencode-go-deepseek-v4-pro / opencode-ds4pro)
target model across all 3 nodes.

=== SCOPE ===
- Target model: deepseek-v4-pro (opencode-go-ds4pro) ONLY.
- Nodes: 21bao (local read-only), 5bao/9bao (sanctioned SSH read-only).
- Collects: runtime_visible_observed, config_visible_observed,
  wrapper_visible_observed, env_loaded_observed_enum,
  credential_status_observed_enum, endpoint_ref_observed_enum.
- NO model inference / model calls / credential provisioning / node sync.
- NO write-back to model_pool.yaml or node_model_capability.yaml.
- NO runtime_visible/env_loaded/model_call_verified/operator_approved promotion.
- Output: redacted receipt per node with collection_status + leak_scan.
- Wrong node/mode → NOT_COLLECTED. Unauthorized → NOT_COLLECTED.

=== COLLECTOR MODES ===
- 21bao_local_sanctioned_read: read-only local file inspection on 21bao.
- 5bao_sanctioned_ssh_read: sanctioned SSH read-only on 5bao.
- 9bao_sanctioned_ssh_read: sanctioned SSH read-only on 9bao.
- dry_run: no-op (returns collection_status=not_collected, no SSH/file read).

=== RECEIPT FIELDS ===
schema_version, anchor, node, source_node, target_model,
canonical_model_id, provider_namespace, runtime_provider,
aliases_checked, runtime_visible_observed, runtime_visible_source,
config_visible_observed, wrapper_visible_observed,
env_loaded_observed_enum, credential_status_observed_enum,
endpoint_ref_observed_enum, redaction_status, leak_scan,
forbidden_operation_flags, collector_mode, operator_approval_id,
collection_status, generated_at.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess  # sanctioned: used ONLY in SSH collection functions
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore

# ── Constants ─────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.0.0"
SOURCE = "worker_attest_layer3_d4_sanctioned_live_evidence"
# D4 collector merge base anchor (PR #321 merge = all 3 fix PRs).
CURRENT_ANCHOR = "baad421f3213f666ce5b1448e7923b0ad2c640f7"

# Target model identity — deepseek-v4-pro (the D4 blocker).
TARGET_MODEL = "deepseek-v4-pro"
# Canonical model IDs in model_pool.yaml for the D4 model.
CANONICAL_MODEL_IDS = frozenset({
    "opencode-go-deepseek-v4-pro",      # active
    "deepseek-plan-deepseek-v4-pro",    # legacy/disabled
})
# Provider namespaces for D4.
TARGET_PROVIDER_NAMESPACES = frozenset({"opencode-go", "deepseek-plan"})
# Runtime providers for D4.
TARGET_RUNTIME_PROVIDERS = frozenset({"opencode-go", "deepseek-plan"})
# Aliases to check.
TARGET_ALIASES = frozenset({
    "opencode-ds4pro",
    "deepseek-v4-pro",
    "ds4pro",
    "deepseek-v4-flash",
})

VALID_NODES = frozenset({"21bao", "5bao", "9bao"})

# Collector modes — strictly gated per node.
COLLECTOR_MODE_21BAO = "21bao_local_sanctioned_read"
COLLECTOR_MODE_5BAO = "5bao_sanctioned_ssh_read"
COLLECTOR_MODE_9BAO = "9bao_sanctioned_ssh_read"
ALL_COLLECTOR_MODES = frozenset({
    COLLECTOR_MODE_21BAO, COLLECTOR_MODE_5BAO, COLLECTOR_MODE_9BAO, "dry_run",
})

# SSH configuration (env-overridable, defaults match 5bao canary pattern)
SSH_KEY_PATH_DEFAULT = "~/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519"

# Safety: SSH only allowed for 5bao and 9bao.
SSH_ALLOWED_NODES = frozenset({"5bao", "9bao"})

# Forbidden operation flags — all must stay False.
FORBIDDEN_FLAGS = [
    "model_invocation_attempted",
    "credential_provisioning_attempted",
    "node_sync_attempted",
    "runtime_field_promotion_attempted",
    "deu_assignment_attempted",
    "write_back_attempted",
]

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO = SCRIPT_DIR.parent

# ── Helper: repo-local data loaders ──────────────────────────────────────────

def _load_model_pool() -> dict:
    path = SCRIPT_DIR / "model_pool.yaml"
    if not path.exists() or yaml is None:
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def _load_nmc() -> dict:
    path = SCRIPT_DIR / "node_model_capability.yaml"
    if not path.exists() or yaml is None:
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


# ── Redaction utilities ──────────────────────────────────────────────────────

SUSPICIOUS_PATTERNS = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{16,}|"
    r"Bearer\s+[A-Za-z0-9_.-]{16,}|AKIA[0-9A-Z]{12,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----|"
    r"://[^/\s:@]*:[^/\s@]+@)"
)


def _leak_scan(obj: Any) -> dict:
    """Scan a JSON-serializable object for secret patterns.

    Returns: {"passed": True/False, "matches_found": int, "details": [str]}
    """
    def _scan(value: Any, path: str = "$") -> list[str]:
        findings: list[str] = []
        if isinstance(value, str):
            for m in SUSPICIOUS_PATTERNS.finditer(value):
                findings.append(f"{path}: matched pattern at pos {m.start()}")
        elif isinstance(value, dict):
            for k, v in value.items():
                findings.extend(_scan(v, f"{path}.{k}"))
        elif isinstance(value, list):
            for i, v in enumerate(value):
                findings.extend(_scan(v, f"{path}[{i}]"))
        return findings

    details = _scan(obj)
    return {
        "passed": len(details) == 0,
        "matches_found": len(details),
        "details": details,
    }


def _maybe_redact(data: dict) -> dict:
    """Redact any secret-like values from a dict in-place.

    Returns the same dict (with redacted values) + redaction_status.
    """
    redacted_count = 0
    for k, v in data.items():
        if isinstance(v, str) and SUSPICIOUS_PATTERNS.search(v):
            data[k] = f"*** REDACTED ({k}) ***"
            redacted_count += 1
        elif isinstance(v, dict):
            sub = _maybe_redact(v)
            redacted_count += sub.get("_redacted_count", 0)
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, str) and SUSPICIOUS_PATTERNS.search(item):
                    v[i] = f"*** REDACTED ({k}[{i}]) ***"
                    redacted_count += 1
                elif isinstance(item, dict):
                    sub = _maybe_redact(item)
                    redacted_count += sub.get("_redacted_count", 0)
    data["_redacted_count"] = redacted_count
    return data


# ── Sanctioned SSH evidence collection ──────────────────────────────────────

# Remote collector script for 5bao/9bao (read-only metadata extraction).
# Only reads safe metadata: model ID, alias, provider_namespace,
# env var NAMES (never values), credential file existence (not content),
# endpoint file name (not content).
_REMOTE_COLLECTOR_SCRIPT = r"""
import json, os, sys

result = {
    "models_found": [],
    "env_names": [],
    "credential_files": [],
    "endpoint_files": [],
    "opencode_exists": False,
    "config_paths": [],
}

# Check opencode binary: which (PATH) first, then common install paths as fallback
opencode_path = os.popen("which opencode 2>/dev/null || true").read().strip()
if not opencode_path:
    for candidate in [
        os.path.expanduser("~/.opencode/bin/opencode"),
        os.path.expanduser("~/.npm-global/bin/opencode"),
        "/usr/local/bin/opencode",
    ]:
        expanded = os.path.expanduser(candidate)
        if os.path.exists(expanded):
            opencode_path = expanded
            break
result["opencode_exists"] = bool(opencode_path)

# Check opencode config file
config_paths = [
    os.path.expanduser("~/.config/opencode/config.json"),
    os.path.expanduser("~/.config/opencode/opencode.jsonc"),
]
for p in config_paths:
    if os.path.exists(p):
        result["config_paths"].append(p)
        try:
            data = json.load(open(p))
            # Extract model IDs and aliases (safe metadata)
            if isinstance(data, dict):
                for section_name in ["models", "model", "providers", "provider"]:
                    section = data.get(section_name, {})
                    if isinstance(section, dict):
                        for key, val in section.items():
                            if isinstance(val, dict):
                                entry = {
                                    "model_id": key,
                                    "id": val.get("id", ""),
                                    "alias": val.get("alias", ""),
                                    "provider": val.get("provider", ""),
                                    "namespace": val.get("namespace", ""),
                                }
                                result["models_found"].append(entry)
                                # Recurse into nested models (e.g. provider.models)
                                nested = val.get("models", None)
                                if isinstance(nested, dict):
                                    for nkey, nval in nested.items():
                                        if isinstance(nval, dict):
                                            nested_entry = {
                                                "model_id": nkey,
                                                "id": nval.get("id", ""),
                                                "alias": nval.get("alias", "") or nval.get("name", ""),
                                                "provider": key,
                                                "namespace": val.get("namespace", "") or val.get("npm", ""),
                                            }
                                            result["models_found"].append(nested_entry)
        except (json.JSONDecodeError, OSError):
            pass

# Check credential directory (file NAMES only, never content)
cred_dir = os.path.expanduser("~/.config/hermes/credentials")
if os.path.isdir(cred_dir):
    result["credential_files"] = os.listdir(cred_dir)

# Check endpoint directory (file NAMES only, never content)
endpoint_dir = os.path.expanduser("~/.config/hermes/endpoints")
if os.path.isdir(endpoint_dir):
    result["endpoint_files"] = os.listdir(endpoint_dir)

# Check env file NAMES (never values)
env_path = os.path.expanduser("~/.config/opencode/opencode.env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and "=" in line:
                name_only = line.split("=", 1)[0].strip()
                result["env_names"].append(name_only)

print(json.dumps(result))
"""


def _ssh_collect_read_only(node: str) -> dict:
    """Run read-only SSH commands on `node` (5bao or 9bao) to collect metadata.

    Returns: dict with keys:
      - opencode_exists (bool)
      - models_found (list of dicts with model_id/alias/provider/namespace)
      - credential_files (list of filenames)
      - endpoint_files (list of filenames)
      - env_names (list of env var NAMES)
      - error (str or None)
    This is the ONLY sanctioned SSH function. It NEVER reads secret values.
    """
    evidence: dict = {
        "opencode_exists": False,
        "models_found": [],
        "credential_files": [],
        "endpoint_files": [],
        "env_names": [],
        "error": None,
    }

    # Map node to SSH connection parameters.
    host_map = {
        "5bao": ("vibeworker", "192.168.5.6", "22222"),
        "9bao": ("vibeworker", "192.168.9.6", "22222"),
    }
    user, host, port = host_map.get(node, ("", "", ""))
    if not user:
        evidence["error"] = f"unknown node for SSH: {node}"
        return evidence

    # Resolve SSH key path.
    key_path = os.environ.get(
        "VIBEDEV_SSH_KEY",
        os.path.expanduser(SSH_KEY_PATH_DEFAULT),
    )

    ssh_common = [
        "ssh",
        "-i", key_path,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
        "-p", port,
        f"{user}@{host}",
    ]

    try:
        # Run the remote collector script via SSH (read-only, secret-safe).
        # Pipe the script via stdin to avoid multi-line quoting issues
        # with Windows/MSYS subprocess across SSH.
        cmd = ssh_common + ["python3"]
        result = subprocess.run(
            cmd, input=_REMOTE_COLLECTOR_SCRIPT,
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            try:
                remote_data = json.loads(result.stdout)
                evidence.update(remote_data)
            except (json.JSONDecodeError, ValueError):
                evidence["error"] = (
                    "SSH remote script returned non-JSON output"
                )
        else:
            evidence["error"] = (
                f"SSH remote script returned exit {result.returncode}: "
                f"{result.stderr[:500] if result.stderr else '(no stderr)'}"
            )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError,
            FileNotFoundError, OSError) as e:
        evidence["error"] = f"SSH error: {type(e).__name__}: {e}"

    return evidence


# ── 21bao local evidence collection ──────────────────────────────────────────

def _collect_21bao_local_evidence() -> dict:
    """Collect read-only runtime evidence from 21bao (local Windows node).

    Reads:
      - model_pool.yaml for D4 target model declarations
      - node_model_capability.yaml for D4 NMC entries
      - Local opencode config (if accessible) for metadata
    NO SSH, NO subprocess (beyond safe Python yaml/json reads).
    """
    evidence: dict = {
        "pool_models": [],
        "nmc_entries": [],
        "opencode_config_found": False,
        "local_config_models": [],
        "error": None,
    }

    # Load model_pool.yaml
    pool = _load_model_pool()
    pool_models = pool.get("models", []) if isinstance(pool, dict) else []
    for m in pool_models:
        if isinstance(m, dict):
            mid = m.get("id", "")
            if any(t in mid for t in TARGET_ALIASES) or mid in CANONICAL_MODEL_IDS:
                evidence["pool_models"].append({
                    "id": mid,
                    "enabled": m.get("enabled"),
                    "lifecycle_status": m.get("lifecycle_status"),
                    "allowed_nodes": m.get("allowed_nodes"),
                    "provider_namespace": m.get("provider_namespace"),
                    "runtime_provider": m.get("runtime_provider"),
                    "primary_alias": m.get("primary_alias"),
                })

    # Load node_model_capability.yaml
    nmc = _load_nmc()
    if isinstance(nmc, dict):
        nodes = nmc.get("nodes", {})
        for node_name in ("21bao",):
            n = nodes.get(node_name, {})
            matrix = n.get("matrix", []) if isinstance(n, dict) else []
            for entry in matrix:
                if isinstance(entry, dict):
                    check = " ".join([
                        str(entry.get("name", "")),
                        str(entry.get("model_id", "")),
                        str(entry.get("primary_alias", "")),
                    ]).lower()
                    if "deepseek-v4-pro" in check or "ds4pro" in check:
                        evidence["nmc_entries"].append({
                            "node": node_name,
                            "model_id": entry.get("model_id"),
                            "name": entry.get("name"),
                            "primary_alias": entry.get("primary_alias"),
                            "runtime_visible": entry.get("runtime_visible"),
                            "declared": entry.get("declared"),
                            "synced": entry.get("synced"),
                            "wrapper_valid": entry.get("wrapper_valid"),
                            "credential_status": entry.get("credential_status"),
                            "endpoint_ref": entry.get("endpoint_ref"),
                        })

    # Check local opencode config (safe metadata only)
    opencode_config_paths = [
        Path.home() / ".config" / "opencode" / "opencode.jsonc",
        Path.home() / ".config" / "opencode" / "config.json",
    ]
    for cp in opencode_config_paths:
        if cp.exists():
            evidence["opencode_config_found"] = True
            try:
                data = json.loads(cp.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    for section in ("models", "providers"):
                        sec = data.get(section, {})
                        if isinstance(sec, dict):
                            for key, val in sec.items():
                                if isinstance(val, dict):
                                    evidence["local_config_models"].append({
                                        "key": key,
                                        "alias": val.get("alias", ""),
                                        "provider": val.get("provider", ""),
                                    })
            except (json.JSONDecodeError, OSError):
                pass
            break

    return evidence


# ── Receipt builder ──────────────────────────────────────────────────────────

def _build_empty_forbidden_flags() -> dict:
    return {flag: False for flag in FORBIDDEN_FLAGS}


def _build_receipt(
    node: str,
    collector_mode: str,
    operator_approval_id: str,
    evidence: dict,
    gate_passed: bool = True,
) -> dict:
    """Build a redacted D4 live evidence receipt.

    This is the single receipt builder for all nodes.
    """
    # Determine runtime_visible_observed from evidence
    runtime_visible_observed = False
    runtime_visible_source = ""

    if node == "21bao":
        nmc_entries = evidence.get("nmc_entries", [])
        runtime_visible_observed = any(
            e.get("runtime_visible") is True for e in nmc_entries
        )
        runtime_visible_source = (
            "21bao_local_nmc" if nmc_entries else "21bao_local_nmc_no_entries"
        )
        # Also check local config
        config_found = evidence.get("opencode_config_found", False)
        config_visible_observed = config_found
        # Read wrapper_valid from NMC entries; fall back to False if none
        wrapper_visible_observed = any(
            e.get("wrapper_valid") is True for e in nmc_entries
        ) if nmc_entries else False
        env_loaded_observed_enum = (
            "config_only" if config_found else "not_checked"
        )
        credential_status_observed_enum = "not_checked"
        endpoint_ref_observed_enum = "not_checked"
        if nmc_entries:
            # Take from first NMC entry's credential_status/endpoint_ref
            first = nmc_entries[0]
            cs = first.get("credential_status")
            if cs:
                credential_status_observed_enum = str(cs)
            er = first.get("endpoint_ref")
            if er:
                endpoint_ref_observed_enum = str(er)
    else:
        # 5bao / 9bao — SSH-based evidence
        models_found = evidence.get("models_found", [])
        # Check if target model is in the SSH-returned models
        d4_found = [
            m for m in models_found
            if any(t in str(m.get("model_id", "") + m.get("alias", "")).lower()
                   for t in ["deepseek-v4-pro", "ds4pro", "deepseek-coder",
                             "opencode-go-deepseek"])
        ]
        runtime_visible_observed = evidence.get("opencode_exists", False) and len(d4_found) > 0
        runtime_visible_source = (
            f"{node}_ssh_opencode_config" if runtime_visible_observed
            else f"{node}_ssh_not_found"
        )
        config_visible_observed = evidence.get("opencode_exists", False)
        wrapper_visible_observed = False
        env_loaded_observed_enum = (
            "env_names_present" if evidence.get("env_names")
            else "not_found"
        )
        credential_files = evidence.get("credential_files", [])
        credential_status_observed_enum = (
            f"files_present:{','.join(sorted(credential_files))}"
            if credential_files else "not_found"
        )
        endpoint_files = evidence.get("endpoint_files", [])
        endpoint_ref_observed_enum = (
            f"files_present:{','.join(sorted(endpoint_files))}"
            if endpoint_files else "not_found"
        )

    # Leak scan on the evidence dict
    leak_result = _leak_scan(evidence)
    evidence_leak_scan = {
        "passed": leak_result["passed"],
        "matches_found": leak_result["matches_found"],
    }

    # Build aliases_checked
    aliases_checked = sorted(TARGET_ALIASES)

    # Determine canonical_model_id and provider_namespace from pool entries
    canonical_model_id = "unknown"
    provider_namespace = "unknown"
    runtime_provider = "unknown"
    for m in evidence.get("pool_models", []):
        if m.get("enabled") is True or m.get("lifecycle_status") == "enabled_assigned":
            canonical_model_id = m.get("id", canonical_model_id)
            provider_namespace = m.get("provider_namespace", provider_namespace)
            runtime_provider = m.get("runtime_provider", runtime_provider)
        elif canonical_model_id == "unknown":
            # Fall back to first found
            canonical_model_id = m.get("id", canonical_model_id)

    # Build forbidden flags
    forbidden_operation_flags = _build_empty_forbidden_flags()

    # Determine collection_status
    if not gate_passed:
        collection_status = "not_collected"
    elif collector_mode == "dry_run":
        collection_status = "not_collected"
    elif evidence.get("error"):
        collection_status = "error"
    else:
        collection_status = "completed"

    receipt: dict = {
        "schema_version": SCHEMA_VERSION,
        "anchor": CURRENT_ANCHOR,
        "node": node,
        "source_node": SOURCE,
        "target_model": TARGET_MODEL,
        "canonical_model_id": canonical_model_id,
        "provider_namespace": provider_namespace,
        "runtime_provider": runtime_provider,
        "aliases_checked": aliases_checked,
        "runtime_visible_observed": runtime_visible_observed,
        "runtime_visible_source": runtime_visible_source,
        "config_visible_observed": config_visible_observed,
        "wrapper_visible_observed": wrapper_visible_observed,
        "env_loaded_observed_enum": env_loaded_observed_enum,
        "credential_status_observed_enum": credential_status_observed_enum,
        "endpoint_ref_observed_enum": endpoint_ref_observed_enum,
        "redaction_status": {
            "redacted": False,
            "redacted_count": 0,
        },
        "leak_scan": evidence_leak_scan,
        "forbidden_operation_flags": forbidden_operation_flags,
        "collector_mode": collector_mode,
        "operator_approval_id": operator_approval_id,
        "collection_status": collection_status,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    # Apply redaction as a final safety pass.
    snap = json.dumps(receipt, default=str)
    redacted_snap, redacted_count = SUSPICIOUS_PATTERNS.subn(
        "*** REDACTED ***", snap
    )
    if redacted_count > 0:
        receipt["redaction_status"] = {
            "redacted": True,
            "redacted_count": redacted_count,
        }
        receipt = json.loads(redacted_snap)

    # Leak scan on the receipt itself (merge with evidence scan)
    receipt_leak = _leak_scan(receipt)
    # Combine: if either evidence or receipt has leak, report it
    combined_passed = evidence_leak_scan["passed"] and receipt_leak["passed"]
    receipt["leak_scan"] = {
        "passed": combined_passed,
        "matches_found": evidence_leak_scan["matches_found"]
                        + receipt_leak["matches_found"],
    }

    return receipt


# ── Operator gate ────────────────────────────────────────────────────────────

def check_operator_gate(
    operator_approval_id: str | None,
    node: str | None,
    collector_mode: str | None,
) -> dict:
    """Check the operator gate for D4 sanctioned live evidence collection.

    Gate passes only if:
      - operator_approval_id is non-empty
      - node is one of {21bao, 5bao, 9bao}
      - collector_mode is valid for the node:
        - 21bao: {21bao_local_sanctioned_read, dry_run}
        - 5bao:  {5bao_sanctioned_ssh_read, dry_run}
        - 9bao:  {9bao_sanctioned_ssh_read, dry_run}
    """
    errors: list[str] = []

    if not operator_approval_id or not operator_approval_id.strip():
        errors.append("operator_approval_id must be non-empty string")

    if not node or node not in VALID_NODES:
        errors.append(f"node must be one of {sorted(VALID_NODES)}")
    elif node not in SSH_ALLOWED_NODES and node != "21bao":
        errors.append(f"unknown node: {node}")

    if not collector_mode:
        errors.append("collector_mode must be non-empty")
    elif collector_mode not in ALL_COLLECTOR_MODES:
        errors.append(
            f"rejects collector_mode='{collector_mode}'. "
            f"Valid modes: {sorted(ALL_COLLECTOR_MODES)}"
        )
    elif node:
        # Node-mode gating
        valid_for_node = {
            "21bao": {COLLECTOR_MODE_21BAO, "dry_run"},
            "5bao": {COLLECTOR_MODE_5BAO, "dry_run"},
            "9bao": {COLLECTOR_MODE_9BAO, "dry_run"},
        }
        allowed = valid_for_node.get(node, set())
        if collector_mode not in allowed:
            errors.append(
                f"collector_mode='{collector_mode}' not valid for "
                f"node='{node}'. Allowed: {sorted(allowed)}"
            )

    # Extra safety: reject 21bao SSH
    if node == "21bao" and collector_mode and "ssh" in collector_mode:
        errors.append("21bao is local-exec/control; SSH collector modes rejected")

    if not errors:
        return {
            "passed": True,
            "collection_status": "collected",
            "operator_approval_id": operator_approval_id,
            "reason": "gate passed",
        }

    return {
        "passed": False,
        "collection_status": "not_collected",
        "operator_approval_id": operator_approval_id or "",
        "reason": "; ".join(errors),
    }


# ── Main collection dispatcher ──────────────────────────────────────────────

VALID_COLLECTOR_MODES = {
    "21bao": {COLLECTOR_MODE_21BAO, "dry_run"},
    "5bao": {COLLECTOR_MODE_5BAO, "dry_run"},
    "9bao": {COLLECTOR_MODE_9BAO, "dry_run"},
}


def collect_d4_live_evidence(
    node: str,
    collector_mode: str = "dry_run",
    operator_approval_id: str = "",
) -> dict:
    """Collect sanctioned live evidence for D4 target model on `node`.

    This is the main public API. Returns a full receipt dict.
    """
    # 1. Operator gate
    gate = check_operator_gate(operator_approval_id, node, collector_mode)
    gate_passed = gate["passed"]
    if not gate_passed:
        return _build_receipt(
            node, collector_mode, operator_approval_id,
            {"error": gate["reason"]},
            gate_passed=False,
        )

    # 2. Collect evidence per node
    evidence: dict = {}
    if collector_mode == "dry_run":
        evidence = {
            "pool_models": [],
            "nmc_entries": [],
            "opencode_config_found": False,
            "local_config_models": [],
            "models_found": [],
            "env_names": [],
            "credential_files": [],
            "endpoint_files": [],
            "opencode_exists": False,
            "error": None,
        }
        # Still load pool/NMC for dry_run (repo-local, safe)
        pool = _load_model_pool()
        pool_models = pool.get("models", []) if isinstance(pool, dict) else []
        for m in pool_models:
            if isinstance(m, dict):
                mid = m.get("id", "")
                if any(t in mid for t in TARGET_ALIASES) or mid in CANONICAL_MODEL_IDS:
                    evidence["pool_models"].append({
                        "id": mid,
                        "enabled": m.get("enabled"),
                        "lifecycle_status": m.get("lifecycle_status"),
                        "allowed_nodes": m.get("allowed_nodes"),
                        "provider_namespace": m.get("provider_namespace"),
                        "runtime_provider": m.get("runtime_provider"),
                        "primary_alias": m.get("primary_alias"),
                    })
        evidence["error"] = "dry_run mode: no live collection performed"
    elif node == "21bao":
        evidence = _collect_21bao_local_evidence()
    elif node in SSH_ALLOWED_NODES:
        evidence = _ssh_collect_read_only(node)
    else:
        evidence = {"error": f"unknown node: {node}"}

    return _build_receipt(node, collector_mode, operator_approval_id, evidence)


# ── Self check ──────────────────────────────────────────────────────────────

REQUIRED_RECEIPT_FIELDS = [
    "schema_version", "anchor", "node", "source_node",
    "target_model", "canonical_model_id", "provider_namespace",
    "runtime_provider", "aliases_checked", "runtime_visible_observed",
    "runtime_visible_source", "config_visible_observed",
    "wrapper_visible_observed", "env_loaded_observed_enum",
    "credential_status_observed_enum", "endpoint_ref_observed_enum",
    "redaction_status", "leak_scan", "forbidden_operation_flags",
    "collector_mode", "operator_approval_id", "collection_status",
    "generated_at",
]


def self_check() -> dict:
    """Self-check: validate that all receipt fields are present.

    Returns: dict with passed, errors (list), total_fields, expected_count.
    """
    errors: list[str] = []
    for node in VALID_NODES:
        for mode in {COLLECTOR_MODE_21BAO, COLLECTOR_MODE_5BAO,
                     COLLECTOR_MODE_9BAO, "dry_run"}:
            # Skip mismatched modes
            valid = VALID_COLLECTOR_MODES.get(node, set())
            if mode not in valid and mode != "dry_run":
                continue
            receipt = collect_d4_live_evidence(
                node=node,
                collector_mode=mode,
                operator_approval_id="self-check",
            )
            missing = [
                f for f in REQUIRED_RECEIPT_FIELDS if f not in receipt
            ]
            if missing:
                errors.append(
                    f"{node}/{mode}: missing fields: {missing}"
                )
            # Verify forbidden flags
            ff = receipt.get("forbidden_operation_flags", {})
            for flag in FORBIDDEN_FLAGS:
                if ff.get(flag, None) is not True:
                    pass  # fine
                else:
                    errors.append(
                        f"{node}/{mode}: forbidden flag {flag} is True"
                    )

    # Build scope note
    scope_note = {
        "scope": [
            "D4 sanctioned live evidence collection only",
            "Read-only: no model inference, credential provisioning, "
            "node sync, runtime promotion, DEU assignment, new namespace",
            "Target: opencode-go-deepseek-v4-pro / deepseek-v4-pro only",
            "21bao: local read; 5bao/9bao: sanctioned SSH read",
        ],
        "not_authorized_scope": [
            "G-L4 live inference / model_call_verified promotion",
            "G-READINESS (readiness ready assertion)",
            "Formal G-D-A (DEU assignment)",
            "Formal G-D-B (DEU enablement decision)",
            "G-GRAY / GRAY_ACCEPTANCE",
            "PR-7 (model_pool.yaml schema v1.3+)",
            "Baseline03 (stage 8 hardening)",
            "Stage8 (production readiness)",
            "Runtime data write-back to model_pool.yaml",
            "Runtime data write-back to node_model_capability.yaml",
            "runtime_visible/env_loaded/model_call_verified/operator_approved promotion",
            "New namespace enablement",
            "Real model call / live inference",
        ],
    }

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "total_fields": len(REQUIRED_RECEIPT_FIELDS),
        "expected_count": len(REQUIRED_RECEIPT_FIELDS),
        "scope_note": scope_note,
    }


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="G-L3R D4 Sanctioned Live Evidence Collector"
    )
    parser.add_argument(
        "--node", choices=sorted(VALID_NODES),
        help="Target node (21bao, 5bao, 9bao)",
    )
    parser.add_argument(
        "--mode", choices=sorted(ALL_COLLECTOR_MODES), default="dry_run",
        help=f"Collector mode (default: dry_run)",
    )
    parser.add_argument(
        "--approval-id", default="",
        help="Operator approval ID (required for real collection)",
    )
    parser.add_argument(
        "--self-check", action="store_true",
        help="Run self-check and exit",
    )

    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(0 if result["passed"] else 1)

    if not args.node:
        parser.error("--node is required (unless --self-check is used)")

    receipt = collect_d4_live_evidence(
        node=args.node,
        collector_mode=args.mode,
        operator_approval_id=args.approval_id,
    )
    print(json.dumps(receipt, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
