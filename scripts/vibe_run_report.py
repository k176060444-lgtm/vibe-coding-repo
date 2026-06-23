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

VERSION = "1.2.0"

# V1.20.7: Report status gate integration
try:
    from vibe_report_status_gate import check_report_status
    _REPORT_STATUS_GATE_AVAILABLE = True
except ImportError:
    check_report_status = None
    _REPORT_STATUS_GATE_AVAILABLE = False


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


def _collect_action_specific(eag_result):
    """Extract action-specific audit fields from EAG check result.

    Args:
        eag_result: dict returned by check_execution_approval() (V1.21.15+)

    Returns:
        dict with action_specific_approval section, or None if no eag_result.
    """
    if not eag_result:
        return None

    action = eag_result.get("action", "unknown")
    action_category = eag_result.get("action_category", "ordinary")

    section = {
        "action": action,
        "action_category": action_category,
        "verdict": eag_result.get("verdict", "UNKNOWN"),
    }

    # Only include detailed fields for action_specific actions
    if action_category == "action_specific":
        section["action_specific_required_fields"] = eag_result.get(
            "action_specific_required_fields", []
        )
        section["missing_fields"] = eag_result.get("missing_fields", [])
        section["invalid_fields"] = eag_result.get("invalid_fields", [])
        section["dedicated_approval_required"] = eag_result.get(
            "dedicated_approval_required", False
        )
        section["service_admin_critical_required"] = eag_result.get(
            "service_admin_critical_required", False
        )
        blocked_code = eag_result.get("blocked_reason_code")
        if blocked_code:
            section["blocked_reason_code"] = blocked_code

    return section


def _collect_deferred_registry(repo_root):
    """Collect deferred registry summary from .vibe/deferred_registry/*.json.

    Returns list of summary dicts, or empty list if no entries / dir missing.
    Graceful fallback: bad JSON, missing fields, IO errors are skipped.
    """
    registry_dir = Path(repo_root) / ".vibe" / "deferred_registry"
    if not registry_dir.is_dir():
        return []

    entries = []
    for f in sorted(registry_dir.glob("*.json")):
        if f.name.startswith("."):
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except (json.JSONDecodeError, IOError, OSError):
            continue

        entry = {
            "action": raw.get("action", "unknown"),
            "approval_id": raw.get("approval_id", ""),
            "workorder_id": raw.get("workorder_id", ""),
            "risk_level": raw.get("risk_level", "low"),
            "dedicated_approval": raw.get("dedicated_approval", False),
            "registry_only": raw.get("registry_only", True),
            "dry_run_only": raw.get("dry_run_only", True),
            "real_execution": False,
            "created_at": raw.get("created_at", ""),
            "history_digest": raw.get("history_digest", ""),
        }
        entries.append(entry)

    return entries


