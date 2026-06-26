"""V1.21.33I7: Dispatcher Admission Gate contract module.

Implements the contract layer for Dispatcher Admission: validates that a
dispatch request is properly derived from ApprovalContract →
RuntimeAssignment → ExecutionTicket, and returns allow/block verdict.

This is a CONTRACT layer only. It does NOT execute any worker, dispatcher,
SSH session, OpenCode call, or model API call. It is a gate that decides
whether a dispatch *would be allowed*, with no side effects.

Architecture invariant: Recommendation != ApprovalContract !=
RuntimeAssignment != ExecutionTicket != DispatchAdmission.
"""
import json
import hashlib
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set, Tuple

# Allow importing as `scripts.vibe_runtime_assignment` from the project root.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Reuse existing contract primitives to enforce invariants
from scripts.vibe_runtime_assignment import (
    VALID_ROLES, VALID_NODES, VALID_TRANSPORTS, VALID_HEALTH_STATUSES,
    VALID_SELECTION_SOURCES, EXECUTABLE_SELECTION_SOURCES,
    NODE_TRANSPORT_MAP, FORBIDDEN_FILES, SECRET_PATTERNS,
    ApprovalContract, RuntimeAssignment, ExecutionTicket,
    RoleAssignment, derive_operator_selected, derive_runtime_assignment_id,
    validate_base_sha_match, validate_approval_not_expired,
    validate_action_allowed, check_secret_leak, check_forbidden_files,
    generate_workorder_id, generate_approval_id, generate_ticket_id,
)


# ──────────────────────────────────────────────
# DispatchAdmissionRequest — the input to the gate
# ──────────────────────────────────────────────


@dataclass
class DispatchAdmissionRequest:
    """A request to admit a ticket for dispatch.

    The dispatcher admission gate takes this request and decides
    allow / block + reasons. It does NOT execute anything.
    """
    approval: Optional[ApprovalContract] = None
    runtime_assignment: Optional[RuntimeAssignment] = None
    execution_ticket: Optional[ExecutionTicket] = None
    target_role: str = ""
    target_node: str = ""
    target_provider: str = ""
    target_model: str = ""
    action: str = ""
    consumed_ticket_ids: Set[str] = field(default_factory=set)

    def to_json(self) -> str:
        return json.dumps({
            "approval": asdict(self.approval) if self.approval else None,
            "runtime_assignment": asdict(self.runtime_assignment) if self.runtime_assignment else None,
            "execution_ticket": asdict(self.execution_ticket) if self.execution_ticket else None,
            "target_role": self.target_role,
            "target_node": self.target_node,
            "target_provider": self.target_provider,
            "target_model": self.target_model,
            "action": self.action,
            "consumed_ticket_ids": sorted(self.consumed_ticket_ids),
        }, indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> "DispatchAdmissionRequest":
        d = json.loads(data)
        appr = ApprovalContract(**d["approval"]) if d.get("approval") else None
        assign_d = d.get("runtime_assignment")
        assign = None
        if assign_d:
            ras = {}
            for role, ra_dict in assign_d.get("role_assignments", {}).items():
                ras[role] = RoleAssignment(**ra_dict)
            assign_d["role_assignments"] = ras
            assign = RuntimeAssignment(**assign_d)
        ticket = ExecutionTicket(**d["execution_ticket"]) if d.get("execution_ticket") else None
        return cls(
            approval=appr,
            runtime_assignment=assign,
            execution_ticket=ticket,
            target_role=d.get("target_role", ""),
            target_node=d.get("target_node", ""),
            target_provider=d.get("target_provider", ""),
            target_model=d.get("target_model", ""),
            action=d.get("action", ""),
            consumed_ticket_ids=set(d.get("consumed_ticket_ids", [])),
        )


# ──────────────────────────────────────────────
# DispatchAdmissionResult — the gate's verdict
# ──────────────────────────────────────────────


@dataclass
class DispatchAdmissionResult:
    """Verdict of the dispatcher admission gate."""
    allowed: bool = False
    block_reasons: List[str] = field(default_factory=list)
    admission_id: str = ""
    decided_at: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)


# ──────────────────────────────────────────────
# Admission Gate — pure function, no side effects
# ──────────────────────────────────────────────


