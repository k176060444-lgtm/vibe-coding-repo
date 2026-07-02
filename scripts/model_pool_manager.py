#!/usr/bin/env python3
"""
VibeDev Model Pool Manager CLI — maintain the central model pool from the command line.

Usage:
    python scripts/model_pool_manager.py list [--json]
    python scripts/model_pool_manager.py add --id ID --alias ALIAS [--alias ALIAS2 ...] --provider P --model M --key-env KEY [options]
    python scripts/model_pool_manager.py update ID [--provider P] [--model M] [--key-env KEY] [--base-url-env URL]
                                       [--enable|--disable] [--quarantine|--unquarantine]
                                       [--nodes NODE,...] [--notes TEXT] [--priority N]
                                       [--capability-tags TAG,...] [--cost COST]
                                       [--internal-provider-id PID] [--key-env-aliases KEY,...]
                                       [--smoke-required BOOL] [--add-alias ALIAS] [--remove-alias ALIAS]
                                       [--dry-run] [--apply]
    python scripts/model_pool_manager.py remove ID [--dry-run] [--force] [--reason TEXT]
    python scripts/model_pool_manager.py deprecate ID [--reason TEXT]
    python scripts/model_pool_manager.py enable ID
    python scripts/model_pool_manager.py disable ID
    python scripts/model_pool_manager.py validate-full [--json]
    python scripts/model_pool_manager.py freeze [--evidence PATH] [--output PATH]
    python scripts/model_pool_manager.py sync [--nodes N,...]

Output: all commands return JSON to stdout for machine consumption.
"""

import argparse
import copy
import json
import os
import shutil
import sys
import tempfile
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from collections import OrderedDict

# --- Paths ---
SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
DEFAULT_POOL = SCRIPTS_DIR / "model_pool.yaml"
DEFAULT_EVIDENCE = SCRIPTS_DIR / "fixtures" / "credential_evidence_live.json"
KNOWN_NODES = {"5bao", "9bao", "21bao", "win"}

# --- Helpers ---

def _load_pool(path=None):
    """Load the current model pool YAML."""
    import yaml
    path = path or DEFAULT_POOL
    if not path.exists():
        return {"schema_version": "1.0", "models": []}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {"schema_version": "1.0", "models": []}


def _save_pool(pool, path=None):
    """Save the model pool back to YAML with backup."""
    import yaml
    from collections import OrderedDict
    path = path or DEFAULT_POOL
    # Create backup
    if path.exists():
        backup = path.with_suffix(".yaml.bak")
        shutil.copy2(str(path), str(backup))
    with open(path, "w", encoding="utf-8") as f:
        # Use representer that handles all dict types cleanly
        dumper = yaml.SafeDumper
        dumper.add_representer(OrderedDict, dumper.represent_dict)
        dumper.add_representer(dict, dumper.represent_dict)
        yaml.dump(pool, f, default_flow_style=False, allow_unicode=True, sort_keys=False, Dumper=dumper)
    return path


def _find_model(pool, model_id):
    """Find a model by ID in the pool list. Returns (index, model) or (None, None)."""
    models = pool.get("models", [])
    for i, m in enumerate(models):
        if m.get("id") == model_id:
            return i, m
    return None, None


def _resolve_path(path_str):
    """Resolve relative path from SCRIPTS_DIR."""
    if not path_str:
        return None
    p = Path(path_str)
    if not p.is_absolute():
        p = SCRIPTS_DIR / path_str
    return p


def _normalize_bool(val):
    """Normalize various bool representations."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "1", "yes", "y")
    return bool(val)


def _output(data):
    """Print JSON output."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _error(msg, status="ERROR"):
    """Print error output and exit."""
    _output({"status": status, "message": msg})
    sys.exit(1)


def _diff_dict(before, after, prefix=""):
    """Generate a list of changed fields between two dicts."""
    changes = []
    all_keys = set(list(before.keys()) + list(after.keys()))
    for k in sorted(all_keys):
        vb = before.get(k)
        va = after.get(k)
        if vb != va:
            changes.append({
                "field": f"{prefix}{k}" if prefix else k,
                "before": vb,
                "after": va,
            })
    return changes


def _load_evidence(path):
    """Load credential evidence JSON."""
    path = _resolve_path(path) if path else DEFAULT_EVIDENCE
    if not path or not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# --- Commands ---

def cmd_list(args):
    """List models in the pool, optionally filtered by lifecycle_status."""
    pool = _load_pool()
    models = pool.get("models", [])

    # Filter by lifecycle_status if specified
    if hasattr(args, "lifecycle_status") and args.lifecycle_status:
        err = validate_lifecycle_status(args.lifecycle_status)
        if err:
            _error(err, "INVALID_LIFECYCLE_STATUS")
        models = [m for m in models if m.get("lifecycle_status") == args.lifecycle_status]

    if args.json:
        _output({"status": "ok", "total_models": len(models), "models": models})
    else:
        print(f"Total models: {len(models)}" +
              (f" (lifecycle_status={args.lifecycle_status})" if hasattr(args, "lifecycle_status") and args.lifecycle_status else ""))
        for m in models:
            nodes = ",".join(m.get("allowed_nodes", [])) or "(none)"
            enabled = "E" if m.get("enabled") else "D"
            ls = m.get("lifecycle_status", "?")
            print(f"  [{enabled}] {m['id']:40s} ls={ls:30s} nodes=[{nodes}]")
    return True


def cmd_add(args):
    """Add a new model to the pool."""
    pool = _load_pool()
    models = pool.setdefault("models", [])

    # Check duplicate ID
    idx, existing = _find_model(pool, args.id)
    if existing:
        _output({"status": "ERROR", "message": f"Model ID '{args.id}' already exists."})
        sys.exit(1)

    # Check duplicate alias
    new_aliases = args.alias if args.alias else []
    for m in models:
        existing_aliases = set(m.get("alias", []) or [])
        overlapping = existing_aliases & set(new_aliases)
        if overlapping:
            _output({"status": "ALIAS_CONFLICT", "message": f"Alias(es) already in use: {overlapping}", "conflicting_model": m["id"]})
            sys.exit(1)

    tags = []
    if args.capability_tags:
        tags = [t.strip() for t in args.capability_tags.split(",") if t.strip()]

    key_env_aliases = []
    if args.key_env_aliases:
        key_env_aliases = [t.strip() for t in args.key_env_aliases.split(",") if t.strip()]

    nodes = []
    if args.nodes:
        nodes = [n.strip() for n in args.nodes.split(",") if n.strip()]

    entry = OrderedDict()
    entry["id"] = args.id
    entry["alias"] = new_aliases
    entry["provider"] = args.provider
    entry["model"] = args.model
    entry["key_env"] = args.key_env
    if args.base_url_env:
        entry["base_url_env"] = args.base_url_env
    entry["enabled"] = True
    entry["quarantined"] = False
    entry["allowed_nodes"] = nodes
    entry["cost"] = args.cost or "unknown"
    entry["capability_tags"] = tags
    entry["priority"] = args.priority or 50
    entry["fallback_policy"] = "none"
    entry["smoke_required"] = False
    if args.smoke_required:
        entry["smoke_required"] = _normalize_bool(args.smoke_required)
    entry["smoke_results"] = {}
    entry["source"] = "add-command"
    entry["notes"] = args.notes or ""
    if args.lifecycle_status:
        err = validate_lifecycle_status(args.lifecycle_status)
        if err:
            _error(err, "INVALID_LIFECYCLE_STATUS")
        entry["lifecycle_status"] = args.lifecycle_status
    if args.internal_provider_id:
        entry["internal_provider_id"] = args.internal_provider_id
    if key_env_aliases:
        entry["key_env_aliases"] = key_env_aliases

    models.append(entry)
    _save_pool(pool)

    _output({
        "status": "ok",
        "message": f"Added model '{args.id}'",
        "initial_status": "UNVERIFIED",
        "id": args.id,
    })
    return True


def cmd_update(args):
    """Update a model entry."""
    pool = _load_pool()
    idx, model = _find_model(pool, args.id)
    if not model:
        _error(f"Model ID '{args.id}' not found.", "NOT_FOUND")

    before = copy.deepcopy(model)
    changes = []

    # Simple field updates
    for field, attr in [
        ("provider", "provider"), ("model", "model"), ("key_env", "key_env"),
        ("base_url_env", "base_url_env"), ("cost", "cost"),
        ("priority", "priority"), ("notes", "notes"),
        ("lifecycle_status", "lifecycle_status"),
        ("internal_provider_id", "internal_provider_id"),
    ]:
        val = getattr(args, attr, None)
        if val is not None:
            model[field] = val

    # Bool fields
    if args.enable is True:
        model["enabled"] = True
    elif args.disable is True:
        model["enabled"] = False
    if args.quarantine is True:
        model["quarantined"] = True
    elif args.unquarantine is True:
        model["quarantined"] = False

    # Smoke required
    if args.smoke_required is not None:
        model["smoke_required"] = _normalize_bool(args.smoke_required)

    # Allowed nodes
    if hasattr(args, "nodes") and args.nodes is not None:
        model["allowed_nodes"] = [n.strip() for n in args.nodes.split(",") if n.strip()]

    # Capability tags
    if args.capability_tags is not None:
        model["capability_tags"] = [t.strip() for t in args.capability_tags.split(",") if t.strip()]

    # Key env aliases
    if args.key_env_aliases is not None:
        model["key_env_aliases"] = [t.strip() for t in args.key_env_aliases.split(",") if t.strip()]

    # Aliases
    if args.add_alias:
        existing = set(model.get("alias", []) or [])
        existing.add(args.add_alias)
        model["alias"] = list(existing)
    if args.remove_alias:
        existing = set(model.get("alias", []) or [])
        existing.discard(args.remove_alias)
        model["alias"] = list(existing)

    after = model
    changes = _diff_dict(before, after)

    is_dry_run = args.dry_run if (args.dry_run or args.apply) else True
    if is_dry_run:
        _output({
            "status": "DRY_RUN",
            "id": args.id,
            "changes": changes,
            "change_count": len(changes),
            "message": "Use --apply to commit changes.",
        })
        return True

    # Apply
    pool["models"][idx] = model
    _save_pool(pool)
    _output({
        "status": "ok",
        "id": args.id,
        "changes": changes,
        "change_count": len(changes),
        "message": "Changes applied.",
    })
    return True


