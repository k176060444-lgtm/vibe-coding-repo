#!/usr/bin/env python3
"""
apply_operator_approval_receipt.py — Validate & preview operator approval receipts.

DEFAULT MODE: dry-run only.  Reads a YAML receipt, validates every field,
checks each (node, model_id) against the current NMC, and prints the diff
that WOULD be applied.  Does NOT write NMC unless --apply is passed (which
requires separate operator authorization).

Usage:
    python scripts/apply_operator_approval_receipt.py \
        --receipt path/to/receipt.yaml

    python scripts/apply_operator_approval_receipt.py \
        --receipt path/to/receipt.yaml --self-check

    python scripts/apply_operator_approval_receipt.py --self-check
"""

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone

import yaml

NMC_PATH = "scripts/node_model_capability.yaml"

REQUIRED_STATES = [
    "declared",
    "synced",
    "wrapper_valid",
    "runtime_visible",
    "env_loaded",
    "model_call_verified",
]

RECEIPT_SCHEMA = {
    "receipt_id": str,
    "issued_by": str,
    "issued_at": str,
    "base_sha": str,
    "approved_entries": list,
    "non_scope": list,
}

WILDCARDS = ["全部", "所有", "所有节点", "全部节点", "全部模型", "所有模型", "*", "all"]

ENTRY_PATTERN = re.compile(r"^([\w][\w.-]*)/([\w][\w.-]*)$")

# ============================================================
# Helpers
# ============================================================

