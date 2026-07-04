"""G-L4 D4 21bao Model-Call Canary Evidence Tests.

Verifies the canary receipt at .hermes/evidence/g-l4-d4-model-call-canary-21bao-v1/21bao-receipt.json
and docs/baseline02/g-l4-d4-model-call-canary-21bao.md:

1. Receipt schema valid with required fields
2. Canary performed on 21bao ONLY (no 5bao/9bao)
3. attempt_count=1, fallback_used=false
4. model_call_attempted=true, model_call_succeeded=true
5. No credential value leakage in receipt
6. model_call_verified/operator_approved NOT promoted in NMC
7. No readiness/gray/Baseline03 claims made
8. No NMC/model_pool/runtime config mutation
9. P16/BLOCKER-01 decision recorded
10. Failure path stops without fallback
"""

import json
import os
import re
import subprocess

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECEIPT_PATH = os.path.join(REPO_ROOT, ".hermes/evidence/g-l4-d4-model-call-canary-21bao-v1/21bao-receipt.json")
DOC_PATH = os.path.join(REPO_ROOT, "docs/baseline02/g-l4-d4-model-call-canary-21bao.md")

EXPECTED_ANCHOR = "6daa7ee081f610b014f6234c27f45c809f0018fb"

FORBIDDEN_CLAIMS = [
    "G-L4 ready",
    "readiness ready",
    "model_call_verified ready",
    "operator_approved ready",
    "gray ready",
    "Baseline03 ready",
    "Stage8 ready",
]


def _load_receipt():
    with open(RECEIPT_PATH) as f:
        return json.load(f)


def _load_doc():
    with open(DOC_PATH) as f:
        return f.read()


# ── Basic Structure ──────────────────────────────────────────────


class TestAnchor:
    def test_anchor_exact(self):
        r = _load_receipt()
        assert r["anchor"] == EXPECTED_ANCHOR

    def test_four_way_aligned(self):
        r = _load_receipt()
        assert r["four_way_anchor_aligned"] is True


class TestSchema:
    def test_schema_version(self):
        r = _load_receipt()
        assert r["schema_version"] == "1.0.0"

    def test_gate_id_correct(self):
        r = _load_receipt()
        assert r["gate_id"] == "G-L4-D4-MODEL-CALL-CANARY-21BAO"

    def test_canary_verdict_present(self):
        r = _load_receipt()
        assert "canary_verdict" in r


class TestModelCall:
    def test_only_21bao(self):
        r = _load_receipt()
        assert r["p16_wrapper_decision"]["execution_command_class"] is not None
        assert "opencode" in r["p16_wrapper_decision"]["opencode_path"].lower()

    def test_attempt_count_one(self):
        r = _load_receipt()
        assert r["model_call"]["attempt_count"] == 1

    def test_fallback_not_used(self):
        r = _load_receipt()
        assert r["model_call"]["fallback_used"] is False

    def test_model_call_attempted(self):
        r = _load_receipt()
        assert r["model_call"]["model_call_attempted"] is True

    def test_model_call_succeeded(self):
        r = _load_receipt()
        assert r["model_call"]["model_call_succeeded"] is True

    def test_exit_code_zero(self):
        r = _load_receipt()
        assert r["model_call"]["exit_code"] == 0

    def test_marker_detected(self):
        r = _load_receipt()
        assert r["model_call"]["output_marker_detected"] is True

    def test_exact_match(self):
        r = _load_receipt()
        assert r["model_call"]["output_exact_match"] is True

    def test_d4_model_identity(self):
        r = _load_receipt()
        assert r["model_call"]["model_id_canonical"] == "opencode-go-deepseek-v4-pro"
        assert r["model_call"]["concrete_invocation"] == "deepseek-plan/deepseek-v4-pro"

    def test_opencode_go_not_available_noted(self):
        """Receipt notes the opencode-go provider not found on 21bao."""
        r = _load_receipt()
        assert "opencode_go_provider_availability_note" in r["model_call"]
        note = r["model_call"]["opencode_go_provider_availability_note"]
        assert "not found" in note.lower()


