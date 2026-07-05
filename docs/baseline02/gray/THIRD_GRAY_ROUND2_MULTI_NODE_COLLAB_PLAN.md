# Third Gray Round 2 — Multi-Node Collaboration Plan (Draft)

**Status**: PLANNING DOCUMENT — docs-only, no execution, no model call, no SSH dispatch, no live collection
**Phase**: 第三次恢复使用验收 — Round 2 (三节点协作)
**Anchor (base)**: `0ddfe6b2976c4735b7c7403174d4a0563af65760` (PR #359 merge commit, T3-A evidence on main)
**Date**: 2026-07-05
**Author**: VibeDev Orchestrator (consultant role) — under operator authorization `YDV-AUTOPILOT-LOW-RISK-MERGE-QUEUE-AUTHORIZED`
**Supersedes**: nothing (this plan is **adjacent** to `THIRD_GRAY_ACCEPTANCE_PLAN.md`, NOT a replacement)

---

## 0. Scope of This Document

This is a **draft planning document** for Round 2 of the third gray acceptance. It does **NOT**:

- Execute any gray operation (Round 1 / T3-A already completed; this is forward planning only)
- Call any model
- Initiate any SSH session (5bao / 9bao SSH dispatch is **NOT** part of this plan's MVP)
- Provision any credential
- Modify any runtime configuration / node sync state
- Modify `scripts/node_model_capability.yaml` or `scripts/model_pool.yaml`
- Modify `scripts/apply_operator_approval_receipt.py` / `scripts/create_readiness_receipt.py` / F6 / Stage4 / Stage7 gate tests
- Enter Baseline03 / Stage8
- Add any new gate / framework / receipt pipeline

Per `THIRD_GRAY_ACCEPTANCE_PLAN.md` §11 ("What This Plan Does Not Decide"), Round 2 scope was **explicitly out of scope** for the original plan. This document is the **separate plan** that plan §11 reserved.

---

## 1. Goal

**验证 21bao (orchestrator) + 5bao (implementer) + 9bao (reviewer) 三节点协作能力.**

Per operator direction: `21bao orchestrator + 5bao implementer + 9bao reviewer 协作能力`.

This is **NOT** a gray authorization by itself. It is a **planning** document that defines the MVP scope for Round 2, so that — when operator decides to launch Round 2 — there is a written procedure ready.

---

## 2. Why Round 2 Is Different From Round 1 (T3-A)

| Dimension | Round 1 (T3-A, MERGED @ `0ddfe6b`) | Round 2 (this plan, DRAFT) |
|---|---|---|
| Topology | 1 node (21bao local-exec) | 3 nodes (21bao + 5bao + 9bao) |
| Roles | 1 role (explorer) | 3 roles (orchestrator + implementer + reviewer) |
| Model invocations | 1 (deepseek-v4-pro) | 3+ (each node may use a different model in `operator_approved=true` set) |
| Cross-node coordination | none | required (worker attest, evidence transfer, role handoff) |
| Stop surface area | low (single worker) | high (3 nodes × N models × role boundary) |
| Network surface area | none (local) | high (SSH to 5bao/9bao via `vibe_worker_registry.py`) |
| Risk class | single-node smoke | multi-node integration test |
| Pre-requisite issues to clear | none (T3-A proceeded without resolving any I21 issue) | at minimum I21 issues touching cross-node coordination must be assessed |

---

## 3. Carry-Forward I21 Issues That Block Round 2

Per `I21_GRAY_USAGE_BACKLOG.md`, the following issues are **highly relevant** to Round 2 multi-node dispatch. They are listed as **out of scope for this planning document**, but operator must acknowledge them before launching Round 2 execution.

| Issue ID | Severity | Title | Why it matters for Round 2 |
|---|---|---|---|
| **ARCH-001** | Blocker | Architecture contract has no runtime enforcement | Multi-node dispatch cannot be enforced without runtime architecture gate |
| **DSP-002** | Blocker | route-all has no operator-approved checkpoint | Round 2 will use route-all to pick 5bao vs 9bao — gate must exist first |
| **ARCH-003** | High | Manual-only worker flag has no enforcement | 5bao/9bao dispatch must respect manual_only |
| **WRKR-001** | High | Worker registry has no reachability probe | Round 2 needs verified SSH reachability to 5bao/9bao |
| **WRKR-002** | High | No automated recovery on worker failure | One node failure mid-task = stall, no failover |
| **DSP-003** | High | Fallback policy not enforced at runtime | If implementer on 5bao fails, fallback to 9bao must be gated |
| **POOL-001** | High | Extra visible models not blocked from alias resolution | Multi-node × multi-model = alias resolution surface |
| **WIN-001** | High | python3 not available on Windows | 21bao orchestrator dispatch depends on Python on Windows |
| **WIN-002** | High | 21bao has no operational worker runtime | Round 2 makes 21bao **orchestrator**, not just local-exec — this issue becomes directly blocking |
| **TEST-002** | High | No runtime/integration test coverage | Round 2 IS an integration test, but no harness exists to compare against |

**Operator decision required**: Before Round 2 launches, decide which of these 10 I21 issues must be resolved first (per `I21 §4 Recommended Fix Order`, Phase I22 covers 7 of them; I23 covers the remaining 3).

---

## 4. Round 2 MVP Scope (Proposed, Subject to Operator Approval)

### 4.1 Topology

```
[operator]
    │
    ▼
[21bao]  (orchestrator role)
    │
    ├── SSH dispatch ──▶ [5bao] (implementer role)
    │                       │
    └── SSH dispatch ──▶ [9bao] (reviewer role)
```

### 4.2 Role × Node × Model Assignment (Proposed)

| Role | Node | Recommended Model | Reason |
|---|---|---|---|
| **orchestrator** | 21bao | `opencode-go-deepseek-v4-pro` | Round 1 (T3-A) proved 21bao + deepseek-v4-pro works end-to-end; reuse for continuity |
| **implementer** | 5bao | `opencode-go-mimo-v2-5` (or deepseek-v4-pro) | `operator_approved=true` on 5bao; SSH-dispatched via `vibe_worker_registry.py` |
| **reviewer** | 9bao | `opencode-go-mimo-v2-5` (or deepseek-v4-pro) | `operator_approved=true` on 9bao; reviewer needs read-only access, lower blast radius |

**NOT in scope for Round 2 MVP**:
- `opencode-go-qwen3-7-plus` (explicitly in `non_scope` of operator approval receipt)
- 3 models in parallel (Round 2 MVP = 1 model per role)
- More than 1 task per role (Round 2 MVP = 1 task per round)

### 4.3 Task Type (Proposed)

A **docs-only or read-only audit task** that requires **handoff** between roles. Example:

| Task | Orchestrator (21bao) | Implementer (5bao) | Reviewer (9bao) |
|---|---|---|---|
| T2-A | Generate a one-page summary of NMC entries where `operator_approved=unknown` | Write structured markdown table to `docs/baseline02/gray/round2-T2-A-implementer-output.md` | Read implementer output, produce verdict (APPROVE / REJECT / NEEDS_REVISION) |
| T2-B | Generate list of 3 known I21 issues to address next | For each issue, propose fix plan (markdown only) | Review fix plans, rank by risk/effort |

**NOT acceptable for Round 2 MVP**:
- Anything that writes to `main` (no commits, no pushes, no merges from worker nodes)
- Anything that modifies NMC / model_pool / apply tool / F6 gate
- Anything that uses `qwen3-7-plus`
- Anything that requires >3 model calls total across all roles (blast radius)
- Anything requiring >1 retry per node (Round 2 single-pass, manual retry)

---

## 5. Pre-conditions (Operator Acknowledges Before Launching Round 2)

All of the following MUST be true at the moment operator authorizes Round 2 execution:

| # | Pre-condition | Verification |
|---|---|---|
| P2-1 | local main = github main = origin main = `0ddfe6b2976c4735b7c7403174d4a0563af65760` (or later after Round 1 evidence merge) | `git rev-parse` triple check |
| P2-2 | Working tree clean | `git status --porcelain` empty |
| P2-3 | Open PRs = 0 OR operator has explicit exception | `gh pr list --state open` returns `[]` (or exception noted) |
| P2-4 | T3-A evidence (`0ddfe6b`) on main | `git ls-tree main docs/baseline02/gray/THIRD_GRAY_REPORT-20260705.md` non-empty |
| P2-5 | operator_approved=true count = 6 (deepseek-v4-pro ×3 + mimo-v2-5 ×3) | Receipt on main shows `set_equal=true, actual_count=6` |
| P2-6 | qwen3-7-plus × 3 all unknown | Receipt shows `non_scope_check.all_unknown=true` |
| P2-7 | `vibe_worker_registry.py --health-check --node 21bao` ONLINE | Operator runs locally |
| P2-8 | `vibe_worker_registry.py --health-check --node 5bao` ONLINE | Operator runs locally or via SSH |
| P2-9 | `vibe_worker_registry.py --health-check --node 9bao` ONLINE | Operator runs locally or via SSH |
| P2-10 | Operator has acknowledged the 10 I21 carry-forward issues (§3 above) | Explicit `ACKNOWLEDGE_ROUND2_I21_RISKS` reply |
| P2-11 | No active gray / Baseline03 / Stage8 artifacts | Self-evident |
| P2-12 | No in-flight secret / credential / gateway modification | Self-evident |

If **any** P2-* fails → STOP. Do not proceed to Round 2 execution. Re-anchor.

---

## 6. Execution Steps (Operator-Authorized One at a Time)

Each step is a **single operator-authorized action**. No batching.

### Step 1 — Operator acknowledges this Round 2 plan

Operator reply: `ACKNOWLEDGE_ROUND2_PLAN` (proceed) / `REVISE_ROUND2_PLAN` (with edits) / `REJECT_ROUND2_PLAN` (do not proceed)

### Step 2 — Operator acknowledges I21 carry-forward risks

Operator reply: `ACKNOWLEDGE_ROUND2_I21_RISKS` (proceed despite unresolved I21 issues) / `DEFER_ROUND2` (work on I22 issues first)

### Step 3 — Operator selects Round 2 task

Operator reply: `T2_TASK=<task_id>` + `EXECUTE`

### Step 4 — Orchestrator produces role-node-model-provider assignment

Orchestrator reply: full role × node × model × provider × namespace × runtime_provider × wrapper matrix (per `THIRD_GRAY_ACCEPTANCE_PLAN.md` §10 AUTH-3 pattern)

### Step 5 — Operator approves assignment

Operator reply: `APPROVE_ROUND2_ASSIGNMENT` / `REVISE_ROUND2_ASSIGNMENT`

### Step 6 — Worker nodes execute

- 21bao orchestrator dispatches to 5bao (implementer) and 9bao (reviewer) via `vibe_worker_registry.py`
- 5bao executes implementer role, writes output to `docs/baseline02/gray/round2-<task_id>-implementer-output.md` (untracked)
- 9bao reads implementer output (via SSH file fetch), produces reviewer verdict file `docs/baseline02/gray/round2-<task_id>-reviewer-verdict.md` (untracked)
- 21bao orchestrator collects both, writes `docs/baseline02/gray/round2-<task_id>-orchestrator-summary.md` (untracked)

### Step 7 — Operator reviews all 3 outputs

Operator reply: `ACCEPT_ROUND2_OUTPUT` / `REJECT_ROUND2_OUTPUT_RETRY` / `REJECT_ROUND2_OUTPUT_ABORT`

### Step 8 — Operator finalizes Round 2 report

Operator reply: `ACCEPT_ROUND2_REPORT` / `REJECT_ROUND2_REPORT`

---

## 7. Success Criteria (Round 2 PASS)

All of the following MUST hold for Round 2 to be declared PASS:

| # | Criterion |
|---|---|
| R2-S-1 | Pre-conditions P2-1..P2-12 all held at execution time (verified post-hoc) |
| R2-S-2 | All 3 nodes (21bao/5bao/9bao) executed their assigned role without SSH stall |
| R2-S-3 | Only models in `operator_approved=true` set were invoked (deepseek-v4-pro + mimo-v2-5) |
| R2-S-4 | qwen3-7-plus not invoked at any point |
| R2-S-5 | All 3 output files written under `docs/baseline02/gray/round2-*` |
| R2-S-6 | No `git commit` / `git push` / `gh pr create` / `gh pr merge` from worker nodes |
| R2-S-7 | NMC / model_pool / apply tool / F6 / Stage7 / Stage4 files 0 diff |
| R2-S-8 | No STOP condition triggered |
| R2-S-9 | No rollback condition triggered |
| R2-S-10 | Reviewer verdict on 9bao is `APPROVE` (or operator overrides) |
| R2-S-11 | Round 2 report (`THIRD_GRAY_ROUND2_REPORT-<yyyymmdd>.md`) drafted and committed to main via separate PR |

---

## 8. STOP Conditions (Round 2 Specific — Plan §7 Plus Additional)

Any one of these triggers **STOP_AND_REANCHOR** immediately:

| # | Condition |
|---|---|
| R2-STOP-1 | Any of 21bao/5bao/9bao `vibe_worker_registry.py --health-check` returns non-ONLINE |
| R2-STOP-2 | SSH dispatch to 5bao or 9bao fails (network, auth, ProxyCommand) |
| R2-STOP-3 | Worker node (5bao or 9bao) attempts to call qwen3-7-plus |
| R2-STOP-4 | Implementer output file appears outside `docs/baseline02/gray/round2-*` |
| R2-STOP-5 | Reviewer output file appears outside `docs/baseline02/gray/round2-*` |
| R2-STOP-6 | Worker node (5bao or 9bao) attempts `git commit` / `git push` / `gh pr create` |
| R2-STOP-7 | Orchestrator on 21bao auto-fallbacks between models without operator approval |
| R2-STOP-8 | Cross-node evidence transfer fails (cannot fetch implementer output to 9bao) |
| R2-STOP-9 | Reviewer verdict file references secrets, tokens, or credentials |
| R2-STOP-10 | Reviewer verdict suggests modifying NMC / model_pool / apply tool / F6 gate |

Plus all of plan §7 STOP-1..STOP-12 (still apply, expanded scope).

---

## 9. Rollback Conditions (Round 2 Specific)

| # | Condition | Rollback action |
|---|---|---|
| R2-RB-1 | Any worker node SSH failure mid-execution | Manual cleanup of partial output files; record `THIRD_GRAY_ROUND2_ABORT_RECORD-<yyyymmdd>.md` |
| R2-RB-2 | Reviewer verdict = REJECT | Operator may retry once with same task or abort |
| R2-RB-3 | Auto-fallback detected (per R2-STOP-7) | Discard entire Round 2 run; mark FAILED |
| R2-RB-4 | Multiple STOP conditions firing in same run | Mandatory full re-anchor; do not retry without separate plan |

---

## 10. Forbidden Actions (Hard Boundaries — Inherited from Plan §9 + Round 2 Specific)

All of plan §9 F-1..F-14 still apply. Additional:

| # | Forbidden |
|---|---|
| R2-F-1 | Using `opencode-go-qwen3-7-plus` on any node (explicitly in non_scope) |
| R2-F-2 | Allowing any worker node to commit/push/merge to main |
| R2-F-3 | Cross-node SSH key reuse without operator confirmation (5bao/9bao use same key per memory, but each invocation must be traceable) |
| R2-F-4 | Running >1 task per role in this round |
| R2-F-5 | Auto-fallback between deepseek-v4-pro and mimo-v2-5 without operator approval |
| R2-F-6 | Running Round 2 in parallel with any I22/I23 work (no concurrent gray dispatch) |
| R2-F-7 | Treating Round 2 PASS as authorization for Round 3 or multi-cluster federation |

---

## 11. Operator Authorization Points (Round 2)

Each requires **explicit operator reply** in chat. No inference.

| # | Authorization ID | Trigger |
|---|---|---|
| R2-AUTH-1 | `ACKNOWLEDGE_ROUND2_PLAN` | Operator accepts this plan as written |
| R2-AUTH-2 | `ACKNOWLEDGE_ROUND2_I21_RISKS` | Operator acknowledges 10 carry-forward I21 issues |
| R2-AUTH-3 | `T2_TASK=<task_id>` + `EXECUTE` | Operator picks Round 2 task |
| R2-AUTH-4 | `APPROVE_ROUND2_ASSIGNMENT` | Operator accepts role × node × model × provider matrix |
| R2-AUTH-5 | `ACCEPT_ROUND2_OUTPUT` / `REJECT_ROUND2_OUTPUT_RETRY` / `REJECT_ROUND2_OUTPUT_ABORT` | Operator decides on combined 3-output set |
| R2-AUTH-6 | `ACCEPT_ROUND2_REPORT` / `REJECT_ROUND2_REPORT` | Operator accepts final Round 2 report |

---

## 12. What This Round 2 Plan Does Not Decide

- Whether to **fix I21 issues first** (operator may decide to work on I22/I23 before Round 2 launch — separate plan)
- Whether to **expand Round 2 to 2+ tasks per role** (Round 2 MVP = 1 task per role)
- Whether to **add a 4th node** (Round 2 MVP = 3 nodes only)
- Whether to **enter Baseline03** (separate operator authorization, separate plan)
- Whether to **enter Stage8** (separate operator authorization, separate plan)
- Whether to **flip qwen3-7-plus from unknown to true** (separate operator authorization)
- Whether to **modify any protected file** in scripts/, tests/, docs/baseline02/{operator-approvals,readiness}/

This plan is intentionally **narrow**: 3 nodes, 1 task, 1 round, 3 model calls max.

---

## 13. Open Issues Carried Forward (Round 2 Specific)

In addition to the 10 I21 issues in §3:

| Issue | Source | Why out of scope for this plan |
|---|---|---|
| Operator must verify `vibe_worker_registry.py --health-check` works for 5bao/9bao | `I21 §13 WRKR-001` | Health check assumed for plan pre-conditions; actual implementation is I22 work |
| `vibe_worker_registry.py` SSH dispatch needs explicit `ssh_key_path` for auditability | `I21 §13 WRKR-003` | Worker registry currently uses SSH config instead of explicit path |
| Cross-node evidence transfer protocol not standardized | implicit from `I21 §13 RSYNC-001` | Round 2 assumes manual `scp` or worker attest; standardization is I23 work |
| Reviewer role semantics not formalized in `docs/` | implicit | Round 2 MVP defines reviewer's job ad-hoc; formalization is separate plan |

---

## 14. Change Log

| Date | Change | Author |
|---|---|---|
| 2026-07-05 | Initial draft (this document) | VibeDev Orchestrator under operator authorization |

---

## 15. Operator Sign-off Block

```
Operator:  ____________________________________
Date:      ____________________________________
Decision:  □ ACKNOWLEDGE_ROUND2_PLAN
           □ REVISE_ROUND2_PLAN (see notes)
           □ REJECT_ROUND2_PLAN
Notes:     ____________________________________
           ____________________________________
```

---

## 16. Appendix — Relationship to Existing Artifacts

| Artifact | Path | Relationship |
|---|---|---|
| Third Gray Plan (Round 1) | `docs/baseline02/gray/THIRD_GRAY_ACCEPTANCE_PLAN.md` | Round 1 plan; Round 2 is adjacent (this doc) |
| Third Gray Report (T3-A) | `docs/baseline02/gray/THIRD_GRAY_REPORT-20260705.md` | Round 1 report (single-node smoke); Round 2 will produce its own report |
| T3-A Output | `docs/baseline02/gray/third-gray-task-output-T3-A-20260705-165222.md` | T3-A evidence; Round 2 will produce its own outputs |
| Readiness receipt | `docs/baseline02/readiness/receipts/readiness-receipt-20260705-150000.yaml` | Operator_approved=6, qwen all unknown; Round 2 plan inherits these constraints |
| I21 backlog | `docs/reports/I21_GRAY_USAGE_BACKLOG.md` | 10 issues carried forward (§3); rest out of scope |
| Architecture contract | `docs/OPERATOR_ORCHESTRATOR_CONTRACT.md` | Round 2 follows same operator-orchestrator-executor pattern |