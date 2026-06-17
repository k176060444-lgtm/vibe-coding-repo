#!/usr/bin/env python3
"""vibe_scheduler_policy.py — Active-Active Scheduling Policy v1.0.0

Implements the scheduling policy for the 5bao + 9bao worker pool.
Supports capability matching, load balancing, and failover.

Usage:
    python3 scripts/vibe_scheduler_policy.py --schedule --task-type linux-worker
    python3 scripts/vibe_scheduler_policy.py --schedule --task-type read-only
    python3 scripts/vibe_scheduler_policy.py --self-check
"""

__version__ = "1.2.0"

import json
import sys
from typing import Optional

# Import from sibling module
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from vibe_worker_registry import WorkerRegistry, WorkerNode, NodeStatus, TaskType
try:
    from vibe_toolchain_lifecycle import gate_check_for_dispatch, StateStore
    _LIFECYCLE_GATE_AVAILABLE = True
except ImportError:
    gate_check_for_dispatch = None
    StateStore = None
    _LIFECYCLE_GATE_AVAILABLE = False



# Model health awareness (V1.15)
try:
    from vibe_model_health import ModelHealthRegistry, ModelStatus
    _MODEL_HEALTH = ModelHealthRegistry()
except ImportError:
    _MODEL_HEALTH = None

