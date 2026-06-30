#!/usr/bin/env python3
"""Tool Registry — catalog of VibeDev commands and workflow planner.

Records command metadata (purpose, risk, scope, token requirements)
and provides workflow-plan capability for task decomposition.

Usage:
    python3 scripts/vibe_tool_registry.py --list [--json]
    python3 scripts/vibe_tool_registry.py --plan --repo <repo> --task <desc> --operation <op> [--json]
    python3 scripts/vibe_tool_registry.py --version
"""

import argparse
import json
import sys

VERSION = "1.0.0"

# ── Tool Registry ──────────────────────────────────────────────────────

TOOLS = [
    {
        "command": "vibe_external_authorized_push.py",
        "aliases": ["ext-auth-push", "eap"],
        "purpose": "Controlled push to external repos with approval + validation",
        "read_only": False,
        "mutation": "push (external repo branch)",
        "requires_token": True,
        "requires_approval": True,
        "repo_scope": "protected-external",
        "risk_level": "high",
        "validation_mode": "full",
        "examples": [
            "eap validate --approval-id <id>",
            "eap dry-run --approval-id <id>",
            "eap push --approval-id <id>",
        ],
    },
    {
        "command": "vibe_privileged_push.py",
        "aliases": ["priv-push", "pp", "push-approved"],
        "purpose": "Controlled push with repo trust policy (baseline01: all repos require approval)",
        "read_only": False,
        "mutation": "push (self-repo branch)",
        "requires_token": True,
        "requires_approval": True,
        "repo_scope": "trusted-self / protected-external",
        "risk_level": "medium",
        "validation_mode": "full",
        "examples": [
            "priv-push --token-preflight",
            "priv-push --action-id <id> --dry-run-push",
            "priv-push --action-id <id> --push",
        ],
    },
    {
        "command": "vibe_autonomous_merge.py",
        "aliases": ["wrapper-merge"],
        "purpose": "Gate-verified PR merge via gh CLI",
        "read_only": False,
        "mutation": "merge PR (self-repo only)",
        "requires_token": True,
        "requires_approval": True,
        "repo_scope": "trusted-self",
        "risk_level": "medium",
        "validation_mode": "full",
        "examples": [
            "vibe_autonomous_merge.py --repo <r> --pr <n> --expected-base-sha <s> --expected-head-sha <s> --json --dry-run",
        ],
    },
    {
        "command": "vibe_privileged_approval.py",
        "aliases": ["priv-approval", "priv-appr"],
        "purpose": "Create/show/list/approve privileged action approvals",
        "read_only": True,
        "mutation": "approval record create/approve/expire",
        "requires_token": False,
        "requires_approval": True,
        "repo_scope": "any",
        "risk_level": "low",
        "validation_mode": "fast",
        "examples": [
            "priv-approval create --action-id <id> --repo <r> --branch <b> --action push",
            "priv-approval short-approve",
            "priv-approval list",
        ],
    },
    {
        "command": "vibe_batch_runner.py",
        "aliases": ["batch-runner", "br", "batch"],
        "purpose": "Serial execution of trusted-self Work Orders",
        "read_only": False,
        "mutation": "branch/commit/push/PR/merge (self-repo)",
        "requires_token": True,
        "requires_approval": True,
        "repo_scope": "trusted-self",
        "risk_level": "medium",
        "validation_mode": "fast / full",
        "examples": [
            "br --batch plan.json --dry-run",
            "br --status",
        ],
    },
    {
        "command": "vibe_external_test_harness.py",
        "aliases": ["ext-test", "eth"],
        "purpose": "Targeted pytest harness for external repos (read-only diagnosis)",
        "read_only": True,
        "mutation": "none",
        "requires_token": False,
        "requires_approval": True,
        "repo_scope": "any (read-only)",
        "risk_level": "low",
        "validation_mode": "fast",
        "examples": [
            "ext-test diagnose --repo-path <path>",
            "ext-test build-cmd --repo-path <path> --target <module>",
        ],
    },
    {
        "command": "vibe_node_attribution.py",
        "aliases": ["attribution", "na"],
        "purpose": "Generate per-node execution attribution reports",
        "read_only": True,
        "mutation": "none",
        "requires_token": False,
        "requires_approval": True,
        "repo_scope": "any",
        "risk_level": "none",
        "validation_mode": "fast",
        "examples": [
            "attribution --json --example",
            "attribution --format --example",
        ],
    },
    {
        "command": "vibe_tool_registry.py",
        "aliases": ["tool-registry", "tr"],
        "purpose": "Tool catalog and workflow planner",
        "read_only": True,
        "mutation": "none",
        "requires_token": False,
        "requires_approval": True,
        "repo_scope": "any",
        "risk_level": "none",
        "validation_mode": "fast",
        "examples": [
            "tr --list",
            "tr --plan --repo <r> --task <desc> --operation <op>",
        ],
    },
    {
        "command": "test_toolchain_smoke.py",
        "aliases": ["smoke"],
        "purpose": "Full toolchain smoke test suite",
        "read_only": True,
        "mutation": "none",
        "requires_token": False,
        "requires_approval": True,
        "repo_scope": "any",
        "risk_level": "none",
        "validation_mode": "fast/full",
        "examples": ["python3 scripts/test_toolchain_smoke.py --jobs-dir ~/vibedev/jobs"],
    },
    {
        "command": "vibe_quality_gate.py",
        "aliases": ["qg", "quality-gate"],
        "purpose": "Quality gate: smoke + router + audit + baseline + loop + evidence",
        "read_only": True,
        "mutation": "none",
        "requires_token": False,
        "requires_approval": True,
        "repo_scope": "any",
        "risk_level": "none",
        "validation_mode": "full",
        "examples": ["qg --jobs-dir ~/vibedev/jobs"],
    },
]


