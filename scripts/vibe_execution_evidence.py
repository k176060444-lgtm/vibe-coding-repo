#!/usr/bin/env python3
"""Execution Evidence — bundle execution evidence for Work Orders.

Collects and bundles execution evidence including registry entries, approval
receipts, packaged prompts, git SHAs, PR URLs, wrapper results, smoke/health
status into a single evidence bundle.

Usage:
    python3 scripts/vibe_execution_evidence.py create --evidence-dir /path --id my-wo --base-sha abc123 --result-sha def456
    python3 scripts/vibe_execution_evidence.py list --evidence-dir /path
    python3 scripts/vibe_execution_evidence.py show --evidence-dir /path --evidence-id ev-001
    python3 scripts/vibe_execution_evidence.py list --evidence-dir /path --json

Environment Variables:
    VIBEDEV_EVIDENCE_DIR  Default evidence directory (overridden by --evidence-dir)
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
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

def _save_evidence(evidence_dir, evidence):
    """Save an evidence bundle atomically."""
    evidence_file = evidence_dir / f"{evidence['evidence_id']}.json"
    tmp_file = evidence_file.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp_file.rename(evidence_file)

def _list_evidence(evidence_dir):
    """List all evidence bundles."""
    evidence_list = []
    if not evidence_dir.is_dir():
        return evidence_list
    for f in sorted(evidence_dir.glob("*.json")):
        if f.name.startswith("."):
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                evidence = json.load(fh)
                if "evidence_id" in evidence:
                    evidence_list.append(evidence)
        except (json.JSONDecodeError, IOError):
            continue
    return evidence_list

def _compute_evidence_digest(evidence_data):
    """Compute SHA256 digest of evidence data."""
    data_str = json.dumps(evidence_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(data_str.encode("utf-8")).hexdigest()

def cmd_create(args):
    """Create a new execution evidence bundle."""
    evidence_dir = _evidence_dir_path(args)
    if not evidence_dir:
        print("ERROR: --evidence-dir or VIBEDEV_EVIDENCE_DIR required", file=sys.stderr)
        return 1

    evidence_dir.mkdir(parents=True, exist_ok=True)

    workorder_id = args.id
    if not workorder_id:
        print("ERROR: --id required", file=sys.stderr)
        return 1

    base_sha = args.base_sha
    if not base_sha:
        print("ERROR: --base-sha required", file=sys.stderr)
        return 1

    result_sha = args.result_sha
    if not result_sha:
        print("ERROR: --result-sha required", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc).isoformat()

    # Generate evidence ID
    existing_evidence = _list_evidence(evidence_dir)
    evidence_num = len(existing_evidence) + 1
    evidence_id = f"ev-{evidence_num:03d}"

    # Collect optional fields
    pr_url = getattr(args, 'pr_url', None) or ""
    pr_number = getattr(args, 'pr_number', None) or ""
    post_merge_sha = getattr(args, 'post_merge_sha', None) or ""
    wrapper_dry_run = getattr(args, 'wrapper_dry_run', None) or ""
    wrapper_merge = getattr(args, 'wrapper_merge', None) or ""
    smoke_result = getattr(args, 'smoke_result', None) or ""
    health_result = getattr(args, 'health_result', None) or ""
    implementer_model = getattr(args, 'implementer_model', None) or ""
    reviewer_model = getattr(args, 'reviewer_model', None) or ""
    job_status = getattr(args, 'job_status', None) or ""
    audit_status = getattr(args, 'audit_status', None) or ""
    changed_paths = getattr(args, 'changed_paths', None) or []
    if isinstance(changed_paths, str):
        changed_paths = [p.strip() for p in changed_paths.split(",")]

    # Evidence data for digest
    evidence_data = {
        "workorder_id": workorder_id,
        "base_sha": base_sha,
        "result_sha": result_sha,
        "pr_url": pr_url,
        "pr_number": pr_number,
        "post_merge_sha": post_merge_sha,
        "timestamp": now,
    }

    digest = _compute_evidence_digest(evidence_data)

    evidence = {
        "evidence_id": evidence_id,
        "workorder_id": workorder_id,
        "base_sha": base_sha,
        "result_sha": result_sha,
        "pr_url": pr_url,
        "pr_number": pr_number,
        "post_merge_sha": post_merge_sha,
        "wrapper_dry_run": wrapper_dry_run,
        "wrapper_merge": wrapper_merge,
        "smoke_result": smoke_result,
        "health_result": health_result,
        "implementer_model": implementer_model,
        "reviewer_model": reviewer_model,
        "job_status": job_status,
        "audit_status": audit_status,
        "changed_paths": changed_paths,
        "timestamp": now,
        "digest": digest,
    }

    _save_evidence(evidence_dir, evidence)

    use_json = getattr(args, 'json', False)
    if use_json:
        print(json.dumps({"action": "create", "evidence": evidence}, indent=2, ensure_ascii=False))
    else:
        print(f"Evidence Created: {evidence_id}")
        print(f"  Work Order: {workorder_id}")
        print(f"  Base SHA: {base_sha[:16]}...")
        print(f"  Result SHA: {result_sha[:16]}...")
        print(f"  Digest: {digest[:16]}...")
        print(f"  Timestamp: {now}")

    return 0

def cmd_list(args):
    """List all evidence bundles."""
    evidence_dir = _evidence_dir_path(args)
    if not evidence_dir:
        print("ERROR: --evidence-dir or VIBEDEV_EVIDENCE_DIR required", file=sys.stderr)
        return 1

    evidence_list = _list_evidence(evidence_dir)

    use_json = getattr(args, 'json', False)
    if use_json:
        output = {
            "action": "list",
            "evidence_dir": str(evidence_dir),
            "count": len(evidence_list),
            "evidence": evidence_list,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        if not evidence_list:
            print("No evidence found")
        else:
            print(f"Evidence: {len(evidence_list)} bundles")
            print()
            for ev in evidence_list:
                print(f"  [{ev['evidence_id']}] {ev['workorder_id']}: {ev['base_sha'][:8]}..{ev['result_sha'][:8]} @ {ev['timestamp'][:19]}")
    return 0

def cmd_show(args):
    """Show details of a specific evidence bundle."""
    evidence_dir = _evidence_dir_path(args)
    if not evidence_dir:
        print("ERROR: --evidence-dir or VIBEDEV_EVIDENCE_DIR required", file=sys.stderr)
        return 1

    evidence_id = args.evidence_id
    if not evidence_id:
        print("ERROR: --evidence-id required", file=sys.stderr)
        return 1

    evidence = _load_evidence(evidence_dir, evidence_id)
    if not evidence:
        print(f"ERROR: Evidence '{evidence_id}' not found", file=sys.stderr)
        return 1

    use_json = getattr(args, 'json', False)
    if use_json:
        output = {
            "action": "show",
            "evidence": evidence,
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    else:
        print(f"Evidence: {evidence['evidence_id']}")
        print(f"  Work Order: {evidence['workorder_id']}")
        print(f"  Base SHA: {evidence['base_sha']}")
        print(f"  Result SHA: {evidence['result_sha']}")
        print(f"  PR URL: {evidence.get('pr_url', '')}")
        print(f"  PR Number: {evidence.get('pr_number', '')}")
        print(f"  Post-Merge SHA: {evidence.get('post_merge_sha', '')}")
        print(f"  Wrapper Dry-Run: {evidence.get('wrapper_dry_run', '')}")
        print(f"  Wrapper Merge: {evidence.get('wrapper_merge', '')}")
        print(f"  Smoke Result: {evidence.get('smoke_result', '')}")
        print(f"  Health Result: {evidence.get('health_result', '')}")
        print(f"  Implementer Model: {evidence.get('implementer_model', '')}")
        print(f"  Reviewer Model: {evidence.get('reviewer_model', '')}")
        print(f"  Job Status: {evidence.get('job_status', '')}")
        print(f"  Audit Status: {evidence.get('audit_status', '')}")
        print(f"  Changed Paths: {', '.join(evidence.get('changed_paths', []))}")
        print(f"  Timestamp: {evidence['timestamp']}")
        print(f"  Digest: {evidence['digest'][:16]}...")
    return 0

def build_parser():
    """Build argument parser."""
    parser = argparse.ArgumentParser(
        description="Execution Evidence — bundle execution evidence for Work Orders",
        epilog="Env: VIBEDEV_EVIDENCE_DIR sets default evidence directory"
    )
    parser.add_argument("--version", action="version", version=f"vibe_execution_evidence {VERSION}")

    sub = parser.add_subparsers(dest="command")

    # create
    cr = sub.add_parser("create", help="Create a new evidence bundle")
    cr.add_argument("--id", required=True, help="Work order ID")
    cr.add_argument("--base-sha", required=True, help="Base commit SHA")
    cr.add_argument("--result-sha", required=True, help="Result commit SHA")
    cr.add_argument("--pr-url", help="PR URL")
    cr.add_argument("--pr-number", help="PR number")
    cr.add_argument("--post-merge-sha", help="Post-merge main SHA")
    cr.add_argument("--wrapper-dry-run", help="Wrapper dry-run result")
    cr.add_argument("--wrapper-merge", help="Wrapper merge result")
    cr.add_argument("--smoke-result", help="Smoke test result")
    cr.add_argument("--health-result", help="Health check result")
    cr.add_argument("--implementer-model", help="Implementer model")
    cr.add_argument("--reviewer-model", help="Reviewer model")
    cr.add_argument("--job-status", help="Job status")
    cr.add_argument("--audit-status", help="Audit status")
    cr.add_argument("--changed-paths", help="Changed paths (comma-separated)")
    cr.add_argument("--evidence-dir", help="Evidence directory")
    cr.add_argument("--json", action="store_true", help="Output as JSON")

    # list
    ls = sub.add_parser("list", help="List all evidence bundles")
    ls.add_argument("--evidence-dir", help="Evidence directory")
    ls.add_argument("--json", action="store_true", help="Output as JSON")

    # show
    sh = sub.add_parser("show", help="Show details of a specific evidence bundle")
    sh.add_argument("--evidence-id", required=True, help="Evidence ID")
    sh.add_argument("--evidence-dir", help="Evidence directory")
    sh.add_argument("--json", action="store_true", help="Output as JSON")

    return parser

def main(argv=None):
    """Main entry point (import-safe)."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    if args.command == "create":
        return cmd_create(args)
    elif args.command == "list":
        return cmd_list(args)
    elif args.command == "show":
        return cmd_show(args)
    else:
        parser.print_help()
        return 0

if __name__ == "__main__":
    sys.exit(main())
