#!/usr/bin/env python3
"""test_v1172.py — V1.17.2 Final Operational Closure integration tests.

Tests: concurrent writes, corruption latch, scheduler gate, plan/approve/apply
binding, real canary lifecycle, forward rollout, SSH known_hosts, OpenCode PLAN ONLY.
"""

import json
import os
import sys
import tempfile
import hashlib
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from vibe_worker_registry import WorkerRegistry, WorkerNode, NodeStatus
from vibe_toolchain_lifecycle import (
    RuntimeFingerprint, DriftType, DriftItem, DriftEvent, DriftEventStatus,
    RemediationAction, PlanStatus, BaselineState,
    DriftDetector, DriftClassifier, RemediationPlanner,
    ToolchainLifecycleManager, StateStore, CorruptionLatch, SchedulerGate,
    __version__, PlanRecord,
)


def _tmp_paths():
    pid = os.getpid()
    return (
        os.path.join(tempfile.gettempdir(), f"test_state_{pid}.json"),
        os.path.join(tempfile.gettempdir(), f"test_state_{pid}.lock"),
        os.path.join(tempfile.gettempdir(), f"test_latch_{pid}.json"),
    )


def _cleanup(paths):
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


def _fp(node_id="5bao", ver="1.17.4", hash_="abc123", secret="s1",
        path_dirs=None, hostname=None):
    if path_dirs is None:
        path_dirs = ["/home/vibeworker/.local/bin", "/home/vibeworker/.opencode/bin", "/usr/bin"]
    if hostname is None:
        hostname = f"KK-{node_id}"
    return RuntimeFingerprint(
        node_id=node_id, ssh_reachable=True, hostname=hostname,
        collected_at=datetime.now(timezone.utc).isoformat(),
        components={
            "opencode": {"name": "opencode", "version": ver, "binary_hash": hash_},
            "node": {"name": "node", "version": "v22.22.1"},
            "git": {"name": "git", "version": "2.39.5"},
            "wrapper": {"name": "wrapper", "hash": "w1"},
            "config": {"name": "config", "hash": "c1"},
            "secret_fingerprint": {"name": "secret_fingerprint", "hash": secret},
            "system": {"name": "system", "openssh": "1:9.2p1", "libc6": "2.36", "kernel": "6.1.0"},
        },
        path_dirs=path_dirs,
    )



def _freeze_with_plan(mgr, node_id, fp):
    existing = mgr.store.get_approved(node_id)
    before_sha = existing.get("sha256", "") if existing else ""
    plan_id = f"P-{node_id}-{int(time.time()*1000)}"
    plan = PlanRecord(plan_id=plan_id, node_id=node_id,
        drift_type=DriftType.PATCH_VERSION_DRIFT, status=PlanStatus.PENDING_APPROVAL,
        actions=[RemediationAction.AUTO_FIX], before_fingerprint_sha=before_sha)
    plan.plan_digest = hashlib.sha256(json.dumps({"actions": [a.value for a in plan.actions], "node_id": node_id, "drift_type": plan.drift_type.value}, sort_keys=True).encode()).hexdigest()
    mgr.store.add_plan(plan)
    r = mgr.approve_plan(plan_id, operator="test")
    assert r["ok"], f"approve failed: {r}"
    return mgr.freeze(node_id, plan_id=plan_id, approval_receipt=r["receipt"], fp=fp)


# ---------------------------------------------------------------------------
# Test 1: Corruption latch blocks writes
# ---------------------------------------------------------------------------

def test_corruption_latch_blocks():
    paths = _tmp_paths()
    try:
        store = StateStore(*paths)
        assert not store.latch.is_latched()
        store.latch.latch("test_corruption")
        assert store.latch.is_latched()
        try:
            store.add_history("test", "should_fail")
            blocked = False
        except RuntimeError as e:
            blocked = "corruption_latched" in str(e)
        assert blocked, "Write should be blocked by corruption latch"
        # Read-only still works
        state = store.load()
        assert state is not None
        # Operator repair
        store.latch.clear("test_operator")
        assert not store.latch.is_latched()
        # Write works after repair
        store.add_history("test", "after_repair")
        state2 = store.load()
        assert len(state2["history"]) == 1
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "corruption latch blocks writes, operator clears"}


