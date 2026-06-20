# V1.20.19 21bao Manual-Only Dry-Run Activation Plan

**Version:** 1.20.19
**Date:** 2026-06-20
**Status:** PLAN ONLY -- NOT enabling 21bao, NOT executing any job, NOT calling any model
**Main baseline:** a50b1bbd10dcabeb11723e5635ca4c1edadf9d9c

---

## Safety Declarations

- **This plan does NOT enable 21bao auto-scheduling**
- **This plan does NOT execute any dry-run/no-op/real job**
- **This plan does NOT call OpenCode or any model**
- **This plan does NOT modify any secret/env/credential**
- **This plan does NOT merge to main**
- **This plan describes the activation procedure for future Operator approval**

---

## 1. ACTIVATION_TARGET

### 1.1 Current State (Before)

| Parameter | Value |
|---|---|
| 21bao enabled | **False** |
| 21bao manual_only | **True** |
| 21bao transport | local-exec |
| scheduler auto candidates | **excludes 21bao** |
| available_workers default | **excludes 21bao** |
| 5bao | enabled=True, manual_only=False, ssh |
| 9bao | enabled=True, manual_only=False, ssh |
| active-active capacity | **2** (5bao + 9bao) |

### 1.2 Target State (After)

| Parameter | Value |
|---|---|
| 21bao enabled | **True** |
| 21bao manual_only | **True** (unchanged) |
| 21bao transport | local-exec (unchanged) |
| scheduler auto candidates | **still excludes 21bao** (manual_only=True) |
| available_workers default | **still excludes 21bao** (manual_only=True) |
| 5bao | enabled=True, manual_only=False (unchanged) |
| 9bao | enabled=True, manual_only=False (unchanged) |
| active-active capacity | **2** (5bao + 9bao, unchanged) |

### 1.3 What Changes

**Single change:** `registry.workers["21bao"].enabled = True`

**What does NOT change:**
- `manual_only` remains True
- Scheduler auto-candidates still exclude 21bao
- 5bao/9bao unchanged
- No transport change
- No capability change
- No secret/env/credential change

### 1.4 Why This Is Safe

When `manual_only=True`:
1. `available_workers()` with default `include_manual_only=False` excludes 21bao
2. `get_eligible_candidates()` calls `available_workers()` without `include_manual_only=True`, so 21bao never appears in auto-scheduling
3. `schedule()` never routes to 21bao automatically
4. Only explicit `available_workers(include_manual_only=True)` can see 21bao
5. The runner's `run_job()` still validates all paths against allowlist/blocklist

---

## 2. MANUAL_ONLY_GUARD_MODEL

### 2.1 Dispatch Requirements (All Must Be True)

For any job to execute on 21bao, ALL of the following must be satisfied:

| # | Condition | Enforcer | Fail-Closed Behavior |
|---|---|---|---|
| 1 | `node=21bao` explicitly specified | Caller/dispatcher | Reject if not specified |
| 2 | `manual=true` explicitly specified | Caller/dispatcher | Reject if not specified |
| 3 | `dry_run=true` OR `no_op=true` | Runner `JobSpec` | Reject if neither set |
| 4 | `enabled=True` in registry | `available_workers(include_manual_only=True)` | Worker not found |
| 5 | `manual_only=True` in registry | Scheduler excludes from auto | Never auto-routed |
| 6 | Path passes `validate_path()` | Runner | `status=failed` |
| 7 | Transport is `local-exec` | Registry | Unknown transport fail-closed |

### 2.2 Guard Chain

```
Caller
  │
  ├─ Must specify: node=21bao, manual=true, dry_run=true|no_op=true
  │  └─ Missing any → REJECT (fail-closed)
  │
  ▼
available_workers(include_manual_only=True)
  │
  ├─ 21bao.enabled must be True
  ├─ 21bao.manual_only must be True
  ├─ 21bao.health_status must be ONLINE
  ├─ 21bao.maintenance_status must not be "maintenance"
  └─ Any check fails → Worker not available
  │
  ▼
run_job(spec)
  │
  ├─ spec.no_op=True → return mock result immediately (no filesystem)
  ├─ spec.dry_run=True → validate paths, return mock result (no execution)
  ├─ Neither set → BLOCK (21bao manual-only requires dry_run or no_op)
  │
  ▼
validate_path(worktree), validate_path(evidence_dir), validate_path(log_dir)
  │
  ├─ _canonicalize() succeeds → check allowlist (D:\, E:\) + blocklist
  ├─ _canonicalize() fails → fail-closed (BLOCK)
  ├─ Path not in allowlist → BLOCK
  ├─ Path in blocklist → BLOCK
  └─ All pass → proceed (dry_run/no_op returns mock)
```

### 2.3 Fail-Closed Points

