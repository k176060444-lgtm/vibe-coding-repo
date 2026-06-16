#!/usr/bin/env python3
"""Smoke tests for vibe_node_attribution.py."""
import json, os, subprocess, sys

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "vibe_node_attribution.py")

def _run(args):
    proc = subprocess.run([sys.executable, SCRIPT] + args, capture_output=True, text=True, timeout=15)
    parsed = None
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass
    return proc.returncode, proc.stdout, proc.stderr, parsed

def _test_version():
    rc, stdout, stderr, _ = _run(["--version"])
    ok = rc == 0 and "1.0.0" in stdout
    return {"passed": ok, "message": stdout.strip()[:60]}

def _test_report_has_controller_node():
    rc, stdout, stderr, parsed = _run(["--json", "--example"])
    if not parsed:
        return {"passed": False, "message": "no json output"}
    ok = "controller_node" in parsed
    return {"passed": ok, "message": f"controller_node={parsed.get('controller_node','?')}"}

def _test_report_has_execution_node():
    rc, stdout, stderr, parsed = _run(["--json", "--example"])
    if not parsed:
        return {"passed": False, "message": "no json output"}
    ok = "execution_node" in parsed
    return {"passed": ok, "message": f"execution_node={parsed.get('execution_node','?')}"}

def _test_report_has_git_mutation_node():
    rc, stdout, stderr, parsed = _run(["--json", "--example"])
    if not parsed:
        return {"passed": False, "message": "no json output"}
    ok = "git_mutation_node" in parsed
    return {"passed": ok, "message": f"git_mutation_node={parsed.get('git_mutation_node','?')}"}

def _test_report_has_token_access_node():
    rc, stdout, stderr, parsed = _run(["--json", "--example"])
    if not parsed:
        return {"passed": False, "message": "no json output"}
    ok = "token_access_node" in parsed
    return {"passed": ok, "message": f"token_access_node={parsed.get('token_access_node','?')}"}

def _test_distinguishes_controller_from_worker():
    rc, stdout, stderr, parsed = _run(["--json", "--example"])
    if not parsed:
        return {"passed": False, "message": "no json output"}
    ctrl = parsed.get("controller_node")
    exec_node = parsed.get("execution_node")
    ok = ctrl != exec_node and ctrl and exec_node
    return {"passed": ok, "message": f"controller={ctrl} execution={exec_node}"}

def _test_token_redaction():
    rc, stdout, stderr, parsed = _run(["--json", "--example"])
    if not parsed:
        return {"passed": False, "message": "no json output"}
    combined = json.dumps(parsed)
    has_secret = "ghp_" in combined or "github_pat_" in combined or "Bearer" in combined
    return {"passed": not has_secret, "message": f"secret_in_output={has_secret}"}

def _test_format_has_attribution_section():
    rc, stdout, stderr, _ = _run(["--format", "--example"])
    ok = "Node / Agent Attribution" in stdout and "controller_node" in stdout
    return {"passed": ok, "message": f"has_section={ok}"}

TESTS = [
    ("attribution_version", _test_version),
    ("attribution_controller_node", _test_report_has_controller_node),
    ("attribution_execution_node", _test_report_has_execution_node),
    ("attribution_git_mutation_node", _test_report_has_git_mutation_node),
    ("attribution_token_access_node", _test_report_has_token_access_node),
    ("attribution_distinguishes_nodes", _test_distinguishes_controller_from_worker),
    ("attribution_token_redaction", _test_token_redaction),
    ("attribution_format_section", _test_format_has_attribution_section),
]

def main():
    passed = failed = 0
    results = []
    for name, func in TESTS:
        try:
            r = func()
            ok = r.get("passed", False)
            if ok:
                passed += 1
            else:
                failed += 1
            results.append({"test": name, "result": "PASS" if ok else "FAIL", "message": r.get("message", "")})
        except Exception as e:
            failed += 1
            results.append({"test": name, "result": "ERROR", "message": str(e)})

    total = passed + failed
    print(f"=== Node Attribution Smoke Tests ===")
    print(f"Total: {total} | Passed: {passed} | Failed: {failed}")
    print()
    for r in results:
        icon = "PASS" if r["result"] == "PASS" else "FAIL"
        print(f"  [{icon}] {r['test']}: {r['message']}")
    if failed > 0:
        print(f"\nFAILED: {failed}")
        return 1
    print(f"\nALL {total} TESTS PASSED")
    return 0

if __name__ == "__main__":
    sys.exit(main())
