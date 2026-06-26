#!/usr/bin/env python3
"""Work Order Registry — local registry for intake/validate/packager outputs.

Provides register/list/show/update-status operations for Work Order entries
stored in a local registry directory. Each entry is a JSON file with metadata
about a work order draft or validated work order.

Usage:
    python3 scripts/vibe_workorder_registry.py register --registry-dir /path --id my-wo --title "My Work Order"
    python3 scripts/vibe_workorder_registry.py list --registry-dir /path
    python3 scripts/vibe_workorder_registry.py show --registry-dir /path --id my-wo
    python3 scripts/vibe_workorder_registry.py list --registry-dir /path --json
    python3 scripts/vibe_workorder_registry.py show --registry-dir /path --id my-wo --json
    python3 scripts/vibe_workorder_registry.py update-status --registry-dir /path --id my-wo --status validated --reason "All checks passed"

Environment Variables:
    VIBEDEV_REGISTRY_DIR  Default registry directory (overridden by --registry-dir)
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.1.0"

VALID_STATUSES = {"draft", "validated", "packaged", "approved", "executed", "blocked"}

# Valid status transitions (from -> set of allowed targets)
VALID_TRANSITIONS = {
    "draft": {"validated", "blocked"},
    "validated": {"packaged", "blocked"},
    "packaged": {"approved", "blocked"},
    "approved": {"executed", "blocked"},
    "executed": {"blocked"},
    "blocked": {"draft"},  # Can reset to draft from blocked
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

def _save_entry(registry_dir, entry):
    """Save a registry entry atomically."""
    entry_file = registry_dir / f"{entry['workorder_id']}.json"
    tmp_file = entry_file.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(str(tmp_file), str(entry_file))

def _list_entries(registry_dir):
    """List all registry entries."""
    entries = []
    if not registry_dir.is_dir():
        return entries
    for f in sorted(registry_dir.glob("*.json")):
        if f.name.startswith("."):
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                entry = json.load(fh)
                if "workorder_id" in entry:
                    entries.append(entry)
        except (json.JSONDecodeError, IOError):
            continue
    return entries

def _compute_history_digest(history):
    """Compute SHA256 digest of status history."""
    history_str = json.dumps(history, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(history_str.encode("utf-8")).hexdigest()

def cmd_register(args):
    """Register a new work order entry."""
    registry_dir = _registry_dir_path(args)
    if not registry_dir:
        print("ERROR: --registry-dir or VIBEDEV_REGISTRY_DIR required", file=sys.stderr)
        return 1

    registry_dir.mkdir(parents=True, exist_ok=True)

    workorder_id = args.id
    if not workorder_id:
        print("ERROR: --id required", file=sys.stderr)
        return 1

    # Check for existing entry
    existing = _load_entry(registry_dir, workorder_id)
    if existing:
        print(f"ERROR: Entry '{workorder_id}' already exists", file=sys.stderr)
        return 1

    # Validate status
    status = args.status or "draft"
    if status not in VALID_STATUSES:
        print(f"ERROR: Invalid status '{status}'. Valid: {', '.join(sorted(VALID_STATUSES))}", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc).isoformat()
    history = [{
        "from": None,
        "to": status,
        "reason": "initial registration",
        "timestamp": now,
    }]

    entry = {
        "workorder_id": workorder_id,
        "title": args.title or workorder_id,
        "risk_level": args.risk_level or "low",
        "status": status,
        "base_sha": args.base_sha or "",
        "created_at": now,
        "updated_at": now,
        "source": args.source or "manual",
        "requires_human_approval": args.requires_human_approval if args.requires_human_approval is not None else False,
        "changed_paths": [],
        "forbidden_actions": [],
        "acceptance_tests": [],
        "stop_conditions": [],
        "status_history": history,
        "history_digest": _compute_history_digest(history),
    }

    _save_entry(registry_dir, entry)

    use_json = getattr(args, 'json', False)
    if use_json:
        print(json.dumps({"action": "register", "entry": entry}, indent=2, ensure_ascii=False))
    else:
        print(f"Registered: {workorder_id}")
        print(f"  Status: {status}")
        print(f"  Risk: {entry['risk_level']}")
        print(f"  Requires approval: {entry['requires_human_approval']}")

    return 0

def cmd_list(args):
    """List all registry entries."""
    registry_dir = _registry_dir_path(args)
    if not registry_dir:
        print("ERROR: --registry-dir or VIBEDEV_REGISTRY_DIR required", file=sys.stderr)
        return 1

    entries = _list_entries(registry_dir)

    # Filter by status if specified
    if hasattr(args, 'filter_status') and args.filter_status:
        entries = [e for e in entries if e.get("status") == args.filter_status]

    use_json = getattr(args, 'json', False)
    if use_json:
        output = {
            "action": "list",
            "registry_dir": str(registry_dir),
            "count": len(entries),
            "entries": entries,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if not entries:
            print("Registry is empty")
        else:
            print(f"Registry: {registry_dir} ({len(entries)} entries)")
            print()
            for entry in entries:
                status = entry.get("status", "unknown")
                risk = entry.get("risk_level", "?")
                approval = "⚠" if entry.get("requires_human_approval") else " "
                print(f"  {approval} [{status:10s}] [{risk:6s}] {entry['workorder_id']}: {entry.get('title', '')}")
    return 0

def cmd_show(args):
    """Show details of a specific registry entry."""
    registry_dir = _registry_dir_path(args)
    if not registry_dir:
        print("ERROR: --registry-dir or VIBEDEV_REGISTRY_DIR required", file=sys.stderr)
        return 1

    workorder_id = args.id
    if not workorder_id:
        print("ERROR: --id required", file=sys.stderr)
        return 1

    entry = _load_entry(registry_dir, workorder_id)
    if not entry:
        print(f"ERROR: Entry '{workorder_id}' not found", file=sys.stderr)
        return 1

    use_json = getattr(args, 'json', False)
    if use_json:
        output = {
            "action": "show",
            "entry": entry,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"Work Order: {entry['workorder_id']}")
        print(f"  Title: {entry.get('title', '')}")
        print(f"  Status: {entry.get('status', 'unknown')}")
        print(f"  Risk Level: {entry.get('risk_level', '?')}")
        print(f"  Base SHA: {entry.get('base_sha', '')}")
        print(f"  Source: {entry.get('source', '')}")
        print(f"  Created: {entry.get('created_at', '')}")
        print(f"  Updated: {entry.get('updated_at', '')}")
        print(f"  Requires Approval: {entry.get('requires_human_approval', False)}")
        if entry.get("changed_paths"):
            print(f"  Changed Paths: {', '.join(entry['changed_paths'])}")
        if entry.get("forbidden_actions"):
            print(f"  Forbidden Actions: {', '.join(entry['forbidden_actions'])}")
        if entry.get("status_history"):
            print(f"  Status History: {len(entry['status_history'])} transitions")
            for h in entry["status_history"][-3:]:  # Show last 3
                print(f"    {h.get('from', 'init')} → {h.get('to')}: {h.get('reason', '')}")
    return 0

def cmd_update_status(args):
    """Update status of a work order entry with controlled transitions."""
    registry_dir = _registry_dir_path(args)
    if not registry_dir:
        print("ERROR: --registry-dir or VIBEDEV_REGISTRY_DIR required", file=sys.stderr)
        return 1

    workorder_id = args.id
    if not workorder_id:
        print("ERROR: --id required", file=sys.stderr)
        return 1

    target_status = args.status
    if not target_status:
        print("ERROR: --status required", file=sys.stderr)
        return 1

    if target_status not in VALID_STATUSES:
        print(f"ERROR: Invalid status '{target_status}'. Valid: {', '.join(sorted(VALID_STATUSES))}", file=sys.stderr)
        return 1

    reason = args.reason
    if not reason:
        print("ERROR: --reason required", file=sys.stderr)
        return 1

    # Load entry
    entry = _load_entry(registry_dir, workorder_id)
    if not entry:
        print(f"ERROR: Entry '{workorder_id}' not found", file=sys.stderr)
        return 1

    current_status = entry.get("status", "draft")

    # Check valid transition
    allowed_targets = VALID_TRANSITIONS.get(current_status, set())
    if target_status not in allowed_targets:
        print(f"ERROR: Invalid transition: {current_status} → {target_status}", file=sys.stderr)
        print(f"  Allowed from '{current_status}': {', '.join(sorted(allowed_targets))}", file=sys.stderr)
        return 1

    # Update status
    now = datetime.now(timezone.utc).isoformat()
    history = entry.get("status_history", [])
    history.append({
        "from": current_status,
        "to": target_status,
        "reason": reason,
        "timestamp": now,
    })

    entry["status"] = target_status
    entry["updated_at"] = now
    entry["status_history"] = history
    entry["history_digest"] = _compute_history_digest(history)

    _save_entry(registry_dir, entry)

    use_json = getattr(args, 'json', False)
    if use_json:
        output = {
            "action": "update_status",
            "workorder_id": workorder_id,
            "from_status": current_status,
            "to_status": target_status,
            "reason": reason,
            "timestamp": now,
            "history_digest": entry["history_digest"],
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"Status Updated: {workorder_id}")
        print(f"  {current_status} → {target_status}")
        print(f"  Reason: {reason}")
        print(f"  History Digest: {entry['history_digest'][:16]}...")

    return 0

def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Work Order Registry — local registry for intake/validate/packager outputs",
        epilog="Aliases: reg (register), ls (list), info (show), update (update-status)\n"
               "Env: VIBEDEV_REGISTRY_DIR sets default registry directory"
    )
    parser.add_argument("--version", action="version", version=f"vibe_workorder_registry {VERSION}")

    sub = parser.add_subparsers(dest="command")

    # register
    reg = sub.add_parser("register", help="Register a new work order entry")
    reg.add_argument("--id", required=True, help="Work order ID")
    reg.add_argument("--title", help="Work order title")
    reg.add_argument("--risk-level", choices=["low", "medium", "high", "critical"], default="low")
    reg.add_argument("--status", choices=sorted(VALID_STATUSES), default="draft")
    reg.add_argument("--base-sha", help="Base commit SHA")
    reg.add_argument("--source", help="Source of the work order")
    reg.add_argument("--requires-human-approval", action="store_true", default=False)
    reg.add_argument("--registry-dir", help="Registry directory")
    reg.add_argument("--json", action="store_true", help="Output as JSON")

    # list
    ls = sub.add_parser("list", help="List all registry entries")
    ls.add_argument("--filter-status", choices=sorted(VALID_STATUSES), help="Filter by status")
    ls.add_argument("--registry-dir", help="Registry directory")
    ls.add_argument("--json", action="store_true", help="Output as JSON")

    # show
    sh = sub.add_parser("show", help="Show details of a specific entry")
    sh.add_argument("--id", required=True, help="Work order ID")
    sh.add_argument("--registry-dir", help="Registry directory")
    sh.add_argument("--json", action="store_true", help="Output as JSON")

    # update-status
    us = sub.add_parser("update-status", help="Update status with controlled transitions")
    us.add_argument("--id", required=True, help="Work order ID")
    us.add_argument("--status", required=True, choices=sorted(VALID_STATUSES), help="Target status")
    us.add_argument("--reason", required=True, help="Reason for status change")
    us.add_argument("--registry-dir", help="Registry directory")
    us.add_argument("--json", action="store_true", help="Output as JSON")

    return parser

def main(argv=None):
    """Main entry point (import-safe)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "register":
        return cmd_register(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "show":
        return cmd_show(args)
    elif args.command == "update-status":
        return cmd_update_status(args)
    else:
        parser.print_help()
        return 0

# ── V1.21.19: Deferred action registry glue ─────────────────────────

# Deferred action types that can be registered
DEFERRED_ACTION_TYPES = {
    "delegate_task_dispatch",
    "live_model_call",
    "service_admin_uac",
}


def register_deferred_action(action, eag_result, approval=None, repo_root=None):
    """Register a deferred action as a Work Order registry entry.

    Called after APPROVED_FOR_EXECUTION for deferred actions.
    Creates a registry entry with status 'approved' and registry_only flag.
    Graceful: returns None on any error; never raises.

    Args:
        action: Deferred action type (delegate_task_dispatch, live_model_call, service_admin_uac)
        eag_result: EAG check result dict
        approval: Approval record dict (optional)
        repo_root: Repository root path (defaults to cwd)

    Returns:
        Registry entry dict if successful, None otherwise.
    """
    try:
        if action not in DEFERRED_ACTION_TYPES:
            return None
        if eag_result is None:
            return None

        if repo_root is None:
            repo_root = os.getcwd()

        registry_dir = Path(repo_root) / ".vibe" / "deferred_registry"
        registry_dir.mkdir(parents=True, exist_ok=True)

        # Extract approval info (needed for dedup check)
        approval_id = (eag_result.get("approval_id")
                       or (approval or {}).get("approval_id", ""))

        # V1.21.20: Dedup — if same (approval_id, action) already exists, return it
        if approval_id:
            for existing_file in registry_dir.glob("*.json"):
                try:
                    with open(existing_file, "r", encoding="utf-8") as fh:
                        existing = json.load(fh)
                    if (existing.get("approval_id") == approval_id
                            and existing.get("action") == action):
                        return existing
                except (json.JSONDecodeError, IOError):
                    continue

        now = datetime.now(timezone.utc).isoformat()
        # V1.21.20: Include microseconds + random suffix to prevent any collision
        ts = now.replace(':', '').replace('-', '').replace('.', '')[:21]
        rand_suffix = os.urandom(4).hex()
        workorder_id = f"deferred-{action}-{ts}-{rand_suffix}"

        risk_level = (eag_result.get("risk_level")
                      or (approval or {}).get("risk_level", "low"))

        # service_admin_uac always CRITICAL
        if action == "service_admin_uac":
            risk_level = "critical"

        is_dedicated = False
        if action == "service_admin_uac" and approval:
            approved_actions = approval.get("approved_actions", [])
            is_dedicated = (len(approved_actions) == 1
                            and "service_admin_uac" in approved_actions)

        history = [{
            "from": None,
            "to": "approved",
            "reason": f"auto-registered from deferred action '{action}'",
            "timestamp": now,
        }]

        entry = {
            "workorder_id": workorder_id,
            "title": f"Deferred action: {action}",
            "action": action,
            "action_category": "deferred",
            "risk_level": risk_level,
            "status": "approved",
            "base_sha": "",
            "created_at": now,
            "updated_at": now,
            "source": "conversational_intake_gate",
            "requires_human_approval": True,
            "registry_only": True,
            "dry_run_only": True,
            "approval_id": approval_id,
            "eag_verdict": eag_result.get("verdict", ""),
            "eag_detail": eag_result.get("detail", ""),
            "dedicated_approval": is_dedicated,
            "changed_paths": [],
            "forbidden_actions": [],
            "acceptance_tests": [],
            "stop_conditions": [],
            "status_history": history,
            "history_digest": _compute_history_digest(history),
        }

        # Add action-specific fields from eag_result
        if action == "delegate_task_dispatch":
            entry["target_node"] = eag_result.get("target_node", "")
            entry["target_role"] = eag_result.get("target_role", "")
            entry["model_plan"] = eag_result.get("model_plan", "")
        elif action == "live_model_call":
            entry["provider"] = eag_result.get("provider", "")
            entry["model"] = eag_result.get("model", "")
            entry["budget_policy"] = eag_result.get("budget_policy", "")
        elif action == "service_admin_uac":
            entry["target_service"] = eag_result.get("target_service", "")
            entry["change_type"] = eag_result.get("change_type", "")

        _save_entry(registry_dir, entry)
        return entry
    except Exception:
        return None


if __name__ == "__main__":
    sys.exit(main())