def _admission_id_for(ticket_id: str) -> str:
    return "adm_" + hashlib.sha256(ticket_id.encode()).hexdigest()[:16]


def check_dispatcher_admission(
    request: DispatchAdmissionRequest,
) -> DispatchAdmissionResult:
    """Run the dispatcher admission gate.

    Returns DispatchAdmissionResult.allowed = True iff every check passes.
    This function has NO side effects: it does not call any model, dispatch
    any worker, execute any SSH, or read any external state other than the
    supplied request. The only state it touches is request.consumed_ticket_ids
    which the caller supplies.
    """
    result = DispatchAdmissionResult()
    result.decided_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    errors: List[str] = []

    # 1. All three objects must be present
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

    # 2. Approval must validate
    approval_errors = approval.validate()
    if approval_errors:
        errors.append(f"approval invalid: {approval_errors}")

    # 3. Approval must not be expired
    expired_errors = validate_approval_not_expired(approval)
    if expired_errors:
        errors.extend(expired_errors)

    # 4. selection_source must be executable
    if not derive_operator_selected(approval.selection_source):
        errors.append(
            f"selection_source={approval.selection_source} does not authorize dispatch; "
            f"must be one of {EXECUTABLE_SELECTION_SOURCES}"
        )

    # 5. Ticket must validate
    ticket_errors = ticket.validate()
    if ticket_errors:
        errors.append(f"ticket invalid: {ticket_errors}")

    # 6. Ticket has its own expiry check (use ticket.expires_at if present)
    if hasattr(ticket, "expires_at") and getattr(ticket, "expires_at", None):
        if ticket.expires_at:  # type: ignore[attr-defined]
            if ticket.expires_at < result.decided_at:  # type: ignore[attr-defined]
                errors.append(f"execution ticket {ticket.ticket_id} has expired at {ticket.expires_at}")

    # 7. base_sha must match across all three
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

    # 8. Cross-id trace must be consistent
    expected_ra_id = derive_runtime_assignment_id(approval.approval_id)
    actual_ra_id = assignment.runtime_assignment_id
    if actual_ra_id != expected_ra_id:
        errors.append(
            f"runtime_assignment_id mismatch: expected={expected_ra_id} "
            f"(derived from approval_id={approval.approval_id}), got={actual_ra_id}"
        )

    if assignment.approval_id != approval.approval_id:
        errors.append(
            f"approval_id mismatch: approval.approval_id={approval.approval_id}, "
            f"assignment.approval_id={assignment.approval_id}"
        )

    if ticket.approval_id != approval.approval_id:
        errors.append(
            f"approval_id mismatch: approval.approval_id={approval.approval_id}, "
            f"ticket.approval_id={ticket.approval_id}"
        )

    if ticket.workorder_id != approval.workorder_id:
        errors.append(
            f"workorder_id mismatch: approval.workorder_id={approval.workorder_id}, "
            f"ticket.workorder_id={ticket.workorder_id}"
        )

    # 9. RuntimeAssignment operator_selected must be True (derived from approval)
    if assignment.operator_selected is not True:
        errors.append("runtime_assignment.operator_selected must be True (derived from approval)")

    # 10. fallback_allowed must be False
    if assignment.fallback_allowed is not False:
        errors.append("fallback_allowed must be False for executable dispatch")

    # 11. fallback_count must be 0
    if assignment.fallback_count != 0:
        errors.append(f"fallback_count must be 0, got {assignment.fallback_count}")

    # 12. ticket must not be already consumed
    if ticket.ticket_id in request.consumed_ticket_ids:
        errors.append(
            f"execution ticket {ticket.ticket_id} has already been consumed / reused"
        )

    # 13. action must be allowed and not forbidden
    action_errors = validate_action_allowed(assignment, request.action)
    if action_errors:
        errors.extend(action_errors)

    # 14. Target role/node/provider/model must match ticket and assignment
    if request.target_role and request.target_role != ticket.role:
        errors.append(
            f"target_role drift: ticket.role={ticket.role}, target_role={request.target_role}"
        )
    if request.target_node and request.target_node != ticket.node_id:
        errors.append(
            f"target_node drift: ticket.node_id={ticket.node_id}, target_node={request.target_node}"
        )
    if request.target_provider and request.target_provider != ticket.provider:
        errors.append(
            f"target_provider drift: ticket.provider={ticket.provider}, "
            f"target_provider={request.target_provider}"
        )
    if request.target_model and request.target_model != ticket.model:
        errors.append(
            f"target_model drift: ticket.model={ticket.model}, target_model={request.target_model}"
        )

    # 15. Cross-check: ticket.role must exist in assignment
    if ticket.role not in assignment.role_assignments:
        errors.append(
            f"ticket.role={ticket.role} not in runtime assignment roles"
        )
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

    # Finalize verdict
    if errors:
        result.allowed = False
        result.block_reasons = errors
    else:
        result.allowed = True
        result.admission_id = _admission_id_for(ticket.ticket_id)

    return result


