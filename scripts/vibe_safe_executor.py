#!/usr/bin/env python3
"""Safe Executor Stub — generate execution plans from ALLOW gate results.

Only accepts execution gate ALLOW results and generates execution plans or
dry-run reports. Does NOT execute coding agents, call models, push, merge,
or deploy.

Usage:
    python3 scripts/vibe_safe_executor.py plan --registry-dir /path --id my-wo --current-main-sha abc123
    python3 scripts/vibe_safe_executor.py plan --registry-dir /path --id my-wo --current-main-sha abc123 --json
    python3 scripts/vibe_safe_executor.py plan --registry-dir /path --id my-wo --current-main-sha abc123 --plan-only
    python3 scripts/vibe_safe_executor.py plan --registry-dir /path --id my-wo --current-main-sha abc123 --dry-run
"""

import argparse
import json
import os
import subprocess
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

def _run_gate_check(gate_script, registry_dir, workorder_id, current_main_sha):
    """Run execution gate check and return result."""
    try:
        cmd = [sys.executable, str(gate_script), "check",
               "--registry-dir", str(registry_dir),
               "--id", workorder_id,
               "--current-main-sha", current_main_sha,
               "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.stdout:
            return json.loads(result.stdout)
        return {"verdict": "BLOCK", "errors": [result.stderr or "Gate check failed"]}
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError) as e:
        return {"verdict": "BLOCK", "errors": [str(e)]}

