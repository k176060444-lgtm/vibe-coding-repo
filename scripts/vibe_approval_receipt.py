#!/usr/bin/env python3
"""Approval Receipt — local approval receipt generator for Work Orders.

Generates approval receipts with SHA256 digest, timestamp, scope, and
stop conditions. Does NOT execute Work Orders.

Usage:
    python3 scripts/vibe_approval_receipt.py create --registry-dir /path --id my-wo --base-sha abc123 --package-digest def456 --approver "human" --approval-text "Approved for execution"
    python3 scripts/vibe_approval_receipt.py list --registry-dir /path
    python3 scripts/vibe_approval_receipt.py show --registry-dir /path --receipt-id receipt-001
    python3 scripts/vibe_approval_receipt.py list --registry-dir /path --json

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

VERSION = "1.0.0"

def _registry_dir_path(args):
    """Resolve registry directory from args or environment."""
    if hasattr(args, 'registry_dir') and args.registry_dir:
        return Path(args.registry_dir)
    env_dir = os.environ.get("VIBEDEV_REGISTRY_DIR")
    if env_dir:
        return Path(env_dir)
    return None

def _receipts_dir(registry_dir):
    """Get receipts subdirectory."""
    return registry_dir / "receipts"

def _load_receipt(receipts_dir, receipt_id):
    """Load a single receipt by ID."""
    receipt_file = receipts_dir / f"{receipt_id}.json"
    if not receipt_file.is_file():
        return None
    try:
        with open(receipt_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

def _save_receipt(receipts_dir, receipt):
    """Save a receipt atomically."""
    receipt_file = receipts_dir / f"{receipt['receipt_id']}.json"
    tmp_file = receipt_file.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp_file.rename(receipt_file)

def _list_receipts(receipts_dir, workorder_id=None):
    """List all receipts, optionally filtered by workorder_id."""
    receipts = []
    if not receipts_dir.is_dir():
        return receipts
    for f in sorted(receipts_dir.glob("*.json")):
        if f.name.startswith("."):
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                receipt = json.load(fh)
                if "receipt_id" in receipt:
                    if workorder_id and receipt.get("workorder_id") != workorder_id:
                        continue
                    receipts.append(receipt)
        except (json.JSONDecodeError, IOError):
            continue
    return receipts

def _compute_receipt_digest(receipt_data):
    """Compute SHA256 digest of receipt data."""
    data_str = json.dumps(receipt_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data_str.encode("utf-8")).hexdigest()

def cmd_create(args):
    """Create a new approval receipt."""
    registry_dir = _registry_dir_path(args)
    if not registry_dir:
        print("ERROR: --registry-dir or VIBEDEV_REGISTRY_DIR required", file=sys.stderr)
        return 1

    receipts = _receipts_dir(registry_dir)
    receipts.mkdir(parents=True, exist_ok=True)

    workorder_id = args.id
    if not workorder_id:
        print("ERROR: --id required", file=sys.stderr)
        return 1

    base_sha = args.base_sha
    if not base_sha:
        print("ERROR: --base-sha required", file=sys.stderr)
        return 1

    package_digest = args.package_digest
    if not package_digest:
        print("ERROR: --package-digest required", file=sys.stderr)
        return 1

    approver = args.approver
    if not approver:
        print("ERROR: --approver required", file=sys.stderr)
        return 1

    approval_text = args.approval_text
    if not approval_text:
        print("ERROR: --approval-text required", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc).isoformat()

    # Load workorder entry if exists
    registry_entries = list(registry_dir.glob("*.json"))
    workorder_entry = None
    for entry_file in registry_entries:
        if entry_file.name.startswith("."):
            continue
        try:
            with open(entry_file, "r", encoding="utf-8") as f:
                entry = json.load(f)
                if entry.get("workorder_id") == workorder_id:
                    workorder_entry = entry
                    break
        except (json.JSONDecodeError, IOError):
            continue

    # Generate receipt ID
    existing_receipts = _list_receipts(receipts)
    receipt_num = len(existing_receipts) + 1
    receipt_id = f"receipt-{receipt_num:03d}"

    # Receipt data for digest
    receipt_data = {
        "workorder_id": workorder_id,
        "base_sha": base_sha,
        "package_digest": package_digest,
        "approver": approver,
        "approval_text": approval_text,
        "timestamp": now,
    }

    digest = _compute_receipt_digest(receipt_data)

    receipt = {
        "receipt_id": receipt_id,
        "workorder_id": workorder_id,
        "base_sha": base_sha,
        "package_digest": package_digest,
        "approver": approver,
        "approval_text": approval_text,
        "timestamp": now,
        "digest": digest,
        "requires_human_approval": workorder_entry.get("requires_human_approval", False) if workorder_entry else False,
        "approved_scope": workorder_entry.get("changed_paths", []) if workorder_entry else [],
        "stop_conditions": workorder_entry.get("stop_conditions", []) if workorder_entry else [],
    }

    _save_receipt(receipts, receipt)

    use_json = getattr(args, 'json', False)
    if use_json:
        print(json.dumps({"action": "create", "receipt": receipt}, indent=2, ensure_ascii=False))
    else:
        print(f"Receipt Created: {receipt_id}")
        print(f"  Work Order: {workorder_id}")
        print(f"  Approver: {approver}")
        print(f"  Digest: {digest[:16]}...")
        print(f"  Timestamp: {now}")

    return 0

def cmd_list(args):
    """List all approval receipts."""
    registry_dir = _registry_dir_path(args)
    if not registry_dir:
        print("ERROR: --registry-dir or VIBEDEV_REGISTRY_DIR required", file=sys.stderr)
        return 1

    receipts = _list_receipts(_receipts_dir(registry_dir))

    use_json = getattr(args, 'json', False)
    if use_json:
        output = {
            "action": "list",
            "registry_dir": str(registry_dir),
            "count": len(receipts),
            "receipts": receipts,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if not receipts:
            print("No receipts found")
        else:
            print(f"Receipts: {len(receipts)}")
            print()
            for r in receipts:
                print(f"  [{r['receipt_id']}] {r['workorder_id']}: {r['approver']} @ {r['timestamp'][:19]}")
    return 0

def cmd_show(args):
    """Show details of a specific receipt."""
    registry_dir = _registry_dir_path(args)
    if not registry_dir:
        print("ERROR: --registry-dir or VIBEDEV_REGISTRY_DIR required", file=sys.stderr)
        return 1

    receipt_id = args.receipt_id
    if not receipt_id:
        print("ERROR: --receipt-id required", file=sys.stderr)
        return 1

    receipt = _load_receipt(_receipts_dir(registry_dir), receipt_id)
    if not receipt:
        print(f"ERROR: Receipt '{receipt_id}' not found", file=sys.stderr)
        return 1

    use_json = getattr(args, 'json', False)
    if use_json:
        output = {
            "action": "show",
            "receipt": receipt,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"Receipt: {receipt['receipt_id']}")
        print(f"  Work Order: {receipt['workorder_id']}")
        print(f"  Base SHA: {receipt['base_sha']}")
        print(f"  Package Digest: {receipt['package_digest'][:16]}...")
        print(f"  Approver: {receipt['approver']}")
        print(f"  Approval Text: {receipt['approval_text']}")
        print(f"  Timestamp: {receipt['timestamp']}")
        print(f"  Digest: {receipt['digest'][:16]}...")
        print(f"  Requires Human Approval: {receipt['requires_human_approval']}")
        if receipt.get("approved_scope"):
            print(f"  Approved Scope: {', '.join(receipt['approved_scope'])}")
        if receipt.get("stop_conditions"):
            print(f"  Stop Conditions: {len(receipt['stop_conditions'])} conditions")
    return 0

def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Approval Receipt — local approval receipt generator for Work Orders",
        epilog="Env: VIBEDEV_REGISTRY_DIR sets default registry directory"
    )
    parser.add_argument("--version", action="version", version=f"vibe_approval_receipt {VERSION}")

    sub = parser.add_subparsers(dest="command")

    # create
    cr = sub.add_parser("create", help="Create a new approval receipt")
    cr.add_argument("--id", required=True, help="Work order ID")
    cr.add_argument("--base-sha", required=True, help="Base commit SHA")
    cr.add_argument("--package-digest", required=True, help="Package digest (SHA256)")
    cr.add_argument("--approver", required=True, help="Approver label")
    cr.add_argument("--approval-text", required=True, help="Approval text")
    cr.add_argument("--registry-dir", help="Registry directory")
    cr.add_argument("--json", action="store_true", help="Output as JSON")

    # list
    ls = sub.add_parser("list", help="List all approval receipts")
    ls.add_argument("--registry-dir", help="Registry directory")
    ls.add_argument("--json", action="store_true", help="Output as JSON")

    # show
    sh = sub.add_parser("show", help="Show details of a specific receipt")
    sh.add_argument("--receipt-id", required=True, help="Receipt ID")
    sh.add_argument("--registry-dir", help="Registry directory")
    sh.add_argument("--json", action="store_true", help="Output as JSON")

    return parser

def main(argv=None):
    """Main entry point (import-safe)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "create":
        return cmd_create(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "show":
        return cmd_show(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())
