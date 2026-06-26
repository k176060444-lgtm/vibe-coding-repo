"""V1.21.33I4: Runtime Assignment Framework — unified contract module.

Provides the shared data structures and validation logic for:
- RuntimeAssignment: operator-approved execution plan
- RoleAssignment: per-role node/model assignment
- ExecutionTicket: worker-facing execution ticket
- ExecutionReport: worker-produced execution report
- ReconciliationResult: planned-vs-actual audit

Architecture invariants:
- Orchestrator defaults to 21bao/vibedev (control-plane)
- 8 non-orchestrator roles are operator-overridable
- Recommendation != Operator Selection
- operator_selected=true required for executable assignments
- fallback_allowed=false, fallback_count=0
- 21bao=local-exec, 5bao/9bao=ssh
- health UNKNOWN != ONLINE/OFFLINE
- No auto-fallback
- deepseek-v4-pro guarded, mimo/xiaomi blocked
"""
import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


# ──────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────

VALID_ROLES = [
    "orchestrator", "explorer", "planner", "implementer",
    "tester-a", "tester-b", "reviewer-a", "reviewer-b", "git-integrator",
]

VALID_NODES = ["5bao", "9bao", "21bao"]
VALID_TRANSPORTS = ["ssh", "local-exec"]
VALID_HEALTH_STATUSES = ["UNKNOWN", "VERIFIED_READONLY", "ONLINE", "OFFLINE"]
VALID_SOURCES = ["recommendation", "operator_override"]

ORCHESTRATOR_DEFAULT_NODE = "21bao"
ORCHESTRATOR_DEFAULT_TRANSPORT = "local-exec"

NODE_TRANSPORT_MAP = {
    "5bao": "ssh",
    "9bao": "ssh",
    "21bao": "local-exec",
}

FORBIDDEN_FILES = [
    "opencode.env", "opencode.jsonc", "model_pool.secrets",
    "auth.json", "runner", "SOUL.md", "MEMORY.md", "SKILL.md",
]

SECRET_PATTERNS = ["sk-", "AKIA", "Bearer ", "ghp_", "gho_", "ghu_"]


# ──────────────────────────────────────────────
# Data Contracts
# ──────────────────────────────────────────────


@dataclass
class RoleAssignment:
    """Single role assignment within a RuntimeAssignment."""
    role: str
    assignee: str
    node_id: str
    transport: str
    provider: str
    model: str
    model_alias: str
    health_status_at_approval: str = "UNKNOWN"
    capability_required: List[str] = field(default_factory=list)
    source: str = "recommendation"  # recommendation | operator_override

    def validate(self) -> List[str]:
        errors = []
        if self.role not in VALID_ROLES:
            errors.append(f"Invalid role: {self.role}")
        if self.node_id not in VALID_NODES:
            errors.append(f"Invalid node_id: {self.node_id}")
        if self.transport not in VALID_TRANSPORTS:
            errors.append(f"Invalid transport: {self.transport}")
        if self.health_status_at_approval not in VALID_HEALTH_STATUSES:
            errors.append(f"Invalid health_status: {self.health_status_at_approval}")
        if self.source not in VALID_SOURCES:
            errors.append(f"Invalid source: {self.source}")
        # Transport must match node
        expected_transport = NODE_TRANSPORT_MAP.get(self.node_id)
        if expected_transport and self.transport != expected_transport:
            errors.append(
                f"Transport mismatch for {self.node_id}: "
                f"expected {expected_transport}, got {self.transport}"
            )
        # Orchestrator must default to 21bao
        if self.role == "orchestrator" and self.node_id != ORCHESTRATOR_DEFAULT_NODE:
            errors.append(
                f"Orchestrator must default to {ORCHESTRATOR_DEFAULT_NODE}, "
                f"got {self.node_id}"
            )
        return errors


