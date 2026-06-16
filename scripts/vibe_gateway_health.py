#!/usr/bin/env python3
"""vibe_gateway_health.py v2.0.0

Gateway health diagnostics with 72h ExecutionTimeLimit detection.

v2.0.0 changes:
  - Enhanced _check_windows_tasks() with ExecutionTimeLimit fields
  - Added _parse_task_scheduler_config() for detailed task config
  - Added _assess_limit_risk() for 72h limit risk assessment
  - diagnose_profile() includes limit_risk section
  - Supports PT0S/PT0/indefinite as "no limit"
  - Separate default/vibedev reporting
"""

import json
import os
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone

VERSION = "2.0.0"

# Status constants
STATUS_ONLINE = "ONLINE"
STATUS_OFFLINE_NO_PROCESS = "OFFLINE_NO_PROCESS"
STATUS_TASK_READY_NOT_RUNNING = "TASK_READY_NOT_RUNNING"
STATUS_STALE_LOG = "STALE_LOG"
STATUS_RECONNECTING = "RECONNECTING"
STATUS_SESSION_CONFLICT_SUSPECTED = "SESSION_CONFLICT_SUSPECTED"
STATUS_SESSION_CONFLICT = STATUS_SESSION_CONFLICT_SUSPECTED
STATUS_UNKNOWN = "UNKNOWN"
STATUS_LIMIT_WARNING = "LIMIT_WARNING"
STATUS_LIMIT_BLOCK = "LIMIT_BLOCK"

# Limit risk statuses
LIMIT_OK = "OK"
LIMIT_WARN = "WARN"
LIMIT_BLOCK = "BLOCK"
LIMIT_UNKNOWN = "UNKNOWN"

# PT72H in seconds
PT72H_SECONDS = 72 * 3600  # 259200


def _run_cmd(cmd, timeout=15):
    """Run a command and return (rc, stdout, stderr)."""
    try:
        if isinstance(cmd, str):
            r = subprocess.run(cmd, shell=True, capture_output=True,
                               text=True, timeout=timeout)
        else:
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:
        return -1, "", str(e)


def _get_file_age(filepath):
    """Get file age in seconds, or -1 if not found."""
    try:
        return datetime.now().timestamp() - os.path.getmtime(filepath)
    except Exception:
        return -1


def _parse_log_patterns(log_path, patterns, max_lines=200):
    """Parse log file for specific patterns."""
    if not os.path.exists(log_path):
        return {"status": "NO_LOG", "matches": []}
    matches = []
    try:
        with open(log_path, "r", errors="replace") as f:
            lines = f.readlines()[-max_lines:]
        for line in lines:
            for pat in patterns:
                if pat.lower() in line.lower():
                    matches.append({"pattern": pat, "line": line.strip()[:200]})
    except Exception:
        return {"status": "READ_ERROR", "matches": []}
    return {"status": "PARSED", "matches": matches[-20:]}


def _parse_duration(duration_str):
    """Parse ISO 8601 duration (PT72H, PT0S, etc.) to seconds.
    Returns: (seconds, is_indefinite)
    """
    if not duration_str or duration_str.strip() in ("PT0S", "PT0", "P0D", "",
                                                      "indefinite", "none",
                                                      "unlimited"):
        return 0, True

    # PT72H format
    m = re.match(r'PT?(\d+)H', duration_str.strip())
    if m:
        return int(m.group(1)) * 3600, False

    # PT#M format
    m = re.match(r'PT?(\d+)M', duration_str.strip())
    if m:
        return int(m.group(1)) * 60, False

    # PT#S format
    m = re.match(r'PT?(\d+)S', duration_str.strip())
    if m:
        return int(m.group(1)), False

    # P#D format
    m = re.match(r'P(\d+)D', duration_str.strip())
    if m:
        return int(m.group(1)) * 86400, False

    return 0, False  # Unknown format


