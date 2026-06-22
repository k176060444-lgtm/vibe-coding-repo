"""Tests for remote_verification_gate.py (V1.21.9).

Covers:
  - PASS case
  - head SHA mismatch (BLOCK)
  - base SHA mismatch (BLOCK)
  - files mismatch (BLOCK)
  - body missing expected text (WARNING)
  - draft/ready mismatch (WARNING)
  - merged_not_reported (BLOCK)
  - stale baseRefOid (BLOCK)
  - api_failure (BLOCK)
  - pr_not_found via Python API (BLOCK)
  - local_remote_diff_mismatch (BLOCK)
  - draft+BLOCK coexistence → BLOCKED verdict
  - fetch_pr_data_result() wrapper
"""

import os
import sys

import pytest

# Add scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from remote_verification_gate import (
    MISMATCH_TYPES,
    __version__,
    fetch_pr_data_result,
    verify_pr,
)


# --- Fixtures ---

@pytest.fixture
def mock_pr():
    """Standard OPEN PR data."""
    return {
        "number": 197,
        "state": "OPEN",
        "isDraft": False,
        "mergeable": "MERGEABLE",
        "baseRefName": "main",
        "baseRefOid": "aaa111",
        "headRefName": "feat/test",
        "headRefOid": "bbb222",
        "body": "## Scope\nSome content",
        "files": [{"path": "a.py"}],
        "commits": [{"oid": "bbb222"}],
    }


@pytest.fixture
def merged_pr(mock_pr):
    """Merged PR data."""
    return {**mock_pr, "state": "MERGED"}


# --- Tests ---

class TestPassCase:
    """All expectations met → PASS."""

    def test_all_expectations_met(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            pr_diff_files=["a.py"],
            expected_head_oid="bbb222",
            expected_base_oid="aaa111",
            expected_files=["a.py"],
            expected_body_contains=["Scope"],
            expected_is_draft=False,
        )
        assert result["verdict"] == "PASS"
        assert result["checks_passed"] == result["checks_total"]
        assert len(result["mismatches"]) == 0

    def test_no_expectations(self, mock_pr):
        result = verify_pr(pr_data=mock_pr)
        assert result["verdict"] == "PASS"
        # Check 1 (PR is OPEN) always runs when pr_data is present
        assert result["checks_passed"] == 1
        assert result["checks_total"] == 1


class TestHeadMismatch:
    """expected_head_oid ≠ PR headRefOid → BLOCK."""

    def test_head_mismatch_blocks(self, mock_pr):
        result = verify_pr(pr_data=mock_pr, expected_head_oid="ccc999")
        assert result["verdict"] == "BLOCKED"
        types = [m["type"] for m in result["mismatches"]]
        assert "head_sha_mismatch" in types

    def test_head_mismatch_severity(self, mock_pr):
        result = verify_pr(pr_data=mock_pr, expected_head_oid="wrong")
        head = [m for m in result["mismatches"] if m["type"] == "head_sha_mismatch"][0]
        assert head["severity"] == "BLOCK"

    def test_head_case_insensitive(self, mock_pr):
        result = verify_pr(pr_data=mock_pr, expected_head_oid="BBB222")
        assert result["verdict"] == "PASS"


class TestBaseMismatch:
    """expected_base_oid ≠ PR baseRefOid → BLOCK."""

    def test_base_mismatch_blocks(self, mock_pr):
        result = verify_pr(pr_data=mock_pr, expected_base_oid="ddd888")
        assert result["verdict"] == "BLOCKED"
        types = [m["type"] for m in result["mismatches"]]
        assert "base_sha_mismatch" in types


class TestFilesMismatch:
    """PR diff files ≠ expected files → BLOCK."""

    def test_extra_file_blocks(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            pr_diff_files=["a.py", "extra.py"],
            expected_files=["a.py"],
        )
        assert result["verdict"] == "BLOCKED"
        types = [m["type"] for m in result["mismatches"]]
        assert "files_mismatch" in types

    def test_missing_file_blocks(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            pr_diff_files=["a.py"],
            expected_files=["a.py", "missing.py"],
        )
        assert result["verdict"] == "BLOCKED"

    def test_files_order_independent(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            pr_diff_files=["b.py", "a.py"],
            expected_files=["a.py", "b.py"],
        )
        assert result["verdict"] == "PASS"


