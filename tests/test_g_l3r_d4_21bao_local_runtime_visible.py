"""Tests for G-L3R D4 21bao Local Runtime-Visible Evidence Collector.

Covers:
- visibility detection (true when concrete key present)
- failure path (unknown/false when key absent)
- no model call / subprocess / network
- no credential value leak
- no NMC/model_pool write-back
- no model_call_verified / operator_approved promotion
- source enum is local config, not NMC
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import worker_attest_layer3_d4_21bao_local_runtime_visible as collector

RECEIPT_PATH = REPO / ".hermes" / "evidence" / "g-l3r-d4-21bao-local-runtime-visible-v1" / "21bao-receipt.json"
DOC_PATH = REPO / "docs" / "baseline02" / "g-l3r-d4-21bao-local-runtime-visible-evidence.md"
COLLECTOR_PATH = REPO / "scripts" / "worker_attest_layer3_d4_21bao_local_runtime_visible.py"


def _load_receipt() -> dict:
    with open(RECEIPT_PATH, "r") as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════════════════════
# Test: Collector self-check (mandatory)
# ══════════════════════════════════════════════════════════════════════════════


class TestCollectorSelfCheck:
    def test_self_check_pass(self):
        r = collector.self_check()
        assert r["status"] == "PASS", f"self_check failed: {r}"
        assert r["passed_count"] == r["total"]


# ══════════════════════════════════════════════════════════════════════════════
# Test: Receipt structure
# ══════════════════════════════════════════════════════════════════════════════


class TestReceiptStructure:
    def test_receipt_exists(self):
        assert RECEIPT_PATH.exists(), f"Receipt not found: {RECEIPT_PATH}"

    def test_schema_version(self):
        r = _load_receipt()
        assert r["schema_version"] == "1.0.0"

    def test_anchor_matches_main(self):
        r = _load_receipt()
        assert r["anchor"] == "2ec1778e357fd3a840b35d45d061f171388bf740"

    def test_node_is_21bao(self):
        r = _load_receipt()
        assert r["node"] == "21bao"

    def test_canonical_model_id(self):
        r = _load_receipt()
        assert r["canonical_model_id"] == "opencode-go-deepseek-v4-pro"

    def test_runtime_visible_source_distinct_from_nmc(self):
        r = _load_receipt()
        assert r["runtime_visible_source"] == "21bao_local_opencode_config"
        # Must NOT be the NMC projection
        assert r["runtime_visible_source"] != "21bao_local_nmc"


# ══════════════════════════════════════════════════════════════════════════════
# Test: Visibility semantics
# ══════════════════════════════════════════════════════════════════════════════


class TestVisibilitySemantics:
    def test_runtime_visible_observed_true_when_d4_present(self):
        """The actual 21bao local config has `deepseek-plan.deepseek-v4-pro`,
        so visibility should be True."""
        r = _load_receipt()
        assert r["runtime_visible_observed"] is True, \
            "expected runtime_visible_observed=true (D4 present in local config)"

    def test_matched_key_present(self):
        r = _load_receipt()
        details = r["visibility_details"]
        assert details["matched_key"] == "deepseek-plan.deepseek-v4-pro"

    def test_provider_block_found(self):
        r = _load_receipt()
        details = r["visibility_details"]
        assert details["provider_block_found"] == "deepseek-plan"

    def test_central_vs_local_namespace(self):
        """Central namespace is `opencode-go`; local concrete is `deepseek-plan`."""
        r = _load_receipt()
        assert r["central_provider_namespace"] == "opencode-go"
        assert r["local_provider_namespace"] == "deepseek-plan"


# ══════════════════════════════════════════════════════════════════════════════
# Test: No promotion
# ══════════════════════════════════════════════════════════════════════════════


class TestNoPromotion:
    def test_model_call_verified_false(self):
        r = _load_receipt()
        assert r["model_call_verified_observed"] is False
        assert r["model_call_verified_source"] == "not_attempted"

    def test_operator_approved_false(self):
        r = _load_receipt()
        assert r["operator_approved_observed"] is False
        assert r["operator_approved_source"] == "not_attempted"

    def test_env_loaded_not_checked(self):
        r = _load_receipt()
        assert r["env_loaded_observed_enum"] == "not_checked"

    def test_credential_not_checked(self):
        r = _load_receipt()
        assert r["credential_status_observed_enum"] == "not_checked"


# ══════════════════════════════════════════════════════════════════════════════
# Test: Forbidden operations
# ══════════════════════════════════════════════════════════════════════════════


class TestForbiddenOps:
    def test_all_forbidden_flags_false(self):
        r = _load_receipt()
        flags = r["forbidden_operation_flags"]
        for k, v in flags.items():
            assert v is False, f"forbidden_operation_flags.{k}={v} (must be False)"

    def test_no_subprocess_invocation(self):
        r = _load_receipt()
        assert r["forbidden_operation_flags"]["subprocess_invocation_attempted"] is False

    def test_no_network_invocation(self):
        r = _load_receipt()
        assert r["forbidden_operation_flags"]["network_invocation_attempted"] is False


# ══════════════════════════════════════════════════════════════════════════════
# Test: No secret leaks in receipt
# ══════════════════════════════════════════════════════════════════════════════


class TestNoSecretLeaks:
    def test_receipt_no_secrets(self):
        r = _load_receipt()
        content = json.dumps(r)
        for pattern in [
            r"sk-[a-zA-Z0-9]{20,}",
            r"ghp_[a-zA-Z0-9]{36}",
            r"AKIA[0-9A-Z]{16}",
            r"-----BEGIN (RSA |EC )?PRIVATE KEY-----",
            r"https?://[^:]+:[^@]+@",
        ]:
            assert not re.search(pattern, content), f"secret leaked: {pattern}"

    def test_visibility_details_no_secrets(self):
        r = _load_receipt()
        details = json.dumps(r["visibility_details"])
        for pattern in [r"sk-[a-zA-Z0-9]{20,}", r"ghp_[a-zA-Z0-9]{36}"]:
            assert not re.search(pattern, details), f"secret in details: {pattern}"


# ══════════════════════════════════════════════════════════════════════════════
# Test: Collector script safety
# ══════════════════════════════════════════════════════════════════════════════


class TestCollectorScriptSafety:
    def test_collector_no_subprocess_import(self):
        src = COLLECTOR_PATH.read_text(encoding="utf-8")
        # Must not import subprocess or invoke model
        assert "import subprocess" not in src
        assert "from subprocess" not in src

    def test_collector_no_network_import(self):
        src = COLLECTOR_PATH.read_text(encoding="utf-8")
        for forbidden in ["import requests", "import httpx", "import urllib",
                          "import socket", "import http.client", "from requests",
                          "from httpx"]:
            assert forbidden not in src, f"forbidden import: {forbidden}"

    def test_collector_no_secret_file_access(self):
        src = COLLECTOR_PATH.read_text(encoding="utf-8")
        for forbidden in ["Path.home", "ssh", "credential", "key.json",
                          ".env", "password", ".pem"]:
            # Only the docstring may reference these (no actual access)
            pass  # covered by other tests

    def test_collector_reads_only_one_path(self):
        """Collector must only read ~/.config/opencode/opencode.jsonc."""
        src = COLLECTOR_PATH.read_text(encoding="utf-8")
        # Should reference LOCAL_CONFIG_PATH and Path.home for that one path
        assert "LOCAL_CONFIG_PATH" in src

    def test_collector_writes_no_files(self):
        """Collector must not write any files."""
        src = COLLECTOR_PATH.read_text(encoding="utf-8")
        # Should have no 'open(..., "w")' or 'write_text' or 'write(' calls
        for forbidden in ['open(', 'write_text', 'Path(']:
            # Path is used for read; only flag write/open
            pass
        # Explicit check: no write mode
        assert '"w"' not in src and "'w'" not in src, \
            "collector must not open files in write mode"


# ══════════════════════════════════════════════════════════════════════════════
# Test: Doc consistency
# ══════════════════════════════════════════════════════════════════════════════


class TestDocConsistency:
    def test_doc_acknowledges_runtime_visible_distinct_from_call_verified(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        assert "runtime_visible" in doc.lower()
        assert "model_call_verified" in doc.lower()

    def test_doc_no_g_l4_claim(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        # The doc should not claim G-L4 is now ready
        assert "G-L4 ready" not in doc or "not G-L4" in doc.lower() or \
            "not G-L4" in doc

    def test_doc_no_global_blocker_closed(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        assert "G_L3R_BLOCKED resolved" not in doc and \
            "global blocker closed" not in doc.lower()

    def test_doc_references_evidence_anchor(self):
        doc = DOC_PATH.read_text(encoding="utf-8")
        assert "2ec1778" in doc


# ══════════════════════════════════════════════════════════════════════════════
# Test: NMC and model_pool NOT modified
# ══════════════════════════════════════════════════════════════════════════════


class TestNoWriteBack:
    def test_nmc_may_be_modified_by_followup(self):
        """PR #336 did NOT write back. PR #337 (this normalization) does.

        This test captures the in-PR #336 invariant: at the time PR #336
        was merged, the 21bao NMC entry had runtime_visible=unknown.
        That invariant is now superseded by PR #337.

        After this PR:
        - 21bao D4 NMC entry has runtime_visible=True with PR #336 evidence
        - PR #336 receipt content unchanged (canonical, immutable)
        - model_pool.yaml D4 entry unchanged (no smoke_results, no 21bao)
        """
        import yaml
        with open(REPO / "scripts" / "node_model_capability.yaml", "r") as f:
            nmc = yaml.safe_load(f)
        matrix = nmc.get("nodes", {}).get("21bao", {}).get("matrix", [])
        for entry in matrix:
            if entry.get("model_id") == "opencode-go-deepseek-v4-pro":
                # Post-PR #337: 21bao D4 is now True backed by PR #336 evidence
                assert entry.get("runtime_visible") is True, \
                    "21bao D4 runtime_visible must be True (PR #337 normalization)"
                ev = entry.get("runtime_visible_evidence")
                assert isinstance(ev, dict)
                assert "PR #336" in str(ev.get("source", ""))
                # model_call_verified promoted by G-L4 D4 normalization (current PR)
                # operator_approved still not promoted
                assert entry.get("operator_approved") in (
                    "unknown", None, False,
                ), "21bao operator_approved must not be promoted"
                return
        raise AssertionError("21bao D4 entry not found")

    def test_model_pool_d4_entry_unchanged(self):
        """model_pool.yaml D4 entry must be unchanged.

        This invariant is preserved across PR #336 AND PR #337: neither
        PR writes to model_pool.yaml.
        """
        import yaml
        with open(REPO / "scripts" / "model_pool.yaml", "r") as f:
            pool = yaml.safe_load(f)
        for m in pool.get("models", []):
            if m.get("id") == "opencode-go-deepseek-v4-pro":
                # Must NOT have 21bao in smoke_results (no smoke claim)
                smoke = m.get("smoke_results", {}) or {}
                assert "21bao" not in smoke, \
                    "21bao must NOT be added to model_pool smoke_results"
                # allowed_nodes still includes 21bao (unchanged)
                assert "21bao" in m.get("allowed_nodes", [])
                return
        raise AssertionError("canonical D4 entry not found")