def _check_windows_tasks_enhanced():
    """Enhanced Windows task check with ExecutionTimeLimit details."""
    tasks = {}
    for task_name in ["Hermes_Gateway", "Hermes_Gateway_vibedev"]:
        task_info = {
            "exists": False,
            "task_state": "NOT_FOUND",
            "gateway_process_present": False,
            "execution_time_limit": "UNKNOWN",
            "execution_time_limit_seconds": 0,
            "execution_time_limit_is_indefinite": False,
            "allow_hard_terminate": False,
            "start_when_available": False,
            "multiple_instances": "UNKNOWN",
            "last_run_time": "",
            "current_uptime_seconds": 0,
            "estimated_seconds_to_limit": -1,
            "limit_risk_status": LIMIT_UNKNOWN,
        }

        if platform.system() != "Windows":
            task_info["task_state"] = "NOT_WINDOWS"
            tasks[task_name] = task_info
            continue

        # Query task via PowerShell for detailed config
        ps_script = f'''
$task = Get-ScheduledTask -TaskName '{task_name}' -ErrorAction SilentlyContinue
if ($task) {{
    $info = Get-ScheduledTaskInfo -TaskName '{task_name}' -ErrorAction SilentlyContinue
    Write-Output "EXISTS=true"
    Write-Output "STATE=$($task.State)"
    Write-Output "ETL=$($task.Settings.ExecutionTimeLimit)"
    Write-Output "AHT=$($task.Settings.AllowHardTerminate)"
    Write-Output "SWA=$($task.Settings.StartWhenAvailable)"
    Write-Output "MI=$($task.Settings.MultipleInstances)"
    if ($info) {{
        Write-Output "LRT=$($info.LastRunTime)"
        Write-Output "LTR=$($info.LastTaskResult)"
    }}
}} else {{
    Write-Output "EXISTS=false"
}}
'''
        rc, out, _ = _run_cmd(
            f'powershell -ExecutionPolicy Bypass -Command "{ps_script}"',
            timeout=20)

        if rc != 0 or "EXISTS=true" not in out:
            tasks[task_name] = task_info
            continue

        task_info["exists"] = True

        # Parse output
        for line in out.strip().split("\n"):
            line = line.strip()
            if line.startswith("STATE="):
                task_info["task_state"] = line[6:]
            elif line.startswith("ETL="):
                task_info["execution_time_limit"] = line[4:]
            elif line.startswith("AHT="):
                task_info["allow_hard_terminate"] = line[4:].lower() == "true"
            elif line.startswith("SWA="):
                task_info["start_when_available"] = line[4:].lower() == "true"
            elif line.startswith("MI="):
                task_info["multiple_instances"] = line[3:]
            elif line.startswith("LRT="):
                task_info["last_run_time"] = line[4:]
            elif line.startswith("LTR="):
                pass  # LastTaskResult, informational

        # Parse ETL to seconds
        etl_str = task_info["execution_time_limit"]
        etl_seconds, is_indefinite = _parse_duration(etl_str)
        task_info["execution_time_limit_seconds"] = etl_seconds
        task_info["execution_time_limit_is_indefinite"] = is_indefinite

        # Check gateway process
        proc_rc, proc_out, _ = _run_cmd(
            'tasklist /FI "IMAGENAME eq node.exe" /FO CSV 2>nul')
        # Also check for hermes processes
        hermes_rc, hermes_out, _ = _run_cmd(
            f'tasklist /FI "STATUS eq RUNNING" /FO CSV 2>nul')
        gateway_present = ("node" in (proc_out or "").lower() or
                           "hermes" in (hermes_out or "").lower())
        task_info["gateway_process_present"] = gateway_present

        # Assess limit risk
        task_info["limit_risk_status"] = _assess_limit_risk(
            task_info["task_state"],
            task_info["execution_time_limit_is_indefinite"],
            etl_seconds,
            task_info["allow_hard_terminate"],
            gateway_present,
        )

        tasks[task_name] = task_info

    return tasks


def _assess_limit_risk(task_state, is_indefinite, etl_seconds,
                       allow_hard_terminate, gateway_present):
    """Assess 72h limit risk status."""
    # No limit → OK
    if is_indefinite or etl_seconds == 0:
        return LIMIT_OK

    # Finite limit present
    running = task_state.upper() in ("RUNNING", "4")
    ready_not_running = (task_state.upper() in ("READY", "QUEUED") and
                         not gateway_present)

    if ready_not_running:
        # Task ready but gateway absent — likely killed by limit
        return LIMIT_BLOCK

    if running and allow_hard_terminate:
        # Running with hard terminate enabled — risk depends on uptime
        # Without exact uptime, we flag as WARN for any finite limit
        return LIMIT_WARN

    if not gateway_present and not running:
        return LIMIT_BLOCK

    return LIMIT_OK


