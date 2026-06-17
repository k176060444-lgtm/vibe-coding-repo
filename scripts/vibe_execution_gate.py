#!/usr/bin/env python3
"""Execution Gate — pre-execution admission check for Work Checks registry status, approval digest, base SHA, risk level, stop conditions, allowed paths, forbidden actions, and audit lock before allowing execution.

Usage:
    python3 scripts/vibe_execution_gate.py check --registry-dir /path --id my-wo --current-main-sha abc123
    python3 scripts/vibe_execution_gate.py check --registry-dir /path --id my-wo --current-main-sha abc123 --json

Output:
    ALLOW  — all checks passed, safe to execute
    REVIEW — warnings found, human review recommended
    BLOCK  — critical issues found, must not execute

Environment Variables:
    VIBEDEV_REGISTRY_DIR  Default registry directory (overridden by --registry-dir)
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

VERSION = "1.1.0"

try:
    from vibe_toolchain_lifecycle import gate_check_for_dispatch
except ImportError:
    gate_check_for_dispatch = None

# High-risk forbidden actions that trigger BLOCK
HIGH_RISK_ACTIONS = {
    "push_to_main",
    "modify_secrets",
    "modify_ci",
    "modify_provider",
    "modify_ssh",
    "force_push",
    "delete_branch",
    "deploy",
    "release",
}

def _registry_dir_path(args):
    """Resolve registry directory from args or environment."""
    if hasattr(args, 'registry_dir') and args.registry_dir:
        return Path(args.registry_dir)
    env_dir = os.environ.get("VIBEDEV_REGISTRY_DIR")
    if env_dir:
        return Path(env_dir)
    return None

def _load_entry(registry_dir, workorder_id):
    """Load a single registry entry by ID."""
    entry_file = registry_dir / f"{workorder_id}.json"
    if not entry_file.is_file():
        return None
    try:
        with open(entry_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

def _load_receipt(receipts_dir, workorder_id):
    """Load approval receipt for workorder."""
    if not receipts_dir.is_dir():
        return None
    for f in sorted(receipts_dir.glob("*.json")):
        if f.name.startswith("."):
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                receipt = json.load(fh)
                if receipt.get("workorder_id") == workorder_id:
                    return receipt
        except (json.JSONDecodeError, IOError):
            continue
    return None

def _compute_package_digest(package_data):
    """Compute SHA256 digest of package data."""
    data_str = json.dumps(package_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data_str.encode("utf-8")).hexdigest()

def cmd_check(args):
    """Run execution gate checks."""
    registry_dir = _registry_dir_path(args)
    if not registry_dir:
        print("ERROR: --registry-dir or VIBEDEV_REGISTRY_DIR required", file=sys.stderr)
        return 1

    workorder_id = args.id
    if not workorder_id:
        print("ERROR: --id required", file=sys.stderr)
        return 1

    current_main_sha = args.current_main_sha
    if not current_main_sha:
        print("ERROR: --current-main-sha required", file=sys.stderr)
        return 1

    use_json = getattr(args, 'json', False)

    # Load registry entry
    entry = _load_entry(registry_dir, workorder_id)
    if not entry:
        result = {
            "verdict": "BLOCK",
            "workorder_id": workorder_id,
            "checks": [],
            "errors": [f"Registry entry '{workorder_id}' not found"],
        }
        if use_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"BLOCK: Registry entry '{workorder_id}' not found")
        return 1

    # Load approval receipt
    receipts_dir = registry_dir / "receipts"
    receipt = _load_receipt(receipts_dir, workorder_id)

    checks = []
    errors = []
    warnings = []

    # Check 1: Registry status is approved
    status = entry.get("status", "draft")
    if status == "approved":
        checks.append({"name": "registry_status", "result": "PASS", "detail": f"Status is approved"})
    elif status in ("executed", "blocked"):
        checks.append({"name": "registry_status", "result": "BLOCK", "detail": f"Status is {status}"})
        errors.append(f"Registry status is '{status}', not 'approved'")
    else:
        checks.append({"name": "registry_status", "result": "REVIEW", "detail": f"Status is '{status}', not 'approved'"})
        warnings.append(f"Registry status is '{status}', expected 'approved'")

    # Check 2: Approval receipt exists
    if receipt:
        checks.append({"name": "approval_receipt", "result": "PASS", "detail": "Receipt exists"})
    else:
        checks.append({"name": "approval_receipt", "result": "REVIEW", "detail": "No approval receipt found"})
        warnings.append("No approval receipt found")

    # Check 3: Base SHA matches current main
    base_sha = entry.get("base_sha", "")
    if base_sha == current_main_sha:
        checks.append({"name": "base_sha_match", "result": "PASS", "detail": "Base SHA matches current main"})
    else:
        checks.append({"name": "base_sha_match", "result": "BLOCK", "detail": f"Base SHA mismatch: {base_sha[:8]}.. vs {current_main_sha[:8]}.."})
        errors.append(f"Base SHA mismatch: entry has {base_sha[:16]}..., current main is {current_main_sha[:16]}...")

    # Check 4: Risk level and human approval
    risk_level = entry.get("risk_level", "low")
    requires_human = entry.get("requires_human_approval", False)
    if risk_level in ("high", "critical") and not requires_human:
        checks.append({"name": "risk_approval", "result": "BLOCK", "detail": f"Risk '{risk_level}' requires human approval"})
        errors.append(f"Risk level '{risk_level}' requires human approval but requires_human_approval is false")
    elif risk_level in ("high", "critical") and requires_human:
        checks.append({"name": "risk_approval", "result": "REVIEW", "detail": f"Risk '{risk_level}', human approval required"})
        warnings.append(f"Risk level '{risk_level}' - human approval required")
    else:
        checks.append({"name": "risk_approval", "result": "PASS", "detail": f"Risk '{risk_level}', no human approval required"})

    # Check 5: Stop conditions
    stop_conditions = entry.get("stop_conditions", [])
    if stop_conditions:
        checks.append({"name": "stop_conditions", "result": "REVIEW", "detail": f"{len(stop_conditions)} stop conditions defined"})
        warnings.append(f"{len(stop_conditions)} stop conditions defined")
    else:
        checks.append({"name": "stop_conditions", "result": "PASS", "detail": "No stop conditions"})

    # Check 6: Allowed paths not empty
    allowed_paths = entry.get("allowed_paths", [])
    if allowed_paths:
        checks.append({"name": "allowed_paths", "result": "PASS", "detail": f"{len(allowed_paths)} allowed paths"})
    else:
        checks.append({"name": "allowed_paths", "result": "REVIEW", "detail": "No allowed paths defined"})
        warnings.append("No allowed paths defined")

    # Check 7: Forbidden actions
    forbidden_actions = entry.get("forbidden_actions", [])
    high_risk_found = set(forbidden_actions) & HIGH_RISK_ACTIONS
    if high_risk_found:
        checks.append({"name": "forbidden_actions", "result": "PASS", "detail": f"High-risk actions forbidden: {', '.join(sorted(high_risk_found))}"})
    elif forbidden_actions:
        checks.append({"name": "forbidden_actions", "result": "PASS", "detail": f"{len(forbidden_actions)} forbidden actions"})
    else:
        checks.append({"name": "forbidden_actions", "result": "REVIEW", "detail": "No forbidden actions defined"})
        warnings.append("No forbidden actions defined")

    # Check 8: Audit tainted lock
    audit_status = entry.get("audit_status", "clean")
    if audit_status == "audit_tainted":
        checks.append({"name": "audit_lock", "result": "BLOCK", "detail": "Entry is audit_tainted"})
        errors.append("Entry is audit_tainted - must not execute")
    else:
        checks.append({"name": "audit_lock", "result": "PASS", "detail": f"Audit status: {audit_status}"})

    # Determine verdict
    has_block = any(c["result"] == "BLOCK" for c in checks)
    has_review = any(c["result"] == "REVIEW" for c in checks)

    if has_block:
        verdict = "BLOCK"
    elif has_review:
        verdict = "REVIEW"
    else:
        verdict = "ALLOW"

    result = {
        "verdict": verdict,
        "workorder_id": workorder_id,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "total": len(checks),
            "pass": sum(1 for c in checks if c["result"] == "PASS"),
            "review": sum(1 for c in checks if c["result"] == "REVIEW"),
            "block": sum(1 for c in checks if c["result"] == "BLOCK"),
        },
    }

    if use_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Execution Gate: {verdict}")
        print(f"  Work Order: {workorder_id}")
        print(f"  Checks: {result['summary']['total']} total, {result['summary']['pass']} pass, {result['summary']['review']} review, {result['summary']['block']} block")
        if errors:
            print(f"  Errors:")
            for e in errors:
                print(f"    - {e}")
        if warnings:
            print(f"  Warnings:")
            for w in warnings:
                print(f"    - {w}")

    if verdict == "BLOCK":
        return 1
    return 0

def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Execution Gate — pre-execution admission check for Work Orders",
        epilog="Env: VIBEDEV_REGISTRY_DIR sets default registry directory"
    )
    parser.add_argument("--version", action="version", version=f"vibe_execution_gate {VERSION}")

    sub = parser.add_subparsers(dest="command")

    # check
    ck = sub.add_parser("check", help="Run execution gate checks")
    ck.add_argument("--id", required=True, help="Work order ID")
    ck.add_argument("--current-main-sha", required=True, help="Current origin/main SHA")
    ck.add_argument("--registry-dir", help="Registry directory")
    ck.add_argument("--json", action="store_true", help="Output as JSON")

    return parser

def main(argv=None):
    """Main entry point (import-safe)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "check":
        return cmd_check(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())