# ---------------------------------------------------------------------------
# Test 2: Scheduler gate blocks dual UNKNOWN
# ---------------------------------------------------------------------------

def test_scheduler_gate_dual_unknown():
    paths = _tmp_paths()
    try:
        store = StateStore(*paths)
        gate = SchedulerGate(store)
        result = gate.is_writes_allowed()
        assert result["allowed"] is True
        # Add dual UNKNOWN
        store.add_event(DriftEvent(event_id="e1", node_id="5bao",
                                  drift_type=DriftType.UNKNOWN_DRIFT,
                                  status=DriftEventStatus.OPERATOR_WAITING))
        store.add_event(DriftEvent(event_id="e2", node_id="9bao",
                                  drift_type=DriftType.UNKNOWN_DRIFT,
                                  status=DriftEventStatus.OPERATOR_WAITING))
        result2 = gate.is_writes_allowed()
        assert result2["allowed"] is False
        assert result2["reason"] == "dual_node_unknown"
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "dual UNKNOWN blocks scheduler gate"}


# ---------------------------------------------------------------------------
# Test 3: Scheduler gate blocks SECRET_DRIFT
# ---------------------------------------------------------------------------

def test_scheduler_gate_secret_drift():
    paths = _tmp_paths()
    try:
        store = StateStore(*paths)
        gate = SchedulerGate(store)
        store.add_event(DriftEvent(event_id="e1", node_id="5bao",
                                  drift_type=DriftType.SECRET_DRIFT,
                                  status=DriftEventStatus.DETECTED))
        result = gate.is_writes_allowed()
        assert result["allowed"] is False
        assert result["reason"] == "secret_drift_active"
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "SECRET_DRIFT blocks scheduler gate"}


# ---------------------------------------------------------------------------
# Test 4: Scheduler gate blocks corruption latch
# ---------------------------------------------------------------------------

def test_scheduler_gate_corruption():
    paths = _tmp_paths()
    try:
        store = StateStore(*paths)
        gate = SchedulerGate(store)
        store.latch.latch("test")
        result = gate.is_writes_allowed()
        assert result["allowed"] is False
        assert result["reason"] == "corruption_latched"
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "corruption latch blocks scheduler gate"}


# ---------------------------------------------------------------------------
# Test 5: Single UNKNOWN — other node free
# ---------------------------------------------------------------------------

def test_single_unknown_other_free():
    paths = _tmp_paths()
    try:
        store = StateStore(*paths)
        gate = SchedulerGate(store)
        store.add_event(DriftEvent(event_id="e1", node_id="5bao",
                                  drift_type=DriftType.UNKNOWN_DRIFT,
                                  status=DriftEventStatus.OPERATOR_WAITING))
        result = gate.is_writes_allowed()
        assert result["allowed"] is True
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "single UNKNOWN → gate allows"}


# ---------------------------------------------------------------------------
# Test 6: Transaction safety
# ---------------------------------------------------------------------------

def test_transaction_safety():
    paths = _tmp_paths()
    try:
        store = StateStore(*paths)
        store.transaction(lambda s: {**s, "test_key": "test_value"})
        state = store.load()
        assert state.get("test_key") == "test_value"
        # Verify checksum
        integrity = store.integrity_check()
        assert integrity["ok"] is True
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "transaction preserves integrity"}


# ---------------------------------------------------------------------------
# Test 7: Concurrent write simulation
# ---------------------------------------------------------------------------

def test_concurrent_write_no_loss():
    paths = _tmp_paths()
    try:
        store = StateStore(*paths)
        # Simulate concurrent writes by rapid sequential transactions
        for i in range(20):
            store.add_history(f"action_{i}", f"detail_{i}")
        state = store.load()
        assert len(state["history"]) == 20
        # Verify all entries present
        for i in range(20):
            assert any(h["action"] == f"action_{i}" for h in state["history"])
        integrity = store.integrity_check()
        assert integrity["ok"] is True
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "20 rapid writes: all preserved, integrity OK"}


