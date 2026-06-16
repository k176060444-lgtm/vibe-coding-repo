#!/usr/bin/env python3
"""vibe_worker_pool_health.py — Worker Pool Health Check v1.0.0

Checks health of all workers in the active-active pool.

Usage:
    python3 scripts/vibe_worker_pool_health.py --json
    python3 scripts/vibe_worker_pool_health.py --self-check
"""

__version__ = "1.0.0"

import json
import subprocess
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from vibe_worker_registry import WorkerRegistry, WorkerNode, NodeStatus

# SSH key path (relative to Windows controller)
SSH_KEY = os.environ.get("VIBEDEV_SSH_KEY", "")
SSH_BASE_OPTS = ["-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=no", "-o", "BatchMode=yes"]


def _ssh_check(host: str, port: int, user: str, key_path: str, cmd: str, timeout: int = 15) -> tuple:
    """Run SSH command, return (exit_code, stdout, stderr)."""
    ssh_cmd = ["ssh"] + SSH_BASE_OPTS
    if key_path:
        ssh_cmd += ["-i", key_path]
    ssh_cmd += ["-p", str(port), f"{user}@{host}", cmd]
    try:
        p = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except OSError as e:
        return -1, "", str(e)


def check_worker_health(worker: WorkerNode, key_path: str = "") -> dict:
    """Check health of a single worker via SSH."""
    result = {
        "worker_id": worker.worker_id,
        "node_type": worker.node_type,
        "ssh_host": worker.ssh_host,
        "ssh_port": worker.ssh_port,
        "health": NodeStatus.UNKNOWN,
        "hostname": "",
        "whoami": "",
        "uid": "",
        "disk_free_gb": 0,
        "load_1m": 0.0,
        "uptime": "",
        "git_version": "",
        "python_version": "",
        "node_version": "",
        "baseline_sha": "",
        "baseline_match": False,
        "checks": [],
    }

    # Basic connectivity
    rc, out, err = _ssh_check(
        worker.ssh_host, worker.ssh_port, worker.ssh_user, key_path,
        "hostname && whoami && id && date -Iseconds"
    )
    if rc != 0:
        result["health"] = NodeStatus.OFFLINE
        result["checks"].append({"name": "ssh_connect", "passed": False, "error": err[:100]})
        return result

    lines = out.split("\n")
    if len(lines) >= 4:
        result["hostname"] = lines[0]
        result["whoami"] = lines[1]
        result["uid"] = lines[2]
        result["checks"].append({"name": "ssh_connect", "passed": True})

    # System info
    rc, out, _ = _ssh_check(
        worker.ssh_host, worker.ssh_port, worker.ssh_user, key_path,
        "df -h / | tail -1 && uptime && git --version && python3 --version && node --version 2>/dev/null || echo NODE_MISSING"
    )
    if rc == 0:
        parts = out.split("\n")
        if len(parts) >= 5:
            # Parse disk
            disk_parts = parts[0].split()
            if len(disk_parts) >= 4:
                avail = disk_parts[3]
                if avail.endswith("G"):
                    try:
                        result["disk_free_gb"] = float(avail[:-1])
                    except ValueError:
                        pass
            # Parse load
            uptime_parts = parts[1].split("load average:")
            if len(uptime_parts) >= 2:
                try:
                    result["load_1m"] = float(uptime_parts[1].split(",")[0].strip())
                except ValueError:
                    pass
            result["uptime"] = parts[1].strip()
            result["git_version"] = parts[2].strip()
            result["python_version"] = parts[3].strip()
            result["node_version"] = parts[4].strip() if parts[4] != "NODE_MISSING" else "NOT_INSTALLED"
            result["checks"].append({"name": "system_info", "passed": True})

    # Baseline check
    rc, out, _ = _ssh_check(
        worker.ssh_host, worker.ssh_port, worker.ssh_user, key_path,
        f"git --git-dir={worker.repo_root} rev-parse refs/heads/main 2>/dev/null"
    )
    if rc == 0 and out:
        result["baseline_sha"] = out
        result["checks"].append({"name": "baseline_check", "passed": True, "sha": out[:12]})

    # Determine overall health
    all_passed = all(c.get("passed", False) for c in result["checks"])
    if all_passed and result["disk_free_gb"] > 5:
        result["health"] = NodeStatus.ONLINE
    elif all_passed:
        result["health"] = NodeStatus.ONLINE  # low disk but online
    else:
        result["health"] = NodeStatus.OFFLINE

    return result


def check_pool_health(key_path: str = "") -> dict:
    """Check health of all workers in the pool."""
    registry = WorkerRegistry()
    pool_results = []

    for worker in registry.list_workers():
        health = check_worker_health(worker, key_path)
        pool_results.append(health)
        # Update registry
        registry.set_health(worker.worker_id, health["health"])

    online_count = sum(1 for r in pool_results if r["health"] == NodeStatus.ONLINE)

    return {
        "version": __version__,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pool_summary": {
            "total_workers": len(pool_results),
            "online": online_count,
            "offline": len(pool_results) - online_count,
            "total_capacity": sum(w.max_parallel_jobs for w in registry.workers.values()),
        },
        "workers": pool_results,
    }


def self_check() -> dict:
    """Self-check: verify health check structure."""
    checks = []
    passed = True

    # Check 1: Registry import
    try:
        reg = WorkerRegistry()
        assert len(reg.workers) == 2
        checks.append({"name": "registry_import", "passed": True})
    except Exception as e:
        checks.append({"name": "registry_import", "passed": False, "error": str(e)})
        passed = False

    # Check 2: Health check structure
    try:
        health = check_pool_health(key_path="__test__")
        assert "version" in health
        assert "pool_summary" in health
        assert "workers" in health
        assert health["pool_summary"]["total_workers"] == 2
        checks.append({"name": "health_structure", "passed": True})
    except Exception as e:
        checks.append({"name": "health_structure", "passed": False, "error": str(e)})
        passed = False

    # Check 3: No secret in output
    try:
        health = check_pool_health(key_path="__test__")
        output = json.dumps(health)
        assert "password" not in output.lower()
        assert "token" not in output.lower() or "token_policy" in output
        checks.append({"name": "no_secret", "passed": True})
    except Exception as e:
        checks.append({"name": "no_secret", "passed": False, "error": str(e)})
        passed = False

    return {"passed": passed, "version": __version__, "checks": checks}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Worker Pool Health Check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--self-check", action="store_true", help="Self-check")
    parser.add_argument("--key", default="", help="SSH key path")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    result = check_pool_health(args.key)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
