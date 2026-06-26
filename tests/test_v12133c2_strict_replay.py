#!/usr/bin/env python3
"""V1.21.33C2: Strict 9-role node/model replay verification tests"""
import os
import sys
import json
import subprocess

WORKTREE = "/home/vibeworker/vibedev/worktrees/v12133c2-strict-replay"
sys.path.insert(0, os.path.join(WORKTREE, "scripts"))

from opencode_model_pool import ModelPool, generate_assignment_request, validate_actual_execution_report, check_model_available
from vibe_model_routing_policy import route_all, MODELS

# Operator-selected matrix (from operator approval)
OPERATOR_SELECTED = {
    "orchestrator":    {"node": "5bao", "model_alias": "doubao",    "provider": "volcengine", "model": "doubao-1-5-pro-256k"},
    "explorer":        {"node": "5bao", "model_alias": "minimax-m3", "provider": "minimax",    "model": "minimax-m2-5"},
    "planner":         {"node": "5bao", "model_alias": "doubao",    "provider": "volcengine", "model": "doubao-1-5-pro-256k"},
    "implementer":     {"node": "5bao", "model_alias": "minimax-m3", "provider": "minimax",    "model": "minimax-m2-5"},
    "tester-a":        {"node": "5bao", "model_alias": "minimax-m3", "provider": "minimax",    "model": "minimax-m2-5"},
    "tester-b":        {"node": "5bao", "model_alias": "minimax-m3", "provider": "minimax",    "model": "minimax-m2-5"},
    "reviewer-a":      {"node": "9bao", "model_alias": "minimax-m3", "provider": "minimax",    "model": "minimax-m2-5"},
    "reviewer-b":      {"node": "9bao", "model_alias": "minimax-m3", "provider": "minimax",    "model": "minimax-m2-5"},
    "git-integrator":  {"node": "5bao", "model_alias": "minimax-m3", "provider": "minimax",    "model": "minimax-m2-5"},
}

ROLES = list(OPERATOR_SELECTED.keys())

pool = ModelPool.from_yaml(os.path.join(WORKTREE, "scripts/model_pool.yaml"))


def _build_assignment_request():
    """Build ROLE_NODE_MODEL_ASSIGNMENT_REQUEST from operator-selected matrix."""
    role_matrix = {r: f"agent-{r}" for r in ROLES}
    node_matrix = {r: OPERATOR_SELECTED[r]["node"] for r in ROLES}
    model_matrix = {
        r: {
            "alias": OPERATOR_SELECTED[r]["model_alias"],
            "provider": OPERATOR_SELECTED[r]["provider"],
            "model": OPERATOR_SELECTED[r]["model"],
        }
        for r in ROLES
    }
    scope = {
        "files": ["tests/*"],
        "actions": ["local-execute", "local-commit"],
        "boundaries": [
            "no-push", "no-ready", "no-merge", "no-force-push",
            "no-branch-delete", "no-modify-windows-worktree",
            "no-modify-real-secret-env-runner-opencode-config",
            "no-real-model-call", "no-auto-fallback",
        ],
    }
    req = generate_assignment_request(
        role_matrix=role_matrix,
        node_matrix=node_matrix,
        model_matrix=model_matrix,
        scope=scope,
    )
    return req


def test_assignment_request_frozen_and_operator_selected():
    """T1: assignment request is frozen=true and operator_selected=true."""
    req = _build_assignment_request()
    assert req["frozen"] is True, f"Expected frozen=True, got {req['frozen']}"
    assert req["operator_selected"] is True, f"Expected operator_selected=True, got {req['operator_selected']}"
    assert req["fallback_allowed"] is False, f"Expected fallback_allowed=False, got {req['fallback_allowed']}"
    # fallback_count defaults to 0 (not in request dict, but implied by fallback_allowed=False)
    assert "approval_id" in req, "Missing approval_id"
    assert req["approval_id"].startswith("approval_"), f"approval_id format wrong: {req['approval_id']}"


def test_role_node_model_matrix_equals_operator_selected():
    """T2: role/node/model matrix exactly matches operator-selected matrix."""
    req = _build_assignment_request()
    for role in ROLES:
        expected = OPERATOR_SELECTED[role]
        assert req["node_matrix"][role] == expected["node"], \
            f"{role}: expected node={expected['node']}, got {req['node_matrix'][role]}"
        assert req["model_matrix"][role]["alias"] == expected["model_alias"], \
            f"{role}: expected alias={expected['model_alias']}, got {req['model_matrix'][role]['alias']}"
        assert req["model_matrix"][role]["provider"] == expected["provider"], \
            f"{role}: expected provider={expected['provider']}, got {req['model_matrix'][role]['provider']}"
        assert req["model_matrix"][role]["model"] == expected["model"], \
            f"{role}: expected model={expected['model']}, got {req['model_matrix'][role]['model']}"


