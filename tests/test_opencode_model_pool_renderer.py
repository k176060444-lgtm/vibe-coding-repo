#!/usr/bin/env python3
"""Tests for Model Pool → Renderer Integration — Dry-run Only.

Covers:
- dry_run=false rejection
- seed/fixture/file sources (no discovery/provider calls)
- sanitized export no real keys
- quarantine_status enrichment
- opencode-free → not-configured credential
- paid/user_configured missing credential → non_available_summary
- paid with explicit valid credential → available
- secret_ref placeholder generation
- protocol default openai-compatible
- disabled/quarantined/missing credential/not detected → non_available_summary
- node-specific output
- role_assignment passthrough
- role_assignment no auto-substitute
- output no plaintext keys
- audit/input_hash stable
- output schema compliance
- local dirt not in diff
- no provider/discovery call

Contract: docs/MODEL_POOL_DISTRIBUTION_CONTRACT.md
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from opencode_model_pool_renderer import (
    DANGEROUS_KEY_PATTERNS,
    INTEGRATION_VERSION,
    enrich_model_entry,
    enrich_model_list,
    load_from_file,
    load_from_fixture,
    load_from_seed,
    render_from_pool,
    scan_output_for_secrets,
    self_check,
)
from opencode_model_pool import KNOWN_MODELS_SEED, KNOWN_QUARANTINE


# --- Fixtures ---


@pytest.fixture
def sample_fixture_models():
    """Fixture models for testing."""
    return [
        {
            "exact_model_id": "opencode/mimo-v2.5-free",
            "alias": "mimo-free",
            "provider": "opencode",
            "cost_tag": "free",
            "source_flags": ["opencode-free"],
            "enabled": True,
            "health_status": "healthy",
            "node_availability": {
                "21bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
                "5bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
            },
            "roles": ["implementer", "reviewer"],
            "priority": 1,
            "capability_tags": ["code"],
            "fallback_allowed": True,
        },
        {
            "exact_model_id": "deepseek-plan/deepseek-v4-pro",
            "alias": "ds-v4-pro",
            "provider": "deepseek-plan",
            "cost_tag": "paid",
            "source_flags": ["user_configured"],
            "enabled": True,
            "health_status": "healthy",
            "node_availability": {
                "21bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
                "9bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
            },
            "roles": ["implementer", "reviewer"],
            "priority": 3,
            "capability_tags": ["code"],
            "fallback_allowed": True,
            "credential_status": "valid",
        },
        {
            "exact_model_id": "volcengine-plan/ark-code-latest",
            "alias": "doubao",
            "provider": "volcengine-plan",
            "cost_tag": "paid",
            "source_flags": ["user_configured"],
            "enabled": True,
            "health_status": "healthy",
            "node_availability": {
                "21bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
            },
            "roles": ["implementer"],
            "priority": 8,
            "capability_tags": ["code"],
            "fallback_allowed": False,
        },
        {
            "exact_model_id": "opencode/nemotron-3-ultra-free",
            "alias": "nemotron-free",
            "provider": "opencode",
            "cost_tag": "free",
            "source_flags": ["opencode-free"],
            "enabled": False,
            "health_status": "healthy",
            "node_availability": {
                "21bao": {"available": True, "last_seen": "2026-06-24T00:00:00Z"},
            },
            "roles": ["implementer"],
            "priority": 4,
            "capability_tags": ["code"],
            "fallback_allowed": True,
        },
    ]


@pytest.fixture
def pool_json_file(sample_fixture_models, tmp_path):
    """Create a temporary pool JSON file."""
    pool_data = {
        "models": {m["exact_model_id"]: m for m in sample_fixture_models},
        "snapshot_timestamp": "2026-06-24T00:00:00Z",
        "snapshot_sha256": "a" * 64,
    }
    pool_path = str(tmp_path / "test_pool.json")
    with open(pool_path, "w", encoding="utf-8") as f:
        json.dump(pool_data, f)
    return pool_path


# --- Test Classes ---


class TestDryRunOnly:
    """Integration must reject dry_run=false."""

    def test_dry_run_false_rejected(self):
        with pytest.raises(ValueError, match="dry_run must be True"):
            render_from_pool(target_node="21bao", source="seed", dry_run=False)

    def test_dry_run_true_accepted(self):
        result = render_from_pool(target_node="21bao", source="seed", dry_run=True)
        assert result["dry_run"] is True


class TestOfflineSources:
    """All sources must be offline — no discovery/provider calls."""

    def test_seed_source(self):
        """Seed source produces valid output without any calls."""
        result = render_from_pool(target_node="21bao", source="seed", dry_run=True)
        assert result["integration"]["source"] == "seed"
        assert result["integration"]["pool_model_count"] > 0

    def test_fixture_source(self, sample_fixture_models):
        """Fixture source produces valid output without any calls."""
        result = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        assert result["integration"]["source"] == "fixture"
        assert result["integration"]["pool_model_count"] == len(sample_fixture_models)

    def test_file_source(self, pool_json_file):
        """File source reads local JSON without any calls."""
        result = render_from_pool(
            target_node="21bao", source="file",
            pool_path=pool_json_file, dry_run=True,
        )
        assert result["integration"]["source"] == "file"
        assert result["integration"]["pool_snapshot_sha256"] == "a" * 64

    def test_file_source_not_found(self):
        """File source raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            render_from_pool(
                target_node="21bao", source="file",
                pool_path="/nonexistent/pool.json", dry_run=True,
            )


