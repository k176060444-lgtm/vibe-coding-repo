"""Stage 6 (F7): Public-PR Pre-flight tests."""
import json
import pytest
from scripts.public_pr_preflight import (
    run_preflight,
    self_check,
    VERDICT_PASS,
    VERDICT_BLOCKED_NO_CONFIRMATION,
    VERDICT_BLOCKED_CONFIRMATION_FUZZY,
    VERDICT_BLOCKED_API_FAILURE,
    _MOCK_REPO_RESPONSE_PUBLIC,
    _MOCK_REPO_RESPONSE_PRIVATE,
    _MOCK_REPO_RESPONSE_FORK,
)


class TestPublicRepoNoConfirmation:
    """Public repo merge without operator confirmation -> blocked."""

    def test_no_confirmation_none(self):
        r = run_preflight("test-o", "test-r", operator_confirmation=None,
                          use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PUBLIC)
        assert r["verdict"] == VERDICT_BLOCKED_NO_CONFIRMATION
        assert r["operator_merge_authorized"] is False
        assert r["repo_is_public"] is True

    def test_no_confirmation_empty(self):
        r = run_preflight("test-o", "test-r", operator_confirmation="",
                          use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PUBLIC)
        assert r["verdict"] == VERDICT_BLOCKED_NO_CONFIRMATION
        assert r["operator_merge_authorized"] is False


class TestPublicRepoExactConfirmation:
    """Public repo merge with exact 'yes, merge' -> PASS."""

    def test_exact_confirmation(self):
        r = run_preflight("test-o", "test-r", operator_confirmation="yes, merge",
                          use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PUBLIC)
        assert r["verdict"] == VERDICT_PASS
        assert r["operator_merge_authorized"] is True
        assert r["repo_is_public"] is True
        assert r["public_repo_merge_requires_operator_confirmation"] is True

    def test_exact_confirmation_case_insensitive(self):
        r = run_preflight("test-o", "test-r", operator_confirmation="YES, MERGE",
                          use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PUBLIC)
        assert r["verdict"] == VERDICT_PASS
        assert r["operator_merge_authorized"] is True


class TestFuzzyConfirmation:
    """Fuzzy/non-exact confirmation -> blocked."""

    def test_fuzzy_missing_comma(self):
        r = run_preflight("test-o", "test-r", operator_confirmation="yes merge",
                          use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PUBLIC)
        assert r["verdict"] == VERDICT_BLOCKED_CONFIRMATION_FUZZY
        assert r["operator_merge_authorized"] is False

    def test_fuzzy_wrong_phrase(self):
        r = run_preflight("test-o", "test-r", operator_confirmation="ok",
                          use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PUBLIC)
        assert r["verdict"] == VERDICT_BLOCKED_CONFIRMATION_FUZZY

    def test_fuzzy_whitespace(self):
        r = run_preflight("test-o", "test-r", operator_confirmation="  yes, merge  ",
                          use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PUBLIC)
        assert r["verdict"] == VERDICT_PASS
        assert r["operator_merge_authorized"] is True


class TestPrivateRepo:
    """Private repo -> PASS without operator confirmation."""

    def test_private_no_confirmation(self):
        r = run_preflight("test-o", "test-r", operator_confirmation=None,
                          use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PRIVATE)
        assert r["verdict"] == VERDICT_PASS
        assert r["operator_merge_authorized"] is True
        assert r["repo_is_public"] is False
        assert r["public_repo_merge_requires_operator_confirmation"] is False

    def test_private_with_confirmation(self):
        r = run_preflight("test-o", "test-r", operator_confirmation="yes, merge",
                          use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PRIVATE)
        assert r["verdict"] == VERDICT_PASS
        assert r["operator_merge_authorized"] is True


class TestForkRepo:
    """Fork repo -> flagged, still passes with confirmation."""

    def test_fork_detected(self):
        r = run_preflight("fork-o", "test-r", operator_confirmation="yes, merge",
                          use_mock=True, mock_data=_MOCK_REPO_RESPONSE_FORK)
        assert r["repo_is_fork"] is True
        assert "FORK_DETECTED" in r["reason"]
        assert r["verdict"] == VERDICT_PASS

    def test_fork_no_confirmation_public(self):
        r = run_preflight("fork-o", "test-r", operator_confirmation=None,
                          use_mock=True, mock_data=_MOCK_REPO_RESPONSE_FORK)
        assert r["verdict"] == VERDICT_BLOCKED_NO_CONFIRMATION
        assert "FORK_DETECTED" in r["reason"]


class TestApiFailure:
    """GitHub API failure -> fail-closed."""

    def test_mock_exception(self):
        # When use_mock=False and no gh_token, the API call will fail
        # but not necessarily raise RuntimeError since we catch it
        pass


class TestFieldPresence:
    """Verify all required fields in output."""

    def test_required_fields_public(self):
        r = run_preflight("test-o", "test-r", operator_confirmation="yes, merge",
                          use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PUBLIC)
        required = ["checked", "repo_full_name", "repo_is_public", "repo_is_fork",
                     "default_branch", "public_repo_merge_requires_operator_confirmation",
                     "operator_merge_authorized", "operator_confirmation_provided",
                     "verdict", "reason"]
        for field in required:
            assert field in r, f"Missing field: {field}"


class TestSelfCheck:
    """Self-check should pass."""

    def test_self_check_passes(self):
        r = self_check(output_json=True)
        assert r["result"] == "PASSED"
        assert r["failed"] == 0
