# G-L4 D4 Model-Call Verification Preflight Plan

**Status**: READ-ONLY PREFLIGHT PLANNING DOCUMENT — not-G-L4-execution, not-readiness, not-gray, not-Baseline03
**Gate ID**: `G-L4-D4-MODEL-CALL-VERIFICATION-PREFLIGHT`
**Anchor**: `ef464b25bd482da8a67886c4b864a4420cfc7e01`
**Created**: 2026-07-04

---

## 1. Purpose

This document is the **preflight admission plan** for G-L4 D4 model-call verification. It:

1. Records the current canonical state after G-L3R D4 runtime_visible closure
2. Defines the D4 model identity and node scope for model_call_verified
3. Proposes an execution plan for the operator to review and authorize
4. Documents failure strategies, evidence schema, and boundary guards

**This is NOT a G-L4 execution ticket.**
**This is NOT a readiness claim.**
**This does NOT produce model_call_verified=true on any node.**

---

## 2. Current Anchor

| Anchor | SHA | Status |
|---|---|---|
| HEAD (local) | `ef464b25bd482da8a67886c4b864a4420cfc7e01` | ALIGNED |
| local main | `ef464b25bd482da8a67886c4b864a4420cfc7e01` | ALIGNED |
| github/main | `ef464b25bd482da8a67886c4b864a4420cfc7e01` | ALIGNED |
| origin/main | `ef464b25bd482da8a67886c4b864a4420cfc7e01` | **R5 CLOSED** (OPS-HYGIENE-008) |
| Open PRs | 0 | CLEAN |

---

## 3. Prerequisite: G-L3R D4 Runtime-Visible Closure (Completed)

| PR | Title | Merge Commit | Layer Impact |
|---|---|---|---|
| PR #332 | evidence: add G-L3R D4 clean-main live receipts | `18807dd` | 5bao/9bao D4 runtime_visible evidence |
| PR #333 | docs: G-L3R D4 post-evidence normalization plan | `cde599d` | post-evidence plan (design only) |
| PR #334 | NMC runtime_visible=true for 5bao/9bao (data layer) | `9681cca` | 5bao/9bao D4 runtime_visible NMC update |
| PR #335 | 21bao residual gate (initial narrowing) | (operator decision) | G_L3R_BLOCKED narrowed to 21bao residual |
| PR #336 | 21bao local runtime-visible evidence | `0a932be` | 21bao D4 runtime_visible local evidence |
| PR #337 | 21bao receipt-to-NMC normalization | `ad10e01` | 21bao D4 runtime_visible → **3-of-3** |
| PR #338 | strict replay test hygiene fix | `0f2fd87` | test-only fix; no production code |
| PR #339 | G-L3R D4 final runtime-visible closure record | `ef464b2` | Closure record, OPS-HYGIENE-008 |

**G-L3R D4 runtime_visible verdict**: `G_L3R_D4_RUNTIME_VISIBLE_3OF3_NORMALIZED`
**Prerequisite for G-L4**: ✅ runtime_visible = true on all 3 nodes
**G-L4 model_call_verified**: Outside G-L3R scope — requires separate authorization

---

## 4. D4 Model Identity

| Field | Value |
|---|---|
| **Active model ID** | `opencode-go-deepseek-v4-pro` |
| **Canonical provider** | `opencode-go` |
| **Provider namespace** | `opencode-go` |
| **Model** | `deepseek-v4-pro` |
| **Primary alias** | `opencode-ds4pro` |
| **Aliases** | `opencode-ds4pro`, `opencode-deepseek-v4-pro` |
| **Key env var** | `OPENCODE_GO_API_KEY` |
| **Base URL env var** | `OPENCODE_GO_BASE_URL` |
| **Runtime provider** | `opencode-go` |
| **Legacy entry** | `deepseek-plan-deepseek-v4-pro` (superseded, `primary_alias=deepseek-v4-pro`) |
| **Invocation form** | `opencode run -m opencode-go/deepseek-v4-pro` |

---

## 5. Node Scope

### 5.1 Current NMC State (all 3 nodes)

| Field | 21bao | 5bao | 9bao |
|---|---|---|---|
| `declared` | true | true | true |
| `synced` | true | true | true |
| `wrapper_valid` | true | true | true |
| `runtime_visible` | true | true | true |
| `env_loaded` | true | true | true |
| `model_call_verified` | unknown | unknown | unknown |
| `operator_approved` | unknown | unknown | unknown |

### 5.2 Node Details

**21bao** (Windows local-exec/control host):
- `opencode.exe` v1.17.8 via `vibedev-tools/opencode/`
- Env vars loaded via Windows user env (no wrapper script — see BLOCKER-01)
- Fastest turnaround: local execution, no SSH dependency
- ⚠️ No `vibedev-opencode.bat` wrapper exists (P16 from deploy skill)

**5bao** (Remote SSH Debian worker, `192.168.5.6:22222`):
- Uses `vibedev-opencode` wrapper + `~/.vibedev-secrets/opencode.env`
- 6-provider credential set verified (deepseek, xiaomi, volcengine, minimax, opencode-go, deepseek-v4-pro)
- SSH key: `debian-vibeworker-ed25519` (same as 9bao)

