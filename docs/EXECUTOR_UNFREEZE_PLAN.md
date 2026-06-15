# Executor Unfreeze Plan

**Status:** DRAFT — requires human approval before any level activation
**Current Level:** 0 (noop/dry-run only)
**Last Updated:** 2026-06-15

---

## Overview

This document defines a graduated unfreeze plan for the executor subsystem.
Each level unlocks additional capabilities with corresponding safety requirements.
No level may be activated without explicit human approval and all entry conditions met.

---

## Level 0: Current State (noop/dry-run)

**Status:** ACTIVE (frozen)

### Capabilities
- `noop` adapter: 1-step no-op, no side effects
- `dry-run` adapter: 8-step simulated execution, writes transcript only
- All adapters refuse: model_call, shell_exec, repo_write, git_push, git_merge, deploy, tag, file_delete

### Entry Conditions
- Always active (default state)

### Forbidden Actions
- All real execution actions are forbidden

### Evidence Required
- None (this is the baseline)

### Rollback
- N/A (no changes to roll back)

### Stop Conditions
- N/A (default safe state)

---

## Level 1: Fixture-Only Local Write

**Status:** NOT ACTIVATED — requires human approval

### Capabilities
- Write a single fixture file (`EXECUTOR_FIXTURE.md`) to a temporary fixture worktree
- No production file modifications
- No push, no PR, no merge
- Sandbox-enforced isolation

### Entry Conditions (all must be GREEN)
- [ ] Human explicitly approves Level 1 activation
- [ ] Sandbox check PASS (all 12 constraints)
- [ ] Gate check returns ALLOW for fixture workorder
- [ ] Approval receipt exists with valid SHA256 digest
- [ ] Fixture workorder registered with `status=approved`
- [ ] Smoke suite PASS (currently 61/61)
- [ ] No active audit_tainted violations (except wo-code-repo-status-001)
- [ ] `wo-code-repo-status-001` remains `audit_tainted`, `push_allowed=false`
- [ ] Recovery plan exists for `dirty_worktree` failure type
- [ ] Cancel token generated and validated

### Forbidden Actions
- `git_push` — no push to any remote
- `git_merge` — no merge to any branch
- `deploy` — no deployment
- `tag` — no git tags
- `file_delete` — no file deletion
- `model_call` — no model API calls
- `shell_exec` — no shell command execution
- Production file modifications — any file outside fixture worktree

### Approval Materials
- Sandbox check output (JSON)
- Gate check output (JSON)
- Approval receipt (JSON)
- Fixture workorder specification
- Recovery plan for each applicable failure type
- Cancel token

### Evidence Required
- Fixture file created in fixture worktree
- Transcript of fixture creation
- Evidence bundle with fixture file hash
- Verifier PASS

### Rollback
1. Delete fixture worktree
2. Delete fixture workorder from registry
3. Delete fixture evidence/transcript
4. Verify no production files modified
5. Log rollback action

### Stop Conditions
- Sandbox check FAIL
- Gate check BLOCK
- Evidence verifier FAIL
- Production file detected in changed_paths
- Push attempt detected
- Model call detected
- Shell exec detected

---

## Level 2: Fixture Branch Push

**Status:** NOT ACTIVATED — requires human approval

### Capabilities
- Everything in Level 1, plus:
- Push fixture branch to remote (dedicated fixture branch, not main)
- No PR creation, no merge to main

### Entry Conditions (all must be GREEN)
- [ ] All Level 1 entry conditions met
- [ ] Level 1 completed successfully with valid evidence
- [ ] Human explicitly approves Level 2 activation
- [ ] Dedicated fixture branch name approved by human
- [ ] Remote push target verified (not main, not production)
- [ ] Branch protection rules verified (no direct push to main)

### Forbidden Actions
- `git_merge` to main — no merge to main branch
- `deploy` — no deployment
- `tag` — no git tags
- `file_delete` — no file deletion
- `model_call` — no model API calls
- `shell_exec` — no shell command execution
- PR creation — no pull requests
- Production branch modifications

### Approval Materials
- All Level 1 approval materials
- Fixture branch specification
- Remote push target verification
- Branch protection verification

### Evidence Required
- All Level 1 evidence
- Push confirmation (branch name, commit SHA)
- Remote branch existence verification

### Rollback
1. Delete remote fixture branch
2. Delete local fixture branch
3. All Level 1 rollback steps
4. Verify no production branches modified
5. Log rollback action

### Stop Conditions
- All Level 1 stop conditions
- Push to main detected
- Push to production branch detected
- PR creation detected

---

## Level 3: Low-Risk Docs/Code PR via Wrapper

**Status:** NOT ACTIVATED — requires human approval

### Capabilities
- Everything in Level 2, plus:
- Create PR for low-risk changes (docs, tests, non-critical code)
- Merge via `vibe_autonomous_merge.py` wrapper only
- No direct `gh pr merge`

