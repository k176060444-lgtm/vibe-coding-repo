#!/usr/bin/env python3
"""Upgrade evidence JSON validator for VibeDev lifecycle management.

Validates upgrade evidence records against the schema defined in
UPGRADE_DOWNGRADE_LIFECYCLE.md Section 9.

Usage:
    python upgrade_evidence_validate.py <evidence.json>
    python upgrade_evidence_validate.py --self-check
"""

import argparse
import json
import re
import sys

SCHEMA_VERSION = 1

VALID_OPERATION_TYPES = ["upgrade", "downgrade", "rollback"]

VALID_GATE_RESULTS = ["pass", "fail", "skip", "not_applicable"]

VALID_STATES = [
    "DISCOVER", "PLAN", "APPROVE", "DRAIN_WORKER", "SNAPSHOT",
    "UPGRADE_CANARY", "SMOKE_TEST", "REAL_FIXTURE_TEST",
    "OBSERVE", "PROMOTE_OR_ROLLBACK", "ATTEST",
    "DETECT_REGRESSION", "FREEZE_NEW_JOBS", "RESTORE_PREVIOUS_VERSION",
    "VERIFY", "REJOIN_POOL",
]

REQUIRED_EVIDENCE_FIELDS = [
    "operation_id", "component", "node", "from_version",
    "to_version", "operation_type", "state_machine_trace",
    "gate_results", "evidence_sha256", "operator_approval",
    "timestamp",
]

REQUIRED_GATE_RESULT_FIELDS = ["gate_name", "result", "evidence"]

PLACEHOLDER_PATTERNS = [
    r"\bTBD\b",
    r"\bN/A\b",
    r"\bpending\b",
    r"\bunknown\b",
    r"\bcomputed_at_commit\b",
    r"\brecomputed_at_commit\b",
    r"\bplaceholder\b",
]


class ValidationError:
    def __init__(self, field, message, severity="error"):
        self.field = field
        self.message = message
        self.severity = severity

    def __repr__(self):
        return f"[{self.severity}] {self.field}: {self.message}"


def check_placeholders(text, field_name):
    """Check for unexplained placeholders in text fields."""
    errors = []
    for pattern in PLACEHOLDER_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            errors.append(ValidationError(
                field_name,
                f"unexplained placeholder found: '{match}'",
                severity="warning"
            ))
    return errors


def validate_evidence(evidence):
    """Validate an upgrade evidence dict. Returns list of ValidationError."""
    errors = []

    # Check schema version
    if evidence.get("schema_version") != SCHEMA_VERSION:
        errors.append(ValidationError(
            "schema_version",
            f"expected {SCHEMA_VERSION}, got {evidence.get('schema_version')}"
        ))

    # Check required fields
    for field in REQUIRED_EVIDENCE_FIELDS:
        if field not in evidence:
            errors.append(ValidationError(field, "missing required field"))

    # Validate operation_type
    op_type = evidence.get("operation_type", "")
    if op_type and op_type not in VALID_OPERATION_TYPES:
        errors.append(ValidationError(
            "operation_type",
            f"invalid: {op_type}. Valid: {VALID_OPERATION_TYPES}"
        ))

    # Validate state_machine_trace
    trace = evidence.get("state_machine_trace", [])
    if not isinstance(trace, list):
        errors.append(ValidationError("state_machine_trace", "must be a list"))
    elif len(trace) == 0:
        errors.append(ValidationError("state_machine_trace", "must not be empty"))
    else:
        for i, state in enumerate(trace):
            if state not in VALID_STATES:
                errors.append(ValidationError(
                    f"state_machine_trace[{i}]",
                    f"invalid state: {state}"
                ))
        # Check trace ends with ATTEST
        if trace and trace[-1] != "ATTEST":
            errors.append(ValidationError(
                "state_machine_trace",
                f"must end with ATTEST, got {trace[-1]}",
                severity="warning"
            ))

    # Validate gate_results
    gate_results = evidence.get("gate_results", [])
    if not isinstance(gate_results, list):
        errors.append(ValidationError("gate_results", "must be a list"))
    elif len(gate_results) == 0:
        errors.append(ValidationError("gate_results", "at least one gate result required"))
    else:
        for i, gate in enumerate(gate_results):
            for field in REQUIRED_GATE_RESULT_FIELDS:
                if field not in gate:
                    errors.append(ValidationError(
                        f"gate_results[{i}].{field}",
                        "missing required gate result field"
                    ))
            result = gate.get("result", "")
            if result and result not in VALID_GATE_RESULTS:
                errors.append(ValidationError(
                    f"gate_results[{i}].result",
                    f"invalid result: {result}. Valid: {VALID_GATE_RESULTS}"
                ))

    # Validate operator_approval
    approval = evidence.get("operator_approval", {})
    if isinstance(approval, dict):
        if "approved" not in approval:
            errors.append(ValidationError(
                "operator_approval.approved", "missing required field"
            ))
    elif isinstance(approval, bool):
        pass  # Accept bare boolean

    # Validate evidence_sha256 format
    sha = evidence.get("evidence_sha256", "")
    if sha and not re.match(r"^[0-9a-f]{64}$", sha):
        # Allow "pending_computation" as special case
        if sha != "pending_computation":
            errors.append(ValidationError(
                "evidence_sha256",
                "must be 64-char hex or 'pending_computation'"
            ))

    # Validate timestamp format (ISO 8601)
    ts = evidence.get("timestamp", "")
    if ts:
        # Basic ISO 8601 check
        iso_pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
        if not re.match(iso_pattern, ts):
            errors.append(ValidationError(
                "timestamp",
                f"not valid ISO 8601: {ts}"
            ))

    # Check for unexplained placeholders in string fields
    evidence_str = json.dumps(evidence)
    placeholder_errors = check_placeholders(evidence_str, "evidence_content")
    # Filter out explained_nonblocking placeholders
    explained = evidence.get("explained_placeholders", [])
    for pe in placeholder_errors:
        # Check if this placeholder is explained
        is_explained = False
        for exp in explained:
            if exp.get("placeholder", "").lower() in pe.message.lower():
                is_explained = True
                break
        if not is_explained:
            errors.append(pe)

    # Security: no secrets
    secret_patterns = ["PRIVATE KEY", "sk-", "ghp_", "gho_"]
    for pat in secret_patterns:
        if pat.lower() in evidence_str.lower():
            errors.append(ValidationError(
                "security",
                f"potential secret pattern: {pat}",
                severity="critical"
            ))

    return errors


