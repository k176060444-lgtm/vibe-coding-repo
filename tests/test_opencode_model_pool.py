"""Tests for OpenCode Dynamic Model Pool and Operator Model Approval Gate."""

import json
import os
import sys
import tempfile

import pytest
import unittest

# Add scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from opencode_model_pool import (
    ModelPool,
    auto_capability_tags,
    auto_tag_cost,
    new_model_entry,
)
from operator_model_approval_gate import (
    generate_approval_template,
    validate_approval,
)


# --- Fixtures ---

@pytest.fixture
def tmp_pool(tmp_path):
    """Create a temporary ModelPool."""
    pool_path = str(tmp_path / "test_pool.json")
    return ModelPool(pool_path)


@pytest.fixture
def populated_pool(tmp_path):
    """Create a ModelPool with some models."""
    pool_path = str(tmp_path / "pop_pool.json")
    pool = ModelPool(pool_path)
    pool.discover_node("21bao", [
        "opencode/mimo-v2.5-free",
        "opencode/deepseek-v4-flash-free",
        "opencode/nemotron-3-ultra-free",
    ])
    pool.discover_node("5bao", [
        "opencode/mimo-v2.5-free",
        "opencode/deepseek-v4-flash-free",
    ])
    return pool


@pytest.fixture
def valid_approval():
    return {
        "job_id": "test-001",
        "node": "21bao",
        "exact_model_id": "opencode/mimo-v2.5-free",
        "model_alias": "mimo-free",
        "model_pool_snapshot_sha256": "a" * 64,
        "prompt_sha256": "b" * 64,
        "max_calls": 1,
        "fallback_policy": "disabled",
        "approval_status": "APPROVED",
        "approved_by": "Operator",
        "approved_at": "2026-06-20T00:00:00Z",
    }


# --- auto_tag_cost tests ---

class TestAutoTagCost:
    def test_free_model(self):
        assert auto_tag_cost("opencode/mimo-v2.5-free") == "free"

    def test_free_flash(self):
        assert auto_tag_cost("opencode/deepseek-v4-flash-free") == "free"

    def test_pro_model(self):
        assert auto_tag_cost("openai/gpt-4-pro") == "cost"

    def test_unknown_model(self):
        assert auto_tag_cost("opencode/custom-model") == "unknown"


# --- auto_capability_tags tests ---

class TestAutoCapabilityTags:
    def test_code_model(self):
        tags = auto_capability_tags("opencode/deepseek-v4-flash-free")
        assert "free" in tags
        assert "fast" in tags
        assert "code" in tags

    def test_ultra_model(self):
        tags = auto_capability_tags("opencode/nemotron-3-ultra-free")
        assert "strong" in tags or "free" in tags


# --- ModelPool discover tests ---

class TestModelPoolDiscover:
    def test_discover_add(self, tmp_pool):
        result = tmp_pool.discover_node("21bao", ["opencode/model-a", "opencode/model-b"])
        assert len(result["added"]) == 2
        assert "opencode/model-a" in tmp_pool.models

    def test_discover_diff_new(self, tmp_pool):
        tmp_pool.discover_node("n", ["opencode/model-a"])
        result = tmp_pool.discover_node("n", ["opencode/model-a", "opencode/model-b"])
        assert "opencode/model-b" in result["added"]

    def test_discover_diff_disappeared(self, tmp_pool):
        """Disappeared models are marked unavailable, not deleted."""
        tmp_pool.discover_node("n", ["opencode/model-a", "opencode/model-b"])
        result = tmp_pool.discover_node("n", ["opencode/model-a"])
        assert "opencode/model-b" in result["disappeared"]
        assert "opencode/model-b" in tmp_pool.models  # not deleted
        avail = tmp_pool.models["opencode/model-b"]["node_availability"]["n"]
        assert avail["available"] is False

    def test_snapshot_sha_changes(self, tmp_pool):
        tmp_pool.discover_node("n", ["opencode/model-a"])
        sha1 = tmp_pool.snapshot_sha256
        tmp_pool.discover_node("n", ["opencode/model-a", "opencode/model-b"])
        sha2 = tmp_pool.snapshot_sha256
        assert sha1 != sha2

    def test_snapshot_sha_stable(self, tmp_pool):
        tmp_pool.discover_node("n", ["opencode/model-a"])
        sha1 = tmp_pool.snapshot_sha256
        tmp_pool.save()  # re-save without changes
        sha2 = tmp_pool.snapshot_sha256
        assert sha1 == sha2


# --- ModelPool stale tests ---

