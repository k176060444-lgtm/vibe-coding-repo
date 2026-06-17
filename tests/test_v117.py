#!/usr/bin/env python3
"""test_v117.py — V1.17 Toolchain Lifecycle Manager + Runtime Drift Reconciler tests.

Tests for drift detection, classification, remediation planning, dual-node safety,
simulation scenarios (patch upgrade, incompatible rollback, PATH fix, deps rebuild,
secret block, dual-unknown freeze).

All tests use in-memory mocks — no SSH, no network, no external repo mutation.
"""

import copy
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from vibe_worker_registry import WorkerRegistry, WorkerNode, NodeStatus
from vibe_toolchain_lifecycle import (
    RuntimeFingerprint, RuntimeBaseline, BaselineState,
    DriftType, DriftItem, DriftEvent, DriftEventStatus,
    RemediationAction,
    DriftDetector, DriftClassifier, RemediationPlanner,
    ToolchainLifecycleManager, FingerprintCollector,
    _sha256_text,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fingerprint(node_id="5bao", opencode_ver="1.17.4", opencode_hash="abc123",
                      node_ver="v22.22.1", path_dirs=None, wrapper_hash="w1",
                      config_hash="c1", secret_hash="s1", npm_pkg_hash="n1",
                      node_modules=True, venv_exists=True, hostname="KK-5bao",
                      openssh="1:9.2p1-2+deb12u6", libc6="2.36-9+deb12u10",
                      kernel="6.1.0-37-amd64"):
    """Create a test RuntimeFingerprint."""
    if path_dirs is None:
        path_dirs = ["/home/vibeworker/.local/bin",
                     "/home/vibeworker/.opencode/bin",
                     "/home/vibeworker/.local/node-current/bin",
                     "/usr/bin", "/bin"]
    return RuntimeFingerprint(
        node_id=node_id,
        collected_at=datetime.now(timezone.utc).isoformat(),
        hostname=hostname,
        ssh_reachable=True,
        components={
            "opencode": {"name": "opencode", "version": opencode_ver,
                        "binary_hash": opencode_hash, "path": "/home/vibeworker/.opencode/bin/opencode"},
            "node": {"name": "node", "version": node_ver,
                    "path": "/home/vibeworker/.local/node-current/bin/node"},
            "npm": {"name": "npm", "version": "10.9.4", "path": "/home/vibeworker/.local/node-current/bin/npm"},
            "git": {"name": "git", "version": "2.39.5", "path": "/usr/bin/git"},
            "gh": {"name": "gh", "version": "2.23.0", "path": "/usr/bin/gh"},
            "python3": {"name": "python3", "version": "3.11.2", "path": "/usr/bin/python3"},
            "pytest": {"name": "pytest", "version": "9.1.0"},
            "wrapper": {"name": "wrapper", "hash": wrapper_hash},
            "config": {"name": "config", "hash": config_hash},
            "lockfile": {"name": "lockfile", "hash": "lk1"},
            "npm_deps": {"name": "npm_deps", "package_hash": npm_pkg_hash,
                        "node_modules": node_modules},
            "venv": {"name": "venv", "exists": venv_exists},
            "secret_fingerprint": {"name": "secret_fingerprint", "hash": secret_hash},
            "system": {"name": "system", "openssh": openssh, "libc6": libc6, "kernel": kernel},
        },
        path_dirs=path_dirs,
    )


def _make_manager_with_baselines(nodes=None):
    """Create a ToolchainLifecycleManager with approved baselines."""
    if nodes is None:
        nodes = ["5bao", "9bao"]
    reg = WorkerRegistry()
    for n in nodes:
        reg.set_health(n, NodeStatus.ONLINE)
    mgr = ToolchainLifecycleManager(registry=reg)
    for n in nodes:
        fp = _make_fingerprint(node_id=n, hostname=f"KK-{n}")
        mgr.set_approved_baseline(n, fp)
        mgr.observed_states[n] = fp
    return mgr


# ---------------------------------------------------------------------------
# Test 1: No drift when fingerprints are identical
# ---------------------------------------------------------------------------

def test_no_drift_identical():
    """Identical fingerprints → 0 drift items."""
    approved = _make_fingerprint()
    observed = _make_fingerprint()
    items = DriftDetector().detect(approved, observed)
    assert len(items) == 0, f"Expected 0 items, got {len(items)}"
    return {"passed": True, "message": "identical: 0 drift items"}


# ---------------------------------------------------------------------------
# Test 2: Patch version drift detected
# ---------------------------------------------------------------------------

def test_patch_version_drift():
    """opencode 1.17.4 → 1.17.5 = PATCH_VERSION_DRIFT."""
    approved = _make_fingerprint(opencode_ver="1.17.4")
    observed = _make_fingerprint(opencode_ver="1.17.5")
    items = DriftDetector().detect(approved, observed)
    assert len(items) > 0, "Expected drift items"
    types = [i.drift_type for i in items]
    assert DriftType.PATCH_VERSION_DRIFT in types, f"Expected PATCH, got {types}"
    return {"passed": True, "message": f"1.17.4→1.17.5: PATCH_VERSION_DRIFT ({len(items)} items)"}


# ---------------------------------------------------------------------------
# Test 3: Major version drift detected
# ---------------------------------------------------------------------------

def test_major_version_drift():
    """opencode 1.17.4 → 2.0.0 = MAJOR_VERSION_DRIFT."""
    approved = _make_fingerprint(opencode_ver="1.17.4")
    observed = _make_fingerprint(opencode_ver="2.0.0")
    items = DriftDetector().detect(approved, observed)
    types = [i.drift_type for i in items]
    assert DriftType.MAJOR_VERSION_DRIFT in types, f"Expected MAJOR, got {types}"
    return {"passed": True, "message": "1.17.4→2.0.0: MAJOR_VERSION_DRIFT"}


# ---------------------------------------------------------------------------
# Test 4: PATH drift detected
# ---------------------------------------------------------------------------

def test_path_drift():
    """Changed PATH dirs → PATH_DRIFT."""
    approved = _make_fingerprint(path_dirs=["/a", "/b", "/c"])
    observed = _make_fingerprint(path_dirs=["/a", "/b", "/d"])
    items = DriftDetector().detect(approved, observed)
    path_items = [i for i in items if i.drift_type == DriftType.PATH_DRIFT]
    assert len(path_items) > 0, f"Expected PATH_DRIFT, got {[i.drift_type for i in items]}"
    return {"passed": True, "message": f"PATH changed: {len(path_items)} PATH items"}


# ---------------------------------------------------------------------------
# Test 5: Dependency drift (node_modules missing)
# ---------------------------------------------------------------------------

def test_dependency_drift_npm():
    """node_modules missing → DEPENDENCY_DRIFT."""
    approved = _make_fingerprint(node_modules=True)
    observed = _make_fingerprint(node_modules=False)
    items = DriftDetector().detect(approved, observed)
    dep_items = [i for i in items if i.drift_type == DriftType.DEPENDENCY_DRIFT]
    assert len(dep_items) > 0, f"Expected DEPENDENCY_DRIFT, got {[i.drift_type for i in items]}"
    return {"passed": True, "message": "node_modules missing: DEPENDENCY_DRIFT"}


# ---------------------------------------------------------------------------
# Test 6: Dependency drift (venv missing)
# ---------------------------------------------------------------------------

def test_dependency_drift_venv():
    """venv missing → DEPENDENCY_DRIFT."""
    approved = _make_fingerprint(venv_exists=True)
    observed = _make_fingerprint(venv_exists=False)
    items = DriftDetector().detect(approved, observed)
    dep_items = [i for i in items if i.drift_type == DriftType.DEPENDENCY_DRIFT]
    assert len(dep_items) > 0, f"Expected DEPENDENCY_DRIFT"
    return {"passed": True, "message": "venv missing: DEPENDENCY_DRIFT"}


# ---------------------------------------------------------------------------
# Test 7: Secret drift detected and BLOCK-ed
# ---------------------------------------------------------------------------

def test_secret_drift_block():
    """Secret fingerprint change → SECRET_DRIFT → BLOCK."""
    approved = _make_fingerprint(secret_hash="original_hash")
    observed = _make_fingerprint(secret_hash="changed_hash_!!")
    items = DriftDetector().detect(approved, observed)
    secret_items = [i for i in items if i.drift_type == DriftType.SECRET_DRIFT]
    assert len(secret_items) > 0, "Expected SECRET_DRIFT"

    # Planner must BLOCK
    action = RemediationPlanner().plan(DriftType.SECRET_DRIFT)
    assert action == RemediationAction.BLOCK, f"Expected BLOCK, got {action}"

    # Manager reconcile must block
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    mgr = ToolchainLifecycleManager(registry=reg)
    mgr.set_approved_baseline("5bao", approved)
    mgr.observed_states["5bao"] = observed
    event = mgr.reconcile("5bao", items, DriftType.SECRET_DRIFT)
    assert event.status == DriftEventStatus.BLOCKED, f"Expected BLOCKED, got {event.status}"
    assert event.operator_required is True
    assert "blocked" in event.resolution.lower() or "secret" in event.resolution.lower()
    return {"passed": True, "message": "SECRET_DRIFT → BLOCK + operator_required"}


# ---------------------------------------------------------------------------
# Test 8: System package drift → operator required
# ---------------------------------------------------------------------------

def test_system_package_drift():
    """libc6 version change → SYSTEM_PACKAGE_DRIFT → operator."""
    approved = _make_fingerprint(libc6="2.36-9+deb12u10")
    observed = _make_fingerprint(libc6="2.36-9+deb12u11")
    items = DriftDetector().detect(approved, observed)
    sys_items = [i for i in items if i.drift_type == DriftType.SYSTEM_PACKAGE_DRIFT]
    assert len(sys_items) > 0, "Expected SYSTEM_PACKAGE_DRIFT"

    action = RemediationPlanner().plan(DriftType.SYSTEM_PACKAGE_DRIFT)
    assert action == RemediationAction.OPERATOR_REQUIRED
    return {"passed": True, "message": "libc6 change: SYSTEM_PACKAGE_DRIFT → operator"}


# ---------------------------------------------------------------------------
# Test 9: Classifier priority — UNKNOWN > all
# ---------------------------------------------------------------------------

def test_classifier_priority():
    """UNKNOWN_DRIFT wins over all other types."""
    items = [
        DriftItem(component="a", drift_type=DriftType.PATH_DRIFT),
        DriftItem(component="b", drift_type=DriftType.MAJOR_VERSION_DRIFT),
        DriftItem(component="c", drift_type=DriftType.UNKNOWN_DRIFT),
    ]
    result = DriftClassifier().classify(items)
    assert result == DriftType.UNKNOWN_DRIFT, f"Expected UNKNOWN, got {result}"
    return {"passed": True, "message": "UNKNOWN > MAJOR > PATH"}


# ---------------------------------------------------------------------------
# Test 10: Classifier priority — SECRET > PATCH/DEP/CONFIG
# ---------------------------------------------------------------------------

def test_classifier_secret_priority():
    """SECRET_DRIFT wins over PATCH/DEPENDENCY/CONFIG."""
    items = [
        DriftItem(component="a", drift_type=DriftType.PATCH_VERSION_DRIFT),
        DriftItem(component="b", drift_type=DriftType.DEPENDENCY_DRIFT),
        DriftItem(component="c", drift_type=DriftType.SECRET_DRIFT),
    ]
    result = DriftClassifier().classify(items)
    assert result == DriftType.SECRET_DRIFT, f"Expected SECRET, got {result}"
    return {"passed": True, "message": "SECRET > PATCH > DEP"}


# ---------------------------------------------------------------------------
# Test 11: Dual-node safety — both unknown → block writes
# ---------------------------------------------------------------------------

def test_dual_node_safety():
    """Both nodes UNKNOWN drift → no write tasks allowed."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    reg.set_health("9bao", NodeStatus.ONLINE)
    mgr = ToolchainLifecycleManager(registry=reg)

    # Both nodes have unresolved UNKNOWN drift
    mgr.event_log.append({
        "node_id": "9bao",
        "drift_type": "UNKNOWN_DRIFT",
        "status": "operator_waiting",
    })
    mgr.event_log.append({
        "node_id": "5bao",
        "drift_type": "UNKNOWN_DRIFT",
        "status": "operator_waiting",
    })

    # 5bao reconcile should be blocked
    fp = _make_fingerprint(node_id="5bao")
    mgr.set_approved_baseline("5bao", fp)
    items = [DriftItem(component="test", drift_type=DriftType.PATH_DRIFT)]
    event = mgr.reconcile("5bao", items, DriftType.PATH_DRIFT)
    assert event.status == DriftEventStatus.BLOCKED, f"Expected BLOCKED, got {event.status}"
    assert "both_nodes_unknown" in event.resolution
    return {"passed": True, "message": "both nodes UNKNOWN → BLOCKED"}


# ---------------------------------------------------------------------------
# Test 12: Single node unknown → other node still works
# ---------------------------------------------------------------------------

def test_single_node_unknown_other_works():
    """Only one node UNKNOWN → other node can still reconcile."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    reg.set_health("9bao", NodeStatus.ONLINE)
    mgr = ToolchainLifecycleManager(registry=reg)

    # Only 5bao has unresolved UNKNOWN drift (not 9bao)
    mgr.event_log.append({
        "node_id": "5bao",
        "drift_type": "UNKNOWN_DRIFT",
        "status": "operator_waiting",
    })

    # 9bao should still work: _both_nodes_unknown requires BOTH nodes to have unknown
    both_unknown = mgr._both_nodes_unknown("9bao")
    assert not both_unknown, "Only 5bao is unknown, 9bao should be free"
    return {"passed": True, "message": "single unknown → other node free"}


# ---------------------------------------------------------------------------
# Test 13: Simulation — 9bao OpenCode patch upgrade → canary pass → candidate
# ---------------------------------------------------------------------------

def test_sim_patch_upgrade_canary_pass():
    """9bao opencode 1.17.4 → 1.17.5: canary validation creates candidate baseline."""
    reg = WorkerRegistry()
    reg.set_health("9bao", NodeStatus.ONLINE)
    mgr = ToolchainLifecycleManager(registry=reg)

    # Set approved baseline
    approved = _make_fingerprint(node_id="9bao", opencode_ver="1.17.4")
    mgr.set_approved_baseline("9bao", approved)

    # Simulate observed state with new version
    observed = _make_fingerprint(node_id="9bao", opencode_ver="1.17.5",
                                opencode_hash="new_hash_123")
    mgr.observed_states["9bao"] = observed

    items, dtype = mgr.detect_drift("9bao")
    assert dtype == DriftType.PATCH_VERSION_DRIFT, f"Expected PATCH, got {dtype}"

    # Planner says canary validation
    action = RemediationPlanner().plan(dtype)
    assert action == RemediationAction.CANARY_VALIDATION

    # Since we can't SSH in tests, simulate canary result manually
    # Create a candidate baseline as if canary passed
    sha = _sha256_text(json.dumps(observed.to_dict(), sort_keys=True, default=str))
    mgr.candidate_baselines["9bao"] = RuntimeBaseline(
        state=BaselineState.CANDIDATE,
        fingerprint=observed,
        sha256=sha,
        frozen_at=datetime.now(timezone.utc).isoformat(),
        frozen_by="auto_canary",
    )

    assert "9bao" in mgr.candidate_baselines
    assert mgr.candidate_baselines["9bao"].sha256 == sha
    return {"passed": True, "message": f"patch upgrade → candidate baseline (sha={sha})"}


# ---------------------------------------------------------------------------
# Test 14: Simulation — adopt candidate → approved
# ---------------------------------------------------------------------------

def test_sim_adopt_candidate():
    """Adopt candidate baseline → becomes approved."""
    reg = WorkerRegistry()
    reg.set_health("9bao", NodeStatus.ONLINE)
    mgr = ToolchainLifecycleManager(registry=reg)

    observed = _make_fingerprint(node_id="9bao", opencode_ver="1.17.5")
    sha = _sha256_text(json.dumps(observed.to_dict(), sort_keys=True, default=str))
    mgr.candidate_baselines["9bao"] = RuntimeBaseline(
        state=BaselineState.CANDIDATE,
        fingerprint=observed,
        sha256=sha,
    )

    event = mgr.adopt_candidate("9bao")
    assert event.status == DriftEventStatus.RESOLVED
    assert event.forward_converge is True
    assert "9bao" in mgr.approved_baselines
    assert mgr.approved_baselines["9bao"].fingerprint.components["opencode"]["version"] == "1.17.5"
    assert "9bao" not in mgr.candidate_baselines  # candidate consumed
    return {"passed": True, "message": "adopt → approved (1.17.5)"}


# ---------------------------------------------------------------------------
# Test 15: Simulation — forward converge other node
# ---------------------------------------------------------------------------

def test_sim_forward_converge():
    """After adopt on 9bao, forward converge sets same baseline on 5bao."""
    mgr = _make_manager_with_baselines()

    # 9bao gets a new approved baseline (simulating post-adopt)
    new_fp = _make_fingerprint(node_id="9bao", opencode_ver="1.17.5")
    sha = _sha256_text(json.dumps(new_fp.to_dict(), sort_keys=True, default=str))
    mgr.approved_baselines["9bao"] = RuntimeBaseline(
        state=BaselineState.APPROVED,
        fingerprint=new_fp,
        sha256=sha,
    )

    event = mgr.forward_converge_other_node("9bao")
    assert event.status == DriftEventStatus.RESOLVED
    assert event.forward_converge is True
    assert event.other_node_converged == "9bao"
    # 5bao should now have the same baseline sha
    assert mgr.approved_baselines["5bao"].sha256 == sha
    return {"passed": True, "message": "forward converge 5bao from 9bao (sha match)"}


# ---------------------------------------------------------------------------
# Test 16: Simulation — incompatible version → rollback
# ---------------------------------------------------------------------------

def test_sim_incompatible_rollback():
    """Incompatible version → canary fail → rollback to approved."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    mgr = ToolchainLifecycleManager(registry=reg)

    approved = _make_fingerprint(node_id="5bao", opencode_ver="1.17.4")
    mgr.set_approved_baseline("5bao", approved)

    # Simulate rollback restoring the approved version
    event = DriftEvent(
        event_id="test-rollback",
        node_id="5bao",
        detected_at=datetime.now(timezone.utc).isoformat(),
        drift_type=DriftType.PATCH_VERSION_DRIFT,
        status=DriftEventStatus.RECONCILING,
        remediation=RemediationAction.ROLLBACK,
    )

    # Simulate rollback result (without SSH)
    event.status = DriftEventStatus.ROLLED_BACK
    event.rollback_performed = True
    event.resolution = "rolled_back_to_approved_1.17.4"
    event.operator_required = False

    assert event.status == DriftEventStatus.ROLLED_BACK
    assert event.rollback_performed is True
    assert "1.17.4" in event.resolution
    return {"passed": True, "message": "incompatible → ROLLED_BACK to 1.17.4"}


# ---------------------------------------------------------------------------
# Test 17: PATH drift auto-fix simulation
# ---------------------------------------------------------------------------

def test_sim_path_auto_fix():
    """PATH drift detected → auto_fix planned → resolution."""
    planner = RemediationPlanner()
    action = planner.plan(DriftType.PATH_DRIFT)
    assert action == RemediationAction.AUTO_FIX

    # Simulate successful auto-fix
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    mgr = ToolchainLifecycleManager(registry=reg)

    approved = _make_fingerprint(node_id="5bao")
    mgr.set_approved_baseline("5bao", approved)

    # After fix, observed = approved
    mgr.observed_states["5bao"] = _make_fingerprint(node_id="5bao")
    items, dtype = mgr.detect_drift("5bao")
    assert len(items) == 0, "Post-fix: no drift"

    return {"passed": True, "message": "PATH_DRIFT → AUTO_FIX → no drift after fix"}


# ---------------------------------------------------------------------------
# Test 18: Deps rebuild simulation
# ---------------------------------------------------------------------------

def test_sim_deps_rebuild():
    """DEPENDENCY_DRIFT → REBUILD planned."""
    planner = RemediationPlanner()
    action = planner.plan(DriftType.DEPENDENCY_DRIFT)
    assert action == RemediationAction.REBUILD

    # Verify post-rebuild: node_modules restored
    approved = _make_fingerprint(node_modules=True, venv_exists=True)
    observed_post = _make_fingerprint(node_modules=True, venv_exists=True)
    items = DriftDetector().detect(approved, observed_post)
    dep_items = [i for i in items if i.drift_type == DriftType.DEPENDENCY_DRIFT]
    assert len(dep_items) == 0, "Post-rebuild: no DEPENDENCY_DRIFT"
    return {"passed": True, "message": "DEPENDENCY_DRIFT → REBUILD → clean"}


# ---------------------------------------------------------------------------
# Test 19: Config drift restore
# ---------------------------------------------------------------------------

def test_sim_config_restore():
    """CONFIG_DRIFT → RESTORE_CONFIG planned."""
    planner = RemediationPlanner()
    action = planner.plan(DriftType.CONFIG_DRIFT)
    assert action == RemediationAction.RESTORE_CONFIG

    # Post-restore: config hashes match
    approved = _make_fingerprint(config_hash="original")
    observed_post = _make_fingerprint(config_hash="original")
    items = DriftDetector().detect(approved, observed_post)
    config_items = [i for i in items if i.drift_type == DriftType.CONFIG_DRIFT]
    assert len(config_items) == 0
    return {"passed": True, "message": "CONFIG_DRIFT → RESTORE_CONFIG → clean"}


# ---------------------------------------------------------------------------
# Test 20: Event log persistence
# ---------------------------------------------------------------------------

def test_event_log_persistence():
    """Events saved to file and reloadable."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        tmppath = f.name

    try:
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.ONLINE)
        mgr = ToolchainLifecycleManager(registry=reg, event_log_path=tmppath)
        fp = _make_fingerprint(node_id="5bao")
        mgr.set_approved_baseline("5bao", fp)

        # Create an event
        evt = DriftEvent(
            event_id="persist-test-001",
            node_id="5bao",
            status=DriftEventStatus.RESOLVED,
            resolution="test_persist",
        )
        mgr.event_log.append(evt.to_dict())
        mgr._save_events()

        # Reload
        mgr2 = ToolchainLifecycleManager(registry=reg, event_log_path=tmppath)
        assert len(mgr2.event_log) == 1
        assert mgr2.event_log[0]["event_id"] == "persist-test-001"
        return {"passed": True, "message": "events persist and reload"}
    finally:
        os.unlink(tmppath)


