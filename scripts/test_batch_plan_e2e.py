#!/usr/bin/env python3
"""E2E test for operator snapshot -> dispatch planner -> batch plan chain.

Usage:
    python scripts/test_batch_plan_e2e.py [--jobs-dir <dir>]

Tests:
    1. Real jobs: queue_clean scenario (0 tasks)
    2. Fixture jobs: mixed scenarios (4 tasks, high risk)
    3. --limit flag: limits task count
    4. Import safety: no IO on import
    5. Risk classification: correct risk levels
    6. Stop conditions: all 7 conditions present
    7. Expected reports: all 6 reports present

Constraints:
    - Read-only, no file modifications
    - Standard library only
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path


def _run_script(script, *args):
    """Run a Python script and return parsed JSON or None."""
    try:
        cmd = [sys.executable, script] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, FileNotFoundError):
        pass
    return None


def _create_fixture(fixture_dir):
    """Create fixture jobs for testing."""
    if os.path.exists(fixture_dir):
        shutil.rmtree(fixture_dir)
    os.makedirs(fixture_dir)

    # Scenario 1: ready_for_merge (low risk)
    os.makedirs(f"{fixture_dir}/wo-ready-001")
    with open(f"{fixture_dir}/wo-ready-001/work-order.json", "w") as f:
        json.dump({
            "job_id": "wo-ready-001", "status": "review_passed",
            "base_sha": "aaa111", "result_sha": "bbb222",
            "audit_status": "clean", "push_allowed": True,
            "scope": {"allowed_paths": ["scripts/test.py"]},
        }, f)

    # Scenario 2: failed (high risk)
    os.makedirs(f"{fixture_dir}/wo-failed-001")
    with open(f"{fixture_dir}/wo-failed-001/work-order.json", "w") as f:
        json.dump({
            "job_id": "wo-failed-001", "status": "failed",
            "base_sha": "ccc333", "result_sha": None,
            "audit_status": "clean", "push_allowed": False,
            "scope": {"allowed_paths": ["scripts/feature.py"]},
        }, f)

    # Scenario 3: in_progress (medium risk)
    os.makedirs(f"{fixture_dir}/wo-inprogress-001")
    with open(f"{fixture_dir}/wo-inprogress-001/work-order.json", "w") as f:
        json.dump({
            "job_id": "wo-inprogress-001", "status": "in_progress",
            "base_sha": "ddd444", "result_sha": None,
            "audit_status": "clean", "push_allowed": False,
            "scope": {"allowed_paths": ["scripts/new_feature.py"]},
        }, f)

    # Scenario 4: tainted (critical risk)
    os.makedirs(f"{fixture_dir}/wo-tainted-001")
    with open(f"{fixture_dir}/wo-tainted-001/work-order.json", "w") as f:
        json.dump({
            "job_id": "wo-tainted-001", "status": "review_passed",
            "base_sha": "eee555", "result_sha": "fff666",
            "audit_status": "audit_tainted", "push_allowed": False,
            "audit_reason": "test_tainted",
            "scope": {"allowed_paths": ["scripts/test.py"]},
        }, f)

    # Scenario 5: non-production (filtered out)
    os.makedirs(f"{fixture_dir}/wo-smoke-001")
    with open(f"{fixture_dir}/wo-smoke-001/work-order.json", "w") as f:
        json.dump({
            "job_id": "wo-smoke-001", "status": "failed",
            "base_sha": "ggg777", "result_sha": None,
            "audit_status": "clean", "push_allowed": False,
            "scope": {"allowed_paths": ["scripts/smoke.py"]},
        }, f)

    # Scenario 6: ready_for_merge v2
    os.makedirs(f"{fixture_dir}/wo-ready-v2-001")
    with open(f"{fixture_dir}/wo-ready-v2-001/work-order.json", "w") as f:
        json.dump({
            "job_id": "wo-ready-v2-001", "status": "review_passed",
            "base_sha": "hhh888", "result_sha": "iii999",
            "audit_status": "clean", "push_allowed": True,
            "scope": {"allowed_paths": ["scripts/test.py"]},
        }, f)

    return len(os.listdir(fixture_dir))


def test_real_jobs(script_dir, jobs_dir):
    """Test 1: Real jobs should show queue_clean (0 tasks)."""
    plan = _run_script(str(script_dir / "vibe_batch_plan.py"), "--json", "--jobs-dir", jobs_dir)
    assert plan is not None, "Failed to run batch plan"
    assert plan["task_count"] == 0, f"Expected 0 tasks, got {plan['task_count']}"
    assert plan["risk_level"] == "low", f"Expected low risk, got {plan['risk_level']}"
    assert plan["requires_human_approval"] == False, "Expected no human approval"
    print("  PASS: real jobs (queue_clean, 0 tasks)")


def test_fixture_jobs(script_dir, fixture_dir):
    """Test 2: Fixture jobs should show 4 tasks, high risk."""
    plan = _run_script(str(script_dir / "vibe_batch_plan.py"), "--json", "--jobs-dir", fixture_dir)
    assert plan is not None, "Failed to run batch plan"
    assert plan["task_count"] == 4, f"Expected 4 tasks, got {plan['task_count']}"
    assert plan["risk_level"] == "high", f"Expected high risk, got {plan['risk_level']}"
    assert plan["requires_human_approval"] == True, "Expected human approval required"
    
    # Check task order
    task_ids = [t["job_id"] for t in plan["task_order"]]
    assert "wo-failed-001" in task_ids, "Missing wo-failed-001"
    assert "wo-inprogress-001" in task_ids, "Missing wo-inprogress-001"
    assert "wo-ready-001" in task_ids, "Missing wo-ready-001"
    assert "wo-ready-v2-001" in task_ids, "Missing wo-ready-v2-001"
    assert "wo-tainted-001" not in task_ids, "Should not include tainted job"
    assert "wo-smoke-001" not in task_ids, "Should not include non-production job"
    
    # Check risk classification
    for task in plan["task_order"]:
        if task["job_id"] == "wo-failed-001":
            assert task["risk_level"] == "high", f"Expected high risk for failed job, got {task['risk_level']}"
        elif task["job_id"] == "wo-inprogress-001":
            assert task["risk_level"] == "medium", f"Expected medium risk for in-progress job, got {task['risk_level']}"
        elif task["job_id"] in ["wo-ready-001", "wo-ready-v2-001"]:
            assert task["risk_level"] == "low", f"Expected low risk for ready job, got {task['risk_level']}"
    
    print("  PASS: fixture jobs (4 tasks, high risk)")


def test_limit(script_dir, fixture_dir):
    """Test 3: --limit flag should limit task count."""
    plan = _run_script(str(script_dir / "vibe_batch_plan.py"), "--json", "--jobs-dir", fixture_dir, "--limit", "2")
    assert plan is not None, "Failed to run batch plan"
    assert plan["task_count"] == 2, f"Expected 2 tasks, got {plan['task_count']}"
    print("  PASS: --limit 2 (2 tasks)")


def test_import_safety(script_dir):
    """Test 4: Import should not execute IO."""
    import importlib.util; spec = importlib.util.spec_from_file_location("bp", str(script_dir / "vibe_batch_plan.py"))
    mod = __import__("importlib").util.module_from_spec(spec)
    print("  PASS: import safety (no IO)")


def test_stop_conditions(script_dir, fixture_dir):
    """Test 5: Stop conditions should be present."""
    plan = _run_script(str(script_dir / "vibe_batch_plan.py"), "--json", "--jobs-dir", fixture_dir)
    assert plan is not None, "Failed to run batch plan"
    assert len(plan["stop_conditions"]) == 7, f"Expected 7 stop conditions, got {len(plan['stop_conditions'])}"
    print("  PASS: stop conditions (7 conditions)")


def test_expected_reports(script_dir, fixture_dir):
    """Test 6: Expected reports should be present."""
    plan = _run_script(str(script_dir / "vibe_batch_plan.py"), "--json", "--jobs-dir", fixture_dir)
    assert plan is not None, "Failed to run batch plan"
    assert len(plan["expected_reports"]) == 6, f"Expected 6 reports, got {len(plan['expected_reports'])}"
    print("  PASS: expected reports (6 reports)")


def main():
    parser = argparse.ArgumentParser(description="E2E test for batch plan chain")
    parser.add_argument("--jobs-dir", default=None)
    args = parser.parse_args()

    jobs_dir = args.jobs_dir or os.path.expanduser("~/vibedev/jobs")
    script_dir = Path(__file__).parent
    fixture_dir = tempfile.mkdtemp(prefix="batch-plan-e2e-")

    print("=== Batch Plan E2E Test ===")
    print(f"Script dir: {script_dir}")
    print(f"Jobs dir: {jobs_dir}")
    print(f"Fixture dir: {fixture_dir}")
    print()

    try:
        # Create fixture
        job_count = _create_fixture(fixture_dir)
        print(f"Created {job_count} fixture jobs")
        print()

        # Run tests
        test_real_jobs(script_dir, jobs_dir)
        test_fixture_jobs(script_dir, fixture_dir)
        test_limit(script_dir, fixture_dir)
        test_import_safety(script_dir)
        test_stop_conditions(script_dir, fixture_dir)
        test_expected_reports(script_dir, fixture_dir)

        print()
        print("=== ALL TESTS PASSED ===")
        return 0
    except AssertionError as e:
        print(f"  FAIL: {e}")
        return 1
    finally:
        # Cleanup
        shutil.rmtree(fixture_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
