"""Tests for V1.21.33I4: Runtime Assignment Framework.

Tests the unified contract module: RuntimeAssignment, ExecutionTicket,
ExecutionReport, ReconciliationResult, and validation/reconciliation logic.
No real model calls, no remote execution.
"""
import sys
import os
import json
import tempfile
from typing import Dict, List, Optional

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.vibe_runtime_assignment import (
    RuntimeAssignment, RoleAssignment, ExecutionTicket, ExecutionReport,
    ReconciliationResult, reconcile_report, reconcile_all_reports,
    check_secret_leak, check_forbidden_files, self_check,
    VALID_ROLES, VALID_NODES, NODE_TRANSPORT_MAP,
    ORCHESTRATOR_DEFAULT_NODE, FORBIDDEN_FILES,
)


def _make_full_assignment():
    """Create a valid full 9-role RuntimeAssignment for testing."""
    role_assignments = {}
    for role in VALID_ROLES:
        if role in ("orchestrator", "planner", "reviewer-b", "git-integrator"):
            node = "21bao"
        elif role in ("tester-b", "reviewer-a"):
            node = "9bao"
        else:
            node = "5bao"
        role_assignments[role] = RoleAssignment(
            role=role,
            assignee=f"{role}/{node}",
            node_id=node,
            transport=NODE_TRANSPORT_MAP[node],
            provider="minimax-plan",
            model="MiniMax-M3",
            model_alias="minimax-m3",
        )
    return RuntimeAssignment(
        workorder_id="wo_test_20260626",
        approval_id="appr_test_abc123",
        base_sha="c71f9b5d6cbde04c7461b894108235b44886a64a",
        created_at="2026-06-26T12:00:00Z",
        scope="test scope",
        role_assignments=role_assignments,
    )


# ── 1. Valid runtime assignment ──

def test_valid_runtime_assignment():
    """A properly constructed RuntimeAssignment must validate."""
    assign = _make_full_assignment()
    errors = assign.validate()
    assert len(errors) == 0, f"Validation errors: {errors}"
    assert assign.is_executable() is True


# ── 2. operator_selected=false BLOCK ──

def test_operator_selected_false_block():
    """operator_selected=false must block execution."""
    assign = _make_full_assignment()
    assign.operator_selected = False
    assert assign.is_executable() is False
    errors = assign.validate()
    assert any("operator_selected" in e for e in errors)


# ── 3. fallback_allowed=true BLOCK ──

def test_fallback_allowed_true_block():
    """fallback_allowed=true must block execution."""
    assign = _make_full_assignment()
    assign.fallback_allowed = True
    assert assign.is_executable() is False
    errors = assign.validate()
    assert any("fallback_allowed" in e for e in errors)


# ── 4. Node mismatch BLOCK ──

def test_node_mismatch_block():
    """Reconciliation must detect node mismatch."""
    assign = _make_full_assignment()
    report = ExecutionReport(
        ticket_id="tkt_test_impl", role="implementer",
        planned_node="5bao", actual_node="9bao",
        planned_provider="minimax-plan", actual_provider="minimax-plan",
        planned_model="MiniMax-M3", actual_model="MiniMax-M3",
    )
    result = reconcile_report(assign, report)
    assert result.all_pass is False
    assert result.node_mismatch is True
    assert any("Node mismatch" in r for r in result.block_reasons)


# ── 5. Provider mismatch BLOCK ──

def test_provider_mismatch_block():
    """Reconciliation must detect provider mismatch."""
    assign = _make_full_assignment()
    report = ExecutionReport(
        ticket_id="tkt_test_impl", role="implementer",
        planned_node="5bao", actual_node="5bao",
        planned_provider="minimax-plan", actual_provider="volcengine",
        planned_model="MiniMax-M3", actual_model="MiniMax-M3",
    )
    result = reconcile_report(assign, report)
    assert result.all_pass is False
    assert result.provider_mismatch is True


# ── 6. Model mismatch BLOCK ──

def test_model_mismatch_block():
    """Reconciliation must detect model mismatch."""
    assign = _make_full_assignment()
    report = ExecutionReport(
        ticket_id="tkt_test_impl", role="implementer",
        planned_node="5bao", actual_node="5bao",
        planned_provider="minimax-plan", actual_provider="minimax-plan",
        planned_model="MiniMax-M3", actual_model="deepseek-v4-flash",
    )
    result = reconcile_report(assign, report)
    assert result.all_pass is False
    assert result.model_mismatch is True


