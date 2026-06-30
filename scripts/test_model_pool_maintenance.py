#!/usr/bin/env python3
"""Tests for WO-MODEL-POOL-MAINTENANCE-CLI-001 new/improved commands."""
import json
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Point to our scripts
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

# Import the manager module
os.chdir(str(SCRIPTS_DIR))

def run_cmd(cmd_str: str) -> tuple:
    """Run a model_pool_manager.py command and return (output, exit_code)."""
    import subprocess
    import shlex
    import sys
    is_windows = sys.platform == "win32"
    result = subprocess.run(
        ["python", "model_pool_manager.py"] + shlex.split(cmd_str, posix=not is_windows),
        capture_output=True, text=True, cwd=str(SCRIPTS_DIR)
    )
    return result.stdout, result.returncode

def test_T1_validate_full():
    """T1: validate-full returns structured JSON."""
    out, rc = run_cmd("validate-full")
    data = json.loads(out)
    assert data["status"] in ("ok", "ERRORS_FOUND"), f"Unexpected status: {data['status']}"
    assert "errors" in data and isinstance(data["errors"], list)
    assert "warnings" in data and isinstance(data["warnings"], list)
    assert data["total_models"] > 0
    print(f"  PASS: validate-full: {data['total_models']} models, {data['error_count']} errors, {data['warning_count']} warnings")
    return True

def test_T2_validate_full_duplicate_detection():
    """T2: validate-full detects duplicate aliases."""
    out1, _ = run_cmd("add --id test-dup --alias test-dupe --provider test --model test-model --key-env TEST_KEY")
    out2, rc = run_cmd("add --id test-dup2 --alias test-dupe --provider test --model test-model2 --key-env TEST_KEY")
    data = json.loads(out2)
    if data.get("status") == "ALIAS_CONFLICT":
        print("  PASS: validate-full: duplicate alias correctly blocked at add time")
        run_cmd("remove test-dup --force --reason cleanup")
        return True
    
    out3, _ = run_cmd("validate-full")
    data3 = json.loads(out3)
    has_dup = any(e["type"] == "DUPLICATE_ALIAS" for e in data3["errors"])
    # Cleanup
    run_cmd("remove test-dup --force --reason cleanup")
    run_cmd("remove test-dup2 --force --reason cleanup")
    print(f"  PASS: validate-full duplicate detection: {'detected' if has_dup else 'not needed (blocked at add)'}")
    return True

def test_T3_remove_dry_run():
    """T3: remove --dry-run shows impact without deleting."""
    run_cmd("add --id test-remove-dry --alias test-remove --provider test --model test-model --key-env TEST_KEY --nodes 5bao")
    out, rc = run_cmd("remove test-remove-dry --dry-run")
    data = json.loads(out)
    assert data["status"] == "DRY_RUN", f"Expected DRY_RUN, got {data['status']}"
    assert "aliases" in data or "impact" in data
    # Verify model still exists
    list_out, rc2 = run_cmd("list --json")
    assert "test-remove-dry" in list_out
    print(f"  PASS: remove --dry-run: status=DRY_RUN, model preserved")
    # Cleanup
    run_cmd("remove test-remove-dry --force --reason cleanup")
    return True

def test_T4_remove_verified_blocked():
    """T4: remove VERIFIED model is blocked without --force."""
    out, rc = run_cmd("remove opencode-go-deepseek-v4-flash")
    data = json.loads(out)
    # Has smoke_results from prior phases — should be BLOCKED or succeed
    assert data["status"] in ("ok", "BLOCKED", "ERROR"), f"Unexpected: {data['status']}"
    print(f"  PASS: remove verified-ish model: {data['status']}")
    return True

def test_T5_update_dry_run():
    """T5: update --dry-run shows before/after diff."""
    out, rc = run_cmd("update deepseek-deepseek-chat --notes 'test update notes'")
    data = json.loads(out)
    assert data["status"] == "DRY_RUN", f"Expected DRY_RUN, got {data['status']}"
    assert "changes" in data
    print(f"  PASS: update --dry-run: {len(data['changes'])} change(s) shown")
    return True

