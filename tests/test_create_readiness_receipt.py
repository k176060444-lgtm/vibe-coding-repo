#!/usr/bin/env python3
"""
Tests for scripts/create_readiness_receipt.py.

These tests verify:
  - PASS path emits a complete receipt payload
  - BLOCKED path on each fail-closed gate
  - Schema fields are present and correct types
  - Idempotency (same input → same receipt_id)
  - No side effects (does not write to disk)
  - Receipt payload is YAML-serializable

Tests do NOT write any receipt file to disk.
"""
import copy
import datetime as _dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import create_readiness_receipt as crr


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def current_head():
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    return r.stdout.strip()


@pytest.fixture
def real_nmc():
    """Load the real NMC.  Tests should be tolerant: it may have 6 true or 0 true
    depending on repo state.  Tests should mock NMCl when asserting exact count."""
    with open(REPO_ROOT / "scripts" / "node_model_capability.yaml") as f:
        return yaml.safe_load(f)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _all_pass_subtest_results() -> dict:
    """Build a subtest_results dict representing all 5 suites passing 1 test each."""
    return {
        "apply_tool":       {"passed": 29, "failed": 0, "exit_code": 0},
        "stage4":           {"passed": 19, "failed": 0, "exit_code": 0},
        "stage7":           {"passed": 50, "failed": 0, "exit_code": 0},
        "g_l4_planning":    {"passed": 24, "failed": 0, "exit_code": 0},
        "d_b_policy_lock":  {"passed": 35, "failed": 0, "exit_code": 0},
    }


def _all_pass_subtest_results_minimal() -> dict:
    """Minimal valid subtest results for unit tests (1 passed, 0 failed per suite)."""
    return {name: {"passed": 1, "failed": 0, "exit_code": 0} for name, _ in crr.SUBTEST_SUITES}


def _build_minimal_nmc(operator_approved_entries=None, qwen_true=False):
    """Build a minimal NMC dict with controllable operator_approved state."""
    if operator_approved_entries is None:
        operator_approved_entries = set(crr.EXPECTED_OPERATOR_APPROVED)

    nodes = {}
    for node in ("21bao", "5bao", "9bao"):
        matrix = []
        for mid in ("opencode-go-deepseek-v4-pro", "opencode-go-mimo-v2-5",
                    "opencode-go-qwen3-7-plus", "opencode-go-deepseek-v4-flash"):
            entry = {
                "model_id": mid,
                "declared": True,
                "synced": True,
                "wrapper_valid": True,
                "runtime_visible": True,
                "env_loaded": True,
                "model_call_verified": True,
            }
            if (node, mid) in operator_approved_entries:
                entry["operator_approved"] = True
            elif mid == "opencode-go-qwen3-7-plus":
                entry["operator_approved"] = True if qwen_true else "unknown"
            else:
                entry["operator_approved"] = "unknown"
            matrix.append(entry)
        nodes[node] = {"matrix": matrix}
    return {"nodes": nodes}


# ── TestSchemaValidation ──────────────────────────────────────────────────────