# ── Workflow Planner ───────────────────────────────────────────────────

WORKFLOW_TEMPLATES = {
    "trusted-self-low-risk-batch": {
        "repo_scope": "trusted-self",
        "recommended_workflow": "intake → branch → commit → push → PR → wrapper-merge → smoke/QG → freeze",
        "required_tools": ["vibe_batch_runner.py", "vibe_autonomous_merge.py", "test_toolchain_smoke.py", "vibe_quality_gate.py"],
        "requires_approval": True,
        "requires_token": True,
        "validation_mode": "fast",
        "stop_conditions": ["smoke_fail", "qg_fail", "v1_freeze_fail", "dirty_worktree"],
    },
    "protected-external-read-only": {
        "repo_scope": "protected-external",
        "recommended_workflow": "fetch → read-only analysis → report",
        "required_tools": ["curl", "git (read-only)", "vibe_external_test_harness.py"],
        "requires_approval": True,
        "requires_token": False,
        "validation_mode": "fast",
        "stop_conditions": ["network_error", "repo_not_found"],
    },
    "protected-external-push": {
        "repo_scope": "protected-external",
        "recommended_workflow": "scout → local-fix → approval-request → wrapper-validate → wrapper-push → remote-verify",
        "required_tools": ["vibe_external_authorized_push.py", "vibe_privileged_approval.py"],
        "requires_approval": True,
        "requires_token": True,
        "validation_mode": "full",
        "stop_conditions": ["approval_rejected", "remote_sha_mismatch", "push_403", "changed_files_anomaly"],
    },
    "remediation-force-update": {
        "repo_scope": "protected-external",
        "recommended_workflow": "diagnosis → approval → API-create-commit → force-ref-update → verify",
        "required_tools": ["vibe_external_authorized_push.py (API fallback)"],
        "requires_approval": True,
        "requires_token": True,
        "validation_mode": "full",
        "stop_conditions": ["approval_rejected", "parent_order_wrong", "remote_sha_mismatch"],
    },
    "secrets-ci-high-risk": {
        "repo_scope": "any",
        "recommended_workflow": "BLOCK — never auto-execute",
        "required_tools": [],
        "requires_approval": True,
        "requires_token": False,
        "validation_mode": "full",
        "stop_conditions": ["always_block"],
    },
}


def _classify_task(repo, operation, risk="low"):
    """Classify a task and return the matching workflow template."""
    SELF_REPO = "k176060444-lgtm/vibe-coding-repo"

    if repo == SELF_REPO and risk == "low" and operation in ("batch", "commit", "push"):
        return "trusted-self-low-risk-batch"
    if operation in ("read", "diagnose", "analyze"):
        return "protected-external-read-only"
    if operation == "push" and repo != SELF_REPO:
        return "protected-external-push"
    if operation in ("force-update", "remediation"):
        return "remediation-force-update"
    if any(kw in (operation + risk) for kw in ["secret", "ci", "workflow", "provider", "ssh"]):
        return "secrets-ci-high-risk"
    return "protected-external-read-only"


def generate_plan(repo, task, operation, risk="low"):
    """Generate a workflow plan for a given task."""
    template_name = _classify_task(repo, operation, risk)
    template = WORKFLOW_TEMPLATES.get(template_name, WORKFLOW_TEMPLATES["protected-external-read-only"])

    return {
        "repo": repo,
        "task": task,
        "operation": operation,
        "risk_level": risk,
        "workflow_template": template_name,
        "repo_scope": template["repo_scope"],
        "recommended_workflow": template["recommended_workflow"],
        "required_tools": template["required_tools"],
        "requires_approval": template["requires_approval"],
        "requires_token": template["requires_token"],
        "validation_mode": template["validation_mode"],
        "stop_conditions": template["stop_conditions"],
    }


# ── CLI ────────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(prog="vibe_tool_registry")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--json", action="store_true", dest="output_json")
    parser.add_argument("--list", action="store_true", help="List all registered tools")
    parser.add_argument("--plan", action="store_true", help="Generate workflow plan")
    parser.add_argument("--repo", help="Repository for workflow plan")
    parser.add_argument("--task", help="Task description for workflow plan")
    parser.add_argument("--operation", help="Operation type (read/push/batch/force-update)")
    parser.add_argument("--risk", default="low", help="Risk level (low/medium/high/critical)")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        if args.output_json:
            print(json.dumps(TOOLS, indent=2))
        else:
            for t in TOOLS:
                print(f"  {t['command']} ({', '.join(t['aliases'])}): {t['purpose']}")
                print(f"    scope={t['repo_scope']} risk={t['risk_level']} token={t['requires_token']}")
        return 0

    if args.plan:
        if not args.repo or not args.operation:
            print("ERROR: --repo and --operation required for --plan", file=sys.stderr)
            return 1
        plan = generate_plan(args.repo, args.task or "", args.operation, args.risk)
        if args.output_json:
            print(json.dumps(plan, indent=2))
        else:
            print(f"Workflow Plan: {plan['workflow_template']}")
            print(f"  repo_scope: {plan['repo_scope']}")
            print(f"  validation: {plan['validation_mode']}")
            print(f"  approval: {plan['requires_approval']}")
            print(f"  token: {plan['requires_token']}")
            print(f"  tools: {', '.join(plan['required_tools'])}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
