#!/usr/bin/env python3
"""Cluster Upgrade Contract Validator v1.0.0

Validates protocol versions, required fields, and gate semantics
for cluster component upgrades. Fail-closed on unknown/missing.

Usage:
    python scripts/cluster_upgrade_contract.py --validate CONTRACT_JSON
    python scripts/cluster_upgrade_contract.py --self-check
"""

__version__ = "1.0.0"

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Import protocol versions from manifest
sys.path.insert(0, str(Path(__file__).parent))
from cluster_component_manifest import (
    KNOWN_PROTOCOL_VERSIONS,
    CONTROLLER_PROTOCOL_VERSION,
    WORKER_REGISTRY_SCHEMA_VERSION,
    RUNNER_PROTOCOL_VERSION,
    APPROVAL_GATE_SEMANTICS_VERSION,
    SCHEDULER_ROUTING_SCHEMA_VERSION,
)


# --- Required fields for upgrade contract ---

UPGRADE_CONTRACT_REQUIRED_FIELDS = [
    "contract_type",
    "source_version",
    "target_version",
    "component",
    "upgrade_class",
    "health_gate_result",
    "safety_gate_result",
    "feature_flags",
]

PROMOTION_CONTRACT_REQUIRED_FIELDS = [
    "candidate_version",
    "current_version",
    "previous_version",
    "health_probe_result",
    "contract_compatibility",
    "safety_scan_result",
    "operator_approval",
]

APPROVAL_GATE_REQUIRED_FIELDS = [
    "approved_head_sha",
    "approved_base_sha",
    "merge_method_allowed",
    "approval_scope",
    "pr_number",
    "approval_status",
]

# Known contract types
KNOWN_CONTRACT_TYPES = {
    "component_upgrade",
    "promotion",
    "rollback",
    "protocol_negotiation",
    "approval_gate",
    "worker_registration",
    "scheduler_routing",
}

# Feature flag required structure
FEATURE_FLAG_REQUIRED_FIELDS = ["enabled", "manual_only"]


# --- Validation Functions ---

def validate_protocol_version(protocol_name: str, version: str) -> list[str]:
    """Validate a protocol version against known versions. Fail-closed."""
    errors = []
    if protocol_name not in KNOWN_PROTOCOL_VERSIONS:
        errors.append(f"UNKNOWN_PROTOCOL: '{protocol_name}' not in known protocols {list(KNOWN_PROTOCOL_VERSIONS.keys())}")
        return errors  # fail-closed: unknown protocol = reject
    expected = KNOWN_PROTOCOL_VERSIONS[protocol_name]
    if version != expected:
        errors.append(f"PROTOCOL_MISMATCH: {protocol_name} expected={expected}, got={version}")
    return errors


def validate_contract_fields(contract: dict, required_fields: list[str]) -> list[str]:
    """Validate required fields present. Missing = fail-closed."""
    errors = []
    for field_name in required_fields:
        if field_name not in contract:
            errors.append(f"MISSING_FIELD: '{field_name}' is required but absent")
        elif contract[field_name] is None:
            errors.append(f"NULL_FIELD: '{field_name}' is null")
        elif isinstance(contract[field_name], str) and contract[field_name].strip() == "":
            errors.append(f"EMPTY_FIELD: '{field_name}' is empty string")
    return errors


def validate_contract_type(contract_type: str) -> list[str]:
    """Validate contract type is known. Unknown = fail-closed."""
    errors = []
    if contract_type not in KNOWN_CONTRACT_TYPES:
        errors.append(f"UNKNOWN_CONTRACT_TYPE: '{contract_type}' not in {list(KNOWN_CONTRACT_TYPES)}")
    return errors


def validate_health_gate(gate_result: str) -> list[str]:
    """Health gate must be PASS to allow promotion. Fail-closed."""
    errors = []
    if gate_result != "PASS":
        errors.append(f"HEALTH_GATE_NOT_PASS: got '{gate_result}', required 'PASS'")
    return errors


def validate_safety_gate(gate_result: str) -> list[str]:
    """Safety gate must be PASS. Fail-closed."""
    errors = []
    if gate_result != "PASS":
        errors.append(f"SAFETY_GATE_NOT_PASS: got '{gate_result}', required 'PASS'")
    return errors


def validate_feature_flags(flags: dict) -> list[str]:
    """Feature flags must have required structure."""
    errors = []
    for field_name in FEATURE_FLAG_REQUIRED_FIELDS:
        if field_name not in flags:
            errors.append(f"MISSING_FLAG: '{field_name}' in feature_flags")
        elif not isinstance(flags[field_name], bool):
            errors.append(f"INVALID_FLAG_TYPE: '{field_name}' must be bool, got {type(flags[field_name]).__name__}")
    return errors


