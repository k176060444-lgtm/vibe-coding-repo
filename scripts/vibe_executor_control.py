#!/usr/bin/env python3
"""Executor Control — timeout, cancel, and control contract for future real execution.

Generates control plans and cancel tokens for executor lifecycle management.
Does NOT kill processes, execute tasks, or modify any state.

Usage:
    python3 scripts/vibe_executor_control.py plan-timeout --id my-wo --max-seconds 300
    python3 scripts/vibe_executor_control.py plan-timeout --id my-wo --max-seconds 300 --json
    python3 scripts/vibe_executor_control.py cancel-token --id my-wo
    python3 scripts/vibe_executor_control.py cancel-token --id my-wo --json
    python3 scripts/vibe_executor_control.py status --id my-wo
    python3 scripts/vibe_executor_control.py status --id my-wo --json
"""

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone

VERSION = "1.0.0"

# ---------- Control Defaults ----------

DEFAULTS = {
    "max_execution_seconds": 300,
    "heartbeat_interval_seconds": 30,
    "stale_lock_threshold_seconds": 600,
    "cancel_grace_period_seconds": 10,
    "retry_max_attempts": 3,
    "retry_backoff_base_seconds": 5,
}


# ---------- CLI Handlers ----------

def cmd_plan_timeout(args):
    """Generate a timeout control plan."""
    as_json = getattr(args, "json_output", False)
    workorder_id = args.id
    max_seconds = getattr(args, "max_seconds", None) or DEFAULTS["max_execution_seconds"]
    now = datetime.now(timezone.utc).isoformat()

    plan = {
        "workorder_id": workorder_id,
        "control_type": "timeout",
        "timestamp": now,
        "timeout_config": {
            "max_execution_seconds": max_seconds,
            "heartbeat_interval_seconds": DEFAULTS["heartbeat_interval_seconds"],
            "stale_lock_threshold_seconds": DEFAULTS["stale_lock_threshold_seconds"],
            "cancel_grace_period_seconds": DEFAULTS["cancel_grace_period_seconds"],
        },
        "timeout_policy": {
            "on_timeout": "cancel_execution",
            "on_heartbeat_miss": "warn_then_cancel",
            "on_stale_lock": "force_release_and_log",
        },
        "phases": [
            {"phase": "pre-check", "timeout": "10s", "action": "validate inputs"},
            {"phase": "worktree-setup", "timeout": "30s", "action": "create/verify worktree"},
            {"phase": "implementation", "timeout": f"{max_seconds - 80}s", "action": "run coding agent"},
            {"phase": "commit", "timeout": "20s", "action": "git add/commit"},
            {"phase": "evidence", "timeout": "20s", "action": "create evidence bundle"},
        ],
        "monitoring": {
            "heartbeat_required": True,
            "heartbeat_interval": f"{DEFAULTS['heartbeat_interval_seconds']}s",
            "stale_detection": True,
            "stale_threshold": f"{DEFAULTS['stale_lock_threshold_seconds']}s",
        },
        "policy": "This is a planning-only operation. No process will be killed or task executed.",
    }

    if as_json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        _print_timeout_plan(plan)
    return 0


def cmd_cancel_token(args):
    """Generate a cancel token for a workorder."""
    as_json = getattr(args, "json_output", False)
    workorder_id = args.id
    now = datetime.now(timezone.utc).isoformat()

    # Generate a deterministic but unique token
    token_seed = f"{workorder_id}:{now}:{uuid.uuid4().hex[:8]}"
    token = hashlib.sha256(token_seed.encode()).hexdigest()[:32]

    cancel_info = {
        "workorder_id": workorder_id,
        "control_type": "cancel_token",
        "timestamp": now,
        "cancel_token": f"cancel-{token}",
        "cancel_grace_period_seconds": DEFAULTS["cancel_grace_period_seconds"],
        "cancel_methods": [
            {"method": "graceful", "description": "Send SIGTERM, wait grace period, then SIGKILL"},
            {"method": "immediate", "description": "Send SIGKILL immediately"},
            {"method": "file_signal", "description": "Write cancel file to worktree/.cancel"},
        ],
        "cancel_conditions": [
            "User explicitly requests cancellation",
            "Timeout exceeded",
            "Heartbeat missed for stale_lock_threshold",
            "Gate verdict changes to BLOCK",
            "Fatal error in executor",
        ],
        "post_cancel_actions": [
            "Log cancellation reason",
            "Release worktree lock",
            "Create partial evidence bundle if possible",
            "Update registry status to 'cancelled'",
        ],
        "policy": "This is a token generation only. No process will be cancelled.",
    }

    if as_json:
        print(json.dumps(cancel_info, indent=2, ensure_ascii=False))
    else:
        _print_cancel_token(cancel_info)
    return 0


