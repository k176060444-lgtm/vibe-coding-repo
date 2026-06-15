#!/usr/bin/env python3
"""Executor Recovery Plan — failure recovery/rollback plan generator.

Generates recovery plans for executor failures. Covers: model_error, timeout,
dirty_worktree, gate_blocked, wrapper_blocked, test_failed, partial_artifacts,
evidence_mismatch. Only generates plans; does NOT execute reset/clean/rm/push/delete.

Usage:
    python3 scripts/vibe_executor_recovery.py plan --id my-wo --failure-type model_error
    python3 scripts/vibe_executor_recovery.py plan --id my-wo --failure-type timeout --json
    python3 scripts/vibe_executor_recovery.py classify-failure --id my-wo --error-msg "quota exceeded"
    python3 scripts/vibe_executor_recovery.py classify-failure --id my-wo --error-msg "timeout after 300s" --json
"""

import argparse
import json
import sys
from datetime import datetime, timezone

VERSION = "1.0.0"

# ---------- Failure Types ----------

FAILURE_TYPES = {
    "model_error": {
        "description": "Model API call failed (quota, rate limit, auth, provider down)",
        "severity": "high",
        "reversible": True,
        "recovery_strategy": "switch_model_or_abort",
        "worktree_policy": "keep_for_inspection",
        "retry_allowed": True,
        "retry_conditions": ["different_model", "quota_refresh", "provider_recovery"],
    },
    "timeout": {
        "description": "Execution exceeded maximum allowed time",
        "severity": "medium",
        "reversible": True,
        "recovery_strategy": "cancel_and_log",
        "worktree_policy": "keep_for_inspection",
        "retry_allowed": True,
        "retry_conditions": ["increased_timeout", "simplified_scope"],
    },
    "dirty_worktree": {
        "description": "Worktree has uncommitted changes from failed execution",
        "severity": "medium",
        "reversible": True,
        "recovery_strategy": "inspect_and_decide",
        "worktree_policy": "inspect_changes",
        "retry_allowed": True,
        "retry_conditions": ["commit_partial", "reset_to_base", "user_decision"],
    },
    "gate_blocked": {
        "description": "Execution gate returned BLOCK verdict",
        "severity": "high",
        "reversible": True,
        "recovery_strategy": "abort_and_log",
        "worktree_policy": "cleanup",
        "retry_allowed": False,
        "retry_conditions": [],
    },
    "wrapper_blocked": {
        "description": "Autonomous merge wrapper blocked the merge",
        "severity": "high",
        "reversible": True,
        "recovery_strategy": "abort_and_log",
        "worktree_policy": "cleanup",
        "retry_allowed": False,
        "retry_conditions": [],
    },
    "test_failed": {
        "description": "Post-execution tests failed",
        "severity": "medium",
        "reversible": True,
        "recovery_strategy": "fix_or_rollback",
        "worktree_policy": "keep_for_debug",
        "retry_allowed": True,
        "retry_conditions": ["fix_tests", "simplified_scope", "skip_non_critical"],
    },
    "partial_artifacts": {
        "description": "Some artifacts created but execution incomplete",
        "severity": "low",
        "reversible": True,
        "recovery_strategy": "cleanup_partial",
        "worktree_policy": "cleanup",
        "retry_allowed": True,
        "retry_conditions": ["restart_from_checkpoint"],
    },
    "evidence_mismatch": {
        "description": "Evidence bundle inconsistent with execution record",
        "severity": "medium",
        "reversible": True,
        "recovery_strategy": "regenerate_evidence",
        "worktree_policy": "keep",
        "retry_allowed": True,
        "retry_conditions": ["recreate_evidence", "verify_again"],
    },
}


# ---------- CLI Handlers ----------