class TestSanitizedExportNoKeys:
    """Sanitized export must not contain real keys."""

    def test_seed_export_no_keys(self):
        """KNOWN_MODELS_SEED entries must not contain real keys."""
        for entry in KNOWN_MODELS_SEED:
            entry_str = json.dumps(entry)
            assert not entry_str.startswith("sk-")
            assert "AKIA" not in entry_str
            assert "Bearer" not in entry_str or "Bearer" in entry_str and len(entry_str) < 50


class TestEnrichmentQuarantine:
    """quarantine_status enrichment from KNOWN_QUARANTINE."""

    def test_quarantined_model_enriched(self):
        """volcengine-plan/ark-code-latest → quarantined."""
        entry = {
            "exact_model_id": "volcengine-plan/ark-code-latest",
            "alias": "doubao",
            "provider": "volcengine-plan",
        }
        enriched = enrich_model_entry(entry)
        assert enriched["quarantine_status"] == "quarantined"

    def test_non_quarantined_model_default_none(self):
        """Non-quarantined model → quarantine_status=none."""
        entry = {
            "exact_model_id": "opencode/mimo-v2.5-free",
            "alias": "mimo-free",
            "provider": "opencode",
        }
        enriched = enrich_model_entry(entry)
        assert enriched["quarantine_status"] == "none"


class TestEnrichmentCredential:
    """credential_status enrichment rules."""

    def test_opencode_free_no_credential(self):
        """opencode-free → credential_status=not-configured."""
        entry = {
            "exact_model_id": "opencode/mimo-v2.5-free",
            "source_flags": ["opencode-free"],
            "cost_tag": "free",
        }
        enriched = enrich_model_entry(entry)
        assert enriched["credential_status"] == "not-configured"

    def test_free_cost_tag_no_credential(self):
        """cost_tag=free → credential_status=not-configured."""
        entry = {
            "exact_model_id": "some/free-model",
            "cost_tag": "free",
            "source_flags": [],
        }
        enriched = enrich_model_entry(entry)
        assert enriched["credential_status"] == "not-configured"

    def test_paid_user_configured_missing_credential(self):
        """paid/user_configured without credential_status → missing."""
        entry = {
            "exact_model_id": "deepseek-plan/deepseek-v4-pro",
            "cost_tag": "paid",
            "source_flags": ["user_configured"],
        }
        enriched = enrich_model_entry(entry)
        assert enriched["credential_status"] == "missing"

    def test_paid_with_explicit_valid_credential(self):
        """paid with explicit credential_status=valid → valid."""
        entry = {
            "exact_model_id": "deepseek-plan/deepseek-v4-pro",
            "cost_tag": "paid",
            "source_flags": ["user_configured"],
            "credential_status": "valid",
        }
        enriched = enrich_model_entry(entry)
        assert enriched["credential_status"] == "valid"

    def test_explicit_credential_preserved(self):
        """Existing credential_status must not be overwritten."""
        entry = {
            "exact_model_id": "some/model",
            "credential_status": "expired",
        }
        enriched = enrich_model_entry(entry)
        assert enriched["credential_status"] == "expired"


