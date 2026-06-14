#!/usr/bin/env python3
"""Toolchain Smoke Suite v1 - Local smoke test for all orchestrator tools.

Usage:
    python scripts/test_toolchain_smoke.py [--jobs-dir <dir>]

Tests:
    1. Command Router: help, snapshot, advisor, dispatch, batch-plan
    2. Health Check: all checks pass
    3. Operator Snapshot: returns valid JSON
    4. Queue Advisor: returns valid JSON
    5. Dispatch Planner: returns valid JSON
    6. Batch Plan: returns valid JSON

Constraints:
    - Read-only, no file modifications
    - No network writes
    - Standard library only
    - Must pass on clean repo state
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _run_test(name, test_fn):
    """Run a test and return (name, passed, message)."""
    try:
        result = test_fn()
        return (name, result["passed"], result.get("message", ""))
    except Exception as e:
        return (name, False, str(e))


def _run_script(script_path, args, timeout=30):
    """Run a script and return (returncode, stdout, stderr)."""
    try:
        cmd = [sys.executable, str(script_path)] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (1, "", "timeout")
    except (OSError, FileNotFoundError) as e:
        return (1, "", str(e))


def _test_command_router_help(script_dir):
    """Test command router help."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["help"])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    if "vibe_command_router" not in stdout:
        return {"passed": False, "message": "help text missing"}
    
    return {"passed": True, "message": "help works"}


