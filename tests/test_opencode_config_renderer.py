#!/usr/bin/env python3
"""Tests for OpenCode Config Renderer — Dry-run Only.

Covers:
- dry_run=false rejection
- No plaintext keys in output
- secret_ref usage
- requires_operator_approval always True
- Available pool filtering (enabled + credential + health + quarantine + node detected)
- Non-available exclusion (disabled, missing credential, quarantined, not detected)
- OpenCode free conditional availability
- OpenCode Go conditional availability
- Node-specific config
- Role assignment mapping
- Empty available pool warning
- Audit input_hash stability
- Output conforms to contract schema
- Local dirt not in diff

Contract: docs/MODEL_POOL_DISTRIBUTION_CONTRACT.md §4
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from opencode_config_renderer import (
    DANGEROUS_KEY_PATTERNS,
    RENDERER_VERSION,
    filter_available_models,
    generate_config_draft,
    is_model_available,
    render_config,
    resolve_role_assignment,
    scan_output_for_secrets,
    self_check,
    validate_input,
)


# --- Fixtures ---


@pytest.fixture
def sample_models():
    """Sample model list for testing."""
    return [
        {
            "model_id": "opencode/mimo-v2.5-free",
            "provider": "opencode",
            "alias": "mimo-free",
            "endpoint": "https://api.opencode.example.com/v1",
            "protocol": "openai-compatible",
            "node_availability": {
                "21bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
                "5bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
                "9bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
            },
            "cost_tag": "free",
            "enabled": True,
            "health_status": "healthy",
            "quarantine_status": "none",
            "credential_status": "not-configured",
            "secret_ref": "secret:opencode:mimo-free-token",
            "source_flags": ["opencode-free"],
            "roles": ["implementer", "reviewer"],
            "priority": 1,
            "capability_tags": ["code", "chat"],
            "fallback_allowed": True,
        },
        {
            "model_id": "deepseek-plan/deepseek-v4-pro",
            "provider": "deepseek-plan",
            "alias": "ds-v4-pro",
            "endpoint": "https://api.deepseek.example.com/v1",
            "protocol": "openai-compatible",
            "node_availability": {
                "21bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
                "5bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
                "9bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
            },
            "cost_tag": "paid",
            "enabled": True,
            "health_status": "healthy",
            "quarantine_status": "none",
            "credential_status": "valid",
            "secret_ref": "secret:deepseek:api-key",
            "source_flags": ["user-configured"],
            "roles": ["implementer", "reviewer"],
            "priority": 2,
            "capability_tags": ["code", "chat", "reasoning"],
            "fallback_allowed": True,
        },
        {
            "model_id": "volcengine-plan/ark-code-latest",
            "provider": "volcengine-plan",
            "alias": "doubao",
            "endpoint": "https://api.volcengine.example.com/v1",
            "protocol": "openai-compatible",
            "node_availability": {
                "21bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
            },
            "cost_tag": "paid",
            "enabled": True,
            "health_status": "healthy",
            "quarantine_status": "quarantined",
            "credential_status": "valid",
            "secret_ref": "secret:volcengine:api-key",
            "source_flags": ["user-configured"],
            "roles": ["implementer"],
            "priority": 3,
            "capability_tags": ["code"],
            "fallback_allowed": False,
        },
    ]


@pytest.fixture
def disabled_model():
    """A disabled model."""
    return {
        "model_id": "opencode/nemotron-3-ultra-free",
        "provider": "opencode",
        "alias": "nemotron-free",
        "endpoint": "https://api.opencode.example.com/v1",
        "protocol": "openai-compatible",
        "node_availability": {
            "21bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
        },
        "cost_tag": "free",
        "enabled": False,
        "health_status": "healthy",
        "quarantine_status": "none",
        "credential_status": "not-configured",
        "secret_ref": "secret:opencode:nemotron-free-token",
        "source_flags": ["opencode-free"],
        "roles": ["implementer"],
        "priority": 4,
        "capability_tags": ["code"],
        "fallback_allowed": True,
    }


@pytest.fixture
def missing_credential_model():
    """A model with missing credentials."""
    return {
        "model_id": "xiaomi-plan/mimo-v2.5-pro",
        "provider": "xiaomi-plan",
        "alias": "mimo-pro",
        "endpoint": "https://api.xiaomi.example.com/v1",
        "protocol": "openai-compatible",
        "node_availability": {
            "21bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
        },
        "cost_tag": "paid",
        "enabled": True,
        "health_status": "healthy",
        "quarantine_status": "none",
        "credential_status": "missing",
        "secret_ref": "secret:xiaomi:api-key",
        "source_flags": ["user-configured"],
        "roles": ["implementer", "reviewer"],
        "priority": 5,
        "capability_tags": ["code", "chat"],
        "fallback_allowed": True,
    }


@pytest.fixture
def standard_input(sample_models):
    """Standard renderer input."""
    return {
        "target_node": "21bao",
        "available_models": sample_models,
        "dry_run": True,
    }


# --- Test Classes ---


class TestDryRunOnly:
    """Renderer must reject dry_run=false."""

    def test_dry_run_false_rejected(self, sample_models):
        """dry_run=false must raise ValueError."""
        input_data = {
            "target_node": "21bao",
            "available_models": sample_models,
            "dry_run": False,
        }
        with pytest.raises(ValueError, match="dry_run must be True"):
            render_config(input_data)

    def test_dry_run_missing_rejected(self, sample_models):
        """Missing dry_run must raise ValueError."""
        input_data = {
            "target_node": "21bao",
            "available_models": sample_models,
        }
        with pytest.raises(ValueError, match="missing required field: dry_run"):
            render_config(input_data)

    def test_dry_run_true_accepted(self, standard_input):
        """dry_run=true must succeed."""
        result = render_config(standard_input)
        assert result["dry_run"] is True


class TestNoPlaintextKeys:
    """Output must not contain plaintext keys."""

    def test_no_sk_keys(self, standard_input):
        """Output must not contain sk- prefixed keys."""
        result = render_config(standard_input)
        output_str = json.dumps(result)
        assert not re.search(r"sk-[a-zA-Z0-9]{10,}", output_str)

    def test_no_akia_keys(self, standard_input):
        """Output must not contain AKIA AWS keys."""
        result = render_config(standard_input)
        output_str = json.dumps(result)
        assert not re.search(r"AKIA[A-Z0-9]{16}", output_str)

    def test_no_bearer_tokens(self, standard_input):
        """Output must not contain Bearer tokens."""
        result = render_config(standard_input)
        output_str = json.dumps(result)
        assert not re.search(r"Bearer [a-zA-Z0-9]{10,}", output_str)

    def test_no_api_key_assignments(self, standard_input):
        """Output must not contain api_key assignments."""
        result = render_config(standard_input)
        output_str = json.dumps(result)
        assert not re.search(r"api[_-]?key\s*[:=]\s*[\"'][a-zA-Z0-9]{10,}", output_str, re.IGNORECASE)

    def test_no_openai_api_key(self, standard_input):
        """Output must not contain OPENAI_API_KEY values."""
        result = render_config(standard_input)
        output_str = json.dumps(result)
        assert not re.search(r"OPENAI_API_KEY\s*=\s*[a-zA-Z0-9-]{10,}", output_str)

    def test_no_deepseek_api_key(self, standard_input):
        """Output must not contain DEEPSEEK_API_KEY values."""
        result = render_config(standard_input)
        output_str = json.dumps(result)
        assert not re.search(r"DEEPSEEK_API_KEY\s*=\s*[a-zA-Z0-9-]{10,}", output_str)

    def test_scan_output_for_secrets_clean(self, standard_input):
        """Security scan must pass on clean output."""
        result = render_config(standard_input)
        violations = scan_output_for_secrets(result)
        assert violations == [], f"Security violations: {violations}"


class TestSecretRefUsage:
    """All model configs must use secret_ref."""

    def test_all_models_have_secret_ref(self, standard_input):
        """Every model in config_draft must have secret_ref."""
        result = render_config(standard_input)
        for model in result["config_draft"]["models"]:
            assert "secret_ref" in model, f"Model {model['alias']} missing secret_ref"
            assert model["secret_ref"].startswith("secret:"), \
                f"Model {model['alias']} secret_ref must start with 'secret:'"

    def test_credential_source_is_placeholder(self, standard_input):
        """credential_source must be node-local-secure-storage."""
        result = render_config(standard_input)
        for model in result["config_draft"]["models"]:
            assert model["credential_source"] == "node-local-secure-storage"


class TestRequiresOperatorApproval:
    """requires_operator_approval must always be True."""

    def test_always_true(self, standard_input):
        """Output must have requires_operator_approval=True."""
        result = render_config(standard_input)
        assert result["requires_operator_approval"] is True

    def test_always_true_empty_pool(self):
        """Even with empty available pool, requires_operator_approval=True."""
        input_data = {
            "target_node": "21bao",
            "available_models": [],
            "dry_run": True,
        }
        result = render_config(input_data)
        assert result["requires_operator_approval"] is True


class TestAvailablePoolFiltering:
    """Only models meeting all criteria enter Available pool."""

    def test_enabled_healthy_not_quarantined_available(self, sample_models):
        """Enabled + healthy + not quarantined + detected → Available."""
        input_data = {
            "target_node": "21bao",
            "available_models": sample_models,
            "dry_run": True,
        }
        result = render_config(input_data)
        aliases = [m["alias"] for m in result["config_draft"]["models"]]
        assert "mimo-free" in aliases
        assert "ds-v4-pro" in aliases

    def test_quarantined_excluded(self, sample_models):
        """Quarantined model → non_available_summary."""
        input_data = {
            "target_node": "21bao",
            "available_models": sample_models,
            "dry_run": True,
        }
        result = render_config(input_data)
        non_avail_ids = [m["model_id"] for m in result["non_available_summary"]]
        assert "volcengine-plan/ark-code-latest" in non_avail_ids

    def test_disabled_excluded(self, sample_models, disabled_model):
        """Disabled model → non_available_summary."""
        models = sample_models + [disabled_model]
        input_data = {
            "target_node": "21bao",
            "available_models": models,
            "dry_run": True,
        }
        result = render_config(input_data)
        non_avail_ids = [m["model_id"] for m in result["non_available_summary"]]
        assert "opencode/nemotron-3-ultra-free" in non_avail_ids

    def test_missing_credential_excluded(self, sample_models, missing_credential_model):
        """Missing credential model → non_available_summary."""
        models = sample_models + [missing_credential_model]
        input_data = {
            "target_node": "21bao",
            "available_models": models,
            "dry_run": True,
        }
        result = render_config(input_data)
        non_avail_ids = [m["model_id"] for m in result["non_available_summary"]]
        assert "xiaomi-plan/mimo-v2.5-pro" in non_avail_ids

    def test_not_detected_on_node_excluded(self, sample_models):
        """Model not detected on target node → non_available_summary."""
        input_data = {
            "target_node": "Windows",
            "available_models": sample_models,
            "dry_run": True,
        }
        result = render_config(input_data)
        non_avail_ids = [m["model_id"] for m in result["non_available_summary"]]
        # volcengine only on 21bao, so should be excluded on Windows
        assert "volcengine-plan/ark-code-latest" in non_avail_ids


class TestOpenCodeFreeConditional:
    """OpenCode free models: only if discovered + healthy + enabled."""

    def test_free_model_available_when_discovered(self, sample_models):
        """Free model available when discovered + healthy + enabled."""
        input_data = {
            "target_node": "21bao",
            "available_models": sample_models,
            "dry_run": True,
        }
        result = render_config(input_data)
        aliases = [m["alias"] for m in result["config_draft"]["models"]]
        assert "mimo-free" in aliases

    def test_free_model_excluded_when_not_discovered(self):
        """Free model excluded when not detected on node."""
        models = [
            {
                "model_id": "opencode/mimo-v2.5-free",
                "provider": "opencode",
                "alias": "mimo-free",
                "endpoint": "https://api.opencode.example.com/v1",
                "protocol": "openai-compatible",
                "node_availability": {
                    "21bao": {"available": False, "last_seen": "2026-06-01T00:00:00Z"},
                },
                "cost_tag": "free",
                "enabled": True,
                "health_status": "healthy",
                "quarantine_status": "none",
                "credential_status": "not-configured",
                "secret_ref": "secret:opencode:mimo-free-token",
                "source_flags": ["opencode-free"],
                "roles": ["implementer"],
                "priority": 1,
                "capability_tags": ["code"],
                "fallback_allowed": True,
            }
        ]
        input_data = {
            "target_node": "21bao",
            "available_models": models,
            "dry_run": True,
        }
        result = render_config(input_data)
        assert result["config_draft"]["models"] == []
        non_avail_ids = [m["model_id"] for m in result["non_available_summary"]]
        assert "opencode/mimo-v2.5-free" in non_avail_ids

    def test_free_model_excluded_when_unhealthy(self):
        """Free model excluded when health_status=unhealthy."""
        models = [
            {
                "model_id": "opencode/mimo-v2.5-free",
                "provider": "opencode",
                "alias": "mimo-free",
                "endpoint": "https://api.opencode.example.com/v1",
                "protocol": "openai-compatible",
                "node_availability": {
                    "21bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
                },
                "cost_tag": "free",
                "enabled": True,
                "health_status": "unhealthy",
                "quarantine_status": "none",
                "credential_status": "not-configured",
                "secret_ref": "secret:opencode:mimo-free-token",
                "source_flags": ["opencode-free"],
                "roles": ["implementer"],
                "priority": 1,
                "capability_tags": ["code"],
                "fallback_allowed": True,
            }
        ]
        input_data = {
            "target_node": "21bao",
            "available_models": models,
            "dry_run": True,
        }
        result = render_config(input_data)
        assert result["config_draft"]["models"] == []


class TestOpenCodeGoConditional:
    """OpenCode Go models: only if subscribed + enabled + detected."""

    def test_go_model_available_when_subscribed(self):
        """Go model available when subscribed + enabled + detected."""
        models = [
            {
                "model_id": "opencode-go/claude-sonnet-4",
                "provider": "opencode-go",
                "alias": "claude-sonnet",
                "endpoint": "https://api.opencode.example.com/v1",
                "protocol": "openai-compatible",
                "node_availability": {
                    "21bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
                },
                "cost_tag": "paid",
                "enabled": True,
                "health_status": "healthy",
                "quarantine_status": "none",
                "credential_status": "valid",
                "secret_ref": "secret:opencode-go:subscription",
                "source_flags": ["opencode-go"],
                "roles": ["implementer", "reviewer"],
                "priority": 5,
                "capability_tags": ["code", "chat"],
                "fallback_allowed": True,
            }
        ]
        input_data = {
            "target_node": "21bao",
            "available_models": models,
            "dry_run": True,
        }
        result = render_config(input_data)
        aliases = [m["alias"] for m in result["config_draft"]["models"]]
        assert "claude-sonnet" in aliases

    def test_go_model_excluded_when_no_credential(self):
        """Go model excluded when credential_status=missing."""
        models = [
            {
                "model_id": "opencode-go/claude-sonnet-4",
                "provider": "opencode-go",
                "alias": "claude-sonnet",
                "endpoint": "https://api.opencode.example.com/v1",
                "protocol": "openai-compatible",
                "node_availability": {
                    "21bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
                },
                "cost_tag": "paid",
                "enabled": True,
                "health_status": "healthy",
                "quarantine_status": "none",
                "credential_status": "missing",
                "secret_ref": "secret:opencode-go:subscription",
                "source_flags": ["opencode-go"],
                "roles": ["implementer"],
                "priority": 5,
                "capability_tags": ["code"],
                "fallback_allowed": True,
            }
        ]
        input_data = {
            "target_node": "21bao",
            "available_models": models,
            "dry_run": True,
        }
        result = render_config(input_data)
        assert result["config_draft"]["models"] == []


class TestNodeSpecificConfig:
    """Different target_nodes produce different configs."""

    def test_different_nodes_different_output(self, sample_models):
        """Config for 21bao vs 5bao may differ based on availability."""
        input_21bao = {
            "target_node": "21bao",
            "available_models": sample_models,
            "dry_run": True,
        }
        input_5bao = {
            "target_node": "5bao",
            "available_models": sample_models,
            "dry_run": True,
        }
        result_21bao = render_config(input_21bao)
        result_5bao = render_config(input_5bao)

        assert result_21bao["node"] == "21bao"
        assert result_5bao["node"] == "5bao"
        assert result_21bao["config_draft"]["node"] == "21bao"
        assert result_5bao["config_draft"]["node"] == "5bao"

    def test_windows_node(self, sample_models):
        """Windows node produces valid output."""
        input_data = {
            "target_node": "Windows",
            "available_models": sample_models,
            "dry_run": True,
        }
        result = render_config(input_data)
        assert result["node"] == "Windows"


class TestRoleAssignment:
    """Role assignment correctly maps to available models."""

    def test_role_assignment_configured(self, sample_models):
        """Role pointing to available model → status=configured."""
        input_data = {
            "target_node": "21bao",
            "available_models": sample_models,
            "role_assignment": {
                "implementer": "opencode/mimo-v2.5-free",
                "reviewer": "deepseek-plan/deepseek-v4-pro",
            },
            "dry_run": True,
        }
        result = render_config(input_data)
        assert result["role_assignment"]["implementer"]["status"] == "configured"
        assert result["role_assignment"]["reviewer"]["status"] == "configured"

    def test_role_assignment_unavailable_model(self, sample_models, disabled_model):
        """Role pointing to unavailable model → status includes reason + warning."""
        models = sample_models + [disabled_model]
        input_data = {
            "target_node": "21bao",
            "available_models": models,
            "role_assignment": {
                "implementer": "opencode/nemotron-3-ultra-free",
            },
            "dry_run": True,
        }
        result = render_config(input_data)
        assert "unavailable" in result["role_assignment"]["implementer"]["status"]
        assert len(result["warnings"]) > 0

    def test_role_assignment_unknown_model(self, sample_models):
        """Role pointing to unknown model → status=not-found + warning."""
        input_data = {
            "target_node": "21bao",
            "available_models": sample_models,
            "role_assignment": {
                "implementer": "nonexistent/model",
            },
            "dry_run": True,
        }
        result = render_config(input_data)
        assert result["role_assignment"]["implementer"]["status"] == "not-found"
        assert len(result["warnings"]) > 0

    def test_role_assignment_unassigned(self, sample_models):
        """Role with None → status=unassigned."""
        input_data = {
            "target_node": "21bao",
            "available_models": sample_models,
            "role_assignment": {
                "implementer": "opencode/mimo-v2.5-free",
                "reviewer": None,
            },
            "dry_run": True,
        }
        result = render_config(input_data)
        assert result["role_assignment"]["reviewer"]["status"] == "unassigned"

    def test_role_assignment_auto_substitute_forbidden(self, sample_models):
        """Role pointing to unavailable model must NOT auto-substitute."""
        input_data = {
            "target_node": "21bao",
            "available_models": sample_models,
            "role_assignment": {
                "implementer": "volcengine-plan/ark-code-latest",
            },
            "dry_run": True,
        }
        result = render_config(input_data)
        # Must NOT substitute with an available model
        assert result["role_assignment"]["implementer"]["model_alias"] == "volcengine-plan/ark-code-latest"
        assert "unavailable" in result["role_assignment"]["implementer"]["status"]


class TestEmptyAvailablePool:
    """Empty available pool produces empty config + warning."""

    def test_empty_pool_warning(self):
        """No available models → empty config + warning."""
        input_data = {
            "target_node": "21bao",
            "available_models": [],
            "dry_run": True,
        }
        result = render_config(input_data)
        assert result["config_draft"]["models"] == []
        assert result["config_draft"]["default_model"] is None
        assert any("no available models" in w for w in result["warnings"])


class TestAuditInputHash:
    """Audit input_hash must be stable and deterministic."""

    def test_hash_stability(self, standard_input):
        """Same input produces same hash."""
        result1 = render_config(standard_input)
        result2 = render_config(standard_input)
        assert result1["audit"]["input_hash"] == result2["audit"]["input_hash"]

    def test_hash_changes_with_input(self, sample_models):
        """Different input produces different hash."""
        input1 = {
            "target_node": "21bao",
            "available_models": sample_models,
            "dry_run": True,
        }
        input2 = {
            "target_node": "5bao",
            "available_models": sample_models,
            "dry_run": True,
        }
        result1 = render_config(input1)
        result2 = render_config(input2)
        assert result1["audit"]["input_hash"] != result2["audit"]["input_hash"]

    def test_hash_is_sha256(self, standard_input):
        """Input hash must be valid SHA256."""
        result = render_config(standard_input)
        h = result["audit"]["input_hash"]
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_renderer_version_present(self, standard_input):
        """Audit must include renderer_version."""
        result = render_config(standard_input)
        assert result["audit"]["renderer_version"] == RENDERER_VERSION


class TestContractSchemaCompliance:
    """Output must conform to contract §4.3 schema."""

    def test_output_has_required_fields(self, standard_input):
        """Output must have all required fields."""
        result = render_config(standard_input)
        required = ["node", "dry_run", "timestamp", "config_draft", "role_assignment",
                     "warnings", "non_available_summary", "requires_operator_approval", "audit"]
        for field in required:
            assert field in result, f"Missing required field: {field}"

    def test_config_draft_has_models(self, standard_input):
        """config_draft must have models list."""
        result = render_config(standard_input)
        assert "models" in result["config_draft"]
        assert isinstance(result["config_draft"]["models"], list)

    def test_audit_has_input_hash(self, standard_input):
        """audit must have input_hash."""
        result = render_config(standard_input)
        assert "input_hash" in result["audit"]

    def test_audit_has_renderer_version(self, standard_input):
        """audit must have renderer_version."""
        result = render_config(standard_input)
        assert "renderer_version" in result["audit"]

    def test_timestamp_iso8601(self, standard_input):
        """timestamp must be ISO 8601."""
        result = render_config(standard_input)
        ts = result["timestamp"]
        assert ts.endswith("Z")
        # Basic ISO 8601 check
        datetime_part = ts[:-1]
        assert "T" in datetime_part


class TestLocalDirtNotInDiff:
    """Local dirt files must not appear in renderer output."""

    def test_malicious_payload_not_in_output(self, standard_input):
        """malicious_payload_evidence.json content must not appear in output."""
        result = render_config(standard_input)
        output_str = json.dumps(result)
        assert "malicious_payload" not in output_str.lower()

    def test_pilot_prompts_not_in_output(self, standard_input):
        """pilot-prompts content must not appear in output."""
        result = render_config(standard_input)
        output_str = json.dumps(result)
        assert "pilot-prompts" not in output_str.lower()


class TestInputValidation:
    """Input validation must catch all error cases."""

    def test_missing_target_node(self):
        """Missing target_node must raise ValueError."""
        input_data = {
            "available_models": [],
            "dry_run": True,
        }
        with pytest.raises(ValueError, match="missing required field: target_node"):
            render_config(input_data)

    def test_empty_target_node(self):
        """Empty target_node must raise ValueError."""
        input_data = {
            "target_node": "",
            "available_models": [],
            "dry_run": True,
        }
        with pytest.raises(ValueError, match="target_node must be a non-empty string"):
            render_config(input_data)

    def test_missing_models(self):
        """Missing both available_models and model_pool must raise ValueError."""
        input_data = {
            "target_node": "21bao",
            "dry_run": True,
        }
        with pytest.raises(ValueError, match="missing required field: available_models"):
            render_config(input_data)

    def test_invalid_role_assignment_type(self, sample_models):
        """Invalid role_assignment type must raise ValueError."""
        input_data = {
            "target_node": "21bao",
            "available_models": sample_models,
            "role_assignment": "invalid",
            "dry_run": True,
        }
        with pytest.raises(ValueError, match="role_assignment must be a dict"):
            render_config(input_data)


class TestSelfCheck:
    """Self-check must return valid status."""

    def test_self_check(self):
        """Self-check must return ok status."""
        result = self_check()
        assert result["status"] == "ok"
        assert result["dry_run_only"] is True
        assert "renderer_version" in result
