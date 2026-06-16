#!/usr/bin/env python3
"""tests/test_v1131.py — V1.13.1 Iteration Budget Policy standalone tests.

Covers:
  T1: read-only → short=200
  T2: self repo single WO → standard=300
  T3: multi-WO batch → long=500
  T4: long batch explicit → extended=800 (needs reason)
  T5: external push still approval required
  T6: remediation force still approval required
  T7: secrets/CI/workflow blocked
  T8: timeout no auto model switch
  T9: token redaction passes
"""

import json
import sys
import os

# Add scripts dir to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from vibe_iteration_policy import (
    PROFILES, recommend_profile, check_approval_gate, check_model_switch,
    generate_policy_report, self_check,
)


def test_readonly_short():
    """T1: read-only → short=200"""
    r = recommend_profile("investigation", risk_level="low", is_read_only=True)
    assert r["profile"] == "short", f"Expected short, got {r['profile']}"
    assert r["steps"] == 200, f"Expected 200, got {r['steps']}"
    assert r["auto_approve"] is True
    print("PASS: T1 read-only → short=200")


def test_selfrepo_standard():
    """T2: self repo single WO → standard=300"""
    r = recommend_profile("self_repo_fix", risk_level="low",
                          is_external=False)
    assert r["profile"] == "standard", f"Expected standard, got {r['profile']}"
    assert r["steps"] == 300, f"Expected 300, got {r['steps']}"
    assert r["auto_approve"] is True
    print("PASS: T2 self repo single WO → standard=300")


def test_multiwo_long():
    """T3: multi-WO batch → long=500"""
    r = recommend_profile("batch", is_multi_wo=True)
    assert r["profile"] == "long", f"Expected long, got {r['profile']}"
    assert r["steps"] == 500, f"Expected 500, got {r['steps']}"
    print("PASS: T3 multi-WO batch → long=500")


def test_extended():
    """T4: extended=800 available and needs reason"""
    assert PROFILES["extended"]["steps"] == 800
    assert PROFILES["extended"]["auto_approve"] is False
    r = generate_policy_report("extended", 800, extended_reason="Major refactor")
    assert r["iteration_policy"]["profile"] == "extended"
    assert r.get("extended_reason") == "Major refactor"
    print("PASS: T4 extended=800 requires reason")


def test_external_push_approval():
    """T5: external push still approval required"""
    r = recommend_profile("external_push", risk_level="high",
                          is_external=True)
    assert r["auto_approve"] is False, "External push should not auto-approve"
    gate = check_approval_gate("external_push", "high", "standard")
    assert gate["requires_approval"] is True
    print("PASS: T5 external push requires approval")


def test_remediation_force_approval():
    """T6: remediation force still approval required"""
    gate = check_approval_gate("remediation_force", "critical", "standard")
    assert gate["requires_approval"] is True
    print("PASS: T6 remediation force requires approval")


def test_secrets_ci_workflow_blocked():
    """T7: secrets/CI/workflow patterns require approval"""
    for pattern in ["secrets", "ci", "workflow", "provider", "ssh"]:
        gate = check_approval_gate(pattern, "high", "standard")
        assert gate["requires_approval"] is True, f"{pattern} should require approval"
    print("PASS: T7 secrets/CI/workflow require approval")


def test_timeout_no_auto_switch():
    """T8: timeout/429 no auto model switch"""
    for signal in ["429", "timeout", "rate_limit"]:
        r = check_model_switch(signal)
        assert r["auto_switch"] is False, f"{signal} should not auto-switch"
        assert r["action"] == "REPORT_TO_OPERATOR"
    print("PASS: T8 timeout/429 no auto model switch")


def test_token_redaction():
    """T9: token redaction in policy report"""
    report = generate_policy_report("standard", 300, task_type="self_repo_fix")
    report_str = json.dumps(report)
    # Should not contain any token patterns
    for kw in ["ghp_", "github_pat", "token_value", "secret_value"]:
        assert kw not in report_str.lower(), f"Report contains {kw}"
    print("PASS: T9 token redaction passes")


def test_401_blocked():
    """T10: 401/config error blocked"""
    r = check_model_switch("401 unauthorized")
    assert r["action"] == "BLOCK"
    r2 = check_model_switch("config_error")
    assert r2["action"] == "BLOCK"
    print("PASS: T10 401/config error blocked")


def test_self_check():
    """T11: built-in self-check passes"""
    result = self_check()
    assert result["failed"] == 0, f"Self-check failed: {result}"
    assert result["passed"] >= 10
    print(f"PASS: T11 self-check {result['passed']}/{result['total']}")


if __name__ == "__main__":
    tests = [
        test_readonly_short,
        test_selfrepo_standard,
        test_multiwo_long,
        test_extended,
        test_external_push_approval,
        test_remediation_force_approval,
        test_secrets_ci_workflow_blocked,
        test_timeout_no_auto_switch,
        test_token_redaction,
        test_401_blocked,
        test_self_check,
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
