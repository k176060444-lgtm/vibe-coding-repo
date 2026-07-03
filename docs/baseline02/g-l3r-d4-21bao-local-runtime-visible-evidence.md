# G-L3R D4 — 21bao Local Runtime-Visible Evidence

## Status

| Field | Value |
|---|---|
| Anchor | `2ec1778e357fd3a840b35d45d061f171388bf740` |
| Schema | `1.0.0` |
| Source collector | `worker_attest_layer3_d4_21bao_local_runtime_visible` |
| Receipt path | `.hermes/evidence/g-l3r-d4-21bao-local-runtime-visible-v1/21bao-receipt.json` |
| Operator decision | `require_21bao_d4_runtime_visible` (issued 2026-07-03) |
| Created | 2026-07-03 |

## Background

Per the operator decision `require_21bao_d4_runtime_visible`, the 21bao
residual asymmetry (R8, PR #324) must be addressed by collecting fresh
local-config-derived evidence. The previous receipt (`21bao-receipt.json`
in `g-l3r-d4-clean-main-v1/`) reads the NMC central projection and reports
`runtime_visible_observed=false` because NMC `runtime_visible=unknown`.

This new collector produces a **distinct, second-layer receipt** from the
21bao **local** runtime configuration (`~/.config/opencode/opencode.jsonc`),
which is the actual concrete config used by the 21bao worker runtime.

## Semantic Distinction

| Field | Previous Receipt (PR #332) | New Receipt (this PR) |
|---|---|---|
| Source | `21bao_local_nmc` (central NMC) | `21bao_local_opencode_config` (local config) |
| Read path | NMC matrix → `runtime_visible` field | JSONC `provider.deepseek-plan.deepseek-v4-pro` |
| Concrete provider key | N/A | `deepseek-plan.deepseek-v4-pro` |
| `runtime_visible_observed` | `false` | **`true`** |
| `model_call_verified_observed` | N/A | `false` (not attempted) |
| `operator_approved_observed` | N/A | `false` (not attempted) |

## Why runtime_visible IS Distinct from model_call_verified

- `runtime_visible=true` (this receipt): the local runtime **config/wrapper**
  can SEE the D4 model entry. This is a configuration fact.
- `model_call_verified=true`: requires actual model call succeeded.
  This is G-L4 territory, explicitly forbidden here.

A model being "runtime visible" on 21bao does not require successful invocation.

## Evidence Result

| Field | Value |
|---|---|
| `runtime_visible_observed` | **`true`** |
| `runtime_visible_source` | `21bao_local_opencode_config` |
| `matched_key` | `deepseek-plan.deepseek-v4-pro` |
| `provider_block_found` | `deepseek-plan` |
| `config_visible_observed` | `true` |
| `wrapper_visible_observed` | `false` (wrapper invocation not attempted) |
| `env_loaded_observed_enum` | `not_checked` |
| `credential_status_observed_enum` | `not_checked` |
| `endpoint_ref_observed_enum` | `not_checked` |
| `model_call_verified_observed` | `false` |
| `operator_approved_observed` | `false` |

## Forbidden-Operation Checklist

This evidence collector does NOT perform:

- Model call / live inference / smoke test
- Credential provisioning
- Subprocess invocation of model wrapper
- Network / HTTP calls
- SSH (21bao is local-exec/control host)
- Data write-back to NMC or model_pool
- Promotion of `model_call_verified` / `operator_approved` / `env_loaded`
- G-L4 / G-READINESS / G-GRAY / G-D-A / G-D-B / PR-7 / Baseline03 / Stage8

## What This Receipt Does NOT Do

- Does NOT close the global `G_L3R_BLOCKED` — the D4 blocker narrowing
  to 21bao residual (PR #335) remains in effect.
- Does NOT promote 21bao's NMC `runtime_visible` to `True`. NMC is a
  generated artifact; promotion requires a separate bounded PR with
  canonical NMC write-back (PR #334 pattern).
- Does NOT authorize model_call_verified or operator_approved.
- Does NOT advance to G-L4, G-READINESS, or any subsequent phase.

## Next Step

The collected evidence `runtime_visible_observed=true` from local config
is a **partial condition** for closing the 21bao residual. Per the
asymmetry doc §7, a complete close requires:

1. Explicit operator authorization (received — `require_21bao_d4_runtime_visible`)
2. Clean-main sanctioned evidence (this PR provides layer-2 evidence)
3. Live verification (sanctioned read; this collector is read-only)
4. Receipt regeneration (this PR provides the new layer-2 receipt)
5. No readiness/G-L4 progression (enforced by this PR's forbidden-ops)

A separate bounded PR may follow to normalize the 21bao NMC
`runtime_visible` field based on this evidence (similar to PR #334 for
5bao/9bao), but only with additional operator authorization.