#!/usr/bin/env python3
"""tests/test_vibe_pytest_result_classifier.py — Unit tests for scripts/vibe_pytest_result_classifier.py

Covers classify_pytest_result() pure-function behavior for all major exit codes,
output parsing, env-fail detection, and allow_skipped_only toggle.
"""
import os
import sys

import pytest

# Add scripts dir to path
SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)

from vibe_pytest_result_classifier import (  # noqa: E402
    classify_pytest_result,
    self_check,
    VERSION,
    EXIT_OK,
    EXIT_TEST_FAILED,
    EXIT_INTERRUPTED,
    EXIT_INTERNAL_ERROR,
    EXIT_USAGE_ERROR,
    EXIT_NO_TESTS,
)


# ── Exit code → category mapping ────────────────────────────────────────


def test_exit0_with_passes_is_pass():
    """T1: exit_code=0 + '5 passed' → category=PASS, passed=5."""
    r = classify_pytest_result(0, "5 passed in 1.0s")
    assert r["category"] == "PASS"
    assert r["passed"] == 5
    assert r["failed"] == 0
    assert r["strong_validation"] is True


def test_exit0_no_summary_defaults_pass():
    """T1b: exit_code=0 with no parsed summary still → PASS (no failures)."""
    r = classify_pytest_result(0, "")
    assert r["category"] == "PASS"
    assert r["strong_validation"] is False  # passed=0 → no strong validation


def test_exit1_with_failures_is_test_fail():
    """T2: exit_code=1 + '2 failed, 3 passed' → TEST_FAIL, failed=2."""
    r = classify_pytest_result(1, "3 passed, 2 failed in 1.0s")
    assert r["category"] == "TEST_FAIL"
    assert r["failed"] == 2
    assert r["passed"] == 3


def test_exit2_is_interrupted():
    """T3: exit_code=2 → INTERRUPTED."""
    r = classify_pytest_result(2, "")
    assert r["category"] == "INTERRUPTED"
    assert r["exit_code"] == 2


def test_exit3_internal_error_is_env_fail():
    """T4: exit_code=3 (pytest internal error) → ENV_FAIL."""
    r = classify_pytest_result(3, "")
    assert r["category"] == "ENV_FAIL"
    assert r["env_ready"] is True  # not env issue per pattern, just exit=3


def test_exit4_usage_error_is_env_fail():
    """T5: exit_code=4 (pytest usage error) → ENV_FAIL."""
    r = classify_pytest_result(4, "")
    assert r["category"] == "ENV_FAIL"


def test_exit5_no_output_is_no_tests():
    """T6: exit_code=5 + empty output → NO_TESTS."""
    r = classify_pytest_result(5, "")
    assert r["category"] == "NO_TESTS"


def test_exit99_unknown():
    """T7: exit_code outside standard set → UNKNOWN."""
    r = classify_pytest_result(99, "")
    assert r["category"] == "UNKNOWN"
    assert r["exit_code"] == 99


# ── Skipped-only boundary ───────────────────────────────────────────────


def test_exit0_skipped_only_default_is_skipped_only():
    """T8: exit_code=0 + only skipped (no passes) → SKIPPED_ONLY (default)."""
    r = classify_pytest_result(0, "1 skipped in 0.05s")
    assert r["category"] == "SKIPPED_ONLY"
    assert r["skipped"] == 1
    assert r["passed"] == 0


def test_exit0_skipped_only_with_allow_flag_is_pass():
    """T8b: exit_code=0 + skipped only + allow_skipped_only=True → PASS."""
    r = classify_pytest_result(0, "1 skipped in 0.05s", allow_skipped_only=True)
    assert r["category"] == "PASS"
    assert r["skipped"] == 1


# ── NO_TESTS vs INCONSISTENT_RESULT ─────────────────────────────────────