**9bao** (Remote SSH Debian worker, `192.168.9.6:22222`):
- Uses `vibedev-opencode` wrapper + `~/.vibedev-secrets/opencode.env`
- ⚠️ Known credential gaps: volcengine/minimax providers missing (not relevant for D4)
- `opencode-go` provider was present on both 5bao and 9bao as of I16
- Same SSH key as 5bao

---

## 6. Model-Call Verification Plan (Proposed)

### 6.1 Execution Order (Minimal Blast Radius)

```
Phase 1: 21bao (canary)   → fast local test, no SSH dependency
Phase 2: 5bao (expand)     → remote Debian, proven credential set
Phase 3: 9bao (expand)     → remote Debian, last in sequence
```

Each phase requires **separate operator authorization** before execution.

### 6.2 Model Call Form

```bash
# 21bao (local Windows):
opencode run -m opencode-go/deepseek-v4-pro "Output exactly: G_L4_D4_OK_21BAO"

# 5bao (remote SSH):
ssh -i <key> -p 22222 vibeworker@192.168.5.6 \
  'bash --login -c "opencode run -m opencode-go/deepseek-v4-pro \"Output exactly: G_L4_D4_OK_5BAO\""'

# 9bao (remote SSH):
ssh -i <key> -p 22222 vibeworker@192.168.9.6 \
  'bash --login -c "opencode run -m opencode-go/deepseek-v4-pro \"Output exactly: G_L4_D4_OK_9BAO\""'
```

### 6.3 Acceptance Criteria (per node)

| Criterion | Value |
|---|---|
| Exit code | `0` |
| Expected marker in output | `true` |
| Fallback attempted | `false` |
| model_call_verified verdict | `true` only if ALL 3 criteria met |

### 6.4 Failure Handling

| Scenario | Action |
|---|---|
| Exit code ≠ 0 | **REPORT_AND_STOP**. Do NOT auto-fallback. Do NOT auto-retry with different model. |
| Expected marker missing | **REPORT_AND_STOP**. Output may be truncated or model returned unexpected response. |
| Timeout / network error | Retry exactly once after 30s cooldown. If still fails → REPORT_AND_STOP. |
| Credential missing | Report env var name presence/absence (not value). Do NOT provision. Operator authorizes separately. |
| Node unreachable | REPORT_AND_STOP. Do NOT skip to next node. |
| Fallback detected | REPORT_AND_STOP. Verify invocation string matches `opencode-go/deepseek-v4-pro` exactly. |

### 6.5 Evidence Receipt Schema (per node)

```json
{
  "schema_version": "1.0.0",
  "gate_id": "G-L4-D4-MODEL-CALL-VERIFIED-<NODE>",
  "node": "<node_name>",
  "model_id": "opencode-go-deepseek-v4-pro",
  "invocation_anchor": "<merge_commit_or_head>",
  "call_timestamp": "<ISO8601>",
  "model_call_exit_code": 0,
  "model_call_stderr_truncated": "absent",
  "expected_marker_detected": true,
  "fallback_attempted": false,
  "credential_enum": "present",
  "model_call_verified_verdict": true,
  "note": "model_call_verified=true only if exit_code=0 AND expected_marker_detected=true AND fallback_attempted=false"
}
```

---

## 7. Operator Authorization Checklist

Before each node's model_call_verified execution, the operator must explicitly approve:

- [ ] **Authorization ID**: e.g. `OPERATOR-YYYYMMDD-G-L4-D4-MODEL-CALL-VERIFY-<NODE>-<NNN>`
- [ ] **Work order**: which node, which model, which invocation form
- [ ] **Credential policy**: check env var presence only, do NOT read value, do NOT provision
- [ ] **Failure policy**: STOP on any failure, do NOT auto-fallback, do NOT auto-promote
- [ ] **Write-back policy**: `model_call_verified` set only in bounded PR after operator reviews receipts
- [ ] **Boundary guard**: do NOT transition to G-L4 readiness without separate operator authorization

### Not Authorized (These Require Separate Operator Decision)

| Stage | Authorization Status |
|---|---|
| G-L4 execution (across all nodes) | ❌ NOT authorized |
| G-L4 model_call_verified promotion (NMC write-back) | ❌ NOT authorized |
| operator_approved promotion | ❌ NOT authorized |
| G-READINESS entry | ❌ NOT authorized |
| G-GRAY entry | ❌ NOT authorized |
| G-D-A / G-D-B / PR-7 | ❌ NOT authorized |
| Baseline03 / Stage8 entry | ❌ NOT authorized |

---

## 8. Blockers and Required Operator Decisions

### BLOCKER-01: 21bao no wrapper script (P16)

21bao lacks a `vibedev-opencode.bat` wrapper. Env vars are loaded via Windows user env, but no explicit sourcing mechanism is verified. The `env_loaded=true` in NMC was set during a sync — it may not reflect runtime loading state.

**Operator question**: Accept env-via-Windows-user-env as working for model call? Or require wrapper creation first?

