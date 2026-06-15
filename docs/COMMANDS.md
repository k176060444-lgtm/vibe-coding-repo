# Agent Command Cheatsheet

## Unified CLI Entry Point

Use the command router for all operations:

### Short Aliases

| Alias | Command | Description |
|-------|---------|-------------|
| `s` | snapshot | Operator Snapshot |
| `a` | advisor | Queue Advisor |
| `d` | dispatch | Dispatch Planner |
| `b` | batch-plan | Batch Queue Plan |
| `h` | health | Health Check |
| `sm` | smoke | Toolchain Smoke Suite |
| `i` / `wo` | intake | Work Order Intake |
| `notes` / `rn` / `progress` | release-notes | Release Notes |
| `dash` / `status-page` | dashboard | Project Dashboard |
| `?` | help | Show help |
| `v` | version | Show version |

**Typo correction**: If you type a misspelled command, the router suggests the closest match (e.g., `snapsho` → "Did you mean 'snapshot'?").

```bash
# Show help
python3 scripts/vibe_command_router.py help

# Operator Snapshot
python3 scripts/vibe_command_router.py snapshot --compact
python3 scripts/vibe_command_router.py snapshot --json

# Queue Advisor
python3 scripts/vibe_command_router.py advisor --json
python3 scripts/vibe_command_router.py advisor --include-tainted --include-merged --json

# Dispatch Planner
python3 scripts/vibe_command_router.py dispatch --compact
python3 scripts/vibe_command_router.py dispatch --json

# Batch Queue Plan
python3 scripts/vibe_command_router.py batch-plan --json
python3 scripts/vibe_command_router.py batch-plan --limit 3 --json

# Toolchain Smoke Suite
python3 scripts/test_toolchain_smoke.py
python3 scripts/test_toolchain_smoke.py --json

# Health Check

```bash
# Run health check (compact)
python3 scripts/vibe_health_check.py

# Run health check (JSON)
python3 scripts/vibe_health_check.py --json
```

# Health Check
python3 scripts/vibe_command_router.py health
```

# Agent Command Cheatsheet (Legacy)

Quick reference for QQ / Hermes orchestrator commands on Debian vibeworker.

## Status & Monitoring

```bash
# Operator Snapshot (compact, ~16 lines)
python3 scripts/vibe_operator_snapshot.py --compact

# Operator Snapshot (full JSON)
python3 scripts/vibe_operator_snapshot.py --json

# Include tainted/merged in snapshot
python3 scripts/vibe_operator_snapshot.py --include-tainted --include-merged --compact

# Queue Advisor (default)
python3 scripts/vibe_queue_advisor.py

# Queue Advisor (JSON with all details)
python3 scripts/vibe_queue_advisor.py --json

# Queue Advisor with tainted/merged
python3 scripts/vibe_queue_advisor.py --include-tainted --include-merged --json

# Dispatch Planner (next action suggestion)
python3 scripts/vibe_dispatch_planner.py --compact

# Dispatch Planner (JSON)
python3 scripts/vibe_dispatch_planner.py --json
```

## Job Registry

```bash
# List all jobs
python3 scripts/vibe_repo_status.py --jobs

# Jobs summary
python3 scripts/vibe_repo_status.py --jobs-summary

# Filter by status
python3 scripts/vibe_repo_status.py --jobs --status review_passed --json

# Filter by audit status
python3 scripts/vibe_repo_status.py --jobs --audit-status audit_tainted --json
```

## Failed Job Triage (Read-Only)

```bash
# Check a specific job's work-order
cat ~/vibedev/jobs/<job-id>/work-order.json

# Check job manifest
cat ~/vibedev/jobs/<job-id>/manifest.json

# Check if job result_sha is in main
cd ~/vibedev/repos/vibe-coding-repo.git
git merge-base --is-ancestor <result_sha> origin/main && echo "IN_MAIN" || echo "NOT_IN_MAIN"
```

## Creating a Work Order

