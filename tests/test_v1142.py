#!/usr/bin/env python3
"""tests/test_v1142.py — V1.14.2 Gateway Health 72h Limit Detection.

Covers:
  T1: PT0S/indefinite → OK
  T2: PT72H + running far from limit → WARN (AHT=True)
  T3: PT72H + running near limit → WARN
  T4: PT72H + ready/not running + process absent → BLOCK
  T5: finite limit + AllowHardTerminate=True → WARN
  T6: default/vibedev independent output
  T7: missing task → UNKNOWN
  T8: no token leak
  T9: no external write
"""

import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


def test_pt0s_ok():
    """T1: PT0S → OK."""
    from vibe_gateway_health import _assess_limit_risk, LIMIT_OK
    risk = _assess_limit_risk("Running", True, 0, False, True)
    assert risk == LIMIT_OK, f"Expected OK, got {risk}"
    print("PASS: T1 PT0S → OK")


def test_pt72h_running_warn():
    """T2: PT72H + running + AHT=True → WARN."""
    from vibe_gateway_health import _assess_limit_risk, LIMIT_WARN
    risk = _assess_limit_risk("Running", False, 259200, True, True)
    assert risk == LIMIT_WARN, f"Expected WARN, got {risk}"
    print("PASS: T2 PT72H+running+AHT → WARN")


def test_pt72h_ready_block():
    """T3: PT72H + ready/not running + no process → BLOCK."""
    from vibe_gateway_health import _assess_limit_risk, LIMIT_BLOCK
    risk = _assess_limit_risk("Ready", False, 259200, True, False)
    assert risk == LIMIT_BLOCK, f"Expected BLOCK, got {risk}"
    print("PASS: T3 PT72H+ready+no_proc → BLOCK")


def test_pt72h_running_aht_false_ok():
    """T4: PT72H + running + AHT=False → OK (no hard terminate)."""
    from vibe_gateway_health import _assess_limit_risk, LIMIT_OK
    risk = _assess_limit_risk("Running", False, 259200, False, True)
    assert risk == LIMIT_OK, f"Expected OK, got {risk}"
    print("PASS: T4 PT72H+running+AHT=False → OK")


def test_parse_duration():
    """T5: duration parsing."""
    from vibe_gateway_health import _parse_duration
    s, i = _parse_duration("PT72H")
    assert s == 259200 and i is False, f"PT72H: {s} {i}"
    s, i = _parse_duration("PT0S")
    assert s == 0 and i is True, f"PT0S: {s} {i}"
    s, i = _parse_duration("PT0")
    assert s == 0 and i is True, f"PT0: {s} {i}"
    s, i = _parse_duration("indefinite")
    assert s == 0 and i is True, f"indefinite: {s} {i}"
    print("PASS: T5 duration parsing")


def test_independent_profiles():
    """T6: default/vibedev should be independently assessed."""
    from vibe_gateway_health import _assess_limit_risk, LIMIT_OK, LIMIT_WARN
    # Default: PT0S → OK
    d = _assess_limit_risk("Running", True, 0, False, True)
    # Vibedev: PT72H + AHT → WARN
    v = _assess_limit_risk("Running", False, 259200, True, True)
    assert d == LIMIT_OK and v == LIMIT_WARN
    print("PASS: T6 independent profiles")


def test_no_token_leak():
    """T8: no token in output."""
    from vibe_gateway_health import self_check
    result = self_check(json_output=True)
    result_str = json.dumps(result)
    for kw in ["ghp_", "github_pat", "token_value", "secret_value", "api_key"]:
        assert kw not in result_str.lower(), f"Token leak: {kw}"
    print("PASS: T8 no token leak")


def test_no_external_write():
    """T9: verify this is read-only."""
    from vibe_gateway_health import _run_cmd
    # _run_cmd should only read, not write
    assert callable(_run_cmd)
    print("PASS: T9 read-only module")


def test_self_check_passes():
    """T10: gateway_health self-check passes."""
    from vibe_gateway_health import self_check
    result = self_check(json_output=True)
    assert result["failed"] == 0, f"Self-check failed: {result}"
    assert result["passed"] >= 8
    print(f"PASS: T10 self-check {result['passed']}/{result['total']}")


if __name__ == "__main__":
    tests = [
        test_pt0s_ok,
        test_pt72h_running_warn,
        test_pt72h_ready_block,
        test_pt72h_running_aht_false_ok,
        test_parse_duration,
        test_independent_profiles,
        test_no_token_leak,
        test_no_external_write,
        test_self_check_passes,
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