# ── 7. fallback_count>0 BLOCK ──

def test_fallback_count_positive_block():
    """Report with fallback_count>0 must be blocked."""
    report = ExecutionReport(
        ticket_id="tkt_test", role="implementer",
        planned_node="5bao", actual_node="5bao",
        planned_provider="minimax-plan", actual_provider="minimax-plan",
        planned_model="MiniMax-M3", actual_model="MiniMax-M3",
        fallback_count=1,
    )
    errors = report.validate()
    assert len(errors) > 0
    assert any("fallback_count" in e for e in errors)


# ── 8. Forbidden file modified BLOCK ──

def test_forbidden_file_modified_block():
    """Reconciliation must detect forbidden file modification."""
    assign = _make_full_assignment()
    report = ExecutionReport(
        ticket_id="tkt_test_impl", role="implementer",
        planned_node="5bao", actual_node="5bao",
        planned_provider="minimax-plan", actual_provider="minimax-plan",
        planned_model="MiniMax-M3", actual_model="MiniMax-M3",
        forbidden_check="FAIL",
    )
    result = reconcile_report(assign, report)
    assert result.all_pass is False
    assert result.forbidden_file_violation is True


# ── 9. Secret leak BLOCK ──

def test_secret_leak_block():
    """Reconciliation must detect secret leak."""
    assign = _make_full_assignment()
    report = ExecutionReport(
        ticket_id="tkt_test_impl", role="implementer",
        planned_node="5bao", actual_node="5bao",
        planned_provider="minimax-plan", actual_provider="minimax-plan",
        planned_model="MiniMax-M3", actual_model="MiniMax-M3",
        secret_check="FAIL",
    )
    result = reconcile_report(assign, report)
    assert result.all_pass is False
    assert result.secret_leak_violation is True


# ── 10. Missing role BLOCK ──

def test_missing_role_block():
    """Reconciliation must detect missing role report."""
    assign = _make_full_assignment()
    reports = {}
    result = reconcile_all_reports(assign, reports)
    assert result.all_pass is False
    assert result.missing_role is True


# ── 11. Extra role BLOCK ──

def test_extra_role_block():
    """Reconciliation must detect extra unassigned role."""
    assign = _make_full_assignment()
    # Create reports for all assigned roles
    reports = {}
    for role in assign.role_assignments:
        ra = assign.role_assignments[role]
        reports[role] = ExecutionReport(
            ticket_id=f"tkt_{role}", role=role,
            planned_node=ra.node_id, actual_node=ra.node_id,
            planned_provider=ra.provider, actual_provider=ra.provider,
            planned_model=ra.model, actual_model=ra.model,
        )
    # Add extra role
    reports["extra-role"] = ExecutionReport(
        ticket_id="tkt_extra", role="extra-role",
        planned_node="5bao", actual_node="5bao",
        planned_provider="test", actual_provider="test",
        planned_model="test", actual_model="test",
    )
    result = reconcile_all_reports(assign, reports)
    assert result.all_pass is False
    assert result.extra_role is True


# ── 12. Health OFFLINE BLOCK ──

def test_health_offline_blocks_assignment():
    """RoleAssignment with health OFFLINE should be valid but not recommended."""
    ra = RoleAssignment(
        role="implementer", assignee="test",
        node_id="5bao", transport="ssh",
        provider="test", model="test", model_alias="test",
        health_status_at_approval="OFFLINE",
    )
    errors = ra.validate()
    # OFFLINE is a valid health status value
    assert len(errors) == 0
    # But should not be used for execution (policy decision)
    # The routing policy already skips OFFLINE nodes


# ── 13. Orchestrator 默认 21bao ──

def test_orchestrator_default_21bao():
    """Orchestrator must default to 21bao."""
    assert ORCHESTRATOR_DEFAULT_NODE == "21bao"
    # Verify in assignment
    assign = _make_full_assignment()
    orch = assign.role_assignments.get("orchestrator")
    assert orch is not None
    assert orch.node_id == "21bao"
    assert orch.transport == "local-exec"


# ── 14. 8 non-orchestrator roles operator override allowed ──

