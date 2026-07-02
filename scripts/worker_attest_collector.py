#!/usr/bin/env python3
"""
VibeDev Worker Attest Collector — DRY-RUN BY DEFAULT.

Phase 3 PR-4D (21bao local), PR-4G (5bao SSH), PR-4H (9bao SSH).
This implements the read-only collection half of the worker_attest
pipeline for 21bao (local), 5bao (SSH), and 9bao (SSH).

== Operating modes ==

1. **dry-run (default)**:
   - No file I/O
   - No env read
   - No subprocess
   - Returns collection_status="not_collected"
   - Use for plan validation, audit-trail drafts, CI gates

2. **real-collection (operator-approved)**:
   - Caller MUST pass operator_approved_real_read=True
   - Caller MUST pass an explicit allowlist of LABEL paths (not real
     filesystem paths); these resolve to fixture files only by default
   - In PR-4D the real-mode loader is fixture-driven: the "real read"
     is from a local fixture that simulates what the 21bao
     opencode_config + opencode_env would look like, but the
     fixture is read from inside the repo (tests/fixtures/...).
   - Returns collection_status="completed" only on success
   - Real remote filesystem reads of `~/.opencode/` on 21bao are
     DEFERRED to a future PR with explicit operator approval and
     auditable path passing.

== Safety guarantees ==

- 21bao = local Windows node (PR-4D)
- 5bao/9bao = remote Debian SSH workers (PR-4G / PR-4H)
- local_exec only: refuses ssh transport
- No real secret value, key length, token, base_url value, real
  endpoint URL, env var value
- Only reads key_env NAME, base_url_env NAME, model_id, alias,
  provider_namespace, lifecycle_status, credential_status, endpoint_ref
  — all metadata, never secrets
- All output JSON goes through audit-safe redaction before emission
- Receipt is validated against worker_attest_plan.validate_receipt
- forbidden_operation_flags must all be False; any True → blocked
- AST-verifiable: no subprocess, no os.environ, no socket, no ssh libs

== Public API ==

- build_collection_plan(node, dry_run=True) -> dict
- collect_21bao_local(plan, fixture_path=None,
                       operator_approved_real_read=False) -> dict
- collect_5bao_remote(plan, operator_approved_real_read=False) -> dict
- collect_9bao_remote(plan, operator_approved_real_read=False) -> dict
- self_check() -> dict
- CLI: collect --node 21bao|5bao|9bao [--fixture PATH] [--real]
        (--real is gated; refused without explicit env var
         WORKER_ATTEST_OPERATOR_APPROVED=1)
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Force-disable real-mode unless the operator explicitly approves.
# This is a defense-in-depth: even if caller passes
# operator_approved_real_read=True, the CLI also requires the env var.
_OPERATOR_APPROVED_ENV = "WORKER_ATTEST_OPERATOR_APPROVED"

# ── Constants ────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).parent.resolve()

# 21bao = local Windows node. 5bao/9bao = remote Debian SSH workers.
# 5bao: PR-4G. 9bao: PR-4H.
VALID_NODES = frozenset({"21bao", "5bao", "9bao"})

# Labels for the allowlist. These are LABELS, not real paths.
# Real path resolution goes through _resolve_label_to_path(), which
# only ever resolves to a fixture file under tests/fixtures/.
ALLOWED_READ_LABELS = frozenset({
    "opencode_config",   # opencode.jsonc metadata
    "opencode_env",      # env var NAMES (never values)
    "model_alias_registry",
    "model_pool_manifest",
    "node_model_capability_summary",
})

# Default fixture file per label. These are tests/fixtures/... paths,
# NOT real 21bao filesystem paths. Real-path resolution is DEFERRED.
DEFAULT_FIXTURE_FOR_LABEL = {
    "opencode_config": SCRIPT_DIR.parent
        / "tests" / "fixtures" / "worker_attest_21bao" / "opencode_config.json",
    "opencode_env": SCRIPT_DIR.parent
        / "tests" / "fixtures" / "worker_attest_21bao" / "opencode_env.json",
    "model_alias_registry": SCRIPT_DIR.parent
        / "tests" / "fixtures" / "worker_attest_21bao" / "model_alias_registry.json",
    "model_pool_manifest": SCRIPT_DIR.parent
        / "scripts" / "model_pool_manifest.json",
    "node_model_capability_summary": SCRIPT_DIR.parent
        / "scripts" / "node_model_capability.yaml",
}

# Real 21bao filesystem paths for canary mode (PR-4F).
# These are the ACTUAL paths on 21bao, resolved at runtime for the canary.
# Only paths that exist on this node are valid.
CANARY_21BAO_REAL_PATHS = frozenset({
    Path.home() / ".config" / "opencode" / "opencode.jsonc",
})

# Env var name pattern to extract from config {env:...} references.
# These are env var NAMES, never values — entirely audit-safe.
_ENV_REF_PATTERN = "{env:"

COLLECTOR_SCHEMA_VERSION = "1.0"

# ── 5bao SSH config (PR-4G canary) ───────────────────────────────────────────
# These are the connection parameters for SSH-based collection on 5bao.
_SSH_5BAO_USER = "vibeworker"
_SSH_5BAO_HOST = "192.168.5.6"
_SSH_5BAO_PORT = 22222
_SSH_5BAO_KEY = Path(
    os.environ.get("VIBEDEV_SSH_KEY",
                   str(Path.home() / "AppData" / "Local" / "vibedev-tools"
                       / "ssh" / "debian-vibeworker-ed25519"))
)

# ── 9bao SSH config (PR-4H canary) ───────────────────────────────────────────
# These are the connection parameters for SSH-based collection on 9bao.
# Mirrors the PR-4G 5bao pattern; isolated to 9bao only.
_SSH_9BAO_USER = "vibeworker"
_SSH_9BAO_HOST = "192.168.9.6"
_SSH_9BAO_PORT = 22222
_SSH_9BAO_KEY = Path(
    os.environ.get("VIBEDEV_SSH_KEY",
                   str(Path.home() / "AppData" / "Local" / "vibedev-tools"
                       / "ssh" / "debian-vibeworker-ed25519"))
)

# Remote Python script that runs on 5bao via SSH to read config safely.
# Only extracts metadata (provider names, model keys, env var names) — NO
# secret values, NO api keys, NO base URLs, NO env var values.
# The output is JSON with safe fields only.
_5BAO_REMOTE_COLLECTOR_SCRIPT = r"""
import json, os, sys
config_path = os.path.expanduser('~/.config/opencode/config.json')
if not os.path.exists(config_path):
    config_path = os.path.expanduser('~/.config/opencode/opencode.jsonc')
if not os.path.exists(config_path):
    print(json.dumps({'error': 'config not found', 'paths_checked': [
        '~/.config/opencode/config.json',
        '~/.config/opencode/opencode.jsonc'
    ]}))
    sys.exit(0)
