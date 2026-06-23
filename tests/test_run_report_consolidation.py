#!/usr/bin/env python3
"""V1.21.25A Master — Reporting Consolidation tests.

Covers: operator_snapshot dead field fix, evidence_verifier dynamic status,
unified DAR/VDR render functions, dedicated/critical condition unification.

Read-only. No real execution, no gate verdict change, no new verdicts.
"""
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_operator_snapshot():
    """Return a realistic operator_snapshot dict (with repo, jobs_summary, etc.)."""
    return {
        "repo": {
            "local_main_sha": "abc123def456",
            "remote_main_sha": "abc123def456",
            "main_consistent": True,
            "working_tree_dirty": False,
            "current_branch": "main",
        },
        "jobs_summary": {
            "total_jobs": 5,
            "merged_total": 3,
            "blocked_total": 1,
        },
        "locks": [],
        "recommended_next_action": "review PR #215",
        "warnings": ["test warning"],
    }


def _mock_run_report_result():
    """Return a realistic run_report result dict."""
    return {
        "timestamp": "2026-06-23T12:00:00Z",
        "version": "1.2.0",
        "operator_snapshot": {
            "repo": _mock_operator_snapshot()["repo"],
            "jobs_summary": _mock_operator_snapshot()["jobs_summary"],
            "locks": [],
            "recommended_next_action": "review PR #215",
            "warnings": ["test warning"],
        },
        "evidence_verifier": {"status": "available"},
        "deferred_action_registry": [
            {
                "action": "code_modify",
                "workorder_id": "wo-001",
                "approval_id": "approval-001",
                "risk_level": "low",
                "dedicated_approval": False,
                "real_execution": False,
            },
            {
                "action": "service_admin_uac",
                "workorder_id": "wo-002",
                "approval_id": "approval-002",
                "risk_level": "high",
                "dedicated_approval": True,
                "real_execution": False,
            },
        ],
        "verifier_deferred_result": {
            "name": "deferred_action_registry_consistency",
            "result": "WARN",
            "detail": "service_admin_uac + dedicated_approval=True",
            "errors": [],
            "warnings": ["service_admin_uac + dedicated_approval=True → dedicated/critical"],
        },
    }


# ── T-81: operator_snapshot passes full data ────────────────────────────────

class TestT81OperatorSnapshotData:
    """T-81: run_report operator_snapshot field passes full data, not just overall."""

    def test_operator_snapshot_has_repo(self, tmp_path):
        """operator_snapshot.repo contains repo info."""
        from vibe_run_report import run_report
        mock_snapshot = _mock_operator_snapshot()

        with patch("vibe_run_report._get_operator_snapshot", return_value=mock_snapshot):
            result = run_report(repo_root=tmp_path)

        op = result.get("operator_snapshot", {})
        assert "repo" in op, "operator_snapshot should have 'repo' key"
        assert op["repo"].get("local_main_sha") == "abc123def456"

    def test_operator_snapshot_has_jobs_summary(self, tmp_path):
        """operator_snapshot.jobs_summary contains job data."""
        from vibe_run_report import run_report
        mock_snapshot = _mock_operator_snapshot()

        with patch("vibe_run_report._get_operator_snapshot", return_value=mock_snapshot):
            result = run_report(repo_root=tmp_path)

        op = result.get("operator_snapshot", {})
        assert "jobs_summary" in op
        assert op["jobs_summary"].get("total_jobs") == 5

    def test_operator_snapshot_has_recommended_action(self, tmp_path):
        """operator_snapshot.recommended_next_action present."""
        from vibe_run_report import run_report
        mock_snapshot = _mock_operator_snapshot()

        with patch("vibe_run_report._get_operator_snapshot", return_value=mock_snapshot):
            result = run_report(repo_root=tmp_path)

        op = result.get("operator_snapshot", {})
        assert "recommended_next_action" in op
        assert op["recommended_next_action"] == "review PR #215"

    def test_operator_snapshot_has_warnings(self, tmp_path):
        """operator_snapshot.warnings present."""
        from vibe_run_report import run_report
        mock_snapshot = _mock_operator_snapshot()

        with patch("vibe_run_report._get_operator_snapshot", return_value=mock_snapshot):
            result = run_report(repo_root=tmp_path)

        op = result.get("operator_snapshot", {})
        assert "warnings" in op
        assert "test warning" in op["warnings"]

    def test_operator_snapshot_no_overall_unknown(self, tmp_path):
        """operator_snapshot no longer has dead 'overall': 'unknown' field."""
        from vibe_run_report import run_report
        mock_snapshot = _mock_operator_snapshot()

        with patch("vibe_run_report._get_operator_snapshot", return_value=mock_snapshot):
            result = run_report(repo_root=tmp_path)

        op = result.get("operator_snapshot", {})
        # The old dead field should not exist
        assert op.get("overall") != "unknown", "Dead 'overall: unknown' field should be removed"


