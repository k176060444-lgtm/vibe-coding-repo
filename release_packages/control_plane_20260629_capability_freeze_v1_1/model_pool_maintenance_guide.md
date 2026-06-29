# Model Pool Maintenance Guide

**Part of**: WO-CONTROL-PLANE-RELEASE-PACKAGE-001  
**Last updated**: 2026-06-29  
**CLI tool**: `model_pool_manager.py` (in `scripts/`)

---

## Overview

The central model pool is the source of truth for all node configurations. 
Rather than editing `model_pool.yaml` by hand, use the CLI commands below.

**All commands** are run from the `scripts/` directory:
```bash
cd /path/to/scripts/
python model_pool_manager.py <command> [options]
```

---

## 1. Add a New Model

```bash
python model_pool_manager.py add \
  --id opencode-go-minimax-m3 \
  --alias minimax-m3 m3 \
  --provider opencode-go \
  --model MiniMax-M3 \
  --internal-provider-id opencode-go \
  --key-env OPENCODE_GO_API_KEY \
  --base-url-env OPENCODE_GO_BASE_URL \
  --capability-tags chat,code \
  --cost paid \
  --nodes 5bao,9bao,21bao \
  --priority 23 \
  --smoke-required true \
  --notes "MiniMax M3 via opencode-go provider"
```

New models default to:
- `enabled: true`
- `quarantined: false`
- `smoke_required: true`
- **status: UNVERIFIED** (never starts as VERIFIED — smoke must be run first)

---

## 2. List Models

```bash
# All models
python model_pool_manager.py list

# Filter by node
python model_pool_manager.py list --node 5bao

# JSON output for scripting
python model_pool_manager.py list --json
```

---

## 3. Update a Model

```bash
# Dry-run (default): preview changes without applying
python model_pool_manager.py update opencode-go-minimax-m3 \
  --key-env OPENCODE_MINIMAX_API_KEY \
  --notes "Updated key env"

# Apply changes (pass --apply)
python model_pool_manager.py update opencode-go-minimax-m3 \
  --allowed-nodes 5bao,9bao \
  --priority 15 \
  --apply
```

**Supported update fields:**

| CLI flag | Pool field | Type |
|----------|------------|------|
| `--provider` | `provider` | string |
| `--model` | `model` | string |
| `--internal-provider-id` | `internal_provider_id` | string |
| `--key-env` | `key_env` | string |
| `--base-url-env` | `base_url_env` | string |
| `--allowed-nodes` | `allowed_nodes` | comma-separated |
| `--aliases` | `alias` | space-separated list |
| `--capability-tags` | `capability_tags` | comma-separated |
| `--key-env-aliases` | `key_env_aliases` | comma-separated |
| `--cost` | `cost` | string |
| `--notes` | `notes` | string |
| `--priority` | `priority` | integer |
| `--smoke-required` | `smoke_required` | true/false |

---

## 4. Disable / Enable a Model

```bash
# Disable (model remains in pool but not used)
python model_pool_manager.py disable opencode-go-minimax-m3

# Re-enable
python model_pool_manager.py enable opencode-go-minimax-m3
```

---

## 5. Deprecate a Model (Preferred Over Deletion)

```bash
# Deprecate: disables + quarantines + adds deprecation note
python model_pool_manager.py deprecate opencode-go-minimax-m3 \
  --reason "Superseded by newer version"

# If smoke or evidence already exists, deprecation preserves them for history.
```

**Deprecation preserves:**
- `smoke_results` (historical record)
- `credential_status_by_node`
- `evidence` entries

---

## 6. Remove a Model (Permanent Deletion)

```bash
# DRY-RUN FIRST: preview impact
python model_pool_manager.py remove opencode-go-minimax-m3 --dry-run

# Dry-run output includes: aliases, smoke_results, credential_status_by_node

# Blocked: VERIFIED models cannot be removed without --force
python model_pool_manager.py remove opencode-go-minimax-m3  # BLOCKED
# -> "Has VERIFIED smoke on nodes: [5bao]. Use --force to remove."

# Force remove (only if you're sure)
python model_pool_manager.py remove opencode-go-minimax-m3 \
  --force --reason "Replaced by newer model"
```

---

## 7. Full Schema Validation

```bash
# Validates ALL constraints
python model_pool_manager.py validate-full

# Machine-readable JSON
python model_pool_manager.py validate-full --json
```

