#!/usr/bin/env python3
"""Tests for Credential Status Resolver v1.0.0

Contract: docs/MODEL_POOL_DISTRIBUTION_CONTRACT.md
"""

import json
import os
import sys
import tempfile

import pytest

# Add scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from credential_status_resolver import (
    DANGEROUS_KEY_PATTERNS,
    PROVIDER_ENV_MAP,
    RESOLVER_VERSION,
    SENSITIVE_FIELD_NAMES,
    VALID_BACKENDS,
    VALID_CREDENTIAL_STATUSES,
    parse_secret_ref,
    resolve_batch,
    resolve_credential,
    self_check,
    validate_backend,
    validate_output_safety,
    validate_secret_ref,
)


# --- Fixtures ---


@pytest.fixture
def sample_fixture():
    """Sample fixture data for testing."""
    return {
        "credentials": {
            "secret:deepseek-plan:deepseek-v4-pro": {
                "credential_status": "valid",
                "status_reason": "key configured in env",
            },
            "secret:volcengine-plan:ark-code-latest": {
                "credential_status": "missing",
                "status_reason": "no key found",
            },
            "secret:xiaomi-plan:mimo-v2.5": {
                "credential_status": "expired",
                "status_reason": "key expired on 2026-01-01",
            },
            "secret:opencode:deepseek-v4-flash-free": {
                "credential_status": "not-configured",
                "status_reason": "free model, no key needed",
            },
        }
    }


@pytest.fixture
def sample_fixture_file(sample_fixture, tmp_path):
    """Write fixture to a temp file."""
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(sample_fixture), encoding="utf-8")
    return str(path)


# --- Test Validate Secret Ref ---


class TestValidateSecretRef:
    """Tests for secret_ref validation."""

    def test_valid_format(self):
        valid, err = validate_secret_ref("secret:deepseek-plan:deepseek-v4-pro")
        assert valid is True
        assert err == ""

    def test_valid_opencode_free(self):
        valid, err = validate_secret_ref("secret:opencode:mimo-v2.5-free")
        assert valid is True

    def test_reject_empty(self):
        valid, err = validate_secret_ref("")
        assert valid is False
        assert "non-empty" in err

    def test_reject_none(self):
        valid, err = validate_secret_ref(None)
        assert valid is False

    def test_reject_non_string(self):
        valid, err = validate_secret_ref(123)
        assert valid is False

    def test_reject_no_secret_prefix(self):
        valid, err = validate_secret_ref("sk-abc...mnop")
        assert valid is False
        assert "secret:" in err

    def test_reject_sk_key(self):
        valid, err = validate_secret_ref("secret:deepseek:sk-abcdefghijklmnopqrstuvwxyz")
        assert valid is False
        assert "real key" in err

    def test_reject_akia(self):
        valid, err = validate_secret_ref("secret:aws:AKIAIOSFODNN7EXAMPLE")
        assert valid is False
        assert "real key" in err

    def test_reject_bearer(self):
        valid, err = validate_secret_ref("secret:oauth:Bearer abc123def456ghi789jkl012")
        assert valid is False
        assert "real key" in err

    def test_reject_private_key(self):
        valid, err = validate_secret_ref("secret:ssh:-----BEGIN RSA PRIVATE KEY-----")
        assert valid is False
        assert "real key" in err

    def test_reject_too_long(self):
        valid, err = validate_secret_ref("secret:test:" + "x" * 200)
        assert valid is False
        assert "too long" in err

    def test_reject_only_secret(self):
        valid, err = validate_secret_ref("secret:")
        assert valid is False
        assert "format" in err

    def test_valid_with_hyphens_and_numbers(self):
        valid, err = validate_secret_ref("secret:deepseek-plan:ds-v4-flash-free-2")
        assert valid is True


# --- Test Validate Backend ---


