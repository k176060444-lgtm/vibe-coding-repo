#!/usr/bin/env python3
"""Trusted Self-Repo Auto-Loop Contract — standard autonomous execution loop.

Defines and validates the trusted-self repo auto-loop contract:
  intake → branch → commit → push → PR → wrapper merge →
  smoke/qg/rr/v1-freeze → freeze baseline

For trusted-self repos (k176060444-lgtm/vibe-coding-repo):
  All Work Orders require explicit human approval before execution.
  Policy gate, wrapper, smoke, QG, V1-freeze are additional gates, not substitutes.

For protected-external repos:
  Write operations require human approval via privileged action.

Usage:
    python3 scripts/vibe_trusted_self_loop.py --check [--json] [--compact]
    python3 scripts/vibe_trusted_self_loop.py --contract [--json]
    python3 scripts/vibe_trusted_self_loop.py --validate <work-order-json> [--json]

Constraints:
    - Read-only, no file modifications.
    - Standard library only, no external dependencies.
    - No IO on import.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

VERSION = "1.0.0"

# ── Repo Trust Policy ──────────────────────────────────────────────────
SELF_REPO = "k176060444-lgtm/vibe-coding-repo"
# ────────────────────────────────────────────────────────────────────────

# Auto-loop steps (in order)
AUTO_LOOP_STEPS = [
    "intake",           # Work Order intake / registry
    "branch",           # Create feature branch
    "commit",           # Commit changes
    "push",             # Push to remote
    "pr",               # Create Pull Request
    "wrapper_merge",    # Merge via autonomous wrapper
    "smoke",            # Run smoke tests
    "quality_gate",     # Run quality gate
    "run_report",       # Generate run report
    "v1_freeze",        # Verify V1 freeze
    "freeze_baseline",  # Update freeze baseline
]

# Forbidden paths (always blocked, even for trusted-self)
FORBIDDEN_PATH_PREFIXES = [
    ".github/workflows/",
    ".github/actions/",
    "secrets/",
    ".env",
    "credentials",
    "ssh/",
    ".ssh/",
]

# Forbidden actions (always blocked)
FORBIDDEN_ACTIONS = [
    "force_push", "delete_branch", "tag", "release", "deploy",
]


def _run_script(script_path, args, timeout=60):
    """Run a Python script and return (rc, stdout, stderr)."""
    try:
        cmd = [sys.executable, str(script_path)] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "timeout"
    except (OSError, FileNotFoundError) as e:
        return 1, "", str(e)


def _check_path_forbidden(path_str):
    """Check if a path matches forbidden prefixes."""
    lower = path_str.lower().replace("\\", "/")
    for prefix in FORBIDDEN_PATH_PREFIXES:
        if lower.startswith(prefix.lower()):
            return True, f"forbidden path prefix: {prefix}"
    return False, None


def _classify_repo(repo):
    """Classify repo trust level."""
    if repo == SELF_REPO:
        return "trusted-self", True  # baseline01: all repos require approval
    return "protected-external", True


def _check_policy_gate(changed_paths, action="push"):
    """Run policy gate checks on changed paths and action.

    Returns (verdict: str, blockers: list, warnings: list).
    """
    blockers = []
    warnings = []

    # Check forbidden paths
    for cp in changed_paths:
        is_forbidden, reason = _check_path_forbidden(cp)
        if is_forbidden:
            blockers.append(f"changed_path '{cp}': {reason}")

    # Check forbidden actions
    action_lower = action.lower()
    for fa in FORBIDDEN_ACTIONS:
        if fa in action_lower or action_lower in fa:
            blockers.append(f"forbidden action: {fa} in '{action}'")

    # Force push pattern
    if "--force" in action_lower or "+:" in action_lower:
        blockers.append("force push detected in action")

    verdict = "PASS" if not blockers else "BLOCK"
    return verdict, blockers, warnings


def _cmd_check(args):
    """Check current repo state against auto-loop contract."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent

    result = {
        "repo": SELF_REPO,
        "repo_trust_level": "trusted-self",
        "requires_human_approval": True,  # baseline01: all repos require approval
        "auto_loop_steps": AUTO_LOOP_STEPS,
        "checks": {},
    }

    # 1. Smoke check
    smoke_path = script_dir / "test_toolchain_smoke.py"
    if smoke_path.exists():
        rc, stdout, stderr = _run_script(smoke_path, ["--json", "--jobs-dir", os.path.expanduser("~/vibedev/jobs")])
        try:
            smoke_data = json.loads(stdout)
            result["checks"]["smoke"] = {
                "status": "PASS" if smoke_data.get("overall") == "PASS" else "FAIL",
                "passed": smoke_data.get("passed", 0),
                "failed": smoke_data.get("failed", 0),
            }
        except (json.JSONDecodeError, KeyError):
            result["checks"]["smoke"] = {"status": "ERROR", "stderr": stderr[:200]}
    else:
        result["checks"]["smoke"] = {"status": "SKIP", "reason": "script not found"}

    # 2. Quality gate
    qg_path = script_dir / "vibe_quality_gate.py"
    if qg_path.exists():
        rc, stdout, stderr = _run_script(qg_path, ["--json", "--skip-smoke", "--repo-root", str(repo_root)])
        try:
            qg_data = json.loads(stdout)
            result["checks"]["quality_gate"] = {
                "status": qg_data.get("verdict", "UNKNOWN"),
            }
        except (json.JSONDecodeError, KeyError):
            result["checks"]["quality_gate"] = {"status": "ERROR", "stderr": stderr[:200]}
    else:
        result["checks"]["quality_gate"] = {"status": "SKIP", "reason": "script not found"}

    # 3. V1 freeze
    v1_path = script_dir / "vibe_v1_freeze_check.py"
    if v1_path.exists():
        rc, stdout, stderr = _run_script(v1_path, ["--json", "--repo-root", str(repo_root)])
        try:
            v1_data = json.loads(stdout)
            result["checks"]["v1_freeze"] = {
                "status": v1_data.get("verdict", "UNKNOWN"),
            }
        except (json.JSONDecodeError, KeyError):
            result["checks"]["v1_freeze"] = {"status": "ERROR", "stderr": stderr[:200]}
    else:
        result["checks"]["v1_freeze"] = {"status": "SKIP", "reason": "script not found"}

    # 4. Run report
    rr_path = script_dir / "vibe_run_report.py"
    if rr_path.exists():
        rc, stdout, stderr = _run_script(rr_path, ["--compact", "--repo-root", str(repo_root)])
        result["checks"]["run_report"] = {
            "status": "PASS" if rc == 0 else "WARN",
            "summary": stdout.strip()[:200],
        }
    else:
        result["checks"]["run_report"] = {"status": "SKIP", "reason": "script not found"}

    # 5. Policy gate (no specific changed_paths — general check)
    result["checks"]["policy_gate"] = {
        "status": "PASS",
        "forbidden_paths": FORBIDDEN_PATH_PREFIXES,
        "forbidden_actions": FORBIDDEN_ACTIONS,
    }

    # 6. Wrapper availability
    wrapper_path = script_dir / "vibe_autonomous_merge.py"
    result["checks"]["wrapper"] = {
        "status": "PASS" if wrapper_path.exists() else "FAIL",
    }

    # Overall verdict
    statuses = [c.get("status") for c in result["checks"].values()]
    if all(s == "PASS" for s in statuses):
        result["policy_verdict"] = "PASS"
    elif any(s == "FAIL" or s == "BLOCK" for s in statuses):
        result["policy_verdict"] = "BLOCK"
    else:
        result["policy_verdict"] = "WARN"

    return result, 0 if result["policy_verdict"] == "PASS" else 1


