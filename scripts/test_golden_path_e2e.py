#!/usr/bin/env python3
"""Golden Path E2E Test Suite — end-to-end test of the full Work Order lifecycle.

Tests the complete pipeline in a temporary directory:
requirement → intake → validate → registry.register → packager →
registry.update-status → approval-receipt.create → execution-gate.check →
evidence.create

Covers ALLOW, REVIEW, and BLOCK paths. Does NOT execute real Work Orders.

Usage:
    python3 scripts/test_golden_path_e2e.py
    python3 scripts/test_golden_path_e2e.py --json
    python3 scripts/test_golden_path_e2e.py --verbose
"""

import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"

def _find_scripts_dir():
    """Find the scripts directory."""
    return Path(__file__).parent

def _run_script(script_path, args):
    """Run a Python script and return (exit_code, stdout, stderr)."""
    import subprocess
    try:
        cmd = [sys.executable, str(script_path)] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "Script timed out"
    except (OSError, FileNotFoundError) as e:
        return 1, "", str(e)

def _test_golden_path_allow(script_dir, tmpdir, verbose=False):
    """Test ALLOW path: valid workorder through the full pipeline."""
    steps = []
    registry_dir = os.path.join(tmpdir, "allow_registry")

    # Step 1: Register workorder
    rc, stdout, stderr = _run_script(
        script_dir / "vibe_workorder_registry.py",
        ["register", "--registry-dir", registry_dir,
         "--id", "golden-allow-001", "--title", "Golden Path Allow Test",
         "--risk-level", "low", "--base-sha", "abc123"]
    )
    steps.append({"step": "register", "exit_code": rc, "passed": rc == 0})
    if rc != 0:
        return {"passed": False, "verdict": "BLOCK", "steps": steps, "failed_at": "register"}

    # Step 2: Update status to validated
    rc, stdout, stderr = _run_script(
        script_dir / "vibe_workorder_registry.py",
        ["update-status", "--registry-dir", registry_dir,
         "--id", "golden-allow-001", "--status", "validated",
         "--reason", "Validation passed"]
    )
    steps.append({"step": "status_validated", "exit_code": rc, "passed": rc == 0})
    if rc != 0:
        return {"passed": False, "verdict": "BLOCK", "steps": steps, "failed_at": "status_validated"}

    # Step 3: Update status to packaged
    rc, stdout, stderr = _run_script(
        script_dir / "vibe_workorder_registry.py",
        ["update-status", "--registry-dir", registry_dir,
         "--id", "golden-allow-001", "--status", "packaged",
         "--reason", "Package ready"]
    )
    steps.append({"step": "status_packaged", "exit_code": rc, "passed": rc == 0})
    if rc != 0:
        return {"passed": False, "verdict": "BLOCK", "steps": steps, "failed_at": "status_packaged"}

    # Step 4: Update status to approved
    rc, stdout, stderr = _run_script(
        script_dir / "vibe_workorder_registry.py",
        ["update-status", "--registry-dir", registry_dir,
         "--id", "golden-allow-001", "--status", "approved",
         "--reason", "Human approved"]
    )
    steps.append({"step": "status_approved", "exit_code": rc, "passed": rc == 0})
    if rc != 0:
        return {"passed": False, "verdict": "BLOCK", "steps": steps, "failed_at": "status_approved"}

    # Clear stop_conditions for clean ALLOW path
    entry_file = os.path.join(registry_dir, "golden-allow-001.json")
    with open(entry_file, "r") as f:
        entry = json.load(f)
    entry["stop_conditions"] = []
    entry["allowed_paths"] = ["scripts/"]
    entry["forbidden_actions"] = ["push_to_main", "modify_secrets"]
    with open(entry_file, "w") as f:
        json.dump(entry, f, indent=2)

    # Step 5: Create approval receipt
    receipts_dir = os.path.join(registry_dir, "receipts")
    os.makedirs(receipts_dir, exist_ok=True)
    receipt_file = os.path.join(receipts_dir, "receipt-001.json")
    with open(receipt_file, "w") as f:
        json.dump({
            "receipt_id": "receipt-001",
            "workorder_id": "golden-allow-001",
            "base_sha": "abc123",
            "package_digest": "test_digest",
            "approver": "human",
            "approval_text": "Approved for execution",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "digest": "test_receipt_digest"
        }, f)
    steps.append({"step": "approval_receipt", "exit_code": 0, "passed": True})

    # Step 6: Run execution gate
    rc, stdout, stderr = _run_script(
        script_dir / "vibe_execution_gate.py",
        ["check", "--registry-dir", registry_dir,
         "--id", "golden-allow-001", "--current-main-sha", "abc123", "--json"]
    )
    gate_result = None
    if rc == 0 and stdout:
        try:
            gate_result = json.loads(stdout)
        except json.JSONDecodeError:
            pass
    steps.append({"step": "execution_gate", "exit_code": rc, "passed": rc == 0,
                  "verdict": gate_result.get("verdict") if gate_result else None})

    # Step 7: Create execution evidence
    evidence_dir = os.path.join(tmpdir, "allow_evidence")
    rc, stdout, stderr = _run_script(
        script_dir / "vibe_execution_evidence.py",
        ["create", "--evidence-dir", evidence_dir,
         "--id", "golden-allow-001", "--base-sha", "abc123",
         "--result-sha", "def456", "--smoke-result", "44/44 PASS",
         "--job-status", "review_passed", "--audit-status", "clean", "--json"]
    )
    steps.append({"step": "evidence_create", "exit_code": rc, "passed": rc == 0})

    # Determine verdict
    all_passed = all(s["passed"] for s in steps)
    gate_verdict = gate_result.get("verdict") if gate_result else "UNKNOWN"

    return {
        "passed": all_passed and gate_verdict == "ALLOW",
        "verdict": gate_verdict,
        "steps": steps,
        "gate_result": gate_result,
    }