1. Define work-order.json with required fields
2. Create worktree from main
3. Implement changes in worktree
4. Run tests (py_compile, import, --help, --json)
5. Commit with descriptive message
6. Push branch: `git push origin vibedev/<wo-id>`
7. Create PR: `gh pr create --repo k176060444-lgtm/vibe-coding-repo --head <branch> --base main`
8. Run wrapper dry-run (see below)
9. Run wrapper merge (see below)
10. Post-merge freeze (see below)

## Merge Gate (Pre-Merge Verification)

```bash
# Dry-run gate check
python3 scripts/vibe_merge_gate.py   --repo k176060444-lgtm/vibe-coding-repo   --pr <N>   --expected-base-sha <MAIN_SHA>   --expected-head-sha <HEAD_SHA>   --allowed-path <path1> --allowed-path <path2>   --job-id <WO_ID>   --json --dry-run
```

## Wrapper Merge (Must Use — No Bare gh pr merge!)

```bash
# Dry-run (must return allow_merge=true, merge_executed=false)
python3 scripts/vibe_autonomous_merge.py \
  --repo k176060444-lgtm/vibe-coding-repo \
  --pr <N> \
  --expected-base-sha <MAIN_SHA> \
  --expected-head-sha <HEAD_SHA> \
  --allowed-path <path1> --allowed-path <path2> \
  --job-id <WO_ID> \
  --json --dry-run

# Actual merge (must return merge_executed=true)
python3 scripts/vibe_autonomous_merge.py \
  --repo k176060444-lgtm/vibe-coding-repo \
  --pr <N> \
  --expected-base-sha <MAIN_SHA> \
  --expected-head-sha <HEAD_SHA> \
  --allowed-path <path1> --allowed-path <path2> \
  --job-id <WO_ID> \
  --json
```

## Post-Merge Freeze

After wrapper merge succeeds:

```bash
# 1. Fetch and verify new main
git fetch origin
git rev-parse origin/main

# 2. Check PR state
gh pr view <N> -R k176060444-lgtm/vibe-coding-repo --json state

# 3. Verify changed paths
git diff <old_main>..<new_main> --name-only

# 4. Compile and test on new main
git checkout origin/main -- scripts/ docs/
python3 -m py_compile scripts/<changed>.py

# 5. Negative wrapper test (must return allow_merge=false)
python3 scripts/vibe_autonomous_merge.py ... --json
# Expected: blockers = ["PR state is MERGED", "Main SHA mismatch"]

# 6. Verify wo-code-repo-status-001 lock
cat ~/vibedev/jobs/wo-code-repo-status-001/work-order.json | python3 -c 'import sys,json; d=json.load(sys.stdin); print(d["audit_status"], d["push_allowed"])'
```

## Maintenance

```bash
# List worktrees
git worktree list

# Remove a worktree (only if HEAD in main and clean)
git worktree remove ~/vibedev/worktrees/<name> --force

# List remote branches
git branch -r

# Delete a remote branch (requires authorization)
git push origin --delete <branch_name>
```

## Key Constraints

- **NEVER** use bare `gh pr merge` — always use `vibe_autonomous_merge.py`
- **NEVER** delete `wo-code-repo-status-001` records or unlock
- **NEVER** print/echo/record PAT/token
- **NEVER** push to main directly
- **NEVER** deploy/tag/release without explicit authorization
- **ALWAYS** verify `origin/main` before starting a Work Order
- **ALWAYS** run post-merge freeze after wrapper merge

## Autonomous Operation Runbook

For detailed autonomous operation boundaries, stop conditions, and human approval points, see:
- **[AUTONOMOUS_OPERATION_RUNBOOK.md](AUTONOMOUS_OPERATION_RUNBOOK.md)**: Full autonomous operation runbook

## QQ Command Routing

For detailed command specifications, permission boundaries, and prohibited behaviors, see:
- **[QQ_COMMAND_ROUTING.md](QQ_COMMAND_ROUTING.md)**: Full command routing specification
- **[WORKFLOW.md](WORKFLOW.md)**: Workflow documentation and merge requirements
- **[AUTONOMOUS_MERGE_GATE.md](AUTONOMOUS_MERGE_GATE.md)**: Merge gate specification

