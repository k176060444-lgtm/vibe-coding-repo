# V1.18.1 Final Evidence Reconciliation Report

**Generated**: 2026-06-18T18:55:00+08:00
**Final HEAD**: `099bf16` (Merge pull request #161)
**PR #160**: V1.18.1 Production Hardening Reconciliation (merged)
**PR #161**: 3 crash-point fault injection tests (merged)
**evidence_scope**: controller_local

---

## 1. Code Publication

| Item | Value |
|------|-------|
| PR #160 SHA | `ed919ea` |
| PR #161 SHA | `099bf16` |
| Final HEAD (3-way) | `099bf16` |
| Windows HEAD | `099bf16` ✓ |
| 5bao HEAD | `099bf16` ✓ |
| 9bao HEAD | `099bf16` ✓ |
| Source SHA256 | `0bdc37353ca5b2451c45835956c4b9a14d2e7f1519da9ada6954a6fa6fbed16b` |
| pyc timestamp | 18:45 (newer than .py 18:07) ✓ |
| Version | 3.6.0 |

---

## 2. Cancel Test

| Item | Value |
|------|-------|
| Job ID | `job-98ef70aebf07` |
| Worker | 9bao |
| Remote PID | 2553172 |
| Remote PGID | 2553172 |
| Cancel result | `CONFIRMED_EXIT` |
| Remote process | DEAD (ps verified) |
| Claim | Released |
| Manifest state | `CANCELLED` |
| Manifest error | `cancelled_confirmed_exit` |
| Start time | 18:33:24 |
| End time | 18:35:01 |

---

## 3. Heartbeat Test

| Item | Value |
|------|-------|
| Job ID | `job-3b945444efb3` |
| Worker | 5bao |
| Remote PID | 740807 |
| Remote PGID | 740807 |
| Start | 10:35:58 |
| Heartbeat #1 | 10:37:59 (lease_until=1781779379) |
| Heartbeat #2 | 10:39:59 (lease_until=1781779499) |
| End | 10:40:42 |
| Duration | ~284s |
| Exit code | 0 |
| State | SUCCEEDED |

---

## 4. Repair Fault Injection (7/7 PASS)

| Test | Crash Point | State | Receipt | Latch |
|------|-------------|-------|---------|-------|
| Test 1: Concurrent | 2 processes race | 1 success | consumed | cleared |
| Test 2: Empty/Missing | invalid paths | rejected | N/A | active |
| Test 3: Single-Use | duplicate nonce | rejected | consumed | cleared |
| Test 4: Same SHA | wrong old_sha | rejected | N/A | active |
| Test 5: After Replace | post-replace | replaced | NOT consumed | active |
| Test 6: After Receipt | post-consume | replaced | consumed | active |
| Test 7: Before Replace | pre-replace | corrupted | NOT consumed | active |

---

## 5. Issues Resolved

| # | Original Issue | Resolution |
|---|---------------|------------|
| 1 | HEAD not in PR/merge | PR #160 + #161 merged, 3-way sync to 099bf16 |
| 2 | Stale .pyc | pyc cache cleared and rebuilt (18:45 > 18:07) |
| 3 | Reviewer/Verifier same model | Reviewer: mimo-v2.5-pro, Verifier: MiniMax-M3 |
| 4 | Cancel PID conflict 727254/727253 | New test: unique PID 2553172/2553172 |
| 5 | Heartbeat job/PID mapping | New test: 1:1 mapping, 2 heartbeats recorded |
| 6 | Repair 3 crash points | 3 new tests covering replace/receipt/latch |

---

## 6. Independent Verification

| Role | Model | Result |
|------|-------|--------|
| Reviewer | mimo-v2.5-pro | APPROVE |
| Verifier | MiniMax-M3 | 6/6 PASS |

### Reviewer Artifact
- Model: mimo-v2.5-pro
- Duration: 268s
- Verdict: APPROVE
- Key findings: Code correct, fail-closed maintained, tests adequate

### Verifier Artifact
- Model: MiniMax-M3
- Duration: 312s
- Verdict: 6/6 PASS
- Verified: merge SHA, source/pyc, cancel, heartbeat, repair, self-check

---

## 7. Regression Suite

| Test | Result |
|------|--------|
| Lifecycle (20) | 20/20 ✓ |
| Orchestrator (30) | 30/30 ✓ |
| pytest (29) | 29/29 ✓ |
| Repair concurrency (7) | 7/7 ✓ |
| V1.17.7 freeze manifest | `3699732c...` ✓ UNCHANGED |

---

## 8. Evidence Files

| File | Scope | SHA256 |
|------|-------|--------|
| `docs/V1181_RECONCILIATION_REPORT.md` | controller_local | (this file) |
| `docs/V1181_ACCEPTANCE_EVIDENCE.md` | controller_local | `cd2ba6ef...` |
| `docs/V1181_PRODUCTION_HARDENING_REPORT.md` | controller_local | `55f2011b...` |
| `docs/V1177_FINAL_FREEZE_MANIFEST.md` | controller_local | `3699732c...` |

---

## 9. Credential Status

```
CREDENTIAL_REMEDIATION_PENDING_OPERATOR_APPROVAL
```

5bao key 与 Windows key 相同。建议轮换为独立 key。等待 Operator 审批。

---

## Final Tokens

```
V1.18.1_PRODUCTION_HARDENING_PASS
V1.17.7_FREEZE_UNCHANGED
CREDENTIAL_REMEDIATION_PENDING_OPERATOR_APPROVAL
```
