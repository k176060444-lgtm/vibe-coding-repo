#!/usr/bin/env python3
"""Work Order Packager v1 - Package draft + validation + snapshot into execution prompt.

Usage:
    python scripts/vibe_workorder_packager.py <draft.json>
    python scripts/vibe_workorder_packager.py <draft.json> --json
    python scripts/vibe_workorder_packager.py <draft.json> --compact
    python scripts/vibe_workorder_packager.py <draft.json> --max-chars 2000

Packages a validated Work Order draft with current system state into a
standard prompt for Hermes execution. Supports chunking for large prompts.

Constraints:
    - Read-only, no IO on import, standard library only.
    - Generates prompt only, never executes Work Order.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _run_script(script, *args, timeout=15):
    """Run a script and return parsed JSON or None."""
    try:
        cmd = [sys.executable, str(script)] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError, FileNotFoundError):
        pass
    return None


def _get_main_sha():
    """Get current HEAD SHA."""
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def _get_router_version(script_dir):
    """Get router version from source."""
    router = script_dir / "vibe_command_router.py"
    if router.exists():
        try:
            with open(router, "r") as f:
                for line in f:
                    if line.startswith("VERSION"):
                        import re
                        m = re.search(r'"([^"]+)"', line)
                        if m:
                            return m.group(1)
        except (OSError, IOError):
            pass
    return "unknown"


def _count_tests(script_dir):
    """Count test functions in smoke suite."""
    smoke = script_dir / "test_toolchain_smoke.py"
    if smoke.exists():
        try:
            with open(smoke, "r") as f:
                import re
                return len(re.findall(r'def _test_', f.read()))
        except (OSError, IOError):
            pass
    return 0


def package_work_order(draft, script_dir, compact=False, max_chars=None):
    """Package a Work Order draft into an execution prompt.

    Args:
        draft: dict with Work Order fields
        script_dir: Path to scripts directory
        compact: If True, shorter prompt
        max_chars: Max characters per chunk (None = no limit)

    Returns:
        dict with packaged prompt and metadata
    """
    main_sha = _get_main_sha()
    router_version = _get_router_version(script_dir)
    test_count = _count_tests(script_dir)

    wo_id = draft.get("work_order_id", "unknown")
    title = draft.get("title", "unknown")
    wo_type = draft.get("type", "unknown")
    risk = draft.get("risk_level", "unknown")
    requires_human = draft.get("requires_human_approval", False)
    goal = draft.get("goal", "")
    allowed = draft.get("allowed_paths", [])
    forbidden = draft.get("forbidden_actions", [])
    tests = draft.get("acceptance_tests", [])
    stops = draft.get("stop_conditions", [])
    reports = draft.get("expected_report_fields", [])

    # Build the execution prompt
    prompt_lines = [
        "Execute Work Order: %s" % wo_id,
        "",
        "## Task",
        "Title: %s" % title,
        "Type: %s" % wo_type,
        "Risk: %s" % risk,
        "Human Approval: %s" % ("REQUIRED" if requires_human else "Not required"),
        "",
        "## Goal",
        goal,
        "",
        "## Baseline",
        "origin/main: %s" % main_sha,
        "Router: v%s" % router_version,
        "Smoke: %d tests" % test_count,
        "",
        "## Scope",
        "Allowed paths:",
    ]
    for p in allowed:
        prompt_lines.append("  - %s" % p)
    prompt_lines.append("")
    prompt_lines.append("Forbidden actions:")
    if compact:
        prompt_lines.append("  (see standard forbidden list)")
    else:
        for f in forbidden[:5]:
            prompt_lines.append("  - %s" % f)
        if len(forbidden) > 5:
            prompt_lines.append("  ... and %d more" % (len(forbidden) - 5))

    prompt_lines.extend(["", "## Acceptance Tests"])
    for i, t in enumerate(tests, 1):
        prompt_lines.append("%d. %s" % (i, t))

    if not compact:
        prompt_lines.extend(["", "## Stop Conditions"])
        for s in stops:
            prompt_lines.append("  - %s" % s)

        prompt_lines.extend(["", "## Expected Report Fields"])
        for r in reports:
            prompt_lines.append("  - `%s`" % r)

    prompt_lines.extend([
        "",
        "## Safety",
        "- Do NOT modify secrets/CI/Provider/SSH",
        "- Do NOT deploy/tag/release",
        "- Do NOT force push or reset",
        "- Merge via vibe_autonomous_merge.py wrapper only",
        "- audit_tainted lock (wo-code-repo-status-001) must remain unchanged",
        "",
        "## Execution Pipeline",
        "1. Create worktree from base_sha",
        "2. Implement changes within allowed_paths",
        "3. Run py_compile on modified Python files",
        "4. Run smoke suite: python scripts/test_toolchain_smoke.py",
        "5. Commit and push branch",
        "6. Create PR",
        "7. Wrapper dry-run: vibe_autonomous_merge.py --dry-run",
        "8. Wrapper merge: vibe_autonomous_merge.py",
        "9. Post-merge freeze: fetch + verify main",
        "",
        "**This is an executable Work Order, not a draft. Proceed with implementation.**",
    ])

    prompt = "\n".join(prompt_lines)

    # Chunking
    chunks = []
    if max_chars and len(prompt) > max_chars:
        lines = prompt.split("\n")
        current_chunk = []
        current_len = 0
        for line in lines:
            if current_len + len(line) + 1 > max_chars and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            current_chunk.append(line)
            current_len += len(line) + 1
        if current_chunk:
            chunks.append("\n".join(current_chunk))
    else:
        chunks = [prompt]

    return {
        "work_order_id": wo_id,
        "title": title,
        "type": wo_type,
        "risk_level": risk,
        "requires_human_approval": requires_human,
        "base_sha": main_sha,
        "router_version": router_version,
        "smoke_tests": test_count,
        "prompt": prompt if len(chunks) == 1 else None,
        "chunks": chunks,
        "chunk_count": len(chunks),
        "total_chars": len(prompt),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_workorder_packager",
        description="Work Order Packager v1 - package drafts into execution prompts.",
    )
    parser.add_argument("draft", help="Draft JSON file path")
    parser.add_argument("--json", dest="output_json", action="store_true", default=False)
    parser.add_argument("--compact", action="store_true", default=False)
    parser.add_argument("--max-chars", type=int, default=None, help="Max chars per chunk")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        with open(args.draft, "r", encoding="utf-8") as f:
            draft = json.load(f)
    except (OSError, IOError) as e:
        print("ERROR: Cannot read: %s" % e, file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print("ERROR: Invalid JSON: %s" % e, file=sys.stderr)
        return 1

    script_dir = Path(__file__).parent
    result = package_work_order(draft, script_dir, args.compact, args.max_chars)

    if args.output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["chunk_count"] > 1:
            for i, chunk in enumerate(result["chunks"], 1):
                print("=== Chunk %d/%d ===" % (i, result["chunk_count"]))
                print(chunk)
                print()
        else:
            print(result["prompt"])

    return 0


if __name__ == "__main__":
    sys.exit(main())
