#!/usr/bin/env python3
"""
VibeDev Model Pool Drift Detector — Layer 1 (pool ↔ matrix).

Local-only, read-only. Compares central model_pool.yaml vs node_model_capability.yaml
and detects drift categories. Does NOT touch remote worker configs.

=== Design (Phase 2 §2 Layer 1) ===
- pool ↔ matrix comparison
- missing matrix entry → BLOCK
- extra matrix entry (not in pool) → BLOCK
- allowed_nodes mismatch (pool allows but matrix missing) → BLOCK
- lifecycle_status vs matrix inclusion conflict → BLOCK
- manifest SHA mismatch → BLOCK (fail-closed) or WARN
- declared_enabled_unassigned is NOT drift (operator D-B decision pending)
- remove_pending / disabled / historical / candidate NOT in active matrix → PASS

=== No side-effects ===
No SSH, no subprocess, no HTTP, no file writes, no env var read (only yaml/json load).
"""

import hashlib
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

import yaml

SCRIPT_DIR = Path(__file__).parent.resolve()
POOL_PATH = SCRIPT_DIR / "model_pool.yaml"
NMC_PATH = SCRIPT_DIR / "node_model_capability.yaml"
MANIFEST_PATH = SCRIPT_DIR / "model_pool_manifest.json"

VALID_NODES = ("21bao", "5bao", "9bao")

# Legacy alias from baseline01 architecture taxonomy:
# pre-baseline02 pool used "win" for the Windows local-exec node;
# baseline02 renamed to "21bao". Matrix builder maps win -> 21bao.
# Detector must accept win as alias to maintain backward compat.
LEGACY_NODE_ALIASES = {"win": "21bao"}

def _normalize_node(node: str) -> str | None:
    """Normalize node identifier, resolving legacy aliases."""
    if node in VALID_NODES:
        return node
    if node in LEGACY_NODE_ALIASES:
        return LEGACY_NODE_ALIASES[node]
    return None

# Lifecycle_statuses that should NEVER appear in node_model_capability matrix
# declared_enabled_unassigned → WARN only (D-B decision pending; may be transient)
NON_ACTIVE_LIFECYCLE_STATUSES = frozenset({
    "disabled", "historical", "remove_pending", "candidate", "required",
})

WARN_LIFECYCLE_STATUSES = frozenset({
    "declared_enabled_unassigned",
})


