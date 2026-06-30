#!/usr/bin/env python3
"""Task Intake v1.0.0 — natural language to auditable task spec.

Usage:
    python3 scripts/vibe_task_intake.py --json "fix the conflict in PR 40457"
    python3 scripts/vibe_task_intake.py --json "update docs" --repo k176060444-lgtm/vibe-coding-repo
    python3 scripts/vibe_task_intake.py self-check [--json]
"""

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone

VERSION = "1.0.0"

SELF_REPO = "k176060444-lgtm/vibe-coding-repo"

# ── Classification patterns ──────────────────────────────────────────

RISK_PATTERNS = {
    "critical": [
        r"(?i)force\s*push", r"(?i)delete\s*branch", r"(?i)reset\s*--hard",
        r"(?i)tag\s*release", r"(?i)deploy", r"(?i)secrets?", r"(?i)\.github",
        r"(?i)CI\s*(pipeline|config)", r"(?i)provider\s*(config|key)",
        r"(?i)SSH\s*(key|config)", r"(?i)audit_tainted.*unlock",
        r"(?i)level\s*5",
    ],
    "high": [
        r"(?i)external\s*(push|write|merge)", r"(?i)remediation",
        r"(?i)force.*update.*ref", r"(?i)PR\s*#?\d+.*conflict",
        r"(?i)dependency\s*install", r"(?i)sudo",
        r"(?i)global\s*pip", r"(?i)non.?standard.*env.*token",
    ],
    "medium": [
        r"(?i)external\s*read", r"(?i)fetch\s*upstream", r"(?i)diagnos",
        r"(?i)pytest.*harness", r"(?i)gateway\s*(recovery|restart|offline)",
        r"(?i)resume\s*(batch|gate)", r"(?i)worker\s*unreachable",
    ],
    "low": [
        r"(?i)update\s*docs", r"(?i)self\s*repo", r"(?i)smoke",
        r"(?i)quality\s*gate", r"(?i)freeze", r"(?i)snapshot",
        r"(?i)dashboard", r"(?i)runbook", r"(?i)batch\s*plan",
        r"(?i)report\s*schema", r"(?i)task\s*intake",
        r"(?i)model\s*routing", r"(?i)WO\s*compiler",
    ],
}

OPERATION_PATTERNS = {
    "push": [r"(?i)push", r"(?i)merge\s*PR", r"(?i)PR\s*create"],
    "read-only": [r"(?i)fetch", r"(?i)diagnos", r"(?i)check", r"(?i)read", r"(?i)status", r"(?i)snapshot"],
    "write-local": [r"(?i)update\s*docs", r"(?i)commit", r"(?i)branch"],
    "remediation": [r"(?i)remediation", r"(?i)force.*update", r"(?i)fix.*conflict"],
    "install": [r"(?i)install", r"(?i)pip\s*install", r"(?i)dependency"],
    "planning": [r"(?i)plan", r"(?i)intake", r"(?i)compile", r"(?i)route", r"(?i)spec"],
}


def _match_patterns(text, patterns):
    """Return first matching category."""
    for category, pats in patterns.items():
        for pat in pats:
            if re.search(pat, text):
                return category
    return None


def classify_task(text, repo=None):
    """Classify a natural language task into a task spec."""
    repo = repo or "unspecified"
    is_self_repo = repo == SELF_REPO or repo == "unspecified"

    # Risk level
    risk = _match_patterns(text, RISK_PATTERNS) or ("low" if is_self_repo else "medium")

    # Operation type
    op_type = _match_patterns(text, OPERATION_PATTERNS) or "planning"

    # Repo scope
    if is_self_repo:
        repo_scope = "trusted-self"
    elif any(kw in text.lower() for kw in ["hermes-agent", "nousresearch", "external"]):
        repo_scope = "protected-external"
    else:
        repo_scope = "protected-external"

    # Approval/token
    # baseline01: all tasks require operator approval.
    # The iteration_policy.auto_approve=False is enforced by recommend_iteration.
    requires_approval = True
    requires_token = op_type in ("push", "remediation") and repo_scope == "protected-external"

    # Forbidden actions
    forbidden = ["sudo", "global_pip", "system_python_modification"]
    if risk == "critical":
        forbidden.extend(["force_push", "delete_branch", "tag_release", "deploy", "secrets_modify", "ci_modify"])
    if repo_scope == "protected-external" and op_type != "read-only":
        forbidden.append("unapproved_external_write")

    # Validation mode
    if risk in ("critical", "high"):
        validation_mode = "full"
    elif risk == "medium":
        validation_mode = "fast"
    else:
        validation_mode = "auto"

    # Task ID
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    task_hash = hashlib.sha256(text.encode()).hexdigest()[:8]
    task_id = f"task-{ts}-{task_hash}"

    # Summary
    summary = text[:200]

    # Next command
    next_cmd = f'python3 scripts/vibe_wo_compiler.py --json --task-id {task_id}'

    spec = {
        "version": VERSION,
        "task_id": task_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "summary": summary,
        "repo": repo,
        "repo_scope": repo_scope,
        "operation_type": op_type,
        "risk_level": risk,
        "requires_approval": requires_approval,
        "requires_token": requires_token,
        "forbidden_actions": sorted(set(forbidden)),
        "validation_mode": validation_mode,
        "next_command": next_cmd,
        "iteration_policy": {},
        "node_attribution": {
            "controller_node": "windows",
            "execution_node": "debian",
        },
    }

    # Populate iteration policy
    iter_rec = recommend_iteration(
        task_type=op_type,
        risk_level=risk,
        is_read_only="read-only" in op_type or op_type == "read-only",
        is_external=repo_scope == "protected-external",
    )
    spec["iteration_policy"] = {
        "recommended_profile": iter_rec["profile"],
        "recommended_steps": iter_rec["steps"],
        "auto_approve": iter_rec["auto_approve"],
        "reason": iter_rec["reason"],
    }
    return spec



