# G-L3R D4 21bao Residual Gate

## Status

| Field | Value |
|---|---|
| Gate ID | `G-L3R-D4-21BAO-RESIDUAL-GATE` |
| Verdict | `G_L3R_D4_BLOCKER_NARROWED_TO_21BAO_RESIDUAL_ONLY` |
| Anchor | `9681cca87abff7d89d73ade8ee165f3a7b8e6fbf` |
| Operator Decision | `OPERATOR-20260703-G-L3R-D4-RESIDUAL-GATE-001` |
| Created | 2026-07-03 |
| Predecessor Plans | PR #333 (`g-l3r-d4-post-evidence-normalization-plan.md`) |
| NMC Normalization | PR #334 |

## Background

Per the G-L3R D4 post-evidence normalization plan (PR #333), this gate implements
the blocker narrowing decision once the two preconditions are met:

1. **NMC runtime_visible updated for 5bao/9bao** — completed via PR #334
2. **21bao asymmetry documented** — completed via PR #324

## Evidence State

| Node | runtime_visible | Evidence Source | Classification |
|---|---|---|---|
| **21bao** | `unknown` (residual) | NMC notes R8 | `R8_documented_residual` |
| **5bao** | `True` | PR #332, approval `OPERATOR-20260703-G-L3R-D4-LIVE-EVIDENCE-003`, anchor `09b1d97` | `closure_evidence` |
| **9bao** | `True` | PR #332, approval `OPERATOR-20260703-G-L3R-D4-LIVE-EVIDENCE-003`, anchor `09b1d97` | `closure_evidence` |

### Evidence Chain

```
PR #319-#322          stdin-pipe fix, PATH fix, section_name fix (D4 collector)
PR #332               clean-main live evidence receipts & closure
PR #333               post-evidence normalization plan (design only)
PR #334               NMC runtime_visible normalization for 5bao/9bao
PR #324               21bao namespace asymmetry documentation
```

## Gate Verdict Semantics

### Verdict Name

`G_L3R_D4_BLOCKER_NARROWED_TO_21BAO_RESIDUAL_ONLY`

### What This Verdict Means

- **5bao D4 runtime_visible = True** — evidence-based, PR #332 confirmed,
  PR #334 normalized into NMC. The 5bao D4 blocker is resolved.
- **9bao D4 runtime_visible = True** — evidence-based, PR #332 confirmed,
  PR #334 normalized into NMC. The 9bao D4 blocker is resolved.
- **21bao D4 runtime_visible = unknown/residual** — asymmetric local config
  (R8 documented, PR #324). The 21bao D4 blocker is NOT resolved, but it
  is a **residual** that does not block 5bao/9bao progression.

### What This Verdict Does NOT Mean

| Claim | Is this verdict claiming it? |
|---|---|
| Global `G_L3R_BLOCKED` is resolved | **NO** — global blocker narrows but stays open |
| 21bao runtime_visible is True | **NO** — must remain unknown/residual |
| G-L4 ready | **NO** |
| Readiness ready | **NO** |
| model_call_verified ready | **NO** |
| operator_approved ready | **NO** |
| DEU assignment complete | **NO** |
| NMC/model_pool write-back occurred | **NO** — PR #334 was NMC normalization, not write-back |
| 21bao is decommissioned | **NO** — awaits operator decision on residual handling |

## Reconciliation Impact

### Before (at PR #332)[¹]

```
Blockers:
  - deepseek-v4-pro: runtime_visible/fixture mismatch on all 3 nodes
```

### After (this gate)

```
Blockers:
  - deepseek-v4-pro (5bao/9bao): runtime_visible=True via evidence
    (PR #332, PR #334). Node-level D4 blocker resolved.
  - deepseek-v4-pro (21bao): residual asymmetry (R8 documented).
    Global G_L3R_BLOCKED narrowed to 21bao residual only.
```

### Blocker Summary Update

The reconciliation blocker text in `scripts/worker_attest_layer3_reconciliation.py`
is updated from "on all 3 nodes" to "on 21bao (5bao/9bao resolved via evidence)".

## Unblock Criteria (Updated)

| Criteria | Status |
|---|---|
| 5bao/9bao evidence collected | ✅ Complete (PR #332) |
| NMC normalization applied | ✅ Complete (PR #334) |
| 21bao asymmetry documented | ✅ Complete (PR #324) |
| Operator narrowing decision | ✅ Issued (this gate) |
| 21bao runtime_visible resolution | ⏳ Operator decision required — see below |
| model_call_verified smokes | ❌ Not authorized |
| operator_approved | ❌ Not authorized |

## 21bao Residual — Available Operator Options

The 21bao D4 blocker is a residual asymmetry: 21bao uses `opencode.jsonc`
(no `opencode-go` provider block) while 5bao/9bao use `model_pool.yaml` with
`opencode-go` declared. This is documented as R8.

The operator has two options for 21bao:

| Option | Description | Impact |
|---|---|---|
| **Keep residual** | Accept 21bao local-exec asymmetry as permanent. No further D4 action. | 21bao D4 remains unresolved. G_L3R_BLOCKED remains open for 21bao. |
| **Configure 21bao** | Add `opencode-go` provider block to 21bao's `opencode.jsonc`. | Requires separate operator decision, SSH/tooling access, bounded PR for NMC update. |

## Scope Constraints

This gate does NOT authorize:

- Model call / inference
- Credential provisioning
- Node sync apply
- SSH / live collection
- runtime field promotion (`env_loaded`/`model_call_verified`/`operator_approved`)
- model_pool.yaml modification
- NMC modification (beyond reading current state)
- DEU assignment (G-D-A)
- G-L4 / G-READINESS / G-GRAY / G-D-B / PR-7 / Baseline03 / Stage8

---

[¹]: The "before" state is the canonical state at PR #332 closure merge
(`18807ddbef5d962b67dd102220cdb118432d4f7c`), before NMC normalization.