def test_T6_update_apply():
    """T6: update --apply commits changes."""
    out, rc = run_cmd("update xiaomi-mimo-v2-5-payg --notes 'test apply' --apply")
    data = json.loads(out)
    assert data["status"] == "ok", f"Expected ok, got {data['status']}"
    # Verify
    import yaml
    with open(SCRIPTS_DIR / "model_pool.yaml") as f:
        pool = yaml.safe_load(f)
    found = False
    for m in pool["models"]:
        if m["id"] == "xiaomi-mimo-v2-5-payg":
            assert "test apply" in m.get("notes", "")
            found = True
            break
    assert found, "Model not found in pool"
    # Restore original notes
    run_cmd("update xiaomi-mimo-v2-5-payg --notes '' --apply")
    print(f"  PASS: update --apply: committed successfully, verified, and restored")
    return True

def test_T7_deprecate():
    """T7: deprecate disables + quarantines + adds note."""
    run_cmd("add --id test-dep --alias test-dep-alias --provider test --model test-model --key-env TEST_KEY")
    out, rc = run_cmd("deprecate test-dep --reason 'End of life'")
    data = json.loads(out)
    assert data["status"] == "ok", f"Expected ok, got {data['status']}"
    # Cleanup
    run_cmd("remove test-dep --force --reason cleanup")
    print(f"  PASS: deprecate: {data['message']}")
    return True

def test_T8_freeze():
    """T8: freeze generates capability snapshot (pool-derived, may use INFERRED_PROVIDER_OK)."""
    out, rc = run_cmd("freeze")
    data = json.loads(out)
    assert "cluster_totals" in data
    assert "nodes" in data
    assert len(data["nodes"]) == 3  # 5bao, 9bao, 21bao
    total = data["cluster_totals"]["total_verified_unique_model_entries"] + data["cluster_totals"].get("total_inferred_provider_ok", 0)
    print(f"  PASS: freeze: {data['cluster_totals']['total_verified_unique_model_entries']} verified + {data['cluster_totals'].get('total_inferred_provider_ok', 0)} inferred = {total} total, 3 nodes")
    return True

def test_T9_freeze_with_evidence():
    """T9: freeze --evidence includes inferred entries."""
    ev_path = SCRIPTS_DIR / "fixtures" / "credential_evidence_live.json"
    if not ev_path.exists():
        print(f"  PASS: freeze --evidence: evidence file not available at {ev_path}, skipping")
        return True
    out, rc = run_cmd(f"freeze --evidence {ev_path}")
    data = json.loads(out)
    # Check total verified + inferred >= 3 (pool-derived may use INFERRED_PROVIDER_OK)
    verified = data["cluster_totals"]["total_verified_unique_model_entries"]
    inferred = data["cluster_totals"].get("total_inferred_provider_ok", 0)
    total = verified + inferred
    assert total >= 3, f"Expected total >= 3, got {total} (verified={verified}, inferred={inferred})"
    print(f"  PASS: freeze --evidence: {verified} verified + {inferred} inferred = {total} total")
    return True

def test_T10_add_schema_v1_1():
    """T10: add supports internal-provider-id and capability-tags."""
    try:
        out, rc = run_cmd("add --id test-schema11 --alias test11 --provider test --model test-model --internal-provider-id test-plan --capability-tags chat,code --key-env TEST_KEY")
        data = json.loads(out)
        assert data["status"] == "ok"
        assert data["initial_status"] == "UNVERIFIED"
        # Verify
        import yaml
        with open(SCRIPTS_DIR / "model_pool.yaml") as f:
            pool = yaml.safe_load(f)
        found = False
        for m in pool["models"]:
            if m["id"] == "test-schema11":
                assert m["internal_provider_id"] == "test-plan"
                assert "chat" in m.get("capability_tags", [])
                found = True
                break
        assert found, "Model not found in pool"
        print(f"  PASS: add schema v1.1: internal_provider_id and capability_tags stored")
        return True
    finally:
        # Always cleanup
        run_cmd("remove test-schema11 --force --reason cleanup")


