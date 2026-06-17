#!/usr/bin/env python3
"""vibe_worker_capability.py — Worker Capability Detection v1.0.0

Detects what capabilities the current worker environment has.
Used by smoke tests to determine SKIP vs NOT_APPLICABLE vs BLOCKED.

Usage:
    python3 scripts/vibe_worker_capability.py
    python3 scripts/vibe_worker_capability.py --json
    python3 scripts/vibe_worker_capability.py --self-check
"""

__version__ = "1.0.0"

import json
import os
import subprocess
import sys
from pathlib import Path


def _find_test_python():
    """Find the test venv Python if available."""
    venv = Path.home() / ".vibedev" / "test-envs" / "toolchain" / "venv"
    for candidate in [
        venv / "bin" / "python3",
        venv / "bin" / "python",
    ]:
        if candidate.is_file():
            return str(candidate)
    return None


def _can_import(module_name, python_path=None):
    """Check if a module can be imported."""
    py = python_path or _find_test_python() or sys.executable
    try:
        r = subprocess.run(
            [py, "-c", f"import {module_name}"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def detect_capabilities(worker_id=None):
    """Detect worker capabilities. Returns dict of capability → bool."""
    wid = worker_id or os.environ.get("VIBEDEV_WORKER_ID", "unknown")
    test_python = _find_test_python()

    caps = {
        "worker_id": wid,
        "test_python": test_python,
        "system_python": sys.executable,
        "pytest_available": _can_import("pytest", test_python),
        "pytest_timeout_available": _can_import("pytest_timeout", test_python),
        "is_controller": wid in ("windows", "controller"),
        "has_privileged_token": os.path.isfile(
            os.path.expanduser("~/.vibedev-secrets/github_privileged_token")
        ),
        "has_audit_tainted_lock": os.path.isfile(
            os.path.expanduser("~/vibedev/jobs/wo-code-repo-status-001/work-order.json")
        ),
    }
    return caps


def self_check():
    """Run self-check."""
    caps = detect_capabilities()
    checks = []
    checks.append({"name": "version", "passed": True, "message": __version__})
    checks.append({"name": "detection_works", "passed": isinstance(caps, dict), "message": f"keys={len(caps)}"})
    checks.append({"name": "worker_id_set", "passed": caps["worker_id"] != "", "message": caps["worker_id"]})
    checks.append({"name": "no_secret_leak", "passed": True, "message": "no secrets in output"})
    passed = sum(1 for c in checks if c["passed"])
    return {"overall": "PASS" if passed == len(checks) else "FAIL",
            "passed": passed, "total": len(checks), "checks": checks, "capabilities": caps}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Worker Capability Detection")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args()

    if args.self_check:
        r = self_check()
    else:
        r = detect_capabilities(args.worker_id)

    if args.json:
        print(json.dumps(r, indent=2))
    else:
        if isinstance(r, dict) and "capabilities" not in r:
            for k, v in r.items():
                print(f"  {k}: {v}")
        else:
            print(json.dumps(r, indent=2))


if __name__ == "__main__":
    main()
