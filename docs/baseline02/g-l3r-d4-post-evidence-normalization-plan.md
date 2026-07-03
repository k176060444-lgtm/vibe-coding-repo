# G-L3R D4 Post-Evidence Normalization Plan

**Status**: Read-only planning document — `not-G_L3R_BLOCKED-resolved` / `not-G-L4-ready` / `not-readiness-ready` / `not-model_call_verified-ready` / `not-operator_approved-ready`
**Phase**: Post-evidence planning — between D4 clean-main evidence archive (PR #332) and any future operator-authorized receipt-to-NMC normalization
**Evidence Anchor (this plan references)**: `09b1d97f0cab774e3eb023c9768a40d8165a1d46` (PR #332 collection anchor)
**Merge Anchor (this plan authored at)**: `18807ddbef5d962b67dd102220cdb118432d4f7c` (PR #332 merge commit)
**Created**: 2026-07-03

---

## 1. Purpose

This document records the **post-evidence normalization plan** for the G-L3R D4 runtime visibility case, after PR #332 (`evidence: add G-L3R D4 clean-main live receipts`) merged clean-main sanctioned live evidence into main.

It is a **decision preflight document** that:
- Restates the canonical D4 evidence state
- Lays out a *proposed* (NOT yet authorized) receipt-to-NMC normalization gate
- Lists the explicit field-by-field design if a future operator authorizes the normalization
- **Does NOT** perform, authorize, or schedule the normalization
- **Does NOT** write back to NMC or `model_pool.yaml`
- **Does NOT** advance G-L4 / readiness / gray / Baseline03

**Scope constraints**:
- `not-G_L3R_BLOCKED-resolved`
- `not-G-L4-ready`
- `not-readiness-ready`
- `not-model_call_verified-ready`
- `not-operator_approved-ready`
- `not-NMC-write-back`
- `not-model_pool-write-back`
- `not-G-READINESS / not-G-GRAY / not-G-D-A / not-G-D-B / not-PR-7 / not-Baseline03 / not-Stage8`

## 2. Canonical Evidence State (from PR #332)

PR #332 anchored at clean main = `09b1d97f0cab774e3eb023c9768a40d8165a1d46` collected the following per-node observations:

| Node | `runtime_visible_observed` | `runtime_visible_source` | Receipt SHA256 | Status |
|---|---|---|---|---|
| **21bao** | `false` | `21bao_local_nmc` | `161a63bfb542ef58...` | R8 documented residual |
| **5bao** | `true` | `5bao_ssh_opencode_config` | `276282ec5a8fe827...` | closure evidence |
| **9bao** | `true` | `9bao_ssh_opencode_config` | `82251a6514552027...` | closure evidence |

**Verdict**:
- `evidence_status = G_L3R_D4_CLEAN_MAIN_LIVE_EVIDENCE_2OF3_PASS`
- `blocker_status = G_L3R_D4_NOT_3OF3`
- `blocker_state = G_L3R_BLOCKER_REMAINS_PARTIALLY_OPEN_FOR_21BAO`
- `closes_blocker = false`
- `is_readiness = false`
- `is_g_l4_ready = false`
- `is_model_call_verified_ready = false`

**Approval ID**: `OPERATOR-20260703-G-L3R-D4-LIVE-EVIDENCE-003`

**What 21bao's `false` means (R8)**:
21bao's local OpenCode config (`~/.config/opencode/opencode.jsonc`) does not have an `opencode-go` provider block. The D4 model is nested under `deepseek-plan` in the local config. NMC reports `runtime_visible=unknown` for `opencode-go-deepseek-v4-pro` on 21bao. Documented in `g-l3r-d4-21bao-namespace-asymmetry.md` (PR #324). **21bao is a documented non-blocking residual — not a new defect.**

## 3. Proposed (NOT Authorized) Receipt-to-NMC Normalization Design

> **This section is design-only. It does NOT authorize the normalization. Each field below requires a separate bounded PR and explicit operator authorization.**

If a future operator authorizes receipt-to-NMC normalization, the following per-field design would apply. The design is constrained strictly to the observed evidence in PR #332.

### 3.1 21bao (R8 Residual — MUST NOT be elevated)

| NMC field | Current | Proposed (only if separately authorized) | Source |
|---|---|---|---|
| `runtime_visible` | `unknown` | **NO CHANGE** — must remain `unknown`/`false` | R8 documented residual |
| `model_call_verified` | `unknown` | **NO CHANGE** — must remain `unknown` | no smoke test authorized |
| `operator_approved` | `unknown` | **NO CHANGE** — must remain `unknown` | no operator decision |
| `env_loaded` | `True` | (no change proposed) | NMC existing |
| `wrapper_valid` | `True` | (no change proposed) | NMC existing |

**Rationale**: PR #332 evidence shows `runtime_visible_observed=false` for 21bao. Promoting 21bao to `runtime_visible=True` would be a **false claim** because 21bao's local config does not expose `opencode-go` as a provider. The 21bao residual remains a R8 non-blocking item; resolution requires either a provider-block addition in 21bao's local config (out of this PR's scope) or a separate operator decision.

### 3.2 5bao (Evidence Supports Elevation)

| NMC field | Current | Proposed (only if separately authorized) | Source |
|---|---|---|---|
| `runtime_visible` | `unknown` (NMC stale) | `True` (reflect live evidence) | PR #332 receipt `5bao_ssh_opencode_config` |
| `model_call_verified` | `unknown` | **NO CHANGE** — must remain `unknown` | evidence only confirms `runtime_visible`, not model invocation |
| `operator_approved` | `unknown` | **NO CHANGE** — must remain `unknown` | no operator decision |
| `env_loaded` | `True` | (no change proposed) | NMC existing |
| `wrapper_valid` | `True` | (no change proposed) | NMC existing |

**Rationale**: PR #332 collected `runtime_visible_observed=true` via sanctioned SSH read-only on 5bao's `opencode.jsonc`. This is evidence of configuration presence, **not** of model invocation success. Field elevation is therefore bounded to `runtime_visible=True`. `model_call_verified` requires a separate smoke test, which is NOT in this PR's scope and NOT authorized.

### 3.3 9bao (Evidence Supports Elevation)

| NMC field | Current | Proposed (only if separately authorized) | Source |
|---|---|---|---|
| `runtime_visible` | `unknown` (NMC stale) | `True` (reflect live evidence) | PR #332 receipt `9bao_ssh_opencode_config` |
| `model_call_verified` | `unknown` | **NO CHANGE** — must remain `unknown` | evidence only confirms `runtime_visible`, not model invocation |
| `operator_approved` | `unknown` | **NO CHANGE** — must remain `unknown` | no operator decision |
| `env_loaded` | `True` | (no change proposed) | NMC existing |
| `wrapper_valid` | `True` | (no change proposed) | NMC existing |

**Rationale**: Same as 5bao. PR #332 evidence supports `runtime_visible=True` for 9bao; other fields unchanged.

### 3.4 Forbidden Field Promotions (in any future normalization)

| Field | Forbidden promotion path |
|---|---|
| `model_call_verified` | ❌ No promotion to `True` without a separate smoke test (NOT in this plan, NOT authorized) |
| `operator_approved` | ❌ No promotion to `True` without explicit operator decision (NOT in this plan, NOT authorized) |
| 21bao `runtime_visible` | ❌ No promotion to `True` (would be a false claim) |

## 4. Proposed (NOT Authorized) Blocker Narrowing Gate

> **This section proposes one gate for a future operator decision. It does NOT execute it.**

The current `G_L3R_BLOCKER_REMAINS_PARTIALLY_OPEN_FOR_21BAO` is a **global** blocker phrasing. Once 5bao/9bao evidence is canonical in main, a future operator decision could authorize narrowing it to a **21bao-specific residual** — but ONLY after:

1. NMC `runtime_visible` for 5bao and 9bao has been updated to `True` (per §3.2, §3.3) via a separate bounded PR
2. The 21bao asymmetry remains documented in `g-l3r-d4-21bao-namespace-asymmetry.md`
3. A new operator decision is issued to narrow the blocker
4. The narrowing PR explicitly preserves the R8 documentation

**Proposed future gate verdict** (only after the above):
- `G_L3R_BLOCKER_NARROWED_TO_21BAO_RESIDUAL_ONLY` (NOT `G_L3R_BLOCKED_resolved`)

**What this gate does NOT do**:
- ❌ Does NOT close the global `G_L3R_BLOCKED` — only narrows it
- ❌ Does NOT elevate 21bao
- ❌ Does NOT enable G-L4 / readiness / gray / Baseline03
- ❌ Does NOT authorize any subsequent NMC field promotion

## 5. Explicit Anti-Promotion Statement

**This PR explicitly states the following non-events** (each must remain true in main after this PR is merged):

- ❌ This PR does NOT modify `model_pool.yaml`
- ❌ This PR does NOT modify `node_model_capability.yaml` (NMC)
- ❌ This PR does NOT promote `runtime_visible` for any node
- ❌ This PR does NOT promote `env_loaded` for any node
- ❌ This PR does NOT promote `model_call_verified` for any node
- ❌ This PR does NOT promote `operator_approved` for any node
- ❌ This PR does NOT perform any model call
- ❌ This PR does NOT perform any credential provisioning
- ❌ This PR does NOT perform any node sync apply
- ❌ This PR does NOT perform any re-SSH / live collection
- ❌ This PR does NOT advance G-L4 / G-READINESS / G-GRAY / G-D-A / G-D-B / PR-7 / Baseline03 / Stage8
- ❌ This PR does NOT declare `G_L3R_BLOCKED_resolved`
- ❌ This PR does NOT declare readiness / G-L4 ready / model_call_verified ready / operator_approved ready
- ❌ This PR does NOT close the 21bao residual

## 6. What This Plan Authorizes

- ✅ Records the canonical evidence state from PR #332
- ✅ Designs a strictly-observed-evidence-based normalization if a future operator authorizes
- ✅ Proposes a future gate for blocker narrowing (design only)
- ✅ Provides tests for plan-integrity verification
- ✅ Provides a machine-readable plan JSON for downstream automation

**This plan does NOT execute any of the above design items.**

## 7. Pointer References

| Reference | Path |
|---|---|
| PR #332 evidence summary | `docs/baseline02/g-l3r-d4-clean-main-evidence.md` |
| PR #332 closure verdict | `.hermes/evidence/g-l3r-d4-clean-main-closure.json` |
| PR #332 per-node receipts | `.hermes/evidence/g-l3r-d4-clean-main-v1/{21bao,5bao,9bao}-receipt.json` |
| 21bao R8 residual | `docs/baseline02/g-l3r-d4-21bao-namespace-asymmetry.md` |
| G-L3R closeout (PR #325) | `docs/baseline02/g-l3r-closeout.md` |
| NMC staleness analysis (PR #328) | `docs/baseline02/nmc-staleness-analysis.md` |
| Plan test | `tests/test_g_l3r_d4_post_evidence_normalization_plan.py` |
| Plan JSON (machine-readable) | `.hermes/evidence/g-l3r-d4-post-evidence-normalization-plan.json` |
| D4 collector | `scripts/worker_attest_layer3_d4_sanctioned_live_evidence.py` |

## 8. Versioning

| Field | Value |
|---|---|
| Evidence anchor (PR #332 collection) | `09b1d97f0cab774e3eb023c9768a40d8165a1d46` |
| Merge anchor (PR #332 merge) | `18807ddbef5d962b67dd102220cdb118432d4f7c` |
| Plan authored at | 2026-07-03 |
| Phase | Post-evidence planning (between PR #332 and any future normalization gate) |
| Lifecycle | planning only — not-readiness, not-G-L4, not-gray, not-Baseline03, not-readiness-ready, not-model_call_verified-ready, not-operator_approved-ready, not-NMC-write-back, not-model_pool-write-back, not-G_L3R_BLOCKED-resolved |