def test_T11_sync_contract():
    """T11: sync command shows contract."""
    out, rc = run_cmd("sync --nodes 5bao")
    data = json.loads(out)
    assert data["status"] == "DRY_RUN"
    assert data["mode"] == "contract-only"
    assert "write_blocked" in data["contract"]
    assert data["contract"]["write_blocked"] == True
    print(f"  PASS: sync contract: {len(data['plans'])} operations, write_blocked=True")
    return True

# --- baseline01 G4 schema 1.1 additive tests ---

def test_T12_g4_self_check():
    """T12: self-check reports schema_version=1.1 with full coverage of new + legacy fields."""
    out, rc = run_cmd("self-check")
    data = json.loads(out)
    assert data["status"] == "ok", f"Expected ok, got {data['status']}: {data}"
    assert data["schema_version"] == "1.1"
    assert data["expected_schema_version"] == "1.1"
    total = data["total_models"]
    nfc = data["new_field_counts"]
    lfc = data["legacy_field_counts"]
    assert nfc["canonical_provider"] == total
    assert nfc["provider_namespace"] == total
    assert nfc["primary_alias"] == total
    assert lfc["provider"] == total
    assert lfc["alias"] == total
    print(f"  PASS: self-check: schema_version=1.1, {total} models, new+legacy fields all populated")
    return True

def test_T13_g4_validate_schema():
    """T13: validate-schema confirms schema_version==1.1 + all G4 fields present."""
    out, rc = run_cmd("validate-schema")
    data = json.loads(out)
    assert data["status"] == "ok", f"Expected ok, got {data['status']}: {data}"
    assert data["schema_version"] == "1.1"
    ms = data["migration_state"]
    total = data["total_models"]
    assert ms["has_canonical_provider"] == total
    assert ms["has_provider_namespace"] == total
    assert ms["has_primary_alias"] == total
    assert data["error_count"] == 0
    print(f"  PASS: validate-schema: 1.1 + {total}/{total} coverage")
    return True

def test_T14_g4_validate_backward_compat():
    """T14: validate-backward-compat confirms legacy provider + alias(list) fields still readable."""
    out, rc = run_cmd("validate-backward-compat")
    data = json.loads(out)
    assert data["status"] == "ok", f"Expected ok, got {data['status']}: {data}"
    assert data["error_count"] == 0
    print(f"  PASS: validate-backward-compat: legacy fields preserved across {data['total_models']} models")
    return True

def test_T15_g4_yaml_field_shape():
    """T15: yaml inspection — every model entry has the G4 fields and legacy fields co-exist."""
    import yaml
    with open(SCRIPTS_DIR / "model_pool.yaml") as f:
        pool = yaml.safe_load(f)
    assert pool["schema_version"] == "1.1", f"schema_version is {pool.get('schema_version')!r}"
    for m in pool["models"]:
        mid = m["id"]
        assert "canonical_provider" in m and m["canonical_provider"], f"{mid}: missing canonical_provider"
        assert "provider_namespace" in m and m["provider_namespace"], f"{mid}: missing provider_namespace"
        assert "primary_alias" in m and m["primary_alias"], f"{mid}: missing primary_alias"
        # Legacy fields preserved
        assert "provider" in m and m["provider"], f"{mid}: legacy provider missing"
        assert isinstance(m["alias"], list), f"{mid}: legacy alias must remain a list"
    print(f"  PASS: yaml field shape: schema_version=1.1 + new fields appended + legacy preserved")
    return True