def _check_windows_tasks():
    """Legacy wrapper — returns simple task status."""
    enhanced = _check_windows_tasks_enhanced()
    simple = {}
    for name, info in enhanced.items():
        simple[name] = {
            "exists": info["exists"],
            "status": info["task_state"],
        }
    return simple


def _check_processes():
    """Check for gateway/agent/qqbot processes."""
    proc_patterns = [
        "hermes", "gateway", "qqbot", "vibedev",
        "node", "python", "terminal", "bash", "git"
    ]
    found = {}
    for pattern in proc_patterns:
        if platform.system() == "Windows":
            rc, out, _ = _run_cmd(
                f'tasklist /FI "IMAGENAME eq *{pattern}*" /FO CSV 2>nul')
        else:
            rc, out, _ = _run_cmd(["pgrep", "-la", pattern])
        if rc == 0 and out.strip():
            lines = [l for l in out.strip().split("\n")
                     if pattern.lower() in l.lower()]
            if lines:
                found[pattern] = len(lines)
    return found


def _check_log_freshness(log_paths):
    """Check if log files are fresh (< 5 minutes)."""
    results = {}
    for name, path in log_paths.items():
        age = _get_file_age(path)
        if age < 0:
            results[name] = {"status": "NO_LOG", "age_seconds": -1}
        elif age < 300:
            results[name] = {"status": "FRESH", "age_seconds": int(age)}
        else:
            results[name] = {"status": "STALE", "age_seconds": int(age)}
    return results


def _check_websocket_state(log_path):
    """Check WebSocket state from log file."""
    patterns = ["WebSocket closed", "reconnect failed", "session expired",
                "session resumed", "connected", "QQBot"]
    parsed = _parse_log_patterns(log_path, patterns)
    if parsed["status"] == "NO_LOG":
        return {"status": "NO_LOG", "signals": []}
    signals = [m["pattern"] for m in parsed["matches"]]
    if "reconnect failed" in signals:
        return {"status": STATUS_RECONNECTING, "signals": signals}
    if "session expired" in signals:
        return {"status": STATUS_SESSION_CONFLICT_SUSPECTED, "signals": signals}
    if "connected" in signals or "session resumed" in signals:
        return {"status": "CONNECTED", "signals": signals}
    return {"status": "NO_SIGNALS", "signals": signals}


def _is_telegram_error(log_path):
    """Check if Telegram errors are present."""
    patterns = ["telegram", "TELEGRAM_ERROR", "network error"]
    parsed = _parse_log_patterns(log_path, patterns)
    return len(parsed["matches"]) > 0


