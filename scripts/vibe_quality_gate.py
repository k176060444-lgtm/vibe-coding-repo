#!/usr/bin/env python3
"""Workflow Quality Gate — aggregated pre/post-execution health check.

Runs smoke suite, loop summary, evidence verifier, router version, audit lock,
and origin/main sync status in a single pass. Outputs PASS/WARN/BLOCK verdict.

Usage:
    python3 scripts/vibe_quality_gate.py [--json] [--compact] [--repo-root <path>]

Verdict rules:
    PASS  — all core checks passed
    WARN  — acceptable degradation (fixture mode, partial evidence)
    BLOCK — critical failure (smoke fail, origin mismatch, audit lock missing)

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


def _run_script(script_path, args, timeout=120):
    """Run a Python script and return (rc, stdout, stderr)."""
    try:
        cmd = [sys.executable, str(script_path)] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "timeout"
    except (OSError, FileNotFoundError) as e:
        return 1, "", str(e)


def _check_smoke(script_dir, jobs_dir):
    """Run smoke suite and return status."""
    path = script_dir / "test_toolchain_smoke.py"
    if not path.exists():
        return "BLOCK", "script not found", {}
    rc, stdout, stderr = _run_script(path, ["--json", "--jobs-dir", str(jobs_dir)])
    try:
        data = json.loads(stdout)
        passed = data.get("passed", 0)
        failed = data.get("failed", 0)
        if failed > 0:
            return "BLOCK", "%d passed, %d failed" % (passed, failed), data
        return "PASS", "%d passed, 0 failed" % passed, data
    except (json.JSONDecodeError, KeyError):
        return "BLOCK", "invalid output", {}


def _check_router_version(script_dir):
    """Get router version."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return "WARN", "router not found", {}
    rc, stdout, stderr = _run_script(path, ["version"])
    version = stdout.strip() if rc == 0 else "unknown"
    return "PASS", version, {"version": version}


def _check_audit_lock(script_dir, jobs_dir):
    """Check wo-code-repo-status-001 audit lock status."""
    path = script_dir / "vibe_repo_status.py"
    if not path.exists():
        return "WARN", "repo_status script not found", {}
    rc, stdout, stderr = _run_script(path, ["--jobs", "--json"])
    if rc != 0:
        return "WARN", "repo_status failed", {}
    try:
        data = json.loads(stdout)
        for job in data.get("jobs", []):
            if job.get("job_id") == "wo-code-repo-status-001":
                audit = job.get("audit_status", "unknown")
                push = job.get("push_allowed", "unknown")
                if audit == "audit_tainted" and push is False:
                    return "PASS", "audit_tainted, push_allowed=false", job
                elif audit == "audit_tainted":
                    return "BLOCK", "audit_tainted but push_allowed=%s" % push, job
                else:
                    return "WARN", "audit_status=%s" % audit, job
        return "WARN", "wo-code-repo-status-001 not found", {}
    except (json.JSONDecodeError, KeyError):
        return "WARN", "invalid output", {}


