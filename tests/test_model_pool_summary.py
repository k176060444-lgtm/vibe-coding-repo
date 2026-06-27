"""Tests for scripts/model_pool_summary.py (I11)."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure scripts/ is importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from model_pool_summary import summarize_model, summarize_opencode_models  # noqa: E402


class TestSummarizeModel:
    """Unit tests for the pure summarize_model function."""

    def test_enabled_opencode_canary(self):
        entry = {
            "id": "opencode-go-deepseek-v4-flash",
            "provider": "opencode-go",
            "model": "deepseek-v4-flash",
            "cost": "free",
            "enabled": True,
            "priority": 25,
            "fallback_policy": "none",
        }
        s = summarize_model(entry)
        assert "opencode-go-deepseek-v4-flash" in s
        assert "provider=opencode-go" in s
        assert "model=deepseek-v4-flash" in s
        assert "cost=free" in s
        assert "enabled" in s
        assert "priority=25" in s
        assert "fallback=none" in s

    def test_disabled_opencode_model(self):
        entry = {
            "id": "opencode-go-glm-5-2",
            "provider": "opencode-go",
            "model": "glm-5.2",
            "cost": "free",
            "enabled": False,
            "priority": 23,
            "fallback_policy": "none",
        }
        s = summarize_model(entry)
        assert "opencode-go-glm-5-2" in s
        assert "disabled" in s
        assert "fallback=none" in s

    def test_traditional_provider_model(self):
        entry = {
            "id": "deepseek-deepseek-chat",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "cost": "paid",
            "enabled": True,
            "priority": 5,
            "fallback_policy": "none",
        }
        s = summarize_model(entry)
        assert "deepseek-deepseek-chat" in s
        assert "provider=deepseek" in s
        assert "cost=paid" in s
        assert "enabled" in s

    def test_missing_fields_uses_defaults(self):
        s = summarize_model({})
        assert "unknown" in s
        assert "disabled" in s  # default enabled=False
        assert "fallback=none" in s  # default

    def test_pure_function_no_side_effects(self):
        entry = {"id": "x", "provider": "y", "enabled": True}
        s1 = summarize_model(entry)
        s2 = summarize_model(entry)
        assert s1 == s2  # deterministic
        assert entry == {"id": "x", "provider": "y", "enabled": True}  # not mutated


class TestSummarizeOpencodeModels:
    """Integration test: reads actual model_pool.yaml from repo."""

    def test_returns_8_opencode_go_models(self):
        yaml_path = _REPO_ROOT / "scripts" / "model_pool.yaml"
        summaries = summarize_opencode_models(yaml_path)
        assert len(summaries) == 8
        # All should mention provider=opencode-go
        for s in summaries:
            assert "provider=opencode-go" in s

    def test_canary_is_enabled(self):
        yaml_path = _REPO_ROOT / "scripts" / "model_pool.yaml"
        summaries = summarize_opencode_models(yaml_path)
        canary_lines = [s for s in summaries if "opencode-go-deepseek-v4-flash" in s]
        assert len(canary_lines) == 1
        assert "enabled" in canary_lines[0]
        assert "fallback=none" in canary_lines[0]

    def test_seven_disabled_models(self):
        yaml_path = _REPO_ROOT / "scripts" / "model_pool.yaml"
        summaries = summarize_opencode_models(yaml_path)
        disabled = [s for s in summaries if "disabled" in s]
        assert len(disabled) == 7

    def test_missing_file_returns_empty(self, tmp_path):
        summaries = summarize_opencode_models(tmp_path / "nonexistent.yaml")
        assert summaries == []
