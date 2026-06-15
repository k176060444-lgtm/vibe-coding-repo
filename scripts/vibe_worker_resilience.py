#!/usr/bin/env python3
"""Worker Reachability & Resilience — state classification, retry, checkpoint, resume.

Classifies worker reachability, implements retry/report/checkpoint/resume
for batch-runner when worker is temporarily unreachable.

Usage:
    python3 scripts/vibe_worker_resilience.py --check [--json] [--compact]
    python3 scripts/vibe_worker_resilience.py --checkpoint <file> [--json]
    python3 scripts/vibe_worker_resilience.py --resume <file> [--json] [--compact]
    python3 scripts/vibe_worker_resilience.py --status-report <file> [--json]
    python3 scripts/vibe_worker_resilience.py --reconcile <file> [--json] [--compact]

Constraints:
    - Read-only on repo; checkpoint file is the only write target.
    - No token read, no git mutation.
    - Standard library only.
    - No IO on import.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

VERSION = "1.1.0"

RETRY_INTERVAL_MINUTES = 5
MAX_WAIT_MINUTES = 75
MAX_RETRY_COUNT = 15
REPORT_INTERVAL_MINUTES = 15

SELF_REPO = "k176060444-lgtm/vibe-coding-repo"


def _run_cmd(cmd, timeout=15):
    """Run a command and return (rc, stdout, stderr)."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except OSError as e:
        return -1, "", str(e)


def _check_worker_reachable():
    """Check if Debian worker is reachable via SSH.

    Returns (status: str, error: str|None).
    """
    ssh_key = os.path.expanduser("~") + "/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519"
    cmd = [
        "ssh", "-i", ssh_key,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-p", "22222",
        "vibeworker@192.168.5.6",
        "echo WORKER_OK",
    ]
    rc, stdout, stderr = _run_cmd(cmd, timeout=20)

    if rc == 0 and "WORKER_OK" in stdout:
        return "reachable", None
    if "timed out" in stderr.lower() or "timeout" in stderr.lower():
        return "unreachable_timeout", "SSH connection timed out (VPN suspected down)"
    if "refused" in stderr.lower():
        return "unreachable_refused", "SSH connection refused (service not running)"
    return "unknown", f"rc={rc} stderr={stderr[:200]}"


def _get_current_baseline():
    """Get current git baseline SHA (read-only)."""
    rc, stdout, stderr = _run_cmd(["git", "rev-parse", "HEAD"])
    if rc == 0:
        return stdout
    return None


def _check_worktree_clean():
    """Check if worktree is clean (no uncommitted changes)."""
    rc, stdout, stderr = _run_cmd(["git", "status", "--porcelain"])
    if rc == 0 and not stdout:
        return True
    return False


def _cmd_check(args):
    """Check worker reachability."""
    status, error = _check_worker_reachable()
    result = {
        "worker_status": status,
        "worker_error": error,
        "reachable": status == "reachable",
        "check_time": time.time(),
    }

    if status != "reachable":
        result["recommended_action"] = "WAITING_WORKER_RECOVERY"
        result["retry_interval_minutes"] = RETRY_INTERVAL_MINUTES
        result["max_wait_minutes"] = MAX_WAIT_MINUTES
        result["max_retry_count"] = MAX_RETRY_COUNT
        result["next_retry_recommended"] = True
    else:
        result["recommended_action"] = "PROCEED"

    return result, 0 if status == "reachable" else 1


def _load_checkpoint(checkpoint_path):
    """Load checkpoint file."""
    p = Path(checkpoint_path)
    if not p.exists():
        return None, f"Checkpoint not found: {checkpoint_path}"
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f), None
    except (json.JSONDecodeError, OSError) as e:
        return None, f"Failed to load checkpoint: {e}"


def _save_checkpoint(checkpoint_path, data):
    """Save checkpoint file atomically."""
    p = Path(checkpoint_path)
    tmp = p.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(p)
        return None
    except OSError as e:
        return str(e)