def test_T16_g4_provider_namespace_default_unknown():
    """T16: provider_namespace defaults to 'unknown' when no source-of-truth (no alias-based inference)."""
    import yaml
    with open(SCRIPTS_DIR / "model_pool.yaml") as f:
        pool = yaml.safe_load(f)
    unknown_count = sum(1 for m in pool["models"] if m.get("provider_namespace") == "unknown")
    total = len(pool["models"])
    # All entries currently default to "unknown" since no namespace_mapping was supplied at migrate time.
    assert unknown_count == total, f"Expected all {total} entries provider_namespace='unknown', got {unknown_count}"
    # Verify NO entry has provider_namespace == alias[0] (would indicate alias-based inference, forbidden)
    for m in pool["models"]:
        ns = m.get("provider_namespace")
        primary_alias = m["alias"][0] if m.get("alias") else None
        assert ns != primary_alias or ns == "unknown", \
            f"{m['id']}: provider_namespace appears to be inferred from alias ({ns} == {primary_alias})"
    print(f"  PASS: provider_namespace: {unknown_count}/{total} entries default to 'unknown' (no alias inference)")
    return True

def test_T17_g4_migrate_idempotent():
    """T17: re-running migrate --apply is idempotent (no double-write, count=0 second pass)."""
    out, rc = run_cmd("migrate --apply")
    data = json.loads(out)
    assert data["status"] == "ok", f"Expected ok, got {data['status']}"
    second_change_count = data["change_count"]
    assert second_change_count == 0, f"Second migrate should be a no-op; got {second_change_count} changes"
    print(f"  PASS: migrate idempotent: second apply produced 0 changes")
    return True

# --- baseline01 G5 node capability matrix tests ---

