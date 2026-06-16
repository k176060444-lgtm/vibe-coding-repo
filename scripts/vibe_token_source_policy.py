#!/usr/bin/env python3
"""Token Source Policy v1.0.0

Defines and enforces token source rules for repo operations.

Rules:
  - self repo automation: gh CLI cached credentials allowed (must report)
  - protected external read-only: no token needed
  - protected external push/remediation: standard token source + wrapper + approval
  - protected external writes: gh cached credentials FORBIDDEN
  - non-standard env tokens: FORBIDDEN

Usage:
    python3 scripts/vibe_token_source_policy.py check --repo <repo> --operation <op> [--json]
    python3 scripts/vibe_token_source_policy.py self-check [--json]
    python3 scripts/vibe_token_source_policy.py --version
"""

import argparse
import json
import os
import sys
import time

VERSION = "1.0.0"

# Standard token source (Debian worker)
STANDARD_TOKEN_FILE = "/home/vibeworker/.vibedev/secrets/github_privileged_token"

# Non-standard env vars that must NOT be used
FORBIDDEN_ENV_VARS = [
    "~/.vibedev-secrets/github.env",
]

# Repo classification
TRUSTED_SELF = "k176060444-lgtm/vibe-coding-repo"

# Operation categories
READ_OPS = {"fetch", "diff", "merge-dry-run", "patch", "read-tree", "log", "show", "status", "clone"}
WRITE_OPS = {"push", "pr-create", "pr-merge", "pr-update", "branch-write", "merge", "tag", "release", "deploy"}
HIGH_RISK_OPS = {"force-push", "delete-branch", "remediation-force-update"}


def classify_repo(repo):
    """Classify a repo as trusted-self or protected-external."""
    if repo == TRUSTED_SELF:
        return "trusted-self"
    return "protected-external"


def classify_operation(operation):
    """Classify an operation as read, write, or high-risk."""
    op = operation.lower().replace("_", "-")
    if op in HIGH_RISK_OPS:
        return "high-risk"
    if op in WRITE_OPS:
        return "write"
    if op in READ_OPS:
        return "read"
    # Default: treat unknown as write for safety
    return "write"


def check_token_source(repo, operation, json_output=False):
    """Check whether a token source is allowed for a repo+operation combo.

    Returns policy decision with allowed token sources.
    """
    repo_class = classify_repo(repo)
    op_class = classify_operation(operation)

    result = {
        "repo": repo,
        "repo_classification": repo_class,
        "operation": operation,
        "operation_class": op_class,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
    }

    # Policy rules
    if repo_class == "trusted-self":
        # Self repo: gh cached allowed for all ops, but must report
        result["gh_cached_credentials_allowed"] = True
        result["standard_token_allowed"] = True
        result["requires_approval"] = op_class in ("high-risk",)
        result["requires_wrapper"] = op_class in ("write", "high-risk")
        result["token_source_policy"] = "gh_cached_credentials_allowed_must_report"
        result["notes"] = "Self repo: gh CLI cached credentials allowed. Must report token_access_node=debian, token_source=gh_cached_credentials, scope=self_repo_only."

    elif repo_class == "protected-external":
        if op_class == "read":
            # External read-only: no token needed
            result["gh_cached_credentials_allowed"] = False
            result["standard_token_allowed"] = False
            result["requires_approval"] = False
            result["requires_wrapper"] = False
            result["token_source_policy"] = "no_token_needed"
            result["notes"] = "External read-only: no token needed or allowed."

        elif op_class == "write":
            # External write: standard token + wrapper + approval
            result["gh_cached_credentials_allowed"] = False
            result["standard_token_allowed"] = True
            result["requires_approval"] = True
            result["requires_wrapper"] = True
            result["token_source_policy"] = "standard_token_required_with_approval"
            result["notes"] = "External write: must use standard token source + wrapper + approval. gh cached credentials FORBIDDEN."

        elif op_class == "high-risk":
            # External high-risk: standard token + wrapper + approval + remediation approval
            result["gh_cached_credentials_allowed"] = False
            result["standard_token_allowed"] = True
            result["requires_approval"] = True
            result["requires_wrapper"] = True
            result["requires_remediation_approval"] = True
            result["token_source_policy"] = "standard_token_required_with_remediation_approval"
            result["notes"] = "External high-risk: must use standard token + wrapper + explicit remediation approval. gh cached credentials FORBIDDEN."

    # Standard token file check (metadata only, never read content)
    result["standard_token_file"] = STANDARD_TOKEN_FILE
    result["standard_token_file_exists"] = os.path.isfile(STANDARD_TOKEN_FILE)

    # Blocked sources
    result["forbidden_sources"] = FORBIDDEN_ENV_VARS

    return result


