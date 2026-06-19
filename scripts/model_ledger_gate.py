#!/usr/bin/env python3
"""model_ledger_gate.py — MODEL_LEDGER Enforcement Gate v1.0.0

Enforces that reports with terminal statuses (PASS, MERGE_READY, FREEZE_PASS,
PROMOTION_PASS) contain complete MODEL_LEDGER, NODE_MODEL_SUMMARY,
RATE_LIMIT_EVENT_LEDGER, FALLBACK_DECISION_LEDGER, and COOLDOWN_STATE_SUMMARY.

Usage:
    python scripts/model_ledger_gate.py --validate REPORT_JSON
    python scripts/model_ledger_gate.py --self-check
    python scripts/model_ledger_gate.py --fixture PATH

Exit codes:
    0 = gate passed
    1 = gate failed
    2 = usage error
"""

__version__ = "1.0.0"

import json
import sys
from pathlib import Path

# --- Constants ---

TERMINAL_STATUSES = {"PASS", "MERGE_READY", "FREEZE_PASS", "PROMOTION_PASS"}

MODEL_LEDGER_REQUIRED_FIELDS = [
    "node", "job_id", "role", "planned_model", "actual_model",
    "provider", "opencode_provider_alias", "fallback_used",
    "call_count", "token_usage_or_unavailable_reason",
    "duration", "exit_code", "rate_limit", "final_status",
]

# fallback_from, fallback_to, fallback_reason are conditionally required
MODEL_LEDGER_CONDITIONAL_FIELDS = ["fallback_from", "fallback_to", "fallback_reason"]

NODE_MODEL_SUMMARY_REQUIRED_FIELDS = [
    "node", "opencode_version", "models_used_this_run",
    "total_model_calls", "successful_model_calls", "failed_model_calls",
    "fallback_count", "rate_limit_count", "cooldown_state",
]

RATE_LIMIT_EVENT_REQUIRED_FIELDS = [
    "timestamp", "node", "affected_model", "provider", "error_type",
    "exit_code", "binary_ok", "rollback_required",
    "cooldown_action", "fallback_action",
]

RATE_LIMIT_ERROR_TYPES = {
    "RL-TRANSIENT", "RL-QUOTA", "AUTH-ERR", "BIN-FAIL", "PROV-UNAVAIL", "UNKNOWN",
}

# BIN-FAIL is the ONLY error type that allows rollback
ROLLBACK_ALLOWED_ERROR_TYPES = {"BIN-FAIL"}

FALLBACK_DECISION_REQUIRED_FIELDS = [
    "timestamp", "job_id", "node", "fallback_from", "fallback_to",
    "fallback_reason", "fallback_chain_position",
    "operator_approval_required", "final_status",
]

COOLDOWN_STATE_REQUIRED_FIELDS = [
    "node", "model", "consecutive_rate_limits",
    "current_cooldown_seconds", "cooldown_action",
]

FORBIDDEN_TOKEN_VALUES = {"", "unknown", "tbd", "n/a", "null", "none"}

NO_MODEL_CALL_PREFIX = "no_model_call"


# --- Validation Functions ---

