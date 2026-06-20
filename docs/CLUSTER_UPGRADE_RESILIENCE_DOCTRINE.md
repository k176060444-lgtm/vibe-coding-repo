# Cluster Upgrade Resilience Doctrine

**Version:** 1.0.0
**Scope:** VibeDev small cluster (Hermes controller + OpenCode workers)
**Status:** Architecture policy — no real upgrade executed

---

## 1. Core Principles

### 1.1 Program-State Separation

Every upgradeable component MUST separate **replaceable programs** from **persistent state**.

| Category | Examples | Upgrade Rule |
|---|---|---|
| **Replaceable Programs** | Hermes binary, OpenCode binary, runner scripts, runtime deps | Safe to replace; old version preserved until promotion |
| **Persistent State** | Job queue, work-order state, locks, evidence, logs, config, worktrees, approval records | NEVER deleted or overwritten during upgrade |

**Invariant:** An upgrade that mutates persistent state paths is a STATE MIGRATION, not a program upgrade. State migrations require explicit operator approval.

### 1.2 Version Parallel Layout

```
<component>/
  releases/
    <version>/          # immutable after install
      bin/
      config/
    current -> <version>   # symlink/junction
    previous -> <version>  # last known-good
    candidate -> <version> # under validation
```

- `current` = active version serving traffic
- `previous` = rollback target
- `candidate` = being validated, NOT serving traffic
- Promotion: `candidate` → `current`, old `current` → `previous`
- Rollback: `previous` → `current`

### 1.3 Promotion Gate

A candidate version MAY be promoted to `current` ONLY when ALL pass:

| Gate | Description |
|---|---|
| **Health PASS** | `health_probe()` returns healthy |
| **Contract PASS** | Protocol/schema version compatible |
| **Safety PASS** | No secret exposure, no unauthorized state mutation |
| **Feature Flag** | New capabilities default to `disabled`/`manual_only` |

### 1.4 Rollback Safety

- Rollback MUST NOT delete evidence, logs, state, or approval records
- Rollback MUST preserve the ability to re-attempt promotion
- Rollback target (`previous`) MUST be a known-good version
- If `previous` is missing or corrupt, promotion is BLOCKED

### 1.5 Feature Flag / Manual-Only Default

New components (workers, providers, schedulers, fallback mechanisms) MUST start as:
- `enabled = false`
- `manual_only = true`

Graduation path (each requires operator approval):
1. `enabled=true, manual_only=true` — can be triggered manually
2. `enabled=true, manual_only=false` — enters automatic scheduling
3. Full integration — participates in all dispatch paths

### 1.6 Fail-Closed but Recoverable

| Failure Mode | Behavior |
|---|---|
| Unknown protocol version | REJECT, do not dispatch |
| Missing required field | REJECT, do not dispatch |
| Health check FAIL | BLOCK promotion |
| Contract check FAIL | BLOCK promotion |
| Upgrade script crash | Preserve current, log error, allow retry |
| Provider unavailable | Log, cooldown, allow manual override |

**Recoverable means:** After any failure, the system MUST retain:
- Health/status reporting capability
- Reconciliation/diagnostic capability
- Rollback capability
- Manual override capability (operator-gated)

### 1.7 Compatibility Contract

Every inter-component interface defines a **protocol version**:

| Contract | Scope |
|---|---|
| `controller_protocol_version` | Hermes controller ↔ worker dispatch |
| `worker_registry_schema_version` | Registry data model |
| `runner_protocol_version` | Runner ↔ OpenCode invocation |
| `approval_gate_semantics` | Merge guard SHA binding, method enforcement |
| `scheduler_routing_schema` | Transport routing, capability matching |

When a contract version is unrecognized: **fail-closed, do not dispatch.**

### 1.8 Per-Component Upgrade Classification

| Component | Upgrade Class | Rollback Target | State Paths |
|---|---|---|---|
| Hermes controller | PLATFORM | previous binary + config | ~/.hermes/profiles/ |
| OpenCode engine | RUNTIME | previous binary | opencode install dir |
| Windows local runner | WORKFLOW | git revert | worktrees, evidence, logs |
| Debian SSH runner | WORKFLOW | git revert | worktrees, evidence, logs |
| Scheduler/Registry | WORKFLOW | git revert | in-memory + config |
| Model provider config | CONFIG | env file backup | opencode.env, jsonc |
| Network fallback | CONFIG | config file backup | registry config |
| Node/npm/Python/Git/gh | SYSTEM | system package manager | N/A (system-managed) |

---

## 2. Upgrade Lifecycle

```
[Install Candidate] → [Validate] → [Promote] → [Monitor] → [Stable]
                            ↓              ↓           ↓
                      [BLOCK/RETRY]  [ROLLBACK]  [ROLLBACK]
```

1. **Install Candidate**: Deploy new version to `candidate` path
2. **Validate**: Run health + contract + safety gates
3. **Promote**: If all gates pass, swap `current` ↔ `candidate`
4. **Monitor**: Observe post-promotion health
5. **Stable**: Demote old `current` to `previous`

At any stage, if validation fails:
- Do NOT proceed to next stage
- Log failure reason
- Preserve current version
- Allow operator to retry or rollback

---

## 3. Anti-Patterns (Forbidden)

| Anti-Pattern | Why Forbidden |
|---|---|
| In-place overwrite | Loses rollback capability |
| Auto-promote on install | Bypasses validation gates |
| Delete state on upgrade | Violates program-state separation |
| Silent version drift | Undetectable compatibility break |
| Auto-enable new features | Bypasses manual-only graduation |
| Force push during upgrade | Destroys audit trail |
| Upgrade without backup | No recovery path |

---

## 4. Decision Matrix

| Scenario | Action |
|---|---|
| OpenCode new version available | Install to candidate, validate, promote with operator approval |
| Hermes needs update | PLATFORM class: full backup, candidate validation, operator approval |
| New worker node joining | Manual-only, dry-run, operator graduation |
| Provider rate limiting | Cooldown, fallback chain, no auto-promote to paid |
| Network fallback change | Config class: backup, validate, operator approval |
| Runtime dep (Node/Python) update | SYSTEM class: managed outside cluster, contract re-validate |

---

*This document is a policy reference. Implementation follows in companion scripts.*
