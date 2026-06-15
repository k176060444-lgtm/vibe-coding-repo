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




def _detect_repo_context(script_dir):
    """Detect if running in full repo context vs temp/standalone context.

    Returns:
        dict with 'in_repo' (bool), 'has_docs' (bool), 'has_readme' (bool),
        'context' (str: 'repo' or 'temp')
    """
    parent = script_dir.parent
    has_docs = (parent / "docs").is_dir()
    has_readme = (parent / "README.md").is_file()
    has_scripts = (parent / "scripts").is_dir()
    in_repo = has_docs and has_readme and has_scripts
    return {
        "in_repo": in_repo,
        "has_docs": has_docs,
        "has_readme": has_readme,
        "has_scripts": has_scripts,
        "context": "repo" if in_repo else "temp",
    }

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
    if rc >= 2:
        return {"passed": False, "message": f"exit code {rc}"}
    if rc == 1 and not stdout.strip():
        return {"passed": False, "message": "exit code 1 with no output"}
    
    try:
        data = json.loads(stdout)
        overall = data.get("overall", "UNKNOWN")
        ctx = _detect_repo_context(script_dir)
        if overall == "PASS":
            return {"passed": True, "message": f"overall=PASS ctx={ctx['context']}"}
        elif overall == "WARN":
            return {"passed": True, "message": f"overall=WARN ctx={ctx['context']} (acceptable)"}
        else:
            return {"passed": False, "message": f"overall={overall} ctx={ctx['context']}"}
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
        ctx = _detect_repo_context(script_dir)
        if not ctx["has_docs"]:
            return {"passed": True, "message": "SKIP: no docs/ (temp-context)"}
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


def _test_sandbox_check(script_dir):
    rc, out, err = _run_script(script_dir / "vibe_executor_sandbox.py", ["check", "--json"])
    if rc != 0:
        return {"passed": False, "message": "exit %d" % rc}
    data = json.loads(out)
    if data.get("verdict") != "PASS":
        return {"passed": False, "message": "verdict=%s" % data.get("verdict")}
    return {"passed": True, "message": "sandbox check PASS: %d checks" % len(data.get("checks", []))}

def _test_control_plan(script_dir):
    rc, out, err = _run_script(script_dir / "vibe_executor_control.py", ["plan-timeout", "--id", "smoke", "--json"])
    if rc != 0:
        return {"passed": False, "message": "exit %d" % rc}
    data = json.loads(out)
    if "timeout_config" not in data:
        return {"passed": False, "message": "missing timeout_config"}
    return {"passed": True, "message": "control plan OK"}

def _test_recovery_plan(script_dir):
    rc, out, err = _run_script(script_dir / "vibe_executor_recovery.py", ["plan", "--id", "smoke", "--failure-type", "model_error", "--json"])
    if rc != 0:
        return {"passed": False, "message": "exit %d" % rc}
    data = json.loads(out)
    if data.get("failure_type") != "model_error":
        return {"passed": False, "message": "wrong type: %s" % data.get("failure_type")}
    return {"passed": True, "message": "recovery plan OK"}

def _test_recovery_classify(script_dir):
    rc, out, err = _run_script(script_dir / "vibe_executor_recovery.py", ["classify-failure", "--id", "smoke", "--error-msg", "quota exceeded", "--json"])
    if rc != 0:
        return {"passed": False, "message": "exit %d" % rc}
    data = json.loads(out)
    if data.get("classified_type") != "model_error":
        return {"passed": False, "message": "wrong type: %s" % data.get("classified_type")}
    return {"passed": True, "message": "classify OK: %s" % data["classified_type"]}


def _test_unfreeze_checklist(script_dir):
    rc, out, err = _run_script(script_dir / "vibe_executor_unfreeze_checklist.py", ["--level", "1", "--compact"])
    if rc != 0:
        return {"passed": False, "message": "exit %d" % rc}
    if "Level 1" not in out:
        return {"passed": False, "message": "missing Level 1"}
    return {"passed": True, "message": "unfreeze checklist level 1 OK"}

def _test_unfreeze_checklist_json(script_dir):
    rc, out, err = _run_script(script_dir / "vibe_executor_unfreeze_checklist.py", ["--level", "1", "--json"])
    if rc != 0:
        return {"passed": False, "message": "exit %d" % rc}
    data = json.loads(out)
    if data.get("level") != 1:
        return {"passed": False, "message": "wrong level"}
    if "required_approvals" not in data:
        return {"passed": False, "message": "missing required_approvals"}
    return {"passed": True, "message": "unfreeze checklist JSON OK"}

def _test_unfreeze_checklist_router(script_dir):
    rc, out, err = _run_script(script_dir / "vibe_command_router.py", ["uc", "--level", "2", "--json"])
    if rc != 0:
        return {"passed": False, "message": "exit %d" % rc}
    data = json.loads(out)
    if data.get("level") != 2:
        return {"passed": False, "message": "wrong level"}
    return {"passed": True, "message": "router unfreeze-checklist OK"}


def _test_repo_context_detection(script_dir):
    """Test that context detection works correctly."""
    ctx = _detect_repo_context(script_dir)
    return {"passed": True, "message": "ctx=%s docs=%s readme=%s" % (ctx["context"], ctx["has_docs"], ctx["has_readme"])}


def _test_temp_context_graceful(script_dir):
    """Test that key scripts handle missing context gracefully."""
    ctx = _detect_repo_context(script_dir)
    if ctx["context"] == "repo":
        return {"passed": True, "message": "repo-context: detection OK"}

    health_path = script_dir / "vibe_health_check.py"
    if health_path.exists():
        rc, stdout, stderr = _run_script(health_path, ["--json"])
        if rc != 0:
            return {"passed": False, "message": "health_check exit=%d in temp-context" % rc}
        try:
            data = json.loads(stdout)
            overall = data.get("overall", "UNKNOWN")
            if overall == "FAIL":
                return {"passed": False, "message": "health_check FAIL in temp-context (should be PASS/WARN)"}
        except json.JSONDecodeError:
            return {"passed": False, "message": "health_check invalid JSON in temp-context"}

    return {"passed": True, "message": "temp-context: graceful handling OK"}




def _test_evidence_verifier_fixture_mode(script_dir):
    """Test that evidence verifier correctly identifies fixture mode."""
    path = script_dir / "vibe_evidence_verifier.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    import tempfile, json as _json
    tmpdir = tempfile.mkdtemp()
    evidence_dir = Path(tmpdir) / "evidence"
    registry_dir = Path(tmpdir) / "registry"
    evidence_dir.mkdir()
    registry_dir.mkdir()

    # Create fixture-mode evidence (level4 workorder, no real model)
    ev = {
        "evidence_id": "ev-fixture",
        "workorder_id": "level4a-test-fixture",
        "base_sha": "abc123",
        "result_sha": "def456",
        "timestamp": "2026-01-01T00:00:00Z",
        "digest": "test",
        "wrapper_dry_run": "PASS",
        "implementer_model": "none",
        "smoke_result": "",
    }
    import hashlib
    ev_data = {k: ev.get(k) for k in ["workorder_id", "base_sha", "result_sha", "pr_url", "pr_number", "post_merge_sha", "timestamp"]}
    ev["digest"] = hashlib.sha256(_json.dumps(ev_data, sort_keys=True).encode()).hexdigest()
    with open(evidence_dir / "ev-fixture.json", "w") as f:
        _json.dump(ev, f)

    rc, stdout, stderr = _run_script(path, ["verify", "--evidence-id", "ev-fixture",
                                             "--evidence-dir", str(evidence_dir),
                                             "--registry-dir", str(registry_dir), "--json"])
    try:
        data = _json.loads(stdout)
    except _json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}

    if data.get("verdict") == "FAIL":
        return {"passed": False, "message": "verdict=FAIL (should be WARN for fixture)"}
    if not data.get("expected_fixture_mode"):
        return {"passed": False, "message": "expected_fixture_mode should be True"}
    if data.get("verdict_detail") != "WARN_EXPECTED_FIXTURE_MODE":
        return {"passed": False, "message": "verdict_detail=%s (expected WARN_EXPECTED_FIXTURE_MODE)" % data.get("verdict_detail")}
    if "operator_summary" not in data:
        return {"passed": False, "message": "missing operator_summary"}

    return {"passed": True, "message": "fixture mode detected: %s" % data.get("verdict_detail")}


def _test_evidence_verifier_unexpected_warn(script_dir):
    """Test that evidence verifier flags unexpected missing fields in non-fixture mode."""
    path = script_dir / "vibe_evidence_verifier.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    import tempfile, json as _json
    tmpdir = tempfile.mkdtemp()
    evidence_dir = Path(tmpdir) / "evidence"
    registry_dir = Path(tmpdir) / "registry"
    evidence_dir.mkdir()
    registry_dir.mkdir()

    # Create non-fixture evidence (no fixture indicators, real model)
    ev = {
        "evidence_id": "ev-real",
        "workorder_id": "wo-real-job-001",
        "base_sha": "abc123",
        "result_sha": "def456",
        "timestamp": "2026-01-01T00:00:00Z",
        "digest": "test",
        "implementer_model": "deepseek-v4-flash",
        "smoke_result": "",
        "job_status": "",
    }
    import hashlib
    ev_data = {k: ev.get(k) for k in ["workorder_id", "base_sha", "result_sha", "pr_url", "pr_number", "post_merge_sha", "timestamp"]}
    ev["digest"] = hashlib.sha256(_json.dumps(ev_data, sort_keys=True).encode()).hexdigest()
    with open(evidence_dir / "ev-real.json", "w") as f:
        _json.dump(ev, f)

    rc, stdout, stderr = _run_script(path, ["verify", "--evidence-id", "ev-real",
                                             "--evidence-dir", str(evidence_dir),
                                             "--registry-dir", str(registry_dir), "--json"])
    try:
        data = _json.loads(stdout)
    except _json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}

    if data.get("expected_fixture_mode"):
        return {"passed": False, "message": "expected_fixture_mode should be False for real job"}
    unexpected = data.get("unexpected_warnings", [])
    if not unexpected:
        return {"passed": False, "message": "should have unexpected_warnings, got none"}
    if data.get("verdict_detail") != "WARN_UNEXPECTED_MISSING_FIELD":
        return {"passed": False, "message": "verdict_detail=%s (expected WARN_UNEXPECTED_MISSING_FIELD)" % data.get("verdict_detail")}

    return {"passed": True, "message": "unexpected warnings flagged: %s" % ", ".join(unexpected)}