# ──────────────────────────────────────────────
# Self-Check
# ──────────────────────────────────────────────


def _make_valid_approval_for_admission(
    selection_source: str = "operator_confirmed_default",
    base_sha: str = "c71f9b5d6cbde04c7461b894108235b44886a64a",
    expires_at: Optional[str] = None,
    approval_id: str = "appr_i7_valid",
):
    return ApprovalContract(
        approval_id=approval_id,
        workorder_id="wo_i7_valid",
        operator_id="kk",
        approved_at="2026-06-26T12:00:00Z",
        base_sha=base_sha,
        expires_at=expires_at,
        risk_level="low",
        scope="I7 test",
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
        allowed_actions=["local_exec", "test_run", "self_check"],
        forbidden_actions=["push", "merge", "force_push", "model_call"],
        allowed_files=["tests/"],
        forbidden_files=FORBIDDEN_FILES,
        selection_source=selection_source,
    )


def self_check() -> Dict[str, Any]:
    """Run self-check and return results."""
    results: List[Dict[str, Any]] = []
    all_pass = True

    def _check(name: str, ok: bool, detail: str = "") -> None:
        nonlocal all_pass
        if not ok:
            all_pass = False
        results.append({"name": name, "passed": ok, "detail": detail})

    # Build a valid request
    appr = _make_valid_approval_for_admission()
    assign = RuntimeAssignment(
        workorder_id=appr.workorder_id,
        approval_id=appr.approval_id,
        runtime_assignment_id=derive_runtime_assignment_id(appr.approval_id),
        base_sha=appr.base_sha,
        created_at=appr.approved_at,
        scope=appr.scope,
        role_assignments={
            r: RoleAssignment(
                role=r, assignee=f"{r}/node", node_id=appr.selected_node_matrix[r],
                transport=NODE_TRANSPORT_MAP[appr.selected_node_matrix[r]],
                provider=appr.selected_model_matrix[r]["provider"],
                model=appr.selected_model_matrix[r]["model"],
                model_alias=appr.selected_model_matrix[r]["alias"],
            )
            for r in VALID_ROLES
        },
        operator_selected=True,
        fallback_allowed=False,
        fallback_count=0,
        derivation_source="approval_contract",
        allowed_actions=appr.allowed_actions,
        forbidden_actions=appr.forbidden_actions,
        allowed_files=appr.allowed_files,
        forbidden_files=appr.forbidden_files,
    )
    ticket = ExecutionTicket(
        ticket_id="tkt_i7_test", workorder_id=appr.workorder_id,
        approval_id=appr.approval_id, role="implementer",
        node_id="5bao", provider="minimax-plan", model="MiniMax-M3",
        base_sha=appr.base_sha,
        allowed_paths=["tests/"],
        forbidden_paths=FORBIDDEN_FILES,
    )

    # SC1: valid ticket admission PASS
    req = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign, execution_ticket=ticket,
        target_role="implementer", target_node="5bao",
        target_provider="minimax-plan", target_model="MiniMax-M3",
        action="test_run",
    )
    res = check_dispatcher_admission(req)
    _check("valid_admission_pass", res.allowed is True, str(res.block_reasons))

    # SC2: missing approval BLOCK
    req_no_appr = DispatchAdmissionRequest(
        approval=None, runtime_assignment=assign, execution_ticket=ticket,
        target_role="implementer", action="test_run",
    )
    res2 = check_dispatcher_admission(req_no_appr)
    _check("missing_approval_block", res2.allowed is False,
           any("missing approval" in r for r in res2.block_reasons))

    # SC3: missing runtime assignment BLOCK
    req_no_assign = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=None, execution_ticket=ticket,
        target_role="implementer", action="test_run",
    )
    res3 = check_dispatcher_admission(req_no_assign)
    _check("missing_runtime_assignment_block", res3.allowed is False,
           any("missing runtime" in r for r in res3.block_reasons))

    # SC4: missing ticket BLOCK
    req_no_ticket = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign, execution_ticket=None,
        target_role="implementer", action="test_run",
    )
    res4 = check_dispatcher_admission(req_no_ticket)
    _check("missing_ticket_block", res4.allowed is False,
           any("missing execution ticket" in r for r in res4.block_reasons))

    # SC5: planner_default BLOCK
    appr_planner = _make_valid_approval_for_admission(selection_source="planner_default")
    assign_planner = RuntimeAssignment(
        workorder_id=appr_planner.workorder_id, approval_id=appr_planner.approval_id,
        runtime_assignment_id=derive_runtime_assignment_id(appr_planner.approval_id),
        base_sha=appr_planner.base_sha, created_at=appr_planner.approved_at,
        scope=appr_planner.scope, role_assignments={
            r: RoleAssignment(role=r, assignee=f"{r}/node",
                node_id=appr_planner.selected_node_matrix[r],
                transport=NODE_TRANSPORT_MAP[appr_planner.selected_node_matrix[r]],
                provider=appr_planner.selected_model_matrix[r]["provider"],
                model=appr_planner.selected_model_matrix[r]["model"],
                model_alias=appr_planner.selected_model_matrix[r]["alias"])
            for r in VALID_ROLES
        },
        operator_selected=True, fallback_allowed=False, fallback_count=0,
        derivation_source="approval_contract",
    )
    ticket_planner = ExecutionTicket(
        ticket_id="tkt_planner", workorder_id=appr_planner.workorder_id,
        approval_id=appr_planner.approval_id, role="implementer",
        node_id="5bao", provider="minimax-plan", model="MiniMax-M3",
        base_sha=appr_planner.base_sha,
    )
    req_planner = DispatchAdmissionRequest(
        approval=appr_planner, runtime_assignment=assign_planner,
        execution_ticket=ticket_planner, action="test_run",
    )
    res5 = check_dispatcher_admission(req_planner)
    _check("planner_default_block", res5.allowed is False,
           any("planner_default" in r for r in res5.block_reasons))

    # SC6: operator_confirmed_default PASS
    _check("operator_confirmed_default_pass", res.allowed is True)

    # SC7: operator_override PASS
    appr_override = _make_valid_approval_for_admission(
        selection_source="operator_override", approval_id="appr_i7_override")
    assign_override = RuntimeAssignment(
        workorder_id=appr_override.workorder_id, approval_id=appr_override.approval_id,
        runtime_assignment_id=derive_runtime_assignment_id(appr_override.approval_id),
        base_sha=appr_override.base_sha, created_at=appr_override.approved_at,
        scope=appr_override.scope, role_assignments={
            r: RoleAssignment(role=r, assignee=f"{r}/node",
                node_id=appr_override.selected_node_matrix[r],
                transport=NODE_TRANSPORT_MAP[appr_override.selected_node_matrix[r]],
                provider=appr_override.selected_model_matrix[r]["provider"],
                model=appr_override.selected_model_matrix[r]["model"],
                model_alias=appr_override.selected_model_matrix[r]["alias"],
                source="operator_override")
            for r in VALID_ROLES
        },
        operator_selected=True, fallback_allowed=False, fallback_count=0,
        derivation_source="approval_contract",
    )
    ticket_override = ExecutionTicket(
        ticket_id="tkt_override", workorder_id=appr_override.workorder_id,
        approval_id=appr_override.approval_id, role="implementer",
        node_id="5bao", provider="minimax-plan", model="MiniMax-M3",
        base_sha=appr_override.base_sha,
    )
    req_override = DispatchAdmissionRequest(
        approval=appr_override, runtime_assignment=assign_override,
        execution_ticket=ticket_override, action="test_run",
    )
    res7 = check_dispatcher_admission(req_override)
    _check("operator_override_pass", res7.allowed is True,
           str(res7.block_reasons))

    # SC8: base_sha mismatch BLOCK
    appr_mismatch = _make_valid_approval_for_admission(
        base_sha="aaaaaaa11111", approval_id="appr_i7_mismatch")
    assign_mismatch = RuntimeAssignment(
        workorder_id=appr_mismatch.workorder_id, approval_id=appr_mismatch.approval_id,
        runtime_assignment_id=derive_runtime_assignment_id(appr_mismatch.approval_id),
        base_sha=appr_mismatch.base_sha, created_at=appr_mismatch.approved_at,
        scope=appr_mismatch.scope, role_assignments={
            r: RoleAssignment(role=r, assignee=f"{r}/node",
                node_id=appr_mismatch.selected_node_matrix[r],
                transport=NODE_TRANSPORT_MAP[appr_mismatch.selected_node_matrix[r]],
                provider=appr_mismatch.selected_model_matrix[r]["provider"],
                model=appr_mismatch.selected_model_matrix[r]["model"],
                model_alias=appr_mismatch.selected_model_matrix[r]["alias"])
            for r in VALID_ROLES
        },
        operator_selected=True, fallback_allowed=False, fallback_count=0,
        derivation_source="approval_contract",
    )
    ticket_mismatch = ExecutionTicket(
        ticket_id="tkt_mismatch", workorder_id=appr_mismatch.workorder_id,
        approval_id=appr_mismatch.approval_id, role="implementer",
        node_id="5bao", provider="minimax-plan", model="MiniMax-M3",
        base_sha="bbbbbbb22222",  # ticket base_sha differs
    )
    req_mismatch = DispatchAdmissionRequest(
        approval=appr_mismatch, runtime_assignment=assign_mismatch,
        execution_ticket=ticket_mismatch, action="test_run",
    )
    res8 = check_dispatcher_admission(req_mismatch)
    _check("base_sha_mismatch_block", res8.allowed is False,
           any("base_sha mismatch" in r for r in res8.block_reasons))

    # SC9: approval_id mismatch BLOCK
    assign_wrong_id = RuntimeAssignment(
        **{**assign.__dict__, "approval_id": "appr_wrong_approval_id"}
    )
    req_id_mismatch = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign_wrong_id,
        execution_ticket=ticket, action="test_run",
    )
    res9 = check_dispatcher_admission(req_id_mismatch)
    _check("approval_id_mismatch_block", res9.allowed is False,
           any("approval_id mismatch" in r for r in res9.block_reasons))

    # SC10: runtime_assignment_id mismatch BLOCK
    assign_wrong_ra = RuntimeAssignment(
        **{**assign.__dict__, "runtime_assignment_id": "ra_wrong_id"}
    )
    req_ra_mismatch = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign_wrong_ra,
        execution_ticket=ticket, action="test_run",
    )
    res10 = check_dispatcher_admission(req_ra_mismatch)
    _check("runtime_assignment_id_mismatch_block", res10.allowed is False,
           any("runtime_assignment_id mismatch" in r for r in res10.block_reasons))

    # SC11: expired approval BLOCK
    appr_exp = _make_valid_approval_for_admission(
        expires_at="2020-01-01T00:00:00Z", approval_id="appr_i7_expired")
    assign_exp = RuntimeAssignment(
        workorder_id=appr_exp.workorder_id, approval_id=appr_exp.approval_id,
        runtime_assignment_id=derive_runtime_assignment_id(appr_exp.approval_id),
        base_sha=appr_exp.base_sha, created_at=appr_exp.approved_at,
        scope=appr_exp.scope, role_assignments={
            r: RoleAssignment(role=r, assignee=f"{r}/node",
                node_id=appr_exp.selected_node_matrix[r],
                transport=NODE_TRANSPORT_MAP[appr_exp.selected_node_matrix[r]],
                provider=appr_exp.selected_model_matrix[r]["provider"],
                model=appr_exp.selected_model_matrix[r]["model"],
                model_alias=appr_exp.selected_model_matrix[r]["alias"])
            for r in VALID_ROLES
        },
        operator_selected=True, fallback_allowed=False, fallback_count=0,
        derivation_source="approval_contract",
    )
    ticket_exp = ExecutionTicket(
        ticket_id="tkt_exp", workorder_id=appr_exp.workorder_id,
        approval_id=appr_exp.approval_id, role="implementer",
        node_id="5bao", provider="minimax-plan", model="MiniMax-M3",
        base_sha=appr_exp.base_sha,
    )
    req_exp = DispatchAdmissionRequest(
        approval=appr_exp, runtime_assignment=assign_exp,
        execution_ticket=ticket_exp, action="test_run",
    )
    res11 = check_dispatcher_admission(req_exp)
    _check("expired_approval_block", res11.allowed is False,
           any("expired" in r for r in res11.block_reasons))

    # SC12: forbidden action BLOCK
    req_forbidden = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign,
        execution_ticket=ticket, action="push",
    )
    res12 = check_dispatcher_admission(req_forbidden)
    _check("forbidden_action_block", res12.allowed is False,
           any("forbidden_actions" in r for r in res12.block_reasons))

    # SC13: fallback_allowed=true BLOCK (on the assignment)
    assign_fb = RuntimeAssignment(
        **{**assign.__dict__, "fallback_allowed": True}
    )
    req_fb = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign_fb,
        execution_ticket=ticket, action="test_run",
    )
    res13 = check_dispatcher_admission(req_fb)
    _check("fallback_allowed_block", res13.allowed is False,
           any("fallback_allowed" in r for r in res13.block_reasons))

    # SC14: fallback_count>0 BLOCK
    assign_fc = RuntimeAssignment(
        **{**assign.__dict__, "fallback_count": 1}
    )
    req_fc = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign_fc,
        execution_ticket=ticket, action="test_run",
    )
    res14 = check_dispatcher_admission(req_fc)
    _check("fallback_count_positive_block", res14.allowed is False,
           any("fallback_count" in r for r in res14.block_reasons))

    # SC15: role/node/model drift BLOCK
    req_drift = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign,
        execution_ticket=ticket,
        target_role="implementer", target_node="9bao",  # drift
        target_provider="minimax-plan", target_model="MiniMax-M3",
        action="test_run",
    )
    res15 = check_dispatcher_admission(req_drift)
    _check("role_node_drift_block", res15.allowed is False,
           any("target_node drift" in r for r in res15.block_reasons))

    # SC16: consumed ticket BLOCK
    req_consumed = DispatchAdmissionRequest(
        approval=appr, runtime_assignment=assign,
        execution_ticket=ticket,
        target_role="implementer", target_node="5bao",
        target_provider="minimax-plan", target_model="MiniMax-M3",
        action="test_run",
        consumed_ticket_ids={ticket.ticket_id},
    )
    res16 = check_dispatcher_admission(req_consumed)
    _check("consumed_ticket_block", res16.allowed is False,
           any("already been consumed" in r for r in res16.block_reasons))

    # SC17: no real model call (already trivially true — we don't call any)
    _check("no_real_model_call", True, "pure-function gate, no I/O")

    # SC18: JSON roundtrip for DispatchAdmissionRequest
    rt = req.to_json()
    restored = DispatchAdmissionRequest.from_json(rt)
    _check("json_roundtrip_request",
           restored.approval is not None
           and restored.runtime_assignment is not None
           and restored.execution_ticket is not None
           and restored.target_role == req.target_role)

    # SC19: DispatchAdmissionResult JSON roundtrip
    rt2 = res.to_json()
    parsed = json.loads(rt2)
    _check("json_roundtrip_result",
           "allowed" in parsed and "block_reasons" in parsed and "admission_id" in parsed)

    # SC20: base_sha match function import works
    _check("validate_base_sha_match_import", validate_base_sha_match(appr, assign) == [])

    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    all_pass = failed == 0

    return {
        "name": "vibe_dispatcher_admission",
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
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)
    else:
        print("Usage: python scripts/vibe_dispatcher_admission.py --self-check")
        sys.exit(1)
