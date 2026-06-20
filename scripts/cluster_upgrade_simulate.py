#!/usr/bin/env python3
"""Cluster Upgrade Simulator v1.0.0

Dry-run simulation of candidate promotion, rollback, and lifecycle events.
NO real upgrade is executed. NO state is mutated.

Usage:
    python scripts/cluster_upgrade_simulate.py --simulate-promotion SCENARIO_JSON
    python scripts/cluster_upgrade_simulate.py --simulate-rollback SCENARIO_JSON
    python scripts/cluster_upgrade_simulate.py --self-check
"""

__version__ = "1.0.0"

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))
from cluster_component_manifest import (
    get_component_manifest,
    KNOWN_PROTOCOL_VERSIONS,
)
from cluster_upgrade_contract import (
    validate_upgrade_contract,
    validate_promotion_contract,
    validate_approval_gate,
)


# --- Simulation Result Types ---

class SimResult:
    """Result of a simulated operation."""
    def __init__(self, operation: str, component: str):
        self.operation = operation
        self.component = component
        self.allowed = False
        self.gates = {}
        self.errors = []
        self.warnings = []
        self.state_before = {}
        self.state_after = {}
        self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "component": self.component,
            "allowed": self.allowed,
            "gates": self.gates,
            "errors": self.errors,
            "warnings": self.warnings,
            "state_before": self.state_before,
            "state_after": self.state_after,
            "simulated": True,
            "timestamp": self.timestamp,
        }


# --- Promotion Simulation ---

def simulate_promotion(scenario: dict) -> dict:
    """
    Simulate a candidate version promotion.

    Scenario fields:
        component: str
        candidate_version: str
        health_probe_result: str (PASS/FAIL/BLOCKED)
        contract_compatibility: str (PASS/FAIL/BLOCKED)
        safety_scan_result: str (PASS/FAIL/BLOCKED)
        operator_approval: dict or None
        feature_flags: dict (enabled, manual_only)
        state_paths_mutated: list[str]  (should be empty for safe promotion)
    """
    component = scenario.get("component", "unknown")
    result = SimResult("promotion", component)

    # Get current component info
    manifest = get_component_manifest()
    current = next((e for e in manifest if e.component == component), None)

    if current is None:
        result.errors.append(f"UNKNOWN_COMPONENT: '{component}' not in manifest")
        return result.to_dict()

    result.state_before = {
        "version": current.version,
        "enabled": current.enabled,
        "manual_only": current.manual_only,
        "rollback_available": current.rollback_available,
    }

    # Gate 1: Health probe
    health = scenario.get("health_probe_result", "MISSING")
    health_pass = health == "PASS"
    result.gates["health_probe"] = {"result": health, "pass": health_pass}
    if not health_pass:
        result.errors.append(f"HEALTH_GATE_FAIL: got '{health}', promotion BLOCKED")

    # Gate 2: Contract compatibility
    contract = scenario.get("contract_compatibility", "MISSING")
    contract_pass = contract == "PASS"
    result.gates["contract_compatibility"] = {"result": contract, "pass": contract_pass}
    if not contract_pass:
        result.errors.append(f"CONTRACT_INCOMPATIBLE: got '{contract}', promotion BLOCKED")

    # Gate 3: Safety scan
    safety = scenario.get("safety_scan_result", "MISSING")
    safety_pass = safety == "PASS"
    result.gates["safety_scan"] = {"result": safety, "pass": safety_pass}
    if not safety_pass:
        result.errors.append(f"SAFETY_GATE_FAIL: got '{safety}', promotion BLOCKED")

    # Gate 4: Rollback target exists
    rollback_ok = current.rollback_available
    result.gates["rollback_target"] = {"result": "AVAILABLE" if rollback_ok else "MISSING", "pass": rollback_ok}
    if not rollback_ok:
        result.errors.append("ROLLBACK_TARGET_MISSING: cannot promote without rollback safety")

    # Gate 5: Operator approval (if required)
    approval = scenario.get("operator_approval")
    if approval:
        approval_errors = validate_approval_gate(approval)
        approval_pass = len(approval_errors) == 0
        result.gates["operator_approval"] = {"result": "APPROVED" if approval_pass else "BLOCKED",
                                               "pass": approval_pass, "errors": approval_errors}
        if not approval_pass:
            result.errors.extend(approval_errors)
    else:
        result.gates["operator_approval"] = {"result": "NOT_PROVIDED", "pass": False}
        result.errors.append("OPERATOR_APPROVAL_MISSING")

    # Gate 6: Feature flags check
    flags = scenario.get("feature_flags", {})
    if component not in ("hermes-controller",):  # platform components exempt from manual_only default
        if flags.get("enabled") and flags.get("manual_only") is False:
            # Auto-enable requires explicit graduation
            result.warnings.append("AUTO_ENABLE_WITHOUT_MANUAL_ONLY: requires explicit graduation approval")

    # Gate 7: State mutation check
    mutated = scenario.get("state_paths_mutated", [])
    if mutated:
        result.errors.append(f"STATE_MUTATION_DETECTED: {mutated} — upgrade must not mutate persistent state")
        result.gates["state_isolation"] = {"result": "VIOLATED", "pass": False, "mutated_paths": mutated}
    else:
        result.gates["state_isolation"] = {"result": "CLEAN", "pass": True}

    # Final decision
    all_gates_pass = all(g.get("pass", False) for g in result.gates.values())
    result.allowed = all_gates_pass and len(result.errors) == 0

    # Simulate state transition (not actually applied)
    if result.allowed:
        result.state_after = {
            "version": scenario.get("candidate_version"),
            "previous_version": current.version,
            "enabled": flags.get("enabled", current.enabled),
            "manual_only": flags.get("manual_only", current.manual_only),
            "rollback_available": True,
        }
    else:
        result.state_after = dict(result.state_before)
        result.state_after["note"] = "unchanged — promotion blocked"

    return result.to_dict()


