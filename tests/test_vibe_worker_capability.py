#!/usr/bin/env python3
"""tests/test_vibe_worker_capability.py — Unit tests for scripts/vibe_worker_capability.py

Covers deterministic, pure-function behavior:
  T1: detect_capabilities(worker_id=...) accepts string worker_id
  T2: "windows" / "controller" → is_controller=True
  T3: "5bao" / "9bao" / arbitrary → is_controller=False
  T4: "unknown" when worker_id=None and no env var
  T5: returned dict has expected keys
  T6: bool field types (pytest_available etc. are bool)
  T7: worker_id explicitly passed overrides env var
  T8: self_check structure (overall + checks + capabilities keys)
  T9: self_check all 4 sub-checks present
"""
import importlib
import os
import sys

import pytest

# Add scripts dir to path
SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")
sys.path.insert(0, SCRIPTS)

import vibe_worker_capability as vwc  # noqa: E402

EXPECTED_KEYS = {
    "worker_id",
    "test_python",
    "system_python",
    "pytest_available",
    "pytest_timeout_available",
    "is_controller",
    "has_privileged_token",
    "has_audit_tainted_lock",
}


@pytest.fixture(autouse=True)
def _isolate_worker_id_env(monkeypatch):
    """Ensure VIBEDEV_WORKER_ID is unset unless a test sets it."""
    monkeypatch.delenv("VIBEDEV_WORKER_ID", raising=False)


def test_detect_accepts_explicit_worker_id():
    """T1: detect_capabilities(worker_id=...) accepts a string worker_id."""
    caps = vwc.detect_capabilities(worker_id="5bao")
    assert caps["worker_id"] == "5bao"


def test_windows_worker_id_is_controller():
    """T2: 'windows' / 'controller' → is_controller=True."""
    for wid in ("windows", "controller"):
        caps = vwc.detect_capabilities(worker_id=wid)
        assert caps["worker_id"] == wid
        assert caps["is_controller"] is True, f"{wid} should be controller"


def test_debian_workers_are_not_controller():
    """T3: '5bao' / '9bao' / arbitrary worker_id → is_controller=False."""
    for wid in ("5bao", "9bao", "custom-node-1", "any-other-id"):
        caps = vwc.detect_capabilities(worker_id=wid)
        assert caps["worker_id"] == wid
        assert caps["is_controller"] is False, f"{wid} should not be controller"


def test_unknown_worker_id_when_none_and_no_env(monkeypatch):
    """T4: with worker_id=None and no env var, worker_id is 'unknown'."""
    monkeypatch.delenv("VIBEDEV_WORKER_ID", raising=False)
    caps = vwc.detect_capabilities(worker_id=None)
    assert caps["worker_id"] == "unknown"
    assert caps["is_controller"] is False


def test_returns_expected_keys():
    """T5: returned dict has the expected capability keys."""
    caps = vwc.detect_capabilities(worker_id="5bao")
    assert EXPECTED_KEYS.issubset(set(caps.keys())), \
        f"missing keys: {EXPECTED_KEYS - set(caps.keys())}"


def test_bool_fields_are_bool():
    """T6: capability bool fields are actual booleans, not None / 1 / 0."""
    caps = vwc.detect_capabilities(worker_id="5bao")
    bool_keys = [
        "pytest_available",
        "pytest_timeout_available",
        "is_controller",
        "has_privileged_token",
        "has_audit_tainted_lock",
    ]
    for k in bool_keys:
        assert isinstance(caps[k], bool), f"{k} should be bool, got {type(caps[k]).__name__}"


def test_explicit_worker_id_overrides_env(monkeypatch):
    """T7: explicit worker_id=... overrides VIBEDEV_WORKER_ID env var."""
    monkeypatch.setenv("VIBEDEV_WORKER_ID", "from-env")
    caps = vwc.detect_capabilities(worker_id="from-arg")
    assert caps["worker_id"] == "from-arg", "arg should win over env"


def test_env_var_used_when_arg_is_none(monkeypatch):
    """T7b: with worker_id=None and env set, env value is used."""
    monkeypatch.setenv("VIBEDEV_WORKER_ID", "from-env")
    caps = vwc.detect_capabilities(worker_id=None)
    assert caps["worker_id"] == "from-env"


def test_self_check_structure():
    """T8: self_check returns dict with overall, passed, total, checks, capabilities."""
    result = vwc.self_check()
    assert isinstance(result, dict)
    assert "overall" in result
    assert result["overall"] in ("PASS", "FAIL")
    assert "passed" in result
    assert "total" in result
    assert "checks" in result
    assert "capabilities" in result
    assert isinstance(result["checks"], list)
    assert isinstance(result["capabilities"], dict)


def test_self_check_has_expected_subchecks():
    """T9: self_check has the 4 expected sub-checks."""
    result = vwc.self_check()
    check_names = [c["name"] for c in result["checks"]]
    expected = {"version", "detection_works", "worker_id_set", "no_secret_leak"}
    assert expected.issubset(set(check_names)), \
        f"missing checks: {expected - set(check_names)}"
    # passed must equal total when all sub-checks pass (current behavior)
    assert result["passed"] == result["total"], \
        f"self_check should be all-pass: passed={result['passed']} total={result['total']}"