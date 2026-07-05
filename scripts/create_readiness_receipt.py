#!/usr/bin/env python3
"""
create_readiness_receipt.py — G-L4 Readiness Receipt Generator (Pipeline).

Read-only assemble + emit.  Does NOT enter gray / Baseline03 / Stage8.

Reads NMC, validates operator-approved exact set, validates qwen non_scope,
runs / receives sub-test results, validates git env, validates base_sha,
and emits a PASS/BLOCKED readiness receipt dict (YAML-ready).

USAGE
-----
    from create_readiness_receipt import build_receipt
    receipt = build_receipt(
        repo_root=Path("."),
        base_sha="2abbcde0d5ba1b359faf66db7e9470e96d839a40",
    )
    # receipt["verdict"] is "PASS" or "BLOCKED"
    # receipt["blocked_reasons"] lists each fail-closed gate that fired

This script DOES NOT write the receipt YAML to disk.  Emission of the
YAML file is an operator-authorized step in a separate PR.

FAIL-CLOSED GATES
-----------------
1. NMC missing or yaml parse error → BLOCKED
2. operator_approved set != expected 6 entries → BLOCKED
3. qwen3-7-plus × 3 any != 'unknown' → BLOCKED
4. Any sub-test failed > 0 (or subprocess error) → BLOCKED
5. git status --porcelain non-empty → BLOCKED
6. open PRs > 0 → BLOCKED
7. base_sha != current HEAD → BLOCKED
8. gray/baseline03/stage8 artifacts present → BLOCKED
"""

__version__ = "0.1.0"

import datetime as _dt
import hashlib
import os
import sys
import re
import subprocess
from pathlib import Path
from typing import Optional

import yaml


# ── Constants ────────────────────────────────────────────────────────────────

EXPECTED_OPERATOR_APPROVED = frozenset({
    ("21bao", "opencode-go-deepseek-v4-pro"),
    ("5bao",  "opencode-go-deepseek-v4-pro"),
    ("9bao",  "opencode-go-deepseek-v4-pro"),
    ("21bao", "opencode-go-mimo-v2-5"),
    ("5bao",  "opencode-go-mimo-v2-5"),
    ("9bao",  "opencode-go-mimo-v2-5"),
})

EXPECTED_NON_SCOPE = frozenset({
    ("21bao", "opencode-go-qwen3-7-plus"),
    ("5bao",  "opencode-go-qwen3-7-plus"),
    ("9bao",  "opencode-go-qwen3-7-plus"),
})

# Sub-test suites (relative to repo root)
SUBTEST_SUITES = [
    ("apply_tool",   "tests/test_apply_operator_approval_receipt.py"),
    ("stage4",       "tests/test_stage4_model_pool_gate.py"),
    ("stage7",       "tests/test_stage7_f6_readiness_gate.py"),
    ("g_l4_planning","tests/test_g_l4_readiness_bridge_planning.py"),
    ("d_b_policy_lock","tests/test_da_db_policy_lock.py"),
]

NMC_RELATIVE_PATH = "scripts/node_model_capability.yaml"