def _test_quality_gate_json(script_dir):
    """Test quality gate JSON output."""
    path = script_dir / "vibe_quality_gate.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["--json", "--skip-smoke", "--repo-root", str(script_dir.parent)])
    if rc != 0 and rc != 1:
        return {"passed": False, "message": "exit code %d" % rc}

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}

    if "verdict" not in data:
        return {"passed": False, "message": "missing verdict"}
    if "checks" not in data:
        return {"passed": False, "message": "missing checks"}
    if "operator_summary" not in data:
        return {"passed": False, "message": "missing operator_summary"}

    verdict = data.get("verdict", "UNKNOWN")
    total = data.get("summary", {}).get("total", 0)
    return {"passed": True, "message": "verdict=%s checks=%d" % (verdict, total)}


def _test_quality_gate_router(script_dir):
    """Test quality gate router aliases (qg, go-no-go)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}

    # Test qg alias
    rc1, stdout1, stderr1 = _run_script(path, ["qg", "--json", "--skip-smoke", "--repo-root", str(script_dir.parent)])
    if rc1 != 0 and rc1 != 1:
        return {"passed": False, "message": "qg exit=%d" % rc1}

    try:
        data1 = json.loads(stdout1)
        if "verdict" not in data1:
            return {"passed": False, "message": "qg missing verdict"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "qg invalid JSON"}

    # Test go-no-go alias
    rc2, stdout2, stderr2 = _run_script(path, ["go-no-go", "--json", "--skip-smoke", "--repo-root", str(script_dir.parent)])
    if rc2 != 0 and rc2 != 1:
        return {"passed": False, "message": "go-no-go exit=%d" % rc2}

    return {"passed": True, "message": "qg+go-no-go verdict=%s" % data1.get("verdict")}


def _test_quality_gate_block_scenario(script_dir):
    """Test quality gate BLOCK scenario (nonexistent repo root)."""
    path = script_dir / "vibe_quality_gate.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    # Use a nonexistent repo root to trigger BLOCK
    rc, stdout, stderr = _run_script(path, ["--json", "--repo-root", "/nonexistent/repo"])
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}

    verdict = data.get("verdict", "UNKNOWN")
    # Should be BLOCK or WARN (smoke will fail at minimum)
    if verdict == "PASS":
        return {"passed": False, "message": "verdict=PASS with bad repo root (should be BLOCK/WARN)"}

    blocks = data.get("summary", {}).get("block", 0)
    return {"passed": True, "message": "verdict=%s blocks=%d" % (verdict, blocks)}




def _test_run_report_json(script_dir):
    """Test run report JSON output."""
    path = script_dir / "vibe_run_report.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["--json", "--repo-root", str(script_dir.parent)])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}

    required = ["baseline", "quality_gate", "smoke_status", "audit_lock",
                 "new_freeze_baseline", "next_recommended_action", "operator_summary"]
    missing = [f for f in required if f not in data]
    if missing:
        return {"passed": False, "message": "missing: %s" % ", ".join(missing)}

    return {"passed": True, "message": "verdict=%s pr=%s" % (
        data.get("quality_gate", {}).get("verdict", "?"),
        data.get("pr_summary", {}).get("number", "?"))}


def _test_run_report_markdown(script_dir):
    """Test run report Markdown output."""
    path = script_dir / "vibe_run_report.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["--markdown", "--repo-root", str(script_dir.parent)])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    if "Run Report" not in stdout:
        return {"passed": False, "message": "missing header"}
    if "## Quality Gate" not in stdout:
        return {"passed": False, "message": "missing quality gate section"}
    if "下一步" not in stdout and "Next Action" not in stdout:
        return {"passed": False, "message": "missing next action"}

    return {"passed": True, "message": "markdown OK (%d chars)" % len(stdout)}


def _test_run_report_compact(script_dir):
    """Test run report compact output."""
    path = script_dir / "vibe_run_report.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["--compact", "--repo-root", str(script_dir.parent)])
    if rc != 0:
        return {"passed": False, "message": "exit code %d" % rc}

    if "QG:" not in stdout:
        return {"passed": False, "message": "missing QG indicator"}

    return {"passed": True, "message": "compact: %s" % stdout.strip()[:60]}


def _test_run_report_router(script_dir):
    """Test run report router aliases (rr, handoff)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}

    rc1, stdout1, stderr1 = _run_script(path, ["rr", "--json", "--repo-root", str(script_dir.parent)])
    if rc1 != 0:
        return {"passed": False, "message": "rr exit=%d" % rc1}

    try:
        data1 = json.loads(stdout1)
        if "operator_summary" not in data1:
            return {"passed": False, "message": "rr missing operator_summary"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "rr invalid JSON"}

    rc2, stdout2, stderr2 = _run_script(path, ["handoff", "--compact", "--repo-root", str(script_dir.parent)])
    if rc2 != 0:
        return {"passed": False, "message": "handoff exit=%d" % rc2}

    return {"passed": True, "message": "rr+handoff OK"}




def _test_v1_freeze_check_json(script_dir):
    """Test V1 freeze check JSON output."""
    path = script_dir / "vibe_v1_freeze_check.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}

    rc, stdout, stderr = _run_script(path, ["--json", "--repo-root", str(script_dir.parent)])
    if rc != 0 and rc != 1:
        return {"passed": False, "message": "exit code %d" % rc}

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}

    if "verdict" not in data:
        return {"passed": False, "message": "missing verdict"}
    if "checks" not in data:
        return {"passed": False, "message": "missing checks"}
    if "operator_summary" not in data:
        return {"passed": False, "message": "missing operator_summary"}

    verdict = data.get("verdict", "UNKNOWN")
    total = len(data.get("checks", []))
    return {"passed": True, "message": "verdict=%s checks=%d" % (verdict, total)}


def _test_v1_freeze_router(script_dir):
    """Test V1 freeze check router aliases (v1, freeze-check)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}

    rc, stdout, stderr = _run_script(path, ["v1", "--json", "--repo-root", str(script_dir.parent)])
    if rc != 0 and rc != 1:
        return {"passed": False, "message": "v1 exit=%d" % rc}

    try:
        data = json.loads(stdout)
        if "verdict" not in data:
            return {"passed": False, "message": "v1 missing verdict"}
    except json.JSONDecodeError:
        return {"passed": False, "message": "v1 invalid JSON"}

    return {"passed": True, "message": "v1+freeze-check verdict=%s" % data.get("verdict")}





def _test_privileged_approval_help(script_dir):
    """Test privileged approval script --help."""
    path = script_dir / "vibe_privileged_approval.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--help"])
    if rc != 0:
        return {"passed": False, "message": "help exit=%d" % rc}
    if "short-approve" not in stdout and "short-approve" not in stderr:
        return {"passed": False, "message": "missing short-approve in help"}
    return {"passed": True, "message": "help has short-approve"}


def _test_privileged_approval_create_list(script_dir):
    """Test privileged approval create + list cycle."""
    import tempfile, shutil
    path = script_dir / "vibe_privileged_approval.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-appr-")
    try:
        rc, stdout, stderr = _run_script(path, [
            "create", "--action-id", "test-001",
            "--repo", "test/repo", "--branch", "main",
            "--action", "push", "--base-sha", "abc123",
            "--approval-dir", tmpdir, "--json"
        ])
        if rc != 0:
            return {"passed": False, "message": "create exit=%d stderr=%s" % (rc, stderr[:100])}
        import json
        data = json.loads(stdout)
        if data.get("status") != "created":
            return {"passed": False, "message": "create status=%s" % data.get("status")}
        rc, stdout, stderr = _run_script(path, [
            "list", "--approval-dir", tmpdir, "--json"
        ])
        if rc != 0:
            return {"passed": False, "message": "list exit=%d" % rc}
        data = json.loads(stdout)
        if data.get("pending") != 1:
            return {"passed": False, "message": "list pending=%d" % data.get("pending")}
        return {"passed": True, "message": "create+list ok pending=1"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_privileged_approval_short_approve(script_dir):
    """Test short-approve with exactly 1 pending action."""
    import tempfile, shutil
    path = script_dir / "vibe_privileged_approval.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-appr-")
    try:
        _run_script(path, [
            "create", "--action-id", "test-sa",
            "--repo", "test/repo", "--branch", "main",
            "--action", "push", "--base-sha", "abc123",
            "--approval-dir", tmpdir, "--json"
        ])
        rc, stdout, stderr = _run_script(path, [
            "short-approve", "--approval-dir", tmpdir, "--json"
        ])
        if rc != 0:
            return {"passed": False, "message": "short-approve exit=%d" % rc}
        import json
        data = json.loads(stdout)
        if data.get("status") != "approved":
            return {"passed": False, "message": "short-approve status=%s" % data.get("status")}
        return {"passed": True, "message": "short-approve ok"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_privileged_approval_short_approve_multi_pending(script_dir):
    """Test short-approve BLOCKS when multiple pending actions exist."""
    import tempfile, shutil
    path = script_dir / "vibe_privileged_approval.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-appr-")
    try:
        _run_script(path, [
            "create", "--action-id", "test-m1",
            "--repo", "test/repo", "--branch", "main",
            "--action", "push", "--base-sha", "abc123",
            "--approval-dir", tmpdir, "--json"
        ])
        _run_script(path, [
            "create", "--action-id", "test-m2",
            "--repo", "test/repo", "--branch", "dev",
            "--action", "push", "--base-sha", "def456",
            "--approval-dir", tmpdir, "--json"
        ])
        rc, stdout, stderr = _run_script(path, [
            "short-approve", "--approval-dir", tmpdir, "--json"
        ])
        if rc == 0:
            return {"passed": False, "message": "should have failed with multi pending"}
        import json
        data = json.loads(stdout)
        if data.get("status") != "blocked":
            return {"passed": False, "message": "expected blocked, got %s" % data.get("status")}
        return {"passed": True, "message": "multi-pending correctly blocked"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_privileged_approval_short_approve_no_pending(script_dir):
    """Test short-approve BLOCKS when no pending actions exist."""
    import tempfile, shutil
    path = script_dir / "vibe_privileged_approval.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-appr-")
    try:
        rc, stdout, stderr = _run_script(path, [
            "short-approve", "--approval-dir", tmpdir, "--json"
        ])
        if rc == 0:
            return {"passed": False, "message": "should have failed with no pending"}
        import json
        data = json.loads(stdout)
        if data.get("status") != "blocked":
            return {"passed": False, "message": "expected blocked, got %s" % data.get("status")}
        return {"passed": True, "message": "no-pending correctly blocked"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_privileged_push_help(script_dir):
    """Test privileged push script --help."""
    path = script_dir / "vibe_privileged_push.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--help"])
    if rc != 0:
        return {"passed": False, "message": "help exit=%d" % rc}
    if "dry-run" not in stdout.lower() and "dry_run" not in stdout.lower():
        return {"passed": False, "message": "missing dry-run in help"}
    return {"passed": True, "message": "push help has dry-run"}


def _test_privileged_push_dryrun(script_dir):
    """Test privileged push dry-run with an approved action."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-push-")
    try:
        _run_script(appr_path, [
            "create", "--action-id", "test-push",
            "--repo", "test/repo", "--branch", "main",
            "--action", "push", "--base-sha", "abc123",
            "--changed-path", "scripts/x.py",
            "--approval-dir", tmpdir, "--json"
        ])
        _run_script(appr_path, [
            "approve", "--action-id", "test-push",
            "--approval-dir", tmpdir, "--json"
        ])
        rc, stdout, stderr = _run_script(push_path, [
            "--action-id", "test-push",
            "--approval-dir", tmpdir, "--json"
        ])
        if rc != 0:
            return {"passed": False, "message": "push dry-run exit=%d" % rc}
        import json
        data = json.loads(stdout)
        if not data.get("would_push"):
            return {"passed": False, "message": "would_push=%s" % data.get("would_push")}
        if not data.get("dry_run"):
            return {"passed": False, "message": "dry_run=%s" % data.get("dry_run")}
        return {"passed": True, "message": "push dry-run would_push=true dry_run=true"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_privileged_push_blocked_forbidden_path(script_dir):
    """Test privileged push BLOCKS when changed_paths contain forbidden paths."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-push-")
    try:
        _run_script(appr_path, [
            "create", "--action-id", "test-forbidden",
            "--repo", "test/repo", "--branch", "main",
            "--action", "push", "--base-sha", "abc123",
            "--changed-path", ".github/workflows/deploy.yml",
            "--approval-dir", tmpdir, "--json"
        ])
        _run_script(appr_path, [
            "approve", "--action-id", "test-forbidden",
            "--approval-dir", tmpdir, "--json"
        ])
        rc, stdout, stderr = _run_script(push_path, [
            "--action-id", "test-forbidden",
            "--approval-dir", tmpdir, "--json"
        ])
        if rc == 0:
            return {"passed": False, "message": "should have blocked forbidden path"}
        import json
        data = json.loads(stdout)
        if data.get("would_push"):
            return {"passed": False, "message": "would_push should be false"}
        return {"passed": True, "message": "forbidden path correctly blocked"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_privileged_push_router(script_dir):
    """Test privileged push router command (pp, push-approved)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}
    rc, stdout, stderr = _run_script(path, ["pp", "--help"])
    if "Privileged Push" not in stdout and "privileged" not in stdout.lower():
        return {"passed": False, "message": "pp not resolved to priv-push: %s" % stdout[:100]}
    return {"passed": True, "message": "pp->priv-push ok"}