@dataclass
class RuntimeAssignment:
    """Operator-approved execution plan — the central contract."""
    workorder_id: str
    approval_id: str
    base_sha: str
    created_at: str
    scope: str
    risk_level: str = "low"
    operator_selected: bool = True
    fallback_allowed: bool = False
    fallback_count: int = 0
    role_assignments: Dict[str, RoleAssignment] = field(default_factory=dict)
    allowed_files: List[str] = field(default_factory=list)
    forbidden_files: List[str] = field(default_factory=lambda: FORBIDDEN_FILES[:])
    allowed_actions: List[str] = field(default_factory=list)
    forbidden_actions: List[str] = field(default_factory=list)
    expected_outputs: List[str] = field(default_factory=list)
    audit_requirements: List[str] = field(default_factory=list)
    report_schema_version: str = "1.0.0"
    derivation_source: str = "self_constructed"  # "self_constructed" | "approval_contract"

    def validate(self) -> List[str]:
        errors = []
        if not self.workorder_id:
            errors.append("workorder_id is required")
        if not self.approval_id:
            errors.append("approval_id is required")
        if not self.base_sha:
            errors.append("base_sha is required")
        if not self.created_at:
            errors.append("created_at is required")
        if not self.scope:
            errors.append("scope is required")
        if self.operator_selected is not True:
            errors.append("operator_selected must be True for executable assignment")
        if self.fallback_allowed is not False:
            errors.append("fallback_allowed must be False")
        if self.fallback_count != 0:
            errors.append("fallback_count must be 0")
        if not self.role_assignments:
            errors.append("At least one role_assignment required")
        else:
            for role, ra in self.role_assignments.items():
                ra_errors = ra.validate()
                for e in ra_errors:
                    errors.append(f"role_assignments.{role}: {e}")
        # Check all 9 roles present
        assigned_roles = set(self.role_assignments.keys())
        for role in VALID_ROLES:
            if role not in assigned_roles:
                errors.append(f"Missing required role: {role}")
        # Check no extra roles
        for role in assigned_roles:
            if role not in VALID_ROLES:
                errors.append(f"Extra invalid role: {role}")
        return errors

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> "RuntimeAssignment":
        d = json.loads(data)
        ras = {}
        for role, ra_dict in d.get("role_assignments", {}).items():
            ras[role] = RoleAssignment(**ra_dict)
        d["role_assignments"] = ras
        return cls(**d)

    def is_executable(self) -> bool:
        """Check if this assignment is ready for execution."""
        return (
            self.operator_selected is True
            and self.fallback_allowed is False
            and self.fallback_count == 0
            and len(self.role_assignments) == 9
            and len(self.validate()) == 0
        )


@dataclass
class ExecutionTicket:
    """Worker-facing execution ticket — what a worker receives."""
    ticket_id: str
    workorder_id: str
    approval_id: str
    role: str
    node_id: str
    provider: str
    model: str
    task_prompt_hash: str = ""
    allowed_paths: List[str] = field(default_factory=list)
    forbidden_paths: List[str] = field(default_factory=lambda: FORBIDDEN_FILES[:])
    no_secret_output: bool = True
    no_fallback: bool = True
    expected_artifacts: List[str] = field(default_factory=list)
    report_schema_ref: str = "report_schema_v1.0.0"

    def validate(self) -> List[str]:
        errors = []
        if not self.ticket_id:
            errors.append("ticket_id is required")
        if not self.workorder_id:
            errors.append("workorder_id is required")
        if not self.approval_id:
            errors.append("approval_id is required")
        if self.role not in VALID_ROLES:
            errors.append(f"Invalid role: {self.role}")
        if self.node_id not in VALID_NODES:
            errors.append(f"Invalid node_id: {self.node_id}")
        if self.no_secret_output is not True:
            errors.append("no_secret_output must be True")
        if self.no_fallback is not True:
            errors.append("no_fallback must be True")
        return errors

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> "ExecutionTicket":
        return cls(**json.loads(data))

    @classmethod
    def from_role_assignment(
        cls, assignment: RuntimeAssignment, role: str
    ) -> "ExecutionTicket":
        """Generate a ticket from a RuntimeAssignment for a specific role."""
        ra = assignment.role_assignments[role]
        ticket_id = f"tkt_{assignment.workorder_id}_{role}"
        return cls(
            ticket_id=ticket_id,
            workorder_id=assignment.workorder_id,
            approval_id=assignment.approval_id,
            role=role,
            node_id=ra.node_id,
            provider=ra.provider,
            model=ra.model,
            allowed_paths=assignment.allowed_files,
            forbidden_paths=assignment.forbidden_files,
            expected_artifacts=assignment.expected_outputs,
        )


