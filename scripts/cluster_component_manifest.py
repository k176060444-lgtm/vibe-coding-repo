#!/usr/bin/env python3
"""Cluster Component Manifest v1.0.0

Read-only manifest of all cluster components with their upgrade class,
version, state/program paths (aliased), and upgrade readiness.

Usage:
    python scripts/cluster_component_manifest.py --list
    python scripts/cluster_component_manifest.py --self-check
    python scripts/cluster_component_manifest.py --json
"""

__version__ = "1.0.0"

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


# --- Upgrade Classes ---

class UpgradeClass(str, Enum):
    PLATFORM = "platform"      # Hermes controller — full backup + operator approval
    RUNTIME = "runtime"        # OpenCode engine — binary swap + validation
    WORKFLOW = "workflow"      # Runner/scheduler/registry — git revert
    CONFIG = "config"          # Provider/network config — file backup
    SYSTEM = "system"          # Node/npm/Python/Git/gh — system-managed


class ComponentRole(str, Enum):
    CONTROLLER = "controller"
    ENGINE = "engine"
    RUNNER = "runner"
    REGISTRY = "registry"
    SCHEDULER = "scheduler"
    CONFIG = "config"
    RUNTIME_DEP = "runtime_dep"


# --- Protocol Versions ---

CONTROLLER_PROTOCOL_VERSION = "1.0"
WORKER_REGISTRY_SCHEMA_VERSION = "1.1"
RUNNER_PROTOCOL_VERSION = "1.0"
APPROVAL_GATE_SEMANTICS_VERSION = "1.1"
SCHEDULER_ROUTING_SCHEMA_VERSION = "1.0"


# --- Component Definitions ---

@dataclass
class ComponentEntry:
    component: str
    role: str
    version: str
    upgrade_class: str
    program_path_alias: str
    state_path_alias: str
    rollback_available: bool
    enabled: bool
    manual_only: bool
    protocol_version: str
    notes: str = ""


# Aliased paths — NO real secrets/domains/IPs
_PATH_ALIASES = {
    "hermes_controller": "$HERMES_PROFILE/",
    "hermes_config": "$HERMES_PROFILE/config/",
    "opencode_engine": "$OPENCODE_INSTALL/",
    "opencode_config": "$OPENCODE_CONFIG/",
    "runner_windows": "$REPO/scripts/",
    "runner_debian_ssh": "$REPO/scripts/",
    "registry": "$REPO/scripts/",
    "scheduler": "$REPO/scripts/",
    "provider_config": "$OPENCODE_CONFIG/opencode.env",
    "network_fallback": "$REGISTRY_CONFIG/",
    "node_runtime": "$SYSTEM/",
    "npm_runtime": "$SYSTEM/",
    "python_runtime": "$SYSTEM/",
    "git_runtime": "$SYSTEM/",
    "gh_runtime": "$SYSTEM/",
    "state_evidence": "$STATE/evidence/",
    "state_logs": "$STATE/logs/",
    "state_worktrees": "$STATE/worktrees/",
    "state_approval": "$STATE/approval/",
}

# Per-component state path aliases for separation
_STATE_PATH_MAP = {
    "hermes-controller": "$HERMES_PROFILE/ (queue, config, plugins, skills, memories)",
    "opencode-engine-5bao": "$WORKER_STATE/5bao/ (worktrees, evidence, logs, cache)",
    "opencode-engine-9bao": "$WORKER_STATE/9bao/ (worktrees, evidence, logs, cache)",
    "opencode-engine-21bao": "$WORKER_STATE/21bao/ (worktrees, evidence, logs)",
    "windows-local-runner": "$WORKTREE/ (evidence, logs, lock, process state)",
    "debian-ssh-runner": "$WORKTREE/ (evidence, logs, lock, process state)",
    "worker-registry": "$REPO/scripts/vibe_worker_registry.py (config + in-memory state)",
    "scheduler-policy": "$REPO/scripts/vibe_scheduler_policy.py (routing + lock state)",
    "model-provider-config": "$OPENCODE_CONFIG/ (env, jsonc, provider entries)",
    "network-fallback-endpoints": "$REGISTRY_CONFIG/ (endpoint list, health state)",
    "node-runtime": "$SYSTEM/node_modules/",
    "npm-runtime": "$SYSTEM/npm/",
    "python-runtime": "$SYSTEM/python/",
    "git-runtime": "$SYSTEM/git/",
    "gh-runtime": "$SYSTEM/gh/",
}


