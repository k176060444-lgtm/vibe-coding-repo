#!/usr/bin/env python3
"""Report Export v1 - Export snapshot/release-notes/dashboard reports to files.

Usage:
    python scripts/vibe_report_export.py --kind snapshot|release-notes|dashboard|all
                                         [--output-dir DIR] [--json] [--dry-run]

Exports toolchain reports as Markdown files for QQ/Hermes delivery or archival.
Read-only by default; writes only to specified --output-dir.

Constraints:
    - Read-only, no IO on import, standard library only.
    - Writes only to --output-dir (never modifies repo source).
    - Never writes secrets or credentials.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# V1.21.22: Import run_report for deferred registry export
try:
    from vibe_run_report import run_report as _run_report
except ImportError:
    _run_report = None


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


def _export_kind(script_dir, kind):
    """Export a single report kind."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if kind == "snapshot":
        rc, stdout, stderr = _run_script(script_dir / "vibe_operator_snapshot.py", ["--compact"])
        # V1.21.25A: Single run_report() call — SSOT for deferred/verifier
        _rr = None
        if rc == 0 and stdout and _run_report is not None:
            try:
                _rr = _run_report(repo_root=script_dir.parent)
            except Exception:
                _rr = None  # Graceful fallback — no deferred/verifier sections
        # Append deferred registry section (from cached _rr)
        if _rr:
            _dar = _rr.get("deferred_action_registry")
            if _dar:
                _lines = ["\n## Deferred Action Registry\n"]
                _lines.append("- %d deferred action(s) registered\n" % len(_dar))
                for _e in _dar:
                    _action = _e.get("action", "?")
                    _wid = _e.get("workorder_id", "?")
                    _risk = _e.get("risk_level", "low")
                    _dedicated = " ⚠️ dedicated/critical" if _e.get("dedicated_approval") else ""
                    _real = "yes" if _e.get("real_execution") else "no"
                    _lines.append("- `%s` | wo=`%s` | risk=%s | real_exec=%s%s\n" % (
                        _action, _wid, _risk, _real, _dedicated))
                stdout += "".join(_lines)
            # Append verifier deferred result section (from same cached _rr)
            _vdr = _rr.get("verifier_deferred_result")
            if _vdr:
                _vdr_result = _vdr.get("result", "UNKNOWN")
                _vdr_detail = _vdr.get("detail", "")
                _vlines = ["\n## Verifier Deferred Registry\n"]
                if _vdr_result == "PASS":
                    _vlines.append("- ✅ %s\n" % _vdr_detail)
                elif _vdr_result == "WARN":
                    _vlines.append("- ⚠️ %s\n" % _vdr_detail)
                    for _w in _vdr.get("warnings", []):
                        _vlines.append("  - %s\n" % _w)
                elif _vdr_result == "FAIL":
                    _vlines.append("- ❌ %s\n" % _vdr_detail)
                    for _e2 in _vdr.get("errors", []):
                        _vlines.append("  - %s\n" % _e2)
                stdout += "".join(_vlines)
        filename = "snapshot_%s.md" % timestamp
    elif kind == "release-notes":
        rc, stdout, stderr = _run_script(script_dir / "vibe_release_notes.py", ["--compact"])
        filename = "release_notes_%s.md" % timestamp
    elif kind == "dashboard":
        rc, stdout, stderr = _run_script(script_dir / "vibe_operator_snapshot.py", ["--compact"])
        # Also read the dashboard doc
        dashboard_path = script_dir.parent / "docs" / "PROJECT_DASHBOARD.md"
        if dashboard_path.exists():
            try:
                with open(dashboard_path, "r") as f:
                    stdout = f.read()
            except (OSError, IOError):
                pass
        filename = "dashboard_%s.md" % timestamp
    else:
        return None

    return {
        "kind": kind,
        "filename": filename,
        "exit_code": rc,
        "content": stdout if rc == 0 else "",
        "error": stderr if rc != 0 else "",
        "timestamp": timestamp,
    }


def export_reports(kind, script_dir, output_dir=None, dry_run=False):
    """Export reports and optionally write to output directory.

    Args:
        kind: 'snapshot', 'release-notes', 'dashboard', or 'all'
        script_dir: Path to scripts directory
        output_dir: Directory to write files (None = preview only)
        dry_run: If True, show what would be written without writing

    Returns:
        dict with export results
    """
    kinds = ["snapshot", "release-notes", "dashboard"] if kind == "all" else [kind]
    results = []

    for k in kinds:
        result = _export_kind(script_dir, k)
        if result:
            results.append(result)

    # Write files if output_dir specified and not dry_run
    written = []
    if output_dir and not dry_run:
        os.makedirs(output_dir, exist_ok=True)
        for r in results:
            if r["exit_code"] == 0 and r["content"]:
                filepath = os.path.join(output_dir, r["filename"])
                try:
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(r["content"])
                    written.append(filepath)
                except (OSError, IOError) as e:
                    r["error"] = "write failed: %s" % e

    return {
        "kind": kind,
        "exported": len([r for r in results if r["exit_code"] == 0]),
        "total": len(results),
        "output_dir": output_dir,
        "dry_run": dry_run,
        "written_files": written,
        "results": results,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_parser():
    parser = argparse.ArgumentParser(
        prog="vibe_report_export",
        description="Report Export v1 - export toolchain reports to files.",
    )
    parser.add_argument("--kind", required=True,
                        choices=["snapshot", "release-notes", "dashboard", "all"],
                        help="Report kind to export")
    parser.add_argument("--output-dir", "-o", default=None,
                        help="Directory to write report files")
    parser.add_argument("--json", dest="output_json", action="store_true", default=False)
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Preview what would be exported without writing")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    script_dir = Path(__file__).parent

    result = export_reports(args.kind, script_dir, args.output_dir, args.dry_run)

    if args.output_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("=" * 40)
        print("  Report Export: %s" % result["kind"])
        print("=" * 40)
        for r in result["results"]:
            icon = "✓" if r["exit_code"] == 0 else "✗"
            print("  %s %s: %s" % (icon, r["kind"], r["filename"] if r["exit_code"] == 0 else r["error"]))
        print("-" * 40)
        print("  Exported: %d/%d" % (result["exported"], result["total"]))
        if result["dry_run"]:
            print("  Mode: DRY RUN (no files written)")
        elif result["written_files"]:
            print("  Written to: %s" % result["output_dir"])
        print("=" * 40)

    return 0 if result["exported"] == result["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
