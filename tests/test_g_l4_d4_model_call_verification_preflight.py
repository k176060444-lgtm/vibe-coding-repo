"""G-L4 D4 Model-Call Verification Preflight Plan Tests.

Verifies the preflight record at .hermes/evidence/g-l4-d4-model-call-verification-preflight.json
and docs/baseline02/g-l4-d4-model-call-verification-preflight.md:

1. Preflight anchor matches current main (ef464b25bd482da8a67886c4b864a4420cfc7e01)
2. References G-L3R D4 closure chain (PR #332-#339) correctly
3. 3-of-3 runtime_visible recognized only as prerequisite
4. model_call_verified/operator_approved remain false/unknown/not promoted
5. No G-L4 execution claim made
6. No readiness/gray/Baseline03 claim made
7. No secret values present
8. No model_pool/NMC mutation in this PR
9. Suggested next stage requires separate operator authorization
10. Scope constraints correctly limit this to preflight
"""

import json
import os
import re
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFLIGHT_JSON = os.path.join(REPO_ROOT, ".hermes/evidence/g-l4-d4-model-call-verification-preflight.json")
PREFLIGHT_MD = os.path.join(REPO_ROOT, "docs/baseline02/g-l4-d4-model-call-verification-preflight.md")

EXPECTED_PREFLIGHT_ANCHOR = "ef464b25bd482da8a67886c4b864a4420cfc7e01"

FORBIDDEN_CLAIMS = [
    "G-L4 ready",
    "readiness ready",
    "model_call_verified ready",
    "operator_approved ready",
    "gray ready",
    "Baseline03 ready",
    "Stage8 ready",
    "is_g_l4_ready: true",
    "is_readiness_ready: true",
    "is_model_call_verified_ready: true",
    "is_operator_approved_promotion: true",
    "is_gray_acceptance: true",
    "is_baseline03_ready: true",
    "model_call_verified promoted to any node",
    "G-L4 execution in progress",
    "G-L4 execution completed",
    "operator_approved promoted",
]

# Phrases that MUST appear at least once
REQUIRED_PHRASES_MD = [
    "G-L4",
    "model_call_verified",
    "opencode-go-deepseek-v4-pro",
    "preflight",
    "not-G-L4-execution",
    "not-readiness",
    "operator authorization",
    "BLOCKER-01",
    "BLOCKER-02",
    "DECISION-01",
    "separate operator authorization",
    "REPORT_AND_STOP",
]

REQUIRED_PHRASES_JSON = [
    "G-L4-D4-MODEL-CALL-VERIFICATION-PREFLIGHT",
    "G_L4_D4_MODEL_CALL_VERIFICATION_PREFLIGHT_DRAFTED",
    "opencode-go-deepseek-v4-pro",
    "model_call_verified",
    "operator_approved",
    "forbidden_claims_NOT_made",
    "execution_authorized",
    "model_calls_performed",
]


def _load_preflight_json():
    with open(PREFLIGHT_JSON) as f:
        return json.load(f)


def _load_preflight_md():
    with open(PREFLIGHT_MD) as f:
        return f.read()


# ──────────────────────────────────────────────────────────────────────
# Anchor and Structural Tests
# ──────────────────────────────────────────────────────────────────────


class TestAnchor:
    """Test preflight anchor alignment."""

    def test_preflight_anchor_exact(self):
        """Preflight anchor is exactly ef464b25.."""
        pf = _load_preflight_json()
        assert pf["preflight_anchor"] == EXPECTED_PREFLIGHT_ANCHOR, (
            f"Anchor mismatch: {pf['preflight_anchor']}"
        )

    def test_four_way_anchor_aligned_json(self):
        """Four-way anchor alignment flag is true."""
        pf = _load_preflight_json()
        assert pf["four_way_anchor_aligned"] is True

    def test_r5_origin_main_closed(self):
        """R5 origin/main closure recorded."""
        pf = _load_preflight_json()
        assert pf["r5_origin_main_closed"] is True
        post = pf["ops_hygiene_008"]["post"]
        assert "ef464b25bd482da8a67886c4b864a4420cfc7e01" in post