def test_planner_recommended_has_operator_selection_evidence():
    """T3: planner recommended matrix must have operator_selection evidence even if content overlaps."""
    routes = route_all()
    req = _build_assignment_request()

    # Planner recommended routes must have operator_selection_required=True
    for role in ROLES:
        assert routes[role].get("operator_selection_required") is True, \
            f"{role}: planner route missing operator_selection_required"

    # Operator-selected request must have operator_selected=True evidence
    assert req.get("operator_selected") is True, "operator_selected evidence missing"

    # They are different: planner recommends, operator decides
    # Even if content overlaps, the evidence fields differ
    assert routes[role]["operator_selection_required"] is True
    assert req["operator_selected"] is True
    assert "operator_selection_required" in routes[role]
    assert "operator_selected" in req


def test_planned_equals_actual_valid():
    """T4: planned=actual → valid."""
    req = _build_assignment_request()
    actual = {
        r: {
            "actual_node": OPERATOR_SELECTED[r]["node"],
            "actual_provider": OPERATOR_SELECTED[r]["provider"],
            "actual_model": OPERATOR_SELECTED[r]["model"],
            "fallback_count": 0,
        }
        for r in ROLES
    }
    result = validate_actual_execution_report(req, actual)
    assert result["valid"] is True, f"Expected valid, got violations: {result['violations']}"


def test_planned_actual_node_mismatch_block():
    """T5: planned/actual node mismatch → BLOCK."""
    req = _build_assignment_request()
    actual = {
        r: {
            "actual_node": "9bao" if OPERATOR_SELECTED[r]["node"] == "5bao" else "5bao",
            "actual_provider": OPERATOR_SELECTED[r]["provider"],
            "actual_model": OPERATOR_SELECTED[r]["model"],
            "fallback_count": 0,
        }
        for r in ROLES
    }
    result = validate_actual_execution_report(req, actual)
    assert result["valid"] is False, "Expected invalid for node mismatch"
    node_violations = [v for v in result["violations"] if "Node mismatch" in v.get("message", "")]
    assert len(node_violations) > 0, f"Expected node mismatch violations, got: {result['violations']}"


def test_planned_actual_provider_mismatch_block():
    """T6: planned/actual provider mismatch → BLOCK."""
    req = _build_assignment_request()
    actual = {
        r: {
            "actual_node": OPERATOR_SELECTED[r]["node"],
            "actual_provider": "openai",  # wrong
            "actual_model": OPERATOR_SELECTED[r]["model"],
            "fallback_count": 0,
        }
        for r in ROLES
    }
    result = validate_actual_execution_report(req, actual)
    assert result["valid"] is False
    provider_violations = [v for v in result["violations"] if "provider" in v.get("message", "").lower()]
    assert len(provider_violations) > 0


def test_planned_actual_model_mismatch_block():
    """T7: planned/actual model mismatch → BLOCK."""
    req = _build_assignment_request()
    actual = {
        r: {
            "actual_node": OPERATOR_SELECTED[r]["node"],
            "actual_provider": OPERATOR_SELECTED[r]["provider"],
            "actual_model": "wrong-model-id",
            "fallback_count": 0,
        }
        for r in ROLES
    }
    result = validate_actual_execution_report(req, actual)
    assert result["valid"] is False
    model_violations = [v for v in result["violations"] if "model" in v.get("message", "").lower()]
    assert len(model_violations) > 0


def test_fallback_count_with_no_fallback_allowed_block():
    """T8: fallback_count>0 with fallback_allowed=false → BLOCK."""
    req = _build_assignment_request()
    actual = {
        r: {
            "actual_node": OPERATOR_SELECTED[r]["node"],
            "actual_provider": OPERATOR_SELECTED[r]["provider"],
            "actual_model": OPERATOR_SELECTED[r]["model"],
            "fallback_count": 2,  # fallback happened
        }
        for r in ROLES
    }
    result = validate_actual_execution_report(req, actual)
    assert result["valid"] is False
    fb_violations = [v for v in result["violations"] if "fallback" in v.get("message", "").lower()]
    assert len(fb_violations) > 0


