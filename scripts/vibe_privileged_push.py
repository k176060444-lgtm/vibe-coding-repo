#!/usr/bin/env python3
"""Privileged Push Wrapper — controlled push for approved privileged actions.

Reads an approved action from the approval directory, validates all
constraints, and performs token-aware preflight before push.
Current phase: PREFLIGHT + DRY-RUN + REAL PUSH (to test branches only).

Usage:
    python3 scripts/vibe_privileged_push.py \\
        --action-id <id> [--approval-dir <dir>] [--json] [--compact]

    python3 scripts/vibe_privileged_push.py --list-approved [--json]
    python3 scripts/vibe_privileged_push.py --action-id <id> --push [--json]

Constraints:
    - Token only read after action is approved.
    - Token NEVER output to stdout/stderr/log/report.
    - Validates: repo, branch, changed_paths, forbidden_actions,
      no_force_push, no_pr_merge, no_secrets/CI/workflow/provider/SSH.
    - Real push only to self-repo test branches.
    - Standard library only, no external dependencies.
    - No IO on import.
"""

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

VERSION = "1.1.0"

# Self-repo: the only repo allowed for real privileged push
SELF_REPO = "k176060444-lgtm/vibe-coding-repo"

# Test branch prefix: only branches matching this prefix are allowed
TEST_BRANCH_PREFIX = "privileged-smoke/"

# Token file path
DEFAULT_TOKEN_FILE = "/home/vibeworker/.vibedev/secrets/github_privileged_token"

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


def _check_token_file(token_path):
    """Check token file exists with correct owner/mode/size.

    Returns (ok: bool, details: dict).  NEVER returns token content.
    """
    details = {"path": token_path, "exists": False}
    p = Path(token_path)
    if not p.exists():
        details["error"] = "token file not found"
        return False, details
    details["exists"] = True

    try:
        st = p.stat()
    except OSError as e:
        details["error"] = f"stat failed: {e}"
        return False, details

    # Check size > 20
    details["size"] = st.st_size
    if st.st_size <= 20:
        details["error"] = "token file too small (size <= 20)"
        return False, details

    # Check mode is 600 (owner read/write only)
    mode = stat.S_IMODE(st.st_mode)
    details["mode"] = oct(mode)
    if mode != 0o600:
        details["error"] = f"token file mode {oct(mode)}, expected 0o600"
        return False, details

    # Check owner (on Linux, st_uid)
    try:
        import pwd
        owner_info = pwd.getpwuid(st.st_uid)
        details["owner"] = owner_info.pw_name
        if owner_info.pw_name != "vibeworker":
            details["error"] = f"token file owner={owner_info.pw_name}, expected=vibeworker"
            return False, details
    except (ImportError, KeyError):
        # pwd module not available (Windows) or uid not found
        details["owner_check"] = "skipped (pwd unavailable)"

    details["error"] = None
    return True, details


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

    # 8. Repo restriction: only self-repo for real push
    repo = record.get("repo", "")
    if repo != SELF_REPO:
        blockers.append(f"repo '{repo}' is not self-repo ({SELF_REPO}); only self-repo privileged push allowed")

    # 9. Branch restriction: only test branch prefix for real push
    branch = record.get("branch", "")
    if not branch.startswith(TEST_BRANCH_PREFIX):
        blockers.append(f"branch '{branch}' does not start with '{TEST_BRANCH_PREFIX}'; only test branches allowed")

    would_push = len(blockers) == 0
    return would_push, blockers, warnings