def _get_impact_report(pool, model_id, model):
    """Generate impact report for a model removal."""
    aliases = model.get("alias", [])
    nodes = model.get("allowed_nodes", [])
    smoke_results = model.get("smoke_results", {})
    enabled = model.get("enabled", False)
    quarantined = model.get("quarantined", False)
    provider = model.get("provider", "?")
    model_name = model.get("model", "?")

    impact = {
        "id": model_id,
        "aliases": aliases,
        "provider_model": f"{provider}/{model_name}",
        "enabled": enabled,
        "quarantined": quarantined,
        "assigned_nodes": nodes,
        "smoke_results": smoke_results,
        "smoke_verified": bool(smoke_results),
    }
    return impact


def cmd_remove(args):
    """Remove or deprecate a model."""
    pool = _load_pool()
    idx, model = _find_model(pool, args.id)
    if not model:
        _error(f"Model ID '{args.id}' not found.", "NOT_FOUND")

    impact = _get_impact_report(pool, args.id, model)

    # Check if VERIFIED (has smoke_results)
    is_verified = bool(model.get("smoke_results", {}))

    if args.dry_run:
        _output({
            "status": "DRY_RUN",
            "id": args.id,
            "impact": impact,
            "would_delete": True,
            "verified": is_verified,
            "blocked_without_force": is_verified,
            "message": "Dry-run: use --force to bypass verified protection, or use 'deprecate' instead.",
        })
        return True

    if is_verified and not args.force:
        _output({
            "status": "BLOCKED",
            "id": args.id,
            "impact": impact,
            "message": "VERIFIED model cannot be removed without --force. Use 'deprecate' instead.",
        })
        sys.exit(1)

    # Remove
    removed = pool["models"].pop(idx)
    _save_pool(pool)
    _output({
        "status": "ok",
        "id": args.id,
        "message": f"Removed model '{args.id}'." + (f" Reason: {args.reason}" if args.reason else ""),
        "impact": impact,
    })
    return True


def cmd_deprecate(args):
    """Deprecate a model (disable + quarantine + note)."""
    pool = _load_pool()
    idx, model = _find_model(pool, args.id)
    if not model:
        _error(f"Model ID '{args.id}' not found.", "NOT_FOUND")

    model["enabled"] = False
    model["quarantined"] = True
    reason = args.reason or "Deprecated by operator"
    model["notes"] = (model.get("notes", "") + f" | DEPRECATED: {reason}").strip()
    pool["models"][idx] = model
    _save_pool(pool)

    _output({
        "status": "ok",
        "id": args.id,
        "message": f"Model '{args.id}' deprecated. Reason: {reason}",
    })
    return True


def cmd_enable(args):
    """Enable a model."""
    pool = _load_pool()
    idx, model = _find_model(pool, args.id)
    if not model:
        _error(f"Model ID '{args.id}' not found.", "NOT_FOUND")
    model["enabled"] = True
    model["quarantined"] = False
    pool["models"][idx] = model
    _save_pool(pool)
    _output({"status": "ok", "id": args.id, "message": f"Model '{args.id}' enabled."})
    return True


def cmd_disable(args):
    """Disable a model."""
    pool = _load_pool()
    idx, model = _find_model(pool, args.id)
    if not model:
        _error(f"Model ID '{args.id}' not found.", "NOT_FOUND")
    model["enabled"] = False
    pool["models"][idx] = model
    _save_pool(pool)
    _output({"status": "ok", "id": args.id, "message": f"Model '{args.id}' disabled."})
    return True


def cmd_validate_full(args):
    """Run full validation on the model pool."""
    pool = _load_pool()
    models = pool.get("models", [])
    errors = []
    warnings = []

    seen_ids = set()
    seen_aliases = {}
    node_set = KNOWN_NODES

    for i, m in enumerate(models):
        mid = m.get("id")
        # Check duplicate IDs
        if mid in seen_ids:
            errors.append({"type": "DUPLICATE_ID", "id": mid, "index": i})
        else:
            seen_ids.add(mid)

        # Check duplicate aliases (skip empty/none)
        for alias in (m.get("alias") or []):
            if not alias:
                continue
            if alias in seen_aliases:
                errors.append({
                    "type": "DUPLICATE_ALIAS",
                    "alias": alias,
                    "models": [seen_aliases[alias], mid],
                })
            else:
                seen_aliases[alias] = mid

        # Check missing key_env
        if not m.get("key_env"):
            errors.append({"type": "MISSING_KEY_ENV", "id": mid, "index": i})

        # Check invalid nodes
        for node in (m.get("allowed_nodes") or []):
            if node not in node_set:
                errors.append({"type": "UNKNOWN_NODE", "id": mid, "node": node, "index": i})

        # Check enabled but no nodes
        if m.get("enabled") and not m.get("allowed_nodes"):
            warnings.append({"type": "ENABLED_NO_NODES", "id": mid, "index": i})

        # Check internal_provider_id format
        ipid = m.get("internal_provider_id")
        if ipid and not isinstance(ipid, str):
            errors.append({"type": "INVALID_INTERNAL_PROVIDER_ID", "id": mid, "value": ipid, "index": i})

        # Check smoke_required vs smoke_results
        if m.get("smoke_required") and not m.get("smoke_results"):
            warnings.append({"type": "SMOKE_REQUIRED_NO_RESULTS", "id": mid, "index": i})

        # Check base_url_env (recommended but not required)
        if not m.get("base_url_env"):
            warnings.append({"type": "MISSING_BASE_URL_ENV", "id": mid, "index": i})

    # Check tracked repo for inline secrets
    secret_patterns = ["OPENCODE_", "api_key", "apiKey"]
    tracked_secrets_found = _check_tracked_repo_secrets(secret_patterns)
    for item in tracked_secrets_found:
        errors.append(item)

    status = "ERRORS_FOUND" if errors else "ok"
    result = {
        "status": status,
        "total_models": len(models),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "summary": f"{len(models)} models, {len(errors)} errors, {len(warnings)} warnings",
    }
    _output(result)
    return True


# --- baseline01 G4 helpers (schema 1.1 additive) ---

# Field name sets — kept module-level so both validate-schema / validate-backward-compat
# and the migrate command share a single source of truth.
G4_NEW_MODEL_FIELDS = ("canonical_provider", "provider_namespace", "primary_alias")
G4_LEGACY_MODEL_FIELDS = ("provider", "alias")  # alias is reused as both list (legacy) and string (new); see notes.
G4_REQUIRED_NEW = ("canonical_provider", "provider_namespace", "primary_alias")


def _get_new_alias(entry):
    """Return the explicit single alias introduced in schema 1.1 (primary_alias)."""
    return entry.get("primary_alias")


def _resolve_provider_namespace(entry, namespace_mapping=None):
    """Resolve provider_namespace with strict source-of-truth priority.

    Priority:
      1. entry-level explicit `provider_namespace` / `namespace` field
      2. namespace_mapping[alias] reverse lookup (if a mapping table is supplied)
      3. otherwise "unknown" — DO NOT infer from alias.
    """
    explicit = entry.get("provider_namespace") or entry.get("namespace")
    if explicit:
        return explicit
    primary_alias = None
    if isinstance(entry.get("primary_alias"), str) and entry.get("primary_alias"):
        primary_alias = entry["primary_alias"]
    elif entry.get("alias") and isinstance(entry["alias"], list) and entry["alias"]:
        primary_alias = entry["alias"][0]
    if primary_alias and namespace_mapping and primary_alias in namespace_mapping:
        return namespace_mapping[primary_alias]
    return "unknown"


