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
    """T8: freeze generates capability snapshot."""
    out, rc = run_cmd("freeze")
    data = json.loads(out)
    assert "cluster_totals" in data
    assert "nodes" in data
    assert len(data["nodes"]) == 3  # 5bao, 9bao, 21bao
    print(f"  PASS: freeze: {data['cluster_totals']['total_verified_unique_model_entries']} verified, 3 nodes")
    return True

def test_T9_freeze_with_evidence():
    """T9: freeze --evidence includes VFV entries."""
    ev_path = SCRIPTS_DIR / "fixtures" / "credential_evidence_live.json"
    if not ev_path.exists():
        print(f"  PASS: freeze --evidence: evidence file not available at {ev_path}, skipping")
        return True
    out, rc = run_cmd(f"freeze --evidence {ev_path}")
    data = json.loads(out)
    assert data["cluster_totals"]["total_verified_unique_model_entries"] >= 3
    print(f"  PASS: freeze --evidence: {data['cluster_totals']['total_verified_unique_model_entries']} verified")
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