| Failure Mode | Behavior |
|---|---|
| Missing node=21bao | REJECT |
| Missing manual=true | REJECT |
| Missing dry_run/no_op | REJECT |
| 21bao not enabled | Worker unavailable |
| Canonicalization failure | Path BLOCKED |
| Path not in D/E allowlist | Path BLOCKED |
| Path in controller blocklist | Path BLOCKED |
| Null byte in path | Path BLOCKED |
| Unknown transport | Fail-closed, excluded |

---

## 3. ALLOWED_DRY_RUN_MATRIX

### 3.1 Job Classes

| # | Job Class | Description | dry_run | no_op | Real Execution | Model Call |
|---|---|---|---|---|---|---|
| A1 | no_op_fixture | Return mock success, no filesystem | — | **yes** | No | No |
| A2 | dry_run_path_validation | Validate paths, return would_execute | **yes** | — | No | No |
| A3 | dry_run_wrapper_check | Validate wrapper path exists | **yes** | — | No | No |
| A4 | dry_run_evidence_dir | Validate evidence/log dirs | **yes** | — | No | No |

### 3.2 Example JobSpecs

**A1: no_op fixture**
```python
JobSpec(job_id="21bao-noop-001", branch="feat/test", task="implementer", no_op=True)
# Expected: status="no_op", exit_code=0
```

**A2: dry_run path validation**
```python
JobSpec(job_id="21bao-dryrun-001", branch="feat/test", task="implementer", dry_run=True)
# Expected: status="dry_run", exit_code=0, stdout contains worktree/evidence/log paths
```

**A3: dry_run wrapper check**
```python
JobSpec(job_id="21bao-dryrun-002", branch="feat/test", task="implementer", dry_run=True)
# Expected: status="dry_run", stdout includes wrapper path
```

**A4: dry_run evidence dir**
```python
JobSpec(job_id="21bao-dryrun-003", branch="feat/test", task="implementer", dry_run=True)
# Expected: status="dry_run", stdout includes evidence/log dirs
```

---

## 4. FORBIDDEN_JOB_MATRIX

| # | Job Class | Why Forbidden | Enforcement |
|---|---|---|---|
| F1 | Real coding job | 21bao manual-only, not approved for real work | dry_run/no_op required |
| F2 | Reviewer job | Not in allowed scope | manual_only guard |
| F3 | Merge job | Not in allowed scope | manual_only guard |
| F4 | Live model call | No OpenCode invocation | dry_run/no_op returns mock |
| F5 | Provider call | No API calls | dry_run/no_op returns mock |
| F6 | OpenCode mutation | No config changes | dry_run/no_op returns mock |
| F7 | Auto-scheduled job | manual_only excludes from auto | scheduler filter |
| F8 | Underspecified job | Missing node/manual/dry_run | fail-closed REJECT |

---

## 5. SCHEDULER_EXCLUSION_PROOF

### 5.1 Code Path Analysis

**Path 1: `schedule()` → `available_workers()`**
```python
# vibe_scheduler_policy.py line 176
available = self.registry.available_workers(task_type)
# default: include_manual_only=False
# → 21bao (manual_only=True) excluded
```

**Path 2: `get_eligible_candidates()` → `available_workers()`**
```python
# vibe_scheduler_policy.py line 176
available = self.registry.available_workers(task_type, ...)
# default: include_manual_only=False
# → 21bao (manual_only=True) excluded
```

**Path 3: `available_workers()` filter**
```python
# vibe_worker_registry.py line 206-207
if not include_manual_only:
    candidates = [w for w in candidates if not w.manual_only]
# → 21bao filtered out
```

### 5.2 Self-Check Coverage

| Check | Script | Verifies |
|---|---|---|
| `21bao_not_auto_scheduled` | scheduler | 21bao not in auto candidates |
| `manual_only_filtering` | registry | manual_only excludes 21bao by default |
| `manual_only_included_when_flag` | registry | include_manual_only=True includes 21bao |

### 5.3 Proof Summary

| Condition | Result |
|---|---|
| `schedule()` called without explicit 21bao | **21bao never selected** |
| `get_eligible_candidates()` default | **21bao not in list** |
| `available_workers()` default | **21bao filtered out** |
| Only `available_workers(include_manual_only=True)` | **21bao visible** |

---

## 6. SAFETY_AND_ROLLBACK_PLAN

### 6.1 Safety Invariants (Must Hold After Activation)

| # | Invariant | Verification |
|---|---|---|
| S1 | 5bao enabled=True | registry check |
| S2 | 9bao enabled=True | registry check |
| S3 | 21bao manual_only=True | registry check |
| S4 | auto candidates exclude 21bao | scheduler check |
| S5 | active capacity = 2 (5bao+9bao) | registry check |
| S6 | controller repo path blocked | runner self-check |
| S7 | D/E allowlist enforced | runner self-check |
| S8 | unknown transport fail-closed | scheduler self-check |

