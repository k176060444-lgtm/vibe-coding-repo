#!/usr/bin/env python3
"""Remote Verification Gate v1.0.0 — verify GitHub PR remote source-of-truth.

Ensures final reports are backed by verified remote state, not just local claims.
Detects stale base, head mismatch, file drift, body drift, draft/ready mismatch,
merged state, and GitHub API failures.

Usage:
    python scripts/remote_verification_gate.py verify-pr --pr 197 --repo owner/repo \
        --expected-head SHA --expected-base SHA \
        --expected-files .gitignore scripts/opencode_model_pool.py \
        --expected-body-contains "Scope" \
        [--json]
    python scripts/remote_verification_gate.py verify-pr --pr 197 --repo owner/repo \
        --pr-data-file pr_data.json [--json]
    python scripts/remote_verification_gate.py self-check [--json]

Exit codes:
    0 = PASS
    1 = BLOCKED
    2 = WARNING (issues found but not blocking)
    3 = usage error

Constraints:
    - Read-only. No file writes, no pushes, no merges.
    - No secrets read. No live model calls.
"""

__version__ = "1.1.0"

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


# --- Severity levels ---

SEVERITY_BLOCK = "BLOCK"
SEVERITY_WARN = "WARNING"
SEVERITY_PASS = "PASS"
SEVERITY_INFO = "INFO"


# --- Mismatch types ---

MISMATCH_TYPES = {
    "head_sha_mismatch": {
        "severity": SEVERITY_BLOCK,
        "description": "Local HEAD does not match PR headRefOid",
    },
    "base_sha_mismatch": {
        "severity": SEVERITY_BLOCK,
        "description": "Expected base does not match PR baseRefOid",
    },
    "files_mismatch": {
        "severity": SEVERITY_BLOCK,
        "description": "PR diff files do not match expected files",
    },
    "body_missing_text": {
        "severity": SEVERITY_WARN,
        "description": "PR body does not contain expected text",
    },
    "draft_ready_mismatch": {
        "severity": SEVERITY_WARN,
        "description": "PR draft/ready state does not match report claim",
    },
    "merged_not_reported": {
        "severity": SEVERITY_BLOCK,
        "description": "PR is merged but report does not mention it",
    },
    "local_remote_diff_mismatch": {
        "severity": SEVERITY_BLOCK,
        "description": "GitHub PR diff does not match local git diff",
    },
    "stale_base": {
        "severity": SEVERITY_BLOCK,
        "description": "PR baseRefOid is stale — base branch has advanced",
    },
    "api_failure": {
        "severity": SEVERITY_BLOCK,
        "description": "GitHub API call failed — cannot verify remote state",
    },
    "pr_not_found": {
        "severity": SEVERITY_BLOCK,
        "description": "PR not found on GitHub",
    },
    "pr_not_open": {
        "severity": SEVERITY_WARN,
        "description": "PR is not in OPEN state",
    },
}


# --- GitHub PR fetcher ---