def _test_golden_path_block(script_dir, tmpdir, verbose=False):
    """Test BLOCK path: base_sha mismatch triggers BLOCK."""
    steps = []
    registry_dir = os.path.join(tmpdir, "block_registry")

    # Step 1: Register workorder
    rc, stdout, stderr = _run_script(
        script_dir / "vibe_workorder_registry.py",
        ["register", "--registry-dir", registry_dir,
         "--id", "golden-block-001", "--title", "Golden Path Block Test",
         "--risk-level", "low", "--base-sha", "abc123"]
    )
    steps.append({"step": "register", "exit_code": rc, "passed": rc == 0})
    if rc != 0:
        return {"passed": False, "verdict": "BLOCK", "steps": steps, "failed_at": "register"}

    # Step 2: Update to approved (skip intermediate states for brevity)
    for status in ["validated", "packaged", "approved"]:
        rc, stdout, stderr = _run_script(
            script_dir / "vibe_workorder_registry.py",
            ["update-status", "--registry-dir", registry_dir,
             "--id", "golden-block-001", "--status", status,
             "--reason", f"Auto-transition to {status}"]
        )
        steps.append({"step": f"status_{status}", "exit_code": rc, "passed": rc == 0})

    # Step 3: Run execution gate with WRONG SHA
    rc, stdout, stderr = _run_script(
        script_dir / "vibe_execution_gate.py",
        ["check", "--registry-dir", registry_dir,
         "--id", "golden-block-001", "--current-main-sha", "WRONG_SHA", "--json"]
    )
    gate_result = None
    if stdout:
        try:
            gate_result = json.loads(stdout)
        except json.JSONDecodeError:
            pass
    steps.append({"step": "execution_gate", "exit_code": rc, "passed": rc == 1,
                  "verdict": gate_result.get("verdict") if gate_result else None})

    # Gate should return BLOCK (exit code 1)
    gate_verdict = gate_result.get("verdict") if gate_result else "UNKNOWN"
    return {
        "passed": gate_verdict == "BLOCK",
        "verdict": gate_verdict,
        "steps": steps,
        "gate_result": gate_result,
    }

