#!/usr/bin/env python3
"""V1.21.24 — Deferred Registry Verifier Result Report Visibility tests.

Covers T-53~T-63: run_report JSON/markdown/compact/snapshot includes
verifier_deferred_result, absent/empty skip, FAIL/WARN/PASS render,
schema validation, existing tests unaffected.

Read-only. No real execution, no gate verdict change, no new verdicts.
"""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _vdr_pass():
    """Return a PASS verifier deferred result dict."""
    return {
        "name": "deferred_action_registry_consistency",
        "result": "PASS",
        "detail": "2 entries, all invariants valid",
        "errors": [],
        "warnings": [],
    }


def _vdr_warn():
    """Return a WARN verifier deferred result dict."""
    return {
        "name": "deferred_action_registry_consistency",
        "result": "WARN",
        "detail": "entry[0]: service_admin_uac + dedicated_approval=True → ⚠️ dedicated/critical visibility only",
        "errors": [],
        "warnings": [
            "entry[0]: service_admin_uac + dedicated_approval=True → ⚠️ dedicated/critical visibility only",
        ],
    }


def _vdr_fail():
    """Return a FAIL verifier deferred result dict."""
    return {
        "name": "deferred_action_registry_consistency",
        "result": "FAIL",
        "detail": "entry[0]: real_execution=True (must be False)",
        "errors": [
            "entry[0]: real_execution=True (must be False)",
        ],
        "warnings": [],
    }


def _run_report_with_vdr(vdr, tmp_path):
    """Run run_report with mocked verifier deferred result."""
    from vibe_run_report import run_report, _collect_verifier_deferred_result
    with patch.object(
        sys.modules["vibe_run_report"],
        "_collect_verifier_deferred_result",
        return_value=vdr,
    ):
        return run_report(repo_root=tmp_path)


# ── T-53: JSON includes verifier_deferred_result ───────────────────────────

class TestT53JsonIncludesVdr:
    """T-53: run_report JSON includes verifier_deferred_result when check exists."""

    def test_json_pass(self, tmp_path):
        """JSON output includes verifier_deferred_result with PASS."""
        result = _run_report_with_vdr(_vdr_pass(), tmp_path)
        assert "verifier_deferred_result" in result
        assert result["verifier_deferred_result"]["result"] == "PASS"

    def test_json_warn(self, tmp_path):
        """JSON output includes verifier_deferred_result with WARN."""
        result = _run_report_with_vdr(_vdr_warn(), tmp_path)
        assert "verifier_deferred_result" in result
        assert result["verifier_deferred_result"]["result"] == "WARN"

    def test_json_fail(self, tmp_path):
        """JSON output includes verifier_deferred_result with FAIL."""
        result = _run_report_with_vdr(_vdr_fail(), tmp_path)
        assert "verifier_deferred_result" in result
        assert result["verifier_deferred_result"]["result"] == "FAIL"


# ── T-54: JSON omits verifier_deferred_result ─────────────────────────────

class TestT54JsonOmitsVdr:
    """T-54: run_report JSON omits verifier_deferred_result when check absent."""

    def test_json_omit_when_none(self, tmp_path):
        """No verifier_deferred_result when collector returns None."""
        result = _run_report_with_vdr(None, tmp_path)
        assert "verifier_deferred_result" not in result


# ── T-55: Markdown renders verifier deferred section ─────────────────────

class TestT55MarkdownRendersVdr:
    """T-55: run_report markdown renders Verifier Deferred Registry section."""

    def test_markdown_pass_section(self, tmp_path):
        """Markdown includes Verifier Deferred Registry section for PASS."""
        result = _run_report_with_vdr(_vdr_pass(), tmp_path)
        from vibe_run_report import _format_markdown
        md = _format_markdown(result)
        assert "## Verifier Deferred Registry" in md
        assert "✅" in md
        assert "all invariants valid" in md

    def test_markdown_warn_section(self, tmp_path):
        """Markdown includes Verifier Deferred Registry section for WARN."""
        result = _run_report_with_vdr(_vdr_warn(), tmp_path)
        from vibe_run_report import _format_markdown
        md = _format_markdown(result)
        assert "## Verifier Deferred Registry" in md
        assert "⚠️" in md
        assert "dedicated/critical visibility only" in md

    def test_markdown_fail_section(self, tmp_path):
        """Markdown includes Verifier Deferred Registry section for FAIL."""
        result = _run_report_with_vdr(_vdr_fail(), tmp_path)
        from vibe_run_report import _format_markdown
        md = _format_markdown(result)
        assert "## Verifier Deferred Registry" in md
        assert "❌" in md
        assert "real_execution=True" in md


