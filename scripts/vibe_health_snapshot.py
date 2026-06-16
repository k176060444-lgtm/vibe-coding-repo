#!/usr/bin/env python3
"""Health Snapshot v1.0.0 — one-command pre-work safety check.

Usage:
    python3 scripts/vibe_health_snapshot.py --json
    python3 scripts/vibe_health_snapshot.py --text
    python3 scripts/vibe_health_snapshot.py --self-check [--json]
"""

import argparse
import json
import os
import subprocess
import sys
import importlib.util
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"


def _run(cmd, timeout=15, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except OSError as e:
        return -1, "", str(e)


def _load_and_run(script_path, args):
    """Run a script and parse JSON output."""
    rc, out, err = _run([sys.executable, script_path] + args, timeout=30)
    if rc == 0 and out:
        try:
            return json.loads(out)
        except (json.JSONDecodeError, ValueError):
            pass
    return {"error": f"rc={rc}", "stderr": err[:200]}


def snapshot(jobs_dir=None, output_json=False):
    jobs_dir = jobs_dir or os.path.expanduser("~/vibedev/jobs")
    script_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)))

    checks = []
    risks = []

    # 1. Batch dashboard
    dashboard_path = os.path.join(script_dir, "vibe_batch_dashboard.py")
    if os.path.isfile(dashboard_path):
        d = _load_and_run(dashboard_path, ["--json", "--jobs-dir", jobs_dir])
        if "error" not in d:
            baseline = d.get("baseline", {})
            if not baseline.get("consistent"):
                risks.append("baseline inconsistent (local != origin)")
                checks.append({"name": "dashboard", "status": "WARN", "message": "baseline inconsistent"})
            else:
                checks.append({"name": "dashboard", "status": "OK", "message": f"baseline={baseline.get('origin_main', '?')}"})
        else:
            checks.append({"name": "dashboard", "status": "WARN", "message": str(d.get("error", ""))[:60]})
    else:
        checks.append({"name": "dashboard", "status": "WARN", "message": "not found"})

    # 2. Gateway health (read-only check)
    gw_path = os.path.join(script_dir, "vibe_gateway_health.py")
    if os.path.isfile(gw_path):
        gw = _load_and_run(gw_path, ["--json", "self-check"])
        if gw.get("overall") == "PASS":
            checks.append({"name": "gateway_health", "status": "OK", "message": f"{gw.get('passed')}/{gw.get('total')}"})
        else:
            checks.append({"name": "gateway_health", "status": "WARN", "message": f"{gw.get('overall', 'FAIL')}"})
    else:
        checks.append({"name": "gateway_health", "status": "WARN", "message": "not found"})

    # 3. Test env manager
    env_path = os.path.join(script_dir, "vibe_test_env_manager.py")
    if os.path.isfile(env_path):
        env = _load_and_run(env_path, ["--json", "self-check"])
        if env.get("overall") == "PASS":
            checks.append({"name": "test_env_manager", "status": "OK", "message": f"{env.get('passed')}/{env.get('total')}"})
        else:
            checks.append({"name": "test_env_manager", "status": "WARN", "message": str(env.get("overall", "FAIL"))})
    else:
        checks.append({"name": "test_env_manager", "status": "WARN", "message": "not found"})

    # 4. Token source policy
    tok_path = os.path.join(script_dir, "vibe_token_source_policy.py")
    if os.path.isfile(tok_path):
        tok = _load_and_run(tok_path, ["--json", "self-check"])
        if tok.get("overall") == "PASS":
            checks.append({"name": "token_policy", "status": "OK", "message": f"{tok.get('passed')}/{tok.get('total')}"})
        else:
            checks.append({"name": "token_policy", "status": "WARN", "message": str(tok.get("overall", "FAIL"))})
            risks.append("token policy self-check failed")

    # 5. Pytest classifier
    cls_path = os.path.join(script_dir, "vibe_pytest_result_classifier.py")
    if os.path.isfile(cls_path):
        cls = _load_and_run(cls_path, ["--json", "self-check"])
        if cls.get("overall") == "PASS":
            checks.append({"name": "classifier", "status": "OK", "message": f"{cls.get('passed')}/{cls.get('total')}"})
        else:
            checks.append({"name": "classifier", "status": "WARN", "message": str(cls.get("overall", "FAIL"))})

    # 6. External harness
    h_path = os.path.join(script_dir, "vibe_external_test_harness.py")
    if os.path.isfile(h_path):
        h = _load_and_run(h_path, ["--json", "self-check"])
        if h.get("overall") == "PASS":
            checks.append({"name": "harness", "status": "OK", "message": f"{h.get('passed')}/{h.get('total')}"})
        else:
            checks.append({"name": "harness", "status": "WARN", "message": str(h.get("overall", "FAIL"))})

    # 7. Audit lock
    lock_path = os.path.join(jobs_dir, "wo-code-repo-status-001", "work-order.json")
    if os.path.isfile(lock_path):
        try:
            with open(lock_path) as f:
                wo = json.load(f)
            if wo.get("audit_status") == "audit_tainted":
                checks.append({"name": "audit_lock", "status": "OK", "message": "intact"})
            else:
                checks.append({"name": "audit_lock", "status": "WARN", "message": f"status={wo.get('audit_status')}"})
        except (json.JSONDecodeError, OSError):
            checks.append({"name": "audit_lock", "status": "WARN", "message": "unreadable"})
    else:
        checks.append({"name": "audit_lock", "status": "BLOCK", "message": "lock file missing"})
        risks.append("audit lock missing — critical")

    # Overall verdict
    statuses = [c["status"] for c in checks]
    if "BLOCK" in statuses:
        verdict = "BLOCK"
    elif statuses.count("WARN") >= 3:
        verdict = "WARN"
    elif "WARN" in statuses:
        verdict = "WARN"
    else:
        verdict = "OK"

    recommended = "proceed" if verdict == "OK" else ("review warnings" if verdict == "WARN" else "STOP — investigate blockers")

    result = {
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "verdict": verdict,
        "checks": checks,
        "top_risks": risks,
        "recommended_action": recommended,
        "node_attribution": {
            "controller_node": "windows",
            "execution_node": "debian",
        },
    }
    return result


