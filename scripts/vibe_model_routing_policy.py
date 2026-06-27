#!/usr/bin/env python3
"""Model Routing Policy v1.0.0 — recommend model roles for tasks.

Usage:
    python3 scripts/vibe_model_routing_policy.py --json route --task-type implementer --risk low
    python3 scripts/vibe_model_routing_policy.py --json route-all
    python3 scripts/vibe_model_routing_policy.py self-check [--json]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

VERSION = "1.0.0"

# ── Model Role Definitions ───────────────────────────────────────────

ROLES = {
    "orchestrator": {
        "purpose": "Pure flow control — stage transitions, gate checks, worker dispatch",
        "requirements": ["stage_control", "gate_enforcement", "worker_dispatch"],
        "risk_constraint": "low — read-only flow control, no mutation",
    },
    "explorer": {
        "purpose": "Read-only evidence collection in PLAN-DISCOVERY",
        "requirements": ["codebase_reading", "git_history", "file_search"],
        "risk_constraint": "low — read-only exploration, no mutation",
    },
    "planner": {
        "purpose": "Generate plan, risk assessment, test strategy, and recommendation matrix",
        "requirements": ["planning", "structured_output", "risk_analysis"],
        "risk_constraint": "low — read-only planning, no mutation",
    },
    "implementer": {
        "purpose": "Write code, fix bugs, resolve conflicts in isolated worktree",
        "requirements": ["coding", "testing", "git_operations"],
        "risk_constraint": "medium — writes to worktree only, reviewed before merge",
    },
    "tester-a": {
        "purpose": "Run test suite A and output PASS/FAIL with evidence",
        "requirements": ["testing", "pytest", "result_classification"],
        "risk_constraint": "low — read-only test execution, no mutation",
    },
    "tester-b": {
        "purpose": "Run independent test suite B or different environment, output independent verdict",
        "requirements": ["testing", "pytest", "result_classification"],
        "risk_constraint": "low — read-only test execution, no mutation",
    },
    "reviewer-a": {
        "purpose": "Blind review of base_sha..result_sha diff, output PASS/REQUEST_CHANGES/BLOCKED",
        "requirements": ["code_review", "security_awareness", "diff_analysis"],
        "risk_constraint": "low — read-only review, no mutation",
    },
    "reviewer-b": {
        "purpose": "Independent blind review of same diff, output independent verdict",
        "requirements": ["code_review", "security_awareness", "diff_analysis"],
        "risk_constraint": "low — read-only review, no mutation",
    },
    "git-integrator": {
        "purpose": "Push, create draft PR, Ready, merge, cleanup — only after operator approval",
        "requirements": ["git_operations", "gh_cli", "audit_trail"],
        "risk_constraint": "high — writes to remote, requires explicit operator approval for each action",
    },
}

# ── Available Models (no secrets, just role fitness) ──────────────────

MODELS = {
    "deepseek-v4-pro": {
        "provider": "deepseek",
        "strengths": ["coding", "instruction_following", "structured_output"],
        "role_fit": {"orchestrator": 0.6, "explorer": 0.7, "planner": 0.8, "implementer": 0.9, "tester-a": 0.8, "tester-b": 0.8, "reviewer-a": 0.8, "reviewer-b": 0.8, "git-integrator": 0.5},
        "allowed_nodes": ["5bao", "9bao", "21bao"],
        "operator_selection_required": True,
        "guarded_blocked": True,
        "block_reason": "deepseek-v4-pro requires explicit operator approval; not default recommended",
    },
    "mimo-v2.5-pro": {
        "provider": "xiaomi",
        "strengths": ["chinese_output", "instruction_following", "planning"],
        "role_fit": {"orchestrator": 0.7, "explorer": 0.7, "planner": 0.9, "implementer": 0.7, "tester-a": 0.6, "tester-b": 0.6, "reviewer-a": 0.7, "reviewer-b": 0.7, "git-integrator": 0.4},
        "allowed_nodes": ["5bao", "9bao", "21bao", "win"],
        "operator_selection_required": True,
        "blocked": True,
        "block_reason": "mimo/xiaomi models are temporary_unavailable",
    },
    "minimax-m3": {
        "provider": "minimax",
        "strengths": ["coding", "testing", "structured_output"],
        "role_fit": {"orchestrator": 0.6, "explorer": 0.7, "planner": 0.7, "implementer": 0.8, "tester-a": 0.8, "tester-b": 0.8, "reviewer-a": 0.8, "reviewer-b": 0.8, "git-integrator": 0.5},
        "allowed_nodes": ["5bao", "9bao", "21bao"],
        "operator_selection_required": True,
    },
    "volcengine-doubao": {
        "provider": "volcengine",
        "strengths": ["chinese_output", "summarization", "planning"],
        "role_fit": {"orchestrator": 0.8, "explorer": 0.7, "planner": 0.8, "implementer": 0.6, "tester-a": 0.6, "tester-b": 0.6, "reviewer-a": 0.7, "reviewer-b": 0.7, "git-integrator": 0.5},
        "allowed_nodes": ["5bao", "9bao", "21bao"],
        "operator_selection_required": True,
    },
}

# ── Operator Checkpoint Gate (DSP-002) ──


def require_operator_checkpoint(role: str = None,
                                model_alias: str = None,
                                phase_id: str = None) -> dict:
    """Lightweight operator checkpoint gate — fail-closed.

    Simulates the approval gate that must exist between route-all
    recommendation and actual dispatch. In production this would
    reference an operator-approved dispatch manifest. For I22,
    this provides a fail-closed gate that rejects any dispatch
    that hasn't been explicitly approved.

    Returns {"approved": bool, "reason": str, "gate": str}.
    Always returns {"approved": False, "reason": "operator_checkpoint_required",
                    "gate": "dsp-002"} — dispatch must not proceed without
                    explicit operator approval manifest.
    """
    return {
        "approved": False,
        "reason": "operator_checkpoint_required",
        "gate": "dsp-002",
        "detail": {
            "role": role,
            "model_alias": model_alias,
            "phase_id": phase_id,
        },
        "message": "No operator-approved dispatch manifest. "
                   "Hermes/WebDEV/vibedev may only recommend; "
                   "operator must approve before dispatch.",
    }


# ── Central Pool Guard (POOL-001) ──


# Known extra visible models that exist in provider API but NOT in central pool.
# These MUST NOT be resolved by alias resolver or used in route-all.
EXTRA_VISIBLE_MODELS = {
    "opencode-go/deepseek-v4-pro": "extra visible — not in central pool",
    "opencode-go/kimi-k2.7-code": "extra visible — not in central pool",
    "opencode-go/minimax-m2.7": "extra visible — not in central pool",
    "opencode-go/minimax-m3": "extra visible — not in central pool",
    "opencode-go/qwen3.6-plus": "extra visible — not in central pool",
}


def validate_model_in_central_pool(model_id: str) -> dict:
    """Verify a model ID exists in the central model_pool.yaml.

    Returns {"in_pool": bool, "detail": str, "enabled": bool|None}.
    """
    pool = _load_model_pool()
    if pool is None:
        return {"in_pool": False, "detail": "central pool not loadable",
                "enabled": None}
    pm = pool.models.get(model_id)
    if pm is None:
        return {"in_pool": False,
                "detail": f"model '{model_id}' not found in central pool",
                "enabled": None}
    return {"in_pool": True,
            "detail": f"model '{model_id}' found in central pool",
            "enabled": pm.get("enabled", False)}


def is_extra_visible_model(model_id: str) -> bool:
    """Check if a model ID is an extra visible model (not in central pool)."""
    return model_id in EXTRA_VISIBLE_MODELS


# ── Hard Boundary Enforcement (ARCH-003) ──


FORBIDDEN_OPERATIONS = {
    "direct_ssh_bypass": "SSH commands must come from registry, not direct",
    "secret_env_write": "secret/env write requires operator approval",
    "secret_write": "secret/env write requires operator approval",
    "node_write": "node filesystem write requires operator approval",
    "model_call": "model API call requires operator-approved dispatch",
    "merge": "merge requires explicit operator approval",
    "push": "push requires explicit operator approval",
    "merge_push": "merge/push requires explicit operator approval",
}


def check_forbidden_operation(operation: str) -> dict:
    """Check if an operation is forbidden by hard boundary.

    Returns {"allowed": bool, "reason": str}.
    """
    if operation in FORBIDDEN_OPERATIONS:
        return {
            "allowed": False,
            "reason": FORBIDDEN_OPERATIONS[operation],
        }
    return {"allowed": True, "reason": "operation not in forbidden list"}

def _load_model_pool():
    """Load central model pool for guard filtering."""
    try:
        from opencode_model_pool import ModelPool
        yp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model_pool.yaml")
        if os.path.exists(yp):
            return ModelPool.from_yaml(yp)
    except Exception:
        pass
    return None


# ── Policy ────────────────────────────────────────────────────────────

NO_AUTO_SWITCH_REASONS = [
    "HTTP 401 — invalid credentials",
    "configuration error",
    "permission error",
    "Git conflict",
    "provider key missing",
]

AUTO_SWITCH_ALLOWED = [
    "quota exhaustion",
    "rate limiting (429)",
    "provider unavailable (503)",
    "timeout",
]


def recommend(role, risk_level="low", node_id=None, enforce_guards=True):
    """Recommend models for a given role and risk level."""
    if role not in ROLES:
        return {"error": f"unknown role: {role}"}

    candidates = []

    # Load model pool for guard filtering
    pool = _load_model_pool() if enforce_guards else None

    # Build routing-name to YAML model-id mapping
    _ROUTING_TO_YAML = {
        "deepseek-v4-pro": "deepseek-plan-deepseek-v4-pro",
        "mimo-v2.5-pro": "xiaomi-mimo-v2-5-pro",
        "minimax-m3": "minimax-plan-minimax-m3",
        "volcengine-doubao": "volcengine-doubao-1-5-pro-256k",
    }

    for model_name, model_info in MODELS.items():
        # Apply model selection guards
        if enforce_guards and pool:
            yaml_id = _ROUTING_TO_YAML.get(model_name)
            pm = pool.models.get(yaml_id) if yaml_id else None

            # ── POOL-001: Central pool guard ──────────────────
            # Verify model exists in central pool via YAML ID
            if yaml_id:
                pool_check = validate_model_in_central_pool(yaml_id)
                if not pool_check.get("in_pool"):
                    continue  # Block: not in central pool
                # Also check enabled/verified status from guard function
                if pool_check.get("enabled") is False:
                    continue  # Block: disabled in central pool
            # ── POOL-001: Extra visible model guard ───────────
            if is_extra_visible_model(model_name):
                continue  # Block: extra visible
            # ─────────────────────────────────────────────────

            if pm:
                if pm.get("status") in ("temporary_unavailable", "unverified"):
                    continue
                if pm.get("provider") == "xiaomi" or "mimo" in model_name.lower():
                    continue
                if node_id:
                    an = pm.get("allowed_nodes", [])
                    if an and node_id not in an:
                        continue
                if pm.get("smoke_required", False):
                    sr = pm.get("smoke_results", {})
                    if node_id and sr.get(node_id, {}).get("status") == "failed":
                        continue
            else:
                # Model not in YAML pool - block if guards enabled (unverified)
                if "mimo" in model_name.lower() or model_info.get("provider") == "xiaomi":
                    continue
                # Block models with no YAML entry (they are unverified)
                if yaml_id is None:
                    continue
            # Respect guarded_blocked flag (e.g. deepseek-v4-pro requires operator approval)
            if model_info.get("guarded_blocked"):
                continue
        fit = model_info["role_fit"].get(role, 0)
        candidates.append({
            "model": model_name,
            "provider": model_info["provider"],
            "fitness": fit,
            "strengths": model_info["strengths"],
        })

    candidates.sort(key=lambda c: c["fitness"], reverse=True)

    return {
        "role": role,
        "purpose": ROLES[role]["purpose"],
        "risk_level": risk_level,
        "risk_constraint": ROLES[role]["risk_constraint"],
        "candidates": candidates,
        "recommended": candidates[0]["model"] if candidates else None,
        "auto_switch_policy": {
            "allowed_on": AUTO_SWITCH_ALLOWED,
            "blocked_on": NO_AUTO_SWITCH_REASONS,
            "requires_operator_approval": True,
        },
        "node_attribution": {
            "controller_node": "windows",
            "model_selection": "operator_approved",
        },
    }


def _load_worker_registry():
    """Dynamically load worker registry from vibe_worker_registry.DEFAULT_WORKERS.

    Falls back to a minimal dict if registry import fails.
    Returns dict of {worker_id: WorkerNode-like dict}.
    """
    try:
        from vibe_worker_registry import DEFAULT_WORKERS, NodeStatus
        out = {}
        for wid, wn in DEFAULT_WORKERS.items():
            out[wid] = {
                "worker_id": wid,
                "node_type": wn.node_type,
                "transport": getattr(wn, "transport", "ssh"),
                "vpn_address": getattr(wn, "ssh_host", "") or getattr(wn, "vpn_address", ""),
                "ssh_port": getattr(wn, "ssh_port", 0),
                "workspace_root": getattr(wn, "workspace_root", ""),
                "capabilities": list(getattr(wn, "capabilities", [])),
                "health_status": getattr(wn, "health_status", NodeStatus.UNKNOWN.value if hasattr(NodeStatus, "UNKNOWN") else "UNKNOWN"),
                "enabled": getattr(wn, "enabled", True),
                "maintenance_status": getattr(wn, "maintenance_status", "active"),
            }
        return out
    except Exception as e:
        # Fallback: minimal dict (must NEVER hardcode 5bao/9bao-only)
        return {
            "_load_error": str(e),
            "_note": "registry load failed; route-all must BLOCK or report UNKNOWN_REQUIRES_OPERATOR",
        }


def _resolve_node_for_role(role, registry):
    """Resolve which node should host a role, based on registry capabilities.

    Returns (node_id, attribution_dict) or (None, error_dict).
    """
    if not registry or "_load_error" in registry:
        return None, {
            "error": "REGISTRY_UNAVAILABLE",
            "message": "worker registry not loaded; route-all cannot determine nodes",
            "operator_action_required": "verify vibe_worker_registry.py import",
        }

    # Role-to-node preference (declared, not hardcoded fixed list)
    ROLE_NODE_PREFERENCE = {
        "orchestrator":    ["21bao", "win"],
        "planner":         ["21bao", "win"],
        "git-integrator":  ["21bao", "win"],
        "implementer":     ["5bao", "9bao", "21bao"],
        "tester-a":        ["5bao", "9bao"],
        "tester-b":        ["9bao", "5bao"],
        "reviewer-a":      ["9bao", "5bao"],
        "reviewer-b":      ["21bao", "9bao"],
        "explorer":        ["5bao", "9bao", "21bao"],
    }

    preferred = ROLE_NODE_PREFERENCE.get(role, [])
    candidates = []
    for nid in preferred:
        node = registry.get(nid)
        if not node:
            continue
        if not node.get("enabled", True):
            continue
        if node.get("maintenance_status") == "maintenance":
            continue
        if node.get("health_status") == "OFFLINE":
            continue
        candidates.append((nid, node))

    if not candidates:
        return None, {
            "error": "NO_AVAILABLE_NODE",
            "message": f"no available node for role={role}; preferred={preferred}",
            "operator_action_required": "health-check required or operator must confirm",
        }

    # Pick first available; could be load-balanced in future
    nid, node = candidates[0]
    return nid, {
        "node_id": nid,
        "node_type": node["node_type"],
        "transport": node["transport"],
        "vpn_address": node.get("vpn_address", ""),
        "capabilities": node.get("capabilities", []),
        "health_status": node.get("health_status", "UNKNOWN"),
    }


def route_all():
    """Route all 9 roles with node attribution, operator checkpoint, and pool guard.

    ├─ DSP-002: require_operator_checkpoint() — fail-closed gate
    ├─ ARCH-001: runtime_enforce() — architecture contract verification
    ├─ POOL-001: validate_model_in_central_pool() — each recommended model
    └─ POOL-001: is_extra_visible_model() — extra visible models blocked

    Uses dynamic worker registry (no hardcoded fixed node list).
    Each node is checked for: enabled, maintenance, health_status != OFFLINE.
    UNKNOWN health_status requires operator confirmation before assignment.
    """
    gate_results = {}

    # ── DSP-002: Operator Checkpoint Gate ─────────────────────
    # Fail-closed: without operator-approved dispatch manifest,
    # dispatch must not proceed. This call is the gate entry point.
    gate_results["operator_checkpoint"] = require_operator_checkpoint(
        phase_id="route-all")

    # ── ARCH-001/003: Runtime Enforcement Gate ────────────────
    # Verify architecture contract (worker transport, SSH bypass,
    # forbidden usernames) at every route-all entry.
    try:
        from vibe_architecture_contract import runtime_enforce
        gate_results["runtime_enforcement"] = runtime_enforce()
    except ImportError:
        gate_results["runtime_enforcement"] = {
            "passed": False,
            "errors": ["vibe_architecture_contract not importable"],
            "warnings": [],
        }
    # ──────────────────────────────────────────────────────────

    results = {}
    registry = _load_worker_registry()

    for role in ROLES:
        rec = recommend(role)
        node_id, attribution = _resolve_node_for_role(role, registry)

        rec["planned_alias"] = rec.get("recommended", "")
        rec["planned_provider_model"] = ""
        rec["operator_selection_required"] = True
        rec["fallback_count"] = 0

        # ── POOL-001: Central Pool Guard for each role ─────────
        recommended = rec.get("recommended", "")
        if recommended:
            # Use YAML ID mapping for pool lookup (routing name != YAML key)
            _ROUTING_TO_YAML = {
                "deepseek-v4-pro": "deepseek-plan-deepseek-v4-pro",
                "mimo-v2.5-pro": "xiaomi-mimo-v2-5-pro",
                "minimax-m3": "minimax-plan-minimax-m3",
                "volcengine-doubao": "volcengine-doubao-1-5-pro-256k",
            }
            yaml_id = _ROUTING_TO_YAML.get(recommended, recommended)
            pool_check = validate_model_in_central_pool(yaml_id)
            rec["_pool_verified"] = pool_check.get("in_pool", False)
            rec["_pool_enabled"] = pool_check.get("enabled")
            rec["_extra_visible"] = is_extra_visible_model(recommended)
            if not pool_check.get("in_pool"):
                rec["_pool_warning"] = (
                    f"Model '{recommended}' not in central pool — "
                    "cannot dispatch without operator override")
            if is_extra_visible_model(recommended):
                rec["_pool_warning"] = (
                    f"Model '{recommended}' is extra visible — "
                    "BLOCKED from route/dispatch/alias")
        else:
            rec["_pool_verified"] = False
            rec["_pool_enabled"] = None
            rec["_extra_visible"] = False
        # ──────────────────────────────────────────────────────

        if node_id:
            rec["planned_node"] = node_id
            rec["node_attribution"] = attribution
            # 3 independent physical locations (per registry)
            rec["node_isolation"] = "physical"
            rec["physical_isolation_claimed"] = True
            rec["node_degradation_requires_operator_approval"] = False
            rec["allowed_nodes_check"] = (
                f"node={node_id} from registry; "
                f"transport={attribution.get('transport')}; "
                f"health={attribution.get('health_status')}"
            )
        else:
            rec["planned_node"] = None
            rec["node_attribution"] = attribution
            rec["node_isolation"] = "UNKNOWN"
            rec["physical_isolation_claimed"] = False
            rec["node_degradation_requires_operator_approval"] = True
            rec["allowed_nodes_check"] = (
                f"NO_AVAILABLE_NODE for role={role}; error={attribution.get('error')}"
            )
        results[role] = rec
    results["_gate_results"] = gate_results
    return results


def self_check(output_json=False):
    checks = []
    checks.append({"name": "version", "passed": True, "message": VERSION})

    # Implementer recommendation
    r = recommend("implementer")
    checks.append({
        "name": "implementer_recommendation",
        "passed": r.get("recommended") is not None and len(r.get("candidates", [])) >= 2,
        "message": f"recommended={r.get('recommended')} candidates={len(r.get('candidates', []))}",
    })

    # Reviewer recommendation
    r2 = recommend("reviewer-a")
    checks.append({
        "name": "reviewer-a_recommendation",
        "passed": r2.get("recommended") is not None,
        "message": f"recommended={r2.get('recommended')}",
    })

    # Summarizer recommendation
    r3 = recommend("explorer")
    checks.append({
        "name": "explorer_recommendation",
        "passed": r3.get("recommended") is not None,
        "message": f"recommended={r3.get('recommended')}",
    })

    # Auto-switch policy present
    checks.append({
        "name": "auto_switch_policy",
        "passed": len(r.get("auto_switch_policy", {}).get("blocked_on", [])) >= 3,
        "message": f"blocked_reasons={len(r.get('auto_switch_policy', {}).get('blocked_on', []))}",
    })

    # Unknown role returns error
    r_bad = recommend("nonexistent")
    checks.append({
        "name": "unknown_role_error",
        "passed": "error" in r_bad,
        "message": f"error={r_bad.get('error', 'none')}",
    })

    # Has node attribution
    checks.append({
        "name": "has_attribution",
        "passed": "controller_node" in r.get("node_attribution", {}),
        "message": "present",
    })

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    return {"overall": "PASS" if passed == total else "FAIL", "passed": passed, "total": total, "checks": checks}


def build_parser():
    p = argparse.ArgumentParser(prog="vibe_model_routing_policy")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument("--json", dest="output_json", action="store_true")
    p.add_argument("--self-check", dest="self_check_flag", action="store_true")
    p.add_argument("--runtime-enforce", dest="runtime_enforce_flag",
                   action="store_true",
                   help="Run architecture contract runtime enforcement gate")
    sub = p.add_subparsers(dest="command")
    p_route = sub.add_parser("route")
    p_route.add_argument("--task-type", required=True)
    p_route.add_argument("--risk", default="low")
    sub.add_parser("route-all")
    p_check = sub.add_parser("check")
    p_check.add_argument("--operation", required=True,
                         help="Operation to check: model_call, node_write, "
                              "secret_write, merge, push, direct_ssh_bypass")
    return p


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)

    if args.self_check_flag:
        result = self_check(args.output_json)
    elif args.runtime_enforce_flag:
        # ARCH-001/003: Runtime enforcement gate from CLI
        from vibe_architecture_contract import runtime_enforce
        result = runtime_enforce()
    elif args.command == "route":
        result = recommend(args.task_type, args.risk)
    elif args.command == "route-all":
        result = route_all()
    elif args.command == "check":
        # ARCH-003: Forbidden operation check gate from CLI
        result = check_forbidden_operation(args.operation)
    else:
        p.print_help()
        return 1

    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        if "overall" in result:
            print(f"Overall: {result['overall']} ({result['passed']}/{result['total']})")
            for c in result.get("checks", []):
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  [{icon}] {c['name']}: {c['message']}")
        elif "recommended" in result:
            print(f"Role: {result['role']} → {result['recommended']}")
            print(f"  Candidates: {', '.join(c['model'] for c in result.get('candidates', []))}")
        else:
            for role, data in result.items():
                print(f"  {role}: {data.get('recommended', 'N/A')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