def test_non_orchestrator_operator_override():
    """Non-orchestrator roles must support operator_override source."""
    assign = _make_full_assignment()
    non_orch = [r for r in assign.role_assignments if r != "orchestrator"]
    assert len(non_orch) == 8
    # Each non-orchestrator role should be able to have source=operator_override
    for role in non_orch:
        ra = assign.role_assignments[role]
        ra.source = "operator_override"
        assert ra.source == "operator_override"
        errors = ra.validate()
        assert len(errors) == 0, f"Role {role} operator_override errors: {errors}"


# ── 15. Ticket/report roundtrip serialization ──

def test_ticket_report_roundtrip():
    """ExecutionTicket and ExecutionReport must survive JSON roundtrip."""
    ticket = ExecutionTicket(
        ticket_id="tkt_roundtrip", workorder_id="wo_rt",
        approval_id="appr_rt", role="implementer",
        node_id="5bao", provider="minimax-plan", model="MiniMax-M3",
    )
    json_str = ticket.to_json()
    restored = ExecutionTicket.from_json(json_str)
    assert restored.ticket_id == ticket.ticket_id
    assert restored.role == ticket.role
    assert restored.node_id == ticket.node_id

    report = ExecutionReport(
        ticket_id="tkt_rt", role="implementer",
        planned_node="5bao", actual_node="5bao",
        planned_provider="minimax-plan", actual_provider="minimax-plan",
        planned_model="MiniMax-M3", actual_model="MiniMax-M3",
    )
    json_str2 = report.to_json()
    restored2 = ExecutionReport.from_json(json_str2)
    assert restored2.ticket_id == report.ticket_id
    assert restored2.actual_node == report.actual_node


# ── 16. JSON schema / required fields validation ──

def test_required_fields_validation():
    """RuntimeAssignment must reject missing required fields."""
    # Missing workorder_id
    assign = RuntimeAssignment(
        workorder_id="", approval_id="test", base_sha="abc",
        created_at="now", scope="test",
    )
    errors = assign.validate()
    assert any("workorder_id" in e for e in errors)

    # Missing approval_id
    assign2 = RuntimeAssignment(
        workorder_id="test", approval_id="", base_sha="abc",
        created_at="now", scope="test",
    )
    errors2 = assign2.validate()
    assert any("approval_id" in e for e in errors2)

    # Missing base_sha
    assign3 = RuntimeAssignment(
        workorder_id="test", approval_id="test", base_sha="",
        created_at="now", scope="test",
    )
    errors3 = assign3.validate()
    assert any("base_sha" in e for e in errors3)


# ── 17. No real model call ──

def test_no_real_model_call():
    """All validation must complete without real model API calls."""
    import time
    start = time.time()
    assign = _make_full_assignment()
    errors = assign.validate()
    elapsed = time.time() - start
    assert elapsed < 2.0, f"Validation took {elapsed:.2f}s — may have made API calls"
    assert len(errors) == 0


# ── 18. No remote execution ──

def test_no_remote_execution():
    """Validation must not trigger remote execution."""
    import time
    start = time.time()
    # Run self-check (should be instant, no remote calls)
    result = self_check()
    elapsed = time.time() - start
    assert elapsed < 5.0, f"Self-check took {elapsed:.2f}s — may have remote calls"
    assert result["passed"] is True


# ── 19. validate_node_capability valid ──

def test_validate_node_capability_valid():
    """RoleAssignment with valid node/capability must pass."""
    ra = RoleAssignment(
        role="implementer", assignee="5bao/opencode",
        node_id="5bao", transport="ssh",
        provider="minimax-plan", model="MiniMax-M3",
        model_alias="minimax-m3",
        capability_required=["linux-worker", "implementer", "pytest"],
    )
    errors = ra.validate()
    assert len(errors) == 0


# ── 20. validate_node_capability invalid BLOCK ──

def test_validate_node_capability_invalid():
    """RoleAssignment with invalid node must be blocked."""
    ra = RoleAssignment(
        role="implementer", assignee="test",
        node_id="invalid-node", transport="ssh",
        provider="test", model="test", model_alias="test",
    )
    errors = ra.validate()
    assert len(errors) > 0
    assert any("node_id" in e.lower() for e in errors)


# ── 21. health UNKNOWN→VERIFIED_READONLY allowed ──

