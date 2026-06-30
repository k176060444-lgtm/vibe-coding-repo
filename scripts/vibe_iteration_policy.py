#!/usr/bin/env python3
"""vibe_iteration_policy.py v1.0.0

VibeCoding iteration budget policy. Maps task profiles to OpenCode `steps`
values and enforces approval rules for high-risk tasks.

DEPRECATED (baseline01): Production approval enforcement is handled by
fail-closed gates in vibe_task_intake.py, vibe_batch_runner.py, and
git_pr_approval_gate.py. Values and metadata in this module (auto_approve,
requires_approval) are retained for legacy/test compatibility only.
Do not wire this module into runtime approval decisions.

Profiles:
  short=200    — read-only scout, dashboard, health, gateway queries
  standard=300 — self repo single WO, small fixes
  long=500     — multi-WO batch, full smoke, docs+tests+freeze
  extended=800 — very large batches (must record reason in final report)

Key rules:
  - High-risk tasks: recommendation only, never auto-approved
  - 429/timeout: no auto model switch, must report or wait for operator
  - 401/config error: BLOCK immediately
  - extended profile: final report MUST include reason
"""

import json
import sys
from datetime import datetime, timezone

VERSION = "1.0.0"

# ── Profile Definitions ──────────────────────────────────────────

PROFILES = {
    "short": {
        "steps": 200,
        "description": "Read-only scout, dashboard, health, gateway queries",
        "auto_approve": True,
        "examples": [
            "read-only investigation",
            "dashboard status",
            "health snapshot",
            "gateway state query",
            "smoke test run (read-only)",
        ],
    },
    "standard": {
        "steps": 300,
        "description": "Self repo single WO, small fixes",
        "auto_approve": True,
        "examples": [
            "self repo single WO",
            "small bug fix",
            "doc update",
            "config tweak",
            "single test addition",
        ],
    },
    "long": {
        "steps": 500,
        "description": "Multi-WO batch, full smoke, docs+tests+freeze",
        "auto_approve": True,
        "examples": [
            "multi-WO batch",
            "full smoke suite",
            "docs + tests + freeze",
            "new script + tests + integration",
            "quality gate full run",
        ],
    },
    "extended": {
        "steps": 800,
        "description": "Very large batches — reason MUST be recorded",
        "auto_approve": False,  # Must record reason
        "examples": [
            "major refactor across many files",
            "multi-batch with external dependencies",
            "migration + rollback plan",
            "cross-repo coordination",
        ],
    },
}

# ── Risk → Approval Rules ────────────────────────────────────────

HIGH_RISK_PATTERNS = [
    "external_write",
    "external_push",
    "remediation_force",
    "secrets",
    "ci",
    "workflow",
    "provider",
    "ssh",
    "deploy",
    "tag",
    "release",
    "force_push",
    "sudo",
    "global_pip",
    "system_python",
]

BLOCKED_PATTERNS = [
    "401",
    "config_error",
    "credential_invalid",
]

NO_AUTO_SWITCH_PATTERNS = [
    "429",
    "timeout",
    "rate_limit",
    "provider_unavailable",
]


def recommend_profile(task_type: str, risk_level: str = "low",
                      is_multi_wo: bool = False, is_external: bool = False,
                      has_tests: bool = False, is_read_only: bool = False
                      ) -> dict:
    """Recommend an iteration profile based on task characteristics.

    NOTE (baseline01): This function is retained for legacy/test compatibility.
    Returned `auto_approve` is legacy metadata, not runtime authorization.
    Production approval enforcement is in vibe_task_intake.py, not here.

    Returns dict with profile_name, steps, auto_approve, reason, warnings.
    """
    warnings = []

    # Rule 1: read-only → short
    if is_read_only and risk_level == "low":
        return {
            "profile": "short",
            "steps": PROFILES["short"]["steps"],
            "auto_approve": True,
            "reason": "Read-only task with low risk",
            "warnings": [],
        }

    # Rule 2: external + high risk → standard (recommendation only)
    if is_external and risk_level in ("medium", "high", "critical"):
        warnings.append(
            "High-risk external task: profile is recommendation only, "
            "requires explicit operator approval"
        )
        return {
            "profile": "standard",
            "steps": PROFILES["standard"]["steps"],
            "auto_approve": False,
            "reason": f"External {risk_level}-risk task — recommendation only",
            "warnings": warnings,
        }

    # Rule 3: multi-WO batch → long
    if is_multi_wo or (has_tests and not is_read_only):
        return {
            "profile": "long",
            "steps": PROFILES["long"]["steps"],
            "auto_approve": True,
            "reason": "Multi-WO batch or test-inclusive task",
            "warnings": warnings,
        }

    # Rule 4: self repo single WO → standard
    if not is_external and risk_level in ("low", "medium"):
        return {
            "profile": "standard",
            "steps": PROFILES["standard"]["steps"],
            "auto_approve": True,
            "reason": "Self repo standard task",
            "warnings": warnings,
        }

    # Default: standard
    return {
        "profile": "standard",
        "steps": PROFILES["standard"]["steps"],
        "auto_approve": True,
        "reason": "Default recommendation",
        "warnings": warnings,
    }


