#!/usr/bin/env python3
"""Autonomous Merge Gate v1 - Pre-merge verification for vibedev Hermes.

Usage:
    python scripts/vibe_merge_gate.py --repo <owner/repo> --pr <number> \
        --expected-base-sha <sha> --expected-head-sha <sha> \
        --allowed-path <path> [--allowed-path <path2> ...] \
        [--jobs-dir <dir>] [--job-id <id>] [--json]

Constraints:
    - Read-only operations only.
    - No merge/push/delete.
    - No secrets/keys read.
    - No file modifications.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
try:
    from vibe_toolchain_lifecycle import gate_check_for_dispatch
    _LIFECYCLE_GATE_AVAILABLE = True
except ImportError:
    gate_check_for_dispatch = None
    _LIFECYCLE_GATE_AVAILABLE = False

# V1.20.8: Model ledger gate integration
try:
    from model_ledger_gate import validate_report as ledger_gate_validate
    _LEDGER_GATE_AVAILABLE = True
except ImportError:
    ledger_gate_validate = None
    _LEDGER_GATE_AVAILABLE = False

# V1.20.10: Operator merge approval gate
try:
    from operator_merge_approval_gate import validate_approval as operator_validate_approval
    _OPERATOR_APPROVAL_GATE_AVAILABLE = True
except ImportError:
    operator_validate_approval = None
    _OPERATOR_APPROVAL_GATE_AVAILABLE = False


def _run_cmd(*args, check=False):
    """Run a command and return (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            list(args),
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except FileNotFoundError:
        return "", f"Command not found: {args[0]}", 127


def _run_gh(*args):
    """Run gh CLI and return parsed JSON or None."""
    cmd = ["gh"] + list(args)
    stdout, stderr, rc = _run_cmd(*cmd)
    if rc != 0:
        return None, stderr
    try:
        return json.loads(stdout), None
    except json.JSONDecodeError:
        return stdout, None


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

    wo = _read_json_file(job_path / "work-order.json")
    if not wo:
        return {
            "job_id": job_id,
            "job_status": "unknown",
            "audit_status": "unknown",
            "push_allowed": False,
            "error": "missing_work_order",
        }

    state = _read_json_file(job_path / "state.json")

    job_status = "unknown"
    if state and "status" in state:
        job_status = state["status"]
    elif "status" in wo:
        job_status = wo["status"]

    audit_status = wo.get("audit_status", "clean")
    push_allowed = wo.get("push_allowed", wo.get("allow_push", False))
    if audit_status == "audit_tainted":
        push_allowed = False

    return {
        "job_id": job_id,
        "job_status": job_status,
        "audit_status": audit_status,
        "push_allowed": push_allowed,
    }


def _check_pr(repo, pr_number):
    """Check PR status via gh CLI."""
    pr_data, err = _run_gh(
        "pr", "view", str(pr_number),
        "-R", repo,
        "--json", "number,title,state,headRefName,baseRefName,headRefOid,mergeable,changedFiles,statusCheckRollup,url"
    )
    if pr_data is None:
        return None, f"Failed to read PR #{pr_number}: {err}"
    return pr_data, None


def _check_main_sha(repo):
    """Check current main SHA via git ls-remote."""
    stdout, stderr, rc = _run_cmd(
        "git", "ls-remote", f"git@github.com:{repo}.git", "refs/heads/main"
    )
    if rc != 0:
        return None, f"Failed to read main SHA: {stderr}"
    parts = stdout.split()
    if len(parts) >= 1:
        return parts[0], None
    return None, "No main SHA found"


def run_gate(args):
    """Run the merge gate checks."""
    blockers = []
    warnings = []

    # Lifecycle gate check (V1.17.5 fail-closed)
    if not _LIFECYCLE_GATE_AVAILABLE:
        blockers.append("lifecycle gate import failed")
        return _build_result(False, blockers, warnings, {}, {}, {})
    _lg = gate_check_for_dispatch()
    if not _lg.get("allowed"):
        blockers.append(f"lifecycle gate: {_lg.get('reason', 'unknown')} {_lg.get('detail', '')}")
        return _build_result(False, blockers, warnings, {}, {}, {})
    pr_info = {}
    job_info = {}
    checks_info = {}

    # 1. Check PR
    pr_data, err = _check_pr(args.repo, args.pr)
    if pr_data is None:
        blockers.append(f"PR not accessible: {err}")
        return _build_result(False, blockers, warnings, pr_info, job_info, checks_info)

    pr_info = {
        "number": pr_data.get("number"),
        "title": pr_data.get("title"),
        "state": pr_data.get("state"),
        "head_ref": pr_data.get("headRefName"),
        "base_ref": pr_data.get("baseRefName"),
        "head_sha": pr_data.get("headRefOid"),
        "mergeable": pr_data.get("mergeable"),
        "changed_files": pr_data.get("changedFiles"),
        "url": pr_data.get("url"),
    }

    # Check PR is open
    if pr_data.get("state") != "OPEN":
        blockers.append(f"PR state is {pr_data.get('state')}, not OPEN")

    # Check base branch
    if pr_data.get("baseRefName") != "main":
        blockers.append(f"Base branch is {pr_data.get('baseRefName')}, not main")

    # 2. Check main SHA
    current_main_sha, err = _check_main_sha(args.repo)
    if current_main_sha is None:
        blockers.append(f"Cannot read main SHA: {err}")
    elif current_main_sha != args.expected_base_sha:
        blockers.append(f"Main SHA mismatch: expected {args.expected_base_sha[:12]}, got {current_main_sha[:12]}")

    # 3. Check head SHA
    if pr_data.get("headRefOid") != args.expected_head_sha:
        blockers.append(f"Head SHA mismatch: expected {args.expected_head_sha[:12]}, got {pr_data.get('headRefOid', 'N/A')[:12]}")

    # 4. Check changed files
    # Note: We can't easily get file list from gh pr view, so we check changedFiles count
    # For detailed file check, we'd need gh pr diff or API
    pr_diff_stdout, _, _ = _run_cmd(
        "gh", "pr", "diff", str(args.pr),
        "-R", args.repo,
        "--name-only"
    )
    changed_paths = [p.strip() for p in pr_diff_stdout.splitlines() if p.strip()]
    pr_info["changed_paths"] = changed_paths

    if args.allowed_path:
        allowed = set(args.allowed_path)
        for path in changed_paths:
            if path not in allowed:
                blockers.append(f"Changed path not in allowed list: {path}")

    # 5. Check mergeable
    mergeable = pr_data.get("mergeable", "UNKNOWN")
    if mergeable not in ("MERGEABLE", "CLEAN", "UNKNOWN"):
        blockers.append(f"PR not mergeable: {mergeable}")
    elif mergeable == "UNKNOWN":
        warnings.append("Mergeable status unknown")

    # 6. Check checks
    checks = pr_data.get("statusCheckRollup", [])
    if not checks:
        checks_info = {"status": "no_checks_found", "count": 0}
        warnings.append("No checks found")
    else:
        failed = [c for c in checks if c.get("conclusion") == "FAILURE" or c.get("status") == "FAILURE"]
        checks_info = {
            "status": "failure" if failed else "success",
            "count": len(checks),
            "failed": len(failed),
        }
        if failed:
            blockers.append(f"{len(failed)} check(s) failed")

    # 7. Check job registry (if provided)
    if args.job_id:
        jobs_dir = (
            args.jobs_dir
            or os.environ.get("VIBEDEV_JOBS_DIR")
            or os.path.expanduser("~/vibedev/jobs")
        )
        job_path = Path(jobs_dir) / args.job_id
        if not job_path.exists():
            blockers.append(f"Job {args.job_id} not found in {jobs_dir}")
        else:
            info = _collect_job_info(job_path)
            job_info = info

            if info.get("job_status") != "review_passed":
                blockers.append(f"Job status is {info.get('job_status')}, not review_passed")

            if info.get("audit_status") != "clean":
                blockers.append(f"Job audit_status is {info.get('audit_status')}, not clean")

    # 8. Check locked job (always)
    jobs_dir = (
        args.jobs_dir
        or os.environ.get("VIBEDEV_JOBS_DIR")
        or os.path.expanduser("~/vibedev/jobs")
    )
    locked_job_path = Path(jobs_dir) / "wo-code-repo-status-001"
    if locked_job_path.exists():
        locked_info = _collect_job_info(locked_job_path)
        if locked_info.get("audit_status") != "audit_tainted":
            blockers.append("Locked job wo-code-repo-status-001 audit_status changed!")
        if locked_info.get("push_allowed") != False:
            blockers.append("Locked job wo-code-repo-status-001 push_allowed changed!")
    else:
        warnings.append("Locked job wo-code-repo-status-001 not found")

    # V1.20.8: Model ledger gate check — FAIL-CLOSED
    # merge_ready=true REQUIRES model_ledger_gate.result=PASS
    # N/A, GATE_UNAVAILABLE, missing report-file all BLOCK merge
    ledger_gate_result = None
    if not _LEDGER_GATE_AVAILABLE:
        ledger_gate_result = {'checked': False, 'result': 'GATE_UNAVAILABLE'}
        blockers.append('Model ledger gate UNAVAILABLE: cannot validate merge readiness')
    else:
        report_file = getattr(args, 'report_file', None)
        gate_report = None
        gate_error_detail = None

        # 1. Require --report-file and valid JSON with status
        if not report_file:
            gate_error_detail = 'no --report-file provided'
        else:
            rf_path = Path(report_file)
            if not rf_path.exists():
                gate_error_detail = f'report file not found: {report_file}'
            elif not rf_path.is_file():
                gate_error_detail = f'report file is not a file: {report_file}'
            else:
                rf = _read_json_file(rf_path)
                if rf is None:
                    gate_error_detail = f'report file is not valid JSON: {report_file}'
                else:
                    gate_report = rf
                    if 'status' not in gate_report:
                        gate_error_detail = 'report file missing status field'

        # 2. Check terminal status FIRST (before ledger field checks)
        terminal_statuses = {'PASS', 'MERGE_READY', 'FREEZE_PASS', 'PROMOTION_PASS'}
        is_non_terminal = False
        if not gate_error_detail and gate_report is not None:
            status = str(gate_report.get('status', '')).upper()
            if status not in terminal_statuses:
                is_non_terminal = True
                ledger_gate_result = {
                    'checked': False,
                    'result': 'N/A',
                    'reason': f'non-terminal status: {status}',
                }
                blockers.append(
                    f'Merge readiness gate: non-terminal status "{status}", cannot confirm ledger validity')

        # 3. For terminal status, validate ledger fields
        if not gate_error_detail and not is_non_terminal and gate_report is not None:
            if not gate_report.get('MODEL_LEDGER'):
                gate_error_detail = 'report file missing MODEL_LEDGER'
            elif not gate_report.get('NODE_MODEL_SUMMARY'):
                gate_error_detail = 'report file missing NODE_MODEL_SUMMARY'
            elif not gate_report.get('COOLDOWN_STATE_SUMMARY'):
                gate_error_detail = 'report file missing COOLDOWN_STATE_SUMMARY'

        # 4. If any error -> fail-closed
        if gate_error_detail and not is_non_terminal:
            ledger_gate_result = {
                'checked': False,
                'result': 'FAIL',
                'errors': [f'Merge readiness gate: {gate_error_detail}'],
            }
            blockers.append(f'Merge readiness gate FAIL: {gate_error_detail}')
        elif not gate_error_detail and not is_non_terminal and gate_report is not None:
            # 5. All fields present, terminal status: validate
            ledger_errors = ledger_gate_validate(gate_report)
            ledger_gate_result = {
                'checked': True,
                'result': 'PASS' if not ledger_errors else 'FAIL',
                'errors': ledger_errors,
            }
            if ledger_errors:
                blockers.append('Model ledger gate FAIL: ' + '; '.join(ledger_errors[:3]))

    # V1.20.10: Operator merge approval check -- FAIL-CLOSED
    operator_approval_result = None
    if not _OPERATOR_APPROVAL_GATE_AVAILABLE:
        operator_approval_result = {'checked': False, 'result': 'BLOCKED', 'errors': ['operator_merge_approval_gate not importable']}
        blockers.append('Operator merge approval gate UNAVAILABLE: cannot validate merge approval')
    else:
        approval_file = getattr(args, 'approval_file', None)
        merge_method = getattr(args, 'merge_method', None)
        if not approval_file:
            operator_approval_result = {'checked': True, 'result': 'BLOCKED', 'errors': ['no --approval-file provided']}
            blockers.append('Operator merge approval FAIL: no --approval-file provided')
        elif not merge_method:
            operator_approval_result = {'checked': True, 'result': 'BLOCKED', 'errors': ['no --merge-method provided']}
            blockers.append('Operator merge approval FAIL: no --merge-method provided')
        else:
            af_path = Path(approval_file)
            if not af_path.exists():
                operator_approval_result = {'checked': True, 'result': 'BLOCKED', 'errors': ['approval file not found']}
                blockers.append(f'Operator merge approval FAIL: approval file not found: {approval_file}')
            else:
                af = _read_json_file(af_path)
                if af is None:
                    operator_approval_result = {'checked': True, 'result': 'BLOCKED', 'errors': ['approval file is not valid JSON']}
                    blockers.append('Operator merge approval FAIL: approval file is not valid JSON')
                else:
                    expected_pr = getattr(args, 'pr', None)
                    expected_head = getattr(args, 'expected_head_sha', None)
                    expected_base = getattr(args, 'expected_base_sha', None)
                    merge_method = getattr(args, 'merge_method', None)
                    operator_approval_result = operator_validate_approval(
                        af, expected_pr=expected_pr, expected_head=expected_head, expected_base=expected_base,
                        merge_method_requested=merge_method)
                    if operator_approval_result['result'] != 'APPROVED':
                        errs = operator_approval_result.get('errors', [])
                        blockers.append('Operator merge approval FAIL: ' + '; '.join(errs[:3]))

    # allow_merge requires: no blockers AND ledger gate PASS AND operator approval APPROVED
    base_allow = len(blockers) == 0
    ledger_ok = (ledger_gate_result is not None
                 and ledger_gate_result.get('checked', False)
                 and ledger_gate_result.get('result') == 'PASS')
    operator_ok = (operator_approval_result is not None
                   and operator_approval_result.get('checked', False)
                   and operator_approval_result.get('result') == 'APPROVED')
    allow_merge = base_allow and ledger_ok and operator_ok
    return _build_result(allow_merge, blockers, warnings, pr_info, job_info, checks_info,
                         ledger_gate_result, operator_approval_result)


def _build_result(allow_merge, blockers, warnings, pr_info, job_info, checks_info, ledger_gate_result=None, operator_approval_result=None):
    """Build the gate result."""
    result = {
        "allow_merge": allow_merge,
        "blockers": blockers,
        "warnings": warnings,
        "pr": pr_info,
        "job": job_info,
        "checks": checks_info,
    }
    if ledger_gate_result is not None:
        result["model_ledger_gate"] = ledger_gate_result
    if operator_approval_result is not None:
        result["operator_merge_approval"] = operator_approval_result
    return result


def _format_text(result):
    """Format result as human-readable text."""
    lines = [
        "========================================",
        "  Autonomous Merge Gate v1",
        "========================================",
    ]

    status = "✅ ALLOW MERGE" if result["allow_merge"] else "⛔ BLOCKED"
    lines.append(f"  Result: {status}")
    lines.append("----------------------------------------")

    # V1.20.8: Ledger gate status
    lg = result.get("model_ledger_gate", {})
    if lg:
        lg_icon = {"PASS": "✅", "FAIL": "❌", "N/A": "➖", "GATE_UNAVAILABLE": "⚠️"}.get(lg.get("result", "?"), "❓")
        lines.append(f"  Model Ledger Gate: {lg_icon} {lg.get('result', 'unknown')}")
        if lg.get("errors"):
            for e in lg["errors"][:3]:
                lines.append(f"    - {e}")
        lines.append("----------------------------------------")

    # V1.20.10: Operator approval status
    oa = result.get("operator_merge_approval", {})
    if oa:
        oa_icon = {"APPROVED": "\u2705", "BLOCKED": "\u274c"}.get(oa.get("result", "?"), "\u2753")
        lines.append(f"  Operator Approval: {oa_icon} {oa.get('result', 'unknown')}")
        if oa.get("errors"):
            for e in oa["errors"][:3]:
                lines.append(f"    - {e}")
        lines.append("----------------------------------------")

    if result["blockers"]:
        lines.append("  Blockers:")
        for b in result["blockers"]:
            lines.append(f"    ❌ {b}")

    if result["warnings"]:
        lines.append("  Warnings:")
        for w in result["warnings"]:
            lines.append(f"    ⚠️  {w}")

    lines.append("----------------------------------------")

    pr = result.get("pr", {})
    if pr:
        lines.append("  PR Info:")
        lines.append(f"    Number: {pr.get('number')}")
        lines.append(f"    Title: {pr.get('title')}")
        lines.append(f"    State: {pr.get('state')}")
        lines.append(f"    Head: {pr.get('head_ref')} ({pr.get('head_sha', 'N/A')[:12]})")
        lines.append(f"    Base: {pr.get('base_ref')}")
        lines.append(f"    Mergeable: {pr.get('mergeable')}")
        lines.append(f"    Changed Files: {pr.get('changed_files')}")
        lines.append(f"    URL: {pr.get('url')}")
        if pr.get("changed_paths"):
            lines.append(f"    Paths: {', '.join(pr['changed_paths'])}")

    lines.append("----------------------------------------")

    job = result.get("job", {})
    if job:
        lines.append("  Job Info:")
        lines.append(f"    Job ID: {job.get('job_id')}")
        lines.append(f"    Status: {job.get('job_status')}")
        lines.append(f"    Audit: {job.get('audit_status')}")
        lines.append(f"    Push Allowed: {job.get('push_allowed')}")

    lines.append("----------------------------------------")

    checks = result.get("checks", {})
    if checks:
        lines.append("  Checks:")
        lines.append(f"    Status: {checks.get('status')}")
        lines.append(f"    Count: {checks.get('count')}")

    lines.append("========================================")
    return "\n".join(lines)


def _format_json(result):
    """Format result as JSON."""
    return json.dumps(result, indent=2)


def build_parser():
    """Build and return the argument parser."""
    parser = argparse.ArgumentParser(
        prog="vibe_merge_gate",
        description="Autonomous Merge Gate v1 - Pre-merge verification for vibedev Hermes.",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="GitHub repository (owner/repo).",
    )
    parser.add_argument(
        "--pr",
        type=int,
        required=True,
        help="Pull request number.",
    )
    parser.add_argument(
        "--expected-base-sha",
        required=True,
        help="Expected base (main) SHA.",
    )
    parser.add_argument(
        "--expected-head-sha",
        required=True,
        help="Expected PR head SHA.",
    )
    parser.add_argument(
        "--allowed-path",
        action="append",
        default=[],
        help="Allowed changed paths (can be repeated).",
    )
    parser.add_argument(
        "--jobs-dir",
        default=None,
        help="Jobs directory path (default: VIBEDEV_JOBS_DIR env or ~/vibedev/jobs).",
    )
    parser.add_argument(
        "--job-id",
        default=None,
        help="Job ID to check in registry.",
    )
    parser.add_argument(
        "--report-file",
        default=None,
        help="Path to report JSON with MODEL_LEDGER/NODE_MODEL_SUMMARY/COOLDOWN_STATE_SUMMARY for ledger gate.",
    )
    parser.add_argument(
        "--approval-file",
        default=None,
        help="Path to operator merge approval JSON (required for merge readiness).",
    )
    parser.add_argument(
        "--merge-method",
        default=None,
        help="Requested merge method (merge/squash/rebase). Required for approval validation.",
    )
    parser.add_argument(
        "--json",
        dest="output_json",
        action="store_true",
        default=False,
        help="Output in JSON format.",
    )
    return parser


def main(argv=None):
    """Entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    result = run_gate(args)

    if args.output_json:
        print(_format_json(result))
    else:
        print(_format_text(result))

    return 0 if result["allow_merge"] else 1


if __name__ == "__main__":
    sys.exit(main())
