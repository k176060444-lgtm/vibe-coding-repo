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

def load_nmc(path: str | None = None) -> dict:
    p = NMC_PATH if path is None else path
    with open(p, "r", encoding="utf-8") as f:
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
        "base_sha_mode": None,
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

        # 2. Base SHA — ancestor check (not exact match)
        # A receipt pinned to an ancestor commit of HEAD is valid;
        # this accommodates PR merge workflows where HEAD advances
        # past the receipt's base_sha.
        current_sha = _git_head_sha()
        receipt_sha = receipt["base_sha"]
        if not _is_ancestor(receipt_sha, current_sha):
            result["errors"].append(
                f"base_sha mismatch: receipt={receipt_sha}, "
                f"current HEAD={current_sha} — receipt base_sha "
                f"is not an ancestor of current HEAD (stale/forked receipt)"
            )
            result["verdict"] = "DRY_RUN_FAIL"
            return result
        result["base_sha_ok"] = True
        result["base_sha_mode"] = "ancestor"

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
    import os
    # Derive repo root from this script's location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, ".."))
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=10,
        cwd=repo_root,
    )
    return r.stdout.strip()


def _is_ancestor(ancestor_candidate: str, descendant: str) -> bool:
    """Return True if ancestor_candidate is an ancestor of descendant (or equal).

    Uses `git merge-base --is-ancestor`.  On success (ancestor or equal)
    returns True.  On failure (not ancestor, invalid SHA, git error)
    returns False so the fail-closed gate stays engaged.
    """
    import subprocess
    import os
    if not re.match(r"^[0-9a-f]{40}$", ancestor_candidate):
        return False
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, ".."))
    r = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor_candidate, descendant],
        capture_output=True, text=True, timeout=10,
        cwd=repo_root,
    )
    # git merge-base --is-ancestor exits 0 if ancestor, 1 if not
    return r.returncode == 0


# ============================================================
# Apply Receipt (write path)
# ============================================================

def save_nmc(nmc: dict, path: str | None = None) -> None:
    """Write NMC to disk atomically with backup and verification.

    Pattern: serialize → backup → write → verify → cleanup backup.
    On ANY failure, rollback from backup.
    """
    p = NMC_PATH if path is None else path
    import os
    import shutil
    bak = p + ".bak"
    try:
        # 1. Serialize first
        serialized = yaml.dump(
            nmc,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )
        # 2. Backup existing if present
        if os.path.exists(p):
            shutil.copy2(p, bak)
        # 3. Write
        with open(p, "w", encoding="utf-8") as f:
            f.write(serialized)
        # 4. Verify: reload and compare
        with open(p, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        if loaded != nmc:
            raise RuntimeError(
                "NMC verification failed: written content differs from expected"
            )
        # 5. Cleanup backup on success
        if os.path.exists(bak):
            os.remove(bak)
    except Exception:
        # Rollback on any error: restore from backup
        if os.path.exists(bak):
            shutil.copy2(bak, p)
            os.remove(bak)
        raise


def apply_receipt(receipt: dict) -> dict:
    """Validate and apply a receipt to NMC.

    First runs full dry-run validation (same fail-closed gates as
    dry_run).  Only writes to NMC if dry_run passes.

    Returns a result dict with write outcome.  Never writes if
    validation fails.
    """
    # Step 1: Full dry-run validation (reuses all fail-closed gates)
    dr = dry_run(receipt)
    if dr["verdict"] != "DRY_RUN_PASS":
        return {
            "verdict": "APPLY_FAIL",
            "receipt_id": receipt.get("receipt_id", ""),
            "dry_run_verdict": dr["verdict"],
            "errors": dr.get("errors", []),
            "entries_ineligible": dr.get("entries_ineligible", []),
            "entries_approved": [],
            "entries_skipped_already_true": [],
            "entries_reaffirmed_unknown": [],
            "written": False,
        }

    # Step 2: Load NMC for modification
    nmc = load_nmc()

    # Step 3: Apply approved_entries to NMC in-memory
    entries_approved = []
    entries_skipped = []

    for ae_entry in receipt.get("approved_entries", []):
        if isinstance(ae_entry, dict):
            node = ae_entry.get("node", "")
            model_id = ae_entry.get("model_id", "")
        elif isinstance(ae_entry, str):
            parts = ae_entry.split("/", 1)
            if len(parts) != 2:
                continue
            node, model_id = parts
        else:
            continue

        nd = nmc.get("nodes", {}).get(node)
        if not nd:
            continue
        for e in nd.get("matrix", []):
            if e.get("model_id") == model_id:
                current = e.get("operator_approved")
                if current is True:
                    entries_skipped.append({
                        "node": node,
                        "model_id": model_id,
                        "reason": "already true",
                    })
                elif current == "unknown":
                    e["operator_approved"] = True
                    entries_approved.append({
                        "node": node,
                        "model_id": model_id,
                        "from": "unknown",
                        "to": True,
                    })
                break

    # Step 4: Re-affirm non_scope entries stay unknown (no-op in NMC)
    entries_reaffirmed = [
        {"node": ns["node"], "model_id": ns["model_id"], "stays": "unknown"}
        for ns in dr.get("entries_to_reaffirm_unknown", [])
    ]

    # Step 5: Write atomically
    try:
        save_nmc(nmc)
    except Exception as e:
        return {
            "verdict": "APPLY_FAIL",
            "receipt_id": receipt.get("receipt_id", ""),
            "dry_run_verdict": dr["verdict"],
            "entries_approved": [],
            "entries_skipped_already_true": [],
            "entries_reaffirmed_unknown": [],
            "errors": [f"NMC write failed: {e}"],
            "written": False,
        }

    return {
        "verdict": "APPLY_PASS",
        "receipt_id": receipt.get("receipt_id", ""),
        "dry_run_verdict": dr["verdict"],
        "entries_approved": entries_approved,
        "entries_skipped_already_true": entries_skipped,
        "entries_reaffirmed_unknown": entries_reaffirmed,
        "written": True,
        "errors": [],
    }


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
        description="Validate and apply operator approval receipts "
                    "(default: dry-run only; pass --apply to write)"
    )
    parser.add_argument("--receipt", "-r", help="Path to receipt YAML")
    parser.add_argument("--apply", action="store_true",
                        help="Apply receipt changes to NMC (destructive; "
                             "requires operator authorization)")
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
        if args.apply:
            result = apply_receipt(receipt)
        else:
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

    ok_prefixes = ("DRY_RUN_PASS", "APPLY_PASS")
    sys.exit(0 if result.get("verdict", "").startswith(ok_prefixes) else 1)


if __name__ == "__main__":
    main()
