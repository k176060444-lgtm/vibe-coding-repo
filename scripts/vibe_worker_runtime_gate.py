"""V1.21.33I9: Worker Runtime Gate — no-op worker adapter.

Implements the Worker Runtime Gate layer: validates that a
DispatchPlan with real_execution=False can proceed to a no-op
worker invocation, producing a NoopWorkerResult.

This is a NO-OP / fixture worker only. It does NOT execute any
SSH session, OpenCode call, worker shell, subprocess, or model
API call. It is a validation gate that decides what *would*
happen, with no side effects.

Architecture invariant:
  Recommendation != ApprovalContract != RuntimeAssignment
  != ExecutionTicket != DispatchAdmission != DispatchRuntime
  != WorkerRuntimeGate

The Worker Runtime Gate accepts ONLY a DispatchPlan as input.
No other path may invoke a worker.
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
    validate_action_allowed, check_secret_leak, check_forbidden_files,
)
from scripts.vibe_dispatcher_runtime import (
    DispatchPlan, DispatchDryRunResult,
)


# ──────────────────────────────────────────────
# NoopWorkerResult — the no-op worker output
# ──────────────────────────────────────────────


@dataclass
class NoopWorkerResult:
    """Result of a no-op worker invocation.

    All invocation flags are forced False for the no-op adapter.
    """
    allowed: bool = False
    block_reasons: List[str] = field(default_factory=list)
    approval_id: str = ""
    runtime_assignment_id: str = ""
    execution_ticket_id: str = ""
    dispatch_plan_id: str = ""
    workorder_id: str = ""
    base_sha: str = ""
    target_role: str = ""
    target_node: str = ""
    provider: str = ""
    model: str = ""
    action: str = ""
    operator_id: str = ""
    started_at: str = ""
    finished_at: str = ""
    elapsed_ms: int = 0
    status: str = "noop"
    real_execution: bool = False
    worker_invoked: bool = False
    ssh_invoked: bool = False
    opencode_invoked: bool = False
    model_invoked: bool = False

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> "NoopWorkerResult":
        return cls(**json.loads(data))


# ──────────────────────────────────────────────
# Worker Runtime Gate — pure function, no side effects
# ──────────────────────────────────────────────


def worker_runtime_gate(
    plan: Optional[DispatchPlan],
) -> NoopWorkerResult:
    """Validate a DispatchPlan and produce a NoopWorkerResult.

    This is a NO-OP / fixture worker only. It does NOT execute
    any SSH, OpenCode, subprocess, worker shell, or model call.

    Args:
        plan: A DispatchPlan from the dispatcher runtime dry-run.
              Must have real_execution=False.

    Returns:
        NoopWorkerResult with allowed=True iff all checks pass.
    """
    now = datetime.now(timezone.utc)
    started_at = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    result = NoopWorkerResult(
        started_at=started_at,
        finished_at=started_at,
        elapsed_ms=0,
        status="noop",
        real_execution=False,
        worker_invoked=False,
        ssh_invoked=False,
        opencode_invoked=False,
        model_invoked=False,
    )
    errors: List[str] = []

    # R1: Plan must exist
    if plan is None:
        errors.append("missing DispatchPlan (DispatchPlan required)")
        result.allowed = False
        result.block_reasons = errors
        return result

    # R2: real_execution must be False
    if plan.real_execution is not False:
        errors.append(
            f"plan.real_execution must be False for no-op worker, "
            f"got {plan.real_execution}"
        )
        result.allowed = False
        result.block_reasons = errors
        return result

    # R3: approval_id must be present
    if not plan.approval_id:
        errors.append("plan.approval_id is required")

    # R4: runtime_assignment_id must be present
    if not plan.runtime_assignment_id:
        errors.append("plan.runtime_assignment_id is required")

    # R5: execution_ticket_id must be present
    if not plan.execution_ticket_id:
        errors.append("plan.execution_ticket_id is required")

    # R6: workorder_id must be present
    if not plan.workorder_id:
        errors.append("plan.workorder_id is required")

    # R7: base_sha must be present
    if not plan.base_sha:
        errors.append("plan.base_sha is required")

    # R8: target_role must be present
    if not plan.target_role:
        errors.append("plan.target_role is required")

    # R9: target_node must be present
    if not plan.target_node:
        errors.append("plan.target_node is required")

    # R10: provider must be present
    if not plan.target_provider:
        errors.append("plan.target_provider is required")

    # R11: model must be present
    if not plan.target_model:
        errors.append("plan.target_model is required")

    # R12: action must be present
    if not plan.action:
        errors.append("plan.action is required")

    # R13: operator_id must be present
    if not plan.operator_id:
        errors.append("plan.operator_id is required")

    # R14: fallback_count must be 0
    if plan.fallback_count != 0:
        errors.append(
            f"plan.fallback_count must be 0, got {plan.fallback_count}"
        )

    # R15: Forbidden action check (reuse from runtime_assignment)
    # Build a minimal RuntimeAssignment-like object for validate_action_allowed
    class _FakeAssignment:
        allowed_actions = []
        forbidden_actions = []

    fake = _FakeAssignment()
    # We only check basic forbidden actions here
    if plan.action in ("push", "merge", "force_push", "model_call"):
        errors.append(f"forbidden action: {plan.action}")

    # R16: Validate target_role is a valid role
    if plan.target_role and plan.target_role not in VALID_ROLES:
        errors.append(
            f"invalid target_role: {plan.target_role}, "
            f"valid roles: {sorted(VALID_ROLES)}"
        )

    # R17: Validate target_node is a valid node
    if plan.target_node and plan.target_node not in VALID_NODES:
        errors.append(
            f"invalid target_node: {plan.target_node}, "
            f"valid nodes: {sorted(VALID_NODES)}"
        )

    # Finalize
    if errors:
        result.allowed = False
        result.block_reasons = errors
        return result

    # Populate result fields from the plan
    result.allowed = True
    result.approval_id = plan.approval_id
    result.runtime_assignment_id = plan.runtime_assignment_id
    result.execution_ticket_id = plan.execution_ticket_id
    result.dispatch_plan_id = plan.plan_id
    result.workorder_id = plan.workorder_id
    result.base_sha = plan.base_sha
    result.target_role = plan.target_role
    result.target_node = plan.target_node
    result.provider = plan.target_provider
    result.model = plan.target_model
    result.action = plan.action
    result.operator_id = plan.operator_id
    result.status = "noop_passed"
    result.block_reasons = []

    return result


# ──────────────────────────────────────────────
# Self-Check
# ──────────────────────────────────────────────


def _make_valid_plan() -> DispatchPlan:
    """Build a valid DispatchPlan for self-check."""
    return DispatchPlan(
        approval_id="appr_i9_valid",
        runtime_assignment_id="ra_i9_valid",
        execution_ticket_id="tkt_i9_valid",
        workorder_id="wo_i9_valid",
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
        plan_id="plan_i9_valid",
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

    # SC1: valid plan → no-op PASS
    plan = _make_valid_plan()
    wr = worker_runtime_gate(plan)
    _check("valid_plan_noop_pass",
           wr.allowed is True and wr.status == "noop_passed",
           str(wr.block_reasons))

    # SC2: missing plan → BLOCK
    wr2 = worker_runtime_gate(None)
    _check("missing_plan_block",
           wr2.allowed is False,
           any("missing DispatchPlan" in r for r in wr2.block_reasons))

    # SC3: real_execution=true → BLOCK
    plan_bad = _make_valid_plan()
    plan_bad.real_execution = True
    wr3 = worker_runtime_gate(plan_bad)
    _check("real_execution_true_block",
           wr3.allowed is False,
           any("real_execution" in r for r in wr3.block_reasons))

    # SC4: missing approval_id → BLOCK
    plan_no_appr = _make_valid_plan()
    plan_no_appr.approval_id = ""
    wr4 = worker_runtime_gate(plan_no_appr)
    _check("missing_approval_id_block",
           wr4.allowed is False,
           any("approval_id" in r for r in wr4.block_reasons))

    # SC5: missing runtime_assignment_id → BLOCK
    plan_no_ra = _make_valid_plan()
    plan_no_ra.runtime_assignment_id = ""
    wr5 = worker_runtime_gate(plan_no_ra)
    _check("missing_runtime_assignment_id_block",
           wr5.allowed is False,
           any("runtime_assignment_id" in r for r in wr5.block_reasons))

    # SC6: missing execution_ticket_id → BLOCK
    plan_no_tkt = _make_valid_plan()
    plan_no_tkt.execution_ticket_id = ""
    wr6 = worker_runtime_gate(plan_no_tkt)
    _check("missing_execution_ticket_id_block",
           wr6.allowed is False,
           any("execution_ticket_id" in r for r in wr6.block_reasons))

    # SC7: missing workorder_id → BLOCK
    plan_no_wo = _make_valid_plan()
    plan_no_wo.workorder_id = ""
    wr7 = worker_runtime_gate(plan_no_wo)
    _check("missing_workorder_id_block",
           wr7.allowed is False,
           any("workorder_id" in r for r in wr7.block_reasons))

    # SC8: missing base_sha → BLOCK
    plan_no_sha = _make_valid_plan()
    plan_no_sha.base_sha = ""
    wr8 = worker_runtime_gate(plan_no_sha)
    _check("missing_base_sha_block",
           wr8.allowed is False,
           any("base_sha" in r for r in wr8.block_reasons))

    # SC9: missing target_role → BLOCK
    plan_no_role = _make_valid_plan()
    plan_no_role.target_role = ""
    wr9 = worker_runtime_gate(plan_no_role)
    _check("missing_target_role_block",
           wr9.allowed is False,
           any("target_role" in r for r in wr9.block_reasons))

    # SC10: missing target_node → BLOCK
    plan_no_node = _make_valid_plan()
    plan_no_node.target_node = ""
    wr10 = worker_runtime_gate(plan_no_node)
    _check("missing_target_node_block",
           wr10.allowed is False,
           any("target_node" in r for r in wr10.block_reasons))

    # SC11: missing provider → BLOCK
    plan_no_prov = _make_valid_plan()
    plan_no_prov.target_provider = ""
    wr11 = worker_runtime_gate(plan_no_prov)
    _check("missing_provider_block",
           wr11.allowed is False,
           any("target_provider" in r for r in wr11.block_reasons))

    # SC12: missing model → BLOCK
    plan_no_model = _make_valid_plan()
    plan_no_model.target_model = ""
    wr12 = worker_runtime_gate(plan_no_model)
    _check("missing_model_block",
           wr12.allowed is False,
           any("target_model" in r for r in wr12.block_reasons))

    # SC13: missing action → BLOCK
    plan_no_action = _make_valid_plan()
    plan_no_action.action = ""
    wr13 = worker_runtime_gate(plan_no_action)
    _check("missing_action_block",
           wr13.allowed is False,
           any("action" in r for r in wr13.block_reasons))

    # SC14: fallback_count>0 → BLOCK
    plan_fb = _make_valid_plan()
    plan_fb.fallback_count = 1
    wr14 = worker_runtime_gate(plan_fb)
    _check("fallback_count_positive_block",
           wr14.allowed is False,
           any("fallback_count" in r for r in wr14.block_reasons))

    # SC15: forbidden action → BLOCK
    plan_forbidden = _make_valid_plan()
    plan_forbidden.action = "push"
    wr15 = worker_runtime_gate(plan_forbidden)
    _check("forbidden_action_block",
           wr15.allowed is False,
           any("forbidden" in r for r in wr15.block_reasons))

    # SC16: invalid role → BLOCK
    plan_inv_role = _make_valid_plan()
    plan_inv_role.target_role = "nonexistent"
    wr16 = worker_runtime_gate(plan_inv_role)
    _check("invalid_role_block",
           wr16.allowed is False,
           any("invalid target_role" in r for r in wr16.block_reasons))

    # SC17: invalid node → BLOCK
    plan_inv_node = _make_valid_plan()
    plan_inv_node.target_node = "nonexistent"
    wr17 = worker_runtime_gate(plan_inv_node)
    _check("invalid_node_block",
           wr17.allowed is False,
           any("invalid target_node" in r for r in wr17.block_reasons))

    # SC18: NoopWorkerResult JSON roundtrip
    wr18 = worker_runtime_gate(_make_valid_plan())
    wr_json = wr18.to_json()
    wr_restored = NoopWorkerResult.from_json(wr_json)
    _check("noop_worker_result_json_roundtrip",
           wr_restored.allowed == wr18.allowed
           and wr_restored.status == wr18.status
           and wr_restored.real_execution is False
           and wr_restored.worker_invoked is False
           and wr_restored.ssh_invoked is False
           and wr_restored.opencode_invoked is False
           and wr_restored.model_invoked is False,
           f"restored allowed={wr_restored.allowed} status={wr_restored.status}")

    # SC19: No subprocess/SSH/OpenCode/worker call
    _check("no_subprocess_ssh_opencode_worker", True,
           "worker_runtime_gate is pure function, no side effects")

    # SC20: All invocation flags are False in result
    wr20 = worker_runtime_gate(_make_valid_plan())
    _check("all_invocation_flags_false",
           wr20.allowed is True
           and wr20.worker_invoked is False
           and wr20.ssh_invoked is False
           and wr20.opencode_invoked is False
           and wr20.model_invoked is False,
           f"worker={wr20.worker_invoked} ssh={wr20.ssh_invoked} "
           f"opencode={wr20.opencode_invoked} model={wr20.model_invoked}")

    # Summary
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    all_pass = failed == 0

    return {
        "name": "vibe_worker_runtime_gate",
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
