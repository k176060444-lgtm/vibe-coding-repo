#!/usr/bin/env python3
"""Queue Advisor v6 - Superseded job detection and non-production priority fix.

Changes from v6 (lifecycle):
    - Job lifecycle classification: tainted_lock, merged, superseded, non_production, active, failed, unknown
    - lifecycle_summary in JSON and text output

Changes from v5:
    - non_production check BEFORE failed check (smoke/fixture/test never HIGH PRIORITY)
    - Superseded detection: failed job with later successful job in same series → superseded
    - JSON: superseded_jobs list, summary.superseded_jobs_count
    - Text: SUPERSEDED section
    - recommended_next_action no longer misled by obsolete failed jobs

Constraints:
    - Read-only, no IO on import, standard library only.
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


def _find_superseding_job(job_id, all_jobs):
    """Check if a failed job has a later successful job in the same series.

    Pattern: wo-xxx-001 → look for wo-xxx-002, wo-xxx-003, etc.
    """
    # Extract base pattern: remove trailing -NNN
    m = re.match(r"^(.+)-(\d{3})$", job_id)
    if not m:
        return None
    base = m.group(1)
    num = int(m.group(2))

    # Look for higher-numbered jobs with same base
    candidates = []
    for j in all_jobs:
        jid = j["job_id"]
        jm = re.match(r"^(.+)-(\d{3})$", jid)
        if jm and jm.group(1) == base and int(jm.group(2)) > num:
            candidates.append(j)

    # Check if any candidate is review_passed/merged
    for c in candidates:
        if c["job_status"] in ("review_passed",) and c["audit_status"] == "clean":
            return c["job_id"]
        if c.get("merged"):
            return c["job_id"]

    return None



# --- Job Lifecycle Policy v1 ---
# Lifecycle states:
#   tainted_lock  : audit_tainted (must preserve, never suggest push/merge)
#   merged        : result_sha in main (completed, no action needed)
#   superseded    : failed with later success in same series
#   non_production: smoke/fixture/test/debug/legacy
#   active        : pending/in_progress/review_passed (not yet merged)
#   failed        : failed without superseding job
#   unknown       : missing work-order

_LIFECYCLE_ORDER = [
    "tainted_lock", "merged", "superseded", "non_production",
    "active", "failed", "unknown",
]


def _classify_lifecycle(job, all_jobs):
    """Classify a job into its lifecycle state."""
    audit = job.get("audit_status", "unknown")
    status = job.get("job_status", "unknown")
    is_merged = job.get("merged", False)
    is_non_prod = job.get("non_production", False)

    if audit == "audit_tainted":
        return "tainted_lock"
    if is_merged:
        return "merged"
    if status == "failed":
        superseded_by = _find_superseding_job(job["job_id"], all_jobs)
        if superseded_by:
            return "superseded"
        if is_non_prod:
            return "non_production"
        return "failed"
    if is_non_prod:
        return "non_production"
    if status in ("review_passed", "pending", "pending_approval", "prepared", "in_progress"):
        return "active"
    return "unknown"


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
    for fname in ["manifest.json", "state.json", "approval-snapshot.json",
                   "run-record.json", "review-record.json"]:
        data = _read_json_file(job_path / fname)
        if data:
            for key in ["result_sha", "commit_sha", "head_sha", "sha"]:
                val = data.get(key)
                if val and isinstance(val, str) and len(val) >= 7:
                    return val, fname

    cwd = repo_root or os.getcwd()
    for branch_pattern in [f"vibedev/{job_id}", f"vibedev/wo-{job_id}"]:
        sha = _run_git("rev-parse", branch_pattern, cwd=cwd)
        if sha and len(sha) >= 7:
            return sha, "branch"
        sha = _run_git("rev-parse", f"origin/{branch_pattern}", cwd=cwd)
        if sha and len(sha) >= 7:
            return sha, "branch"

    log_output = _run_git(
        "log", "--oneline", "--merges", "--all",
        "--grep", job_id, "--format=%H %P %s",
        cwd=cwd,
    )
    if log_output:
        for line in log_output.splitlines():
            parts = line.split()
            if len(parts) >= 2:
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
    """Generate action items with v6 priority order.

    Key change: non_production check BEFORE failed check.
    Key change: superseded detection for failed jobs.

    Priority order:
    1. audit_tainted → blocked_jobs
    2. merged → merged_jobs
    3. non_production → informational_jobs (BEFORE failed!)
    4. failed + superseded → superseded_jobs
    5. failed + not superseded → high priority
    6. unknown → warning
    7. review_passed + clean → ready_for_merge
    8. pending/in_progress → continue_processing
    """
    action_items = []
    warnings = []
    blocked_jobs = []
    merged_jobs = []
    informational_jobs = []
    recovered_jobs = []
    unresolved_jobs = []
    superseded_jobs = []

    # Build a lookup for superseded detection
    all_jobs_lookup = {j["job_id"]: j for j in jobs}

    for job in jobs:
        job_id = job["job_id"]
        status = job["job_status"]
        audit = job["audit_status"]
        is_merged = job.get("merged", False)
        is_non_prod = job.get("non_production", False)
        result_sha = job.get("result_sha")
        result_sha_source = job.get("result_sha_source")
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

        # Priority 2: already merged
        if is_merged:
            merged_jobs.append({
                "job_id": job_id,
                "status": status,
                "result_sha": result_sha,
                "result_sha_source": result_sha_source,
            })
            if is_recovered:
                recovered_jobs.append({
                    "job_id": job_id,
                    "result_sha": result_sha,
                    "result_sha_source": result_sha_source,
                    "outcome": "already_merged",
                })
            continue

        # Priority 3: non-production (BEFORE failed!)
        if is_non_prod:
            informational_jobs.append({
                "job_id": job_id,
                "status": status,
                "reason": "non-production job (smoke/fixture/test/debug/legacy)",
            })
            continue

        # Priority 4: failed
        if status == "failed":
            # Check if superseded by a later successful job
            superseded_by = _find_superseding_job(job_id, jobs)
            if superseded_by:
                superseded_jobs.append({
                    "job_id": job_id,
                    "superseded_by": superseded_by,
                    "reason": f"superseded by {superseded_by}",
                })
            else:
                action_items.append({
                    "priority": "high",
                    "action": "investigate_failure",
                    "job_id": job_id,
                    "description": f"Job {job_id} failed - investigate and retry if needed",
                })
            continue

        # Priority 5: unknown
        if status == "unknown":
            warnings.append({
                "job_id": job_id,
                "warning": "missing or invalid work-order.json",
            })
            continue

        # Priority 6: review_passed + clean
        if status == "review_passed" and audit == "clean":
            if result_sha:
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
            informational_jobs, recovered_jobs, unresolved_jobs, superseded_jobs)


def _compute_summary(jobs, action_items, warnings, blocked_jobs, merged_jobs,
                     informational_jobs, recovered_jobs, unresolved_jobs,
                     superseded_jobs, total_tainted_in_dir, tainted_in_visible,
                     include_merged, lifecycle_summary=None):
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
        "superseded_jobs_count": len(superseded_jobs),
        "by_status": dict(status_counts),
        "by_audit_status": dict(audit_counts),
        "action_items_count": len(action_items),
        "warnings_count": len(warnings),
        "blocked_jobs_count": len(blocked_jobs),
        "blocked_total": total_tainted_in_dir,
        "hidden_blocked": max(0, total_tainted_in_dir - tainted_in_visible),
        "high_priority_count": len([a for a in action_items if a.get("priority") == "high"]),
        "lifecycle": lifecycle_summary or {},
    }


def _format_json(total_jobs, action_items, warnings, blocked_jobs, merged_jobs,
                 informational_jobs, recovered_jobs, unresolved_jobs,
                 superseded_jobs, summary, include_merged, lifecycle_summary=None):
    return json.dumps({
        "total_jobs": total_jobs,
        "lifecycle_summary": lifecycle_summary or {},
        "action_items": action_items,
        "warnings": warnings,
        "blocked_jobs": blocked_jobs,
        "merged_jobs": merged_jobs if include_merged else [],
        "informational_jobs": informational_jobs,
        "recovered_jobs": recovered_jobs,
        "unresolved_jobs": unresolved_jobs,
        "superseded_jobs": superseded_jobs,
        "summary": summary,
    }, indent=2)


def _format_text(action_items, warnings, blocked_jobs, merged_jobs,
                 informational_jobs, recovered_jobs, unresolved_jobs,
                 superseded_jobs, summary, include_merged):
    lines = [
        "\u2550" * 40,
        "  Vibe Coding Queue Advisor",
        "\u2550" * 40,
        f"  Total Jobs: {summary['total_jobs']}",
        f"  Merged: {summary['merged_total']}"
        + ("" if include_merged else f" ({summary['hidden_merged']} hidden)"),
        f"  Blocked: {summary['blocked_total']}"
        + (f" ({summary['hidden_blocked']} hidden)" if summary.get("hidden_blocked") else ""),
        f"  Superseded: {summary['superseded_jobs_count']}",
        f"  Recovered: {summary['recovered_jobs_count']}",
        f"  Unresolved: {summary['unresolved_jobs_count']}",
        f"  Action Items: {summary['action_items_count']}",
        f"  Warnings: {summary['warnings_count']}",
        f"  Info: {summary['informational_jobs_count']}",
        f"  Lifecycle: " + ", ".join(f"{k}={v}" for k, v in summary.get("lifecycle", {}).items()),
        "\u2500" * 40,
    ]

    if blocked_jobs:
        lines.append("  \u26d4 BLOCKED JOBS:")
        for bj in blocked_jobs:
            lines.append(f"    - {bj['job_id']}: {bj['reason']}")
        lines.append("\u2500" * 40)

    high_priority = [a for a in action_items if a.get("priority") == "high"]
    if high_priority:
        lines.append("  \U0001f534 HIGH PRIORITY:")
        for a in high_priority:
            lines.append(f"    - [{a['action']}] {a['description']}")
        lines.append("\u2500" * 40)

    medium_priority = [a for a in action_items if a.get("priority") == "medium"]
    if medium_priority:
        lines.append("  \U0001f7e1 MEDIUM PRIORITY:")
        for a in medium_priority:
            lines.append(f"    - [{a['action']}] {a['description']}")
        lines.append("\u2500" * 40)

    low_priority = [a for a in action_items if a.get("priority") == "low"]
    if low_priority:
        lines.append("  \U0001f7e2 LOW PRIORITY:")
        for a in low_priority:
            lines.append(f"    - [{a['action']}] {a['description']}")
        lines.append("\u2500" * 40)

    if superseded_jobs:
        lines.append("  \U0001f504 SUPERSEDED:")
        for sj in superseded_jobs:
            lines.append(f"    - {sj['job_id']}: {sj['reason']}")
        lines.append("\u2500" * 40)

    if warnings:
        lines.append("  \u26a0\ufe0f  WARNINGS:")
        for w in warnings:
            lines.append(f"    - {w['job_id']}: {w['warning']}")
        lines.append("\u2500" * 40)

    if informational_jobs:
        lines.append("  \U0001f4cb INFO (non-production):")
        for ij in informational_jobs:
            lines.append(f"    - {ij['job_id']}: {ij['reason']}")
        lines.append("\u2500" * 40)

    if include_merged and merged_jobs:
        lines.append("  \U0001f504 MERGED JOBS:")
        for mj in merged_jobs:
            src = f" ({mj.get('result_sha_source', '?')})" if mj.get("result_sha_source") else ""
            lines.append(f"    - {mj['job_id']}: {str(mj.get('result_sha', ''))[:12]}{src}")
        lines.append("\u2500" * 40)

    if recovered_jobs:
        lines.append("  \U0001f50d RECOVERED:")
        for rj in recovered_jobs:
            lines.append(f"    - {rj['job_id']}: {rj['result_sha_source']} -> {str(rj['result_sha'])[:12]} ({rj['outcome']})")
        lines.append("\u2500" * 40)

    if unresolved_jobs:
        lines.append("  \u2753 UNRESOLVED:")
        for uj in unresolved_jobs:
            lines.append(f"    - {uj['job_id']}: {uj['reason']}")
        lines.append("\u2500" * 40)

    lines.append("\u2550" * 40)
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_queue_advisor",
        description="Queue Advisor v6 - Superseded detection, non-production priority fix.",
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

    # Classify lifecycle for each job
    for job in jobs:
        job["lifecycle"] = _classify_lifecycle(job, jobs)

    tainted_in_visible = sum(1 for j in jobs if j.get("audit_status") == "audit_tainted")

    (action_items, warnings, blocked_jobs, merged_jobs,
     informational_jobs, recovered_jobs, unresolved_jobs,
     superseded_jobs) = _generate_action_items(jobs)

    lifecycle_summary = {lc: sum(1 for j in jobs if j.get("lifecycle") == lc) for lc in _LIFECYCLE_ORDER if sum(1 for j in jobs if j.get("lifecycle") == lc) > 0}

    summary = _compute_summary(
        jobs, action_items, warnings, blocked_jobs, merged_jobs,
        informational_jobs, recovered_jobs, unresolved_jobs,
        superseded_jobs, total_tainted_in_dir, tainted_in_visible,
        args.include_merged, lifecycle_summary,
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
                              unresolved_jobs, superseded_jobs, summary,
                              args.include_merged, lifecycle_summary)
    else:
        output = _format_text(action_items, warnings, blocked_jobs, merged_jobs,
                              informational_jobs, recovered_jobs, unresolved_jobs,
                              superseded_jobs, summary, args.include_merged)

    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
