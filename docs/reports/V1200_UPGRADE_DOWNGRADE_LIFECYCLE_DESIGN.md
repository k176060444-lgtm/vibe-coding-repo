# V1.20.0 Upgrade/Downgrade Lifecycle Manager Design Report

Version: V1.20.0
Date: 2026-06-19
Branch: feat/v1200-upgrade-downgrade-lifecycle
Base: d7e0585d459b7a8441d61206f6e45e1c48add624
Status: DESIGN_PR_READY

## 1. Objective

Establish formal upgrade/downgrade lifecycle management for the VibeDev
orchestration cluster. This is a design-only deliverable: no real upgrades
or downgrades are executed.

## 2. Deliverables

| File | Type | Description |
|------|------|-------------|
| docs/UPGRADE_DOWNGRADE_LIFECYCLE.md | Design doc | Full lifecycle specification |
| scripts/runtime_inventory.py | Script | Runtime version inventory scanner |
| scripts/upgrade_plan_validate.py | Script | Upgrade plan JSON validator |
| scripts/upgrade_evidence_validate.py | Script | Upgrade evidence JSON validator |
| docs/reports/upgrade-plan-fixture.json | Fixture | Example upgrade plan |
| docs/reports/upgrade-evidence-fixture.json | Fixture | Example upgrade evidence |
| docs/reports/V1200_UPGRADE_DOWNGRADE_LIFECYCLE_DESIGN.md | Report | This file |

## 3. Design Scope

### 3.1 Covered Components

12 component categories defined in UPGRADE_DOWNGRADE_LIFECYCLE.md Section 2.1.

### 3.2 State Machines

Two state machines defined:

- Upgrade: DISCOVER -> PLAN -> APPROVE -> DRAIN -> SNAPSHOT -> CANARY ->
  SMOKE -> FIXTURE -> OBSERVE -> PROMOTE_OR_ROLLBACK -> ATTEST
- Downgrade: DETECT -> FREEZE -> DRAIN -> RESTORE -> VERIFY -> REJOIN -> ATTEST

### 3.3 Robustness Gates

9 gates defined: capacity, drain, rollback, health, version_skew,
sandbox, provider, secret, evidence.

## 4. Current Version Inventory (Baseline Snapshot)

This is a point-in-time snapshot. The runtime_inventory.py script can
generate a fresh inventory.

| Component | Node | Version | Install Method |
|-----------|------|---------|----------------|
| hermes-controller | windows | managed-by-user | config_only |
| qq-gateway | windows | managed-by-user | config_only |
| opencode-runtime | 5bao | 1.17.4 | npm_global |
| opencode-runtime | 9bao | 1.17.4 | npm_global |
| node-runtime | 5bao | v22.x | binary |
| node-runtime | 9bao | v22.22.1 | binary |
| python-runtime | windows | 3.11.15 | system |
| git-runtime | windows | system | system |
| git-runtime | 5bao | system | apt |
| git-runtime | 9bao | system | apt |
| gh-cli | 5bao | 2.23 | apt |
| gh-cli | 9bao | 2.23 | apt |
| bubblewrap | 5bao | not_installed | n/a |
| bubblewrap | 9bao | not_installed | n/a |
| ripgrep | 9bao | 13.0.0 | binary |

Note: "managed-by-user" indicates the component version is controlled
by the operator outside this lifecycle system. These components require
independent operator approval for any version change.

## 5. Evidence Quality Rule

Added as Section 7 of UPGRADE_DOWNGRADE_LIFECYCLE.md. Addresses the
V1.19.0 finding that committed reports contained unexplained
`recomputed_at_commit` placeholders.

Rule: All placeholders (TBD, N/A, pending, unknown, computed_at_commit,
recomputed_at_commit, placeholder) must be classified as either
explained_nonblocking or blocking.

## 6. Validation Results

### 6.1 Script Self-Checks

Each Python script includes a `--self-check` mode that runs internal
validation without external dependencies.

### 6.2 ASCII Scan

All new .md files verified ASCII-only (0 non-ASCII characters).
All new .py files verified ASCII-only.
All new .json files verified ASCII-only.

### 6.3 Secret Scan

No secrets, tokens, API keys, private keys, or authorized_keys content
found in any new file.

### 6.4 Internal Path Scan

No internal IPs (192.168.x.x) found in public docs.
No Windows absolute paths found in public docs.

### 6.5 runtime_code_changed

This PR adds scripts under scripts/ and fixtures under docs/reports/.
The scripts are validation/audit tools, not runtime orchestrator code.
Classification: runtime_code_changed = FALSE.

The scripts do not modify the orchestrator's execution path, scheduling
logic, claim mechanism, or SSH control flow. They are standalone
validators that can be run independently.

## 7. Placeholder Inventory

| Placeholder | Location | Classification | Reason |
|-------------|----------|----------------|--------|
| "managed-by-user" | Section 4, hermes-controller version | explained_nonblocking | Hermes version is operator-managed outside this system |
| "not_installed" | Section 4, bubblewrap | explained_nonblocking | bubblewrap is not installed on workers; installation requires separate operator approval |
| "system" | Section 4, git-runtime install_method | explained_nonblocking | Installed via OS package manager; exact version varies by node |

## 8. Merge Policy

This PR must NOT be merged automatically. It requires:

1. Operator review of design completeness
2. Operator approval of gate definitions
3. Confirmation that no runtime code was modified
4. Confirmation that evidence quality rule is adequate

Merge requires explicit operator approval after review.

## 9. Security Declarations

| Declaration | Value |
|-------------|-------|
| runtime_code_changed | FALSE |
| secrets_exposed | FALSE |
| internal_paths_exposed | FALSE |
| ssh_keys_modified | FALSE |
| credentials_modified | FALSE |
| provider_env_modified | FALSE |
| force_push | FALSE |
| auto_merge | FALSE |
