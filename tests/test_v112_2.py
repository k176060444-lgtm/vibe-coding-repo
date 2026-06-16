#!/usr/bin/env python3
"""WO4: Tests for V1.12.2 token source policy + test env manager.

Tests:
1. Self repo gh cached allowed
2. External push gh cached blocked
3. External read-only no token
4. Standard token metadata preflight allowed
5. Token redaction passes
6. Test env manager self-check
7. Node/Agent Attribution
"""
import json, os, subprocess, sys

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")


def _run_script(name, args):
    path = os.path.join(SCRIPTS, name)
    proc = subprocess.run([sys.executable, path] + args, capture_output=True, text=True, timeout=120)
    parsed = None
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass
    return proc.returncode, proc.stdout, proc.stderr, parsed


# ── Token Source Policy Tests ──────────────────────────────────────────

def _test_self_repo_gh_cached_allowed():
    """Self repo push: gh cached credentials allowed."""
    rc, out, _, parsed = _run_script("vibe_token_source_policy.py", [
        "--json", "check", "--repo", "k176060444-lgtm/vibe-coding-repo", "--operation", "push"
    ])
    ok = parsed and parsed.get("gh_cached_credentials_allowed") is True
    return {"passed": ok, "message": f"gh_cached={parsed.get('gh_cached_credentials_allowed') if parsed else 'N/A'}"}


def _test_external_push_gh_cached_blocked():
    """External push: gh cached credentials FORBIDDEN."""
    rc, out, _, parsed = _run_script("vibe_token_source_policy.py", [
        "--json", "check", "--repo", "NousResearch/hermes-agent", "--operation", "push"
    ])
    ok = parsed and parsed.get("gh_cached_credentials_allowed") is False
    return {"passed": ok, "message": f"gh_cached={parsed.get('gh_cached_credentials_allowed') if parsed else 'N/A'}"}


def _test_external_read_no_token():
    """External read-only: no token needed."""
    rc, out, _, parsed = _run_script("vibe_token_source_policy.py", [
        "--json", "check", "--repo", "NousResearch/hermes-agent", "--operation", "fetch"
    ])
    ok = parsed and parsed.get("token_source_policy") == "no_token_needed"
    return {"passed": ok, "message": f"policy={parsed.get('token_source_policy') if parsed else 'N/A'}"}


def _test_standard_token_preflight():
    """Standard token metadata preflight: allowed for external push."""
    rc, out, _, parsed = _run_script("vibe_token_source_policy.py", [
        "--json", "check", "--repo", "NousResearch/hermes-agent", "--operation", "push"
    ])
    ok = parsed and parsed.get("standard_token_allowed") is True and parsed.get("requires_approval") is True
    return {"passed": ok, "message": f"standard_allowed={parsed.get('standard_token_allowed') if parsed else 'N/A'}"}


def _test_token_redaction():
    """Token source policy self-check passes (verifies redaction)."""
    rc, out, _, parsed = _run_script("vibe_token_source_policy.py", [
        "--json", "self-check"
    ])
    ok = parsed and parsed.get("overall") == "PASS"
    return {"passed": ok, "message": f"{parsed.get('overall', '?')} ({parsed.get('passed', 0)}/{parsed.get('total', 0)})" if parsed else "parse failed"}


# ── Test Env Manager Tests ─────────────────────────────────────────────

def _test_env_manager_self_check():
    """Test env manager self-check passes."""
    rc, out, _, parsed = _run_script("vibe_test_env_manager.py", [
        "--json", "self-check"
    ])
    ok = parsed and parsed.get("overall") == "PASS"
    return {"passed": ok, "message": f"{parsed.get('overall', '?')} ({parsed.get('passed', 0)}/{parsed.get('total', 0)})" if parsed else "parse failed"}


def _test_env_manager_version():
    """Test env manager version is 1.0.0."""
    rc, out, _, _ = _run_script("vibe_test_env_manager.py", ["--version"])
    return {"passed": rc == 0 and "1.0.0" in out, "message": out.strip()[:60]}


def _test_token_policy_version():
    """Token source policy version is 1.0.0."""
    rc, out, _, _ = _run_script("vibe_token_source_policy.py", ["--version"])
    return {"passed": rc == 0 and "1.0.0" in out, "message": out.strip()[:60]}


# ── Runner ─────────────────────────────────────────────────────────────

TESTS = [
    ("self_repo_gh_cached_allowed", _test_self_repo_gh_cached_allowed),
    ("external_push_gh_cached_blocked", _test_external_push_gh_cached_blocked),
    ("external_read_no_token", _test_external_read_no_token),
    ("standard_token_preflight", _test_standard_token_preflight),
    ("token_redaction", _test_token_redaction),
    ("env_manager_self_check", _test_env_manager_self_check),
    ("env_manager_version", _test_env_manager_version),
    ("token_policy_version", _test_token_policy_version),
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
            results.append({"test": name, "result": "ERROR", "message": str(e)[:100]})

    total = passed + failed
    print(f"=== V1.12.2 Token Policy + Env Manager Tests ===")
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
