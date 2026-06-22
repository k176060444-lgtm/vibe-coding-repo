#!/usr/bin/env python3
"""delegate_capability_gate.py — Planned/Actual Model Ledger + Capability Declaration v1.0.0

Enforces that:
  1. Execution paths declare their capabilities (per-task model override, etc.)
  2. Role assignments requiring capabilities the executor doesn't support are BLOCKED
  3. Planned vs actual model/node/provider are validated with structured verdicts
  4. Mismatches without operator approval are BLOCKED
  5. Same-model review requires explicit operator approval when capabilities limit it

Verdicts:
  PASS                                     — planned == actual, receipt verifiable
  BLOCKED                                  — planned != actual, no operator_approved_downgrade
  WARNING                                  — actual unknown (preflight/plan stage)
  SAME_MODEL_REVIEW_ALLOWED_WITH_OPERATOR_APPROVAL — operator approved same-model review
  BLOCKED_UNSUPPORTED_CAPABILITY           — role needs capability executor doesn't have

Usage:
    python scripts/delegate_capability_gate.py validate-entry --json ENTRY_JSON
    python scripts/delegate_capability_gate.py validate-ledger --json LEDGER_JSON
    python scripts/delegate_capability_gate.py declare-capability --json CAP_JSON
    python scripts/delegate_capability_gate.py --self-check [--json]

Exit codes:
    0 = gate passed
    1 = gate failed / blocked
    2 = usage error
"""

__version__ = "1.0.0"

import argparse
import json
import sys

# ── Verdict constants ─────────────────────────────────────────────────

VERDICT_PASS = "PASS"
VERDICT_BLOCKED = "BLOCKED"
VERDICT_WARNING = "WARNING"
VERDICT_SAME_MODEL_REVIEW = "SAME_MODEL_REVIEW_ALLOWED_WITH_OPERATOR_APPROVAL"
VERDICT_BLOCKED_UNSUPPORTED = "BLOCKED_UNSUPPORTED_CAPABILITY"

ALL_VERDICTS = {
    VERDICT_PASS,
    VERDICT_BLOCKED,
    VERDICT_WARNING,
    VERDICT_SAME_MODEL_REVIEW,
    VERDICT_BLOCKED_UNSUPPORTED,
}

# ── Capability keys ───────────────────────────────────────────────────

CAPABILITY_KEYS = [
    "per_task_model_override",
    "per_task_node_override",
    "actual_model_receipt",
    "actual_node_receipt",
    "token_usage_receipt",
]

# ── Ledger entry required fields ──────────────────────────────────────

LEDGER_ENTRY_REQUIRED_FIELDS = [
    "role",
    "planned_provider",
    "planned_model",
    "planned_node",
    "actual_provider",
    "actual_model",
    "actual_node",
    "actual_source",
    "receipt_confidence",
    "mismatch_reason",
    "operator_approved_downgrade",
]

VALID_RECEIPT_CONFIDENCE = {"verified", "claimed", "unknown", "none"}
VALID_ACTUAL_SOURCES = {
    "opencode_exit_log",
    "model_routing_fixture",
    "gh_pr_metadata",
    "operator_declaration",
    "parent_session_inheritance",
    "unknown",
    "none",
}

# ── Capability declaration ────────────────────────────────────────────


def create_capability_declaration(
    executor_name: str,
    per_task_model_override: bool = False,
    per_task_node_override: bool = False,
    actual_model_receipt: bool = False,
    actual_node_receipt: bool = False,
    token_usage_receipt: bool = False,
    notes: str = "",
) -> dict:
    """Create a capability declaration for an executor.

    Args:
        executor_name: Name of the executor (e.g. "delegate_task", "local-job").
        per_task_model_override: Can the executor accept per-task model?
        per_task_node_override: Can the executor accept per-task node?
        actual_model_receipt: Can the executor return actual model used?
        actual_node_receipt: Can the executor return actual node used?
        token_usage_receipt: Can the executor return token usage?
        notes: Free-form notes about limitations.

    Returns:
        Capability declaration dict.
    """
    return {
        "executor_name": executor_name,
        "version": __version__,
        "capabilities": {
            "per_task_model_override": per_task_model_override,
            "per_task_node_override": per_task_node_override,
            "actual_model_receipt": actual_model_receipt,
            "actual_node_receipt": actual_node_receipt,
            "token_usage_receipt": token_usage_receipt,
        },
        "notes": notes,
    }


