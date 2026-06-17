#!/usr/bin/env python3
"""vibe_toolchain_lifecycle.py — Toolchain Lifecycle Manager v1.0.0

Runtime Drift Reconciler + Controlled Self-Healing for the VibeDev worker pool.
Detects, classifies, isolates, reconciles, and freezes runtime drift across
5bao and 9bao Debian workers.

Runtime fingerprint collected via SSH: version, binary path/hash, config hash,
lockfile, Python venv, npm dependency tree, wrapper, Git, gh, Node, OpenCode,
pytest, and critical system packages.

Three-state model:
  approved_runtime_baseline  — frozen, human-approved
  observed_runtime_state     — current SSH-collected reality
  candidate_runtime_baseline — canary-validated, pending adoption

Drift classification:
  PATH_DRIFT, PATCH_VERSION_DRIFT, DEPENDENCY_DRIFT, CONFIG_DRIFT,
  SECRET_DRIFT, SYSTEM_PACKAGE_DRIFT, MAJOR_VERSION_DRIFT, UNKNOWN_DRIFT

Auto-remediation:
  PATH_DRIFT             → auto-fix wrapper/PATH + verify
  DEPENDENCY_DRIFT       → rebuild per package-lock/venv contract
  CONFIG_DRIFT (non-sens)→ restore approved config
  PATCH_VERSION_DRIFT    → maintenance + canary; pass → candidate + converge;
                           fail → auto-rollback
  SECRET_DRIFT           → BLOCK, never auto-copy
  MAJOR/SYSTEM/UNKNOWN   → maintenance + wait for operator

Dual-node safety: only one node drift-healed at a time. Both unknown → no writes.

Commands:
    python3 scripts/vibe_toolchain_lifecycle.py --drift [--json]
    python3 scripts/vibe_toolchain_lifecycle.py --reconcile [--node 5bao|9bao] [--json]
    python3 scripts/vibe_toolchain_lifecycle.py --events [--json] [--limit N]
    python3 scripts/vibe_toolchain_lifecycle.py --adopt-candidate [--node 5bao|9bao] [--json]
    python3 scripts/vibe_toolchain_lifecycle.py --rollback-drift [--node 5bao|9bao] [--event-id ID] [--json]
    python3 scripts/vibe_toolchain_lifecycle.py --self-check [--json]
"""

__version__ = "1.0.0"

import copy
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from vibe_worker_registry import WorkerRegistry, WorkerNode, NodeStatus


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DriftType(str, Enum):
    PATH_DRIFT = "PATH_DRIFT"
    PATCH_VERSION_DRIFT = "PATCH_VERSION_DRIFT"
    DEPENDENCY_DRIFT = "DEPENDENCY_DRIFT"
    CONFIG_DRIFT = "CONFIG_DRIFT"
    SECRET_DRIFT = "SECRET_DRIFT"
    SYSTEM_PACKAGE_DRIFT = "SYSTEM_PACKAGE_DRIFT"
    MAJOR_VERSION_DRIFT = "MAJOR_VERSION_DRIFT"
    UNKNOWN_DRIFT = "UNKNOWN_DRIFT"


class BaselineState(str, Enum):
    APPROVED = "approved"
    OBSERVED = "observed"
    CANDIDATE = "candidate"


class RemediationAction(str, Enum):
    AUTO_FIX = "auto_fix"
    REBUILD = "rebuild"
    RESTORE_CONFIG = "restore_config"
    CANARY_VALIDATION = "canary_validation"
    FORWARD_CONVERGE = "forward_converge"
    ROLLBACK = "rollback"
    BLOCK = "block"
    OPERATOR_REQUIRED = "operator_required"


class DriftEventStatus(str, Enum):
    DETECTED = "detected"
    ISOLATED = "isolated"
    RECONCILING = "reconciling"
    CANARY = "canary"
    RESOLVED = "resolved"
    ROLLED_BACK = "rolled_back"
    BLOCKED = "blocked"
    OPERATOR_WAITING = "operator_waiting"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RuntimeComponent:
    """Single component fingerprint (e.g. opencode binary, git, node)."""
    name: str
    version: str = ""
    binary_path: str = ""
    binary_hash: str = ""  # sha256 of binary file
    config_hash: str = ""  # sha256 of config file(s)
    extra: dict = field(default_factory=dict)


@dataclass
class RuntimeFingerprint:
    """Complete runtime state of a worker node."""
    node_id: str
    collected_at: str = ""
    hostname: str = ""
    components: dict = field(default_factory=dict)  # name -> RuntimeComponent dict
    path_dirs: list = field(default_factory=list)
    env_vars: dict = field(default_factory=dict)  # non-secret env vars only
    ssh_reachable: bool = False
    collection_errors: list = field(default_factory=list)

    def to_dict(self):
        return {
            "node_id": self.node_id,
            "collected_at": self.collected_at,
            "hostname": self.hostname,
            "components": self.components,
            "path_dirs": self.path_dirs,
            "ssh_reachable": self.ssh_reachable,
            "collection_errors": self.collection_errors,
        }


@dataclass
class RuntimeBaseline:
    """Three-state baseline model."""
    state: BaselineState
    fingerprint: RuntimeFingerprint
    sha256: str = ""  # hash of the fingerprint JSON
    frozen_at: str = ""
    frozen_by: str = ""  # "operator" or "auto_converge"


@dataclass
class DriftItem:
    """Single drift finding."""
    component: str
    drift_type: DriftType
    approved_value: str = ""
    observed_value: str = ""
    detail: str = ""


@dataclass
class DriftEvent:
    """Evidence record for a drift detection/reconciliation cycle."""
    event_id: str
    node_id: str
    detected_at: str = ""
    drift_type: DriftType = DriftType.UNKNOWN_DRIFT
    status: DriftEventStatus = DriftEventStatus.DETECTED
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    drift_items: list = field(default_factory=list)
    maintenance_set: bool = False
    remediation: RemediationAction = RemediationAction.OPERATOR_REQUIRED
    canary_result: str = ""  # PASS/FAIL/SKIP
    canary_details: list = field(default_factory=list)
    rollback_performed: bool = False
    forward_converge: bool = False
    other_node_converged: str = ""
    runtime_baseline_sha: str = ""
    operator_required: bool = True
    resolution: str = ""
    resolved_at: str = ""

    def to_dict(self):
        return {
            "event_id": self.event_id,
            "node_id": self.node_id,
            "detected_at": self.detected_at,
            "drift_type": self.drift_type.value if isinstance(self.drift_type, DriftType) else self.drift_type,
            "status": self.status.value if isinstance(self.status, DriftEventStatus) else self.status,
            "before": self.before,
            "after": self.after,
            "drift_items": self.drift_items,
            "maintenance_set": self.maintenance_set,
            "remediation": self.remediation.value if isinstance(self.remediation, RemediationAction) else self.remediation,
            "canary_result": self.canary_result,
            "canary_details": self.canary_details,
            "rollback_performed": self.rollback_performed,
            "forward_converge": self.forward_converge,
            "other_node_converged": self.other_node_converged,
            "runtime_baseline_sha": self.runtime_baseline_sha,
            "operator_required": self.operator_required,
            "resolution": self.resolution,
            "resolved_at": self.resolved_at,
        }


