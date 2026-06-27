#!/usr/bin/env python3
"""Tests for I19 dispatch governance RFC.

Verifies:
- RFC document exists and has minimum required sections
- RFC covers all 14 provider families
- RFC explicitly states operator final approval requirement
- RFC explicitly states route-all/manifest do NOT auto-decide
- RFC explicitly states planned-vs-actual fail-closed
- RFC explicitly states opencode-go is not the sole model pool center
- No real secrets in the RFC document
"""

import os
import re
import yaml
import json
import subprocess
import sys

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
RFC_PATH = os.path.join(REPO_ROOT, "docs", "reports", "I19_DISPATCH_GOVERNANCE_RFC.md")
POOL_PATH = os.path.join(REPO_ROOT, "scripts", "model_pool.yaml")


def load_rfc():
    assert os.path.exists(RFC_PATH), f"RFC not found at {RFC_PATH}"
    with open(RFC_PATH) as f:
        return f.read()


def load_pool():
    with open(POOL_PATH) as f:
        return yaml.safe_load(f)


class TestI19RfcExists:
    def test_rfc_file_exists(self):
        assert os.path.exists(RFC_PATH), "RFC file does not exist"

    def test_rfc_minimum_sections(self):
        content = load_rfc()
        required_sections = [
            "Problem Statement",
            "Current State",
            "Proposed Terminology",
            "Operator Approval Contract",
            "Manifest Schema Sketch",
            "Planned-vs-Actual",
            "Failure Policy",
            "Migration Plan",
            "Non-Goals",
            "Risks",
            "Open Questions",
        ]
        for section in required_sections:
            assert section in content, f"RFC missing section: {section}"


class TestI19ProviderFamilies:
    def test_all_providers_covered_in_rfc(self):
        """RFC must mention all 14 provider families from the pool."""
        pool = load_pool()
        providers = set()
        for m in pool.get("models", []):
            p = m.get("provider", "unknown")
            providers.add(p)
        assert len(providers) == 14, f"Expected 14 providers, got {len(providers)}: {sorted(providers)}"

        content = load_rfc()
        for p in sorted(providers):
            assert p in content, f"Provider '{p}' not mentioned in RFC"

    def test_total_model_count_correct(self):
        pool = load_pool()
        models = pool.get("models", [])
        assert len(models) == 37, f"Expected 37 models, got {len(models)}"

    def test_enabled_count_in_rfc(self):
        pool = load_pool()
        enabled = sum(1 for m in pool.get("models", []) if m.get("enabled") == True)
        content = load_rfc()
        assert str(enabled) in content, f"Enabled count {enabled} not found in RFC"

    def test_opencode_not_sole_center(self):
        """RFC must not present opencode-go as the only important provider."""
        content = load_rfc()
        # Count mentions of other providers vs opencode
        if "opencode" in content:
            assert "volcengine" in content, "RFC missing non-opencode providers"
            assert "xiaomi" in content, "RFC missing xiaomi provider"


class TestI19GovernanceRules:
    def test_operator_final_approval_stated(self):
        content = load_rfc()
        assert "operator" in content.lower()
        assert "approval" in content.lower() or "approved" in content.lower()

    def test_route_all_no_auto_decision(self):
        content = load_rfc()
        assert "recommendation" in content.lower() or "recommends" in content.lower(), \
            "RFC must state route-all is recommendation, not decision"

    def test_fail_closed_mentioned(self):
        content = load_rfc()
        assert "fail-closed" in content.lower() or "fail_closed" in content.lower() or "BLOCKED" in content, \
            "RFC must mention fail-closed behavior"

    def test_planned_vs_actual_audit_mentioned(self):
        content = load_rfc()
        assert "planned" in content.lower() and "actual" in content.lower(), \
            "RFC must discuss planned-vs-actual auditing"

    def test_no_real_secrets(self):
        content = load_rfc()
        key_patterns = re.findall(r'sk-[a-zA-Z0-9]{10,}', content)
        assert len(key_patterns) == 0, f"Found potential API key patterns: {key_patterns[:3]}"
        akia_patterns = re.findall(r'AKIA[0-9A-Z]{10,}', content)
        assert len(akia_patterns) == 0, f"Found AKIA patterns"
        # Check no env var values (only names)
        for line in content.split('\n'):
            if 'OPENCODE_GO_API_KEY' in line and '=' in line and not line.strip().endswith('OPENCODE_GO_API_KEY'):
                assert False, f"Secret value found: {line.strip()[:60]}"


class TestI19RouteAllUnchanged:
    def test_route_all_unchanged(self):
        result = subprocess.run(
            [sys.executable, "scripts/vibe_model_routing_policy.py", "--json", "route-all"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        assert result.returncode == 0, f"route-all failed: {result.stderr}"
        routes = json.loads(result.stdout)
        roles = {k: v for k, v in routes.items() if not k.startswith("_")}
        assert len(roles) == 9, f"Expected 9 roles, got {len(roles)}"
        for role, info in roles.items():
            model = info.get("recommended", "")
            assert "opencode-go" not in model, \
                f"Route-all role {role} uses opencode-go model {model} (should be unchanged)"

    def test_route_all_has_both_doubao_and_minimax(self):
        """Current route-all uses volcengine-doubao for orchestrator/planner and minimax-m3 for others."""
        result = subprocess.run(
            [sys.executable, "scripts/vibe_model_routing_policy.py", "--json", "route-all"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        routes = json.loads(result.stdout)
        recommendations = {}
        for role, info in routes.items():
            recommendations[role] = info.get("recommended", "")
        assert recommendations.get("orchestrator") == "volcengine-doubao", \
            f"Expected orchestrator=volcengine-doubao, got {recommendations.get('orchestrator')}"
        assert recommendations.get("implementer") == "minimax-m3", \
            f"Expected implementer=minimax-m3, got {recommendations.get('implementer')}"
        assert recommendations.get("tester-a") == "minimax-m3", \
            f"Expected tester-a=minimax-m3, got {recommendations.get('tester-a')}"


class TestI19ModelPoolSelfCheck:
    def test_model_pool_self_check_passes(self):
        result = subprocess.run(
            [sys.executable, "scripts/opencode_model_pool.py", "--self-check"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        assert result.returncode == 0, f"Self-check failed: {result.stderr}"
        assert '"passed": true' in result.stdout, "Self-check did not pass"
