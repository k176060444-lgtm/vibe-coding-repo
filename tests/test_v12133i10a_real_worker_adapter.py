"""V1.21.33I10A: Tests for Real Worker Adapter.

Tests the real_worker_adapter() function, ControlledWorkerRequest,
ControlledWorkerResult, and SSH smoke. All tests are local-only
except SSH smoke which is read-only and may be skipped.
"""

import json
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.vibe_real_worker_adapter import (
    ControlledWorkerRequest, ControlledWorkerResult,
    real_worker_adapter, ssh_smoke, FIXTURE_ALLOWED_ACTIONS,
    HARD_FORBIDDEN_ACTIONS,
)
from scripts.vibe_worker_runtime_gate import (
    NoopWorkerResult, worker_runtime_gate,
)
from scripts.vibe_dispatcher_runtime import DispatchPlan


def _make_noop_plan() -> DispatchPlan:
    return DispatchPlan(
        approval_id="appr_i10a_test",
        runtime_assignment_id="ra_i10a_test",
        execution_ticket_id="tkt_i10a_test",
        workorder_id="wo_i10a_test",
        base_sha="b328d458a3de0b2d9c3d26597f046f4f90355bd7",
        target_role="implementer",
        target_node="5bao",
        target_provider="minimax-plan",
        target_model="MiniMax-M3",
        action="local_exec",
        operator_id="kk",
        fallback_count=0,
        real_execution=False,
        planned_at="2026-06-27T12:00:00Z",
        plan_id="plan_i10a_test",
    )


def _make_real_plan() -> DispatchPlan:
    return DispatchPlan(
        approval_id="appr_i10a_real",
        runtime_assignment_id="ra_i10a_real",
        execution_ticket_id="tkt_i10a_real",
        workorder_id="wo_i10a_real",
        base_sha="b328d458a3de0b2d9c3d26597f046f4f90355bd7",
        target_role="implementer",
        target_node="5bao",
        target_provider="minimax-plan",
        target_model="MiniMax-M3",
        action="fixture_add",
        operator_id="kk",
        fallback_count=0,
        real_execution=True,
        planned_at="2026-06-27T12:00:00Z",
        plan_id="plan_i10a_real",
    )


def _make_gate_result(plan) -> NoopWorkerResult:
    return worker_runtime_gate(plan)


def _make_request(plan, gate_result=None, **kwargs) -> ControlledWorkerRequest:
    if gate_result is None:
        gate_result = _make_gate_result(plan)
    return ControlledWorkerRequest(
        gate_result=gate_result,
        plan=plan,
        max_parallel=1,
        read_only=True,
        **kwargs,
    )


# ── Tests ──