class TestBodyMissingText:
    """PR body missing expected text → WARNING."""

    def test_body_missing_text_warns(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            expected_body_contains=["NonexistentSection"],
        )
        assert result["verdict"] == "WARNING"
        warnings = [w["type"] for w in result["warnings"]]
        assert "body_missing_text" in warnings

    def test_body_partial_match_warns(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            expected_body_contains=["Scope", "Nonexistent"],
        )
        assert result["verdict"] == "WARNING"

    def test_body_case_insensitive(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            expected_body_contains=["scope"],
        )
        assert result["verdict"] == "PASS"


class TestDraftReadyMismatch:
    """draft/ready mismatch → WARNING (until V1.21.10)."""

    def test_draft_mismatch_warns(self, mock_pr):
        result = verify_pr(pr_data=mock_pr, expected_is_draft=True)
        assert result["verdict"] == "WARNING"
        warnings = [w["type"] for w in result["warnings"]]
        assert "draft_ready_mismatch" in warnings

    def test_ready_mismatch_warns(self, mock_pr):
        result = verify_pr(
            pr_data={**mock_pr, "isDraft": True},
            expected_is_draft=False,
        )
        assert result["verdict"] == "WARNING"

    def test_draft_match_passes(self, mock_pr):
        result = verify_pr(pr_data=mock_pr, expected_is_draft=False)
        assert result["verdict"] == "PASS"


class TestMergedNotReported:
    """PR merged but report doesn't mention → BLOCK."""

    def test_merged_not_reported_blocks(self, merged_pr):
        result = verify_pr(pr_data=merged_pr, report_claims_merged=False)
        assert result["verdict"] == "BLOCKED"
        types = [m["type"] for m in result["mismatches"]]
        assert "merged_not_reported" in types

    def test_merged_reported_passes(self, merged_pr):
        result = verify_pr(pr_data=merged_pr, report_claims_merged=True)
        assert result["verdict"] == "PASS"

    def test_merged_skipped_when_none(self, merged_pr):
        """report_claims_merged=None → merged check not performed."""
        result = verify_pr(pr_data=merged_pr)
        assert result["verdict"] == "PASS"


class TestStaleBase:
    """PR baseRefOid ≠ current main → BLOCK."""

    def test_stale_base_blocks(self, mock_pr):
        result = verify_pr(pr_data=mock_pr, current_main_oid="ccc999")
        assert result["verdict"] == "BLOCKED"
        types = [m["type"] for m in result["mismatches"]]
        assert "stale_base" in types

    def test_fresh_base_passes(self, mock_pr):
        result = verify_pr(pr_data=mock_pr, current_main_oid="aaa111")
        assert result["verdict"] == "PASS"


class TestApiFailure:
    """pr_data=None without pr_not_found → api_failure BLOCK."""

    def test_api_failure_blocks(self):
        result = verify_pr(pr_data=None)
        assert result["verdict"] == "BLOCKED"
        types = [m["type"] for m in result["mismatches"]]
        assert "api_failure" in types
        assert "pr_not_found" not in types

    def test_api_failure_with_detail(self):
        result = verify_pr(
            pr_data=None,
            pr_error="gh pr view failed (exit=1): network error",
        )
        assert result["verdict"] == "BLOCKED"
        detail = result["mismatches"][0]["detail"]
        assert "network error" in detail


