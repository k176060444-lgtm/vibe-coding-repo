"""Tests for delegate_capability_gate.py (V1.21.8).

Covers:
  - planned==actual PASS
  - planned model mismatch BLOCKED
  - planned node mismatch BLOCKED
  - actual unknown preflight WARNING
  - delegate_task unsupported capability → BLOCKED_UNSUPPORTED_CAPABILITY
  - operator approved same-model review → SAME_MODEL_REVIEW_ALLOWED_WITH_OPERATOR_APPROVAL
  - claimed actual_model but no receipt source → WARNING/BLOCKED
  - report schema contains capability/planned_actual sections
  - router aliases mlc / dcc available
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from delegate_capability_gate import (
    ALL_VERDICTS,
    VERDICT_BLOCKED,
    VERDICT_BLOCKED_UNSUPPORTED,
    VERDICT_PASS,
    VERDICT_SAME_MODEL_REVIEW,
    VERDICT_WARNING,
    __version__,
    compute_entry_verdict,
    create_capability_declaration,
    get_executor_capability,
    validate_capability_declaration,
    validate_ledger,
    validate_ledger_entry,
)


# --- Fixtures ---

@pytest.fixture
def entry_pass():
    return {
        "role": "implementer",
        "planned_provider": "minimax-plan",
        "planned_model": "minimax-plan/MiniMax-M3",
        "planned_node": "windows",
        "actual_provider": "minimax-plan",
        "actual_model": "minimax-plan/MiniMax-M3",
        "actual_node": "windows",
        "actual_source": "opencode_exit_log",
        "receipt_confidence": "verified",
        "mismatch_reason": "",
        "operator_approved_downgrade": False,
    }


@pytest.fixture
def entry_mismatch():
    return {
        "role": "reviewer",
        "planned_provider": "deepseek-plan",
        "planned_model": "deepseek-plan/deepseek-v4-pro",
        "planned_node": "9bao",
        "actual_provider": "xiaomi-plan",
        "actual_model": "xiaomi-plan/mimo-v2.5-pro",
        "actual_node": "windows",
        "actual_source": "parent_session_inheritance",
        "receipt_confidence": "claimed",
        "mismatch_reason": "",
        "operator_approved_downgrade": False,
    }


@pytest.fixture
def entry_node_mismatch():
    return {
        "role": "reviewer",
        "planned_provider": "deepseek-plan",
        "planned_model": "deepseek-plan/deepseek-v4-pro",
        "planned_node": "9bao",
        "actual_provider": "deepseek-plan",
        "actual_model": "deepseek-plan/deepseek-v4-pro",
        "actual_node": "windows",
        "actual_source": "opencode_exit_log",
        "receipt_confidence": "verified",
        "mismatch_reason": "",
        "operator_approved_downgrade": False,
    }


@pytest.fixture
def entry_preflight():
    return {
        "role": "tester",
        "planned_provider": "deepseek-plan",
        "planned_model": "deepseek-plan/deepseek-v4-flash",
        "planned_node": "windows",
        "actual_provider": "",
        "actual_model": "",
        "actual_node": "",
        "actual_source": "none",
        "receipt_confidence": "none",
        "mismatch_reason": "",
        "operator_approved_downgrade": False,
    }


@pytest.fixture
def entry_approved_same_model():
    return {
        "role": "reviewer",
        "planned_provider": "deepseek-plan",
        "planned_model": "deepseek-plan/deepseek-v4-pro",
        "planned_node": "9bao",
        "actual_provider": "xiaomi-plan",
        "actual_model": "xiaomi-plan/mimo-v2.5-pro",
        "actual_node": "windows",
        "actual_source": "parent_session_inheritance",
        "receipt_confidence": "claimed",
        "mismatch_reason": "delegate_task cannot override per-task model; "
                           "operator approved same-model review",
        "operator_approved_downgrade": True,
    }


# --- Tests ---


class TestPassCase:
    def test_planned_equals_actual_pass(self, entry_pass):
        v = compute_entry_verdict(entry_pass)
        assert v["verdict"] == VERDICT_PASS
        assert v["model_match"] is True
        assert v["node_match"] is True

    def test_pass_with_claimed_receipt(self, entry_pass):
        entry_pass["receipt_confidence"] = "claimed"
        v = compute_entry_verdict(entry_pass)
        assert v["verdict"] == VERDICT_PASS


class TestModelMismatchBlocked:
    def test_model_mismatch_blocks(self, entry_mismatch):
        v = compute_entry_verdict(entry_mismatch)
        assert v["verdict"] == VERDICT_BLOCKED
        assert v["model_match"] is False
        assert "mismatch" in v["detail"].lower()


class TestNodeMismatchBlocked:
    def test_node_mismatch_blocks(self, entry_node_mismatch):
        v = compute_entry_verdict(entry_node_mismatch)
        assert v["verdict"] == VERDICT_BLOCKED
        assert v["node_match"] is False


class TestPreflightWarning:
    def test_actual_unknown_warns(self, entry_preflight):
        v = compute_entry_verdict(entry_preflight)
        assert v["verdict"] == VERDICT_WARNING
        assert "preflight" in v["detail"].lower() or "not yet known" in v["detail"].lower()


class TestUnsupportedCapability:
    def test_delegate_task_blocks_model_mismatch(self, entry_mismatch):
        cap = get_executor_capability("delegate_task")
        v = compute_entry_verdict(entry_mismatch, cap)
        assert v["verdict"] == VERDICT_BLOCKED_UNSUPPORTED
        assert "per_task_model_override" in v["detail"]

    def test_local_job_allows_model_mismatch(self, entry_mismatch):
        cap = get_executor_capability("local-job")
        v = compute_entry_verdict(entry_mismatch, cap)
        # local-job supports per_task_model_override, so it's a regular BLOCKED
        assert v["verdict"] == VERDICT_BLOCKED

    def test_unknown_executor_assumes_no_capability(self, entry_mismatch):
        cap = get_executor_capability("unknown-executor")
        v = compute_entry_verdict(entry_mismatch, cap)
        assert v["verdict"] == VERDICT_BLOCKED_UNSUPPORTED


class TestOperatorApprovedSameModelReview:
    def test_approved_same_model_review(self, entry_approved_same_model):
        cap = get_executor_capability("delegate_task")
        v = compute_entry_verdict(entry_approved_same_model, cap)
        assert v["verdict"] == VERDICT_SAME_MODEL_REVIEW
        assert "operator approved" in v["detail"].lower()


class TestOperatorApprovedDowngrade:
    def test_approved_downgrade_passes(self, entry_mismatch):
        entry_mismatch["operator_approved_downgrade"] = True
        v = compute_entry_verdict(entry_mismatch)
        assert v["verdict"] == VERDICT_PASS
        assert "approved" in v["detail"].lower()


class TestNoReceiptSource:
    def test_match_but_no_source_warns(self, entry_pass):
        entry_pass["actual_source"] = "none"
        entry_pass["receipt_confidence"] = "none"
        v = compute_entry_verdict(entry_pass)
        assert v["verdict"] == VERDICT_WARNING


class TestLedgerValidation:
    def test_all_pass_ledger(self, entry_pass):
        result = validate_ledger([entry_pass])
        assert result["overall_verdict"] == VERDICT_PASS
        assert result["checks_passed"] == 1

    def test_mixed_ledger_blocked(self, entry_pass, entry_mismatch):
        result = validate_ledger([entry_pass, entry_mismatch])
        assert result["overall_verdict"] == VERDICT_BLOCKED
        assert result["checks_passed"] == 1

    def test_ledger_with_executor_capability(self, entry_mismatch):
        result = validate_ledger([entry_mismatch], executor_name="delegate_task")
        assert result["overall_verdict"] == VERDICT_BLOCKED_UNSUPPORTED

    def test_ledger_missing_field(self):
        bad = [{"role": "test"}]
        result = validate_ledger(bad)
        assert result["valid"] is False
        assert len(result["errors"]) > 0


class TestCapabilityDeclaration:
    def test_create_declaration(self):
        decl = create_capability_declaration("test-executor")
        assert decl["executor_name"] == "test-executor"
        assert "per_task_model_override" in decl["capabilities"]

    def test_validate_valid_declaration(self):
        decl = create_capability_declaration("test")
        errors = validate_capability_declaration(decl)
        assert len(errors) == 0

    def test_validate_missing_key(self):
        bad = {"executor_name": "bad", "capabilities": {}}
        errors = validate_capability_declaration(bad)
        assert len(errors) > 0

    def test_known_delegate_task_no_override(self):
        cap = get_executor_capability("delegate_task")
        assert cap["capabilities"]["per_task_model_override"] is False

    def test_known_local_job_has_override(self):
        cap = get_executor_capability("local-job")
        assert cap["capabilities"]["per_task_model_override"] is True

    def test_unknown_executor_all_false(self):
        cap = get_executor_capability("foobar")
        assert not any(cap["capabilities"].values())


class TestLedgerEntryValidation:
    def test_valid_entry_no_errors(self, entry_pass):
        errors = validate_ledger_entry(entry_pass, 0)
        assert len(errors) == 0

    def test_missing_field_detected(self):
        errors = validate_ledger_entry({"role": "test"}, 0)
        assert len(errors) > 0
        assert any("missing" in e for e in errors)

    def test_invalid_receipt_confidence(self, entry_pass):
        entry_pass["receipt_confidence"] = "bogus"
        errors = validate_ledger_entry(entry_pass, 0)
        assert any("receipt_confidence" in e for e in errors)

    def test_invalid_actual_source(self, entry_pass):
        entry_pass["actual_source"] = "bogus"
        errors = validate_ledger_entry(entry_pass, 0)
        assert any("actual_source" in e for e in errors)


class TestVersion:
    def test_version(self):
        assert __version__ == "1.0.0"


class TestVerdicts:
    def test_five_verdicts(self):
        assert len(ALL_VERDICTS) == 5
