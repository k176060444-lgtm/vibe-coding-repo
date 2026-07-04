# G-L4 Readiness Bridge Planning Record

**Status**: READ-ONLY PLANNING DOCUMENT — not-readiness-promotion, not-operator_approved-execution, not-G-READINESS, not-gray, not-Baseline03

**Gate ID**: `G-L4-READINESS-BRIDGE-PLANNING`

**Current Anchor**: `316640d236d276a019d0549c05501aea899117db`

---

## 1. Current Anchor and Merge Chain

| Reference | Item | SHA / ID |
|:----------|:-----|:---------|
| **Anchor** | HEAD / local main / github main / origin main | `316640d` |
| **Open PRs** | 0 | — |
| **R5** | origin/main synced | ✅ |

### Merge Chain (Bounded)

| PR | Merge Commit | Scope | Merged |
|:--:|:-------------|:------|:------:|
| #341 | `d78d546` | G-L4 D4 21bao model-call canary evidence | ✅ |
| #342 | `7fc883b` | G-L4 D4 5bao model-call canary evidence | ✅ |
| #343 | `6a8b8ab` | G-L4 D4 9bao model-call canary evidence | ✅ |
| #344 | `e805894` | G-L4 D4 3-of-3 model_call_verified NMC normalization | ✅ |
| #345 | `316640d` | R1 seven-test hygiene fix (7 pre-existing failures) | ✅ |

---

## 2. D4 State per Node

