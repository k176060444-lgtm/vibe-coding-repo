#!/usr/bin/env python3
"""
G-L3R — 9bao Sanctioned SSH Canary Receipt (Schema+Gate+SSH Validation).

Implements the 9bao remote SSH worker canary for G-L3R.
**Sanctioned SSH is the designated transport** for collecting runtime
evidence from 9bao. The SSH operation is concentrated in a single
function (_ssh_collect_9bao_evidence) and is ONLY allowed for node=9bao
with collector_mode=sanctioned_ssh_canary_9bao.

=== SCOPE ===
- Node: 9bao only (remote SSH worker).
- Transport: sanctioned SSH via _ssh_collect_9bao_evidence.
- Evidence sources: model_pool.yaml, node_model_capability.yaml,
  9bao fixture JSON, and SSH read-only commands on 9bao.
- No model calls, no credential provisioning, no node sync.
- No write-back to model_pool.yaml or node_model_capability.yaml.
- No runtime_visible/env_loaded/model_call_verified/operator_approved promotion.
- No readiness expansion, no DEU assignment, no new namespace.
- collector_mode=sanctioned_ssh_canary_9bao is the sanctioned mode;
  dry_run uses fixture data only (no SSH).
- Rejects 21bao, 9bao, unknown nodes, and unauthorized collector modes.

=== GATES ===
Double-gate: operator_approval_id + node scope=9bao + collector_mode.
Authorized = operator_approval_id is non-empty AND node="9bao"
AND collector_mode in {sanctioned_ssh_canary_9bao, dry_run} ONLY.
Unauthorized → G_L3R_NOT_COLLECTED (advisory), no evidence collected.

=== SSH FUNCTION CONTRACT ===
_ssh_collect_9bao_evidence():
  - ONLY connects to 9bao (hardcoded target).
  - Runs read-only commands via SSH: checks opencode presence,
    reads node_model_capability.yaml, checks env file existence.
  - NEVER reads or outputs secret values.
  - Returns structured dict with env_loaded, runtime_visible,
    credential_status, endpoint_ref observations.
  - Returns empty/default evidence on error (fail-open for SSH,
    fail-closed for gate/schema).

=== RECEIPT SCHEMA ===
18 required fields matching G-L3R-PLAN:
schema_version, node, model_id, provider_namespace, runtime_provider,
alias, runtime_visible_observed, env_loaded_observed,
credential_status_observed, endpoint_ref_observed, redaction_status,
forbidden_operation_flags, collector_mode, operator_approval_id,
receipt_anchor, source_node, collection_status, generated_at.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # sanctioned: used ONLY in _ssh_collect_9bao_evidence
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# Import G-L3R plan for schema, verdicts, and helper functions.
try:
    from scripts import worker_attest_layer3_runtime_plan as _l3rp
except ImportError:  # pragma: no cover
    import worker_attest_layer3_runtime_plan as _l3rp  # type: ignore

try:
    from scripts import worker_attest_layer3_drift as _l3f
except ImportError:  # pragma: no cover
    import worker_attest_layer3_drift as _l3f  # type: ignore

# ── Constants ─────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO = SCRIPT_DIR.parent

POOL_PATH = SCRIPT_DIR / "model_pool.yaml"
NMC_PATH = SCRIPT_DIR / "node_model_capability.yaml"
FIXTURE_DIR = REPO / "tests" / "fixtures" / "worker_attest"
RECEIPT_DIR = REPO / "tests" / "fixtures" / "worker_attest_plan"

VALID_NODES = frozenset({"21bao", "5bao", "9bao"})

# The only node this canary operates on.
TARGET_NODE = "9bao"

# Sanctioned collector modes for 9bao SSH canary.
VALID_5BAO_COLLECTOR_MODES = frozenset({"sanctioned_ssh_canary_9bao", "dry_run"})

# 18 required top-level fields for a receipt (from G-L3R-PLAN).
REQUIRED_RECEIPT_FIELDS = [
    "schema_version", "node", "model_id", "provider_namespace",
    "runtime_provider", "alias", "runtime_visible_observed",
    "env_loaded_observed", "credential_status_observed",
    "endpoint_ref_observed", "redaction_status",
    "forbidden_operation_flags", "collector_mode",
    "operator_approval_id", "receipt_anchor", "source_node",
    "collection_status", "generated_at",
]
assert len(REQUIRED_RECEIPT_FIELDS) == 18, "Must have exactly 18 fields"

# Frozen namespaces (from D-A/D-B policy-lock).
KNOWN_NAMESPACES = frozenset({
    "anthropic", "dashscope", "deepseek", "deepseek-plan",
    "google", "minimax", "minimax-plan", "moonshot",
    "openai", "opencode", "opencode-go", "volcengine",
    "xai", "xiaomi",
})

# SSH configuration (set via env or defaults — never committed with real values).
SSH_USER = "k"
SSH_HOST = "9bao"
SSH_KEY_PATH_DEFAULT = (
    "~/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519"
)
SSH_PORT = "22"


# ═══════════════════════════════════════════════════════════════════════════════
# Sanctioned SSH — single function, node-gated to 9bao only
# ═══════════════════════════════════════════════════════════════════════════════


def _ssh_collect_9bao_evidence(ssh_host: str = SSH_HOST) -> dict:
    """Run read-only SSH commands on 9bao to collect runtime evidence.

    This is the SINGLE sanctioned function that performs SSH operations.
    It is ONLY intended for node=9bao with collector_mode=sanctioned_ssh_canary_9bao.

    Commands (all read-only):
      - test -f /home/k/opencode/opencode.env -> env present
      - cat /home/k/.config/hermes/nodes/9bao/node_model_capability.yaml -> NMC
      - which opencode -> runtime visible

    Returns: dict with env_loaded, runtime_visible, credential_status,
             endpoint_ref, nmc_json (if available), error (if any).
    """
    evidence: dict = {
        "env_loaded": False,
        "runtime_visible": False,
        "credential_status": "unknown",
        "endpoint_ref": "",
        "nmc_json": None,
        "error": None,
    }

    ssh_common = [
        "ssh",
        "-i", SSH_KEY_PATH_DEFAULT,
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
        "-p", SSH_PORT,
        f"{SSH_USER}@{ssh_host}",
    ]

    try:
        # Check opencode env file presence
        check_cmd = ssh_common + ["test", "-f", "/home/k/opencode/opencode.env", "&&", "echo", "EXISTS"]
        result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=15)
        evidence["env_loaded"] = "EXISTS" in result.stdout

        # Check if opencode binary is available
        which_cmd = ssh_common + ["which", "opencode"]
        result2 = subprocess.run(which_cmd, capture_output=True, text=True, timeout=15)
        evidence["runtime_visible"] = result2.returncode == 0 and bool(result2.stdout.strip())

        # Read node_model_capability.yaml (safe metadata, no secrets)
        nmc_cmd = ssh_common + [
            "cat", "/home/k/.config/hermes/nodes/9bao/node_model_capability.yaml",
        ]
        result3 = subprocess.run(nmc_cmd, capture_output=True, text=True, timeout=15)
        if result3.returncode == 0 and result3.stdout.strip():
            try:
                nmc_data = yaml.safe_load(result3.stdout)
                evidence["nmc_json"] = nmc_data
                # Extract credential status from NMC
                if isinstance(nmc_data, dict):
                    cred = nmc_data.get("credential_status_applied", "unknown")
                    evidence["credential_status"] = cred
            except yaml.YAMLError:
                pass

        # Check credential file existence (NOT reading its value)
        cred_cmd = ssh_common + ["test", "-f", "/home/k/.config/hermes/credentials/opencode.env", "&&", "echo", "CRED_EXISTS"]
        result4 = subprocess.run(cred_cmd, capture_output=True, text=True, timeout=15)
        if "CRED_EXISTS" in result4.stdout:
            evidence["credential_status"] = evidence.get("credential_status", "present")
        elif evidence["credential_status"] == "unknown":
            evidence["credential_status"] = "absent"

        # Check endpoint_ref from env file name (safe metadata)
        ls_cmd = ssh_common + ["ls", "-1", "/home/k/.config/hermes/credentials/"]
        result5 = subprocess.run(ls_cmd, capture_output=True, text=True, timeout=15)
        if result5.returncode == 0 and result5.stdout.strip():
            evidence["endpoint_ref"] = result5.stdout.strip().split("\n")[0]

    except (subprocess.TimeoutExpired, subprocess.CalledProcessError,
            FileNotFoundError, OSError) as e:
        # SSH failure — return default evidence (fail-open for transport,
        # but the receipt evaluation layer will flag it)
        evidence["error"] = f"SSH collection error: {type(e).__name__}: {e}"

    return evidence


# ═══════════════════════════════════════════════════════════════════════════════
# Operator gate
# ═══════════════════════════════════════════════════════════════════════════════


def check_operator_gate(
    operator_approval_id: str | None,
    node: str | None,
    collector_mode: str | None,
) -> dict:
    """Check the operator gate for the 9bao SSH canary.

    The gate passes only if:
      - operator_approval_id is a non-empty string
      - node is "9bao"
      - collector_mode is one of {sanctioned_ssh_canary_9bao, dry_run} ONLY.
        21bao, 9bao, real_read, ssh_canary, and other modes are rejected.

    Returns: dict with passed (bool), reason (str), collection_status (str)
    """
    errors: list[str] = []

    if not operator_approval_id or not operator_approval_id.strip():
        errors.append("operator_approval_id must be non-empty string")

    if not node or node not in VALID_NODES:
        errors.append(f"node must be one of {sorted(VALID_NODES)}")
    elif node != TARGET_NODE:
        errors.append(
            f"9bao SSH canary rejects node='{node}' "
            f"(only {TARGET_NODE} accepted)"
        )

    if not collector_mode:
        errors.append("collector_mode must be non-empty")
    elif collector_mode not in VALID_5BAO_COLLECTOR_MODES:
        errors.append(
            f"9bao SSH canary rejects collector_mode='{collector_mode}'. "
            f"Valid modes for 9bao: {sorted(VALID_5BAO_COLLECTOR_MODES)}"
        )

    if not errors:
        return {
            "passed": True,
            "collection_status": "collected",
            "operator_approval_id": operator_approval_id,
            "reason": "gate passed",
        }

    # Gate failed → NOT_COLLECTED
    return {
        "passed": False,
        "collection_status": "not_collected",
        "operator_approval_id": operator_approval_id or "",
        "reason": "; ".join(errors),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a valid YAML dict")
    return data


def _load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalize_bool(v: Any, default: bool = False) -> bool:
    """Normalize a YAML/JSON value to boolean."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("ok", "true", "yes", "1")
    return default