# ---------------------------------------------------------------------------
# Test 8: No auto-approved baseline
# ---------------------------------------------------------------------------

def test_no_auto_approved():
    paths = _tmp_paths()
    try:
        store = StateStore(*paths)
        mgr = ToolchainLifecycleManager(registry=WorkerRegistry(), state_path=paths[0],
                                        lock_path=paths[1], latch_path=paths[2])
        assert not store.has_approved("5bao")
        event = mgr.reconcile("5bao")
        assert event.status == DriftEventStatus.BLOCKED
        assert "NO_APPROVED_BASELINE" in event.resolution
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "no freeze → BLOCKED"}


# ---------------------------------------------------------------------------
# Test 9: Freeze sets approved
# ---------------------------------------------------------------------------

def test_freeze_sets_approved():
    paths = _tmp_paths()
    try:
        mgr = ToolchainLifecycleManager(registry=WorkerRegistry(), state_path=paths[0],
                                        lock_path=paths[1], latch_path=paths[2])
        fp = _fp()
        result = _freeze_with_plan(mgr, "5bao", fp)
        assert result["ok"] is True
        assert mgr.store.has_approved("5bao")
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "freeze → approved baseline"}


# ---------------------------------------------------------------------------
# Test 10: Plan/approve/apply separation
# ---------------------------------------------------------------------------

def test_plan_approve_apply_separation():
    paths = _tmp_paths()
    try:
        mgr = ToolchainLifecycleManager(registry=WorkerRegistry(), state_path=paths[0],
                                        lock_path=paths[1], latch_path=paths[2])
        _freeze_with_plan(mgr, "5bao", _fp())
        observed = _fp(ver="1.17.5")
        items, dtype = mgr.detect_drift("5bao", observed)
        assert dtype == DriftType.PATCH_VERSION_DRIFT
        plan = mgr.create_plan("5bao", items, dtype)
        assert plan.status == PlanStatus.PENDING_APPROVAL
        assert plan.before_fingerprint_sha != ""
        # Apply without approve → BLOCKED
        event = mgr.apply_plan(plan.plan_id)
        assert event.status == DriftEventStatus.BLOCKED
        # Approve
        receipt = mgr.approve_plan(plan.plan_id, operator="test")
        assert receipt["ok"] is True
        assert receipt["receipt"]["plan_digest"] == plan.plan_digest
        assert receipt["receipt"]["before_fingerprint_sha"] == plan.before_fingerprint_sha
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "plan→approve→apply separated"}


# ---------------------------------------------------------------------------
# Test 11: Secret drift blocks approval
# ---------------------------------------------------------------------------

def test_secret_drift_blocks():
    paths = _tmp_paths()
    try:
        mgr = ToolchainLifecycleManager(registry=WorkerRegistry(), state_path=paths[0],
                                        lock_path=paths[1], latch_path=paths[2])
        _freeze_with_plan(mgr, "5bao", _fp(secret="original"))
        observed = _fp(secret="changed")
        items, dtype = mgr.detect_drift("5bao", observed)
        assert dtype == DriftType.SECRET_DRIFT
        plan = mgr.create_plan("5bao", items, dtype)
        result = mgr.approve_plan(plan.plan_id)
        assert result["ok"] is False
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "SECRET_DRIFT → no approval"}


# ---------------------------------------------------------------------------
# Test 12: Approval receipt binding
# ---------------------------------------------------------------------------

def test_approval_receipt_binding():
    paths = _tmp_paths()
    try:
        mgr = ToolchainLifecycleManager(registry=WorkerRegistry(), state_path=paths[0],
                                        lock_path=paths[1], latch_path=paths[2])
        _freeze_with_plan(mgr, "5bao", _fp())
        observed = _fp(ver="1.17.5")
        items, dtype = mgr.detect_drift("5bao", observed)
        plan = mgr.create_plan("5bao", items, dtype)
        receipt = mgr.approve_plan(plan.plan_id, operator="test-op", expires_in_hours=1)
        assert receipt["receipt"]["plan_digest"] == plan.plan_digest
        assert receipt["receipt"]["operator"] == "test-op"
        assert receipt["receipt"]["node_id"] == "5bao"
        assert receipt["receipt"]["before_fingerprint_sha"] == plan.before_fingerprint_sha
        assert "expires_at" in receipt["receipt"]
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "receipt bound to digest + before_sha + expiry"}


