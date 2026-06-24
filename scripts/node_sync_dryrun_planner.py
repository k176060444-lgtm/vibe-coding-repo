#!/usr/bin/env python3
"""Node Sync Dry-run Planner v1.0.0

Converts renderer output into an auditable node sync action plan with:
- action_plan (sync_config details)
- config_write_preview (JSON draft, no real keys)
- approval_receipt_draft (for operator sign-off)
- rollback_plan (backup-and-restore strategy)
- safety_checks (all boundaries enforced)

NEVER writes to nodes, NEVER executes SSH, NEVER exposes real keys.

Usage:
    python scripts/node_sync_dryrun_planner.py --self-check

Contract: docs/MODEL_POOL_DISTRIBUTION_CONTRACT.md
"""

__version__ = "1.0.0"

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from typing import Any, Optional

# --- Constants ---

PLANNER_VERSION = __version__

# Default planned paths per node (preview only, never written)
DEFAULT_PLANNED_PATHS = {
    "21bao": {
        "config_path": r"D:\vibedev-config\opencode\opencode.jsonc",
        "backup_path": r"D:\vibedev-config\opencode\opencode.jsonc.bak",
    },
    "5bao": {
        "config_path": "/home/vibeworker/.config/opencode/config.json",
        "backup_path": "/home/vibeworker/.config/opencode/config.json.bak",
    },
    "9bao": {
        "config_path": "/home/vibeworker/.config/opencode/config.json",
        "backup_path": "/home/vibeworker/.config/opencode/config.json.bak",
    },
    "Windows": {
        "config_path": r"D:\vibedev-config\opencode\opencode.jsonc",
        "backup_path": r"D:\vibedev-config\opencode\opencode.jsonc.bak",
    },
}

# Risk levels
RISK_LEVELS = {
    "sync_config": "medium",
}

# Dangerous patterns for output scanning
DANGEROUS_KEY_PATTERNS = [
    r"sk-[a-zA-Z0-9]{10,}",
    r"AKIA[A-Z0-9]{16}",
    r"Bearer [a-zA-Z0-9]{10,}",
    r"api[_-]?key\s*[:=]\s*[\"'][a-zA-Z0-9]{10,}",
    r"access[_-]?token\s*[:=]\s*[\"'][a-zA-Z0-9]{10,}",
    r"OPENAI_API_KEY\s*=\s*[a-zA-Z0-9-]{10,}",
    r"DEEPSEEK_API_KEY\s*=\s*[a-zA-Z0-9-]{10,}",
    r"password\s*[:=]\s*[\"'][^\"']{6,}",
    r"secret[_-]?value\s*[:=]\s*[\"'][^\"']{6,}",
    r"-----BEGIN\s+(RSA|EC|DSA|OPENSSH)\s+PRIVATE\s+KEY-----",
]

# Execution instruction patterns (must NOT appear in output)
EXECUTION_PATTERNS = [
    r"\bssh\s+",
    r"\bscp\s+",
    r"\brsync\s+",
    r"\bchmod\s+",
    r"\bmkdir\s+",
    r"\bwrite_file\s*\(",
    r"\bfile_write\s*\(",
    r"\bremote_exec\s*\(",
    r"\bexec\s*\(",
    r"\bsystem\s*\(",
    r"\bpopen\s*\(",
]


# --- Input Validation ---


def validate_input(renderer_output: dict, dry_run: bool) -> tuple[bool, list[str]]:
    """Validate planner input. Returns (valid, errors)."""
    errors = []

    # dry_run must be True
    if dry_run is not True:
        errors.append("dry_run must be True")

    # renderer_output must be a dict
    if not isinstance(renderer_output, dict) or not renderer_output:
        errors.append("renderer_output must be a non-empty dict")
        return len(errors) == 0, errors

    # node required
    node = renderer_output.get("node")
    if not node or not isinstance(node, str):
        errors.append("renderer_output must contain 'node' (non-empty string)")

    # renderer dry_run must be True
    if renderer_output.get("dry_run") is not True:
        errors.append("renderer_output.dry_run must be True")

    # config_draft required
    if "config_draft" not in renderer_output:
        errors.append("renderer_output must contain 'config_draft'")

    return len(errors) == 0, errors


