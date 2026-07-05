# Third Gray Acceptance — Remaining Gaps Catalog

**Status**: PLANNING / EVIDENCE — docs-only, not a gate, not a framework
**Phase**: 第三次恢复使用验收 — 缺口清单 (T3-A Round 1 → Round 2 之间)
**Anchor (base)**: `0ddfe6b2976c4735b7c7403174d4a0563af65760`
**Date**: 2026-07-05
**Author**: VibeDev Orchestrator under operator authorization `YDV-AUTOPILOT-LOW-RISK-MERGE-QUEUE-AUTHORIZED`

---

## 0. Purpose

This catalog consolidates **all known gaps** that remain after T3-A Round 1 closure. It is the **single source of truth** for "what still needs to happen before the third gray acceptance is fully complete".

It is intentionally **not a gate** and **not a framework**. It is a reference checklist that operators can use to decide next steps.

---

## 1. Gap Categories

| Category | Count | Status |
|---|:---:|---|
| I21 carry-forward (architecture / worker / dispatch / runtime) | 10 | open (per `I21_GRAY_USAGE_BACKLOG.md`) |
| Plan §11 "What This Plan Does Not Decide" | 6 | not-decided |
| T3-A report §10 caveats | 2 | noted |
| T3-A self-assessment S-10 | 1 | pending operator AUTH-5 (now ✅ via PR #359 merge, but operator review of §9 conclusion block still pending) |
| Round 2 prerequisites | 5 | planning only (per `THIRD_GRAY_ROUND2_MULTI_NODE_COLLAB_PLAN.md`) |
| Operator decision points (deferred) | 3 | pending operator |

---

## 2. I21 Carry-Forward (10 Issues)

These are the I21 issues that **directly block or shape** Round 2 multi-node execution. They are **NOT** automatically resolved by T3-A success.

### 2.1 Blockers (must fix before any multi-node dispatch)

| Issue ID | Severity | Title | Round 2 Relevance |
|---|---|---|---|
| **ARCH-001** | Blocker | Architecture contract has no runtime enforcement | Without runtime architecture gate, 5bao/9bao dispatch cannot be enforced |
| **DSP-002** | Blocker | route-all has no operator-approved checkpoint | Round 2 will use route-all to pick implementer vs reviewer — gate must exist |

### 2.2 High (significant risk to Round 2)

| Issue ID | Severity | Title | Round 2 Relevance |
|---|---|---|---|
| **ARCH-003** | High | Manual-only worker flag has no enforcement | 5bao/9bao dispatch must respect manual_only |
| **WRKR-001** | High | Worker registry has no reachability probe | Round 2 needs verified SSH reachability to 5bao/9bao |
| **WRKR-002** | High | No automated recovery on worker failure | One node failure mid-task = stall, no failover |
| **DSP-003** | High | Fallback policy not enforced at runtime | If implementer on 5bao fails, fallback to 9bao must be gated |
| **POOL-001** | High | Extra visible models not blocked from alias resolution | Multi-node × multi-model = alias resolution surface |
| **WIN-001** | High | python3 not available on Windows | 21bao orchestrator dispatch depends on Python on Windows |
| **WIN-002** | High | 21bao has no operational worker runtime | Round 2 makes 21bao **orchestrator**, not just local-exec — this issue becomes directly blocking |
| **TEST-002** | High | No runtime/integration test coverage | Round 2 IS an integration test, but no harness exists to compare against |

### 2.3 Operator Decision

- **Decision required**: Per `I21 §4 Recommended Fix Order`, Phase I22 covers 7 of these 10 issues (ARCH-001, ARCH-003, WRKR-001, DSP-002, POOL-001, WIN-001, TEST-001). The remaining 3 are I23.
- **Operator may choose**:
  - (a) Work on I22 issues first (separate plan, separate authorization)
  - (b) Proceed to Round 2 with these issues acknowledged as known risks
  - (c) Reduce Round 2 scope to avoid issues (e.g., skip multi-node, stay single-node)
- **Default per `THIRD_GRAY_ROUND2_MULTI_NODE_COLLAB_PLAN.md` §5 P2-10**: Operator must explicitly `ACKNOWLEDGE_ROUND2_I21_RISKS` before Round 2 launch.

---

## 3. Plan §11 "What This Plan Does Not Decide" (6 Items)

Per `THIRD_GRAY_ACCEPTANCE_PLAN.md` §11, the following were **explicitly out of scope** for Round 1 (T3-A) and remain undecided:

| # | Not-Decided Item | Current Status | Round 2 Plan Status |
|---|---|---|---|
| ND-1 | Whether to expand to 3 nodes in a fourth round | Round 2 plan drafted (§THIRD_GRAY_ROUND2_MULTI_NODE_COLLAB_PLAN.md) | **resolved** (this catalog entry) |
| ND-2 | Whether to enable `opencode-go-mimo-v2-5` as primary | Round 2 §4.2 lists as alternative | **partial** (recommended for Round 2, not yet promoted to "primary") |
| ND-3 | Whether to enter Baseline03 | not entered | **deferred** |
| ND-4 | Whether to enter Stage8 | not entered | **deferred** |
| ND-5 | Whether to flip qwen3-7-plus from unknown to true | still unknown | **deferred** (Round 2 explicitly excludes it) |
| ND-6 | Whether to modify any protected file in scripts/, tests/, docs/baseline02/{operator-approvals,readiness}/ | 0 diff maintained | **deferred** (operator decision pending) |

---

## 4. T3-A Report §10 Caveats (2 Items)

Per `THIRD_GRAY_REPORT-20260705.md` §10.2, two caveats were noted:

| # | Caveat | Status | Operator Action Required |
|---|---|---|---|
| C-1 | Token count not surfaced in stdout (opencode default `--format default`) | Documented | None for Round 1; Round 2 may require `--format json` (separate authorization) |
| C-2 | Call #1 write tool auto-rejection event (opencode auto-rejected model's Write attempt) | Documented as "safety net working as designed" | Operator may log to I21 backlog as "tool calling default" risk |

**Operator decision recommended**:
- C-1: Whether Round 2 should mandate `--format json` for token attribution
- C-2: Whether to record C-2 as a new I21 issue (e.g., I22.x — "opencode default behavior includes write tool; explicit Read-only prompt required for read-only tasks")

---

## 5. T3-A Self-Assessment §9 Operator Conclusion (1 Item)

The T3-A report §9 contains an `Operator Review Conclusion` block with placeholders for operator name, date, and decision (`ACCEPT_THIRD_GRAY_REPORT` vs `REJECT_THIRD_GRAY_REPORT`).

**Status of placeholders** (as of this catalog creation):
- Operator name: **not filled**
- Date: **not filled**
- Decision: **implicitly ACCEPTED** via PR #359 merge (operator authorized `PR359-MERGE-AND-R5-AUTHORIZED`), but the report file's literal §9 block remains as placeholder

**Operator decision recommended**:
- (a) Fill in the §9 block retroactively (requires editing T3-A report file; this would mean T3-A evidence on main is now historical and operator must decide whether to amend)
- (b) Leave §9 as-is (placeholder is part of the template per plan §12); future reports should fill it before merge

**Note**: This is a **documentation hygiene** item, not a substance gap. T3-A evidence (`PR #359` merged) is the substantive outcome.

---

## 6. Round 2 Prerequisites (5 Items)

Per `THIRD_GRAY_ROUND2_MULTI_NODE_COLLAB_PLAN.md` §5, Round 2 requires 12 pre-conditions. The 5 that are **planning prerequisites** (not runtime checks) are:

| # | Prerequisite | Status |
|---|---|---|
| R2-PR-1 | Round 2 plan drafted (`THIRD_GRAY_ROUND2_MULTI_NODE_COLLAB_PLAN.md`) | ✅ this PR |
| R2-PR-2 | Round 2 I21 risk acknowledgment ready | Plan §3 + this catalog §2 |
| R2-PR-3 | T3-A single-node smoke concluded | ✅ PR #359 merged |
| R2-PR-4 | operator_approved set verified (= 6, deepseek-v4-pro ×3 + mimo-v2-5 ×3) | ✅ receipt on main |
| R2-PR-5 | qwen3-7-plus exclusion verified | ✅ receipt `non_scope_check.all_unknown=true` |

---

## 7. Operator Decision Points (Deferred, 3 Items)

| # | Decision | Default Behavior | Action Needed |
|---|---|---|---|
| OD-1 | Continue with Round 2 launch | **pending** | Operator reply `T2_TASK=<id>` + `EXECUTE` after `ACKNOWLEDGE_ROUND2_I21_RISKS` |
| OD-2 | Address I21 issues (I22/I23) before Round 2 | **pending** | Operator reply `DEFER_ROUND2` + `I22_TASK=<id>` if operator wants to fix issues first |
| OD-3 | Declare third gray acceptance "fully complete" without Round 2 | **pending** | Operator reply `DECLARE_THIRD_GRAY_COMPLETE` if operator decides Round 1 was sufficient |

---

## 8. Gap Closure Strategy (Operator Decision Tree)

```
After T3-A evidence merge (DONE @ 0ddfe6b)
    │
    ├── Operator: continue with Round 2?
    │       │
    │       ├── YES → Read THIRD_GRAY_ROUND2_MULTI_NODE_COLLAB_PLAN.md
    │       │           │
    │       │           ├── Operator acknowledges Round 2 plan (R2-AUTH-1)
    │       │           ├── Operator acknowledges I21 risks (R2-AUTH-2)
    │       │           ├── Operator picks task (R2-AUTH-3)
    │       │           └── ... (per Round 2 plan §6)
    │       │
    │       └── NO → Operator declares third gray complete
    │                   │
    │                   └── Optional: close T3-A caveats (C-1, C-2)
    │
    └── Operator: address I21 issues first?
            │
            ├── YES → Operator picks I22 work (separate plan, separate AUTH)
            │
            └── NO → Stay in "third gray acceptance in progress" state
```

---

## 9. Single-Source-of-Truth Files

| Concern | File |
|---|---|
| Third gray overall plan | `docs/baseline02/gray/THIRD_GRAY_ACCEPTANCE_PLAN.md` |
| Round 2 (multi-node) plan | `docs/baseline02/gray/THIRD_GRAY_ROUND2_MULTI_NODE_COLLAB_PLAN.md` |
| Round 1 (T3-A) report | `docs/baseline02/gray/THIRD_GRAY_REPORT-20260705.md` |
| T3-A task output | `docs/baseline02/gray/third-gray-task-output-T3-A-20260705-165222.md` |
| **Remaining gaps (this file)** | `docs/baseline02/gray/THIRD_GRAY_REMAINING_GAPS.md` |
| T3-A single-node smoke qualification | `docs/baseline02/gray/THIRD_GRAY_T3A_SMOKE_QUALIFICATION.md` |
| I21 issue catalog | `docs/reports/I21_GRAY_USAGE_BACKLOG.md` |
| Readiness receipt | `docs/baseline02/readiness/receipts/readiness-receipt-20260705-150000.yaml` |

---

## 10. Change Log

| Date | Change | Author |
|---|---|---|
| 2026-07-05 | Initial catalog (this document) | VibeDev Orchestrator under operator authorization |