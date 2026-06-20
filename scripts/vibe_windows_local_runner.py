#!/usr/bin/env python3
"""vibe_windows_local_runner.py — Windows local job runner for 21bao v1.0.0

Runs opencode jobs locally on the Windows 21bao worker.
Uses E:\vibedev-worktrees\21bao\ for worktrees,
       D:\vibedev-evidence\21bao\ for evidence,
       D:\vibedev-logs\21bao\ for logs.

Safety:
  - NEVER writes to controller repo (C:\\Users\\KK\\vibe-coding-repo)
  - Path allowlist: only D:\\ and E:\\ drives allowed
  - Supports timeout, cancellation (taskkill), dry-run, no-op fixture

Usage:
    python3 scripts/vibe_windows_local_runner.py --job-id test-001 --branch feat/test --task implementer
    python3 scripts/vibe_windows_local_runner.py --self-check
    python3 scripts/vibe_windows_local_runner.py --dry-run --job-id test-001 --branch feat/test --task implementer
"""

__version__ = "1.0.0"

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# --- Constants ---

WORKTREE_ROOT = r"E:\vibedev-worktrees\21bao"
EVIDENCE_ROOT = r"D:\vibedev-evidence\21bao"
LOG_ROOT = r"D:\vibedev-logs\21bao"
WRAPPER_PATH = r"D:\vibedev-tools\bin\opencode-21bao.ps1"

# Path allowlist: only D:\ and E:\ are allowed for worktrees/evidence/logs
ALLOWED_PREFIXES = (r"D:\\", r"E:\\")
# Blocked paths: controller repo must never be written to
# V1.20.18: Added profile-scoped path + canonical path resolution
_CONTROLLER_REPO_PATHS = [
    r"C:\Users\KK\vibe-coding-repo",
    r"C:\Users\KK\AppData\Local\hermes\profiles\vibedev\home\vibe-coding-repo",
]
BLOCKED_PREFIXES = tuple(
    p for p in _CONTROLLER_REPO_PATHS
) + tuple(
    p + "\\" for p in _CONTROLLER_REPO_PATHS
)

DEFAULT_TIMEOUT_S = 1800  # 30 minutes
LOCK_DIR = Path(tempfile.gettempdir()) / "vibedev-locks"
LOCK_DIR.mkdir(parents=True, exist_ok=True)


# --- Data classes ---

@dataclass
class JobSpec:
    job_id: str
    branch: str
    task: str  # implementer, reviewer, etc.
    timeout_s: int = DEFAULT_TIMEOUT_S
    dry_run: bool = False
    no_op: bool = False  # fixture mode: return immediately with mock result
    extra_args: list = field(default_factory=list)


@dataclass
class JobResult:
    job_id: str
    branch: str
    task: str
    status: str  # success, failed, timeout, cancelled, dry_run, no_op
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    evidence_path: str = ""
    log_path: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "branch": self.branch,
            "task": self.task,
            "status": self.status,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:2000],
            "stderr": self.stderr[:2000],
            "duration_s": round(self.duration_s, 2),
            "evidence_path": self.evidence_path,
            "log_path": self.log_path,
            "timestamp": self.timestamp,
        }


# --- Path validation ---

def _canonicalize(path: str) -> str:
    """Canonicalize a Windows path for safe comparison.

    Handles: case normalization, forward/backward slash, relative paths,
    .. traversal, trailing slashes, drive letter normalization.
    Returns lowercased, fully resolved absolute path.
    """
    # Resolve relative paths, symlinks, junctions
    try:
        resolved = os.path.realpath(os.path.abspath(path))
    except (OSError, ValueError):
        # If we can't resolve, use normpath as fallback
        resolved = os.path.normpath(os.path.abspath(path))
    # Lowercase for case-insensitive Windows comparison
    return resolved.lower()


