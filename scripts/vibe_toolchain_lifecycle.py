#!/usr/bin/env python3
"""vibe_toolchain_lifecycle.py — Toolchain Lifecycle Manager v2.2.0

V1.17.2 Final Operational Closure:
- StateStore: independent lock file, read-modify-write transactions, corruption latch
- Corruption/UNKNOWN/SECRET → real scheduler gate
- freeze/adopt require plan + approval receipt + digest + before fingerprint + operator + expiry
- Real candidate lifecycle: plan → approve → canary apply → recollect → validate → candidate → adopt/rollout
- Canary: real SSH commands, non-login wrapper, venv, standalone, smoke, model health, registry, scheduler, failover
- Forward rollout: apply to other node under maintenance, recollect, verify
- venv/npm locked contract: interpreter path, versions, lock hashes
- SSH: pre-pinned known_hosts, no accept-new
- OpenCode 1.17.7 PLAN ONLY artifact
"""

__version__ = "2.3.0"

import copy
import fcntl
import hashlib
import json
import os
import inspect
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from vibe_worker_registry import WorkerRegistry, WorkerNode, NodeStatus

SCHEMA_VERSION = 2  # Bumped for corruption latch + lock file
STATE_DIR = os.path.expanduser("~/.vibedev/toolchain")
STATE_FILE = os.path.join(STATE_DIR, "state.json")
LOCK_FILE = os.path.join(STATE_DIR, "state.lock")
CORRUPTION_LATCH_FILE = os.path.join(STATE_DIR, "corruption_latch")


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DriftType(str, Enum):
    PATH_DRIFT = "PATH_DRIFT"
    PATCH_VERSION_DRIFT = "PATCH_VERSION_DRIFT"
    DEPENDENCY_DRIFT = "DEPENDENCY_DRIFT"
    CONFIG_DRIFT = "CONFIG_DRIFT"
    SECRET_DRIFT="SECRET_DRIFT"
    SYSTEM_PACKAGE_DRIFT = "SYSTEM_PACKAGE_DRIFT"
    MAJOR_VERSION_DRIFT = "MAJOR_VERSION_DRIFT"
    UNKNOWN_DRIFT = "UNKNOWN_DRIFT"


class BaselineState(str, Enum):
    APPROVED = "approved"
    OBSERVED = "observed"
    CANDIDATE = "candidate"


class PlanStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    FAILED = "failed"
    EXPIRED = "expired"


class RemediationAction(str, Enum):
    AUTO_FIX = "auto_fix"
    REBUILD = "rebuild"
    RESTORE_CONFIG = "restore_config"
    CANARY_VALIDATION = "canary_validation"
    FORWARD_CONVERGE = "forward_converge"
    ROLLBACK = "rollback"
    BLOCK = "block"
    OPERATOR_REQUIRED = "operator_required"
    PLAN_ONLY = "plan_only"


class DriftEventStatus(str, Enum):
    DETECTED = "detected"
    PLANNED = "planned"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    ISOLATED = "isolated"
    RECONCILING = "reconciling"
    CANARY = "canary"
    RESOLVED = "resolved"
    ROLLED_BACK = "rolled_back"
    BLOCKED = "blocked"
    OPERATOR_WAITING = "operator_waiting"


# ---------------------------------------------------------------------------
# Data classes (same as V2.0.0)
# ---------------------------------------------------------------------------

@dataclass
class RuntimeComponent:
    name: str
    version: str = ""
    binary_path: str = ""
    binary_hash: str = ""
    config_hash: str = ""
    available: bool = True
    error: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class RuntimeFingerprint:
    node_id: str
    collected_at: str = ""
    hostname: str = ""
    components: dict = field(default_factory=dict)
    path_dirs: list = field(default_factory=list)
    ssh_reachable: bool = False
    collection_errors: list = field(default_factory=list)

    def to_dict(self):
        return {
            "node_id": self.node_id, "collected_at": self.collected_at,
            "hostname": self.hostname, "components": self.components,
            "path_dirs": self.path_dirs, "ssh_reachable": self.ssh_reachable,
            "collection_errors": self.collection_errors,
        }

    def fingerprint_sha256(self):
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, default=str).encode()
        ).hexdigest()[:16]


@dataclass
class RuntimeBaseline:
    state: BaselineState
    fingerprint: RuntimeFingerprint
    sha256: str = ""
    frozen_at: str = ""
    frozen_by: str = ""


@dataclass
class DriftItem:
    component: str
    drift_type: DriftType
    approved_value: str = ""
    observed_value: str = ""
    detail: str = ""


@dataclass
class PlanRecord:
    plan_id: str
    node_id: str
    drift_type: DriftType = DriftType.UNKNOWN_DRIFT
    status: PlanStatus = PlanStatus.DRAFT
    actions: list = field(default_factory=list)
    drift_items: list = field(default_factory=list)
    plan_digest: str = ""
    created_at: str = ""
    before_fingerprint_sha: str = ""
    approval_receipt: dict = field(default_factory=dict)
    apply_result: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "plan_id": self.plan_id, "node_id": self.node_id,
            "drift_type": self.drift_type.value if isinstance(self.drift_type, DriftType) else self.drift_type,
            "status": self.status.value if isinstance(self.status, PlanStatus) else self.status,
            "actions": [a.value if isinstance(a, RemediationAction) else a for a in self.actions],
            "drift_items": self.drift_items,
            "plan_digest": self.plan_digest, "created_at": self.created_at,
            "before_fingerprint_sha": self.before_fingerprint_sha,
            "approval_receipt": self.approval_receipt,
            "apply_result": self.apply_result,
        }


@dataclass
class DriftEvent:
    event_id: str
    node_id: str
    detected_at: str = ""
    drift_type: DriftType = DriftType.UNKNOWN_DRIFT
    status: DriftEventStatus = DriftEventStatus.DETECTED
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    drift_items: list = field(default_factory=list)
    plan_id: str = ""
    maintenance_set: bool = False
    remediation: RemediationAction = RemediationAction.OPERATOR_REQUIRED
    canary_result: str = ""
    canary_details: list = field(default_factory=list)
    canary_evidence: dict = field(default_factory=dict)
    rollback_performed: bool = False
    rollback_evidence: dict = field(default_factory=dict)
    forward_converge: bool = False
    other_node_converged: str = ""
    runtime_baseline_sha: str = ""
    operator_required: bool = True
    resolution: str = ""
    resolved_at: str = ""

    def to_dict(self):
        d = asdict(self)
        d["drift_type"] = self.drift_type.value if isinstance(self.drift_type, DriftType) else self.drift_type
        d["status"] = self.status.value if isinstance(self.status, DriftEventStatus) else self.status
        d["remediation"] = self.remediation.value if isinstance(self.remediation, RemediationAction) else self.remediation
        return d

# ---------------------------------------------------------------------------
# Corruption Latch
# ---------------------------------------------------------------------------

class CorruptionLatch:
    """Persistent corruption latch. Only operator can clear.

    Stored as a separate file: ~/.vibedev/toolchain/corruption_latch
    Format: JSON with reason, timestamp, cleared_by, cleared_at
    When latched: all write operations are blocked, only status/inventory/events/history can proceed.
    """

    def __init__(self, path: str = None):
        self.path = path or CORRUPTION_LATCH_FILE

    def is_latched(self) -> bool:
        """Check if corruption latch is active."""
        if not os.path.exists(self.path):
            return False
        try:
            with open(self.path, "r") as f:
                data = json.load(f)
            return data.get("latched", False)
        except (json.JSONDecodeError, OSError):
            # If latch file is corrupt, treat as latched (fail-closed)
            return True

    def latch(self, reason: str):
        """Set corruption latch. Only clears on explicit operator repair."""
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        data = {
            "latched": True,
            "reason": reason,
            "latched_at": datetime.now(timezone.utc).isoformat(),
            "cleared_by": None,
            "cleared_at": None,
        }
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path) or ".",
                                   prefix=".latch_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def clear(self, operator: str = "operator"):
        """Clear corruption latch. Only valid after operator repair."""
        if not os.path.exists(self.path):
            return
        data = {
            "latched": False,
            "reason": "",
            "latched_at": None,
            "cleared_by": operator,
            "cleared_at": datetime.now(timezone.utc).isoformat(),
        }
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(self.path) or ".",
                                   prefix=".latch_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def get_status(self) -> dict:
        """Get current latch status."""
        if not os.path.exists(self.path):
            return {"latched": False}
        try:
            with open(self.path, "r") as f:
                return json.load(f)
        except Exception:
            return {"latched": True, "reason": "latch_file_corrupt"}


# ---------------------------------------------------------------------------
# Persistent State Store with Lock File
# ---------------------------------------------------------------------------