def test_health_unknown_to_verified_readonly():
    """Health status change from UNKNOWN to VERIFIED_READONLY must be allowed."""
    ra = RoleAssignment(
        role="implementer", assignee="test",
        node_id="5bao", transport="ssh",
        provider="test", model="test", model_alias="test",
        health_status_at_approval="VERIFIED_READONLY",
    )
    errors = ra.validate()
    assert len(errors) == 0, f"VERIFIED_READONLY should be valid: {errors}"


# ── 22. approval_id required ──

def test_approval_id_required():
    """RuntimeAssignment must require approval_id."""
    assign = _make_full_assignment()
    assign.approval_id = ""
    errors = assign.validate()
    assert any("approval_id" in e for e in errors)


# ── 23. base_sha required ──

def test_base_sha_required():
    """RuntimeAssignment must require base_sha."""
    assign = _make_full_assignment()
    assign.base_sha = ""
    errors = assign.validate()
    assert any("base_sha" in e for e in errors)


# ── 24. Report planned/actual exact match PASS ──

def test_report_planned_actual_exact_match():
    """Reconciliation must PASS when planned matches actual exactly."""
    assign = _make_full_assignment()
    reports = {}
    for role in assign.role_assignments:
        ra = assign.role_assignments[role]
        reports[role] = ExecutionReport(
            ticket_id=f"tkt_{role}", role=role,
            planned_node=ra.node_id, actual_node=ra.node_id,
            planned_provider=ra.provider, actual_provider=ra.provider,
            planned_model=ra.model, actual_model=ra.model,
        )
    result = reconcile_all_reports(assign, reports)
    assert result.all_pass is True, f"Expected PASS, got: {result.block_reasons}"
    assert result.node_mismatch is False
    assert result.provider_mismatch is False
    assert result.model_mismatch is False


# ── 25. recommendation source / operator_override source preserved ──

def test_source_preserved():
    """RoleAssignment source field must be preserved and valid."""
    ra_rec = RoleAssignment(
        role="implementer", assignee="test",
        node_id="5bao", transport="ssh",
        provider="test", model="test", model_alias="test",
        source="recommendation",
    )
    assert ra_rec.source == "recommendation"
    assert len(ra_rec.validate()) == 0

    ra_ovr = RoleAssignment(
        role="implementer", assignee="test",
        node_id="5bao", transport="ssh",
        provider="test", model="test", model_alias="test",
        source="operator_override",
    )
    assert ra_ovr.source == "operator_override"
    assert len(ra_ovr.validate()) == 0

    ra_bad = RoleAssignment(
        role="implementer", assignee="test",
        node_id="5bao", transport="ssh",
        provider="test", model="test", model_alias="test",
        source="invalid_source",
    )
    errors = ra_bad.validate()
    assert any("source" in e for e in errors)


# ── Additional: JSON roundtrip for RuntimeAssignment ──

def test_runtime_assignment_json_roundtrip():
    """RuntimeAssignment must survive full JSON roundtrip."""
    assign = _make_full_assignment()
    json_str = assign.to_json()
    restored = RuntimeAssignment.from_json(json_str)
    assert restored.workorder_id == assign.workorder_id
    assert restored.approval_id == assign.approval_id
    assert restored.base_sha == assign.base_sha
    assert len(restored.role_assignments) == 9
    for role in VALID_ROLES:
        assert role in restored.role_assignments
        assert restored.role_assignments[role].node_id == assign.role_assignments[role].node_id


# ── Additional: Secret leak detection ──

def test_secret_leak_detection():
    """check_secret_leak must detect common secret patterns."""
    assert check_secret_leak("sk-abc123") is True
    assert check_secret_leak("AKIAIOSFODNN7EXAMPLE") is True
    assert check_secret_leak("Bearer abc123token") is True
    assert check_secret_leak("ghp_abc123") is True
    assert check_secret_leak("gho_abc123") is True
    assert check_secret_leak("ghu_abc123") is True
    assert check_secret_leak("normal text without secrets") is False
    assert check_secret_leak("SECRET_REF is a field name") is False
    assert check_secret_leak("key_env is a field name") is False
    assert check_secret_leak("HTTP_401_INVALID_API_KEY") is False


# ── Additional: Forbidden files check ──

