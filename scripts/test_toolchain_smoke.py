#!/usr/bin/env python3
"""Toolchain Smoke Suite v1 - Local smoke test for all orchestrator tools.

Usage:
    python scripts/test_toolchain_smoke.py [--jobs-dir <dir>]

Tests:
    1. Command Router: help, snapshot, advisor, dispatch, batch-plan
    2. Health Check: all checks pass
    3. Operator Snapshot: returns valid JSON
    4. Queue Advisor: returns valid JSON
    5. Dispatch Planner: returns valid JSON
    6. Batch Plan: returns valid JSON

Constraints:
    - Read-only, no file modifications
    - No network writes
    - Standard library only
    - Must pass on clean repo state
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _run_test(name, test_fn):
    """Run a test and return (name, passed, message)."""
    try:
        result = test_fn()
        return (name, result["passed"], result.get("message", ""))
    except Exception as e:
        return (name, False, str(e))


def _run_script(script_path, args, timeout=30):
    """Run a script and return (returncode, stdout, stderr)."""
    try:
        cmd = [sys.executable, str(script_path)] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (1, "", "timeout")
    except (OSError, FileNotFoundError) as e:
        return (1, "", str(e))


def _test_command_router_help(script_dir):
    """Test command router help."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["help"])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    if "vibe_command_router" not in stdout:
        return {"passed": False, "message": "help text missing"}
    
    return {"passed": True, "message": "help works"}


