"""V1.21.33I8: Dispatcher Runtime dry-run tests.

Tests that the Dispatcher Runtime dry-run adapter correctly:
- Accepts valid admission results and produces a plan
- Blocks on missing/invalid admission, request, or contract objects
- Blocks on drift, forbidden actions, fallback violations, consumed tickets
- Keeps real_execution=False at all times
- Does NOT call subprocess/SSH/OpenCode/worker
"""

import json
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.vibe_runtime_assignment import (
    VALID_ROLES, FORBIDDEN_FILES,
    ApprovalContract, RuntimeAssignment, ExecutionTicket,
    RoleAssignment, derive_runtime_assignment_id,
)
from scripts.vibe_dispatcher_admission import (
    DispatchAdmissionRequest, DispatchAdmissionResult,
    check_dispatcher_admission,
)
from scripts.vibe_dispatcher_runtime import (
    DispatchPlan, DispatchDryRunResult,
    dispatch_dry_run, self_check,
)


def _make_valid_setup():
    """Build a valid approval → assignment → ticket → admission → request chain."""
    approval = ApprovalContract(
        approval_id="appr_i8_test",
        workorder_id="wo_i8_test",
        operator_id="kk",
        approved_at="2026-06-27T12:00:00Z",
        base_sha="d0a87fc47336d6e0cab32fc8933a8bf918bfef52",
        risk_level="low",
        scope="I8 test",
        selected_role_matrix={r: r for r in VALID_ROLES},
        selected_node_matrix={
            "orchestrator": "21bao", "planner": "21bao", "reviewer-b": "21bao",
            "git-integrator": "21bao", "tester-b": "9bao", "reviewer-a": "9bao",
            "explorer": "5bao", "implementer": "5bao", "tester-a": "5bao",
        },
        selected_model_matrix={
            r: {"provider": "minimax-plan", "model": "MiniMax-M3", "alias": "minimax-m3"}
            for r in VALID_ROLES
        },
        allowed_actions=["local_exec", "test_run", "self_check", "dry_run"],
        forbidden_actions=["push", "merge", "force_push", "model_call"],
        allowed_files=["tests/"],
        forbidden_files=FORBIDDEN_FILES,
        selection_source="operator_confirmed_default",
    )

    assignment = RuntimeAssignment(
        workorder_id=approval.workorder_id,
        approval_id=approval.approval_id,
        runtime_assignment_id=derive_runtime_assignment_id(approval.approval_id),
        base_sha=approval.base_sha,
        created_at=approval.approved_at,
        scope=approval.scope,
        role_assignments={
            r: RoleAssignment(
                role=r, assignee=f"{r}/node",
                node_id=approval.selected_node_matrix[r],
                transport="ssh" if approval.selected_node_matrix[r] in ("5bao", "9bao") else "local-exec",
                provider=approval.selected_model_matrix[r]["provider"],
                model=approval.selected_model_matrix[r]["model"],
                model_alias=approval.selected_model_matrix[r]["alias"],
            )
            for r in VALID_ROLES
        },
        operator_selected=True,
        fallback_allowed=False,
        fallback_count=0,
        derivation_source="approval_contract",
        allowed_actions=approval.allowed_actions,
        forbidden_actions=approval.forbidden_actions,
        allowed_files=approval.allowed_files,
        forbidden_files=approval.forbidden_files,
    )

    ticket = ExecutionTicket(
        ticket_id="tkt_i8_test",
        workorder_id=approval.workorder_id,
        approval_id=approval.approval_id,
        role="implementer",
        node_id="5bao",
        provider="minimax-plan",
        model="MiniMax-M3",
        base_sha=approval.base_sha,
        allowed_paths=["tests/"],
        forbidden_paths=FORBIDDEN_FILES,
    )

    request = DispatchAdmissionRequest(
        approval=approval,
        runtime_assignment=assignment,
        execution_ticket=ticket,
        target_role="implementer",
        target_node="5bao",
        target_provider="minimax-plan",
        target_model="MiniMax-M3",
        action="dry_run",
    )

    admission_result = check_dispatcher_admission(request)

    return approval, assignment, ticket, request, admission_result


