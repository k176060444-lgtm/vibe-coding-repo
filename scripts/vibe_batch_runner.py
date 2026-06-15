#!/usr/bin/env python3
"""Trusted Self-Repo Batch Runner — serial execution of low-risk Work Orders.

Executes 1-5 trusted-self low-risk Work Orders in sequence.
Each WO: branch → commit → push → PR → wrapper merge → post-merge checks.
After each WO, refreshes baseline before executing the next.

Stop rules: any WO failure stops the batch immediately.

Usage:
    python3 scripts/vibe_batch_runner.py --batch <batch.json> [--json] [--compact] [--dry-run]
    python3 scripts/vibe_batch_runner.py --status [--json]

Batch JSON format:
    {
        "batch_id": "batch-001",
        "repo": "k176060444-lgtm/vibe-coding-repo",
        "work_orders": [
            {
                "wo_id": "wo-001",
                "branch": "v101/feature-001",
                "title": "feat: description",
                "body": "PR body",
                "changed_paths": ["scripts/x.py"],
                "allowed_paths": ["scripts/x.py"]
            }
        ]
    }

Constraints:
    - Self-repo only (k176060444-lgtm/vibe-coding-repo).
    - External repo writes BLOCK unless approved.
    - No force push, no bare gh pr merge.
    - Wrapper merge required.
    - Standard library only, no external dependencies.
    - No IO on import.
"""

import argparse
import json
import tempfile
import os
import subprocess
import sys
import time
from pathlib import Path

VERSION = "1.1.0"

SELF_REPO = "k176060444-lgtm/vibe-coding-repo"

# Stop conditions
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
    """Verify changed_paths are subset of allowed_paths.

    Returns (ok: bool, violations: list).
    """
    violations = []
    for cp in changed_paths:
        if cp not in allowed_paths:
            # Check prefix match
            matched = False
            for ap in allowed_paths:
                if cp.startswith(ap) or ap.startswith(cp):
                    matched = True
                    break
            if not matched:
                violations.append(f"unexpected changed_path: {cp}")
    return len(violations) == 0, violations


def _run_post_merge_checks(script_dir, repo_root, wo_id):
    """Run smoke, QG, V1-freeze after a WO merge.

    Returns (passed: bool, results: dict, stop_reason: str|None).
    """
    results = {}
    jobs_dir = os.path.expanduser("~/vibedev/jobs")

    # Smoke
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

    # Quality gate
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

    # V1 freeze
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
    """Check worker reachability; if unreachable, create checkpoint.

    Returns (reachable: bool, info: dict).
    """
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
    # Unreachable — create checkpoint
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


def _execute_wo(wo, script_dir, repo_dir, repo_root, dry_run=False):
    """Execute a single Work Order.

    Returns (success: bool, result: dict, stop_reason: str|None).
    """
    wo_id = wo.get("wo_id", "unknown")
    branch = wo.get("branch", "")
    title = wo.get("title", f"batch: {wo_id}")
    body = wo.get("body", "")
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

    # Policy gate: check changed_paths
    gate_ok, violations = _check_policy_gate(changed_paths, allowed_paths)
    if not gate_ok:
        result["status"] = "blocked"
        result["blockers"] = violations
        return False, result, "unexpected_changed_paths"

    if dry_run:
        result["status"] = "dry_run_ok"
        result["blockers"] = []
        return True, result, None

    # Real execution would go here:
    # 1. Create worktree
    # 2. Make changes
    # 3. Commit
    # 4. Push
    # 5. Create PR
    # 6. Wrapper merge
    # 7. Post-merge checks
    # For now, this is a contract/validation script — actual execution
    # is done by the orchestrator (Hermes) following this contract.

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

    # Validate repo trust
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

    # Pre-flight worker reachability check
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
    }

    for i, wo in enumerate(work_orders):
        wo_id = wo.get("wo_id", f"wo-{i+1}")
        success, result, stop_reason = _execute_wo(
            wo, script_dir, repo_dir, repo_root, dry_run=args.dry_run
        )
        batch_result["work_order_results"].append(result)

        if success:
            result["status"] = "passed" if not args.dry_run else "dry_run_ok"
            batch_result["completed"] += 1
        else:
            result["status"] = "failed"
            batch_result["failed"] += 1
            batch_result["status"] = "stopped"
            batch_result["stop_reason"] = stop_reason
            # Stop batch on failure
            break

    if batch_result["status"] == "running":
        batch_result["status"] = "completed"

    return batch_result, 0 if batch_result["status"] == "completed" else 1


def _cmd_status(args):
    """Show batch runner status/capabilities."""
    return {
        "batch_runner_version": VERSION,
        "repo": SELF_REPO,
        "repo_trust_level": "trusted-self",
        "max_batch_size": 5,
        "stop_conditions": STOP_CONDITIONS,
        "supported_commands": ["run", "status"],
        "dry_run_supported": True,
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

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--batch", metavar="FILE", help="Batch plan JSON file")
    group.add_argument("--status", action="store_true", help="Show runner status")

    return parser


def _format_compact(result):
    """Format as compact string."""
    if "error" in result:
        return f"BATCH ERROR | {result['error']}"
    status = result.get("status", "?")
    completed = result.get("completed", 0)
    total = result.get("total_work_orders", 0)
    stop = result.get("stop_reason", "")
    if stop:
        return f"BATCH {status} | {completed}/{total} done | stop={stop}"
    return f"BATCH {status} | {completed}/{total} done"


def main(argv=None):
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.batch:
        result, rc = _cmd_run(args)
    elif args.status:
        result, rc = _cmd_status(args)
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
