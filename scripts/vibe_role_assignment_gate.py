#!/usr/bin/env python3
"""vibe_role_assignment_gate.py — Workflow Role Assignment Gate v1.0.0

Enforces that every coding PR/workflow starts with a complete role/model/node
plan.  Execution is blocked until the operator confirms the assignment matrix.

Hard requirements (V1.21.2):
  1. Every coding PR must have a reviewer.
  2. Medium/high-risk / upstream / security / admin / credential /
     command-execution / permission-related PRs must recommend two independent
     reviewers where possible.
  3. Tester/checker must be an explicit role.  The main agent may only act as
     tester if the operator explicitly approves that assignment.
  4. Role architecture is recommended based on task size/risk.
  5. Each role assignment must include: role, node, model, provider, cost_tag,
     reason, call_budget, fallback_policy.
  6. Operator must approve the assignment matrix before live model calls.
  7. Final report must include planned vs actual ledger.

Usage:
    python scripts/vibe_role_assignment_gate.py --self-check
    python scripts/vibe_role_assignment_gate.py validate --matrix MATRIX_JSON
    python scripts/vibe_role_assignment_gate.py recommend --risk low --task-type coding
    python scripts/vibe_role_assignment_gate.py recommend --risk high --tags upstream,admin
"""

__version__ = "1.0.0"

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import List, Optional

# ── Constants ──────────────────────────────────────────────────────────

VALID_RISK_LEVELS = {"low", "medium", "high", "critical"}
VALID_ROLES = {
    "implementer", "reviewer", "reviewer-1", "reviewer-2",
    "tester", "checker", "tester-checker",
    "docs-helper", "planner", "smoke",
}
REQUIRED_ASSIGNMENT_FIELDS = [
    "role", "node", "model", "provider",
    "cost_tag", "reason", "call_budget", "fallback_policy",
]
VALID_FALLBACK_POLICIES = {"disabled", "operator_selects", "same_provider_different_model"}

# High-risk tags that trigger dual reviewer requirement
DUAL_REVIEWER_TAGS = {
    "upstream", "security", "admin", "credential",
    "command-execution", "permission", "hermes-agent",
}

# ── Risk Classification ───────────────────────────────────────────────

def classify_risk(risk_level: str, tags: list = None) -> str:
    """Return effective risk tier: low, medium, high, critical.

    Classification rules:
      - low:     small, self-contained, local-only changes
      - medium:  moderate scope, multiple files, internal tools
      - high:    upstream PRs, security, admin, credentials, permissions
      - critical: production deployment, gateway restart, credential rotation
    """
    tags = set(tags or [])
    risk_level = (risk_level or "low").lower()

    if risk_level == "critical":
        return "critical"
    if risk_level == "high" or tags & DUAL_REVIEWER_TAGS:
        return "high"
    if risk_level == "medium":
        return "medium"
    return "low"


def needs_dual_reviewer(risk_level: str, tags: list = None) -> bool:
    """Check if task requires two independent reviewers."""
    effective = classify_risk(risk_level, tags)
    return effective in ("high", "critical")


# ── Required Roles by Risk ────────────────────────────────────────────

def get_required_roles(risk_level: str, tags: list = None) -> dict:
    """Return required role structure for a given risk level.

    Returns:
        {
            "risk_level": str,
            "effective_risk": str,
            "required_roles": [str],
            "optional_roles": [str],
            "requires_dual_reviewer": bool,
            "main_agent_as_tester_requires_approval": bool,
        }
    """
    effective = classify_risk(risk_level, tags)

    if effective == "low":
        return {
            "risk_level": risk_level,
            "effective_risk": effective,
            "required_roles": ["implementer", "reviewer", "checker"],
            "optional_roles": [],
            "requires_dual_reviewer": False,
            "main_agent_as_tester_requires_approval": True,
        }
    elif effective == "medium":
        return {
            "risk_level": risk_level,
            "effective_risk": effective,
            "required_roles": ["implementer", "reviewer", "tester-checker"],
            "optional_roles": [],
            "requires_dual_reviewer": False,
            "main_agent_as_tester_requires_approval": True,
        }
    else:  # high or critical
        return {
            "risk_level": risk_level,
            "effective_risk": effective,
            "required_roles": ["implementer", "reviewer-1", "reviewer-2", "tester-checker"],
            "optional_roles": ["docs-helper"],
            "requires_dual_reviewer": True,
            "main_agent_as_tester_requires_approval": True,
        }


