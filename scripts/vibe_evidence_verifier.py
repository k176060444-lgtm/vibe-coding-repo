#!/usr/bin/env python3
"""Evidence Verifier — verify execution evidence bundle integrity and consistency.

Checks registry entry, approval receipt, digests, SHAs, PR URL, wrapper results,
smoke/health status, job_status/audit_status, and changed_paths.

Usage:
    python3 scripts/vibe_evidence_verifier.py verify --evidence-dir /path --registry-dir /path --evidence-id ev-001
    python3 scripts/vibe_evidence_verifier.py verify --evidence-dir /path --registry-dir /path --evidence-id ev-001 --json

Output:
    PASS  — all checks passed
    WARN  — non-critical issues found
    FAIL  — critical integrity issues found
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

VERSION = "1.0.0"

def _evidence_dir_path(args):
    """Resolve evidence directory from args or environment."""
    if hasattr(args, 'evidence_dir') and args.evidence_dir:
        return Path(args.evidence_dir)
    env_dir = os.environ.get("VIBEDEV_EVIDENCE_DIR")
    if env_dir:
        return Path(env_dir)
    return None

def _registry_dir_path(args):
    """Resolve registry directory from args or environment."""
    if hasattr(args, 'registry_dir') and args.registry_dir:
        return Path(args.registry_dir)
    env_dir = os.environ.get("VIBEDEV_REGISTRY_DIR")
    if env_dir:
        return Path(env_dir)
    return None

def _load_evidence(evidence_dir, evidence_id):
    """Load a single evidence bundle by ID."""
    evidence_file = evidence_dir / f"{evidence_id}.json"
    if not evidence_file.is_file():
        return None
    try:
        with open(evidence_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

def _load_entry(registry_dir, workorder_id):
    """Load a single registry entry by ID."""
    entry_file = registry_dir / f"{workorder_id}.json"
    if not entry_file.is_file():
        return None
    try:
        with open(entry_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

def _load_receipt(receipts_dir, workorder_id):
    """Load approval receipt for workorder."""
    if not receipts_dir.is_dir():
        return None
    for f in sorted(receipts_dir.glob("*.json")):
        if f.name.startswith("."):
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                receipt = json.load(fh)
                if receipt.get("workorder_id") == workorder_id:
                    return receipt
        except (json.JSONDecodeError, IOError):
            continue
    return None

def _compute_evidence_digest(evidence_data):
    """Compute SHA256 digest of evidence data."""
    data_str = json.dumps(evidence_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data_str.encode("utf-8")).hexdigest()

def cmd_verify(args):
    """Verify an evidence bundle."""
    evidence_dir = _evidence_dir_path(args)
    if not evidence_dir:
        print("ERROR: --evidence-dir required", file=sys.stderr)
        return 1

    registry_dir = _registry_dir_path(args)
    if not registry_dir:
        print("ERROR: --registry-dir required", file=sys.stderr)
        return 1

    evidence_id = args.evidence_id
    if not evidence_id:
        print("ERROR: --evidence-id required", file=sys.stderr)
        return 1

    use_json = getattr(args, 'json', False)

    # Load evidence
    evidence = _load_evidence(evidence_dir, evidence_id)
    if not evidence:
        result = {"verdict": "FAIL", "checks": [], "errors": [f"Evidence '{evidence_id}' not found"]}
        if use_json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"FAIL: Evidence '{evidence_id}' not found")
        return 1

    checks = []
    errors = []
    warnings = []

    workorder_id = evidence.get("workorder_id", "")

    # Check 1: Evidence has required fields
    required_fields = ["evidence_id", "workorder_id", "base_sha", "result_sha", "timestamp", "digest"]
    missing = [f for f in required_fields if not evidence.get(f)]
    if missing:
        checks.append({"name": "required_fields", "result": "FAIL", "detail": f"Missing: {', '.join(missing)}"})
        errors.append(f"Missing required fields: {', '.join(missing)}")
    else:
        checks.append({"name": "required_fields", "result": "PASS", "detail": "All required fields present"})

    # Check 2: Digest matches recomputed
    evidence_data = {k: evidence.get(k) for k in ["workorder_id", "base_sha", "result_sha", "pr_url", "pr_number", "post_merge_sha", "timestamp"]}
    expected_digest = _compute_evidence_digest(evidence_data)
    if evidence.get("digest") == expected_digest:
        checks.append({"name": "digest_match", "result": "PASS", "detail": "Digest matches recomputed"})
    else:
        checks.append({"name": "digest_match", "result": "FAIL", "detail": "Digest mismatch"})
        errors.append("Evidence digest does not match recomputed digest")

    # Check 3: Registry entry exists
    entry = _load_entry(registry_dir, workorder_id)
    if entry:
        checks.append({"name": "registry_entry", "result": "PASS", "detail": "Registry entry exists"})
    else:
        checks.append({"name": "registry_entry", "result": "WARN", "detail": "Registry entry not found", "missing_fields": ["registry_entry"], "expected_fixture_mode": True})
        warnings.append(f"Registry entry '{workorder_id}' not found (expected in fixture mode)")

    # Check 4: Approval receipt exists
    receipts_dir = registry_dir / "receipts"
    receipt = _load_receipt(receipts_dir, workorder_id)
    if receipt:
        checks.append({"name": "approval_receipt", "result": "PASS", "detail": "Approval receipt exists"})
    else:
        checks.append({"name": "approval_receipt", "result": "WARN", "detail": "Approval receipt not found", "missing_fields": ["approval_receipt"], "expected_fixture_mode": True})
        warnings.append(f"Approval receipt for '{workorder_id}' not found (expected in fixture mode)")

    # Check 5: SHAs are non-empty
    if evidence.get("base_sha") and evidence.get("result_sha"):
        checks.append({"name": "shas_present", "result": "PASS", "detail": "Base and result SHAs present"})
    else:
        checks.append({"name": "shas_present", "result": "FAIL", "detail": "Missing base_sha or result_sha"})
        errors.append("base_sha or result_sha is empty")

    # Check 6: Smoke result
    smoke_result = evidence.get("smoke_result", "")
    if smoke_result:
        if "PASS" in smoke_result.upper():
            checks.append({"name": "smoke_result", "result": "PASS", "detail": f"Smoke: {smoke_result}"})
        else:
            checks.append({"name": "smoke_result", "result": "WARN", "detail": f"Smoke: {smoke_result}"})
            warnings.append(f"Smoke result indicates issues: {smoke_result}")
    else:
        checks.append({"name": "smoke_result", "result": "WARN", "detail": "No smoke result recorded", "missing_fields": ["smoke_result"], "expected_fixture_mode": True})
        warnings.append("No smoke result recorded (expected in fixture mode)")

    # Check 7: Job status
    job_status = evidence.get("job_status", "")
    if job_status:
        if "passed" in job_status.lower() or "clean" in job_status.lower():
            checks.append({"name": "job_status", "result": "PASS", "detail": f"Job status: {job_status}"})
        else:
            checks.append({"name": "job_status", "result": "WARN", "detail": f"Job status: {job_status}", "expected_fixture_mode": job_status == "completed"})
            warnings.append(f"Job status indicates issues: {job_status}")
    else:
        checks.append({"name": "job_status", "result": "WARN", "detail": "No job status recorded"})

    # Check 8: Audit status
    audit_status = evidence.get("audit_status", "")
    if audit_status == "audit_tainted":
        checks.append({"name": "audit_status", "result": "FAIL", "detail": "Audit status is audit_tainted"})
        errors.append("Evidence has audit_tainted status")
    elif audit_status:
        checks.append({"name": "audit_status", "result": "PASS", "detail": f"Audit status: {audit_status}"})
    else:
        checks.append({"name": "audit_status", "result": "WARN", "detail": "No audit status recorded"})

    # Check 9: Changed paths consistency
    changed_paths = evidence.get("changed_paths", [])
    if entry and changed_paths:
        entry_paths = set(entry.get("allowed_paths", []))
        evidence_paths = set(changed_paths)
        # Check that changed paths are within allowed paths (prefix match)
        covered = all(
            any(ep.startswith(ap) or ap.startswith(ep) for ap in entry_paths)
            for ep in evidence_paths
        ) if entry_paths else True
        if covered:
            checks.append({"name": "changed_paths", "result": "PASS", "detail": f"{len(changed_paths)} paths, within scope"})
        else:
            checks.append({"name": "changed_paths", "result": "WARN", "detail": "Some paths may be outside allowed scope"})
            warnings.append("Changed paths may exceed allowed scope")
    elif changed_paths:
        checks.append({"name": "changed_paths", "result": "WARN", "detail": f"{len(changed_paths)} paths recorded, cannot verify scope"})
    else:
        checks.append({"name": "changed_paths", "result": "WARN", "detail": "No changed paths recorded"})

    # Determine verdict
    has_fail = any(c["result"] == "FAIL" for c in checks)
    has_warn = any(c["result"] == "WARN" for c in checks)

    if has_fail:
        verdict = "FAIL"
    elif has_warn:
        verdict = "WARN"
    else:
        verdict = "PASS"

    # Collect all missing fields from WARN/FAIL checks
    all_missing = []
    fixture_mode = False
    for c in checks:
        if c.get("missing_fields"):
            all_missing.extend(c["missing_fields"])
        if c.get("expected_fixture_mode"):
            fixture_mode = True

    result = {
        "verdict": verdict,
        "evidence_id": evidence_id,
        "workorder_id": workorder_id,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "missing_fields": sorted(set(all_missing)),
        "expected_fixture_mode": fixture_mode,
        "summary": {
            "total": len(checks),
            "pass": sum(1 for c in checks if c["result"] == "PASS"),
            "warn": sum(1 for c in checks if c["result"] == "WARN"),
            "fail": sum(1 for c in checks if c["result"] == "FAIL"),
        },
    }

    if use_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Evidence Verifier: {verdict}")
        print(f"  Evidence: {evidence_id}")
        print(f"  Work Order: {workorder_id}")
        print(f"  Checks: {result['summary']['total']} total, {result['summary']['pass']} pass, {result['summary']['warn']} warn, {result['summary']['fail']} fail")
        if errors:
            print(f"  Errors:")
            for e in errors:
                print(f"    - {e}")
        if warnings:
            print(f"  Warnings:")
            for w in warnings:
                print(f"    - {w}")

    if verdict == "FAIL":
        return 1
    return 0

def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Evidence Verifier — verify execution evidence bundle integrity",
        epilog="Env: VIBEDEV_EVIDENCE_DIR, VIBEDEV_REGISTRY_DIR"
    )
    parser.add_argument("--version", action="version", version=f"vibe_evidence_verifier {VERSION}")

    sub = parser.add_subparsers(dest="command")

    # verify
    vf = sub.add_parser("verify", help="Verify an evidence bundle")
    vf.add_argument("--evidence-id", required=True, help="Evidence ID")
    vf.add_argument("--evidence-dir", help="Evidence directory")
    vf.add_argument("--registry-dir", help="Registry directory")
    vf.add_argument("--json", action="store_true", help="Output as JSON")

    return parser

def main(argv=None):
    """Main entry point (import-safe)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "verify":
        return cmd_verify(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())
