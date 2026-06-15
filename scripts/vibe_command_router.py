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
    intake      - Work Order Intake (NL to draft)
    release-notes - Release Notes (progress from git)
    dashboard   - Project Dashboard (status overview)
    validate-wo - Work Order Validator (draft validation)
    pack-wo     - Work Order Packager (draft to prompt)
    preflight   - Preflight Check (intake+validate+pack)
    registry    - Work Order Registry (register/list/show/update-status)
    wo-status   - Work Order Status Update (registry update-status)
    receipt     - Approval Receipt (create/list/show)
    evidence    - Execution Evidence (create/list/show)
    exec-gate   - Execution Gate (pre-execution admission check)
    safe-executor - Safe Executor (execution plan generator)
    quality-gate - Workflow Quality Gate (aggregated health check)
    help        - Show this help message
    version     - Show version

Short aliases:
    s → snapshot, a → advisor, d → dispatch, b → batch-plan,
    h → health, sm → smoke, i/wo → intake, notes/rn/progress → release-notes,
    dash/status-page → dashboard, validate/vw → validate-wo, pack/pw → pack-wo,
    pre → preflight, reg/wo-list/wo-show → registry, ws → wo-status,
    approve-receipt → receipt, ar → receipt, ev → evidence, exec-log → evidence,
    gate → exec-gate, ready-run → exec-gate, se → safe-executor, plan → safe-executor, qg → quality-gate, go-no-go → quality-gate, ? → help, v → version

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