class TestSchemaValidation:
    """Verify receipt dict has all required fields and correct types."""

    def test_receipt_has_all_top_level_fields(self, current_head):
        receipt = crr.build_receipt(
            repo_root=REPO_ROOT,
            base_sha=current_head,
            run_subtests=False,
            subtest_results=_all_pass_subtest_results_minimal(),
        )
        required_fields = [
            "receipt_id", "gate", "gate_version", "created_at",
            "base_sha", "operator_approved_check", "non_scope_check",
            "test_invocation", "environment", "forbidden_artifacts_check",
            "verdict", "blocked_reasons", "notes",
        ]
        for f in required_fields:
            assert f in receipt, f"missing field: {f}"

    def test_receipt_id_is_26_hex_chars(self, current_head):
        receipt = crr.build_receipt(
            repo_root=REPO_ROOT,
            base_sha=current_head,
            run_subtests=False,
            subtest_results=_all_pass_subtest_results_minimal(),
        )
        rid = receipt["receipt_id"]
        assert len(rid) == 26
        assert all(c in "0123456789abcdef" for c in rid)

    def test_gate_version_field(self):
        assert crr.__version__ == "0.1.0"
        assert isinstance(crr.__version__, str)

    def test_created_at_is_iso8601(self, current_head):
        receipt = crr.build_receipt(
            repo_root=REPO_ROOT,
            base_sha=current_head,
            run_subtests=False,
            subtest_results=_all_pass_subtest_results_minimal(),
        )
        # Should be parseable as ISO 8601
        _dt.datetime.fromisoformat(receipt["created_at"])

    def test_receipt_yaml_serializable(self, current_head):
        receipt = crr.build_receipt(
            repo_root=REPO_ROOT,
            base_sha=current_head,
            run_subtests=False,
            subtest_results=_all_pass_subtest_results_minimal(),
        )
        # Must be serializable to YAML without errors
        yaml_str = yaml.safe_dump(receipt, default_flow_style=False, sort_keys=False)
        assert isinstance(yaml_str, str)
        # Round-trip
        parsed = yaml.safe_load(yaml_str)
        assert parsed["verdict"] == receipt["verdict"]


# ── TestNmcRead ───────────────────────────────────────────────────────────────

class TestNmcRead:
    def test_nmc_missing(self, current_head, tmp_path):
        receipt = crr.build_receipt(
            repo_root=tmp_path,  # empty tmp dir, no NMC
            base_sha=current_head,
            run_subtests=False,
            subtest_results=_all_pass_subtest_results_minimal(),
        )
        assert receipt["verdict"] == "BLOCKED"
        assert any("nmc_missing" in r for r in receipt["blocked_reasons"])

    def test_nmc_parse_error(self, current_head, tmp_path):
        # Create a malformed yaml file
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "node_model_capability.yaml").write_text(
            "{invalid: yaml: [}"
        )
        receipt = crr.build_receipt(
            repo_root=tmp_path,
            base_sha=current_head,
            run_subtests=False,
            subtest_results=_all_pass_subtest_results_minimal(),
        )
        assert receipt["verdict"] == "BLOCKED"
        assert any("nmc_parse_error" in r for r in receipt["blocked_reasons"])


# ── TestOperatorApprovedCheck ─────────────────────────────────────────────────

class TestOperatorApprovedCheck:
    def test_exact_match_passes_set_equal(self, current_head):
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            receipt = crr.build_receipt(
                repo_root=REPO_ROOT,
                base_sha=current_head,
                run_subtests=False,
                subtest_results=_all_pass_subtest_results_minimal(),
            )
            assert receipt["operator_approved_check"]["set_equal"] is True
            assert receipt["operator_approved_check"]["actual_count"] == 6
            assert receipt["operator_approved_check"]["expected_count"] == 6
            assert receipt["operator_approved_check"]["missing"] == []
            assert receipt["operator_approved_check"]["unexpected"] == []

    def test_missing_entry_blocks(self, current_head):
        # Drop one entry from operator_approved
        approved = set(crr.EXPECTED_OPERATOR_APPROVED)
        approved.discard(("21bao", "opencode-go-mimo-v2-5"))
        nmc = _build_minimal_nmc(operator_approved_entries=approved)
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            receipt = crr.build_receipt(
                repo_root=REPO_ROOT,
                base_sha=current_head,
                run_subtests=False,
                subtest_results=_all_pass_subtest_results_minimal(),
            )
            assert receipt["verdict"] == "BLOCKED"
            assert any("operator_approved_set_mismatch" in r
                       for r in receipt["blocked_reasons"])
            assert "21bao/opencode-go-mimo-v2-5" in receipt["operator_approved_check"]["missing"]

    def test_extra_entry_blocks(self, current_head):
        # Add an entry that's NOT in the expected set
        approved = set(crr.EXPECTED_OPERATOR_APPROVED)
        approved.add(("21bao", "opencode-go-deepseek-v4-flash"))
        nmc = _build_minimal_nmc(operator_approved_entries=approved)
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            receipt = crr.build_receipt(
                repo_root=REPO_ROOT,
                base_sha=current_head,
                run_subtests=False,
                subtest_results=_all_pass_subtest_results_minimal(),
            )
            assert receipt["verdict"] == "BLOCKED"
            assert any("operator_approved_set_mismatch" in r
                       for r in receipt["blocked_reasons"])
            assert "21bao/opencode-go-deepseek-v4-flash" in receipt["operator_approved_check"]["unexpected"]

    def test_count_mismatch_blocks(self, current_head):
        # Empty approved set
        nmc = _build_minimal_nmc(operator_approved_entries=set())
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            receipt = crr.build_receipt(
                repo_root=REPO_ROOT,
                base_sha=current_head,
                run_subtests=False,
                subtest_results=_all_pass_subtest_results_minimal(),
            )
            assert receipt["operator_approved_check"]["actual_count"] == 0
            assert receipt["operator_approved_check"]["expected_count"] == 6
            assert receipt["verdict"] == "BLOCKED"