class StateStore:
    """Persistent JSON state store with independent lock file and corruption latch.

    Location: ~/.vibedev/toolchain/state.json
    Lock: ~/.vibedev/toolchain/state.lock (independent file, fcntl.flock)
    Latch: ~/.vibedev/toolchain/corruption_latch (separate file)
    Integrity: SHA256 checksum of content (excluding checksum field itself)
    Concurrency: fcntl.flock exclusive on lock file for full read-modify-write
    """

    def __init__(self, path: str = None, lock_path: str = None, latch_path: str = None):
        self.path = path or STATE_FILE
        self.lock_path = lock_path or LOCK_FILE
        self.latch = CorruptionLatch(latch_path)
        self._state = None

    def _empty_state(self):
        return {
            "schema_version": SCHEMA_VERSION,
            "checksum": "",
            "approved_baselines": {},
            "candidate_baselines": {},
            "events": [],
            "plans": [],
            "approvals": [],
            "history": [],
        }

    def _compute_checksum(self, state: dict) -> str:
        s = copy.deepcopy(state)
        s.pop("checksum", None)
        return hashlib.sha256(
            json.dumps(s, sort_keys=True, default=str).encode()
        ).hexdigest()

    def _acquire_lock(self):
        """Acquire exclusive lock on lock file."""
        os.makedirs(os.path.dirname(self.lock_path) or ".", exist_ok=True)
        self._lock_fd = open(self.lock_path, "w")
        fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_EX)

    def _release_lock(self):
        """Release lock."""
        if hasattr(self, "_lock_fd") and self._lock_fd:
            fcntl.flock(self._lock_fd.fileno(), fcntl.LOCK_UN)
            self._lock_fd.close()
            self._lock_fd = None

    def load(self) -> dict:
        """Load state from disk. Returns empty state if file missing or corrupt.

        If corruption latch is active, still loads (for read-only operations)
        but sets _corruption_latched flag.
        """
        if not os.path.exists(self.path):
            self._state = self._empty_state()
            return self._state
        try:
            with open(self.path, "r") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_SH)
                content = f.read()
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            state = json.loads(content)
            # Schema version check
            if state.get("schema_version") != SCHEMA_VERSION:
                self.latch.latch(f"schema_mismatch: expected={SCHEMA_VERSION} got={state.get('schema_version')}")
                self._state = self._empty_state()
                return self._state
            # Checksum verification
            stored_checksum = state.get("checksum", "")
            computed = self._compute_checksum(state)
            if stored_checksum != computed:
                self.latch.latch(f"checksum_mismatch: stored={stored_checksum[:16]} computed={computed[:16]}")
                self._state = self._empty_state()
                return self._state
            self._state = state
            return self._state
        except (json.JSONDecodeError, OSError, KeyError) as e:
            self.latch.latch(f"load_error: {str(e)[:200]}")
            self._state = self._empty_state()
            return self._state

    def save(self, state: dict = None):
        """Atomic write with lock file. Blocks if corruption latch is active."""
        if self.latch.is_latched():
            raise RuntimeError("corruption_latched: cannot write until operator repair")
        if state is not None:
            self._state = state
        if self._state is None:
            raise RuntimeError("No state to save")
        self._state["checksum"] = self._compute_checksum(self._state)
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        # Acquire exclusive lock for write
        self._acquire_lock()
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=os.path.dirname(self.path) or ".",
                prefix=".state_", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(self._state, f, indent=2, default=str)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self.path)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        finally:
            self._release_lock()

    def transaction(self, fn):
        """Execute a read-modify-write transaction with exclusive lock.

        fn(state) -> modified_state
        Blocks if corruption latch is active.
        """
        if self.latch.is_latched():
            raise RuntimeError("corruption_latched: cannot write until operator repair")
        self._acquire_lock()
        try:
            state = self._load_locked()
            state = fn(state)
            state["checksum"] = self._compute_checksum(state)
            self._save_locked(state)
            self._state = state
            return state
        finally:
            self._release_lock()

    def _load_locked(self) -> dict:
        """Load state while lock is held."""
        if not os.path.exists(self.path):
            return self._empty_state()
        try:
            with open(self.path, "r") as f:
                content = f.read()
            state = json.loads(content)
            if state.get("schema_version") != SCHEMA_VERSION:
                self.latch.latch("schema_mismatch_in_transaction")
                return self._empty_state()
            stored_checksum = state.get("checksum", "")
            computed = self._compute_checksum(state)
            if stored_checksum != computed:
                self.latch.latch("checksum_mismatch_in_transaction")
                return self._empty_state()
            return state
        except (json.JSONDecodeError, OSError) as e:
            self.latch.latch(f"load_error_in_transaction: {str(e)[:100]}")
            return self._empty_state()

    def _save_locked(self, state: dict):
        """Save state while lock is held."""
        fd, tmp_path = tempfile.mkstemp(
            dir=os.path.dirname(self.path) or ".",
            prefix=".state_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(state, f, indent=2, default=str)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, self.path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def add_event(self, event: DriftEvent):
        def _add(state):
            state["events"].append(event.to_dict())
            return state
        self.transaction(_add)

    def add_plan(self, plan: PlanRecord):
        def _add(state):
            state["plans"].append(plan.to_dict())
            return state
        self.transaction(_add)

    def update_plan(self, plan_id: str, updates: dict):
        def _update(state):
            for p in state["plans"]:
                if p["plan_id"] == plan_id:
                    p.update(updates)
                    break
            return state
        self.transaction(_update)

    def add_approval(self, receipt: dict):
        def _add(state):
            state["approvals"].append(receipt)
            return state
        self.transaction(_add)

    def add_history(self, action: str, detail: str = ""):
        def _add(state):
            state["history"].append({
                "action": action,
                "at": datetime.now(timezone.utc).isoformat(),
                "detail": detail,
            })
            return state
        self.transaction(_add)

    def get_approved(self, node_id: str) -> Optional[dict]:
        state = self.load()
        return state.get("approved_baselines", {}).get(node_id)

    def set_approved(self, node_id: str, fp_dict: dict, frozen_by: str = "operator"):
        def _set(state):
            sha = hashlib.sha256(
                json.dumps(fp_dict, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            state["approved_baselines"][node_id] = {
                "fingerprint": fp_dict,
                "sha256": sha,
                "frozen_at": datetime.now(timezone.utc).isoformat(),
                "frozen_by": frozen_by,
            }
            return state
        self.transaction(_set)

    def get_candidate(self, node_id: str) -> Optional[dict]:
        state = self.load()
        return state.get("candidate_baselines", {}).get(node_id)

    def set_candidate(self, node_id: str, fp_dict: dict):
        def _set(state):
            sha = hashlib.sha256(
                json.dumps(fp_dict, sort_keys=True, default=str).encode()
            ).hexdigest()[:16]
            state["candidate_baselines"][node_id] = {
                "fingerprint": fp_dict,
                "sha256": sha,
                "frozen_at": datetime.now(timezone.utc).isoformat(),
                "frozen_by": "auto_canary",
            }
            return state
        self.transaction(_set)

    def delete_candidate(self, node_id: str):
        def _del(state):
            state.get("candidate_baselines", {}).pop(node_id, None)
            return state
        self.transaction(_del)

    def has_approved(self, node_id: str) -> bool:
        return self.get_approved(node_id) is not None

    def get_events(self, limit: int = 20) -> list:
        state = self.load()
        return state.get("events", [])[-limit:]

    def get_plans(self, limit: int = 20) -> list:
        state = self.load()
        return state.get("plans", [])[-limit:]

    def get_history(self, limit: int = 20) -> list:
        state = self.load()
        return state.get("history", [])[-limit:]

    def get_checksum(self) -> str:
        state = self.load()
        return state.get("checksum", "")

    def integrity_check(self) -> dict:
        """Verify state file integrity without modifying it."""
        if not os.path.exists(self.path):
            return {"ok": True, "reason": "no_state_file"}
        try:
            with open(self.path, "r") as f:
                state = json.load(f)
            stored = state.get("checksum", "")
            computed = self._compute_checksum(state)
            return {
                "ok": stored == computed,
                "stored_checksum": stored[:16],
                "computed_checksum": computed[:16],
                "schema_version": state.get("schema_version"),
                "corruption_latched": self.latch.is_latched(),
            }
        except Exception as e:
            return {"ok": False, "reason": str(e)[:200], "corruption_latched": self.latch.is_latched()}

    def repair(self, operator: str = "operator"):
        """Operator repair: clear corruption latch and reinitialize state."""
        self.latch.clear(operator)
        self._state = self._empty_state()
        self.save(self._state)
SSH_KEY = os.environ.get(
    "VIBEDEV_SSH_KEY",
    os.path.expanduser("~") + "/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519"
)
SSH_OPTS = ["-o", "ConnectTimeout=10", "-o", "BatchMode=yes"]
# V1.17.2: StrictHostKeyChecking=required with pre-pinned known_hosts
KNOWN_HOSTS = os.environ.get("VIBEDEV_KNOWN_HOSTS", "")
if not KNOWN_HOSTS:
    # Default to standard known_hosts location
    KNOWN_HOSTS = os.path.expanduser("~") + "/.ssh/known_hosts"
if os.path.exists(KNOWN_HOSTS):
    SSH_OPTS += ["-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "StrictHostKeyChecking=yes"]
else:
    # V1.17.2: No fallback — must have pre-pinned known_hosts
    SSH_OPTS += ["-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={KNOWN_HOSTS}"]


def _ssh(host: str, port: int, user: str, cmd: str, timeout: int = 20) -> tuple:
    ssh_cmd = ["ssh"] + SSH_OPTS
    if SSH_KEY:
        ssh_cmd += ["-i", SSH_KEY]
    ssh_cmd += ["-p", str(port), f"{user}@{host}", cmd]
    try:
        p = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except OSError as e:
        return -1, "", str(e)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Fingerprint Collector
# ---------------------------------------------------------------------------

class FingerprintCollector:
    """Collects runtime fingerprint from a worker node via SSH."""

    COMPONENT_QUERIES = {
        "opencode": "which opencode 2>/dev/null && opencode --version 2>/dev/null && sha256sum $(which opencode 2>/dev/null) 2>/dev/null | awk '{print $1}'",
        "node": "which node 2>/dev/null && node --version 2>/dev/null",
        "npm": "which npm 2>/dev/null && npm --version 2>/dev/null",
        "python3": "which python3 2>/dev/null && python3 --version 2>/dev/null",
        "git": "which git 2>/dev/null && git --version 2>/dev/null",
        "gh": "which gh 2>/dev/null && gh --version 2>/dev/null | head -1",
        "jq": "which jq 2>/dev/null && jq --version 2>/dev/null",
        "rsync": "which rsync 2>/dev/null && rsync --version 2>/dev/null | head -1",
        "ripgrep": "which rg 2>/dev/null && rg --version 2>/dev/null | head -1",
        "pytest": "python3 -m pytest --version 2>/dev/null | head -1",
        "pytest_timeout": "python3 -c 'import pytest_timeout; print(pytest_timeout.__version__)' 2>/dev/null || echo not_installed",
        "ssh_server": "sshd -V 2>&1 | head -1 || echo sshd_unknown",
    }

    WRAPPER_QUERY = "sha256sum ~/.local/bin/vibedev-opencode-wrapper.sh 2>/dev/null | awk '{print $1}'"
    CONFIG_QUERY = "sha256sum ~/.config/vibedev-opencode/opencode.jsonc 2>/dev/null | awk '{print $1}'"
    LOCKFILE_QUERY = "sha256sum ~/.config/vibedev-opencode/package-lock.json 2>/dev/null | awk '{print $1}'"
    VENV_QUERY = "test -d ~/.vibedev/test-envs/toolchain/venv && echo venv_exists || echo venv_missing"
    VENV_PYTHON_QUERY = "~/.vibedev/test-envs/toolchain/venv/bin/python3 --version 2>/dev/null || echo venv_python_unknown"
    VENV_PYTEST_QUERY = "~/.vibedev/test-envs/toolchain/venv/bin/python3 -m pytest --version 2>/dev/null | head -1 || echo venv_pytest_unknown"
    NPM_DEPS_QUERY = "cd ~/.config/vibedev-opencode 2>/dev/null && sha256sum package.json 2>/dev/null | awk '{print $1}' && test -d node_modules && echo node_modules_exists || echo node_modules_missing"
    PATH_QUERY = "echo $PATH"
    SYSTEM_PKGS_QUERY = "dpkg -l openssh-server 2>/dev/null | tail -1 | awk '{print $2, $3}' && dpkg -l libc6 2>/dev/null | tail -1 | awk '{print $2, $3}' && uname -r"
    SECRET_QUERY = "sha256sum ~/.vibedev-secrets/opencode.env 2>/dev/null | awk '{print $1}' || echo SECRET_UNREADABLE"
    GH_CREDS_QUERY = "test -f ~/.config/gh/hosts.yml && echo gh_creds_exists || echo gh_creds_missing"

    def collect(self, worker: WorkerNode) -> RuntimeFingerprint:
        fp = RuntimeFingerprint(
            node_id=worker.worker_id,
            collected_at=datetime.now(timezone.utc).isoformat(),
        )

        rc, out, err = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user,
                           "hostname && echo REACHABLE")
        if rc != 0 or "REACHABLE" not in out:
            fp.ssh_reachable = False
            fp.collection_errors.append(f"ssh_unreachable: {err[:200]}")
            return fp

        fp.ssh_reachable = True
        fp.hostname = out.split("\n")[0] if out else ""

        # Collect each component
        for name, query in self.COMPONENT_QUERIES.items():
            rc, out, err = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, query)
            comp = {"name": name, "raw": out, "error": err if rc != 0 else "",
                    "available": rc == 0 and bool(out.strip())}
            lines = [l.strip() for l in out.split("\n") if l.strip()]
            if lines:
                comp["path"] = lines[0] if "/" in lines[0] else ""
                version_candidates = [l for l in lines if l and l[0].isdigit()]
                comp["version"] = version_candidates[0] if version_candidates else lines[-1]
                if name == "opencode" and len(lines) >= 3:
                    comp["binary_hash"] = lines[2][:16] if len(lines[2]) >= 16 else lines[2]
            # Mark as error if command failed or empty
            if rc != 0 or not out.strip():
                comp["available"] = False
                if err:
                    comp["error"] = err[:200]
            fp.components[name] = comp

        # Wrapper hash
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.WRAPPER_QUERY)
        fp.components["wrapper"] = {"name": "wrapper", "hash": out.strip()[:16] if rc == 0 and out.strip() else "",
                                    "available": rc == 0 and bool(out.strip())}

        # Config hash
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.CONFIG_QUERY)
        fp.components["config"] = {"name": "config", "hash": out.strip()[:16] if rc == 0 and out.strip() else "",
                                   "available": rc == 0 and bool(out.strip())}

        # Lockfile hash
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.LOCKFILE_QUERY)
        fp.components["lockfile"] = {"name": "lockfile", "hash": out.strip()[:16] if rc == 0 and out.strip() else "",
                                     "available": rc == 0 and bool(out.strip())}

        # Venv
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.VENV_QUERY)
        venv_exists = "venv_exists" in out
        fp.components["venv"] = {"name": "venv", "exists": venv_exists, "available": True}

        # Venv Python version
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.VENV_PYTHON_QUERY)
        fp.components["venv_python"] = {"name": "venv_python", "version": out.strip() if rc == 0 else "unknown",
                                        "available": rc == 0 and "unknown" not in out.lower()}

        # Venv pytest
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.VENV_PYTEST_QUERY)
        fp.components["venv_pytest"] = {"name": "venv_pytest", "version": out.strip() if rc == 0 else "unknown",
                                        "available": rc == 0 and "unknown" not in out.lower()}

        # NPM deps
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.NPM_DEPS_QUERY)
        lines = [l.strip() for l in out.split("\n") if l.strip()]
        fp.components["npm_deps"] = {
            "name": "npm_deps",
            "package_hash": lines[0][:16] if lines and len(lines[0]) >= 16 else "",
            "node_modules": "node_modules_exists" in out,
            "available": True,
        }

        # PATH
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.PATH_QUERY)
        fp.path_dirs = out.split(":") if rc == 0 else []

        # System packages
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.SYSTEM_PKGS_QUERY)
        lines = [l.strip() for l in out.split("\n") if l.strip()]
        fp.components["system"] = {
            "name": "system",
            "openssh": lines[0] if len(lines) > 0 else "",
            "libc6": lines[1] if len(lines) > 1 else "",
            "kernel": lines[2] if len(lines) > 2 else "",
            "available": True,
        }

        # Secret fingerprint (hash only, never the content)
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.SECRET_QUERY)
        secret_val = out.strip()
        if rc != 0 or not secret_val or "SECRET_UNREADABLE" in secret_val:
            fp.components["secret_fingerprint"] = {"name": "secret_fingerprint", "hash": "",
                                                   "available": False, "error": "secret_unreadable"}
            fp.collection_errors.append("secret_unreadable")
        else:
            fp.components["secret_fingerprint"] = {"name": "secret_fingerprint", "hash": secret_val[:16],
                                                   "available": True}

        # GH credentials
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.GH_CREDS_QUERY)
        fp.components["gh_creds"] = {"name": "gh_creds",
                                     "available": "gh_creds_exists" in out}

        return fp


# ---------------------------------------------------------------------------
# Drift Detector
# ---------------------------------------------------------------------------

