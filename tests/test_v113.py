#!/usr/bin/env python3
"""V1.13 standalone tests — task intake, WO compiler, model routing, report schema."""
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

# ── Task Intake ──
def _test_intake_self_check():
    rc, d = _run("vibe_task_intake.py", ["--json", "--self-check"])
    ok = d and d.get("overall") == "PASS"
    return {"passed": ok, "message": f"{d.get('overall')} ({d.get('passed')}/{d.get('total')})" if d else "fail"}

def _test_intake_self_repo_low():
    rc, d = _run("vibe_task_intake.py", ["--json", "--repo", "k176060444-lgtm/vibe-coding-repo", "update docs"])
    ok = d and d.get("risk_level") == "low" and d.get("repo_scope") == "trusted-self"
    return {"passed": ok, "message": f"risk={d.get('risk_level')} scope={d.get('repo_scope')}" if d else "fail"}

def _test_intake_external_push():
    rc, d = _run("vibe_task_intake.py", ["--json", "--repo", "org/repo", "push conflict fix"])
    ok = d and d.get("requires_approval") is True and d.get("repo_scope") == "protected-external"
    return {"passed": ok, "message": f"risk={d.get('risk_level')} approval={d.get('requires_approval')}" if d else "fail"}

# ── WO Compiler ──
def _test_compiler_self_check():
    rc, d = _run("vibe_wo_compiler.py", ["--json", "--self-check"])
    ok = d and d.get("overall") == "PASS"
    return {"passed": ok, "message": f"{d.get('overall')} ({d.get('passed')}/{d.get('total')})" if d else "fail"}

def _test_compiler_generates_plan():
    # Create a task spec and compile it
    spec = {"task_id": "task-v113-test", "summary": "test plan", "repo": "k176060444-lgtm/vibe-coding-repo",
            "repo_scope": "trusted-self", "risk_level": "low", "operation_type": "write-local",
            "requires_approval": False, "requires_token": False,
            "forbidden_actions": [], "validation_mode": "auto"}
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(spec, f)
        f.flush()
        rc, d = _run("vibe_wo_compiler.py", ["--json", "--input", f.name])
    os.unlink(f.name)
    ok = d and d.get("wo_id") is not None and d.get("template") == "self-repo-low-risk"
    return {"passed": ok, "message": f"wo={d.get('wo_id', '?')} template={d.get('template')}" if d else "fail"}

# ── Model Routing ──
def _test_routing_self_check():
    rc, d = _run("vibe_model_routing_policy.py", ["--json", "--self-check"])
    ok = d and d.get("overall") == "PASS"
    return {"passed": ok, "message": f"{d.get('overall')} ({d.get('passed')}/{d.get('total')})" if d else "fail"}

def _test_routing_implementer():
    rc, d = _run("vibe_model_routing_policy.py", ["--json", "route", "--task-type", "implementer"])
    ok = d and d.get("recommended") is not None
    return {"passed": ok, "message": f"recommended={d.get('recommended')}" if d else "fail"}

# ── Report Schema ──
def _test_schema_self_check():
    rc, d = _run("vibe_report_schema.py", ["--json", "--self-check"])
    ok = d and d.get("overall") == "PASS"
    return {"passed": ok, "message": f"{d.get('overall')} ({d.get('passed')}/{d.get('total')})" if d else "fail"}

def _test_schema_valid_report():
    report = {
        "pr_merge_info": {"pr": 1}, "changed_paths": [], "baseline": {"current_sha": "x"},
        "validation": {"smoke": "PASS", "qg": "PASS", "v1_freeze": "PASS"},
        "node_attribution": {"controller_node": "windows", "execution_node": "debian",
                             "transport": "ssh", "git_mutation_node": "debian",
                             "token_access_node": "debian", "pr_operation_node": "debian"},
        "token_status": {"token_read": False, "token_leaked": False, "token_source": "none"},
        "external_write_status": {"real_write_occurred": False},
    }
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(report, f)
        f.flush()
        rc, d = _run("vibe_report_schema.py", ["--json", "validate", "--input", f.name])
    os.unlink(f.name)
    ok = d and d.get("valid") is True
    return {"passed": ok, "message": f"valid={d.get('valid')} errors={len(d.get('errors', []))}" if d else "fail"}

# ── Runner ──
TESTS = [
    ("intake_self_check", _test_intake_self_check),
    ("intake_self_repo_low", _test_intake_self_repo_low),
    ("intake_external_push", _test_intake_external_push),
    ("compiler_self_check", _test_compiler_self_check),
    ("compiler_generates_plan", _test_compiler_generates_plan),
    ("routing_self_check", _test_routing_self_check),
    ("routing_implementer", _test_routing_implementer),
    ("schema_self_check", _test_schema_self_check),
    ("schema_valid_report", _test_schema_valid_report),
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
    print(f"=== V1.13 Task Intake + WO Compiler + Model Routing + Report Schema Tests ===")
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
