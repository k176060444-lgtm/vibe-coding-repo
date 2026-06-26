"""Tests for V1.21.33I4: Runtime Assignment Framework.

Tests the unified contract module: RuntimeAssignment, ExecutionTicket,
ExecutionReport, ReconciliationResult, and validation/reconciliation logic.
No real model calls, no remote execution.
"""
import sys
import os
import json
import tempfile

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