| Node | `runtime_visible` | `model_call_verified` | `operator_approved` | `env_loaded` |
|:----:|:-----------------:|:---------------------:|:-------------------:|:-----------:|
| **21bao** | `true` (G-L3R) | `true` (G-L4, PR #341) | **`unknown`** | `true` |
| **5bao**  | `true` (G-L3R) | `true` (G-L4, PR #342) | **`unknown`** | `true` |
| **9bao**  | `true` (G-L3R) | `true` (G-L4, PR #343) | **`unknown`** | `true` |

### Operator-Controlled Fields (Not Promoted)

The following fields are **operator-controlled** and remain at their pre-G-L4 value (operator_approved remains unknown):

| Field | Status |
|:------|:-------|
| `operator_approved` | **unknown** — unchanged, operator decision required |
| `env_loaded` | unchanged from G-L3R normalization |
| NMC: `model_pool.yaml` | NOT modified |
| NMC: `node_model_capability.yaml` | NOT modified beyond PR #344 G-L4 normalization |
| Readiness / Gray / Baseline03 | **NOT entered** |

---

## 3. Evidence Map

| Node | runtime_visible Evidence | model_call_verified Evidence |
|:----:|:------------------------|:----------------------------|
| **21bao** | PR #336 (21bao local) | PR #341 (D4 canary: `deepseek-plan/deepseek-v4-pro`) |
| **5bao**  | PR #332 (5bao via SSH worker attest) | PR #342 (D4 canary: `deepseek-plan/deepseek-v4-pro`) |
| **9bao**  | PR #332 (9bao via SSH worker attest) | PR #343 (D4 canary: `opencode-go/deepseek-v4-pro`) |

---

## 4. Namespace Asymmetry Summary

The canonical model identity is `opencode-go-deepseek-v4-pro` in the `opencode-go` central namespace. Node-specific concrete invocation differs by node:

| Node | Provider Namespace | Concrete Invocation | Canonical Provider |
|:----:|:------------------|:--------------------|:------------------|
| **21bao** | `deepseek-plan` | `deepseek-plan/deepseek-v4-pro` | `opencode-go` |
| **5bao**  | `deepseek-plan` | `deepseek-plan/deepseek-v4-pro` | `opencode-go` |
| **9bao**  | `opencode-go`   | `opencode-go/deepseek-v4-pro`  | `opencode-go` |

This is a **node-specific runtime provider routing configuration difference**, **NOT**:
- ❌ A fallback (no alternative provider was attempted on failure)
- ❌ Provider drift (the canonical identity `opencode-go-deepseek-v4-pro` is consistent)
- ❌ A provider-wide failure (both `deepseek-plan` and `opencode-go` work correctly)
- ✅ A deliberate per-node routing decision: 21bao/5bao use `deepseek-plan` due to local runtime configuration, 9bao uses the canonical `opencode-go` directly

**Canonical model ID consistency**: All 3 nodes map to the same canonical identity `opencode-go-deepseek-v4-pro`. The provider namespace difference is transparent at the model identity layer.

---

## 5. Readiness Prerequisites

### 5.1 operator_approved — Explicit Receipt Required

Readiness promotion requires an explicit `operator_approved: true` receipt for each node. This is a **qualitative operator decision**, not derivable from `model_call_verified`.

| Prerequisite | Status | Required For |
|:-------------|:------:|:-------------|
| 21bao `operator_approved = true` | ❌ `unknown` | Readiness on 21bao |
| 5bao `operator_approved = true` | ❌ `unknown` | Readiness on 5bao |
| 9bao `operator_approved = true` | ❌ `unknown` | Readiness on 9bao |

### 5.2 Stage7 F6 Gate — Fail-Closed Until operator_approved

The Stage7 F6 readiness gate (`tests/test_stage7_f6_readiness_gate.py`) is **design-correct** in its current behavior: it blocks when `operator_approved` is `unknown`. This is expected and intentional. The 8 pre-existing Stage7 gate failures will **not** resolve until `operator_approved` is set to `true` for the relevant entries.

The gate failures **do not** block read-only planning. They **do** block readiness promotion.

### 5.3 Stage4 Matrix Drift — Known Gap

The 8 pre-existing Stage4 test failures reflect a known NMC matrix drift after PR #344 (G-L4 normalization). The NMC per-node matrix contains routing-name entries (`deepseek-deepseek-v4-pro`, `xiaomi-mimo-v2-5`, etc.) and free models that are not fully synchronized with `model_pool.yaml`. This gap requires one of:

- A separate bounded test-only PR to align fixture expectations with the current NMC state (recommended, can proceed in parallel)
- A documented waiver before readiness promotion acknowledging the matrix drift as non-blocking

**Stage4 failures are NOT blockers for read-only planning.** They are maintenance debts.

### 5.4 Readiness NOT Derivable from model_call_verified Alone

`model_call_verified = true` on 3 nodes is **necessary but not sufficient** for readiness.
- Readiness requires **both** `model_call_verified` AND `operator_approved`
- `model_call_verified` is a technical verification (canary passed)
- `operator_approved` is a policy/authorization decision (operator signs off)
- No automated test or gate can substitute for operator authorization

---

## 6. Blocked / Unblocked Matrix

| Action | Blocked By | Classification |
|:-------|:-----------|:---------------|
| Read-only readiness bridge planning | **NOT BLOCKED** | ✅ Planning can proceed |
| Stage7 F6 gate test fix | `operator_approved = unknown` | 🟡 Requires operator decision first |
| Stage4 matrix drift test fix | None (test-only PR) | ✅ Can be parallel |
| Readiness promotion on 21bao | `operator_approved = unknown` | 🔴 Requires explicit operator approval |
| Readiness promotion on 5bao | `operator_approved = unknown` | 🔴 Requires explicit operator approval |
| Readiness promotion on 9bao | `operator_approved = unknown` | 🔴 Requires explicit operator approval |
| G-READINESS / G-GRAY / Baseline03 / Stage8 | Requires readiness bridge completion | 🔴 Not yet applicable |

### What CAN proceed now (read-only, no authorization requirement)

- Planning and documentation
- Stage4 matrix drift test fix
- operator_approved decision document / evidence preparation

### What MUST NOT proceed without operator authorization

- Setting `operator_approved = true` in NMC
- Calling readiness gate against production NMC
- Any SSH, model call, credential provisioning, node sync
- Entering G-READINESS, G-GRAY, Baseline03, Stage8

---

## 7. Subsequent Authorization Steps

The following sequence is required to progress from current state (`model_call_verified = true`, `operator_approved = unknown`) to readiness:

### Step A: operator_approved Decision (Operator-Authorized)

1. Operator reviews D4 canary receipts (PR #341, #342, #343)
2. Operator explicitly approves each node: "批准 21bao D4 model_call_verified 作为 operator_approved"
3. A bounded PR sets `operator_approved = true` in NMC for the approved nodes

### Step B: Readiness Gate Pass

1. With `operator_approved = true`, F6 gate can evaluate readiness
2. Stage7 tests would transition from "fail-closed (expected)" to "pass (eligible)"
3. Stage4 drift should be resolved or waived before readiness declaration

### Step C: Readiness Declaration

1. All 3 nodes have: `runtime_visible = true`, `model_call_verified = true`, `operator_approved = true`, `env_loaded = true`
2. Readiness gate passes for all intended entries
3. Operator declares G-L4 readiness

---

## 8. Non-Promotion Statement

This document is a **read-only planning record**. It does NOT:

- ❌ Set `operator_approved = true`
- ❌ Modify `scripts/node_model_capability.yaml`
- ❌ Modify `scripts/model_pool.yaml`
- ❌ Modify runtime config
- ❌ Enter readiness / G-READINESS / gray / Baseline03 / Stage8
- ❌ Authorize SSH, model call, credential provisioning, node sync
- ❌ Authorize Stage4 or Stage7 test modifications
- ❌ Imply that `model_call_verified = true` is equivalent to readiness

All fields and behaviors documented here are **descriptions of current state**, not actions taken.

---

## 9. Known Caveats

| Caveat | Scope | Status |
|:-------|:------|:-------|
| Stage4 matrix drift (8 failures) | NMC matrix entries not synced with pool | ✅ Documented — non-blocking for planning |
| Stage7 fail-closed (8 failures) | F6 gate blocks on `operator_approved = unknown` | ✅ Expected — will resolve after Step A |
| `test_open_prs_zero_before_closure_creation` | Live-state test, cleared after PR #345 merge | ✅ Resolved |