class TestValidateBackend:
    """Tests for backend validation."""

    def test_valid_fixture(self):
        valid, _ = validate_backend("fixture")
        assert valid is True

    def test_valid_file(self):
        valid, _ = validate_backend("file")
        assert valid is True

    def test_valid_env_status(self):
        valid, _ = validate_backend("env-status")
        assert valid is True

    def test_reject_invalid(self):
        valid, err = validate_backend("api")
        assert valid is False
        assert "invalid" in err

    def test_reject_empty(self):
        valid, _ = validate_backend("")
        assert valid is False


# --- Test Parse Secret Ref ---


class TestParseSecretRef:
    """Tests for secret_ref parsing."""

    def test_parse_standard(self):
        provider, alias = parse_secret_ref("secret:deepseek-plan:deepseek-v4-pro")
        assert provider == "deepseek-plan"
        assert alias == "deepseek-v4-pro"

    def test_parse_opencode_free(self):
        provider, alias = parse_secret_ref("secret:opencode:mimo-v2.5-free")
        assert provider == "opencode"
        assert alias == "mimo-v2.5-free"

    def test_parse_minimal(self):
        provider, alias = parse_secret_ref("secret:x:y")
        assert provider == "x"
        assert alias == "y"


# --- Test Resolve Credential ---


class TestResolveCredential:
    """Tests for main resolve_credential function."""

    def test_fixture_valid(self, sample_fixture):
        result = resolve_credential(
            "secret:deepseek-plan:deepseek-v4-pro",
            backend="fixture", fixture_data=sample_fixture,
        )
        assert result["credential_status"] == "valid"
        assert result["secret_ref"] == "secret:deepseek-plan:deepseek-v4-pro"
        assert result["resolver_version"] == RESOLVER_VERSION

    def test_fixture_missing(self, sample_fixture):
        result = resolve_credential(
            "secret:volcengine-plan:ark-code-latest",
            backend="fixture", fixture_data=sample_fixture,
        )
        assert result["credential_status"] == "missing"

    def test_fixture_expired(self, sample_fixture):
        result = resolve_credential(
            "secret:xiaomi-plan:mimo-v2.5",
            backend="fixture", fixture_data=sample_fixture,
        )
        assert result["credential_status"] == "expired"

    def test_fixture_not_configured(self, sample_fixture):
        result = resolve_credential(
            "secret:opencode:deepseek-v4-flash-free",
            backend="fixture", fixture_data=sample_fixture,
        )
        assert result["credential_status"] == "not-configured"

    def test_fixture_unknown_ref(self, sample_fixture):
        result = resolve_credential(
            "secret:unknown:model-xyz",
            backend="fixture", fixture_data=sample_fixture,
        )
        assert result["credential_status"] == "unknown"

    def test_fixture_no_data(self):
        result = resolve_credential(
            "secret:test:model", backend="fixture", fixture_data=None,
        )
        assert result["credential_status"] == "unknown"
        assert "no fixture" in result["metadata"]["status_reason"]

    def test_file_backend(self, sample_fixture_file):
        result = resolve_credential(
            "secret:deepseek-plan:deepseek-v4-pro",
            backend="file", fixture_path=sample_fixture_file,
        )
        assert result["credential_status"] == "valid"

    def test_file_backend_not_found(self):
        with pytest.raises(FileNotFoundError):
            resolve_credential(
                "secret:test:model", backend="file",
                fixture_path="/nonexistent/path.json",
            )

    def test_env_status_backend(self):
        result = resolve_credential(
            "secret:deepseek-plan:deepseek-v4-pro", backend="env-status",
        )
        assert result["credential_status"] in ("valid", "missing")
        assert "env var" in result["metadata"]["status_reason"]

    def test_reject_invalid_ref(self):
        with pytest.raises(ValueError, match="invalid secret_ref"):
            resolve_credential("sk-abc...mnop", backend="fixture")

    def test_reject_invalid_backend(self):
        with pytest.raises(ValueError, match="invalid backend"):
            resolve_credential("secret:test:model", backend="api")

    def test_file_backend_no_path(self):
        with pytest.raises(ValueError, match="fixture_path"):
            resolve_credential("secret:test:model", backend="file")