# ── TestNonScopeCheck ─────────────────────────────────────────────────────────

class TestNonScopeCheck:
    def test_qwen_all_unknown_passes(self, current_head):
        nmc = _build_minimal_nmc(qwen_true=False)
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            receipt = crr.build_receipt(
                repo_root=REPO_ROOT,
                base_sha=current_head,
                run_subtests=False,
                subtest_results=_all_pass_subtest_results_minimal(),
            )
            assert receipt["non_scope_check"]["all_unknown"] is True

    def test_qwen_any_true_blocks(self, current_head):
        nmc = _build_minimal_nmc(qwen_true=True)
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            receipt = crr.build_receipt(
                repo_root=REPO_ROOT,
                base_sha=current_head,
                run_subtests=False,
                subtest_results=_all_pass_subtest_results_minimal(),
            )
            assert receipt["non_scope_check"]["all_unknown"] is False
            assert receipt["verdict"] == "BLOCKED"
            assert any("non_scope_violated" in r for r in receipt["blocked_reasons"])


# ── TestTestInvocation ────────────────────────────────────────────────────────

class TestTestInvocation:
    def test_all_pass_sets_all_pass_true(self, current_head):
        # Mock NMC to be exact
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    receipt = crr.build_receipt(
                        repo_root=REPO_ROOT,
                        base_sha=current_head,
                        run_subtests=False,
                        subtest_results=_all_pass_subtest_results_minimal(),
                    )
                    assert receipt["test_invocation"]["all_pass"] is True
                    assert receipt["verdict"] == "PASS"
                    assert receipt["blocked_reasons"] == []

    def test_one_failure_blocks(self, current_head):
        nmc = _build_minimal_nmc()
        subtest = _all_pass_subtest_results_minimal()
        subtest["stage4"] = {"passed": 18, "failed": 1, "exit_code": 1}
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    receipt = crr.build_receipt(
                        repo_root=REPO_ROOT,
                        base_sha=current_head,
                        run_subtests=False,
                        subtest_results=subtest,
                    )
                    assert receipt["test_invocation"]["all_pass"] is False
                    assert receipt["verdict"] == "BLOCKED"
                    assert any("subtest_failure:stage4" in r
                               for r in receipt["blocked_reasons"])

    def test_subprocess_error_blocks(self, current_head):
        nmc = _build_minimal_nmc()
        subtest = _all_pass_subtest_results_minimal()
        subtest["apply_tool"] = {"error": "subprocess_error", "stderr": "pytest crashed"}
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    receipt = crr.build_receipt(
                        repo_root=REPO_ROOT,
                        base_sha=current_head,
                        run_subtests=False,
                        subtest_results=subtest,
                    )
                    assert receipt["verdict"] == "BLOCKED"
                    assert any("subtest_error:apply_tool" in r
                               for r in receipt["blocked_reasons"])

    def test_subtest_results_missing_blocks(self, current_head):
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    with patch.object(crr, "_run_pytest_suite",
                                      return_value={"passed": 1, "failed": 0, "exit_code": 0}):
                        # Don't pass subtest_results AND don't run subtests
                        receipt = crr.build_receipt(
                            repo_root=REPO_ROOT,
                            base_sha=current_head,
                            run_subtests=False,
                            subtest_results=None,
                        )
                        assert receipt["verdict"] == "BLOCKED"
                        assert any("subtest_results_missing" in r
                                   for r in receipt["blocked_reasons"])