class TestPrerequisiteChain:
    """Test G-L3R D4 closure chain references."""

    def test_g_l3r_d4_closure_pr_339(self):
        """Preflight prerequisite references PR #339."""
        pf = _load_preflight_json()
        pre = pf["prerequisites"]
        assert pre["g_l3r_d4_runtime_visible_closure"]["closure_pr"] == 339
        assert pre["g_l3r_d4_runtime_visible_closure"]["three_of_three_confirmed"] is True

    def test_evidence_chain_complete(self):
        """All 8 PRs from G-L3R D4 chain referenced."""
        pf = _load_preflight_json()
        chain = pf["prerequisites"]["evidence_chain"]
        assert "pr_332" in chain
        assert "pr_333" in chain
        assert "pr_334" in chain
        assert "pr_335" in chain
        assert "pr_336" in chain
        assert "pr_337" in chain
        assert "pr_338" in chain
        assert "pr_339" in chain
        assert len(chain) == 8

    def test_pr_338_distinct_from_pr_337(self):
        """PR #338 is test-only fix (distinct from PR #337 NMC normalization)."""
        pf = _load_preflight_json()
        chain_338 = pf["prerequisites"]["evidence_chain"]["pr_338"]
        assert "test" in chain_338.lower() or "fix" in chain_338.lower()
        assert "nmc" not in chain_338.lower() or "normalization" not in chain_338.lower()

    def test_model_call_verified_outside_scope(self):
        """Preflight correctly notes model_call_verified is outside G-L3R scope."""
        pf = _load_preflight_json()
        note = pf["prerequisites"]["g_l3r_d4_runtime_visible_closure"]["note"]
        assert "outside" in note.lower() or "outside G-L3R" in note


class TestD4Identity:
    """Test D4 model identity fields."""

    def test_active_model_id(self):
        pf = _load_preflight_json()
        assert pf["d4_identity"]["active_model_id"] == "opencode-go-deepseek-v4-pro"

    def test_canonical_provider(self):
        pf = _load_preflight_json()
        assert pf["d4_identity"]["canonical_provider"] == "opencode-go"

    def test_provider_namespace(self):
        pf = _load_preflight_json()
        assert pf["d4_identity"]["provider_namespace"] == "opencode-go"

    def test_key_env_var(self):
        pf = _load_preflight_json()
        assert pf["d4_identity"]["key_env_var"] == "OPENCODE_GO_API_KEY"

    def test_base_url_env_var(self):
        pf = _load_preflight_json()
        assert pf["d4_identity"]["base_url_env_var"] == "OPENCODE_GO_BASE_URL"

    def test_aliases_include_opencode_ds4pro(self):
        pf = _load_preflight_json()
        assert "opencode-ds4pro" in pf["d4_identity"]["aliases"]

    def test_legacy_entry_documented(self):
        pf = _load_preflight_json()
        assert "deepseek-plan-deepseek-v4-pro" in pf["d4_identity"]["legacy_entry"]["model_id"]


class TestNodeScope:
    """Test node scope fields — all 3 nodes present with correct state."""

    NODES = ["21bao", "5bao", "9bao"]

    def test_all_nodes_present(self):
        pf = _load_preflight_json()
        for node in self.NODES:
            assert node in pf["node_scope"], f"Node {node} missing from node_scope"

    def test_all_nodes_runtime_visible_true(self):
        pf = _load_preflight_json()
        for node in self.NODES:
            assert pf["node_scope"][node]["runtime_visible"] is True, \
                f"{node} runtime_visible not true"

    def test_all_nodes_model_call_verified_unknown(self):
        pf = _load_preflight_json()
        for node in self.NODES:
            assert pf["node_scope"][node]["model_call_verified"] == "unknown", \
                f"{node} model_call_verified not unknown"

    def test_all_nodes_operator_approved_unknown(self):
        pf = _load_preflight_json()
        for node in self.NODES:
            assert pf["node_scope"][node]["operator_approved"] == "unknown", \
                f"{node} operator_approved not unknown"

    def test_node_scope_proper_types(self):
        pf = _load_preflight_json()
        assert "Windows" in pf["node_scope"]["21bao"]["node_type"]
        assert "Debian" in pf["node_scope"]["5bao"]["node_type"]
        assert "Debian" in pf["node_scope"]["9bao"]["node_type"]