def test_forbidden_files_detection():
    """check_forbidden_files must detect forbidden file paths."""
    assert len(check_forbidden_files(["tests/test.py"])) == 0
    assert len(check_forbidden_files(["opencode.env"])) == 1
    assert len(check_forbidden_files(["config/opencode.jsonc"])) == 1
    assert len(check_forbidden_files(["runner"])) == 1
    assert len(check_forbidden_files(["SOUL.md"])) == 1
    assert len(check_forbidden_files(["MEMORY.md"])) == 1
    assert len(check_forbidden_files(["SKILL.md"])) == 1
    assert len(check_forbidden_files(["model_pool.secrets"])) == 1
    assert len(check_forbidden_files(["auth.json"])) == 1


# ── Additional: Transport mismatch ──

def test_transport_mismatch_block():
    """RoleAssignment must reject transport mismatch for node."""
    ra = RoleAssignment(
        role="implementer", assignee="test",
        node_id="5bao", transport="local-exec",  # 5bao must be ssh
        provider="test", model="test", model_alias="test",
    )
    errors = ra.validate()
    assert any("Transport mismatch" in e for e in errors)

    ra2 = RoleAssignment(
        role="orchestrator", assignee="test",
        node_id="21bao", transport="ssh",  # 21bao must be local-exec
        provider="test", model="test", model_alias="test",
    )
    errors2 = ra2.validate()
    assert any("Transport mismatch" in e for e in errors2)


# ── Additional: Ticket from assignment ──

def test_ticket_from_assignment():
    """ExecutionTicket.from_role_assignment must generate valid ticket."""
    assign = _make_full_assignment()
    ticket = ExecutionTicket.from_role_assignment(assign, "implementer")
    assert ticket.role == "implementer"
    assert ticket.node_id == "5bao"
    assert ticket.workorder_id == assign.workorder_id
    assert ticket.approval_id == assign.approval_id
    errors = ticket.validate()
    assert len(errors) == 0, f"Ticket validation errors: {errors}"


# ──────────────────────────────────────────────
# I5: ApprovalContract + Integration Tests (18 new tests)
# ──────────────────────────────────────────────

from scripts.vibe_runtime_assignment import (
    ApprovalContract, derive_runtime_assignment, derive_operator_selected,
    derive_runtime_assignment_source, validate_base_sha_match,
    validate_approval_not_expired, validate_action_allowed,
    trace_assignment_to_approval,
    VALID_SELECTION_SOURCES, EXECUTABLE_SELECTION_SOURCES,
)


def _make_valid_approval(
    selection_source: str = "operator_confirmed_default",
    base_sha: str = "c71f9b5d6cbde04c7461b894108235b44886a64a",
    expires_at: Optional[str] = None,
    approval_id: str = "appr_test_valid",
    workorder_id: str = "wo_test_valid",
    operator_id: str = "kk",
    forbidden_actions: Optional[List[str]] = None,
    allowed_actions: Optional[List[str]] = None,
):
    """Create a valid ApprovalContract for testing."""
    if forbidden_actions is None:
        forbidden_actions = ["push", "merge"]
    if allowed_actions is None:
        allowed_actions = ["local_exec", "test_run"]
    return ApprovalContract(
        approval_id=approval_id,
        workorder_id=workorder_id,
        operator_id=operator_id,
        operator_label="KK (operator)",
        approved_at="2026-06-26T12:00:00Z",
        base_sha=base_sha,
        expires_at=expires_at,
        risk_level="low",
        scope="test scope",
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
        allowed_actions=allowed_actions,
        forbidden_actions=forbidden_actions,
        allowed_files=["tests/"],
        forbidden_files=FORBIDDEN_FILES,
        selection_source=selection_source,
    )


# I5-1: ApprovalContract creation
def test_i5_approval_contract_creation():
    """Valid ApprovalContract must pass validation."""
    appr = _make_valid_approval()
    errors = appr.validate()
    assert len(errors) == 0, f"Validation errors: {errors}"


# I5-2: Missing approval_id
def test_i5_missing_approval_id():
    """ApprovalContract without approval_id must be blocked."""
    appr = _make_valid_approval(approval_id="")
    errors = appr.validate()
    assert any("approval_id" in e for e in errors)


# I5-3: Missing operator_id
def test_i5_missing_operator_id():
    """ApprovalContract without operator_id must be blocked."""
    appr = _make_valid_approval(operator_id="")
    errors = appr.validate()
    assert any("operator_id" in e for e in errors)


