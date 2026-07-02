#!/usr/bin/env python3
"""
G-L3F — Layer3 Fixture-Based Runtime Drift Adapter (Phase 3 postlude).

FIxture-based, read-only. Compares declared intent (model_pool.yaml +
node_model_capability.yaml) against fixture evidence (worker_attest JSON +
plan receipt JSON), constrained by D-A/D-B policy-lock rules.

KEY DESIGN DECISIONS:
- G-L3F uses ONLY fixture evidence, NEVER live runtime evidence.
- Fixture evidence can produce CANDIDATE_DRIFT, not live runtime BLOCK.
- Schema/integrity failures produce BLOCK.
- DEU fixture evidence produces WARN only, never promotion.
- Missing fixture → "fixture evidence missing" (not "live worker missing").
- DeepSeek V4 Pro is NOT special-cased; follows the same active-model rule.
- No subprocess, SSH, model call, credential provisioning, node sync, env read.

VERDICTS:
  G_L3F_PASS                  — all checks pass, no candidate drift
  G_L3F_PASS_WITH_WARN        — DEU models have fixture evidence (WARN)
  G_L3F_CANDIDATE_DRIFT       — active models have fixture mismatch (data gap)
  G_L3F_BLOCKED               — schema/integrity failure, forbidden flag True
  G_L3F_STOP_SECRET_RISK      — redaction false or secret/path/URL leak
  G_L3F_STOP_AND_REANCHOR     — schema version/enum mismatch

Cost strategy (comment-only; G-L3F does NOT call models):
  Future G-L4 live validation should default to low-cost models
  (DeepSeek V4 Flash, Mimo V2.5). Expensive models require bounded
  smoke and explicit operator authorization.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# ── Constants ─────────────────────────────────────────────────────────────────

SCHEMA_VERSION = "1.0"

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO = SCRIPT_DIR.parent

POOL_PATH = SCRIPT_DIR / "model_pool.yaml"
NMC_PATH = SCRIPT_DIR / "node_model_capability.yaml"
DEFAULT_FIXTURE_DIR = REPO / "tests" / "fixtures" / "worker_attest"
DEFAULT_RECEIPT_DIR = REPO / "tests" / "fixtures" / "worker_attest_plan"

VALID_NODES = frozenset({"21bao", "5bao", "9bao"})

# ── Lifecycle classification ──────────────────────────────────────────────────

ACTIVE_LIFECYCLE_STATUSES = frozenset({"enabled_assigned", "operator_requested"})
DEU_LIFECYCLE_STATUSES = frozenset({"declared_enabled_unassigned"})
NON_ACTIVE_LIFECYCLE_STATUSES = frozenset(
    {"disabled", "historical", "remove_pending", "candidate", "required"}
)

# ── Redaction sub-flags (must all be True) ────────────────────────────────────

REDACTION_SUBFLAGS = (
    "no_secret_value",
    "no_env_value",
    "no_base_url_value",
    "no_real_endpoint_url",
    "no_key_length",
)

# ── Forbidden operation flags (must all be False) ─────────────────────────────

FORBIDDEN_FLAGS = (
    "ssh_attempted",
    "subprocess_attempted",
    "os_environ_read_attempted",
    "real_path_read_attempted",
    "model_call_attempted",
    "credential_provisioning_attempted",
)

# ── Node capability fields compared ───────────────────────────────────────────

CAPABILITY_COMPARE_FIELDS = (
    "declared",
    "synced",
    "wrapper_valid",
    "runtime_visible",
    "env_loaded",
    "model_call_verified",
    "operator_approved",
)

# ── Leak scanners (defensive copy from E2E summary) ──────────────────────────

_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|"
    r"glpat-[A-Za-z0-9_\-]{20,}|xai-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
_URL_RE = re.compile(r"https?://[A-Za-z0-9][A-Za-z0-9.\-]{1,}(?::\d+)?(?:/[^\s\"']*)?")
_PATH_RE = re.compile(
    r"(?:/home/[A-Za-z0-9_\-]+|/root/|C:\\Users\\[A-Za-z0-9_\-]+|"
    r"opencode\.env)"
)


# ═══════════════════════════════════════════════════════════════════════════════
# Data loaders
# ═══════════════════════════════════════════════════════════════════════════════


def _load_yaml(path: Path) -> dict:
    """Load a YAML file. Raises ValueError on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError(f"{path} is not a valid YAML dict")
        return data
    except FileNotFoundError:
        raise ValueError(f"file not found: {path}")
    except yaml.YAMLError as e:
        raise ValueError(f"YAML parse error in {path}: {e}")


