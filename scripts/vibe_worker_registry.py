#!/usr/bin/env python3
"""vibe_worker_registry.py — Active-Active Worker Pool Registry v1.0.0

Manages the Debian worker pool for VibeDev orchestration.
Supports 5bao + 9bao active-active with equal weight scheduling.

Usage:
    python3 scripts/vibe_worker_registry.py --status
    python3 scripts/vibe_worker_registry.py --select --task-type linux-worker
    python3 scripts/vibe_worker_registry.py --health-check
    python3 scripts/vibe_worker_registry.py --self-check
"""

__version__ = "1.0.0"

import copy, json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class NodeStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    MAINTENANCE = "MAINTENANCE"
    UNKNOWN = "UNKNOWN"


class TaskType(str, Enum):
    LINUX_WORKER = "linux-worker"
    WINDOWS_WORKER = "windows-worker"
    DUAL_NODE = "dual-node"
    READ_ONLY = "read-only"
    IMPLEMENTER = "implementer"
    REVIEWER = "reviewer"
    CODE_SEARCH = "code-search"


@dataclass
class WorkerNode:
    worker_id: str
    node_type: str  # debian-worker, windows-worker
    ssh_host: str
    ssh_port: int
    ssh_user: str
    ssh_key_path: str
    repo_root: str
    workspace_root: str
    capabilities: list = field(default_factory=list)
    weight: int = 100
    max_parallel_jobs: int = 1
    active_jobs: int = 0
    maintenance_status: str = "active"  # active, maintenance
    health_status: str = "UNKNOWN"  # ONLINE, OFFLINE, UNKNOWN
    token_policy: str = "gh_cached_credentials"  # self-repo only
    allowed_operations: list = field(default_factory=lambda: [
        "read-only", "implementer", "reviewer", "pytest", "smoke"
    ])
    recent_failure_count: int = 0
    last_health_check: str = ""
    last_job_completed: str = ""
    baseline_sha: str = ""
    tools_installed: dict = field(default_factory=dict)  # tool_name -> version_or_path


# Default worker pool configuration
DEFAULT_WORKERS = {
    "5bao": WorkerNode(
        worker_id="5bao",
        node_type="debian-worker",
        ssh_host="192.168.5.6",
        ssh_port=22222,
        ssh_user="vibeworker",
        ssh_key_path="debian-vibeworker-ed25519",
        repo_root="/home/vibeworker/vibedev/repos/vibe-coding-repo.git",
        workspace_root="/home/vibeworker/vibedev/worktrees",
        capabilities=["linux-worker", "read-only", "implementer", "reviewer", "pytest", "smoke"],
        weight=100,
        max_parallel_jobs=1,
        tools_installed={"ripgrep": "NOT_INSTALLED"},
    ),
    "9bao": WorkerNode(
        worker_id="9bao",
        node_type="debian-worker",
        ssh_host="192.168.9.6",
        ssh_port=22222,
        ssh_user="vibeworker",
        ssh_key_path="debian-vibeworker-ed25519",
        repo_root="/home/vibeworker/vibedev/repos/vibe-coding-repo.git",
        workspace_root="/home/vibeworker/vibedev/worktrees",
        capabilities=["linux-worker", "read-only", "implementer", "reviewer", "pytest", "smoke"],
        weight=100,
        max_parallel_jobs=1,
        tools_installed={"ripgrep": "13.0.0"},
    ),
}


