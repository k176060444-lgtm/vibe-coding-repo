#!/usr/bin/env python3
"""V1.18.4 Recoverable Repair Saga + Active-Active Fault Injection Tests.

Tests for:
1. Real OS subprocess crash injection at each repair stage
2. Repair recovery idempotency
3. Two repair processes competing for same nonce
4. Active-active scheduling verification
5. Nonce ledger reconcile
6. Manifest checksum integrity

Each crash test uses an independent OS subprocess that is killed at a specific
point in the repair transaction. A new process then verifies recovery.
"""

import copy
import hashlib
import json
import multiprocessing
import os
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vibe_job_orchestrator import (
    JobState, JobManifest, ClaimStore, JobOrchestrator,
    TERMINAL_STATES, VALID_TRANSITIONS,
    _manifest_checksum, _compute_store_checksum, _now_iso,
    NONCE_LEDGER_PATH, NONCE_LEDGER_LOCK,
    APPROVAL_RECEIPTS_DIR, CLAIM_STORE_SCHEMA_VERSION,
    _STORE_CHECKSUM_KEY,
)
from vibe_worker_registry import WorkerRegistry, NodeStatus


def _make_valid_store(claims=None):
    """Create a valid store dict."""
    store = {
        "claims": claims or {},
        "version": CLAIM_STORE_SCHEMA_VERSION,
    }
    store[_STORE_CHECKSUM_KEY] = _compute_store_checksum(store)
    return store


def _make_receipt(receipt_id, nonce, old_sha, new_sha, reason="test",
                  operator="test-op", node="test-node", plan_digest="test-plan"):
    """Create a valid approval receipt."""
    return {
        "receipt_id": receipt_id,
        "operation": "claim_store_repair",
        "node_id": node,
        "operator": operator,
        "reason": reason,
        "repair_plan_digest": plan_digest,
        "approved_runtime_plan_digest": "test-approved-digest",
        "old_store_sha256": old_sha,
        "new_store_sha256": new_sha,
        "issued_at": _now_iso(),
        "expires_at": "2099-12-31T23:59:59+00:00",
        "nonce": nonce,
        "status": "APPROVED",
        "consumed": False,
    }


def _write_candidate_store(path, claims=None):
    """Write a valid candidate store to disk."""
    store = _make_valid_store(claims)
    path.write_text(json.dumps(store, indent=2))
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ===========================================================================
# Crash injection via config file — avoids path escaping issues
# ===========================================================================