# ── Role Assignment Schema ────────────────────────────────────────────

def create_role_assignment(
    role: str,
    node: str,
    model: str,
    provider: str,
    cost_tag: str = "",
    reason: str = "",
    call_budget: int = 100,
    fallback_policy: str = "disabled",
) -> dict:
    """Create a single role assignment entry."""
    return {
        "role": role,
        "node": node,
        "model": model,
        "provider": provider,
        "cost_tag": cost_tag,
        "reason": reason,
        "call_budget": call_budget,
        "fallback_policy": fallback_policy,
    }


def create_assignment_matrix(
    risk_level: str,
    tags: list = None,
    task_id: str = "",
    task_type: str = "coding",
) -> dict:
    """Create an empty assignment matrix template for the given risk level."""
    required = get_required_roles(risk_level, tags)
    return {
        "version": __version__,
        "task_id": task_id,
        "task_type": task_type,
        "risk_level": risk_level,
        "effective_risk": required["effective_risk"],
        "tags": tags or [],
        "required_roles": required["required_roles"],
        "optional_roles": required["optional_roles"],
        "requires_dual_reviewer": required["requires_dual_reviewer"],
        "assignments": [],  # to be filled by operator
        "operator_approved": False,
        "operator_approval_timestamp": None,
        "operator_approval_signature": None,
        "main_agent_as_tester_approved": False,
    }


# ── Validation ────────────────────────────────────────────────────────

def validate_assignment_entry(entry: dict, index: int) -> list:
    """Validate a single assignment entry. Returns list of errors."""
    errors = []
    for field in REQUIRED_ASSIGNMENT_FIELDS:
        if field not in entry:
            errors.append(f"assignment[{index}]: missing required field '{field}'")

    # Validate role
    role = entry.get("role", "")
    if role not in VALID_ROLES:
        errors.append(f"assignment[{index}]: invalid role '{role}' (valid: {VALID_ROLES})")

    # Validate fallback_policy
    fb = entry.get("fallback_policy", "")
    if fb not in VALID_FALLBACK_POLICIES:
        errors.append(f"assignment[{index}]: invalid fallback_policy '{fb}'")

    # Validate call_budget
    cb = entry.get("call_budget", 0)
    if not isinstance(cb, int) or cb < 1:
        errors.append(f"assignment[{index}]: call_budget must be positive integer, got {cb}")

    # node, model, provider must be non-empty strings
    for field in ("node", "model", "provider"):
        val = str(entry.get(field, "")).strip()
        if not val:
            errors.append(f"assignment[{index}]: {field} must not be empty")

    return errors