# Known executor capabilities (hardcoded defaults)
KNOWN_EXECUTOR_CAPABILITIES = {
    "delegate_task": create_capability_declaration(
        executor_name="delegate_task",
        per_task_model_override=False,
        per_task_node_override=False,
        actual_model_receipt=False,
        actual_node_receipt=False,
        token_usage_receipt=False,
        notes="delegate_task inherits parent model. No per-task override. "
              "No structured receipt for actual model/node/token usage.",
    ),
    "local-job": create_capability_declaration(
        executor_name="local-job",
        per_task_model_override=True,
        per_task_node_override=True,
        actual_model_receipt=True,
        actual_node_receipt=True,
        token_usage_receipt=True,
        notes="local-job.ps1 supports explicit model param and records "
              "actual model from opencode exit logs.",
    ),
}


def get_executor_capability(executor_name: str) -> dict:
    """Get capability declaration for a known executor.

    Returns declaration dict, or a fully-false declaration if unknown.
    """
    if executor_name in KNOWN_EXECUTOR_CAPABILITIES:
        return KNOWN_EXECUTOR_CAPABILITIES[executor_name]
    return create_capability_declaration(
        executor_name=executor_name,
        notes=f"Unknown executor '{executor_name}' — all capabilities assumed false.",
    )


# ── Validation ────────────────────────────────────────────────────────


def validate_capability_declaration(decl: dict) -> list:
    """Validate a capability declaration dict. Returns list of errors."""
    errors = []
    if not decl.get("executor_name"):
        errors.append("capability: missing executor_name")
    caps = decl.get("capabilities", {})
    for key in CAPABILITY_KEYS:
        if key not in caps:
            errors.append(f"capability: missing capability key '{key}'")
        elif not isinstance(caps[key], bool):
            errors.append(
                f"capability: '{key}' must be bool, got {type(caps[key]).__name__}"
            )
    return errors


def validate_ledger_entry(entry: dict, index: int) -> list:
    """Validate a single planned/actual ledger entry. Returns list of errors."""
    errors = []
    for field in LEDGER_ENTRY_REQUIRED_FIELDS:
        if field not in entry:
            errors.append(f"entry[{index}]: missing required field '{field}'")

    # Validate receipt_confidence
    rc = entry.get("receipt_confidence", "")
    if rc and rc not in VALID_RECEIPT_CONFIDENCE:
        errors.append(
            f"entry[{index}]: invalid receipt_confidence '{rc}' "
            f"(valid: {sorted(VALID_RECEIPT_CONFIDENCE)})"
        )

    # Validate actual_source
    src = entry.get("actual_source", "")
    if src and src not in VALID_ACTUAL_SOURCES:
        errors.append(
            f"entry[{index}]: invalid actual_source '{src}' "
            f"(valid: {sorted(VALID_ACTUAL_SOURCES)})"
        )

    return errors


# ── Verdict engine ────────────────────────────────────────────────────