def validate_approval_gate(approval: dict) -> list[str]:
    """Validate operator approval gate fields. Fail-closed on missing."""
    errors = validate_contract_fields(approval, APPROVAL_GATE_REQUIRED_FIELDS)
    if errors:
        return errors  # fail-closed

    # SHA must be 40-char hex
    import re
    sha_pattern = re.compile(r'^[0-9a-f]{40}$')
    head = approval.get("approved_head_sha", "")
    base = approval.get("approved_base_sha", "")
    if not sha_pattern.match(head):
        errors.append(f"INVALID_HEAD_SHA: must be 40-char hex, got '{head[:12]}...'")
    if not sha_pattern.match(base):
        errors.append(f"INVALID_BASE_SHA: must be 40-char hex, got '{base[:12]}...'")

    # Merge method must be in allowed set
    valid_methods = {"merge", "squash", "rebase"}
    method = approval.get("merge_method_allowed", "")
    if method not in valid_methods:
        errors.append(f"INVALID_MERGE_METHOD: '{method}' not in {valid_methods}")

    # Approval status
    if approval.get("approval_status") != "APPROVED":
        errors.append(f"NOT_APPROVED: status is '{approval.get('approval_status')}'")

    return errors


def validate_upgrade_contract(contract: dict) -> dict:
    """Full upgrade contract validation. Returns result dict."""
    all_errors = []
    all_warnings = []

    # 1. Required fields
    field_errors = validate_contract_fields(contract, UPGRADE_CONTRACT_REQUIRED_FIELDS)
    if field_errors:
        return {
            "valid": False,
            "errors": field_errors,
            "warnings": all_warnings,
            "phase": "field_validation",
        }
    all_errors.extend(field_errors)

    # 2. Contract type
    type_errors = validate_contract_type(contract.get("contract_type", ""))
    all_errors.extend(type_errors)

    # 3. Health gate
    health_errors = validate_health_gate(contract.get("health_gate_result", ""))
    all_errors.extend(health_errors)

    # 4. Safety gate
    safety_errors = validate_safety_gate(contract.get("safety_gate_result", ""))
    all_errors.extend(safety_errors)

    # 5. Feature flags
    flags = contract.get("feature_flags", {})
    flag_errors = validate_feature_flags(flags)
    all_errors.extend(flag_errors)

    # 6. Protocol compatibility (if protocol_version present)
    if "protocol_version" in contract:
        proto_errors = validate_protocol_version(
            contract.get("protocol_name", "unknown"),
            contract.get("protocol_version", "")
        )
        all_errors.extend(proto_errors)

    return {
        "valid": len(all_errors) == 0,
        "errors": all_errors,
        "warnings": all_warnings,
        "phase": "complete",
    }


def validate_promotion_contract(contract: dict) -> dict:
    """Validate a promotion-specific contract."""
    all_errors = []

    # Required promotion fields
    field_errors = validate_contract_fields(contract, PROMOTION_CONTRACT_REQUIRED_FIELDS)
    if field_errors:
        return {
            "valid": False,
            "errors": field_errors,
            "warnings": [],
            "phase": "field_validation",
        }

    # Health probe must be PASS
    health_errors = validate_health_gate(contract.get("health_probe_result", ""))
    all_errors.extend(health_errors)

    # Contract compatibility must be PASS
    if contract.get("contract_compatibility") != "PASS":
        all_errors.append(f"CONTRACT_INCOMPATIBLE: got '{contract.get('contract_compatibility')}'")

    # Safety scan must be PASS
    safety_errors = validate_safety_gate(contract.get("safety_scan_result", ""))
    all_errors.extend(safety_errors)

    # Rollback target must exist
    if not contract.get("previous_version"):
        all_errors.append("ROLLBACK_TARGET_MISSING: no previous_version for rollback safety")

    # Operator approval (if required)
    if contract.get("operator_approval_required", True):
        approval = contract.get("operator_approval")
        if not approval:
            all_errors.append("OPERATOR_APPROVAL_MISSING: required but not provided")
        else:
            approval_errors = validate_approval_gate(approval)
            all_errors.extend(approval_errors)

    return {
        "valid": len(all_errors) == 0,
        "errors": all_errors,
        "warnings": [],
        "phase": "complete",
    }


# --- Self-Check ---

