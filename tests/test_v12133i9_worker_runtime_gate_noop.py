"""V1.21.33I9: Tests for Worker Runtime Gate / no-op worker adapter.

Tests the worker_runtime_gate() pure function and NoopWorkerResult
dataclass. All tests are local-only — no SSH, OpenCode, subprocess,
worker shell, or model calls.
"""

import sys
import os
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.vibe_worker_runtime_gate import (
    worker_runtime_gate, NoopWorkerResult, self_check,
)
from scripts.vibe_dispatcher_runtime import DispatchPlan


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _make_valid_plan(**overrides) -> DispatchPlan:
    """Build a valid DispatchPlan for testing."""
    defaults = dict(
        approval_id="appr_i9_test",
        runtime_assignment_id="ra_i9_test",
        execution_ticket_id="tkt_i9_test",
        workorder_id="wo_i9_test",
        base_sha="166c3b316aa8ec129b8f086b69f4e8f18ba34a42",
        target_role="implementer",
        target_node="5bao",
        target_provider="minimax-plan",
        target_model="MiniMax-M3",
        action="local_exec",
        operator_id="kk",
        fallback_count=0,
        real_execution=False,
        planned_at="2026-06-27T12:00:00Z",
        plan_id="plan_i9_test",
    )
    defaults.update(overrides)
    return DispatchPlan(**defaults)


# ──────────────────────────────────────────────
# T1: valid plan → no-op PASS
# ──────────────────────────────────────────────


def test_valid_plan_noop_pass():
    plan = _make_valid_plan()
    result = worker_runtime_gate(plan)
    assert result.allowed is True, f"expected allowed=True, got {result.block_reasons}"
    assert result.status == "noop_passed"
    assert result.real_execution is False
    assert result.worker_invoked is False
    assert result.ssh_invoked is False
    assert result.opencode_invoked is False
    assert result.model_invoked is False
    assert result.approval_id == "appr_i9_test"
    assert result.runtime_assignment_id == "ra_i9_test"
    assert result.execution_ticket_id == "tkt_i9_test"
    assert result.dispatch_plan_id == "plan_i9_test"
    assert result.workorder_id == "wo_i9_test"
    assert result.base_sha == "166c3b316aa8ec129b8f086b69f4e8f18ba34a42"
    assert result.target_role == "implementer"
    assert result.target_node == "5bao"
    assert result.provider == "minimax-plan"
    assert result.model == "MiniMax-M3"
    assert result.action == "local_exec"
    assert result.operator_id == "kk"


# ──────────────────────────────────────────────
# T2: missing plan → BLOCK
# ──────────────────────────────────────────────


