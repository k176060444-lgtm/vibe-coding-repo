#!/usr/bin/env python3
"""Tests for endpoint_ref additive schema (Phase 3 PR-6).

Covers:
- Allowed enum values (base_url_env, not_required, unknown, missing)
- Invalid endpoint_ref rejection
- Auto-classification logic (deterministic, no URL read)
- Lifecycle × endpoint_ref compatibility
- declared_enabled_unassigned NOT forced to runtime endpoint
- enabled_assigned/operator_requested constraints
- No URL value read, no env var read
- Legacy compatibility (no field = no crash)
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
OK_VALS = {"base_url_env", "not_required", "unknown", "missing"}


def _run_manager(*args: str) -> dict:
    result = subprocess.run(
        [sys.executable, "scripts/model_pool_manager.py", *args],
        cwd=REPO, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0 and result.stderr:
        raise RuntimeError(f"Manager failed: {result.stderr[:300]}")
    return json.loads(result.stdout)


def _load_pool() -> dict:
    import yaml
    with open(REPO / "scripts" / "model_pool.yaml") as f:
        return yaml.safe_load(f)


def _get_models() -> list[dict]:
    return _load_pool().get("models", [])


@pytest.fixture
def pool_models() -> list[dict]:
    return _get_models()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Allowed enum values
# ═══════════════════════════════════════════════════════════════════════════════

class TestAllowedEnumValues:
    """All 38 models must have valid endpoint_ref."""

    def test_all_models_have_endpoint_ref(self, pool_models):
        for m in pool_models:
            assert "endpoint_ref" in m, f"Missing in {m['id']}"

    def test_all_endpoint_ref_valid(self, pool_models):
        for m in pool_models:
            ref = m.get("endpoint_ref", "")
            assert ref in OK_VALS, f"{m['id']}: invalid '{ref}'"

    def test_only_allowed_values_present(self, pool_models):
        actual = {m.get("endpoint_ref", "") for m in pool_models}
        assert actual.issubset(OK_VALS), f"Unexpected: {actual - OK_VALS}"

    def test_base_url_env_and_not_required_only(self, pool_models):
        for m in pool_models:
            ref = m.get("endpoint_ref")
            assert ref in ("base_url_env", "not_required"), \
                f"{m['id']}: expected base_url_env or not_required, got '{ref}'"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Auto-classification logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestAutoClassification:
    """Verify auto_classify_endpoint_ref logic is deterministic."""

    def test_opencode_go_base_url_env(self, pool_models):
        for m in pool_models:
            if m.get("provider") == "opencode-go":
                assert m.get("endpoint_ref") == "base_url_env", \
                    f"{m['id']}: expected base_url_env"

    def test_declared_enabled_unassigned_base_url_env(self, pool_models):
        deu = [m for m in pool_models if m.get("lifecycle_status") == "declared_enabled_unassigned"]
        assert len(deu) == 16
        for m in deu:
            assert m.get("endpoint_ref") == "base_url_env", \
                f"{m['id']}: expected base_url_env"

    def test_disabled_not_required(self, pool_models):
        dis = [m for m in pool_models if m.get("lifecycle_status") == "disabled"]
        assert len(dis) == 1
        for m in dis:
            assert m.get("endpoint_ref") == "not_required"

    def test_historical_not_required(self, pool_models):
        hist = [m for m in pool_models if m.get("lifecycle_status") == "historical"]
        assert len(hist) == 4
        for m in hist:
            assert m.get("endpoint_ref") == "not_required", f"{m['id']}"

    def test_remove_pending_not_required(self, pool_models):
        rp = [m for m in pool_models if m.get("lifecycle_status") == "remove_pending"]
        assert len(rp) == 5
        for m in rp:
            assert m.get("endpoint_ref") == "not_required", f"{m['id']}"

    def test_candidate_base_url_env(self, pool_models):
        cand = [m for m in pool_models if m.get("lifecycle_status") == "candidate"]
        for m in cand:
            assert m.get("endpoint_ref") == "base_url_env", f"{m['id']} (has base_url_env)"

    def test_operator_requested_base_url_env(self, pool_models):
        opq = [m for m in pool_models if m.get("lifecycle_status") == "operator_requested"]
        assert len(opq) == 1
        assert opq[0].get("endpoint_ref") == "base_url_env"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Manager CLI — endpoint-ref command
# ═══════════════════════════════════════════════════════════════════════════════

class TestManagerEndpointRef:
    def test_dry_run(self):
        result = _run_manager("endpoint-ref")
        assert result["status"] == "DRY_RUN"
        assert result["total_models"] == 38
        assert result["endpoint_refs"]["base_url_env"] == 28
        assert result["endpoint_refs"]["not_required"] == 10
        assert result["changed"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Validation CLI — validate-endpoint-ref command
# ═══════════════════════════════════════════════════════════════════════════════

class TestManagerValidate:
    def test_validate_pass(self):
        result = _run_manager("validate-endpoint-ref")
        assert result["status"] == "ok"
        assert result["error_count"] == 0
        assert result["warning_count"] == 0
        assert result["total_models"] == 38

    def test_validate_note_f6_not_affected(self):
        result = _run_manager("validate-endpoint-ref")
        assert "F6 readiness gate not affected" in result.get("note", "")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. DEU NOT forced to runtime endpoint blocker
# ═══════════════════════════════════════════════════════════════════════════════

class TestDEUNotForcedToEndpoint:
    def test_deu_all_base_url_env(self, pool_models):
        deu = [m for m in pool_models if m.get("lifecycle_status") == "declared_enabled_unassigned"]
        for m in deu:
            assert m.get("endpoint_ref") == "base_url_env", \
                f"{m['id']}: expected base_url_env (ref NAME, not URL value)"

    def test_deu_not_in_validator_errors(self):
        result = _run_manager("validate-endpoint-ref")
        for err in result.get("errors", []):
            assert "declared_enabled_unassigned" not in err.get("lifecycle_status", ""), \
                f"DEU should not cause error: {err}"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. active model constraints
# ═══════════════════════════════════════════════════════════════════════════════

class TestActiveModelConstraints:
    def test_all_assigned_base_url_env(self, pool_models):
        ea = [m for m in pool_models if m.get("lifecycle_status") == "enabled_assigned"]
        assert len(ea) == 8
        for m in ea:
            assert m.get("endpoint_ref") == "base_url_env", f"{m['id']}"

    def test_aggregate_28_base_url_env(self, pool_models):
        count = sum(1 for m in pool_models if m.get("endpoint_ref") == "base_url_env")
        assert count == 28


# ═══════════════════════════════════════════════════════════════════════════════
# 7. No URL value / env read
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoSecretLeak:
    def test_no_url_in_dry_run(self):
        result = _run_manager("endpoint-ref")
        output = json.dumps(result)
        assert "http://" not in output, "URL leak: http:// found"
        assert "https://" not in output, "URL leak: https:// found"
        assert "sk-" not in output, "Secret leak: sk- found"
        for detail in result.get("details", []):
            be = detail.get("base_url_env", "")
            assert not be.startswith("http"), f"URL in base_url_env: {be}"

    def test_no_url_in_validate(self):
        result = _run_manager("validate-endpoint-ref")
        output = json.dumps(result)
        assert "http://" not in output
        assert "https://" not in output


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Legacy compatibility
# ═══════════════════════════════════════════════════════════════════════════════

class TestLegacyCompatibility:
    def test_auto_classify_no_crash_missing_field(self):
        sys.path.insert(0, str(REPO / "scripts"))
        from model_pool_manager import auto_classify_endpoint_ref

        m1 = {"id": "test-no-base", "lifecycle_status": "disabled"}
        assert auto_classify_endpoint_ref(m1) == "not_required"

        m2 = {"id": "test-no-ls", "lifecycle_status": ""}
        assert auto_classify_endpoint_ref(m2) == "unknown"

        m3 = {"id": "test-empty-base", "base_url_env": "", "lifecycle_status": "candidate"}
        assert auto_classify_endpoint_ref(m3) == "unknown"

        m4 = {"id": "test-has-base", "base_url_env": "MY_BASE_URL", "lifecycle_status": "enabled_assigned"}
        assert auto_classify_endpoint_ref(m4) == "base_url_env"

        m5 = {"id": "test-operator-no-base", "lifecycle_status": "operator_requested"}
        assert auto_classify_endpoint_ref(m5) == "missing"

    def test_validate_missing_field_no_crash(self):
        result = _run_manager("validate-endpoint-ref")
        assert "error" not in result.get("status", "").lower()


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Lifecycle × endpoint_ref compatibility
# ═══════════════════════════════════════════════════════════════════════════════

class TestLifecycleEndpointCompat:
    def test_all_base_url_env_by_lifecycle(self, pool_models):
        base = {m["id"]: m.get("lifecycle_status") for m in pool_models
                if m.get("endpoint_ref") == "base_url_env"}
        assert len(base) == 28
        ls_dist = {}
        for ls in base.values():
            ls_dist[ls] = ls_dist.get(ls, 0) + 1
        assert ls_dist.get("declared_enabled_unassigned") == 16
        assert ls_dist.get("enabled_assigned") == 8
        assert ls_dist.get("operator_requested") == 1
        assert ls_dist.get("candidate") == 3

    def test_all_not_required_by_lifecycle(self, pool_models):
        nr = {m["id"]: m.get("lifecycle_status") for m in pool_models
              if m.get("endpoint_ref") == "not_required"}
        assert len(nr) == 10
        ls_dist = {}
        for ls in nr.values():
            ls_dist[ls] = ls_dist.get(ls, 0) + 1
        assert ls_dist.get("disabled") == 1
        assert ls_dist.get("historical") == 4
        assert ls_dist.get("remove_pending") == 5

    def test_no_missing_or_unknown(self, pool_models):
        bad = [m["id"] for m in pool_models
               if m.get("endpoint_ref") in ("missing", "unknown")]
        assert len(bad) == 0, f"Unexpected missing/unknown: {bad}"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. BIDI scan
# ═══════════════════════════════════════════════════════════════════════════════

class TestBidiControl:
    TARGETS = [
        REPO / "scripts" / "model_pool_manager.py",
        REPO / "tests" / "test_model_pool_endpoint_ref.py",
    ]
    BIDI_CHARS = set(chr(c) for c in range(0x202A, 0x202F)) | \
                 set(chr(c) for c in range(0x2066, 0x206A)) | \
                 {"\u200E", "\u200F"}

    def test_no_bidi_in_manager(self):
        src = self.TARGETS[0].read_text(encoding="utf-8")
        for i, ch in enumerate(src):
            assert ch not in self.BIDI_CHARS, f"BIDI at offset {i}: U+{ord(ch):04X}"

    def test_no_bidi_in_test_file(self):
        src = self.TARGETS[1].read_text(encoding="utf-8")
        for i, ch in enumerate(src):
            assert ch not in self.BIDI_CHARS, f"BIDI at offset {i}: U+{ord(ch):04X}"


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Distribution stability
# ═══════════════════════════════════════════════════════════════════════════════

class TestDistribution:
    def test_sum_matches_models(self, pool_models):
        bu = sum(1 for m in pool_models if m.get("endpoint_ref") == "base_url_env")
        nr = sum(1 for m in pool_models if m.get("endpoint_ref") == "not_required")
        assert bu + nr == len(pool_models)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Manager help
# ═══════════════════════════════════════════════════════════════════════════════

class TestHelp:
    def test_endpoint_ref_in_help(self):
        result = subprocess.run(
            [sys.executable, "scripts/model_pool_manager.py", "endpoint-ref", "--help"],
            cwd=REPO, capture_output=True, text=True, timeout=10,
        )
        assert "--apply" in result.stdout

    def test_validate_endpoint_ref_in_help(self):
        result = subprocess.run(
            [sys.executable, "scripts/model_pool_manager.py", "validate-endpoint-ref", "--help"],
            cwd=REPO, capture_output=True, text=True, timeout=10,
        )
        assert "validate-endpoint-ref" in result.stdout