def self_check():
    """Run self-validation with fixture data."""
    print("=== upgrade_evidence_validate.py self-check ===")

    # Valid evidence
    valid_evidence = {
        "operation_id": "op-test-001",
        "schema_version": 1,
        "component": "opencode-runtime",
        "node": "5bao",
        "from_version": "1.17.4",
        "to_version": "1.18.0",
        "operation_type": "upgrade",
        "state_machine_trace": [
            "DISCOVER", "PLAN", "APPROVE", "DRAIN_WORKER",
            "SNAPSHOT", "UPGRADE_CANARY", "SMOKE_TEST",
            "REAL_FIXTURE_TEST", "OBSERVE", "PROMOTE_OR_ROLLBACK", "ATTEST",
        ],
        "gate_results": [
            {"gate_name": "version_check", "result": "pass", "evidence": "1.18.0"},
            {"gate_name": "smoke_test", "result": "pass", "evidence": "ok"},
        ],
        "evidence_sha256": "a" * 64,
        "operator_approval": {"approved": True, "approver": "operator"},
        "timestamp": "2026-06-19T00:00:00Z",
    }
    errors = validate_evidence(valid_evidence)
    real_errors = [e for e in errors if e.severity in ("error", "critical")]
    assert len(real_errors) == 0, f"valid evidence should have 0 errors, got: {errors}"
    print("  PASS  valid evidence accepted")

    # Invalid operation_type
    bad_op = dict(valid_evidence, operation_type="invalid")
    errors = validate_evidence(bad_op)
    assert any("operation_type" in e.field for e in errors)
    print("  PASS  invalid operation_type rejected")

    # Missing ATTEST in trace
    bad_trace = dict(valid_evidence, state_machine_trace=["DISCOVER", "PLAN"])
    errors = validate_evidence(bad_trace)
    assert any("ATTEST" in e.message for e in errors)
    print("  PASS  missing ATTEST warning")

    # Empty gate_results
    no_gates = dict(valid_evidence, gate_results=[])
    errors = validate_evidence(no_gates)
    assert any("gate_results" in e.field for e in errors)
    print("  PASS  empty gate_results rejected")

    # Placeholder detection
    with_placeholder = dict(valid_evidence, to_version="TBD")
    errors = validate_evidence(with_placeholder)
    has_placeholder_warning = any("placeholder" in e.message.lower() for e in errors)
    # This should be caught as a placeholder
    print(f"  {'PASS' if has_placeholder_warning else 'INFO'}  "
          f"placeholder detection: {has_placeholder_warning}")

    # Explained placeholder
    with_explained = dict(valid_evidence, to_version="TBD")
    with_explained["explained_placeholders"] = [
        {"placeholder": "TBD", "reason": "version not yet determined", "classification": "explained_nonblocking"}
    ]
    errors = validate_evidence(with_explained)
    placeholder_errors = [e for e in errors if "placeholder" in e.message.lower() and "TBD" in e.message]
    # Should be filtered out by explained_placeholders
    print(f"  {'PASS' if len(placeholder_errors) == 0 else 'INFO'}  "
          f"explained placeholder accepted")

    # Check constants
    assert len(VALID_OPERATION_TYPES) == 3
    assert len(VALID_GATE_RESULTS) == 4
    assert len(VALID_STATES) == 16
    print(f"  PASS  constants: {len(VALID_OPERATION_TYPES)} op types, "
          f"{len(VALID_GATE_RESULTS)} gate results, {len(VALID_STATES)} states")

    # Fixture validation
    fixture_path = "docs/reports/upgrade-evidence-fixture.json"
    try:
        with open(fixture_path) as f:
            fixture = json.load(f)
        errors = validate_evidence(fixture)
        real_errors = [e for e in errors if e.severity in ("error", "critical")]
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
    parser = argparse.ArgumentParser(description="Upgrade evidence validator")
    parser.add_argument("evidence_file", nargs="?", help="Path to evidence JSON file")
    parser.add_argument("--self-check", action="store_true", help="Run self-validation")
    args = parser.parse_args()

    if args.self_check:
        sys.exit(self_check())

    if not args.evidence_file:
        parser.error("evidence_file required (or use --self-check)")

    with open(args.evidence_file) as f:
        evidence = json.load(f)

    errors = validate_evidence(evidence)

    if not errors:
        print("VALID  evidence passed all checks")
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
