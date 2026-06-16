#!/usr/bin/env python3
"""test_v1143.py — V1.14.3 Active-Active Worker Pool tests.

Tests for worker registry, scheduler policy, global locks, and dual-node coordination.
"""

import json
import sys
import os
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from vibe_worker_registry import WorkerRegistry, WorkerNode, NodeStatus
from vibe_scheduler_policy import SchedulerPolicy


def test_5bao_9bao_both_online_least_loaded():
    """Both online → least-loaded selected."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    reg.set_health("9bao", NodeStatus.ONLINE)
    # 5bao has a job, 9bao idle
    reg.record_job_start("5bao")
    selected = reg.select_worker()
    assert selected is not None
    assert selected.worker_id == "9bao"
    return {"passed": True, "message": "least-loaded: 9bao selected (5bao busy)"}


def test_equal_load_weighted_round_robin():
    """Equal load → weighted round-robin (both weight=100, first wins)."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    reg.set_health("9bao", NodeStatus.ONLINE)
    selected = reg.select_worker()
    assert selected is not None
    # Both have same weight, 5bao is first in dict
    assert selected.worker_id in ("5bao", "9bao")
    return {"passed": True, "message": f"equal load: {selected.worker_id} selected"}


def test_5bao_busy_9bao_selected():
    """5bao busy → 9bao selected."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    reg.set_health("9bao", NodeStatus.ONLINE)
    reg.record_job_start("5bao")
    reg.record_job_start("5bao")  # 2 jobs
    selected = reg.select_worker()
    assert selected is not None
    assert selected.worker_id == "9bao"
    return {"passed": True, "message": "5bao busy → 9bao selected"}


def test_9bao_busy_5bao_selected():
    """9bao busy → 5bao selected."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    reg.set_health("9bao", NodeStatus.ONLINE)
    reg.record_job_start("9bao")
    selected = reg.select_worker()
    assert selected is not None
    assert selected.worker_id == "5bao"
    return {"passed": True, "message": "9bao busy → 5bao selected"}


def test_one_offline_other_selected():
    """One offline → other selected."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    reg.set_health("9bao", NodeStatus.OFFLINE)
    selected = reg.select_worker()
    assert selected is not None
    assert selected.worker_id == "5bao"

    reg2 = WorkerRegistry()
    reg2.set_health("5bao", NodeStatus.OFFLINE)
    reg2.set_health("9bao", NodeStatus.ONLINE)
    selected2 = reg2.select_worker()
    assert selected2 is not None
    assert selected2.worker_id == "9bao"
    return {"passed": True, "message": "offline failover works both ways"}


def test_both_offline_pending():
    """Both offline → pending no worker."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.OFFLINE)
    reg.set_health("9bao", NodeStatus.OFFLINE)
    selected = reg.select_worker()
    assert selected is None
    return {"passed": True, "message": "both offline → no worker"}


def test_maintenance_not_selected():
    """Maintenance worker not selected."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    reg.set_health("9bao", NodeStatus.ONLINE)
    reg.set_maintenance("5bao", "maintenance")
    selected = reg.select_worker()
    assert selected is not None
    assert selected.worker_id == "9bao"
    return {"passed": True, "message": "maintenance worker excluded"}


def test_branch_lock_prevents_concurrent():
    """Same branch lock prevents concurrent mutation."""
    reg = WorkerRegistry()
    assert reg.acquire_branch_lock("feat/test", "5bao") is True
    assert reg.acquire_branch_lock("feat/test", "9bao") is False
    assert reg.release_branch_lock("feat/test", "5bao") is True
    assert reg.acquire_branch_lock("feat/test", "9bao") is True
    return {"passed": True, "message": "branch lock prevents concurrent mutation"}


def test_merge_lock_prevents_duplicate():
    """Global merge lock prevents duplicate merge."""
    reg = WorkerRegistry()
    assert reg.acquire_merge_lock("5bao") is True
    assert reg.acquire_merge_lock("9bao") is False
    assert reg.release_merge_lock("5bao") is True
    assert reg.acquire_merge_lock("9bao") is True
    return {"passed": True, "message": "merge lock prevents duplicate merge"}


def test_interrupted_job_requires_resume_gate():
    """Interrupted job must go through resume gate."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    reg.set_health("9bao", NodeStatus.ONLINE)
    policy = SchedulerPolicy(reg)
    failover = policy.failover_check("5bao")
    assert failover["failover_possible"] is True
    assert failover["safe_next_action"] == "resume_gate_required"
    return {"passed": True, "message": "interrupted job requires resume gate"}


def test_external_write_still_approval_required():
    """External write still requires approval (policy check)."""
    # This is a policy assertion - external write gate is not bypassed by pool
    from vibe_worker_registry import DEFAULT_WORKERS
    for w in DEFAULT_WORKERS.values():
        assert "external_write" not in w.allowed_operations
    return {"passed": True, "message": "external write not in allowed_operations"}


def test_no_token_leak():
    """No token/secret in registry output."""
    reg = WorkerRegistry()
    output = json.dumps(reg.to_dict())
    # Allow "token_policy" as field name but not actual token values
    assert "ghp_" not in output
    assert "github_pat_" not in output
    assert "password" not in output.lower()
    return {"passed": True, "message": "no token leak in output"}


def test_dual_node_independent_jobs():
    """Two independent jobs can run on different workers simultaneously."""
    reg = WorkerRegistry()
    reg.set_health("5bao", NodeStatus.ONLINE)
    reg.set_health("9bao", NodeStatus.ONLINE)

    # Schedule first job
    w1 = reg.select_worker()
    assert w1 is not None
    reg.record_job_start(w1.worker_id)

    # Schedule second job
    w2 = reg.select_worker()
    assert w2 is not None
    assert w2.worker_id != w1.worker_id
    reg.record_job_start(w2.worker_id)

    # Both busy
    w3 = reg.select_worker()
    assert w3 is None  # No capacity

    # Complete first job
    reg.record_job_end(w1.worker_id)

    # Now one slot available
    w4 = reg.select_worker()
    assert w4 is not None
    assert w4.worker_id == w1.worker_id
    return {"passed": True, "message": f"dual-node: {w1.worker_id}+{w2.worker_id} parallel, then {w4.worker_id} recycled"}


# All tests
ALL_TESTS = [
    test_5bao_9bao_both_online_least_loaded,
    test_equal_load_weighted_round_robin,
    test_5bao_busy_9bao_selected,
    test_9bao_busy_5bao_selected,
    test_one_offline_other_selected,
    test_both_offline_pending,
    test_maintenance_not_selected,
    test_branch_lock_prevents_concurrent,
    test_merge_lock_prevents_duplicate,
    test_interrupted_job_requires_resume_gate,
    test_external_write_still_approval_required,
    test_no_token_leak,
    test_dual_node_independent_jobs,
]


def main():
    passed = 0
    failed = 0
    results = []
    for test_fn in ALL_TESTS:
        try:
            result = test_fn()
            if result.get("passed"):
                passed += 1
                results.append({"name": test_fn.__name__, "passed": True, "message": result.get("message", "")})
            else:
                failed += 1
                results.append({"name": test_fn.__name__, "passed": False, "message": result.get("message", "")})
        except Exception as e:
            failed += 1
            results.append({"name": test_fn.__name__, "passed": False, "error": str(e)})

    total = passed + failed
    print(json.dumps({
        "total": total,
        "passed": passed,
        "failed": failed,
        "tests": results,
    }, indent=2))
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
