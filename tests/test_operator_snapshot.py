#!/usr/bin/env python3
"""V1.21.26A — Operator Snapshot unit tests.

Covers candidate-26a: vibe_operator_snapshot.py behavior verification.
- repo/jobs_summary/locks/recommended_next_action/warnings propagation
- _build_compact rendering (via _print_text compact mode)
- main != origin/main sync warning
- --json output shape
- Prevention of overall_status/overall regression

Read-only. No real execution, no gate verdict change.
"""
import io
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_repo_info(local="aaa111", remote="aaa111", dirty=False, branch="main"):
    """Return a repo_info dict with controlled values."""
    return {
        "local_main_sha": local,
        "remote_main_sha": remote,
        "main_consistent": local == remote if (local and remote) else False,
        "working_tree_dirty": dirty,
        "current_branch": branch,
    }


def _mock_advisor(total=5, merged=2, blocked=0, warnings=None,
                  action_items=None, unresolved=None, lifecycle=None):
    """Return a minimal advisor_data dict."""
    return {
        "summary": {
            "total_jobs": total,
            "merged_total": merged,
            "blocked_total": blocked,
            "hidden_blocked": 0,
            "recovered_jobs_count": 0,
            "unresolved_jobs_count": len(unresolved or []),
            "action_items_count": len(action_items or []),
            "warnings_count": len(warnings or []),
            "informational_jobs_count": 0,
            "lifecycle": lifecycle or {"merged": merged, "unknown": total - merged},
        },
        "blocked_jobs": [],
        "action_items": action_items or [],
        "warnings": warnings or [],
        "unresolved_jobs": unresolved or [],
    }


# ── _get_repo_info tests ────────────────────────────────────────────────────

class TestGetRepoInfo:
    """Tests for _get_repo_info()."""

    def test_consistent_main(self, tmp_path):
        """local == remote → main_consistent=True."""
        from vibe_operator_snapshot import _get_repo_info
        with patch("vibe_operator_snapshot._run_git") as mock_git:
            mock_git.side_effect = lambda *args, **kw: {
                ("rev-parse", "main"): "aaa111",
                ("rev-parse", "origin/main"): "aaa111",
                ("status", "--porcelain"): "",
                ("branch", "--show-current"): "main",
            }.get(args, "")
            info = _get_repo_info(str(tmp_path))
        assert info["main_consistent"] is True
        assert info["local_main_sha"] == "aaa111"
        assert info["remote_main_sha"] == "aaa111"
        assert info["working_tree_dirty"] is False

    def test_inconsistent_main(self, tmp_path):
        """local != remote → main_consistent=False."""
        from vibe_operator_snapshot import _get_repo_info
        with patch("vibe_operator_snapshot._run_git") as mock_git:
            mock_git.side_effect = lambda *args, **kw: {
                ("rev-parse", "main"): "aaa111",
                ("rev-parse", "origin/main"): "bbb222",
                ("status", "--porcelain"): "",
                ("branch", "--show-current"): "main",
            }.get(args, "")
            info = _get_repo_info(str(tmp_path))
        assert info["main_consistent"] is False

    def test_dirty_working_tree(self, tmp_path):
        """Uncommitted changes → working_tree_dirty=True."""
        from vibe_operator_snapshot import _get_repo_info
        with patch("vibe_operator_snapshot._run_git") as mock_git:
            mock_git.side_effect = lambda *args, **kw: {
                ("rev-parse", "main"): "aaa111",
                ("rev-parse", "origin/main"): "aaa111",
                ("status", "--porcelain"): "M file.py",
                ("branch", "--show-current"): "main",
            }.get(args, "")
            info = _get_repo_info(str(tmp_path))
        assert info["working_tree_dirty"] is True

    def test_empty_sha_returns_false(self, tmp_path):
        """Empty SHA → main_consistent=False."""
        from vibe_operator_snapshot import _get_repo_info
        with patch("vibe_operator_snapshot._run_git") as mock_git:
            mock_git.side_effect = lambda *args, **kw: {
                ("rev-parse", "main"): "",
                ("rev-parse", "origin/main"): "aaa111",
                ("status", "--porcelain"): "",
                ("branch", "--show-current"): "main",
            }.get(args, "")
            info = _get_repo_info(str(tmp_path))
        assert info["main_consistent"] is False


# ── _extract_locks tests ────────────────────────────────────────────────────