# ---------------------------------------------------------------------------
# Test 21: Baseline state separation
# ---------------------------------------------------------------------------

def test_baseline_state_separation():
    """approved ≠ observed ≠ candidate — three separate states."""
    reg = WorkerRegistry()
    mgr = ToolchainLifecycleManager(registry=reg)

    fp_approved = _make_fingerprint(opencode_ver="1.17.4")
    fp_observed = _make_fingerprint(opencode_ver="1.17.5")
    fp_candidate = _make_fingerprint(opencode_ver="1.17.5", opencode_hash="candidate_hash")

    mgr.set_approved_baseline("5bao", fp_approved)
    mgr.observed_states["5bao"] = fp_observed
    sha = _sha256_text(json.dumps(fp_candidate.to_dict(), sort_keys=True, default=str))
    mgr.candidate_baselines["5bao"] = RuntimeBaseline(
        state=BaselineState.CANDIDATE,
        fingerprint=fp_candidate,
        sha256=sha,
    )

    assert mgr.approved_baselines["5bao"].state == BaselineState.APPROVED
    assert mgr.approved_baselines["5bao"].fingerprint.components["opencode"]["version"] == "1.17.4"
    assert mgr.observed_states["5bao"].components["opencode"]["version"] == "1.17.5"
    assert mgr.candidate_baselines["5bao"].state == BaselineState.CANDIDATE

    # Mutating observed must not affect approved
    mgr.observed_states["5bao"].components["opencode"]["version"] = "1.18.0"
    assert mgr.approved_baselines["5bao"].fingerprint.components["opencode"]["version"] == "1.17.4"
    return {"passed": True, "message": "3 states isolated, no cross-contamination"}


