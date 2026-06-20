"""test_windows_local_runner.py — Tests for vibe_windows_local_runner.py

All tests use fixtures / dry-run / no-op mode. No live model calls.
No filesystem writes to controller repo.
"""

import json
import os
import sys
import unittest
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from vibe_windows_local_runner import (
    JobSpec, JobResult, run_job,
    is_path_allowed, is_path_blocked, validate_path,
    WORKTREE_ROOT, EVIDENCE_ROOT, LOG_ROOT, WRAPPER_PATH,
    self_check,
)


class TestPathAllowlist(unittest.TestCase):
    """Test path allowlist validation."""

    def test_drive_d_allowed(self):
        assert is_path_allowed(r"D:\vibedev-evidence\21bao\test")
        assert is_path_allowed(r"D:\vibedev-logs\21bao\test")
        assert is_path_allowed(r"D:\vibedev-tools\bin\opencode-21bao.ps1")

    def test_drive_e_allowed(self):
        assert is_path_allowed(r"E:\vibedev-worktrees\21bao\test")
        assert is_path_allowed(r"E:\some-other-path")

    def test_drive_c_not_allowed(self):
        assert not is_path_allowed(r"C:\Windows\System32")
        assert not is_path_allowed(r"C:\Users\KK\something")

    def test_controller_repo_blocked(self):
        assert is_path_blocked(r"C:\Users\KK\vibe-coding-repo\.git")
        assert is_path_blocked(r"C:\Users\KK\vibe-coding-repo\scripts")
        assert not is_path_blocked(r"D:\vibedev-evidence\test")

    def test_validate_path_controller_repo(self):
        ok, reason = validate_path(r"C:\Users\KK\vibe-coding-repo\.git")
        assert not ok
        assert "blocked" in reason
        assert "controller repo" in reason

    def test_validate_path_allowed(self):
        ok, reason = validate_path(r"D:\vibedev-evidence\21bao")
        assert ok
        assert reason == "ok"

    def test_validate_path_disallowed(self):
        ok, reason = validate_path(r"C:\Users\KK\something")
        assert not ok
        assert "not in allowlist" in reason


class TestDryRunMode(unittest.TestCase):
    """Test dry-run mode."""

    def test_dry_run_returns_dry_run_status(self):
        spec = JobSpec(job_id="test-dry-001", branch="feat/test", task="implementer", dry_run=True)
        result = run_job(spec)
        assert result.status == "dry_run"
        assert result.exit_code == 0
        assert result.job_id == "test-dry-001"
        assert result.branch == "feat/test"
        assert result.task == "implementer"

    def test_dry_run_contains_paths(self):
        spec = JobSpec(job_id="test-dry-002", branch="feat/test", task="implementer", dry_run=True)
        result = run_job(spec)
        parsed = json.loads(result.stdout)
        assert parsed["would_execute"] is True
        assert parsed["wrapper"] == WRAPPER_PATH
        assert parsed["worktree"] == os.path.join(WORKTREE_ROOT, "feat/test")
        assert parsed["evidence_dir"] == os.path.join(EVIDENCE_ROOT, "feat/test")
        assert parsed["log_dir"] == os.path.join(LOG_ROOT, "feat/test")

    def test_dry_run_no_filesystem_changes(self):
        spec = JobSpec(job_id="test-dry-003", branch="feat/fs-test", task="implementer", dry_run=True)
        result = run_job(spec)
        assert result.status == "dry_run"
        assert result.exit_code == 0
        if result.evidence_path:
            assert not os.path.isfile(result.evidence_path), "dry-run must not create evidence files"
        if result.log_path:
            assert not os.path.isfile(result.log_path), "dry-run must not create log files"


class TestNoOpFixture(unittest.TestCase):
    """Test no-op fixture mode."""

    def test_no_op_returns_no_op_status(self):
        spec = JobSpec(job_id="test-noop-001", branch="feat/test", task="implementer", no_op=True)
        result = run_job(spec)
        assert result.status == "no_op"
        assert result.exit_code == 0

    def test_no_op_no_filesystem_writes(self):
        spec = JobSpec(job_id="test-noop-002", branch="feat/test", task="implementer", no_op=True)
        result = run_job(spec)
        assert result.evidence_path == ""
        assert result.log_path == ""

    def test_no_op_serialization(self):
        spec = JobSpec(job_id="test-noop-003", branch="feat/test", task="implementer", no_op=True)
        result = run_job(spec)
        d = result.to_dict()
        assert d["job_id"] == "test-noop-003"
        assert d["status"] == "no_op"
        assert d["exit_code"] == 0


class TestPathSeparation(unittest.TestCase):
    """Test evidence/log path separation."""

    def test_worktree_on_e_drive(self):
        assert WORKTREE_ROOT.startswith("E:\\")

    def test_evidence_on_d_drive(self):
        assert EVIDENCE_ROOT.startswith("D:\\")

    def test_logs_on_d_drive(self):
        assert LOG_ROOT.startswith("D:\\")

    def test_paths_are_separate(self):
        assert WORKTREE_ROOT != EVIDENCE_ROOT
        assert EVIDENCE_ROOT != LOG_ROOT
        assert WORKTREE_ROOT != LOG_ROOT

    def test_wrapper_on_d_drive(self):
        assert WRAPPER_PATH.startswith("D:\\")


class TestNoControllerRepoWrites(unittest.TestCase):
    """Verify runner never writes to controller repo."""

    def test_dry_run_no_writes(self):
        spec = JobSpec(job_id="test-nocr-001", branch="feat/test", task="implementer", dry_run=True)
        result = run_job(spec)
        assert result.status == "dry_run"
        if result.evidence_path:
            assert not os.path.isfile(result.evidence_path)
        if result.log_path:
            assert not os.path.isfile(result.log_path)

    def test_no_op_no_writes(self):
        spec = JobSpec(job_id="test-nocr-002", branch="feat/test", task="implementer", no_op=True)
        result = run_job(spec)
        assert result.evidence_path == ""
        assert result.log_path == ""

    def test_path_validation_blocks_controller(self):
        ok, _ = validate_path(r"C:\Users\KK\vibe-coding-repo\scripts")
        assert not ok


class TestSelfCheck(unittest.TestCase):
    """Test the self-check function."""

    def test_self_check_passes(self):
        result = self_check()
        assert result["passed"] is True
        assert result["version"] == "1.0.0"
        assert len(result["checks"]) >= 8
        for check in result["checks"]:
            assert check["passed"], f"Check {check['name']} failed: {check.get('error')}"


if __name__ == "__main__":
    unittest.main()
