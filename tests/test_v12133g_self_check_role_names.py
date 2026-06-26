"""Tests for V1.21.33G: routing self-check role name fix.

Ensures self_check() outputs clean 7/7 PASS semantics.
"""
import subprocess
import sys
import os

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS_DIR))

import pytest


# ── 1. self_check() returns overall PASS ──────────────────────────────

def test_self_check_overall_pass():
    """self_check() returns overall=PASS (7/7)."""
    from vibe_model_routing_policy import self_check
    result = self_check()
    assert result["overall"] == "PASS", f"Expected PASS, got {result['overall']}"
    assert result["passed"] == result["total"], f"{result['passed']}/{result['total']}"
    assert result["total"] == 7


def test_self_check_exit_code_zero():
    """--self-check CLI exits 0."""
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, "vibe_model_routing_policy.py"), "--self-check"],
        capture_output=True, text=True, cwd=os.path.dirname(__file__) + "/.."
    )
    assert result.returncode == 0, f"exit={result.returncode}: {result.stdout}"


def test_self_check_no_failures():
    """self_check() has zero failed checks."""
    from vibe_model_routing_policy import self_check
    result = self_check()
    failures = [c for c in result["checks"] if not c["passed"]]
    assert len(failures) == 0, f"Failures: {failures}"


# ── 2. recommend() for valid 9-role names returns non-None ────────────

@pytest.mark.parametrize("role", [
    "reviewer-a", "reviewer-b", "explorer", "planner",
    "git-integrator", "implementer", "tester-a", "tester-b",
])
def test_recommend_valid_role_returns_non_none(role):
    """recommend(role) returns non-None recommended for all valid 9-role names."""
    from vibe_model_routing_policy import recommend
    r = recommend(role)
    assert r.get("recommended") is not None, f"{role}: recommended=None, error={r.get('error')}"
    assert len(r.get("candidates", [])) >= 1, f"{role}: no candidates"


def test_recommend_orchestrator_has_attribution():
    """recommend(orchestrator) includes node_attribution with controller_node."""
    from vibe_model_routing_policy import recommend
    r = recommend("orchestrator")
    attrib = r.get("node_attribution", {})
    assert "controller_node" in attrib, f"Missing controller_node in {list(attrib.keys())}"
    assert attrib["controller_node"] == "windows"


# ── 3. recommend() for invalid role returns error ─────────────────────

def test_recommend_summarizer_returns_error():
    """recommend(summarizer) returns unknown role error (no longer in self-check)."""
    from vibe_model_routing_policy import recommend
    r = recommend("summarizer")
    assert "error" in r, f"Expected error, got {r}"
    assert "unknown role" in r["error"].lower()


def test_recommend_reviewer_returns_error():
    """recommend(reviewer) returns unknown role error (use reviewer-a/b instead)."""
    from vibe_model_routing_policy import recommend
    r = recommend("reviewer")
    assert "error" in r, f"Expected error, got {r}"


# ── 4. route_all() outputs 9 roles ────────────────────────────────────

def test_route_all_9_roles():
    """route_all() returns exactly 9 roles."""
    from vibe_model_routing_policy import route_all
    result = route_all()
    expected_roles = [
        "orchestrator", "explorer", "planner", "implementer",
        "tester-a", "tester-b", "reviewer-a", "reviewer-b",
        "git-integrator",
    ]
    for role in expected_roles:
        assert role in result, f"Missing role: {role}"
    assert len(result) == 9, f"Expected 9 roles, got {len(result)}"


def test_route_all_orchestrator_21bao():
    """route_all() recommends orchestrator on 21bao (Windows control-plane)."""
    from vibe_model_routing_policy import route_all
    result = route_all()
    orch = result["orchestrator"]
    assert orch.get("planned_node") == "21bao", f"Expected 21bao, got {orch.get('planned_node')}"
    attrib = orch.get("node_attribution", {})
    assert attrib.get("transport") == "local-exec", f"Expected local-exec, got {attrib.get('transport')}"


# ── 5. operator_selection_required and fallback_count ─────────────────

def test_route_all_operator_selection_required():
    """Every role in route_all has operator_selection_required=true."""
    from vibe_model_routing_policy import route_all
    result = route_all()
    for role, rec in result.items():
        assert rec.get("operator_selection_required") is True, f"{role}: not operator_selection_required"