**Checks performed:**

| Check | Type | What it validates |
|-------|:----:|-------------------|
| Duplicate aliases | ERROR | Two models cannot share the same alias |
| Missing key_env | WARNING | Enabled model with nodes but no credential var |
| Missing base_url_env | WARNING | key_env set but no URL env |
| Missing internal_provider_id | WARNING | Enabled model with nodes but no provider ID |
| Unknown node | ERROR | `allowed_nodes` contains unrecognized node name |
| Enabled without nodes | WARNING | Model enabled but no nodes assigned |
| Smoke required but empty | WARNING | `smoke_required=true` but no smoke results |
| Secret in tracked repo | FINDING | Suspicious patterns in YAML |

---

## 8. Generate Capability Freeze Snapshot

```bash
# Basic: from pool smoke_results only
python model_pool_manager.py freeze

# With evidence: includes VFV entries from credential_evidence
python model_pool_manager.py freeze \
  --evidence fixtures/credential_evidence_live.json

# Save to file
python model_pool_manager.py freeze \
  --evidence fixtures/credential_evidence_live.json \
  --output path/to/capability_freeze.json
```

The freeze output is a JSON snapshot with status labels:

| Label | Meaning |
|-------|---------|
| `V` | Exact-match PASS (pool `smoke_results.confirmed`) |
| `VFV` | VERIFIED_WITH_FORMAT_VARIANCE (exit=0 + prior evidence) |
| `UNVERIFIED` | In pool, enabled on node, not yet verified |
| `FROZEN` | Operator-confirmed INVALID (xiaomi) |

---

## 9. Sync Dry-Run (Contract)

```bash
# Preview what would be synced to workers
python model_pool_manager.py sync --nodes 5bao,9bao
```

Sync is **dry-run only** in this work order. Real worker writes require a separate approved work order (WO-WORKER-SYNC-001).

Each sync-plan entry reports:
- Target worker files (`opencode.jsonc`, `credential_evidence.json`)
- Backup plan
- Credential source (central secret overlay)
- Whether smoke is required after sync

---

## 10. After Smoke: Record Results

```bash
python model_pool_manager.py smoke-result \
  --alias opencode-kimi26 \
  --node 21bao \
  --status pass \
  --phase C-STAGE \
  --wrapper "vibedev-opencode.bat" \
  --invocation "opencode-go/kimi-k2.6" \
  --duration 8.0 \
  --reason "21bao opencode-go expansion PASS, exact match, build kimi-k2.6"
```

---

## 11. Backup and Rollback

The pool automatically creates a backup before every write operation:

```bash
# Manual backup
python model_pool_manager.py backup

# Rollback to a backup
python model_pool_manager.py rollback /path/to/backup.yaml
```

---

## Common Workflows

### A. Add a new model to all 3 nodes

```bash
# 1. Add
python model_pool_manager.py add --id ... [all params]

# 2. Validate
python model_pool_manager.py validate-full

# 3. Sync preview
python model_pool_manager.py sync --nodes 5bao,9bao,21bao

# 4. Sync + smoke (requires operator approval for real writes)
# 5. Record smoke result
python model_pool_manager.py smoke-result --alias ... --node ... --status pass

# 6. Regenerate freeze
python model_pool_manager.py freeze --evidence fixtures/credential_evidence_live.json --output path/to/freeze.json
```

### B. Disable a model across all nodes

```bash
# Prefer deprecation over deletion
python model_pool_manager.py deprecate MODEL_ID --reason "Reason"

# Or temporarily disable
python model_pool_manager.py disable MODEL_ID
```

### C. Change a model's key_env

```bash
python model_pool_manager.py update MODEL_ID --key-env NEW_KEY_ENV --apply
```

### D. Generate release freeze

```bash
python model_pool_manager.py freeze \
  --evidence fixtures/credential_evidence_live.json \
  --output release_packages/control_plane_YYYYMMDD/freeze.json
```

---

## Remaining Work (Deferred)

See `WO-MODEL-POOL-MAINTENANCE-CLI-001` for deferred items:

1. **`validate-full` tracked-repo check**: The `_check_tracked_repo_secrets` function is basic regex-based and may need tuning.
2. **Real worker sync**: Requires separate operator-approved work order (`WO-WORKER-SYNC-001`).
3. **Auto-smoke pipeline**: Optional —  `smoke-result` records results but doesn't auto-trigger smoke.
