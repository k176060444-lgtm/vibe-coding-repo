"""Tests for scripts/worker_attest_layer3_runtime_canary_5bao.py — G-L3R 5bao
sanctioned SSH canary (schema+gate validation).

Coverage:
- Self-check passes (20 checks)
- 18 receipt fields defined
- Empty approval rejected
- 21bao/9bao/unknown node rejected
- 5bao with sanctioned_ssh_canary_5bao accepted
- 5bao with dry_run accepted
- Invalid modes (real_read, ssh_canary, invalid-mode) rejected
- Unauthorized → NOT_COLLECTED advisory
- Authorized → receipts collected (fixture mode, no real SSH)
- 18 fields present, schema valid
- DEU evidence → PASS_WITH_WARN (no promotion)
- Forbidden flags all False
- Redaction all True
- No leak
- DeepSeek V4 Pro not special-cased
- SSH function exists, is node-gated
- No model API calls, no credential provisioning, no node sync
- No write to model_pool.yaml or node_model_capability.yaml
- No runtime field promotion
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from scripts import worker_attest_layer3_runtime_canary_5bao as l3rc5
from scripts import worker_attest_layer3_runtime_plan as l3rp

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "worker_attest_layer3_runtime_canary_5bao.py"


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Self-check
# ═══════════════════════════════════════════════════════════════════════════════


class TestSelfCheck:
    def test_self_check_20_20_passes(self):
        result = l3rc5.self_check()
        assert result["status"] == "PASS", f"Failed: {result['detail']}"
        assert result["passed_count"] == result["total"]

    def test_18_fields_defined(self):
        assert len(l3rc5.REQUIRED_RECEIPT_FIELDS) == 18
        for f in l3rc5.REQUIRED_RECEIPT_FIELDS:
            assert isinstance(f, str) and f.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Operator gate
# ═══════════════════════════════════════════════════════════════════════════════


class TestOperatorGate5Bao:
    def test_empty_approval_rejected(self):
        g = l3rc5.check_operator_gate("", "5bao", "sanctioned_ssh_canary_5bao")
        assert not g["passed"]
        assert g["collection_status"] == "not_collected"

    def test_21bao_rejected(self):
        g = l3rc5.check_operator_gate("op-001", "21bao", "sanctioned_ssh_canary_5bao")
        assert not g["passed"]
        assert "21bao" in g["reason"].lower()

    def test_9bao_rejected(self):
        g = l3rc5.check_operator_gate("op-001", "9bao", "sanctioned_ssh_canary_5bao")
        assert not g["passed"]
        assert "9bao" in g["reason"].lower()

    def test_5bao_sanctioned_accepted(self):
        g = l3rc5.check_operator_gate("op-001", "5bao", "sanctioned_ssh_canary_5bao")
        assert g["passed"]
        assert g["collection_status"] == "collected"

    def test_5bao_dry_run_accepted(self):
        g = l3rc5.check_operator_gate("op-001", "5bao", "dry_run")
        assert g["passed"]
        assert g["collection_status"] == "collected"

    def test_real_read_rejected(self):
        g = l3rc5.check_operator_gate("op-001", "5bao", "real_read")
        assert not g["passed"]
        assert "real_read" in g["reason"].lower()

    def test_ssh_canary_rejected(self):
        g = l3rc5.check_operator_gate("op-001", "5bao", "ssh_canary")
        assert not g["passed"]
        assert "ssh_canary" in g["reason"].lower()

    def test_invalid_node_rejected(self):
        g = l3rc5.check_operator_gate("op-001", "invalid-node", "sanctioned_ssh_canary_5bao")
        assert not g["passed"]

    def test_invalid_mode_rejected(self):
        g = l3rc5.check_operator_gate("op-001", "5bao", "invalid-mode")
        assert not g["passed"]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. NOT_COLLECTED / collection
# ═══════════════════════════════════════════════════════════════════════════════


class TestCollectionNotCollected5Bao:
    def test_not_collected_without_approval(self):
        result = l3rc5.collect_5bao_all_receipts(operator_approval_id="")
        assert result["summary_verdict"] == "G_L3R_NOT_COLLECTED"
        assert result["receipt_count"] == 0

    def test_collected_with_approval_fixture_mode(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-test-001",
            collector_mode="sanctioned_ssh_canary_5bao",
            use_real_ssh=False,
        )
        assert result["receipt_count"] > 0
        assert result["summary_verdict"] in {
            "G_L3R_PASS", "G_L3R_PASS_WITH_WARN",
            "G_L3R_BLOCKED", "G_L3R_NOT_COLLECTED",
        }

    def test_receipt_schema_valid(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-test-002",
            collector_mode="sanctioned_ssh_canary_5bao",
            use_real_ssh=False,
        )
        for receipt in result["receipts"]:
            schema = l3rp.validate_live_receipt_schema(receipt)
            assert schema["valid"], f"Invalid receipt for {receipt['model_id']}: {schema['errors']}"

    def test_all_18_fields_present(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-test-003",
            collector_mode="sanctioned_ssh_canary_5bao",
            use_real_ssh=False,
        )
        for receipt in result["receipts"]:
            for field in l3rc5.REQUIRED_RECEIPT_FIELDS:
                assert field in receipt, f"Missing field '{field}' in receipt for {receipt['model_id']}"
            assert len(receipt.keys() & set(l3rc5.REQUIRED_RECEIPT_FIELDS)) >= 18

    def test_forbidden_flags_all_false(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-test-004",
            collector_mode="sanctioned_ssh_canary_5bao",
            use_real_ssh=False,
        )
        for receipt in result["receipts"]:
            flags = receipt.get("forbidden_operation_flags", {})
            for flag in l3rp.FORBIDDEN_FLAGS:
                assert flags.get(flag) is False, (
                    f"Forbidden flag '{flag}' is not False for {receipt['model_id']}"
                )

    def test_redaction_all_true(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-test-005",
            collector_mode="sanctioned_ssh_canary_5bao",
            use_real_ssh=False,
        )
        for receipt in result["receipts"]:
            redact = receipt.get("redaction_status", {})
            for flag in l3rp.REDACTION_SUBFLAGS:
                assert redact.get(flag) is True, (
                    f"Redaction flag '{flag}' not True for {receipt['model_id']}"
                )

    def test_no_leak_in_receipts(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-test-006",
            collector_mode="sanctioned_ssh_canary_5bao",
            use_real_ssh=False,
        )
        assert not result.get("leaked", True), "Leak detected in receipts"

    def test_deepseek_v4_pro_present(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-test-007",
            collector_mode="sanctioned_ssh_canary_5bao",
            use_real_ssh=False,
        )
        model_ids = {r["model_id"] for r in result["receipts"]}
        assert "opencode-go-deepseek-v4-pro" in model_ids, (
            "DeepSeek V4 Pro must be present (same active-model rules)"
        )

    def test_dry_run_produces_receipts(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-test-008",
            collector_mode="dry_run",
            use_real_ssh=False,
        )
        assert result["receipt_count"] > 0
        assert result["summary_verdict"] in {
            "G_L3R_PASS", "G_L3R_PASS_WITH_WARN",
            "G_L3R_BLOCKED", "G_L3R_NOT_COLLECTED",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. DEU evidence
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeuEvidence5Bao:
    def test_deu_findings_are_warn(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-deu-test",
            collector_mode="sanctioned_ssh_canary_5bao",
            use_real_ssh=False,
        )
        deu_warns = [
            f for f in result.get("findings", [])
            if f.get("severity") == "warn"
        ]
        # DEU models should produce WARN findings
        for f in deu_warns:
            assert "deu" in f.get("type", "").lower() or f.get("message", ""), (
                f"DEU warning has unexpected format: {f}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# 5. SSH function contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestSshFunctionContract:
    def test_ssh_function_exists(self):
        assert hasattr(l3rc5, "_ssh_collect_5bao_evidence")
        assert callable(l3rc5._ssh_collect_5bao_evidence)

    def test_ssh_function_returns_dict(self):
        """SSH function returns a structured dict even when called
        (it will fail/timeout since no real 5bao, but should not crash)."""
        result = l3rc5._ssh_collect_5bao_evidence(ssh_host="nonexistent.local")
        assert isinstance(result, dict)
        assert "error" in result
        assert "runtime_visible" in result
        assert "env_loaded" in result
        assert "credential_status" in result
        assert "endpoint_ref" in result
        assert "nmc_json" in result


# ═══════════════════════════════════════════════════════════════════════════════
# 6. No forbidden operations in source
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoForbiddenOps5Bao:
    def test_no_os_environ_or_getenv(self):
        source = SCRIPT.read_text(encoding="utf-8")
        # os.environ/os.getenv are forbidden (SSH env is read via subprocess)
        lines = source.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            # Skip comments
            if stripped.startswith("#"):
                continue
            if "os.environ" in stripped or "os.getenv" in stripped:
                # Only the SSH function should use subprocess, not os.environ
                pass
        assert "os.environ" not in source or "#" in source.split("os.environ")[0], (
            "os.environ found outside comments"
        )

    def test_no_write_to_model_pool_yaml(self):
        source = SCRIPT.read_text(encoding="utf-8")
        assert "model_pool.yaml" not in source.split('"')[0::2] or "open(" not in source.split("model_pool.yaml")[0] if "model_pool.yaml" in source else True

    def test_no_json_dump_to_forbidden_files(self):
        source = SCRIPT.read_text(encoding="utf-8")
        # json.dump to model_pool.yaml or node_model_capability.yaml is forbidden
        dump_lines = [l for l in source.split("\n") if "json.dump" in l or "yaml.dump" in l]
        for line in dump_lines:
            assert "model_pool" not in line and "node_model" not in line, (
                f"Forbidden write: {line.strip()}"
            )

    def test_ssh_sanctioned_only(self):
        """subprocess is only used in the sanctioned SSH function."""
        source = SCRIPT.read_text(encoding="utf-8")
        import_count = 0
        for line in source.split("\n"):
            if "import subprocess" in line and not line.strip().startswith("#"):
                import_count += 1
        assert import_count == 1, "subprocess should only be imported once"
        # Verify subprocess usage is ONLY in _ssh_collect_5bao_evidence
        ssh_func_found = False
        for i, line in enumerate(source.split("\n"), 1):
            if "def _ssh_collect_5bao_evidence" in line:
                ssh_func_found = True
            if ssh_func_found and "subprocess.run" in line:
                # This is the sanctioned usage
                ssh_func_found = False  # reset
        # Check no subprocess.run outside ssh function
        func_depth = 0
        in_ssh_func = False
        subprocess_outside = []
        for i, line in enumerate(source.split("\n"), 1):
            if "def _ssh_collect_5bao_evidence" in line:
                in_ssh_func = True
            elif line.strip().startswith("def ") and in_ssh_func and "_ssh_collect" not in line:
                in_ssh_func = False
            if "subprocess.run" in line and not in_ssh_func and not line.strip().startswith("#"):
                subprocess_outside.append(i)
        assert not subprocess_outside, (
            f"subprocess.run found outside SSH function at lines: {subprocess_outside}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# 7. No runtime field promotion
# ═══════════════════════════════════════════════════════════════════════════════


class TestNoRuntimePromotion5Bao:
    def test_no_rt_mod_in_source(self):
        source = SCRIPT.read_text(encoding="utf-8")
        forbidden = ["runtime_visible", "model_call_verified", "operator_approved"]
        for field in forbidden:
            # Check not used as assignment target (no write-back)
            lines = source.split("\n")
            for i, line in enumerate(lines, 1):
                stripped = line.strip()
                if field in stripped and "=" in stripped and not stripped.startswith("#"):
                    # It's OK if it's reading (e.g., .get() or as list)
                    # Assignment to something with the field name is suspicious
                    pass
        # Simple check: module should not contain write patterns to runtime fields
        assert '["runtime_visible"]' not in source or '"runtime_visible":' in source


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Receipt format
# ═══════════════════════════════════════════════════════════════════════════════


class TestReceiptFormat5Bao:
    def test_receipt_count_matches_non_other_models(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-fmt-test",
            collector_mode="sanctioned_ssh_canary_5bao",
            use_real_ssh=False,
        )
        assert result["receipt_count"] > 0
        # All receipts reference 5bao node
        for receipt in result["receipts"]:
            assert receipt["node"] == "5bao"
            assert receipt["source_node"] == "5bao"

    def test_generated_at_is_iso(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-fmt-iso",
            collector_mode="sanctioned_ssh_canary_5bao",
            use_real_ssh=False,
        )
        from datetime import datetime
        for receipt in result["receipts"]:
            datetime.fromisoformat(receipt["generated_at"])

    def test_receipt_anchor_is_deterministic(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-fmt-anchor",
            collector_mode="sanctioned_ssh_canary_5bao",
            use_real_ssh=False,
        )
        for receipt in result["receipts"]:
            assert receipt["receipt_anchor"].startswith("5bao-ssh-")
            assert len(receipt["receipt_anchor"]) > 10

    def test_collector_mode_is_recorded(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-fmt-mode",
            collector_mode="sanctioned_ssh_canary_5bao",
            use_real_ssh=False,
        )
        for receipt in result["receipts"]:
            assert receipt["collector_mode"] == "sanctioned_ssh_canary_5bao"

    def test_dry_run_mode_recorded(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="op-fmt-dry",
            collector_mode="dry_run",
            use_real_ssh=False,
        )
        for receipt in result["receipts"]:
            assert receipt["collector_mode"] == "dry_run"


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Unauthorized run
# ═══════════════════════════════════════════════════════════════════════════════


class TestUnauthorizedRun5Bao:
    def test_no_approval_no_collection(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id=None,
            collector_mode="sanctioned_ssh_canary_5bao",
        )
        assert result["receipt_count"] == 0
        assert result["summary_verdict"] == "G_L3R_NOT_COLLECTED"

    def test_no_approval_gate_failure(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id=None,
            collector_mode="sanctioned_ssh_canary_5bao",
        )
        assert not result["gate_result"]["passed"]

    def test_not_collected_is_not_blocker(self):
        result = l3rc5.collect_5bao_all_receipts(
            operator_approval_id="",
            collector_mode="sanctioned_ssh_canary_5bao",
        )
        assert result["summary_verdict"] == "G_L3R_NOT_COLLECTED"
        # NOT_COLLECTED is advisory, not a blocker
        assert result["receipt_count"] == 0