def test_route_all_fallback_count_zero():
    """Every role in route_all has fallback_count=0."""
    from vibe_model_routing_policy import route_all
    result = route_all()
    for role, rec in result.items():
        assert rec.get("fallback_count") == 0, f"{role}: fallback_count={rec.get('fallback_count')}"


# ── 6. health UNKNOWN semantics ───────────────────────────────────────

def test_route_all_health_unknown_not_online():
    """route_all() does not claim ONLINE for any node (all UNKNOWN)."""
    from vibe_model_routing_policy import route_all
    result = route_all()
    for role, rec in result.items():
        attrib = rec.get("node_attribution", {})
        health = attrib.get("health_status", "N/A")
        assert health != "ONLINE", f"{role}: health=ONLINE (should be UNKNOWN)"
        assert health == "UNKNOWN", f"{role}: health={health} (expected UNKNOWN)"


def test_route_all_health_unknown_not_offline():
    """route_all() does not mark UNKNOWN nodes as OFFLINE."""
    from vibe_model_routing_policy import route_all
    result = route_all()
    for role, rec in result.items():
        attrib = rec.get("node_attribution", {})
        health = attrib.get("health_status", "N/A")
        assert health != "OFFLINE", f"{role}: health=OFFLINE (UNKNOWN != OFFLINE)"


# ── 7. node_isolation and physical_isolation ──────────────────────────

def test_route_all_physical_isolation():
    """route_all() claims physical_isolation_claimed=true for all roles."""
    from vibe_model_routing_policy import route_all
    result = route_all()
    for role, rec in result.items():
        assert rec.get("physical_isolation_claimed") is True, f"{role}: not physical"


def test_route_all_no_logical_node_only():
    """route_all() no longer uses LOGICAL_NODE_ONLY."""
    from vibe_model_routing_policy import route_all
    result = route_all()
    for role, rec in result.items():
        assert rec.get("node_isolation") != "logical_only", f"{role}: still logical_only"


# ── 8. 5bao/9bao/21bao node topology ──────────────────────────────────

def test_route_all_three_nodes():
    """route_all() uses exactly 3 distinct nodes: 5bao, 9bao, 21bao."""
    from vibe_model_routing_policy import route_all
    result = route_all()
    nodes = set()
    for rec in result.values():
        nid = rec.get("planned_node")
        if nid:
            nodes.add(nid)
    assert "5bao" in nodes, "Missing 5bao"
    assert "9bao" in nodes, "Missing 9bao"
    assert "21bao" in nodes, "Missing 21bao"
    assert len(nodes) == 3, f"Expected 3 nodes, got {nodes}"


def test_route_all_21bao_local_exec():
    """21bao transport is local-exec, not ssh."""
    from vibe_model_routing_policy import route_all
    result = route_all()
    for rec in result.values():
        attrib = rec.get("node_attribution", {})
        if attrib.get("node_id") == "21bao":
            assert attrib.get("transport") == "local-exec", f"21bao transport={attrib.get('transport')}"


# ── 9. node add/delete scaffold still present ─────────────────────────

def test_add_node_dry_run_exists():
    """WorkerRegistry.add_node(dry_run=True) still exists."""
    from vibe_worker_registry import WorkerRegistry
    registry = WorkerRegistry()
    assert hasattr(registry, "add_node"), "add_node method missing"
    assert hasattr(registry, "remove_node"), "remove_node method missing"
    assert hasattr(registry, "dry_run_node_change"), "dry_run_node_change method missing"


# ── 10. existing self-check test still passes ─────────────────────────

def test_existing_routing_self_check_passes():
    """Existing test_routing_self_check_passes still passes (returncode=0)."""
    result = subprocess.run(
        [sys.executable, os.path.join(SCRIPTS_DIR, "vibe_model_routing_policy.py"), "--self-check"],
        capture_output=True, text=True, cwd=os.path.dirname(__file__) + "/.."
    )
    assert result.returncode == 0, f"exit={result.returncode}: {result.stdout}"
    assert "PASS (7/7)" in result.stdout, f"Not 7/7: {result.stdout}"


# ── 11. no secret in output ───────────────────────────────────────────

def test_no_secret_in_self_check_output():
    """self-check output contains no real secret patterns."""
    from vibe_model_routing_policy import self_check
    result = self_check()
    output = str(result)
    for secret_pattern in ["sk-", "AKIA", "Bearer ", "secret_key", "api_key"]:
        assert secret_pattern not in output, f"Secret pattern found: {secret_pattern}"
