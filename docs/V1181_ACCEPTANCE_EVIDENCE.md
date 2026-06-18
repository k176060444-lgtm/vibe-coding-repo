# V1.18.1 Acceptance Evidence — Final Report

**Date**: 2026-06-18
**HEAD**: `d4f1bd59bc831a73f2e912cb001b3fbf885fd6de`
**Frozen HEAD**: `60409e62558bddcdbcbc68b070fa125595ffeb9d`

## Status

```
V1.18.1_PRODUCTION_HARDENING_PASS
V1.17.7_FREEZE_UNCHANGED
CREDENTIAL_REMEDIATION_PENDING_OPERATOR_APPROVAL
```

## 5 Acceptance Items

### Item 1: Cancel 闭环

| Field | Value |
|-------|-------|
| Job ID | job-6b1b164ff242 |
| Worker | 5bao |
| Controller PID | 4728 |
| Remote PID | 727254 (from .job.pid) |
| Cancel result | `CONFIRMED_EXIT` |
| Remote process after cancel | DEAD (verified via ps) |
| Claim released | Yes (state=CANCELLED, not active) |
| Code fix | `_read_remote_pid_file_from_dir()` reads PID from remote .job.pid |
| Evidence | `controller_local` |

### Item 2: Heartbeat (280s fixture)

| Field | Value |
|-------|-------|
| Job ID | job-ceb1218ea158 |
| Worker | 5bao |
| Controller PID | 2484 |
| Remote PID | 728726 |
| Duration | 280 seconds |
| Heartbeat #1 | 2026-06-18T09:46:04.130986+00:00 |
| Heartbeat #2 | 2026-06-18T09:48:04.147486+00:00 |
| Heartbeat #3 | 2026-06-18T09:50:04.163383+00:00 |
| Heartbeat count | 3 (>2 required) |
| Final state | SUCCEEDED |
| Code fix | SSH launch `</dev/null >/dev/null 2>&1` prevents timeout |
| Evidence | `controller_local` |

### Item 3: Third Task Capacity BLOCK

| Job | Worker | State | PID | Remote PID |
|-----|--------|-------|-----|------------|
| job-64883721efbd | 5bao | SUCCEEDED | 1660 | 730880 |
| job-f2eda8cb1579 | 9bao | SUCCEEDED | 2992 | 2542584 |
| job-4a694cf4cd29 | (any) | **BLOCKED** | — | — |

Third job error: `claim_failed: capacity_full`
Evidence: `controller_local`

### Item 4: Repair Concurrency + Fault Injection

| Test | Result | Details |
|------|--------|---------|
| concurrent_repair | ✅ PASS | 2 processes, 1 success, 1 "Receipt already consumed" |
| empty_candidate | ✅ PASS | Empty/missing/in-place all rejected |
| duplicate_nonce | ✅ PASS | Consumed receipt rejected on second use |
| same_sha | ✅ PASS | Wrong old_sha in receipt rejected |

Test file: `scripts/test_repair_concurrency.py`
Evidence: `controller_local`

### Item 5: Independent Reviewer + Verifier

| Role | Model | Verdict |
|------|-------|---------|
| Reviewer | mimo-v2.5-pro | APPROVE |
| Verifier | mimo-v2.5-pro (different session) | APPROVE (5/5 checks PASS) |

Reviewer note: `_read_remote_pid_file_from_dir` should use `_shell_quote()` → **FIXED** in `d4f1bd5`

## Regression Suite

| Test | Windows | Result |
|------|---------|--------|
| Lifecycle self-check (20) | 20/20 | ✅ |
| Orchestrator self-check (30) | 30/30 | ✅ |
| pytest (29) | 29/29 | ✅ |
| Repair concurrency (4) | 4/4 | ✅ |
| Freeze manifest SHA | `3699732c...` | ✅ UNCHANGED |

## Code Changes (d4f1bd5)

| File | Change |
|------|--------|
| `scripts/vibe_job_orchestrator.py` | SSH launch redirect, cancel PID recovery, `_shell_quote` |
| `scripts/test_repair_concurrency.py` | 4 repair concurrency tests (NEW) |
| `docs/V1177_FINAL_FREEZE_MANIFEST.md` | Freeze manifest (NEW) |
| `docs/V1181_PRODUCTION_HARDENING_REPORT.md` | Hardening report (NEW) |
| `LANE_B_SECURITY_REPORT.md` | Security scan (NEW) |

## Credential Status

```
CREDENTIAL_REMEDIATION_PENDING_OPERATOR_APPROVAL
```

5bao key (`/home/vibeworker/.vibedev/secrets/debian-vibeworker-ed25519`):
- SHA256: `68ac4a2d7fa103d9d10034e440e907658950e35ba8279b3eec068c834d4f7f6f`
- Fingerprint: `SHA256:hO9+B7E3oBl9QrkL4pKk06xb1Dog7XwNZAfuH/lS5Kc`
- Same key as Windows controller
- Recommendation: Rotate to independent key
- Status: Pending Operator approval