class TestModelPoolStale:
    def test_stale_old_timestamp(self, tmp_pool):
        tmp_pool.snapshot_timestamp = "2020-01-01T00:00:00Z"
        assert tmp_pool.is_snapshot_stale() is True

    def test_not_stale_recent(self, tmp_pool):
        from datetime import datetime, timezone
        tmp_pool.snapshot_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert tmp_pool.is_snapshot_stale() is False

    def test_stale_none(self, tmp_pool):
        tmp_pool.snapshot_timestamp = None
        assert tmp_pool.is_snapshot_stale() is True


# --- ModelPool alias resolve tests ---

class TestModelPoolResolve:
    def test_resolve_alias(self, populated_pool):
        # mimo-v2.5-free has auto-alias "mimo-v2.5-free"
        resolved = populated_pool.resolve_alias("mimo-v2.5-free", "21bao")
        assert resolved == "opencode/mimo-v2.5-free"

    def test_resolve_alias_not_found(self, populated_pool):
        assert populated_pool.resolve_alias("nonexistent", "21bao") is None

    def test_resolve_alias_unavailable_node(self, populated_pool):
        # nemotron not on 5bao
        resolved = populated_pool.resolve_alias("nemotron-3-ultra-free", "5bao")
        assert resolved is None

    def test_resolve_alias_wrong_node(self, tmp_pool):
        """Alias mismatch fails closed."""
        tmp_pool.discover_node("n1", ["opencode/model-x"])
        resolved = tmp_pool.resolve_alias("model-x", "n2")
        assert resolved is None


# --- ModelPool validate tests ---

class TestModelPoolValidate:
    def test_validate_ok(self, populated_pool):
        ok, msg = populated_pool.validate_model("opencode/mimo-v2.5-free", "21bao")
        assert ok is True

    def test_validate_not_in_pool(self, populated_pool):
        ok, msg = populated_pool.validate_model("opencode/nonexistent", "21bao")
        assert ok is False
        assert "not in pool" in msg

    def test_validate_unavailable_node(self, populated_pool):
        ok, msg = populated_pool.validate_model("opencode/nemotron-3-ultra-free", "5bao")
        assert ok is False

    def test_validate_disabled(self, populated_pool):
        populated_pool.models["opencode/mimo-v2.5-free"]["enabled"] = False
        ok, msg = populated_pool.validate_model("opencode/mimo-v2.5-free", "21bao")
        assert ok is False
        assert "disabled" in msg


# --- ModelPool recommend tests ---

class TestModelPoolRecommend:
    def test_recommend_smoke(self, populated_pool):
        rec = populated_pool.recommend("first_live_smoke", "21bao")
        assert rec["recommended"] is not None
        assert rec["task_type"] == "first_live_smoke"

    def test_recommend_implementer(self, populated_pool):
        rec = populated_pool.recommend("implementer", "21bao")
        assert rec["recommended"] is not None

    def test_recommend_unknown_task(self, populated_pool):
        rec = populated_pool.recommend("nonexistent_task", "21bao")
        assert rec.get("error") is not None

    def test_recommend_no_models(self, tmp_pool):
        rec = tmp_pool.recommend("first_live_smoke", "empty-node")
        assert rec.get("error") is not None


# --- ModelPool fallback tests ---

class TestModelPoolFallback:
    def test_fallback_disabled_by_default(self):
        entry = new_model_entry("opencode/test")
        assert entry["fallback_allowed"] is False


# --- ModelPool sanitize tests ---

class TestModelPoolSanitize:
    def test_sanitize_no_secrets(self, populated_pool):
        sanitized = exported = populated_pool.export_sanitized()
        text = json.dumps(sanitized)
        for kw in ["TOKEN", "SECRET", "KEY", "PASSWORD", "PRIVATE"]:
            assert kw not in text.upper()

    def test_sanitize_has_model_fields(self, populated_pool):
        sanitized = populated_pool.export_sanitized()
        assert "models" in sanitized
        for mid, entry in sanitized["models"].items():
            assert "exact_model_id" in entry
            assert "cost_tag" in entry
            assert "node_availability" in entry


# --- ModelPool snapshot for approval tests ---

class TestModelPoolSnapshotApproval:
    def test_snapshot_has_sha(self, populated_pool):
        snap = populated_pool.export_snapshot_for_approval()
        assert len(snap["snapshot_sha256"]) == 64
        assert snap["model_count"] > 0


# --- ModelPool list tests ---