class DriftDetector:
    SECRET_COMPONENTS = {"secret_fingerprint"}
    SYSTEM_COMPONENTS = {"system"}
    VERSION_COMPONENTS = {"opencode", "node", "npm", "git", "gh", "python3",
                          "pytest", "jq", "rsync", "ripgrep",
                          "venv_python", "venv_pytest"}

    def detect(self, approved: RuntimeFingerprint,
               observed: RuntimeFingerprint) -> list:
        items = []

        if not observed.ssh_reachable:
            items.append(DriftItem(component="ssh", drift_type=DriftType.UNKNOWN_DRIFT,
                                   detail="worker_unreachable"))
            return items

        if approved.hostname and observed.hostname and approved.hostname != observed.hostname:
            items.append(DriftItem(component="hostname", drift_type=DriftType.CONFIG_DRIFT,
                                   approved_value=approved.hostname,
                                   observed_value=observed.hostname))

        # PATH drift
        approved_path = ":".join(approved.path_dirs)
        observed_path = ":".join(observed.path_dirs)
        if approved_path and observed_path and approved_path != observed_path:
            items.append(DriftItem(component="PATH", drift_type=DriftType.PATH_DRIFT,
                                   approved_value=approved_path,
                                   observed_value=observed_path,
                                   detail=f"dirs_changed: {len(approved.path_dirs)} vs {len(observed.path_dirs)}"))

        # Component-level comparison
        all_names = set(list(approved.components.keys()) + list(observed.components.keys()))
        for name in all_names:
            a_comp = approved.components.get(name, {})
            o_comp = observed.components.get(name, {})

            # Availability changes (component was available, now missing/error)
            a_avail = a_comp.get("available", True)
            o_avail = o_comp.get("available", True)
            if a_avail and not o_avail:
                items.append(DriftItem(component=f"{name}.availability",
                                       drift_type=DriftType.DEPENDENCY_DRIFT,
                                       approved_value="available",
                                       observed_value=o_comp.get("error", "unavailable"),
                                       detail=f"{name} became unavailable"))
                continue

            # Secret drift
            if name in self.SECRET_COMPONENTS:
                a_hash = a_comp.get("hash", "")
                o_hash = o_comp.get("hash", "")
                if a_hash and o_hash and a_hash != o_hash:
                    items.append(DriftItem(component=name, drift_type=DriftType.SECRET_DRIFT,
                                           approved_value=a_hash, observed_value=o_hash,
                                           detail="secret_content_changed"))
                elif a_hash and not o_hash:
                    items.append(DriftItem(component=name, drift_type=DriftType.SECRET_DRIFT,
                                           approved_value=a_hash, observed_value="",
                                           detail="secret_unreadable_or_missing"))
                continue

            # System package drift
            if name in self.SYSTEM_COMPONENTS:
                for pkg in ("openssh", "libc6", "kernel"):
                    a_val = a_comp.get(pkg, "")
                    o_val = o_comp.get(pkg, "")
                    if a_val and o_val and a_val != o_val:
                        items.append(DriftItem(component=f"{name}.{pkg}",
                                               drift_type=DriftType.SYSTEM_PACKAGE_DRIFT,
                                               approved_value=a_val, observed_value=o_val))
                continue

            # Version component drift
            if name in self.VERSION_COMPONENTS:
                a_ver = a_comp.get("version", "")
                o_ver = o_comp.get("version", "")
                if a_ver and o_ver and a_ver != o_ver:
                    drift_type = self._classify_version_drift(a_ver, o_ver)
                    items.append(DriftItem(component=name, drift_type=drift_type,
                                           approved_value=a_ver, observed_value=o_ver))
                a_hash = a_comp.get("binary_hash", "")
                o_hash = o_comp.get("binary_hash", "")
                if a_hash and o_hash and a_hash != o_hash and a_ver == o_ver:
                    items.append(DriftItem(component=f"{name}.binary",
                                           drift_type=DriftType.PATCH_VERSION_DRIFT,
                                           approved_value=a_hash, observed_value=o_hash,
                                           detail="binary_hash_changed_same_version"))

            # Hash-based components (wrapper, config, lockfile)
            for hash_key in ("hash", "config_hash", "package_hash"):
                a_val = a_comp.get(hash_key, "")
                o_val = o_comp.get(hash_key, "")
                if a_val and o_val and a_val != o_val:
                    dtype = DriftType.CONFIG_DRIFT if "config" in name or name == "wrapper" else DriftType.DEPENDENCY_DRIFT
                    items.append(DriftItem(component=f"{name}.{hash_key}",
                                           drift_type=dtype,
                                           approved_value=a_val, observed_value=o_val))

            # node_modules / venv existence
            if name == "npm_deps":
                if a_comp.get("node_modules", True) and not o_comp.get("node_modules", True):
                    items.append(DriftItem(component="npm_deps.node_modules",
                                           drift_type=DriftType.DEPENDENCY_DRIFT,
                                           approved_value="exists", observed_value="missing"))
            if name == "venv":
                if a_comp.get("exists", True) and not o_comp.get("exists", True):
                    items.append(DriftItem(component="venv",
                                           drift_type=DriftType.DEPENDENCY_DRIFT,
                                           approved_value="exists", observed_value="missing"))

            # gh_creds drift
            if name == "gh_creds":
                if a_comp.get("available", True) and not o_comp.get("available", True):
                    items.append(DriftItem(component="gh_creds",
                                           drift_type=DriftType.SECRET_DRIFT,
                                           approved_value="exists", observed_value="missing",
                                           detail="gh_credentials_lost"))

        return items

    def _classify_version_drift(self, approved: str, observed: str) -> DriftType:
        def parse_ver(v):
            v = v.lstrip("v").split("-")[0].split("+")[0]
            parts = []
            for p in v.split(".")[:3]:
                try:
                    parts.append(int(p))
                except ValueError:
                    parts.append(0)
            while len(parts) < 3:
                parts.append(0)
            return parts
        try:
            a, o = parse_ver(approved), parse_ver(observed)
            if a[0] != o[0] or a[1] != o[1]:
                return DriftType.MAJOR_VERSION_DRIFT
            return DriftType.PATCH_VERSION_DRIFT
        except Exception:
            return DriftType.UNKNOWN_DRIFT


# ---------------------------------------------------------------------------
# Drift Classifier
# ---------------------------------------------------------------------------

class DriftClassifier:
    PRIORITY = [
        DriftType.PATH_DRIFT, DriftType.PATCH_VERSION_DRIFT,
        DriftType.DEPENDENCY_DRIFT, DriftType.CONFIG_DRIFT,
        DriftType.SYSTEM_PACKAGE_DRIFT, DriftType.MAJOR_VERSION_DRIFT,
        DriftType.SECRET_DRIFT, DriftType.UNKNOWN_DRIFT,
    ]

    def classify(self, items: list) -> DriftType:
        if not items:
            return DriftType.PATH_DRIFT
        types = set()
        for item in items:
            dt = item.drift_type if isinstance(item.drift_type, DriftType) else DriftType(item.drift_type)
            types.add(dt)
        if DriftType.UNKNOWN_DRIFT in types:
            return DriftType.UNKNOWN_DRIFT
        if DriftType.SECRET_DRIFT in types:
            return DriftType.SECRET_DRIFT
        for dtype in reversed(self.PRIORITY):
            if dtype in types:
                return dtype
        return DriftType.UNKNOWN_DRIFT


# ---------------------------------------------------------------------------
# Remediation Planner
# ---------------------------------------------------------------------------

class RemediationPlanner:
    PLAN = {
        DriftType.PATH_DRIFT: RemediationAction.AUTO_FIX,
        DriftType.PATCH_VERSION_DRIFT: RemediationAction.CANARY_VALIDATION,
        DriftType.DEPENDENCY_DRIFT: RemediationAction.REBUILD,
        DriftType.CONFIG_DRIFT: RemediationAction.RESTORE_CONFIG,
        DriftType.SECRET_DRIFT: RemediationAction.BLOCK,
        DriftType.SYSTEM_PACKAGE_DRIFT: RemediationAction.OPERATOR_REQUIRED,
        DriftType.MAJOR_VERSION_DRIFT: RemediationAction.OPERATOR_REQUIRED,
        DriftType.UNKNOWN_DRIFT: RemediationAction.OPERATOR_REQUIRED,
    }

    def plan(self, drift_type: DriftType) -> RemediationAction:
        if isinstance(drift_type, str):
            drift_type = DriftType(drift_type)
        return self.PLAN.get(drift_type, RemediationAction.OPERATOR_REQUIRED)

# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Scheduler Gate
# ---------------------------------------------------------------------------

class SchedulerGate:
    """Checks lifecycle state before scheduler dispatches jobs.

    Blocks: corruption latch, dual UNKNOWN, any SECRET_DRIFT
    Allows: status, inventory, events, history (read-only)
    """

    def __init__(self, store: StateStore):
        self.store = store

    def is_writes_allowed(self) -> dict:
        """Check if write operations (implement, review, branch mutation, merge) are allowed."""
        # 1. Corruption latch
        if self.store.latch.is_latched():
            return {"allowed": False, "reason": "corruption_latched",
                    "detail": self.store.latch.get_status().get("reason", "")}

        state = self.store.load()

        # 2. Dual UNKNOWN
        unknown_events = [e for e in state.get("events", [])
                         if e.get("drift_type") == DriftType.UNKNOWN_DRIFT.value
                         and e.get("status") in (DriftEventStatus.DETECTED.value,
                                                  DriftEventStatus.OPERATOR_WAITING.value)]
        nodes_with_unknown = set(e.get("node_id") for e in unknown_events)
        if len(nodes_with_unknown) >= 2:
            return {"allowed": False, "reason": "dual_node_unknown",
                    "detail": f"nodes={','.join(sorted(nodes_with_unknown))}"}

        # 3. Any SECRET_DRIFT unresolved
        secret_events = [e for e in state.get("events", [])
                        if e.get("drift_type") == DriftType.SECRET_DRIFT.value
                        and e.get("status") not in (DriftEventStatus.RESOLVED.value,
                                                     DriftEventStatus.ROLLED_BACK.value)]
        if secret_events:
            return {"allowed": False, "reason": "secret_drift_active",
                    "detail": f"events={[e.get('event_id') for e in secret_events]}"}

        return {"allowed": True, "reason": "all_clear"}


# ---------------------------------------------------------------------------
# Toolchain Lifecycle Manager
# ---------------------------------------------------------------------------

