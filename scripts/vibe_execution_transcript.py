#!/usr/bin/env python3
"""Execution Transcript — append-only record of executor dry-run / noop sessions.

Records transcript entries for adapter plan executions (noop, dry-run only).
Each transcript captures: gate verdict, adapter plan, approval receipt digest,
base_sha, timestamp, status. Append-only; never modifies repo source code.

Usage:
    python3 scripts/vibe_execution_transcript.py create --id my-wo --adapter noop --base-sha abc123 --gate-verdict ALLOW
    python3 scripts/vibe_execution_transcript.py create --id my-wo --adapter dry-run --base-sha abc123 --gate-verdict ALLOW --json
    python3 scripts/vibe_execution_transcript.py list
    python3 scripts/vibe_execution_transcript.py list --json
    python3 scripts/vibe_execution_transcript.py show --transcript-id txn-001
    python3 scripts/vibe_execution_transcript.py show --transcript-id txn-001 --json
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"


def _transcript_dir_path(args):
    """Resolve transcript directory from args or environment."""
    if hasattr(args, "transcript_dir") and args.transcript_dir:
        return Path(args.transcript_dir)
    env_dir = os.environ.get("VIBEDEV_TRANSCRIPT_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(os.environ.get("VIBEDEV_TRANSCRIPT_DEFAULT_DIR", "/tmp/vibedev-transcripts"))


def _next_transcript_id(txn_dir):
    """Generate next sequential transcript ID."""
    txn_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(txn_dir.glob("txn-*.json"))
    if not existing:
        return "txn-001"
    nums = []
    for p in existing:
        try:
            nums.append(int(p.stem.split("-")[1]))
        except (ValueError, IndexError):
            pass
    next_num = max(nums, default=0) + 1
    return f"txn-{next_num:03d}"


def _compute_digest(entry):
    """Compute SHA256 digest of transcript entry (without digest field)."""
    digest_data = {k: v for k, v in entry.items() if k != "digest"}
    canonical = json.dumps(digest_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------- CLI Handlers ----------

def cmd_create(args):
    """Create a new transcript entry."""
    txn_dir = _transcript_dir_path(args)
    txn_id = _next_transcript_id(txn_dir)
    now = datetime.now(timezone.utc).isoformat()

    entry = {
        "transcript_id": txn_id,
        "workorder_id": args.id,
        "adapter": args.adapter,
        "base_sha": args.base_sha,
        "gate_verdict": args.gate_verdict or "ALLOW",
        "approval_receipt_digest": getattr(args, "receipt_digest", None) or "none",
        "timestamp": now,
        "status": "completed",
        "mode": args.adapter,
        "steps_executed": 1 if args.adapter == "noop" else 8,
        "side_effects": "none",
        "policy": "No real execution performed. Transcript is append-only.",
    }

    entry["digest"] = _compute_digest(entry)

    # Write to transcript dir (append-only)
    txn_dir.mkdir(parents=True, exist_ok=True)
    txn_file = txn_dir / f"{txn_id}.json"
    txn_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n")

    as_json = getattr(args, "json_output", False)
    if as_json:
        print(json.dumps(entry, indent=2, ensure_ascii=False))
    else:
        print(f"Transcript created: {txn_id}")
        print(f"  Workorder: {entry['workorder_id']}")
        print(f"  Adapter: {entry['adapter']}")
        print(f"  Gate: {entry['gate_verdict']}")
        print(f"  Status: {entry['status']}")
        print(f"  Digest: {entry['digest'][:16]}...")
        print(f"  File: {txn_file}")
    return 0


def cmd_list(args):
    """List all transcript entries."""
    txn_dir = _transcript_dir_path(args)
    as_json = getattr(args, "json_output", False)

    if not txn_dir.exists():
        if as_json:
            print(json.dumps({"transcripts": [], "count": 0}, indent=2))
        else:
            print("No transcripts found.")
        return 0

    entries = []
    for txn_file in sorted(txn_dir.glob("txn-*.json")):
        try:
            entry = json.loads(txn_file.read_text())
            entries.append(entry)
        except (json.JSONDecodeError, OSError) as e:
            if as_json:
                entries.append({"file": str(txn_file), "error": str(e)})
            else:
                print(f"WARN: Could not read {txn_file}: {e}", file=sys.stderr)

    if as_json:
        print(json.dumps({"transcripts": entries, "count": len(entries)}, indent=2, ensure_ascii=False))
    else:
        if not entries:
            print("No transcripts found.")
        else:
            print(f"Transcripts: {len(entries)}")
            for e in entries:
                tid = e.get("transcript_id", "?")
                wo = e.get("workorder_id", "?")
                adapter = e.get("adapter", "?")
                status = e.get("status", "?")
                print(f"  {tid}: {wo} [{adapter}] {status}")
    return 0


def cmd_show(args):
    """Show a specific transcript entry."""
    txn_dir = _transcript_dir_path(args)
    txn_id = args.transcript_id
    as_json = getattr(args, "json_output", False)

    txn_file = txn_dir / f"{txn_id}.json"
    if not txn_file.exists():
        print(f"ERROR: Transcript not found: {txn_id}", file=sys.stderr)
        return 1

    try:
        entry = json.loads(txn_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"ERROR: Could not read transcript: {e}", file=sys.stderr)
        return 1

    if as_json:
        print(json.dumps(entry, indent=2, ensure_ascii=False))
    else:
        print(f"Transcript: {entry.get('transcript_id', '?')}")
        print(f"  Workorder: {entry.get('workorder_id', '?')}")
        print(f"  Adapter: {entry.get('adapter', '?')}")
        print(f"  Mode: {entry.get('mode', '?')}")
        print(f"  Base SHA: {entry.get('base_sha', '?')}")
        print(f"  Gate Verdict: {entry.get('gate_verdict', '?')}")
        print(f"  Receipt Digest: {entry.get('approval_receipt_digest', '?')}")
        print(f"  Timestamp: {entry.get('timestamp', '?')}")
        print(f"  Status: {entry.get('status', '?')}")
        print(f"  Steps: {entry.get('steps_executed', '?')}")
        print(f"  Side Effects: {entry.get('side_effects', '?')}")
        print(f"  Digest: {entry.get('digest', '?')[:32]}...")
    return 0


# ---------- CLI Parser ----------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_execution_transcript",
        description="Execution Transcript — append-only record of executor dry-run / noop sessions.",
    )
    parser.add_argument("--version", action="version", version=f"v{VERSION}")
    parser.add_argument("--transcript-dir", help="Transcript directory (default: $VIBEDEV_TRANSCRIPT_DIR or /tmp/vibedev-transcripts)")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output JSON")

    sub = parser.add_subparsers(dest="command")

    # create
    create = sub.add_parser("create", aliases=["c"], help="Create transcript entry")
    create.add_argument("--id", required=True, help="Workorder ID")
    create.add_argument("--adapter", required=True, choices=["noop", "dry-run"], help="Adapter name")
    create.add_argument("--base-sha", required=True, help="Base commit SHA")
    create.add_argument("--gate-verdict", default="ALLOW", help="Gate verdict (default: ALLOW)")
    create.add_argument("--receipt-digest", help="Approval receipt digest (optional)")
    create.add_argument("--transcript-dir", help="Transcript directory")
    create.add_argument("--json", dest="json_output", action="store_true")

    # list
    lst = sub.add_parser("list", aliases=["l"], help="List transcripts")
    lst.add_argument("--transcript-dir", help="Transcript directory")
    lst.add_argument("--json", dest="json_output", action="store_true")

    # show
    show = sub.add_parser("show", aliases=["s"], help="Show transcript")
    show.add_argument("--transcript-id", required=True, help="Transcript ID")
    show.add_argument("--transcript-dir", help="Transcript directory")
    show.add_argument("--json", dest="json_output", action="store_true")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    handler = {
        "create": cmd_create,
        "c": cmd_create,
        "list": cmd_list,
        "l": cmd_list,
        "show": cmd_show,
        "s": cmd_show,
    }.get(args.command)
    if handler:
        return handler(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