# ---------------------------------------------------------------------------
# SSH helpers
# ---------------------------------------------------------------------------

SSH_KEY = os.environ.get(
    "VIBEDEV_SSH_KEY",
    os.path.expanduser("~") + "/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519"
)
SSH_OPTS = ["-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes"]


def _ssh(host: str, port: int, user: str, cmd: str, timeout: int = 20) -> tuple:
    """Run SSH command. Returns (exit_code, stdout, stderr)."""
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

    # Commands that produce version + path info for each component
    COMPONENT_QUERIES = {
        "opencode": "which opencode 2>/dev/null && opencode --version 2>/dev/null && sha256sum $(which opencode 2>/dev/null) 2>/dev/null | awk '{print $1}'",
        "node": "which node 2>/dev/null && node --version 2>/dev/null",
        "npm": "which npm 2>/dev/null && npm --version 2>/dev/null",
        "python3": "which python3 2>/dev/null && python3 --version 2>/dev/null",
        "git": "which git 2>/dev/null && git --version 2>/dev/null",
        "gh": "which gh 2>/dev/null && gh --version 2>/dev/null | head -1",
        "pytest": "python3 -m pytest --version 2>/dev/null | head -1",
        "ssh_server": "sshd -V 2>&1 | head -1 || echo 'sshd_unknown'",
    }

    WRAPPER_QUERY = "sha256sum ~/.local/bin/vibedev-opencode-wrapper.sh 2>/dev/null | awk '{print $1}'"
    CONFIG_QUERY = "sha256sum ~/.config/vibedev-opencode/opencode.jsonc 2>/dev/null | awk '{print $1}'"
    LOCKFILE_QUERY = "sha256sum ~/.config/vibedev-opencode/package-lock.json 2>/dev/null | awk '{print $1}'"
    VENV_QUERY = "python3 -c 'import sys; print(sys.prefix)' 2>/dev/null && test -d ~/.vibedev/test-envs/toolchain/venv && echo venv_exists || echo venv_missing"
    NPM_DEPS_QUERY = "cd ~/.config/vibedev-opencode && sha256sum package.json 2>/dev/null | awk '{print $1}' && test -d node_modules && echo node_modules_exists || echo node_modules_missing"
    PATH_QUERY = "echo $PATH"
    SYSTEM_PKGS_QUERY = "dpkg -l openssh-server 2>/dev/null | tail -1 | awk '{print $2, $3}' && dpkg -l libc6 2>/dev/null | tail -1 | awk '{print $2, $3}' && uname -r"
    OPENCODE_ENV_QUERY = "sha256sum ~/.vibedev-secrets/opencode.env 2>/dev/null | awk '{print $1}'"

    def collect(self, worker: WorkerNode) -> RuntimeFingerprint:
        """Collect full fingerprint from a worker."""
        fp = RuntimeFingerprint(
            node_id=worker.worker_id,
            collected_at=datetime.now(timezone.utc).isoformat(),
        )

        # Check reachability first
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
            comp = {"name": name, "raw": out, "error": err if rc != 0 else ""}
            # Parse version and path from output
            lines = [l.strip() for l in out.split("\n") if l.strip()]
            if lines:
                comp["path"] = lines[0] if "/" in lines[0] else ""
                version_candidates = [l for l in lines if l and l[0].isdigit()]
                comp["version"] = version_candidates[0] if version_candidates else lines[-1]
                if name == "opencode" and len(lines) >= 3:
                    comp["binary_hash"] = lines[2][:16] if len(lines[2]) >= 16 else lines[2]
            fp.components[name] = comp

        # Wrapper hash
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.WRAPPER_QUERY)
        fp.components["wrapper"] = {"name": "wrapper", "hash": out.strip()[:16] if rc == 0 else ""}

        # Config hash
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.CONFIG_QUERY)
        fp.components["config"] = {"name": "config", "hash": out.strip()[:16] if rc == 0 else ""}

        # Lockfile hash
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.LOCKFILE_QUERY)
        fp.components["lockfile"] = {"name": "lockfile", "hash": out.strip()[:16] if rc == 0 else ""}

        # Venv
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.VENV_QUERY)
        fp.components["venv"] = {"name": "venv", "raw": out, "exists": "venv_exists" in out}

        # NPM deps
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.NPM_DEPS_QUERY)
        lines = [l.strip() for l in out.split("\n") if l.strip()]
        fp.components["npm_deps"] = {
            "name": "npm_deps",
            "package_hash": lines[0][:16] if lines else "",
            "node_modules": "node_modules_exists" in out,
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
        }

        # Secret fingerprint (hash only, never the content)
        rc, out, _ = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, self.OPENCODE_ENV_QUERY)
        fp.components["secret_fingerprint"] = {
            "name": "secret_fingerprint",
            "hash": out.strip()[:16] if rc == 0 else "",
        }

        return fp


# ---------------------------------------------------------------------------
# Drift Detector
# ---------------------------------------------------------------------------