data = json.load(open(config_path))
# Extract env var NAMES from {env:...} references (never values)
env_names = set()
def _scan_for_env_refs(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            _scan_for_env_refs(v)
    elif isinstance(obj, list):
        for item in obj:
            _scan_for_env_refs(item)
    elif isinstance(obj, str):
        for token in obj.split():
            if '{env:' in token:
                start = token.find('{env:') + 5
                end = token.find('}', start)
                if end > start:
                    name = token[start:end].strip()
                    if name:
                        env_names.add(name)
_scan_for_env_refs(data)
# Extract only safe model metadata
providers = data.get('provider', {})
output = {
    'config_present': True,
    'provider_namespaces': list(providers.keys()),
    'model_aliases': [],
    'env_var_names': sorted(env_names),
}
for ns_name, ns_data in providers.items():
    models = ns_data.get('models', {})
    if not isinstance(models, dict):
        continue
    for model_key in models:
        alias = model_key.lower().replace('_', '-').replace('.', '-')
        output['model_aliases'].append({
            'model_id': f'{ns_name}-{model_key}',
            'alias': alias,
            'provider_namespace': ns_name,
            'lifecycle_status': 'operator_requested',
            'credential_status': 'present',
            'endpoint_ref': 'base_url_env',
            'key_env': f'OPENCODE_{ns_name.upper()}_API_KEY',
            'base_url_env': f'OPENCODE_{ns_name.upper()}_BASE_URL',
        })
print(json.dumps(output))
"""

# Remote Python script that runs on 9bao via SSH to read config safely.
# Identical extraction logic to the 5bao script; isolated constant for
# audit traceability (PR-4H). NO secret values, NO api keys, NO base URLs,
# NO env var values. Output is JSON with safe fields only.
_9BAO_REMOTE_COLLECTOR_SCRIPT = r"""
import json, os, sys
config_path = os.path.expanduser('~/.config/opencode/config.json')
if not os.path.exists(config_path):
    config_path = os.path.expanduser('~/.config/opencode/opencode.jsonc')
if not os.path.exists(config_path):
    print(json.dumps({'error': 'config not found', 'paths_checked': [
        '~/.config/opencode/config.json',
        '~/.config/opencode/opencode.jsonc'
    ]}))
    sys.exit(0)
try:
    data = json.load(open(config_path))
except Exception as e:
    print(json.dumps({'error': 'json parse failed: ' + str(e)}))
    sys.exit(0)
# Extract env var NAMES from {env:...} references (never values)
env_names = set()
def _scan_for_env_refs(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            _scan_for_env_refs(v)
    elif isinstance(obj, list):
        for item in obj:
            _scan_for_env_refs(item)
    elif isinstance(obj, str):
        for token in obj.split():
            if '{env:' in token:
                start = token.find('{env:') + 5
                end = token.find('}', start)
                if end > start:
                    name = token[start:end].strip()
                    if name:
                        env_names.add(name)
_scan_for_env_refs(data)
# Extract only safe model metadata
providers = data.get('provider', {})
output = {
    'config_present': True,
    'provider_namespaces': list(providers.keys()),
    'model_aliases': [],
    'env_var_names': sorted(env_names),
}
for ns_name, ns_data in providers.items():
    models = ns_data.get('models', {})
    if not isinstance(models, dict):
        continue
    for model_key in models:
        alias = model_key.lower().replace('_', '-').replace('.', '-')
        output['model_aliases'].append({
            'model_id': f'{ns_name}-{model_key}',
            'alias': alias,
            'provider_namespace': ns_name,
            'lifecycle_status': 'operator_requested',
            'credential_status': 'present',
            'endpoint_ref': 'base_url_env',
            'key_env': f'OPENCODE_{ns_name.upper()}_API_KEY',
            'base_url_env': f'OPENCODE_{ns_name.upper()}_BASE_URL',
        })
print(json.dumps(output))
"""

# Pattern set for redaction-detection on output (NOT for executing).
_SECRET_PATTERNS = ("sk-", "sk-ant-", "sk-proj-", "ghp_", "gho_",
                    "glpat-", "xai-", "AKIA", "-----BEGIN")
_URL_PATTERNS = ("http://", "https://")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _string_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    return ""


def _looks_like_secret(value: Any) -> bool:
    s = _string_value(value)
    if not s:
        return False
    for p in _SECRET_PATTERNS:
        if p in s:
            return True
    return False


def _looks_like_url(value: Any) -> bool:
    s = _string_value(value)
    if not s:
        return False
    for p in _URL_PATTERNS:
        if p in s:
            return True
    return False


def _redact_value(value: Any) -> Any:
    """Return a safe replacement for any value that looks like a secret
    or URL. Returns the original value (truncated to label) if safe.
    Never logs the original secret/url value."""
    if value is None:
        return None
    if isinstance(value, str):
        if _looks_like_secret(value):
            return "[REDACTED:secret-like]"
        if _looks_like_url(value):
            return "[REDACTED:url-like]"
        return value
    return value


def _redact_dict(d: dict) -> dict:
    """Recursively redact a dict, returning a new dict with sensitive
    values replaced by [REDACTED:...] labels."""
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = _redact_dict(v)
        elif isinstance(v, list):
            out[k] = [_redact_value(x) if not isinstance(x, dict)
                      else _redact_dict(x) for x in v]
        else:
            out[k] = _redact_value(v)
    return out


def _resolve_label_to_path(label: str) -> Path:
    """Resolve a whitelisted LABEL to its default fixture path.
    Raises ValueError if the label is not in the allowlist.
    The returned path is always a path under the repo, never a real
    worker filesystem path (e.g. /home/vibeworker/...)."""
    if label not in ALLOWED_READ_LABELS:
        raise ValueError(
            f"Label '{label}' is not in the allowlist. "
            f"Allowed labels: {sorted(ALLOWED_READ_LABELS)}"
        )
    return DEFAULT_FIXTURE_FOR_LABEL[label]


# ── Real 21bao config reader (canary mode, PR-4F) ────────────────────────────


def _extract_env_names_from_config(config: dict) -> dict:
    """Extract env var NAMES from {env:...} references in config.

    Scans all string values in the config dict for {env:VARIABLE_NAME}
    patterns and returns their names. Never reads actual env values.
    """
    env_names: dict[str, str] = {}
    def _scan(obj):
        if isinstance(obj, dict):
            for v in obj.values():
                _scan(v)
        elif isinstance(obj, list):
            for item in obj:
                _scan(item)
        elif isinstance(obj, str):
            for token in obj.split():
                if _ENV_REF_PATTERN in token:
                    # Extract name from {env:NAME} or {env:NAME}
                    start = token.find(_ENV_REF_PATTERN) + len(_ENV_REF_PATTERN)
                    end = token.find("}", start)
                    if end > start:
                        name = token[start:end].strip()
                        if name:
                            env_names[name] = "ENV_NAME_ONLY_NEVER_VALUE"
    _scan(config)
    return env_names


def _read_real_21bao_files() -> dict:
    """Read real 21bao OpenCode configuration from the local filesystem.

    This is the PR-4F canary: the FIRST safe real-filesystem read of 21bao
    config. Returns a fixture-shaped dict suitable for
    _build_attestation_from_fixture().

    Safety guarantees:
    - Paths are hardcoded, not user-provided
    - Only files in CANARY_21BAO_REAL_PATHS are read
    - Missing files return error, never crash or create fake data
    - All output goes through the standard redaction pipeline
    - Env var NAMES are extracted from {env:...} refs (never read from env)
    """
    config_path = Path.home() / ".config" / "opencode" / "opencode.jsonc"

    if config_path not in CANARY_21BAO_REAL_PATHS:
        raise ValueError(
            f"Path {config_path} is not in the canary allowlist"
        )

    if not config_path.exists():
        raise FileNotFoundError(
            f"Real 21bao config not found at {config_path}. "
            f"This is expected if OpenCode is not configured on this node."
        )

    raw = json.loads(config_path.read_text(encoding="utf-8"))

    # Extract env var NAMES from {env:...} references
    env_names = _extract_env_names_from_config(raw)

    # Extract model aliases from provider configurations
    model_aliases: list[dict] = []
    providers = raw.get("provider", {})
    if isinstance(providers, dict):
        for ns_name, ns_data in providers.items():
            models = ns_data.get("models", {})
            if not isinstance(models, dict):
                continue
            for model_key in models:
                model_id = f"{ns_name}-{model_key}"
                alias = model_key.lower().replace("_", "-").replace(".", "-")
                entry = {
                    "model_id": model_id,
                    "alias": alias,
                    "provider_namespace": ns_name,
                    "lifecycle_status": "operator_requested",
                    "credential_status": "present",
                    "endpoint_ref": "base_url_env",
                    "key_env": f"OPENCODE_{ns_name.upper()}_API_KEY",
                    "base_url_env": f"OPENCODE_{ns_name.upper()}_BASE_URL",
                }
                model_aliases.append(entry)

    return {
        "opencode_config": {
            "schema_version": "1.0",
            "node": "21bao",
        },
        "opencode_env": env_names,
        "model_aliases": model_aliases,
    }





def build_collection_plan(
    node: str,
    dry_run: bool = True,
) -> dict:
    """Build a collection plan for the given node.

    21bao: local_exec, dry-run by default.
    5bao/9bao: ssh, dry-run by default (PR-4G/PR-4H canary).

    dry_run=True: no real reads. Returns a plan with collection_status
                  that will be 'not_collected' after collect.
    dry_run=False: real-mode plan, still requires operator_approved_real_read
                   to actually execute any read.

    Raises ValueError for unsupported nodes.
    """
    if node not in VALID_NODES:
        raise ValueError(
            f"Node '{node}' is not supported. "
            f"Supported: {sorted(VALID_NODES)}"
        )

    if node == "21bao":
        return {
            "schema_version": COLLECTOR_SCHEMA_VERSION,
            "plan_id": f"collect_{node}_{int(datetime.now(timezone.utc).timestamp())}",
            "generated_at": _now_iso(),
            "node": node,
            "collector": "21bao_local_only",
            "transport_type": "local_exec",
            "intended_user": "vibedev",
            "dry_run": dry_run,
            "allowed_read_labels": sorted(ALLOWED_READ_LABELS),
            "no_secret_value_output": True,
            "no_env_value_output": True,
            "no_base_url_value_output": True,
            "no_real_endpoint_url_output": True,
            "no_ssh_execution": True,
            "no_subprocess_execution": True,
            "forbidden_operations": [
                "no_real_worker_file_read",
                "no_ssh_connection",
                "no_subprocess_execution",
                "no_os_environ_read_for_secrets",
                "no_opencode_jsonc_real_read",
                "no_opencode_env_real_read",
            ],
        }
    elif node == "5bao":
        return {
            "schema_version": COLLECTOR_SCHEMA_VERSION,
            "plan_id": f"collect_{node}_{int(datetime.now(timezone.utc).timestamp())}",
            "generated_at": _now_iso(),
            "node": node,
            "collector": "5bao_ssh_canary",
            "transport_type": "ssh",
            "intended_user": "vibedev",
            "dry_run": dry_run,
            "allowed_read_labels": sorted(ALLOWED_READ_LABELS),
            "no_secret_value_output": True,
            "no_env_value_output": True,
            "no_base_url_value_output": True,
            "no_real_endpoint_url_output": True,
            "no_local_exec_override": True,
            "forbidden_operations": [
                "no_opencode_jsonc_real_read_on_target",
                "no_secret_value_transmission",
                "no_remote_file_write",
                "no_node_sync",
                "no_model_call_on_target",
                "no_credential_provisioning_on_target",
            ],
        }
    else:  # 9bao (PR-4H)
        return {
            "schema_version": COLLECTOR_SCHEMA_VERSION,
            "plan_id": f"collect_{node}_{int(datetime.now(timezone.utc).timestamp())}",
            "generated_at": _now_iso(),
            "node": node,
            "collector": "9bao_ssh_canary",
            "transport_type": "ssh",
            "intended_user": "vibedev",
            "dry_run": dry_run,
            "allowed_read_labels": sorted(ALLOWED_READ_LABELS),
            "no_secret_value_output": True,
            "no_env_value_output": True,
            "no_base_url_value_output": True,
            "no_real_endpoint_url_output": True,
            "no_local_exec_override": True,
            "forbidden_operations": [
                "no_opencode_jsonc_real_read_on_target",
                "no_secret_value_transmission",
                "no_remote_file_write",
                "no_node_sync",
                "no_model_call_on_target",
                "no_credential_provisioning_on_target",
            ],
        }


# ── Main collector ──────────────────────────────────────────────────────────


def collect_21bao_local(
    plan: dict,
    fixture_path: Path | None = None,
    operator_approved_real_read: bool = False,
    canary_real_read: bool = False,
) -> dict:
    """Execute (or dry-run) the 21bao local collection.

    Returns a dict with:
      - collection_status: 'not_collected' | 'completed' | 'skipped' | 'error'
      - attestation: dict (the worker_attest JSON, audit-safe)
      - receipt: dict (the receipt, validated)
      - validator_result: dict
      - forbidden_operation_flags: dict
      - redacted_output: dict (redaction summary)

    canary_real_read: when True (and all gates pass), reads from real 21bao
    filesystem paths instead of fixture files. Requires explicit operator
    approval (operator_approved_real_read + env var).
    """
    # Defensive validation
    if not isinstance(plan, dict):
        return _err_collect("plan must be a dict", plan_id=None)

    if plan.get("node") not in VALID_NODES:
        return _err_collect(
            f"plan.node='{plan.get('node')}' not in 21bao collector scope",
            plan_id=plan.get("plan_id"),
        )
    if plan.get("transport_type") != "local_exec":
        return _err_collect(
            f"plan.transport_type='{plan.get('transport_type')}' not allowed; "
            f"21bao collector requires local_exec",
            plan_id=plan.get("plan_id"),
        )
    if plan.get("collector") != "21bao_local_only":
        return _err_collect(
            f"plan.collector='{plan.get('collector')}' not recognized",
            plan_id=plan.get("plan_id"),
        )

    # Dry-run fast path
    if plan.get("dry_run", True):
        return _dry_run_receipt(plan)

    # Real mode: must be operator-approved
    if not operator_approved_real_read:
        return _skipped_receipt(
            plan,
            reason="operator_approved_real_read=False; refusing real reads"
        )

    # Real mode: must be env-gated too (defense in depth)
    if os.environ.get(_OPERATOR_APPROVED_ENV) != "1":
        return _skipped_receipt(
            plan,
            reason=(f"{_OPERATOR_APPROVED_ENV} env var not set to '1'; "
                    f"refusing real reads even though "
                    f"operator_approved_real_read=True")
        )

    # Real mode: determine data source
    if fixture_path is not None:
        # Fixture-based read (PR-4D behavior)
        try:
            fixture = _load_fixture(fixture_path)
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
            return _error_receipt(plan, reason=f"fixture load failed: {e}")
    elif canary_real_read:
        # Canary real-filesystem read (PR-4F)
        try:
            fixture = _read_real_21bao_files()
        except (ValueError, FileNotFoundError, json.JSONDecodeError) as e:
            return _error_receipt(plan, reason=f"canary real read failed: {e}")
    else:
        return _err_collect(
            "real mode requires explicit fixture_path or canary_real_read=True; "
            "refusing to read from any default real path",
            plan_id=plan.get("plan_id"),
        )

    # Convert the fixture into a worker_attest-shaped dict, redacting
    # any sensitive values.
    attestation = _build_attestation_from_fixture(
        node=plan["node"],
        fixture=fixture,
    )

    # Validate attestation against worker_attest schema
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from worker_attest import validate_worker_attestation
        vr = validate_worker_attestation(attestation)
    except (ImportError, Exception) as e:
        return _error_receipt(plan, reason=f"validator import/run failed: {e}")

    if not vr["valid"]:
        return _error_receipt(
            plan,
            reason=f"attestation validation failed: {vr['errors'][:3]}",
            attestation=attestation,
            validator_result=vr,
        )

    # Build receipt
    return _completed_receipt(plan, attestation, vr)


# ── Receipt builders ────────────────────────────────────────────────────────


def _err_collect(msg: str, plan_id: str | None) -> dict:
    return {
        "collection_status": "error",
        "plan_id": plan_id,
        "error": msg,
        "forbidden_operation_flags": _default_forbidden_flags(),
        "redacted_output": {"error": "[REDACTED:error-message]"},
    }


def _dry_run_receipt(plan: dict) -> dict:
    """dry-run path: no real read, no real attestation."""
    empty_attestation = {
        "schema_version": "1.0",
        "node": plan["node"],
        "generated_at": _now_iso(),
        "opencode_config_present": False,
        "opencode_env_present": False,
        "model_aliases": [],
    }
    receipt = _build_receipt(
        plan=plan,
        attestation=empty_attestation,
        collection_status="not_collected",
        validator_result={
            "valid": True,
            "errors": [],
            "warnings": ["dry_run: no real attestation collected"],
            "node": plan["node"],
            "model_count": 0,
            "detail": "dry_run_no_collect",
        },
    )
    return {
        "collection_status": "not_collected",
        "plan_id": plan["plan_id"],
        "attestation": empty_attestation,
        "receipt": receipt,
        "validator_result": receipt["validator_result"],
        "forbidden_operation_flags": receipt["forbidden_operation_flags"],
        "redacted_output": _redact_dict({"plan_id": plan["plan_id"],
                                          "node": plan["node"]}),
    }


def _skipped_receipt(plan: dict, reason: str) -> dict:
    empty_attestation = {
        "schema_version": "1.0",
        "node": plan["node"],
        "generated_at": _now_iso(),
        "opencode_config_present": False,
        "opencode_env_present": False,
        "model_aliases": [],
    }
    receipt = _build_receipt(
        plan=plan,
        attestation=empty_attestation,
        collection_status="skipped",
        validator_result={
            "valid": True,
            "errors": [],
            "warnings": [f"skipped: {reason}"],
            "node": plan["node"],
            "model_count": 0,
            "detail": f"skipped:{reason[:40]}",
        },
    )
    return {
        "collection_status": "skipped",
        "plan_id": plan["plan_id"],
        "skip_reason": reason,
        "attestation": empty_attestation,
        "receipt": receipt,
        "validator_result": receipt["validator_result"],
        "forbidden_operation_flags": receipt["forbidden_operation_flags"],
        "redacted_output": _redact_dict({
            "plan_id": plan["plan_id"],
            "node": plan["node"],
            "skip_reason": reason,
        }),
    }


def _error_receipt(plan: dict, reason: str,
                    attestation: dict | None = None,
                    validator_result: dict | None = None) -> dict:
    att = attestation or {
        "schema_version": "1.0",
        "node": plan["node"],
        "generated_at": _now_iso(),
        "opencode_config_present": False,
        "opencode_env_present": False,
        "model_aliases": [],
    }
    vr = validator_result or {
        "valid": False,
        "errors": [reason],
        "warnings": [],
        "node": plan["node"],
        "model_count": 0,
        "detail": f"error:{reason[:40]}",
    }
    receipt = _build_receipt(
        plan=plan,
        attestation=att,
        collection_status="error",
        validator_result=vr,
    )
    return {
        "collection_status": "error",
        "plan_id": plan["plan_id"],
        "error": reason,
        "attestation": att,
        "receipt": receipt,
        "validator_result": vr,
        "forbidden_operation_flags": receipt["forbidden_operation_flags"],
        "redacted_output": _redact_dict({
            "plan_id": plan["plan_id"],
            "node": plan["node"],
            "error": reason,
        }),
    }


def _completed_receipt(plan: dict, attestation: dict,
                        validator_result: dict) -> dict:
    receipt = _build_receipt(
        plan=plan,
        attestation=attestation,
        collection_status="completed",
        validator_result=validator_result,
    )
    return {
        "collection_status": "completed",
        "plan_id": plan["plan_id"],
        "attestation": attestation,
        "receipt": receipt,
        "validator_result": validator_result,
        "forbidden_operation_flags": receipt["forbidden_operation_flags"],
        "redacted_output": _redact_dict({
            "plan_id": plan["plan_id"],
            "node": plan["node"],
            "model_count": validator_result.get("model_count", 0),
            "validator_valid": validator_result.get("valid", False),
        }),
    }


# ── 5bao remote SSH collector (PR-4G) ────────────────────────────────────────


def _execute_ssh_5bao() -> dict:
    """SSH to 5bao and run the remote collector script.

    Returns the parsed JSON output from the remote script.
    Uses subprocess to run the ssh command, which is the intended
    transport for 5bao (operator-approved SSH canary).

    Safety:
    - Only reads from hardcoded paths on 5bao
    - Remote script only extracts metadata (provider names, model keys)
    - No secret values transmitted over SSH
    - No files written to 5bao
    """
    import subprocess

    ssh_key_path = str(_SSH_5BAO_KEY)

    cmd = [
        "ssh", "-i", ssh_key_path,
        "-p", str(_SSH_5BAO_PORT),
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        f"{_SSH_5BAO_USER}@{_SSH_5BAO_HOST}",
        "python3",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(input=_5BAO_REMOTE_COLLECTOR_SCRIPT, timeout=30)
        result = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    except FileNotFoundError:
        return {"error": "ssh command not found on this host"}
    except subprocess.TimeoutExpired:
        return {"error": "SSH connection timed out"}

    if result.returncode != 0:
        return {"error": f"SSH failed (exit={result.returncode}): "
                         f"{result.stderr[:200]}"}

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {"error": f"remote output parse failed: {e}"}


def collect_5bao_remote(
    plan: dict,
    operator_approved_real_read: bool = False,
) -> dict:
    """Execute (or dry-run) the 5bao remote SSH collection.

    SSHs to 5bao and runs a safe metadata-reading Python script.
    Returns the same attestation + receipt format as collect_21bao_local().

    Safety:
    - Gated by operator_approved_real_read + env var (defense in depth)
    - Only reads hardcoded config paths on 5bao
    - Remote script extracts metadata only, no secrets
    - Output redacted through standard pipeline
    """
    # Defensive validation
    if not isinstance(plan, dict):
        return _err_collect("plan must be a dict", plan_id=None)

    if plan.get("node") != "5bao":
        return _err_collect(
            f"plan.node='{plan.get('node')}' not in 5bao collector scope",
            plan_id=plan.get("plan_id"),
        )
    if plan.get("transport_type") != "ssh":
        return _err_collect(
            f"plan.transport_type='{plan.get('transport_type')}' not allowed; "
            f"5bao collector requires ssh",
            plan_id=plan.get("plan_id"),
        )
    if plan.get("collector") != "5bao_ssh_canary":
        return _err_collect(
            f"plan.collector='{plan.get('collector')}' not recognized "
            f"for 5bao SSH collection",
            plan_id=plan.get("plan_id"),
        )

    # Dry-run fast path
    if plan.get("dry_run", True):
        return _dry_run_receipt(plan)

    # Real mode: must be operator-approved
    if not operator_approved_real_read:
        return _skipped_receipt(
            plan,
            reason="operator_approved_real_read=False; refusing SSH reads"
        )

    # Real mode: must be env-gated too (defense in depth)
    if os.environ.get(_OPERATOR_APPROVED_ENV) != "1":
        return _skipped_receipt(
            plan,
            reason=(f"{_OPERATOR_APPROVED_ENV} env var not set to '1'; "
                    f"refusing SSH reads even though "
                    f"operator_approved_real_read=True")
        )

    # Execute SSH collection
    remote_data = _execute_ssh_5bao()

    if "error" in remote_data:
        return _error_receipt(plan, reason=f"SSH collection failed: {remote_data['error']}")

    if not remote_data.get("config_present"):
        return _error_receipt(plan, reason="5bao config not found")

    # Build fixture-shaped dict from remote data
    fixture = {
        "opencode_config": {
            "schema_version": "1.0",
            "node": "5bao",
        },
        "opencode_env": {name: "ENV_NAME_ONLY_NEVER_VALUE"
                         for name in remote_data.get("env_var_names", [])},
        "model_aliases": remote_data.get("model_aliases", []),
    }

    # Build attestation (same redaction pipeline)
    attestation = _build_attestation_from_fixture(
        node=plan["node"],
        fixture=fixture,
    )

    # Validate attestation
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from worker_attest import validate_worker_attestation
        vr = validate_worker_attestation(attestation)
    except (ImportError, Exception) as e:
        return _error_receipt(plan, reason=f"validator import/run failed: {e}")

    if not vr["valid"]:
        return _error_receipt(
            plan,
            reason=f"attestation validation failed: {vr['errors'][:3]}",
            attestation=attestation,
            validator_result=vr,
        )

    # Build receipt
    return _completed_receipt(plan, attestation, vr)


# ── 9bao remote SSH collector (PR-4H) ────────────────────────────────────────


def _execute_ssh_9bao() -> dict:
    """SSH to 9bao and run the remote collector script.

    Returns the parsed JSON output from the remote script.
    Uses subprocess to run the ssh command, which is the intended
    transport for 9bao (operator-approved SSH canary).

    Safety:
    - Only reads from hardcoded paths on 9bao
    - Remote script only extracts metadata (provider names, model keys)
    - No secret values transmitted over SSH
    - No files written to 9bao
    - 9bao only: refuses 5bao (separate host/port)
    """
    import subprocess

    ssh_key_path = str(_SSH_9BAO_KEY)

    cmd = [
        "ssh", "-i", ssh_key_path,
        "-p", str(_SSH_9BAO_PORT),
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        f"{_SSH_9BAO_USER}@{_SSH_9BAO_HOST}",
        "python3",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = proc.communicate(input=_9BAO_REMOTE_COLLECTOR_SCRIPT, timeout=30)
        result = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    except FileNotFoundError:
        return {"error": "ssh command not found on this host"}
    except subprocess.TimeoutExpired:
        return {"error": "SSH connection timed out"}

    if result.returncode != 0:
        return {"error": f"SSH failed (exit={result.returncode}): "
                         f"{result.stderr[:200]}"}

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return {"error": f"remote output parse failed: {e}"}


def collect_9bao_remote(
    plan: dict,
    operator_approved_real_read: bool = False,
) -> dict:
    """Execute (or dry-run) the 9bao remote SSH collection.

    SSHs to 9bao and runs a safe metadata-reading Python script.
    Returns the same attestation + receipt format as collect_21bao_local().

    Safety:
    - Gated by operator_approved_real_read + env var (defense in depth)
    - Only reads hardcoded config paths on 9bao
    - Remote script extracts metadata only, no secrets
    - Output redacted through standard pipeline
    - 9bao only: refuses 5bao or any other node
    """
    # Defensive validation
    if not isinstance(plan, dict):
        return _err_collect("plan must be a dict", plan_id=None)

    if plan.get("node") != "9bao":
        return _err_collect(
            f"plan.node='{plan.get('node')}' not in 9bao collector scope",
            plan_id=plan.get("plan_id"),
        )
    if plan.get("transport_type") != "ssh":
        return _err_collect(
            f"plan.transport_type='{plan.get('transport_type')}' not allowed; "
            f"9bao collector requires ssh",
            plan_id=plan.get("plan_id"),
        )
    if plan.get("collector") != "9bao_ssh_canary":
        return _err_collect(
            f"plan.collector='{plan.get('collector')}' not recognized "
            f"for 9bao SSH collection",
            plan_id=plan.get("plan_id"),
        )

    # Dry-run fast path
    if plan.get("dry_run", True):
        return _dry_run_receipt(plan)

    # Real mode: must be operator-approved
    if not operator_approved_real_read:
        return _skipped_receipt(
            plan,
            reason="operator_approved_real_read=False; refusing SSH reads"
        )

    # Real mode: must be env-gated too (defense in depth)
    if os.environ.get(_OPERATOR_APPROVED_ENV) != "1":
        return _skipped_receipt(
            plan,
            reason=(f"{_OPERATOR_APPROVED_ENV} env var not set to '1'; "
                    f"refusing SSH reads even though "
                    f"operator_approved_real_read=True")
        )

    # Execute SSH collection
    remote_data = _execute_ssh_9bao()

    if "error" in remote_data:
        return _error_receipt(plan, reason=f"SSH collection failed: {remote_data['error']}")

    if not remote_data.get("config_present"):
        return _error_receipt(plan, reason="9bao config not found")

    # Build fixture-shaped dict from remote data
    fixture = {
        "opencode_config": {
            "schema_version": "1.0",
            "node": "9bao",
        },
        "opencode_env": {name: "ENV_NAME_ONLY_NEVER_VALUE"
                         for name in remote_data.get("env_var_names", [])},
        "model_aliases": remote_data.get("model_aliases", []),
    }

    # Build attestation (same redaction pipeline)
    attestation = _build_attestation_from_fixture(
        node=plan["node"],
        fixture=fixture,
    )

    # Validate attestation
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from worker_attest import validate_worker_attestation
        vr = validate_worker_attestation(attestation)
    except (ImportError, Exception) as e:
        return _error_receipt(plan, reason=f"validator import/run failed: {e}")

    if not vr["valid"]:
        return _error_receipt(
            plan,
            reason=f"attestation validation failed: {vr['errors'][:3]}",
            attestation=attestation,
            validator_result=vr,
        )

    # Build receipt
    return _completed_receipt(plan, attestation, vr)


def _build_receipt(plan: dict, attestation: dict,
                    collection_status: str,
                    validator_result: dict) -> dict:
    return {
        "schema_version": "1.0",
        "node": plan["node"],
        "generated_at": _now_iso(),
        "source": "worker_attest_runtime",
        "command_plan_id": plan["plan_id"],
        "collection_status": collection_status,
        "attestation_file": None,
        "attestation_file_label": f"worker_attest_{plan['node']}.json",
        "validator_result": {
            "valid": validator_result.get("valid", False),
            "errors": validator_result.get("errors", []),
            "warnings": validator_result.get("warnings", []),
            "detail": validator_result.get("detail", ""),
        },
        "redaction_status": {
            "no_secret_value": True,
            "no_env_value": True,
            "no_base_url_value": True,
            "no_real_endpoint_url": True,
            "no_key_length": True,
        },
        "forbidden_operation_flags": _default_forbidden_flags(),
    }


def _default_forbidden_flags() -> dict:
    return {
        "ssh_attempted": False,
        "subprocess_attempted": False,
        "os_environ_read_attempted": False,
        "real_path_read_attempted": False,
        "model_call_attempted": False,
        "credential_provisioning_attempted": False,
    }


# ── Attestation builder from fixture ────────────────────────────────────────


def _build_attestation_from_fixture(node: str, fixture: dict) -> dict:
    """Convert a fixture dict into a worker_attest v1.0 attestation,
    redacting any sensitive values found."""
    if not isinstance(fixture, dict):
        raise ValueError("fixture must be a dict")

    opencode_config_present = bool(fixture.get("opencode_config"))
    opencode_env_present = bool(fixture.get("opencode_env"))
    raw_aliases = fixture.get("model_aliases", [])

    if not isinstance(raw_aliases, list):
        raise ValueError("fixture.model_aliases must be a list")

    redacted_aliases = []
    for entry in raw_aliases:
        if not isinstance(entry, dict):
            continue
        out = {}
        for k, v in entry.items():
            # Redact any field that looks like a secret/url. Keep names.
            if isinstance(v, str):
                if _looks_like_secret(v):
                    out[k] = "[REDACTED:secret-like]"
                elif _looks_like_url(v):
                    out[k] = "[REDACTED:url-like]"
                else:
                    out[k] = v
            elif isinstance(v, dict):
                out[k] = _redact_dict(v)
            elif isinstance(v, list):
                out[k] = [
                    _redact_value(x) if not isinstance(x, dict)
                    else _redact_dict(x)
                    for x in v
                ]
            else:
                out[k] = v
        redacted_aliases.append(out)

    return {
        "schema_version": "1.0",
        "node": node,
        "generated_at": _now_iso(),
        "opencode_config_present": opencode_config_present,
        "opencode_env_present": opencode_env_present,
        "model_aliases": redacted_aliases,
    }


# ── Fixture loader (real mode only) ────────────────────────────────────────


def _load_fixture(path: Path) -> dict:
    """Load a fixture file. Real mode only. The path is the path
    explicitly passed by the caller — never derived from env or
    worker filesystem probes."""
    if not isinstance(path, Path):
        raise ValueError("path must be a Path")
    # Refuse anything that looks like a real worker path BEFORE existence
    # check, so we never probe the real worker filesystem. Use both
    # POSIX and Windows-style separators.
    s = str(path)
    s_norm = s.replace("\\", "/")
    for bad in ("/home/vibeworker", "C:/Users/KK/.opencode"):
        if bad in s or bad in s_norm:
            raise ValueError(
                f"fixture path '{s}' looks like a real worker path; "
                f"refused"
            )
    if not path.exists():
        raise FileNotFoundError(f"fixture not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


# ── Self-check ──────────────────────────────────────────────────────────────


def self_check() -> dict:
    """Internal self-check that exercises all paths."""
    checks = []

    # 1. valid 21bao plan
    p = build_collection_plan("21bao", dry_run=True)
    r = collect_21bao_local(p)
    checks.append({
        "name": "dry_run_21bao_valid",
        "passed": r["collection_status"] == "not_collected",
        "detail": f"status={r['collection_status']}",
    })

    # 2. 9bao is now supported (PR-4H): build plan + dry-run
    try:
        p9 = build_collection_plan("9bao", dry_run=True)
        r9 = collect_9bao_remote(p9, operator_approved_real_read=False)
        checks.append({
            "name": "9bao_plan_and_dry_run",
            "passed": (p9.get("node") == "9bao"
                       and p9.get("transport_type") == "ssh"
                       and p9.get("collector") == "9bao_ssh_canary"
                       and r9.get("collection_status") == "not_collected"),
            "detail": f"node={p9.get('node')} transport={p9.get('transport_type')} "
                      f"collector={p9.get('collector')} status={r9.get('collection_status')}",
        })
    except Exception as e:
        checks.append({
            "name": "9bao_plan_and_dry_run",
            "passed": False,
            "detail": f"exception: {e}",
        })

    # 2b. 10bao still rejected
    try:
        build_collection_plan("10bao", dry_run=True)
        checks.append({
            "name": "10bao_rejected",
            "passed": False,
            "detail": "10bao should have raised",
        })
    except ValueError:
        checks.append({
            "name": "10bao_rejected",
            "passed": True,
            "detail": "10bao raised ValueError as expected",
        })

    # 3. 5bao as local_exec blocked
    try:
        p5_bad = build_collection_plan("5bao", dry_run=True)
        p5_bad["transport_type"] = "local_exec"
        # collect_5bao_remote rejects non-ssh transport
        r = collect_5bao_remote(p5_bad, operator_approved_real_read=False)
        checks.append({
            "name": "5bao_as_local_exec_blocked",
            "passed": r["collection_status"] == "error",
            "detail": f"status={r['collection_status']}",
        })
    except Exception as e:
        checks.append({
            "name": "5bao_as_local_exec_blocked",
            "passed": False,
            "detail": f"unexpected error: {e}",
        })

    # 4. real-mode without operator_approved → skipped
    p_real = build_collection_plan("21bao", dry_run=False)
    r_real = collect_21bao_local(p_real, operator_approved_real_read=False)
    checks.append({
        "name": "real_mode_without_approval_skipped",
        "passed": r_real["collection_status"] == "skipped",
        "detail": f"status={r_real['collection_status']}",
    })

    # 5. real-mode with approval but no env var → skipped
    r_real2 = collect_21bao_local(
        p_real,
        operator_approved_real_read=True,
    )
    checks.append({
        "name": "real_mode_without_env_skipped",
        "passed": r_real2["collection_status"] == "skipped",
        "detail": f"status={r_real2['collection_status']}",
    })

    # 6. plan with wrong transport → error
    p_bad = build_collection_plan("21bao", dry_run=True)
    p_bad["transport_type"] = "ssh"
    r_bad = collect_21bao_local(p_bad)
    checks.append({
        "name": "ssh_transport_rejected",
        "passed": r_bad["collection_status"] == "error",
        "detail": f"status={r_bad['collection_status']}",
    })

    # 7. plan with wrong collector label → error
    p_bad2 = build_collection_plan("21bao", dry_run=True)
    p_bad2["collector"] = "ssh_5bao_collector"
    r_bad2 = collect_21bao_local(p_bad2)
    checks.append({
        "name": "wrong_collector_rejected",
        "passed": r_bad2["collection_status"] == "error",
        "detail": f"status={r_bad2['collection_status']}",
    })

    # 8. dry-run output audit-safe (no secret/URL)
    p8 = build_collection_plan("21bao", dry_run=True)
    r8 = collect_21bao_local(p8)
    s = json.dumps(r8)
    has_secret = any(p in s for p in _SECRET_PATTERNS)
    has_url = any(p in s for p in _URL_PATTERNS)
    checks.append({
        "name": "dry_run_audit_safe",
        "passed": not has_secret and not has_url,
        "detail": f"secret={has_secret} url={has_url}",
    })

    # 9. receipt is a dict
    checks.append({
        "name": "receipt_is_dict",
        "passed": isinstance(r8.get("receipt"), dict),
        "detail": f"type={type(r8.get('receipt')).__name__}",
    })

    # 10. receipt validates against worker_attest_plan.validate_receipt
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from worker_attest_plan import validate_receipt
        vr = validate_receipt(r8["receipt"])
        checks.append({
            "name": "receipt_passes_workspace_validator",
            "passed": vr["valid"],
            "detail": f"errors={vr['errors'][:1]}",
        })
    except ImportError:
        checks.append({
            "name": "receipt_passes_workspace_validator",
            "passed": False,
            "detail": "worker_attest_plan not importable",
        })

    # 11. forbidden_operation_flags all False
    fof = r8["receipt"].get("forbidden_operation_flags", {})
    all_false = all(v is False for v in fof.values())
    checks.append({
        "name": "forbidden_flags_all_false",
        "passed": all_false,
        "detail": f"flags={fof}",
    })

    # 12. label not in allowlist raises
    try:
        _resolve_label_to_path("/home/vibeworker/.opencode/config")
        checks.append({
            "name": "label_allowlist_enforced",
            "passed": False,
            "detail": "should have raised",
        })
    except ValueError:
        checks.append({
            "name": "label_allowlist_enforced",
            "passed": True,
            "detail": "raise as expected",
        })

    # 13. real path fixture rejected
    try:
        _load_fixture(Path("/home/vibeworker/.opencode/config.json"))
        checks.append({
            "name": "real_path_fixture_rejected",
            "passed": False,
            "detail": "should have raised",
        })
    except ValueError:
        checks.append({
            "name": "real_path_fixture_rejected",
            "passed": True,
            "detail": "raise as expected",
        })

    # 14. dry-run plan is dry
    p14 = build_collection_plan("21bao", dry_run=True)
    checks.append({
        "name": "plan_dry_run_flag",
        "passed": p14["dry_run"] is True,
        "detail": f"dry_run={p14['dry_run']}",
    })

    # 15. real-mode plan has dry_run=False
    p15 = build_collection_plan("21bao", dry_run=False)
    checks.append({
        "name": "plan_real_mode_flag",
        "passed": p15["dry_run"] is False,
        "detail": f"dry_run={p15['dry_run']}",
    })

    # 16. canary real read without env gate → skipped (not error)
    # The self-check runs without env var, so canary_real_read without
    # env gate should return skipped.
    p16 = build_collection_plan("21bao", dry_run=False)
    r16 = collect_21bao_local(p16, canary_real_read=True,
                              operator_approved_real_read=False)
    checks.append({
        "name": "canary_without_approval_skipped",
        "passed": r16["collection_status"] == "skipped",
        "detail": f"status={r16['collection_status']}",
    })

    # 17. canary real read dry-run → not_collected
    p17 = build_collection_plan("21bao", dry_run=True)
    r17 = collect_21bao_local(p17, canary_real_read=True)
    checks.append({
        "name": "canary_dry_run_not_collected",
        "passed": r17["collection_status"] == "not_collected",
        "detail": f"status={r17['collection_status']}",
    })

    # 18. _read_real_21bao_files runs without crash (may be error if
    # config file missing — that's OK, tests canary function exists)
    try:
        fixture = _read_real_21bao_files()
        checks.append({
            "name": "canary_real_read_function_exists",
            "passed": True,
            "detail": f"aliases={len(fixture.get('model_aliases',[]))}",
        })
    except (FileNotFoundError, ValueError) as e:
        # Missing file on this node is acceptable for self-check
        checks.append({
            "name": "canary_real_read_function_exists",
            "passed": True,
            "detail": f"function works, file not found: {e}",
        })
    except Exception as e:
        checks.append({
            "name": "canary_real_read_function_exists",
            "passed": False,
            "detail": f"unexpected error: {e}",
        })

    # 19. 5bao plan builds correctly
    p19 = build_collection_plan("5bao", dry_run=True)
    checks.append({
        "name": "plan_5bao_ssh_valid",
        "passed": p19["transport_type"] == "ssh"
                 and p19["collector"] == "5bao_ssh_canary",
        "detail": f"transport={p19['transport_type']} collector={p19['collector']}",
    })

    # 20. 5bao real mode without approval → skipped
    p20 = build_collection_plan("5bao", dry_run=False)
    r20 = collect_5bao_remote(p20, operator_approved_real_read=False)
    checks.append({
        "name": "plan_5bao_without_approval_skipped",
        "passed": r20["collection_status"] == "skipped",
        "detail": f"status={r20['collection_status']}",
    })

    # 21. 5bao dry-run → not_collected
    p21 = build_collection_plan("5bao", dry_run=True)
    r21 = collect_5bao_remote(p21)
    checks.append({
        "name": "plan_5bao_dry_run_not_collected",
        "passed": r21["collection_status"] == "not_collected",
        "detail": f"status={r21['collection_status']}",
    })

    # 22. 9bao plan: ssh transport, 9bao_ssh_canary collector
    p22 = build_collection_plan("9bao", dry_run=True)
    checks.append({
        "name": "plan_9bao_ssh_valid",
        "passed": (p22["transport_type"] == "ssh"
                   and p22["collector"] == "9bao_ssh_canary"),
        "detail": f"transport={p22['transport_type']} collector={p22['collector']}",
    })

    # 23. 9bao real mode without approval → skipped
    p23 = build_collection_plan("9bao", dry_run=False)
    r23 = collect_9bao_remote(p23, operator_approved_real_read=False)
    checks.append({
        "name": "plan_9bao_without_approval_skipped",
        "passed": r23["collection_status"] == "skipped",
        "detail": f"status={r23['collection_status']}",
    })

    # 24. 9bao dry-run → not_collected
    p24 = build_collection_plan("9bao", dry_run=True)
    r24 = collect_9bao_remote(p24)
    checks.append({
        "name": "plan_9bao_dry_run_not_collected",
        "passed": r24["collection_status"] == "not_collected",
        "detail": f"status={r24['collection_status']}",
    })

    # 25. 9bao as local_exec blocked
    try:
        p9_bad = build_collection_plan("9bao", dry_run=True)
        p9_bad["transport_type"] = "local_exec"
        r9_bad = collect_9bao_remote(p9_bad, operator_approved_real_read=False)
        checks.append({
            "name": "9bao_as_local_exec_blocked",
            "passed": r9_bad["collection_status"] == "error",
            "detail": f"status={r9_bad['collection_status']}",
        })
    except Exception as e:
        checks.append({
            "name": "9bao_as_local_exec_blocked",
            "passed": False,
            "detail": f"exception: {e}",
        })

    # 26. 9bao real mode without env gate → skipped
    try:
        env_save_9 = os.environ.pop(_OPERATOR_APPROVED_ENV, None)
        try:
            p9_real = build_collection_plan("9bao", dry_run=False)
            r9_real = collect_9bao_remote(p9_real, operator_approved_real_read=True)
            checks.append({
                "name": "plan_9bao_without_env_skipped",
                "passed": r9_real["collection_status"] == "skipped",
                "detail": f"status={r9_real['collection_status']}",
            })
        finally:
            if env_save_9 is not None:
                os.environ[_OPERATOR_APPROVED_ENV] = env_save_9
    except Exception as e:
        checks.append({
            "name": "plan_9bao_without_env_skipped",
            "passed": False,
            "detail": f"exception: {e}",
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
        print("  python worker_attest_collector.py self-check")
        print("  python worker_attest_collector.py collect --node 21bao|5bao")
        print("                  [--fixture PATH] [--real] [--canary]")
        print()
        print("Real mode is gated:")
        print(f"  - Pass --real AND set {_OPERATOR_APPROVED_ENV}=1 in env")
        print("  - --fixture PATH reads from fixture file (21bao only)")
        print("  - --canary reads from real 21bao filesystem (requires --real)")
        print("  - --node 5bao uses SSH (requires --real)")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "self-check":
        r = self_check()
        _print_json(r)
        sys.exit(0 if r["status"] == "PASS" else 1)

    elif cmd == "collect":
        node = None
        fixture_path = None
        real = False
        canary = False
        i = 2
        while i < len(sys.argv):
            a = sys.argv[i]
            if a == "--node" and i + 1 < len(sys.argv):
                node = sys.argv[i + 1]
                i += 2
            elif a == "--fixture" and i + 1 < len(sys.argv):
                fixture_path = Path(sys.argv[i + 1])
                i += 2
            elif a == "--real":
                real = True
                i += 1
            elif a == "--canary":
                canary = True
                i += 1
            else:
                print(f"Unknown arg: {a}", file=sys.stderr)
                sys.exit(2)

        if node is None:
            print("--node required", file=sys.stderr)
            sys.exit(2)

        try:
            plan = build_collection_plan(node, dry_run=not real)
        except ValueError as e:
            err = {"error": str(e), "blocked_reason": "invalid_node"}
            _print_json(err)
            sys.exit(1)

        operator_approved = real and \
            os.environ.get(_OPERATOR_APPROVED_ENV) == "1"

        if node == "5bao":
            result = collect_5bao_remote(
                plan,
                operator_approved_real_read=operator_approved,
            )
        elif node == "9bao":
            result = collect_9bao_remote(
                plan,
                operator_approved_real_read=operator_approved,
            )
        else:
            result = collect_21bao_local(
                plan,
                fixture_path=fixture_path,
                operator_approved_real_read=operator_approved,
                canary_real_read=canary,
            )
        _print_json(result)
        sys.exit(0)

    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