def load_nmc(path: str = NMC_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_entry(nmc: dict, node: str, model_id: str) -> dict | None:
    nd = nmc.get("nodes", {}).get(node)
    if not nd:
        return None
    for e in nd.get("matrix", []):
        if e.get("model_id") == model_id:
            return e
    return None


# ============================================================
# Receipt Validation
# ============================================================

class ReceiptError(Exception):
    """Fatal error — receipt cannot be applied as-is."""
    pass


class ReceiptWarning(Exception):
    """Non-fatal warning for a specific entry."""
    pass


def validate_receipt_schema(receipt: dict) -> None:
    errors = []
    for field, ftype in RECEIPT_SCHEMA.items():
        val = receipt.get(field)
        if val is None:
            errors.append(f"missing required field: {field!r}")
        elif not isinstance(val, ftype):
            errors.append(
                f"field {field!r}: expected {ftype.__name__}, "
                f"got {type(val).__name__}"
            )
    if errors:
        raise ReceiptError(" | ".join(errors))


def parse_entry_string(raw: str) -> tuple[str, str]:
    """Parse 'node/model_id' string into (node, model_id)."""
    raw = raw.strip()
    if not raw:
        raise ReceiptError(f"empty entry string")
    # Block wildcard/bulk keywords
    for wc in WILDCARDS:
        if wc in raw:
            raise ReceiptError(
                f"wildcard/bulk phrase not allowed in entry: '{raw}' "
                f"(contains '{wc}')"
            )
    m = ENTRY_PATTERN.match(raw)
    if not m:
        raise ReceiptError(
            f"invalid entry format: '{raw}' (expected node/model_id, "
            f"no wildcards)"
        )
    return m.group(1), m.group(2)


def validate_approved_entries(
    nmc: dict,
    entries: list[dict | str],
    label: str,
) -> list[tuple[str, str, dict]]:
    """
    Validate a list of (node, model_id) entries against NMC.

    Each entry can be a dict with 'node' and 'model_id' keys,
    or a string "node/model_id".

    Returns list of (node, model_id, entry_dict) for valid found entries.
    """
    resolved: list[tuple[str, str, dict]] = []
    errors: list[str] = []
    for i, raw in enumerate(entries):
        try:
            if isinstance(raw, dict):
                node = raw.get("node", "")
                model_id = raw.get("model_id", "")
                if not node or not model_id:
                    raise ReceiptError(
                        f"entry[{i}]: missing 'node' or 'model_id' key"
                    )
                # Also check wildcards in dict keys
                for wc in WILDCARDS:
                    if wc in node or wc in model_id:
                        raise ReceiptError(
                            f"wildcard in entry[{i}]: {node}/{model_id}"
                        )
            elif isinstance(raw, str):
                node, model_id = parse_entry_string(raw)
            else:
                raise ReceiptError(f"entry[{i}]: unexpected type {type(raw).__name__}")

            entry = find_entry(nmc, node, model_id)
            if entry is None:
                errors.append(f"{node}/{model_id}: entry not found in NMC matrix")
                continue
            resolved.append((node, model_id, entry))
        except ReceiptError as e:
            errors.append(str(e))
    if errors:
        raise ReceiptError(" | ".join(errors))
    return resolved


def check_single_entry_states(entry: dict) -> tuple[bool, list[str]]:
    missing = [s for s in REQUIRED_STATES if entry.get(s) is not True]
    return len(missing) == 0, missing


# ============================================================
# Dry-Run
# ============================================================

def dry_run(receipt: dict) -> dict:
    """
    Validate receipt and produce a diff summary.
    Returns dict with full result.
    """
    result = {
        "verdict": "DRY_RUN_PASS",
        "receipt_id": receipt.get("receipt_id", ""),
        "base_sha_ok": False,
        "entries_to_approve": [],
        "entries_to_reaffirm_unknown": [],
        "entries_already_true": [],
        "entries_not_found": [],
        "entries_ineligible": [],
        "errors": [],
        "warnings": [],
    }

    try:
        # 1. Schema
        validate_receipt_schema(receipt)

        # 2. Base SHA match
        current_sha = _git_head_sha()
        receipt_sha = receipt["base_sha"]
        if current_sha != receipt_sha:
            result["errors"].append(
                f"base_sha mismatch: receipt={receipt_sha}, "
                f"current HEAD={current_sha} (stale/forked receipt)"
            )
            result["verdict"] = "DRY_RUN_FAIL"
            return result
        result["base_sha_ok"] = True

        # 3. Load NMC
        nmc = load_nmc()

        # 4. Check no out-of-scope operator_approved=true entries exist
        oos_true = []
        for nn, nd in nmc.get("nodes", {}).items():
            for e in nd.get("matrix", []):
                if e.get("operator_approved") is True:
                    oos_true.append(f"{nn}/{e.get('model_id','?')}")
        if oos_true:
            # Collect approved_entries + non_scope sets
            approved_set = set()
            for ae in receipt.get("approved_entries", []):
                if isinstance(ae, dict):
                    approved_set.add(f"{ae.get('node','')}/{ae.get('model_id','')}")
                elif isinstance(ae, str):
                    approved_set.add(ae)
            ns_set = set()
            for ns in receipt.get("non_scope", []):
                if isinstance(ns, dict):
                    ns_set.add(f"{ns.get('node','')}/{ns.get('model_id','')}")
                elif isinstance(ns, str):
                    ns_set.add(ns)
            unexpected_true = [x for x in oos_true if x not in approved_set and x not in ns_set]
            if unexpected_true:
                result["errors"].append(
                    f"out-of-scope operator_approved=true entries: "
                    f"{unexpected_true}; must be explicitly listed in "
                    f"non_scope or approved_entries"
                )
                result["verdict"] = "DRY_RUN_FAIL"
                return result

        # 5. Validate approved_entries
        if not receipt.get("approved_entries"):
            result["errors"].append("approved_entries is empty")
            result["verdict"] = "DRY_RUN_FAIL"
            return result

        approved_resolved = validate_approved_entries(
            nmc, receipt["approved_entries"], "approved_entries"
        )
        for node, mid, entry in approved_resolved:
            # Check operator_approved is 'unknown'
            current_op = entry.get("operator_approved")
            if current_op is True:
                result["entries_already_true"].append(f"{node}/{mid}")
                continue
            if current_op != "unknown":
                result["errors"].append(
                    f"{node}/{mid}: operator_approved={current_op!r}; "
                    f"expected 'unknown' or True"
                )
                result["verdict"] = "DRY_RUN_FAIL"
                continue
            # Check 6-state eligibility
            eligible, missing = check_single_entry_states(entry)
            if not eligible:
                result["entries_ineligible"].append(
                    f"{node}/{mid}: blocked by state(s): {missing}"
                )
                result["verdict"] = "DRY_RUN_FAIL"
                continue
            result["entries_to_approve"].append({
                "node": node,
                "model_id": mid,
                "will_set": "operator_approved: unknown -> true",
                "evidence_note": f"all {len(REQUIRED_STATES)} REQUIRED_STATES true",
            })

        # 6. Validate non_scope (if present)
        if receipt.get("non_scope"):
            ns_resolved = validate_approved_entries(
                nmc, receipt["non_scope"], "non_scope"
            )
            for node, mid, entry in ns_resolved:
                current_op = entry.get("operator_approved")
                if current_op is True:
                    result["errors"].append(
                        f"{node}/{mid}: in non_scope but operator_approved=true; "
                        f"must be revoked via a separate revocation receipt"
                    )
                    result["verdict"] = "DRY_RUN_FAIL"
                    continue
                result["entries_to_reaffirm_unknown"].append({
                    "node": node,
                    "model_id": mid,
                    "current": current_op,
                    "will_stay": "unknown",
                })

        # 7. Final summary
        if result["verdict"] == "DRY_RUN_PASS":
            result["detail"] = (
                f"dry-run PASS: {len(result['entries_to_approve'])} to approve, "
                f"{len(result['entries_to_reaffirm_unknown'])} to re-affirm unknown"
            )
        else:
            result["detail"] = "dry-run FAIL — see errors above"

    except ReceiptError as e:
        result["errors"].append(str(e))
        result["verdict"] = "DRY_RUN_FAIL"
    except Exception as e:
        result["errors"].append(f"unexpected error: {e}")
        result["verdict"] = "DRY_RUN_FAIL"

    return result


def _git_head_sha() -> str:
    import subprocess
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=10,
    )
    return r.stdout.strip()


