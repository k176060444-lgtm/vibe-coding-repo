#!/usr/bin/env python3
"""Tests for I21 Gray Usage Issue Backlog.

Verifies:
- Backlog document exists and has required sections
- All issues have required fields (issue_id, title, description, severity, etc.)
- Severity values are valid
- Category sections exist
- No real secrets in backlog
- Route-all unchanged
- Model pool unchanged
"""

import os
import re
import json
import subprocess
import sys

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
BACKLOG_PATH = os.path.join(REPO_ROOT, "docs", "reports", "I21_GRAY_USAGE_BACKLOG.md")


def load_backlog():
    assert os.path.exists(BACKLOG_PATH), f"Backlog not found at {BACKLOG_PATH}"
    with open(BACKLOG_PATH, encoding="utf-8") as f:
        return f.read()


# ── Document Structure Tests ──────────────────────────────────────

class TestBacklogExists:
    def test_backlog_file_exists(self):
        assert os.path.exists(BACKLOG_PATH), "Backlog document does not exist"

    def test_backlog_minimum_sections(self):
        content = load_backlog()
        required_sections = [
            "Executive Summary",
            "Issue Catalog",
            "Priority Matrix",
            "Recommended Fix Order",
            "Technical Debt Summary",
            "Future Enhancement Summary",
            "Backlog Maintenance",
        ]
        for section in required_sections:
            assert section in content, f"Missing required section: {section}"

    def test_backlog_has_category_sections(self):
        content = load_backlog()
        categories = [
            "Architecture",
            "Worker / Registry",
            "Dispatch",
            "Model Pool",
            "Runtime Sync",
            "OpenCode Runtime",
            "Git / PR Workflow",
            "Windows Compatibility",
            "Reporting",
            "Test Infrastructure",
            "Documentation",
        ]
        for cat in categories:
            # Check for category heading or mention in Issue Catalog
            assert cat in content or cat.replace(" / ", "/") in content, \
                f"Missing category section: {cat}"

    def test_backlog_no_real_secrets(self):
        content = load_backlog()
        patterns = [
            r'sk-[a-zA-Z0-9]{20,}',
            r'sk-ant-[a-zA-Z0-9]{20,}',
            r'AIza[0-9A-Za-z_-]{35}',
            r'ghp_[a-zA-Z0-9]{36}',
            r'-----BEGIN.*PRIVATE KEY-----',
        ]
        for pat in patterns:
            assert not re.search(pat, content), f"Secret pattern found: {pat}"