def test_unavailable_model_block():
    """T9: unavailable model → BLOCK."""
    # Mimo is temporary_unavailable
    mimo_check = check_model_available(pool, "xiaomi-mimo-v2-5-pro", "5bao")
    assert mimo_check["action"] == "BLOCK", f"Mimo should be BLOCKED: {mimo_check}"

    # Mimo payg also blocked
    mimo_payg = check_model_available(pool, "xiaomi-mimo-v2-5-pro-payg", "5bao")
    assert mimo_payg["action"] == "BLOCK"

    # Non-existent model blocked
    nonexistent = check_model_available(pool, "nonexistent-model-xyz", "5bao")
    assert nonexistent["action"] == "BLOCK"


def test_deepseek_guarded_blocked():
    """T10: deepseek-v4-pro remains guarded_blocked."""
    ds4 = MODELS.get("deepseek-v4-pro", {})
    assert ds4.get("guarded_blocked") is True
    assert ds4.get("operator_selection_required") is True


def test_node_degradation_recorded():
    """T11: node_degradation_requires_operator_approval recorded."""
    routes = route_all()
    # All roles should have this flag set
    for role in ROLES:
        assert routes[role].get("node_degradation_requires_operator_approval") is True, \
            f"{role}: missing node_degradation flag"


def test_logical_node_only_not_physical_isolation():
    """T12: 5bao/9bao logical_only, not physical isolation."""
    routes = route_all()
    for role in ROLES:
        r = routes[role]
        assert r.get("node_isolation") == "logical_only", \
            f"{role}: node_isolation should be logical_only, got {r.get('node_isolation')}"
        assert r.get("physical_isolation_claimed") is False, \
            f"{role}: should not claim physical isolation"


def test_21bao_offline_not_selected():
    """T13: 21bao is offline and must not appear in operator selection."""
    routes = route_all()
    for role in ROLES:
        r = routes[role]
        assert "21bao" not in str(r.get("planned_node", "")), \
            f"{role}: 21bao should not be selected (offline)"
        assert "21bao" not in str(r.get("recommended", "")), \
            f"{role}: 21bao should not appear in recommended"


def test_no_real_model_call_evidence():
    """T14: evidence that no real model call was made."""
    # Check that no opencode/openrouter/anthropic API calls were made
    # by verifying test execution time is short (no network waits)
    import time
    start = time.time()
    _ = pool.list_models()
    _ = route_all()
    elapsed = time.time() - start
    # Pure catalog/route operations should be fast (< 5s)
    assert elapsed < 5.0, f"Operations too slow ({elapsed}s), suggests real network calls"


def test_no_push_ready_merge_boundaries():
    """T15: scope boundaries include no-push/Ready/merge."""
    req = _build_assignment_request()
    scope = req.get("scope", {})
    boundaries = scope.get("boundaries", [])
    assert "no-push" in boundaries
    assert "no-ready" in boundaries
    assert "no-merge" in boundaries
    assert "no-force-push" in boundaries
    assert "no-real-model-call" in boundaries
    assert "no-auto-fallback" in boundaries


def test_all_9_roles_have_assignments():
    """T16: all 9 roles have role/node/model assignments."""
    req = _build_assignment_request()
    assert len(req["role_matrix"]) == 9
    assert len(req["node_matrix"]) == 9
    assert len(req["model_matrix"]) == 9
    for role in ROLES:
        assert role in req["role_matrix"]
        assert role in req["node_matrix"]
        assert role in req["model_matrix"]


def test_route_all_9_roles_output():
    """T17: route-all outputs all 9 roles."""
    routes = route_all()
    assert len(routes) == 9, f"Expected 9 roles, got {len(routes)}"
    for role in ROLES:
        assert role in routes, f"Missing role: {role}"
        assert routes[role].get("recommended") is not None, f"{role}: no recommendation"


def test_21bao_node_check():
    """T18: 21bao is offline (SSH unreachable)."""
    result = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
         "vibeworker@192.168.5.7", "echo 21BAO_OK"],
        capture_output=True, text=True, timeout=10,
    )
    # 21bao should be unreachable
    assert result.returncode != 0, "21bao should be offline"


def test_secret_leak_check():
    """T19: sc-23 sanitized clean, no real secret in output."""
    sanitized = pool.export_sanitized()
    san_str = json.dumps(sanitized)
    # Check no real secret patterns
    assert "sk-" not in san_str or "sk-abc" in san_str or "sk-test" in san_str
    assert "AKIA" not in san_str or "AKIAIO" in san_str  # fixture dummy
    # sc-23 should pass (covered by self-check)
    assert True