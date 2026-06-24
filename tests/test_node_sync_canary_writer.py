#!/usr/bin/env python3
"""Tests for Node Sync Canary Writer + Verify v1.0.0

Contract: docs/MODEL_POOL_DISTRIBUTION_CONTRACT.md
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from node_sync_canary_writer import (
    BLOCKED_PATHS,
    CANARY_SUFFIX,
    WRITER_VERSION,
    actually_write_temp_file,
    generate_write_plan,
    run_safety_checks,
    self_check as writer_self_check,
    validate_content_safety,
    validate_write_request,
    write_canary_config,
)
from node_sync_canary_verify import (
    VERIFY_VERSION,
    self_check as verify_self_check,
    verify_canary_config,
)


# --- Fixtures ---


@pytest.fixture
def sample_planner_output():
    """Sample planner output with config_preview."""
    return {
        "node": "21bao",
        "dry_run": True,
        "requires_operator_approval": True,
        "config_preview": {
            "format": "opencode-jsonc",
            "content_preview": {
                "provider": {
                    "opencode": {
                        "npm": "@ai-sdk/openai-compatible",
                        "options": {"baseURL": ""},
                        "models": {
                            "mimo-v2.5-free": {"name": "MiMo V2.5 Free"},
                            "deepseek-v4-flash-free": {"name": "DeepSeek V4 Flash Free"},
                        },
                    }
                }
            },
            "content_hash": "abc123def456",
            "secret_fields": ["secret:opencode:mimo-v2.5-free"],
            "no_real_keys": True,
        },
        "action_plan": {"action": "sync_config", "target_node": "21bao"},
        "safety_checks": {"passed": True},
        "audit": {"input_hash": "test123", "planner_version": "1.0.0"},
    }


@pytest.fixture
def canary_path(tmp_path):
    """Temp canary path."""
    return str(tmp_path / "opencode.jsonc.canary-test")


# --- Test Writer Input Validation ---


class TestWriterInputValidation:
    """Tests for writer input validation."""

    def test_valid_request(self, sample_planner_output, canary_path):
        valid, errors = validate_write_request(
            sample_planner_output, canary_path, False, None, True
        )
        assert valid is True
        assert errors == []

    def test_dry_run_false(self, sample_planner_output, canary_path):
        valid, errors = validate_write_request(
            sample_planner_output, canary_path, False, None, False
        )
        assert valid is False
        assert any("dry_run" in e for e in errors)

    def test_empty_planner(self, canary_path):
        valid, errors = validate_write_request({}, canary_path, False, None, True)
        assert valid is False

    def test_missing_config_preview(self, canary_path):
        valid, errors = validate_write_request(
            {"node": "test"}, canary_path, False, None, True
        )
        assert valid is False
        assert any("config_preview" in e for e in errors)

    def test_non_canary_suffix(self, sample_planner_output):
        valid, errors = validate_write_request(
            sample_planner_output, "/tmp/config.json", False, None, True
        )
        assert valid is False
        assert any("canary-test" in e for e in errors)

    def test_blocked_real_path(self, sample_planner_output):
        valid, errors = validate_write_request(
            sample_planner_output, "/tmp/opencode.jsonc", False, None, True
        )
        assert valid is False
        assert any("blocked" in e for e in errors)

    def test_allow_write_without_approval(self, sample_planner_output, canary_path):
        valid, errors = validate_write_request(
            sample_planner_output, canary_path, True, None, True
        )
        assert valid is False
        assert any("approval_id" in e for e in errors)

    def test_allow_write_with_approval(self, sample_planner_output, canary_path):
        valid, errors = validate_write_request(
            sample_planner_output, canary_path, True, "approval-001", True
        )
        assert valid is True


# --- Test Content Safety ---


class TestContentSafety:
    """Tests for content safety validation."""

    def test_clean_content(self):
        safe, violations = validate_content_safety('{"provider": {"test": {}}}')
        assert safe is True
        assert violations == []

    def test_detect_sk_key(self):
        safe, violations = validate_content_safety('{"key": "sk-abcdefghijklmnop"}')
        assert safe is False

    def test_detect_akia(self):
        safe, violations = validate_content_safety('{"key": "AKIAIOSFODNN7EXAMPLE"}')
        assert safe is False


# --- Test Write Plan ---


class TestWritePlan:
    """Tests for write plan generation."""

    def test_write_plan_fields(self, sample_planner_output, canary_path):
        plan = generate_write_plan(
            sample_planner_output, "21bao", canary_path, "op-1", "approval-001"
        )
        assert plan["action"] == "write_canary_config"
        assert plan["target_node"] == "21bao"
        assert plan["temp_config_path"] == canary_path
        assert plan["no_real_keys"] is True
        assert plan["operator_id"] == "op-1"
        assert plan["approval_id"] == "approval-001"

    def test_write_plan_content_hash(self, sample_planner_output, canary_path):
        plan = generate_write_plan(
            sample_planner_output, "21bao", canary_path, "op-1", None
        )
        assert plan["content_hash"] == "abc123def456"


# --- Test Safety Checks ---


class TestWriterSafetyChecks:
    """Tests for writer safety checks."""

    def test_all_pass(self, sample_planner_output, canary_path):
        content = json.dumps(sample_planner_output["config_preview"]["content_preview"])
        safety = run_safety_checks(
            sample_planner_output, canary_path, False, None, True, content
        )
        assert safety["passed"] is True
        assert safety["dry_run_enforced"] is True
        assert safety["path_is_canary"] is True
        assert safety["not_real_config_path"] is True
        assert safety["no_real_keys"] is True

    def test_dry_run_false(self, sample_planner_output, canary_path):
        content = "{}"
        safety = run_safety_checks(
            sample_planner_output, canary_path, False, None, False, content
        )
        assert safety["passed"] is False

    def test_non_canary_path(self, sample_planner_output):
        content = "{}"
        safety = run_safety_checks(
            sample_planner_output, "/tmp/config.json", False, None, True, content
        )
        assert safety["passed"] is False

    def test_secrets_in_content(self, sample_planner_output, canary_path):
        content = '{"key": "sk-abcdefghijklmnop"}'
        safety = run_safety_checks(
            sample_planner_output, canary_path, False, None, True, content
        )
        assert safety["passed"] is False
        assert safety["no_real_keys"] is False


# --- Test Main Writer ---


class TestWriteCanaryConfig:
    """Tests for main write_canary_config function."""

    def test_dry_run_no_write(self, sample_planner_output, canary_path):
        result = write_canary_config(
            sample_planner_output, "21bao", canary_path,
            operator_id="test-op", dry_run=True,
        )
        assert result["dry_run"] is True
        assert result["requires_operator_approval"] is True
        assert result["actually_wrote"] is False
        assert result["safety_checks"]["passed"] is True
        assert os.path.exists(canary_path) is False

    def test_no_approval_no_write(self, sample_planner_output, canary_path):
        result = write_canary_config(
            sample_planner_output, "21bao", canary_path,
            operator_id="test-op", allow_temp_write=False, dry_run=True,
        )
        assert result["actually_wrote"] is False

    def test_audit_fields(self, sample_planner_output, canary_path):
        result = write_canary_config(
            sample_planner_output, "21bao", canary_path,
            operator_id="test-op", approval_id="approval-001", dry_run=True,
        )
        audit = result["audit"]
        assert audit["action"] == "write_canary_config"
        assert audit["operator_id"] == "test-op"
        assert audit["approval_id"] == "approval-001"
        assert audit["writer_version"] == WRITER_VERSION

    def test_blocked_real_path(self, sample_planner_output):
        with pytest.raises(ValueError, match="blocked|canary-test"):
            write_canary_config(
                sample_planner_output, "21bao", "/tmp/opencode.jsonc",
                operator_id="test-op", dry_run=True,
            )

    def test_dry_run_false_blocked(self, sample_planner_output, canary_path):
        with pytest.raises(ValueError, match="dry_run"):
            write_canary_config(
                sample_planner_output, "21bao", canary_path,
                dry_run=False,
            )


# --- Test Actually Write ---


class TestActuallyWrite:
    """Tests for actually_write_temp_file."""

    def test_write_and_verify(self, tmp_path):
        path = str(tmp_path / "test.canary-test")
        content = '{"provider": {"test": {}}}'
        content_hash = __import__("hashlib").sha256(content.encode()).hexdigest()

        result = actually_write_temp_file(path, content, content_hash)
        assert result["written"] is True
        assert result["hash_match"] is True
        assert os.path.exists(path)

    def test_write_creates_parent(self, tmp_path):
        path = str(tmp_path / "subdir" / "test.canary-test")
        content = '{"test": true}'
        content_hash = __import__("hashlib").sha256(content.encode()).hexdigest()

        result = actually_write_temp_file(path, content, content_hash)
        assert result["written"] is True
        assert os.path.exists(path)


# --- Test Verify ---


class TestVerifyCanaryConfig:
    """Tests for verify_canary_config."""

    def test_file_not_exists(self):
        result = verify_canary_config("/nonexistent/path.canary-test")
        assert result["exists"] is False
        assert result["would_be_loadable_offline"] is False

    def test_valid_config(self, tmp_path):
        path = str(tmp_path / "test.canary-test")
        content = json.dumps({
            "provider": {
                "opencode": {
                    "models": {"test": {"name": "Test"}}
                }
            }
        })
        with open(path, "w") as f:
            f.write(content)

        result = verify_canary_config(path)
        assert result["exists"] is True
        assert result["schema_valid"] is True
        assert result["no_real_keys"] is True
        assert result["would_be_loadable_offline"] is True
        assert result["violations"] == []

    def test_hash_match(self, tmp_path):
        path = str(tmp_path / "test.canary-test")
        content = '{"provider": {}}'
        content_hash = __import__("hashlib").sha256(content.encode()).hexdigest()
        with open(path, "w") as f:
            f.write(content)

        result = verify_canary_config(path, expected_hash=content_hash)
        assert result["hash_match"] is True

    def test_hash_mismatch(self, tmp_path):
        path = str(tmp_path / "test.canary-test")
        with open(path, "w") as f:
            f.write('{"provider": {}}')

        result = verify_canary_config(path, expected_hash="wrong_hash")
        assert result["hash_match"] is False
        assert any("mismatch" in v for v in result["violations"])

    def test_secret_scan_fail(self, tmp_path):
        path = str(tmp_path / "test.canary-test")
        with open(path, "w") as f:
            f.write('{"key": "sk-abcdefghijklmnop"}')

        result = verify_canary_config(path)
        assert result["no_real_keys"] is False

    def test_invalid_json(self, tmp_path):
        path = str(tmp_path / "test.canary-test")
        with open(path, "w") as f:
            f.write("{invalid json}")

        result = verify_canary_config(path)
        assert result["schema_valid"] is False

    def test_jsonc_comments(self, tmp_path):
        path = str(tmp_path / "test.canary-test")
        with open(path, "w") as f:
            f.write('// comment\n{"provider": {"test": {}}}')

        result = verify_canary_config(path)
        assert result["schema_valid"] is True

    def test_audit_fields(self, tmp_path):
        path = str(tmp_path / "test.canary-test")
        with open(path, "w") as f:
            f.write('{"provider": {}}')

        result = verify_canary_config(path, operator_id="test-op")
        assert result["audit"]["action"] == "verify_canary_config"
        assert result["audit"]["operator_id"] == "test-op"
        assert result["audit"]["verify_version"] == VERIFY_VERSION


# --- Test Integration ---


class TestWriterVerifyIntegration:
    """Test writer → verify round-trip."""

    def test_round_trip(self, sample_planner_output, tmp_path):
        canary_path = str(tmp_path / "roundtrip.canary-test")

        # Get content from planner
        content_preview = sample_planner_output["config_preview"]["content_preview"]
        content_str = json.dumps(content_preview, indent=2, ensure_ascii=False)
        content_hash = __import__("hashlib").sha256(content_str.encode()).hexdigest()

        # Write
        write_result = actually_write_temp_file(canary_path, content_str, content_hash)
        assert write_result["written"] is True

        # Verify
        verify_result = verify_canary_config(canary_path, expected_hash=content_hash)
        assert verify_result["exists"] is True
        assert verify_result["hash_match"] is True
        assert verify_result["schema_valid"] is True
        assert verify_result["no_real_keys"] is True
        assert verify_result["would_be_loadable_offline"] is True


# --- Test Self-check ---


class TestSelfCheck:
    """Tests for self-checks."""

    def test_writer_self_check(self):
        result = writer_self_check()
        assert result["status"] == "ok"
        assert result["writer_version"] == WRITER_VERSION

    def test_verify_self_check(self):
        result = verify_self_check()
        assert result["status"] == "ok"
        assert result["verify_version"] == VERIFY_VERSION


# --- Test Constants ---


class TestConstants:
    """Tests for module constants."""

    def test_canary_suffix(self):
        assert CANARY_SUFFIX == ".canary-test"

    def test_blocked_paths(self):
        assert "opencode.jsonc" in BLOCKED_PATHS
        assert "opencode.json" in BLOCKED_PATHS
        assert "config.json" in BLOCKED_PATHS

    def test_dangerous_patterns(self):
        from node_sync_canary_writer import DANGEROUS_KEY_PATTERNS
        assert len(DANGEROUS_KEY_PATTERNS) >= 5
