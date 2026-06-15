#!/usr/bin/env python3
"""Executor Unfreeze Checklist — machine-readable unfreeze readiness check.

Generates checklist for each unfreeze level (1-4). Outputs required_approvals,
required_green_checks, forbidden_actions, evidence_required, rollback_required,
go_no_go. Read-only; does NOT unfreeze executor.

Usage:
    python3 scripts/vibe_executor_unfreeze_checklist.py --level 1
    python3 scripts/vibe_executor_unfreeze_checklist.py --level 1 --json
    python3 scripts/vibe_executor_unfreeze_checklist.py --level 2 --compact
    python3 scripts/vibe_executor_unfreeze_checklist.py --level 3 --json
"""

import argparse
import json
import sys
from datetime import datetime, timezone

VERSION = "1.0.0"

# ---------- Level Definitions ----------

LEVELS = {
    1: {
        "name": "Fixture-Only Local Write",
        "description": "Write a single fixture file to temporary fixture worktree. No push, no PR.",
        "required_approvals": [
            "Human explicitly approves Level 1 activation",
            "Fixture workorder approved by human",
        ],
        "required_green_checks": [
            "sandbox_check_PASS",
            "gate_check_ALLOW",
            "approval_receipt_exists",
            "registry_status_approved",
            "smoke_suite_PASS",
            "no_active_audit_violations",
            "wo-code-repo-status-001_audit_tainted",
            "recovery_plan_exists",
            "cancel_token_generated",
        ],
        "forbidden_actions": [
            "git_push",
            "git_merge",
            "deploy",
            "tag",
            "file_delete",
            "model_call",
            "shell_exec",
            "production_file_modification",
        ],
        "evidence_required": [
            "fixture_file_created",
            "fixture_file_hash",
            "transcript_created",
            "evidence_bundle",
            "verifier_PASS",
        ],
        "rollback_required": True,
        "rollback_steps": [
            "Delete fixture worktree",
            "Delete fixture workorder from registry",
            "Delete fixture evidence/transcript",
            "Verify no production files modified",
        ],
        "stop_conditions": [
            "sandbox_check_FAIL",
            "gate_check_BLOCK",
            "evidence_verifier_FAIL",
            "production_file_in_changed_paths",
            "push_attempt_detected",
            "model_call_detected",
            "shell_exec_detected",
        ],
    },
    2: {
        "name": "Fixture Branch Push",
        "description": "Push fixture branch to remote. No PR, no merge to main.",
        "required_approvals": [
            "All Level 1 approvals",
            "Human explicitly approves Level 2 activation",
            "Fixture branch name approved",
            "Remote push target verified",
        ],
        "required_green_checks": [
            "all_level_1_checks_GREEN",
            "level_1_completed_successfully",
            "fixture_branch_specified",
            "remote_push_target_verified",
            "branch_protection_verified",
        ],
        "forbidden_actions": [
            "git_merge_to_main",
            "deploy",
            "tag",
            "file_delete",
            "model_call",
            "shell_exec",
            "pr_creation",
            "production_branch_modification",
        ],
        "evidence_required": [
            "all_level_1_evidence",
            "push_confirmation",
            "remote_branch_existence",
        ],
        "rollback_required": True,
        "rollback_steps": [
            "Delete remote fixture branch",
            "Delete local fixture branch",
            "All Level 1 rollback steps",
            "Verify no production branches modified",
        ],
        "stop_conditions": [
            "all_level_1_stop_conditions",
            "push_to_main_detected",
            "push_to_production_branch_detected",
            "pr_creation_detected",
        ],
    },
    3: {
        "name": "Low-Risk Docs/Code PR via Wrapper",
        "description": "Create and merge PR for low-risk changes via autonomous merge wrapper.",
        "required_approvals": [
            "All Level 2 approvals",
            "Human explicitly approves Level 3 activation",
            "Changed paths approved by human",
            "PR template approved",
        ],
        "required_green_checks": [
            "all_level_2_checks_GREEN",
            "level_2_completed_successfully",
            "changed_paths_in_allowed_scope",
            "wrapper_dry_run_PASS",
            "merge_method_merge_commit",
        ],
        "forbidden_actions": [
            "deploy",
            "tag",
            "file_delete_outside_scope",
            "model_call",
            "shell_exec",
            "direct_gh_pr_merge",
            "squash_or_rebase_merge",
            "secrets_ci_provider_ssh_changes",
        ],
        "evidence_required": [
            "all_level_2_evidence",
            "pr_url_and_number",
            "wrapper_merge_confirmation",
            "post_merge_main_sha",
            "smoke_suite_PASS_after_merge",
        ],
        "rollback_required": True,
        "rollback_steps": [
            "Close PR if not merged",
            "Revert merge commit if merged",
            "Delete feature branch",
            "All Level 2 rollback steps",
            "Verify main is clean",
        ],
        "stop_conditions": [
            "all_level_2_stop_conditions",
            "wrapper_merge_BLOCK",
            "changed_paths_outside_scope",
            "high_risk_file_modification",
            "smoke_suite_FAIL_after_merge",
        ],
    },
    4: {
        "name": "Broader Autonomous Execution",
        "description": "Full autonomous loop: model calls, shell execution, broader file mods.",
        "required_approvals": [
            "All Level 3 approvals",
            "Human explicitly approves Level 4 activation",
            "Model provider credentials validated",
            "Test infrastructure validated",
            "Rollback procedures tested",
            "Monitoring configured",
            "Human override tested",
        ],
        "required_green_checks": [
            "all_level_3_checks_GREEN",
            "level_3_completed_3_PRs",
            "model_provider_validated",
            "test_infrastructure_operational",
            "rollback_procedures_tested",
            "monitoring_configured",
            "human_override_tested",
        ],
        "forbidden_actions": [
            "deploy_to_production_without_approval",
            "tag_releases_without_approval",
            "secrets_changes_without_approval",
            "ci_provider_ssh_changes_without_approval",
        ],
        "evidence_required": [
            "all_level_3_evidence",
            "model_call_logs",
            "shell_execution_logs",
            "test_results",
            "code_quality_metrics",
        ],
        "rollback_required": True,
        "rollback_steps": [
            "Cancel in-progress execution",
            "Revert all changes since last checkpoint",
            "All Level 3 rollback steps",
            "Verify repository integrity",
        ],
        "stop_conditions": [
            "all_level_3_stop_conditions",
            "model_provider_unavailable",
            "test_infrastructure_failure",
            "rollback_procedure_failure",
            "human_override_requested",
        ],
    },
}


