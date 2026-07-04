"""G-L4 D4 5bao Model-Call Canary Evidence Tests.

Verifies the canary receipt at .hermes/evidence/g-l4-d4-model-call-canary-5bao-v1/5bao-receipt.json
and docs/baseline02/g-l4-d4-model-call-canary-5bao.md:

1. Receipt schema valid with required fields
2. Canary performed on 5bao ONLY (no 21bao/9bao)
3. attempt_count=1, fallback_used=false
4. model_call_attempted=true, model_call_succeeded=true
5. No credential value leakage in receipt
6. model_call_verified/operator_approved NOT promoted in NMC
7. No readiness/gray/Baseline03 claims made
8. No NMC/model_pool/runtime config mutation
9. SSH transport documented without remote config modification
10. Distinct from PR #341 21bao canary
"""

import json
import os
import re

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECEIPT_PATH = os.path.join(REPO_ROOT, ".hermes/evidence/g-l4-d4-model-call-canary-5bao-v1/5bao-receipt.json")
DOC_PATH = os.path.join(REPO_ROOT, "docs/baseline02/g-l4-d4-model-call-canary-5bao.md")

EXPECTED_ANCHOR = "d78d5463daf84784778051e18578710c042a0093"

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
        assert r["gate_id"] == "G-L4-D4-MODEL-CALL-CANARY-5BAO"

    def test_canary_verdict_present(self):
        r = _load_receipt()
        assert r["canary_verdict"] == "G_L4_D4_5BAO_CANARY_PASS"


class TestNodeScope:
    def test_node_is_5bao(self):
        r = _load_receipt()
        assert r["ssh_transport"]["node"] == "5bao"

    def test_no_21bao_execution(self):
        r = _load_receipt()
        nf = r["forbidden_claims_NOT_made"]
        assert any("21bao" in c for c in nf), "21bao must be in forbidden claims"

    def test_no_9bao_execution(self):
        r = _load_receipt()
        nf = r["forbidden_claims_NOT_made"]
        assert any("9bao" in c for c in nf), "9bao must be in forbidden claims"


class TestModelCall:
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

    def test_namespace_asymmetry_noted(self):
        r = _load_receipt()
        note = r["model_call"]["opencode_go_provider_availability_note"]
        assert "NOT a fallback" in note
        assert "NOT provider drift" in note
        assert "namespace asymmetry" in note


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

    def test_no_model_pool_modification(self):
        r = _load_receipt()
        assert r["post_call_state"]["model_pool_modified"] is False

    def test_no_nmc_modification(self):
        r = _load_receipt()
        assert r["post_call_state"]["nmc_modified"] is False

    def test_no_runtime_config_modification(self):
        r = _load_receipt()
        assert r["post_call_state"]["runtime_config_modified"] is False


class TestSSHTransport:
    def test_remote_config_not_modified(self):
        r = _load_receipt()
        assert r["ssh_transport"]["remote_config_modified"] is False

    def test_authorized_keys_not_modified(self):
        r = _load_receipt()
        assert r["ssh_transport"]["authorized_keys_modified"] is False

    def test_wrapper_used(self):
        r = _load_receipt()
        assert r["ssh_transport"]["wrapper_used"] is not None
        assert "vibedev-opencode" in r["ssh_transport"]["wrapper_used"]


class TestNoHigherLayerEntry:
    def test_readiness_not_entered(self):
        r = _load_receipt()
        assert r["post_call_state"]["readiness_entered"] is False

    def test_gray_not_entered(self):
        r = _load_receipt()
        assert r["post_call_state"]["gray_entered"] is False

    def test_baseline03_not_entered(self):
        r = _load_receipt()
        assert r["post_call_state"]["baseline03_entered"] is False


class TestDistinctFrom21bao:
    def test_21bao_canary_pr_referenced(self):
        r = _load_receipt()
        assert r["post_call_state"]["21bao_canary_pr"] == 341

    def test_distinct_note_present(self):
        r = _load_receipt()
        note = r["post_call_state"]["21bao_canary_distinct_note"]
        assert "separate execution" in note

    def test_5bao_verdict_different_from_21bao(self):
        """The 5bao verdict is distinct from 21bao verdict."""
        r = _load_receipt()
        assert "5BAO" in r["canary_verdict"]


class TestNoSecretLeakage:
    def test_credential_values_not_printed(self):
        r = _load_receipt()
        assert r["ssh_transport"]["credential_values_printed"] is False

    def test_secrets_redacted_true(self):
        r = _load_receipt()
        assert r["ssh_transport"]["secrets_redacted"] is True

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
                            f"'{phrase}' at line {i+1} without negation"
                        )


class TestDangerouslySkipPermissions:
    def test_dsp_flag_used(self):
        r = _load_receipt()
        assert r["dangerously_skip_permissions"]["flag_used"] is True

    def test_dsp_no_repo_content(self):
        r = _load_receipt()
        assert r["dangerously_skip_permissions"]["mitigation_no_repo_content_sent"] is True

    def test_dsp_no_secrets(self):
        r = _load_receipt()
        assert r["dangerously_skip_permissions"]["mitigation_no_secrets_sent"] is True

    def test_dsp_no_tool_execution(self):
        r = _load_receipt()
        assert r["dangerously_skip_permissions"]["mitigation_no_tool_execution"] is True

    def test_dsp_no_fallback(self):
        r = _load_receipt()
        assert r["dangerously_skip_permissions"]["mitigation_no_fallback"] is True


class TestMaxAttempts:
    def test_single_attempt_no_retry(self):
        r = _load_receipt()
        assert r["model_call"]["attempt_count"] == 1
        assert r["model_call"]["fallback_used"] is False


class TestDocStructure:
    def test_required_sections(self):
        doc = _load_doc()
        sections = [
            "## Status",
            "## Scope",
            "## SSH Transport",
            "## Model Call Result",
            "### Risk Mitigation",
            "### Important Note",
            "## Post-Call State",
            "## Relationship to PR #341",
            "## Forbidden Claims",
            "## See Also",
        ]
        for s in sections:
            assert s in doc, f"Missing section: {s}"

    def test_doc_references_pr341(self):
        doc = _load_doc()
        assert "PR #341" in doc

    def test_doc_5bao_specific_marker(self):
        doc = _load_doc()
        assert "D4_CANARY_OK_5BAO" in doc
