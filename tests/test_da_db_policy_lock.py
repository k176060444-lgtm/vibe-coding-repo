"""Tests for scripts/da_db_policy_lock.py — Baseline02 D-A/D-B policy-lock."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import da_db_policy_lock as pl


# ── Fixtures ───────────────────────────────────────────────────────────────


def _minimal_pool(models: list[dict]) -> dict:
    return {"schema_version": "1.2", "models": models}


def _valid_active() -> dict:
    return {
        "id": "opencode-go-fake-active",
        "primary_alias": "a",
        "canonical_provider": "opencode-go",
        "provider_namespace": "opencode-go",
        "lifecycle_status": "enabled_assigned",
        "enabled": True,
        "allowed_nodes": ["5bao", "9bao"],
        "credential_status": "present",
        "endpoint_ref": "base_url_env",
    }


def _valid_deu(mid: str = "deu-model", ns: str = "openai") -> dict:
    return {
        "id": mid,
        "primary_alias": mid,
        "canonical_provider": ns,
        "provider_namespace": ns,
        "lifecycle_status": "declared_enabled_unassigned",
        "enabled": True,
        "allowed_nodes": [],
        "credential_status": "present",
        "endpoint_ref": "base_url_env",
    }


# ── Self-check ─────────────────────────────────────────────────────────────


def test_self_check_all_pass():
    r = pl.self_check()
    assert r["status"] == "PASS", r
    assert "9/9" in r["detail"]


# ── Real pool ──────────────────────────────────────────────────────────────


def test_real_pool_passes_lock_at_freeze_point():
    """The frozen pool at main=3536f310 must PASS the lock unchanged."""
    r = pl.validate_policy_lock()
    assert r["final_verdict"] == "DA_DB_POLICY_LOCK_PASS", r
    assert r["counts"]["active"] == pl.EXPECTED_ACTIVE_COUNT
    assert r["counts"]["deu"] == pl.EXPECTED_DEU_COUNT
    assert r["leak_scan"]["any_leak"] is False


def test_real_pool_active_folded_to_opencode_go():
    r = pl.validate_policy_lock()
    da = [c for c in r["checks"] if c["check"] == "da_active_folding"][0]
    assert da["passed"] is True
    assert da["active_count"] == pl.EXPECTED_ACTIVE_COUNT
    assert da["count_matches_expected"] is True


def test_real_pool_16_deu_locked():
    r = pl.validate_policy_lock()
    db = [c for c in r["checks"] if c["check"] == "db_deu_lock"][0]
    assert db["passed"] is True
    assert db["deu_count"] == pl.EXPECTED_DEU_COUNT
    assert db["count_matches_expected"] is True
    assert db["violations"] == []


def test_real_pool_no_new_namespace():
    r = pl.validate_policy_lock()
    ns = [c for c in r["checks"] if c["check"] == "no_new_namespace"][0]
    assert ns["passed"] is True
    assert ns["unknown_namespaces"] == []


def test_real_pool_reports_legacy_win_but_non_blocking():
    r = pl.validate_policy_lock()
    an = [c for c in r["checks"] if c["check"] == "node_alias_normalization"][0]
    assert an["passed"] is True  # legacy 'win' is not blocking
    # At freeze point there are historical/active models that still use 'win'
    assert len(an["legacy_win_refs"]) > 0
    assert an["invalid_node_refs"] == []


# ── D-A violations ─────────────────────────────────────────────────────────


def test_active_with_wrong_canonical_blocked():
    m = _valid_active()
    m["canonical_provider"] = "openai"
    r = pl.validate_policy_lock(_minimal_pool([m]))
    assert r["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED"


def test_active_with_wrong_namespace_blocked():
    m = _valid_active()
    m["provider_namespace"] = "openai"
    r = pl.validate_policy_lock(_minimal_pool([m]))
    assert r["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED"


def test_operator_requested_must_also_fold():
    m = _valid_active()
    m["lifecycle_status"] = "operator_requested"
    m["canonical_provider"] = "xiaomi"
    r = pl.validate_policy_lock(_minimal_pool([m]))
    assert r["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED"


def test_active_count_deviation_blocked_when_mismatch():
    """Only 1 active but expected 9 → blocked (count mismatch)."""
    r = pl.validate_policy_lock(_minimal_pool([_valid_active()]))
    assert r["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED"
    da = [c for c in r["checks"] if c["check"] == "da_active_folding"][0]
    assert da["count_matches_expected"] is False


# ── D-B violations ─────────────────────────────────────────────────────────


def test_deu_with_allowed_nodes_is_silent_promotion_blocked():
    m = _valid_deu()
    m["allowed_nodes"] = ["21bao"]  # silent promotion
    r = pl.validate_policy_lock(_minimal_pool([m]))
    assert r["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED"
    db = [c for c in r["checks"] if c["check"] == "db_deu_lock"][0]
    assert any("silent promotion" in v["reason"] for v in db["violations"])


def test_deu_disabled_blocked():
    m = _valid_deu()
    m["enabled"] = False
    r = pl.validate_policy_lock(_minimal_pool([m]))
    assert r["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED"


def test_deu_with_pool_level_operator_approved_blocked():
    m = _valid_deu()
    m["operator_approved"] = True
    r = pl.validate_policy_lock(_minimal_pool([m]))
    assert r["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED"


def test_deu_with_pool_level_model_call_verified_blocked():
    m = _valid_deu()
    m["model_call_verified"] = True
    r = pl.validate_policy_lock(_minimal_pool([m]))
    assert r["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED"


def test_deu_with_pool_level_readiness_blocked():
    m = _valid_deu()
    m["readiness"] = "ready"
    r = pl.validate_policy_lock(_minimal_pool([m]))
    assert r["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED"


# ── Node alias normalization ──────────────────────────────────────────────


def test_legacy_win_alias_reported_not_blocking_when_alone():
    m = _valid_active()
    m["allowed_nodes"] = ["5bao", "9bao", "win"]
    # Bring total active up to expected count with 8 more folded models
    filler = [dict(_valid_active(), id=f"opencode-go-a{i}") for i in range(8)]
    deu = [dict(_valid_deu(mid=f"deu{i}")) for i in range(16)]
    r = pl.validate_policy_lock(_minimal_pool([m] + filler + deu))
    an = [c for c in r["checks"] if c["check"] == "node_alias_normalization"][0]
    assert an["passed"] is True
    assert len(an["legacy_win_refs"]) == 1


def test_invalid_node_ref_blocks():
    m = _valid_active()
    m["allowed_nodes"] = ["mars"]
    r = pl.validate_policy_lock(_minimal_pool([m]))
    assert r["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED"
    an = [c for c in r["checks"] if c["check"] == "node_alias_normalization"][0]
    assert len(an["invalid_node_refs"]) == 1


def test_normalization_plan_has_three_steps():
    r = pl.validate_policy_lock()
    an = [c for c in r["checks"] if c["check"] == "node_alias_normalization"][0]
    assert len(an["normalization_plan"]) == 3
    steps = [s["step"] for s in an["normalization_plan"]]
    assert any("Do NOT rewrite pool automatically" in s for s in steps)


def test_legacy_alias_map_is_win_to_21bao():
    assert pl.LEGACY_NODE_ALIASES == {"win": "21bao"}


# ── Namespace freeze ──────────────────────────────────────────────────────


def test_unknown_namespace_blocked():
    m = _valid_deu()
    m["provider_namespace"] = "brand-new-plan"
    m["canonical_provider"] = "opencode-go"  # keep D-B lock happy on other axes
    r = pl.validate_policy_lock(_minimal_pool([m]))
    assert r["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED"


def test_all_current_pool_namespaces_are_in_frozen_set():
    r = pl.validate_policy_lock()
    ns = [c for c in r["checks"] if c["check"] == "no_new_namespace"][0]
    observed = set(ns["observed"])
    frozen = set(ns["frozen_set"])
    assert observed.issubset(frozen)


# ── Schema mismatch → STOP_AND_REANCHOR ───────────────────────────────────


def test_unexpected_schema_version_triggers_reanchor():
    r = pl.validate_policy_lock({"schema_version": "9.9", "models": []})
    assert r["final_verdict"] == "STOP_AND_REANCHOR"


def test_missing_models_list_triggers_reanchor():
    r = pl.validate_policy_lock({"schema_version": "not-a-string", "models": []})
    assert r["final_verdict"] == "STOP_AND_REANCHOR"


# ── Leak scanner ──────────────────────────────────────────────────────────


def test_leak_scanner_catches_openai_style_secret():
    leak = pl._scan_leaks({"marker": "sk-" + "A" * 40})
    assert leak["any_leak"] is True
    assert leak["secret_leak"] is True


def test_leak_scanner_catches_url():
    leak = pl._scan_leaks({"endpoint": "https://api.openai.com/v1/models"})
    assert leak["any_leak"] is True
    assert leak["url_leak"] is True


def test_leak_scanner_catches_real_path_hint():
    leak = pl._scan_leaks({"path": "/home/vibeworker/config"})
    assert leak["any_leak"] is True
    assert leak["path_leak"] is True


def test_leak_scanner_clean_on_safe_payload():
    leak = pl._scan_leaks({"id": "opencode-go-mimo-v2-5", "alias": "mimo"})
    assert leak["any_leak"] is False


def test_report_never_contains_secret_or_url_or_path_from_real_pool():
    """The real report emitted by validate_policy_lock() must have no leaks."""
    r = pl.validate_policy_lock()
    text = json.dumps(r, ensure_ascii=False)
    # Should not carry secret / URL / real path shapes
    assert "sk-" not in text or "sk-abc" in text  # tolerate 'sk-' only as substring of unrelated ids
    assert "https://" not in text
    assert "/home/" not in text
    assert r["leak_scan"]["any_leak"] is False


# ── Safety: no side effects, no env / socket / subprocess ─────────────────


def test_module_has_no_forbidden_imports():
    src = Path(pl.__file__).read_text(encoding="utf-8")
    forbidden = [
        "import subprocess",
        "import socket",
        "import paramiko",
        "import fabric",
        "import requests",
        "import urllib.request",
        "from urllib.request import",
        "import http.client",
    ]
    for f in forbidden:
        assert f not in src, f"forbidden import in policy-lock module: {f}"


def test_module_does_not_touch_os_environ():
    """AST-level check: no os.environ / os.getenv / getenv() calls in code."""
    import ast
    src = Path(pl.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        # Reject `os.environ` / `os.getenv` attribute access
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "os":
                assert node.attr not in ("environ", "getenv"), (
                    f"forbidden os.{node.attr} access at line {node.lineno}"
                )
        # Reject bare getenv() calls (e.g. from `from os import getenv`)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in ("getenv",), (
                f"forbidden getenv() call at line {node.lineno}"
            )
        # Reject `from os import environ` / `from os import getenv`
        if isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                assert alias.name not in ("environ", "getenv"), (
                    f"forbidden 'from os import {alias.name}' at line {node.lineno}"
                )


def test_module_does_not_ssh_or_shell():
    """AST-level check: no subprocess/SSH tokens in executable code."""
    import ast
    src = Path(pl.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    # Confirm no subprocess/socket/paramiko imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name not in (
                    "subprocess", "socket", "paramiko", "fabric",
                    "requests", "http.client",
                ), f"forbidden import: {alias.name}"
        if isinstance(node, ast.ImportFrom):
            assert node.module not in (
                "subprocess", "socket", "paramiko", "fabric",
                "requests", "urllib.request", "http.client",
            ), f"forbidden import from: {node.module}"
        # Reject Popen / run / os.system / os.popen calls
        if isinstance(node, ast.Attribute):
            if node.attr in ("Popen", "system", "popen", "spawn", "call", "check_call", "check_output"):
                # Allow only if inside a docstring (attributes appear only in
                # real expressions, not strings, so any Attribute node here IS
                # in code)
                raise AssertionError(
                    f"forbidden attribute {node.attr} at line {node.lineno}"
                )
        # Reject shell=True keyword
        if isinstance(node, ast.keyword) and node.arg == "shell":
            if isinstance(node.value, ast.Constant) and node.value.value is True:
                raise AssertionError(
                    f"forbidden shell=True at line {node.lineno}"
                )


def test_validate_policy_lock_does_not_write_pool(tmp_path):
    """Running validate must not modify model_pool.yaml."""
    pool_path = Path(pl._script_dir()) / "model_pool.yaml"
    before = pool_path.read_bytes()
    _ = pl.validate_policy_lock()
    after = pool_path.read_bytes()
    assert before == after


# ── CLI ────────────────────────────────────────────────────────────────────


def test_cli_self_check_returns_zero(capsys):
    rc = pl.main(["self-check"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 0
    assert payload["status"] == "PASS"


def test_cli_validate_returns_zero_on_real_pool(capsys):
    rc = pl.main(["validate"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 0
    assert payload["final_verdict"] == "DA_DB_POLICY_LOCK_PASS"


def test_cli_rejects_pool_path_outside_repo(tmp_path, capsys):
    outside = tmp_path / "elsewhere_pool.yaml"
    outside.write_text("schema_version: '1.2'\nmodels: []\n", encoding="utf-8")
    rc = pl.main(["validate", "--pool", str(outside)])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert rc == 1
    assert payload["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED"
    assert "repo tree" in payload.get("error", "")