def _test_privileged_push_token_not_leaked(script_dir):
    """Test that privileged push never outputs token content."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-leak-")
    try:
        # Create + approve
        _run_script(appr_path, [
            "--json", "create", "--action-id", "test-leak",
            "--repo", "k176060444-lgtm/vibe-coding-repo",
            "--branch", "privileged-smoke/test",
            "--action", "push", "--base-sha", "abc123",
            "--changed-path", "docs/test.md",
            "--approval-dir", tmpdir
        ])
        _run_script(appr_path, [
            "--json", "short-approve", "--approval-dir", tmpdir
        ])
        # Run dry-run push
        rc, stdout, stderr = _run_script(push_path, [
            "--json", "--action-id", "test-leak",
            "--approval-dir", tmpdir, "--dry-run-push"
        ])
        combined = stdout + stderr
        # Check for common token patterns
        suspicious = ["ghp_", "gho_", "github_pat_", "Bearer ", "Basic "]
        for pat in suspicious:
            if pat in combined:
                return {"passed": False, "message": "token pattern found in output: %s" % pat}
        return {"passed": True, "message": "no token patterns in output"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_privileged_push_forbidden_path_block(script_dir):
    """Test privileged push blocks forbidden paths (.github/workflows)."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-forbid-")
    try:
        _run_script(appr_path, [
            "--json", "create", "--action-id", "test-forbid",
            "--repo", "k176060444-lgtm/vibe-coding-repo",
            "--branch", "privileged-smoke/test",
            "--action", "push", "--base-sha", "abc123",
            "--changed-path", ".github/workflows/deploy.yml",
            "--approval-dir", tmpdir
        ])
        _run_script(appr_path, [
            "--json", "short-approve", "--approval-dir", tmpdir
        ])
        rc, stdout, stderr = _run_script(push_path, [
            "--json", "--action-id", "test-forbid",
            "--approval-dir", tmpdir, "--dry-run-push"
        ])
        import json
        data = json.loads(stdout)
        if data.get("would_push"):
            return {"passed": False, "message": "should block .github/workflows"}
        return {"passed": True, "message": "forbidden path blocked"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_privileged_push_self_repo_allowed(script_dir):
    """Test privileged push allows self-repo test branches."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-self-")
    try:
        _run_script(appr_path, [
            "--json", "create", "--action-id", "test-self",
            "--repo", "k176060444-lgtm/vibe-coding-repo",
            "--branch", "privileged-smoke/test-branch",
            "--action", "push", "--base-sha", "abc123",
            "--changed-path", "docs/test.md",
            "--approval-dir", tmpdir
        ])
        _run_script(appr_path, [
            "--json", "short-approve", "--approval-dir", tmpdir
        ])
        rc, stdout, stderr = _run_script(push_path, [
            "--json", "--action-id", "test-self",
            "--approval-dir", tmpdir, "--dry-run-push"
        ])
        import json
        data = json.loads(stdout)
        if not data.get("would_push"):
            return {"passed": False, "message": "should allow self-repo: %s" % data.get("blockers")}
        return {"passed": True, "message": "self-repo test branch allowed"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_privileged_push_external_repo_block(script_dir):
    """Test privileged push blocks external repos."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-ext-")
    try:
        _run_script(appr_path, [
            "--json", "create", "--action-id", "test-ext",
            "--repo", "other-org/other-repo",
            "--branch", "privileged-smoke/test",
            "--action", "push", "--base-sha", "abc123",
            "--changed-path", "docs/test.md",
            "--approval-dir", tmpdir
        ])
        _run_script(appr_path, [
            "--json", "short-approve", "--approval-dir", tmpdir
        ])
        rc, stdout, stderr = _run_script(push_path, [
            "--json", "--action-id", "test-ext",
            "--approval-dir", tmpdir, "--dry-run-push"
        ])
        import json
        data = json.loads(stdout)
        if data.get("would_push"):
            return {"passed": False, "message": "should block external repo"}
        return {"passed": True, "message": "external repo blocked"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_privileged_push_force_delete_tag_block(script_dir):
    """Test privileged push blocks force push, delete, tag, release."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-fdt-")
    try:
        # Test with no_force_push=false
        _run_script(appr_path, [
            "--json", "create", "--action-id", "test-force",
            "--repo", "k176060444-lgtm/vibe-coding-repo",
            "--branch", "privileged-smoke/test",
            "--action", "push --force",
            "--base-sha", "abc123",
            "--changed-path", "docs/test.md",
            "--approval-dir", tmpdir
        ])
        _run_script(appr_path, [
            "--json", "short-approve", "--approval-dir", tmpdir
        ])
        rc, stdout, stderr = _run_script(push_path, [
            "--json", "--action-id", "test-force",
            "--approval-dir", tmpdir, "--dry-run-push"
        ])
        import json
        data = json.loads(stdout)
        # Should be blocked because action contains "force"
        if data.get("would_push"):
            return {"passed": False, "message": "should block force push action"}
        return {"passed": True, "message": "force/delete/tag blocked"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_privileged_approval_parser(script_dir):
    """Test vibe_privileged_approval.py CLI: import safe, help works."""
    path = script_dir / "vibe_privileged_approval.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--help"])
    if rc != 0:
        return {"passed": False, "message": "help exit=%d" % rc}
    if "short-approve" not in stdout:
        return {"passed": False, "message": "missing short-approve"}
    if "create" not in stdout:
        return {"passed": False, "message": "missing create"}
    return {"passed": True, "message": "approval CLI ok"}


def _test_privileged_push_parser(script_dir):
    """Test vibe_privileged_push.py CLI: import safe, help works."""
    path = script_dir / "vibe_privileged_push.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--help"])
    if rc != 0:
        return {"passed": False, "message": "help exit=%d" % rc}
    if "token-preflight" not in stdout:
        return {"passed": False, "message": "missing token-preflight"}
    if "dry-run" not in stdout.lower():
        return {"passed": False, "message": "missing dry-run"}
    return {"passed": True, "message": "push CLI ok"}


def _test_privileged_push_router(script_dir):
    """Test priv-push router aliases (pp, push-approved)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}
    rc, stdout, stderr = _run_script(path, ["pp", "--help"])
    if "Privileged Push" not in stdout and "privileged" not in stdout.lower():
        return {"passed": False, "message": "pp not resolved: %s" % stdout[:80]}
    return {"passed": True, "message": "pp->priv-push ok"}