def cmd_plan(args):
    """Generate recovery plan for a failure type."""
    as_json = getattr(args, "json_output", False)
    workorder_id = args.id
    failure_type = args.failure_type
    now = datetime.now(timezone.utc).isoformat()

    if failure_type not in FAILURE_TYPES:
        print(f"ERROR: Unknown failure type '{failure_type}'", file=sys.stderr)
        print(f"Available: {', '.join(sorted(FAILURE_TYPES))}", file=sys.stderr)
        return 1

    ft = FAILURE_TYPES[failure_type]
    plan = {
        "workorder_id": workorder_id,
        "failure_type": failure_type,
        "timestamp": now,
        "recovery_version": VERSION,
        "failure_info": {
            "description": ft["description"],
            "severity": ft["severity"],
            "reversible": ft["reversible"],
        },
        "recovery_strategy": ft["recovery_strategy"],
        "worktree_policy": ft["worktree_policy"],
        "retry": {
            "allowed": ft["retry_allowed"],
            "conditions": ft["retry_conditions"],
        },
        "recovery_steps": _get_recovery_steps(failure_type, ft),
        "post_recovery_actions": [
            "Log recovery action to transcript",
            "Update registry status if applicable",
            "Create partial evidence bundle",
            "Notify orchestrator of outcome",
        ],
        "policy": "This is a plan-only operation. No reset/clean/rm/push/delete will be executed.",
    }

    if as_json:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    else:
        _print_plan(plan)
    return 0


def cmd_classify_failure(args):
    """Classify a failure from error message."""
    as_json = getattr(args, "json_output", False)
    workorder_id = args.id
    error_msg = args.error_msg
    now = datetime.now(timezone.utc).isoformat()

    # Simple classification based on error message keywords
    classified_type = "unknown"
    confidence = 0.0
    error_lower = error_msg.lower()

    classifiers = [
        ("model_error", ["quota", "rate limit", "api key", "auth", "provider", "model", "401", "429", "503"]),
        ("timeout", ["timeout", "timed out", "time limit", "deadline"]),
        ("dirty_worktree", ["dirty", "uncommitted", "modified", "untracked"]),
        ("gate_blocked", ["gate", "blocked", "denied", "not allowed"]),
        ("wrapper_blocked", ["wrapper", "merge blocked", "not mergeable"]),
        ("test_failed", ["test fail", "assertion", "pytest", "unittest", "smoke"]),
        ("partial_artifacts", ["partial", "incomplete", "interrupted"]),
        ("evidence_mismatch", ["evidence", "mismatch", "inconsistent", "digest"]),
    ]

    for ftype, keywords in classifiers:
        for kw in keywords:
            if kw in error_lower:
                classified_type = ftype
                confidence = 0.8
                break
        if classified_type != "unknown":
            break

    if classified_type == "unknown":
        classified_type = "model_error"  # default fallback
        confidence = 0.3

    ft = FAILURE_TYPES[classified_type]
    result = {
        "workorder_id": workorder_id,
        "error_msg": error_msg,
        "classified_type": classified_type,
        "confidence": confidence,
        "failure_info": {
            "description": ft["description"],
            "severity": ft["severity"],
            "reversible": ft["reversible"],
        },
        "recommended_action": ft["recovery_strategy"],
        "timestamp": now,
    }

    if as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print_classification(result)
    return 0


