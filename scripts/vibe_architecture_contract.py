"""vibe_architecture_contract.py — Architecture contract enforcement.

Validates worker transport, node topology, and SSH credential isolation
for the Vibe Coding cluster. Enforces:

- 21bao/vibedev = local-exec (no SSH credential needed)
- 5bao/9bao = ssh with username=vibeworker (never kk)
- SSH commands must come from registry/canonical resolver, not direct bypass
- No username=kk as default worker user
"""

import json
import sys
import os
from pathlib import Path

# Add scripts dir for imports
_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from vibe_worker_registry import WorkerRegistry, DEFAULT_WORKERS

# ── Hard topology facts ──────────────────────────────────────────────

EXPECTED_WORKERS = {
    "21bao": {
        "transport": "local-exec",
        "ssh_host": "",
        "ssh_port": 0,
        "ssh_user": "",
        "ssh_key_path": "",
        "node_type": "windows-worker",
        "note": "vibedev=21bao=orchestrator 本机, local-exec only",
    },
    "5bao": {
        "transport": "ssh",
        "ssh_host": "192.168.5.6",
        "ssh_port": 22222,
        "ssh_user": "vibeworker",
        "ssh_key_path": "",
        "node_type": "debian-worker",
        "note": "远程 worker, username MUST be vibeworker",
    },
    "9bao": {
        "transport": "ssh",
        "ssh_host": "192.168.9.6",
        "ssh_port": 22222,
        "ssh_user": "vibeworker",
        "ssh_key_path": "",
        "node_type": "debian-worker",
        "note": "远程 worker, username MUST be vibeworker",
    },
}

FORBIDDEN_USERNAMES = {"kk", "root", "admin", "administrator"}


# ── Validation functions ─────────────────────────────────────────────

def validate_worker_transport(worker_id: str, w) -> dict:
    """Validate a single worker's transport configuration.

    Returns {"passed": bool, "errors": [str]}.
    """
    errors = []
    expected = EXPECTED_WORKERS.get(worker_id)
    if not expected:
        return {"worker_id": worker_id, "passed": True,
                "errors": [], "warnings": [f"unknown worker {worker_id}"]}

    # Check transport
    actual_transport = getattr(w, "transport", None)
    expected_transport = expected["transport"]
    if actual_transport != expected_transport:
        errors.append(
            f"transport mismatch: expected '{expected_transport}', got '{actual_transport}'")

    # Check SSH fields
    if expected_transport == "local-exec":
        # local-exec must have empty SSH fields
        for field in ["ssh_host", "ssh_port", "ssh_user", "ssh_key_path"]:
            val = getattr(w, field, None)
            if field == "ssh_port":
                if val != 0:
                    errors.append(f"{field}: expected 0 for local-exec, got {val}")
            elif val:
                errors.append(f"{field}: expected empty for local-exec, got '{val}'")
    elif expected_transport == "ssh":
        # ssh workers must have host, port, user
        if not getattr(w, "ssh_host", None):
            errors.append("ssh_host is empty for ssh worker")
        if not getattr(w, "ssh_port", None):
            errors.append("ssh_port is 0 for ssh worker")
        ssh_user = getattr(w, "ssh_user", None)
        if not ssh_user:
            errors.append("ssh_user is empty for ssh worker")
        elif ssh_user.lower() in FORBIDDEN_USERNAMES:
            errors.append(
                f"ssh_user '{ssh_user}' is forbidden. "
                f"Must use '{expected['ssh_user']}' per registry.")

    return {
        "worker_id": worker_id,
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": [],
    }


def validate_all_workers() -> dict:
    """Validate all workers in the default registry."""
    reg = WorkerRegistry()
    results = {}
    all_passed = True
    for wid, w in reg.workers.items():
        result = validate_worker_transport(wid, w)
        results[wid] = result
        if not result["passed"]:
            all_passed = False
    return {
        "passed": all_passed,
        "worker_count": len(results),
        "workers": results,
    }