def is_path_allowed(path: str) -> bool:
    """Check if a path is in the allowlist (D:\\ or E:\\ only)."""
    canonical = _canonicalize(path)
    for prefix in ALLOWED_PREFIXES:
        canon_prefix = _canonicalize(prefix)
        if canonical.startswith(canon_prefix):
            return True
    return False


def is_path_blocked(path: str) -> bool:
    """Check if a path is explicitly blocked (controller repo).

    Uses canonical path resolution to prevent bypass via:
    - case differences (c:/Users vs C:/Users)
    - forward slashes (C:/Users/KK/...)
    - relative paths / .. traversal
    - trailing slashes
    - symlinks / junctions
    """
    canonical = _canonicalize(path)
    for prefix in BLOCKED_PREFIXES:
        canon_prefix = _canonicalize(prefix)
        if canonical.startswith(canon_prefix):
            return True
    return False


def validate_path(path: str) -> tuple[bool, str]:
    """Validate a path against allowlist and blocklist. Returns (ok, reason).

    Fail-closed: blocklist check first, then allowlist.
    Any path that can't be safely canonicalized is rejected.
    """
    # Fail-closed: try canonicalization, reject on failure
    try:
        canonical = _canonicalize(path)
    except Exception:
        return False, f"blocked: cannot canonicalize path ({path})"

    # Blocklist check first (higher priority)
    if is_path_blocked(path):
        return False, f"blocked: path is in controller repo ({path})"

    # Allowlist check
    if not is_path_allowed(path):
        return False, f"blocked: path not in allowlist D:\\ or E:\\ ({path})"

    return True, "ok"


# --- Job lock ---

class JobLock:
    """Simple file-based job lock to prevent concurrent execution."""

    def __init__(self, job_id: str):
        self.lock_file = LOCK_DIR / f"vibedev-local-{job_id}.lock"
        self._fd = None

    def acquire(self) -> bool:
        """Try to acquire lock. Returns False if already locked."""
        if self.lock_file.exists():
            # Check if lock is stale (> 1 hour old)
            try:
                age = time.time() - self.lock_file.stat().st_mtime
                if age > 3600:
                    self.lock_file.unlink(missing_ok=True)
                else:
                    return False
            except OSError:
                return False
        try:
            self.lock_file.write_text(json.dumps({
                "job_id": self.lock_file.stem,
                "acquired_at": datetime.now(timezone.utc).isoformat(),
                "pid": os.getpid(),
            }))
            self._fd = open(self.lock_file, "r")
            return True
        except OSError:
            return False

    def release(self):
        """Release the lock."""
        try:
            if self._fd:
                self._fd.close()
                self._fd = None
            self.lock_file.unlink(missing_ok=True)
        except OSError:
            pass


# --- Runner ---

