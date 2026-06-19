#!/usr/bin/env python3
"""Model routing and provider capacity fixture validator.

Validates fixture scenarios against policy rules defined in
docs/MODEL_ROUTING_AND_PROVIDER_CAPACITY.md.

Usage:
    python3 scripts/model_routing_validate.py [--fixture PATH] [--self-check]

Exit codes:
    0 = all scenarios pass
    1 = one or more scenarios fail
"""

import json
import sys
import os
from pathlib import Path

DEFAULT_FIXTURE = "docs/reports/model-routing-fixture.json"

RATE_LIMIT_ERROR_TYPES = {"RL-TRANSIENT", "RL-QUOTA"}
BINARY_FAILURE_ERROR_TYPES = {"BIN-FAIL"}
NON_ROLLBACK_ERROR_TYPES = {"RL-TRANSIENT", "RL-QUOTA", "AUTH-ERR", "PROV-UNAVAIL"}
ROLLBACK_ERROR_TYPES = {"BIN-FAIL"}

EXIT_CODE_TO_ERROR_TYPE = {
    0: None,
    124: "RL-TRANSIENT",
    139: "BIN-FAIL",
}


def classify_error(scenario: dict) -> str | None:
    """Classify error type from scenario fields."""
    if scenario.get("expected_error_type"):
        return scenario["expected_error_type"]

    exit_code = scenario.get("exit_code", 0)
    if exit_code in EXIT_CODE_TO_ERROR_TYPE:
        return EXIT_CODE_TO_ERROR_TYPE[exit_code]

    error_msg = scenario.get("error_message", "").lower()
    if "rate limit" in error_msg:
        return "RL-TRANSIENT"
    if "quota" in error_msg or "billing" in error_msg:
        return "RL-QUOTA"
    if "401" in error_msg or "auth" in error_msg:
        return "AUTH-ERR"
    if "segfault" in error_msg or "sigsegv" in error_msg:
        return "BIN-FAIL"
    if "connection refused" in error_msg or "timeout" in error_msg:
        return "PROV-UNAVAIL"
    if exit_code != 0:
        return "UNKNOWN"
    return None


def validate_scenario(scenario: dict) -> list:
    """Validate a single scenario against policy rules. Returns list of errors."""
    errors = []
    sid = scenario.get("id", "unknown")

    # Rule 1: When fallback_used is false, fallback fields must be null
    if not scenario.get("fallback_used", False):
        for field in ("fallback_from", "fallback_to", "fallback_reason"):
            if scenario.get(field) is not None:
                errors.append(
                    f"{sid}: {field} must be null when fallback_used=false"
                )

    # Rule 2: When fallback_used is true, fallback fields must be present
    if scenario.get("fallback_used", False):
        for field in ("fallback_from", "fallback_to", "fallback_reason"):
            if not scenario.get(field):
                errors.append(
                    f"{sid}: {field} required when fallback_used=true"
                )

    # Rule 3: Binary failure must not be classified as rate limit
    error_type = classify_error(scenario)
    if error_type in BINARY_FAILURE_ERROR_TYPES:
        if scenario.get("rate_limit", False):
            errors.append(
                f"{sid}: binary failure (exit {scenario.get('exit_code')}) "
                f"must not be classified as rate_limit=true"
            )

    # Rule 4: Rate limit must not trigger rollback
    if error_type in RATE_LIMIT_ERROR_TYPES:
        if scenario.get("expected_rollback_required", False):
            errors.append(
                f"{sid}: rate limit ({error_type}) must not trigger rollback"
            )

    # Rule 5: Binary failure must trigger rollback
    if error_type in ROLLBACK_ERROR_TYPES:
        if not scenario.get("expected_rollback_required", False):
            errors.append(
                f"{sid}: binary failure ({error_type}) must trigger rollback"
            )

    # Rule 6: planned_model provider suffix should match actual_model
    if scenario.get("actual_model") and scenario.get("planned_model"):
        planned = scenario["planned_model"]
        actual = scenario["actual_model"]
        if "/" in planned:
            planned_name = planned.split("/", 1)[1]
        else:
            planned_name = planned
        if actual != planned_name and not scenario.get("fallback_used", False):
            errors.append(
                f"{sid}: actual_model '{actual}' does not match planned "
                f"'{planned_name}' without fallback"
            )

    # Rule 7: Quarantined models must not be in active tier
    model_tiers = scenario.get("_model_tiers", {})
    if scenario.get("planned_model") in model_tiers:
        tier = model_tiers[scenario["planned_model"]]
        if tier == "quarantined":
            errors.append(
                f"{sid}: planned_model '{scenario['planned_model']}' is quarantined"
            )

    # Rule 8: final_status must match exit_code semantics
    expected_status = scenario.get("expected_final_status")
    exit_code = scenario.get("exit_code", 0)
    if expected_status == "PASS" and exit_code != 0:
        errors.append(
            f"{sid}: expected PASS but exit_code={exit_code}"
        )
    if expected_status == "RATE_LIMITED" and not scenario.get("rate_limit", False):
        errors.append(
            f"{sid}: expected RATE_LIMITED but rate_limit=false"
        )

    # Rule 9: binary_ok must be false for binary failures
    if error_type in BINARY_FAILURE_ERROR_TYPES:
        if scenario.get("expected_binary_ok", True):
            errors.append(
                f"{sid}: binary failure must set binary_ok=false"
            )

    # Rule 10: Cooldown escalation check
    consecutive = scenario.get("consecutive_rate_limits", 0)
    expected_cooldown = scenario.get("expected_cooldown_action")
    if consecutive >= 3 and expected_cooldown and "300" not in expected_cooldown:
        errors.append(
            f"{sid}: 3+ consecutive rate limits should trigger 300s cooldown, "
            f"got '{expected_cooldown}'"
        )

    return errors


