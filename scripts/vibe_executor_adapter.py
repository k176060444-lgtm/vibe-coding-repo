#!/usr/bin/env python3
"""Executor Adapter Contract — define and query executor adapter capabilities.

Exposes a structured contract for executor adapters (noop, dry-run) that
describe what they can and cannot do. This is a READ-ONLY contract definition;
adapters never execute real work, call models, write repos, push, or merge.

Usage:
    python3 scripts/vibe_executor_adapter.py capabilities
    python3 scripts/vibe_executor_adapter.py capabilities --adapter noop
    python3 scripts/vibe_executor_adapter.py capabilities --adapter dry-run
    python3 scripts/vibe_executor_adapter.py capabilities --json
    python3 scripts/vibe_executor_adapter.py plan --adapter noop --id my-wo --base-sha abc123
    python3 scripts/vibe_executor_adapter.py plan --adapter dry-run --id my-wo --base-sha abc123 --json
    python3 scripts/vibe_executor_adapter.py validate-inputs --adapter noop --id my-wo --base-sha abc123 --gate-verdict ALLOW
"""

import argparse
import json
import sys
from datetime import datetime, timezone

VERSION = "1.0.0"

# ---------- Adapter Registry ----------

ADAPTERS = {
    "noop": {
        "adapter_name": "noop",
        "description": "No-operation adapter. Produces a plan that does nothing. For testing and dry-run validation.",
        "modes": ["noop"],
        "accepted_inputs": {
            "workorder_id": "required",
            "base_sha": "required",
            "gate_verdict": "required (must be ALLOW)",
        },
        "refused_actions": [
            "model_call",
            "shell_exec",
            "repo_write",
            "git_push",
            "git_merge",
            "deploy",
            "tag",
            "file_delete",
        ],
        "required_approval": False,
        "execution_plan": {
            "steps": [
                {"step": 1, "action": "noop", "description": "Do nothing"},
            ],
            "total_steps": 1,
            "estimated_duration": "0s",
            "reversible": True,
        },
        "evidence_expectations": {
            "transcript_created": True,
            "evidence_bundle": False,
            "gate_verdict": "ALLOW",
            "approval_receipt": "optional",
        },
    },
    "dry-run": {
        "adapter_name": "dry-run",
        "description": "Dry-run adapter. Simulates a full execution without side effects.",
        "modes": ["dry-run"],
        "accepted_inputs": {
            "workorder_id": "required",
            "base_sha": "required",
            "gate_verdict": "required (must be ALLOW)",
            "changed_paths": "optional (for path validation)",
            "transcript_dir": "optional",
        },
        "refused_actions": [
            "model_call",
            "shell_exec",
            "repo_write",
            "git_push",
            "git_merge",
            "deploy",
            "tag",
            "file_delete",
        ],
        "required_approval": False,
        "execution_plan": {
            "steps": [
                {"step": 1, "action": "validate-gate", "description": "Verify gate verdict is ALLOW"},
                {"step": 2, "action": "validate-inputs", "description": "Check required fields present"},
                {"step": 3, "action": "simulate-worktree", "description": "Simulate worktree creation (no FS change)"},
                {"step": 4, "action": "simulate-implementation", "description": "Simulate code changes (no FS change)"},
                {"step": 5, "action": "simulate-commit", "description": "Simulate commit (no git change)"},
                {"step": 6, "action": "simulate-pr", "description": "Simulate PR creation (no GitHub API)"},
                {"step": 7, "action": "simulate-merge", "description": "Simulate merge (no git change)"},
                {"step": 8, "action": "write-transcript", "description": "Write dry-run transcript to transcript-dir"},
            ],
            "total_steps": 8,
            "estimated_duration": "<1s",
            "reversible": True,
        },
        "evidence_expectations": {
            "transcript_created": True,
            "evidence_bundle": False,
            "gate_verdict": "ALLOW",
            "approval_receipt": "recommended",
        },
    },
}

FORBIDDEN_ACTIONS = sorted({
    action
    for adapter in ADAPTERS.values()
    for action in adapter["refused_actions"]
})

# ---------- CLI Handlers ----------

def cmd_capabilities(args):
    """Show adapter capabilities."""
    adapter_name = getattr(args, "adapter", None)
    as_json = getattr(args, "json_output", False)

    if adapter_name:
        if adapter_name not in ADAPTERS:
            print(f"ERROR: Unknown adapter '{adapter_name}'. Available: {', '.join(sorted(ADAPTERS))}", file=sys.stderr)
            return 1
        result = ADAPTERS[adapter_name]
    else:
        result = {
            "version": VERSION,
            "adapters": {name: ad for name, ad in ADAPTERS.items()},
            "forbidden_actions": FORBIDDEN_ACTIONS,
            "policy": "No adapter may call models, execute shell, write repos, push, merge, deploy, tag, or delete files.",
        }

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_capabilities(result)
    return 0