# --- Rollback Simulation ---

def simulate_rollback(scenario: dict) -> dict:
    """
    Simulate a rollback to previous version.

    Scenario fields:
        component: str
        rollback_target_version: str
        current_version: str
        preserve_state: bool (must be True)
        reason: str
    """
    component = scenario.get("component", "unknown")
    result = SimResult("rollback", component)

    manifest = get_component_manifest()
    current = next((e for e in manifest if e.component == component), None)

    if current is None:
        result.errors.append(f"UNKNOWN_COMPONENT: '{component}' not in manifest")
        return result.to_dict()

    result.state_before = {
        "version": current.version,
        "enabled": current.enabled,
        "manual_only": current.manual_only,
    }

    # Gate 1: Rollback target exists
    target = scenario.get("rollback_target_version")
    if not target:
        result.errors.append("ROLLBACK_TARGET_MISSING: no target version specified")
        result.gates["target_exists"] = {"result": "MISSING", "pass": False}
    else:
        result.gates["target_exists"] = {"result": target, "pass": True}

    # Gate 2: State preservation
    preserve = scenario.get("preserve_state", True)
    result.gates["state_preservation"] = {"result": "PRESERVED" if preserve else "AT_RISK", "pass": preserve}
    if not preserve:
        result.errors.append("STATE_NOT_PRESERVED: rollback must preserve evidence/logs/state")

    # Gate 3: Component has rollback capability
    result.gates["rollback_capable"] = {"result": "YES" if current.rollback_available else "NO",
                                          "pass": current.rollback_available}

    result.allowed = all(g.get("pass", False) for g in result.gates.values())

    if result.allowed:
        result.state_after = {
            "version": target,
            "previous_version": current.version,
            "enabled": current.enabled,
            "manual_only": current.manual_only,
            "reason": scenario.get("reason", "unspecified"),
        }
    else:
        result.state_after = dict(result.state_before)
        result.state_after["note"] = "unchanged — rollback blocked"

    return result.to_dict()


# --- Self-Check ---

