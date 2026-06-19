#!/usr/bin/env python3
"""vibe_report_status_gate.py — Report Status Gate v1.0.0

Integrates model_ledger_gate into the report/status output path.
Any report claiming terminal status (PASS, MERGE_READY, FREEZE_PASS,
PROMOTION_PASS) must pass model_ledger_gate before the status is accepted.

Usage:
    python scripts/vibe_report_status_gate.py --report REPORT_JSON [--json]
    python scripts/vibe_report_status_gate.py --self-check

Exit codes:
    0 = gate passed, terminal status allowed
    1 = gate failed, terminal status blocked
    2 = usage error
"""

__version__ = "1.0.0"

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from model_ledger_gate import validate_report, TERMINAL_STATUSES, __version__ as gate_version


def check_report_status(report: dict) -> dict:
    """Check if a report's terminal status is allowed by model_ledger_gate.

    Returns:
        {
            "status_allowed": bool,
            "terminal_status_found": str or None,
            "gate_passed": bool,
            "gate_errors": list,
            "model_ledger_gate_version": str,
        }
    """
    # Determine if report claims terminal status
    terminal_status = None
    top_status = str(report.get("status", "")).upper()
    if top_status in TERMINAL_STATUSES:
        terminal_status = top_status

    if not terminal_status:
        for entry in report.get("MODEL_LEDGER", []):
            fs = str(entry.get("final_status", "")).upper()
            if fs in TERMINAL_STATUSES:
                terminal_status = fs
                break

    # If no terminal status, gate is not applicable
    if not terminal_status:
        return {
            "status_allowed": True,
            "terminal_status_found": None,
            "gate_passed": True,
            "gate_errors": [],
            "gate_not_applicable": True,
            "model_ledger_gate_version": gate_version,
        }

    # Run gate validation
    errors = validate_report(report)
    gate_passed = len(errors) == 0

    return {
        "status_allowed": gate_passed,
        "terminal_status_found": terminal_status,
        "gate_passed": gate_passed,
        "gate_errors": errors,
        "gate_not_applicable": False,
        "model_ledger_gate_version": gate_version,
    }


def check_merge_readiness(report: dict) -> dict:
    """Check merge readiness including model_ledger_gate result.

    Returns:
        {
            "merge_ready": bool,
            "model_ledger_gate_result": str ("PASS" or "FAIL"),
            "checked_report_path": str or None,
            "gate_exit_code": int,
            "failure_reasons": list,
        }
    """
    result = check_report_status(report)

    # merge_ready requires both: terminal status found AND gate passed
    merge_ready = result["status_allowed"] and not result.get("gate_not_applicable", False)

    return {
        "merge_ready": merge_ready,
        "model_ledger_gate_result": "PASS" if result["gate_passed"] else "FAIL",
        "gate_exit_code": 0 if result["gate_passed"] else 1,
        "failure_reasons": result["gate_errors"],
        "terminal_status_found": result.get("terminal_status_found"),
        "model_ledger_gate_version": result["model_ledger_gate_version"],
    }


def self_check() -> dict:
    """Run self-check with integration test scenarios."""
    scenarios = _get_integration_scenarios()
    results = []
    all_passed = True

    for scenario in scenarios:
        sid = scenario["id"]
        report = scenario["report"]
        expected_allowed = scenario["expected_status_allowed"]
        expected_merge_ready = scenario.get("expected_merge_ready", expected_allowed)

        status_result = check_report_status(report)
        merge_result = check_merge_readiness(report)

        status_ok = status_result["status_allowed"] == expected_allowed
        merge_ok = merge_result["merge_ready"] == expected_merge_ready
        match = status_ok and merge_ok

        results.append({
            "id": sid,
            "description": scenario.get("description", ""),
            "expected_allowed": expected_allowed,
            "actual_allowed": status_result["status_allowed"],
            "expected_merge_ready": expected_merge_ready,
            "actual_merge_ready": merge_result["merge_ready"],
            "match": match,
            "status": "PASS" if match else "FAIL",
            "errors": status_result["gate_errors"] if not match else [],
        })

        if not match:
            all_passed = False

    return {
        "passed": all_passed,
        "version": __version__,
        "gate_version": gate_version,
        "total": len(results),
        "passed_count": sum(1 for r in results if r["status"] == "PASS"),
        "failed_count": sum(1 for r in results if r["status"] == "FAIL"),
        "scenarios": results,
    }