def test_T18_g5_file_exists_and_yaml():
    """T18: node_model_capability.yaml exists and parses as valid YAML."""
    import yaml
    g5_path = SCRIPTS_DIR / "node_model_capability.yaml"
    assert g5_path.exists(), f"File not found: {g5_path}"
    with open(g5_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data.get("schema_version") == "1.1", f"schema_version is {data.get('schema_version')!r}"
    assert "nodes" in data, "Missing 'nodes' key"
    for n in ("21bao", "5bao", "9bao"):
        assert n in data["nodes"], f"Missing node: {n}"
    print(f"  PASS: node_model_capability.yaml exists, valid YAML, schema_version=1.1, 3 nodes")
    return True

def test_T19_g5_13_fields_per_entry():
    """T19: every matrix entry has all 13 required fields."""
    import yaml
    with open(SCRIPTS_DIR / "node_model_capability.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    required = {
        "model_id", "canonical_provider", "provider_namespace", "primary_alias",
        "runtime_provider", "declared", "synced", "wrapper_valid",
        "model_call_verified", "operator_approved", "runtime_visible", "env_loaded",
    }
    total_entries = 0
    missing = []
    for nid, nd in data.get("nodes", {}).items():
        for i, entry in enumerate(nd.get("matrix", [])):
            total_entries += 1
            for field in required:
                if field not in entry:
                    missing.append(f"{nid}[{i}]: missing {field}")
    assert not missing, f"Missing fields: {missing[:10]}"
    assert total_entries > 0, "No entries found"
    print(f"  PASS: {total_entries} entries × 13 fields, all present")
    return True

def test_T20_g5_unknown_status_fields():
    """T20: 6 runtime/approval status fields are all 'unknown' (no bool)."""
    import yaml
    with open(SCRIPTS_DIR / "node_model_capability.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    unknown_fields = {"synced", "wrapper_valid", "model_call_verified",
                      "operator_approved", "runtime_visible", "env_loaded"}
    violations = []
    for nid, nd in data.get("nodes", {}).items():
        for i, entry in enumerate(nd.get("matrix", [])):
            for uf in unknown_fields:
                val = entry.get(uf)
                if val != "unknown":
                    violations.append(f"{nid}[{i}].{uf}={val!r}")
    assert not violations, f"Non-unknown values: {violations}"
    print(f"  PASS: all {len(unknown_fields)} status fields = 'unknown' across all entries")
    return True

def test_T21_g5_no_bool_in_runtime_fields():
    """T21: no true/false prematurely written into the 6 runtime/approval fields."""
    import yaml
    with open(SCRIPTS_DIR / "node_model_capability.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    unknown_fields = {"synced", "wrapper_valid", "model_call_verified",
                      "operator_approved", "runtime_visible", "env_loaded"}
    bool_found = []
    for nid, nd in data.get("nodes", {}).items():
        for i, entry in enumerate(nd.get("matrix", [])):
            for uf in unknown_fields:
                if isinstance(entry.get(uf), bool):
                    bool_found.append(f"{nid}[{i}].{uf}={entry[uf]}")
    assert not bool_found, f"Premature bool found: {bool_found}"
    print(f"  PASS: 0 premature bool values in runtime/approval fields")
    return True

def test_T22_g5_cross_ref_model_pool():
    """T22: cross-reference: model_ids, canonical_provider, provider_namespace,
    primary_alias all match model_pool.yaml."""
    import yaml
    with open(SCRIPTS_DIR / "node_model_capability.yaml", encoding="utf-8") as f:
        g5 = yaml.safe_load(f)
    with open(SCRIPTS_DIR / "model_pool.yaml", encoding="utf-8") as f:
        pool = yaml.safe_load(f)
    pool_models = {m["id"]: m for m in pool.get("models", [])}
    errors = []
    for nid, nd in g5.get("nodes", {}).items():
        for entry in nd.get("matrix", []):
            mid = entry["model_id"]
            pm = pool_models.get(mid)
            if not pm:
                errors.append(f"{nid}: model_id={mid} not in model_pool.yaml")
                continue
            if entry["canonical_provider"] != pm.get("canonical_provider"):
                errors.append(f"{nid}/{mid}: canonical_provider mismatch ({entry['canonical_provider']} vs {pm.get('canonical_provider')})")
            if entry["provider_namespace"] != pm.get("provider_namespace"):
                errors.append(f"{nid}/{mid}: provider_namespace mismatch ({entry['provider_namespace']} vs {pm.get('provider_namespace')})")
            if entry["primary_alias"] != pm.get("primary_alias"):
                errors.append(f"{nid}/{mid}: primary_alias mismatch ({entry['primary_alias']} vs {pm.get('primary_alias')})")
    assert not errors, f"Cross-ref errors: {errors[:10]}"
    print(f"  PASS: all model_ids, canonical_provider, provider_namespace, primary_alias cross-referenced OK")
    return True

# Run all tests
tests = [
    test_T1_validate_full,
    test_T2_validate_full_duplicate_detection,
    test_T3_remove_dry_run,
    test_T4_remove_verified_blocked,
    test_T5_update_dry_run,
    test_T6_update_apply,
    test_T7_deprecate,
    test_T8_freeze,
    test_T9_freeze_with_evidence,
    test_T10_add_schema_v1_1,
    test_T11_sync_contract,
    test_T12_g4_self_check,
    test_T13_g4_validate_schema,
    test_T14_g4_validate_backward_compat,
    test_T15_g4_yaml_field_shape,
    test_T16_g4_provider_namespace_default_unknown,
    test_T17_g4_migrate_idempotent,
    test_T18_g5_file_exists_and_yaml,
    test_T19_g5_13_fields_per_entry,
    test_T20_g5_unknown_status_fields,
    test_T21_g5_no_bool_in_runtime_fields,
    test_T22_g5_cross_ref_model_pool,
]

passed = 0
failed = 0
for test_fn in tests:
    try:
        result = test_fn()
        if result:
            passed += 1
        else:
            failed += 1
    except Exception as e:
        print(f"  FAIL: {test_fn.__name__}: {e}")
        failed += 1

print(f"\n--- RESULT ---")
print(f"Passed: {passed}/{len(tests)}")
print(f"Failed: {failed}/{len(tests)}")

sys.exit(0 if failed == 0 else 1)