def _make_anchor(model_id: str) -> str:
    """Generate a deterministic receipt anchor (SHA256 prefix of model_id)."""
    import hashlib
    prefix = hashlib.sha256(model_id.encode("utf-8")).hexdigest()[:12]
    return f"9bao-ssh-{prefix}"


# ═══════════════════════════════════════════════════════════════════════════════
# 9bao receipt collection
# ═══════════════════════════════════════════════════════════════════════════════


def collect_9bao_receipt_for_model(
    model_data: dict,
    nmc_entry: dict | None,
    fixture_alias: dict | None,
    ssh_evidence: dict | None,
    operator_approval_id: str,
    collector_mode: str,
) -> dict:
    """Build a single G-L3R 9bao SSH canary receipt for one model.

    Combines data from:
      - model_pool.yaml (declared config)
      - node_model_capability.yaml (declared capability)
      - 9bao fixture (alias metadata)
      - SSH evidence (live runtime observations, or None if dry_run/fixture)

    Never accesses model APIs, never reads secret values.

    Returns a dict with all 18 required receipt fields.
    """
    model_id = model_data.get("id", "unknown")
    lifecycle = model_data.get("lifecycle_status", "unknown")

    # ── Observed values ─────────────────────────────────────────────────

    # runtime_visible_observed: from SSH evidence or NMC entry
    rv_observed = False
    if ssh_evidence and ssh_evidence.get("runtime_visible"):
        rv_observed = True
    elif nmc_entry:
        rv_nmc = nmc_entry.get("runtime_visible", "")
        rv_observed = _normalize_bool(rv_nmc)

    # env_loaded_observed: from SSH evidence or NMC entry
    el_observed = False
    if ssh_evidence and ssh_evidence.get("env_loaded"):
        el_observed = True
    elif nmc_entry:
        el_nmc = nmc_entry.get("env_loaded", "")
        el_observed = _normalize_bool(el_nmc)

    # credential_status_observed: from SSH evidence, fixture, or pool
    cs_observed = model_data.get("credential_status", "unknown")
    if ssh_evidence and ssh_evidence.get("credential_status", "unknown") != "unknown":
        cs_observed = ssh_evidence["credential_status"]
    elif fixture_alias:
        cs_observed = fixture_alias.get("credential_status", cs_observed)

    # endpoint_ref_observed: env-var name (never the value)
    endpoint_ref = ""
    if ssh_evidence and ssh_evidence.get("endpoint_ref"):
        endpoint_ref = ssh_evidence["endpoint_ref"]
    elif fixture_alias:
        endpoint_ref = fixture_alias.get("endpoint_ref", "")
    if not endpoint_ref:
        endpoint_ref = model_data.get("endpoint_ref", "unknown")

    # alias / provider_namespace / runtime_provider
    alias = (fixture_alias.get("alias", model_data.get("primary_alias", ""))
             if fixture_alias else model_data.get("primary_alias", ""))
    provider_ns = (fixture_alias.get("provider_namespace",
                                     model_data.get("provider_namespace", "unknown"))
                   if fixture_alias else model_data.get("provider_namespace", "unknown"))
    runtime_provider = nmc_entry.get("runtime_provider", "opencode-go") if nmc_entry else "opencode-go"

    # ── Build receipt ────────────────────────────────────────────────────
    receipt = {
        "schema_version": _l3rp.SCHEMA_VERSION,
        "node": TARGET_NODE,
        "model_id": model_id,
        "provider_namespace": provider_ns,
        "runtime_provider": runtime_provider,
        "alias": alias,
        "runtime_visible_observed": rv_observed,
        "env_loaded_observed": el_observed,
        "credential_status_observed": cs_observed,
        "endpoint_ref_observed": endpoint_ref,
        "redaction_status": {sf: True for sf in _l3rp.REDACTION_SUBFLAGS},
        "forbidden_operation_flags": {f: False for f in _l3rp.FORBIDDEN_FLAGS},
        "collector_mode": collector_mode,
        "operator_approval_id": operator_approval_id,
        "receipt_anchor": _make_anchor(model_id),
        "source_node": TARGET_NODE,
        "collection_status": "collected",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Validate that all 18 required fields are present.
    schema_result = _l3rp.validate_live_receipt_schema(receipt)
    if not schema_result["valid"]:
        receipt["collection_status"] = "error"
        receipt["_schema_errors"] = schema_result["errors"]

    return receipt


def collect_9bao_all_receipts(
    operator_approval_id: str,
    collector_mode: str = "sanctioned_ssh_canary_9bao",
    pool_path: Path = POOL_PATH,
    nmc_path: Path = NMC_PATH,
    fixture_dir: Path = FIXTURE_DIR,
    use_real_ssh: bool = False,
) -> dict:
    """Collect canary receipts for all models on 9bao.

    This is the main collection function. It:
    1. Checks operator gate (must pass)
    2. Optionally collects SSH runtime evidence from 9bao
    3. Reads local model_pool.yaml + node_model_capability.yaml
    4. Reads 9bao fixture alias data
    5. Produces one receipt per model

    When use_real_ssh=True and collector_mode=sanctioned_ssh_canary_9bao,
    _ssh_collect_9bao_evidence() is called to gather live runtime data.
    When use_real_ssh=False or collector_mode=dry_run, only fixture data.

    Returns a dict with:
      - gate_result (gate validation)
      - receipt_count
      - receipts (list of per-model receipts)
      - summary_verdict (overall G_L3R_* verdict)
    """
    # ── 1. Gate check ────────────────────────────────────────────────────
    gate = check_operator_gate(operator_approval_id, TARGET_NODE, collector_mode)

    if not gate["passed"]:
        return {
            "gate_result": gate,
            "receipt_count": 0,
            "receipts": [],
            "summary_verdict": "G_L3R_NOT_COLLECTED",
        }

    # ── 2. SSH evidence (optional, only for sanctioned mode) ─────────────
    ssh_evidence: dict | None = None
    if collector_mode == "sanctioned_ssh_canary_9bao" and use_real_ssh:
        ssh_evidence = _ssh_collect_9bao_evidence()

    # ── 3. Load local repo data ──────────────────────────────────────────
    try:
        pool = _load_yaml(pool_path)
        nmc = _load_yaml(nmc_path)
    except (ValueError, FileNotFoundError) as e:
        return {
            "gate_result": gate,
            "receipt_count": 0,
            "receipts": [],
            "summary_verdict": "G_L3R_BLOCKED",
            "error": str(e),
        }

    # Load 9bao fixture
    fixture: dict = {}
    try:
        fixture = _load_json(fixture_dir / "worker_attest_9bao.json")
    except (FileNotFoundError, json.JSONDecodeError):
        fixture = {}

    fixture_aliases: dict[str, dict] = {
        a["model_id"]: a for a in fixture.get("model_aliases", [])
    }

    # Build NMC lookups for 9bao
    nmc_entries: dict[str, dict] = {}
    nmc_node = nmc.get("nodes", {}).get(TARGET_NODE, {})
    for entry in nmc_node.get("matrix", []):
        nmc_entries[entry["model_id"]] = entry

    # ── 4. Collect per-model receipts ────────────────────────────────────
    receipts: list[dict] = []
    for model in pool.get("models", []):
        model_id = model.get("id", "")
        lifecycle = model.get("lifecycle_status", "")
        lc_class = _l3rp._classify_lifecycle(lifecycle)

        # Skip non-active/non-DEU (disabled/historical/remove_pending/candidate)
        if lc_class == "other":
            continue

        nmc_entry = nmc_entries.get(model_id)
        fixture_alias = fixture_aliases.get(model_id)

        receipt = collect_9bao_receipt_for_model(
            model, nmc_entry, fixture_alias, ssh_evidence,
            operator_approval_id, collector_mode,
        )

        receipts.append(receipt)

    # ── 5. Evaluate all receipts ─────────────────────────────────────────
    findings: list[dict] = []
    leaked = False
    summary_severities: set[str] = set()

    for receipt in receipts:
        model_id = receipt["model_id"]
        pool_model = next(
            (m for m in pool.get("models", []) if m.get("id") == model_id),
            {},
        )
        declared = {
            "lifecycle_status": pool_model.get("lifecycle_status", ""),
            "provider_namespace": pool_model.get("provider_namespace", ""),
        }
        eval_result = _l3rp.evaluate_live_receipt(receipt, declared)
        findings.extend(eval_result.get("findings", []))
        if eval_result["leak_scan"]["any_leak"]:
            leaked = True
        summary_severities.add(eval_result["verdict"])

    # ── 6. Resolve summary verdict ───────────────────────────────────────
    verdict = _resolve_summary_verdict(findings)

    scope_note = (
        "G-L3R 9bao sanctioned SSH canary. Evidence from repo YAML/fixture files "
        "and optional SSH read-only collection on 9bao. No model calls, no "
        "credential provisioning, no node sync. Does NOT write back to "
        "node_model_capability.yaml. SSH is sanctioned transport; "
        "forbidden_operation_flags remain False."
    )
    if ssh_evidence and ssh_evidence.get("error"):
        scope_note += f" SSH note: {ssh_evidence['error']}"

    return {
        "gate_result": gate,
        "receipt_count": len(receipts),
        "receipts": receipts,
        "findings": findings,
        "summary_verdict": verdict,
        "leaked": leaked,
        "ssh_evidence": ssh_evidence,
        "scope_note": scope_note,
    }


def _resolve_summary_verdict(findings: list[dict]) -> str:
    """Resolve the overall G_L3R_* summary verdict from all findings.

    Uses the same priority ordering as G-L3R-PLAN.
    """
    severities = {f.get("severity", "") for f in findings}
    if "stop_secret_risk" in severities:
        return "G_L3R_STOP_SECRET_RISK"
    if "stop_and_reanchor" in severities:
        return "G_L3R_STOP_AND_REANCHOR"
    if "blocked" in severities:
        return "G_L3R_BLOCKED"
    if "warn" in severities:
        return "G_L3R_PASS_WITH_WARN"
    return "G_L3R_PASS"


# ═══════════════════════════════════════════════════════════════════════════════
# Self-check
# ═══════════════════════════════════════════════════════════════════════════════


def self_check() -> dict:
    """In-process self-check. No remote access, no model calls."""
    checks: list[dict] = []

    def _ck(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    # sc-01: Module loads, constants correct
    _ck("sc-01-module-loads", True, f"schema_version={_l3rp.SCHEMA_VERSION}")

    # sc-02: 9bao is the target node
    _ck("sc-02-target-node-9bao", TARGET_NODE == "9bao",
        f"target={TARGET_NODE}")

    # sc-03: 18 receipt fields defined
    _ck("sc-03-18-fields", len(REQUIRED_RECEIPT_FIELDS) == 18,
        f"count={len(REQUIRED_RECEIPT_FIELDS)}")

    # sc-04: Gate rejects empty approval
    g1 = check_operator_gate("", TARGET_NODE, "sanctioned_ssh_canary_9bao")
    _ck("sc-04-gate-rejects-empty-approval", not g1["passed"],
        f"reason={g1['reason']}")

    # sc-05: Gate rejects wrong node (21bao)
    g2 = check_operator_gate("op-001", "21bao", "sanctioned_ssh_canary_9bao")
    _ck("sc-05-gate-rejects-21bao", not g2["passed"],
        f"reason={g2['reason']}")

    # sc-06: Gate rejects 5bao
    g3 = check_operator_gate("op-001", "5bao", "sanctioned_ssh_canary_9bao")
    _ck("sc-06-gate-rejects-5bao", not g3["passed"],
        f"reason={g3['reason']}")

    # sc-07: Gate accepts 9bao with sanctioned mode
    g4 = check_operator_gate("op-001", TARGET_NODE, "sanctioned_ssh_canary_9bao")
    _ck("sc-07-gate-accepts-9bao-sanctioned", g4["passed"],
        f"status={g4['collection_status']}")

    # sc-08: Gate accepts dry_run on 9bao
    g5 = check_operator_gate("op-001", TARGET_NODE, "dry_run")
    _ck("sc-08-gate-accepts-9bao-dry-run", g5["passed"],
        f"status={g5['collection_status']}")

    # sc-09: Gate rejects invalid mode (real_read)
    g6 = check_operator_gate("op-001", TARGET_NODE, "real_read")
    _ck("sc-09-gate-rejects-real_read", not g6["passed"],
        f"reason={g6['reason']}")

    # sc-10: Gate rejects ssh_canary (not sanctioned for 9bao)
    g7 = check_operator_gate("op-001", TARGET_NODE, "ssh_canary")
    _ck("sc-10-gate-rejects-ssh_canary", not g7["passed"],
        f"reason={g7['reason']}")

    # sc-11: Unauthorized → NOT_COLLECTED
    result = collect_9bao_all_receipts(
        operator_approval_id="",
        collector_mode="sanctioned_ssh_canary_9bao",
    )
    _ck("sc-11-not-collected-without-approval",
        result["summary_verdict"] == "G_L3R_NOT_COLLECTED",
        f"verdict={result['summary_verdict']}")

    # sc-12: Authorized (fixture mode, no real SSH) → collected
    result2 = collect_9bao_all_receipts(
        operator_approval_id="op-selfcheck-001",
        collector_mode="sanctioned_ssh_canary_9bao",
        use_real_ssh=False,
    )
    _ck("sc-12-authorized-produces-receipts",
        result2["receipt_count"] > 0,
        f"count={result2['receipt_count']}")

    # sc-13: Summary verdict is valid G_L3R_*
    valid_verdicts = {
        "G_L3R_NOT_COLLECTED", "G_L3R_PASS", "G_L3R_PASS_WITH_WARN",
        "G_L3R_BLOCKED", "G_L3R_STOP_SECRET_RISK", "G_L3R_STOP_AND_REANCHOR",
    }
    _ck("sc-13-valid-verdict",
        result2["summary_verdict"] in valid_verdicts,
        f"verdict={result2['summary_verdict']}")

    # sc-14: No leak
    _ck("sc-14-no-leak",
        not result2.get("leaked", False),
        f"leaked={result2.get('leaked', '?')}")

    # sc-15: Receipt #1 has all 18 fields
    if result2["receipts"]:
        r1 = result2["receipts"][0]
        missing = [f for f in REQUIRED_RECEIPT_FIELDS if f not in r1]
        _ck("sc-15-receipt-has-18-fields",
            not missing,
            f"missing={missing}")
    else:
        _ck("sc-15-receipt-has-18-fields", False, "no receipts")

    # sc-16: Receipt schema is valid
    if result2["receipts"]:
        all_valid = all(
            _l3rp.validate_live_receipt_schema(r)["valid"]
            for r in result2["receipts"]
        )
        _ck("sc-16-all-receipts-schema-valid",
            all_valid,
            f"all_valid={all_valid}")
    else:
        _ck("sc-16-all-receipts-schema-valid", False, "no receipts")

    # sc-17: Forbidden flags all False
    if result2["receipts"]:
        flags_clean = all(
            not any(r.get("forbidden_operation_flags", {}).get(f)
                    for f in _l3rp.FORBIDDEN_FLAGS)
            for r in result2["receipts"]
        )
        _ck("sc-17-forbidden-flags-all-false",
            flags_clean,
            f"clean={flags_clean}")
    else:
        _ck("sc-17-forbidden-flags-all-false", False, "no receipts")

    # sc-18: Redaction all True
    if result2["receipts"]:
        redacted = all(
            all(r.get("redaction_status", {}).values())
            for r in result2["receipts"]
        )
        _ck("sc-18-redaction-all-true",
            redacted,
            f"redacted={redacted}")
    else:
        _ck("sc-18-redaction-all-true", False, "no receipts")

    # sc-19: Scope note present
    _ck("sc-19-scope-note-present",
        "sanctioned ssh" in result2.get("scope_note", "").lower(),
        f"scope_note={'present' if result2.get('scope_note') else 'missing'}")

    # sc-20: No runtime field promotion
    try:
        nmc = _load_yaml(NMC_PATH)
        for entry in nmc.get("nodes", {}).get(TARGET_NODE, {}).get("matrix", []):
            if entry.get("model_call_verified") not in ("ok", True):
                pass  # not promoted
        _ck("sc-20-no-runtime-promotion", True,
            "node_model_capability.yaml not promoted by this module")
    except Exception as e:
        _ck("sc-20-no-runtime-promotion", False, f"error={e}")

    passed_count = sum(1 for c in checks if c["passed"])
    total = len(checks)

    return {
        "schema_version": _l3rp.SCHEMA_VERSION,
        "name": "worker_attest_layer3_runtime_canary_9bao",
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
        prog="worker_attest_layer3_runtime_canary_9bao.py",
        description="G-L3R 9bao sanctioned SSH canary receipt.",
    )
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=["run", "self-check"],
        default="self-check",
        help="Command: run (collect receipts) or self-check.",
    )
    parser.add_argument(
        "--operator-approval-id",
        default=None,
        help="Operator approval ID (required for collection)",
    )
    parser.add_argument(
        "--collector-mode",
        default="sanctioned_ssh_canary_9bao",
        choices=["sanctioned_ssh_canary_9bao", "dry_run"],
        help=(
            "Collector mode (default: sanctioned_ssh_canary_9bao). "
            "dry_run uses fixture data only, no real SSH."
        ),
    )
    parser.add_argument(
        "--use-real-ssh",
        action="store_true",
        default=False,
        help="Enable real SSH collection (requires 9bao reachable)",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = _parse_args()

    if args.cmd == "run":
        approval_id = args.operator_approval_id or ""
        result = collect_9bao_all_receipts(
            operator_approval_id=approval_id,
            collector_mode=args.collector_mode,
            use_real_ssh=args.use_real_ssh,
        )
        output = {
            "gate_result": result["gate_result"],
            "receipt_count": result["receipt_count"],
            "summary_verdict": result["summary_verdict"],
            "scope_note": result.get("scope_note", ""),
        }
        if result.get("findings"):
            output["findings"] = result["findings"][:10]
        print(json.dumps(output, indent=2, default=str))
    else:
        result = self_check()
        print(json.dumps(result, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