class TestI10ARealWorkerAdapter:
    """Test suite for real_worker_adapter."""

    def test_noop_path_passes(self):
        """SC1: no-op path → no-op PASS (I9 compatible)."""
        plan = _make_noop_plan()
        gate = _make_gate_result(plan)
        assert gate.allowed is True, f"gate should allow no-op: {gate.block_reasons}"

        req = _make_request(plan, gate)
        result = real_worker_adapter(req)
        assert result.allowed is True, f"should pass: {result.block_reasons}"
        assert result.status == "noop_passed"
        assert result.real_execution is False
        assert result.worker_invoked is False
        assert result.ssh_invoked is False
        assert result.opencode_invoked is False
        assert result.model_invoked is False

    def test_missing_gate_result_blocks(self):
        """SC2: missing gate result → BLOCK."""
        plan = _make_noop_plan()
        req = ControlledWorkerRequest(gate_result=None, plan=plan)
        result = real_worker_adapter(req)
        assert result.allowed is False
        assert any("missing gate result" in r for r in result.block_reasons)

    def test_missing_plan_blocks(self):
        """SC3: missing plan → BLOCK."""
        gate = _make_gate_result(_make_noop_plan())
        req = ControlledWorkerRequest(gate_result=gate, plan=None)
        result = real_worker_adapter(req)
        assert result.allowed is False
        assert any("missing plan" in r for r in result.block_reasons)

    def test_gate_not_allowed_blocks(self):
        """SC4: gate not allowed → BLOCK."""
        blocked_gate = NoopWorkerResult(allowed=False, block_reasons=["test block"])
        plan = _make_noop_plan()
        req = ControlledWorkerRequest(gate_result=blocked_gate, plan=plan)
        result = real_worker_adapter(req)
        assert result.allowed is False
        assert any("did not allow" in r for r in result.block_reasons)

    def test_real_execution_node_not_5bao_blocks(self):
        """SC5: real_execution=true but node not 5bao → BLOCK."""
        plan = _make_real_plan()
        plan.target_node = "9bao"
        gate = NoopWorkerResult(allowed=True, status="gate_passed")
        req = ControlledWorkerRequest(gate_result=gate, plan=plan)
        result = real_worker_adapter(req)
        assert result.allowed is False
        assert any("node must be 5bao" in r for r in result.block_reasons)

    def test_fallback_count_positive_blocks(self):
        """SC6: fallback_count>0 → BLOCK."""
        plan = _make_real_plan()
        plan.fallback_count = 1
        gate = NoopWorkerResult(allowed=True, status="gate_passed")
        req = ControlledWorkerRequest(gate_result=gate, plan=plan)
        result = real_worker_adapter(req)
        assert result.allowed is False
        assert any("fallback_count" in r for r in result.block_reasons)

    def test_max_parallel_gt_1_blocks(self):
        """SC7: max_parallel>1 → BLOCK."""
        plan = _make_real_plan()
        gate = NoopWorkerResult(allowed=True, status="gate_passed")
        req = ControlledWorkerRequest(gate_result=gate, plan=plan, max_parallel=2)
        result = real_worker_adapter(req)
        assert result.allowed is False
        assert any("max_parallel" in r for r in result.block_reasons)

    def test_forbidden_action_blocks(self):
        """SC8: forbidden action → BLOCK."""
        for action in HARD_FORBIDDEN_ACTIONS:
            plan = _make_real_plan()
            plan.action = action
            gate = NoopWorkerResult(allowed=True, status="gate_passed")
            req = ControlledWorkerRequest(gate_result=gate, plan=plan)
            result = real_worker_adapter(req)
            assert result.allowed is False, f"should block action={action}"
            assert any("forbidden" in r for r in result.block_reasons), \
                f"should mention forbidden for action={action}"

    def test_missing_provider_blocks(self):
        """SC9: missing provider → BLOCK."""
        plan = _make_real_plan()
        plan.target_provider = ""
        gate = NoopWorkerResult(allowed=True, status="gate_passed")
        req = ControlledWorkerRequest(gate_result=gate, plan=plan)
        result = real_worker_adapter(req)
        assert result.allowed is False
        assert any("target_provider" in r for r in result.block_reasons)

    def test_missing_model_blocks(self):
        """SC10: missing model → BLOCK."""
        plan = _make_real_plan()
        plan.target_model = ""
        gate = NoopWorkerResult(allowed=True, status="gate_passed")
        req = ControlledWorkerRequest(gate_result=gate, plan=plan)
        result = real_worker_adapter(req)
        assert result.allowed is False
        assert any("target_model" in r for r in result.block_reasons)

    def test_missing_trace_blocks(self):
        """SC11: missing approval/ticket/dispatch trace → BLOCK."""
        plan = _make_real_plan()
        plan.approval_id = ""
        plan.execution_ticket_id = ""
        gate = NoopWorkerResult(allowed=True, status="gate_passed")
        req = ControlledWorkerRequest(gate_result=gate, plan=plan)
        result = real_worker_adapter(req)
        assert result.allowed is False
        assert any("approval_id" in r for r in result.block_reasons)

    def test_21bao_stub_blocks(self):
        """SC12: 21bao stub → BLOCK."""
        plan = _make_real_plan()
        plan.target_node = "21bao"
        gate = NoopWorkerResult(allowed=True, status="gate_passed")
        req = ControlledWorkerRequest(gate_result=gate, plan=plan)
        result = real_worker_adapter(req)
        assert result.allowed is False
        assert any("not implemented" in r for r in result.block_reasons)

    def test_opencode_not_invoked(self):
        """SC13: opencode_invoked must be False."""
        plan = _make_noop_plan()
        gate = _make_gate_result(plan)
        req = _make_request(plan, gate)
        result = real_worker_adapter(req)
        assert result.opencode_invoked is False

    def test_model_not_invoked(self):
        """SC14: model_invoked must be False."""
        plan = _make_noop_plan()
        gate = _make_gate_result(plan)
        req = _make_request(plan, gate)
        result = real_worker_adapter(req)
        assert result.model_invoked is False

    def test_controlled_worker_result_json_roundtrip(self):
        """SC15: ControlledWorkerResult JSON roundtrip."""
        plan = _make_noop_plan()
        gate = _make_gate_result(plan)
        req = _make_request(plan, gate)
        result = real_worker_adapter(req)
        wr_json = result.to_json()
        wr_restored = ControlledWorkerResult.from_json(wr_json)
        assert wr_restored.allowed == result.allowed
        assert wr_restored.status == result.status
        assert wr_restored.real_execution == result.real_execution
        assert wr_restored.worker_invoked == result.worker_invoked

    def test_fixture_allowed_actions(self):
        """Verify fixture/doc allowlist actions pass validation."""
        for action in FIXTURE_ALLOWED_ACTIONS:
            plan = _make_real_plan()
            plan.action = action
            gate = NoopWorkerResult(allowed=True, status="gate_passed")
            req = ControlledWorkerRequest(gate_result=gate, plan=plan)
            result = real_worker_adapter(req)
            # May still block on SSH smoke if 5bao unreachable,
            # but should not block on action check
            action_blocked = any(
                "not in fixture/doc allowlist" in r
                for r in result.block_reasons
            )
            assert not action_blocked, \
                f"action={action} should be in allowlist: {result.block_reasons}"

    def test_real_execution_path_passes_with_ssh(self):
        """SC16: real_execution path with valid 5bao SSH smoke."""
        plan = _make_real_plan()
        gate = NoopWorkerResult(allowed=True, status="gate_passed")
        req = ControlledWorkerRequest(gate_result=gate, plan=plan)
        result = real_worker_adapter(req)
        # This may PASS or fail on SSH — either is acceptable
        if result.allowed:
            assert result.status == "real_passed"
            assert result.real_execution is True
            assert result.worker_invoked is True
            assert result.ssh_invoked is True
            assert result.opencode_invoked is False
            assert result.model_invoked is False
            assert result.command_count > 0
            assert result.exit_code == 0
            assert "ssh_smoke" in result.evidence
        else:
            # SSH unavailable — acceptable, test is informational
            assert any("SSH" in r for r in result.block_reasons) or \
                   any("ssh" in r for r in result.block_reasons)

    def test_ssh_smoke_read_only(self):
        """SSH smoke commands must be read-only."""
        smoke = ssh_smoke("5bao")
        assert smoke["read_only"] is True
        for cmd in smoke["commands"]:
            # All commands must be read-only
            assert cmd["command"] in (
                "hostname", "uname -a", "whoami", "pwd",
            ), f"unexpected command: {cmd['command']}"

    def test_worker_runtime_gate_real_execution_valid(self):
        """WorkerRuntimeGate must allow valid real_execution plan."""
        plan = _make_real_plan()
        result = worker_runtime_gate(plan)
        assert result.allowed is True, \
            f"gate should allow valid real_execution: {result.block_reasons}"
        assert result.real_execution is True
        assert result.worker_invoked is True
        assert result.status == "real_passed"

    def test_worker_runtime_gate_real_execution_invalid_node(self):
        """WorkerRuntimeGate must block real_execution with invalid node."""
        plan = _make_real_plan()
        plan.target_node = "9bao"
        result = worker_runtime_gate(plan)
        assert result.allowed is False
        assert any("node must be 5bao" in r for r in result.block_reasons)

    def test_worker_runtime_gate_real_execution_forbidden_action(self):
        """WorkerRuntimeGate must block real_execution with forbidden action."""
        plan = _make_real_plan()
        plan.action = "push"
        result = worker_runtime_gate(plan)
        assert result.allowed is False
        assert any("forbidden" in r for r in result.block_reasons)

    def test_worker_runtime_gate_real_execution_missing_provider(self):
        """WorkerRuntimeGate must block real_execution with missing provider."""
        plan = _make_real_plan()
        plan.target_provider = ""
        result = worker_runtime_gate(plan)
        assert result.allowed is False
        assert any("target_provider" in r for r in result.block_reasons)

    def test_worker_runtime_gate_real_execution_missing_model(self):
        """WorkerRuntimeGate must block real_execution with missing model."""
        plan = _make_real_plan()
        plan.target_model = ""
        result = worker_runtime_gate(plan)
        assert result.allowed is False
        assert any("target_model" in r for r in result.block_reasons)

    def test_controlled_worker_request_json_roundtrip(self):
        """ControlledWorkerRequest JSON roundtrip."""
        plan = _make_noop_plan()
        gate = _make_gate_result(plan)
        req = _make_request(plan, gate)
        req_json = req.to_json()
        req_restored = ControlledWorkerRequest.from_json(req_json)
        assert req_restored.max_parallel == req.max_parallel
        assert req_restored.plan.approval_id == req.plan.approval_id
        assert req_restored.gate_result.allowed == req.gate_result.allowed