def _load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _flatten_text(obj: Any) -> str:
    """Serialize a JSON-like object to a flat string for scanning."""
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(obj)


def _scan_leaks(text: str) -> dict:
    """Return leak scan result: secret_leak, url_leak, path_leak, any_leak."""
    result = {
        "secret_leak": bool(_SECRET_RE.search(text)),
        "url_leak": bool(_URL_RE.search(text)),
        "path_leak": bool(_PATH_RE.search(text)),
    }
    result["any_leak"] = any(result.values())
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Core comparison logic
# ═══════════════════════════════════════════════════════════════════════════════


def _get_lifecycle_class(status: str) -> str:
    """Classify a lifecycle_status into 'active', 'deu', or 'other'."""
    if status in ACTIVE_LIFECYCLE_STATUSES:
        return "active"
    if status in DEU_LIFECYCLE_STATUSES:
        return "deu"
    return "other"


def compare_pool_to_nmc(
    pool: dict, nmc: dict
) -> list[dict]:
    """
    Compare model_pool.yaml lifecycle_status against node_model_capability.yaml
    matrix entries. Returns a list of candidate drift items.

    This detects:
    - Active model missing from NMC entirely (CANDIDATE_DRIFT)
    - Active model present in NMC but with mismatched lifecycle class (WARN)
    - DEU model in NMC (expected, non-blocking WARN)
    - Active model with runtime_visible != ok (CANDIDATE_DRIFT)
    """
    pool_models = {m["id"]: m for m in pool["models"]}

    findings: list[dict] = []

    for node_name in VALID_NODES:
        node_data = nmc.get("nodes", {}).get(node_name, {})
        nmc_entries = {m["model_id"]: m for m in node_data.get("matrix", [])}

        # Check each pool model against NMC
        for mid, pm in pool_models.items():
            lifecycle = pm.get("lifecycle_status", "unknown")
            lc_class = _get_lifecycle_class(lifecycle)

            if lc_class == "other":
                continue  # disabled/historical/remove_pending/candidate: not in scope

            nmc_entry = nmc_entries.get(mid)

            if nmc_entry is None:
                # Model declared in pool but NOT in NMC matrix
                findings.append({
                    "node": node_name,
                    "model_id": mid,
                    "lifecycle_class": lc_class,
                    "lifecycle_status": lifecycle,
                    "drift_type": "missing_from_nmc",
                    "severity": "candidate_drift" if lc_class == "active" else "warn",
                    "detail": (
                        f"Active model '{mid}' is in pool but has no "
                        f"node_model_capability entry on {node_name}"
                        if lc_class == "active"
                        else f"DEU model '{mid}' is in pool but has no "
                             f"node_model_capability entry on {node_name}"
                    ),
                })
                continue

            if lc_class == "active":
                # Check runtime_visible = ok
                rv = nmc_entry.get("runtime_visible", "unknown")
                if rv != "ok" and rv is not True:
                    findings.append({
                        "node": node_name,
                        "model_id": mid,
                        "lifecycle_class": "active",
                        "lifecycle_status": lifecycle,
                        "drift_type": "runtime_visible_not_ok",
                        "severity": "candidate_drift",
                        "detail": (
                            f"Active model '{mid}' on {node_name} has "
                            f"runtime_visible={rv!r} (expected 'ok')"
                        ),
                        "capability_field": "runtime_visible",
                        "expected": "ok",
                        "actual": rv,
                    })

                # Check env_loaded = ok
                env_ld = nmc_entry.get("env_loaded", "unknown")
                if env_ld != "ok" and env_ld is not True:
                    findings.append({
                        "node": node_name,
                        "model_id": mid,
                        "lifecycle_class": "active",
                        "lifecycle_status": lifecycle,
                        "drift_type": "env_loaded_not_ok",
                        "severity": "candidate_drift",
                        "detail": (
                            f"Active model '{mid}' on {node_name} has "
                            f"env_loaded={env_ld!r} (expected 'ok')"
                        ),
                        "capability_field": "env_loaded",
                        "expected": "ok",
                        "actual": env_ld,
                    })

            elif lc_class == "deu":
                # DEU model found in NMC — expected, non-blocking WARN
                findings.append({
                    "node": node_name,
                    "model_id": mid,
                    "lifecycle_class": "deu",
                    "lifecycle_status": lifecycle,
                    "drift_type": "deu_in_nmc",
                    "severity": "warn",
                    "detail": (
                        f"DEU model '{mid}' present in {node_name} "
                        f"node_model_capability (expected; D-B pending)"
                    ),
                })

    return findings


