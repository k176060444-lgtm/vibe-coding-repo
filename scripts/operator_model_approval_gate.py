#!/usr/bin/env python3
"""Operator Model Approval Gate v1.0.0

Enforces that any OpenCode model execution requires a valid, auditable
operator approval record binding exact_model_id, model_pool_snapshot_sha256,
and prompt_sha256.

Usage:
    python scripts/operator_model_approval_gate.py --self-check
    python scripts/operator_model_approval_gate.py --approval-file FILE --job-id ID --node N --exact-model-id ID --prompt-sha256 SHA --snapshot-sha256 SHA --json
"""

__version__ = "1.0.0"

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from typing import Optional

REQUIRED_FIELDS = [
    "job_id",
    "node",
    "exact_model_id",
    "model_alias",
    "model_pool_snapshot_sha256",
    "prompt_sha256",
    "max_calls",
    "fallback_policy",
    "approval_status",
    "approved_by",
    "approved_at",
]

VALID_STATUSES = {"APPROVED"}
VALID_FALLBACK = {"disabled", "enabled"}


def validate_approval(approval: dict, expected_job_id: str = "",
                      expected_node: str = "", expected_model_id: str = "",
                      expected_prompt_sha: str = "",
                      expected_snapshot_sha: str = "") -> tuple[bool, list[str]]:
    """Validate an operator model approval record.

    Returns (valid, errors).
    """
    errors = []

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in approval:
            errors.append(f"missing required field: {field}")

    if errors:
        return False, errors

    # Status must be APPROVED
    if approval["approval_status"] not in VALID_STATUSES:
        errors.append(f"invalid approval_status: {approval['approval_status']}")

    # Fallback policy
    if approval.get("fallback_policy") not in VALID_FALLBACK:
        errors.append(f"invalid fallback_policy: {approval.get('fallback_policy')}")

    # If fallback enabled, must have fallback_model_id and separate approval
    if approval.get("fallback_policy") == "enabled":
        if not approval.get("fallback_model_id"):
            errors.append("fallback enabled but missing fallback_model_id")
        if not approval.get("fallback_approved"):
            errors.append("fallback enabled but not separately approved")

    # max_calls must be positive integer
    mc = approval.get("max_calls", 0)
    if not isinstance(mc, int) or mc < 1:
        errors.append(f"invalid max_calls: {mc}")

    # SHA256 format (64 hex chars)
    for sha_field in ["model_pool_snapshot_sha256", "prompt_sha256"]:
        val = approval.get(sha_field, "")
        if not isinstance(val, str) or len(val) != 64:
            errors.append(f"invalid {sha_field}: must be 64 hex chars")
        elif not all(c in "0123456789abcdef" for c in val.lower()):
            errors.append(f"invalid {sha_field}: not hex")

    # exact_model_id must contain /
    if "/" not in approval.get("exact_model_id", ""):
        errors.append("exact_model_id must be in provider/model format")

    # Bind checks (if expected values provided)
    if expected_job_id and approval.get("job_id") != expected_job_id:
        errors.append(f"job_id mismatch: {approval.get('job_id')} != {expected_job_id}")
    if expected_node and approval.get("node") != expected_node:
        errors.append(f"node mismatch: {approval.get('node')} != {expected_node}")
    if expected_model_id and approval.get("exact_model_id") != expected_model_id:
        errors.append(f"exact_model_id mismatch: {approval.get('exact_model_id')} != {expected_model_id}")
    if expected_prompt_sha and approval.get("prompt_sha256") != expected_prompt_sha:
        errors.append(f"prompt_sha256 mismatch")
    if expected_snapshot_sha and approval.get("model_pool_snapshot_sha256") != expected_snapshot_sha:
        errors.append(f"model_pool_snapshot_sha256 mismatch")

    return len(errors) == 0, errors


def generate_approval_template(job_id: str, node: str, exact_model_id: str,
                                model_alias: str, snapshot_sha256: str,
                                prompt_sha256: str, max_calls: int = 1,
                                fallback_policy: str = "disabled") -> dict:
    """Generate an operator approval template."""
    return {
        "job_id": job_id,
        "node": node,
        "exact_model_id": exact_model_id,
        "model_alias": model_alias,
        "model_pool_snapshot_sha256": snapshot_sha256,
        "prompt_sha256": prompt_sha256,
        "max_calls": max_calls,
        "fallback_policy": fallback_policy,
        "fallback_model_id": None,
        "fallback_approved": False,
        "approval_status": "NOT_APPROVED",
        "approved_by": None,
        "approved_at": None,
    }


# --- Self-check ---