## Batch Queue Plan

Generate batch execution plan for multiple Work Orders:

```bash
# Generate batch execution plan (JSON)
python3 scripts/vibe_batch_plan.py --json

# Generate batch plan with limit
python3 scripts/vibe_batch_plan.py --limit 3 --json

# Generate batch plan (compact text)
python3 scripts/vibe_batch_plan.py
```



## Toolchain Freeze

See [TOOLCHAIN_FREEZE.md](TOOLCHAIN_FREEZE.md) for the complete frozen toolchain state, including:
- Stable commands and scripts
- CLI flags reference
- Recommendation consistency rules
- Batch queue execution method
- Human stop conditions
- Known reserved items (wo-code-repo-status-001)
- Merge policy and scope boundaries


## Live Examples (Real Output)

### Short Aliases

```
$ python scripts/vibe_command_router.py s --compact
════════════════════════════════════════
  📊 Operator Snapshot
════════════════════════════════════════
  Main:     32f81591d42f
  Remote:   32f81591d42f
  Sync:     YES
  Jobs:     26
  Merged:   18
  Blocked:  1 (1 hidden)
  Actions:  0
  Warnings: 0
  ...
  ➡ NEXT: queue_clean: consider documentation, next phase planning, or queue cleanup
════════════════════════════════════════
```

```
$ python scripts/vibe_command_router.py a --json | python -c "import sys,json; d=json.load(sys.stdin); print(d['total_jobs'])"
26
```

```
$ python scripts/vibe_command_router.py d --json | python -c "import sys,json; d=json.load(sys.stdin); print(d['recommended_action'])"
queue_clean
```

### Typo Correction

```
$ python scripts/vibe_command_router.py snapsho
ERROR: Unknown command 'snapsho'. Did you mean 'snapshot'?
```

```
$ python scripts/vibe_command_router.py helpp
ERROR: Unknown command 'helpp'. Did you mean 'help'?
```

### Version

```
$ python scripts/vibe_command_router.py v
vibe_command_router 2.0.0
Scripts: 6 registered
Aliases: 8 defined
```

### Health Check

```
$ python scripts/vibe_command_router.py h
========================================
  Health Check v1
========================================
  ✓ py_compile: PASS - 8 scripts compiled
  ✓ import: PASS - 8 scripts importable
  ✓ operator_snapshot: PASS - total=26
  ✓ queue_advisor: PASS - total=26
  ✓ dispatch_planner: PASS - recommended=queue_clean
  ✓ batch_plan: PASS - tasks=0
  ✓ audit_tainted_lock: PASS - 1 tainted lock(s) visible
----------------------------------------
  Overall: PASS (7 pass, 0 warn, 0 fail)
========================================
```

### Smoke Suite

```
$ python scripts/vibe_command_router.py sm
========================================
  Toolchain Smoke Suite v1
========================================
  ✓ command_router_help: PASS - help works
  ✓ command_router_snapshot: PASS - snapshot works
  ✓ command_router_advisor: PASS - total=26
  ✓ command_router_dispatch: PASS - recommended=queue_clean
  ✓ command_router_batch_plan: PASS - tasks=0
  ✓ health_check: PASS - overall=PASS
  ✓ operator_snapshot: PASS - total=26
  ✓ queue_advisor: PASS - total=26
  ✓ dispatch_planner: PASS - recommended=queue_clean
  ✓ batch_plan: PASS - tasks=0
  ✓ recommendation_consistency: PASS - consistent: all report queue_clean/0-tasks
----------------------------------------
  Overall: PASS (11 passed, 0 failed)
========================================
```

### Batch Plan (JSON)

```
$ python scripts/vibe_command_router.py b --json
{
  "batch_id": "batch-0-tasks",
  "task_order": [],
  "task_count": 0,
  "risk_level": "low",
  ...
}
```

