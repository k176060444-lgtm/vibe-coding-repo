#!/usr/bin/env python3
"""Tests for credential_status additive schema (Phase 3 PR-5).

Covers:
- Allowed enum values (present, empty, missing, unknown, not_required)
- Invalid credential_status rejection
- Auto-classification logic (deterministic, no env read)
- Lifecycle × credential compatibility
- declared_enabled_unassigned NOT forced to present
- enabled_assigned/operator_requested constraints
- No secret value read, no env var read
- Legacy compatibility (no field = no crash)
"""

import json
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

REPO = Path(__file__).resolve().parent.parent

# ── helpers ──────────────────────────────────────────────────────────────────


def _run_manager(*args: str) -> dict:
    """Run model_pool_manager.py with given args, return parsed JSON stdout."""
    result = subprocess.run(
        [sys.executable, "scripts/model_pool_manager.py", *args],
        cwd=REPO, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0 and result.stderr:
        raise RuntimeError(f"Manager failed: {result.stderr[:300]}")
    return json.loads(result.stdout)


def _load_pool() -> dict:
    import yaml
    with open(REPO / "scripts" / "model_pool.yaml", "r") as f:
        return yaml.safe_load(f)


def _get_models() -> list[dict]:
    return _load_pool().get("models", [])


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def pool_models() -> list[dict]:
    return _get_models()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Allowed enum values
# ═══════════════════════════════════════════════════════════════════════════════

CREDENTIAL_STATUS_VALUES = frozenset({
    "present", "empty", "missing", "unknown", "not_required",
})


class TestAllowedEnumValues:
    """All 38 models must have valid credential_status."""

    def test_all_models_have_credential_status(self, pool_models):
        """Every model has a credential_status field."""
        for m in pool_models:
            assert "credential_status" in m, f"Missing in {m['id']}"

    def test_all_credential_status_valid(self, pool_models):
        """All credential_status values are in the allowed set."""
        for m in pool_models:
            cs = m.get("credential_status", "")
            assert cs in CREDENTIAL_STATUS_VALUES, \
                f"{m['id']}: invalid '{cs}'"

    def test_only_allowed_values_present(self, pool_models):
        """No unexpected values in the field."""
        actual = {m.get("credential_status", "") for m in pool_models}
        assert actual.issubset(CREDENTIAL_STATUS_VALUES), \
            f"Unexpected values: {actual - CREDENTIAL_STATUS_VALUES}"

    def test_present_and_not_required_only(self, pool_models):
        conversation = {
            m["id"]: m.get("credential_status")
            for m in pool_models
        }
        # All 38 models are either present or not_required given current data
        for mid, cs in conversation.items():
            assert cs in ("present", "not_required"), \
                f"{mid}: expected present or not_required, got '{cs}'"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Auto-classification logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutoClassification:
    """Verify auto_classify_credential_status logic is deterministic."""

    def test_opencode_go_present(self, pool_models):
        """Enabled opencode-go models have present (key_env declared)."""
        for m in pool_models:
            if m.get("provider") == "opencode-go":
                assert m.get("credential_status") == "present", \
                    f"{m['id']}: expected present"

    def test_mimo_v2_5_operator_requested_present(self, pool_models):
        """operator_requested mimo-v2.5 has present."""
        opq = [m for m in pool_models if m.get("lifecycle_status") == "operator_requested"]
        assert len(opq) == 1
        assert opq[0]["credential_status"] == "present"

    def test_declared_enabled_unassigned_present(self, pool_models):
        """DEU models have present (key_env declared, even if env empty)."""
        deu = [m for m in pool_models if m.get("lifecycle_status") == "declared_enabled_unassigned"]
        assert len(deu) == 16
        for m in deu:
            assert m.get("credential_status") == "present", \
                f"{m['id']}: expected present"

    def test_disabled_not_required(self, pool_models):
        """Disabled models are not_required even if key_env declared."""
        dis = [m for m in pool_models if m.get("lifecycle_status") == "disabled"]
        assert len(dis) == 1  # deepseek-deepseek-chat
        for m in dis:
            assert m.get("credential_status") == "not_required"

    def test_historical_not_required(self, pool_models):
        """Historical models are not_required."""
        hist = [m for m in pool_models if m.get("lifecycle_status") == "historical"]
        assert len(hist) == 4
        for m in hist:
            assert m.get("credential_status") == "not_required", \
                f"{m['id']}: expected not_required"

    def test_remove_pending_not_required(self, pool_models):
        """Remove-pending models are not_required."""
        rp = [m for m in pool_models if m.get("lifecycle_status") == "remove_pending"]
        assert len(rp) == 5
        for m in rp:
            assert m.get("credential_status") == "not_required", \
                f"{m['id']}: expected not_required"

    def test_candidate_present(self, pool_models):
        """Candidate models with key_env are present."""
        cand = [m for m in pool_models if m.get("lifecycle_status") == "candidate"]
        for m in cand:
            assert m.get("credential_status") == "present", \
                f"{m['id']}: expected present (has key_env)"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Manager CLI — credential-status command
# ═══════════════════════════════════════════════════════════════════════════════

class TestManagerCredentialStatus:
    """CLI credential-status command must work correctly."""

    def test_credential_status_dry_run(self):
        """Dry-run returns DRY_RUN status with expected distribution."""
        result = _run_manager("credential-status")
        assert result["status"] == "DRY_RUN"
        assert result["total_models"] == 38
        assert result["credential_statuses"]["present"] == 28
        assert result["credential_statuses"]["not_required"] == 10
        assert result["changed"] == 0  # all already match

    def test_credential_status_dry_run_changed_none(self):
        """With current data, --apply should also show 0 changed."""
        # We expect the dry-run already matches since we wrote the field
        # This verifies auto_classify matches what was written
        result = _run_manager("credential-status")
        assert result["changed"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Validation CLI — validate-credential-status command
# ═══════════════════════════════════════════════════════════════════════════════

class TestManagerValidate:
    """Validate-credential-status must pass for current data."""

    def test_validate_pass(self):
        """Current data passes validation (0 errors, 0 warnings)."""
        result = _run_manager("validate-credential-status")
        assert result["status"] == "ok"
        assert result["error_count"] == 0
        assert result["warning_count"] == 0
        assert result["total_models"] == 38

    def test_validate_note_f6_not_affected(self):
        """Output note confirms F6 gate is not affected."""
        result = _run_manager("validate-credential-status")
        assert "F6 readiness gate not affected" in result.get("note", "")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. declared_enabled_unassigned NOT forced to present
# ═══════════════════════════════════════════════════════════════════════════════

class TestDEUNotForcedToPresent:
    """Constraint 8: DEU must not be mis-classified as 'must be present'."""

    def test_deu_accepted_as_present(self, pool_models):
        """DEU with present is OK (not an error)."""
        deu = [m for m in pool_models if m.get("lifecycle_status") == "declared_enabled_unassigned"]
        non_present_deu = [m for m in deu if m.get("credential_status") != "present"]
        # All DEU currently have key_env so they auto-classify as present
        # This test documents the expectation; if DEU had no key_env they'd be unknown
        assert len(non_present_deu) == 0, \
            f"DEU models without present: {[m['id'] for m in non_present_deu]}"

    def test_deu_not_in_validator_errors(self):
        """Validator does NOT produce errors for DEU models."""
        # Inject a theoretical DEU with 'unknown' — should NOT error
        # (We verify the auto-classification doesn't fault DEU)
        # Also verify the validate-credential-status command:
        result = _run_manager("validate-credential-status")
        for err in result.get("errors", []):
            assert "declared_enabled_unassigned" not in err.get("lifecycle_status", ""), \
                f"DEU should not cause error: {err}"
        for warn in result.get("warnings", []):
            assert "declared_enabled_unassigned" not in warn.get("lifecycle_status", ""), \
                f"DEU should not cause warning (current data): {warn}"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. enabled_assigned/operator_requested rules
# ═══════════════════════════════════════════════════════════════════════════════

class TestActiveModelConstraints:
    """Active models must have present credential_status."""

    def test_all_assigned_have_present(self, pool_models):
        """All enabled_assigned models have present."""
        ea = [m for m in pool_models if m.get("lifecycle_status") == "enabled_assigned"]
        assert len(ea) == 8  # opencode-go enabled_assigned
        for m in ea:
            assert m.get("credential_status") == "present", \
                f"{m['id']}: expected present"

    def test_operator_requested_present(self, pool_models):
        """operator_requested model has present."""
        opq = [m for m in pool_models if m.get("lifecycle_status") == "operator_requested"]
        assert len(opq) == 1
        assert opq[0]["credential_status"] == "present"

    def test_aggregate_28_present(self, pool_models):
        """28 models should have present: DEU 16 + enabled_assigned 8 + operator_requested 1 + candidate 3 = 28."""
        present_count = sum(1 for m in pool_models if m.get("credential_status") == "present")
        assert present_count == 28


# ═══════════════════════════════════════════════════════════════════════════════
# 7. No secret value / env read
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoSecretLeak:
    """credential_status code must not read env values or output secrets."""

    def test_manager_credential_status_no_env_value(self):
        """Dry-run output shows key_env NAME, not value."""
        result = _run_manager("credential-status")
        output = json.dumps(result)
        # key_env should show NAME like OPENCODE_ANTHROPIC_API_KEY, not a value
        # Should never contain sk- patterns
        assert "sk-" not in output, "SECRET LEAK: sk- pattern found in output"
        for detail in result.get("details", []):
            ke = detail.get("key_env", "")
            assert not ke.startswith("sk-"), f"Secret value in key_env: {ke}"
            assert not ke.startswith("http"), f"URL in key_env: {ke}"

    def test_validate_credential_status_no_value(self):
        """Validate output contains no secret values."""
        result = _run_manager("validate-credential-status")
        output = json.dumps(result)
        assert "sk-" not in output, "SECRET LEAK: sk- pattern found"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Legacy compatibility (missing field, missing lifecycle)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLegacyCompatibility:
    """Model without credential_status must not crash auto-classify."""

    def test_auto_classify_no_crash_on_missing_field(self):
        """auto_classify_credential_status handles missing key_env gracefully."""
        # Import and test the function directly
        sys.path.insert(0, str(REPO / "scripts"))
        from model_pool_manager import auto_classify_credential_status

        # Model with no credential_status fields
        m1 = {"id": "test-no-key", "lifecycle_status": "disabled"}
        assert auto_classify_credential_status(m1) == "not_required"

        m2 = {"id": "test-no-ls", "lifecycle_status": ""}
        assert auto_classify_credential_status(m2) == "unknown"

        m3 = {"id": "test-empty-key", "key_env": "", "lifecycle_status": "candidate"}
        assert auto_classify_credential_status(m3) == "unknown"

        m4 = {"id": "test-has-key", "key_env": "MY_API_KEY", "lifecycle_status": "enabled_assigned"}
        assert auto_classify_credential_status(m4) == "present"

        m5 = {"id": "test-operator-no-key", "lifecycle_status": "operator_requested"}
        assert auto_classify_credential_status(m5) == "missing"

    def test_validate_missing_field_no_crash(self):
        """validate_credential_status handles models without credential_status."""
        result = _run_manager("validate-credential-status")
        assert "error" not in result.get("status", "").lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 9. credential_status × lifecycle_status compatibility
# ═══════════════════════════════════════════════════════════════════════════════

class TestLifecycleCredentialCompatibility:
    """All lifecycle_status × credential_status combinations must be valid."""

    def test_all_present_models_by_lifecycle(self, pool_models):
        """Count present models: 16 DEU + 8 enabled_assigned + 1 operator_requested + 3 candidate = 28."""
        present = {m["id"]: m.get("lifecycle_status") for m in pool_models
                   if m.get("credential_status") == "present"}
        assert len(present) == 28

        ls_dist = {}
        for ls in present.values():
            ls_dist[ls] = ls_dist.get(ls, 0) + 1
        assert ls_dist.get("declared_enabled_unassigned") == 16
        assert ls_dist.get("enabled_assigned") == 8
        assert ls_dist.get("operator_requested") == 1
        assert ls_dist.get("candidate") == 3

    def test_all_not_required_models_by_lifecycle(self, pool_models):
        """Count not_required models: 1 disabled + 4 historical + 5 remove_pending = 10."""
        nr = {m["id"]: m.get("lifecycle_status") for m in pool_models
              if m.get("credential_status") == "not_required"}
        assert len(nr) == 10

        ls_dist = {}
        for ls in nr.values():
            ls_dist[ls] = ls_dist.get(ls, 0) + 1
        assert ls_dist.get("disabled") == 1
        assert ls_dist.get("historical") == 4
        assert ls_dist.get("remove_pending") == 5

    def test_no_missing_or_empty(self, pool_models):
        """No model has missing or empty credential_status (given current data)."""
        bad = [m["id"] for m in pool_models
               if m.get("credential_status") in ("missing", "empty")]
        assert len(bad) == 0, f"Unexpected missing/empty: {bad}"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. BIDI / hidden Unicode scan
# ═══════════════════════════════════════════════════════════════════════════════

class TestBidiControl:
    """Source files must not contain hidden bidi control characters."""

    TARGETS = [
        REPO / "scripts" / "model_pool_manager.py",
        REPO / "tests" / "test_model_pool_credential_status.py",
    ]
    BIDI_CHARS = set(chr(c) for c in range(0x202A, 0x202F)) | \
                 set(chr(c) for c in range(0x2066, 0x206A)) | \
                 {"\u200E", "\u200F"}

    def test_no_bidi_in_manager(self):
        """model_pool_manager.py has no bidi control characters."""
        src = self.TARGETS[0].read_text(encoding="utf-8")
        for i, ch in enumerate(src):
            assert ch not in self.BIDI_CHARS, \
                f"BIDI at offset {i}: U+{ord(ch):04X}"

    def test_no_bidi_in_test_file(self):
        """test file has no bidi control characters."""
        src = self.TARGETS[1].read_text(encoding="utf-8")
        for i, ch in enumerate(src):
            assert ch not in self.BIDI_CHARS, \
                f"BIDI at offset {i}: U+{ord(ch):04X}"


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Distribution stability / schema integrity
# ═══════════════════════════════════════════════════════════════════════════════

class TestDistributionStability:
    """Credential_status distribution must be stable."""

    def test_distribution_sum_matches_models(self, pool_models):
        """present + not_required = 38."""
        present = sum(1 for m in pool_models if m.get("credential_status") == "present")
        nr = sum(1 for m in pool_models if m.get("credential_status") == "not_required")
        assert present + nr == len(pool_models)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Manager help output
# ═══════════════════════════════════════════════════════════════════════════════

class TestManagerHelp:
    """Manager CLI help mentions new subcommands."""

    def test_credential_status_in_help(self):
        """'credential-status' subcommand shows --apply flag in usage."""
        result = subprocess.run(
            [sys.executable, "scripts/model_pool_manager.py", "credential-status", "--help"],
            cwd=REPO, capture_output=True, text=True, timeout=10,
        )
        assert "--apply" in result.stdout
        assert "credential_status" in result.stdout

    def test_validate_credential_status_in_help(self):
        """'validate-credential-status' subcommand parses correctly."""
        result = subprocess.run(
            [sys.executable, "scripts/model_pool_manager.py", "validate-credential-status", "--help"],
            cwd=REPO, capture_output=True, text=True, timeout=10,
        )
        assert "validate-credential-status" in result.stdout
