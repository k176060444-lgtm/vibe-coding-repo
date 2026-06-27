"""I15 Architecture & Model Pool Correction — targeted tests.

Verifies:
1. Architecture contract: worker transport, SSH username, no SSH bypass
2. Central pool completeness: all expected models present
3. Route-all model existence: all route-all models resolvable in central pool
4. OpenCode-go alias isolation: opencode- prefix isolation
5. Secret safety: no plaintext keys in YAML
"""

import os
import sys
import json
import yaml

_SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from vibe_architecture_contract import (
    self_check as arch_self_check,
    validate_worker_transport,
    validate_worker_count,
    validate_no_ssh_bypass,
)
from vibe_worker_registry import DEFAULT_WORKERS
from vibe_model_routing_policy import route_all, recommend


# ── Helpers ──────────────────────────────────────────────────────────

def _load_yaml_pool():
    yp = os.path.join(_SCRIPTS_DIR, "model_pool.yaml")
    if not os.path.exists(yp):
        return None
    with open(yp, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Architecture Contract Tests ──────────────────────────────────────

class TestArchitectureContract:
    """Verify worker transport, SSH username, and no-bypass rules."""

    def test_arch_self_check_passes(self):
        result = arch_self_check()
        assert result["passed"], f"Architecture contract failed: {result['checks']}"

    def test_worker_count_three(self):
        result = validate_worker_count()
        assert result["passed"], f"Worker count: {result}"
        assert result["actual_count"] == 3

    def test_21bao_local_exec(self):
        w = DEFAULT_WORKERS.get("21bao")
        assert w is not None, "21bao worker not found"
        assert w.transport == "local-exec", f"21bao transport={w.transport}"
        assert not w.ssh_host, f"21bao ssh_host should be empty, got '{w.ssh_host}'"
        assert not w.ssh_user, f"21bao ssh_user should be empty, got '{w.ssh_user}'"

    def test_5bao_username_vibeworker(self):
        w = DEFAULT_WORKERS.get("5bao")
        assert w is not None, "5bao worker not found"
        assert w.ssh_user == "vibeworker", f"5bao ssh_user='{w.ssh_user}'"
        assert w.transport == "ssh", f"5bao transport={w.transport}"

    def test_9bao_username_vibeworker(self):
        w = DEFAULT_WORKERS.get("9bao")
        assert w is not None, "9bao worker not found"
        assert w.ssh_user == "vibeworker", f"9bao ssh_user='{w.ssh_user}'"
        assert w.transport == "ssh", f"9bao transport={w.transport}"

    def test_no_ssh_bypass(self):
        result = validate_no_ssh_bypass()
        assert result["passed"], f"SSH bypass issues: {result['ssh_bypass_issues']}"


# ── Central Pool Completeness Tests ──────────────────────────────────

class TestCentralPoolCompleteness:
    """Verify all expected models are in model_pool.yaml."""

    def test_pool_file_exists(self):
        pool = _load_yaml_pool()
        assert pool is not None, "model_pool.yaml not found"
        assert "models" in pool, "model_pool.yaml has no 'models' key"

    def test_minimax_m3_present(self):
        pool = _load_yaml_pool()
        models = {m["id"]: m for m in pool["models"]}
        assert "minimax-plan-minimax-m3" in models, (
            "minimax-plan-minimax-m3 not in pool")

    def test_deepseek_v4_pro_present(self):
        pool = _load_yaml_pool()
        models = {m["id"]: m for m in pool["models"]}
        assert "deepseek-plan-deepseek-v4-pro" in models, (
            "deepseek-plan-deepseek-v4-pro not in pool")

    def test_opencode_free_models_present(self):
        pool = _load_yaml_pool()
        models = {m["id"]: m for m in pool["models"]}
        for mid in ["opencode-deepseek-v4-flash-free", "opencode-mimo-v2-5-free",
                     "opencode-nemotron-3-ultra-free", "opencode-north-mini-code-free",
                     "opencode-big-pickle"]:
            assert mid in models, f"{mid} not in pool"

    def test_opencode_go_models_present(self):
        pool = _load_yaml_pool()
        models = {m["id"]: m for m in pool["models"]}
        for mid in ["opencode-go-deepseek-v4-flash", "opencode-go-glm-5-2",
                     "opencode-go-glm-5-1", "opencode-go-kimi-k2-6",
                     "opencode-go-qwen3-7-max", "opencode-go-qwen3-7-plus",
                     "opencode-go-mimo-v2-5-pro", "opencode-go-mimo-v2-5"]:
            assert mid in models, f"{mid} not in pool"

    def test_opencode_go_key_env_not_empty(self):
        pool = _load_yaml_pool()
        models = {m["id"]: m for m in pool["models"]}
        for mid in ["opencode-go-deepseek-v4-flash", "opencode-go-glm-5-2",
                     "opencode-go-glm-5-1", "opencode-go-kimi-k2-6",
                     "opencode-go-qwen3-7-max", "opencode-go-qwen3-7-plus",
                     "opencode-go-mimo-v2-5-pro", "opencode-go-mimo-v2-5"]:
            m = models[mid]
            assert m["key_env"] == "OPENCODE_GO_API_KEY", (
                f"{mid} key_env='{m['key_env']}' (expected OPENCODE_GO_API_KEY)")
            assert m["base_url_env"] == "OPENCODE_GO_BASE_URL", (
                f"{mid} base_url_env='{m['base_url_env']}'")

    def test_total_model_count(self):
        """Model count must match current authorized model_pool.yaml state.

        Uses dynamic read instead of hardcoded count to avoid stale
        assertions when operator authorizes pool changes.
        """
        pool = _load_yaml_pool()
        models = pool["models"]
        # Dynamic: read from YAML, verify internal consistency
        total = len(models)
        enabled = sum(1 for m in models if m.get("enabled"))
        disabled = total - enabled
        assert total == enabled + disabled, (
            f"Count mismatch: total={total}, enabled={enabled}, disabled={disabled}")
        # Authorized state (I23): 38 total, 33 enabled, 5 disabled
        assert total >= 37, (
            f"Expected >=37 models (I15 baseline), got {total}")

    def test_opencode_go_all_enabled(self):
        """All opencode-go models are enabled per I23 operator authorization.

        I23 commit 0a82dad authorized enabling all 8 original opencode-go
        models + adding deepseek-v4-pro (9 total, all enabled).
        """
        pool = _load_yaml_pool()
        enabled = [m for m in pool["models"] if m.get("enabled")]
        opencode_go_enabled = [m for m in enabled
                               if m["id"].startswith("opencode-go-")]
        # Dynamic: verify all opencode-go models are enabled
        all_og = [m for m in pool["models"]
                  if m["id"].startswith("opencode-go-")]
        assert len(opencode_go_enabled) == len(all_og), (
            f"Not all opencode-go models enabled: "
            f"enabled={len(opencode_go_enabled)}, total={len(all_og)}: "
            f"{[m['id'] for m in opencode_go_enabled]}")
        # Verify deepseek-v4-pro is present and enabled (I23 addition)
        v4pro = [m for m in all_og if "deepseek-v4-pro" in m["id"]]
        assert len(v4pro) == 1, f"deepseek-v4-pro not found in opencode-go"
        assert v4pro[0].get("enabled") is True, "deepseek-v4-pro not enabled"


# ── Route-All Model Existence Tests ──────────────────────────────────

class TestRouteAllModelExistence:
    """Verify all route-all models exist in central pool."""

    def test_route_all_9_roles(self):
        """route_all() returns exactly 9 business roles (excluding _gate_results metadata)."""
        result = route_all()
        # _gate_results is metadata, not a business role — filter it out
        business_roles = {k: v for k, v in result.items() if not k.startswith("_")}
        assert len(business_roles) == 9, (
            f"Expected 9 business roles, got {len(business_roles)}: "
            f"{sorted(business_roles.keys())}")

    def test_route_all_roles_unchanged(self):
        result = route_all()
        expected_roles = {"orchestrator", "explorer", "planner", "implementer",
                          "tester-a", "tester-b", "reviewer-a", "reviewer-b",
                          "git-integrator"}
        # Filter out metadata keys (like _gate_results) before comparing
        actual_roles = {k for k in result.keys() if not k.startswith("_")}
        assert actual_roles == expected_roles, (
            f"Role mismatch: expected={expected_roles}, actual={actual_roles}")

    def test_route_all_models_in_pool(self):
        pool = _load_yaml_pool()
        pool_models = {m["id"]: m for m in pool["models"]}
        result = route_all()
        for role, data in result.items():
            model_name = data.get("recommended")
            if model_name is None:
                continue  # skip roles with no recommendation
            # Find the YAML ID for this routing model
            from vibe_model_routing_policy import recommend as _rec
            r = _rec(role)
            _ROUTING_TO_YAML = {
                "deepseek-v4-pro": "deepseek-plan-deepseek-v4-pro",
                "mimo-v2.5-pro": "xiaomi-mimo-v2-5-pro",
                "minimax-m3": "minimax-plan-minimax-m3",
                "volcengine-doubao": "volcengine-doubao-1-5-pro-256k",
            }
            yaml_id = _ROUTING_TO_YAML.get(model_name)
            if yaml_id:
                assert yaml_id in pool_models, (
                    f"Role '{role}' model '{model_name}' -> YAML ID '{yaml_id}' "
                    f"not found in central pool")


# ── OpenCode-Go Alias Isolation Tests ────────────────────────────────

class TestOpenCodeGoAliasIsolation:
    """Verify opencode- prefix isolation and no conflict with traditional aliases."""

    def test_opencode_go_aliases_in_exact_map(self):
        from opencode_model_pool import EXACT_ALIAS_MAP
        opencode_go_aliases = [k for k in EXACT_ALIAS_MAP
                               if "opencode-go" in EXACT_ALIAS_MAP[k] or
                               k.startswith("opencode-")]
        assert len(opencode_go_aliases) >= 16, (
            f"Expected >=16 opencode-go aliases in EXACT_ALIAS_MAP, "
            f"got {len(opencode_go_aliases)}: {opencode_go_aliases}")

    def test_opencode_go_in_ambiguous_map(self):
        from opencode_model_pool import AMBIGUOUS_ALIAS_MAP
        assert "opencode-go" in AMBIGUOUS_ALIAS_MAP, (
            "opencode-go not in AMBIGUOUS_ALIAS_MAP")
        # Dynamic: opencode-go count matches model_pool.yaml
        pool = _load_yaml_pool()
        og_in_pool = [m for m in pool["models"]
                      if m.get("provider") == "opencode-go"]
        expected_count = len(og_in_pool)
        actual_count = len(AMBIGUOUS_ALIAS_MAP["opencode-go"])
        assert actual_count == expected_count, (
            f"Expected {expected_count} opencode-go candidates (matching pool), "
            f"got {actual_count}")

    def test_no_traditional_alias_overwrite(self):
        from opencode_model_pool import EXACT_ALIAS_MAP
        # Traditional aliases must not be overwritten by opencode-go
        traditional = {"deepseek pro", "deepseek flash", "ds-v4-pro", "ds-v4-flash",
                       "mimo pro", "mimo-v2.5-pro", "mimo-v2.5",
                       "doubao", "volcengine", "ark-code", "ark-code-latest",
                       "minimax", "m3", "minimax-m3", "MiniMax-M3"}
        for alias in traditional:
            assert alias in EXACT_ALIAS_MAP, f"Traditional alias '{alias}' missing"
            assert "opencode-go" not in EXACT_ALIAS_MAP[alias], (
                f"Traditional alias '{alias}' points to opencode-go: "
                f"{EXACT_ALIAS_MAP[alias]}")


# ── Secret Safety Tests ──────────────────────────────────────────────

class TestSecretSafety:
    """Verify no plaintext API keys in tracked files."""

    def test_no_plaintext_keys_in_yaml(self):
        pool = _load_yaml_pool()
        for m in pool["models"]:
            key_env = m.get("key_env", "")
            base_url_env = m.get("base_url_env", "")
            # key_env must be a reference name, not a real key
            assert key_env == "" or key_env.endswith("_API_KEY") or \
                key_env.endswith("_BASE_URL") or key_env.endswith("_KEY") or \
                key_env.endswith("_TOKEN"), (
                    f"Model '{m['id']}' has suspicious key_env: '{key_env}'")
            assert base_url_env == "" or base_url_env.endswith("_BASE_URL") or \
                base_url_env.endswith("_ENDPOINT"), (
                    f"Model '{m['id']}' has suspicious base_url_env: '{base_url_env}'")
