"""worker_attest 5-receipt E2E summary — Baseline02 Phase 3 G-5-RECEIPT-E2E.

Local-only, read-only summarizer that aggregates up to 5 worker_attest receipts
(21bao dry-run + 21bao real-read + 5bao SSH canary + 9bao SSH canary + optional
prior-summary receipt) into a single Layer-2 E2E verdict.

STRICT SCOPE:
- No SSH, no subprocess, no network calls.
- No model calls, no credential provisioning, no node sync.
- No readiness expansion, no D-A / D-B decisions.
- No PR-7, no Baseline03, no Stage8.
- Reads only receipt objects passed in memory or from allowlisted local
  JSON files under tests/fixtures/ or a caller-supplied fixture path.
- Preserves redaction and forbidden_operation_flags blocker semantics from
  the source receipts; never mutates them.
- Fail-closed: any missing receipt / invalid receipt / forbidden flag True /
  redaction False / secret-or-URL/path leak in redacted_output produces
  BLOCKED verdict.

VERDICTS:
- E2E_PASS                  : all 4 canary receipts valid + fully redacted +
                              forbidden flags all False + no leaks.
- E2E_BLOCKED               : any receipt fails validation, redaction, or
                              forbidden-flag rules.
- STOP_SECRET_RISK          : hard leak of a plausibly real secret / URL /
                              filesystem path detected in any summarized field.
- STOP_AND_REANCHOR         : receipt schema disagreement (schema_version,
                              node/collection_status enums, etc.) that
                              suggests the caller passed stale data.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# Import receipt schema constants from the plan module to stay in sync.
try:
    from scripts import worker_attest_plan as _plan
except ImportError:  # pragma: no cover
    import worker_attest_plan as _plan  # type: ignore

SUMMARY_SCHEMA_VERSION = "1.0"

# Required per-canary lanes for a complete 5-receipt E2E.
# Lane 5 (summary_prior) is optional carry-over from a previous summary run.
CANONICAL_LANES = (
    "21bao_dry_run",
    "21bao_real_read",
    "5bao_ssh_canary",
    "9bao_ssh_canary",
)
OPTIONAL_LANES = ("summary_prior",)

# All 5 redaction sub-flags MUST be True for a canary receipt to pass.
REDACTION_SUBFLAGS = (
    "no_secret_value",
    "no_env_value",
    "no_base_url_value",
    "no_real_endpoint_url",
    "no_key_length",
)

# All 6 forbidden operation flags MUST be False for a canary receipt to pass.
# "sanctioned SSH" is expressed by the collector still reporting ssh_attempted=False
# in its emitted receipt — this preserves the blocker semantic: a True value
# always indicates a forbidden action, never a sanctioned one.
FORBIDDEN_FLAGS = (
    "ssh_attempted",
    "subprocess_attempted",
    "os_environ_read_attempted",
    "real_path_read_attempted",
    "model_call_attempted",
    "credential_provisioning_attempted",
)

# Leak scanners (defensive; the collector should already redact).
_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_\-]{16,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|"
    r"glpat-[A-Za-z0-9_\-]{20,}|xai-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
_URL_RE = re.compile(r"https?://[A-Za-z0-9][A-Za-z0-9.\-]{1,}(?::\d+)?(?:/[^\s\"']*)?")
_PATH_RE = re.compile(
    r"(?:/home/[A-Za-z0-9_\-]+|/root/|C:\\\\Users\\\\[A-Za-z0-9_\-]+|"
    r"opencode\.env)"
)


# ----------------------------- helpers ---------------------------------


def _flatten_text(obj: Any) -> str:
    """Serialize a JSON-like object to a single scanning string."""
    try:
        return json.dumps(obj, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return repr(obj)


def _scan_leaks(payload: Any) -> dict:
    """Scan a payload for secret / URL / real-path leaks. Read-only."""
    text = _flatten_text(payload)
    result = {
        "secret_leak": bool(_SECRET_RE.search(text)),
        "url_leak": bool(_URL_RE.search(text)),
        "path_leak": bool(_PATH_RE.search(text)),
    }
    result["any_leak"] = any(result.values())
    return result


def _extract_inner_receipt(obj: Any) -> dict:
    """A collector emits {plan_id, attestation, receipt, ...}. If the caller
    passed the outer wrapper, unwrap the schema-compliant 'receipt' sub-dict.
    Otherwise assume the payload is already a receipt.
    """
    if not isinstance(obj, dict):
        return {}
    if "receipt" in obj and isinstance(obj["receipt"], dict) and "schema_version" in obj["receipt"]:
        return obj["receipt"]
    return obj


def _validate_one_receipt(lane: str, wrapper: Any) -> dict:
    """Validate a single receipt for schema, redaction, forbidden flags, and
    leaks. Returns per-lane result. NEVER echoes raw secret/URL/path values."""
    lane_result: dict = {
        "lane": lane,
        "receipt_present": False,
        "receipt_schema_valid": False,
        "collection_status": None,
        "redaction_all_true": False,
        "redaction_missing": [],
        "forbidden_flags_all_false": False,
        "forbidden_flags_true": [],
        "leak_scan": {"secret_leak": False, "url_leak": False, "path_leak": False, "any_leak": False},
        "errors": [],
    }
    if wrapper is None:
        lane_result["errors"].append("missing")
        return lane_result

    lane_result["receipt_present"] = True
    receipt = _extract_inner_receipt(wrapper)
    if not receipt:
        lane_result["errors"].append("receipt_not_dict")
        return lane_result

    # Schema validation via plan module (fail-closed).
    v = _plan.validate_receipt(receipt)
    lane_result["receipt_schema_valid"] = bool(v.get("valid"))
    if not v.get("valid"):
        lane_result["errors"].extend(list(v.get("errors", []))[:5])
        # continue evaluation — we still want redaction/leak signal

    lane_result["collection_status"] = receipt.get("collection_status")

    # Redaction check
    red = receipt.get("redaction_status") or {}
    missing = [k for k in REDACTION_SUBFLAGS if red.get(k) is not True]
    lane_result["redaction_all_true"] = not missing
    lane_result["redaction_missing"] = missing

    # Forbidden flags check
    flags = receipt.get("forbidden_operation_flags") or {}
    trues = [k for k in FORBIDDEN_FLAGS if flags.get(k) is True]
    lane_result["forbidden_flags_all_false"] = not trues
    lane_result["forbidden_flags_true"] = trues

    # Leak scan across the wrapper (redacted_output + attestation + receipt),
    # not raw values — we only report booleans, never the raw hit.
    leak = _scan_leaks(wrapper)
    lane_result["leak_scan"] = leak

    return lane_result


def _lane_verdict(r: dict) -> str:
    if r["leak_scan"]["any_leak"]:
        return "STOP_SECRET_RISK"
    if not r["receipt_present"]:
        return "E2E_BLOCKED"
    if not r["receipt_schema_valid"]:
        return "E2E_BLOCKED"
    if not r["redaction_all_true"]:
        return "E2E_BLOCKED"
    if not r["forbidden_flags_all_false"]:
        return "E2E_BLOCKED"
    return "E2E_PASS"


# ----------------------------- API ------------------------------------


def summarize_receipts(receipts: dict, include_prior_summary: bool = False) -> dict:
    """Aggregate 4 (or 5) canary receipts into a Layer-2 E2E verdict.

    Args:
        receipts: dict mapping lane name -> receipt wrapper (dict). Recognized
                  keys are CANONICAL_LANES; OPTIONAL_LANES may also be present.
        include_prior_summary: when True and receipts contains 'summary_prior',
                               the prior summary receipt is validated too.

    Returns:
        Aggregated summary dict with `final_verdict`.
    """
    per_lane: list[dict] = []
    lanes = list(CANONICAL_LANES)
    if include_prior_summary and "summary_prior" in receipts:
        lanes.append("summary_prior")

    schema_mismatch = False
    for lane in lanes:
        wrapper = receipts.get(lane)
        r = _validate_one_receipt(lane, wrapper)
        per_lane.append(r)
        # STOP_AND_REANCHOR trigger: receipt schema disagreement on a present
        # payload.
        if r["receipt_present"] and any(
            "schema_version" in e or "Invalid node" in e or "Invalid collection_status" in e
            for e in r.get("errors", [])
        ):
            schema_mismatch = True

    # Overall verdict
    if any(x["leak_scan"]["any_leak"] for x in per_lane):
        overall = "STOP_SECRET_RISK"
    elif schema_mismatch:
        overall = "STOP_AND_REANCHOR"
    elif all(_lane_verdict(x) == "E2E_PASS" for x in per_lane):
        overall = "E2E_PASS"
    else:
        overall = "E2E_BLOCKED"

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "source": "worker_attest_e2e_summary",
        "canonical_lanes": list(CANONICAL_LANES),
        "optional_lanes_included": [
            l for l in OPTIONAL_LANES if include_prior_summary and l in receipts
        ],
        "per_lane": per_lane,
        "layer2_e2e_verdict": overall,
        "final_verdict": overall,
        "summary_counts": {
            "lanes_total": len(per_lane),
            "lanes_pass": sum(1 for x in per_lane if _lane_verdict(x) == "E2E_PASS"),
            "lanes_blocked": sum(1 for x in per_lane if _lane_verdict(x) == "E2E_BLOCKED"),
            "lanes_secret_risk": sum(1 for x in per_lane if _lane_verdict(x) == "STOP_SECRET_RISK"),
        },
    }


def _load_receipts_from_dir(fixture_dir: Path) -> dict:
    """Load a lane->receipt map from a local directory. Read-only. Filenames
    must be exactly <lane>.json and must live under tests/fixtures/ subpath
    OR the caller's explicit --fixture-dir. No path expansion, no globs."""
    result: dict = {}
    if not fixture_dir.is_dir():
        return result
    for lane in list(CANONICAL_LANES) + list(OPTIONAL_LANES):
        f = fixture_dir / f"{lane}.json"
        if f.is_file():
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    result[lane] = json.load(fh)
            except (OSError, json.JSONDecodeError) as exc:
                result[lane] = {"_load_error": str(exc)}
    return result


