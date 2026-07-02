"""
Tests for scripts/worker_attest_layer3_drift_summary.py — G-L3F fixture drift
summary renderer (PR-4I part 2).

Coverage:
- Summary JSON schema correctness
- Human summary wording
- Fixture-only scope note
- CANDIDATE_DRIFT is NOT a merge blocker (advisory)
- BLOCKED / STOP_SECRET_RISK / STOP_AND_REANCHOR are fail-closed
- DEU warnings are NEVER promoted
- DeepSeek V4 Pro is NOT special-cased
- No reuse of Layer2 E2E_* verdict names
- No forbidden imports (subprocess, os.environ, ssh, http, model_call, writes)
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scripts import worker_attest_layer3_drift as l3f
from scripts import worker_attest_layer3_drift_summary as l3fs

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "worker_attest_layer3_drift_summary.py"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Real-repo health
# ═══════════════════════════════════════════════════════════════════════════════


class TestRealRepo:
    """G-L3F summary against real repo data."""

    def test_self_check_12_12_passes(self):
        """Self-check must pass all 12 checks."""
        result = l3fs.self_check()
        assert result["status"] == "PASS", f"Failed: {result['detail']}"
        assert result["passed_count"] == result["total"]

    def test_real_verdict_is_candidate_drift(self):
        """Real repo has known gaps → G_L3F_CANDIDATE_DRIFT."""
        summary = l3fs.build_summary()
        assert summary["final_verdict"] == "G_L3F_CANDIDATE_DRIFT"
        assert summary["verdict_priority_class"] == "advisory_only"
        assert summary["is_merge_blocker"] is False

    def test_finding_counts_match(self):
        """Finding counts match base module."""
        base = l3f.run_layer3_drift()
        summary = l3fs.build_summary()
        assert summary["finding_counts"] == base["finding_counts"]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. JSON schema correctness
# ═══════════════════════════════════════════════════════════════════════════════


class TestSummarySchema:
    """Summary JSON must have correct schema and structure."""

    REQUIRED_KEYS = {
        "schema_version",
        "source",
        "generated_at",
        "scope_note",
        "base_inputs",
        "final_verdict",
        "verdict_priority_class",
        "is_merge_blocker",
        "verdict_priority_rank",
        "finding_counts",
        "finding_type_counts",
        "finding_categories",
        "leak_scan",
        "human_summary",
        "drift_report_ref",
    }

    def test_summary_has_required_keys(self):
        summary = l3fs.build_summary()
        missing = self.REQUIRED_KEYS - set(summary.keys())
        assert not missing, f"Missing keys: {missing}"

    def test_source_is_layer3_drift_summary(self):
        summary = l3fs.build_summary()
        assert summary["source"] == "worker_attest_layer3_drift_summary"

    def test_schema_version_format(self):
        summary = l3fs.build_summary()
        assert summary["schema_version"] == "1.0"

    def test_base_inputs_paths_only(self):
        """base_inputs must contain only paths, no secrets or values."""
        summary = l3fs.build_summary()
        bi = summary["base_inputs"]
        for k in ("model_pool_yaml", "node_capability_yaml", "fixture_dir", "receipt_dir"):
            assert k in bi, f"Missing key: {k}"
            assert isinstance(bi[k], str), f"{k} should be str path"
            assert bi[k].strip(), f"{k} should not be empty"

    def test_drift_report_ref_is_summary_only(self):
        """drift_report_ref must contain only verdict metadata, not raw findings."""
        summary = l3fs.build_summary()
        ref = summary["drift_report_ref"]
        # Should NOT include the full findings array (would bloat summary)
        assert "findings" not in ref
        assert "schema_version" in ref
        assert "source" in ref
        assert "final_verdict" in ref


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Verdict namespace isolation
# ═══════════════════════════════════════════════════════════════════════════════


class TestVerdictNamespace:
    """G-L3F verdict must NOT reuse Layer2 E2E_* names."""

    def test_verdict_starts_with_G_L3F(self):
        summary = l3fs.build_summary()
        assert summary["final_verdict"].startswith("G_L3F_"), (
            f"Verdict must use G_L3F_* namespace, got {summary['final_verdict']}"
        )

    def test_no_e2e_namespace_in_summary(self):
        """No E2E_* verdict should appear anywhere in the summary output."""
        summary = l3fs.build_summary()
        summary_str = json.dumps(summary)
        # Allow E2E_ in the scope_note only as a contrast statement (avoid altogether)
        # The key requirement is verdict names don't reuse E2E_*
        assert '"final_verdict": "E2E_' not in summary_str, (
            "final_verdict must NOT be E2E_*"
        )
        assert '"layer2_e2e_verdict"' not in summary_str, (
            "Summary must NOT have layer2_e2e_verdict field"
        )

    def test_verdict_priority_rank_matches(self):
        """Verdict priority rank must match the verdict."""
        summary = l3fs.build_summary()
        expected_ranks = {
            "G_L3F_STOP_SECRET_RISK": 6,
            "G_L3F_STOP_AND_REANCHOR": 5,
            "G_L3F_BLOCKED": 4,
            "G_L3F_CANDIDATE_DRIFT": 3,
            "G_L3F_PASS_WITH_WARN": 2,
            "G_L3F_PASS": 1,
        }
        assert summary["verdict_priority_rank"] == expected_ranks[summary["final_verdict"]]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. CANDIDATE_DRIFT is NOT a merge blocker
# ═══════════════════════════════════════════════════════════════════════════════


class TestCandidateDriftNotBlocker:
    """CANDIDATE_DRIFT verdict must NEVER block merge."""

    def test_real_repo_candidate_drift_is_not_blocker(self):
        summary = l3fs.build_summary()
        if summary["final_verdict"] == "G_L3F_CANDIDATE_DRIFT":
            assert summary["is_merge_blocker"] is False
            assert summary["verdict_priority_class"] == "advisory_only"

    def test_synthetic_candidate_drift_is_not_blocker(self):
        """Synthetic CANDIDATE_DRIFT summary should also be advisory."""
        synthetic = {
            "schema_version": "1.0",
            "source": "test",
            "inputs_loaded": {
                "model_pool_yaml": "/tmp/x",
                "node_capability_yaml": "/tmp/y",
                "fixture_dir": "/tmp/f",
                "receipt_dir": "/tmp/r",
            },
            "findings": [{"severity": "candidate_drift", "detail": "test"}],
            "finding_counts": {"candidate_drift": 1},
            "final_verdict": "G_L3F_CANDIDATE_DRIFT",
            "leak_scan": {"secret_leak": False, "url_leak": False, "path_leak": False, "any_leak": False},
            "scope_note": "test",
        }
        summary = l3fs.build_summary(drift_report=synthetic)
        assert summary["is_merge_blocker"] is False
        assert summary["verdict_priority_class"] == "advisory_only"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Fail-closed priority for blocked verdicts
# ═══════════════════════════════════════════════════════════════════════════════


class TestFailClosedPriority:
    """STOP_SECRET_RISK / STOP_AND_REANCHOR / BLOCKED must fail-closed."""

    @pytest.mark.parametrize("verdict", [
        "G_L3F_STOP_SECRET_RISK",
        "G_L3F_STOP_AND_REANCHOR",
        "G_L3F_BLOCKED",
    ])
    def test_fail_closed_verdict_is_blocker(self, verdict):
        synthetic = {
            "schema_version": "1.0",
            "source": "test",
            "inputs_loaded": {
                "model_pool_yaml": "/tmp/x",
                "node_capability_yaml": "/tmp/y",
                "fixture_dir": "/tmp/f",
                "receipt_dir": "/tmp/r",
            },
            "findings": [{"severity": verdict.replace("G_L3F_", "").lower(), "detail": "test"}],
            "finding_counts": {verdict.replace("G_L3F_", "").lower(): 1},
            "final_verdict": verdict,
            "leak_scan": {"secret_leak": False, "url_leak": False, "path_leak": False, "any_leak": False},
            "scope_note": "test",
        }
        summary = l3fs.build_summary(drift_report=synthetic)
        assert summary["is_merge_blocker"] is True, (
            f"{verdict} must be a merge blocker"
        )
        assert summary["verdict_priority_class"] == "fail_closed"

    def test_priority_ordering_secret_highest(self):
        """STOP_SECRET_RISK must outrank STOP_AND_REANCHOR."""
        rank = l3fs._VERDICT_PRIORITY
        assert rank["G_L3F_STOP_SECRET_RISK"] > rank["G_L3F_STOP_AND_REANCHOR"]
        assert rank["G_L3F_STOP_AND_REANCHOR"] > rank["G_L3F_BLOCKED"]
        assert rank["G_L3F_BLOCKED"] > rank["G_L3F_CANDIDATE_DRIFT"]
        assert rank["G_L3F_CANDIDATE_DRIFT"] > rank["G_L3F_PASS_WITH_WARN"]
        assert rank["G_L3F_PASS_WITH_WARN"] > rank["G_L3F_PASS"]


# ═══════════════════════════════════════════════════════════════════════════════
# 6. DEU never promoted
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeuNeverPromoted:
    """DEU findings must not appear as blocked or candidate_drift."""

    def test_deu_findings_never_blocked(self):
        """No DEU findings should appear in blocked category."""
        summary = l3fs.build_summary()
        for f in summary.get("finding_categories", {}).get("blocked", []):
            assert f.get("lifecycle_class") != "deu", (
                f"DEU finding incorrectly classified as blocked: {f}"
            )

    def test_deu_findings_never_candidate_drift(self):
        """No DEU findings should appear in candidate_drift category."""
        summary = l3fs.build_summary()
        for f in summary.get("finding_categories", {}).get("candidate_drift", []):
            assert f.get("lifecycle_class") != "deu", (
                f"DEU finding incorrectly classified as candidate_drift: {f}"
            )

    def test_deu_only_in_warn(self):
        """DEU findings should only appear in warn category."""
        summary = l3fs.build_summary()
        for cat, items in summary.get("finding_categories", {}).items():
            for f in items:
                if f.get("lifecycle_class") == "deu":
                    assert cat == "warn", (
                        f"DEU finding in wrong category '{cat}': {f}"
                    )


# ═══════════════════════════════════════════════════════════════════════════════
# 7. DeepSeek V4 Pro not special-cased
# ═══════════════════════════════════════════════════════════════════════════════


class TestV4ProNotSpecial:
    """DeepSeek V4 Pro must follow same active-model rules."""

    def test_v4_pro_follows_active_rules(self):
        """V4 Pro is active and subject to same checks as other active models."""
        summary = l3fs.build_summary()
        ds4pro_findings = []
        for cat_items in summary.get("finding_categories", {}).values():
            for f in cat_items:
                if f.get("model_id") == "opencode-go-deepseek-v4-pro":
                    ds4pro_findings.append(f)

        # V4 Pro has known gap — should appear as candidate_drift
        assert len(ds4pro_findings) > 0, (
            "DeepSeek V4 Pro should appear with active-model candidate drift"
        )

    def test_v4_pro_treated_like_other_active(self):
        """V4 Pro classification logic is identical to other active models."""
        # Build synthetic finding for V4 Pro and another active model
        v4_pro_finding = {
            "node": "21bao",
            "model_id": "opencode-go-deepseek-v4-pro",
            "lifecycle_class": "active",
            "severity": "candidate_drift",
            "drift_type": "runtime_visible_not_ok",
            "detail": "Active model 'opencode-go-deepseek-v4-pro' on 21bao",
        }
        other_active_finding = {
            "node": "21bao",
            "model_id": "opencode-go-glm-5-1",
            "lifecycle_class": "active",
            "severity": "candidate_drift",
            "drift_type": "runtime_visible_not_ok",
            "detail": "Active model 'opencode-go-glm-5-1' on 21bao",
        }
        v4_class = l3fs._classify_finding(v4_pro_finding)
        other_class = l3fs._classify_finding(other_active_finding)
        assert v4_class == other_class == "candidate_drift"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Human summary wording
# ═══════════════════════════════════════════════════════════════════════════════


class TestHumanSummaryWording:
    """Human summary must include verdict, scope note, and key warnings."""

    def test_human_summary_has_verdict(self):
        summary = l3fs.build_summary()
        assert summary["final_verdict"] in summary["human_summary"]

    def test_human_summary_has_scope_marker(self):
        summary = l3fs.build_summary()
        assert "FIXTURE" in summary["human_summary"].upper()

    def test_human_summary_mentions_candidate_drift_meaning(self):
        """Human summary must clarify CANDIDATE_DRIFT is NOT live runtime BLOCK."""
        summary = l3fs.build_summary()
        human_lower = summary["human_summary"].lower()
        # Should mention candidate drift in some form
        assert "candidate" in human_lower or "data gap" in human_lower
        # Should clarify it's not live runtime
        assert "not" in human_lower and ("live" in human_lower or "fixture" in human_lower)

    def test_build_text_summary_renders(self):
        summary = l3fs.build_summary()
        text = l3fs.build_text_summary(summary)
        assert isinstance(text, str)
        assert summary["final_verdict"] in text
        assert "=" * 70 in text  # banner line

    def test_text_summary_deterministic(self):
        """Text summary must be deterministic across calls."""
        summary = l3fs.build_summary()
        text1 = l3fs.build_text_summary(summary)
        text2 = l3fs.build_text_summary(summary)
        assert text1 == text2


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Fixture-only scope note
# ═══════════════════════════════════════════════════════════════════════════════


class TestFixtureOnlyScope:
    """Summary must NOT claim live runtime clean."""

    def test_scope_note_fixture_only(self):
        summary = l3fs.build_summary()
        note = summary["scope_note"].lower()
        assert "fixture" in note
        assert "not live" in note or "not claim" in note or "fixture evidence" in note

    def test_no_live_runtime_claim_in_summary(self):
        summary = l3fs.build_summary()
        # Check that the summary explicitly NEGATES live runtime claims.
        # The scope_note MUST contain "not live runtime" or "does NOT claim live runtime"
        note = summary["scope_note"].lower()
        assert "not live runtime" in note or "does not claim live runtime" in note, (
            f"scope_note must negate live-runtime claim: {note}"
        )
        # The phrase "live runtime clean" must appear ONLY in negated form
        # (e.g., "does NOT claim live runtime clean"). Check context.
        import re
        for m in re.finditer(r"live runtime \w+", json.dumps(summary).lower()):
            # Look back 50 chars for negation words
            start = max(0, m.start() - 50)
            context = json.dumps(summary).lower()[start:m.start()]
            if "not" in context or "no " in context:
                continue  # OK — negated
            pytest.fail(
                f"Possible affirmative live-runtime claim: {m.group()}"
            )

    def test_missing_fixture_described_correctly(self):
        """Missing fixture evidence must use 'fixture evidence missing' wording."""
        summary = l3fs.build_summary()
        for cat_items in summary.get("finding_categories", {}).values():
            for f in cat_items:
                if "missing" in f.get("drift_type", "").lower():
                    msg = f.get("short_message", "").lower()
                    assert "fixture" in msg or "evidence" in msg, (
                        f"Missing fixture should use correct wording: {msg}"
                    )


# ═══════════════════════════════════════════════════════════════════════════════
# 10. No forbidden imports / writes
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoForbiddenOperations:
    """Summary module must not contain forbidden operations."""

    def test_no_subprocess_import(self):
        with open(SCRIPT) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name == "subprocess" or alias.name.startswith("subprocess."):
                        pytest.fail(f"Found forbidden import: subprocess")

    def test_no_os_environ_access(self):
        """No os.environ or os.getenv access."""
        with open(SCRIPT) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr == "environ":
                    pytest.fail("Found os.environ access")
                if node.attr == "getenv":
                    pytest.fail("Found os.getenv access")

    def test_no_ssh_or_scp_in_source(self):
        """Module source must not contain SSH/SCP command strings."""
        with open(SCRIPT) as f:
            source = f.read()
        forbidden = ['"ssh ', "'ssh ", '"scp ', "'scp ", "paramiko", "pexpect"]
        for pat in forbidden:
            assert pat not in source, f"Found forbidden pattern '{pat}'"

    def test_no_http_or_requests(self):
        with open(SCRIPT) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name in ("urllib", "requests", "http"):
                        pytest.fail(f"Found network import: {alias.name}")

    def test_no_model_call_imports(self):
        """Module must not import model-calling code."""
        with open(SCRIPT) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if any(x in alias.name for x in [
                        "opencode_model", "vibe_model_routing",
                        "model_pool_manager", "opencode", "model_alias_registry"
                    ]):
                        pytest.fail(f"Found model-related import: {alias.name}")

    def test_no_write_to_yaml_files(self):
        """Summary must not write to model_pool.yaml or node_model_capability.yaml."""
        with open(SCRIPT) as f:
            source = f.read()
        # Check that file open calls are not in write mode for these files
        forbidden_targets = ["model_pool.yaml", "node_model_capability.yaml"]
        for target in forbidden_targets:
            # If target appears, check context — should only be in comments
            if target in source:
                # Look for lines with 'open' + 'w' + target
                for line in source.split("\n"):
                    if target in line and ("open" in line and '"w"' in line):
                        pytest.fail(f"Found write to {target}: {line}")

    def test_no_unlink_or_rename(self):
        """Module must not delete or rename files."""
        with open(SCRIPT) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr in ("unlink", "remove", "rmtree"):
                    pytest.fail(f"Found destructive call: .{node.attr}")


# ═══════════════════════════════════════════════════════════════════════════════
# 11. No secret leak in output
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoSecretLeak:
    """Summary output must not contain real secrets, URLs, or paths."""

    def test_summary_no_leak(self):
        summary = l3fs.build_summary()
        leak = summary["leak_scan"]
        assert leak["any_leak"] is False, f"Found leak: {leak}"

    def test_self_check_no_leak(self):
        result = l3fs.self_check()
        assert result["status"] == "PASS"
        # No leak in self-check output either
        result_str = json.dumps(result)
        assert "sk-abc" not in result_str
        assert "AKIA" not in result_str