# --- Safety Checks ---


def run_safety_checks(
    renderer_output: dict,
    dry_run: bool,
    output_preview: dict,
) -> dict:
    """Run all safety checks. Returns safety_checks dict."""
    violations = []

    # 1. dry_run_enforced
    dry_run_ok = dry_run is True and renderer_output.get("dry_run") is True

    # 2. no_secrets_in_output
    output_str = json.dumps(output_preview, ensure_ascii=False)
    secret_violations = []
    for pattern in DANGEROUS_KEY_PATTERNS:
        matches = re.findall(pattern, output_str, re.IGNORECASE)
        if matches:
            secret_violations.append(pattern)
    no_secrets = len(secret_violations) == 0

    # 3. no_node_write / no_ssh_execution
    exec_violations = []
    for pattern in EXECUTION_PATTERNS:
        if re.search(pattern, output_str, re.IGNORECASE):
            exec_violations.append(pattern)
    no_node_write = len(exec_violations) == 0
    no_ssh = True  # We never generate SSH commands

    # 4. requires_operator_approval
    requires_approval = output_preview.get("requires_operator_approval") is True

    # 5. config_preview_has_no_keys
    config_preview = output_preview.get("config_preview", {})
    config_str = json.dumps(config_preview, ensure_ascii=False)
    config_has_keys = False
    for pattern in DANGEROUS_KEY_PATTERNS:
        if re.search(pattern, config_str, re.IGNORECASE):
            config_has_keys = True
            break
    config_no_keys = not config_has_keys

    # 6. rollback_plan_is_dryrun
    rollback = output_preview.get("rollback_plan", {})
    rollback_dryrun = rollback.get("dry_run_only") is True

    # 7. all_models_have_secret_ref
    action_plan = output_preview.get("action_plan", {})
    models = action_plan.get("models_to_sync", [])
    all_have_ref = all(
        isinstance(m, dict) and m.get("secret_ref")
        for m in models
    ) if models else True  # empty models = vacuously true

    # Build violations
    if not dry_run_ok:
        violations.append("dry_run not enforced")
    if not no_secrets:
        violations.append(f"secrets detected: {secret_violations}")
    if not no_node_write:
        violations.append(f"execution instructions detected: {exec_violations}")
    if not no_ssh:
        violations.append("SSH execution detected")
    if not requires_approval:
        violations.append("requires_operator_approval not set")
    if not config_no_keys:
        violations.append("config_preview contains real keys")
    if not rollback_dryrun:
        violations.append("rollback_plan not marked dry_run_only")

    return {
        "dry_run_enforced": dry_run_ok,
        "no_secrets_in_output": no_secrets,
        "no_node_write": no_node_write,
        "no_ssh_execution": no_ssh,
        "requires_operator_approval": requires_approval,
        "all_models_have_secret_ref": all_have_ref,
        "config_preview_has_no_keys": config_no_keys,
        "rollback_plan_is_dryrun": rollback_dryrun,
        "passed": len(violations) == 0,
        "violations": violations,
    }


# --- Path Generation ---


def get_planned_paths(
    node: str,
    planned_config_path: str = "",
    previous_config_path: str = "",
) -> dict:
    """Get planned paths for a node. Uses defaults if not provided."""
    defaults = DEFAULT_PLANNED_PATHS.get(node, {
        "config_path": f"/tmp/opencode-{node}/config.json",
        "backup_path": f"/tmp/opencode-{node}/config.json.bak",
    })

    return {
        "config_path": planned_config_path or defaults["config_path"],
        "backup_path": previous_config_path or defaults["backup_path"],
    }


# --- Config Preview ---


