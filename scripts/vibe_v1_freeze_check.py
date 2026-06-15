#!/usr/bin/env python3
"""V1 Freeze Check — verify V1 operational freeze is healthy.

Read-only check that verifies the current repository state matches
the V1 operational freeze requirements.

Usage:
    python3 scripts/vibe_v1_freeze_check.py [--json] [--compact]

Checks:
    - quality-gate PASS
    - run-report available
    - smoke test count >= 75
    - router has required commands (quality-gate, run-report)
    - audit lock intact (wo-code-repo-status-001: audit_tainted, push_allowed=false)
    - origin/main reachable
    - Level 5 not activated (documented)
    - wrapper requirement documented

Constraints:
    - Read-only, no file modifications, standard library only.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

VERSION = "1.0.0"


def _run_script(script_path, args, timeout=60):
    try:
        cmd = [sys.executable, str(script_path)] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "timeout"
    except (OSError, FileNotFoundError) as e:
        return 1, "", str(e)


def _check_quality_gate(script_dir, repo_root):
    path = script_dir / "vibe_quality_gate.py"
    if not path.exists():
        return "BLOCK", "script not found"
    rc, stdout, stderr = _run_script(path, ["--json", "--skip-smoke", "--repo-root", str(repo_root)])
    try:
        data = json.loads(stdout)
        return data.get("verdict", "BLOCK"), "verdict=%s" % data.get("verdict")
    except (json.JSONDecodeError, KeyError):
        return "BLOCK", "invalid output"


def _check_run_report(script_dir, repo_root):
    path = script_dir / "vibe_run_report.py"
    if not path.exists():
        return "BLOCK", "script not found"
    rc, stdout, stderr = _run_script(path, ["--json", "--repo-root", str(repo_root)])
    try:
        data = json.loads(stdout)
        if "operator_summary" in data:
            return "PASS", "available"
        return "WARN", "missing operator_summary"
    except (json.JSONDecodeError, KeyError):
        return "BLOCK", "invalid output"


def _check_smoke_count(script_dir):
    path = script_dir / "test_toolchain_smoke.py"
    if not path.exists():
        return "BLOCK", "script not found"
    content = path.read_text()
    count = content.count("def _test_")
    if count >= 75:
        return "PASS", "%d tests" % count
    elif count >= 70:
        return "WARN", "%d tests (expected >= 75)" % count
    return "BLOCK", "%d tests (too few)" % count


def _check_router_commands(script_dir):
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return "BLOCK", "router not found"
    content = path.read_text()
    required = ["quality-gate", "run-report", "qg", "rr", "handoff", "go-no-go"]
    missing = [cmd for cmd in required if '"%s"' % cmd not in content]
    if not missing:
        return "PASS", "all %d commands/aliases present" % len(required)
    return "BLOCK", "missing: %s" % ", ".join(missing)


def _check_audit_lock(script_dir):
    path = script_dir / "vibe_repo_status.py"
    if not path.exists():
        return "WARN", "repo_status not found"
    rc, stdout, stderr = _run_script(path, ["--jobs", "--json"])
    try:
        data = json.loads(stdout)
        for job in data.get("jobs", []):
            if job.get("job_id") == "wo-code-repo-status-001":
                audit = job.get("audit_status", "unknown")
                push = job.get("push_allowed", "unknown")
                if audit == "audit_tainted" and push is False:
                    return "PASS", "audit_tainted, push_allowed=false"
                return "BLOCK", "audit=%s push=%s" % (audit, push)
        return "BLOCK", "wo-code-repo-status-001 not found"
    except (json.JSONDecodeError, KeyError):
        return "WARN", "invalid output"


def _check_origin_main(repo_root):
    try:
        result = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            capture_output=True, text=True, timeout=15, cwd=str(repo_root)
        )
        if result.returncode == 0:
            sha = result.stdout.strip()
            return "PASS", "origin/main=%s" % sha[:12]
        return "BLOCK", "origin/main not reachable"
    except (subprocess.TimeoutExpired, OSError) as e:
        return "BLOCK", str(e)


def _check_level5_not_activated(repo_root):
    freeze_doc = repo_root / "docs" / "V1_OPERATIONAL_FREEZE.md"
    if not freeze_doc.exists():
        return "WARN", "V1_OPERATIONAL_FREEZE.md not found"
    content = freeze_doc.read_text()
    if "NOT ACTIVATED" in content and "Level 5" in content:
        return "PASS", "Level 5 NOT ACTIVATED (documented)"
    return "WARN", "Level 5 status unclear"


def _check_wrapper_documented(repo_root):
    freeze_doc = repo_root / "docs" / "V1_OPERATIONAL_FREEZE.md"
    if not freeze_doc.exists():
        return "WARN", "V1_OPERATIONAL_FREEZE.md not found"
    content = freeze_doc.read_text()
    if "vibe_autonomous_merge" in content and "FORBIDDEN" in content:
        return "PASS", "wrapper requirement documented"
    return "WARN", "wrapper requirement not fully documented"


def run_v1_freeze_check(repo_root=None, jobs_dir=None):
    if repo_root is None:
        repo_root = Path.cwd()
    else:
        repo_root = Path(repo_root)

    script_dir = repo_root / "scripts"

    checks = []
    block_count = 0
    warn_count = 0

    check_fns = [
        ("quality_gate", lambda: _check_quality_gate(script_dir, repo_root)),
        ("run_report", lambda: _check_run_report(script_dir, repo_root)),
        ("smoke_count", lambda: _check_smoke_count(script_dir)),
        ("router_commands", lambda: _check_router_commands(script_dir)),
        ("audit_lock", lambda: _check_audit_lock(script_dir)),
        ("origin_main", lambda: _check_origin_main(repo_root)),
        ("level5_not_activated", lambda: _check_level5_not_activated(repo_root)),
        ("wrapper_documented", lambda: _check_wrapper_documented(repo_root)),
    ]

    for name, fn in check_fns:
        status, detail = fn()
        checks.append({"name": name, "result": status, "detail": detail})
        if status == "BLOCK":
            block_count += 1
        elif status == "WARN":
            warn_count += 1

    if block_count > 0:
        verdict = "BLOCK"
        summary = "V1 FREEZE BROKEN: %d critical issue(s). Fix before proceeding." % block_count
    elif warn_count > 0:
        verdict = "WARN"
        summary = "V1 FREEZE WARNING: %d non-critical issue(s). Review recommended." % warn_count
    else:
        verdict = "PASS"
        summary = "V1 OPERATIONAL FREEZE INTACT: All %d checks passed." % len(checks)

    return {
        "verdict": verdict,
        "version": VERSION,
        "checks": checks,
        "operator_summary": summary,
        "summary": {
            "total": len(checks),
            "pass": sum(1 for c in checks if c["result"] == "PASS"),
            "warn": warn_count,
            "block": block_count,
        },
    }


def build_parser():
    parser = argparse.ArgumentParser(
        description="V1 Freeze Check — verify operational freeze is healthy"
    )
    parser.add_argument("--version", action="version", version="vibe_v1_freeze_check %s" % VERSION)
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--compact", action="store_true", help="Compact output")
    parser.add_argument("--repo-root", help="Repository root")
    parser.add_argument("--jobs-dir", help="Jobs directory")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    result = run_v1_freeze_check(
        repo_root=args.repo_root or Path(__file__).parent.parent,
        jobs_dir=args.jobs_dir,
    )

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif args.compact:
        checks_str = " ".join(
            "%s:%s" % (c["name"].replace("_", "-"), c["result"])
            for c in result["checks"]
        )
        print("%s | %s" % (result["verdict"], checks_str))
        print(result["operator_summary"])
    else:
        print("=" * 50)
        print("  V1 Freeze Check v%s" % VERSION)
        print("=" * 50)
        for c in result["checks"]:
            icon = {"PASS": "\u2713", "WARN": "\u26a0", "BLOCK": "\u2717"}.get(c["result"], "?")
            print("  %s %s: %s - %s" % (icon, c["name"], c["result"], c["detail"]))
        print("-" * 50)
        s = result["summary"]
        print("  Verdict: %s (%d pass, %d warn, %d block)" % (
            result["verdict"], s["pass"], s["warn"], s["block"]))
        print("  %s" % result["operator_summary"])

    return 0 if result["verdict"] != "BLOCK" else 1


if __name__ == "__main__":
    sys.exit(main())
