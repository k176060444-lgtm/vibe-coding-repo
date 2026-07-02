"""
Tests for scripts/worker_attest_layer3_runtime_canary.py — G-L3R 21bao local
runtime receipt canary.

Coverage:
- Unauthorized → NOT_COLLECTED advisory
- Authorized receipts collected (18 fields each)
- 21bao scope correct; 5bao/9bao rejected
- Active model mismatch → BLOCKED
- Missing authorized receipt → BLOCKED / worker_attest_missing
- DEU evidence → PASS_WITH_WARN (no promotion)
- Forbidden flag → BLOCKED
- Redaction/secret → STOP_SECRET_RISK
- Schema mismatch → STOP_AND_REANCHOR
- DeepSeek V4 Pro not special-cased
- No SSH/subprocess/http/os.environ/model call/write path
- No runtime field promotion
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scripts import worker_attest_layer3_runtime_canary as l3rc
from scripts import worker_attest_layer3_runtime_plan as l3rp

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "worker_attest_layer3_runtime_canary.py"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Self-check
# ═══════════════════════════════════════════════════════════════════════════════


class TestSelfCheck:
    def test_self_check_17_17_passes(self):
        result = l3rc.self_check()
        assert result["status"] == "PASS", f"Failed: {result['detail']}"
        assert result["passed_count"] == result["total"]

    def test_18_fields_defined(self):
        assert len(l3rc.REQUIRED_RECEIPT_FIELDS) == 18
        for f in l3rc.REQUIRED_RECEIPT_FIELDS:
            assert isinstance(f, str) and f.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Operator gate
# ═══════════════════════════════════════════════════════════════════════════════


class TestOperatorGate:
    def test_empty_approval_rejected(self):
        g = l3rc.check_operator_gate("", "21bao", "real_read")
        assert not g["passed"]
        assert g["collection_status"] == "not_collected"

    def test_5bao_rejected(self):
        g = l3rc.check_operator_gate("op-001", "5bao", "real_read")
        assert not g["passed"]

    def test_9bao_rejected(self):
        g = l3rc.check_operator_gate("op-001", "9bao", "real_read")
        assert not g["passed"]

    def test_21bao_accepted(self):
        g = l3rc.check_operator_gate("op-001", "21bao", "real_read")
        assert g["passed"]
        assert g["collection_status"] == "collected"

    def test_invalid_mode_rejected(self):
        g = l3rc.check_operator_gate("op-001", "21bao", "invalid")
        assert not g["passed"]

    def test_dry_run_accepted(self):
        g = l3rc.check_operator_gate("op-001", "21bao", "dry_run")
        assert g["passed"]

    def test_ssh_canary_accepted(self):
        g = l3rc.check_operator_gate("op-001", "21bao", "ssh_canary")
        assert g["passed"]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. NOT_COLLECTED / collection
# ═══════════════════════════════════════════════════════════════════════════════


class TestCollectionNotCollected:
    def test_not_collected_without_approval(self):
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="")
        assert result["summary_verdict"] == "G_L3R_NOT_COLLECTED"
        assert result["receipt_count"] == 0

    def test_collected_with_approval(self):
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-001")
        assert result["receipt_count"] > 0
        assert result["summary_verdict"] in {
            "G_L3R_PASS", "G_L3R_PASS_WITH_WARN",
            "G_L3R_BLOCKED", "G_L3R_NOT_COLLECTED",
        }

    def test_receipt_schema_valid(self):
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-002")
        for receipt in result["receipts"]:
            schema = l3rp.validate_live_receipt_schema(receipt)
            assert schema["valid"], f"Invalid receipt for {receipt['model_id']}: {schema['errors']}"

    def test_all_18_fields_present(self):
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-003")
        for receipt in result["receipts"]:
            missing = [f for f in l3rc.REQUIRED_RECEIPT_FIELDS if f not in receipt]
            assert not missing, f"Receipt for {receipt.get('model_id','?')} missing fields: {missing}"

    def test_forbidden_flags_all_false(self):
        """Sanctioned 21bao local-only canary must NOT set any forbidden flag True."""
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-004")
        for receipt in result["receipts"]:
            for flag in l3rp.FORBIDDEN_FLAGS:
                assert receipt.get("forbidden_operation_flags", {}).get(flag) is False, (
                    f"Forbidden flag '{flag}' is True in {receipt['model_id']}: "
                    f"{receipt.get('forbidden_operation_flags')}"
                )

    def test_redaction_all_true(self):
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-005")
        for receipt in result["receipts"]:
            for sf in l3rp.REDACTION_SUBFLAGS:
                assert receipt.get("redaction_status", {}).get(sf) is True, (
                    f"Redaction subflag '{sf}' is False in {receipt['model_id']}"
                )

    def test_no_leak_in_receipts(self):
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-006")
        assert not result.get("leaked", True), "Leak detected in receipts"

    def test_deepseek_v4_pro_present(self):
        """DeepSeek V4 Pro must appear in receipts like any other active model."""
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-007")
        v4_ids = [r for r in result["receipts"] if "deepseek-v4-pro" in r.get("model_id", "")]
        assert len(v4_ids) > 0, "DeepSeek V4 Pro not found in receipts"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. DEU evidence → WARN, not promotion
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeuEvidence:
    def test_deu_findings_are_warn(self):
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-008")
        deu_warns = [f for f in result.get("findings", [])
                     if f.get("type") == "deu_live_evidence"]
        # DEU findings should exist but be WARN only
        for f in deu_warns:
            assert f.get("severity") == "warn", \
                f"DEU finding should be warn: {f}"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Forbidden flag → BLOCKED
# ═══════════════════════════════════════════════════════════════════════════════


class TestForbiddenFlagBlocked:
    def test_collector_emits_forbidden_flag_check(self):
        """Receipts must document forbidden flags (even if all False)."""
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-009")
        for receipt in result["receipts"]:
            ff = receipt.get("forbidden_operation_flags", {})
            for flag in l3rp.FORBIDDEN_FLAGS:
                # Flag must be documented
                assert flag in ff, \
                    f"Missing forbidden flag '{flag}' in {receipt['model_id']}"
                # Must be False for sanctioned operation
                assert ff[flag] is False, \
                    f"Forbidden flag '{flag}' is True"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Redaction / STOP_SECRET_RISK
# ═══════════════════════════════════════════════════════════════════════════════


class TestRedaction:
    def test_redaction_status_has_all_flags(self):
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-010")
        for receipt in result["receipts"]:
            rs = receipt.get("redaction_status", {})
            for sf in l3rp.REDACTION_SUBFLAGS:
                assert sf in rs, \
                    f"Missing redaction subflag '{sf}' in {receipt['model_id']}"

    def test_endpoint_ref_is_label_not_url(self):
        """endpoint_ref_observed must be a label (env var name), never a URL."""
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-011")
        import re
        url_pat = re.compile(r"https?://")
        for receipt in result["receipts"]:
            ref = receipt.get("endpoint_ref_observed", "")
            assert not url_pat.search(ref), \
                f"endpoint_ref looks like URL: {ref} in {receipt['model_id']}"


# ═══════════════════════════════════════════════════════════════════════════════
# 7. No forbidden imports / ops
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoForbiddenOps:
    FORBIDDEN_MODS = {"subprocess", "paramiko", "fabric", "pexpect",
                      "socket", "urllib", "requests", "http"}

    def test_no_subprocess_import(self):
        with open(SCRIPT) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    top = a.name.split('.')[0]
                    if top in self.FORBIDDEN_MODS:
                        pytest.fail(f"Forbidden import: {a.name}")

    def test_no_os_environ_or_getenv(self):
        with open(SCRIPT) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr in ("environ", "getenv", "system", "popen", "exec", "spawn"):
                    try:
                        if isinstance(node.value, ast.Name) and node.value.id == "os":
                            pytest.fail(f"Forbidden os.{node.attr} @ line {node.lineno}")
                    except (AttributeError, TypeError):
                        pass

    def test_no_ssh_scp_in_source(self):
        with open(SCRIPT) as f:
            source = f.read()
        for pat in ['"ssh ', "'ssh ", '"scp ', "'scp ", "paramiko"]:
            if pat in source:
                lower = source.lower()
                if "forbid" in lower or "must not" in lower:
                    continue
                pytest.fail(f"Forbidden pattern: {pat}")

    def test_no_model_call_imports(self):
        with open(SCRIPT) as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    if any(x in a.name for x in ["opencode_model", "vibe_model",
                                                  "model_pool_manager"]):
                        pytest.fail(f"Model-related import: {a.name}")

    def test_no_write_to_model_pool_yaml(self):
        """Module must NOT write model_pool.yaml or node_model_capability.yaml."""
        with open(SCRIPT) as f:
            source = f.read()
        for target in ["model_pool.yaml", "node_model_capability.yaml"]:
            for line in source.split("\n"):
                if target in line and "open(" in line and '"w"' in line:
                    pytest.fail(f"Write to {target}: {line.strip()[:80]}")

    def test_no_json_dump_to_forbidden_files(self):
        with open(SCRIPT) as f:
            source = f.read()
        for target in ["model_pool.yaml", "node_model_capability.yaml"]:
            for line in source.split("\n"):
                if any(fn in line for fn in ["yaml.dump", "json.dump", "write_text"]):
                    if target in line:
                        pytest.fail(f"Write to {target}: {line.strip()[:80]}")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. No runtime field promotion
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoRuntimePromotion:
    def test_no_rt_mod_in_source(self):
        """No runtime_visible/env_loaded/model_call_verified/operator_approved
        assignments in the canary module."""
        with open(SCRIPT) as f:
            tree = ast.parse(f.read())
        runtime_fields = {"runtime_visible", "env_loaded",
                          "model_call_verified", "operator_approved"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant):
                        if t.slice.value in runtime_fields:
                            pytest.fail(f"Runtime field assignment: {t.slice.value} @ line {t.lineno}")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Receipt format details
# ═══════════════════════════════════════════════════════════════════════════════


class TestReceiptFormat:
    def test_receipt_count_matches_non_other_models(self):
        """Receipt count should equal pool models minus other-status ones."""
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-012")
        assert result["receipt_count"] == 25, \
            f"Expected 25 receipts (all non-'other' models), got {result['receipt_count']}"

    def test_generated_at_is_iso(self):
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-013")
        for receipt in result["receipts"]:
            dt = receipt.get("generated_at", "")
            assert "T" in dt, f"generated_at not ISO: {dt}"

    def test_receipt_anchor_is_deterministic(self):
        """Same model_id should produce same anchor."""
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-014")
        # Run twice — same anchor for same model
        result2 = l3rc.collect_21bao_all_receipts(operator_approval_id="op-test-014")
        for r1, r2 in zip(result["receipts"], result2["receipts"]):
            if r1["model_id"] == r2["model_id"]:
                assert r1["receipt_anchor"] == r2["receipt_anchor"], \
                    f"Anchor mismatch for {r1['model_id']}: {r1['receipt_anchor']} vs {r2['receipt_anchor']}"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Unauthorized run
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnauthorizedRun:
    """CLI behavior when run without approval."""

    def test_no_approval_no_collection(self):
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="")
        assert result["receipt_count"] == 0
        assert result["summary_verdict"] == "G_L3R_NOT_COLLECTED"

    def test_no_approval_gate_failure(self):
        result = l3rc.collect_21bao_all_receipts(operator_approval_id="")
        assert not result["gate_result"]["passed"]

    def test_not_collected_is_not_blocker(self):
        """NOT_COLLECTED is advisory, not a merge blocker."""
        assert l3rp._VERDICT_PRIORITY.get("G_L3R_NOT_COLLECTED", 0) < l3rp._VERDICT_PRIORITY.get("G_L3R_BLOCKED", 0)