VERSION = "2.10.0"

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
    "registry": "vibe_workorder_registry.py",
    "wo-status": "vibe_workorder_registry.py",
    "receipt": "vibe_approval_receipt.py",
    "evidence": "vibe_execution_evidence.py",
    "exec-gate": "vibe_execution_gate.py",
    "safe-executor": "vibe_safe_executor.py",
    "adapter": "vibe_executor_adapter.py",
    "loop-summary": "vibe_loop_summary.py",
    "sandbox": "vibe_executor_sandbox.py",
    "exec-control": "vibe_executor_control.py",
    "recovery": "vibe_executor_recovery.py",
    "unfreeze-checklist": "vibe_executor_unfreeze_checklist.py",
    "transcript": "vibe_execution_transcript.py",
    "quality-gate": "vibe_quality_gate.py",
    "run-report": "vibe_run_report.py",
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
    "reg": "registry",
    "wo-list": "registry",
    "wo-show": "registry",
    "ws": "wo-status",
    "approve-receipt": "receipt",
    "ar": "receipt",
    "ev": "evidence",
    "exec-log": "evidence",
    "gate": "exec-gate",
    "ready-run": "exec-gate",
    "se": "safe-executor",
    "plan": "safe-executor",
    "ac": "adapter",
    "ls": "loop-summary",
    "sb": "sandbox",
    "ec": "exec-control",
    "rc": "recovery",
    "uc": "unfreeze-checklist",
    "unfreeze": "unfreeze-checklist",
    "recover": "recovery",
    "ctrl": "exec-control",
    "summary": "loop-summary",
    "txn": "transcript",
    "exec-txn": "transcript",
    "adapter-cap": "adapter",
    "qg": "quality-gate",
    "go-no-go": "quality-gate",
    "rr": "run-report",
    "handoff": "run-report",
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
    "registry": "Work Order Registry - register/list/show/update-status",
    "wo-status": "Work Order Status Update - controlled status transitions",
    "receipt": "Approval Receipt - create/list/show approval receipts",
    "evidence": "Execution Evidence - create/list/show evidence bundles",
    "exec-gate": "Execution Gate - pre-execution admission check (ALLOW/REVIEW/BLOCK)",
    "safe-executor": "Safe Executor - generate execution plans (no real execution)",
    "adapter": "Executor Adapter Contract - query and validate adapter capabilities",
    "loop-summary": "Autonomous Loop Summary - complete chain capability overview",
    "sandbox": "Executor Sandbox Contract - verify sandbox constraints",
    "exec-control": "Executor Control - timeout, cancel, and lifecycle management",
    "recovery": "Executor Recovery Plan - failure recovery/rollback plan generator",
    "unfreeze-checklist": "Executor Unfreeze Checklist - machine-readable unfreeze readiness check",
    "transcript": "Execution Transcript - append-only record of dry-run / noop sessions",
    "quality-gate": "Workflow Quality Gate - aggregated pre/post-execution health check",
    "run-report": "Run Report / Session Handoff - execution summary for QQ/mobile",
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
    "registry": ["--json", "--registry-dir"],
    "wo-status": ["--json", "--registry-dir"],
    "receipt": ["--json", "--registry-dir"],
    "evidence": ["--json", "--evidence-dir"],
    "exec-gate": ["--json", "--registry-dir"],
    "safe-executor": ["--json", "--registry-dir"],
    "adapter": ["--json", "--adapter"],
    "loop-summary": ["--json", "--compact"],
    "sandbox": ["--json", "--base-sha"],
    "exec-control": ["--json"],
    "recovery": ["--json"],
    "unfreeze-checklist": ["--json", "--compact", "--level"],
    "transcript": ["--json", "--transcript-dir"],
    "quality-gate": ["--json", "--compact", "--repo-root", "--jobs-dir"],
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

    max_name = max(len(n) for n in COMMAND_SCRIPTS) + 2
    for name in sorted(COMMAND_SCRIPTS):
        desc = COMMAND_DESCRIPTIONS.get(name, "")
        lines.append("  %s%s%s" % (name, " " * (max_name - len(name)), desc))

    lines.append("")
    lines.append("Aliases:")
    alias_groups = {}
    for alias, target in sorted(ALIASES.items()):
        alias_groups.setdefault(target, []).append(alias)
    for target in sorted(alias_groups):
        aliases = ", ".join(alias_groups[target])
        lines.append("  %s → %s" % (aliases, target))

    lines.append("")
    lines.append("Key Commands:")
    lines.append("  quality-gate (qg, go-no-go)  Pre/post execution health check")
    lines.append("  run-report (rr, handoff)     Session handoff / execution summary")
    lines.append("  smoke                        Full smoke suite (75 tests)")
    lines.append("  health                       Quick health check")
    lines.append("  snapshot                     Operator status snapshot")
    lines.append("")
    lines.append("Options:")
    lines.append("  --help, -h    Show this help message")
    lines.append("  --version     Show version")
    lines.append("")
    lines.append("Built-in commands (preflight, dashboard) run internally.")
    lines.append("Other commands route to scripts/vibe_*.py")
    lines.append("")
    lines.append("Examples:")
    lines.append("  python scripts/vibe_command_router.py snapshot --compact")
    lines.append("  python scripts/vibe_command_router.py s --json")
    lines.append("  python scripts/vibe_command_router.py pre 'Add --verbose flag to health check'")
    lines.append("  python scripts/vibe_command_router.py reg list --registry-dir /tmp/registry")
    lines.append("  python scripts/vibe_command_router.py ws --id my-wo --status validated --reason 'OK'")
    lines.append("  python scripts/vibe_command_router.py ar create --id my-wo --base-sha abc123 ...")
    lines.append("  python scripts/vibe_command_router.py ev create --id my-wo --base-sha abc123 --result-sha def456 ...")
    lines.append("  python scripts/vibe_command_router.py gate --id my-wo --current-main-sha abc123")
    lines.append("")
    lines.append("  # Quality Gate & Run Report (new)")
    lines.append("  python scripts/vibe_command_router.py qg --json")
    lines.append("  python scripts/vibe_command_router.py go-no-go --compact")
    lines.append("  python scripts/vibe_command_router.py rr --json")
    lines.append("  python scripts/vibe_command_router.py handoff --compact")

    print("\n".join(lines))


def _show_version():
    """Show version."""
    print("vibe_command_router %s" % VERSION)


def _run_dashboard(args):
    """Built-in dashboard command."""
    try:
        # Find repo root
        script_dir = Path(__file__).parent
        repo_root = script_dir.parent
        dashboard_path = repo_root / "docs" / "PROJECT_DASHBOARD.md"

        # Read router version
        router_version = VERSION

        # Count scripts
        scripts_dir = script_dir
        script_count = len([f for f in scripts_dir.glob("vibe_*.py") if not f.name.startswith("__")])

        # Count smoke tests
        smoke_file = scripts_dir / "test_toolchain_smoke.py"
        smoke_count = 0
        if smoke_file.exists():
            content = smoke_file.read_text()
            smoke_count = content.count("def _test_")

        use_json = "--json" in args

        if use_json:
            output = {
                "dashboard_path": str(dashboard_path),
                "exists": dashboard_path.exists(),
                "version": router_version,
                "script_count": script_count,
                "smoke_tests": smoke_count,
                "commands": list(COMMAND_SCRIPTS.keys()),
                "aliases": len(ALIASES),
            }
            print(json.dumps(output, indent=2))
        else:
            print("Dashboard v%s" % router_version)
            print("  Dashboard file: %s" % dashboard_path)
            print("  Scripts: %d" % script_count)
            print("  Smoke tests: %d" % smoke_count)
            print("  Commands: %d" % len(COMMAND_SCRIPTS))
            print("  Aliases: %d" % len(ALIASES))

        return 0
    except Exception as e:
        print("ERROR: Dashboard failed: %s" % e, file=sys.stderr)
        return 1


