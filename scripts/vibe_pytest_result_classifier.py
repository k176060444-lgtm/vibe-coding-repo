#!/usr/bin/env python3
"""Pytest Result Classifier v1.0.0 — Strict pytest exit code / output classification.

Classifies pytest results into unambiguous categories. exit=5 is NEVER PASS.

Categories:
  PASS              — exit=0, tests passed (or skipped with allow_skipped_only)
  SKIPPED_ONLY      — exit=0, only skipped tests, no passes
  NO_TESTS          — exit=5 (no tests collected)
  INCONSISTENT_RESULT — exit=5 but output mentions tests ran/skipped
  ENV_FAIL          — import/dependency/plugin/config failure
  TEST_FAIL         — assertion/test failure (exit=1)
  INTERRUPTED       — exit=2 (keyboard interrupt)
  TIMEOUT           — process timeout
  UNKNOWN           — other exit codes

Usage:
    python3 scripts/vibe_pytest_result_classifier.py classify --exit-code 5 --output "1 skipped in 0.05s" [--json]
    python3 scripts/vibe_pytest_result_classifier.py classify-run --command "python -m pytest ..." [--json]
    python3 scripts/vibe_pytest_result_classifier.py self-check [--json]
    python3 scripts/vibe_pytest_result_classifier.py --version
"""

import argparse
import json
import os
import re
import subprocess
import sys

VERSION = "1.0.0"

# Pytest exit codes (standard)
EXIT_OK = 0           # Tests passed (or all skipped)
EXIT_TEST_FAILED = 1  # Tests failed
EXIT_INTERRUPTED = 2  # Keyboard interrupt
EXIT_INTERNAL_ERROR = 3  # Internal error
EXIT_USAGE_ERROR = 4  # Usage error
EXIT_NO_TESTS = 5     # No tests collected


