#!/usr/bin/env python3
"""WO Compiler v1.0.0 — task spec to auditable WO plan.

Usage:
    python3 scripts/vibe_wo_compiler.py --json --task-id <id> [--input task_spec.json]
    python3 scripts/vibe_wo_compiler.py self-check [--json]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

VERSION = "1.0.0"

# ── WO Templates ─────────────────────────────────────────────────────

WO_TEMPLATES = {
    "self-repo-low-risk": {
        "execution_node": "debian",
        "tools": ["git", "python3", "smoke", "qg", "freeze", "wrapper-merge"],
        "per_wo_validation": ["py_compile", "changed_paths_allowlist", "forbidden_paths"],
        "final_validation": ["smoke", "qg", "v1_freeze", "dashboard", "resume_gate"],
        "stop_conditions": ["smoke_fail", "qg_block", "freeze_fail", "dirty_worktree", "forbidden_path"],
        "resume_strategy": "clean_resume_from_current_main",
        "requires_approval": False,
    },
    "protected-external-read": {
        "execution_node": "debian",
        "tools": ["git", "python3", "curl"],
        "per_wo_validation": ["read_only_verify", "no_token_access"],
        "final_validation": ["report_schema"],
        "stop_conditions": ["write_detected", "token_access_detected"],
        "resume_strategy": "re_fetch_and_retry",
        "requires_approval": False,
    },
    "protected-external-push": {
        "execution_node": "debian",
        "tools": ["git", "python3", "ext-auth-push-wrapper", "github-api"],
        "per_wo_validation": ["parent_order", "changed_files_anomaly", "current_remote_sha"],
        "final_validation": ["smoke", "qg", "ext_push_preflight", "report_schema"],
        "stop_conditions": ["parent_order_wrong", "changed_files_anomaly", "approval_missing"],
        "resume_strategy": "manual_approval_required",
        "requires_approval": True,
    },
    "gateway-recovery": {
        "execution_node": "windows",
        "tools": ["task_scheduler", "process_check", "log_analysis"],
        "per_wo_validation": ["process_running", "log_fresh", "websocket_connected"],
        "final_validation": ["gateway_health"],
        "stop_conditions": ["session_conflict", "both_profiles_offline"],
        "resume_strategy": "restart_default_first_then_vibedev",
        "requires_approval": False,
    },
    "dependency-install": {
        "execution_node": "debian",
        "tools": ["python3", "pip", "venv"],
        "per_wo_validation": ["venv_isolation", "no_system_python"],
        "final_validation": ["test_env_manager", "report_schema"],
        "stop_conditions": ["sudo_detected", "global_pip_detected"],
        "resume_strategy": "approval_for_each_package",
        "requires_approval": True,
    },
}


def _select_template(task_spec):
    """Select WO template based on task spec."""
    risk = task_spec.get("risk_level", "low")
    scope = task_spec.get("repo_scope", "trusted-self")
    op = task_spec.get("operation_type", "planning")

    if "gateway" in task_spec.get("summary", "").lower():
        return "gateway-recovery"
    if scope == "trusted-self" and risk in ("low", "medium"):
        return "self-repo-low-risk"
    if scope == "protected-external" and op == "read-only":
        return "protected-external-read"
    if scope == "protected-external" and op in ("push", "remediation"):
        return "protected-external-push"
    if op == "install":
        return "dependency-install"
    return "self-repo-low-risk"


def compile_wo(task_spec):
    """Compile a task spec into a WO plan."""
    template_name = _select_template(task_spec)
    template = WO_TEMPLATES[template_name]

    task_id = task_spec.get("task_id", "unknown")
    wo_id = task_id.replace("task-", "wo-") if task_id.startswith("task-") else f"wo-{task_id}"

    forbidden = task_spec.get("forbidden_actions", []) + [
        "external_write_unapproved", "force_push", "sudo", "global_pip",
    ]

    plan = {
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "task_id": task_id,
        "wo_id": wo_id,
        "goal": task_spec.get("summary", ""),
        "template": template_name,
        "repo": task_spec.get("repo", SELF_REPO),
        "repo_scope": task_spec.get("repo_scope", "trusted-self"),
        "risk_level": task_spec.get("risk_level", "low"),
        "execution_node": template["execution_node"],
        "tools": template["tools"],
        "allowed_files": [],
        "forbidden_files": [".github/workflows/*", ".github/actions/*", "secrets/*", ".env"],
        "forbidden_actions": sorted(set(forbidden)),
        "per_wo_validation": template["per_wo_validation"],
        "final_validation": template["final_validation"],
        "stop_conditions": template["stop_conditions"],
        "resume_strategy": template["resume_strategy"],
        "requires_approval": task_spec.get("requires_approval", template["requires_approval"]),
        "requires_token": task_spec.get("requires_token", False),
        "validation_mode": task_spec.get("validation_mode", "auto"),
        "node_attribution": {
            "controller_node": "windows",
            "execution_node": template["execution_node"],
        },
    }
    return plan


SELF_REPO = "k176060444-lgtm/vibe-coding-repo"


def self_check(output_json=False):
    checks = []
    checks.append({"name": "version", "passed": True, "message": VERSION})

    # Self repo low-risk compilation
    spec = {"task_id": "task-test-001", "summary": "update docs", "repo": SELF_REPO,
            "repo_scope": "trusted-self", "risk_level": "low", "operation_type": "write-local",
            "requires_approval": False, "requires_token": False,
            "forbidden_actions": [], "validation_mode": "auto"}
    plan = compile_wo(spec)
    checks.append({
        "name": "self_repo_low_risk",
        "passed": plan["template"] == "self-repo-low-risk" and not plan["requires_approval"],
        "message": f"template={plan['template']} approval={plan['requires_approval']}",
    })

    # External push compilation
    spec2 = {"task_id": "task-test-002", "summary": "push conflict fix", "repo": "org/repo",
             "repo_scope": "protected-external", "risk_level": "high", "operation_type": "push",
             "requires_approval": True, "requires_token": True,
             "forbidden_actions": [], "validation_mode": "full"}
    plan2 = compile_wo(spec2)
    checks.append({
        "name": "external_push",
        "passed": plan2["template"] == "protected-external-push" and plan2["requires_approval"],
        "message": f"template={plan2['template']} approval={plan2['requires_approval']}",
    })

    # Gateway recovery
    spec3 = {"task_id": "task-test-003", "summary": "gateway recovery for QQBot", "repo": SELF_REPO,
             "repo_scope": "trusted-self", "risk_level": "medium", "operation_type": "write-local",
             "requires_approval": False, "requires_token": False,
             "forbidden_actions": [], "validation_mode": "fast"}
    plan3 = compile_wo(spec3)
    checks.append({
        "name": "gateway_recovery",
        "passed": plan3["template"] == "gateway-recovery",
        "message": f"template={plan3['template']}",
    })

    # Has node attribution
    checks.append({
        "name": "has_attribution",
        "passed": "controller_node" in plan.get("node_attribution", {}),
        "message": "present",
    })

    # Has stop conditions
    checks.append({
        "name": "has_stop_conditions",
        "passed": len(plan.get("stop_conditions", [])) >= 2,
        "message": f"count={len(plan.get('stop_conditions', []))}",
    })

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    return {"overall": "PASS" if passed == total else "FAIL", "passed": passed, "total": total, "checks": checks}


def build_parser():
    p = argparse.ArgumentParser(prog="vibe_wo_compiler")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument("--json", dest="output_json", action="store_true")
    p.add_argument("--task-id", default=None)
    p.add_argument("--input", dest="input_file", default=None)
    p.add_argument("--self-check", dest="self_check_flag", action="store_true")
    return p


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)

    if args.self_check_flag:
        result = self_check(args.output_json)
    elif args.input_file:
        with open(args.input_file) as f:
            task_spec = json.load(f)
        result = compile_wo(task_spec)
    elif args.task_id:
        # Minimal spec from task_id
        task_spec = {"task_id": args.task_id, "summary": "compiled from task_id"}
        result = compile_wo(task_spec)
    else:
        p.print_help()
        return 1

    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        if "overall" in result:
            print(f"Overall: {result['overall']} ({result['passed']}/{result['total']})")
            for c in result.get("checks", []):
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  [{icon}] {c['name']}: {c['message']}")
        else:
            print(f"WO: {result.get('wo_id')}")
            print(f"  template={result.get('template')} risk={result.get('risk_level')}")
            print(f"  node={result.get('execution_node')} approval={result.get('requires_approval')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