def validate_worker_count() -> dict:
    """Validate exactly 3 workers: 21bao, 5bao, 9bao."""
    reg = WorkerRegistry()
    expected_ids = {"21bao", "5bao", "9bao"}
    actual_ids = set(reg.workers.keys())
    missing = expected_ids - actual_ids
    extra = actual_ids - expected_ids
    errors = []
    if missing:
        errors.append(f"missing workers: {missing}")
    if extra:
        errors.append(f"unexpected workers: {extra}")
    return {
        "passed": len(errors) == 0,
        "expected_count": 3,
        "actual_count": len(reg.workers),
        "expected_ids": sorted(expected_ids),
        "actual_ids": sorted(actual_ids),
        "errors": errors,
    }


def validate_no_ssh_bypass() -> dict:
    """Check that no code path uses hardcoded ssh with username=kk."""
    import re
    scripts_dir = _SCRIPTS_DIR
    issues = []
    for py_file in scripts_dir.glob("*.py"):
        # Skip self-check (this file contains the detection patterns)
        if py_file.name == "vibe_architecture_contract.py":
            continue
        content = py_file.read_text(encoding="utf-8", errors="replace")
        # Look for patterns like "kk@" or "ssh_user.*kk" or "username.*kk"
        for lineno, line in enumerate(content.split("\n"), 1):
            if "kk@" in line and ("ssh" in line.lower() or "192.168" in line):
                issues.append({
                    "file": py_file.name,
                    "line": lineno,
                    "text": line.strip()[:80],
                    "severity": "error",
                })
            if re.search(r'ssh_user["\']?\s*[:=]\s*["\']?kk["\']?', line):
                issues.append({
                    "file": py_file.name,
                    "line": lineno,
                    "text": line.strip()[:80],
                    "severity": "error",
                })
    return {
        "passed": len(issues) == 0,
        "ssh_bypass_issues": issues,
    }


def self_check() -> dict:
    """Run all architecture contract checks."""
    checks = []

    # Check 1: Worker count
    count_result = validate_worker_count()
    checks.append({
        "name": "worker_count",
        "passed": count_result["passed"],
        "detail": f"expected=3, actual={count_result['actual_count']}",
    })

    # Check 2: Transport validation
    transport_result = validate_all_workers()
    for wid, w_result in transport_result["workers"].items():
        checks.append({
            "name": f"transport_{wid}",
            "passed": w_result["passed"],
            "detail": f"transport={getattr(DEFAULT_WORKERS.get(wid), 'transport', '?')}, "
                      f"errors={w_result['errors']}",
        })

    # Check 3: No SSH bypass
    bypass_result = validate_no_ssh_bypass()
    checks.append({
        "name": "no_ssh_bypass",
        "passed": bypass_result["passed"],
        "detail": f"issues={len(bypass_result['ssh_bypass_issues'])}",
    })

    # Check 4: 21bao has no SSH credential
    w21 = DEFAULT_WORKERS.get("21bao")
    if w21:
        has_ssh = bool(getattr(w21, "ssh_host", None) or
                       getattr(w21, "ssh_user", None) or
                       getattr(w21, "ssh_key_path", None))
        checks.append({
            "name": "21bao_no_ssh_credential",
            "passed": not has_ssh,
            "detail": f"ssh_host='{getattr(w21, 'ssh_host', '')}', "
                      f"ssh_user='{getattr(w21, 'ssh_user', '')}'",
        })

    # Check 5: 5bao/9bao have correct username
    for wid in ["5bao", "9bao"]:
        w = DEFAULT_WORKERS.get(wid)
        if w:
            user = getattr(w, "ssh_user", "")
            checks.append({
                "name": f"{wid}_username_vibeworker",
                "passed": user == "vibeworker",
                "detail": f"ssh_user='{user}'",
            })

    all_passed = all(c["passed"] for c in checks)
    return {
        "passed": all_passed,
        "version": "1.0.0",
        "checks": checks,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="VibeDev Architecture Contract Validator")
    parser.add_argument("--self-check", action="store_true",
                        help="Run all architecture contract checks")
    parser.add_argument("--json", action="store_true",
                        help="JSON output")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Architecture Contract: {'PASS' if result['passed'] else 'FAIL'}")
            for c in result["checks"]:
                status = "✅" if c["passed"] else "❌"
                print(f"  {status} {c['name']}: {c['detail']}")
        sys.exit(0 if result["passed"] else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