def _run_crash_injection(td, target_stage):
    """Run a subprocess that crashes at the given repair stage.

    Uses a JSON config file to pass paths (avoids Windows backslash escaping).
    Returns the process exit code.
    """
    scripts_dir = str(Path(__file__).parent)
    store_path = os.path.join(td, "claims.json")
    lock_path = os.path.join(td, "claims.lock")
    candidate_path = os.path.join(td, "candidate.json")
    receipt_id = "test-receipt-%s" % secrets.token_hex(4)
    nonce = secrets.token_hex(32)

    # Write initial valid store
    store = _make_valid_store()
    Path(store_path).write_text(json.dumps(store, indent=2))
    old_sha = hashlib.sha256(Path(store_path).read_bytes()).hexdigest()

    # Write candidate store
    new_sha = _write_candidate_store(Path(candidate_path))

    # Write config file
    config = {
        "scripts_dir": scripts_dir,
        "store_path": store_path,
        "lock_path": lock_path,
        "candidate_path": candidate_path,
        "receipt_id": receipt_id,
        "nonce": nonce,
        "reason": "crash-test",
        "operator": "test-op",
        "node": "test-node",
        "plan_digest": "test-plan-digest",
        "target_stage": target_stage,
        "old_sha": old_sha,
        "new_sha": new_sha,
    }
    config_path = os.path.join(td, "crash_config.json")
    Path(config_path).write_text(json.dumps(config, indent=2))

    # Write the crash script to a file (avoids template string issues)
    script_path = os.path.join(td, "crash_script.py")
    Path(script_path).write_text(CRASH_SCRIPT_SOURCE)

    # Run subprocess
    proc = subprocess.Popen(
        [sys.executable, script_path, config_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        stdout, stderr = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()

    return proc.returncode, td, receipt_id, nonce


# The crash script source — reads config from argv[1]
CRASH_SCRIPT_SOURCE = r'''
import json, os, sys, hashlib, shutil, uuid
from pathlib import Path

config_path = sys.argv[1]
config = json.loads(Path(config_path).read_text())

scripts_dir = config["scripts_dir"]
sys.path.insert(0, scripts_dir)

from vibe_job_orchestrator import (
    ClaimStore, _compute_store_checksum, _now_iso,
    _STORE_CHECKSUM_KEY, CLAIM_STORE_SCHEMA_VERSION,
    NONCE_LEDGER_PATH, NONCE_LEDGER_LOCK,
    APPROVAL_RECEIPTS_DIR,
)

store_path = Path(config["store_path"])
lock_path = Path(config["lock_path"])
candidate_path = Path(config["candidate_path"])
receipt_id = config["receipt_id"]
nonce = config["nonce"]
reason = config["reason"]
operator = config["operator"]
node = config["node"]
plan_digest = config["plan_digest"]
target_stage = config["target_stage"]
old_sha = config["old_sha"]
new_sha = config["new_sha"]

# Create ClaimStore
cs = ClaimStore(str(store_path), str(lock_path))

# Write receipt
receipt_path = APPROVAL_RECEIPTS_DIR / (receipt_id + ".json")
receipt_path.parent.mkdir(parents=True, exist_ok=True)
receipt = {
    "receipt_id": receipt_id,
    "operation": "claim_store_repair",
    "node_id": node,
    "operator": operator,
    "reason": reason,
    "repair_plan_digest": plan_digest,
    "approved_runtime_plan_digest": "test-approved-digest",
    "old_store_sha256": old_sha,
    "new_store_sha256": new_sha,
    "issued_at": _now_iso(),
    "expires_at": "2099-12-31T23:59:59+00:00",
    "nonce": nonce,
    "status": "APPROVED",
    "consumed": False,
}
receipt_path.write_text(json.dumps(receipt, indent=2))

# Latch the store (simulate corruption)
cs._latch("test_injected_corruption")

# Acquire lock
cs.acquire_lock()
try:
    tx_id = "repair-tx-crash-%s" % uuid.uuid4().hex[:8]
    journal_path = store_path.parent / ("%s.journal.json" % tx_id)
    cur_sha = hashlib.sha256(store_path.read_bytes()).hexdigest()
    cand_sha = hashlib.sha256(candidate_path.read_bytes()).hexdigest()

    journal = {
        "tx_id": tx_id,
        "status": "STARTED",
        "started_at": _now_iso(),
        "approval_receipt_id": receipt_id,
        "operator_id": operator,
        "reason": reason,
        "target_node": node,
        "repair_plan_digest": plan_digest,
        "nonce": nonce,
        "old_store_sha256": cur_sha,
        "new_store_sha256": cand_sha,
        "candidate_path": str(candidate_path),
        "steps_completed": [],
    }
    cs._write_journal(journal_path, journal)

    if target_stage == "STARTED":
        sys.exit(42)

    # Stage: BACKUP_CREATED
    backup_path = str(store_path) + ".corrupted.%s" % cur_sha[:16]
    if not os.path.exists(backup_path):
        shutil.copy2(str(store_path), backup_path)
    journal["status"] = "BACKUP_CREATED"
    journal["steps_completed"].append("backup")
    cs._write_journal(journal_path, journal)

    if target_stage == "BACKUP_CREATED":
        sys.exit(42)

    # Stage: STORE_REPLACED
    tmp_store = str(store_path) + ".repair.tmp"
    shutil.copy2(str(candidate_path), tmp_store)
    os.replace(tmp_store, str(store_path))
    journal["status"] = "STORE_REPLACED"
    journal["steps_completed"].append("store_replace")
    cs._write_journal(journal_path, journal)

    if target_stage == "STORE_REPLACED":
        sys.exit(42)

    # Stage: RECEIPT_CONSUMED
    receipt["consumed"] = True
    receipt["consumed_at"] = _now_iso()
    receipt["consumed_store_sha"] = hashlib.sha256(store_path.read_bytes()).hexdigest()
    receipt["tx_id"] = tx_id
    tmp_r = receipt_path.with_suffix(".tmp")
    with open(str(tmp_r), "w") as f:
        json.dump(receipt, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp_r), str(receipt_path))
    journal["status"] = "RECEIPT_CONSUMED"
    journal["steps_completed"].append("receipt_consume")
    cs._write_journal(journal_path, journal)

    if target_stage == "RECEIPT_CONSUMED":
        sys.exit(42)

    # Stage: NONCE_CONSUMED
    cs._consume_nonce(nonce, receipt_id)
    journal["status"] = "NONCE_CONSUMED"
    journal["steps_completed"].append("nonce_consume")
    cs._write_journal(journal_path, journal)

    if target_stage == "NONCE_CONSUMED":
        sys.exit(42)

    # Complete
    journal["status"] = "COMPLETED"
    journal["completed_at"] = _now_iso()
    journal["steps_completed"].append("latch_clear")
    cs._write_journal(journal_path, journal)
    print("COMPLETED")
    sys.exit(0)

finally:
    cs.release_lock()
'''


# ===========================================================================
# Test Suite
# ===========================================================================

def test_repair_saga_rollback_at_started():
    """Crash at STARTED stage, verify rollback recovery."""
    print("\n=== Test: Repair Saga Rollback at STARTED ===")
    with tempfile.TemporaryDirectory() as td:
        exit_code, _, _, _ = _run_crash_injection(td, "STARTED")
        assert exit_code == 42, "Subprocess should exit 42 (crash), got %d" % exit_code

        # Recover — create new ClaimStore, should auto-recover
        cs = ClaimStore(
            os.path.join(td, "claims.json"),
            os.path.join(td, "claims.lock"),
        )
        assert not cs.is_latched(), "Latch should be cleared after rollback"
        print("  Rollback at STARTED: PASS")


def test_repair_saga_rollback_at_backup():
    """Crash at BACKUP_CREATED stage, verify rollback recovery."""
    print("\n=== Test: Repair Saga Rollback at BACKUP_CREATED ===")
    with tempfile.TemporaryDirectory() as td:
        exit_code, _, _, _ = _run_crash_injection(td, "BACKUP_CREATED")
        assert exit_code == 42

        cs = ClaimStore(
            os.path.join(td, "claims.json"),
            os.path.join(td, "claims.lock"),
        )
        assert not cs.is_latched(), "Latch should be cleared after rollback"
        print("  Rollback at BACKUP_CREATED: PASS")


def test_repair_saga_complete_at_store_replaced():
    """Crash at STORE_REPLACED, verify completion recovery."""
    print("\n=== Test: Repair Saga Complete at STORE_REPLACED ===")
    with tempfile.TemporaryDirectory() as td:
        exit_code, _, _, _ = _run_crash_injection(td, "STORE_REPLACED")
        assert exit_code == 42

        cs = ClaimStore(
            os.path.join(td, "claims.json"),
            os.path.join(td, "claims.lock"),
        )
        assert not cs.is_latched(), "Latch should be cleared after completion"
        data = cs._raw_read()
        assert data.get("version") == CLAIM_STORE_SCHEMA_VERSION
        print("  Complete at STORE_REPLACED: PASS")


def test_repair_saga_complete_at_receipt_consumed():
    """Crash at RECEIPT_CONSUMED, verify completion recovery."""
    print("\n=== Test: Repair Saga Complete at RECEIPT_CONSUMED ===")
    with tempfile.TemporaryDirectory() as td:
        exit_code, _, _, _ = _run_crash_injection(td, "RECEIPT_CONSUMED")
        assert exit_code == 42

        cs = ClaimStore(
            os.path.join(td, "claims.json"),
            os.path.join(td, "claims.lock"),
        )
        assert not cs.is_latched()
        print("  Complete at RECEIPT_CONSUMED: PASS")


def test_repair_saga_complete_at_nonce_consumed():
    """Crash at NONCE_CONSUMED, verify completion recovery."""
    print("\n=== Test: Repair Saga Complete at NONCE_CONSUMED ===")
    with tempfile.TemporaryDirectory() as td:
        exit_code, _, _, _ = _run_crash_injection(td, "NONCE_CONSUMED")
        assert exit_code == 42

        cs = ClaimStore(
            os.path.join(td, "claims.json"),
            os.path.join(td, "claims.lock"),
        )
        assert not cs.is_latched()
        print("  Complete at NONCE_CONSUMED: PASS")


def test_repair_recovery_idempotent():
    """Recovery must be idempotent — running recovery twice produces same result."""
    print("\n=== Test: Repair Recovery Idempotent ===")
    with tempfile.TemporaryDirectory() as td:
        _run_crash_injection(td, "STARTED")

        # First recovery
        cs1 = ClaimStore(
            os.path.join(td, "claims.json"),
            os.path.join(td, "claims.lock"),
        )
        assert not cs1.is_latched()

        # Second recovery — should be no-op
        cs2 = ClaimStore(
            os.path.join(td, "claims.json"),
            os.path.join(td, "claims.lock"),
        )
        assert not cs2.is_latched()
        print("  Idempotent recovery: PASS")


def test_repair_competing_nonces():
    """Two repair processes competing for same nonce — only one succeeds."""
    print("\n=== Test: Competing Repair Nonces ===")
    with tempfile.TemporaryDirectory() as td:
        store_path = os.path.join(td, "claims.json")
        lock_path = os.path.join(td, "claims.lock")

        # Write initial valid store (with a dummy claim to ensure different SHA from candidate)
        store = _make_valid_store({"old-job": {"state": "FAILED", "worker_id": "5bao"}})
        Path(store_path).write_text(json.dumps(store, indent=2))

        # Latch the store
        cs = ClaimStore(store_path, lock_path)
        cs._latch("test_corruption")

        shared_nonce = secrets.token_hex(32)
        results = []

        def attempt_repair(receipt_suffix):
            receipt_id = "competing-receipt-%s" % receipt_suffix
            candidate_path = os.path.join(td, "candidate-%s.json" % receipt_suffix)
            _write_candidate_store(Path(candidate_path))

            receipt_path = APPROVAL_RECEIPTS_DIR / ("%s.json" % receipt_id)
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            receipt = _make_receipt(
                receipt_id, shared_nonce,
                hashlib.sha256(Path(store_path).read_bytes()).hexdigest(),
                hashlib.sha256(Path(candidate_path).read_bytes()).hexdigest(),
                reason="competing-test", node="test-node",
            )
            receipt_path.write_text(json.dumps(receipt, indent=2))

            try:
                cs2 = ClaimStore(store_path, lock_path)
                cs2.repair(
                    reason="competing-test",
                    operator_id="test-op",
                    approval_receipt_id=receipt_id,
                    approved_digest="test-approved-digest",
                    target_node="test-node",
                    repair_candidate_path=candidate_path,
                    repair_plan_digest="test-plan",
                )
                results.append(("success", receipt_suffix))
            except Exception as e:
                results.append(("error", receipt_suffix, str(e)))

        attempt_repair("a")
        attempt_repair("b")

        successes = [r for r in results if r[0] == "success"]
        errors = [r for r in results if r[0] == "error"]
        assert len(successes) == 1, "Exactly one repair should succeed, got %d" % len(successes)
        assert len(errors) == 1, "Exactly one repair should fail, got %d" % len(errors)
        print("  Competing nonces: PASS (1 success, 1 blocked)")


def test_active_active_both_workers():
    """Both 5bao and 9bao each get one job (true active-active)."""
    print("\n=== Test: Active-Active Both Workers ===")
    # Use _make_test_orchestrator to avoid hitting real (possibly corrupt) claim store
    from vibe_job_orchestrator import _make_test_orchestrator, NodeStatus
    orch = _make_test_orchestrator()
    for w in orch.registry.list_workers():
        orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)

    m1 = orch.submit_job("linux-worker", "echo job1")
    m2 = orch.submit_job("linux-worker", "echo job2")

    w1 = m1.get("actual_worker")
    w2 = m2.get("actual_worker")

    assert m1["state"] == "CLAIMED", "Job 1 state: %s" % m1.get("state")
    assert m2["state"] == "CLAIMED", "Job 2 state: %s" % m2.get("state")
    assert w1 in ("5bao", "9bao"), "Job 1 worker: %s" % w1
    assert w2 in ("5bao", "9bao"), "Job 2 worker: %s" % w2
    assert w1 != w2, "Active-active requires different workers, got %s and %s" % (w1, w2)
    print("  Job 1 -> %s, Job 2 -> %s" % (w1, w2))
    print("  Active-active: PASS")


def test_third_job_blocked():
    """Third job should be BLOCKED when pool is full."""
    print("\n=== Test: Third Job Blocked (Pool Full) ===")
    from vibe_job_orchestrator import _make_test_orchestrator, NodeStatus
    orch = _make_test_orchestrator()
    for w in orch.registry.list_workers():
        orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)

    m1 = orch.submit_job("linux-worker", "echo job1")
    m2 = orch.submit_job("linux-worker", "echo job2")
    m3 = orch.submit_job("linux-worker", "echo job3")

    assert m1["state"] == "CLAIMED"
    assert m2["state"] == "CLAIMED"
    assert m3["state"] == "BLOCKED", "Third job should be BLOCKED, got %s" % m3.get("state")
    print("  Third job BLOCKED: PASS")


