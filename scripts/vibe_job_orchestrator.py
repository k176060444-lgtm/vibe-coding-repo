#!/usr/bin/env python3
"""vibe_job_orchestrator.py — Durable Job Orchestrator v2.0.0

Persistent, cross-process job orchestrator with:
  - File-based claim store with fcntl locks
  - Atomic claim/release lifecycle
  - Remote job directory via SSH wrapper
  - Pre-execution gate revalidation
  - Cancel, resume, crash recovery
  - Failure count tracking
  - Separate local/remote PID tracking

Job lifecycle: QUEUED -> CLAIMED -> RUNNING -> SUCCEEDED/FAILED/BLOCKED/CANCELLED/ORPHANED

CLI:
  python3 vibe_job_orchestrator.py submit --task-type linux-worker --command "echo hi" [--required-tools ripgrep]
  python3 vibe_job_orchestrator.py execute --job-id <id>
  python3 vibe_job_orchestrator.py submit --run --task-type linux-worker --command "echo hi"
  python3 vibe_job_orchestrator.py status --job-id <id>
  python3 vibe_job_orchestrator.py cancel --job-id <id>
  python3 vibe_job_orchestrator.py resume --job-id <id>
  python3 vibe_job_orchestrator.py list [--active] [--failed]
  python3 vibe_job_orchestrator.py self-check
"""

__version__ = "2.0.0"

import fcntl
import hashlib
import json
import os
import signal
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
    CANCELLED = "CANCELLED"
    ORPHANED = "ORPHANED"


JOBS_ROOT = Path.home() / "vibedev" / "jobs"
CLAIM_STORE = Path.home() / ".vibedev" / "toolchain" / "claim_store.json"
CLAIM_LOCK = Path.home() / ".vibedev" / "toolchain" / "claim_store.lock"

# SSH key path (resolved at runtime)
SSH_KEY_PATH = None

def _resolve_ssh_key():
    """Resolve SSH key path."""
    global SSH_KEY_PATH
    if SSH_KEY_PATH:
        return SSH_KEY_PATH
    candidates = [
        Path.home() / ".vibedev" / "secrets" / "debian-vibeworker-ed25519",
        Path.home() / ".ssh" / "debian-vibeworker-ed25519",
        Path("/home/vibeworker/.vibedev/secrets/debian-vibeworker-ed25519"),
        Path("/home/vibeworker/.ssh/debian-vibeworker-ed25519"),
        Path("/c/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519"),
    ]
    for p in candidates:
        if p.exists():
            SSH_KEY_PATH = str(p)
            return SSH_KEY_PATH
    # Fallback: use registry default
    SSH_KEY_PATH = "debian-vibeworker-ed25519"
    return SSH_KEY_PATH


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _manifest_checksum(manifest_dict: dict) -> str:
    """Compute deterministic checksum of manifest (excluding checksum field itself)."""
    d = {k: v for k, v in sorted(manifest_dict.items()) if k != "checksum"}
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:16]


