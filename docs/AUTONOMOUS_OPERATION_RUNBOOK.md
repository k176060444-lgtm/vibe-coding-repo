# Autonomous Operation Runbook

Defines boundaries, stop conditions, human approval points, and operational rules for repo-scoped autonomous mode.

## Scope

### What Autonomous Mode Can Do
- Read-only status checks (snapshot, queue, plan, batch)
- Create feature branches and worktrees
- Implement code changes within declared scope
- Run tests and verification
- Create pull requests
- Execute wrapper merge (with gate pass)
- Post-merge freeze verification

### What Autonomous Mode Cannot Do
- Push directly to main
- Merge without wrapper
- Delete records or worktrees without authorization
- Modify secrets/permissions/CI/workflow/admin/Provider/SSH
- Deploy/tag/release
- Force push or reset
- Release audit_tainted locks
- Print/echo/record PAT/token

## Stop Conditions

Execution MUST stop immediately when ANY of these conditions are detected:

| # | Condition | Action |
|---|-----------|--------|
| 1 | origin/main SHA changes during execution | Stop, report, re-verify base_sha |
| 2 | Gate check returns blockers | Stop, report blockers |
| 3 | Wrapper merge returns allow_merge=false | Stop, report blockers |
| 4 | Changed paths exceed declared scope | Stop, report scope violation |
| 5 | audit_tainted lock status changes | Stop, report lock change |
| 6 | New high-priority failures detected | Stop, report failures |
| 7 | Any Work Order fails acceptance | Stop, report failure |
| 8 | PR state is not OPEN | Stop, report PR state |
| 9 | Head SHA mismatch | Stop, report mismatch |
| 10 | Base SHA mismatch | Stop, report mismatch |

## Human Approval Points

These actions REQUIRE explicit human approval before execution:

| Action | Approval Required |
|--------|-------------------|
| Work Order creation | Yes (confirm scope, risk, model) |
| Wrapper merge execution | Yes (confirm gate pass, changed paths) |
| Remote branch deletion | Yes (confirm branch list) |
| Worktree cleanup | Yes (except forced cleanup of untracked) |
| audit_tainted lock release | NEVER (permanent lock) |
| Secrets/Provider modification | NEVER (out of scope) |

## Wrapper Merge Rules

### Pre-Merge Checklist
1. Verify origin/main == base_sha
2. Run gate check (vibe_merge_gate.py)
3. Verify changed_paths within scope
4. Run wrapper dry-run (must return allow_merge=true)
5. Verify PR state is OPEN
6. Verify head SHA matches commit

### Merge Execution
```bash
python3 scripts/vibe_autonomous_merge.py \
  --repo k176060444-lgtm/vibe-coding-repo \
  --pr <N> \
  --expected-base-sha <MAIN_SHA> \
  --expected-head-sha <HEAD_SHA> \
  --allowed-path <path1> --allowed-path <path2> \
  --job-id <WO_ID> \
  --json
```

### Post-Merge Freeze
1. Fetch and verify new main
2. Check PR state (MERGED)
3. Verify changed paths
4. Compile and test on new main
5. Negative wrapper test (must return allow_merge=false)
6. Verify wo-code-repo-status-001 lock

## audit_tainted Lock Rules

### What is audit_tainted?
An audit_tainted lock indicates a Work Order that has been flagged for manual review. This is a PERMANENT lock that cannot be released by autonomous mode.

### Lock Behavior
- `audit_status = "audit_tainted"` in work-order.json
- `push_allowed = false` (cannot push to remote)
- Worktree must be preserved (cannot delete)
- Records must be preserved (cannot delete)
- Lock status must be verified after every merge

### How to Handle audit_tainted Jobs
1. DO NOT attempt to release the lock
2. DO NOT delete the worktree
3. DO NOT delete records
4. Report lock status in every operator snapshot
5. Continue with other Work Orders (lock does not block other work)

## Batch Queue Usage

### When to Use Batch Queue
- Multiple low-risk Work Orders to execute
- Queue is clean (no high-priority failures)
- All Work Orders have clear scope and acceptance criteria

### Batch Queue Workflow
1. Run batch plan: `python3 scripts/vibe_batch_plan.py --json`
2. Verify risk_level and requires_human_approval
3. Execute Work Orders in task_order sequence
4. After each Work Order, verify post-merge freeze
5. Report batch summary at end

