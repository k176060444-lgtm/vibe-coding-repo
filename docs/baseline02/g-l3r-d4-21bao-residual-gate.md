# G-L3R D4 21bao Residual Gate

## Status (Updated via PR #338)

| Field | Value |
|---|---|
| Gate ID | `G-L3R-D4-21BAO-RESIDUAL-GATE` |
| Current Verdict | `G_L3R_D4_RUNTIME_VISIBLE_3OF3_NORMALIZED` |
| Legacy Verdict | `G_L3R_D4_BLOCKER_NARROWED_TO_21BAO_RESIDUAL_ONLY` (superseded) |
| Anchor | `0a932be4fd6d12760e8c5e6400044644864e003c` |
| Merge Commit | `0a932be4fd6d12760e8c5e6400044644864e003c` |
| Operator Decision (current) | `OPERATOR-20260704-G-L3R-D4-21BAO-NMC-NORMALIZATION-006` |
| Operator Decision (legacy) | `OPERATOR-20260703-G-L3R-D4-RESIDUAL-GATE-001` |
| Created | 2026-07-03 |
| Updated | 2026-07-04 (this PR #338) |
| Predecessor Plans | PR #333, PR #335, PR #336 |
| NMC Normalization (5bao/9bao) | PR #334 |
| NMC Normalization (21bao) | PR #338 (this PR) |
| Closes Global Blocker | **NO** — narrowed to higher layers |

## Background

Per the G-L3R D4 post-evidence normalization plan (PR #333), this gate
originally implemented the blocker narrowing decision once the two preconditions
were met:

1. **NMC runtime_visible updated for 5bao/9bao** — completed via PR #334
2. **21bao asymmetry documented** — completed via PR #324

After PR #335 the gate verdict was `G_L3R_D4_BLOCKER_NARROWED_TO_21BAO_RESIDUAL_ONLY`
(2-of-3 confirmed at runtime_visible layer).

After PR #336 produced canonical local-config runtime-visible evidence for 21bao
(`deepseek-plan.deepseek-v4-pro` matched in `~/.config/opencode/opencode.jsonc`),
PR #338 normalizes that evidence into NMC, elevating 21bao D4 to
`runtime_visible=True`. **All 3 nodes are now 3-of-3 at the runtime_visible layer.**

The gate verdict is updated to `G_L3R_D4_RUNTIME_VISIBLE_3OF3_NORMALIZED`,
but `closes_global_blocker=false` is preserved because the global G_L3R_BLOCKED
remains open at the higher layers (model_call_verified, operator_approved,
G-L4 preflight, readiness, G-D-A/B, G-GRAY, PR-7, Baseline03, Stage8).

## Evidence State

| Node | runtime_visible | Evidence Source | Classification |
|---|---|---|---|
| **21bao** | `True` ✅ | PR #336, approval `OPERATOR-20260704-G-L3R-D4-21BAO-LOCAL-RT-EVIDENCE-005`, anchor `2ec1778e`, merge `0a932be`, matched_key `deepseek-plan.deepseek-v4-pro` | `PR336_normalized` |
| **5bao** | `True` ✅ | PR #332, approval `OPERATOR-20260703-G-L3R-D4-LIVE-EVIDENCE-003`, anchor `09b1d97` | `closure_evidence` |
| **9bao** | `True` ✅ | PR #332, approval `OPERATOR-20260703-G-L3R-D4-LIVE-EVIDENCE-003`, anchor `09b1d97` | `closure_evidence` |

### Evidence Chain

```
PR #319–#322     stdin-pipe fix, PATH fix, section_name fix (D4 collector)
PR #324          21bao namespace asymmetry documentation
PR #332          clean-main live evidence receipts & closure (5bao/9bao)
PR #333          post-evidence normalization plan (design only)
PR #334          NMC runtime_visible normalization for 5bao/9bao
PR #335          21bao residual gate (initial narrowing)
PR #336          21bao local runtime-visible evidence + receipt
PR #338          NMC runtime_visible normalization for 21bao (this PR)
```

## Gate Verdict Semantics

### Verdict Name (current)

`G_L3R_D4_RUNTIME_VISIBLE_3OF3_NORMALIZED`

**Note**: This is 3-of-3 at the **runtime_visible** layer only. It is NOT
3-of-3 (and not 2-of-3) at any other layer (`model_call_verified`,
`operator_approved`, `env_loaded`, `G-L4 readiness`, `readiness`). The
3-of-3 normalization at runtime_visible is **not** a promotion to
3-of-3 readiness or model invocation. See "What This Verdict Does NOT
Mean" below.

### What This Verdict Means

- **All 3 nodes D4 runtime_visible = True** — evidence-based:
  - **5bao / 9bao**: PR #332 clean-main evidence, NMC normalized via PR #334
  - **21bao**: PR #336 local config evidence (matched_key
    `deepseek-plan.deepseek-v4-pro`), NMC normalized via PR #338 (this PR)
- **G-L3R D4 runtime_visible layer is fully normalized** (3-of-3)
- **Layer-specific guarantee**: this is a CONFIGURATION FACT, not an
  INVOCATION FACT. `runtime_visible=True` means the local config/wrapper can
  SEE the D4 model entry; it does **NOT** assert successful invocation.

### What This Verdict Does NOT Mean

| Claim | Is this verdict claiming it? |
|---|---|
| Global `G_L3R_BLOCKED` is resolved/closed | **NO** — global blocker narrows further but stays open |
| `model_call_verified` is True for any node | **NO** — explicitly false on all 3 nodes |
| `operator_approved` is True for any node | **NO** — explicitly false on all 3 nodes |
| G-L4 ready | **NO** |
| Readiness ready | **NO** |
| model_call_verified ready | **NO** |
| operator_approved ready | **NO** |
| DEU assignment complete | **NO** |
| Smoke test performed | **NO** |
| Model invocation attempted | **NO** — read-only evidence path only |
| Credential provisioning performed | **NO** |
| NMC/model_pool write-back to other fields | **NO** — only runtime_visible on D4 entry |
| 3-of-3 at `model_call_verified`/`operator_approved` | **NO** — explicitly false at those layers. **Not 3-of-3** for any readiness / model invocation layer. |

## Reconciliation Impact

### Before PR #332[¹]

```
Blockers:
  - deepseek-v4-pro: runtime_visible/fixture mismatch on all 3 nodes
```

### After PR #335 (initial gate)

```
Blockers:
  - deepseek-v4-pro (5bao/9bao): runtime_visible=True via evidence
    (PR #332, PR #334).
  - deepseek-v4-pro (21bao): residual asymmetry (R8 documented).
```

### After PR #338 (this PR)

```
Blockers:
  - deepseek-v4-pro (all 3 nodes): runtime_visible=True via evidence
    (5bao/9bao via PR #332 evidence, PR #334 NMC; 21bao via PR #336
    local config evidence, PR #338 NMC normalization).
  - HIGHER LAYER blockers remain open:
      * model_call_verified (3/3 still false)
      * operator_approved (3/3 still false)
      * env_loaded (per-model status, promotion not authorized)
      * G-L4 preflight, G-READINESS, G-D-A/B, G-GRAY, PR-7,
        Baseline03, Stage8 — all not authorized.
Global G_L3R_BLOCKED narrowed to higher-layer promotion — does not close globally.
```

### Blocker Summary Update

The reconciliation blocker text in `scripts/worker_attest_layer3_reconciliation.py`
is updated from "21bao residual" to "higher-layer promotion (model_call_verified /
operator_approved / G-L4 readiness)".

