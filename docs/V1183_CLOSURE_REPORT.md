# V1.18.3 Evidence-Complete Linearizability + Repair Transaction Closure

**Date:** 2026-06-18
**code_head:** 905917d9343ea9f9f015bdacb2c7b4a5b59c980b (PR #163 merged)
**attestation_head:** 905917d9343ea9f9f015bdacb2c7b4a5b59c980b (same — report in next commit)

## HEAD Verification

| Node | SHA | Branch |
|------|-----|--------|
| Windows | 905917d9343ea9f9 | main |
| 5bao | 905917d9343ea9f9 | main (bare repo) |
| 9bao | 905917d9343ea9f9 | main (bare repo) |
| Public main | 905917d9343ea9f9 | main |

**3-way consistency:** ✓ PASS

## Changes (PR #163)

### 1. Cancel State Machine Closure
- CANCEL_REQUESTED can ONLY transition to CANCELLED (removed FAILED, SUCCEEDED)
- All state transitions use `_transition_state()` with CAS — zero direct `manifest.state =` assignments in production paths
- FAILED/CANCELLED → QUEUED resume transitions via VALID_TRANSITIONS table
- Stale writers cannot overwrite newer revision (CAS)

### 2. Credential Resolver Strict Enforcement
- Registry is the ONLY source — removed explicit path fallback (`_CONTROLLER_SSH_KEY_PATHS` no longer used as fallback)
- target_worker MANDATORY at all call sites
- All registry entries validated: platform, controller identity, approved root, fingerprint, allowed_workers

### 3. ClaimStore Repair — Journal-Based Recoverable Transaction
- `repair_plan_digest` is MANDATORY and strictly matched against receipt
- Persistent journal written BEFORE any mutations (tx_id, receipt, nonce, candidate, old/new SHA, node, operator)
- Nonce consume failure aborts repair with RuntimeError (no silent warning)
- fsync on tmp files (Linux) + parent directory fsync (Linux)
- On crash: journal allows safe completion or rollback — no manual state manipulation

### 4. Test Updates
- V1.18.2 test_v1182_linearizable.py updated for new state machine semantics
- test_v1173.py, test_v1174.py, test_v1177_runtime_closure.py: version assertions updated
- test_v1177_runtime_closure.py: repair_plan_digest added to repair calls

## Test Results

| Test Suite | Result |
|-----------|--------|
| Self-check (Windows) | 30/30 PASS |
| Self-check (5bao) | 30/30 PASS |
| Self-check (9bao) | 30/30 PASS |
| pytest (167 tests) | 167 PASS, 2 deselected (pre-existing Windows multiprocessing) |
| test_v1182_linearizable.py | 8/8 PASS |
| Cancel race (real job) | CANCELLED, executor observed ✓ |
| Active-active jobs | SUCCEEDED ✓ |
| ripgrep→9bao routing | SUCCEEDED ✓ |

## Real System Evidence

| Test | Job ID | Worker | State | Notes |
|------|--------|--------|-------|-------|
| Cancel race | job-d60254f50421 | 9bao | CANCELLED | cancel_job CONFIRMED_EXIT, executor EXECUTOR_OBSERVED_CANCEL |
| Active-active | job-10e0281fe8c0 | 9bao | SUCCEEDED | exit=0 |
| Active-active | job-c03760dbffc1 | 9bao | SUCCEEDED | exit=0 |
| ripgrep→9bao | job-0736332b898f | 9bao | SUCCEEDED | rg --version, exit=0 |

## Verification

| Role | Model | Result |
|------|-------|--------|
| Reviewer | mimo-v2.5-pro | APPROVE |
| Verifier | MiniMax-M3 (pytest) | 167/167 PASS |
| Verifier | MiniMax-M3 (self-check) | 30/30 PASS |

## Frozen Baselines

| Item | Status |
|------|--------|
| V1.17.7 FREEZE_MANIFEST | 3699732c... UNCHANGED ✓ |
| OpenCode 5bao | 1.17.4 |
| OpenCode 9bao | 1.17.4 |
| approved runtime baseline | 13c70424bc7af317... UNCHANGED |

## Evidence SHA256

(to be computed after report commit)

---

```
V1.18.3_LINEARIZABLE_TRANSACTION_CLOSURE_PASS
V1.17.7_FREEZE_UNCHANGED
CREDENTIAL_REMEDIATION_PENDING_OPERATOR_APPROVAL
```