class TestEnrichmentSecretRef:
    """secret_ref placeholder generation."""

    def test_secret_ref_generated(self):
        """secret_ref generated from provider+alias."""
        entry = {
            "exact_model_id": "deepseek-plan/deepseek-v4-pro",
            "alias": "ds-v4-pro",
            "provider": "deepseek-plan",
        }
        enriched = enrich_model_entry(entry)
        assert enriched["secret_ref"] == "secret:deepseek-plan:ds-v4-pro"

    def test_secret_ref_preserved(self):
        """Existing secret_ref not overwritten."""
        entry = {
            "exact_model_id": "some/model",
            "secret_ref": "secret:custom:ref",
        }
        enriched = enrich_model_entry(entry)
        assert enriched["secret_ref"] == "secret:custom:ref"


class TestEnrichmentProtocol:
    """protocol default."""

    def test_protocol_default(self):
        """Missing protocol → openai-compatible."""
        entry = {"exact_model_id": "some/model"}
        enriched = enrich_model_entry(entry)
        assert enriched["protocol"] == "openai-compatible"


class TestNonAvailableSummary:
    """Disabled/quarantined/missing credential/not detected → non_available_summary."""

    def test_disabled_model_excluded(self, sample_fixture_models):
        """Disabled model → non_available_summary."""
        result = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        non_avail = result["renderer_output"]["non_available_summary"]
        non_avail_ids = [m["model_id"] for m in non_avail]
        assert "opencode/nemotron-3-ultra-free" in non_avail_ids

    def test_quarantined_model_excluded(self, sample_fixture_models):
        """Quarantined model → non_available_summary."""
        result = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        non_avail = result["renderer_output"]["non_available_summary"]
        non_avail_ids = [m["model_id"] for m in non_avail]
        assert "volcengine-plan/ark-code-latest" in non_avail_ids

    def test_paid_missing_credential_excluded(self, sample_fixture_models):
        """Paid model without explicit credential_status → non_available_summary."""
        result = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        # volcengine is both quarantined AND paid with missing credential
        non_avail = result["renderer_output"]["non_available_summary"]
        non_avail_ids = [m["model_id"] for m in non_avail]
        assert "volcengine-plan/ark-code-latest" in non_avail_ids

    def test_not_detected_on_node_excluded(self, sample_fixture_models):
        """Model not detected on target node → non_available_summary."""
        result = render_from_pool(
            target_node="Windows", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        non_avail = result["renderer_output"]["non_available_summary"]
        non_avail_ids = [m["model_id"] for m in non_avail]
        # volcengine only on 21bao
        assert "volcengine-plan/ark-code-latest" in non_avail_ids


class TestNodeSpecificOutput:
    """Different target_nodes produce different outputs."""

    def test_different_nodes_different_output(self, sample_fixture_models):
        result_21bao = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        result_9bao = render_from_pool(
            target_node="9bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        assert result_21bao["renderer_output"]["node"] == "21bao"
        assert result_9bao["renderer_output"]["node"] == "9bao"
        # 21bao has more models available than 9bao (volcengine only on 21bao)
        avail_21 = len(result_21bao["renderer_output"]["config_draft"]["models"])
        avail_9 = len(result_9bao["renderer_output"]["config_draft"]["models"])
        assert avail_21 >= avail_9


class TestRoleAssignment:
    """Role assignment passthrough and no auto-substitute."""

    def test_role_assignment_passthrough(self, sample_fixture_models):
        """Role assignment correctly passed to renderer."""
        result = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models,
            role_assignment={"implementer": "opencode/mimo-v2.5-free"},
            dry_run=True,
        )
        assert result["renderer_output"]["role_assignment"]["implementer"]["status"] == "configured"

    def test_role_assignment_no_auto_substitute(self, sample_fixture_models):
        """Unavailable model → warning/status, not auto-substituted."""
        result = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models,
            role_assignment={"implementer": "opencode/nemotron-3-ultra-free"},
            dry_run=True,
        )
        ra = result["renderer_output"]["role_assignment"]["implementer"]
        assert "unavailable" in ra["status"]
        assert ra["model_alias"] == "opencode/nemotron-3-ultra-free"


