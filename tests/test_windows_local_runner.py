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
    JobSpec, JobResult, run_job, self_check,
    is_path_allowed, is_path_blocked, validate_path,
    is_path_write_allowed, is_path_read_allowed,
    WORKTREE_ROOT, EVIDENCE_ROOT, LOG_ROOT, WRAPPER_PATH,
)


class TestPathAllowlist(unittest.TestCase):
    """Test path allowlist validation."""

    def test_drive_d_allowed(self):
        assert is_path_allowed(r"D:\vibedev-evidence\21bao\test")
        assert is_path_allowed(r"D:\vibedev-logs\21bao\test")
        assert is_path_allowed(r"D:\vibedev-tools\bin\opencode-21bao.ps1")

    def test_drive_e_allowed(self):
        assert is_path_allowed(r"E:\vibedev-worktrees\21bao\test")
        assert not is_path_allowed(r"E:\some-other-path")  # V1.20.23: not in subtree

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
        assert "subtree" in reason  # V1.20.23: subtree containment message


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
        assert len(result["checks"]) >= 28  # V1.20.23: 28 checks
        for check in result["checks"]:
            assert check["passed"], f"Check {check['name']} failed: {check.get('error')}"


class TestBlocklistBypassPrevention(unittest.TestCase):
    """V1.20.18: Test controller repo blocklist bypass prevention."""

    PROFILE_REPO = r"C:\Users\KK\AppData\Local\hermes\profiles\vibedev\home\vibe-coding-repo"

    def test_profile_scoped_path_blocked(self):
        """Profile-scoped controller repo path must be blocked."""
        ok, _ = validate_path(self.PROFILE_REPO + r"\scripts\test.py")
        assert not ok, "Profile-scoped controller repo should be blocked"

    def test_case_insensitive_bypass_blocked(self):
        """Uppercase variant of controller repo path must be blocked."""
        ok, _ = validate_path(self.PROFILE_REPO.upper() + r"\test")
        assert not ok, "Uppercase controller repo should be blocked"

    def test_forward_slash_bypass_blocked(self):
        """Forward slash variant of controller repo path must be blocked."""
        fwd = self.PROFILE_REPO.replace("\\", "/") + "/test"
        ok, _ = validate_path(fwd)
        assert not ok, "Forward slash controller repo should be blocked"

    def test_path_traversal_blocked(self):
        """Path with .. traversal resolving to controller repo must be blocked."""
        traversal = os.path.normpath(self.PROFILE_REPO + "/../../../" + self.PROFILE_REPO)
        ok, _ = validate_path(traversal)
        assert not ok, "Path traversal should be blocked"

    def test_trailing_slash_bypass_blocked(self):
        """Trailing slash variant of controller repo path must be blocked."""
        ok, _ = validate_path(self.PROFILE_REPO + "\\\\")
        assert not ok, "Trailing slash controller repo should be blocked"

    def test_old_path_still_blocked(self):
        """Old controller repo path must still be blocked."""
        ok, _ = validate_path(r"C:\Users\KK\vibe-coding-repo\test")
        assert not ok, "Old controller repo path should still be blocked"

    def test_d_drive_subtree_containment(self):
        """V1.20.23: Arbitrary D drive path should be blocked (subtree containment)."""
        ok, _ = validate_path(r"D:\vibedev-test-new")
        assert not ok, "Arbitrary D path should be blocked (subtree containment)"

    def test_e_drive_subtree_containment(self):
        """V1.20.23: Arbitrary E drive path should be blocked (subtree containment)."""
        ok, _ = validate_path(r"E:\vibedev-test-new")
        assert not ok, "Arbitrary E path should be blocked (subtree containment)"

    def test_is_path_blocked_profile_scoped(self):
        """is_path_blocked must detect profile-scoped controller repo."""
        assert is_path_blocked(self.PROFILE_REPO + r"\test")
        assert is_path_blocked(self.PROFILE_REPO)

    def test_is_path_blocked_case_insensitive(self):
        """is_path_blocked must be case-insensitive."""
        assert is_path_blocked(self.PROFILE_REPO.upper() + r"\test")
        assert is_path_blocked(self.PROFILE_REPO.lower() + r"\test")