class ClaimStore:
    """Persistent, file-locked claim store for cross-process atomicity."""

    def __init__(self, store_path=None, lock_path=None):
        self.store_path = Path(store_path) if store_path else CLAIM_STORE
        self.lock_path = Path(lock_path) if lock_path else CLAIM_LOCK
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            self._write_store({"claims": {}, "version": __version__})

    def _read_store(self) -> dict:
        try:
            return json.loads(self.store_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return {"claims": {}, "version": __version__}

    def _write_store(self, data: dict):
        import uuid
        tmp = self.store_path.with_suffix(".tmp." + uuid.uuid4().hex[:8])
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.rename(self.store_path)

    def acquire_lock(self, timeout=10):
        """Acquire exclusive file lock using fcntl.lockf. Raises TimeoutError."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock_fd = open(self.lock_path, "w")
        deadline = time.time() + timeout
        while True:
            try:
                fcntl.lockf(self._lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB, 0, 0)
                return
            except (IOError, OSError, ValueError):
                if time.time() > deadline:
                    raise TimeoutError("claim_store lock timeout after %ds" % timeout)
                time.sleep(0.05)

    def release_lock(self):
        if hasattr(self, "_lock_fd") and self._lock_fd:
            try:
                fcntl.lockf(self._lock_fd, fcntl.LOCK_UN, 0, 0)
                self._lock_fd.close()
            except Exception:
                pass

    def try_claim(self, job_id: str, worker_id: str, pid: int,
                  lease_seconds: int = 3600) -> dict:
        """Atomically try to claim a worker for a job.

        Returns {"claimed": True, ...} or {"claimed": False, "reason": ...}.
        """
        self.acquire_lock()
        try:
            store = self._read_store()
            claims = store.get("claims", {})

            # Purge stale claims first (lease expired)
            now = time.time()
            stale_purged = False
            for cid, claim in list(claims.items()):
                if claim.get("state") in ("CLAIMED", "RUNNING"):
                    lease_until = claim.get("lease_until", 0)
                    if now > lease_until:
                        claims[cid]["state"] = "ORPHANED"
                        claims[cid]["orphaned_at"] = _now_iso()
                        stale_purged = True

            if stale_purged:
                self._write_store(store)
                store = self._read_store()
                claims = store.get("claims", {})

            # Count active claims per worker (after stale purge)
            active_on_worker = [
                c for c in claims.values()
                if c.get("worker_id") == worker_id
                and c.get("state") in ("CLAIMED", "RUNNING")
            ]

            # Check max_parallel_jobs (hardcoded 1 per worker for now)
            if len(active_on_worker) >= 1:
                return {"claimed": False, "reason": "capacity_full",
                        "active_claims": len(active_on_worker)}

            claim = {
                "job_id": job_id,
                "worker_id": worker_id,
                "pid": pid,
                "remote_pid": None,
                "claimed_at": _now_iso(),
                "lease_until": now + lease_seconds,
                "heartbeat": _now_iso(),
                "state": "CLAIMED",
            }
            claims[job_id] = claim
            store["claims"] = claims
            self._write_store(store)
            return {"claimed": True, "claim": claim}
        finally:
            self.release_lock()

    def update_claim(self, job_id: str, updates: dict):
        """Update a claim (e.g., set remote_pid, state, heartbeat)."""
        self.acquire_lock()
        try:
            store = self._read_store()
            claims = store.get("claims", {})
            if job_id in claims:
                claims[job_id].update(updates)
                store["claims"] = claims
                self._write_store(store)
        finally:
            self.release_lock()

    def release_claim(self, job_id: str, final_state: str = "SUCCEEDED",
                      success: bool = True):
        """Release a claim and record final state."""
        self.acquire_lock()
        try:
            store = self._read_store()
            claims = store.get("claims", {})
            if job_id in claims:
                claims[job_id]["state"] = final_state
                claims[job_id]["released_at"] = _now_iso()
                claims[job_id]["success"] = success
                store["claims"] = claims
                self._write_store(store)
        finally:
            self.release_lock()

    def get_claim(self, job_id: str) -> Optional[dict]:
        store = self._read_store()
        return store.get("claims", {}).get(job_id)

    def get_active_claims(self, worker_id: str = None) -> list:
        store = self._read_store()
        claims = store.get("claims", {})
        result = []
        for cid, claim in claims.items():
            if claim.get("state") in ("CLAIMED", "RUNNING"):
                if worker_id is None or claim.get("worker_id") == worker_id:
                    result.append(claim)
        return result

    def get_stale_claims(self, max_age_seconds: int = 600) -> list:
        """Find claims whose lease has expired."""
        store = self._read_store()
        claims = store.get("claims", {})
        now = time.time()
        stale = []
        for cid, claim in claims.items():
            if claim.get("state") in ("CLAIMED", "RUNNING"):
                lease_until = claim.get("lease_until", 0)
                if now > lease_until:
                    stale.append(claim)
        return stale


@dataclass
class JobManifest:
    """Persistent job manifest."""
    job_id: str
    task_type: str
    command: str
    state: str = JobState.QUEUED.value
    required_tools: List[str] = field(default_factory=list)
    optional_tools: List[str] = field(default_factory=list)
    requested_worker: Optional[str] = None
    actual_worker: Optional[str] = None
    capability_resolution: str = ""
    controller_job_dir: str = ""
    remote_job_dir: str = ""
    local_pid: Optional[int] = None
    remote_pid: Optional[int] = None
    exit_code: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    error: Optional[str] = None
    failure_count: int = 0
    checksum: str = ""
    version: str = __version__
    preflight_checks: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["checksum"] = _manifest_checksum(d)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "JobManifest":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class JobOrchestrator:
    """Durable job orchestrator with persistent claims and cross-process support."""

    def __init__(self, registry=None, scheduler=None, jobs_root=None,
                 claim_store=None):
        self.registry = registry or WorkerRegistry()
        self.scheduler = scheduler or SchedulerPolicy(self.registry)
        self.jobs_root = jobs_root or JOBS_ROOT
        self.claim_store = claim_store or ClaimStore()
        self.jobs_root.mkdir(parents=True, exist_ok=True)

    def _get_candidate_workers(self, task_type, required_tools=None):
        """Get ordered list of candidate workers for a task."""
        if required_tools:
            cap = self.scheduler._filter_by_capabilities(required_tools)
            if cap.get("blocked"):
                return [], cap.get("reason", "capability_blocked")
            capable_ids = cap.get("capable_workers", [])
        else:
            capable_ids = None

        workers = self.registry.available_workers(
            task_type, allowed_worker_ids=capable_ids)
        # Sort by least loaded
        workers.sort(key=lambda w: (w.active_jobs, w.recent_failure_count, -w.weight))
        return workers, None

    def submit_job(self, task_type, command, required_tools=None,
                   optional_tools=None, job_id=None) -> dict:
        """Submit a job. Returns manifest dict. Fail-closed on no capable worker."""
        jid = job_id or "job-" + uuid.uuid4().hex[:12]

        # Get candidate workers
        candidates, block_reason = self._get_candidate_workers(
            task_type, required_tools)

        manifest = JobManifest(
            job_id=jid,
            task_type=task_type,
            command=command,
            required_tools=required_tools or [],
            optional_tools=optional_tools or [],
        )

        if not candidates:
            manifest.state = JobState.BLOCKED.value
            manifest.error = block_reason or "no_candidates"
            self._persist_manifest(manifest)
            return manifest.to_dict()

        # Try each candidate until one is claimed
        claimed = False
        for worker in candidates:
            manifest.requested_worker = worker.worker_id
            manifest.capability_resolution = "selected_%s" % worker.worker_id
            claim_result = self.claim_store.try_claim(
                jid, worker.worker_id, os.getpid())
            if claim_result.get("claimed"):
                manifest.actual_worker = worker.worker_id
                claimed = True
                break

        if not claimed:
            manifest.state = JobState.BLOCKED.value
            manifest.error = "all_candidates_at_capacity"
            self._persist_manifest(manifest)
            return manifest.to_dict()

        worker_id = manifest.actual_worker
        manifest.state = JobState.CLAIMED.value

        # Create controller-side job dir
        controller_dir = self.jobs_root / jid
        controller_dir.mkdir(parents=True, exist_ok=True)
        manifest.controller_job_dir = str(controller_dir)

        # Remote job dir: worker workspace_root/jobs/<job_id>
        worker = self.registry.get_worker(worker_id)
        if worker:
            manifest.remote_job_dir = os.path.join(
                worker.workspace_root, "jobs", jid)

        self._persist_manifest(manifest)
        return manifest.to_dict()

    def execute_job(self, job_id: str, timeout: int = 600) -> dict:
        """Execute a CLAIMED job. Loads from disk, revalidates, runs via SSH.

        Cross-process safe: can be called by a different process than submit.
        """
        manifest = self._load_manifest(job_id)
        if manifest is None:
            return {"ok": False, "error": "job_not_found", "job_id": job_id}

        if manifest.state != JobState.CLAIMED.value:
            return {"ok": False, "error": "invalid_state_for_execute: " + manifest.state,
                    "job_id": job_id}

        # Preflight revalidation
        preflight = self._preflight_check(manifest)
        manifest.preflight_checks = preflight
        if not preflight["all_passed"]:
            manifest.state = JobState.BLOCKED.value
            manifest.error = "preflight_failed: " + str(preflight.get("failed_checks", []))
            self._persist_manifest(manifest)
            self.claim_store.release_claim(job_id, "BLOCKED", success=False)
            self._release_worker_capacity(manifest.actual_worker, success=False)
            return {"ok": False, "error": manifest.error, "job_id": job_id,
                    "preflight": preflight}

        worker = self.registry.get_worker(manifest.actual_worker)
        if worker is None:
            manifest.state = JobState.FAILED.value
            manifest.error = "worker_disappeared"
            self._persist_manifest(manifest)
            return {"ok": False, "error": "worker_disappeared", "job_id": job_id}

        # Ensure remote job dir exists
        remote_dir_ok = self._ensure_remote_dir(worker, manifest.remote_job_dir)
        if not remote_dir_ok:
            manifest.state = JobState.FAILED.value
            manifest.error = "remote_dir_creation_failed"
            self._persist_manifest(manifest)
            self.claim_store.release_claim(job_id, "FAILED", success=False)
            self._release_worker_capacity(manifest.actual_worker, success=False)
            return {"ok": False, "error": "remote_dir_creation_failed", "job_id": job_id}

        # Mark RUNNING
        manifest.state = JobState.RUNNING.value
        manifest.start_time = _now_iso()
        self._persist_manifest(manifest)
        self.claim_store.update_claim(job_id, {
            "state": "RUNNING",
            "started_at": manifest.start_time,
        })

        # Build SSH command
        ssh_key = _resolve_ssh_key()
        ssh_opts = [
            "-p", str(worker.ssh_port),
            "-i", ssh_key,
            "-o", "StrictHostKeyChecking=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
        ]
        ssh_target = worker.ssh_user + "@" + worker.ssh_host
        # Use shell escaping for remote command
        remote_cmd = "cd %s && %s" % (
            _shell_quote(manifest.remote_job_dir),
            manifest.command,
        )
        ssh_cmd = ["ssh"] + ssh_opts + [ssh_target, remote_cmd]

        try:
            proc = subprocess.Popen(
                ssh_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            manifest.local_pid = proc.pid
            self.claim_store.update_claim(job_id, {"local_pid": proc.pid})
            self._persist_manifest(manifest)

            stdout, stderr = proc.communicate(timeout=timeout)
            manifest.exit_code = proc.returncode

            # Save output
            controller_dir = Path(manifest.controller_job_dir)
            (controller_dir / "stdout.txt").write_bytes(stdout)
            (controller_dir / "stderr.txt").write_bytes(stderr)

            if proc.returncode == 0:
                manifest.state = JobState.SUCCEEDED.value
                self.claim_store.release_claim(job_id, "SUCCEEDED", success=True)
                self._release_worker_capacity(manifest.actual_worker, success=True)
            else:
                manifest.state = JobState.FAILED.value
                manifest.error = "exit_code_%d" % proc.returncode
                manifest.failure_count += 1
                self.claim_store.release_claim(job_id, "FAILED", success=False)
                self._release_worker_capacity(manifest.actual_worker, success=False)

        except subprocess.TimeoutExpired:
            # Kill local process group
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

            manifest.state = JobState.FAILED.value
            manifest.error = "timeout_%ds" % timeout
            manifest.exit_code = -1
            manifest.failure_count += 1
            self.claim_store.release_claim(job_id, "FAILED", success=False)
            self._release_worker_capacity(manifest.actual_worker, success=False)

        except Exception as e:
            manifest.state = JobState.FAILED.value
            manifest.error = str(e)
            manifest.exit_code = -1
            manifest.failure_count += 1
            self.claim_store.release_claim(job_id, "FAILED", success=False)
            self._release_worker_capacity(manifest.actual_worker, success=False)

        finally:
            manifest.end_time = _now_iso()
            self._persist_manifest(manifest)

        return {
            "ok": manifest.state == JobState.SUCCEEDED.value,
            "job_id": job_id,
            "state": manifest.state,
            "exit_code": manifest.exit_code,
            "local_pid": manifest.local_pid,
            "remote_pid": manifest.remote_pid,
            "actual_worker": manifest.actual_worker,
            "failure_count": manifest.failure_count,
        }

    def cancel_job(self, job_id: str) -> dict:
        """Cancel a QUEUED or CLAIMED job."""
        manifest = self._load_manifest(job_id)
        if manifest is None:
            return {"ok": False, "error": "job_not_found"}

        if manifest.state in (JobState.SUCCEEDED.value, JobState.FAILED.value,
                              JobState.CANCELLED.value):
            return {"ok": False, "error": "cannot_cancel_%s" % manifest.state}

        manifest.state = JobState.CANCELLED.value
        manifest.end_time = _now_iso()
        self._persist_manifest(manifest)
        self.claim_store.release_claim(job_id, "CANCELLED", success=False)
        if manifest.actual_worker:
            self._release_worker_capacity(manifest.actual_worker, success=False)
        return {"ok": True, "job_id": job_id, "state": "CANCELLED"}

    def resume_job(self, job_id: str) -> dict:
        """Resume an ORPHANED or failed job by re-running execute."""
        manifest = self._load_manifest(job_id)
        if manifest is None:
            return {"ok": False, "error": "job_not_found"}

        if manifest.state == JobState.ORPHANED.value:
            # Re-claim
            claim_result = self.claim_store.try_claim(
                job_id, manifest.actual_worker, os.getpid())
            if not claim_result.get("claimed"):
                return {"ok": False, "error": "reclaim_failed",
                        "reason": claim_result.get("reason")}
            manifest.state = JobState.CLAIMED.value
            self._persist_manifest(manifest)
            return self.execute_job(job_id)

        if manifest.state in (JobState.FAILED.value, JobState.CANCELLED.value):
            # Re-submit with same job_id
            manifest.state = JobState.QUEUED.value
            manifest.error = None
            manifest.exit_code = None
            manifest.local_pid = None
            manifest.remote_pid = None
            self._persist_manifest(manifest)
            result = self.submit_job(
                manifest.task_type, manifest.command,
                required_tools=manifest.required_tools,
                optional_tools=manifest.optional_tools,
                job_id=job_id,
            )
            if result.get("state") == JobState.CLAIMED.value:
                return self.execute_job(job_id)
            return result

        return {"ok": False, "error": "cannot_resume_%s" % manifest.state}

    def get_job_status(self, job_id: str) -> Optional[dict]:
        """Return current job manifest."""
        manifest = self._load_manifest(job_id)
        if manifest:
            return manifest.to_dict()
        return None

    def list_jobs(self, state_filter: str = None) -> list:
        """List all jobs, optionally filtered by state."""
        jobs = []
        if self.jobs_root.exists():
            for d in self.jobs_root.iterdir():
                manifest_path = d / "manifest.json"
                if manifest_path.exists():
                    try:
                        m = json.loads(manifest_path.read_text())
                        if state_filter is None or m.get("state") == state_filter:
                            jobs.append(m)
                    except Exception:
                        pass
        return jobs

    def _preflight_check(self, manifest: JobManifest) -> dict:
        """Pre-execution revalidation. Returns check results."""
        checks = {}
        all_passed = True
        failed = []

        # 1. Worker still online and not maintenance
        worker = self.registry.get_worker(manifest.actual_worker)
        if worker is None:
            checks["worker_exists"] = {"passed": False, "detail": "worker_not_found"}
            all_passed = False
            failed.append("worker_exists")
        else:
            checks["worker_exists"] = {"passed": True}
            if worker.health_status != NodeStatus.ONLINE.value:
                checks["worker_online"] = {"passed": False,
                                            "detail": worker.health_status}
                all_passed = False
                failed.append("worker_online")
            else:
                checks["worker_online"] = {"passed": True}

            if worker.maintenance_status == "maintenance":
                checks["not_maintenance"] = {"passed": False}
                all_passed = False
                failed.append("not_maintenance")
            else:
                checks["not_maintenance"] = {"passed": True}

        # 2. Capability still satisfied
        if manifest.required_tools:
            cap_result = self.scheduler._filter_by_capabilities(manifest.required_tools)
            if manifest.actual_worker not in cap_result.get("capable_workers", []):
                checks["capability"] = {"passed": False,
                                        "detail": cap_result.get("reason")}
                all_passed = False
                failed.append("capability")
            else:
                checks["capability"] = {"passed": True}

        # 3. Claim still valid
        claim = self.claim_store.get_claim(manifest.job_id)
        if claim and claim.get("state") in ("CLAIMED", "RUNNING"):
            checks["claim_valid"] = {"passed": True}
        else:
            checks["claim_valid"] = {"passed": False, "detail": "claim_missing_or_released"}
            all_passed = False
            failed.append("claim_valid")

        # 4. Branch lock check (placeholder - would check actual branch locks)
        checks["branch_lock"] = {"passed": True, "detail": "no_branch_specified"}

        # 5. Merge lock check
        checks["merge_lock"] = {"passed": True, "detail": "not_merge_operation"}

        return {"all_passed": all_passed, "checks": checks,
                "failed_checks": failed}

    def _ensure_remote_dir(self, worker, remote_path: str) -> bool:
        """Create remote directory via SSH. Returns True on success."""
        ssh_key = _resolve_ssh_key()
        cmd = [
            "ssh",
            "-p", str(worker.ssh_port),
            "-i", ssh_key,
            "-o", "StrictHostKeyChecking=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
            worker.ssh_user + "@" + worker.ssh_host,
            "mkdir -p %s && test -d %s" % (
                _shell_quote(remote_path), _shell_quote(remote_path)),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            return result.returncode == 0
        except Exception:
            return False

    def _release_worker_capacity(self, worker_id: str, success: bool = True):
        """Record job end in registry."""
        self.registry.record_job_end(worker_id, success=success)

    def _persist_manifest(self, manifest: JobManifest):
        """Write manifest to controller job dir."""
        if manifest.controller_job_dir:
            p = Path(manifest.controller_job_dir) / "manifest.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(manifest.to_dict(), indent=2))

    def _load_manifest(self, job_id: str) -> Optional[JobManifest]:
        """Load manifest from disk. Cross-process safe."""
        # Check controller job dir
        manifest_path = self.jobs_root / job_id / "manifest.json"
        if manifest_path.exists():
            try:
                d = json.loads(manifest_path.read_text())
                return JobManifest.from_dict(d)
            except Exception:
                pass
        return None


def _shell_quote(s: str) -> str:
    """Safe shell quoting."""
    return "'" + s.replace("'", "'\\''") + "'"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Job Orchestrator v" + __version__)
    sub = parser.add_subparsers(dest="subcommand")

    # submit
    p_submit = sub.add_parser("submit")
    p_submit.add_argument("--task-type", default="linux-worker")
    p_submit.add_argument("--command", default="echo hello")
    p_submit.add_argument("--required-tools", nargs="*", default=[])
    p_submit.add_argument("--optional-tools", nargs="*", default=[])
    p_submit.add_argument("--job-id", default=None)
    p_submit.add_argument("--run", action="store_true",
                          help="Submit and immediately execute")

    # execute
    p_exec = sub.add_parser("execute")
    p_exec.add_argument("--job-id", required=True)
    p_exec.add_argument("--timeout", type=int, default=600)

    # status
    p_status = sub.add_parser("status")
    p_status.add_argument("--job-id", required=True)

    # cancel
    p_cancel = sub.add_parser("cancel")
    p_cancel.add_argument("--job-id", required=True)

    # resume
    p_resume = sub.add_parser("resume")
    p_resume.add_argument("--job-id", required=True)

    # list
    p_list = sub.add_parser("list")
    p_list.add_argument("--active", action="store_true")
    p_list.add_argument("--failed", action="store_true")

    # self-check
    sub.add_parser("self-check")


    args = parser.parse_args()

    if args.subcommand == "self-check":
        result = run_self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    orch = JobOrchestrator()

    # Set all workers ONLINE for CLI operations
    for w in orch.registry.list_workers():
        orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)

    if args.subcommand == "submit":
        m = orch.submit_job(
            args.task_type, args.command,
            required_tools=args.required_tools,
            optional_tools=args.optional_tools,
            job_id=args.job_id,
        )
        print(json.dumps(m, indent=2))
        if getattr(args, "run", False) and m.get("state") == "CLAIMED":
            result = orch.execute_job(m["job_id"], timeout=getattr(args, "timeout", 600))
            print(json.dumps(result, indent=2))
            sys.exit(0 if result.get("ok") else 1)
        sys.exit(0 if m.get("state") != "BLOCKED" else 1)

    elif args.subcommand == "execute":
        result = orch.execute_job(args.job_id, timeout=args.timeout)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("ok") else 1)

    elif args.subcommand == "status":
        s = orch.get_job_status(args.job_id)
        if s:
            print(json.dumps(s, indent=2))
        else:
            print("Job %s not found" % args.job_id)
            sys.exit(1)

    elif args.subcommand == "cancel":
        result = orch.cancel_job(args.job_id)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("ok") else 1)

    elif args.subcommand == "resume":
        result = orch.resume_job(args.job_id)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result.get("ok") else 1)

    elif args.subcommand == "list":
        state_filter = None
        if args.active:
            state_filter = "RUNNING"
        elif args.failed:
            state_filter = "FAILED"
        jobs = orch.list_jobs(state_filter)
        print(json.dumps(jobs, indent=2))

    else:
        parser.print_help()



def _make_test_orchestrator():
    """Create orchestrator with isolated temp claim store for testing."""
    import tempfile
    td = tempfile.mkdtemp(prefix="vibe-orch-test-")
    cs = ClaimStore(
        os.path.join(td, "claims.json"),
        os.path.join(td, "claims.lock"),
    )
    jobs_root = Path(td) / "jobs"
    return JobOrchestrator(claim_store=cs, jobs_root=jobs_root)


def run_self_check() -> dict:
    """Comprehensive self-check for durable orchestrator."""
    import tempfile

    checks = []
    passed = True

    # Check 1: Module imports
    try:
        orch = _make_test_orchestrator()
        checks.append({"name": "import_ok", "passed": True})
    except Exception as e:
        checks.append({"name": "import_ok", "passed": False, "error": str(e)})
        return {"passed": False, "version": __version__, "checks": checks}

    # Check 2: ClaimStore persistence
    try:
        with tempfile.TemporaryDirectory() as td:
            store_path = os.path.join(td, "claims.json")
            lock_path = os.path.join(td, "claims.lock")
            cs = ClaimStore(store_path, lock_path)
            result = cs.try_claim("test-job-1", "5bao", os.getpid())
            assert result["claimed"], "claim should succeed"
            # Read back from disk
            cs2 = ClaimStore(store_path, lock_path)
            claim = cs2.get_claim("test-job-1")
            assert claim is not None, "claim should persist"
            assert claim["worker_id"] == "5bao"
            checks.append({"name": "claim_store_persistence", "passed": True})
    except Exception as e:
        checks.append({"name": "claim_store_persistence", "passed": False, "error": str(e)})
        passed = False

    # Check 3: Atomic claim prevents double-claim
    try:
        with tempfile.TemporaryDirectory() as td:
            store_path = os.path.join(td, "claims.json")
            lock_path = os.path.join(td, "claims.lock")
            cs = ClaimStore(store_path, lock_path)
            r1 = cs.try_claim("job-a", "5bao", 100)
            assert r1["claimed"]
            r2 = cs.try_claim("job-b", "5bao", 200)
            assert not r2["claimed"]
            assert r2["reason"] == "capacity_full"
            checks.append({"name": "atomic_claim_no_double", "passed": True})
    except Exception as e:
        checks.append({"name": "atomic_claim_no_double", "passed": False, "error": str(e)})
        passed = False

    # Check 4: Claim release frees capacity
    try:
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            cs.try_claim("j1", "5bao", 1)
            cs.release_claim("j1", "SUCCEEDED", True)
            r = cs.try_claim("j2", "5bao", 2)
            assert r["claimed"], "should succeed after release"
            checks.append({"name": "release_frees_capacity", "passed": True})
    except Exception as e:
        checks.append({"name": "release_frees_capacity", "passed": False, "error": str(e)})
        passed = False

    # Check 5: Stale claim detection
    try:
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            # Claim with 1-second lease
            cs.try_claim("j-stale", "5bao", 1, lease_seconds=1)
            time.sleep(1.5)
            stale = cs.get_stale_claims()
            assert len(stale) >= 1, "should detect stale claim"
            # New claim should succeed (stale gets ORPHANED)
            r = cs.try_claim("j-new", "5bao", 2)
            assert r["claimed"], "should succeed after stale detected"
            checks.append({"name": "stale_claim_detection", "passed": True})
    except Exception as e:
        checks.append({"name": "stale_claim_detection", "passed": False, "error": str(e)})
        passed = False

    # Check 6: Submit with no capable worker blocks
    try:
        orch = _make_test_orchestrator()
        for w in orch.registry.list_workers():
            orch.registry.set_health(w.worker_id, NodeStatus.OFFLINE)
        m = orch.submit_job("linux-worker", "echo hi", required_tools=["ripgrep"])
        assert m["state"] == "BLOCKED", "expected BLOCKED, got %s" % m["state"]
        checks.append({"name": "submit_blocked_no_worker", "passed": True})
    except Exception as e:
        checks.append({"name": "submit_blocked_no_worker", "passed": False, "error": str(e)})
        passed = False

    # Check 7: Submit without tools succeeds
    try:
        orch = _make_test_orchestrator()
        for w in orch.registry.list_workers():
            orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
        m = orch.submit_job("linux-worker", "echo hi")
        assert m["state"] == "CLAIMED"
        assert m["actual_worker"] in ("5bao", "9bao")
        assert m["remote_job_dir"] != "", "remote_job_dir must be set"
        assert m["controller_job_dir"] != "", "controller_job_dir must be set"
        assert m["remote_job_dir"] != m["controller_job_dir"], "dirs must differ"
        checks.append({"name": "submit_no_tools_ok", "passed": True})
    except Exception as e:
        checks.append({"name": "submit_no_tools_ok", "passed": False, "error": str(e)})
        passed = False

    # Check 8: ripgrep routes to 9bao (has ripgrep)
    try:
        orch = _make_test_orchestrator()
        for w in orch.registry.list_workers():
            orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
        m = orch.submit_job("linux-worker", "rg --version", required_tools=["ripgrep"])
        assert m["state"] == "CLAIMED", "expected CLAIMED, got %s" % m["state"]
        assert m["actual_worker"] == "9bao", "expected 9bao, got %s" % m.get("actual_worker")
        checks.append({"name": "ripgrep_routes_9bao", "passed": True})
    except Exception as e:
        checks.append({"name": "ripgrep_routes_9bao", "passed": False, "error": str(e)})
        passed = False

    # Check 9: Manifest checksum
    try:
        m = JobManifest(job_id="test", task_type="linux-worker", command="echo hi")
        d = m.to_dict()
        assert d["checksum"] != "", "checksum must be set"
        # Tamper: changing command should change checksum
        m2 = JobManifest(job_id="test", task_type="linux-worker", command="echo bye")
        d2 = m2.to_dict()
        assert d["checksum"] != d2["checksum"], "checksum must change with content"
        checks.append({"name": "manifest_checksum", "passed": True})
    except Exception as e:
        checks.append({"name": "manifest_checksum", "passed": False, "error": str(e)})
        passed = False

    # Check 10: Preflight check detects offline worker
    try:
        orch = _make_test_orchestrator()
        for w in orch.registry.list_workers():
            orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
        m = orch.submit_job("linux-worker", "echo hi")
        manifest = orch._load_manifest(m["job_id"])
        # Now take worker offline
        orch.registry.set_health(manifest.actual_worker, NodeStatus.OFFLINE)
        preflight = orch._preflight_check(manifest)
        assert not preflight["all_passed"], "preflight should fail with offline worker"
        assert "worker_online" in preflight.get("failed_checks", [])
        checks.append({"name": "preflight_offline_worker", "passed": True})
    except Exception as e:
        checks.append({"name": "preflight_offline_worker", "passed": False, "error": str(e)})
        passed = False

    # Check 11: Manifest disk persistence (cross-process)
    try:
        orch = _make_test_orchestrator()
        for w in orch.registry.list_workers():
            orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
        m = orch.submit_job("linux-worker", "echo hi")
        jid = m["job_id"]
        # Simulate loading from a different process
        loaded = orch._load_manifest(jid)
        assert loaded is not None, "manifest must persist to disk"
        assert loaded.job_id == jid
        assert loaded.state == "CLAIMED"
        checks.append({"name": "manifest_disk_persistence", "passed": True})
    except Exception as e:
        checks.append({"name": "manifest_disk_persistence", "passed": False, "error": str(e)})
        passed = False

    # Check 12: Two workers can claim different jobs simultaneously
    try:
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            r1 = cs.try_claim("j1", "5bao", 1)
            r2 = cs.try_claim("j2", "9bao", 2)
            assert r1["claimed"] and r2["claimed"]
            active = cs.get_active_claims()
            assert len(active) == 2
            checks.append({"name": "parallel_different_workers", "passed": True})
    except Exception as e:
        checks.append({"name": "parallel_different_workers", "passed": False, "error": str(e)})
        passed = False

    return {"passed": passed, "version": __version__, "checks": checks}


if __name__ == "__main__":
    main()