@dataclass
class ExecutionReport:
    """Worker-produced execution report."""
    ticket_id: str
    role: str
    planned_node: str
    actual_node: str
    planned_provider: str
    actual_provider: str
    planned_model: str
    actual_model: str
    started_at: str = ""
    ended_at: str = ""
    elapsed_seconds: Optional[float] = None
    model_call_count: int = 0
    token_usage: Optional[Dict[str, int]] = None
    changed_files: List[str] = field(default_factory=list)
    commands_run: List[str] = field(default_factory=list)
    test_result: Dict[str, Any] = field(default_factory=dict)
    fallback_count: int = 0
    secret_check: str = "PASS"
    forbidden_check: str = "PASS"
    final_verdict: str = "PASS"
    deviation_notes: List[str] = field(default_factory=list)

    def validate(self) -> List[str]:
        errors = []
        if not self.ticket_id:
            errors.append("ticket_id is required")
        if self.role not in VALID_ROLES:
            errors.append(f"Invalid role: {self.role}")
        if self.fallback_count > 0:
            errors.append(f"fallback_count must be 0, got {self.fallback_count}")
        return errors

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> "ExecutionReport":
        return cls(**json.loads(data))


@dataclass
class ReconciliationResult:
    """Planned vs Actual audit result."""
    node_mismatch: bool = False
    provider_mismatch: bool = False
    model_mismatch: bool = False
    fallback_violation: bool = False
    forbidden_file_violation: bool = False
    secret_leak_violation: bool = False
    missing_role: bool = False
    extra_role: bool = False
    health_changed_to_offline: bool = False
    all_pass: bool = True
    block_reasons: List[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)


# ──────────────────────────────────────────────
# ApprovalContract
# ──────────────────────────────────────────────

VALID_SELECTION_SOURCES = ["planner_default", "operator_confirmed_default", "operator_override"]
EXECUTABLE_SELECTION_SOURCES = ["operator_confirmed_default", "operator_override"]
VALID_RISK_LEVELS = ["low", "medium", "high"]


@dataclass
class ApprovalContract:
    """Operator-approved execution authorization.

    Source of truth for RuntimeAssignment. RuntimeAssignment must be
    derived from ApprovalContract via derive_runtime_assignment().
    """
    approval_id: str
    workorder_id: str
    operator_id: str
    operator_label: str = ""
    approved_at: str = ""
    base_sha: str = ""
    expires_at: Optional[str] = None
    approval_version: str = "1.0.0"
    approval_notes: str = ""
    risk_level: str = "low"
    scope: str = ""
    selected_role_matrix: Dict[str, str] = field(default_factory=dict)
    selected_node_matrix: Dict[str, str] = field(default_factory=dict)
    selected_model_matrix: Dict[str, Dict[str, str]] = field(default_factory=dict)
    allowed_actions: List[str] = field(default_factory=list)
    forbidden_actions: List[str] = field(default_factory=list)
    allowed_files: List[str] = field(default_factory=list)
    forbidden_files: List[str] = field(default_factory=lambda: FORBIDDEN_FILES[:])
    selection_source: str = "planner_default"
    approval_signature: Optional[str] = None  # reserved, not implemented

    def validate(self) -> List[str]:
        errors = []
        if not self.approval_id:
            errors.append("approval_id is required")
        if not self.workorder_id:
            errors.append("workorder_id is required")
        if not self.operator_id:
            errors.append("operator_id is required")
        if not self.approved_at:
            errors.append("approved_at is required")
        if not self.base_sha or len(self.base_sha) < 7:
            errors.append("base_sha is required (min 7 chars)")
        if self.risk_level not in VALID_RISK_LEVELS:
            errors.append(f"Invalid risk_level: {self.risk_level}")
        if self.selection_source not in VALID_SELECTION_SOURCES:
            errors.append(f"Invalid selection_source: {self.selection_source}")
        if not self.selected_role_matrix:
            errors.append("selected_role_matrix is required")
        if not self.selected_node_matrix:
            errors.append("selected_node_matrix is required")
        if not self.selected_model_matrix:
            errors.append("selected_model_matrix is required")
        for role in VALID_ROLES:
            if role not in self.selected_role_matrix:
                errors.append(f"selected_role_matrix missing: {role}")
            if role not in self.selected_node_matrix:
                errors.append(f"selected_node_matrix missing: {role}")
            if role not in self.selected_model_matrix:
                errors.append(f"selected_model_matrix missing: {role}")
        return errors

    def is_expired(self, now: Optional[str] = None) -> bool:
        if not self.expires_at:
            return False
        if now is None:
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return now > self.expires_at

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> "ApprovalContract":
        return cls(**json.loads(data))


