# Toolchain Freeze Document

**Freeze Date**: 2026-06-15
**Freeze Baseline**: `origin/main = 40704fcbdae231f7b6ea14c43a292afb2cb23e8d`
**Total PRs Merged**: 30

---

## Stable Commands (Verified)

| Command | Script | Description | Status |
|---------|--------|-------------|--------|
| `snapshot` | `vibe_operator_snapshot.py` | Unified status snapshot | ✅ STABLE |
| `advisor` | `vibe_queue_advisor.py` | Lifecycle analysis & action items | ✅ STABLE |
| `dispatch` | `vibe_dispatch_planner.py` | Next Work Order suggestions | ✅ STABLE |
| `batch-plan` | `vibe_batch_plan.py` | Batch execution plan | ✅ STABLE |
| `health` | `vibe_health_check.py` | Toolchain verification | ✅ STABLE |
| `smoke` | `test_toolchain_smoke.py` | Full smoke suite (11 tests) | ✅ STABLE |
| `router` | `vibe_command_router.py` | Unified CLI entry point | ✅ STABLE |
| `merge` | `vibe_autonomous_merge.py` | Controlled merge wrapper | ✅ STABLE |

### Short Aliases

| Alias | Command |
|-------|---------|
| `s` | snapshot |
| `a` | advisor |
| `d` | dispatch |
| `b` | batch-plan |
| `h` | health |
| `sm` | smoke |
| `?` | help |
| `v` | version |

---

## Script Inventory

| Script | Lines | Purpose | Import Safe |
|--------|-------|---------|-------------|
| `vibe_repo_status.py` | ~400 | Job registry & repo status | ✅ |
| `vibe_queue_advisor.py` | ~500 | Lifecycle classification | ✅ |
| `vibe_operator_snapshot.py` | ~250 | Unified snapshot | ✅ |
| `vibe_dispatch_planner.py` | ~200 | Dispatch suggestions | ✅ |
| `vibe_batch_plan.py` | ~230 | Batch execution plan | ✅ |
| `vibe_command_router.py` | ~180 | CLI entry point | ✅ |
| `vibe_health_check.py` | ~200 | Toolchain health | ✅ |
| `vibe_autonomous_merge.py` | ~250 | Merge wrapper | ✅ |
| `test_toolchain_smoke.py` | ~280 | Smoke test suite | ✅ |

**Total**: 9 scripts, all standard library, no new dependencies.

---

## CLI Flags

### Global Flags (via command router)
- `--json` — JSON output
- `--compact` — Compact text output
- `--jobs-dir <dir>` — Custom jobs directory

### Per-Command Flags
- **snapshot**: `--include-merged`, `--include-tainted`
- **advisor**: `--include-tainted`, `--include-merged`
- **dispatch**: `--compact`
- **batch-plan**: `--limit N`
- **health**: `--json`
- **smoke**: `--json`
- **merge**: `--repo`, `--pr`, `--expected-base-sha`, `--expected-head-sha`, `--allowed-path`, `--dry-run`

---

## Recommendation Consistency Rules

All recommendation tools produce consistent top-level guidance:

| Scenario | Snapshot | Dispatch | Batch Plan |
|----------|----------|----------|------------|
| Queue clean | queue_clean | queue_clean | tasks=0, risk=low |
| Tainted lock | resolve_blocked | hold_due_to_blocker | risk=critical |
| Failed jobs | investigate_failures | investigate_failures | risk=high |
| Ready for merge | process_merge_queue | process_merge_queue | risk=low |
| Superseded only | queue_clean | queue_clean + info | tasks=0 |

**Key invariant**: Superseded jobs are informational (already resolved by later success). They must NOT cause Dispatch Planner to recommend `resolve_superseded` when the queue is otherwise clean.

---

## Batch Queue Execution Method

1. **Plan**: `vibe_command_router batch-plan --json` to get execution plan
2. **Execute**: For each task in `task_order`:
   - Create worktree from `base_sha`
   - Implement changes within `allowed_paths`
   - Run smoke test: `vibe_command_router smoke`
   - Commit and push branch
   - Create PR
   - Run wrapper dry-run: `vibe_autonomous_merge.py ... --dry-run`
   - Run wrapper merge: `vibe_autonomous_merge.py ...`
   - Post-merge freeze: fetch + verify main