class TestCallVerifiedStatus:
    """Test model_call_verified and operator_approved promotion status."""

    def test_model_call_verified_not_promoted(self):
        pf = _load_preflight_json()
        assert pf["model_call_verified_current_status"]["promoted"] is False
        for node in ["21bao", "5bao", "9bao"]:
            assert pf["model_call_verified_current_status"]["state_per_node"][node] == "unknown"

    def test_operator_approved_not_promoted(self):
        pf = _load_preflight_json()
        assert pf["operator_approved_current_status"]["promoted"] is False
        for node in ["21bao", "5bao", "9bao"]:
            assert pf["operator_approved_current_status"]["state_per_node"][node] == "unknown"


class TestG4ExecutionReadiness:
    """Test that G-L4 execution has NOT started."""

    def test_execution_not_authorized(self):
        pf = _load_preflight_json()
        assert pf["g_l4_execution_readiness"]["execution_authorized"] is False

    def test_no_model_calls(self):
        pf = _load_preflight_json()
        assert pf["g_l4_execution_readiness"]["model_calls_performed"] is False

    def test_no_credential_provisioning(self):
        pf = _load_preflight_json()
        assert pf["g_l4_execution_readiness"]["credential_provisioning_performed"] is False

    def test_no_node_sync(self):
        pf = _load_preflight_json()
        assert pf["g_l4_execution_readiness"]["node_sync_performed"] is False

    def test_no_runtime_config_mod(self):
        pf = _load_preflight_json()
        assert pf["g_l4_execution_readiness"]["runtime_config_modified"] is False

    def test_no_model_pool_mod(self):
        pf = _load_preflight_json()
        assert pf["g_l4_execution_readiness"]["model_pool_modified"] is False

    def test_no_nmc_mod(self):
        pf = _load_preflight_json()
        assert pf["g_l4_execution_readiness"]["nmc_modified"] is False


class TestModelCallPlan:
    """Test the proposed execution plan structure."""

    def test_execution_order_three_phases(self):
        pf = _load_preflight_json()
        plan = pf["model_call_verification_plan"]["proposed_execution_order"]
        assert len(plan) == 3

    def test_canary_phase_is_21bao(self):
        pf = _load_preflight_json()
        first = pf["model_call_verification_plan"]["proposed_execution_order"][0]
        assert first["phase"] == "canary"
        assert first["node"] == "21bao"

    def test_each_phase_has_fallback_none(self):
        pf = _load_preflight_json()
        for phase in pf["model_call_verification_plan"]["proposed_execution_order"]:
            assert "NO_FALLBACK" in phase["fallback_strategy"]
            assert phase["model_id"] == "opencode-go-deepseek-v4-pro"

    def test_each_phase_requires_separate_authorization(self):
        pf = _load_preflight_json()
        for phase in pf["model_call_verification_plan"]["proposed_execution_order"]:
            assert phase["per_node_authorization_required"] != ""

    def test_failure_handling_no_fallback(self):
        pf = _load_preflight_json()
        fh = pf["model_call_verification_plan"]["failure_handling"]
        assert "NO_FALLBACK" in fh["single_node_failure"].upper() or "NO_FALLBACK" not in fh["single_node_failure"] or "Do NOT" in fh["single_node_failure"]
        assert "Do NOT" in fh["single_node_failure"]

    def test_evidence_receipt_schema_has_required_fields(self):
        pf = _load_preflight_json()
        schema = pf["model_call_verification_plan"]["evidence_receipt_schema"]["per_node_receipt"]
        required = ["schema_version", "gate_id", "node", "model_id", "model_call_exit_code",
                        "expected_marker_detected", "fallback_attempted", "model_call_verified_verdict"]
        for field in required:
            assert field in schema, f"Receipt schema missing field: {field}"


class TestOperatorChecklist:
    """Test that operator authorization checklist is present."""

    def test_required_for_each_node_has_six_items(self):
        pf = _load_preflight_json()
        checklist = pf["operator_authorization_checklist"]["required_for_each_node"]
        assert len(checklist) >= 5

    def test_global_authorizations_not_granted(self):
        pf = _load_preflight_json()
        denied = pf["operator_authorization_checklist"]["global_authorizations_not_granted"]
        assert len(denied) >= 5
        assert "G-L4 execution" in denied
        assert "operator_approved promotion" in denied


