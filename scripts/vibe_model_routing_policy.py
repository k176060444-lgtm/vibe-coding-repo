#!/usr/bin/env python3
"""Model Routing Policy v1.0.0 — recommend model roles for tasks.

Usage:
    python3 scripts/vibe_model_routing_policy.py --json route --task-type implementer --risk low
    python3 scripts/vibe_model_routing_policy.py --json route-all
    python3 scripts/vibe_model_routing_policy.py self-check [--json]
"""

import argparse
import json
import sys
from datetime import datetime, timezone

VERSION = "1.0.0"

# ── Model Role Definitions ───────────────────────────────────────────

ROLES = {
    "planner": {
        "purpose": "Decompose requirements into auditable WO plans",
        "requirements": ["instruction_following", "structured_output", "planning"],
        "risk_constraint": "low — read-only planning, no mutation",
    },
    "implementer": {
        "purpose": "Write code, fix bugs, resolve conflicts",
        "requirements": ["coding", "testing", "git_operations"],
        "risk_constraint": "medium — writes to worktree only, reviewed before merge",
    },
    "reviewer": {
        "purpose": "Blind review of diffs, security checks, quality gates",
        "requirements": ["code_review", "security_awareness", "attention_to_detail"],
        "risk_constraint": "low — read-only review, no mutation",
    },
    "summarizer": {
        "purpose": "Generate operator reports, daily briefings, batch summaries",
        "requirements": ["summarization", "chinese_output", "structured_output"],
        "risk_constraint": "low — no mutation, no token access",
    },
    "recovery": {
        "purpose": "Diagnose and recover from failures (gateway, worker, batch)",
        "requirements": ["debugging", "system_knowledge", "careful_execution"],
        "risk_constraint": "high — may restart services, requires human approval for destructive ops",
    },
}

# ── Available Models (no secrets, just role fitness) ──────────────────

MODELS = {
    "deepseek-v4-pro": {
        "provider": "deepseek",
        "strengths": ["coding", "instruction_following", "structured_output"],
        "role_fit": {"planner": 0.8, "implementer": 0.9, "reviewer": 0.8, "summarizer": 0.7, "recovery": 0.7},
    },
    "mimo-v2.5-pro": {
        "provider": "xiaomi",
        "strengths": ["chinese_output", "instruction_following", "planning"],
        "role_fit": {"planner": 0.9, "implementer": 0.7, "reviewer": 0.7, "summarizer": 0.9, "recovery": 0.6},
    },
    "minimax-m3": {
        "provider": "minimax",
        "strengths": ["coding", "testing", "structured_output"],
        "role_fit": {"planner": 0.7, "implementer": 0.8, "reviewer": 0.8, "summarizer": 0.7, "recovery": 0.7},
    },
    "volcengine-doubao": {
        "provider": "volcengine",
        "strengths": ["chinese_output", "summarization", "planning"],
        "role_fit": {"planner": 0.8, "implementer": 0.6, "reviewer": 0.7, "summarizer": 0.9, "recovery": 0.5},
    },
}

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


def recommend(role, risk_level="low"):
    """Recommend models for a given role and risk level."""
    if role not in ROLES:
        return {"error": f"unknown role: {role}"}

    candidates = []
    for model_name, model_info in MODELS.items():
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
    """Route all roles."""
    results = {}
    for role in ROLES:
        results[role] = recommend(role)
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
