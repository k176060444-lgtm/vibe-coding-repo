#!/usr/bin/env python3
"""Work Order Registry — local registry for intake/validate/packager outputs.

Provides register/list/show operations for Work Order entries stored in a
local registry directory. Each entry is a JSON file with metadata about a
work order draft or validated work order.

Usage:
    python3 scripts/vibe_workorder_registry.py register --registry-dir /path/to/registry --id my-wo --title "My Work Order"
    python3 scripts/vibe_workorder_registry.py list --registry-dir /path/to/registry
    python3 scripts/vibe_workorder_registry.py show --registry-dir /path/to/registry --id my-wo
    python3 scripts/vibe_workorder_registry.py list --registry-dir /path/to/registry --json
    python3 scripts/vibe_workorder_registry.py show --registry-dir /path/to/registry --id my-wo --json

Environment Variables:
    VIBEDEV_REGISTRY_DIR  Default registry directory (overridden by --registry-dir)
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"

VALID_STATUSES = {"draft", "validated", "packaged", "approved", "executed", "blocked"}

def _registry_dir_path(args):
    """Resolve registry directory from args or environment."""
    if args.registry_dir:
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
    tmp_file.rename(entry_file)

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

    entry = {
        "workorder_id": workorder_id,
        "title": args.title or workorder_id,
        "risk_level": args.risk_level or "low",
        "status": status,
        "base_sha": args.base_sha or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": args.source or "manual",
        "requires_human_approval": args.requires_human_approval if args.requires_human_approval is not None else False,
        "changed_paths": [],
        "forbidden_actions": [],
        "acceptance_tests": [],
        "stop_conditions": [],
    }

    _save_entry(registry_dir, entry)

    if args.json:
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
    if args.filter_status:
        entries = [e for e in entries if e.get("status") == args.filter_status]

    if args.json:
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

    if args.json:
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
        print(f"  Requires Approval: {entry.get('requires_human_approval', False)}")
        if entry.get("changed_paths"):
            print(f"  Changed Paths: {', '.join(entry['changed_paths'])}")
        if entry.get("forbidden_actions"):
            print(f"  Forbidden Actions: {', '.join(entry['forbidden_actions'])}")
    return 0

def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Work Order Registry — local registry for intake/validate/packager outputs",
        epilog="Aliases: reg (register), ls (list), info (show)\n"
               "Env: VIBEDEV_REGISTRY_DIR sets default registry directory"
    )
    parser.add_argument("--version", action="version", version=f"vibe_workorder_registry {VERSION}")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

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

    # list
    ls = sub.add_parser("list", help="List all registry entries")
    ls.add_argument("--filter-status", choices=sorted(VALID_STATUSES), help="Filter by status")
    ls.add_argument("--registry-dir", help="Registry directory")

    # show
    sh = sub.add_parser("show", help="Show details of a specific entry")
    sh.add_argument("--id", required=True, help="Work order ID")
    sh.add_argument("--registry-dir", help="Registry directory")

    return parser

def main(argv=None):
    """Main entry point (import-safe)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    # Resolve registry_dir from args
    registry_dir = getattr(args, "registry_dir", None)
    if registry_dir:
        registry_dir = Path(registry_dir)

    # Also set on args for subcommands
    args.registry_dir = registry_dir

    if args.command == "register":
        return cmd_register(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "show":
        return cmd_show(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())