def _cmd_contract(args):
    """Output the auto-loop contract specification."""
    contract = {
        "name": "trusted-self-auto-loop",
        "version": VERSION,
        "repo": SELF_REPO,
        "repo_trust_level": "trusted-self",
        "requires_human_approval": True,  # baseline01: all repos require approval
        "auto_loop_steps": AUTO_LOOP_STEPS,
        "policy_gate": {
            "forbidden_paths": FORBIDDEN_PATH_PREFIXES,
            "forbidden_actions": FORBIDDEN_ACTIONS,
            "no_force_push": True,
            "no_pr_merge": True,
            "no_secrets_ci_workflow_provider_ssh": True,
        },
        "merge_method": "merge_commit",
        "wrapper_required": True,
        "post_merge_checks": ["smoke", "quality_gate", "run_report", "v1_freeze"],
        "protected_external_rules": {
            "repo_trust_level": "protected-external",
            "requires_human_approval": True,
            "write_operations_require_approval": True,
            "read_only_operations_allowed": ["fetch", "diff", "merge_dry_run", "patch_generate"],
        },
    }
    return contract, 0


def _cmd_validate(args):
    """Validate a work-order against the auto-loop contract."""
    wo_path = args.work_order
    if not wo_path or not Path(wo_path).exists():
        return {"error": f"Work order not found: {wo_path}"}, 1

    try:
        with open(wo_path, "r", encoding="utf-8") as f:
            wo = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return {"error": f"Failed to load work order: {e}"}, 1

    repo = wo.get("repo", "")
    trust_level, requires_approval = _classify_repo(repo)
    changed_paths = wo.get("changed_paths", [])
    action = wo.get("action", "push")

    policy_verdict, blockers, warnings = _check_policy_gate(changed_paths, action)

    result = {
        "repo": repo,
        "repo_trust_level": trust_level,
        "requires_human_approval": requires_approval,
        "policy_verdict": policy_verdict,
        "branch": wo.get("branch", ""),
        "changed_paths": changed_paths,
        "blockers": blockers,
        "warnings": warnings,
    }

    # For external repos, check if approved
    if requires_approval:
        status = wo.get("status", "")
        if status != "approved":
            result["policy_verdict"] = "BLOCK"
            result["blockers"].append(f"external repo requires approval (status={status})")

    return result, 0 if result["policy_verdict"] == "PASS" else 1


def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        prog="vibe_trusted_self_loop",
        description="Trusted Self-Repo Auto-Loop Contract",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--json", action="store_true", dest="output_json", help="JSON output")
    parser.add_argument("--compact", action="store_true", help="Compact output")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Check current repo state")
    group.add_argument("--contract", action="store_true", help="Output contract specification")
    group.add_argument("--validate", metavar="WORK_ORDER", help="Validate a work-order file")

    return parser


def _format_compact(result):
    """Format result as compact single-line string."""
    if "error" in result:
        return f"LOOP ERROR | {result['error']}"
    verdict = result.get("policy_verdict", "UNKNOWN")
    trust = result.get("repo_trust_level", "?")
    checks = result.get("checks", {})
    check_summary = " ".join(f"{k}:{v.get('status', '?')}" for k, v in checks.items())
    return f"LOOP {verdict} | trust={trust} | {check_summary}"


def main(argv=None):
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.check:
        result, rc = _cmd_check(args)
    elif args.contract:
        result, rc = _cmd_contract(args)
    elif args.validate:
        result, rc = _cmd_validate(args)
    else:
        parser.print_help()
        return 1

    if args.output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.compact:
        print(_format_compact(result))
    else:
        if "error" in result:
            print(f"ERROR: {result['error']}", file=sys.stderr)
        else:
            print(json.dumps(result, indent=2, ensure_ascii=False))

    return rc


if __name__ == "__main__":
    sys.exit(main())