def validate_assignment_matrix(matrix: dict) -> dict:
    """Validate a complete assignment matrix.

    Returns:
        {
            "valid": bool,
            "errors": [str],
            "warnings": [str],
            "checks": [{name, result, detail}],
        }
    """
    errors = []
    warnings = []
    checks = []

    # Check 1: Has risk_level
    risk = matrix.get("risk_level", "")
    if risk not in VALID_RISK_LEVELS:
        errors.append(f"invalid risk_level: '{risk}'")
        checks.append({"name": "risk_level", "result": "BLOCK", "detail": f"invalid: {risk}"})
    else:
        checks.append({"name": "risk_level", "result": "PASS", "detail": risk})

    # Check 2: Has required roles
    required_roles = matrix.get("required_roles", [])
    if not required_roles:
        errors.append("missing required_roles")
        checks.append({"name": "required_roles", "result": "BLOCK", "detail": "missing"})
    else:
        checks.append({"name": "required_roles", "result": "PASS", "detail": f"{len(required_roles)} roles"})

    # Check 3: Has assignments
    assignments = matrix.get("assignments", [])
    if not assignments:
        errors.append("no assignments provided")
        checks.append({"name": "has_assignments", "result": "BLOCK", "detail": "empty"})
    else:
        checks.append({"name": "has_assignments", "result": "PASS", "detail": f"{len(assignments)} entries"})

    # Check 4: Each assignment entry is valid
    for i, entry in enumerate(assignments):
        entry_errors = validate_assignment_entry(entry, i)
        errors.extend(entry_errors)
    if not errors:
        checks.append({"name": "assignment_entries_valid", "result": "PASS", "detail": "all valid"})
    else:
        checks.append({"name": "assignment_entries_valid", "result": "BLOCK", "detail": f"{len(errors)} errors"})

    # Check 5: Every coding PR must have a reviewer
    has_reviewer = any(
        a.get("role", "").startswith("reviewer")
        for a in assignments
    )
    if not has_reviewer:
        errors.append("BLOCK: no reviewer assigned — every coding PR must have a reviewer")
        checks.append({"name": "has_reviewer", "result": "BLOCK", "detail": "no reviewer"})
    else:
        checks.append({"name": "has_reviewer", "result": "PASS", "detail": "reviewer present"})

    # Check 6: High-risk requires dual reviewer
    requires_dual = matrix.get("requires_dual_reviewer", False)
    reviewer_count = sum(
        1 for a in assignments
        if a.get("role", "").startswith("reviewer")
    )
    if requires_dual and reviewer_count < 2:
        errors.append(
            f"BLOCK: high-risk/critical task requires 2 independent reviewers, "
            f"found {reviewer_count}"
        )
        checks.append({
            "name": "dual_reviewer",
            "result": "BLOCK",
            "detail": f"requires 2, found {reviewer_count}",
        })
    elif requires_dual:
        checks.append({
            "name": "dual_reviewer",
            "result": "PASS",
            "detail": f"{reviewer_count} reviewers",
        })
    else:
        checks.append({
            "name": "dual_reviewer",
            "result": "PASS",
            "detail": f"not required (risk={matrix.get('risk_level')})",
        })

    # Check 7: Tester/checker must be explicit
    has_tester = any(
        a.get("role", "") in ("tester", "checker", "tester-checker")
        for a in assignments
    )
    if not has_tester:
        errors.append("BLOCK: tester/checker must be an explicit role assignment")
        checks.append({"name": "tester_explicit", "result": "BLOCK", "detail": "no tester/checker"})
    else:
        checks.append({"name": "tester_explicit", "result": "PASS", "detail": "tester/checker present"})

    # Check 8: Main agent as tester requires explicit approval
    main_as_tester = any(
        a.get("role", "") in ("tester", "tester-checker")
        and a.get("node", "") == "main-agent"
        for a in assignments
    )
    if main_as_tester and not matrix.get("main_agent_as_tester_approved", False):
        errors.append(
            "BLOCK: main agent assigned as tester but operator has not "
            "explicitly approved this assignment"
        )
        checks.append({
            "name": "main_agent_as_tester",
            "result": "BLOCK",
            "detail": "main-agent-as-tester not approved",
        })
    elif main_as_tester:
        checks.append({
            "name": "main_agent_as_tester",
            "result": "PASS",
            "detail": "operator approved main-agent-as-tester",
        })
    else:
        checks.append({
            "name": "main_agent_as_tester",
            "result": "PASS",
            "detail": "main agent not assigned as tester",
        })

    # Check 9: Operator approval
    if not matrix.get("operator_approved", False):
        errors.append("BLOCK: operator has not approved the assignment matrix")
        checks.append({
            "name": "operator_approved",
            "result": "BLOCK",
            "detail": "not approved",
        })
    else:
        checks.append({
            "name": "operator_approved",
            "result": "PASS",
            "detail": f"approved at {matrix.get('operator_approval_timestamp', '?')}",
        })

    # Determine verdict
    has_block = any(c["result"] == "BLOCK" for c in checks)
    verdict = "BLOCK" if has_block else "ALLOW"

    return {
        "valid": len(errors) == 0,
        "verdict": verdict,
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "summary": {
            "total": len(checks),
            "pass": sum(1 for c in checks if c["result"] == "PASS"),
            "block": sum(1 for c in checks if c["result"] == "BLOCK"),
        },
    }


# ── Planned vs Actual Ledger ──────────────────────────────────────────