class TestExtractLocks:
    """Tests for _extract_locks()."""

    def test_no_advisor_data(self):
        """None advisor → empty locks."""
        from vibe_operator_snapshot import _extract_locks
        assert _extract_locks(None) == []

    def test_empty_blocked_jobs(self):
        """No blocked jobs → empty locks."""
        from vibe_operator_snapshot import _extract_locks
        assert _extract_locks({"blocked_jobs": []}) == []

    def test_blocked_job_produces_lock(self):
        """Blocked job → lock with push_allowed=False."""
        from vibe_operator_snapshot import _extract_locks
        advisor = {"blocked_jobs": [
            {"job_id": "wo-001", "audit_status": "audit_tainted", "reason": "test"},
        ]}
        locks = _extract_locks(advisor)
        assert len(locks) == 1
        assert locks[0]["job_id"] == "wo-001"
        assert locks[0]["lock_type"] == "audit_tainted"
        assert locks[0]["push_allowed"] is False


# ── _extract_warnings tests ─────────────────────────────────────────────────

class TestExtractWarnings:
    """Tests for _extract_warnings()."""

    def test_main_inconsistency_warning(self):
        """main_consistent=False → warning about inconsistency."""
        from vibe_operator_snapshot import _extract_warnings
        repo = _mock_repo_info(local="aaa111", remote="bbb222")
        warnings = _extract_warnings(None, repo)
        assert any("inconsistent" in w.lower() for w in warnings)

    def test_dirty_tree_warning(self):
        """working_tree_dirty=True → warning about uncommitted changes."""
        from vibe_operator_snapshot import _extract_warnings
        repo = _mock_repo_info(dirty=True)
        warnings = _extract_warnings(None, repo)
        assert any("uncommitted" in w.lower() for w in warnings)

    def test_advisor_warnings_included(self):
        """Advisor warnings are included in output."""
        from vibe_operator_snapshot import _extract_warnings
        advisor = {"warnings": [
            {"job_id": "wo-001", "warning": "test warning"},
        ]}
        warnings = _extract_warnings(advisor, _mock_repo_info())
        assert any("wo-001" in w and "test warning" in w for w in warnings)

    def test_no_warnings_clean_state(self):
        """Clean state with no advisor warnings → empty list."""
        from vibe_operator_snapshot import _extract_warnings
        warnings = _extract_warnings(None, _mock_repo_info())
        assert warnings == []


# ── _determine_next_action tests ────────────────────────────────────────────

class TestDetermineNextAction:
    """Tests for _determine_next_action()."""

    def test_no_advisor_data(self):
        """None advisor → review_queue_state."""
        from vibe_operator_snapshot import _determine_next_action
        assert _determine_next_action(None, {}, []) == "review_queue_state"

    def test_blocked_jobs(self):
        """Locks present → resolve_blocked."""
        from vibe_operator_snapshot import _determine_next_action
        locks = [{"job_id": "wo-001", "lock_type": "audit_tainted"}]
        result = _determine_next_action({"action_items": []}, {}, locks)
        assert "resolve_blocked" in result

    def test_high_priority_actions(self):
        """High priority actions → investigate_failures."""
        from vibe_operator_snapshot import _determine_next_action
        advisor = {"action_items": [
            {"priority": "high", "action": "fix", "job_id": "wo-001"},
        ]}
        result = _determine_next_action(advisor, {}, [])
        assert "investigate_failures" in result

    def test_ready_for_merge(self):
        """Ready for merge items → process_merge_queue."""
        from vibe_operator_snapshot import _determine_next_action
        advisor = {"action_items": [
            {"priority": "medium", "action": "ready_for_merge", "job_id": "wo-001"},
        ]}
        result = _determine_next_action(advisor, {}, [])
        assert "process_merge_queue" in result

    def test_medium_priority_pending(self):
        """Medium priority actions → continue_processing."""
        from vibe_operator_snapshot import _determine_next_action
        advisor = {"action_items": [
            {"priority": "medium", "action": "continue", "job_id": "wo-001"},
        ]}
        result = _determine_next_action(advisor, {}, [])
        assert "continue_processing" in result

    def test_unresolved_jobs(self):
        """Unresolved jobs → resolve_unresolved."""
        from vibe_operator_snapshot import _determine_next_action
        advisor = {"action_items": [], "unresolved_jobs": ["wo-001"]}
        result = _determine_next_action(advisor, {}, [])
        assert "resolve_unresolved" in result

    def test_queue_clean(self):
        """No issues → queue_clean."""
        from vibe_operator_snapshot import _determine_next_action
        advisor = {"action_items": [], "unresolved_jobs": []}
        result = _determine_next_action(advisor, {}, [])
        assert "queue_clean" in result


# ── Snapshot structure tests ────────────────────────────────────────────────