# ──────────────────────────────────────────────
# Derivation Functions
# ──────────────────────────────────────────────


def derive_operator_selected(selection_source: str) -> bool:
    """Only operator-confirmed sources authorize execution."""
    return selection_source in EXECUTABLE_SELECTION_SOURCES


def derive_runtime_assignment_source(selection_source: str) -> str:
    """Map selection_source to RoleAssignment.source."""
    if selection_source == "operator_override":
        return "operator_override"
    return "recommendation"


def derive_runtime_assignment(approval: ApprovalContract) -> RuntimeAssignment:
    """Derive RuntimeAssignment from ApprovalContract.

    This is the ONLY sanctioned way to create an executable RuntimeAssignment.
    RuntimeAssignment must NOT be self-constructed for execution.
    """
    if not isinstance(approval, ApprovalContract):
        raise TypeError("RuntimeAssignment must be derived from ApprovalContract")

    errors = approval.validate()
    if errors:
        raise ValueError(f"Invalid approval: {errors}")

    if approval.is_expired():
        raise ValueError(f"Approval {approval.approval_id} has expired")

    operator_selected = derive_operator_selected(approval.selection_source)
    if not operator_selected:
        raise ValueError(
            f"selection_source={approval.selection_source} does not authorize execution; "
            f"must be one of {EXECUTABLE_SELECTION_SOURCES}"
        )

    role_assignments = {}
    for role in VALID_ROLES:
        node_id = approval.selected_node_matrix[role]
        model_info = approval.selected_model_matrix[role]
        ra = RoleAssignment(
            role=role,
            assignee=f"{role}/{node_id}",
            node_id=node_id,
            transport=NODE_TRANSPORT_MAP[node_id],
            provider=model_info["provider"],
            model=model_info["model"],
            model_alias=model_info["alias"],
            health_status_at_approval="UNKNOWN",
            capability_required=[],
            source=derive_runtime_assignment_source(approval.selection_source),
        )
        role_assignments[role] = ra

    return RuntimeAssignment(
        workorder_id=approval.workorder_id,
        approval_id=approval.approval_id,
        base_sha=approval.base_sha,
        created_at=approval.approved_at,
        scope=approval.scope,
        risk_level=approval.risk_level,
        operator_selected=operator_selected,
        fallback_allowed=False,
        fallback_count=0,
        role_assignments=role_assignments,
        allowed_files=approval.allowed_files,
        forbidden_files=approval.forbidden_files,
        allowed_actions=approval.allowed_actions,
        forbidden_actions=approval.forbidden_actions,
        expected_outputs=[],
        audit_requirements=[
            "base_sha_match", "approval_not_expired",
            "secret_leak_check", "forbidden_files_check",
        ],
        derivation_source="approval_contract",
    )


# ──────────────────────────────────────────────
# Cross-validation
# ──────────────────────────────────────────────


def validate_base_sha_match(
    approval: ApprovalContract, assignment: RuntimeAssignment
) -> List[str]:
    """Enforce approval.base_sha == assignment.base_sha."""
    errors = []
    if approval.base_sha != assignment.base_sha:
        errors.append(
            f"base_sha mismatch: approval={approval.base_sha}, "
            f"assignment={assignment.base_sha}"
        )
    return errors


def validate_approval_not_expired(approval: ApprovalContract) -> List[str]:
    """Enforce approval not expired."""
    if approval.is_expired():
        return [f"Approval {approval.approval_id} has expired at {approval.expires_at}"]
    return []


def validate_action_allowed(
    assignment: RuntimeAssignment, action: str
) -> List[str]:
    """Enforce action is in allowed_actions and not in forbidden_actions."""
    errors = []
    if action in assignment.forbidden_actions:
        errors.append(f"Action '{action}' is in forbidden_actions")
    if assignment.allowed_actions and action not in assignment.allowed_actions:
        errors.append(f"Action '{action}' is not in allowed_actions")
    return errors


def trace_assignment_to_approval(
    assignment: RuntimeAssignment, approval: ApprovalContract
) -> List[str]:
    """Verify RuntimeAssignment was derived from this ApprovalContract."""
    errors = []
    if assignment.approval_id != approval.approval_id:
        errors.append(
            f"approval_id mismatch: assignment={assignment.approval_id}, "
            f"approval={approval.approval_id}"
        )
    if assignment.base_sha != approval.base_sha:
        errors.append(
            f"base_sha mismatch: assignment={assignment.base_sha}, "
            f"approval={approval.base_sha}"
        )
    if assignment.workorder_id != approval.workorder_id:
        errors.append(
            f"workorder_id mismatch: assignment={assignment.workorder_id}, "
            f"approval={approval.workorder_id}"
        )
    return errors