def test_missing_plan_block():
    result = worker_runtime_gate(None)
    assert result.allowed is False
    assert any("missing DispatchPlan" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T3: real_execution=true → BLOCK
# ──────────────────────────────────────────────


def test_real_execution_true_block():
    plan = _make_valid_plan(real_execution=True)
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("real_execution" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T4: missing approval_id → BLOCK
# ──────────────────────────────────────────────


def test_missing_approval_id_block():
    plan = _make_valid_plan(approval_id="")
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("approval_id" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T5: missing runtime_assignment_id → BLOCK
# ──────────────────────────────────────────────


def test_missing_runtime_assignment_id_block():
    plan = _make_valid_plan(runtime_assignment_id="")
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("runtime_assignment_id" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T6: missing execution_ticket_id → BLOCK
# ──────────────────────────────────────────────


def test_missing_execution_ticket_id_block():
    plan = _make_valid_plan(execution_ticket_id="")
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("execution_ticket_id" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T7: missing workorder_id → BLOCK
# ──────────────────────────────────────────────


def test_missing_workorder_id_block():
    plan = _make_valid_plan(workorder_id="")
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("workorder_id" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T8: missing base_sha → BLOCK
# ──────────────────────────────────────────────


def test_missing_base_sha_block():
    plan = _make_valid_plan(base_sha="")
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("base_sha" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T9: target role drift → BLOCK
# ──────────────────────────────────────────────


def test_target_role_drift_block():
    plan = _make_valid_plan(target_role="nonexistent")
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("invalid target_role" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T10: target node drift → BLOCK
# ──────────────────────────────────────────────


def test_target_node_drift_block():
    plan = _make_valid_plan(target_node="nonexistent")
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("invalid target_node" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T11: missing provider → BLOCK
# ──────────────────────────────────────────────


def test_missing_provider_block():
    plan = _make_valid_plan(target_provider="")
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("target_provider" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T12: missing model → BLOCK
# ──────────────────────────────────────────────


def test_missing_model_block():
    plan = _make_valid_plan(target_model="")
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("target_model" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T13: missing action → BLOCK
# ──────────────────────────────────────────────


def test_missing_action_block():
    plan = _make_valid_plan(action="")
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("action" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T14: forbidden action → BLOCK
# ──────────────────────────────────────────────


def test_forbidden_action_block():
    plan = _make_valid_plan(action="push")
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("forbidden" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T15: fallback_count>0 → BLOCK
# ──────────────────────────────────────────────


def test_fallback_count_positive_block():
    plan = _make_valid_plan(fallback_count=1)
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("fallback_count" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T16: worker result real_execution=false
# ──────────────────────────────────────────────


def test_worker_result_real_execution_false():
    plan = _make_valid_plan()
    result = worker_runtime_gate(plan)
    assert result.real_execution is False


# ──────────────────────────────────────────────
# T17: all invocation flags false
# ──────────────────────────────────────────────


def test_all_invocation_flags_false():
    plan = _make_valid_plan()
    result = worker_runtime_gate(plan)
    assert result.worker_invoked is False
    assert result.ssh_invoked is False
    assert result.opencode_invoked is False
    assert result.model_invoked is False


# ──────────────────────────────────────────────
# T18: no subprocess/SSH/OpenCode/worker call
# ──────────────────────────────────────────────


def test_no_subprocess_ssh_opencode_worker():
    """Verify worker_runtime_gate is a pure function with no side effects."""
    plan = _make_valid_plan()
    result = worker_runtime_gate(plan)
    assert result.allowed is True
    # Pure function guarantee: no subprocess, no SSH, no OpenCode, no worker
    assert result.worker_invoked is False
    assert result.ssh_invoked is False
    assert result.opencode_invoked is False
    assert result.model_invoked is False


# ──────────────────────────────────────────────
# T19: NoopWorkerResult JSON roundtrip
# ──────────────────────────────────────────────


def test_noop_worker_result_json_roundtrip():
    plan = _make_valid_plan()
    result = worker_runtime_gate(plan)
    json_str = result.to_json()
    restored = NoopWorkerResult.from_json(json_str)
    assert restored.allowed == result.allowed
    assert restored.status == result.status
    assert restored.real_execution is False
    assert restored.worker_invoked is False
    assert restored.ssh_invoked is False
    assert restored.opencode_invoked is False
    assert restored.model_invoked is False
    assert restored.approval_id == result.approval_id
    assert restored.runtime_assignment_id == result.runtime_assignment_id
    assert restored.execution_ticket_id == result.execution_ticket_id
    assert restored.dispatch_plan_id == result.dispatch_plan_id
    assert restored.workorder_id == result.workorder_id
    assert restored.base_sha == result.base_sha
    assert restored.target_role == result.target_role
    assert restored.target_node == result.target_node
    assert restored.provider == result.provider
    assert restored.model == result.model
    assert restored.action == result.action
    assert restored.operator_id == result.operator_id


# ──────────────────────────────────────────────
# T20: no-op path does not modify files
# ──────────────────────────────────────────────


def test_noop_does_not_modify_files():
    """Verify worker_runtime_gate does not write or modify any files."""
    import tempfile
    import os

    # Create a marker file
    tmpdir = tempfile.mkdtemp()
    marker = os.path.join(tmpdir, "marker.txt")
    with open(marker, "w") as f:
        f.write("before")

    # Run the gate
    plan = _make_valid_plan()
    result = worker_runtime_gate(plan)
    assert result.allowed is True

    # Verify marker file is unchanged
    with open(marker) as f:
        assert f.read() == "before", "no-op worker should not modify files"

    # Cleanup
    os.remove(marker)
    os.rmdir(tmpdir)


# ──────────────────────────────────────────────
# T21: missing operator_id → BLOCK
# ──────────────────────────────────────────────


def test_missing_operator_id_block():
    plan = _make_valid_plan(operator_id="")
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("operator_id" in r for r in result.block_reasons)


# ──────────────────────────────────────────────
# T22: self-check covers core worker gate cases
# ──────────────────────────────────────────────


def test_self_check_passes():
    result = self_check()
    assert result["passed"] is True, (
        f"self-check failed: {result['failed_count']}/{result['total']} failed"
    )
    assert result["passed_count"] >= 20
    assert result["total"] >= 20


# ──────────────────────────────────────────────
# T23: missing dispatch_plan_id in result (empty plan_id)
# ──────────────────────────────────────────────


def test_empty_plan_id_allowed():
    """plan_id empty is allowed (generated at runtime)."""
    plan = _make_valid_plan(plan_id="")
    result = worker_runtime_gate(plan)
    assert result.allowed is True
    assert result.dispatch_plan_id == ""


# ──────────────────────────────────────────────
# T24: multiple missing fields produce multiple block reasons
# ──────────────────────────────────────────────


def test_multiple_missing_fields():
    plan = _make_valid_plan(
        approval_id="",
        runtime_assignment_id="",
        execution_ticket_id="",
        workorder_id="",
        base_sha="",
        target_role="",
        target_node="",
        target_provider="",
        target_model="",
        action="",
        operator_id="",
    )
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    # Should have multiple block reasons
    assert len(result.block_reasons) >= 5


# ──────────────────────────────────────────────
# T25: model_call forbidden action → BLOCK
# ──────────────────────────────────────────────


def test_model_call_forbidden():
    plan = _make_valid_plan(action="model_call")
    result = worker_runtime_gate(plan)
    assert result.allowed is False
    assert any("forbidden" in r for r in result.block_reasons)