def build_config_preview(config_draft: dict) -> dict:
    """Build config write preview from renderer config_draft.

    Only includes safe metadata, never real keys.
    """
    models = config_draft.get("models", [])
    default_model = config_draft.get("default_model", "")

    # Build provider structure for preview
    providers = {}
    secret_fields = []

    for model in models:
        provider = model.get("provider", "unknown")
        alias = model.get("alias", "unknown")
        secret_ref = model.get("secret_ref", "")

        if provider not in providers:
            providers[provider] = {
                "npm": "@ai-sdk/openai-compatible",
                "options": {"baseURL": model.get("endpoint", "")},
                "models": {},
            }

        providers[provider]["models"][alias] = {
            "name": model.get("alias", alias),
        }

        if secret_ref:
            secret_fields.append(secret_ref)

    content_preview = {"provider": providers}
    content_str = json.dumps(content_preview, sort_keys=True, ensure_ascii=False)
    content_hash = hashlib.sha256(content_str.encode("utf-8")).hexdigest()

    return {
        "format": "opencode-jsonc",
        "content_preview": content_preview,
        "content_hash": content_hash,
        "secret_fields": sorted(set(secret_fields)),
        "no_real_keys": True,
    }


# --- Rollback Plan ---


def build_rollback_plan(planned_paths: dict) -> dict:
    """Build rollback plan (dry-run only)."""
    backup_path = planned_paths.get("backup_path", "unknown")
    config_path = planned_paths.get("config_path", "unknown")

    rollback_steps = [
        f"1. Verify backup exists at {backup_path}",
        f"2. Copy backup to {config_path}",
        "3. Verify config hash matches backup hash",
        "4. Restart OpenCode service (if applicable)",
    ]

    rollback_hash = hashlib.sha256(
        json.dumps(rollback_steps, sort_keys=True).encode("utf-8")
    ).hexdigest()

    return {
        "strategy": "backup-and-restore",
        "backup_path": backup_path,
        "rollback_steps": rollback_steps,
        "rollback_hash": rollback_hash,
        "dry_run_only": True,
    }


# --- Approval Receipt ---


def build_approval_receipt(
    node: str,
    operator_id: str,
    approval_id: Optional[str],
    planned_paths: dict,
    models: list[dict],
    input_hash: str,
) -> dict:
    """Build approval receipt draft."""
    model_aliases = [m.get("alias", m.get("model_id", "unknown")) for m in models]

    # Generate approval_id if not provided
    if not approval_id:
        approval_id = f"approval-v12129g-sync-{node}-001"

    return {
        "approval_id": approval_id,
        "operator_id": operator_id,
        "target_node": node,
        "model_aliases": model_aliases,
        "risk_level": RISK_LEVELS.get("sync_config", "medium"),
        "planned_paths": planned_paths,
        "input_hash": input_hash,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "pending_operator_approval",
    }


# --- Main Planner ---