def compute_entry_verdict(
    entry: dict,
    executor_capability: dict = None,
) -> dict:
    """Compute verdict for a single planned/actual ledger entry.

    Args:
        entry: Ledger entry with planned/actual fields.
        executor_capability: Capability declaration dict (optional).

    Returns:
        {
            "role": str,
            "verdict": str,
            "model_match": bool,
            "node_match": bool,
            "provider_match": bool,
            "detail": str,
        }
    """
    role = entry.get("role", "unknown")
    planned_model = entry.get("planned_model", "N/A")
    actual_model = entry.get("actual_model", "N/A")
    planned_node = entry.get("planned_node", "N/A")
    actual_node = entry.get("actual_node", "N/A")
    planned_provider = entry.get("planned_provider", "N/A")
    actual_provider = entry.get("actual_provider", "N/A")
    actual_source = entry.get("actual_source", "none")
    receipt_confidence = entry.get("receipt_confidence", "none")
    mismatch_reason = entry.get("mismatch_reason", "")
    operator_approved = entry.get("operator_approved_downgrade", False)

    model_match = planned_model == actual_model
    node_match = planned_node == actual_node
    provider_match = planned_provider == actual_provider
    all_match = model_match and node_match and provider_match

    # Operator approval checks MUST come before capability checks
    # because operator can override capability limitations.
    if not all_match and operator_approved:
        # Same-model review: operator explicitly approved despite mismatch
        if "same-model review" in mismatch_reason.lower():
            return {
                "role": role,
                "verdict": VERDICT_SAME_MODEL_REVIEW,
                "model_match": model_match,
                "node_match": node_match,
                "provider_match": provider_match,
                "detail": (
                    f"Operator approved: {mismatch_reason}. "
                    f"Model: {planned_model}→{actual_model}. "
                    f"Node: {planned_node}→{actual_node}."
                ),
            }
        # Generic operator-approved downgrade
        mismatch_parts = []
        if not model_match:
            mismatch_parts.append(f"model: {planned_model}→{actual_model}")
        if not node_match:
            mismatch_parts.append(f"node: {planned_node}→{actual_node}")
        if not provider_match:
            mismatch_parts.append(f"provider: {planned_provider}→{actual_provider}")
        return {
            "role": role,
            "verdict": VERDICT_PASS,
            "model_match": model_match,
            "node_match": node_match,
            "provider_match": provider_match,
            "detail": (
                f"Operator approved downgrade. "
                f"{'; '.join(mismatch_parts)}."
            ),
        }

    # Check capability requirements (only when no operator approval)
    if executor_capability:
        caps = executor_capability.get("capabilities", {})
        needs_model_override = not model_match and planned_model != "N/A"
        if needs_model_override and not caps.get("per_task_model_override"):
            return {
                "role": role,
                "verdict": VERDICT_BLOCKED_UNSUPPORTED,
                "model_match": model_match,
                "node_match": node_match,
                "provider_match": provider_match,
                "detail": (
                    f"Role '{role}' requires per_task_model_override "
                    f"(planned={planned_model}, actual={actual_model}) "
                    f"but executor '{executor_capability.get('executor_name', '?')}' "
                    f"does not support it."
                ),
            }

    # PASS: all match with verifiable receipt
    if all_match:
        if receipt_confidence in ("verified", "claimed"):
            return {
                "role": role,
                "verdict": VERDICT_PASS,
                "model_match": True,
                "node_match": True,
                "provider_match": True,
                "detail": f"All fields match. Receipt: {receipt_confidence}.",
            }
        elif receipt_confidence == "unknown":
            return {
                "role": role,
                "verdict": VERDICT_WARNING,
                "model_match": True,
                "node_match": True,
                "provider_match": True,
                "detail": "Fields appear to match but receipt confidence is unknown.",
            }

    # WARNING: actual unknown (preflight)
    if actual_model in ("N/A", "unknown", "") and actual_source in ("none", "unknown"):
        return {
            "role": role,
            "verdict": VERDICT_WARNING,
            "model_match": model_match,
            "node_match": node_match,
            "provider_match": provider_match,
            "detail": (
                f"Actual model/node not yet known (preflight). "
                f"Planned: {planned_model}/{planned_node}."
            ),
        }

    # Mismatch without operator approval → BLOCKED
    if not all_match:
        mismatch_parts = []
        if not model_match:
            mismatch_parts.append(f"model: {planned_model}→{actual_model}")
        if not node_match:
            mismatch_parts.append(f"node: {planned_node}→{actual_node}")
        if not provider_match:
            mismatch_parts.append(f"provider: {planned_provider}→{actual_provider}")

        return {
            "role": role,
            "verdict": VERDICT_BLOCKED,
            "model_match": model_match,
            "node_match": node_match,
            "provider_match": provider_match,
            "detail": (
                f"Planned/actual mismatch without operator approval: "
                f"{'; '.join(mismatch_parts)}."
            ),
        }

    # Fallback
    return {
        "role": role,
        "verdict": VERDICT_WARNING,
        "model_match": model_match,
        "node_match": node_match,
        "provider_match": provider_match,
        "detail": "Could not determine verdict.",
    }