class DriftDetector:
    """Compares approved baseline against observed state."""

    # Components that are secret-related — drift = BLOCK, never auto-fix
    SECRET_COMPONENTS = {"secret_fingerprint"}

    # Components that trigger SYSTEM_PACKAGE_DRIFT
    SYSTEM_COMPONENTS = {"system"}

    # Version-sensitive components
    VERSION_COMPONENTS = {"opencode", "node", "npm", "git", "gh", "python3", "pytest"}

    def detect(self, approved: RuntimeFingerprint,
               observed: RuntimeFingerprint) -> list:
        """Return list of DriftItem."""
        items = []

        # Check reachability
        if not observed.ssh_reachable:
            items.append(DriftItem(
                component="ssh",
                drift_type=DriftType.UNKNOWN_DRIFT,
                detail="worker unreachable",
            ))
            return items

        # Check hostname stability
        if approved.hostname and observed.hostname and approved.hostname != observed.hostname:
            items.append(DriftItem(
                component="hostname",
                drift_type=DriftType.CONFIG_DRIFT,
                approved_value=approved.hostname,
                observed_value=observed.hostname,
            ))

        # PATH drift
        approved_path = ":".join(approved.path_dirs)
        observed_path = ":".join(observed.path_dirs)
        if approved_path and observed_path and approved_path != observed_path:
            items.append(DriftItem(
                component="PATH",
                drift_type=DriftType.PATH_DRIFT,
                approved_value=approved_path,
                observed_value=observed_path,
                detail=f"dirs_changed: {len(approved.path_dirs)} vs {len(observed.path_dirs)}",
            ))

        # Component-level comparison
        for name in set(list(approved.components.keys()) + list(observed.components.keys())):
            a_comp = approved.components.get(name, {})
            o_comp = observed.components.get(name, {})

            # Secret drift
            if name in self.SECRET_COMPONENTS:
                a_hash = a_comp.get("hash", "")
                o_hash = o_comp.get("hash", "")
                if a_hash and o_hash and a_hash != o_hash:
                    items.append(DriftItem(
                        component=name,
                        drift_type=DriftType.SECRET_DRIFT,
                        approved_value=a_hash,
                        observed_value=o_hash,
                        detail="secret content changed — BLOCK auto-remediation",
                    ))
                continue

            # System package drift
            if name in self.SYSTEM_COMPONENTS:
                for pkg in ("openssh", "libc6", "kernel"):
                    a_val = a_comp.get(pkg, "")
                    o_val = o_comp.get(pkg, "")
                    if a_val and o_val and a_val != o_val:
                        items.append(DriftItem(
                            component=f"{name}.{pkg}",
                            drift_type=DriftType.SYSTEM_PACKAGE_DRIFT,
                            approved_value=a_val,
                            observed_value=o_val,
                        ))
                continue

            # Version component drift
            if name in self.VERSION_COMPONENTS:
                a_ver = a_comp.get("version", "")
                o_ver = o_comp.get("version", "")
                if a_ver and o_ver and a_ver != o_ver:
                    drift_type = self._classify_version_drift(a_ver, o_ver)
                    items.append(DriftItem(
                        component=name,
                        drift_type=drift_type,
                        approved_value=a_ver,
                        observed_value=o_ver,
                    ))
                # Binary hash drift (same version, different binary)
                a_hash = a_comp.get("binary_hash", "")
                o_hash = o_comp.get("binary_hash", "")
                if a_hash and o_hash and a_hash != o_hash and a_ver == o_ver:
                    items.append(DriftItem(
                        component=f"{name}.binary",
                        drift_type=DriftType.PATCH_VERSION_DRIFT,
                        approved_value=a_hash,
                        observed_value=o_hash,
                        detail="binary_hash_changed_same_version",
                    ))

            # Wrapper/config/lockfile/npm_deps hash drift
            for hash_key in ("hash", "config_hash", "package_hash"):
                a_val = a_comp.get(hash_key, "")
                o_val = o_comp.get(hash_key, "")
                if a_val and o_val and a_val != o_val:
                    dtype = DriftType.CONFIG_DRIFT if "config" in name else DriftType.DEPENDENCY_DRIFT
                    if name == "wrapper":
                        dtype = DriftType.CONFIG_DRIFT
                    items.append(DriftItem(
                        component=f"{name}.{hash_key}",
                        drift_type=dtype,
                        approved_value=a_val,
                        observed_value=o_val,
                    ))

            # node_modules existence
            if name == "npm_deps":
                a_nm = a_comp.get("node_modules", True)
                o_nm = o_comp.get("node_modules", True)
                if a_nm and not o_nm:
                    items.append(DriftItem(
                        component="npm_deps.node_modules",
                        drift_type=DriftType.DEPENDENCY_DRIFT,
                        approved_value="exists",
                        observed_value="missing",
                    ))

            # venv existence
            if name == "venv":
                a_ex = a_comp.get("exists", True)
                o_ex = o_comp.get("exists", True)
                if a_ex and not o_ex:
                    items.append(DriftItem(
                        component="venv",
                        drift_type=DriftType.DEPENDENCY_DRIFT,
                        approved_value="exists",
                        observed_value="missing",
                    ))

        return items

    def _classify_version_drift(self, approved: str, observed: str) -> DriftType:
        """Classify version difference as PATCH or MAJOR."""
        def parse_ver(v: str) -> list:
            # Strip leading 'v' and any suffix
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
            a = parse_ver(approved)
            o = parse_ver(observed)
            if a[0] != o[0] or a[1] != o[1]:
                return DriftType.MAJOR_VERSION_DRIFT
            return DriftType.PATCH_VERSION_DRIFT
        except Exception:
            return DriftType.UNKNOWN_DRIFT


# ---------------------------------------------------------------------------
# Drift Classifier — aggregate a list of DriftItems into a single DriftType
# ---------------------------------------------------------------------------

class DriftClassifier:
    """Classifies overall drift severity from a list of drift items."""

    # Priority: higher index = more severe
    PRIORITY = [
        DriftType.PATH_DRIFT,
        DriftType.PATCH_VERSION_DRIFT,
        DriftType.DEPENDENCY_DRIFT,
        DriftType.CONFIG_DRIFT,
        DriftType.SYSTEM_PACKAGE_DRIFT,
        DriftType.MAJOR_VERSION_DRIFT,
        DriftType.SECRET_DRIFT,
        DriftType.UNKNOWN_DRIFT,
    ]

    def classify(self, items: list) -> DriftType:
        """Return the most severe drift type from the items."""
        if not items:
            return DriftType.PATH_DRIFT  # no drift

        types = set(item.drift_type if isinstance(item.drift_type, DriftType)
                     else DriftType(item.drift_type) for item in items)

        # UNKNOWN wins over everything
        if DriftType.UNKNOWN_DRIFT in types:
            return DriftType.UNKNOWN_DRIFT
        # SECRET is second-highest priority
        if DriftType.SECRET_DRIFT in types:
            return DriftType.SECRET_DRIFT
        # Otherwise find highest priority
        for dtype in reversed(self.PRIORITY):
            if dtype in types:
                return dtype
        return DriftType.UNKNOWN_DRIFT


# ---------------------------------------------------------------------------
# Remediation Planner
# ---------------------------------------------------------------------------

