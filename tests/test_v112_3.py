#!/usr/bin/env python3
"""WO4: Tests for V1.12.3 gateway health + pytest result classifier."""
import json, os, subprocess, sys

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")

def _run_script(name, args):
    path = os.path.join(SCRIPTS, name)
    proc = subprocess.run([sys.executable, path] + args, capture_output=True, text=True, timeout=30)
    parsed = None
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass
    return proc.returncode, proc.stdout, proc.stderr, parsed


# ── Gateway Health Tests ──────────────────────────────────────────────

def _test_gateway_health_self_check():
    rc, out, _, parsed = _run_script("vibe_gateway_health.py", ["--json", "self-check"])
    ok = parsed and parsed.get("overall") == "PASS"
    return {"passed": ok, "message": f"{parsed.get('overall')} ({parsed.get('passed')}/{parsed.get('total')})" if parsed else "parse failed"}

def _test_gateway_health_version():
    rc, out, _, _ = _run_script("vibe_gateway_health.py", ["--version"])
    return {"passed": rc == 0 and "1.0.0" in out, "message": out.strip()[:60]}

def _test_gateway_offline_no_process():
    """Simulate: no process found → OFFLINE_NO_PROCESS."""
    # We test by calling diagnose_profile with no matching processes
    sys.path.insert(0, SCRIPTS)
    try:
        import vibe_gateway_health as gwh
        # On Debian, no Windows gateway processes exist
        result = gwh.diagnose_profile("default", log_dir="/nonexistent")
        ok = result["overall_status"] in (gwh.STATUS_OFFLINE_NO_PROCESS, gwh.STATUS_UNKNOWN, gwh.STATUS_TASK_READY_NOT_RUNNING, gwh.STATUS_STALE_LOG)
        return {"passed": ok, "message": f"status={result['overall_status']}"}
    except Exception as e:
        return {"passed": False, "message": str(e)[:80]}
    finally:
        sys.path.pop(0)


# ── Pytest Result Classifier Tests ────────────────────────────────────

def _test_classifier_self_check():
    rc, out, _, parsed = _run_script("vibe_pytest_result_classifier.py", ["--json", "self-check"])
    ok = parsed and parsed.get("overall") == "PASS"
    return {"passed": ok, "message": f"{parsed.get('overall')} ({parsed.get('passed')}/{parsed.get('total')})" if parsed else "parse failed"}

def _test_classifier_version():
    rc, out, _, _ = _run_script("vibe_pytest_result_classifier.py", ["--version"])
    return {"passed": rc == 0 and "1.0.0" in out, "message": out.strip()[:60]}

def _test_classifier_exit0_pass():
    rc, out, _, parsed = _run_script("vibe_pytest_result_classifier.py", [
        "--json", "classify", "--exit-code", "0", "--output", "5 passed in 1.0s"
    ])
    ok = parsed and parsed.get("category") == "PASS" and parsed.get("passed") == 5
    return {"passed": ok, "message": f"category={parsed.get('category')} passed={parsed.get('passed')}" if parsed else "parse failed"}

def _test_classifier_exit0_skipped_only():
    rc, out, _, parsed = _run_script("vibe_pytest_result_classifier.py", [
        "--json", "classify", "--exit-code", "0", "--output", "1 skipped in 0.05s"
    ])
    ok = parsed and parsed.get("category") == "SKIPPED_ONLY"
    return {"passed": ok, "message": f"category={parsed.get('category')}" if parsed else "parse failed"}

def _test_classifier_exit5_no_tests():
    rc, out, _, parsed = _run_script("vibe_pytest_result_classifier.py", [
        "--json", "classify", "--exit-code", "5", "--output", ""
    ])
    ok = parsed and parsed.get("category") == "NO_TESTS"
    return {"passed": ok, "message": f"category={parsed.get('category')}" if parsed else "parse failed"}

def _test_classifier_exit5_inconsistent():
    rc, out, _, parsed = _run_script("vibe_pytest_result_classifier.py", [
        "--json", "classify", "--exit-code", "5", "--output", "1 skipped in 0.05s"
    ])
    ok = parsed and parsed.get("category") == "INCONSISTENT_RESULT"
    return {"passed": ok, "message": f"category={parsed.get('category')}" if parsed else "parse failed"}

def _test_classifier_exit1_env_fail():
    rc, out, _, parsed = _run_script("vibe_pytest_result_classifier.py", [
        "--json", "classify", "--exit-code", "1", "--output", "", "--stderr", "ModuleNotFoundError: No module named 'xyz'"
    ])
    ok = parsed and parsed.get("category") == "ENV_FAIL"
    return {"passed": ok, "message": f"category={parsed.get('category')}" if parsed else "parse failed"}

def _test_classifier_strong_validation():
    """Strong validation only for real passes (exit=0, passed>0)."""
    sys.path.insert(0, SCRIPTS)
    try:
        import vibe_pytest_result_classifier as prc
        r1 = prc.classify_pytest_result(0, "5 passed in 1.0s")
        r2 = prc.classify_pytest_result(0, "1 skipped in 0.05s")
        r3 = prc.classify_pytest_result(5, "1 skipped in 0.05s")
        ok = r1["strong_validation"] and not r2["strong_validation"] and not r3["strong_validation"]
        return {"passed": ok, "message": f"pass={r1['strong_validation']} skipped={r2['strong_validation']} inc={r3['strong_validation']}"}
    except Exception as e:
        return {"passed": False, "message": str(e)[:80]}
    finally:
        sys.path.pop(0)


# ── Runner ─────────────────────────────────────────────────────────────

TESTS = [
    ("gateway_health_self_check", _test_gateway_health_self_check),
    ("gateway_health_version", _test_gateway_health_version),
    ("gateway_offline_no_process", _test_gateway_offline_no_process),
    ("classifier_self_check", _test_classifier_self_check),
    ("classifier_version", _test_classifier_version),
    ("classifier_exit0_pass", _test_classifier_exit0_pass),
    ("classifier_exit0_skipped", _test_classifier_exit0_skipped_only),
    ("classifier_exit5_no_tests", _test_classifier_exit5_no_tests),
    ("classifier_exit5_inconsistent", _test_classifier_exit5_inconsistent),
    ("classifier_exit1_env_fail", _test_classifier_exit1_env_fail),
    ("classifier_strong_validation", _test_classifier_strong_validation),
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
    print(f"=== V1.12.3 Gateway Health + Pytest Classifier Tests ===")
    print(f"Total: {total} | Passed: {passed} | Failed: {failed}")
    print()
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
