#!/usr/bin/env python3
"""Upgrade plan JSON validator for VibeDev lifecycle management.

Validates upgrade plan JSON files against the schema defined in
UPGRADE_DOWNGRADE_LIFECYCLE.md.

Usage:
    python upgrade_plan_validate.py <plan.json>
    python upgrade_plan_validate.py --self-check
"""

import argparse
import json
import sys

SCHEMA_VERSION = 1

VALID_COMPONENTS = [
    "hermes-controller", "qq-gateway", "opencode-runtime",
    "node-runtime", "npm-runtime", "python-runtime",
    "git-runtime", "gh-cli", "bubblewrap", "ripgrep",
    "provider-plugin", "repo-lifecycle", "report-validator",
]

VALID_NODES = ["windows", "5bao", "9bao", "all"]

VALID_STATES = [
    "DISCOVER", "PLAN", "APPROVE", "DRAIN_WORKER", "SNAPSHOT",
    "UPGRADE_CANARY", "SMOKE_TEST", "REAL_FIXTURE_TEST",
    "OBSERVE", "PROMOTE_OR_ROLLBACK", "ATTEST",
]

VALID_ROLLBACK_METHODS = [
    "version_pin", "binary_restore", "config_restore", "git_revert",
]

VALID_INSTALL_METHODS = [
    "npm_global", "pip", "apt", "binary", "git_clone",
    "config_only", "system", "bundled",
]

REQUIRED_PLAN_FIELDS = [
    "plan_id", "schema_version", "component", "from_version",
    "to_version", "source", "install_method", "target_node",
    "canary_required", "rollback_target", "rollback_method",
    "health_gates", "operator_approval_required", "created_at",
]

REQUIRED_HEALTH_GATE_FIELDS = ["gate_name", "command", "expected_result"]


class ValidationError:
    def __init__(self, field, message, severity="error"):
        self.field = field
        self.message = message
        self.severity = severity

    def __repr__(self):
        return f"[{self.severity}] {self.field}: {self.message}"


def validate_plan(plan):
    """Validate an upgrade plan dict. Returns list of ValidationError."""
    errors = []

    # Check schema version
    if plan.get("schema_version") != SCHEMA_VERSION:
        errors.append(ValidationError(
            "schema_version",
            f"expected {SCHEMA_VERSION}, got {plan.get('schema_version')}"
        ))

    # Check required fields
    for field in REQUIRED_PLAN_FIELDS:
        if field not in plan:
            errors.append(ValidationError(field, "missing required field"))

    # Validate component
    comp = plan.get("component", "")
    if comp and comp not in VALID_COMPONENTS:
        errors.append(ValidationError(
            "component",
            f"unknown component: {comp}. Valid: {VALID_COMPONENTS}"
        ))

    # Validate target_node
    node = plan.get("target_node", "")
    if node and node not in VALID_NODES:
        errors.append(ValidationError(
            "target_node",
            f"unknown node: {node}. Valid: {VALID_NODES}"
        ))

    # Validate install_method
    method = plan.get("install_method", "")
    if method and method not in VALID_INSTALL_METHODS:
        errors.append(ValidationError(
            "install_method",
            f"unknown method: {method}. Valid: {VALID_INSTALL_METHODS}"
        ))

    # Validate rollback_method
    rb_method = plan.get("rollback_method", "")
    if rb_method and rb_method not in VALID_ROLLBACK_METHODS:
        errors.append(ValidationError(
            "rollback_method",
            f"unknown method: {rb_method}. Valid: {VALID_ROLLBACK_METHODS}"
        ))

    # Validate health_gates
    gates = plan.get("health_gates", [])
    if not isinstance(gates, list):
        errors.append(ValidationError("health_gates", "must be a list"))
    elif len(gates) == 0:
        errors.append(ValidationError("health_gates", "at least one health gate required"))
    else:
        for i, gate in enumerate(gates):
            for field in REQUIRED_HEALTH_GATE_FIELDS:
                if field not in gate:
                    errors.append(ValidationError(
                        f"health_gates[{i}].{field}",
                        "missing required health gate field"
                    ))

    # Validate canary_required is boolean
    if "canary_required" in plan:
        if not isinstance(plan["canary_required"], bool):
            errors.append(ValidationError(
                "canary_required", "must be boolean"
            ))

    # Validate operator_approval_required is boolean
    if "operator_approval_required" in plan:
        if not isinstance(plan["operator_approval_required"], bool):
            errors.append(ValidationError(
                "operator_approval_required", "must be boolean"
            ))
        elif not plan["operator_approval_required"]:
            errors.append(ValidationError(
                "operator_approval_required",
                "must be true for all upgrades",
                severity="warning"
            ))

    # Validate rollback_target is not empty
    if "rollback_target" in plan:
        if not plan["rollback_target"]:
            errors.append(ValidationError(
                "rollback_target",
                "must not be empty (rollback gate: no rollback target, no upgrade)"
            ))

    # Validate state_sequence if present
    if "state_sequence" in plan:
        for i, state in enumerate(plan["state_sequence"]):
            if state not in VALID_STATES:
                errors.append(ValidationError(
                    f"state_sequence[{i}]",
                    f"invalid state: {state}. Valid: {VALID_STATES}"
                ))

    # Check no secrets in plan
    plan_str = json.dumps(plan)
    secret_patterns = ["PRIVATE KEY", "sk-", "ghp_", "gho_", "api_key", "token="]
    for pat in secret_patterns:
        if pat.lower() in plan_str.lower():
            errors.append(ValidationError(
                "security",
                f"potential secret pattern found: {pat}",
                severity="critical"
            ))

    return errors


