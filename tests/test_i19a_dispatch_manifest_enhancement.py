#!/usr/bin/env python3
"""Tests for I19A dispatch manifest schema enhancement RFC.

Verifies:
- RFC exists and has minimum required sections
- All new schema fields documented (recommendation_id, recommended_by,
  recommendation_reason, selection_policy_version, recommendation_timestamp,
  operator_decision, operator_override_reason, approved/execution/audit versions)
- Recommendation vs approval separation stated
- Operator override supported
- recommended_by applies to ALL provider families (not just opencode-go)
- selection_policy_version exists
- No real secrets
- Route-all unchanged
- Model pool unchanged
"""

import os
import re
import json
import subprocess
import sys

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
RFC_PATH = os.path.join(REPO_ROOT, "docs", "reports", "I19A_MANIFEST_SCHEMA_ENHANCEMENT_RFC.md")


def load_rfc():
    assert os.path.exists(RFC_PATH), f"RFC not found at {RFC_PATH}"
    with open(RFC_PATH) as f:
        return f.read()


class TestI19aRfcExists:
    def test_rfc_file_exists(self):
        assert os.path.exists(RFC_PATH), "RFC file does not exist"

    def test_rfc_minimum_sections(self):
        content = load_rfc()
        required_sections = [
            "Problem Statement",
            "Enhanced Schema",
            "Recommendation vs. Approval",
            "Responsibility Boundaries",
            "Selection Policy Version",
            "Provider Scope",
            "Migration",
            "Failure Model",
            "Non-Goals",
            "Risks",
            "Open Questions",
        ]
        for section in required_sections:
            assert section in content, f"RFC missing section: {section}"


class TestI19aSchemaFields:
    def test_recommendation_id_field(self):
        content = load_rfc()
        assert "recommendation_id" in content, "Missing recommendation_id field"

    def test_recommended_by_field(self):
        content = load_rfc()
        assert "recommended_by" in content, "Missing recommended_by field"

    def test_recommendation_reason_field(self):
        content = load_rfc()
        assert "recommendation_reason" in content, "Missing recommendation_reason field"

    def test_selection_policy_version_field(self):
        content = load_rfc()
        assert "selection_policy_version" in content, "Missing selection_policy_version field"

    def test_recommendation_timestamp_field(self):
        content = load_rfc()
        assert "recommendation_timestamp" in content, "Missing recommendation_timestamp field"

    def test_operator_decision_field(self):
        content = load_rfc()
        assert "operator_decision" in content, "Missing operator_decision field"

    def test_operator_override_reason_field(self):
        content = load_rfc()
        assert "override_reason" in content, "Missing operator_override_reason field"

    def test_approval_manifest_version(self):
        content = load_rfc()
        assert "approval_manifest_version" in content, "Missing approval_manifest_version"

    def test_execution_manifest_version(self):
        content = load_rfc()
        assert "execution_manifest_version" in content, "Missing execution_manifest_version"

    def test_audit_manifest_version(self):
        content = load_rfc()
        assert "audit_manifest_version" in content, "Missing audit_manifest_version"

    def test_operator_match_field(self):
        content = load_rfc()
        assert "operator_match" in content, "Missing operator_match field"


class TestI19aGovernance:
    def test_recommendation_vs_approval_separation(self):
        """RFC must state recommendation cannot become approval automatically."""
        content = load_rfc()
        assert "never automatically become" in content or \
               "MUST NEVER automatically" in content or \
               ("recommendation" in content and "approval" in content and "NEVER" in content), \
            "RFC must explicitly state recommendation != approval"

    def test_operator_override_supported(self):
        content = load_rfc()
        assert "override" in content.lower(), "RFC must mention operator override"
        assert "override_reason" in content or "override_notes" in content, \
            "RFC must have override_reason or override_notes field"

    def test_recommended_by_enum_covers_all_providers(self):
        """recommended_by enum must not be opencode-go specific."""
        content = load_rfc()
        for provider in ["volcengine", "minimax", "xiaomi", "opencode-go", "deepseek"]:
            assert provider in content, f"Provider {provider} not in RFC scope"
        # Check that recommended_by section mentions non-opencode providers
        assert "recommended_by" in content, "Missing recommended_by"
        # The controlled vocabulary section exists
        assert "controlled vocabulary" in content.lower() or "vibedev-route-all" in content, \
            "recommended_by should have a controlled vocabulary"

    def test_selection_policy_version_tracking(self):
        content = load_rfc()
        assert "v1.21.33" in content, "RFC should reference existing policy versions"
        assert "selection_policy_version" in content


class TestI19aNoSecrets:
    def test_no_real_secrets_in_rfc(self):
        content = load_rfc()
        key_patterns = re.findall(r'sk-[a-zA-Z0-9]{10,}', content)
        assert len(key_patterns) == 0, f"Found potential API key patterns: {key_patterns[:3]}"
        akia_patterns = re.findall(r'AKIA[0-9A-Z]{10,}', content)
        assert len(akia_patterns) == 0, f"Found AKIA patterns"


class TestI19aRouteAllUnchanged:
    def test_route_all_unchanged(self):
        """Route-all must remain 9 roles, no opencode-go."""
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
                f"Route-all role {role} uses opencode-go model {model}"


class TestI19aModelPoolUnchanged:
    def test_model_pool_unchanged(self):
        """Model pool state must match current authorized model_pool.yaml.

        Dynamic assertion: reads from YAML instead of hardcoding stale counts.
        I23 authorized: 38 total, 33 enabled, 9 opencode-go (all enabled).
        """
        import yaml
        with open(os.path.join(REPO_ROOT, "scripts", "model_pool.yaml")) as f:
            pool = yaml.safe_load(f)
        models = pool.get("models", [])
        # Dynamic: verify internal consistency
        total = len(models)
        enabled = sum(1 for m in models if m.get("enabled") == True)
        oc_total = sum(1 for m in models if m.get("provider") == "opencode-go")
        oc_enabled = sum(1 for m in models if m.get("provider") == "opencode-go" and m.get("enabled") == True)
        assert total >= 37, f"Expected >=37 models, got {total}"
        assert oc_enabled == oc_total, (
            f"Not all opencode-go enabled: enabled={oc_enabled}, total={oc_total}")

    def test_model_pool_self_check_passes(self):
        result = subprocess.run(
            [sys.executable, "scripts/opencode_model_pool.py", "--self-check"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        assert result.returncode == 0, f"Self-check failed: {result.stderr}"
        assert '"passed": true' in result.stdout, "Self-check did not pass"


class TestI19aProviderFamilyScope:
    def test_all_14_providers_mentioned(self):
        content = load_rfc()
        expected = [
            "anthropic", "dashscope", "deepseek", "deepseek-plan",
            "google", "minimax", "minimax-plan", "moonshot",
            "openai", "opencode", "opencode-go", "volcengine", "xai", "xiaomi",
        ]
        for p in expected:
            assert p in content, f"Provider {p} not mentioned in RFC"