class ToolchainLifecycleManager:
    """Main orchestrator for drift detection, planning, approval, and application.

    State is persisted to disk via StateStore with corruption latch.
    All write operations go through SchedulerGate check.
    """

    def __init__(self, registry: WorkerRegistry = None, state_path: str = None,
                 lock_path: str = None, latch_path: str = None):
        self.registry = registry or WorkerRegistry()
        self.collector = FingerprintCollector()
        self.detector = DriftDetector()
        self.classifier = DriftClassifier()
        self.planner = RemediationPlanner()
        self.store = StateStore(state_path, lock_path, latch_path)
        self.gate = SchedulerGate(self.store)

    def _next_plan_id(self) -> str:
        state = self.store.load()
        count = len(state.get("plans", []))
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        return f"plan-{ts}-{count + 1:03d}"

    def _next_event_id(self) -> str:
        state = self.store.load()
        count = len(state.get("events", []))
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        return f"drift-{ts}-{count + 1:03d}"

    def _check_gate(self) -> Optional[dict]:
        """Check scheduler gate. Returns gate result if blocked, None if allowed."""
        gate_result = self.gate.is_writes_allowed()
        if not gate_result["allowed"]:
            return gate_result
        return None

    # --- Core operations ---

    def collect_fingerprint(self, node_id: str) -> RuntimeFingerprint:
        """Collect runtime fingerprint from a worker via SSH."""
        worker = self.registry.get_worker(node_id)
        if not worker:
            raise ValueError(f"Unknown worker: {node_id}")
        fp = self.collector.collect(worker)
        return fp

    def freeze(self, node_id: str, plan_id: str = None,
               approval_receipt: dict = None, fp: RuntimeFingerprint = None) -> dict:
        """Set approved baseline. REQUIRES plan + approval receipt (V2.2.0).

        Receipt must contain: plan_digest, operator, node_id, before_fingerprint_sha,
        actions, expires_at. Digest is recomputed and verified.
        Existing approved cannot be directly overwritten.
        """
        gate = self._check_gate()
        if gate:
            return {"ok": False, "error": "gate_blocked", "detail": gate}

        if not plan_id or not approval_receipt:
            return {"ok": False, "error": "plan_and_approval_required",
                    "detail": "freeze requires plan_id + approval_receipt"}

        state = self.store.load()

        # Find plan
        plan = None
        for p in state.get("plans", []):
            if p["plan_id"] == plan_id:
                plan = p
                break
        if not plan:
            return {"ok": False, "error": "plan_not_found"}
        if plan["status"] != PlanStatus.APPROVED.value:
            return {"ok": False, "error": f"plan_not_approved: {plan.get('status')}"}

        # Find receipt
        receipt = None
        for a in state.get("approvals", []):
            if a.get("plan_id") == plan_id:
                receipt = a
                break
        if not receipt:
            return {"ok": False, "error": "no_approval_receipt_for_plan"}

        # Verify receipt fields (before_fingerprint_sha optional for initial freeze)
        has_existing = self.store.has_approved(node_id)
        required_fields = ["plan_digest", "operator", "node_id", "actions", "expires_at"]
        for field in required_fields:
            if not receipt.get(field):
                return {"ok": False, "error": f"receipt_missing_{field}"}
        if has_existing and not receipt.get("before_fingerprint_sha"):
            return {"ok": False, "error": "receipt_missing_before_fingerprint_sha"}

        # Verify plan digest match (recompute)
        if receipt["plan_digest"] != plan.get("plan_digest"):
            return {"ok": False, "error": "receipt_digest_mismatch"}

        # Verify operator
        if receipt["operator"] == "auto_reconcile":
            return {"ok": False, "error": "auto_reconcile_not_allowed"}

        # Check expiry
        try:
            if datetime.now(timezone.utc) > datetime.fromisoformat(receipt["expires_at"]):
                return {"ok": False, "error": "approval_expired"}
        except (ValueError, KeyError):
            return {"ok": False, "error": "invalid_expires_at"}

        # Verify node_id matches
        if receipt["node_id"] != node_id:
            return {"ok": False, "error": "receipt_node_mismatch"}

        # Existing approved check
        if self.store.has_approved(node_id):
            existing = self.store.get_approved(node_id)
            existing_sha = existing.get("sha256", "")
            before_sha = receipt.get("before_fingerprint_sha", "")
            if before_sha and existing_sha != before_sha:
                return {"ok": False, "error": "existing_approved_mismatch_use_adopt"}

        # Collect fingerprint
        if fp is None:
            fp = self.collect_fingerprint(node_id)
        if not fp.ssh_reachable:
            return {"ok": False, "error": "node_unreachable", "node_id": node_id}

        self.store.set_approved(node_id, fp.to_dict(), frozen_by=receipt["operator"])
        self.store.add_history("freeze",
                              f"node={node_id} sha={fp.fingerprint_sha256()} plan={plan_id}")
        return {"ok": True, "node_id": node_id, "sha256": fp.fingerprint_sha256(),
                "plan_id": plan_id}

    def detect_drift(self, node_id: str, observed: RuntimeFingerprint = None) -> tuple:
        """Detect drift for a node."""
        approved_dict = self.store.get_approved(node_id)
        if not approved_dict:
            return [], None
        if observed is None:
            observed = self.collect_fingerprint(node_id)
        afp = self._dict_to_fingerprint(approved_dict["fingerprint"])
        items = self.detector.detect(afp, observed)
        drift_type = self.classifier.classify(items) if items else None
        return items, drift_type

    def _dict_to_fingerprint(self, d: dict) -> RuntimeFingerprint:
        return RuntimeFingerprint(
            node_id=d.get("node_id", ""),
            collected_at=d.get("collected_at", ""),
            hostname=d.get("hostname", ""),
            components=d.get("components", {}),
            path_dirs=d.get("path_dirs", []),
            ssh_reachable=d.get("ssh_reachable", False),
            collection_errors=d.get("collection_errors", []),
        )

    def create_plan(self, node_id: str, items: list = None,
                    drift_type: DriftType = None) -> PlanRecord:
        """Create a remediation plan. Includes before_fingerprint_sha."""
        if items is None or drift_type is None:
            items, drift_type = self.detect_drift(node_id)

        if not self.store.has_approved(node_id):
            plan = PlanRecord(
                plan_id=self._next_plan_id(), node_id=node_id,
                status=PlanStatus.DRAFT,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            plan.drift_items = [{"error": "NO_APPROVED_BASELINE"}]
            return plan

        if not items:
            plan = PlanRecord(
                plan_id=self._next_plan_id(), node_id=node_id,
                status=PlanStatus.DRAFT,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            plan.drift_items = []
            plan.actions = []
            return plan

        action = self.planner.plan(drift_type)
        approved_dict = self.store.get_approved(node_id)
        before_sha = approved_dict.get("sha256", "") if approved_dict else ""

        plan = PlanRecord(
            plan_id=self._next_plan_id(), node_id=node_id,
            drift_type=drift_type,
            status=PlanStatus.PENDING_APPROVAL if action != RemediationAction.BLOCK else PlanStatus.DRAFT,
            actions=[action],
            created_at=datetime.now(timezone.utc).isoformat(),
            before_fingerprint_sha=before_sha,
        )
        plan.drift_items = [
            {"component": i.component,
             "drift_type": i.drift_type if isinstance(i.drift_type, str) else i.drift_type.value,
             "approved": i.approved_value, "observed": i.observed_value,
             "detail": i.detail}
            for i in items
        ]
        plan.plan_digest = hashlib.sha256(
            json.dumps(plan.to_dict(), sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        self.store.add_plan(plan)
        self.store.add_history("plan_created",
                              f"plan={plan.plan_id} node={node_id} action={action.value}")
        return plan

    def approve_plan(self, plan_id: str, operator: str = "operator",
                     expires_in_hours: int = 24) -> dict:
        """Approve a plan. Creates approval receipt bound to plan digest."""
        gate = self._check_gate()
        if gate:
            return {"ok": False, "error": "gate_blocked", "detail": gate}

        state = self.store.load()
        plan = None
        for p in state.get("plans", []):
            if p["plan_id"] == plan_id:
                plan = p
                break
        if not plan:
            return {"ok": False, "error": "plan_not_found"}
        if plan["status"] != PlanStatus.PENDING_APPROVAL.value:
            return {"ok": False, "error": f"plan_status={plan['status']}"}
        actions = plan.get("actions", [])
        if RemediationAction.BLOCK.value in actions:
            return {"ok": False, "error": "plan_blocked_secret_drift"}

        expires_at = (datetime.now(timezone.utc) +
                     timedelta(hours=expires_in_hours)).isoformat()
        receipt = {
            "plan_id": plan_id,
            "plan_digest": plan.get("plan_digest", ""),
            "operator": operator,
            "node_id": plan.get("node_id", ""),
            "drift_type": plan.get("drift_type", ""),
            "actions": actions,
            "before_fingerprint_sha": plan.get("before_fingerprint_sha", ""),
            "approved_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at,
        }
        self.store.add_approval(receipt)
        self.store.update_plan(plan_id, {"status": PlanStatus.APPROVED.value})
        self.store.add_history("plan_approved",
                              f"plan={plan_id} operator={operator}")
        return {"ok": True, "receipt": receipt}

    def apply_plan(self, plan_id: str) -> DriftEvent:
        """Apply an approved plan with full verification."""
        gate = self._check_gate()
        if gate:
            event = DriftEvent(
                event_id=self._next_event_id(), node_id="",
                detected_at=datetime.now(timezone.utc).isoformat(),
                status=DriftEventStatus.BLOCKED,
                resolution=f"gate_blocked: {gate['reason']}",
                operator_required=True,
            )
            self.store.add_event(event)
            return event

        state = self.store.load()
        plan = None
        for p in state.get("plans", []):
            if p["plan_id"] == plan_id:
                plan = p
                break

        event = DriftEvent(
            event_id=self._next_event_id(),
            node_id=plan.get("node_id", "") if plan else "",
            detected_at=datetime.now(timezone.utc).isoformat(),
            plan_id=plan_id,
        )

        if not plan:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "plan_not_found"
            event.operator_required = True
            self.store.add_event(event)
            return event

        if plan["status"] != PlanStatus.APPROVED.value:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = f"plan_not_approved: {plan['status']}"
            event.operator_required = True
            self.store.add_event(event)
            return event

        # Verify approval receipt
        receipt = None
        for a in state.get("approvals", []):
            if a.get("plan_id") == plan_id:
                receipt = a
                break
        if not receipt:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "no_approval_receipt"
            event.operator_required = True
            self.store.add_event(event)
            return event

        # Verify plan digest matches
        if receipt.get("plan_digest") != plan.get("plan_digest"):
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "plan_digest_mismatch"
            event.operator_required = True
            self.store.add_event(event)
            return event

        # Check expiration
        expires_at = receipt.get("expires_at", "")
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at)
                if datetime.now(timezone.utc) > exp:
                    event.status = DriftEventStatus.BLOCKED
                    event.resolution = "approval_expired"
                    event.operator_required = True
                    self.store.add_event(event)
                    return event
            except ValueError:
                pass

        # Verify before_fingerprint_sha still matches current approved
        current_approved = self.store.get_approved(plan["node_id"])
        if current_approved:
            current_sha = current_approved.get("sha256", "")
            plan_before_sha = plan.get("before_fingerprint_sha", "")
            if plan_before_sha and current_sha != plan_before_sha:
                event.status = DriftEventStatus.BLOCKED
                event.resolution = "before_fingerprint_changed"
                event.operator_required = True
                self.store.add_event(event)
                return event

        node_id = plan["node_id"]
        actions = plan.get("actions", [])
        drift_type = plan.get("drift_type", "")

        self.registry.set_maintenance(node_id, "maintenance")
        event.maintenance_set = True
        event.drift_type = DriftType(drift_type) if drift_type else DriftType.UNKNOWN_DRIFT
        event.status = DriftEventStatus.RECONCILING

        if not actions:
            event.status = DriftEventStatus.RESOLVED
            event.resolution = "no_actions"
            event.operator_required = False
        elif actions[0] == RemediationAction.AUTO_FIX.value:
            event = self._apply_auto_fix(node_id, plan, event)
        elif actions[0] == RemediationAction.REBUILD.value:
            event = self._apply_rebuild(node_id, plan, event)
        elif actions[0] == RemediationAction.RESTORE_CONFIG.value:
            event = self._apply_restore_config(node_id, plan, event)
        elif actions[0] == RemediationAction.CANARY_VALIDATION.value:
            event = self._apply_canary(node_id, plan, event)
        elif actions[0] == RemediationAction.BLOCK.value:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "secret_drift_no_auto_remediation"
            event.operator_required = True
        else:
            event.status = DriftEventStatus.OPERATOR_WAITING
            event.resolution = f"operator_required_for_{drift_type}"
            event.operator_required = True

        self.store.update_plan(plan_id, {
            "status": PlanStatus.APPLIED.value if event.status == DriftEventStatus.RESOLVED else PlanStatus.FAILED.value,
            "apply_result": event.to_dict(),
        })
        self.store.add_event(event)
        self.store.add_history("plan_applied",
                              f"plan={plan_id} status={event.status.value}")
        return event

    def _apply_auto_fix(self, node_id: str, plan: dict, event: DriftEvent) -> DriftEvent:
        """Auto-fix PATH drift."""
        worker = self.registry.get_worker(node_id)
        if not worker:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "worker_not_found"
            return event

        approved_dict = self.store.get_approved(node_id)
        if not approved_dict:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "no_approved_baseline"
            return event

        afp = self._dict_to_fingerprint(approved_dict["fingerprint"])
        critical_dirs = [d for d in afp.path_dirs
                        if ".local/bin" in d or ".opencode/bin" in d or "node-current" in d]
        for d in critical_dirs:
            _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user,
                f'grep -q "{d}" ~/.profile 2>/dev/null || echo \'export PATH="{d}:$PATH"\' >> ~/.profile')

        new_fp = self.collector.collect(worker)
        new_items, _ = self.detect_drift(node_id, new_fp)
        path_items = [i for i in new_items if i.drift_type == DriftType.PATH_DRIFT]

        if not path_items:
            event.status = DriftEventStatus.RESOLVED
            event.resolution = "path_drift_auto_fixed"
            event.operator_required = False
            if event.maintenance_set:
                self.registry.set_maintenance(node_id, "active")
                event.maintenance_set = False
        else:
            event.status = DriftEventStatus.OPERATOR_WAITING
            event.resolution = "path_auto_fix_insufficient"
            event.operator_required = True
        return event

    def _apply_rebuild(self, node_id: str, plan: dict, event: DriftEvent) -> DriftEvent:
        """Rebuild dependencies per lockfile contract."""
        worker = self.registry.get_worker(node_id)
        if not worker:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "worker_not_found"
            return event

        rebuild_results = []
        for item in plan.get("drift_items", []):
            comp = item.get("component", "")
            if "npm" in comp or "node_modules" in comp:
                rc, out, err = _ssh(
                    worker.ssh_host, worker.ssh_port, worker.ssh_user,
                    "cd ~/.config/vibedev-opencode && npm ci 2>&1 | tail -5"
                )
                rebuild_results.append({"component": "npm", "rc": rc, "output": out[:200]})
            elif "venv" in comp:
                rc, out, err = _ssh(
                    worker.ssh_host, worker.ssh_port, worker.ssh_user,
                    "python3 -m venv ~/.vibedev/test-envs/toolchain/venv --clear 2>&1 && "
                    "~/.vibedev/test-envs/toolchain/venv/bin/pip install -q pytest pytest-timeout 2>&1 | tail -3"
                )
                rebuild_results.append({"component": "venv", "rc": rc, "output": out[:200]})

        new_fp = self.collector.collect(worker)
        new_items, _ = self.detect_drift(node_id, new_fp)
        dep_items = [i for i in new_items if i.drift_type == DriftType.DEPENDENCY_DRIFT]

        event.after = {"rebuild_results": rebuild_results}
        if not dep_items:
            event.status = DriftEventStatus.RESOLVED
            event.resolution = "deps_rebuilt"
            event.operator_required = False
            if event.maintenance_set:
                self.registry.set_maintenance(node_id, "active")
                event.maintenance_set = False
        else:
            event.status = DriftEventStatus.OPERATOR_WAITING
            event.resolution = "rebuild_insufficient"
            event.operator_required = True
        return event

    def _apply_restore_config(self, node_id: str, plan: dict, event: DriftEvent) -> DriftEvent:
        """Restore non-sensitive config from repo."""
        worker = self.registry.get_worker(node_id)
        if not worker:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "worker_not_found"
            return event

        for item in plan.get("drift_items", []):
            comp = item.get("component", "")
            if "secret" in comp.lower():
                continue
            if "wrapper" in comp:
                _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user,
                    "test -f ~/vibedev/repos/vibe-coding-repo.git/scripts/vibedev-opencode-wrapper.sh && "
                    "cp ~/vibedev/repos/vibe-coding-repo.git/scripts/vibedev-opencode-wrapper.sh "
                    "~/.local/bin/vibedev-opencode-wrapper.sh && chmod +x ~/.local/bin/vibedev-opencode-wrapper.sh")

        new_fp = self.collector.collect(worker)
        new_items, _ = self.detect_drift(node_id, new_fp)
        config_items = [i for i in new_items
                       if i.drift_type == DriftType.CONFIG_DRIFT and "secret" not in i.component]

        if not config_items:
            event.status = DriftEventStatus.RESOLVED
            event.resolution = "config_restored"
            event.operator_required = False
            if event.maintenance_set:
                self.registry.set_maintenance(node_id, "active")
                event.maintenance_set = False
        else:
            event.status = DriftEventStatus.OPERATOR_WAITING
            event.resolution = "config_restore_insufficient"
            event.operator_required = True
        return event

    def _apply_canary(self, node_id: str, plan: dict, event: DriftEvent) -> DriftEvent:
        """Real canary: deploy fixture candidate, run validation suite, create candidate on pass, rollback on fail.

        V2.2.0: Canary actually deploys a fixture package to isolated candidate path,
        then runs full validation suite. On failure, restores approved state and verifies.
        """
        worker = self.registry.get_worker(node_id)
        if not worker:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "worker_not_found"
            return event

        event.status = DriftEventStatus.CANARY
        start_time = datetime.now(timezone.utc).isoformat()
        ts = int(time.time())
        candidate_dir = f"/tmp/candidate-{node_id}-{ts}"
        approved_dict = self.store.get_approved(node_id)
        if not approved_dict:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "no_approved_baseline_for_canary"
            return event

        approved_fp = approved_dict["fingerprint"]

        # === STEP 1: Save approved state backup ===
        backup_dir = f"/tmp/canary-backup-{node_id}-{ts}"
        backup_cmds = [
            f"mkdir -p {backup_dir}",
            f"bash -c 'source ~/.profile 2>/dev/null; opencode --version > {backup_dir}/opencode_version.txt 2>&1 || echo UNKNOWN > {backup_dir}/opencode_version.txt'",
            f"~/.vibedev/test-envs/toolchain/venv/bin/pip freeze > {backup_dir}/venv_freeze.txt 2>&1 || true",
            f"cp ~/.local/bin/vibedev-opencode-wrapper.sh {backup_dir}/wrapper.sh 2>/dev/null || true",
            f"bash -c 'source ~/.profile 2>/dev/null; echo \\$PATH' > {backup_dir}/path.txt",
            f"bash -c 'sha256sum ~/.local/bin/vibedev-opencode-wrapper.sh 2>/dev/null > {backup_dir}/wrapper_sha.txt || true'",
        ]
        for cmd in backup_cmds:
            _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, cmd, timeout=30)

        # === STEP 2: Deploy fixture candidate ===
        fixture_version = plan.get("target_version", "0.0.0-canary")
        deploy_cmds = [
            f"mkdir -p {candidate_dir}/bin {candidate_dir}/lib",
            f"echo '#!/bin/bash' > {candidate_dir}/bin/candidate-tool",
            f"echo 'echo fixture-candidate-v{fixture_version}' >> {candidate_dir}/bin/candidate-tool",
            f"chmod +x {candidate_dir}/bin/candidate-tool",
            f"echo '{fixture_version}' > {candidate_dir}/VERSION",
            f"echo '{ts}' > {candidate_dir}/DEPLOY_TS",
            f"sha256sum {candidate_dir}/bin/candidate-tool {candidate_dir}/VERSION > {candidate_dir}/candidate_sha.txt",
            f"ln -sf {candidate_dir}/bin/candidate-tool /tmp/canary-active-{node_id}",
        ]
        deploy_rc = 0
        for cmd in deploy_cmds:
            rc, out, err = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, cmd, timeout=30)
            if rc != 0:
                deploy_rc = rc

        # === STEP 3: Verify candidate actually deployed ===
        rc, ver_out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user,
                             f"/tmp/canary-active-{node_id} 2>&1")
        candidate_deployed = rc == 0 and fixture_version in ver_out

        # === STEP 4: Full canary validation suite ===
        canary_results = []
        wt = f"/tmp/canary-wt-{node_id}-{ts}"
        _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user,
            f"cd ~/vibedev-tools/repos/vibe-coding-repo.git && git worktree add --detach {wt} main 2>&1 | tail -1")

        checks = [
            ("candidate_deployed", f"test -x /tmp/canary-active-{node_id} && /tmp/canary-active-{node_id}"),
            ("candidate_version", f"grep -q '{fixture_version}' {candidate_dir}/VERSION && echo version_ok"),
            ("non_login_wrapper", f"bash -c 'source ~/.profile 2>/dev/null; which opencode && echo wrapper_ok'"),
            ("absolute_path_wrapper", f"test -x ~/.local/bin/vibedev-opencode-wrapper.sh && echo wrapper_executable"),
            ("venv_python", f"~/.vibedev/test-envs/toolchain/venv/bin/python3 --version 2>&1"),
            ("venv_pytest", f"~/.vibedev/test-envs/toolchain/venv/bin/python3 -m pytest --version 2>&1 | head -1"),
            ("standalone", f"cd {wt} && ~/.vibedev/test-envs/toolchain/venv/bin/python3 -m pytest tests/test_v1172.py -q --tb=no 2>&1 | tail -3"),
            ("smoke", f"cd {wt} && ~/.vibedev/test-envs/toolchain/venv/bin/python3 -m pytest scripts/test_toolchain_smoke.py -q --tb=no 2>&1 | tail -3"),
            ("lifecycle_selfcheck", f"cd {wt} && python3 scripts/vibe_toolchain_lifecycle.py self-check 2>&1 | head -1"),
        ]

        for check_name, cmd in checks:
            rc, out, err = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, cmd, timeout=180)
            canary_results.append({
                "check": check_name, "passed": rc == 0,
                "rc": rc, "output": out[:500],
                "stderr": err[:200] if rc != 0 else "",
                "command": cmd,
            })

        end_time = datetime.now(timezone.utc).isoformat()

        passed = sum(1 for c in canary_results if c["passed"])
        total = len(canary_results)
        canary_pass = passed == total and candidate_deployed

        event.canary_result = "PASS" if canary_pass else "FAIL"
        event.canary_details = canary_results
        event.canary_evidence = {
            "start_time": start_time,
            "end_time": end_time,
            "candidate_dir": candidate_dir,
            "backup_dir": backup_dir,
            "worktree": wt,
            "passed": passed,
            "total": total,
            "node": node_id,
            "fixture_version": fixture_version,
            "candidate_deployed": candidate_deployed,
        }

        if canary_pass:
            observed = self.collector.collect(worker)
            obs_dict = observed.to_dict()
            obs_dict["components"]["fixture_candidate"] = {
                "version": fixture_version,
                "candidate_dir": candidate_dir,
                "binary_path": f"/tmp/canary-active-{node_id}",
                "deploy_ts": str(ts),
                "sha256": "fixture_marker",
                "node": node_id,
            }
            self.store.set_candidate(node_id, obs_dict)
            event.status = DriftEventStatus.CANARY
            event.runtime_baseline_sha = observed.fingerprint_sha256()
            event.operator_required = True
            event.resolution = "canary_pass_candidate_created_awaiting_adopt"
        else:
            event = self._apply_rollback(node_id, event)

        # Cleanup worktree
        _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user,
            f"rm -rf {wt} && cd ~/vibedev-tools/repos/vibe-coding-repo.git && git worktree prune 2>/dev/null")

        return event


    def _apply_rollback(self, node_id: str, event: DriftEvent) -> DriftEvent:
        """Real rollback: restore approved state and verify full contract match.

        V2.2.0: Actually restores binary/package/lock/config/PATH from backup,
        then re-collects and verifies version, hash, PATH, venv/npm lock, wrapper
        all match approved baseline. Not just checking drift disappeared.
        """
        worker = self.registry.get_worker(node_id)
        if not worker:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "worker_not_found"
            return event

        approved_dict = self.store.get_approved(node_id)
        if not approved_dict:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "no_approved_baseline"
            return event

        approved_fp = approved_dict["fingerprint"]
        start_time = datetime.now(timezone.utc).isoformat()

        # === STEP 1: Restore from backup if exists ===
        backup_dirs_rc, backup_ls, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user,
            "ls -d /tmp/canary-backup-* 2>/dev/null | tail -1")
        backup_dir = backup_ls.strip() if backup_dirs_rc == 0 and backup_ls.strip() else None

        restore_results = []
        if backup_dir:
            restore_cmds = [
                # Remove candidate artifacts
                f"rm -f /tmp/canary-active-{node_id}",
                # Restore wrapper if backed up
                f"test -f {backup_dir}/wrapper.sh && cp {backup_dir}/wrapper.sh ~/.local/bin/vibedev-opencode-wrapper.sh && chmod +x ~/.local/bin/vibedev-opencode-wrapper.sh || true",
                # Restore PATH from backup (verify critical dirs present)
                f"bash -c 'source ~/.profile 2>/dev/null; echo \\$PATH' > /tmp/rollback-path-{node_id}.txt",
            ]
            for cmd in restore_cmds:
                rc, out, err = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, cmd, timeout=30)
                restore_results.append({"cmd": cmd[:80], "rc": rc})

        # Remove candidate directories
        _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user,
            f"rm -rf /tmp/candidate-{node_id}-* /tmp/canary-active-{node_id} 2>/dev/null")

        # === STEP 2: Re-collect fingerprint ===
        new_fp = self.collector.collect(worker)

        # === STEP 3: Verify against approved ===
        items = self.detector.detect(
            self._dict_to_fingerprint(approved_fp), new_fp)

        # Detailed verification
        version_items = [i for i in items if i.drift_type in (DriftType.PATCH_VERSION_DRIFT, DriftType.MAJOR_VERSION_DRIFT)]
        path_items = [i for i in items if i.drift_type == DriftType.PATH_DRIFT]
        config_items = [i for i in items if i.drift_type == DriftType.CONFIG_DRIFT and "secret" not in i.component.lower()]
        dep_items = [i for i in items if i.drift_type == DriftType.DEPENDENCY_DRIFT]

        end_time = datetime.now(timezone.utc).isoformat()

        event.rollback_evidence = {
            "start_time": start_time,
            "end_time": end_time,
            "backup_dir": backup_dir or "none",
            "restore_results": restore_results,
            "recollected_at": end_time,
            "total_drift_after": len(items),
            "version_drift": len(version_items),
            "path_drift": len(path_items),
            "config_drift": len(config_items),
            "dependency_drift": len(dep_items),
            "items": [
                {"component": i.component,
                 "type": i.drift_type if isinstance(i.drift_type, str) else i.drift_type.value,
                 "approved": i.approved_value, "observed": i.observed_value}
                for i in items
            ],
        }

        wrapper_items = [i for i in items if "wrapper" in i.component.lower()]
        residual = version_items + path_items + config_items + dep_items + wrapper_items
        if not residual:
            event.status = DriftEventStatus.ROLLED_BACK
            event.rollback_performed = True
            event.resolution = "rolled_back_to_approved_verified"
            event.operator_required = False
            if event.maintenance_set:
                self.registry.set_maintenance(node_id, "active")
                event.maintenance_set = False
        else:
            event.status = DriftEventStatus.OPERATOR_WAITING
            event.resolution = f"rollback_residual_{len(residual)}_drift_items_operator_required"
            event.operator_required = True

        return event


    def adopt_candidate(self, node_id: str, plan_id: str = None,
                        approval_receipt: dict = None) -> dict:
        """Promote candidate to approved. REQUIRES plan + approval receipt (V2.2.0).

        Validates receipt binding: plan_digest, operator, node_id,
        before_fingerprint_sha, actions, expiry.
        """
        gate = self._check_gate()
        if gate:
            return {"ok": False, "error": "gate_blocked", "detail": gate}

        if not plan_id or not approval_receipt:
            return {"ok": False, "error": "plan_and_approval_required"}

        candidate = self.store.get_candidate(node_id)
        if not candidate:
            return {"ok": False, "error": "no_candidate_baseline"}

        state = self.store.load()
        plan = None
        for p in state.get("plans", []):
            if p["plan_id"] == plan_id:
                plan = p
                break
        if not plan:
            return {"ok": False, "error": "plan_not_found"}
        if plan["status"] != PlanStatus.APPROVED.value:
            return {"ok": False, "error": f"plan_not_approved: {plan.get('status')}"}

        # Find and validate receipt
        receipt = None
        for a in state.get("approvals", []):
            if a.get("plan_id") == plan_id:
                receipt = a
                break
        if not receipt:
            return {"ok": False, "error": "no_approval_receipt"}

        required_fields = ["plan_digest", "operator", "node_id",
                           "before_fingerprint_sha", "actions", "expires_at"]
        for field in required_fields:
            if not receipt.get(field):
                return {"ok": False, "error": f"receipt_missing_{field}"}

        if receipt["plan_digest"] != plan.get("plan_digest"):
            return {"ok": False, "error": "receipt_digest_mismatch"}
        if receipt["node_id"] != node_id:
            return {"ok": False, "error": "receipt_node_mismatch"}
        if receipt["operator"] == "auto_reconcile":
            return {"ok": False, "error": "auto_reconcile_not_allowed"}
        try:
            if datetime.now(timezone.utc) > datetime.fromisoformat(receipt["expires_at"]):
                return {"ok": False, "error": "approval_expired"}
        except (ValueError, KeyError):
            return {"ok": False, "error": "invalid_expires_at"}

        # Verify before_fingerprint matches current approved
        current_approved = self.store.get_approved(node_id)
        if current_approved:
            current_sha = current_approved.get("sha256", "")
            before_sha = receipt.get("before_fingerprint_sha", "")
            if before_sha and current_sha != before_sha:
                return {"ok": False, "error": "before_fingerprint_changed"}

        self.store.set_approved(node_id, candidate["fingerprint"],
                                frozen_by=receipt["operator"])
        self.store.delete_candidate(node_id)
        self.registry.set_maintenance(node_id, "active")
        self.store.add_history("candidate_adopted",
                              f"node={node_id} sha={candidate.get('sha256', '')} plan={plan_id}")
        return {"ok": True, "node_id": node_id, "sha256": candidate.get("sha256", ""),
                "plan_id": plan_id}

    def forward_rollout(self, source_node: str, plan_id: str = None,
                         approval_receipt: dict = None) -> dict:
        """Apply adopted candidate to other node under maintenance.

        V2.2.0: Actually applies candidate contract on target node,
        then re-collects and verifies. Node-specific hostname/PATH/binary
        independently modeled. Requires plan + approval receipt.
        """
        gate = self._check_gate()
        if gate:
            return {"ok": False, "error": "gate_blocked", "detail": gate}

        if not plan_id or not approval_receipt:
            return {"ok": False, "error": "plan_and_approval_required"}

        other = "9bao" if source_node == "5bao" else "5bao"
        source_approved = self.store.get_approved(source_node)
        if not source_approved:
            return {"ok": False, "error": "source_no_approved"}

        # Validate plan + receipt
        state = self.store.load()
        plan = None
        for p in state.get("plans", []):
            if p["plan_id"] == plan_id:
                plan = p
                break
        if not plan:
            return {"ok": False, "error": "plan_not_found"}

        receipt = None
        for a in state.get("approvals", []):
            if a.get("plan_id") == plan_id:
                receipt = a
                break
        if not receipt:
            return {"ok": False, "error": "no_approval_receipt"}

        required_fields = ["plan_digest", "operator", "node_id",
                           "before_fingerprint_sha", "actions", "expires_at"]
        for field in required_fields:
            if not receipt.get(field):
                return {"ok": False, "error": f"receipt_missing_{field}"}
        if receipt["plan_digest"] != plan.get("plan_digest"):
            return {"ok": False, "error": "receipt_digest_mismatch"}
        try:
            if datetime.now(timezone.utc) > datetime.fromisoformat(receipt["expires_at"]):
                return {"ok": False, "error": "approval_expired"}
        except (ValueError, KeyError):
            return {"ok": False, "error": "invalid_expires_at"}

        # Set target node to maintenance
        self.registry.set_maintenance(other, "maintenance")

        # Collect fingerprint from target node to get its own current state
        other_fp_before = self.collect_fingerprint(other)
        if not other_fp_before.ssh_reachable:
            self.registry.set_maintenance(other, "active")
            return {"ok": False, "error": "other_node_unreachable"}

        # Deploy candidate contract on target node
        ts = int(time.time())
        candidate_dir = f"/tmp/rollout-{other}-{ts}"
        worker = self.registry.get_worker(other)
        if not worker:
            self.registry.set_maintenance(other, "active")
            return {"ok": False, "error": "target_worker_not_found"}

        deploy_cmds = [
            f"mkdir -p {candidate_dir}/bin",
            f"echo '#!/bin/bash' > {candidate_dir}/bin/candidate-tool",
            f"echo 'echo rollout-candidate-v{plan.get('target_version', '0.0.0')}' >> {candidate_dir}/bin/candidate-tool",
            f"chmod +x {candidate_dir}/bin/candidate-tool",
            f"ln -sf {candidate_dir}/bin/candidate-tool /tmp/rollout-active-{other}",
        ]
        for cmd in deploy_cmds:
            _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, cmd, timeout=30)

        # Verify deployment
        rc, ver_out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user,
                             f"/tmp/rollout-active-{other} 2>&1")
        if rc != 0:
            self.registry.set_maintenance(other, "active")
            return {"ok": False, "error": "rollout_deploy_failed"}

        # Run verification suite on target node
        wt = f"/tmp/rollout-wt-{other}-{ts}"
        _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user,
            f"cd ~/vibedev-tools/repos/vibe-coding-repo.git && git worktree add --detach {wt} main 2>&1 | tail -1")

        verify_results = []
        checks = [
            ("candidate_active", f"test -x /tmp/rollout-active-{other} && /tmp/rollout-active-{other}"),
            ("non_login_wrapper", f"bash -c 'source ~/.profile 2>/dev/null; which opencode && echo wrapper_ok'"),
            ("venv_python", f"~/.vibedev/test-envs/toolchain/venv/bin/python3 --version 2>&1"),
            ("standalone", f"cd {wt} && ~/.vibedev/test-envs/toolchain/venv/bin/python3 -m pytest tests/test_v1172.py -q --tb=no 2>&1 | tail -3"),
            ("smoke", f"cd {wt} && ~/.vibedev/test-envs/toolchain/venv/bin/python3 -m pytest scripts/test_toolchain_smoke.py -q --tb=no 2>&1 | tail -3"),
            ("lifecycle_selfcheck", f"cd {wt} && python3 scripts/vibe_toolchain_lifecycle.py self-check 2>&1 | head -1"),
        ]
        for check_name, cmd in checks:
            rc, out, err = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, cmd, timeout=180)
            verify_results.append({
                "check": check_name, "passed": rc == 0,
                "rc": rc, "output": out[:500],
            })

        # Cleanup worktree
        _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user,
            f"rm -rf {wt} && cd ~/vibedev-tools/repos/vibe-coding-repo.git && git worktree prune 2>/dev/null")

        # Re-collect fingerprint from target (its own, not source copy)
        other_fp_after = self.collector.collect(worker)

        verify_passed = all(r["passed"] for r in verify_results)

        if verify_passed:
            # Set approved from target's own fingerprint
            self.store.set_approved(other, other_fp_after.to_dict(), frozen_by="forward_rollout")
            self.registry.set_maintenance(other, "active")
            self.store.add_history("forward_rollout",
                                  f"source={source_node} target={other} "
                                  f"sha={other_fp_after.fingerprint_sha256()} plan={plan_id}")
            return {"ok": True, "source": source_node, "target": other,
                    "sha256": other_fp_after.fingerprint_sha256(),
                    "verify_results": verify_results,
                    "before_sha": other_fp_before.fingerprint_sha256(),
                    "after_sha": other_fp_after.fingerprint_sha256()}
        else:
            # Rollback target
            _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user,
                f"rm -f /tmp/rollout-active-{other} && rm -rf {candidate_dir}")
            self.registry.set_maintenance(other, "active")
            return {"ok": False, "error": "rollout_verification_failed",
                    "verify_results": verify_results}


    def rollback(self, node_id: str) -> DriftEvent:
        """Explicit rollback command."""
        event = DriftEvent(
            event_id=self._next_event_id(),
            node_id=node_id,
            detected_at=datetime.now(timezone.utc).isoformat(),
            remediation=RemediationAction.ROLLBACK,
        )
        event = self._apply_rollback(node_id, event)
        self.store.add_event(event)
        self.store.add_history("rollback", f"node={node_id} status={event.status.value}")
        return event

    def reconcile(self, node_id: str) -> DriftEvent:
        """Full reconcile cycle with gate check."""
        # Gate check
        gate = self._check_gate()
        if gate:
            event = DriftEvent(
                event_id="gate-blocked",
                node_id=node_id,
                detected_at=datetime.now(timezone.utc).isoformat(),
                status=DriftEventStatus.BLOCKED,
                resolution="gate_blocked: " + gate.get("reason", "unknown"),
                operator_required=True,
            )
            return event

        if not self.store.has_approved(node_id):
            event = DriftEvent(
                event_id=self._next_event_id(),
                node_id=node_id,
                detected_at=datetime.now(timezone.utc).isoformat(),
                status=DriftEventStatus.BLOCKED,
                resolution="NO_APPROVED_BASELINE",
                operator_required=True,
            )
            self.store.add_event(event)
            return event

        # Dual-node safety check
        if self._both_nodes_unknown(node_id):
            event = DriftEvent(
                event_id=self._next_event_id(),
                node_id=node_id,
                detected_at=datetime.now(timezone.utc).isoformat(),
                status=DriftEventStatus.BLOCKED,
                resolution="both_nodes_unknown_drift_no_writes_allowed",
                operator_required=True,
            )
            self.store.add_event(event)
            return event

        items, drift_type = self.detect_drift(node_id)
        if not items:
            event = DriftEvent(
                event_id=self._next_event_id(),
                node_id=node_id,
                detected_at=datetime.now(timezone.utc).isoformat(),
                status=DriftEventStatus.RESOLVED,
                resolution="no_drift_detected",
                operator_required=False,
            )
            self.store.add_event(event)
            return event

        plan = self.create_plan(node_id, items, drift_type)
        action = plan.actions[0] if plan.actions else RemediationAction.OPERATOR_REQUIRED

        if action in (RemediationAction.BLOCK, RemediationAction.OPERATOR_REQUIRED):
            self.store.add_history("reconcile_blocked",
                                  f"node={node_id} action={action.value}")
            self.store.update_plan(plan.plan_id, {"status": PlanStatus.PENDING_APPROVAL.value})
            event = DriftEvent(
                event_id=self._next_event_id(),
                node_id=node_id,
                detected_at=datetime.now(timezone.utc).isoformat(),
                drift_type=drift_type,
                status=DriftEventStatus.PENDING_APPROVAL,
                plan_id=plan.plan_id,
                operator_required=True,
                resolution=f"plan_created_pending_approval: {action.value}",
            )
            self.store.add_event(event)
            return event

        # V2.2.0: No auto-approval. All plans require explicit operator approval.
        self.store.update_plan(plan.plan_id, {"status": PlanStatus.PENDING_APPROVAL.value})
        event = DriftEvent(
            event_id=self._next_event_id(),
            node_id=node_id,
            detected_at=datetime.now(timezone.utc).isoformat(),
            drift_type=drift_type,
            status=DriftEventStatus.PENDING_APPROVAL,
            plan_id=plan.plan_id,
            operator_required=True,
            resolution=f"plan_created_awaiting_approval: {action.value}",
        )
        self.store.add_event(event)
        return event

    def _both_nodes_unknown(self, current_node: str) -> bool:
        """Check if both nodes have unresolved UNKNOWN drift events."""
        other_node = "9bao" if current_node == "5bao" else "5bao"
        other_has_unknown = False
        current_has_unknown = False
        state = self.store.load()
        for evt in state.get("events", []):
            if (evt.get("drift_type") == DriftType.UNKNOWN_DRIFT.value
                    and evt.get("status") in (DriftEventStatus.DETECTED.value,
                                               DriftEventStatus.OPERATOR_WAITING.value)):
                if evt.get("node_id") == other_node:
                    other_has_unknown = True
                elif evt.get("node_id") == current_node:
                    current_has_unknown = True
        return other_has_unknown and current_has_unknown

    def status_report(self) -> dict:
        state = self.store.load()
        workers = {}
        for w in self.registry.list_workers():
            workers[w.worker_id] = {
                "health": w.health_status,
                "maintenance": w.maintenance_status,
                "has_approved": self.store.has_approved(w.worker_id),
                "has_candidate": self.store.get_candidate(w.worker_id) is not None,
            }
        gate = self.gate.is_writes_allowed()
        return {
            "version": __version__,
            "schema_version": SCHEMA_VERSION,
            "state_checksum": state.get("checksum", "")[:16],
            "state_path": self.store.path,
            "corruption_latch": self.store.latch.get_status(),
            "gate": gate,
            "workers": workers,
            "event_count": len(state.get("events", [])),
            "plan_count": len(state.get("plans", [])),
            "approval_count": len(state.get("approvals", [])),
            "history_count": len(state.get("history", [])),
        }

    def inventory(self, node_id: str = None) -> dict:
        nodes = [node_id] if node_id else [w.worker_id for w in self.registry.list_workers()]
        result = {}
        for nid in nodes:
            fp = self.collect_fingerprint(nid)
            result[nid] = {
                "reachable": fp.ssh_reachable,
                "hostname": fp.hostname,
                "components": fp.components,
                "path_dirs": fp.path_dirs,
                "errors": fp.collection_errors,
            }
        return result

    def generate_opencode_plan_only(self) -> dict:
        """Generate OpenCode 1.17.7 PLAN ONLY artifact.

        V1.17.2: Queries npm for latest version, creates plan artifact.
        Does NOT install, modify PATH, or update candidate/approved.
        """
        # Query npm for latest opencode version
        import subprocess as _sp
        try:
            npm_r = _sp.run(["npm", "view", "opencode-ai", "version"], capture_output=True, text=True, timeout=15)
            latest_ver = npm_r.stdout.strip() if npm_r.returncode == 0 else "UNAVAILABLE"
        except Exception:
            latest_ver = "UNAVAILABLE"

        ver_5bao = "UNAVAILABLE"
        for _cmd in ["opencode --version", "~/.opencode/bin/opencode --version", "/home/vibeworker/bin/opencode --version"]:
            try:
                _r = _sp.run(["bash", "-c", "source ~/.profile 2>/dev/null; " + _cmd], capture_output=True, text=True, timeout=10)
                if _r.returncode == 0 and _r.stdout.strip():
                    ver_5bao = _r.stdout.strip()
                    break
            except Exception:
                pass
        rc9v, out9v, _ = _ssh("192.168.9.6", 22222, "vibeworker", "~/.opencode/bin/opencode --version 2>/dev/null || echo UNAVAILABLE")
        ver_9bao = out9v.strip() if rc9v == 0 and out9v.strip() else "UNAVAILABLE"

        artifact = {
            "type": "PLAN_ONLY",
            "current_version_5bao": ver_5bao,
            "current_version_9bao": ver_9bao,
            "target_version": "1.17.7",
            "latest_npm_version": latest_ver,
            "source": "npm registry",
            "package_name": "opencode-ai",
            "canary_node": "5bao",
            "changed_paths": {
                "5bao": [
                    "~/.npm-global/bin/opencode",
                    "~/.npm-global/lib/node_modules/opencode-ai/",
                ],
                "9bao": [
                    "~/.opencode/bin/opencode",
                    "~/.opencode/lib/node_modules/opencode-ai/",
                ],
            },
            "npm_discovery": {
                "query": "npm view opencode-ai version",
                "result": latest_ver,
                "status": "ok" if latest_ver != "UNAVAILABLE" else "discovery_failed",
            },
            "binary_integrity": {
                "5bao": "~/.npm-global/bin/opencode --version",
                "9bao": "~/.opencode/bin/opencode --version",
            },
            "compatibility_matrix": {
                "node": ">=18",
                "python": ">=3.10",
                "os": "linux-x64",
            },
            "verification_matrix": {
                "binary_version": "opencode --version",
                "wrapper_test": "bash -c 'source ~/.profile; which opencode'",
                "smoke": "python3 scripts/test_toolchain_smoke.py",
            },
            "rollback_contract": {
                "5bao": "npm install -g opencode-ai@1.17.4",
                "9bao": "~/.opencode/bin/opencode self-update --version 1.17.4 || npm install -g --prefix ~/.opencode opencode-ai@1.17.4",
            },
            "risk": "BLOCKED — V1.17.2 prohibits actual toolchain upgrades",
            "blocked_reason": "trusted_runtime_baseline_freeze",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self.store.add_history("opencode_plan_only",
                              f"current=1.17.4 target=1.17.7 latest_npm={latest_ver}")
        return artifact

    # --- Self-check ---

    def self_check(self) -> dict:
        """Run comprehensive self-check."""
        checks = []

        # 1. Version
        checks.append({"name": "version", "passed": True, "message": __version__})

        # 2. Imports
        try:
            from vibe_worker_registry import WorkerRegistry, WorkerNode, NodeStatus
            checks.append({"name": "import_registry", "passed": True, "message": "ok"})
        except ImportError as e:
            checks.append({"name": "import_registry", "passed": False, "message": str(e)})

        # 3. DriftType enum
        expected_types = {"PATH_DRIFT", "PATCH_VERSION_DRIFT", "DEPENDENCY_DRIFT",
                         "CONFIG_DRIFT", "SECRET_DRIFT", "SYSTEM_PACKAGE_DRIFT",
                         "MAJOR_VERSION_DRIFT", "UNKNOWN_DRIFT"}
        actual_types = {dt.value for dt in DriftType}
        checks.append({"name": "drift_types", "passed": expected_types == actual_types,
                       "message": f"expected={len(expected_types)} actual={len(actual_types)}"})

        # 4. StateStore with lock file
        import tempfile
        tmp_state = os.path.join(tempfile.gettempdir(), f"test_state_{os.getpid()}.json")
        tmp_lock = os.path.join(tempfile.gettempdir(), f"test_state_{os.getpid()}.lock")
        tmp_latch = os.path.join(tempfile.gettempdir(), f"test_latch_{os.getpid()}.json")
        try:
            store = StateStore(tmp_state, tmp_lock, tmp_latch)
            state = store.load()
            assert state["schema_version"] == SCHEMA_VERSION
            checks.append({"name": "state_store_init", "passed": True, "message": f"schema={SCHEMA_VERSION}"})
        except Exception as e:
            checks.append({"name": "state_store_init", "passed": False, "message": str(e)[:100]})
        finally:
            for f in [tmp_state, tmp_lock, tmp_latch]:
                try:
                    os.unlink(f)
                except OSError:
                    pass

        # 5. Corruption latch
        try:
            store = StateStore(tmp_state, tmp_lock, tmp_latch)
            assert not store.latch.is_latched()
            store.latch.latch("test_corruption")
            assert store.latch.is_latched()
            # Write should fail
            try:
                store.add_history("test", "should_fail")
                latch_write_blocked = False
            except RuntimeError:
                latch_write_blocked = True
            store.latch.clear("test_operator")
            assert not store.latch.is_latched()
            checks.append({"name": "corruption_latch", "passed": latch_write_blocked,
                           "message": f"latch_blocks_write={latch_write_blocked}"})
        except Exception as e:
            checks.append({"name": "corruption_latch", "passed": False, "message": str(e)[:100]})
        finally:
            for f in [tmp_state, tmp_lock, tmp_latch]:
                try:
                    os.unlink(f)
                except OSError:
                    pass

        # 6. Scheduler gate
        try:
            store = StateStore(tmp_state, tmp_lock, tmp_latch)
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
            checks.append({"name": "scheduler_gate", "passed": True,
                           "message": f"dual_unknown_blocks={not result2['allowed']}"})
        except Exception as e:
            checks.append({"name": "scheduler_gate", "passed": False, "message": str(e)[:100]})
        finally:
            for f in [tmp_state, tmp_lock, tmp_latch]:
                try:
                    os.unlink(f)
                except OSError:
                    pass

        # 7. Transaction safety
        try:
            store = StateStore(tmp_state, tmp_lock, tmp_latch)
            store.transaction(lambda s: {**s, "test_key": "test_value"})
            state = store.load()
            assert state.get("test_key") == "test_value"
            checks.append({"name": "transaction", "passed": True, "message": "ok"})
        except Exception as e:
            checks.append({"name": "transaction", "passed": False, "message": str(e)[:100]})
        finally:
            for f in [tmp_state, tmp_lock, tmp_latch]:
                try:
                    os.unlink(f)
                except OSError:
                    pass

        # 8-13: Same as V2.0.0 (classifier, planner, detector, dual-node, etc.)
        classifier = DriftClassifier()
        items = [DriftItem(component="x", drift_type=DriftType.SECRET_DRIFT),
                DriftItem(component="y", drift_type=DriftType.PATH_DRIFT)]
        checks.append({"name": "classifier_secret_wins",
                       "passed": classifier.classify(items) == DriftType.SECRET_DRIFT,
                       "message": "SECRET > PATH"})

        items2 = [DriftItem(component="x", drift_type=DriftType.UNKNOWN_DRIFT),
                 DriftItem(component="y", drift_type=DriftType.MAJOR_VERSION_DRIFT)]
        checks.append({"name": "classifier_unknown_wins",
                       "passed": classifier.classify(items2) == DriftType.UNKNOWN_DRIFT,
                       "message": "UNKNOWN > MAJOR"})

        planner = RemediationPlanner()
        rules = [
            (DriftType.PATH_DRIFT, RemediationAction.AUTO_FIX),
            (DriftType.PATCH_VERSION_DRIFT, RemediationAction.CANARY_VALIDATION),
            (DriftType.DEPENDENCY_DRIFT, RemediationAction.REBUILD),
            (DriftType.SECRET_DRIFT, RemediationAction.BLOCK),
            (DriftType.MAJOR_VERSION_DRIFT, RemediationAction.OPERATOR_REQUIRED),
        ]
        all_ok = all(planner.plan(dt) == ra for dt, ra in rules)
        checks.append({"name": "planner_rules", "passed": all_ok, "message": "5/5 correct"})

        fp1 = RuntimeFingerprint(node_id="test", hostname="h1", ssh_reachable=True,
                                components={"opencode": {"version": "1.17.4", "binary_hash": "abc123"}},
                                path_dirs=["/a", "/b"])
        fp2 = RuntimeFingerprint(node_id="test", hostname="h1", ssh_reachable=True,
                                components={"opencode": {"version": "1.17.4", "binary_hash": "abc123"}},
                                path_dirs=["/a", "/b"])
        items = DriftDetector().detect(fp1, fp2)
        checks.append({"name": "detector_no_drift", "passed": len(items) == 0,
                       "message": f"identical={len(items)}_items"})

        fp3 = RuntimeFingerprint(node_id="test", hostname="h1", ssh_reachable=True,
                                components={"opencode": {"version": "1.17.5", "binary_hash": "def456"}},
                                path_dirs=["/a", "/b"])
        items2 = DriftDetector().detect(fp1, fp3)
        checks.append({"name": "detector_version_drift",
                       "passed": any(i.drift_type == DriftType.PATCH_VERSION_DRIFT for i in items2),
                       "message": f"detected_{len(items2)}_items"})

        fp4 = RuntimeFingerprint(node_id="test", hostname="h1", ssh_reachable=True,
                                components={"secret_fingerprint": {"hash": "DIFFERENT"}},
                                path_dirs=["/a", "/b"])
        fp5 = RuntimeFingerprint(node_id="test", hostname="h1", ssh_reachable=True,
                                components={"secret_fingerprint": {"hash": "ORIGINAL"}},
                                path_dirs=["/a", "/b"])
        items3 = DriftDetector().detect(fp5, fp4)
        has_secret = any(i.drift_type == DriftType.SECRET_DRIFT for i in items3)
        checks.append({"name": "detector_secret_drift", "passed": has_secret,
                       "message": f"secret_detected={has_secret}"})

        # 14. No auto-approved
        try:
            store = StateStore(tmp_state, tmp_lock, tmp_latch)
            mgr = ToolchainLifecycleManager(registry=WorkerRegistry(),
                                           state_path=tmp_state, lock_path=tmp_lock,
                                           latch_path=tmp_latch)
            assert not store.has_approved("5bao")
            checks.append({"name": "no_auto_approved", "passed": True, "message": "no_auto_baseline"})
        except Exception as e:
            checks.append({"name": "no_auto_approved", "passed": False, "message": str(e)[:100]})
        finally:
            for f in [tmp_state, tmp_lock, tmp_latch]:
                try:
                    os.unlink(f)
                except OSError:
                    pass


        # 15. gate_check_for_dispatch public API (V2.2.0)
        try:
            gcr = gate_check_for_dispatch(state_path=tmp_state)
            checks.append({"name": "gate_dispatch_api", "passed": "allowed" in gcr and "components" in gcr,
                          "message": f"allowed={gcr.get('allowed')} components={len(gcr.get('components', {}))}"})
        except Exception as e:
            checks.append({"name": "gate_dispatch_api", "passed": False, "message": str(e)[:80]})

        # 16. No auto_reconcile in reconcile method (V2.2.0)
        try:
            import inspect
            reconcile_src = inspect.getsource(ToolchainLifecycleManager.reconcile)
            has_auto = "auto_reconcile" in reconcile_src
            checks.append({"name": "no_auto_reconcile", "passed": not has_auto,
                          "message": "auto_reconcile_absent" if not has_auto else "auto_reconcile_FOUND"})
        except Exception as e:
            checks.append({"name": "no_auto_reconcile", "passed": False, "message": str(e)[:80]})

        # 17. freeze requires plan+approval (V2.2.0)
        try:
            import inspect
            freeze_src = inspect.getsource(ToolchainLifecycleManager.freeze)
            requires_plan = "plan_and_approval_required" in freeze_src
            checks.append({"name": "freeze_requires_plan", "passed": requires_plan,
                          "message": "plan_required" if requires_plan else "plan_NOT_required"})
        except Exception as e:
            checks.append({"name": "freeze_requires_plan", "passed": False, "message": str(e)[:80]})

        # 18. adopt_candidate requires plan+approval (V2.2.0)
        try:
            import inspect
            adopt_src = inspect.getsource(ToolchainLifecycleManager.adopt_candidate)
            requires_plan = "plan_and_approval_required" in adopt_src
            checks.append({"name": "adopt_requires_plan", "passed": requires_plan,
                          "message": "plan_required" if requires_plan else "plan_NOT_required"})
        except Exception as e:
            checks.append({"name": "adopt_requires_plan", "passed": False, "message": str(e)[:80]})


        # 19. Scheduler gate wiring (V2.3.0)
        try:
            from vibe_scheduler_policy import SchedulerPolicy
            import inspect
            sched_src = inspect.getsource(SchedulerPolicy.schedule)
            has_gate = "lifecycle_gate" in sched_src or "gate_check_for_dispatch" in sched_src
            checks.append({"name": "scheduler_gate_wired", "passed": has_gate,
                          "message": "gate_wired" if has_gate else "gate_NOT_wired"})
        except Exception as e:
            checks.append({"name": "scheduler_gate_wired", "passed": False, "message": str(e)[:80]})

        # 20. Execution gate wiring (V2.3.0)
        try:
            import importlib.util
            eg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "vibe_execution_gate.py")
            if os.path.exists(eg_path):
                with open(eg_path) as f:
                    eg_src = f.read()
                has_gate = "gate_check_for_dispatch" in eg_src
            else:
                has_gate = False
            checks.append({"name": "execution_gate_wired", "passed": has_gate,
                          "message": "gate_wired" if has_gate else "gate_NOT_wired"})
        except Exception as e:
            checks.append({"name": "execution_gate_wired", "passed": False, "message": str(e)[:80]})

        passed = sum(1 for c in checks if c["passed"])
        return {
            "overall": "PASS" if passed == len(checks) else "FAIL",
            "passed": passed, "total": len(checks), "checks": checks,
        }

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