def run_self_check():
    """Run self-check with minimal assertions."""
    print("=== SELF-CHECK ===")
    checks = 0
    passed = 0

    checks += 1
    result = classify_error({"exit_code": 124})
    if result == "RL-TRANSIENT":
        passed += 1
        print(f"  [{passed}/{checks}] classify_error(124) = RL-TRANSIENT: PASS")
    else:
        print(f"  [FAIL] classify_error(124) = {result}, expected RL-TRANSIENT")

    checks += 1
    result = classify_error({"exit_code": 139})
    if result == "BIN-FAIL":
        passed += 1
        print(f"  [{passed}/{checks}] classify_error(139) = BIN-FAIL: PASS")
    else:
        print(f"  [FAIL] classify_error(139) = {result}, expected BIN-FAIL")

    checks += 1
    errs = validate_scenario({
        "id": "self-check-3",
        "fallback_used": False,
        "fallback_from": "should-not-be-here",
        "exit_code": 0,
    })
    if errs:
        passed += 1
        print(f"  [{passed}/{checks}] null fallback fields enforced: PASS")
    else:
        print(f"  [FAIL] null fallback fields not enforced")

    checks += 1
    errs = validate_scenario({
        "id": "self-check-4",
        "exit_code": 139,
        "rate_limit": True,
        "expected_error_type": "BIN-FAIL",
    })
    if errs:
        passed += 1
        print(f"  [{passed}/{checks}] BIN-FAIL vs rate_limit conflict detected: PASS")
    else:
        print(f"  [FAIL] BIN-FAIL vs rate_limit conflict not detected")

    checks += 1
    errs = validate_scenario({
        "id": "self-check-5",
        "exit_code": 124,
        "rate_limit": True,
        "expected_error_type": "RL-TRANSIENT",
        "expected_rollback_required": True,
    })
    if errs:
        passed += 1
        print(f"  [{passed}/{checks}] rate-limit rollback guard: PASS")
    else:
        print(f"  [FAIL] rate-limit rollback guard not enforced")

    checks += 1
    errs = validate_scenario({
        "id": "self-check-6",
        "planned_model": "opencode/deepseek-v4-flash-free",
        "actual_model": "wrong-model",
        "fallback_used": False,
        "exit_code": 0,
    })
    if errs:
        passed += 1
        print(f"  [{passed}/{checks}] planned/actual mismatch without fallback: PASS")
    else:
        print(f"  [FAIL] planned/actual mismatch not detected")

    checks += 1
    errs = validate_scenario({
        "id": "self-check-7",
        "fallback_used": True,
        "fallback_from": None,
        "fallback_to": None,
        "fallback_reason": None,
        "exit_code": 0,
    })
    if errs:
        passed += 1
        print(f"  [{passed}/{checks}] fallback required fields: PASS")
    else:
        print(f"  [FAIL] fallback required fields not enforced")

    checks += 1
    errs = validate_scenario({
        "id": "self-check-8",
        "exit_code": 124,
        "rate_limit": True,
        "consecutive_rate_limits": 3,
        "expected_cooldown_action": "cooldown_30s",
        "expected_error_type": "RL-TRANSIENT",
    })
    if errs:
        passed += 1
        print(f"  [{passed}/{checks}] cooldown escalation (3+ -> 300s): PASS")
    else:
        print(f"  [FAIL] cooldown escalation not enforced")

    print(f"\n  Self-check: {passed}/{checks} passed")
    return passed == checks


def validate_fixture(fixture_path: str) -> bool:
    """Validate all scenarios in fixture file."""
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scenarios = data.get("scenarios", [])
    model_tiers = data.get("model_tiers", {})
    total = len(scenarios)
    passed = 0
    failed = 0
    all_errors = []

    print(f"=== FIXTURE VALIDATION: {fixture_path} ===")
    print(f"  Scenarios: {total}")
    print(f"  Model tiers: {len(model_tiers)}")
    print()

    for scenario in scenarios:
        scenario["_model_tiers"] = model_tiers
        errors = validate_scenario(scenario)
        sid = scenario.get("id", "unknown")
        if errors:
            failed += 1
            all_errors.extend(errors)
            print(f"  FAIL  {sid}")
            for err in errors:
                print(f"        {err}")
        else:
            passed += 1
            print(f"  PASS  {sid}")

    print(f"\n  Results: {passed}/{total} passed, {failed} failed")
    if all_errors:
        print(f"\n  Errors:")
        for err in all_errors:
            print(f"    - {err}")

    return failed == 0


def main():
    if "--self-check" in sys.argv:
        ok = run_self_check()
        sys.exit(0 if ok else 1)

    fixture_path = DEFAULT_FIXTURE
    for i, arg in enumerate(sys.argv):
        if arg == "--fixture" and i + 1 < len(sys.argv):
            fixture_path = sys.argv[i + 1]

    if not os.path.exists(fixture_path):
        print(f"ERROR: fixture not found: {fixture_path}", file=sys.stderr)
        sys.exit(1)

    ok = validate_fixture(fixture_path)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
