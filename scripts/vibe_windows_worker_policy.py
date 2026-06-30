#!/usr/bin/env python3
"""vibe_windows_worker_policy.py v1.0.0

Windows Worker Lane policy. Classifies tasks as suitable for Windows
execution vs must-Debian, with gateway isolation rules.

NOTE (baseline01): This module is a node/task classifier only. Its
`requires_approval` return value is informational legacy metadata.
Production approval enforcement must come from baseline01 operator gates
(vibe_task_intake.py, git_pr_approval_gate.py, vibe_batch_runner.py), not
from this classifier. Callers must not treat classifier output as
authorization.

Windows suitable:
  - gateway health / status / reconnect
  - Windows scheduled tasks (Task Scheduler)
  - PowerShell scripts / diagnostics
  - Windows event logs
  - Path / ACL / env checks
  - .NET / BAT / Office / VBA
  - GUI / local software diagnostics

Windows NOT suitable (default Debian):
  - full smoke / pytest / git operations
  - PR create / merge / push
  - long-running builds
  - external protected writes
  - anything needing Linux tools

Gateway isolation:
  - Windows worker tasks MUST NOT block gateway
  - Max task duration: 300s (5 min) for worker tasks
  - Gateway health checks: 30s max
"""

import json
import sys
from datetime import datetime, timezone

VERSION = "1.0.0"

# ── Task Classification ──────────────────────────────────────────

WINDOWS_SUITABLE_PATTERNS = {
    "gateway": [
        r"gateway.?health", r"gateway.?status", r"gateway.?reconnect",
        r"gateway.?restart", r"gateway.?log", r"qqbot",
    ],
    "scheduled_task": [
        r"task.?scheduler", r"scheduled.?task", r"cron.*windows",
        r"windows.*cron",
    ],
    "powershell": [
        r"powershell", r"pwsh", r"ps1", r"get-.*item", r"set-.*item",
        r"invoke-.*command", r"new-.*object",
    ],
    "windows_logs": [
        r"event.?log", r"windows.?log", r"get-winevent",
        r"application.?log", r"system.?log",
    ],
    "path_acl_env": [
        r"windows.?path", r"acl", r"ntfs.*permission",
        r"env:.*", r"registry", r"hklm", r"hkcu",
    ],
    "dotnet_bat": [
        r"\.net", r"dotnet", r"batch.?file", r"\.bat", r"\.cmd",
    ],
    "office_vba": [
        r"office", r"vba", r"excel", r"word", r"outlook", r"com.?object",
    ],
    "gui_local": [
        r"gui", r"desktop", r"local.?software", r"installed.?app",
        r"add.?remove.?program",
    ],
}

DEBIAN_REQUIRED_PATTERNS = {
    "git_operations": [
        r"git\s+(push|merge|commit|rebase|branch)", r"pr\s+create",
        r"pr\s+merge", r"pull.?request",
    ],
    "pytest_testing": [
        r"pytest", r"python.*-m.*test", r"full.?smoke", r"smoke.?suite",
        r"quality.?gate", r"freeze.?check",
    ],
    "long_builds": [
        r"build.*full", r"compile.*all", r"npm.*install", r"pip.*install",
    ],
    "external_write": [
        r"external.*push", r"protected.*write", r"fork.*push",
    ],
    "linux_tools": [
        r"ssh.*debian", r"scp", r"rsync", r"apt.?get", r"systemctl",
    ],
}

GATEWAY_ISOLATION = {
    "max_worker_task_seconds": 300,
    "max_gateway_health_seconds": 30,
    "blocked_during_gateway_restart": True,
    "requires_gateway_healthy": False,  # worker tasks can run independently
}


