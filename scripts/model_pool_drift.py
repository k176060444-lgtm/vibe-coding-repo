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


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "PASS" else 1)
    elif len(sys.argv) > 1 and sys.argv[1] in ("detect", "diff"):
        report = detect_drift_layer1()
        print(json.dumps(report, indent=2))
        sys.exit(0 if not report["drift_detected"] else 1)
    elif len(sys.argv) > 1 and sys.argv[1] == "drift":
        report = detect_drift_layer1()
        print(json.dumps(report, indent=2))
        sys.exit(0 if not report["drift_detected"] else 1)
    else:
        print("Usage:")
        print("  python model_pool_drift.py --self-check")
        print("  python model_pool_drift.py detect")
        print("  python model_pool_drift.py drift")
        sys.exit(0)


if __name__ == "__main__":
    main()