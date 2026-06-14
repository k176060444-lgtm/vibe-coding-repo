#!/usr/bin/env python3
"""Batch Queue Plan v1 - Generate execution plans for multiple Work Orders.

Usage:
    python scripts/vibe_batch_plan.py [--jobs-dir <dir>] [--json] [--limit N]

Reads Operator Snapshot and Queue Advisor output, generates a batch execution plan
for multiple low-risk Work Orders. The plan is read-only and does not execute
any shell/git operations.

Constraints:
    - Read-only, no IO on import, standard library only.
    - Plan generation only, no execution.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _run_script(script, *args):
    """Run a Python script and return parsed JSON or None."""
    try:
        cmd = [sys.executable, script] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, FileNotFoundError):
        pass
    return None


def _classify_risk(item):
    """Classify risk level for a Work Order action item.
    
    Returns: "low", "medium", "high", "critical"
    
    Risk factors based on action_items fields:
    - action: review_blocked -> critical
    - action: investigate_failure -> high
    - action: continue_processing -> medium
    - action: ready_for_merge -> low
    - priority: high -> high, medium -> medium, low -> low
    """
    action = item.get("action", "")
    priority = item.get("priority", "info")
    
    # Critical: blocked/tainted
    if action == "review_blocked":
        return "critical"
    
    # High: failures
    if action == "investigate_failure" or priority == "high":
        return "high"
    
    # Medium: in-progress
    if action == "continue_processing" or priority == "medium":
        return "medium"
    
    # Low: ready for merge
    return "low"
def _generate_plan(snapshot, advisor, limit=None):
    """Generate batch execution plan.
    
    Returns a plan with:
    - task_order: ordered list of Work Orders to execute
    - risk_level: overall risk level
    - allowed_paths: paths that can be modified
    - stop_conditions: conditions that halt execution
    - requires_human_approval: whether human approval is needed
    - expected_reports: what reports to generate
    """
    # Get action items from advisor
    action_items = advisor.get("action_items", []) if advisor else []
    lifecycle = advisor.get("lifecycle_summary", {}) if advisor else {}
    blocked_jobs = advisor.get("blocked_jobs", []) if advisor else []
    superseded_jobs = advisor.get("superseded_jobs", []) if advisor else []
    
    # Filter actionable items (not blocked, not superseded)
    actionable = []
    for item in action_items:
        job_id = item.get("job_id", "")
        
        # Skip blocked jobs
        if any(b["job_id"] == job_id for b in blocked_jobs):
            continue
        
        # Skip superseded jobs
        if any(s["job_id"] == job_id for s in superseded_jobs):
            continue
        
        # Skip non-production jobs
        if any(kw in job_id.lower() for kw in [
            "smoke", "fixture", "test", "debug", "legacy", "e2e", "_pipeline"
        ]):
            continue
        
        actionable.append(item)
    
    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    actionable.sort(key=lambda x: priority_order.get(x.get("priority", "info"), 4))
    
    # Apply limit
    if limit and limit > 0:
        actionable = actionable[:limit]
    
    # Build task order
    task_order = []
    for item in actionable:
        job_id = item.get("job_id", "")
        action = item.get("action", "")
        priority = item.get("priority", "info")
        
        task_order.append({
            "job_id": job_id,
            "action": action,
            "priority": priority,
            "risk_level": _classify_risk(item),
            "requires_human_approval": priority in ["high", "critical"],
        })
    
    # Calculate overall risk
    risk_levels = [t["risk_level"] for t in task_order]
    if "critical" in risk_levels:
        overall_risk = "critical"
    elif "high" in risk_levels:
        overall_risk = "high"
    elif "medium" in risk_levels:
        overall_risk = "medium"
    else:
        overall_risk = "low"
    
    # Determine if human approval is needed
    requires_human_approval = overall_risk in ["high", "critical"] or any(
        t["requires_human_approval"] for t in task_order
    )
    
    # Define stop conditions
    stop_conditions = [
        "Any Work Order fails acceptance",
        "origin/main SHA changes during execution",
        "Gate check returns blockers",
        "Wrapper merge returns allow_merge=false",
        "Changed paths exceed declared scope",
        "audit_tainted lock status changes",
        "New high-priority failures detected",
    ]
    
    # Define expected reports
    expected_reports = [
        "Per-Work Order: conclusion, base_sha, result_sha, PR URL, changed_paths",
        "Per-Work Order: implementer_model, reviewer_model, job_status, audit_status",
        "Per-Work Order: wrapper dry-run/merge results, post-merge freeze",
        "Per-Work Order: operator snapshot compact, wo-code-repo-status-001 lock status",
        "Batch summary: total tasks, success/failure count, final main SHA",
        "Batch summary: risk level, human approval status, stop conditions triggered",
    ]
    
    plan = {
        "batch_id": f"batch-{len(task_order)}-tasks",
        "task_order": task_order,
        "task_count": len(task_order),
        "risk_level": overall_risk,
        "allowed_paths": [],  # Will be filled per-task
        "stop_conditions": stop_conditions,
        "requires_human_approval": requires_human_approval,
        "expected_reports": expected_reports,
        "current_state": {
            "main_sha": snapshot.get("repo", {}).get("local_main_sha", "unknown"),
            "main_consistent": snapshot.get("repo", {}).get("main_consistent", False),
            "total_jobs": snapshot.get("jobs_summary", {}).get("total_jobs", 0),
            "lifecycle": lifecycle,
        },
    }
    
    # Collect allowed paths from all tasks
    all_paths = set()
    for item in actionable:
        # This is a simplified version; real implementation would read from work-order.json
        pass
    plan["allowed_paths"] = sorted(all_paths)
    
    return plan


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_batch_plan",
        description="Batch Queue Plan v1 - Generate execution plans for multiple Work Orders.",
    )
    parser.add_argument("--jobs-dir", default=None)
    parser.add_argument("--json", dest="output_json", action="store_true", default=False)
    parser.add_argument("--limit", type=int, default=None)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    jobs_dir = (
        args.jobs_dir
        or os.environ.get("VIBEDEV_JOBS_DIR")
        or os.path.expanduser("~/vibedev/jobs")
    )

    # Gather scripts directory
    script_dir = Path(__file__).parent

    # Run Operator Snapshot
    snapshot_args = ["--json", "--jobs-dir", jobs_dir]
    snapshot = _run_script(str(script_dir / "vibe_operator_snapshot.py"), *snapshot_args)
    if not snapshot:
        snapshot = {"locks": [], "recommended_next_action": "unknown", "jobs_summary": {}}

    # Run Queue Advisor
    advisor_args = ["--json", "--jobs-dir", jobs_dir]
    advisor = _run_script(str(script_dir / "vibe_queue_advisor.py"), *advisor_args)
    if not advisor:
        advisor = {"action_items": [], "superseded_jobs": [], "unresolved_jobs": [],
                   "lifecycle_summary": {}, "summary": {}}

    # Generate plan
    plan = _generate_plan(snapshot, advisor, args.limit)

    if args.output_json:
        print(json.dumps(plan, indent=2))
    else:
        _print_text(plan)
    return 0


def _print_text(plan):
    lines = [
        "\u2550" * 40,
        "  \U0001f4cb Batch Queue Plan v1",
        "\u2550" * 40,
        f"  Batch ID: {plan['batch_id']}",
        f"  Tasks: {plan['task_count']}",
        f"  Risk Level: {plan['risk_level'].upper()}",
        f"  Human Approval: {'YES' if plan['requires_human_approval'] else 'NO'}",
        "\u2500" * 40,
        "  Task Order:",
    ]
    
    for i, task in enumerate(plan.get("task_order", []), 1):
        lines.append(f"    {i}. {task['job_id']} ({task['priority']}, {task['risk_level']})")
    
    lines.extend([
        "\u2500" * 40,
        "  Stop Conditions:",
    ])
    for cond in plan.get("stop_conditions", []):
        lines.append(f"    - {cond}")
    
    lines.extend([
        "\u2500" * 40,
        "  Expected Reports:",
    ])
    for report in plan.get("expected_reports", []):
        lines.append(f"    - {report}")
    
    lines.append("\u2550" * 40)
    print("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
