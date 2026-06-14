#!/usr/bin/env python3
"""Queue Advisor v5 - Summary consistency and recovered/merged relationship clarity.

Usage:
    python scripts/vibe_queue_advisor.py [--jobs-dir <dir>] [--json] [--limit <N>]
                                          [--include-tainted] [--include-merged]

Changes from v4:
    - summary.merged_total always equals len(merged_jobs)
    - Default (merged hidden): summary.hidden_merged = merged_total
    - --include-merged: summary.hidden_merged = 0, merged_jobs visible
    - recovered_jobs with outcome=already_merged are a SUBSET of merged_jobs
    - No double-counting between recovered and merged
    - Text: Merged/Recovered/Unresolved counts match JSON exactly

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

_NON_PRODUCTION_PATTERNS = [
    re.compile(r"^_"),
    re.compile(r"smoke", re.IGNORECASE),
    re.compile(r"fixture", re.IGNORECASE),
    re.compile(r"test", re.IGNORECASE),
    re.compile(r"debug", re.IGNORECASE),
    re.compile(r"legacy", re.IGNORECASE),
    re.compile(r"e2e", re.IGNORECASE),
    re.compile(r"_pipeline", re.IGNORECASE),
]


def _is_non_production(job_id):
    for pat in _NON_PRODUCTION_PATTERNS:
        if pat.search(job_id):
            return True
    return False


def _read_json_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _run_git(*args, cwd=None):
    try:
        result = subprocess.run(
            ["git"] + list(args),
            capture_output=True, text=True, timeout=30, cwd=cwd,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _get_main_ancestors(repo_root=None):
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
    if not result_sha:
        return False
    if result_sha in main_shas:
        return True
    for sha in main_shas:
        if sha.startswith(result_sha) or result_sha.startswith(sha):
            return True
    return False


def _recover_result_sha(job_id, job_path, main_shas, repo_root=None):
    """Recover result_sha from multiple sources. Returns (sha, source) or (None, None)."""
    # Source 1: Local files
    for fname in ["manifest.json", "state.json", "approval-snapshot.json",
                   "run-record.json", "review-record.json"]:
        data = _read_json_file(job_path / fname)
        if data:
            for key in ["result_sha", "commit_sha", "head_sha", "sha"]:
                val = data.get(key)
                if val and isinstance(val, str) and len(val) >= 7:
                    return val, fname

    # Source 2: Feature branch head
    cwd = repo_root or os.getcwd()
    for branch_pattern in [f"vibedev/{job_id}", f"vibedev/wo-{job_id}"]:
        sha = _run_git("rev-parse", branch_pattern, cwd=cwd)
        if sha and len(sha) >= 7:
            return sha, "branch"
        sha = _run_git("rev-parse", f"origin/{branch_pattern}", cwd=cwd)
        if sha and len(sha) >= 7:
            return sha, "branch"

    # Source 3: PR merge parent from main history
    log_output = _run_git(
        "log", "--oneline", "--merges", "--all",
        "--grep", job_id, "--format=%H %P %s",
        cwd=cwd,
    )
    if log_output:
        for line in log_output.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                merge_sha = parts[0]
                feature_sha = parts[1]
                if len(feature_sha) >= 7 and feature_sha in main_shas:
                    if len(parts) >= 3 and len(parts[2]) >= 7:
                        candidate = parts[2]
                        if candidate not in main_shas or _is_sha_merged(candidate, main_shas):
                            return candidate, "merge_parent"
                    return feature_sha, "merge_parent"
                elif len(feature_sha) >= 7:
                    return feature_sha, "merge_parent"

    return None, None


def _collect_job_info(job_dir, main_shas=None, repo_root=None):
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
            "result_sha_source": None,
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
    result_sha_source = None
    if manifest and "result_sha" in manifest:
        result_sha = manifest["result_sha"]
        result_sha_source = "manifest"
    elif "result_sha" in wo:
        result_sha = wo["result_sha"]
        result_sha_source = "work-order"

    # Recovery for review_passed/clean with missing result_sha
    if not result_sha and job_status == "review_passed" and audit_status == "clean":
        if main_shas is not None:
            result_sha, result_sha_source = _recover_result_sha(
                job_id, job_path, main_shas, repo_root,
            )

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
        "result_sha_source": result_sha_source,
        "changed_paths": changed_paths,
        "fallback_used": fallback_used,
        "actual_model_used": actual_model_used,
        "records_count": records_count,
        "worktree_present": worktree_present,
        "merged": False,
        "non_production": _is_non_production(job_id),
    }


def _count_tainted_in_dir(jobs_dir):
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


def _collect_jobs(jobs_dir, include_tainted=False, main_shas=None, repo_root=None):
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
            job_info = _collect_job_info(entry, main_shas=main_shas, repo_root=repo_root)
            if not include_tainted and job_info.get("audit_status") == "audit_tainted":
                continue
            jobs.append(job_info)
    return jobs


def _mark_merged_jobs(jobs, main_shas):
    for job in jobs:
        result_sha = job.get("result_sha")
        if result_sha and _is_sha_merged(result_sha, main_shas):
            job["merged"] = True


def _generate_action_items(jobs):
    """Generate action items. recovered_jobs are a SUBSET of merged_jobs when outcome=already_merged."""
    action_items = []
    warnings = []
    blocked_jobs = []
    merged_jobs = []          # All jobs whose result_sha is in main
    informational_jobs = []
    recovered_jobs = []       # Jobs where result_sha was recovered (subset of merged if already_merged)
    unresolved_jobs = []

    for job in jobs:
        job_id = job["job_id"]
        status = job["job_status"]
        audit = job["audit_status"]
        is_merged = job.get("merged", False)
        is_non_prod = job.get("non_production", False)
        result_sha = job.get("result_sha")
        result_sha_source = job.get("result_sha_source")

        # Determine if this result_sha was recovered (not from manifest/work-order)
        is_recovered = result_sha_source and result_sha_source not in ("manifest", "work-order")

        # Priority 1: audit_tainted
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

        # Priority 2: already merged into main
        if is_merged:
            merged_entry = {
                "job_id": job_id,
                "status": status,
                "result_sha": result_sha,
                "result_sha_source": result_sha_source,
            }
            merged_jobs.append(merged_entry)
            # If recovered, also track in recovered_jobs (SUBSET relationship)
            if is_recovered:
                recovered_jobs.append({
                    "job_id": job_id,
                    "result_sha": result_sha,
                    "result_sha_source": result_sha_source,
                    "outcome": "already_merged",
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

        # Priority 4: unknown
        if status == "unknown":
            warnings.append({
                "job_id": job_id,
                "warning": "missing or invalid work-order.json",
            })
            continue

        # Priority 5: non-production
        if is_non_prod:
            informational_jobs.append({
                "job_id": job_id,
                "status": status,
                "reason": "non-production job (smoke/fixture/test/debug/legacy)",
            })
            continue

        # Priority 6: review_passed + clean
        if status == "review_passed" and audit == "clean":
            if result_sha:
                # If recovered and result_sha not in main, track as recovered
                if is_recovered:
                    recovered_jobs.append({
                        "job_id": job_id,
                        "result_sha": result_sha,
                        "result_sha_source": result_sha_source,
                        "outcome": "ready_for_merge",
                    })
                action_items.append({
                    "priority": "low",
                    "action": "ready_for_merge",
                    "job_id": job_id,
                    "description": f"Job {job_id} is ready for merge (result_sha: {str(result_sha)[:12]})",
                })
            else:
                warnings.append({
                    "job_id": job_id,
                    "warning": "review_passed but missing result_sha - recovery failed",
                })
                unresolved_jobs.append({
                    "job_id": job_id,
                    "reason": "result_sha missing and recovery failed",
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

    return (action_items, warnings, blocked_jobs, merged_jobs,
            informational_jobs, recovered_jobs, unresolved_jobs)


def _compute_summary(jobs, action_items, warnings, blocked_jobs, merged_jobs,
                     informational_jobs, recovered_jobs, unresolved_jobs,
                     total_tainted_in_dir, tainted_in_visible, include_merged):
    """Compute summary with consistent counts.

    merged_total = len(merged_jobs)  (always, regardless of include_merged)
    hidden_merged = merged_total if not include_merged, else 0
    """
    from collections import Counter

    status_counts = Counter(j["job_status"] for j in jobs)
    audit_counts = Counter(j["audit_status"] for j in jobs)
    merged_total = len(merged_jobs)

    return {
        "total_jobs": len(jobs),
        "merged_total": merged_total,
        "hidden_merged": merged_total if not include_merged else 0,
        "informational_jobs_count": len(informational_jobs),
        "recovered_jobs_count": len(recovered_jobs),
        "unresolved_jobs_count": len(unresolved_jobs),
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
                 informational_jobs, recovered_jobs, unresolved_jobs, summary,
                 include_merged):
    """Format result as JSON.

    When include_merged=False: merged_jobs list is empty (hidden), summary.merged_total still present.
    When include_merged=True: merged_jobs list is full, summary.hidden_merged=0.
    """
    return json.dumps({
        "total_jobs": total_jobs,
        "action_items": action_items,
        "warnings": warnings,
        "blocked_jobs": blocked_jobs,
        "merged_jobs": merged_jobs if include_merged else [],
        "informational_jobs": informational_jobs,
        "recovered_jobs": recovered_jobs,
        "unresolved_jobs": unresolved_jobs,
        "summary": summary,
    }, indent=2)


def _format_text(action_items, warnings, blocked_jobs, merged_jobs,
                 informational_jobs, recovered_jobs, unresolved_jobs, summary,
                 include_merged):
    lines = [
        "========================================",
        "  Vibe Coding Queue Advisor",
        "========================================",
        f"  Total Jobs: {summary['total_jobs']}",
        f"  Merged: {summary['merged_total']}"
        + ("" if include_merged else f" ({summary['hidden_merged']} hidden)"),
        f"  Blocked: {summary['blocked_total']}"
        + (f" ({summary['hidden_blocked']} hidden)" if summary.get("hidden_blocked") else ""),
        f"  Recovered: {summary['recovered_jobs_count']}",
        f"  Unresolved: {summary['unresolved_jobs_count']}",
        f"  Action Items: {summary['action_items_count']}",
        f"  Warnings: {summary['warnings_count']}",
        f"  Info: {summary['informational_jobs_count']}",
        "----------------------------------------",
    ]

    if blocked_jobs:
        lines.append("  \u26d4 BLOCKED JOBS:")
        for bj in blocked_jobs:
            lines.append(f"    - {bj['job_id']}: {bj['reason']}")
        lines.append("----------------------------------------")

    high_priority = [a for a in action_items if a.get("priority") == "high"]
    if high_priority:
        lines.append("  \U0001f534 HIGH PRIORITY:")
        for a in high_priority:
            lines.append(f"    - [{a['action']}] {a['description']}")
        lines.append("----------------------------------------")

    medium_priority = [a for a in action_items if a.get("priority") == "medium"]
    if medium_priority:
        lines.append("  \U0001f7e1 MEDIUM PRIORITY:")
        for a in medium_priority:
            lines.append(f"    - [{a['action']}] {a['description']}")
        lines.append("----------------------------------------")

    low_priority = [a for a in action_items if a.get("priority") == "low"]
    if low_priority:
        lines.append("  \U0001f7e2 LOW PRIORITY:")
        for a in low_priority:
            lines.append(f"    - [{a['action']}] {a['description']}")
        lines.append("----------------------------------------")

    if warnings:
        lines.append("  \u26a0\ufe0f  WARNINGS:")
        for w in warnings:
            lines.append(f"    - {w['job_id']}: {w['warning']}")
        lines.append("----------------------------------------")

    if informational_jobs:
        lines.append("  \U0001f4cb INFO (non-production):")
        for ij in informational_jobs:
            lines.append(f"    - {ij['job_id']}: {ij['reason']}")
        lines.append("----------------------------------------")

    if include_merged and merged_jobs:
        lines.append("  \U0001f504 MERGED JOBS:")
        for mj in merged_jobs:
            src = f" ({mj.get('result_sha_source', '?')})" if mj.get("result_sha_source") else ""
            lines.append(f"    - {mj['job_id']}: {str(mj.get('result_sha', ''))[:12]}{src}")
        lines.append("----------------------------------------")

    if recovered_jobs:
        lines.append("  \U0001f50d RECOVERED:")
        for rj in recovered_jobs:
            lines.append(f"    - {rj['job_id']}: {rj['result_sha_source']} -> {str(rj['result_sha'])[:12]} ({rj['outcome']})")
        lines.append("----------------------------------------")

    if unresolved_jobs:
        lines.append("  \u2753 UNRESOLVED:")
        for uj in unresolved_jobs:
            lines.append(f"    - {uj['job_id']}: {uj['reason']}")
        lines.append("----------------------------------------")

    lines.append("========================================")
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_queue_advisor",
        description="Queue Advisor v5 - Summary consistency and recovered/merged clarity.",
    )
    parser.add_argument("--jobs-dir", default=None)
    parser.add_argument("--json", dest="output_json", action="store_true", default=False)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--include-tainted", action="store_true", default=False)
    parser.add_argument("--include-merged", action="store_true", default=False)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    jobs_dir = (
        args.jobs_dir
        or os.environ.get("VIBEDEV_JOBS_DIR")
        or os.path.expanduser("~/vibedev/jobs")
    )

    total_tainted_in_dir = _count_tainted_in_dir(jobs_dir)

    repo_root = None
    for candidate in [os.getcwd(), str(Path(jobs_dir).parent)]:
        test = _run_git("rev-parse", "--git-dir", cwd=candidate)
        if test:
            repo_root = candidate
            break

    main_shas = set()
    if repo_root:
        main_shas = _get_main_ancestors(repo_root)

    jobs = _collect_jobs(jobs_dir, include_tainted=args.include_tainted,
                         main_shas=main_shas, repo_root=repo_root)
    _mark_merged_jobs(jobs, main_shas)

    tainted_in_visible = sum(1 for j in jobs if j.get("audit_status") == "audit_tainted")

    (action_items, warnings, blocked_jobs, merged_jobs,
     informational_jobs, recovered_jobs, unresolved_jobs) = _generate_action_items(jobs)

    summary = _compute_summary(
        jobs, action_items, warnings, blocked_jobs, merged_jobs,
        informational_jobs, recovered_jobs, unresolved_jobs,
        total_tainted_in_dir, tainted_in_visible, args.include_merged,
    )

    if args.limit is not None:
        action_items = action_items[:args.limit]

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
                              merged_jobs, informational_jobs, recovered_jobs,
                              unresolved_jobs, summary, args.include_merged)
    else:
        output = _format_text(action_items, warnings, blocked_jobs, merged_jobs,
                              informational_jobs, recovered_jobs, unresolved_jobs,
                              summary, args.include_merged)

    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