def get_component_manifest() -> list[ComponentEntry]:
    """Return the current cluster component manifest."""
    return [
        ComponentEntry(
            component="hermes-controller",
            role=ComponentRole.CONTROLLER.value,
            version="current",
            upgrade_class=UpgradeClass.PLATFORM.value,
            program_path_alias="$HERMES_INSTALL/",
            state_path_alias=_STATE_PATH_MAP["hermes-controller"],
            rollback_available=True,
            enabled=True,
            manual_only=False,
            protocol_version=CONTROLLER_PROTOCOL_VERSION,
            notes="Hermes Agent controller; platform-level upgrade requires full backup + operator approval"
        ),
        ComponentEntry(
            component="opencode-engine-5bao",
            role=ComponentRole.ENGINE.value,
            version="1.17.8",
            upgrade_class=UpgradeClass.RUNTIME.value,
            program_path_alias="$OPENCODE_INSTALL/5bao/",
            state_path_alias=_STATE_PATH_MAP["opencode-engine-5bao"],
            rollback_available=True,
            enabled=True,
            manual_only=False,
            protocol_version=RUNNER_PROTOCOL_VERSION,
            notes="OpenCode 1.17.8 on Debian 5bao; SHA256=ea9f0e72..."
        ),
        ComponentEntry(
            component="opencode-engine-9bao",
            role=ComponentRole.ENGINE.value,
            version="1.17.8",
            upgrade_class=UpgradeClass.RUNTIME.value,
            program_path_alias="$OPENCODE_INSTALL/9bao/",
            state_path_alias=_STATE_PATH_MAP["opencode-engine-9bao"],
            rollback_available=True,
            enabled=True,
            manual_only=False,
            protocol_version=RUNNER_PROTOCOL_VERSION,
            notes="OpenCode 1.17.8 on Debian 9bao; SHA256=ea9f0e72..."
        ),
        ComponentEntry(
            component="opencode-engine-21bao",
            role=ComponentRole.ENGINE.value,
            version="1.17.8",
            upgrade_class=UpgradeClass.RUNTIME.value,
            program_path_alias="$OPENCODE_INSTALL/21bao/",
            state_path_alias=_STATE_PATH_MAP["opencode-engine-21bao"],
            rollback_available=True,
            enabled=False,
            manual_only=True,
            protocol_version=RUNNER_PROTOCOL_VERSION,
            notes="OpenCode 1.17.8 on Windows 21bao; SHA256=5fa54e6d...; manual-only, not auto-scheduled"
        ),
        ComponentEntry(
            component="windows-local-runner",
            role=ComponentRole.RUNNER.value,
            version="1.0.0",
            upgrade_class=UpgradeClass.WORKFLOW.value,
            program_path_alias="$REPO/scripts/vibe_windows_local_runner.py",
            state_path_alias=_STATE_PATH_MAP["windows-local-runner"],
            rollback_available=True,
            enabled=False,
            manual_only=True,
            protocol_version=RUNNER_PROTOCOL_VERSION,
            notes="Windows local-exec runner for 21bao; path allowlist D:\\+E:\\; blocklist controller repo"
        ),
        ComponentEntry(
            component="debian-ssh-runner",
            role=ComponentRole.RUNNER.value,
            version="1.0.0",
            upgrade_class=UpgradeClass.WORKFLOW.value,
            program_path_alias="$REPO/scripts/ (SSH dispatch via vibe_toolchain_lifecycle.py)",
            state_path_alias=_STATE_PATH_MAP["debian-ssh-runner"],
            rollback_available=True,
            enabled=True,
            manual_only=False,
            protocol_version=RUNNER_PROTOCOL_VERSION,
            notes="SSH-based runner for 5bao/9bao Debian workers"
        ),
        ComponentEntry(
            component="worker-registry",
            role=ComponentRole.REGISTRY.value,
            version="1.3.0",
            upgrade_class=UpgradeClass.WORKFLOW.value,
            program_path_alias="$REPO/scripts/vibe_worker_registry.py",
            state_path_alias=_STATE_PATH_MAP["worker-registry"],
            rollback_available=True,
            enabled=True,
            manual_only=False,
            protocol_version=WORKER_REGISTRY_SCHEMA_VERSION,
            notes="Worker node registry with transport field; 3 nodes registered"
        ),
        ComponentEntry(
            component="scheduler-policy",
            role=ComponentRole.SCHEDULER.value,
            version="1.3.0",
            upgrade_class=UpgradeClass.WORKFLOW.value,
            program_path_alias="$REPO/scripts/vibe_scheduler_policy.py",
            state_path_alias=_STATE_PATH_MAP["scheduler-policy"],
            rollback_available=True,
            enabled=True,
            manual_only=False,
            protocol_version=SCHEDULER_ROUTING_SCHEMA_VERSION,
            notes="Transport-aware routing; unknown transport fail-closed"
        ),
        ComponentEntry(
            component="model-provider-config",
            role=ComponentRole.CONFIG.value,
            version="1.0.0",
            upgrade_class=UpgradeClass.CONFIG.value,
            program_path_alias="$OPENCODE_CONFIG/opencode.jsonc",
            state_path_alias=_STATE_PATH_MAP["model-provider-config"],
            rollback_available=True,
            enabled=True,
            manual_only=False,
            protocol_version="1.0",
            notes="Provider model routing policy; 4 providers configured"
        ),
        ComponentEntry(
            component="network-fallback-endpoints",
            role=ComponentRole.CONFIG.value,
            version="1.0.0",
            upgrade_class=UpgradeClass.CONFIG.value,
            program_path_alias="$REGISTRY_CONFIG/",
            state_path_alias=_STATE_PATH_MAP["network-fallback-endpoints"],
            rollback_available=True,
            enabled=True,
            manual_only=False,
            protocol_version="1.0",
            notes="Worker SSH endpoint registry; primary+fallback addresses per node"
        ),
    ]