def generate_planned_vs_actual_ledger(
    matrix: dict,
    actual_entries: list,
) -> dict:
    """Generate planned vs actual comparison ledger.

    Args:
        matrix: The approved assignment matrix (planned).
        actual_entries: List of actual execution records, each with:
            {role, node, model, provider, call_count, duration, exit_code,
             fallback_used, final_status, evidence_path}

    Returns:
        {
            "planned_roles": [...],
            "actual_roles": [...],
            "discrepancies": [...],
            "ledger": [{role, planned_model, actual_model, planned_node,
                       actual_node, planned_provider, actual_provider,
                       match, call_count, duration, exit_code, final_status}],
        }
    """
    planned = {a["role"]: a for a in matrix.get("assignments", [])}
    actual = {a["role"]: a for a in actual_entries}

    all_roles = sorted(set(planned.keys()) | set(actual.keys()))

    ledger = []
    discrepancies = []

    for role in all_roles:
        p = planned.get(role, {})
        a = actual.get(role, {})

        model_match = p.get("model") == a.get("model")
        node_match = p.get("node") == a.get("node")
        provider_match = p.get("provider") == a.get("provider")

        entry = {
            "role": role,
            "planned_model": p.get("model", "N/A"),
            "actual_model": a.get("model", "N/A"),
            "planned_node": p.get("node", "N/A"),
            "actual_node": a.get("node", "N/A"),
            "planned_provider": p.get("provider", "N/A"),
            "actual_provider": a.get("provider", "N/A"),
            "model_match": model_match,
            "node_match": node_match,
            "provider_match": provider_match,
            "call_count": a.get("call_count", 0),
            "duration": a.get("duration", "N/A"),
            "exit_code": a.get("exit_code", None),
            "final_status": a.get("final_status", "N/A"),
        }
        ledger.append(entry)

        if not model_match:
            discrepancies.append(f"{role}: model {p.get('model')} -> {a.get('model')}")
        if not node_match:
            discrepancies.append(f"{role}: node {p.get('node')} -> {a.get('node')}")
        if not provider_match:
            discrepancies.append(f"{role}: provider {p.get('provider')} -> {a.get('provider')}")

    return {
        "planned_roles": sorted(planned.keys()),
        "actual_roles": sorted(actual.keys()),
        "missing_actual": sorted(set(planned.keys()) - set(actual.keys())),
        "extra_actual": sorted(set(actual.keys()) - set(planned.keys())),
        "discrepancies": discrepancies,
        "ledger": ledger,
    }


# ── Self-Check ────────────────────────────────────────────────────────