### Entry Conditions (all must be GREEN)
- [ ] All Level 2 entry conditions met
- [ ] Level 2 completed successfully with valid evidence
- [ ] Human explicitly approves Level 3 activation
- [ ] Changed paths limited to: `docs/`, `scripts/`, `tests/`, `README.md`
- [ ] No changes to: `secrets/`, `.github/workflows/`, `deploy/`, `ssh/`, `provider/`, `admin/`
- [ ] Autonomous merge wrapper validated (dry-run PASS)
- [ ] Wrapper merge method: merge commit only (no squash/rebase)
- [ ] PR template includes: summary, testing, changed_paths, rollback plan

### Forbidden Actions
- `deploy` — no deployment
- `tag` — no git tags
- `file_delete` — no file deletion outside scope
- `model_call` — no model API calls (code changes must be pre-written)
- `shell_exec` — no shell command execution
- Direct `gh pr merge` — must use wrapper
- Squash or rebase merge — merge commit only
- Changes to secrets/CI/Provider/SSH/production

### Approval Materials
- All Level 2 approval materials
- PR template with changed_paths
- Wrapper dry-run output
- Risk assessment for changed files

### Evidence Required
- All Level 2 evidence
- PR URL and number
- Wrapper merge confirmation
- Post-merge main SHA
- Smoke suite PASS after merge

### Rollback
1. Close PR if not merged
2. Revert merge commit if merged
3. Delete feature branch
4. All Level 2 rollback steps
5. Verify main is clean
6. Log rollback action

### Stop Conditions
- All Level 2 stop conditions
- Wrapper merge BLOCK
- Changed paths outside allowed scope
- High-risk file modification detected
- Smoke suite FAIL after merge

---

## Level 4: Broader Autonomous Execution

**Status:** NOT ACTIVATED — requires human approval

### Capabilities
- Everything in Level 3, plus:
- Model calls for code generation
- Shell execution for testing
- Broader file modifications
- All features of the full autonomous loop

### Entry Conditions (all must be GREEN)
- [ ] All Level 3 entry conditions met
- [ ] Level 3 completed successfully with valid evidence (at least 3 PRs)
- [ ] Human explicitly approves Level 4 activation
- [ ] Model provider credentials validated
- [ ] Test infrastructure operational
- [ ] Rollback procedures tested and validated
- [ ] Monitoring and alerting configured
- [ ] Human override mechanism tested

### Forbidden Actions
- `deploy` to production without explicit human approval
- `tag` releases without explicit human approval
- Changes to secrets without explicit human approval
- Changes to CI/Provider/SSH without explicit human approval

### Approval Materials
- All Level 3 approval materials
- Model provider validation
- Test infrastructure validation
- Rollback procedure test results
- Monitoring configuration
- Human override test results

### Evidence Required
- All Level 3 evidence
- Model call logs
- Shell execution logs
- Test results
- Code quality metrics

### Rollback
1. Cancel any in-progress execution
2. Revert all changes since last checkpoint
3. All Level 3 rollback steps
4. Verify repository integrity
5. Log rollback action

### Stop Conditions
- All Level 3 stop conditions
- Model provider unavailable
- Test infrastructure failure
- Rollback procedure failure
- Human override requested

---

## Level Progression Rules

1. **Sequential only** — must complete Level N before activating Level N+1
2. **Human approval required** — each level requires explicit human approval
3. **Evidence required** — each level must produce valid evidence before progression
4. **Rollback tested** — rollback procedures must be validated at each level
5. **Stop conditions enforced** — any stop condition halts progression

---

## Current Readiness

| Component | Status | Level 1 Ready |
|-----------|--------|---------------|
| Sandbox | ✅ operational | YES |
| Gate | ✅ operational | YES |
| Adapter | 🔒 frozen (noop/dry-run) | YES (Level 0) |
| Control | ✅ operational | YES |
| Recovery | ✅ operational | YES |
| Transcript | ✅ operational | YES |
| Evidence | ✅ operational | YES |
| Verifier | ✅ operational | YES |
| Smoke Suite | ✅ 61/61 PASS | YES |

---

## References

- `docs/EXECUTOR_BOUNDARY_FREEZE.md` — current freeze status
- `docs/MINIMAL_EXECUTOR_FIXTURE_SPEC.md` — Level 1 fixture specification
- `scripts/vibe_executor_sandbox.py` — sandbox checks
- `scripts/vibe_execution_gate.py` — gate checks
- `scripts/vibe_executor_recovery.py` — recovery plans
- `scripts/vibe_executor_control.py` — timeout/cancel control

## Level 1 Fixture Specification
Detailed fixture spec: docs/MINIMAL_EXECUTOR_FIXTURE_SPEC.md