def _load_yaml(path: Path) -> dict:
    """Load YAML file. Raises ValueError on failure."""
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
    """Load JSON file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise ValueError(f"file not found: {path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON parse error in {path}: {e}")


def _sha256_of_file(path: Path) -> str:
    """Compute SHA256 of file contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_drift_layer1(
    pool: dict | None = None,
    nmc: dict | None = None,
    manifest: dict | None = None,
) -> dict:
    """Detect drift between model_pool.yaml and node_model_capability.yaml.

    Returns a drift report dict. Pure function — no file I/O when pool/nmc/manifest
    are passed in; otherwise reads from default paths.

    drift_categories:
      - missing_matrix_entry: pool enabled model not in matrix
      - extra_matrix_entry: matrix contains model not in pool
      - allowed_nodes_mismatch: pool allowed_nodes != matrix node inclusion
      - lifecycle_in_matrix: disabled/remove_pending/etc in active matrix
      - manifest_mismatch: pool file SHA != manifest SHA
      - schema_mismatch: schema_version mismatch between pool/manifest
    """
    # Load data
    if pool is None:
        pool = _load_yaml(POOL_PATH)
    if nmc is None:
        nmc = _load_yaml(NMC_PATH)
    if manifest is None:
        try:
            manifest = _load_json(MANIFEST_PATH)
        except ValueError:
            manifest = {}

    drift_categories = []
    warnings_list = []
    details = []
    details_warn = []

    # --- Build pool index ---
    pool_models = {m["id"]: m for m in pool.get("models", [])}

    # --- Build matrix index ---
    matrix_by_node = {}
    for node, n in nmc.get("nodes", {}).items():
        matrix_by_node[node] = {e["model_id"]: e for e in n.get("matrix", [])}

    skipped_ids = set((nmc.get("skipped_models") or {}).get("ids") or [])

    # --- Check missing matrix entries ---
    # For each pool model that should be in matrix (enabled + has allowed_nodes),
    # verify matrix contains it for those nodes.
    for mid, m in pool_models.items():
        allowed = m.get("allowed_nodes") or []
        ls = m.get("lifecycle_status")
        if not m.get("enabled"):
            # Disabled models should NOT be in active matrix
            continue
        # Non-active lifecycle status models should NOT be in matrix
        if ls in NON_ACTIVE_LIFECYCLE_STATUSES:
            continue
        # declared_enabled_unassigned models not in any matrix by design
        if ls == "declared_enabled_unassigned" or not allowed:
            # Optional: verify not in matrix (it's a "should not be" check)
            for node in VALID_NODES:
                if mid in matrix_by_node.get(node, {}):
                    # WARN only — D-B decision pending
                    warnings_list.append("lifecycle_in_matrix_warn")
                    details_warn.append({
                        "category": "lifecycle_in_matrix_warn",
                        "severity": "WARN",
                        "model_id": mid,
                        "node": node,
                        "lifecycle_status": ls,
                        "detail": f"declared_enabled_unassigned model '{mid}' found in matrix[{node}] (D-B decision pending)"
                    })
            continue
        # enabled_assigned / operator_requested: must be in matrix for each allowed node
        for node in allowed:
            norm_node = _normalize_node(node)
            if norm_node is None:
                drift_categories.append("allowed_nodes_mismatch")
                details.append({
                    "category": "allowed_nodes_mismatch",
                    "model_id": mid,
                    "node": node,
                    "detail": f"allowed_nodes contains invalid node '{node}'"
                })
                continue
            if mid not in matrix_by_node.get(norm_node, {}):
                drift_categories.append("missing_matrix_entry")
                details.append({
                    "category": "missing_matrix_entry",
                    "model_id": mid,
                    "node": norm_node,
                    "detail": f"pool enabled model '{mid}' missing from matrix[{norm_node}]"
                })

    # --- Check extra matrix entries (matrix contains model not in pool) ---
    for node, entries in matrix_by_node.items():
        for mid in entries:
            if mid not in pool_models:
                drift_categories.append("extra_matrix_entry")
                details.append({
                    "category": "extra_matrix_entry",
                    "model_id": mid,
                    "node": node,
                    "detail": f"matrix[{node}] contains unknown model_id '{mid}' (not in pool)"
                })

    # --- Check allowed_nodes coverage (matrix has model not in pool allowed_nodes) ---
    for node, entries in matrix_by_node.items():
        for mid, entry in entries.items():
            if mid not in pool_models:
                continue
            pool_model = pool_models[mid]
            ls = pool_model.get("lifecycle_status")
            # declared_enabled_unassigned is handled by lifecycle_in_matrix_warn
            # (the matrix inclusion is the drift; allowed_nodes=[] is by design)
            if ls == "declared_enabled_unassigned":
                continue
            pool_allowed_raw = pool_model.get("allowed_nodes") or []
            # Normalize pool's allowed_nodes (handle legacy 'win')
            pool_allowed_normalized = set()
            for n in pool_allowed_raw:
                norm = _normalize_node(n)
                if norm:
                    pool_allowed_normalized.add(norm)
            if node not in pool_allowed_normalized:
                drift_categories.append("allowed_nodes_mismatch")
                details.append({
                    "category": "allowed_nodes_mismatch",
                    "model_id": mid,
                    "node": node,
                    "detail": f"matrix[{node}] has '{mid}' but pool allowed_nodes={pool_allowed_raw}"
                })

    # --- Check matrix inclusion of non-active lifecycle_status models ---
    for node, entries in matrix_by_node.items():
        for mid in entries:
            if mid not in pool_models:
                continue
            ls = pool_models[mid].get("lifecycle_status")
            if ls in NON_ACTIVE_LIFECYCLE_STATUSES:
                drift_categories.append("lifecycle_in_matrix")
                details.append({
                    "category": "lifecycle_in_matrix",
                    "model_id": mid,
                    "node": node,
                    "lifecycle_status": ls,
                    "detail": f"matrix[{node}] contains '{mid}' with non-active lifecycle_status='{ls}'"
                })

    # --- Check skipped_models vs pool ---
    for sid in skipped_ids:
        if sid in pool_models:
            pool_entry = pool_models[sid]
            if pool_entry.get("enabled"):
                drift_categories.append("skipped_should_not_be_active")
                details.append({
                    "category": "skipped_should_not_be_active",
                    "model_id": sid,
                    "detail": f"skipped_models entry '{sid}' is enabled in pool"
                })

    # --- Manifest check (compute SHA of pool file if available) ---
    manifest_status = "ok"
    manifest_drift = None
    try:
        pool_sha = _sha256_of_file(POOL_PATH)
        declared_sha = manifest.get("files", {}).get("model_pool.yaml", {}).get("sha256", "")
        if declared_sha and declared_sha != pool_sha:
            drift_categories.append("manifest_mismatch")
            details.append({
                "category": "manifest_mismatch",
                "model_id": None,
                "detail": f"manifest sha={declared_sha[:16]}... != actual sha={pool_sha[:16]}..."
            })
            manifest_status = "mismatch"
    except Exception as e:
        manifest_status = "unverifiable"
        manifest_drift = str(e)

    # --- Schema version check ---
    pool_schema = str(pool.get("schema_version", ""))
    manifest_schema = str(manifest.get("schema_version", ""))
    if manifest_schema and pool_schema and pool_schema != manifest_schema:
        drift_categories.append("schema_mismatch")
        details.append({
            "category": "schema_mismatch",
            "model_id": None,
            "detail": f"pool schema_version={pool_schema} != manifest schema_version={manifest_schema}"
        })

    # --- Build report ---
    drift_detected = len(drift_categories) > 0
    drift_count = len(drift_categories)
    warn_count = len(warnings_list)

    # Dedupe categories for summary
    unique_categories = sorted(set(drift_categories))
    unique_warnings = sorted(set(warnings_list))

    report = {
        "drift_detected": drift_detected,
        "drift_count": drift_count,
        "warn_count": warn_count,
        "drift_categories": unique_categories,
        "warn_categories": unique_warnings,
        "details": details,
        "warnings": details_warn,
        "pool_schema_version": pool_schema,
        "nmc_schema_version": str(nmc.get("schema_version", "")),
        "manifest_status": manifest_status,
        "manifest_drift": manifest_drift,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "checked_scope": {
            "pool_path": str(POOL_PATH),
            "nmc_path": str(NMC_PATH),
            "manifest_path": str(MANIFEST_PATH),
            "nodes": list(VALID_NODES),
        },
        "layer": 1,
        "blocked_reason": None if not drift_detected else (
            f"layer 1 drift detected: {drift_count} issue(s) in categories {unique_categories}"
        ),
    }
    return report