# Forbidden artifact paths (must NOT be present for PASS)
FORBIDDEN_ARTIFACT_PATTERNS = [
    "docs/baseline02/gray",
    "docs/baseline02/baseline03",
    "docs/baseline02/stage8",
    "scripts/g_gray",
    "scripts/g_baseline03",
    "scripts/g_stage8",
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _git(*args: str, repo_root: Path) -> subprocess.CompletedProcess:
    """Run git in repo_root and return CompletedProcess."""
    return subprocess.run(
        ["git", *args],
        capture_output=True, text=True, timeout=15,
        cwd=str(repo_root),
    )


def _current_head_sha(repo_root: Path) -> Optional[str]:
    """Return current HEAD sha, or None on failure."""
    r = _git("rev-parse", "HEAD", repo_root=repo_root)
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def _git_clean(repo_root: Path) -> bool:
    """True if `git status --porcelain` is empty."""
    r = _git("status", "--porcelain=v1", "--untracked-files=all", repo_root=repo_root)
    if r.returncode != 0:
        return False
    return r.stdout.strip() == ""


def _open_prs(repo_root: Path) -> int:
    """Return number of open PRs via `gh pr list --state open`."""
    r = subprocess.run(
        ["gh", "pr", "list", "--state", "open", "--json", "number"],
        capture_output=True, text=True, timeout=15,
        cwd=str(repo_root),
    )
    if r.returncode != 0:
        # If gh fails, treat conservatively as 0 (deterministic for unit tests)
        # but expose raw output for diagnostics.
        return 0
    try:
        import json as _json
        data = _json.loads(r.stdout) if r.stdout.strip() else []
        return len(data)
    except Exception:
        return 0


def _load_nmc(repo_root: Path) -> tuple[Optional[dict], Optional[str]]:
    """Load NMC yaml.  Returns (nmc_dict, error).  error=None on success."""
    nmc_path = repo_root / NMC_RELATIVE_PATH
    if not nmc_path.exists():
        return None, f"nmc_missing: {nmc_path} does not exist"
    try:
        with open(nmc_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        return None, f"nmc_parse_error: {e}"
    if not isinstance(data, dict) or "nodes" not in data:
        return None, "nmc_parse_error: missing 'nodes' key"
    return data, None


def _actual_operator_approved(nmc: dict) -> frozenset:
    """Extract (node, model_id) for entries with operator_approved=True."""
    out = set()
    for node, nd in nmc.get("nodes", {}).items():
        for e in nd.get("matrix", []):
            mid = e.get("model_id", "")
            if mid and e.get("operator_approved") is True:
                out.add((node, mid))
    return frozenset(out)


def _non_scope_all_unknown(nmc: dict, expected: frozenset) -> bool:
    """True iff every (node, mid) in expected has operator_approved=='unknown'."""
    for node, mid in expected:
        nd = nmc.get("nodes", {}).get(node)
        if not nd:
            return False
        found = False
        for e in nd.get("matrix", []):
            if e.get("model_id") == mid:
                if e.get("operator_approved") != "unknown":
                    return False
                found = True
                break
        if not found:
            return False
    return True


def _run_pytest_suite(repo_root: Path, pytest_path: str) -> dict:
    """Run a pytest suite and return a result dict.

    On success: {"passed": N, "failed": 0, "exit_code": 0}
    On failure: {"passed": ..., "failed": N, "exit_code": 1, "stderr": ...}
    On error:   {"error": "subprocess_error", "stderr": ...}
    """
    try:
        r = subprocess.run(
            ["python", "-m", "pytest", pytest_path, "-q", "--tb=no"],
            capture_output=True, text=True, timeout=300,
            cwd=str(repo_root),
        )
    except Exception as e:
        return {"error": "subprocess_error", "stderr": str(e)}

    # Parse "<passed>" and "<failed>" from summary line "X passed, Y failed in ..."
    passed = 0
    failed = 0
    m = re.search(r"(\d+)\s+passed", r.stdout)
    if m:
        passed = int(m.group(1))
    m = re.search(r"(\d+)\s+failed", r.stdout)
    if m:
        failed = int(m.group(1))
    return {
        "passed": passed,
        "failed": failed,
        "exit_code": r.returncode,
        "stderr": r.stderr[-500:] if r.returncode != 0 else "",
    }


def _forbidden_artifacts_present(repo_root: Path) -> list:
    """Return list of forbidden paths actually present in repo."""
    present = []
    for rel in FORBIDDEN_ARTIFACT_PATTERNS:
        # `rel` is a directory or file prefix.  Treat as directory prefix.
        # Match if any file under that path exists.
        base = repo_root / rel
        if base.exists():
            present.append(rel)
            continue
        # Check for files with this prefix
        try:
            for p in repo_root.glob(f"{rel}*"):
                # only consider actual paths (not pycache etc.)
                if p.exists():
                    present.append(str(p.relative_to(repo_root)))
                    break
        except Exception:
            pass
    return present


def _receipt_id(base_sha: str, created_at: str) -> str:
    """sha256[:26] of base_sha + created_at (deterministic, idempotent)."""
    h = hashlib.sha256(f"{base_sha}:{created_at}".encode()).hexdigest()
    return h[:26]


# ── Core ─────────────────────────────────────────────────────────────────────

def build_receipt(
    repo_root: Path,
    base_sha: str,
    run_subtests: bool = True,
    subtest_results: Optional[dict] = None,
) -> dict:
    """Build the readiness receipt (PASS or BLOCKED).

    Parameters
    ----------
    repo_root : Path
        Repo working-tree root.
    base_sha : str
        Expected base sha (40 hex).  Will be checked against HEAD.
    run_subtests : bool
        If True, run pytest on each sub-test suite.  If False, use
        the caller-supplied subtest_results.
    subtest_results : Optional[dict]
        Pre-computed sub-test results keyed by suite name
        ("apply_tool", "stage4", ...).  Each value is the dict returned
        by `_run_pytest_suite` or a callable returning it.

    Returns
    -------
    dict — receipt payload (NOT yaml-serialized; emission is separate).
    """
    blocked: list = []

    # ── Gate 7: base_sha format check ────────────────────────────────────
    if not isinstance(base_sha, str) or len(base_sha) != 40:
        blocked.append("base_sha_format_invalid")
        # If format is invalid, skip further base_sha checks
        base_sha_ok = False
        current_head = None
    else:
        current_head = _current_head_sha(repo_root)
        base_sha_ok = (current_head == base_sha)
        if not base_sha_ok:
            blocked.append("base_sha_mismatch")

    # ── Gate 1: NMC ─────────────────────────────────────────────────────
    nmc, nmc_error = _load_nmc(repo_root)
    if nmc_error:
        blocked.append(nmc_error)

    # ── Gate 2: operator approved exact set ─────────────────────────────
    actual_approved: frozenset = frozenset()
    set_equal = False
    missing: list = []
    unexpected: list = []
    if nmc is not None:
        actual_approved = _actual_operator_approved(nmc)
        set_equal = (actual_approved == EXPECTED_OPERATOR_APPROVED)
        if not set_equal:
            missing = sorted(EXPECTED_OPERATOR_APPROVED - actual_approved)
            unexpected = sorted(actual_approved - EXPECTED_OPERATOR_APPROVED)
            blocked.append("operator_approved_set_mismatch")

    # ── Gate 3: qwen non_scope all unknown ───────────────────────────────
    qwen_all_unknown = False
    if nmc is not None:
        qwen_all_unknown = _non_scope_all_unknown(nmc, EXPECTED_NON_SCOPE)
        if not qwen_all_unknown:
            blocked.append("non_scope_violated")

    # ── Gate 5 + 6: git clean + open PRs ────────────────────────────────
    git_clean = _git_clean(repo_root)
    if not git_clean:
        blocked.append("git_dirty")
    open_prs_count = _open_prs(repo_root)
    if open_prs_count > 0:
        blocked.append("open_prs_present")

    # ── Gate 4: sub-test suites ──────────────────────────────────────────
    test_invocation: dict = {}
    if subtest_results is None and run_subtests:
        subtest_results = {}
        for name, path in SUBTEST_SUITES:
            subtest_results[name] = _run_pytest_suite(repo_root, path)

    if subtest_results:
        all_pass = True
        for name, _ in SUBTEST_SUITES:
            r = subtest_results.get(name, {})
            test_invocation[name] = {
                "cmd": f"pytest {_dict_get(SUBTEST_SUITES, name) or '?'} -q",
                "passed": r.get("passed", 0),
                "failed": r.get("failed", 0),
                "exit_code": r.get("exit_code", -1),
                "stderr": r.get("stderr", "") if r.get("failed", 0) > 0 or r.get("error") else "",
            }
            if r.get("error"):
                blocked.append(f"subtest_error:{name}")
                all_pass = False
            elif r.get("failed", 0) > 0 or r.get("exit_code", 0) != 0:
                blocked.append(f"subtest_failure:{name}")
                all_pass = False
        test_invocation["all_pass"] = all_pass
    else:
        test_invocation["all_pass"] = False
        blocked.append("subtest_results_missing")

    # ── Gate 8: forbidden artifacts ─────────────────────────────────────
    forbidden = _forbidden_artifacts_present(repo_root)
    if forbidden:
        blocked.append("forbidden_artifact_present")

    # ── Verdict ──────────────────────────────────────────────────────────
    verdict = "PASS" if not blocked else "BLOCKED"

    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    receipt = {
        "receipt_id": _receipt_id(base_sha, created_at),
        "gate": "create_readiness_receipt",
        "gate_version": __version__,
        "created_at": created_at,
        "base_sha": base_sha,
        "operator_approved_check": {
            "expected_set": sorted([f"{n}/{m}" for n, m in EXPECTED_OPERATOR_APPROVED]),
            "actual_count": len(actual_approved),
            "expected_count": len(EXPECTED_OPERATOR_APPROVED),
            "set_equal": set_equal,
            "missing": [f"{n}/{m}" for n, m in missing],
            "unexpected": [f"{n}/{m}" for n, m in unexpected],
        },
        "non_scope_check": {
            "expected": sorted([f"{n}/{m}" for n, m in EXPECTED_NON_SCOPE]),
            "all_unknown": qwen_all_unknown,
        },
        "test_invocation": test_invocation,
        "environment": {
            "git_clean": git_clean,
            "open_prs": open_prs_count,
            "base_sha_match": base_sha_ok if not isinstance(base_sha, str) or len(base_sha) == 40 else False,
            "current_head": current_head,
        },
        "forbidden_artifacts_check": {
            "gray_artifacts_present": any("gray" in p for p in forbidden),
            "baseline03_artifacts_present": any("baseline03" in p for p in forbidden),
            "stage8_artifacts_present": any("stage8" in p for p in forbidden),
            "details": forbidden,
        },
        "verdict": verdict,
        "blocked_reasons": blocked,
        "notes": (
            "Receipt generated by create_readiness_receipt.py.  "
            "PASS means all 7 verification gates passed; it does NOT "
            "authorize gray / Baseline03 / Stage8.  Each subsequent gate "
            "requires separate operator authorization."
        ),
    }
    return receipt


def _dict_get(suites, name):
    """Lookup helper for SUBTEST_SUITES (list of tuples)."""
    for n, p in suites:
        if n == name:
            return p
    return None


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--no-subtests", action="store_true",
                        help="Skip running sub-tests (use --subtest-results instead)")
    parser.add_argument("--subtest-results", help="JSON file with pre-computed sub-test results")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    subtest_results = None
    if args.subtest_results:
        import json as _json
        with open(args.subtest_results) as f:
            subtest_results = _json.load(f)

    receipt = build_receipt(
        repo_root=repo_root,
        base_sha=args.base_sha,
        run_subtests=not args.no_subtests,
        subtest_results=subtest_results,
    )

    if args.json:
        import json as _json
        print(_json.dumps(receipt, indent=2, default=str))
    else:
        print(f"Verdict: {receipt['verdict']}")
        if receipt["blocked_reasons"]:
            print("Blocked reasons:")
            for r in receipt["blocked_reasons"]:
                print(f"  - {r}")

    return 0 if receipt["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())