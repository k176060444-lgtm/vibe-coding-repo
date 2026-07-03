"""Test: G-L3R D4 clean-main evidence archive digest & verdict integrity.

Verifies that:
1. Each clean-main receipt file still exists at its expected path
2. Each receipt SHA256 matches what was declared in the closure
3. Closure verdict fields are intact and consistent
4. 21bao runtime_visible_observed remains false (no false-claim)
5. 5bao/9bao runtime_visible_observed remains true
6. Anchor in closure matches main HEAD
7. Scope constraints present and consistent

This test does NOT modify any production config, NMC, or model_pool.
"""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
CLOSURE_PATH = REPO / ".hermes/evidence/g-l3r-d4-clean-main-closure.json"
EVIDENCE_DIR = REPO / ".hermes/evidence/g-l3r-d4-clean-main-v1"
SUMMARY_PATH = REPO / "docs/baseline02/g-l3r-d4-clean-main-evidence.md"

EXPECTED_DIGESTS = {
    "21bao": "161a63bfb542ef5887437d1d3da6153282a76957e7ce68a77e6b2abd55e9155a",
    "5bao":  "276282ec5a8fe827671df7af2bee1547621cb3418190b5a8fa10ff67d27bec92",
    "9bao":  "82251a651455202752a36bce1b6db54d7f01f226f7529ef57a593e49c6ae651e",
}

EXPECTED_BYTES = {
    "21bao": 1415,
    "5bao": 1395,
    "9bao": 1395,
}


def _sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _git_head() -> str:
    out = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO, capture_output=True, text=True, timeout=10,
    )
    return out.stdout.strip()


def test_closure_file_exists():
    assert CLOSURE_PATH.exists(), f"closure file missing: {CLOSURE_PATH}"


def test_evidence_receipts_exist():
    for node in ("21bao", "5bao", "9bao"):
        p = EVIDENCE_DIR / f"{node}-receipt.json"
        assert p.exists(), f"receipt missing: {p}"


def test_receipt_digests_match_closure():
    closure = json.loads(CLOSURE_PATH.read_text())
    for node, expected in EXPECTED_DIGESTS.items():
        receipt_path = EVIDENCE_DIR / f"{node}-receipt.json"
        actual = _sha256(receipt_path)
        declared = closure["per_node"][node]["receipt_sha256"]
        assert actual == declared, (
            f"{node} digest mismatch: file={actual} closure={declared}"
        )
        assert actual == expected, (
            f"{node} digest mismatch: actual={actual} expected={expected}"
        )


def test_receipt_bytes_match_closure():
    closure = json.loads(CLOSURE_PATH.read_text())
    for node, expected in EXPECTED_BYTES.items():
        actual = (EVIDENCE_DIR / f"{node}-receipt.json").stat().st_size
        declared = closure["per_node"][node]["receipt_bytes"]
        assert actual == declared == expected, (
            f"{node} bytes mismatch: file={actual} closure={declared} "
            f"expected={expected}"
        )


