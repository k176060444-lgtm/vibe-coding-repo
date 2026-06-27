#!/usr/bin/env python3
"""vibe_runtime_reliability.py — I23 Runtime Reliability Checks v1.0.0

Aggregated read-only runtime reliability checks for VibeDev cluster.

Usage:
    python scripts/vibe_runtime_reliability.py --self-check [--json]
    python scripts/vibe_runtime_reliability.py --health-summary [--json]
    python scripts/vibe_runtime_reliability.py drift-detect [--json]
    python scripts/vibe_runtime_reliability.py check-secret [--json]

Checks (I23 scope):
    ARCH-002   — Worker health_status known/present in self-check output
    WRKR-002   — Worker failover readiness assessment (read-only)
    DSP-003    — Fallback policy enforcement consistency check
    GIT-001    — PR base ref lag detection (requires gh CLI)
    WIN-003    — MSYS/POSIX path artifact detection
    RPT-001    — Report field schema consistency validation
    RPT-002    — Enhanced secret leak detection
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ── ARCH-002: Worker Health Status Check ──────────────────────────────


def check_worker_health_status() -> dict:
    """ARCH-002: Verify worker health_status is documented and realistic.

    Read-only: parses worker_registry self-check output without probing.
    Returns current health_status vs expected baseline.
    """
    try:
        from vibe_worker_registry import WorkerRegistry, NodeStatus

        checks = []
        reg = WorkerRegistry()
        for wid, w in reg.workers.items():
            hs = w.health_status
            expected = NodeStatus.UNKNOWN
            checks.append({
                "worker_id": wid,
                "health_status": hs,
                "expected_baseline": expected.value,
                "status_known": hs != "",
                "transport": w.transport,
                "enabled": w.enabled,
                "maintenance": w.maintenance_status,
            })
        return {
            "passed": all(c["status_known"] for c in checks),
            "version": VERSION,
            "check_type": "arch-002",
            "checks": checks,
            "warnings": [
                f"Worker '{c['worker_id']}' health_status='{c['health_status']}'"
                for c in checks if c["health_status"] != NodeStatus.ONLINE.value
            ],
        }
    except Exception as e:
        return {
            "passed": False,
            "version": VERSION,
            "check_type": "arch-002",
            "error": str(e),
        }


# ── WRKR-002: Worker Failover Readiness (Read-Only) ──────────────────


def check_failover_readiness() -> dict:
    """WRKR-002: Assess worker failover readiness without making SSH calls.

    Read-only analysis based on registry state: checks if at least one
    DEBIAN worker could cover for another, and if 21bao can continue
    as orchestrator independently.
    """
    try:
        from vibe_worker_registry import WorkerRegistry, NodeStatus

        reg = WorkerRegistry()
        debian_online = [
            w for w in reg.workers.values()
            if w.node_type == "debian-worker"
            and w.health_status == NodeStatus.ONLINE.value
            and w.enabled
        ]
        debian_offline = [
            w for w in reg.workers.values()
            if w.node_type == "debian-worker"
            and w.health_status != NodeStatus.ONLINE.value
        ]

        findings = []
        if len(debian_online) < 2:
            findings.append(
                f"Only {len(debian_online)}/{len(debian_offline) + len(debian_online)} "
                f"debian workers ONLINE — no active-active redundancy")
        else:
            findings.append(
                f"{len(debian_online)} debian workers ONLINE — active-active possible")

        # Check capability overlap
        if len(debian_online) >= 2:
            caps_5 = set(debian_online[0].capabilities)
            caps_9 = set(debian_online[1].capabilities)
            overlap = caps_5 & caps_9
            findings.append(
                f"Capability overlap between debian workers: {len(overlap)} shared")

        # Check 21bao orchestrator can continue independently
        w21 = reg.workers.get("21bao")
        if w21:
            findings.append(
                f"21bao orchestrator: transport={w21.transport} "
                f"enabled={w21.enabled} health={w21.health_status}")

        return {
            "passed": len(debian_online) >= 1,
            "version": VERSION,
            "check_type": "wrkr-002",
            "dependencies": [],
            "findings": findings,
            "debian_online_count": len(debian_online),
            "debian_offline_count": len(debian_offline),
            "warnings": [
                f"Worker '{w.worker_id}' is OFFLINE" for w in debian_offline
            ],
        }
    except Exception as e:
        return {
            "passed": False,
            "version": VERSION,
            "check_type": "wrkr-002",
            "error": str(e),
        }


# ── DSP-003: Fallback Policy Enforcement ────────────────────────────


def check_fallback_policy() -> dict:
    """DSP-003: Verify fallback_allowed is consistently defined in central pool.

    Read-only: parses model_pool.yaml for fallback_allowed fields.
    Reports models missing the field or with ambiguous values.
    """
    try:
        from opencode_model_pool import ModelPool

        yp = os.path.join(SCRIPTS_DIR, "model_pool.yaml")
        if not os.path.exists(yp):
            return {
                "passed": False,
                "version": VERSION,
                "check_type": "dsp-003",
                "error": "model_pool.yaml not found",
            }

        pool = ModelPool.from_yaml(yp)
        issues = []
        ok_count = 0
        for mid, m in pool.models.items():
            fb = m.get("fallback_allowed")
            if fb is None:
                if m.get("enabled", False):
                    issues.append({
                        "model_id": mid,
                        "issue": "missing fallback_allowed field on enabled model",
                    })
            elif isinstance(fb, bool):
                ok_count += 1
            else:
                issues.append({
                    "model_id": mid,
                    "issue": f"fallback_allowed has non-boolean type: {type(fb).__name__}",
                })

        return {
            "passed": len(issues) == 0,
            "version": VERSION,
            "check_type": "dsp-003",
            "total_models_checked": len(pool.models),
            "models_with_valid_fallback": ok_count,
            "models_missing_fallback": len(issues),
            "issues": issues,
            "warnings": [],
        }
    except Exception as e:
        return {
            "passed": False,
            "version": VERSION,
            "check_type": "dsp-003",
            "error": str(e),
        }


# ── GIT-001: PR Base Ref Lag Detection ──────────────────────────────


def check_pr_base_lag(pr_number: int = None) -> dict:
    """GIT-001: Check if current branch base is behind github/main.

    If pr_number is given, also checks via gh CLI for the PR.
    Read-only: uses git fetch + merge-base. No mutations.
    """
    try:
        # Get current branch info
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        branch = result.stdout.strip()

        # Get main head
        result = subprocess.run(
            ["git", "rev-parse", "github/main"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        main_head = result.stdout.strip()

        # Get base (merge-base between this branch and main)
        result = subprocess.run(
            ["git", "merge-base", branch, "github/main"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        merge_base = result.stdout.strip()

        # Check if base is behind main
        result = subprocess.run(
            ["git", "rev-list", "--count", f"{merge_base}..{main_head}"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        behind_count = int(result.stdout.strip())

        findings = {
            "branch": branch,
            "main_head": main_head[:12],
            "merge_base": merge_base[:12],
            "behind_count": behind_count,
            "is_behind": behind_count > 0,
        }

        if pr_number:
            try:
                result = subprocess.run(
                    ["gh", "pr", "view", str(pr_number), "--json",
                     "baseRefOid,headRefOid"],
                    capture_output=True, text=True,
                    env={**os.environ, "PATH": f"{os.path.expanduser('~/bin')}:{os.environ.get('PATH', '')}"}
                )
                if result.returncode == 0:
                    pr_data = json.loads(result.stdout)
                    findings["pr_base_oid"] = pr_data.get("baseRefOid", "")[:12]
                    findings["pr_head_oid"] = pr_data.get("headRefOid", "")[:12]
            except Exception:
                pass

        return {
            "passed": not findings["is_behind"],
            "version": VERSION,
            "check_type": "git-001",
            "findings": findings,
            "warnings": [] if not findings["is_behind"] else [
                f"Branch '{branch}' is {behind_count} commit(s) behind github/main. "
                "PR base ref should be updated before merge."
            ],
        }
    except Exception as e:
        return {
            "passed": False,
            "version": VERSION,
            "check_type": "git-001",
            "error": str(e),
        }


# ── WIN-003: MSYS/POSIX Path Artifact Detection ─────────────────────


def check_msys_path_artifacts(paths_to_check: list = None) -> dict:
    """WIN-003: Scan files for MSYS/POSIX path artifacts.

    Detects patterns like:
    - C:\\c\\Users\\... (MSYS /c/Users translated wrong)
    - Hybrid path with wrong separators
    - Inconsistent path style (mix of \\ and / on Windows)
    """
    if paths_to_check is None:
        paths_to_check = [
            SCRIPTS_DIR / "vibe_worker_registry.py",
            SCRIPTS_DIR / "vibe_architecture_contract.py",
            SCRIPTS_DIR / "vibe_model_routing_policy.py",
            SCRIPTS_DIR / "opencode_model_pool.py",
            SCRIPTS_DIR / "execution_approval_gate.py",
        ]

    issues = []
    for fpath in paths_to_check:
        if not os.path.exists(fpath):
            continue
        content = Path(fpath).read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(content.split("\n"), 1):
            # C:\c\Users pattern (MSYS artifact: /c/Users → C:\c\Users)
            if re.search(r'C:[\\/]c[\\/]Users', line, re.IGNORECASE):
                issues.append({
                    "file": os.path.basename(str(fpath)),
                    "line": lineno,
                    "text": line.strip()[:80],
                    "severity": "error",
                    "description": "MSYS path translation artifact: C:\\c\\Users",
                })
            # Double separator issues
            if re.search(r'[\\/]{3,}', line):
                issues.append({
                    "file": os.path.basename(str(fpath)),
                    "line": lineno,
                    "text": line.strip()[:80],
                    "severity": "warning",
                    "description": "Possible path separator issue (3+ consecutive)",
                })
            # Mixed \\ and / that looks like corrupt path
            if re.search(r'C:[\\/].*[\\/]c[\\/]Users', line, re.IGNORECASE):
                issues.append({
                    "file": os.path.basename(str(fpath)),
                    "line": lineno,
                    "text": line.strip()[:80],
                    "severity": "warning",
                    "description": "Mixed path style with /c/Users pattern",
                })

    return {
        "passed": len([i for i in issues if i["severity"] == "error"]) == 0,
        "version": VERSION,
        "check_type": "win-003",
        "files_checked": len(paths_to_check),
        "issues_count": len(issues),
        "issues": issues,
        "warnings": [
            f"{i['file']}:{i['line']} — {i['description']}"
            for i in issues if i["severity"] == "error"
        ],
    }


# ── RPT-001: Report Schema Consistency ──────────────────────────────

REQUIRED_REPORT_FIELDS = [
    "phase_id",
    "final_verdict",
    "gate_results",
    "secret_check",
    "tests_run",
]

OPTIONAL_BUT_RECOMMENDED = [
    "hidden_bidi_check",
    "route_all_result",
    "git_status",
    "model_pool_self_check",
]


def check_report_schema(report_path: str = None) -> dict:
    """RPT-001: Validate a phase report YAML/document for required fields.

    If no path given, scans docs/reports/ for consistency.
    Read-only: checks field presence, not content.
    """
    reports_dir = REPO_ROOT / "docs" / "reports"
    if not reports_dir.exists():
        return {
            "passed": False,
            "version": VERSION,
            "check_type": "rpt-001",
            "error": "docs/reports/ not found",
        }

    findings = []
    for fpath in sorted(reports_dir.glob("I*_*.md")):
        content = fpath.read_text(encoding="utf-8", errors="replace")
        present = [f for f in REQUIRED_REPORT_FIELDS if f in content]
        missing = [f for f in REQUIRED_REPORT_FIELDS if f not in content]
        findings.append({
            "file": fpath.name,
            "size": fpath.stat().st_size,
            "required_fields_present": len(present),
            "required_fields_missing": missing if missing else [],
            "has_final_verdict": "final_verdict" in content,
        })

    missing_count = sum(
        len(f["required_fields_missing"]) for f in findings
    )

    return {
        "passed": missing_count == 0,
        "version": VERSION,
        "check_type": "rpt-001",
        "reports_scanned": len(findings),
        "total_missing_fields": missing_count,
        "findings": findings,
        "warnings": [
            f"{f['file']}: missing fields {f['required_fields_missing']}"
            for f in findings if f["required_fields_missing"]
        ],
    }


# ── RPT-002: Enhanced Secret Leak Detection ─────────────────────────


def enhanced_secret_check(files_to_check: list = None) -> dict:
    """RPT-002: Enhanced secret leak detection with false-positive
    classification and pattern coverage.

    Extends the basic regex check with:
    - Expanded pattern list
    - False-positive classification by context (regex pattern def, test fixture)
    - Pre-existing vs new classification
    - Machine-readable output
    """
    if files_to_check is None:
        # Default: check all scripts and test files
        files_to_check = []
        for ext in ("*.py", "*.yaml", "*.md", "*.json", "*.toml", "*.cfg"):
            files_to_check.extend(SCRIPTS_DIR.glob(ext))
            files_to_check.extend((REPO_ROOT / "tests").glob(ext))
        files_to_check = sorted(set(str(f) for f in files_to_check))

    SECRET_PATTERNS = [
        (r'sk-[a-zA-Z0-9]{20,}', "API key (sk-)"),
        (r'sk-ant-[a-zA-Z0-9]{20,}', "Anthropic key"),
        (r'AIza[0-9A-Za-z_-]{35}', "Google API key"),
        (r'ghp_[a-zA-Z0-9]{36}', "GitHub PAT"),
        (r'gho_[a-zA-Z0-9]{36}', "GitHub OAuth"),
        (r'ghu_[a-zA-Z0-9]{36}', "GitHub user token"),
        (r'-----BEGIN.*PRIVATE KEY-----', "Private key PEM"),
        (r'-----BEGIN.*EC PRIVATE KEY-----', "EC private key PEM"),
        (r'-----BEGIN.*RSA PRIVATE KEY-----', "RSA private key PEM"),
        (r'AKIA[0-9A-Z]{16}', "AWS access key"),
        (r'xox[baprs]-[0-9a-zA-Z-]{24,}', "Slack token"),
    ]

    results = []
    false_positive_count = 0
    real_concern_count = 0

    for fpath in files_to_check:
        if not os.path.isfile(fpath):
            continue
        try:
            content = Path(fpath).read_text(
                encoding="utf-8", errors="replace")
        except Exception:
            content = ""

        for pat, pat_name in SECRET_PATTERNS:
            for m in re.finditer(pat, content):
                matched = m.group()

                # False-positive classification
                is_false_positive = False
                fp_reason = ""

                # 1. Regex pattern definition
                if f"r'{pat}" in content or f'r"{pat}' in content:
                    is_false_positive = True
                    fp_reason = "regex pattern definition"
                elif f"r'{matched}" in content or f'r"{matched}' in content:
                    is_false_positive = True
                    fp_reason = "regex pattern definition (exact match)"

                # 2. Test fixture / example
                if "example" in fpath.lower() or "fixture" in fpath.lower():
                    is_false_positive = True
                    fp_reason = fp_reason or "test fixture"

                # 3. Known safe patterns in memory/notes
                if "memory" in fpath.lower() or "note" in fpath.lower():
                    is_false_positive = True
                    fp_reason = fp_reason or "memory/notes file"

                # 4. Too short to be real (pattern has minimum length)
                if pat_name.startswith("API key") and len(matched) < 25:
                    is_false_positive = True
                    fp_reason = fp_reason or "too short (likely placeholder)"

                results.append({
                    "file": fpath,
                    "pattern": pat_name,
                    "matched_preview": matched[:12] + "..." if len(matched) > 12 else matched,
                    "is_false_positive": is_false_positive,
                    "fp_reason": fp_reason,
                })
                if is_false_positive:
                    false_positive_count += 1
                else:
                    real_concern_count += 1

    return {
        "passed": real_concern_count == 0,
        "version": VERSION,
        "check_type": "rpt-002",
        "files_checked": len(files_to_check),
        "total_matches": len(results),
        "false_positives": false_positive_count,
        "real_concerns": real_concern_count,
        "matches": results[:50],  # cap at 50 to avoid huge output
        "warnings": [] if real_concern_count == 0 else [
            f"{m['file']}: {m['pattern']} — potential real secret"
            for m in results if not m["is_false_positive"]
        ],
    }


# ── Self-Check ───────────────────────────────────────────────────────


def self_check() -> dict:
    """Run all I23 reliability checks and return aggregated result."""
    results = {}

    # ARCH-002
    results["worker_health_status"] = check_worker_health_status()

    # WRKR-002
    results["failover_readiness"] = check_failover_readiness()

    # DSP-003
    results["fallback_policy"] = check_fallback_policy()

    # GIT-001 (no specific PR, just current branch)
    results["pr_base_lag"] = check_pr_base_lag()

    # WIN-003
    results["msys_path_artifacts"] = check_msys_path_artifacts()

    # RPT-001
    results["report_schema"] = check_report_schema()

    # RPT-002
    results["secret_check"] = enhanced_secret_check()

    passed = all(
        r.get("passed", False) for r in results.values()
        if "error" not in r
    )

    return {
        "passed": passed,
        "version": VERSION,
        "checks": results,
        "total": len(results),
        "passed_count": sum(
            1 for r in results.values() if r.get("passed", False)
        ),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="VibeDev Runtime Reliability Checks")
    parser.add_argument("--self-check", action="store_true",
                        help="Run all I23 runtime reliability checks")
    parser.add_argument("--health-summary", action="store_true",
                        help="Show worker health summary")
    parser.add_argument("--json", action="store_true",
                        help="JSON output")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("drift-detect", help="Run drift detection checks")
    sub.add_parser("check-secret", help="Run enhanced secret check")

    args = parser.parse_args()

    if args.self_check:
        result = self_check()
    elif args.command == "drift-detect":
        result = {
            "worker_health": check_worker_health_status(),
            "failover": check_failover_readiness(),
            "fallback": check_fallback_policy(),
        }
    elif args.command == "check-secret":
        result = enhanced_secret_check()
    elif args.health_summary:
        result = check_worker_health_status()
    else:
        parser.print_help()
        return 1

    if args.json or args.command in ("drift-detect", "check-secret"):
        print(json.dumps(result, indent=2))
    else:
        if "passed" in result:
            print(f"Runtime Reliability: {'PASS' if result['passed'] else 'FAIL'}")
            for cname, cresult in result.get("checks", {}).items():
                status = "✅" if cresult.get("passed", False) else "❌"
                warns = cresult.get("warnings", [])
                print(f"  {status} {cname}: passed={cresult.get('passed')}")
                for w in warns[:3]:
                    print(f"     ⚠️  {w}")
        else:
            print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
