#!/usr/bin/env python3
"""V1.21.27B — Health Check unit tests.

Covers vibe_health_check.py behavior:
- _run_check: exception handling
- _check_py_compile: compile verification
- _check_import: import verification
- run_checks: 7 checks, overall logic
- main: CLI output structure, --json
- Edge cases: missing scripts, degraded states

Read-only. No real execution, no gate verdict change.
"""
import io
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ── _run_check ──────────────────────────────────────────────────────────────

class TestRunCheck:
    """Tests for _run_check()."""

    def test_successful_check(self):
        """Successful check returns (name, 'PASS', message)."""
        from vibe_health_check import _run_check
        name, status, msg = _run_check("test", lambda: {"status": "PASS", "message": "ok"})
        assert name == "test"
        assert status == "PASS"
        assert msg == "ok"

    def test_warn_check(self):
        """WARN check returns correct status."""
        from vibe_health_check import _run_check
        _, status, msg = _run_check("test", lambda: {"status": "WARN", "message": "warning"})
        assert status == "WARN"
        assert msg == "warning"

    def test_fail_check(self):
        """FAIL check returns correct status."""
        from vibe_health_check import _run_check
        _, status, msg = _run_check("test", lambda: {"status": "FAIL", "message": "error"})
        assert status == "FAIL"
        assert msg == "error"

    def test_exception_returns_fail(self):
        """Exception in check function → FAIL with exception message."""
        from vibe_health_check import _run_check
        _, status, msg = _run_check("test", lambda: 1 / 0)
        assert status == "FAIL"
        assert "division" in msg.lower() or "ZeroDivision" in msg

    def test_missing_message_defaults_empty(self):
        """Check without message key → empty string."""
        from vibe_health_check import _run_check
        _, _, msg = _run_check("test", lambda: {"status": "PASS"})
        assert msg == ""


# ── _check_py_compile ───────────────────────────────────────────────────────

class TestCheckPyCompile:
    """Tests for _check_py_compile()."""

    def test_compiles_all_scripts(self):
        """All SCRIPTS compile → PASS with count message."""
        from vibe_health_check import _check_py_compile, SCRIPTS
        result = _check_py_compile()
        assert result["status"] == "PASS"
        assert str(len(SCRIPTS)) in result["message"]

    def test_missing_script_fails(self):
        """Missing script → FAIL."""
        from vibe_health_check import _check_py_compile
        with patch("vibe_health_check.SCRIPTS", ["nonexistent_script_xyz.py"]):
            result = _check_py_compile()
        assert result["status"] == "FAIL"
        assert "not found" in result["message"]


# ── _check_import ───────────────────────────────────────────────────────────

class TestCheckImport:
    """Tests for _check_import()."""

    def test_imports_all_scripts(self):
        """All SCRIPTS importable → PASS."""
        from vibe_health_check import _check_import, SCRIPTS
        result = _check_import()
        assert result["status"] == "PASS"
        assert str(len(SCRIPTS)) in result["message"]

    def test_missing_script_fails(self):
        """Missing script → FAIL."""
        from vibe_health_check import _check_import
        with patch("vibe_health_check.SCRIPTS", ["nonexistent_script_xyz.py"]):
            result = _check_import()
        assert result["status"] == "FAIL"
        assert "not found" in result["message"]


# ── run_checks ──────────────────────────────────────────────────────────────

class TestRunChecks:
    """Tests for run_checks()."""

    def test_returns_seven_checks(self):
        """run_checks returns exactly 7 check tuples."""
        from vibe_health_check import run_checks
        with patch("vibe_health_check._check_operator_snapshot", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_queue_advisor", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_dispatch_planner", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_batch_plan", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_audit_tainted_lock", return_value={"status": "PASS", "message": ""}):
            checks = run_checks("/tmp/fake-jobs")
        assert len(checks) == 7

    def test_check_names(self):
        """Checks have expected names."""
        from vibe_health_check import run_checks
        with patch("vibe_health_check._check_operator_snapshot", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_queue_advisor", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_dispatch_planner", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_batch_plan", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_audit_tainted_lock", return_value={"status": "PASS", "message": ""}):
            checks = run_checks("/tmp/fake-jobs")
        names = [c[0] for c in checks]
        expected = ["py_compile", "import", "operator_snapshot", "queue_advisor",
                    "dispatch_planner", "batch_plan", "audit_tainted_lock"]
        assert names == expected

    def test_all_pass_overall_pass(self):
        """All checks PASS → overall PASS."""
        from vibe_health_check import run_checks
        with patch("vibe_health_check._check_operator_snapshot", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_queue_advisor", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_dispatch_planner", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_batch_plan", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_audit_tainted_lock", return_value={"status": "PASS", "message": ""}):
            checks = run_checks("/tmp/fake-jobs")
        # Verify all pass
        assert all(s == "PASS" for _, s, _ in checks)

    def test_warn_check_exists(self):
        """A WARN check produces WARN status in tuple."""
        from vibe_health_check import _run_check
        _, status, _ = _run_check("test", lambda: {"status": "WARN", "message": ""})
        assert status == "WARN"