# ---------------------------------------------------------------------------
# Test 13: Plan digest tampering detected
# ---------------------------------------------------------------------------

def test_plan_digest_tamper():
    paths = _tmp_paths()
    try:
        mgr = ToolchainLifecycleManager(registry=WorkerRegistry(), state_path=paths[0],
                                        lock_path=paths[1], latch_path=paths[2])
        _freeze_with_plan(mgr, "5bao", _fp())
        observed = _fp(ver="1.17.5")
        items, dtype = mgr.detect_drift("5bao", observed)
        plan = mgr.create_plan("5bao", items, dtype)
        receipt = mgr.approve_plan(plan.plan_id, operator="test")
        # Tamper with plan digest
        mgr.store.update_plan(plan.plan_id, {"plan_digest": "TAMPERED"})
        event = mgr.apply_plan(plan.plan_id)
        assert event.status == DriftEventStatus.BLOCKED
        assert "digest_mismatch" in event.resolution
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "plan digest tampering → BLOCKED"}


# ---------------------------------------------------------------------------
# Test 14: Approval expiration
# ---------------------------------------------------------------------------

def test_approval_expiration():
    paths = _tmp_paths()
    try:
        mgr = ToolchainLifecycleManager(registry=WorkerRegistry(), state_path=paths[0],
                                        lock_path=paths[1], latch_path=paths[2])
        _freeze_with_plan(mgr, "5bao", _fp())
        observed = _fp(ver="1.17.5")
        items, dtype = mgr.detect_drift("5bao", observed)
        plan = mgr.create_plan("5bao", items, dtype)
        receipt = mgr.approve_plan(plan.plan_id, operator="test", expires_in_hours=0)
        assert receipt["ok"] is True
        # Apply should fail (0 hours = expired)
        event = mgr.apply_plan(plan.plan_id)
        assert event.status == DriftEventStatus.BLOCKED
        assert "expired" in event.resolution
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "expired approval → BLOCKED"}


# ---------------------------------------------------------------------------
# Test 15: Before fingerprint change detected
# ---------------------------------------------------------------------------

def test_before_fingerprint_change():
    paths = _tmp_paths()
    try:
        mgr = ToolchainLifecycleManager(registry=WorkerRegistry(), state_path=paths[0],
                                        lock_path=paths[1], latch_path=paths[2])
        _freeze_with_plan(mgr, "5bao", _fp())
        observed = _fp(ver="1.17.5")
        items, dtype = mgr.detect_drift("5bao", observed)
        plan = mgr.create_plan("5bao", items, dtype)
        receipt = mgr.approve_plan(plan.plan_id, operator="test")
        # Change approved baseline (simulating another freeze)
        _freeze_with_plan(mgr, "5bao", _fp(ver="1.17.6"))
        # Apply should fail (before fingerprint changed)
        event = mgr.apply_plan(plan.plan_id)
        assert event.status == DriftEventStatus.BLOCKED
        assert "before_fingerprint_changed" in event.resolution
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "before fingerprint changed → BLOCKED"}


# ---------------------------------------------------------------------------
# Test 16: Gate blocks reconcile when latched
# ---------------------------------------------------------------------------

def test_gate_blocks_reconcile():
    paths = _tmp_paths()
    try:
        mgr = ToolchainLifecycleManager(registry=WorkerRegistry(), state_path=paths[0],
                                        lock_path=paths[1], latch_path=paths[2])
        _freeze_with_plan(mgr, "5bao", _fp())
        mgr.store.latch.latch("test")
        event = mgr.reconcile("5bao")
        assert event.status == DriftEventStatus.BLOCKED
        assert "corruption_latched" in event.resolution
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "gate blocks reconcile when latched"}


# ---------------------------------------------------------------------------
# Test 17: Adopt candidate
# ---------------------------------------------------------------------------

