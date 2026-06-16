#!/usr/bin/env python3
"""Smoke tests for vibe_external_authorized_push.py.

Tests the external authorized push wrapper with isolated temp environments.
No real push is ever executed. No token content is read or output.
"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "vibe_external_authorized_push.py"
)

# ── Helpers ────────────────────────────────────────────────────────────

def _run(args, env_extra=None):
    """Run the script and return (rc, stdout, stderr, parsed_json)."""
    env = os.environ.copy()
    # Ensure no non-standard token env vars leak in
    for var in [
        "GITHUB_PAT", "GITHUB_TOKEN", "GH_TOKEN",
        "GITHUB_AUTH_TOKEN", "GH_ENTERPRISE_TOKEN",
    ]:
        env.pop(var, None)
    if env_extra:
        env.update(env_extra)

    proc = subprocess.run(
        [sys.executable, SCRIPT] + args,
        capture_output=True, text=True, timeout=30, env=env,
    )
    parsed = None
    if proc.stdout.strip():
        try:
            parsed = json.loads(proc.stdout)
        except json.JSONDecodeError:
            pass
    return proc.returncode, proc.stdout, proc.stderr, parsed


def _make_token_file(tmpdir, content="ghp_test_token_1234567890abcdef", mode=0o600):
    """Create a fake token file."""
    path = os.path.join(tmpdir, "github_privileged_token")
    with open(path, "w") as f:
        f.write(content)
    os.chmod(path, mode)
    return path


def _make_approval(tmpdir, approval_id, overrides=None):
    """Create a test approval file."""
    record = {
        "approval_id": approval_id,
        "repo": "some-org/some-repo",
        "branch": "feat/test",
        "operation": "push",
        "base_sha": "abc123",
        "local_commit_sha": "def456",
        "remote_branch_current_sha": "abc123",
        "changed_paths": ["tools/test.py"],
        "patch_sha256": "aabbccdd",
        "expires_at": 9999999999,
        "status": "approved",
        "force_push": False,
        "delete_branch": False,
        "merge_pr": False,
        "token_source": "/home/vibeworker/.vibedev/secrets/github_privileged_token",
        "allowed_operations": ["push"],
    }
    if overrides:
        record.update(overrides)

    path = os.path.join(tmpdir, f"{approval_id}.json")
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    return path, record


# ── Test Functions ─────────────────────────────────────────────────────

def _test_version():
    """Script reports version."""
    rc, stdout, stderr, parsed = _run(["--version"])
    return {"passed": rc == 0 and "1.0.0" in stdout, "message": stdout.strip()}


def _test_token_preflight_ok():
    """Token preflight passes with correct file."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        token_path = _make_token_file(tmpdir)
        rc, stdout, stderr, parsed = _run(
            ["--json", "--token-file", token_path, "token-preflight"]
        )
        ok = parsed and parsed.get("ok") is True
        return {"passed": ok, "message": f"rc={rc} ok={parsed.get('ok') if parsed else 'N/A'}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_token_preflight_missing():
    """Token preflight fails when file missing."""
    rc, stdout, stderr, parsed = _run(
        ["--json", "--token-file", "/nonexistent/path", "token-preflight"]
    )
    ok = parsed and parsed.get("ok") is False
    return {"passed": ok, "message": f"rc={rc} ok={parsed.get('ok') if parsed else 'N/A'}"}


def _test_token_preflight_bad_mode():
    """Token preflight fails when mode != 600."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        token_path = _make_token_file(tmpdir, mode=0o644)
        rc, stdout, stderr, parsed = _run(
            ["--json", "--token-file", token_path, "token-preflight"]
        )
        ok = parsed and parsed.get("ok") is False
        return {"passed": ok, "message": f"rc={rc} ok={parsed.get('ok') if parsed else 'N/A'}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_validate_valid_approval():
    """Valid approval passes validation."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        _make_approval(tmpdir, "test-valid-001")
        rc, stdout, stderr, parsed = _run(
            ["--json", "--approval-dir", tmpdir, "validate", "--approval-id", "test-valid-001"]
        )
        ok = parsed and parsed.get("would_push") is True
        return {"passed": ok, "message": f"rc={rc} would_push={parsed.get('would_push') if parsed else 'N/A'}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_validate_no_approval():
    """Missing approval returns error."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        rc, stdout, stderr, parsed = _run(
            ["--json", "--approval-dir", tmpdir, "validate", "--approval-id", "nonexistent"]
        )
        ok = rc != 0 and (parsed and "error" in parsed)
        return {"passed": ok, "message": f"rc={rc} error={parsed.get('error') if parsed else 'N/A'}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_validate_expired():
    """Expired approval is blocked."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        _make_approval(tmpdir, "test-expired-001", {"expires_at": 1})
        rc, stdout, stderr, parsed = _run(
            ["--json", "--approval-dir", tmpdir, "validate", "--approval-id", "test-expired-001"]
        )
        ok = parsed and parsed.get("would_push") is False
        blockers = parsed.get("blockers", []) if parsed else []
        has_expired = any("expired" in b for b in blockers)
        return {"passed": ok and has_expired, "message": f"rc={rc} blockers={blockers[:2]}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_validate_forbidden_path_workflow():
    """Forbidden .github/workflows/ path is blocked."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        _make_approval(tmpdir, "test-forbid-wf", {
            "changed_paths": [".github/workflows/ci.yml"]
        })
        rc, stdout, stderr, parsed = _run(
            ["--json", "--approval-dir", tmpdir, "validate", "--approval-id", "test-forbid-wf"]
        )
        ok = parsed and parsed.get("would_push") is False
        blockers = parsed.get("blockers", []) if parsed else []
        has_forbidden = any("forbidden" in b for b in blockers)
        return {"passed": ok and has_forbidden, "message": f"rc={rc} blockers={blockers[:2]}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_validate_forbidden_path_secrets():
    """Forbidden secrets/ path is blocked."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        _make_approval(tmpdir, "test-forbid-sec", {
            "changed_paths": ["secrets/config.json"]
        })
        rc, stdout, stderr, parsed = _run(
            ["--json", "--approval-dir", tmpdir, "validate", "--approval-id", "test-forbid-sec"]
        )
        ok = parsed and parsed.get("would_push") is False
        return {"passed": ok, "message": f"rc={rc} would_push={parsed.get('would_push') if parsed else 'N/A'}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_validate_force_push():
    """Force push is blocked."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        _make_approval(tmpdir, "test-force", {"force_push": True})
        rc, stdout, stderr, parsed = _run(
            ["--json", "--approval-dir", tmpdir, "validate", "--approval-id", "test-force"]
        )
        ok = parsed and parsed.get("would_push") is False
        blockers = parsed.get("blockers", []) if parsed else []
        has_force = any("force" in b.lower() for b in blockers)
        return {"passed": ok and has_force, "message": f"rc={rc} blockers={blockers[:2]}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_validate_delete_branch():
    """Delete branch is blocked."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        _make_approval(tmpdir, "test-delete", {"delete_branch": True})
        rc, stdout, stderr, parsed = _run(
            ["--json", "--approval-dir", tmpdir, "validate", "--approval-id", "test-delete"]
        )
        ok = parsed and parsed.get("would_push") is False
        return {"passed": ok, "message": f"rc={rc} would_push={parsed.get('would_push') if parsed else 'N/A'}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_validate_wrong_operation():
    """Non-push operation is blocked."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        _make_approval(tmpdir, "test-op", {"operation": "merge"})
        rc, stdout, stderr, parsed = _run(
            ["--json", "--approval-dir", tmpdir, "validate", "--approval-id", "test-op"]
        )
        ok = parsed and parsed.get("would_push") is False
        return {"passed": ok, "message": f"rc={rc} would_push={parsed.get('would_push') if parsed else 'N/A'}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_validate_missing_fields():
    """Missing required fields is blocked."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        record = {"approval_id": "test-missing", "repo": "org/repo"}
        path = os.path.join(tmpdir, "test-missing.json")
        with open(path, "w") as f:
            json.dump(record, f)
        rc, stdout, stderr, parsed = _run(
            ["--json", "--approval-dir", tmpdir, "validate", "--approval-id", "test-missing"]
        )
        ok = parsed and parsed.get("would_push") is False
        blockers = parsed.get("blockers", []) if parsed else []
        has_missing = any("missing" in b.lower() for b in blockers)
        return {"passed": ok and has_missing, "message": f"rc={rc} blockers={blockers[:2]}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_non_standard_env_detected():
    """Non-standard token env vars are detected."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        _make_approval(tmpdir, "test-env")
        rc, stdout, stderr, parsed = _run(
            ["--json", "--approval-dir", tmpdir, "validate", "--approval-id", "test-env"],
            env_extra={"GITHUB_PAT": "fake_token_value"},
        )
        ok = parsed and parsed.get("non_standard_env_clean") is False
        violations = parsed.get("env_violations", []) if parsed else []
        return {"passed": ok and len(violations) > 0, "message": f"violations={violations[:2]}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_token_not_in_output():
    """Token content never appears in output."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        token_path = _make_token_file(tmpdir, content="ghp_SUPERSECRET_12345")
        rc, stdout, stderr, parsed = _run(
            ["--json", "--token-file", token_path, "token-preflight"]
        )
        combined = stdout + stderr
        has_secret = "ghp_SUPERSECRET_12345" in combined
        return {"passed": not has_secret, "message": f"secret_in_output={has_secret}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_command_preview_no_token():
    """Command preview does not contain token."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        token_path = _make_token_file(tmpdir)
        _make_approval(tmpdir, "test-preview")
        rc, stdout, stderr, parsed = _run(
            ["--json", "--approval-dir", tmpdir, "--token-file", token_path,
             "dry-run", "--approval-id", "test-preview"]
        )
        combined = stdout + stderr
        # Check that push_preview doesn't contain the token
        preview = (parsed or {}).get("push_preview", "")
        safe_cmd = (parsed or {}).get("push_command_safe", "")
        has_token = "ghp_test_token_1234567890abcdef" in preview
        return {
            "passed": not has_token,
            "message": f"token_in_preview={has_token} preview={preview[:60]}"
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_list():
    """List command works."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        _make_approval(tmpdir, "test-list-1")
        _make_approval(tmpdir, "test-list-2")
        rc, stdout, stderr, parsed = _run(
            ["--json", "--approval-dir", tmpdir, "list"]
        )
        ok = parsed and parsed.get("total") == 2
        return {"passed": ok, "message": f"total={parsed.get('total') if parsed else 'N/A'}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_validate_patch_sha_mismatch():
    """Patch SHA mismatch is noted (not blocked - can't verify without remote)."""
    tmpdir = tempfile.mkdtemp(prefix="eap-test-")
    try:
        _make_approval(tmpdir, "test-patch", {
            "patch_sha256": "different_sha_value"
        })
        rc, stdout, stderr, parsed = _run(
            ["--json", "--approval-dir", tmpdir, "validate", "--approval-id", "test-patch"]
        )
        # Validation should still pass (patch_sha is stored, not verified during validate)
        ok = parsed and parsed.get("would_push") is True
        return {"passed": ok, "message": f"would_push={parsed.get('would_push') if parsed else 'N/A'}"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ── Runner ─────────────────────────────────────────────────────────────

TESTS = [
    ("version", _test_version),
    ("token_preflight_ok", _test_token_preflight_ok),
    ("token_preflight_missing", _test_token_preflight_missing),
    ("token_preflight_bad_mode", _test_token_preflight_bad_mode),
    ("validate_valid_approval", _test_validate_valid_approval),
    ("validate_no_approval", _test_validate_no_approval),
    ("validate_expired", _test_validate_expired),
    ("validate_forbidden_path_workflow", _test_validate_forbidden_path_workflow),
    ("validate_forbidden_path_secrets", _test_validate_forbidden_path_secrets),
    ("validate_force_push", _test_validate_force_push),
    ("validate_delete_branch", _test_validate_delete_branch),
    ("validate_wrong_operation", _test_validate_wrong_operation),
    ("validate_missing_fields", _test_validate_missing_fields),
    ("non_standard_env_detected", _test_non_standard_env_detected),
    ("token_not_in_output", _test_token_not_in_output),
    ("command_preview_no_token", _test_command_preview_no_token),
    ("list", _test_list),
    ("validate_patch_sha_mismatch", _test_validate_patch_sha_mismatch),
]


def main():
    passed = 0
    failed = 0
    results = []

    for name, func in TESTS:
        try:
            r = func()
            ok = r.get("passed", False)
            if ok:
                passed += 1
                icon = "PASS"
            else:
                failed += 1
                icon = "FAIL"
            results.append({"test": name, "result": icon, "message": r.get("message", "")})
        except Exception as e:
            failed += 1
            results.append({"test": name, "result": "ERROR", "message": str(e)})

    total = passed + failed
    print(f"=== External Authorized Push Smoke Tests ===")
    print(f"Total: {total} | Passed: {passed} | Failed: {failed}")
    print()
    for r in results:
        print(f"  [{r['result']}] {r['test']}: {r['message']}")

    if failed > 0:
        print(f"\nFAILED: {failed} tests")
        return 1
    else:
        print(f"\nALL {total} TESTS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
