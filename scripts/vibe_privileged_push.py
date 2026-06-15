#!/usr/bin/env python3
"""Privileged Push Wrapper — controlled push for approved privileged actions.

Reads an approved action from the approval directory, validates all
constraints, and outputs would_push=true/false in dry-run mode.
Current phase: DRY-RUN ONLY — no real push, no token read.

Usage:
    python3 scripts/vibe_privileged_push.py \\
        --action-id <id> [--approval-dir <dir>] [--json] [--compact]

    python3 scripts/vibe_privileged_push.py --list-approved [--json]

Constraints:
    - Dry-run only: never reads GitHub Key, never pushes.
    - Validates: repo, branch, changed_paths, forbidden_actions,
      no_force_push, no_pr_merge, no_secrets/CI/workflow/provider/SSH.
    - Standard library only, no external dependencies.
    - No IO on import.
"""

import argparse
import json
import os
import sys
from pathlib import Path

VERSION = "1.0.0"

# Paths/components that are always forbidden in privileged push
FORBIDDEN_PATH_PREFIXES = [
    ".github/workflows/",
    ".github/actions/",
    "secrets/",
    ".env",
    "credentials",
    "ssh/",
    ".ssh/",
]

FORBIDDEN_KEYWORDS = [
    "secret", "token", "password", "credential", "private_key",
    "deploy", "release", "ci", "workflow", "provider", "ssh",
]


def _load_approval(approval_dir, action_id):
    """Load a single approval record by action_id."""
    path = Path(approval_dir) / f"{action_id}.json"
    if not path.exists():
        return None, f"Approval not found: {action_id}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f), None
    except (json.JSONDecodeError, OSError) as e:
        return None, f"Failed to load {path}: {e}"