def cmd_validate_schema(args):
    """Validate schema_version == 1.1 + every model entry has the new G4 fields.

    Schema 1.1 is purely additive: legacy `provider` / `alias` (list) fields MUST
    remain present (validated separately by validate-backward-compat). This
    command only checks the additive layer.
    """
    pool = _load_pool()
    schema_version = str(pool.get("schema_version", "1.0"))
    models = pool.get("models", [])

    errors = []
    warnings = []
    seen_migration_state = {"has_canonical_provider": 0, "has_provider_namespace": 0, "has_primary_alias": 0}

    for i, m in enumerate(models):
        mid = m.get("id")
        if "canonical_provider" in m and m["canonical_provider"]:
            seen_migration_state["has_canonical_provider"] += 1
        else:
            errors.append({"type": "MISSING_CANONICAL_PROVIDER", "id": mid, "index": i})

        if "provider_namespace" in m and m["provider_namespace"]:
            seen_migration_state["has_provider_namespace"] += 1
        else:
            errors.append({"type": "MISSING_PROVIDER_NAMESPACE", "id": mid, "index": i})

        if "primary_alias" in m and m["primary_alias"]:
            seen_migration_state["has_primary_alias"] += 1
        else:
            errors.append({"type": "MISSING_ALIAS_G4", "id": mid, "index": i})

        ns = m.get("provider_namespace")
        if ns is not None and ns != "unknown" and not isinstance(ns, str):
            errors.append({"type": "INVALID_PROVIDER_NAMESPACE", "id": mid, "value": ns, "index": i})

    if schema_version not in ("1.1", "1.2"):
        errors.append({"type": "SCHEMA_VERSION_NOT_1_1_OR_1_2", "expected": "1.1 or 1.2", "actual": schema_version})

    # Lifecycle_status check (v1.2+)
    seen_ls = {"present": 0, "missing": 0}
    for m in models:
        if "lifecycle_status" in m and m.get("lifecycle_status"):
            seen_ls["present"] += 1
            ls = m["lifecycle_status"]
            if ls not in LIFECYCLE_STATUS_VALUES:
                errors.append({"type": "INVALID_LIFECYCLE_STATUS", "id": m.get("id"), "value": ls})
        else:
            seen_ls["missing"] += 1
            if schema_version == "1.2":
                warnings.append({"type": "MISSING_LIFECYCLE_STATUS", "id": m.get("id"), "message": "All models should have lifecycle_status in schema v1.2; run 'classify --apply'"})

    status = "ok" if not errors else "ERRORS_FOUND"
    result = {
        "status": status,
        "schema_version": schema_version,
        "total_models": len(models),
        "migration_state": seen_migration_state,
        "lifecycle_status": seen_ls,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }
    _output(result)
    return status == "ok"


def cmd_validate_backward_compat(args):
    """Verify that legacy `provider` and `alias` (list) fields are still readable.

    Schema 1.1 is additive only: legacy fields must remain present and readable
    for downstream renderers and existing tests. This command confirms that.
    """
    pool = _load_pool()
    models = pool.get("models", [])

    errors = []
    warnings = []

    for i, m in enumerate(models):
        mid = m.get("id")
        if "provider" not in m or not m["provider"]:
            errors.append({"type": "LEGACY_PROVIDER_MISSING", "id": mid, "index": i})
        if "alias" not in m or not isinstance(m["alias"], list):
            errors.append({"type": "LEGACY_ALIAS_LIST_MISSING", "id": mid, "index": i})
        if "canonical_provider" in m and "provider" in m:
            if m["canonical_provider"] != m["provider"]:
                warnings.append({
                    "type": "CANONICAL_PROVIDER_DIVERGES_FROM_LEGACY",
                    "id": mid,
                    "canonical": m["canonical_provider"],
                    "legacy": m["provider"],
                    "index": i,
                })

    status = "ok" if not errors else "ERRORS_FOUND"
    result = {
        "status": status,
        "total_models": len(models),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }
    _output(result)
    return status == "ok"


def cmd_self_check(args):
    """Top-level self-check: schema_version + new field coverage + backward compat.

    Returns combined verdict. Exits 0 only if all checks pass.
    """
    pool = _load_pool()
    schema_version = str(pool.get("schema_version", "1.0"))
    models = pool.get("models", [])

    new_field_counts = {"canonical_provider": 0, "provider_namespace": 0, "primary_alias": 0}
    legacy_field_counts = {"provider": 0, "alias": 0}

    for m in models:
        for k in new_field_counts:
            if m.get(k):
                new_field_counts[k] += 1
        if m.get("provider"):
            legacy_field_counts["provider"] += 1
        if isinstance(m.get("alias"), list):
            legacy_field_counts["alias"] += 1

    result = {
        "status": "ok",
        "schema_version": schema_version,
        "expected_schema_version": "1.1 or 1.2",
        "total_models": len(models),
        "new_field_counts": new_field_counts,
        "legacy_field_counts": legacy_field_counts,
        "summary": (
            f"schema_version={schema_version} (expected 1.1/1.2); "
            f"new_fields coverage: canonical_provider={new_field_counts['canonical_provider']}/{len(models)}, "
            f"provider_namespace={new_field_counts['provider_namespace']}/{len(models)}, "
            f"primary_alias={new_field_counts['primary_alias']}/{len(models)}; "
            f"legacy_fields retained: provider={legacy_field_counts['provider']}/{len(models)}, "
            f"alias(list)={legacy_field_counts['alias']}/{len(models)}"
        ),
    }

    coverage_ok = all(v == len(models) for v in new_field_counts.values())
    legacy_ok = all(v == len(models) for v in legacy_field_counts.values())
    schema_ok = schema_version in ("1.1", "1.2")
    if not (coverage_ok and legacy_ok and schema_ok):
        result["status"] = "WARN"
        result["issues"] = {
            "coverage_ok": coverage_ok,
            "legacy_ok": legacy_ok,
            "schema_ok": schema_ok,
        }

    _output(result)
    return result["status"] == "ok"


def cmd_migrate(args):
    """Apply the G4 additive migration to model_pool.yaml in place.

    Idempotent: entries that already have primary_alias / canonical_provider /
    provider_namespace set are not overwritten. Legacy fields (`provider`,
    `alias` list) are NEVER removed.
    """
    pool = _load_pool()
    if str(pool.get("schema_version", "1.0")) != "1.1":
        pool["schema_version"] = "1.1"

    namespace_mapping = None
    if args.namespace_mapping:
        mapping_path = _resolve_path(args.namespace_mapping)
        if mapping_path and mapping_path.exists():
            try:
                import yaml
                with open(mapping_path, "r", encoding="utf-8") as f:
                    namespace_mapping = yaml.safe_load(f) or {}
            except Exception as e:
                _output({"status": "WARN", "message": f"namespace_mapping load failed: {e}"})

    changes = []
    for i, m in enumerate(pool.get("models", [])):
        mid = m.get("id")
        before = {k: m.get(k) for k in G4_NEW_MODEL_FIELDS}

        if not m.get("canonical_provider") and m.get("provider"):
            m["canonical_provider"] = m["provider"]

        if not m.get("provider_namespace"):
            m["provider_namespace"] = _resolve_provider_namespace(m, namespace_mapping)

        if not m.get("primary_alias"):
            legacy_aliases = m.get("alias")
            if isinstance(legacy_aliases, list) and legacy_aliases:
                m["primary_alias"] = legacy_aliases[0]
            else:
                m["primary_alias"] = "unknown"

        after = {k: m.get(k) for k in G4_NEW_MODEL_FIELDS}
        for k in G4_NEW_MODEL_FIELDS:
            if before.get(k) != after.get(k):
                changes.append({"id": mid, "field": k, "before": before.get(k), "after": after.get(k)})

    if args.apply:
        pass  # fall through to apply
    elif args.dry_run:
        _output({
            "status": "DRY_RUN",
            "change_count": len(changes),
            "changes": changes[:50],
            "message": "Use --apply to commit migration.",
        })
        return True
    else:
        # No flag given — default to dry-run for safety.
        _output({
            "status": "DRY_RUN",
            "change_count": len(changes),
            "changes": changes[:50],
            "message": "Default mode is dry-run; pass --apply to commit.",
        })
        return True

    _save_pool(pool)
    _output({
        "status": "ok",
        "change_count": len(changes),
        "applied": len(changes),
        "schema_version": pool.get("schema_version"),
        "message": "Migration applied; legacy fields preserved.",
    })
    return True


def _check_tracked_repo_secrets(patterns):
    """Quick check for inline secrets in tracked files."""
    findings = []
    repo_git_dir = REPO_ROOT / ".git"
    if not repo_git_dir.exists():
        return findings

    # Check model_pool.yaml itself — key_env should be var names, not values
    pool = _load_pool()
    for m in pool.get("models", []):
        ke = m.get("key_env", "")
        if ke and not ke.startswith("OPENCODE_") and not ke.startswith("XIAOMI_") and not ke.startswith("MINIMAX_") and not ke.startswith("DEEPSEEK_") and not ke.startswith("VOLCENGINE_") and not ke.startswith("ANTHROPIC_") and not ke.startswith("DASHSCOPE_") and not ke.startswith("GOOGLE_") and not ke.startswith("MOONSHOT_") and not ke.startswith("OPENAI_") and not ke.startswith("XAI_"):
            findings.append({
                "type": "SUSPICIOUS_KEY_ENV",
                "id": m.get("id"),
                "key_env": ke,
            })
    return findings