def self_check() -> dict:
    """In-process self-check. Uses only dry-run/skipped collector paths — no
    SSH, no real read, no network."""
    try:
        from scripts import worker_attest_collector as _wac
    except ImportError:  # pragma: no cover
        import worker_attest_collector as _wac  # type: ignore

    checks: list[dict] = []

    def _ck(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    # 1. 4 lanes all pass in dry-run/skipped mode
    r21_dry = _wac.collect_21bao_local(_wac.build_collection_plan("21bao", dry_run=True))
    r21_real = _wac.collect_21bao_local(
        _wac.build_collection_plan("21bao", dry_run=False),
        operator_approved_real_read=False,
    )
    r5 = _wac.collect_5bao_remote(
        _wac.build_collection_plan("5bao", dry_run=False),
        operator_approved_real_read=False,
    )
    r9 = _wac.collect_9bao_remote(
        _wac.build_collection_plan("9bao", dry_run=False),
        operator_approved_real_read=False,
    )
    receipts = {
        "21bao_dry_run": r21_dry,
        "21bao_real_read": r21_real,
        "5bao_ssh_canary": r5,
        "9bao_ssh_canary": r9,
    }
    summary = summarize_receipts(receipts)
    _ck(
        "four_lane_dry_run_pass",
        summary["final_verdict"] == "E2E_PASS",
        f"verdict={summary['final_verdict']}",
    )
    _ck(
        "all_lanes_forbidden_flags_all_false",
        all(x["forbidden_flags_all_false"] for x in summary["per_lane"]),
    )
    _ck(
        "all_lanes_redaction_all_true",
        all(x["redaction_all_true"] for x in summary["per_lane"]),
    )
    _ck(
        "no_lane_reports_leak",
        not any(x["leak_scan"]["any_leak"] for x in summary["per_lane"]),
    )

    # 2. Missing lane → BLOCKED
    partial = {k: v for k, v in receipts.items() if k != "5bao_ssh_canary"}
    s2 = summarize_receipts(partial)
    _ck("missing_lane_blocked", s2["final_verdict"] == "E2E_BLOCKED",
        f"verdict={s2['final_verdict']}")

    # 3. Injected forbidden flag → BLOCKED (never touched original receipt)
    tampered = json.loads(json.dumps(receipts))
    tampered["9bao_ssh_canary"]["receipt"]["forbidden_operation_flags"]["ssh_attempted"] = True
    s3 = summarize_receipts(tampered)
    _ck("forbidden_flag_true_blocked", s3["final_verdict"] == "E2E_BLOCKED",
        f"verdict={s3['final_verdict']}")

    # 4. Injected leak (fake sk-) → STOP_SECRET_RISK
    tampered2 = json.loads(json.dumps(receipts))
    tampered2["21bao_dry_run"]["redacted_output"]["injected"] = "sk-abcdefghijklmnop1234567890"
    s4 = summarize_receipts(tampered2)
    _ck("secret_leak_stops", s4["final_verdict"] == "STOP_SECRET_RISK",
        f"verdict={s4['final_verdict']}")

    # 5. Injected redaction False → BLOCKED
    tampered3 = json.loads(json.dumps(receipts))
    tampered3["5bao_ssh_canary"]["receipt"]["redaction_status"]["no_secret_value"] = False
    s5 = summarize_receipts(tampered3)
    _ck("redaction_false_blocked", s5["final_verdict"] == "E2E_BLOCKED",
        f"verdict={s5['final_verdict']}")

    # 6. Schema mismatch → STOP_AND_REANCHOR
    tampered4 = json.loads(json.dumps(receipts))
    tampered4["21bao_real_read"]["receipt"]["schema_version"] = "9.9"
    s6 = summarize_receipts(tampered4)
    _ck(
        "schema_mismatch_reanchor",
        s6["final_verdict"] == "STOP_AND_REANCHOR",
        f"verdict={s6['final_verdict']}",
    )

    # 7. include_prior_summary path smoke: use an unrelated valid receipt
    priors = dict(receipts)
    priors["summary_prior"] = r21_dry
    s7 = summarize_receipts(priors, include_prior_summary=True)
    _ck(
        "include_prior_summary_pass",
        s7["final_verdict"] == "E2E_PASS"
        and "summary_prior" in s7["optional_lanes_included"],
        f"verdict={s7['final_verdict']}",
    )

    # 8. AST safety: no forbidden imports/calls in this module
    import ast as _ast
    src = Path(__file__).read_text(encoding="utf-8")
    tree = _ast.parse(src)
    forbidden_names = {"subprocess", "socket", "paramiko", "fabric", "requests", "urllib"}
    imports = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Import):
            for a in node.names:
                imports.add(a.name.split(".")[0])
        elif isinstance(node, _ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    hit = forbidden_names & imports
    _ck("no_forbidden_imports", not hit, f"hit={sorted(hit)}")

    passed = sum(1 for c in checks if c["passed"])
    total = len(checks)
    return {
        "status": "PASS" if passed == total else "FAIL",
        "detail": f"{passed}/{total} passed",
        "checks": checks,
        "version": SUMMARY_SCHEMA_VERSION,
    }


# ----------------------------- CLI ------------------------------------


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _cmd_self_check(_args: argparse.Namespace) -> int:
    res = self_check()
    _print_json(res)
    return 0 if res["status"] == "PASS" else 1


def _cmd_summarize(args: argparse.Namespace) -> int:
    """Summarize receipts. Two modes:
    1. --fixture-dir PATH : load <lane>.json files from a local dir.
    2. In-process only (no CLI input for real receipts) — CLI always dry-run.
    """
    if args.fixture_dir:
        fd = Path(args.fixture_dir).resolve()
        # Fail-closed on paths outside CWD tree — no absolute reads outside
        cwd = Path.cwd().resolve()
        try:
            fd.relative_to(cwd)
        except ValueError:
            _print_json({
                "final_verdict": "E2E_BLOCKED",
                "error": "fixture-dir must be under current repo tree",
            })
            return 1
        receipts = _load_receipts_from_dir(fd)
    else:
        # Default: run 4 lanes in dry-run/skipped mode (no SSH, no real access).
        try:
            from scripts import worker_attest_collector as _wac
        except ImportError:  # pragma: no cover
            import worker_attest_collector as _wac  # type: ignore
        receipts = {
            "21bao_dry_run": _wac.collect_21bao_local(
                _wac.build_collection_plan("21bao", dry_run=True)
            ),
            "21bao_real_read": _wac.collect_21bao_local(
                _wac.build_collection_plan("21bao", dry_run=False),
                operator_approved_real_read=False,
            ),
            "5bao_ssh_canary": _wac.collect_5bao_remote(
                _wac.build_collection_plan("5bao", dry_run=False),
                operator_approved_real_read=False,
            ),
            "9bao_ssh_canary": _wac.collect_9bao_remote(
                _wac.build_collection_plan("9bao", dry_run=False),
                operator_approved_real_read=False,
            ),
        }
    summary = summarize_receipts(receipts, include_prior_summary=args.include_prior)
    _print_json(summary)
    return 0 if summary["final_verdict"] == "E2E_PASS" else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="worker_attest_e2e_summary",
        description="Baseline02 Phase 3 G-5-RECEIPT-E2E worker_attest summarizer",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sc = sub.add_parser("self-check", help="Run in-process self-check (no SSH, no real read)")
    sc.set_defaults(func=_cmd_self_check)

    sm = sub.add_parser("summarize", help="Summarize 4-lane (or 5-lane) receipts")
    sm.add_argument(
        "--fixture-dir",
        default=None,
        help="Load <lane>.json files from a local fixture directory (under repo root only)",
    )
    sm.add_argument(
        "--include-prior",
        action="store_true",
        help="Include summary_prior.json as a 5th optional lane if present",
    )
    sm.set_defaults(func=_cmd_summarize)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
