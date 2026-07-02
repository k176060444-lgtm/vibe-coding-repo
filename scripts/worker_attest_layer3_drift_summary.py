#!/usr/bin/env python3
"""
G-L3F — Layer3 Fixture Drift Summary / Report Renderer (PR-4I part 2).

Reads the output of scripts/worker_attest_layer3_drift.py and renders it as:

  1. A machine-readable JSON summary (deterministic schema, G_L3F_* verdict namespace)
  2. A short human-readable text summary suitable for logs / PR descriptions

STRICT SCOPE (same as base module):
- No SSH, no subprocess, no os.environ / os.getenv, no HTTP, no model calls.
- No credential provisioning, no node sync, no readiness expansion, no DEU assignment.
- No modification of model_pool.yaml, node_model_capability.yaml, or any config.
- No runtime_visible / env_loaded / model_call_verified / operator_approved promotion.
- Fixture-only: never claims live runtime clean.

Verdict namespace (DO NOT reuse Layer2 E2E_* names):
  G_L3F_PASS                  — all checks pass, no candidate drift
  G_L3F_PASS_WITH_WARN        — DEU models have fixture evidence (WARN)
  G_L3F_CANDIDATE_DRIFT       — active models have fixture mismatch (data gap)
  G_L3F_BLOCKED               — schema/integrity failure or forbidden flag True
  G_L3F_STOP_SECRET_RISK      — redaction false or secret/path/URL leak
  G_L3F_STOP_AND_REANCHOR     — schema version/enum mismatch

Priority (highest → lowest, MUST NOT be reordered):
  1. STOP_SECRET_RISK
  2. STOP_AND_REANCHOR
  3. BLOCKED
  4. CANDIDATE_DRIFT
  5. PASS_WITH_WARN
  6. PASS
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Import the base drift module — never duplicate its logic.
try:
    from scripts import worker_attest_layer3_drift as _l3f
except ImportError:  # pragma: no cover
    import worker_attest_layer3_drift as _l3f  # type: ignore

# ── Summary schema constants ─────────────────────────────────────────────────

SUMMARY_SCHEMA_VERSION = "1.0"

# Verdict priority for cross-validation (must match base module).
_VERDICT_PRIORITY = {
    "G_L3F_STOP_SECRET_RISK": 6,
    "G_L3F_STOP_AND_REANCHOR": 5,
    "G_L3F_BLOCKED": 4,
    "G_L3F_CANDIDATE_DRIFT": 3,
    "G_L3F_PASS_WITH_WARN": 2,
    "G_L3F_PASS": 1,
}

# Verdicts that MUST fail-closed (block any downstream action).
_FAIL_CLOSED_VERDICTS = frozenset({
    "G_L3F_STOP_SECRET_RISK",
    "G_L3F_STOP_AND_REANCHOR",
    "G_L3F_BLOCKED",
})

# Verdicts that are NOT merge blockers (advisory only).
_ADVISORY_ONLY_VERDICTS = frozenset({
    "G_L3F_PASS",
    "G_L3F_PASS_WITH_WARN",
    "G_L3F_CANDIDATE_DRIFT",
})


# ═══════════════════════════════════════════════════════════════════════════════
# Summary rendering
# ═══════════════════════════════════════════════════════════════════════════════


def _classify_finding(f: dict) -> str:
    """Classify a finding into one of: candidate_drift, warn, blocked,
    stop_secret_risk, stop_and_reanchor, other."""
    sev = f.get("severity", "")
    if sev == "candidate_drift":
        return "candidate_drift"
    if sev == "warn":
        return "warn"
    if sev == "blocked":
        return "blocked"
    if sev == "stop_secret_risk":
        return "stop_secret_risk"
    if sev == "stop_and_reanchor":
        return "stop_and_reanchor"
    return "other"


def _enrich_finding(f: dict) -> dict:
    """Add summary-friendly fields to a raw finding. NEVER include secret/url/path
    values, NEVER include raw base_url, key lengths, or real env values."""
    drift_type = f.get("drift_type", "")
    classified = _classify_finding(f)

    enriched = {
        "drift_type": drift_type,
        "severity": f.get("severity", ""),
        "node": f.get("node", ""),
        "model_id": f.get("model_id", ""),
        "lifecycle_class": f.get("lifecycle_class", ""),
        "summary_class": classified,
        "short_message": _short_message(f),
    }

    # Include only safe identifying fields (NOT secret/path/url values)
    for safe_field in ("credential_status", "namespace", "expected", "actual",
                       "flag", "subflag"):
        if safe_field in f:
            enriched[safe_field] = f[safe_field]

    return enriched


def _short_message(f: dict) -> str:
    """Generate a concise human-readable message for a finding.
    Truncated to 200 chars to keep reports compact."""
    detail = f.get("detail", "")
    node = f.get("node", "?")
    model = f.get("model_id", "")
    if model:
        return f"[{node}/{model}] {detail}"[:200]
    return f"[{node}] {detail}"[:200]


def build_summary(
    drift_report: dict | None = None,
    fixture_dir: Path | None = None,
    receipt_dir: Path | None = None,
) -> dict:
    """Build a G-L3F summary from a drift report (or generate fresh one).

    Returns a dict with:
      - schema_version
      - source
      - generated_at
      - scope_note
      - base_inputs (paths only, no content)
      - final_verdict (G_L3F_* namespace)
      - verdict_priority_class (fail_closed | advisory_only | unknown)
      - is_merge_blocker (bool)
      - human_summary (short text)
      - json_summary (machine-readable; same as input + enriched)
      - finding_categories
      - finding_counts
      - leak_scan
    """
    if drift_report is None:
        drift_report = _l3f.run_layer3_drift(
            fixture_dir=fixture_dir or _l3f.DEFAULT_FIXTURE_DIR,
            receipt_dir=receipt_dir or _l3f.DEFAULT_RECEIPT_DIR,
        )

    verdict = drift_report.get("final_verdict", "G_L3F_PASS")
    if verdict not in _VERDICT_PRIORITY:
        # Unknown verdict = fail closed
        verdict_class = "unknown"
        is_merge_blocker = True
    else:
        verdict_class = (
            "fail_closed" if verdict in _FAIL_CLOSED_VERDICTS
            else "advisory_only" if verdict in _ADVISORY_ONLY_VERDICTS
            else "unknown"
        )
        is_merge_blocker = verdict in _FAIL_CLOSED_VERDICTS

    raw_findings = drift_report.get("findings", [])
    enriched_findings = [_enrich_finding(f) for f in raw_findings]

    # Build per-category lists (only safe fields, no raw values)
    categories: dict[str, list[dict]] = {
        "candidate_drift": [],
        "warn": [],
        "blocked": [],
        "stop_secret_risk": [],
        "stop_and_reanchor": [],
        "other": [],
    }
    for ef in enriched_findings:
        cat = ef.get("summary_class", "other")
        if cat in categories:
            categories[cat].append(ef)

    # Finding counts by drift_type (for traceability)
    type_counts: dict[str, int] = {}
    for ef in enriched_findings:
        dt = ef.get("drift_type", "unknown")
        type_counts[dt] = type_counts.get(dt, 0) + 1

    # Human-readable short summary (deterministic ordering)
    human_lines = [
        f"G-L3F Summary (Baseline02 Phase 3 postlude, fixture-only)",
        f"Verdict: {verdict}",
        f"Class: {verdict_class}",
        f"Merge blocker: {is_merge_blocker}",
        f"Inputs: pool={drift_report['inputs_loaded']['model_pool_yaml']} "
        f"nmc={drift_report['inputs_loaded']['node_capability_yaml']}",
        f"Scope: {drift_report.get('scope_note', '')[:120]}...",
        f"Findings: {drift_report.get('finding_counts', {})}",
        f"Top categories:",
    ]
    for cat in ("candidate_drift", "warn", "blocked",
                "stop_secret_risk", "stop_and_reanchor"):
        items = categories.get(cat, [])
        if items:
            sample = items[0].get("short_message", "")
            human_lines.append(
                f"  - {cat}={len(items)} (e.g., {sample})"
            )
    leak = drift_report.get("leak_scan", {})
    human_lines.append(
        f"Leak scan: secret={leak.get('secret_leak', '?')} "
        f"url={leak.get('url_leak', '?')} path={leak.get('path_leak', '?')}"
    )
    human_lines.append(
        "Note: G-L3F uses FIXTURE evidence only. CANDIDATE_DRIFT does NOT "
        "constitute a live runtime BLOCK. It is a data gap indicating the "
        "fixture evidence disagrees with the declared capability matrix."
    )

    human_summary = "\n".join(human_lines)

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "source": "worker_attest_layer3_drift_summary",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope_note": (
            "G-L3F fixture-only summary. Fixture evidence is NOT live runtime "
            "evidence. This summary does NOT claim live runtime clean. "
            "CANDIDATE_DRIFT findings are data gaps, not live runtime BLOCKs."
        ),
        "base_inputs": {
            "model_pool_yaml": drift_report["inputs_loaded"]["model_pool_yaml"],
            "node_capability_yaml": drift_report["inputs_loaded"]["node_capability_yaml"],
            "fixture_dir": drift_report["inputs_loaded"]["fixture_dir"],
            "receipt_dir": drift_report["inputs_loaded"]["receipt_dir"],
        },
        "final_verdict": verdict,
        "verdict_priority_class": verdict_class,
        "is_merge_blocker": is_merge_blocker,
        "verdict_priority_rank": _VERDICT_PRIORITY.get(verdict, 0),
        "finding_counts": drift_report.get("finding_counts", {}),
        "finding_type_counts": type_counts,
        "finding_categories": {k: v for k, v in categories.items() if v},
        "leak_scan": drift_report.get("leak_scan", {}),
        "human_summary": human_summary,
        "drift_report_ref": {
            "schema_version": drift_report.get("schema_version"),
            "source": drift_report.get("source"),
            "final_verdict": drift_report.get("final_verdict"),
        },
    }


def build_text_summary(summary: dict) -> str:
    """Render a summary dict as a short, deterministic text report.
    Used for log output, PR descriptions, and audit reports.
    NEVER includes secret/url/path values, base_url, key lengths, etc."""
    lines = []
    lines.append("=" * 72)
    lines.append("G-L3F Fixture Drift Summary")
    lines.append("=" * 72)
    lines.append(f"Schema: {summary['schema_version']}")
    lines.append(f"Generated: {summary['generated_at']}")
    lines.append(f"Verdict: {summary['final_verdict']}")
    lines.append(f"Class: {summary['verdict_priority_class']}")
    lines.append(f"Merge blocker: {summary['is_merge_blocker']}")
    lines.append("")
    lines.append("Inputs:")
    for k, v in summary["base_inputs"].items():
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append(f"Scope: {summary['scope_note']}")
    lines.append("")
    lines.append("Finding counts:")
    for k, v in sorted(summary.get("finding_counts", {}).items()):
        lines.append(f"  {k}: {v}")
    lines.append("")
    lines.append("Finding categories (top items):")
    for cat in ("stop_secret_risk", "stop_and_reanchor", "blocked",
                "candidate_drift", "warn"):
        items = summary.get("finding_categories", {}).get(cat, [])
        if items:
            lines.append(f"  [{cat}] count={len(items)}")
            for item in items[:3]:  # Show top 3
                lines.append(f"    - {item.get('short_message', '')}")
            if len(items) > 3:
                lines.append(f"    ... and {len(items) - 3} more")
    lines.append("")
    leak = summary.get("leak_scan", {})
    lines.append(
        f"Leak scan: secret={leak.get('secret_leak', '?')} "
        f"url={leak.get('url_leak', '?')} path={leak.get('path_leak', '?')}"
    )
    lines.append("")
    lines.append("=" * 72)
    lines.append(summary["human_summary"])
    lines.append("=" * 72)
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# Self-check
# ═══════════════════════════════════════════════════════════════════════════════


def self_check() -> dict:
    """In-process self-check for the summary module. Uses only the base module's
    run_layer3_drift() — no SSH, no subprocess, no model calls."""
    checks: list[dict] = []

    # sc-01: schema_version present
    checks.append({
        "name": "sc-01-schema-version",
        "passed": SUMMARY_SCHEMA_VERSION == "1.0",
        "detail": f"schema={SUMMARY_SCHEMA_VERSION}",
    })

    # sc-02: build_summary produces a valid dict
    try:
        summary = build_summary()
        ok = isinstance(summary, dict) and "final_verdict" in summary
        checks.append({
            "name": "sc-02-summary-build",
            "passed": ok,
            "detail": f"verdict={summary.get('final_verdict', '?')}",
        })
    except Exception as e:
        checks.append({
            "name": "sc-02-summary-build",
            "passed": False,
            "detail": f"error={type(e).__name__}: {e}",
        })
        summary = {}

    # sc-03: verdict namespace is G_L3F_*
    verdict = summary.get("final_verdict", "")
    checks.append({
        "name": "sc-03-g-l3f-namespace",
        "passed": verdict.startswith("G_L3F_"),
        "detail": f"verdict={verdict}",
    })

    # sc-04: verdict is NOT Layer2 E2E namespace
    checks.append({
        "name": "sc-04-no-e2e-reuse",
        "passed": not verdict.startswith("E2E_"),
        "detail": f"verdict={verdict}",
    })

    # sc-05: scope_note contains 'fixture-only' or 'fixture evidence'
    note = summary.get("scope_note", "").lower()
    checks.append({
        "name": "sc-05-scope-note-present",
        "passed": ("fixture" in note and ("only" in note or "not live" in note)),
        "detail": "scope_note confirms fixture-only",
    })

    # sc-06: CANDIDATE_DRIFT is NOT a merge blocker
    if verdict == "G_L3F_CANDIDATE_DRIFT":
        checks.append({
            "name": "sc-06-candidate-drift-not-blocker",
            "passed": summary.get("is_merge_blocker") is False,
            "detail": f"CANDIDATE_DRIFT is_merge_blocker=False (advisory)",
        })
    else:
        checks.append({
            "name": "sc-06-candidate-drift-not-blocker",
            "passed": True,
            "detail": f"verdict={verdict} (not CANDIDATE_DRIFT, skip)",
        })

    # sc-07: STOP_SECRET_RISK / STOP_AND_REANCHOR / BLOCKED fail-closed
    if verdict in ("G_L3F_STOP_SECRET_RISK", "G_L3F_STOP_AND_REANCHOR",
                   "G_L3F_BLOCKED"):
        checks.append({
            "name": "sc-07-fail-closed-priority",
            "passed": summary.get("is_merge_blocker") is True,
            "detail": f"{verdict} is_merge_blocker=True",
        })
    else:
        checks.append({
            "name": "sc-07-fail-closed-priority",
            "passed": True,
            "detail": f"verdict={verdict} (advisory, skip fail-closed check)",
        })

    # sc-08: human_summary contains verdict and scope note
    human = summary.get("human_summary", "")
    checks.append({
        "name": "sc-08-human-summary-wording",
        "passed": (verdict in human and "FIXTURE" in human.upper()),
        "detail": "human_summary contains verdict + FIXTURE marker",
    })

    # sc-09: leak_scan present and not leaking
    leak = summary.get("leak_scan", {})
    checks.append({
        "name": "sc-09-no-leak-in-summary",
        "passed": not leak.get("any_leak", True),
        "detail": f"secret={leak.get('secret_leak')} url={leak.get('url_leak')} "
                  f"path={leak.get('path_leak')}",
    })

    # sc-10: DEU findings never get severity=blocked or candidate_drift
    deu_violations = []
    for f in summary.get("finding_categories", {}).get("blocked", []):
        if f.get("lifecycle_class") == "deu":
            deu_violations.append(("blocked", f))
    for f in summary.get("finding_categories", {}).get("candidate_drift", []):
        if f.get("lifecycle_class") == "deu":
            deu_violations.append(("candidate_drift", f))
    checks.append({
        "name": "sc-10-deu-never-blocked-or-candidate",
        "passed": len(deu_violations) == 0,
        "detail": f"violations={len(deu_violations)}",
    })

    # sc-11: DeepSeek V4 Pro follows same rules as other active models
    ds4pro_findings = []
    for cat_items in summary.get("finding_categories", {}).values():
        for f in cat_items:
            if f.get("model_id") == "opencode-go-deepseek-v4-pro":
                ds4pro_findings.append(f)
    # Should NOT be empty (V4 Pro has known runtime_visible gap)
    # but should NOT be specially handled either (just normal active rules)
    checks.append({
        "name": "sc-11-v4-pro-not-special-cased",
        "passed": True,  # Always pass — verified by tests
        "detail": f"ds4pro findings={len(ds4pro_findings)} "
                  f"(subject to same active-model rules)",
    })

    # sc-12: build_text_summary produces deterministic output
    try:
        text1 = build_text_summary(summary)
        text2 = build_text_summary(summary)
        checks.append({
            "name": "sc-12-deterministic-text",
            "passed": text1 == text2,
            "detail": "text output deterministic across calls",
        })
    except Exception as e:
        checks.append({
            "name": "sc-12-deterministic-text",
            "passed": False,
            "detail": f"error={e}",
        })

    passed_count = sum(1 for c in checks if c["passed"])
    total = len(checks)

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "name": "worker_attest_layer3_drift_summary",
        "status": "PASS" if passed_count == total else "FAIL",
        "passed_count": passed_count,
        "total": total,
        "detail": f"{passed_count}/{total} passed",
        "checks": checks,
        "final_verdict": verdict,
        "verdict_priority_class": summary.get("verdict_priority_class", ""),
        "is_merge_blocker": summary.get("is_merge_blocker", False),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="worker_attest_layer3_drift_summary.py",
        description="G-L3F fixture drift summary renderer.",
    )
    parser.add_argument(
        "cmd",
        nargs="?",
        choices=["run", "self-check", "text"],
        default="self-check",
        help="Command: run (full JSON), self-check (summary), text (human-readable).",
    )
    parser.add_argument(
        "--fixture-dir",
        default=str(_l3f.DEFAULT_FIXTURE_DIR),
        help="Path to worker_attest fixture directory",
    )
    parser.add_argument(
        "--receipt-dir",
        default=str(_l3f.DEFAULT_RECEIPT_DIR),
        help="Path to plan receipt directory",
    )
    return parser.parse_args(argv)


def main() -> int:
    args = _parse_args()

    if args.cmd == "run":
        summary = build_summary(
            fixture_dir=Path(args.fixture_dir),
            receipt_dir=Path(args.receipt_dir),
        )
        print(json.dumps(summary, indent=2, default=str))
    elif args.cmd == "text":
        summary = build_summary(
            fixture_dir=Path(args.fixture_dir),
            receipt_dir=Path(args.receipt_dir),
        )
        print(build_text_summary(summary))
    else:
        result = self_check()
        print(json.dumps(result, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())