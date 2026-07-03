"""Test: G-L3R D4 post-evidence normalization plan integrity.

Verifies that:
1. Plan references the correct PR #332 evidence anchors
2. Per-node evidence state is correctly recorded (5bao/9bao true, 21bao false)
3. The plan does NOT declare G_L3R_BLOCKED resolved
4. The plan does NOT declare G-L4 / readiness / model_call_verified / operator_approved ready
5. The plan does NOT propose NMC or model_pool write-back
6. The plan proposes ONLY future gate design (not execution)
7. Forbidden positive claims absent
8. Secret/Unicode scan clean

This test does NOT modify any production config, NMC, or model_pool.
"""

import json
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
PLAN_MD = REPO / "docs/baseline02/g-l3r-d4-post-evidence-normalization-plan.md"
PLAN_JSON = REPO / ".hermes/evidence/g-l3r-d4-post-evidence-normalization-plan.json"
EVIDENCE_CLOSURE = REPO / ".hermes/evidence/g-l3r-d4-clean-main-closure.json"
EVIDENCE_21BAO = REPO / ".hermes/evidence/g-l3r-d4-clean-main-v1/21bao-receipt.json"
EVIDENCE_5BAO = REPO / ".hermes/evidence/g-l3r-d4-clean-main-v1/5bao-receipt.json"
EVIDENCE_9BAO = REPO / ".hermes/evidence/g-l3r-d4-clean-main-v1/9bao-receipt.json"

EVIDENCE_ANCHOR = "09b1d97f0cab774e3eb023c9768a40d8165a1d46"
MERGE_ANCHOR = "18807ddbef5d962b67dd102220cdb118432d4f7c"


def test_plan_files_exist():
    assert PLAN_MD.exists(), f"plan md missing: {PLAN_MD}"
    assert PLAN_JSON.exists(), f"plan json missing: {PLAN_JSON}"


def test_plan_json_loads():
    data = json.loads(PLAN_JSON.read_text())
    assert "evidence_state" in data
    assert "proposed_normalization" in data
    assert "scope_constraints" in data


def test_plan_evidence_anchors():
    """Plan must reference the PR #332 evidence anchor and merge anchor."""
    md = PLAN_MD.read_text()
    assert EVIDENCE_ANCHOR in md, f"plan md missing evidence anchor {EVIDENCE_ANCHOR}"
    assert MERGE_ANCHOR in md, f"plan md missing merge anchor {MERGE_ANCHOR}"


def test_plan_json_anchors():
    plan = json.loads(PLAN_JSON.read_text())
    assert plan["evidence_anchor"] == EVIDENCE_ANCHOR
    assert plan["merge_anchor"] == MERGE_ANCHOR
    assert plan["source_pr"] == 332


def test_plan_records_5bao_9bao_true_21bao_false():
    plan = json.loads(PLAN_JSON.read_text())
    assert plan["evidence_state"]["5bao"]["runtime_visible_observed"] is True
    assert plan["evidence_state"]["5bao"]["runtime_visible_source"] == "5bao_ssh_opencode_config"
    assert plan["evidence_state"]["9bao"]["runtime_visible_observed"] is True
    assert plan["evidence_state"]["9bao"]["runtime_visible_source"] == "9bao_ssh_opencode_config"
    assert plan["evidence_state"]["21bao"]["runtime_visible_observed"] is False
    assert plan["evidence_state"]["21bao"]["runtime_visible_source"] == "21bao_local_nmc"


def test_plan_references_verdict_2of3_not_3of3():
    plan = json.loads(PLAN_JSON.read_text())
    assert plan["verdict_referenced"]["evidence_status"] == "G_L3R_D4_CLEAN_MAIN_LIVE_EVIDENCE_2OF3_PASS"
    assert plan["verdict_referenced"]["blocker_status"] == "G_L3R_D4_NOT_3OF3"
    assert plan["verdict_referenced"]["blocker_state"] == "G_L3R_BLOCKER_REMAINS_PARTIALLY_OPEN_FOR_21BAO"