## Unblock Criteria (Updated)

| Criteria | Status |
|---|---|
| 5bao/9bao evidence collected | ✅ Complete (PR #332) |
| 5bao/9bao NMC normalization applied | ✅ Complete (PR #334) |
| 21bao asymmetry documented | ✅ Complete (PR #324) |
| Initial operator narrowing decision | ✅ Issued (PR #335) |
| 21bao local evidence collected | ✅ Complete (PR #336) |
| 21bao NMC normalization applied | ✅ Complete (PR #338, this PR) |
| 21bao runtime_visible resolution | ✅ Complete (PR #336 + #338) |
| model_call_verified smokes | ❌ Not authorized (G-L4 scope) |
| operator_approved | ❌ Not authorized |
| G-L4 preflight | ❌ Not authorized |
| Readiness / G-READINESS | ❌ Not authorized |
| DEU assignment (G-D-A) | ❌ Not authorized |
| DEU enablement (G-D-B) | ❌ Not authorized |
| G-GRAY / GRAY_ACCEPTANCE | ❌ Not authorized |
| PR-7 / Baseline03 / Stage8 | ❌ Not authorized |

## 21bao Specifics

The 21bao D4 evidence is distinct from 5bao/9bao:

- 5bao/9bao evidence collected via SSH at `~/.config/opencode/opencode.jsonc`
  on the remote workers and used the canonical `opencode-go` namespace.
- 21bao evidence collected via local file read on `vibedev = 21bao =
  Windows local-exec/control node` (no SSH). 21bao's local config uses the
  `deepseek-plan` concrete provider namespace (which is the actual worker
  local namespace, distinct from the central `opencode-go` abstract
  namespace). PR #324 documented this asymmetry as R8.

The matched concrete key is `deepseek-plan.deepseek-v4-pro`, present in
21bao's `~/.config/opencode/opencode.jsonc`. This is sufficient to assert
`runtime_visible=True` at the local-config layer. It is **not** sufficient
to assert anything about invocation, environment loading, credential
status, or endpoint reachability (those are deferred to higher layers).

## Scope Constraints

This gate (and this PR #338) do NOT authorize:

- Model call / inference
- Credential provisioning
- Node sync apply
- SSH / live collection
- Runtime field promotion (`env_loaded` / `model_call_verified` / `operator_approved`)
- model_pool.yaml modification
- NMC modification beyond `runtime_visible` on the single D4 entry
- DEU assignment (G-D-A)
- G-L4 / G-READINESS / G-GRAY / G-D-B / PR-7 / Baseline03 / Stage8

---

[¹]: The "before" state is the canonical state at PR #332 closure merge
(`18807ddbef5d962b67dd102220cdb118432d4f7c`), before NMC normalization.