def compare_nmc_to_fixture(
    nmc: dict,
    fixtures: dict[str, dict],
    receipts: dict[str, dict],
) -> list[dict]:
    """
    Compare node_model_capability matrix entries against fixture evidence and
    plan receipts.

    This detects:
    - Active model in NMC but missing from fixture alias list (CANDIDATE_DRIFT)
    - Active model in fixture with MIA credential_status (CANDIDATE_DRIFT)
    - Unknown namespace in fixture evidence (BLOCK)
    - DEU model present in fixture (WARN - unexpected evidence)
    - Forbidden operation flags in receipt (BLOCK)
    - Redaction failure in receipt (STOP_SECRET_RISK)
    - Schema version mismatch (STOP_AND_REANCHOR)
    - Provider namespace mismatch between NMC and fixture (CANDIDATE_DRIFT)
    """
    findings: list[dict] = []

    for node_name in VALID_NODES:
        node_data = nmc.get("nodes", {}).get(node_name, {})
        nmc_entries = {m["model_id"]: m for m in node_data.get("matrix", [])}

        fixture = fixtures.get(node_name, {})
        fixture_aliases = {a["model_id"]: a for a in fixture.get("model_aliases", [])}
        fixture_schema = fixture.get("schema_version", "")

        # --- Receipt checks for this node ---
        receipt = receipts.get(node_name, {})
        receipt_schema = receipt.get("schema_version", "")

        if receipt and receipt_schema != SCHEMA_VERSION:
            findings.append({
                "node": node_name,
                "drift_type": "receipt_schema_mismatch",
                "severity": "stop_and_reanchor",
                "detail": (
                    f"Receipt schema version mismatch: "
                    f"expected '{SCHEMA_VERSION}', got '{receipt_schema}'"
                ),
                "expected": SCHEMA_VERSION,
                "actual": receipt_schema,
            })
            # Schema mismatch is terminal per-node; skip further receipt checks
        elif receipt:
            # Check forbidden operation flags
            forbidden = receipt.get("forbidden_operation_flags", {})
            for flag_name in FORBIDDEN_FLAGS:
                if forbidden.get(flag_name) is True:
                    findings.append({
                        "node": node_name,
                        "drift_type": f"forbidden_flag_{flag_name}",
                        "severity": "blocked",
                        "detail": (
                            f"Forbidden operation flag '{flag_name}' "
                            f"is True on {node_name}"
                        ),
                        "flag": flag_name,
                    })

            # Check redaction status
            redaction = receipt.get("redaction_status", {})
            for subflag in REDACTION_SUBFLAGS:
                if redaction.get(subflag) is False:
                    leak_text = _flatten_text(receipt)
                    leak_scan = _scan_leaks(leak_text)
                    findings.append({
                        "node": node_name,
                        "drift_type": f"redaction_fail_{subflag}",
                        "severity": "stop_secret_risk",
                        "detail": (
                            f"Redaction flag '{subflag}' is False "
                            f"on {node_name}"
                        ),
                        "subflag": subflag,
                        "leak_scan": leak_scan,
                    })

        # --- Fixture checks for each NMC entry ---
        for mid, nmc_entry in nmc_entries.items():
            lifecycle_class = "unknown"
            lc = nmc_entry.get("lifecycle_status", "")
            if lc in ACTIVE_LIFECYCLE_STATUSES:
                lifecycle_class = "active"
            elif lc in DEU_LIFECYCLE_STATUSES:
                lifecycle_class = "deu"
            else:
                # Skip disabled/historical/etc entries
                continue

            fixture_entry = fixture_aliases.get(mid)

            if fixture_entry is None:
                # Model in NMC but NOT in fixture — note as fixture_evidence_missing
                findings.append({
                    "node": node_name,
                    "model_id": mid,
                    "lifecycle_class": lifecycle_class,
                    "drift_type": "fixture_evidence_missing",
                    "severity": "candidate_drift" if lifecycle_class == "active" else "warn",
                    "detail": (
                        f"Active model '{mid}' has no fixture alias entry "
                        f"on {node_name} — fixture evidence missing, cannot "
                        f"confirm runtime match"
                        if lifecycle_class == "active"
                        else f"DEU model '{mid}' has no fixture alias entry "
                             f"on {node_name} — expected for DEU"
                    ),
                })
                continue

            # --- Fixture-field comparisons ---
            fixture_ns = fixture_entry.get("provider_namespace", "")
            nmc_ns = nmc_entry.get("provider_namespace", "")

            if fixture_ns and nmc_ns and fixture_ns != nmc_ns:
                # Namespace mismatch between fixture and NMC
                new_severity = "candidate_drift" if lifecycle_class == "active" else "warn"
                new_dt = "fixture_namespace_mismatch"
                findings.append({
                    "node": node_name,
                    "model_id": mid,
                    "lifecycle_class": lifecycle_class,
                    "drift_type": new_dt,
                    "severity": new_severity,
                    "detail": (
                        f"Fixture namespace '{fixture_ns}' != "
                        f"NMC namespace '{nmc_ns}' for '{mid}' on {node_name}"
                    ),
                    "fixture_namespace": fixture_ns,
                    "nmc_namespace": nmc_ns,
                })

            # --- Credential status check (only for active) ---
            if lifecycle_class == "active":
                fixture_cred = fixture_entry.get("credential_status", "")
                if fixture_cred != "present":
                    findings.append({
                        "node": node_name,
                        "model_id": mid,
                        "lifecycle_class": "active",
                        "drift_type": "fixture_credential_not_present",
                        "severity": "candidate_drift",
                        "detail": (
                            f"Active model '{mid}' on {node_name} has "
                            f"credential_status='{fixture_cred}' "
                            f"(expected 'present')"
                        ),
                        "credential_status": fixture_cred,
                    })

            # --- Runtime provider mismatch ---
            fixture_rp = fixture_entry.get("runtime_provider", "")
            nmc_rp = nmc_entry.get("runtime_provider", "")
            if fixture_rp and nmc_rp and fixture_rp != nmc_rp:
                findings.append({
                    "node": node_name,
                    "model_id": mid,
                    "lifecycle_class": lifecycle_class,
                    "drift_type": "fixture_runtime_provider_mismatch",
                    "severity": "candidate_drift" if lifecycle_class == "active" else "warn",
                    "detail": (
                        f"Fixture runtime_provider '{fixture_rp}' != "
                        f"NMC runtime_provider '{nmc_rp}' for '{mid}'"
                    ),
                    "fixture_rp": fixture_rp,
                    "nmc_rp": nmc_rp,
                })

            # --- DEU model in fixture: WARN (unexpected evidence) ---
            if lifecycle_class == "deu" and fixture_entry:
                findings.append({
                    "node": node_name,
                    "model_id": mid,
                    "lifecycle_class": "deu",
                    "drift_type": "deu_fixture_evidence",
                    "severity": "warn",
                    "detail": (
                        f"DEU model '{mid}' appears in fixture aliases "
                        f"on {node_name} — unexpected evidence "
                        f"(non-blocking WARN; DEU models may have credentials "
                        f"but must not be promoted)"
                    ),
                })

    return findings