def self_check() -> dict:
    """Verify drift detector is importable and basic logic works."""
    checks = []
    try:
        report = detect_drift_layer1()
        checks.append({
            "name": "detect_no_throw",
            "passed": isinstance(report, dict) and "drift_count" in report,
            "detail": f"drift_count={report.get('drift_count')} categories={report.get('drift_categories')}",
        })
    except Exception as e:
        checks.append({"name": "detect_no_throw", "passed": False, "detail": str(e)})

    # No secret leak check
    try:
        report = detect_drift_layer1()
        output = json.dumps(report)
        # Should NEVER contain key_env values, base_url values, or sk- patterns
        leaked = any(p in output for p in ["sk-", "=***", "http://", "https://"])
        checks.append({
            "name": "no_secret_leak",
            "passed": not leaked,
            "detail": "ok" if not leaked else "SECRET LEAK DETECTED",
        })
    except Exception as e:
        checks.append({"name": "no_secret_leak", "passed": False, "detail": str(e)})

    # Local-only check (verify no SSH/subprocess imports in actual module body)
    try:
        # Read the module AST, not the source text, to avoid false positives
        # from detection patterns embedded in strings/comments.
        import ast
        tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
        forbidden_imports = {
            "subprocess", "paramiko", "fabric", "requests", "urllib",
            "urllib.request", "socket", "http.client",
        }
        forbidden_calls = {"subprocess.run", "subprocess.Popen", "subprocess.call"}
        forbidden_attrs = {"SSHClient", "connect"}
        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in forbidden_imports:
                        violations.append(f"import {alias.name}")
            if isinstance(node, ast.ImportFrom):
                mod = (node.module or "").split(".")[0]
                if mod in forbidden_imports:
                    violations.append(f"from {node.module} import ...")
            if isinstance(node, ast.Call):
                func = node.func
                # Check attribute calls (e.g., subprocess.run)
                if isinstance(func, ast.Attribute):
                    full = ""
                    if isinstance(func.value, ast.Name):
                        full = f"{func.value.id}.{func.attr}"
                    if full in forbidden_calls or func.attr in forbidden_attrs:
                        violations.append(f"call {full}")
        local_only = len(violations) == 0
        checks.append({
            "name": "local_only",
            "passed": local_only,
            "detail": "ok" if local_only else f"forbidden: {violations}",
        })
    except Exception as e:
        checks.append({"name": "local_only", "passed": False, "detail": str(e)})

    all_pass = all(c["passed"] for c in checks)
    return {
        "status": "PASS" if all_pass else "FAIL",
        "version": "1.0.0",
        "layer": 1,
        "checks": checks,
        "detail": f"{sum(1 for c in checks if c['passed'])}/{len(checks)} passed",
    }


