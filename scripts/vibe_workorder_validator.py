#!/usr/bin/env python3
"""Work Order Validator v1 - Validate intake drafts for execution readiness.

Usage:
    python scripts/vibe_workorder_validator.py <json-file-or-draft>
    python scripts/vibe_workorder_validator.py --stdin
    python scripts/vibe_workorder_validator.py --json <json-file-or-draft>

Reads a Work Order draft (JSON) and validates field completeness,
allowed_paths, forbidden_actions, risk_level, acceptance_tests,
stop_conditions. Outputs PASS/WARN/FAIL with details.

Constraints:
    - Read-only, no IO on import, standard library only.
    - Validates only, never executes.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


# Required fields for a valid Work Order
REQUIRED_FIELDS = [
    "work_order_id", "title", "type", "goal", "risk_level",
    "requires_human_approval", "allowed_paths", "forbidden_actions",
    "acceptance_tests", "stop_conditions", "expected_report_fields",
]

# Valid values for enum fields
VALID_TYPES = {"code", "doc", "test", "fix", "maint"}
VALID_RISKS = {"low", "medium", "high", "critical"}

# Dangerous patterns that should be in forbidden_actions
DANGEROUS_PATTERNS = [
    r"(?i)secret", r"(?i)credential", r"(?i)token", r"(?i)password",
    r"(?i)deploy", r"(?i)production", r"(?i)force.push",
]

# Forbidden path patterns (should never be in allowed_paths)
FORBIDDEN_PATH_PATTERNS = [
    r"\.github/", r"secrets/", r"\*token\*", r"\*secret\*",
    r"\*credential\*", r"\*password\*", r"\.env",
]


def validate_draft(draft):
    """Validate a Work Order draft.

    Args:
        draft: dict with Work Order fields

    Returns:
        dict with validation result: overall (PASS/WARN/FAIL), checks, warnings, errors
    """
    checks = []
    warnings = []
    errors = []

    # 1. Type check
    if not isinstance(draft, dict):
        return {
            "overall": "FAIL",
            "checks": [],
            "warnings": [],
            "errors": ["Draft is not a JSON object"],
        }

    # 2. Required fields
    missing = [f for f in REQUIRED_FIELDS if f not in draft]
    if missing:
        errors.append("Missing required fields: %s" % ", ".join(missing))
    else:
        checks.append("All required fields present (%d)" % len(REQUIRED_FIELDS))

    # 3. Type validation
    wo_type = draft.get("type", "")
    if wo_type in VALID_TYPES:
        checks.append("Valid type: %s" % wo_type)
    elif wo_type:
        warnings.append("Unknown type: %s (expected: %s)" % (wo_type, ", ".join(VALID_TYPES)))

    # 4. Risk level validation
    risk = draft.get("risk_level", "")
    if risk in VALID_RISKS:
        checks.append("Valid risk_level: %s" % risk)
    elif risk:
        warnings.append("Unknown risk_level: %s" % risk)

    # 5. Human approval consistency
    requires_human = draft.get("requires_human_approval")
    if risk in ("high", "critical") and requires_human is not True:
        errors.append("risk=%s requires requires_human_approval=true" % risk)
    elif risk in ("low", "medium") and requires_human is True:
        warnings.append("risk=%s but requires_human_approval=true (unusual)" % risk)
    elif requires_human is not None:
        checks.append("Human approval: %s (matches risk)" % requires_human)

    # 6. Allowed paths validation
    allowed = draft.get("allowed_paths", [])
    if not allowed:
        errors.append("allowed_paths is empty — scope undefined")
    else:
        path_issues = []
        for p in allowed:
            for fp in FORBIDDEN_PATH_PATTERNS:
                if re.search(fp, p):
                    path_issues.append("%s matches forbidden pattern %s" % (p, fp))
        if path_issues:
            errors.extend(["Forbidden path: %s" % i for i in path_issues])
        else:
            checks.append("allowed_paths valid (%d paths)" % len(allowed))

    # 7. Forbidden actions validation
    forbidden = draft.get("forbidden_actions", [])
    if not forbidden:
        warnings.append("forbidden_actions is empty — consider adding safety constraints")
    else:
        checks.append("forbidden_actions defined (%d rules)" % len(forbidden))

    # 8. Goal validation
    goal = draft.get("goal", "")
    if not goal or len(goal.strip()) < 10:
        errors.append("Goal is empty or too short (< 10 chars)")
    else:
        checks.append("Goal present (%d chars)" % len(goal))

    # 9. Acceptance tests validation
    tests = draft.get("acceptance_tests", [])
    if not tests:
        errors.append("acceptance_tests is empty — no verification criteria")
    elif len(tests) < 2:
        warnings.append("acceptance_tests has only %d entry — consider adding more" % len(tests))
    else:
        checks.append("acceptance_tests defined (%d criteria)" % len(tests))

    # 10. Stop conditions validation
    stops = draft.get("stop_conditions", [])
    if not stops:
        warnings.append("stop_conditions is empty — consider adding safety stops")
    else:
        checks.append("stop_conditions defined (%d conditions)" % len(stops))

    # 11. Draft-only check
    if draft.get("draft_only") is not True:
        warnings.append("draft_only is not true — draft may be mistaken for executable")

    # 12. Execution approval check
    if draft.get("execution_requires_explicit_approval") is not True:
        warnings.append("execution_requires_explicit_approval is not true")

    # 13. Work order ID format
    wo_id = draft.get("work_order_id", "")
    if wo_id and not re.match(r'^wo-(code|doc|maint|test|fix)-[\w-]+-\d+$', wo_id):
        warnings.append("work_order_id format non-standard: %s" % wo_id)
    elif wo_id:
        checks.append("work_order_id format valid: %s" % wo_id)

    # Overall verdict
    if errors:
        overall = "FAIL"
    elif warnings:
        overall = "WARN"
    else:
        overall = "PASS"

    return {
        "overall": overall,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "field_count": len(draft),
        "risk_level": risk,
        "requires_human_approval": requires_human,
    }


def load_draft(source):
    """Load draft from file path or stdin."""
    if source == "-":
        return json.load(sys.stdin)
    with open(source, "r", encoding="utf-8") as f:
        return json.load(f)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_workorder_validator",
        description="Work Order Validator v1 - validate intake drafts.",
    )
    parser.add_argument("source", nargs="?", default=None, help="JSON file path")
    parser.add_argument("--stdin", action="store_true", help="Read from stdin")
    parser.add_argument("--json", dest="output_json", action="store_true", default=False)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.stdin:
        source = "-"
    elif args.source:
        source = args.source
    else:
        print("ERROR: Provide JSON file or --stdin", file=sys.stderr)
        return 1

    try:
        draft = load_draft(source)
    except (OSError, IOError) as e:
        print("ERROR: Cannot read: %s" % e, file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print("ERROR: Invalid JSON: %s" % e, file=sys.stderr)
        return 1

    result = validate_draft(draft)

    if args.output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}[result["overall"]]
        print("=" * 40)
        print("  Work Order Validation: %s %s" % (icon, result["overall"]))
        print("=" * 40)
        for c in result["checks"]:
            print("  ✓ %s" % c)
        for w in result["warnings"]:
            print("  ⚠ %s" % w)
        for e in result["errors"]:
            print("  ✗ %s" % e)
        print("=" * 40)

    return 0 if result["overall"] != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
