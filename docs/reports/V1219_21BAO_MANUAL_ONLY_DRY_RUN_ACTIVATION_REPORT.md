# V1.20.19 21bao Manual-Only Activation State Report

**Version:** 1.20.19
**Date:** 2026-06-20
**Status:** 21bao activated as enabled=True, manual_only=True
**Main baseline:** a50b1bbd10dcabeb11723e5635ca4c1edadf9d9c

---

## Safety Declarations

- **21bao is NOT auto-scheduled** (manual_only=True excludes from scheduler)
- **No real coding job executed**
- **No live model calls**
- **No OpenCode invocation**
- **No secret/env/credential mutation**
- **No runtime mutation**
- **Rollback: set 21bao.enabled=False (does not affect 5bao/9bao)**

---

## 1. Activation Summary

### Before

| Parameter | Value |
|---|---|
| 21bao enabled | False |
| 21bao manual_only | True |
| auto candidates | excludes 21bao |
| active capacity | 2 (5bao+9bao) |

### After

| Parameter | Value |
|---|---|
| 21bao enabled | **True** |
| 21bao manual_only | **True** (unchanged) |
| auto candidates | **still excludes 21bao** |
| active capacity | **2** (5bao+9bao, unchanged) |

### What Changed

**Single semantic change:** `21bao.enabled = False` → `True`

All other parameters unchanged. 21bao remains manual-only, not auto-scheduled.

---

## 2. Changed Files

| File | Change |
|---|---|
| `scripts/vibe_worker_registry.py` | 21bao `enabled=True`; self-check 13 temporarily disables 21bao for disabled-worker test |
| `scripts/cluster_component_manifest.py` | 21bao entries `enabled=True`; self-check updated |
| `scripts/cluster_upgrade_simulate.py` | Self-check updated for enabled=True |
| `tests/test_worker_transport_routing.py` | 4 assertions updated for enabled=True |
| `tests/test_cluster_upgrade_resilience.py` | 2 assertions updated for enabled=True |
| `docs/reports/V1219_...PLAN.md` | Activation plan document (new) |

---

## 3. Scheduler Exclusion Proof

| Condition | Result |
|---|---|
| `schedule()` default | 21bao never selected |
| `get_eligible_candidates()` default | 21bao not in list |
| `available_workers()` default | 21bao filtered out (manual_only=True) |
| `available_workers(include_manual_only=True)` | 21bao visible |
| Active capacity | 2 (5bao+9bao) |

---

## 4. Dry-Run Validation Results

| Test | Result |
|---|---|
| no_op fixture | status="no_op", exit_code=0 |
| dry_run path validation | status="dry_run", exit_code=0 |
| dry_run wrapper check | wrapper path in stdout |
| dry_run evidence/log | evidence+log in stdout |
| Controller repo path | BLOCKED |
| Outside D/E allowlist | BLOCKED |
| Null byte path | BLOCKED |

---

## 5. Regression Tests

| Check | Result |
|---|---|
| py_compile (4 files) | ALL OK |
| runner self-check | 19/19 PASS |
| registry self-check | 15/15 PASS |
| scheduler self-check | 10/10 PASS |
| manifest self-check | 8/8 PASS |
| pytest (3 files) | 120/120 PASS |
| **Total** | **172/172** |

---

## 6. Rollback

**Trigger:** Any safety invariant fails, or Operator decides to revert.

**Steps:**
1. Set `registry.workers["21bao"].enabled = False`
2. Revert manifest entries to `enabled=False`
3. Update self-checks and tests accordingly
4. Verify 21bao excluded from auto candidates
5. Verify active capacity = 2

**Rollback does NOT affect 5bao/9bao.**

---

## 7. Safety Scan

| Field | Value |
|---|---|
| 21bao enabled | True |
| 21bao manual_only | True |
| 21bao auto-scheduled | NO |
| 5bao | unchanged |
| 9bao | unchanged |
| active capacity | 2 |
| no real job | true |
| model_calls | 0 |
| opencode_called | false |
| secret_exposed | false |
| credential_modified | false |
| runtime_code_changed | false |
| workflow_code_changed | true |
