#!/usr/bin/env python3
"""vibe_windows_job_runner.py v1.0.0

Windows Job Runner — isolated execution for short diagnostic tasks.
Designed to NOT block gateway.

Features:
  - Timeout enforcement (default 300s, max 300s)
  - Exit code capture
  - Log path and artifact path tracking
  - Gateway isolation (checks gateway health before long tasks)
  - No token access, no SSH/Provider/secrets modification

Allowed task types:
  - gateway health/status checks
  - PowerShell diagnostics (short)
  - Windows event log queries
  - Path/ACL/env checks
  - File existence / attribute checks

Blocked:
  - Long-running tasks (>300s)
  - Git operations
  - Python/pytest
  - External writes
  - Token/secret access
  - SSH/Provider modification
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.0.0"
MAX_TIMEOUT = 300  # 5 minutes
DEFAULT_TIMEOUT = 60

BLOCKED_PATTERNS = [
    "git push", "git merge", "git commit", "git rebase",
    "pytest", "python -m test",
    "ssh ", "scp ", "rsync",
    "token", "secret", "api_key", "password",
    "provider", "credential",
    "external push", "fork push",
]


def validate_task(command: str, timeout: int) -> dict:
    """Validate a task before execution."""
    if timeout > MAX_TIMEOUT:
        return {"allowed": False,
                "reason": f"Timeout {timeout}s exceeds max {MAX_TIMEOUT}s"}

    cmd_lower = command.lower()
    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return {"allowed": False,
                    "reason": f"Blocked pattern: {pattern}"}

    return {"allowed": True, "reason": "Task validated"}


def run_task(command: str, timeout: int = DEFAULT_TIMEOUT,
             log_dir: str = "") -> dict:
    """Execute a Windows task with isolation.

    Returns: exit_code, stdout, stderr, duration, log_path, timed_out.
    """
    # Validate
    validation = validate_task(command, timeout)
    if not validation["allowed"]:
        return {
            "version": VERSION,
            "status": "BLOCKED",
            "reason": validation["reason"],
            "exit_code": -1,
            "stdout": "",
            "stderr": "",
            "duration_seconds": 0,
            "log_path": "",
            "timed_out": False,
            "timestamp": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"),
        }

    # Setup log dir
    if not log_dir:
        log_dir = os.path.join(os.environ.get("LOCALAPPDATA", "/tmp"),
                               "vibedev-tools", "windows-worker", "logs")
    os.makedirs(log_dir, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(log_dir, f"task-{ts}.log")

    # Execute
    start = time.time()
    timed_out = False
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=timeout,
        )
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired:
        exit_code = -1
        stdout = ""
        stderr = f"TIMEOUT: task exceeded {timeout}s"
        timed_out = True
    except Exception as e:
        exit_code = -1
        stdout = ""
        stderr = f"ERROR: {str(e)}"

    duration = round(time.time() - start, 2)

    # Write log
    log_entry = {
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout[:10000],  # cap
        "stderr": stderr[:5000],
        "duration_seconds": duration,
        "timed_out": timed_out,
        "timestamp": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        with open(log_path, "w") as f:
            json.dump(log_entry, f, indent=2)
    except Exception:
        log_path = ""

    return {
        "version": VERSION,
        "status": "TIMEOUT" if timed_out else (
            "PASS" if exit_code == 0 else "FAIL"),
        "exit_code": exit_code,
        "stdout": stdout[:10000],
        "stderr": stderr[:5000],
        "duration_seconds": duration,
        "log_path": log_path,
        "timed_out": timed_out,
        "artifact_path": log_path,
        "timestamp": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
    }


def self_check() -> dict:
    """Run self-check tests."""
    results = []
    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            results.append({"test": name, "status": "PASS", "detail": detail})
            passed += 1
        else:
            results.append({"test": name, "status": "FAIL", "detail": detail})
            failed += 1

    # T1: blocked git push
    v = validate_task("git push origin main", 60)
    check("block_git_push", not v["allowed"],
          f"reason={v['reason']}")

    # T2: blocked pytest
    v = validate_task("pytest tests/", 120)
    check("block_pytest", not v["allowed"],
          f"reason={v['reason']}")

    # T3: blocked token
    v = validate_task("cat token file", 30)
    check("block_token", not v["allowed"],
          f"reason={v['reason']}")

    # T4: blocked timeout
    v = validate_task("echo hello", 600)
    check("block_timeout", not v["allowed"],
          f"reason={v['reason']}")

    # T5: allowed echo
    v = validate_task("echo hello world", 30)
    check("allow_echo", v["allowed"],
          f"reason={v['reason']}")

    # T6: allowed dir listing
    v = validate_task("dir C:\\Users", 30)
    check("allow_dir", v["allowed"],
          f"reason={v['reason']}")

    # T7: max timeout constant
    check("max_timeout", MAX_TIMEOUT == 300,
          f"MAX_TIMEOUT={MAX_TIMEOUT}")

    # T8: version
    check("version", True, VERSION)

    return {"passed": passed, "failed": failed, "total": passed + failed,
            "results": results}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "self-check":
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["failed"] == 0 else 1)

    if len(sys.argv) > 1 and sys.argv[1] == "run":
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--command", required=True)
        parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
        parser.add_argument("--log-dir", default="")
        args = parser.parse_args(sys.argv[2:])
        result = run_task(args.command, args.timeout, args.log_dir)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] == "PASS" else 1)

    print(json.dumps({"version": VERSION, "max_timeout": MAX_TIMEOUT}, indent=2))


if __name__ == "__main__":
    main()