# --- Test Output Safety ---


class TestOutputSafety:
    """Tests for output safety validation."""

    def test_clean_output(self):
        output = {
            "secret_ref": "secret:test:model",
            "credential_status": "valid",
            "metadata": {"provider": "test", "alias": "model"},
        }
        safe, violations = validate_output_safety(output)
        assert safe is True
        assert violations == []

    def test_detect_sensitive_key(self):
        output = {"api_key": "something"}
        safe, violations = validate_output_safety(output)
        assert safe is False
        assert any("api_key" in v for v in violations)

    def test_detect_sensitive_metadata(self):
        output = {"metadata": {"token": "value"}}
        safe, violations = validate_output_safety(output)
        assert safe is False

    def test_detect_dangerous_pattern_in_value(self):
        output = {"note": "key is sk-abcdefghijklmnopqrstuvwxyz123456"}
        safe, violations = validate_output_safety(output)
        assert safe is False


# --- Test Resolve Batch ---


class TestResolveBatch:
    """Tests for batch resolution."""

    def test_batch_mixed(self, sample_fixture):
        refs = [
            "secret:deepseek-plan:deepseek-v4-pro",
            "secret:volcengine-plan:ark-code-latest",
            "secret:unknown:model-xyz",
        ]
        results = resolve_batch(refs, backend="fixture", fixture_data=sample_fixture)
        assert len(results) == 3
        assert results[0]["credential_status"] == "valid"
        assert results[1]["credential_status"] == "missing"
        assert results[2]["credential_status"] == "unknown"

    def test_batch_with_invalid_ref(self, sample_fixture):
        refs = [
            "secret:deepseek-plan:deepseek-v4-pro",
            "sk-abc...mnop",  # invalid
        ]
        results = resolve_batch(refs, backend="fixture", fixture_data=sample_fixture)
        assert len(results) == 2
        assert results[0]["credential_status"] == "valid"
        assert results[1]["credential_status"] == "unknown"
        assert "error" in results[1]


# --- Test Metadata ---


class TestResolverMetadata:
    """Tests for resolver metadata fields."""

    def test_metadata_fields(self, sample_fixture):
        result = resolve_credential(
            "secret:deepseek-plan:deepseek-v4-pro",
            backend="fixture", fixture_data=sample_fixture,
        )
        meta = result["metadata"]
        assert meta["provider"] == "deepseek-plan"
        assert meta["alias"] == "deepseek-v4-pro"
        assert meta["source"] == "fixture"
        assert meta["last_checked"] is not None
        assert meta["resolver_version"] == RESOLVER_VERSION
        assert meta["status_reason"] is not None

    def test_metadata_env_status(self):
        result = resolve_credential(
            "secret:deepseek-plan:test", backend="env-status",
        )
        assert result["metadata"]["source"] == "env-status"
        assert "env var" in result["metadata"]["status_reason"]

    def test_resolved_at_present(self, sample_fixture):
        result = resolve_credential(
            "secret:test:model", backend="fixture", fixture_data=sample_fixture,
        )
        assert "resolved_at" in result
        assert result["resolved_at"].endswith("Z")


# --- Test Edge Cases ---


class TestResolverEdgeCases:
    """Tests for edge cases."""

    def test_consistent_results(self, sample_fixture):
        """Multiple resolves return same result."""
        r1 = resolve_credential(
            "secret:deepseek-plan:deepseek-v4-pro",
            backend="fixture", fixture_data=sample_fixture,
        )
        r2 = resolve_credential(
            "secret:deepseek-plan:deepseek-v4-pro",
            backend="fixture", fixture_data=sample_fixture,
        )
        assert r1["credential_status"] == r2["credential_status"]

    def test_empty_fixture_data(self):
        result = resolve_credential(
            "secret:test:model", backend="fixture", fixture_data={},
        )
        assert result["credential_status"] == "unknown"

    def test_malformed_fixture_no_credentials_key(self):
        result = resolve_credential(
            "secret:test:model", backend="fixture",
            fixture_data={"other_key": "value"},
        )
        assert result["credential_status"] == "unknown"

    def test_valid_statuses_all_valid(self):
        """All valid credential statuses are recognized."""
        for status in ("valid", "expired", "missing", "not-configured", "unknown"):
            assert status in VALID_CREDENTIAL_STATUSES

    def test_all_backends_recognized(self):
        for backend in ("fixture", "file", "env-status"):
            valid, _ = validate_backend(backend)
            assert valid is True


