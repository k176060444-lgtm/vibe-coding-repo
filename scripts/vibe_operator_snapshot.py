#!/usr/bin/env python3
"""Operator Snapshot v1 - Unified status snapshot for QQ/Hermes orchestrator.

Usage:
    python scripts/vibe_operator_snapshot.py [--repo-root <dir>] [--jobs-dir <dir>]
                                              [--json] [--compact]
                                              [--include-merged] [--include-tainted]

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
import subprocess
import sys
from pathlib import Path


def _run_cmd(*args, cwd=None, timeout=30):
    """Run a command and return (stdout, returncode)."""
    try:
        result = subprocess.run(
            list(args), capture_output=True, text=True, timeout=timeout, cwd=cwd,
        )
        return result.stdout.strip(), result.returncode
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        return "", 1


def _run_git(*args, cwd=None):
    """Run git command and return stdout or empty string."""
    stdout, rc = _run_cmd("git", *args, cwd=cwd)
    return stdout if rc == 0 else ""


def _get_repo_info(repo_root):
    """Get repo status: main SHA, remote SHA, consistency."""
    local_main = _run_git("rev-parse", "main", cwd=repo_root)
    remote_main = _run_git("rev-parse", "origin/main", cwd=repo_root)
    consistent = local_main == remote_main if (local_main and remote_main) else False
    dirty = bool(_run_git("status", "--porcelain", cwd=repo_root))
    branch = _run_git("branch", "--show-current", cwd=repo_root)
    return {
        "local_main_sha": local_main,
        "remote_main_sha": remote_main,
        "main_consistent": consistent,
        "working_tree_dirty": dirty,
        "current_branch": branch,
    }


def _run_advisor(jobs_dir, include_tainted=False, include_merged=False):
    """Run vibe_queue_advisor.py --json and parse output."""
    cmd = [sys.executable, "scripts/vibe_queue_advisor.py", "--json"]
    if include_tainted:
        cmd.append("--include-tainted")
    if include_merged:
        cmd.append("--include-merged")
    stdout, rc = _run_cmd(*cmd)
    if rc != 0:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _run_repo_status_jobs(jobs_dir):
    """Run vibe_repo_status.py --jobs --json for job registry."""
    cmd = [sys.executable, "scripts/vibe_repo_status.py", "--jobs", "--json"]
    stdout, rc = _run_cmd(*cmd)
    if rc != 0:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def _extract_locks(advisor_data):
    """Extract tainted/blocked lock info from advisor data."""
    locks = []
    if not advisor_data:
        return locks
    for bj in advisor_data.get("blocked_jobs", []):
        locks.append({
            "job_id": bj["job_id"],
            "lock_type": bj.get("audit_status", "unknown"),
            "reason": bj.get("reason", ""),
            "push_allowed": False,
        })
    return locks


def _extract_warnings(advisor_data, repo_info):
    """Extract warnings from advisor and repo info."""
    warnings = []
    if advisor_data:
        for w in advisor_data.get("warnings", []):
            warnings.append(f"{w['job_id']}: {w['warning']}")
    if repo_info and not repo_info.get("main_consistent"):
        warnings.append("Local main and remote main are inconsistent")
    if repo_info and repo_info.get("working_tree_dirty"):
        warnings.append("Working tree has uncommitted changes")
    return warnings


def _determine_next_action(advisor_data, repo_info, locks):
    """Determine recommended next action based on current state."""
    if not advisor_data:
        return "review_queue_state"

    # If there are blocked/tainted jobs
    if locks:
        return f"resolve_blocked ({len(locks)} locked job(s))"

    # If there are high priority actions
    high = [a for a in advisor_data.get("action_items", []) if a.get("priority") == "high"]
    if high:
        return f"investigate_failures ({len(high)} high priority)"

    # If there are ready_for_merge items
    ready = [a for a in advisor_data.get("action_items", []) if a.get("action") == "ready_for_merge"]
    if ready:
        return f"process_merge_queue ({len(ready)} ready)"

    # If there are pending items
    pending = [a for a in advisor_data.get("action_items", []) if a.get("priority") == "medium"]
    if pending:
        return f"continue_processing ({len(pending)} pending)"

    # If there are unresolved
    unresolved = advisor_data.get("unresolved_jobs", [])
    if unresolved:
        return f"resolve_unresolved ({len(unresolved)} jobs)"

    # Queue appears clean
    return "queue_clean: consider documentation, next phase planning, or queue cleanup"


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_operator_snapshot",
        description="Operator Snapshot v1 - Unified status for QQ/Hermes orchestrator.",
    )
    parser.add_argument("--repo-root", default=None,
                        help="Repository root (default: CWD or detected).")
    parser.add_argument("--jobs-dir", default=None,
                        help="Jobs directory (default: VIBEDEV_JOBS_DIR or ~/vibedev/jobs).")
    parser.add_argument("--json", dest="output_json", action="store_true", default=False,
                        help="Output in JSON format.")
    parser.add_argument("--compact", action="store_true", default=False,
                        help="Compact text output (~20 lines).")
    parser.add_argument("--include-merged", action="store_true", default=False,
                        help="Include merged jobs in analysis.")
    parser.add_argument("--include-tainted", action="store_true", default=False,
                        help="Include audit_tainted jobs in analysis.")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = args.repo_root or os.getcwd()
    jobs_dir = (
        args.jobs_dir
        or os.environ.get("VIBEDEV_JOBS_DIR")
        or os.path.expanduser("~/vibedev/jobs")
    )

    # Collect data
    repo_info = _get_repo_info(repo_root)
    advisor_data = _run_advisor(jobs_dir, args.include_tainted, args.include_merged)
    locks = _extract_locks(advisor_data)
    warnings = _extract_warnings(advisor_data, repo_info)
    next_action = _determine_next_action(advisor_data, repo_info, locks)

    # Build advisor summary
    advisor_summary = {}
    if advisor_data and "summary" in advisor_data:
        s = advisor_data["summary"]
        advisor_summary = {
            "total_jobs": s.get("total_jobs", 0),
            "merged_total": s.get("merged_total", 0),
            "blocked_total": s.get("blocked_total", 0),
            "hidden_blocked": s.get("hidden_blocked", 0),
            "recovered_jobs_count": s.get("recovered_jobs_count", 0),
            "unresolved_jobs_count": s.get("unresolved_jobs_count", 0),
            "action_items_count": s.get("action_items_count", 0),
            "warnings_count": s.get("warnings_count", 0),
            "informational_jobs_count": s.get("informational_jobs_count", 0),
        }

    # Top action items (for compact display)
    action_items_top = []
    if advisor_data:
        for ai in advisor_data.get("action_items", [])[:5]:
            action_items_top.append({
                "priority": ai.get("priority"),
                "action": ai.get("action"),
                "job_id": ai.get("job_id"),
                "description": ai.get("description"),
            })

    snapshot = {
        "repo": {
            "repo_id": os.path.basename(repo_root),
            "local_main_sha": repo_info["local_main_sha"],
            "remote_main_sha": repo_info["remote_main_sha"],
            "main_consistent": repo_info["main_consistent"],
            "working_tree_dirty": repo_info["working_tree_dirty"],
            "current_branch": repo_info["current_branch"],
        },
        "jobs_summary": advisor_summary,
        "locks": locks,
        "action_items_top": action_items_top,
        "recommended_next_action": next_action,
        "warnings": warnings,
    }

    if args.output_json:
        print(json.dumps(snapshot, indent=2))
    else:
        _print_text(snapshot, args.compact, locks, advisor_data)
    return 0


def _print_text(snapshot, compact, locks, advisor_data):
    repo = snapshot["repo"]
    js = snapshot["jobs_summary"]
    main_short = (repo["local_main_sha"] or "?")[:12]
    remote_short = (repo["remote_main_sha"] or "?")[:12]
    consistent = "YES" if repo["main_consistent"] else "NO"

    lines = [
        "\u2550" * 40,
        "  \U0001f4ca Operator Snapshot",
        "\u2550" * 40,
        f"  Main:     {main_short}",
        f"  Remote:   {remote_short}",
        f"  Sync:     {consistent}",
        f"  Jobs:     {js.get('total_jobs', '?')}",
        f"  Merged:   {js.get('merged_total', '?')}",
        f"  Blocked:  {js.get('blocked_total', '?')}"
        + (f" ({js.get('hidden_blocked', 0)} hidden)" if js.get("hidden_blocked") else ""),
        f"  Actions:  {js.get('action_items_count', '?')}",
        f"  Warnings: {js.get('warnings_count', '?')}",
        f"  Recovered: {js.get('recovered_jobs_count', '?')}",
        f"  Unresolved: {js.get('unresolved_jobs_count', '?')}",
    ]

    if locks:
        lines.append("\u2500" * 40)
        lines.append("  \U0001f512 LOCKS:")
        for lk in locks:
            lines.append(f"    - {lk['job_id']}: {lk['lock_type']} (push=false)")

    if not compact:
        # Show top action items
        if snapshot["action_items_top"]:
            lines.append("\u2500" * 40)
            lines.append("  \U0001f4cc TOP ACTIONS:")
            for ai in snapshot["action_items_top"]:
                lines.append(f"    - [{ai['priority']}] {ai['job_id']}: {ai['action']}")

    lines.append("\u2500" * 40)
    lines.append(f"  \u27a1 NEXT: {snapshot['recommended_next_action']}")

    if snapshot["warnings"] and not compact:
        lines.append("\u2500" * 40)
        lines.append("  \u26a0\ufe0f  WARNINGS:")
        for w in snapshot["warnings"][:5]:
            lines.append(f"    - {w}")

    lines.append("\u2550" * 40)
    print("\n".join(lines))


if __name__ == "__main__":
    sys.exit(main())