# ── T-82: evidence_verifier dynamic status ──────────────────────────────────

class TestT82EvidenceVerifierDynamic:
    """T-82: evidence_verifier.status is dynamic, not hardcoded."""

    def test_verifier_available_when_script_exists(self, tmp_path):
        """Status is 'available' when vibe_evidence_verifier.py exists."""
        # Create mock verifier script
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "vibe_evidence_verifier.py").touch()

        from vibe_run_report import run_report
        result = run_report(repo_root=tmp_path)

        ev = result.get("evidence_verifier", {})
        assert ev.get("status") == "available"

    def test_verifier_unavailable_when_script_missing(self, tmp_path):
        """Status is 'unavailable' when vibe_evidence_verifier.py missing."""
        # Ensure scripts dir exists but no verifier
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True)

        from vibe_run_report import run_report
        result = run_report(repo_root=tmp_path)

        ev = result.get("evidence_verifier", {})
        assert ev.get("status") == "unavailable"


# ── T-83: render_dar_section unified format ─────────────────────────────────

class TestT83RenderDarSection:
    """T-83: render_dar_section produces unified format with all fields."""

    def test_dar_includes_workorder_id(self):
        """DAR rendering includes workorder_id."""
        from vibe_run_report import render_dar_section
        result = _mock_run_report_result()
        md = render_dar_section(result)
        assert "wo=`wo-001`" in md

    def test_dar_includes_approval_id(self):
        """DAR rendering includes approval_id."""
        from vibe_run_report import render_dar_section
        result = _mock_run_report_result()
        md = render_dar_section(result)
        assert "approval=`approval-001`" in md

    def test_dar_includes_real_execution(self):
        """DAR rendering includes real_execution."""
        from vibe_run_report import render_dar_section
        result = _mock_run_report_result()
        md = render_dar_section(result)
        assert "real_exec=no" in md

    def test_dar_dedicated_any_action(self):
        """DAR dedicated/critical annotation applies to ANY action with dedicated_approval=True."""
        from vibe_run_report import render_dar_section
        result = _mock_run_report_result()
        md = render_dar_section(result)
        # service_admin_uac with dedicated_approval=True should show warning
        assert "dedicated/critical visibility only" in md

    def test_dar_empty_when_no_entries(self):
        """render_dar_section returns empty string when no DAR entries."""
        from vibe_run_report import render_dar_section
        md = render_dar_section({"timestamp": "2026-06-23"})
        assert md == ""


# ── T-84: render_vdr_section ───────────────────────────────────────────────

class TestT84RenderVdrSection:
    """T-84: render_vdr_section produces PASS/WARN/FAIL rendering."""

    def test_vdr_warn_with_warnings(self):
        """VDR WARN renders with warnings list."""
        from vibe_run_report import render_vdr_section
        result = _mock_run_report_result()
        md = render_vdr_section(result)
        assert "⚠️" in md
        assert "dedicated/critical" in md

    def test_vdr_pass(self):
        """VDR PASS renders with detail."""
        from vibe_run_report import render_vdr_section
        result = {"verifier_deferred_result": {"result": "PASS", "detail": "all valid", "errors": [], "warnings": []}}
        md = render_vdr_section(result)
        assert "✅" in md
        assert "all valid" in md

    def test_vdr_fail(self):
        """VDR FAIL renders with errors."""
        from vibe_run_report import render_vdr_section
        result = {"verifier_deferred_result": {"result": "FAIL", "detail": "bad", "errors": ["entry[0]: bad"], "warnings": []}}
        md = render_vdr_section(result)
        assert "❌" in md
        assert "entry[0]: bad" in md

    def test_vdr_empty_when_no_result(self):
        """render_vdr_section returns empty string when no VDR."""
        from vibe_run_report import render_vdr_section
        md = render_vdr_section({"timestamp": "2026-06-23"})
        assert md == ""