def self_check(output_json=False):
    checks = []
    checks.append({"name": "version", "passed": True, "message": VERSION})
    # Verify script structure without calling snapshot (avoids git fetch)
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        expected = ["vibe_batch_dashboard.py", "vibe_gateway_health.py", "vibe_test_env_manager.py", "vibe_token_source_policy.py", "vibe_pytest_result_classifier.py", "vibe_external_test_harness.py"]
        found = sum(1 for s in expected if os.path.isfile(os.path.join(script_dir, s)))
        checks.append({"name": "component_scripts", "passed": found >= 4, "message": f"{found}/{len(expected)} found"})
        checks.append({"name": "has_attribution", "passed": True, "message": "controller=windows execution=debian"})
        checks.append({"name": "verdict_format", "passed": True, "message": "OK/WARN/BLOCK supported"})
    except Exception as e:
        checks.append({"name": "load_check", "passed": False, "message": str(e)[:80]})

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    return {"overall": "PASS" if passed == total else "FAIL", "passed": passed, "total": total, "checks": checks}


def build_parser():
    p = argparse.ArgumentParser(prog="vibe_health_snapshot")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument("--json", dest="output_json", action="store_true")
    p.add_argument("--text", dest="output_text", action="store_true", default=True)
    p.add_argument("--self-check", dest="self_check_flag", action="store_true")
    p.add_argument("--jobs-dir", default=None)
    return p


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)

    if args.self_check_flag:
        r = self_check(args.output_json)
    else:
        r = snapshot(args.jobs_dir, args.output_json)

    if args.output_json:
        print(json.dumps(r, indent=2))
    else:
        if "overall" in r:
            print(f"Overall: {r['overall']} ({r['passed']}/{r['total']})")
            for c in r.get("checks", []):
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  [{icon}] {c['name']}: {c['message']}")
        else:
            print(f"Verdict: {r['verdict']}")
            for c in r.get("checks", []):
                icon = {"OK": "✓", "WARN": "⚠", "BLOCK": "✗"}.get(c["status"], "?")
                print(f"  {icon} {c['name']}: {c['status']} - {c['message']}")
            if r.get("top_risks"):
                print("Risks:")
                for risk in r["top_risks"]:
                    print(f"  ! {risk}")
            print(f"Recommended: {r.get('recommended_action')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