# ── main CLI ────────────────────────────────────────────────────────────────

class TestMainCli:
    """Tests for main() CLI output."""

    def test_json_output_has_required_keys(self):
        """--json output has overall, pass, warn, fail, checks."""
        from vibe_health_check import main
        with patch("vibe_health_check._check_operator_snapshot", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_queue_advisor", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_dispatch_planner", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_batch_plan", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_audit_tainted_lock", return_value={"status": "PASS", "message": ""}):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                ret = main(["--json", "--jobs-dir", "/tmp/fake-jobs"])
        assert ret == 0
        output = json.loads(buf.getvalue())
        for key in ["overall", "pass", "warn", "fail", "checks"]:
            assert key in output, f"Missing key: {key}"

    def test_json_overall_is_string(self):
        """overall is a string (PASS/WARN/FAIL)."""
        from vibe_health_check import main
        with patch("vibe_health_check._check_operator_snapshot", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_queue_advisor", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_dispatch_planner", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_batch_plan", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_audit_tainted_lock", return_value={"status": "PASS", "message": ""}):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                main(["--json", "--jobs-dir", "/tmp/fake-jobs"])
        output = json.loads(buf.getvalue())
        assert output["overall"] in ("PASS", "WARN", "FAIL")

    def test_json_checks_is_list_of_dicts(self):
        """checks is a list of dicts with name/status/message."""
        from vibe_health_check import main
        with patch("vibe_health_check._check_operator_snapshot", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_queue_advisor", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_dispatch_planner", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_batch_plan", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_audit_tainted_lock", return_value={"status": "PASS", "message": ""}):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                main(["--json", "--jobs-dir", "/tmp/fake-jobs"])
        output = json.loads(buf.getvalue())
        assert isinstance(output["checks"], list)
        assert len(output["checks"]) == 7
        for c in output["checks"]:
            assert "name" in c
            assert "status" in c
            assert "message" in c

    def test_text_output_has_header(self):
        """Text output has Health Check header."""
        from vibe_health_check import main
        with patch("vibe_health_check._check_operator_snapshot", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_queue_advisor", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_dispatch_planner", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_batch_plan", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_audit_tainted_lock", return_value={"status": "PASS", "message": ""}):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                main(["--jobs-dir", "/tmp/fake-jobs"])
        output = buf.getvalue()
        assert "Health Check" in output

    def test_text_output_has_overall_line(self):
        """Text output has Overall line."""
        from vibe_health_check import main
        with patch("vibe_health_check._check_operator_snapshot", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_queue_advisor", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_dispatch_planner", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_batch_plan", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_audit_tainted_lock", return_value={"status": "PASS", "message": ""}):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                main(["--jobs-dir", "/tmp/fake-jobs"])
        output = buf.getvalue()
        assert "Overall:" in output

    def test_fail_returns_exit_code_1(self):
        """FAIL overall → exit code 1."""
        from vibe_health_check import main
        with patch("vibe_health_check._check_operator_snapshot", return_value={"status": "FAIL", "message": "broken"}), \
             patch("vibe_health_check._check_queue_advisor", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_dispatch_planner", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_batch_plan", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_audit_tainted_lock", return_value={"status": "PASS", "message": ""}):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                ret = main(["--json", "--jobs-dir", "/tmp/fake-jobs"])
        assert ret == 1


# ── Edge cases ──────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Edge cases for health check."""

    def test_script_list_not_empty(self):
        """SCRIPTS list is non-empty."""
        from vibe_health_check import SCRIPTS
        assert len(SCRIPTS) > 0

    def test_script_list_contains_expected(self):
        """SCRIPTS contains key orchestrator scripts."""
        from vibe_health_check import SCRIPTS
        assert "vibe_operator_snapshot.py" in SCRIPTS
        assert "vibe_command_router.py" in SCRIPTS

    def test_json_output_is_valid_json(self):
        """--json output parses as valid JSON."""
        from vibe_health_check import main
        with patch("vibe_health_check._check_operator_snapshot", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_queue_advisor", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_dispatch_planner", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_batch_plan", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_audit_tainted_lock", return_value={"status": "PASS", "message": ""}):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                main(["--json", "--jobs-dir", "/tmp/fake-jobs"])
        # Should not raise
        parsed = json.loads(buf.getvalue())
        assert isinstance(parsed, dict)

    def test_pass_warn_fail_counts_match_checks(self):
        """pass + warn + fail counts sum to total checks."""
        from vibe_health_check import main
        with patch("vibe_health_check._check_operator_snapshot", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_queue_advisor", return_value={"status": "WARN", "message": ""}), \
             patch("vibe_health_check._check_dispatch_planner", return_value={"status": "FAIL", "message": ""}), \
             patch("vibe_health_check._check_batch_plan", return_value={"status": "PASS", "message": ""}), \
             patch("vibe_health_check._check_audit_tainted_lock", return_value={"status": "PASS", "message": ""}):
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                main(["--json", "--jobs-dir", "/tmp/fake-jobs"])
        output = json.loads(buf.getvalue())
        assert output["pass"] + output["warn"] + output["fail"] == 7


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
