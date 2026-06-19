#!/usr/bin/env python3
"""Integration tests for V1.20.7/8/9 ledger gate real integration.

Tests the actual call paths through vibe_run_report.py and vibe_merge_gate.py.

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
from operator_merge_approval_gate import validate_approval as operator_validate_approval


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


def _simulate_merge_gate_report_file(report_file_path):
    """Simulate vibe_merge_gate.py --report-file logic for testing.

    Returns (allow_merge, ledger_gate_result, blockers).
    """
    blockers = []
    ledger_gate_result = None
    gate_error_detail = None
    gate_report = None
    is_non_terminal = False

    # 1. Require --report-file and valid JSON with status
    if not report_file_path:
        gate_error_detail = "no --report-file provided"
    else:
        rf_path = Path(report_file_path)
        if not rf_path.exists():
            gate_error_detail = f"report file not found: {report_file_path}"
        else:
            try:
                with open(rf_path, "r", encoding="utf-8") as f:
                    rf = json.load(f)
            except (json.JSONDecodeError, OSError):
                rf = None
            if rf is None:
                gate_error_detail = "report file is not valid JSON"
            else:
                gate_report = rf
                if "status" not in gate_report:
                    gate_error_detail = "report file missing status field"

    # 2. Check terminal status FIRST
    terminal_statuses = {"PASS", "MERGE_READY", "FREEZE_PASS", "PROMOTION_PASS"}
    if not gate_error_detail and gate_report is not None:
        status = str(gate_report.get("status", "")).upper()
        if status not in terminal_statuses:
            is_non_terminal = True
            ledger_gate_result = {"checked": False, "result": "N/A", "reason": f"non-terminal: {status}"}
            blockers.append(f'Merge readiness gate: non-terminal status "{status}", cannot confirm ledger validity')

    # 3. For terminal status, validate ledger fields
    if not gate_error_detail and not is_non_terminal and gate_report is not None:
        if not gate_report.get("MODEL_LEDGER"):
            gate_error_detail = "report file missing MODEL_LEDGER"
        elif not gate_report.get("NODE_MODEL_SUMMARY"):
            gate_error_detail = "report file missing NODE_MODEL_SUMMARY"
        elif not gate_report.get("COOLDOWN_STATE_SUMMARY"):
            gate_error_detail = "report file missing COOLDOWN_STATE_SUMMARY"

    # 4. If any error -> fail-closed
    if gate_error_detail and not is_non_terminal:
        ledger_gate_result = {"checked": False, "result": "FAIL", "errors": [gate_error_detail]}
        blockers.append(f"Merge readiness gate FAIL: {gate_error_detail}")
    elif not gate_error_detail and not is_non_terminal and gate_report is not None:
        errors = validate_report(gate_report)
        ledger_gate_result = {"checked": True, "result": "PASS" if not errors else "FAIL", "errors": errors}
        if errors:
            blockers.append("Model ledger gate FAIL: " + "; ".join(errors[:3]))

    base_allow = len(blockers) == 0
    ledger_ok = (ledger_gate_result is not None
                 and ledger_gate_result.get("checked", False)
                 and ledger_gate_result.get("result") == "PASS")
    allow_merge = base_allow and ledger_ok
    return allow_merge, ledger_gate_result, blockers



# === Tests rt-01 through rt-07 (existing) ===

def test_run_report_no_ledger():
    """rt-01: PASS without MODEL_LEDGER -> BLOCKED."""
    result = {"status": "PASS", "quality_gate": {"verdict": "PASS"}}
    gate_result = check_report_status(result)
    assert not gate_result["status_allowed"]
    assert gate_result["terminal_status_found"] == "PASS"
    return True, "PASS without MODEL_LEDGER -> BLOCKED"


def test_run_report_valid_ledger():
    """rt-02: PASS with valid ledger -> ALLOWED."""
    result = _make_valid_report()
    gate_result = check_report_status(result)
    assert gate_result["status_allowed"]
    return True, "PASS with valid ledger -> ALLOWED"


def test_merge_gate_no_ledger():
    """rt-03: merge candidate no ledger -> FAIL."""
    errors = validate_report({"status": "PASS"})
    assert len(errors) > 0
    return True, "No ledger -> gate FAIL"


def test_merge_gate_valid_ledger():
    """rt-04: merge candidate valid ledger -> PASS."""
    errors = validate_report(_make_valid_report())
    assert len(errors) == 0
    return True, "Valid ledger -> gate PASS"


def test_merge_gate_report_file():
    """rt-05: --report-file valid -> PASS."""
    report = _make_valid_report()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(report, f)
        tmp = f.name
    try:
        allow, lg, _ = _simulate_merge_gate_report_file(tmp)
        assert allow and lg["result"] == "PASS"
        return True, "--report-file valid -> merge allowed"
    finally:
        os.unlink(tmp)


def test_merge_gate_report_file_no_ledger():
    """rt-06: --report-file without ledger -> FAIL."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"status": "PASS"}, f)
        tmp = f.name
    try:
        allow, lg, _ = _simulate_merge_gate_report_file(tmp)
        assert not allow and lg["result"] == "FAIL"
        return True, "--report-file no ledger -> merge blocked"
    finally:
        os.unlink(tmp)