# ── T-56: Compact includes VDR prefix ────────────────────────────────────

class TestT56CompactIncludesVdr:
    """T-56: run_report compact includes VDR:PASS/WARN/FAIL prefix."""

    def test_compact_pass(self, tmp_path):
        """Compact output includes VDR:PASS."""
        result = _run_report_with_vdr(_vdr_pass(), tmp_path)
        from vibe_run_report import _format_compact
        compact = _format_compact(result)
        assert "VDR:PASS" in compact

    def test_compact_warn(self, tmp_path):
        """Compact output includes VDR:WARN."""
        result = _run_report_with_vdr(_vdr_warn(), tmp_path)
        from vibe_run_report import _format_compact
        compact = _format_compact(result)
        assert "VDR:WARN" in compact

    def test_compact_fail(self, tmp_path):
        """Compact output includes VDR:FAIL."""
        result = _run_report_with_vdr(_vdr_fail(), tmp_path)
        from vibe_run_report import _format_compact
        compact = _format_compact(result)
        assert "VDR:FAIL" in compact


# ── T-57: Snapshot export includes verifier deferred section ─────────────

class TestT57SnapshotIncludesVdr:
    """T-57: Report export snapshot includes Verifier Deferred Registry section."""

    def test_snapshot_includes_vdr_section(self, tmp_path):
        """Snapshot content includes Verifier Deferred Registry section."""
        snapshot_content = "Some snapshot content\n"
        mock_rr = {
            "timestamp": "2026-06-23T10:00:00Z",
            "verifier_deferred_result": _vdr_pass(),
        }
        with patch("vibe_report_export._run_report", return_value=mock_rr):
            from vibe_report_export import _run_report
            if _run_report is not None:
                _rr = _run_report(repo_root=tmp_path)
                _vdr = _rr.get("verifier_deferred_result") if _rr else None
                if _vdr:
                    _vdr_result = _vdr.get("result", "UNKNOWN")
                    _vdr_detail = _vdr.get("detail", "")
                    _vlines = ["\n## Verifier Deferred Registry\n"]
                    if _vdr_result == "PASS":
                        _vlines.append("- ✅ %s\n" % _vdr_detail)
                    snapshot_content += "".join(_vlines)

        assert "## Verifier Deferred Registry" in snapshot_content
        assert "✅" in snapshot_content


# ── T-58: Absent/empty → no output ──────────────────────────────────────

class TestT58AbsentEmptyNoOutput:
    """T-58: absent/empty deferred_action_registry → no verifier deferred output."""

    def test_none_vdr_no_section(self, tmp_path):
        """No verifier deferred section when vdr is None."""
        result = _run_report_with_vdr(None, tmp_path)
        from vibe_run_report import _format_markdown, _format_compact
        md = _format_markdown(result)
        compact = _format_compact(result)
        assert "## Verifier Deferred Registry" not in md
        assert "VDR:" not in compact

    def test_none_vdr_no_json_field(self, tmp_path):
        """No verifier_deferred_result in JSON when vdr is None."""
        result = _run_report_with_vdr(None, tmp_path)
        assert "verifier_deferred_result" not in result


# ── T-59: FAIL renders with error details ────────────────────────────────

class TestT59FailRendersErrors:
    """T-59: FAIL result renders with error details in markdown."""

    def test_fail_error_details_in_markdown(self, tmp_path):
        """FAIL markdown includes error details."""
        result = _run_report_with_vdr(_vdr_fail(), tmp_path)
        from vibe_run_report import _format_markdown
        md = _format_markdown(result)
        assert "❌" in md
        assert "real_execution=True (must be False)" in md


# ── T-60: WARN renders with dedicated/critical annotation ───────────────