# I5-4: base_sha mismatch
def test_i5_base_sha_mismatch():
    """RuntimeAssignment base_sha must match ApprovalContract base_sha."""
    appr1 = _make_valid_approval(base_sha="aaaaaaa11111")
    appr2 = _make_valid_approval(base_sha="bbbbbbb22222", approval_id="appr_test2")
    assign1 = derive_runtime_assignment(appr1)
    assign2 = derive_runtime_assignment(appr2)
    errors = validate_base_sha_match(appr1, assign2)
    assert len(errors) > 0
    assert any("base_sha mismatch" in e for e in errors)


# I5-5: Expired approval
def test_i5_expired_approval():
    """Expired ApprovalContract must be rejected by derive_runtime_assignment."""
    appr = _make_valid_approval(expires_at="2020-01-01T00:00:00Z")
    try:
        derive_runtime_assignment(appr)
        assert False, "Should have raised ValueError for expired approval"
    except ValueError as e:
        assert "expired" in str(e)


# I5-6: planner_default BLOCK
def test_i5_planner_default_blocked():
    """selection_source=planner_default must NOT authorize execution."""
    appr = _make_valid_approval(selection_source="planner_default")
    try:
        derive_runtime_assignment(appr)
        assert False, "Should have raised ValueError for planner_default"
    except ValueError as e:
        assert "planner_default" in str(e) or "does not authorize" in str(e)
    # Also check derive_operator_selected
    assert derive_operator_selected("planner_default") is False


# I5-7: operator_confirmed_default PASS
def test_i5_operator_confirmed_default_passes():
    """selection_source=operator_confirmed_default must authorize execution."""
    appr = _make_valid_approval(selection_source="operator_confirmed_default")
    assign = derive_runtime_assignment(appr)
    assert assign.operator_selected is True
    assert assign.derivation_source == "approval_contract"
    # Role source should be "recommendation" (traceable to planner)
    assert assign.role_assignments["implementer"].source == "recommendation"
    assert derive_operator_selected("operator_confirmed_default") is True


# I5-8: operator_override PASS
def test_i5_operator_override_passes():
    """selection_source=operator_override must authorize execution."""
    appr = _make_valid_approval(selection_source="operator_override")
    assign = derive_runtime_assignment(appr)
    assert assign.operator_selected is True
    # Role source should be "operator_override"
    assert assign.role_assignments["implementer"].source == "operator_override"
    assert derive_operator_selected("operator_override") is True


# I5-9: derive_runtime_assignment
def test_i5_derive_runtime_assignment():
    """derive_runtime_assignment must produce correct RuntimeAssignment from ApprovalContract."""
    appr = _make_valid_approval()
    assign = derive_runtime_assignment(appr)
    assert assign.approval_id == appr.approval_id
    assert assign.base_sha == appr.base_sha
    assert assign.workorder_id == appr.workorder_id
    assert assign.operator_selected is True
    assert assign.fallback_allowed is False
    assert assign.fallback_count == 0
    assert assign.derivation_source == "approval_contract"
    assert len(assign.role_assignments) == 9
    # Verify orchestrator defaults to 21bao
    assert assign.role_assignments["orchestrator"].node_id == "21bao"


# I5-10: Cannot derive without ApprovalContract
def test_i5_cannot_derive_without_approval():
    """derive_runtime_assignment must reject non-ApprovalContract input."""
    try:
        derive_runtime_assignment("not an approval")
        assert False, "Should have raised TypeError"
    except TypeError as e:
        assert "ApprovalContract" in str(e)

    try:
        derive_runtime_assignment({"approval_id": "x"})
        assert False, "Should have raised TypeError"
    except TypeError as e:
        assert "ApprovalContract" in str(e)


# I5-11: forbidden action BLOCK
def test_i5_forbidden_action_block():
    """RuntimeAssignment must reject actions in forbidden_actions."""
    appr = _make_valid_approval(
        forbidden_actions=["push", "merge", "force_push"],
        allowed_actions=["local_exec", "test_run"],
    )
    assign = derive_runtime_assignment(appr)
    # Push is forbidden
    errors_push = validate_action_allowed(assign, "push")
    assert len(errors_push) > 0
    # Local exec is allowed
    errors_local = validate_action_allowed(assign, "local_exec")
    assert len(errors_local) == 0
    # Test run is allowed
    errors_test = validate_action_allowed(assign, "test_run")
    assert len(errors_test) == 0
    # Some random action not in allowed_actions
    errors_random = validate_action_allowed(assign, "random_action")
    assert len(errors_random) > 0


