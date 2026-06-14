#!/usr/bin/env python3
"""Read-only CLI tool to output a Vibe Coding repo/job status summary.

Usage:
    python scripts/vibe_repo_status.py --repo-id <id> --base-sha <sha> [--job-id <id>] [--json]
    python scripts/vibe_repo_status.py --jobs [--jobs-dir <dir>] [--json]
    python scripts/vibe_repo_status.py --jobs-summary [--jobs-dir <dir>] [--json]
    python scripts/vibe_repo_status.py --jobs [--status <val>] [--audit-status <val>] [--limit <N>] [--sort <field>] [--json]

Constraints:
    - No network access.
    - No secrets/keys read.
    - No file modifications.
    - No git push/merge/deploy.
"""

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def _run_git(*args):
    """Run a git command and return stripped stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return None


def _git_status_summary():
    """Collect local git status information (read-only)."""
    info = {}

    branch = _run_git("rev-parse", "--abbrev-ref", "HEAD")
    if branch:
        info["current_branch"] = branch

    head_sha = _run_git("rev-parse", "HEAD")
    if head_sha:
        info["head_sha"] = head_sha

    short_sha = _run_git("rev-parse", "--short", "HEAD")
    if short_sha:
        info["head_short_sha"] = short_sha

    commit_count = _run_git("rev-list", "--count", "HEAD")
    if commit_count:
        info["commit_count"] = int(commit_count)

    last_commit_msg = _run_git("log", "-1", "--pretty=%s")
    if last_commit_msg:
        info["last_commit_message"] = last_commit_msg

    last_commit_author = _run_git("log", "-1", "--pretty=%an")
    if last_commit_author:
        info["last_commit_author"] = last_commit_author

    last_commit_date = _run_git("log", "-1", "--pretty=%aI")
    if last_commit_date:
        info["last_commit_date"] = last_commit_date

    upstream = _run_git("rev-parse", "--abbrev-ref", "@{upstream}")
    if upstream:
        info["upstream"] = upstream
        ahead_behind = _run_git("rev-list", "--left-right", "--count", f"{upstream}...HEAD")
        if ahead_behind:
            parts = ahead_behind.split()
            if len(parts) == 2:
                info["behind_upstream"] = int(parts[0])
                info["ahead_of_upstream"] = int(parts[1])
    else:
        info["upstream"] = None
        info["behind_upstream"] = None
        info["ahead_of_upstream"] = None

    diff_output = _run_git("status", "--porcelain")
    if diff_output is not None:
        lines = [l for l in diff_output.splitlines() if l.strip()]
        info["uncommitted_changes"] = len(lines)
        info["has_uncommitted_changes"] = len(lines) > 0
    else:
        info["uncommitted_changes"] = 0
        info["has_uncommitted_changes"] = False

    stash_count = _run_git("stash", "list")
    if stash_count is not None:
        info["stashed_changes"] = len(stash_count.splitlines()) if stash_count else 0
    else:
        info["stashed_changes"] = 0

    untracked_output = _run_git("ls-files", "--others", "--exclude-standard")
    if untracked_output is not None:
        info["untracked_files"] = len(
            [l for l in untracked_output.splitlines() if l.strip()]
        )
    else:
        info["untracked_files"] = 0

    tags = _run_git("tag", "--points-at", "HEAD")
    if tags is not None:
        info["tags_at_head"] = tags.splitlines() if tags else []
    else:
        info["tags_at_head"] = []

    return info


def _read_json_file(path):
    """Read a JSON file safely, return dict or None."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _collect_job_info(job_dir):
    """Collect read-only info for a single job directory."""
    job_path = Path(job_dir)
    job_id = job_path.name

    # Read work-order.json (primary source)
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
            "error": "missing_work_order",
        }

    # Read optional files
    state = _read_json_file(job_path / "state.json")
    manifest = _read_json_file(job_path / "manifest.json")
    run_record = _read_json_file(job_path / "run-record.json")
    model_policy = _read_json_file(job_path / "model-policy.json")

    # Determine job_status: prefer state.json > work-order.status
    job_status = "unknown"
    if state and "status" in state:
        job_status = state["status"]
    elif "status" in wo:
        job_status = wo["status"]

    # Determine audit_status
    audit_status = wo.get("audit_status", "clean")

    # Determine push_allowed
    push_allowed = wo.get("push_allowed", wo.get("allow_push", False))
    if audit_status == "audit_tainted":
        push_allowed = False

    # Determine base_sha
    base_sha = wo.get("base_sha")

    # Determine result_sha from manifest
    result_sha = None
    if manifest:
        result_sha = manifest.get("result_sha")

    # Determine changed_paths from run_record
    changed_paths = []
    if run_record and "changed_paths" in run_record:
        cp = run_record["changed_paths"]
        if isinstance(cp, str):
            changed_paths = [p.strip() for p in cp.split(",") if p.strip()]
        elif isinstance(cp, list):
            changed_paths = cp

    # Determine fallback_used and actual_model_used
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

    # Count records (files in job directory)
    records_count = 0
    try:
        records_count = len([f for f in job_path.iterdir() if f.is_file()])
    except OSError:
        pass

    # Check worktree presence
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
    }