def diagnose_profile(profile_name, log_dir=None, is_windows=None):
    """Diagnose a single gateway profile with 72h limit detection."""
    if is_windows is None:
        is_windows = platform.system() == "Windows"

    result = {
        "profile": profile_name,
        "platform": platform.system(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # Enhanced task status with limit detection
    if is_windows:
        enhanced_tasks = _check_windows_tasks_enhanced()
        task_key = ("Hermes_Gateway" if profile_name == "default"
                    else "Hermes_Gateway_vibedev")
        task_info = enhanced_tasks.get(task_key, {
            "exists": False, "task_state": "NOT_FOUND",
            "limit_risk_status": LIMIT_UNKNOWN,
        })
        result["task"] = {
            "exists": task_info["exists"],
            "status": task_info["task_state"],
        }
        result["limit_risk"] = {
            "task_name": task_key,
            "task_state": task_info["task_state"],
            "gateway_process_present": task_info.get(
                "gateway_process_present", False),
            "execution_time_limit": task_info.get(
                "execution_time_limit", "UNKNOWN"),
            "execution_time_limit_seconds": task_info.get(
                "execution_time_limit_seconds", 0),
            "execution_time_limit_is_indefinite": task_info.get(
                "execution_time_limit_is_indefinite", False),
            "allow_hard_terminate": task_info.get(
                "allow_hard_terminate", False),
            "start_when_available": task_info.get(
                "start_when_available", False),
            "multiple_instances": task_info.get(
                "multiple_instances", "UNKNOWN"),
            "last_run_time": task_info.get("last_run_time", ""),
            "current_uptime_seconds": task_info.get(
                "current_uptime_seconds", 0),
            "estimated_seconds_to_limit": task_info.get(
                "estimated_seconds_to_limit", -1),
            "limit_risk_status": task_info.get(
                "limit_risk_status", LIMIT_UNKNOWN),
        }
    else:
        result["task"] = {"exists": False, "status": "NOT_WINDOWS"}
        result["limit_risk"] = {
            "task_name": "",
            "task_state": "NOT_WINDOWS",
            "gateway_process_present": False,
            "execution_time_limit": "N/A",
            "execution_time_limit_seconds": 0,
            "execution_time_limit_is_indefinite": True,
            "allow_hard_terminate": False,
            "start_when_available": False,
            "multiple_instances": "N/A",
            "last_run_time": "",
            "current_uptime_seconds": 0,
            "estimated_seconds_to_limit": -1,
            "limit_risk_status": LIMIT_OK,
        }

    # Process status
    processes = _check_processes()
    result["processes"] = processes
    result["process_count"] = sum(processes.values())

    # Log freshness
    if log_dir is None:
        log_dir = os.path.expanduser(
            f"~/.hermes/profiles/{profile_name}/logs")
    log_paths = {
        "main_log": os.path.join(log_dir, "hermes.log"),
        "qqbot_log": os.path.join(log_dir, "qqbot.log"),
        "gateway_log": os.path.join(log_dir, "gateway.log"),
    }
    result["logs"] = _check_log_freshness(log_paths)

    # WebSocket state
    result["qqbot_websocket"] = _check_websocket_state(
        log_paths.get("qqbot_log"))

    # Telegram error check
    result["telegram_error_present"] = _is_telegram_error(
        log_paths.get("main_log"))

    # Determine overall status (incorporating limit risk)
    has_process = result["process_count"] > 0
    task_ready = result.get("task", {}).get("status", "").upper() in (
        "READY", "RUNNING")
    log_fresh = any(l.get("status") == "FRESH"
                    for l in result["logs"].values())
    ws_ok = result["qqbot_websocket"]["status"] in (
        "CONNECTED", "NO_SIGNALS", "NO_LOG")
    limit_risk = result.get("limit_risk", {}).get(
        "limit_risk_status", LIMIT_OK)

    if limit_risk == LIMIT_BLOCK:
        result["overall_status"] = STATUS_LIMIT_BLOCK
    elif limit_risk == LIMIT_WARN:
        result["overall_status"] = STATUS_LIMIT_WARNING
    elif has_process and log_fresh and ws_ok:
        result["overall_status"] = STATUS_ONLINE
    elif has_process and not log_fresh:
        result["overall_status"] = STATUS_STALE_LOG
    elif not has_process and task_ready:
        result["overall_status"] = STATUS_TASK_READY_NOT_RUNNING
    elif not has_process:
        result["overall_status"] = STATUS_OFFLINE_NO_PROCESS
    elif result["qqbot_websocket"]["status"] == STATUS_SESSION_CONFLICT:
        result["overall_status"] = STATUS_SESSION_CONFLICT
    elif result["qqbot_websocket"]["status"] == STATUS_RECONNECTING:
        result["overall_status"] = STATUS_RECONNECTING
    else:
        result["overall_status"] = STATUS_UNKNOWN

    return result


def diagnose(json_output=False):
    """Diagnose both default and vibedev gateway profiles.
    
    Always returns results dict. Prints only if json_output is explicitly
    requested (called from main/CLI, not from other modules).
    """
    results = {
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "profiles": {},
    }
    for profile in ["default", "vibedev"]:
        results["profiles"][profile] = diagnose_profile(profile)

    # Overall summary
    statuses = [p["overall_status"]
                for p in results["profiles"].values()]
    if all(s == STATUS_ONLINE for s in statuses):
        results["overall"] = STATUS_ONLINE
    elif any(s == STATUS_LIMIT_BLOCK for s in statuses):
        results["overall"] = STATUS_LIMIT_BLOCK
    elif any(s == STATUS_LIMIT_WARNING for s in statuses):
        results["overall"] = STATUS_LIMIT_WARNING
    elif any(s in (STATUS_OFFLINE_NO_PROCESS, STATUS_TASK_READY_NOT_RUNNING)
             for s in statuses):
        results["overall"] = "DEGRADED"
    else:
        results["overall"] = STATUS_UNKNOWN

    # Only print when called from CLI (json_output flag)
    if json_output == "print":
        print(json.dumps(results, indent=2))
    elif json_output is True:
        # Return-only mode for programmatic callers
        pass
    else:
        for name, prof in results["profiles"].items():
            lr = prof.get("limit_risk", {})
            etl = lr.get("execution_time_limit", "N/A")
            risk = lr.get("limit_risk_status", "N/A")
            print(f"  {name}: {prof['overall_status']}"
                  f" | task={prof['task']['status']}"
                  f" | procs={prof['process_count']}"
                  f" | etl={etl} risk={risk}")
        print(f"  Overall: {results['overall']}")

    return results


def self_check(json_output=False):
    """Run self-check tests."""
    checks = []
    checks.append({"name": "version", "passed": True, "message": VERSION})

    # Test PT0S parsing
    secs, indef = _parse_duration("PT0S")
    checks.append({
        "name": "parse_pt0s",
        "passed": secs == 0 and indef is True,
        "message": f"PT0S -> {secs}s indefinite={indef}",
    })

    # Test PT72H parsing
    secs, indef = _parse_duration("PT72H")
    checks.append({
        "name": "parse_pt72h",
        "passed": secs == 259200 and indef is False,
        "message": f"PT72H -> {secs}s indefinite={indef}",
    })

    # Test PT0 parsing
    secs, indef = _parse_duration("PT0")
    checks.append({
        "name": "parse_pt0",
        "passed": secs == 0 and indef is True,
        "message": f"PT0 -> {secs}s indefinite={indef}",
    })

    # Test limit risk: indefinite → OK
    risk = _assess_limit_risk("Running", True, 0, False, True)
    checks.append({
        "name": "risk_indefinite_ok",
        "passed": risk == LIMIT_OK,
        "message": f"indefinite -> {risk}",
    })

    # Test limit risk: PT72H + running + AHT=True → WARN
    risk = _assess_limit_risk("Running", False, 259200, True, True)
    checks.append({
        "name": "risk_pt72h_running_warn",
        "passed": risk == LIMIT_WARN,
        "message": f"PT72H+running+AHT -> {risk}",
    })

    # Test limit risk: PT72H + ready/not running + no process → BLOCK
    risk = _assess_limit_risk("Ready", False, 259200, True, False)
    checks.append({
        "name": "risk_pt72h_ready_block",
        "passed": risk == LIMIT_BLOCK,
        "message": f"PT72H+ready+no_proc -> {risk}",
    })

    # Test limit risk: PT72H + running + AHT=False → OK (no hard terminate)
    risk = _assess_limit_risk("Running", False, 259200, False, True)
    checks.append({
        "name": "risk_pt72h_no_aht_ok",
        "passed": risk == LIMIT_OK,
        "message": f"PT72H+running+AHT=False -> {risk}",
    })

    # Test version string
    checks.append({
        "name": "version_2",
        "passed": VERSION == "2.0.0",
        "message": f"VERSION={VERSION}",
    })

    passed = sum(1 for c in checks if c["passed"])
    failed = sum(1 for c in checks if not c["passed"])
    result = {"overall": "PASS" if failed == 0 else "FAIL",
              "passed": passed, "failed": failed, "total": len(checks),
              "checks": checks}

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        for c in checks:
            sym = "✓" if c["passed"] else "✗"
            print(f"  {sym} {c['name']}: {'PASS' if c['passed'] else 'FAIL'}"
                  f" - {c['message']}")
        print(f"  Overall: {'PASS' if failed == 0 else 'FAIL'}"
              f" ({passed}/{len(checks)})")

    return result


def build_parser():
    """Build argument parser."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Gateway health diagnostics with 72h limit detection")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {VERSION}")
    parser.add_argument("--json", dest="output_json", action="store_true",
                        help="JSON output")
    parser.add_argument("--self-check", dest="self_check_flag",
                        action="store_true", help="Run self-check")
    parser.add_argument("positional", nargs="?", default=None,
                        help="Positional arg (e.g., 'self-check')")
    parser.add_argument("--compact", action="store_true",
                        help="Compact one-line output")
    return parser


def main(argv=None):
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_check_flag or args.positional == "self-check":
        result = self_check(args.output_json)
        return 0 if result.get("failed", 1) == 0 else 1

    if args.compact:
        results = diagnose(json_output=False)
        return 0 if results.get("overall") == STATUS_ONLINE else 1

    results = diagnose(json_output="print" if args.output_json else False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
