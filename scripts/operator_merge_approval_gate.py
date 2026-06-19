#!/usr/bin/env python3
"""Operator Merge Approval Gate v1.0.0

Enforces that any PR merge requires a valid, auditable Operator merge approval record.
Without this record, vibe_merge_gate must fail-closed (allow_merge=false).

Usage:
    python scripts/operator_merge_approval_gate.py --self-check
    python scripts/operator_merge_approval_gate.py --approval-file FILE --pr 174 --head SHA --base SHA [--json]

Exit codes:
    0 = approval valid
    1 = approval invalid or missing
    2 = usage error
"""

__version__ = "1.0.0"

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# Required fields in an approval record
REQUIRED_FIELDS = [
    "pr_number",
    "approval_status",
    "approved_by",
    "approved_at",
    "approved_head_sha",
    "approved_base_sha",
    "merge_method_allowed",
    "approval_scope",
]

# Valid approval statuses
VALID_STATUSES = {"APPROVED"}

# Valid merge methods
VALID_MERGE_METHODS = {"merge", "squash", "rebase", "any"}

# Valid approval scopes that allow merge
VALID_MERGE_SCOPES = {"merge", "full", "operator_merge_approval"}

# Default approval expiry: 72 hours
DEFAULT_EXPIRY_HOURS = 72


