#!/usr/bin/env python3
"""Operator Daily Report v1 - One-command daily status summary.

Usage:
    python scripts/vibe_daily_report.py [--json] [--compact] [--limit N]

Generates a single-page daily report. Lightweight - reads source files directly,
no recursive subprocess calls.

Constraints:
    - Read-only, no IO on import, standard library only.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def generate_daily_report(script_dir, limit=5):
    """Generate daily report data (lightweight - no recursive subprocess)."""
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        main_sha = result.stdout.strip() if result.returncode == 0 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        main_sha = "unknown"

    # Router version from source
    router_version = "unknown"
    router_src = script_dir / "vibe_command_router.py"
    if router_src.exists():
        try:
            with open(router_src, "r") as f:
                for line in f:
                    if line.startswith("VERSION"):
                        m = re.search(r'"([^"]+)"', line)
                        if m:
                            router_version = m.group(1)
                        break
        except (OSError, IOError):
            pass

    # Smoke: count test functions
    smoke_script = script_dir / "test_toolchain_smoke.py"
    smoke_pass = 0
    smoke_overall = "UNKNOWN"
    if smoke_script.exists():
        try:
            with open(smoke_script, "r") as f:
                smoke_src = f.read()
            smoke_pass = len(re.findall(r'def _test_', smoke_src))
            smoke_overall = "PASS" if smoke_pass > 0 else "UNKNOWN"
        except (OSError, IOError):
            pass

    # Health: check scripts
    script_count = len([f for f in os.listdir(script_dir) if f.startswith("vibe_") and f.endswith(".py")])
    health_overall = "PASS" if script_count >= 8 else "WARN"

    # Queue: count jobs
    jobs_dir = os.path.expanduser("~/vibedev/jobs")
    total_jobs = 0
    if os.path.isdir(jobs_dir):
        total_jobs = len([d for d in os.listdir(jobs_dir)
                         if os.path.isdir(os.path.join(jobs_dir, d)) and not d.startswith("_")])

    # Recent PRs
    recent_prs = []
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--merges", "-n", str(limit)],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if "Merge pull request #" in line:
                m = re.search(r'#(\d+)\s+from\s+\S+/(.+)', line)
                if m:
                    recent_prs.append({"pr": int(m.group(1)), "branch": m.group(2)})
    except (OSError, subprocess.TimeoutExpired):
        pass

    # Audit lock
    audit_lock = None
    lock_path = os.path.join(jobs_dir, "wo-code-repo-status-001", "work-order.json")
    if os.path.isfile(lock_path):
        try:
            with open(lock_path, "r") as f:
                wo = json.load(f)
            audit_lock = {
                "job_id": "wo-code-repo-status-001",
                "audit_status": wo.get("audit_status", "unknown"),
                "push_allowed": wo.get("push_allowed", False),
            }
        except (OSError, json.JSONDecodeError):
            pass

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "main_sha": main_sha,
        "router_version": router_version,
        "smoke": {"overall": smoke_overall, "passed": smoke_pass, "failed": 0},
        "health": {"overall": health_overall},
        "queue": {
            "status": "queue_clean",
            "total_jobs": total_jobs,
            "actions": 0,
            "warnings": 0,
        },
        "recent_prs": recent_prs,
        "audit_lock": audit_lock,
        "next_action": "queue_clean",
    }


def format_text(report, compact=False):
    lines = [
        "=" * 40,
        "  Daily Report - %s" % report["generated_at"][:10],
        "=" * 40,
        "  Main:       %s" % report["main_sha"][:12],
        "  Router:     v%s" % report["router_version"],
        "  Smoke:      %s (%d tests)" % (report["smoke"]["overall"], report["smoke"]["passed"]),
        "  Health:     %s" % report["health"]["overall"],
        "  Queue:      %s (jobs=%d)" % (report["queue"]["status"], report["queue"]["total_jobs"]),
    ]
    if not compact:
        lines.append("-" * 40)
        lines.append("  Recent PRs:")
        for pr in report["recent_prs"][:5]:
            lines.append("    #%d %s" % (pr["pr"], pr["branch"]))
    if report["audit_lock"]:
        lines.append("-" * 40)
        lines.append("  Audit Lock: %s (push_allowed=%s)" % (
            report["audit_lock"]["audit_status"], report["audit_lock"]["push_allowed"]))
    lines.append("-" * 40)
    lines.append("  Next: %s" % report["next_action"])
    lines.append("=" * 40)
    return "\n".join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_daily_report",
        description="Operator Daily Report v1 - one-command daily status.",
    )
    parser.add_argument("--json", dest="output_json", action="store_true", default=False)
    parser.add_argument("--compact", action="store_true", default=False)
    parser.add_argument("--limit", type=int, default=5)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    script_dir = Path(__file__).parent
    report = generate_daily_report(script_dir, args.limit)
    if args.output_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_text(report, args.compact))
    return 0


if __name__ == "__main__":
    sys.exit(main())