def validate_report(report: dict) -> list:
    """Validate a report against all gate rules. Returns list of errors."""
    errors = []
    has_terminal = _has_terminal_status(report)

    # Rule 1: Terminal status requires MODEL_LEDGER
    if has_terminal:
        ledger = report.get("MODEL_LEDGER")
        if not ledger:
            errors.append("GATE-01: Terminal status found but MODEL_LEDGER is missing")
            return errors  # Can't check further without ledger

    ledger = report.get("MODEL_LEDGER", [])
    node_summary = report.get("NODE_MODEL_SUMMARY", [])
    rate_limit_ledger = report.get("RATE_LIMIT_EVENT_LEDGER", [])
    fallback_ledger = report.get("FALLBACK_DECISION_LEDGER", [])
    cooldown_summary = report.get("COOLDOWN_STATE_SUMMARY", [])

    # Rule 2: MODEL_LEDGER entry completeness
    for i, entry in enumerate(ledger):
        entry_errors = _validate_ledger_entry(entry, i)
        errors.extend(entry_errors)

    # Rule 3: No-model-call entries must have correct format
    for i, entry in enumerate(ledger):
        if entry.get("call_count", -1) == 0:
            pm = str(entry.get("planned_model", "")).upper()
            am = str(entry.get("actual_model", "")).upper()
            tok = str(entry.get("token_usage_or_unavailable_reason", ""))
            if pm not in ("N/A", "NA", "NONE"):
                errors.append(
                    f"LEDGER-{i}: call_count=0 but planned_model={entry.get('planned_model')} "
                    f"(expected N/A)"
                )
            if am not in ("N/A", "NA", "NONE"):
                errors.append(
                    f"LEDGER-{i}: call_count=0 but actual_model={entry.get('actual_model')} "
                    f"(expected N/A)"
                )
            if not tok.startswith(NO_MODEL_CALL_PREFIX):
                errors.append(
                    f"LEDGER-{i}: call_count=0 but token_usage_or_unavailable_reason="
                    f"'{tok}' (expected no_model_call:<reason>)"
                )

    # Rule 4: NODE_MODEL_SUMMARY must exist
    if has_terminal and not node_summary:
        errors.append("GATE-04: Terminal status found but NODE_MODEL_SUMMARY is missing")

    # Rule 5: rate_limit=true requires RATE_LIMIT_EVENT_LEDGER
    has_rate_limit = any(e.get("rate_limit") for e in ledger)
    if has_rate_limit and not rate_limit_ledger:
        errors.append(
            "GATE-05: rate_limit=true in MODEL_LEDGER but "
            "RATE_LIMIT_EVENT_LEDGER is missing"
        )
    # Validate rate limit entries
    for i, entry in enumerate(rate_limit_ledger):
        rl_errors = _validate_rate_limit_entry(entry, i)
        errors.extend(rl_errors)

    # Rule 6: rate limit must not trigger binary rollback
    for i, entry in enumerate(rate_limit_ledger):
        et = entry.get("error_type", "")
        rr = entry.get("rollback_required")
        if et in RATE_LIMIT_ERROR_TYPES - ROLLBACK_ALLOWED_ERROR_TYPES and rr:
            errors.append(
                f"RATE_LIMIT-{i}: error_type={et} must not have "
                f"rollback_required=true (only BIN-FAIL allows rollback)"
            )

    # Rule 6b: exit_code must match error_type (no misclassification)
    EXIT_CODE_ERROR_MAP = {124: "RL-TRANSIENT", 139: "BIN-FAIL"}
    for i, entry in enumerate(rate_limit_ledger):
        ec = entry.get("exit_code")
        et = entry.get("error_type", "")
        expected_et = EXIT_CODE_ERROR_MAP.get(ec)
        if expected_et and et != expected_et:
            errors.append(
                f"RATE_LIMIT-{i}: exit_code={ec} maps to {expected_et} "
                f"but error_type={et} (misclassification)"
            )

    # Rule 7: fallback_used=true requires FALLBACK_DECISION_LEDGER
    has_fallback = any(e.get("fallback_used") for e in ledger)
    if has_fallback and not fallback_ledger:
        errors.append(
            "GATE-07: fallback_used=true in MODEL_LEDGER but "
            "FALLBACK_DECISION_LEDGER is missing"
        )
    # Validate fallback entries
    for i, entry in enumerate(fallback_ledger):
        fb_errors = _validate_fallback_entry(entry, i)
        errors.extend(fb_errors)

    # Also check MODEL_LEDGER fallback fields
    for i, entry in enumerate(ledger):
        if entry.get("fallback_used"):
            for field in MODEL_LEDGER_CONDITIONAL_FIELDS:
                val = entry.get(field)
                if not val or str(val).lower() in ("null", "none", ""):
                    errors.append(
                        f"LEDGER-{i}: fallback_used=true but {field} is empty/null"
                    )

    # Rule 8: COOLDOWN_STATE_SUMMARY must exist
    if has_terminal and not cooldown_summary:
        # Check if there's a reason field
        cooldown_reason = report.get("COOLDOWN_NOT_APPLICABLE_REASON")
        if not cooldown_reason:
            errors.append(
                "GATE-08: Terminal status found but COOLDOWN_STATE_SUMMARY "
                "is missing and no COOLDOWN_NOT_APPLICABLE_REASON provided"
            )

    # Rule 9: token_usage must not be empty/unknown/TBD
    for i, entry in enumerate(ledger):
        tok = str(entry.get("token_usage_or_unavailable_reason", "")).strip().lower()
        if tok in FORBIDDEN_TOKEN_VALUES:
            errors.append(
                f"LEDGER-{i}: token_usage_or_unavailable_reason is "
                f"'{entry.get('token_usage_or_unavailable_reason')}' "
                f"(must not be empty/unknown/TBD)"
            )

    return errors


def _has_terminal_status(report: dict) -> bool:
    """Check if report contains any terminal status."""
    # Check top-level status
    top_status = str(report.get("status", "")).upper()
    if top_status in TERMINAL_STATUSES:
        return True
    # Check in MODEL_LEDGER entries
    for entry in report.get("MODEL_LEDGER", []):
        fs = str(entry.get("final_status", "")).upper()
        if fs in TERMINAL_STATUSES:
            return True
    return False


def _validate_ledger_entry(entry: dict, index: int) -> list:
    """Validate a single MODEL_LEDGER entry."""
    errors = []
    for field in MODEL_LEDGER_REQUIRED_FIELDS:
        if field not in entry:
            errors.append(f"LEDGER-{index}: missing required field '{field}'")
    # Check for conditional fields when fallback_used=true
    if entry.get("fallback_used"):
        for field in MODEL_LEDGER_CONDITIONAL_FIELDS:
            val = entry.get(field)
            if not val or str(val).lower() in ("null", "none", ""):
                errors.append(
                    f"LEDGER-{index}: fallback_used=true but {field} is missing/empty"
                )
    return errors