def _run_preflight(args):
    """Built-in preflight command: intake → validate → package."""
    try:
        import tempfile

        if not args or args[0].startswith("--"):
            print("ERROR: preflight requires a requirement string", file=sys.stderr)
            print("Usage: preflight '<requirement>' [--json]", file=sys.stderr)
            return 1

        requirement = args[0]
        use_json = "--json" in args

        script_dir = Path(__file__).parent
        tmpdir = tempfile.mkdtemp(prefix="preflight_")

        # Step 1: intake with --json to get structured output
        intake_out = os.path.join(tmpdir, "draft.json")
        intake_cmd = [sys.executable, str(script_dir / "vibe_workorder_intake.py"),
                      requirement, "--json", "--output", intake_out]

        result = subprocess.run(intake_cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print("ERROR: intake failed: %s" % result.stderr, file=sys.stderr)
            return 1

        # Step 2: validate
        validate_cmd = [sys.executable, str(script_dir / "vibe_workorder_validator.py"),
                        intake_out]
        if use_json:
            validate_cmd.append("--json")

        result = subprocess.run(validate_cmd, capture_output=True, text=True, timeout=30)
        validate_pass = result.returncode == 0

        # Step 3: package (outputs to stdout, no --output flag)
        package_cmd = [sys.executable, str(script_dir / "vibe_workorder_packager.py"),
                       intake_out]
        if use_json:
            package_cmd.append("--json")

        result = subprocess.run(package_cmd, capture_output=True, text=True, timeout=30)
        package_ok = result.returncode == 0

        # Output
        if use_json:
            output = {
                "requirement": requirement,
                "intake": {"exit_code": 0, "draft_file": intake_out},
                "validate": {"exit_code": 0 if validate_pass else 1},
                "package": {"exit_code": 0 if package_ok else 1},
                "preflight": "PASS" if (validate_pass and package_ok) else "FAIL",
            }
            print(json.dumps(output, indent=2))
        else:
            print("Preflight Check")
            print("  Requirement: %s" % requirement[:80])
            print("  Intake: %s" % ("OK" if True else "FAIL"))
            print("  Validate: %s" % ("PASS" if validate_pass else "FAIL"))
            print("  Package: %s" % ("OK" if package_ok else "FAIL"))
            print("  Overall: %s" % ("PASS" if (validate_pass and package_ok) else "FAIL"))

        return 0 if (validate_pass and package_ok) else 1
    except Exception as e:
        print("ERROR: Preflight failed: %s" % e, file=sys.stderr)
        return 1


def main(argv=None):
    """Main entry point."""
    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        _show_help()
        return 0

    raw = argv[0]
    args = argv[1:]

    # Handle --help/-h before command resolution
    if raw in ("--help", "-h"):
        _show_help()
        return 0

    # Handle --version
    if raw == "--version":
        _show_version()
        return 0

    cmd = _resolve_command(raw)
    if cmd is None:
        return 1

    if cmd == "help":
        _show_help()
        return 0

    if cmd == "version":
        _show_version()
        return 0

    # Built-in commands
    if cmd == "dashboard":
        return _run_dashboard(args)

    if cmd == "preflight":
        return _run_preflight(args)

    # Route to script
    script_name = COMMAND_SCRIPTS.get(cmd)
    if script_name is None:
        print("ERROR: Command '%s' has no script mapping" % cmd, file=sys.stderr)
        return 1

    script_path = Path(__file__).parent / script_name
    if not script_path.exists():
        print("ERROR: Script not found: %s" % script_path, file=sys.stderr)
        return 1

    # Special handling for wo-status command (route to registry update-status)
    if cmd == "wo-status":
        # Inject 'update-status' as first argument
        args = ["update-status"] + args

    # Special handling for exec-gate command (route to check)
    if cmd == "exec-gate":
        # Inject 'check' as first argument if not already present
        if not args or args[0] != "check":
            args = ["check"] + args

    return _run_script(script_path, args)


if __name__ == "__main__":
    sys.exit(main())