def _cmd_checkpoint(args):
    """Create or update a batch checkpoint."""
    checkpoint_path = args.checkpoint
    now = time.time()

    existing, _ = _load_checkpoint(checkpoint_path)
    if existing:
        existing["last_updated"] = now
        existing["retry_count"] = existing.get("retry_count", 0)
        err = _save_checkpoint(checkpoint_path, existing)
        if err:
            return {"error": err}, 1
        return existing, 0

    # Create new checkpoint
    checkpoint = {
        "batch_id": "pending",
        "status": "WAITING_WORKER_RECOVERY",
        "current_wo": None,
        "phase": "before_any_mutation",
        "baseline_before": None,
        "baseline_after": None,
        "branch": None,
        "pr": None,
        "changed_paths": [],
        "last_safe_point": now,
        "resume_allowed": True,
        "worker_error": None,
        "retry_count": 0,
        "first_unreachable_at": now,
        "last_retry_at": None,
        "next_retry_at": now + RETRY_INTERVAL_MINUTES * 60,
        "created_at": now,
        "last_updated": now,
    }
    err = _save_checkpoint(checkpoint_path, checkpoint)
    if err:
        return {"error": err}, 1
    return checkpoint, 0


def _cmd_pause(args):
    """Pause batch at safe point — writes PAUSED checkpoint."""
    checkpoint_path = args.pause
    now = time.time()

    existing, err = _load_checkpoint(checkpoint_path)
    if existing:
        existing["status"] = "PAUSED"
        existing["paused_at"] = now
        existing["last_updated"] = now
        existing["resume_allowed"] = True
        err = _save_checkpoint(checkpoint_path, existing)
        if err:
            return {"error": err}, 1
        return existing, 0

    # Create new paused checkpoint
    checkpoint = {
        "batch_id": "pending",
        "status": "PAUSED",
        "current_wo": None,
        "phase": "before_any_mutation",
        "baseline_before": None,
        "baseline_after": None,
        "branch": None,
        "pr": None,
        "changed_paths": [],
        "last_safe_point": now,
        "paused_at": now,
        "resume_allowed": True,
        "worker_error": None,
        "retry_count": 0,
        "created_at": now,
        "last_updated": now,
    }
    err = _save_checkpoint(checkpoint_path, checkpoint)
    if err:
        return {"error": err}, 1
    return checkpoint, 0


def _cmd_resume(args):
    """Check if resume is allowed and reconcile state.

    Resume requires:
    1. Worker reachable
    2. Baseline matches checkpoint
    3. Worktree clean
    4. Status allows resume
    """
    checkpoint_path = args.resume
    checkpoint, err = _load_checkpoint(checkpoint_path)
    if err:
        return {"error": err}, 1

    status = checkpoint.get("status", "unknown")
    phase = checkpoint.get("phase", "unknown")
    resume_allowed = checkpoint.get("resume_allowed", False)

    result = {
        "checkpoint_status": status,
        "phase": phase,
        "resume_allowed": resume_allowed,
        "batch_id": checkpoint.get("batch_id"),
        "current_wo": checkpoint.get("current_wo"),
        "baseline_before": checkpoint.get("baseline_before"),
    }

    if not resume_allowed:
        result["reason"] = "resume_not_allowed"
        return result, 1

    if status == "BLOCKED_NEEDS_OPERATOR":
        result["reason"] = "needs_operator_intervention"
        return result, 1

    # Reconcile: check worker
    worker_status, worker_error = _check_worker_reachable()
    result["worker_status"] = worker_status
    if worker_status != "reachable":
        result["reason"] = "worker_still_unreachable"
        result["status"] = "BLOCKED_WORKER_UNREACHABLE"
        return result, 1

    # Reconcile: check baseline
    current_baseline = _get_current_baseline()
    result["current_baseline"] = current_baseline
    expected_baseline = checkpoint.get("baseline_before") or checkpoint.get("baseline_after")
    if expected_baseline and current_baseline and expected_baseline != current_baseline:
        result["reason"] = "baseline_mismatch"
        result["expected_baseline"] = expected_baseline
        result["status"] = "BLOCKED_BASELINE_MISMATCH"
        return result, 1

    # Reconcile: check worktree clean
    worktree_clean = _check_worktree_clean()
    result["worktree_clean"] = worktree_clean
    if not worktree_clean:
        result["reason"] = "dirty_worktree"
        result["status"] = "BLOCKED_DIRTY_WORKTREE"
        return result, 1

    # All checks passed
    result["status"] = "RECONCILING"
    result["note"] = "All reconcile checks passed. Ready to resume."
    result["reconcile_checks"] = {
        "worker": "PASS",
        "baseline": "PASS",
        "worktree": "PASS",
    }
    return result, 0