def self_check() -> dict:
    checks = []
    passed = 0
    total = 0

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal passed, total
        total += 1
        if ok:
            passed += 1
        checks.append({"name": name, "passed": ok, "detail": detail})

    # oag-01: version
    check("oag-01-version", bool(__version__))

    # oag-02: valid approval
    valid_approval = {
        "job_id": "test-001", "node": "21bao",
        "exact_model_id": "opencode/mimo-v2.5-free",
        "model_alias": "mimo-free",
        "model_pool_snapshot_sha256": "a" * 64,
        "prompt_sha256": "b" * 64,
        "max_calls": 1, "fallback_policy": "disabled",
        "approval_status": "APPROVED",
        "approved_by": "Operator", "approved_at": "2026-06-20T00:00:00Z",
    }
    ok, errs = validate_approval(valid_approval)
    check("oag-02-valid", ok, str(errs))

    # oag-03: missing field
    bad1 = {k: v for k, v in valid_approval.items() if k != "job_id"}
    ok1, _ = validate_approval(bad1)
    check("oag-03-missing-field", not ok1)

    # oag-04: not approved
    bad2 = {**valid_approval, "approval_status": "PENDING"}
    ok2, _ = validate_approval(bad2)
    check("oag-04-not-approved", not ok2)

    # oag-05: invalid SHA
    bad3 = {**valid_approval, "prompt_sha256": "tooshort"}
    ok3, _ = validate_approval(bad3)
    check("oag-05-invalid-sha", not ok3)

    # oag-06: max_calls invalid
    bad4 = {**valid_approval, "max_calls": 0}
    ok4, _ = validate_approval(bad4)
    check("oag-06-max-calls", not ok4)

    # oag-07: fallback enabled without model
    bad5 = {**valid_approval, "fallback_policy": "enabled", "fallback_model_id": None, "fallback_approved": True}
    ok5, _ = validate_approval(bad5)
    check("oag-07-fallback-no-model", not ok5)

    # oag-08: fallback enabled without approval
    bad6 = {**valid_approval, "fallback_policy": "enabled", "fallback_model_id": "opencode/backup", "fallback_approved": False}
    ok6, _ = validate_approval(bad6)
    check("oag-08-fallback-no-approval", not ok6)

    # oag-09: exact_model_id format
    bad7 = {**valid_approval, "exact_model_id": "no-slash"}
    ok7, _ = validate_approval(bad7)
    check("oag-09-model-format", not ok7)

    # oag-10: binding mismatch
    ok8, _ = validate_approval(valid_approval, expected_job_id="wrong-id")
    check("oag-10-binding-mismatch", not ok8)

    # oag-11: binding match
    ok9, _ = validate_approval(valid_approval, expected_job_id="test-001",
                               expected_node="21bao",
                               expected_model_id="opencode/mimo-v2.5-free")
    check("oag-11-binding-match", ok9)

    # oag-12: template generation
    tmpl = generate_approval_template("j-001", "21bao", "opencode/mimo-v2.5-free",
                                       "mimo-free", "c" * 64, "d" * 64)
    check("oag-12-template", tmpl["approval_status"] == "NOT_APPROVED" and tmpl["fallback_policy"] == "disabled")

    # oag-13: fallback default disabled
    check("oag-13-fallback-default", tmpl["fallback_policy"] == "disabled")

    # oag-14: required fields count
    check("oag-14-required-count", len(REQUIRED_FIELDS) >= 10)

    # oag-15: valid statuses
    check("oag-15-valid-statuses", VALID_STATUSES == {"APPROVED"})

    return {
        "version": __version__,
        "passed": passed == total,
        "total_tests": total,
        "passed_count": passed,
        "failed_count": total - passed,
        "checks": checks,
        "exit_code": 0 if passed == total else 1,
    }


def main():
    parser = argparse.ArgumentParser(description="Operator Model Approval Gate")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--approval-file", help="Approval JSON file")
    parser.add_argument("--job-id", default="")
    parser.add_argument("--node", default="")
    parser.add_argument("--exact-model-id", default="")
    parser.add_argument("--prompt-sha256", default="")
    parser.add_argument("--snapshot-sha256", default="")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(result["exit_code"])

    if not args.approval_file:
        print(json.dumps({"error": "missing --approval-file"}))
        sys.exit(2)

    try:
        with open(args.approval_file, "r", encoding="utf-8") as f:
            approval = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
        print(json.dumps({"checked": True, "result": "BLOCKED", "errors": [str(e)]}))
        sys.exit(1)

    ok, errors = validate_approval(
        approval,
        expected_job_id=args.job_id,
        expected_node=args.node,
        expected_model_id=args.exact_model_id,
        expected_prompt_sha=args.prompt_sha256,
        expected_snapshot_sha=args.snapshot_sha256,
    )

    result = {
        "checked": True,
        "result": "APPROVED" if ok else "BLOCKED",
        "errors": errors,
        "approval": approval if ok else None,
    }
    print(json.dumps(result, indent=2))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