# ── Layer 2: worker_attest fixture adapter ──────────────────────────────────

FIXTURES_DIR = SCRIPT_DIR.parent / "tests" / "fixtures" / "worker_attest"
LAYER2_BLOCK = frozenset({
    "worker_attest_missing", "worker_node_mismatch", "worker_schema_mismatch",
    "worker_provider_namespace_mismatch", "worker_lifecycle_status_mismatch",
})
LAYER2_WARN = frozenset({
    "worker_alias_missing", "worker_extra_alias", "worker_credential_status_mismatch",
    "worker_endpoint_ref_mismatch", "worker_attestation_invalid",
})


def _load_fixture(fixture_path: Path) -> dict:
    if not fixture_path.exists():
        raise ValueError(f"Fixture not found: {fixture_path}")
    try:
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Fixture JSON parse error: {e}")
    if "node" not in data:
        raise ValueError("Fixture missing 'node' field")
    if "model_aliases" not in data:
        raise ValueError("Fixture missing 'model_aliases' field")
    return data


def detect_drift_layer2(
    fixture_path: Path | None = None,
    node: str | None = None,
    pool: dict | None = None,
    nmc: dict | None = None,
    attestation: dict | None = None,
) -> dict:
    """Local-only drift Layer 2: compare worker_attest fixture vs pool vs matrix.

    Accepts EITHER a fixture_path (legacy file-based) OR an attestation dict
    (from collector completed receipt). When attestation is provided,
    fixture_path and node are ignored for loading.

    No SSH, no real worker access, no env read. Pure local comparison.
    """
    # ── Get attestation data ──
    if attestation is not None:
        fixture = attestation
        used_fixture_path = None
    elif fixture_path is not None:
        used_fixture_path = fixture_path
        try:
            fixture = _load_fixture(fixture_path)
        except ValueError as e:
            return _layer2_err(str(e))
    elif node is not None:
        used_fixture_path = FIXTURES_DIR / f"worker_attest_{node}.json"
        try:
            fixture = _load_fixture(used_fixture_path)
        except ValueError as e:
            return _layer2_err(str(e))
    else:
        return _layer2_err("No fixture path, node, or attestation specified")

    # ── Validate fixture/attestation schema ──
    try:
        from worker_attest import validate_worker_attestation
        vr = validate_worker_attestation(fixture)
        if not vr["valid"]:
            return {
                "drift_detected": True, "drift_count": 1, "warn_count": 0,
                "drift_categories": ["worker_attestation_invalid"],
                "warn_categories": [],
                "details": [{"category": "worker_attestation_invalid", "severity": "BLOCK",
                             "detail": f"Fixture invalid: {'; '.join(vr['errors'][:3])}"}],
                "warnings": vr.get("warnings", []), "layer": 2,
                "node": fixture.get("node"), "fixture_path": str(used_fixture_path) if used_fixture_path else None,
                "model_count": {}, "blocked_reason": "worker_attestation_invalid",
            }
    except ImportError:
        return _layer2_err("worker_attest module not available for validation")

    # ── Load pool and NMC ──
    if pool is None:
        try:
            pool = _load_yaml(POOL_PATH)
        except ValueError as e:
            return _layer2_err(f"Cannot load pool: {e}")
    if nmc is None:
        try:
            nmc = _load_yaml(NMC_PATH)
        except ValueError as e:
            return _layer2_err(f"Cannot load NMC: {e}")

    node_name = fixture.get("node", "")
    pool_models = {m["id"]: m for m in pool.get("models", [])}
    matrix_by_node = {}
    for n, ndata in nmc.get("nodes", {}).items():
        matrix_by_node[n] = {e["model_id"]: e for e in ndata.get("matrix", [])}
    matrix = matrix_by_node.get(node_name, {})
    aliases = fixture.get("model_aliases", [])
    fixture_by_id = {a["model_id"]: a for a in aliases}

    drift_cats = []
    warn_cats = []
    details = []
    details_warn = []

    # ── Check node match ──
    if node_name not in matrix_by_node:
        drift_cats.append("worker_node_mismatch")
        details.append({"category": "worker_node_mismatch", "severity": "BLOCK",
                        "node": node_name,
                        "detail": f"Fixture node '{node_name}' not in NMC matrix"})

    # ── alias missing (matrix has model not in fixture) ──
    # Severity policy: per PR #297 fix, active models (enabled_assigned /
    # operator_requested) must BLOCK if missing from worker attestation, because
    # a missing alias means the worker hasn't attested a model the central pool
    # thinks it should have. declared_enabled_unassigned stays WARN (D-B
    # pending). Other lifecycle states (candidate/disabled/historical/
    # remove_pending/required) BLOCK as a generic safety net — the only carve-
    # out is DEU because the matrix currently reflects pre-existing baseline02
    # matrix builder behavior pending D-B.
    _ACTIVE = ("enabled_assigned", "operator_requested")
    _DEU = "declared_enabled_unassigned"
    for mid in matrix:
        if mid not in fixture_by_id:
            ls = pool_models.get(mid, {}).get("lifecycle_status", "")
            if ls == _DEU:
                # DEU stays WARN — pre-existing baseline02 matrix builder
                # behavior pending D-B operator decision.
                warn_cats.append("worker_alias_missing")
                details_warn.append({"category": "worker_alias_missing", "severity": "WARN",
                                     "model_id": mid, "node": node_name,
                                     "detail": f"Matrix has '{mid}' but fixture does not "
                                               f"(declared_enabled_unassigned, D-B pending)"})
            else:
                # active or other non-DEU lifecycle status: BLOCK.
                drift_cats.append("worker_alias_missing")
                details.append({"category": "worker_alias_missing", "severity": "BLOCK",
                                "model_id": mid, "node": node_name,
                                "detail": f"Matrix has '{mid}' ({ls}) but fixture does not"})

    # ── extra alias (fixture has model not in pool/matrix) ──
    for aid in fixture_by_id:
        if aid not in pool_models:
            warn_cats.append("worker_extra_alias")
            details_warn.append({"category": "worker_extra_alias", "severity": "WARN",
                                 "model_id": aid, "node": node_name,
                                 "detail": f"Fixture has '{aid}' but not in pool"})
        elif aid not in matrix:
            warn_cats.append("worker_extra_alias")
            details_warn.append({"category": "worker_extra_alias", "severity": "WARN",
                                 "model_id": aid, "node": node_name,
                                 "detail": f"Fixture has '{aid}' but not in matrix"})

    # ── field-by-field comparison ──
    for mid in fixture_by_id:
        fe = fixture_by_id[mid]
        if mid not in pool_models or mid not in matrix:
            continue
        pe = pool_models[mid]

        # provider_namespace
        f_ns = fe.get("provider_namespace", "")
        p_ns = pe.get("provider_namespace", "")
        if f_ns and p_ns and f_ns != p_ns:
            drift_cats.append("worker_provider_namespace_mismatch")
            details.append({"category": "worker_provider_namespace_mismatch",
                            "severity": "BLOCK", "model_id": mid, "node": node_name,
                            "detail": f"provider_namespace mismatch: fixture='{f_ns}' pool='{p_ns}'"})

        # lifecycle_status
        f_ls = fe.get("lifecycle_status", "")
        p_ls = pe.get("lifecycle_status", "")
        if f_ls and p_ls and f_ls != p_ls:
            if p_ls == "declared_enabled_unassigned":
                warn_cats.append("worker_lifecycle_status_mismatch")
                details_warn.append({"category": "worker_lifecycle_status_mismatch",
                                     "severity": "WARN", "model_id": mid, "node": node_name,
                                     "detail": f"lifecycle_status: fixture='{f_ls}' pool='{p_ls}' (DEU, fixture may be stale)"})
            else:
                drift_cats.append("worker_lifecycle_status_mismatch")
                details.append({"category": "worker_lifecycle_status_mismatch",
                                "severity": "BLOCK", "model_id": mid, "node": node_name,
                                "detail": f"lifecycle_status: fixture='{f_ls}' pool='{p_ls}'"})

        # credential_status
        # Severity policy per PR #297 fix:
        #   - active models (enabled_assigned / operator_requested) with a
        #     credential_status mismatch → BLOCK (runtime credential ref drift
        #     between central pool and worker attestation).
        #   - declared_enabled_unassigned → WARN (D-B pending).
        #   - other lifecycle states (candidate/disabled/historical/
        #     remove_pending/required) → BLOCK as safety net.
        f_cs = fe.get("credential_status", "")
        p_cs = pe.get("credential_status", "")
        if f_cs and p_cs and f_cs != p_cs:
            ls = pe.get("lifecycle_status", "")
            if ls == _DEU:
                warn_cats.append("worker_credential_status_mismatch")
                details_warn.append({"category": "worker_credential_status_mismatch",
                                     "severity": "WARN", "model_id": mid, "node": node_name,
                                     "detail": f"credential_status: fixture='{f_cs}' pool='{p_cs}' "
                                               f"(declared_enabled_unassigned, D-B pending)"})
            else:
                drift_cats.append("worker_credential_status_mismatch")
                details.append({"category": "worker_credential_status_mismatch",
                                "severity": "BLOCK", "model_id": mid, "node": node_name,
                                "detail": f"credential_status: fixture='{f_cs}' pool='{p_cs}' "
                                          f"({ls})"})

        # endpoint_ref
        # Severity policy mirrors credential_status (see above).
        f_er = fe.get("endpoint_ref", "")
        p_er = pe.get("endpoint_ref", "")
        if f_er and p_er and f_er != p_er:
            ls = pe.get("lifecycle_status", "")
            if ls == _DEU:
                warn_cats.append("worker_endpoint_ref_mismatch")
                details_warn.append({"category": "worker_endpoint_ref_mismatch",
                                     "severity": "WARN", "model_id": mid, "node": node_name,
                                     "detail": f"endpoint_ref: fixture='{f_er}' pool='{p_er}' "
                                               f"(declared_enabled_unassigned, D-B pending)"})
            else:
                drift_cats.append("worker_endpoint_ref_mismatch")
                details.append({"category": "worker_endpoint_ref_mismatch",
                                "severity": "BLOCK", "model_id": mid, "node": node_name,
                                "detail": f"endpoint_ref: fixture='{f_er}' pool='{p_er}' "
                                          f"({ls})"})

    drift_count = len(drift_cats)
    warn_count = len(warn_cats)
    return {
        "drift_detected": drift_count > 0,
        "drift_count": drift_count,
        "warn_count": warn_count,
        "drift_categories": sorted(set(drift_cats)),
        "warn_categories": sorted(set(warn_cats)),
        "details": details,
        "warnings": details_warn,
        "layer": 2,
        "node": node_name,
        "fixture_path": str(used_fixture_path) if used_fixture_path else None,
        "model_count": {"pool": len(pool_models), "matrix": len(matrix), "fixture": len(aliases)},
        "blocked_reason": None if drift_count == 0 else f"Layer 2 drift: {drift_count} BLOCK(s) in {sorted(set(drift_cats))}",
    }


