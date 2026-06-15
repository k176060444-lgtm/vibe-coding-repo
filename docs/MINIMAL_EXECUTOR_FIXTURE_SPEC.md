# Minimal Executor Fixture Specification

**Status:** SPECIFICATION — defines Level 1 fixture, does not execute
**Level:** 1 (Fixture-Only Local Write)
**Prerequisite:** `docs/EXECUTOR_UNFREEZE_PLAN.md` Level 1 entry conditions all GREEN

---

## Purpose

This document specifies the minimal real write operation that proves the executor
can safely modify a file within a sandboxed environment. The fixture is intentionally
trivial — the goal is validation, not functionality.

---

## Fixture Definition

### Target File
- **Path:** `EXECUTOR_FIXTURE.md` (in fixture worktree root)
- **Content:** Minimal markdown with timestamp, workorder ID, executor version, SHA256 hash
- **Size:** < 1KB
- **Format:** Markdown with YAML-like metadata

### Fixture Content Template

```markdown
# Executor Fixture

**Generated:** {timestamp}
**Workorder:** {workorder_id}
**Executor Version:** {executor_version}
**Mode:** Level 1 (Fixture-Only Local Write)
**Base SHA:** {base_sha_fixture_worktree_created_from}

## Verification

This file was created by the executor in Level 1 mode.
It proves the executor can safely write a file within a sandboxed environment.

**SHA256 of this content:** {sha256_hash}
```

### Content Constraints
- No secrets, credentials, or tokens
- No production data
- No model outputs (no code generation)
- No shell command results
- No external API responses
- Deterministic: same inputs produce same content

---

## Execution Environment

### Fixture Worktree
- **Location:** `/tmp/vibedev-fixtures/{workorder_id}/` (temporary)
- **Created from:** `origin/main` at `base_sha`
- **Lifetime:** deleted after evidence collection
- **Isolation:** no access to production worktree

### Sandbox Constraints
- Network: DISABLED
- Model calls: DISABLED
- Shell execution: DISABLED
- Write scope: fixture worktree ONLY
- Push: DISABLED
- Merge: DISABLED
- Deploy: DISABLED
- Tag: DISABLED

---

## Required Pipeline Steps

### Step 1: Pre-Execution Checks
1. Sandbox check PASS (12 constraints)
2. Gate check ALLOW
3. Approval receipt exists (SHA256 digest)
4. Registry status = approved
5. Smoke suite PASS (64/64)
6. Cancel token generated

### Step 2: Fixture Worktree Creation
1. Create temporary directory `/tmp/vibedev-fixtures/{workorder_id}/`
2. Clone `origin/main` at `base_sha` into fixture worktree
3. Verify worktree is clean
4. Record fixture worktree path

### Step 3: Fixture File Creation
1. Generate fixture content from template
2. Compute SHA256 of content
3. Write `EXECUTOR_FIXTURE.md` to fixture worktree root
4. Verify file written correctly (read back and hash)
5. Record file hash in transcript

### Step 4: Transcript Recording
1. Create transcript entry with:
   - workorder_id
   - adapter: "level1-fixture"
   - base_sha
   - fixture_file_hash
   - timestamp
   - status: "completed"
2. Compute transcript digest

### Step 5: Evidence Bundle Creation
1. Create evidence bundle with:
   - Fixture file content (or hash)
   - Transcript entry
   - Sandbox check output
   - Gate check output
   - Approval receipt
   - Fixture worktree path
   - Execution timestamp
2. Compute evidence digest

### Step 6: Verification
1. Run evidence verifier (9 checks)
2. Verify fixture file hash matches transcript
3. Verify no production files modified
4. Verify fixture worktree is isolated
5. Record verifier result

### Step 7: Cleanup
1. Delete fixture worktree
2. Delete fixture workorder from registry (optional, keep for audit)
3. Verify cleanup complete
4. Log cleanup action

---

## Evidence Requirements

| Evidence | Format | Required |
|----------|--------|----------|
| Fixture file content | markdown | YES |
| Fixture file SHA256 | hex string | YES |
| Transcript entry | JSON | YES |
| Transcript digest | SHA256 hex | YES |
| Sandbox check output | JSON | YES |
| Gate check output | JSON | YES |
| Approval receipt | JSON | YES |
| Evidence bundle | JSON | YES |
| Evidence digest | SHA256 hex | YES |
| Verifier result | JSON (PASS/WARN/FAIL) | YES |
| Cleanup confirmation | log entry | YES |

---

## Rollback Procedure

If any step fails:

1. **Cancel execution** — send cancel signal
2. **Delete fixture worktree** — `rm -rf /tmp/vibedev-fixtures/{workorder_id}/`
3. **Log failure** — record failure in transcript
4. **Update registry** — set status to `failed` if applicable
5. **Verify isolation** — confirm no production files affected
6. **Notify orchestrator** — report failure reason

---

## Stop Conditions

Execution must stop immediately if:

- Sandbox check returns FAIL
- Gate check returns BLOCK
- Production file detected in changed_paths
- Push attempt detected
- Model call detected
- Shell execution detected
- Network request detected
- Credential access detected
- Evidence verifier returns FAIL
- Cancel signal received

---

## Success Criteria

The fixture execution is successful if:

1. ✅ `EXECUTOR_FIXTURE.md` created in fixture worktree
2. ✅ File content matches template with valid SHA256
3. ✅ Transcript created with correct digest
4. ✅ Evidence bundle created with all required fields
5. ✅ Evidence verifier returns PASS
6. ✅ No production files modified
7. ✅ Fixture worktree cleaned up
8. ✅ All stop conditions remained GREEN throughout

---

## Future Extensions

After Level 1 is validated:

- **Level 2:** Push fixture branch to remote (dedicated fixture branch)
- **Level 3:** Create PR for low-risk changes via wrapper
- **Level 4:** Full autonomous execution with model calls

---

## References

- `docs/EXECUTOR_UNFREEZE_PLAN.md` — graduated unfreeze plan
- `docs/EXECUTOR_BOUNDARY_FREEZE.md` — current freeze status
- `scripts/vibe_executor_sandbox.py` — sandbox checks
- `scripts/vibe_execution_gate.py` — gate checks
- `scripts/vibe_execution_transcript.py` — transcript recording
- `scripts/vibe_execution_evidence.py` — evidence bundles
- `scripts/vibe_evidence_verifier.py` — evidence verification
- `scripts/vibe_executor_recovery.py` — recovery plans