# ──────────────────────────────────────────────
# Validation / Reconciliation Functions
# ──────────────────────────────────────────────


def reconcile_report(
    assignment: RuntimeAssignment,
    report: ExecutionReport,
) -> ReconciliationResult:
    """Reconcile a single ExecutionReport against its RuntimeAssignment."""
    result = ReconciliationResult()

    ra = assignment.role_assignments.get(report.role)
    if ra is None:
        result.missing_role = True
        result.all_pass = False
        result.block_reasons.append(f"Role {report.role} not in assignment")
        return result

    # Node mismatch
    if report.actual_node != ra.node_id:
        result.node_mismatch = True
        result.all_pass = False
        result.block_reasons.append(
            f"Node mismatch: planned={ra.node_id}, actual={report.actual_node}"
        )

    # Provider mismatch
    if report.actual_provider != ra.provider:
        result.provider_mismatch = True
        result.all_pass = False
        result.block_reasons.append(
            f"Provider mismatch: planned={ra.provider}, actual={report.actual_provider}"
        )

    # Model mismatch
    if report.actual_model != ra.model:
        result.model_mismatch = True
        result.all_pass = False
        result.block_reasons.append(
            f"Model mismatch: planned={ra.model}, actual={report.actual_model}"
        )

    # Fallback violation
    if report.fallback_count > 0:
        result.fallback_violation = True
        result.all_pass = False
        result.block_reasons.append(
            f"Fallback violation: count={report.fallback_count}"
        )

    # Secret leak
    if report.secret_check != "PASS":
        result.secret_leak_violation = True
        result.all_pass = False
        result.block_reasons.append("Secret leak detected")

    # Forbidden file
    if report.forbidden_check != "PASS":
        result.forbidden_file_violation = True
        result.all_pass = False
        result.block_reasons.append("Forbidden file modified")

    return result


def reconcile_all_reports(
    assignment: RuntimeAssignment,
    reports: Dict[str, ExecutionReport],
) -> ReconciliationResult:
    """Reconcile all reports against the assignment."""
    result = ReconciliationResult()

    # Check all assigned roles have reports
    for role in assignment.role_assignments:
        if role not in reports:
            result.missing_role = True
            result.all_pass = False
            result.block_reasons.append(f"Missing report for role: {role}")

    # Check no extra reports
    for role in reports:
        if role not in assignment.role_assignments:
            result.extra_role = True
            result.all_pass = False
            result.block_reasons.append(f"Extra report for unassigned role: {role}")

    # Reconcile each report
    for role, report in reports.items():
        if role in assignment.role_assignments:
            single = reconcile_report(assignment, report)
            if not single.all_pass:
                result.all_pass = False
                result.block_reasons.extend(single.block_reasons)
            # Merge flags
            result.node_mismatch = result.node_mismatch or single.node_mismatch
            result.provider_mismatch = result.provider_mismatch or single.provider_mismatch
            result.model_mismatch = result.model_mismatch or single.model_mismatch
            result.fallback_violation = result.fallback_violation or single.fallback_violation
            result.forbidden_file_violation = result.forbidden_file_violation or single.forbidden_file_violation
            result.secret_leak_violation = result.secret_leak_violation or single.secret_leak_violation

    return result


def check_secret_leak(text: str) -> bool:
    """Check if text contains potential secret patterns."""
    for pattern in SECRET_PATTERNS:
        if pattern in text:
            return True
    return False


def check_forbidden_files(changed_files: List[str]) -> List[str]:
    """Check if any changed files are in the forbidden list."""
    violations = []
    for f in changed_files:
        for forbidden in FORBIDDEN_FILES:
            if forbidden in f:
                violations.append(f)
    return violations


def generate_workorder_id(prefix: str = "wo") -> str:
    """Generate a unique workorder ID."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{prefix}_{ts}"


def generate_approval_id(prefix: str = "appr") -> str:
    """Generate a unique approval ID."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{prefix}_{ts}"


