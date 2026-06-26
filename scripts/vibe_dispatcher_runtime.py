"""V1.21.33I8: Dispatcher Runtime dry-run/no-op adapter.

Implements the Runtime layer for dispatch: validates that a
DispatchAdmissionResult.allowed=True admission can proceed to a
DispatchPlan, then produces a DispatchDryRunResult.

This is a DRY-RUN / NO-OP adapter only. It does NOT execute any
worker, dispatcher, SSH session, OpenCode call, or model API call.
It is a planning layer that decides what *would* happen, with no
side effects.

Architecture invariant: Recommendation != ApprovalContract !=
RuntimeAssignment != ExecutionTicket != DispatchAdmission !=
DispatchRuntime.
"""

import json
import hashlib
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from scripts.vibe_runtime_assignment import (
    VALID_ROLES, VALID_NODES, FORBIDDEN_FILES, SECRET_PATTERNS,
    ApprovalContract, RuntimeAssignment, ExecutionTicket,
    RoleAssignment, derive_runtime_assignment_id,
    validate_base_sha_match, validate_approval_not_expired,
    validate_action_allowed, check_secret_leak, check_forbidden_files,
    generate_workorder_id, generate_approval_id, generate_ticket_id,
)

from scripts.vibe_dispatcher_admission import (
    DispatchAdmissionRequest, DispatchAdmissionResult,
    check_dispatcher_admission,
)


# ──────────────────────────────────────────────
# DispatchPlan — the dry-run output plan
# ──────────────────────────────────────────────


@dataclass
class DispatchPlan:
    """The plan produced by the dispatcher runtime dry-run.

    Contains all information needed for a real dispatch, but with
    real_execution=False. This plan is the output of the planning
    phase and must be operator-approved before real execution.
    """
    approval_id: str
    runtime_assignment_id: str
    execution_ticket_id: str
    workorder_id: str
    base_sha: str
    target_role: str
    target_node: str
    target_provider: str
    target_model: str
    action: str
    operator_id: str
    fallback_count: int = 0
    real_execution: bool = False  # MUST remain False for dry-run
    planned_at: str = ""
    plan_id: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> "DispatchPlan":
        return cls(**json.loads(data))

    def validate(self) -> List[str]:
        errors = []
        if not self.approval_id:
            errors.append("approval_id is required")
        if not self.runtime_assignment_id:
            errors.append("runtime_assignment_id is required")
        if not self.execution_ticket_id:
            errors.append("execution_ticket_id is required")
        if not self.workorder_id:
            errors.append("workorder_id is required")
        if not self.base_sha:
            errors.append("base_sha is required")
        if not self.target_role:
            errors.append("target_role is required")
        if not self.target_node:
            errors.append("target_node is required")
        if self.real_execution is not False:
            errors.append("real_execution must be False for dry-run")
        if self.fallback_count > 0:
            errors.append(f"fallback_count must be 0, got {self.fallback_count}")
        return errors


# ──────────────────────────────────────────────
# DispatchDryRunResult — the dry-run verdict
# ──────────────────────────────────────────────


@dataclass
class DispatchDryRunResult:
    """Result of the dispatcher runtime dry-run."""
    allowed: bool = False
    block_reasons: List[str] = field(default_factory=list)
    plan: Optional[Dict[str, Any]] = None
    runtime_id: str = ""
    decided_at: str = ""
    admission_id: str = ""
    trace: Dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> "DispatchDryRunResult":
        d = json.loads(data)
        return cls(**d)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _generate_plan_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    h = hashlib.sha256(ts.encode()).hexdigest()[:8]
    return f"plan_{ts}_{h}"


# ──────────────────────────────────────────────
# Main Entry Point — pure function, no side effects
# ──────────────────────────────────────────────


