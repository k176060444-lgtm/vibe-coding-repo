#!/usr/bin/env python3
"""Read-only CLI tool to output a Vibe Coding repo/job status summary.

Usage:
    python scripts/vibe_repo_status.py --repo-id <id> --base-sha <sha> [--job-id <id>] [--json]

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
from datetime import datetime, timezone


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
    lines.append("  Clean: " + ("No" if git_info.get("has_uncommitted_changes") else "Yes"))
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
        required=True,
        help="Repository identifier.",
    )
    parser.add_argument(
        "--base-sha",
        required=True,
        help="Base commit SHA to compare against.",
    )
    parser.add_argument(
        "--job-id",
        default=None,
        help="Optional job identifier.",
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

    git_info = _git_status_summary()

    if args.output_json:
        output = _format_json(args.repo_id, args.base_sha, args.job_id, git_info)
    else:
        output = _format_text(args.repo_id, args.base_sha, args.job_id, git_info)

    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