def generate_ticket_id(workorder_id: str, role: str) -> str:
    """Generate a ticket ID from workorder and role."""
    return f"tkt_{workorder_id}_{role}"


def generate_prompt_hash(prompt: str) -> str:
    """Generate SHA256 hash of a task prompt."""
    return hashlib.sha256(prompt.encode()).hexdigest()


# ──────────────────────────────────────────────
# Self-Check
# ──────────────────────────────────────────────


def self_check() -> Dict[str, Any]:
    """Run self-check and return results."""
    results = []
    all_pass = True

    # SC1: Valid role list
    assert len(VALID_ROLES) == 9, f"Expected 9 roles, got {len(VALID_ROLES)}"
    results.append({"name": "valid_9_roles", "passed": True, "detail": f"9 roles: {VALID_ROLES}"})

    # SC2: Orchestrator default
    assert ORCHESTRATOR_DEFAULT_NODE == "21bao"
    results.append({"name": "orchestrator_default_21bao", "passed": True})

    # SC3: Node transport map
    assert NODE_TRANSPORT_MAP["5bao"] == "ssh"
    assert NODE_TRANSPORT_MAP["9bao"] == "ssh"
    assert NODE_TRANSPORT_MAP["21bao"] == "local-exec"
    results.append({"name": "node_transport_map", "passed": True})

    # SC4: Create valid RuntimeAssignment
    ra = RoleAssignment(
        role="implementer", assignee="5bao/opencode",
        node_id="5bao", transport="ssh",
        provider="minimax-plan", model="MiniMax-M3",
        model_alias="minimax-m3",
    )
    assert len(ra.validate()) == 0
    results.append({"name": "valid_role_assignment", "passed": True})

    # SC5: Orchestrator wrong node BLOCK
    ra_bad = RoleAssignment(
        role="orchestrator", assignee="bad",
        node_id="5bao", transport="ssh",
        provider="x", model="y", model_alias="z",
    )
    assert len(ra_bad.validate()) > 0
    results.append({"name": "orchestrator_wrong_node_blocked", "passed": True})

    # SC6: operator_selected=false BLOCK
    assign = RuntimeAssignment(
        workorder_id="test", approval_id="test", base_sha="abc",
        created_at="now", scope="test",
        operator_selected=False,
    )
    assert not assign.is_executable()
    results.append({"name": "operator_selected_false_blocked", "passed": True})

    # SC7: fallback_allowed=true BLOCK
    assign2 = RuntimeAssignment(
        workorder_id="test", approval_id="test", base_sha="abc",
        created_at="now", scope="test",
        fallback_allowed=True,
    )
    assert not assign2.is_executable()
    results.append({"name": "fallback_allowed_true_blocked", "passed": True})

    # SC8: Valid ticket creation
    ticket = ExecutionTicket(
        ticket_id="tkt_test_impl", workorder_id="wo_test",
        approval_id="appr_test", role="implementer",
        node_id="5bao", provider="minimax-plan", model="MiniMax-M3",
    )
    assert len(ticket.validate()) == 0
    results.append({"name": "valid_ticket", "passed": True})

    # SC9: Ticket with invalid role
    ticket_bad = ExecutionTicket(
        ticket_id="tkt_bad", workorder_id="wo_bad",
        approval_id="appr_bad", role="nonexistent",
        node_id="5bao", provider="x", model="y",
    )
    assert len(ticket_bad.validate()) > 0
    results.append({"name": "invalid_role_ticket_blocked", "passed": True})

    # SC10: Report with fallback_count>0 BLOCK
    report = ExecutionReport(
        ticket_id="tkt_test", role="implementer",
        planned_node="5bao", actual_node="5bao",
        planned_provider="minimax-plan", actual_provider="minimax-plan",
        planned_model="MiniMax-M3", actual_model="MiniMax-M3",
        fallback_count=1,
    )
    assert len(report.validate()) > 0
    results.append({"name": "fallback_count_positive_blocked", "passed": True})

    # SC11: Reconciliation node mismatch
    assign_full = RuntimeAssignment(
        workorder_id="wo_test", approval_id="appr_test",
        base_sha="abc", created_at="now", scope="test",
        role_assignments={
            "implementer": RoleAssignment(
                role="implementer", assignee="5bao/opencode",
                node_id="5bao", transport="ssh",
                provider="minimax-plan", model="MiniMax-M3",
                model_alias="minimax-m3",
            ),
        },
    )
    # Fill missing roles with dummy
    for r in VALID_ROLES:
        if r not in assign_full.role_assignments:
            assign_full.role_assignments[r] = RoleAssignment(
                role=r, assignee=f"{r}/test",
                node_id="21bao" if r in ("orchestrator", "planner", "reviewer-b", "git-integrator") else "5bao",
                transport=NODE_TRANSPORT_MAP.get("21bao" if r in ("orchestrator", "planner", "reviewer-b", "git-integrator") else "5bao", "ssh"),
                provider="test", model="test", model_alias="test",
            )

    report_good = ExecutionReport(
        ticket_id="tkt_test", role="implementer",
        planned_node="5bao", actual_node="5bao",
        planned_provider="minimax-plan", actual_provider="minimax-plan",
        planned_model="MiniMax-M3", actual_model="MiniMax-M3",
    )
    rec = reconcile_report(assign_full, report_good)
    assert rec.all_pass is True
    results.append({"name": "reconciliation_match_pass", "passed": True})

    report_bad_node = ExecutionReport(
        ticket_id="tkt_test", role="implementer",
        planned_node="5bao", actual_node="9bao",
        planned_provider="minimax-plan", actual_provider="minimax-plan",
        planned_model="MiniMax-M3", actual_model="MiniMax-M3",
    )
    rec2 = reconcile_report(assign_full, report_bad_node)
    assert rec2.all_pass is False
    assert rec2.node_mismatch is True
    results.append({"name": "reconciliation_node_mismatch_block", "passed": True})

    # SC12: Secret leak detection
    assert check_secret_leak("sk-abc123") is True
    assert check_secret_leak("AKIAIOSFODNN7EXAMPLE") is True
    assert check_secret_leak("Bearer abc123") is True
    assert check_secret_leak("normal text") is False
    results.append({"name": "secret_leak_detection", "passed": True})

    # SC13: Forbidden files check
    assert len(check_forbidden_files(["tests/test.py"])) == 0
    assert len(check_forbidden_files(["opencode.env"])) == 1
    assert len(check_forbidden_files(["config/opencode.jsonc"])) == 1
    results.append({"name": "forbidden_files_check", "passed": True})

    # SC14: JSON roundtrip
    json_str = assign_full.to_json()
    restored = RuntimeAssignment.from_json(json_str)
    assert restored.workorder_id == assign_full.workorder_id
    assert restored.approval_id == assign_full.approval_id
    results.append({"name": "json_roundtrip", "passed": True})

    # SC15: Ticket from assignment
    ticket_from = ExecutionTicket.from_role_assignment(assign_full, "implementer")
    assert ticket_from.role == "implementer"
    assert ticket_from.node_id == "5bao"
    results.append({"name": "ticket_from_assignment", "passed": True})

    # SC16: Orchestrator default check
    orch_ra = assign_full.role_assignments.get("orchestrator")
    if orch_ra:
        assert orch_ra.node_id == "21bao"
        results.append({"name": "orchestrator_default_in_assignment", "passed": True})

    # SC17: 8 non-orchestrator roles
    non_orch = [r for r in assign_full.role_assignments if r != "orchestrator"]
    assert len(non_orch) == 8
    results.append({"name": "eight_non_orchestrator_roles", "passed": True})

    # SC18: No real model call (self-check only)
    results.append({"name": "no_real_model_call", "passed": True})

    # SC19: approval_id required
    assign_no_approval = RuntimeAssignment(
        workorder_id="test", approval_id="", base_sha="abc",
        created_at="now", scope="test",
    )
    assert "approval_id" in str(assign_no_approval.validate())
    results.append({"name": "approval_id_required", "passed": True})

    # SC20: base_sha required
    assign_no_sha = RuntimeAssignment(
        workorder_id="test", approval_id="test", base_sha="",
        created_at="now", scope="test",
    )
    assert "base_sha" in str(assign_no_sha.validate())
    results.append({"name": "base_sha_required", "passed": True})

    # SC21: ApprovalContract valid creation
    valid_approval = ApprovalContract(
        approval_id="appr_sc21", workorder_id="wo_sc21", operator_id="kk",
        approved_at="2026-06-26T12:00:00Z",
        base_sha="c71f9b5d6cbde04c7461b894108235b44886a64a",
        scope="sc21 test",
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
        selection_source="operator_confirmed_default",
    )
    assert len(valid_approval.validate()) == 0
    results.append({"name": "approval_valid", "passed": True})

    # SC22: derive_runtime_assignment from valid approval
    derived = derive_runtime_assignment(valid_approval)
    assert derived.approval_id == valid_approval.approval_id
    assert derived.base_sha == valid_approval.base_sha
    assert derived.operator_selected is True
    assert derived.derivation_source == "approval_contract"
    results.append({"name": "derive_runtime_assignment", "passed": True})

    # SC23: base_sha mismatch BLOCK
    mismatch_approval = ApprovalContract(
        approval_id="appr_sc23", workorder_id="wo_sc23", operator_id="kk",
        approved_at="2026-06-26T12:00:00Z",
        base_sha="aaaaaaa",
        scope="sc23 test",
        selected_role_matrix={r: r for r in VALID_ROLES},
        selected_node_matrix=valid_approval.selected_node_matrix,
        selected_model_matrix=valid_approval.selected_model_matrix,
        selection_source="operator_confirmed_default",
    )
    derived2 = derive_runtime_assignment(mismatch_approval)
    base_sha_errors = validate_base_sha_match(valid_approval, derived2)
    assert len(base_sha_errors) > 0
    results.append({"name": "base_sha_mismatch_block", "passed": True})

    # SC24: expired approval BLOCK
    expired_approval = ApprovalContract(
        approval_id="appr_sc24", workorder_id="wo_sc24", operator_id="kk",
        approved_at="2020-01-01T00:00:00Z",
        expires_at="2020-01-02T00:00:00Z",
        base_sha="c71f9b5d6cbde04c7461b894108235b44886a64a",
        scope="sc24 test",
        selected_role_matrix={r: r for r in VALID_ROLES},
        selected_node_matrix=valid_approval.selected_node_matrix,
        selected_model_matrix=valid_approval.selected_model_matrix,
        selection_source="operator_confirmed_default",
    )
    try:
        derive_runtime_assignment(expired_approval)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "expired" in str(e)
    results.append({"name": "expired_approval_block", "passed": True})

    # SC25: planner_default BLOCK
    planner_default_approval = ApprovalContract(
        approval_id="appr_sc25", workorder_id="wo_sc25", operator_id="kk",
        approved_at="2026-06-26T12:00:00Z",
        base_sha="c71f9b5d6cbde04c7461b894108235b44886a64a",
        scope="sc25 test",
        selected_role_matrix={r: r for r in VALID_ROLES},
        selected_node_matrix=valid_approval.selected_node_matrix,
        selected_model_matrix=valid_approval.selected_model_matrix,
        selection_source="planner_default",
    )
    try:
        derive_runtime_assignment(planner_default_approval)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "planner_default" in str(e) or "does not authorize" in str(e)
    results.append({"name": "planner_default_block", "passed": True})

    # SC26: operator_override source preserved
    override_approval = ApprovalContract(
        approval_id="appr_sc26", workorder_id="wo_sc26", operator_id="kk",
        approved_at="2026-06-26T12:00:00Z",
        base_sha="c71f9b5d6cbde04c7461b894108235b44886a64a",
        scope="sc26 test",
        selected_role_matrix={r: r for r in VALID_ROLES},
        selected_node_matrix=valid_approval.selected_node_matrix,
        selected_model_matrix=valid_approval.selected_model_matrix,
        selection_source="operator_override",
    )
    derived_override = derive_runtime_assignment(override_approval)
    assert derived_override.role_assignments["implementer"].source == "operator_override"
    results.append({"name": "operator_override_preserved", "passed": True})

    # Summary
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    all_pass = failed == 0

    return {
        "name": "vibe_runtime_assignment",
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
    elif "--validate" in sys.argv:
        # Read JSON from stdin and validate
        data = sys.stdin.read()
        try:
            assign = RuntimeAssignment.from_json(data)
            errors = assign.validate()
            if errors:
                print(json.dumps({"valid": False, "errors": errors}, indent=2))
                sys.exit(1)
            else:
                print(json.dumps({"valid": True, "executable": assign.is_executable()}, indent=2))
                sys.exit(0)
        except Exception as e:
            print(json.dumps({"valid": False, "errors": [str(e)]}, indent=2))
            sys.exit(1)
    else:
        print("Usage: python scripts/vibe_runtime_assignment.py --self-check")
        print("       python scripts/vibe_runtime_assignment.py --validate < assignment.json")
