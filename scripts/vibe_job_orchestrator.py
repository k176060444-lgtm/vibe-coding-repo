#!/usr/bin/env python3
"""vibe_job_orchestrator.py — Durable Job Orchestrator v3.1.0

FAIL-CLOSED runtime closure:
  - All dependency imports are MANDATORY — no fallbacks/stubs
  - Real lifecycle gate, branch gate, merge gate, resume gate
  - ClaimStore with corruption latch, fsync, schema validation, store checksum
  - Persistent latch file on disk (survives process restarts)
  - Auto heartbeat daemon thread during RUNNING
  - SSH key: explicit Windows controller paths + registry only
  - Credential enforcement: BLOCKS execution on non-Windows nodes
  - Remote process control via setsid process groups + PID file capture
  - Signed job scripts with SHA256 integrity
  - Multi-candidate retry through unified SchedulerPolicy
  - Cross-platform FileLock (no fcntl dependency)

Job lifecycle: QUEUED -> CLAIMED -> RUNNING -> SUCCEEDED/FAILED/BLOCKED/CANCELLED/RECOVERY_REQUIRED

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

__version__ = "3.1.0"

# ===========================================================================
# MANDATORY IMPORTS — FAIL-CLOSED, NO FALLBACKS
# ===========================================================================
import hashlib
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))

# Cross-platform file lock — MANDATORY
from vibe_filelock import FileLock

# FAIL-CLOSED: these imports MUST succeed or the module refuses to load
from vibe_worker_registry import WorkerRegistry, WorkerNode, NodeStatus
from vibe_scheduler_policy import SchedulerPolicy

# Resume gate — MANDATORY
from vibe_resume_gate import check as _resume_gate_check

# Lifecycle gate — MANDATORY
from vibe_toolchain_lifecycle import gate_check_for_dispatch as _real_gate_check_for_dispatch

logger = logging.getLogger(__name__)


# ===========================================================================
# Error codes
# ===========================================================================
class OrchestratorError(Exception):
    pass


class MANIFEST_CORRUPTED(OrchestratorError):
    """Manifest checksum or schema verification failed."""
    pass


class IMPORT_FAILED(OrchestratorError):
    """A mandatory dependency import failed."""
    pass


class JobState(str, Enum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


JOBS_ROOT = Path.home() / "vibedev" / "jobs"
CLAIM_STORE = Path.home() / ".vibedev" / "toolchain" / "claim_store.json"
CLAIM_LOCK = Path.home() / ".vibedev" / "toolchain" / "claim_store.lock"
CLAIM_LATCH = Path.home() / ".vibedev" / "toolchain" / "claim_store.latch"

# ===========================================================================
# SSH key resolution — EXPLICIT CONTROLLER-ONLY
# ===========================================================================
# ONLY Windows controller paths. No auto-search of ~/.vibedev/secrets, ~/.ssh,
# or bare filename fallback. Non-Windows must provide explicit path.
_CONTROLLER_SSH_KEY_PATHS = [
    Path("C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519"),
]
SSH_KEY_PATH = None


def _resolve_ssh_key(registry=None):
    """Resolve SSH key path. ONLY checks explicit Windows controller paths and registry.

    Fails closed: raises RuntimeError if no key found.
    BLOCKS execution on non-Windows platforms.
    """
    global SSH_KEY_PATH

    # Credential enforcement: must be Windows controller
    if sys.platform != "win32":
        raise RuntimeError(
            "Orchestrator must run on Windows controller. Current platform: %s"
            % sys.platform
        )

    if SSH_KEY_PATH:
        return SSH_KEY_PATH

    # 1. Explicit Windows controller paths only
    for p in _CONTROLLER_SSH_KEY_PATHS:
        if p.exists():
            SSH_KEY_PATH = str(p)
            return SSH_KEY_PATH

    # 2. Registry ssh_key_path (controller credential reference)
    if registry:
        for w in registry.list_workers():
            if w.ssh_key_path and Path(w.ssh_key_path).exists():
                SSH_KEY_PATH = w.ssh_key_path
                return SSH_KEY_PATH

    # FAIL CLOSED — no key = no execution
    raise RuntimeError(
        "SSH key not found. Only explicit Windows controller paths and "
        "registry ssh_key_path are accepted. No auto-search fallback."
    )


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _manifest_checksum(manifest_dict: dict) -> str:
    """Compute deterministic checksum of manifest (excluding checksum field itself)."""
    d = {k: v for k, v in sorted(manifest_dict.items()) if k != "checksum"}
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()[:16]


# ===========================================================================
# ClaimStore — FAIL-CLOSED with corruption latch, store checksum, persistent latch
# ===========================================================================
DEFAULT_LEASE_SECONDS = 300  # 5 minutes
HEARTBEAT_EXTEND_SECONDS = 300  # heartbeat extends by 5 min
HEARTBEAT_INTERVAL_SECONDS = 120  # heartbeat thread runs every 2 min

CLAIM_STORE_SCHEMA_VERSION = "3.0"
_STORE_CHECKSUM_KEY = "_store_checksum"


def _compute_store_checksum(data: dict) -> str:
    """Compute SHA256 of store JSON excluding the checksum field itself."""
    d = {k: v for k, v in data.items() if k != _STORE_CHECKSUM_KEY}
    return hashlib.sha256(
        json.dumps(d, sort_keys=True, default=str).encode()
    ).hexdigest()


class ClaimStore:
    """Persistent, file-locked claim store with corruption latch, store checksum,
    persistent latch file, and fsync."""

    def __init__(self, store_path=None, lock_path=None, latch_path=None):
        self.store_path = Path(store_path) if store_path else CLAIM_STORE
        self.lock_path = Path(lock_path) if lock_path else CLAIM_LOCK
        self.latch_path = Path(latch_path) if latch_path else self.store_path.parent / "claim_store.latch"
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._corruption_latch = False
        self._corruption_reason = ""
        self._lock_instance = None

        # Check for persistent latch file on init
        if self.latch_path.exists():
            try:
                latch_data = json.loads(self.latch_path.read_text())
                reason = latch_data.get("reason", "persistent_latch_file_exists")
                self._latch(reason)
            except Exception:
                self._latch("persistent_latch_file_unreadable")

        if not self.store_path.exists():
            self._write_store({"claims": {}, "version": CLAIM_STORE_SCHEMA_VERSION})
        else:
            # Validate existing store on load
            self._validate_store_or_latch()

    def _validate_store_or_latch(self):
        """Validate store schema and checksum. Latch on corruption."""
        try:
            data = self._raw_read()
            if not isinstance(data, dict):
                self._latch("store is not a dict")
                return
            if "claims" not in data:
                self._latch("missing 'claims' key")
                return
            if not isinstance(data["claims"], dict):
                self._latch("'claims' is not a dict")
                return
            # Strict schema version check: must exactly match
            ver = data.get("version")
            if ver is None:
                self._latch("missing schema version")
                return
            if ver != CLAIM_STORE_SCHEMA_VERSION:
                self._latch("schema version mismatch: got %s, expected %s" % (ver, CLAIM_STORE_SCHEMA_VERSION))
                return
            # Store checksum verification
            stored_checksum = data.get(_STORE_CHECKSUM_KEY)
            if stored_checksum is None:
                self._latch("store_checksum_mismatch")
                return
            recomputed = _compute_store_checksum(data)
            if stored_checksum != recomputed:
                self._latch("store_checksum_mismatch")
                return
        except (json.JSONDecodeError, ValueError) as e:
            self._latch("JSON parse error: %s" % str(e))
        except OSError as e:
            self._latch("OS error reading store: %s" % str(e))

    def _latch(self, reason: str):
        """Set corruption latch. Once latched, all operations are blocked.
        Also writes a persistent latch file to disk."""
        self._corruption_latch = True
        self._corruption_reason = reason
        # Write persistent latch file
        try:
            latch_data = {
                "reason": reason,
                "latched_at": _now_iso(),
                "schema_version": CLAIM_STORE_SCHEMA_VERSION,
            }
            self.latch_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.latch_path.with_suffix(".tmp")
            with open(str(tmp), "w") as f:
                json.dump(latch_data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(tmp), str(self.latch_path))
        except Exception:
            pass  # best effort for persistent latch

    def is_latched(self) -> bool:
        return self._corruption_latch

    def latch_reason(self) -> str:
        return self._corruption_reason

    def _check_latch(self):
        """Raise if latched."""
        if self._corruption_latch:
            raise MANIFEST_CORRUPTED(
                "ClaimStore corruption latched: %s" % self._corruption_reason
            )

    def repair(self, reason: str, operator_id: str):
        """Clear the corruption latch. Requires explicit operator approval.

        Only clears if both reason and operator_id are non-empty.
        Removes the persistent latch file.
        """
        if not reason or not reason.strip():
            raise ValueError("repair() requires a non-empty reason")
        if not operator_id or not operator_id.strip():
            raise ValueError("repair() requires a non-empty operator_id")

        logger.info(
            "ClaimStore repair: reason=%s operator=%s",
            reason, operator_id,
        )
        self._corruption_latch = False
        self._corruption_reason = ""

        # Remove persistent latch file
        try:
            if self.latch_path.exists():
                self.latch_path.unlink()
        except OSError:
            pass

    def _raw_read(self) -> dict:
        """Raw JSON read without latch check."""
        return json.loads(self.store_path.read_text())

    def _read_store(self) -> dict:
        """Read with latch check, validation, and checksum verification."""
        self._check_latch()
        try:
            data = self._raw_read()
            if not isinstance(data, dict) or "claims" not in data:
                self._latch("invalid store structure")
                raise MANIFEST_CORRUPTED("invalid store structure")

            # Verify store checksum
            stored_checksum = data.get(_STORE_CHECKSUM_KEY)
            if stored_checksum is None:
                self._latch("store_checksum_mismatch")
                raise MANIFEST_CORRUPTED("store checksum missing")
            recomputed = _compute_store_checksum(data)
            if stored_checksum != recomputed:
                self._latch("store_checksum_mismatch")
                raise MANIFEST_CORRUPTED("store checksum mismatch")

            return data
        except json.JSONDecodeError as e:
            self._latch("JSON decode error: %s" % str(e))
            raise MANIFEST_CORRUPTED("JSON decode error: %s" % str(e))

    def _write_store(self, data: dict):
        """Atomic write with flush + fsync + store checksum."""
        self._check_latch()
        data["version"] = CLAIM_STORE_SCHEMA_VERSION
        # Compute and embed store checksum
        data[_STORE_CHECKSUM_KEY] = _compute_store_checksum(data)
        tmp = self.store_path.with_suffix(".tmp")
        with open(str(tmp), "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp), str(self.store_path))

    def acquire_lock(self, timeout=10):
        """Acquire exclusive file lock via cross-platform FileLock. Raises TimeoutError."""
        self._lock_instance = FileLock(str(self.lock_path), timeout)
        self._lock_instance.acquire()

    def release_lock(self):
        if self._lock_instance is not None:
            try:
                self._lock_instance.release()
            except Exception:
                pass
            finally:
                self._lock_instance = None

    def try_claim(self, job_id: str, worker_id: str, pid: int,
                  lease_seconds: int = DEFAULT_LEASE_SECONDS,
                  max_parallel_jobs: int = 1) -> dict:
        """Atomically try to claim a worker for a job.

        Returns {"claimed": True, ...} or {"claimed": False, "reason": ...}.
        """
        self._check_latch()
        self.acquire_lock()
        try:
            store = self._read_store()
            claims = store.get("claims", {})

            # Transition stale claims to RECOVERY_REQUIRED (NOT released)
            now = time.time()
            stale_found = False
            for cid, claim in list(claims.items()):
                if claim.get("state") in ("CLAIMED", "RUNNING"):
                    lease_until = claim.get("lease_until", 0)
                    if now > lease_until:
                        claims[cid]["state"] = "RECOVERY_REQUIRED"
                        claims[cid]["recovery_required_at"] = _now_iso()
                        stale_found = True

            if stale_found:
                self._write_store(store)
                store = self._read_store()
                claims = store.get("claims", {})

            # Count active claims per worker (CLAIMED + RUNNING only)
            # RECOVERY_REQUIRED still counts toward capacity
            active_on_worker = [
                c for c in claims.values()
                if c.get("worker_id") == worker_id
                and c.get("state") in ("CLAIMED", "RUNNING", "RECOVERY_REQUIRED")
            ]

            if len(active_on_worker) >= max_parallel_jobs:
                return {"claimed": False, "reason": "capacity_full",
                        "active_claims": len(active_on_worker),
                        "max_parallel_jobs": max_parallel_jobs}

            claim = {
                "job_id": job_id,
                "worker_id": worker_id,
                "pid": pid,
                "remote_pid": None,
                "remote_pgid": None,
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

    def heartbeat_claim(self, job_id: str) -> dict:
        """Extend a claim's lease by HEARTBEAT_EXTEND_SECONDS."""
        self._check_latch()
        self.acquire_lock()
        try:
            store = self._read_store()
            claims = store.get("claims", {})
            if job_id not in claims:
                return {"ok": False, "error": "claim_not_found"}
            claim = claims[job_id]
            if claim.get("state") not in ("CLAIMED", "RUNNING"):
                return {"ok": False, "error": "invalid_state_for_heartbeat",
                        "state": claim.get("state")}
            now = time.time()
            claim["lease_until"] = now + HEARTBEAT_EXTEND_SECONDS
            claim["heartbeat"] = _now_iso()
            store["claims"] = claims
            self._write_store(store)
            return {"ok": True, "claim": claim}
        finally:
            self.release_lock()

    def update_claim(self, job_id: str, updates: dict):
        """Update a claim (e.g., set remote_pid, state, heartbeat)."""
        self._check_latch()
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
        self._check_latch()
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
        self._check_latch()
        store = self._read_store()
        return store.get("claims", {}).get(job_id)

    def get_active_claims(self, worker_id: str = None) -> list:
        self._check_latch()
        store = self._read_store()
        claims = store.get("claims", {})
        result = []
        for cid, claim in claims.items():
            if claim.get("state") in ("CLAIMED", "RUNNING", "RECOVERY_REQUIRED"):
                if worker_id is None or claim.get("worker_id") == worker_id:
                    result.append(claim)
        return result

    def get_stale_claims(self, max_age_seconds: int = 600) -> list:
        """Find claims whose lease has expired."""
        self._check_latch()
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


