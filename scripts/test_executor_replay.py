#!/usr/bin/env python3
"""Test Executor Replay — adapter + transcript + evidence verifier integration.

Validates the full replay chain: noop/dry-run plan → transcript create/list/show →
JSON parse → router commands → evidence verifier compatibility.

Usage:
    python3 scripts/test_executor_replay.py [--json]
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


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


def run_replay_tests(script_dir=None, as_json=False):
    """Run all replay integration tests."""
    if script_dir is None:
        script_dir = Path(__file__).parent

    tests = []
    txn_dir = tempfile.mkdtemp(prefix="replay_txn_")

    # Test 1: Adapter noop plan JSON
    def test_adapter_noop_plan():
        rc, out, err = _run_script(
            script_dir / "vibe_executor_adapter.py",
            ["plan", "--adapter", "noop", "--id", "replay-test", "--base-sha", "abc123", "--json"]
        )
        if rc != 0:
            return {"passed": False, "message": f"exit {rc}: {err}"}
        data = json.loads(out)
        if data["adapter_name"] != "noop" or data["mode"] != "noop":
            return {"passed": False, "message": f"wrong adapter/mode: {data.get('adapter_name')}/{data.get('mode')}"}
        if "refused_actions" not in data or "model_call" not in data["refused_actions"]:
            return {"passed": False, "message": "missing refused_actions"}
        return {"passed": True, "message": "noop plan OK"}

    tests.append(("adapter_noop_plan", test_adapter_noop_plan))

    # Test 2: Adapter dry-run plan JSON
    def test_adapter_dryrun_plan():
        rc, out, err = _run_script(
            script_dir / "vibe_executor_adapter.py",
            ["plan", "--adapter", "dry-run", "--id", "replay-test", "--base-sha", "abc123", "--json"]
        )
        if rc != 0:
            return {"passed": False, "message": f"exit {rc}: {err}"}
        data = json.loads(out)
        if data["adapter_name"] != "dry-run" or len(data["execution_plan"]["steps"]) != 8:
            return {"passed": False, "message": f"wrong plan: {data.get('adapter_name')} steps={len(data.get('execution_plan', {}).get('steps', []))}"}
        return {"passed": True, "message": "dry-run plan OK (8 steps)"}

    tests.append(("adapter_dryrun_plan", test_adapter_dryrun_plan))

    # Test 3: Adapter validate-inputs ALLOW
    def test_adapter_validate_allow():
        rc, out, err = _run_script(
            script_dir / "vibe_executor_adapter.py",
            ["validate-inputs", "--adapter", "noop", "--id", "replay-test", "--base-sha", "abc123", "--gate-verdict", "ALLOW", "--json"]
        )
        if rc != 0:
            return {"passed": False, "message": f"exit {rc}: {err}"}
        data = json.loads(out)
        if not data.get("valid"):
            return {"passed": False, "message": f"expected valid=True, got {data.get('valid')}"}
        return {"passed": True, "message": "validate-inputs ALLOW OK"}

    tests.append(("adapter_validate_allow", test_adapter_validate_allow))

    # Test 4: Adapter validate-inputs BLOCK
    def test_adapter_validate_block():
        rc, out, err = _run_script(
            script_dir / "vibe_executor_adapter.py",
            ["validate-inputs", "--adapter", "noop", "--id", "replay-test", "--base-sha", "abc123", "--gate-verdict", "BLOCK", "--json"]
        )
        if rc == 0:
            return {"passed": False, "message": "expected non-zero exit for BLOCK"}
        data = json.loads(out)
        if data.get("valid"):
            return {"passed": False, "message": f"expected valid=False for BLOCK"}
        return {"passed": True, "message": "validate-inputs BLOCK rejected OK"}

    tests.append(("adapter_validate_block", test_adapter_validate_block))

    # Test 5: Transcript create
    def test_transcript_create():
        rc, out, err = _run_script(
            script_dir / "vibe_execution_transcript.py",
            ["create", "--id", "replay-test", "--adapter", "noop", "--base-sha", "abc123",
             "--transcript-dir", txn_dir, "--json"]
        )
        if rc != 0:
            return {"passed": False, "message": f"exit {rc}: {err}"}
        data = json.loads(out)
        if data["workorder_id"] != "replay-test" or data["adapter"] != "noop":
            return {"passed": False, "message": f"wrong fields: {data.get('workorder_id')}/{data.get('adapter')}"}
        if "digest" not in data:
            return {"passed": False, "message": "missing digest"}
        return {"passed": True, "message": f"transcript create OK: {data['transcript_id']}"}

    tests.append(("transcript_create", test_transcript_create))

    # Test 6: Transcript list
    def test_transcript_list():
        rc, out, err = _run_script(
            script_dir / "vibe_execution_transcript.py",
            ["list", "--transcript-dir", txn_dir, "--json"]
        )
        if rc != 0:
            return {"passed": False, "message": f"exit {rc}: {err}"}
        data = json.loads(out)
        if data["count"] < 1:
            return {"passed": False, "message": f"expected count >= 1, got {data['count']}"}
        return {"passed": True, "message": f"transcript list OK: {data['count']} entries"}

    tests.append(("transcript_list", test_transcript_list))

    # Test 7: Transcript show
    def test_transcript_show():
        rc, out, err = _run_script(
            script_dir / "vibe_execution_transcript.py",
            ["show", "--transcript-id", "txn-001", "--transcript-dir", txn_dir, "--json"]
        )
        if rc != 0:
            return {"passed": False, "message": f"exit {rc}: {err}"}
        data = json.loads(out)
        if data["transcript_id"] != "txn-001":
            return {"passed": False, "message": f"wrong id: {data.get('transcript_id')}"}
        return {"passed": True, "message": "transcript show OK"}

    tests.append(("transcript_show", test_transcript_show))

    # Test 8: Router adapter integration
    def test_router_adapter():
        rc, out, err = _run_script(
            script_dir / "vibe_command_router.py",
            ["adapter", "capabilities", "--json"]
        )
        if rc != 0:
            return {"passed": False, "message": f"exit {rc}: {err}"}
        data = json.loads(out)
        if "adapters" not in data:
            return {"passed": False, "message": "missing adapters key"}
        return {"passed": True, "message": "router adapter OK"}

    tests.append(("router_adapter", test_router_adapter))

    # Test 9: Router transcript integration
    def test_router_transcript():
        rc, out, err = _run_script(
            script_dir / "vibe_command_router.py",
            ["txn", "list", "--transcript-dir", txn_dir, "--json"]
        )
        if rc != 0:
            return {"passed": False, "message": f"exit {rc}: {err}"}
        data = json.loads(out)
        if "transcripts" not in data:
            return {"passed": False, "message": "missing transcripts key"}
        return {"passed": True, "message": "router transcript OK"}

    tests.append(("router_transcript", test_router_transcript))

    # Test 10: Full replay chain (adapter plan → transcript create → verify transcript)
    def test_full_replay_chain():
        # Step 1: Get adapter plan
        rc, out, err = _run_script(
            script_dir / "vibe_executor_adapter.py",
            ["plan", "--adapter", "dry-run", "--id", "replay-chain", "--base-sha", "def456", "--json"]
        )
        if rc != 0:
            return {"passed": False, "message": f"adapter plan failed: {err}"}
        plan = json.loads(out)

        # Step 2: Create transcript from plan
        rc, out, err = _run_script(
            script_dir / "vibe_execution_transcript.py",
            ["create", "--id", "replay-chain", "--adapter", "dry-run", "--base-sha", "def456",
             "--transcript-dir", txn_dir, "--json"]
        )
        if rc != 0:
            return {"passed": False, "message": f"transcript create failed: {err}"}
        txn = json.loads(out)

        # Step 3: Verify transcript contains expected fields from plan
        if txn["workorder_id"] != plan["workorder_id"]:
            return {"passed": False, "message": f"workorder_id mismatch: {txn['workorder_id']} vs {plan['workorder_id']}"}
        if txn["base_sha"] != plan["base_sha"]:
            return {"passed": False, "message": f"base_sha mismatch: {txn['base_sha']} vs {plan['base_sha']}"}
        if txn["adapter"] != plan["adapter_name"]:
            return {"passed": False, "message": f"adapter mismatch: {txn['adapter']} vs {plan['adapter_name']}"}

        # Step 4: Verify transcript is retrievable
        rc, out, err = _run_script(
            script_dir / "vibe_execution_transcript.py",
            ["show", "--transcript-id", txn["transcript_id"], "--transcript-dir", txn_dir, "--json"]
        )
        if rc != 0:
            return {"passed": False, "message": f"transcript show failed: {err}"}
        shown = json.loads(out)
        if shown["digest"] != txn["digest"]:
            return {"passed": False, "message": "digest mismatch on show"}

        return {"passed": True, "message": f"full replay chain OK: plan→{txn['transcript_id']}→verify"}

    tests.append(("full_replay_chain", test_full_replay_chain))

    # Run all tests
    results = []
    for name, test_fn in tests:
        try:
            result = test_fn()
            results.append({"name": name, "passed": result["passed"], "message": result.get("message", "")})
        except Exception as e:
            results.append({"name": name, "passed": False, "message": str(e)})

    passed_count = sum(1 for r in results if r["passed"])
    failed_count = sum(1 for r in results if not r["passed"])
    overall = "PASS" if failed_count == 0 else "FAIL"

    if as_json:
        print(json.dumps({
            "overall": overall,
            "passed": passed_count,
            "failed": failed_count,
            "tests": results,
        }, indent=2))
    else:
        print("=" * 40)
        print("  Executor Replay Smoke Suite v1")
        print("=" * 40)
        for r in results:
            icon = "✓" if r["passed"] else "✗"
            print(f"  {icon} {r['name']}: {'PASS' if r['passed'] else 'FAIL'} - {r['message']}")
        print("-" * 40)
        print(f"  Overall: {overall} ({passed_count} passed, {failed_count} failed)")
        print("=" * 40)

    return 0 if overall == "PASS" else 1


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(prog="test_executor_replay")
    parser.add_argument("--json", dest="output_json", action="store_true")
    args = parser.parse_args(argv)
    return run_replay_tests(as_json=args.output_json)


if __name__ == "__main__":
    sys.exit(main())