def self_check():
    """Run self-validation with fixture data."""
    print("=== upgrade_plan_validate.py self-check ===")

    # Valid plan
    valid_plan = {
        "plan_id": "test-001",
        "schema_version": 1,
        "component": "opencode-runtime",
        "from_version": "1.17.4",
        "to_version": "1.18.0",
        "source": "npm registry",
        "install_method": "npm_global",
        "target_node": "5bao",
        "canary_required": True,
        "rollback_target": "1.17.4",
        "rollback_method": "version_pin",
        "health_gates": [
            {
                "gate_name": "version_check",
                "command": "opencode --version",
                "expected_result": "1.18.0",
            },
            {
                "gate_name": "smoke_test",
                "command": "echo smoke",
                "expected_result": "smoke",
            },
        ],
        "operator_approval_required": True,
        "created_at": "2026-06-19T00:00:00Z",
    }
    errors = validate_plan(valid_plan)
    real_errors = [e for e in errors if e.severity == "error"]
    assert len(real_errors) == 0, f"valid plan should have 0 errors, got: {errors}"
    print("  PASS  valid plan accepted")

    # Invalid component
    bad_comp = dict(valid_plan, component="nonexistent")
    errors = validate_plan(bad_comp)
    assert any("component" in e.field for e in errors), "should reject bad component"
    print("  PASS  invalid component rejected")

    # Missing required field
    missing = dict(valid_plan)
    del missing["rollback_method"]
    errors = validate_plan(missing)
    assert any("rollback_method" in e.field for e in errors), "should catch missing field"
    print("  PASS  missing field rejected")

    # Empty health gates
    no_gates = dict(valid_plan, health_gates=[])
    errors = validate_plan(no_gates)
    assert any("health_gates" in e.field for e in errors), "should require health gates"
    print("  PASS  empty health gates rejected")

    # operator_approval_required=false
    no_approval = dict(valid_plan, operator_approval_required=False)
    errors = validate_plan(no_approval)
    assert any("operator_approval" in e.field for e in errors), "should warn on no approval"
    print("  PASS  operator_approval_required=false warning")

    # Check constants
    assert len(VALID_COMPONENTS) >= 10, "should have at least 10 valid components"
    assert len(VALID_STATES) == 11, "should have 11 valid states"
    assert len(VALID_ROLLBACK_METHODS) == 4, "should have 4 rollback methods"
    print(f"  PASS  constants: {len(VALID_COMPONENTS)} components, "
          f"{len(VALID_STATES)} states, {len(VALID_ROLLBACK_METHODS)} rollback methods")

    # Fixture file validation
    fixture_path = "docs/reports/upgrade-plan-fixture.json"
    try:
        with open(fixture_path) as f:
            fixture = json.load(f)
        errors = validate_plan(fixture)
        real_errors = [e for e in errors if e.severity == "error"]
        print(f"  PASS  fixture validation: {len(real_errors)} errors, "
              f"{len(errors) - len(real_errors)} warnings")
    except FileNotFoundError:
        print(f"  SKIP  fixture file not found: {fixture_path}")
    except json.JSONDecodeError as e:
        print(f"  FAIL  fixture JSON parse error: {e}")
        return 1

    print("=== self-check PASSED ===")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Upgrade plan validator")
    parser.add_argument("plan_file", nargs="?", help="Path to plan JSON file")
    parser.add_argument("--self-check", action="store_true", help="Run self-validation")
    args = parser.parse_args()

    if args.self_check:
        sys.exit(self_check())

    if not args.plan_file:
        parser.error("plan_file required (or use --self-check)")

    with open(args.plan_file) as f:
        plan = json.load(f)

    errors = validate_plan(plan)

    if not errors:
        print("VALID  plan passed all checks")
        sys.exit(0)

    for err in errors:
        print(err)

    real_errors = [e for e in errors if e.severity in ("error", "critical")]
    if real_errors:
        print(f"\nINVALID  {len(real_errors)} error(s) found")
        sys.exit(1)
    else:
        print(f"\nVALID_WITH_WARNINGS  {len(errors)} warning(s)")
        sys.exit(0)


if __name__ == "__main__":
    main()