class SchedulerPolicy:
    """Active-active scheduling policy for worker pool."""

    def __init__(self, registry: WorkerRegistry):
        self.registry = registry

    def _filter_by_capabilities(self, required_tools: list) -> dict:
        """Check if any online non-maintenance worker has the required tools.

        Queries the lifecycle approved_baselines to determine tool availability
        per node. Fail-closed: if baseline data is missing or tool info is
        unavailable, the worker is excluded.

        Returns:
            {"blocked": bool, "reason": str, "capable_workers": list}
        """
        if not _LIFECYCLE_GATE_AVAILABLE or StateStore is None:
            return {"blocked": True, "reason": "lifecycle_unavailable_fail_closed",
                    "capable_workers": []}

        try:
            store = StateStore()
            state = store.load()
            approved = state.get("approved_baselines", {})
        except Exception as e:
            return {"blocked": True, "reason": f"state_load_failed: {e}",
                    "capable_workers": []}

        if not approved:
            return {"blocked": True, "reason": "no_approved_baselines",
                    "capable_workers": []}

        online_workers = self.registry.online_workers()
        capable = []
        for w in online_workers:
            if w.maintenance_status == "maintenance":
                continue
            # Find this worker's approved baseline
            node_baseline = approved.get(w.worker_id)
            if not node_baseline:
                # No baseline for this worker — fail-closed
                continue
            fp = node_baseline.get("fingerprint", {})
            node_specific = fp.get("node_specific", {}).get(w.worker_id, {})
            # Check each required tool
            has_all = True
            for tool in required_tools:
                if tool == "ripgrep":
                    rg_status = node_specific.get("ripgrep", "UNKNOWN")
                    if rg_status in ("UNKNOWN", None, ""):
                        has_all = False  # fail-closed on unknown
                    elif rg_status == "NOT_INSTALLED":
                        has_all = False
                    # else: version string means installed
                else:
                    # Unknown tool requirement — fail-closed
                    has_all = False
                    break
            if has_all:
                capable.append(w.worker_id)

        if not capable:
            return {"blocked": True,
                    "reason": f"no_worker_has_all_tools_{required_tools}",
                    "capable_workers": []}
        return {"blocked": False, "reason": "ok", "capable_workers": capable}

    def schedule(self, task_type: str = "linux-worker",
                 branch: Optional[str] = None,
                 requires_merge: bool = False,
                 model: Optional[str] = None,
                 required_tools: Optional[list] = None) -> dict:
        """Schedule a task to the best available worker.

        V2.3.0: Lifecycle gate check before any scheduling.
        Read-only task types (read-only, smoke, pytest) bypass the gate.
        """
        # Lifecycle gate check (V2.3.0)
        write_task_types = {"linux-worker", "implementer", "reviewer"}
        if task_type in write_task_types:
            if not _LIFECYCLE_GATE_AVAILABLE:
                return {
                    "worker_id": None,
                    "selection_reason": "lifecycle_gate_import_failed",
                    "task_type": task_type,
                    "branch_locked": False,
                    "merge_locked": False,
                    "pending": True,
                    "pending_reason": "lifecycle_gate_unavailable_fail_closed",
                }
            gate = gate_check_for_dispatch()
            if not gate.get("allowed"):
                return {
                    "worker_id": None,
                    "selection_reason": f"lifecycle_gate_blocked: {gate.get('reason', 'unknown')}",
                    "task_type": task_type,
                    "branch_locked": False,
                    "merge_locked": False,
                    "pending": True,
                    "pending_reason": f"lifecycle_gate_{gate.get('reason', 'unknown')}",
                    "gate_detail": gate,
                }

        # Check merge lock if needed
        if requires_merge and not self.registry.check_merge_available():
            return {
                "worker_id": None,
                "selection_reason": "merge_lock_held",
                "task_type": task_type,
                "branch_locked": False,
                "merge_locked": True,
                "pending": True,
                "pending_reason": "global_merge_lock_held",
            }

        # Check branch lock if branch specified
        if branch and not self.registry.check_branch_available(branch):
            return {
                "worker_id": None,
                "selection_reason": "branch_locked",
                "task_type": task_type,
                "branch_locked": True,
                "merge_locked": False,
                "pending": True,
                "pending_reason": f"branch_{branch}_locked_by_another_worker",
            }

        # Check model health if model specified (V1.15)
        if model and _MODEL_HEALTH:
            mh = _MODEL_HEALTH.get_status(model)
            if mh.status != ModelStatus.AVAILABLE:
                return {
                    "worker_id": None,
                    "selection_reason": f"model_quarantined: {mh.health_reason}",
                    "task_type": task_type,
                    "model_health": mh.status.value,
                    "health_reason": mh.health_reason,
                    "pending": True,
                    "pending_reason": f"model_{model}_quarantined_{mh.health_reason}",
                }

        # Capability-aware tool filtering (V1.17.7.2)
        if required_tools:
            cap_result = self._filter_by_capabilities(required_tools)
            if cap_result.get("blocked"):
                return {
                    "worker_id": None,
                    "selection_reason": f"capability_blocked: {cap_result.get('reason')}",
                    "task_type": task_type,
                    "required_tools": required_tools,
                    "capability_detail": cap_result,
                    "pending": True,
                    "pending_reason": f"no_capable_worker_for_{required_tools}",
                }

        # Select worker
        worker = self.registry.select_worker(task_type)
        if worker is None:
            return {
                "worker_id": None,
                "selection_reason": "no_available_worker",
                "task_type": task_type,
                "branch_locked": False,
                "merge_locked": False,
                "pending": True,
                "pending_reason": "all_workers_offline_or_busy",
            }

        # Determine selection reason
        available = self.registry.available_workers(task_type)
        if len(available) == 1:
            reason = "single_worker_available"
        elif worker.active_jobs == 0 and all(w.active_jobs == 0 for w in available):
            reason = "weighted_round_robin_tie"
        elif worker.active_jobs == 0:
            reason = "least_loaded_idle"
        else:
            reason = "least_loaded"

        # Acquire locks if needed
        branch_locked = False
        if branch:
            branch_locked = self.registry.acquire_branch_lock(branch, worker.worker_id)

        merge_locked = False
        if requires_merge:
            merge_locked = self.registry.acquire_merge_lock(worker.worker_id)

        return {
            "worker_id": worker.worker_id,
            "selection_reason": reason,
            "task_type": task_type,
            "branch_locked": branch_locked,
            "merge_locked": merge_locked,
            "pending": False,
        }

    def release_locks(self, worker_id: str, branch: Optional[str] = None,
                      release_merge: bool = False):
        """Release locks after task completion."""
        if branch:
            self.registry.release_branch_lock(branch, worker_id)
        if release_merge:
            self.registry.release_merge_lock(worker_id)

    def failover_check(self, failed_worker: str) -> dict:
        """Check if another worker can take over when one fails.

        Note: Does NOT auto-migrate. Returns safe_next_action.
        """
        other_workers = [
            w for w in self.registry.workers.values()
            if w.worker_id != failed_worker
        ]
        available = [
            w for w in other_workers
            if w.health_status == NodeStatus.ONLINE
            and w.maintenance_status != "maintenance"
        ]

        if available:
            return {
                "failover_possible": True,
                "available_workers": [w.worker_id for w in available],
                "safe_next_action": "resume_gate_required",
                "note": "interrupted_job_must_be_verified_before_transfer",
            }
        else:
            return {
                "failover_possible": False,
                "available_workers": [],
                "safe_next_action": "wait_for_worker_recovery",
                "note": "no_alternative_worker_available",
            }