### BLOCKER-02: 9bao credential gaps

9bao has known gaps (volcengine/minimax missing). While D4 uses `opencode-go` provider which was verified present, the credential env for `OPENCODE_GO_API_KEY` on 9bao has not been re-verified since I16 (2026-06-27).

**Operator question**: Pre-verify `OPENCODE_GO_API_KEY` presence on 9bao before model call? Or attempt model call and handle failure per protocol?

### DECISION-01: Execution order

Proposed order: 21bao (canary) → 5bao → 9bao.

**Operator question**: Accept this order? Or start with a remote node?

### DECISION-02: Per-node vs batched authorization

Each node's model_call_verified needs its own operator approval.
**Option A**: Separate per-node approvals (3 separate authorizations)
**Option B**: Single batch authorization covering all 3 nodes

### DECISION-03: NMC write-back strategy

After model_call_verified on a node, should NMC be updated immediately per-node or in a batch?

**Option A**: Immediate per-node NMC write-back (3 PRs, 1 per node)
**Option B**: Batch all 3 nodes into one post-verification NMC update PR

---

## 9. Scope Constraints

```
not-G-L4-ready
not-readiness-ready
not-model_call_verified-ready
not-operator_approved-promotion
not-gray
not-Baseline03
not-Stage8
G-L4-model-call-verification-preflight-drafted
```

## 10. Forbidden Claims (NOT in this preflight)

This preflight document does NOT declare:

- ❌ G-L4 ready
- ❌ readiness ready
- ❌ model_call_verified ready
- ❌ operator_approved ready
- ❌ gray ready
- ❌ Baseline03 ready
- ❌ Stage8 ready
- ❌ Global `G_L3R_BLOCKED` closed
- ❌ D4 model_call_verified promoted to any node
- ❌ G-L4 execution in progress or completed
- ❌ operator_approved promoted

## 11. Production Code Modification Audit

| File | Modified? | Notes |
|---|---|---|
| `scripts/vibe_model_routing_policy.py` | NO | — |
| `scripts/model_pool.yaml` | NO | — |
| `scripts/node_model_capability.yaml` | NO | — |
| `scripts/worker_attest_layer3_reconciliation.py` | NO | — |
| Runtime config / env / credentials | NO | — |
| Model calls performed | NO | Preflight only |
| Credential provisioning performed | NO | — |
| Node sync performed | NO | — |
| SSH / live collection performed | NO | — |

---

## 12. Next Stage Requires Separate Operator Authorization

The next concrete execution phase is one of:

| Candidate | Authorization ID | Scope |
|---|---|---|
| Canary model call on 21bao | `OPERATOR-...-G-L4-D4-MODEL-CALL-VERIFY-CANARY-21BAO` | Single model call on 21bao |
| Model call on 5bao | `OPERATOR-...-G-L4-D4-MODEL-CALL-VERIFY-5BAO` | Single model call on 5bao |
| Model call on 9bao | `OPERATOR-...-G-L4-D4-MODEL-CALL-VERIFY-9BAO` | Single model call on 9bao |

None of these are authorized by this preflight document. Each requires **explicit operator approval** before proceeding.

---

## See Also

- `.hermes/evidence/g-l4-d4-model-call-verification-preflight.json` — machine-readable preflight record
- `.hermes/evidence/g-l3r-d4-final-runtime-visible-closure.json` — G-L3R D4 closure record (predecessor)
- `docs/baseline02/g-l3r-d4-final-runtime-visible-closure.md` — G-L3R D4 closure doc
- `docs/baseline02/baseline02-to-g-l4-preflight-map.md` — previous preflight planning map (PR #331 era)
- `tests/test_g_l4_d4_model_call_verification_preflight.py` — preflight record tests

---

## 13. Test-Governance Amendment (PR #340)

During the PR #340 strengthened self-check, two pre-existing tests in
`tests/test_g_l3r_d4_final_runtime_visible_closure.py` were updated for
robustness:

1. **`test_four_way_anchor_aligned`**: Changed from single-level parent check
   (`HEAD~1` / `main~1`) to ancestry traversal up to 5 generations. This
   supports both pre-merge (branch) and post-merge (main) contexts without
   requiring live HEAD to equal the closure anchor.

2. **`test_open_prs_zero_before_closure_creation`**: Changed from a strict
   live GitHub "0 open PRs" assertion to a **record-based** approach. The
   closure JSON's `four_way_anchor_aligned` and `r5_origin_main_closed` fields
   are the primary evidence. The live open-PR check recognizes PR #340 as a
   documented successor (G-L4 preflight), preventing false failures when
   subsequent preflight PRs exist.

These amendments are **test-governance only**. They do NOT modify:
- The G-L3R D4 closure semantics (3-of-3 runtime_visible, global blocker open)
- The G-L4 preflight semantics (preflight drafted only, no execution)
- Any production code, model_pool, NMC, or runtime config

**Scope constraints unchanged**: `not-G-L4-ready / not-readiness-ready /
not-model_call_verified-ready / not-operator_approved-promotion / not-gray /
not-Baseline03`
