# G-L4 D4 — model_call_verified 3-of-3 NMC Normalization

## Status

| Field | Value |
|---|---|
| **Gate ID** | `G-L4-D4-MODEL-CALL-VERIFIED-3OF3-NMC-NORMALIZATION` |
| **Operator Authorization** | `OPERATOR-20260704-G-L4-D4-MODEL-CALL-VERIFIED-3OF3-NMC-NORMALIZATION` |
| **Anchor** | `6a8b8ab81f5b91b5cfabaa488a3ad2842f37561e` |
| **Normalization Verdict** | `G_L4_D4_MODEL_CALL_VERIFIED_3OF3_NORMALIZED` |
| **Created** | 2026-07-04 |

## Scope

This is a **data-only NMC normalization** based on three already-merged canary
evidence PRs. No new model calls, no SSH, no credential operations.

## Evidence Sources

| Node | PR | Evidence Anchor | Concrete Invocation | Verdict |
|:----:|:--:|:---------------:|:-------------------:|:-------:|
| **21bao** | #341 | `f0b010c` | `deepseek-plan/deepseek-v4-pro` | model_call_succeeded=true |
| **5bao** | #342 | `1ccdf31` | `deepseek-plan/deepseek-v4-pro` | model_call_succeeded=true |
| **9bao** | #343 | `2f1df7e` | `opencode-go/deepseek-v4-pro` | model_call_succeeded=true |

## NMC Changes

### D4 Model: `opencode-go-deepseek-v4-pro`

| Node | Field | Before | After | Evidence Reference |
|:----:|:------|:------:|:-----:|:-----------------:|
| **21bao** | `model_call_verified` | `unknown` | **`true`** | PR #341, anchor `f0b010c` |
| | `model_call_verified_evidence` | — | **added** | source/canonical/concrete/namespace_note |
| **5bao** | `model_call_verified` | `unknown` | **`true`** | PR #342, anchor `1ccdf31` |
| | `model_call_verified_evidence` | — | **added** | source/canonical/concrete/namespace_note |
| **9bao** | `model_call_verified` | `unknown` | **`true`** | PR #343, anchor `2f1df7e` |
| | `model_call_verified_evidence` | — | **added** | source/canonical/concrete/namespace_note |

### Fields NOT Changed

| Field | Status |
|---|---|
| `operator_approved` | ❌ unchanged (remains `unknown` for all nodes) |
| `env_loaded` | ❌ unchanged |
| `runtime_visible` | ❌ unchanged (G-L3R 3-of-3 preserved) |
| `declared` / `synced` / `wrapper_valid` | ❌ unchanged |
| model_pool.yaml | ❌ NOT modified |

## Namespace-Asymmetry Semantics

- **21bao** and **5bao** use `deepseek-plan/deepseek-v4-pro` as concrete invocation
  — this is the **documented concrete runtime path** for nodes where
  `opencode-go` provider fails at runtime (ProviderModelNotFoundError).
  Recorded as `namespace_note: node-specific runtime namespace asymmetry; not
  fallback; not provider drift`.

- **9bao** uses `opencode-go/deepseek-v4-pro` as concrete invocation — the
  canonical provider resolves correctly. Recorded as `namespace_note: canonical
  provider direct invocation; no fallback needed`.

- These are NOT recorded as fallback or provider drift — they are
  node-specific configuration differences documented at normalization time.

## Non-Promotion Proof

| Claim | Status |
|---|---|
| `operator_approved` promoted | ❌ false — remains `unknown` |
| `env_loaded` promoted | ❌ false — unchanged |
| `readiness` entered | ❌ false |
| `gray` entered | ❌ false |
| `Baseline03` entered | ❌ false |
| `model_pool.yaml` modified | ❌ false — only NMC changed |

## See Also

- `.hermes/evidence/g-l4-d4-model-call-canary-21bao-v1/21bao-receipt.json` — PR #341
- `.hermes/evidence/g-l4-d4-model-call-canary-5bao-v1/5bao-receipt.json` — PR #342
- `.hermes/evidence/g-l4-d4-model-call-canary-9bao-v1/9bao-receipt.json` — PR #343
- `scripts/node_model_capability.yaml` — NMC with 3-of-3 model_call_verified