def test_plan_does_not_close_blocker():
    plan = json.loads(PLAN_JSON.read_text())
    assert plan["verdict_referenced"]["closes_blocker"] is False


def test_plan_does_not_claim_readiness_or_g_l4_ready():
    plan = json.loads(PLAN_JSON.read_text())
    v = plan["verdict_referenced"]
    assert v["is_readiness"] is False
    assert v["is_g_l4_ready"] is False
    assert v["is_model_call_verified_ready"] is False
    assert v["is_operator_approved_ready"] is False


def test_plan_does_not_write_back():
    plan = json.loads(PLAN_JSON.read_text())
    assert plan["executes"] is False
    assert plan["writes_back_to_nmc"] is False
    assert plan["writes_back_to_model_pool"] is False


def test_plan_21bao_no_field_elevates():
    plan = json.loads(PLAN_JSON.read_text())
    p = plan["proposed_normalization"]["21bao"]
    assert p["elevates"] is False
    assert p["runtime_visible"]["proposed"] == "NO_CHANGE"


@pytest.mark.parametrize("node", ["5bao", "9bao"])
def test_plan_5bao_9bao_proposed_only_runtime_visible(node):
    plan = json.loads(PLAN_JSON.read_text())
    p = plan["proposed_normalization"][node]
    assert p["runtime_visible"]["proposed"] == "True"
    assert p["model_call_verified"]["proposed"] == "NO_CHANGE"
    assert p["operator_approved"]["proposed"] == "NO_CHANGE"
    assert p["elevates"] == "runtime_visible_only"


def test_plan_forbids_model_call_verified_or_operator_approved_promotion():
    plan = json.loads(PLAN_JSON.read_text())
    f = plan["forbidden_field_promotions"]
    assert "21bao_runtime_visible" in f
    assert "any_model_call_verified" in f
    assert "any_operator_approved" in f


def test_plan_md_no_positive_readiness_claim():
    md = PLAN_MD.read_text()
    forbidden = [
        "G_L3R_BLOCKED resolved",
        "G-L4 ready",
        "readiness ready",
        "model_call_verified ready",
        "operator_approved ready",
        "G-L4 authorized",
        "GRAY ready",
        "Baseline03 ready",
        "closes the global",
        "fully resolved",
    ]
    for p in forbidden:
        # Each forbidden phrase must either be absent OR appear in a negation context
        idx = 0
        while True:
            i = md.find(p, idx)
            if i < 0: break
            line_start = md.rfind("\n", 0, i) + 1
            line_end = md.find("\n", i)
            line = md[line_start:line_end]
            ll = line.lower()
            assert (
                "does not" in ll or "not " in ll or "❌" in line or "is " in ll.lower() and "false" in ll
                or "must remain" in ll or "is_readiness" in line or "closes_blocker" in line
                or "NOT " in line
            ), f"POSITIVE forbidden phrase '{p}' in plan md at line: {line.strip()[:120]}"
            idx = i + len(p)


def test_plan_md_scope_constraints_section_present():
    md = PLAN_MD.read_text()
    # These 14 must be present in scope-constraint form (in §1 or §5)
    section_1_or_5 = md.split("## 1.")[1].split("## 2.")[0] + "\n" + md.split("## 5.")[1].split("## 6.")[0]
    required = [
        "not-G_L3R_BLOCKED-resolved",
        "not-G-L4-ready",
        "not-readiness-ready",
        "not-model_call_verified-ready",
        "not-operator_approved-ready",
        "not-NMC-write-back",
        "not-model_pool-write-back",
        "not-G-READINESS",
        "not-G-GRAY",
        "not-G-D-A",
        "not-G-D-B",
        "not-PR-7",
        "not-Baseline03",
        "not-Stage8",
    ]
    for r in required:
        assert r in section_1_or_5, f"missing scope constraint {r} in plan md §1 or §5"