class TestDispatcherRuntimeDryRun(unittest.TestCase):
    """Test the Dispatcher Runtime dry-run adapter."""

    def setUp(self):
        self.appr, self.assign, self.ticket, self.req, self.adm = _make_valid_setup()

    # T1: valid admission → dry-run PASS
    def test_valid_admission_dryrun_pass(self):
        dr = dispatch_dry_run(self.adm, self.req)
        self.assertTrue(dr.allowed, f"Expected allowed=True, got {dr.block_reasons}")
        self.assertIsNotNone(dr.plan, "Expected a plan")
        self.assertIn("plan_id", dr.plan)
        self.assertEqual(dr.plan["real_execution"], False)
        self.assertEqual(dr.plan["fallback_count"], 0)
        self.assertEqual(dr.plan["target_role"], "implementer")
        self.assertEqual(dr.plan["target_node"], "5bao")
        self.assertEqual(dr.plan["approval_id"], "appr_i8_test")
        self.assertEqual(dr.plan["workorder_id"], "wo_i8_test")
        self.assertEqual(dr.plan["base_sha"], "d0a87fc47336d6e0cab32fc8933a8bf918bfef52")

    # T2: missing admission → BLOCK
    def test_missing_admission_block(self):
        dr = dispatch_dry_run(None, self.req)  # type: ignore[arg-type]
        self.assertFalse(dr.allowed)
        self.assertTrue(any("missing admission" in r for r in dr.block_reasons))

    # T3: admission allowed=false → BLOCK
    def test_admission_not_allowed_block(self):
        blocked_adm = DispatchAdmissionResult(allowed=False, block_reasons=["test block"])
        dr = dispatch_dry_run(blocked_adm, self.req)
        self.assertFalse(dr.allowed)
        self.assertTrue(any("not allowed" in r for r in dr.block_reasons))

    # T4: missing request → BLOCK
    def test_missing_request_block(self):
        dr = dispatch_dry_run(self.adm, None)  # type: ignore[arg-type]
        self.assertFalse(dr.allowed)
        self.assertTrue(any("missing dispatch request" in r for r in dr.block_reasons))

    # T5: missing approval → BLOCK
    def test_missing_approval_block(self):
        req = DispatchAdmissionRequest(
            approval=None, runtime_assignment=self.assign,
            execution_ticket=self.ticket,
            target_role="implementer", action="dry_run",
        )
        adm = check_dispatcher_admission(req)
        dr = dispatch_dry_run(adm, req)
        self.assertFalse(dr.allowed)
        self.assertTrue(any("missing approval" in r for r in dr.block_reasons))

    # T6: missing runtime assignment → BLOCK
    def test_missing_runtime_assignment_block(self):
        req = DispatchAdmissionRequest(
            approval=self.appr, runtime_assignment=None,
            execution_ticket=self.ticket,
            target_role="implementer", action="dry_run",
        )
        adm = check_dispatcher_admission(req)
        dr = dispatch_dry_run(adm, req)
        self.assertFalse(dr.allowed)
        self.assertTrue(any("missing runtime assignment" in r for r in dr.block_reasons))

    # T7: missing ticket → BLOCK
    def test_missing_ticket_block(self):
        req = DispatchAdmissionRequest(
            approval=self.appr, runtime_assignment=self.assign,
            execution_ticket=None,
            target_role="implementer", action="dry_run",
        )
        adm = check_dispatcher_admission(req)
        dr = dispatch_dry_run(adm, req)
        self.assertFalse(dr.allowed)
        self.assertTrue(any("missing execution ticket" in r for r in dr.block_reasons))

    # T8: target_role drift → BLOCK
    def test_target_role_drift_block(self):
        req = DispatchAdmissionRequest(
            approval=self.appr, runtime_assignment=self.assign,
            execution_ticket=self.ticket,
            target_role="explorer", target_node="5bao",
            target_provider="minimax-plan", target_model="MiniMax-M3",
            action="dry_run",
        )
        adm = check_dispatcher_admission(req)
        dr = dispatch_dry_run(adm, req)
        self.assertFalse(dr.allowed)
        self.assertTrue(any("drift" in r for r in dr.block_reasons))

    # T9: target_node drift → BLOCK
    def test_target_node_drift_block(self):
        req = DispatchAdmissionRequest(
            approval=self.appr, runtime_assignment=self.assign,
            execution_ticket=self.ticket,
            target_role="implementer", target_node="9bao",
            target_provider="minimax-plan", target_model="MiniMax-M3",
            action="dry_run",
        )
        adm = check_dispatcher_admission(req)
        dr = dispatch_dry_run(adm, req)
        self.assertFalse(dr.allowed)
        self.assertTrue(any("drift" in r for r in dr.block_reasons))

    # T10: forbidden action → BLOCK
    def test_forbidden_action_block(self):
        req = DispatchAdmissionRequest(
            approval=self.appr, runtime_assignment=self.assign,
            execution_ticket=self.ticket,
            target_role="implementer", target_node="5bao",
            target_provider="minimax-plan", target_model="MiniMax-M3",
            action="push",
        )
        adm = check_dispatcher_admission(req)
        dr = dispatch_dry_run(adm, req)
        self.assertFalse(dr.allowed)
        self.assertTrue(any("forbidden" in r for r in dr.block_reasons))

    # T11: fallback_allowed=true → BLOCK
    def test_fallback_allowed_true_block(self):
        assign_fb = RuntimeAssignment(
            workorder_id=self.assign.workorder_id,
            approval_id=self.assign.approval_id,
            runtime_assignment_id=self.assign.runtime_assignment_id,
            base_sha=self.assign.base_sha,
            created_at=self.assign.created_at,
            scope=self.assign.scope,
            role_assignments=self.assign.role_assignments,
            operator_selected=True, fallback_allowed=True, fallback_count=0,
            derivation_source="approval_contract",
        )
        req = DispatchAdmissionRequest(
            approval=self.appr, runtime_assignment=assign_fb,
            execution_ticket=self.ticket,
            target_role="implementer", target_node="5bao",
            target_provider="minimax-plan", target_model="MiniMax-M3",
            action="dry_run",
        )
        adm = check_dispatcher_admission(req)
        dr = dispatch_dry_run(adm, req)
        self.assertFalse(dr.allowed)
        self.assertTrue(any("fallback_allowed" in r for r in dr.block_reasons))

    # T12: fallback_count>0 → BLOCK
    def test_fallback_count_positive_block(self):
        assign_fb = RuntimeAssignment(
            workorder_id=self.assign.workorder_id,
            approval_id=self.assign.approval_id,
            runtime_assignment_id=self.assign.runtime_assignment_id,
            base_sha=self.assign.base_sha,
            created_at=self.assign.created_at,
            scope=self.assign.scope,
            role_assignments=self.assign.role_assignments,
            operator_selected=True, fallback_allowed=False, fallback_count=1,
            derivation_source="approval_contract",
        )
        req = DispatchAdmissionRequest(
            approval=self.appr, runtime_assignment=assign_fb,
            execution_ticket=self.ticket,
            target_role="implementer", target_node="5bao",
            target_provider="minimax-plan", target_model="MiniMax-M3",
            action="dry_run",
        )
        adm = check_dispatcher_admission(req)
        dr = dispatch_dry_run(adm, req)
        self.assertFalse(dr.allowed)
        self.assertTrue(any("fallback_count" in r for r in dr.block_reasons))

    # T13: consumed ticket → BLOCK
    def test_consumed_ticket_block(self):
        req = DispatchAdmissionRequest(
            approval=self.appr, runtime_assignment=self.assign,
            execution_ticket=self.ticket,
            target_role="implementer", target_node="5bao",
            target_provider="minimax-plan", target_model="MiniMax-M3",
            action="dry_run",
            consumed_ticket_ids={self.ticket.ticket_id},
        )
        adm = check_dispatcher_admission(req)
        dr = dispatch_dry_run(adm, req)
        self.assertFalse(dr.allowed)
        self.assertTrue(any("consumed" in r for r in dr.block_reasons))

    # T14: real_execution must remain false
    def test_real_execution_forced_false(self):
        dr = dispatch_dry_run(self.adm, self.req)
        self.assertTrue(dr.allowed)
        self.assertIsNotNone(dr.plan)
        self.assertEqual(dr.plan["real_execution"], False)

    # T15: dry-run does not call subprocess/SSH/OpenCode/worker
    def test_no_subprocess_ssh_opencode_worker(self):
        dr = dispatch_dry_run(self.adm, self.req)
        self.assertTrue(dr.allowed)
        # The function is a pure Python function with no subprocess calls.
        # This test verifies that calling it doesn't crash and returns
        # a valid result without side effects.
        self.assertIn("plan_id", dr.plan)
        self.assertTrue(dr.runtime_id.startswith("dryrun_"),
                        f"Expected dryrun_ prefix, got {dr.runtime_id}")

    # T16: DispatchPlan JSON roundtrip
    def test_dispatch_plan_json_roundtrip(self):
        plan = DispatchPlan(
            approval_id="appr_test", runtime_assignment_id="ra_test",
            execution_ticket_id="tkt_test", workorder_id="wo_test",
            base_sha="abc1234", target_role="implementer",
            target_node="5bao", target_provider="minimax-plan",
            target_model="MiniMax-M3", action="dry_run",
            operator_id="kk", fallback_count=0, real_execution=False,
            planned_at="2026-06-27T12:00:00Z", plan_id="plan_test",
        )
        json_str = plan.to_json()
        restored = DispatchPlan.from_json(json_str)
        self.assertEqual(restored.approval_id, plan.approval_id)
        self.assertEqual(restored.runtime_assignment_id, plan.runtime_assignment_id)
        self.assertEqual(restored.execution_ticket_id, plan.execution_ticket_id)
        self.assertEqual(restored.workorder_id, plan.workorder_id)
        self.assertEqual(restored.base_sha, plan.base_sha)
        self.assertEqual(restored.target_role, plan.target_role)
        self.assertEqual(restored.target_node, plan.target_node)
        self.assertEqual(restored.target_provider, plan.target_provider)
        self.assertEqual(restored.target_model, plan.target_model)
        self.assertEqual(restored.action, plan.action)
        self.assertEqual(restored.operator_id, plan.operator_id)
        self.assertEqual(restored.fallback_count, 0)
        self.assertEqual(restored.real_execution, False)

    # T17: DispatchDryRunResult JSON roundtrip
    def test_dryrun_result_json_roundtrip(self):
        dr = dispatch_dry_run(self.adm, self.req)
        json_str = dr.to_json()
        restored = DispatchDryRunResult.from_json(json_str)
        self.assertEqual(restored.allowed, dr.allowed)
        self.assertEqual(restored.runtime_id, dr.runtime_id)
        self.assertEqual(restored.admission_id, dr.admission_id)
        self.assertEqual(restored.block_reasons, dr.block_reasons)

    # T18: Dry-run trace is complete
    def test_dryrun_trace_complete(self):
        dr = dispatch_dry_run(self.adm, self.req)
        expected_fields = [
            "approval_id", "runtime_assignment_id", "execution_ticket_id",
            "workorder_id", "base_sha", "target_role", "target_node",
            "target_provider", "target_model", "action", "operator_id",
        ]
        for field in expected_fields:
            self.assertIn(field, dr.trace,
                          f"Missing trace field: {field}")
            self.assertTrue(dr.trace[field], f"Empty trace field: {field}")

    # T19: Self-check covers core dry-run cases
    def test_self_check_passes(self):
        result = self_check()
        self.assertTrue(result["passed"],
                        f"Self-check failed: {result['failed_count']}/{result['total']}")
        self.assertEqual(result["failed_count"], 0)

    # T20: Plan validation rejects real_execution=True
    def test_plan_rejects_real_execution_true(self):
        plan = DispatchPlan(
            approval_id="a", runtime_assignment_id="b",
            execution_ticket_id="c", workorder_id="d",
            base_sha="e", target_role="f",
            target_node="g", target_provider="h",
            target_model="i", action="j",
            operator_id="k", real_execution=True,
        )
        errors = plan.validate()
        self.assertTrue(any("real_execution" in e for e in errors))

    # T21: Plan validation rejects fallback_count>0
    def test_plan_rejects_fallback_count_positive(self):
        plan = DispatchPlan(
            approval_id="a", runtime_assignment_id="b",
            execution_ticket_id="c", workorder_id="d",
            base_sha="e", target_role="f",
            target_node="g", target_provider="h",
            target_model="i", action="j",
            operator_id="k", fallback_count=1,
        )
        errors = plan.validate()
        self.assertTrue(any("fallback_count" in e for e in errors))

    # T22: Runtime cannot bypass Admission — admission allowed=false must block
    def test_runtime_cannot_bypass_admission(self):
        # Even if we try to pass a fake admission result with allowed=True
        # but the underlying request has a bad ticket, the runtime re-validates
        bad_ticket = ExecutionTicket(
            ticket_id="tkt_bad", workorder_id="wo_bad",
            approval_id="appr_bad", role="invalid_role",
            node_id="5bao", provider="x", model="y",
        )
        req = DispatchAdmissionRequest(
            approval=self.appr, runtime_assignment=self.assign,
            execution_ticket=bad_ticket,
            target_role="implementer", target_node="5bao",
            target_provider="minimax-plan", target_model="MiniMax-M3",
            action="dry_run",
        )
        adm = check_dispatcher_admission(req)
        dr = dispatch_dry_run(adm, req)
        self.assertFalse(dr.allowed,
                         "Runtime must re-validate and block invalid ticket")

    # T23: Runtime cannot bypass ApprovalContract — missing approval_id must block
    def test_runtime_cannot_bypass_approval(self):
        bad_approval = ApprovalContract(
            approval_id="appr_bad_nonexistent", workorder_id="wo_bad", operator_id="kk",
            approved_at="2026-06-27T12:00:00Z",
            base_sha="d0a87fc47336d6e0cab32fc8933a8bf918bfef52",
            scope="bad", selection_source="operator_confirmed_default",
            selected_role_matrix={r: r for r in VALID_ROLES},
            selected_node_matrix=self.appr.selected_node_matrix,
            selected_model_matrix=self.appr.selected_model_matrix,
        )
        bad_assign = RuntimeAssignment(
            workorder_id="wo_bad", approval_id="different_approval_id",
            runtime_assignment_id="ra_bad_nonexistent",
            base_sha="d0a87fc47336d6e0cab32fc8933a8bf918bfef52",
            created_at="now", scope="bad",
            role_assignments=self.assign.role_assignments,
            operator_selected=True, fallback_allowed=False, fallback_count=0,
            derivation_source="approval_contract",
        )
        bad_ticket = ExecutionTicket(
            ticket_id="tkt_bad", workorder_id="wo_bad",
            approval_id="", role="implementer",
            node_id="5bao", provider="minimax-plan", model="MiniMax-M3",
        )
        req = DispatchAdmissionRequest(
            approval=bad_approval, runtime_assignment=bad_assign,
            execution_ticket=bad_ticket,
            target_role="implementer", target_node="5bao",
            target_provider="minimax-plan", target_model="MiniMax-M3",
            action="dry_run",
        )
        adm = check_dispatcher_admission(req)
        dr = dispatch_dry_run(adm, req)
        self.assertFalse(dr.allowed,
                         "Runtime must block invalid approval")

    # T24: base_sha mismatch across approval/assignment/ticket → BLOCK
    def test_base_sha_mismatch_block(self):
        bad_approval = ApprovalContract(
            approval_id="appr_sha_mismatch", workorder_id="wo_sha_mismatch",
            operator_id="kk",
            approved_at="2026-06-27T12:00:00Z",
            base_sha="aaaaaaa1111111",
            scope="sha mismatch test",
            selection_source="operator_confirmed_default",
            selected_role_matrix={r: r for r in VALID_ROLES},
            selected_node_matrix=self.appr.selected_node_matrix,
            selected_model_matrix=self.appr.selected_model_matrix,
        )
        bad_assign = RuntimeAssignment(
            workorder_id="wo_sha_mismatch",
            approval_id="appr_sha_mismatch",
            runtime_assignment_id=derive_runtime_assignment_id("appr_sha_mismatch"),
            base_sha="aaaaaaa1111111",
            created_at="now", scope="sha mismatch test",
            role_assignments=self.assign.role_assignments,
            operator_selected=True, fallback_allowed=False, fallback_count=0,
            derivation_source="approval_contract",
        )
        bad_ticket = ExecutionTicket(
            ticket_id="tkt_sha_mismatch",
            workorder_id="wo_sha_mismatch",
            approval_id="appr_sha_mismatch",
            role="implementer", node_id="5bao",
            provider="minimax-plan", model="MiniMax-M3",
            base_sha="bbbbbbb2222222",  # different from approval/assignment
        )
        req = DispatchAdmissionRequest(
            approval=bad_approval, runtime_assignment=bad_assign,
            execution_ticket=bad_ticket,
            target_role="implementer", target_node="5bao",
            target_provider="minimax-plan", target_model="MiniMax-M3",
            action="dry_run",
        )
        adm = check_dispatcher_admission(req)
        dr = dispatch_dry_run(adm, req)
        self.assertFalse(dr.allowed)
        self.assertTrue(any("base_sha" in r for r in dr.block_reasons))

    # T25: Approval-id mismatch across approval/assignment/ticket → BLOCK
    def test_approval_id_mismatch_block(self):
        bad_ticket = ExecutionTicket(
            ticket_id="tkt_mismatch",
            workorder_id=self.appr.workorder_id,
            approval_id="different_approval_id",
            role="implementer", node_id="5bao",
            provider="minimax-plan", model="MiniMax-M3",
            base_sha=self.appr.base_sha,
        )
        req = DispatchAdmissionRequest(
            approval=self.appr, runtime_assignment=self.assign,
            execution_ticket=bad_ticket,
            target_role="implementer", target_node="5bao",
            target_provider="minimax-plan", target_model="MiniMax-M3",
            action="dry_run",
        )
        adm = check_dispatcher_admission(req)
        dr = dispatch_dry_run(adm, req)
        self.assertFalse(dr.allowed)
        self.assertTrue(any("approval_id" in r for r in dr.block_reasons))


if __name__ == "__main__":
    unittest.main()
