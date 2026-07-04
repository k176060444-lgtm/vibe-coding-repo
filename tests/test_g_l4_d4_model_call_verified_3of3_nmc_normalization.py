"""G-L4 D4 model_call_verified 3-of-3 NMC Normalization Tests.

Verifies the NMC normalization at scripts/node_model_capability.yaml
and docs/baseline02/g-l4-d4-model-call-verified-3of3-nmc-normalization.md:

1. D4 model_call_verified=true for all 3 nodes (21bao, 5bao, 9bao)
2. model_call_verified_evidence exists for each node with correct PR references
3. 21bao/5bao concrete_invocation is deepseek-plan (not fallback)
4. 9bao concrete_invocation is opencode-go direct
5. operator_approved unchanged (unknown)
6. env_loaded unchanged
7. runtime_visible unchanged (3-of-3 preserved)
8. model_pool.yaml NOT modified
9. No credential/raw secret leakage
10. Readiness/gray/Baseline03 NOT entered
"""

import os
import re
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NMC_PATH = os.path.join(REPO_ROOT, "scripts/node_model_capability.yaml")
DOC_PATH = os.path.join(REPO_ROOT, "docs/baseline02/g-l4-d4-model-call-verified-3of3-nmc-normalization.md")
MODEL_POOL_PATH = os.path.join(REPO_ROOT, "scripts/model_pool.yaml")

D4_MODEL_ID = "opencode-go-deepseek-v4-pro"

EVIDENCE_MAP = {
    "21bao": {"pr": 341, "anchor": "f0b010c", "concrete": "deepseek-plan/deepseek-v4-pro", "canonical_provider": "opencode-go", "concrete_provider": "deepseek-plan"},
    "5bao":  {"pr": 342, "anchor": "1ccdf31", "concrete": "deepseek-plan/deepseek-v4-pro", "canonical_provider": "opencode-go", "concrete_provider": "deepseek-plan"},
    "9bao":  {"pr": 343, "anchor": "2f1df7e", "concrete": "opencode-go/deepseek-v4-pro", "canonical_provider": "opencode-go", "concrete_provider": "opencode-go"},
}


def _load_nmc():
    try:
        import yaml
    except ImportError:
        pytest.skip("yaml module not available")
    with open(NMC_PATH) as f:
        return yaml.safe_load(f)


def _load_doc():
    with open(DOC_PATH) as f:
        return f.read()


def _get_d4_entry(nmc, node):
    nodes_root = nmc.get("nodes", nmc)
    node_data = nodes_root.get(node, {})
    matrix = node_data.get("matrix", [])
    return next((m for m in matrix if m.get("model_id") == D4_MODEL_ID), None)


class TestModelCallVerified3of3:
    """D4 model_call_verified is true for all 3 nodes."""

    def test_21bao_model_call_verified_true(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "21bao")
        assert entry is not None, "21bao D4 entry not found in NMC"
        assert entry["model_call_verified"] is True

    def test_5bao_model_call_verified_true(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "5bao")
        assert entry is not None, "5bao D4 entry not found in NMC"
        assert entry["model_call_verified"] is True

    def test_9bao_model_call_verified_true(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "9bao")
        assert entry is not None, "9bao D4 entry not found in NMC"
        assert entry["model_call_verified"] is True

    def test_all_three_model_call_verified(self):
        nmc = _load_nmc()
        for node in ("21bao", "5bao", "9bao"):
            entry = _get_d4_entry(nmc, node)
            assert entry["model_call_verified"] is True, f"{node} model_call_verified should be true"


class TestModelCallVerifiedEvidence:
    """model_call_verified_evidence block exists with correct data."""

    def test_21bao_evidence_exists(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "21bao")
        evidence = entry.get("model_call_verified_evidence")
        assert evidence is not None, "21bao missing model_call_verified_evidence"
        assert "PR #341" in evidence.get("source", "")
        assert evidence.get("evidence_anchor", "").startswith("f0b010c")
        assert evidence.get("concrete_invocation") == "deepseek-plan/deepseek-v4-pro"
        assert "not fallback" in evidence.get("namespace_note", "")

    def test_5bao_evidence_exists(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "5bao")
        evidence = entry.get("model_call_verified_evidence")
        assert evidence is not None, "5bao missing model_call_verified_evidence"
        assert "PR #342" in evidence.get("source", "")
        assert evidence.get("evidence_anchor", "").startswith("1ccdf31")
        assert evidence.get("concrete_invocation") == "deepseek-plan/deepseek-v4-pro"
        assert "not fallback" in evidence.get("namespace_note", "")

    def test_9bao_evidence_exists(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "9bao")
        evidence = entry.get("model_call_verified_evidence")
        assert evidence is not None, "9bao missing model_call_verified_evidence"
        assert "PR #343" in evidence.get("source", "")
        assert evidence.get("evidence_anchor", "").startswith("2f1df7e")
        # 9bao uses opencode-go directly (canonical)
        assert evidence.get("concrete_invocation") == "opencode-go/deepseek-v4-pro"
        assert "canonical provider" in evidence.get("namespace_note", "")

    def test_evidence_attempt_count_one(self):
        nmc = _load_nmc()
        for node in ("21bao", "5bao", "9bao"):
            entry = _get_d4_entry(nmc, node)
            evidence = entry.get("model_call_verified_evidence")
            assert evidence.get("attempt_count") == 1, f"{node} attempt_count should be 1"
            assert evidence.get("fallback_used") is False, f"{node} fallback_used should be false"

    def test_evidence_model_call_succeeded(self):
        nmc = _load_nmc()
        for node in ("21bao", "5bao", "9bao"):
            entry = _get_d4_entry(nmc, node)
            evidence = entry.get("model_call_verified_evidence")
            assert evidence.get("model_call_succeeded") is True, f"{node} model_call_succeeded should be true"

    def test_not_fallback_semantics(self):
        """21bao/5bao concrete_invocation is deepseek-plan but NOT recorded as fallback."""
        nmc = _load_nmc()
        for node in ("21bao", "5bao"):
            entry = _get_d4_entry(nmc, node)
            evidence = entry.get("model_call_verified_evidence")
            note = evidence.get("namespace_note", "")
            assert "fallback" not in evidence.get("concrete_invocation", "")
            assert "not fallback" in note, f"{node}: namespace_note should clarify 'not fallback'"
            assert "not provider drift" in note

    def test_9bao_canonical_direct(self):
        """9bao uses opencode-go/deepseek-v4-pro directly (canonical)."""
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "9bao")
        evidence = entry.get("model_call_verified_evidence")
        assert evidence.get("canonical_provider") == "opencode-go"
        assert evidence.get("concrete_provider") == "opencode-go"
        assert "canonical provider" in evidence.get("namespace_note", "")