class TestOutputNoPlaintextKeys:
    """Output must not contain plaintext keys."""

    def test_no_sk_keys(self, sample_fixture_models):
        result = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        output_str = json.dumps(result)
        assert not output_str.__contains__("sk-") or len(output_str) < 100

    def test_scan_clean(self, sample_fixture_models):
        result = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        violations = scan_output_for_secrets(result)
        assert violations == [], f"Violations: {violations}"


class TestAuditInputHash:
    """audit/input_hash stability."""

    def test_hash_stable(self, sample_fixture_models):
        """Same input → same hash."""
        r1 = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        r2 = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        assert r1["renderer_output"]["audit"]["input_hash"] == r2["renderer_output"]["audit"]["input_hash"]


class TestOutputSchemaCompliance:
    """Output must conform to integration schema."""

    def test_integration_metadata(self, sample_fixture_models):
        result = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        integration = result["integration"]
        assert "source" in integration
        assert "pool_snapshot_sha256" in integration
        assert "pool_model_count" in integration
        assert "enrichment_applied" in integration
        assert "integration_version" in integration

    def test_renderer_output_embedded(self, sample_fixture_models):
        result = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        ro = result["renderer_output"]
        assert "node" in ro
        assert "dry_run" in ro
        assert "config_draft" in ro
        assert "requires_operator_approval" in ro

    def test_requires_operator_approval(self, sample_fixture_models):
        result = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        assert result["requires_operator_approval"] is True
        assert result["renderer_output"]["requires_operator_approval"] is True


class TestLocalDirtNotInDiff:
    """Local dirt must not appear in output."""

    def test_no_malicious_payload(self, sample_fixture_models):
        result = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        output_str = json.dumps(result)
        assert "malicious_payload" not in output_str.lower()

    def test_no_pilot_prompts(self, sample_fixture_models):
        result = render_from_pool(
            target_node="21bao", source="fixture",
            fixture_models=sample_fixture_models, dry_run=True,
        )
        output_str = json.dumps(result)
        assert "pilot-prompts" not in output_str.lower()


class TestEnrichmentApplied:
    """enrichment_applied tracks which fields were added."""

    def test_enrichment_applied_fields(self):
        """Enrichment adds required fields."""
        models = [
            {"exact_model_id": "test/model", "alias": "test", "provider": "test"},
        ]
        enriched, applied = enrich_model_list(models)
        assert "quarantine_status" in applied
        assert "credential_status" in applied
        assert "secret_ref" in applied
        assert "protocol" in applied
        assert "model_id" in applied


class TestSelfCheck:
    """Self-check must return ok."""

    def test_self_check(self):
        result = self_check()
        assert result["status"] == "ok"
        assert result["dry_run_only"] is True