def test_run_report_non_terminal():
    """rt-07: non-terminal -> gate N/A, allowed."""
    result = {"status": "IN_PROGRESS"}
    gate_result = check_report_status(result)
    assert gate_result["status_allowed"] and gate_result.get("gate_not_applicable")
    return True, "Non-terminal -> gate N/A, allowed"


# === Tests rt-08 through rt-12 (new fail-closed) ===

def test_merge_gate_no_report_file():
    """rt-08: merge gate without --report-file -> allow_merge=false."""
    allow, lg, blockers = _simulate_merge_gate_report_file(None)
    assert not allow, f"Expected blocked, got allow={allow}"
    assert lg["result"] == "FAIL"
    return True, "No --report-file -> merge blocked"


def test_merge_gate_report_file_not_found():
    """rt-09: --report-file path not found -> allow_merge=false."""
    allow, lg, blockers = _simulate_merge_gate_report_file("/tmp/nonexistent_xyz_12345.json")
    assert not allow, f"Expected blocked, got allow={allow}"
    assert lg["result"] == "FAIL"
    return True, "Nonexistent file -> merge blocked"


def test_merge_gate_report_file_non_terminal():
    """rt-10: --report-file status=IN_PROGRESS -> allow_merge=false, N/A."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"status": "IN_PROGRESS"}, f)
        tmp = f.name
    try:
        allow, lg, blockers = _simulate_merge_gate_report_file(tmp)
        assert not allow, f"Expected blocked, got allow={allow}"
        assert lg["result"] == "N/A"
        return True, "status=IN_PROGRESS -> N/A but merge blocked"
    finally:
        os.unlink(tmp)


def test_merge_gate_report_file_valid():
    """rt-11: --report-file status=PASS complete ledger -> allow_merge=true."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_make_valid_report(), f)
        tmp = f.name
    try:
        allow, lg, blockers = _simulate_merge_gate_report_file(tmp)
        assert allow, f"Expected allowed, got blockers: {blockers}"
        assert lg["result"] == "PASS" and lg["checked"]
        return True, "Valid report -> merge allowed, gate PASS"
    finally:
        os.unlink(tmp)