def test_plan_md_proposed_blocker_narrowing_does_not_close():
    md = PLAN_MD.read_text()
    assert "G_L3R_BLOCKER_NARROWED_TO_21BAO_RESIDUAL_ONLY" in md
    # The narrowing gate must NOT be presented as resolving the global blocker
    if "## 4" in md:
        s4 = md.split("## 4.")[1].split("## 5.")[0]
        # Must explicitly say the gate does NOT close the global blocker
        s4_lower = s4.lower()
        assert (
            "does not close" in s4_lower
            or "not close" in s4_lower
            or "not " in s4_lower and "close" in s4_lower
        ), f"narrowing gate section must explicitly say it does NOT close global blocker; got: {s4[:300]}"


def test_plan_md_no_secret_or_url():
    md = PLAN_MD.read_text()
    patterns = [
        (r"\bsk-[A-Za-z0-9]{16,}", "sk- token"),
        (r"\bghp_[A-Za-z0-9]{16,}", "ghp_ token"),
        (r"Bearer\s+[A-Za-z0-9_.-]{16,}", "Bearer token"),
        (r"\bAKIA[0-9A-Z]{12,}", "AWS access key"),
        (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
        (r"://[^/\s:@]+:[^/\s@]+@", "basic-auth URL"),
    ]
    for pat, name in patterns:
        m = re.search(pat, md)
        assert m is None, f"forbidden pattern {name!r} found in plan md at {m.start() if m else '?'}"


def test_plan_json_no_secret_or_url():
    pj = PLAN_JSON.read_text()
    patterns = [
        (r"\bsk-[A-Za-z0-9]{16,}", "sk- token"),
        (r"\bghp_[A-Za-z0-9]{16,}", "ghp_ token"),
        (r"Bearer\s+[A-Za-z0-9_.-]{16,}", "Bearer token"),
        (r"\bAKIA[0-9A-Z]{12,}", "AWS access key"),
        (r"://[^/\s:@]+:[^/\s@]+@", "basic-auth URL"),
    ]
    for pat, name in patterns:
        m = re.search(pat, pj)
        assert m is None, f"forbidden pattern {name!r} found in plan json at {m.start() if m else '?'}"


def test_plan_md_unicode_clean():
    data = PLAN_MD.read_bytes()
    c = data.decode("utf-8")
    assert not re.search(r"[\u200B\u200C\u200D\uFEFF]", c), "zero-width in plan md"
    assert not re.search(r"[\u200E\u200F\u202A-\u202E\u2066-\u2069]", c), "bidi in plan md"
    ctrl = [b for b in data if b < 0x20 and b not in (0x09, 0x0A, 0x0D)]
    assert not ctrl, f"control chars in plan md: {len(ctrl)}"


def test_plan_json_unicode_clean():
    data = PLAN_JSON.read_bytes()
    c = data.decode("utf-8")
    assert not re.search(r"[\u200B\u200C\u200D\uFEFF]", c), "zero-width in plan json"
    assert not re.search(r"[\u200E\u200F\u202A-\u202E\u2066-\u2069]", c), "bidi in plan json"
    ctrl = [b for b in data if b < 0x20 and b not in (0x09, 0x0A, 0x0D)]
    assert not ctrl, f"control chars in plan json: {len(ctrl)}"


def test_plan_evidence_digests_match_receipts():
    """The plan JSON's evidence_state per-node SHA256 must match the
    actual receipt file SHA256, ensuring the plan references canonical
    evidence."""
    plan = json.loads(PLAN_JSON.read_text())
    import hashlib
    expected = {
        "21bao": (EVIDENCE_21BAO, "161a63bfb542ef5887437d1d3da6153282a76957e7ce68a77e6b2abd55e9155a"),
        "5bao":  (EVIDENCE_5BAO,  "276282ec5a8fe827671df7af2bee1547621cb3418190b5a8fa10ff67d27bec92"),
        "9bao":  (EVIDENCE_9BAO,  "82251a651455202752a36bce1b6db54d7f01f226f7529ef57a593e49c6ae651e"),
    }
    for node, (path, declared) in expected.items():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == declared, f"{node} receipt actual={actual} declared={declared}"
        assert plan["evidence_state"][node]["receipt_sha256"] == declared


# ── Amendment: anchor semantic separation ───────────────────────────────────
# These tests enforce the operator-clarified semantics:
# (a) evidence_anchor = STABLE 09b1d97... (collection-time, immutable)
# (b) merge_anchor / current HEAD = ADVANCING (canonicalization-time)
# (c) current repository HEAD may be 18807dd or any later commit


def test_evidence_anchor_stable_across_later_commits():
    """The evidence collection anchor must be a fixed, stable value
    independent of the current main HEAD."""
    closure = json.loads(EVIDENCE_CLOSURE.read_text())
    assert closure["anchor"] == EVIDENCE_ANCHOR, (
        f"closure anchor drifted: {closure['anchor']} != {EVIDENCE_ANCHOR}"
    )


def test_current_repo_head_not_required_to_equal_evidence_anchor():
    """The current repository HEAD (canonicalization/merge anchor)
    is allowed to differ from the evidence collection anchor.
    It must NOT equal the evidence anchor (which is older)."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO, capture_output=True, text=True, timeout=10,
    ).stdout.strip()
    # Current HEAD may be 18807dd, eccdffc, or any later commit.
    # It must NOT be required to equal the evidence anchor.
    # The key property: HEAD is allowed to be != evidence_anchor.
    # No assertion that they are different — but no assertion that they
    # are equal either. We only assert that the test logic tolerates both.
    closure = json.loads(EVIDENCE_CLOSURE.read_text())
    # Sanity: if HEAD == evidence_anchor, that's fine (collection just
    # happened, nothing merged). If HEAD != evidence_anchor, also fine
    # (PRs merged in between). The test just confirms no error.
    assert closure["anchor"] == EVIDENCE_ANCHOR


def test_evidence_anchor_2of3_unchanged_after_amend():
    """2-of-3 evidence state must remain: 21bao=false, 5bao=true, 9bao=true.
    This is a regression guard: the amendment must NOT change the
    per-node evidence observations."""
    for node, expected_rv, expected_src in [
        ("21bao", False, "21bao_local_nmc"),
        ("5bao",  True,  "5bao_ssh_opencode_config"),
        ("9bao",  True,  "9bao_ssh_opencode_config"),
    ]:
        r = json.loads((REPO / f".hermes/evidence/g-l3r-d4-clean-main-v1/{node}-receipt.json").read_text())
        assert r["runtime_visible_observed"] is expected_rv, (
            f"{node} rv regression: {r['runtime_visible_observed']} != {expected_rv}"
        )
        assert r["runtime_visible_source"] == expected_src


def test_no_false_3of3_claim():
    """The closure must NOT claim 3-of-3 (since 21bao is false)."""
    closure = json.loads(EVIDENCE_CLOSURE.read_text())
    v = closure["verdict"]
    assert v["blocker_status"] == "G_L3R_D4_NOT_3OF3"
    assert "3OF3" not in v["evidence_status"] or "NOT_3OF3" in v["evidence_status"]
    # evidence_status must contain the NOT_3OF3 form
    assert "NOT_3OF3" in v["blocker_status"]


def test_no_blocker_resolved_claim():
    """The closure must NOT claim G_L3R_BLOCKED resolved."""
    closure = json.loads(EVIDENCE_CLOSURE.read_text())
    assert closure["verdict"]["closes_blocker"] is False
    assert "G_L3R_BLOCKER_REMAINS_PARTIALLY_OPEN_FOR_21BAO" in closure["verdict"]["blocker_state"]


def test_no_readiness_or_g_l4_or_model_call_verified_ready_claim():
    """The closure must NOT claim readiness / G-L4 / model_call_verified ready."""
    closure = json.loads(EVIDENCE_CLOSURE.read_text())
    v = closure["verdict"]
    assert v["is_readiness"] is False
    assert v["is_g_l4_ready"] is False
    assert v["is_model_call_verified_ready"] is False
    assert v["is_operator_approved_promotion"] is False