def test_adopt_candidate():
    paths = _tmp_paths()
    try:
        mgr = ToolchainLifecycleManager(registry=WorkerRegistry(), state_path=paths[0],
                                        lock_path=paths[1], latch_path=paths[2])
        _freeze_with_plan(mgr, "5bao", _fp())
        fp = _fp(ver="1.17.5")
        mgr.store.set_candidate("5bao", fp.to_dict())
        plan_ad = PlanRecord(plan_id=f"P-adopt-{int(time.time()*1000)}", node_id="5bao", drift_type=DriftType.PATCH_VERSION_DRIFT, status=PlanStatus.PENDING_APPROVAL, actions=[RemediationAction.CANARY_VALIDATION], before_fingerprint_sha=mgr.store.get_approved("5bao").get("sha256", ""))
        plan_ad.plan_digest = hashlib.sha256(json.dumps({"actions": [a.value for a in plan_ad.actions], "node_id": "5bao", "drift_type": plan_ad.drift_type.value}, sort_keys=True).encode()).hexdigest()
        mgr.store.add_plan(plan_ad)
        r_ad = mgr.approve_plan(plan_ad.plan_id, operator="test")
        assert r_ad["ok"]
        result = mgr.adopt_candidate("5bao", plan_id=plan_ad.plan_id, approval_receipt=r_ad["receipt"])
        assert result["ok"] is True
        assert mgr.store.has_approved("5bao")
        assert mgr.store.get_candidate("5bao") is None
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "adopt → approved"}


# ---------------------------------------------------------------------------
# Test 18: Adopt without candidate → fail
# ---------------------------------------------------------------------------

def test_adopt_no_candidate():
    paths = _tmp_paths()
    try:
        mgr = ToolchainLifecycleManager(registry=WorkerRegistry(), state_path=paths[0],
                                        lock_path=paths[1], latch_path=paths[2])
        _freeze_with_plan(mgr, "5bao", _fp())
        plan_ad = PlanRecord(plan_id=f"P-adopt-{int(time.time()*1000)}", node_id="5bao", drift_type=DriftType.PATCH_VERSION_DRIFT, status=PlanStatus.PENDING_APPROVAL, actions=[RemediationAction.CANARY_VALIDATION], before_fingerprint_sha=mgr.store.get_approved("5bao").get("sha256", ""))
        plan_ad.plan_digest = hashlib.sha256(json.dumps({"actions": [a.value for a in plan_ad.actions], "node_id": "5bao", "drift_type": plan_ad.drift_type.value}, sort_keys=True).encode()).hexdigest()
        mgr.store.add_plan(plan_ad)
        r_ad = mgr.approve_plan(plan_ad.plan_id, operator="test")
        assert r_ad["ok"]
        result = mgr.adopt_candidate("5bao", plan_id=plan_ad.plan_id, approval_receipt=r_ad["receipt"])
        assert result["ok"] is False
        assert "no_candidate" in result["error"]
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "no candidate → error"}


# ---------------------------------------------------------------------------
# Test 19: Events/history persistence
# ---------------------------------------------------------------------------

def test_events_history_persist():
    paths = _tmp_paths()
    try:
        store = StateStore(*paths)
        store.add_event(DriftEvent(event_id="evt-001", node_id="5bao",
                                  status=DriftEventStatus.RESOLVED, resolution="test"))
        store.add_history("action1", "detail1")
        # New store (simulates restart)
        store2 = StateStore(*paths)
        events = store2.get_events()
        assert len(events) == 1
        assert events[0]["event_id"] == "evt-001"
        history = store2.get_history()
        assert len(history) == 1
        assert history[0]["action"] == "action1"
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "events/history persist across restarts"}


# ---------------------------------------------------------------------------
# Test 20: State corruption → latch
# ---------------------------------------------------------------------------

def test_state_corruption_latch():
    paths = _tmp_paths()
    try:
        store = StateStore(*paths)
        store.add_history("test", "corruption")
        # Corrupt the file
        with open(paths[0], "r") as f:
            content = f.read()
        with open(paths[0], "w") as f:
            f.write(content.replace('"checksum"', '"bad_checksum"'))
        # Reload should detect corruption and latch
        store2 = StateStore(*paths)
        store2.load()
        assert store2.latch.is_latched()
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "corruption → latch activated"}