### 6.2 Rollback Procedure

**Trigger:** Any safety invariant fails, or Operator decides to revert.

**Steps:**
1. Set `registry.workers["21bao"].enabled = False`
2. Verify `21bao.enabled=False, manual_only=True`
3. Verify `auto candidates` still exclude 21bao
4. Verify `active capacity = 2` (5bao+9bao)
5. No restart required (in-memory state change)
6. No effect on 5bao/9bao

**Rollback is idempotent:** Setting enabled=False when already False is safe.

### 6.3 Rollback Does NOT Affect

| Component | Impact |
|---|---|
| 5bao | None |
| 9bao | None |
| Active capacity | Remains 2 |
| Scheduler policy | Unchanged |
| Runner code | Unchanged |
| Secrets/env | Unchanged |

---

## 7. TEST_PLAN

### 7.1 Pre-Activation Tests (Must All PASS)

| # | Test | Script | Expected |
|---|---|---|---|
| T1 | py_compile all modified files | python -m py_compile | OK |
| T2 | runner self-check (19 checks) | runner --self-check | 19/19 PASS |
| T3 | registry self-check (15 checks) | registry --self-check | 15/15 PASS |
| T4 | scheduler self-check (10 checks) | scheduler --self-check | 10/10 PASS |
| T5 | pytest runner tests (37) | pytest test_windows_local_runner | 37/37 PASS |
| T6 | pytest transport routing (25) | pytest test_worker_transport_routing | 25/25 PASS |
| T7 | pytest upgrade resilience (58) | pytest test_cluster_upgrade_resilience | 58/58 PASS |

### 7.2 Activation Tests (After `enabled=True`)

| # | Test | Method | Expected |
|---|---|---|---|
| T8 | 21bao.enabled == True | registry.get_worker("21bao") | True |
| T9 | 21bao.manual_only == True | registry.get_worker("21bao") | True |
| T10 | auto candidates exclude 21bao | scheduler.get_eligible_candidates() | 21bao not in list |
| T11 | available_workers default excludes 21bao | registry.available_workers() | 21bao not in list |
| T12 | available_workers(manual) includes 21bao | registry.available_workers(include_manual_only=True) | 21bao in list |
| T13 | active capacity = 2 | count enabled non-manual workers | 2 |
| T14 | 5bao unchanged | registry.get_worker("5bao") | enabled=True |
| T15 | 9bao unchanged | registry.get_worker("9bao") | enabled=True |

### 7.3 Dry-Run Execution Tests

| # | Test | JobSpec | Expected |
|---|---|---|---|
| T16 | no_op fixture | no_op=True | status="no_op", exit_code=0 |
| T17 | dry_run path validation | dry_run=True | status="dry_run", exit_code=0 |
| T18 | dry_run wrapper check | dry_run=True | stdout includes wrapper path |
| T19 | dry_run evidence dir | dry_run=True | stdout includes evidence/log dirs |

### 7.4 Fail-Closed Tests

| # | Test | Condition | Expected |
|---|---|---|---|
| T20 | No node specified | Missing node=21bao | REJECT |
| T21 | No manual flag | Missing manual=true | REJECT |
| T22 | No dry_run/no_op | Neither set | REJECT |
| T23 | Controller repo path | Path in blocklist | BLOCKED |
| T24 | Outside D/E | Path not in allowlist | BLOCKED |
| T25 | Null byte path | Path with \x00 | BLOCKED |

### 7.5 Post-Activation Full Regression

| # | Test | Expected |
|---|---|---|
| T26 | runner self-check | 19/19 PASS |
| T27 | registry self-check | 15/15 PASS |
| T28 | scheduler self-check | 10/10 PASS |
| T29 | pytest (all 3 files) | 120/120 PASS |

---

## 8. RISK_AND_STOPLINE_MATRIX

### 8.1 Risk Assessment

| # | Risk | Likelihood | Impact | Mitigation | Stopline |
|---|---|---|---|---|---|
| R1 | 21bao auto-scheduled | Very Low | High | manual_only=True enforced at registry + scheduler level | If auto candidates include 21bao → STOP |
| R2 | Real job executes on 21bao | Very Low | High | dry_run/no_op required, fail-closed guard | If job status not dry_run/no_op → STOP |
| R3 | Controller repo written | Very Low | Critical | blocklist + allowlist + canonicalization | If path not BLOCKED → STOP |
| R4 | Secret/env leaked | Very Low | Critical | no env access in dry_run/no_op | If secret in output → STOP |
| R5 | 5bao/9bao affected | Very Low | Medium | activation only changes 21bao.enabled | If 5bao/9bao state changes → STOP |
| R6 | OpenCode called | Very Low | Medium | dry_run/no_op returns mock, no OpenCode invocation | If opencode_called=true → STOP |
| R7 | Rollback fails | Very Low | Medium | enabled=False is idempotent | If rollback verification fails → STOP |