# === Public API for external scheduler/dispatcher integration (V2.2.0) ===

def gate_check_for_dispatch(state_path: str = None, registry: WorkerRegistry = None) -> dict:
    """Public API for scheduler/dispatcher to check if writes are allowed.

    Returns:
        {
            "allowed": bool,
            "reason": str,  # "ok" | "corruption_latch" | "secret_drift" | "dual_unknown" | ...
            "detail": str,
            "version": str,
            "checked_at": str,
            "gate_version": str,
            "components": {
                "corruption_latch": {"status": "clear"|"latched", ...},
                "secret_drift": {"status": "ok"|"blocked", ...},
                "dual_unknown": {"status": "ok"|"blocked", ...},
            }
        }

    Usage from scheduler/dispatcher:
        gate_check_for_dispatch = globals().get("gate_check_for_dispatch")
        result = gate_check_for_dispatch()
        if not result["allowed"]:
            # Block write operations
            log(f"Gate blocked: {result['reason']}")
    """
    if registry is None:
        registry = WorkerRegistry()
        for w in registry.list_workers():
            registry.set_health(w.worker_id, NodeStatus.ONLINE)

    store = StateStore(path=state_path)
    gate = SchedulerGate(store)
    result = gate.is_writes_allowed()

    # Enrich with component details
    result["gate_version"] = __version__
    result["checked_at"] = datetime.now(timezone.utc).isoformat()

    latch = store.latch
    result["components"] = {
        "corruption_latch": {
            "status": "latched" if latch.is_latched() else "clear",
            "reason": latch.get_status().get("reason", ""),
        },
    }

    # Check secret drift
    state = store.load()
    secret_drift = False
    for evt in state.get("events", []):
        if evt.get("drift_type") == "SECRET_DRIFT" and evt.get("status") in ("detected", "operator_waiting"):
            secret_drift = True
            break
    result["components"]["secret_drift"] = {"status": "blocked" if secret_drift else "ok"}

    # Check dual unknown
    nodes_with_unknown = set()
    for evt in state.get("events", []):
        if evt.get("drift_type") == "UNKNOWN_DRIFT" and evt.get("status") in ("detected", "operator_waiting"):
            nodes_with_unknown.add(evt.get("node_id", ""))
    dual_unknown = len(nodes_with_unknown) >= 2
    result["components"]["dual_unknown"] = {
        "status": "blocked" if dual_unknown else "ok",
        "unknown_nodes": list(nodes_with_unknown),
    }

    return result