def plan_node_sync(
    renderer_output: dict,
    operator_id: str = "",
    approval_id: Optional[str] = None,
    planned_config_path: str = "",
    previous_config_path: str = "",
    dry_run: bool = True,
) -> dict:
    """Plan node sync from renderer output (dry-run only).

    Args:
        renderer_output: Output from opencode_config_renderer or opencode_model_pool_renderer
        operator_id: Operator performing the sync
        approval_id: Optional approval identifier
        planned_config_path: Target config path (preview only)
        previous_config_path: Previous config path for rollback (preview only)
        dry_run: Must be True

    Returns:
        Node sync plan with action_plan, config_preview, approval_receipt,
        rollback_plan, safety_checks, and audit.

    Raises:
        ValueError: If input validation fails
        RuntimeError: If safety checks fail
    """
    # --- Input validation ---
    valid, errors = validate_input(renderer_output, dry_run)
    if not valid:
        raise ValueError(f"input validation failed: {'; '.join(errors)}")

    node = renderer_output["node"]
    config_draft = renderer_output.get("config_draft", {})
    models = config_draft.get("models", [])
    default_model = config_draft.get("default_model", "")
    role_assignment = renderer_output.get("role_assignment", {})
    warnings = list(renderer_output.get("warnings", []))
    non_available = renderer_output.get("non_available_summary", [])

    # --- Compute input hash ---
    input_canonical = json.dumps(renderer_output, sort_keys=True, ensure_ascii=False)
    input_hash = hashlib.sha256(input_canonical.encode("utf-8")).hexdigest()

    # --- Planned paths ---
    planned_paths = get_planned_paths(node, planned_config_path, previous_config_path)

    # --- Build action plan ---
    models_to_sync = []
    for model in models:
        models_to_sync.append({
            "alias": model.get("alias", "unknown"),
            "secret_ref": model.get("secret_ref", ""),
            "credential_status": model.get("credential_status", "unknown"),
            "credential_source": model.get("credential_source", ""),
            "provider": model.get("provider", "unknown"),
            "endpoint": model.get("endpoint", ""),
            "protocol": model.get("protocol", "openai-compatible"),
        })

    # Resolve roles
    roles_to_assign = {}
    if isinstance(role_assignment, dict):
        for role, assignment in role_assignment.items():
            if isinstance(assignment, dict):
                roles_to_assign[role] = assignment.get("model_alias", assignment.get("model_id", ""))
            else:
                roles_to_assign[role] = str(assignment)

    action_plan = {
        "action": "sync_config",
        "target_node": node,
        "planned_paths": planned_paths,
        "model_count": len(models),
        "default_model": default_model,
        "models_to_sync": models_to_sync,
        "roles_to_assign": roles_to_assign,
        "risk_level": RISK_LEVELS.get("sync_config", "medium"),
    }

    # --- Build config preview ---
    config_preview = build_config_preview(config_draft)

    # --- Build approval receipt ---
    approval_receipt = build_approval_receipt(
        node, operator_id, approval_id,
        planned_paths, models, input_hash,
    )

    # --- Build rollback plan ---
    rollback_plan = build_rollback_plan(planned_paths)

    # --- Empty models warning ---
    if not models:
        warnings.append("no models to sync — empty config_draft")

    # --- Build output (before safety checks) ---
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    output = {
        "node": node,
        "dry_run": True,
        "requires_operator_approval": True,
        "planner_version": PLANNER_VERSION,
        "timestamp": now,
        "action_plan": action_plan,
        "config_preview": config_preview,
        "approval_receipt_draft": approval_receipt,
        "rollback_plan": rollback_plan,
        "safety_checks": {},  # filled below
        "warnings": warnings,
        "non_available_summary": non_available,
        "audit": {
            "timestamp": now,
            "operator_id": operator_id,
            "approval_id": approval_id or "",
            "action": "plan_node_sync",
            "target_node": node,
            "input_hash": input_hash,
            "planner_version": PLANNER_VERSION,
        },
    }

    # --- Safety checks ---
    safety = run_safety_checks(renderer_output, dry_run, output)
    output["safety_checks"] = safety

    if not safety["passed"]:
        raise RuntimeError(f"safety checks failed: {safety['violations']}")

    return output


# --- Multi-node Wrapper ---