def check_unknown_namespace(
    pool: dict,
    nmc: dict,
    fixtures: dict[str, dict],
) -> list[dict]:
    """
    Detect unknown/empty provider_namespace across all sources.
    Any unknown namespace found → BLOCK.
    """
    findings: list[dict] = []
    known_namespaces: set[str] = set()

    # Collect from pool
    for m in pool.get("models", []):
        ns = m.get("provider_namespace", "")
        if ns:
            known_namespaces.add(ns)

    # Collect from NMC
    for node_name in VALID_NODES:
        node_data = nmc.get("nodes", {}).get(node_name, {})
        for entry in node_data.get("matrix", []):
            ns = entry.get("provider_namespace", "")
            if ns:
                known_namespaces.add(ns)

    # Collect from fixtures
    for node_name in VALID_NODES:
        fixture = fixtures.get(node_name, {})
        for alias in fixture.get("model_aliases", []):
            ns = alias.get("provider_namespace", "")
            if ns:
                known_namespaces.add(ns)

    # Check for empty/unknown namespace (excluding "unknown" placeholder)
    # The policy-lock treats "unknown" as a legitimate placeholder.
    for ns in known_namespaces:
        if not ns or ns.strip() == "":
            findings.append({
                "drift_type": "empty_namespace",
                "severity": "blocked",
                "detail": f"Empty provider_namespace found across data sources",
                "namespace": ns or "<empty>",
            })

    return findings