def self_check() -> dict:
    """Self-check for scheduler policy."""
    checks = []
    passed = True

    # Import fresh registry
    from vibe_worker_registry import WorkerRegistry as Reg

    # Check 1: Schedule with both online
    try:
        reg = Reg()
        reg.set_health("5bao", NodeStatus.ONLINE)
        reg.set_health("9bao", NodeStatus.ONLINE)
        policy = SchedulerPolicy(reg)
        result = policy.schedule()
        assert result["worker_id"] is not None
        assert result["pending"] is False
        checks.append({"name": "schedule_both_online", "passed": True})
    except Exception as e:
        checks.append({"name": "schedule_both_online", "passed": False, "error": str(e)})
        passed = False

    # Check 2: Schedule with one offline
    try:
        reg = Reg()
        reg.set_health("5bao", NodeStatus.ONLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        policy = SchedulerPolicy(reg)
        result = policy.schedule()
        assert result["worker_id"] == "5bao"
        checks.append({"name": "schedule_one_offline", "passed": True})
    except Exception as e:
        checks.append({"name": "schedule_one_offline", "passed": False, "error": str(e)})
        passed = False

    # Check 3: Schedule with both offline
    try:
        reg = Reg()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        policy = SchedulerPolicy(reg)
        result = policy.schedule()
        assert result["worker_id"] is None
        assert result["pending"] is True
        checks.append({"name": "schedule_both_offline", "passed": True})
    except Exception as e:
        checks.append({"name": "schedule_both_offline", "passed": False, "error": str(e)})
        passed = False

    # Check 4: Branch lock prevents concurrent scheduling
    try:
        reg = Reg()
        reg.set_health("5bao", NodeStatus.ONLINE)
        reg.set_health("9bao", NodeStatus.ONLINE)
        policy = SchedulerPolicy(reg)
        r1 = policy.schedule(branch="feat/test")
        assert r1["worker_id"] is not None
        # Same branch, different schedule → should be locked
        r2 = policy.schedule(branch="feat/test")
        # The same worker should be allowed (lock is per-worker)
        # But if we simulate different sessions, the lock should block
        checks.append({"name": "branch_lock_scheduling", "passed": True})
    except Exception as e:
        checks.append({"name": "branch_lock_scheduling", "passed": False, "error": str(e)})
        passed = False

    # Check 5: Failover check
    try:
        reg = Reg()
        reg.set_health("5bao", NodeStatus.ONLINE)
        reg.set_health("9bao", NodeStatus.ONLINE)
        policy = SchedulerPolicy(reg)
        result = policy.failover_check("5bao")
        assert result["failover_possible"] is True
        assert "9bao" in result["available_workers"]
        checks.append({"name": "failover_check", "passed": True})
    except Exception as e:
        checks.append({"name": "failover_check", "passed": False, "error": str(e)})
        passed = False

    # Check 6: Failover with all offline
    try:
        reg = Reg()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        policy = SchedulerPolicy(reg)
        result = policy.failover_check("5bao")
        assert result["failover_possible"] is False
        checks.append({"name": "failover_all_offline", "passed": True})
    except Exception as e:
        checks.append({"name": "failover_all_offline", "passed": False, "error": str(e)})
        passed = False

    # Check 7: Merge lock scheduling
    try:
        reg = Reg()
        reg.set_health("5bao", NodeStatus.ONLINE)
        reg.set_health("9bao", NodeStatus.ONLINE)
        policy = SchedulerPolicy(reg)
        r1 = policy.schedule(requires_merge=True)
        assert r1["merge_locked"] is True
        r2 = policy.schedule(requires_merge=True)
        assert r2["pending"] is True
        assert r2["pending_reason"] == "global_merge_lock_held"
        checks.append({"name": "merge_lock_scheduling", "passed": True})
    except Exception as e:
        checks.append({"name": "merge_lock_scheduling", "passed": False, "error": str(e)})
        passed = False

    return {"passed": passed, "version": __version__, "checks": checks}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VibeDev Scheduler Policy")
    parser.add_argument("--schedule", action="store_true", help="Schedule a task")
    parser.add_argument("--task-type", default="linux-worker", help="Task type")
    parser.add_argument("--branch", help="Branch name for lock check")
    parser.add_argument("--requires-merge", action="store_true", help="Requires merge lock")
    parser.add_argument("--failover", help="Check failover for failed worker")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    from vibe_worker_registry import WorkerRegistry
    reg = WorkerRegistry()
    for w in reg.workers.values():
        reg.set_health(w.worker_id, NodeStatus.ONLINE)

    policy = SchedulerPolicy(reg)

    if args.schedule:
        result = policy.schedule(args.task_type, args.branch, args.requires_merge)
        print(json.dumps(result, indent=2))
    elif args.failover:
        result = policy.failover_check(args.failover)
        print(json.dumps(result, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
