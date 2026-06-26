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
        "allowed_nodes": ["5bao", "9bao"],
        "operator_selection_required": True,
        "guarded_blocked": True,
        "block_reason": "deepseek-v4-pro requires explicit operator approval; not default recommended",
    },
    "mimo-v2.5-pro": {
        "provider": "xiaomi",
        "strengths": ["chinese_output", "instruction_following", "planning"],
        "role_fit": {"orchestrator": 0.7, "explorer": 0.7, "planner": 0.9, "implementer": 0.7, "tester-a": 0.6, "tester-b": 0.6, "reviewer-a": 0.7, "reviewer-b": 0.7, "git-integrator": 0.4},
        "allowed_nodes": ["5bao", "9bao", "win"],
        "operator_selection_required": True,
        "blocked": True,
        "block_reason": "mimo/xiaomi models are temporary_unavailable",
    },
    "minimax-m3": {
        "provider": "minimax",
        "strengths": ["coding", "testing", "structured_output"],
        "role_fit": {"orchestrator": 0.6, "explorer": 0.7, "planner": 0.7, "implementer": 0.8, "tester-a": 0.8, "tester-b": 0.8, "reviewer-a": 0.8, "reviewer-b": 0.8, "git-integrator": 0.5},
        "allowed_nodes": ["5bao", "9bao"],
        "operator_selection_required": True,
    },
    "volcengine-doubao": {
        "provider": "volcengine",
        "strengths": ["chinese_output", "summarization", "planning"],
        "role_fit": {"orchestrator": 0.8, "explorer": 0.7, "planner": 0.8, "implementer": 0.6, "tester-a": 0.6, "tester-b": 0.6, "reviewer-a": 0.7, "reviewer-b": 0.7, "git-integrator": 0.5},
        "allowed_nodes": ["5bao", "9bao"],
        "operator_selection_required": True,
    },
}

# ── Model Pool Guard ──

def _load_model_pool():
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
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
        "deepseek-v4-pro": "deepseek-deepseek-chat",
        "mimo-v2.5-pro": "xiaomi-mimo-v2-5-pro",
        "minimax-m3": "minimax-minimax-m2-5",
        "volcengine-doubao": "volcengine-doubao-1-5-pro-256k",
    }

    for model_name, model_info in MODELS.items():
        # Apply model selection guards
        if enforce_guards and pool:
            yaml_id = _ROUTING_TO_YAML.get(model_name)
            pm = pool.models.get(yaml_id) if yaml_id else None
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


def route_all():
    """Route all 9 roles with node attribution and operator selection requirement."""
    results = {}
    for role in ROLES:
        rec = recommend(role)
        # Add VibeDev 9-role metadata
        rec["planned_node"] = "LOGICAL_NODE_ONLY"
        rec["planned_alias"] = rec.get("recommended", "")
        rec["planned_provider_model"] = ""
        rec["allowed_nodes_check"] = "5bao and 9bao share same physical node (KK-5bao); LOGICAL_NODE_ONLY"
        rec["node_isolation"] = "logical_only"
        rec["physical_isolation_claimed"] = False
        rec["operator_selection_required"] = True
        rec["fallback_count"] = 0
        rec["node_degradation_requires_operator_approval"] = True
        results[role] = rec
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
    r2 = recommend("reviewer")
    checks.append({
        "name": "reviewer_recommendation",
        "passed": r2.get("recommended") is not None,
        "message": f"recommended={r2.get('recommended')}",
    })

    # Summarizer recommendation
    r3 = recommend("summarizer")
    checks.append({
        "name": "summarizer_recommendation",
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
    sub = p.add_subparsers(dest="command")
    p_route = sub.add_parser("route")
    p_route.add_argument("--task-type", required=True)
    p_route.add_argument("--risk", default="low")
    sub.add_parser("route-all")
    return p


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)

    if args.self_check_flag:
        result = self_check(args.output_json)
    elif args.command == "route":
        result = recommend(args.task_type, args.risk)
    elif args.command == "route-all":
        result = route_all()
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
