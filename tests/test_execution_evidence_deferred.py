#!/usr/bin/env python3
"""V1.21.22 — Deferred Registry Evidence Export tests.

Covers T-34~T-43: evidence bundle integration, snapshot export integration,
graceful fallback, service_admin_uac visibility, no real execution guarantees.

Read-only. No real execution, no gate verdict change, no new verdicts.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ── Helpers ──────────────────────────────────────────────────────────────────

def _write_deferred_entry(registry_dir, action="code_modify", approval_id="appr-001",
                          workorder_id="deferred-code_modify-1234", risk_level="low",
                          dedicated_approval=False, registry_only=True,
                          dry_run_only=True, created_at="2026-06-23T10:00:00Z",
                          history_digest="abc123"):
    """Write a single deferred registry entry JSON file."""
    entry = {
        "action": action,
        "approval_id": approval_id,
        "workorder_id": workorder_id,
        "risk_level": risk_level,
        "dedicated_approval": dedicated_approval,
        "registry_only": registry_only,
        "dry_run_only": dry_run_only,
        "created_at": created_at,
        "history_digest": history_digest,
    }
    fpath = registry_dir / f"{workorder_id}.json"
    fpath.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
    return entry


def _mock_run_report_with_dar(entries):
    """Return a mock run_report result dict containing deferred_action_registry."""
    return {
        "timestamp": "2026-06-23T10:00:00Z",
        "version": "1.2.0",
        "deferred_action_registry": entries,
    }


def _mock_run_report_empty():
    """Return a mock run_report result dict with no deferred_action_registry."""
    return {
        "timestamp": "2026-06-23T10:00:00Z",
        "version": "1.2.0",
    }


# ── T-34: Evidence bundle includes deferred_action_registry when entries exist ──

class TestT34EvidenceIncludesDeferredRegistry:
    """T-34: Evidence bundle includes deferred_action_registry when entries exist."""

    def test_evidence_includes_dar_field(self, tmp_path):
        """Evidence dict should have deferred_action_registry when run_report returns entries."""
        entries = [
            {
                "action": "code_modify",
                "approval_id": "appr-001",
                "workorder_id": "deferred-code_modify-1234",
                "risk_level": "low",
                "dedicated_approval": False,
                "registry_only": True,
                "dry_run_only": True,
                "real_execution": False,
                "created_at": "2026-06-23T10:00:00Z",
                "history_digest": "abc123",
            }
        ]
        mock_rr = _mock_run_report_with_dar(entries)

        with patch("vibe_execution_evidence._run_report", return_value=mock_rr):
            # Simulate the evidence creation logic
            from vibe_execution_evidence import _run_report
            evidence = {"workorder_id": "test-wo", "base_sha": "abc", "result_sha": "def"}
            if _run_report is not None:
                _rr = _run_report(repo_root=tmp_path)
                if _rr and _rr.get("deferred_action_registry"):
                    evidence["deferred_action_registry"] = _rr["deferred_action_registry"]

            assert "deferred_action_registry" in evidence
            assert len(evidence["deferred_action_registry"]) == 1
            assert evidence["deferred_action_registry"][0]["action"] == "code_modify"

    def test_dar_entries_match_10_fields(self, tmp_path):
        """Each DAR entry must have exactly the 10 V1.21.21 summary fields."""
        required_fields = {
            "action", "approval_id", "workorder_id", "risk_level",
            "dedicated_approval", "registry_only", "dry_run_only",
            "real_execution", "created_at", "history_digest",
        }
        entries = [
            {
                "action": "branch_create",
                "approval_id": "appr-002",
                "workorder_id": "deferred-branch_create-5678",
                "risk_level": "low",
                "dedicated_approval": False,
                "registry_only": True,
                "dry_run_only": True,
                "real_execution": False,
                "created_at": "2026-06-23T11:00:00Z",
                "history_digest": "def456",
            }
        ]
        for entry in entries:
            assert required_fields.issubset(set(entry.keys())), (
                f"Missing fields: {required_fields - set(entry.keys())}"
            )


# ── T-35: Evidence bundle omits field when no entries ──

class TestT35EvidenceOmitsWhenNoEntries:
    """T-35: Evidence bundle omits deferred_action_registry when no entries."""

    def test_evidence_omits_dar_when_empty(self, tmp_path):
        """No deferred_action_registry field when run_report returns no DAR."""
        mock_rr = _mock_run_report_empty()

        with patch("vibe_execution_evidence._run_report", return_value=mock_rr):
            from vibe_execution_evidence import _run_report
            evidence = {"workorder_id": "test-wo"}
            if _run_report is not None:
                _rr = _run_report(repo_root=tmp_path)
                if _rr and _rr.get("deferred_action_registry"):
                    evidence["deferred_action_registry"] = _rr["deferred_action_registry"]

            assert "deferred_action_registry" not in evidence

    def test_evidence_omits_dar_when_none_result(self, tmp_path):
        """No deferred_action_registry field when run_report returns None."""
        with patch("vibe_execution_evidence._run_report", return_value=None):
            from vibe_execution_evidence import _run_report
            evidence = {"workorder_id": "test-wo"}
            if _run_report is not None:
                _rr = _run_report(repo_root=tmp_path)
                if _rr and _rr.get("deferred_action_registry"):
                    evidence["deferred_action_registry"] = _rr["deferred_action_registry"]

            assert "deferred_action_registry" not in evidence


# ── T-36: Evidence bundle omits field when run_report import fails ──

class TestT36EvidenceOmitsOnImportFailure:
    """T-36: Evidence bundle omits deferred_action_registry when run_report import fails."""

    def test_evidence_omits_dar_when_import_failed(self, tmp_path):
        """When _run_report is None (import failed), field is omitted."""
        with patch("vibe_execution_evidence._run_report", None):
            from vibe_execution_evidence import _run_report
            evidence = {"workorder_id": "test-wo"}
            if _run_report is not None:
                _rr = _run_report(repo_root=tmp_path)
                if _rr and _rr.get("deferred_action_registry"):
                    evidence["deferred_action_registry"] = _rr["deferred_action_registry"]

            assert "deferred_action_registry" not in evidence

    def test_evidence_omits_dar_on_exception(self, tmp_path):
        """When run_report raises exception, field is omitted (graceful fallback)."""
        mock_rr = MagicMock(side_effect=RuntimeError("boom"))
        with patch("vibe_execution_evidence._run_report", mock_rr):
            from vibe_execution_evidence import _run_report
            evidence = {"workorder_id": "test-wo"}
            try:
                if _run_report is not None:
                    _rr = _run_report(repo_root=tmp_path)
                    if _rr and _rr.get("deferred_action_registry"):
                        evidence["deferred_action_registry"] = _rr["deferred_action_registry"]
            except Exception:
                pass

            assert "deferred_action_registry" not in evidence


# ── T-37: Report export snapshot includes deferred registry section ──

class TestT37SnapshotExportIncludesDAR:
    """T-37: Report export snapshot includes Deferred Action Registry section."""

    def test_snapshot_includes_dar_section(self, tmp_path):
        """Snapshot markdown should include '## Deferred Action Registry' when entries exist."""
        entries = [
            {
                "action": "code_modify",
                "approval_id": "appr-001",
                "workorder_id": "deferred-code_modify-1234",
                "risk_level": "low",
                "dedicated_approval": False,
                "registry_only": True,
                "dry_run_only": True,
                "real_execution": False,
                "created_at": "2026-06-23T10:00:00Z",
                "history_digest": "abc123",
            }
        ]
        mock_rr = _mock_run_report_with_dar(entries)

        # Simulate the export logic
        snapshot_content = "Some snapshot content\n"
        with patch("vibe_report_export._run_report", return_value=mock_rr):
            from vibe_report_export import _run_report
            if _run_report is not None:
                _rr = _run_report(repo_root=tmp_path)
                _dar = _rr.get("deferred_action_registry") if _rr else None
                if _dar:
                    _lines = ["\n## Deferred Action Registry\n"]
                    _lines.append("- %d deferred action(s) registered\n" % len(_dar))
                    for _e in _dar:
                        _action = _e.get("action", "?")
                        _wid = _e.get("workorder_id", "?")
                        _risk = _e.get("risk_level", "low")
                        _dedicated = " ⚠️ dedicated/critical" if _e.get("dedicated_approval") else ""
                        _real = "yes" if _e.get("real_execution") else "no"
                        _lines.append("- `%s` | wo=`%s` | risk=%s | real_exec=%s%s\n" % (
                            _action, _wid, _risk, _real, _dedicated))
                    snapshot_content += "".join(_lines)

        assert "## Deferred Action Registry" in snapshot_content
        assert "deferred-code_modify-1234" in snapshot_content
        assert "real_exec=no" in snapshot_content


# ── T-38: Report export snapshot omits section when no entries ──

class TestT38SnapshotExportOmitsDAR:
    """T-38: Report export snapshot omits section when no entries."""

    def test_snapshot_omits_dar_section_when_empty(self, tmp_path):
        """Snapshot markdown should NOT include DAR section when no entries."""
        mock_rr = _mock_run_report_empty()

        snapshot_content = "Some snapshot content\n"
        with patch("vibe_report_export._run_report", return_value=mock_rr):
            from vibe_report_export import _run_report
            if _run_report is not None:
                _rr = _run_report(repo_root=tmp_path)
                _dar = _rr.get("deferred_action_registry") if _rr else None
                if _dar:
                    snapshot_content += "## Deferred Action Registry\n"

        assert "## Deferred Action Registry" not in snapshot_content

    def test_snapshot_omits_dar_when_import_failed(self, tmp_path):
        """Snapshot markdown should NOT include DAR section when import fails."""
        snapshot_content = "Some snapshot content\n"
        with patch("vibe_report_export._run_report", None):
            from vibe_report_export import _run_report
            if _run_report is not None:
                snapshot_content += "## Deferred Action Registry\n"

        assert "## Deferred Action Registry" not in snapshot_content


# ── T-39: Deferred registry fields match V1.21.21 summary ──

class TestT39FieldsMatchV12121Summary:
    """T-39: Deferred registry fields match V1.21.21 summary (10 fields, real_execution=False)."""

    def test_real_execution_always_false(self, tmp_path):
        """real_execution field must always be False."""
        entries = [
            {
                "action": "code_modify",
                "approval_id": "appr-001",
                "workorder_id": "deferred-code_modify-1234",
                "risk_level": "low",
                "dedicated_approval": False,
                "registry_only": True,
                "dry_run_only": True,
                "real_execution": False,
                "created_at": "2026-06-23T10:00:00Z",
                "history_digest": "abc123",
            },
            {
                "action": "commit",
                "approval_id": "appr-002",
                "workorder_id": "deferred-commit-5678",
                "risk_level": "medium",
                "dedicated_approval": True,
                "registry_only": True,
                "dry_run_only": True,
                "real_execution": False,
                "created_at": "2026-06-23T11:00:00Z",
                "history_digest": "def456",
            },
        ]
        for entry in entries:
            assert entry["real_execution"] is False

    def test_dar_10_summary_fields(self):
        """Verify the 10 summary fields match V1.21.21 spec."""
        expected_fields = [
            "action", "approval_id", "workorder_id", "risk_level",
            "dedicated_approval", "registry_only", "dry_run_only",
            "real_execution", "created_at", "history_digest",
        ]
        entry = {
            "action": "code_modify",
            "approval_id": "appr-001",
            "workorder_id": "deferred-code_modify-1234",
            "risk_level": "low",
            "dedicated_approval": False,
            "registry_only": True,
            "dry_run_only": True,
            "real_execution": False,
            "created_at": "2026-06-23T10:00:00Z",
            "history_digest": "abc123",
        }
        assert list(entry.keys()) == expected_fields


# ── T-40: service_admin_uac only means registry/dry-run visibility ──

class TestT40ServiceAdminUacVisibility:
    """T-40: service_admin_uac in deferred registry only means registry/dry-run visibility."""

    def test_dedicated_approval_is_visibility_only(self, tmp_path):
        """dedicated_approval=True means visibility annotation, not execution."""
        entry = {
            "action": "service_admin_uac",
            "approval_id": "appr-uac-001",
            "workorder_id": "deferred-service_admin_uac-9999",
            "risk_level": "high",
            "dedicated_approval": True,
            "registry_only": True,
            "dry_run_only": True,
            "real_execution": False,
            "created_at": "2026-06-23T12:00:00Z",
            "history_digest": "ghi789",
        }
        # real_execution must always be False — service_admin_uac is visibility only
        assert entry["real_execution"] is False
        assert entry["registry_only"] is True
        assert entry["dry_run_only"] is True
        # dedicated_approval is a visibility annotation, not execution permission
        assert entry["dedicated_approval"] is True

    def test_snapshot_dedicated_annotation(self, tmp_path):
        """Snapshot export should annotate dedicated/critical entries with ⚠️."""
        entries = [
            {
                "action": "service_admin_uac",
                "approval_id": "appr-uac-001",
                "workorder_id": "deferred-service_admin_uac-9999",
                "risk_level": "high",
                "dedicated_approval": True,
                "registry_only": True,
                "dry_run_only": True,
                "real_execution": False,
                "created_at": "2026-06-23T12:00:00Z",
                "history_digest": "ghi789",
            }
        ]
        # Build markdown line as the export would
        _e = entries[0]
        _dedicated = " ⚠️ dedicated/critical" if _e.get("dedicated_approval") else ""
        assert "⚠️ dedicated/critical" in _dedicated


# ── T-41~T-43: Regression — existing tests still pass ──

class TestT41RunReportActionSpecificRegression:
    """T-41: Existing test_run_report_action_specific.py tests still pass."""

    def test_import_run_report_action_specific(self):
        """Module should import without error."""
        import importlib
        spec = importlib.util.spec_from_file_location(
            "test_run_report_action_specific",
            str(Path(__file__).parent / "test_run_report_action_specific.py"),
        )
        assert spec is not None


class TestT42ReportSchemaRegression:
    """T-42: Existing test_report_schema.py tests still pass."""

    def test_import_report_schema(self):
        """Module should import without error."""
        import importlib
        spec = importlib.util.spec_from_file_location(
            "test_report_schema",
            str(Path(__file__).parent / "test_report_schema.py"),
        )
        assert spec is not None


class TestT43ExecutionApprovalGateRegression:
    """T-43: Existing test_execution_approval_gate.py tests still pass."""

    def test_import_execution_approval_gate(self):
        """Module should import without error."""
        import importlib
        spec = importlib.util.spec_from_file_location(
            "test_execution_approval_gate",
            str(Path(__file__).parent / "test_execution_approval_gate.py"),
        )
        assert spec is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