def validate_collector_receipt(receipt: dict) -> dict:
    """Validate a collector receipt before using attestation for Layer2.

    Checks:
    - Receipt is a dict with required fields
    - collection_status is 'completed' (only completed receipts have attestation)
    - forbidden_operation_flags all False
    - redaction_status all True
    - attestation is present with model_aliases

    Returns: {'valid': True/False, 'errors': [...], 'blocked_reason': ...}
    """
    errors: list[str] = []

    if not isinstance(receipt, dict):
        return {"valid": False, "errors": ["receipt must be a dict"],
                "blocked_reason": "receipt_not_dict"}

    # collection_status must be 'completed' to have attestation
    cs = receipt.get("collection_status", "")
    if cs != "completed":
        errors.append(f"collection_status must be 'completed', got '{cs}'")

    # forbidden_operation_flags must all be False
    fof = receipt.get("forbidden_operation_flags", {})
    if not isinstance(fof, dict):
        errors.append("forbidden_operation_flags must be a dict")
    else:
        for k, v in fof.items():
            if v is True:
                errors.append(f"forbidden_operation_flags.{k} is True (forbidden operation detected)")

    # redaction_status must all be True
    rs = receipt.get("redacted_output", {})
    # Also check the receipt's own redaction_status if present
    rs_inner = receipt.get("receipt", {}).get("redaction_status", {})
    if isinstance(rs_inner, dict):
        for k, v in rs_inner.items():
            if v is False:
                errors.append(f"receipt.redaction_status.{k} is False")

    # attestation field must be present
    attestation = receipt.get("attestation")
    if attestation is None:
        errors.append("attestation field missing from collector output")
    elif not isinstance(attestation, dict):
        errors.append("attestation must be a dict")
    elif "model_aliases" not in attestation:
        errors.append("attestation missing model_aliases")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "blocked_reason": None if not errors else "collector_receipt_invalid",
    }