def _test_command_router_snapshot(script_dir, jobs_dir):
    """Test command router snapshot."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["snapshot", "--compact"])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    if "Operator Snapshot" not in stdout:
        return {"passed": False, "message": "snapshot output missing"}
    
    return {"passed": True, "message": "snapshot works"}


def _test_command_router_advisor(script_dir, jobs_dir):
    """Test command router advisor."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["advisor", "--json"])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"total={data.get('total_jobs', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_command_router_dispatch(script_dir, jobs_dir):
    """Test command router dispatch."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["dispatch", "--json"])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"recommended={data.get('recommended_action', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_command_router_batch_plan(script_dir, jobs_dir):
    """Test command router batch plan."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["batch-plan", "--json"])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"tasks={data.get('task_count', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_health_check(script_dir, jobs_dir):
    """Test health check."""
    path = script_dir / "vibe_health_check.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["--json", "--jobs-dir", jobs_dir])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        overall = data.get("overall", "UNKNOWN")
        return {"passed": overall == "PASS", "message": f"overall={overall}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_operator_snapshot(script_dir, jobs_dir):
    """Test operator snapshot."""
    path = script_dir / "vibe_operator_snapshot.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["--json", "--jobs-dir", jobs_dir])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"total={data.get('jobs_summary', {}).get('total_jobs', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_queue_advisor(script_dir, jobs_dir):
    """Test queue advisor."""
    path = script_dir / "vibe_queue_advisor.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["--json", "--jobs-dir", jobs_dir])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"total={data.get('total_jobs', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_dispatch_planner(script_dir, jobs_dir):
    """Test dispatch planner."""
    path = script_dir / "vibe_dispatch_planner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["--json", "--jobs-dir", jobs_dir])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"recommended={data.get('recommended_action', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}


def _test_batch_plan(script_dir, jobs_dir):
    """Test batch plan."""
    path = script_dir / "vibe_batch_plan.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    
    rc, stdout, stderr = _run_script(path, ["--json", "--jobs-dir", jobs_dir])
    if rc != 0:
        return {"passed": False, "message": f"exit code {rc}"}
    
    try:
        data = json.loads(stdout)
        return {"passed": True, "message": f"tasks={data.get('task_count', '?')}"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}



def _test_recommendation_consistency(script_dir, jobs_dir):
    """Test that snapshot, dispatch, and batch-plan recommendations are consistent."""
    import json as _json
    
    # Run snapshot
    rc1, out1, _ = _run_script(script_dir / "vibe_operator_snapshot.py", ["--json", "--jobs-dir", jobs_dir])
    # Run dispatch
    rc2, out2, _ = _run_script(script_dir / "vibe_dispatch_planner.py", ["--json", "--jobs-dir", jobs_dir])
    # Run batch plan
    rc3, out3, _ = _run_script(script_dir / "vibe_batch_plan.py", ["--json", "--jobs-dir", jobs_dir])
    
    if rc1 != 0 or rc2 != 0 or rc3 != 0:
        return {"passed": False, "message": "one or more scripts failed to run"}
    
    try:
        snap = _json.loads(out1)
        disp = _json.loads(out2)
        batch = _json.loads(out3)
    except _json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON from one or more scripts"}
    
    snap_action = snap.get("recommended_next_action", "")
    disp_action = disp.get("recommended_action", "")
    batch_tasks = batch.get("task_count", -1)
    
    # Consistency rule: if snapshot says queue_clean, dispatch should too
    if "queue_clean" in snap_action and disp_action != "queue_clean":
        return {"passed": False, "message": "inconsistent: snapshot=%s dispatch=%s" % (snap_action, disp_action)}
    
    # Consistency rule: if batch has 0 tasks and dispatch says queue_clean, all agree
    if batch_tasks == 0 and disp_action == "queue_clean" and "queue_clean" in snap_action:
        return {"passed": True, "message": "consistent: all report queue_clean/0-tasks"}
    
    # If batch has tasks, dispatch should not be queue_clean
    if batch_tasks > 0 and disp_action == "queue_clean":
        return {"passed": False, "message": "inconsistent: batch=%d tasks but dispatch=queue_clean" % batch_tasks}
    
    return {"passed": True, "message": "snapshot=%s dispatch=%s batch=%d" % (snap_action, disp_action, batch_tasks)}


def _test_intake_basic(script_dir):
    """Test intake basic markdown output."""
    path = script_dir / "vibe_workorder_intake.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["Add --summary flag to snapshot"])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    if "Work Order Draft" not in stdout:
        return {"passed": False, "message": "missing draft header"}

    if "wo-code-" not in stdout:
        return {"passed": False, "message": "missing work_order_id"}

    return {"passed": True, "message": "markdown draft generated"}


def _test_intake_json(script_dir):
    """Test intake JSON output is valid and complete."""
    import json as _json
    path = script_dir / "vibe_workorder_intake.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["Update workflow docs", "--type", "doc", "--json"])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    try:
        d = _json.loads(stdout)
    except _json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}

    required = ["work_order_id", "title", "type", "goal", "risk_level",
                 "requires_human_approval", "allowed_paths", "forbidden_actions",
                 "acceptance_tests", "stop_conditions", "expected_report_fields", "draft_only"]
    missing = [k for k in required if k not in d]
    if missing:
        return {"passed": False, "message": "missing fields: %s" % ", ".join(missing)}

    if not d.get("draft_only"):
        return {"passed": False, "message": "draft_only must be true"}

    return {"passed": True, "message": "type=%s risk=%s" % (d["type"], d["risk_level"])}


def _test_intake_risk_classification(script_dir):
    """Test intake risk classification for dangerous requirements."""
    import json as _json
    path = script_dir / "vibe_workorder_intake.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    # Critical: credentials + production
    rc, stdout, stderr = _run_script(path, ["Change auth credentials for production deploy", "--json"])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    try:
        d = _json.loads(stdout)
    except _json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}

    if d["risk_level"] not in ("critical", "high"):
        return {"passed": False, "message": "expected high/critical, got %s" % d["risk_level"]}

    if not d["requires_human_approval"]:
        return {"passed": False, "message": "should require human approval"}

    return {"passed": True, "message": "risk=%s human=%s" % (d["risk_level"], d["requires_human_approval"])}


def _test_intake_type_detection(script_dir):
    """Test intake type detection for different requirements."""
    import json as _json
    path = script_dir / "vibe_workorder_intake.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    cases = [
        ("Update the README documentation", "doc"),
        ("Add new unit tests for advisor", "test"),
        ("Fix the crash in dispatch planner", "fix"),
    ]
    for req, expected_type in cases:
        rc, stdout, stderr = _run_script(path, [req, "--json"])
        if rc != 0:
            return {"passed": False, "message": "exit code %d for: %s" % (rc, req)}
        try:
            d = _json.loads(stdout)
        except _json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON for: %s" % req}
        if d["type"] != expected_type:
            return {"passed": False, "message": "expected type=%s got=%s for: %s" % (expected_type, d["type"], req)}

    return {"passed": True, "message": "3 type cases pass"}


def _test_intake_router(script_dir):
    """Test intake via command router."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["intake", "Add --summary flag to snapshot"])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    if "Work Order Draft" not in stdout:
        return {"passed": False, "message": "missing draft output"}

    return {"passed": True, "message": "router intake works"}



def _test_release_notes_basic(script_dir):
    """Test release notes basic markdown output."""
    path = script_dir / "vibe_release_notes.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["--compact"])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    if "Release Notes" not in stdout:
        return {"passed": False, "message": "missing title"}

    if "Main SHA" not in stdout:
        return {"passed": False, "message": "missing main SHA"}

    return {"passed": True, "message": "compact report generated"}


def _test_release_notes_json(script_dir):
    """Test release notes JSON output."""
    import json as _json
    path = script_dir / "vibe_release_notes.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["--json", "--limit", "5"])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    try:
        d = _json.loads(stdout)
    except _json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}

    required = ["current_main_sha", "total_merged_prs", "merged_prs",
                 "pr_summary", "capability_changes", "safety_status",
                 "recommended_next_phase"]
    missing = [k for k in required if k not in d]
    if missing:
        return {"passed": False, "message": "missing: %s" % ", ".join(missing)}

    return {"passed": True, "message": "prs=%d caps=%d" % (d["total_merged_prs"], len(d["capability_changes"]))}


def _test_release_notes_safety(script_dir):
    """Test release notes safety status includes audit lock."""
    import json as _json
    path = script_dir / "vibe_release_notes.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["--json"])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    try:
        d = _json.loads(stdout)
    except _json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}

    lock = d.get("safety_status", {}).get("audit_tainted_lock")
    if not lock:
        return {"passed": False, "message": "missing audit_tainted_lock"}

    if lock.get("audit_status") != "audit_tainted":
        return {"passed": False, "message": "wrong audit_status: %s" % lock.get("audit_status")}

    if lock.get("push_allowed") is not False:
        return {"passed": False, "message": "push_allowed should be false"}

    return {"passed": True, "message": "audit_tainted lock visible"}


def _test_release_notes_router(script_dir):
    """Test release notes via command router."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["notes", "--compact"])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    if "Release Notes" not in stdout:
        return {"passed": False, "message": "missing output"}

    return {"passed": True, "message": "router notes works"}



def _test_dashboard_text(script_dir):
    """Test dashboard text output via router."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["dash"])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    if "Dashboard" not in stdout:
        return {"passed": False, "message": "missing dashboard output"}

    if "PROJECT_DASHBOARD.md" not in stdout:
        return {"passed": False, "message": "missing dashboard path"}

    return {"passed": True, "message": "dashboard text output"}


def _test_dashboard_json(script_dir):
    """Test dashboard JSON output."""
    import json as _json
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["dash", "--json"])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    try:
        d = _json.loads(stdout)
    except _json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}

    if not d.get("exists"):
        return {"passed": False, "message": "dashboard file not found"}

    if "version" not in d:
        return {"passed": False, "message": "missing version"}

    return {"passed": True, "message": "ver=%s cmds=%d" % (d.get("version"), len(d.get("commands", [])))}


def _test_dashboard_aliases(script_dir):
    """Test dashboard aliases (dash, status-page)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    for alias in ["dash", "status-page"]:
        rc, stdout, stderr = _run_script(path, [alias])
        if rc != 0:
            return {"passed": False, "message": "alias '%s' failed: exit %d" % (alias, rc)}
        if "Dashboard" not in stdout:
            return {"passed": False, "message": "alias '%s' missing output" % alias}

    return {"passed": True, "message": "dash + status-page work"}



def _test_daily_report_text(script_dir):
    """Test daily report text output."""
    path = script_dir / "vibe_daily_report.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["--compact"])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    if "Daily Report" not in stdout:
        return {"passed": False, "message": "missing title"}

    if "Main:" not in stdout:
        return {"passed": False, "message": "missing main SHA"}

    return {"passed": True, "message": "daily report generated"}


def _test_daily_report_json(script_dir):
    """Test daily report JSON output."""
    import json as _json
    path = script_dir / "vibe_daily_report.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["--json"])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    try:
        d = _json.loads(stdout)
    except _json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}

    required = ["main_sha", "router_version", "smoke", "health", "queue", "next_action"]
    missing = [k for k in required if k not in d]
    if missing:
        return {"passed": False, "message": "missing: %s" % ", ".join(missing)}

    return {"passed": True, "message": "smoke=%s health=%s" % (d["smoke"]["overall"], d["health"]["overall"])}



def _test_validator_basic(script_dir):
    """Test validator with valid draft."""
    import json as _json
    import tempfile
    intake = script_dir / "vibe_workorder_intake.py"
    validator = script_dir / "vibe_workorder_validator.py"
    if not intake.exists() or not validator.exists():
        return {"passed": False, "message": "scripts not found"}

    # Generate draft
    rc1, out1, _ = _run_script(intake, ["Add --verbose flag", "--json"])
    if rc1 != 0:
        return {"passed": False, "message": "intake failed"}

    # Validate draft
    try:
        draft = _json.loads(out1)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            _json.dump(draft, tf)
            tf.flush()
            rc2, out2, _ = _run_script(validator, [tf.name, "--json"])
        import os
        os.unlink(tf.name)
    except Exception as e:
        return {"passed": False, "message": str(e)}

    if rc2 != 0:
        return {"passed": False, "message": "validator failed"}

    try:
        result = _json.loads(out2)
        return {"passed": result["overall"] == "PASS", "message": "validation=%s" % result["overall"]}
    except (_json.JSONDecodeError, KeyError):
        return {"passed": False, "message": "invalid validator output"}


def _test_packager_basic(script_dir):
    """Test packager with valid draft."""
    import json as _json
    import tempfile
    intake = script_dir / "vibe_workorder_intake.py"
    packager = script_dir / "vibe_workorder_packager.py"
    if not intake.exists() or not packager.exists():
        return {"passed": False, "message": "scripts not found"}

    # Generate draft
    rc1, out1, _ = _run_script(intake, ["Update docs", "--type", "doc", "--json"])
    if rc1 != 0:
        return {"passed": False, "message": "intake failed"}

    # Package draft
    try:
        draft = _json.loads(out1)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            _json.dump(draft, tf)
            tf.flush()
            rc2, out2, _ = _run_script(packager, [tf.name, "--json", "--compact"])
        import os
        os.unlink(tf.name)
    except Exception as e:
        return {"passed": False, "message": str(e)}

    if rc2 != 0:
        return {"passed": False, "message": "packager failed"}

    try:
        result = _json.loads(out2)
        return {"passed": result["total_chars"] > 0, "message": "chars=%d chunks=%d" % (result["total_chars"], result["chunk_count"])}
    except (_json.JSONDecodeError, KeyError):
        return {"passed": False, "message": "invalid packager output"}


def _test_preflight_router(script_dir):
    """Test preflight command via router."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["preflight", "Add --summary flag to snapshot"])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    if "Preflight" not in stdout:
        return {"passed": False, "message": "missing preflight output"}

    return {"passed": True, "message": "preflight chain works"}



def _test_registry_basic(script_dir):
    """Test registry basic operations: register, list, show."""
    import subprocess
    import tempfile
    import shutil

    registry_script = script_dir / "vibe_workorder_registry.py"
    if not registry_script.exists():
        return {"passed": False, "message": "registry script not found"}

    tmpdir = tempfile.mkdtemp(prefix="registry_smoke_")

    try:
        # Test register
        cmd = [sys.executable, str(registry_script), "register",
               "--registry-dir", tmpdir,
               "--id", "test-wo-001",
               "--title", "Test Work Order",
               "--risk-level", "low",
               "--base-sha", "abc123"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "register failed: %s" % result.stderr}

        # Test list
        cmd = [sys.executable, str(registry_script), "list",
               "--registry-dir", tmpdir]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "list failed: %s" % result.stderr}

        if "test-wo-001" not in result.stdout:
            return {"passed": False, "message": "registered entry not in list output"}

        # Test show
        cmd = [sys.executable, str(registry_script), "show",
               "--registry-dir", tmpdir,
               "--id", "test-wo-001"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "show failed: %s" % result.stderr}

        if "Test Work Order" not in result.stdout:
            return {"passed": False, "message": "title not in show output"}

        return {"passed": True, "message": "register/list/show work"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_registry_json(script_dir):
    """Test registry JSON output."""
    import subprocess
    import tempfile
    import shutil
    import json

    registry_script = script_dir / "vibe_workorder_registry.py"
    if not registry_script.exists():
        return {"passed": False, "message": "registry script not found"}

    tmpdir = tempfile.mkdtemp(prefix="registry_smoke_")

    try:
        # Register entry
        cmd = [sys.executable, str(registry_script), "register",
               "--registry-dir", tmpdir,
               "--id", "test-wo-json",
               "--title", "JSON Test",
               "--risk-level", "medium",
               "--status", "validated"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "register failed"}

        # Test list --json
        cmd = [sys.executable, str(registry_script), "list",
               "--registry-dir", tmpdir, "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "list --json failed"}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON output"}

        if "entries" not in data:
            return {"passed": False, "message": "missing entries field"}

        if len(data["entries"]) != 1:
            return {"passed": False, "message": "expected 1 entry, got %d" % len(data["entries"])}

        entry = data["entries"][0]
        if entry.get("workorder_id") != "test-wo-json":
            return {"passed": False, "message": "wrong workorder_id"}
        if entry.get("risk_level") != "medium":
            return {"passed": False, "message": "wrong risk_level"}
        if entry.get("status") != "validated":
            return {"passed": False, "message": "wrong status"}

        return {"passed": True, "message": "JSON output valid, fields correct"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_registry_router(script_dir):
    """Test registry via command router."""
    import subprocess
    import tempfile
    import shutil
    import json

    router_script = script_dir / "vibe_command_router.py"
    if not router_script.exists():
        return {"passed": False, "message": "router script not found"}

    tmpdir = tempfile.mkdtemp(prefix="registry_smoke_")

    try:
        # Register via router
        cmd = [sys.executable, str(router_script), "reg", "register",
               "--registry-dir", tmpdir,
               "--id", "test-wo-router",
               "--title", "Router Test"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "router register failed: %s" % result.stderr}

        # List via router
        cmd = [sys.executable, str(router_script), "reg", "list",
               "--registry-dir", tmpdir, "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "router list failed"}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON from router"}

        if len(data.get("entries", [])) != 1:
            return {"passed": False, "message": "expected 1 entry via router"}

        # Show via router alias wo-show
        cmd = [sys.executable, str(router_script), "reg", "show",
               "--registry-dir", tmpdir,
               "--id", "test-wo-router", "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "wo-show failed"}

        return {"passed": True, "message": "reg/wo-show aliases work"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_registry_readonly(script_dir):
    """Test registry is read-only by default."""
    import subprocess

    registry_script = script_dir / "vibe_workorder_registry.py"
    if not registry_script.exists():
        return {"passed": False, "message": "registry script not found"}

    # Try list without --registry-dir (should fail gracefully)
    cmd = [sys.executable, str(registry_script), "list"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

    if result.returncode == 0:
        return {"passed": False, "message": "list without --registry-dir should fail"}

    if "ERROR" not in result.stderr and "ERROR" not in result.stdout:
        return {"passed": False, "message": "missing error message"}

    return {"passed": True, "message": "graceful failure without registry dir"}



def _test_status_update(script_dir):
    """Test registry status update with valid transitions."""
    import subprocess
    import tempfile
    import shutil
    import json

    registry_script = script_dir / "vibe_workorder_registry.py"
    if not registry_script.exists():
        return {"passed": False, "message": "registry script not found"}

    tmpdir = tempfile.mkdtemp(prefix="status_smoke_")

    try:
        # Register entry
        cmd = [sys.executable, str(registry_script), "register",
               "--registry-dir", tmpdir,
               "--id", "test-wo-status",
               "--title", "Status Test"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "register failed"}

        # Test valid transition: draft → validated
        cmd = [sys.executable, str(registry_script), "update-status",
               "--registry-dir", tmpdir,
               "--id", "test-wo-status",
               "--status", "validated",
               "--reason", "All checks passed",
               "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "update-status failed: %s" % result.stderr}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON output"}

        if data.get("from_status") != "draft":
            return {"passed": False, "message": "wrong from_status"}
        if data.get("to_status") != "validated":
            return {"passed": False, "message": "wrong to_status"}

        return {"passed": True, "message": "valid transition works"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_status_invalid_transition(script_dir):
    """Test registry rejects invalid status transitions."""
    import subprocess
    import tempfile
    import shutil

    registry_script = script_dir / "vibe_workorder_registry.py"
    if not registry_script.exists():
        return {"passed": False, "message": "registry script not found"}

    tmpdir = tempfile.mkdtemp(prefix="status_smoke_")

    try:
        # Register entry
        cmd = [sys.executable, str(registry_script), "register",
               "--registry-dir", tmpdir,
               "--id", "test-wo-invalid",
               "--title", "Invalid Transition Test"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "register failed"}

        # Test invalid transition: draft → executed (should fail)
        cmd = [sys.executable, str(registry_script), "update-status",
               "--registry-dir", tmpdir,
               "--id", "test-wo-invalid",
               "--status", "executed",
               "--reason", "Skip approval"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        # Should fail with exit code 1
        if result.returncode == 0:
            return {"passed": False, "message": "invalid transition should fail"}

        if "Invalid transition" not in result.stderr:
            return {"passed": False, "message": "missing error message about invalid transition"}

        return {"passed": True, "message": "invalid transition rejected"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_approval_receipt(script_dir):
    """Test approval receipt creation and listing."""
    import subprocess
    import tempfile
    import shutil
    import json

    receipt_script = script_dir / "vibe_approval_receipt.py"
    if not receipt_script.exists():
        return {"passed": False, "message": "receipt script not found"}

    tmpdir = tempfile.mkdtemp(prefix="receipt_smoke_")

    try:
        # Create a test workorder entry
        entry_file = os.path.join(tmpdir, "test-wo-receipt.json")
        with open(entry_file, "w") as f:
            json.dump({
                "workorder_id": "test-wo-receipt",
                "title": "Receipt Test",
                "status": "packaged",
                "requires_human_approval": True,
                "changed_paths": ["scripts/test.py"],
                "stop_conditions": ["py_compile fails"]
            }, f)

        # Create receipt
        cmd = [sys.executable, str(receipt_script), "create",
               "--registry-dir", tmpdir,
               "--id", "test-wo-receipt",
               "--base-sha", "abc123",
               "--package-digest", "def456",
               "--approver", "human",
               "--approval-text", "Approved for execution",
               "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "create failed: %s" % result.stderr}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON output"}

        receipt = data.get("receipt", {})
        if not receipt.get("receipt_id"):
            return {"passed": False, "message": "missing receipt_id"}
        if not receipt.get("digest"):
            return {"passed": False, "message": "missing digest"}
        if receipt.get("requires_human_approval") != True:
            return {"passed": False, "message": "wrong requires_human_approval"}
        if "scripts/test.py" not in receipt.get("approved_scope", []):
            return {"passed": False, "message": "wrong approved_scope"}

        # List receipts
        cmd = [sys.executable, str(receipt_script), "list",
               "--registry-dir", tmpdir, "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "list failed"}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON from list"}

        if data.get("count") != 1:
            return {"passed": False, "message": "expected 1 receipt"}

        return {"passed": True, "message": "receipt create/list works"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_approval_router(script_dir):
    """Test approval receipt via command router."""
    import subprocess
    import tempfile
    import shutil
    import json

    router_script = script_dir / "vibe_command_router.py"
    if not router_script.exists():
        return {"passed": False, "message": "router script not found"}

    tmpdir = tempfile.mkdtemp(prefix="receipt_smoke_")

    try:
        # Create a test workorder entry
        entry_file = os.path.join(tmpdir, "test-wo-router-receipt.json")
        with open(entry_file, "w") as f:
            json.dump({
                "workorder_id": "test-wo-router-receipt",
                "title": "Router Receipt Test",
                "status": "packaged",
                "requires_human_approval": False,
                "changed_paths": [],
                "stop_conditions": []
            }, f)

        # Create receipt via router
        cmd = [sys.executable, str(router_script), "ar", "create",
               "--registry-dir", tmpdir,
               "--id", "test-wo-router-receipt",
               "--base-sha", "abc123",
               "--package-digest", "def456",
               "--approver", "automated",
               "--approval-text", "Auto-approved",
               "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "router receipt create failed: %s" % result.stderr}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON from router"}

        if not data.get("receipt", {}).get("receipt_id"):
            return {"passed": False, "message": "missing receipt_id from router"}

        return {"passed": True, "message": "ar (approve-receipt) alias works"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)



def _test_evidence_basic(script_dir):
    """Test evidence basic operations: create, list, show."""
    import subprocess
    import tempfile
    import shutil

    evidence_script = script_dir / "vibe_execution_evidence.py"
    if not evidence_script.exists():
        return {"passed": False, "message": "evidence script not found"}

    tmpdir = tempfile.mkdtemp(prefix="evidence_smoke_")

    try:
        # Create evidence
        cmd = [sys.executable, str(evidence_script), "create",
               "--evidence-dir", tmpdir,
               "--id", "test-wo-evidence",
               "--base-sha", "abc123",
               "--result-sha", "def456",
               "--smoke-result", "36/36 PASS",
               "--job-status", "review_passed"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "create failed: %s" % result.stderr}

        # List evidence
        cmd = [sys.executable, str(evidence_script), "list",
               "--evidence-dir", tmpdir]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "list failed: %s" % result.stderr}

        if "test-wo-evidence" not in result.stdout:
            return {"passed": False, "message": "created evidence not in list output"}

        # Show evidence
        cmd = [sys.executable, str(evidence_script), "show",
               "--evidence-dir", tmpdir,
               "--evidence-id", "ev-001"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "show failed: %s" % result.stderr}

        if "test-wo-evidence" not in result.stdout:
            return {"passed": False, "message": "workorder_id not in show output"}

        return {"passed": True, "message": "create/list/show work"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_evidence_json(script_dir):
    """Test evidence JSON output."""
    import subprocess
    import tempfile
    import shutil
    import json

    evidence_script = script_dir / "vibe_execution_evidence.py"
    if not evidence_script.exists():
        return {"passed": False, "message": "evidence script not found"}

    tmpdir = tempfile.mkdtemp(prefix="evidence_smoke_")

    try:
        # Create evidence with JSON
        cmd = [sys.executable, str(evidence_script), "create",
               "--evidence-dir", tmpdir,
               "--id", "test-wo-json",
               "--base-sha", "abc123",
               "--result-sha", "def456",
               "--pr-url", "https://github.com/test/pr/1",
               "--smoke-result", "36/36 PASS",
               "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "create failed"}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON output"}

        evidence = data.get("evidence", {})
        if evidence.get("workorder_id") != "test-wo-json":
            return {"passed": False, "message": "wrong workorder_id"}
        if evidence.get("base_sha") != "abc123":
            return {"passed": False, "message": "wrong base_sha"}
        if evidence.get("result_sha") != "def456":
            return {"passed": False, "message": "wrong result_sha"}
        if not evidence.get("digest"):
            return {"passed": False, "message": "missing digest"}

        return {"passed": True, "message": "JSON output valid, fields correct"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_evidence_router(script_dir):
    """Test evidence via command router."""
    import subprocess
    import tempfile
    import shutil
    import json

    router_script = script_dir / "vibe_command_router.py"
    if not router_script.exists():
        return {"passed": False, "message": "router script not found"}

    tmpdir = tempfile.mkdtemp(prefix="evidence_smoke_")

    try:
        # Create evidence via router
        cmd = [sys.executable, str(router_script), "ev", "create",
               "--evidence-dir", tmpdir,
               "--id", "test-wo-router-ev",
               "--base-sha", "abc123",
               "--result-sha", "def456",
               "--smoke-result", "36/36 PASS",
               "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "router evidence create failed: %s" % result.stderr}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON from router"}

        if not data.get("evidence", {}).get("evidence_id"):
            return {"passed": False, "message": "missing evidence_id from router"}

        # List via router
        cmd = [sys.executable, str(router_script), "ev", "list",
               "--evidence-dir", tmpdir, "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "router evidence list failed"}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON from router list"}

        if data.get("count") != 1:
            return {"passed": False, "message": "expected 1 evidence"}

        return {"passed": True, "message": "ev (evidence) alias works"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_evidence_readonly(script_dir):
    """Test evidence is read-only by default."""
    import subprocess

    evidence_script = script_dir / "vibe_execution_evidence.py"
    if not evidence_script.exists():
        return {"passed": False, "message": "evidence script not found"}

    # Try list without --evidence-dir (should fail gracefully)
    cmd = [sys.executable, str(evidence_script), "list"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

    if result.returncode == 0:
        return {"passed": False, "message": "list without --evidence-dir should fail"}

    if "ERROR" not in result.stderr and "ERROR" not in result.stdout:
        return {"passed": False, "message": "missing error message"}

    return {"passed": True, "message": "graceful failure without evidence dir"}



def _test_gate_allow(script_dir):
    """Test execution gate ALLOW scenario."""
    import subprocess
    import tempfile
    import shutil
    import json

    gate_script = script_dir / "vibe_execution_gate.py"
    if not gate_script.exists():
        return {"passed": False, "message": "gate script not found"}

    tmpdir = tempfile.mkdtemp(prefix="gate_smoke_")

    try:
        # Create approved registry entry
        entry_file = os.path.join(tmpdir, "test-wo-allow.json")
        with open(entry_file, "w") as f:
            json.dump({
                "workorder_id": "test-wo-allow",
                "title": "Allow Test",
                "status": "approved",
                "base_sha": "abc123",
                "risk_level": "low",
                "requires_human_approval": False,
                "changed_paths": ["scripts/test.py"],
                "forbidden_actions": ["push_to_main", "modify_secrets"],
                "stop_conditions": [],
                "allowed_paths": ["scripts/"],
                "audit_status": "clean"
            }, f)

        # Create approval receipt
        receipts_dir = os.path.join(tmpdir, "receipts")
        os.makedirs(receipts_dir, exist_ok=True)
        receipt_file = os.path.join(receipts_dir, "receipt-001.json")
        with open(receipt_file, "w") as f:
            json.dump({
                "receipt_id": "receipt-001",
                "workorder_id": "test-wo-allow",
                "base_sha": "abc123",
                "package_digest": "def456",
                "approver": "human",
                "approval_text": "Approved"
            }, f)

        # Run gate check
        cmd = [sys.executable, str(gate_script), "check",
               "--registry-dir", tmpdir,
               "--id", "test-wo-allow",
               "--current-main-sha", "abc123",
               "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "gate check failed: %s" % result.stderr}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON output"}

        if data.get("verdict") != "ALLOW":
            return {"passed": False, "message": "expected ALLOW, got %s" % data.get("verdict")}

        return {"passed": True, "message": "ALLOW verdict correct"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_gate_block(script_dir):
    """Test execution gate BLOCK scenario (base_sha mismatch)."""
    import subprocess
    import tempfile
    import shutil
    import json

    gate_script = script_dir / "vibe_execution_gate.py"
    if not gate_script.exists():
        return {"passed": False, "message": "gate script not found"}

    tmpdir = tempfile.mkdtemp(prefix="gate_smoke_")

    try:
        # Create approved registry entry
        entry_file = os.path.join(tmpdir, "test-wo-block.json")
        with open(entry_file, "w") as f:
            json.dump({
                "workorder_id": "test-wo-block",
                "title": "Block Test",
                "status": "approved",
                "base_sha": "abc123",
                "risk_level": "low",
                "requires_human_approval": False,
                "changed_paths": ["scripts/test.py"],
                "forbidden_actions": ["push_to_main"],
                "stop_conditions": [],
                "allowed_paths": ["scripts/"],
                "audit_status": "clean"
            }, f)

        # Run gate check with WRONG SHA
        cmd = [sys.executable, str(gate_script), "check",
               "--registry-dir", tmpdir,
               "--id", "test-wo-block",
               "--current-main-sha", "WRONG_SHA",
               "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        # Should fail with exit code 1 (BLOCK)
        if result.returncode != 1:
            return {"passed": False, "message": "expected exit code 1 for BLOCK, got %d" % result.returncode}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON output"}

        if data.get("verdict") != "BLOCK":
            return {"passed": False, "message": "expected BLOCK, got %s" % data.get("verdict")}

        # Check that base_sha_match is BLOCK
        checks = data.get("checks", [])
        base_sha_check = next((c for c in checks if c["name"] == "base_sha_match"), None)
        if not base_sha_check or base_sha_check["result"] != "BLOCK":
            return {"passed": False, "message": "base_sha_match should be BLOCK"}

        return {"passed": True, "message": "BLOCK verdict on SHA mismatch"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_gate_review(script_dir):
    """Test execution gate REVIEW scenario (audit_tainted)."""
    import subprocess
    import tempfile
    import shutil
    import json

    gate_script = script_dir / "vibe_execution_gate.py"
    if not gate_script.exists():
        return {"passed": False, "message": "gate script not found"}

    tmpdir = tempfile.mkdtemp(prefix="gate_smoke_")

    try:
        # Create audit_tainted registry entry
        entry_file = os.path.join(tmpdir, "test-wo-review.json")
        with open(entry_file, "w") as f:
            json.dump({
                "workorder_id": "test-wo-review",
                "title": "Review Test",
                "status": "approved",
                "base_sha": "abc123",
                "risk_level": "low",
                "requires_human_approval": False,
                "changed_paths": ["scripts/test.py"],
                "forbidden_actions": ["push_to_main"],
                "stop_conditions": ["py_compile fails"],
                "allowed_paths": ["scripts/"],
                "audit_status": "audit_tainted"
            }, f)

        # Run gate check
        cmd = [sys.executable, str(gate_script), "check",
               "--registry-dir", tmpdir,
               "--id", "test-wo-review",
               "--current-main-sha", "abc123",
               "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        # Should fail with exit code 1 (BLOCK due to audit_tainted)
        if result.returncode != 1:
            return {"passed": False, "message": "expected exit code 1 for BLOCK, got %d" % result.returncode}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON output"}

        if data.get("verdict") != "BLOCK":
            return {"passed": False, "message": "expected BLOCK, got %s" % data.get("verdict")}

        # Check that audit_lock is BLOCK
        checks = data.get("checks", [])
        audit_check = next((c for c in checks if c["name"] == "audit_lock"), None)
        if not audit_check or audit_check["result"] != "BLOCK":
            return {"passed": False, "message": "audit_lock should be BLOCK"}

        return {"passed": True, "message": "BLOCK verdict on audit_tainted"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_gate_router(script_dir):
    """Test execution gate via command router."""
    import subprocess
    import tempfile
    import shutil
    import json

    router_script = script_dir / "vibe_command_router.py"
    if not router_script.exists():
        return {"passed": False, "message": "router script not found"}

    tmpdir = tempfile.mkdtemp(prefix="gate_smoke_")

    try:
        # Create approved registry entry
        entry_file = os.path.join(tmpdir, "test-wo-router-gate.json")
        with open(entry_file, "w") as f:
            json.dump({
                "workorder_id": "test-wo-router-gate",
                "title": "Router Gate Test",
                "status": "approved",
                "base_sha": "abc123",
                "risk_level": "low",
                "requires_human_approval": False,
                "changed_paths": [],
                "forbidden_actions": ["push_to_main"],
                "stop_conditions": [],
                "allowed_paths": ["scripts/"],
                "audit_status": "clean"
            }, f)

        # Run gate via router
        cmd = [sys.executable, str(router_script), "gate",
               "--registry-dir", tmpdir,
               "--id", "test-wo-router-gate",
               "--current-main-sha", "abc123",
               "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "router gate failed: %s" % result.stderr}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON from router"}

        if data.get("verdict") not in ("ALLOW", "REVIEW"):
            return {"passed": False, "message": "unexpected verdict: %s" % data.get("verdict")}

        return {"passed": True, "message": "gate/ready-run aliases work"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)



def _test_safe_executor_block(script_dir):
    """Test safe executor blocks on non-ALLOW gate."""
    import subprocess
    import tempfile
    import shutil
    import json
    import os

    executor_script = script_dir / "vibe_safe_executor.py"
    if not executor_script.exists():
        return {"passed": False, "message": "executor script not found"}

    tmpdir = tempfile.mkdtemp(prefix="executor_smoke_")

    try:
        entry_file = os.path.join(tmpdir, "test-wo-exec.json")
        with open(entry_file, "w") as f:
            json.dump({
                "workorder_id": "test-wo-exec",
                "status": "approved",
                "base_sha": "abc123",
                "risk_level": "low",
                "requires_human_approval": False,
                "stop_conditions": ["py_compile fails"],
                "allowed_paths": ["scripts/"],
                "forbidden_actions": ["push_to_main"],
                "audit_status": "clean"
            }, f)

        cmd = [sys.executable, str(executor_script), "plan",
               "--registry-dir", tmpdir,
               "--id", "test-wo-exec",
               "--current-main-sha", "abc123",
               "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 1:
            return {"passed": False, "message": "expected exit 1, got %d" % result.returncode}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON"}

        if data.get("status") != "BLOCKED":
            return {"passed": False, "message": "expected BLOCKED, got %s" % data.get("status")}

        return {"passed": True, "message": "blocks on non-ALLOW gate"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_safe_executor_router(script_dir):
    """Test safe executor via command router."""
    import subprocess
    import tempfile
    import shutil
    import json
    import os

    router_script = script_dir / "vibe_command_router.py"
    if not router_script.exists():
        return {"passed": False, "message": "router script not found"}

    tmpdir = tempfile.mkdtemp(prefix="executor_smoke_")

    try:
        entry_file = os.path.join(tmpdir, "test-wo-exec-router.json")
        with open(entry_file, "w") as f:
            json.dump({
                "workorder_id": "test-wo-exec-router",
                "status": "approved",
                "base_sha": "abc123",
                "risk_level": "low",
                "requires_human_approval": False,
                "stop_conditions": [],
                "allowed_paths": ["scripts/"],
                "forbidden_actions": ["push_to_main"],
                "audit_status": "clean"
            }, f)

        receipts_dir = os.path.join(tmpdir, "receipts")
        os.makedirs(receipts_dir, exist_ok=True)
        receipt_path = os.path.join(receipts_dir, "receipt-001.json")
        with open(receipt_path, "w") as f:
            json.dump({
                "receipt_id": "receipt-001",
                "workorder_id": "test-wo-exec-router",
                "base_sha": "abc123"
            }, f)

        cmd = [sys.executable, str(router_script), "se", "plan",
               "--registry-dir", tmpdir,
               "--id", "test-wo-exec-router",
               "--current-main-sha", "abc123",
               "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"passed": False, "message": "router executor failed: %s" % result.stderr}

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"passed": False, "message": "invalid JSON"}

        if data.get("status") != "READY":
            return {"passed": False, "message": "expected READY, got %s" % data.get("status")}

        if not data.get("execution_plan", {}).get("phases"):
            return {"passed": False, "message": "missing execution plan phases"}

        return {"passed": True, "message": "se/plan aliases work, READY status"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)



# --- Adapter and Transcript Tests (added for replay smoke) ---

def _test_adapter_capabilities(script_dir):
    rc, out, err = _run_script(script_dir / "vibe_executor_adapter.py", ["capabilities", "--json"])
    if rc != 0:
        return {"passed": False, "message": f"exit {rc}"}
    data = json.loads(out)
    if "adapters" not in data or "noop" not in data["adapters"]:
        return {"passed": False, "message": "missing adapters"}
    return {"passed": True, "message": f"adapters: {', '.join(data['adapters'].keys())}"}

def _test_adapter_plan_json(script_dir):
    rc, out, err = _run_script(script_dir / "vibe_executor_adapter.py",
        ["plan", "--adapter", "dry-run", "--id", "smoke-test", "--base-sha", "abc", "--json"])
    if rc != 0:
        return {"passed": False, "message": f"exit {rc}"}
    data = json.loads(out)
    if data["adapter_name"] != "dry-run":
        return {"passed": False, "message": "wrong adapter"}
    return {"passed": True, "message": f"dry-run plan {len(data['execution_plan']['steps'])} steps"}

def _test_adapter_router(script_dir):
    rc, out, err = _run_script(script_dir / "vibe_command_router.py", ["adapter", "capabilities", "--json"])
    if rc != 0:
        return {"passed": False, "message": f"exit {rc}"}
    data = json.loads(out)
    if "adapters" not in data:
        return {"passed": False, "message": "missing adapters"}
    return {"passed": True, "message": "router adapter OK"}

def _test_transcript_create_list(script_dir):
    import tempfile
    txn_dir = tempfile.mkdtemp(prefix="smoke_txn_")
    rc, out, err = _run_script(script_dir / "vibe_execution_transcript.py",
        ["create", "--id", "smoke-test", "--adapter", "noop", "--base-sha", "abc",
         "--transcript-dir", txn_dir, "--json"])
    if rc != 0:
        return {"passed": False, "message": f"create exit {rc}"}
    data = json.loads(out)
    if "digest" not in data:
        return {"passed": False, "message": "missing digest"}
    rc2, out2, err2 = _run_script(script_dir / "vibe_execution_transcript.py",
        ["list", "--transcript-dir", txn_dir, "--json"])
    if rc2 != 0:
        return {"passed": False, "message": f"list exit {rc2}"}
    data2 = json.loads(out2)
    if data2["count"] < 1:
        return {"passed": False, "message": "count < 1"}
    return {"passed": True, "message": f"create+list OK: {data['transcript_id']}"}


def _test_loop_summary(script_dir):
    rc, out, err = _run_script(script_dir / "vibe_loop_summary.py", ["--compact"])
    if rc != 0:
        return {"passed": False, "message": f"exit {rc}"}
    if "Autonomous Loop Summary" not in out:
        return {"passed": False, "message": "missing title"}
    if "Components:" not in out:
        return {"passed": False, "message": "missing components"}
    return {"passed": True, "message": "loop summary OK"}

def _test_loop_summary_json(script_dir):
    rc, out, err = _run_script(script_dir / "vibe_loop_summary.py", ["--json"])
    if rc != 0:
        return {"passed": False, "message": f"exit {rc}"}
    import json
    data = json.loads(out)
    if "components" not in data or len(data["components"]) < 10:
        return {"passed": False, "message": f"too few components: {len(data.get('components', []))}"}
    return {"passed": True, "message": f"loop summary JSON OK: {len(data['components'])} components"}

def _test_loop_summary_router(script_dir):
    rc, out, err = _run_script(script_dir / "vibe_command_router.py", ["ls", "--json"])
    if rc != 0:
        return {"passed": False, "message": f"exit {rc}"}
    import json
    data = json.loads(out)
    if "components" not in data:
        return {"passed": False, "message": "missing components"}
    return {"passed": True, "message": "router loop-summary OK"}

def run_tests(jobs_dir=None):
    """Run all smoke tests."""
    if jobs_dir is None:
        jobs_dir = os.path.expanduser("~/vibedev/jobs")
    
    script_dir = Path(__file__).parent
    
    tests = []
    
    # Test 1: Command Router help
    tests.append(_run_test("command_router_help", lambda: _test_command_router_help(script_dir)))
    
    # Test 2: Command Router snapshot
    tests.append(_run_test("command_router_snapshot", lambda: _test_command_router_snapshot(script_dir, jobs_dir)))
    
    # Test 3: Command Router advisor
    tests.append(_run_test("command_router_advisor", lambda: _test_command_router_advisor(script_dir, jobs_dir)))
    
    # Test 4: Command Router dispatch
    tests.append(_run_test("command_router_dispatch", lambda: _test_command_router_dispatch(script_dir, jobs_dir)))
    
    # Test 5: Command Router batch plan
    tests.append(_run_test("command_router_batch_plan", lambda: _test_command_router_batch_plan(script_dir, jobs_dir)))
    
    # Test 6: Health Check
    tests.append(_run_test("health_check", lambda: _test_health_check(script_dir, jobs_dir)))
    
    # Test 7: Operator Snapshot
    tests.append(_run_test("operator_snapshot", lambda: _test_operator_snapshot(script_dir, jobs_dir)))
    
    # Test 8: Queue Advisor
    tests.append(_run_test("queue_advisor", lambda: _test_queue_advisor(script_dir, jobs_dir)))
    
    # Test 9: Dispatch Planner
    tests.append(_run_test("dispatch_planner", lambda: _test_dispatch_planner(script_dir, jobs_dir)))
    
    # Test 10: Batch Plan
    tests.append(_run_test("batch_plan", lambda: _test_batch_plan(script_dir, jobs_dir)))
    
    # Test 11: Recommendation Consistency
    tests.append(_run_test("recommendation_consistency", lambda: _test_recommendation_consistency(script_dir, jobs_dir)))
    
    # Test 12: Intake - basic markdown
    tests.append(_run_test("intake_basic", lambda: _test_intake_basic(script_dir)))
    
    # Test 13: Intake - JSON output
    tests.append(_run_test("intake_json", lambda: _test_intake_json(script_dir)))
    
    # Test 14: Intake - risk classification
    tests.append(_run_test("intake_risk_classification", lambda: _test_intake_risk_classification(script_dir)))
    
    # Test 15: Intake - type detection
    tests.append(_run_test("intake_type_detection", lambda: _test_intake_type_detection(script_dir)))
    
    # Test 16: Intake - router integration
    tests.append(_run_test("intake_router", lambda: _test_intake_router(script_dir)))
    
    # Test 17: Release Notes - basic
    tests.append(_run_test("release_notes_basic", lambda: _test_release_notes_basic(script_dir)))
    
    # Test 18: Release Notes - JSON
    tests.append(_run_test("release_notes_json", lambda: _test_release_notes_json(script_dir)))
    
    # Test 19: Release Notes - safety
    tests.append(_run_test("release_notes_safety", lambda: _test_release_notes_safety(script_dir)))
    
    # Test 20: Release Notes - router
    tests.append(_run_test("release_notes_router", lambda: _test_release_notes_router(script_dir)))
    
    # Test 21: Dashboard - text output
    tests.append(_run_test("dashboard_text", lambda: _test_dashboard_text(script_dir)))
    
    # Test 22: Dashboard - JSON output
    tests.append(_run_test("dashboard_json", lambda: _test_dashboard_json(script_dir)))
    
    # Test 23: Dashboard - aliases
    tests.append(_run_test("dashboard_aliases", lambda: _test_dashboard_aliases(script_dir)))
    
    # Test 24: Daily Report - text
    tests.append(_run_test("daily_report_text", lambda: _test_daily_report_text(script_dir)))
    
    # Test 25: Daily Report - JSON
    tests.append(_run_test("daily_report_json", lambda: _test_daily_report_json(script_dir)))
    
    # Test 26: Validator - basic
    tests.append(_run_test("validator_basic", lambda: _test_validator_basic(script_dir)))
    
    # Test 27: Packager - basic
    tests.append(_run_test("packager_basic", lambda: _test_packager_basic(script_dir)))
    
    # Test 28: Preflight - router
    tests.append(_run_test("preflight_router", lambda: _test_preflight_router(script_dir)))
    

    # Test 29: Registry - basic operations
    tests.append(_run_test("registry_basic", lambda: _test_registry_basic(script_dir)))
    

    # Test 33: Status Update - valid transition
    tests.append(_run_test("status_update", lambda: _test_status_update(script_dir)))
    
    # Test 34: Status Update - invalid transition
    tests.append(_run_test("status_invalid_transition", lambda: _test_status_invalid_transition(script_dir)))
    
    # Test 35: Approval Receipt - create/list
    tests.append(_run_test("approval_receipt", lambda: _test_approval_receipt(script_dir)))
    

    # Test 37: Evidence - basic operations
    tests.append(_run_test("evidence_basic", lambda: _test_evidence_basic(script_dir)))
    

    # Test 41: Gate - ALLOW scenario
    tests.append(_run_test("gate_allow", lambda: _test_gate_allow(script_dir)))
    
    # Test 42: Gate - BLOCK scenario (SHA mismatch)
    tests.append(_run_test("gate_block", lambda: _test_gate_block(script_dir)))
    
    # Test 43: Gate - BLOCK scenario (audit_tainted)
    tests.append(_run_test("gate_review", lambda: _test_gate_review(script_dir)))
    
    # Test 44: Gate - router integration
    tests.append(_run_test("gate_router", lambda: _test_gate_router(script_dir)))
    
    # Test 45: Safe Executor - blocks on non-ALLOW
    tests.append(_run_test("safe_executor_block", lambda: _test_safe_executor_block(script_dir)))
    
    # Test 46: Safe Executor - router integration
    tests.append(_run_test("safe_executor_router", lambda: _test_safe_executor_router(script_dir)))
    # Test 38: Evidence - JSON output
    tests.append(_run_test("evidence_json", lambda: _test_evidence_json(script_dir)))
    
    # Test 39: Evidence - router integration
    tests.append(_run_test("evidence_router", lambda: _test_evidence_router(script_dir)))
    
    # Test 40: Evidence - read-only behavior
    tests.append(_run_test("evidence_readonly", lambda: _test_evidence_readonly(script_dir)))
    # Test 36: Approval Receipt - router integration
    tests.append(_run_test("approval_router", lambda: _test_approval_router(script_dir)))
    # Test 30: Registry - JSON output
    tests.append(_run_test("registry_json", lambda: _test_registry_json(script_dir)))
    
    # Test 31: Registry - router integration
    tests.append(_run_test("registry_router", lambda: _test_registry_router(script_dir)))
    
    # Test 32: Registry - read-only behavior
    tests.append(_run_test("registry_readonly", lambda: _test_registry_readonly(script_dir)))

    # Test 47: Adapter - capabilities JSON
    tests.append(_run_test("adapter_capabilities", lambda: _test_adapter_capabilities(script_dir)))

    # Test 48: Adapter - plan JSON
    tests.append(_run_test("adapter_plan_json", lambda: _test_adapter_plan_json(script_dir)))

    # Test 49: Adapter - router integration
    tests.append(_run_test("adapter_router", lambda: _test_adapter_router(script_dir)))

    # Test 50: Transcript - create and list
    tests.append(_run_test("transcript_create_list", lambda: _test_transcript_create_list(script_dir)))
    # Test 47: Adapter - capabilities JSON
    tests.append(_run_test("adapter_capabilities", lambda: _test_adapter_capabilities(script_dir)))

    # Test 48: Adapter - plan JSON
    tests.append(_run_test("adapter_plan_json", lambda: _test_adapter_plan_json(script_dir)))

    # Test 49: Adapter - router integration
    tests.append(_run_test("adapter_router", lambda: _test_adapter_router(script_dir)))

    # Test 50: Transcript - create and list
    tests.append(_run_test("transcript_create_list", lambda: _test_transcript_create_list(script_dir)))


    # Test 51: Loop Summary - compact
    tests.append(_run_test("loop_summary", lambda: _test_loop_summary(script_dir)))

    # Test 52: Loop Summary - JSON
    tests.append(_run_test("loop_summary_json", lambda: _test_loop_summary_json(script_dir)))

    # Test 53: Loop Summary - router integration
    tests.append(_run_test("loop_summary_router", lambda: _test_loop_summary_router(script_dir)))
    return tests


def build_parser():
    parser = argparse.ArgumentParser(
        prog="test_toolchain_smoke",
        description="Toolchain Smoke Suite v1 - Local smoke test for all orchestrator tools.",
    )
    parser.add_argument("--json", dest="output_json", action="store_true", default=False)
    parser.add_argument("--jobs-dir", default=None)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    jobs_dir = args.jobs_dir or os.path.expanduser("~/vibedev/jobs")
    
    tests = run_tests(jobs_dir)
    
    # Count results
    passed_count = sum(1 for _, passed, _ in tests if passed)
    failed_count = sum(1 for _, passed, _ in tests if not passed)
    
    # Determine overall result
    overall = "PASS" if failed_count == 0 else "FAIL"
    
    if args.output_json:
        result = {
            "overall": overall,
            "passed": passed_count,
            "failed": failed_count,
            "tests": [
                {"name": name, "passed": passed, "message": msg}
                for name, passed, msg in tests
            ],
        }
        print(json.dumps(result, indent=2))
    else:
        print("=" * 40)
        print("  Toolchain Smoke Suite v1")
        print("=" * 40)
        for name, passed, msg in tests:
            icon = "✓" if passed else "✗"
            status = "PASS" if passed else "FAIL"
            print(f"  {icon} {name}: {status} - {msg}")
        print("-" * 40)
        print(f"  Overall: {overall} ({passed_count} passed, {failed_count} failed)")
        print("=" * 40)
    
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