# ---------- CLI Handlers ----------

def cmd_checklist(args):
    """Generate unfreeze checklist for a level."""
    as_json = getattr(args, "json_output", False)
    compact = getattr(args, "compact", False)
    level = args.level
    now = datetime.now(timezone.utc).isoformat()

    if level not in LEVELS:
        print(f"ERROR: Invalid level {level}. Valid: {sorted(LEVELS.keys())}", file=sys.stderr)
        return 1

    level_def = LEVELS[level]
    checklist = {
        "level": level,
        "name": level_def["name"],
        "description": level_def["description"],
        "timestamp": now,
        "checklist_version": VERSION,
        "required_approvals": level_def["required_approvals"],
        "required_green_checks": level_def["required_green_checks"],
        "forbidden_actions": level_def["forbidden_actions"],
        "evidence_required": level_def["evidence_required"],
        "rollback_required": level_def["rollback_required"],
        "rollback_steps": level_def["rollback_steps"],
        "stop_conditions": level_def["stop_conditions"],
        "go_no_go": "NO_GO — requires human approval and all checks GREEN",
        "current_status": {
            "level": 0,
            "name": "noop/dry-run (frozen)",
            "activated": False,
        },
    }

    if as_json:
        print(json.dumps(checklist, indent=2, ensure_ascii=False))
    else:
        _print_checklist(checklist, compact)
    return 0


def _print_checklist(checklist, compact):
    """Print human-readable checklist."""
    level = checklist["level"]
    print(f"Unfreeze Checklist: Level {level} — {checklist['name']}")
    print(f"  {checklist['description']}")
    print(f"  Go/No-Go: {checklist['go_no_go']}")
    print()

    if compact:
        print(f"  Approvals: {len(checklist['required_approvals'])}")
        print(f"  Green checks: {len(checklist['required_green_checks'])}")
        print(f"  Forbidden: {len(checklist['forbidden_actions'])}")
        print(f"  Evidence: {len(checklist['evidence_required'])}")
        print(f"  Rollback: {'YES' if checklist['rollback_required'] else 'NO'}")
        print(f"  Stop conditions: {len(checklist['stop_conditions'])}")
    else:
        print("  Required Approvals:")
        for a in checklist["required_approvals"]:
            print(f"    [ ] {a}")
        print()
        print("  Required Green Checks:")
        for c in checklist["required_green_checks"]:
            print(f"    [ ] {c}")
        print()
        print("  Forbidden Actions:")
        for f in checklist["forbidden_actions"]:
            print(f"    [X] {f}")
        print()
        print("  Evidence Required:")
        for e in checklist["evidence_required"]:
            print(f"    [ ] {e}")
        print()
        print("  Rollback Steps:")
        for i, s in enumerate(checklist["rollback_steps"], 1):
            print(f"    {i}. {s}")
        print()
        print("  Stop Conditions:")
        for s in checklist["stop_conditions"]:
            print(f"    [!] {s}")


# ---------- CLI Parser ----------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_executor_unfreeze_checklist",
        description="Executor Unfreeze Checklist — machine-readable unfreeze readiness check.",
    )
    parser.add_argument("--version", action="version", version=f"v{VERSION}")
    parser.add_argument("--level", type=int, required=True, choices=[1, 2, 3, 4],
                        help="Unfreeze level (1-4)")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output JSON")
    parser.add_argument("--compact", action="store_true", help="Compact output")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return cmd_checklist(args)


if __name__ == "__main__":
    sys.exit(main())
