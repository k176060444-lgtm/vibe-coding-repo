"""
Tests for scripts/worker_attest_layer3_runtime_plan.py — G-L3R plan/schema/validator.

Coverage:
- G-L3F / G-L3R boundary documented
- G_L3R_* verdict enum (no G_L3F_* or E2E_* reuse)
- Active live receipt mismatch → G_L3R_BLOCKED
- Missing authorized live receipt → G_L3R_BLOCKED / worker_attest_missing
- DEU live evidence → G_L3R_PASS_WITH_WARN (no promotion)
- Forbidden operation flag True → G_L3R_BLOCKED
- Redaction false / secret leak → G_L3R_STOP_SECRET_RISK
- Schema/anchor mismatch → G_L3R_STOP_AND_REANCHOR
- No automatic runtime field promotion
- DeepSeek V4 Pro not special-cased
- No SSH / subprocess / http / os.environ / model call / write path
"""

from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import worker_attest_layer3_runtime_plan as l3rp

# ── Paths ─────────────────────────────────────────────────────────────────────

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "worker_attest_layer3_runtime_plan.py"


def _good_receipt(model_id: str = "opencode-go-deepseek-v4-flash",
                  provider_namespace: str = "opencode-go",
                  runtime_visible: bool = True,
                  env_loaded: bool = True,
                  credential_status: str = "present",
                  forbid_flag: str | None = None) -> dict:
    """Build a structurally valid G-L3R live receipt for testing."""
    flags = {f: False for f in l3rp.FORBIDDEN_FLAGS}
    if forbid_flag:
        flags[forbid_flag] = True
    return {
        "schema_version": l3rp.SCHEMA_VERSION,
        "node": "21bao",
        "model_id": model_id,
        "provider_namespace": provider_namespace,
        "runtime_provider": "opencode-go",
        "alias": "opencode-test",
        "runtime_visible_observed": runtime_visible,
        "env_loaded_observed": env_loaded,
        "credential_status_observed": credential_status,
        "endpoint_ref_observed": "OPENCODE_GO_BASE_URL",
        "redaction_status": {sf: True for sf in l3rp.REDACTION_SUBFLAGS},
        "forbidden_operation_flags": flags,
        "collector_mode": "real_read",
        "operator_approval_id": "op-approval-test-001",
        "receipt_anchor": "rcpt-anchor-abc123",
        "source_node": "21bao",
        "collection_status": "collected",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Self-check / plan generation
# ═══════════════════════════════════════════════════════════════════════════════


class TestSelfCheck:
    """Plan module's in-process self-check."""

    def test_self_check_15_15_passes(self):
        result = l3rp.self_check()
        assert result["status"] == "PASS", f"Failed: {result['detail']}"
        assert result["passed_count"] == result["total"]
        assert result["plan_kind"] == "plan_only_no_execution"

    def test_plan_kind_no_execution(self):
        plan = l3rp.build_plan()
        assert plan["kind"] == "plan_only_no_execution"

    def test_scope_note_present(self):
        plan = l3rp.build_plan()
        note = plan["scope_note"].lower()
        # Scope note must contain the key scoping constraints
        assert "does not perform" in note, f"scope_note missing constraints: {note}"
        assert "live" in note and ("collection" in note or "model" in note), f"scope_note missing live limitation: {note}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. G-L3F / G-L3R boundary
# ═══════════════════════════════════════════════════════════════════════════════


class TestBoundary:
    """Boundary between G-L3F (fixture) and G-L3R (live) is documented."""

    def test_boundary_has_g_l3f_and_g_l3r(self):
        b = l3rp.get_l3f_l3r_boundary()
        assert "G_L3F" in b
        assert "G_L3R" in b

    def test_g_l3f_evidence_source_fixture(self):
        b = l3rp.get_l3f_l3r_boundary()
        assert "fixture" in b["G_L3F"]["evidence_source"].lower()

    def test_g_l3r_evidence_source_live(self):
        b = l3rp.get_l3f_l3r_boundary()
        assert "live" in b["G_L3R"]["evidence_source"].lower()

    def test_g_l3r_can_be_run_now_false(self):
        """G-L3R must NOT be runnable now."""
        b = l3rp.get_l3f_l3r_boundary()
        assert b["G_L3R"]["can_be_run_now"] is False
        assert b["G_L3R"]["live_collection_in_this_pr"] is False

    def test_g_l3f_verdict_namespace_documented(self):
        b = l3rp.get_l3f_l3r_boundary()
        assert b["G_L3F"]["verdict_namespace"] == "G_L3F_*"

    def test_g_l3r_verdict_namespace_documented(self):
        b = l3rp.get_l3f_l3r_boundary()
        assert b["G_L3R"]["verdict_namespace"] == "G_L3R_*"

    def test_boundary_rules_present(self):
        b = l3rp.get_l3f_l3r_boundary()
        assert "boundary_rules" in b
        assert len(b["boundary_rules"]) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 3. G_L3R_* verdict enum
# ═══════════════════════════════════════════════════════════════════════════════


class TestVerdictEnum:
    """G_L3R_* verdicts, no G_L3F_* or E2E_* reuse."""

    EXPECTED_VERDICTS = {
        "G_L3R_NOT_COLLECTED",
        "G_L3R_PASS",
        "G_L3R_PASS_WITH_WARN",
        "G_L3R_BLOCKED",
        "G_L3R_STOP_SECRET_RISK",
        "G_L3R_STOP_AND_REANCHOR",
    }

    def test_verdict_enum_complete(self):
        plan = l3rp.build_plan()
        actual = set(plan["verdicts"])
        assert actual == self.EXPECTED_VERDICTS, (
            f"verdicts mismatch: extra={actual-self.EXPECTED_VERDICTS} "
            f"missing={self.EXPECTED_VERDICTS-actual}"
        )

    def test_no_g_l3f_in_g_l3r_verdicts(self):
        plan = l3rp.build_plan()
        for v in plan["verdicts"]:
            assert not v.startswith("G_L3F_"), f"G_L3F_* in G_L3R: {v}"

    def test_no_e2e_in_g_l3r_verdicts(self):
        plan = l3rp.build_plan()
        for v in plan["verdicts"]:
            assert not v.startswith("E2E_"), f"E2E_* in G_L3R: {v}"

    def test_verdict_priority_ordering(self):
        p = l3rp._VERDICT_PRIORITY
        assert p["G_L3R_STOP_SECRET_RISK"] > p["G_L3R_STOP_AND_REANCHOR"]
        assert p["G_L3R_STOP_AND_REANCHOR"] > p["G_L3R_BLOCKED"]
        assert p["G_L3R_BLOCKED"] > p["G_L3R_NOT_COLLECTED"]
        assert p["G_L3R_NOT_COLLECTED"] > p["G_L3R_PASS_WITH_WARN"]
        assert p["G_L3R_PASS_WITH_WARN"] > p["G_L3R_PASS"]


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Active live receipt mismatch
# ═══════════════════════════════════════════════════════════════════════════════


class TestActiveMismatch:
    """Active model with live evidence mismatch → G_L3R_BLOCKED."""

    def test_active_runtime_visible_false_blocks(self):
        receipt = _good_receipt(runtime_visible=False)
        declared = {"lifecycle_status": "enabled_assigned",
                    "provider_namespace": "opencode-go"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        assert result["verdict"] == "G_L3R_BLOCKED"
        assert any("runtime_not_visible" in f.get("type", "")
                   for f in result["findings"])

    def test_active_env_loaded_false_blocks(self):
        receipt = _good_receipt(env_loaded=False)
        declared = {"lifecycle_status": "enabled_assigned",
                    "provider_namespace": "opencode-go"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        assert result["verdict"] == "G_L3R_BLOCKED"
        assert any("env_not_loaded" in f.get("type", "")
                   for f in result["findings"])

    def test_active_credential_absent_blocks(self):
        receipt = _good_receipt(credential_status="absent")
        declared = {"lifecycle_status": "enabled_assigned",
                    "provider_namespace": "opencode-go"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        assert result["verdict"] == "G_L3R_BLOCKED"
        assert any("credential" in f["type"]
                   for f in result["findings"])

    def test_namespace_mismatch_blocks(self):
        receipt = _good_receipt(provider_namespace="anthropic")
        declared = {"lifecycle_status": "enabled_assigned",
                    "provider_namespace": "opencode-go"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        assert result["verdict"] == "G_L3R_BLOCKED"
        assert any("namespace" in f["type"]
                   for f in result["findings"])

    def test_unknown_namespace_blocks(self):
        receipt = _good_receipt(provider_namespace="unauthorized-ns")
        declared = {"lifecycle_status": "enabled_assigned",
                    "provider_namespace": "opencode-go"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        assert result["verdict"] == "G_L3R_BLOCKED"
        assert any("unknown_namespace" in f["type"]
                   for f in result["findings"])


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Missing authorized receipt
# ═══════════════════════════════════════════════════════════════════════════════


class TestMissingAuthorizedReceipt:
    """After G-L3R collection is authorized, missing live receipt → G_L3R_BLOCKED."""

    def test_missing_required_fields_blocks(self):
        bad = {"schema_version": l3rp.SCHEMA_VERSION}  # missing fields
        result = l3rp.validate_live_receipt_schema(bad)
        assert result["valid"] is False
        assert len(result["errors"]) > 0

    def test_missing_operator_approval_id_blocks(self):
        receipt = _good_receipt()
        receipt["operator_approval_id"] = ""  # empty
        result = l3rp.validate_live_receipt_schema(receipt)
        assert result["valid"] is False
        assert any("approval_id" in e for e in result["errors"])

    def test_missing_receipt_anchor_blocks(self):
        """Empty receipt_anchor → STOP_AND_REANCHOR via evaluation."""
        receipt = _good_receipt()
        receipt["receipt_anchor"] = ""
        declared = {"lifecycle_status": "enabled_assigned",
                    "provider_namespace": "opencode-go"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        assert result["verdict"] == "G_L3R_STOP_AND_REANCHOR"
        assert any("missing_anchor" in f.get("type", "")
                   for f in result["findings"])

    def test_missing_redaction_subflag_blocks(self):
        receipt = _good_receipt()
        receipt["redaction_status"] = {"no_secret_value": True}  # missing others
        result = l3rp.validate_live_receipt_schema(receipt)
        assert result["valid"] is False
        assert any("subflag" in e for e in result["errors"])

    def test_missing_forbidden_flag_blocks(self):
        receipt = _good_receipt()
        receipt["forbidden_operation_flags"] = {"ssh_attempted": False}  # missing
        result = l3rp.validate_live_receipt_schema(receipt)
        assert result["valid"] is False
        assert any("forbidden_operation_flags" in e for e in result["errors"])

    def test_collection_status_not_collected_blocks_active(self):
        """Active model with collection_status='not_collected' → worker_attest_missing → BLOCKED."""
        receipt = _good_receipt()
        receipt["collection_status"] = "not_collected"
        declared = {"lifecycle_status": "enabled_assigned",
                    "provider_namespace": "opencode-go"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        assert result["verdict"] == "G_L3R_BLOCKED", (
            f"Expected BLOCKED for not_collected, got {result['verdict']}"
        )
        assert any("worker_attest_missing" in f.get("type", "")
                   for f in result["findings"]), (
            "Should find worker_attest_missing finding"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 6. DEU live evidence → WARN only
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeuLiveEvidence:
    """DEU model live evidence → WARN only, never promotion."""

    def test_deu_live_evidence_is_warn(self):
        receipt = _good_receipt(
            model_id="anthropic-claude-opus-4",
            provider_namespace="anthropic",
        )
        declared = {"lifecycle_status": "declared_enabled_unassigned",
                    "provider_namespace": "anthropic"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        # DEU live evidence: warn, not blocked
        assert result["verdict"] in ("G_L3R_PASS_WITH_WARN", "G_L3R_PASS")
        # No blocked findings for DEU
        blocked = [f for f in result["findings"] if f.get("severity") == "blocked"]
        assert not blocked, f"DEU should not be blocked: {blocked}"

    def test_deu_with_runtime_visible_false_does_not_block(self):
        """DEU runtime_visible=False is informational, not a block."""
        receipt = _good_receipt(
            model_id="anthropic-claude-opus-4",
            provider_namespace="anthropic",
            runtime_visible=False,
        )
        declared = {"lifecycle_status": "declared_enabled_unassigned",
                    "provider_namespace": "anthropic"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        # DEU should never block
        assert result["verdict"] != "G_L3R_BLOCKED", (
            f"DEU should not block: {result}"
        )

    def test_deu_finding_appears_in_warn_only(self):
        """DEU finding must have severity=warn."""
        receipt = _good_receipt(
            model_id="anthropic-claude-opus-4",
            provider_namespace="anthropic",
        )
        declared = {"lifecycle_status": "declared_enabled_unassigned",
                    "provider_namespace": "anthropic"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        deu_findings = [f for f in result["findings"]
                        if "deu" in f.get("type", "").lower()]
        if deu_findings:
            for f in deu_findings:
                assert f.get("severity") == "warn"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Forbidden operation flag → BLOCKED
# ═══════════════════════════════════════════════════════════════════════════════


class TestForbiddenFlag:
    """Any forbidden operation flag True → G_L3R_BLOCKED."""

    @pytest.mark.parametrize("flag", l3rp.FORBIDDEN_FLAGS)
    def test_forbidden_flag_true_blocks(self, flag):
        receipt = _good_receipt(forbid_flag=flag)
        declared = {"lifecycle_status": "enabled_assigned",
                    "provider_namespace": "opencode-go"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        assert result["verdict"] == "G_L3R_BLOCKED", (
            f"flag={flag} verdict={result['verdict']}"
        )
        assert any(flag in f.get("type", "")
                   for f in result["findings"])


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Redaction / secret leak → STOP_SECRET_RISK
# ═══════════════════════════════════════════════════════════════════════════════


class TestRedactionLeak:
    """Redaction false or secret leak → G_L3R_STOP_SECRET_RISK."""

    def test_redaction_false_stops(self):
        receipt = _good_receipt()
        receipt["redaction_status"]["no_secret_value"] = False
        declared = {"lifecycle_status": "enabled_assigned",
                    "provider_namespace": "opencode-go"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        assert result["verdict"] == "G_L3R_STOP_SECRET_RISK"

    def test_secret_in_endpoint_ref_stops(self):
        """If endpoint_ref contains a secret-like pattern → STOP_SECRET_RISK."""
        receipt = _good_receipt()
        receipt["endpoint_ref_observed"] = "sk-abcdefghij1234567890"
        declared = {"lifecycle_status": "enabled_assigned",
                    "provider_namespace": "opencode-go"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        # Either schema validation rejects it OR evaluation catches leak
        assert result["verdict"] in ("G_L3R_STOP_SECRET_RISK", "G_L3R_BLOCKED")

    def test_url_in_endpoint_ref_blocks(self):
        """If endpoint_ref is a URL → schema rejection."""
        receipt = _good_receipt()
        receipt["endpoint_ref_observed"] = "https://api.example.com/v1"
        result = l3rp.validate_live_receipt_schema(receipt)
        assert result["valid"] is False
        assert any("endpoint_ref" in e for e in result["errors"])


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Schema / anchor mismatch → STOP_AND_REANCHOR
# ═══════════════════════════════════════════════════════════════════════════════


class TestSchemaAnchorMismatch:
    """Schema or anchor mismatch → G_L3R_STOP_AND_REANCHOR."""

    def test_schema_version_mismatch_stops(self):
        receipt = _good_receipt()
        receipt["schema_version"] = "99.0"  # wrong
        result = l3rp.validate_live_receipt_schema(receipt)
        assert result["valid"] is False
        assert any("schema_version" in e for e in result["errors"])

    def test_node_mismatch_blocks(self):
        receipt = _good_receipt()
        receipt["node"] = "invalid-node"
        result = l3rp.validate_live_receipt_schema(receipt)
        assert result["valid"] is False
        assert any("node" in e for e in result["errors"])

    def test_collector_mode_mismatch_blocks(self):
        receipt = _good_receipt()
        receipt["collector_mode"] = "unauthorized-mode"
        result = l3rp.validate_live_receipt_schema(receipt)
        assert result["valid"] is False

    def test_collection_status_mismatch_blocks(self):
        receipt = _good_receipt()
        receipt["collection_status"] = "invalid-status"
        result = l3rp.validate_live_receipt_schema(receipt)
        assert result["valid"] is False

    def test_empty_anchor_stops(self):
        """Empty receipt_anchor → STOP_AND_REANCHOR via evaluation."""
        receipt = _good_receipt()
        receipt["receipt_anchor"] = ""
        declared = {"lifecycle_status": "enabled_assigned",
                    "provider_namespace": "opencode-go"}
        result = l3rp.evaluate_live_receipt(receipt, declared)
        assert result["verdict"] == "G_L3R_STOP_AND_REANCHOR"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. No automatic runtime field promotion
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoRuntimeFieldPromotion:
    """G-L3R must NOT promote runtime_visible/env_loaded/etc. fields."""

    def test_forbidden_fields_documented(self):
        plan = l3rp.build_plan()
        rf = plan.get("runtime_fields_forbidden_to_write", [])
        assert "runtime_visible" in rf
        assert "env_loaded" in rf
        assert "model_call_verified" in rf
        assert "operator_approved" in rf

    def test_gate_rejects_promote_model_call_verified(self):
        gate = {
            "operator_approval_id": "op-test",
            "node": "21bao",
            "collector_mode": "real_read",
            "promote_model_call_verified": True,
        }
        result = l3rp.validate_operator_gate(gate)
        assert result["valid"] is False
        assert any("model_call_verified" in e for e in result["errors"])

    def test_gate_rejects_promote_operator_approved(self):
        gate = {
            "operator_approval_id": "op-test",
            "node": "21bao",
            "collector_mode": "real_read",
            "promote_operator_approved": True,
        }
        result = l3rp.validate_operator_gate(gate)
        assert result["valid"] is False
        assert any("operator_approved" in e for e in result["errors"])

    def test_gate_rejects_writeback(self):
        gate = {
            "operator_approval_id": "op-test",
            "node": "21bao",
            "collector_mode": "real_read",
            "write_back_to_capability_yaml": True,
        }
        result = l3rp.validate_operator_gate(gate)
        assert result["valid"] is False
        assert any("write-back" in e for e in result["errors"])

    def test_valid_gate_passes(self):
        gate = {
            "operator_approval_id": "op-test-001",
            "node": "21bao",
            "collector_mode": "real_read",
        }
        result = l3rp.validate_operator_gate(gate)
        assert result["valid"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 11. DeepSeek V4 Pro not special-cased
# ═══════════════════════════════════════════════════════════════════════════════


class TestV4ProNotSpecial:
    """DeepSeek V4 Pro treated identically to other active models."""

    def test_v4_pro_pass_same_as_other_active(self):
        v4_receipt = _good_receipt(model_id="opencode-go-deepseek-v4-pro")
        other_receipt = _good_receipt(model_id="opencode-go-glm-5-1")
        declared = {"lifecycle_status": "enabled_assigned",
                    "provider_namespace": "opencode-go"}
        v4_result = l3rp.evaluate_live_receipt(v4_receipt, declared)
        other_result = l3rp.evaluate_live_receipt(other_receipt, declared)
        assert v4_result["verdict"] == other_result["verdict"]

    def test_v4_pro_missing_runtime_blocks_same(self):
        v4_receipt = _good_receipt(model_id="opencode-go-deepseek-v4-pro",
                                   runtime_visible=False)
        other_receipt = _good_receipt(model_id="opencode-go-glm-5-1",
                                      runtime_visible=False)
        declared = {"lifecycle_status": "enabled_assigned",
                    "provider_namespace": "opencode-go"}
        v4_result = l3rp.evaluate_live_receipt(v4_receipt, declared)
        other_result = l3rp.evaluate_live_receipt(other_receipt, declared)
        assert v4_result["verdict"] == other_result["verdict"]
        assert v4_result["verdict"] == "G_L3R_BLOCKED"

    def test_v4_pro_not_in_special_handling(self):
        """Module source must not special-case V4 Pro."""
        with open(SCRIPT) as f:
            source = f.read()
        # Check for special-case comments
        bad_phrases = [
            "deepseek_v4_pro_special",
            "v4_pro_exempt",
            "v4_pro_skip",
        ]
        for phrase in bad_phrases:
            assert phrase not in source.lower(), (
                f"Found special-case phrase: {phrase}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 12. No forbidden operations
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoForbiddenOps:
    """Module must not contain SSH, subprocess, os.environ, model calls, writes."""

    FORBIDDEN_MODULES = {
        "subprocess", "paramiko", "fabric", "pexpect", "socket",
        "urllib", "urllib.request", "requests", "http",
    }

    def test_no_subprocess_import(self):
        with open(SCRIPT) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    top = alias.name.split('.')[0]
                    if top in self.FORBIDDEN_MODULES:
                        pytest.fail(f"Forbidden import: {alias.name}")

    def test_no_os_environ_or_getenv(self):
        with open(SCRIPT) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr in ("environ", "getenv", "system", "popen",
                                 "exec", "spawn"):
                    pytest.fail(f"Forbidden attr: .{node.attr}")

    def test_no_ssh_scp_in_source(self):
        with open(SCRIPT) as f:
            source = f.read()
        forbidden = ['"ssh ', "'ssh ", '"scp ', "'scp ", "paramiko"]
        for pat in forbidden:
            assert pat not in source, f"Forbidden pattern: {pat}"

    def test_no_model_call_imports(self):
        with open(SCRIPT) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if "opencode_model" in alias.name or "vibe_model" in alias.name:
                        pytest.fail(f"Model-related import: {alias.name}")

    def test_no_write_to_yaml_files(self):
        """Module must not write model_pool.yaml or node_model_capability.yaml."""
        with open(SCRIPT) as f:
            source = f.read()
        forbidden = ["model_pool.yaml", "node_model_capability.yaml"]
        for target in forbidden:
            for line in source.split("\n"):
                if target in line and ("open(" in line and '"w"' in line):
                    pytest.fail(f"Write to {target}: {line.strip()[:80]}")

    def test_no_yaml_dump_json_dump_to_yaml_files(self):
        """No yaml.dump / json.dump to forbidden files."""
        with open(SCRIPT) as f:
            source = f.read()
        for target in ["model_pool.yaml", "node_model_capability.yaml"]:
            for line in source.split("\n"):
                if "yaml.dump" in line and target in line:
                    pytest.fail(f"yaml.dump to {target}: {line.strip()}")
                if "json.dump" in line and target in line:
                    pytest.fail(f"json.dump to {target}: {line.strip()}")

    def test_no_path_write_text_to_yaml_files(self):
        """No Path.write_text to forbidden files."""
        with open(SCRIPT) as f:
            source = f.read()
        for target in ["model_pool.yaml", "node_model_capability.yaml"]:
            for line in source.split("\n"):
                if "write_text" in line and target in line:
                    pytest.fail(f"write_text to {target}: {line.strip()}")


# ═══════════════════════════════════════════════════════════════════════════════
# 13. Required fields completeness
# ═══════════════════════════════════════════════════════════════════════════════


class TestRequiredFields:
    """Live receipt schema defines all required fields per operator spec."""

    REQUIRED_FIELDS_PER_SPEC = {
        "node", "model_id", "provider_namespace", "runtime_provider",
        "alias", "runtime_visible_observed", "env_loaded_observed",
        "credential_status_observed", "endpoint_ref_observed",
        "redaction_status", "forbidden_operation_flags", "collector_mode",
        "operator_approval_id", "receipt_anchor", "source_node",
        "collection_status",
    }

    def test_required_fields_documented(self):
        actual = l3rp.LIVE_RECEIPT_REQUIRED_FIELDS
        missing = self.REQUIRED_FIELDS_PER_SPEC - actual
        assert not missing, f"Missing required fields: {missing}"

    def test_valid_nodes_documented(self):
        assert l3rp.VALID_NODES == frozenset({"21bao", "5bao", "9bao"})

    def test_collector_modes_documented(self):
        expected = {"dry_run", "real_read", "ssh_canary", "sanctioned_ssh_canary_5bao"}
        assert l3rp.VALID_COLLECTOR_MODES == expected

    def test_collection_status_documented(self):
        expected = {"not_collected", "collected", "skipped", "error", "blocked"}
        assert l3rp.VALID_COLLECTION_STATUS == expected


# ═══════════════════════════════════════════════════════════════════════════════
# 14. Cost strategy
# ═══════════════════════════════════════════════════════════════════════════════


class TestCostStrategy:
    """Cost strategy documents low-cost default models."""

    def test_cost_strategy_exists(self):
        cost = l3rp.get_cost_strategy()
        assert "default_models_for_g_l4" in cost

    def test_default_includes_low_cost(self):
        cost = l3rp.get_cost_strategy()
        defaults = cost["default_models_for_g_l4"]
        assert any("deepseek" in m.lower() or "flash" in m.lower() for m in defaults), (
            f"Default should include low-cost: {defaults}"
        )
        assert any("mimo" in m.lower() for m in defaults), (
            f"Default should include mimo: {defaults}"
        )

    def test_no_call_now_status(self):
        cost = l3rp.get_cost_strategy()
        assert cost["current_phase"] == "G-L3R-PLAN (no model calls)"

    def test_expensive_models_requiring_extra_authorization(self):
        cost = l3rp.get_cost_strategy()
        expensive = cost.get("expensive_models_requiring_extra_authorization", [])
        # V4 Pro must be in the expensive list (treated no differently than others
        # in G-L3R logic, but cost-strategy-wise it's expensive)
        assert "opencode-go-deepseek-v4-pro" in expensive

    def test_v4_pro_handling_in_cost_strategy(self):
        cost = l3rp.get_cost_strategy()
        assert "deepseek_v4_pro_handling" in cost
        assert "identical" in cost["deepseek_v4_pro_handling"].lower()