def _get_recovery_steps(failure_type, ft):
    """Get specific recovery steps for a failure type."""
    steps_map = {
        "model_error": [
            {"step": 1, "action": "log_error", "description": "Record model error details"},
            {"step": 2, "action": "check_alternatives", "description": "Check fallback models available"},
            {"step": 3, "action": "switch_model_or_abort", "description": "Switch to fallback or abort"},
            {"step": 4, "action": "cleanup_worktree", "description": "Keep worktree for inspection"},
        ],
        "timeout": [
            {"step": 1, "action": "log_timeout", "description": "Record timeout details"},
            {"step": 2, "action": "cancel_execution", "description": "Send cancel signal"},
            {"step": 3, "action": "wait_grace_period", "description": "Wait for graceful shutdown"},
            {"step": 4, "action": "force_cleanup", "description": "Force cleanup if needed"},
            {"step": 5, "action": "keep_worktree", "description": "Keep worktree for inspection"},
        ],
        "dirty_worktree": [
            {"step": 1, "action": "inspect_changes", "description": "List uncommitted changes"},
            {"step": 2, "action": "decide_action", "description": "Commit partial, reset, or user decision"},
            {"step": 3, "action": "execute_decision", "description": "Apply chosen action"},
        ],
        "gate_blocked": [
            {"step": 1, "action": "log_block_reason", "description": "Record gate block details"},
            {"step": 2, "action": "abort_execution", "description": "Abort execution"},
            {"step": 3, "action": "cleanup_worktree", "description": "Clean up worktree"},
        ],
        "wrapper_blocked": [
            {"step": 1, "action": "log_block_reason", "description": "Record wrapper block details"},
            {"step": 2, "action": "abort_merge", "description": "Abort merge attempt"},
            {"step": 3, "action": "cleanup_branch", "description": "Clean up branch"},
        ],
        "test_failed": [
            {"step": 1, "action": "capture_test_output", "description": "Record test failures"},
            {"step": 2, "action": "analyze_failures", "description": "Categorize test failures"},
            {"step": 3, "action": "decide_fix_or_rollback", "description": "Fix tests or rollback"},
            {"step": 4, "action": "execute_decision", "description": "Apply chosen action"},
        ],
        "partial_artifacts": [
            {"step": 1, "action": "inventory_artifacts", "description": "List created artifacts"},
            {"step": 2, "action": "determine_checkpoint", "description": "Find last valid checkpoint"},
            {"step": 3, "action": "cleanup_or_resume", "description": "Clean up or resume from checkpoint"},
        ],
        "evidence_mismatch": [
            {"step": 1, "action": "compare_evidence", "description": "Compare evidence with execution record"},
            {"step": 2, "action": "identify_mismatch", "description": "Find specific inconsistencies"},
            {"step": 3, "action": "regenerate_or_fix", "description": "Regenerate evidence or fix mismatch"},
        ],
    }
    return steps_map.get(failure_type, [{"step": 1, "action": "log_and_abort", "description": "Log error and abort"}])


# ---------- Pretty Printers ----------

def _print_plan(plan):
    print(f"Recovery Plan: {plan['workorder_id']}")
    print(f"  Failure: {plan['failure_type']} ({plan['failure_info']['severity']})")
    print(f"  Strategy: {plan['recovery_strategy']}")
    print(f"  Reversible: {plan['failure_info']['reversible']}")
    print(f"  Retry allowed: {plan['retry']['allowed']}")
    print()
    print("  Recovery steps:")
    for step in plan["recovery_steps"]:
        print(f"    {step['step']}. [{step['action']}] {step['description']}")
    if plan["retry"]["conditions"]:
        print()
        print("  Retry conditions:")
        for c in plan["retry"]["conditions"]:
            print(f"    - {c}")


def _print_classification(result):
    print(f"Failure Classification: {result['workorder_id']}")
    print(f"  Error: {result['error_msg'][:80]}")
    print(f"  Type: {result['classified_type']} (confidence: {result['confidence']:.0%})")
    print(f"  Severity: {result['failure_info']['severity']}")
    print(f"  Action: {result['recommended_action']}")


# ---------- CLI Parser ----------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_executor_recovery",
        description="Executor Recovery Plan — failure recovery/rollback plan generator.",
    )
    parser.add_argument("--version", action="version", version=f"v{VERSION}")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Output JSON")

    sub = parser.add_subparsers(dest="command")

    # plan
    plan = sub.add_parser("plan", aliases=["p"], help="Generate recovery plan")
    plan.add_argument("--id", required=True, help="Workorder ID")
    plan.add_argument("--failure-type", required=True,
                      choices=list(FAILURE_TYPES.keys()),
                      help="Failure type")
    plan.add_argument("--json", dest="json_output", action="store_true")

    # classify-failure
    cf = sub.add_parser("classify-failure", aliases=["cf", "classify"], help="Classify failure from error message")
    cf.add_argument("--id", required=True, help="Workorder ID")
    cf.add_argument("--error-msg", required=True, help="Error message to classify")
    cf.add_argument("--json", dest="json_output", action="store_true")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    handler = {
        "plan": cmd_plan,
        "p": cmd_plan,
        "classify-failure": cmd_classify_failure,
        "cf": cmd_classify_failure,
        "classify": cmd_classify_failure,
    }.get(args.command)
    if handler:
        return handler(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