# --- Test File Backend ---


class TestFileBackend:
    """Tests for file-based fixture backend."""

    def test_file_resolve_valid(self, sample_fixture_file):
        result = resolve_credential(
            "secret:deepseek-plan:deepseek-v4-pro",
            backend="file", fixture_path=sample_fixture_file,
        )
        assert result["credential_status"] == "valid"

    def test_file_resolve_missing(self, sample_fixture_file):
        result = resolve_credential(
            "secret:volcengine-plan:ark-code-latest",
            backend="file", fixture_path=sample_fixture_file,
        )
        assert result["credential_status"] == "missing"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            resolve_credential(
                "secret:test:model", backend="file",
                fixture_path="/nonexistent.json",
            )


# --- Test Env Status Backend ---


class TestEnvStatusBackend:
    """Tests for env-status backend."""

    def test_env_status_deeplink(self):
        """env-status correctly reports based on env var existence."""
        result = resolve_credential(
            "secret:deepseek-plan:test", backend="env-status",
        )
        # DEEPSEEK_API_KEY may or may not exist in test env
        assert result["credential_status"] in ("valid", "missing")
        assert "DEEPSEEK_API_KEY" in result["metadata"]["status_reason"]

    def test_env_status_unknown_provider(self):
        result = resolve_credential(
            "secret:unknown-prov:test", backend="env-status",
        )
        assert result["credential_status"] in ("valid", "missing")
        assert "UNKNOWN_PROV_API_KEY" in result["metadata"]["status_reason"]


# --- Test Self-check ---


class TestSelfCheck:
    """Tests for resolver self-check."""

    def test_self_check_passes(self):
        result = self_check()
        assert result["status"] == "ok"
        assert result["resolver_version"] == RESOLVER_VERSION
        assert result["passed"] == result["total"]

    def test_self_check_has_checks(self):
        result = self_check()
        assert len(result["checks"]) >= 10

    def test_self_check_all_passed(self):
        result = self_check()
        for check in result["checks"]:
            assert check["passed"] is True, f"check {check['name']} failed: {check['detail']}"


# --- Test Constants ---


class TestConstants:
    """Tests for module constants."""

    def test_valid_statuses(self):
        assert "valid" in VALID_CREDENTIAL_STATUSES
        assert "expired" in VALID_CREDENTIAL_STATUSES
        assert "missing" in VALID_CREDENTIAL_STATUSES
        assert "not-configured" in VALID_CREDENTIAL_STATUSES
        assert "unknown" in VALID_CREDENTIAL_STATUSES

    def test_valid_backends(self):
        assert "fixture" in VALID_BACKENDS
        assert "file" in VALID_BACKENDS
        assert "env-status" in VALID_BACKENDS

    def test_dangerous_patterns(self):
        assert len(DANGEROUS_KEY_PATTERNS) >= 3

    def test_sensitive_field_names(self):
        assert "api_key" in SENSITIVE_FIELD_NAMES
        assert "token" in SENSITIVE_FIELD_NAMES
        assert "password" in SENSITIVE_FIELD_NAMES

    def test_provider_env_map(self):
        assert "deepseek-plan" in PROVIDER_ENV_MAP
        assert PROVIDER_ENV_MAP["deepseek-plan"] == "DEEPSEEK_API_KEY"
