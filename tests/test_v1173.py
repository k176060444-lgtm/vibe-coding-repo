#!/usr/bin/env python3
"""V1.17.3 Integration Tests — real gate, real lifecycle, real concurrency."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import multiprocessing
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from vibe_toolchain_lifecycle import (
    __version__, StateStore, CorruptionLatch, DriftEvent, DriftEventStatus,
    DriftType, RuntimeFingerprint, DriftDetector, DriftClassifier,
    RemediationPlanner, RemediationAction, PlanRecord, PlanStatus,
    SchedulerGate, ToolchainLifecycleManager, gate_check_for_dispatch,
    dispatch_check_write_operation, SSH_OPTS,
)
from vibe_worker_registry import WorkerRegistry, WorkerNode, NodeStatus


def _make_tmp():
    d = tempfile.mkdtemp(prefix="v1173test_")
    return d

def _cleanup(d):
    shutil.rmtree(d, ignore_errors=True)

def _make_store(d):
    store = StateStore(
        os.path.join(d, "state.json"),
        os.path.join(d, "state.lock"),
        os.path.join(d, "latch.json"),
    )
    store.bootstrap()
    return store

def _make_mgr(d, store=None):
    if store is None:
        store = _make_store(d)
    return ToolchainLifecycleManager(state_path=os.path.join(d, "state.json"),
                                     lock_path=os.path.join(d, "state.lock"),
                                     latch_path=os.path.join(d, "latch.json"))

def _seed_approved(store, node_id="5bao"):
    fp = RuntimeFingerprint(
        node_id=node_id, hostname=f"{node_id}-test", ssh_reachable=True,
        components={"opencode": {"version": "1.17.4", "binary_hash": "abc"}},
        path_dirs=["/usr/bin", "/home/test/.local/bin"],
    )
    store.set_approved(node_id, fp.to_dict(), frozen_by="test")
    return fp

def _make_plan_with_digest(mgr, store, node_id="5bao", plan_id="P-test"):
    approved = store.get_approved(node_id)
    before_sha = approved.get("sha256", "") if approved else ""
    plan = PlanRecord(
        plan_id=plan_id, node_id=node_id,
        drift_type=DriftType.PATCH_VERSION_DRIFT,
        status=PlanStatus.PENDING_APPROVAL,
        actions=[RemediationAction.AUTO_FIX],
        before_fingerprint_sha=before_sha,
    )
    plan.plan_digest = hashlib.sha256(json.dumps({
        "actions": [a.value for a in plan.actions],
        "node_id": node_id,
        "drift_type": plan.drift_type.value,
    }, sort_keys=True).encode()).hexdigest()
    store.add_plan(plan)
    return plan


# === Test 1: Two concurrent processes race state.lock, no event loss ===
def test_concurrent_lock_no_loss():
    d = _make_tmp()
    try:
        store = _make_store(d)
        store.load()
        n_events = 50
        def writer(store_path, lock_path, latch_path, start_idx, count):
            s = StateStore(store_path, lock_path, latch_path)
            for i in range(count):
                evt = DriftEvent(
                    event_id=f"evt-{start_idx + i}",
                    node_id="5bao",
                    detected_at=datetime.now(timezone.utc).isoformat(),
                    drift_type=DriftType.PATCH_VERSION_DRIFT,
                    status=DriftEventStatus.DETECTED,
                    resolution=f"concurrent-{start_idx + i}",
                )
                s.add_event(evt)

        sp = os.path.join(d, "state.json")
        lp = os.path.join(d, "state.lock")
        latchp = os.path.join(d, "latch.json")
        p1 = multiprocessing.Process(target=writer, args=(sp, lp, latchp, 0, n_events))
        p2 = multiprocessing.Process(target=writer, args=(sp, lp, latchp, n_events, n_events))
        p1.start()
        p2.start()
        p1.join(timeout=30)
        p2.join(timeout=30)
        assert p1.exitcode == 0, f"p1 exit={p1.exitcode}"
        assert p2.exitcode == 0, f"p2 exit={p2.exitcode}"

        final = StateStore(sp, lp, latchp).load()
        stored_ids = {e["event_id"] for e in final.get("events", [])}
        expected = {f"evt-{i}" for i in range(n_events * 2)}
        missing = expected - stored_ids
        assert len(missing) == 0, f"Lost events: {len(missing)}/{len(expected)}"
    finally:
        _cleanup(d)


# === Test 2: Corruption latch blocks scheduler dispatch ===
def test_corruption_latch_blocks_scheduler():
    d = _make_tmp()
    try:
        store = _make_store(d)
        store.load()
        _seed_approved(store)
        gate = SchedulerGate(store)
        assert gate.is_writes_allowed()["allowed"]

        store.latch.latch("test_corruption")
        result = gate.is_writes_allowed()
        assert not result["allowed"]
        assert "corruption" in result["reason"]

        # Verify via SchedulerGate (uses same store instance)
        assert store.latch.is_latched()
        assert not gate.is_writes_allowed()["allowed"]
    finally:
        _cleanup(d)


# === Test 3: SECRET_DRIFT blocks dispatch ===
def test_secret_drift_blocks_dispatch():
    d = _make_tmp()
    try:
        store = _make_store(d)
        store.load()
        _seed_approved(store)
        gate = SchedulerGate(store)
        assert gate.is_writes_allowed()["allowed"]

        evt = DriftEvent(
            event_id="sec-1", node_id="5bao",
            detected_at=datetime.now(timezone.utc).isoformat(),
            drift_type=DriftType.SECRET_DRIFT,
            status=DriftEventStatus.DETECTED,
            resolution="secret_changed",
        )
        store.add_event(evt)

        result = gate.is_writes_allowed()
        assert not result["allowed"]
        assert "secret" in result["reason"]
    finally:
        _cleanup(d)


# === Test 4: Dual UNKNOWN blocks dispatch ===
def test_dual_unknown_blocks_dispatch():
    d = _make_tmp()
    try:
        store = _make_store(d)
        store.load()
        _seed_approved(store, "5bao")
        _seed_approved(store, "9bao")
        gate = SchedulerGate(store)

        for node in ("5bao", "9bao"):
            evt = DriftEvent(
                event_id=f"unk-{node}", node_id=node,
                detected_at=datetime.now(timezone.utc).isoformat(),
                drift_type=DriftType.UNKNOWN_DRIFT,
                status=DriftEventStatus.DETECTED,
                resolution="unknown",
            )
            store.add_event(evt)

        result = gate.is_writes_allowed()
        assert not result["allowed"]
        assert "unknown" in result["reason"]
    finally:
        _cleanup(d)


# === Test 5: Single UNKNOWN with other free → allowed ===
def test_single_unknown_other_free():
    d = _make_tmp()
    try:
        store = _make_store(d)
        store.load()
        _seed_approved(store, "5bao")
        _seed_approved(store, "9bao")
        gate = SchedulerGate(store)

        evt = DriftEvent(
            event_id="unk-5bao", node_id="5bao",
            detected_at=datetime.now(timezone.utc).isoformat(),
            drift_type=DriftType.UNKNOWN_DRIFT,
            status=DriftEventStatus.DETECTED,
            resolution="unknown",
        )
        store.add_event(evt)

        result = gate.is_writes_allowed()
        assert result["allowed"]
    finally:
        _cleanup(d)


# === Test 6: freeze without plan/approval blocks ===
def test_freeze_requires_plan():
    d = _make_tmp()
    try:
        mgr = _make_mgr(d)
        result = mgr.freeze("5bao")
        assert not result["ok"]
        assert result["error"] == "plan_and_approval_required"
    finally:
        _cleanup(d)


# === Test 7: adopt without plan/approval blocks ===
def test_adopt_requires_plan():
    d = _make_tmp()
    try:
        store = _make_store(d)
        store.load()
        _seed_approved(store)
        mgr = _make_mgr(d, store)
        fp = RuntimeFingerprint(
            node_id="5bao", hostname="5bao-test", ssh_reachable=True,
            components={"opencode": {"version": "1.17.5"}},
            path_dirs=["/usr/bin"],
        )
        store.set_candidate("5bao", fp.to_dict())
        result = mgr.adopt_candidate("5bao")
        assert not result["ok"]
        assert result["error"] == "plan_and_approval_required"
    finally:
        _cleanup(d)


# === Test 8: Receipt tamper blocks ===
def test_receipt_tamper_blocks():
    d = _make_tmp()
    try:
        store = _make_store(d)
        store.load()
        _seed_approved(store)
        mgr = _make_mgr(d, store)

        plan = _make_plan_with_digest(mgr, store, "5bao", "P-tamper")
        receipt_result = mgr.approve_plan("P-tamper", operator="test")
        assert receipt_result["ok"]
        receipt = receipt_result["receipt"]

        # Tamper with stored receipt digest
        state = store.load()
        for a in state.get("approvals", []):
            if a.get("plan_id") == "P-tamper":
                a["plan_digest"] = "TAMPERED"
                break
        store.save(state)

        result = mgr.freeze("5bao", plan_id="P-tamper", approval_receipt=receipt)
        assert not result["ok"]
        assert "digest" in result["error"]
    finally:
        _cleanup(d)


# === Test 9: Approval expiry blocks ===
def test_approval_expiry_blocks():
    d = _make_tmp()
    try:
        store = _make_store(d)
        store.load()
        _seed_approved(store)
        mgr = _make_mgr(d, store)

        plan = _make_plan_with_digest(mgr, store, "5bao", "P-expire")
        receipt_result = mgr.approve_plan("P-expire", operator="test")
        assert receipt_result["ok"]

        # Set expiry to past
        state = store.load()
        for a in state.get("approvals", []):
            if a.get("plan_id") == "P-expire":
                a["expires_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
                break
        store.save(state)

        result = mgr.freeze("5bao", plan_id="P-expire",
                           approval_receipt=receipt_result["receipt"])
        assert not result["ok"]
        assert result["error"] == "approval_expired"
    finally:
        _cleanup(d)


# === Test 10: No auto_reconcile ===
def test_no_auto_reconcile():
    import inspect
    src = inspect.getsource(ToolchainLifecycleManager.reconcile)
    assert "auto_reconcile" not in src


# === Test 11: dispatch_check_write_operation on clean state ===
def test_dispatch_check_write():
    d = _make_tmp()
    try:
        store = _make_store(d)
        store.load()
        _seed_approved(store)
        sp = os.path.join(d, "state.json")
        for op in ("implement", "review", "branch_write", "merge"):
            result = dispatch_check_write_operation(op, state_path=sp)
            assert result["allowed"], f"{op} should be allowed"
            assert result["operation"] == op
    finally:
        _cleanup(d)


# === Test 12: gate_check_for_dispatch on clean state returns components ===
def test_gate_dispatch_components():
    d = _make_tmp()
    try:
        store = _make_store(d)
        store.load()
        _seed_approved(store)
        # Use default state path for gate_check_for_dispatch
        gc = gate_check_for_dispatch()
        assert "components" in gc
        assert "corruption_latch" in gc["components"]
        assert "secret_drift" in gc["components"]
        assert "dual_unknown" in gc["components"]
        assert gc["gate_version"] == __version__
        assert "checked_at" in gc
    finally:
        _cleanup(d)


# === Test 13: freeze with valid plan+approval succeeds ===
def test_freeze_with_valid_plan():
    d = _make_tmp()
    try:
        store = _make_store(d)
        store.load()
        # Must seed approved first so before_fingerprint_sha is available
        _seed_approved(store)
        mgr = _make_mgr(d, store)

        plan = _make_plan_with_digest(mgr, store, "5bao", "P-valid")
        receipt_result = mgr.approve_plan("P-valid", operator="test_op")
        assert receipt_result["ok"]
        receipt = receipt_result["receipt"]

        fp = RuntimeFingerprint(
            node_id="5bao", hostname="5bao-test", ssh_reachable=True,
            components={"opencode": {"version": "1.17.4"}},
            path_dirs=["/usr/bin"],
        )
        result = mgr.freeze("5bao", plan_id="P-valid",
                           approval_receipt=receipt, fp=fp)
        assert result["ok"], f"freeze failed: {result}"
        assert store.has_approved("5bao")
    finally:
        _cleanup(d)


# === Test 14: adopt with valid plan+approval succeeds ===
def test_adopt_with_valid_plan():
    d = _make_tmp()
    try:
        store = _make_store(d)
        store.load()
        _seed_approved(store)
        mgr = _make_mgr(d, store)

        fp = RuntimeFingerprint(
            node_id="5bao", hostname="5bao-test", ssh_reachable=True,
            components={"opencode": {"version": "1.17.5"}},
            path_dirs=["/usr/bin"],
        )
        store.set_candidate("5bao", fp.to_dict())

        plan = _make_plan_with_digest(mgr, store, "5bao", "P-adopt")
        receipt_result = mgr.approve_plan("P-adopt", operator="test_op")
        assert receipt_result["ok"]
        receipt = receipt_result["receipt"]

        result = mgr.adopt_candidate("5bao", plan_id="P-adopt",
                                     approval_receipt=receipt)
        assert result["ok"], f"adopt failed: {result}"
        assert store.has_approved("5bao")
        assert store.get_candidate("5bao") is None
    finally:
        _cleanup(d)


# === Test 15: reconcile does NOT auto-approve ===
def test_reconcile_no_auto_approve():
    d = _make_tmp()
    try:
        store = _make_store(d)
        store.load()
        _seed_approved(store)
        mgr = _make_mgr(d, store)
        event = mgr.reconcile("5bao")
        assert event.status in (DriftEventStatus.RESOLVED, DriftEventStatus.BLOCKED,
                                DriftEventStatus.PENDING_APPROVAL)
        import inspect
        src = inspect.getsource(ToolchainLifecycleManager.reconcile)
        assert "auto_reconcile" not in src
    finally:
        _cleanup(d)


# === Test 16: Version ===
def test_version():
    assert __version__ in ("2.2.0", "2.3.0", "2.6.0", "2.7.0")


# === Test 17: Self-check ===
def test_self_check():
    d = _make_tmp()
    try:
        mgr = _make_mgr(d)
        result = mgr.self_check()
        assert result["overall"] == "PASS", f"Self-check failed: {result}"
        assert result["total"] >= 18
    finally:
        _cleanup(d)


# === Test 18: SSH StrictHostKeyChecking via SSH_OPTS ===
def test_ssh_strict_host_key():
    opts_str = " ".join(SSH_OPTS)
    assert "StrictHostKeyChecking" in opts_str, f"Not found in: {SSH_OPTS}"
    assert "StrictHostKeyChecking=no" not in opts_str
    assert "accept-new" not in opts_str


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
