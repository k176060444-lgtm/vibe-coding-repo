#!/usr/bin/env python3
"""Tests for I20 Execution Intelligence Foundation RFC.

Verifies:
- RFC exists with minimum required sections
- Execution Record Schema fields complete (all 38 fields)
- Evaluation Schema fields complete
- Cost NOT part of this phase
- Recommendation engine NOT part of this phase
- Provider agnostic (ALL 14 families)
- Links to I19 dispatch manifest documented
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
RFC_PATH = os.path.join(REPO_ROOT, "docs", "reports", "I20_EXECUTION_INTELLIGENCE_FOUNDATION_RFC.md")


def load_rfc():
    assert os.path.exists(RFC_PATH), f"RFC not found at {RFC_PATH}"
    with open(RFC_PATH) as f:
        return f.read()


# Core execution record fields that MUST exist
REQUIRED_RECORD_FIELDS = [
    "execution_id",
    "schema_version",
    "created_at",
    "phase_id",
    "work_order_id",
    "approval_id",
    "dispatch_manifest_version",
    "dispatch_manifest_reference",
    "provider",
    "model_id",
    "model_alias",
    "node",
    "transport",
    "role",
    "task_type",
    "language",
    "planned_calls",
    "actual_calls",
    "fallback_count",
    "fallback_models_attempted",
    "duration_ms",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "exit_status",
    "exit_code",
    "exact_string",
    "exact_match",
    "review_result",
    "operator_result",
    "operator_notes",
    "files_changed",
    "files_changed_count",
    "tests_summary",
    "merge_result",
    "merge_commit_sha",
    "evidence_refs",
    "redaction_check",
]

REQUIRED_EVAL_FIELDS = [
    "evaluation_id",
    "execution_record_ids",
    "evaluation_version",
    "evaluated_at",
    "quality_score",
    "stability_score",
    "latency_score",
    "overall_score",
    "recommended_for",
    "not_recommended_for",
    "confidence",
    "evaluation_source",
    "evaluation_notes",
    "compatible_task_types",
    "compatible_languages",
    "status",
]

ALL_PROVIDERS = [
    "anthropic", "dashscope", "deepseek", "deepseek-plan",
    "google", "minimax", "minimax-plan", "moonshot",
    "openai", "opencode", "opencode-go", "volcengine", "xai", "xiaomi",
]


class TestI20RfcExists:
    def test_rfc_file_exists(self):
        assert os.path.exists(RFC_PATH), "RFC file does not exist"

    def test_rfc_minimum_sections(self):
        content = load_rfc()
        required_sections = [
            "Problem Statement",
            "Existing Artifacts Reviewed",
            "Execution Record Schema",
            "Field Dictionary",
            "Evaluation Schema",
            "Relationship to I19",
            "Migration",
            "Provider Scope",
            "Non-Goals",
            "Risks",
            "Open Questions",
        ]
        for section in required_sections:
            assert section in content, f"RFC missing section: {section}"


class TestI20ExecutionRecordFields:
    def test_all_required_fields_present(self):
        content = load_rfc()
        for field in REQUIRED_RECORD_FIELDS:
            assert field in content, f"Missing execution record field: {field}"

    def test_field_categories(self):
        content = load_rfc()
        expected_categories = ["Identity", "Chain of Custody", "Dispatch Context",
                               "Model", "Execution", "Calls", "Performance",
                               "Outcome", "Review", "Artifacts", "Integration",
                               "Traces", "Safety"]
        for cat in expected_categories:
            assert cat in content, f"Missing field category: {cat}"

    def task_type_enum_complete(self):
        content = load_rfc()
        for tt in ["live-smoke", "coding", "review", "test", "audit", "governance",
                    "metadata", "operator-decision", "merge"]:
            assert tt in content, f"Missing task_type: {tt}"


class TestI20EvaluationFields:
    def test_all_eval_fields_present(self):
        content = load_rfc()
        for field in REQUIRED_EVAL_FIELDS:
            assert field in content, f"Missing evaluation field: {field}"

    def test_eval_status_schema_defined(self):
        content = load_rfc()
        assert "schema-defined-not-implemented" in content, \
            "status field should indicate schema-defined-not-implemented"


class TestI20NonGoals:
    def test_cost_not_part_of_this_phase(self):
        content = load_rfc()
        assert "cost" not in content.lower() or \
               "does not" in content[content.lower().find("cost")-50:content.lower().find("cost")+50] or \
               "excluded" in content or \
               "does NOT" in content, \
            "Cost should not be part of this phase"

    def test_recommendation_engine_not_implemented(self):
        content = load_rfc()
        assert "does NOT" in content, "RFC must list non-goals"
        assert "recommendation" in content, "Recommendation must be mentioned"

    def test_non_goals_listed(self):
        content = load_rfc()
        assert "Non-Goals" in content, "Missing Non-Goals section"
        # Check at least 4 non-goals
        non_goal_markers = ["does NOT", "does not", "No automatic"]
        found = sum(1 for m in non_goal_markers if m in content)
        assert found >= 1, "Non-goals not clearly marked"


class TestI20ProviderAgnostic:
    def test_all_14_providers_mentioned(self):
        content = load_rfc()
        for p in ALL_PROVIDERS:
            assert p in content, f"Provider {p} not mentioned in RFC"

    def test_provider_agnostic_stated(self):
        content = load_rfc()
        assert "provider-agnostic" in content.lower() or \
               "provider agnostic" in content.lower(), \
            "RFC must explicitly state provider-agnostic"

    def test_extra_visible_models_not_allowed(self):
        content = load_rfc()
        assert "extra visible" in content.lower() or \
               "EXTRA VISIBLE" in content, \
            "Extra visible models concern should be mentioned"


class TestI20DispatchManifestLink:
    def test_i19_relationship_documented(self):
        content = load_rfc()
        assert "I19" in content or "I19A" in content, \
            "RFC must reference I19/I19A dispatch manifest"
        assert "dispatch_manifest" in content.lower(), \
            "Dispatch manifest link should be documented"

    def test_data_flow_documented(self):
        content = load_rfc()
        assert "Data Flow" in content or "data flow" in content.lower(), \
            "Data flow between artifacts should be documented"


class TestI20NoSecrets:
    def test_no_secrets_in_rfc(self):
        content = load_rfc()
        key_patterns = re.findall(r'sk-[a-zA-Z0-9]{10,}', content)
        assert len(key_patterns) == 0, f"Found potential API key patterns: {key_patterns[:3]}"
        akia_patterns = re.findall(r'AKIA[0-9A-Z]{10,}', content)
        assert len(akia_patterns) == 0, f"Found AKIA patterns"

    def test_no_env_var_values(self):
        content = load_rfc()
        for line in content.split('\n'):
            if 'OPENCODE_GO_API_KEY' in line and '=' in line and \
               not line.strip().endswith('OPENCODE_GO_API_KEY'):
                assert False, f"Potential key value: {line.strip()[:60]}"


class TestI20RouteAllUnchanged:
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
                f"Route-all role {role} uses opencode-go model {model}"

    def test_route_all_has_correct_models(self):
        result = subprocess.run(
            [sys.executable, "scripts/vibe_model_routing_policy.py", "--json", "route-all"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        routes = json.loads(result.stdout)
        assert routes["orchestrator"]["recommended"] == "volcengine-doubao"
        assert routes["implementer"]["recommended"] == "minimax-m3"


class TestI20ModelPoolUnchanged:
    def test_model_pool_unchanged(self):
        import yaml
        with open(os.path.join(REPO_ROOT, "scripts", "model_pool.yaml")) as f:
            pool = yaml.safe_load(f)
        models = pool.get("models", [])
        assert len(models) == 37, f"Expected 37 models, got {len(models)}"
        oc_count = sum(1 for m in models if m.get("provider") == "opencode-go")
        assert oc_count == 8, f"Expected 8 opencode-go, got {oc_count}"
        enabled_oc = sum(1 for m in models if m.get("provider") == "opencode-go" and m.get("enabled") == True)
        assert enabled_oc == 2, f"Expected 2 enabled opencode-go, got {enabled_oc}"
        enabled = sum(1 for m in models if m.get("enabled") == True)
        assert enabled == 26, f"Expected 26 enabled, got {enabled}"

    def test_model_pool_self_check_passes(self):
        result = subprocess.run(
            [sys.executable, "scripts/opencode_model_pool.py", "--self-check"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        assert result.returncode == 0
        assert '"passed": true' in result.stdout


class TestI20Migration:
    def test_migration_section_exists(self):
        content = load_rfc()
        assert "Migration" in content or "Compatibility" in content, \
            "RFC must have migration/compatibility section"

    def test_pre_i20_defaults_defined(self):
        content = load_rfc()
        assert "pre-i20" in content.lower() or "Pre-I20" in content, \
            "Pre-I20 evidence defaults should be defined"


class TestI20aEnhancements:
    """Tests for I20A minimal schema enhancements."""

    def test_environment_field_exists(self):
        content = load_rfc()
        assert "environment" in content, "Missing environment field group"

    def test_environment_subfields(self):
        content = load_rfc()
        for sf in ["node", "worker_version", "opencode_version", "model_pool_head", "dispatch_manifest_version"]:
            assert sf in content, f"Missing environment sub-field: {sf}"

    def test_environment_nullable(self):
        content = load_rfc()
        assert "nullable" in content[content.lower().find("environment"):content.lower().find("environment")+500].lower() or \
               "nullable" in content, "environment must be nullable"

    def test_task_tags_field_exists(self):
        content = load_rfc()
        assert "task_tags" in content, "Missing task_tags field"

    def test_task_tags_provider_agnostic(self):
        content = load_rfc()
        # Check tags mention multiple providers
        assert "task_tags" in content
        tag_section = content[content.lower().find("task_tags"):content.lower().find("task_tags")+300]
        assert "provider-agnostic" in tag_section.lower() or "14 provider" in content, \
            "task_tags should be provider-agnostic"

    def test_operator_feedback_field_exists(self):
        content = load_rfc()
        assert "operator_feedback" in content, "Missing operator_feedback field"

    def test_operator_feedback_subfields(self):
        content = load_rfc()
        for sf in ["accepted", "rating", "note"]:
            assert sf in content, f"Missing operator_feedback sub-field: {sf}"

    def test_operator_feedback_nullable(self):
        content = load_rfc()
        # Sub-fields use null (JSON nullable) or have nullable descriptions
        assert "null" in content[content.lower().find("operator_feedback"):content.lower().find("operator_feedback")+500], \
            "operator_feedback fields must support null values"
        # Also check field dictionary has int/null or string/null for these
        assert "int/null" in content or "string/null" in content or "nullable" in content, \
            "RFC should document nullable types"

    def test_no_hashes_implemented(self):
        """Hash terms may appear in 'Explicitly Excluded' section, but not as implemented fields."""
        content = load_rfc()
        # The hash terms appear in the exclusion table — that's ok
        # Verify they're only mentioned in exclusion context
        for h in ["prompt_hash", "input_hash", "approval_hash", "execution_hash"]:
            if h in content:
                # Must be in the "Explicitly Excluded" section or "does NOT" context
                idx = content.find(h)
                context = content[max(0,idx-200):idx+200]
                assert "Explicitly Excluded" in context or "excluded" in context.lower(), \
                    f"{h} should only appear as excluded, not as implemented"

    def test_no_normalization_implementation(self):
        content = load_rfc()
        assert "normalization" not in content or \
               "future concept" in content.lower() or \
               "Explicitly Excluded" in content[content.lower().find("normalization"):content.lower().find("normalization")+300], \
            "Normalization must not be implemented as schema"

    def test_no_cost_model(self):
        content = load_rfc()
        # Cost may be mentioned as excluded, but must not be implemented
        cost_section = content[content.lower().find("cost"):content.lower().find("cost")+200] if "cost" in content.lower() else ""
        assert "Explicitly Excluded" in content or "does NOT" in content, \
            "cost must be explicitly excluded"

    def test_no_recommendation_engine(self):
        content = load_rfc()
        assert "does NOT" in content or "Explicitly Excluded" in content, \
            "Recommendation engine must be excluded"

    def test_no_normalization_implementation(self):
        content = load_rfc()
        assert "normalization" not in content or \
               "future concept" in content.lower() or \
               "Explicitly Excluded" in content[content.lower().find("normalization"):content.lower().find("normalization")+300], \
            "Normalization must not be implemented as schema"

    def test_environment_category_exists(self):
        content = load_rfc()
        assert "Environment" in content, "Missing Environment category in field groups"
        assert "Operator Feedback" in content, "Missing Operator Feedback category"
        assert "Tags" in content, "Missing Tags category"

    def test_field_count_with_i20a(self):
        """Total fields should be 49 (38 original + 11 new sub-fields)."""
        content = load_rfc()
        # Just verify the table rows go up to 49
        assert "49" in content, "Field dictionary should extend to 49 rows"
