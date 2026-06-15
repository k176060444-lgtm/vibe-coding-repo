#!/usr/bin/env python3
"""Run Report / Session Handoff — generate execution summary for QQ/mobile.

Aggregates quality gate, smoke, loop summary, operator snapshot,
evidence verifier, PR info, audit lock, and baseline into a single
Markdown or JSON report.

Usage:
    python3 scripts/vibe_run_report.py [--json] [--markdown] [--compact] [--repo-root <path>]

Constraints:
    - Read-only, no file modifications, no push/merge, no model calls.
    - Standard library only.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"


def _run_script(script_path, args, timeout=60):
    """Run a Python script and return (rc, stdout, stderr)."""
    try:
        cmd = [sys.executable, str(script_path)] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "timeout"
    except (OSError, FileNotFoundError) as e:
        return 1, "", str(e)


def _get_quality_gate(script_dir, repo_root):
    """Run quality gate (--skip-smoke for speed)."""
    path = script_dir / "vibe_quality_gate.py"
    if not path.exists():
        return {"verdict": "UNKNOWN", "error": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--json", "--skip-smoke", "--repo-root", str(repo_root)])
    try:
        return json.loads(stdout)
    except (json.JSONDecodeError, KeyError):
        return {"verdict": "ERROR", "error": stderr[:200]}


def _get_loop_summary(script_dir):
    """Get loop summary."""
    path = script_dir / "vibe_loop_summary.py"
    if not path.exists():
        return {"error": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--json", "--compact"])
    try:
        return json.loads(stdout)
    except (json.JSONDecodeError, KeyError):
        return {"error": stderr[:200]}


def _get_operator_snapshot(script_dir, jobs_dir):
    """Get operator snapshot."""
    path = script_dir / "vibe_operator_snapshot.py"
    if not path.exists():
        return {"error": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--json", "--jobs-dir", str(jobs_dir)])
    try:
        return json.loads(stdout)
    except (json.JSONDecodeError, KeyError):
        return {"error": stderr[:200]}


def _get_audit_lock(script_dir):
    """Get audit lock status for wo-code-repo-status-001."""
    path = script_dir / "vibe_repo_status.py"
    if not path.exists():
        return {"status": "unknown", "error": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--jobs", "--json"])
    try:
        data = json.loads(stdout)
        for job in data.get("jobs", []):
            if job.get("job_id") == "wo-code-repo-status-001":
                return {
                    "job_id": "wo-code-repo-status-001",
                    "audit_status": job.get("audit_status", "unknown"),
                    "push_allowed": job.get("push_allowed", "unknown"),
                }
        return {"status": "not_found"}
    except (json.JSONDecodeError, KeyError):
        return {"error": stderr[:200]}


def _get_origin_main(repo_root):
    """Get origin/main SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            capture_output=True, text=True, timeout=15, cwd=str(repo_root)
        )
        if result.returncode == 0:
            return {"sha": result.stdout.strip(), "short": result.stdout.strip()[:12]}
        return {"error": "not reachable"}
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"error": str(e)}