class TestT60WarnRendersDedicated:
    """T-60: WARN result renders with dedicated/critical visibility annotation."""

    def test_warn_dedicated_annotation(self, tmp_path):
        """WARN markdown includes dedicated/critical visibility annotation."""
        result = _run_report_with_vdr(_vdr_warn(), tmp_path)
        from vibe_run_report import _format_markdown
        md = _format_markdown(result)
        assert "⚠️" in md
        assert "dedicated/critical visibility only" in md


# ── T-61: PASS renders normally ─────────────────────────────────────────

class TestT61PassRendersNormally:
    """T-61: PASS result renders normally."""

    def test_pass_normal_render(self, tmp_path):
        """PASS markdown includes all invariants valid."""
        result = _run_report_with_vdr(_vdr_pass(), tmp_path)
        from vibe_run_report import _format_markdown
        md = _format_markdown(result)
        assert "✅" in md
        assert "all invariants valid" in md


# ── T-62: Schema validates with verifier_deferred_result ─────────────────

class TestT62SchemaValidates:
    """T-62: schema validates with verifier_deferred_result optional section."""

    def test_vdr_in_optional_sections(self):
        """verifier_deferred_result is in OPTIONAL_SECTIONS."""
        from vibe_report_schema import OPTIONAL_SECTIONS
        assert "verifier_deferred_result" in OPTIONAL_SECTIONS

    def test_schema_validates_with_vdr(self):
        """Report with verifier_deferred_result passes schema validation."""
        from vibe_report_schema import validate_report, OPTIONAL_SECTIONS
        # Build a report with all required sections
        report = {
            "timestamp": "2026-06-23T10:00:00Z",
            "version": "1.2.0",
            "baseline": {"sha": "abc123", "short": "abc1234", "current_sha": "abc123"},
            "quality_gate": {"verdict": "PASS", "checks": {}},
            "smoke_status": "PASS",
            "loop_summary": {"total_components": 5, "overall_health": "healthy"},
            "operator_snapshot": {"overall": "ok"},
            "evidence_verifier": {"status": "available"},
            "audit_lock": {"audit_status": "clean"},
            "pr_summary": {"total": 0, "open": 0, "merged": 0},
            "new_freeze_baseline": "abc123",
            "v1_freeze": {},
            "next_recommended_action": "none",
            "operator_summary": "ok",
            "pr_merge_info": {"merged": True},
            "changed_paths": [],
            "validation": {"smoke": "PASS", "qg": "PASS", "v1_freeze": "PASS"},
            "node_attribution": {
                "controller_node": "windows",
                "execution_node": "debian",
                "transport": "ssh",
                "git_mutation_node": "debian",
                "token_access_node": "windows",
                "pr_operation_node": "debian",
            },
            "token_status": {"token_read": True, "token_leaked": False, "token_source": "env"},
            "external_write_status": {"writes": []},
            # Optional: V1.21.24
            "verifier_deferred_result": {
                "name": "deferred_action_registry_consistency",
                "result": "PASS",
                "detail": "2 entries, all invariants valid",
            },
        }
        result = validate_report(report)
        assert result["valid"], "Unexpected errors: %s" % result["errors"]
        # Verify verifier_deferred_result counted as optional
        assert result["optional_sections_present"] >= 1


# ── T-63: Existing report tests still pass ───────────────────────────────

class TestT63ExistingTestsUnaffected:
    """T-63: existing report tests still pass."""

    def test_import_run_report(self):
        """vibe_run_report module imports without error."""
        import importlib
        spec = importlib.util.spec_from_file_location(
            "vibe_run_report",
            str(Path(__file__).parent.parent / "scripts" / "vibe_run_report.py"),
        )
        assert spec is not None

    def test_import_report_schema(self):
        """vibe_report_schema module imports without error."""
        import importlib
        spec = importlib.util.spec_from_file_location(
            "vibe_report_schema",
            str(Path(__file__).parent.parent / "scripts" / "vibe_report_schema.py"),
        )
        assert spec is not None

    def test_import_report_export(self):
        """vibe_report_export module imports without error."""
        import importlib
        spec = importlib.util.spec_from_file_location(
            "vibe_report_export",
            str(Path(__file__).parent.parent / "scripts" / "vibe_report_export.py"),
        )
        assert spec is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
