# Executor Boundary Freeze

**Status:** FROZEN (as of 2026-06-15)
**Scope:** Vibe Coding Agent executor adapters
**Enforced by:** vibe_executor_adapter.py, vibe_execution_gate.py, policy.json

---

## Current Executor Boundary

The Vibe Coding Agent executor subsystem is currently frozen at the **noop/dry-run** level.
No real execution, model invocation, or side-effect-producing operations are permitted.

### Permitted Adapters

| Adapter | Mode | Steps | Side Effects | Purpose |
|---------|------|-------|-------------|---------|
| `noop` | noop | 1 | None | Testing, validation, smoke tests |
| `dry-run` | dry-run | 8 | None (writes transcript only) | Simulated execution, replay chain validation |

### Forbidden Actions (All Adapters)

The following actions are **permanently forbidden** for all current adapters:

| Action | Description | Enforcement |
|--------|-------------|-------------|
| `model_call` | Calling any LLM/AI model API | adapter contract |
| `shell_exec` | Executing shell commands | adapter contract |
| `repo_write` | Writing to repository source files | adapter contract |
| `git_push` | Pushing to remote repositories | adapter contract + gate |
| `git_merge` | Merging branches | adapter contract + gate |
| `deploy` | Deploying to any environment | adapter contract + gate |
| `tag` | Creating git tags | adapter contract + gate |
| `file_delete` | Deleting files | adapter contract |

### Gate Integration

The execution gate (`vibe_execution_gate.py`) enforces:

1. **Registry approved** — workorder must have `status=approved`
2. **Approval receipt exists** — SHA256 digest must match
3. **Base SHA matches** — workorder base_sha must equal current main HEAD
4. **Risk assessment** — high-risk workorders require human approval
5. **Stop conditions** — must not violate any declared stop conditions
6. **Allowed paths** — changed_paths must be within scope
7. **Forbidden high-risk** — no secrets/CI/Provider/SSH/production changes
8. **Audit lock** — `wo-code-repo-status-001` must remain `audit_tainted` with `push_allowed=false`

---

## Conditions for Real Executor Approval

A real executor (capable of model calls, code generation, file writes) requires **all** of the following:

### Technical Prerequisites

- [ ] Execution gate returns `ALLOW` for the target workorder
- [ ] Approval receipt with valid SHA256 digest exists
- [ ] Registry entry shows `status=approved`
- [ ] Base SHA matches current main HEAD
- [ ] Changed paths are within declared scope
- [ ] No forbidden high-risk paths (secrets/CI/Provider/SSH/production)

### Human Approval Requirements

- [ ] **Explicit human authorization** — user must approve the specific workorder execution
- [ ] **Model selection confirmation** — user must confirm the model to be used
- [ ] **Scope validation** — user must verify changed_paths are acceptable
- [ ] **Rollback plan** — user must confirm rollback capability exists

### Safety Invariants

- [ ] `wo-code-repo-status-001` remains `audit_tainted` with `push_allowed=false`
- [ ] No secrets/credentials in changed files
- [ ] No CI/workflow modifications
- [ ] No Provider/SSH configuration changes
- [ ] No production environment modifications

### Approval Workflow (Future)

```
1. User submits workorder via intake
2. Validate → Package → Register (status: draft → validated → packaged)
3. Human approves workorder (status: approved)
4. Approval receipt created with SHA256 digest
5. Execution gate checks all 8 conditions
6. Gate returns ALLOW
7. Human explicitly authorizes execution (THIS STEP REQUIRES MANUAL CONFIRMATION)
8. Real executor runs with approved model
9. Evidence bundle created
10. Transcript recorded
11. Evidence verifier checks integrity
12. Status updated (status: executed)
```

**Step 7 is the critical human checkpoint. No automation may bypass this step.**

---

## Current Toolchain Versions

| Component | Version | Status |
|-----------|---------|--------|
| vibe_executor_adapter.py | 1.0.0 | noop/dry-run only |
| vibe_execution_gate.py | 1.0.0 | 8-condition check |
| vibe_execution_transcript.py | 1.0.0 | append-only records |
| vibe_evidence_verifier.py | 1.0.0 | integrity checks |
| vibe_safe_executor.py | 1.0.0 | plan generator (no execution) |
| test_executor_replay.py | 1.0.0 | 10 replay tests |
| test_toolchain_smoke.py | 54 tests | all PASS |

---

## Escalation Path

To unfreeze the executor boundary and enable real execution:

1. **Document the change** — update this file with new adapter capabilities
2. **Update gate conditions** — add any new safety checks required
3. **Human approval** — user must explicitly approve the unfreeze
4. **Smoke tests** — all existing tests must continue to pass
5. **New tests** — add tests for the new executor capabilities
6. **Audit trail** — record the unfreeze decision in transcript

---

## References

- `docs/AUTONOMOUS_OPERATION_RUNBOOK.md` — operational procedures
- `docs/WORKFLOW.md` — complete workflow documentation
- `scripts/vibe_executor_adapter.py` — adapter contract definition
- `scripts/vibe_execution_gate.py` — execution gate implementation
- `scripts/vibe_safe_executor.py` — safe executor stub