def run_job(spec: JobSpec) -> JobResult:
    """Execute a local job on the 21bao worker.

    Never writes to the controller repo. All paths are validated against
    the allowlist (D:\\, E:\\) and blocklist (controller repo).
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # No-op fixture mode
    if spec.no_op:
        return JobResult(
            job_id=spec.job_id, branch=spec.branch, task=spec.task,
            status="no_op", exit_code=0,
            stdout="no-op fixture: returning mock success",
            duration_s=0.0,
            timestamp=timestamp,
        )

    # Validate paths
    worktree = os.path.join(WORKTREE_ROOT, spec.branch)
    evidence_dir = os.path.join(EVIDENCE_ROOT, spec.branch)
    log_dir = os.path.join(LOG_ROOT, spec.branch)

    for label, p in [("worktree", worktree), ("evidence", evidence_dir), ("log", log_dir)]:
        ok, reason = validate_path(p)
        if not ok:
            return JobResult(
                job_id=spec.job_id, branch=spec.branch, task=spec.task,
                status="failed", exit_code=1,
                stderr=f"path_validation_failed: {label}={p}: {reason}",
                timestamp=timestamp,
            )

    # Dry-run mode: return paths but don't execute
    if spec.dry_run:
        return JobResult(
            job_id=spec.job_id, branch=spec.branch, task=spec.task,
            status="dry_run", exit_code=0,
            stdout=json.dumps({
                "would_execute": True,
                "wrapper": WRAPPER_PATH,
                "worktree": worktree,
                "evidence_dir": evidence_dir,
                "log_dir": log_dir,
                "timeout_s": spec.timeout_s,
                "task": spec.task,
                "branch": spec.branch,
            }, indent=2),
            evidence_path=evidence_dir,
            log_path=log_dir,
            duration_s=0.0,
            timestamp=timestamp,
        )

    # Acquire job lock
    lock = JobLock(spec.job_id)
    if not lock.acquire():
        return JobResult(
            job_id=spec.job_id, branch=spec.branch, task=spec.task,
            status="failed", exit_code=1,
            stderr=f"job_lock_held: another instance is running job {spec.job_id}",
            timestamp=timestamp,
        )

    try:
        # Ensure directories exist
        os.makedirs(evidence_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)

        # Build command
        cmd = [
            "powershell", "-ExecutionPolicy", "Bypass",
            "-File", WRAPPER_PATH,
            "--branch", spec.branch,
            "--task", spec.task,
            "--evidence-dir", evidence_dir,
            "--log-dir", log_dir,
        ] + spec.extra_args

        start = time.monotonic()
        proc = None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            stdout, stderr = proc.communicate(timeout=spec.timeout_s)
            elapsed = time.monotonic() - start

            # Write evidence
            evidence_file = os.path.join(evidence_dir, f"{spec.job_id}.json")
            with open(evidence_file, "w") as f:
                json.dump({
                    "job_id": spec.job_id,
                    "branch": spec.branch,
                    "task": spec.task,
                    "exit_code": proc.returncode,
                    "stdout": stdout[:5000],
                    "stderr": stderr[:5000],
                    "duration_s": round(elapsed, 2),
                    "timestamp": timestamp,
                }, f, indent=2)

            # Write log
            log_file = os.path.join(log_dir, f"{spec.job_id}.log")
            with open(log_file, "w") as f:
                f.write(f"=== STDOUT ===\n{stdout}\n=== STDERR ===\n{stderr}\n")

            status = "success" if proc.returncode == 0 else "failed"
            return JobResult(
                job_id=spec.job_id, branch=spec.branch, task=spec.task,
                status=status, exit_code=proc.returncode,
                stdout=stdout, stderr=stderr,
                duration_s=elapsed,
                evidence_path=evidence_file,
                log_path=log_file,
                timestamp=timestamp,
            )

        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start
            if proc:
                try:
                    # Kill the process tree on Windows
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True, timeout=10,
                    )
                except Exception:
                    pass
                try:
                    proc.kill()
                except Exception:
                    pass
            return JobResult(
                job_id=spec.job_id, branch=spec.branch, task=spec.task,
                status="timeout", exit_code=-1,
                stderr=f"job timed out after {spec.timeout_s}s",
                duration_s=elapsed,
                timestamp=timestamp,
            )

    finally:
        lock.release()


# --- Self-check ---

def self_check() -> dict:
    """Self-check: verify runner structure and path validation."""
    checks = []
    passed = True

    # Check 1: Path allowlist allows D:\
    try:
        ok, _ = validate_path(r"D:\vibedev-evidence\21bao\test")
        assert ok, "D:\\ should be allowed"
        checks.append({"name": "path_allowlist_drive_d", "passed": True})
    except Exception as e:
        checks.append({"name": "path_allowlist_drive_d", "passed": False, "error": str(e)})
        passed = False

    # Check 2: Path allowlist allows E:\
    try:
        ok, _ = validate_path(r"E:\vibedev-worktrees\21bao\test")
        assert ok, "E:\\ should be allowed"
        checks.append({"name": "path_allowlist_drive_e", "passed": True})
    except Exception as e:
        checks.append({"name": "path_allowlist_drive_e", "passed": False, "error": str(e)})
        passed = False

    # Check 3: Path allowlist blocks controller repo
    try:
        ok, reason = validate_path(r"C:\Users\KK\vibe-coding-repo\.git")
        assert not ok, "Controller repo should be blocked"
        assert "blocked" in reason
        checks.append({"name": "path_blocklist_controller", "passed": True})
    except Exception as e:
        checks.append({"name": "path_blocklist_controller", "passed": False, "error": str(e)})
        passed = False

    # Check 4: Path allowlist blocks C:\ in general
    try:
        ok, _ = validate_path(r"C:\Windows\System32")
        assert not ok, "C:\\ should be blocked"
        checks.append({"name": "path_blocklist_drive_c", "passed": True})
    except Exception as e:
        checks.append({"name": "path_blocklist_drive_c", "passed": False, "error": str(e)})
        passed = False

    # Check 5: Dry-run mode
    try:
        spec = JobSpec(job_id="check-dry", branch="feat/test", task="implementer", dry_run=True)
        result = run_job(spec)
        assert result.status == "dry_run"
        assert result.exit_code == 0
        assert "would_execute" in result.stdout
        checks.append({"name": "dry_run_mode", "passed": True})
    except Exception as e:
        checks.append({"name": "dry_run_mode", "passed": False, "error": str(e)})
        passed = False

    # Check 6: No-op fixture mode
    try:
        spec = JobSpec(job_id="check-noop", branch="feat/test", task="implementer", no_op=True)
        result = run_job(spec)
        assert result.status == "no_op"
        assert result.exit_code == 0
        checks.append({"name": "no_op_fixture", "passed": True})
    except Exception as e:
        checks.append({"name": "no_op_fixture", "passed": False, "error": str(e)})
        passed = False

    # Check 7: JobResult serialization
    try:
        result = JobResult(
            job_id="check-serial", branch="feat/test", task="implementer",
            status="success", exit_code=0, timestamp="2026-01-01T00:00:00Z",
        )
        d = result.to_dict()
        assert d["job_id"] == "check-serial"
        assert d["status"] == "success"
        checks.append({"name": "job_result_serialization", "passed": True})
    except Exception as e:
        checks.append({"name": "job_result_serialization", "passed": False, "error": str(e)})
        passed = False

    # Check 8: Constants are correct
    try:
        assert WORKTREE_ROOT == r"E:\vibedev-worktrees\21bao"
        assert EVIDENCE_ROOT == r"D:\vibedev-evidence\21bao"
        assert LOG_ROOT == r"D:\vibedev-logs\21bao"
        assert WRAPPER_PATH == r"D:\vibedev-tools\bin\opencode-21bao.ps1"
        checks.append({"name": "constants_correct", "passed": True})
    except Exception as e:
        checks.append({"name": "constants_correct", "passed": False, "error": str(e)})
        passed = False

    # Check 9: No-op never touches filesystem
    try:
        spec = JobSpec(job_id="check-no-fs", branch="feat/test", task="implementer", no_op=True)
        result = run_job(spec)
        assert result.evidence_path == ""
        assert result.log_path == ""
        checks.append({"name": "no_op_no_filesystem", "passed": True})
    except Exception as e:
        checks.append({"name": "no_op_no_filesystem", "passed": False, "error": str(e)})
        passed = False

    # Check 10: Version present
    try:
        assert __version__ == "1.0.0"
        checks.append({"name": "version_check", "passed": True})
    except Exception as e:
        checks.append({"name": "version_check", "passed": False, "error": str(e)})
        passed = False

    # V1.20.18: Check 11-17: Controller repo blocklist gap closure
    _ctrl_profile = r"C:\Users\KK\AppData\Local\hermes\profiles\vibedev\home\vibe-coding-repo"

    # Check 11: Profile-scoped controller repo blocked
    try:
        ok, _ = validate_path(_ctrl_profile + r"\scripts\test.py")
        assert not ok, "Profile-scoped controller repo should be blocked"
        checks.append({"name": "blocklist_profile_scoped", "passed": True})
    except Exception as e:
        checks.append({"name": "blocklist_profile_scoped", "passed": False, "error": str(e)})
        passed = False

    # Check 12: Case-insensitive bypass blocked
    try:
        ok, _ = validate_path(_ctrl_profile.upper() + r"\test")
        assert not ok, "Uppercase controller repo should be blocked"
        checks.append({"name": "blocklist_case_insensitive", "passed": True})
    except Exception as e:
        checks.append({"name": "blocklist_case_insensitive", "passed": False, "error": str(e)})
        passed = False

    # Check 13: Forward slash bypass blocked
    try:
        fwd = _ctrl_profile.replace("\\", "/") + "/test"
        ok, _ = validate_path(fwd)
        assert not ok, "Forward slash controller repo should be blocked"
        checks.append({"name": "blocklist_forward_slash", "passed": True})
    except Exception as e:
        checks.append({"name": "blocklist_forward_slash", "passed": False, "error": str(e)})
        passed = False

    # Check 14: Path traversal with .. blocked
    try:
        traversal = os.path.normpath(_ctrl_profile + "/../../../" + _ctrl_profile)
        ok, _ = validate_path(traversal)
        assert not ok, "Path traversal should be blocked"
        checks.append({"name": "blocklist_path_traversal", "passed": True})
    except Exception as e:
        checks.append({"name": "blocklist_path_traversal", "passed": False, "error": str(e)})
        passed = False

    # Check 15: Trailing slash bypass blocked
    try:
        ok, _ = validate_path(_ctrl_profile + r"\\")
        assert not ok, "Trailing slash controller repo should be blocked"
        checks.append({"name": "blocklist_trailing_slash", "passed": True})
    except Exception as e:
        checks.append({"name": "blocklist_trailing_slash", "passed": False, "error": str(e)})
        passed = False

    # Check 16: Old path still blocked
    try:
        ok, _ = validate_path(r"C:\Users\KK\vibe-coding-repo\test")
        assert not ok, "Old controller repo path should still be blocked"
        checks.append({"name": "blocklist_old_path_still_blocked", "passed": True})
    except Exception as e:
        checks.append({"name": "blocklist_old_path_still_blocked", "passed": False, "error": str(e)})
        passed = False

    # Check 17: D/E paths remain allowed after blocklist update
    try:
        ok_d, _ = validate_path(r"D:\vibedev-test-new")
        ok_e, _ = validate_path(r"E:\vibedev-test-new")
        assert ok_d, "D drive should still be allowed"
        assert ok_e, "E drive should still be allowed"
        checks.append({"name": "allowlist_de_unchanged", "passed": True})
    except Exception as e:
        checks.append({"name": "allowlist_de_unchanged", "passed": False, "error": str(e)})
        passed = False

    return {"passed": passed, "version": __version__, "checks": checks}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="VibeDev Windows Local Runner (21bao)")
    parser.add_argument("--job-id", help="Job identifier")
    parser.add_argument("--branch", help="Branch name")
    parser.add_argument("--task", default="implementer", help="Task type")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="Timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode")
    parser.add_argument("--no-op", action="store_true", help="No-op fixture mode")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    if not args.job_id or not args.branch:
        parser.error("--job-id and --branch are required")

    spec = JobSpec(
        job_id=args.job_id,
        branch=args.branch,
        task=args.task,
        timeout_s=args.timeout,
        dry_run=args.dry_run,
        no_op=args.no_op,
    )
    result = run_job(spec)
    print(json.dumps(result.to_dict(), indent=2))
    sys.exit(0 if result.status in ("success", "dry_run", "no_op") else 1)


if __name__ == "__main__":
    main()
