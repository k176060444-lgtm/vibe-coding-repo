#!/usr/bin/env python3
"""Public-PR Pre-flight (F7 Gate) — Stage 6 of Baseline02.

Determines repo visibility and fork status before merge,
and enforces operator confirmation for public repo merges.

Usage:
    python scripts/public_pr_preflight.py --owner k176060444-lgtm --repo vibe-coding-repo
    python scripts/public_pr_preflight.py --self-check
"""

__version__ = "1.0.0"

import argparse
import json
import os
import sys
import urllib.request
import urllib.error


_MOCK_REPO_RESPONSE_PUBLIC = {
    "id": 123456, "name": "test-repo", "full_name": "test-owner/test-repo",
    "private": False, "fork": False, "default_branch": "main", "visibility": "public",
}

_MOCK_REPO_RESPONSE_PRIVATE = {
    "id": 123457, "name": "test-repo", "full_name": "test-owner/test-repo",
    "private": True, "fork": False, "default_branch": "main", "visibility": "private",
}

_MOCK_REPO_RESPONSE_FORK = {
    "id": 123458, "name": "test-repo", "full_name": "fork-owner/test-repo",
    "private": False, "fork": True, "default_branch": "main", "visibility": "public",
}

VERDICT_PASS = "PASS"
VERDICT_BLOCKED_API_FAILURE = "BLOCKED_API_FAILURE"
VERDICT_BLOCKED_NO_CONFIRMATION = "BLOCKED_PUBLIC_PR_OPERATOR_CONFIRMATION_REQUIRED"
VERDICT_BLOCKED_CONFIRMATION_FUZZY = "BLOCKED_CONFIRMATION_NOT_EXACT"


def _gh_api_get(url, gh_token=None, use_mock=False, mock_data=None):
    if use_mock:
        return mock_data if mock_data is not None else _MOCK_REPO_RESPONSE_PUBLIC
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "Hermes-vibedev-stage6"}
    if gh_token:
        headers["Authorization"] = "Bearer " + gh_token
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500] if e.code != 204 else "{}"
        raise RuntimeError("GitHub API error: HTTP " + str(e.code)) from e
    except urllib.error.URLError as e:
        raise RuntimeError("GitHub API network error") from e


def _check_operator_confirmation(confirmation, required_phrase="yes, merge"):
    if not confirmation or not confirmation.strip():
        return (False, VERDICT_BLOCKED_NO_CONFIRMATION,
                "Public repo merge requires operator confirmation")
    if confirmation.strip().lower() == required_phrase.lower():
        return (True, VERDICT_PASS, "Operator confirmation accepted")
    return (False, VERDICT_BLOCKED_CONFIRMATION_FUZZY,
            "Confirmation must be exact phrase: '" + required_phrase + "'")


def run_preflight(owner, repo, operator_confirmation=None, gh_token=None,
                   use_mock=False, mock_data=None):
    result = {
        "checked": True,
        "repo_full_name": owner + "/" + repo,
        "repo_is_public": None,
        "repo_is_fork": None,
        "default_branch": None,
        "public_repo_merge_requires_operator_confirmation": False,
        "operator_merge_authorized": False,
        "operator_confirmation_provided": False,
        "verdict": VERDICT_PASS,
        "reason": "",
    }
    url = "https://api.github.com/repos/" + owner + "/" + repo
    resolved_token = gh_token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        repo_data = _gh_api_get(url, gh_token=resolved_token, use_mock=use_mock, mock_data=mock_data)
    except (RuntimeError, json.JSONDecodeError) as e:
        result["verdict"] = VERDICT_BLOCKED_API_FAILURE
        result["reason"] = "GitHub API call failed"
        return result

    result["repo_is_public"] = not repo_data.get("private", True)
    result["repo_is_fork"] = repo_data.get("fork", False)
    result["default_branch"] = repo_data.get("default_branch", "main")
    result["repo_full_name"] = repo_data.get("full_name", owner + "/" + repo)

    if result["repo_is_public"]:
        result["public_repo_merge_requires_operator_confirmation"] = True
        is_valid, verdict, reason = _check_operator_confirmation(operator_confirmation or "")
        result["operator_confirmation_provided"] = bool(operator_confirmation and operator_confirmation.strip())
        result["verdict"] = verdict
        result["reason"] = reason
        result["operator_merge_authorized"] = is_valid
    else:
        result["operator_merge_authorized"] = True
        result["repo_is_public"] = False
        v = repo_data.get("visibility", "unknown")
        result["reason"] = "Private repo no confirmation required visibility=" + str(v)

    if result["repo_is_fork"]:
        result["reason"] = result["reason"] + " FORK_DETECTED"

    return result