def _validate_rate_limit_entry(entry: dict, index: int) -> list:
    """Validate a single RATE_LIMIT_EVENT_LEDGER entry."""
    errors = []
    for field in RATE_LIMIT_EVENT_REQUIRED_FIELDS:
        if field not in entry:
            errors.append(f"RATE_LIMIT-{index}: missing required field '{field}'")
    et = entry.get("error_type", "")
    if et and et not in RATE_LIMIT_ERROR_TYPES:
        errors.append(
            f"RATE_LIMIT-{index}: unknown error_type '{et}' "
            f"(expected one of {RATE_LIMIT_ERROR_TYPES})"
        )
    return errors


def _validate_fallback_entry(entry: dict, index: int) -> list:
    """Validate a single FALLBACK_DECISION_LEDGER entry."""
    errors = []
    for field in FALLBACK_DECISION_REQUIRED_FIELDS:
        if field not in entry:
            errors.append(f"FALLBACK-{index}: missing required field '{field}'")
    # from/to/reason must not be empty
    for field in ("fallback_from", "fallback_to", "fallback_reason"):
        val = entry.get(field)
        if not val or str(val).lower() in ("null", "none", ""):
            errors.append(f"FALLBACK-{index}: {field} is empty/null")
    return errors


# --- Self-Check ---

def self_check() -> dict:
    """Run self-check with fixture scenarios."""
    fixture_path = Path(__file__).parent.parent / "docs" / "reports" / "model-ledger-gate-fixture.json"
    if not fixture_path.exists():
        return {"passed": False, "error": f"Fixture not found: {fixture_path}"}
    return run_fixture(fixture_path)


def run_fixture(fixture_path: str) -> dict:
    """Run fixture validation. Returns {passed, scenarios, errors}."""
    with open(fixture_path, "r", encoding="utf-8") as f:
        fixtures = json.load(f)

    results = []
    all_passed = True

    for scenario in fixtures.get("scenarios", []):
        sid = scenario.get("id", "unknown")
        report = scenario.get("report", {})
        expected_pass = scenario.get("expected_gate_pass", True)
        description = scenario.get("description", "")

        errors = validate_report(report)
        gate_passed = len(errors) == 0

        match = gate_passed == expected_pass
        status = "PASS" if match else "FAIL"

        results.append({
            "id": sid,
            "description": description,
            "expected_pass": expected_pass,
            "actual_pass": gate_passed,
            "match": match,
            "status": status,
            "errors": errors if not match else [],
        })

        if not match:
            all_passed = False

    return {
        "passed": all_passed,
        "version": __version__,
        "total": len(results),
        "passed_count": sum(1 for r in results if r["status"] == "PASS"),
        "failed_count": sum(1 for r in results if r["status"] == "FAIL"),
        "scenarios": results,
    }


# --- CLI ---

def main():
    import argparse
    parser = argparse.ArgumentParser(description="MODEL_LEDGER Enforcement Gate")
    parser.add_argument("--validate", metavar="REPORT_JSON", help="Validate a report JSON file")
    parser.add_argument("--self-check", action="store_true", help="Run self-check with fixtures")
    parser.add_argument("--fixture", metavar="PATH", help="Run fixture validation")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"=== SELF-CHECK ===")
            print(f"  Version: {result.get('version')}")
            print(f"  Total: {result.get('total')}")
            print(f"  Passed: {result.get('passed_count')}")
            print(f"  Failed: {result.get('failed_count')}")
            for s in result.get("scenarios", []):
                print(f"  {s['status']}  {s['id']}: {s['description']}")
                if s["errors"]:
                    for e in s["errors"]:
                        print(f"        {e}")
            print(f"\n  Self-check: {'PASSED' if result['passed'] else 'FAILED'}")
        sys.exit(0 if result["passed"] else 1)

    if args.fixture:
        result = run_fixture(args.fixture)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"=== FIXTURE VALIDATION: {args.fixture} ===")
            print(f"  Scenarios: {result['total']}")
            for s in result["scenarios"]:
                print(f"  {s['status']}  {s['id']}: {s['description']}")
                if s["errors"]:
                    for e in s["errors"]:
                        print(f"        {e}")
            print(f"\n  Results: {result['passed_count']}/{result['total']} passed")
        sys.exit(0 if result["passed"] else 1)

    if args.validate:
        with open(args.validate, "r", encoding="utf-8") as f:
            report = json.load(f)
        errors = validate_report(report)
        if args.json:
            print(json.dumps({"passed": len(errors) == 0, "errors": errors}, indent=2))
        else:
            if errors:
                print("GATE FAILED:")
                for e in errors:
                    print(f"  - {e}")
            else:
                print("GATE PASSED")
        sys.exit(0 if not errors else 1)

    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