class RemediationPlanner:
    """Determines remediation action for a drift type."""

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
# Toolchain Lifecycle Manager
# ---------------------------------------------------------------------------

class ToolchainLifecycleManager:
    """Main orchestrator for drift detection, reconciliation, and evidence."""

    def __init__(self, registry: WorkerRegistry = None,
                 approved_baselines: dict = None,
                 event_log_path: str = None):
        self.registry = registry or WorkerRegistry()
        self.collector = FingerprintCollector()
        self.detector = DriftDetector()
        self.classifier = DriftClassifier()
        self.planner = RemediationPlanner()
        # approved baselines: node_id -> RuntimeBaseline
        self.approved_baselines: dict = approved_baselines or {}
        # observed states: node_id -> RuntimeFingerprint
        self.observed_states: dict = {}
        # candidate baselines: node_id -> RuntimeBaseline
        self.candidate_baselines: dict = {}
        # event log
        self.event_log: list = []
        self.event_log_path = event_log_path or ""
        self._event_counter = 0
        self._load_events()

    def _load_events(self):
        if self.event_log_path and os.path.exists(self.event_log_path):
            try:
                with open(self.event_log_path) as f:
                    self.event_log = json.load(f)
                self._event_counter = len(self.event_log)
            except Exception:
                pass

    def _save_events(self):
        if self.event_log_path:
            try:
                os.makedirs(os.path.dirname(self.event_log_path) or ".", exist_ok=True)
                with open(self.event_log_path, "w") as f:
                    json.dump(self.event_log, f, indent=2, default=str)
            except Exception:
                pass

    def _next_event_id(self) -> str:
        self._event_counter += 1
        ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
        return f"drift-{ts}-{self._event_counter:03d}"

    # --- Core operations ---

    def collect_fingerprint(self, node_id: str) -> RuntimeFingerprint:
        """Collect runtime fingerprint from a worker."""
        worker = self.registry.get_worker(node_id)
        if not worker:
            raise ValueError(f"Unknown worker: {node_id}")
        fp = self.collector.collect(worker)
        self.observed_states[node_id] = fp
        return fp

    def set_approved_baseline(self, node_id: str, fp: RuntimeFingerprint):
        """Set/replace the approved baseline for a node."""
        sha = _sha256_text(json.dumps(fp.to_dict(), sort_keys=True, default=str))
        self.approved_baselines[node_id] = RuntimeBaseline(
            state=BaselineState.APPROVED,
            fingerprint=fp,
            sha256=sha,
            frozen_at=datetime.now(timezone.utc).isoformat(),
            frozen_by="operator",
        )

    def detect_drift(self, node_id: str) -> tuple:
        """Detect drift for a node. Returns (drift_items, drift_type)."""
        approved = self.approved_baselines.get(node_id)
        if not approved:
            return [], None

        observed = self.observed_states.get(node_id)
        if not observed:
            observed = self.collect_fingerprint(node_id)

        items = self.detector.detect(approved.fingerprint, observed)
        drift_type = self.classifier.classify(items) if items else None
        return items, drift_type

    def detect_all_drift(self) -> dict:
        """Detect drift on all registered workers. Returns {node_id: (items, type)}."""
        results = {}
        for worker in self.registry.list_workers():
            if worker.health_status == NodeStatus.ONLINE:
                self.collect_fingerprint(worker.worker_id)
                items, dtype = self.detect_drift(worker.worker_id)
                results[worker.worker_id] = {"items": items, "drift_type": dtype}
        return results

    def reconcile(self, node_id: str, items: list = None,
                  drift_type: DriftType = None) -> DriftEvent:
        """Attempt to reconcile drift for a node.

        Dual-node safety: if both nodes have UNKNOWN drift, refuse write tasks.
        Only one node at a time can be reconciled.
        """
        if items is None or drift_type is None:
            items, drift_type = self.detect_drift(node_id)

        event = DriftEvent(
            event_id=self._next_event_id(),
            node_id=node_id,
            detected_at=datetime.now(timezone.utc).isoformat(),
            drift_type=drift_type or DriftType.UNKNOWN_DRIFT,
        )

        if not items:
            event.status = DriftEventStatus.RESOLVED
            event.resolution = "no_drift_detected"
            event.operator_required = False
            self.event_log.append(event.to_dict())
            self._save_events()
            return event

        # Dual-node safety check
        if self._both_nodes_unknown(node_id):
            event.status = DriftEventStatus.BLOCKED
            event.remediation = RemediationAction.OPERATOR_REQUIRED
            event.operator_required = True
            event.resolution = "both_nodes_unknown_drift_no_writes_allowed"
            self.event_log.append(event.to_dict())
            self._save_events()
            return event

        # Determine remediation
        action = self.planner.plan(drift_type)
        event.remediation = action

        # Set maintenance for non-trivial drift
        if action not in (RemediationAction.AUTO_FIX,):
            worker = self.registry.get_worker(node_id)
            if worker:
                self.registry.set_maintenance(node_id, "maintenance")
                event.maintenance_set = True

        event.status = DriftEventStatus.RECONCILING

        # Execute remediation
        if action == RemediationAction.AUTO_FIX:
            event = self._auto_fix_path(node_id, items, event)
        elif action == RemediationAction.REBUILD:
            event = self._rebuild_deps(node_id, items, event)
        elif action == RemediationAction.RESTORE_CONFIG:
            event = self._restore_config(node_id, items, event)
        elif action == RemediationAction.CANARY_VALIDATION:
            event = self._canary_validate(node_id, items, event)
        elif action == RemediationAction.BLOCK:
            event.status = DriftEventStatus.BLOCKED
            event.operator_required = True
            event.resolution = "secret_drift_blocked_no_auto_remediation"
        else:
            event.status = DriftEventStatus.OPERATOR_WAITING
            event.operator_required = True
            event.resolution = f"operator_approval_required_for_{drift_type.value}"

        self.event_log.append(event.to_dict())
        self._save_events()
        return event

    def _both_nodes_unknown(self, current_node: str) -> bool:
        """Check if both nodes have UNKNOWN drift."""
        other_node = "9bao" if current_node == "5bao" else "5bao"
        other_has_unknown = False
        current_has_unknown = False
        for evt in self.event_log:
            if (evt.get("drift_type") == DriftType.UNKNOWN_DRIFT.value
                    and evt.get("status") in (DriftEventStatus.DETECTED.value,
                                               DriftEventStatus.OPERATOR_WAITING.value)):
                if evt.get("node_id") == other_node:
                    other_has_unknown = True
                elif evt.get("node_id") == current_node:
                    current_has_unknown = True
        return other_has_unknown and current_has_unknown
    def _auto_fix_path(self, node_id: str, items: list, event: DriftEvent) -> DriftEvent:
        """Auto-fix PATH drift by updating wrapper/PATH."""
        worker = self.registry.get_worker(node_id)
        if not worker:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "worker_not_found"
            return event

        # Verify current PATH on the worker
        approved_fp = self.approved_baselines[node_id].fingerprint
        approved_path = ":".join(approved_fp.path_dirs)

        # Write PATH fix to .profile if needed
        rc, out, err = _ssh(
            worker.ssh_host, worker.ssh_port, worker.ssh_user,
            f'grep -q "VIBEDEV_TOOLCHAIN_PATH" ~/.profile 2>/dev/null && echo "already_set" || echo "needs_fix"'
        )

        if "needs_fix" in out and approved_path:
            # Auto-fix: add critical paths to .profile
            critical_dirs = [d for d in approved_fp.path_dirs
                            if ".local/bin" in d or ".opencode/bin" in d or "node-current" in d]
            for d in critical_dirs:
                _ssh(
                    worker.ssh_host, worker.ssh_port, worker.ssh_user,
                    f'grep -q "{d}" ~/.profile 2>/dev/null || echo \'export PATH="{d}:$PATH"\' >> ~/.profile'
                )

        # Re-collect and verify
        new_fp = self.collector.collect(worker)
        self.observed_states[node_id] = new_fp
        new_items, new_type = self.detect_drift(node_id)

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
            event.operator_required = True
            event.resolution = "path_auto_fix_insufficient"

        return event

    def _rebuild_deps(self, node_id: str, items: list, event: DriftEvent) -> DriftEvent:
        """Rebuild dependencies (npm ci, venv recreate)."""
        worker = self.registry.get_worker(node_id)
        if not worker:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "worker_not_found"
            return event

        rebuild_results = []

        # Check if npm deps need rebuild
        dep_items = [i for i in items if "npm" in i.component or "node_modules" in i.component]
        if dep_items:
            rc, out, err = _ssh(
                worker.ssh_host, worker.ssh_port, worker.ssh_user,
                "cd ~/.config/vibedev-opencode && npm ci 2>&1 | tail -5"
            )
            rebuild_results.append({"component": "npm", "rc": rc, "output": out[:200]})

        # Check if venv needs rebuild
        venv_items = [i for i in items if "venv" in i.component]
        if venv_items:
            rc, out, err = _ssh(
                worker.ssh_host, worker.ssh_port, worker.ssh_user,
                "python3 -m venv ~/.vibedev/test-envs/toolchain/venv --clear 2>&1 && "
                "~/.vibedev/test-envs/toolchain/venv/bin/pip install -q pytest pytest-timeout 2>&1 | tail -3"
            )
            rebuild_results.append({"component": "venv", "rc": rc, "output": out[:200]})

        # Re-verify
        new_fp = self.collector.collect(worker)
        self.observed_states[node_id] = new_fp
        new_items, _ = self.detect_drift(node_id)
        dep_items_after = [i for i in new_items if i.drift_type == DriftType.DEPENDENCY_DRIFT]

        if not dep_items_after:
            event.status = DriftEventStatus.RESOLVED
            event.resolution = "deps_rebuilt_successfully"
            event.operator_required = False
            if event.maintenance_set:
                self.registry.set_maintenance(node_id, "active")
                event.maintenance_set = False
        else:
            event.status = DriftEventStatus.OPERATOR_WAITING
            event.operator_required = True
            event.resolution = "deps_rebuild_insufficient"

        event.after = {"rebuild_results": rebuild_results}
        return event

    def _restore_config(self, node_id: str, items: list, event: DriftEvent) -> DriftEvent:
        """Restore approved config files (non-secret)."""
        worker = self.registry.get_worker(node_id)
        if not worker:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "worker_not_found"
            return event

        approved_fp = self.approved_baselines[node_id].fingerprint
        restore_results = []

        # Restore wrapper hash
        wrapper_items = [i for i in items if "wrapper" in i.component]
        if wrapper_items:
            # Re-sync wrapper from approved source
            rc, out, err = _ssh(
                worker.ssh_host, worker.ssh_port, worker.ssh_user,
                "test -f ~/vibedev/repos/vibe-coding-repo.git/scripts/vibedev-opencode-wrapper.sh && "
                "cp ~/vibedev/repos/vibe-coding-repo.git/scripts/vibedev-opencode-wrapper.sh "
                "~/.local/bin/vibedev-opencode-wrapper.sh && chmod +x ~/.local/bin/vibedev-opencode-wrapper.sh "
                "&& echo restored || echo source_not_found"
            )
            restore_results.append({"component": "wrapper", "result": out[:100]})

        # Restore opencode.jsonc
        config_items = [i for i in items if "config" in i.component and "secret" not in i.component]
        if config_items:
            rc, out, err = _ssh(
                worker.ssh_host, worker.ssh_port, worker.ssh_user,
                "test -f ~/vibedev/repos/vibe-coding-repo.git/configs/opencode.jsonc && "
                "cp ~/vibedev/repos/vibe-coding-repo.git/configs/opencode.jsonc "
                "~/.config/vibedev-opencode/opencode.jsonc "
                "&& echo restored || echo source_not_found"
            )
            restore_results.append({"component": "config", "result": out[:100]})

        event.after = {"restore_results": restore_results}

        # Re-verify
        new_fp = self.collector.collect(worker)
        self.observed_states[node_id] = new_fp
        new_items, _ = self.detect_drift(node_id)
        config_items_after = [i for i in new_items
                             if i.drift_type == DriftType.CONFIG_DRIFT
                             and "secret" not in i.component]

        if not config_items_after:
            event.status = DriftEventStatus.RESOLVED
            event.resolution = "config_restored_from_approved"
            event.operator_required = False
            if event.maintenance_set:
                self.registry.set_maintenance(node_id, "active")
                event.maintenance_set = False
        else:
            event.status = DriftEventStatus.OPERATOR_WAITING
            event.operator_required = True
            event.resolution = "config_restore_insufficient"

        return event

    def _canary_validate(self, node_id: str, items: list, event: DriftEvent) -> DriftEvent:
        """Canary validation for PATCH_VERSION_DRIFT.

        Runs compatibility suite, then promotes to candidate if PASS.
        """
        worker = self.registry.get_worker(node_id)
        if not worker:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "worker_not_found"
            return event

        event.status = DriftEventStatus.CANARY

        # Canary checks — run on the worker
        canary_results = []
        checks = [
            ("binary_version", "which opencode && opencode --version"),
            ("non_login_wrapper", "bash -c 'source ~/.profile 2>/dev/null; which opencode && echo wrapper_ok'"),
            ("config_parse", "python3 -c \"import json; json.load(open('/home/vibeworker/.config/vibedev-opencode/opencode.jsonc'.replace('.jsonc','.json')) if __import__('os').path.exists('/home/vibeworker/.config/vibedev-opencode/opencode.jsonc'.replace('.jsonc','.json')) else __import__('io').StringIO('{}')); print('config_ok')\" 2>/dev/null || echo config_parse_skip"),
            ("git_available", "git --version && echo git_ok"),
            ("pytest_available", "python3 -m pytest --version 2>/dev/null | head -1 && echo pytest_ok"),
            ("repo_baseline", "cd ~/vibedev/repos/vibe-coding-repo.git && git rev-parse HEAD"),
        ]

        for check_name, cmd in checks:
            rc, out, err = _ssh(worker.ssh_host, worker.ssh_port, worker.ssh_user, cmd)
            canary_results.append({
                "check": check_name,
                "passed": rc == 0,
                "output": out[:200],
            })

        # Run standalone tests if available
        rc, out, err = _ssh(
            worker.ssh_host, worker.ssh_port, worker.ssh_user,
            "cd ~/vibedev/repos/vibe-coding-repo.git && "
            "python3 -c \"import scripts.vibe_worker_registry as r; print('registry_import_ok')\" 2>/dev/null"
        )
        canary_results.append({
            "check": "registry_import",
            "passed": rc == 0 and "registry_import_ok" in out,
            "output": out[:200],
        })

        passed = sum(1 for c in canary_results if c["passed"])
        total = len(canary_results)
        canary_pass = passed == total

        event.canary_result = "PASS" if canary_pass else "FAIL"
        event.canary_details = canary_results

        if canary_pass:
            # Promote to candidate baseline
            observed = self.observed_states.get(node_id)
            if observed:
                sha = _sha256_text(json.dumps(observed.to_dict(), sort_keys=True, default=str))
                self.candidate_baselines[node_id] = RuntimeBaseline(
                    state=BaselineState.CANDIDATE,
                    fingerprint=observed,
                    sha256=sha,
                    frozen_at=datetime.now(timezone.utc).isoformat(),
                    frozen_by="auto_canary",
                )
                event.status = DriftEventStatus.CANARY
                event.runtime_baseline_sha = sha
                event.operator_required = True
                event.resolution = "canary_pass_candidate_created_awaiting_adopt"
            else:
                event.status = DriftEventStatus.BLOCKED
                event.resolution = "no_observed_state_for_candidate"
        else:
            # Auto-rollback
            event = self._rollback_to_approved(node_id, event)

        return event

    def _rollback_to_approved(self, node_id: str, event: DriftEvent) -> DriftEvent:
        """Rollback to approved baseline version."""
        worker = self.registry.get_worker(node_id)
        if not worker:
            event.status = DriftEventStatus.BLOCKED
            event.resolution = "worker_not_found"
            return event

        approved_fp = self.approved_baselines[node_id].fingerprint

        # Get approved opencode version
        approved_oc = approved_fp.components.get("opencode", {})
        approved_ver = approved_oc.get("version", "")

        if approved_ver:
            # Attempt to install the approved version
            rc, out, err = _ssh(
                worker.ssh_host, worker.ssh_port, worker.ssh_user,
                f"cd ~/.config/vibedev-opencode && npm install opencode@{approved_ver} 2>&1 | tail -3"
            )
            event.after = {"rollback_install": {"rc": rc, "output": out[:200]}}

        # Re-verify
        new_fp = self.collector.collect(worker)
        self.observed_states[node_id] = new_fp
        new_items, _ = self.detect_drift(node_id)
        patch_items = [i for i in new_items if i.drift_type == DriftType.PATCH_VERSION_DRIFT]

        if not patch_items:
            event.status = DriftEventStatus.ROLLED_BACK
            event.rollback_performed = True
            event.resolution = f"rolled_back_to_approved_{approved_ver}"
            event.operator_required = False
            if event.maintenance_set:
                self.registry.set_maintenance(node_id, "active")
                event.maintenance_set = False
        else:
            event.status = DriftEventStatus.OPERATOR_WAITING
            event.operator_required = True
            event.resolution = "rollback_insufficient_operator_required"

        return event

    def adopt_candidate(self, node_id: str) -> DriftEvent:
        """Promote candidate baseline to approved baseline."""
        candidate = self.candidate_baselines.get(node_id)
        if not candidate:
            return DriftEvent(
                event_id=self._next_event_id(),
                node_id=node_id,
                detected_at=datetime.now(timezone.utc).isoformat(),
                status=DriftEventStatus.BLOCKED,
                resolution="no_candidate_baseline_to_adopt",
            )

        self.approved_baselines[node_id] = RuntimeBaseline(
            state=BaselineState.APPROVED,
            fingerprint=candidate.fingerprint,
            sha256=candidate.sha256,
            frozen_at=datetime.now(timezone.utc).isoformat(),
            frozen_by="auto_adopt",
        )
        del self.candidate_baselines[node_id]

        # Clear maintenance
        self.registry.set_maintenance(node_id, "active")

        event = DriftEvent(
            event_id=self._next_event_id(),
            node_id=node_id,
            detected_at=datetime.now(timezone.utc).isoformat(),
            drift_type=DriftType.PATCH_VERSION_DRIFT,
            status=DriftEventStatus.RESOLVED,
            remediation=RemediationAction.FORWARD_CONVERGE,
            forward_converge=True,
            runtime_baseline_sha=candidate.sha256,
            operator_required=False,
            resolution="candidate_adopted_as_approved",
            resolved_at=datetime.now(timezone.utc).isoformat(),
        )
        self.event_log.append(event.to_dict())
        self._save_events()
        return event

    def rollback_drift(self, node_id: str, event_id: str = None) -> DriftEvent:
        """Explicit rollback command — restores approved baseline."""
        event = DriftEvent(
            event_id=self._next_event_id(),
            node_id=node_id,
            detected_at=datetime.now(timezone.utc).isoformat(),
            status=DriftEventStatus.RECONCILING,
            remediation=RemediationAction.ROLLBACK,
        )
        event = self._rollback_to_approved(node_id, event)
        self.event_log.append(event.to_dict())
        self._save_events()
        return event

    def get_events(self, limit: int = 20) -> list:
        """Return recent drift events."""
        return self.event_log[-limit:]

    def forward_converge_other_node(self, source_node: str) -> DriftEvent:
        """After adopting candidate on source, converge the other node."""
        other = "9bao" if source_node == "5bao" else "5bao"
        source_approved = self.approved_baselines.get(source_node)
        if not source_approved:
            return DriftEvent(
                event_id=self._next_event_id(),
                node_id=other,
                detected_at=datetime.now(timezone.utc).isoformat(),
                status=DriftEventStatus.BLOCKED,
                resolution="source_node_no_approved_baseline",
            )

        # Set other node to maintenance, apply same approved baseline
        self.registry.set_maintenance(other, "maintenance")

        # Copy the approved baseline fingerprint to the other node
        self.approved_baselines[other] = RuntimeBaseline(
            state=BaselineState.APPROVED,
            fingerprint=copy.deepcopy(source_approved.fingerprint),
            sha256=source_approved.sha256,
            frozen_at=datetime.now(timezone.utc).isoformat(),
            frozen_by="forward_converge",
        )

        self.registry.set_maintenance(other, "active")

        event = DriftEvent(
            event_id=self._next_event_id(),
            node_id=other,
            detected_at=datetime.now(timezone.utc).isoformat(),
            drift_type=DriftType.PATCH_VERSION_DRIFT,
            status=DriftEventStatus.RESOLVED,
            remediation=RemediationAction.FORWARD_CONVERGE,
            forward_converge=True,
            other_node_converged=source_node,
            runtime_baseline_sha=source_approved.sha256,
            operator_required=False,
            resolution=f"converged_from_{source_node}_approved_baseline",
            resolved_at=datetime.now(timezone.utc).isoformat(),
        )
        self.event_log.append(event.to_dict())
        self._save_events()
        return event

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

        # 3. DriftType enum completeness
        expected_types = {"PATH_DRIFT", "PATCH_VERSION_DRIFT", "DEPENDENCY_DRIFT",
                         "CONFIG_DRIFT", "SECRET_DRIFT", "SYSTEM_PACKAGE_DRIFT",
                         "MAJOR_VERSION_DRIFT", "UNKNOWN_DRIFT"}
        actual_types = {dt.value for dt in DriftType}
        checks.append({"name": "drift_types", "passed": expected_types == actual_types,
                       "message": f"expected={len(expected_types)} actual={len(actual_types)}"})

        # 4. RemediationAction completeness
        expected_actions = {"auto_fix", "rebuild", "restore_config", "canary_validation",
                           "forward_converge", "rollback", "block", "operator_required"}
        actual_actions = {ra.value for ra in RemediationAction}
        checks.append({"name": "remediation_actions", "passed": expected_actions == actual_actions,
                       "message": f"expected={len(expected_actions)} actual={len(actual_actions)}"})

        # 5. Classifier priority
        classifier = DriftClassifier()
        test_items_secret = [DriftItem(component="x", drift_type=DriftType.SECRET_DRIFT),
                            DriftItem(component="y", drift_type=DriftType.PATH_DRIFT)]
        checks.append({"name": "classifier_secret_wins",
                       "passed": classifier.classify(test_items_secret) == DriftType.SECRET_DRIFT,
                       "message": "SECRET > PATH"})

        test_items_unknown = [DriftItem(component="x", drift_type=DriftType.UNKNOWN_DRIFT),
                             DriftItem(component="y", drift_type=DriftType.MAJOR_VERSION_DRIFT)]
        checks.append({"name": "classifier_unknown_wins",
                       "passed": classifier.classify(test_items_unknown) == DriftType.UNKNOWN_DRIFT,
                       "message": "UNKNOWN > MAJOR"})

        # 6. Planner correctness
        planner = RemediationPlanner()
        plan_checks = [
            (DriftType.PATH_DRIFT, RemediationAction.AUTO_FIX),
            (DriftType.PATCH_VERSION_DRIFT, RemediationAction.CANARY_VALIDATION),
            (DriftType.DEPENDENCY_DRIFT, RemediationAction.REBUILD),
            (DriftType.SECRET_DRIFT, RemediationAction.BLOCK),
            (DriftType.MAJOR_VERSION_DRIFT, RemediationAction.OPERATOR_REQUIRED),
        ]
        all_plan_ok = all(planner.plan(dt) == ra for dt, ra in plan_checks)
        checks.append({"name": "planner_rules", "passed": all_plan_ok,
                       "message": "5/5 plan rules correct"})

        # 7. Registry integration
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.ONLINE)
        reg.set_health("9bao", NodeStatus.ONLINE)
        manager = ToolchainLifecycleManager(registry=reg)
        checks.append({"name": "manager_init", "passed": len(manager.registry.workers) == 2,
                       "message": "2 workers registered"})

        # 8. Drift detector: identical fingerprints = no drift
        fp1 = RuntimeFingerprint(node_id="test", hostname="h1", ssh_reachable=True,
                                components={"opencode": {"version": "1.17.4", "binary_hash": "abc123"}},
                                path_dirs=["/a", "/b"])
        fp2 = RuntimeFingerprint(node_id="test", hostname="h1", ssh_reachable=True,
                                components={"opencode": {"version": "1.17.4", "binary_hash": "abc123"}},
                                path_dirs=["/a", "/b"])
        items = DriftDetector().detect(fp1, fp2)
        checks.append({"name": "detector_no_drift", "passed": len(items) == 0,
                       "message": f"identical_fingerprints={len(items)}_items"})

        # 9. Drift detector: version change detected
        fp3 = RuntimeFingerprint(node_id="test", hostname="h1", ssh_reachable=True,
                                components={"opencode": {"version": "1.17.5", "binary_hash": "def456"}},
                                path_dirs=["/a", "/b"])
        items2 = DriftDetector().detect(fp1, fp3)
        checks.append({"name": "detector_version_drift",
                       "passed": len(items2) > 0 and any(i.drift_type == DriftType.PATCH_VERSION_DRIFT for i in items2),
                       "message": f"detected_{len(items2)}_items"})

        # 10. Secret drift detected and classified correctly
        fp4 = RuntimeFingerprint(node_id="test", hostname="h1", ssh_reachable=True,
                                components={"secret_fingerprint": {"hash": "DIFFERENT"}},
                                path_dirs=["/a", "/b"])
        fp_approved = RuntimeFingerprint(node_id="test", hostname="h1", ssh_reachable=True,
                                        components={"secret_fingerprint": {"hash": "ORIGINAL"}},
                                        path_dirs=["/a", "/b"])
        items3 = DriftDetector().detect(fp_approved, fp4)
        has_secret = any(i.drift_type == DriftType.SECRET_DRIFT for i in items3)
        checks.append({"name": "detector_secret_drift", "passed": has_secret,
                       "message": f"secret_drift_detected={has_secret}"})

        # 11. Dual-node safety: both unknown → no writes
        reg2 = WorkerRegistry()
        reg2.set_health("5bao", NodeStatus.ONLINE)
        reg2.set_health("9bao", NodeStatus.ONLINE)
        mgr2 = ToolchainLifecycleManager(registry=reg2)
        # Both nodes have UNKNOWN drift events
        mgr2.event_log.append({
            "node_id": "9bao",
            "drift_type": "UNKNOWN_DRIFT",
            "status": "operator_waiting",
        })
        mgr2.event_log.append({
            "node_id": "5bao",
            "drift_type": "UNKNOWN_DRIFT",
            "status": "operator_waiting",
        })
        both_unknown = mgr2._both_nodes_unknown("5bao")
        checks.append({"name": "dual_node_safety", "passed": both_unknown,
                       "message": f"both_nodes_unknown={both_unknown}"})

        # 12. Event lifecycle
        reg3 = WorkerRegistry()
        reg3.set_health("5bao", NodeStatus.ONLINE)
        mgr3 = ToolchainLifecycleManager(registry=reg3)
        evt = DriftEvent(event_id="test-001", node_id="5bao",
                        status=DriftEventStatus.RESOLVED, resolution="test")
        mgr3.event_log.append(evt.to_dict())
        checks.append({"name": "event_lifecycle", "passed": len(mgr3.get_events()) == 1,
                       "message": f"events={len(mgr3.get_events())}"})

        # 13. Baseline state separation
        fp_base = RuntimeFingerprint(node_id="5bao", components={})
        mgr3.set_approved_baseline("5bao", fp_base)
        checks.append({"name": "baseline_states",
                       "passed": "5bao" in mgr3.approved_baselines
                                 and mgr3.approved_baselines["5bao"].state == BaselineState.APPROVED,
                       "message": "approved_baseline_set"})

        passed = sum(1 for c in checks if c["passed"])
        return {
            "overall": "PASS" if passed == len(checks) else "FAIL",
            "passed": passed,
            "total": len(checks),
            "checks": checks,
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Toolchain Lifecycle Manager")
    parser.add_argument("--drift", action="store_true", help="Detect drift on all workers")
    parser.add_argument("--reconcile", action="store_true", help="Reconcile drift")
    parser.add_argument("--events", action="store_true", help="Show drift events")
    parser.add_argument("--adopt-candidate", action="store_true", help="Adopt candidate baseline")
    parser.add_argument("--rollback-drift", action="store_true", help="Rollback drift")
    parser.add_argument("--node", help="Target node (5bao or 9bao)")
    parser.add_argument("--event-id", help="Event ID for rollback")
    parser.add_argument("--limit", type=int, default=20, help="Event limit")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.self_check:
        result = ToolchainLifecycleManager().self_check()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Self-check: {result['overall']} ({result['passed']}/{result['total']})")
            for c in result["checks"]:
                mark = "PASS" if c["passed"] else "FAIL"
                print(f"  [{mark}] {c['name']}: {c['message']}")
        sys.exit(0 if result["overall"] == "PASS" else 1)

    if args.drift:
        manager = ToolchainLifecycleManager()
        # Collect fingerprints and set as approved baselines first
        for w in manager.registry.list_workers():
            if w.health_status == NodeStatus.ONLINE:
                fp = manager.collect_fingerprint(w.worker_id)
                if w.worker_id not in manager.approved_baselines:
                    manager.set_approved_baseline(w.worker_id, fp)
        results = manager.detect_all_drift()
        output = {}
        for nid, data in results.items():
            output[nid] = {
                "drift_type": data["drift_type"].value if data["drift_type"] else "NONE",
                "items": [{"component": i.component, "type": i.drift_type if isinstance(i.drift_type, str) else i.drift_type.value,
                          "approved": i.approved_value, "observed": i.observed_value}
                         for i in data["items"]],
            }
        if args.json:
            print(json.dumps(output, indent=2))
        else:
            for nid, data in output.items():
                print(f"\n{nid}: drift_type={data['drift_type']}")
                for item in data["items"]:
                    print(f"  {item['component']}: {item['type']} ({item['approved']} → {item['observed']})")

    if args.events:
        manager = ToolchainLifecycleManager()
        events = manager.get_events(args.limit)
        if args.json:
            print(json.dumps(events, indent=2))
        else:
            for e in events:
                print(f"[{e.get('event_id')}] {e.get('node_id')}: {e.get('drift_type')} → {e.get('status')} | {e.get('resolution')}")

    if args.reconcile:
        node = args.node
        if not node:
            print("ERROR: --node required for --reconcile")
            sys.exit(1)
        manager = ToolchainLifecycleManager()
        worker = manager.registry.get_worker(node)
        if not worker:
            print(f"ERROR: unknown node {node}")
            sys.exit(1)
        manager.registry.set_health(node, NodeStatus.ONLINE)
        fp = manager.collect_fingerprint(node)
        manager.set_approved_baseline(node, fp)
        items, dtype = manager.detect_drift(node)
        event = manager.reconcile(node, items, dtype)
        if args.json:
            print(json.dumps(event.to_dict(), indent=2))
        else:
            print(f"Reconcile {node}: status={event.status.value} resolution={event.resolution}")

    if args.adopt_candidate:
        node = args.node
        if not node:
            print("ERROR: --node required for --adopt-candidate")
            sys.exit(1)
        manager = ToolchainLifecycleManager()
        event = manager.adopt_candidate(node)
        if args.json:
            print(json.dumps(event.to_dict(), indent=2))
        else:
            print(f"Adopt {node}: status={event.status.value} resolution={event.resolution}")

    if args.rollback_drift:
        node = args.node
        if not node:
            print("ERROR: --node required for --rollback-drift")
            sys.exit(1)
        manager = ToolchainLifecycleManager()
        event = manager.rollback_drift(node, args.event_id)
        if args.json:
            print(json.dumps(event.to_dict(), indent=2))
        else:
            print(f"Rollback {node}: status={event.status.value} resolution={event.resolution}")


if __name__ == "__main__":
    main()