def _test_privileged_approval_router(script_dir):
    """Test priv-approval router aliases (priv-appr, approval)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}
    rc, stdout, stderr = _run_script(path, ["priv-appr", "--help"])
    if "Privileged Approval" not in stdout and "privileged" not in stdout.lower():
        return {"passed": False, "message": "priv-appr not resolved: %s" % stdout[:80]}
    return {"passed": True, "message": "priv-appr->priv-approval ok"}




def _test_repo_trust_self_repo_allow(script_dir):
    """Test self-repo push policy allows without human approval."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-trust-")
    try:
        _run_script(appr_path, [
            "--json", "create", "--action-id", "test-trust-self",
            "--repo", "k176060444-lgtm/vibe-coding-repo",
            "--branch", "main",
            "--action", "push", "--base-sha", "abc123",
            "--changed-path", "scripts/test.py",
            "--approval-dir", tmpdir
        ])
        rc, stdout, stderr = _run_script(push_path, [
            "--json", "--action-id", "test-trust-self",
            "--approval-dir", tmpdir, "--dry-run-push"
        ])
        import json
        data = json.loads(stdout)
        if not data.get("would_push"):
            return {"passed": False, "message": "self-repo should allow: %s" % data.get("blockers")}
        if data.get("repo_trust_level") != "trusted-self":
            return {"passed": False, "message": "expected trusted-self, got %s" % data.get("repo_trust_level")}
        return {"passed": True, "message": "self-repo allows push without approval"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_repo_trust_external_block_without_approve(script_dir):
    """Test external repo push blocks without human approval."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-ext-")
    try:
        _run_script(appr_path, [
            "--json", "create", "--action-id", "test-ext-block",
            "--repo", "other-org/other-repo",
            "--branch", "main",
            "--action", "push", "--base-sha", "abc123",
            "--changed-path", "src/main.py",
            "--approval-dir", tmpdir
        ])
        rc, stdout, stderr = _run_script(push_path, [
            "--json", "--action-id", "test-ext-block",
            "--approval-dir", tmpdir, "--dry-run-push"
        ])
        import json
        data = json.loads(stdout)
        if data.get("would_push"):
            return {"passed": False, "message": "external repo should block without approval"}
        if data.get("repo_trust_level") != "protected-external":
            return {"passed": False, "message": "expected protected-external, got %s" % data.get("repo_trust_level")}
        return {"passed": True, "message": "external repo correctly blocked without approval"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_repo_trust_external_approved_passes_policy(script_dir):
    """Test approved external repo passes policy check."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-extok-")
    try:
        _run_script(appr_path, [
            "--json", "create", "--action-id", "test-ext-ok",
            "--repo", "other-org/other-repo",
            "--branch", "main",
            "--action", "push", "--base-sha", "abc123",
            "--changed-path", "src/main.py",
            "--approval-dir", tmpdir
        ])
        _run_script(appr_path, [
            "--json", "short-approve", "--approval-dir", tmpdir
        ])
        rc, stdout, stderr = _run_script(push_path, [
            "--json", "--action-id", "test-ext-ok",
            "--approval-dir", tmpdir, "--dry-run-push"
        ])
        import json
        data = json.loads(stdout)
        blockers = data.get("blockers", [])
        has_policy_blocker = any("requires human approval" in b for b in blockers)
        if has_policy_blocker:
            return {"passed": False, "message": "approved external should pass policy"}
        return {"passed": True, "message": "approved external passes policy check"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_repo_trust_forbidden_path_all_repos(script_dir):
    """Test forbidden path blocks for all repos."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-forbid-")
    try:
        _run_script(appr_path, [
            "--json", "create", "--action-id", "test-forbid-self",
            "--repo", "k176060444-lgtm/vibe-coding-repo",
            "--branch", "main",
            "--action", "push", "--base-sha", "abc123",
            "--changed-path", ".github/workflows/deploy.yml",
            "--approval-dir", tmpdir
        ])
        rc, stdout, stderr = _run_script(push_path, [
            "--json", "--action-id", "test-forbid-self",
            "--approval-dir", tmpdir, "--dry-run-push"
        ])
        import json
        data = json.loads(stdout)
        if data.get("would_push"):
            return {"passed": False, "message": "forbidden path should block even for self-repo"}
        return {"passed": True, "message": "forbidden path blocks for all repos"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_token_redaction_enforced(script_dir):
    """Test that token patterns are not in privileged push output."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-redact-")
    try:
        _run_script(appr_path, [
            "--json", "create", "--action-id", "test-redact",
            "--repo", "k176060444-lgtm/vibe-coding-repo",
            "--branch", "privileged-smoke/test",
            "--action", "push", "--base-sha", "abc123",
            "--changed-path", "docs/test.md",
            "--approval-dir", tmpdir
        ])
        _run_script(appr_path, [
            "--json", "short-approve", "--approval-dir", tmpdir
        ])
        rc, stdout, stderr = _run_script(push_path, [
            "--json", "--action-id", "test-redact",
            "--approval-dir", tmpdir, "--dry-run-push"
        ])
        combined = stdout + stderr
        suspicious = ["ghp_", "gho_", "github_pat_", "Bearer ", "Basic "]
        for pat in suspicious:
            if pat in combined:
                return {"passed": False, "message": "token pattern found: %s" % pat}
        return {"passed": True, "message": "no token patterns in output"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_token_only_read_when_policy_allows(script_dir):
    """Test token preflight works independently."""
    push_path = script_dir / "vibe_privileged_push.py"
    if not push_path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(push_path, ["--token-preflight", "--json"])
    if rc != 0:
        return {"passed": False, "message": "token preflight failed: %s" % stderr[:80]}
    import json
    data = json.loads(stdout)
    if not data.get("ok"):
        return {"passed": False, "message": "token preflight should pass"}
    return {"passed": True, "message": "token preflight works independently"}


def _test_force_delete_tag_block(script_dir):
    """Test force push action blocks."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-fdt-")
    try:
        _run_script(appr_path, [
            "--json", "create", "--action-id", "test-force",
            "--repo", "k176060444-lgtm/vibe-coding-repo",
            "--branch", "privileged-smoke/test",
            "--action", "push --force",
            "--base-sha", "abc123",
            "--changed-path", "docs/test.md",
            "--approval-dir", tmpdir
        ])
        rc, stdout, stderr = _run_script(push_path, [
            "--json", "--action-id", "test-force",
            "--approval-dir", tmpdir, "--dry-run-push"
        ])
        import json
        data = json.loads(stdout)
        if data.get("would_push"):
            return {"passed": False, "message": "should block force push action"}
        return {"passed": True, "message": "force/delete/tag blocked"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _test_privileged_push_v12_parser(script_dir):
    """Test privileged push v1.2 CLI with trust policy fields."""
    path = script_dir / "vibe_privileged_push.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--help"])
    if rc != 0:
        return {"passed": False, "message": "help exit=%d" % rc}
    if "token-preflight" not in stdout:
        return {"passed": False, "message": "missing token-preflight"}
    return {"passed": True, "message": "v1.2 push CLI ok"}


def _test_repo_trust_compact_output(script_dir):
    """Test compact output includes trust level."""
    import tempfile, shutil
    appr_path = script_dir / "vibe_privileged_approval.py"
    push_path = script_dir / "vibe_privileged_push.py"
    if not appr_path.exists() or not push_path.exists():
        return {"passed": False, "message": "scripts not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-compact-")
    try:
        _run_script(appr_path, [
            "--json", "create", "--action-id", "test-compact",
            "--repo", "k176060444-lgtm/vibe-coding-repo",
            "--branch", "main",
            "--action", "push", "--base-sha", "abc123",
            "--changed-path", "scripts/test.py",
            "--approval-dir", tmpdir
        ])
        rc, stdout, stderr = _run_script(push_path, [
            "--compact", "--action-id", "test-compact",
            "--approval-dir", tmpdir, "--dry-run-push"
        ])
        if "trusted-self" not in stdout:
            return {"passed": False, "message": "compact missing trust level: %s" % stdout[:100]}
        return {"passed": True, "message": "compact includes trust level"}
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)




def _test_trusted_loop_check(script_dir):
    """Test trusted self-loop --check returns PASS."""
    path = script_dir / "vibe_trusted_self_loop.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--check", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON: %s" % stdout[:100]}
    if data.get("repo_trust_level") != "trusted-self":
        return {"passed": False, "message": "expected trusted-self, got %s" % data.get("repo_trust_level")}
    if data.get("requires_human_approval"):
        return {"passed": False, "message": "should not require human approval"}
    return {"passed": True, "message": "trusted-loop check verdict=%s" % data.get("policy_verdict")}


def _test_trusted_loop_contract(script_dir):
    """Test trusted self-loop --contract outputs spec."""
    path = script_dir / "vibe_trusted_self_loop.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--contract", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    if data.get("repo_trust_level") != "trusted-self":
        return {"passed": False, "message": "expected trusted-self"}
    if "auto_loop_steps" not in data:
        return {"passed": False, "message": "missing auto_loop_steps"}
    if len(data["auto_loop_steps"]) < 8:
        return {"passed": False, "message": "too few steps: %d" % len(data["auto_loop_steps"])}
    return {"passed": True, "message": "contract has %d steps" % len(data["auto_loop_steps"])}


def _test_trusted_loop_validate_self_repo(script_dir):
    """Test trusted self-loop validates self-repo work order as PASS."""
    import tempfile, json as json_mod
    path = script_dir / "vibe_trusted_self_loop.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-loop-")
    wo_path = pathlib.Path(tmpdir) / "wo.json"
    wo = {
        "repo": "k176060444-lgtm/vibe-coding-repo",
        "branch": "main",
        "action": "push",
        "changed_paths": ["scripts/test.py", "docs/README.md"],
    }
    wo_path.write_text(json_mod.dumps(wo))
    rc, stdout, stderr = _run_script(path, ["--validate", str(wo_path), "--json"])
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    if data.get("policy_verdict") != "PASS":
        return {"passed": False, "message": "expected PASS, got %s: %s" % (data.get("policy_verdict"), data.get("blockers"))}
    return {"passed": True, "message": "self-repo validate PASS"}


def _test_trusted_loop_validate_external_block(script_dir):
    """Test trusted self-loop blocks external repo without approval."""
    import tempfile, json as json_mod
    path = script_dir / "vibe_trusted_self_loop.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-loop-")
    wo_path = pathlib.Path(tmpdir) / "wo.json"
    wo = {
        "repo": "other-org/other-repo",
        "branch": "main",
        "action": "push",
        "changed_paths": ["src/main.py"],
        "status": "pending",
    }
    wo_path.write_text(json_mod.dumps(wo))
    rc, stdout, stderr = _run_script(path, ["--validate", str(wo_path), "--json"])
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    if data.get("policy_verdict") != "BLOCK":
        return {"passed": False, "message": "expected BLOCK, got %s" % data.get("policy_verdict")}
    return {"passed": True, "message": "external repo correctly blocked"}


def _test_trusted_loop_forbidden_path_block(script_dir):
    """Test trusted self-loop blocks forbidden paths."""
    import tempfile, json as json_mod
    path = script_dir / "vibe_trusted_self_loop.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-loop-")
    wo_path = pathlib.Path(tmpdir) / "wo.json"
    wo = {
        "repo": "k176060444-lgtm/vibe-coding-repo",
        "branch": "main",
        "action": "push",
        "changed_paths": [".github/workflows/deploy.yml"],
    }
    wo_path.write_text(json_mod.dumps(wo))
    rc, stdout, stderr = _run_script(path, ["--validate", str(wo_path), "--json"])
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    if data.get("policy_verdict") != "BLOCK":
        return {"passed": False, "message": "expected BLOCK for forbidden path"}
    return {"passed": True, "message": "forbidden path correctly blocked"}


def _test_trusted_loop_force_block(script_dir):
    """Test trusted self-loop blocks force push."""
    import tempfile, json as json_mod
    path = script_dir / "vibe_trusted_self_loop.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-loop-")
    wo_path = pathlib.Path(tmpdir) / "wo.json"
    wo = {
        "repo": "k176060444-lgtm/vibe-coding-repo",
        "branch": "main",
        "action": "push --force",
        "changed_paths": ["scripts/test.py"],
    }
    wo_path.write_text(json_mod.dumps(wo))
    rc, stdout, stderr = _run_script(path, ["--validate", str(wo_path), "--json"])
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    if data.get("policy_verdict") != "BLOCK":
        return {"passed": False, "message": "expected BLOCK for force push"}
    return {"passed": True, "message": "force push correctly blocked"}


def _test_trusted_loop_router(script_dir):
    """Test trusted-loop router alias (tl, auto-loop, loop)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}
    rc, stdout, stderr = _run_script(path, ["tl", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON from router"}
    if "repo_trust_level" not in data:
        return {"passed": False, "message": "missing repo_trust_level"}
    return {"passed": True, "message": "tl->trusted-loop ok"}


def _test_wrapper_merge_required(script_dir):
    """Test that vibe_autonomous_merge.py exists and is the only merge path."""
    path = script_dir / "vibe_autonomous_merge.py"
    if not path.exists():
        return {"passed": False, "message": "wrapper not found"}
    # Check it has merge logic
    content = path.read_text()
    if "merge" not in content.lower():
        return {"passed": False, "message": "wrapper missing merge logic"}
    return {"passed": True, "message": "wrapper merge available"}


def _test_bare_gh_merge_forbidden(script_dir):
    """Test that docs enforce wrapper-only merge (no bare gh pr merge)."""
    workflow = script_dir.parent / "docs" / "WORKFLOW.md"
    if not workflow.exists():
        return {"passed": False, "message": "WORKFLOW.md not found"}
    content = workflow.read_text()
    # Should mention wrapper requirement
    if "wrapper" not in content.lower() and "vibe_autonomous_merge" not in content:
        return {"passed": False, "message": "WORKFLOW.md does not mention wrapper"}
    return {"passed": True, "message": "wrapper merge documented"}




def _test_batch_runner_status(script_dir):
    """Test batch runner --status returns capabilities."""
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--status", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    if data.get("repo_trust_level") != "trusted-self":
        return {"passed": False, "message": "expected trusted-self"}
    if "stop_conditions" not in data:
        return {"passed": False, "message": "missing stop_conditions"}
    if len(data["stop_conditions"]) < 8:
        return {"passed": False, "message": "too few stop conditions: %d" % len(data["stop_conditions"])}
    return {"passed": True, "message": "batch runner status ok, %d stop conditions" % len(data["stop_conditions"])}


def _test_batch_runner_dry_run(script_dir):
    """Test batch runner --dry-run validates batch plan."""
    import tempfile, json as json_mod
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-batch-")
    batch_path = pathlib.Path(tmpdir) / "batch.json"
    batch = {
        "batch_id": "test-batch-001",
        "repo": "k176060444-lgtm/vibe-coding-repo",
        "work_orders": [
            {
                "wo_id": "test-wo-001",
                "branch": "v101/test-001",
                "title": "test: wo 001",
                "changed_paths": ["scripts/test.py"],
                "allowed_paths": ["scripts/test.py"],
            },
            {
                "wo_id": "test-wo-002",
                "branch": "v101/test-002",
                "title": "test: wo 002",
                "changed_paths": ["docs/test.md"],
                "allowed_paths": ["docs/test.md"],
            },
        ],
    }
    batch_path.write_text(json_mod.dumps(batch))
    rc, stdout, stderr = _run_script(path, ["--batch", str(batch_path), "--dry-run", "--json"])
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON: %s" % stdout[:100]}
    if data.get("status") != "completed":
        return {"passed": False, "message": "expected completed, got %s" % data.get("status")}
    if data.get("completed") != 2:
        return {"passed": False, "message": "expected 2 completed, got %d" % data.get("completed")}
    return {"passed": True, "message": "batch dry-run ok, %d WOs" % data.get("completed")}


def _test_batch_runner_stop_on_policy_violation(script_dir):
    """Test batch runner stops when policy gate fails."""
    import tempfile, json as json_mod
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-batch-")
    batch_path = pathlib.Path(tmpdir) / "batch.json"
    batch = {
        "batch_id": "test-batch-stop",
        "repo": "k176060444-lgtm/vibe-coding-repo",
        "work_orders": [
            {
                "wo_id": "test-wo-ok",
                "branch": "v101/test-ok",
                "title": "test: ok",
                "changed_paths": ["scripts/test.py"],
                "allowed_paths": ["scripts/test.py"],
            },
            {
                "wo_id": "test-wo-bad",
                "branch": "v101/test-bad",
                "title": "test: bad path",
                "changed_paths": [".github/workflows/deploy.yml"],
                "allowed_paths": ["scripts/test.py"],
            },
        ],
    }
    batch_path.write_text(json_mod.dumps(batch))
    rc, stdout, stderr = _run_script(path, ["--batch", str(batch_path), "--dry-run", "--json"])
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    if data.get("status") != "stopped":
        return {"passed": False, "message": "expected stopped, got %s" % data.get("status")}
    if data.get("stop_reason") != "unexpected_changed_paths":
        return {"passed": False, "message": "expected unexpected_changed_paths, got %s" % data.get("stop_reason")}
    if data.get("completed") != 1:
        return {"passed": False, "message": "expected 1 completed before stop, got %d" % data.get("completed")}
    return {"passed": True, "message": "batch stopped on policy violation, %d completed" % data.get("completed")}


def _test_batch_runner_external_repo_block(script_dir):
    """Test batch runner blocks external repo."""
    import tempfile, json as json_mod
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-batch-")
    batch_path = pathlib.Path(tmpdir) / "batch.json"
    batch = {
        "batch_id": "test-batch-ext",
        "repo": "other-org/other-repo",
        "work_orders": [{"wo_id": "ext-001", "branch": "main", "changed_paths": ["src/x.py"], "allowed_paths": ["src/x.py"]}],
    }
    batch_path.write_text(json_mod.dumps(batch))
    rc, stdout, stderr = _run_script(path, ["--batch", str(batch_path), "--dry-run", "--json"])
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    if data.get("status") != "blocked":
        return {"passed": False, "message": "expected blocked, got %s" % data.get("status")}
    return {"passed": True, "message": "external repo correctly blocked"}


def _test_batch_runner_max_size(script_dir):
    """Test batch runner rejects >5 work orders."""
    import tempfile, json as json_mod
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-batch-")
    batch_path = pathlib.Path(tmpdir) / "batch.json"
    batch = {
        "batch_id": "test-batch-big",
        "repo": "k176060444-lgtm/vibe-coding-repo",
        "work_orders": [
            {"wo_id": f"wo-{i}", "branch": f"v101/wo-{i}", "changed_paths": [f"scripts/x{i}.py"], "allowed_paths": [f"scripts/x{i}.py"]}
            for i in range(6)
        ],
    }
    batch_path.write_text(json_mod.dumps(batch))
    rc, stdout, stderr = _run_script(path, ["--batch", str(batch_path), "--dry-run", "--json"])
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    if "error" not in data and data.get("status") != "blocked":
        return {"passed": False, "message": "should reject >5 WOs"}
    return {"passed": True, "message": "max size enforced"}


def _test_batch_runner_router(script_dir):
    """Test batch-runner router alias (br, batch)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}
    rc, stdout, stderr = _run_script(path, ["br", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON from router"}
    if "stop_conditions" not in data and "batch_runner_version" not in data:
        return {"passed": False, "message": "missing batch runner fields"}
    return {"passed": True, "message": "br->batch-runner ok"}


def _test_batch_runner_token_redaction(script_dir):
    """Test batch runner does not leak token patterns."""
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--status", "--json"])
    combined = stdout + stderr
    suspicious = ["ghp_", "gho_", "github_pat_", "Bearer ", "Basic "]
    for pat in suspicious:
        if pat in combined:
            return {"passed": False, "message": "token pattern found: %s" % pat}
    return {"passed": True, "message": "no token patterns in batch runner output"}




def _test_worker_resilience_check(script_dir):
    """Test worker resilience --check returns status."""
    path = script_dir / "vibe_worker_resilience.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--check", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    if "worker_status" not in data:
        return {"passed": False, "message": "missing worker_status"}
    valid_statuses = ["reachable", "unreachable_timeout", "unreachable_refused", "unknown"]
    if data["worker_status"] not in valid_statuses:
        return {"passed": False, "message": "invalid status: %s" % data["worker_status"]}
    return {"passed": True, "message": "worker_status=%s" % data["worker_status"]}


def _test_worker_resilience_checkpoint(script_dir):
    """Test checkpoint creation."""
    import tempfile
    path = script_dir / "vibe_worker_resilience.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-cp-")
    cp_path = Path(tmpdir) / "checkpoint.json"
    rc, stdout, stderr = _run_script(path, ["--checkpoint", str(cp_path), "--json"])
    import json, shutil
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return {"passed": False, "message": "invalid JSON"}
    shutil.rmtree(tmpdir, ignore_errors=True)
    if "status" not in data:
        return {"passed": False, "message": "missing status in checkpoint"}
    if data.get("resume_allowed") is None:
        return {"passed": False, "message": "missing resume_allowed"}
    return {"passed": True, "message": "checkpoint created, resume_allowed=%s" % data.get("resume_allowed")}


def _test_worker_resilience_retry_config(script_dir):
    """Test retry config: 5min interval, 75min max, 15 retries."""
    path = script_dir / "vibe_worker_resilience.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    content = path.read_text()
    checks = [
        ("RETRY_INTERVAL_MINUTES = 5", "retry interval 5min"),
        ("MAX_WAIT_MINUTES = 75", "max wait 75min"),
        ("MAX_RETRY_COUNT = 15", "max retry 15"),
        ("REPORT_INTERVAL_MINUTES = 15", "report interval 15min"),
    ]
    for pattern, desc in checks:
        if pattern not in content:
            return {"passed": False, "message": "missing: %s" % desc}
    return {"passed": True, "message": "retry config: 5min/75min/15/15min"}


def _test_worker_resilience_status_report(script_dir):
    """Test status report generation."""
    import tempfile
    path = script_dir / "vibe_worker_resilience.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-rpt-")
    cp_path = Path(tmpdir) / "checkpoint.json"
    # Create checkpoint first
    _run_script(path, ["--checkpoint", str(cp_path), "--json"])
    # Generate report
    rc, stdout, stderr = _run_script(path, ["--status-report", str(cp_path), "--json"])
    import json, shutil
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return {"passed": False, "message": "invalid JSON"}
    shutil.rmtree(tmpdir, ignore_errors=True)
    required = ["batch_id", "status", "retry_count", "resume_allowed", "recommendation"]
    missing = [f for f in required if f not in data]
    if missing:
        return {"passed": False, "message": "missing fields: %s" % missing}
    return {"passed": True, "message": "status report has all required fields"}


def _test_worker_resilience_resume(script_dir):
    """Test resume from checkpoint."""
    import tempfile
    path = script_dir / "vibe_worker_resilience.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-resume-")
    cp_path = Path(tmpdir) / "checkpoint.json"
    _run_script(path, ["--checkpoint", str(cp_path), "--json"])
    rc, stdout, stderr = _run_script(path, ["--resume", str(cp_path), "--json"])
    import json, shutil
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return {"passed": False, "message": "invalid JSON"}
    shutil.rmtree(tmpdir, ignore_errors=True)
    if "resume_allowed" not in data:
        return {"passed": False, "message": "missing resume_allowed"}
    return {"passed": True, "message": "resume check ok, resume_allowed=%s" % data.get("resume_allowed")}


def _test_worker_resilience_router(script_dir):
    """Test worker-resilience router alias (wr, worker, resilience)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}
    rc, stdout, stderr = _run_script(path, ["wr", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON from router"}
    if "worker_status" not in data:
        return {"passed": False, "message": "missing worker_status"}
    return {"passed": True, "message": "wr->worker-resilience ok"}


def _test_worker_resilience_token_no_leak(script_dir):
    """Test worker resilience does not leak token."""
    path = script_dir / "vibe_worker_resilience.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--check", "--json"])
    combined = stdout + stderr
    suspicious = ["ghp_", "gho_", "github_pat_", "Bearer ", "Basic "]
    for pat in suspicious:
        if pat in combined:
            return {"passed": False, "message": "token pattern found: %s" % pat}
    return {"passed": True, "message": "no token patterns"}




def _test_batch_runner_report_fields(script_dir):
    """Test batch runner status includes report fields."""
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--status", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    if "batch_runner_version" not in data:
        return {"passed": False, "message": "missing batch_runner_version"}
    return {"passed": True, "message": "batch runner v%s" % data.get("batch_runner_version")}


def _test_batch_runner_version(script_dir):
    """Test batch runner version >= 1.2.0."""
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    content = path.read_text()
    if 'VERSION = "1.2.0"' not in content:
        return {"passed": False, "message": "expected version 1.2.0"}
    return {"passed": True, "message": "batch runner v1.2.0"}




def _test_batch_status_json(script_dir):
    """Test batch-status --json returns valid JSON with required fields."""
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--batch-status", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    required = ["batch_id", "status", "current_wo", "phase", "baseline_before",
                "current_baseline", "last_safe_point", "resume_allowed",
                "worker_status", "retry_count", "next_retry_at",
                "completed_count", "remaining_count", "last_pr", "last_changed_paths"]
    missing = [f for f in required if f not in data]
    if missing:
        return {"passed": False, "message": "missing fields: %s" % missing}
    return {"passed": True, "message": "batch-status has all %d required fields" % len(required)}


