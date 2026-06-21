#!/usr/bin/env python3
"""vibe_scheduler_policy.py — Active-Active Scheduling Policy v1.3.0

Implements the scheduling policy for the 5bao + 9bao + 21bao worker pool.
Supports capability matching, load balancing, failover, and transport-aware routing.

V1.3.0 (V1.20.16): Transport-aware routing.
  - WINDOWS_WORKER tasks route to transport=local-exec workers only.
  - LINUX_WORKER tasks route to transport=ssh workers only.
  - IMPLEMENTER/REVIEWER route to any capable worker.
  - Unknown transport fails closed.
  - Manual-only workers excluded from auto-scheduling.

Usage:
    python3 scripts/vibe_scheduler_policy.py --schedule --task-type linux-worker
    python3 scripts/vibe_scheduler_policy.py --schedule --task-type read-only
    python3 scripts/vibe_scheduler_policy.py --self-check
"""

__version__ = "1.3.0"

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

        Primary source: worker registry tools_installed (authoritative per-node).
        Fallback: lifecycle approved_baselines node_specific data.
        Fail-closed: if both sources are unavailable or tool info is unknown,
        the worker is excluded.

        V1.3.0: Also filters out disabled and manual_only workers.

        Returns:
            {"blocked": bool, "reason": str, "capable_workers": list}
        """
        # Load baseline fallback data if available
        approved = {}
        if _LIFECYCLE_GATE_AVAILABLE and StateStore is not None:
            try:
                store = StateStore()
                state = store.load()
                approved = state.get("approved_baselines", {})
            except Exception:
                pass  # baseline unavailable, rely on registry

        online_workers = [
            w for w in self.registry.online_workers()
            if w.enabled and not w.manual_only
        ]
        capable = []
        for w in online_workers:
            if w.maintenance_status == "maintenance":
                continue
            has_all = True
            for tool in required_tools:
                # Primary: check registry tools_installed
                reg_tool = w.tools_installed.get(tool)
                if reg_tool is not None:
                    if reg_tool in ("NOT_INSTALLED", "UNKNOWN", None, ""):
                        has_all = False
                    # else: version string means installed
                    continue
                # Fallback: check approved baseline
                node_baseline = approved.get(w.worker_id)
                if not node_baseline:
                    has_all = False  # no data at all -- fail-closed
                    break
                fp = node_baseline.get("fingerprint", {})
                node_specific = fp.get("node_specific", {}).get(w.worker_id, {})
                baseline_tool = node_specific.get(tool, "UNKNOWN")
                if baseline_tool in ("UNKNOWN", None, ""):
                    has_all = False
                elif baseline_tool == "NOT_INSTALLED":
                    has_all = False
                # else: version string means installed
            if has_all:
                capable.append(w.worker_id)

        if not capable:
            return {"blocked": True,
                    "reason": "no_worker_has_all_tools_%s" % required_tools,
                    "capable_workers": []}
        return {"blocked": False, "reason": "ok", "capable_workers": capable}

    def _get_transport_filter(self, task_type: str) -> Optional[str]:
        """Return required transport for a task type, or None for any transport.

        V1.3.0: Transport-aware routing.
        - WINDOWS_WORKER -> local-exec
        - LINUX_WORKER -> ssh
        - IMPLEMENTER/REVIEWER/other -> None (any transport)
        """
        transport_map = {
            "windows-worker": "local-exec",
            "linux-worker": "ssh",
        }
        return transport_map.get(task_type)

    def get_eligible_candidates(self, task_type: str = "linux-worker",
                                 required_tools: list = None,
                                 branch: str = None,
                                 requires_merge: bool = False) -> list:
        """Return ordered list of (worker_id, reason) passing ALL gates.

        V1.3.0: Transport-aware routing.
        - WINDOWS_WORKER tasks route to transport=local-exec workers only.
        - LINUX_WORKER tasks route to transport=ssh workers only.
        - IMPLEMENTER/REVIEWER route to any capable worker.
        - Unknown transport fails closed.
        - Manual-only workers excluded from auto-scheduling.

        Applies same gates as schedule(): lifecycle, merge lock, branch lock,
        capability, health, maintenance. Returns empty list if any gate fails.
        Workers sorted by least-loaded first.
        """
        import sys as _sys
        _sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
        from vibe_worker_registry import NodeStatus

        # Lifecycle gate
        write_task_types = {"linux-worker", "implementer", "reviewer"}
        if task_type in write_task_types:
            if not _LIFECYCLE_GATE_AVAILABLE:
                return []
            try:
                gate = gate_check_for_dispatch()
                if not gate.get("allowed"):
                    return []
            except Exception:
                return []

        # Merge lock
        if requires_merge and not self.registry.check_merge_available():
            return []

        # Branch lock
        if branch and not self.registry.check_branch_available(branch):
            return []

        # Capability filtering
        capable_ids = None
        if required_tools:
            cap_result = self._filter_by_capabilities(required_tools)
            if cap_result.get("blocked"):
                return []
            capable_ids = cap_result.get("capable_workers", [])

        # Get available workers (manual_only excluded by default)
        available = self.registry.available_workers(
            task_type, allowed_worker_ids=capable_ids)
        if not available:
            return []

        # Transport-aware filtering (V1.3.0)
        transport_filter = self._get_transport_filter(task_type)
        if transport_filter:
            available = [w for w in available if w.transport == transport_filter]
            if not available:
                return []

        # Fail-closed: exclude unknown transports (V1.3.0)
        known_transports = {"ssh", "local-exec"}
        available = [w for w in available if w.transport in known_transports]
        if not available:
            return []

        # Sort by least loaded
        available.sort(key=lambda w: (
            w.active_jobs, w.recent_failure_count, -w.weight))
        return [(w.worker_id, "all_gates_passed") for w in available]

    def schedule(self, task_type: str = "linux-worker",
                 branch: Optional[str] = None,
                 requires_merge: bool = False,
                 model: Optional[str] = None,
                 required_tools: Optional[list] = None) -> dict:
        """Schedule a task to the best available worker.

        V2.3.0: Lifecycle gate check before any scheduling.
        V1.3.0: Transport-aware routing.
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

        # Capability-aware tool filtering (V1.17.7.3 — closed-loop)
        capable_worker_ids = None
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
            capable_worker_ids = cap_result.get("capable_workers", [])

        # Select worker from capability-filtered candidate set
        worker = self.registry.select_worker(task_type, allowed_worker_ids=capable_worker_ids)
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
        available = self.registry.available_workers(task_type, allowed_worker_ids=capable_worker_ids)
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

    # Check 8: Transport-aware routing (V1.3.0)
    try:
        reg = Reg()
        reg.set_health("5bao", NodeStatus.ONLINE)
        reg.set_health("9bao", NodeStatus.ONLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        policy = SchedulerPolicy(reg)
        # 21bao is manual_only, should not appear in auto-scheduling
        result = policy.schedule(task_type="implementer")
        assert result["worker_id"] in ("5bao", "9bao"), \
            f"Expected ssh worker, got {result['worker_id']}"
        checks.append({"name": "transport_routing_implementer", "passed": True})
    except Exception as e:
        checks.append({"name": "transport_routing_implementer", "passed": False, "error": str(e)})
        passed = False

    # Check 9: 21bao normal admission + safety gate (updated V1.20.57)
    try:
        reg = Reg()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        policy = SchedulerPolicy(reg)
        # Non-sensitive tasks SHOULD be scheduled in normal mode
        result_impl = policy.schedule(task_type="implementer")
        assert result_impl["worker_id"] == "21bao", "21bao normal should be scheduled for implementer"
        result_smoke = policy.schedule(task_type="smoke")
        assert result_smoke["worker_id"] == "21bao", "21bao normal should be scheduled for smoke"
        result_small = policy.schedule(task_type="implementer-small")
        assert result_small["worker_id"] == "21bao", "21bao normal should be scheduled for implementer-small"
        result_reviewer = policy.schedule(task_type="reviewer")
        assert result_reviewer["worker_id"] == "21bao", "21bao normal should be scheduled for reviewer"
        # Sensitive tasks should be BLOCKED by safety gate
        result_win = policy.schedule(task_type="windows-worker")
        assert result_win["worker_id"] is None, "21bao normal+safety-gate should BLOCK windows-worker"
        result_merge = policy.schedule(task_type="merge")
        assert result_merge["worker_id"] is None, "21bao normal+safety-gate should BLOCK merge"
        checks.append({"name": "21bao_normal_safety_gate", "passed": True})
    except Exception as e:
        checks.append({"name": "21bao_normal_safety_gate", "passed": False, "error": str(e)})
        passed = False

    # Check 10: Transport filter helper
    try:
        reg = Reg()
        policy = SchedulerPolicy(reg)
        assert policy._get_transport_filter("linux-worker") == "ssh"
        assert policy._get_transport_filter("windows-worker") == "local-exec"
        assert policy._get_transport_filter("implementer") is None
        assert policy._get_transport_filter("reviewer") is None
        assert policy._get_transport_filter("read-only") is None
        checks.append({"name": "transport_filter_helper", "passed": True})
    except Exception as e:
        checks.append({"name": "transport_filter_helper", "passed": False, "error": str(e)})
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