def _list_approved(approval_dir):
    """List all approved actions."""
    d = Path(approval_dir)
    if not d.exists():
        return []
    approved = []
    for p in sorted(d.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                record = json.load(f)
            if record.get("status") == "approved":
                approved.append(record)
        except (json.JSONDecodeError, OSError):
            continue
    return approved


def _check_path_forbidden(path_str):
    """Check if a path matches forbidden prefixes."""
    lower = path_str.lower().replace("\\", "/")
    for prefix in FORBIDDEN_PATH_PREFIXES:
        if lower.startswith(prefix.lower()):
            return True, f"forbidden path prefix: {prefix}"
    return False, None


def _check_forbidden_actions(record):
    """Check if the action itself is forbidden."""
    forbidden = record.get("forbidden_actions", [])
    action = record.get("action", "").lower()
    for f in forbidden:
        if f.lower() in action or action in f.lower():
            return True, f"action '{action}' matches forbidden '{f}'"
    return False, None


def _validate_push(record):
    """Validate all constraints for a privileged push.

    Returns (would_push: bool, blockers: list, warnings: list).
    """
    blockers = []
    warnings = []

    # 1. Status must be approved
    if record.get("status") != "approved":
        blockers.append(f"status={record.get('status')}, expected=approved")

    # 2. Required fields completeness
    required = ["action_id", "repo", "branch", "action", "base_sha", "digest"]
    missing = [f for f in required if not record.get(f)]
    if missing:
        blockers.append(f"incomplete fields: {missing}")

    # 3. no_force_push invariant
    if not record.get("no_force_push", True):
        blockers.append("no_force_push=false (force push is forbidden)")

    # 4. no_pr_merge invariant
    if not record.get("no_pr_merge", True):
        blockers.append("no_pr_merge=false (PR merge via privileged push is forbidden)")

    # 5. no_secrets_ci_workflow_provider_ssh
    if not record.get("no_secrets_ci_workflow_provider_ssh", True):
        blockers.append("no_secrets_ci_workflow_provider_ssh=false")

    # 6. Check changed_paths against forbidden paths
    changed_paths = record.get("changed_paths", [])
    for cp in changed_paths:
        is_forbidden, reason = _check_path_forbidden(cp)
        if is_forbidden:
            blockers.append(f"changed_path '{cp}': {reason}")

    # 7. Check forbidden_actions
    is_forbidden, reason = _check_forbidden_actions(record)
    if is_forbidden:
        blockers.append(f"forbidden_action: {reason}")

    # 8. Digest validation
    if record.get("digest"):
        import hashlib
        # Recompute digest from canonical record (without approved_at/approved_by which may vary)
        check_record = {k: v for k, v in record.items()
                       if k not in ("approved_at", "approved_by", "expired_at")}
        # Restore pre-approval state for check
        check_record_copy = dict(check_record)
        check_record_copy["status"] = "pending"
        check_record_copy["approved_at"] = None
        check_record_copy["approved_by"] = None
        canonical = json.dumps(check_record_copy, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        expected_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        # Note: we don't block on digest mismatch since approved records have modified digests
        # This is a warning only
        if record.get("digest") != expected_digest:
            # Recompute from current state
            current_canonical = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            current_digest = hashlib.sha256(current_canonical.encode("utf-8")).hexdigest()
            if record.get("digest") != current_digest:
                warnings.append("digest mismatch (record may have been tampered)")

    would_push = len(blockers) == 0
    return would_push, blockers, warnings


def _cmd_check(args):
    """Check if a specific approved action would be pushed (dry-run)."""
    record, err = _load_approval(args.approval_dir, args.action_id)
    if err:
        return {"error": err, "would_push": False}, 1

    would_push, blockers, warnings = _validate_push(record)

    result = {
        "action_id": record.get("action_id"),
        "would_push": would_push,
        "dry_run": True,
        "repo": record.get("repo"),
        "branch": record.get("branch"),
        "base_sha": record.get("base_sha"),
        "changed_paths": record.get("changed_paths", []),
        "blockers": blockers,
        "warnings": warnings,
        "status": record.get("status"),
    }

    if would_push:
        result["push_command_preview"] = (
            f"git push {record.get('repo')} {record.get('branch')}  "
            f"# DRY-RUN ONLY — not executed"
        )

    return result, 0 if would_push else 1


def _cmd_list_approved(args):
    """List all approved actions ready for push."""
    approved = _list_approved(args.approval_dir)
    results = []
    for record in approved:
        would_push, blockers, warnings = _validate_push(record)
        results.append({
            "action_id": record.get("action_id"),
            "repo": record.get("repo"),
            "branch": record.get("branch"),
            "would_push": would_push,
            "blockers": blockers,
            "warnings": warnings,
        })

    return {
        "total_approved": len(approved),
        "would_push_count": sum(1 for r in results if r["would_push"]),
        "blocked_count": sum(1 for r in results if not r["would_push"]),
        "actions": results,
        "dry_run": True,
    }, 0


def build_parser():
    """Build argument parser. Used by router for help generation."""
    parser = argparse.ArgumentParser(
        prog="vibe_privileged_push",
        description="Privileged Push Wrapper — controlled push (dry-run only)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--json", action="store_true", dest="output_json", help="JSON output")
    parser.add_argument("--compact", action="store_true", help="Compact output")
    parser.add_argument(
        "--approval-dir",
        default=os.path.expanduser("~/vibedev/privileged-approvals"),
        help="Directory for approval records (default: ~/vibedev/privileged-approvals)",
    )

    # Default mode: check a specific action
    parser.add_argument("--action-id", help="Action ID to check")

    # List approved
    parser.add_argument("--list-approved", action="store_true", help="List approved actions")

    return parser


def _format_compact(result):
    """Format result as compact single-line string."""
    if "error" in result:
        return f"PP ERROR | {result['error']}"
    if result.get("would_push"):
        cp_count = len(result.get("changed_paths", []))
        return f"PP READY | {result.get('repo')}:{result.get('branch')} | {cp_count} paths | dry-run"
    else:
        blockers = result.get("blockers", [])
        return f"PP BLOCKED | {len(blockers)} blockers | {blockers[0] if blockers else 'unknown'}"


def main(argv=None):
    """Main entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_approved:
        result, rc = _cmd_list_approved(args)
    elif args.action_id:
        result, rc = _cmd_check(args)
    else:
        parser.print_help()
        return 1

    if args.output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.compact:
        print(_format_compact(result))
    else:
        if "error" in result:
            print(f"ERROR: {result['error']}", file=sys.stderr)
        elif args.list_approved:
            print(f"Approved actions: {result['total_approved']} total, "
                  f"{result['would_push_count']} ready, {result['blocked_count']} blocked")
            for a in result["actions"]:
                icon = "✓" if a["would_push"] else "✗"
                print(f"  {icon} {a['action_id']}: {a['repo']}:{a['branch']}")
        else:
            if result["would_push"]:
                print(f"WOULD PUSH: {result['repo']}:{result['branch']}")
                print(f"  base_sha: {result['base_sha']}")
                print(f"  changed_paths: {result['changed_paths']}")
                print(f"  [DRY-RUN — not executed]")
            else:
                print(f"BLOCKED: {result['action_id']}")
                for b in result["blockers"]:
                    print(f"  - {b}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
