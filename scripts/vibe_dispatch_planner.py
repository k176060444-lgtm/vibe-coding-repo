#!/usr/bin/env python3
"""Dispatch Planner v2 - Enhanced lifecycle-aware next Work Order suggestions.

Usage:
    python scripts/vibe_dispatch_planner.py [--jobs-dir <dir>] [--json] [--compact]

Reads Operator Snapshot and Queue Advisor output, generates actionable Work Order suggestions.

Changes from v1:
- Lifecycle-aware: handles tainted_lock, superseded, non_production, informational
- Passes --jobs-dir to sub-scripts correctly
- Scenario-stable output for queue_clean, blocked, failed, superseded, non-production

Constraints:
    - Read-only, no IO on import, standard library only.
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


def _generate_plan(snapshot, advisor):
    """Generate dispatch plan based on current state.
    
    Priority order:
    1. critical: tainted locks (manual resolution required)
    2. high: investigation failures
    3. medium: superseded conflicts, in-progress jobs
    4. low: ready_for_merge
    5. info: queue_clean, non-production informational
    """
    suggestions = []

    # Extract key metrics
    locks = snapshot.get("locks", [])
    action_items = advisor.get("action_items", []) if advisor else []
    lifecycle = advisor.get("lifecycle_summary", {}) if advisor else {}
    high_priority = [a for a in action_items if a.get("priority") == "high"]
    medium_priority = [a for a in action_items if a.get("priority") == "medium"]
    low_priority = [a for a in action_items if a.get("priority") == "low"]
    superseded = advisor.get("superseded_jobs", []) if advisor else []
    informational = advisor.get("informational_jobs", []) if advisor else []
    blocked = advisor.get("blocked_jobs", []) if advisor else []

    # Rule 1: If there are blocked/tainted locks
    if locks:
        suggestions.append({
            "action": "hold_due_to_blocker",
            "priority": "critical",
            "description": f"{len(locks)} tainted lock(s) require manual resolution",
            "details": [lk["job_id"] for lk in locks],
            "work_order_template": "wo-maint-resolve-tainted-lock-{id}",
        })

    # Rule 2: If there are high priority failures
    if high_priority:
        suggestions.append({
            "action": "investigate_failures",
            "priority": "high",
            "description": f"{len(high_priority)} high priority item(s) need investigation",
            "details": [a["job_id"] for a in high_priority],
            "work_order_template": "wo-maint-investigate-{id}",
        })

    # Rule 3: If there are superseded jobs (conflict risk)
    if superseded:
        suggestions.append({
            "action": "resolve_superseded",
            "priority": "medium",
            "description": f"{len(superseded)} job(s) superseded by newer versions",
            "details": [s["job_id"] for s in superseded],
            "work_order_template": "wo-maint-resolve-superseded-{id}",
        })

    # Rule 4: If there are in-progress jobs
    if medium_priority:
        suggestions.append({
            "action": "continue_processing",
            "priority": "medium",
            "description": f"{len(medium_priority)} job(s) in progress",
            "details": [a["job_id"] for a in medium_priority],
        })

    # Rule 5: If there are ready_for_merge items
    if low_priority:
        suggestions.append({
            "action": "process_merge_queue",
            "priority": "low",
            "description": f"{len(low_priority)} job(s) ready for merge",
            "details": [a["job_id"] for a in low_priority],
        })

    # Rule 6: Non-production informational (no action needed)
    if informational:
        suggestions.append({
            "action": "non_production_info",
            "priority": "info",
            "description": f"{len(informational)} non-production job(s) (smoke/fixture/test)",
            "details": [i["job_id"] for i in informational],
        })

    # Rule 7: If queue is clean (no high/medium/locks)
    if not high_priority and not medium_priority and not locks:
        suggestions.append({
            "action": "queue_clean",
            "priority": "info",
            "description": "Queue is clean. Consider next phase:",
            "details": [
                "documentation: solidify workflow docs, runbooks, cheatsheets",
                "feature_work: start new feature Work Orders",
                "maintenance: archive old records, clean up jobs directory",
                "planning: define next cluster capability milestones",
            ],
            "work_order_template": "wo-{type}-{name}-001",
        })

    # Sort by priority
    priority_map = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    suggestions.sort(key=lambda s: priority_map.get(s.get("priority", "info"), 5))

    return suggestions


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_dispatch_planner",
        description="Dispatch Planner v2 - lifecycle-aware next Work Order suggestions.",
    )
    parser.add_argument("--jobs-dir", default=None)
    parser.add_argument("--json", dest="output_json", action="store_true", default=False)
    parser.add_argument("--compact", action="store_true", default=False)
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
    suggestions = _generate_plan(snapshot, advisor)

    # Top recommendation
    top = suggestions[0] if suggestions else {"action": "none", "description": "No suggestions"}

    plan = {
        "current_state": {
            "main_sha": snapshot.get("repo", {}).get("local_main_sha", "unknown"),
            "main_consistent": snapshot.get("repo", {}).get("main_consistent", False),
            "total_jobs": snapshot.get("jobs_summary", {}).get("total_jobs", 0),
            "lifecycle": advisor.get("lifecycle_summary", {}),
        },
        "suggestions": suggestions,
        "recommended_action": top.get("action", "none"),
        "recommended_description": top.get("description", ""),
        "suggestion_count": len(suggestions),
    }

    if args.output_json:
        print(json.dumps(plan, indent=2))
    else:
        _print_text(plan, args.compact)
    return 0


def _print_text(plan, compact):
    state = plan["current_state"]
    lines = [
        "\u2550" * 40,
        "  \U0001f4cb Dispatch Planner v2",
        "\u2550" * 40,
        f"  Main: {str(state.get('main_sha', '?'))[:12]}",
        f"  Jobs: {state.get('total_jobs', '?')}",
        f"  Lifecycle: " + ", ".join(f"{k}={v}" for k, v in state.get("lifecycle", {}).items()),
        "\u2500" * 40,
        f"  \u27a1 RECOMMENDED: {plan['recommended_action']}",
        f"  {plan['recommended_description']}",
        "\u2500" * 40,
    ]

    if not compact:
        for s in plan.get("suggestions", []):
            prio = s.get("priority", "?").upper()
            lines.append(f"  [{prio}] {s['action']}: {s['description']}")
            for d in s.get("details", [])[:3]:
                lines.append(f"    - {d}")

    lines.append("\u2550" * 40)
    print("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
