# Baseline02 → G-L4 Preflight Planning Map

**Status**: READ-ONLY PLANNING DOCUMENT — not-G-L4-execution, not-readiness, not-gray, not-Baseline03
**Phase**: Preflight — between Baseline02 (complete) and any future G-L4 authorization
**Anchor**: `7385cc47253a864e4f406789c432351917b762af`
**Created**: 2026-07-03

---

## 1. Purpose

This document maps the gap between the completed **Baseline02 / G-L3R D4** phase and what would be required to authorise entry into **G-L4** (the next planned phase after Baseline02). It is a **planning aid for the operator**, not an execution ticket, not a readiness claim, and not a G-L4 gate.

**Scope constraints**: `not-readiness / not-G-L4-execution / not-gray / not-Baseline03`

---

## 2. Current State (Baseline02 Complete)

| Domain | Status | Evidence |
|---|---|---|
| D4 runtime_visibility blocker | `CLOSED_BY_5BAO_9BAO` | PR #322, receipts in `.hermes/evidence/` |
| D4 collector fixes | Merged | PR #319 (stdin-pipe), #320 (PATH/wrapper), #321 (section_name) |
| Dynamic evidence anchor | Merged | PR #323 |
| Origin/main stale hygiene | Resolved | OPS-HYGIENE-001B, OPS-HYGIENE-002 |
| 21bao namespace asymmetry | Documented residual | PR #324 |
| G-L3R closeout doc | Complete | `docs/baseline02/g-l3r-closeout.md` |
| Baseline02 docs system | 5 files, cross-linked | #325–#329 |
| P2 test-noise (TypeError) | Fixed | PR #330 |
| All tests | 3063 green | `python -m pytest tests/ --collect-only` |
| Open PRs | 0 | `gh pr list` |
| Working tree | clean | `git status` |
| 4-way anchor | `7385cc47` aligned | HEAD / local main / github/main / origin/main |

### Active Model Set (8 opencode-go models, `enabled_assigned`)

All 8 models are symmetrically configured across 21bao, 5bao, 9bao.

| Model ID | Alias | NMC `runtime_visible` (21bao) | NMC `runtime_visible` (5bao) | NMC `runtime_visible` (9bao) |
|---|---|---|---|---|
| `opencode-go-deepseek-v4-flash` | opencode-ds4flash | `True` | `True` | `True` |
| `opencode-go-deepseek-v4-pro` | opencode-ds4pro | `unknown` | `unknown` | `unknown` |
| `opencode-go-glm-5-1` | opencode-glm51 | `True` | `True` | `True` |
| `opencode-go-glm-5-2` | opencode-glm52 | `True` | `True` | `True` |
| `opencode-go-kimi-k2-6` | opencode-kimi26 | `True` | `True` | `True` |
| `opencode-go-mimo-v2-5-pro` | opencode-mimopro | `True` | `True` | `True` |
| `opencode-go-qwen3-7-max` | opencode-qwen37max | `True` | `True` | `True` |
| `opencode-go-qwen3-7-plus` | opencode-qwen37plus | `True` | `True` | `True` |

**Note**: All 8 models have `wrapper_valid=True` and `env_loaded=True` on all 3 nodes. All 8 have `model_call_verified=unknown` and `operator_approved=unknown` (except a single historical entry). NMC `runtime_visible=True` for 7/8 models across all 3 nodes — including 21bao — indicating the NMC has been updated since the D4 evidence.

---

## 3. Known Residuals (pre-G-L4)

These are gaps that would need operator decisions **before or during G-L4**, but are **not P0/P1 blockers** for the current Baseline02 phase.