def validate_approval(approval: dict, expected_pr: int = None,
                      expected_head: str = None, expected_base: str = None,
                      expiry_hours: int = DEFAULT_EXPIRY_HOURS,
                      merge_method_requested: str = None) -> dict:
    """Validate an operator merge approval record.

    Returns:
        {
            "checked": True,
            "result": "APPROVED" or "BLOCKED",
            "errors": [str],
            "approval": dict or None,
        }
    """
    errors = []

    if not approval:
        return {
            "checked": True,
            "result": "BLOCKED",
            "errors": ["no approval record provided"],
            "approval": None,
        }

    if not isinstance(approval, dict):
        return {
            "checked": True,
            "result": "BLOCKED",
            "errors": ["approval record is not a dict"],
            "approval": None,
        }

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in approval:
            errors.append(f"missing required field: {field}")
        elif approval[field] is None or approval[field] == "":
            errors.append(f"empty required field: {field}")

    if errors:
        return {
            "checked": True,
            "result": "BLOCKED",
            "errors": errors,
            "approval": approval,
        }

    # Check approval_status
    status = str(approval.get("approval_status", "")).upper()
    if status not in VALID_STATUSES:
        errors.append(f"approval_status is '{status}', expected one of {VALID_STATUSES}")

    # Check merge_method_allowed
    method = str(approval.get("merge_method_allowed", "")).lower()
    if method not in VALID_MERGE_METHODS:
        errors.append(f"merge_method_allowed is '{method}', expected one of {VALID_MERGE_METHODS}")
    elif merge_method_requested is not None:
        requested = str(merge_method_requested).lower()
        if method == "any":
            pass  # "any" allows all methods
        elif method != requested:
            errors.append(f"merge_method_allowed='{method}' does not permit requested '{requested}'")

    # Check approval_scope allows merge
    scope = str(approval.get("approval_scope", "")).lower()
    if scope not in VALID_MERGE_SCOPES:
        errors.append(f"approval_scope is '{scope}', does not include merge permission")

    # Validate SHA format: must be full 40-char hex
    sha_re = re.compile(r'^[0-9a-fA-F]{40}$')
    approved_head_raw = str(approval.get("approved_head_sha", ""))
    approved_base_raw = str(approval.get("approved_base_sha", ""))
    if not sha_re.match(approved_head_raw):
        errors.append(f"approved_head_sha is not a valid 40-char hex SHA: got {len(approved_head_raw)} chars")
    if not sha_re.match(approved_base_raw):
        errors.append(f"approved_base_sha is not a valid 40-char hex SHA: got {len(approved_base_raw)} chars")

    # Check PR number match
    if expected_pr is not None:
        try:
            pr_num = int(approval.get("pr_number", 0))
        except (ValueError, TypeError):
            pr_num = 0
        if pr_num != expected_pr:
            errors.append(f"pr_number mismatch: approval={pr_num}, expected={expected_pr}")

    # Check head SHA exact match (full 40-char)
    if expected_head is not None and sha_re.match(approved_head_raw):
        if approved_head_raw.lower() != expected_head.lower():
            errors.append(f"head SHA mismatch: approval={approved_head_raw[:12]}..., expected={expected_head[:12]}...")

    # Check base SHA exact match (full 40-char)
    if expected_base is not None and sha_re.match(approved_base_raw):
        if approved_base_raw.lower() != expected_base.lower():
            errors.append(f"base SHA mismatch: approval={approved_base_raw[:12]}..., expected={expected_base[:12]}...")

    # Check expiry
    try:
        approved_at = datetime.fromisoformat(
            approval.get("approved_at", "").replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_hours = (now - approved_at).total_seconds() / 3600
        if age_hours > expiry_hours:
            errors.append(f"approval expired: age={age_hours:.1f}h, limit={expiry_hours}h")
    except (ValueError, AttributeError):
        errors.append("approved_at is not a valid ISO timestamp")

    result = "APPROVED" if not errors else "BLOCKED"
    return {
        "checked": True,
        "result": result,
        "errors": errors,
        "approval": approval,
    }


def self_check() -> dict:
    """Run self-check with test scenarios."""
    now = datetime.now(timezone.utc).isoformat()
    past = "2020-01-01T00:00:00Z"

    def _make_valid():
        return {
            "pr_number": 174,
            "approval_status": "APPROVED",
            "approved_by": "operator_kk",
            "approved_at": now,
            "approved_head_sha": "8dfcedf9f9509069650df6642ec639421558a08e",
            "approved_base_sha": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
            "merge_method_allowed": "merge",
            "approval_scope": "merge",
        }

    scenarios = [
        {
            "id": "oa-01-no-approval",
            "description": "no approval record -> BLOCKED",
            "approval": None,
            "expected": "BLOCKED",
        },
        {
            "id": "oa-02-missing-fields",
            "description": "approval missing required fields -> BLOCKED",
            "approval": {"pr_number": 174, "approval_status": "APPROVED"},
            "expected": "BLOCKED",
        },
        {
            "id": "oa-03-head-mismatch",
            "description": "head SHA mismatch -> BLOCKED",
            "approval": {**_make_valid(), "approved_head_sha": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
            "expected": "BLOCKED",
            "expected_head": "8dfcedf9f9509069650df6642ec639421558a08e",
        },
        {
            "id": "oa-04-base-mismatch",
            "description": "base SHA mismatch -> BLOCKED",
            "approval": {**_make_valid(), "approved_base_sha": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"},
            "expected": "BLOCKED",
            "expected_base": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
        },
        {
            "id": "oa-05-status-not-approved",
            "description": "approval_status=PENDING -> BLOCKED",
            "approval": {**_make_valid(), "approval_status": "PENDING"},
            "expected": "BLOCKED",
        },
        {
            "id": "oa-06-expired",
            "description": "expired approval -> BLOCKED",
            "approval": {**_make_valid(), "approved_at": past},
            "expected": "BLOCKED",
        },
        {
            "id": "oa-07-scope-no-merge",
            "description": "approval_scope=comment -> BLOCKED",
            "approval": {**_make_valid(), "approval_scope": "comment"},
            "expected": "BLOCKED",
        },
        {
            "id": "oa-08-valid-approval",
            "description": "valid approval -> APPROVED",
            "approval": _make_valid(),
            "expected": "APPROVED",
            "expected_pr": 174,
            "expected_head": "8dfcedf9f9509069650df6642ec639421558a08e",
            "expected_base": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
        },
        {
            "id": "oa-09-pr-mismatch",
            "description": "pr_number mismatch -> BLOCKED",
            "approval": {**_make_valid(), "pr_number": 999},
            "expected": "BLOCKED",
            "expected_pr": 174,
        },
        {
            "id": "oa-10-method-invalid",
            "description": "merge_method_allowed invalid -> BLOCKED",
            "approval": {**_make_valid(), "merge_method_allowed": "magic"},
            "expected": "BLOCKED",
        },
        {
            "id": "oa-11-empty-approval",
            "description": "empty dict -> BLOCKED",
            "approval": {},
            "expected": "BLOCKED",
        },
        {
            "id": "oa-12-scope-full",
            "description": "approval_scope=full -> APPROVED",
            "approval": {**_make_valid(), "approval_scope": "full"},
            "expected": "APPROVED",
            "expected_pr": 174,
            "expected_head": "8dfcedf9f9509069650df6642ec639421558a08e",
            "expected_base": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
        },
        {
            "id": "oa-13-short-head-sha",
            "description": "short head SHA (7 chars) -> BLOCKED",
            "approval": {**_make_valid(), "approved_head_sha": "8dfcedf"},
            "expected": "BLOCKED",
        },
        {
            "id": "oa-14-short-base-sha",
            "description": "short base SHA (7 chars) -> BLOCKED",
            "approval": {**_make_valid(), "approved_base_sha": "b3a59f9"},
            "expected": "BLOCKED",
        },
        {
            "id": "oa-15-non-hex-sha",
            "description": "non-hex head SHA -> BLOCKED",
            "approval": {**_make_valid(), "approved_head_sha": "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz"},
            "expected": "BLOCKED",
        },
        {
            "id": "oa-16-merge-method-mismatch",
            "description": "allowed=merge requested=squash -> BLOCKED",
            "approval": _make_valid(),
            "expected": "BLOCKED",
            "merge_method_requested": "squash",
        },
        {
            "id": "oa-17-merge-method-any",
            "description": "allowed=any requested=rebase -> APPROVED",
            "approval": {**_make_valid(), "merge_method_allowed": "any"},
            "expected": "APPROVED",
            "expected_pr": 174,
            "expected_head": "8dfcedf9f9509069650df6642ec639421558a08e",
            "expected_base": "b3a59f9271dcbc320cd79e85d2b4470d79ecd50f",
            "merge_method_requested": "rebase",
        },
    ]

    results = []
    all_passed = True
    for scenario in scenarios:
        r = validate_approval(
            scenario["approval"],
            expected_pr=scenario.get("expected_pr"),
            expected_head=scenario.get("expected_head"),
            expected_base=scenario.get("expected_base"),
            merge_method_requested=scenario.get("merge_method_requested"),
        )
        match = r["result"] == scenario["expected"]
        status = "PASS" if match else "FAIL"
        results.append({
            "id": scenario["id"],
            "description": scenario["description"],
            "expected": scenario["expected"],
            "actual": r["result"],
            "errors": r["errors"] if not match else [],
            "status": status,
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


def main():
    parser = argparse.ArgumentParser(description="Operator Merge Approval Gate")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    parser.add_argument("--approval-file", metavar="PATH", help="Path to approval JSON")
    parser.add_argument("--pr", type=int, help="Expected PR number")
    parser.add_argument("--head", help="Expected head SHA")
    parser.add_argument("--base", help="Expected base SHA")
    parser.add_argument("--merge-method", default=None, help="Requested merge method (merge/squash/rebase)")
    parser.add_argument("--expiry-hours", type=int, default=DEFAULT_EXPIRY_HOURS,
                        help=f"Approval expiry hours (default: {DEFAULT_EXPIRY_HOURS})")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"=== OPERATOR APPROVAL GATE SELF-CHECK (v{__version__}) ===")
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

    if args.approval_file:
        try:
            with open(args.approval_file, "r", encoding="utf-8") as f:
                approval = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            approval = None
            load_error = str(e)
        else:
            load_error = None

        if approval is None:
            result = {
                "checked": True,
                "result": "BLOCKED",
                "errors": [f"could not load approval file: {load_error or 'unknown'}"],
                "approval": None,
            }
        else:
            result = validate_approval(
                approval,
                expected_pr=args.pr,
                expected_head=args.head,
                expected_base=args.base,
                expiry_hours=args.expiry_hours,
                merge_method_requested=args.merge_method,
            )

        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Operator Approval: {result['result']}")
            for e in result.get("errors", []):
                print(f"  - {e}")
        sys.exit(0 if result["result"] == "APPROVED" else 1)

    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