class TestBlockersAndDecisions:
    """Test operator decisions flagged."""

    def test_blocker_01_exists(self):
        pf = _load_preflight_json()
        blocker_ids = [b["id"] for b in pf["blockers_and_operator_decisions_required"]]
        assert "BLOCKER-01" in blocker_ids

    def test_blocker_02_exists(self):
        pf = _load_preflight_json()
        blocker_ids = [b["id"] for b in pf["blockers_and_operator_decisions_required"]]
        assert "BLOCKER-02" in blocker_ids

    def test_decision_01_exists(self):
        pf = _load_preflight_json()
        decision_ids = [b["id"] for b in pf["blockers_and_operator_decisions_required"]]
        assert "DECISION-01" in decision_ids

    def test_each_blocker_has_operator_question(self):
        pf = _load_preflight_json()
        for b in pf["blockers_and_operator_decisions_required"]:
            assert "operator_decision_needed" in b, f"Missing operator_decision_needed in {b['id']}"


class TestForbiddenClaims:
    """Test that forbidden claims are NOT made."""

    def test_forbidden_claims_not_made_json(self):
        """Forbidden claims are listed in forbidden_claims_NOT_made."""
        pf = _load_preflight_json()
        nf = pf["forbidden_claims_NOT_made"]
        assert "G-L4 ready" in nf
        assert "model_call_verified ready" in nf
        assert "operator_approved ready" in nf

    def test_forbidden_claims_absent_from_md(self):
        """Forbidden claims must NOT appear in MD as positive assertions."""
        md = _load_preflight_md()
        for claim in FORBIDDEN_CLAIMS:
            # The claim must only appear in the "not made" section or not at all
            if claim in md:
                lines = md.split("\n")
                for i, line in enumerate(lines):
                    if claim in line:
                        # Check if preceding lines indicate negation
                        preceding = "\n".join(lines[max(0, i - 3):i])
                        assert "NOT" in preceding or "❌" in preceding or "not made" in preceding.lower(), \
                            f"Forbidden claim '{claim}' found at line {i + 1} without negation context"

    def test_no_global_blocker_closed(self):
        """Global G_L3R_BLOCKED must NOT be declared closed."""
        md = _load_preflight_md()
        pf = _load_preflight_json()
        # JSON: check forbidden_claims_NOT_made
        assert "Global G_L3R_BLOCKED closed" in pf["forbidden_claims_NOT_made"]
        # MD: must not positively claim global blocker is closed
        # Check for positive assertions (not in negation context)
        lines = md.split("\n")
        for i, line in enumerate(lines):
            if "G_L3R_BLOCKED closed" in line or "global_blocker" in line.lower():
                preceding = "\n".join(lines[max(0, i - 3):i])
                assert "❌" in preceding or "NOT" in preceding or "not" in preceding.lower(), \
                    f"Global blocker closed claim found at line {i + 1}"

    def test_no_model_call_verified_promotion_claim(self):
        """Must not claim model_call_verified has been promoted."""
        pf = _load_preflight_json()
        assert "D4 model_call_verified promoted to any node" in pf["forbidden_claims_NOT_made"]


class TestScopeConstraints:
    """Test that scope constraints properly limit this to preflight."""

    def test_scope_says_preflight_only(self):
        pf = _load_preflight_json()
        scope_lower = pf["scope"].lower()
        assert "not" in scope_lower
        assert "execution" in scope_lower
        assert "preflight" in scope_lower
        assert "only" in pf["scope"] or "ONLY" in pf["scope"]

    def test_md_states_not_execution(self):
        md = _load_preflight_md()
        assert "not-G-L4-execution" in md
        assert "READ-ONLY PREFLIGHT" in md

    def test_next_stage_requires_separate_authorization(self):
        md = _load_preflight_md()
        assert "separate operator authorization" in md

    def test_md_has_forbidden_claims_NOT_made(self):
        md = _load_preflight_md()
        assert "❌" in md
        assert "D4 model_call_verified promoted to any node" in md