# --- Contract Versions (for validation) ---

KNOWN_PROTOCOL_VERSIONS = {
    "controller_protocol": CONTROLLER_PROTOCOL_VERSION,
    "worker_registry_schema": WORKER_REGISTRY_SCHEMA_VERSION,
    "runner_protocol": RUNNER_PROTOCOL_VERSION,
    "approval_gate_semantics": APPROVAL_GATE_SEMANTICS_VERSION,
    "scheduler_routing_schema": SCHEDULER_ROUTING_SCHEMA_VERSION,
}


def get_protocol_versions() -> dict:
    """Return all known protocol versions."""
    return dict(KNOWN_PROTOCOL_VERSIONS)


# --- Self-Check ---

def self_check() -> dict:
    """Validate manifest integrity."""
    checks = []
    manifest = get_component_manifest()

    # 1. All entries have required fields
    required = ["component", "role", "version", "upgrade_class",
                "program_path_alias", "state_path_alias", "rollback_available",
                "enabled", "manual_only", "protocol_version"]
    all_have_fields = all(
        all(hasattr(e, f) for f in required)
        for e in manifest
    )
    checks.append({"name": "all_entries_have_required_fields", "passed": all_have_fields})

    # 2. No real secrets/domains/IPs in aliases
    import re
    real_patterns = [r'token', r'secret', r'api_key', r'password',
                     r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}',
                     r'\.top\b', r'\.vip\b']
    found_real = []
    for entry in manifest:
        for f in ["program_path_alias", "state_path_alias", "notes"]:
            val = str(getattr(entry, f, ""))
            for pat in real_patterns:
                if re.search(pat, val, re.IGNORECASE):
                    found_real.append(f"{entry.component}.{f}: pattern={pat}")
    checks.append({"name": "no_real_secrets_in_manifest", "passed": len(found_real) == 0,
                   "details": found_real if found_real else None})

    # 3. 21bao is disabled + manual_only
    bao21 = [e for e in manifest if "21bao" in e.component]
    bao21_ok = all(not e.enabled and e.manual_only for e in bao21) if bao21 else False
    checks.append({"name": "21bao_disabled_manual_only", "passed": bao21_ok})

    # 4. Upgrade classes are valid
    valid_classes = {c.value for c in UpgradeClass}
    all_classes_valid = all(e.upgrade_class in valid_classes for e in manifest)
    checks.append({"name": "valid_upgrade_classes", "passed": all_classes_valid})

    # 5. All components have rollback_available
    all_rollback = all(e.rollback_available for e in manifest)
    checks.append({"name": "all_rollback_available", "passed": all_rollback})

    # 6. Protocol versions defined
    all_proto = all(e.protocol_version for e in manifest)
    checks.append({"name": "all_protocol_versions_defined", "passed": all_proto})

    # 7. Component count
    checks.append({"name": "component_count_10", "passed": len(manifest) == 10})

    # 8. No real IP addresses
    checks.append({"name": "no_real_ip_addresses",
                   "passed": len(found_real) == 0})

    passed = all(c["passed"] for c in checks)
    return {"passed": passed, "version": __version__, "checks": checks}


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(prog="cluster_component_manifest")
    parser.add_argument("--list", action="store_true", help="List all components")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--self-check", action="store_true", help="Run self-check")
    args = parser.parse_args()

    if args.self_check:
        result = self_check()
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["passed"] else 1)

    manifest = get_component_manifest()

    if args.json:
        print(json.dumps([asdict(e) for e in manifest], indent=2))
    elif args.list:
        print(f"{'Component':<30} {'Role':<12} {'Version':<10} {'Class':<10} {'Enabled':<8} {'Manual':<8} {'Protocol':<10}")
        print("-" * 98)
        for e in manifest:
            print(f"{e.component:<30} {e.role:<12} {e.version:<10} {e.upgrade_class:<10} "
                  f"{str(e.enabled):<8} {str(e.manual_only):<8} {e.protocol_version:<10}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