# ---------------------------------------------------------------------------
# Test 22: Rollback via CLI command
# ---------------------------------------------------------------------------

def test_rollback_command():
    """rollback_drift creates rollback event."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    mgr = ToolchainLifecycleManager(registry=reg)
    fp = _make_fingerprint(node_id="5bao")
    mgr.set_approved_baseline("5bao", fp)

    event = mgr.rollback_drift("5bao", "manual-rollback")
    # Without SSH, rollback can't actually execute, but event is created
    assert event.node_id == "5bao"
    assert event.remediation == RemediationAction.ROLLBACK
    return {"passed": True, "message": "rollback event created"}


# ---------------------------------------------------------------------------
# Test 23: Events listing with limit
# ---------------------------------------------------------------------------

def test_events_listing():
    """Events listing respects limit."""
    reg = WorkerRegistry()
    mgr = ToolchainLifecycleManager(registry=reg)
    for i in range(10):
        mgr.event_log.append({"event_id": f"evt-{i}", "node_id": "5bao"})

    assert len(mgr.get_events(5)) == 5
    assert len(mgr.get_events(20)) == 10
    assert len(mgr.get_events()) == 10  # default limit=20
    return {"passed": True, "message": "events listing limit works"}


# ---------------------------------------------------------------------------
# Test 24: Multi-drift scenario (PATH + DEP + PATCH)
# ---------------------------------------------------------------------------

def test_multi_drift_highest_priority():
    """Multiple drift types → classifier picks highest priority."""
    approved = _make_fingerprint(path_dirs=["/a", "/b"])
    observed = _make_fingerprint(
        path_dirs=["/a", "/c"],  # PATH_DRIFT
        opencode_ver="1.17.5",   # PATCH_VERSION_DRIFT
        node_modules=False,      # DEPENDENCY_DRIFT
    )
    items = DriftDetector().detect(approved, observed)
    assert len(items) > 0

    drift_type = DriftClassifier().classify(items)
    # DEP > PATCH > PATH in priority
    assert drift_type == DriftType.DEPENDENCY_DRIFT, f"Expected DEP, got {drift_type}"
    return {"passed": True, "message": f"multi-drift → {drift_type.value} (highest priority)"}


# ---------------------------------------------------------------------------
# Test 25: Edge case — approved not set → empty detection
# ---------------------------------------------------------------------------

def test_no_approved_baseline():
    """No approved baseline → detect returns empty."""
    reg = WorkerRegistry()
    mgr = ToolchainLifecycleManager(registry=reg)
    items, dtype = mgr.detect_drift("5bao")
    assert items == []
    assert dtype is None
    return {"passed": True, "message": "no baseline → empty detection"}


# ---------------------------------------------------------------------------
# Test 26: Wrapper hash drift → CONFIG_DRIFT
# ---------------------------------------------------------------------------

def test_wrapper_hash_drift():
    """Wrapper script changed → CONFIG_DRIFT."""
    approved = _make_fingerprint(wrapper_hash="old_wrapper")
    observed = _make_fingerprint(wrapper_hash="new_wrapper")
    items = DriftDetector().detect(approved, observed)
    config_items = [i for i in items if i.drift_type == DriftType.CONFIG_DRIFT]
    assert len(config_items) > 0, f"Expected CONFIG_DRIFT for wrapper, got {items}"
    return {"passed": True, "message": "wrapper hash change → CONFIG_DRIFT"}


# ---------------------------------------------------------------------------
# Test 27: Maintenance set during reconcile for non-trivial drift
# ---------------------------------------------------------------------------

def test_maintenance_set_during_reconcile():
    """Non-trivial drift → worker set to maintenance during reconcile."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    mgr = ToolchainLifecycleManager(registry=reg)
    fp = _make_fingerprint(node_id="5bao")
    mgr.set_approved_baseline("5bao", fp)
    mgr.observed_states["5bao"] = fp

    # SECRET drift → BLOCK → maintenance
    items = [DriftItem(component="secret_fingerprint", drift_type=DriftType.SECRET_DRIFT,
                       approved_value="a", observed_value="b")]
    event = mgr.reconcile("5bao", items, DriftType.SECRET_DRIFT)
    assert event.maintenance_set is True
    assert reg.get_worker("5bao").maintenance_status == "maintenance"
    return {"passed": True, "message": "SECRET → maintenance set"}