class TestBacklogIssueFields:
    """Verify all issues have required fields and valid values."""

    def _extract_issues(self):
        """Extract issue blocks from backlog markdown."""
        content = load_backlog()
        issues = []
        # Find all issue tables — each starts with | issue_id |
        # Format: | Field | Value | ... | issue_id | XYZ-001 |
        issue_blocks = re.findall(
            r'\|\s*\*\*issue_id\*\*\s*\|\s*(\S+)\s*\|\n'
            r'\|\s*\*\*title\*\*\s*\|\s*(.+?)\s*\|\n'
            r'\|\s*\*\*description\*\*\s*\|\s*(.+?)\s*\|\n'
            r'\|\s*\*\*current_status\*\*\s*\|\s*(.+?)\s*\|\n'
            r'\|\s*\*\*severity\*\*\s*\|\s*(.+?)\s*\|\n'
            r'\|\s*\*\*reproducibility\*\*\s*\|\s*(.+?)\s*\|\n'
            r'\|\s*\*\*affected_phase\*\*\s*\|\s*(.+?)\s*\|\n'
            r'\|\s*\*\*proposed_fix_phase\*\*\s*\|\s*(.+?)\s*\|\n'
            r'\|\s*\*\*requires_model_call\*\*\s*\|\s*(.+?)\s*\|\n'
            r'\|\s*\*\*requires_node_change\*\*\s*\|\s*(.+?)\s*\|\n',
            content,
            re.DOTALL
        )
        for match in issue_blocks:
            issues.append({
                "issue_id": match[0].strip(),
                "title": match[1].strip(),
                "description": match[2].strip(),
                "current_status": match[3].strip(),
                "severity": match[4].strip(),
                "reproducibility": match[5].strip(),
                "affected_phase": match[6].strip(),
                "proposed_fix_phase": match[7].strip(),
                "requires_model_call": match[8].strip().lower(),
                "requires_node_change": match[9].strip().lower(),
            })
        return issues

    def test_issues_have_required_fields(self):
        issues = self._extract_issues()
        assert len(issues) >= 20, f"Too few issues extracted ({len(issues)} < 20)"

    def test_issue_ids_format(self):
        issues = self._extract_issues()
        for iss in issues:
            assert re.match(r'^[A-Z]+-\d{3}$', iss["issue_id"]), \
                f"Invalid issue_id format: {iss['issue_id']}"

    def test_severity_values_valid(self):
        issues = self._extract_issues()
        valid = {"blocker", "high", "medium", "low"}
        for iss in issues:
            assert iss["severity"] in valid, \
                f"Invalid severity '{iss['severity']}' for {iss['issue_id']}"

    def test_status_values_valid(self):
        issues = self._extract_issues()
        valid = {"known", "open", "verified"}
        for iss in issues:
            assert iss["current_status"] in valid, \
                f"Invalid status '{iss['current_status']}' for {iss['issue_id']}"

    def test_requires_model_call_yes_no(self):
        issues = self._extract_issues()
        for iss in issues:
            assert iss["requires_model_call"] in ("yes", "no") or \
                iss["requires_model_call"].startswith("yes") or \
                iss["requires_model_call"].startswith("no"), \
                f"{iss['issue_id']}: requires_model_call='{iss['requires_model_call']}'"

    def test_requires_node_change_yes_no(self):
        issues = self._extract_issues()
        for iss in issues:
            assert iss["requires_node_change"] in ("yes", "no") or \
                iss["requires_node_change"].startswith("yes") or \
                iss["requires_node_change"].startswith("no"), \
                f"{iss['issue_id']}: requires_node_change='{iss['requires_node_change']}'"

    def test_all_categories_covered(self):
        issues = self._extract_issues()
        ids = [i["issue_id"] for i in issues]
        # Check category prefixes
        expected_prefixes = {
            "ARCH", "WRKR", "DSP", "POOL", "RSYNC", "OCR",
            "GIT", "WIN", "RPT", "TEST", "DOC",
        }
        found_prefixes = set()
        for iid in ids:
            prefix = iid.split("-")[0]
            if prefix != "ENH":
                found_prefixes.add(prefix)
        missing = expected_prefixes - found_prefixes
        assert not missing, f"Missing issue category prefixes: {missing}"


class TestBacklogPriorityMatrix:
    def test_blocker_count(self):
        content = load_backlog()
        # Find the Priority Matrix section and count blockers
        issues = re.findall(r'\|\s*\*\*severity\*\*\s*\|\s*(blocker)', content, re.IGNORECASE)
        assert len(issues) >= 2, f"Expected at least 2 blockers, found {len(issues)}"

    def test_fix_order_phases(self):
        content = load_backlog()
        # Check that phases I22-I25 are mentioned in fix order
        for phase in ["I22", "I23", "I24", "I25"]:
            assert f"**{phase}**" in content, f"Fix order phase {phase} not found"


class TestBacklogNoChanges:
    """I21 must not change route-all or model pool."""

    def test_route_all_unchanged(self):
        result = subprocess.run(
            [sys.executable, "scripts/vibe_model_routing_policy.py", "--json", "route-all"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        assert result.returncode == 0, f"route-all failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert len(data) == 9, f"Expected 9 route-all roles, got {len(data)}"

    def test_model_pool_unchanged(self):
        result = subprocess.run(
            [sys.executable, "scripts/opencode_model_pool.py", "--self-check"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        assert result.returncode == 0, f"model_pool self-check failed: {result.stderr}"
        data = json.loads(result.stdout)
        assert data["passed"], "model_pool self-check did not pass"
        assert data["passed_count"] >= 129, \
            f"Expected >=129 model_pool checks, got {data['passed_count']}"


class TestBacklogSecretSafety:
    def test_backlog_no_env_var_values(self):
        content = load_backlog()
        # Check that no real env var values are written
        lines = content.split("\n")
        for line in lines:
            # Allow env var NAMES but not values
            if "OPENCODE_GO_API_KEY" in line:
                # Check this is a reference, not a value assignment
                assert "REDACTED" not in line  # Should not show REDACTED
            if "=" in line and "key" in line.lower():
                val = line.split("=", 1)[1].strip()
                if val and val not in ["yes", "no", '""', "?", "present", "reference"]:
                    # This should not be a real key value
                    if re.match(r'^[A-Za-z0-9+/]{10,}$', val):
                        assert False, f"Potential secret value in backlog: {line.strip()}"