def check_approval_gate(task_type: str, risk_level: str,
                        profile: str) -> dict:
    """Check if a task can proceed with the given profile.

    DEPRECATED (baseline01): This function is legacy-only. Its returned
    `requires_approval` is metadata, not an approval gate. Production
    approval enforcement is in vibe_task_intake.py and related gates.

    Returns dict with allowed, reason, requires_approval.
    """
    # High-risk patterns always require approval
    for pattern in HIGH_RISK_PATTERNS:
        if pattern in task_type.lower() or pattern in risk_level.lower():
            return {
                "allowed": True,  # Can proceed, but needs approval
                "requires_approval": True,
                "reason": f"High-risk pattern '{pattern}' detected",
            }

    # Blocked patterns
    for pattern in BLOCKED_PATTERNS:
        if pattern in task_type.lower():
            return {
                "allowed": False,
                "requires_approval": False,
                "reason": f"BLOCKED: pattern '{pattern}' detected",
            }

    # Extended profile needs reason
    if profile == "extended":
        return {
            "allowed": True,
            "requires_approval": True,
            "reason": "Extended profile requires reason in final report",
        }

    return {
        "allowed": True,
        "requires_approval": False,
        "reason": "Standard approval flow",
    }


def check_model_switch(signal: str) -> dict:
    """Check if a model switch signal requires operator approval.

    429/timeout: must report, no auto-switch.
    401/config: BLOCK immediately.
    """
    for pattern in NO_AUTO_SWITCH_PATTERNS:
        if pattern in signal.lower():
            return {
                "auto_switch": False,
                "action": "REPORT_TO_OPERATOR",
                "reason": f"Signal '{pattern}': no auto model switch allowed",
            }

    for pattern in BLOCKED_PATTERNS:
        if pattern in signal.lower():
            return {
                "auto_switch": False,
                "action": "BLOCK",
                "reason": f"Signal '{pattern}': blocked, no model switch",
            }

    return {
        "auto_switch": False,
        "action": "REPORT_TO_OPERATOR",
        "reason": "Unknown signal: report to operator for decision",
    }


def generate_policy_report(profile: str, steps: int, task_type: str = "",
                           risk_level: str = "", extended_reason: str = ""
                           ) -> dict:
    """Generate a complete policy report for a task."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prof = PROFILES.get(profile, PROFILES["standard"])

    report = {
        "version": VERSION,
        "timestamp": now,
        "iteration_policy": {
            "profile": profile,
            "steps": steps,
            "description": prof["description"],
            "auto_approve": prof["auto_approve"],
        },
        "task_context": {
            "task_type": task_type,
            "risk_level": risk_level,
        },
        "rules": {
            "high_risk_requires_approval": True,
            "429_timeout_no_auto_switch": True,
            "401_config_blocked": True,
            "extended_requires_reason": True,
        },
        "profiles_available": {
            name: {"steps": p["steps"], "description": p["description"]}
            for name, p in PROFILES.items()
        },
    }

    if profile == "extended" and extended_reason:
        report["extended_reason"] = extended_reason

    return report


def self_check() -> dict:
    """Run self-check tests."""
    results = []
    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            results.append({"test": name, "status": "PASS", "detail": detail})
            passed += 1
        else:
            results.append({"test": name, "status": "FAIL", "detail": detail})
            failed += 1

    # Test 1: profiles exist
    check("profiles_exist",
          len(PROFILES) == 4,
          f"Found {len(PROFILES)} profiles")

    # Test 2: short=200
    check("short_steps",
          PROFILES["short"]["steps"] == 200,
          f"short={PROFILES['short']['steps']}")

    # Test 3: standard=300
    check("standard_steps",
          PROFILES["standard"]["steps"] == 300,
          f"standard={PROFILES['standard']['steps']}")

    # Test 4: long=500
    check("long_steps",
          PROFILES["long"]["steps"] == 500,
          f"long={PROFILES['long']['steps']}")

    # Test 5: extended=800
    check("extended_steps",
          PROFILES["extended"]["steps"] == 800,
          f"extended={PROFILES['extended']['steps']}")

    # Test 6: read-only → short
    r = recommend_profile("investigation", is_read_only=True)
    check("readonly_short",
          r["profile"] == "short",
          f"got {r['profile']}")

    # Test 7: multi-WO → long
    r = recommend_profile("batch", is_multi_wo=True)
    check("multiwo_long",
          r["profile"] == "long",
          f"got {r['profile']}")

    # Test 8: external push → no auto-approve
    r = recommend_profile("external_push", risk_level="high",
                          is_external=True)
    check("external_no_auto",
          not r["auto_approve"],
          f"auto_approve={r['auto_approve']}")

    # Test 9: 429 → no auto switch
    r = check_model_switch("429 rate limit")
    check("429_no_auto",
          not r["auto_switch"] and r["action"] == "REPORT_TO_OPERATOR",
          f"action={r['action']}")

    # Test 10: 401 → BLOCK
    r = check_model_switch("401 unauthorized")
    check("401_block",
          r["action"] == "BLOCK",
          f"action={r['action']}")

    return {
        "passed": passed,
        "failed": failed,
        "total": passed + failed,
        "results": results,
    }


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "self-check":
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["failed"] == 0 else 1)

    if len(sys.argv) > 1 and sys.argv[1] == "profiles":
        for name, prof in PROFILES.items():
            print(f"  {name:10s} = {prof['steps']:4d}  {prof['description']}")
        sys.exit(0)

    if len(sys.argv) > 1 and sys.argv[1] == "recommend":
        # Example: python vibe_iteration_policy.py recommend --read-only
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--task-type", default="general")
        parser.add_argument("--risk", default="low")
        parser.add_argument("--multi-wo", action="store_true")
        parser.add_argument("--external", action="store_true")
        parser.add_argument("--has-tests", action="store_true")
        parser.add_argument("--read-only", action="store_true")
        parser.add_argument("--extended-reason", default="")
        args = parser.parse_args(sys.argv[2:])

        rec = recommend_profile(
            task_type=args.task_type,
            risk_level=args.risk,
            is_multi_wo=args.multi_wo,
            is_external=args.external,
            has_tests=args.has_tests,
            is_read_only=args.read_only,
        )
        print(json.dumps(rec, indent=2))
        sys.exit(0)

    # Default: show policy report
    report = generate_policy_report("standard", 300)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