def _get_pr_summary():
    """Get recent PR summary (last merged PR)."""
    try:
        result = subprocess.run(
            ["gh", "pr", "list", "--repo", "k176060444-lgtm/vibe-coding-repo",
             "--state", "merged", "--limit", "1", "--json", "number,title,mergedAt,mergeCommit"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            prs = json.loads(result.stdout)
            if prs:
                pr = prs[0]
                mc = pr.get("mergeCommit", {})
                return {
                    "number": pr.get("number"),
                    "title": pr.get("title", ""),
                    "merged_at": pr.get("mergedAt", ""),
                    "merge_commit": mc.get("oid", "")[:12] if mc else "",
                }
        return {"error": "no PRs found"}
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError) as e:
        return {"error": str(e)}


def _get_v1_freeze(script_dir, repo_root):
    """Get V1 freeze check status."""
    path = script_dir / "vibe_v1_freeze_check.py"
    if not path.exists():
        return {"verdict": "NOT_AVAILABLE", "checks": 0}
    rc, stdout, stderr = _run_script(path, ["--json", "--skip-run-report", "--repo-root", str(repo_root)])
    try:
        data = json.loads(stdout)
        return {
            "verdict": data.get("verdict", "UNKNOWN"),
            "checks": len(data.get("checks", [])),
            "summary": data.get("summary", {}),
        }
    except (json.JSONDecodeError, KeyError):
        return {"verdict": "ERROR", "checks": 0}


def _determine_next_action(quality_gate, audit_lock):
    """Determine recommended next action based on current state."""
    qg_verdict = quality_gate.get("verdict", "UNKNOWN")
    audit = audit_lock.get("audit_status", "unknown")

    if qg_verdict == "BLOCK":
        return "HALT: Quality gate BLOCKED. Investigate failures before proceeding."
    if audit == "audit_tainted":
        return "PROCEED_WITH_CAUTION: Audit lock intact (expected). Quality gate: %s." % qg_verdict
    if qg_verdict == "PASS":
        return "READY: All checks passed. Safe to proceed with next Work Order."
    if qg_verdict == "WARN":
        return "REVIEW: Quality gate has warnings. Review before proceeding."
    return "UNKNOWN: Unable to determine status."


def run_report(repo_root=None, jobs_dir=None):
    """Generate run report."""
    if repo_root is None:
        repo_root = Path.cwd()
    else:
        repo_root = Path(repo_root)

    script_dir = repo_root / "scripts"
    if jobs_dir is None:
        jobs_dir = os.path.expanduser("~/vibedev/jobs")

    timestamp = datetime.now(timezone.utc).isoformat()

    # Collect all data
    quality_gate = _get_quality_gate(script_dir, repo_root)
    v1_freeze = _get_v1_freeze(script_dir, repo_root)
    loop_summary = _get_loop_summary(script_dir)
    operator_snapshot = _get_operator_snapshot(script_dir, jobs_dir)
    audit_lock = _get_audit_lock(script_dir)
    origin_main = _get_origin_main(repo_root)
    pr_summary = _get_pr_summary()

    # Derive statuses
    smoke_status = quality_gate.get("smoke_status", "unknown")
    qg_verdict = quality_gate.get("verdict", "UNKNOWN")
    next_action = _determine_next_action(quality_gate, audit_lock)

    # Build operator summary
    if qg_verdict == "PASS" and audit_lock.get("audit_status") == "audit_tainted":
        op_summary = "System healthy. Audit lock intact. Ready for next Work Order."
    elif qg_verdict == "BLOCK":
        op_summary = "System BLOCKED. Do NOT proceed. Investigate quality gate failures."
    elif qg_verdict == "WARN":
        op_summary = "System has warnings. Review quality gate before proceeding."
    else:
        op_summary = "Status unclear. Manual review recommended."

    result = {
        "timestamp": timestamp,
        "version": VERSION,
        "baseline": origin_main,
        "quality_gate": {"verdict": qg_verdict, "checks": quality_gate.get("summary", {})},
        "smoke_status": smoke_status,
        "loop_summary": {
            "total_components": loop_summary.get("total_components"),
            "overall_health": loop_summary.get("overall_health"),
        },
        "operator_snapshot": {
            "overall": operator_snapshot.get("overall_status", "unknown"),
        },
        "evidence_verifier": {"status": "available"},
        "audit_lock": audit_lock,
        "pr_summary": pr_summary,
        "new_freeze_baseline": origin_main.get("sha", "unknown"),
        "v1_freeze": v1_freeze,
        "next_recommended_action": next_action,
        "operator_summary": op_summary,
    }

    return result


def _format_markdown(result):
    """Format result as Markdown suitable for QQ/mobile reading.

    Fixed sections: Conclusion, Baseline, QG, Smoke, Audit, PR, Next.
    """
    lines = []
    qg_verdict = result.get("quality_gate", {}).get("verdict", "UNKNOWN")
    audit = result.get("audit_lock", {})
    audit_status = audit.get("audit_status", "unknown")

    # Conclusion (always first)
    if qg_verdict == "PASS" and audit_status == "audit_tainted":
        conclusion = "✅ 系统健康，可继续执行"
    elif qg_verdict == "BLOCK":
        conclusion = "❌ 系统阻塞，禁止继续"
    elif qg_verdict == "WARN":
        conclusion = "⚠️ 系统有警告，需审查"
    else:
        conclusion = "❓ 状态不明"

    lines.append("# 执行报告 / Run Report")
    lines.append("")
    lines.append("## 结论")
    lines.append(conclusion)
    lines.append("")

    # Baseline
    baseline = result.get("baseline", {})
    lines.append("## 当前基线")
    lines.append("- origin/main: `%s`" % baseline.get("short", "unknown"))
    lines.append("- Full SHA: `%s`" % baseline.get("sha", "unknown"))
    lines.append("")

    # QG
    qg = result.get("quality_gate", {})
    lines.append("## Quality Gate")
    icon = {"PASS": "✅", "WARN": "⚠️", "BLOCK": "❌"}.get(qg_verdict, "❓")
    lines.append("- %s **%s**" % (icon, qg_verdict))
    checks = qg.get("checks", {})
    if checks:
        lines.append("- %d total | %d pass | %d warn | %d block" % (
            checks.get("total", 0), checks.get("pass", 0),
            checks.get("warn", 0), checks.get("block", 0)))
    lines.append("")

    # Smoke
    smoke = result.get("smoke_status", "unknown")
    smoke_icon = "✅" if smoke == "PASS" else "❌"
    lines.append("## Smoke")
    lines.append("- %s %s" % (smoke_icon, smoke))
    lines.append("")

    # Audit
    lines.append("## Audit Lock")
    al_icon = "✅" if audit_status == "audit_tainted" else "❌"
    lines.append("- %s %s (push_allowed=%s)" % (
        al_icon, audit_status, audit.get("push_allowed", "unknown")))
    lines.append("")

    # PR
    pr = result.get("pr_summary", {})
    if pr.get("number"):
        lines.append("## Latest PR")
        lines.append("- #%s: %s" % (pr["number"], pr.get("title", "")[:60]))
        lines.append("- Merged: %s" % pr.get("merged_at", "")[:19])
        lines.append("- Commit: `%s`" % pr.get("merge_commit", ""))
        lines.append("")

    # V1 Freeze
    v1f = result.get("v1_freeze", {})
    v1f_verdict = v1f.get("verdict", "N/A")
    v1f_icon = {"PASS": "✅", "WARN": "⚠️", "BLOCK": "❌"}.get(v1f_verdict, "❓")
    lines.append("## V1 Freeze")
    lines.append("- %s %s" % (v1f_icon, v1f_verdict))
    lines.append("")

    # Next
    lines.append("## 下一步")
    lines.append(result.get("next_recommended_action", "unknown"))
    lines.append("")

    lines.append("---")
    lines.append("*%s*" % result.get("operator_summary", ""))

    return "\n".join(lines)


def _format_compact(result):
    """Format as compact one-liner."""
    qg = result.get("quality_gate", {}).get("verdict", "?")
    smoke = result.get("smoke_status", "?")
    audit = result.get("audit_lock", {}).get("audit_status", "?")
    baseline = result.get("baseline", {}).get("short", "?")
    pr = result.get("pr_summary", {})
    pr_str = "#%s" % pr.get("number", "?") if pr.get("number") else "none"
    v1f = result.get("v1_freeze", {}).get("verdict", "?")
    return "QG:%s Smoke:%s Audit:%s Baseline:%s PR:%s V1:%s | %s" % (
        qg, smoke, audit, baseline, pr_str, v1f, result.get("operator_summary", "")[:60])


def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Run Report / Session Handoff — execution summary for QQ/mobile"
    )
    parser.add_argument("--version", action="version", version="vibe_run_report %s" % VERSION)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--markdown", action="store_true", help="Output as Markdown (default)")
    parser.add_argument("--compact", action="store_true", help="Compact one-liner output")
    parser.add_argument("--repo-root", help="Repository root (default: cwd)")
    parser.add_argument("--jobs-dir", help="Jobs directory (default: ~/vibedev/jobs)")
    return parser


def main(argv=None):
    """Main entry point (import-safe)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    result = run_report(
        repo_root=args.repo_root or Path(__file__).parent.parent,
        jobs_dir=args.jobs_dir,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.compact:
        print(_format_compact(result))
    else:
        # Default: markdown
        print(_format_markdown(result))

    return 0


if __name__ == "__main__":
    sys.exit(main())