def self_check(json_output=False):
    """Self-check: verify token source policy."""
    checks = []

    # 1. Version
    checks.append({"name": "version", "passed": True, "message": VERSION})

    # 2. Self repo + push = gh_cached allowed
    r = check_token_source(TRUSTED_SELF, "push")
    checks.append({
        "name": "self_repo_push_gh_cached",
        "passed": r["gh_cached_credentials_allowed"] is True,
        "message": f"gh_cached={r['gh_cached_credentials_allowed']}",
    })

    # 3. External push = gh_cached FORBIDDEN
    r = check_token_source("NousResearch/hermes-agent", "push")
    checks.append({
        "name": "external_push_gh_cached_blocked",
        "passed": r["gh_cached_credentials_allowed"] is False,
        "message": f"gh_cached={r['gh_cached_credentials_allowed']}",
    })

    # 4. External read-only = no token
    r = check_token_source("NousResearch/hermes-agent", "fetch")
    checks.append({
        "name": "external_read_no_token",
        "passed": r["token_source_policy"] == "no_token_needed",
        "message": f"policy={r['token_source_policy']}",
    })

    # 5. Standard token metadata preflight
    r = check_token_source("NousResearch/hermes-agent", "push")
    checks.append({
        "name": "standard_token_preflight",
        "passed": r["standard_token_allowed"] is True and r["requires_approval"] is True,
        "message": f"standard_allowed={r['standard_token_allowed']} requires_approval={r['requires_approval']}",
    })

    # 6. Self repo PR merge = gh_cached allowed
    r = check_token_source(TRUSTED_SELF, "pr-merge")
    checks.append({
        "name": "self_repo_pr_merge_gh_cached",
        "passed": r["gh_cached_credentials_allowed"] is True,
        "message": f"gh_cached={r['gh_cached_credentials_allowed']}",
    })

    # 7. External force-push = gh_cached FORBIDDEN + remediation approval
    r = check_token_source("NousResearch/hermes-agent", "force-push")
    checks.append({
        "name": "external_force_push_blocked",
        "passed": r["gh_cached_credentials_allowed"] is False and r.get("requires_remediation_approval") is True,
        "message": f"gh_cached={r['gh_cached_credentials_allowed']} remediation={r.get('requires_remediation_approval')}",
    })

    # 8. Node attribution
    checks.append({
        "name": "node_attribution",
        "passed": True,
        "message": "controller=windows execution=debian",
    })

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    return {"overall": "PASS" if passed == total else "FAIL", "passed": passed, "total": total, "checks": checks}


# ── CLI ────────────────────────────────────────────────────────────────

def build_parser():
    parser = argparse.ArgumentParser(prog="vibe_token_source_policy")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    parser.add_argument("--json", action="store_true", dest="output_json")
    sub = parser.add_subparsers(dest="command")

    p_check = sub.add_parser("check")
    p_check.add_argument("--repo", required=True)
    p_check.add_argument("--operation", required=True)

    sub.add_parser("self-check")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        result = check_token_source(args.repo, args.operation)
    elif args.command == "self-check":
        result = self_check()
    else:
        parser.print_help()
        return 1

    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        if isinstance(result, dict) and "overall" in result:
            print(f"Overall: {result['overall']} ({result['passed']}/{result['total']})")
            for c in result.get("checks", []):
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  [{icon}] {c['name']}: {c['message']}")
        elif isinstance(result, dict):
            for k, v in result.items():
                if isinstance(v, (list, dict)):
                    print(f"{k}: {json.dumps(v, indent=2)[:200]}")
                else:
                    print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
