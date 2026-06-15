#!/usr/bin/env python3
"""Demo Scenario Pack v1 - Repeatable scenario examples for intake→dispatch→report pipeline.

Usage:
    python scripts/vibe_demo_scenarios.py [--scenario NAME] [--json] [--list]

Scenarios:
    queue-clean     - Demonstrate queue-clean flow (snapshot→dispatch→dashboard)
    feature-request - Demonstrate feature request flow (intake→dispatch→batch-plan)
    maintenance     - Demonstrate maintenance flow (health→release-notes→dashboard)

All scenarios are read-only. No PRs created, no tasks executed.

Constraints:
    - Read-only, no IO on import, standard library only.
    - Runs existing scripts via subprocess, never modifies repo.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


SCENARIOS = {
    "queue-clean": {
        "title": "Queue Clean — System Health & Status",
        "description": "Demonstrate the read-only status check flow when the queue is clean.",
        "steps": [
            {"script": "vibe_operator_snapshot.py", "args": ["--compact"], "label": "Operator Snapshot"},
            {"script": "vibe_dispatch_planner.py", "args": ["--compact"], "label": "Dispatch Planner"},
            {"script": "vibe_release_notes.py", "args": ["--compact", "--limit", "5"], "label": "Release Notes (last 5)"},
        ],
        "expected_outcome": "queue_clean — no action required, system healthy",
    },
    "feature-request": {
        "title": "Feature Request — Intake & Planning",
        "description": "Demonstrate how a user requirement flows through intake and planning.",
        "steps": [
            {
                "script": "vibe_workorder_intake.py",
                "args": ["Add --verbose flag to health check", "--type", "code", "--json"],
                "label": "Intake: draft Work Order",
            },
            {
                "script": "vibe_dispatch_planner.py",
                "args": ["--json"],
                "label": "Dispatch: current recommendations",
            },
            {
                "script": "vibe_batch_plan.py",
                "args": ["--json", "--limit", "3"],
                "label": "Batch Plan: execution plan",
            },
        ],
        "expected_outcome": "Work Order draft generated, dispatch shows queue_clean, batch shows 0 tasks",
    },
    "maintenance": {
        "title": "Maintenance — Health & Reporting",
        "description": "Demonstrate health check and progress reporting flow.",
        "steps": [
            {"script": "vibe_health_check.py", "args": [], "label": "Health Check"},
            {"script": "vibe_release_notes.py", "args": ["--compact"], "label": "Release Notes"},
            {"script": "vibe_operator_snapshot.py", "args": ["--compact"], "label": "Operator Snapshot"},
        ],
        "expected_outcome": "All checks pass, system operational",
    },
}


def _run_step(script_dir, step, as_json=False):
    """Run a single scenario step."""
    script_path = script_dir / step["script"]
    if not script_path.exists():
        return {"label": step["label"], "status": "SKIP", "message": "script not found"}

    args = step["args"][:]
    if as_json and "--json" not in args and "--compact" in args:
        args = [a for a in args if a != "--compact"]
        args.append("--json")

    try:
        cmd = [sys.executable, str(script_path)] + args
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {
            "label": step["label"],
            "status": "PASS" if result.returncode == 0 else "FAIL",
            "exit_code": result.returncode,
            "output_preview": result.stdout[:500] if result.stdout else "",
            "stderr_preview": result.stderr[:200] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"label": step["label"], "status": "TIMEOUT", "message": "30s timeout"}
    except (OSError, FileNotFoundError) as e:
        return {"label": step["label"], "status": "ERROR", "message": str(e)}


def run_scenario(scenario_name, script_dir, as_json=False):
    """Run a named scenario."""
    if scenario_name not in SCENARIOS:
        return None

    scenario = SCENARIOS[scenario_name]
    results = []
    for step in scenario["steps"]:
        results.append(_run_step(script_dir, step, as_json))

    passed = sum(1 for r in results if r["status"] == "PASS")
    total = len(results)

    return {
        "scenario": scenario_name,
        "title": scenario["title"],
        "description": scenario["description"],
        "steps": results,
        "passed": passed,
        "total": total,
        "overall": "PASS" if passed == total else "FAIL",
        "expected_outcome": scenario["expected_outcome"],
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_demo_scenarios",
        description="Demo Scenario Pack v1 - repeatable scenario examples.",
    )
    parser.add_argument("--scenario", "-s", default=None,
                        help="Scenario to run: queue-clean, feature-request, maintenance")
    parser.add_argument("--json", dest="output_json", action="store_true", default=False)
    parser.add_argument("--list", dest="list_scenarios", action="store_true", default=False)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    script_dir = Path(__file__).parent

    if args.list_scenarios:
        for name, sc in SCENARIOS.items():
            print("  %-20s %s" % (name, sc["title"]))
        return 0

    if args.scenario is None:
        print("Available scenarios:", file=sys.stderr)
        for name, sc in SCENARIOS.items():
            print("  %-20s %s" % (name, sc["title"]), file=sys.stderr)
        print("\nUsage: vibe_demo_scenarios --scenario <name>", file=sys.stderr)
        return 1

    result = run_scenario(args.scenario, script_dir, args.output_json)
    if result is None:
        print("ERROR: Unknown scenario: %s" % args.scenario, file=sys.stderr)
        print("Available: %s" % ", ".join(SCENARIOS.keys()), file=sys.stderr)
        return 1

    if args.output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=" * 40)
        print("  Demo Scenario: %s" % result["title"])
        print("=" * 40)
        for step in result["steps"]:
            icon = "✓" if step["status"] == "PASS" else "✗" if step["status"] == "FAIL" else "⊘"
            print("  %s %s: %s" % (icon, step["label"], step["status"]))
        print("-" * 40)
        print("  Overall: %s (%d/%d)" % (result["overall"], result["passed"], result["total"]))
        print("  Expected: %s" % result["expected_outcome"])
        print("=" * 40)

    return 0 if result["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
