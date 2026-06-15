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

VERSION = "2.4.0"

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
    "dashboard": None,
    "validate-wo": "vibe_workorder_validator.py",
    "pack-wo": "vibe_workorder_packager.py",
    "preflight": None,
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
    "dash": "dashboard",
    "status-page": "dashboard",
    "validate": "validate-wo",
    "vw": "validate-wo",
    "pack": "pack-wo",
    "pw": "pack-wo",
    "pre": "preflight",
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
    "dashboard": "Project Dashboard - system status overview",
    "validate-wo": "Work Order Validator - validate intake drafts",
    "pack-wo": "Work Order Packager - package drafts into prompts",
    "preflight": "Preflight Check - intake + validate + package chain",
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



def _show_dashboard(output_json=False):
    """Show project dashboard summary."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    dashboard_path = repo_root / "docs" / "PROJECT_DASHBOARD.md"

    if output_json:
        import json as _json
        result = {
            "dashboard_path": str(dashboard_path),
            "exists": dashboard_path.exists(),
            "commands": list(COMMAND_SCRIPTS.keys()) + ["dashboard", "help", "version"],
            "aliases": dict(ALIASES),
            "version": VERSION,
        }
        # Try to read first line for baseline info
        if dashboard_path.exists():
            try:
                with open(dashboard_path, "r") as f:
                    for line in f:
                        if "Baseline" in line:
                            result["baseline"] = line.strip().split("`")[1] if "`" in line else line.strip()
                            break
            except (OSError, IOError):
                pass
        print(_json.dumps(result, indent=2))
    else:
        lines = [
            "=" * 40,
            "  \U0001f4ca Project Dashboard",
            "=" * 40,
            "",
            "  Dashboard: docs/PROJECT_DASHBOARD.md",
        ]
        if dashboard_path.exists():
            try:
                with open(dashboard_path, "r") as f:
                    content = f.read()
                # Extract key metrics
                for line in content.split("\n"):
                    if "Baseline" in line and "`" in line:
                        lines.append("  Baseline:  %s" % line.strip().split("`")[1])
                    elif "Total PRs" in line:
                        lines.append("  %s" % line.strip().replace("**", ""))
                    elif "System Status" in line:
                        lines.append("  Status:    %s" % line.split(":")[1].strip() if ":" in line else "")
                    elif "Smoke Suite" in line and "PASS" in line:
                        lines.append("  Smoke:     PASS")
                    elif "Health Check" in line and "PASS" in line:
                        lines.append("  Health:    PASS")
                    elif "Queue" in line and "Clean" in line:
                        lines.append("  Queue:     Clean")
            except (OSError, IOError):
                lines.append("  (cannot read dashboard)")
        else:
            lines.append("  (dashboard not found)")
        lines.extend([
            "",
            "  Run: python scripts/vibe_command_router.py dashboard --json",
            "  Full: cat docs/PROJECT_DASHBOARD.md",
            "=" * 40,
        ])
        print("\n".join(lines))
    return 0



def _run_preflight(requirement_text, output_json=False):
    """Run intake -> validate -> package chain."""
    import json as _json
    import tempfile
    script_dir = Path(__file__).parent

    # Step 1: Intake
    intake_path = script_dir / "vibe_workorder_intake.py"
    if not intake_path.exists():
        print("ERROR: intake script not found", file=sys.stderr)
        return 1

    try:
        cmd = [sys.executable, str(intake_path), requirement_text, "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print("ERROR: intake failed: %s" % result.stderr[:200], file=sys.stderr)
            return 1
        draft = _json.loads(result.stdout)
    except (subprocess.TimeoutExpired, _json.JSONDecodeError, OSError) as e:
        print("ERROR: intake error: %s" % e, file=sys.stderr)
        return 1

    # Step 2: Validate
    validator_path = script_dir / "vibe_workorder_validator.py"
    validation = {"overall": "SKIP"}
    if validator_path.exists():
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
                _json.dump(draft, tf)
                tf.flush()
                cmd = [sys.executable, str(validator_path), tf.name, "--json"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    validation = _json.loads(result.stdout)
            import os
            os.unlink(tf.name)
        except (subprocess.TimeoutExpired, _json.JSONDecodeError, OSError):
            pass

    # Step 3: Package
    packager_path = script_dir / "vibe_workorder_packager.py"
    package = {"total_chars": 0, "chunk_count": 0}
    if packager_path.exists():
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
                _json.dump(draft, tf)
                tf.flush()
                cmd = [sys.executable, str(packager_path), tf.name, "--json", "--compact"]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                if result.returncode == 0:
                    package = _json.loads(result.stdout)
            import os
            os.unlink(tf.name)
        except (subprocess.TimeoutExpired, _json.JSONDecodeError, OSError):
            pass

    result = {
        "requirement": requirement_text,
        "draft": {
            "work_order_id": draft.get("work_order_id"),
            "type": draft.get("type"),
            "risk_level": draft.get("risk_level"),
            "requires_human_approval": draft.get("requires_human_approval"),
        },
        "validation": {
            "overall": validation.get("overall", "SKIP"),
            "checks": len(validation.get("checks", [])),
            "warnings": len(validation.get("warnings", [])),
            "errors": len(validation.get("errors", [])),
        },
        "package": {
            "total_chars": package.get("total_chars", 0),
            "chunk_count": package.get("chunk_count", 0),
        },
        "preflight": "PASS" if validation.get("overall") in ("PASS", "WARN") else "FAIL",
    }

    if output_json:
        print(_json.dumps(result, indent=2))
    else:
        icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "⊘"}[result["preflight"]]
        print("=" * 40)
        print("  Preflight Check")
        print("=" * 40)
        print("  Requirement: %s" % result["requirement"][:60])
        print("  Draft ID:    %s" % result["draft"]["work_order_id"])
        print("  Type:        %s" % result["draft"]["type"])
        print("  Risk:        %s" % result["draft"]["risk_level"])
        print("  Human:       %s" % result["draft"]["requires_human_approval"])
        print("  Validation:  %s" % result["validation"]["overall"])
        print("  Package:     %d chars, %d chunk(s)" % (result["package"]["total_chars"], result["package"]["chunk_count"]))
        print("-" * 40)
        print("  %s Preflight: %s" % (icon, result["preflight"]))
        print("=" * 40)

    return 0 if result["preflight"] != "FAIL" else 1


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

    # Handle preflight (no script, built-in)
    if command == "preflight":
        req_text = " ".join(args.args) if args.args else ""
        if not req_text:
            print("ERROR: preflight requires requirement text", file=sys.stderr)
            print("Usage: vibe_command_router.py preflight 'your requirement here'", file=sys.stderr)
            return 1
        return _run_preflight(req_text, "--json" in args.args)

    # Handle dashboard (no script, built-in)
    if command == "dashboard":
        return _show_dashboard(args.output_json if hasattr(args, "output_json") else "--json" in args.args)

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