def _collect_jobs_summary(jobs_dir):
    """Collect summary for all jobs in directory."""
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
            jobs.append(job_info)

    return jobs


def _filter_jobs(jobs, status=None, audit_status=None):
    """Filter jobs by status and/or audit_status."""
    filtered = jobs
    if status:
        filtered = [j for j in filtered if j["job_status"] == status]
    if audit_status:
        filtered = [j for j in filtered if j["audit_status"] == audit_status]
    return filtered


def _sort_jobs(jobs, sort_field="job_id"):
    """Sort jobs by field."""
    if sort_field == "job_id":
        return sorted(jobs, key=lambda j: j["job_id"])
    elif sort_field == "job_status":
        return sorted(jobs, key=lambda j: (j["job_status"], j["job_id"]))
    elif sort_field == "audit_status":
        return sorted(jobs, key=lambda j: (j["audit_status"], j["job_id"]))
    else:
        return jobs


def _compute_summary(jobs):
    """Compute summary statistics for jobs."""
    status_counts = Counter(j["job_status"] for j in jobs)
    audit_counts = Counter(j["audit_status"] for j in jobs)
    push_counts = Counter(j["push_allowed"] for j in jobs)

    return {
        "total": len(jobs),
        "by_status": dict(status_counts),
        "by_audit_status": dict(audit_counts),
        "by_push_allowed": {
            "true": push_counts.get(True, 0),
            "false": push_counts.get(False, 0),
        },
        "audit_tainted_count": audit_counts.get("audit_tainted", 0),
    }


def _format_jobs_summary_text(summary):
    """Return human-readable jobs summary."""
    lines = [
        "========================================",
        "  Vibe Coding Job Registry Summary",
        "========================================",
        f"  Total Jobs: {summary['total']}",
        "----------------------------------------",
    ]

    # By status
    lines.append("  By Job Status:")
    for status, count in sorted(summary["by_status"].items()):
        lines.append(f"    {status}: {count}")

    lines.append("----------------------------------------")

    # By audit status
    lines.append("  By Audit Status:")
    for audit, count in sorted(summary["by_audit_status"].items()):
        marker = " ⚠️" if audit == "audit_tainted" else ""
        lines.append(f"    {audit}: {count}{marker}")

    lines.append("----------------------------------------")

    # By push allowed
    lines.append("  By Push Allowed:")
    lines.append(f"    true: {summary['by_push_allowed']['true']}")
    lines.append(f"    false: {summary['by_push_allowed']['false']}")

    if summary["audit_tainted_count"] > 0:
        lines.append("----------------------------------------")
        lines.append(f"  ⚠️  Audit Tainted: {summary['audit_tainted_count']} job(s)")

    lines.append("========================================")
    return "\n".join(lines)


def _format_jobs_summary_json(summary):
    """Return JSON jobs summary."""
    return json.dumps({"summary": summary}, indent=2)


def _format_jobs_text(jobs):
    """Return human-readable jobs list."""
    if not jobs:
        return "No jobs found."

    lines = [
        "========================================",
        "  Vibe Coding Job Registry",
        "========================================",
        f"  Total Jobs: {len(jobs)}",
        "----------------------------------------",
    ]

    for job in jobs:
        push_flag = "PUSH_OK" if job["push_allowed"] else "NO_PUSH"
        audit_flag = (
            f"audit={job['audit_status']}" if job["audit_status"] != "clean" else ""
        )
        fallback_flag = "FALLBACK" if job["fallback_used"] else ""

        status_line = f"  {job['job_id']}: {job['job_status']} [{push_flag}]"
        if audit_flag:
            status_line += f" [{audit_flag}]"
        if fallback_flag:
            status_line += f" [{fallback_flag}]"

        lines.append(status_line)
        lines.append(
            f"    base={job['base_sha'][:12] if job['base_sha'] else 'N/A'}"
        )
        lines.append(
            f"    result={job['result_sha'][:12] if job['result_sha'] else 'N/A'}"
        )
        lines.append(f"    model={job['actual_model_used'] or 'N/A'}")
        lines.append(
            f"    records={job['records_count']}  worktree={'yes' if job['worktree_present'] else 'no'}"
        )
        if job["changed_paths"]:
            lines.append(f"    changed={', '.join(job['changed_paths'][:3])}")
        lines.append("----------------------------------------")

    lines.append("========================================")
    return "\n".join(lines)


def _format_jobs_json(jobs):
    """Return JSON jobs list."""
    return json.dumps({"jobs": jobs, "total": len(jobs)}, indent=2)