### Batch Plan (with limit)

```
$ python scripts/vibe_command_router.py b --json --limit 3
```

## Command Behavior Matrix

| Command | Read-Only | Triggers Work Order | Human Approval |
|---------|-----------|-------------------|----------------|
| `snapshot` | ✅ | No | No |
| `advisor` | ✅ | No | No |
| `dispatch` | ✅ | Suggests only | No |
| `batch-plan` | ✅ | Plans only | No |
| `health` | ✅ | No | No |
| `smoke` | ✅ | No | No |
| `merge` | ❌ | Executes merge | Wrapper gate |

**All commands except `merge` are read-only.** The `merge` command is the only one with side effects and requires wrapper gate approval.


## Feature Work Order Template

See [WORK_ORDER_TEMPLATE.md](WORK_ORDER_TEMPLATE.md) for the template used to convert user requirements into executable Work Orders.

### Quick Reference

| Field | Description |
|-------|-------------|
| `work_order_id` | `wo-{type}-{name}-{seq}` |
| `scope.allowed_paths` | Files that can be modified |
| `acceptance_criteria` | Testable requirements |
| `review_criteria` | Quality gates |
| `stop_conditions` | When to halt execution |

### Type Prefixes

| Prefix | Use Case |
|--------|----------|
| `wo-code-` | Code changes |
| `wo-doc-` | Documentation |
| `wo-maint-` | Maintenance |
| `wo-test-` | Tests only |
| `wo-fix-` | Bug fixes |


## Work Order Intake

Convert natural language requirements into structured Work Order drafts.

```
$ python scripts/vibe_workorder_intake.py 'Add --summary flag to snapshot'
# Work Order Draft

**ID**: `wo-code-add-summary-001`
**Title**: Add --summary flag to snapshot
**Type**: code
**Risk**: medium
**Human Approval**: Not required

## Goal
Add --summary flag to snapshot

## Allowed Paths
- `scripts/`

## Acceptance Tests
1. python -m py_compile passes on all modified Python files
2. --help flag works and shows expected options
3. Smoke suite passes (all existing tests)
...

**⚠️ DRAFT ONLY — This is a proposal, not an executed task.**
```

### JSON Output

```
$ python scripts/vibe_workorder_intake.py 'Update workflow docs' --type doc --json
{
  "work_order_id": "wo-doc-update-workflow-001",
  "title": "Update workflow docs",
  "type": "doc",
  "risk_level": "low",
  "requires_human_approval": false,
  "allowed_paths": ["docs/"],
  "acceptance_tests": [...],
  "draft_only": true,
  "execution_requires_explicit_approval": true
}
```

### Options

| Flag | Description |
|------|-------------|
| `--json` | Output in JSON format |
| `--type TYPE` | Override auto-detected type (code/doc/test/fix/maint) |
| `--priority PRIORITY` | Override risk level (low/medium/high/critical) |
| `--file PATH` | Read requirement from file |
| `--output PATH` | Write draft to file |

### Risk Classification

| Level | Keywords | Human Approval |
|-------|----------|----------------|
| critical | security, credential, secret, deploy | Required |
| high | refactor, breaking change, api change | Required |
| medium | new script, new feature, modify | Not required |
| low | documentation, typo, rename | Not required |


### Intake via Router

```
$ python scripts/vibe_command_router.py intake 'Add --summary flag to snapshot'
# Work Order Draft

**ID**: `wo-code-add-summary-flag-001`
**Title**: Add --summary flag to snapshot
**Type**: code
**Risk**: low
...

$ python scripts/vibe_command_router.py i 'Fix advisor crash' --type fix --priority high --json
{
  "work_order_id": "wo-fix-fix-advisor-crash-001",
  "type": "fix",
  "risk_level": "high",
  "requires_human_approval": true,
  ...
}
```


### Smoke Suite Coverage