# ── T-85: render functions used by _format_markdown ────────────────────────

class TestT85FormatMarkdownUsesRenders:
    """T-85: _format_markdown uses render_dar_section/render_vdr_section."""

    def test_markdown_includes_dar_from_render_function(self):
        """_format_markdown includes DAR section from render function."""
        from vibe_run_report import _format_markdown
        result = _mock_run_report_result()
        md = _format_markdown(result)
        assert "## Deferred Action Registry" in md
        assert "wo=`wo-001`" in md

    def test_markdown_includes_vdr_from_render_function(self):
        """_format_markdown includes VDR section from render function."""
        from vibe_run_report import _format_markdown
        result = _mock_run_report_result()
        md = _format_markdown(result)
        assert "## Verifier Deferred Registry" in md


# ── T-86: Export reuses render functions ────────────────────────────────────

class TestT86ExportReusesRenders:
    """T-86: export layer imports and uses render_dar_section/render_vdr_section."""

    def test_export_imports_render_functions(self):
        """Export module imports render_dar_section and render_vdr_section."""
        import vibe_report_export as mod
        assert hasattr(mod, "_render_dar"), "Export should import _render_dar"
        assert hasattr(mod, "_render_vdr"), "Export should import _render_vdr"

    def test_export_no_inline_dar_rendering(self):
        """Export should not have inline DAR rendering code."""
        export_path = Path(__file__).parent.parent / "scripts" / "vibe_report_export.py"
        source = export_path.read_text()
        # The inline rendering had these patterns
        assert "## Deferred Action Registry\\n" not in source, \
            "Export should not have inline DAR rendering"


# ── T-87: Dashboard no-waste-call ───────────────────────────────────────────

class TestT87DashboardNoWaste:
    """T-87: dashboard export reads PROJECT_DASHBOARD.md first, no wasted call."""

    def test_dashboard_reads_file_first(self, tmp_path):
        """When PROJECT_DASHBOARD.md exists, operator_snapshot.py not called."""
        # _export_kind uses script_dir.parent / "docs" / "PROJECT_DASHBOARD.md"
        docs_dir = tmp_path.parent / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "PROJECT_DASHBOARD.md").write_text("# Dashboard\nContent\n")

        mock_run_script = MagicMock(return_value=(0, "snapshot output", ""))

        with patch("vibe_report_export._run_script", mock_run_script):
            from vibe_report_export import _export_kind
            result = _export_kind(tmp_path, "dashboard")

        # operator_snapshot.py should NOT have been called
        for c in mock_run_script.call_args_list:
            args = c[0]
            if len(args) > 0 and "operator_snapshot" in str(args[0]):
                pytest.fail("operator_snapshot.py should not be called when dashboard file exists")

    def test_dashboard_fallback_when_no_file(self, tmp_path):
        """When PROJECT_DASHBOARD.md missing, falls back to operator_snapshot.py."""
        # Ensure no dashboard file exists
        docs_dir = tmp_path.parent / "docs"
        if docs_dir.exists():
            import shutil
            shutil.rmtree(docs_dir)

        call_log = []
        def tracking_run_script(script_path, args, timeout=30):
            call_log.append(str(script_path))
            return (0, "snapshot output", "")

        with patch("vibe_report_export._run_script", side_effect=tracking_run_script):
            from vibe_report_export import _export_kind
            result = _export_kind(tmp_path, "dashboard")

        # operator_snapshot.py SHOULD have been called
        snapshot_called = any("operator_snapshot" in p for p in call_log)
        assert snapshot_called, "operator_snapshot.py should be called as fallback"


# ── T-88: No real execution / no gate change ────────────────────────────────

class TestT88NoRealExecution:
    """T-88: no real execution, no gate verdict change, no new verdicts."""

    def test_no_delegate_task_in_run_report(self):
        """run_report does not call delegate_task."""
        rr_path = Path(__file__).parent.parent / "scripts" / "vibe_run_report.py"
        source = rr_path.read_text()
        assert "delegate_task" not in source

    def test_no_delegate_task_in_export(self):
        """export does not call delegate_task."""
        export_path = Path(__file__).parent.parent / "scripts" / "vibe_report_export.py"
        source = export_path.read_text()
        assert "delegate_task" not in source


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