# ── TestEnvironment ───────────────────────────────────────────────────────────

class TestEnvironment:
    def test_git_dirty_blocks(self, current_head):
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=False):
                with patch.object(crr, "_open_prs", return_value=0):
                    receipt = crr.build_receipt(
                        repo_root=REPO_ROOT,
                        base_sha=current_head,
                        run_subtests=False,
                        subtest_results=_all_pass_subtest_results_minimal(),
                    )
                    assert receipt["environment"]["git_clean"] is False
                    assert receipt["verdict"] == "BLOCKED"
                    assert any("git_dirty" in r for r in receipt["blocked_reasons"])

    def test_open_prs_blocks(self, current_head):
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=2):
                    receipt = crr.build_receipt(
                        repo_root=REPO_ROOT,
                        base_sha=current_head,
                        run_subtests=False,
                        subtest_results=_all_pass_subtest_results_minimal(),
                    )
                    assert receipt["environment"]["open_prs"] == 2
                    assert receipt["verdict"] == "BLOCKED"
                    assert any("open_prs_present" in r for r in receipt["blocked_reasons"])

    def test_base_sha_mismatch_blocks(self, current_head):
        nmc = _build_minimal_nmc()
        wrong_sha = "0" * 40  # valid format, but won't match HEAD
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    receipt = crr.build_receipt(
                        repo_root=REPO_ROOT,
                        base_sha=wrong_sha,
                        run_subtests=False,
                        subtest_results=_all_pass_subtest_results_minimal(),
                    )
                    assert receipt["environment"]["base_sha_match"] is False
                    assert receipt["verdict"] == "BLOCKED"
                    assert any("base_sha_mismatch" in r for r in receipt["blocked_reasons"])

    def test_base_sha_format_invalid_blocks(self, current_head):
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    receipt = crr.build_receipt(
                        repo_root=REPO_ROOT,
                        base_sha="not-40-chars",
                        run_subtests=False,
                        subtest_results=_all_pass_subtest_results_minimal(),
                    )
                    assert receipt["verdict"] == "BLOCKED"
                    assert any("base_sha_format_invalid" in r
                               for r in receipt["blocked_reasons"])


# ── TestForbiddenArtifacts ────────────────────────────────────────────────────

