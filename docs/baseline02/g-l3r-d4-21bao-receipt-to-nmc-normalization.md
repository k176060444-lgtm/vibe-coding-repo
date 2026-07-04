# G-L3R D4 21bao Receipt-to-NMC Normalization

## Status

| Field | Value |
|---|---|
| PR | (this PR) — `data: normalize 21bao G-L3R D4 runtime-visible evidence` |
| Branch | `data-g-l3r-d4-21bao-receipt-to-nmc-normalization` |
| Author | operator-authorized (KK) |
| Operator Decision | `OPERATOR-20260704-G-L3R-D4-21BAO-NMC-NORMALIZATION-006` |
| Anchor | `0a932be4fd6d12760e8c5e6400044644864e003c` |
| Evidence Source | PR #336 (`g-l3r-d4-21bao-local-runtime-visible-evidence.md`) |
| Predecessor | PR #336 (evidence collected), PR #334 (5bao/9bao NMC normalization) |
| Closes Global G_L3R_BLOCKED | **NO** — runtime_visible layer only |

## Purpose

This PR performs **bounded, data-only normalization** of the 21bao D4
runtime_visible evidence (collected in PR #336) into the NMC data layer
(`scripts/node_model_capability.yaml`). It does:

- Set `runtime_visible: True` on the 21bao D4 entry (`opencode-go-deepseek-v4-pro`),
  referencing PR #336 evidence (anchor `2ec1778e`, merge commit `0a932be`).
- Add a `runtime_visible_evidence` block pointing to PR #336 receipt,
  collector, and source enum (`21bao_local_opencode_config`).
- Update the regression-test invariants in existing tests that previously
  asserted "21bao runtime_visible != True" (which was true before PR #336).
- Regenerate NMC via deterministic script
  (`scripts/normalize_g_l3r_d4_runtime_visible.py`) with idempotency
  verified.

It does **NOT** perform:

- Model calls / inference / smoke
- Credential provisioning
- Node sync apply
- SSH / live collection
- `model_call_verified` / `operator_approved` / `env_loaded` promotion
- `model_pool.yaml` modification
- DEU assignment (G-D-A) / enablement (G-D-B)
- G-L4 / G-READINESS / G-GRAY / PR-7 / Baseline03 / Stage8 entry
- Global `G_L3R_BLOCKED` closure

## 21bao Normalization Semantics

### Before this PR

| Layer | 21bao | 5bao | 9bao |
|---|---|---|---|
| `runtime_visible` (NMC) | `unknown` (residual) | `true` | `true` |
| Runtime layer config keys | `deepseek-plan.deepseek-v4-pro` present | `opencode-go-deepseek-v4-pro` | `opencode-go-deepseek-v4-pro` |
| Canonical D4 entry | `opencode-go-deepseek-v4-pro` | same | same |
| Evidence-backed `runtime_visible=true`? | NO (R8 residual) | YES (PR #332) | YES (PR #332) |

### After this PR

| Layer | 21bao | 5bao | 9bao |
|---|---|---|---|
| `runtime_visible` (NMC) | `true` | `true` | `true` |
| Evidence-backed? | YES (PR #336) | YES (PR #332) | YES (PR #332) |
| 3-of-3 at runtime_visible? | **YES** | **YES** | **YES** |

The evidence anchor for 21bao is `2ec1778e357fd3a840b35d45d061f171388bf740`
(merge of PR #332 = pre-PR #336 base). The PR #336 receipt itself records
this anchor and the PR #336 merge commit `0a932be4fd6d12760e8c5e6400044644864e003c`.

The 21bao D4 NMC entry now carries:

```yaml
- model_id: opencode-go-deepseek-v4-pro
  canonical_provider: opencode-go
  provider_namespace: opencode-go
  primary_alias: opencode-ds4pro
  runtime_provider: opencode-go
  declared: true
  synced: true
  wrapper_valid: true
  model_call_verified: unknown       # NOT PROMOTED
  operator_approved: unknown         # NOT PROMOTED
  runtime_visible: true              # NORMALIZED via PR #336 evidence
  env_loaded: true                   # Pre-existing, not promoted here
  runtime_visible_evidence:
    source: 'PR #336 21bao local runtime-visible evidence'
    approval_id: OPERATOR-20260704-G-L3R-D4-21BAO-LOCAL-RT-EVIDENCE-005
    evidence_anchor: 2ec1778e357fd3a840b35d45d061f171388bf740
    merge_commit: 0a932be4fd6d12760e8c5e6400044644864e003c
    collector: worker_attest_layer3_d4_21bao_local_runtime_visible
    matched_key: deepseek-plan.deepseek-v4-pro
    runtime_visible_source: 21bao_local_opencode_config
    note: '21bao local concrete opencode.jsonc has `deepseek-plan` provider block ...'
```

## D4 Preflight / Aggregate / Reconciliation Outputs

### D4 Preflight (`worker_attest_layer3_d4_runtime_visible_preflight`)

The preflight still runs against the same logic. After this PR:

- All 3 nodes have `runtime_visible_known=True` in the mismatch matrix.
- Root cause `runtime_visible_unknown` is no longer triggered.
- The verdict may shift to `G_L3R_D4_PREFLIGHT_DATA_ONLY_CANDIDATE`
  (because 3-of-3 normalization closes the data-only gap). The KEEP_BLOCKED
  verdict is also acceptable if the higher-layer logic dominates.

### Aggregate Summary (`worker_attest_layer3_runtime_summary`)

- `nodes_seen`: all 3 nodes (21bao/5bao/9bao).
- The D4 `runtime_visible` finding is closed for all 3 nodes.

### Reconciliation (`worker_attest_layer3_reconciliation`)

- The blocker text in the reconciliation report is updated to reflect
  3-of-3 at runtime_visible:
  > "deepseek-v4-pro (DeepSeek V4 Pro): All 3 nodes (21bao/5bao/9bao)
  > runtime_visible=true (5bao/9bao via PR #332 evidence, PR #334 NMC
  > normalization; 21bao via PR #336 local evidence, PR #337 NMC
  > normalization). Global G_L3R_BLOCKED narrowed to
  > model_call_verified / operator_approved / readiness / G-L4 layers —
  > does not close globally until those layers resolve."
- `next_recommendation` is updated to point operator toward
  higher-layer authorization (separate authorization required for
  G-L4 / readiness / model_call_verified / operator_approved).
- The reconciliation's `closes_global_blocker` is preserved as **false**.

## Files Changed in This PR

| File | Status | Purpose |
|---|---|---|
| `scripts/normalize_g_l3r_d4_runtime_visible.py` | MODIFIED | Now handles 21bao via PR #336 evidence; deterministic, idempotent; has `--self-check` |
| `scripts/node_model_capability.yaml` | REGENERATED | 21bao D4 entry now `runtime_visible: true` with PR #336 evidence block |
| `scripts/worker_attest_layer3_reconciliation.py` | MODIFIED | Blocker text and recommendations updated to reflect 3-of-3 at runtime_visible |
| `tests/test_worker_attest_layer3_d4_data_normalization.py` | MODIFIED | Removed "21bao != True" assertions; added PR #336 evidence reference test |
| `tests/test_g_l3r_d4_21bao_residual_gate.py` | MODIFIED | Updated 3-of-3 verdict assertions; 21bao=true now expected; reconciliation references 21bao history |
| `.hermes/evidence/g-l3r-d4-21bao-residual-gate.json` | MODIFIED | Verdict updated to `G_L3R_D4_RUNTIME_VISIBLE_3OF3_NORMALIZED`; preserves higher-layer narrowing |
| `docs/baseline02/g-l3r-d4-21bao-residual-gate.md` | MODIFIED | Updated to reflect 3-of-3 normalization and clarify what is NOT being claimed |
| `docs/baseline02/g-l3r-d4-21bao-receipt-to-nmc-normalization.md` | NEW | This document |
| `tests/test_g_l3r_d4_21bao_receipt_to_nmc_normalization.py` | NEW | Bounded test suite for this PR |

## Forbidden-Operation Checklist

| Operation | Status |
|---|---|
| Model call / smoke / inference | ❌ NOT performed |
| Credential provisioning | ❌ NOT performed |
| Node sync apply | ❌ NOT performed |
| SSH / live collection | ❌ NOT performed |
| `env_loaded` promotion | ❌ NOT performed |
| `model_call_verified` promotion | ❌ NOT performed |
| `operator_approved` promotion | ❌ NOT performed |
| `model_pool.yaml` modification | ❌ NOT performed |
| Other NMC entries modified | ❌ NOT performed (only D4 entry's `runtime_visible` set) |
| DEU assignment (G-D-A) | ❌ NOT performed |
| DEU enablement (G-D-B) | ❌ NOT performed |
| G-L4 / G-READINESS / G-GRAY / PR-7 / Baseline03 / Stage8 entry | ❌ NOT performed |
| Global `G_L3R_BLOCKED` closure | ❌ NOT closed |

## Why This Is Data-Only and Bounded

1. **Source of truth unchanged**: The PR reads canonical evidence
   (PR #336 receipt) and projects it onto the NMC's existing 21bao D4
   entry. It does NOT change:
   - `model_pool.yaml` (provider identity, lifecycle, enablement)
   - The `D4` model_id in either pool or NMC
   - 5bao/9bao's evidence reference (kept as-is pointing to PR #332)
   - Other NMC entries (untouched)

2. **Deterministic**: The normalization script regenerates the NMC YAML
   deterministically from the YAML input. Running the script twice produces
   the same YAML output (bit-for-bit, modulo timestamps). Self-check
   (`--self-check` flag) verifies the invariants without modifying the file.

3. **Self-check enforced**: The normalization script has a `--self-check`
   mode that verifies:
   - All 3 nodes carry the correct evidence reference
   - 21bao evidence references `PR #336`, anchor `2ec1778`, merge `0a932be`
   - 5bao/9bao evidence reference `PR #332`, anchor `09b1d97`
   - All `model_call_verified` / `operator_approved` remain non-promoted
   - `model_pool.yaml` is untouched (no smoke_results, no new fields)
   - No G-L4 / readiness claims in NMC notes

4. **Higher-layer preservation**: Global `G_L3R_BLOCKED` remains open.
   The next operator decision needed is about the higher layers
   (model_call_verified / operator_approved / G-L4 preflight), not this PR.
