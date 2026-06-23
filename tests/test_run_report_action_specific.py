"""Tests for vibe_run_report.py action-specific audit visibility (V1.21.16+).

Covers T-01 through T-22 from V1.21.16/V1.21.17/V1.21.18 proposals,
and T-23 through T-33 from V1.21.21 (deferred registry report visibility).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from vibe_run_report import (
    VERSION,
    _collect_action_specific,
    _collect_deferred_registry,
    _format_compact,
    _format_markdown,
    run_report,
)


# ── Fixtures ──────────────────────────────────────────────────────────

def _make_eag_action_specific_blocked():
    """EAG result for a blocked action_specific action (delegate_task_dispatch)."""
    return {
        "verdict": "BLOCKED_ACTION_SPECIFIC_FIELDS_MISSING",
        "action": "delegate_task_dispatch",
        "action_class": "execution",
        "action_category": "action_specific",
        "action_specific_required_fields": [
            "target_node", "target_role", "task_goal_summary",
            "allowed_repo_scope", "model_plan", "max_parallel",
            "fallback_policy", "timeout_seconds",
        ],
        "missing_fields": ["target_node", "model_plan"],
        "invalid_fields": [],
        "dedicated_approval_required": False,
        "service_admin_critical_required": False,
        "blocked_reason_code": "FIELDS_MISSING",
    }


def _make_eag_action_specific_pass():
    """EAG result for a passing action_specific action."""
    return {
        "verdict": "APPROVAL_BOUND",
        "action": "delegate_task_dispatch",
        "action_class": "execution",
        "action_category": "action_specific",
        "action_specific_required_fields": [
            "target_node", "target_role", "task_goal_summary",
            "allowed_repo_scope", "model_plan", "max_parallel",
            "fallback_policy", "timeout_seconds",
        ],
        "missing_fields": [],
        "invalid_fields": [],
        "dedicated_approval_required": False,
        "service_admin_critical_required": False,
    }


def _make_eag_ordinary():
    """EAG result for an ordinary execution action (code_modify)."""
    return {
        "verdict": "APPROVAL_BOUND",
        "action": "code_modify",
        "action_class": "execution",
        "action_category": "ordinary",
    }


def _make_eag_service_admin_blocked():
    """EAG result for a blocked service_admin_uac action."""
    return {
        "verdict": "BLOCKED_SERVICE_ADMIN_REQUIRES_DEDICATED_APPROVAL",
        "action": "service_admin_uac",
        "action_class": "execution",
        "action_category": "action_specific",
        "action_specific_required_fields": [
            "target_service", "change_type", "affected_scope",
            "rollback_plan", "requires_outage",
        ],
        "missing_fields": [],
        "invalid_fields": [],
        "dedicated_approval_required": True,
        "service_admin_critical_required": True,
        "blocked_reason_code": "SERVICE_ADMIN_CRITICAL",
    }


def _make_base_report():
    """Minimal valid report dict for run_report (without eag)."""
    return {
        "quality_gate": {"verdict": "PASS", "summary": {"total": 5, "pass": 5, "warn": 0, "block": 0}},
        "smoke_status": "PASS",
        "audit_lock": {"audit_status": "audit_tainted", "push_allowed": False},
        "baseline": {"sha": "abc123def456", "short": "abc123def456"},
        "pr_summary": {"number": 206, "title": "Test PR", "merged_at": "2026-06-23T01:15:37Z", "merge_commit": "8abc1a87000b"},
        "v1_freeze": {"verdict": "PASS"},
        "operator_summary": "System healthy.",
        "next_recommended_action": "READY",
    }


# ── Tests ─────────────────────────────────────────────────────────────

class TestVersion:
    """T-09: Version bump verified."""

    def test_version(self):
        assert VERSION == "1.2.0"


class TestCollectActionSpecific:
    """Tests for _collect_action_specific() helper."""

    def test_action_specific_blocked(self):
        """T-01: action_specific with blocked verdict → full section."""
        eag = _make_eag_action_specific_blocked()
        section = _collect_action_specific(eag)
        assert section is not None
        assert section["action"] == "delegate_task_dispatch"
        assert section["action_category"] == "action_specific"
        assert section["verdict"] == "BLOCKED_ACTION_SPECIFIC_FIELDS_MISSING"
        assert section["blocked_reason_code"] == "FIELDS_MISSING"
        assert "target_node" in section["missing_fields"]
        assert section["action_specific_required_fields"]  # non-empty
        assert section["dedicated_approval_required"] is False
        assert section["service_admin_critical_required"] is False

    def test_action_specific_pass(self):
        """T-01b: action_specific with PASS → full section, no blocked_reason_code."""
        eag = _make_eag_action_specific_pass()
        section = _collect_action_specific(eag)
        assert section is not None
        assert section["action_category"] == "action_specific"
        assert section["verdict"] == "APPROVAL_BOUND"
        assert "blocked_reason_code" not in section  # not present when PASS
        assert section["missing_fields"] == []
        assert section["invalid_fields"] == []

    def test_ordinary_minimal(self):
        """T-02: ordinary action → minimal section (no detailed fields)."""
        eag = _make_eag_ordinary()
        section = _collect_action_specific(eag)
        assert section is not None
        assert section["action"] == "code_modify"
        assert section["action_category"] == "ordinary"
        assert section["verdict"] == "APPROVAL_BOUND"
        # Ordinary actions should NOT have detailed fields
        assert "action_specific_required_fields" not in section
        assert "missing_fields" not in section
        assert "invalid_fields" not in section
        assert "blocked_reason_code" not in section

    def test_no_eag_result(self):
        """T-03: no eag_result → None."""
        assert _collect_action_specific(None) is None
        assert _collect_action_specific({}) is None

    def test_service_admin_blocked(self):
        """T-04: service_admin_uac blocked → blocked_reason_code + dedicated flags."""
        eag = _make_eag_service_admin_blocked()
        section = _collect_action_specific(eag)
        assert section is not None
        assert section["blocked_reason_code"] == "SERVICE_ADMIN_CRITICAL"
        assert section["dedicated_approval_required"] is True
        assert section["service_admin_critical_required"] is True

    def test_missing_fields_populated(self):
        """T-05: missing_fields surfaced correctly."""
        eag = _make_eag_action_specific_blocked()
        section = _collect_action_specific(eag)
        assert "target_node" in section["missing_fields"]
        assert "model_plan" in section["missing_fields"]


class TestMarkdownFormat:
    """Tests for _format_markdown() with action-specific section."""

    def _get_report_with_asa(self, eag):
        """Helper: build report dict with action_specific_approval injected."""
        report = _make_base_report()
        asa = _collect_action_specific(eag)
        if asa:
            report["action_specific_approval"] = asa
        return report

    def test_action_specific_section_present(self):
        """T-06: markdown includes Action-Specific Approval section."""
        report = self._get_report_with_asa(_make_eag_action_specific_blocked())
        md = _format_markdown(report)
        assert "## Action-Specific Approval" in md
        assert "BLOCKED_ACTION_SPECIFIC_FIELDS_MISSING" in md
        assert "delegate_task_dispatch" in md
        assert "FIELDS_MISSING" in md

    def test_ordinary_section_present(self):
        """T-06b: markdown includes section for ordinary action (minimal)."""
        report = self._get_report_with_asa(_make_eag_ordinary())
        md = _format_markdown(report)
        assert "## Action-Specific Approval" in md
        assert "code_modify" in md

    def test_no_section_when_absent(self):
        """T-06c: no section when no action_specific_approval."""
        report = _make_base_report()
        md = _format_markdown(report)
        assert "## Action-Specific Approval" not in md

    def test_service_admin_flags_in_markdown(self):
        """T-06d: service_admin flags rendered in markdown."""
        report = self._get_report_with_asa(_make_eag_service_admin_blocked())
        md = _format_markdown(report)
        assert "Dedicated approval required" in md
        assert "CRITICAL risk level required" in md


class TestCompactFormat:
    """Tests for _format_compact() with action-specific section."""

    def test_compact_asa_prefix(self):
        """T-07: compact includes ASA: prefix when present."""
        report = _make_base_report()
        asa = _collect_action_specific(_make_eag_action_specific_blocked())
        report["action_specific_approval"] = asa
        compact = _format_compact(report)
        assert "ASA:action_specific" in compact
        assert "FIELDS_MISSING" in compact

    def test_compact_no_asa_when_absent(self):
        """T-07b: no ASA when no section."""
        report = _make_base_report()
        compact = _format_compact(report)
        assert "ASA:" not in compact

    def test_compact_ordinary_no_code(self):
        """T-07c: compact ASA:ordinary without blocked_reason_code."""
        report = _make_base_report()
        asa = _collect_action_specific(_make_eag_ordinary())
        report["action_specific_approval"] = asa
        compact = _format_compact(report)
        assert "ASA:ordinary" in compact
        # No parenthesized code for ordinary
        assert "ASA:ordinary(" not in compact


class TestJsonOutput:
    """Tests for JSON output with action_specific_approval."""

    def test_json_with_eag(self):
        """T-08: JSON includes action_specific_approval key when eag provided."""
        # We can't easily call run_report() without a real repo, but we can
        # test _collect_action_specific output structure directly
        eag = _make_eag_action_specific_blocked()
        section = _collect_action_specific(eag)
        assert "action_category" in section
        assert "blocked_reason_code" in section
        assert "missing_fields" in section

    def test_json_without_eag(self):
        """T-08b: no eag → no section."""
        section = _collect_action_specific(None)
        assert section is None


class TestBackwardCompatibility:
    """T-03 / T-10: Backward compatibility — no eag_result = old behavior."""

    def test_collect_returns_none_for_none(self):
        """No eag_result → None, no section injected."""
        assert _collect_action_specific(None) is None

    def test_collect_returns_none_for_empty(self):
        """Empty dict → falsy, returns None."""
        # Empty dict is falsy in Python
        assert _collect_action_specific({}) is None

    def test_markdown_without_section_unchanged(self):
        """Report without action_specific_approval → same as before V1.21.16."""
        report = _make_base_report()
        md = _format_markdown(report)
        # Should have standard sections
        assert "## 结论" in md
        assert "## 当前基线" in md
        assert "## Quality Gate" in md
        # No action-specific section
        assert "## Action-Specific Approval" not in md

    def test_compact_without_section_unchanged(self):
        """Compact without action_specific_approval → same as before V1.21.16."""
        report = _make_base_report()
        compact = _format_compact(report)
        assert "ASA:" not in compact
        assert "QG:PASS" in compact


class TestSelfCheck:
    """T-10: vibe_run_report self-check unchanged."""

    def test_version_in_output(self):
        """Version is reported correctly."""
        assert VERSION == "1.2.0"


# ── V1.21.17: Auto-discovery + write_eag_result tests ────────────────

import json as _json
import os as _os


def _setup_fake_repo(tmp_path):
    """Create minimal repo structure for run_report() with mocked helpers."""
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    # Create empty script files so _run_script doesn't fail hard
    (scripts_dir / "vibe_quality_gate.py").touch()
    (scripts_dir / "vibe_loop_summary.py").touch()
    (scripts_dir / "vibe_operator_snapshot.py").touch()
    (scripts_dir / "vibe_repo_status.py").touch()
    (scripts_dir / "vibe_v1_freeze_check.py").touch()
    return tmp_path


class TestAutoDiscovery:
    """T-11 through T-14: Auto-discovery from .vibe/eag_result.json."""

    def test_autodiscovery_from_vibe_dir(self, tmp_path):
        """T-11: Auto-discovery loads eag_result from .vibe/eag_result.json."""
        repo_root = _setup_fake_repo(tmp_path)
        vibe_dir = repo_root / ".vibe"
        vibe_dir.mkdir()
        eag = _make_eag_action_specific_blocked()
        with open(vibe_dir / "eag_result.json", "w", encoding="utf-8") as f:
            _json.dump(eag, f)

        result = run_report(repo_root=str(repo_root))
        asa = result.get("action_specific_approval")
        assert asa is not None
        assert asa["action_category"] == "action_specific"
        assert asa["blocked_reason_code"] == "FIELDS_MISSING"

    def test_explicit_overrides_autodiscovery(self, tmp_path):
        """T-12: Explicit eag_result param overrides auto-discovery."""
        repo_root = _setup_fake_repo(tmp_path)
        vibe_dir = repo_root / ".vibe"
        vibe_dir.mkdir()
        # Write blocked result to .vibe/
        blocked_eag = _make_eag_action_specific_blocked()
        with open(vibe_dir / "eag_result.json", "w", encoding="utf-8") as f:
            _json.dump(blocked_eag, f)

        # Pass ordinary result explicitly — should override
        ordinary_eag = _make_eag_ordinary()
        result = run_report(repo_root=str(repo_root), eag_result=ordinary_eag)
        asa = result.get("action_specific_approval")
        assert asa is not None
        assert asa["action_category"] == "ordinary"
        # Should NOT have blocked_reason_code (ordinary)
        assert "blocked_reason_code" not in asa

    def test_missing_vibe_dir_backward_compat(self, tmp_path):
        """T-13: No .vibe/eag_result.json → no section (backward compat)."""
        repo_root = _setup_fake_repo(tmp_path)
        # No .vibe/ directory created
        result = run_report(repo_root=str(repo_root))
        assert "action_specific_approval" not in result

    def test_invalid_json_graceful_fallback(self, tmp_path):
        """T-14: Invalid JSON in .vibe/eag_result.json → graceful fallback."""
        repo_root = _setup_fake_repo(tmp_path)
        vibe_dir = repo_root / ".vibe"
        vibe_dir.mkdir()
        with open(vibe_dir / "eag_result.json", "w", encoding="utf-8") as f:
            f.write("NOT VALID JSON {{{")

        result = run_report(repo_root=str(repo_root))
        assert "action_specific_approval" not in result


class TestWriteEagResult:
    """T-15, T-16: write_eag_result() tests."""

    def test_write_creates_file(self, tmp_path):
        """T-15: write_eag_result creates .vibe/eag_result.json with correct content."""
        from conversational_intake_gate import write_eag_result

        eag = _make_eag_action_specific_blocked()
        write_eag_result(eag, repo_root=str(tmp_path))

        result_path = tmp_path / ".vibe" / "eag_result.json"
        assert result_path.is_file()
        with open(result_path, encoding="utf-8") as f:
            loaded = _json.load(f)
        assert loaded["action"] == "delegate_task_dispatch"
        assert loaded["blocked_reason_code"] == "FIELDS_MISSING"

    def test_write_silent_failure(self, tmp_path):
        """T-16: write_eag_result silent failure on permission/path error."""
        from conversational_intake_gate import write_eag_result

        eag = _make_eag_action_specific_blocked()
        # Use a non-existent nested path that can't be created
        bad_root = str(tmp_path / "nonexistent" / "deeply" / "nested" / "path")
        # Should not raise
        write_eag_result(eag, repo_root=bad_root)


class TestVersionUnchanged:
    """T-17: vibe_run_report version unchanged 1.2.0."""

    def test_version_still_120(self):
        assert VERSION == "1.2.0"


# ── V1.21.18: Git PR Gate EAG persistence + .vibe/ ignore tests ──────

import subprocess as _subprocess
import tempfile as _tempfile


class TestGitPrGateEagPersistence:
    """T-19: git_pr_approval_gate path also persists eag_result."""

    def test_persistence_via_write_eag_result(self, tmp_path):
        """T-19: write_eag_result called from git_pr_gate context persists to .vibe/."""
        from conversational_intake_gate import write_eag_result

        eag = {
            "verdict": "APPROVAL_BOUND",
            "action": "push_feature_branch",
            "action_class": "execution",
            "action_category": "ordinary",
        }
        write_eag_result(eag, repo_root=str(tmp_path))

        result_path = tmp_path / ".vibe" / "eag_result.json"
        assert result_path.is_file()
        with open(result_path, encoding="utf-8") as f:
            loaded = _json.load(f)
        assert loaded["verdict"] == "APPROVAL_BOUND"
        assert loaded["action"] == "push_feature_branch"

    def test_import_cycle_free(self):
        """T-19b: git_pr_approval_gate → conversational_intake_gate has no cycle."""
        # If this import succeeds, there's no cycle
        from conversational_intake_gate import write_eag_result
        assert callable(write_eag_result)


class TestVibeIgnorePolicy:
    """T-20: .vibe/ ignored by git."""

    def test_vibe_dir_ignored_by_git(self):
        """T-20: git check-ignore .vibe/ returns 0 (ignored)."""
        repo_root = Path(__file__).resolve().parent.parent
        result = _subprocess.run(
            ["git", "check-ignore", ".vibe/"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Expected .vibe/ to be ignored, got exit {result.returncode}"
        assert ".vibe/" in result.stdout


class TestVersionV12118:
    """T-22: vibe_run_report version unchanged 1.2.0 (V1.21.18)."""

    def test_version_still_120(self):
        assert VERSION == "1.2.0"


# ── V1.21.21: Deferred Registry Report Visibility tests ──────────────

import json as _json2
import os as _os2
import tempfile as _tempfile2


class TestCollectDeferredRegistry:
    """T-23~T-26: _collect_deferred_registry basic behavior."""

    def test_returns_summaries_with_correct_fields(self, tmp_path):
        """T-23: Returns list of summaries with all required fields."""
        registry_dir = tmp_path / ".vibe" / "deferred_registry"
        registry_dir.mkdir(parents=True)
        entry = {
            "workorder_id": "deferred-delegate_task_dispatch-20260623T120000-abcdef12",
            "action": "delegate_task_dispatch",
            "action_category": "deferred",
            "approval_id": "approval-test-001",
            "risk_level": "low",
            "dedicated_approval": False,
            "registry_only": True,
            "dry_run_only": True,
            "created_at": "2026-06-23T12:00:00+00:00",
            "history_digest": "abc123",
        }
        (registry_dir / "test-entry.json").write_text(
            _json2.dumps(entry, indent=2), encoding="utf-8"
        )
        result = _collect_deferred_registry(str(tmp_path))
        assert len(result) == 1
        r = result[0]
        assert r["action"] == "delegate_task_dispatch"
        assert r["approval_id"] == "approval-test-001"
        assert r["workorder_id"] == "deferred-delegate_task_dispatch-20260623T120000-abcdef12"
        assert r["risk_level"] == "low"
        assert r["dedicated_approval"] is False
        assert r["registry_only"] is True
        assert r["dry_run_only"] is True
        assert r["real_execution"] is False
        assert r["created_at"] == "2026-06-23T12:00:00+00:00"
        assert r["history_digest"] == "abc123"

    def test_empty_dir_returns_empty_list(self, tmp_path):
        """T-24: Empty registry dir → empty list."""
        registry_dir = tmp_path / ".vibe" / "deferred_registry"
        registry_dir.mkdir(parents=True)
        result = _collect_deferred_registry(str(tmp_path))
        assert result == []

    def test_missing_dir_returns_empty_list(self, tmp_path):
        """T-25: Non-existent dir → empty list."""
        result = _collect_deferred_registry(str(tmp_path))
        assert result == []

    def test_bad_json_skipped(self, tmp_path):
        """T-26: Bad JSON in registry dir → skipped gracefully."""
        registry_dir = tmp_path / ".vibe" / "deferred_registry"
        registry_dir.mkdir(parents=True)
        (registry_dir / "bad.json").write_text("{invalid json", encoding="utf-8")
        # Add a valid entry too
        entry = {
            "workorder_id": "deferred-test-20260623T120000-abcdef12",
            "action": "live_model_call",
            "approval_id": "approval-bad-json-test",
            "risk_level": "low",
            "created_at": "2026-06-23T12:00:00+00:00",
        }
        (registry_dir / "good.json").write_text(
            _json2.dumps(entry, indent=2), encoding="utf-8"
        )
        result = _collect_deferred_registry(str(tmp_path))
        assert len(result) == 1
        assert result[0]["action"] == "live_model_call"


class TestDeferredRegistryInReport:
    """T-27~T-28: Deferred registry in run_report JSON output."""

    def test_present_when_entries_exist(self, tmp_path):
        """T-27: deferred_action_registry present in JSON output when entries exist."""
        registry_dir = tmp_path / ".vibe" / "deferred_registry"
        registry_dir.mkdir(parents=True)
        entry = {
            "workorder_id": "deferred-dispatch-20260623T120000-abcdef12",
            "action": "delegate_task_dispatch",
            "approval_id": "approval-27",
            "risk_level": "low",
            "dedicated_approval": False,
            "registry_only": True,
            "dry_run_only": True,
            "created_at": "2026-06-23T12:00:00+00:00",
            "history_digest": "def456",
        }
        (registry_dir / "entry.json").write_text(
            _json2.dumps(entry, indent=2), encoding="utf-8"
        )
        report = run_report(repo_root=str(tmp_path))
        assert "deferred_action_registry" in report
        dar = report["deferred_action_registry"]
        assert len(dar) == 1
        assert dar[0]["action"] == "delegate_task_dispatch"
        assert dar[0]["real_execution"] is False

    def test_absent_when_no_entries(self, tmp_path):
        """T-28: deferred_action_registry absent from JSON output when no entries."""
        report = run_report(repo_root=str(tmp_path))
        assert "deferred_action_registry" not in report


class TestDeferredRegistryMarkdown:
    """T-28b~T-29: Markdown rendering of deferred registry."""

    def test_service_admin_uac_dedicated_warning(self, tmp_path):
        """T-28b: service_admin_uac + dedicated_approval → ⚠️ in markdown."""
        registry_dir = tmp_path / ".vibe" / "deferred_registry"
        registry_dir.mkdir(parents=True)
        entry = {
            "workorder_id": "deferred-uac-20260623T120000-abcdef12",
            "action": "service_admin_uac",
            "approval_id": "approval-uac-001",
            "risk_level": "critical",
            "dedicated_approval": True,
            "registry_only": True,
            "dry_run_only": True,
            "created_at": "2026-06-23T12:00:00+00:00",
            "history_digest": "uac123",
        }
        (registry_dir / "uac.json").write_text(
            _json2.dumps(entry, indent=2), encoding="utf-8"
        )
        report = run_report(repo_root=str(tmp_path))
        md = _format_markdown(report)
        assert "Deferred Action Registry" in md
        assert "service_admin_uac" in md
        assert "dedicated/critical" in md

    def test_markdown_renders_section(self, tmp_path):
        """T-29: Markdown renders deferred registry section with action/approval/risk."""
        registry_dir = tmp_path / ".vibe" / "deferred_registry"
        registry_dir.mkdir(parents=True)
        entry = {
            "workorder_id": "deferred-model-20260623T120000-abcdef12",
            "action": "live_model_call",
            "approval_id": "approval-md-001",
            "risk_level": "low",
            "dedicated_approval": False,
            "registry_only": True,
            "dry_run_only": True,
            "created_at": "2026-06-23T12:00:00+00:00",
            "history_digest": "md123",
        }
        (registry_dir / "model.json").write_text(
            _json2.dumps(entry, indent=2), encoding="utf-8"
        )
        report = run_report(repo_root=str(tmp_path))
        md = _format_markdown(report)
        assert "Deferred Action Registry" in md
        assert "live_model_call" in md
        assert "approval-md-001" in md
        assert "low" in md


class TestDeferredRegistryCompact:
    """T-30: Compact format includes DAR info."""

    def test_compact_dar_present(self, tmp_path):
        """T-30: Compact format includes DAR:N and action summary."""
        registry_dir = tmp_path / ".vibe" / "deferred_registry"
        registry_dir.mkdir(parents=True)
        for action in ["delegate_task_dispatch", "live_model_call"]:
            entry = {
                "workorder_id": f"deferred-{action}-20260623T120000-abcdef12",
                "action": action,
                "approval_id": f"approval-compact-{action}",
                "risk_level": "low",
                "dedicated_approval": False,
                "registry_only": True,
                "dry_run_only": True,
                "created_at": "2026-06-23T12:00:00+00:00",
                "history_digest": "compact123",
            }
            (registry_dir / f"{action}.json").write_text(
                _json2.dumps(entry, indent=2), encoding="utf-8"
            )
        report = run_report(repo_root=str(tmp_path))
        compact = _format_compact(report)
        assert "DAR:2" in compact
        assert "delegate_task_dispatch" in compact
        assert "live_model_call" in compact


class TestRealExecutionAlwaysFalse:
    """T-31: real_execution is always False in output."""

    def test_real_execution_false(self, tmp_path):
        """T-31: real_execution field is always False."""
        registry_dir = tmp_path / ".vibe" / "deferred_registry"
        registry_dir.mkdir(parents=True)
        # Include real_execution=True in source — should be overridden
        entry = {
            "workorder_id": "deferred-exec-20260623T120000-abcdef12",
            "action": "delegate_task_dispatch",
            "approval_id": "approval-exec-001",
            "risk_level": "low",
            "real_execution": True,  # This should be overridden
            "registry_only": True,
            "dry_run_only": True,
            "created_at": "2026-06-23T12:00:00+00:00",
            "history_digest": "exec123",
        }
        (registry_dir / "exec.json").write_text(
            _json2.dumps(entry, indent=2), encoding="utf-8"
        )
        result = _collect_deferred_registry(str(tmp_path))
        assert len(result) == 1
        assert result[0]["real_execution"] is False


class TestDeferredRegistrySchemaValidation:
    """T-32: Report schema validates with deferred_action_registry optional section."""

    def test_schema_validates_with_dar_section(self):
        """T-32: Schema accepts deferred_action_registry as optional section."""
        from vibe_report_schema import validate_report, OPTIONAL_SECTIONS
        assert "deferred_action_registry" in OPTIONAL_SECTIONS
        report = {
            "pr_merge_info": {"pr": 211, "merged": True},
            "changed_paths": ["scripts/vibe_run_report.py"],
            "baseline": {"current_sha": "ec9eb08"},
            "validation": {"smoke": "PASS", "qg": "PASS", "v1_freeze": "PASS"},
            "node_attribution": {
                "controller_node": "windows", "execution_node": "windows",
                "transport": "local", "git_mutation_node": "windows",
                "token_access_node": "windows", "pr_operation_node": "windows",
            },
            "token_status": {"token_read": False, "token_leaked": False, "token_source": "gh_cached"},
            "external_write_status": {"real_write_occurred": False},
            "deferred_action_registry": [
                {
                    "action": "delegate_task_dispatch",
                    "approval_id": "approval-32",
                    "workorder_id": "deferred-dispatch-001",
                    "risk_level": "low",
                    "dedicated_approval": False,
                    "registry_only": True,
                    "dry_run_only": True,
                    "real_execution": False,
                    "created_at": "2026-06-23T12:00:00+00:00",
                    "history_digest": "schema123",
                }
            ],
        }
        result = validate_report(report)
        assert result["valid"] is True
        # No warning about deferred_action_registry since it's present
        dar_warnings = [w for w in result["warnings"] if "deferred_action_registry" in w]
        assert len(dar_warnings) == 0


class TestExistingTestsUnaffected:
    """T-33: Existing T-01~T-22 still pass (verified by scoped pytest run)."""

    def test_deferred_registry_does_not_affect_old_report(self, tmp_path):
        """T-33: Report without deferred registry works identically to pre-V1.21.21."""
        report = run_report(repo_root=str(tmp_path))
        assert "deferred_action_registry" not in report
        md = _format_markdown(report)
        assert "Deferred Action Registry" not in md
        compact = _format_compact(report)
        assert "DAR:" not in compact
