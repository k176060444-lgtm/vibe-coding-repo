# Model Pool Distribution Contract

**Version:** 1.0.0
**Effective:** 2026-06-24
**Authority:** Operator-validated, auditable
**Parent Contract:** [VIBE_CODING_WORKFLOW_CONTRACT.md](./VIBE_CODING_WORKFLOW_CONTRACT.md)

---

## Purpose

This contract defines the **governance, schema, and distribution rules** for the dynamic model pool used in Vibe Coding orchestration. It ensures:

- Model lifecycle (add/delete/enable/disable) is centrally governed by the Orchestrator
- No plaintext secrets ever enter the model registry, Git, PRs, logs, or reports
- Node-specific configuration is generated via a dry-run renderer with operator approval
- Only truly available models appear as execution candidates

---

## 1. Architecture

The model pool distribution system consists of six components:

```
┌─────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                             │
│  Central governance: add / delete / enable / disable / distribute│
└────────┬──────────────┬──────────────┬──────────────┬───────────┘
         │              │              │              │
         ▼              ▼              ▼              ▼
┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
│   MODEL    │  │  SECRET    │  │  OPENCODE  │  │   NODE     │
│  REGISTRY  │  │  BROKER    │  │  CONFIG    │  │   SYNC     │
│            │  │            │  │  RENDERER  │  │            │
│ metadata   │  │ secret_ref │  │ dry-run    │  │ operator   │
│ only       │  │ + status   │  │ config     │  │ authorized │
│            │  │            │  │ generation │  │ delivery   │
└────────────┘  └────────────┘  └────────────┘  └────────────┘
         │              │              │              │
         └──────────────┴──────────────┴──────────────┘
                              │
                              ▼
                     ┌────────────────┐
                     │   AUDIT LOG    │
                     │                │
                     │ all mutations  │
                     │ all approvals  │
                     │ all distributions│
                     └────────────────┘
```

### 1.1 Orchestrator
- **Role:** Sole governance authority for model pool mutations
- **Responsibilities:** Validates add/delete/enable/disable requests; enforces policy; coordinates distribution
- **Constraint:** Cannot self-approve; requires operator confirmation for high-risk actions

### 1.2 Model Registry
- **Role:** Persistent store for model metadata
- **Constraint:** Stores ONLY non-secret metadata; never stores plaintext keys, tokens, or credentials

### 1.3 Secret Broker
- **Role:** Manages secret references and credential status
- **Constraint:** Exposes only `secret_ref` identifiers and `credential_status`; never exposes actual key values

### 1.4 OpenCode Config Renderer
- **Role:** Generates per-node OpenCode configuration drafts
- **Constraint:** Produces dry-run output only; uses `secret_ref` placeholders or node-local secure storage references

### 1.5 Node Sync
- **Role:** Delivers configuration to target nodes
- **Constraint:** Requires explicit operator authorization before any delivery

### 1.6 Audit Log
- **Role:** Immutable record of all model pool operations
- **Contents:** Timestamps, operator IDs, action types, affected models, approval IDs, outcomes

---

## 2. Model Registry Schema