def _cmd_reconcile(args):
    """Explicit reconciliation — same as resume but focused on state verification."""
    # Temporarily set args.checkpoint so _cmd_resume can use it
    args.resume = args.reconcile
    result, rc = _cmd_resume(args)
    if rc == 0:
        result["reconcile_status"] = "PASS"
    else:
        result["reconcile_status"] = "FAIL"
    return result, rc


def _cmd_resume_legacy(args):
    """Legacy resume from V1.5.1 — delegates to new resume."""
    return _cmd_resume(args)


def _cmd_status_report(args):
    """Generate a 15-minute status report."""
    checkpoint_path = args.resume
    checkpoint, err = _load_checkpoint(checkpoint_path)
    if err:
        return {"error": err}, 1

    now = time.time()
    first_unreachable = checkpoint.get("first_unreachable_at", now)
    elapsed_minutes = (now - first_unreachable) / 60

    report = {
        "batch_id": checkpoint.get("batch_id", "unknown"),
        "status": checkpoint.get("status", "unknown"),
        "elapsed_minutes": round(elapsed_minutes, 1),
        "retry_count": checkpoint.get("retry_count", 0),
        "max_retry_count": MAX_RETRY_COUNT,
        "current_wo": checkpoint.get("current_wo"),
        "phase": checkpoint.get("phase"),
        "last_safe_point": checkpoint.get("last_safe_point"),
        "baseline_before": checkpoint.get("baseline_before"),
        "mutation_occurred": checkpoint.get("phase") != "before_any_mutation",
        "resume_allowed": checkpoint.get("resume_allowed", False),
        "next_retry_at": checkpoint.get("next_retry_at"),
        "report_time": now,
    }

    if elapsed_minutes >= MAX_WAIT_MINUTES:
        report["recommendation"] = "BLOCKED_NEEDS_OPERATOR — max wait exceeded"
    else:
        report["recommendation"] = "等待 worker 恢复 / 检查 VPN / 检查 Debian worker"

    return report, 0


def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        prog="vibe_worker_resilience",
        description="Worker Reachability & Resilience",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--json", action="store_true", dest="output_json")
    parser.add_argument("--compact", action="store_true")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Check worker reachability")
    group.add_argument("--checkpoint", metavar="FILE", help="Create/update checkpoint")
    group.add_argument("--pause", metavar="FILE", help="Pause batch at safe point")
    group.add_argument("--resume", metavar="FILE", help="Resume from checkpoint with reconcile")
    group.add_argument("--reconcile", metavar="FILE", help="Reconcile state without resuming")
    group.add_argument("--status-report", metavar="FILE", help="Generate status report")

    return parser


def _format_compact(result):
    """Compact format."""
    if "error" in result:
        return f"RESILIENCE ERROR | {result['error']}"
    status = result.get("worker_status") or result.get("status") or result.get("checkpoint_status", "?")
    return f"RESILIENCE {status}"


def main(argv=None):
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.check:
        result, rc = _cmd_check(args)
    elif args.checkpoint:
        result, rc = _cmd_checkpoint(args)
    elif args.pause:
        result, rc = _cmd_pause(args)
    elif args.resume:
        result, rc = _cmd_resume(args)
    elif args.reconcile:
        result, rc = _cmd_reconcile(args)
    elif args.status_report:
        result, rc = _cmd_status_report(args)
    else:
        parser.print_help()
        return 1

    if args.output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.compact:
        print(_format_compact(result))
    else:
        if "error" in result:
            print(f"ERROR: {result['error']}", file=sys.stderr)
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))

    return rc


if __name__ == "__main__":
    sys.exit(main())