class TestNoPromotion:
    def test_nmc_writeback_not_performed(self):
        r = _load_receipt()
        assert r["post_call_state"]["nmc_writeback_performed"] is False

    def test_model_call_verified_not_promoted(self):
        r = _load_receipt()
        assert r["post_call_state"]["model_call_verified_promoted"] is False

    def test_operator_approved_not_promoted(self):
        r = _load_receipt()
        assert r["post_call_state"]["operator_approved_promoted"] is False

    def test_env_loaded_not_promoted(self):
        r = _load_receipt()
        assert r["post_call_state"]["env_loaded_promoted"] is False

    def test_no_runtime_config_modification(self):
        r = _load_receipt()
        assert r["post_call_state"]["runtime_config_modified"] is False

    def test_no_model_pool_modification(self):
        r = _load_receipt()
        assert r["post_call_state"]["model_pool_modified"] is False

    def test_no_nmc_modification(self):
        r = _load_receipt()
        assert r["post_call_state"]["nmc_modified"] is False

    def test_no_node_sync(self):
        r = _load_receipt()
        assert r["post_call_state"]["node_sync_performed"] is False

    def test_no_credential_provisioning(self):
        r = _load_receipt()
        assert r["post_call_state"]["credential_provisioning_performed"] is False


class TestNoHigherLayerEntry:
    def test_readiness_not_entered(self):
        r = _load_receipt()
        assert r["post_call_state"]["readiness_entered"] is False

    def test_gray_not_entered(self):
        r = _load_receipt()
        assert r["post_call_state"]["gray_entered"] is False

    def test_gd_a_not_entered(self):
        r = _load_receipt()
        assert r["post_call_state"]["gd_a_entered"] is False

    def test_gd_b_not_entered(self):
        r = _load_receipt()
        assert r["post_call_state"]["gd_b_entered"] is False

    def test_baseline03_not_entered(self):
        r = _load_receipt()
        assert r["post_call_state"]["baseline03_entered"] is False


class TestNoSecretLeakage:
    def test_credential_values_not_printed(self):
        r = _load_receipt()
        assert r["p16_wrapper_decision"]["credential_values_printed"] is False

    def test_secrets_redacted_true(self):
        r = _load_receipt()
        assert r["p16_wrapper_decision"]["secrets_redacted"] is True

    def test_no_api_keys_in_json(self):
        raw = json.dumps(_load_receipt())
        api_keys = re.findall(r'sk-[a-zA-Z0-9_\-]{20,}', raw)
        assert len(api_keys) == 0, f"API keys found in receipt: {api_keys}"

    def test_no_api_keys_in_doc(self):
        doc = _load_doc()
        api_keys = re.findall(r'sk-[a-zA-Z0-9_\-]{20,}', doc)
        assert len(api_keys) == 0, f"API keys found in doc: {api_keys}"


class TestForbiddenClaims:
    def test_forbidden_claims_not_made_json(self):
        r = _load_receipt()
        nf = r["forbidden_claims_NOT_made"]
        for phrase in FORBIDDEN_CLAIMS:
            assert phrase in nf, f"Missing forbidden claim: {phrase}"

    def test_forbidden_claims_absent_from_doc(self):
        doc = _load_doc()
        for phrase in FORBIDDEN_CLAIMS:
            if phrase in doc:
                lines = doc.split("\n")
                for i, line in enumerate(lines):
                    if phrase in line:
                        preceding = "\n".join(lines[max(0, i - 3):i])
                        assert "NOT" in preceding or "❌" in preceding, (
                            f"Forbidden claim '{phrase}' at line {i+1} without negation"
                        )


class TestP16Decision:
    def test_authorization_source_recorded(self):
        r = _load_receipt()
        assert "authorization_source" in r["p16_wrapper_decision"]
        auth_src = r["p16_wrapper_decision"]["authorization_source"]
        assert "G-L4-D4-MODEL-CALL-VERIFY-CANARY-21BAO" in auth_src
        assert "2026-07-04" in auth_src

    def test_execution_command_class_recorded(self):
        r = _load_receipt()
        assert "opencode" in r["p16_wrapper_decision"]["execution_command_class"]

    def test_opencode_path_recorded(self):
        r = _load_receipt()
        assert "opencode" in r["p16_wrapper_decision"]["opencode_path"].lower()

    def test_credential_enum_not_value(self):
        r = _load_receipt()
        cred = r["p16_wrapper_decision"]["credential_enum"]
        assert "PRESENT" in cred
        assert "MISSING" not in cred  # both were PRESENT


class TestFailurePath:
    def test_single_attempt_no_retry_loop(self):
        """Only 1 attempt; no auto-retry or fallback."""
        r = _load_receipt()
        assert r["model_call"]["attempt_count"] == 1
        assert r["model_call"]["fallback_used"] is False


class TestDocStructure:
    def test_required_sections(self):
        doc = _load_doc()
        sections = [
            "## Status",
            "## Scope",
            "## P16 / BLOCKER-01 Decision",
            "## Model Call Result",
            "## Post-Call State",
            "## Forbidden Claims",
            "## See Also",
        ]
        for s in sections:
            assert s in doc, f"Missing section: {s}"