def detect_drift_layer2_from_receipt(
    receipt: dict,
    pool: dict | None = None,
    nmc: dict | None = None,
) -> dict:
    """Validate a collector receipt and run Layer 2 drift on its attestation.

    This wires the collector output (PR-4D) into the Layer 2 drift detection
    (PR-4B). Steps:
    1. Validate the receipt format and safety constraints
    2. Extract the attestation
    3. Run existing detect_drift_layer2 with the attestation

    No SSH, no real worker access, no env read. Pure local comparison.
    """
    # Step 1: Validate receipt
    vr = validate_collector_receipt(receipt)
    if not vr["valid"]:
        return {
            "drift_detected": True, "drift_count": 1, "warn_count": 0,
            "drift_categories": ["collector_receipt_invalid"],
            "warn_categories": [],
            "details": [{"category": "collector_receipt_invalid", "severity": "BLOCK",
                         "detail": "; ".join(vr["errors"][:3])}],
            "warnings": [], "layer": 2,
            "node": receipt.get("attestation", {}).get("node", None),
            "fixture_path": None,
            "model_count": {}, "blocked_reason": vr["blocked_reason"],
        }

    # Step 2: Extract attestation
    attestation = receipt["attestation"]

    # Step 3: Run Layer 2 comparison
    return detect_drift_layer2(
        attestation=attestation,
        pool=pool,
        nmc=nmc,
    )