class TestSnapshotStructure:
    """Tests for the snapshot dict produced by main()."""

    def test_json_output_has_required_keys(self, tmp_path):
        """--json output must have repo, jobs_summary, locks, etc."""
        from vibe_operator_snapshot import main
        with patch("vibe_operator_snapshot._get_repo_info") as mock_repo, \
             patch("vibe_operator_snapshot._run_advisor") as mock_advisor:
            mock_repo.return_value = _mock_repo_info()
            mock_advisor.return_value = _mock_advisor()
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                ret = main(["--json", "--repo-root", str(tmp_path)])
        assert ret == 0
        output = json.loads(buf.getvalue())
        # V1.21.25A required keys
        assert "repo" in output
        assert "jobs_summary" in output
        assert "locks" in output
        assert "recommended_next_action" in output
        assert "warnings" in output
        assert "action_items_top" in output

    def test_no_overall_status_key(self, tmp_path):
        """Regression: overall_status must NOT appear in snapshot (V1.21.25A fix)."""
        from vibe_operator_snapshot import main
        with patch("vibe_operator_snapshot._get_repo_info") as mock_repo, \
             patch("vibe_operator_snapshot._run_advisor") as mock_advisor:
            mock_repo.return_value = _mock_repo_info()
            mock_advisor.return_value = _mock_advisor()
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                main(["--json", "--repo-root", str(tmp_path)])
        output = json.loads(buf.getvalue())
        assert "overall_status" not in output, (
            "overall_status must not be in snapshot — V1.21.25A regression"
        )
        assert "overall" not in output, (
            "overall must not be in snapshot — V1.21.25A regression"
        )

    def test_repo_subdict_fields(self, tmp_path):
        """repo subdict must have repo_id, local_main_sha, remote_main_sha, etc."""
        from vibe_operator_snapshot import main
        with patch("vibe_operator_snapshot._get_repo_info") as mock_repo, \
             patch("vibe_operator_snapshot._run_advisor") as mock_advisor:
            mock_repo.return_value = _mock_repo_info()
            mock_advisor.return_value = _mock_advisor()
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                main(["--json", "--repo-root", str(tmp_path)])
        output = json.loads(buf.getvalue())
        repo = output["repo"]
        for key in ["repo_id", "local_main_sha", "remote_main_sha",
                     "main_consistent", "working_tree_dirty", "current_branch"]:
            assert key in repo, f"repo.{key} missing"

    def test_jobs_summary_fields(self, tmp_path):
        """jobs_summary must have total_jobs, merged_total, etc."""
        from vibe_operator_snapshot import main
        with patch("vibe_operator_snapshot._get_repo_info") as mock_repo, \
             patch("vibe_operator_snapshot._run_advisor") as mock_advisor:
            mock_repo.return_value = _mock_repo_info()
            mock_advisor.return_value = _mock_advisor()
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                main(["--json", "--repo-root", str(tmp_path)])
        output = json.loads(buf.getvalue())
        js = output["jobs_summary"]
        for key in ["total_jobs", "merged_total", "blocked_total",
                     "recovered_jobs_count", "unresolved_jobs_count",
                     "action_items_count", "warnings_count", "lifecycle"]:
            assert key in js, f"jobs_summary.{key} missing"


# ── Text rendering tests ────────────────────────────────────────────────────