def _get_integration_scenarios() -> list:
    """Integration test scenarios for report status gate."""
    return [
        # === POSITIVE CASES ===
        {
            "id": "int-01-valid-v1205-report",
            "description": "Valid V1.20.5 report: 3 live + 2 fixture/mock -> allowed",
            "expected_status_allowed": True,
            "expected_merge_ready": True,
            "report": {
                "status": "PASS",
                "MODEL_LEDGER": [
                    {"node": "5bao", "job_id": "e2e-001", "role": "implementer",
                     "planned_model": "opencode/deepseek-v4-flash-free",
                     "actual_model": "deepseek-v4-flash-free", "provider": "opencode",
                     "opencode_provider_alias": "opencode", "fallback_used": False,
                     "fallback_from": None, "fallback_to": None, "fallback_reason": None,
                     "call_count": 1, "token_usage_or_unavailable_reason": "unavailable_opencode_cli",
                     "duration": "12s", "exit_code": 0, "rate_limit": False,
                     "binary_ok": True, "final_status": "PASS"},
                    {"node": "9bao", "job_id": "e2e-002", "role": "reviewer",
                     "planned_model": "opencode/deepseek-v4-flash-free",
                     "actual_model": "deepseek-v4-flash-free", "provider": "opencode",
                     "opencode_provider_alias": "opencode", "fallback_used": False,
                     "call_count": 1, "token_usage_or_unavailable_reason": "unavailable_opencode_cli",
                     "duration": "15s", "exit_code": 0, "rate_limit": False,
                     "binary_ok": True, "final_status": "PASS"},
                    {"node": "5bao", "job_id": "e2e-004", "role": "implementer",
                     "planned_model": "opencode/deepseek-v4-flash-free",
                     "actual_model": "deepseek-v4-flash-free", "provider": "opencode",
                     "opencode_provider_alias": "opencode", "fallback_used": False,
                     "call_count": 1, "token_usage_or_unavailable_reason": "unavailable_opencode_cli",
                     "duration": "19s", "exit_code": 0, "rate_limit": False,
                     "binary_ok": True, "final_status": "PASS"},
                    {"node": "windows", "job_id": "e2e-003", "role": "smoke",
                     "planned_model": "N/A", "actual_model": "N/A", "provider": "N/A",
                     "opencode_provider_alias": "N/A", "fallback_used": False,
                     "call_count": 0, "token_usage_or_unavailable_reason": "no_model_call_fixture",
                     "duration": "2s", "exit_code": 0, "rate_limit": False,
                     "binary_ok": True, "final_status": "PASS"},
                    {"node": "windows", "job_id": "e2e-005", "role": "smoke",
                     "planned_model": "N/A", "actual_model": "N/A", "provider": "N/A",
                     "opencode_provider_alias": "N/A", "fallback_used": False,
                     "call_count": 0, "token_usage_or_unavailable_reason": "no_model_call_cooldown",
                     "duration": "1s", "exit_code": 0, "rate_limit": False,
                     "binary_ok": True, "final_status": "PASS"},
                ],
                "NODE_MODEL_SUMMARY": [
                    {"node": "5bao", "opencode_version": "1.17.8",
                     "models_used_this_run": ["deepseek-v4-flash-free"],
                     "total_model_calls": 2, "successful_model_calls": 2,
                     "failed_model_calls": 0, "fallback_count": 0,
                     "rate_limit_count": 0, "cooldown_state": "NORMAL"},
                    {"node": "9bao", "opencode_version": "1.17.8",
                     "models_used_this_run": ["deepseek-v4-flash-free"],
                     "total_model_calls": 1, "successful_model_calls": 1,
                     "failed_model_calls": 0, "fallback_count": 0,
                     "rate_limit_count": 0, "cooldown_state": "NORMAL"},
                ],
                "RATE_LIMIT_EVENT_LEDGER": [],
                "FALLBACK_DECISION_LEDGER": [],
                "COOLDOWN_STATE_SUMMARY": [
                    {"node": "5bao", "model": "opencode/deepseek-v4-flash-free",
                     "consecutive_rate_limits": 0, "current_cooldown_seconds": 0,
                     "cooldown_action": "NORMAL"},
                    {"node": "9bao", "model": "opencode/deepseek-v4-flash-free",
                     "consecutive_rate_limits": 0, "current_cooldown_seconds": 0,
                     "cooldown_action": "NORMAL"},
                ],
            },
        },
        {
            "id": "int-02-non-terminal-status",
            "description": "Non-terminal status (IN_PROGRESS) -> gate not applicable, allowed",
            "expected_status_allowed": True,
            "expected_merge_ready": False,
            "report": {"status": "IN_PROGRESS"},
        },
        # === NEGATIVE CASES ===
        {
            "id": "int-03-missing-model-ledger",
            "description": "PASS but no MODEL_LEDGER -> blocked",
            "expected_status_allowed": False,
            "expected_merge_ready": False,
            "report": {"status": "PASS", "NODE_MODEL_SUMMARY": [{"node": "5bao"}],
                       "COOLDOWN_STATE_SUMMARY": [{"node": "5bao"}]},
        },
        {
            "id": "int-04-missing-node-summary",
            "description": "PASS but no NODE_MODEL_SUMMARY -> blocked",
            "expected_status_allowed": False,
            "expected_merge_ready": False,
            "report": {"status": "PASS",
                       "MODEL_LEDGER": [
                           {"node": "5bao", "job_id": "e2e-001", "role": "implementer",
                            "planned_model": "opencode/deepseek-v4-flash-free",
                            "actual_model": "deepseek-v4-flash-free", "provider": "opencode",
                            "opencode_provider_alias": "opencode", "fallback_used": False,
                            "call_count": 1, "token_usage_or_unavailable_reason": "unavailable",
                            "duration": "12s", "exit_code": 0, "rate_limit": False,
                            "final_status": "PASS"}],
                       "COOLDOWN_STATE_SUMMARY": [{"node": "5bao"}]},
        },
        {
            "id": "int-05-missing-cooldown-summary",
            "description": "PASS but no COOLDOWN_STATE_SUMMARY -> blocked",
            "expected_status_allowed": False,
            "expected_merge_ready": False,
            "report": {"status": "PASS",
                       "MODEL_LEDGER": [
                           {"node": "5bao", "job_id": "e2e-001", "role": "implementer",
                            "planned_model": "opencode/deepseek-v4-flash-free",
                            "actual_model": "deepseek-v4-flash-free", "provider": "opencode",
                            "opencode_provider_alias": "opencode", "fallback_used": False,
                            "call_count": 1, "token_usage_or_unavailable_reason": "unavailable",
                            "duration": "12s", "exit_code": 0, "rate_limit": False,
                            "final_status": "PASS"}],
                       "NODE_MODEL_SUMMARY": [{"node": "5bao"}]},
        },
        {
            "id": "int-06-rate-limit-without-ledger",
            "description": "rate_limit=true but no RATE_LIMIT_EVENT_LEDGER -> blocked",
            "expected_status_allowed": False,
            "expected_merge_ready": False,
            "report": {"status": "PASS",
                       "MODEL_LEDGER": [
                           {"node": "9bao", "job_id": "e2e-002", "role": "smoke",
                            "planned_model": "opencode/deepseek-v4-flash-free",
                            "actual_model": None, "provider": "opencode",
                            "opencode_provider_alias": "opencode", "fallback_used": False,
                            "call_count": 1, "token_usage_or_unavailable_reason": "rate_limited",
                            "duration": "90s", "exit_code": 124, "rate_limit": True,
                            "final_status": "RATE_LIMITED"}],
                       "NODE_MODEL_SUMMARY": [{"node": "9bao", "opencode_version": "1.17.8",
                                                "models_used_this_run": [], "total_model_calls": 1,
                                                "successful_model_calls": 0, "failed_model_calls": 1,
                                                "fallback_count": 0, "rate_limit_count": 1,
                                                "cooldown_state": "RATE_LIMITED_1"}],
                       "COOLDOWN_STATE_SUMMARY": [{"node": "9bao", "model": "opencode/deepseek-v4-flash-free",
                                                    "consecutive_rate_limits": 1, "current_cooldown_seconds": 30,
                                                    "cooldown_action": "cooldown_30s"}]},
        },
        {
            "id": "int-07-fallback-without-fields",
            "description": "fallback_used=true but no from/to/reason -> blocked",
            "expected_status_allowed": False,
            "expected_merge_ready": False,
            "report": {"status": "PASS",
                       "MODEL_LEDGER": [
                           {"node": "5bao", "job_id": "e2e-004", "role": "implementer",
                            "planned_model": "opencode/deepseek-v4-flash-free",
                            "actual_model": "mimo-v2.5-free", "provider": "opencode",
                            "opencode_provider_alias": "opencode", "fallback_used": True,
                            "fallback_from": None, "fallback_to": None, "fallback_reason": None,
                            "call_count": 1, "token_usage_or_unavailable_reason": "unavailable",
                            "duration": "8s", "exit_code": 0, "rate_limit": False,
                            "final_status": "PASS"}],
                       "NODE_MODEL_SUMMARY": [{"node": "5bao", "opencode_version": "1.17.8",
                                                "models_used_this_run": ["mimo-v2.5-free"],
                                                "total_model_calls": 1, "successful_model_calls": 1,
                                                "failed_model_calls": 0, "fallback_count": 1,
                                                "rate_limit_count": 0, "cooldown_state": "NORMAL"}],
                       "COOLDOWN_STATE_SUMMARY": [{"node": "5bao", "model": "opencode/deepseek-v4-flash-free",
                                                    "consecutive_rate_limits": 0, "current_cooldown_seconds": 0,
                                                    "cooldown_action": "NORMAL"}]},
        },
        {
            "id": "int-08-token-usage-unknown",
            "description": "token_usage='unknown' -> blocked",
            "expected_status_allowed": False,
            "expected_merge_ready": False,
            "report": {"status": "PASS",
                       "MODEL_LEDGER": [
                           {"node": "5bao", "job_id": "e2e-001", "role": "implementer",
                            "planned_model": "opencode/deepseek-v4-flash-free",
                            "actual_model": "deepseek-v4-flash-free", "provider": "opencode",
                            "opencode_provider_alias": "opencode", "fallback_used": False,
                            "call_count": 1, "token_usage_or_unavailable_reason": "unknown",
                            "duration": "12s", "exit_code": 0, "rate_limit": False,
                            "final_status": "PASS"}],
                       "NODE_MODEL_SUMMARY": [{"node": "5bao", "opencode_version": "1.17.8",
                                                "models_used_this_run": ["deepseek-v4-flash-free"],
                                                "total_model_calls": 1, "successful_model_calls": 1,
                                                "failed_model_calls": 0, "fallback_count": 0,
                                                "rate_limit_count": 0, "cooldown_state": "NORMAL"}],
                       "COOLDOWN_STATE_SUMMARY": [{"node": "5bao", "model": "opencode/deepseek-v4-flash-free",
                                                    "consecutive_rate_limits": 0, "current_cooldown_seconds": 0,
                                                    "cooldown_action": "NORMAL"}]},
        },
        {
            "id": "int-09-rate-limit-as-binary-failure",
            "description": "Rate limit (exit 124) misclassified as BIN-FAIL -> blocked",
            "expected_status_allowed": False,
            "expected_merge_ready": False,
            "report": {"status": "PASS",
                       "MODEL_LEDGER": [
                           {"node": "9bao", "job_id": "e2e-002", "role": "smoke",
                            "planned_model": "opencode/deepseek-v4-flash-free",
                            "actual_model": None, "provider": "opencode",
                            "opencode_provider_alias": "opencode", "fallback_used": False,
                            "call_count": 1, "token_usage_or_unavailable_reason": "rate_limited",
                            "duration": "90s", "exit_code": 124, "rate_limit": True,
                            "final_status": "RATE_LIMITED"}],
                       "NODE_MODEL_SUMMARY": [{"node": "9bao", "opencode_version": "1.17.8",
                                                "models_used_this_run": [], "total_model_calls": 1,
                                                "successful_model_calls": 0, "failed_model_calls": 1,
                                                "fallback_count": 0, "rate_limit_count": 1,
                                                "cooldown_state": "RATE_LIMITED_1"}],
                       "RATE_LIMIT_EVENT_LEDGER": [
                           {"timestamp": "2026-06-19T14:00:00Z", "node": "9bao",
                            "affected_model": "opencode/deepseek-v4-flash-free",
                            "provider": "opencode", "error_type": "BIN-FAIL",
                            "exit_code": 124, "binary_ok": True,
                            "rollback_required": True,
                            "cooldown_action": "cooldown_30s",
                            "fallback_action": "none"}
                       ],
                       "COOLDOWN_STATE_SUMMARY": [{"node": "9bao", "model": "opencode/deepseek-v4-flash-free",
                                                    "consecutive_rate_limits": 1, "current_cooldown_seconds": 30,
                                                    "cooldown_action": "cooldown_30s"}]},
        },
        {
            "id": "int-10-node-summary-missing-fields",
            "description": "NODE_MODEL_SUMMARY only has node -> blocked",
            "expected_status_allowed": False,
            "expected_merge_ready": False,
            "report": {"status": "PASS",
                       "MODEL_LEDGER": [
                           {"node": "5bao", "job_id": "e2e-001", "role": "implementer",
                            "planned_model": "opencode/deepseek-v4-flash-free",
                            "actual_model": "deepseek-v4-flash-free", "provider": "opencode",
                            "opencode_provider_alias": "opencode", "fallback_used": False,
                            "call_count": 1, "token_usage_or_unavailable_reason": "unavailable",
                            "duration": "12s", "exit_code": 0, "rate_limit": False,
                            "final_status": "PASS"}],
                       "NODE_MODEL_SUMMARY": [{"node": "5bao"}],
                       "COOLDOWN_STATE_SUMMARY": [{"node": "5bao", "model": "opencode/deepseek-v4-flash-free",
                                                    "consecutive_rate_limits": 0, "current_cooldown_seconds": 0,
                                                    "cooldown_action": "NORMAL"}]},
        },
        {
            "id": "int-11-cooldown-missing-fields",
            "description": "COOLDOWN_STATE_SUMMARY only has node -> blocked",
            "expected_status_allowed": False,
            "expected_merge_ready": False,
            "report": {"status": "PASS",
                       "MODEL_LEDGER": [
                           {"node": "5bao", "job_id": "e2e-001", "role": "implementer",
                            "planned_model": "opencode/deepseek-v4-flash-free",
                            "actual_model": "deepseek-v4-flash-free", "provider": "opencode",
                            "opencode_provider_alias": "opencode", "fallback_used": False,
                            "call_count": 1, "token_usage_or_unavailable_reason": "unavailable",
                            "duration": "12s", "exit_code": 0, "rate_limit": False,
                            "final_status": "PASS"}],
                       "NODE_MODEL_SUMMARY": [{"node": "5bao", "opencode_version": "1.17.8",
                                                "models_used_this_run": ["deepseek-v4-flash-free"],
                                                "total_model_calls": 1, "successful_model_calls": 1,
                                                "failed_model_calls": 0, "fallback_count": 0,
                                                "rate_limit_count": 0, "cooldown_state": "NORMAL"}],
                       "COOLDOWN_STATE_SUMMARY": [{"node": "5bao"}]},
        },
    ]


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Report Status Gate")
    parser.add_argument("--report", metavar="PATH", help="Validate a report JSON")
    parser.add_argument("--merge-readiness", metavar="PATH", help="Check merge readiness")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"=== SELF-CHECK (v{__version__}, gate v{gate_version}) ===")
            print(f"  Total: {result['total']}")
            print(f"  Passed: {result['passed_count']}")
            print(f"  Failed: {result['failed_count']}")
            for s in result["scenarios"]:
                print(f"  {s['status']}  {s['id']}: {s['description']}")
                if s["errors"]:
                    for e in s["errors"]:
                        print(f"        {e}")
            print(f"\n  Self-check: {'PASSED' if result['passed'] else 'FAILED'}")
        sys.exit(0 if result["passed"] else 1)

    if args.report:
        with open(args.report, "r", encoding="utf-8") as f:
            report = json.load(f)
        result = check_report_status(report)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if result["status_allowed"]:
                print(f"STATUS ALLOWED (terminal={result.get('terminal_status_found')})")
            else:
                print(f"STATUS BLOCKED (terminal={result.get('terminal_status_found')})")
                for e in result["gate_errors"]:
                    print(f"  - {e}")
        sys.exit(0 if result["status_allowed"] else 1)

    if args.merge_readiness:
        with open(args.merge_readiness, "r", encoding="utf-8") as f:
            report = json.load(f)
        result = check_merge_readiness(report)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"MERGE_READY={result['merge_ready']}")
            print(f"MODEL_LEDGER_GATE_RESULT={result['model_ledger_gate_result']}")
            print(f"GATE_EXIT_CODE={result['gate_exit_code']}")
            if result["failure_reasons"]:
                print("FAILURE_REASONS:")
                for r in result["failure_reasons"]:
                    print(f"  - {r}")
        sys.exit(0 if result["merge_ready"] else 1)

    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
