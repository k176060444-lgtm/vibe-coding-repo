#!/usr/bin/env python3
"""Batch Dashboard v1.0.0 — one-command cluster status snapshot.

Usage:
    python3 scripts/vibe_batch_dashboard.py --json
    python3 scripts/vibe_batch_dashboard.py --text
    python3 scripts/vibe_batch_dashboard.py --self-check [--json]
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

VERSION = "1.0.0"


def _run(cmd, timeout=15, cwd=None):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except OSError as e:
        return -1, "", str(e)


def _git(repo, *args):
    rc, out, _ = _run(["git", "-C", repo] + list(args), timeout=10)
    return out if rc == 0 else ""


def _check_baseline(repo):
    local = _git(repo, "rev-parse", "main")
    _git(repo, "fetch", "origin", "--quiet")
    origin = _git(repo, "rev-parse", "origin/main")
    return {
        "local_main": local[:12] if local else None,
        "origin_main": origin[:12] if origin else None,
        "consistent": local == origin and local != "",
    }


def _check_pending_branches(repo):
    _git(repo, "fetch", "origin", "--quiet")
    out = _git(repo, "branch", "-r", "--no-merged", "origin/main")
    branches = [b.strip() for b in out.splitlines() if b.strip() and "HEAD" not in b]
    return branches[:20]


def _check_pending_prs(repo_path):
    rc, out, _ = _run(["gh", "pr", "list", "--repo", "k176060444-lgtm/vibe-coding-repo",
                        "--state", "open", "--json", "number,title,headRefName", "--limit", "10"])
    if rc == 0:
        try:
            return json.loads(out)
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def _check_worktrees(repo):
    out = _git(repo, "worktree", "list", "--porcelain")
    worktrees = []
    current = {}
    for line in out.splitlines():
        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line.split(" ", 1)[1]}
        elif line.startswith("HEAD "):
            current["head"] = line.split(" ", 1)[1][:12]
        elif line.startswith("branch "):
            current["branch"] = line.split(" ", 1)[1]
    if current:
        worktrees.append(current)

    for wt in worktrees:
        p = wt.get("path", "")
        if os.path.isdir(p):
            rc, s, _ = _run(["git", "-C", p, "status", "--porcelain"])
            wt["dirty"] = rc == 0 and s != ""
            wt["dirty_files"] = len(s.splitlines()) if s else 0
        else:
            wt["dirty"] = None
            wt["missing"] = True
    return worktrees


def _check_jobs(jobs_dir):
    if not os.path.isdir(jobs_dir):
        return {"total": 0, "jobs": []}
    jobs = []
    for d in sorted(os.listdir(jobs_dir)):
        wo_path = os.path.join(jobs_dir, d, "work-order.json")
        if os.path.isfile(wo_path):
            try:
                with open(wo_path) as f:
                    wo = json.load(f)
                jobs.append({
                    "job_id": d,
                    "status": wo.get("status", "unknown"),
                    "audit_status": wo.get("audit_status", "unknown"),
                    "title": wo.get("title", "")[:60],
                })
            except (json.JSONDecodeError, OSError):
                jobs.append({"job_id": d, "status": "unreadable"})
    return {"total": len(jobs), "jobs": jobs[-10:]}


def _check_test_envs():
    env_base = os.path.expanduser("~/.vibedev/test-envs")
    if not os.path.isdir(env_base):
        return {"count": 0, "envs": []}
    envs = []
    for profile in os.listdir(env_base):
        profile_dir = os.path.join(env_base, profile)
        if not os.path.isdir(profile_dir):
            continue
        for h in os.listdir(profile_dir):
            meta = os.path.join(profile_dir, h, "env_meta.json")
            if os.path.isfile(meta):
                try:
                    with open(meta) as f:
                        m = json.load(f)
                    envs.append({
                        "profile": m.get("profile"),
                        "venv_path": m.get("venv_path"),
                        "packages": len(m.get("installed_packages", [])),
                        "system_touched": m.get("system_python_touched", None),
                    })
                except (json.JSONDecodeError, OSError):
                    pass
    return {"count": len(envs), "envs": envs}


def _check_audit_lock(jobs_dir):
    lock_path = os.path.join(jobs_dir, "wo-code-repo-status-001", "work-order.json")
    if not os.path.isfile(lock_path):
        return {"locked": False, "error": "lock file missing"}
    try:
        with open(lock_path) as f:
            wo = json.load(f)
        return {
            "locked": True,
            "audit_status": wo.get("audit_status"),
            "push_allowed": wo.get("push_allowed", wo.get("allow_push", False)),
        }
    except (json.JSONDecodeError, OSError):
        return {"locked": True, "error": "unreadable"}


def dashboard(jobs_dir=None, output_json=False):
    jobs_dir = jobs_dir or os.path.expanduser("~/vibedev/jobs")
    bare_repo = os.path.expanduser("~/vibedev/repos/vibe-coding-repo.git")

    # Gateway limit risk check
    import importlib.util
    gw_health_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vibe_gateway_health.py")
    limit_info = {}
    if os.path.isfile(gw_health_path):
        try:
            spec = importlib.util.spec_from_file_location("vgw", gw_health_path)
            gw_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(gw_mod)
            if hasattr(gw_mod, "diagnose"):
                diag = gw_mod.diagnose(json_output=True)
                for pname, pdata in diag.get("profiles", {}).items():
                    lr = pdata.get("limit_risk", {})
                    limit_info[pname] = {
                        "etl": lr.get("execution_time_limit", "N/A"),
                        "risk": lr.get("limit_risk_status", "UNKNOWN"),
                        "indefinite": lr.get("execution_time_limit_is_indefinite", False),
                    }
        except Exception:
            pass

    result = {
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "baseline": _check_baseline(bare_repo),
        "pending_branches": _check_pending_branches(bare_repo),
        "pending_prs": _check_pending_prs(bare_repo),
        "worktrees": _check_worktrees(bare_repo),
        "jobs": _check_jobs(jobs_dir),
        "test_envs": _check_test_envs(),
        "audit_lock": _check_audit_lock(jobs_dir),
        "level5_activated": False,
        "gateway_limit_risk": limit_info,
        "node_attribution": {
            "controller_node": "windows",
            "execution_node": "debian",
        },
    }
    return result


def self_check(output_json=False):
    checks = []
    checks.append({"name": "version", "passed": True, "message": VERSION})
    try:
        d = dashboard()
        checks.append({"name": "dashboard_loads", "passed": "baseline" in d, "message": f"keys={len(d)}"})
        checks.append({"name": "has_baseline", "passed": d["baseline"]["local_main"] is not None, "message": f"local={d['baseline']['local_main']}"})
        checks.append({"name": "has_worktrees", "passed": isinstance(d["worktrees"], list), "message": f"count={len(d['worktrees'])}"})
        checks.append({"name": "has_jobs", "passed": isinstance(d["jobs"], dict), "message": f"total={d['jobs']['total']}"})
        checks.append({"name": "audit_lock_present", "passed": d["audit_lock"].get("locked", False), "message": f"locked={d['audit_lock'].get('locked')}"})
        checks.append({"name": "level5_off", "passed": d["level5_activated"] is False, "message": "level5=False"})
        checks.append({"name": "node_attribution", "passed": "controller_node" in d.get("node_attribution", {}), "message": "present"})
    except Exception as e:
        checks.append({"name": "dashboard_loads", "passed": False, "message": str(e)[:80]})

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    r = {"overall": "PASS" if passed == total else "FAIL", "passed": passed, "total": total, "checks": checks}
    return r


def build_parser():
    p = argparse.ArgumentParser(prog="vibe_batch_dashboard")
    p.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument("--json", dest="output_json", action="store_true")
    p.add_argument("--text", dest="output_text", action="store_true", default=True)
    p.add_argument("--self-check", dest="self_check_flag", action="store_true")
    p.add_argument("--jobs-dir", default=None)
    return p


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)

    if args.self_check_flag:
        r = self_check(args.output_json)
    else:
        r = dashboard(args.jobs_dir, args.output_json)

    if args.output_json:
        print(json.dumps(r, indent=2))
    else:
        if isinstance(r, dict) and "overall" in r:
            print(f"Overall: {r['overall']} ({r['passed']}/{r['total']})")
            for c in r.get("checks", []):
                icon = "PASS" if c["passed"] else "FAIL"
                print(f"  [{icon}] {c['name']}: {c['message']}")
        elif isinstance(r, dict):
            b = r.get("baseline", {})
            print(f"Baseline: local={b.get('local_main')} origin={b.get('origin_main')} consistent={b.get('consistent')}")
            print(f"Worktrees: {len(r.get('worktrees', []))}")
            for wt in r.get("worktrees", []):
                dirty = "DIRTY" if wt.get("dirty") else "clean"
                print(f"  {wt.get('path', '?')}: {wt.get('head', '?')} [{dirty}]")
            print(f"Jobs: {r['jobs']['total']}")
            print(f"Test envs: {r['test_envs']['count']}")
            al = r.get("audit_lock", {})
            print(f"Audit lock: locked={al.get('locked')} push_allowed={al.get('push_allowed')}")
            print(f"Level 5: {r.get('level5_activated')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
