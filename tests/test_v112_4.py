#!/usr/bin/env python3
"""V1.12.4 standalone tests — dashboard, resume gate, health snapshot."""
import json, os, subprocess, sys

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")

def _run(name, args):
    path = os.path.join(SCRIPTS, name)
    proc = subprocess.run([sys.executable, path] + args, capture_output=True, text=True, timeout=15)
    parsed = None
    if proc.stdout.strip():
        try: parsed = json.loads(proc.stdout)
        except: pass
    return proc.returncode, parsed

# ── Dashboard ──
def _test_dashboard_self_check():
    rc, d = _run("vibe_batch_dashboard.py", ["--json", "--self-check"])
    ok = d and d.get("overall") == "PASS"
    return {"passed": ok, "message": f"{d.get('overall')} ({d.get('passed')}/{d.get('total')})" if d else "fail"}

def _test_dashboard_reports_baseline():
    rc, d = _run("vibe_batch_dashboard.py", ["--json", "--self-check"])
    ok = d and d.get("overall") == "PASS"
    return {"passed": ok, "message": f"baseline={d.get('baseline', {}).get('local_main', '?')[:12]}" if d else "fail"}

def _test_dashboard_reports_worktrees():
    rc, d = _run("vibe_batch_dashboard.py", ["--json", "--self-check"])
    ok = d and d.get("overall") == "PASS"
    return {"passed": ok, "message": f"worktrees={len(d.get('worktrees', []))}" if d else "fail"}

# ── Resume Gate ──
def _test_resume_gate_self_check():
    rc, d = _run("vibe_resume_gate.py", ["--json", "self-check"])
    ok = d and d.get("overall") == "PASS"
    return {"passed": ok, "message": f"{d.get('overall')} ({d.get('passed')}/{d.get('total')})" if d else "fail"}

def _test_resume_gate_stale_dirty():
    rc, d = _run("vibe_resume_gate.py", ["--json", "check", "--batch-id", "test", "--worktree", "/x", "--expected-baseline", "old", "--current-main", "new", "--dirty", "true", "--gateway-status", "ONLINE", "--worker-reachable", "true"])
    ok = d and d.get("decision") == "CLEAN_RESUME_REQUIRED"
    return {"passed": ok, "message": d.get("decision", "?") if d else "fail"}

def _test_resume_gate_clean_safe():
    rc, d = _run("vibe_resume_gate.py", ["--json", "check", "--batch-id", "test", "--worktree", "/x", "--expected-baseline", "sha", "--current-main", "sha", "--dirty", "false", "--gateway-status", "ONLINE", "--worker-reachable", "true"])
    ok = d and d.get("decision") == "RESUME_SAFE"
    return {"passed": ok, "message": d.get("decision", "?") if d else "fail"}

def _test_resume_gate_gateway_offline():
    rc, d = _run("vibe_resume_gate.py", ["--json", "check", "--batch-id", "test", "--worktree", "/x", "--expected-baseline", "sha", "--current-main", "sha", "--gateway-status", "OFFLINE_NO_PROCESS", "--worker-reachable", "true"])
    ok = d and d.get("decision") == "BLOCK_GATEWAY_OFFLINE"
    return {"passed": ok, "message": d.get("decision", "?") if d else "fail"}

def _test_resume_gate_worker_unreachable():
    rc, d = _run("vibe_resume_gate.py", ["--json", "check", "--batch-id", "test", "--worktree", "/x", "--expected-baseline", "sha", "--current-main", "sha", "--gateway-status", "ONLINE", "--worker-reachable", "false"])
    ok = d and d.get("decision") == "BLOCK_WORKER_UNREACHABLE"
    return {"passed": ok, "message": d.get("decision", "?") if d else "fail"}

# ── Health Snapshot ──
def _test_health_snapshot_self_check():
    rc, d = _run("vibe_health_snapshot.py", ["--json", "--self-check"])
    ok = d and d.get("overall") == "PASS"
    return {"passed": ok, "message": f"{d.get('overall')} ({d.get('passed')}/{d.get('total')})" if d else "fail"}

def _test_health_snapshot_verdict():
    rc, d = _run("vibe_health_snapshot.py", ["--json", "--self-check"])
    ok = d and (d.get("verdict") in ("OK", "WARN", "BLOCK") or d.get("overall") == "PASS")
    return {"passed": ok, "message": f"verdict={d.get('verdict')}" if d else "fail"}

def _test_health_snapshot_has_checks():
    rc, d = _run("vibe_health_snapshot.py", ["--json", "--self-check"])
    ok = d and len(d.get("checks", [])) >= 3
    return {"passed": ok, "message": f"checks={len(d.get('checks', []))}" if d else "fail"}

# ── Runner ──
TESTS = [
    ("dashboard_self_check", _test_dashboard_self_check),
    ("dashboard_baseline", _test_dashboard_reports_baseline),
    ("dashboard_worktrees", _test_dashboard_reports_worktrees),
    ("resume_gate_self_check", _test_resume_gate_self_check),
    ("resume_gate_stale_dirty", _test_resume_gate_stale_dirty),
    ("resume_gate_clean_safe", _test_resume_gate_clean_safe),
    ("resume_gate_gateway_offline", _test_resume_gate_gateway_offline),
    ("resume_gate_worker_unreachable", _test_resume_gate_worker_unreachable),
    ("health_snapshot_self_check", _test_health_snapshot_self_check),
    ("health_snapshot_verdict", _test_health_snapshot_verdict),
    ("health_snapshot_checks", _test_health_snapshot_has_checks),
]

def main():
    passed = failed = 0
    results = []
    for name, func in TESTS:
        try:
            r = func()
            ok = r.get("passed", False)
            if ok: passed += 1
            else: failed += 1
            results.append({"test": name, "result": "PASS" if ok else "FAIL", "message": r.get("message", "")})
        except Exception as e:
            failed += 1
            results.append({"test": name, "result": "ERROR", "message": str(e)[:100]})

    total = passed + failed
    print(f"=== V1.12.4 Dashboard + Resume Gate + Health Snapshot Tests ===")
    print(f"Total: {total} | Passed: {passed} | Failed: {failed}\n")
    for r in results:
        icon = "PASS" if r["result"] == "PASS" else "FAIL"
        print(f"  [{icon}] {r['test']}: {r['message']}")
    if failed:
        print(f"\nFAILED: {failed}")
        return 1
    print(f"\nALL {total} TESTS PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