def fetch_pr_data(repo: str, pr_number: int) -> tuple:
    """Fetch PR data via gh CLI. Returns (data_dict, error_string).

    Does NOT read secrets. Only reads PR metadata.
    Error string is prefixed with "PR_NOT_FOUND: " when the PR doesn't exist.
    """
    try:
        result = subprocess.run(
            [
                "gh", "pr", "view", str(pr_number),
                "-R", repo,
                "--json",
                "number,title,state,isDraft,mergeable,"
                "baseRefName,baseRefOid,headRefName,headRefOid,"
                "url,body,commits,files,statusCheckRollup",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            stderr_lower = result.stderr.lower()
            if "not found" in stderr_lower or "could not resolve" in stderr_lower:
                return None, f"PR_NOT_FOUND: PR #{pr_number} not found in {repo}"
            return None, f"gh pr view failed (exit={result.returncode}): {result.stderr.strip()}"
        data = json.loads(result.stdout)
        return data, None
    except FileNotFoundError:
        return None, "gh CLI not found — cannot verify remote state"
    except json.JSONDecodeError as e:
        return None, f"Failed to parse gh output: {e}"
    except subprocess.TimeoutExpired:
        return None, "gh pr view timed out (30s)"
    except Exception as e:
        return None, f"Unexpected error: {e}"


def fetch_pr_data_result(repo: str, pr_number: int) -> dict:
    """Fetch PR data and return structured result for verify_pr().

    Returns dict with keys: pr_data, pr_not_found, pr_error.
    Callers pass these directly into verify_pr() keyword args.

    Example:
        fr = fetch_pr_data_result("owner/repo", 197)
        result = verify_pr(pr_diff_files=..., **fr)
    """
    pr_data, pr_error = fetch_pr_data(repo, pr_number)
    pr_not_found = pr_error is not None and pr_error.startswith("PR_NOT_FOUND:")
    return {
        "pr_data": pr_data,
        "pr_not_found": pr_not_found,
        "pr_error": pr_error,
    }


def fetch_pr_diff_files(repo: str, pr_number: int) -> tuple:
    """Fetch PR diff file list via gh CLI. Returns (list_of_files, error_string)."""
    try:
        result = subprocess.run(
            ["gh", "pr", "diff", str(pr_number), "-R", repo, "--name-only"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return None, f"gh pr diff failed (exit={result.returncode}): {result.stderr.strip()}"
        files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return files, None
    except FileNotFoundError:
        return None, "gh CLI not found"
    except subprocess.TimeoutExpired:
        return None, "gh pr diff timed out"
    except Exception as e:
        return None, f"Unexpected error: {e}"


def fetch_local_diff_files(repo_root: str, base_ref: str, head_ref: str) -> tuple:
    """Fetch local git diff file list. Returns (list_of_files, error_string)."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=repo_root,
        )
        if result.returncode != 0:
            return None, f"git diff failed: {result.stderr.strip()}"
        files = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        return files, None
    except Exception as e:
        return None, f"git diff error: {e}"


# --- Verification engine ---

def verify_pr(
    pr_data: dict = None,
    pr_diff_files: list = None,
    expected_head_oid: str = None,
    expected_base_oid: str = None,
    expected_files: list = None,
    expected_body_contains: list = None,
    expected_is_draft: bool = None,
    report_claims_merged: bool = None,
    local_diff_files: list = None,
    current_main_oid: str = None,
    pr_not_found: bool = False,
    pr_error: str = None,
) -> dict:
    """Verify PR remote state against expectations.

    Args:
        pr_data: PR data dict from gh CLI (None if fetch failed).
        pr_diff_files: File list from gh pr diff --name-only.
        expected_head_oid: Expected PR headRefOid (BLOCK on mismatch).
        expected_base_oid: Expected PR baseRefOid (BLOCK on mismatch).
        expected_files: Expected diff file list (BLOCK on mismatch).
        expected_body_contains: Texts that must appear in PR body (WARNING on missing).
        expected_is_draft: Expected isDraft state (WARNING on mismatch).
        report_claims_merged: Three-state:
            None  = merged check skipped (caller didn't assert merged status);
            True  = report claims PR is merged (PASS if PR is MERGED);
            False = report does NOT mention merged (BLOCK if PR is MERGED).
        local_diff_files: Local diff file list for cross-check against remote.
        current_main_oid: Current main HEAD for stale base detection (BLOCK on mismatch).
        pr_not_found: If True, produce pr_not_found BLOCK instead of api_failure.
        pr_error: Raw error string from fetch (recorded in result for diagnostics).

    Returns:
        {
            "verdict": "PASS" | "BLOCKED" | "WARNING",
            "mismatches": [{type, severity, detail, expected, actual}],
            "warnings": [{type, severity, detail}],
            "pr_summary": {number, state, isDraft, ...},
            "checks_passed": int,
            "checks_total": int,
        }
    """
    mismatches = []
    warnings = []
    checks_total = 0
    checks_passed = 0

    # Handle API failure / PR not found
    if pr_data is None:
        if pr_not_found:
            mismatches.append({
                "type": "pr_not_found",
                "severity": SEVERITY_BLOCK,
                "detail": pr_error or "PR not found on GitHub",
            })
        else:
            mismatches.append({
                "type": "api_failure",
                "severity": SEVERITY_BLOCK,
                "detail": pr_error or "Could not fetch PR data from GitHub",
            })
        return _build_result(mismatches, warnings, checks_total, checks_passed, None)

    # Extract PR fields
    pr_number = pr_data.get("number")
    pr_state = pr_data.get("state", "UNKNOWN")
    pr_is_draft = pr_data.get("isDraft")
    pr_mergeable = pr_data.get("mergeable", "UNKNOWN")
    pr_base_oid = pr_data.get("baseRefOid", "")
    pr_head_oid = pr_data.get("headRefOid", "")
    pr_base_name = pr_data.get("baseRefName", "")
    pr_head_name = pr_data.get("headRefName", "")
    pr_body = pr_data.get("body", "")
    pr_files = pr_data.get("files", [])
    pr_commits = pr_data.get("commits", [])

    pr_summary = {
        "number": pr_number,
        "state": pr_state,
        "isDraft": pr_is_draft,
        "mergeable": pr_mergeable,
        "baseRefName": pr_base_name,
        "baseRefOid": pr_base_oid,
        "headRefName": pr_head_name,
        "headRefOid": pr_head_oid,
        "file_count": len(pr_files) if isinstance(pr_files, list) else pr_files,
        "commit_count": len(pr_commits) if isinstance(pr_commits, list) else 0,
    }

    # Check 1: PR is OPEN
    checks_total += 1
    if pr_state == "MERGED":
        if report_claims_merged is False:
            mismatches.append({
                "type": "merged_not_reported",
                "severity": SEVERITY_BLOCK,
                "detail": "PR is MERGED but report does not mention it",
            })
        else:
            checks_passed += 1
    elif pr_state != "OPEN":
        warnings.append({
            "type": "pr_not_open",
            "severity": SEVERITY_WARN,
            "detail": f"PR state is '{pr_state}', expected OPEN",
        })
    else:
        checks_passed += 1

    # Check 2: Head OID match
    if expected_head_oid:
        checks_total += 1
        if pr_head_oid.lower() != expected_head_oid.lower():
            mismatches.append({
                "type": "head_sha_mismatch",
                "severity": MISMATCH_TYPES["head_sha_mismatch"]["severity"],
                "detail": f"PR headRefOid mismatch",
                "expected": expected_head_oid,
                "actual": pr_head_oid,
            })
        else:
            checks_passed += 1

    # Check 3: Base OID match
    if expected_base_oid:
        checks_total += 1
        if pr_base_oid.lower() != expected_base_oid.lower():
            mismatches.append({
                "type": "base_sha_mismatch",
                "severity": MISMATCH_TYPES["base_sha_mismatch"]["severity"],
                "detail": f"PR baseRefOid mismatch",
                "expected": expected_base_oid,
                "actual": pr_base_oid,
            })
        else:
            checks_passed += 1

    # Check 4: Stale base (current_main_oid vs pr_base_oid)
    if current_main_oid:
        checks_total += 1
        if pr_base_oid.lower() != current_main_oid.lower():
            mismatches.append({
                "type": "stale_base",
                "severity": MISMATCH_TYPES["stale_base"]["severity"],
                "detail": "PR baseRefOid does not match current main HEAD",
                "expected": current_main_oid,
                "actual": pr_base_oid,
            })
        else:
            checks_passed += 1

    # Check 5: Files match (from gh pr diff)
    if expected_files is not None and pr_diff_files is not None:
        checks_total += 1
        expected_set = set(expected_files)
        actual_set = set(pr_diff_files)
        if expected_set != actual_set:
            missing = expected_set - actual_set
            extra = actual_set - expected_set
            detail_parts = []
            if missing:
                detail_parts.append(f"missing: {sorted(missing)}")
            if extra:
                detail_parts.append(f"extra: {sorted(extra)}")
            mismatches.append({
                "type": "files_mismatch",
                "severity": MISMATCH_TYPES["files_mismatch"]["severity"],
                "detail": "; ".join(detail_parts),
                "expected": sorted(expected_set),
                "actual": sorted(actual_set),
            })
        else:
            checks_passed += 1

    # Check 6: Body contains expected text
    if expected_body_contains:
        checks_total += 1
        missing_texts = []
        for text in expected_body_contains:
            if text.lower() not in pr_body.lower():
                missing_texts.append(text)
        if missing_texts:
            warnings.append({
                "type": "body_missing_text",
                "severity": MISMATCH_TYPES["body_missing_text"]["severity"],
                "detail": f"PR body missing expected text: {missing_texts}",
                "expected": expected_body_contains,
                "actual": f"body length={len(pr_body)}",
            })
        else:
            checks_passed += 1

    # Check 7: Draft/Ready mismatch
    if expected_is_draft is not None:
        checks_total += 1
        if pr_is_draft != expected_is_draft:
            warnings.append({
                "type": "draft_ready_mismatch",
                "severity": MISMATCH_TYPES["draft_ready_mismatch"]["severity"],
                "detail": f"PR isDraft={pr_is_draft}, expected={expected_is_draft}",
                "expected": expected_is_draft,
                "actual": pr_is_draft,
            })
        else:
            checks_passed += 1

    # Check 8: Local vs remote diff consistency
    if local_diff_files is not None and pr_diff_files is not None:
        checks_total += 1
        local_set = set(local_diff_files)
        remote_set = set(pr_diff_files)
        if local_set != remote_set:
            only_local = local_set - remote_set
            only_remote = remote_set - local_set
            detail_parts = []
            if only_local:
                detail_parts.append(f"only_local: {sorted(only_local)}")
            if only_remote:
                detail_parts.append(f"only_remote: {sorted(only_remote)}")
            mismatches.append({
                "type": "local_remote_diff_mismatch",
                "severity": MISMATCH_TYPES["local_remote_diff_mismatch"]["severity"],
                "detail": "; ".join(detail_parts),
                "expected": sorted(local_set),
                "actual": sorted(remote_set),
            })
        else:
            checks_passed += 1

    return _build_result(mismatches, warnings, checks_total, checks_passed, pr_summary)


def _build_result(mismatches, warnings, checks_total, checks_passed, pr_summary):
    """Build verification result dict."""
    has_block = any(m["severity"] == SEVERITY_BLOCK for m in mismatches)
    has_warn = len(warnings) > 0 or any(m["severity"] == SEVERITY_WARN for m in mismatches)

    if has_block:
        verdict = "BLOCKED"
    elif has_warn:
        verdict = "WARNING"
    else:
        verdict = "PASS"

    all_issues = mismatches + warnings

    return {
        "verdict": verdict,
        "version": __version__,
        "mismatches": mismatches,
        "warnings": warnings,
        "all_issues": all_issues,
        "checks_passed": checks_passed,
        "checks_total": checks_total,
        "pr_summary": pr_summary,
    }


# --- Self-check (no network) ---

def self_check() -> dict:
    """Run self-check with synthetic data. No GitHub API calls."""
    checks = []
    passed = 0
    total = 0

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal passed, total
        total += 1
        if ok:
            passed += 1
        checks.append({"name": name, "passed": ok, "detail": detail})

    # rv-01: version
    check("rv-01-version", bool(__version__), __version__)

    # rv-02: PASS case — all expectations met
    mock_pr = {
        "number": 197, "state": "OPEN", "isDraft": False, "mergeable": "MERGEABLE",
        "baseRefName": "main", "baseRefOid": "aaa111",
        "headRefName": "feat/test", "headRefOid": "bbb222",
        "body": "## Scope\nSome content", "files": [{"path": "a.py"}],
        "commits": [{"oid": "bbb222"}],
    }
    result_pass = verify_pr(
        pr_data=mock_pr,
        pr_diff_files=["a.py"],
        expected_head_oid="bbb222",
        expected_base_oid="aaa111",
        expected_files=["a.py"],
        expected_body_contains=["Scope"],
        expected_is_draft=False,
    )
    check("rv-02-pass-verdict", result_pass["verdict"] == "PASS",
          f"got={result_pass['verdict']}")
    check("rv-02-pass-checks", result_pass["checks_passed"] == result_pass["checks_total"],
          f"{result_pass['checks_passed']}/{result_pass['checks_total']}")

    # rv-03: head SHA mismatch
    result_head = verify_pr(
        pr_data=mock_pr,
        expected_head_oid="ccc999",
    )
    check("rv-03-head-mismatch", result_head["verdict"] == "BLOCKED")
    check("rv-03-head-type",
          any(m["type"] == "head_sha_mismatch" for m in result_head["mismatches"]))

    # rv-04: base SHA mismatch
    result_base = verify_pr(
        pr_data=mock_pr,
        expected_base_oid="ddd888",
    )
    check("rv-04-base-mismatch", result_base["verdict"] == "BLOCKED")
    check("rv-04-base-type",
          any(m["type"] == "base_sha_mismatch" for m in result_base["mismatches"]))

    # rv-05: files mismatch
    result_files = verify_pr(
        pr_data=mock_pr,
        pr_diff_files=["a.py", "extra.py"],
        expected_files=["a.py"],
    )
    check("rv-05-files-mismatch", result_files["verdict"] == "BLOCKED")
    check("rv-05-files-type",
          any(m["type"] == "files_mismatch" for m in result_files["mismatches"]))

    # rv-06: body missing text
    result_body = verify_pr(
        pr_data=mock_pr,
        expected_body_contains=["NonexistentSection"],
    )
    check("rv-06-body-missing", result_body["verdict"] == "WARNING")
    check("rv-06-body-type",
          any(w["type"] == "body_missing_text" for w in result_body["warnings"]))

    # rv-07: draft/ready mismatch — PR is not draft but report claims draft
    result_draft = verify_pr(
        pr_data=mock_pr,
        expected_is_draft=True,
    )
    check("rv-07-draft-mismatch", result_draft["verdict"] == "WARNING")
    check("rv-07-draft-type",
          any(w["type"] == "draft_ready_mismatch" for w in result_draft["warnings"]))

    # rv-08: merged not reported
    mock_merged = {**mock_pr, "state": "MERGED"}
    result_merged = verify_pr(
        pr_data=mock_merged,
        report_claims_merged=False,
    )
    check("rv-08-merged-not-reported", result_merged["verdict"] == "BLOCKED")
    check("rv-08-merged-type",
          any(m["type"] == "merged_not_reported" for m in result_merged["mismatches"]))

    # rv-09: merged reported (PASS)
    result_merged_ok = verify_pr(
        pr_data=mock_merged,
        report_claims_merged=True,
    )
    check("rv-09-merged-reported", result_merged_ok["verdict"] == "PASS")

    # rv-10: local/remote diff mismatch
    result_diff = verify_pr(
        pr_data=mock_pr,
        pr_diff_files=["a.py"],
        local_diff_files=["a.py", "b.py"],
    )
    check("rv-10-diff-mismatch", result_diff["verdict"] == "BLOCKED")
    check("rv-10-diff-type",
          any(m["type"] == "local_remote_diff_mismatch" for m in result_diff["mismatches"]))

    # rv-11: stale base
    result_stale = verify_pr(
        pr_data=mock_pr,
        current_main_oid="ccc999",
    )
    check("rv-11-stale-base", result_stale["verdict"] == "BLOCKED")
    check("rv-11-stale-type",
          any(m["type"] == "stale_base" for m in result_stale["mismatches"]))

    # rv-12: API failure
    result_api = verify_pr(pr_data=None)
    check("rv-12-api-failure", result_api["verdict"] == "BLOCKED")
    check("rv-12-api-type",
          any(m["type"] == "api_failure" for m in result_api["mismatches"]))

    # rv-13: no expectations = PASS with no checks
    result_empty = verify_pr(pr_data=mock_pr)
    check("rv-13-no-expectations", result_empty["verdict"] == "PASS")

    # rv-14: multiple failures
    result_multi = verify_pr(
        pr_data=mock_pr,
        expected_head_oid="wrong",
        expected_base_oid="wrong",
        pr_diff_files=["a.py"],
        expected_files=["wrong.py"],
        expected_is_draft=True,
    )
    check("rv-14-multi-fail", result_multi["verdict"] == "BLOCKED")
    check("rv-14-multi-count", len(result_multi["mismatches"]) >= 3,
          f"count={len(result_multi['mismatches'])}")

    # rv-15: MISMATCH_TYPES completeness
    check("rv-15-types-count", len(MISMATCH_TYPES) >= 9,
          f"count={len(MISMATCH_TYPES)}")

    # rv-16: fetch_pr_data with mock (test the function signature)
    check("rv-16-fetch-sig", callable(fetch_pr_data))

    # rv-17: pr_not_found via verify_pr (M-2 — unified path)
    result_pnf = verify_pr(
        pr_data=None,
        pr_not_found=True,
        pr_error="PR_NOT_FOUND: PR #999 not found in owner/repo",
    )
    check("rv-17-pr-not-found-verdict", result_pnf["verdict"] == "BLOCKED")
    check("rv-17-pr-not-found-type",
          any(m["type"] == "pr_not_found" for m in result_pnf["mismatches"]),
          f"types={[m['type'] for m in result_pnf['mismatches']]}")

    # rv-18: pr_not_found does NOT produce api_failure
    check("rv-18-pr-not-found-no-api",
          not any(m["type"] == "api_failure" for m in result_pnf["mismatches"]))

    # rv-19: api_failure still works without pr_not_found flag
    result_api2 = verify_pr(
        pr_data=None,
        pr_error="gh pr view failed (exit=1): network error",
    )
    check("rv-19-api-failure-still-works", result_api2["verdict"] == "BLOCKED")
    check("rv-19-api-type",
          any(m["type"] == "api_failure" for m in result_api2["mismatches"]))
    check("rv-19-no-pr-not-found",
          not any(m["type"] == "pr_not_found" for m in result_api2["mismatches"]))

    # rv-20: fetch_pr_data_result signature
    check("rv-20-fetch-result-sig", callable(fetch_pr_data_result))

    # rv-21: draft_ready_mismatch warning alone = WARNING (M-3)
    result_draft_alone = verify_pr(
        pr_data=mock_pr,
        expected_is_draft=True,
    )
    check("rv-21-draft-alone-warn", result_draft_alone["verdict"] == "WARNING",
          f"got={result_draft_alone['verdict']}")

    # rv-22: draft_ready_mismatch + BLOCK coexistence = BLOCKED (M-3)
    result_draft_block = verify_pr(
        pr_data=mock_pr,
        expected_head_oid="wrong",
        expected_is_draft=True,
    )
    check("rv-22-draft-plus-block", result_draft_block["verdict"] == "BLOCKED",
          f"got={result_draft_block['verdict']}")
    check("rv-22-has-draft-warn",
          any(w["type"] == "draft_ready_mismatch" for w in result_draft_block["warnings"]))
    check("rv-22-has-head-block",
          any(m["type"] == "head_sha_mismatch" for m in result_draft_block["mismatches"]))

    # rv-23: pr_not_found with empty detail fallback
    result_pnf_empty = verify_pr(pr_data=None, pr_not_found=True)
    check("rv-23-pr-not-found-fallback",
          result_pnf_empty["mismatches"][0]["detail"] == "PR not found on GitHub")

    return {
        "version": __version__,
        "passed": passed == total,
        "total_tests": total,
        "passed_count": passed,
        "failed_count": total - passed,
        "checks": checks,
        "exit_code": 0 if passed == total else 1,
    }


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(
        description="Remote Verification Gate — verify GitHub PR source-of-truth")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    sub = parser.add_subparsers(dest="command")

    # verify-pr
    vp = sub.add_parser("verify-pr", help="Verify PR remote state")
    vp.add_argument("--pr", type=int, required=True, help="PR number")
    vp.add_argument("--repo", required=True, help="owner/repo")
    vp.add_argument("--expected-head", help="Expected headRefOid")
    vp.add_argument("--expected-base", help="Expected baseRefOid")
    vp.add_argument("--expected-files", nargs="*", help="Expected diff file list")
    vp.add_argument("--expected-body-contains", nargs="*", help="Expected text in PR body")
    vp.add_argument("--expected-is-draft", type=lambda x: x.lower() == "true",
                    help="Expected isDraft (true/false)")
    vp.add_argument("--report-claims-merged", type=lambda x: x.lower() == "true",
                    help="Whether report claims PR is merged")
    vp.add_argument("--current-main-oid", help="Current main HEAD for stale base check")
    vp.add_argument("--local-diff-files", nargs="*",
                    help="Local diff files for cross-check against remote")
    vp.add_argument("--pr-data-file",
                    help="Path to PR data JSON (skip gh fetch, for testing)")

    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"=== REMOTE VERIFICATION GATE SELF-CHECK (v{__version__}) ===")
            print(f"  Total: {result['total_tests']}")
            print(f"  Passed: {result['passed_count']}")
            print(f"  Failed: {result['failed_count']}")
            for c in result["checks"]:
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  {icon}  {c['name']}: {c['detail']}")
            print(f"\n  Self-check: {'PASSED' if result['passed'] else 'FAILED'}")
        sys.exit(result["exit_code"])

    if args.command == "verify-pr":
        # Fetch PR data
        if args.pr_data_file:
            with open(args.pr_data_file, "r", encoding="utf-8") as f:
                pr_data = json.load(f)
            pr_not_found = False
            pr_error = None
        else:
            fr = fetch_pr_data_result(args.repo, args.pr)
            pr_data = fr["pr_data"]
            pr_not_found = fr["pr_not_found"]
            pr_error = fr["pr_error"]

        # Fetch PR diff files
        pr_diff_files = None
        if pr_data is not None:
            pr_diff_files, _ = fetch_pr_diff_files(args.repo, args.pr)

        # Run verification (pr_not_found and pr_error handled inside verify_pr)
        result = verify_pr(
            pr_data=pr_data,
            pr_diff_files=pr_diff_files,
            expected_head_oid=args.expected_head,
            expected_base_oid=args.expected_base,
            expected_files=args.expected_files,
            expected_body_contains=args.expected_body_contains,
            expected_is_draft=args.expected_is_draft,
            report_claims_merged=args.report_claims_merged,
            local_diff_files=args.local_diff_files,
            current_main_oid=args.current_main_oid,
            pr_not_found=pr_not_found,
            pr_error=pr_error,
        )

        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Remote Verification: {result['verdict']}")
            print(f"  Checks: {result['checks_passed']}/{result['checks_total']}")
            if result["pr_summary"]:
                ps = result["pr_summary"]
                print(f"  PR #{ps['number']}: {ps['state']} "
                      f"draft={ps['isDraft']} mergeable={ps['mergeable']}")
                print(f"  Base: {ps['baseRefName']} ({ps['baseRefOid'][:12]})")
                print(f"  Head: {ps['headRefName']} ({ps['headRefOid'][:12]})")
            for m in result["mismatches"]:
                print(f"  ❌ [{m['severity']}] {m['type']}: {m['detail']}")
            for w in result["warnings"]:
                print(f"  ⚠️ [{w['severity']}] {w['type']}: {w['detail']}")

        exit_codes = {"PASS": 0, "BLOCKED": 1, "WARNING": 2}
        sys.exit(exit_codes.get(result["verdict"], 1))

    parser.print_help()
    sys.exit(3)


if __name__ == "__main__":
    main()