class TestTextRendering:
    """Tests for _print_text compact/non-compact rendering."""

    def test_compact_renders_sync_status(self):
        """Compact mode shows Sync: YES/NO."""
        from vibe_operator_snapshot import _print_text
        snapshot = {
            "repo": {"local_main_sha": "aaa111bbb222", "remote_main_sha": "aaa111bbb222",
                     "main_consistent": True, "working_tree_dirty": False, "current_branch": "main"},
            "jobs_summary": {"total_jobs": 5, "merged_total": 2, "blocked_total": 0,
                             "hidden_blocked": 0, "recovered_jobs_count": 0,
                             "unresolved_jobs_count": 0, "action_items_count": 0,
                             "warnings_count": 0, "lifecycle": {}},
            "locks": [],
            "action_items_top": [],
            "recommended_next_action": "queue_clean",
            "warnings": [],
        }
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _print_text(snapshot, compact=True, locks=[], advisor_data=None)
        output = buf.getvalue()
        assert "Sync:" in output
        assert "YES" in output

    def test_compact_renders_next_action(self):
        """Compact mode shows NEXT action."""
        from vibe_operator_snapshot import _print_text
        snapshot = {
            "repo": {"local_main_sha": "aaa111bbb222", "remote_main_sha": "bbb222ccc333",
                     "main_consistent": False, "working_tree_dirty": False, "current_branch": "main"},
            "jobs_summary": {"total_jobs": 0, "merged_total": 0, "blocked_total": 0,
                             "hidden_blocked": 0, "recovered_jobs_count": 0,
                             "unresolved_jobs_count": 0, "action_items_count": 0,
                             "warnings_count": 0, "lifecycle": {}},
            "locks": [],
            "action_items_top": [],
            "recommended_next_action": "review_queue_state",
            "warnings": ["Local main and remote main are inconsistent"],
        }
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _print_text(snapshot, compact=True, locks=[], advisor_data=None)
        output = buf.getvalue()
        assert "NEXT:" in output
        assert "review_queue_state" in output

    def test_non_compact_shows_warnings(self):
        """Non-compact mode shows warnings section."""
        from vibe_operator_snapshot import _print_text
        snapshot = {
            "repo": {"local_main_sha": "aaa111bbb222", "remote_main_sha": "aaa111bbb222",
                     "main_consistent": True, "working_tree_dirty": True, "current_branch": "main"},
            "jobs_summary": {"total_jobs": 0, "merged_total": 0, "blocked_total": 0,
                             "hidden_blocked": 0, "recovered_jobs_count": 0,
                             "unresolved_jobs_count": 0, "action_items_count": 0,
                             "warnings_count": 1, "lifecycle": {}},
            "locks": [],
            "action_items_top": [],
            "recommended_next_action": "queue_clean",
            "warnings": ["Working tree has uncommitted changes"],
        }
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _print_text(snapshot, compact=False, locks=[], advisor_data=None)
        output = buf.getvalue()
        assert "WARNINGS" in output
        assert "uncommitted" in output

    def test_non_compact_shows_action_items(self):
        """Non-compact mode shows top action items."""
        from vibe_operator_snapshot import _print_text
        snapshot = {
            "repo": {"local_main_sha": "aaa111bbb222", "remote_main_sha": "aaa111bbb222",
                     "main_consistent": True, "working_tree_dirty": False, "current_branch": "main"},
            "jobs_summary": {"total_jobs": 1, "merged_total": 0, "blocked_total": 0,
                             "hidden_blocked": 0, "recovered_jobs_count": 0,
                             "unresolved_jobs_count": 0, "action_items_count": 1,
                             "warnings_count": 0, "lifecycle": {}},
            "locks": [],
            "action_items_top": [
                {"priority": "high", "action": "fix", "job_id": "wo-001", "description": "test"},
            ],
            "recommended_next_action": "investigate_failures",
            "warnings": [],
        }
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _print_text(snapshot, compact=False, locks=[], advisor_data=None)
        output = buf.getvalue()
        assert "TOP ACTIONS" in output
        assert "wo-001" in output

    def test_locks_rendered_in_output(self):
        """Locks are rendered in both compact and non-compact modes."""
        from vibe_operator_snapshot import _print_text
        snapshot = {
            "repo": {"local_main_sha": "aaa111bbb222", "remote_main_sha": "aaa111bbb222",
                     "main_consistent": True, "working_tree_dirty": False, "current_branch": "main"},
            "jobs_summary": {"total_jobs": 1, "merged_total": 0, "blocked_total": 1,
                             "hidden_blocked": 0, "recovered_jobs_count": 0,
                             "unresolved_jobs_count": 0, "action_items_count": 0,
                             "warnings_count": 0, "lifecycle": {}},
            "locks": [{"job_id": "wo-001", "lock_type": "audit_tainted",
                       "reason": "test", "push_allowed": False}],
            "action_items_top": [],
            "recommended_next_action": "resolve_blocked",
            "warnings": [],
        }
        locks = snapshot["locks"]
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _print_text(snapshot, compact=True, locks=locks, advisor_data=None)
        output = buf.getvalue()
        assert "LOCKS" in output
        assert "wo-001" in output


# ── Edge cases ──────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Edge cases for operator snapshot."""

    def test_no_advisor_data_still_produces_snapshot(self, tmp_path):
        """When advisor returns None, snapshot still has all keys."""
        from vibe_operator_snapshot import main
        with patch("vibe_operator_snapshot._get_repo_info") as mock_repo, \
             patch("vibe_operator_snapshot._run_advisor") as mock_advisor:
            mock_repo.return_value = _mock_repo_info()
            mock_advisor.return_value = None
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                ret = main(["--json", "--repo-root", str(tmp_path)])
        assert ret == 0
        output = json.loads(buf.getvalue())
        assert "repo" in output
        assert "jobs_summary" in output
        assert "locks" in output
        assert "recommended_next_action" in output
        assert output["recommended_next_action"] == "review_queue_state"

    def test_json_output_is_valid_json(self, tmp_path):
        """--json output must be valid JSON."""
        from vibe_operator_snapshot import main
        with patch("vibe_operator_snapshot._get_repo_info") as mock_repo, \
             patch("vibe_operator_snapshot._run_advisor") as mock_advisor:
            mock_repo.return_value = _mock_repo_info()
            mock_advisor.return_value = _mock_advisor()
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                main(["--json", "--repo-root", str(tmp_path)])
        # Should not raise
        parsed = json.loads(buf.getvalue())
        assert isinstance(parsed, dict)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