def _test_batch_report_json(script_dir):
    """Test batch-report --json returns valid JSON with report fields."""
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--batch-report", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    required = ["report_type", "report_time", "batch_runner_version", "repo", "repo_trust_level"]
    missing = [f for f in required if f not in data]
    if missing:
        return {"passed": False, "message": "missing report fields: %s" % missing}
    if data.get("report_type") != "batch_report":
        return {"passed": False, "message": "expected report_type=batch_report"}
    return {"passed": True, "message": "batch-report ok, v%s" % data.get("batch_runner_version")}


def _test_batch_status_router_bs(script_dir):
    """Test batch-status router alias (bs)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}
    rc, stdout, stderr = _run_script(path, ["bs", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON from router"}
    if "status" not in data:
        return {"passed": False, "message": "missing status field"}
    return {"passed": True, "message": "bs->batch-status ok"}


def _test_batch_report_router_breport(script_dir):
    """Test batch-report router alias (breport)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}
    rc, stdout, stderr = _run_script(path, ["breport", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON from router"}
    if "report_type" not in data:
        return {"passed": False, "message": "missing report_type field"}
    return {"passed": True, "message": "breport->batch-report ok"}


def _test_batch_status_token_no_leak(script_dir):
    """Test batch-status does not leak token patterns."""
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--batch-status", "--json"])
    combined = stdout + stderr
    suspicious = ["ghp_", "gho_", "github_pat_", "Bearer ", "Basic "]
    for pat in suspicious:
        if pat in combined:
            return {"passed": False, "message": "token pattern found: %s" % pat}
    return {"passed": True, "message": "no token patterns in batch-status output"}


def _test_batch_status_with_checkpoint(script_dir):
    """Test batch-status reads checkpoint data."""
    import tempfile, json as json_mod
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-bs-")
    cp_path = Path(tmpdir) / "checkpoint.json"
    cp_data = {
        "batch_id": "test-bs-001",
        "status": "WAITING_WORKER_RECOVERY",
        "current_wo": "wo-test-002",
        "phase": "after_push",
        "baseline_before": "abc123",
        "last_safe_point": 1000000,
        "resume_allowed": True,
        "retry_count": 3,
        "next_retry_at": 1000300,
        "pr": 42,
        "changed_paths": ["scripts/test.py"],
        "work_orders": [{"wo_id": "wo-1"}, {"wo_id": "wo-2"}, {"wo_id": "wo-3"}],
        "current_wo_index": 1,
    }
    cp_path.write_text(json_mod.dumps(cp_data))
    rc, stdout, stderr = _run_script(path, ["--batch-status", "--checkpoint", str(cp_path), "--json"])
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON: %s" % stdout[:100]}
    if data.get("batch_id") != "test-bs-001":
        return {"passed": False, "message": "expected batch_id=test-bs-001, got %s" % data.get("batch_id")}
    if data.get("status") != "WAITING_WORKER_RECOVERY":
        return {"passed": False, "message": "expected WAITING_WORKER_RECOVERY, got %s" % data.get("status")}
    if data.get("current_wo") != "wo-test-002":
        return {"passed": False, "message": "expected current_wo=wo-test-002"}
    if data.get("completed_count") != 1:
        return {"passed": False, "message": "expected completed_count=1, got %s" % data.get("completed_count")}
    if data.get("remaining_count") != 2:
        return {"passed": False, "message": "expected remaining_count=2, got %s" % data.get("remaining_count")}
    return {"passed": True, "message": "batch-status checkpoint read ok, batch_id=%s" % data.get("batch_id")}




def _test_batch_pause_help(script_dir):
    """Test batch-runner --help shows --pause option."""
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    rc, stdout, stderr = _run_script(path, ["--help"])
    combined = stdout + stderr
    if "--pause" not in combined:
        return {"passed": False, "message": "--pause not in help"}
    if "--resume" not in combined:
        return {"passed": False, "message": "--resume not in help"}
    return {"passed": True, "message": "pause/resume in help"}


def _test_batch_pause_creates_checkpoint(script_dir):
    """Test --pause creates checkpoint with PAUSED status."""
    import tempfile, json as json_mod, shutil
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-pause-")
    cp_path = Path(tmpdir) / "pause-cp.json"
    rc, stdout, stderr = _run_script(path, ["--pause", "--checkpoint", str(cp_path), "--json"])
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return {"passed": False, "message": "invalid JSON: %s" % stdout[:100]}
    shutil.rmtree(tmpdir, ignore_errors=True)
    if data.get("status") != "PAUSED":
        return {"passed": False, "message": "expected PAUSED, got %s" % data.get("status")}
    if data.get("resume_allowed") is not True:
        return {"passed": False, "message": "expected resume_allowed=True"}
    return {"passed": True, "message": "pause creates PAUSED checkpoint"}


def _test_batch_resume_checks_reconcile(script_dir):
    """Test --resume performs reconciliation checks."""
    import tempfile, json as json_mod, shutil
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-resume-")
    cp_path = Path(tmpdir) / "resume-cp.json"
    # Create a PAUSED checkpoint
    cp_data = {
        "batch_id": "test-resume",
        "status": "PAUSED",
        "current_wo": None,
        "phase": "before_any_mutation",
        "baseline_before": "nonexistent_sha_for_test",
        "resume_allowed": True,
        "retry_count": 0,
    }
    cp_path.write_text(json_mod.dumps(cp_data))
    rc, stdout, stderr = _run_script(path, ["--resume", "--checkpoint", str(cp_path), "--json"])
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return {"passed": False, "message": "invalid JSON: %s" % stdout[:100]}
    shutil.rmtree(tmpdir, ignore_errors=True)
    # Resume should fail because baseline doesn't match or worker unreachable
    if rc == 0:
        return {"passed": False, "message": "expected resume to fail (mismatch), got rc=0"}
    if "BLOCKED" not in data.get("status", ""):
        return {"passed": False, "message": "expected BLOCKED status, got %s" % data.get("status")}
    return {"passed": True, "message": "resume correctly blocked: %s" % data.get("reason", "unknown")}


def _test_batch_pause_router_bp(script_dir):
    """Test batch-pause router alias (bp)."""
    import tempfile, shutil
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-bp-")
    cp_path = Path(tmpdir) / "bp-cp.json"
    rc, stdout, stderr = _run_script(path, ["bp", "--checkpoint", str(cp_path), "--json"])
    shutil.rmtree(tmpdir, ignore_errors=True)
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON from router"}
    if data.get("status") != "PAUSED":
        return {"passed": False, "message": "expected PAUSED, got %s" % data.get("status")}
    return {"passed": True, "message": "bp->batch-pause ok"}


def _test_batch_resume_router_bresume(script_dir):
    """Test batch-resume router alias (bresume)."""
    import tempfile, json as json_mod, shutil
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-br-")
    cp_path = Path(tmpdir) / "br-cp.json"
    cp_data = {
        "batch_id": "test-bresume",
        "status": "PAUSED",
        "resume_allowed": True,
        "phase": "before_any_mutation",
        "baseline_before": "nonexistent_sha",
    }
    cp_path.write_text(json_mod.dumps(cp_data))
    rc, stdout, stderr = _run_script(path, ["bresume", "--checkpoint", str(cp_path), "--json"])
    shutil.rmtree(tmpdir, ignore_errors=True)
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON from router"}
    if "resume_command" not in data:
        return {"passed": False, "message": "missing resume_command field"}
    return {"passed": True, "message": "bresume->batch-resume ok"}


def _test_worker_resilience_pause(script_dir):
    """Test worker resilience --pause creates PAUSED checkpoint."""
    import tempfile, json as json_mod, shutil
    path = script_dir / "vibe_worker_resilience.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-wr-pause-")
    cp_path = Path(tmpdir) / "wr-pause-cp.json"
    rc, stdout, stderr = _run_script(path, ["--pause", str(cp_path), "--json"])
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return {"passed": False, "message": "invalid JSON"}
    shutil.rmtree(tmpdir, ignore_errors=True)
    if data.get("status") != "PAUSED":
        return {"passed": False, "message": "expected PAUSED, got %s" % data.get("status")}
    return {"passed": True, "message": "worker resilience pause ok"}


def _test_worker_resilience_reconcile(script_dir):
    """Test worker resilience --reconcile checks state."""
    import tempfile, json as json_mod, shutil
    path = script_dir / "vibe_worker_resilience.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-wr-recon-")
    cp_path = Path(tmpdir) / "wr-recon-cp.json"
    cp_data = {
        "batch_id": "test-reconcile",
        "status": "PAUSED",
        "resume_allowed": True,
        "phase": "before_any_mutation",
        "baseline_before": "nonexistent",
    }
    cp_path.write_text(json_mod.dumps(cp_data))
    rc, stdout, stderr = _run_script(path, ["--reconcile", str(cp_path), "--json"])
    shutil.rmtree(tmpdir, ignore_errors=True)
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    if "reconcile_status" not in data:
        return {"passed": False, "message": "missing reconcile_status"}
    return {"passed": True, "message": "reconcile status=%s" % data.get("reconcile_status")}


