# Level 4A: Real Executor First Run — Documentation PR

> **Work Order:** `wo-executor-level4a-real-executor-docs-pr-001`
> **Executor Model:** `xiaomi-plan/mimo-v2.5-pro` (Hermes Agent, real model invocation)
> **Execution Date:** 2026-06-15
> **Authorization:** Human explicitly authorized Level 4A docs-only real executor

## 1. Scope and Constraints

### Allowed Actions

| Action | Status |
|--------|--------|
| Real model invocation | ✅ Authorized |
| Create dedicated branch | ✅ `level4a/wo-executor-level4a-real-executor-docs-pr-001` |
| Write single docs file | ✅ `docs/LEVEL4A_REAL_EXECUTOR_DEMO.md` only |
| Local commit | ✅ |
| Push to GitHub branch | ✅ |
| Create PR | ✅ |
| Wrapper dry-run | ✅ `scripts/vibe_autonomous_merge.py` |
| Wrapper merge | ✅ |

### Forbidden Actions

| Action | Status |
|--------|--------|
| Bare `gh pr merge` | ❌ Forbidden — must use wrapper |
| Modify `scripts/` code | ❌ Forbidden |
| Modify secrets/CI/SSH/Provider | ❌ Forbidden |
| Deploy/tag/release | ❌ Forbidden |
| Force push | ❌ Forbidden |
| Delete records | ❌ Forbidden |
| Remove audit_tainted lock | ❌ Forbidden |
| Level 4B / broader autonomy | ❌ Not activated |

## 2. Unfreeze Levels Recap

| Level | Name | Status | Date |
|-------|------|--------|------|
| Level 0 | noop/dry-run (frozen) | ✅ Completed | Pre-June 2026 |
| Level 1 | Fixture-only local write | ✅ Completed | 2026-06-15 |
| Level 2 | Fixture branch push | ✅ Completed | 2026-06-15 |
| Level 3 | Low-risk docs PR via wrapper | ✅ Completed (PR #79) | 2026-06-15 |
| Level 3B | Low-risk tooling code PR | ✅ Completed (PR #80) | 2026-06-15 |
| **Level 4A** | **Real executor docs-only PR** | **✅ This document** | **2026-06-15** |
| Level 4B | Broader autonomous execution | ❌ NOT ACTIVATED | — |

## 3. What "Real Executor" Means

At Level 4A, the executor is no longer a stub or dry-run adapter. The actual AI model
(`mimo-v2.5-pro` via Hermes Agent) is authorized to:

1. **Read** the work order and understand requirements
2. **Generate** documentation content based on the task specification
3. **Write** the file into an isolated branch
4. **Test** the result (smoke suite must pass)
5. **Submit** via the full PR → wrapper → merge pipeline

This is the first time the model produces real, committed, merged output in the repository.

## 4. Execution Pipeline

```
Work Order (human-authored)
    ↓
Model reads task → generates docs/LEVEL4A_REAL_EXECUTOR_DEMO.md
    ↓
Branch: level4a/wo-executor-level4a-real-executor-docs-pr-001
    ↓
git add + commit + push to GitHub
    ↓
PR created (#81)
    ↓
Wrapper dry-run: scripts/vibe_autonomous_merge.py --dry-run
    ↓  (must be ALLOW)
Wrapper merge: scripts/vibe_autonomous_merge.py merge
    ↓  (must succeed)
Post-merge origin/main advances
    ↓
Transcript + Evidence + Verifier
    ↓
Smoke suite: 66/66 PASS
```

## 5. Evidence and Audit Trail

Every step produces auditable evidence:

- **Transcript**: `txn-001` — records adapter, base_sha, gate_verdict, steps_executed
- **Evidence**: `ev-001` — records base/result SHAs, PR URL, wrapper results, smoke result
- **Evidence Verifier**: 9 checks (required_fields, digest_match, registry_entry, approval_receipt, shas_present, smoke_result, job_status, audit_status, changed_paths)
- **Smoke Suite**: 66 tests covering router, health, snapshot, queue, dispatch, intake, release notes, dashboard, validator, packager, registry, gate, adapter, transcript, loop summary, sandbox, control, recovery, unfreeze, context detection

## 6. What Is NOT Enabled at Level 4A

| Capability | Level 4A | Level 4B (future) |
|------------|----------|-------------------|
| Docs-only changes | ✅ | ✅ |
| Code changes (scripts/) | ❌ | ✅ (with review) |
| Multi-file changes | ❌ | ✅ (limited scope) |
| Consecutive work orders | ❌ | ✅ (with approval) |
| Auto-merge without wrapper | ❌ | ❌ (always forbidden) |
| Real model executor | ✅ (this run) | ✅ |
| Deploy/release | ❌ | ❌ (always forbidden) |

## 7. Guardrails

### Wrapper Requirements

All merges must go through `scripts/vibe_autonomous_merge.py`:

- **dry-run**: verifies PR state, base SHA, head SHA, allowed paths, job status
- **merge**: executes `gh pr merge --merge` only if dry-run passes
- **blockers**: SHA mismatch, non-allowed paths, job not found, PR not mergeable

### Scope Enforcement

- `--allowed-path docs/LEVEL4A_REAL_EXECUTOR_DEMO.md` restricts wrapper to this single file
- Any `scripts/` or config change would trigger a BLOCK

### Audit Lock

- `wo-code-repo-status-001` remains `audit_status=audit_tainted`, `push_allowed=false`
- This lock is never removed by automated processes

## 8. Lessons Learned

1. **Context detection matters**: The smoke suite now correctly handles temp-context vs repo-context, preventing false failures when run outside the full repo.
2. **Structured warnings are better**: Evidence verifier now outputs `missing_fields` and `expected_fixture_mode`, making fixture-mode warnings self-explanatory.
3. **Wrapper is the gate**: The autonomous merge wrapper enforces scope, SHA consistency, and merge method — it is the single point of merge control.
4. **Real executor needs guardrails**: Even for a single docs file, the full pipeline (gates → commit → push → PR → wrapper → evidence) ensures accountability.

## 9. Next Steps

Level 4B readiness requires:

- [ ] Human explicitly approves Level 4B activation
- [ ] Model provider credentials validated
- [ ] Test infrastructure validated
- [ ] Rollback procedures tested
- [ ] Monitoring configured
- [ ] Human override tested
- [ ] All Level 4A evidence archived

**Level 4B is NOT ACTIVATED. Waiting for separate human approval.**

---

*Generated by: `mimo-v2.5-pro` (Hermes Agent real executor)*
*Work Order: `wo-executor-level4a-real-executor-docs-pr-001`*
*Execution timestamp: 2026-06-15T08:30:00Z*