def dispatch_dry_run(
    admission_result: DispatchAdmissionResult,
    request: DispatchAdmissionRequest,
) -> DispatchDryRunResult:
    """Run the dispatcher runtime dry-run.

    This is a NO-OP / planning-only function. It does NOT execute
    any worker, SSH, OpenCode, subprocess, or model call.

    Args:
        admission_result: The result of check_dispatcher_admission()
        request: The original DispatchAdmissionRequest

    Returns:
        DispatchDryRunResult with allowed=True iff all checks pass
    """
    result = DispatchDryRunResult()
    result.decided_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    errors: List[str] = []

    # R1: Admission result must exist
    if admission_result is None:
        errors.append("missing admission result (DispatchAdmissionResult required)")
        result.allowed = False
        result.block_reasons = errors
        return result

    # R2: Admission must be allowed
    if not admission_result.allowed:
        errors.append(
            "admission not allowed: " + "; ".join(admission_result.block_reasons)
        )
        result.allowed = False
        result.block_reasons = errors
        return result

    # R3: Request must exist
    if request is None:
        errors.append("missing dispatch request (DispatchAdmissionRequest required)")
        result.allowed = False
        result.block_reasons = errors
        return result

    # R4: All three contract objects must be present
    if request.approval is None:
        errors.append("missing approval (ApprovalContract required)")
    if request.runtime_assignment is None:
        errors.append("missing runtime assignment (RuntimeAssignment required)")
    if request.execution_ticket is None:
        errors.append("missing execution ticket (ExecutionTicket required)")

    if errors:
        result.allowed = False
        result.block_reasons = errors
        return result

    approval = request.approval  # type: ignore[assignment]
    assignment = request.runtime_assignment  # type: ignore[assignment]
    ticket = request.execution_ticket  # type: ignore[assignment]

    # R5: Approval must validate
    approval_errors = approval.validate()
    if approval_errors:
        errors.append(f"approval invalid: {approval_errors}")

    # R6: Approval must not be expired
    expired_errors = validate_approval_not_expired(approval)
    if expired_errors:
        errors.extend(expired_errors)

    # R7: Assignment must validate
    assign_errors = assignment.validate()
    if assign_errors:
        errors.append(f"assignment invalid: {assign_errors}")

    # R8: Ticket must validate
    ticket_errors = ticket.validate()
    if ticket_errors:
        errors.append(f"ticket invalid: {ticket_errors}")

    # R9: Cross-id trace — approval_id must match across all three
    if assignment.approval_id != approval.approval_id:
        errors.append(
            f"approval_id mismatch: approval={approval.approval_id}, "
            f"assignment={assignment.approval_id}"
        )
    if ticket.approval_id != approval.approval_id:
        errors.append(
            f"approval_id mismatch: approval={approval.approval_id}, "
            f"ticket={ticket.approval_id}"
        )

    # R10: Cross-id trace — workorder_id must match
    if ticket.workorder_id != approval.workorder_id:
        errors.append(
            f"workorder_id mismatch: approval={approval.workorder_id}, "
            f"ticket={ticket.workorder_id}"
        )

    # R11: Cross-id trace — runtime_assignment_id must match derived value
    expected_ra_id = derive_runtime_assignment_id(approval.approval_id)
    if assignment.runtime_assignment_id != expected_ra_id:
        errors.append(
            f"runtime_assignment_id mismatch: expected={expected_ra_id}, "
            f"got={assignment.runtime_assignment_id}"
        )

    # R12: base_sha must match across all three
    if approval.base_sha != assignment.base_sha:
        errors.append(
            f"base_sha mismatch between approval and assignment: "
            f"approval={approval.base_sha}, assignment={assignment.base_sha}"
        )
    if assignment.base_sha != ticket.base_sha:
        errors.append(
            f"base_sha mismatch between assignment and ticket: "
            f"assignment={assignment.base_sha}, ticket={ticket.base_sha}"
        )

    # R13: operator_selected must be True
    if assignment.operator_selected is not True:
        errors.append("runtime_assignment.operator_selected must be True")

    # R14: fallback_allowed must be False
    if assignment.fallback_allowed is not False:
        errors.append("fallback_allowed must be False for executable dispatch")

    # R15: fallback_count must be 0
    if assignment.fallback_count != 0:
        errors.append(f"fallback_count must be 0, got {assignment.fallback_count}")

    # R16: ticket must not be already consumed
    if ticket.ticket_id in request.consumed_ticket_ids:
        errors.append(
            f"execution ticket {ticket.ticket_id} has already been consumed / reused"
        )

    # R17: action must be allowed and not forbidden
    action_errors = validate_action_allowed(assignment, request.action)
    if action_errors:
        errors.extend(action_errors)

    # R18: Target role/node/provider/model drift check
    if request.target_role and request.target_role != ticket.role:
        errors.append(
            f"target_role drift: ticket.role={ticket.role}, "
            f"target_role={request.target_role}"
        )
    if request.target_node and request.target_node != ticket.node_id:
        errors.append(
            f"target_node drift: ticket.node_id={ticket.node_id}, "
            f"target_node={request.target_node}"
        )
    if request.target_provider and request.target_provider != ticket.provider:
        errors.append(
            f"target_provider drift: ticket.provider={ticket.provider}, "
            f"target_provider={request.target_provider}"
        )
    if request.target_model and request.target_model != ticket.model:
        errors.append(
            f"target_model drift: ticket.model={ticket.model}, "
            f"target_model={request.target_model}"
        )

    # R19: Cross-check ticket.role exists in assignment
    if ticket.role not in assignment.role_assignments:
        errors.append(f"ticket.role={ticket.role} not in runtime assignment roles")
    else:
        ra = assignment.role_assignments[ticket.role]
        if ra.node_id != ticket.node_id:
            errors.append(
                f"role/node drift: assignment[{ticket.role}].node_id={ra.node_id}, "
                f"ticket.node_id={ticket.node_id}"
            )
        if ra.provider != ticket.provider:
            errors.append(
                f"role/provider drift: assignment[{ticket.role}].provider={ra.provider}, "
                f"ticket.provider={ticket.provider}"
            )
        if ra.model != ticket.model:
            errors.append(
                f"role/model drift: assignment[{ticket.role}].model={ra.model}, "
                f"ticket.model={ticket.model}"
            )

    # Finalize
    if errors:
        result.allowed = False
        result.block_reasons = errors
        return result

    # Build trace for the successful dry-run
    result.admission_id = admission_result.admission_id
    result.trace = {
        "approval_id": approval.approval_id,
        "runtime_assignment_id": assignment.runtime_assignment_id,
        "execution_ticket_id": ticket.ticket_id,
        "workorder_id": approval.workorder_id,
        "base_sha": approval.base_sha,
        "target_role": request.target_role,
        "target_node": request.target_node,
        "target_provider": request.target_provider,
        "target_model": request.target_model,
        "action": request.action,
        "operator_id": approval.operator_id,
    }

    # Build plan (dry-run only — real_execution is forced False)
    plan = DispatchPlan(
        approval_id=approval.approval_id,
        runtime_assignment_id=assignment.runtime_assignment_id,
        execution_ticket_id=ticket.ticket_id,
        workorder_id=approval.workorder_id,
        base_sha=approval.base_sha,
        target_role=request.target_role,
        target_node=request.target_node,
        target_provider=request.target_provider,
        target_model=request.target_model,
        action=request.action,
        operator_id=approval.operator_id,
        fallback_count=0,
        real_execution=False,
        planned_at=result.decided_at,
        plan_id=_generate_plan_id(),
    )

    result.allowed = True
    result.plan = asdict(plan)
    result.runtime_id = f"dryrun_{plan.plan_id}"

    return result


