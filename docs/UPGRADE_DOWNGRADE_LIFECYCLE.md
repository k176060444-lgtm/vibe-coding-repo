# Upgrade / Downgrade Lifecycle Manager

## 1. Overview

This document defines the formal lifecycle management capability for the
VibeDev orchestration cluster. The cluster consists of:

- Windows Controller (Hermes vibedev profile)
- 5bao Debian Executor (vibeworker, active-active)
- 9bao Debian Executor (vibeworker, active-active)

All upgrades, downgrades, rollbacks, canary deployments, version audits,
and robustness protections must follow the procedures defined here.

## 2. Scope

### 2.1 Covered Components

| Component ID | Component | Nodes |
|-------------|-----------|-------|
| hermes-controller | Hermes controller agent | Windows |
| qq-gateway | QQ gateway / scheduled task wrapper | Windows |
| opencode-runtime | OpenCode CLI runtime | 5bao, 9bao |
| node-runtime | Node.js / npm / bun | 5bao, 9bao |
| python-runtime | Python interpreter | 5bao, 9bao, Windows |
| git-runtime | Git | 5bao, 9bao, Windows |
| gh-cli | GitHub CLI | 5bao, 9bao, Windows |
| bubblewrap | bubblewrap sandbox wrapper | 5bao, 9bao |
| ripgrep | ripgrep search tool | 9bao |
| provider-plugin | Model provider plugin/config schema | Windows |
| repo-lifecycle | Repo lifecycle scripts | All |
| report-validator | Report/evidence validators | All |

### 2.2 Excluded from Auto-Upgrade

- SSH keys, authorized_keys, credentials
- Provider API keys, tokens, secrets
- sudoers, sshd_config, sysctl, network config
- Hermes gateway restart (requires independent operator approval)
- System kernel or OS-level packages (requires independent operator approval)

## 3. Version Inventory

Every managed component must have a version inventory record:

```
component      : string   -- component ID from table above
node           : string   -- "windows" | "5bao" | "9bao" | "all"
current_version: string   -- semver or commit SHA
install_path   : string   -- absolute path to binary or package root
install_method : string   -- "npm_global" | "pip" | "apt" | "binary" | "git_clone" | "config_only"
binary_sha256  : string   -- SHA256 of primary binary, if applicable
config_path    : string   -- path to config file (presence only, no content)
secret_ref     : string   -- "present" | "absent" (no content)
last_verified  : ISO8601  -- timestamp of last verification
```

## 4. Upgrade State Machine

```
DISCOVER -> PLAN -> APPROVE -> DRAIN_WORKER -> SNAPSHOT ->
UPGRADE_CANARY -> SMOKE_TEST -> REAL_FIXTURE_TEST ->
OBSERVE -> PROMOTE_OR_ROLLBACK -> ATTEST
```

### 4.1 State Definitions

| State | Description | Gate |
|-------|-------------|------|
| DISCOVER | Detect available new version | None |
| PLAN | Generate upgrade plan with rollback strategy | Plan must include rollback_method |
| APPROVE | Operator reviews and approves plan | operator_approval_required=true |
| DRAIN_WORKER | Wait for active jobs to complete | capacity_gate + drain_gate |
| SNAPSHOT | Record pre-upgrade state (version, SHA, config) | Snapshot must be persisted |
| UPGRADE_CANARY | Apply upgrade to one canary node first | canary_required=true for multi-node |
| SMOKE_TEST | Run basic health checks on canary | health_gate |
| REAL_FIXTURE_TEST | Run fixture-based validation | evidence_gate |
| OBSERVE | Monitor canary for regression period | Timeout-based |
| PROMOTE_OR_ROLLBACK | Either promote to all nodes or rollback | version_skew_gate |
| ATTEST | Generate upgrade evidence report | evidence_gate |

### 4.2 Canary Policy

- Single-component upgrades on multi-node clusters MUST canary one node first.
- Canary observation period: minimum 5 minutes, recommended 15 minutes.
- If canary fails smoke test: immediate rollback, no promotion.
- If canary passes but fixture test fails: rollback, investigate.

## 5. Downgrade State Machine

```
DETECT_REGRESSION -> FREEZE_NEW_JOBS -> DRAIN_WORKER ->
RESTORE_PREVIOUS_VERSION -> VERIFY -> REJOIN_POOL -> ATTEST
```

### 5.1 State Definitions