The smoke suite now covers 16 tests:
- 1-5: Command Router (help, snapshot, advisor, dispatch, batch-plan)
- 6: Health Check
- 7-10: Core tools (snapshot, advisor, dispatch, batch-plan)
- 11: Recommendation Consistency
- 12: Intake - basic markdown draft
- 13: Intake - JSON output validation
- 14: Intake - risk classification (critical/high/medium/low)
- 15: Intake - type detection (code/doc/test/fix/maint)
- 16: Intake - router integration
- 17: Release Notes - basic compact
- 18: Release Notes - JSON output
- 19: Release Notes - safety/audit lock
- 20: Release Notes - router integration
- 21: Dashboard - text output
- 22: Dashboard - JSON output
- 23: Dashboard - aliases (dash, status-page)


## Release Notes / Progress Report

Generate stage reports from git history, merge commits, and toolchain state.

```
$ python scripts/vibe_release_notes.py --compact
# Release Notes / Progress Report

**Generated**: 2026-06-15T...
**Main SHA**: `5d421c04226d...`
**Total PRs Merged**: 37

---

## PR Summary
- **Feature**: 15
- **Documentation**: 12
- **Testing**: 5
- **Maintenance**: 3

## Capability Changes
- **Work Order Intake** (feature) — PR #35
- **Command Router V2** (feature) — PR #30
- **Operational Readiness** (documentation) — PR #34
...

## Safety Status
- **audit_tainted lock**: `wo-code-repo-status-001` — push_allowed=False (PERMANENT)
- **Secrets modified**: False
```

### Options

| Flag | Description |
|------|-------------|
| `--json` | Full JSON report |
| `--compact` | Shorter text output |
| `--limit N` | Max PRs to include |
| `--since SHA` | Only PRs after this commit |


### Release Notes via Router

```
$ python scripts/vibe_command_router.py notes --compact
# Release Notes / Progress Report
**Main SHA**: `e4a1ac9...`
**Total PRs Merged**: 38
...

$ python scripts/vibe_command_router.py rn --json --limit 5
{ "current_main_sha": "e4a1ac9...", "total_merged_prs": 5, ... }
```


## Project Dashboard

See [PROJECT_DASHBOARD.md](PROJECT_DASHBOARD.md) for the complete operator-facing status dashboard.

Includes: system status, router commands, toolchain scripts, autonomous capabilities, safety status, lifecycle summary, recent merges, quick commands, and next phase recommendations.


### Dashboard via Router

```
$ python scripts/vibe_command_router.py dash
========================================
  📊 Project Dashboard
========================================
  Baseline:  cc5501f375efc86d28435563d6860aa67fef9f3f
  Total PRs Merged: 40
  Status:    🟢 OPERATIONAL
  Smoke:     PASS
  Health:    PASS
  Queue:     Clean
  Dashboard: docs/PROJECT_DASHBOARD.md
========================================
```

```
$ python scripts/vibe_command_router.py dash --json
{ "dashboard_path": "docs/PROJECT_DASHBOARD.md", "exists": true, "version": "2.3.0", ... }
```


## Demo Scenarios

Repeatable scenario examples for the intake→dispatch→report pipeline.

```
$ python scripts/vibe_demo_scenarios.py --list
  queue-clean          Queue Clean — System Health & Status
  feature-request      Feature Request — Intake & Planning
  maintenance          Maintenance — Health & Reporting

$ python scripts/vibe_demo_scenarios.py --scenario queue-clean
========================================
  Demo Scenario: Queue Clean — System Health & Status
========================================
  ✓ Operator Snapshot: PASS
  ✓ Dispatch Planner: PASS
  ✓ Release Notes (last 5): PASS
----------------------------------------
  Overall: PASS (3/3)
  Expected: queue_clean — no action required
========================================
```

### Scenarios

| Scenario | Flow | Steps |
|----------|------|-------|
| `queue-clean` | snapshot→dispatch→release-notes | 3 |
| `feature-request` | intake→dispatch→batch-plan | 3 |
| `maintenance` | health→release-notes→snapshot | 3 |
