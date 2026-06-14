#!/usr/bin/env python3
"""Command Router v1 - Unified CLI entry point for QQ/Hermes orchestrator.

Usage:
    python scripts/vibe_command_router.py <command> [options]

Commands:
    snapshot    - Operator Snapshot (compact/full JSON)
    advisor     - Queue Advisor (lifecycle analysis)
    dispatch    - Dispatch Planner (next action suggestion)
    batch-plan  - Batch Queue Plan (execution plan)
    health      - Health Check (toolchain verification)
    help        - Show this help message

Constraints:
    - Read-only, no IO on import, standard library only.
    - Routes to existing scripts, does not duplicate logic.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# Command to script mapping
COMMAND_SCRIPTS = {
    "snapshot": "vibe_operator_snapshot.py",
    "advisor": "vibe_queue_advisor.py",
    "dispatch": "vibe_dispatch_planner.py",
    "batch-plan": "vibe_batch_plan.py",
    "health": "vibe_health_check.py",
}

# Command descriptions
COMMAND_DESCRIPTIONS = {
    "snapshot": "Operator Snapshot - unified status for QQ/Hermes orchestrator",
    "advisor": "Queue Advisor - lifecycle analysis and action items",
    "dispatch": "Dispatch Planner - next Work Order suggestions",
    "batch-plan": "Batch Queue Plan - execution plan for multiple Work Orders",
    "health": "Health Check - toolchain verification",
    "help": "Show this help message",
}


def _run_script(script_path, args):
    """Run a Python script and return exit code."""
    try:
        cmd = [sys.executable, str(script_path)] + args
        result = subprocess.run(cmd, timeout=60)
        return result.returncode
    except subprocess.TimeoutExpired:
        print(f"ERROR: Script timed out: {script_path}", file=sys.stderr)
        return 1
    except (OSError, FileNotFoundError) as e:
        print(f"ERROR: Failed to run script: {script_path}: {e}", file=sys.stderr)
        return 1


def _show_help():
    """Show help message."""
    print("vibe_command_router - Unified CLI entry point for QQ/Hermes orchestrator")
    print()
    print("Usage:")
    print("  python scripts/vibe_command_router.py <command> [options]")
    print()
    print("Commands:")
    for cmd, desc in COMMAND_DESCRIPTIONS.items():
        print(f"  {cmd:12s} - {desc}")
    print()
    print("Examples:")
    print("  python scripts/vibe_command_router.py snapshot --compact")
    print("  python scripts/vibe_command_router.py advisor --json")
    print("  python scripts/vibe_command_router.py dispatch --compact")
    print("  python scripts/vibe_command_router.py batch-plan --json --limit 3")
    print("  python scripts/vibe_command_router.py health")
    print()
    print("For command-specific help, use:")
    print("  python scripts/vibe_command_router.py <command> --help")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_command_router",
        description="Command Router v1 - Unified CLI entry point for QQ/Hermes orchestrator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  snapshot    - Operator Snapshot (compact/full JSON)
  advisor     - Queue Advisor (lifecycle analysis)
  dispatch    - Dispatch Planner (next action suggestion)
  batch-plan  - Batch Queue Plan (execution plan)
  health      - Health Check (toolchain verification)
  help        - Show this help message

Examples:
  vibe_command_router snapshot --compact
  vibe_command_router advisor --json
  vibe_command_router dispatch --compact
  vibe_command_router batch-plan --json --limit 3
  vibe_command_router health
        """,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="help",
        help="Command to execute (default: help)",
    )
    parser.add_argument(
        "args",
        nargs=argparse.REMAINDER,
        help="Arguments to pass to the command",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    command = args.command

    # Handle help command
    if command == "help" or command == "--help" or command == "-h":
        _show_help()
        return 0

    # Check if command is valid
    if command not in COMMAND_SCRIPTS:
        print(f"ERROR: Unknown command: {command}", file=sys.stderr)
        print(f"Available commands: {', '.join(COMMAND_SCRIPTS.keys())}", file=sys.stderr)
        return 1

    # Get script path
    script_name = COMMAND_SCRIPTS[command]
    script_dir = Path(__file__).parent
    script_path = script_dir / script_name

    # Check if script exists
    if not script_path.exists():
        print(f"ERROR: Script not found: {script_path}", file=sys.stderr)
        return 1

    # Run the script with remaining arguments
    return _run_script(script_path, args.args)


if __name__ == "__main__":
    sys.exit(main())
