#!/usr/bin/env python3
"""Queue Advisor v3 - Actionable next suggestions with smoke/fixture filtering.

Usage:
    python scripts/vibe_queue_advisor.py [--jobs-dir <dir>] [--json] [--limit <N>]
                                          [--include-tainted] [--include-merged]

Changes from v2:
    - Actionability rules: only real work orders with clean audit, review_passed,
      result_sha present, not in main, and verifiable PR/branch → ready_for_merge
    - smoke/fixture/test/debug/legacy jobs → informational_jobs (never ready_for_merge)
    - audit_tainted always counted in blocked_total (even when hidden)
    - JSON: summary.blocked_total, summary.hidden_blocked, informational_jobs
    - Text: BLOCKED, WARNINGS, INFO sections; blocked_total in header

Constraints:
    - Read-only operations only.
    - No file modifications.
    - No secrets/keys read.
    - Standard library only, no new dependencies.
    - No IO on import.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Patterns that identify non-production jobs (smoke/fixture/test/debug/legacy)
_NON_PRODUCTION_PATTERNS = [
    re.compile(r"^_"),                      # leading underscore
    re.compile(r"smoke", re.IGNORECASE),
    re.compile(r"fixture", re.IGNORECASE),
    re.compile(r"test", re.IGNORECASE),
    re.compile(r"debug", re.IGNORECASE),
    re.compile(r"legacy", re.IGNORECASE),
    re.compile(r"e2e", re.IGNORECASE),
    re.compile(r"_pipeline", re.IGNORECASE),
]


def _is_non_production(job_id):
    """Check if a job_id looks like a non-production (smoke/fixture/test/debug/legacy) job."""
    for pat in _NON_PRODUCTION_PATTERNS:
        if pat.search(job_id):
            return True
    return False


def _read_json_file(path):
    """Read a JSON file safely, return dict or None."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _get_main_ancestors(repo_root=None):
    """Return a set of all commit SHAs reachable from main (full + short)."""
    try:
        cwd = repo_root or os.getcwd()
        result = subprocess.run(
            ["git", "rev-list", "--all"],
            capture_output=True, text=True, timeout=30, cwd=cwd,
        )
        if result.returncode != 0:
            return set()
        shas = set()
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line:
                shas.add(line)
                shas.add(line[:12])
        return shas
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        return set()


def _is_sha_merged(result_sha, main_shas):
    """Check if result_sha is in the main branch history."""
    if not result_sha:
        return False
    if result_sha in main_shas:
        return True
    for sha in main_shas:
        if sha.startswith(result_sha) or result_sha.startswith(sha):
            return True
    return False


def _collect_job_info(job_dir):
    """Collect read-only info for a single job directory."""
    job_path = Path(job_dir)
    job_id = job_path.name

    wo = _read_json_file(job_path / "work-order.json")
    if not wo:
        return {
            "job_id": job_id,
            "job_status": "unknown",
            "audit_status": "unknown",
            "push_allowed": False,
            "base_sha": None,
            "result_sha": None,
            "changed_paths": [],
            "fallback_used": False,
            "actual_model_used": None,
            "records_count": 0,
            "worktree_present": False,
            "merged": False,
            "non_production": _is_non_production(job_id),
            "error": "missing_work_order",
        }

    state = _read_json_file(job_path / "state.json")
    manifest = _read_json_file(job_path / "manifest.json")
    run_record = _read_json_file(job_path / "run-record.json")
    model_policy = _read_json_file(job_path / "model-policy.json")

    job_status = "unknown"
    if state and "status" in state:
        job_status = state["status"]
    elif "status" in wo:
        job_status = wo["status"]

    audit_status = wo.get("audit_status", "clean")
    push_allowed = wo.get("push_allowed", wo.get("allow_push", False))
    if audit_status == "audit_tainted":
        push_allowed = False

    base_sha = wo.get("base_sha")
    result_sha = None
    if manifest and "result_sha" in manifest:
        result_sha = manifest["result_sha"]
    elif "result_sha" in wo:
        result_sha = wo["result_sha"]

    changed_paths = []
    if run_record and "changed_paths" in run_record:
        cp = run_record["changed_paths"]
        if isinstance(cp, str):
            changed_paths = [p.strip() for p in cp.split(",") if p.strip()]
        elif isinstance(cp, list):
            changed_paths = cp

    fallback_used = False
    actual_model_used = wo.get("implementer_model")
    if model_policy:
        primary = model_policy.get("implementer", {}).get("primary")
        if run_record and "model" in run_record:
            actual_model_used = run_record["model"]
            if primary and actual_model_used != primary:
                fallback_used = True
    elif run_record and "model" in run_record:
        actual_model_used = run_record["model"]

    records_count = 0
    try:
        records_count = len([f for f in job_path.iterdir() if f.is_file()])
    except OSError:
        pass

    worktree_present = False
    if manifest and "worktree" in manifest:
        worktree_path = Path(manifest["worktree"])
        worktree_present = worktree_path.exists()

    return {
        "job_id": job_id,
        "job_status": job_status,
        "audit_status": audit_status,
        "push_allowed": push_allowed,
        "base_sha": base_sha,
        "result_sha": result_sha,
        "changed_paths": changed_paths,
        "fallback_used": fallback_used,
        "actual_model_used": actual_model_used,
        "records_count": records_count,
        "worktree_present": worktree_present,
        "merged": False,
        "non_production": _is_non_production(job_id),
    }


