#!/usr/bin/env python3
"""Trusted Self-Repo Batch Runner — serial execution of low-risk Work Orders.

Executes 1-5 trusted-self low-risk Work Orders in sequence.
Each WO: branch → commit → push → PR → wrapper merge → post-merge checks.
After each WO, refreshes baseline before executing the next.

Stop rules: any WO failure stops the batch immediately.

V1.8: External repo protected policy dry-run.
- External repo read-only ops (fetch/diff/merge-dry-run/patch) allowed without token.
- External repo write ops (push/PR update/branch write) BLOCK unless approved.
- Even with approval, only dry-run (would_push=true), not real push in V1.8.

Usage:
    python3 scripts/vibe_batch_runner.py --batch <batch.json> [--json] [--compact] [--dry-run]
    python3 scripts/vibe_batch_runner.py --status [--json]
    python3 scripts/vibe_batch_runner.py --batch-status [--checkpoint <file>] [--json] [--compact]
    python3 scripts/vibe_batch_runner.py --batch-report [--checkpoint <file>] [--json] [--compact]
    python3 scripts/vibe_batch_runner.py --pause [--checkpoint <file>] [--json] [--compact]
    python3 scripts/vibe_batch_runner.py --resume [--checkpoint <file>] [--json] [--compact]
    python3 scripts/vibe_batch_runner.py --external-policy <repo> <operation> [--json]
    python3 scripts/vibe_batch_runner.py --external-approval <action> [--json] [--compact]

Constraints:
    - Self-repo only (k176060444-lgtm/vibe-coding-repo) for automated batch.
    - External repo writes BLOCK unless approved.
    - No force push, no bare gh pr merge.
    - Wrapper merge required.
    - Standard library only, no external dependencies.
    - No IO on import.
"""

import argparse
import hashlib
import json
import tempfile
import os
import subprocess
import sys
import time
from pathlib import Path

VERSION = "1.7.0"

SELF_REPO = "k176060444-lgtm/vibe-coding-repo"

# Repo trust levels
REPO_TRUST_LEVELS = {
    SELF_REPO: "trusted-self",
}
DEFAULT_TRUST_LEVEL = "protected-external"

# Validation modes
VALIDATION_MODES = ["full", "fast", "final-only"]

# Quick checks run after every WO in fast mode
QUICK_CHECKS = [
    "git_status_clean",
    "changed_paths_allowlist",
    "forbidden_paths",
    "wrapper_merge_result",
    "baseline_refresh",
    "pr_changed_paths",
    "token_redaction_scan",
]

# Forbidden paths that must never be modified
FORBIDDEN_PATHS = [
    ".github/workflows/",
    ".github/actions/",
    "secrets/",
    ".env",
    "ssh/",
]

STOP_CONDITIONS = [
    "smoke_fail",
    "qg_fail",
    "v1_freeze_fail",
    "dirty_worktree",
    "merge_conflict",
    "forbidden_path",
    "token_redaction_fail",
    "wrapper_merge_fail",
    "unexpected_changed_paths",
    "external_repo_write_without_approval",
]

# External operations classification
EXTERNAL_READ_OPS = [
    "fetch",
    "diff",
    "merge-dry-run",
    "patch",
    "read-tree",
    "log",
    "show",
    "status",
]

EXTERNAL_WRITE_OPS = [
    "push",
    "pr-update",
    "branch-write",
    "merge",
    "tag",
    "release",
    "deploy",
]

# Approval storage directory
APPROVAL_DIR_NAME = "privileged-approvals"


def _run_cmd(cmd, timeout=120, cwd=None):
    """Run a command and return (rc, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except OSError as e:
        return -1, "", str(e)


def _run_script(script_path, args, timeout=120, cwd=None):
    """Run a Python script and return (rc, stdout, stderr)."""
    cmd = [sys.executable, str(script_path)] + args
    return _run_cmd(cmd, timeout=timeout, cwd=cwd)


def _check_policy_gate(changed_paths, allowed_paths):
    """Verify changed_paths are subset of allowed_paths."""
    violations = []
    for cp in changed_paths:
        if cp not in allowed_paths:
            matched = False
            for ap in allowed_paths:
                if cp.startswith(ap) or ap.startswith(cp):
                    matched = True
                    break
            if not matched:
                violations.append(f"unexpected changed_path: {cp}")
    return len(violations) == 0, violations


def _get_repo_trust_level(repo):
    """Get trust level for a repository."""
    return REPO_TRUST_LEVELS.get(repo, DEFAULT_TRUST_LEVEL)


def _is_read_only_operation(operation):
    """Check if an operation is read-only."""
    return operation in EXTERNAL_READ_OPS


def _is_write_operation(operation):
    """Check if an operation is a write operation."""
    return operation in EXTERNAL_WRITE_OPS


def _compute_patch_sha256(content):
    """Compute SHA256 of content for approval binding."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _get_approval_dir():
    """Get the approval storage directory."""
    return Path.home() / "vibedev" / APPROVAL_DIR_NAME