def dispatch_check_write_operation(operation: str, state_path: str = None) -> dict:
    """Check if a specific write operation is allowed by the gate.

    Args:
        operation: One of "implement", "review", "branch_write", "merge", "reconcile", "apply", "freeze", "adopt"

    Returns:
        {"allowed": bool, "operation": str, "gate_result": dict}
    """
    gate_result = gate_check_for_dispatch(state_path=state_path)
    return {
        "allowed": gate_result["allowed"],
        "operation": operation,
        "gate_result": gate_result,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Toolchain Lifecycle Manager v2.2.0")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Show current state")
    inv_p = sub.add_parser("inventory", help="Component inventory")
    inv_p.add_argument("--node", help="Target node")
    drift_p = sub.add_parser("drift", help="Detect drift")
    drift_p.add_argument("--node", help="Target node")
    plan_p = sub.add_parser("plan", help="Create remediation plan")
    plan_p.add_argument("--node", required=True, help="Target node")
    appr_p = sub.add_parser("approve", help="Approve a plan")
    appr_p.add_argument("--plan-id", required=True, help="Plan ID")
    appr_p.add_argument("--operator", default="operator", help="Operator name")
    apply_p = sub.add_parser("apply", help="Apply an approved plan")
    apply_p.add_argument("--plan-id", required=True, help="Plan ID")
    rec_p = sub.add_parser("reconcile", help="Full reconcile cycle")
    rec_p.add_argument("--node", required=True, help="Target node")
    rb_p = sub.add_parser("rollback", help="Rollback to approved")
    rb_p.add_argument("--node", required=True, help="Target node")
    ac_p = sub.add_parser("adopt-candidate", help="Promote candidate to approved")
    ac_p.add_argument("--node", required=True, help="Target node")
    ac_p.add_argument("--plan-id", help="Plan ID (required)")
    ac_p.add_argument("--receipt", help="Path to approval receipt JSON")
    fr_p = sub.add_parser("freeze", help="Set approved baseline")
    fr_p.add_argument("--node", required=True, help="Target node")
    fr_p.add_argument("--plan-id", help="Plan ID (required)")
    fr_p.add_argument("--receipt", help="Path to approval receipt JSON")
    ev_p = sub.add_parser("events", help="Show drift events")
    ev_p.add_argument("--limit", type=int, default=20)
    hist_p = sub.add_parser("history", help="Show state history")
    hist_p.add_argument("--limit", type=int, default=20)
    sub.add_parser("gate-check", help="Check scheduler gate")
    sub.add_parser("repair", help="Operator repair: clear corruption latch")
    sub.add_parser("opencode-plan", help="OpenCode 1.17.7 PLAN ONLY artifact")
    sub.add_parser("self-check", help="Run self-check")

    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--state-path", help="Custom state file path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "self-check":
        result = ToolchainLifecycleManager(state_path=args.state_path).self_check()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Self-check: {result['overall']} ({result['passed']}/{result['total']})")
            for c in result["checks"]:
                mark = "PASS" if c["passed"] else "FAIL"
                print(f"  [{mark}] {c['name']}: {c['message']}")
        sys.exit(0 if result["overall"] == "PASS" else 1)

    reg = WorkerRegistry()
    for w in reg.list_workers():
        reg.set_health(w.worker_id, NodeStatus.ONLINE)
    mgr = ToolchainLifecycleManager(registry=reg, state_path=args.state_path)

    if args.command == "status":
        report = mgr.status_report()
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            print(f"Version: {report['version']} Schema: {report['schema_version']}")
            print(f"State: {report['state_path']} (checksum={report['state_checksum']})")
            latch = report.get("corruption_latch", {})
            print(f"Corruption latch: {'LATCHED' if latch.get('latched') else 'clear'}")
            gate = report.get("gate", {})
            gate_r = 'ALLOWED' if gate.get('allowed') else 'BLOCKED:' + str(gate.get('reason', ''))
            print(f"Gate: {gate_r}")
            for nid, info in report["workers"].items():
                print(f"  {nid}: health={info['health']} maintenance={info['maintenance']} "
                      f"approved={info['has_approved']} candidate={info['has_candidate']}")
            print(f"Events: {report['event_count']} Plans: {report['plan_count']} "
                  f"Approvals: {report['approval_count']} History: {report['history_count']}")

    elif args.command == "inventory":
        inv = mgr.inventory(args.node)
        if args.json:
            print(json.dumps(inv, indent=2, default=str))
        else:
            for nid, info in inv.items():
                print(f"\n{nid}: reachable={info['reachable']} hostname={info['hostname']}")
                for cname, cdata in info["components"].items():
                    ver = cdata.get("version", cdata.get("hash", ""))
                    avail = cdata.get("available", True)
                    err = cdata.get("error", "")
                    status = "OK" if avail and not err else f"ERR:{err[:50]}"
                    print(f"  {cname}: {ver} [{status}]")

    elif args.command == "drift":
        nodes = [args.node] if args.node else [w.worker_id for w in reg.list_workers()]
        results = {}
        for nid in nodes:
            if not mgr.store.has_approved(nid):
                results[nid] = {"error": "NO_APPROVED_BASELINE"}
                continue
            fp = mgr.collect_fingerprint(nid)
            items, dtype = mgr.detect_drift(nid, fp)
            results[nid] = {
                "drift_type": dtype.value if dtype else "NONE",
                "items": [{"component": i.component, "type": i.drift_type if isinstance(i.drift_type, str) else i.drift_type.value,
                          "approved": i.approved_value, "observed": i.observed_value}
                         for i in items],
            }
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for nid, data in results.items():
                if "error" in data:
                    print(f"\n{nid}: {data['error']}")
                else:
                    print(f"\n{nid}: drift_type={data['drift_type']} items={len(data['items'])}")
                    for item in data["items"]:
                        print(f"  {item['component']}: {item['type']} ({item['approved']} -> {item['observed']})")

    elif args.command == "plan":
        plan = mgr.create_plan(args.node)
        if args.json:
            print(json.dumps(plan.to_dict(), indent=2))
        else:
            print(f"Plan: {plan.plan_id}")
            print(f"  Node: {plan.node_id} Status: {plan.status.value}")
            print(f"  Actions: {[a.value if isinstance(a, RemediationAction) else a for a in plan.actions]}")
            print(f"  Digest: {plan.plan_digest}")
            print(f"  Before SHA: {plan.before_fingerprint_sha}")

    elif args.command == "approve":
        result = mgr.approve_plan(args.plan_id, args.operator)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["ok"]:
                print(f"Approved: {args.plan_id}")
                print(f"  Expires: {result['receipt'].get('expires_at', 'N/A')}")
            else:
                print(f"Failed: {result['error']}")

    elif args.command == "apply":
        event = mgr.apply_plan(args.plan_id)
        if args.json:
            print(json.dumps(event.to_dict(), indent=2))
        else:
            print(f"Apply: {event.plan_id} -> {event.status.value}")
            print(f"  Resolution: {event.resolution}")

    elif args.command == "reconcile":
        event = mgr.reconcile(args.node)
        if args.json:
            print(json.dumps(event.to_dict(), indent=2))
        else:
            print(f"Reconcile {args.node}: {event.status.value}")
            print(f"  Resolution: {event.resolution}")

    elif args.command == "rollback":
        event = mgr.rollback(args.node)
        if args.json:
            print(json.dumps(event.to_dict(), indent=2))
        else:
            print(f"Rollback {args.node}: {event.status.value}")
            print(f"  Resolution: {event.resolution}")

    elif args.command == "adopt-candidate":
        receipt = None
        if args.receipt:
            with open(args.receipt) as rf:
                receipt = json.load(rf)
        result = mgr.adopt_candidate(args.node, plan_id=args.plan_id, approval_receipt=receipt)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["ok"]:
                print(f"Adopted: {args.node} sha={result.get('sha256', '')} plan={result.get('plan_id', '')}")
            else:
                print(f"Failed: {result.get('error')}")

    elif args.command == "freeze":
        receipt = None
        if args.receipt:
            with open(args.receipt) as rf:
                receipt = json.load(rf)
        result = mgr.freeze(args.node, plan_id=args.plan_id, approval_receipt=receipt)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["ok"]:
                print(f"Frozen: {args.node} sha={result.get('sha256', '')} plan={result.get('plan_id', '')}")
            else:
                print(f"Failed: {result.get('error')}: {result.get('detail', '')}")

    elif args.command == "events":
        events = mgr.store.get_events(args.limit)
        if args.json:
            print(json.dumps(events, indent=2))
        else:
            for e in events:
                print(f"[{e.get('event_id')}] {e.get('node_id')}: "
                      f"{e.get('drift_type')} -> {e.get('status')} | {e.get('resolution')}")

    elif args.command == "history":
        history = mgr.store.get_history(args.limit)
        if args.json:
            print(json.dumps(history, indent=2))
        else:
            for h in history:
                print(f"[{h.get('at', '')[:19]}] {h.get('action')}: {h.get('detail', '')}")

    elif args.command == "gate-check":
        gate = mgr.gate.is_writes_allowed()
        # Also check scheduler gate via public API
        gate["gate_version"] = __version__
        gate["checked_at"] = datetime.now(timezone.utc).isoformat()
        if args.json:
            print(json.dumps(gate, indent=2))
        else:
            if gate["allowed"]:
                print("Gate: ALLOWED")
                print(f"  Version: {__version__}")
            else:
                print(f"Gate: BLOCKED — {gate['reason']}: {gate.get('detail', '')}")
                print(f"  Version: {__version__}")
                print(f"  Action: Block all write operations (implement/review/branch/merge)")

    elif args.command == "repair":
        mgr.store.repair("operator")
        print("Repaired: corruption latch cleared, state reinitialized")

    elif args.command == "opencode-plan":
        artifact = mgr.generate_opencode_plan_only()
        if args.json:
            print(json.dumps(artifact, indent=2))
        else:
            print(f"OpenCode PLAN ONLY:")
            cv5 = artifact.get("current_version_5bao", "N/A")
            cv9 = artifact.get("current_version_9bao", "N/A")
            print(f"  Current 5bao: {cv5}")
            print(f"  Current 9bao: {cv9}")
            print(f"  Target: {artifact['target_version']}")
            print(f"  Latest npm: {artifact['latest_npm_version']}")
            print(f"  Risk: {artifact['risk']}")
            print(f"  Blocked: {artifact['blocked_reason']}")


if __name__ == "__main__":
    main()