# ── Ledger validation ─────────────────────────────────────────────────


def validate_ledger(
    entries: list,
    executor_name: str = None,
) -> dict:
    """Validate a complete planned/actual ledger.

    Args:
        entries: List of ledger entries.
        executor_name: Executor name for capability lookup (optional).

    Returns:
        {
            "valid": bool,
            "overall_verdict": str,
            "entry_verdicts": [{role, verdict, detail, ...}],
            "errors": [str],
            "checks_passed": int,
            "checks_total": int,
        }
    """
    errors = []
    entry_verdicts = []
    checks_total = 0
    checks_passed = 0

    # Validate each entry structure
    for i, entry in enumerate(entries):
        entry_errors = validate_ledger_entry(entry, i)
        errors.extend(entry_errors)

    if errors:
        return {
            "valid": False,
            "overall_verdict": VERDICT_BLOCKED,
            "entry_verdicts": [],
            "errors": errors,
            "checks_passed": 0,
            "checks_total": len(entries),
        }

    # Get executor capability
    cap = None
    if executor_name:
        cap = get_executor_capability(executor_name)

    # Compute verdicts
    for entry in entries:
        verdict = compute_entry_verdict(entry, cap)
        entry_verdicts.append(verdict)
        checks_total += 1
        if verdict["verdict"] == VERDICT_PASS:
            checks_passed += 1

    # Overall verdict: worst case
    verdict_priority = {
        VERDICT_BLOCKED_UNSUPPORTED: 0,
        VERDICT_BLOCKED: 1,
        VERDICT_WARNING: 2,
        VERDICT_SAME_MODEL_REVIEW: 3,
        VERDICT_PASS: 4,
    }
    worst = min(
        entry_verdicts,
        key=lambda v: verdict_priority.get(v["verdict"], 99),
    )
    overall = worst["verdict"]

    # If all PASS, overall is PASS
    if all(v["verdict"] == VERDICT_PASS for v in entry_verdicts):
        overall = VERDICT_PASS

    return {
        "valid": len(errors) == 0,
        "overall_verdict": overall,
        "entry_verdicts": entry_verdicts,
        "errors": errors,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "executor_capability": cap,
    }


# ── Self-check ────────────────────────────────────────────────────────


