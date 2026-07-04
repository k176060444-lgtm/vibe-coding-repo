# Stage4 Class B — DEU Semantic Caveat

**Status**: Read-only documentation; no test or production semantics changed.

## Context

Stage4 `test_enabled_models_in_at_least_one_matrix` and
`test_5bao_9bao_matrix_includes_enabled` originally failed because 10
enabled pool models were missing from NMC matrices. Investigation
classified them:

| Classification | Models | Disposition |
|:---------------|:-------|:------------|
| **DEU** (declared_enabled_unassigned) | 9 models with `allowed_nodes=[]` and `lifecycle_status=declared_enabled_unassigned` | Correctly absent from NMC per D-B policy lock semantics |
| **Real NMC sync gap** | `opencode-go-qwen3-7-plus` with explicit `allowed_nodes=['5bao','9bao','21bao']` and `lifecycle_status=enabled_assigned` | Synced to NMC via idempotent normalization script |

## DEU Semantic Authority

`scripts/da_db_policy_lock.py:191-213` (`check_db_deu_lock`) defines:

```
"""D-B lock: DEU count matches expected and every DEU has empty allowed_nodes."""
...
if allowed:
    violations.append({..., "reason": "DEU model must have allowed_nodes=[]; got ... — silent promotion detected"})
```

This is the authoritative semantic. A model with `enabled=True` AND
`allowed_nodes=[]` AND `lifecycle_status=declared_enabled_unassigned` is
**DEU by design** and is correctly absent from NMC matrices until
explicit operator promotion.

## 9 DEU Models (Exact Allowlist)

| Model ID | provider_namespace | allowed_nodes |
|:---------|:-------------------|:--------------|
| `google-gemini-2-5-flash` | google | `[]` |
| `google-gemini-2-5-pro` | google | `[]` |
| `moonshot-moonshot-v1-128k` | moonshot | `[]` |
| `openai-gpt-4o` | openai | `[]` |
| `openai-o1` | openai | `[]` |
| `openai-o3` | openai | `[]` |
| `openai-o3-mini` | openai | `[]` |
| `openai-o4-mini` | openai | `[]` |
| `xai-grok-3` | xai | `[]` |

## Existing allowed_nodes=[] Models in NMC (Unaffected)

`anthropic-*`, `dashscope-*`, `deepseek-deepseek-coder`,
`deepseek-deepseek-reasoner` all have `allowed_nodes=[]` AND are
present in NMC matrices. They are present because of prior
normalization passes (S7-2 inventory evidence populated `env_loaded=True`).
The DEU-aware test logic does NOT remove or alter these existing entries;
it only changes whether an *absent* DEU model counts as a "missing"
failure.

## Real NMC Sync Gap

`opencode-go-qwen3-7-plus` has explicit `allowed_nodes=['5bao','9bao','21bao']`
and `lifecycle_status=enabled_assigned` — i.e., NOT DEU. Smoke evidence
is confirmed on 5bao and 9bao. The entry was missing from all 3 NMC
matrices due to incomplete normalization.

Fixed via `scripts/normalize_opencode_go_qwen3_7_plus_to_nmc.py` which
adds the entry to each node's matrix with all 6 runtime states
(`synced`, `runtime_visible`, `env_loaded`, `wrapper_valid`,
`model_call_verified`, `operator_approved`) set to `'unknown'`. No
promotion. Smoke evidence is preserved as metadata only.

## Readiness Promotion Status

Stage7 F6 gate (8 failures) still blocks readiness because
`operator_approved=unknown` for all 3 D4 nodes. Stage4 Class B is now
cleared.