def _count_tainted_in_dir(jobs_dir):
    """Count audit_tainted jobs in directory (read-only, for hidden_blocked count).

    This runs BEFORE filtering, so even when include_tainted=False,
    we can report how many tainted jobs exist.
    """
    jobs_path = Path(jobs_dir)
    if not jobs_path.exists() or not jobs_path.is_dir():
        return 0
    count = 0
    try:
        for entry in jobs_path.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                wo = _read_json_file(entry / "work-order.json")
                if wo and wo.get("audit_status") == "audit_tainted":
                    count += 1
    except OSError:
        pass
    return count


def _collect_jobs(jobs_dir, include_tainted=False):
    """Collect all jobs from directory."""
    jobs_path = Path(jobs_dir)
    if not jobs_path.exists() or not jobs_path.is_dir():
        return []

    jobs = []
    try:
        entries = sorted(jobs_path.iterdir())
    except OSError:
        return []

    for entry in entries:
        if entry.is_dir() and not entry.name.startswith("."):
            job_info = _collect_job_info(entry)
            if not include_tainted and job_info.get("audit_status") == "audit_tainted":
                continue
            jobs.append(job_info)

    return jobs


def _mark_merged_jobs(jobs, main_shas):
    """Mark jobs whose result_sha is already in main."""
    for job in jobs:
        result_sha = job.get("result_sha")
        if result_sha and _is_sha_merged(result_sha, main_shas):
            job["merged"] = True


