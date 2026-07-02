#!/usr/bin/env python3
"""
VibeDev Worker Attestation Plan Generator + Receipt Schema — DRY-RUN ONLY.

Phase 3 PR-4C. Builds the *template* and *receipt schema* for future
real worker_attest runtime collection. THIS MODULE DOES NOT EXECUTE
ANY COMMAND, OPEN ANY SSH CONNECTION, OR READ ANY REAL WORKER FILE.

Operator policy (PR #276 + Phase 2 design):
- 21bao = Windows local control host → transport MUST be local_exec
- 5bao / 9bao = remote SSH workers   → transport MUST be ssh
- Only output command plan + receipt schema; no execution
- Never output secret value, key length, token, base_url value,
  real endpoint URL, env var value
- command plan MUST NOT include real worker file paths — only labels
- forbidden_operation_flags surfaces any implicit execution attempt

== Public API ==
- build_command_plan(node) -> dict   (template only)
- validate_command_plan(plan) -> dict  (fail-closed)
- build_receipt_template(node) -> dict  (schema stub for later fill)
- validate_receipt(receipt) -> dict
- self_check() -> dict
"""

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Constants ────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()

VALID_NODES = frozenset({"21bao", "5bao", "9bao"})

# Per PR #276 taxonomy: 21bao = local control, 5bao/9bao = remote SSH.
# This is the canonical mapping. The operator override field is a forward
# compatibility hook ONLY; default is false.
DEFAULT_TRANSPORT = {
    "21bao": "local_exec",
    "5bao": "ssh",
    "9bao": "ssh",
}

INTENDED_USER = {
    "21bao": "vibedev",
    "5bao": "vibeworker",
    "9bao": "vibeworker",
}

# Allowed read paths are LABELS only — never real filesystem paths.
ALLOWED_READ_LABELS = frozenset({
    "opencode_config",
    "opencode_env",
    "model_alias_registry",
    "model_pool_manifest",
    "node_model_capability_summary",
})

# Safety flags — every plan MUST have all of these set.
SAFETY_FLAGS = frozenset({
    "no_secret_value_output",
    "no_env_value_output",
    "no_base_url_value_output",
    "no_key_length_output",
    "no_token_output",
    "dry_run_only",
    "no_subprocess_execution",
    "no_ssh_execution",
    "no_real_worker_path_access",
})

# Forbidden command-fragment patterns: any command plan that includes these
# is rejected outright.
FORBIDDEN_COMMAND_FRAGMENTS = (
    "ssh ", "scp ", "rsync ", "nc ", "netcat ",
    "Invoke-Expression", "iex ", "& ",  # PowerShell exec
    "subprocess.run", "subprocess.call", "subprocess.Popen",
    "os.system", "os.popen", "os.exec", "os.spawn",
    "paramiko", "fabric", "pexpect",
    "curl ", "wget ", "Invoke-WebRequest", "iwr ",
    "Read-S3Object", "Get-Content -Raw $env:",
)

RECEIPT_SCHEMA_VERSION = "1.0"
COMMAND_PLAN_SCHEMA_VERSION = "1.0"

RECEIPT_REQUIRED_FIELDS = frozenset({
    "schema_version", "node", "generated_at", "source",
    "command_plan_id", "collection_status", "attestation_file",
    "validator_result", "redaction_status", "forbidden_operation_flags",
})