class TestModelPoolList:
    def test_list_all(self, populated_pool):
        models = populated_pool.list_models()
        assert len(models) >= 3

    def test_list_by_node(self, populated_pool):
        models = populated_pool.list_models(node_id="5bao")
        assert all(
            m["node_availability"].get("5bao", {}).get("available", False)
            for m in models
        )

    def test_list_by_tag(self, populated_pool):
        models = populated_pool.list_models(tag="free")
        assert all(m["cost_tag"] == "free" for m in models)


# --- Operator Model Approval Gate tests ---

class TestOperatorModelApprovalGate:
    def test_valid_approval(self, valid_approval):
        ok, errs = validate_approval(valid_approval)
        assert ok is True

    def test_missing_field(self, valid_approval):
        del valid_approval["job_id"]
        ok, _ = validate_approval(valid_approval)
        assert ok is False

    def test_not_approved(self, valid_approval):
        valid_approval["approval_status"] = "PENDING"
        ok, _ = validate_approval(valid_approval)
        assert ok is False

    def test_invalid_sha(self, valid_approval):
        valid_approval["prompt_sha256"] = "tooshort"
        ok, _ = validate_approval(valid_approval)
        assert ok is False

    def test_max_calls_zero(self, valid_approval):
        valid_approval["max_calls"] = 0
        ok, _ = validate_approval(valid_approval)
        assert ok is False

    def test_fallback_enabled_no_model(self, valid_approval):
        valid_approval["fallback_policy"] = "enabled"
        valid_approval["fallback_model_id"] = None
        valid_approval["fallback_approved"] = True
        ok, _ = validate_approval(valid_approval)
        assert ok is False

    def test_fallback_enabled_no_approval(self, valid_approval):
        valid_approval["fallback_policy"] = "enabled"
        valid_approval["fallback_model_id"] = "opencode/backup"
        valid_approval["fallback_approved"] = False
        ok, _ = validate_approval(valid_approval)
        assert ok is False

    def test_model_id_format(self, valid_approval):
        valid_approval["exact_model_id"] = "no-slash"
        ok, _ = validate_approval(valid_approval)
        assert ok is False

    def test_binding_mismatch(self, valid_approval):
        ok, _ = validate_approval(valid_approval, expected_job_id="wrong")
        assert ok is False

    def test_binding_match(self, valid_approval):
        ok, _ = validate_approval(
            valid_approval,
            expected_job_id="test-001",
            expected_node="21bao",
            expected_model_id="opencode/mimo-v2.5-free",
            expected_prompt_sha="b" * 64,
            expected_snapshot_sha="a" * 64,
        )
        assert ok is True

    def test_template_default_fallback_disabled(self):
        tmpl = generate_approval_template(
            "j-001", "21bao", "opencode/mimo-v2.5-free",
            "mimo-free", "c" * 64, "d" * 64,
        )
        assert tmpl["fallback_policy"] == "disabled"
        assert tmpl["approval_status"] == "NOT_APPROVED"