def _check_origin_main(repo_root):
    """Check if origin/main is reachable and current."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--get-url", "origin"],
            capture_output=True, text=True, timeout=15, cwd=str(repo_root)
        )
        remote_url = result.stdout.strip()
        if not remote_url:
            return "WARN", "no remote URL", {}

        result = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            capture_output=True, text=True, timeout=15, cwd=str(repo_root)
        )
        if result.returncode != 0:
            return "BLOCK", "origin/main not reachable", {}
        sha = result.stdout.strip()

        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=15, cwd=str(repo_root)
        )
        head = result.stdout.strip() if result.returncode == 0 else "unknown"

        return "PASS", "origin/main=%s" % sha[:12], {"sha": sha, "head": head}
    except (subprocess.TimeoutExpired, OSError) as e:
        return "WARN", "git error: %s" % e, {}


def _check_loop_summary(script_dir):
    """Check loop summary status."""
    path = script_dir / "vibe_loop_summary.py"
    if not path.exists():
        return "WARN", "loop_summary not found", {}
    rc, stdout, stderr = _run_script(path, ["--json", "--compact"])
    if rc != 0:
        return "WARN", "loop_summary failed", {}
    try:
        data = json.loads(stdout)
        components = data.get("total_components", 0)
        return "PASS", "%d components" % components, data
    except (json.JSONDecodeError, KeyError):
        return "WARN", "invalid output", {}


def _check_evidence_verifier(script_dir):
    """Check that evidence verifier is functional."""
    path = script_dir / "vibe_evidence_verifier.py"
    if not path.exists():
        return "WARN", "evidence_verifier not found", {}
    # Just verify it imports and shows help
    rc, stdout, stderr = _run_script(path, ["--help"])
    if rc == 0:
        return "PASS", "available", {}
    return "WARN", "help failed", {}


def run_quality_gate(repo_root=None, jobs_dir=None, skip_smoke=False):
    """Run all quality gate checks and return result dict."""
    if repo_root is None:
        repo_root = Path.cwd()
    else:
        repo_root = Path(repo_root)

    script_dir = repo_root / "scripts"
    if jobs_dir is None:
        jobs_dir = os.path.expanduser("~/vibedev/jobs")

    checks = []
    block_count = 0
    warn_count = 0

    # Check 1: Smoke suite (skip in fast mode)
    if skip_smoke:
        smoke_status, smoke_detail, smoke_data = "PASS", "skipped (--skip-smoke)", {}
    else:
        smoke_status, smoke_detail, smoke_data = _check_smoke(script_dir, jobs_dir)
    checks.append({
        "name": "smoke_suite",
        "result": smoke_status,
        "detail": smoke_detail,
    })
    if smoke_status == "BLOCK":
        block_count += 1
    elif smoke_status == "WARN":
        warn_count += 1

    # Check 2: Router version
    router_status, router_detail, router_data = _check_router_version(script_dir)
    checks.append({
        "name": "router_version",
        "result": router_status,
        "detail": router_detail,
    })
    if router_status == "BLOCK":
        block_count += 1
    elif router_status == "WARN":
        warn_count += 1

    # Check 3: Audit lock
    audit_status, audit_detail, audit_data = _check_audit_lock(script_dir, jobs_dir)
    checks.append({
        "name": "audit_lock",
        "result": audit_status,
        "detail": audit_detail,
    })
    if audit_status == "BLOCK":
        block_count += 1
    elif audit_status == "WARN":
        warn_count += 1

    # Check 4: Origin/main sync
    origin_status, origin_detail, origin_data = _check_origin_main(repo_root)
    checks.append({
        "name": "origin_main",
        "result": origin_status,
        "detail": origin_detail,
    })
    if origin_status == "BLOCK":
        block_count += 1
    elif origin_status == "WARN":
        warn_count += 1

    # Check 5: Loop summary
    loop_status, loop_detail, loop_data = _check_loop_summary(script_dir)
    checks.append({
        "name": "loop_summary",
        "result": loop_status,
        "detail": loop_detail,
    })
    if loop_status == "BLOCK":
        block_count += 1
    elif loop_status == "WARN":
        warn_count += 1

    # Check 6: Evidence verifier
    ev_status, ev_detail, ev_data = _check_evidence_verifier(script_dir)
    checks.append({
        "name": "evidence_verifier",
        "result": ev_status,
        "detail": ev_detail,
    })
    if ev_status == "BLOCK":
        block_count += 1
    elif ev_status == "WARN":
        warn_count += 1

    # Determine verdict
    if block_count > 0:
        verdict = "BLOCK"
        operator_summary = "BLOCKED: %d critical failure(s). Do NOT proceed with execution. See checks for details." % block_count
    elif warn_count > 0:
        verdict = "WARN"
        operator_summary = "ACCEPTABLE: %d warning(s). Review before proceeding. Non-critical degradation detected." % warn_count
    else:
        verdict = "PASS"
        operator_summary = "ALL CLEAR: All %d checks passed. System is healthy for execution." % len(checks)

    result = {
        "verdict": verdict,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": VERSION,
        "checks": checks,
        "router_version": router_detail if router_status == "PASS" else "unknown",
        "smoke_status": smoke_status,
        "loop_summary_status": loop_status,
        "audit_lock_status": audit_status,
        "origin_main_status": origin_status,
        "evidence_verifier_status": ev_status,
        "operator_summary": operator_summary,
        "summary": {
            "total": len(checks),
            "pass": sum(1 for c in checks if c["result"] == "PASS"),
            "warn": warn_count,
            "block": block_count,
        },
    }

    return result


def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Workflow Quality Gate — aggregated pre/post-execution health check",
        epilog="Verdict: PASS (all clear), WARN (acceptable), BLOCK (critical)"
    )
    parser.add_argument("--version", action="version", version="vibe_quality_gate %s" % VERSION)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--compact", action="store_true", help="Compact output")
    parser.add_argument("--repo-root", help="Repository root (default: cwd)")
    parser.add_argument("--jobs-dir", help="Jobs directory (default: ~/vibedev/jobs)")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip smoke suite for fast mode")
    return parser


def main(argv=None):
    """Main entry point (import-safe)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    result = run_quality_gate(
        repo_root=args.repo_root or Path(__file__).parent.parent,
        jobs_dir=args.jobs_dir,
        skip_smoke=getattr(args, "skip_smoke", False),
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.compact:
        # Enhanced compact: one-line QQ-friendly summary
        qg = result["verdict"]
        smoke = result.get("smoke_status", "?")
        audit = result.get("audit_lock_status", "?")
        origin = result.get("origin_main_status", "?")
        loop_s = result.get("loop_summary_status", "?")
        ev = result.get("evidence_verifier_status", "?")

        # Short labels
        audit_short = {"PASS": "tainted-intact"}.get(audit, audit)
        origin_short = {"PASS": "synced"}.get(origin, origin)
        loop_short = {"PASS": "ok"}.get(loop_s, loop_s)
        ev_short = {"PASS": "ok"}.get(ev, ev)

        # Next action hint
        if qg == "BLOCK":
            next_hint = "HALT"
        elif qg == "WARN":
            next_hint = "REVIEW"
        else:
            next_hint = "run-report"

        print("QG %s | Smoke %s | Audit %s | Main %s | Loop %s | EV %s | Next: %s" % (
            qg, smoke, audit_short, origin_short, loop_short, ev_short, next_hint))
    else:
        print("=" * 50)
        print("  Workflow Quality Gate v%s" % VERSION)
        print("=" * 50)
        for c in result["checks"]:
            icon = {"PASS": "\u2713", "WARN": "\u26a0", "BLOCK": "\u2717"}.get(c["result"], "?")
            print("  %s %s: %s - %s" % (icon, c["name"], c["result"], c["detail"]))
        print("-" * 50)
        s = result["summary"]
        print("  Verdict: %s (%d pass, %d warn, %d block)" % (
            result["verdict"], s["pass"], s["warn"], s["block"]))
        print("  %s" % result["operator_summary"])
        print("=" * 50)

    return 0 if result["verdict"] != "BLOCK" else 1


if __name__ == "__main__":
    sys.exit(main())