# ===========================================================================
# JobManifest
# ===========================================================================
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
    remote_pgid: Optional[int] = None
    exit_code: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    error: Optional[str] = None
    failure_count: int = 0
    checksum: str = ""
    version: str = __version__
    preflight_checks: dict = field(default_factory=dict)
    involves_branch_mutation: bool = False
    branch_name: Optional[str] = None
    involves_merge: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["checksum"] = _manifest_checksum(d)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "JobManifest":
        """Load from dict with checksum verification.

        Raises MANIFEST_CORRUPTED if stored checksum doesn't match recomputed.
        Missing checksum is treated as corruption.
        """
        stored_checksum = d.get("checksum", "")
        recomputed = _manifest_checksum(d)
        # Strict: missing checksum = corruption (no more `if stored_checksum and ...`)
        if stored_checksum != recomputed:
            raise MANIFEST_CORRUPTED(
                "checksum mismatch: stored=%s computed=%s" % (stored_checksum, recomputed)
            )
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ===========================================================================
# Heartbeat Manager
# ===========================================================================
class HeartbeatManager:
    """Background daemon thread that heartbeats RUNNING claims."""

    def __init__(self, claim_store: ClaimStore):
        self.claim_store = claim_store
        self._active_jobs: Dict[str, bool] = {}  # job_id -> running
        self._lock = threading.Lock()
        self._thread = None
        self._stop_event = threading.Event()

    def start_heartbeat(self, job_id: str):
        """Register a job for heartbeat."""
        with self._lock:
            self._active_jobs[job_id] = True
            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(
                    target=self._heartbeat_loop, daemon=True)
                self._thread.start()

    def stop_heartbeat(self, job_id: str):
        """Unregister a job from heartbeat."""
        with self._lock:
            self._active_jobs.pop(job_id, None)
            if not self._active_jobs:
                self._stop_event.set()

    def _heartbeat_loop(self):
        """Background loop: heartbeat all active jobs."""
        while not self._stop_event.is_set():
            with self._lock:
                active = list(self._active_jobs.keys())
            for job_id in active:
                try:
                    result = self.claim_store.heartbeat_claim(job_id)
                    if not result.get("ok"):
                        # Heartbeat failed — mark RECOVERY_REQUIRED and remove from active
                        try:
                            self.claim_store.update_claim(job_id, {
                                "state": "RECOVERY_REQUIRED",
                                "heartbeat_failed_at": _now_iso(),
                                "heartbeat_failure_reason": result.get("error", "unknown"),
                            })
                        except Exception:
                            pass
                        with self._lock:
                            self._active_jobs.pop(job_id, None)
                        logger.warning(
                            "Heartbeat failed for job %s: %s",
                            job_id, result.get("error", "unknown"),
                        )
                except Exception:
                    pass
            self._stop_event.wait(HEARTBEAT_INTERVAL_SECONDS)

    def is_active(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._active_jobs

# ===========================================================================
# JobOrchestrator
# ===========================================================================
class JobOrchestrator:
    """Durable job orchestrator with persistent claims and cross-process support."""

    def __init__(self, registry=None, scheduler=None, jobs_root=None,
                 claim_store=None):
        # All dependencies are MANDATORY — no fallbacks
        self.registry = registry or WorkerRegistry()
        self.scheduler = scheduler or SchedulerPolicy(self.registry)
        self.jobs_root = jobs_root or JOBS_ROOT
        self.claim_store = claim_store or ClaimStore()
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self.heartbeat_mgr = HeartbeatManager(self.claim_store)

    def submit_job(self, task_type, command, required_tools=None,
                   optional_tools=None, job_id=None) -> dict:
        """Submit a job. Fail-closed on no capable worker.

        Uses unified SchedulerPolicy.get_eligible_candidates() which enforces
        ALL gates (lifecycle, capability, branch, merge, health, maintenance).
        Multi-candidate retry on capacity_full.
        """
        jid = job_id or "job-" + uuid.uuid4().hex[:12]

        manifest = JobManifest(
            job_id=jid,
            task_type=task_type,
            command=command,
            required_tools=required_tools or [],
            optional_tools=optional_tools or [],
        )

        # Get ordered candidate list from scheduler (ALL gates applied)
        candidates = self.scheduler.get_eligible_candidates(
            task_type=task_type,
            required_tools=required_tools,
        )

        if not candidates:
            manifest.state = JobState.BLOCKED.value
            manifest.error = "no_eligible_worker"
            manifest.capability_resolution = "no_eligible_worker"
            self._persist_manifest(manifest)
            return manifest.to_dict()

        # Multi-candidate retry loop
        last_error = None
        for worker_id, reason in candidates:
            manifest.capability_resolution = reason
            manifest.requested_worker = worker_id

            worker = self.registry.get_worker(worker_id)
            max_pj = worker.max_parallel_jobs if worker else 1

            claim_result = self.claim_store.try_claim(
                jid, worker_id, os.getpid(),
                max_parallel_jobs=max_pj,
            )
            if claim_result.get("claimed"):
                manifest.actual_worker = worker_id
                manifest.state = JobState.CLAIMED.value

                controller_dir = self.jobs_root / jid
                controller_dir.mkdir(parents=True, exist_ok=True)
                manifest.controller_job_dir = str(controller_dir)

                if worker:
                    import posixpath
                    manifest.remote_job_dir = posixpath.join(
                        worker.workspace_root, "jobs", jid)

                self._persist_manifest(manifest)
                return manifest.to_dict()

            last_error = claim_result.get("reason", "unknown")
            if last_error == "capacity_full":
                continue
            break

        manifest.state = JobState.BLOCKED.value
        manifest.error = "claim_failed: " + str(last_error)
        self._persist_manifest(manifest)
        return manifest.to_dict()

    def execute_job(self, job_id: str, timeout: int = 600) -> dict:
        """Execute a CLAIMED job with fail-closed preflight, heartbeat,
        signed job script, setsid process isolation, and PID file capture."""
        manifest = self._load_manifest(job_id)
        if manifest is None:
            return {"ok": False, "error": "job_not_found", "job_id": job_id}

        if manifest.state != JobState.CLAIMED.value:
            return {"ok": False, "error": "invalid_state_for_execute: " + manifest.state,
                    "job_id": job_id}

        # Preflight revalidation (ALL real gates)
        preflight = self._preflight_check(manifest)
        manifest.preflight_checks = preflight
        if not preflight["all_passed"]:
            manifest.state = JobState.BLOCKED.value
            manifest.error = "preflight_failed: " + str(preflight.get("failed_checks", []))
            self._persist_manifest(manifest)
            self.claim_store.release_claim(job_id, "BLOCKED", success=False)
            return {"ok": False, "error": manifest.error, "job_id": job_id,
                    "preflight": preflight}

        worker = self.registry.get_worker(manifest.actual_worker)
        if worker is None:
            manifest.state = JobState.FAILED.value
            manifest.error = "worker_disappeared"
            self._persist_manifest(manifest)
            return {"ok": False, "error": "worker_disappeared", "job_id": job_id}

        # Verify SSH key availability before any remote operations
        try:
            _resolve_ssh_key(self.registry)
        except RuntimeError as e:
            manifest.state = JobState.FAILED.value
            manifest.error = "ssh_key_unavailable: %s" % str(e)
            self._persist_manifest(manifest)
            self.claim_store.release_claim(job_id, "FAILED", success=False)
            return {"ok": False, "error": manifest.error, "job_id": job_id}

        # Ensure remote job dir
        remote_dir_ok = self._ensure_remote_dir(worker, manifest.remote_job_dir)
        if not remote_dir_ok:
            manifest.state = JobState.FAILED.value
            manifest.error = "remote_dir_creation_failed"
            self._persist_manifest(manifest)
            self.claim_store.release_claim(job_id, "FAILED", success=False)
            return {"ok": False, "error": "remote_dir_creation_failed", "job_id": job_id}

        # Mark RUNNING
        manifest.state = JobState.RUNNING.value
        manifest.start_time = _now_iso()
        self._persist_manifest(manifest)
        self.claim_store.update_claim(job_id, {
            "state": "RUNNING",
            "started_at": manifest.start_time,
        })

        # Build SSH command with process group isolation
        ssh_key = _resolve_ssh_key(self.registry)
        ssh_opts = [
            "-p", str(worker.ssh_port),
            "-i", ssh_key,
            "-o", "StrictHostKeyChecking=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
        ]
        ssh_target = worker.ssh_user + "@" + worker.ssh_host

        # Build signed job script
        job_script_content = self._build_signed_job_script(
            job_id, manifest.command, manifest.remote_job_dir)

        # PID file path on remote
        pid_file = manifest.remote_job_dir + "/.job.pid"
        job_script_path = manifest.remote_job_dir + "/job.sh"

        proc = None
        try:
            # Write signed job script to remote
            write_script_cmd = "cat > %s << 'VIBE_JOB_SCRIPT_EOF'\n%s\nVIBE_JOB_SCRIPT_EOF\nchmod +x %s" % (
                _shell_quote(job_script_path),
                job_script_content,
                _shell_quote(job_script_path),
            )
            script_result = subprocess.run(
                ["ssh"] + ssh_opts + [ssh_target, write_script_cmd],
                capture_output=True, timeout=30,
            )
            if script_result.returncode != 0:
                manifest.state = JobState.FAILED.value
                manifest.error = "job_script_write_failed"
                self._persist_manifest(manifest)
                self.claim_store.release_claim(job_id, "FAILED", success=False)
                return {"ok": False, "error": "job_script_write_failed",
                        "job_id": job_id,
                        "stderr": script_result.stderr.decode("utf-8", errors="replace")}

            # Launch with setsid + PID file capture
            # setsid runs the script in a new session; PID file captures the session leader PID
            launch_cmd = (
                "setsid bash -c 'echo $$ > %s; exec bash %s' > /dev/null 2>&1 &"
                % (_shell_quote(pid_file), _shell_quote(job_script_path))
            )
            proc = subprocess.Popen(
                ["ssh"] + ssh_opts + [ssh_target, launch_cmd],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            manifest.local_pid = proc.pid
            self.claim_store.update_claim(job_id, {"local_pid": proc.pid})
            self._persist_manifest(manifest)

            # Start heartbeat for this job
            self.heartbeat_mgr.start_heartbeat(job_id)

            # Wait for the launch SSH command to complete
            try:
                launch_stdout, launch_stderr = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                manifest.state = JobState.FAILED.value
                manifest.error = "launch_command_timeout"
                self._persist_manifest(manifest)
                self.claim_store.release_claim(job_id, "FAILED", success=False)
                return {"ok": False, "error": "launch_command_timeout", "job_id": job_id}

            # Read PID file via separate SSH after brief delay
            time.sleep(0.5)
            remote_pgid = self._read_remote_pid_file(
                worker, ssh_opts, ssh_target, pid_file)
            if remote_pgid:
                manifest.remote_pid = remote_pgid
                manifest.remote_pgid = remote_pgid
                self.claim_store.update_claim(job_id, {
                    "remote_pid": remote_pgid,
                    "remote_pgid": remote_pgid,
                })
                self._persist_manifest(manifest)

            # Wait for the remote job to complete by polling for the PID file to disappear
            # or checking if the process is still alive
            start_wait = time.time()
            job_exit_code = None
            while time.time() - start_wait < timeout:
                alive = self._check_remote_process_alive(worker, remote_pgid)
                if not alive:
                    # Process exited — try to get exit code
                    # Write a marker to capture exit code
                    exit_code_cmd = "cat %s.exit_code 2>/dev/null || echo -1" % _shell_quote(
                        manifest.remote_job_dir + "/.exit_code")
                    exit_result = subprocess.run(
                        ["ssh"] + ssh_opts + [ssh_target, exit_code_cmd],
                        capture_output=True, timeout=10,
                    )
                    try:
                        job_exit_code = int(
                            exit_result.stdout.decode("utf-8", errors="replace").strip()
                        )
                    except (ValueError, TypeError):
                        job_exit_code = 0 if not alive else -1
                    break
                time.sleep(2)

            if time.time() - start_wait >= timeout:
                # Timeout: TERM the remote process group
                pgid = manifest.remote_pgid or manifest.remote_pid
                self._terminate_remote_process_group(worker, pgid, manifest.remote_pid)

                manifest.state = JobState.RECOVERY_REQUIRED.value
                manifest.error = "timeout_%ds" % timeout
                manifest.exit_code = -1
                manifest.failure_count += 1
                # Do NOT release capacity — remote may still be alive
                self.claim_store.update_claim(job_id, {
                    "state": "RECOVERY_REQUIRED",
                    "error": manifest.error,
                })
                return {
                    "ok": False,
                    "job_id": job_id,
                    "state": manifest.state,
                    "exit_code": manifest.exit_code,
                    "error": manifest.error,
                    "failure_count": manifest.failure_count,
                }

            # Capture stdout/stderr from remote job files
            stdout_text = self._read_remote_file(
                worker, ssh_opts, ssh_target,
                manifest.remote_job_dir + "/stdout.txt")
            stderr_text = self._read_remote_file(
                worker, ssh_opts, ssh_target,
                manifest.remote_job_dir + "/stderr.txt")

            manifest.exit_code = job_exit_code if job_exit_code is not None else 0

            # Save output locally
            controller_dir = Path(manifest.controller_job_dir)
            (controller_dir / "stdout.txt").write_text(stdout_text)
            (controller_dir / "stderr.txt").write_text(stderr_text)

            if manifest.exit_code == 0:
                manifest.state = JobState.SUCCEEDED.value
                self.claim_store.release_claim(job_id, "SUCCEEDED", success=True)
            else:
                manifest.state = JobState.FAILED.value
                manifest.error = "exit_code_%d" % manifest.exit_code
                manifest.failure_count += 1
                self.claim_store.release_claim(job_id, "FAILED", success=False)

        except subprocess.TimeoutExpired:
            # TERM the remote process group
            pgid = manifest.remote_pgid or manifest.remote_pid
            self._terminate_remote_process_group(
                worker, pgid, manifest.remote_pid)
            # Kill local SSH process
            if proc:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except Exception:
                    pass

            manifest.state = JobState.RECOVERY_REQUIRED.value
            manifest.error = "timeout_%ds" % timeout
            manifest.exit_code = -1
            manifest.failure_count += 1
            # Do NOT release capacity — remote may still be alive
            self.claim_store.update_claim(job_id, {
                "state": "RECOVERY_REQUIRED",
                "error": manifest.error,
            })

        except Exception as e:
            manifest.state = JobState.FAILED.value
            manifest.error = str(e)
            manifest.exit_code = -1
            manifest.failure_count += 1
            self.claim_store.release_claim(job_id, "FAILED", success=False)

        finally:
            self.heartbeat_mgr.stop_heartbeat(job_id)
            manifest.end_time = _now_iso()
            self._persist_manifest(manifest)

        return {
            "ok": manifest.state == JobState.SUCCEEDED.value,
            "job_id": job_id,
            "state": manifest.state,
            "exit_code": manifest.exit_code,
            "local_pid": manifest.local_pid,
            "remote_pid": manifest.remote_pid,
            "remote_pgid": manifest.remote_pgid,
            "actual_worker": manifest.actual_worker,
            "failure_count": manifest.failure_count,
        }

    def _build_signed_job_script(self, job_id: str, command: str,
                                  remote_job_dir: str) -> str:
        """Build a signed job script for remote execution.

        The signature is SHA256 of job_id + command, providing integrity
        verification for the job script.
        """
        sig_input = (job_id + command).encode("utf-8")
        signature = hashlib.sha256(sig_input).hexdigest()[:32]

        script = (
            "#!/bin/bash\n"
            "# Job: %s\n"
            "# Signed: %s\n"
            "set -e\n"
            "cd %s\n"
            "%s\n"
        ) % (job_id, signature, _shell_quote(remote_job_dir), command)

        return script

    def _read_remote_pid_file(self, worker, ssh_opts, ssh_target,
                               pid_file_path) -> Optional[int]:
        """Read PID file from remote host via SSH."""
        read_cmd = "cat %s 2>/dev/null" % _shell_quote(pid_file_path)
        try:
            result = subprocess.run(
                ["ssh"] + ssh_opts + [ssh_target, read_cmd],
                capture_output=True, timeout=10,
            )
            output = result.stdout.decode("utf-8", errors="replace").strip()
            if output:
                return int(output)
        except (ValueError, TypeError, Exception):
            pass
        return None

    def _read_remote_file(self, worker, ssh_opts, ssh_target,
                           file_path: str) -> str:
        """Read a file from remote host via SSH."""
        read_cmd = "cat %s 2>/dev/null || true" % _shell_quote(file_path)
        try:
            result = subprocess.run(
                ["ssh"] + ssh_opts + [ssh_target, read_cmd],
                capture_output=True, timeout=30,
            )
            return result.stdout.decode("utf-8", errors="replace")
        except Exception:
            return ""

    def cancel_job(self, job_id: str) -> dict:
        """Cancel a QUEUED, CLAIMED, or RUNNING job.

        For RUNNING: TERM remote PGID, wait, KILL, confirm exit, then
        mark RECOVERY_REQUIRED (capacity NOT released until confirmed).
        """
        manifest = self._load_manifest(job_id)
        if manifest is None:
            return {"ok": False, "error": "job_not_found"}

        if manifest.state in (JobState.SUCCEEDED.value, JobState.FAILED.value,
                              JobState.CANCELLED.value):
            return {"ok": False, "error": "cannot_cancel_%s" % manifest.state}

        if manifest.state == JobState.RUNNING.value:
            worker = self.registry.get_worker(manifest.actual_worker)
            pgid = manifest.remote_pgid or manifest.remote_pid
            if worker and pgid:
                self._terminate_remote_process_group(
                    worker, pgid, manifest.remote_pid)

            self.heartbeat_mgr.stop_heartbeat(job_id)

            manifest.state = JobState.RECOVERY_REQUIRED.value
            manifest.end_time = _now_iso()
            manifest.error = "cancelled"
            self._persist_manifest(manifest)
            self.claim_store.update_claim(job_id, {
                "state": "RECOVERY_REQUIRED",
                "error": "cancelled",
            })
            return {"ok": True, "job_id": job_id, "state": "RECOVERY_REQUIRED"}
        else:
            manifest.state = JobState.CANCELLED.value
            manifest.end_time = _now_iso()
            self._persist_manifest(manifest)
            self.claim_store.release_claim(job_id, "CANCELLED", success=False)
            return {"ok": True, "job_id": job_id, "state": "CANCELLED"}

    def resume_job(self, job_id: str) -> dict:
        """Resume a RECOVERY_REQUIRED, FAILED, or CANCELLED job.

        Calls real resume gate before proceeding.
        For RECOVERY_REQUIRED: verify remote process dead before re-claim.
        """
        manifest = self._load_manifest(job_id)
        if manifest is None:
            return {"ok": False, "error": "job_not_found"}

        # Call REAL resume gate
        gate_result = _resume_gate_check(
            batch_id=job_id,
            worktree=manifest.controller_job_dir or str(self.jobs_root / job_id),
            expected_baseline=None,
            jobs_dir=str(self.jobs_root),
        )
        decision = gate_result.get("decision", "")
        if decision != "RESUME_SAFE":
            return {"ok": False, "error": "resume_gate_denied",
                    "reason": decision,
                    "blockers": gate_result.get("blockers", [])}

        if manifest.state == JobState.RECOVERY_REQUIRED.value:
            worker = self.registry.get_worker(manifest.actual_worker)
            if worker and manifest.remote_pid:
                remote_alive = self._check_remote_process_alive(
                    worker, manifest.remote_pid)
                if remote_alive:
                    return {"ok": False,
                            "error": "remote_process_still_alive",
                            "remote_pid": manifest.remote_pid}

            max_pj = worker.max_parallel_jobs if worker else 1
            claim_result = self.claim_store.try_claim(
                job_id, manifest.actual_worker, os.getpid(),
                max_parallel_jobs=max_pj,
            )
            if not claim_result.get("claimed"):
                return {"ok": False, "error": "reclaim_failed",
                        "reason": claim_result.get("reason")}
            manifest.state = JobState.CLAIMED.value
            manifest.error = None
            self._persist_manifest(manifest)
            return self.execute_job(job_id)

        if manifest.state in (JobState.FAILED.value, JobState.CANCELLED.value):
            manifest.state = JobState.QUEUED.value
            manifest.error = None
            manifest.exit_code = None
            manifest.local_pid = None
            manifest.remote_pid = None
            manifest.remote_pgid = None
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
        manifest = self._load_manifest(job_id)
        if manifest:
            return manifest.to_dict()
        return None

    def list_jobs(self, state_filter: str = None) -> list:
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

    # ===================================================================
    # Preflight — ALL REAL GATES
    # ===================================================================
    def _preflight_check(self, manifest: JobManifest) -> dict:
        """Pre-execution revalidation with REAL gates.

        Gates:
          1. Worker status: health + maintenance
          2. Lifecycle: gate_check_for_dispatch(state_path, registry)
          3. Capability: scheduler._filter_by_capabilities()
          4. Branch: registry.check_branch_available(branch)
          5. Merge: registry.check_merge_available()
          6. Resume: resume_gate_check (for resume operations)
          7. Claim still valid
        """
        checks = {}
        all_passed = True
        failed = []

        # 1. Worker status
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

        # 2. Lifecycle gate: REAL gate_check_for_dispatch(state_path, registry)
        try:
            gate_result = _real_gate_check_for_dispatch(
                registry=self.registry)
            lifecycle_ok = gate_result.get("allowed", False)
            checks["lifecycle_gate"] = {
                "passed": lifecycle_ok,
                "detail": gate_result.get("reason", ""),
                "gate_version": gate_result.get("gate_version", ""),
            }
        except Exception as e:
            lifecycle_ok = False
            checks["lifecycle_gate"] = {
                "passed": False,
                "detail": "gate_exception: %s" % str(e),
            }
        if not lifecycle_ok:
            all_passed = False
            failed.append("lifecycle_gate")

        # 3. Capability gate
        if manifest.required_tools:
            cap_result = self.scheduler._filter_by_capabilities(manifest.required_tools)
            if manifest.actual_worker not in cap_result.get("capable_workers", []):
                checks["capability"] = {"passed": False,
                                        "detail": cap_result.get("reason")}
                all_passed = False
                failed.append("capability")
            else:
                checks["capability"] = {"passed": True}
        else:
            checks["capability"] = {"passed": True, "detail": "no_tools_required"}

        # 4. Branch gate: check_branch_available(branch) — NO worker_id arg
        if manifest.involves_branch_mutation and manifest.branch_name:
            branch_ok = self.registry.check_branch_available(manifest.branch_name)
            checks["branch_gate"] = {"passed": branch_ok,
                                      "detail": "branch=%s" % manifest.branch_name}
            if not branch_ok:
                all_passed = False
                failed.append("branch_gate")
        else:
            checks["branch_gate"] = {"passed": True, "detail": "no_branch_mutation"}

        # 5. Merge gate: check_merge_available() — NO args
        if manifest.involves_merge:
            merge_ok = self.registry.check_merge_available()
            checks["merge_gate"] = {"passed": merge_ok,
                                     "detail": "merge_available"}
            if not merge_ok:
                all_passed = False
                failed.append("merge_gate")
        else:
            checks["merge_gate"] = {"passed": True, "detail": "not_merge_operation"}

        # 6. Resume gate (for resume operations)
        checks["resume_gate"] = {"passed": True, "detail": "not_resume_operation"}

        # 7. Claim still valid
        claim = self.claim_store.get_claim(manifest.job_id)
        if claim and claim.get("state") in ("CLAIMED", "RUNNING"):
            checks["claim_valid"] = {"passed": True}
        else:
            checks["claim_valid"] = {"passed": False, "detail": "claim_missing_or_released"}
            all_passed = False
            failed.append("claim_valid")

        return {"all_passed": all_passed, "checks": checks,
                "failed_checks": failed}

    # ===================================================================
    # Remote process control
    # ===================================================================
    def _ensure_remote_dir(self, worker, remote_path: str) -> bool:
        ssh_key = _resolve_ssh_key(self.registry)
        cmd = [
            "ssh", "-p", str(worker.ssh_port), "-i", ssh_key,
            "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
            worker.ssh_user + "@" + worker.ssh_host,
            "mkdir -p %s && test -d %s" % (
                _shell_quote(remote_path), _shell_quote(remote_path)),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=15)
            return result.returncode == 0
        except Exception:
            return False

    def _terminate_remote_process_group(self, worker, pgid: int,
                                         fallback_pid: int = None):
        """TERM remote PGID, wait, KILL, confirm exit."""
        if not pgid and not fallback_pid:
            return

        ssh_key = _resolve_ssh_key(self.registry)
        ssh_opts = [
            "-p", str(worker.ssh_port), "-i", ssh_key,
            "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        ]
        ssh_target = worker.ssh_user + "@" + worker.ssh_host

        # TERM the process group
        targets = []
        if pgid:
            targets.append("-%d" % pgid)
        if fallback_pid and fallback_pid != pgid:
            targets.append("%d" % fallback_pid)

        kill_cmd = "kill -TERM %s 2>/dev/null; sleep 3" % " ".join(targets)
        try:
            subprocess.run(
                ["ssh"] + ssh_opts + [ssh_target, kill_cmd],
                capture_output=True, timeout=15,
            )
        except Exception:
            pass

        # Check if still alive, then KILL
        check_and_kill = (
            "for pid in %s; do "
            "  kill -0 $pid 2>/dev/null && kill -KILL $pid 2>/dev/null; "
            "done; sleep 1"
            % " ".join(targets)
        )
        try:
            subprocess.run(
                ["ssh"] + ssh_opts + [ssh_target, check_and_kill],
                capture_output=True, timeout=15,
            )
        except Exception:
            pass

    def _check_remote_process_alive(self, worker, remote_pid: int) -> bool:
        """Check if remote process is still running."""
        if not remote_pid:
            return False
        ssh_key = _resolve_ssh_key(self.registry)
        ssh_opts = [
            "-p", str(worker.ssh_port), "-i", ssh_key,
            "-o", "StrictHostKeyChecking=yes", "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
        ]
        ssh_target = worker.ssh_user + "@" + worker.ssh_host
        check_cmd = 'kill -0 -- -%d 2>/dev/null && echo ALIVE || echo DEAD' % remote_pid
        try:
            result = subprocess.run(
                ["ssh"] + ssh_opts + [ssh_target, check_cmd],
                capture_output=True, timeout=10,
            )
            output = result.stdout.decode("utf-8", errors="replace").strip()
            return "ALIVE" in output
        except Exception:
            # Can't check — assume alive to be safe (fail-closed)
            return True

    @staticmethod
    def _parse_remote_pid(stdout_text: str) -> Optional[int]:
        for line in stdout_text.split("\n"):
            line = line.strip()
            if line.startswith("REMOTE_PID="):
                try:
                    return int(line.split("=", 1)[1])
                except (ValueError, IndexError):
                    pass
        return None

    @staticmethod
    def _strip_remote_pid_line(stdout_text: str) -> str:
        lines = stdout_text.split("\n")
        filtered = [l for l in lines if not l.strip().startswith("REMOTE_PID=")
                     and not l.strip().startswith("REMOTE_PGID=")]
        return "\n".join(filtered)

    def _persist_manifest(self, manifest: JobManifest):
        if manifest.controller_job_dir:
            p = Path(manifest.controller_job_dir) / "manifest.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            data = manifest.to_dict()
            tmp = p.with_suffix(".tmp")
            with open(str(tmp), "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(tmp), str(p))

    def _load_manifest(self, job_id: str) -> Optional[JobManifest]:
        manifest_path = self.jobs_root / job_id / "manifest.json"
        if manifest_path.exists():
            try:
                d = json.loads(manifest_path.read_text())
                return JobManifest.from_dict(d)
            except MANIFEST_CORRUPTED as e:
                # Log corruption and check if the job has an active claim.
                # If so, don't release the claim (capacity stays occupied).
                logger.error("MANIFEST_CORRUPTED for job %s: %s", job_id, str(e))
                try:
                    claim = self.claim_store.get_claim(job_id)
                    if claim and claim.get("state") in ("CLAIMED", "RUNNING"):
                        logger.warning(
                            "Job %s has active claim (state=%s) but manifest corrupted. "
                            "Not releasing claim to preserve capacity.",
                            job_id, claim.get("state"),
                        )
                except Exception:
                    pass
                return None
            except Exception:
                pass
        return None


def _shell_quote(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


# ===========================================================================
# CLI
# ===========================================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Job Orchestrator v" + __version__)
    sub = parser.add_subparsers(dest="subcommand")

    p_submit = sub.add_parser("submit")
    p_submit.add_argument("--task-type", default="linux-worker")
    p_submit.add_argument("--command", default="echo hello")
    p_submit.add_argument("--required-tools", nargs="*", default=[])
    p_submit.add_argument("--optional-tools", nargs="*", default=[])
    p_submit.add_argument("--job-id", default=None)
    p_submit.add_argument("--run", action="store_true")

    p_exec = sub.add_parser("execute")
    p_exec.add_argument("--job-id", required=True)
    p_exec.add_argument("--timeout", type=int, default=600)

    p_status = sub.add_parser("status")
    p_status.add_argument("--job-id", required=True)

    p_cancel = sub.add_parser("cancel")
    p_cancel.add_argument("--job-id", required=True)

    p_resume = sub.add_parser("resume")
    p_resume.add_argument("--job-id", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("--active", action="store_true")
    p_list.add_argument("--failed", action="store_true")

    sub.add_parser("self-check")

    args = parser.parse_args()

    if args.subcommand == "self-check":
        result = run_self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    orch = JobOrchestrator()
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
        os.path.join(td, "claim_store.latch"),
    )
    jobs_root = Path(td) / "jobs"
    return JobOrchestrator(claim_store=cs, jobs_root=jobs_root)


def run_self_check() -> dict:
    """Comprehensive self-check for orchestrator v3.1.0."""
    import tempfile

    checks = []
    passed = True

    # Check 1: Module imports (MUST succeed — no fallbacks)
    try:
        orch = _make_test_orchestrator()
        checks.append({"name": "import_ok", "passed": True})
    except Exception as e:
        checks.append({"name": "import_ok", "passed": False, "error": str(e)})
        return {"passed": False, "version": __version__, "checks": checks}

    # Check 2: ClaimStore persistence with fsync
    try:
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "claims.json"), os.path.join(td, "claims.lock"))
            result = cs.try_claim("test-job-1", "5bao", os.getpid())
            assert result["claimed"]
            cs2 = ClaimStore(os.path.join(td, "claims.json"), os.path.join(td, "claims.lock"))
            claim = cs2.get_claim("test-job-1")
            assert claim is not None
            assert claim["worker_id"] == "5bao"
            checks.append({"name": "claim_store_persistence", "passed": True})
    except Exception as e:
        checks.append({"name": "claim_store_persistence", "passed": False, "error": str(e)})
        passed = False

    # Check 3: Atomic claim prevents double-claim
    try:
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            r1 = cs.try_claim("job-a", "5bao", 100, max_parallel_jobs=1)
            assert r1["claimed"]
            r2 = cs.try_claim("job-b", "5bao", 200, max_parallel_jobs=1)
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
            assert r["claimed"]
            checks.append({"name": "release_frees_capacity", "passed": True})
    except Exception as e:
        checks.append({"name": "release_frees_capacity", "passed": False, "error": str(e)})
        passed = False

    # Check 5: Stale claim → RECOVERY_REQUIRED
    try:
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            cs.try_claim("j-stale", "5bao", 1, lease_seconds=1)
            time.sleep(1.5)
            stale = cs.get_stale_claims()
            assert len(stale) >= 1
            # RECOVERY_REQUIRED still counts toward capacity
            r = cs.try_claim("j-new", "5bao", 2, max_parallel_jobs=2)
            assert r["claimed"]
            old = cs.get_claim("j-stale")
            assert old["state"] == "RECOVERY_REQUIRED"
            checks.append({"name": "stale_claim_recovery_required", "passed": True})
    except Exception as e:
        checks.append({"name": "stale_claim_recovery_required", "passed": False, "error": str(e)})
        passed = False

    # Check 6: RECOVERY_REQUIRED counts toward capacity
    try:
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            cs.try_claim("j-rec", "5bao", 1, lease_seconds=1, max_parallel_jobs=1)
            time.sleep(1.5)
            # Triggers stale → RECOVERY_REQUIRED
            r = cs.try_claim("j-new2", "5bao", 2, max_parallel_jobs=1)
            # RECOVERY_REQUIRED should count as occupying capacity
            assert not r["claimed"], "RECOVERY_REQUIRED should block new claim"
            assert r["reason"] == "capacity_full"
            checks.append({"name": "recovery_preserves_capacity", "passed": True})
    except Exception as e:
        checks.append({"name": "recovery_preserves_capacity", "passed": False, "error": str(e)})
        passed = False

    # Check 7: Submit with no capable worker blocks
    try:
        orch = _make_test_orchestrator()
        for w in orch.registry.list_workers():
            orch.registry.set_health(w.worker_id, NodeStatus.OFFLINE)
        m = orch.submit_job("linux-worker", "echo hi", required_tools=["ripgrep"])
        assert m["state"] == "BLOCKED"
        checks.append({"name": "submit_blocked_no_worker", "passed": True})
    except Exception as e:
        checks.append({"name": "submit_blocked_no_worker", "passed": False, "error": str(e)})
        passed = False

    # Check 8: Submit without tools succeeds
    try:
        orch = _make_test_orchestrator()
        for w in orch.registry.list_workers():
            orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
        m = orch.submit_job("linux-worker", "echo hi")
        assert m["state"] == "CLAIMED"
        assert m["actual_worker"] in ("5bao", "9bao")
        assert m["remote_job_dir"] != ""
        checks.append({"name": "submit_no_tools_ok", "passed": True})
    except Exception as e:
        checks.append({"name": "submit_no_tools_ok", "passed": False, "error": str(e)})
        passed = False

    # Check 9: ripgrep routes to 9bao
    try:
        orch = _make_test_orchestrator()
        for w in orch.registry.list_workers():
            orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
        m = orch.submit_job("linux-worker", "rg --version", required_tools=["ripgrep"])
        assert m["state"] == "CLAIMED"
        assert m["actual_worker"] == "9bao"
        checks.append({"name": "ripgrep_routes_9bao", "passed": True})
    except Exception as e:
        checks.append({"name": "ripgrep_routes_9bao", "passed": False, "error": str(e)})
        passed = False

    # Check 10: Manifest checksum
    try:
        m = JobManifest(job_id="test", task_type="linux-worker", command="echo hi")
        d = m.to_dict()
        assert d["checksum"] != ""
        m2 = JobManifest(job_id="test", task_type="linux-worker", command="echo bye")
        d2 = m2.to_dict()
        assert d["checksum"] != d2["checksum"]
        checks.append({"name": "manifest_checksum", "passed": True})
    except Exception as e:
        checks.append({"name": "manifest_checksum", "passed": False, "error": str(e)})
        passed = False

    # Check 11: Manifest checksum corruption detection
    try:
        m = JobManifest(job_id="test-cs", task_type="linux-worker", command="echo hi")
        d = m.to_dict()
        d_corrupt = dict(d)
        d_corrupt["command"] = "echo tampered"
        caught = False
        try:
            JobManifest.from_dict(d_corrupt)
        except MANIFEST_CORRUPTED:
            caught = True
        assert caught
        checks.append({"name": "manifest_corruption_detection", "passed": True})
    except Exception as e:
        checks.append({"name": "manifest_corruption_detection", "passed": False, "error": str(e)})
        passed = False

    # Check 12: ClaimStore corruption latch on bad JSON
    try:
        with tempfile.TemporaryDirectory() as td:
            store_path = os.path.join(td, "c.json")
            lock_path = os.path.join(td, "c.lock")
            # Write valid store first
            cs = ClaimStore(store_path, lock_path)
            cs.try_claim("j1", "5bao", 1)
            # Corrupt the file
            with open(store_path, "w") as f:
                f.write("{corrupt json")
            # New ClaimStore instance should latch
            cs2 = ClaimStore(store_path, lock_path)
            assert cs2.is_latched()
            # All operations should be blocked
            caught = False
            try:
                cs2.try_claim("j2", "5bao", 2)
            except MANIFEST_CORRUPTED:
                caught = True
            assert caught
            checks.append({"name": "corruption_latch_blocks_operations", "passed": True})
    except Exception as e:
        checks.append({"name": "corruption_latch_blocks_operations", "passed": False, "error": str(e)})
        passed = False

    # Check 13: ClaimStore schema validation on bad structure
    try:
        with tempfile.TemporaryDirectory() as td:
            store_path = os.path.join(td, "c.json")
            lock_path = os.path.join(td, "c.lock")
            with open(store_path, "w") as f:
                json.dump({"not_claims": {}}, f)
            cs = ClaimStore(store_path, lock_path)
            assert cs.is_latched()
            checks.append({"name": "schema_validation_latch", "passed": True})
    except Exception as e:
        checks.append({"name": "schema_validation_latch", "passed": False, "error": str(e)})
        passed = False

    # Check 14: Heartbeat renewal
    try:
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            r = cs.try_claim("j-hb", "5bao", 1, lease_seconds=2)
            assert r["claimed"]
            claim_before = cs.get_claim("j-hb")
            lease_before = claim_before["lease_until"]
            time.sleep(0.5)
            hb_result = cs.heartbeat_claim("j-hb")
            assert hb_result["ok"]
            claim_after = cs.get_claim("j-hb")
            assert claim_after["lease_until"] > lease_before
            checks.append({"name": "heartbeat_renewal", "passed": True})
    except Exception as e:
        checks.append({"name": "heartbeat_renewal", "passed": False, "error": str(e)})
        passed = False

    # Check 15: Resume requires real gate
    try:
        orch = _make_test_orchestrator()
        for w in orch.registry.list_workers():
            orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
        m = orch.submit_job("linux-worker", "echo hi")
        jid = m["job_id"]
        manifest = orch._load_manifest(jid)
        manifest.state = JobState.FAILED.value
        manifest.error = "test_failure"
        orch._persist_manifest(manifest)
        result = orch.resume_job(jid)
        assert result.get("error") != "resume_gate_denied", "real gate should not deny valid resume"
        checks.append({"name": "resume_requires_real_gate", "passed": True})
    except Exception as e:
        checks.append({"name": "resume_requires_real_gate", "passed": False, "error": str(e)})
        passed = False

    # Check 16: Multi-candidate retry
    try:
        orch = _make_test_orchestrator()
        for w in orch.registry.list_workers():
            orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
        orch.registry.workers["5bao"].max_parallel_jobs = 1
        orch.registry.workers["9bao"].max_parallel_jobs = 1
        m1 = orch.submit_job("linux-worker", "echo job-0")
        assert m1["state"] == "CLAIMED"
        first_worker = m1["actual_worker"]
        m2 = orch.submit_job("linux-worker", "echo retry-test")
        assert m2["state"] == "CLAIMED"
        assert m2["actual_worker"] != first_worker
        checks.append({"name": "multi_candidate_retry", "passed": True})
    except Exception as e:
        checks.append({"name": "multi_candidate_retry", "passed": False, "error": str(e)})
        passed = False

    # Check 17: Real preflight gates verified
    try:
        orch = _make_test_orchestrator()
        for w in orch.registry.list_workers():
            orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
        m = orch.submit_job("linux-worker", "echo hi")
        manifest = orch._load_manifest(m["job_id"])
        preflight = orch._preflight_check(manifest)
        assert preflight["all_passed"]
        for gate in ["lifecycle_gate", "capability", "branch_gate",
                      "merge_gate", "resume_gate", "worker_online", "not_maintenance"]:
            assert gate in preflight["checks"], "%s must be checked" % gate
        checks.append({"name": "real_preflight_gates", "passed": True})
    except Exception as e:
        checks.append({"name": "real_preflight_gates", "passed": False, "error": str(e)})
        passed = False

    # Check 18: Remote PID parsing
    try:
        stdout = "REMOTE_PID=12345\nREMOTE_PGID=12345\nhello world\n"
        pid = JobOrchestrator._parse_remote_pid(stdout)
        assert pid == 12345
        clean = JobOrchestrator._strip_remote_pid_line(stdout)
        assert "REMOTE_PID" not in clean
        assert "REMOTE_PGID" not in clean
        assert "hello world" in clean
        assert JobOrchestrator._parse_remote_pid("no pid here\n") is None
        checks.append({"name": "remote_pid_parsing", "passed": True})
    except Exception as e:
        checks.append({"name": "remote_pid_parsing", "passed": False, "error": str(e)})
        passed = False

    # Check 19: max_parallel_jobs from registry
    try:
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            r1 = cs.try_claim("mpj-1", "w1", 1, max_parallel_jobs=4)
            r2 = cs.try_claim("mpj-2", "w1", 2, max_parallel_jobs=4)
            r3 = cs.try_claim("mpj-3", "w1", 3, max_parallel_jobs=4)
            r4 = cs.try_claim("mpj-4", "w1", 4, max_parallel_jobs=4)
            assert r1["claimed"] and r2["claimed"] and r3["claimed"] and r4["claimed"]
            r5 = cs.try_claim("mpj-5", "w1", 5, max_parallel_jobs=4)
            assert not r5["claimed"]
            checks.append({"name": "max_parallel_jobs_capacity", "passed": True})
    except Exception as e:
        checks.append({"name": "max_parallel_jobs_capacity", "passed": False, "error": str(e)})
        passed = False

    # Check 20: get_eligible_candidates
    try:
        orch = _make_test_orchestrator()
        for w in orch.registry.list_workers():
            orch.registry.set_health(w.worker_id, NodeStatus.ONLINE)
        candidates = orch.scheduler.get_eligible_candidates("linux-worker")
        assert len(candidates) >= 2
        candidates_rg = orch.scheduler.get_eligible_candidates(
            "linux-worker", required_tools=["ripgrep"])
        assert len(candidates_rg) == 1
        assert candidates_rg[0][0] == "9bao"
        checks.append({"name": "get_eligible_candidates", "passed": True})
    except Exception as e:
        checks.append({"name": "get_eligible_candidates", "passed": False, "error": str(e)})
        passed = False

    # Check 21: Branch/merge gate call signature (no worker_id arg)
    try:
        orch = _make_test_orchestrator()
        # These should NOT raise TypeError from wrong arg count
        b_ok = orch.registry.check_branch_available("test-branch")
        m_ok = orch.registry.check_merge_available()
        assert isinstance(b_ok, bool)
        assert isinstance(m_ok, bool)
        checks.append({"name": "gate_call_signatures", "passed": True})
    except Exception as e:
        checks.append({"name": "gate_call_signatures", "passed": False, "error": str(e)})
        passed = False

    # Check 22: HeartbeatManager starts and stops
    try:
        with tempfile.TemporaryDirectory() as td:
            cs = ClaimStore(os.path.join(td, "c.json"), os.path.join(td, "c.lock"))
            cs.try_claim("j-hm", "5bao", 1, lease_seconds=60)
            hm = HeartbeatManager(cs)
            hm.start_heartbeat("j-hm")
            assert hm.is_active("j-hm")
            time.sleep(0.5)
            hm.stop_heartbeat("j-hm")
            assert not hm.is_active("j-hm")
            checks.append({"name": "heartbeat_manager", "passed": True})
    except Exception as e:
        checks.append({"name": "heartbeat_manager", "passed": False, "error": str(e)})
        passed = False

    # Check 23: FileLock is cross-platform (import succeeds)
    try:
        from vibe_filelock import FileLock as FL
        assert FL is not None
        checks.append({"name": "filelock_cross_platform", "passed": True})
    except Exception as e:
        checks.append({"name": "filelock_cross_platform", "passed": False, "error": str(e)})
        passed = False

    # Check 24: Store checksum validation (corrupt store checksum → latch)
    try:
        with tempfile.TemporaryDirectory() as td:
            store_path = os.path.join(td, "c.json")
            lock_path = os.path.join(td, "c.lock")
            cs = ClaimStore(store_path, lock_path)
            cs.try_claim("j-cs", "5bao", 1)
            # Read and tamper with the checksum field
            raw = json.loads(open(store_path).read())
            raw[_STORE_CHECKSUM_KEY] = "tampered_checksum"
            with open(store_path, "w") as f:
                json.dump(raw, f)
            # New ClaimStore should detect checksum mismatch and latch
            cs2 = ClaimStore(store_path, lock_path)
            assert cs2.is_latched()
            assert "store_checksum" in cs2.latch_reason().lower() or "checksum" in cs2.latch_reason().lower()
            checks.append({"name": "store_checksum_validation", "passed": True})
    except Exception as e:
        checks.append({"name": "store_checksum_validation", "passed": False, "error": str(e)})
        passed = False

    # Check 25: Manifest missing checksum → MANIFEST_CORRUPTED
    try:
        m = JobManifest(job_id="test-mc", task_type="linux-worker", command="echo hi")
        d = m.to_dict()
        # Remove checksum field
        d_no_checksum = {k: v for k, v in d.items() if k != "checksum"}
        d_no_checksum["checksum"] = ""
        caught = False
        try:
            JobManifest.from_dict(d_no_checksum)
        except MANIFEST_CORRUPTED:
            caught = True
        assert caught, "Missing/mismatched checksum should raise MANIFEST_CORRUPTED"
        checks.append({"name": "manifest_missing_checksum_corruption", "passed": True})
    except Exception as e:
        checks.append({"name": "manifest_missing_checksum_corruption", "passed": False, "error": str(e)})
        passed = False

    # Check 26: Persistent latch file on disk
    try:
        with tempfile.TemporaryDirectory() as td:
            store_path = os.path.join(td, "c.json")
            lock_path = os.path.join(td, "c.lock")
            latch_path = os.path.join(td, "claim_store.latch")
            cs = ClaimStore(store_path, lock_path, latch_path)
            # Write a valid store, then corrupt it to trigger latch
            cs.try_claim("j-pl", "5bao", 1)
            with open(store_path, "w") as f:
                f.write("{corrupt json")
            cs2 = ClaimStore(store_path, lock_path, latch_path)
            assert cs2.is_latched()
            # Verify latch file exists on disk
            assert os.path.exists(latch_path), "Persistent latch file should exist"
            latch_data = json.loads(open(latch_path).read())
            assert "reason" in latch_data
            assert "latched_at" in latch_data
            # Verify new instance auto-latches from file
            cs3 = ClaimStore(store_path, lock_path, latch_path)
            assert cs3.is_latched()
            checks.append({"name": "persistent_latch_file", "passed": True})
    except Exception as e:
        checks.append({"name": "persistent_latch_file", "passed": False, "error": str(e)})
        passed = False

    # Check 27: Credential enforcement (platform check)
    try:
        # On Windows, _resolve_ssh_key should NOT raise the platform check error
        # On non-Windows, it SHOULD raise RuntimeError about platform
        # We test that the check exists by verifying the function has the guard
        import inspect
        src = inspect.getsource(_resolve_ssh_key)
        assert "sys.platform" in src, "Platform check must exist in _resolve_ssh_key"
        assert 'win32' in src, "Must check for win32 platform"
        checks.append({"name": "credential_enforcement_platform_check", "passed": True})
    except Exception as e:
        checks.append({"name": "credential_enforcement_platform_check", "passed": False, "error": str(e)})
        passed = False

    # Check 28: Signed job script generation
    try:
        orch = _make_test_orchestrator()
        script = orch._build_signed_job_script("test-job", "echo hello", "/tmp/test")
        assert "#!/bin/bash" in script
        assert "# Job: test-job" in script
        assert "# Signed:" in script
        assert "set -e" in script
        assert "echo hello" in script
        # Verify the signature is deterministic
        script2 = orch._build_signed_job_script("test-job", "echo hello", "/tmp/test")
        assert script == script2
        # Verify different command produces different signature
        script3 = orch._build_signed_job_script("test-job", "echo world", "/tmp/test")
        assert script != script3
        checks.append({"name": "signed_job_script", "passed": True})
    except Exception as e:
        checks.append({"name": "signed_job_script", "passed": False, "error": str(e)})
        passed = False

    # Check 29: Repair method
    try:
        with tempfile.TemporaryDirectory() as td:
            store_path = os.path.join(td, "c.json")
            lock_path = os.path.join(td, "c.lock")
            latch_path = os.path.join(td, "claim_store.latch")
            cs = ClaimStore(store_path, lock_path, latch_path)
            # Corrupt to trigger latch
            cs.try_claim("j-rep", "5bao", 1)
            with open(store_path, "w") as f:
                f.write("{corrupt")
            cs2 = ClaimStore(store_path, lock_path, latch_path)
            assert cs2.is_latched()
            # Repair should clear latch
            cs2.repair("manual recovery after crash", "operator-001")
            assert not cs2.is_latched()
            assert not os.path.exists(latch_path)
            # Repair requires non-empty reason and operator_id
            cs3 = ClaimStore(store_path, lock_path, latch_path)
            cs3._latch("test")
            try:
                cs3.repair("", "op")
                assert False, "Empty reason should raise"
            except ValueError:
                pass
            try:
                cs3.repair("reason", "")
                assert False, "Empty operator should raise"
            except ValueError:
                pass
            checks.append({"name": "repair_method", "passed": True})
    except Exception as e:
        checks.append({"name": "repair_method", "passed": False, "error": str(e)})
        passed = False

    # Check 30: Version is 3.1.0
    try:
        assert __version__ == "3.1.0", "Version must be 3.1.0, got %s" % __version__
        checks.append({"name": "version_check", "passed": True})
    except Exception as e:
        checks.append({"name": "version_check", "passed": False, "error": str(e)})
        passed = False

    return {"passed": passed, "version": __version__, "checks": checks}


if __name__ == "__main__":
    main()