def cmd_plan(args):
    """Generate an execution plan for the given adapter."""
    adapter_name = args.adapter
    workorder_id = args.id
    base_sha = args.base_sha
    as_json = getattr(args, "json_output", False)

    if adapter_name not in ADAPTERS:
        print(f"ERROR: Unknown adapter '{adapter_name}'. Available: {', '.join(sorted(ADAPTERS))}", file=sys.stderr)
        return 1

    adapter = ADAPTERS[adapter_name]
    now = datetime.now(timezone.utc).isoformat()

    plan = {
        "adapter_name": adapter_name,
        "mode": adapter["modes"][0],
        "workorder_id": workorder_id,
        "base_sha": base_sha,
        "timestamp": now,
        "accepted_inputs": adapter["accepted_inputs"],
        "refused_actions": adapter["refused_actions"],
        "required_approval": adapter["required_approval"],
        "execution_plan": adapter["execution_plan"],
        "evidence_expectations": adapter["evidence_expectations"],
        "policy": "This adapter will NOT perform any real execution.",
    }

    if as_json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        _print_plan(plan)
    return 0


def cmd_validate_inputs(args):
    """Validate inputs for the given adapter."""
    adapter_name = args.adapter
    workorder_id = args.id
    base_sha = args.base_sha
    gate_verdict = getattr(args, "gate_verdict", None)
    as_json = getattr(args, "json_output", False)

    if adapter_name not in ADAPTERS:
        print(f"ERROR: Unknown adapter '{adapter_name}'. Available: {', '.join(sorted(ADAPTERS))}", file=sys.stderr)
        return 1

    adapter = ADAPTERS[adapter_name]
    errors = []
    warnings = []

    if not workorder_id:
        errors.append("workorder_id is required")
    if not base_sha:
        errors.append("base_sha is required")
    if gate_verdict and gate_verdict != "ALLOW":
        errors.append(f"gate_verdict must be ALLOW, got '{gate_verdict}'")
    elif not gate_verdict:
        warnings.append("gate_verdict not provided; assuming ALLOW for dry-run")

    result = {
        "adapter_name": adapter_name,
        "workorder_id": workorder_id or "",
        "base_sha": base_sha or "",
        "gate_verdict": gate_verdict or "ALLOW (assumed)",
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_validation(result)
    return 0 if result["valid"] else 1


# ---------- Pretty Printers ----------

def _print_capabilities(data):
    if "adapters" in data:
        print(f"Executor Adapter Contract v{data['version']}")
        print(f"Policy: {data['policy']}")
        print(f"Forbidden actions: {', '.join(data['forbidden_actions'])}")
        print()
        for name, ad in data["adapters"].items():
            print(f"  [{name}] {ad['description']}")
            print(f"    Modes: {', '.join(ad['modes'])}")
            print(f"    Required approval: {ad['required_approval']}")
            print(f"    Refused: {', '.join(ad['refused_actions'][:5])}...")
            print()
    else:
        print(f"Adapter: {data['adapter_name']}")
        print(f"Description: {data['description']}")
        print(f"Modes: {', '.join(data['modes'])}")
        print(f"Required approval: {data['required_approval']}")
        print(f"Refused actions: {', '.join(data['refused_actions'])}")


def _print_plan(plan):
    print(f"Execution Plan: {plan['adapter_name']} ({plan['mode']})")
    print(f"Workorder: {plan['workorder_id']}")
    print(f"Base SHA: {plan['base_sha']}")
    print(f"Policy: {plan['policy']}")
    print()
    for step in plan["execution_plan"]["steps"]:
        print(f"  Step {step['step']}: [{step['action']}] {step['description']}")


def _print_validation(result):
    status = "VALID" if result["valid"] else "INVALID"
    print(f"Validation [{result['adapter_name']}]: {status}")
    print(f"Workorder: {result['workorder_id']}")
    print(f"Base SHA: {result['base_sha']}")
    print(f"Gate: {result['gate_verdict']}")
    for e in result["errors"]:
        print(f"  ERROR: {e}")
    for w in result["warnings"]:
        print(f"  WARN: {w}")


# ---------- CLI Parser ----------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_executor_adapter",
        description="Executor Adapter Contract — query and validate executor adapter capabilities.",
    )
    parser.add_argument("--version", action="version", version=f"v{VERSION}")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output JSON")

    sub = parser.add_subparsers(dest="command")

    # capabilities
    cap = sub.add_parser("capabilities", aliases=["cap", "list"], help="List adapter capabilities")
    cap.add_argument("--adapter", help="Show specific adapter (noop, dry-run)")
    cap.add_argument("--json", dest="json_output", action="store_true")

    # plan
    plan = sub.add_parser("plan", aliases=["p"], help="Generate execution plan")
    plan.add_argument("--adapter", required=True, choices=["noop", "dry-run"], help="Adapter name")
    plan.add_argument("--id", required=True, help="Workorder ID")
    plan.add_argument("--base-sha", required=True, help="Base commit SHA")
    plan.add_argument("--json", dest="json_output", action="store_true")

    # validate-inputs
    vi = sub.add_parser("validate-inputs", aliases=["vi", "validate"], help="Validate adapter inputs")
    vi.add_argument("--adapter", required=True, choices=["noop", "dry-run"], help="Adapter name")
    vi.add_argument("--id", required=True, help="Workorder ID")
    vi.add_argument("--base-sha", required=True, help="Base commit SHA")
    vi.add_argument("--gate-verdict", help="Gate verdict (default: ALLOW)")
    vi.add_argument("--json", dest="json_output", action="store_true")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    handler = {
        "capabilities": cmd_capabilities,
        "cap": cmd_capabilities,
        "list": cmd_capabilities,
        "plan": cmd_plan,
        "p": cmd_plan,
        "validate-inputs": cmd_validate_inputs,
        "vi": cmd_validate_inputs,
        "validate": cmd_validate_inputs,
    }.get(args.command)
    if handler:
        return handler(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
