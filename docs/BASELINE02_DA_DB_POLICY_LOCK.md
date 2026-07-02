# Baseline02 D-A / D-B Policy Lock

**Status:** locked at `main = 3536f310c0fa0537ce7a5715702cf0ec8a75a17a`
**Scope:** Vibe Coding Agent 小集群 model_pool D-A / D-B decision surface
**Enforcement:** `scripts/da_db_policy_lock.py` (read-only validator)
**Tests:** `tests/test_da_db_policy_lock.py`

This document records the current operator decision stance on
Baseline02 D-A (canonical vs runtime provider layering) and D-B (per-node
model assignment). It is a **lock**, not a transition: it flags any deviation
from the frozen stance so an operator either (a) confirms the stance still
holds or (b) explicitly authorizes a change through a dedicated D-A/D-B PR.

## 1. Frozen stance

### 1.1 D-A — Canonical / namespace / runtime folding for active models

Locked. For every model with

```
lifecycle_status in {enabled_assigned, operator_requested}
```

the pool MUST satisfy

```
canonical_provider   == "opencode-go"
provider_namespace   == "opencode-go"
```

and the node-level `runtime_provider` (in `node_model_capability.yaml`) MUST
also be `opencode-go` on 21bao / 5bao / 9bao. In effect, all 9 currently active
models fold onto one runtime.

Rationale:

* Vibe Coding Agent 小集群 currently routes all active traffic through the
  OpenCode Zen (`opencode-go`) cloud proxy at every node.
* Introducing a second runtime layer (e.g. `opencode-go-plan` per SOUL §4
  example) is a schema change that needs its own D-A PR and schema-only
  migration; it must not sneak in through a data edit.

### 1.2 D-B — 16 declared_enabled_unassigned (DEU) models must stay DEU

Locked. The 16 models with

```
lifecycle_status = "declared_enabled_unassigned"
enabled           = true
allowed_nodes     = []
```

MUST remain DEU. They MUST NOT be silently promoted to `enabled_assigned` or
`operator_requested` by any operation that is not an explicit operator D-B PR.

Concretely:

* Adding any node to `allowed_nodes` for a DEU model = silent promotion → **BLOCK**
* Flipping `enabled` to `false` on a DEU = state change out of D-B lock → **BLOCK**
* Tacking pool-level readiness fields (`operator_approved`, `model_call_verified`,
  `readiness`) onto a DEU entry = silent promotion → **BLOCK**

The 16 DEU cluster by canonical provider:

| canonical_provider | count | ids (aliases) |
|---|---:|---|
| openai | 5 | `gpt4o`, `o1`, `o3`, `o3-mini`, `o4-mini` |
| anthropic | 3 | `haiku`, `opus`, `claude` |
| dashscope | 2 | `qwen`, `qwen-plus` |
| deepseek | 2 | `deepseek-coder`, `deepseek-r1` |
| google | 2 | `gemini-flash`, `gemini` |
| moonshot | 1 | `kimi` |
| xai | 1 | `grok` |
| **total** | **16** | |

### 1.3 Node-alias normalization — `win` → `21bao`

**Status: NORMALIZED** — All legacy `win` references in `allowed_nodes` have been
replaced with the canonical `21bao` in [[PR #306]].

The canonical node ids per SOUL.md §1 are `{"21bao", "5bao", "9bao"}`.
The legacy alias `"win"` is no longer present in `model_pool.yaml`.

Defence-in-depth:

* `scripts/model_pool_drift.py` still normalizes `win` → `21bao` at read time
  via `LEGACY_NODE_ALIASES = {"win": "21bao"}` (retained for one release cycle).
* `scripts/vibe_model_resolver.py` restricts input `node` to canonical ids
  (`VALID_NODES = {"21bao", "5bao", "9bao"}`), so `win` cannot enter as a
  resolution target.
* The policy-lock validator now reports 0 legacy `win` refs; any reappearance
  would be flagged.

Any node reference that is neither canonical nor a legacy alias (e.g. a typo
like `"mars"`) is treated as `invalid_node_refs` and **BLOCKS** the lock.

### 1.4 No new provider_namespace without a D-A PR

Locked. The following `provider_namespace` values are frozen:

```
active:  opencode-go
DEU:     anthropic, dashscope, deepseek, google, moonshot, openai, xai
other:   opencode, xiaomi, minimax, volcengine, deepseek-plan, minimax-plan
```

A new `provider_namespace` value in the pool without a D-A PR triggers
`unknown_namespaces` → **BLOCK**.

## 2. Verdicts

`scripts/da_db_policy_lock.py validate` emits one of:

| verdict | meaning |
|---|---|
| `DA_DB_POLICY_LOCK_PASS` | pool matches every clause of §1 |
| `DA_DB_POLICY_LOCK_BLOCKED` | pool violates at least one clause; report lists offending models with `_safe_summary` (no secret / URL / real path / env value / key length) |
| `STOP_SECRET_RISK` | the emitted report would leak a plausibly-real secret / URL / real path — should never fire on the current pool |
| `STOP_AND_REANCHOR` | pool schema shape is unexpected; do not proceed until operator re-anchors |

## 3. Guarantees

`da_db_policy_lock.py` is a pure read-only validator:

* No SSH, no `subprocess`, no `socket`, no `paramiko`, no `requests` / `urllib`.
* No `os.environ` / `os.getenv` access.
* No modification of `model_pool.yaml`, `node_model_capability.yaml`, or any
  other config.
* No model calls, no credential provisioning, no node sync, no readiness
  expansion.
* Reads only non-secret metadata:
  `id, primary_alias, canonical_provider, provider_namespace, allowed_nodes,
   enabled, lifecycle_status, credential_status, endpoint_ref` (as field NAME,
  never the underlying value).

These properties are asserted by the accompanying test file at both AST level
and behavior level.

## 4. How to promote a DEU (D-B change) — not covered by this lock

Out of scope for the lock. The high-level sequence, for reference:

1. Operator issues an explicit D-B decision (target node(s), runtime binding).
2. Data-only PR adds the model to `allowed_nodes` in `model_pool.yaml` and
   the corresponding matrix entry in `node_model_capability.yaml`.
3. Post-merge: Layer 1 drift warn count MUST drop by 3 (or by the number of
   nodes the model was assigned to), never increase.
4. Post-merge: `worker_attest_collector` canary refreshes the Layer 2
   receipt for the affected node(s); Layer 2 fail-closed must NOT persist.
5. `da_db_policy_lock.py validate` is re-run: expected active/DEU counts in
   the module must be updated in the same PR to reflect the new lock point.

## 5. Change control

Editing `EXPECTED_ACTIVE_COUNT`, `EXPECTED_DEU_COUNT`,
`ACTIVE_RUNTIME_PROVIDER`, or the `frozen_set` in
`da_db_policy_lock.py` is itself a **D-A/D-B change** and requires the same
operator PR discipline as any pool data edit.