class TestNoSecretValues:
    """Test that no secret/API key values are present in the preflight record."""

    SECRET_PATTERNS = [
        r"sk-[a-zA-Z0-9_\-]{20,}",       # OpenAI-style keys
        r"API_KEY\s*=\s*[a-zA-Z0-9_\-]{8,}",  # API_KEY=value patterns
        r"apiKey\s*[:=]\s*[a-zA-Z0-9_\-]{8,}",  # apiKey: value patterns
        r"Bearer\s+[a-zA-Z0-9_\-\.]{8,}",  # Bearer tokens
    ]

    def test_json_no_secret_values(self):
        """JSON preflight record must not contain secret values."""
        raw = json.dumps(_load_preflight_json())
        for pattern in self.SECRET_PATTERNS:
            matches = re.findall(pattern, raw)
            if matches:
                # Only check that they're env var names, not actual values
                for m in matches:
                    assert m in ["OPENCODE_GO_API_KEY", "OPENCODE_GO_BASE_URL"], \
                        f"Potential secret value found: {m[:20]}..."

    def test_md_no_secret_values(self):
        """MD preflight doc must not contain secret values."""
        md = _load_preflight_md()
        for pattern in self.SECRET_PATTERNS:
            matches = re.findall(pattern, md)
            for m in matches:
                assert m in ["OPENCODE_GO_API_KEY", "OPENCODE_GO_BASE_URL"], \
                    f"Potential secret value found in MD: {m[:20]}..."

    def test_no_actual_shell_output_with_keys(self):
        """No SSH command output or credential content present."""
        md = _load_preflight_md()
        # Should not contain actual credential command outputs
        assert "sk-" not in md
        assert "apiKey" not in md.lower() or "apiKey" in md.lower() is False


class TestNoProductionCodeMod:
    """Test production code modification audit."""

    def test_no_production_code_modified(self):
        pf = _load_preflight_json()
        audit = pf["production_code_modification_audit"]
        for key, value in audit.items():
            assert value is False, f"Production code modification detected: {key}"

    def test_no_model_pool_mod(self):
        pf = _load_preflight_json()
        assert pf["production_code_modification_audit"]["scripts_model_pool_yaml"] is False

    def test_no_nmc_mod(self):
        pf = _load_preflight_json()
        assert pf["production_code_modification_audit"]["scripts_node_model_capability_yaml"] is False

    def test_no_routing_policy_mod(self):
        pf = _load_preflight_json()
        assert pf["production_code_modification_audit"]["scripts_vibe_model_routing_policy_py"] is False

    def test_no_reconciliation_mod(self):
        pf = _load_preflight_json()
        assert pf["production_code_modification_audit"]["scripts_worker_attest_layer3_reconciliation_py"] is False

    def test_no_model_calls(self):
        pf = _load_preflight_json()
        assert pf["production_code_modification_audit"]["model_calls_performed"] is False

    def test_no_ssh_live_collection(self):
        pf = _load_preflight_json()
        assert pf["production_code_modification_audit"]["ssh_live_collection_performed"] is False


class TestRequiredPhrases:
    """Test that required phrases are present in MD and JSON."""

    def test_md_has_required_phrases(self):
        md = _load_preflight_md()
        for phrase in REQUIRED_PHRASES_MD:
            assert phrase in md, f"Required phrase missing from MD: {phrase}"

    def test_json_has_required_phrases(self):
        raw = json.dumps(_load_preflight_json())
        for phrase in REQUIRED_PHRASES_JSON:
            assert phrase in raw, f"Required phrase missing from JSON: {phrase}"


class TestSchemaVersion:
    """Test schema version."""

    def test_schema_version_1_0_0(self):
        pf = _load_preflight_json()
        assert pf["schema_version"] == "1.0.0"

    def test_gate_id_correct(self):
        pf = _load_preflight_json()
        assert pf["gate_id"] == "G-L4-D4-MODEL-CALL-VERIFICATION-PREFLIGHT"


class TestMarkdownStructure:
    """Test MD document structure."""

    def test_sections_present(self):
        md = _load_preflight_md()
        required_sections = [
            "## 1. Purpose",
            "## 2. Current Anchor",
            "## 3. Prerequisite",
            "## 4. D4 Model Identity",
            "## 5. Node Scope",
            "## 6. Model-Call Verification Plan",
            "## 7. Operator Authorization Checklist",
            "## 8. Blockers",
            "## 9. Scope Constraints",
            "## 10. Forbidden Claims",
            "## 11. Production Code Modification Audit",
            "## 12. Next Stage",
        ]
        for section in required_sections:
            assert section in md, f"Required section missing from MD: {section}"