3. **Report**: Per-task report with all required fields

---

## Human Stop Conditions

The following conditions require human intervention:

1. **audit_tainted lock** — `wo-code-repo-status-001` is permanently locked
2. **origin/main mismatch** — base_sha differs from expected
3. **Gate blockers** — wrapper returns `allow_merge=false`
4. **Scope violation** — changed paths exceed declared scope
5. **High risk** — batch plan risk_level=high or critical
6. **CI failure** — GitHub checks fail (when enabled)
7. **Secret/Provider/CI change** — any attempt triggers immediate stop

---

## Known Reserved Items

### wo-code-repo-status-001 (Permanent Lock)
- **Status**: `audit_status=audit_tainted`, `push_allowed=false`
- **Reason**: `work_order_nonce_mismatch_and_acceptance_attempt_not_append_only`
- **Action**: None — this lock is permanent and must never be removed
- **Visibility**: Appears in operator snapshot as `Blocked: 1 (1 hidden)`

### Why Hidden?
The tainted lock is hidden by default in operator snapshot to avoid noise. Use `--include-tainted` to see it. The smoke test verifies the lock is visible via `audit_tainted_lock` check.

---

## Toolchain Health Check Results

```
Overall: PASS (7 checks)
  ✓ py_compile: PASS - 9 scripts compiled
  ✓ import: PASS - 9 scripts importable
  ✓ operator_snapshot: PASS - total=26
  ✓ queue_advisor: PASS - total=26
  ✓ dispatch_planner: PASS - recommended=queue_clean
  ✓ batch_plan: PASS - tasks=0
  ✓ audit_tainted_lock: PASS - 1 tainted lock(s) visible
```

---

## Smoke Suite Results

```
Overall: PASS (11 tests)
  ✓ command_router_help: PASS
  ✓ command_router_snapshot: PASS
  ✓ command_router_advisor: PASS - total=26
  ✓ command_router_dispatch: PASS - recommended=queue_clean
  ✓ command_router_batch_plan: PASS - tasks=0
  ✓ health_check: PASS - overall=PASS
  ✓ operator_snapshot: PASS - total=26
  ✓ queue_advisor: PASS - total=26
  ✓ dispatch_planner: PASS - recommended=queue_clean
  ✓ batch_plan: PASS - tasks=0
  ✓ recommendation_consistency: PASS - all report queue_clean/0-tasks
```

---

## Merge Policy

- **Method**: Merge commit only (no squash, no rebase)
- **Wrapper**: All merges via `vibe_autonomous_merge.py`
- **Forbidden**: Bare `gh pr merge` without wrapper
- **Gate checks**: PR mergeable, changed paths in scope, base SHA matches
- **Dry-run**: Always run `--dry-run` first

---

## Scope Boundaries

### Always Allowed (Read-Only)
- `scripts/vibe_*.py` — all orchestrator scripts
- `scripts/test_*.py` — all test scripts
- `docs/*.md` — all documentation

### Never Allowed
- `.github/` — CI/workflow configuration
- `secrets/` or `*secret*` — credentials
- `*token*` or `*pat*` — authentication
- Provider configuration
- SSH keys
- Production deployment configs

### Conditional (Requires Explicit Approval)
- New scripts (must be standard library, import-safe)
- Changes to merge wrapper logic
- Changes to gate check rules

---

*This document represents the frozen toolchain state as of the baseline SHA. Any changes to the toolchain require a new Work Order with explicit scope.*


## Operational Readiness

For the full Operational Readiness Report, see [OPERATIONAL_READINESS.md](OPERATIONAL_READINESS.md).

**Readiness Level**: 🟢 AUTONOMOUS (with guardrails)

Quick status:
- 9 scripts, 11 smoke tests, 7 health checks — all PASS
- Recommendation consistency verified
- 33 PRs merged, queue_clean
- audit_tainted lock preserved (wo-code-repo-status-001)
