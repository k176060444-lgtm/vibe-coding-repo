#!/usr/bin/env python3
"""
Baseline02 D-A / D-B Policy-Lock Validator (Phase 3, read-only).

Freezes the current operator D-A/D-B stance as a machine-checkable policy:

  D-A (canonical vs runtime provider layering)
    Locked stance: the 9 currently-active models
    (lifecycle_status in {enabled_assigned, operator_requested}) are folded so
    that canonical_provider == provider_namespace == runtime_provider == "opencode-go".
    No new provider namespace is introduced by this lock.

  D-B (per-node model assignment / DEU promotion)
    Locked stance: the 16 declared_enabled_unassigned (DEU) models must stay
    DEU. They must NOT be silently promoted to enabled_assigned or
    operator_requested. Promotion requires an explicit operator decision
    outside this validator's scope.

  Node alias policy
    Locked stance: the canonical node ids per SOUL.md §1 are
    {"21bao", "5bao", "9bao"}. The legacy alias "win" is tolerated in
    `allowed_nodes` today but MUST resolve to "21bao"; this validator emits
    a normalization plan and reports (but does NOT rewrite) any "win" refs.

Guarantees (audit-safe):
  * Pure function. No side effects.
  * No SSH, no subprocess, no os.environ / os.getenv access.
  * No network, no model call, no credential provisioning, no node sync.
  * Does NOT modify model_pool.yaml, node_model_capability.yaml, or any config.
  * Reads only non-secret metadata:
      id, primary_alias, canonical_provider, provider_namespace,
      allowed_nodes, enabled, lifecycle_status, credential_status,
      endpoint_ref (as field NAME, never the value).
  * Never outputs secret values, env values, base_url values, endpoint URLs,
    key lengths, or real paths.

Verdicts:
  DA_DB_POLICY_LOCK_PASS      — pool matches locked stance
  DA_DB_POLICY_LOCK_BLOCKED   — pool violates locked stance (drift)
  STOP_SECRET_RISK            — leak scan hit a plausibly-real secret / URL /
                                real-path in the payload we intended to emit
  STOP_AND_REANCHOR           — pool schema disagreement (unexpected shape)

This is a lock, not an enforcer of transitions: it flags any deviation from
the frozen stance so operator can either (a) confirm the stance still holds
or (b) explicitly authorize a D-A/D-B change through the appropriate PR.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

# ── Locked constants (change only through an explicit operator D-A/D-B PR) ──

SCHEMA_VERSION = "1.0"

# Canonical node ids per SOUL.md §1.
CANONICAL_NODES = ("21bao", "5bao", "9bao")

# Legacy alias tolerated today; MUST resolve to canonical.
LEGACY_NODE_ALIASES = {"win": "21bao"}

# Lifecycle statuses considered "active" (model_call-eligible).
ACTIVE_LIFECYCLE_STATUSES = ("enabled_assigned", "operator_requested")

# Frozen D-A stance: the runtime_provider that active models must fold to.
ACTIVE_RUNTIME_PROVIDER = "opencode-go"

# Frozen D-A stance: active models must have canonical_provider ==
# provider_namespace == ACTIVE_RUNTIME_PROVIDER.
ACTIVE_CANONICAL_PROVIDER = "opencode-go"
ACTIVE_PROVIDER_NAMESPACE = "opencode-go"

# D-B lock: DEU count expected at the freeze point. Deviation triggers a drift
# report but does NOT auto-promote; operator must reconcile via a D-B PR.
EXPECTED_DEU_COUNT = 16
EXPECTED_ACTIVE_COUNT = 9  # 8 enabled_assigned + 1 operator_requested


# ── Leak scanners (defensive — the pool should never contain these). ────────

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


def _scan_leaks(payload: Any) -> dict:
    """Scan a JSON-serializable payload for secret / URL / real-path leaks."""
    try:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        text = repr(payload)
    return {
        "secret_leak": bool(_SECRET_RE.search(text)),
        "url_leak": bool(_URL_RE.search(text)),
        "path_leak": bool(_PATH_RE.search(text)),
        "any_leak": bool(
            _SECRET_RE.search(text) or _URL_RE.search(text) or _PATH_RE.search(text)
        ),
    }


# ── Helpers ────────────────────────────────────────────────────────────────


def _script_dir() -> Path:
    return Path(__file__).parent.resolve()


def _load_pool(pool_path: Path | None = None) -> dict:
    p = pool_path or (_script_dir() / "model_pool.yaml")
    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"model_pool at {p} is not a dict")
    return data


def _iter_models(pool: dict) -> list[dict]:
    ms = pool.get("models") or []
    if not isinstance(ms, list):
        raise ValueError("model_pool.models is not a list")
    return ms


def _safe_summary(model: dict) -> dict:
    """Return only non-secret fields for reports."""
    return {
        "id": model.get("id"),
        "primary_alias": model.get("primary_alias"),
        "canonical_provider": model.get("canonical_provider"),
        "provider_namespace": model.get("provider_namespace"),
        "lifecycle_status": model.get("lifecycle_status"),
        "enabled": bool(model.get("enabled", False)),
        "allowed_nodes": list(model.get("allowed_nodes") or []),
        "credential_status": model.get("credential_status"),
        "endpoint_ref": model.get("endpoint_ref"),
    }


# ── Core policy checks ────────────────────────────────────────────────────


def check_da_active_folding(models: list[dict]) -> dict:
    """D-A lock: active models fold to ACTIVE_RUNTIME_PROVIDER."""
    active = [
        m for m in models
        if m.get("lifecycle_status") in ACTIVE_LIFECYCLE_STATUSES
    ]
    violations = []
    for m in active:
        cp = m.get("canonical_provider")
        pn = m.get("provider_namespace")
        if cp != ACTIVE_CANONICAL_PROVIDER or pn != ACTIVE_PROVIDER_NAMESPACE:
            violations.append({
                "model": _safe_summary(m),
                "reason": (
                    f"active model must have canonical_provider="
                    f"{ACTIVE_CANONICAL_PROVIDER!r} and provider_namespace="
                    f"{ACTIVE_PROVIDER_NAMESPACE!r}; got canonical={cp!r}, "
                    f"namespace={pn!r}"
                ),
            })
    return {
        "check": "da_active_folding",
        "active_count": len(active),
        "expected_active_count": EXPECTED_ACTIVE_COUNT,
        "count_matches_expected": len(active) == EXPECTED_ACTIVE_COUNT,
        "violations": violations,
        "passed": (
            len(violations) == 0
            and len(active) == EXPECTED_ACTIVE_COUNT
        ),
    }


def check_db_deu_lock(models: list[dict]) -> dict:
    """D-B lock: DEU count matches expected and every DEU has empty allowed_nodes."""
    deu = [
        m for m in models
        if m.get("lifecycle_status") == "declared_enabled_unassigned"
    ]
    violations = []
    for m in deu:
        allowed = list(m.get("allowed_nodes") or [])
        enabled = bool(m.get("enabled", False))
        if not enabled:
            violations.append({
                "model": _safe_summary(m),
                "reason": "DEU model must have enabled=True",
            })
        if allowed:
            violations.append({
                "model": _safe_summary(m),
                "reason": (
                    "DEU model must have allowed_nodes=[]; got "
                    f"{allowed!r} — silent promotion detected"
                ),
            })
    return {
        "check": "db_deu_lock",
        "deu_count": len(deu),
        "expected_deu_count": EXPECTED_DEU_COUNT,
        "count_matches_expected": len(deu) == EXPECTED_DEU_COUNT,
        "violations": violations,
        "passed": (
            len(violations) == 0
            and len(deu) == EXPECTED_DEU_COUNT
        ),
    }


def check_readiness_not_advanced(models: list[dict]) -> dict:
    """DEU must not carry operator_approved / model_call_verified markers.

    The pool schema does not carry these flags per-model (they live in NMC
    matrix), but if a future edit tacked such fields onto a DEU model entry
    itself, that would signal silent promotion.
    """
    forbidden_pool_fields = ("operator_approved", "model_call_verified", "readiness")
    violations = []
    for m in models:
        if m.get("lifecycle_status") != "declared_enabled_unassigned":
            continue
        hits = [f for f in forbidden_pool_fields if f in m]
        if hits:
            violations.append({
                "model": _safe_summary(m),
                "reason": (
                    "DEU model has pool-level readiness fields "
                    f"{hits}; those must live in NMC matrix, never in pool"
                ),
            })
    return {
        "check": "readiness_not_advanced",
        "violations": violations,
        "passed": len(violations) == 0,
    }


def check_node_alias_normalization(models: list[dict]) -> dict:
    """Report `win` legacy alias usage in allowed_nodes and propose plan.

    Non-blocking: legacy `win` is tolerated today and normalized by the
    resolver / drift layer, but we surface it so operator can schedule a
    normalization PR.
    """
    win_refs = []
    invalid_refs = []
    known = set(CANONICAL_NODES) | set(LEGACY_NODE_ALIASES.keys())
    for m in models:
        allowed = list(m.get("allowed_nodes") or [])
        for n in allowed:
            if n in LEGACY_NODE_ALIASES:
                win_refs.append({
                    "model": _safe_summary(m),
                    "legacy_ref": n,
                    "canonical_target": LEGACY_NODE_ALIASES[n],
                })
            elif n not in known:
                invalid_refs.append({
                    "model": _safe_summary(m),
                    "invalid_ref": n,
                })
    plan = [
        {
            "step": "Do NOT rewrite pool automatically",
            "detail": (
                "Any allowed_nodes rewrite is a D-B data change and needs its "
                "own operator-approved PR."
            ),
        },
        {
            "step": "Continue relying on LEGACY_NODE_ALIASES for compat",
            "detail": (
                "scripts/model_pool_drift.py and scripts/model_pool_manager.py "
                "already normalize 'win' → '21bao' at read time; the resolver "
                "restricts input to canonical nodes."
            ),
        },
        {
            "step": "When operator authorizes normalization",
            "detail": (
                "Emit a data-only PR that replaces 'win' with '21bao' in "
                "allowed_nodes for the affected models; keep alias map for "
                "one release cycle for defence-in-depth."
            ),
        },
    ]
    return {
        "check": "node_alias_normalization",
        "legacy_win_refs": win_refs,
        "invalid_node_refs": invalid_refs,
        "normalization_plan": plan,
        # legacy 'win' is not a policy violation today; invalid refs ARE.
        "passed": len(invalid_refs) == 0,
    }


def check_no_new_namespace(models: list[dict]) -> dict:
    """Freeze the set of provider_namespace values present in the pool.

    We record the frozen set at lock time; a NEW namespace value appearing
    in the pool without an operator D-A PR would violate the lock.
    """
    frozen_set = {
        # Active D-A folding target
        "opencode-go",
        # DEU canonical namespaces (16 DEU cluster around these)
        "anthropic", "dashscope", "deepseek", "google", "moonshot",
        "openai", "xai",
        # Non-active buckets present in pool at freeze time
        "opencode", "xiaomi", "minimax", "volcengine",
        "deepseek-plan", "minimax-plan",
    }
    observed = set()
    unknown = []
    for m in models:
        pn = m.get("provider_namespace")
        if pn is None:
            continue
        observed.add(pn)
        if pn not in frozen_set:
            unknown.append({
                "model": _safe_summary(m),
                "unknown_namespace": pn,
            })
    return {
        "check": "no_new_namespace",
        "frozen_set": sorted(frozen_set),
        "observed": sorted(observed),
        "unknown_namespaces": unknown,
        "passed": len(unknown) == 0,
    }


# ── Top-level API ─────────────────────────────────────────────────────────


def validate_policy_lock(pool: dict | None = None) -> dict:
    """Run all D-A/D-B policy-lock checks and produce a signed report."""
    try:
        if pool is None:
            pool = _load_pool()
    except (OSError, ValueError, yaml.YAMLError) as e:
        return {
            "schema_version": SCHEMA_VERSION,
            "final_verdict": "STOP_AND_REANCHOR",
            "error": f"pool load failed: {type(e).__name__}",
            "checks": [],
        }

    models = _iter_models(pool)

    checks = [
        check_da_active_folding(models),
        check_db_deu_lock(models),
        check_readiness_not_advanced(models),
        check_node_alias_normalization(models),
        check_no_new_namespace(models),
    ]

    # Schema sanity: unexpected top-level shape triggers STOP_AND_REANCHOR
    if pool.get("schema_version") not in (None, "1.0", "1.1", "1.2"):
        report = {
            "schema_version": SCHEMA_VERSION,
            "final_verdict": "STOP_AND_REANCHOR",
            "error": (
                "unexpected model_pool schema_version "
                f"{pool.get('schema_version')!r}"
            ),
            "checks": checks,
        }
    else:
        all_passed = all(c["passed"] for c in checks)
        report = {
            "schema_version": SCHEMA_VERSION,
            "pool_schema_version": pool.get("schema_version"),
            "final_verdict": (
                "DA_DB_POLICY_LOCK_PASS" if all_passed else "DA_DB_POLICY_LOCK_BLOCKED"
            ),
            "checks": checks,
            "counts": {
                "total_models": len(models),
                "active": sum(
                    1 for m in models
                    if m.get("lifecycle_status") in ACTIVE_LIFECYCLE_STATUSES
                ),
                "deu": sum(
                    1 for m in models
                    if m.get("lifecycle_status") == "declared_enabled_unassigned"
                ),
            },
        }

    leak = _scan_leaks(report)
    report["leak_scan"] = leak
    if leak["any_leak"]:
        report["final_verdict"] = "STOP_SECRET_RISK"

    return report


# ── Self-check ────────────────────────────────────────────────────────────


def self_check() -> dict:
    """In-process checks; no side effects."""
    checks = []

    def _ck(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(ok), "detail": detail})

    # 1. Real pool passes at freeze point
    real = validate_policy_lock()
    _ck(
        "real_pool_passes_lock",
        real["final_verdict"] == "DA_DB_POLICY_LOCK_PASS",
        f"verdict={real['final_verdict']}",
    )

    # 2. Silent DEU promotion is detected
    fake_pool = {
        "schema_version": "1.2",
        "models": [
            {
                "id": "test-deu-silent-promote",
                "primary_alias": "x",
                "canonical_provider": "openai",
                "provider_namespace": "openai",
                "lifecycle_status": "declared_enabled_unassigned",
                "enabled": True,
                # Silent promotion: allowed_nodes non-empty on DEU
                "allowed_nodes": ["21bao"],
                "credential_status": "present",
                "endpoint_ref": "base_url_env",
            },
        ],
    }
    r = validate_policy_lock(fake_pool)
    _ck(
        "silent_deu_promotion_blocked",
        r["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED",
        f"verdict={r['final_verdict']}",
    )

    # 3. Active without opencode-go canonical is blocked
    fake_pool2 = {
        "schema_version": "1.2",
        "models": [
            {
                "id": "test-active-wrong-canonical",
                "primary_alias": "y",
                "canonical_provider": "openai",  # wrong: not opencode-go
                "provider_namespace": "openai",
                "lifecycle_status": "enabled_assigned",
                "enabled": True,
                "allowed_nodes": ["21bao"],
                "credential_status": "present",
                "endpoint_ref": "base_url_env",
            },
        ],
    }
    r2 = validate_policy_lock(fake_pool2)
    _ck(
        "active_wrong_canonical_blocked",
        r2["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED",
        f"verdict={r2['final_verdict']}",
    )

    # 4. Unknown provider_namespace is blocked
    fake_pool3 = {
        "schema_version": "1.2",
        "models": [
            {
                "id": "test-unknown-namespace",
                "primary_alias": "z",
                "canonical_provider": "opencode-go",
                "provider_namespace": "brand-new-plan",  # not in frozen_set
                "lifecycle_status": "candidate",
                "enabled": False,
                "allowed_nodes": [],
                "credential_status": "absent",
                "endpoint_ref": "base_url_env",
            },
        ],
    }
    r3 = validate_policy_lock(fake_pool3)
    _ck(
        "unknown_namespace_blocked",
        r3["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED",
        f"verdict={r3['final_verdict']}",
    )

    # 5. Schema mismatch triggers STOP_AND_REANCHOR
    fake_pool4 = {"schema_version": "9.9", "models": []}
    r4 = validate_policy_lock(fake_pool4)
    _ck(
        "schema_mismatch_reanchor",
        r4["final_verdict"] == "STOP_AND_REANCHOR",
        f"verdict={r4['final_verdict']}",
    )

    # 6. Leak in report triggers STOP_SECRET_RISK (inject via fake data)
    # We construct a report-like dict manually; the module itself never emits
    # such content, but the guard must fire if a future edit ever did.
    fake_report = {"marker": "sk-" + "A" * 40}
    leak = _scan_leaks(fake_report)
    _ck(
        "leak_scan_catches_real_secret",
        leak["any_leak"] is True and leak["secret_leak"] is True,
        f"leak={leak}",
    )

    # 7. Node alias policy reports legacy 'win' but does not block on it alone
    fake_pool5 = {
        "schema_version": "1.2",
        "models": [
            {
                "id": "opencode-go-fake-active",
                "primary_alias": "a",
                "canonical_provider": "opencode-go",
                "provider_namespace": "opencode-go",
                "lifecycle_status": "enabled_assigned",
                "enabled": True,
                "allowed_nodes": ["5bao", "9bao", "win"],
                "credential_status": "present",
                "endpoint_ref": "base_url_env",
            },
        ],
    }
    r5 = validate_policy_lock(fake_pool5)
    alias_check = [c for c in r5["checks"] if c["check"] == "node_alias_normalization"][0]
    _ck(
        "legacy_win_reported_not_blocking",
        len(alias_check["legacy_win_refs"]) == 1 and alias_check["passed"] is True,
        f"win_refs={len(alias_check['legacy_win_refs'])}",
    )

    # 8. Invalid (non-legacy, non-canonical) node ref IS blocking
    fake_pool6 = {
        "schema_version": "1.2",
        "models": [
            {
                "id": "opencode-go-fake-active",
                "primary_alias": "a",
                "canonical_provider": "opencode-go",
                "provider_namespace": "opencode-go",
                "lifecycle_status": "enabled_assigned",
                "enabled": True,
                "allowed_nodes": ["mars"],
                "credential_status": "present",
                "endpoint_ref": "base_url_env",
            },
        ],
    }
    r6 = validate_policy_lock(fake_pool6)
    _ck(
        "invalid_node_ref_blocked",
        r6["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED",
        f"verdict={r6['final_verdict']}",
    )

    # 9. Pool-level readiness field on DEU is blocked
    fake_pool7 = {
        "schema_version": "1.2",
        "models": [
            {
                "id": "test-deu-with-readiness",
                "primary_alias": "r",
                "canonical_provider": "openai",
                "provider_namespace": "openai",
                "lifecycle_status": "declared_enabled_unassigned",
                "enabled": True,
                "allowed_nodes": [],
                "credential_status": "present",
                "endpoint_ref": "base_url_env",
                # Forbidden pool-level marker
                "operator_approved": True,
            },
        ],
    }
    r7 = validate_policy_lock(fake_pool7)
    _ck(
        "pool_level_readiness_blocked",
        r7["final_verdict"] == "DA_DB_POLICY_LOCK_BLOCKED",
        f"verdict={r7['final_verdict']}",
    )

    passed_ct = sum(1 for c in checks if c["passed"])
    total = len(checks)
    return {
        "status": "PASS" if passed_ct == total else "FAIL",
        "detail": f"{passed_ct}/{total} passed",
        "checks": checks,
    }


# ── CLI ────────────────────────────────────────────────────────────────────


def _print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Baseline02 D-A / D-B Policy-Lock Validator (read-only)"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("self-check", help="run in-process self-check")
    val = sub.add_parser("validate", help="validate the current model_pool.yaml")
    val.add_argument(
        "--pool",
        type=str,
        default=None,
        help="Optional alternate model_pool.yaml path (must be under repo tree)",
    )
    args = parser.parse_args(argv)

    if args.cmd == "self-check":
        r = self_check()
        _print_json(r)
        return 0 if r["status"] == "PASS" else 1

    if args.cmd == "validate":
        pool = None
        if args.pool:
            p = Path(args.pool).resolve()
            repo = Path.cwd().resolve()
            try:
                p.relative_to(repo)
            except ValueError:
                _print_json({
                    "final_verdict": "DA_DB_POLICY_LOCK_BLOCKED",
                    "error": "pool path must be under current repo tree",
                })
                return 1
            pool = _load_pool(p)
        r = validate_policy_lock(pool)
        _print_json(r)
        return 0 if r["final_verdict"] == "DA_DB_POLICY_LOCK_PASS" else 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