RECEIPT_VALID_COLLECTION_STATUS = frozenset({
    "not_collected",  # default for dry-run; no real collection happened
    "skipped",        # operator explicitly skipped
    "error",          # collection attempt failed
    "completed",      # real collection happened (operator-asserted)
})


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _has_secret_pattern(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    s = value
    patterns = ("sk-", "sk-ant-", "sk-proj-", "ghp_", "gho_", "glpat-",
                "xai-", "-----BEGIN", "AKIA")
    for p in patterns:
        if p in s:
            return True
    return False


def _has_url_pattern(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return ("http://" in value) or ("https://" in value)


def _looks_like_real_path(value: Any) -> bool:
    """Detect a real filesystem path (Windows or POSIX absolute)."""
    if not isinstance(value, str):
        return False
    if value.startswith(("/", "\\")) and len(value) > 1:
        return True
    if len(value) >= 3 and value[1] == ":" and value[2] in ("/", "\\"):
        return True
    return False


# ── Command plan builder ─────────────────────────────────────────────────────


def build_command_plan(
    node: str,
    operator_override_local_exec_for_remote: bool = False,
) -> dict:
    """Build a dry-run command plan template for a node.

    Returns a dict suitable for JSON serialization. No execution. No real
    path materialization.

    Args:
        node: must be one of VALID_NODES.
        operator_override_local_exec_for_remote: explicit forward-compat
            hook. Defaults to False. If True, allows 5bao/9bao to use
            local_exec transport (still does NOT execute). Recorded in
            the plan as a flag.

    Returns:
        dict with command plan fields.
    """
    if node not in VALID_NODES:
        raise ValueError(
            f"Unknown node '{node}'. Must be one of: {sorted(VALID_NODES)}"
        )

    transport = DEFAULT_TRANSPORT[node]
    if transport == "ssh" and operator_override_local_exec_for_remote:
        transport = "local_exec"
    if node == "21bao" and operator_override_local_exec_for_remote:
        # 21bao override is meaningless (already local) but allowed for
        # forward-compat; no semantic change.
        pass

    plan = {
        "schema_version": COMMAND_PLAN_SCHEMA_VERSION,
        "plan_id": f"plan_{node}_{uuid.uuid4().hex[:12]}",
        "generated_at": _now_iso(),
        "node": node,
        "transport_type": transport,
        "intended_user": INTENDED_USER[node],
        "allowed_read_paths": sorted(ALLOWED_READ_LABELS),
        "output_path": None,            # LABEL only, never materialized
        "output_path_label": "worker_attest_receipt.json",
        "receipt_path": None,           # LABEL only, never materialized
        "receipt_path_label": "central_model_pool_audit_log",
        "safety_flags": sorted(SAFETY_FLAGS),
        "operator_override_local_exec_for_remote":
            operator_override_local_exec_for_remote,
        "forbidden_operations": [
            "no_real_worker_file_read",
            "no_ssh_connection",
            "no_subprocess_execution",
            "no_os_environ_read",
            "no_opencode_jsonc_direct_read",
            "no_opencode_env_direct_read",
        ],
        "no_secret_value_output": True,
        "no_env_value_output": True,
        "no_base_url_value_output": True,
        "no_real_endpoint_url_output": True,
        "command_template": {
            # Template only — the actual command is the label below, never
            # materializes a real path. There is no execution entry point.
            "kind": "dry_run_template",
            "description": (
                f"local attestation plan for {node} via canonical local "
                f"transport — DRY RUN ONLY, no execution. Real collection "
                f"is operator-approved future PR-4D (not in this PR)."
            ),
        },
    }
    return plan


# ── Command plan validator (fail-closed) ─────────────────────────────────────


def validate_command_plan(plan: Any) -> dict:
    """Validate a command plan dict. Returns fail-closed report.

    A 'valid' plan MUST be:
      - a dict
      - have a known node
      - have the canonical transport for that node (unless explicit
        operator_override_local_exec_for_remote flag is true)
      - have all safety_flags set to true
      - contain no secret-like value, no real URL, no real path,
        no real env var name lookups, no forbidden command fragment.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(plan, dict):
        return {
            "valid": False,
            "errors": ["plan must be a dict"],
            "warnings": warnings,
            "blocked_reason": "plan_not_dict",
        }

    # ── Required fields ──
    required = {
        "schema_version", "plan_id", "generated_at", "node",
        "transport_type", "intended_user", "allowed_read_paths",
        "safety_flags", "command_template",
    }
    for f in required:
        if f not in plan:
            errors.append(f"Missing required field: '{f}'")

    # ── Node check ──
    node = plan.get("node", "")
    if node not in VALID_NODES:
        errors.append(
            f"Invalid node '{node}'. Must be one of: {sorted(VALID_NODES)}"
        )

    # ── Transport taxonomy ──
    transport = plan.get("transport_type", "")
    if node == "21bao":
        if transport != "local_exec":
            errors.append(
                f"21bao transport MUST be 'local_exec', got '{transport}'. "
                f"21bao is the Windows local control host."
            )
    elif node in ("5bao", "9bao"):
        if transport == "local_exec":
            # Allowed only with explicit operator override
            override = plan.get(
                "operator_override_local_exec_for_remote", False
            )
            if not override:
                errors.append(
                    f"{node} transport is 'local_exec' but node is a "
                    f"remote SSH worker. Either set transport='ssh' OR "
                    f"set 'operator_override_local_exec_for_remote: true' "
                    f"explicitly."
                )
            else:
                warnings.append(
                    f"{node} uses local_exec transport via explicit "
                    f"operator_override (forward-compat hook)."
                )
        elif transport != "ssh":
            errors.append(
                f"{node} transport must be 'ssh' (remote worker) or "
                f"'local_exec' (with operator override), got '{transport}'."
            )
    else:
        errors.append(f"Unknown node '{node}'")

    # ── Safety flags ──
    sf = plan.get("safety_flags", [])
    if not isinstance(sf, list):
        errors.append("safety_flags must be a list")
        sf = []
    missing_flags = SAFETY_FLAGS - set(sf)
    if missing_flags:
        errors.append(
            f"Missing required safety_flags: {sorted(missing_flags)}"
        )

    # ── Re-check explicit booleans ──
    for bool_field in [
        "no_secret_value_output", "no_env_value_output",
        "no_base_url_value_output", "no_real_endpoint_url_output",
    ]:
        if not plan.get(bool_field, False):
            errors.append(f"Safety flag '{bool_field}' must be True")

    # ── Scan all string values for secret/URL/path ──
    for path_in_plan, value in _iter_strings(plan):
        if _has_secret_pattern(value):
            errors.append(
                f"Field '{path_in_plan}' contains secret-like value"
            )
        if _has_url_pattern(value):
            errors.append(
                f"Field '{path_in_plan}' contains real URL value"
            )
        if path_in_plan.endswith(("output_path", "receipt_path")):
            if value is not None and _looks_like_real_path(value):
                errors.append(
                    f"Field '{path_in_plan}' contains real filesystem path; "
                    f"labels only"
                )
        # forbidden command fragment scan
        if isinstance(value, str):
            low = value.lower()
            for frag in FORBIDDEN_COMMAND_FRAGMENTS:
                if frag.lower() in low:
                    errors.append(
                        f"Field '{path_in_plan}' contains forbidden "
                        f"execution fragment '{frag}'"
                    )

    # ── command_template kind ──
    ct = plan.get("command_template", {})
    if not isinstance(ct, dict):
        errors.append("command_template must be a dict")
    else:
        kind = ct.get("kind", "")
        if kind != "dry_run_template":
            errors.append(
                f"command_template.kind must be 'dry_run_template', "
                f"got '{kind}'"
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "node": node,
        "transport": transport,
        "blocked_reason": None if not errors else "command_plan_invalid",
    }


def _iter_strings(obj, prefix=""):
    """Yield (dotted_path, str_value) pairs for every string in a nested dict."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            child_prefix = f"{prefix}.{k}" if prefix else k
            yield from _iter_strings(v, child_prefix)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            child_prefix = f"{prefix}[{i}]"
            yield from _iter_strings(v, child_prefix)
    elif isinstance(obj, str):
        yield prefix, obj


# ── Receipt template + validator ─────────────────────────────────────────────


def build_receipt_template(
    node: str,
    command_plan_id: str,
    collection_status: str = "not_collected",
) -> dict:
    """Build a receipt schema stub for a node. DRY-RUN: collection_status
    is always 'not_collected' by default. Real receipt fill is operator-
    approved future PR-4D (not this PR)."""
    if node not in VALID_NODES:
        raise ValueError(f"Unknown node '{node}'")
    if collection_status not in RECEIPT_VALID_COLLECTION_STATUS:
        raise ValueError(
            f"Invalid collection_status '{collection_status}'. "
            f"Must be one of: {sorted(RECEIPT_VALID_COLLECTION_STATUS)}"
        )
    return {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "node": node,
        "generated_at": _now_iso(),
        "source": "worker_attest_runtime",
        "command_plan_id": command_plan_id,
        "collection_status": collection_status,
        "attestation_file": None,            # LABEL only when filled
        "attestation_file_label": "worker_attest_{node}.json".format(node=node),
        "validator_result": {
            "valid": None,                  # unknown until real run
            "errors": [],
            "warnings": [],
            "detail": "not_validated_yet",
        },
        "redaction_status": {
            "no_secret_value": True,
            "no_env_value": True,
            "no_base_url_value": True,
            "no_real_endpoint_url": True,
            "no_key_length": True,
        },
        "forbidden_operation_flags": {
            "ssh_attempted": False,
            "subprocess_attempted": False,
            "os_environ_read_attempted": False,
            "real_path_read_attempted": False,
            "model_call_attempted": False,
            "credential_provisioning_attempted": False,
        },
    }


def validate_receipt(receipt: Any) -> dict:
    """Validate a receipt against schema. Fail-closed."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(receipt, dict):
        return {
            "valid": False,
            "errors": ["receipt must be a dict"],
            "warnings": warnings,
            "blocked_reason": "receipt_not_dict",
        }

    # Required fields
    for f in RECEIPT_REQUIRED_FIELDS:
        if f not in receipt:
            errors.append(f"Missing required field: '{f}'")

    # schema_version
    sv = receipt.get("schema_version", "")
    if sv != RECEIPT_SCHEMA_VERSION:
        errors.append(
            f"schema_version must be '{RECEIPT_SCHEMA_VERSION}', got '{sv}'"
        )

    # node
    node = receipt.get("node", "")
    if node not in VALID_NODES:
        errors.append(
            f"Invalid node '{node}'. Must be one of: {sorted(VALID_NODES)}"
        )

    # source
    if receipt.get("source") != "worker_attest_runtime":
        errors.append(
            "source must be 'worker_attest_runtime'"
        )

    # collection_status
    cs = receipt.get("collection_status", "")
    if cs not in RECEIPT_VALID_COLLECTION_STATUS:
        errors.append(
            f"Invalid collection_status '{cs}'. Must be one of: "
            f"{sorted(RECEIPT_VALID_COLLECTION_STATUS)}"
        )

    # command_plan_id
    cpid = receipt.get("command_plan_id", "")
    if not isinstance(cpid, str) or not cpid.strip():
        errors.append("command_plan_id must be non-empty string")

    # attestation_file: must be label or None
    af = receipt.get("attestation_file")
    if af is not None:
        if not isinstance(af, str):
            errors.append("attestation_file must be string or null")
        elif _looks_like_real_path(af):
            errors.append(
                "attestation_file must be a label, not a real path"
            )
        elif _has_url_pattern(af):
            errors.append(
                "attestation_file must not be a URL"
            )

    # validator_result must be a dict
    vr = receipt.get("validator_result")
    if not isinstance(vr, dict):
        errors.append("validator_result must be a dict")
    else:
        for k in ("valid", "errors", "warnings", "detail"):
            if k not in vr:
                errors.append(f"validator_result missing '{k}'")

    # redaction_status
    rs = receipt.get("redaction_status")
    if not isinstance(rs, dict):
        errors.append("redaction_status must be a dict")
    else:
        for k in ("no_secret_value", "no_env_value", "no_base_url_value",
                   "no_real_endpoint_url", "no_key_length"):
            if k not in rs:
                errors.append(f"redaction_status missing '{k}'")
            elif not isinstance(rs[k], bool):
                errors.append(f"redaction_status.{k} must be boolean")
            elif rs[k] is False:
                errors.append(f"redaction_status.{k} must be True")

    # forbidden_operation_flags
    fof = receipt.get("forbidden_operation_flags")
    if not isinstance(fof, dict):
        errors.append("forbidden_operation_flags must be a dict")
    else:
        for k in ("ssh_attempted", "subprocess_attempted",
                   "os_environ_read_attempted", "real_path_read_attempted",
                   "model_call_attempted",
                   "credential_provisioning_attempted"):
            if k not in fof:
                errors.append(f"forbidden_operation_flags missing '{k}'")
            elif not isinstance(fof[k], bool):
                errors.append(f"forbidden_operation_flags.{k} must be bool")
            elif fof[k] is True:
                errors.append(
                    f"forbidden_operation_flags.{k} must be False "
                    f"(forbidden operation detected)"
                )

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "node": node,
        "collection_status": cs,
        "blocked_reason": None if not errors else "receipt_invalid",
    }


# ── Self-check ───────────────────────────────────────────────────────────────


def self_check() -> dict:
    """Run a self-check that exercises all branches. No file I/O. No env."""
    checks: list[dict] = []

    # 1. valid 21bao plan
    p21 = build_command_plan("21bao")
    r21 = validate_command_plan(p21)
    checks.append({
        "name": "plan_21bao_local_exec_valid",
        "passed": r21["valid"],
        "detail": f"errors={len(r21['errors'])}",
    })

    # 2. valid 5bao ssh plan
    p5 = build_command_plan("5bao")
    r5 = validate_command_plan(p5)
    checks.append({
        "name": "plan_5bao_ssh_valid",
        "passed": r5["valid"],
        "detail": f"errors={len(r5['errors'])}",
    })

    # 3. valid 9bao ssh plan
    p9 = build_command_plan("9bao")
    r9 = validate_command_plan(p9)
    checks.append({
        "name": "plan_9bao_ssh_valid",
        "passed": r9["valid"],
        "detail": f"errors={len(r9['errors'])}",
    })

    # 4. invalid node blocked
    try:
        build_command_plan("10bao")
        blocked = False
    except ValueError:
        blocked = True
    checks.append({
        "name": "plan_invalid_node_blocked",
        "passed": blocked,
        "detail": "10bao rejected",
    })

    # 5. 21bao as ssh blocked
    p21_bad = build_command_plan("21bao")
    p21_bad["transport_type"] = "ssh"
    r21_bad = validate_command_plan(p21_bad)
    checks.append({
        "name": "plan_21bao_as_ssh_blocked",
        "passed": (not r21_bad["valid"]) and any("local_exec" in e for e in r21_bad["errors"]),
        "detail": f"errors={r21_bad['errors'][:1]}",
    })

    # 6. 5bao/9bao as local_exec blocked without override
    p5_bad = build_command_plan("5bao")
    p5_bad["transport_type"] = "local_exec"
    p5_bad["operator_override_local_exec_for_remote"] = False
    r5_bad = validate_command_plan(p5_bad)
    checks.append({
        "name": "plan_5bao_as_local_exec_blocked",
        "passed": (not r5_bad["valid"]),
        "detail": f"errors={len(r5_bad['errors'])}",
    })

    # 7. 5bao local_exec WITH override allowed
    p5_ov = build_command_plan("5bao", operator_override_local_exec_for_remote=True)
    r5_ov = validate_command_plan(p5_ov)
    checks.append({
        "name": "plan_5bao_local_exec_with_override",
        "passed": r5_ov["valid"],
        "detail": f"errors={len(r5_ov['errors'])} warnings={len(r5_ov['warnings'])}",
    })

    # 8. secret in command plan blocked
    p_bad = build_command_plan("21bao")
    p_bad["command_template"]["secret"] = "sk-ant-fake-12345678901234567890"
    r_bad = validate_command_plan(p_bad)
    checks.append({
        "name": "plan_secret_blocked",
        "passed": (not r_bad["valid"]),
        "detail": f"errors={len(r_bad['errors'])}",
    })

    # 9. URL in command plan blocked
    p_bad2 = build_command_plan("21bao")
    p_bad2["command_template"]["endpoint"] = "https://api.opencode.ai/zen/go/v1"
    r_bad2 = validate_command_plan(p_bad2)
    checks.append({
        "name": "plan_url_blocked",
        "passed": (not r_bad2["valid"]),
        "detail": f"errors={len(r_bad2['errors'])}",
    })

    # 10. forbidden command fragment blocked
    p_bad3 = build_command_plan("5bao")
    p_bad3["command_template"]["shell"] = "ssh vibeworker@5bao cat ~/.opencode"
    r_bad3 = validate_command_plan(p_bad3)
    checks.append({
        "name": "plan_ssh_fragment_blocked",
        "passed": (not r_bad3["valid"]),
        "detail": f"errors={len(r_bad3['errors'])}",
    })

    # 11. receipt valid
    plan = build_command_plan("21bao")
    receipt = build_receipt_template("21bao", plan["plan_id"])
    rr = validate_receipt(receipt)
    checks.append({
        "name": "receipt_valid",
        "passed": rr["valid"],
        "detail": f"errors={len(rr['errors'])}",
    })

    # 12. receipt missing field blocked
    bad_receipt = dict(receipt)
    del bad_receipt["command_plan_id"]
    rr_bad = validate_receipt(bad_receipt)
    checks.append({
        "name": "receipt_missing_field_blocked",
        "passed": (not rr_bad["valid"]),
        "detail": f"errors={len(rr_bad['errors'])}",
    })

    # 13. receipt with forbidden op flag set → blocked
    bad_receipt2 = build_receipt_template("5bao", plan["plan_id"])
    bad_receipt2["forbidden_operation_flags"]["ssh_attempted"] = True
    rr_bad2 = validate_receipt(bad_receipt2)
    checks.append({
        "name": "receipt_forbidden_op_flag_blocked",
        "passed": (not rr_bad2["valid"]),
        "detail": f"errors={len(rr_bad2['errors'])}",
    })

    # 14. unknown node in receipt blocked
    bad_receipt3 = build_receipt_template("5bao", plan["plan_id"])
    bad_receipt3["node"] = "10bao"
    rr_bad3 = validate_receipt(bad_receipt3)
    checks.append({
        "name": "receipt_invalid_node_blocked",
        "passed": (not rr_bad3["valid"]),
        "detail": f"errors={len(rr_bad3['errors'])}",
    })

    # 15. output_path with real filesystem path blocked (use a non-real
    #     example path that is still recognized as a real path by the
    #     validator; here we use a Windows-style absolute path that is
    #     not a real user home).
    p_bad4 = build_command_plan("21bao")
    p_bad4["output_path"] = "Z:/example/config.json"
    r_bad4 = validate_command_plan(p_bad4)
    checks.append({
        "name": "plan_real_path_blocked",
        "passed": (not r_bad4["valid"]),
        "detail": f"errors={len(r_bad4['errors'])}",
    })

    passed_count = sum(1 for c in checks if c["passed"])
    return {
        "status": "PASS" if passed_count == len(checks) else "FAIL",
        "version": "1.0.0",
        "checks": checks,
        "detail": f"{passed_count}/{len(checks)} passed",
    }


# ── CLI ──────────────────────────────────────────────────────────────────────


def _print_json(data: dict) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python worker_attest_plan.py self-check")
        print("  python worker_attest_plan.py plan --node 21bao|5bao|9bao")
        print(
            "  python worker_attest_plan.py validate-receipt --file <path>"
        )
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "self-check":
        r = self_check()
        _print_json(r)
        sys.exit(0 if r["status"] == "PASS" else 1)

    elif cmd == "plan":
        # parse --node
        node = None
        i = 2
        while i < len(sys.argv):
            a = sys.argv[i]
            if a == "--node" and i + 1 < len(sys.argv):
                node = sys.argv[i + 1]
                i += 2
            else:
                print(f"Unknown arg: {a}", file=sys.stderr)
                sys.exit(2)
        if node is None:
            print("--node required", file=sys.stderr)
            sys.exit(2)
        try:
            plan = build_command_plan(node)
        except ValueError as e:
            err = {"error": str(e), "blocked_reason": "invalid_node"}
            _print_json(err)
            sys.exit(1)
        _print_json(plan)
        sys.exit(0)

    elif cmd == "validate-receipt":
        fpath = None
        i = 2
        while i < len(sys.argv):
            a = sys.argv[i]
            if a == "--file" and i + 1 < len(sys.argv):
                fpath = sys.argv[i + 1]
                i += 2
            else:
                print(f"Unknown arg: {a}", file=sys.stderr)
                sys.exit(2)
        if fpath is None:
            print("--file required", file=sys.stderr)
            sys.exit(2)
        p = Path(fpath)
        if not p.exists():
            err = {"valid": False, "errors": [f"file not found: {fpath}"],
                   "blocked_reason": "file_not_found"}
            _print_json(err)
            sys.exit(1)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            err = {"valid": False, "errors": [f"JSON parse error: {e}"],
                   "blocked_reason": "json_parse_error"}
            _print_json(err)
            sys.exit(1)
        r = validate_receipt(data)
        _print_json(r)
        sys.exit(0 if r["valid"] else 1)

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