| State | Description | Gate |
|-------|-------------|------|
| DETECT_REGRESSION | Identify that current version has a defect | Evidence of regression required |
| FREEZE_NEW_JOBS | Stop scheduling new jobs to affected node | capacity_gate |
| DRAIN_WORKER | Wait for active jobs to complete | drain_gate |
| RESTORE_PREVIOUS_VERSION | Install previous known-good version | rollback_gate |
| VERIFY | Run smoke + fixture tests on restored version | health_gate |
| REJOIN_POOL | Return node to active pool | version_skew_gate |
| ATTEST | Generate downgrade evidence report | evidence_gate |

## 6. Robustness Gates

### 6.1 Capacity Gate

At least one healthy worker must remain available during any upgrade or
downgrade operation. If the cluster has N workers, at most N-1 may be
in DRAIN/UPGRADE/DOWNGRADE state simultaneously.

### 6.2 Drain Gate

The target worker must have no active jobs before upgrade/downgrade
begins. Active job detection must use the actual job claim mechanism,
not just PID file presence.

### 6.3 Rollback Gate

No upgrade may proceed unless a verified rollback method exists.
Rollback method types:

- `version_pin`: reinstall previous version from package manager
- `binary_restore`: restore previous binary from snapshot
- `config_restore`: restore previous config from snapshot
- `git_revert`: revert to previous commit

If no rollback method is available, the upgrade must be BLOCKED.

### 6.4 Health Gate

Failed smoke test on canary means:

- No promotion to remaining nodes
- Immediate rollback on canary
- Investigation required before retry

### 6.5 Version Skew Gate

Temporary version skew between nodes is allowed only when:

- Skew duration is bounded (max 30 minutes recommended)
- Evidence of canary health is recorded
- Skew does not affect cross-node review independence

### 6.6 Sandbox Gate

bubblewrap / sandbox wrapper configuration must remain unchanged
during upgrade. If the upgrade modifies sandbox policy, it requires
separate operator approval.

### 6.7 Provider Gate

Model provider smoke test must pass before promotion. This means
actually calling a model with a test prompt and verifying response.

### 6.8 Secret Gate

No upgrade/downgrade operation may:

- Output secret values (API keys, tokens, private keys)
- Modify authorized_keys
- Rotate or delete credentials
- Change provider env values

### 6.9 Evidence Gate

No state may be marked PASS without corresponding evidence. Evidence
must include:

- Timestamp
- Node identifier
- Component and version
- Test command and output (or hash thereof)
- Pass/fail verdict with reasoning

## 7. Evidence Quality Rule

Final committed reports must not contain unexplained placeholders:

- `TBD`
- `N/A`
- `pending`
- `unknown`
- `computed_at_commit`
- `recomputed_at_commit`
- `placeholder`

Each occurrence must be classified as:

- `explained_nonblocking`: documented reason why value is unavailable,
  does not block the deliverable
- `blocking`: value is required and its absence blocks the deliverable

This rule applies to all docs/reports/*.md files in the public repository.

## 8. Rollback Procedures

### 8.1 OpenCode Rollback

```
1. Record current version and binary SHA256
2. DRAIN_WORKER: wait for active job completion
3. Install previous version via npm
4. Verify binary SHA256 matches expected
5. Run opencode --version
6. Run smoke test (model call)
7. REJOIN_POOL
```

### 8.2 Hermes Controller Rollback

```
1. Record current version and profile state
2. Stop new task scheduling (cron pause)
3. Wait for active sessions to complete
4. Restore previous profile snapshot
5. Restart gateway (requires operator approval)
6. Verify gateway connectivity
7. Resume task scheduling
```

### 8.3 Node.js Runtime Rollback

```
1. Record current version
2. DRAIN_WORKER
3. Restore previous Node.js binary
4. Verify node --version
5. Run npm/opencode smoke test
6. REJOIN_POOL
```

## 9. Audit Trail

Every upgrade/downgrade operation must produce an evidence record
containing:

- operation_id: unique identifier
- component: component ID
- node: target node
- from_version: version before operation
- to_version: version after operation (or "rollback" target)
- operation_type: "upgrade" | "downgrade" | "rollback"
- state_machine_trace: ordered list of states traversed
- gate_results: pass/fail for each gate checked
- evidence_sha256: SHA256 of the evidence file
- operator_approval: true/false + approver identity
- timestamp: ISO8601

## 10. Security Constraints

1. All operations must be fail-closed.
2. No automatic fallback may bypass capability, capacity, role separation,
   or gate checks.
3. Public repository must never contain secrets, credentials, runtime state,
   internal evidence bundles, sensitive topology, or private key paths.
4. All code modifications must follow branch -> review -> PR -> merge flow.
5. Force push and force reset are prohibited.
6. OpenCode version changes require explicit operator approval per the
   frozen baseline constraint.