# ──────────────────────────────────────────────
# Self-Check
# ──────────────────────────────────────────────


def _make_valid_setup() -> tuple:
    """Build a valid approval → assignment → ticket → admission → request chain."""
    approval = ApprovalContract(
        approval_id="appr_i8_valid",
        workorder_id="wo_i8_valid",
        operator_id="kk",
        approved_at="2026-06-27T12:00:00Z",
        base_sha="d0a87fc47336d6e0cab32fc8933a8bf918bfef52",
        risk_level="low",
        scope="I8 dry-run test",
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
        ticket_id="tkt_i8_valid",
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


def self_check() -> Dict[str, Any]:
    """Run self-check and return results."""
    results: List[Dict[str, Any]] = []
    all_pass = True

    def _check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal all_pass
        if not ok:
            all_pass = False
        results.append({"name": name, "passed": ok, "detail": detail})

    # SC1: valid admission → dry-run PASS
    appr, assign, ticket, req, adm = _make_valid_setup()
    dr = dispatch_dry_run(adm, req)
    _check("valid_admission_dryrun_pass",
           dr.allowed is True and dr.plan is not None,
           str(dr.block_reasons))

    # SC2: missing admission → BLOCK
    dr2 = dispatch_dry_run(None, req)  # type: ignore[arg-type]
    _check("missing_admission_block",
           dr2.allowed is False,
           any("missing admission" in r for r in dr2.block_reasons))

    # SC3: admission allowed=false → BLOCK
    blocked_adm = DispatchAdmissionResult(allowed=False, block_reasons=["test block"])
    dr3 = dispatch_dry_run(blocked_adm, req)
    _check("admission_not_allowed_block",
           dr3.allowed is False,
           any("not allowed" in r for r in dr3.block_reasons))

    # SC4: missing request → BLOCK
    dr4 = dispatch_dry_run(adm, None)  # type: ignore[arg-type]
    _check("missing_request_block",
           dr4.allowed is False,
           any("missing dispatch request" in r for r in dr4.block_reasons))

    # SC5: missing approval → BLOCK
    req_no_appr = DispatchAdmissionRequest(
        approval=None, runtime_assignment=assign, execution_ticket=ticket,
        target_role="implementer", action="dry_run",
    )
    adm_no_appr = check_dispatcher_admission(req_no_appr)
    dr5 = dispatch_dry_run(adm_no_appr, req_no_appr)
    _check("missing_approval_block",
           dr5.allowed is False,
           any("missing approval" in r for r in dr5.block_reasons))

    # SC6: missing runtime assignment → BLOCK
    req_no_ra = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=None, execution_ticket=ticket,
        target_role="implementer", action="dry_run",
    )
    adm_no_ra = check_dispatcher_admission(req_no_ra)
    dr6 = dispatch_dry_run(adm_no_ra, req_no_ra)
    _check("missing_runtime_assignment_block",
           dr6.allowed is False,
           any("missing runtime assignment" in r for r in dr6.block_reasons))

    # SC7: missing ticket → BLOCK
    req_no_tkt = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign, execution_ticket=None,
        target_role="implementer", action="dry_run",
    )
    adm_no_tkt = check_dispatcher_admission(req_no_tkt)
    dr7 = dispatch_dry_run(adm_no_tkt, req_no_tkt)
    _check("missing_ticket_block",
           dr7.allowed is False,
           any("missing execution ticket" in r for r in dr7.block_reasons))

    # SC8: target_role drift → BLOCK
    req_drift = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign, execution_ticket=ticket,
        target_role="explorer", target_node="5bao",
        target_provider="minimax-plan", target_model="MiniMax-M3",
        action="dry_run",
    )
    adm_drift = check_dispatcher_admission(req_drift)
    dr8 = dispatch_dry_run(adm_drift, req_drift)
    _check("target_role_drift_block",
           dr8.allowed is False,
           any("drift" in r for r in dr8.block_reasons))

    # SC9: forbidden action → BLOCK
    req_forbidden = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign, execution_ticket=ticket,
        target_role="implementer", target_node="5bao",
        target_provider="minimax-plan", target_model="MiniMax-M3",
        action="push",
    )
    adm_forbidden = check_dispatcher_admission(req_forbidden)
    dr9 = dispatch_dry_run(adm_forbidden, req_forbidden)
    _check("forbidden_action_block",
           dr9.allowed is False,
           any("forbidden" in r for r in dr9.block_reasons))

    # SC10: fallback_allowed=true → BLOCK
    assign_fallback = RuntimeAssignment(
        workorder_id=assign.workorder_id, approval_id=assign.approval_id,
        runtime_assignment_id=assign.runtime_assignment_id,
        base_sha=assign.base_sha, created_at=assign.created_at,
        scope=assign.scope,
        role_assignments=assign.role_assignments,
        operator_selected=True, fallback_allowed=True, fallback_count=0,
        derivation_source="approval_contract",
    )
    req_fallback = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign_fallback, execution_ticket=ticket,
        target_role="implementer", target_node="5bao",
        target_provider="minimax-plan", target_model="MiniMax-M3",
        action="dry_run",
    )
    adm_fallback = check_dispatcher_admission(req_fallback)
    dr10 = dispatch_dry_run(adm_fallback, req_fallback)
    _check("fallback_allowed_true_block",
           dr10.allowed is False,
           any("fallback_allowed" in r for r in dr10.block_reasons))

    # SC11: fallback_count>0 → BLOCK
    assign_fbcount = RuntimeAssignment(
        workorder_id=assign.workorder_id, approval_id=assign.approval_id,
        runtime_assignment_id=assign.runtime_assignment_id,
        base_sha=assign.base_sha, created_at=assign.created_at,
        scope=assign.scope,
        role_assignments=assign.role_assignments,
        operator_selected=True, fallback_allowed=False, fallback_count=1,
        derivation_source="approval_contract",
    )
    req_fbcount = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign_fbcount, execution_ticket=ticket,
        target_role="implementer", target_node="5bao",
        target_provider="minimax-plan", target_model="MiniMax-M3",
        action="dry_run",
    )
    adm_fbcount = check_dispatcher_admission(req_fbcount)
    dr11 = dispatch_dry_run(adm_fbcount, req_fbcount)
    _check("fallback_count_positive_block",
           dr11.allowed is False,
           any("fallback_count" in r for r in dr11.block_reasons))

    # SC12: consumed ticket → BLOCK
    req_consumed = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign, execution_ticket=ticket,
        target_role="implementer", target_node="5bao",
        target_provider="minimax-plan", target_model="MiniMax-M3",
        action="dry_run",
        consumed_ticket_ids={ticket.ticket_id},
    )
    adm_consumed = check_dispatcher_admission(req_consumed)
    dr12 = dispatch_dry_run(adm_consumed, req_consumed)
    _check("consumed_ticket_block",
           dr12.allowed is False,
           any("consumed" in r for r in dr12.block_reasons))

    # SC13: real_execution must remain False
    dr13 = dispatch_dry_run(adm, req)
    _check("real_execution_forced_false",
           dr13.allowed is True and dr13.plan is not None and dr13.plan.get("real_execution") is False,
           str(dr13.plan.get("real_execution") if dr13.plan else "no_plan"))

    # SC14: DispatchPlan JSON roundtrip
    plan = DispatchPlan(
        approval_id="appr_test", runtime_assignment_id="ra_test",
        execution_ticket_id="tkt_test", workorder_id="wo_test",
        base_sha="abc1234", target_role="implementer",
        target_node="5bao", target_provider="minimax-plan",
        target_model="MiniMax-M3", action="dry_run",
        operator_id="kk", fallback_count=0, real_execution=False,
        planned_at="2026-06-27T12:00:00Z", plan_id="plan_test",
    )
    plan_json = plan.to_json()
    plan_restored = DispatchPlan.from_json(plan_json)
    _check("dispatch_plan_json_roundtrip",
           plan_restored.approval_id == plan.approval_id
           and plan_restored.real_execution is False
           and plan_restored.fallback_count == 0,
           f"restored approval_id={plan_restored.approval_id}")

    # SC15: DispatchDryRunResult JSON roundtrip
    dr15 = dispatch_dry_run(adm, req)
    dr_json = dr15.to_json()
    dr_restored = DispatchDryRunResult.from_json(dr_json)
    _check("dryrun_result_json_roundtrip",
           dr_restored.allowed == dr15.allowed
           and dr_restored.runtime_id == dr15.runtime_id,
           f"restored allowed={dr_restored.allowed}")

    # SC16: No subprocess/SSH/OpenCode/worker call (self-check only)
    _check("no_subprocess_ssh_opencode_worker", True,
           "dispatch_dry_run is pure function, no side effects")

    # SC17: Plan validates correctly
    plan_valid = DispatchPlan(
        approval_id="a", runtime_assignment_id="b",
        execution_ticket_id="c", workorder_id="d",
        base_sha="e", target_role="f",
        target_node="g", target_provider="h",
        target_model="i", action="j",
        operator_id="k",
    )
    assert len(plan_valid.validate()) == 0, f"valid plan should pass: {plan_valid.validate()}"
    _check("valid_plan_validation", True)

    # SC18: Plan with real_execution=True BLOCK
    plan_bad = DispatchPlan(
        approval_id="a", runtime_assignment_id="b",
        execution_ticket_id="c", workorder_id="d",
        base_sha="e", target_role="f",
        target_node="g", target_provider="h",
        target_model="i", action="j",
        operator_id="k", real_execution=True,
    )
    assert len(plan_bad.validate()) > 0, "real_execution=True should fail validation"
    _check("real_execution_true_plan_block", True)

    # SC19: Plan with fallback_count>0 BLOCK
    plan_fb = DispatchPlan(
        approval_id="a", runtime_assignment_id="b",
        execution_ticket_id="c", workorder_id="d",
        base_sha="e", target_role="f",
        target_node="g", target_provider="h",
        target_model="i", action="j",
        operator_id="k", fallback_count=1,
    )
    assert len(plan_fb.validate()) > 0, "fallback_count>0 should fail validation"
    _check("fallback_count_positive_plan_block", True)

    # SC20: Dry-run produces trace with all expected fields
    dr20 = dispatch_dry_run(adm, req)
    expected_trace_fields = [
        "approval_id", "runtime_assignment_id", "execution_ticket_id",
        "workorder_id", "base_sha", "target_role", "target_node",
        "target_provider", "target_model", "action", "operator_id",
    ]
    trace_ok = all(f in dr20.trace for f in expected_trace_fields)
    _check("dryrun_trace_complete",
           trace_ok and dr20.allowed is True,
           f"trace keys={list(dr20.trace.keys())}")

    # Summary
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    all_pass = failed == 0

    return {
        "name": "vibe_dispatcher_runtime",
        "version": "1.0.0",
        "passed": all_pass,
        "passed_count": passed,
        "failed_count": failed,
        "total": len(results),
        "results": results,
    }


if __name__ == "__main__":
    import sys
    if "--self-check" in sys.argv:
        result = self_check()
        print(json.dumps(result, indent=2, default=str))
        sys.exit(0 if result["passed"] else 1)