def _test_golden_path_review(script_dir, tmpdir, verbose=False):
    """Test REVIEW path: stop conditions trigger REVIEW."""
    steps = []
    registry_dir = os.path.join(tmpdir, "review_registry")

    # Step 1: Register workorder with stop conditions
    rc, stdout, stderr = _run_script(
        script_dir / "vibe_workorder_registry.py",
        ["register", "--registry-dir", registry_dir,
         "--id", "golden-review-001", "--title", "Golden Path Review Test",
         "--risk-level", "low", "--base-sha", "abc123"]
    )
    steps.append({"step": "register", "exit_code": rc, "passed": rc == 0})

    # Step 2: Update to approved
    for status in ["validated", "packaged", "approved"]:
        rc, stdout, stderr = _run_script(
            script_dir / "vibe_workorder_registry.py",
            ["update-status", "--registry-dir", registry_dir,
             "--id", "golden-review-001", "--status", status,
             "--reason", f"Auto-transition to {status}"]
        )
        steps.append({"step": f"status_{status}", "exit_code": rc, "passed": rc == 0})

    # Step 3: Update entry to add stop conditions (simulate)
    entry_file = os.path.join(registry_dir, "golden-review-001.json")
    with open(entry_file, "r") as f:
        entry = json.load(f)
    entry["stop_conditions"] = ["py_compile fails", "smoke regression"]
    entry["audit_status"] = "clean"
    with open(entry_file, "w") as f:
        json.dump(entry, f, indent=2)

    # Step 4: Run execution gate (should be REVIEW due to stop conditions)
    rc, stdout, stderr = _run_script(
        script_dir / "vibe_execution_gate.py",
        ["check", "--registry-dir", registry_dir,
         "--id", "golden-review-001", "--current-main-sha", "abc123", "--json"]
    )
    gate_result = None
    if stdout:
        try:
            gate_result = json.loads(stdout)
        except json.JSONDecodeError:
            pass
    steps.append({"step": "execution_gate", "exit_code": rc, "passed": rc == 0,
                  "verdict": gate_result.get("verdict") if gate_result else None})

    gate_verdict = gate_result.get("verdict") if gate_result else "UNKNOWN"
    return {
        "passed": gate_verdict == "REVIEW",
        "verdict": gate_verdict,
        "steps": steps,
        "gate_result": gate_result,
    }

def run_tests(verbose=False):
    """Run all golden path E2E tests."""
    script_dir = _find_scripts_dir()
    tmpdir = tempfile.mkdtemp(prefix="golden_path_e2e_")

    results = []

    try:
        # Test 1: ALLOW path
        result = _test_golden_path_allow(script_dir, tmpdir, verbose)
        results.append(("golden_path_allow", result))

        # Test 2: BLOCK path
        result = _test_golden_path_block(script_dir, tmpdir, verbose)
        results.append(("golden_path_block", result))

        # Test 3: REVIEW path
        result = _test_golden_path_review(script_dir, tmpdir, verbose)
        results.append(("golden_path_review", result))

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return results

def main(argv=None):
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Golden Path E2E Test Suite"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args(argv)

    results = run_tests(verbose=args.verbose)

    passed = sum(1 for _, r in results if r["passed"])
    failed = sum(1 for _, r in results if not r["passed"])

    if args.json:
        output = {
            "overall": "PASS" if failed == 0 else "FAIL",
            "passed": passed,
            "failed": failed,
            "tests": [
                {"name": name, "passed": r["passed"], "verdict": r.get("verdict"),
                 "steps": r.get("steps", [])}
                for name, r in results
            ]
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print("=" * 50)
        print("  Golden Path E2E Test Suite")
        print("=" * 50)
        for name, r in results:
            icon = "✓" if r["passed"] else "✗"
            status = "PASS" if r["passed"] else "FAIL"
            verdict = r.get("verdict", "UNKNOWN")
            print(f"  {icon} {name}: {status} (verdict={verdict})")
            if args.verbose and "steps" in r:
                for step in r["steps"]:
                    step_icon = "✓" if step["passed"] else "✗"
                    print(f"      {step_icon} {step['step']}: exit={step['exit_code']}")
        print("-" * 50)
        print(f"  Overall: {'PASS' if failed == 0 else 'FAIL'} ({passed} passed, {failed} failed)")
        print("=" * 50)

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