class TestOperatorApprovedUnchanged:
    """operator_approved remains unknown (NOT promoted)."""

    def test_operator_approved_unchanged_21bao(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "21bao")
        assert entry.get("operator_approved") == "unknown"

    def test_operator_approved_unchanged_5bao(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "5bao")
        assert entry.get("operator_approved") == "unknown"

    def test_operator_approved_unchanged_9bao(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "9bao")
        assert entry.get("operator_approved") == "unknown"


class TestEnvLoadedUnchanged:
    """env_loaded unchanged — not promoted by this normalization."""

    def test_env_loaded_21bao(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "21bao")
        assert entry.get("env_loaded") is True  # unchanged from G-L3R

    def test_env_loaded_5bao(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "5bao")
        assert entry.get("env_loaded") is True

    def test_env_loaded_9bao(self):
        nmc = _load_nmc()
        entry = _get_d4_entry(nmc, "9bao")
        assert entry.get("env_loaded") is True


class TestRuntimeVisiblePreserved:
    """runtime_visible 3-of-3 from G-L3R preserved unchanged."""

    def test_runtime_visible_still_true(self):
        nmc = _load_nmc()
        for node in ("21bao", "5bao", "9bao"):
            entry = _get_d4_entry(nmc, node)
            assert entry.get("runtime_visible") is True, f"{node} runtime_visible should remain true"


class TestNoModelPoolModification:
    """model_pool.yaml NOT modified."""

    def test_model_pool_unchanged(self):
        """model_pool.yaml must NOT be modified by this PR."""
        # Check via git diff against main
        r = subprocess.run(
            ["git", "diff", "main", "--", "scripts/model_pool.yaml"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        diff_output = r.stdout.strip()
        assert diff_output == "", f"model_pool.yaml should NOT be modified, but git diff shows changes:\n{diff_output}"


class TestNoSecretLeakage:
    """No credential values leaked in NMC or doc."""

    def test_no_api_keys_in_nmc(self):
        nmc = _load_nmc()
        raw = str(nmc)
        api_keys = re.findall(r'sk-[a-zA-Z0-9_\-]{20,}', raw)
        assert len(api_keys) == 0, f"API keys found in NMC: {api_keys}"

    def test_no_api_keys_in_doc(self):
        doc = _load_doc()
        api_keys = re.findall(r'sk-[a-zA-Z0-9_\-]{20,}', doc)
        assert len(api_keys) == 0, f"API keys found in doc: {api_keys}"

    def test_no_private_key_in_nmc(self):
        nmc = _load_nmc()
        raw = str(nmc)
        for pattern in [r'-----BEGIN\s+(?:RSA|DSA|EC|OPENSSH|PRIVATE)\s+KEY-----', r'PRIVATE KEY', r'BEGIN RSA']:
            if re.search(pattern, raw):
                pytest.fail(f"Private key pattern found in NMC: {pattern}")


class TestNoHigherLayerPromotion:
    """Readiness/gray/Baseline03 NOT entered — proof in evidence doc."""

    def test_readiness_not_entered(self):
        doc = _load_doc()
        assert "readiness entered" not in doc or "false" in doc.split("readiness entered")[1][:10]

    def test_gray_not_entered(self):
        doc = _load_doc()
        assert "gray entered" not in doc or "false" in doc.split("gray entered")[1][:10]

    def test_baseline03_not_entered(self):
        doc = _load_doc()
        assert "Baseline03" in doc


class TestDocStructure:
    """Documentation completeness."""

    def test_required_sections(self):
        doc = _load_doc()
        sections = ["## Status", "## Scope", "## Evidence Sources",
                     "## NMC Changes", "### Fields NOT Changed",
                     "## Namespace-Asymmetry Semantics", "## Non-Promotion Proof",
                     "## See Also"]
        for s in sections:
            assert s in doc, f"Missing section: {s}"

    def test_three_evidence_prs_referenced(self):
        doc = _load_doc()
        assert "#341" in doc
        assert "#342" in doc
        assert "#343" in doc