def self_check(output_json=False):
    checks = []

    # f7-01: public repo, no confirmation -> blocked
    r = run_preflight("test-owner", "test-repo", operator_confirmation=None,
                       use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PUBLIC)
    ok = r["verdict"] == VERDICT_BLOCKED_NO_CONFIRMATION and not r["operator_merge_authorized"]
    checks.append({"name": "f7-01-public-no-confirmation", "passed": ok,
                   "message": "v=" + r["verdict"]})

    # f7-02: public repo, exact confirmation -> PASS
    r = run_preflight("test-owner", "test-repo", operator_confirmation="yes, merge",
                       use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PUBLIC)
    ok = r["verdict"] == VERDICT_PASS and r["operator_merge_authorized"]
    checks.append({"name": "f7-02-public-exact-confirmation", "passed": ok,
                   "message": "v=" + r["verdict"]})

    # f7-03: private repo -> PASS without confirmation
    r = run_preflight("test-owner", "test-repo", operator_confirmation=None,
                       use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PRIVATE)
    ok = r["verdict"] == VERDICT_PASS and r["operator_merge_authorized"]
    checks.append({"name": "f7-03-private-no-confirmation", "passed": ok,
                   "message": "v=" + r["verdict"]})

    # f7-04: fork flagged
    r = run_preflight("fork-owner", "test-repo", operator_confirmation="yes, merge",
                       use_mock=True, mock_data=_MOCK_REPO_RESPONSE_FORK)
    ok = r["repo_is_fork"] and "FORK_DETECTED" in r.get("reason", "")
    checks.append({"name": "f7-04-fork-flagged", "passed": ok,
                   "message": "fork=" + str(r["repo_is_fork"])})

    # f7-05: fuzzy confirmation -> blocked
    r = run_preflight("test-owner", "test-repo", operator_confirmation="yes merge",
                       use_mock=True, mock_data=_MOCK_REPO_RESPONSE_PUBLIC)
    ok = r["verdict"] == VERDICT_BLOCKED_CONFIRMATION_FUZZY and not r["operator_merge_authorized"]
    checks.append({"name": "f7-05-fuzzy-confirmation-blocked", "passed": ok,
                   "message": "v=" + r["verdict"]})

    passed = sum(1 for c in checks if c["passed"])
    failed = sum(1 for c in checks if not c["passed"])
    report = {"gate": "F7 v" + __version__, "total": len(checks),
              "passed": passed, "failed": failed,
              "result": "PASSED" if failed == 0 else "FAILED", "checks": checks}

    if output_json:
        print(json.dumps(report, indent=2))
    else:
        print("F7 self-check: " + str(passed) + "/" + str(len(checks)) + " passed")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Public-PR Pre-flight (F7) v" + __version__)
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--owner")
    parser.add_argument("--repo")
    parser.add_argument("--operator-confirmation")
    parser.add_argument("--gh-token")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.self_check:
        report = self_check(output_json=args.json)
        sys.exit(0 if report["result"] == "PASSED" else 1)

    if not args.owner or not args.repo:
        parser.error("--owner and --repo required")

    result = run_preflight(owner=args.owner, repo=args.repo,
                            operator_confirmation=args.operator_confirmation,
                            gh_token=args.gh_token)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(result["verdict"])
    sys.exit(0 if result["verdict"] == VERDICT_PASS else 1)


if __name__ == "__main__":
    main()
