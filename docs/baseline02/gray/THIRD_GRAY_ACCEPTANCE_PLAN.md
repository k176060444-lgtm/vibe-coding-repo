# Third Gray Acceptance Plan

**Status**: PLANNING DOCUMENT — not gray execution, not model call, not SSH, not runtime modification
**Phase**: 第三次恢复使用 / 第三次灰度验收
**Anchor (base)**: `341f62c37d221599fba8c6d7a1648bdf1ecd3cf2` (PR #357 merge commit)
**Date**: 2026-07-05
**Author**: VibeDev Orchestrator (consultant role) — written under operator authorization `THIRD-GRAY-ACCEPTANCE-PLAN-PR-AUTHORIZED`

---

## 0. Scope of This Document

This document is **only a plan**. It does NOT:

- Execute any gray operation
- Call any model
- Initiate any SSH session
- Provision any credential
- Modify any runtime configuration / node sync state
- Modify `scripts/node_model_capability.yaml`
- Modify `scripts/model_pool.yaml`
- Modify `scripts/apply_operator_approval_receipt.py`
- Modify `scripts/create_readiness_receipt.py`
- Modify F6 / Stage7 / Stage4 gate tests
- Enter Baseline03 / Stage8
- Add any new gate / framework / receipt pipeline

This document defines the **MVP scope** for a single, low-risk, real-business
task that the operator can authorize to validate that the small cluster is
usable again. The validation target is **operator's hands-on confirmation**,
not another automated receipt.

---

## 1. Goal

**修复小集群，使 operator 能完成第三次恢复使用验收。**

The small cluster is operational at the technical gate level (PR #357 readiness
receipt on main shows PASS, operator_approved=true count=6, qwen3-7-plus
explicitly excluded). What remains unverified is whether **a real business
task, dispatched to a real worker on a real node, actually works end-to-end**
under operator supervision.

The third gray acceptance is the **first controlled end-to-end real-task
execution after the readiness pipeline was completed**. It is intentionally
narrow — one node, one model, one task — so that if anything fails, the cause
is localizable to a single variable.

### 1.1 What "acceptance" means here

| Layer | Status before this plan |
|---|---|
| Technical gate (NMC, model_call_verified, env_loaded, wrapper_valid) | ✅ PASS (PR #341-#344, PR #356, PR #357) |
| Operator policy gate (operator_approved) | ✅ PASS for 6 entries (deepseek-v4-pro ×3 + mimo-v2-5 ×3); qwen3-7-plus ×3 explicitly unknown |
| End-to-end real-task usability | ❓ Unverified — this plan closes that gap |

### 1.2 What this plan is NOT

This plan is **not**:
- A new gate or framework
- A new receipt pipeline
- A readiness promotion or gray authorization by itself
- A Stage8 / Baseline03 entry point
- A test suite expansion

It is a **written procedure** the operator can read, approve, and then
execute one action at a time.

---

## 2. Scope (MVP)

**MVP = 1 node × 1 model × 1 low-risk real task.**

### 2.1 Why this scope

- **One variable at a time**: if it fails, root cause is localizable.
- **1 node**: avoids cross-node orchestration regressions (which first / second gray previously hit per `I21_GRAY_USAGE_BACKLOG.md` WRKR-002).
- **1 model**: avoids cross-model comparison noise.
- **1 task**: avoids multi-step rollbacks.
- **Low-risk task**: limits blast radius if model output is unexpected.

### 2.2 Recommended node × model

| Field | Value | Reason |
|---|---|---|
| **Node** | `21bao` (local-exec on Windows control) | Lowest network risk: no SSH, no cross-node latency, no ProxyCommand failure. Failures are observable on the operator's own screen. |
| **Model** | `opencode-go-deepseek-v4-pro` | `model_call_verified=true` on 21bao (PR #341); `wrapper_valid=true`; `env_loaded=true`; `operator_approved=true`. Canonical namespace + deepseek-plan runtime provider on 21bao per `g-l4-readiness-bridge-planning.md` §4. |
| **NOT** | `opencode-go-qwen3-7-plus` | Explicitly in `non_scope` of operator approval receipt — operator_approved stays unknown. |
| **NOT** | `opencode-go-mimo-v2-5` (this round) | Approved but reserved as fallback if deepseek-v4-pro fails; not the primary MVP target. |

### 2.3 Task type

**`docs-only` or read-only audit.** Specifically:

- Read a file from the repo
- Produce a structured summary or comparison
- Write the output to `docs/baseline02/gray/` as a new artifact (NOT to `docs/baseline02/operator-approvals/`, NOT to `docs/baseline02/readiness/receipts/`, NOT to root-level docs)
- Do **NOT** run `git commit`, `git push`, `gh pr create/merge`, or modify any tracked file

**Acceptable task examples** (operator picks one):

| Task ID | Description |
|---|---|
| `T3-A` | Summarize the contents of `docs/baseline02/I21_GRAY_USAGE_BACKLOG.md` by severity and produce a one-page severity-ranked table. |
| `T3-B` | Read `scripts/node_model_capability.yaml` and report which `operator_approved` entries are still `unknown`. |
| `T3-C` | Compare `docs/baseline02/00-current-anchor.md` against `git log main --oneline -20` and report any drift. |
| `T3-D` | List the open issues from `I21_GRAY_USAGE_BACKLOG.md` that block this gray round (per operator's selection). |

**Not acceptable for this round**:
- Anything that writes to `main` (no commits, no pushes, no merges)
- Anything that modifies NMC / model_pool / apply tool / F6 gate
- Anything that calls multiple nodes in parallel
- Anything that uses `qwen3-7-plus`
- Anything that touches secrets / credentials / gateway config

---

## 3. Pre-conditions

All of the following MUST be true **at the moment operator authorizes
execution** of the chosen task. Operator verifies each.

| # | Pre-condition | Verification |
|---|---|---|
| P-1 | local main = github main = origin main | `git rev-parse main` / `github/main` / `origin/main` all equal `341f62c37d221599fba8c6d7a1648bdf1ecd3cf2` |
| P-2 | Working tree clean | `git status --porcelain` empty |
| P-3 | Open PRs = 0 | `gh pr list --state open` returns `[]` |
| P-4 | This PR (the plan PR) is merged into main, OR the operator has explicitly accepted "plan not yet merged" exception | Self-evident from PR state |
| P-5 | Readiness receipt on main | `git ls-tree main docs/baseline02/readiness/receipts/readiness-receipt-20260705-150000.yaml` returns non-empty |
| P-6 | `operator_approved=true` count = 6 | Receipt shows `set_equal=true`, `actual_count=6`, `expected_count=6` |
| P-7 | qwen3-7-plus × 3 all unknown | Receipt shows `non_scope_check.all_unknown=true` |
| P-8 | 21bao local-exec reachable | `vibe_worker_registry.py --health-check --node 21bao` shows ONLINE (operator runs locally) |
| P-9 | No active gray / Baseline03 / Stage8 artifacts | `docs/baseline02/gray/THIRD_GRAY_*` should not yet exist beyond this plan |
| P-10 | No in-flight secret / credential / gateway modification | Self-evident |

If **any** P-* fails → STOP. Do not proceed to execution. Re-anchor.

---

## 4. Execution Steps

Each step is a **single operator-authorized action**. No batching.

### Step 1 — Operator reads and approves this plan

- Operator reads this document
- Operator replies in chat with one of:
  - `APPROVE_THIRD_GRAY_PLAN` (proceed)
  - `REJECT_THIRD_GRAY_PLAN` (do not proceed)
  - `REVISE_THIRD_GRAY_PLAN` (operator specifies required edits)

### Step 2 — Operator selects the task

- Operator picks one of T3-A / T3-B / T3-C / T3-D (or proposes a different docs-only task)
- Operator replies with `TASK=<task_id>` and explicit `EXECUTE`

### Step 3 — Orchestrator dispatches the task

- Orchestrator does **NOT** self-execute
- Orchestrator dispatches a single explorer + a single implementer role
- Assigned node = `21bao`
- Assigned model = `opencode-go-deepseek-v4-pro`
- Assigned provider namespace = `deepseek-plan` (per `g-l4-readiness-bridge-planning.md` §4)
- Runtime provider = `opencode-go` (canonical)
- Orchestrator produces a **role assignment plan** before any model call

### Step 4 — Operator approves the role assignment

- Operator reads the role assignment table
- Operator replies `APPROVE_ASSIGNMENT` (or `REVISE_ASSIGNMENT`)

### Step 5 — Worker executes the task

- Worker invokes the chosen model on 21bao via local-exec
- Worker captures: input prompt hash, output text, duration, model_call_verified exit code, token count (if surfaced), stdout/stderr tail
- Worker writes output to `docs/baseline02/gray/third-gray-task-output-<task_id>-<yyyymmdd-hhmmss>.md`
- Worker does NOT commit, NOT push

### Step 6 — Operator reviews output

- Operator reads the output file
- Operator replies with one of:
  - `ACCEPT_TASK_OUTPUT` (proceed to report)
  - `REJECT_TASK_OUTPUT_RETRY` (worker reruns once)
  - `REJECT_TASK_OUTPUT_ABORT` (move to rollback section)

### Step 7 — Operator reviews and finalizes the gray report

- See §12 for report template
- Operator decides: gray PASS / FAIL / PARTIAL

---

## 5. Success Criteria

All of the following MUST hold for the third gray to be declared **PASS**:

| # | Criterion |
|---|---|
| S-1 | Pre-conditions P-1 through P-10 all held at execution time (verified post-hoc by re-running checks) |
| S-2 | Task executed on 21bao with `opencode-go-deepseek-v4-pro` only |
| S-3 | qwen3-7-plus was not invoked at any point (verified by `model_call_verified` exit + receipt entry) |
| S-4 | Output file written under `docs/baseline02/gray/`, NOT under `docs/baseline02/operator-approvals/` or `docs/baseline02/readiness/receipts/` |
| S-5 | No `git commit` / `git push` / `gh pr create` / `gh pr merge` occurred during execution |
| S-6 | NMC / model_pool / apply tool / F6 gate / Stage7 gate / Stage4 gate files show 0 diff before and after (operator verifies with `git diff`) |
| S-7 | No STOP condition (see §7) was triggered |
| S-8 | No rollback condition (see §8) was triggered |
| S-9 | Operator explicitly accepted the task output (Step 6 `ACCEPT_TASK_OUTPUT`) |
| S-10 | Gray report (see §12) committed to `docs/baseline02/gray/THIRD_GRAY_REPORT-<yyyymmdd>.md` |

If S-1 to S-9 hold but S-10 fails (operator does not commit the report), the
gray is **PARTIAL** — not FAIL, but not PASS either.

---

## 6. Pre-Execution Checklist (Operator runs)

```bash
# 1. Three-way SHA alignment
git rev-parse main         # expect 341f62c37d221599fba8c6d7a1648bdf1ecd3cf2
git rev-parse github/main  # expect 341f62c37d221599fba8c6d7a1648bdf1ecd3cf2
git rev-parse origin/main  # expect 341f62c37d221599fba8c6d7a1648bdf1ecd3cf2

# 2. Clean tree + no open PRs
git status --porcelain                    # expect empty
gh pr list --state open --json number     # expect []

# 3. Receipt sanity (read-only)
git show main:docs/baseline02/readiness/receipts/readiness-receipt-20260705-150000.yaml | head -25

# 4. 0 diff on protected files
git diff main -- scripts/node_model_capability.yaml scripts/model_pool.yaml scripts/apply_operator_approval_receipt.py scripts/create_readiness_receipt.py tests/test_stage7_f6_readiness_gate.py
# expect empty

# 5. 21bao health
python scripts/vibe_worker_registry.py --health-check --node 21bao
# expect ONLINE
```

---

## 7. STOP Conditions

Any one of these triggers **STOP_AND_REANCHOR** immediately. No debate, no
"just one more try". Stop, capture state, wait for operator.

| # | Condition |
|---|---|
| STOP-1 | Any `gh` command beyond `gh pr list --state open` and `gh pr view` is invoked without explicit operator approval |
| STOP-2 | Any `git commit` / `git push` to any remote occurs |
| STOP-3 | Any `git push --force` / `git rebase` invoked |
| STOP-4 | Model output contains BIDI / zero-width / control / non-printable characters (CP7 scan failure) |
| STOP-5 | Model output requests credentials, secrets, tokens, or API keys (any form) |
| STOP-6 | Model output suggests modifying NMC / model_pool / apply tool / F6 gate |
| STOP-7 | Worker attempts to call `opencode-go-qwen3-7-plus` at any point |
| STOP-8 | Cross-node SSH dispatch attempted (must remain on 21bao local-exec) |
| STOP-9 | Any side effect outside `docs/baseline02/gray/` (writes to repo root, operator-approvals, readiness/receipts, scripts/, tests/) |
| STOP-10 | `vibe_worker_registry.py --health-check --node 21bao` returns non-ONLINE |
| STOP-11 | Any change to `scripts/conversational_intake_gate.py` or any Hermes profile file |
| STOP-12 | Any change to gateway service, Task Scheduler, env overlay, credentials |

When STOP fires: capture `git status`, last 100 lines of worker log, model
call receipt (if any), and present to operator. Do not auto-recover.

---

## 8. Rollback Conditions

If a STOP condition already produced a side effect (e.g. an unwanted file
was written), the operator triggers rollback. Rollback is **manual** —
orchestrator does not auto-rollback.

| # | Condition | Rollback action |
|---|---|---|
| RB-1 | Task output file contains forbidden content (BIDI, secret, etc.) | Delete `docs/baseline02/gray/third-gray-task-output-*.md`; record `THIRD_GRAY_ROLLBACK_RECORD-<yyyymmdd>.md` |
| RB-2 | Worker wrote outside `docs/baseline02/gray/` | `git checkout -- <unwanted path>` for tracked files; `rm` for untracked; record rollback |
| RB-3 | Model call receipt shows qwen3-7-plus was invoked | Discard entire gray run; mark FAILED; do not retry same task without operator-decided model swap |
| RB-4 | NMC / model_pool / apply tool / F6 gate shows unexpected diff | `git checkout -- <path>`; trigger SEPARATE audit before any further gray |
| RB-5 | Operator issues `ABORT_THIRD_GRAY` at any point | Capture state, write `THIRD_GRAY_ABORT_RECORD-<yyyymmdd>.md`, halt |
| RB-6 | Multiple STOP conditions firing in same run | Mandatory full re-anchor before retry |

Rollback records are committed under `docs/baseline02/gray/` with explicit
"ROLLBACK" / "ABORT" naming.

---

## 9. Forbidden Actions (Hard Boundaries)

| # | Forbidden |
|---|---|
| F-1 | Entering gray / Baseline03 / Stage8 from this plan alone — separate operator authorization required for each |
| F-2 | Adding any new gate, framework, validator, or test pipeline |
| F-3 | Modifying NMC / model_pool / apply tool / F6 / Stage4 / Stage7 gate files |
| F-4 | Auto-fallback to another model without explicit operator approval |
| F-5 | Auto-restart of gateway service |
| F-6 | Touching default Hermes profile skills/plugins/cron/memories |
| F-7 | Writing secrets, tokens, cookies, or API keys anywhere |
| F-8 | Force-push to any remote branch |
| F-9 | Modifying `docs/baseline02/operator-approvals/draft/draft-receipt-001-staged-6-entries.yaml` — it is a deliberate stale fixture |
| F-10 | Calling `opencode-go-qwen3-7-plus` |
| F-11 | Cross-node SSH dispatch in this round |
| F-12 | Squashing / rebasing / amending any existing merged commit on main |
| F-13 | Pre-emptively drafting THIRD_GRAY_REPORT before operator's `ACCEPT_TASK_OUTPUT` |
| F-14 | Treating any PASS receipt as gray authorization |

---

## 10. Operator Authorization Points

Each of these requires an **explicit operator reply** in chat. No inference.

| # | Authorization ID | Trigger |
|---|---|---|
| AUTH-1 | `APPROVE_THIRD_GRAY_PLAN` | Operator accepts this plan as written |
| AUTH-2 | `TASK=<task_id>` + `EXECUTE` | Operator picks task and orders execution |
| AUTH-3 | `APPROVE_ASSIGNMENT` | Operator accepts the role-node-model-provider assignment |
| AUTH-4 | `ACCEPT_TASK_OUTPUT` / `REJECT_TASK_OUTPUT_RETRY` / `REJECT_TASK_OUTPUT_ABORT` | Operator decides on worker output |
| AUTH-5 | `ACCEPT_THIRD_GRAY_REPORT` / `REJECT_THIRD_GRAY_REPORT` | Operator accepts final report |
| AUTH-6 | `AUTHORIZE_NEXT_GRAY_ROUND` (optional) | Only if operator wants to expand scope (NOT in this MVP) |

Each AUTH-N is a **single-step authorization**. No carrying forward. No
"since AUTH-1 passed, AUTH-2 is implicit".

---

## 11. What This Plan Does Not Decide

- Whether to expand to 3 nodes in a fourth round (separate plan)
- Whether to enable `opencode-go-mimo-v2-5` as primary (separate plan)
- Whether to enter Baseline03 (separate operator authorization, separate plan)
- Whether to enter Stage8 (separate operator authorization, separate plan)
- Whether to flip `opencode-go-qwen3-7-plus` from `unknown` to `true` (separate operator authorization)
- Whether to modify any protected file in `scripts/`, `tests/`, `docs/baseline02/{operator-approvals,readiness}/`

This plan is intentionally **narrow**: 1 node, 1 model, 1 task, 1 round.

---

## 12. Gray Result Report Template

After execution, commit the following file at:

```
docs/baseline02/gray/THIRD_GRAY_REPORT-<yyyymmdd>.md
```

Use this template (operator may add fields, not remove):

```markdown
# Third Gray Acceptance Report

**Report ID**: THIRD-GRAY-<yyyymmdd>-<task_id>
**Date**: <yyyymmdd>
**Operator**: <operator name/alias>
**Base anchor**: 341f62c37d221599fba8c6d7a1648bdf1ecd3cf2

## 1. Task
- Task ID: T3-A / T3-B / T3-C / T3-D / <custom>
- Description: <one sentence>

## 2. Assignment
- Node: 21bao
- Model: opencode-go-deepseek-v4-pro
- Provider namespace: deepseek-plan
- Runtime provider: opencode-go
- Worker role: <explorer / implementer / etc.>

## 3. Execution
- Started at: <ISO timestamp>
- Ended at: <ISO timestamp>
- Duration: <seconds>
- Model call exit code: <0 / non-zero>
- Output file: docs/baseline02/gray/third-gray-task-output-<task_id>-<yyyymmdd-hhmmss>.md
- Output file SHA256: <sha256>

## 4. STOP / Rollback
- Any STOP triggered: <yes / no>
- Any rollback executed: <yes / no>
- If yes, see: docs/baseline02/gray/THIRD_GRAY_ROLLBACK_RECORD-<yyyymmdd>.md

## 5. Verdict
- Pre-conditions P-1..P-10 all held: <yes / no>
- Success criteria S-1..S-10 all met: <yes / no>
- Operator final decision: PASS / FAIL / PARTIAL

## 6. Operator Sign-off
- Operator reply: <AUTH-5 reference>
- Next round authorized: <yes / no / deferred>
```

---

## 13. Open Issues Carried Forward (from I21)

These are **known but out of scope** for this gray round. Recorded so the
operator can decide whether they block the next round.

| Issue ID | Title | Severity | Why out of scope |
|---|---|---|---|
| ARCH-001 | Architecture contract has no runtime enforcement | blocker | Not needed for 1-node local-exec MVP |
| ARCH-002 | 21bao health_status permanently UNKNOWN in route-all | medium | Operator runs `--health-check` manually this round |
| ARCH-003 | Manual-only worker flag has no enforcement | high | Not needed (no multi-worker dispatch this round) |
| WRKR-001 | Worker registry has no reachability probe | high | Operator runs health check manually this round |
| WRKR-002 | No automated recovery on worker failure | high | Single task; manual recovery sufficient this round |
| WRKR-003 | SSH credential key path empty in registry | low | 21bao is local-exec; not applicable this round |

---

## 14. Change Log

| Date | Change | Author |
|---|---|---|
| 2026-07-05 | Initial plan (this document) | VibeDev Orchestrator under operator authorization |

---

## 15. Operator Sign-off Block

```
Operator:  ____________________________________
Date:      ____________________________________
Decision:  □ APPROVE_THIRD_GRAY_PLAN
           □ REVISE_THIRD_GRAY_PLAN (see notes)
           □ REJECT_THIRD_GRAY_PLAN
Notes:     ____________________________________
           ____________________________________
```