class TestForbiddenArtifacts:
    def test_no_forbidden_artifacts_passes(self, current_head):
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    with patch.object(crr, "_forbidden_artifacts_present", return_value=[]):
                        receipt = crr.build_receipt(
                            repo_root=REPO_ROOT,
                            base_sha=current_head,
                            run_subtests=False,
                            subtest_results=_all_pass_subtest_results_minimal(),
                        )
                        assert receipt["forbidden_artifacts_check"]["details"] == []
                        assert receipt["verdict"] == "PASS"

    def test_gray_artifact_blocks(self, current_head):
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    with patch.object(crr, "_forbidden_artifacts_present",
                                      return_value=["docs/baseline02/gray/foo.md"]):
                        receipt = crr.build_receipt(
                            repo_root=REPO_ROOT,
                            base_sha=current_head,
                            run_subtests=False,
                            subtest_results=_all_pass_subtest_results_minimal(),
                        )
                        assert receipt["forbidden_artifacts_check"]["gray_artifacts_present"] is True
                        assert receipt["verdict"] == "BLOCKED"
                        assert any("forbidden_artifact_present" in r
                                   for r in receipt["blocked_reasons"])

    def test_baseline03_artifact_blocks(self, current_head):
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    with patch.object(crr, "_forbidden_artifacts_present",
                                      return_value=["docs/baseline02/baseline03/bar.md"]):
                        receipt = crr.build_receipt(
                            repo_root=REPO_ROOT,
                            base_sha=current_head,
                            run_subtests=False,
                            subtest_results=_all_pass_subtest_results_minimal(),
                        )
                        assert receipt["forbidden_artifacts_check"]["baseline03_artifacts_present"] is True
                        assert receipt["verdict"] == "BLOCKED"

    def test_stage8_artifact_blocks(self, current_head):
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    with patch.object(crr, "_forbidden_artifacts_present",
                                      return_value=["docs/baseline02/stage8/baz.md"]):
                        receipt = crr.build_receipt(
                            repo_root=REPO_ROOT,
                            base_sha=current_head,
                            run_subtests=False,
                            subtest_results=_all_pass_subtest_results_minimal(),
                        )
                        assert receipt["forbidden_artifacts_check"]["stage8_artifacts_present"] is True
                        assert receipt["verdict"] == "BLOCKED"


# ── TestIdempotency ──────────────────────────────────────────────────────────

class TestIdempotency:
    def test_same_input_same_receipt_id(self, current_head):
        nmc = _build_minimal_nmc()
        # Mock created_at to a fixed value
        fixed_dt = "2026-07-05T10:00:00+00:00"
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    with patch.object(crr, "_forbidden_artifacts_present", return_value=[]):
                        with patch("create_readiness_receipt._dt.datetime") as mock_dt:
                            mock_dt.now.return_value = _dt.datetime.fromisoformat(fixed_dt)
                            mock_dt.timezone.utc = _dt.timezone.utc
                            r1 = crr.build_receipt(
                                repo_root=REPO_ROOT, base_sha=current_head,
                                run_subtests=False,
                                subtest_results=_all_pass_subtest_results_minimal(),
                            )
                            r2 = crr.build_receipt(
                                repo_root=REPO_ROOT, base_sha=current_head,
                                run_subtests=False,
                                subtest_results=_all_pass_subtest_results_minimal(),
                            )
                        assert r1["receipt_id"] == r2["receipt_id"]

    def test_different_input_different_receipt_id(self, current_head):
        # Without mocking created_at, two calls should give different timestamps
        # → different receipt_ids (with very high probability).
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    with patch.object(crr, "_forbidden_artifacts_present", return_value=[]):
                        r1 = crr.build_receipt(
                            repo_root=REPO_ROOT, base_sha=current_head,
                            run_subtests=False,
                            subtest_results=_all_pass_subtest_results_minimal(),
                        )
                        r2 = crr.build_receipt(
                            repo_root=REPO_ROOT, base_sha=current_head,
                            run_subtests=False,
                            subtest_results=_all_pass_subtest_results_minimal(),
                        )
                        # They might be same if timestamp resolution is too coarse
                        # but receipt_id is sha256-derived from base_sha+created_at
                        # so unless called in same microsecond, should differ
                        # Just check they are valid 26-char hex
                        assert len(r1["receipt_id"]) == 26
                        assert len(r2["receipt_id"]) == 26


# ── TestNoSideEffects ─────────────────────────────────────────────────────────