### Batch Queue Stop Conditions
Same as individual Work Order stop conditions, PLUS:
- Any Work Order in batch fails
- Batch risk level changes during execution
- New high-priority failures detected mid-batch

## Error Recovery

### If Wrapper Merge Fails
1. Do NOT retry automatically
2. Report blockers
3. Wait for human instruction
4. Do NOT force merge

### If Gate Check Fails
1. Do NOT proceed with merge
2. Report gate blockers
3. Wait for human instruction
4. Do NOT bypass gate

### If Post-Merge Freeze Fails
1. Report the failure
2. Do NOT continue with next Work Order
3. Wait for human instruction
4. Do NOT rollback without authorization

### If origin/main Changes
1. Stop current Work Order
2. Fetch and verify new main
3. Report the change
4. Wait for human instruction on whether to continue

## Operational Checklist

### Before Starting a Work Order
- [ ] Verify origin/main == expected base_sha
- [ ] Verify wo-code-repo-status-001 lock status
- [ ] Verify no high-priority failures in queue
- [ ] Verify Work Order scope is clear
- [ ] Verify model is approved

### During Work Order Execution
- [ ] Create isolated worktree
- [ ] Implement changes within scope
- [ ] Run tests and verification
- [ ] Commit with descriptive message
- [ ] Push branch to remote

### Before Wrapper Merge
- [ ] Run gate check (must pass)
- [ ] Run wrapper dry-run (must return allow_merge=true)
- [ ] Verify changed_paths within scope
- [ ] Verify PR state is OPEN
- [ ] Verify head SHA matches commit

### After Wrapper Merge
- [ ] Fetch and verify new main
- [ ] Check PR state (MERGED)
- [ ] Verify changed paths
- [ ] Compile and test on new main
- [ ] Negative wrapper test (must return allow_merge=false)
- [ ] Verify wo-code-repo-status-001 lock
- [ ] Clean up worktree

## References

- `docs/QQ_COMMAND_ROUTING.md`: Command routing specification
- `docs/COMMANDS.md`: Command cheatsheet
- `docs/WORKFLOW.md`: Workflow documentation
- `docs/AUTONOMOUS_MERGE_GATE.md`: Merge gate specification
- `docs/MODEL_SWITCH_RUNBOOK.md`: Model switching procedures
- `scripts/vibe_operator_snapshot.py`: Operator Snapshot
- `scripts/vibe_queue_advisor.py`: Queue Advisor
- `scripts/vibe_dispatch_planner.py`: Dispatch Planner
- `scripts/vibe_batch_plan.py`: Batch Queue Plan
- `scripts/vibe_autonomous_merge.py`: Merge Wrapper
- `scripts/vibe_merge_gate.py`: Merge Gate


## Toolchain Freeze Reference

The current toolchain state is documented in [TOOLCHAIN_FREEZE.md](TOOLCHAIN_FREEZE.md). When operating in autonomous mode:
1. Verify smoke suite passes before any Work Order: 
2. Use wrapper for all merges: 
3. Check recommendation consistency: snapshot/dispatch/batch-plan must agree
4. Respect the permanent audit_tainted lock on 


## Live Entry Points (QQ/Hermes)

### Daily Autonomous Workflow

1. **Morning check**: `/s --compact` — verify queue_clean, no new blockers
2. **Health gate**: `/h` — all 7 checks must pass before starting work
3. **Plan next work**: `/d --compact` — check recommended_action
4. **Batch execution**: `/b --json` — get execution plan for multiple tasks
5. **Post-work verification**: `/sm` — full smoke suite (11 tests)

### When to Stop and Ask Human

| Signal | Command | Action |
|--------|---------|--------|
| `resolve_blocked` in dispatch | `/d` | STOP — tainted lock needs human |
| `investigate_failures` | `/d` | STOP — failed job needs analysis |
| Health check FAIL | `/h` | STOP — toolchain broken |
| Smoke test FAIL | `/sm` | STOP — regression detected |
| `allow_merge=false` | wrapper | STOP — gate blocker |

### When to Proceed Autonomously

| Signal | Command | Action |
|--------|---------|--------|
| `queue_clean` | `/d` | Proceed with next planned Work Order |
| All PASS | `/h`, `/sm` | Safe to execute |
| `tasks=0` | `/b` | Queue empty, plan new work |