class TestRecommendationGateNative(unittest.TestCase):
    """Test native recommendation for implementer-small and smoke (V1.20.29J).

    Uses a temporary fixture pool to avoid dependency on live discover state.
    """

    FIXTURE_MODELS = {
        "opencode/deepseek-v4-flash-free": {
            "model_id": "opencode/deepseek-v4-flash-free",
            "alias": "deepseek-v4-flash-free",
            "provider": "opencode",
            "exact_model_id": "opencode/deepseek-v4-flash-free",
            "cost_tag": "free",
            "capability_tags": ["code", "free", "fast"],
            "roles": ["implementer"],
            "priority": 1,
            "enabled": True,
            "health_status": "healthy",
            "last_seen": "2026-06-21T00:00:00Z",
            "fallback_allowed": False,
            "cooldown_state": {"active": False, "until": None},
            "rate_limit_events": [],
            "node_availability": {"21bao": {"available": True, "last_seen": "2026-06-21T00:00:00Z"}},
        },
        "opencode/nemotron-3-ultra-free": {
            "model_id": "opencode/nemotron-3-ultra-free",
            "alias": "nemotron-3-ultra-free",
            "provider": "opencode",
            "exact_model_id": "opencode/nemotron-3-ultra-free",
            "cost_tag": "free",
            "capability_tags": ["code", "free", "strong"],
            "roles": ["implementer"],
            "priority": 2,
            "enabled": True,
            "health_status": "healthy",
            "last_seen": "2026-06-21T00:00:00Z",
            "fallback_allowed": False,
            "cooldown_state": {"active": False, "until": None},
            "rate_limit_events": [],
            "node_availability": {"21bao": {"available": True, "last_seen": "2026-06-21T00:00:00Z"}},
        },
        "opencode/mimo-v2.5-free": {
            "model_id": "opencode/mimo-v2.5-free",
            "alias": "mimo-v2.5-free",
            "provider": "opencode",
            "exact_model_id": "opencode/mimo-v2.5-free",
            "cost_tag": "free",
            "capability_tags": ["code", "free"],
            "roles": ["implementer"],
            "priority": 3,
            "enabled": True,
            "health_status": "healthy",
            "last_seen": "2026-06-21T00:00:00Z",
            "fallback_allowed": False,
            "cooldown_state": {"active": False, "until": None},
            "rate_limit_events": [],
            "node_availability": {"21bao": {"available": True, "last_seen": "2026-06-21T00:00:00Z"}},
        },
    }

    def setUp(self):
        """Ensure a minimal fixture pool exists for 21bao recommendation tests."""
        import tempfile, os
        from opencode_model_pool import ModelPool
        # Check if real pool already has 21bao models
        pool = ModelPool()
        has_21bao = any(
            "21bao" in m.get("node_availability", {})
            for m in pool.models.values()
        )
        if not has_21bao:
            # Create temporary fixture pool
            self._fixture_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "scripts", ".opencode_model_pool.json"
            )
            self._had_fixture = os.path.exists(self._fixture_path)
            fixture_data = {
                "models": dict(self.FIXTURE_MODELS),
                "snapshot_timestamp": "2026-06-21T00:00:00Z",
                "version": "test-fixture",
            }
            import json
            with open(self._fixture_path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(fixture_data, f, indent=2)
            # Re-compute snapshot SHA
            pool2 = ModelPool()
            pool2.save()
            self._created_fixture = True
        else:
            self._created_fixture = False

    def tearDown(self):
        """Remove fixture if we created it."""
        if getattr(self, "_created_fixture", False) and not getattr(self, "_had_fixture", True):
            import os
            if os.path.exists(self._fixture_path):
                os.remove(self._fixture_path)

    def test_recommend_implementer_small_native(self):
        from opencode_model_pool import ModelPool
        pool = ModelPool()
        rec = pool.recommend("implementer-small", "21bao")
        assert rec.get("error") is None, f"implementer-small should be supported: {rec}"
        assert rec.get("task_type") == "implementer-small"
        assert rec.get("recommended") is not None
        assert rec.get("node") == "21bao"

    def test_recommend_implementer_small_not_implementer_fallback(self):
        from opencode_model_pool import ModelPool
        pool = ModelPool()
        rec = pool.recommend("implementer-small", "21bao")
        assert rec.get("task_type") == "implementer-small"
        assert rec.get("task_type") != "implementer"

    def test_recommend_smoke_native(self):
        from opencode_model_pool import ModelPool
        pool = ModelPool()
        rec = pool.recommend("smoke", "21bao")
        assert rec.get("error") is None, f"smoke should be supported: {rec}"
        assert rec.get("task_type") == "smoke"
        assert rec.get("recommended") is not None

    def test_recommend_implementer_small_has_snapshot_sha(self):
        from opencode_model_pool import ModelPool
        pool = ModelPool()
        rec = pool.recommend("implementer-small", "21bao")
        assert rec.get("model_pool_snapshot_sha256") is not None

    def test_recommend_smoke_has_alternatives(self):
        from opencode_model_pool import ModelPool
        pool = ModelPool()
        rec = pool.recommend("smoke", "21bao")
        assert rec.get("alternatives") is not None

    def test_21bao_canary_admission_now_allows_implementer(self):
        from vibe_worker_registry import WorkerRegistry, NodeStatus
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        selected = reg.select_worker("implementer")
        assert selected is not None, "21bao normal should allow implementer"
        assert selected.worker_id == "21bao"

    def test_21bao_canary_admission_now_allows_reviewer(self):
        from vibe_worker_registry import WorkerRegistry, NodeStatus
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        selected = reg.select_worker("reviewer")
        assert selected is not None
        assert selected.worker_id == "21bao"

    def test_21bao_canary_admission_still_rejects_merge(self):
        from vibe_worker_registry import WorkerRegistry, NodeStatus
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        selected = reg.select_worker("merge")
        assert selected is None

    def test_21bao_canary_admission_still_rejects_windows_worker(self):
        from vibe_worker_registry import WorkerRegistry, NodeStatus
        reg = WorkerRegistry()
        reg.set_health("5bao", NodeStatus.OFFLINE)
        reg.set_health("9bao", NodeStatus.OFFLINE)
        reg.set_health("21bao", NodeStatus.ONLINE)
        selected = reg.select_worker("windows-worker")
        assert selected is None