| # | Residual | Classification | G-L4 Relevance | Current Phase |
|---|---|---|---|---|
| R8 | 21bao `runtime_visible_observed=false` for `deepseek-v4-pro` | Non-blocking, documented | Needs resolution before G-L4 can treat 21bao as fully active | Baseline02 documented |
| — | 16 `declared_enabled_unassigned` models/node | Correct state | G-D-A/G-D-B scope, not G-L4 | Baseline02 complete |
| — | NMC stale vs live evidence for D4 model | Documented (#328) | NMC regeneration = pre-G-L4 candidate task | Baseline02 documented |
| — | 14/25 entries/node `env_loaded=unknown` | Expected — unassigned | No action needed for G-L4 | Current normal state |
| — | 24/25 entries/node `model_call_verified=unknown` | Expected | G-D-A/G-D-B phase for assignment | Current normal state |
| — | 24/25 entries/node `operator_approved=unknown` | Expected | G-D-A/G-D-B phase for approval | Current normal state |

---

## 4. G-L4 Candidate Scope

G-L4 is the next planned phase after Baseline02. Based on current architecture and PR #276 operator-orchestrator contract, G-L4 would likely encompass:

### 4.1 NMC Regeneration

Regenerate `scripts/node_model_capability.yaml` from current `model_pool.yaml` to reflect:
- Live evidence from D4 (5bao/9bao `deepseek-v4-pro` runtime_visible)
- Current credential/env state for all `enabled_assigned` models
- Any model lifecycle changes since last generation (2026-07-01)

**Risk**: Low, bounded to a single file regeneration.

### 4.2 Model Call Verification (Smoke Tests)

Run smoke tests for the 8 `enabled_assigned` opencode-go models to fill `model_call_verified` from `unknown` → `true`/`false`:
- One model call per model per node (21bao, 5bao, 9bao)
- Expected: 24 model calls (8 models × 3 nodes)
- Acceptance criteria: each returns a non-error response within timeout

**Risk**: Medium — consumes model call quota.

### 4.3 Provider Namespace Resolution (21bao Asymmetry)

Resolve the 21bao provider namespace asymmetry documented in PR #324:
- 21bao `~/.config/opencode/opencode.jsonc` has no `opencode-go` provider block
- All 8 opencode-go models are nested under `deepseek-plan`, `volcengine-plan`, `xiaomi-plan`, `minimax-plan`
- Needs: new provider block or alias mapping in 21bao's local OpenCode config

**Risk**: Medium — requires SSH to 21bao (Windows node via local-exec) or manual operator intervention.

### 4.4 Credential Audit

Verify that all 8 opencode-go models have valid API credentials and endpoints on all 3 nodes:
- `credential_status: present` in model_pool.yaml is a declaration, not a runtime verification
- SSH to 5bao/9bao to inspect `opencode.jsonc` key/endpoint env vars
- Local config read on 21bao

**Risk**: Low-Medium — read-only SSH audit, no credential values exposed.

### 4.5 NMC `operator_approved` and `model_call_verified` Elevation

After smoke tests pass, set `operator_approved=True` and `model_call_verified=True` for the tested models in NMC.

**Risk**: Low — deterministic file edit after successful verification.

---

## 5. Explicit G-L4 Gate Conditions (Non-Exhaustive Draft)

For G-L4 to be authorised and executed, the following preconditions should be satisfied:

### 5.1 Bounded Work Order
- [ ] Operator-issued explicit work order with scope, constraints, and STOP conditions
- [ ] Explicit `not-readiness`, `not-gray`, `not-Baseline03` guard in the work order
- [ ] Operator-approved model quota budget (if model calls are required)

### 5.2 SSH Authorisation
- [ ] Operator explicitly authorises SSH to each target node (21bao, 5bao, 9bao as needed)
- [ ] SSH scope limited to specific commands/config reads per work order
- [ ] No SSH for model calls (terminal is used for model calls, not SSH)

### 5.3 Model Call Authorisation
- [ ] Operator explicitly authorises model call scope (which models, which nodes, how many calls)
- [ ] Quota-aware: model calls should not consume production budget unless authorised
- [ ] `model_call_verified` fill is a deterministic binary outcome, not a performance benchmark

### 5.4 NMC Update Authorisation
- [ ] Operator approves NMC field elevation (`runtime_visible`, `model_call_verified`, `operator_approved`)
- [ ] File-scope guard: only `scripts/node_model_capability.yaml` may be modified
- [ ] Pre/post SHA256 recorded for audit

### 5.5 Credential Guard
- [ ] No credential values stored in PRs, commits, or evidence files
- [ ] Credential provenance auditable via env var name + SHA256 (never value)

### 5.6 Phase Guard
- [ ] Explicit `not-readiness` — G-L4 is a technical verification phase, not a deployment readiness phase
- [ ] Explicit `not-gray` — Gray is a separate phase requiring separate authorisation
- [ ] Explicit `not-Baseline03` — Baseline03 is a future phase requiring separate authorisation

---

## 6. Risk Assessment

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Preflight map mistaken for G-L4 execution | Medium | High | Each section marked `not-readiness/not-G-L4/not-gray/not-Baseline03` |
| R2 | NMC `runtime_visible` status misinterpreted as readiness | Low | Medium | Reference D4 closeout that this is infrastructure not readiness |
| R3 | 21bao asymmetry blocks model calls on that node | Medium | High | Flag asymmetry as a G-L4 precondition |
| R4 | Scope creep from planning to execution | Low | High | Work order boundaries per task; STOP conditions enforced |
| R5 | SSH during G-L4 triggers stale origin/main (R5 recurrence) | Low | Medium | SSH-RO guard: SSH is for config INSPECTION only |
| R6 | Model call quota exhaustion on production provider | Medium | High | Pre-authorise quota cap per model |

---

## 7. Counter-Indications (Reasons NOT to Proceed)

The following conditions would argue **against** authorising G-L4:

1. **Active P0/P1 unresolved** — If a new P0/P1 blocker is discovered during preflight analysis, pause G-L4 until resolved.
2. **Anchor instability** — If 4-way anchor alignment breaks during the preflight phase, fix alignment before any execution.
3. **Credential failure on majority of models** — If >50% of the 8 enabled_assigned models have stale/missing credentials, G-L4 model calls would largely fail.
4. **21bao asymmetry proves deeper than expected** — If inspection reveals provider namespace mapping issues beyond just the `opencode-go` block.
5. **Operator bandwidth** — If operator cannot commit to timely reviews, G-L4 would stall mid-execution.

---

## 8. Recommended Pre-G-L4 Sequence

| Step | Action | Authorisation | Scope | Gate |
|---|---|---|---|---|
| 1 | **Operator decision: proceed to G-L4?** | Operator | Read-only approval | Explicit `choose option` |
| 2 | **SSH audit (5bao/9bao)** | Operator per-node | Read-only `opencode.jsonc` env/key check | SSH scope auth |
| 3 | **SSH or local audit (21bao)** | Operator | Read-only local config check | SSH scope auth (or manual) |
| 4 | **NMC regeneration** | Operator | Single file `node_model_capability.yaml` | Full PR cycle |
| 5 | **Model call smoke tests** | Operator + quota | 8 models × 3 nodes | One PR for evidence |
| 6 | **NMC elevation PR** | Operator | `model_call_verified` + `operator_approved` | Full PR cycle |
| 7 | **Phase transition decision** | Operator | G-L4 results → next phase | Blind review |

**Note**: Steps 2–7 are illustrative, not authorised. Each requires a separate operator decision.

---

## 9. Versioning

| Field | Value |
|---|---|
| Anchor | `7385cc47253a864e4f406789c432351917b762af` |
| Phase | Preflight — before G-L4 |
| Lifecycle | Read-only planning — not-readiness, not-G-L4-execution, not-gray, not-Baseline03 |
| Created | 2026-07-03 |

---

## 10. Pointers

| Reference | Path |
|---|---|
| G-L3R closeout | `docs/baseline02/g-l3r-closeout.md` |
| 21bao asymmetry | `docs/baseline02/g-l3r-d4-21bao-namespace-asymmetry.md` |
| NMC staleness | `docs/baseline02/nmc-staleness-analysis.md` |
| Anchor | `docs/baseline02/00-current-anchor.md` |
| Baseline02 entry | `docs/baseline02/README.md` |
| D4 closure evidence | `.hermes/evidence/g-l3r-d4-runtime-visible-blocker-closed.json` |
| NMC (source) | `scripts/node_model_capability.yaml` |
| Model pool (source) | `scripts/model_pool.yaml` |
| D4 collector | `scripts/worker_attest_layer3_d4_sanctioned_live_evidence.py` |