def test_closure_anchor_matches_main():
    """The closure was anchored at clean-main collection time. Compare
    against the PR's base ref (i.e., the main branch HEAD that the PR
    branched from), not the current branch HEAD. The closure anchor
    records the **collection anchor**, which is the main commit at the
    time the clean-main live evidence was collected.
    """
    closure = json.loads(CLOSURE_PATH.read_text())
    # main is the base ref; on the PR branch HEAD is the merge candidate
    main_head = subprocess.run(
        ["git", "rev-parse", "main"],
        cwd=REPO, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    assert closure["anchor"] == main_head, (
        f"closure anchor={closure['anchor']} main HEAD={main_head}"
    )


def test_closure_anchor_matches_each_receipt():
    closure = json.loads(CLOSURE_PATH.read_text())
    for node in ("21bao", "5bao", "9bao"):
        receipt = json.loads((EVIDENCE_DIR / f"{node}-receipt.json").read_text())
        assert receipt["anchor"] == closure["anchor"], (
            f"{node} receipt anchor={receipt['anchor']} "
            f"closure={closure['anchor']}"
        )


def test_21bao_runtime_visible_observed_false():
    """21bao false-claim guard: must remain runtime_visible_observed=false."""
    receipt = json.loads((EVIDENCE_DIR / "21bao-receipt.json").read_text())
    assert receipt["runtime_visible_observed"] is False, (
        f"21bao runtime_visible_observed must be False, got "
        f"{receipt['runtime_visible_observed']}"
    )
    assert receipt["runtime_visible_source"] == "21bao_local_nmc"


@pytest.mark.parametrize("node", ["5bao", "9bao"])
def test_5bao_9bao_runtime_visible_observed_true(node):
    receipt = json.loads((EVIDENCE_DIR / f"{node}-receipt.json").read_text())
    assert receipt["runtime_visible_observed"] is True, (
        f"{node} runtime_visible_observed must be True, got "
        f"{receipt['runtime_visible_observed']}"
    )
    assert receipt["runtime_visible_source"] == f"{node}_ssh_opencode_config"


def test_closure_verdict_blocker_not_resolved():
    """Verdict must NOT close the G_L3R_BLOCKED; 21bao is still false."""
    closure = json.loads(CLOSURE_PATH.read_text())
    v = closure["verdict"]
    assert v["evidence_status"] == "G_L3R_D4_CLEAN_MAIN_LIVE_EVIDENCE_2OF3_PASS"
    assert v["blocker_status"] == "G_L3R_D4_NOT_3OF3"
    assert v["blocker_state"] == "G_L3R_BLOCKER_REMAINS_PARTIALLY_OPEN_FOR_21BAO"
    assert v["closes_blocker"] is False


def test_closure_not_readiness_or_g_l4_or_model_call_verified():
    closure = json.loads(CLOSURE_PATH.read_text())
    v = closure["verdict"]
    assert v["is_readiness"] is False
    assert v["is_g_l4_ready"] is False
    assert v["is_model_call_verified_ready"] is False
    assert v["is_operator_approved_promotion"] is False


def test_closure_no_write_back():
    closure = json.loads(CLOSURE_PATH.read_text())
    v = closure["verdict"]
    assert v["writes_back_to_nmc"] is False
    assert v["writes_back_to_model_pool"] is False


def test_closure_scope_constraints_complete():
    closure = json.loads(CLOSURE_PATH.read_text())
    required = {
        "not-G_L3R_BLOCKED_resolved",
        "not-G-L4-ready",
        "not-readiness-ready",
        "not-model_call_verified-ready",
        "not-operator_approved-promotion",
        "not-nmc-write-back",
        "not-model_pool-write-back",
        "not-G-READINESS",
        "not-G-GRAY",
        "not-G-D-A",
        "not-G-D-B",
        "not-PR-7",
        "not-Baseline03",
        "not-Stage8",
    }
    actual = set(closure["scope_constraints"])
    missing = required - actual
    assert not missing, f"missing scope constraints: {sorted(missing)}"


def test_closure_forbidden_flags_all_false():
    closure = json.loads(CLOSURE_PATH.read_text())
    for k, v in closure["forbidden_operation_flags"].items():
        assert v is False, f"forbidden flag {k} must be False, got {v}"


def test_closure_leak_scan_all_passed():
    closure = json.loads(CLOSURE_PATH.read_text())
    for level in ("evidence_level", "receipt_level", "summary_level"):
        ls = closure["leak_scan"][level]
        assert ls["passed"] is True, (
            f"leak_scan {level} failed: {ls}"
        )
        assert ls["matches_found"] == 0


def test_closure_test_results_recorded():
    closure = json.loads(CLOSURE_PATH.read_text())
    tr = closure["test_results"]
    assert "passed" in tr["d4_self_check"]
    assert "passed" in tr["d4_targeted_pytest"]
    assert "rejected" in tr["negative_21bao_ssh"]
    assert "rejected" in tr["negative_no_approval"]
    assert "rejected" in tr["negative_wrong_mode"]


def test_summary_doc_exists():
    assert SUMMARY_PATH.exists()


def test_summary_doc_contains_key_phrases():
    c = SUMMARY_PATH.read_text()
    assert "G_L3R_D4_CLEAN_MAIN_LIVE_EVIDENCE_2OF3_PASS" in c
    assert "G_L3R_D4_NOT_3OF3" in c
    assert "G_L3R_BLOCKER_REMAINS_PARTIALLY_OPEN_FOR_21BAO" in c
    assert "G_L3R_BLOCKED resolved" in c  # must appear negated
    assert "not-G-L4-ready" in c or "not G-L4" in c or "not G-L4" in c
    assert "not-readiness" in c or "not readiness" in c


def test_summary_doc_uses_enum_endpoint_refs():
    c = SUMMARY_PATH.read_text()
    assert "5bao_ssh_opencode_config" in c
    assert "9bao_ssh_opencode_config" in c
    assert "21bao_local_nmc" in c
    # No real secret patterns: sk- followed by 16+ alnum (token),
    # ghp_ token, AKIA key, basic-auth URL, or BEGIN PRIVATE KEY.
    # The bare substring "sk-" is too broad (matches "asked", "task-", etc.)
    # so we use a word-boundary + 16+ chars regex check.
    import re
    secret_patterns = [
        (r"\bsk-[A-Za-z0-9]{16,}", "sk- token"),
        (r"\bghp_[A-Za-z0-9]{16,}", "ghp_ token"),
        (r"Bearer\s+[A-Za-z0-9_.-]{16,}", "Bearer token"),
        (r"\bAKIA[0-9A-Z]{12,}", "AWS access key"),
        (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
        (r"://[^/\s:@]+:[^/\s@]+@", "basic-auth URL"),
    ]
    for pat, name in secret_patterns:
        m = re.search(pat, c)
        assert m is None, f"forbidden pattern {name!r} found in summary at {m.start() if m else '?'}"


@pytest.mark.parametrize("node", ["21bao", "5bao", "9bao"])
def test_receipt_has_required_fields(node):
    required = {
        "schema_version", "anchor", "node", "source_node",
        "target_model", "canonical_model_id", "provider_namespace",
        "runtime_provider", "aliases_checked", "runtime_visible_observed",
        "runtime_visible_source", "config_visible_observed",
        "wrapper_visible_observed", "env_loaded_observed_enum",
        "credential_status_observed_enum", "endpoint_ref_observed_enum",
        "redaction_status", "leak_scan", "forbidden_operation_flags",
        "collector_mode", "operator_approval_id", "collection_status",
        "generated_at",
    }
    receipt = json.loads((EVIDENCE_DIR / f"{node}-receipt.json").read_text())
    missing = required - set(receipt.keys())
    assert not missing, f"{node} missing fields: {sorted(missing)}"


@pytest.mark.parametrize("node", ["21bao", "5bao", "9bao"])
def test_receipt_leak_scan_passed(node):
    receipt = json.loads((EVIDENCE_DIR / f"{node}-receipt.json").read_text())
    assert receipt["leak_scan"]["passed"] is True
    assert receipt["leak_scan"]["matches_found"] == 0


@pytest.mark.parametrize("node", ["21bao", "5bao", "9bao"])
def test_receipt_forbidden_flags_all_false(node):
    receipt = json.loads((EVIDENCE_DIR / f"{node}-receipt.json").read_text())
    for k, v in receipt["forbidden_operation_flags"].items():
        assert v is False, (
            f"{node} forbidden flag {k} must be False, got {v}"
        )


@pytest.mark.parametrize("node", ["21bao", "5bao", "9bao"])
def test_receipt_operator_approval_id_matches(node):
    receipt = json.loads((EVIDENCE_DIR / f"{node}-receipt.json").read_text())
    assert receipt["operator_approval_id"] == "OPERATOR-20260703-G-L3R-D4-LIVE-EVIDENCE-003"