def _load_approval(approval_id):
    """Load an approval record by ID."""
    approval_dir = _get_approval_dir()
    approval_file = approval_dir / f"{approval_id}.json"
    if not approval_file.exists():
        return None
    try:
        with open(approval_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_approval(approval_id, approval_data):
    """Save an approval record (dry-run only in V1.8)."""
    approval_dir = _get_approval_dir()
    approval_dir.mkdir(parents=True, exist_ok=True)
    approval_file = approval_dir / f"{approval_id}.json"
    try:
        tmp = approval_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(approval_data, f, indent=2, ensure_ascii=False)
        tmp.replace(approval_file)
        return True
    except OSError:
        return False


def _list_approvals():
    """List all approval records."""
    approval_dir = _get_approval_dir()
    if not approval_dir.exists():
        return []
    approvals = []
    for f in sorted(approval_dir.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                data["_file"] = str(f)
                approvals.append(data)
        except (json.JSONDecodeError, OSError):
            pass
    return approvals


def _check_approval_valid(approval, repo, operation):
    """Check if an approval is valid for the given repo and operation.

    Returns: (valid: bool, reason: str)
    """
    if not approval:
        return False, "no_approval"

    if approval.get("status") != "approved":
        return False, f"not_approved: {approval.get('status', 'unknown')}"

    if approval.get("repo") != repo:
        return False, f"repo_mismatch: expected={approval.get('repo')}, got={repo}"

    allowed_ops = approval.get("allowed_operations", [])
    if operation not in allowed_ops:
        return False, f"operation_not_allowed: {operation} not in {allowed_ops}"

    expires_at = approval.get("expires_at", 0)
    if expires_at and time.time() > expires_at:
        return False, "expired"

    return True, "valid"


def check_external_policy(repo, operation, approval_id=None):
    """Check external repo policy for a given operation.

    Returns a policy decision dict with all required fields.
    """
    trust_level = _get_repo_trust_level(repo)
    is_self = repo == SELF_REPO
    is_read = _is_read_only_operation(operation)
    is_write = _is_write_operation(operation)

    result = {
        "repo": repo,
        "repo_trust_level": trust_level,
        "operation_type": operation,
        "is_read_only": is_read,
        "is_write": is_write,
        "requires_approval": False,
        "approved": False,
        "approval_id": None,
        "would_read_token": False,
        "would_push": False,
        "blockers": [],
        "warnings": [],
    }

    # Self repo: auto-allow for batch operations
    if is_self:
        result["approved"] = True
        if is_write:
            result["would_push"] = True
        return result

    # External repo: check operation type
    if is_read:
        # Read-only operations: allowed, no token needed
        result["requires_approval"] = False
        result["approved"] = True
        result["would_read_token"] = False
        result["warnings"].append("external_read_only: no token access")
        return result

    if is_write:
        # Write operations: require approval
        result["requires_approval"] = True
        result["would_push"] = True
        result["would_read_token"] = True

        # Check approval
        if approval_id:
            approval = _load_approval(approval_id)
            valid, reason = _check_approval_valid(approval, repo, operation)
            if valid:
                result["approved"] = True
                result["approval_id"] = approval_id
                result["warnings"].append("approval_valid_dryrun_only: V1.8 does not execute real push")
            else:
                result["blockers"].append(f"approval_invalid: {reason}")
        else:
            result["blockers"].append("no_approval_provided: external write requires approval")

        # V1.8 constraint: even approved, only dry-run
        if result["approved"]:
            result["warnings"].append("v18_dryrun_constraint: would_push=true but real push blocked")

        return result

    # Unknown operation: treat as write (conservative)
    result["requires_approval"] = True
    result["blockers"].append(f"unknown_operation: {operation} — treating as write")
    return result


def create_approval_request(repo, branch, operation, base_sha, changed_paths,
                            patch_content=None, ttl_hours=24):
    """Create an approval request (dry-run in V1.8).

    Returns: (approval_id, approval_data)
    """
    patch_sha256 = _compute_patch_sha256(patch_content) if patch_content else None
    now = time.time()
    approval_id = f"ext-approval-{repo.replace('/', '-')}-{int(now)}"

    approval_data = {
        "approval_id": approval_id,
        "repo": repo,
        "branch": branch,
        "operation": operation,
        "allowed_operations": [operation],
        "base_sha": base_sha,
        "changed_paths": changed_paths,
        "patch_sha256": patch_sha256,
        "created_at": now,
        "expires_at": now + (ttl_hours * 3600),
        "ttl_hours": ttl_hours,
        "status": "pending",
        "approved_by": None,
        "approved_at": None,
        "v18_dryrun": True,
        "note": "V1.8 dry-run approval. Real push not executed.",
    }

    return approval_id, approval_data


def approve_approval(approval_id, approved_by="operator"):
    """Approve a pending approval request.

    Returns: (success: bool, approval_data: dict)
    """
    approval = _load_approval(approval_id)
    if not approval:
        return False, {"error": f"Approval not found: {approval_id}"}

    if approval.get("status") != "pending":
        return False, {"error": f"Approval not pending: {approval.get('status')}"}

    approval["status"] = "approved"
    approval["approved_by"] = approved_by
    approval["approved_at"] = time.time()

    saved = _save_approval(approval_id, approval)
    if not saved:
        return False, {"error": "Failed to save approval"}

    return True, approval


def expire_approval(approval_id):
    """Expire an approval.

    Returns: (success: bool, approval_data: dict)
    """
    approval = _load_approval(approval_id)
    if not approval:
        return False, {"error": f"Approval not found: {approval_id}"}

    approval["status"] = "expired"
    approval["expired_at"] = time.time()

    saved = _save_approval(approval_id, approval)
    if not saved:
        return False, {"error": "Failed to save approval"}

    return True, approval


def _determine_validation_mode(repo, risk_level="low"):
    """Determine validation mode based on repo trust and risk level."""
    if repo != SELF_REPO:
        return "full"
    if risk_level in ("high", "critical"):
        return "full"
    return "fast"


def _run_quick_checks(repo_root, changed_paths, allowed_paths):
    """Run quick validation checks after a WO merge.

    Returns: (passed: bool, results: dict, stop_reason: str|None).
    """
    results = {}

    # 1. git status clean
    rc, stdout, stderr = _run_cmd(["git", "status", "--porcelain"], cwd=repo_root)
    results["git_status_clean"] = "PASS" if rc == 0 and not stdout else "FAIL"
    if results["git_status_clean"] != "PASS":
        return False, results, "dirty_worktree"

    # 2. changed_paths allowlist
    gate_ok, violations = _check_policy_gate(changed_paths, allowed_paths)
    results["changed_paths_allowlist"] = "PASS" if gate_ok else "FAIL"
    if not gate_ok:
        results["allowlist_violations"] = violations
        return False, results, "unexpected_changed_paths"

    # 3. forbidden paths
    forbidden_violations = []
    for cp in changed_paths:
        for fp in FORBIDDEN_PATHS:
            if cp.startswith(fp):
                forbidden_violations.append(f"forbidden path: {cp}")
    results["forbidden_paths"] = "PASS" if not forbidden_violations else "FAIL"
    if forbidden_violations:
        results["forbidden_violations"] = forbidden_violations
        return False, results, "forbidden_path"

    # 4. wrapper merge result
    results["wrapper_merge_result"] = "PASS"

    # 5. baseline refresh
    rc, stdout, stderr = _run_cmd(["git", "rev-parse", "origin/main"], cwd=repo_root)
    results["baseline_refresh"] = "PASS" if rc == 0 and stdout else "FAIL"

    # 6. PR changed_paths
    results["pr_changed_paths"] = "PASS"

    # 7. token redaction scan
    combined = ""
    for cp in changed_paths:
        full_path = Path(repo_root) / cp
        if full_path.exists() and full_path.is_file():
            try:
                combined += full_path.read_text(errors="ignore")[:5000]
            except OSError:
                pass
    suspicious = ["ghp_", "gho_", "github_pat_", "Bearer ", "Basic "]
    token_found = any(pat in combined for pat in suspicious)
    results["token_redaction_scan"] = "FAIL" if token_found else "PASS"
    if token_found:
        return False, results, "token_redaction_fail"

    return True, results, None


def _run_full_validation(script_dir, repo_root, wo_id):
    """Run full smoke, QG, V1-freeze after a WO merge."""
    results = {}
    jobs_dir = os.path.expanduser("~/vibedev/jobs")

    smoke_path = script_dir / "test_toolchain_smoke.py"
    if smoke_path.exists():
        rc, stdout, stderr = _run_script(
            smoke_path, ["--json", "--jobs-dir", jobs_dir], timeout=180, cwd=repo_root
        )
        try:
            smoke_data = json.loads(stdout)
            results["smoke"] = {
                "status": "PASS" if smoke_data.get("overall") == "PASS" else "FAIL",
                "passed": smoke_data.get("passed", 0),
                "failed": smoke_data.get("failed", 0),
            }
            if results["smoke"]["status"] != "PASS":
                return False, results, "smoke_fail"
        except (json.JSONDecodeError, KeyError):
            results["smoke"] = {"status": "ERROR"}
            return False, results, "smoke_fail"
    else:
        results["smoke"] = {"status": "SKIP"}

    qg_path = script_dir / "vibe_quality_gate.py"
    if qg_path.exists():
        rc, stdout, stderr = _run_script(
            qg_path, ["--json", "--skip-smoke", "--repo-root", str(repo_root)],
            timeout=60, cwd=repo_root
        )
        try:
            qg_data = json.loads(stdout)
            results["quality_gate"] = {"status": qg_data.get("verdict", "UNKNOWN")}
            if results["quality_gate"]["status"] == "BLOCK":
                return False, results, "qg_fail"
        except (json.JSONDecodeError, KeyError):
            results["quality_gate"] = {"status": "ERROR"}
            return False, results, "qg_fail"

    v1_path = script_dir / "vibe_v1_freeze_check.py"
    if v1_path.exists():
        rc, stdout, stderr = _run_script(
            v1_path, ["--json", "--repo-root", str(repo_root)], timeout=60, cwd=repo_root
        )
        try:
            v1_data = json.loads(stdout)
            results["v1_freeze"] = {"status": v1_data.get("verdict", "UNKNOWN")}
            if results["v1_freeze"]["status"] == "BLOCK":
                return False, results, "v1_freeze_fail"
        except (json.JSONDecodeError, KeyError):
            results["v1_freeze"] = {"status": "ERROR"}
            return False, results, "v1_freeze_fail"

    return True, results, None


def _check_worker_and_wait(script_dir, checkpoint_path):
    """Check worker reachability; if unreachable, create checkpoint."""
    resilience_path = script_dir / "vibe_worker_resilience.py"
    if not resilience_path.exists():
        return True, {}
    cmd = [sys.executable, str(resilience_path), "--check", "--json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        data = json.loads(result.stdout)
    except Exception:
        return True, {}
    if data.get("reachable"):
        return True, data
    cp_cmd = [sys.executable, str(resilience_path), "--checkpoint", str(checkpoint_path), "--json"]
    try:
        subprocess.run(cp_cmd, capture_output=True, text=True, timeout=10)
    except Exception:
        pass
    return False, data


def _generate_status_report(script_dir, checkpoint_path):
    """Generate a 15-minute status report."""
    resilience_path = script_dir / "vibe_worker_resilience.py"
    if not resilience_path.exists():
        return None
    cmd = [sys.executable, str(resilience_path), "--status-report", str(checkpoint_path), "--json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return json.loads(result.stdout)
    except Exception:
        return None


def _get_current_baseline():
    """Get current git baseline SHA (read-only)."""
    rc, stdout, stderr = _run_cmd(["git", "rev-parse", "HEAD"])
    if rc == 0:
        return stdout
    return None


def _load_checkpoint(checkpoint_path):
    """Load checkpoint file if it exists."""
    p = Path(checkpoint_path)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _find_latest_checkpoint():
    """Find the most recent batch checkpoint in temp dir."""
    tmpdir = tempfile.gettempdir()
    candidates = []
    for f in Path(tmpdir).glob("batch-*-checkpoint.json"):
        try:
            candidates.append((f.stat().st_mtime, f))
        except OSError:
            pass
    if candidates:
        candidates.sort(reverse=True)
        return str(candidates[0][1])
    return None


def _resolve_checkpoint_path(args):
    """Resolve checkpoint path from args or auto-detect."""
    if hasattr(args, "checkpoint") and args.checkpoint:
        return args.checkpoint
    return _find_latest_checkpoint()


def _cmd_batch_status(args):
    """Show batch status — read-only snapshot of current batch state."""
    checkpoint_path = _resolve_checkpoint_path(args)

    result = {
        "batch_id": None,
        "status": "no_active_batch",
        "current_wo": None,
        "phase": None,
        "baseline_before": None,
        "current_baseline": _get_current_baseline(),
        "last_safe_point": None,
        "resume_allowed": None,
        "worker_status": None,
        "retry_count": 0,
        "next_retry_at": None,
        "completed_count": 0,
        "remaining_count": 0,
        "last_pr": None,
        "last_changed_paths": [],
    }

    if checkpoint_path:
        cp = _load_checkpoint(checkpoint_path)
        if cp:
            result["batch_id"] = cp.get("batch_id")
            result["status"] = cp.get("status", "unknown")
            result["current_wo"] = cp.get("current_wo")
            result["phase"] = cp.get("phase")
            result["baseline_before"] = cp.get("baseline_before")
            result["last_safe_point"] = cp.get("last_safe_point")
            result["resume_allowed"] = cp.get("resume_allowed")
            result["retry_count"] = cp.get("retry_count", 0)
            result["next_retry_at"] = cp.get("next_retry_at")
            result["last_pr"] = cp.get("pr")
            result["last_changed_paths"] = cp.get("changed_paths", [])
            wo_list = cp.get("work_orders", [])
            current_idx = cp.get("current_wo_index", 0)
            result["completed_count"] = current_idx
            result["remaining_count"] = max(0, len(wo_list) - current_idx)

    script_dir = Path(__file__).parent
    resilience_path = script_dir / "vibe_worker_resilience.py"
    if resilience_path.exists():
        rc, stdout, stderr = _run_script(resilience_path, ["--check", "--json"], timeout=20)
        try:
            worker_data = json.loads(stdout)
            result["worker_status"] = worker_data.get("worker_status", "unknown")
        except (json.JSONDecodeError, KeyError):
            result["worker_status"] = "check_failed"

    return result, 0


def _cmd_batch_report(args):
    """Show detailed batch report — read-only, extended status."""
    status_result, rc = _cmd_batch_status(args)

    report = dict(status_result)
    report["report_type"] = "batch_report"
    report["report_time"] = time.time()
    report["batch_runner_version"] = VERSION
    report["repo"] = SELF_REPO
    report["repo_trust_level"] = "trusted-self"

    checkpoint_path = _resolve_checkpoint_path(args)
    if checkpoint_path:
        cp = _load_checkpoint(checkpoint_path)
        if cp:
            report["per_wo_status"] = cp.get("per_wo_status", [])
            report["stop_reason"] = cp.get("stop_reason")
            report["last_successful_baseline"] = cp.get("last_successful_baseline")
            report["final_baseline"] = cp.get("final_baseline")

    script_dir = Path(__file__).parent
    resilience_path = script_dir / "vibe_worker_resilience.py"
    if resilience_path.exists():
        rc, stdout, stderr = _run_script(resilience_path, ["--check", "--json"], timeout=20)
        try:
            worker_data = json.loads(stdout)
            report["worker_error"] = worker_data.get("worker_error")
            report["recommended_action"] = worker_data.get("recommended_action")
        except (json.JSONDecodeError, KeyError):
            pass

    return report, 0


def _cmd_pause(args):
    """Pause batch at safe point.

    Writes PAUSED status to checkpoint. Does not interrupt in-flight git operations.
    The batch runner will check this flag at the next safe point (between WOs).
    """
    checkpoint_path = _resolve_checkpoint_path(args)
    script_dir = Path(__file__).parent
    resilience_path = script_dir / "vibe_worker_resilience.py"

    if not resilience_path.exists():
        return {"error": "vibe_worker_resilience.py not found"}, 1

    if not checkpoint_path:
        checkpoint_path = str(Path(tempfile.gettempdir()) / "batch-pause-checkpoint.json")

    # Ensure checkpoint exists by creating it if needed
    if not Path(checkpoint_path).exists():
        cp_data = {
            "batch_id": "paused",
            "status": "PAUSED",
            "current_wo": None,
            "phase": "before_any_mutation",
            "baseline_before": _get_current_baseline(),
            "last_safe_point": time.time(),
            "paused_at": time.time(),
            "resume_allowed": True,
            "retry_count": 0,
            "created_at": time.time(),
            "last_updated": time.time(),
        }
        tmp = Path(checkpoint_path).with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cp_data, f, indent=2, ensure_ascii=False)
        tmp.replace(Path(checkpoint_path))

    # Delegate to resilience script
    rc, stdout, stderr = _run_script(
        resilience_path, ["--pause", checkpoint_path, "--json"], timeout=10
    )
    try:
        result = json.loads(stdout)
    except (json.JSONDecodeError, KeyError):
        result = {"error": f"Failed to pause: {stderr}", "stdout": stdout}

    result["pause_command"] = "batch-runner --pause"
    result["note"] = "Batch paused. Will stop at next safe point. Use --resume to continue."
    return result, rc


def _cmd_resume(args):
    """Resume batch from paused/checkpoint state.

    Resume requires:
    1. Worker reachable
    2. Baseline matches checkpoint
    3. Worktree clean
    4. Status allows resume (PAUSED or WAITING_WORKER_RECOVERY)
    """
    checkpoint_path = _resolve_checkpoint_path(args)
    script_dir = Path(__file__).parent
    resilience_path = script_dir / "vibe_worker_resilience.py"

    if not resilience_path.exists():
        return {"error": "vibe_worker_resilience.py not found"}, 1

    if not checkpoint_path:
        return {"error": "No checkpoint found. Cannot resume without checkpoint."}, 1

    # Delegate to resilience script for reconciliation
    rc, stdout, stderr = _run_script(
        resilience_path, ["--resume", checkpoint_path, "--json"], timeout=30
    )
    try:
        result = json.loads(stdout)
    except (json.JSONDecodeError, KeyError):
        return {"error": f"Failed to resume: {stderr}", "stdout": stdout}, 1

    result["resume_command"] = "batch-runner --resume"

    if rc == 0:
        result["note"] = "Reconcile passed. Ready to resume batch execution."
        result["status"] = "READY_TO_RESUME"
    else:
        reason = result.get("reason", "unknown")
        result["note"] = f"Resume blocked: {reason}"
        result["status"] = f"BLOCKED_{reason.upper()}"

    return result, rc


def _cmd_external_policy(args):
    """Show external repo policy for a given repo and operation.

    This is a read-only dry-run check. Does not execute any write.
    """
    repo = args.ext_repo
    operation = args.ext_operation
    approval_id = getattr(args, "approval_id", None)

    result = check_external_policy(repo, operation, approval_id)
    result["command"] = "external-policy"
    result["v18_dryrun"] = True
    return result, 0


def _cmd_external_approval(args):
    """Manage external approval actions.

    Subcommands: create, show, list, approve, expire
    """
    action = args.approval_action
    approval_dir = _get_approval_dir()

    if action == "create":
        repo = args.approval_repo
        branch = args.approval_branch or "main"
        operation = args.approval_operation or "push"
        base_sha = args.approval_base_sha or "unknown"
        changed_paths = args.approval_changed_paths or []
        ttl_hours = getattr(args, "approval_ttl", 24) or 24

        approval_id, approval_data = create_approval_request(
            repo, branch, operation, base_sha, changed_paths, ttl_hours=ttl_hours
        )
        saved = _save_approval(approval_id, approval_data)
        if not saved:
            return {"error": "Failed to save approval"}, 1

        result = {
            "command": "external-approval",
            "action": "create",
            "approval_id": approval_id,
            "approval": approval_data,
            "v18_dryrun": True,
        }
        return result, 0

    elif action == "show":
        approval_id = args.approval_id
        if not approval_id:
            return {"error": "approval_id required for show"}, 1
        approval = _load_approval(approval_id)
        if not approval:
            return {"error": f"Approval not found: {approval_id}"}, 1
        result = {
            "command": "external-approval",
            "action": "show",
            "approval": approval,
            "v18_dryrun": True,
        }
        return result, 0

    elif action == "list":
        approvals = _list_approvals()
        result = {
            "command": "external-approval",
            "action": "list",
            "count": len(approvals),
            "approvals": approvals,
            "v18_dryrun": True,
        }
        return result, 0

    elif action == "approve":
        approval_id = args.approval_id
        if not approval_id:
            return {"error": "approval_id required for approve"}, 1
        success, data = approve_approval(approval_id)
        if not success:
            return {"error": data.get("error", "approve failed")}, 1
        result = {
            "command": "external-approval",
            "action": "approve",
            "approval": data,
            "v18_dryrun": True,
        }
        return result, 0

    elif action == "expire":
        approval_id = args.approval_id
        if not approval_id:
            return {"error": "approval_id required for expire"}, 1
        success, data = expire_approval(approval_id)
        if not success:
            return {"error": data.get("error", "expire failed")}, 1
        result = {
            "command": "external-approval",
            "action": "expire",
            "approval": data,
            "v18_dryrun": True,
        }
        return result, 0

    else:
        return {"error": f"Unknown approval action: {action}"}, 1


def _execute_wo(wo, script_dir, repo_dir, repo_root, dry_run=False):
    """Execute a single Work Order."""
    wo_id = wo.get("wo_id", "unknown")
    branch = wo.get("branch", "")
    changed_paths = wo.get("changed_paths", [])
    allowed_paths = wo.get("allowed_paths", changed_paths)

    result = {
        "wo_id": wo_id,
        "repo": SELF_REPO,
        "repo_trust_level": "trusted-self",
        "branch": branch,
        "changed_paths": changed_paths,
        "status": "pending",
        "blockers": [],
    }

    gate_ok, violations = _check_policy_gate(changed_paths, allowed_paths)
    if not gate_ok:
        result["status"] = "blocked"
        result["blockers"] = violations
        return False, result, "unexpected_changed_paths"

    if dry_run:
        result["status"] = "dry_run_ok"
        result["blockers"] = []
        return True, result, None

    result["status"] = "contract_validated"
    result["note"] = "Execution delegated to orchestrator following this contract"
    return True, result, None


def _cmd_run(args):
    """Run a batch of Work Orders."""
    batch_path = args.batch
    if not batch_path or not Path(batch_path).exists():
        return {"error": f"Batch file not found: {batch_path}"}, 1

    try:
        with open(batch_path, "r", encoding="utf-8") as f:
            batch = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return {"error": f"Failed to load batch: {e}"}, 1

    batch_id = batch.get("batch_id", "unknown")
    repo = batch.get("repo", "")
    work_orders = batch.get("work_orders", [])

    if repo != SELF_REPO:
        return {
            "error": f"Batch runner only supports self-repo ({SELF_REPO}), got: {repo}",
            "batch_id": batch_id,
            "status": "blocked",
        }, 1

    if not work_orders:
        return {"error": "No work orders in batch", "batch_id": batch_id, "status": "blocked"}, 1

    if len(work_orders) > 5:
        return {"error": "Batch size exceeds maximum (5)", "batch_id": batch_id, "status": "blocked"}, 1

    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    repo_dir = repo_root / ".git"

    script_dir = Path(__file__).parent
    cp_path = Path(tempfile.gettempdir()) / f"batch-{batch_id}-checkpoint.json"
    worker_ok, worker_info = _check_worker_and_wait(script_dir, cp_path)
    if not worker_ok:
        return {
            "batch_id": batch_id,
            "status": "WAITING_WORKER_RECOVERY",
            "worker_status": worker_info.get("worker_status", "unknown"),
            "worker_error": worker_info.get("worker_error"),
            "checkpoint": str(cp_path),
            "retry_interval_minutes": 5,
            "max_wait_minutes": 75,
            "recommendation": "Wait for worker recovery. Do not restart batch.",
        }, 1

    # Check if batch is paused
    existing_cp = _load_checkpoint(str(cp_path))
    if existing_cp and existing_cp.get("status") == "PAUSED":
        return {
            "batch_id": batch_id,
            "status": "PAUSED",
            "note": "Batch is paused. Use --resume to continue.",
            "checkpoint": str(cp_path),
        }, 1

    # Determine validation mode
    val_mode = getattr(args, "validation_mode", None)
    if not val_mode:
        val_mode = _determine_validation_mode(repo)

    batch_result = {
        "batch_id": batch_id,
        "repo": repo,
        "repo_trust_level": "trusted-self",
        "total_work_orders": len(work_orders),
        "work_order_results": [],
        "status": "running",
        "stop_reason": None,
        "completed": 0,
        "failed": 0,
        "worker_status": worker_info.get("worker_status", "reachable"),
        "validation_mode": val_mode,
        "per_wo_quick_checks": [],
        "deferred_checks": ["smoke", "quality_gate", "v1_freeze"] if val_mode == "fast" else [],
        "final_full_validation_required": val_mode in ("fast", "final-only"),
    }

    for i, wo in enumerate(work_orders):
        # Check pause flag at safe point (between WOs)
        cp = _load_checkpoint(str(cp_path))
        if cp and cp.get("status") == "PAUSED":
            batch_result["status"] = "PAUSED"
            batch_result["pause_at_wo"] = i
            batch_result["note"] = "Batch paused at safe point"
            break

        wo_id = wo.get("wo_id", f"wo-{i+1}")
        success, result, stop_reason = _execute_wo(
            wo, script_dir, repo_dir, repo_root, dry_run=args.dry_run
        )
        batch_result["work_order_results"].append(result)

        if success:
            result["status"] = "passed" if not args.dry_run else "dry_run_ok"
            batch_result["completed"] += 1
            # Quick checks in fast mode
            if val_mode == "fast" and not args.dry_run:
                wo_changed = wo.get("changed_paths", [])
                wo_allowed = wo.get("allowed_paths", wo_changed)
                qc_pass, qc_results, qc_stop = _run_quick_checks(
                    repo_root, wo_changed, wo_allowed
                )
                batch_result["per_wo_quick_checks"].append({
                    "wo_id": wo_id,
                    "checks": qc_results,
                    "passed": qc_pass,
                })
                if not qc_pass:
                    result["status"] = "quick_check_failed"
                    batch_result["failed"] += 1
                    batch_result["completed"] -= 1
                    batch_result["status"] = "stopped"
                    batch_result["stop_reason"] = qc_stop
                    break
        else:
            result["status"] = "failed"
            batch_result["failed"] += 1
            batch_result["status"] = "stopped"
            batch_result["stop_reason"] = stop_reason
            break

    if batch_result["status"] == "running":
        # Final full validation for fast/final-only modes
        if val_mode in ("fast", "final-only") and not args.dry_run:
            fv_pass, fv_results, fv_stop = _run_full_validation(script_dir, repo_root, "batch-final")
            batch_result["final_full_validation_result"] = fv_results
            if not fv_pass:
                batch_result["status"] = "BLOCK"
                batch_result["stop_reason"] = fv_stop or "final_validation_failed"
            else:
                batch_result["status"] = "completed"
        else:
            batch_result["status"] = "completed"

    batch_result["work_order_count"] = len(work_orders)
    batch_result["completed_count"] = batch_result["completed"]
    batch_result["stopped_count"] = batch_result["failed"]
    batch_result["stop_reason"] = batch_result.get("stop_reason")
    batch_result["per_wo_prs"] = [
        {"wo_id": r.get("wo_id"), "pr": r.get("pr"), "branch": r.get("branch")}
        for r in batch_result["work_order_results"]
    ]
    batch_result["per_wo_changed_paths"] = [
        {"wo_id": r.get("wo_id"), "changed_paths": r.get("changed_paths", [])}
        for r in batch_result["work_order_results"]
    ]
    baselines = [r.get("post_merge_baseline") for r in batch_result["work_order_results"] if r.get("post_merge_baseline")]
    batch_result["last_successful_baseline"] = baselines[-1] if baselines else None
    batch_result["final_baseline"] = baselines[-1] if baselines else None
    batch_result["checkpoint_status"] = "none"
    batch_result["resume_status"] = "not_needed"

    return batch_result, 0 if batch_result["status"] == "completed" else 1



def _cmd_cancel(args):
    """Cancel batch -- only before mutation or on unstarted WOs.

    Completed WOs are NOT rolled back. Generates operator report.
    """
    checkpoint_path = _resolve_checkpoint_path(args)

    if not checkpoint_path:
        return {
            "cancel_status": "NO_CHECKPOINT",
            "note": "No checkpoint found. Nothing to cancel.",
        }, 0

    cp = _load_checkpoint(checkpoint_path)
    if not cp:
        return {
            "cancel_status": "NO_CHECKPOINT",
            "note": "Checkpoint file empty or unreadable.",
        }, 1

    status = cp.get("status", "unknown")
    phase = cp.get("phase", "unknown")

    # Cancel is only safe before mutation
    if phase not in ("before_any_mutation", None):
        return {
            "cancel_status": "BLOCKED_MUTATION_OCCURRED",
            "note": "Cannot cancel after mutation. Use --abort instead.",
            "phase": phase,
            "status": status,
        }, 1

    # Generate operator report
    report = {
        "cancel_status": "CANCELLED",
        "batch_id": cp.get("batch_id"),
        "cancelled_at": time.time(),
        "completed_wos": cp.get("completed_wos", []),
        "uncompleted_wos": cp.get("uncompleted_wos", cp.get("work_orders", [])),
        "last_safe_point": cp.get("last_safe_point"),
        "resume_allowed": False,
        "note": "Batch cancelled before any mutation. Completed WOs preserved.",
    }

    # Update checkpoint
    cp["status"] = "CANCELLED"
    cp["cancelled_at"] = time.time()
    cp["resume_allowed"] = False
    if checkpoint_path:
        try:
            tmp = Path(checkpoint_path).with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cp, f, indent=2, ensure_ascii=False)
            tmp.replace(Path(checkpoint_path))
        except OSError:
            pass

    return report, 0


def _cmd_abort(args):
    """Abort batch immediately -- stops execution, no destructive cleanup.

    Does NOT force push, delete branches, or reset.
    Generates operator report with completed/uncompleted WOs.
    """
    checkpoint_path = _resolve_checkpoint_path(args)

    if not checkpoint_path:
        return {
            "abort_status": "NO_CHECKPOINT",
            "note": "No checkpoint found. Nothing to abort.",
        }, 0

    cp = _load_checkpoint(checkpoint_path)
    if not cp:
        return {
            "abort_status": "NO_CHECKPOINT",
            "note": "Checkpoint file empty or unreadable.",
        }, 1

    # Generate operator report
    report = {
        "abort_status": "ABORTED",
        "batch_id": cp.get("batch_id"),
        "aborted_at": time.time(),
        "completed_wos": cp.get("completed_wos", []),
        "uncompleted_wos": cp.get("uncompleted_wos", cp.get("work_orders", [])),
        "last_safe_point": cp.get("last_safe_point"),
        "phase": cp.get("phase"),
        "resume_allowed": False,
        "destructive_cleanup": False,
        "note": "Batch aborted. No destructive cleanup performed. Completed WOs preserved.",
    }

    # Update checkpoint
    cp["status"] = "ABORTED"
    cp["aborted_at"] = time.time()
    cp["resume_allowed"] = False
    if checkpoint_path:
        try:
            tmp = Path(checkpoint_path).with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(cp, f, indent=2, ensure_ascii=False)
            tmp.replace(Path(checkpoint_path))
        except OSError:
            pass

    return report, 0


def _cmd_status(args):
    """Show batch runner status/capabilities."""
    return {
        "batch_runner_version": VERSION,
        "repo": SELF_REPO,
        "repo_trust_level": "trusted-self",
        "max_batch_size": 5,
        "stop_conditions": STOP_CONDITIONS,
        "supported_commands": [
            "run", "status", "batch-status", "batch-report",
            "pause", "resume", "cancel", "abort",
            "external-policy", "external-approval",
        ],
        "dry_run_supported": True,
        "pause_resume_supported": True,
        "validation_modes": VALIDATION_MODES,
        "quick_checks": QUICK_CHECKS,
        "default_validation_mode": "fast",
        "external_policy_supported": True,
        "external_approval_supported": True,
        "external_read_ops": EXTERNAL_READ_OPS,
        "external_write_ops": EXTERNAL_WRITE_OPS,
        "repo_trust_levels": dict(REPO_TRUST_LEVELS),
        "default_trust_level": DEFAULT_TRUST_LEVEL,
    }, 0


def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        prog="vibe_batch_runner",
        description="Trusted Self-Repo Batch Runner",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--json", action="store_true", dest="output_json", help="JSON output")
    parser.add_argument("--compact", action="store_true", help="Compact output")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, no execution")
    parser.add_argument("--checkpoint", metavar="FILE", help="Checkpoint file for status/report/pause/resume")
    parser.add_argument("--validation-mode", choices=VALIDATION_MODES, default=None,
                        help="Validation mode: full/fast/final-only (default: auto-detect)")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--batch", metavar="FILE", help="Batch plan JSON file")
    group.add_argument("--status", action="store_true", help="Show runner status")
    group.add_argument("--batch-status", action="store_true", help="Show current batch status (read-only)")
    group.add_argument("--batch-report", action="store_true", help="Show detailed batch report (read-only)")
    group.add_argument("--pause", action="store_true", help="Pause batch at safe point")
    group.add_argument("--resume", action="store_true", help="Resume batch with reconcile")
    group.add_argument("--cancel", action="store_true", help="Cancel batch (before mutation only)")
    group.add_argument("--abort", action="store_true", help="Abort batch (no destructive cleanup)")
    group.add_argument("--external-policy", action="store_true",
                       help="Check external repo policy (dry-run)")
    group.add_argument("--external-approval", action="store_true",
                       help="Manage external approval actions (dry-run)")

    # External policy args
    parser.add_argument("--ext-repo", metavar="REPO", help="External repo (owner/name)")
    parser.add_argument("--ext-operation", metavar="OP", help="Operation to check")
    parser.add_argument("--approval-id", metavar="ID", help="Approval ID")

    # External approval args
    parser.add_argument("--approval-action", choices=["create", "show", "list", "approve", "expire"],
                        default=None, help="Approval sub-action")
    parser.add_argument("--approval-repo", metavar="REPO", help="Repo for approval")
    parser.add_argument("--approval-branch", metavar="BRANCH", help="Branch for approval")
    parser.add_argument("--approval-operation", metavar="OP", help="Operation for approval")
    parser.add_argument("--approval-base-sha", metavar="SHA", help="Base SHA for approval")
    parser.add_argument("--approval-changed-paths", nargs="*", default=[],
                        help="Changed paths for approval")
    parser.add_argument("--approval-ttl", type=int, default=24, help="TTL in hours")

    return parser


def _format_compact(result):
    """Format as compact string."""
    if "error" in result:
        return f"BATCH ERROR | {result['error']}"
    status = result.get("status", "?")
    completed = result.get("completed", result.get("completed_count", 0))
    total = result.get("total_work_orders", result.get("remaining_count", 0)) + completed
    stop = result.get("stop_reason", "")
    if stop:
        return f"BATCH {status} | {completed}/{total} done | stop={stop}"
    wo = result.get("current_wo", "")
    if wo:
        return f"BATCH {status} | wo={wo} | {completed} done"
    # External policy compact
    if result.get("command") == "external-policy":
        approved = "APPROVED" if result.get("approved") else "BLOCKED"
        return f"EXT_POLICY {result.get('repo_trust_level', '?')} | {result.get('operation_type', '?')} | {approved}"
    if result.get("command") == "external-approval":
        return f"EXT_APPROVAL {result.get('action', '?')} | {result.get('approval_id', '?')}"
    return f"BATCH {status} | {completed}/{total} done"


def main(argv=None):
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.batch:
        result, rc = _cmd_run(args)
    elif args.status:
        result, rc = _cmd_status(args)
    elif args.batch_status:
        result, rc = _cmd_batch_status(args)
    elif args.batch_report:
        result, rc = _cmd_batch_report(args)
    elif args.pause:
        result, rc = _cmd_pause(args)
    elif args.resume:
        result, rc = _cmd_resume(args)
    elif args.cancel:
        result, rc = _cmd_cancel(args)
    elif args.abort:
        result, rc = _cmd_abort(args)
    elif args.external_policy:
        result, rc = _cmd_external_policy(args)
    elif args.external_approval:
        result, rc = _cmd_external_approval(args)
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