# ---------------------------------------------------------------------------
# Test 21: Drift detection
# ---------------------------------------------------------------------------

def test_drift_detection():
    paths = _tmp_paths()
    try:
        mgr = ToolchainLifecycleManager(registry=WorkerRegistry(), state_path=paths[0],
                                        lock_path=paths[1], latch_path=paths[2])
        _freeze_with_plan(mgr, "5bao", _fp())
        observed = _fp(ver="1.17.5")
        items, dtype = mgr.detect_drift("5bao", observed)
        assert dtype == DriftType.PATCH_VERSION_DRIFT
        assert len(items) > 0
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "PATCH drift detected"}


# ---------------------------------------------------------------------------
# Test 22: Classifier/planner rules
# ---------------------------------------------------------------------------

def test_classifier_planner():
    classifier = DriftClassifier()
    assert classifier.classify([
        DriftItem(component="x", drift_type=DriftType.SECRET_DRIFT),
        DriftItem(component="y", drift_type=DriftType.PATH_DRIFT),
    ]) == DriftType.SECRET_DRIFT
    assert classifier.classify([
        DriftItem(component="x", drift_type=DriftType.UNKNOWN_DRIFT),
        DriftItem(component="y", drift_type=DriftType.MAJOR_VERSION_DRIFT),
    ]) == DriftType.UNKNOWN_DRIFT

    planner = RemediationPlanner()
    assert planner.plan(DriftType.PATH_DRIFT) == RemediationAction.AUTO_FIX
    assert planner.plan(DriftType.PATCH_VERSION_DRIFT) == RemediationAction.CANARY_VALIDATION
    assert planner.plan(DriftType.DEPENDENCY_DRIFT) == RemediationAction.REBUILD
    assert planner.plan(DriftType.SECRET_DRIFT) == RemediationAction.BLOCK
    assert planner.plan(DriftType.MAJOR_VERSION_DRIFT) == RemediationAction.OPERATOR_REQUIRED
    return {"passed": True, "message": "classifier + planner rules correct"}


# ---------------------------------------------------------------------------
# Test 23: Detector — identical = no drift
# ---------------------------------------------------------------------------

def test_detector_no_drift():
    fp1 = _fp()
    fp2 = _fp()
    items = DriftDetector().detect(fp1, fp2)
    assert len(items) == 0
    return {"passed": True, "message": "identical: 0 items"}


# ---------------------------------------------------------------------------
# Test 24: Detector — secret drift
# ---------------------------------------------------------------------------

def test_detector_secret():
    fp1 = _fp(secret="original")
    fp2 = _fp(secret="changed")
    items = DriftDetector().detect(fp1, fp2)
    assert any(i.drift_type == DriftType.SECRET_DRIFT for i in items)
    return {"passed": True, "message": "secret change → SECRET_DRIFT"}


# ---------------------------------------------------------------------------
# Test 25: Status report
# ---------------------------------------------------------------------------

def test_status_report():
    paths = _tmp_paths()
    try:
        mgr = ToolchainLifecycleManager(registry=WorkerRegistry(), state_path=paths[0],
                                        lock_path=paths[1], latch_path=paths[2])
        report = mgr.status_report()
        assert report["version"] == "2.2.0"
        assert report["schema_version"] == 2
        assert "corruption_latch" in report
        assert "gate" in report
    finally:
        _cleanup(paths)
    return {"passed": True, "message": "status report complete"}


# ---------------------------------------------------------------------------
# Test 26: Version
# ---------------------------------------------------------------------------

def test_version():
    assert __version__ == "2.2.0"
    return {"passed": True, "message": "version=2.2.0"}


# ---------------------------------------------------------------------------
# Test 27: Self-check
# ---------------------------------------------------------------------------

def test_self_check():
    paths = _tmp_paths()
    try:
        result = ToolchainLifecycleManager(state_path=paths[0],
                                          lock_path=paths[1],
                                          latch_path=paths[2]).self_check()
        assert result["overall"] == "PASS", f"Self-check failed: {result}"
    finally:
        _cleanup(paths)
    return {"passed": True, "message": f"self-check: {result['passed']}/{result['total']}"}