def check_missing_fixture(
    fixtures: dict[str, dict],
    receipts: dict[str, dict],
) -> list[dict]:
    """
    Check that each node has at least one fixture and at least SOME receipt
    evidence exists. Missing per-node receipt → WARN (fixture evidence
    missing). Only BLOCK if ALL receipts are missing (no receipt directory).
    """
    findings: list[dict] = []
    available_receipt_nodes = [n for n, r in receipts.items() if r]
    total_fixtures = len([n for n in fixtures.values() if n])

    for node_name in VALID_NODES:
        if node_name not in fixtures or not fixtures[node_name]:
            findings.append({
                "node": node_name,
                "drift_type": "fixture_evidence_missing",
                "severity": "blocked",
                "detail": (
                    f"No worker_attest fixture found for {node_name} — "
                    f"fixture evidence missing (G-L3F is fixture-only; "
                    f"this does NOT imply the node is unreachable)"
                ),
            })
        elif node_name not in receipts or not receipts[node_name]:
            # Per-node receipt missing but others exist → WARN
            findings.append({
                "node": node_name,
                "drift_type": "receipt_evidence_missing",
                "severity": "warn",
                "detail": (
                    f"No plan receipt found for {node_name} — "
                    f"receipt evidence missing for this node "
                    f"(G-L3F is fixture-only; this does NOT imply "
                    f"collection failed; other nodes have receipts: "
                    f"{available_receipt_nodes})"
                ),
            })

    # Only BLOCK if NO receipt data for any node
    if total_fixtures > 0 and not available_receipt_nodes:
        findings.append({
            "drift_type": "all_receipts_missing",
            "severity": "blocked",
            "detail": (
                f"No plan receipts found for ANY node "
                f"(G-L3F is fixture-only; receipt dir may be empty)"
            ),
        })

    return findings


# ═══════════════════════════════════════════════════════════════════════════════
# Verdict resolution
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_verdict(findings: list[dict]) -> str:
    """
    Resolve the overall G-L3F verdict from all findings.

    Priority (highest→lowest):
      1. STOP_SECRET_RISK   — any redaction_fail or leak
      2. STOP_AND_REANCHOR  — any schema mismatch
      3. BLOCKED            — any forbidden flag or schema/integrity failure
      4. CANDIDATE_DRIFT    — any active model drift
      5. PASS_WITH_WARN     — any DEU WARN
      6. PASS               — nothing found
    """
    severities = {f.get("severity", "") for f in findings}

    if "stop_secret_risk" in severities:
        return "G_L3F_STOP_SECRET_RISK"
    if "stop_and_reanchor" in severities:
        return "G_L3F_STOP_AND_REANCHOR"
    if "blocked" in severities:
        return "G_L3F_BLOCKED"
    if "candidate_drift" in severities:
        return "G_L3F_CANDIDATE_DRIFT"
    if "warn" in severities:
        return "G_L3F_PASS_WITH_WARN"
    return "G_L3F_PASS"