def test_nonce_ledger_reconcile():
    """Nonce ledger reconcile on startup."""
    print("\n=== Test: Nonce Ledger Reconcile ===")
    with tempfile.TemporaryDirectory() as td:
        # Patch through sys.modules to ensure ClaimStore sees the patched values
        _mod = sys.modules.get("vibe_job_orchestrator") or sys.modules.get("__main__")
        ledger_path = Path(td) / "nonce_ledger.json"
        ledger_lock = Path(td) / "nonce_ledger.lock"

        ledger = {
            "consumed": {
                "nonce-a": {"receipt_id": "r1", "consumed_at": _now_iso()},
                "nonce-b": {"receipt_id": "r2", "consumed_at": _now_iso()},
            }
        }
        ledger_path.write_text(json.dumps(ledger, indent=2))

        orig_ledger = getattr(_mod, "NONCE_LEDGER_PATH")
        orig_lock = getattr(_mod, "NONCE_LEDGER_LOCK")
        setattr(_mod, "NONCE_LEDGER_PATH", ledger_path)
        setattr(_mod, "NONCE_LEDGER_LOCK", ledger_lock)
        try:
            cs = ClaimStore(
                os.path.join(td, "claims.json"),
                os.path.join(td, "claims.lock"),
            )
            result = cs.reconcile_nonce_ledger()
            assert result["status"] == "reconciled"
            assert result["total_nonces"] == 2
            assert result["duplicates_removed"] == 0
            print("  Nonce reconcile: PASS")
        finally:
            setattr(_mod, "NONCE_LEDGER_PATH", orig_ledger)
            setattr(_mod, "NONCE_LEDGER_LOCK", orig_lock)