def self_check() -> dict:
    """Run self-check with synthetic scenarios. No network calls."""
    checks = []
    passed = 0
    total = 0

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal passed, total
        total += 1
        if ok:
            passed += 1
        checks.append({"name": name, "passed": ok, "detail": detail})

    # dcg-01: version
    check("dcg-01-version", bool(__version__), __version__)

    # dcg-02: PASS — planned == actual, verified receipt
    entry_pass = {
        "role": "implementer",
        "planned_provider": "minimax-plan",
        "planned_model": "minimax-plan/MiniMax-M3",
        "planned_node": "windows",
        "actual_provider": "minimax-plan",
        "actual_model": "minimax-plan/MiniMax-M3",
        "actual_node": "windows",
        "actual_source": "opencode_exit_log",
        "receipt_confidence": "verified",
        "mismatch_reason": "",
        "operator_approved_downgrade": False,
    }
    v_pass = compute_entry_verdict(entry_pass)
    check("dcg-02-pass-verdict", v_pass["verdict"] == VERDICT_PASS,
          f"got={v_pass['verdict']}")
    check("dcg-02-pass-detail", "match" in v_pass["detail"].lower(),
          v_pass["detail"])

    # dcg-03: BLOCKED — model mismatch, no approval
    entry_block = {
        "role": "reviewer",
        "planned_provider": "deepseek-plan",
        "planned_model": "deepseek-plan/deepseek-v4-pro",
        "planned_node": "9bao",
        "actual_provider": "xiaomi-plan",
        "actual_model": "xiaomi-plan/mimo-v2.5-pro",
        "actual_node": "windows",
        "actual_source": "parent_session_inheritance",
        "receipt_confidence": "claimed",
        "mismatch_reason": "",
        "operator_approved_downgrade": False,
    }
    v_block = compute_entry_verdict(entry_block)
    check("dcg-03-blocked-verdict", v_block["verdict"] == VERDICT_BLOCKED,
          f"got={v_block['verdict']}")
    check("dcg-03-blocked-detail", "mismatch" in v_block["detail"].lower(),
          v_block["detail"])

    # dcg-04: BLOCKED — node mismatch, no approval
    entry_node_block = {
        "role": "reviewer",
        "planned_provider": "deepseek-plan",
        "planned_model": "deepseek-plan/deepseek-v4-pro",
        "planned_node": "9bao",
        "actual_provider": "deepseek-plan",
        "actual_model": "deepseek-plan/deepseek-v4-pro",
        "actual_node": "windows",
        "actual_source": "opencode_exit_log",
        "receipt_confidence": "verified",
        "mismatch_reason": "",
        "operator_approved_downgrade": False,
    }
    v_node = compute_entry_verdict(entry_node_block)
    check("dcg-04-node-mismatch-blocked", v_node["verdict"] == VERDICT_BLOCKED,
          f"got={v_node['verdict']}")

    # dcg-05: WARNING — actual unknown (preflight)
    entry_warn = {
        "role": "tester",
        "planned_provider": "deepseek-plan",
        "planned_model": "deepseek-plan/deepseek-v4-flash",
        "planned_node": "windows",
        "actual_provider": "",
        "actual_model": "",
        "actual_node": "",
        "actual_source": "none",
        "receipt_confidence": "none",
        "mismatch_reason": "",
        "operator_approved_downgrade": False,
    }
    v_warn = compute_entry_verdict(entry_warn)
    check("dcg-05-warning-preflight", v_warn["verdict"] == VERDICT_WARNING,
          f"got={v_warn['verdict']}")

    # dcg-06: BLOCKED_UNSUPPORTED_CAPABILITY — delegate_task can't override model
    entry_cap = {
        "role": "reviewer",
        "planned_provider": "deepseek-plan",
        "planned_model": "deepseek-plan/deepseek-v4-pro",
        "planned_node": "9bao",
        "actual_provider": "xiaomi-plan",
        "actual_model": "xiaomi-plan/mimo-v2.5-pro",
        "actual_node": "windows",
        "actual_source": "parent_session_inheritance",
        "receipt_confidence": "claimed",
        "mismatch_reason": "delegate_task cannot override per-task model",
        "operator_approved_downgrade": False,
    }
    delegate_cap = get_executor_capability("delegate_task")
    v_cap = compute_entry_verdict(entry_cap, delegate_cap)
    check("dcg-06-unsupported-capability",
          v_cap["verdict"] == VERDICT_BLOCKED_UNSUPPORTED,
          f"got={v_cap['verdict']}")

    # dcg-07: SAME_MODEL_REVIEW_ALLOWED_WITH_OPERATOR_APPROVAL
    entry_approved = {
        "role": "reviewer",
        "planned_provider": "deepseek-plan",
        "planned_model": "deepseek-plan/deepseek-v4-pro",
        "planned_node": "9bao",
        "actual_provider": "xiaomi-plan",
        "actual_model": "xiaomi-plan/mimo-v2.5-pro",
        "actual_node": "windows",
        "actual_source": "parent_session_inheritance",
        "receipt_confidence": "claimed",
        "mismatch_reason": "delegate_task cannot override per-task model; "
                           "operator approved same-model review",
        "operator_approved_downgrade": True,
    }
    v_approved = compute_entry_verdict(entry_approved, delegate_cap)
    check("dcg-07-same-model-approved",
          v_approved["verdict"] == VERDICT_SAME_MODEL_REVIEW,
          f"got={v_approved['verdict']}")

    # dcg-08: PASS with operator_approved_downgrade
    entry_downgrade = {
        "role": "implementer",
        "planned_provider": "minimax-plan",
        "planned_model": "minimax-plan/MiniMax-M3",
        "planned_node": "windows",
        "actual_provider": "deepseek-plan",
        "actual_model": "deepseek-plan/deepseek-v4-pro",
        "actual_node": "windows",
        "actual_source": "opencode_exit_log",
        "receipt_confidence": "verified",
        "mismatch_reason": "MiniMax-M3 unavailable",
        "operator_approved_downgrade": True,
    }
    v_downgrade = compute_entry_verdict(entry_downgrade)
    check("dcg-08-approved-downgrade-pass",
          v_downgrade["verdict"] == VERDICT_PASS,
          f"got={v_downgrade['verdict']}")

    # dcg-09: BLOCKED — claimed receipt but no source
    entry_no_source = {
        "role": "implementer",
        "planned_provider": "minimax-plan",
        "planned_model": "minimax-plan/MiniMax-M3",
        "planned_node": "windows",
        "actual_provider": "minimax-plan",
        "actual_model": "minimax-plan/MiniMax-M3",
        "actual_node": "windows",
        "actual_source": "none",
        "receipt_confidence": "none",
        "mismatch_reason": "",
        "operator_approved_downgrade": False,
    }
    v_no_src = compute_entry_verdict(entry_no_source)
    check("dcg-09-no-source-warning",
          v_no_src["verdict"] in (VERDICT_WARNING, VERDICT_BLOCKED),
          f"got={v_no_src['verdict']}")

    # dcg-10: Ledger validation — mixed entries
    result_mixed = validate_ledger(
        [entry_pass, entry_block],
        executor_name=None,
    )
    check("dcg-10-mixed-ledger-blocked",
          result_mixed["overall_verdict"] == VERDICT_BLOCKED,
          f"got={result_mixed['overall_verdict']}")
    check("dcg-10-mixed-checks",
          result_mixed["checks_passed"] == 1 and result_mixed["checks_total"] == 2,
          f"{result_mixed['checks_passed']}/{result_mixed['checks_total']}")

    # dcg-11: Ledger validation — all pass
    result_all_pass = validate_ledger([entry_pass])
    check("dcg-11-all-pass-ledger",
          result_all_pass["overall_verdict"] == VERDICT_PASS,
          f"got={result_all_pass['overall_verdict']}")

    # dcg-12: Ledger with executor capability
    result_with_cap = validate_ledger(
        [entry_cap],
        executor_name="delegate_task",
    )
    check("dcg-12-capability-blocked",
          result_with_cap["overall_verdict"] == VERDICT_BLOCKED_UNSUPPORTED,
          f"got={result_with_cap['overall_verdict']}")

    # dcg-13: Known executor capabilities
    check("dcg-13-delegate-no-override",
          not delegate_cap["capabilities"]["per_task_model_override"])
    lj_cap = get_executor_capability("local-job")
    check("dcg-13-local-job-has-override",
          lj_cap["capabilities"]["per_task_model_override"])

    # dcg-14: Unknown executor → all false
    unknown_cap = get_executor_capability("unknown-executor")
    check("dcg-14-unknown-executor-false",
          not any(unknown_cap["capabilities"].values()))

    # dcg-15: validate_capability_declaration
    decl = create_capability_declaration("test-executor")
    decl_errors = validate_capability_declaration(decl)
    check("dcg-15-valid-decl", len(decl_errors) == 0, str(decl_errors))

    # dcg-16: validate_capability_declaration — missing key
    bad_decl = {"executor_name": "bad", "capabilities": {}}
    bad_errors = validate_capability_declaration(bad_decl)
    check("dcg-16-bad-decl-errors", len(bad_errors) > 0,
          f"{len(bad_errors)} errors")

    # dcg-17: validate_ledger_entry — valid
    entry_errors = validate_ledger_entry(entry_pass, 0)
    check("dcg-17-valid-entry", len(entry_errors) == 0, str(entry_errors))

    # dcg-18: validate_ledger_entry — missing field
    bad_entry = {"role": "test"}
    bad_entry_errors = validate_ledger_entry(bad_entry, 0)
    check("dcg-18-missing-fields", len(bad_entry_errors) > 0,
          f"{len(bad_entry_errors)} errors")

    # dcg-19: ALL_VERDICTS has 5 entries
    check("dcg-19-verdicts-count", len(ALL_VERDICTS) == 5,
          f"count={len(ALL_VERDICTS)}")

    return {
        "version": __version__,
        "passed": passed == total,
        "total_tests": total,
        "passed_count": passed,
        "failed_count": total - passed,
        "checks": checks,
        "exit_code": 0 if passed == total else 1,
    }