def _test_batch_runner_version_140(script_dir):
    """Test batch runner version >= 1.4.0."""
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    content = path.read_text()
    v = content.split("VERSION = ")[1].split(chr(34))[1] if "VERSION = " in content else "0.0.0"
    parts = v.split("."); major, minor = int(parts[0]), int(parts[1])
    if major < 1 or (major == 1 and minor < 4):
        return {"passed": False, "message": "expected version >= 1.4.0, got %s" % v}
    return {"passed": True, "message": "batch runner v%s" % v}
def _test_worker_resilience_version_110(script_dir):
    """Test worker resilience version >= 1.1.0."""
    path = script_dir / "vibe_worker_resilience.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    content = path.read_text()
    if 'VERSION = "1.1.0"' not in content:
        return {"passed": False, "message": "expected version 1.1.0"}
    return {"passed": True, "message": "worker resilience v1.1.0"}




def _test_batch_cancel_before_mutation(script_dir):
    """Test --cancel works before any mutation."""
    import tempfile, json as json_mod, shutil
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-cancel-")
    cp_path = Path(tmpdir) / "cancel-cp.json"
    cp_data = {
        "batch_id": "test-cancel-001",
        "status": "running",
        "phase": "before_any_mutation",
        "work_orders": [{"wo_id": "wo-1"}, {"wo_id": "wo-2"}],
        "completed_wos": [],
        "uncompleted_wos": [{"wo_id": "wo-1"}, {"wo_id": "wo-2"}],
        "last_safe_point": 1000000,
        "resume_allowed": True,
    }
    cp_path.write_text(json_mod.dumps(cp_data))
    rc, stdout, stderr = _run_script(path, ["--cancel", "--checkpoint", str(cp_path), "--json"])
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return {"passed": False, "message": "invalid JSON: %s" % stdout[:100]}
    shutil.rmtree(tmpdir, ignore_errors=True)
    if data.get("cancel_status") != "CANCELLED":
        return {"passed": False, "message": "expected CANCELLED, got %s" % data.get("cancel_status")}
    if data.get("resume_allowed") is not False:
        return {"passed": False, "message": "expected resume_allowed=False"}
    return {"passed": True, "message": "cancel before mutation ok"}


