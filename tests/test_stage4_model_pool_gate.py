"""
Baseline02 Stage 4 — Model Pool & Node-Model Matrix Declaration Gate Tests.

Scope: declared-layer only (provider_namespace, alias uniqueness, smoke_required,
       temporary_unavailable, matrix node coverage, seven-state schema).
Does NOT test runtime states — those are Stage 5 scope.
"""

import hashlib
import json
import os
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_POOL_PATH = _REPO_ROOT / "scripts" / "model_pool.yaml"
_NMC_PATH = _REPO_ROOT / "scripts" / "node_model_capability.yaml"
_MANIFEST_PATH = _REPO_ROOT / "scripts" / "model_pool_manifest.json"


@pytest.fixture(scope="module")
def pool():
    with open(_POOL_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def nmc():
    with open(_NMC_PATH) as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def manifest():
    with open(_MANIFEST_PATH) as f:
        return json.load(f)


def _enabled_models(pool):
    return [m for m in pool["models"] if m.get("enabled") is True]


def _disabled_models(pool):
    return [m for m in pool["models"] if m.get("enabled") is False]


class TestProviderNamespace:
    """provider_namespace must be non-'unknown' and match canonical_provider."""

    def test_all_enabled_have_provider_namespace(self, pool):
        for m in _enabled_models(pool):
            ns = m.get("provider_namespace")
            assert ns is not None, f"{m['id']}: provider_namespace is None"
            assert isinstance(ns, str), f"{m['id']}: provider_namespace not a string"

    def test_no_unknown_provider_namespace(self, pool):
        unknowns = [m["id"] for m in _enabled_models(pool)
                    if m.get("provider_namespace") == "unknown"]
        assert unknowns == [], f"Enabled models with provider_namespace=unknown: {unknowns}"

    def test_provider_namespace_matches_canonical(self, pool):
        mapping = {
            "anthropic": "anthropic", "dashscope": "dashscope",
            "deepseek": "deepseek", "deepseek-plan": "deepseek-plan",
            "google": "google", "minimax": "minimax",
            "minimax-plan": "minimax-plan", "moonshot": "moonshot",
            "openai": "openai", "opencode": "opencode",
            "opencode-go": "opencode-go", "volcengine": "volcengine",
            "xai": "xai", "xiaomi": "xiaomi",
        }
        mismatches = []
        for m in _enabled_models(pool):
            cp = m.get("canonical_provider", "")
            expected = mapping.get(cp)
            if expected is None:
                mismatches.append(f"{m['id']}: canonical_provider={cp!r} not mapped")
                continue
            ns = m.get("provider_namespace")
            if ns != expected:
                mismatches.append(f"{m['id']}: ns={ns!r} != expected={expected!r}")
        assert mismatches == [], "\n".join(mismatches)

    def test_disabled_models_also_have_provider_namespace(self, pool):
        unknowns = [m["id"] for m in _disabled_models(pool)
                    if m.get("provider_namespace") == "unknown"]
        assert unknowns == [], f"Disabled with provider_namespace=unknown: {unknowns}"


class TestAliasUniqueness:
    """No duplicate aliases, globally or within a single model."""

    def test_no_intra_model_duplicate_aliases(self, pool):
        offenders = []
        for m in pool["models"]:
            aliases = m.get("alias", [])
            if len(aliases) != len(set(aliases)):
                seen = set()
                dups = [a for a in aliases if a in seen or seen.add(a)]
                offenders.append(f"{m['id']}: dups: {dups}")
        assert offenders == [], "\n".join(offenders)

    def test_no_global_alias_duplicates(self, pool):
        alias_to_models = {}
        for m in pool["models"]:
            for a in m.get("alias", []):
                alias_to_models.setdefault(a, set()).add(m["id"])
        dups = {a: mids for a, mids in alias_to_models.items() if len(mids) > 1}
        assert dups == {}, f"Duplicates across models: {dups}"


class TestEnabledDisabled:
    """Disabled/temporary_unavailable/smoke_required-unverified models."""

    def test_smoke_required_unverified_are_disabled(self, pool):
        bad = []
        for m in pool["models"]:
            if m.get("smoke_required") is not True:
                continue
            sr = m.get("smoke_results", {})
            if not sr:
                if m.get("enabled") is not False:
                    bad.append(f"{m['id']}: smoke=true, empty results, enabled={m['enabled']}")
            else:
                all_unv = all(d.get("status") != "confirmed" for d in sr.values())
                if all_unv and m.get("enabled") is not False:
                    bad.append(f"{m['id']}: smoke=true, all unverified, enabled={m['enabled']}")
        assert bad == [], "\n".join(bad)

    def test_temporary_unavailable_are_disabled(self, pool):
        bad = [m["id"] for m in pool["models"]
               if m.get("status") == "temporary_unavailable"
               and m.get("enabled") is not False]
        assert bad == [], f"temporary_unavailable but enabled: {bad}"

    def test_disabled_models_keep_pool_entry(self, pool):
        assert len(_disabled_models(pool)) >= 5


class TestMatrixNodeCoverage:
    """Matrix entries must match pool declared layer."""

    def test_21bao_only_contains_appropriate_models(self, pool, nmc):
        mids = {e["model_id"] for e in nmc["nodes"]["21bao"]["matrix"]}
        bad = []
        for mid in mids:
            m = next((x for x in pool["models"] if x["id"] == mid), None)
            if m is None:
                bad.append(f"{mid}: not in pool")
            elif m.get("enabled") is False:
                bad.append(f"{mid}: disabled but in 21bao")
            else:
                ans = m.get("allowed_nodes", [])
                if ans and "win" not in ans and "21bao" not in ans:
                    bad.append(f"{mid}: allowed={ans} but in 21bao")
        assert bad == [], "\n".join(bad)

    def test_remote_only_not_in_21bao(self, pool, nmc):
        mids = {e["model_id"] for e in nmc["nodes"]["21bao"]["matrix"]}
        bad = []
        for mid in mids:
            m = next((x for x in pool["models"] if x["id"] == mid), None)
            if m is None:
                continue
            ans = m.get("allowed_nodes", [])
            if ans and "5bao" in ans and "9bao" in ans and "win" not in ans and "21bao" not in ans:
                bad.append(f"{mid}: remote-only in 21bao")
        assert bad == [], "\n".join(bad)

    def test_enabled_models_in_at_least_one_matrix(self, pool, nmc):
        all_mids = set()
        for nd in nmc["nodes"].values():
            all_mids.update(e["model_id"] for e in nd["matrix"])
        missing = {m["id"] for m in pool["models"] if m.get("enabled") is True} - all_mids
        assert missing == set(), f"Enabled models missing from all matrices: {missing}"

    def test_5bao_9bao_matrix_includes_enabled(self, pool, nmc):
        for nn in ["5bao", "9bao"]:
            mids = {e["model_id"] for e in nmc["nodes"][nn]["matrix"]}
            bad = []
            for m in pool["models"]:
                if m.get("enabled") is not True:
                    if m["id"] in mids:
                        bad.append(f"{m['id']}: disabled but in {nn}")
                    continue
                ans = m.get("allowed_nodes", [])
                if not ans or nn in ans or "9bao" in ans:
                    if m["id"] not in mids:
                        bad.append(f"{m['id']}: enabled but missing from {nn}")
            assert bad == [], "\n".join(bad)

    def test_no_disabled_in_any_matrix(self, pool, nmc):
        disabled = {m["id"] for m in pool["models"] if m.get("enabled") is False}
        for nn in ["21bao", "5bao", "9bao"]:
            found = {e["model_id"] for e in nmc["nodes"][nn]["matrix"]} & disabled
            assert found == set(), f"Disabled in {nn}: {found}"

    def test_matrix_counts_consistent(self, nmc):
        n = nmc["nodes"]
        assert n["5bao"]["total_entries"] == n["9bao"]["total_entries"]
        assert n["21bao"]["total_entries"] >= 20
        assert n["5bao"]["total_entries"] >= 20


class TestSevenStateSchema:
    """Matrix entries: 7 fields present; 6 runtime states = 'unknown'."""

    SF = ["declared", "synced", "runtime_visible", "env_loaded",
          "wrapper_valid", "model_call_verified", "operator_approved"]
    RS = ["synced", "runtime_visible", "env_loaded",
          "wrapper_valid", "model_call_verified", "operator_approved"]

    def test_all_entries_have_seven_state_fields(self, nmc):
        for nn, nd in nmc["nodes"].items():
            for i, e in enumerate(nd["matrix"]):
                for sf in self.SF:
                    assert sf in e, f"{nn}[{i}]({e.get('model_id','?')}): missing {sf}"

    def test_runtime_states_are_unknown(self, nmc):
        bad = []
        # States that are EXPECTED to have been promoted on 21bao
        # (Stage 5 Batch A evidence: synced=HIGH confidence, wrapper_valid=HIGH confidence)
        PROMOTED_ON_21BAO = {"synced", "wrapper_valid"}
        # States promoted on 5bao
        # (Stage 5 Batch B + B2 evidence: model_pool synced, wrapper/runner verified)
        PROMOTED_ON_5BAO = {"synced", "wrapper_valid"}
        # States promoted on 9bao
        # (Stage 5 Batch C + C4 evidence: model_pool synced, runner PATH fix, node/npm/opencode-go verified)
        PROMOTED_ON_9BAO = {"synced", "wrapper_valid"}
        # Per-entry model_call_verified promotions (Batch D-R2 evidence:
        # HTTP 200, content='ok', attribution=mimo-v2.5, fallback=0, retry=0, duration<30s)
        MODEL_CALL_VERIFIED_ENTRIES = {
            "21bao": {"opencode-go-mimo-v2-5"},
            "5bao": {"opencode-go-mimo-v2-5"},
            "9bao": {"opencode-go-mimo-v2-5"},
        }
        # Per-entry runtime_visible promotions (S7-1 inventory evidence:
        # model_id listed in opencode.jsonc opencode-go provider on all 3 nodes)
        RUNTIME_VISIBLE_ENTRIES = {
            "21bao": {
                "opencode-go-deepseek-v4-flash", "opencode-go-glm-5-1",
                "opencode-go-glm-5-2", "opencode-go-kimi-k2-6",
                "opencode-go-mimo-v2-5", "opencode-go-mimo-v2-5-pro",
                "opencode-go-qwen3-7-max", "opencode-go-qwen3-7-plus",
            },
            "5bao": {
                "opencode-go-deepseek-v4-flash", "opencode-go-glm-5-1",
                "opencode-go-glm-5-2", "opencode-go-kimi-k2-6",
                "opencode-go-mimo-v2-5", "opencode-go-mimo-v2-5-pro",
                "opencode-go-qwen3-7-max", "opencode-go-qwen3-7-plus",
            },
            "9bao": {
                "opencode-go-deepseek-v4-flash", "opencode-go-glm-5-1",
                "opencode-go-glm-5-2", "opencode-go-kimi-k2-6",
                "opencode-go-mimo-v2-5", "opencode-go-mimo-v2-5-pro",
                "opencode-go-qwen3-7-max", "opencode-go-qwen3-7-plus",
            },
        }
        # Per-entry env_loaded promotions (S7-2 inventory evidence:
        # OPENCODE_GO_API_KEY + OPENCODE_DEEPSEEK_API_KEY populated on all 3 nodes)
        ENV_LOADED_ENTRIES = {
            "21bao": {
                "opencode-go-deepseek-v4-flash", "opencode-go-deepseek-v4-pro",
                "opencode-go-glm-5-1", "opencode-go-glm-5-2",
                "opencode-go-kimi-k2-6", "opencode-go-mimo-v2-5",
                "opencode-go-mimo-v2-5-pro", "opencode-go-qwen3-7-max",
                "opencode-go-qwen3-7-plus",
                "deepseek-deepseek-coder", "deepseek-deepseek-reasoner",
            },
            "5bao": {
                "opencode-go-deepseek-v4-flash", "opencode-go-deepseek-v4-pro",
                "opencode-go-glm-5-1", "opencode-go-glm-5-2",
                "opencode-go-kimi-k2-6", "opencode-go-mimo-v2-5",
                "opencode-go-mimo-v2-5-pro", "opencode-go-qwen3-7-max",
                "opencode-go-qwen3-7-plus",
                "deepseek-deepseek-coder", "deepseek-deepseek-reasoner",
            },
            "9bao": {
                "opencode-go-deepseek-v4-flash", "opencode-go-deepseek-v4-pro",
                "opencode-go-glm-5-1", "opencode-go-glm-5-2",
                "opencode-go-kimi-k2-6", "opencode-go-mimo-v2-5",
                "opencode-go-mimo-v2-5-pro", "opencode-go-qwen3-7-max",
                "opencode-go-qwen3-7-plus",
                "deepseek-deepseek-coder", "deepseek-deepseek-reasoner",
            },
        }
        for nn, nd in nmc["nodes"].items():
            for i, e in enumerate(nd["matrix"]):
                mid = e.get("model_id", "")
                for sf in self.RS:
                    val = e.get(sf)
                    promoted = set()
                    if nn == "21bao":
                        promoted = PROMOTED_ON_21BAO
                    elif nn == "5bao":
                        promoted = PROMOTED_ON_5BAO
                    elif nn == "9bao":
                        promoted = PROMOTED_ON_9BAO
                    # Per-entry override: model_call_verified (Batch D-R2)
                    if sf == "model_call_verified" and mid in MODEL_CALL_VERIFIED_ENTRIES.get(nn, set()):
                        if val is not True:
                            bad.append(f"{nn}[{i}]({mid}): model_call_verified={val!r} (expected True, Batch D-R2)")
                        continue
                    # Per-entry override: runtime_visible (S7-1 inventory evidence)
                    if sf == "runtime_visible" and mid in RUNTIME_VISIBLE_ENTRIES.get(nn, set()):
                        if val is not True:
                            bad.append(f"{nn}[{i}]({mid}): runtime_visible={val!r} (expected True, S7-1)")
                        continue
                    # Per-entry override: env_loaded (S7-2 inventory evidence)
                    if sf == "env_loaded" and mid in ENV_LOADED_ENTRIES.get(nn, set()):
                        if val is not True:
                            bad.append(f"{nn}[{i}]({mid}): env_loaded={val!r} (expected True, S7-2)")
                        continue
                    if promoted and sf in promoted:
                        # Promoted states must be True, not 'unknown'
                        if val is not True:
                            bad.append(f"{nn}[{i}]({e.get('model_id','?')}): {sf}={val!r} (expected True)")
                    else:
                        # All other nodes/states must remain 'unknown'
                        if val != "unknown":
                            bad.append(f"{nn}[{i}]({e.get('model_id','?')}): {sf}={val!r} (expected 'unknown')")
        assert bad == [], "\n".join(bad)

    def test_declared_is_true(self, nmc):
        bad = []
        for nn, nd in nmc["nodes"].items():
            for i, e in enumerate(nd["matrix"]):
                if e.get("declared") is not True:
                    bad.append(f"{nn}[{i}]({e.get('model_id','?')}): declared={e.get('declared')!r}")
        assert bad == [], "\n".join(bad)

    def test_provider_namespace_in_matrix_matches_pool(self, pool, nmc):
        pool_ns = {m["id"]: m.get("provider_namespace") for m in pool["models"]}
        bad = []
        for nn, nd in nmc["nodes"].items():
            for e in nd["matrix"]:
                mid = e.get("model_id", "")
                if e.get("provider_namespace") != pool_ns.get(mid):
                    bad.append(f"{nn}({mid}): {e.get('provider_namespace')!r} != pool {pool_ns.get(mid)!r}")
        assert bad == [], "\n".join(bad)


class TestManifest:
    """model_pool_manifest.json SHA256 must match model_pool.yaml."""

    def test_manifest_sha256_matches(self, pool, manifest):
        declared = manifest["files"]["model_pool.yaml"]["sha256"]
        actual = hashlib.sha256(open(_POOL_PATH, "rb").read()).hexdigest()
        assert declared == actual, f"SHA mismatch: declared={declared} != actual={actual}"

    def test_manifest_size_matches(self, pool, manifest):
        declared = manifest["files"]["model_pool.yaml"]["size"]
        actual = os.path.getsize(_POOL_PATH)
        assert declared == actual, f"Size mismatch: declared={declared} != actual={actual}"