# ── CLI ───────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Planned/Actual Model Ledger + Capability Declaration Gate")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    sub = parser.add_subparsers(dest="command")

    # validate-entry
    ve = sub.add_parser("validate-entry", help="Validate a single ledger entry")
    ve.add_argument("--entry", required=True, help="JSON string of ledger entry")

    # validate-ledger
    vl = sub.add_parser("validate-ledger", help="Validate full ledger")
    vl.add_argument("--entries", required=True, help="JSON string of entries list")
    vl.add_argument("--executor", help="Executor name for capability lookup")

    # declare-capability
    dc = sub.add_parser("declare-capability", help="Create capability declaration")
    dc.add_argument("--executor", required=True, help="Executor name")
    dc.add_argument("--model-override", action="store_true",
                    help="Supports per-task model override")
    dc.add_argument("--node-override", action="store_true",
                    help="Supports per-task node override")
    dc.add_argument("--model-receipt", action="store_true",
                    help="Returns actual model receipt")
    dc.add_argument("--node-receipt", action="store_true",
                    help="Returns actual node receipt")
    dc.add_argument("--token-receipt", action="store_true",
                    help="Returns token usage receipt")
    dc.add_argument("--notes", default="", help="Notes about limitations")

    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"=== DELEGATE CAPABILITY GATE SELF-CHECK (v{__version__}) ===")
            print(f"  Total: {result['total_tests']}")
            print(f"  Passed: {result['passed_count']}")
            print(f"  Failed: {result['failed_count']}")
            for c in result["checks"]:
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  {icon}  {c['name']}: {c['detail']}")
            print(f"\n  Self-check: {'PASSED' if result['passed'] else 'FAILED'}")
        sys.exit(result["exit_code"])

    if args.command == "validate-entry":
        entry = json.loads(args.entry)
        errors = validate_ledger_entry(entry, 0)
        if errors:
            verdict = {"valid": False, "errors": errors}
        else:
            v = compute_entry_verdict(entry)
            verdict = {"valid": True, "verdict": v}
        if args.json:
            print(json.dumps(verdict, indent=2, ensure_ascii=False))
        else:
            if verdict["valid"]:
                print(f"Entry verdict: {v['verdict']}")
                print(f"  {v['detail']}")
            else:
                print(f"Entry INVALID:")
                for e in errors:
                    print(f"  - {e}")
        sys.exit(0 if verdict["valid"] else 1)

    if args.command == "validate-ledger":
        entries = json.loads(args.entries)
        result = validate_ledger(entries, executor_name=args.executor)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Ledger verdict: {result['overall_verdict']}")
            print(f"  Checks: {result['checks_passed']}/{result['checks_total']}")
            for ev in result["entry_verdicts"]:
                print(f"  {ev['verdict']}  {ev['role']}: {ev['detail']}")
            if result["errors"]:
                print(f"  Errors:")
                for e in result["errors"]:
                    print(f"    - {e}")
        sys.exit(0 if result["overall_verdict"] == VERDICT_PASS else 1)

    if args.command == "declare-capability":
        decl = create_capability_declaration(
            executor_name=args.executor,
            per_task_model_override=args.model_override,
            per_task_node_override=args.node_override,
            actual_model_receipt=args.model_receipt,
            actual_node_receipt=args.node_receipt,
            token_usage_receipt=args.token_receipt,
            notes=args.notes,
        )
        errors = validate_capability_declaration(decl)
        if args.json:
            print(json.dumps({"declaration": decl, "errors": errors}, indent=2))
        else:
            print(f"Executor: {decl['executor_name']}")
            for k, v in decl["capabilities"].items():
                print(f"  {k}: {v}")
            if decl["notes"]:
                print(f"  Notes: {decl['notes']}")
            if errors:
                print(f"  Errors: {errors}")
            else:
                print(f"  Validation: PASS")
        sys.exit(0 if not errors else 1)

    parser.print_help()
    sys.exit(2)


if __name__ == "__main__":
    main()
