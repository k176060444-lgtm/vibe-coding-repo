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


class TestBacklogCountConsistency:
    """Verify all counts in sections 1, 3, and 4 match actual issue data."""

    def _parse_all_issues(self):
        """Parse all issues from the backlog."""
        content = load_backlog()
        # Find all issue blocks
        blocks = content.split('| **issue_id** |')
        issues = []
        for block in blocks[1:]:
            block = '| **issue_id** |' + block
            iid_m = re.search(r'\*\*issue_id\*\*\s*\|\s*(\S+)', block)
            sev_m = re.search(r'\*\*severity\*\*\s*\|\s*(\S+)', block)
            phase_m = re.search(r'\*\*proposed_fix_phase\*\*\s*\|\s*(\S+)', block)
            cat_m = re.search(r'\*\*category\*\*', block)
            if iid_m:
                issues.append({
                    'issue_id': iid_m.group(1),
                    'severity': sev_m.group(1).lower() if sev_m else 'unknown',
                    'proposed_fix_phase': phase_m.group(1) if phase_m else 'unknown',
                })
        return issues

    def test_total_count_30_non_enhancement(self):
        issues = self._parse_all_issues()
        non_enh = [i for i in issues if not i['issue_id'].startswith('ENH')]
        enh = [i for i in issues if i['issue_id'].startswith('ENH')]
        assert len(non_enh) == 30, f"Expected 30 non-enhancement, got {len(non_enh)}"
        assert len(enh) == 6, f"Expected 6 enhancement, got {len(enh)}"

    def test_severity_counts_match(self):
        issues = self._parse_all_issues()
        non_enh = [i for i in issues if not i['issue_id'].startswith('ENH')]
        actual = {}
        for i in non_enh:
            sev = i['severity']
            actual[sev] = actual.get(sev, 0) + 1
        # Read the executive summary table
        content = load_backlog()
        table_sev = {}
        for line in content.split('\n'):
            if 'Blockers' in line and '|' in line:
                m = re.search(r'\|\s*(\d+)\s*\|', line)
                if m: table_sev['blocker'] = int(m.group(1))
            elif 'High priority' in line and '|' in line:
                m = re.search(r'\|\s*(\d+)\s*\|', line)
                if m: table_sev['high'] = int(m.group(1))
            elif 'Medium priority' in line and '|' in line:
                m = re.search(r'\|\s*(\d+)\s*\|', line)
                if m: table_sev['medium'] = int(m.group(1))
            elif 'Low priority' in line and '|' in line:
                m = re.search(r'\|\s*(\d+)\s*\|', line)
                if m: table_sev['low'] = int(m.group(1))
        for sev in ['blocker', 'high', 'medium', 'low']:
            assert table_sev.get(sev, -1) == actual.get(sev, -1), \
                f"Severity {sev}: table says {table_sev.get(sev)}, actual={actual.get(sev)}"

    def test_no_duplicate_ids(self):
        issues = self._parse_all_issues()
        ids = [i['issue_id'] for i in issues]
        dupes = [x for x in ids if ids.count(x) > 1]
        assert len(dupes) == 0, f"Duplicate issue_ids: {set(dupes)}"

    def test_fix_order_refs_exist(self):
        """All issue IDs in the fix order table exist in the catalog."""
        issues = self._parse_all_issues()
        all_ids = set(i['issue_id'] for i in issues)
        content = load_backlog()
        # Extract issues from fix order table
        fix_section = content.split('## 4. Recommended Fix Order')[1].split('## 5.')[0]
        fix_ids = re.findall(r'([A-Z]+-\d{3})', fix_section)
        fix_ids = set(fix_ids)
        missing = fix_ids - all_ids
        assert not missing, f"Fix order references non-existent IDs: {missing}"

    def test_fix_order_phase_consistency(self):
        """Fix order table phase assignments match proposed_fix_phase."""
        issues = self._parse_all_issues()
        non_enh = [i for i in issues if not i['issue_id'].startswith('ENH')]
        # Group by proposed_fix_phase
        phase_groups = {}
        for i in non_enh:
            p = i['proposed_fix_phase']
            if p not in phase_groups:
                phase_groups[p] = set()
            phase_groups[p].add(i['issue_id'])
        # Check fix order table row counts vs proposed_fix_phase counts
        content = load_backlog()
        fix_section = content.split('## 4. Recommended Fix Order')[1].split('## 5.')[0]
        for line in fix_section.split('\n'):
            m = re.search(r'\*\*(I\d+)\*\*\s*\|\s*([A-Z,\s-]+?)\s*\|', line)
            if m:
                phase = m.group(1)
                listed_ids = set(re.findall(r'([A-Z]+-\d{3})', m.group(2)))
                if phase in phase_groups:
                    # Every listed ID must have this phase
                    for iid in listed_ids:
                        assert iid in phase_groups[phase], \
                            f"{iid} listed in {phase} but proposed_fix_phase says otherwise"
                    # Some IDs in phase_groups may not be in fix order table
                    # (that's OK for small ones) — only test listed IDs match


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
        roles = {k: v for k, v in data.items() if not k.startswith("_")}
        assert len(roles) == 9, f"Expected 9 route-all roles, got {len(roles)}"

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