def test_exit5_with_skipped_output_is_inconsistent():
    """T9: exit_code=5 + output mentioning skipped tests → INCONSISTENT_RESULT."""
    r = classify_pytest_result(5, "1 skipped in 0.05s")
    assert r["category"] == "INCONSISTENT_RESULT"


def test_exit5_with_passed_output_is_inconsistent():
    """T9b: exit_code=5 + output mentioning passed tests → INCONSISTENT_RESULT."""
    r = classify_pytest_result(5, "3 passed in 1.0s")
    assert r["category"] == "INCONSISTENT_RESULT"
    assert r["passed"] == 3


# ── ENV_FAIL detection ──────────────────────────────────────────────────


def test_exit1_with_import_error_is_env_fail():
    """T10: exit_code=1 + stderr has ModuleNotFoundError → ENV_FAIL."""
    r = classify_pytest_result(1, "", "ModuleNotFoundError: No module named 'xyz'")
    assert r["category"] == "ENV_FAIL"
    assert r["env_ready"] is False


def test_exit1_with_import_error_stdout_is_env_fail():
    """T10b: ModuleNotFoundError in stdout also triggers ENV_FAIL."""
    r = classify_pytest_result(1, "ModuleNotFoundError: No module named 'abc'")
    assert r["category"] == "ENV_FAIL"


def test_exit1_with_plugin_not_found_is_env_fail():
    """T10c: 'plugin not found' pattern triggers ENV_FAIL."""
    r = classify_pytest_result(1, "ERROR: plugin not found: pytest-x")
    assert r["category"] == "ENV_FAIL"


# ── Timeout detection ───────────────────────────────────────────────────


def test_timeout_in_stderr_with_nonzero_exit_is_timeout():
    """T11: 'timeout' in stderr + exit!=0 → TIMEOUT (before other classifications)."""
    r = classify_pytest_result(124, "", "Timeout occurred")
    assert r["category"] == "TIMEOUT"


# ── Output parsing edge cases ───────────────────────────────────────────


def test_summary_parses_multiple_metrics():
    """T12: output with passed/skipped/failed all parsed correctly."""
    r = classify_pytest_result(1, "5 passed, 2 skipped, 3 failed in 2.5s")
    assert r["passed"] == 5
    assert r["skipped"] == 2
    assert r["failed"] == 3
    assert r["tests_collected"] == 10  # passed + skipped + failed


def test_stdout_tail_truncated_to_500():
    """T13: stdout_tail is at most 500 chars from input."""
    long_output = "x" * 1000
    r = classify_pytest_result(0, long_output)
    assert len(r["stdout_tail"]) == 500
    assert r["stdout_tail"] == "x" * 500


def test_stderr_empty_when_not_provided():
    """T14: stderr_tail is empty string when stderr not provided."""
    r = classify_pytest_result(0, "5 passed in 1.0s")
    assert r["stderr_tail"] == ""


# ── strong_validation flag ──────────────────────────────────────────────


def test_strong_validation_true_for_real_pass():
    """T15: PASS with passed>0 → strong_validation=True."""
    r = classify_pytest_result(0, "5 passed in 1.0s")
    assert r["strong_validation"] is True


def test_strong_validation_false_for_skipped_only():
    """T15b: SKIPPED_ONLY → strong_validation=False."""
    r = classify_pytest_result(0, "1 skipped in 0.05s")
    assert r["strong_validation"] is False


def test_strong_validation_false_for_inconsistent():
    """T15c: INCONSISTENT_RESULT → strong_validation=False."""
    r = classify_pytest_result(5, "1 skipped in 0.05s")
    assert r["strong_validation"] is False


# ── Self-check smoke ────────────────────────────────────────────────────


def test_self_check_all_pass():
    """T16: module self_check returns overall=PASS."""
    r = self_check()
    assert r["overall"] == "PASS"
    assert r["passed"] == r["total"]


def test_self_check_has_version_check():
    """T16b: self_check includes a version check."""
    r = self_check()
    check_names = [c["name"] for c in r["checks"]]
    assert "version" in check_names