def _format_text(repo_id, base_sha, job_id, git_info):
    """Return a human-readable status summary string."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "========================================",
        "  Vibe Coding Repo Status Summary",
        "========================================",
        f"  Repo ID      : {repo_id}",
        f"  Base SHA     : {base_sha}",
    ]
    if job_id:
        lines.append(f"  Job ID       : {job_id}")
    lines.append(f"  Report Time  : {now}")
    lines.append("----------------------------------------")

    branch = git_info.get("current_branch", "unknown")
    head = git_info.get("head_sha", "unknown")
    short = git_info.get("head_short_sha", "?")
    lines.append(f"  Branch       : {branch}")
    lines.append(f"  HEAD         : {short} ({head})")

    if git_info.get("last_commit_message"):
        lines.append(f"  Last Commit  : {git_info['last_commit_message']}")
    if git_info.get("last_commit_author"):
        lines.append(f"  Last Author  : {git_info['last_commit_author']}")
    if git_info.get("last_commit_date"):
        lines.append(f"  Last Date    : {git_info['last_commit_date']}")

    lines.append("----------------------------------------")

    upstream = git_info.get("upstream")
    if upstream:
        lines.append(f"  Upstream     : {upstream}")
        behind = git_info.get("behind_upstream")
        ahead = git_info.get("ahead_of_upstream")
        if behind is not None and ahead is not None:
            lines.append(f"  Behind       : {behind}")
            lines.append(f"  Ahead        : {ahead}")
    else:
        lines.append("  Upstream     : (none)")

    lines.append("----------------------------------------")
    lines.append(f"  Uncommitted  : {git_info.get('uncommitted_changes', 0)}")
    lines.append(f"  Untracked    : {git_info.get('untracked_files', 0)}")
    lines.append(f"  Stash        : {git_info.get('stashed_changes', 0)}")

    tags = git_info.get("tags_at_head", [])
    if tags:
        lines.append(f"  Tags at HEAD : {', '.join(tags)}")

    lines.append("========================================")
    lines.append(
        "  Clean: " + ("No" if git_info.get("has_uncommitted_changes") else "Yes")
    )
    lines.append("========================================")

    return "\n".join(lines)


def _format_json(repo_id, base_sha, job_id, git_info):
    """Return a JSON status summary string."""
    payload = {
        "repo_id": repo_id,
        "base_sha": base_sha,
        "job_id": job_id,
        "report_time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git": git_info,
    }
    return json.dumps(payload, indent=2)


def build_parser():
    """Build and return the argument parser (exposed for testing)."""
    parser = argparse.ArgumentParser(
        prog="vibe_repo_status",
        description="Read-only CLI tool to output a Vibe Coding repo/job status summary.",
    )
    parser.add_argument(
        "--repo-id",
        default=None,
        help="Repository identifier.",
    )
    parser.add_argument(
        "--base-sha",
        default=None,
        help="Base commit SHA to compare against.",
    )
    parser.add_argument(
        "--job-id",
        default=None,
        help="Optional job identifier.",
    )
    parser.add_argument(
        "--jobs",
        action="store_true",
        default=False,
        help="List jobs overview from jobs directory.",
    )
    parser.add_argument(
        "--jobs-summary",
        action="store_true",
        default=False,
        help="Show jobs summary statistics grouped by status/audit/push.",
    )
    parser.add_argument(
        "--jobs-dir",
        default=None,
        help="Jobs directory path (default: VIBEDEV_JOBS_DIR env or ~/vibedev/jobs).",
    )
    parser.add_argument(
        "--status",
        default=None,
        help="Filter jobs by job_status value.",
    )
    parser.add_argument(
        "--audit-status",
        default=None,
        help="Filter jobs by audit_status value.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of jobs displayed.",
    )
    parser.add_argument(
        "--sort",
        default="job_id",
        choices=["job_id", "job_status", "audit_status"],
        help="Sort jobs by field (default: job_id).",
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        default=False,
        help="Output in JSON format instead of human-readable text.",
    )
    return parser


def main(argv=None):
    """Entry point. Accepts optional argv for testing."""
    parser = build_parser()
    args = parser.parse_args(argv)

    # Determine jobs directory
    jobs_dir = (
        args.jobs_dir
        or os.environ.get("VIBEDEV_JOBS_DIR")
        or os.path.expanduser("~/vibedev/jobs")
    )

    # Jobs summary mode
    if args.jobs_summary:
        jobs = _collect_jobs_summary(jobs_dir)
        summary = _compute_summary(jobs)

        if args.output_json:
            output = _format_jobs_summary_json(summary)
        else:
            output = _format_jobs_summary_text(summary)

        print(output)
        return 0

    # Jobs list mode
    if args.jobs:
        jobs = _collect_jobs_summary(jobs_dir)

        # Apply filters
        jobs = _filter_jobs(jobs, status=args.status, audit_status=args.audit_status)

        # Apply sort
        jobs = _sort_jobs(jobs, sort_field=args.sort)

        # Apply limit
        if args.limit is not None:
            jobs = jobs[: args.limit]

        if args.output_json:
            output = _format_jobs_json(jobs)
        else:
            output = _format_jobs_text(jobs)

        print(output)
        return 0

    # Repo status mode (requires --repo-id and --base-sha)
    if not args.repo_id or not args.base_sha:
        parser.error(
            "--repo-id and --base-sha are required for repo status mode (or use --jobs/--jobs-summary)"
        )

    git_info = _git_status_summary()

    if args.output_json:
        output = _format_json(args.repo_id, args.base_sha, args.job_id, git_info)
    else:
        output = _format_text(args.repo_id, args.base_sha, args.job_id, git_info)

    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
