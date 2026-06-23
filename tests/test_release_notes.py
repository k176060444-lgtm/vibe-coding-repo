#!/usr/bin/env python3
"""V1.21.27A — Release Notes unit tests.

Covers vibe_release_notes.py behavior:
- _parse_merge_commits: git log parsing
- _classify_pr: branch prefix classification
- _extract_capability_changes: capability extraction
- _recommend_next_phase: recommendation logic
- format_markdown: markdown rendering
- generate_report: full report structure
- Edge cases: empty input, missing fields, degradation

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


# ── _parse_merge_commits ────────────────────────────────────────────────────

class TestParseMergeCommits:
    """Tests for _parse_merge_commits()."""

    def test_single_merge_commit(self):
        """Parse a single merge commit line."""
        from vibe_release_notes import _parse_merge_commits
        log = "abc1234 Merge pull request #42 from k176060444-lgtm/wo-code-test-001"
        prs = _parse_merge_commits(log)
        assert len(prs) == 1
        assert prs[0]["pr_number"] == 42
        assert prs[0]["sha"] == "abc1234"
        assert prs[0]["branch"] == "wo-code-test-001"
        assert "42" in prs[0]["url"]

    def test_multiple_merge_commits(self):
        """Parse multiple merge commits."""
        from vibe_release_notes import _parse_merge_commits
        log = "\n".join([
            "aaa1111 Merge pull request #1 from user/branch-a",
            "bbb2222 Merge pull request #2 from user/branch-b",
            "ccc3333 Merge pull request #3 from user/branch-c",
        ])
        prs = _parse_merge_commits(log)
        assert len(prs) == 3
        assert [p["pr_number"] for p in prs] == [1, 2, 3]

    def test_limit_applied(self):
        """Limit truncates results."""
        from vibe_release_notes import _parse_merge_commits
        log = "\n".join([
            "aaa1111 Merge pull request #1 from user/a",
            "bbb2222 Merge pull request #2 from user/b",
            "ccc3333 Merge pull request #3 from user/c",
        ])
        prs = _parse_merge_commits(log, limit=2)
        assert len(prs) == 2

    def test_empty_log(self):
        """Empty log → empty list."""
        from vibe_release_notes import _parse_merge_commits
        assert _parse_merge_commits("") == []

    def test_non_merge_lines_skipped(self):
        """Non-merge lines are skipped."""
        from vibe_release_notes import _parse_merge_commits
        log = "\n".join([
            "aaa1111 Some regular commit",
            "bbb2222 Merge pull request #5 from user/branch",
            "ccc3333 Another regular commit",
        ])
        prs = _parse_merge_commits(log)
        assert len(prs) == 1
        assert prs[0]["pr_number"] == 5

    def test_url_format(self):
        """PR URL contains the PR number."""
        from vibe_release_notes import _parse_merge_commits
        log = "abc1234 Merge pull request #99 from k176060444-lgtm/feat"
        prs = _parse_merge_commits(log)
        assert "/pull/99" in prs[0]["url"]


# ── _classify_pr ────────────────────────────────────────────────────────────

class TestClassifyPr:
    """Tests for _classify_pr()."""

    def test_wo_code_is_feature(self):
        from vibe_release_notes import _classify_pr
        assert _classify_pr("wo-code-something-001") == "feature"

    def test_wo_doc_is_documentation(self):
        from vibe_release_notes import _classify_pr
        assert _classify_pr("wo-doc-readme-001") == "documentation"

    def test_wo_maint_is_maintenance(self):
        from vibe_release_notes import _classify_pr
        assert _classify_pr("wo-maint-cleanup-001") == "maintenance"

    def test_wo_fix_is_bugfix(self):
        from vibe_release_notes import _classify_pr
        assert _classify_pr("wo-fix-bug-001") == "bugfix"

    def test_wo_test_is_testing(self):
        from vibe_release_notes import _classify_pr
        assert _classify_pr("wo-test-smoke-001") == "testing"

    def test_unknown_prefix_is_other(self):
        from vibe_release_notes import _classify_pr
        assert _classify_pr("feat/something") == "other"

    def test_empty_is_other(self):
        from vibe_release_notes import _classify_pr
        assert _classify_pr("") == "other"

    def test_docs_is_other(self):
        from vibe_release_notes import _classify_pr
        """'docs/' prefix is NOT wo-doc-."""
        assert _classify_pr("docs/something") == "other"

    def test_test_is_other(self):
        from vibe_release_notes import _classify_pr
        """'test/' prefix is NOT wo-test-."""
        assert _classify_pr("test/something") == "other"


# ── _extract_capability_changes ─────────────────────────────────────────────

class TestExtractCapabilityChanges:
    """Tests for _extract_capability_changes()."""

    def test_extracts_name_from_branch(self):
        """Name is derived from branch after prefix removal."""
        from vibe_release_notes import _extract_capability_changes
        prs = [{"sha": "a", "pr_number": 1, "branch": "wo-code-smoke-test-001", "url": ""}]
        caps = _extract_capability_changes(prs, "/nonexistent")
        assert len(caps) == 1
        assert caps[0]["type"] == "feature"
        assert caps[0]["pr"] == 1
        # Sequence number removed, dashes → spaces, title case
        assert "Smoke Test" in caps[0]["name"]

    def test_empty_prs(self):
        """Empty PR list → empty capabilities."""
        from vibe_release_notes import _extract_capability_changes
        assert _extract_capability_changes([], "/nonexistent") == []

    def test_mixed_types(self):
        """Mixed branch types classified correctly."""
        from vibe_release_notes import _extract_capability_changes
        prs = [
            {"sha": "a", "pr_number": 1, "branch": "wo-code-feat-001", "url": ""},
            {"sha": "b", "pr_number": 2, "branch": "wo-doc-guide-001", "url": ""},
            {"sha": "c", "pr_number": 3, "branch": "wo-fix-bug-001", "url": ""},
        ]
        caps = _extract_capability_changes(prs, "/nonexistent")
        types = [c["type"] for c in caps]
        assert types == ["feature", "documentation", "bugfix"]


# ── _recommend_next_phase ───────────────────────────────────────────────────

def _import_recommend():
    from vibe_release_notes import _recommend_next_phase
    return _recommend_next_phase


class TestRecommendNextPhase:
    """Tests for _recommend_next_phase()."""

    def test_audit_tainted_lock_recommendation(self):
        """audit_tainted lock → recommendation to maintain it."""
        recommend = _import_recommend()
        safety = {"audit_tainted_lock": {"job_id": "wo-code-repo-status-001"}}
        recs = recommend({"feature": 0, "documentation": 0, "testing": 0}, safety)
        assert any("audit_tainted" in r for r in recs)

    def test_many_features_recommend_stabilization(self):
        """feature > 5 → stabilization recommendation."""
        recommend = _import_recommend()
        recs = recommend({"feature": 10, "documentation": 0, "testing": 0}, {})
        assert any("stabilization" in r.lower() or "integration" in r.lower() for r in recs)

    def test_few_tests_recommend_increase(self):
        """test < 3 → increase coverage recommendation."""
        recommend = _import_recommend()
        recs = recommend({"feature": 0, "documentation": 0, "testing": 1}, {})
        assert any("test coverage" in r.lower() or "increase" in r.lower() for r in recs)

    def test_many_docs_recommend_guides(self):
        """doc > 5 → user-facing guides recommendation."""
        recommend = _import_recommend()
        recs = recommend({"feature": 0, "documentation": 10, "testing": 0}, {})
        assert any("guide" in r.lower() or "user-facing" in r.lower() for r in recs)

    def test_always_returns_list(self):
        """Always returns a non-empty list."""
        recommend = _import_recommend()
        recs = recommend({"feature": 0, "documentation": 0, "testing": 5}, {})
        assert isinstance(recs, list)
        assert len(recs) > 0

    def test_no_safety_no_tainted_rec(self):
        """No audit_tainted → no tainted recommendation."""
        recommend = _import_recommend()
        recs = recommend({"feature": 0, "documentation": 0, "testing": 5}, {})
        assert not any("audit_tainted" in r for r in recs)


# ── format_markdown ─────────────────────────────────────────────────────────

def _minimal_report():
    """Return a minimal valid report dict."""
    return {
        "current_main_sha": "abc123def456",
        "generated_at": "2026-06-24T00:00:00+00:00",
        "total_merged_prs": 2,
        "merged_prs": [
            {"sha": "aaa1111", "pr_number": 1, "branch": "wo-code-feat-001",
             "url": "https://github.com/k176060444-lgtm/vibe-coding-repo/pull/1"},
            {"sha": "bbb2222", "pr_number": 2, "branch": "wo-doc-guide-001",
             "url": "https://github.com/k176060444-lgtm/vibe-coding-repo/pull/2"},
        ],
        "pr_summary": {"feature": 1, "documentation": 1, "maintenance": 0,
                       "bugfix": 0, "testing": 0, "other": 0},
        "work_orders": [],
        "capability_changes": [
            {"name": "Feat", "type": "feature", "pr": 1, "branch": "wo-code-feat-001"},
            {"name": "Guide", "type": "documentation", "pr": 2, "branch": "wo-doc-guide-001"},
        ],
        "changed_paths_summary": {
            "docs_count": 3, "scripts_count": 5,
            "docs": [{"name": "a.md", "size_bytes": 100}],
            "scripts": [{"name": "s.py", "size_bytes": 200}],
        },
        "safety_status": {
            "audit_tainted_lock": None,
            "secrets_modified": False,
            "ci_modified": False,
            "provider_modified": False,
            "force_operations": False,
        },
        "recommended_next_phase": ["Continue work"],
        "report_version": "1.0",
    }


class TestFormatMarkdown:
    """Tests for format_markdown()."""

    def test_has_header(self):
        """Report has release notes header."""
        from vibe_release_notes import format_markdown
        md = format_markdown(_minimal_report())
        assert "Release Notes" in md or "Progress Report" in md

    def test_has_main_sha(self):
        """Report contains main SHA."""
        from vibe_release_notes import format_markdown
        md = format_markdown(_minimal_report())
        assert "abc123def456" in md

    def test_has_total_prs(self):
        """Report contains total merged PRs."""
        from vibe_release_notes import format_markdown
        md = format_markdown(_minimal_report())
        assert "2" in md

    def test_has_pr_summary(self):
        """Report contains PR summary types."""
        from vibe_release_notes import format_markdown
        md = format_markdown(_minimal_report())
        assert "Feature" in md
        assert "Documentation" in md

    def test_has_recent_merges_non_compact(self):
        """Non-compact mode shows recent merges."""
        from vibe_release_notes import format_markdown
        md = format_markdown(_minimal_report(), compact=False)
        assert "Recent Merges" in md
        assert "#1" in md

    def test_compact_hides_recent_merges(self):
        """Compact mode hides recent merges section."""
        from vibe_release_notes import format_markdown
        md = format_markdown(_minimal_report(), compact=True)
        assert "Recent Merges" not in md

    def test_has_safety_status(self):
        """Report contains safety status section."""
        from vibe_release_notes import format_markdown
        md = format_markdown(_minimal_report())
        assert "Safety Status" in md
        assert "Secrets modified" in md

    def test_has_toolchain(self):
        """Report contains toolchain section."""
        from vibe_release_notes import format_markdown
        md = format_markdown(_minimal_report())
        assert "Toolchain" in md
        assert "Scripts" in md
        assert "Docs" in md

    def test_has_recommendations(self):
        """Report contains recommended next phase."""
        from vibe_release_notes import format_markdown
        md = format_markdown(_minimal_report())
        assert "Recommended Next Phase" in md
        assert "Continue work" in md

    def test_has_report_version(self):
        """Report contains version string."""
        from vibe_release_notes import format_markdown
        md = format_markdown(_minimal_report())
        assert "1.0" in md

    def test_zero_counts_not_shown(self):
        """PR types with 0 count are not shown."""
        from vibe_release_notes import format_markdown
        md = format_markdown(_minimal_report())
        # maintenance=0, bugfix=0 should not appear
        assert "Maintenance" not in md
        assert "Bugfix" not in md


# ── generate_report structure ───────────────────────────────────────────────

class TestGenerateReportStructure:
    """Tests for generate_report() output structure."""

    def test_has_required_keys(self, tmp_path):
        """Report has all required top-level keys."""
        from vibe_release_notes import generate_report
        # Create minimal repo structure
        (tmp_path / "docs").mkdir()
        (tmp_path / "scripts").mkdir()
        (tmp_path / "docs" / "test.md").write_text("# test")
        (tmp_path / "scripts" / "test.py").write_text("# test")

        with patch("vibe_release_notes._run_git") as mock_git, \
             patch("vibe_release_notes._run_script") as mock_script:
            mock_git.return_value = ""
            mock_script.return_value = None
            report = generate_report(str(tmp_path), str(tmp_path / "jobs"))

        required = ["current_main_sha", "generated_at", "total_merged_prs",
                     "merged_prs", "pr_summary", "capability_changes",
                     "changed_paths_summary", "safety_status",
                     "recommended_next_phase", "report_version"]
        for key in required:
            assert key in report, f"Missing key: {key}"

    def test_pr_summary_has_all_types(self, tmp_path):
        """pr_summary has all 6 type keys."""
        from vibe_release_notes import generate_report
        (tmp_path / "docs").mkdir()
        (tmp_path / "scripts").mkdir()

        with patch("vibe_release_notes._run_git") as mock_git, \
             patch("vibe_release_notes._run_script") as mock_script:
            mock_git.return_value = ""
            mock_script.return_value = None
            report = generate_report(str(tmp_path), str(tmp_path / "jobs"))

        for t in ["feature", "documentation", "maintenance", "bugfix", "testing", "other"]:
            assert t in report["pr_summary"]

    def test_safety_status_fields(self, tmp_path):
        """safety_status has all required fields."""
        from vibe_release_notes import generate_report
        (tmp_path / "docs").mkdir()
        (tmp_path / "scripts").mkdir()

        with patch("vibe_release_notes._run_git") as mock_git, \
             patch("vibe_release_notes._run_script") as mock_script:
            mock_git.return_value = ""
            mock_script.return_value = None
            report = generate_report(str(tmp_path), str(tmp_path / "jobs"))

        safety = report["safety_status"]
        for key in ["secrets_modified", "ci_modified", "provider_modified", "force_operations"]:
            assert key in safety
            assert safety[key] is False

    def test_empty_repo_still_produces_report(self, tmp_path):
        """Empty repo (no docs/scripts) still produces valid report."""
        from vibe_release_notes import generate_report

        with patch("vibe_release_notes._run_git") as mock_git, \
             patch("vibe_release_notes._run_script") as mock_script:
            mock_git.return_value = ""
            mock_script.return_value = None
            report = generate_report(str(tmp_path), str(tmp_path / "jobs"))

        assert report["total_merged_prs"] == 0
        assert report["merged_prs"] == []
        assert report["changed_paths_summary"]["docs_count"] == 0
        assert report["changed_paths_summary"]["scripts_count"] == 0

    def test_report_version_is_string(self, tmp_path):
        """report_version is a string."""
        from vibe_release_notes import generate_report
        (tmp_path / "docs").mkdir()
        (tmp_path / "scripts").mkdir()

        with patch("vibe_release_notes._run_git") as mock_git, \
             patch("vibe_release_notes._run_script") as mock_script:
            mock_git.return_value = ""
            mock_script.return_value = None
            report = generate_report(str(tmp_path), str(tmp_path / "jobs"))

        assert isinstance(report["report_version"], str)


# ── Edge cases ──────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Edge cases for release notes."""

    def test_format_markdown_with_no_prs(self):
        """Report with 0 PRs still renders markdown."""
        from vibe_release_notes import format_markdown
        report = _minimal_report()
        report["total_merged_prs"] = 0
        report["merged_prs"] = []
        report["pr_summary"] = {k: 0 for k in report["pr_summary"]}
        report["capability_changes"] = []
        md = format_markdown(report)
        assert "Release Notes" in md or "Progress Report" in md
        assert "0" in md

    def test_format_markdown_with_audit_lock(self):
        """Report with audit_tainted lock renders lock info."""
        from vibe_release_notes import format_markdown
        report = _minimal_report()
        report["safety_status"]["audit_tainted_lock"] = {
            "job_id": "wo-code-repo-status-001",
            "audit_status": "audit_tainted",
            "push_allowed": False,
            "permanent": True,
        }
        md = format_markdown(report)
        assert "audit_tainted" in md
        assert "wo-code-repo-status-001" in md

    def test_classify_pr_edge_cases(self):
        """Edge cases for branch classification."""
        from vibe_release_notes import _classify_pr
        # Exact prefix match, not substring
        assert _classify_pr("wo-code-x") == "feature"
        assert _classify_pr("wo-codex") == "other"
        assert _classify_pr("feat/wo-code-x") == "other"

    def test_parse_merge_commits_malformed_lines(self):
        """Malformed lines are silently skipped."""
        from vibe_release_notes import _parse_merge_commits
        log = "\n".join([
            "not a merge commit",
            "",
            "Merge pull request",  # missing number
            "abc1234 Merge pull request #99 from user/branch",
        ])
        prs = _parse_merge_commits(log)
        assert len(prs) == 1
        assert prs[0]["pr_number"] == 99

    def test_recommend_next_phase_balanced(self):
        """Balanced stats → no special recommendations (just base ones)."""
        recommend = _import_recommend()
        recs = recommend({"feature": 3, "documentation": 3, "testing": 5}, {})
        # Should not have stabilization or increase coverage
        assert not any("stabilization" in r.lower() for r in recs)
        assert not any("increase" in r.lower() for r in recs)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