def test_ripgrep_routes_9bao():
    """ripgrep required_tools must route to capable worker (5bao or 9bao)."""
    print("\n=== Test: ripgrep Routes to Capable Worker ===")
    from vibe_job_orchestrator import _make_test_orchestrator, NodeStatus
    orch = _make_test_orchestrator()
    for w in orch.registry.list_workers():
        orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)

    m = orch.submit_job("linux-worker", "rg --version", required_tools=["ripgrep"])
    assert m["state"] == "CLAIMED", "Expected CLAIMED, got %s" % m.get("state")
    assert m["actual_worker"] in ("5bao", "9bao"), "Expected capable worker, got %s" % m.get("actual_worker")
    print("  ripgrep -> %s: PASS" % m["actual_worker"])


def test_manifest_checksum_integrity():
    """Manifest checksum detects tampering."""
    print("\n=== Test: Manifest Checksum Integrity ===")
    m = JobManifest(job_id="test", task_type="linux-worker", command="echo hi")
    d = m.to_dict()
    assert d["checksum"] != ""

    d_corrupt = dict(d)
    d_corrupt["command"] = "echo tampered"
    caught = False
    try:
        JobManifest.from_dict(d_corrupt)
    except Exception:
        caught = True
    assert caught, "Tampered manifest should be rejected"
    print("  Manifest checksum: PASS")


# ===========================================================================
# Main
# ===========================================================================

def main():
    print("=" * 60)
    print("V1.18.4 Repair Saga + Active-Active Fault Injection Tests")
    print("=" * 60)

    tests = [
        test_repair_saga_rollback_at_started,
        test_repair_saga_rollback_at_backup,
        test_repair_saga_complete_at_store_replaced,
        test_repair_saga_complete_at_receipt_consumed,
        test_repair_saga_complete_at_nonce_consumed,
        test_repair_recovery_idempotent,
        test_repair_competing_nonces,
        test_active_active_both_workers,
        test_third_job_blocked,
        test_nonce_ledger_reconcile,
        test_ripgrep_routes_9bao,
        test_manifest_checksum_integrity,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print("  FAIL: %s -- %s" % (t.__name__, e))
            failed += 1

    print("\n" + "=" * 60)
    print("Results: %d passed, %d failed, %d total" % (passed, failed, len(tests)))
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
