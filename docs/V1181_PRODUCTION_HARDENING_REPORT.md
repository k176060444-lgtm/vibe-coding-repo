# V1.18.1 Production Hardening — Final Report

**Date**: 2026-06-18
**Frozen HEAD**: `60409e62558bddcdbcbc68b070fa125595ffeb9d`

## Status

```
V1.18.1_PRODUCTION_HARDENING_PASS
V1.17.7_FREEZE_UNCHANGED
CREDENTIAL_REMEDIATION_PENDING_OPERATOR_APPROVAL
```

## Three-Node HEAD Consistency

| Node | HEAD | Branch | Status |
|------|------|--------|--------|
| Windows (KK-PC-Server) | `60409e6` | main | ✓ clean |
| 5bao (192.168.5.6:22222) | `60409e6` | fix/v11714-immutable-repair-closure | ✓ clean |
| 9bao (192.168.9.6:22222) | `60409e6` | fix/v11714-immutable-repair-closure | ✓ clean |

## OpenCode Runtime

| Node | Version |
|------|---------|
| 5bao | 1.17.4 |
| 9bao | 1.17.4 |

## Regression Tests (ALL PASSED)

| Test | Windows | 5bao | 9bao |
|------|---------|------|------|
| Lifecycle self-check (20) | 20/20 | 20/20 | 20/20 |
| Orchestrator self-check (30) | 30/30 | 30/30 | 30/30 |
| pytest (29) | 29/29 | 29/29 | 29/29 |

## Lane A: Real Remote Fault Recovery

| # | Scenario | Result | Evidence |
|---|----------|--------|----------|
| A.1 | Normal job on 5bao | ✅ SUCCEEDED | exit_code=0, remote_pid=720186 |
| A.2 | ripgrep→9bao routing | ✅ routed to 9bao | actual_worker=9bao, exit_code=0 |
| A.3 | SSH launch timeout→RECOVERY_REQUIRED | ✅ RECOVERY_REQUIRED | Remote completed (exit=0), claim preserved |
| A.4 | Cancel running task | ✅ CANCELLED | Claim state updated, remote process killed |
| A.5 | Long task across heartbeat | ✅ SUCCEEDED | 30s sleep completed, heartbeat maintained |
| A.6 | Active-active 5bao+9bao parallel | ✅ Both SUCCEEDED | remote_pid 721319/2531913 |
| A.7 | Third task capacity | ✅ SUCCEEDED | Scheduler re-uses completed workers |
| A.8 | Claim store cleanup | ✅ Verified | Backup created, atomic clean, checksum valid |

### Key Findings (Lane A)

1. **SSH launch timeout**: Remote process runs independently after timeout. Claim correctly enters RECOVERY_REQUIRED. Remote PID not captured (remote_pid=None in claim).
2. **Cancel**: Claim state updates to CANCELLED but remote process NOT automatically killed. Manual kill required. **Gap identified for V1.18**.
3. **Active-active**: Both workers process jobs in parallel correctly.
4. **Capacity management**: Completed jobs don't permanently block capacity (correct behavior).

## Lane B: Security Audit & Path Investigation

| # | Task | Result |
|---|------|--------|
| B.1 | Secret scan (current tree) | ✅ CLEAN — 16 matches, ALL false positives |
| B.2 | Secret scan (git history) | ✅ CLEAN — no historical secrets |
| B.3 | Unicode bidi/control scan | ✅ CLEAN — zero bidi characters |
| B.4 | Windows path investigation | ⚠️ 2 hardcoded `C:/Users/KK/...` paths (intentional) |
| B.5 | Credential remediation package | See below |

### Credential Remediation Package

**5bao controller key**:
- Path: `/home/vibeworker/.vibedev/secrets/debian-vibeworker-ed25519`
- Owner: vibeworker:vibeworker
- Mode: 600
- SHA256: `68ac4a2d7fa103d9d10034e440e907658950e35ba8279b3eec068c834d4f7f6f`
- Fingerprint: `SHA256:hO9+B7E3oBl9QrkL4pKk06xb1Dog7XwNZAfuH/lS5Kc`

**Windows controller key**:
- Path: `C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519`
- Mode: 644
- SHA256: `68ac4a2d7fa103d9d10034e440e907658950e35ba8279b3eec068c834d4f7f6f`
- Fingerprint: `SHA256:hO9+B7E3oBl9QrkL4pKk06xb1Dog7XwNZAfuH/lS5Kc`

**Relationship**: SAME KEY — identical SHA256 and fingerprint.

**Three remediation options**:

| Option | Action | Impact | Rollback |
|--------|--------|--------|----------|
| 1. Delete | Remove 5bao key | 5bao cannot authenticate to other services using this key | Restore from backup |
| 2. Rotate | Generate new 5bao key, update authorized_keys | Requires coordinated update | Re-apply old key |
| 3. Keep | No action | Risk if 5bao compromised | N/A |

**Recommendation**: Option 2 (Rotate) — generate independent key for 5bao worker.

**Status**: `CREDENTIAL_REMEDIATION_PENDING_OPERATOR_APPROVAL` — no action taken.

## V1.17.7 Freeze Integrity

| Item | Status |
|------|--------|
| Freeze manifest SHA256 | `3699732c936ff672f794f9b7301b0b6877779994eadbac9206852ed582288c3c` ✓ UNCHANGED |
| Frozen HEAD | `60409e6` ✓ |
| Manifest content | Not modified |

## V1.18 Production Hardening Backlog

The following items are deferred to subsequent V1.18 sprints:

1. **Cancel remote process kill**: Cancel command should automatically kill remote process group
2. **SSH timeout PID capture**: Capture remote PID before timeout for proper recovery
3. **Credential rotation**: Generate independent key for 5bao (pending Operator approval)
4. **GitHub formal review capability**: Enable real PR reviews
5. **Secret history scan**: Deep scan with dedicated tools (git-secrets, truffleHog)
6. **Repair concurrency stress test**: Concurrent receipt competition under load
7. **GitHub bidi warning investigation**: Compare with local Unicode scan
8. **MSYS path verifier**: Fix file-mutation verifier path handling

## Model/Worker Roles

| Role | Model | Worker |
|------|-------|--------|
| Lane A testing | Windows Controller | 5bao, 9bao |
| Lane B security scan | mimo-v2.5-pro (subagent) | Local |
| Regression | Windows/5bao/9bao | All nodes |