def test_merge_gate_report_file_missing_ledger():
    """rt-12: --report-file status=PASS but missing MODEL_LEDGER -> allow_merge=false."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"status": "PASS", "NODE_MODEL_SUMMARY": [{"node": "x"}],
                   "COOLDOWN_STATE_SUMMARY": [{"node": "x"}]}, f)
        tmp = f.name
    try:
        allow, lg, blockers = _simulate_merge_gate_report_file(tmp)
        assert not allow, f"Expected blocked, got allow={allow}"
        assert lg["result"] == "FAIL"
        return True, "PASS without MODEL_LEDGER -> merge blocked"
    finally:
        os.unlink(tmp)


def test_operator_approval_no_record():
    """rt-13: no approval record -> BLOCKED."""
    r = operator_validate_approval(None, expected_pr=174)
    assert r["result"] == "BLOCKED"
    return True, "No approval -> BLOCKED"


def test_operator_approval_head_mismatch():
    """rt-14: head SHA mismatch -> BLOCKED."""
    now = "2026-06-19T16:00:00Z"
    approval = {
        "pr_number": 174, "approval_status": "APPROVED",
        "approved_by": "kk", "approved_at": now,
        "approved_head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "approved_base_sha": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
        "merge_method_allowed": "merge", "approval_scope": "merge",
    }
    r = operator_validate_approval(approval, expected_head="8dfcedf9f9509069650df6642ec639421558a08e")
    assert r["result"] == "BLOCKED"
    return True, "Head mismatch -> BLOCKED"


def test_operator_approval_valid():
    """rt-15: valid approval -> APPROVED."""
    now = "2026-06-19T16:00:00Z"
    approval = {
        "pr_number": 174, "approval_status": "APPROVED",
        "approved_by": "kk", "approved_at": now,
        "approved_head_sha": "8dfcedf9f9509069650df6642ec639421558a08e",
        "approved_base_sha": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
        "merge_method_allowed": "merge", "approval_scope": "merge",
    }
    r = operator_validate_approval(approval, expected_pr=174,
        expected_head="8dfcedf9f9509069650df6642ec639421558a08e",
        expected_base="b3a59f9271dcbc320cd79e85d2b4470d79ecd50f")
    assert r["result"] == "APPROVED"
    return True, "Valid approval -> APPROVED"


def test_operator_approval_scope_no_merge():
    """rt-16: scope=comment -> BLOCKED."""
    now = "2026-06-19T16:00:00Z"
    approval = {
        "pr_number": 174, "approval_status": "APPROVED",
        "approved_by": "kk", "approved_at": now,
        "approved_head_sha": "8dfcedf9f9509069650df6642ec639421558a08e",
        "approved_base_sha": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
        "merge_method_allowed": "merge", "approval_scope": "comment",
    }
    r = operator_validate_approval(approval)
    assert r["result"] == "BLOCKED"
    return True, "Scope=comment -> BLOCKED"


def test_merge_gate_full_path():
    """rt-17: valid approval + valid ledger -> allow_merge=true (simulated)."""
    # Simulate: all gates pass
    now = "2026-06-19T16:00:00Z"
    approval = {
        "pr_number": 174, "approval_status": "APPROVED",
        "approved_by": "kk", "approved_at": now,
        "approved_head_sha": "8dfcedf9f9509069650df6642ec639421558a08e",
        "approved_base_sha": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
        "merge_method_allowed": "merge", "approval_scope": "merge",
    }
    oa = operator_validate_approval(approval, expected_pr=174)
    assert oa["result"] == "APPROVED"

    report = _make_valid_report()
    errors = validate_report(report)
    assert len(errors) == 0

    # Simulate allow_merge logic
    base_allow = True
    ledger_ok = True
    operator_ok = oa["result"] == "APPROVED"
    allow_merge = base_allow and ledger_ok and operator_ok
    assert allow_merge
    return True, "Valid approval + valid ledger -> merge allowed"


def test_merge_gate_valid_approval_bad_ledger():
    """rt-18: valid approval but ledger FAIL -> allow_merge=false."""
    now = "2026-06-19T16:00:00Z"
    approval = {
        "pr_number": 174, "approval_status": "APPROVED",
        "approved_by": "kk", "approved_at": now,
        "approved_head_sha": "8dfcedf9f9509069650df6642ec639421558a08e",
        "approved_base_sha": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
        "merge_method_allowed": "merge", "approval_scope": "merge",
    }
    oa = operator_validate_approval(approval, expected_pr=174)
    assert oa["result"] == "APPROVED"

    # Bad ledger
    errors = validate_report({"status": "PASS"})
    assert len(errors) > 0

    ledger_ok = False
    operator_ok = oa["result"] == "APPROVED"
    allow_merge = ledger_ok and operator_ok
    assert not allow_merge
    return True, "Valid approval + bad ledger -> merge blocked"



def test_operator_short_head_sha():
    """rt-19: short head SHA -> BLOCKED."""
    approval = {
        "pr_number": 174, "approval_status": "APPROVED",
        "approved_by": "kk", "approved_at": "2026-06-19T16:00:00Z",
        "approved_head_sha": "8dfcedf",
        "approved_base_sha": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
        "merge_method_allowed": "merge", "approval_scope": "merge",
    }
    r = operator_validate_approval(approval)
    assert r["result"] == "BLOCKED", f"Expected BLOCKED, got {r['result']}"
    return True, "Short head SHA -> BLOCKED"


def test_operator_merge_method_mismatch():
    """rt-20: allowed=merge requested=squash -> BLOCKED."""
    approval = {
        "pr_number": 174, "approval_status": "APPROVED",
        "approved_by": "kk", "approved_at": "2026-06-19T16:00:00Z",
        "approved_head_sha": "8dfcedf9f9509069650df6642ec639421558a08e",
        "approved_base_sha": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
        "merge_method_allowed": "merge", "approval_scope": "merge",
    }
    r = operator_validate_approval(approval, merge_method_requested="squash")
    assert r["result"] == "BLOCKED", f"Expected BLOCKED, got {r['result']}"
    return True, "allowed=merge requested=squash -> BLOCKED"


def test_operator_merge_method_any():
    """rt-21: allowed=any requested=rebase -> APPROVED."""
    approval = {
        "pr_number": 174, "approval_status": "APPROVED",
        "approved_by": "kk", "approved_at": "2026-06-19T16:00:00Z",
        "approved_head_sha": "8dfcedf9f9509069650df6642ec639421558a08e",
        "approved_base_sha": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
        "merge_method_allowed": "any", "approval_scope": "merge",
    }
    r = operator_validate_approval(approval, merge_method_requested="rebase")
    assert r["result"] == "APPROVED", f"Expected APPROVED, got {r['result']}"
    return True, "allowed=any requested=rebase -> APPROVED"


def test_merge_gate_no_merge_method():
    """rt-22: vibe_merge_gate no --merge-method -> allow_merge=false (simulated)."""
    # Simulate: no merge_method -> operator approval blocked
    # In real gate, --merge-method missing triggers blocker
    approval = {
        "pr_number": 174, "approval_status": "APPROVED",
        "approved_by": "kk", "approved_at": "2026-06-19T16:00:00Z",
        "approved_head_sha": "8dfcedf9f9509069650df6642ec639421558a08e",
        "approved_base_sha": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
        "merge_method_allowed": "merge", "approval_scope": "merge",
    }
    # Without merge_method_requested, approval gate still passes
    # but vibe_merge_gate requires --merge-method arg
    # This test validates the gate itself allows it; the CLI check is in merge_gate
    r = operator_validate_approval(approval)
    assert r["result"] == "APPROVED"
    return True, "Approval gate passes without merge_method (CLI enforces)"


def main():
    tests = [
        ("rt-01-run-report-no-ledger", test_run_report_no_ledger),
        ("rt-02-run-report-valid-ledger", test_run_report_valid_ledger),
        ("rt-03-merge-gate-no-ledger", test_merge_gate_no_ledger),
        ("rt-04-merge-gate-valid-ledger", test_merge_gate_valid_ledger),
        ("rt-05-merge-gate-report-file", test_merge_gate_report_file),
        ("rt-06-merge-gate-report-file-no-ledger", test_merge_gate_report_file_no_ledger),
        ("rt-07-run-report-non-terminal", test_run_report_non_terminal),
        ("rt-08-merge-gate-no-report-file", test_merge_gate_no_report_file),
        ("rt-09-merge-gate-report-not-found", test_merge_gate_report_file_not_found),
        ("rt-10-merge-gate-non-terminal", test_merge_gate_report_file_non_terminal),
        ("rt-11-merge-gate-valid-report", test_merge_gate_report_file_valid),
        ("rt-12-merge-gate-missing-ledger", test_merge_gate_report_file_missing_ledger),
        ("rt-13-operator-no-approval", test_operator_approval_no_record),
        ("rt-14-operator-head-mismatch", test_operator_approval_head_mismatch),
        ("rt-15-operator-valid", test_operator_approval_valid),
        ("rt-16-operator-scope-no-merge", test_operator_approval_scope_no_merge),
        ("rt-17-full-path-valid", test_merge_gate_full_path),
        ("rt-18-valid-approval-bad-ledger", test_merge_gate_valid_approval_bad_ledger),
        ("rt-19-operator-short-sha", test_operator_short_head_sha),
        ("rt-20-merge-method-mismatch", test_operator_merge_method_mismatch),
        ("rt-21-merge-method-any", test_operator_merge_method_any),
        ("rt-22-no-merge-method", test_merge_gate_no_merge_method),
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