def cmd_plan(args):
    """Generate an execution plan."""
    registry_dir = _registry_dir_path(args)
    if not registry_dir:
        print("ERROR: --registry-dir or VIBEDEV_REGISTRY_DIR required", file=sys.stderr)
        return 1

    workorder_id = args.id
    if not workorder_id:
        print("ERROR: --id required", file=sys.stderr)
        return 1

    current_main_sha = args.current_main_sha
    if not current_main_sha:
        print("ERROR: --current-main-sha required", file=sys.stderr)
        return 1

    use_json = getattr(args, 'json', False)
    plan_only = getattr(args, 'plan_only', False)
    dry_run = getattr(args, 'dry_run', False)

    # Load registry entry
    entry = _load_entry(registry_dir, workorder_id)
    if not entry:
        result = {"status": "BLOCKED", "errors": [f"Registry entry '{workorder_id}' not found"]}
        if use_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"BLOCKED: Registry entry '{workorder_id}' not found")
        return 1

    # Run gate check
    script_dir = Path(__file__).parent
    gate_script = script_dir / "vibe_execution_gate.py"
    gate_result = _run_gate_check(gate_script, registry_dir, workorder_id, current_main_sha)

    gate_verdict = gate_result.get("verdict", "BLOCK")

    if gate_verdict != "ALLOW":
        result = {
            "status": "BLOCKED",
            "workorder_id": workorder_id,
            "gate_verdict": gate_verdict,
            "reason": f"Gate returned {gate_verdict}, not ALLOW",
            "gate_result": gate_result,
        }
        if use_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"BLOCKED: Gate returned {gate_verdict}")
            if gate_result.get("errors"):
                for e in gate_result["errors"]:
                    print(f"  - {e}")
        return 1

    # Generate execution plan
    now = datetime.now(timezone.utc).isoformat()
    risk_level = entry.get("risk_level", "low")
    requires_human = entry.get("requires_human_approval", False)
    changed_paths = entry.get("changed_paths", [])
    forbidden_actions = entry.get("forbidden_actions", [])
    stop_conditions = entry.get("stop_conditions", [])
    allowed_paths = entry.get("allowed_paths", [])

    execution_plan = {
        "workorder_id": workorder_id,
        "title": entry.get("title", workorder_id),
        "risk_level": risk_level,
        "requires_human_approval": requires_human,
        "base_sha": entry.get("base_sha", current_main_sha),
        "target_branch": f"vibedev/{workorder_id}",
        "allowed_paths": allowed_paths,
        "forbidden_actions": forbidden_actions,
        "changed_paths": changed_paths,
        "stop_conditions": stop_conditions,
        "phases": [
            {"phase": "prepare", "action": "create worktree from base_sha", "status": "planned"},
            {"phase": "implement", "action": "execute coding agent (not by this stub)", "status": "planned"},
            {"phase": "test", "action": "run py_compile, smoke suite", "status": "planned"},
            {"phase": "commit", "action": "git add + commit allowed paths", "status": "planned"},
            {"phase": "push", "action": "push to target branch", "status": "planned"},
            {"phase": "pr", "action": "create pull request", "status": "planned"},
            {"phase": "review", "action": "independent code review", "status": "planned"},
            {"phase": "merge", "action": "autonomous merge wrapper", "status": "planned"},
            {"phase": "freeze", "action": "post-merge freeze + smoke", "status": "planned"},
        ],
        "required_inputs": [
            "implementer_model (for coding agent)",
            "reviewer_model (for code review)",
            "base_sha (current main SHA)",
        ],
        "blocked_if": [
            "Gate verdict is not ALLOW",
            "origin/main SHA changes during execution",
            "Changed paths exceed allowed scope",
            "py_compile fails",
            "Smoke suite regression",
            "Wrapper gate returns allow_merge=false",
            "audit_tainted lock status changes",
        ],
        "evidence_expectations": {
            "result_sha": "Git SHA after commit",
            "post_merge_sha": "Git SHA after merge",
            "pr_url": "Pull request URL",
            "pr_number": "Pull request number",
            "smoke_result": "Smoke suite result (e.g., 44/44 PASS)",
            "job_status": "Job status (e.g., review_passed)",
            "audit_status": "Audit status (e.g., clean)",
        },
        "generated_at": now,
        "gate_verdict": gate_verdict,
        "gate_checks": gate_result.get("summary", {}),
    }

    if plan_only:
        # Only output the plan, no further processing
        pass

    result = {
        "status": "READY",
        "workorder_id": workorder_id,
        "execution_plan": execution_plan,
        "gate_result": gate_result,
        "dry_run": dry_run,
        "plan_only": plan_only,
    }

    if use_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Execution Plan: {workorder_id}")
        print(f"  Status: READY")
        print(f"  Gate: {gate_verdict}")
        print(f"  Risk: {risk_level}")
        print(f"  Human Approval: {requires_human}")
        print(f"  Phases: {len(execution_plan['phases'])}")
        print(f"  Allowed Paths: {', '.join(allowed_paths)}")
        print(f"  Stop Conditions: {len(stop_conditions)}")
        print(f"  Blocked If: {len(execution_plan['blocked_if'])} conditions")
        if dry_run:
            print(f"  [DRY RUN] No execution will occur")
        if plan_only:
            print(f"  [PLAN ONLY] No execution will occur")

    return 0

def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Safe Executor Stub — generate execution plans from ALLOW gate results",
        epilog="This stub does NOT execute coding agents, call models, push, merge, or deploy."
    )
    parser.add_argument("--version", action="version", version=f"vibe_safe_executor {VERSION}")

    sub = parser.add_subparsers(dest="command")

    # plan
    pl = sub.add_parser("plan", help="Generate execution plan")
    pl.add_argument("--id", required=True, help="Work order ID")
    pl.add_argument("--current-main-sha", required=True, help="Current origin/main SHA")
    pl.add_argument("--registry-dir", help="Registry directory")
    pl.add_argument("--json", action="store_true", help="Output as JSON")
    pl.add_argument("--dry-run", action="store_true", help="Dry run mode (no execution)")
    pl.add_argument("--plan-only", action="store_true", help="Plan only (no execution)")

    return parser

def main(argv=None):
    """Main entry point (import-safe)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "plan":
        return cmd_plan(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())
