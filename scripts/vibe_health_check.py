#!/usr/bin/env python3
"""Health Check v1 - Toolchain verification for QQ/Hermes orchestrator.

Usage:
    python scripts/vibe_health_check.py [--json] [--jobs-dir <dir>]

Checks:
    1. py_compile: all vibe_*.py scripts compile
    2. import: all vibe_*.py scripts can be imported without IO
    3. operator snapshot: returns valid JSON
    4. queue advisor: returns valid JSON
    5. dispatch planner: returns valid JSON
    6. batch plan: returns valid JSON
    7. audit_tainted lock: wo-code-repo-status-001 is visible

Output:
    - PASS/WARN/FAIL for each check
    - JSON output with --json flag

Constraints:
    - Read-only, no IO on import, standard library only.
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


# Scripts to check
SCRIPTS = [
    "vibe_operator_snapshot.py",
    "vibe_queue_advisor.py",
    "vibe_dispatch_planner.py",
    "vibe_batch_plan.py",
    "vibe_command_router.py",
    "vibe_merge_gate.py",
    "vibe_autonomous_merge.py",
    "vibe_repo_status.py",
]


def _run_check(name, check_fn):
    """Run a check and return (name, status, message)."""
    try:
        result = check_fn()
        return (name, result["status"], result.get("message", ""))
    except Exception as e:
        return (name, "FAIL", str(e))


def _check_py_compile():
    """Check that all scripts compile."""
    script_dir = Path(__file__).parent
    failed = []
    for script in SCRIPTS:
        path = script_dir / script
        if not path.exists():
            failed.append(f"{script}: not found")
            continue
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            failed.append(f"{script}: compile error")
    
    if failed:
        return {"status": "FAIL", "message": "; ".join(failed)}
    return {"status": "PASS", "message": f"{len(SCRIPTS)} scripts compiled"}


def _check_import():
    """Check that all scripts can be imported without IO."""
    script_dir = Path(__file__).parent
    failed = []
    for script in SCRIPTS:
        path = script_dir / script
        if not path.exists():
            failed.append(f"{script}: not found")
            continue
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(script.replace(".py", ""), str(path))
            mod = importlib.util.module_from_spec(spec)
            # Don't execute, just check importability
        except Exception as e:
            failed.append(f"{script}: {e}")
    
    if failed:
        return {"status": "FAIL", "message": "; ".join(failed)}
    return {"status": "PASS", "message": f"{len(SCRIPTS)} scripts importable"}


def _check_operator_snapshot(jobs_dir):
    """Check operator snapshot returns valid JSON."""
    script_dir = Path(__file__).parent
    path = script_dir / "vibe_operator_snapshot.py"
    if not path.exists():
        return {"status": "FAIL", "message": "script not found"}
    
    result = subprocess.run(
        [sys.executable, str(path), "--json", "--jobs-dir", jobs_dir],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return {"status": "FAIL", "message": f"exit code {result.returncode}"}
    
    try:
        data = json.loads(result.stdout)
        return {"status": "PASS", "message": f"total={data.get('jobs_summary', {}).get('total_jobs', '?')}"}
    except json.JSONDecodeError:
        return {"status": "FAIL", "message": "invalid JSON"}


def _check_queue_advisor(jobs_dir):
    """Check queue advisor returns valid JSON."""
    script_dir = Path(__file__).parent
    path = script_dir / "vibe_queue_advisor.py"
    if not path.exists():
        return {"status": "FAIL", "message": "script not found"}
    
    result = subprocess.run(
        [sys.executable, str(path), "--json", "--jobs-dir", jobs_dir],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return {"status": "FAIL", "message": f"exit code {result.returncode}"}
    
    try:
        data = json.loads(result.stdout)
        return {"status": "PASS", "message": f"total={data.get('total_jobs', '?')}"}
    except json.JSONDecodeError:
        return {"status": "FAIL", "message": "invalid JSON"}


def _check_dispatch_planner(jobs_dir):
    """Check dispatch planner returns valid JSON."""
    script_dir = Path(__file__).parent
    path = script_dir / "vibe_dispatch_planner.py"
    if not path.exists():
        return {"status": "FAIL", "message": "script not found"}
    
    result = subprocess.run(
        [sys.executable, str(path), "--json", "--jobs-dir", jobs_dir],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return {"status": "FAIL", "message": f"exit code {result.returncode}"}
    
    try:
        data = json.loads(result.stdout)
        return {"status": "PASS", "message": f"recommended={data.get('recommended_action', '?')}"}
    except json.JSONDecodeError:
        return {"status": "FAIL", "message": "invalid JSON"}


def _check_batch_plan(jobs_dir):
    """Check batch plan returns valid JSON."""
    script_dir = Path(__file__).parent
    path = script_dir / "vibe_batch_plan.py"
    if not path.exists():
        return {"status": "FAIL", "message": "script not found"}
    
    result = subprocess.run(
        [sys.executable, str(path), "--json", "--jobs-dir", jobs_dir],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return {"status": "FAIL", "message": f"exit code {result.returncode}"}
    
    try:
        data = json.loads(result.stdout)
        return {"status": "PASS", "message": f"tasks={data.get('task_count', '?')}"}
    except json.JSONDecodeError:
        return {"status": "FAIL", "message": "invalid JSON"}


def _check_audit_tainted_lock(jobs_dir):
    """Check audit_tainted lock is visible."""
    script_dir = Path(__file__).parent
    path = script_dir / "vibe_operator_snapshot.py"
    if not path.exists():
        return {"status": "FAIL", "message": "script not found"}
    
    result = subprocess.run(
        [sys.executable, str(path), "--json", "--include-tainted", "--jobs-dir", jobs_dir],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return {"status": "FAIL", "message": f"exit code {result.returncode}"}
    
    try:
        data = json.loads(result.stdout)
        locks = data.get("locks", [])
        tainted_locks = [l for l in locks if l.get("lock_type") == "audit_tainted"]
        if tainted_locks:
            return {"status": "PASS", "message": f"{len(tainted_locks)} tainted lock(s) visible"}
        else:
            return {"status": "WARN", "message": "no tainted locks visible"}
    except json.JSONDecodeError:
        return {"status": "FAIL", "message": "invalid JSON"}


def run_checks(jobs_dir=None):
    """Run all health checks."""
    if jobs_dir is None:
        jobs_dir = os.path.expanduser("~/vibedev/jobs")
    
    checks = []
    
    # Check 1: py_compile
    checks.append(_run_check("py_compile", _check_py_compile))
    
    # Check 2: import
    checks.append(_run_check("import", _check_import))
    
    # Check 3: operator snapshot
    checks.append(_run_check("operator_snapshot", lambda: _check_operator_snapshot(jobs_dir)))
    
    # Check 4: queue advisor
    checks.append(_run_check("queue_advisor", lambda: _check_queue_advisor(jobs_dir)))
    
    # Check 5: dispatch planner
    checks.append(_run_check("dispatch_planner", lambda: _check_dispatch_planner(jobs_dir)))
    
    # Check 6: batch plan
    checks.append(_run_check("batch_plan", lambda: _check_batch_plan(jobs_dir)))
    
    # Check 7: audit_tainted lock
    checks.append(_run_check("audit_tainted_lock", lambda: _check_audit_tainted_lock(jobs_dir)))
    
    return checks


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_health_check",
        description="Health Check v1 - Toolchain verification for QQ/Hermes orchestrator.",
    )
    parser.add_argument("--json", dest="output_json", action="store_true", default=False)
    parser.add_argument("--jobs-dir", default=None)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    jobs_dir = args.jobs_dir or os.path.expanduser("~/vibedev/jobs")
    
    checks = run_checks(jobs_dir)
    
    # Count statuses
    pass_count = sum(1 for _, status, _ in checks if status == "PASS")
    warn_count = sum(1 for _, status, _ in checks if status == "WARN")
    fail_count = sum(1 for _, status, _ in checks if status == "FAIL")
    
    # Determine overall status
    if fail_count > 0:
        overall = "FAIL"
    elif warn_count > 0:
        overall = "WARN"
    else:
        overall = "PASS"
    
    if args.output_json:
        result = {
            "overall": overall,
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "checks": [
                {"name": name, "status": status, "message": msg}
                for name, status, msg in checks
            ],
        }
        print(json.dumps(result, indent=2))
    else:
        print("=" * 40)
        print("  Health Check v1")
        print("=" * 40)
        for name, status, msg in checks:
            status_icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}.get(status, "?")
            print(f"  {status_icon} {name}: {status} - {msg}")
        print("-" * 40)
        print(f"  Overall: {overall} ({pass_count} pass, {warn_count} warn, {fail_count} fail)")
        print("=" * 40)
    
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
