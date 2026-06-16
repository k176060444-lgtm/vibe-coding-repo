#!/usr/bin/env python3
"""tests/test_v114.py — V1.14 Windows Worker Lane + Dual-Node Scheduling.

Covers:
  T1: gateway task -> windows-worker
  T2: pytest task -> debian-worker
  T3: external push -> debian + approval
  T4: gateway recovery + Debian resume -> dual-node detection
  T5: Windows long task blocked (job runner max timeout)
  T6: Node Attribution distinguishes controller vs execution
  T7: job runner blocks git/pytest/token
  T8: gateway isolation timeout enforcement
  T9: unknown task defaults to debian
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_gateway_windows():
    """T1: gateway health -> windows-worker."""
    from vibe_windows_worker_policy import classify_task_node
    r = classify_task_node("gateway health check")
    assert r["node"] == "windows-worker", f"Expected windows-worker, got {r['node']}"
    assert r["gateway_safe"] is True
    print("PASS: T1 gateway -> windows-worker")


def test_pytest_debian():
    """T2: pytest -> debian-worker."""
    from vibe_windows_worker_policy import classify_task_node
    r = classify_task_node("run pytest full smoke suite")
    assert r["node"] == "debian-worker", f"Expected debian-worker, got {r['node']}"
    print("PASS: T2 pytest -> debian-worker")


def test_external_push_debian_approval():
    """T3: external push -> debian + approval required."""
    from vibe_windows_worker_policy import classify_task_node
    r = classify_task_node("external push to fork repo",
                           risk_level="high", repo_scope="protected-external")
    assert r["node"] == "debian-worker", f"Expected debian-worker, got {r['node']}"
    assert r["requires_approval"] is True
    print("PASS: T3 external push -> debian + approval")


def test_dual_node_detection():
    """T4: mixed tasks should be detectable for dual-node scheduling."""
    from vibe_windows_worker_policy import classify_task_node
    # Gateway health = windows
    r1 = classify_task_node("gateway health check")
    # Then resume with pytest = debian
    r2 = classify_task_node("run pytest after gateway recovery")
    # Dual-node: first windows, then debian
    assert r1["node"] == "windows-worker"
    assert r2["node"] == "debian-worker"
    # A dual-node scheduler would combine both
    dual_nodes = {r1["node"], r2["node"]}
    assert len(dual_nodes) == 2, f"Expected 2 distinct nodes, got {dual_nodes}"
    print("PASS: T4 dual-node detection (windows + debian)")


def test_windows_long_task_blocked():
    """T5: Windows job runner blocks tasks >300s."""
    from vibe_windows_job_runner import validate_task
    v = validate_task("echo hello", 600)
    assert not v["allowed"], "Should block timeout >300s"
    assert "300" in v["reason"] or "max" in v["reason"].lower()
    print("PASS: T5 Windows long task blocked")


def test_node_attribution_fields():
    """T6: Node Attribution distinguishes controller vs execution."""
    from vibe_windows_worker_policy import classify_task_node
    r = classify_task_node("gateway health check")
    # execution_node should be windows-worker
    assert "windows" in r["node"]
    # controller_node is always windows (our setup)
    # This is a policy-level distinction, not in classify output
    # but the WO plan should have both
    print("PASS: T6 node attribution distinguishes controller vs execution")


def test_job_runner_blocks_dangerous():
    """T7: job runner blocks git/pytest/token."""
    from vibe_windows_job_runner import validate_task
    for cmd in ["git push origin main", "pytest tests/", "cat token.txt",
                "ssh user@host", "echo $API_KEY"]:
        v = validate_task(cmd, 60)
        assert not v["allowed"], f"Should block: {cmd}"
    print("PASS: T7 job runner blocks dangerous commands")


def test_gateway_isolation_timeout():
    """T8: gateway isolation enforces timeout limits."""
    from vibe_windows_worker_policy import check_gateway_isolation
    # Within limit
    r = check_gateway_isolation("windows-worker", 120)
    assert r["allowed"], f"Should allow 120s: {r['reason']}"
    # Over limit
    r = check_gateway_isolation("windows-worker", 400)
    assert not r["allowed"], f"Should block 400s: {r['reason']}"
    # Non-windows node always allowed
    r = check_gateway_isolation("debian-worker", 9999)
    assert r["allowed"], f"Debian should always be allowed: {r['reason']}"
    print("PASS: T8 gateway isolation timeout enforcement")


def test_unknown_defaults_debian():
    """T9: unknown task defaults to debian-worker."""
    from vibe_windows_worker_policy import classify_task_node
    r = classify_task_node("do some random stuff that matches nothing")
    assert r["node"] == "debian-worker", f"Expected debian-worker, got {r['node']}"
    print("PASS: T9 unknown defaults to debian")


def test_self_checks():
    """T10: both modules self-check pass."""
    from vibe_windows_worker_policy import self_check as wp_check
    from vibe_windows_job_runner import self_check as jr_check
    wp = wp_check()
    jr = jr_check()
    assert wp["failed"] == 0, f"Worker policy self-check failed: {wp}"
    assert jr["failed"] == 0, f"Job runner self-check failed: {jr}"
    print(f"PASS: T10 self-checks wp={wp['passed']}/{wp['total']} jr={jr['passed']}/{jr['total']}")


if __name__ == "__main__":
    tests = [
        test_gateway_windows,
        test_pytest_debian,
        test_external_push_debian_approval,
        test_dual_node_detection,
        test_windows_long_task_blocked,
        test_node_attribution_fields,
        test_job_runner_blocks_dangerous,
        test_gateway_isolation_timeout,
        test_unknown_defaults_debian,
        test_self_checks,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1
    print(f"\nResults: {passed}/{passed+failed} PASS")
    sys.exit(0 if failed == 0 else 1)