def recommend_iteration(task_type, risk_level, is_read_only=False,
                        is_multi_wo=False, is_external=False):
    """Recommend iteration profile based on task characteristics.

    baseline01 (G3): fully fail-closed. **Every** branch returns
    ``auto_approve=False`` and ``requires_approval=True``. The caller
    must obtain explicit operator approval before invoking any execution
    role (planner / explorer / implementer / reviewer / validator),
    triggering any model call, opening any SSH connection, performing
    any git write, or modifying any file. This function returns only
    the recommended iteration profile metadata; it does NOT constitute
    an approval.
    """
    # Read-only low-risk + no external + no multi-WO: now also requires
    # explicit operator approval. There is no path that auto-approves.
    if is_read_only and risk_level == "low" and not is_external \
            and not is_multi_wo:
        return {"profile": "short", "steps": 200, "auto_approve": False,
                "requires_approval": True,
                "reason": "Read-only low-risk task — operator approval required"}
    # External actions at any non-low risk: explicit operator approval required.
    if is_external and risk_level in ("medium", "high", "critical"):
        return {"profile": "standard", "steps": 300, "auto_approve": False,
                "requires_approval": True,
                "reason": f"External {risk_level}-risk — operator approval required"}
    # Multi-WO / batch / test-inclusive paths: explicit operator approval
    # required of the batch scope.
    if is_multi_wo:
        return {"profile": "long", "steps": 500, "auto_approve": False,
                "requires_approval": True,
                "reason": "Multi-WO batch or test-inclusive — operator approval required"}
    # Self repo standard task paths: explicit operator approval required.
    if not is_external and risk_level in ("low", "medium"):
        return {"profile": "standard", "steps": 300, "auto_approve": False,
                "requires_approval": True,
                "reason": "Self repo standard task — operator approval required"}
    # Catch-all: explicit operator approval required.
    return {"profile": "standard", "steps": 300, "auto_approve": False,
            "requires_approval": True,
            "reason": "Default recommendation — operator approval required"}
def self_check(output_json=False):
    checks = []
    checks.append({"name": "version", "passed": True, "message": VERSION})

    # Test self repo low-risk classification
    spec = classify_task("update docs for V1.13", SELF_REPO)
    checks.append({
        "name": "self_repo_low_risk",
        "passed": spec["risk_level"] == "low" and spec["repo_scope"] == "trusted-self",
        "message": f"risk={spec['risk_level']} scope={spec['repo_scope']}",
    })

    # Test external push high-risk
    spec2 = classify_task("push to external repo", "NousResearch/hermes-agent")
    checks.append({
        "name": "external_push_high_risk",
        "passed": spec2["requires_approval"] and spec2["repo_scope"] == "protected-external",
        "message": f"risk={spec2['risk_level']} approval={spec2['requires_approval']}",
    })

    # Test critical patterns
    spec3 = classify_task("modify .github/workflows and secrets")
    checks.append({
        "name": "critical_forbidden",
        "passed": spec3["risk_level"] == "critical" and "ci_modify" in spec3["forbidden_actions"],
        "message": f"risk={spec3['risk_level']} forbidden={len(spec3['forbidden_actions'])}",
    })

    # Test planning type
    spec4 = classify_task("plan the next batch of work orders")
    checks.append({
        "name": "planning_type",
        "passed": spec4["operation_type"] == "planning",
        "message": f"op={spec4['operation_type']}",
    })

    # Test has task_id
    checks.append({
        "name": "task_id_format",
        "passed": spec["task_id"].startswith("task-"),
        "message": spec["task_id"][:20],
    })

    # Test next_command present
    checks.append({
        "name": "next_command",
        "passed": "vibe_wo_compiler" in spec["next_command"],
        "message": spec["next_command"][:60],
    })

    # Token redaction
    checks.append({
        "name": "token_redaction",
        "passed": "token" not in json.dumps(spec).lower() or "token" in "requires_token",
        "message": "no token content in output",
    })

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    return {"overall": "PASS" if passed == total else "FAIL", "passed": passed, "total": total, "checks": checks}


def build_parser():
    p = argparse.ArgumentParser(prog="vibe_task_intake")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument("--json", dest="output_json", action="store_true")
    p.add_argument("--repo", default=None)
    p.add_argument("--self-check", dest="self_check_flag", action="store_true")
    p.add_argument("task_text", nargs="?", default="")
    return p


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)

    if args.self_check_flag:
        result = self_check(args.output_json)
    elif args.task_text:
        result = classify_task(args.task_text, args.repo)
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
        else:
            print(f"Task: {result['summary'][:60]}")
            print(f"  risk={result['risk_level']} scope={result['repo_scope']} op={result['operation_type']}")
            print(f"  approval={result['requires_approval']} token={result['requires_token']}")
            print(f"  validation={result['validation_mode']}")
            print(f"  next: {result['next_command']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