def _execute_push(record, token_path, dry_run=False):
    """Execute a real git push using the token.

    Returns (success: bool, details: dict).  NEVER outputs token content.
    """
    result = {
        "action_id": record.get("action_id"),
        "repo": record.get("repo"),
        "branch": record.get("branch"),
        "dry_run": dry_run,
    }

    # 1. Validate constraints
    would_push, blockers, warnings = _validate_push(record)
    result["would_push"] = would_push
    result["blockers"] = blockers
    result["warnings"] = warnings
    if not would_push:
        result["push_executed"] = False
        return False, result

    # 2. Token preflight
    token_ok, token_details = _check_token_file(token_path)
    result["token_preflight"] = {k: v for k, v in token_details.items() if k != "content"}
    if not token_ok:
        result["push_executed"] = False
        result["blockers"].append(f"token preflight failed: {token_details.get('error')}")
        return False, result

    # 3. Read token (never output it)
    try:
        with open(token_path, "r") as f:
            token = f.read().strip()
    except OSError as e:
        result["push_executed"] = False
        result["blockers"].append(f"token read failed: {e}")
        return False, result

    if dry_run:
        result["push_executed"] = False
        result["dry_run"] = True
        result["push_preview"] = f"gh auth login --with-token < (token_file) && git push origin {record['branch']}"
        return True, result

    # 4. Execute real push via gh
    try:
        # Set up gh auth with token (via stdin, never as argument)
        proc = subprocess.run(
            ["gh", "auth", "login", "--with-token"],
            input=token, capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            result["push_executed"] = False
            result["blockers"].append(f"gh auth login failed: rc={proc.returncode}")
            return False, result

        # Configure git to use gh credential helper
        subprocess.run(
            ["gh", "auth", "setup-git"],
            capture_output=True, text=True, timeout=15,
        )

        # Push
        push_result = subprocess.run(
            ["git", "push", "origin", f"HEAD:{record['branch']}"],
            capture_output=True, text=True, timeout=60,
        )
        result["push_executed"] = True
        result["push_rc"] = push_result.returncode
        # Sanitize stderr: remove any potential token-like strings
        stderr_clean = push_result.stderr
        if token in stderr_clean:
            stderr_clean = stderr_clean.replace(token, "[REDACTED]")
        result["push_stderr"] = stderr_clean[:500]
        result["push_stdout"] = push_result.stdout[:500]

        if push_result.returncode != 0:
            result["blockers"].append(f"git push failed: rc={push_result.returncode}")
            return False, result

        return True, result

    except subprocess.TimeoutExpired:
        result["push_executed"] = False
        result["blockers"].append("push timed out")
        return False, result
    except OSError as e:
        result["push_executed"] = False
        result["blockers"].append(f"push error: {e}")
        return False, result


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


def _cmd_push(args):
    """Execute a real privileged push (token-aware)."""
    record, err = _load_approval(args.approval_dir, args.action_id)
    if err:
        return {"error": err, "would_push": False}, 1

    token_path = args.token_file or DEFAULT_TOKEN_FILE
    dry_run = args.dry_run if hasattr(args, "dry_run") else False

    success, result = _execute_push(record, token_path, dry_run=dry_run)
    return result, 0 if success else 1


def _cmd_token_preflight(args):
    """Check token file without reading its content."""
    token_path = args.token_file or DEFAULT_TOKEN_FILE
    ok, details = _check_token_file(token_path)
    return {"token_preflight": details, "ok": ok}, 0 if ok else 1


def _cmd_list_approved(args):
    """List all approved actions."""
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
        description="Privileged Push Wrapper — controlled push with token-aware preflight",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--json", action="store_true", dest="output_json", help="JSON output")
    parser.add_argument("--compact", action="store_true", help="Compact output")
    parser.add_argument(
        "--approval-dir",
        default=os.path.expanduser("~/vibedev/privileged-approvals"),
        help="Directory for approval records",
    )
    parser.add_argument(
        "--token-file",
        default=None,
        help="Path to privileged token file (default: ~/.vibedev/secrets/github_privileged_token)",
    )

    # Default mode: check a specific action
    parser.add_argument("--action-id", help="Action ID to check/push")

    # Push mode
    parser.add_argument("--push", action="store_true", help="Execute real push (requires approved action)")
    parser.add_argument("--dry-run-push", action="store_true", help="Push dry-run (validate + token preflight, no push)")

    # Token preflight
    parser.add_argument("--token-preflight", action="store_true", help="Check token file without reading content")

    # List approved
    parser.add_argument("--list-approved", action="store_true", help="List approved actions")

    return parser


def _format_compact(result):
    """Format result as compact single-line string."""
    if "error" in result:
        return f"PP ERROR | {result['error']}"
    if result.get("push_executed"):
        return f"PP PUSHED | {result.get('repo')}:{result.get('branch')} | rc={result.get('push_rc')}"
    if result.get("would_push"):
        cp_count = len(result.get("changed_paths", []))
        return f"PP READY | {result.get('repo')}:{result.get('branch')} | {cp_count} paths | dry-run"
    if result.get("token_preflight"):
        ok = result.get("ok", False)
        return f"PP TOKEN {'OK' if ok else 'FAIL'} | {result['token_preflight'].get('error', 'ok')}"
    blockers = result.get("blockers", [])
    return f"PP BLOCKED | {len(blockers)} blockers | {blockers[0] if blockers else 'unknown'}"


def main(argv=None):
    """Main entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.token_preflight:
        result, rc = _cmd_token_preflight(args)
    elif args.list_approved:
        result, rc = _cmd_list_approved(args)
    elif args.action_id and args.push:
        result, rc = _cmd_push(args)
    elif args.action_id and args.dry_run_push:
        args.dry_run = True
        result, rc = _cmd_push(args)
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
        elif args.token_preflight:
            ok = result.get("ok", False)
            print(f"Token preflight: {'OK' if ok else 'FAIL'}")
            for k, v in result["token_preflight"].items():
                if k != "content":
                    print(f"  {k}: {v}")
        else:
            if result.get("push_executed"):
                print(f"PUSHED: {result['repo']}:{result['branch']} (rc={result.get('push_rc')})")
            elif result.get("would_push"):
                print(f"WOULD PUSH: {result['repo']}:{result['branch']}")
                print(f"  [DRY-RUN — not executed]")
            else:
                print(f"BLOCKED: {result.get('action_id', 'unknown')}")
                for b in result.get("blockers", []):
                    print(f"  - {b}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