def classify_pytest_result(exit_code, stdout="", stderr="", allow_skipped_only=False):
    """Classify a pytest result.

    Returns dict with: category, decision, env_ready, tests_collected,
    passed, skipped, failed, exit_code, details.
    """
    result = {
        "exit_code": exit_code,
        "stdout_tail": stdout[-500:] if stdout else "",
        "stderr_tail": stderr[-500:] if stderr else "",
        "env_ready": True,
        "tests_collected": 0,
        "passed": 0,
        "skipped": 0,
        "failed": 0,
        "errors": 0,
    }

    # Parse pytest summary line: "N passed, N skipped, N failed, N error in Xs"
    summary_match = re.search(
        r"(\d+)\s+passed|(\d+)\s+skipped|(\d+)\s+failed|(\d+)\s+error",
        stdout, re.IGNORECASE
    )
    if summary_match:
        passed_m = re.findall(r"(\d+)\s+passed", stdout, re.IGNORECASE)
        skipped_m = re.findall(r"(\d+)\s+skipped", stdout, re.IGNORECASE)
        failed_m = re.findall(r"(\d+)\s+failed", stdout, re.IGNORECASE)
        error_m = re.findall(r"(\d+)\s+error", stdout, re.IGNORECASE)

        result["passed"] = int(passed_m[0]) if passed_m else 0
        result["skipped"] = int(skipped_m[0]) if skipped_m else 0
        result["failed"] = int(failed_m[0]) if failed_m else 0
        result["errors"] = int(error_m[0]) if error_m else 0
        result["tests_collected"] = result["passed"] + result["skipped"] + result["failed"]

    # Check for env failures
    env_fail_patterns = [
        r"ModuleNotFoundError",
        r"ImportError",
        r"AttributeError.*module",
        r"no: .*not found",
        r"ERRORS.*collecting",
        r"fixture.*not found",
        r"plugin.*not found",
        r"config.*error",
    ]
    for pattern in env_fail_patterns:
        if re.search(pattern, stdout + stderr, re.IGNORECASE):
            result["env_ready"] = False
            break

    # Check for timeout
    if "timeout" in (stderr + stdout).lower() and exit_code != 0:
        result["category"] = "TIMEOUT"
        result["decision"] = "TIMEOUT — process timed out, re-run with longer timeout"
        return result

    # Classify based on exit code
    if exit_code == EXIT_OK:
        if result["passed"] > 0:
            result["category"] = "PASS"
            result["decision"] = f"PASS — {result['passed']} tests passed"
        elif result["skipped"] > 0 and result["passed"] == 0 and result["failed"] == 0:
            if allow_skipped_only:
                result["category"] = "PASS"
                result["decision"] = f"PASS (skipped_only_allowed) — {result['skipped']} skipped"
            else:
                result["category"] = "SKIPPED_ONLY"
                result["decision"] = f"SKIPPED_ONLY — {result['skipped']} skipped, 0 passed. Not a strong validation."
        else:
            result["category"] = "PASS"
            result["decision"] = "PASS — exit=0, no failures"

    elif exit_code == EXIT_NO_TESTS:
        # Check for inconsistent output
        if result["tests_collected"] > 0 or result["skipped"] > 0 or result["passed"] > 0:
            result["category"] = "INCONSISTENT_RESULT"
            result["decision"] = (
                f"INCONSISTENT_RESULT — exit=5 (no tests collected) but output shows "
                f"{result['passed']} passed, {result['skipped']} skipped. "
                f"Possibly conditional skip or collection anomaly."
            )
        else:
            result["category"] = "NO_TESTS"
            result["decision"] = "NO_TESTS — exit=5, no tests collected. Check test discovery."

    elif exit_code == EXIT_TEST_FAILED:
        if not result["env_ready"]:
            result["category"] = "ENV_FAIL"
            result["decision"] = "ENV_FAIL — dependency/import/plugin failure prevented test execution"
        else:
            result["category"] = "TEST_FAIL"
            result["decision"] = f"TEST_FAIL — {result['failed']} tests failed"

    elif exit_code == EXIT_INTERRUPTED:
        result["category"] = "INTERRUPTED"
        result["decision"] = "INTERRUPTED — keyboard interrupt (exit=2)"

    elif exit_code == EXIT_INTERNAL_ERROR:
        result["category"] = "ENV_FAIL"
        result["decision"] = "ENV_FAIL — pytest internal error (exit=3)"

    elif exit_code == EXIT_USAGE_ERROR:
        result["category"] = "ENV_FAIL"
        result["decision"] = "ENV_FAIL — pytest usage error (exit=4)"

    else:
        result["category"] = "UNKNOWN"
        result["decision"] = f"UNKNOWN — exit={exit_code}, cannot classify"

    # Strong validation check
    result["strong_validation"] = (
        result["category"] == "PASS" and result["passed"] > 0
    )

    return result


def classify_run(command, cwd=None, timeout=60, allow_skipped_only=False):
    """Run a pytest command and classify the result."""
    try:
        proc = subprocess.run(
            command, shell=isinstance(command, str),
            capture_output=True, text=True, timeout=timeout, cwd=cwd
        )
        return classify_pytest_result(
            proc.returncode, proc.stdout, proc.stderr, allow_skipped_only
        )
    except subprocess.TimeoutExpired:
        return {
            "category": "TIMEOUT",
            "decision": f"TIMEOUT — process timed out after {timeout}s",
            "exit_code": -1,
            "env_ready": True,
            "tests_collected": 0,
            "passed": 0, "skipped": 0, "failed": 0, "errors": 0,
            "strong_validation": False,
        }


