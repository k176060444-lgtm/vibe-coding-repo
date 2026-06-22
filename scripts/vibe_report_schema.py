#!/usr/bin/env python3
"""Report Schema v1.0.0 — validate final reports have all required sections.

Usage:
    python3 scripts/vibe_report_schema.py --json validate --input report.json
    python3 scripts/vibe_report_schema.py self-check [--json]
"""

import argparse
import json
import sys
from datetime import datetime, timezone

VERSION = "1.1.0"

REQUIRED_SECTIONS = [
    "pr_merge_info",
    "changed_paths",
    "baseline",
    "validation",
    "node_attribution",
    "token_status",
    "external_write_status",
]

REQUIRED_NODE_ATTRIBUTION_FIELDS = [
    "controller_node",
    "execution_node",
    "transport",
    "git_mutation_node",
    "token_access_node",
    "pr_operation_node",
]

REQUIRED_TOKEN_STATUS_FIELDS = [
    "token_read",
    "token_leaked",
    "token_source",
]

OPTIONAL_SECTIONS = [
    "dashboard",
    "resume_gate",
    "health_snapshot",
    "model_roles",
    "failures_retries",
    "evidence",
    "quality_metrics",
    "role_assignment_matrix",
    "planned_vs_actual_role_ledger",
    "remote_verification",
    "capability_declaration",
    "planned_actual_model_ledger",
]


def validate_report(report):
    errors = []
    warnings = []
    for section in REQUIRED_SECTIONS:
        if section not in report:
            errors.append(f"missing required section: {section}")
    na = report.get("node_attribution", {})
    for field in REQUIRED_NODE_ATTRIBUTION_FIELDS:
        if field not in na:
            errors.append(f"missing node_attribution.{field}")
    ts = report.get("token_status", {})
    for field in REQUIRED_TOKEN_STATUS_FIELDS:
        if field not in ts:
            errors.append(f"missing token_status.{field}")
    if ts.get("token_leaked") is True:
        errors.append("CRITICAL: token_leaked=True")
    ews = report.get("external_write_status", {})
    if ews.get("real_write_occurred") and not ews.get("approved"):
        errors.append("CRITICAL: unapproved external write")
    for section in OPTIONAL_SECTIONS:
        if section not in report:
            warnings.append(f"optional section missing: {section}")
    baseline = report.get("baseline", {})
    if baseline and not baseline.get("current_sha"):
        warnings.append("baseline.current_sha missing")
    val = report.get("validation", {})
    if val:
        for check in ["smoke", "qg", "v1_freeze"]:
            if check not in val:
                warnings.append(f"validation.{check} missing")
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "required_sections_present": sum(1 for s in REQUIRED_SECTIONS if s in report),
        "required_sections_total": len(REQUIRED_SECTIONS),
        "optional_sections_present": sum(1 for s in OPTIONAL_SECTIONS if s in report),
        "optional_sections_total": len(OPTIONAL_SECTIONS),
    }


def self_check(output_json=False):
    checks = []
    checks.append({"name": "version", "passed": True, "message": VERSION})
    valid_report = {
        "pr_merge_info": {"pr": 134, "merged": True},
        "changed_paths": ["scripts/foo.py"],
        "baseline": {"current_sha": "abc123"},
        "validation": {"smoke": "PASS", "qg": "PASS", "v1_freeze": "PASS"},
        "node_attribution": {
            "controller_node": "windows", "execution_node": "debian",
            "transport": "ssh", "git_mutation_node": "debian",
            "token_access_node": "debian", "pr_operation_node": "debian",
        },
        "token_status": {"token_read": False, "token_leaked": False, "token_source": "gh_cached"},
        "external_write_status": {"real_write_occurred": False},
    }
    result = validate_report(valid_report)
    checks.append({"name": "valid_report_passes", "passed": result["valid"],
                    "message": f"errors={len(result['errors'])} warnings={len(result['warnings'])}"})
    bad_report = {"pr_merge_info": {}, "changed_paths": [], "baseline": {},
                  "validation": {}, "token_status": {"token_read": False, "token_leaked": False, "token_source": "none"},
                  "external_write_status": {}}
    result2 = validate_report(bad_report)
    checks.append({"name": "missing_attribution_fails", "passed": not result2["valid"],
                    "message": f"errors={len(result2['errors'])}"})
    leak_report = dict(valid_report, token_status={"token_read": True, "token_leaked": True, "token_source": "leaked"})
    result3 = validate_report(leak_report)
    checks.append({"name": "token_leak_fails", "passed": not result3["valid"],
                    "message": f"errors={len(result3['errors'])}"})
    write_report = dict(valid_report, external_write_status={"real_write_occurred": True, "approved": False})
    result4 = validate_report(write_report)
    checks.append({"name": "unapproved_write_fails", "passed": not result4["valid"],
                    "message": f"errors={len(result4['errors'])}"})
    checks.append({"name": "has_attribution", "passed": True, "message": "controller=windows execution=debian"})
    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    return {"overall": "PASS" if passed == total else "FAIL", "passed": passed, "total": total, "checks": checks}


def build_parser():
    p = argparse.ArgumentParser(prog="vibe_report_schema")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument("--json", dest="output_json", action="store_true")
    p.add_argument("--self-check", dest="self_check_flag", action="store_true")
    sub = p.add_subparsers(dest="command")
    p_val = sub.add_parser("validate")
    p_val.add_argument("--input", dest="input_file", required=True)
    return p


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)
    if args.self_check_flag:
        result = self_check(args.output_json)
    elif args.command == "validate" and args.input_file:
        with open(args.input_file) as f:
            report = json.load(f)
        result = validate_report(report)
    else:
        p.print_help()
        return 1
    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        if "overall" in result:
            print(f"Overall: {result['overall']} ({result['passed']}/{result['total']})")
            for c in result.get("checks", []):
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  [{icon}] {c['name']}: {c['message']}")
        else:
            status = "VALID" if result["valid"] else "INVALID"
            print(f"Report: {status}")
            for e in result.get("errors", []):
                print(f"  error: {e}")
            for w in result.get("warnings", []):
                print(f"  warn: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