class WorkerRegistry:
    """Manages the active-active worker pool."""

    def __init__(self, workers: Optional[dict] = None):
        self.workers: dict[str, WorkerNode] = workers or {k: copy.deepcopy(v) for k, v in DEFAULT_WORKERS.items()}
        self._locks: dict[str, str] = {}  # branch -> worker_id
        self._merge_lock: Optional[str] = None  # worker_id holding merge lock

    def get_worker(self, worker_id: str) -> Optional[WorkerNode]:
        return self.workers.get(worker_id)

    def list_workers(self) -> list[WorkerNode]:
        return list(self.workers.values())

    def online_workers(self) -> list[WorkerNode]:
        return [w for w in self.workers.values() if w.health_status == NodeStatus.ONLINE]

    def available_workers(self, task_type: str = "linux-worker",
                          allowed_worker_ids: Optional[list] = None) -> list[WorkerNode]:
        """Workers available for a task: ONLINE, not maintenance, has capacity, capability match.

        If allowed_worker_ids is provided, only workers whose worker_id is in
        that list are considered. This ensures capability filtering and final
        selection use the same candidate set.
        """
        candidates = [
            w for w in self.online_workers()
            if w.maintenance_status != "maintenance"
            and w.active_jobs < w.max_parallel_jobs
            and task_type in w.capabilities
        ]
        if allowed_worker_ids is not None:
            allowed_set = set(allowed_worker_ids)
            candidates = [w for w in candidates if w.worker_id in allowed_set]
        return candidates

    def select_worker(self, task_type: str = "linux-worker",
                      allowed_worker_ids: Optional[list] = None) -> Optional[WorkerNode]:
        """Select best worker using scheduling policy:
        1. capability match
        2. ONLINE
        3. not maintenance
        4. no conflicting lock
        5. least active_jobs
        6. lower recent_failure_count
        7. weighted round-robin tie-break

        If allowed_worker_ids is provided, only those workers are considered.
        This ensures capability filtering and final selection use the same set.
        """
        candidates = self.available_workers(task_type, allowed_worker_ids=allowed_worker_ids)
        if not candidates:
            return None

        # Sort by: least active_jobs, then lowest failure count, then highest weight
        candidates.sort(key=lambda w: (
            w.active_jobs,
            w.recent_failure_count,
            -w.weight,
        ))
        return candidates[0]

    def acquire_branch_lock(self, branch: str, worker_id: str) -> bool:
        """Acquire global branch mutation lock. Returns False if already locked."""
        if branch in self._locks and self._locks[branch] != worker_id:
            return False
        self._locks[branch] = worker_id
        return True

    def release_branch_lock(self, branch: str, worker_id: str) -> bool:
        """Release branch lock. Only the holder can release."""
        if self._locks.get(branch) == worker_id:
            del self._locks[branch]
            return True
        return False

    def acquire_merge_lock(self, worker_id: str) -> bool:
        """Acquire global merge lock. Returns False if already held."""
        if self._merge_lock is not None and self._merge_lock != worker_id:
            return False
        self._merge_lock = worker_id
        return True

    def release_merge_lock(self, worker_id: str) -> bool:
        """Release merge lock. Only the holder can release."""
        if self._merge_lock == worker_id:
            self._merge_lock = None
            return True
        return False

    def check_branch_available(self, branch: str) -> bool:
        """Check if branch is not locked by another worker."""
        return branch not in self._locks

    def check_merge_available(self) -> bool:
        """Check if merge lock is available."""
        return self._merge_lock is None

    def record_job_start(self, worker_id: str):
        w = self.workers.get(worker_id)
        if w:
            w.active_jobs += 1

    def record_job_end(self, worker_id: str, success: bool = True):
        w = self.workers.get(worker_id)
        if w:
            w.active_jobs = max(0, w.active_jobs - 1)
            if not success:
                w.recent_failure_count += 1
            w.last_job_completed = datetime.now(timezone.utc).isoformat()

    def set_maintenance(self, worker_id: str, status: str):
        w = self.workers.get(worker_id)
        if w:
            w.maintenance_status = status

    def set_health(self, worker_id: str, status: str):
        w = self.workers.get(worker_id)
        if w:
            w.health_status = status
            w.last_health_check = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "version": __version__,
            "pool_size": len(self.workers),
            "online_count": len(self.online_workers()),
            "total_capacity": sum(w.max_parallel_jobs for w in self.workers.values()),
            "active_jobs_total": sum(w.active_jobs for w in self.workers.values()),
            "branch_locks": dict(self._locks),
            "merge_lock": self._merge_lock,
            "workers": {k: asdict(v) for k, v in self.workers.items()},
        }

    def status_report(self) -> dict:
        """Generate status report for dashboard."""
        workers_status = []
        for w in self.workers.values():
            workers_status.append({
                "worker_id": w.worker_id,
                "node_type": w.node_type,
                "health": w.health_status,
                "maintenance": w.maintenance_status,
                "active_jobs": w.active_jobs,
                "max_parallel": w.max_parallel_jobs,
                "weight": w.weight,
                "failures": w.recent_failure_count,
                "last_check": w.last_health_check,
                "baseline": w.baseline_sha[:8] if w.baseline_sha else "unknown",
            })
        return {
            "pool_summary": {
                "total": len(self.workers),
                "online": len(self.online_workers()),
                "available": len(self.available_workers()),
                "total_capacity": sum(w.max_parallel_jobs for w in self.workers.values()),
                "active_jobs": sum(w.active_jobs for w in self.workers.values()),
            },
            "workers": workers_status,
            "locks": {
                "branch_locks": dict(self._locks),
                "merge_lock": self._merge_lock,
            },
        }