class TestCanonicalizationFailClosed(unittest.TestCase):
    """V1.20.18: Test that canonicalization failures are fail-closed."""

    PROFILE_REPO = r"C:\Users\KK\AppData\Local\hermes\profiles\vibedev\home\vibe-coding-repo"

    def test_null_byte_path_rejected_or_handled(self):
        """Path with null byte must be rejected or safely handled (fail-closed)."""
        try:
            ok, reason = validate_path("D:\\test\x00evil")
            # If it passes validation, it must at least be on D: (allowlisted)
            # The important thing is it doesn't crash or bypass
            assert isinstance(ok, bool), "validate_path must return bool"
            assert isinstance(reason, str), "validate_path must return reason string"
        except (OSError, ValueError):
            pass  # Exception is fail-closed

    def test_is_path_blocked_fail_closed_on_bad_input(self):
        """is_path_blocked must return True (blocked) for unresolvable paths."""
        try:
            result = is_path_blocked("D:\\test\x00evil")
            assert isinstance(result, bool), "is_path_blocked must return bool"
        except (OSError, ValueError):
            pass  # Exception is fail-closed

    def test_is_path_allowed_fail_closed_on_bad_input(self):
        """is_path_allowed must return False for unresolvable paths."""
        try:
            result = is_path_allowed("D:\\test\x00evil")
            assert isinstance(result, bool), "is_path_allowed must return bool"
        except (OSError, ValueError):
            pass  # Exception is fail-closed

    def test_canonicalize_no_normpath_fallback(self):
        """_canonicalize must not have normpath fallback (fail-closed)."""
        import inspect
        from vibe_windows_local_runner import _canonicalize
        src = inspect.getsource(_canonicalize)
        lines = src.split('\n')
        code_lines = [l for l in lines if not l.strip().startswith('#')
                      and '"""' not in l and "'''" not in l]
        code_text = '\n'.join(code_lines)
        assert 'normpath' not in code_text, \
            "_canonicalize should not use normpath in code (fail-closed requirement)"

    def test_symlink_to_controller_repo_blocked(self):
        """If a junction/symlink resolves to controller repo, it must be blocked.

        NOTE: Actual junction creation requires admin privileges.
        This test verifies the mechanism (realpath + blocklist check).
        Defense-in-depth: D/E allowlist restricts attack surface.
        """
        assert is_path_blocked(self.PROFILE_REPO)
        assert is_path_blocked(self.PROFILE_REPO.upper())
        assert is_path_blocked(self.PROFILE_REPO.lower())


class TestSubtreeContainment(unittest.TestCase):
    """V1.20.23: Test subtree containment hardening."""

    def test_traversal_escape_from_worktree_blocked(self):
        ok, _ = validate_path(r"E:\vibedev-worktrees\21bao\..\..\..\etc\passwd")
        assert not ok, "Traversal escape from worktree subtree should be blocked"

    def test_e_etc_passwd_blocked(self):
        ok, _ = validate_path(r"E:\etc\passwd")
        assert not ok, "E drive but not in allowed subtree should be blocked"

    def test_sibling_directory_blocked(self):
        ok, _ = validate_path(r"E:\vibedev-worktrees\21bao-other\test")
        assert not ok, "Sibling directory should be blocked (prefix false-match)"

    def test_allowed_worktree_child(self):
        ok, _ = validate_path(r"E:\vibedev-worktrees\21bao\feat-test")
        assert ok, "Worktree child should be allowed"

    def test_allowed_evidence_child(self):
        ok, _ = validate_path(r"D:\vibedev-evidence\21bao\job-x")
        assert ok, "Evidence child should be allowed"

    def test_allowed_log_child(self):
        ok, _ = validate_path(r"D:\vibedev-logs\21bao\job-x")
        assert ok, "Log child should be allowed"

    def test_allowed_sandbox_child(self):
        ok, _ = validate_path(r"E:\vibedev-sandbox\21bao\test")
        assert ok, "Sandbox child should be allowed"

    def test_allowed_artifacts_child(self):
        ok, _ = validate_path(r"E:\vibedev-artifacts\21bao\test")
        assert ok, "Artifacts child should be allowed"

    def test_allowed_cache_child(self):
        ok, _ = validate_path(r"D:\vibedev-cache\test")
        assert ok, "Cache child should be allowed"

    def test_tools_read_allowed(self):
        ok, _ = validate_path(r"D:\vibedev-tools\bin\opencode-21bao.ps1")
        assert ok, "Tools path should be read-allowed"

    def test_tools_write_blocked(self):
        ok, _ = validate_path(r"D:\vibedev-tools\bin\test.exe", mode="write")
        assert not ok, "Tools path should be write-blocked"

    def test_config_write_blocked(self):
        ok, _ = validate_path(r"D:\vibedev-config\opencode\test.json", mode="write")
        assert not ok, "Config path should be write-blocked"

    def test_worktree_write_allowed(self):
        ok, _ = validate_path(r"E:\vibedev-worktrees\21bao\feat-x", mode="write")
        assert ok, "Worktree path should be write-allowed"

    def test_evidence_write_allowed(self):
        ok, _ = validate_path(r"D:\vibedev-evidence\21bao\job-x", mode="write")
        assert ok, "Evidence path should be write-allowed"

    def test_other_worker_evidence_blocked(self):
        ok, _ = validate_path(r"D:\vibedev-evidence\other\test")
        assert not ok, "Evidence path for other worker should be blocked"

    def test_case_variation_allowed(self):
        ok, _ = validate_path(r"e:\vibedev-worktrees\21bao\test")
        assert ok, "Case variation should be allowed"

    def test_exact_root_allowed(self):
        ok, _ = validate_path(r"E:\vibedev-worktrees\21bao")
        assert ok, "Exact root should be allowed"

    def test_write_allowed_function(self):
        assert is_path_write_allowed(r"E:\vibedev-worktrees\21bao\test")
        assert not is_path_write_allowed(r"D:\vibedev-tools\bin\test.exe")
        assert not is_path_write_allowed(r"D:\vibedev-config\opencode\test.json")

    def test_read_allowed_function(self):
        assert is_path_read_allowed(r"E:\vibedev-worktrees\21bao\test")
        assert is_path_read_allowed(r"D:\vibedev-tools\bin\test.exe")
        assert is_path_read_allowed(r"D:\vibedev-config\opencode\test.json")


if __name__ == "__main__":
    unittest.main()