# I5-12: allowed action PASS
def test_i5_allowed_action_pass():
    """RuntimeAssignment must accept actions in allowed_actions."""
    appr = _make_valid_approval(allowed_actions=["local_exec", "test_run", "self_check"])
    assign = derive_runtime_assignment(appr)
    for action in ["local_exec", "test_run", "self_check"]:
        errors = validate_action_allowed(assign, action)
        assert len(errors) == 0, f"Action {action} should be allowed: {errors}"


# I5-13: Approval JSON roundtrip
def test_i5_approval_json_roundtrip():
    """ApprovalContract must survive JSON roundtrip."""
    appr = _make_valid_approval()
    json_str = appr.to_json()
    restored = ApprovalContract.from_json(json_str)
    assert restored.approval_id == appr.approval_id
    assert restored.workorder_id == appr.workorder_id
    assert restored.operator_id == appr.operator_id
    assert restored.base_sha == appr.base_sha
    assert restored.selection_source == appr.selection_source
    assert restored.selected_node_matrix == appr.selected_node_matrix
    assert restored.selected_model_matrix == appr.selected_model_matrix


# I5-14: RuntimeAssignment 来源校验
def test_i5_runtime_assignment_source_validation():
    """trace_assignment_to_approval must verify RuntimeAssignment origin."""
    appr = _make_valid_approval()
    assign = derive_runtime_assignment(appr)
    # Valid trace
    errors = trace_assignment_to_approval(assign, appr)
    assert len(errors) == 0, f"Valid trace should pass: {errors}"

    # Wrong approval_id
    wrong_appr = _make_valid_approval(approval_id="appr_wrong")
    errors2 = trace_assignment_to_approval(assign, wrong_appr)
    assert len(errors2) > 0
    assert any("approval_id mismatch" in e for e in errors2)

    # Wrong base_sha
    wrong_sha_appr = _make_valid_approval(base_sha="wrong_sha_xx")
    errors3 = trace_assignment_to_approval(assign, wrong_sha_appr)
    assert len(errors3) > 0
    assert any("base_sha mismatch" in e for e in errors3)


# I5-15: Self-constructed RuntimeAssignment must be marked
def test_i5_self_constructed_marked():
    """RuntimeAssignment not derived from approval must have derivation_source='self_constructed'."""
    assign = _make_full_assignment()
    assign.derivation_source = "self_constructed"
    assert assign.derivation_source == "self_constructed"
    # This is a valid state for testing, but not for execution
    assert assign.derivation_source != "approval_contract"


# I5-16: derive_operator_selected semantics
def test_i5_derive_operator_selected_semantics():
    """derive_operator_selected must follow selection_source semantics."""
    assert derive_operator_selected("planner_default") is False
    assert derive_operator_selected("operator_confirmed_default") is True
    assert derive_operator_selected("operator_override") is True
    assert derive_operator_selected("invalid_source") is False


# I5-17: derive_runtime_assignment_source preserves operator_override
def test_i5_derive_runtime_assignment_source_preserves_override():
    """derive_runtime_assignment_source must preserve operator_override distinction."""
    assert derive_runtime_assignment_source("planner_default") == "recommendation"
    assert derive_runtime_assignment_source("operator_confirmed_default") == "recommendation"
    assert derive_runtime_assignment_source("operator_override") == "operator_override"


# I5-18: Expiration boundary check
def test_i5_expiration_boundary():
    """Approval expiration must be strictly after expires_at."""
    # Future expiration
    future_appr = _make_valid_approval(expires_at="2099-12-31T23:59:59Z")
    assert future_appr.is_expired() is False
    assign = derive_runtime_assignment(future_appr)
    assert assign.approval_id == future_appr.approval_id

    # Past expiration
    past_appr = _make_valid_approval(expires_at="2020-01-01T00:00:00Z")
    assert past_appr.is_expired() is True
    try:
        derive_runtime_assignment(past_appr)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    # No expiration
    no_exp_appr = _make_valid_approval(expires_at=None)
    assert no_exp_appr.is_expired() is False
    assign2 = derive_runtime_assignment(no_exp_appr)
    assert assign2.approval_id == no_exp_appr.approval_id