def _layer2_err(msg: str) -> dict:
    return {"drift_detected": True, "drift_count": 1, "warn_count": 0,
            "drift_categories": ["worker_attest_missing"], "warn_categories": [],
            "details": [{"category": "worker_attest_missing", "severity": "BLOCK", "detail": msg}],
            "warnings": [], "layer": 2, "node": None, "fixture_path": None,
            "model_count": {}, "blocked_reason": f"worker_attest_missing: {msg}"}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "PASS" else 1)
    elif len(sys.argv) > 1 and sys.argv[1] in ("detect", "diff"):
        # Layer 1 only unless --layer2 specified
        if "--layer2" in sys.argv:
            fixture_path = None
            node = None
            receipt_path = None
            for i, a in enumerate(sys.argv):
                if a == "--fixture" and i + 1 < len(sys.argv):
                    fixture_path = Path(sys.argv[i + 1])
                elif a == "--node" and i + 1 < len(sys.argv):
                    node = sys.argv[i + 1]
                elif a == "--receipt" and i + 1 < len(sys.argv):
                    receipt_path = Path(sys.argv[i + 1])
            if receipt_path is not None:
                try:
                    receipt = _load_json(receipt_path)
                    report = detect_drift_layer2_from_receipt(receipt)
                except ValueError as e:
                    report = _layer2_err(str(e))
            else:
                report = detect_drift_layer2(fixture_path=fixture_path, node=node)
        else:
            report = detect_drift_layer1()
        print(json.dumps(report, indent=2))
        sys.exit(0 if not report.get("drift_detected", True) else 1)
    elif len(sys.argv) > 1 and sys.argv[1] in ("layer2",):
        fixture_path = None
        node = None
        receipt_path = None
        for i, a in enumerate(sys.argv):
            if a == "--fixture" and i + 1 < len(sys.argv):
                fixture_path = Path(sys.argv[i + 1])
            elif a == "--node" and i + 1 < len(sys.argv):
                node = sys.argv[i + 1]
            elif a == "--receipt" and i + 1 < len(sys.argv):
                receipt_path = Path(sys.argv[i + 1])
        if receipt_path is not None:
            try:
                receipt = _load_json(receipt_path)
                report = detect_drift_layer2_from_receipt(receipt)
            except ValueError as e:
                report = _layer2_err(str(e))
        else:
            report = detect_drift_layer2(fixture_path=fixture_path, node=node)
        print(json.dumps(report, indent=2))
        sys.exit(0 if not report.get("drift_detected", True) else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "drift":
        report = detect_drift_layer1()
        print(json.dumps(report, indent=2))
        sys.exit(0 if not report["drift_detected"] else 1)
    else:
        print("Usage:")
        print("  python model_pool_drift.py --self-check")
        print("  python model_pool_drift.py detect [--layer2 [--node NODE|--fixture PATH|--receipt PATH]]")
        print("  python model_pool_drift.py drift")
        print("  python model_pool_drift.py layer2 [--node NODE|--fixture PATH|--receipt PATH]")
        sys.exit(0)


if __name__ == "__main__":
    main()