class TestPrNotFound:
    """pr_data=None + pr_not_found=True → pr_not_found BLOCK (M-2 unified path)."""

    def test_pr_not_found_blocks(self):
        result = verify_pr(
            pr_data=None,
            pr_not_found=True,
            pr_error="PR_NOT_FOUND: PR #999 not found in owner/repo",
        )
        assert result["verdict"] == "BLOCKED"
        types = [m["type"] for m in result["mismatches"]]
        assert "pr_not_found" in types
        assert "api_failure" not in types

    def test_pr_not_found_detail_preserved(self):
        err = "PR_NOT_FOUND: PR #999 not found in owner/repo"
        result = verify_pr(pr_data=None, pr_not_found=True, pr_error=err)
        assert result["mismatches"][0]["detail"] == err

    def test_pr_not_found_fallback_detail(self):
        result = verify_pr(pr_data=None, pr_not_found=True)
        assert result["mismatches"][0]["detail"] == "PR not found on GitHub"

    def test_pr_not_found_pr_summary_none(self):
        result = verify_pr(pr_data=None, pr_not_found=True)
        assert result["pr_summary"] is None


class TestLocalRemoteDiffMismatch:
    """Local diff ≠ remote PR diff → BLOCK."""

    def test_diff_mismatch_blocks(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            pr_diff_files=["a.py"],
            local_diff_files=["a.py", "b.py"],
        )
        assert result["verdict"] == "BLOCKED"
        types = [m["type"] for m in result["mismatches"]]
        assert "local_remote_diff_mismatch" in types

    def test_diff_match_passes(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            pr_diff_files=["a.py"],
            local_diff_files=["a.py"],
        )
        assert result["verdict"] == "PASS"


class TestDraftPlusBlockCoexistence:
    """M-3: draft_ready_mismatch WARNING + BLOCK → final verdict BLOCKED."""

    def test_draft_warning_plus_head_block_is_blocked(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            expected_head_oid="wrong",
            expected_is_draft=True,
        )
        assert result["verdict"] == "BLOCKED"
        # Has both draft warning and head mismatch block
        warnings = [w["type"] for w in result["warnings"]]
        mismatches = [m["type"] for m in result["mismatches"]]
        assert "draft_ready_mismatch" in warnings
        assert "head_sha_mismatch" in mismatches

    def test_draft_warning_plus_base_block_is_blocked(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            expected_base_oid="wrong",
            expected_is_draft=True,
        )
        assert result["verdict"] == "BLOCKED"

    def test_draft_warning_plus_files_block_is_blocked(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            pr_diff_files=["a.py", "extra.py"],
            expected_files=["a.py"],
            expected_is_draft=True,
        )
        assert result["verdict"] == "BLOCKED"

    def test_draft_warning_alone_is_warning(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            expected_is_draft=True,
        )
        assert result["verdict"] == "WARNING"


class TestMultipleFailures:
    """Multiple simultaneous failures."""

    def test_three_blocks_counted(self, mock_pr):
        result = verify_pr(
            pr_data=mock_pr,
            expected_head_oid="wrong",
            expected_base_oid="wrong",
            pr_diff_files=["a.py"],
            expected_files=["wrong.py"],
            expected_is_draft=True,
        )
        assert result["verdict"] == "BLOCKED"
        assert len(result["mismatches"]) >= 3


class TestMismatchTypesCompleteness:
    """MISMATCH_TYPES has at least 11 entries."""

    def test_mismatch_types_count(self):
        assert len(MISMATCH_TYPES) >= 11

    def test_all_have_severity(self):
        for name, info in MISMATCH_TYPES.items():
            assert "severity" in info, f"{name} missing severity"
            assert info["severity"] in ("BLOCK", "WARNING", "PASS", "INFO"), \
                f"{name} has invalid severity: {info['severity']}"


class TestVersion:
    def test_version_bumped(self):
        assert __version__ == "1.1.0"


class TestFetchPrDataResult:
    """fetch_pr_data_result() returns structured dict."""

    def test_is_callable(self):
        assert callable(fetch_pr_data_result)

    def test_return_structure(self):
        """We can't call gh in unit tests, but verify the function exists
        and the return key structure is documented."""
        import inspect
        sig = inspect.signature(fetch_pr_data_result)
        assert "repo" in sig.parameters
        assert "pr_number" in sig.parameters