### 8.2 Stolines (Hard Stop Conditions)

| # | Stoline | Condition | Action |
|---|---|---|---|
| ST1 | 21bao auto-scheduled | 21bao in auto candidates | IMMEDIATE STOP, rollback |
| ST2 | Real job on 21bao | job.status not in (dry_run, no_op) | IMMEDIATE STOP, rollback |
| ST3 | Controller repo write | path validation bypassed | IMMEDIATE STOP, rollback |
| ST4 | Secret exposure | secret/token in output | IMMEDIATE STOP, rollback |
| ST5 | 5bao/9bao state change | enabled or manual_only changed | IMMEDIATE STOP, rollback |
| ST6 | Model call | opencode_called or provider_called | IMMEDIATE STOP, rollback |
| ST7 | Capacity change | active capacity != 2 | IMMEDIATE STOP, rollback |

### 8.3 Monitoring

| Metric | Expected | Alert Threshold |
|---|---|---|
| 21bao.enabled | True | Any unexpected change |
| 21bao.manual_only | True | Any change to False |
| auto candidates | excludes 21bao | 21bao appears |
| active capacity | 2 | != 2 |
| jobs on 21bao | dry_run/no_op only | real job detected |
| model calls | 0 | > 0 |

---

## 9. FOLLOWUP_IMPLEMENTATION_PLAN

### 9.1 Phase 1: Activation (Requires Operator Approval)

**Scope:** Set `21bao.enabled = True` in registry, keep `manual_only = True`.

**Implementation:**
```python
# In vibe_worker_registry.py, change line ~150:
WorkerNode(
    worker_id="21bao",
    ...
    enabled=True,   # was False
    manual_only=True,  # unchanged
    ...
)
```

**Verification:**
1. py_compile
2. All self-checks (runner 19/19, registry 15/15, scheduler 10/10)
3. All pytest (120/120)
4. Manual verification: 21bao.enabled=True, manual_only=True
5. Auto candidates still exclude 21bao

**PR:** New PR on branch `feat/v1219-21bao-enable-manual-only`

### 9.2 Phase 2: Dry-Run Validation (Requires Operator Approval)

**Scope:** Execute dry-run/no-op jobs on 21bao.

**Jobs:**
1. `no_op_fixture` — verify mock result
2. `dry_run_path_validation` — verify path validation
3. `dry_run_wrapper_check` — verify wrapper path
4. `dry_run_evidence_dir` — verify evidence/log dirs

**Verification:**
- All 4 jobs return expected status
- No real filesystem changes
- No model calls
- No secret exposure

### 9.3 Phase 3: Manual-Only=False (Requires Operator Approval)

**Scope:** Set `manual_only = False` on 21bao, allowing auto-scheduling.

**NOT in current plan scope.** Requires separate Operator approval after Phase 2 passes.

### 9.4 Phase 4: Real Job (Requires Operator Approval)

**Scope:** Execute real coding jobs on 21bao.

**NOT in current plan scope.** Requires separate Operator approval after Phase 3 passes.

### 9.5 Decision Gate

| Phase | Gate | Approval Required |
|---|---|---|
| Phase 1 | Enable 21bao (manual-only) | Operator |
| Phase 2 | Execute dry-run jobs | Operator |
| Phase 3 | Set manual_only=False | Operator (separate) |
| Phase 4 | Real jobs | Operator (separate) |

Each phase requires:
1. All tests from previous phase PASS
2. All safety invariants verified
3. Operator explicit approval
4. No stopline violations

---

## Appendix A: Code References

| File | Relevant Lines | Purpose |
|---|---|---|
| `scripts/vibe_worker_registry.py` | 150-165 | 21bao WorkerNode definition |
| `scripts/vibe_worker_registry.py` | 189-207 | available_workers() with manual_only filter |
| `scripts/vibe_scheduler_policy.py` | 127-195 | get_eligible_candidates() |
| `scripts/vibe_scheduler_policy.py` | 176 | manual_only excluded from auto |
| `scripts/vibe_windows_local_runner.py` | 60-70 | JobSpec with dry_run/no_op |
| `scripts/vibe_windows_local_runner.py` | 243-280 | run_job() dry_run/no_op handling |
| `scripts/vibe_windows_local_runner.py` | 121-185 | validate_path/is_path_blocked/is_path_allowed |

---

## Appendix B: Self-Check Coverage

| Self-Check | Count | Covers |
|---|---|---|
| runner | 19 | path validation, blocklist, allowlist, dry_run, no_op, fail-closed, canonicalization |
| registry | 15 | worker definitions, transport, manual_only filtering, capacity |
| scheduler | 10 | auto-scheduling exclusion, transport routing, lifecycle gate |
| **Total** | **44** | |