def cmd_status(args):
    """Show executor control status."""
    as_json = getattr(args, "json_output", False)
    workorder_id = args.id
    now = datetime.now(timezone.utc).isoformat()

    status = {
        "workorder_id": workorder_id,
        "timestamp": now,
        "executor_status": "not_running",
        "control_version": VERSION,
        "defaults": DEFAULTS,
        "capabilities": {
            "timeout": "planned (not implemented)",
            "cancel": "planned (not implemented)",
            "heartbeat": "planned (not implemented)",
            "stale_detection": "planned (not implemented)",
            "retry": "planned (not implemented)",
        },
        "current_state": {
            "pid": None,
            "started_at": None,
            "last_heartbeat": None,
            "elapsed_seconds": 0,
            "phase": "idle",
        },
        "policy": "Executor is currently frozen (noop/dry-run only). Control features are planned.",
    }

    if as_json:
        print(json.dumps(status, indent=2, ensure_ascii=False))
    else:
        _print_status(status)
    return 0


# ---------- Pretty Printers ----------

def _print_timeout_plan(plan):
    print(f"Timeout Plan: {plan['workorder_id']}")
    print(f"  Max execution: {plan['timeout_config']['max_execution_seconds']}s")
    print(f"  Heartbeat: every {plan['timeout_config']['heartbeat_interval_seconds']}s")
    print(f"  Stale lock: {plan['timeout_config']['stale_lock_threshold_seconds']}s")
    print()
    print("  Phases:")
    for p in plan["phases"]:
        print(f"    [{p['timeout']}] {p['phase']}: {p['action']}")
    print()
    print("  Monitoring:")
    for k, v in plan["monitoring"].items():
        print(f"    {k}: {v}")


def _print_cancel_token(info):
    print(f"Cancel Token: {info['workorder_id']}")
    print(f"  Token: {info['cancel_token']}")
    print(f"  Grace period: {info['cancel_grace_period_seconds']}s")
    print()
    print("  Methods:")
    for m in info["cancel_methods"]:
        print(f"    {m['method']}: {m['description']}")
    print()
    print("  Conditions:")
    for c in info["cancel_conditions"]:
        print(f"    - {c}")


def _print_status(status):
    print(f"Executor Status: {status['workorder_id']}")
    print(f"  Status: {status['executor_status']}")
    print(f"  Control version: {status['control_version']}")
    print()
    print("  Capabilities:")
    for k, v in status["capabilities"].items():
        print(f"    {k}: {v}")
    print()
    print("  Current state:")
    for k, v in status["current_state"].items():
        print(f"    {k}: {v}")


# ---------- CLI Parser ----------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_executor_control",
        description="Executor Control — timeout, cancel, and control contract.",
    )
    parser.add_argument("--version", action="version", version=f"v{VERSION}")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output JSON")

    sub = parser.add_subparsers(dest="command")

    # plan-timeout
    pt = sub.add_parser("plan-timeout", aliases=["pt", "timeout"], help="Generate timeout plan")
    pt.add_argument("--id", required=True, help="Workorder ID")
    pt.add_argument("--max-seconds", type=int, help=f"Max execution seconds (default: {DEFAULTS['max_execution_seconds']})")
    pt.add_argument("--json", dest="json_output", action="store_true")

    # cancel-token
    ct = sub.add_parser("cancel-token", aliases=["ct", "cancel"], help="Generate cancel token")
    ct.add_argument("--id", required=True, help="Workorder ID")
    ct.add_argument("--json", dest="json_output", action="store_true")

    # status
    st = sub.add_parser("status", aliases=["st"], help="Show executor control status")
    st.add_argument("--id", required=True, help="Workorder ID")
    st.add_argument("--json", dest="json_output", action="store_true")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    handler = {
        "plan-timeout": cmd_plan_timeout,
        "pt": cmd_plan_timeout,
        "timeout": cmd_plan_timeout,
        "cancel-token": cmd_cancel_token,
        "ct": cmd_cancel_token,
        "cancel": cmd_cancel_token,
        "status": cmd_status,
        "st": cmd_status,
    }.get(args.command)
    if handler:
        return handler(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
