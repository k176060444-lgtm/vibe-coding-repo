"""Tests for vibe_report_schema.py (V1.21.15)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from vibe_report_schema import (
    OPTIONAL_SECTIONS,
    VERSION,
    validate_report,
    self_check as schema_self_check,
)


class TestVersion:
    def test_version(self):
        assert VERSION == "1.2.0"


class TestActionSpecificApprovalSection:
    """V1.21.15: action_specific_approval optional section."""

    def test_section_in_optional_sections(self):
        """T-11: action_specific_approval in OPTIONAL_SECTIONS."""
        assert "action_specific_approval" in OPTIONAL_SECTIONS

    def test_valid_report_without_section(self):
        """T-12: missing section = warning only, not error."""
        report = {
            "pr_merge_info": {"pr": 134, "merged": True},
            "changed_paths": ["scripts/foo.py"],
            "baseline": {"current_sha": "abc123"},
            "validation": {"smoke": "PASS", "qg": "PASS", "v1_freeze": "PASS"},
            "node_attribution": {
                "controller_node": "windows", "execution_node": "debian",
                "transport": "ssh", "git_mutation_node": "debian",
                "token_access_node": "debian", "pr_operation_node": "debian",
            },
            "token_status": {"token_read": False, "token_leaked": False, "token_source": "gh_cached"},
            "external_write_status": {"real_write_occurred": False},
        }
        result = validate_report(report)
        assert result["valid"] is True
        # Should have a warning about missing action_specific_approval
        asa_warnings = [w for w in result["warnings"] if "action_specific_approval" in w]
        assert len(asa_warnings) == 1

    def test_valid_report_with_section(self):
        """T-11: report with action_specific_approval section = no warning."""
        report = {
            "pr_merge_info": {"pr": 134, "merged": True},
            "changed_paths": ["scripts/foo.py"],
            "baseline": {"current_sha": "abc123"},
            "validation": {"smoke": "PASS", "qg": "PASS", "v1_freeze": "PASS"},
            "node_attribution": {
                "controller_node": "windows", "execution_node": "debian",
                "transport": "ssh", "git_mutation_node": "debian",
                "token_access_node": "debian", "pr_operation_node": "debian",
            },
            "token_status": {"token_read": False, "token_leaked": False, "token_source": "gh_cached"},
            "external_write_status": {"real_write_occurred": False},
            "action_specific_approval": {
                "action": "service_admin_uac",
                "action_category": "action_specific",
                "verdict": "BLOCKED_SERVICE_ADMIN_REQUIRES_DEDICATED_APPROVAL",
                "blocked_reason_code": "SERVICE_ADMIN_CRITICAL",
            },
        }
        result = validate_report(report)
        assert result["valid"] is True
        asa_warnings = [w for w in result["warnings"] if "action_specific_approval" in w]
        assert len(asa_warnings) == 0


class TestSchemaSelfCheck:
    """T-14: report schema self-check still passes."""

    def test_self_check(self):
        result = schema_self_check()
        assert result["overall"] == "PASS"