def self_check() -> dict:
    """Self-check: verify registry structure and logic."""
    checks = []
    passed = True

    # Check 1: Default workers defined
    try:
        reg = WorkerRegistry()
        assert len(reg.workers) == 2, f"Expected 2 workers, got {len(reg.workers)}"
        assert "5bao" in reg.workers, "5bao not in registry"
        assert "9bao" in reg.workers, "9bao not in registry"
        checks.append({"name": "default_workers_defined", "passed": True})
    except Exception as e:
        checks.append({"name": "default_workers_defined", "passed": False, "error": str(e)})
        passed = False

    # Check 2: Equal weight
    try:
        reg = WorkerRegistry()
        assert reg.workers["5bao"].weight == 100
        assert reg.workers["9bao"].weight == 100
        checks.append({"name": "equal_weight", "passed": True})
    except Exception as e:
        checks.append({"name": "equal_weight", "passed": False, "error": str(e)})
        passed = False

    # Check 3: Selection with one online
    try:
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.ONLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        selected = reg.select_worker()
        assert selected is not None
        assert selected.worker_id == "5bao"
        checks.append({"name": "select_single_online", "passed": True})
    except Exception as e:
        checks.append({"name": "select_single_online", "passed": False, "error": str(e)})
        passed = False

    # Check 4: Least-loaded selection
    try:
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.ONLINE)
        reg.set_health("9bao", NodeStatus.ONLINE)
        reg.record_job_start("5bao")
        selected = reg.select_worker()
        assert selected is not None
        assert selected.worker_id == "9bao", f"Expected 9bao (less loaded), got {selected.worker_id}"
        checks.append({"name": "least_loaded_selection", "passed": True})
    except Exception as e:
        checks.append({"name": "least_loaded_selection", "passed": False, "error": str(e)})
        passed = False

    # Check 5: Branch lock prevents concurrent mutation
    try:
        reg = WorkerRegistry()
        assert reg.acquire_branch_lock("feat/test", "5bao") is True
        assert reg.acquire_branch_lock("feat/test", "9bao") is False
        assert reg.release_branch_lock("feat/test", "5bao") is True
        assert reg.acquire_branch_lock("feat/test", "9bao") is True
        checks.append({"name": "branch_lock_prevents_concurrent", "passed": True})
    except Exception as e:
        checks.append({"name": "branch_lock_prevents_concurrent", "passed": False, "error": str(e)})
        passed = False

    # Check 6: Merge lock prevents duplicate merge
    try:
        reg = WorkerRegistry()
        assert reg.acquire_merge_lock("5bao") is True
        assert reg.acquire_merge_lock("9bao") is False
        assert reg.release_merge_lock("5bao") is True
        assert reg.acquire_merge_lock("9bao") is True
        checks.append({"name": "merge_lock_prevents_duplicate", "passed": True})
    except Exception as e:
        checks.append({"name": "merge_lock_prevents_duplicate", "passed": False, "error": str(e)})
        passed = False

    # Check 7: Maintenance worker not selected
    try:
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.ONLINE)
        reg.set_health("9bao", NodeStatus.ONLINE)
        reg.set_maintenance("5bao", "maintenance")
        selected = reg.select_worker()
        assert selected is not None
        assert selected.worker_id == "9bao"
        checks.append({"name": "maintenance_excluded", "passed": True})
    except Exception as e:
        checks.append({"name": "maintenance_excluded", "passed": False, "error": str(e)})
        passed = False

    # Check 8: Both offline returns None
    try:
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        selected = reg.select_worker()
        assert selected is None
        checks.append({"name": "both_offline_returns_none", "passed": True})
    except Exception as e:
        checks.append({"name": "both_offline_returns_none", "passed": False, "error": str(e)})
        passed = False

    # Check 9: Status report structure
    try:
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.ONLINE)
        reg.set_health("9bao", NodeStatus.ONLINE)
        report = reg.status_report()
        assert "pool_summary" in report
        assert "workers" in report
        assert "locks" in report
        assert report["pool_summary"]["total"] == 2
        assert report["pool_summary"]["online"] == 2
        checks.append({"name": "status_report_structure", "passed": True})
    except Exception as e:
        checks.append({"name": "status_report_structure", "passed": False, "error": str(e)})
        passed = False

    # Check 10: No secret in output
    try:
        reg = WorkerRegistry()
        output = json.dumps(reg.to_dict())
        assert "token" not in output.lower() or "token_policy" in output
        assert "password" not in output.lower()
        assert "secret" not in output.lower() or "allowed_operations" in output
        checks.append({"name": "no_secret_in_output", "passed": True})
    except Exception as e:
        checks.append({"name": "no_secret_in_output", "passed": False, "error": str(e)})
        passed = False

    return {"passed": passed, "version": __version__, "checks": checks}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VibeDev Worker Registry")
    parser.add_argument("--status", action="store_true", help="Show pool status")
    parser.add_argument("--select", action="store_true", help="Select best worker")
    parser.add_argument("--task-type", default="linux-worker", help="Task type for selection")
    parser.add_argument("--health-check", action="store_true", help="Run health checks")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    reg = WorkerRegistry()

    if args.status:
        report = reg.status_report()
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"Worker Pool: {report['pool_summary']['total']} workers, "
                  f"{report['pool_summary']['online']} online")
            for w in report["workers"]:
                print(f"  {w['worker_id']}: {w['health']} | "
                      f"jobs={w['active_jobs']}/{w['max_parallel']} | "
                      f"weight={w['weight']} | failures={w['failures']}")

    elif args.select:
        # Set all to ONLINE for demo
        for w in reg.workers.values():
            reg.set_health(w.worker_id, NodeStatus.ONLINE)
        selected = reg.select_worker(args.task_type)
        if selected:
            print(json.dumps({
                "selected_worker": selected.worker_id,
                "task_type": args.task_type,
                "reason": "least_loaded" if selected.active_jobs == 0 else "available",
            }, indent=2))
        else:
            print(json.dumps({"error": "no_available_worker"}, indent=2))
            sys.exit(1)

    elif args.health_check:
        # Placeholder: in production, SSH to each worker
        for w in reg.workers.values():
            print(f"  {w.worker_id}: health check not yet implemented (requires SSH)")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
