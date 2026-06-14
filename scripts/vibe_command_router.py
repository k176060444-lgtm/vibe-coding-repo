#!/usr/bin/env python3
"""Command Router v2 - Enhanced unified CLI entry point for QQ/Hermes orchestrator.

Usage:
    python scripts/vibe_command_router.py <command> [options]

Commands:
    snapshot    - Operator Snapshot (compact/full JSON)
    advisor     - Queue Advisor (lifecycle analysis)
    dispatch    - Dispatch Planner (next action suggestion)
    batch-plan  - Batch Queue Plan (execution plan)
    health      - Health Check (toolchain verification)
    smoke       - Toolchain Smoke Suite
    help        - Show this help message
    version     - Show version

Short aliases:
    s → snapshot, a → advisor, d → dispatch, b → batch-plan,
    h → health, sm → smoke, ? → help, v → version

Constraints:
    - Read-only, no IO on import, standard library only.
    - Routes to existing scripts, does not duplicate logic.
"""

import argparse
import difflib
import json
import os
import subprocess
import sys
from pathlib import Path

VERSION = "2.2.0"

# Command to script mapping
COMMAND_SCRIPTS = {
    "snapshot": "vibe_operator_snapshot.py",
    "advisor": "vibe_queue_advisor.py",
    "dispatch": "vibe_dispatch_planner.py",
    "batch-plan": "vibe_batch_plan.py",
    "health": "vibe_health_check.py",
    "smoke": "test_toolchain_smoke.py",
    "intake": "vibe_workorder_intake.py",
    "release-notes": "vibe_release_notes.py",
}

# Short aliases
ALIASES = {
    "s": "snapshot",
    "a": "advisor",
    "d": "dispatch",
    "b": "batch-plan",
    "h": "health",
    "sm": "smoke",
    "i": "intake",
    "wo": "intake",
    "notes": "release-notes",
    "rn": "release-notes",
    "progress": "release-notes",
    "?": "help",
    "v": "version",
}

# Command descriptions
COMMAND_DESCRIPTIONS = {
    "snapshot": "Operator Snapshot - unified status for QQ/Hermes orchestrator",
    "advisor": "Queue Advisor - lifecycle analysis and action items",
    "dispatch": "Dispatch Planner - next Work Order suggestions",
    "batch-plan": "Batch Queue Plan - execution plan for multiple Work Orders",
    "health": "Health Check - toolchain verification",
    "smoke": "Toolchain Smoke Suite - verify all tools work",
    "intake": "Work Order Intake - convert requirements to drafts",
    "release-notes": "Release Notes - progress report from git history",
    "help": "Show this help message",
    "version": "Show version",
}

# Per-command example flags for error suggestions
COMMAND_FLAGS = {
    "snapshot": ["--compact", "--json", "--include-merged", "--include-tainted", "--jobs-dir"],
    "advisor": ["--json", "--include-tainted", "--include-merged", "--jobs-dir"],
    "dispatch": ["--json", "--compact", "--jobs-dir"],
    "batch-plan": ["--json", "--limit", "--jobs-dir"],
    "health": ["--json", "--jobs-dir"],
    "smoke": ["--json", "--jobs-dir"],
}


def _run_script(script_path, args):
    """Run a Python script and return exit code."""
    try:
        cmd = [sys.executable, str(script_path)] + args
        result = subprocess.run(cmd, timeout=60)
        return result.returncode
    except subprocess.TimeoutExpired:
        print("ERROR: Script timed out: %s" % script_path, file=sys.stderr)
        return 1
    except (OSError, FileNotFoundError) as e:
        print("ERROR: Failed to run script: %s: %s" % (script_path, e), file=sys.stderr)
        return 1


def _resolve_command(raw):
    """Resolve a command name, checking aliases and close matches."""
    # Exact match
    if raw in COMMAND_SCRIPTS or raw in ("help", "version"):
        return raw

    # Alias match
    if raw in ALIASES:
        return ALIASES[raw]

    # Close match suggestion
    all_names = list(COMMAND_SCRIPTS.keys()) + list(ALIASES.keys()) + ["help", "version"]
    matches = difflib.get_close_matches(raw, all_names, n=1, cutoff=0.6)
    if matches:
        print("ERROR: Unknown command '%s'. Did you mean '%s'?" % (raw, matches[0]), file=sys.stderr)
    else:
        print("ERROR: Unknown command '%s'" % raw, file=sys.stderr)
        print("Available: %s" % ", ".join(sorted(COMMAND_SCRIPTS.keys())), file=sys.stderr)
        print("Aliases:   %s" % ", ".join("%s->%s" % (k, v) for k, v in sorted(ALIASES.items())), file=sys.stderr)
    return None


def _show_help():
    """Show help message."""
    lines = [
        "vibe_command_router v%s - Unified CLI entry point" % VERSION,
        "",
        "Usage:",
        "  python scripts/vibe_command_router.py <command> [options]",
        "",
        "Commands:",
    ]
    for cmd, desc in COMMAND_DESCRIPTIONS.items():
        lines.append("  %-12s %s" % (cmd, desc))
    lines.extend([
        "",
        "Aliases:",
        "  s=snapshot  a=advisor  d=dispatch  b=batch-plan",
        "  h=health    sm=smoke   ?=help      v=version",
        "",
        "Examples:",
        "  vibe_command_router snapshot --compact",
        "  vibe_command_router s --json              # same as snapshot --json",
        "  vibe_command_router advisor --json",
        "  vibe_command_router dispatch --compact",
        "  vibe_command_router batch-plan --json --limit 3",
        "  vibe_command_router health",
        "  vibe_command_router smoke",
        "",
        "For command-specific help:",
        "  vibe_command_router <command> --help",
    ])
    print("\n".join(lines))


def _show_version():
    """Show version."""
    print("vibe_command_router %s" % VERSION)
    print("Scripts: %d registered" % len(COMMAND_SCRIPTS))
    print("Aliases: %d defined" % len(ALIASES))


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_command_router",
        description="Command Router v2 - Enhanced unified CLI for QQ/Hermes orchestrator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Aliases: s=snapshot a=advisor d=dispatch b=batch-plan h=health sm=smoke i/intake=wo-intake notes/rn/progress=release-notes ?=help v=version",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="help",
        help="Command to execute (default: help). Supports aliases.",
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

    raw_command = args.command

    # Handle help
    if raw_command in ("help", "--help", "-h", "?"):
        _show_help()
        return 0

    # Handle version
    if raw_command in ("version", "--version", "-V", "v"):
        _show_version()
        return 0

    # Resolve command (alias + close match)
    command = _resolve_command(raw_command)
    if command is None:
        return 1

    # Handle help/version after alias resolution
    if command == "help":
        _show_help()
        return 0
    if command == "version":
        _show_version()
        return 0

    # Get script path
    script_name = COMMAND_SCRIPTS[command]
    script_dir = Path(__file__).parent
    script_path = script_dir / script_name

    # Check if script exists
    if not script_path.exists():
        print("ERROR: Script not found: %s" % script_path, file=sys.stderr)
        return 1

    # Run the script with remaining arguments
    return _run_script(script_path, args.args)


if __name__ == "__main__":
    sys.exit(main())
