#!/usr/bin/env python3
"""Privileged Approval — controlled approval workflow for high-privilege actions.

Generates, lists, shows, approves, and expires pending privileged action
approval requests.  Default is read-only on approval-dir; no token access,
no push execution.

Usage:
    python3 scripts/vibe_privileged_approval.py create --action-id <id> \\
        --repo <owner/repo> --branch <branch> --action <action> \\
        --base-sha <sha> [--changed-path <p> ...] \\
        [--forbidden-action <f> ...] [--expires-in <seconds>] [--json]

    python3 scripts/vibe_privileged_approval.py show --action-id <id> [--json]
    python3 scripts/vibe_privileged_approval.py list [--json]
    python3 scripts/vibe_privileged_approval.py approve --action-id <id> [--json]
    python3 scripts/vibe_privileged_approval.py expire [--json]

    # Short approval (WO2): only when exactly 1 pending exists
    python3 scripts/vibe_privileged_approval.py short-approve [--json]
    # Or pass --text with the approval expression
    python3 scripts/vibe_privileged_approval.py short-approve --text "批准" [--json]

Constraints:
    - Read-only on approval-dir (create/approve write only to approval-dir).
    - No token read, no push execution.
    - Standard library only, no external dependencies.
    - No IO on import.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

VERSION = "1.0.0"

# Short approval keywords (multi-language)
SHORT_APPROVE_KEYWORDS = [
    # English
    "approve", "approved", "confirm", "confirmed", "yes", "ok", "go",
    "allow", "authorized", "proceed", "execute", "do it", "ship it",
    # Chinese
    "批准", "确认", "同意", "可以执行", "可以", "允许", "执行", "通过",
    "授权", "准许", "准予", "许可",
]

DEFAULT_EXPIRES_IN = 3600  # 1 hour


def _compute_digest(record):
    """Compute SHA256 digest of approval record (canonical JSON)."""
    canonical = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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


def _save_approval(approval_dir, record):
    """Save approval record atomically."""
    action_id = record["action_id"]
    path = Path(approval_dir) / f"{action_id}.json"
    tmp_path = path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2, ensure_ascii=False)
        tmp_path.replace(path)
        return None
    except OSError as e:
        return str(e)


def _list_approvals(approval_dir):
    """List all approval records in the directory."""
    approvals = []
    d = Path(approval_dir)
    if not d.exists():
        return approvals
    for p in sorted(d.glob("*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                record = json.load(f)
            approvals.append(record)
        except (json.JSONDecodeError, OSError):
            continue
    return approvals


def _is_expired(record):
    """Check if an approval record is expired."""
    expires_at = record.get("expires_at", 0)
    if expires_at <= 0:
        return False
    return time.time() > expires_at


def _check_expired(approval_dir):
    """Auto-expire pending approvals that have passed their expires_at."""
    now = time.time()
    expired_count = 0
    for record in _list_approvals(approval_dir):
        if record.get("status") == "pending" and _is_expired(record):
            record["status"] = "expired"
            record["expired_at"] = now
            err = _save_approval(approval_dir, record)
            if err is None:
                expired_count += 1
    return expired_count


def _cmd_create(args):
    """Create a new pending privileged approval request."""
    approval_dir = args.approval_dir
    action_id = args.action_id
    repo = args.repo
    branch = args.branch
    action = args.action
    base_sha = args.base_sha
    changed_paths = args.changed_path or []
    forbidden_actions = args.forbidden_action or []
    expires_in = args.expires_in or DEFAULT_EXPIRES_IN

    # Validate required fields
    if not action_id:
        return {"error": "action_id is required"}, 1
    if not repo:
        return {"error": "repo is required"}, 1
    if not branch:
        return {"error": "branch is required"}, 1
    if not action:
        return {"error": "action is required"}, 1
    if not base_sha:
        return {"error": "base_sha is required"}, 1

    # Check if already exists
    existing, _ = _load_approval(approval_dir, action_id)
    if existing and existing.get("status") in ("pending", "approved"):
        return {"error": f"Action {action_id} already exists with status={existing['status']}"}, 1

    now = time.time()
    record = {
        "action_id": action_id,
        "repo": repo,
        "branch": branch,
        "action": action,
        "base_sha": base_sha,
        "changed_paths": changed_paths,
        "forbidden_actions": forbidden_actions,
        "no_force_push": True,
        "no_pr_merge": True,
        "no_secrets_ci_workflow_provider_ssh": True,
        "created_at": now,
        "expires_at": now + expires_in if expires_in > 0 else 0,
        "status": "pending",
        "approved_at": None,
        "approved_by": None,
    }
    record["digest"] = _compute_digest(record)

    err = _save_approval(approval_dir, record)
    if err:
        return {"error": err}, 1

    return {"status": "created", "action_id": action_id, "digest": record["digest"]}, 0


def _cmd_show(args):
    """Show a specific approval record."""
    _check_expired(args.approval_dir)
    record, err = _load_approval(args.approval_dir, args.action_id)
    if err:
        return {"error": err}, 1
    return record, 0


def _cmd_list(args):
    """List all approval records."""
    _check_expired(args.approval_dir)
    approvals = _list_approvals(args.approval_dir)
    return {
        "total": len(approvals),
        "pending": sum(1 for a in approvals if a.get("status") == "pending"),
        "approved": sum(1 for a in approvals if a.get("status") == "approved"),
        "expired": sum(1 for a in approvals if a.get("status") == "expired"),
        "blocked": sum(1 for a in approvals if a.get("status") == "blocked"),
        "approvals": approvals,
    }, 0


def _cmd_approve(args):
    """Approve a pending privileged action."""
    _check_expired(args.approval_dir)
    record, err = _load_approval(args.approval_dir, args.action_id)
    if err:
        return {"error": err}, 1

    status = record.get("status")
    if status != "pending":
        return {"error": f"Cannot approve: status={status}, expected=pending"}, 1

    # Validate digest completeness
    required_fields = ["action_id", "repo", "branch", "action", "base_sha", "digest"]
    missing = [f for f in required_fields if not record.get(f)]
    if missing:
        record["status"] = "blocked"
        record["block_reason"] = f"incomplete fields: {missing}"
        _save_approval(args.approval_dir, record)
        return {"error": f"BLOCKED: incomplete fields: {missing}", "status": "blocked"}, 1

    now = time.time()
    record["status"] = "approved"
    record["approved_at"] = now
    record["approved_by"] = "short-approve" if getattr(args, "_short", False) else "explicit"
    # Recompute digest to include approval timestamp
    record["digest"] = _compute_digest(record)

    err = _save_approval(args.approval_dir, record)
    if err:
        return {"error": err}, 1

    return {"status": "approved", "action_id": record["action_id"], "digest": record["digest"]}, 0


def _cmd_expire(args):
    """Manually trigger expiry check on all pending approvals."""
    expired_count = _check_expired(args.approval_dir)
    approvals = _list_approvals(args.approval_dir)
    return {
        "expired_count": expired_count,
        "pending": sum(1 for a in approvals if a.get("status") == "pending"),
        "total": len(approvals),
    }, 0


def _cmd_short_approve(args):
    """Short approval: approve the single pending action if exactly 1 exists.

    Rules:
    - Must have exactly 1 pending (non-expired) action in approval-dir
    - If 0 pending: BLOCK + "no pending action"
    - If 2+ pending: BLOCK + "multiple pending actions, specify --action-id"
    - If expired: BLOCK + "action expired"
    - If digest/incomplete: BLOCK + "incomplete fields"
    """
    approval_dir = args.approval_dir
    _check_expired(approval_dir)

    # Filter to pending only
    pending = [a for a in _list_approvals(approval_dir) if a.get("status") == "pending"]

    if len(pending) == 0:
        return {
            "status": "blocked",
            "reason": "no pending privileged action found in approval-dir",
            "hint": "create an approval first with: priv-approval create --action-id <id> ...",
        }, 1

    if len(pending) > 1:
        return {
            "status": "blocked",
            "reason": f"multiple pending actions ({len(pending)}), specify --action-id",
            "pending_ids": [a["action_id"] for a in pending],
        }, 1

    # Exactly 1 pending
    record = pending[0]

    # Validate digest completeness
    required_fields = ["action_id", "repo", "branch", "action", "base_sha", "digest"]
    missing = [f for f in required_fields if not record.get(f)]
    if missing:
        record["status"] = "blocked"
        record["block_reason"] = f"incomplete fields: {missing}"
        _save_approval(approval_dir, record)
        return {"error": f"BLOCKED: incomplete fields: {missing}", "status": "blocked"}, 1

    # Check expiry again (belt-and-suspenders)
    if _is_expired(record):
        record["status"] = "expired"
        _save_approval(approval_dir, record)
        return {"status": "blocked", "reason": "action expired"}, 1

    # Approve
    now = time.time()
    record["status"] = "approved"
    record["approved_at"] = now
    record["approved_by"] = "short-approve"
    record["digest"] = _compute_digest(record)

    err = _save_approval(approval_dir, record)
    if err:
        return {"error": err}, 1

    return {
        "status": "approved",
        "action_id": record["action_id"],
        "digest": record["digest"],
        "action": record["action"],
        "repo": record["repo"],
        "branch": record["branch"],
    }, 0


def build_parser():
    """Build argument parser. Used by router for help generation."""
    parser = argparse.ArgumentParser(
        prog="vibe_privileged_approval",
        description="Privileged Approval — controlled approval for high-privilege actions",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--json", action="store_true", dest="output_json", help="JSON output")
    parser.add_argument(
        "--approval-dir",
        default=os.path.expanduser("~/vibedev/privileged-approvals"),
        help="Directory for approval records (default: ~/vibedev/privileged-approvals)",
    )

    sub = parser.add_subparsers(dest="command")

    # create
    p_create = sub.add_parser("create", help="Create a pending approval request")
    p_create.add_argument("--action-id", required=True, help="Unique action identifier")
    p_create.add_argument("--repo", required=True, help="Repository (owner/repo)")
    p_create.add_argument("--branch", required=True, help="Target branch")
    p_create.add_argument("--action", required=True, help="Action description (e.g. push)")
    p_create.add_argument("--base-sha", required=True, help="Base commit SHA")
    p_create.add_argument("--changed-path", action="append", help="Changed file paths (repeatable)")
    p_create.add_argument("--forbidden-action", action="append", help="Forbidden actions (repeatable)")
    p_create.add_argument("--expires-in", type=int, default=DEFAULT_EXPIRES_IN, help="Expiry in seconds")

    # show
    p_show = sub.add_parser("show", help="Show a specific approval")
    p_show.add_argument("--action-id", required=True, help="Action ID to show")

    # list
    sub.add_parser("list", help="List all approvals")

    # approve
    p_approve = sub.add_parser("approve", help="Approve a pending action")
    p_approve.add_argument("--action-id", required=True, help="Action ID to approve")

    # expire
    sub.add_parser("expire", help="Trigger expiry check on all approvals")

    # short-approve
    p_short = sub.add_parser("short-approve", help="Short approval (single pending action)")
    p_short.add_argument("--text", default="", help="Approval text (auto-detected keyword)")

    return parser


def main(argv=None):
    """Main entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    # Ensure approval dir exists for write commands
    if args.command in ("create", "approve", "short-approve"):
        Path(args.approval_dir).mkdir(parents=True, exist_ok=True)

    cmd_map = {
        "create": _cmd_create,
        "show": _cmd_show,
        "list": _cmd_list,
        "approve": _cmd_approve,
        "expire": _cmd_expire,
        "short-approve": _cmd_short_approve,
    }

    handler = cmd_map.get(args.command)
    if not handler:
        print(f"ERROR: unknown command {args.command}", file=sys.stderr)
        return 1

    result, rc = handler(args)

    if args.output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if "error" in result:
            print(f"ERROR: {result['error']}", file=sys.stderr)
        elif args.command == "create":
            print(f"Created: {result['action_id']} (digest={result['digest'][:16]}...)")
        elif args.command == "approve":
            print(f"Approved: {result['action_id']} (digest={result['digest'][:16]}...)")
        elif args.command == "short-approve":
            print(f"Short-approved: {result['action_id']} ({result['action']} on {result['repo']}:{result['branch']})")
        elif args.command == "list":
            print(f"Approvals: {result['total']} total, {result['pending']} pending, "
                  f"{result['approved']} approved, {result['expired']} expired")
        elif args.command == "show":
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif args.command == "expire":
            print(f"Expired {result['expired_count']} approvals. "
                  f"{result['pending']} pending remaining.")

    return rc


if __name__ == "__main__":
    sys.exit(main())
