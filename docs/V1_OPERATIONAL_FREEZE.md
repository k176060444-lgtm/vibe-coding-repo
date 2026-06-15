# V1 Operational Freeze

> **Freeze Date:** 2026-06-15
> **Freeze Baseline:** `b6cfc10f41f8ac35b4d297cf32fbf48ccbcf68a4`
> **Status:** FROZEN — V1 workflow is operational and validated

## 1. Current Freeze Baseline

| Item | Value |
|------|-------|
| origin/main | `b6cfc10f41f8ac35b4d297cf32fbf48ccbcf68a4` |
| Router | v2.10.0 |
| Smoke Tests | 75/75 PASS |
| Quality Gate | PASS (6/6 checks) |
| PR Count | #4–#88 (85 PRs merged via wrapper) |
| Executor | FROZEN at Level 4E |

## 2. Validated Capabilities (Level 1 → 4E)

| Level | Name | Status | PR(s) |
|-------|------|--------|-------|
| Level 1 | Fixture-only local write | ✅ Validated | — |
| Level 2 | Fixture branch push | ✅ Validated | fixture branches |
| Level 3 | Low-risk docs PR via wrapper | ✅ Validated | #79 |
| Level 3B | Low-risk tooling code PR | ✅ Validated | #80 |
| Level 4A | Real executor docs-only PR | ✅ Validated | #81 |
| Level 4B | Real executor tooling code PR | ✅ Validated | #82 |
| Level 4C | Real executor quality gate PR | ✅ Validated | #83 |
| Level 4D | Real executor run report PR | ✅ Validated | #84 |
| Level 4E | Small batch real executor queue | ✅ Validated | #85–#88 |
| Level 5 | Broader autonomous execution | ❌ NOT ACTIVATED | — |

## 3. Daily Entry Commands

```bash
# Before any execution: quality gate
python scripts/vibe_command_router.py qg --json
python scripts/vibe_command_router.py go-no-go --compact

# After execution: run report
python scripts/vibe_command_router.py rr --json
python scripts/vibe_command_router.py handoff --compact

# Full verification
python scripts/vibe_command_router.py smoke
python scripts/vibe_command_router.py ls --compact
python scripts/vibe_command_router.py s --compact
python scripts/vibe_command_router.py help
```

## 4. Standard Work Order Lifecycle

```
1. Human writes Work Order requirements
2. quality-gate check → must PASS or explainable WARN
3. Create branch from latest origin/main
4. Real executor (model) generates code/docs/tests
5. Verify changed_paths within allowed scope
6. repo-context smoke → must PASS
7. temp-context smoke → must PASS
8. Commit + push to GitHub
9. Create PR
10. wrapper dry-run → must ALLOW
11. wrapper merge → must succeed
12. Post-merge smoke → must PASS
13. quality-gate → must PASS
14. run-report → generate summary
15. Human reviews and approves next step
```

## 5. Wrapper Merge Requirement

**All merges MUST go through `scripts/vibe_autonomous_merge.py`.**

```bash
# Dry-run first
python scripts/vibe_autonomous_merge.py \
  --repo k176060444-lgtm/vibe-coding-repo \
  --pr <NUMBER> \
  --expected-base-sha <BASE> \
  --expected-head-sha <HEAD> \
  --allowed-path <PATH> \
  --job-id <WO_ID> \
  --json --dry-run

# Then merge
python scripts/vibe_autonomous_merge.py \
  --repo k176060444-lgtm/vibe-coding-repo \
  --pr <NUMBER> \
  --expected-base-sha <BASE> \
  --expected-head-sha <HEAD> \
  --allowed-path <PATH> \
  --job-id <WO_ID> \
  --json
```

Bare `gh pr merge` is **FORBIDDEN**.

## 6. Audit Lock Policy

`wo-code-repo-status-001` must remain:
- `audit_status=audit_tainted`
- `push_allowed=false`

This lock is **NEVER** removed by automated processes. It serves as a permanent
safety gate preventing accidental pushes to the main branch without human approval.

## 7. Forbidden Actions

| Category | Forbidden |
|----------|-----------|
| Secrets/Config | secrets, CI, Provider, SSH, workflow, admin |
| Git Operations | force push, reset, delete branches |
| Deployment | deploy, tag, release |
| Merge | bare `gh pr merge` (must use wrapper) |
| Records | delete records, digests, jobs |
| Audit | remove audit_tainted lock |
| Dependencies | add external dependencies |
| Scope | large-scale refactoring outside allowed paths |

## 8. Level 5 Status

**Level 5 (broader autonomous execution) is NOT ACTIVATED.**

Activation requires:
- [ ] Human explicitly approves Level 5
- [ ] Multi-work-order autonomous queue validated
- [ ] Monitoring and alerting configured
- [ ] Rollback procedures tested
- [ ] Human override tested
- [ ] All Level 4E evidence archived

Until all conditions are met, Level 5 remains frozen.

## 9. Emergency Procedures

If quality-gate returns BLOCK:
1. **STOP** all execution
2. Run `smoke` to identify specific failures
3. Run `run-report` for full context
4. Investigate and fix before proceeding
5. Re-run quality-gate to confirm PASS

If audit lock is missing or altered:
1. **STOP** immediately
2. Do NOT proceed with any execution
3. Report to human operator
4. Investigate potential security issue

---

*This document is part of the V1 Operational Freeze. Do not modify without human approval.*