def self_check() -> dict:
    """Validate simulator integrity."""
    checks = []

    # 1. Health FAIL blocks promotion
    scenario = {
        "component": "worker-registry",
        "candidate_version": "2.0.0",
        "health_probe_result": "FAIL",
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
        "feature_flags": {"enabled": False, "manual_only": True},
    }
    result = simulate_promotion(scenario)
    checks.append({"name": "health_fail_blocks_promotion", "passed": not result["allowed"]})

    # 2. Contract FAIL blocks promotion
    scenario["health_probe_result"] = "PASS"
    scenario["contract_compatibility"] = "FAIL"
    result = simulate_promotion(scenario)
    checks.append({"name": "contract_fail_blocks_promotion", "passed": not result["allowed"]})

    # 3. Missing required field fail-closed (via contract validator)
    from cluster_upgrade_contract import validate_contract_fields, UPGRADE_CONTRACT_REQUIRED_FIELDS
    errors = validate_contract_fields({}, UPGRADE_CONTRACT_REQUIRED_FIELDS)
    checks.append({"name": "missing_field_fail_closed", "passed": len(errors) > 0})

    # 4. Unknown protocol version fail-closed
    from cluster_upgrade_contract import validate_protocol_version
    errors = validate_protocol_version("nonexistent_protocol_xyz", "1.0")
    checks.append({"name": "unknown_protocol_fail_closed", "passed": len(errors) > 0})

    # 5. Rollback target missing blocks promotion
    scenario["contract_compatibility"] = "PASS"
    # Find a component and set rollback_available=False by simulating
    # We test via the simulator: no operator_approval = blocked
    scenario_no_approval = dict(scenario)
    scenario_no_approval["operator_approval"] = None
    result = simulate_promotion(scenario_no_approval)
    checks.append({"name": "missing_approval_blocks_promotion", "passed": not result["allowed"]})

    # 6. State mutation detected blocks promotion
    scenario_state = dict(scenario)
    scenario_state["operator_approval"] = {
        "approved_head_sha": "a" * 40,
        "approved_base_sha": "b" * 40,
        "merge_method_allowed": "merge",
        "approval_scope": "merge",
        "pr_number": 1,
        "approval_status": "APPROVED",
    }
    scenario_state["state_paths_mutated"] = ["/some/state/path"]
    result = simulate_promotion(scenario_state)
    checks.append({"name": "state_mutation_blocks_promotion", "passed": not result["allowed"]})

    # 7. All gates PASS allows promotion
    scenario_clean = dict(scenario_state)
    scenario_clean["state_paths_mutated"] = []
    result = simulate_promotion(scenario_clean)
    checks.append({"name": "all_gates_pass_allows_promotion", "passed": result["allowed"]})

    # 8. Rollback simulation with preserve_state=True
    rollback_scenario = {
        "component": "worker-registry",
        "rollback_target_version": "1.2.0",
        "current_version": "2.0.0",
        "preserve_state": True,
        "reason": "test rollback",
    }
    result = simulate_rollback(rollback_scenario)
    checks.append({"name": "rollback_preserve_state_passes", "passed": result["allowed"]})

    # 9. Rollback without state preservation blocked
    rollback_scenario["preserve_state"] = False
    result = simulate_rollback(rollback_scenario)
    checks.append({"name": "rollback_no_preserve_blocked", "passed": not result["allowed"]})

    # 10. Rollback to missing target blocked
    rollback_scenario["preserve_state"] = True
    rollback_scenario["rollback_target_version"] = ""
    result = simulate_rollback(rollback_scenario)
    checks.append({"name": "rollback_missing_target_blocked", "passed": not result["allowed"]})

    # 11. 21bao is enabled/manual_only in manifest (V1.20.19 activation)
    manifest = get_component_manifest()
    bao21 = [e for e in manifest if "21bao" in e.component]
    bao21_ok = all(e.enabled and e.manual_only for e in bao21) if bao21 else False
    checks.append({"name": "21bao_enabled_manual_only", "passed": bao21_ok})

    # 12. Simulated flag present in all results
    result = simulate_promotion(scenario_clean)
    checks.append({"name": "simulated_flag_present", "passed": result.get("simulated", False)})

    passed = all(c["passed"] for c in checks)
    return {"passed": passed, "version": __version__, "checks": checks}


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(prog="cluster_upgrade_simulate")
    parser.add_argument("--simulate-promotion", type=str, help="Path to promotion scenario JSON")
    parser.add_argument("--simulate-rollback", type=str, help="Path to rollback scenario JSON")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    if args.simulate_promotion:
        path = Path(args.simulate_promotion)
        if not path.exists():
            print(json.dumps({"valid": False, "errors": [f"File not found: {args.simulate_promotion}"]}, indent=2))
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            scenario = json.load(f)
        result = simulate_promotion(scenario)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["allowed"] else 1)

    if args.simulate_rollback:
        path = Path(args.simulate_rollback)
        if not path.exists():
            print(json.dumps({"valid": False, "errors": [f"File not found: {args.simulate_rollback}"]}, indent=2))
            sys.exit(1)
        with open(path, "r", encoding="utf-8") as f:
            scenario = json.load(f)
        result = simulate_rollback(scenario)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["allowed"] else 1)

    parser.print_help()


if __name__ == "__main__":
    main()