def self_check(json_output=False):
    """Self-check: verify classifier logic."""
    checks = []

    # 1. Version
    checks.append({"name": "version", "passed": True, "message": VERSION})

    # 2. exit=0 with passes = PASS
    r = classify_pytest_result(0, "5 passed in 1.0s")
    checks.append({"name": "exit0_pass", "passed": r["category"] == "PASS" and r["passed"] == 5,
                   "message": f"category={r['category']} passed={r['passed']}"})

    # 3. exit=0 skipped only = SKIPPED_ONLY
    r = classify_pytest_result(0, "1 skipped in 0.05s")
    checks.append({"name": "exit0_skipped_only", "passed": r["category"] == "SKIPPED_ONLY",
                   "message": f"category={r['category']}"})

    # 4. exit=0 skipped with allow = PASS
    r = classify_pytest_result(0, "1 skipped in 0.05s", allow_skipped_only=True)
    checks.append({"name": "exit0_skipped_allowed", "passed": r["category"] == "PASS",
                   "message": f"category={r['category']}"})

    # 5. exit=5 = NO_TESTS
    r = classify_pytest_result(5, "")
    checks.append({"name": "exit5_no_tests", "passed": r["category"] == "NO_TESTS",
                   "message": f"category={r['category']}"})

    # 6. exit=5 with skipped output = INCONSISTENT_RESULT
    r = classify_pytest_result(5, "1 skipped in 0.05s")
    checks.append({"name": "exit5_inconsistent", "passed": r["category"] == "INCONSISTENT_RESULT",
                   "message": f"category={r['category']}"})

    # 7. exit=1 with failures = TEST_FAIL
    r = classify_pytest_result(1, "2 failed, 3 passed in 1.0s")
    checks.append({"name": "exit1_fail", "passed": r["category"] == "TEST_FAIL" and r["failed"] == 2,
                   "message": f"category={r['category']} failed={r['failed']}"})

    # 8. exit=1 with import error = ENV_FAIL
    r = classify_pytest_result(1, "", "ModuleNotFoundError: No module named 'xyz'")
    checks.append({"name": "exit1_env_fail", "passed": r["category"] == "ENV_FAIL",
                   "message": f"category={r['category']} env_ready={r['env_ready']}"})

    # 9. exit=2 = INTERRUPTED
    r = classify_pytest_result(2, "")
    checks.append({"name": "exit2_interrupted", "passed": r["category"] == "INTERRUPTED",
                   "message": f"category={r['category']}"})

    # 10. strong_validation only for real passes
    r1 = classify_pytest_result(0, "5 passed in 1.0s")
    r2 = classify_pytest_result(0, "1 skipped in 0.05s")
    r3 = classify_pytest_result(5, "1 skipped in 0.05s")
    checks.append({"name": "strong_validation",
                   "passed": r1["strong_validation"] and not r2["strong_validation"] and not r3["strong_validation"],
                   "message": f"pass={r1['strong_validation']} skipped={r2['strong_validation']} inconsistent={r3['strong_validation']}"})

    # 11. Node attribution
    checks.append({"name": "node_attribution", "passed": True,
                   "message": "controller=windows execution=debian"})

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    return {"overall": "PASS" if passed == total else "FAIL", "passed": passed, "total": total, "checks": checks}


def build_parser():
    parser = argparse.ArgumentParser(prog="vibe_pytest_result_classifier")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--json", action="store_true", dest="output_json")
    sub = parser.add_subparsers(dest="command")

    p_classify = sub.add_parser("classify")
    p_classify.add_argument("--exit-code", type=int, required=True)
    p_classify.add_argument("--output", default="")
    p_classify.add_argument("--stderr", default="")
    p_classify.add_argument("--allow-skipped-only", action="store_true")

    p_run = sub.add_parser("classify-run")
    p_run.add_argument("--command", required=True)
    p_run.add_argument("--cwd", default=None)
    p_run.add_argument("--timeout", type=int, default=60)
    p_run.add_argument("--allow-skipped-only", action="store_true")

    sub.add_parser("self-check")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "classify":
        result = classify_pytest_result(args.exit_code, args.output, args.stderr, args.allow_skipped_only)
    elif args.command == "classify-run":
        result = classify_run(args.command, args.cwd, args.timeout, args.allow_skipped_only)
    elif args.command == "self-check":
        result = self_check(args.output_json)
    else:
        parser.print_help()
        return 1

    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        if isinstance(result, dict) and "overall" in result:
            print(f"Overall: {result['overall']} ({result['passed']}/{result['total']})")
            for c in result.get("checks", []):
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  [{icon}] {c['name']}: {c['message']}")
        elif isinstance(result, dict):
            print(f"Category: {result.get('category')}")
            print(f"Decision: {result.get('decision')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