# ============================================================
# Self-Check
# ============================================================

def self_check():
    """Run built-in tests to verify tool logic."""
    results = []
    passed = 0
    total = 0

    def _ck(name, ok, detail=""):
        nonlocal total, passed
        total += 1
        if ok:
            passed += 1
        results.append({"name": name, "passed": ok, "detail": detail})

    # Parse entry string tests
    node, mid = parse_entry_string("21bao/opencode-go-mimo-v2-5")
    _ck("parse-valid", node == "21bao" and mid == "opencode-go-mimo-v2-5")

    try:
        parse_entry_string("*/*")
        _ck("parse-wildcard-rejected", False)
    except ReceiptError:
        _ck("parse-wildcard-rejected", True)

    # schema validation
    try:
        validate_receipt_schema({})
        _ck("schema-empty-fail", False)
    except ReceiptError:
        _ck("schema-empty-fail", True)

    # REQUIRED_STATES
    entry_ok = {s: True for s in REQUIRED_STATES}
    ok, missing = check_single_entry_states(entry_ok)
    _ck("eligible-6/6", ok and len(missing) == 0)

    entry_bad = {**entry_ok, "model_call_verified": "unknown"}
    ok2, missing2 = check_single_entry_states(entry_bad)
    _ck("ineligible-mcv", not ok2 and "model_call_verified" in missing2)

    print(json.dumps({
        "version": "0.1.0",
        "passed": passed == total,
        "total_tests": total,
        "passed_count": passed,
        "failed_count": total - passed,
        "results": results,
        "exit_code": 0 if passed == total else 1,
    }, indent=2))
    return passed == total


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Validate and preview operator approval receipts "
                    "(dry-run only; NMC NOT modified)"
    )
    parser.add_argument("--receipt", "-r", help="Path to receipt YAML")
    parser.add_argument("--self-check", action="store_true",
                        help="Run built-in self-check tests")
    parser.add_argument("--json", action="store_true",
                        help="Output JSON")
    args = parser.parse_args()

    if args.self_check:
        ok = self_check()
        sys.exit(0 if ok else 1)

    if args.receipt:
        with open(args.receipt, "r", encoding="utf-8") as f:
            receipt = yaml.safe_load(f)
        result = dry_run(receipt)
    else:
        # Minimal self-test
        result = {"verdict": "NO_INPUT", "detail": "pass --receipt or --self-check"}

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        v = result.get("verdict", "UNKNOWN")
        print(f"Verdict: {v}")
        if result.get("errors"):
            print("Errors:")
            for e in result["errors"]:
                print(f"  - {e}")
        if result.get("entries_to_approve"):
            print("Would approve:")
            for ae in result["entries_to_approve"]:
                print(f"  {ae['node']}/{ae['model_id']}")
        if result.get("entries_to_reaffirm_unknown"):
            print("Would re-affirm unknown:")
            for ns in result["entries_to_reaffirm_unknown"]:
                print(f"  {ns['node']}/{ns['model_id']}")
        if result.get("details"):
            print(f"Detail: {result['detail']}")

    sys.exit(0 if result.get("verdict", "").startswith("DRY_RUN_PASS") else 1)


if __name__ == "__main__":
    main()