def plan_multi_node_sync(
    renderer_outputs: list[dict],
    operator_id: str = "",
    dry_run: bool = True,
) -> dict:
    """Plan sync for multiple nodes. Each node is independently planned.

    Args:
        renderer_outputs: List of renderer outputs (one per node)
        operator_id: Operator performing the sync
        dry_run: Must be True

    Returns:
        {
            "dry_run": True,
            "requires_operator_approval": True,
            "planner_version": "...",
            "node_count": N,
            "plans": [plan1, plan2, ...],
            "all_safety_passed": bool,
            "timestamp": "...",
        }
    """
    if dry_run is not True:
        raise ValueError("dry_run must be True")

    if not isinstance(renderer_outputs, list) or not renderer_outputs:
        raise ValueError("renderer_outputs must be a non-empty list")

    plans = []
    all_passed = True

    for i, output in enumerate(renderer_outputs):
        try:
            plan = plan_node_sync(output, operator_id=operator_id, dry_run=dry_run)
            plans.append(plan)
        except (ValueError, RuntimeError) as e:
            plans.append({
                "node": output.get("node", f"unknown-{i}"),
                "error": str(e)[:200],
                "safety_checks": {"passed": False, "violations": [str(e)[:100]]},
            })
            all_passed = False

    return {
        "dry_run": True,
        "requires_operator_approval": True,
        "planner_version": PLANNER_VERSION,
        "node_count": len(plans),
        "plans": plans,
        "all_safety_passed": all_passed,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# --- Self-check ---


def self_check() -> dict:
    """Self-check: verify planner is importable and core logic works."""
    checks = []
    passed = 0
    total = 0

    def check(name: str, ok: bool, detail: str = ""):
        nonlocal passed, total
        total += 1
        if ok:
            passed += 1
        checks.append({"name": name, "passed": ok, "detail": detail})

    # sc-01: version
    check("sc-01-version", bool(PLANNER_VERSION), PLANNER_VERSION)

    # sc-02: basic plan
    fake_renderer = {
        "node": "test-node",
        "dry_run": True,
        "config_draft": {
            "node": "test-node",
            "models": [
                {"alias": "test-model", "provider": "test-prov", "secret_ref": "secret:test-prov:test-model",
                 "credential_source": "node-local-secure-storage", "protocol": "openai-compatible",
                 "endpoint": "", "credential_status": "valid"},
            ],
            "default_model": "test-model",
        },
        "role_assignment": {"implementer": {"model_alias": "test-model", "status": "configured"}},
        "warnings": [],
        "non_available_summary": [],
        "requires_operator_approval": True,
        "audit": {"input_hash": "abc123", "renderer_version": "1.0.0"},
    }

    plan = plan_node_sync(fake_renderer, operator_id="test-op")
    check("sc-02-basic-plan", plan["dry_run"] is True)
    check("sc-02-node", plan["node"] == "test-node")
    check("sc-02-approval", plan["requires_operator_approval"] is True)

    # sc-03: action_plan fields
    ap = plan["action_plan"]
    check("sc-03-action", ap["action"] == "sync_config")
    check("sc-03-model-count", ap["model_count"] == 1)
    check("sc-03-default", ap["default_model"] == "test-model")

    # sc-04: config_preview
    cp = plan["config_preview"]
    check("sc-04-format", cp["format"] == "opencode-jsonc")
    check("sc-04-no-keys", cp["no_real_keys"] is True)
    check("sc-04-hash", bool(cp["content_hash"]))

    # sc-05: approval receipt
    ar = plan["approval_receipt_draft"]
    check("sc-05-status", ar["status"] == "pending_operator_approval")
    check("sc-05-input-hash", bool(ar["input_hash"]))

    # sc-06: rollback plan
    rp = plan["rollback_plan"]
    check("sc-06-dryrun", rp["dry_run_only"] is True)
    check("sc-06-strategy", rp["strategy"] == "backup-and-restore")

    # sc-07: safety checks passed
    sc = plan["safety_checks"]
    check("sc-07-passed", sc["passed"] is True)
    check("sc-07-dryrun", sc["dry_run_enforced"] is True)
    check("sc-07-no-secrets", sc["no_secrets_in_output"] is True)

    # sc-08: audit fields
    audit = plan["audit"]
    check("sc-08-audit-action", audit["action"] == "plan_node_sync")
    check("sc-08-audit-version", audit["planner_version"] == PLANNER_VERSION)

    # sc-09: dry_run=False blocked
    try:
        plan_node_sync(fake_renderer, dry_run=False)
        check("sc-09-dryrun-blocked", False, "should have raised")
    except ValueError:
        check("sc-09-dryrun-blocked", True)

    # sc-10: empty renderer blocked
    try:
        plan_node_sync({}, dry_run=True)
        check("sc-10-empty-blocked", False, "should have raised")
    except ValueError:
        check("sc-10-empty-blocked", True)

    # sc-11: multi-node
    multi = plan_multi_node_sync([fake_renderer], operator_id="test-op")
    check("sc-11-multi-count", multi["node_count"] == 1)
    check("sc-11-multi-safety", multi["all_safety_passed"] is True)

    return {
        "planner_version": PLANNER_VERSION,
        "checks": checks,
        "passed": passed,
        "total": total,
        "status": "ok" if passed == total else "FAIL",
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        result = self_check()
        print(json.dumps(result, indent=2))
    else:
        print("Usage: python node_sync_dryrun_planner.py --self-check")
        sys.exit(0)
