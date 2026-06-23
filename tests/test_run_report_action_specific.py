"""Tests for vibe_run_report.py action-specific audit visibility (V1.21.16).

Covers T-01 through T-10 from the V1.21.16 proposal.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from vibe_run_report import (
    VERSION,
    _collect_action_specific,
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