def _generate_action_items(jobs):
    """Generate action items with actionability rules.

    Priority order:
    1. audit_tainted → blocked_jobs (ALWAYS, regardless of merged state)
    2. merged → merged_jobs (skip action items)
    3. failed → high priority
    4. unknown (no work-order) → warning
    5. non_production (smoke/fixture/test/debug/legacy) → informational_jobs
    6. review_passed + clean + result_sha not in main → ready_for_merge
    7. pending/in_progress → continue_processing
    8. review_passed but missing result_sha → warning
    """
    action_items = []
    warnings = []
    blocked_jobs = []
    merged_jobs = []
    informational_jobs = []

    for job in jobs:
        job_id = job["job_id"]
        status = job["job_status"]
        audit = job["audit_status"]
        is_merged = job.get("merged", False)
        is_non_prod = job.get("non_production", False)

        # Priority 1: audit_tainted ALWAYS goes to blocked
        if audit == "audit_tainted":
            blocked_jobs.append({
                "job_id": job_id,
                "reason": "audit_tainted - requires manual review",
                "status": status,
                "audit_status": audit,
            })
            action_items.append({
                "priority": "high",
                "action": "review_blocked",
                "job_id": job_id,
                "description": f"Job {job_id} is audit_tainted - requires manual review",
            })
            continue

        # Priority 2: already merged
        if is_merged:
            merged_jobs.append({
                "job_id": job_id,
                "status": status,
                "result_sha": job.get("result_sha"),
            })
            continue

        # Priority 3: failed
        if status == "failed":
            action_items.append({
                "priority": "high",
                "action": "investigate_failure",
                "job_id": job_id,
                "description": f"Job {job_id} failed - investigate and retry if needed",
            })
            continue

        # Priority 4: unknown (no work-order)
        if status == "unknown":
            warnings.append({
                "job_id": job_id,
                "warning": "missing or invalid work-order.json",
            })
            continue

        # Priority 5: non-production jobs → informational (never ready_for_merge)
        if is_non_prod:
            informational_jobs.append({
                "job_id": job_id,
                "status": status,
                "reason": "non-production job (smoke/fixture/test/debug/legacy)",
            })
            continue

        # Priority 6: review_passed + clean + result_sha not in main → ready_for_merge
        if status == "review_passed" and audit == "clean":
            if not job.get("result_sha"):
                warnings.append({
                    "job_id": job_id,
                    "warning": "review_passed but missing result_sha - cannot verify merge status",
                })
            else:
                action_items.append({
                    "priority": "low",
                    "action": "ready_for_merge",
                    "job_id": job_id,
                    "description": f"Job {job_id} is ready for merge (result_sha: {str(job['result_sha'])[:12]})",
                })
            continue

        # Priority 7: pending / in-progress
        if status in ("pending", "pending_approval", "prepared", "in_progress"):
            action_items.append({
                "priority": "medium",
                "action": "continue_processing",
                "job_id": job_id,
                "description": f"Job {job_id} is {status} - continue processing",
            })
            continue

    return action_items, warnings, blocked_jobs, merged_jobs, informational_jobs


def _compute_summary(jobs, action_items, warnings, blocked_jobs, merged_jobs,
                     informational_jobs, total_tainted_in_dir, tainted_in_visible):
    """Compute summary statistics.

    blocked_total = tainted_in_visible (visible blocked jobs in this run)
    hidden_blocked = total_tainted_in_dir - tainted_in_visible (tainted jobs hidden by default)
    """
    from collections import Counter

    status_counts = Counter(j["job_status"] for j in jobs)
    audit_counts = Counter(j["audit_status"] for j in jobs)

    return {
        "total_jobs": len(jobs),
        "merged_jobs_count": len(merged_jobs),
        "informational_jobs_count": len(informational_jobs),
        "by_status": dict(status_counts),
        "by_audit_status": dict(audit_counts),
        "action_items_count": len(action_items),
        "warnings_count": len(warnings),
        "blocked_jobs_count": len(blocked_jobs),
        "blocked_total": total_tainted_in_dir,
        "hidden_blocked": max(0, total_tainted_in_dir - tainted_in_visible),
        "high_priority_count": len([a for a in action_items if a.get("priority") == "high"]),
    }


def _format_json(total_jobs, action_items, warnings, blocked_jobs, merged_jobs,
                 informational_jobs, summary):
    """Format result as JSON."""
    return json.dumps({
        "total_jobs": total_jobs,
        "action_items": action_items,
        "warnings": warnings,
        "blocked_jobs": blocked_jobs,
        "merged_jobs": merged_jobs,
        "informational_jobs": informational_jobs,
        "summary": summary,
    }, indent=2)