def _test_command_router_snapshot(script_dir, jobs_dir):
    """Test command router snapshot."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["snapshot", "--compact"])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    if "Operator Snapshot" not in stdout:
        return {"passed": False, "message": "snapshot output missing"}
    
    return {"passed": True, "message": "snapshot works"}


def _test_command_router_advisor(script_dir, jobs_dir):
    """Test command router advisor."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["advisor", "--json"])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"total={data.get('total_jobs', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_command_router_dispatch(script_dir, jobs_dir):
    """Test command router dispatch."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["dispatch", "--json"])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"recommended={data.get('recommended_action', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_command_router_batch_plan(script_dir, jobs_dir):
    """Test command router batch plan."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["batch-plan", "--json"])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"tasks={data.get('task_count', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_health_check(script_dir, jobs_dir):
    """Test health check."""
    path = script_dir / "vibe_health_check.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["--json", "--jobs-dir", jobs_dir])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        overall = data.get("overall", "UNKNOWN")
        return {"passed": overall == "PASS", "message": f"overall={overall}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_operator_snapshot(script_dir, jobs_dir):
    """Test operator snapshot."""
    path = script_dir / "vibe_operator_snapshot.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["--json", "--jobs-dir", jobs_dir])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"total={data.get('jobs_summary', {}).get('total_jobs', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_queue_advisor(script_dir, jobs_dir):
    """Test queue advisor."""
    path = script_dir / "vibe_queue_advisor.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["--json", "--jobs-dir", jobs_dir])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"total={data.get('total_jobs', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_dispatch_planner(script_dir, jobs_dir):
    """Test dispatch planner."""
    path = script_dir / "vibe_dispatch_planner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["--json", "--jobs-dir", jobs_dir])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"recommended={data.get('recommended_action', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_batch_plan(script_dir, jobs_dir):
    """Test batch plan."""
    path = script_dir / "vibe_batch_plan.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["--json", "--jobs-dir", jobs_dir])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"tasks={data.get('task_count', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}



def _test_recommendation_consistency(script_dir, jobs_dir):
    """Test that snapshot, dispatch, and batch-plan recommendations are consistent."""
    import json as _json
    
    # Run snapshot
    rc1, out1, _ = _run_script(script_dir / "vibe_operator_snapshot.py", ["--json", "--jobs-dir", jobs_dir])
    # Run dispatch
    rc2, out2, _ = _run_script(script_dir / "vibe_dispatch_planner.py", ["--json", "--jobs-dir", jobs_dir])
    # Run batch plan
    rc3, out3, _ = _run_script(script_dir / "vibe_batch_plan.py", ["--json", "--jobs-dir", jobs_dir])
    
    if rc1 != 0 or rc2 != 0 or rc3 != 0:
        return {"passed": False, "message": "one or more scripts failed to run"}
    
    try:
        snap = _json.loads(out1)
        disp = _json.loads(out2)
        batch = _json.loads(out3)
    except _json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON from one or more scripts"}
    
    snap_action = snap.get("recommended_next_action", "")
    disp_action = disp.get("recommended_action", "")
    batch_tasks = batch.get("task_count", -1)
    
    # Consistency rule: if snapshot says queue_clean, dispatch should too
    if "queue_clean" in snap_action and disp_action != "queue_clean":
        return {"passed": False, "message": "inconsistent: snapshot=%s dispatch=%s" % (snap_action, disp_action)}
    
    # Consistency rule: if batch has 0 tasks and dispatch says queue_clean, all agree
    if batch_tasks == 0 and disp_action == "queue_clean" and "queue_clean" in snap_action:
        return {"passed": True, "message": "consistent: all report queue_clean/0-tasks"}
    
    # If batch has tasks, dispatch should not be queue_clean
    if batch_tasks > 0 and disp_action == "queue_clean":
        return {"passed": False, "message": "inconsistent: batch=%d tasks but dispatch=queue_clean" % batch_tasks}
    
    return {"passed": True, "message": "snapshot=%s dispatch=%s batch=%d" % (snap_action, disp_action, batch_tasks)}

def run_tests(jobs_dir=None):
    """Run all smoke tests."""
    if jobs_dir is None:
        jobs_dir = os.path.expanduser("~/vibedev/jobs")
    
    script_dir = Path(__file__).parent
    
    tests = []
    
    # Test 1: Command Router help
    tests.append(_run_test("command_router_help", lambda: _test_command_router_help(script_dir)))
    
    # Test 2: Command Router snapshot
    tests.append(_run_test("command_router_snapshot", lambda: _test_command_router_snapshot(script_dir, jobs_dir)))
    
    # Test 3: Command Router advisor
    tests.append(_run_test("command_router_advisor", lambda: _test_command_router_advisor(script_dir, jobs_dir)))
    
    # Test 4: Command Router dispatch
    tests.append(_run_test("command_router_dispatch", lambda: _test_command_router_dispatch(script_dir, jobs_dir)))
    
    # Test 5: Command Router batch plan
    tests.append(_run_test("command_router_batch_plan", lambda: _test_command_router_batch_plan(script_dir, jobs_dir)))
    
    # Test 6: Health Check
    tests.append(_run_test("health_check", lambda: _test_health_check(script_dir, jobs_dir)))
    
    # Test 7: Operator Snapshot
    tests.append(_run_test("operator_snapshot", lambda: _test_operator_snapshot(script_dir, jobs_dir)))
    
    # Test 8: Queue Advisor
    tests.append(_run_test("queue_advisor", lambda: _test_queue_advisor(script_dir, jobs_dir)))
    
    # Test 9: Dispatch Planner
    tests.append(_run_test("dispatch_planner", lambda: _test_dispatch_planner(script_dir, jobs_dir)))
    
    # Test 10: Batch Plan
    tests.append(_run_test("batch_plan", lambda: _test_batch_plan(script_dir, jobs_dir)))
    
    # Test 11: Recommendation Consistency
    tests.append(_run_test("recommendation_consistency", lambda: _test_recommendation_consistency(script_dir, jobs_dir)))
    
    return tests


def build_parser():
    parser = argparse.ArgumentParser(
        prog="test_toolchain_smoke",
        description="Toolchain Smoke Suite v1 - Local smoke test for all orchestrator tools.",
    )
    parser.add_argument("--json", dest="output_json", action="store_true", default=False)
    parser.add_argument("--jobs-dir", default=None)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    jobs_dir = args.jobs_dir or os.path.expanduser("~/vibedev/jobs")
    
    tests = run_tests(jobs_dir)
    
    # Count results
    passed_count = sum(1 for _, passed, _ in tests if passed)
    failed_count = sum(1 for _, passed, _ in tests if not passed)
    
    # Determine overall result
    overall = "PASS" if failed_count == 0 else "FAIL"
    
    if args.output_json:
        result = {
            "overall": overall,
            "passed": passed_count,
            "failed": failed_count,
            "tests": [
                {"name": name, "passed": passed, "message": msg}
                for name, passed, msg in tests
            ],
        }
        print(json.dumps(result, indent=2))
    else:
        print("=" * 40)
        print("  Toolchain Smoke Suite v1")
        print("=" * 40)
        for name, passed, msg in tests:
            icon = "✓" if passed else "✗"
            status = "PASS" if passed else "FAIL"
            print(f"  {icon} {name}: {status} - {msg}")
        print("-" * 40)
        print(f"  Overall: {overall} ({passed_count} passed, {failed_count} failed)")
        print("=" * 40)
    
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