def _collect_verifier_deferred_result(repo_root):
    """Collect deferred_action_registry_consistency check from evidence verifier.

    Returns dict with check result (name/result/detail/errors/warnings) or None.
    Consumes verifier output only — does NOT re-parse .vibe/deferred_registry.
    Graceful fallback: verifier unavailable, no evidence, no check → None.
    """
    verifier_script = Path(repo_root) / "scripts" / "vibe_evidence_verifier.py"
    if not verifier_script.is_file():
        return None

    evidence_dir = Path(repo_root) / ".vibe" / "evidence"
    registry_dir = Path(repo_root) / ".vibe" / "registry"
    if not evidence_dir.is_dir() or not registry_dir.is_dir():
        return None

    # Find latest evidence file
    evidence_files = sorted(evidence_dir.glob("ev-*.json"))
    if not evidence_files:
        return None
    latest_evidence_id = evidence_files[-1].stem  # e.g. "ev-001"

    try:
        import subprocess as _sp
        result = _sp.run(
            [sys.executable, str(verifier_script), "verify",
             "--evidence-dir", str(evidence_dir),
             "--registry-dir", str(registry_dir),
             "--evidence-id", latest_evidence_id,
             "--json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode not in (0, 1):
            return None
        data = json.loads(result.stdout)
        for check in data.get("checks", []):
            if check.get("name") == "deferred_action_registry_consistency":
                return {
                    "name": check["name"],
                    "result": check["result"],
                    "detail": check.get("detail", ""),
                    "errors": check.get("errors", []),
                    "warnings": check.get("warnings", []),
                }
    except Exception:
        pass
    return None


def run_report(repo_root=None, jobs_dir=None, eag_result=None):
    """Generate run report."""
    if repo_root is None:
        repo_root = Path.cwd()
    else:
        repo_root = Path(repo_root)

    script_dir = repo_root / "scripts"
    if jobs_dir is None:
        jobs_dir = os.path.expanduser("~/vibedev/jobs")

    # V1.21.17: Auto-discover EAG result from .vibe/eag_result.json
    if eag_result is None:
        eag_result_path = repo_root / ".vibe" / "eag_result.json"
        try:
            if eag_result_path.is_file():
                with open(eag_result_path, encoding="utf-8") as _f:
                    eag_result = json.load(_f)
        except (json.JSONDecodeError, OSError):
            pass  # Graceful fallback — no section injected

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

    # V1.20.7: Run report status gate on terminal verdicts
    # Set top-level status so check_report_status can detect terminal status
    result["status"] = qg_verdict
    ledger_gate_result = None
    if _REPORT_STATUS_GATE_AVAILABLE and qg_verdict in ('PASS', 'MERGE_READY', 'FREEZE_PASS', 'PROMOTION_PASS'):
        ledger_gate_result = check_report_status(result)
        if not ledger_gate_result.get('status_allowed', True):
            result['quality_gate']['verdict'] = 'BLOCKED_BY_LEDGER_GATE'
            result['ledger_gate'] = {
                'result': 'FAIL',
                'terminal_status_found': ledger_gate_result.get('terminal_status_found'),
                'errors': ledger_gate_result.get('gate_errors', []),
            }
            result['operator_summary'] = 'BLOCKED: Model ledger gate failed. ' + '; '.join(ledger_gate_result.get('gate_errors', [])[:3])
            result['next_recommended_action'] = 'HALT: Model ledger gate BLOCKED. Fix ledger issues before proceeding.'
        else:
            result['ledger_gate'] = {
                'result': 'PASS' if ledger_gate_result.get('terminal_status_found') else 'N/A',
                'terminal_status_found': ledger_gate_result.get('terminal_status_found'),
            }
    elif not _REPORT_STATUS_GATE_AVAILABLE:
        result['ledger_gate'] = {'result': 'GATE_UNAVAILABLE', 'warning': 'vibe_report_status_gate not importable'}

    # V1.21.16: Collect action-specific audit fields from EAG result
    action_specific = _collect_action_specific(eag_result)
    if action_specific:
        result['action_specific_approval'] = action_specific

    # V1.21.21: Collect deferred registry entries
    deferred_entries = _collect_deferred_registry(repo_root)
    if deferred_entries:
        result['deferred_action_registry'] = deferred_entries

    # V1.21.24: Collect verifier deferred result
    verifier_deferred = _collect_verifier_deferred_result(repo_root)
    if verifier_deferred:
        result['verifier_deferred_result'] = verifier_deferred

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

    # V1.20.7: Ledger gate status
    ledger = result.get("ledger_gate", {})
    if ledger:
        lg_result = ledger.get("result", "N/A")
        lg_icon = {"PASS": "✅", "FAIL": "❌", "N/A": "➖", "GATE_UNAVAILABLE": "⚠️"}.get(lg_result, "❓")
        lines.append("## Ledger Gate")
        lines.append("- %s %s" % (lg_icon, lg_result))
        if ledger.get("errors"):
            for e in ledger["errors"][:3]:
                lines.append("  - %s" % e)
        lines.append("")

    # V1.21.16: Action-Specific Approval
    asa = result.get("action_specific_approval")
    if asa:
        lines.append("## Action-Specific Approval")
        asa_action = asa.get("action", "unknown")
        asa_category = asa.get("action_category", "unknown")
        asa_verdict = asa.get("verdict", "UNKNOWN")
        asa_icon = "✅" if "PASS" in asa_verdict or "APPROVAL_BOUND" == asa_verdict else "❌"
        lines.append("- %s **%s** [%s]" % (asa_icon, asa_verdict, asa_category))
        lines.append("- Action: `%s`" % asa_action)
        if asa_category == "action_specific":
            if asa.get("blocked_reason_code"):
                lines.append("- Blocked reason: `%s`" % asa["blocked_reason_code"])
            if asa.get("missing_fields"):
                lines.append("- Missing fields: %s" % ", ".join("`%s`" % f for f in asa["missing_fields"]))
            if asa.get("invalid_fields"):
                lines.append("- Invalid fields: %s" % "; ".join(asa["invalid_fields"]))
            if asa.get("dedicated_approval_required"):
                lines.append("- ⚠️ Dedicated approval required")
            if asa.get("service_admin_critical_required"):
                lines.append("- ⚠️ CRITICAL risk level required")
        lines.append("")

    # V1.21.21: Deferred Action Registry
    dar = result.get("deferred_action_registry")
    if dar:
        lines.append("## Deferred Action Registry")
        lines.append("- %d deferred action(s) registered" % len(dar))
        for entry in dar:
            action = entry.get("action", "unknown")
            approval_id = entry.get("approval_id", "")
            risk = entry.get("risk_level", "low")
            dedicated = entry.get("dedicated_approval", False)
            warn = " ⚠️ dedicated/critical" if dedicated and action == "service_admin_uac" else ""
            lines.append("- `%s` | approval: `%s` | risk: %s%s" % (action, approval_id, risk, warn))
        lines.append("")

    # V1.21.24: Verifier Deferred Registry Result
    vdr = result.get("verifier_deferred_result")
    if vdr:
        lines.append("## Verifier Deferred Registry")
        vdr_result = vdr.get("result", "UNKNOWN")
        vdr_detail = vdr.get("detail", "")
        if vdr_result == "PASS":
            lines.append("- ✅ %s" % vdr_detail)
        elif vdr_result == "WARN":
            lines.append("- ⚠️ %s" % vdr_detail)
            for w in vdr.get("warnings", []):
                lines.append("  - %s" % w)
        elif vdr_result == "FAIL":
            lines.append("- ❌ %s" % vdr_detail)
            for e in vdr.get("errors", []):
                lines.append("  - %s" % e)
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
    base = "QG:%s Smoke:%s Audit:%s Baseline:%s PR:%s V1:%s | %s" % (
        qg, smoke, audit, baseline, pr_str, v1f, result.get("operator_summary", "")[:60])
    # V1.21.16: Append ASA info if present
    asa = result.get("action_specific_approval")
    if asa:
        asa_cat = asa.get("action_category", "?")
        asa_code = asa.get("blocked_reason_code")
        asa_part = "ASA:%s" % asa_cat
        if asa_code:
            asa_part += "(%s)" % asa_code
        base += " | " + asa_part
    # V1.21.21: Append DAR info if present
    dar = result.get("deferred_action_registry")
    if dar:
        actions = sorted(set(e.get("action", "?") for e in dar))
        base += " | DAR:%d (%s)" % (len(dar), ", ".join(actions))
    # V1.21.24: Append VDR info if present
    vdr = result.get("verifier_deferred_result")
    if vdr:
        base += " | VDR:%s" % vdr.get("result", "?")
    return base


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
    parser.add_argument("--eag-result", dest="eag_result_file", help="Path to EAG result JSON (optional, for action-specific audit)")
    return parser


def main(argv=None):
    """Main entry point (import-safe)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    eag_result = None
    if args.eag_result_file:
        with open(args.eag_result_file, encoding="utf-8") as f:
            eag_result = json.load(f)

    result = run_report(
        repo_root=args.repo_root or Path(__file__).parent.parent,
        jobs_dir=args.jobs_dir,
        eag_result=eag_result,
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
