#!/usr/bin/env python3
"""vibe_job_orchestrator.py -- Job Orchestrator v1.0.0

Minimal job orchestrator that:
  1. Accepts a work order with required_tools
  2. Calls scheduler.schedule(task_type, required_tools=...) to find a capable worker
  3. Claims worker capacity (increments active_jobs)
  4. Creates isolated job directory under ~/vibedev/jobs/
  5. Executes command via SSH wrapper
  6. Tracks PID, start/end time, exit code
  7. Releases capacity on completion
  8. Records job manifest with requested/actual worker, required_tools, capability resolution

Job lifecycle: QUEUED -> CLAIMED -> RUNNING -> SUCCEEDED/FAILED/BLOCKED

Fail-closed on:
  - capability mismatch
  - worker offline/maintenance
  - no capable worker
  - capacity full

Version: 1.0.0
"""

__version__ = "1.0.0"

import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
from vibe_worker_registry import WorkerRegistry, NodeStatus
from vibe_scheduler_policy import SchedulerPolicy


class JobState(str, Enum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


JOBS_ROOT = Path.home() / "vibedev" / "jobs"


@dataclass
class JobManifest:
    """Record of a scheduled job."""
    job_id: str
    task_type: str
    command: str
    state: str = JobState.QUEUED.value
    required_tools: List[str] = field(default_factory=list)
    optional_tools: List[str] = field(default_factory=list)
    requested_worker: Optional[str] = None
    actual_worker: Optional[str] = None
    capability_resolution: str = ""
    job_dir: str = ""
    pid: Optional[int] = None
    exit_code: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    error: Optional[str] = None
    version: str = __version__

    def to_dict(self) -> dict:
        return asdict(self)


class JobOrchestrator:
    """Minimal job orchestrator with capability-aware scheduling."""

    def __init__(self, registry=None, scheduler=None, jobs_root=None):
        self.registry = registry or WorkerRegistry()
        self.scheduler = scheduler or SchedulerPolicy(self.registry)
        self.jobs_root = jobs_root or JOBS_ROOT
        self._jobs: Dict[str, JobManifest] = {}

    def submit_job(self, task_type, command, required_tools=None,
                   optional_tools=None, job_id=None):
        """Submit a job for execution.

        Returns job manifest dict.  Fail-closed: if no capable worker is
        available, returns BLOCKED state.
        """
        jid = job_id or "job-" + uuid.uuid4().hex[:12]

        manifest = JobManifest(
            job_id=jid,
            task_type=task_type,
            command=command,
            required_tools=required_tools or [],
            optional_tools=optional_tools or [],
        )

        # 1. Schedule via capability-aware scheduler
        schedule_result = self.scheduler.schedule(
            task_type=task_type,
            required_tools=required_tools,
        )

        manifest.capability_resolution = schedule_result.get("selection_reason", "")

        # 2. Fail-closed: check schedule result
        if schedule_result.get("pending") or schedule_result.get("worker_id") is None:
            manifest.state = JobState.BLOCKED.value
            manifest.error = schedule_result.get(
                "pending_reason",
                schedule_result.get("selection_reason", "unknown_block"),
            )
            self._jobs[jid] = manifest
            return manifest.to_dict()

        worker_id = schedule_result["worker_id"]
        manifest.requested_worker = worker_id
        manifest.actual_worker = worker_id

        # 3. Claim capacity
        worker = self.registry.get_worker(worker_id)
        if worker is None:
            manifest.state = JobState.BLOCKED.value
            manifest.error = "worker_disappeared_after_schedule"
            self._jobs[jid] = manifest
            return manifest.to_dict()

        if worker.active_jobs >= worker.max_parallel_jobs:
            manifest.state = JobState.BLOCKED.value
            manifest.error = "capacity_full"
            self._jobs[jid] = manifest
            return manifest.to_dict()

        self.registry.record_job_start(worker_id)
        manifest.state = JobState.CLAIMED.value

        # 4. Create isolated job directory
        job_dir = self.jobs_root / jid
        job_dir.mkdir(parents=True, exist_ok=True)
        manifest.job_dir = str(job_dir)

        # Write manifest to job dir
        manifest_path = job_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2))

        self._jobs[jid] = manifest
        return manifest.to_dict()

    def execute_job(self, job_id):
        """Execute a CLAIMED job via SSH.

        Captures PID, start/end time, exit code.
        Releases capacity on completion.
        """
        manifest = self._jobs.get(job_id)
        if manifest is None:
            return {"ok": False, "error": "job_not_found", "job_id": job_id}

        if manifest.state != JobState.CLAIMED.value:
            return {
                "ok": False,
                "error": "invalid_state_for_execute: " + manifest.state,
                "job_id": job_id,
            }

        worker = self.registry.get_worker(manifest.actual_worker)
        if worker is None:
            manifest.state = JobState.FAILED.value
            manifest.error = "worker_not_found"
            self._write_manifest(manifest)
            return {"ok": False, "error": "worker_not_found", "job_id": job_id}

        # Build SSH command
        ssh_opts = [
            "-p", str(worker.ssh_port),
            "-i", worker.ssh_key_path,
            "-o", "StrictHostKeyChecking=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
        ]
        ssh_target = worker.ssh_user + "@" + worker.ssh_host
        remote_cmd = "cd " + manifest.job_dir + " && " + manifest.command

        ssh_cmd = ["ssh"] + ssh_opts + [ssh_target, remote_cmd]

        manifest.state = JobState.RUNNING.value
        manifest.start_time = datetime.now(timezone.utc).isoformat()
        self._write_manifest(manifest)

        try:
            proc = subprocess.Popen(
                ssh_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            manifest.pid = proc.pid

            stdout, stderr = proc.communicate(timeout=600)
            manifest.exit_code = proc.returncode

            # Save output
            job_dir = Path(manifest.job_dir)
            (job_dir / "stdout.txt").write_bytes(stdout)
            (job_dir / "stderr.txt").write_bytes(stderr)

            if proc.returncode == 0:
                manifest.state = JobState.SUCCEEDED.value
            else:
                manifest.state = JobState.FAILED.value
                manifest.error = "exit_code_" + str(proc.returncode)

        except subprocess.TimeoutExpired:
            proc.kill()
            manifest.state = JobState.FAILED.value
            manifest.error = "timeout_600s"
            manifest.exit_code = -1

        except Exception as e:
            manifest.state = JobState.FAILED.value
            manifest.error = str(e)
            manifest.exit_code = -1

        finally:
            manifest.end_time = datetime.now(timezone.utc).isoformat()
            self._write_manifest(manifest)
            # Release capacity
            self.release_capacity(manifest.actual_worker)

        return {
            "ok": manifest.state == JobState.SUCCEEDED.value,
            "job_id": job_id,
            "state": manifest.state,
            "exit_code": manifest.exit_code,
            "pid": manifest.pid,
        }

    def release_capacity(self, worker_id):
        """Decrement active_jobs for a worker."""
        worker = self.registry.get_worker(worker_id)
        if worker is None:
            return False
        self.registry.record_job_end(worker_id, success=True)
        return True

    def get_job_status(self, job_id):
        """Return current job manifest or None."""
        manifest = self._jobs.get(job_id)
        if manifest is not None:
            return manifest.to_dict()
        # Try loading from disk
        manifest_path = self.jobs_root / job_id / "manifest.json"
        if manifest_path.exists():
            return json.loads(manifest_path.read_text())
        return None

    def _write_manifest(self, manifest):
        """Persist manifest to job directory."""
        if manifest.job_dir:
            p = Path(manifest.job_dir) / "manifest.json"
            p.write_text(json.dumps(manifest.to_dict(), indent=2))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Job Orchestrator v" + __version__)
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--task-type", default="linux-worker")
    parser.add_argument("--command", default="echo hello")
    parser.add_argument("--required-tools", nargs="*", default=[])
    parser.add_argument("--status", help="Get job status by ID")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.self_check:
        checks = []
        passed = True

        # Check 1: Module imports
        try:
            orch = JobOrchestrator()
            checks.append({"name": "import_ok", "passed": True})
        except Exception as e:
            checks.append({"name": "import_ok", "passed": False, "error": str(e)})
            passed = False

        # Check 2: Submit with no capable worker blocks
        try:
            orch = JobOrchestrator()
            for w in orch.registry.list_workers():
                orch.registry.set_health(w.worker_id, NodeStatus.OFFLINE)
            m = orch.submit_job("linux-worker", "echo hi", required_tools=["ripgrep"])
            assert m["state"] == "BLOCKED"
            checks.append({"name": "submit_blocked_no_worker", "passed": True})
        except Exception as e:
            checks.append({"name": "submit_blocked_no_worker", "passed": False, "error": str(e)})
            passed = False

        # Check 3: Submit without required_tools succeeds
        try:
            orch = JobOrchestrator()
            for w in orch.registry.list_workers():
                orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
            m = orch.submit_job("linux-worker", "echo hi")
            assert m["state"] == "CLAIMED"
            assert m["actual_worker"] in ("5bao", "9bao")
            checks.append({"name": "submit_no_tools_ok", "passed": True})
        except Exception as e:
            checks.append({"name": "submit_no_tools_ok", "passed": False, "error": str(e)})
            passed = False

        # Check 4: release_capacity
        try:
            orch = JobOrchestrator()
            for w in orch.registry.list_workers():
                orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
            m = orch.submit_job("linux-worker", "echo hi")
            wid = m["actual_worker"]
            w = orch.registry.get_worker(wid)
            assert w.active_jobs == 1
            orch.release_capacity(wid)
            assert w.active_jobs == 0
            checks.append({"name": "release_capacity", "passed": True})
        except Exception as e:
            checks.append({"name": "release_capacity", "passed": False, "error": str(e)})
            passed = False

        result = {"passed": passed, "version": __version__, "checks": checks}
        print(json.dumps(result, indent=2))
        sys.exit(0 if passed else 1)

    if args.status:
        orch = JobOrchestrator()
        s = orch.get_job_status(args.status)
        print(json.dumps(s, indent=2) if s else "Job " + args.status + " not found")
        return 0 if s else 1

    if args.submit:
        orch = JobOrchestrator()
        for w in orch.registry.list_workers():
            orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
        m = orch.submit_job(args.task_type, args.command, required_tools=args.required_tools)
        print(json.dumps(m, indent=2))
        return 0 if m["state"] != "BLOCKED" else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