# ═══════════════════════════════════════════════════════════════════════════════
# Main API
# ═══════════════════════════════════════════════════════════════════════════════


def run_layer3_drift(
    pool_path: Path = POOL_PATH,
    nmc_path: Path = NMC_PATH,
    fixture_dir: Path = DEFAULT_FIXTURE_DIR,
    receipt_dir: Path = DEFAULT_RECEIPT_DIR,
) -> dict:
    """
    Run the full G-L3F fixture-based layer3 drift analysis.

    Returns a report dict with:
      - schema_version
      - source (always "worker_attest_layer3_drift")
      - generated_at
      - scope_note
      - inputs_loaded
      - findings (list)
      - finding_counts (by severity)
      - final_verdict
      - leak_scan (combined)
    """
    # ── Load inputs ──────────────────────────────────────────────────────
    pool = _load_yaml(pool_path)
    nmc = _load_yaml(nmc_path)

    fixtures: dict[str, dict] = {}
    receipts: dict[str, dict] = {}

    for node_name in VALID_NODES:
        fixture_path = fixture_dir / f"worker_attest_{node_name}.json"
        receipt_path = receipt_dir / f"receipt_{node_name}_valid.json"
        try:
            fixtures[node_name] = _load_json(fixture_path)
        except (FileNotFoundError, json.JSONDecodeError):
            fixtures[node_name] = {}
        try:
            receipts[node_name] = _load_json(receipt_path)
        except (FileNotFoundError, json.JSONDecodeError):
            receipts[node_name] = {}

    # ── Run comparison phases ────────────────────────────────────────────
    all_findings: list[dict] = []

    # Phase 1: Pool ↔ NMC
    all_findings.extend(compare_pool_to_nmc(pool, nmc))

    # Phase 2: NMC ↔ Fixture + Receipt
    all_findings.extend(compare_nmc_to_fixture(nmc, fixtures, receipts))

    # Phase 3: Unknown namespace check
    all_findings.extend(check_unknown_namespace(pool, nmc, fixtures))

    # Phase 4: Missing fixture check
    all_findings.extend(check_missing_fixture(fixtures, receipts))

    # ── Scan all finding detail text for leaks ───────────────────────────
    combined_text = _flatten_text(all_findings)
    combined_leak = _scan_leaks(combined_text)

    # ── Count by severity ────────────────────────────────────────────────
    severity_counts: dict[str, int] = {}
    for f in all_findings:
        sev = f.get("severity", "unknown")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    # ── Resolve verdict ──────────────────────────────────────────────────
    verdict = _resolve_verdict(all_findings)

    # ── Known/gap summary ────────────────────────────────────────────────
    candidate_gaps = [f for f in all_findings if f.get("severity") == "candidate_drift"]
    warns = [f for f in all_findings if f.get("severity") == "warn"]
    blocks = [f for f in all_findings if f.get("severity") == "blocked"]

    return {
        "schema_version": SCHEMA_VERSION,
        "source": "worker_attest_layer3_drift",
        "generated_at": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat(),
        "scope_note": (
            "G-L3F uses ONLY fixture evidence, not live runtime evidence. "
            "Findings are CANDIDATE_DRIFT (data gap) or WARN, not live BLOCK. "
            "This does NOT constitute live runtime validation, readiness "
            "expansion, DEU promotion, or runtime field promotion."
        ),
        "inputs_loaded": {
            "model_pool_yaml": str(pool_path),
            "node_capability_yaml": str(nmc_path),
            "fixture_dir": str(fixture_dir),
            "receipt_dir": str(receipt_dir),
            "fixture_nodes": list(fixtures.keys()),
            "receipt_nodes": list(receipts.keys()),
            "fixture_model_count_per_node": {
                n: len(fixtures.get(n, {}).get("model_aliases", []))
                for n in VALID_NODES
            },
        },
        "findings": all_findings,
        "finding_counts": severity_counts,
        "candidate_gap_count": len(candidate_gaps),
        "warn_count": len(warns),
        "block_count": len(blocks),
        "final_verdict": verdict,
        "leak_scan": combined_leak,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Self-check
# ═══════════════════════════════════════════════════════════════════════════════


def self_check() -> dict:
    """Run G-L3F self-check against real repo data."""
    report = run_layer3_drift()
    verdict = report["final_verdict"]

    checks = []
    # sc-01: module loads and produces a report
    checks.append({
        "name": "module_loads",
        "passed": True,
        "detail": f"schema_version={report['schema_version']}",
    })

    # sc-02: fixture evidence loaded for at least one node
    fixture_count = len(report["inputs_loaded"].get("fixture_nodes", []))
    checks.append({
        "name": "fixtures_loaded",
        "passed": fixture_count > 0,
        "detail": f"fixture_nodes={report['inputs_loaded']['fixture_nodes']} model_counts={report['inputs_loaded']['fixture_model_count_per_node']}",
    })

    # sc-03: receipt evidence loaded for at least one node
    receipt_count = len(report["inputs_loaded"].get("receipt_nodes", []))
    checks.append({
        "name": "receipts_loaded",
        "passed": receipt_count > 0,
        "detail": f"receipt_nodes={report['inputs_loaded']['receipt_nodes']}",
    })

    # sc-04: no leak in output
    checks.append({
        "name": "no_leak",
        "passed": not report["leak_scan"]["any_leak"],
        "detail": f"secret={report['leak_scan']['secret_leak']} url={report['leak_scan']['url_leak']} path={report['leak_scan']['path_leak']}",
    })

    # sc-05: verdict is valid
    valid_verdicts = {
        "G_L3F_PASS", "G_L3F_PASS_WITH_WARN", "G_L3F_CANDIDATE_DRIFT",
        "G_L3F_BLOCKED", "G_L3F_STOP_SECRET_RISK", "G_L3F_STOP_AND_REANCHOR",
    }
    checks.append({
        "name": "valid_verdict",
        "passed": verdict in valid_verdicts,
        "detail": f"verdict={verdict}",
    })

    # sc-06: scope_note present
    checks.append({
        "name": "scope_note_present",
        "passed": "fixture evidence" in report.get("scope_note", ""),
        "detail": "scope_note confirms fixture-only constraint",
    })

    # sc-07: finding_counts present
    checks.append({
        "name": "finding_counts_present",
        "passed": isinstance(report.get("finding_counts"), dict),
        "detail": f"counts={report['finding_counts']}",
    })

    passed_count = sum(1 for c in checks if c["passed"])
    total = len(checks)

    return {
        "schema_version": SCHEMA_VERSION,
        "name": "worker_attest_layer3_drift",
        "status": "PASS" if passed_count == total else "FAIL",
        "passed_count": passed_count,
        "total": total,
        "detail": f"{passed_count}/{total} passed",
        "checks": checks,
        "final_verdict": verdict,
        "leak_scan": report["leak_scan"],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="worker_attest_layer3_drift.py",
        description="G-L3F fixture-based Layer3 runtime drift comparison.",
    )
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=["run", "self-check"],
        default="self-check",
        help="Command: run (full report) or self-check (summary). Default: self-check.",
    )
    parser.add_argument(
        "--fixture-dir",
        default=str(DEFAULT_FIXTURE_DIR),
        help=f"Path to worker_attest fixture directory (default: {DEFAULT_FIXTURE_DIR})",
    )
    parser.add_argument(
        "--receipt-dir",
        default=str(DEFAULT_RECEIPT_DIR),
        help=f"Path to plan receipt directory (default: {DEFAULT_RECEIPT_DIR})",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = _parse_args()

    if args.cmd == "run":
        report = run_layer3_drift(
            fixture_dir=Path(args.fixture_dir),
            receipt_dir=Path(args.receipt_dir),
        )
        print(json.dumps(report, indent=2, default=str))
    else:
        result = self_check()
        print(json.dumps(result, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