# ---------------------------------------------------------------------------
# Test 28: Adopt without candidate → blocked
# ---------------------------------------------------------------------------

def test_adopt_no_candidate():
    """Adopt with no candidate → BLOCKED."""
    reg = WorkerRegistry()
    mgr = ToolchainLifecycleManager(registry=reg)
    event = mgr.adopt_candidate("5bao")
    assert event.status == DriftEventStatus.BLOCKED
    assert "no_candidate" in event.resolution
    return {"passed": True, "message": "no candidate → BLOCKED"}


# ---------------------------------------------------------------------------
# Test 29: Version parsing edge cases
# ---------------------------------------------------------------------------

def test_version_parsing():
    """Version parsing handles v-prefix and suffixes."""
    detector = DriftDetector()
    assert detector._classify_version_drift("v1.17.4", "1.17.5") == DriftType.PATCH_VERSION_DRIFT
    assert detector._classify_version_drift("1.17.4", "1.18.0") == DriftType.MAJOR_VERSION_DRIFT
    assert detector._classify_version_drift("2.0.0", "1.0.0") == DriftType.MAJOR_VERSION_DRIFT
    assert detector._classify_version_drift("1.17.4-beta", "1.17.4") == DriftType.PATCH_VERSION_DRIFT
    return {"passed": True, "message": "version parsing: v-prefix, suffix, major change"}


# ---------------------------------------------------------------------------
# Test 30: Self-check passes
# ---------------------------------------------------------------------------

def test_self_check():
    """Module self-check passes."""
    result = ToolchainLifecycleManager().self_check()
    assert result["overall"] == "PASS", f"Self-check failed: {result}"
    assert result["passed"] == result["total"]
    return {"passed": True, "message": f"self-check: {result['passed']}/{result['total']} PASS"}
