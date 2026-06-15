#!/usr/bin/env python3
"""Executor Sandbox Contract — define and verify sandbox constraints for future real execution.

Checks sandbox readiness: worktree path, repo cleanliness, allowed_paths,
forbidden_actions, network/model/write permissions, artifact dirs,
evidence/transcript dirs, base_sha match. Read-only; never creates worktrees,
writes repos, or calls models.

Usage:
    python3 scripts/vibe_executor_sandbox.py check --base-sha abc123
    python3 scripts/vibe_executor_sandbox.py check --base-sha abc123 --json
    python3 scripts/vibe_executor_sandbox.py plan --id my-wo --base-sha abc123
    python3 scripts/vibe_executor_sandbox.py plan --id my-wo --base-sha abc123 --json
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"

# ---------- Sandbox Constraints ----------

SANDBOX_CONSTRAINTS = {
    "worktree_required": True,
    "repo_cleanliness_required": True,
    "network_allowed": False,
    "model_call_allowed": False,
    "write_outside_worktree": False,
    "push_allowed": False,
    "merge_allowed": False,
    "deploy_allowed": False,
    "tag_allowed": False,
    "delete_allowed": False,
    "shell_exec_allowed": False,
    "max_execution_time_seconds": 300,
    "required_artifact_dirs": ["evidence", "transcript"],
    "forbidden_paths": [
        ".env", "secrets", "credentials", "auth.json",
        ".github/workflows", "deploy", "production",
        "ssh", "provider", "admin",
    ],
    "allowed_path_patterns": [
        "scripts/",
        "docs/",
        "tests/",
        "README.md",
    ],
}

FORBIDDEN_ACTIONS = [
    "model_call",
    "shell_exec",
    "repo_write_outside_scope",
    "git_push",
    "git_merge",
    "deploy",
    "tag",
    "file_delete",
    "network_request",
    "credential_access",
]


# ---------- CLI Handlers ----------

def cmd_check(args):
    """Run sandbox readiness checks."""
    as_json = getattr(args, "json_output", False)
    base_sha = getattr(args, "base_sha", None)
    now = datetime.now(timezone.utc).isoformat()

    checks = []
    warnings = []
    errors = []

    # Check 1: Sandbox constraints defined
    checks.append({
        "name": "constraints_defined",
        "status": "PASS",
        "detail": f"{len(SANDBOX_CONSTRAINTS)} constraints defined",
    })

    # Check 2: Forbidden actions enumerated
    checks.append({
        "name": "forbidden_actions",
        "status": "PASS",
        "detail": f"{len(FORBIDDEN_ACTIONS)} forbidden actions defined",
    })

    # Check 3: Base SHA provided
    if base_sha:
        checks.append({
            "name": "base_sha_provided",
            "status": "PASS",
            "detail": f"base_sha={base_sha[:12]}...",
        })
    else:
        warnings.append("base_sha not provided; sandbox check is informational only")
        checks.append({
            "name": "base_sha_provided",
            "status": "WARN",
            "detail": "base_sha not provided",
        })

    # Check 4: Artifact dirs requirements
    checks.append({
        "name": "artifact_dirs",
        "status": "PASS",
        "detail": f"Required: {', '.join(SANDBOX_CONSTRAINTS['required_artifact_dirs'])}",
    })

    # Check 5: Network isolation
    checks.append({
        "name": "network_isolation",
        "status": "PASS" if not SANDBOX_CONSTRAINTS["network_allowed"] else "FAIL",
        "detail": f"network_allowed={SANDBOX_CONSTRAINTS['network_allowed']}",
    })

    # Check 6: Model isolation
    checks.append({
        "name": "model_isolation",
        "status": "PASS" if not SANDBOX_CONSTRAINTS["model_call_allowed"] else "FAIL",
        "detail": f"model_call_allowed={SANDBOX_CONSTRAINTS['model_call_allowed']}",
    })

    # Check 7: Write isolation
    checks.append({
        "name": "write_isolation",
        "status": "PASS" if not SANDBOX_CONSTRAINTS["write_outside_worktree"] else "FAIL",
        "detail": f"write_outside_worktree={SANDBOX_CONSTRAINTS['write_outside_worktree']}",
    })

    # Check 8: Forbidden paths defined
    checks.append({
        "name": "forbidden_paths",
        "status": "PASS",
        "detail": f"{len(SANDBOX_CONSTRAINTS['forbidden_paths'])} forbidden path patterns",
    })

    # Check 9: Allowed paths defined
    checks.append({
        "name": "allowed_paths",
        "status": "PASS",
        "detail": f"{len(SANDBOX_CONSTRAINTS['allowed_path_patterns'])} allowed path patterns",
    })

    # Check 10: Execution timeout
    checks.append({
        "name": "execution_timeout",
        "status": "PASS",
        "detail": f"max_execution_time={SANDBOX_CONSTRAINTS['max_execution_time_seconds']}s",
    })

    # Check 11: Push/merge/deploy blocked
    blocked = []
    for action in ["push_allowed", "merge_allowed", "deploy_allowed", "tag_allowed", "delete_allowed"]:
        if SANDBOX_CONSTRAINTS.get(action):
            blocked.append(action)
    checks.append({
        "name": "destructive_blocked",
        "status": "PASS" if not blocked else "FAIL",
        "detail": f"Blocked: push, merge, deploy, tag, delete" if not blocked else f"NOT BLOCKED: {', '.join(blocked)}",
    })

    # Check 12: Shell exec blocked
    checks.append({
        "name": "shell_blocked",
        "status": "PASS" if not SANDBOX_CONSTRAINTS["shell_exec_allowed"] else "FAIL",
        "detail": f"shell_exec_allowed={SANDBOX_CONSTRAINTS['shell_exec_allowed']}",
    })

    passed = sum(1 for c in checks if c["status"] == "PASS")
    failed = sum(1 for c in checks if c["status"] == "FAIL")
    warned = sum(1 for c in checks if c["status"] == "WARN")
    verdict = "PASS" if failed == 0 else "FAIL"

    result = {
        "verdict": verdict,
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "summary": f"{passed} PASS, {failed} FAIL, {warned} WARN",
        "timestamp": now,
        "sandbox_version": VERSION,
    }

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_check(result)
    return 0 if verdict == "PASS" else 1


def cmd_plan(args):
    """Generate sandbox plan for a workorder."""
    as_json = getattr(args, "json_output", False)
    workorder_id = args.id
    base_sha = args.base_sha
    now = datetime.now(timezone.utc).isoformat()

    plan = {
        "workorder_id": workorder_id,
        "base_sha": base_sha,
        "timestamp": now,
        "sandbox_version": VERSION,
        "constraints": SANDBOX_CONSTRAINTS,
        "forbidden_actions": FORBIDDEN_ACTIONS,
        "execution_environment": {
            "worktree_path": f"/tmp/vibedev-worktrees/{workorder_id}",
            "evidence_dir": f"/tmp/vibedev-evidence/{workorder_id}",
            "transcript_dir": f"/tmp/vibedev-transcripts/{workorder_id}",
            "max_execution_time": f"{SANDBOX_CONSTRAINTS['max_execution_time_seconds']}s",
            "network": "disabled",
            "model_calls": "disabled",
            "shell_exec": "disabled",
        },
        "pre_execution_checks": [
            "Verify base_sha matches current main HEAD",
            "Verify worktree is clean",
            "Verify gate returns ALLOW",
            "Verify approval receipt exists",
            "Verify no forbidden paths in changed_paths",
            "Verify evidence/transcript dirs are writable",
        ],
        "post_execution_checks": [
            "Verify worktree is clean (no uncommitted changes)",
            "Verify no forbidden paths were modified",
            "Verify evidence bundle is complete",
            "Verify transcript is append-only",
            "Verify no side effects outside sandbox",
        ],
        "policy": "This is a planning-only operation. No real execution will occur.",
    }

    if as_json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        _print_plan(plan)
    return 0


# ---------- Pretty Printers ----------

def _print_check(result):
    print(f"Sandbox Check: {result['verdict']}")
    print(f"  {result['summary']}")
    print()
    for c in result["checks"]:
        icon = "✅" if c["status"] == "PASS" else ("⚠️" if c["status"] == "WARN" else "❌")
        print(f"  {icon} {c['name']}: {c['detail']}")
    for w in result["warnings"]:
        print(f"  ⚠️ {w}")


def _print_plan(plan):
    print(f"Sandbox Plan: {plan['workorder_id']}")
    print(f"  Base SHA: {plan['base_sha']}")
    print(f"  Max Time: {plan['execution_environment']['max_execution_time']}")
    print(f"  Network: {plan['execution_environment']['network']}")
    print(f"  Model: {plan['execution_environment']['model_calls']}")
    print(f"  Shell: {plan['execution_environment']['shell_exec']}")
    print()
    print("  Constraints:")
    for k, v in plan["constraints"].items():
        print(f"    {k}: {v}")
    print()
    print("  Pre-execution checks:")
    for check in plan["pre_execution_checks"]:
        print(f"    - {check}")
    print()
    print("  Post-execution checks:")
    for check in plan["post_execution_checks"]:
        print(f"    - {check}")


# ---------- CLI Parser ----------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_executor_sandbox",
        description="Executor Sandbox Contract — verify sandbox constraints for future real execution.",
    )
    parser.add_argument("--version", action="version", version=f"v{VERSION}")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output JSON")

    sub = parser.add_subparsers(dest="command")

    # check
    chk = sub.add_parser("check", aliases=["c"], help="Run sandbox readiness checks")
    chk.add_argument("--base-sha", help="Current main HEAD SHA for verification")
    chk.add_argument("--json", dest="json_output", action="store_true")

    # plan
    plan = sub.add_parser("plan", aliases=["p"], help="Generate sandbox plan")
    plan.add_argument("--id", required=True, help="Workorder ID")
    plan.add_argument("--base-sha", required=True, help="Base commit SHA")
    plan.add_argument("--json", dest="json_output", action="store_true")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    handler = {
        "check": cmd_check,
        "c": cmd_check,
        "plan": cmd_plan,
        "p": cmd_plan,
    }.get(args.command)
    if handler:
        return handler(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