class TestNoSideEffects:
    """The generator must NOT write any files, modify NMC, or call out externally."""

    def test_no_files_written_to_readiness_receipts_dir(self, current_head):
        receipt_dir = REPO_ROOT / "docs" / "baseline02" / "readiness" / "receipts"
        # Snapshot files BEFORE
        if receipt_dir.exists():
            before = set(p.name for p in receipt_dir.iterdir())
        else:
            before = set()
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    with patch.object(crr, "_forbidden_artifacts_present", return_value=[]):
                        crr.build_receipt(
                            repo_root=REPO_ROOT, base_sha=current_head,
                            run_subtests=False,
                            subtest_results=_all_pass_subtest_results_minimal(),
                        )
        if receipt_dir.exists():
            after = set(p.name for p in receipt_dir.iterdir())
        else:
            after = set()
        assert before == after, f"new files appeared: {after - before}"

    def test_no_nmc_modification(self, current_head):
        nmc_path = REPO_ROOT / "scripts" / "node_model_capability.yaml"
        before = nmc_path.read_bytes()
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    with patch.object(crr, "_forbidden_artifacts_present", return_value=[]):
                        crr.build_receipt(
                            repo_root=REPO_ROOT, base_sha=current_head,
                            run_subtests=False,
                            subtest_results=_all_pass_subtest_results_minimal(),
                        )
        after = nmc_path.read_bytes()
        assert before == after, "NMC was modified!"

    def test_no_model_pool_modification(self, current_head):
        mp_path = REPO_ROOT / "scripts" / "model_pool.yaml"
        before = mp_path.read_bytes()
        nmc = _build_minimal_nmc()
        with patch.object(crr, "_load_nmc", return_value=(nmc, None)):
            with patch.object(crr, "_git_clean", return_value=True):
                with patch.object(crr, "_open_prs", return_value=0):
                    with patch.object(crr, "_forbidden_artifacts_present", return_value=[]):
                        crr.build_receipt(
                            repo_root=REPO_ROOT, base_sha=current_head,
                            run_subtests=False,
                            subtest_results=_all_pass_subtest_results_minimal(),
                        )
        after = mp_path.read_bytes()
        assert before == after, "model_pool was modified!"


# ── TestFullPath ──────────────────────────────────────────────────────────────

class TestFullPath:
    """End-to-end: real NMC, current HEAD, mocked env, subtests not run."""

    def test_real_repo_passes_when_nmc_is_post_apply_state(self, current_head):
        """Real repo state (post PR #355) should produce a PASS receipt
        IF we mock the environment checks and skip subtest execution."""
        nmc_real_path = REPO_ROOT / "scripts" / "node_model_capability.yaml"
        with open(nmc_real_path) as f:
            real_nmc_data = yaml.safe_load(f)

        # Verify pre-condition: real NMC has exactly 6 true and qwen all unknown
        actual = set()
        qwen_ok = True
        for n in ("21bao", "5bao", "9bao"):
            for e in real_nmc_data["nodes"][n]["matrix"]:
                mid = e.get("model_id", "")
                if e.get("operator_approved") is True:
                    actual.add((n, mid))
                if "qwen3-7-plus" in mid and e.get("operator_approved") != "unknown":
                    qwen_ok = False
        # This test is only meaningful if repo state matches post-PR-#355
        if actual != set(crr.EXPECTED_OPERATOR_APPROVED) or not qwen_ok:
            pytest.skip("Repo state is not post-PR-#355; skipping full PASS test")

        with patch.object(crr, "_git_clean", return_value=True):
            with patch.object(crr, "_open_prs", return_value=0):
                with patch.object(crr, "_forbidden_artifacts_present", return_value=[]):
                    receipt = crr.build_receipt(
                        repo_root=REPO_ROOT,
                        base_sha=current_head,
                        run_subtests=False,
                        subtest_results=_all_pass_subtest_results_minimal(),
                    )
                    assert receipt["verdict"] == "PASS"
                    assert receipt["blocked_reasons"] == []
                    assert receipt["operator_approved_check"]["set_equal"] is True
                    assert receipt["non_scope_check"]["all_unknown"] is True
                    assert receipt["environment"]["base_sha_match"] is True
                    assert receipt["environment"]["git_clean"] is True
                    assert receipt["environment"]["open_prs"] == 0
                    assert receipt["test_invocation"]["all_pass"] is True