def classify_task_node(task_text: str, risk_level: str = "low",
                       repo_scope: str = "trusted-self") -> dict:
    """Classify which node should execute a task.

    NOTE (baseline01): This function is a node classifier, not an approval
    gate. Its returned `requires_approval` is legacy metadata — do not use
    it as runtime authorization. Callers must enforce operator approval
    via baseline01 gates (vibe_task_intake.py, git_pr_approval_gate.py).

    Returns: node, reason, timeout, requires_approval, gateway_safe.
    """
    import re
    text_lower = task_text.lower()

    # Check Debian-required first (higher priority)
    for category, patterns in DEBIAN_REQUIRED_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text_lower):
                return {
                    "node": "debian-worker",
                    "category": category,
                    "reason": f"Task matches Debian-required pattern: {category}",
                    "timeout": 600,
                    "requires_approval": risk_level in ("high", "critical"),
                    "gateway_safe": True,
                }

    # Check Windows-suitable
    for category, patterns in WINDOWS_SUITABLE_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text_lower):
                timeout = (GATEWAY_ISOLATION["max_gateway_health_seconds"]
                           if category == "gateway"
                           else GATEWAY_ISOLATION["max_worker_task_seconds"])
                return {
                    "node": "windows-worker",
                    "category": category,
                    "reason": f"Task matches Windows-suitable pattern: {category}",
                    "timeout": timeout,
                    "requires_approval": False,
                    "gateway_safe": True,
                }

    # Default: Debian worker (safer for unknown tasks)
    return {
        "node": "debian-worker",
        "category": "default",
        "reason": "No Windows-specific pattern matched; defaulting to Debian",
        "timeout": 600,
        "requires_approval": False,
        "gateway_safe": True,
    }


def check_gateway_isolation(task_node: str, task_timeout: int) -> dict:
    """Check if task can run without blocking gateway."""
    if task_node != "windows-worker":
        return {"allowed": True, "reason": "Non-Windows node, no gateway conflict"}

    max_timeout = GATEWAY_ISOLATION["max_worker_task_seconds"]
    if task_timeout > max_timeout:
        return {
            "allowed": False,
            "reason": f"Task timeout {task_timeout}s exceeds Windows worker max {max_timeout}s",
        }

    return {"allowed": True, "reason": "Within Windows worker limits"}


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

    # T1: gateway health → windows
    r = classify_task_node("gateway health check")
    check("gateway_windows", r["node"] == "windows-worker",
          f"node={r['node']}")

    # T2: pytest → debian
    r = classify_task_node("run pytest full smoke")
    check("pytest_debian", r["node"] == "debian-worker",
          f"node={r['node']}")

    # T3: powershell → windows
    r = classify_task_node("run powershell script to check ACL")
    check("powershell_windows", r["node"] == "windows-worker",
          f"node={r['node']}")

    # T4: git push → debian
    r = classify_task_node("git push to origin main")
    check("git_push_debian", r["node"] == "debian-worker",
          f"node={r['node']}")

    # T5: event log → windows
    r = classify_task_node("check windows event log for errors")
    check("eventlog_windows", r["node"] == "windows-worker",
          f"node={r['node']}")

    # T6: external push → debian
    r = classify_task_node("external push to fork repo",
                           risk_level="high",
                           repo_scope="protected-external")
    check("ext_push_debian", r["node"] == "debian-worker",
          f"node={r['node']}")

    # T7: gateway timeout check
    iso = check_gateway_isolation("windows-worker", 30)
    check("gateway_iso_ok", iso["allowed"],
          f"reason={iso['reason']}")

    iso = check_gateway_isolation("windows-worker", 600)
    check("gateway_iso_block", not iso["allowed"],
          f"reason={iso['reason']}")

    # T8: default → debian
    r = classify_task_node("do something unknown")
    check("default_debian", r["node"] == "debian-worker",
          f"node={r['node']}")

    # T9: version
    check("version", True, VERSION)

    return {"passed": passed, "failed": failed, "total": passed + failed,
            "results": results}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "self-check":
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["failed"] == 0 else 1)

    if len(sys.argv) > 1 and sys.argv[1] == "classify":
        text = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else "gateway health"
        r = classify_task_node(text)
        print(json.dumps(r, indent=2))
        sys.exit(0)

    print(json.dumps({"version": VERSION, "profiles": list(WINDOWS_SUITABLE_PATTERNS.keys())}, indent=2))


if __name__ == "__main__":
    main()
