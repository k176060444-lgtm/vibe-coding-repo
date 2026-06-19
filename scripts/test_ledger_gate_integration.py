#!/usr/bin/env python3
"""Integration tests for V1.20.7/8/9 ledger gate real integration.

Tests the actual call paths through vibe_run_report.py and vibe_merge_gate.py,
not just the helper script vibe_report_status_gate.py.

Usage:
    python scripts/test_ledger_gate_integration.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from model_ledger_gate import validate_report, TERMINAL_STATUSES
from vibe_report_status_gate import check_report_status, check_merge_readiness


def _make_valid_report():
    """V1.20.5-style valid report with 3 live + 2 fixture."""
    return {
        "status": "PASS",
        "MODEL_LEDGER": [
            {"node": "5bao", "job_id": "e2e-001", "role": "implementer",
             "planned_model": "opencode/deepseek-v4-flash-free",
             "actual_model": "deepseek-v4-flash-free", "provider": "opencode",
             "opencode_provider_alias": "opencode", "fallback_used": False,
             "fallback_from": None, "fallback_to": None, "fallback_reason": None,
             "call_count": 1, "token_usage_or_unavailable_reason": "unavailable_opencode_cli",
             "duration": "12s", "exit_code": 0, "rate_limit": False,
             "binary_ok": True, "final_status": "PASS"},
            {"node": "9bao", "job_id": "e2e-002", "role": "reviewer",
             "planned_model": "opencode/deepseek-v4-flash-free",
             "actual_model": "deepseek-v4-flash-free", "provider": "opencode",
             "opencode_provider_alias": "opencode", "fallback_used": False,
             "call_count": 1, "token_usage_or_unavailable_reason": "unavailable_opencode_cli",
             "duration": "15s", "exit_code": 0, "rate_limit": False,
             "binary_ok": True, "final_status": "PASS"},
            {"node": "5bao", "job_id": "e2e-004", "role": "implementer",
             "planned_model": "opencode/deepseek-v4-flash-free",
             "actual_model": "deepseek-v4-flash-free", "provider": "opencode",
             "opencode_provider_alias": "opencode", "fallback_used": False,
             "call_count": 1, "token_usage_or_unavailable_reason": "unavailable_opencode_cli",
             "duration": "19s", "exit_code": 0, "rate_limit": False,
             "binary_ok": True, "final_status": "PASS"},
            {"node": "windows", "job_id": "e2e-003", "role": "smoke",
             "planned_model": "N/A", "actual_model": "N/A", "provider": "N/A",
             "opencode_provider_alias": "N/A", "fallback_used": False,
             "call_count": 0, "token_usage_or_unavailable_reason": "no_model_call_fixture",
             "duration": "2s", "exit_code": 0, "rate_limit": False,
             "binary_ok": True, "final_status": "PASS"},
            {"node": "windows", "job_id": "e2e-005", "role": "smoke",
             "planned_model": "N/A", "actual_model": "N/A", "provider": "N/A",
             "opencode_provider_alias": "N/A", "fallback_used": False,
             "call_count": 0, "token_usage_or_unavailable_reason": "no_model_call_cooldown",
             "duration": "1s", "exit_code": 0, "rate_limit": False,
             "binary_ok": True, "final_status": "PASS"},
        ],
        "NODE_MODEL_SUMMARY": [
            {"node": "5bao", "opencode_version": "1.17.8",
             "models_used_this_run": ["deepseek-v4-flash-free"],
             "total_model_calls": 2, "successful_model_calls": 2,
             "failed_model_calls": 0, "fallback_count": 0,
             "rate_limit_count": 0, "cooldown_state": "NORMAL"},
            {"node": "9bao", "opencode_version": "1.17.8",
             "models_used_this_run": ["deepseek-v4-flash-free"],
             "total_model_calls": 1, "successful_model_calls": 1,
             "failed_model_calls": 0, "fallback_count": 0,
             "rate_limit_count": 0, "cooldown_state": "NORMAL"},
        ],
        "RATE_LIMIT_EVENT_LEDGER": [],
        "FALLBACK_DECISION_LEDGER": [],
        "COOLDOWN_STATE_SUMMARY": [
            {"node": "5bao", "model": "opencode/deepseek-v4-flash-free",
             "consecutive_rate_limits": 0, "current_cooldown_seconds": 0,
             "cooldown_action": "NORMAL"},
            {"node": "9bao", "model": "opencode/deepseek-v4-flash-free",
             "consecutive_rate_limits": 0, "current_cooldown_seconds": 0,
             "cooldown_action": "NORMAL"},
        ],
    }


def test_run_report_no_ledger():
    """Test 1: PASS status but no MODEL_LEDGER -> BLOCKED_BY_LEDGER_GATE.

    Simulates vibe_run_report.py path: qg_verdict=PASS, result has status=PASS
    but no MODEL_LEDGER/NODE_MODEL_SUMMARY/COOLDOWN_STATE_SUMMARY.
    """
    result = {
        "status": "PASS",
        "quality_gate": {"verdict": "PASS", "checks": {}},
        "operator_summary": "System healthy.",
    }
    gate_result = check_report_status(result)
    assert not gate_result["status_allowed"], \
        "Expected BLOCKED for PASS without MODEL_LEDGER"
    assert gate_result["terminal_status_found"] == "PASS"
    assert len(gate_result["gate_errors"]) > 0
    return True, "PASS without MODEL_LEDGER -> BLOCKED (correct fail-closed)"


def test_run_report_valid_ledger():
    """Test 2: PASS status with valid complete ledger -> ALLOWED."""
    result = _make_valid_report()
    gate_result = check_report_status(result)
    assert gate_result["status_allowed"], \
        "Expected ALLOWED for valid report"
    assert gate_result["terminal_status_found"] == "PASS"
    assert gate_result["gate_errors"] == []
    return True, "PASS with valid ledger -> ALLOWED"


def test_merge_gate_no_ledger():
    """Test 3: merge candidate with terminal status, no ledger -> fail-closed."""
    job_report = {"status": "PASS"}
    errors = validate_report(job_report)
    assert len(errors) > 0, "Expected errors for missing ledger"
    return True, "Merge candidate without ledger -> gate FAIL"


def test_merge_gate_valid_ledger():
    """Test 4: merge candidate with valid report -> gate PASS."""
    report = _make_valid_report()
    errors = validate_report(report)
    assert len(errors) == 0, f"Unexpected errors: {errors}"
    return True, "Merge candidate with valid ledger -> gate PASS"


def test_merge_gate_report_file():
    """Test 5: merge gate --report-file with valid ledger."""
    report = _make_valid_report()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(report, f)
        tmp_path = f.name
    try:
        with open(tmp_path, "r") as f:
            loaded = json.load(f)
        errors = validate_report(loaded)
        assert len(errors) == 0, f"Unexpected errors: {errors}"
        return True, "--report-file valid ledger -> PASS"
    finally:
        os.unlink(tmp_path)


def test_merge_gate_report_file_no_ledger():
    """Test 6: merge gate --report-file without ledger -> fail-closed."""
    bad_report = {"status": "PASS"}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bad_report, f)
        tmp_path = f.name
    try:
        with open(tmp_path, "r") as f:
            loaded = json.load(f)
        errors = validate_report(loaded)
        assert len(errors) > 0, "Expected errors for missing ledger"
        return True, "--report-file without ledger -> FAIL"
    finally:
        os.unlink(tmp_path)


def test_run_report_non_terminal():
    """Test 7: non-terminal status -> gate not applicable, allowed."""
    result = {
        "status": "IN_PROGRESS",
        "quality_gate": {"verdict": "IN_PROGRESS"},
    }
    gate_result = check_report_status(result)
    assert gate_result["status_allowed"]
    assert gate_result.get("gate_not_applicable")
    return True, "Non-terminal -> gate N/A, allowed"


def main():
    tests = [
        ("rt-01-run-report-no-ledger", test_run_report_no_ledger),
        ("rt-02-run-report-valid-ledger", test_run_report_valid_ledger),
        ("rt-03-merge-gate-no-ledger", test_merge_gate_no_ledger),
        ("rt-04-merge-gate-valid-ledger", test_merge_gate_valid_ledger),
        ("rt-05-merge-gate-report-file", test_merge_gate_report_file),
        ("rt-06-merge-gate-report-file-no-ledger", test_merge_gate_report_file_no_ledger),
        ("rt-07-run-report-non-terminal", test_run_report_non_terminal),
    ]

    passed = 0
    failed = 0
    print("=== LEDGER GATE INTEGRATION TESTS ===")
    print(f"  Total: {len(tests)}")
    for test_id, test_fn in tests:
        try:
            ok, msg = test_fn()
            if ok:
                print(f"  PASS  {test_id}: {msg}")
                passed += 1
            else:
                print(f"  FAIL  {test_id}: {msg}")
                failed += 1
        except Exception as e:
            print(f"  FAIL  {test_id}: EXCEPTION: {e}")
            failed += 1

    print(f"\n  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"\n  Result: {'ALL PASSED' if failed == 0 else 'FAILED'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