Each model entry in the registry contains the following fields:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model_id` | string | Yes | Unique identifier (e.g., `opencode/mimo-v2.5-free`) |
| `provider` | string | Yes | Provider name (e.g., `opencode`, `deepseek`, `xiaomi`) |
| `alias` | string | Yes | Human-readable alias (e.g., `mimo-free`) |
| `endpoint` | string | No | API endpoint URL (non-secret) |
| `protocol` | string | Yes | Protocol type (e.g., `openai-compatible`, `custom`) |
| `allowed_nodes` | list[string] | Yes | Nodes permitted to use this model |
| `allowed_roles` | list[string] | Yes | Roles permitted to use this model (e.g., `implementer`, `reviewer`) |
| `enabled` | boolean | Yes | Whether model is currently enabled |
| `source` | string | Yes | Discovery source (e.g., `opencode-free`, `opencode-go`, `manual`) |
| `cost_status` | string | Yes | Cost classification (e.g., `free`, `paid`, `unknown`) |
| `health_status` | string | Yes | Health status (e.g., `healthy`, `degraded`, `unhealthy`, `unknown`) |
| `quarantine_status` | string | Yes | Quarantine state (e.g., `none`, `quarantined`, `pending-review`) |
| `secret_ref` | string | No | Reference to secret in Secret Broker (e.g., `secret:deepseek:api-key`) |
| `credential_status` | string | Yes | Credential state (e.g., `valid`, `expired`, `missing`, `not-configured`) |

**Critical:** The `secret_ref` field is a **reference identifier only**. It MUST NOT contain actual key material.

### 2.1 Example Entry (Non-Secret)

```json
{
  "model_id": "opencode/mimo-v2.5-free",
  "provider": "opencode",
  "alias": "mimo-free",
  "endpoint": "https://api.opencode.example.com/v1",
  "protocol": "openai-compatible",
  "allowed_nodes": ["21bao", "5bao", "9bao"],
  "allowed_roles": ["implementer", "reviewer"],
  "enabled": true,
  "source": "opencode-free",
  "cost_status": "free",
  "health_status": "healthy",
  "quarantine_status": "none",
  "secret_ref": "secret:opencode:mimo-free-token",
  "credential_status": "valid"
}
```

---

## 3. Secret Broker Contract

### 3.1 Interface

The Secret Broker exposes exactly two operations:

| Operation | Input | Output | Description |
|-----------|-------|--------|-------------|
| `resolve_status` | `secret_ref` | `credential_status` | Returns credential state without exposing key |
| `get_secret_ref` | `provider` + `alias` | `secret_ref` | Returns secret reference identifier |

### 3.2 Credential Status Values

| Status | Meaning | Action Allowed |
|--------|---------|----------------|
| `valid` | Credential exists and is not expired | Model can be used |
| `expired` | Credential exists but has expired | Model blocked; renewal required |
| `missing` | No credential found for this model | Model blocked; configuration required |
| `not-configured` | Model does not require credentials | Model can be used (free tier) |

### 3.3 Prohibited Operations

The Secret Broker MUST NOT:
- Return actual key values via any API
- Log key values
- Include key values in error messages
- Expose keys via debug endpoints

### 3.4 Secret Reference Format

```
secret:<provider>:<identifier>
```

Examples:
- `secret:deepseek:api-key`
- `secret:xiaomi:api-key`
- `secret:opencode:mimo-free-token`

---

## 4. OpenCode Config Renderer Dry-Run

### 4.1 Purpose

The OpenCode Config Renderer generates per-node configuration drafts. It operates in **dry-run mode only** during this phase — no configuration is actually delivered to nodes.

### 4.2 Input

```json
{
  "target_node": "21bao",
  "available_models": [
    {
      "model_id": "opencode/mimo-v2.5-free",
      "alias": "mimo-free",
      "secret_ref": "secret:opencode:mimo-free-token"
    }
  ],
  "dry_run": true
}
```

### 4.3 Output (Dry-Run)

```json
{
  "node": "21bao",
  "dry_run": true,
  "config_draft": {
    "models": [
      {
        "alias": "mimo-free",
        "provider": "opencode",
        "endpoint": "https://api.opencode.example.com/v1",
        "secret_ref": "secret:opencode:mimo-free-token",
        "credential_source": "node-local-secure-storage"
      }
    ]
  },
  "warnings": [],
  "requires_operator_approval": true
}
```

### 4.4 Key Rules

1. **No plaintext keys** in output — use `secret_ref` or `credential_source` placeholders
2. **Always requires operator approval** before any node delivery
3. **Dry-run flag** must be explicitly set to `true` during design phase
4. **Node-local secure storage** is the preferred credential source for production

---

## 5. Model Lifecycle Workflows

### 5.1 Add Model

```
Operator request → Orchestrator validates → Registry entry created → Audit log → Operator confirms
```

**Steps:**
1. Operator provides model metadata (no secrets)
2. Orchestrator validates: unique `model_id`, valid `provider`, valid `allowed_nodes`
3. Registry entry created with `enabled: false` (pending activation)
4. Secret Broker assigns `secret_ref` (if credentials required)
5. Orchestrator reports to operator
6. Operator confirms activation → `enabled: true`

### 5.2 Delete Model

```
Operator request → Orchestrator checks usage → Registry entry removed → Audit log → Operator confirms
```

**Steps:**
1. Operator requests deletion
2. Orchestrator checks: no active jobs using this model
3. Registry entry removed
4. Secret Broker revokes `secret_ref` (if exists)
5. Audit log records deletion

### 5.3 Enable Model

```
Operator request → Orchestrator validates → Registry entry updated → Audit log
```

**Steps:**
1. Operator requests enable
2. Orchestrator validates: `credential_status` is `valid` or `not-configured`
3. Registry entry updated: `enabled: true`
4. Audit log records change

### 5.4 Disable Model

```
Operator request → Orchestrator updates → Registry entry updated → Audit log
```

**Steps:**
1. Operator requests disable
2. Orchestrator updates: `enabled: false`
3. Registry entry updated
4. Audit log records change

---

## 6. Per-Node Distribution Workflow

```
Orchestrator prepares config → Config Renderer generates draft → Operator reviews → Operator approves → Node Sync delivers
```

### 6.1 Steps

1. **Prepare:** Orchestrator identifies target node and available models
2. **Render:** Config Renderer generates dry-run configuration draft
3. **Review:** Operator reviews draft configuration
4. **Approve:** Operator explicitly authorizes delivery
5. **Deliver:** Node Sync delivers configuration to target node
6. **Verify:** Node confirms receipt; audit log records delivery

### 6.2 Constraints

- Node Sync MUST NOT execute without explicit operator approval
- Each node delivery requires separate approval
- Batch delivery requires explicit batch approval with node list

---

## 7. Operator Approval Boundaries

| Action | Approval Required | Escalation |
|--------|-------------------|------------|
| Add model (enabled: false) | Yes | None |
| Activate model (enabled: true) | Yes | None |
| Delete model | Yes | Operator confirms no active usage |
| Enable model | Yes | Orchestrator validates credentials |
| Disable model | Yes | None |
| Node config delivery | Yes | Per-node or explicit batch |
| Model substitution | Yes | Operator must approve replacement |

**No action proceeds without operator approval.** The Orchestrator proposes; the operator decides.

---

## 8. Rollback, Quarantine, and Missing Credential Handling

### 8.1 Rollback

When a model causes issues:
1. Operator requests rollback
2. Orchestrator disables model (`enabled: false`)
3. Config Renderer generates rollback configuration (model removed)
4. Node Sync delivers rollback (with operator approval)
5. Audit log records rollback

### 8.2 Quarantine

When a model is suspected of issues:
1. Operator requests quarantine
2. Orchestrator sets `quarantine_status: "quarantined"`
3. Model excluded from Available pool
4. Model appears in Non-available summary only
5. Operator can request quarantine review

### 8.3 Missing Credential

When `credential_status` is `missing` or `expired`:
1. Model cannot be enabled
2. Orchestrator reports missing credential to operator
3. Operator must resolve credential before model can be used
4. Secret Broker updates `credential_status` when credential is provisioned

---

## 9. Audit Report Fields

Every model pool operation produces an audit record with:

| Field | Description |
|-------|-------------|
| `timestamp` | ISO 8601 timestamp |
| `operator_id` | Operator who initiated or approved |
| `action` | Action type (add/delete/enable/disable/distribute/rollback/quarantine) |
| `model_id` | Affected model identifier |
| `provider` | Model provider |
| `approval_id` | Associated approval identifier |
| `previous_state` | State before action |
| `new_state` | State after action |
| `node` | Target node (for distribution actions) |
| `outcome` | Success/failure |
| `notes` | Additional context |

---

## 10. Prohibited Actions

### 10.1 Absolute Prohibitions

| Prohibition | Description |
|-------------|-------------|
| **No plaintext key** | Real keys MUST NOT appear in registry, config, logs, or reports |
| **No Git secret** | Secrets MUST NOT be committed to Git |
| **No auto node sync** | Node delivery requires explicit operator approval |
| **No auto model substitution** | Model changes require explicit operator approval |

### 10.2 Enforcement

These prohibitions are enforced by:
1. Schema validation (registry rejects entries with `secret_ref` containing key patterns)
2. Config Renderer (output uses placeholders only)
3. Node Sync (blocks without operator approval)
4. Audit log (records all attempts, including violations)

---

## 11. Dynamic Available Model Pool

### 11.1 Definition

The **Available Model Pool** contains only models that meet ALL criteria:

1. `enabled: true`
2. `credential_status` is `valid` or `not-configured`
3. `health_status` is `healthy` or `degraded`
4. `quarantine_status` is `none`
5. Model is detected as available on the target node

### 11.2 Non-Available Summary

Models that fail ANY criterion appear in the Non-available summary only:

| Status | Pool Placement |
|--------|----------------|
| `enabled: false` | Non-available |
| `credential_status: missing` | Non-available |
| `credential_status: expired` | Non-available |
| `health_status: unhealthy` | Non-available |
| `quarantine_status: quarantined` | Non-available |
| Not detected on node | Non-available |

### 11.3 OpenCode Free Models

OpenCode free models (e.g., `opencode/mimo-v2.5-free`, `opencode/deepseek-v4-flash-free`) enter the Available pool ONLY when:
1. Currently discovered on the target node
2. `enabled: true`
3. `credential_status: not-configured` (free tier)
4. Not quarantined

### 11.4 OpenCode Go Models

OpenCode Go models (subscription-based) enter the Available pool ONLY when:
1. Subscription is active (`credential_status: valid`)
2. Model is configured on the target node
3. `enabled: true`
4. Not quarantined

---

## 12. Relationship to Workflow Contract

This contract is referenced by [VIBE_CODING_WORKFLOW_CONTRACT.md](./VIBE_CODING_WORKFLOW_CONTRACT.md) in Step 2 (Technical Plan + Model Pool). All model pool operations described in the workflow contract are governed by this distribution contract.

---

## Enforcement

This contract is enforced by:
1. `opencode_model_pool.py` — model pool management
2. `operator_model_approval_gate.py` — operator approval validation
3. This document — the authoritative model pool distribution definition

---

*This contract is the single source of truth for model pool distribution governance. If any other document conflicts with this contract on model pool matters, this contract wins.*