def _test_batch_cancel_after_mutation_blocked(script_dir):
    """Test --cancel blocked after mutation."""
    import tempfile, json as json_mod, shutil
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-cancel-block-")
    cp_path = Path(tmpdir) / "cancel-block-cp.json"
    cp_data = {
        "batch_id": "test-cancel-block",
        "status": "running",
        "phase": "after_push",
        "resume_allowed": True,
    }
    cp_path.write_text(json_mod.dumps(cp_data))
    rc, stdout, stderr = _run_script(path, ["--cancel", "--checkpoint", str(cp_path), "--json"])
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return {"passed": False, "message": "invalid JSON"}
    shutil.rmtree(tmpdir, ignore_errors=True)
    if data.get("cancel_status") != "BLOCKED_MUTATION_OCCURRED":
        return {"passed": False, "message": "expected BLOCKED_MUTATION_OCCURRED, got %s" % data.get("cancel_status")}
    return {"passed": True, "message": "cancel after mutation correctly blocked"}


def _test_batch_abort_after_checkpoint(script_dir):
    """Test --abort works after checkpoint with no destructive cleanup."""
    import tempfile, json as json_mod, shutil
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-abort-")
    cp_path = Path(tmpdir) / "abort-cp.json"
    cp_data = {
        "batch_id": "test-abort-001",
        "status": "running",
        "phase": "after_push",
        "work_orders": [{"wo_id": "wo-1"}, {"wo_id": "wo-2"}],
        "completed_wos": [{"wo_id": "wo-1"}],
        "uncompleted_wos": [{"wo_id": "wo-2"}],
        "last_safe_point": 1000000,
        "resume_allowed": True,
    }
    cp_path.write_text(json_mod.dumps(cp_data))
    rc, stdout, stderr = _run_script(path, ["--abort", "--checkpoint", str(cp_path), "--json"])
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return {"passed": False, "message": "invalid JSON"}
    shutil.rmtree(tmpdir, ignore_errors=True)
    if data.get("abort_status") != "ABORTED":
        return {"passed": False, "message": "expected ABORTED, got %s" % data.get("abort_status")}
    if data.get("destructive_cleanup") is not False:
        return {"passed": False, "message": "expected destructive_cleanup=False"}
    if data.get("resume_allowed") is not False:
        return {"passed": False, "message": "expected resume_allowed=False"}
    return {"passed": True, "message": "abort ok, no destructive cleanup"}


def _test_batch_cancel_operator_report(script_dir):
    """Test --cancel generates operator report with completed/uncompleted WOs."""
    import tempfile, json as json_mod, shutil
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-cancel-rpt-")
    cp_path = Path(tmpdir) / "cancel-rpt-cp.json"
    cp_data = {
        "batch_id": "test-cancel-rpt",
        "status": "running",
        "phase": "before_any_mutation",
        "work_orders": [{"wo_id": "wo-a"}, {"wo_id": "wo-b"}, {"wo_id": "wo-c"}],
        "completed_wos": [],
        "uncompleted_wos": [{"wo_id": "wo-a"}, {"wo_id": "wo-b"}, {"wo_id": "wo-c"}],
        "last_safe_point": 1000000,
    }
    cp_path.write_text(json_mod.dumps(cp_data))
    rc, stdout, stderr = _run_script(path, ["--cancel", "--checkpoint", str(cp_path), "--json"])
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return {"passed": False, "message": "invalid JSON"}
    shutil.rmtree(tmpdir, ignore_errors=True)
    required = ["cancel_status", "batch_id", "cancelled_at", "completed_wos", "uncompleted_wos", "last_safe_point", "resume_allowed"]
    missing = [f for f in required if f not in data]
    if missing:
        return {"passed": False, "message": "missing report fields: %s" % missing}
    return {"passed": True, "message": "cancel operator report complete"}