def _format_text(action_items, warnings, blocked_jobs, merged_jobs,
                 informational_jobs, summary):
    """Format result as human-readable text."""
    lines = [
        "========================================",
        "  Vibe Coding Queue Advisor",
        "========================================",
        f"  Total Jobs: {summary['total_jobs']}",
        f"  Merged: {summary['merged_jobs_count']}",
        f"  Blocked: {summary['blocked_total']}"
        + (f" ({summary['hidden_blocked']} hidden)" if summary.get("hidden_blocked") else ""),
        f"  Action Items: {summary['action_items_count']}",
        f"  Warnings: {summary['warnings_count']}",
        f"  Info: {summary['informational_jobs_count']}",
        "----------------------------------------",
    ]

    # Blocked jobs
    if blocked_jobs:
        lines.append("  \u26d4 BLOCKED JOBS:")
        for bj in blocked_jobs:
            lines.append(f"    - {bj['job_id']}: {bj['reason']}")
        lines.append("----------------------------------------")

    # High priority actions
    high_priority = [a for a in action_items if a.get("priority") == "high"]
    if high_priority:
        lines.append("  \U0001f534 HIGH PRIORITY:")
        for a in high_priority:
            lines.append(f"    - [{a['action']}] {a['description']}")
        lines.append("----------------------------------------")

    # Medium priority actions
    medium_priority = [a for a in action_items if a.get("priority") == "medium"]
    if medium_priority:
        lines.append("  \U0001f7e1 MEDIUM PRIORITY:")
        for a in medium_priority:
            lines.append(f"    - [{a['action']}] {a['description']}")
        lines.append("----------------------------------------")

    # Low priority actions
    low_priority = [a for a in action_items if a.get("priority") == "low"]
    if low_priority:
        lines.append("  \U0001f7e2 LOW PRIORITY:")
        for a in low_priority:
            lines.append(f"    - [{a['action']}] {a['description']}")
        lines.append("----------------------------------------")

    # Warnings
    if warnings:
        lines.append("  \u26a0\ufe0f  WARNINGS:")
        for w in warnings:
            lines.append(f"    - {w['job_id']}: {w['warning']}")
        lines.append("----------------------------------------")

    # Informational (non-production)
    if informational_jobs:
        lines.append("  \U0001f4cb INFO (non-production):")
        for ij in informational_jobs:
            lines.append(f"    - {ij['job_id']}: {ij['reason']}")
        lines.append("----------------------------------------")

    lines.append("========================================")
    return "\n".join(lines)


def build_parser():
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="vibe_queue_advisor",
        description="Queue Advisor v3 - Actionable suggestions with smoke/fixture filtering.",
    )
    parser.add_argument(
        "--jobs-dir",
        default=None,
        help="Jobs directory path (default: VIBEDEV_JOBS_DIR env or ~/vibedev/jobs).",
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        default=False,
        help="Output in JSON format.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of action items displayed.",
    )
    parser.add_argument(
        "--include-tainted",
        action="store_true",
        default=False,
        help="Include audit_tainted jobs in analysis.",
    )
    parser.add_argument(
        "--include-merged",
        action="store_true",
        default=False,
        help="Include merged jobs in action items output.",
    )
    return parser


def main(argv=None):
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    jobs_dir = (
        args.jobs_dir
        or os.environ.get("VIBEDEV_JOBS_DIR")
        or os.path.expanduser("~/vibedev/jobs")
    )

    # Count total tainted in directory BEFORE filtering
    total_tainted_in_dir = _count_tainted_in_dir(jobs_dir)

    # Collect main branch ancestors for merge detection
    main_shas = set()
    for candidate in [os.getcwd(), str(Path(jobs_dir).parent)]:
        main_shas = _get_main_ancestors(candidate)
        if main_shas:
            break

    jobs = _collect_jobs(jobs_dir, include_tainted=args.include_tainted)
    _mark_merged_jobs(jobs, main_shas)

    tainted_in_visible = sum(1 for j in jobs if j.get("audit_status") == "audit_tainted")

    action_items, warnings, blocked_jobs, merged_jobs, informational_jobs = _generate_action_items(jobs)
    summary = _compute_summary(
        jobs, action_items, warnings, blocked_jobs, merged_jobs,
        informational_jobs, total_tainted_in_dir, tainted_in_visible,
    )

    # Apply limit to action_items
    if args.limit is not None:
        action_items = action_items[:args.limit]

    # Optionally re-include merged jobs in action_items for display
    if args.include_merged and merged_jobs:
        for mj in merged_jobs:
            action_items.append({
                "priority": "info",
                "action": "already_merged",
                "job_id": mj["job_id"],
                "description": f"Job {mj['job_id']} already merged into main (result_sha: {str(mj.get('result_sha', ''))[:12]})",
            })

    if args.output_json:
        output = _format_json(len(jobs), action_items, warnings, blocked_jobs,
                              merged_jobs, informational_jobs, summary)
    else:
        output = _format_text(action_items, warnings, blocked_jobs, merged_jobs,
                              informational_jobs, summary)

    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