def cmd_freeze(args):
    """Generate a capability freeze snapshot from the pool and evidence."""
    pool = _load_pool()
    models = pool.get("models", [])

    evidence = _load_evidence(args.evidence) if args.evidence else {}

    nodes_data = OrderedDict()
    # Map win -> 21bao for freeze output
    node_alias_map = {"win": "21bao"}
    for raw_node in sorted(KNOWN_NODES):
        node = node_alias_map.get(raw_node, raw_node)
        # Collect models for this node
        # Also match raw_node for pool lookup
        node_providers = OrderedDict()
        node_verified = 0
        for m in models:
            if not m.get("enabled"):
                continue
            allowed = m.get("allowed_nodes", [])
            # If allowed_nodes is empty, the model is enabled but not assigned — skip
            if not allowed or raw_node not in allowed and node not in allowed:
                continue
            provider = m.get("provider", "other")
            model_name = m.get("model", "?")
            alias = m.get("alias", [m["id"]])[0]

            if provider not in node_providers:
                node_providers[provider] = {
                    "internal_provider_id": m.get("internal_provider_id", provider),
                    "key_env": m.get("key_env", "?"),
                    "credential_source": evidence.get(node, {}).get(provider, {}).get("reason", "unknown"),
                    "models": OrderedDict(),
                }

            # Determine status: prefer individual smoke_results over provider-level inference
            smoke = m.get("smoke_results", {})
            # Normalize provider key for evidence lookup
            provider_map = {
                "deepseek-plan": "deepseek",
                "minimax-plan": "minimax",
                "volcengine-plan": "volcengine",
                "xiaomi": "xiaomi",
                "xiaomi-plan": "xiaomi",
            }
            ev_provider_key = provider_map.get(provider, provider)
            ev_status = evidence.get(node, {}).get(ev_provider_key, {}).get("status", "")

            # Individual smoke_results trumps provider-level inference
            if smoke:
                # Has individual smoke data — use the last smoke result
                last_smoke = list(smoke.values())[0] if isinstance(smoke, dict) else {}
                if isinstance(last_smoke, dict) and last_smoke.get("status") == "PASS":
                    status = "V"
                elif isinstance(last_smoke, dict) and last_smoke.get("status") == "VFV":
                    status = "VFV"
                else:
                    # Smoke exists but no verdict recorded — fall through
                    if ev_status == "VERIFIED":
                        status = "INFERRED_PROVIDER_OK"
                    else:
                        status = "UNVERIFIED"
                # Use the smoke timestamp regardless
                if isinstance(last_smoke, dict):
                    entry_smoke_ts = last_smoke.get("timestamp", "?")
                    entry_smoke_dur = last_smoke.get("duration")
                else:
                    entry_smoke_ts = "?"
                    entry_smoke_dur = None
            elif ev_status == "VERIFIED":
                # Provider-level evidence but no individual smoke — mark as inferred
                status = "INFERRED_PROVIDER_OK"
                entry_smoke_ts = None
                entry_smoke_dur = None
            elif ev_status == "VFV":
                status = "INFERRED_PROVIDER_OK"
                entry_smoke_ts = None
                entry_smoke_dur = None
            elif m.get("quarantined") or not m.get("enabled"):
                status = "FROZEN"
                entry_smoke_ts = None
                entry_smoke_dur = None
            elif "xiaomi" in m.get("id", "").lower():
                status = "FROZEN"
                entry_smoke_ts = None
                entry_smoke_dur = None
            else:
                status = "UNVERIFIED"
                entry_smoke_ts = None
                entry_smoke_dur = None

            if status in ("V", "VFV"):
                node_verified += 1

            entry = OrderedDict()
            entry["model"] = model_name
            entry["alias"] = alias
            entry["status"] = status
            if entry_smoke_ts and entry_smoke_ts != "?":
                entry["last_smoke"] = entry_smoke_ts
                if entry_smoke_dur:
                    entry["duration_seconds"] = entry_smoke_dur
            node_providers[provider]["models"][m["id"]] = entry

        if node_providers:
            nodes_data[node] = OrderedDict()
            nodes_data[node]["description"] = f"Worker {node}"
            nodes_data[node]["opencode_version"] = "1.17.8"
            nodes_data[node]["total_models_verified"] = node_verified
            nodes_data[node]["providers"] = node_providers

    # Cluster totals
    inferred_count = sum(
        1 for ndata in nodes_data.values()
        for pdata in ndata.get("providers", {}).values()
        for mdata in pdata.get("models", {}).values()
        if mdata.get("status") == "INFERRED_PROVIDER_OK"
    )
    frozen_count = sum(
        1 for ndata in nodes_data.values()
        for pdata in ndata.get("providers", {}).values()
        for mdata in pdata.get("models", {}).values()
        if mdata.get("status") == "FROZEN"
    )
    totals = {
        "5bao_verified": nodes_data.get("5bao", {}).get("total_models_verified", 0),
        "9bao_verified": nodes_data.get("9bao", {}).get("total_models_verified", 0),
        "21bao_verified": nodes_data.get("21bao", {}).get("total_models_verified", 0),
        "total_verified_unique_model_entries": sum(
            nodes_data.get(n, {}).get("total_models_verified", 0)
            for n in ["5bao", "9bao", "21bao"]
        ),
        "total_inferred_provider_ok": inferred_count,
        "total_frozen": frozen_count,
    }

    result = OrderedDict()
    result["meta"] = OrderedDict()
    result["meta"]["snapshot_version"] = "1.1"
    result["meta"]["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    result["meta"]["generated_by"] = "model_pool_manager.py freeze"
    result["nodes"] = nodes_data
    result["cluster_totals"] = totals
    result["deferred_providers"] = []
    result["recommended_scheduling"] = OrderedDict()
    result["recommended_scheduling"]["description"] = "Manual operator approval required before each gray task."

    output_path = args.output
    if output_path:
        out_path = _resolve_path(output_path)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        result["_saved_to"] = str(out_path)

    _output(result)
    return True


def cmd_sync(args):
    """Generate a sync plan (contract-only, no write)."""
    pool = _load_pool()
    models = pool.get("models", [])

    target_nodes = args.nodes.split(",") if args.nodes else list(KNOWN_NODES - {"win"})
    target_nodes = [n.strip() for n in target_nodes if n.strip() != "win"]

    plans = []
    for node in target_nodes:
        node_models = [m for m in models if node in (m.get("allowed_nodes") or [])]

        # Separate by provider type
        providers = {}
        for m in node_models:
            prov = m.get("provider", "other")
            if prov not in providers:
                providers[prov] = []
            providers[prov].append(m["id"])

        plans.append({
            "node": node,
            "total_models": len(node_models),
            "providers": providers,
            "target_files": [
                f"opencode.jsonc (partial update for {node})",
                f"opencode.env (if key_env changes)",
            ],
            "backup_plan": ".bak file before write",
            "credential_source": "central overlay -> worker env",
            "needs_smoke": True,
            "needs_manual_approval": True,
        })

    _output({
        "status": "DRY_RUN",
        "mode": "contract-only",
        "contract": {
            "write_blocked": True,
            "description": "Sync is contract-only. Real writes require separate approved Work Order and --apply.",
            "required_gates": ["operator_approval", "backup", "smoke_after_sync"],
        },
        "plans": plans,
    })
    return True


# ── lifecycle_status (schema v1.2) ------------------------------------------------

LIFECYCLE_STATUS_VALUES = frozenset({
    "required",
    "operator_requested",
    "enabled_assigned",
    "declared_enabled_unassigned",
    "candidate",
    "disabled",
    "historical",
    "remove_pending",
})

# Models with explicit F6 operator_approved receipt (lifecycle_status=operator_requested)
EXPLICIT_OPERATOR_REQUESTED = frozenset({"opencode-go-mimo-v2-5"})

# Provider-level auto-classify rules for non-enabled models
CANDIDATE_NAMESPACES = frozenset({"volcengine", "deepseek-plan", "minimax-plan"})
REMOVE_PENDING_NAMESPACES = frozenset({"opencode"})
HISTORICAL_PROVIDER_NAMES = frozenset({"xiaomi", "minimax"})


def auto_classify(model: dict) -> str:
    """Determine lifecycle_status from existing model fields.

    Returns one of the 8 LIFECYCLE_STATUS_VALUES. Does NOT read or depend
    on any secret field (key_env, base_url_env values). Pure deterministic
    function based on id, enabled, allowed_nodes, and canonical_provider.
    """
    mid = model.get("id", "")
    enabled = bool(model.get("enabled", False))
    allowed_nodes = model.get("allowed_nodes") or []
    cp = model.get("canonical_provider", "")

    # operator_requested: models with explicit F6 operator_approved receipt
    if mid in EXPLICIT_OPERATOR_REQUESTED:
        return "operator_requested"

    if enabled:
        if allowed_nodes:
            return "enabled_assigned"
        return "declared_enabled_unassigned"

    # Disabled models — classify by provider/namespace
    ns = model.get("provider_namespace", "")
    if ns in CANDIDATE_NAMESPACES or cp in CANDIDATE_NAMESPACES:
        return "candidate"
    if ns in REMOVE_PENDING_NAMESPACES or cp == "opencode":
        return "remove_pending"
    if cp in HISTORICAL_PROVIDER_NAMES:
        return "historical"
    return "disabled"


def validate_lifecycle_status(status: str) -> str | None:
    """Validate lifecycle_status. Return error message or None."""
    if status not in LIFECYCLE_STATUS_VALUES:
        return (f"Invalid lifecycle_status '{status}'. "
                f"Must be one of: {', '.join(sorted(LIFECYCLE_STATUS_VALUES))}")
    return None


# ── credential_status — additive schema v1.2 ─────────────────────────────────
# Allowed values (Phase 3 PR-5):
#   present       = credential ref (key_env/base_url_env NAME) declared in pool
#   empty         = ref exists but is empty (no value available)
#   missing       = required ref is absent
#   unknown       = not audited yet
#   not_required  = model/provider does not need credential

CREDENTIAL_STATUS_VALUES = frozenset({
    "present", "empty", "missing", "unknown", "not_required",
})


def auto_classify_credential_status(model: dict) -> str:
    """Determine credential_status from model fields.

    Pure deterministic function — reads key_env NAME existence (not value),
    base_url_env NAME existence (not value), and lifecycle_status. No env var
    reading. No secret value access.

    Returns one of:
      present       — key_env or base_url_env NAME is declared
      not_required  — lifecycle in (disabled, historical, remove_pending)
      unknown       — no ref declared, lifecycle in (candidate, declared_enabled_unassigned, or unknown)
      missing       — no ref declared, lifecycle in (enabled_assigned, operator_requested) — should not happen
    """
    key_env = (model.get("key_env") or "").strip()
    base_url_env = (model.get("base_url_env") or "").strip()
    ls = (model.get("lifecycle_status") or "").strip()

    has_ref = bool(key_env) or bool(base_url_env)

    if not has_ref:
        # No credential ref declared in YAML
        if ls in ("remove_pending", "historical", "disabled"):
            return "not_required"
        elif ls in ("candidate", "declared_enabled_unassigned"):
            return "unknown"
        elif ls in ("enabled_assigned", "operator_requested"):
            return "missing"
        else:
            return "unknown"
    else:
        # Credential ref NAME declared in YAML (value may or may not be populated in env)
        if ls in ("remove_pending", "historical", "disabled"):
            return "not_required"
        return "present"


def validate_credential_status(status: str) -> str | None:
    """Validate credential_status. Return error message or None."""
    if status not in CREDENTIAL_STATUS_VALUES:
        return (f"Invalid credential_status '{status}'. "
                f"Must be one of: {', '.join(sorted(CREDENTIAL_STATUS_VALUES))}")
    return None


# ── endpoint_ref — additive schema v1.2 (Phase 3 PR-6) ──────────────────────
# Allowed values:
#   base_url_env  = model's base_url_env NAME is the endpoint reference
#   not_required  = model does not need an endpoint (inactive lifecycle)
#   unknown       = not audited yet
#   missing       = required ref is absent (fail-closed guard)

ENDPOINT_REF_VALUES = frozenset({
    "base_url_env", "not_required", "unknown", "missing",
})


def auto_classify_endpoint_ref(model: dict) -> str:
    """Determine endpoint_ref from model fields.

    Pure deterministic function — reads base_url_env NAME existence (not
    value) and lifecycle_status. No env var reading. No URL value access.

    Returns one of:
      base_url_env   — base_url_env NAME is declared (the reference NAME,
                       never the real URL value)
      not_required   — lifecycle in (disabled, historical, remove_pending)
      unknown        — no ref declared, lifecycle in (candidate,
                       declared_enabled_unassigned, or unknown)
      missing        — no ref declared, lifecycle in (enabled_assigned,
                       operator_requested) — should not happen
    """
    base_url_env = (model.get("base_url_env") or "").strip()
    ls = (model.get("lifecycle_status") or "").strip()

    has_ref = bool(base_url_env)

    if not has_ref:
        if ls in ("remove_pending", "historical", "disabled"):
            return "not_required"
        elif ls in ("candidate", "declared_enabled_unassigned"):
            return "unknown"
        elif ls in ("enabled_assigned", "operator_requested"):
            return "missing"
        else:
            return "unknown"
    else:
        if ls in ("remove_pending", "historical", "disabled"):
            return "not_required"
        return "base_url_env"


def validate_endpoint_ref(status: str) -> str | None:
    """Validate endpoint_ref. Return error message or None."""
    if status not in ENDPOINT_REF_VALUES:
        return (f"Invalid endpoint_ref '{status}'. "
                f"Must be one of: {', '.join(sorted(ENDPOINT_REF_VALUES))}")
    return None


# ── cmd_classify: auto-classify all models ──────────────────────────────────


def cmd_classify(args):
    """Auto-classify all models by lifecycle_status (schema v1.2).

    Reads each model's existing fields (id, enabled, allowed_nodes,
    canonical_provider, provider_namespace) and assigns lifecycle_status
    using auto_classify(). Pure deterministic function — no secret read.
    """
    pool = _load_pool()
    models = pool.get("models", [])
    result = []
    for m in models:
        new_status = auto_classify(m)
        old_status = m.get("lifecycle_status", None)
        changed = old_status is None or old_status != new_status
        result.append({
            "id": m["id"],
            "from": old_status,
            "to": new_status,
            "changed": changed,
        })
        if args.apply:
            m["lifecycle_status"] = new_status

    if args.apply:
        _save_pool(pool)
        status = "ok"
    else:
        status = "DRY_RUN"

    statuses: dict[str, int] = {}
    for r in result:
        s = r["to"]
        statuses[s] = statuses.get(s, 0) + 1
    changed_count = sum(1 for r in result if r["changed"])

    _output({
        "status": status,
        "total_models": len(result),
        "changed": changed_count,
        "classifications": statuses,
        "details": result,
        "message": "Auto-classified. Pass --apply to write." if status == "DRY_RUN" else f"Written {changed_count} lifecycle_status fields.",
    })
    return True


# ── baseline01 G5 node capability matrix ---------------------------------

ACTIVE_NODES = ["21bao", "5bao", "9bao"]
NODE_RUNTIME_PROVIDER = {
    "21bao": "opencode-go",
    "5bao": "opencode-go",
    "9bao": "opencode-go",
}
NODE_DESCRIPTION = {
    "21bao": "Windows local-exec/control node",
    "5bao": "Remote SSH worker",
    "9bao": "Remote SSH worker",
}
G5_UNKNOWN_FIELDS = ("synced", "wrapper_valid", "model_call_verified",
                     "operator_approved", "runtime_visible", "env_loaded")
G5_ENTRY_FIELDS = ("model_id", "canonical_provider", "provider_namespace",
                  "primary_alias", "runtime_provider", "declared") + G5_UNKNOWN_FIELDS


def _build_node_matrix():
    """Build the per-node capability matrix from model_pool.yaml.

    Returns dict[model_id, dict[field, value]] per node, plus skip stats.
    """
    pool = _load_pool()
    models = pool.get("models", [])
    skipped = []

    node_matrix = {node: [] for node in ACTIVE_NODES}

    for m in models:
        mid = m["id"]
        if not m.get("enabled", True) or m.get("quarantined", False):
            skipped.append({"id": mid, "enabled": m.get("enabled", True),
                            "quarantined": m.get("quarantined", False),
                            "reason": "disabled or quarantined"})
            continue

        allowed = m.get("allowed_nodes", [])
        primary = m.get("primary_alias")
        if not primary:
            _error(f"Model {mid} is missing required primary_alias (G4 not migrated?)")

        for node_name in ACTIVE_NODES:
            if allowed and node_name not in allowed:
                continue
            entry = OrderedDict()
            entry["model_id"] = mid
            entry["canonical_provider"] = m.get("canonical_provider", "unknown")
            entry["provider_namespace"] = m.get("provider_namespace", "unknown")
            entry["primary_alias"] = primary
            entry["runtime_provider"] = NODE_RUNTIME_PROVIDER.get(node_name, "unknown")
            entry["declared"] = True
            for uf in G5_UNKNOWN_FIELDS:
                entry[uf] = "unknown"
            node_matrix[node_name].append(entry)

    return node_matrix, skipped, len(models)


def _node_matrix_to_yaml(node_matrix, skipped, total_models):
    """Convert the node matrix into a YAML document string."""
    import yaml
    from collections import OrderedDict

    top = OrderedDict()
    top["schema_version"] = "1.1"
    top["generated_at"] = datetime.now(timezone.utc).isoformat()
    top["generated_from"] = "scripts/model_pool.yaml"
    top["notes"] = (
        "G5 effective model-node matrix. 6 runtime/approval fields default to 'unknown'; "
        "they will be populated by subsequent diagnostic PRs. "
        "model_id, canonical_provider, provider_namespace, primary_alias, "
        "runtime_provider, declared are backfilled from model_pool.yaml."
    )
    top["skipped_models"] = {"count": len(skipped), "ids": [s["id"] for s in skipped]}
    top["nodes"] = OrderedDict()

    for node_name in ACTIVE_NODES:
        nd = OrderedDict()
        nd["runtime_provider"] = NODE_RUNTIME_PROVIDER.get(node_name, "unknown")
        nd["description"] = NODE_DESCRIPTION.get(node_name, "")
        nd["total_entries"] = len(node_matrix[node_name])
        nd["matrix"] = node_matrix[node_name]
        top["nodes"][node_name] = nd

    dumper = yaml.SafeDumper
    dumper.add_representer(OrderedDict, dumper.represent_dict)
    dumper.add_representer(dict, dumper.represent_dict)
    return yaml.dump(top, default_flow_style=False, allow_unicode=True,
                     sort_keys=False, Dumper=dumper)




# --- baseline02 Phase 3 PR-3: drift Layer 1 (local-only) ---


def cmd_diff(args):
    """Run drift Layer 1: pool ↔ matrix consistency. Local-only, read-only.

    Phase 2 design §2 Layer 1. Compares scripts/model_pool.yaml against
    scripts/node_model_capability.yaml. Returns drift report; non-zero exit
    code if drift detected (BLOCK).
    """
    from model_pool_drift import detect_drift_layer1
    report = detect_drift_layer1()
    _output(report)
    return not report.get("drift_detected", True)


def cmd_drift(args):
    """Same as cmd_diff (Phase 3 PR-3 covers Layer 1 only)."""
    return cmd_diff(args)


# ── credential_status commands (Phase 3 PR-5) ───────────────────────────────


def cmd_credential_status(args):
    """Auto-classify or list credential_status for all models.

    Dry-run only (default): shows credential_status for each model without
    writing to model_pool.yaml. Pass --apply to write credential_status fields.

    Pure deterministic — reads key_env/base_url_env NAME (not value).
    No env var reading. No secret value access.
    """
    pool = _load_pool()
    models = pool.get("models", [])
    result = []
    for m in models:
        new_status = auto_classify_credential_status(m)
        old_status = m.get("credential_status", None)
        changed = (old_status is None or old_status != new_status)
        result.append({
            "id": m["id"],
            "key_env": m.get("key_env", ""),
            "lifecycle_status": m.get("lifecycle_status", ""),
            "from": old_status,
            "to": new_status,
            "changed": changed,
        })
        if args.apply:
            m["credential_status"] = new_status

    if args.apply:
        _save_pool(pool)
        status = "ok"
    else:
        status = "DRY_RUN"

    statuses: dict[str, int] = {}
    for r in result:
        s = r["to"]
        statuses[s] = statuses.get(s, 0) + 1
    changed_count = sum(1 for r in result if r["changed"])

    _output({
        "status": status,
        "total_models": len(result),
        "changed": changed_count,
        "credential_statuses": statuses,
        "details": result,
        "message": "Auto-classified. Pass --apply to write."
            if status == "DRY_RUN"
            else f"Written {changed_count} credential_status fields.",
    })
    return True


def cmd_validate_credential_status(args):
    """Validate credential_status across all models.

    Checks:
    - Allowed enum values
    - Lifecycle constraints:
      - enabled_assigned / operator_requested: credential_status must exist;
        if missing/empty → WARN; if unknown → WARN
      - declared_enabled_unassigned: any valid credential_status → no error
      - disabled / historical / remove_pending: any valid credential_status → ok

    No secret value read. No env var read.
    """
    pool = _load_pool()
    models = pool.get("models", [])

    errors = []
    warnings = []
    valid = set(CREDENTIAL_STATUS_VALUES)

    for m in models:
        mid = m.get("id", "???")
        cs = m.get("credential_status", "")
        ls = m.get("lifecycle_status", "")

        # Check allowed values
        if cs and cs not in valid:
            errors.append({
                "model_id": mid,
                "field": "credential_status",
                "issue": "INVALID_VALUE",
                "detail": f"credential_status='{cs}' not in {sorted(valid)}",
            })
            continue

        # Lifecycle constraints
        if ls in ("enabled_assigned", "operator_requested"):
            if not cs:
                warnings.append({
                    "model_id": mid,
                    "lifecycle_status": ls,
                    "credential_status": cs,
                    "issue": "MISSING",
                    "detail": f"Active model '{mid}' has no credential_status",
                })
            elif cs in ("missing", "empty"):
                errors.append({
                    "model_id": mid,
                    "lifecycle_status": ls,
                    "credential_status": cs,
                    "issue": "REQUIRED_CREDENTIAL_MISSING",
                    "detail": f"Active model '{mid}' has credential_status='{cs}'",
                })
            elif cs == "unknown":
                warnings.append({
                    "model_id": mid,
                    "lifecycle_status": ls,
                    "credential_status": cs,
                    "issue": "UNKNOWN_CREDENTIAL",
                    "detail": f"Active model '{mid}' credential_status=unknown (should audit)",
                })

        elif ls == "declared_enabled_unassigned":
            if not cs:
                warnings.append({
                    "model_id": mid,
                    "lifecycle_status": ls,
                    "credential_status": cs,
                    "issue": "MISSING_OPTIONAL",
                    "detail": f"DEU model '{mid}' has no credential_status (D-B pending, optional)",
                })
            elif cs not in valid:
                errors.append({
                    "model_id": mid,
                    "issue": "INVALID_VALUE",
                    "detail": f"credential_status='{cs}' not in {sorted(valid)}",
                })
            # DEU with any valid credential_status = OK (no error per constraint 8)

        else:
            # candidate, disabled, historical, remove_pending, or unknown lifecycle
            if not cs:
                warnings.append({
                    "model_id": mid,
                    "lifecycle_status": ls,
                    "credential_status": cs,
                    "issue": "MISSING",
                    "detail": f"Model '{mid}' ({ls}) has no credential_status",
                })
            elif cs == "missing":
                warnings.append({
                    "model_id": mid,
                    "lifecycle_status": ls,
                    "credential_status": cs,
                    "issue": "UNEXPECTED_MISSING",
                    "detail": f"Model '{mid}' ({ls}) credential_status='missing' (not required)",
                })

    _output({
        "status": "ok" if not errors else "ERRORS_FOUND",
        "total_models": len(models),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "note": "credential_status is additive schema (Phase 3 PR-5). F6 readiness gate not affected.",
    })
    return len(errors) == 0


# ── endpoint_ref commands (Phase 3 PR-6) ────────────────────────────────────


def cmd_endpoint_ref(args):
    """Auto-classify or list endpoint_ref for all models.

    Dry-run only (default): shows endpoint_ref for each model without
    writing to model_pool.yaml. Pass --apply to write endpoint_ref fields.

    Pure deterministic — reads base_url_env NAME (not value).
    No env var reading. No URL value access.
    """
    pool = _load_pool()
    models = pool.get("models", [])
    result = []
    for m in models:
        new_status = auto_classify_endpoint_ref(m)
        old_status = m.get("endpoint_ref", None)
        changed = (old_status is None or old_status != new_status)
        result.append({
            "id": m["id"],
            "base_url_env": m.get("base_url_env", ""),
            "lifecycle_status": m.get("lifecycle_status", ""),
            "from": old_status,
            "to": new_status,
            "changed": changed,
        })
        if args.apply:
            m["endpoint_ref"] = new_status

    if args.apply:
        _save_pool(pool)
        status = "ok"
    else:
        status = "DRY_RUN"

    statuses: dict[str, int] = {}
    for r in result:
        s = r["to"]
        statuses[s] = statuses.get(s, 0) + 1
    changed_count = sum(1 for r in result if r["changed"])

    _output({
        "status": status,
        "total_models": len(result),
        "changed": changed_count,
        "endpoint_refs": statuses,
        "details": result,
        "message": "Auto-classified. Pass --apply to write."
            if status == "DRY_RUN"
            else f"Written {changed_count} endpoint_ref fields.",
    })
    return True


def cmd_validate_endpoint_ref(args):
    """Validate endpoint_ref across all models.

    Checks:
    - Allowed enum values
    - Lifecycle constraints:
      - enabled_assigned / operator_requested: must be base_url_env or unknown
        If missing/empty → WARN
      - declared_enabled_unassigned: any valid endpoint_ref → no error
      - disabled / historical / remove_pending: any valid endpoint_ref → ok

    No URL value read. No env var read.
    """
    pool = _load_pool()
    models = pool.get("models", [])

    errors = []
    warnings = []
    valid = set(ENDPOINT_REF_VALUES)

    for m in models:
        mid = m.get("id", "???")
        er = m.get("endpoint_ref", "")
        ls = m.get("lifecycle_status", "")

        # Check allowed values
        if er and er not in valid:
            errors.append({
                "model_id": mid,
                "field": "endpoint_ref",
                "issue": "INVALID_VALUE",
                "detail": f"endpoint_ref='{er}' not in {sorted(valid)}",
            })
            continue

        # Lifecycle constraints
        if ls in ("enabled_assigned", "operator_requested"):
            if not er:
                warnings.append({
                    "model_id": mid,
                    "lifecycle_status": ls,
                    "endpoint_ref": er,
                    "issue": "MISSING",
                    "detail": f"Active model '{mid}' has no endpoint_ref",
                })
            elif er == "missing":
                errors.append({
                    "model_id": mid,
                    "lifecycle_status": ls,
                    "endpoint_ref": er,
                    "issue": "REQUIRED_ENDPOINT_MISSING",
                    "detail": f"Active model '{mid}' endpoint_ref='{er}'",
                })
            elif er == "unknown":
                warnings.append({
                    "model_id": mid,
                    "lifecycle_status": ls,
                    "endpoint_ref": er,
                    "issue": "UNKNOWN_ENDPOINT",
                    "detail": f"Active model '{mid}' endpoint_ref=unknown (should audit)",
                })

        elif ls == "declared_enabled_unassigned":
            if not er:
                warnings.append({
                    "model_id": mid,
                    "lifecycle_status": ls,
                    "endpoint_ref": er,
                    "issue": "MISSING_OPTIONAL",
                    "detail": f"DEU model '{mid}' has no endpoint_ref (D-B pending, optional)",
                })
            elif er not in valid:
                errors.append({
                    "model_id": mid,
                    "issue": "INVALID_VALUE",
                    "detail": f"endpoint_ref='{er}' not in {sorted(valid)}",
                })

        else:
            # candidate, disabled, historical, remove_pending, or unknown lifecycle
            if not er:
                warnings.append({
                    "model_id": mid,
                    "lifecycle_status": ls,
                    "endpoint_ref": er,
                    "issue": "MISSING",
                    "detail": f"Model '{mid}' ({ls}) has no endpoint_ref",
                })
            elif er == "missing":
                warnings.append({
                    "model_id": mid,
                    "lifecycle_status": ls,
                    "endpoint_ref": er,
                    "issue": "UNEXPECTED_MISSING",
                    "detail": f"Model '{mid}' ({ls}) endpoint_ref='missing' (not required)",
                })

    _output({
        "status": "ok" if not errors else "ERRORS_FOUND",
        "total_models": len(models),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "note": "endpoint_ref is additive schema (Phase 3 PR-6). F6 readiness gate not affected.",
    })
    return len(errors) == 0


def cmd_generate_node_capability(args):
    """Generate scripts/node_model_capability.yaml from model_pool.yaml.

    The new file holds the complete G5 effective model-node matrix with
    12 entry fields (node context from YAML parent key). Six runtime/approval
    status fields are set to 'unknown'; no probe.
    """
    matrix, skipped, total = _build_node_matrix()
    yaml_text = _node_matrix_to_yaml(matrix, skipped, total)

    total_entries = sum(len(entries) for entries in matrix.values())

    if not args.apply:
        _output({
            "status": "DRY_RUN",
            "note": "G5 dry-run",
            "node_entry_counts": {n: len(matrix[n]) for n in ACTIVE_NODES},
            "total_entries": total_entries,
            "models_in_pool": total,
            "skipped_count": len(skipped),
            "skipped_ids": [s["id"] for s in skipped],
            "yaml_preview_lines": len(yaml_text.splitlines()),
            "message": "Pass --apply to write scripts/node_model_capability.yaml",
        })
        return True

    path = SCRIPTS_DIR / "node_model_capability.yaml"
    # Backup if exists
    if path.exists():
        backup = path.with_suffix(".yaml.bak")
        import shutil
        shutil.copy2(str(path), str(backup))

    with open(path, "w", encoding="utf-8") as f:
        f.write(yaml_text)

    _output({
        "status": "ok",
        "note": "G5 generate",
        "path": str(path),
        "node_entry_counts": {n: len(matrix[n]) for n in ACTIVE_NODES},
        "total_entries": total_entries,
        "models_in_pool": total,
        "skipped_count": len(skipped),
        "skipped_ids": [s["id"] for s in skipped],
        "message": "node_model_capability.yaml written.",
    })
    return True


def cmd_validate_node_capability(args):
    """Validate the node capability matrix.

    Checks schema_version, 12-entry-field completeness (node context from YAML key),
    'unknown' defaults for the 6 runtime/approval fields, and (optionally)
    cross-references all model_ids against model_pool.yaml.
    """
    path = SCRIPTS_DIR / "node_model_capability.yaml"
    if not path.exists():
        _output({"status": "ERROR", "message": f"File not found: {path}"})
        return False

    import yaml
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    errors = []
    warnings = []

    # Schema version
    sv = data.get("schema_version", "")
    if sv != "1.1":
        errors.append({"type": "SCHEMA_VERSION", "expected": "1.1", "actual": sv})

    # Node structure
    nodes = data.get("nodes", {})
    for node_name in ACTIVE_NODES:
        if node_name not in nodes:
            errors.append({"type": "MISSING_NODE", "node": node_name})
            continue
        nd = nodes[node_name]
        matrix = nd.get("matrix", [])
        for i, entry in enumerate(matrix):
            mid = entry.get("model_id", f"[index {i}]")
            # Check 12 entry fields present
            for fname in G5_ENTRY_FIELDS:
                if fname not in entry:
                    errors.append({
                        "type": "MISSING_FIELD", "node": node_name,
                        "model_id": mid, "field": fname, "index": i,
                    })
            # Check 6 unknown fields don't have bool
            for uf in G5_UNKNOWN_FIELDS:
                val = entry.get(uf)
                if isinstance(val, bool):
                    errors.append({
                        "type": "RUNTIME_FIELD_HAS_BOOL", "node": node_name,
                        "model_id": mid, "field": uf, "value": val, "index": i,
                    })
                elif val is None:
                    errors.append({
                        "type": "RUNTIME_FIELD_MISSING", "node": node_name,
                        "model_id": mid, "field": uf, "index": i,
                    })
                elif val != "unknown":
                    warnings.append({
                        "type": "RUNTIME_FIELD_UNEXPECTED", "node": node_name,
                        "model_id": mid, "field": uf, "value": val, "index": i,
                    })
            # Check primary_alias not empty
            pa = entry.get("primary_alias")
            if not pa or pa == "":
                errors.append({
                    "type": "MISSING_PRIMARY_ALIAS", "node": node_name,
                    "model_id": mid, "index": i,
                })
            # Check runtime_provider
            rp = entry.get("runtime_provider")
            expected_rp = NODE_RUNTIME_PROVIDER.get(node_name, "unknown")
            if rp != expected_rp:
                errors.append({
                    "type": "WRONG_RUNTIME_PROVIDER", "node": node_name,
                    "model_id": mid, "expected": expected_rp, "actual": rp, "index": i,
                })

    # Count stats
    total_entries = sum(len(nodes.get(n, {}).get("matrix", [])) for n in ACTIVE_NODES)
    total_models_in_pool = len(_load_pool().get("models", []))
    unknown_count_rv = sum(
        1 for n in ACTIVE_NODES
        for e in nodes.get(n, {}).get("matrix", [])
        if e.get("runtime_visible") == "unknown"
    )
    unknown_count_env = sum(
        1 for n in ACTIVE_NODES
        for e in nodes.get(n, {}).get("matrix", [])
        if e.get("env_loaded") == "unknown"
    )

    result = {
        "status": "ok" if not errors else "ERRORS_FOUND",
        "schema_version": sv,
        "total_entries": total_entries,
        "total_models_in_pool": total_models_in_pool,
        "nodes": {n: len(nodes.get(n, {}).get("matrix", [])) for n in ACTIVE_NODES},
        "runtime_visible_unknown": unknown_count_rv,
        "env_loaded_unknown": unknown_count_env,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
    }

    # Cross-reference (--cross-full)
    if args.cross_full:
        pool = _load_pool()
        pool_models = {m["id"]: m for m in pool.get("models", [])}
        cross_errors = []

        for node_name in ACTIVE_NODES:
            for i, entry in enumerate(nodes.get(node_name, {}).get("matrix", [])):
                mid = entry.get("model_id")
                pm = pool_models.get(mid)
                if not pm:
                    cross_errors.append({
                        "type": "MODEL_ID_NOT_IN_POOL", "node": node_name,
                        "model_id": mid, "index": i,
                    })
                    continue
                # Cross-check canonical_provider
                if entry.get("canonical_provider") != pm.get("canonical_provider"):
                    cross_errors.append({
                        "type": "CANONICAL_PROVIDER_MISMATCH", "node": node_name,
                        "model_id": mid,
                        "in_matrix": entry.get("canonical_provider"),
                        "in_pool": pm.get("canonical_provider"),
                    })
                if entry.get("provider_namespace") != pm.get("provider_namespace"):
                    cross_errors.append({
                        "type": "PROVIDER_NAMESPACE_MISMATCH", "node": node_name,
                        "model_id": mid,
                        "in_matrix": entry.get("provider_namespace"),
                        "in_pool": pm.get("provider_namespace"),
                    })
                if entry.get("primary_alias") != pm.get("primary_alias"):
                    cross_errors.append({
                        "type": "PRIMARY_ALIAS_MISMATCH", "node": node_name,
                        "model_id": mid,
                        "in_matrix": entry.get("primary_alias"),
                        "in_pool": pm.get("primary_alias"),
                    })

        result["cross_reference"] = {
            "status": "ok" if not cross_errors else "ERRORS_FOUND",
            "error_count": len(cross_errors),
            "errors": cross_errors,
        }
        all_errors = errors + cross_errors
        if all_errors:
            result["status"] = "ERRORS_FOUND"
            result["error_count"] = len(all_errors)

    _output(result)
    return result["status"] == "ok"


def main():
    parser = argparse.ArgumentParser(
        description="VibeDev Model Pool Manager CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              %(prog)s list --json
              %(prog)s add --id my-model --alias my --provider my --model my-v1 --key-env MY_KEY --nodes 5bao
              %(prog)s update my-model --notes "Updated notes" --dry-run
              %(prog)s update my-model --notes "New notes" --apply
              %(prog)s remove my-model --dry-run
              %(prog)s deprecate my-model --reason "EOL"
              %(prog)s validate-full
              %(prog)s freeze --output freeze.json
        """),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    p_list = sub.add_parser("list", help="List models (optionally filtered)")
    p_list.add_argument("--json", action="store_true", help="JSON output")
    p_list.add_argument("--lifecycle-status", help="Filter by lifecycle_status value")
    p_list.set_defaults(func=cmd_list)

    # add
    p_add = sub.add_parser("add", help="Add a new model")
    p_add.add_argument("--id", required=True, help="Unique model ID")
    p_add.add_argument("--alias", action="append", default=[], help="Alias(es)")
    p_add.add_argument("--provider", required=True, help="Provider (e.g. opencode-go)")
    p_add.add_argument("--model", required=True, help="Model name (e.g. deepseek-v4-flash)")
    p_add.add_argument("--key-env", required=True, help="Environment variable name for API key")
    p_add.add_argument("--base-url-env", help="Environment variable name for base URL")
    p_add.add_argument("--nodes", help="Comma-separated allowed nodes")
    p_add.add_argument("--cost", help="Cost tier")
    p_add.add_argument("--priority", type=int, help="Priority (higher = more preferred)")
    p_add.add_argument("--notes", help="Notes")
    p_add.add_argument("--capability-tags", help="Comma-separated tags")
    p_add.add_argument("--internal-provider-id", help="Internal provider ID for the worker")
    p_add.add_argument("--key-env-aliases", help="Comma-separated alternate key env names")
    p_add.add_argument("--smoke-required", help="Whether smoke is required (true/false)")
    p_add.add_argument("--lifecycle-status", help="lifecycle_status for the model (default: auto-classify)")
    p_add.set_defaults(func=cmd_add)

    # update
    p_upd = sub.add_parser("update", help="Update a model")
    p_upd.add_argument("id", help="Model ID to update")
    p_upd.add_argument("--provider", help="New provider")
    p_upd.add_argument("--model", help="New model name")
    p_upd.add_argument("--key-env", help="New key_env")
    p_upd.add_argument("--base-url-env", help="New base_url_env")
    p_upd.add_argument("--enable", action="store_true", help="Enable")
    p_upd.add_argument("--disable", action="store_true", help="Disable")
    p_upd.add_argument("--quarantine", action="store_true", help="Quarantine")
    p_upd.add_argument("--unquarantine", action="store_true", help="Un-quarantine")
    p_upd.add_argument("--nodes", help="Comma-separated allowed nodes")
    p_upd.add_argument("--notes", help="New notes")
    p_upd.add_argument("--priority", type=int, help="New priority")
    p_upd.add_argument("--cost", help="New cost tier")
    p_upd.add_argument("--capability-tags", help="Comma-separated capability tags")
    p_upd.add_argument("--internal-provider-id", help="New internal provider ID")
    p_upd.add_argument("--key-env-aliases", help="Comma-separated key env aliases")
    p_upd.add_argument("--smoke-required", help="Smoke required (true/false)")
    p_upd.add_argument("--lifecycle-status", help="New lifecycle_status")
    p_upd.add_argument("--add-alias", help="Add an alias")
    p_upd.add_argument("--remove-alias", help="Remove an alias")
    group_mode = p_upd.add_mutually_exclusive_group()
    group_mode.add_argument("--dry-run", action="store_true", help="Show changes (default)")
    group_mode.add_argument("--apply", action="store_true", help="Commit changes")
    p_upd.set_defaults(func=cmd_update)

    # remove
    p_rem = sub.add_parser("remove", help="Remove a model")
    p_rem.add_argument("id", help="Model ID to remove")
    p_rem.add_argument("--dry-run", action="store_true", help="Show impact without deleting")
    p_rem.add_argument("--force", action="store_true", help="Force remove even if VERIFIED")
    p_rem.add_argument("--reason", help="Reason for removal")
    p_rem.set_defaults(func=cmd_remove)

    # deprecate
    p_dep = sub.add_parser("deprecate", help="Deprecate a model (disable + quarantine)")
    p_dep.add_argument("id", help="Model ID to deprecate")
    p_dep.add_argument("--reason", help="Deprecation reason")
    p_dep.set_defaults(func=cmd_deprecate)

    # enable
    p_en = sub.add_parser("enable", help="Enable a model")
    p_en.add_argument("id", help="Model ID")
    p_en.set_defaults(func=cmd_enable)

    # disable
    p_dis = sub.add_parser("disable", help="Disable a model")
    p_dis.add_argument("id", help="Model ID")
    p_dis.set_defaults(func=cmd_disable)

    # validate-full
    p_val = sub.add_parser("validate-full", help="Run full validation")
    p_val.add_argument("--json", action="store_true", help="JSON output (default)")
    p_val.set_defaults(func=cmd_validate_full)

    # --- baseline01 G4 schema 1.1 validators (additive) ---
    # NOTE: legacy model entry uses `alias` as a list (e.g. - haiku); the
    # new schema 1.1 single-alias field is named `primary_alias` to avoid a
    # --- schema validators (additive) ---
    p_vschema = sub.add_parser("validate-schema", help="Validate schema_version >=1.1 + G4 field coverage + lifecycle_status")
    p_vschema.set_defaults(func=cmd_validate_schema)

    p_vbc = sub.add_parser("validate-backward-compat", help="Verify legacy provider/alias(list) fields are still readable")
    p_vbc.set_defaults(func=cmd_validate_backward_compat)

    p_sc = sub.add_parser("self-check", help="Top-level self-check: schema + coverage + backward compat")
    p_sc.set_defaults(func=cmd_self_check)

    # migrate: apply G4 schema 1.1 additive migration to model_pool.yaml.
    # Idempotent. Backward compatible (legacy fields preserved).
    p_mig = sub.add_parser("migrate", help="Apply G4 schema 1.1 additive migration in place")
    p_mig.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p_mig.add_argument("--apply", action="store_true", help="Apply migration to model_pool.yaml")
    p_mig.add_argument("--namespace-mapping", help="Optional path to alias->namespace mapping YAML")
    p_mig.set_defaults(func=cmd_migrate, dry_run=True, apply=False)

    # --- schema v1.2 lifecycle_status ---
    p_cls = sub.add_parser("classify", help="Auto-classify all models by lifecycle_status (schema v1.2)")
    p_cls.add_argument("--dry-run", action="store_true", help="Show changes without writing (default)")
    p_cls.add_argument("--apply", action="store_true", help="Write lifecycle_status to model_pool.yaml")
    p_cls.set_defaults(func=cmd_classify, dry_run=True, apply=False)

    # freeze
    p_frz = sub.add_parser("freeze", help="Generate capability freeze snapshot")
    p_frz.add_argument("--evidence", help="Path to credential evidence JSON")
    p_frz.add_argument("--output", help="Path to save the freeze JSON")
    p_frz.set_defaults(func=cmd_freeze)

    # sync
    p_syn = sub.add_parser("sync", help="Dry-run sync plan (contract only)")
    p_syn.add_argument("--nodes", help="Comma-separated target nodes")
    p_syn.set_defaults(func=cmd_sync)

    # --- baseline01 G5 node capability matrix ---
    p_gnc = sub.add_parser("generate-node-capability",
                           help="Generate scripts/node_model_capability.yaml from model_pool.yaml")
    p_gnc.add_argument("--dry-run", action="store_true", help="Show content without writing")
    p_gnc.add_argument("--apply", action="store_true", help="Write the file")
    p_gnc.set_defaults(func=cmd_generate_node_capability, g5_dry_run=True, g5_apply=False)

    p_vnc = sub.add_parser("validate-node-capability",
                           help="Validate the node capability matrix (schema + unknown defaults)")
    p_vnc.add_argument("--cross-full", action="store_true",
                       help="Also cross-reference all model_ids/providers against model_pool.yaml")
    p_vnc.set_defaults(func=cmd_validate_node_capability)

    # --- baseline02 Phase 3 PR-3: drift Layer 1 ---
    p_diff = sub.add_parser("diff", help="Drift Layer 1: pool ↔ matrix consistency (local-only)")
    p_diff.add_argument("--json", action="store_true", help="JSON output (default)")
    p_diff.set_defaults(func=cmd_diff)

    p_drift = sub.add_parser("drift", help="Same as 'diff'; fail-fast summary across all layers (currently Layer 1 only)")
    p_drift.add_argument("--json", action="store_true", help="JSON output (default)")
    p_drift.set_defaults(func=cmd_drift)

    # --- Phase 3 PR-5: credential_status schema ---
    p_cs = sub.add_parser("credential-status",
                          help="Auto-classify credential_status for all models (dry-run or --apply)")
    p_cs.add_argument("--dry-run", action="store_true", help="Show changes without writing (default)")
    p_cs.add_argument("--apply", action="store_true", help="Write credential_status to model_pool.yaml")
    p_cs.set_defaults(func=cmd_credential_status, dry_run=True, apply=False)

    p_vcs = sub.add_parser("validate-credential-status",
                           help="Validate credential_status across lifecycle constraints")
    p_vcs.set_defaults(func=cmd_validate_credential_status)

    # --- Phase 3 PR-6: endpoint_ref schema ---
    p_er = sub.add_parser("endpoint-ref",
                          help="Auto-classify endpoint_ref for all models (dry-run or --apply)")
    p_er.add_argument("--dry-run", action="store_true", help="Show changes without writing (default)")
    p_er.add_argument("--apply", action="store_true", help="Write endpoint_ref to model_pool.yaml")
    p_er.set_defaults(func=cmd_endpoint_ref, dry_run=True, apply=False)

    p_ver = sub.add_parser("validate-endpoint-ref",
                           help="Validate endpoint_ref across lifecycle constraints")
    p_ver.set_defaults(func=cmd_validate_endpoint_ref)

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as e:
        _error(str(e), "COMMAND_ERROR")


if __name__ == "__main__":
    main()