def self_check() -> dict:
    """Run self-validation checks."""
    checks = []

    # 1. Known protocols defined
    checks.append({
        "name": "known_protocols_count_5",
        "passed": len(KNOWN_PROTOCOL_VERSIONS) == 5,
    })

    # 2. Required fields lists non-empty
    checks.append({
        "name": "upgrade_contract_fields_defined",
        "passed": len(UPGRADE_CONTRACT_REQUIRED_FIELDS) >= 5,
    })
    checks.append({
        "name": "promotion_contract_fields_defined",
        "passed": len(PROMOTION_CONTRACT_REQUIRED_FIELDS) >= 5,
    })
    checks.append({
        "name": "approval_gate_fields_defined",
        "passed": len(APPROVAL_GATE_REQUIRED_FIELDS) >= 5,
    })

    # 3. Known contract types
    checks.append({
        "name": "known_contract_types_count_7",
        "passed": len(KNOWN_CONTRACT_TYPES) == 7,
    })

    # 4. Missing field → fail-closed
    result = validate_contract_fields({}, UPGRADE_CONTRACT_REQUIRED_FIELDS)
    checks.append({
        "name": "missing_fields_fail_closed",
        "passed": len(result) > 0,
    })

    # 5. Unknown contract type → fail-closed
    result = validate_contract_type("nonexistent_type_xyz")
    checks.append({
        "name": "unknown_contract_type_fail_closed",
        "passed": len(result) > 0,
    })

    # 6. Health gate not PASS → fail-closed
    result = validate_health_gate("FAIL")
    checks.append({
        "name": "health_fail_blocks",
        "passed": len(result) > 0,
    })

    # 7. Safety gate not PASS → fail-closed
    result = validate_safety_gate("BLOCKED")
    checks.append({
        "name": "safety_fail_blocks",
        "passed": len(result) > 0,
    })

    # 8. Invalid SHA → fail-closed
    result = validate_approval_gate({
        "approved_head_sha": "short",
        "approved_base_sha": "also_short",
        "merge_method_allowed": "merge",
        "approval_scope": "merge",
        "pr_number": 1,
        "approval_status": "APPROVED",
    })
    checks.append({
        "name": "invalid_sha_fail_closed",
        "passed": len(result) > 0,
    })

    # 9. Valid contract passes
    valid_contract = {
        "contract_type": "component_upgrade",
        "source_version": "1.0.0",
        "target_version": "1.1.0",
        "component": "test",
        "upgrade_class": "workflow",
        "health_gate_result": "PASS",
        "safety_gate_result": "PASS",
        "feature_flags": {"enabled": False, "manual_only": True},
    }
    result = validate_upgrade_contract(valid_contract)
    checks.append({
        "name": "valid_contract_passes",
        "passed": result["valid"],
    })

    # 10. Missing feature flag → fail-closed
    bad_contract = dict(valid_contract)
    bad_contract["feature_flags"] = {}
    result = validate_upgrade_contract(bad_contract)
    checks.append({
        "name": "missing_feature_flag_fail_closed",
        "passed": not result["valid"],
    })

    # 11. Valid promotion contract
    valid_promo = {
        "candidate_version": "1.1.0",
        "current_version": "1.0.0",
        "previous_version": "0.9.0",
        "health_probe_result": "PASS",
        "contract_compatibility": "PASS",
        "safety_scan_result": "PASS",
        "operator_approval": {
            "approved_head_sha": "a" * 40,
            "approved_base_sha": "b" * 40,
            "merge_method_allowed": "merge",
            "approval_scope": "merge",
            "pr_number": 1,
            "approval_status": "APPROVED",
        },
    }
    result = validate_promotion_contract(valid_promo)
    checks.append({
        "name": "valid_promotion_passes",
        "passed": result["valid"],
    })

    # 12. Missing rollback target blocks promotion
    no_rollback = dict(valid_promo)
    no_rollback["previous_version"] = ""
    result = validate_promotion_contract(no_rollback)
    checks.append({
        "name": "missing_rollback_blocks_promotion",
        "passed": not result["valid"],
    })

    passed = all(c["passed"] for c in checks)
    return {"passed": passed, "version": __version__, "checks": checks}


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(prog="cluster_upgrade_contract")
    parser.add_argument("--validate", type=str, help="Path to contract JSON to validate")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    if args.validate:
        path = Path(args.validate)
        if not path.exists():
            print(json.dumps({"valid": False, "errors": [f"File not found: {args.validate}"]}, indent=2))
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            contract = json.load(f)
        result = validate_upgrade_contract(contract)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["valid"] else 1)

    parser.print_help()


if __name__ == "__main__":
    main()