def self_check() -> dict:
    """Run comprehensive self-check."""
    checks = []
    passed = 0
    total = 0

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal passed, total
        total += 1
        if ok:
            passed += 1
        checks.append({"name": name, "passed": ok, "detail": detail})

    # rag-01: version
    check("rag-01-version", bool(__version__), __version__)

    # rag-02: low risk classification
    check("rag-02-low-risk", classify_risk("low") == "low")

    # rag-03: medium risk classification
    check("rag-03-medium-risk", classify_risk("medium") == "medium")

    # rag-04: high risk classification
    check("rag-04-high-risk", classify_risk("high") == "high")

    # rag-05: tag-based escalation
    check("rag-05-tag-escalation", classify_risk("low", ["upstream"]) == "high")

    # rag-06: dual reviewer needed for high risk
    check("rag-06-dual-reviewer", needs_dual_reviewer("high"))

    # rag-07: dual reviewer not needed for low risk
    check("rag-07-no-dual-low", not needs_dual_reviewer("low"))

    # rag-08: low risk requires reviewer
    req_low = get_required_roles("low")
    check("rag-08-low-has-reviewer", "reviewer" in req_low["required_roles"])

    # rag-09: low risk requires checker
    check("rag-09-low-has-checker", "checker" in req_low["required_roles"])

    # rag-10: medium risk requires tester-checker
    req_med = get_required_roles("medium")
    check("rag-10-med-has-tester-checker", "tester-checker" in req_med["required_roles"])

    # rag-11: high risk requires dual reviewer
    req_high = get_required_roles("high")
    check("rag-11-high-dual-reviewer",
          "reviewer-1" in req_high["required_roles"] and
          "reviewer-2" in req_high["required_roles"])

    # rag-12: high risk has optional docs-helper
    check("rag-12-high-docs-helper", "docs-helper" in req_high["optional_roles"])

    # rag-13: assignment entry validation
    good_entry = create_role_assignment(
        role="implementer", node="21bao",
        model="opencode/deepseek-v4-pro", provider="deepseek",
        cost_tag="implementer-001", reason="code implementation",
        call_budget=100, fallback_policy="disabled",
    )
    entry_errors = validate_assignment_entry(good_entry, 0)
    check("rag-13-good-entry-valid", len(entry_errors) == 0, str(entry_errors))

    # rag-14: bad entry missing role
    bad_entry = {k: v for k, v in good_entry.items() if k != "role"}
    bad_errors = validate_assignment_entry(bad_entry, 0)
    check("rag-14-missing-role-invalid", len(bad_errors) > 0)

    # rag-15: valid matrix with approvals
    matrix = create_assignment_matrix("low", task_id="test-001")
    matrix["assignments"] = [
        create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek",
                               cost_tag="imp-001", reason="implement"),
        create_role_assignment("reviewer", "9bao", "opencode/deepseek-v4-pro", "deepseek",
                               cost_tag="rev-001", reason="review"),
        create_role_assignment("checker", "21bao", "opencode/deepseek-v4-pro", "deepseek",
                               cost_tag="chk-001", reason="check"),
    ]
    matrix["operator_approved"] = True
    matrix["operator_approval_timestamp"] = "2026-06-21T00:00:00Z"
    result = validate_assignment_matrix(matrix)
    check("rag-15-valid-matrix", result["valid"], str(result["errors"]))

    # rag-16: missing reviewer blocks
    matrix_no_rev = dict(matrix)
    matrix_no_rev["assignments"] = [
        create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("checker", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
    ]
    result_no_rev = validate_assignment_matrix(matrix_no_rev)
    check("rag-16-missing-reviewer-blocks", not result_no_rev["valid"])

    # rag-17: high risk needs 2 reviewers
    matrix_high = create_assignment_matrix("high", task_id="test-high")
    matrix_high["assignments"] = [
        create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("reviewer-1", "9bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("reviewer-2", "5bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("tester-checker", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
    ]
    matrix_high["operator_approved"] = True
    matrix_high["operator_approval_timestamp"] = "2026-06-21T00:00:00Z"
    result_high = validate_assignment_matrix(matrix_high)
    check("rag-17-high-dual-reviewer-valid", result_high["valid"], str(result_high["errors"]))

    # rag-18: high risk with 1 reviewer blocks
    matrix_high_1rev = dict(matrix_high)
    matrix_high_1rev["assignments"] = [
        create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("reviewer", "9bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("tester-checker", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
    ]
    result_high_1rev = validate_assignment_matrix(matrix_high_1rev)
    check("rag-18-high-one-reviewer-blocks", not result_high_1rev["valid"])

    # rag-19: missing tester blocks
    matrix_no_tester = dict(matrix)
    matrix_no_tester["assignments"] = [
        create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("reviewer", "9bao", "opencode/deepseek-v4-pro", "deepseek"),
    ]
    result_no_tester = validate_assignment_matrix(matrix_no_tester)
    check("rag-19-missing-tester-blocks", not result_no_tester["valid"])

    # rag-20: main-agent-as-tester requires approval
    matrix_main_tester = create_assignment_matrix("low", task_id="test-main-tester")
    matrix_main_tester["assignments"] = [
        create_role_assignment("implementer", "21bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("reviewer", "9bao", "opencode/deepseek-v4-pro", "deepseek"),
        create_role_assignment("tester-checker", "main-agent", "hermes/mimo-v2.5-pro", "xiaomi"),
    ]
    matrix_main_tester["operator_approved"] = True
    matrix_main_tester["operator_approval_timestamp"] = "2026-06-21T00:00:00Z"
    # Without main_agent_as_tester_approved
    result_main = validate_assignment_matrix(matrix_main_tester)
    check("rag-20-main-tester-blocks-without-approval", not result_main["valid"])

    # rag-21: main-agent-as-tester with approval
    matrix_main_tester_approved = dict(matrix_main_tester)
    matrix_main_tester_approved["main_agent_as_tester_approved"] = True
    result_main_ok = validate_assignment_matrix(matrix_main_tester_approved)
    check("rag-21-main-tester-allowed-with-approval", result_main_ok["valid"])

    # rag-22: unapproved matrix blocks
    matrix_unapproved = dict(matrix)
    matrix_unapproved["operator_approved"] = False
    result_unapp = validate_assignment_matrix(matrix_unapproved)
    check("rag-22-unapproved-blocks", not result_unapp["valid"])

    # rag-23: planned vs actual ledger
    actual = [
        {"role": "implementer", "node": "21bao", "model": "opencode/deepseek-v4-pro",
         "provider": "deepseek", "call_count": 5, "duration": "30s", "exit_code": 0,
         "final_status": "PASS"},
        {"role": "reviewer", "node": "9bao", "model": "opencode/deepseek-v4-pro",
         "provider": "deepseek", "call_count": 2, "duration": "10s", "exit_code": 0,
         "final_status": "PASS"},
        {"role": "checker", "node": "21bao", "model": "opencode/deepseek-v4-pro",
         "provider": "deepseek", "call_count": 1, "duration": "5s", "exit_code": 0,
         "final_status": "PASS"},
    ]
    ledger = generate_planned_vs_actual_ledger(matrix, actual)
    check("rag-23-ledger-has-discrepancies-key", "discrepancies" in ledger)
    check("rag-24-ledger-has-entries", len(ledger["ledger"]) == 3)
    check("rag-25-ledger-model-match", ledger["ledger"][0]["model_match"])
    check("rag-26-ledger-no-discrepancies", len(ledger["discrepancies"]) == 0)

    # rag-27: planned vs actual with mismatch
    actual_mismatch = [
        {"role": "implementer", "node": "9bao", "model": "opencode/mimo-v2.5-pro",
         "provider": "xiaomi", "call_count": 5, "duration": "30s", "exit_code": 0,
         "final_status": "PASS"},
        {"role": "reviewer", "node": "9bao", "model": "opencode/deepseek-v4-pro",
         "provider": "deepseek", "call_count": 2, "duration": "10s", "exit_code": 0,
         "final_status": "PASS"},
        {"role": "checker", "node": "21bao", "model": "opencode/deepseek-v4-pro",
         "provider": "deepseek", "call_count": 1, "duration": "5s", "exit_code": 0,
         "final_status": "PASS"},
    ]
    ledger_mismatch = generate_planned_vs_actual_ledger(matrix, actual_mismatch)
    check("rag-27-mismatch-detected", len(ledger_mismatch["discrepancies"]) > 0)
    impl_entry = [e for e in ledger_mismatch["ledger"] if e["role"] == "implementer"][0]
    check("rag-28-mismatch-model", not impl_entry["model_match"])

    # rag-29: all required fields check
    check("rag-29-required-fields-count",
          len(REQUIRED_ASSIGNMENT_FIELDS) >= 8,
          f"count={len(REQUIRED_ASSIGNMENT_FIELDS)}")

    # rag-30: valid roles set
    check("rag-30-valid-roles-count", len(VALID_ROLES) >= 8)

    return {
        "version": __version__,
        "passed": passed == total,
        "total_tests": total,
        "passed_count": passed,
        "failed_count": total - passed,
        "checks": checks,
        "exit_code": 0 if passed == total else 1,
    }


# ── CLI ───────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(
        description="Workflow Role Assignment Gate — enforce role plans before execution",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--json", dest="output_json", action="store_true")
    parser.add_argument("--self-check", dest="self_check_flag", action="store_true")

    sub = parser.add_subparsers(dest="command")

    p_val = sub.add_parser("validate", help="Validate assignment matrix")
    p_val.add_argument("--matrix", required=True, help="Path to assignment matrix JSON")

    p_rec = sub.add_parser("recommend", help="Recommend role structure")
    p_rec.add_argument("--risk", default="low", help="Risk level (low/medium/high/critical)")
    p_rec.add_argument("--tags", default="", help="Comma-separated tags")
    p_rec.add_argument("--task-type", default="coding", help="Task type")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_check_flag:
        result = self_check()
        if args.output_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"=== SELF-CHECK (v{__version__}) ===")
            print(f"  Total: {result['total_tests']}")
            print(f"  Passed: {result['passed_count']}")
            print(f"  Failed: {result['failed_count']}")
            for c in result["checks"]:
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  [{icon}] {c['name']}: {c['detail']}")
            print(f"\n  Self-check: {'PASSED' if result['passed'] else 'FAILED'}")
        sys.exit(result["exit_code"])

    if args.command == "validate":
        with open(args.matrix, "r", encoding="utf-8") as f:
            matrix = json.load(f)
        result = validate_assignment_matrix(matrix)
        if args.output_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Verdict: {result['verdict']}")
            for c in result["checks"]:
                icon = "PASS" if c["result"] == "PASS" else "BLOCK"
                print(f"  [{icon}] {c['name']}: {c['detail']}")
            for e in result["errors"]:
                print(f"  ERROR: {e}")
        sys.exit(0 if result["valid"] else 1)

    if args.command == "recommend":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        result = get_required_roles(args.risk, tags)
        result["tags"] = tags
        result["task_type"] = args.task_type
        if args.output_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Risk: {args.risk} → Effective: {result['effective_risk']}")
            print(f"Required: {', '.join(result['required_roles'])}")
            print(f"Optional: {', '.join(result['optional_roles']) if result['optional_roles'] else 'none'}")
            print(f"Dual reviewer: {result['requires_dual_reviewer']}")
            print(f"Main-agent-as-tester requires approval: {result['main_agent_as_tester_requires_approval']}")
        sys.exit(0)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