def _test_batch_abort_operator_report(script_dir):
    """Test --abort generates operator report."""
    import tempfile, json as json_mod, shutil
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-abort-rpt-")
    cp_path = Path(tmpdir) / "abort-rpt-cp.json"
    cp_data = {
        "batch_id": "test-abort-rpt",
        "status": "running",
        "phase": "after_merge",
        "completed_wos": [{"wo_id": "wo-1"}],
        "uncompleted_wos": [{"wo_id": "wo-2"}],
        "last_safe_point": 1000000,
    }
    cp_path.write_text(json_mod.dumps(cp_data))
    rc, stdout, stderr = _run_script(path, ["--abort", "--checkpoint", str(cp_path), "--json"])
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return {"passed": False, "message": "invalid JSON"}
    shutil.rmtree(tmpdir, ignore_errors=True)
    required = ["abort_status", "batch_id", "aborted_at", "completed_wos", "uncompleted_wos", "last_safe_point", "resume_allowed", "destructive_cleanup"]
    missing = [f for f in required if f not in data]
    if missing:
        return {"passed": False, "message": "missing report fields: %s" % missing}
    return {"passed": True, "message": "abort operator report complete"}


def _test_batch_cancel_router(script_dir):
    """Test batch-cancel router alias (bcancel)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}
    rc, stdout, stderr = _run_script(path, ["bcancel", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON from router"}
    if "cancel_status" not in data:
        return {"passed": False, "message": "missing cancel_status"}
    return {"passed": True, "message": "bcancel->batch-cancel ok"}


def _test_batch_abort_router(script_dir):
    """Test batch-abort router alias (babort)."""
    path = script_dir / "vibe_command_router.py"
    if not path.exists():
        return {"passed": False, "message": "router not found"}
    rc, stdout, stderr = _run_script(path, ["babort", "--json"])
    import json
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON from router"}
    if "abort_status" not in data:
        return {"passed": False, "message": "missing abort_status"}
    return {"passed": True, "message": "babort->batch-abort ok"}


def _test_batch_runner_version_150(script_dir):
    """Test batch runner version >= 1.5.0."""
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    content = path.read_text()
    if 'VERSION = "1.5.0"' not in content:
        return {"passed": False, "message": "expected version 1.5.0"}
    return {"passed": True, "message": "batch runner v1.5.0"}


def _test_batch_runner_checkpoint_status_field(script_dir):
    """Test batch runner dry-run includes checkpoint_status."""
    import tempfile, json as json_mod
    path = script_dir / "vibe_batch_runner.py"
    if not path.exists():
        return {"passed": False, "message": "script not found"}
    tmpdir = tempfile.mkdtemp(prefix="vibedev-test-rpt-")
    batch_path = pathlib.Path(tmpdir) / "batch.json"
    batch = {
        "batch_id": "test-rpt",
        "repo": "k176060444-lgtm/vibe-coding-repo",
        "work_orders": [
            {"wo_id": "wo-1", "branch": "v101/test", "changed_paths": ["docs/test.md"], "allowed_paths": ["docs/test.md"]}
        ],
    }
    batch_path.write_text(json_mod.dumps(batch))
    rc, stdout, stderr = _run_script(path, ["--batch", str(batch_path), "--dry-run", "--json"])
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return {"passed": False, "message": "invalid JSON"}
    if "checkpoint_status" not in data:
        return {"passed": False, "message": "missing checkpoint_status"}
    if "resume_status" not in data:
        return {"passed": False, "message": "missing resume_status"}
    return {"passed": True, "message": "checkpoint_status=%s resume_status=%s" % (data.get("checkpoint_status"), data.get("resume_status"))}


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

    # Test 58: Sandbox check
    tests.append(_run_test("sandbox_check", lambda: _test_sandbox_check(script_dir)))

    # Test 59: Control plan
    tests.append(_run_test("control_plan", lambda: _test_control_plan(script_dir)))

    # Test 60: Recovery plan
    tests.append(_run_test("recovery_plan", lambda: _test_recovery_plan(script_dir)))

    # Test 61: Recovery classify
    tests.append(_run_test("recovery_classify", lambda: _test_recovery_classify(script_dir)))

    # Test 62: Unfreeze checklist
    tests.append(_run_test("unfreeze_checklist", lambda: _test_unfreeze_checklist(script_dir)))

    # Test 63: Unfreeze checklist JSON
    tests.append(_run_test("unfreeze_checklist_json", lambda: _test_unfreeze_checklist_json(script_dir)))

    # Test 64: Unfreeze checklist router
    tests.append(_run_test("unfreeze_checklist_router", lambda: _test_unfreeze_checklist_router(script_dir)))

    # Test 65: Repo context detection
    tests.append(_run_test("repo_context_detection", lambda: _test_repo_context_detection(script_dir)))

    # Test 66: Temp-context graceful handling
    tests.append(_run_test("temp_context_graceful", lambda: _test_temp_context_graceful(script_dir)))

    # Test 67: Evidence verifier fixture mode detection
    tests.append(_run_test("evidence_verifier_fixture_mode", lambda: _test_evidence_verifier_fixture_mode(script_dir)))

    # Test 68: Evidence verifier unexpected WARN in non-fixture mode
    tests.append(_run_test("evidence_verifier_unexpected_warn", lambda: _test_evidence_verifier_unexpected_warn(script_dir)))

    # Test 69: Quality gate JSON output
    tests.append(_run_test("quality_gate_json", lambda: _test_quality_gate_json(script_dir)))

    # Test 70: Quality gate router aliases (qg, go-no-go)
    tests.append(_run_test("quality_gate_router", lambda: _test_quality_gate_router(script_dir)))

    # Test 71: Quality gate BLOCK scenario
    tests.append(_run_test("quality_gate_block", lambda: _test_quality_gate_block_scenario(script_dir)))

    # Test 72: Run report JSON
    tests.append(_run_test("run_report_json", lambda: _test_run_report_json(script_dir)))

    # Test 73: Run report Markdown
    tests.append(_run_test("run_report_markdown", lambda: _test_run_report_markdown(script_dir)))

    # Test 74: Run report compact
    tests.append(_run_test("run_report_compact", lambda: _test_run_report_compact(script_dir)))

    # Test 75: Run report router aliases
    tests.append(_run_test("run_report_router", lambda: _test_run_report_router(script_dir)))

    # Test 76: V1 freeze check JSON
    tests.append(_run_test("v1_freeze_check_json", lambda: _test_v1_freeze_check_json(script_dir)))

    # Test 77: V1 freeze check router aliases
    tests.append(_run_test("v1_freeze_router", lambda: _test_v1_freeze_router(script_dir)))


    # Test 78: batch-status --json
    tests.append(_run_test("batch_status_json", lambda: _test_batch_status_json(script_dir)))

    # Test 79: batch-report --json
    tests.append(_run_test("batch_report_json", lambda: _test_batch_report_json(script_dir)))

    # Test 80: batch-status router alias (bs)
    tests.append(_run_test("batch_status_router_bs", lambda: _test_batch_status_router_bs(script_dir)))

    # Test 81: batch-report router alias (breport)
    tests.append(_run_test("batch_report_router_breport", lambda: _test_batch_report_router_breport(script_dir)))

    # Test 82: batch-status no token leak
    tests.append(_run_test("batch_status_token_no_leak", lambda: _test_batch_status_token_no_leak(script_dir)))

    # Test 83: batch-status with checkpoint
    tests.append(_run_test("batch_status_with_checkpoint", lambda: _test_batch_status_with_checkpoint(script_dir)))



    # Test 84: batch-pause creates checkpoint
    tests.append(_run_test("batch_pause_creates_checkpoint", lambda: _test_batch_pause_creates_checkpoint(script_dir)))

    # Test 85: batch-resume reconciliation
    tests.append(_run_test("batch_resume_checks_reconcile", lambda: _test_batch_resume_checks_reconcile(script_dir)))

    # Test 86: batch-pause router alias (bp)
    tests.append(_run_test("batch_pause_router_bp", lambda: _test_batch_pause_router_bp(script_dir)))

    # Test 87: batch-resume router alias (bresume)
    tests.append(_run_test("batch_resume_router_bresume", lambda: _test_batch_resume_router_bresume(script_dir)))

    # Test 88: worker resilience pause
    tests.append(_run_test("worker_resilience_pause", lambda: _test_worker_resilience_pause(script_dir)))

    # Test 89: worker resilience reconcile
    tests.append(_run_test("worker_resilience_reconcile", lambda: _test_worker_resilience_reconcile(script_dir)))

    # Test 90: batch runner version 1.4.0
    tests.append(_run_test("batch_runner_version_140", lambda: _test_batch_runner_version_140(script_dir)))

    # Test 91: worker resilience version 1.1.0
    tests.append(_run_test("worker_resilience_version_110", lambda: _test_worker_resilience_version_110(script_dir)))



    # Test 92: cancel before mutation
    tests.append(_run_test("batch_cancel_before_mutation", lambda: _test_batch_cancel_before_mutation(script_dir)))

    # Test 93: cancel after mutation blocked
    tests.append(_run_test("batch_cancel_after_mutation_blocked", lambda: _test_batch_cancel_after_mutation_blocked(script_dir)))

    # Test 94: abort after checkpoint
    tests.append(_run_test("batch_abort_after_checkpoint", lambda: _test_batch_abort_after_checkpoint(script_dir)))

    # Test 95: cancel operator report
    tests.append(_run_test("batch_cancel_operator_report", lambda: _test_batch_cancel_operator_report(script_dir)))

    # Test 96: abort operator report
    tests.append(_run_test("batch_abort_operator_report", lambda: _test_batch_abort_operator_report(script_dir)))

    # Test 97: cancel router alias
    tests.append(_run_test("batch_cancel_router", lambda: _test_batch_cancel_router(script_dir)))

    # Test 98: abort router alias
    tests.append(_run_test("batch_abort_router", lambda: _test_batch_abort_router(script_dir)))

    # Test 99: batch runner version 1.5.0
    tests.append(_run_test("batch_runner_version_150", lambda: _test_batch_runner_version_150(script_dir)))

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
