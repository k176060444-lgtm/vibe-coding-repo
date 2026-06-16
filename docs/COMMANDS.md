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
| `validate` / `vw` | validate-wo | Work Order Validator |
| `pack` / `pw` | pack-wo | Work Order Packager |
| `pre` | preflight | Preflight Check (intake+validate+pack) |
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
- 24: Daily Report - text
- 25: Daily Report - JSON
- 26: Validator - basic validation
- 27: Packager - basic packaging
- 28: Preflight - router chain


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


## Report Export

Export toolchain reports (snapshot, release-notes, dashboard) to files.

```
$ python scripts/vibe_report_export.py --kind snapshot --dry-run
========================================
  Report Export: snapshot
========================================
  ✓ snapshot: snapshot_20260615_001530.md
----------------------------------------
  Exported: 1/1
  Mode: DRY RUN (no files written)
========================================

$ python scripts/vibe_report_export.py --kind all --output-dir /tmp/reports --json
{
  "kind": "all",
  "exported": 3,
  "total": 3,
  "output_dir": "/tmp/reports",
  "written_files": ["/tmp/reports/snapshot_....md", ...]
}
```

### Options

| Flag | Description |
|------|-------------|
| `--kind` | snapshot, release-notes, dashboard, or all |
| `--output-dir` | Directory to write report files |
| `--json` | JSON output |
| `--dry-run` | Preview without writing |


## Operator Daily Report

One-command daily status summary.

```
$ python scripts/vibe_daily_report.py --compact
========================================
  Daily Report — 2026-06-15
========================================
  Main:       69385eb90b86
  Router:     v2.3
  Smoke:      PASS (23/23)
  Health:     PASS
  Queue:      queue_clean (jobs=26, actions=0, warnings=0)
----------------------------------------
  Recent PRs:
    #45 wo-code-report-export-001
    #44 wo-code-demo-scenario-pack-001
    ...
----------------------------------------
  Audit Lock: audit_tainted (push_allowed=False)
----------------------------------------
  Next: queue_clean
========================================
```


## Work Order Validator

Validate intake drafts for execution readiness.

```
$ python scripts/vibe_workorder_validator.py draft.json
========================================
  Work Order Validation: ✓ PASS
========================================
  ✓ All required fields present (11)
  ✓ Valid type: code
  ✓ Valid risk_level: low
  ✓ Human approval: False (matches risk)
  ✓ allowed_paths valid (2 paths)
  ✓ forbidden_actions defined (6 rules)
  ✓ Goal present (45 chars)
  ✓ acceptance_tests defined (5 criteria)
  ✓ stop_conditions defined (7 conditions)
  ✓ work_order_id format valid: wo-code-add-summary-001
========================================
```

```
$ python scripts/vibe_workorder_validator.py draft.json --json
{ "overall": "PASS", "checks": [...], "warnings": [], "errors": [] }
```


## Work Order Packager

Package validated drafts into execution prompts for Hermes.

```
$ python scripts/vibe_workorder_intake.py 'Add --verbose flag' --json > draft.json
$ python scripts/vibe_workorder_validator.py draft.json
$ python scripts/vibe_workorder_packager.py draft.json
Execute Work Order: wo-code-add-verbose-flag-001

## Task
Title: Add --verbose flag
Type: code
Risk: low
...

## Baseline
origin/main: df6735711d46...
Router: v2.3
Smoke: 25 tests
...

## Scope
Allowed paths:
  - scripts/
...
```

```
$ python scripts/vibe_workorder_packager.py draft.json --json
{ "work_order_id": "...", "chunks": [...], "chunk_count": 1, "total_chars": 1234 }
```

```
$ python scripts/vibe_workorder_packager.py draft.json --max-chars 500
=== Chunk 1/3 ===
...
=== Chunk 2/3 ===
...
```


### Preflight Chain

```
$ python scripts/vibe_command_router.py preflight 'Add --verbose flag to health check'
========================================
  Preflight Check
========================================
  Requirement: Add --verbose flag to health check
  Draft ID:    wo-code-add-verbose-flag-001
  Type:        code
  Risk:        low
  Human:       False
  Validation:  PASS
  Package:     2278 chars, 1 chunk(s)
----------------------------------------
  ✓ Preflight: PASS
========================================
```

###  /  (Work Order Registry)
Register, list, and show work order entries in a local registry directory.

**Subcommands:**
-  — Register new entry
-  — List all entries
-  — Show entry details

**Options:**
-  — Registry directory (default: VIBEDEV_REGISTRY_DIR env)
-  — JSON output

**Examples:**
```
python3 scripts/vibe_workorder_registry.py register --registry-dir /tmp/registry --id my-wo --title Add feature X
python3 scripts/vibe_workorder_registry.py list --registry-dir /tmp/registry --json
python3 scripts/vibe_workorder_registry.py show --registry-dir /tmp/registry --id my-wo
```


### `registry` / `reg` (Work Order Registry)
Register, list, and show work order entries in a local registry directory.

**Subcommands:**
- `register --id ID [--title TITLE] [--risk-level low|medium|high|critical] [--status draft|validated|packaged|approved|executed|blocked] [--base-sha SHA] [--source SRC] [--requires-human-approval]` — Register new entry
- `list [--filter-status STATUS]` — List all entries
- `show --id ID` — Show entry details

**Options:**
- `--registry-dir DIR` — Registry directory (default: VIBEDEV_REGISTRY_DIR env)
- `--json` — JSON output

**Examples:**
```
python3 scripts/vibe_workorder_registry.py register --registry-dir /tmp/registry --id my-wo --title "Add feature X"
python3 scripts/vibe_workorder_registry.py list --registry-dir /tmp/registry --json
python3 scripts/vibe_workorder_registry.py show --registry-dir /tmp/registry --id my-wo
```


### `registry` / `reg` / `wo-list` / `wo-show` (Work Order Registry)
Register, list, and show work order entries in a local registry directory.

**Subcommands:**
- `register --id ID [--title TITLE] [--risk-level low|medium|high|critical] [--status draft|validated|packaged|approved|executed|blocked]` — Register new entry
- `list [--filter-status STATUS]` — List all entries
- `show --id ID` — Show entry details

**Options:**
- `--registry-dir DIR` — Registry directory (default: VIBEDEV_REGISTRY_DIR env)
- `--json` — JSON output

**Examples:**
```
python3 scripts/vibe_command_router.py reg register --id my-wo --title "Add feature X"
python3 scripts/vibe_command_router.py reg list --json
python3 scripts/vibe_command_router.py reg show --id my-wo
python3 scripts/vibe_command_router.py wo-list --registry-dir /tmp/registry
```


### `update-status` (Status Transitions)
Update status with controlled transitions and append-only history.

**Valid Transitions:**
- draft → validated, blocked
- validated → packaged, blocked
- packaged → approved, blocked
- approved → executed, blocked
- executed → blocked
- blocked → draft (reset)

**Usage:**
```
python3 scripts/vibe_workorder_registry.py update-status --id my-wo --status validated --reason "All checks passed"
python3 scripts/vibe_workorder_registry.py update-status --id my-wo --status packaged --reason "Package ready" --json
```

**Features:**
- Validates transitions (rejects illegal jumps)
- Requires --reason for audit trail
- Append-only history with SHA256 digest
- JSON output with --json flag


### `approval-receipt` / `receipt` (Approval Receipt)
Generate local approval receipts for Work Orders.

**Subcommands:**
- `create --id ID --base-sha SHA --package-digest DIGEST --approver LABEL --approval-text TEXT` — Create receipt
- `list` — List all receipts
- `show --receipt-id ID` — Show receipt details

**Options:**
- `--registry-dir DIR` — Registry directory (default: VIBEDEV_REGISTRY_DIR env)
- `--json` — JSON output

**Examples:**
```
python3 scripts/vibe_approval_receipt.py create --id my-wo --base-sha abc123 --package-digest def456 --approver "human" --approval-text "Approved"
python3 scripts/vibe_approval_receipt.py list --json
python3 scripts/vibe_approval_receipt.py show --receipt-id receipt-001
```

**Features:**
- SHA256 digest of receipt data
- Includes requires_human_approval, approved_scope, stop_conditions from workorder
- Does NOT execute Work Orders


### `wo-status` / `ws` (Work Order Status Update)
Update status with controlled transitions via router.

**Usage:**
```
python3 scripts/vibe_command_router.py ws --id my-wo --status validated --reason "All checks passed"
python3 scripts/vibe_command_router.py wo-status --id my-wo --status packaged --reason "Package ready" --json
```

### `receipt` / `ar` / `approve-receipt` (Approval Receipt)
Create and manage approval receipts via router.

**Usage:**
```
python3 scripts/vibe_command_router.py ar create --id my-wo --base-sha abc123 --package-digest def456 --approver "human" --approval-text "Approved"
python3 scripts/vibe_command_router.py receipt list --json
python3 scripts/vibe_command_router.py ar show --receipt-id receipt-001
```


### `execution-evidence` / `ev` / `exec-log` (Execution Evidence)
Bundle execution evidence for Work Orders.

**Subcommands:**
- `create --id ID --base-sha SHA --result-sha SHA [options]` — Create evidence bundle
- `list` — List all evidence bundles
- `show --evidence-id ID` — Show evidence details

**Create Options:**
- `--pr-url URL` — PR URL
- `--pr-number NUM` — PR number
- `--post-merge-sha SHA` — Post-merge main SHA
- `--wrapper-dry-run RESULT` — Wrapper dry-run result
- `--wrapper-merge RESULT` — Wrapper merge result
- `--smoke-result RESULT` — Smoke test result
- `--health-result RESULT` — Health check result
- `--implementer-model MODEL` — Implementer model
- `--reviewer-model MODEL` — Reviewer model
- `--job-status STATUS` — Job status
- `--audit-status STATUS` — Audit status
- `--changed-paths PATHS` — Changed paths (comma-separated)

**Examples:**
```
python3 scripts/vibe_execution_evidence.py create --id my-wo --base-sha abc123 --result-sha def456 --smoke-result "36/36 PASS"
python3 scripts/vibe_execution_evidence.py list --json
python3 scripts/vibe_execution_evidence.py show --evidence-id ev-001
```


### `evidence` / `ev` / `exec-log` (Execution Evidence)
Create and manage execution evidence bundles via router.

**Usage:**
```
python3 scripts/vibe_command_router.py ev create --id my-wo --base-sha abc123 --result-sha def456 --smoke-result "36/36 PASS"
python3 scripts/vibe_command_router.py evidence list --json
python3 scripts/vibe_command_router.py ev show --evidence-id ev-001
```


### `execution-gate` / `gate` / `ready-run` (Execution Gate)
Pre-execution admission check for Work Orders.

**Usage:**
```
python3 scripts/vibe_execution_gate.py check --id my-wo --current-main-sha abc123
python3 scripts/vibe_execution_gate.py check --id my-wo --current-main-sha abc123 --json
```

**Checks:**
- Registry status is approved
- Approval receipt exists
- Base SHA matches current main
- Risk level and human approval
- Stop conditions
- Allowed paths not empty
- Forbidden actions (high-risk detection)
- Audit tainted lock

**Verdicts:**
- **ALLOW** — all checks passed, safe to execute
- **REVIEW** — warnings found, human review recommended
- **BLOCK** — critical issues found, must not execute


### `exec-gate` / `gate` / `ready-run` (Execution Gate)
Pre-execution admission check via router.

**Usage:**
```
python3 scripts/vibe_command_router.py gate --id my-wo --current-main-sha abc123
python3 scripts/vibe_command_router.py exec-gate --id my-wo --current-main-sha abc123 --json
python3 scripts/vibe_command_router.py ready-run --id my-wo --current-main-sha abc123
```


### Golden Path E2E Test Suite

End-to-end tests covering the complete Work Order lifecycle:

```
requirement → intake → validate → registry.register → packager →
registry.update-status → approval-receipt.create → execution-gate.check →
evidence.create
```

**Test Paths:**
- **ALLOW** — valid workorder through full pipeline, gate returns ALLOW
- **BLOCK** — base_sha mismatch triggers BLOCK at gate
- **REVIEW** — stop conditions trigger REVIEW at gate

**Usage:**
```
python3 scripts/test_golden_path_e2e.py
python3 scripts/test_golden_path_e2e.py --json
python3 scripts/test_golden_path_e2e.py --verbose
```

All tests use temporary directories, no repo modifications.

###  /  (Evidence Verifier)
Verify execution evidence bundle integrity and consistency.

**Usage:**
```
python3 scripts/vibe_evidence_verifier.py verify --evidence-dir /path --registry-dir /path --evidence-id ev-001
python3 scripts/vibe_evidence_verifier.py verify --evidence-dir /path --registry-dir /path --evidence-id ev-001 --json
```

**Checks:**
- Required fields present
- Digest matches recomputed
- Registry entry exists
- Approval receipt exists
- SHAs present
- Smoke result
- Job/audit status
- Changed paths within scope

**Verdicts:** PASS / WARN / FAIL

###  /  /  (Safe Executor)
Generate execution plans from ALLOW gate results. Does NOT execute coding agents.

**Usage:**
```
python3 scripts/vibe_safe_executor.py plan --id my-wo --current-main-sha abc123
python3 scripts/vibe_command_router.py se plan --id my-wo --current-main-sha abc123 --json
python3 scripts/vibe_safe_executor.py plan --id my-wo --current-main-sha abc123 --dry-run --plan-only
```

**Output:** execution_plan, required_inputs, blocked_if, evidence_expectations

### adapter / ac (Executor Adapter Contract)
Query and validate executor adapter capabilities. Read-only contract definition; adapters never execute real work.

**Usage:**
```
python3 scripts/vibe_executor_adapter.py capabilities
python3 scripts/vibe_executor_adapter.py capabilities --adapter noop --json
python3 scripts/vibe_executor_adapter.py plan --adapter dry-run --id my-wo --base-sha abc123 --json
python3 scripts/vibe_executor_adapter.py validate-inputs --adapter noop --id my-wo --base-sha abc123 --gate-verdict ALLOW
python3 scripts/vibe_command_router.py adapter capabilities --json
python3 scripts/vibe_command_router.py adapter plan --adapter noop --id my-wo --base-sha abc123
python3 scripts/vibe_command_router.py adapter validate-inputs --adapter dry-run --id my-wo --base-sha abc123
```

**Adapters:** noop (1-step no-op), dry-run (8-step simulated execution)
**Forbidden actions:** model_call, shell_exec, repo_write, git_push, git_merge, deploy, tag, file_delete

### transcript / txn / exec-txn (Execution Transcript)
Append-only record of executor dry-run / noop sessions. Captures gate verdict, adapter plan, receipt digest, base_sha, timestamp, status.

**Usage:**
```
python3 scripts/vibe_execution_transcript.py create --id my-wo --adapter noop --base-sha abc123
python3 scripts/vibe_execution_transcript.py list --json
python3 scripts/vibe_execution_transcript.py show --transcript-id txn-001 --json
python3 scripts/vibe_command_router.py txn create --id my-wo --adapter dry-run --base-sha abc123 --json
python3 scripts/vibe_command_router.py txn list --transcript-dir /path --json
```

**Fields:** transcript_id, workorder_id, adapter, base_sha, gate_verdict, approval_receipt_digest, timestamp, status, digest (SHA256)

### sandbox / sb (Executor Sandbox Contract)
Verify sandbox constraints for future real execution. Read-only checks; never creates worktrees or writes repos.

**Usage:**
```
python3 scripts/vibe_executor_sandbox.py check --base-sha abc123 --json
python3 scripts/vibe_executor_sandbox.py plan --id my-wo --base-sha abc123 --json
python3 scripts/vibe_command_router.py sb check --json
python3 scripts/vibe_command_router.py sb plan --id my-wo --base-sha abc123
```

**Checks:** constraints_defined, forbidden_actions, base_sha, artifact_dirs, network/model/write isolation, forbidden/allowed paths, execution_timeout, destructive_blocked, shell_blocked

### exec-control / ec / ctrl (Executor Control)
Timeout, cancel, and control contract for executor lifecycle. Planning only; no process killed.

**Usage:**
```
python3 scripts/vibe_executor_control.py plan-timeout --id my-wo --max-seconds 300 --json
python3 scripts/vibe_executor_control.py cancel-token --id my-wo --json
python3 scripts/vibe_executor_control.py status --id my-wo --json
python3 scripts/vibe_command_router.py ec plan-timeout --id my-wo --json
python3 scripts/vibe_command_router.py ec cancel-token --id my-wo
```

**Features:** timeout phases, heartbeat monitoring, stale lock detection, cancel token, graceful/immediate/file-signal cancel methods

### recovery / rc / recover (Executor Recovery Plan)
Failure recovery/rollback plan generator. Covers 8 failure types. Plan-only; no reset/clean/rm/push/delete executed.

**Usage:**
```
python3 scripts/vibe_executor_recovery.py plan --id my-wo --failure-type model_error --json
python3 scripts/vibe_executor_recovery.py classify-failure --id my-wo --error-msg 'quota exceeded' --json
python3 scripts/vibe_command_router.py rc plan --id my-wo --failure-type timeout --json
```

**Failure types:** model_error, timeout, dirty_worktree, gate_blocked, wrapper_blocked, test_failed, partial_artifacts, evidence_mismatch

### unfreeze-checklist / uc / unfreeze (Executor Unfreeze Checklist)
Machine-readable unfreeze readiness check for levels 1-4. Read-only; does NOT unfreeze executor.

**Usage:**
```
python3 scripts/vibe_executor_unfreeze_checklist.py --level 1 --json
python3 scripts/vibe_executor_unfreeze_checklist.py --level 2 --compact
python3 scripts/vibe_command_router.py uc --level 3 --json
python3 scripts/vibe_command_router.py unfreeze --level 4 --compact
```

**Output:** required_approvals, required_green_checks, forbidden_actions, evidence_required, rollback_required, go_no_go


### quality-gate (qg, go-no-go)

Workflow Quality Gate — aggregated pre/post-execution health check.

```bash
python scripts/vibe_command_router.py quality-gate [--json] [--compact]
python scripts/vibe_command_router.py qg --json
python scripts/vibe_command_router.py go-no-go
```

Checks: smoke suite, router version, audit lock, origin/main sync, loop summary, evidence verifier.

Output: PASS / WARN / BLOCK with operator summary.





### priv-approval (priv-appr, approval)

Privileged Approval — controlled approval workflow for high-privilege actions.

\
**Short approval words:** approve, confirmed, 批准, 确认, 同意, 可以执行

**Output fields:** action_id, repo, branch, action, base_sha, changed_paths, forbidden_actions, expires_at, digest, status (pending|approved|expired|blocked)


### priv-push (pp, push-approved)

Privileged Push Wrapper — controlled push with repo trust policy (self-repo auto-allow, external requires approval).

\
**Output:** would_push (true/false), blockers, warnings, dry_run=true. Never reads GitHub Key. Never pushes.

### ext-auth-push (eap)

External Authorized Push Wrapper — controlled push to external repos with full validation chain.

```bash
python3 scripts/vibe_external_authorized_push.py --json validate --approval-id <id>
python3 scripts/vibe_external_authorized_push.py --json --approval-dir <dir> validate --approval-id <id>
python3 scripts/vibe_external_authorized_push.py --json dry-run --approval-id <id>
python3 scripts/vibe_external_authorized_push.py --json push --approval-id <id>
python3 scripts/vibe_external_authorized_push.py --json token-preflight
python3 scripts/vibe_external_authorized_push.py --json list
```

**Validation checks:** repo, branch, operation, base_sha, remote_branch_current_sha, local_commit_sha, changed_paths, patch_sha256, expires_at, force_push, delete_branch, tag/release/deploy, forbidden paths (.github/workflows/, secrets/, .env, ssh/), non-standard token env vars.

**Token source:** ONLY `/home/vibeworker/.vibedev/secrets/github_privileged_token`. NEVER reads `~/.vibedev-secrets/github.env` or any `GITHUB_PAT`/`GITHUB_TOKEN` env var.

**Token injection:** Temporary GIT_ASKPASS helper script, cleaned up after push. Token NEVER in argv, env, or output.

**Output:** would_push, blockers, warnings, remote_sha_match, push_command_safe, dry_run. Token content NEVER output.

### QQ Operator Quick Reference

See [QQ_OPERATOR_CHEATSHEET.md](QQ_OPERATOR_CHEATSHEET.md) for mobile QQ operation shortcuts.

Key shortcuts: qg, rr, smoke, snapshot, dashboard, loop-summary, advisor, batch-plan


### trusted-loop (tl, auto-loop, loop)

Trusted Self-Repo Auto-Loop Contract — verify autonomous execution loop.

```bash
python3 scripts/vibe_trusted_self_loop.py --check [--json] [--compact]
python3 scripts/vibe_trusted_self_loop.py --contract [--json]
python3 scripts/vibe_trusted_self_loop.py --validate <work-order.json> [--json]
python3 scripts/vibe_command_router.py tl --json
python3 scripts/vibe_command_router.py auto-loop --compact
```

Output: repo, repo_trust_level, requires_human_approval, policy_verdict, checks (smoke/qg/v1-freeze/rr/policy/wrapper).



### batch-runner (br, batch)

Trusted Self-Repo Batch Runner — serial execution of low-risk Work Orders.

```bash
python3 scripts/vibe_batch_runner.py --batch <batch.json> [--json] [--dry-run]
python3 scripts/vibe_batch_runner.py --status [--json]
python3 scripts/vibe_command_router.py br --status --json
python3 scripts/vibe_command_router.py batch --batch plan.json --dry-run --json
```

Output: batch_id, wo_id, repo_trust_level, branch, pr, changed_paths, merge_sha, status, blockers, stop_reason.

Max batch size: 5 Work Orders. Stop on any failure.


### worker-resilience (wr, worker, resilience)

Worker Reachability & Resilience — retry, checkpoint, resume.

```bash
python3 scripts/vibe_worker_resilience.py --check [--json] [--compact]
python3 scripts/vibe_worker_resilience.py --checkpoint <file> [--json]
python3 scripts/vibe_worker_resilience.py --resume <file> [--json]
python3 scripts/vibe_worker_resilience.py --status-report <file> [--json]
python3 scripts/vibe_command_router.py wr --json
python3 scripts/vibe_command_router.py worker --check --compact
```

Output: worker_status, worker_error, retry_interval_minutes, max_wait_minutes, resume_allowed.


### batch-runner v1.2.0 report fields

Enhanced batch report includes:
- `work_order_count`, `completed_count`, `stopped_count`
- `last_successful_baseline`, `final_baseline`
- `stop_reason`, `per_wo_prs`, `per_wo_changed_paths`
- `checkpoint_status`, `resume_status`


### batch-status (bs)

Current batch status — read-only snapshot.

```bash
python3 scripts/vibe_batch_runner.py --batch-status [--checkpoint <file>] [--json] [--compact]
python3 scripts/vibe_command_router.py bs --json
```

Output: batch_id, status, current_wo, phase, baseline_before, current_baseline, last_safe_point, resume_allowed, worker_status, retry_count, next_retry_at, completed_count, remaining_count, last_pr, last_changed_paths.

### batch-report (breport)

Detailed batch report — read-only, extended status with per-WO breakdown.

```bash
python3 scripts/vibe_batch_runner.py --batch-report [--checkpoint <file>] [--json] [--compact]
python3 scripts/vibe_command_router.py breport --json
```

Output: All batch-status fields plus report_type, report_time, batch_runner_version, repo, repo_trust_level, per_wo_status, stop_reason, worker_error, recommended_action.

### batch-pause (bp)

Pause batch at safe point. Writes PAUSED checkpoint. Does not interrupt in-flight git operations.

```bash
python3 scripts/vibe_batch_runner.py --pause [--checkpoint <file>] [--json] [--compact]
python3 scripts/vibe_command_router.py bp --checkpoint <file> --json
```

### batch-resume (bresume)

Resume batch with reconciliation. Checks worker, baseline, worktree. Blocks on mismatch.

```bash
python3 scripts/vibe_batch_runner.py --resume [--checkpoint <file>] [--json] [--compact]
python3 scripts/vibe_command_router.py bresume --checkpoint <file> --json
```

### batch-cancel (bcancel)

Cancel batch — only before mutation. Completed WOs preserved. Generates operator report.

```bash
python3 scripts/vibe_batch_runner.py --cancel [--checkpoint <file>] [--json] [--compact]
python3 scripts/vibe_command_router.py bcancel --checkpoint <file> --json
```

### batch-abort (babort)

Abort batch — immediate stop, no destructive cleanup. Generates operator report.

```bash
python3 scripts/vibe_batch_runner.py --abort [--checkpoint <file>] [--json] [--compact]
python3 scripts/vibe_command_router.py babort --checkpoint <file> --json
```

### worker-resilience v1.1.0 additions

```bash
python3 scripts/vibe_worker_resilience.py --pause <file> [--json]
python3 scripts/vibe_worker_resilience.py --reconcile <file> [--json]
```

### batch-runner v1.5.0 report fields

Enhanced batch report includes:
- `work_order_count`, `completed_count`, `stopped_count`
- `last_successful_baseline`, `final_baseline`
- `stop_reason`, `per_wo_prs`, `per_wo_changed_paths`
- `checkpoint_status`, `resume_status`
- `pause_resume_supported`, `cancel_abort_supported`

### batch-runner v1.6.0 — Fast Validation Mode

```bash
python3 scripts/vibe_batch_runner.py --batch plan.json --validation-mode fast --json
python3 scripts/vibe_batch_runner.py --batch plan.json --validation-mode full --json
python3 scripts/vibe_batch_runner.py --status --json  # shows validation_modes, quick_checks
```

**Validation modes:** full, fast, final-only (default: auto-detect)

**Quick checks (per-WO in fast mode):**
- git_status_clean, changed_paths_allowlist, forbidden_paths
- wrapper_merge_result, baseline_refresh, pr_changed_paths, token_redaction_scan

**Output fields:** validation_mode, per_wo_quick_checks, deferred_checks, final_full_validation_required, final_full_validation_result

**Safety rule:** Quick checks fail → stop batch. Final full validation fail → BLOCK, no freeze.

### batch-runner v1.7.0 — External Repo Policy & Approval

```bash
# Check external repo policy (dry-run)
python3 scripts/vibe_batch_runner.py --external-policy --ext-repo org/repo --ext-operation push --json
python3 scripts/vibe_batch_runner.py --external-policy --ext-repo org/repo --ext-operation fetch --json

# Manage approvals
python3 scripts/vibe_batch_runner.py --external-approval --approval-action create --approval-repo org/repo --approval-branch main --approval-operation push --approval-base-sha abc123 --json
python3 scripts/vibe_batch_runner.py --external-approval --approval-action approve --approval-id <id> --json
python3 scripts/vibe_batch_runner.py --external-approval --approval-action expire --approval-id <id> --json
python3 scripts/vibe_batch_runner.py --external-approval --approval-action list --json
python3 scripts/vibe_batch_runner.py --external-approval --approval-action show --approval-id <id> --json
```

**External policy fields:** repo_trust_level, operation_type, requires_approval, approved, would_read_token, would_push, blockers, warnings

**Approval bindings:** repo, branch, operation, base_sha, changed_paths, patch_sha256, expires_at (TTL)

**Status fields:** external_policy_supported, external_approval_supported, external_read_ops, external_write_ops, repo_trust_levels, default_trust_level

**Safety:** Read-only external ops → no token. Write external ops → BLOCK without approval. Approved → dry-run only (V1.8).

### batch-runner v1.8.0 — External Authorized Push Preflight

```bash
# Run preflight check (validates approval + token file metadata)
python3 scripts/vibe_batch_runner.py --ext-push-preflight --approval-id <id> --json
```

**Preflight checks:** approval_load, approval_status, approval_expiry, write_operation, forbidden_paths, token_file

**Output fields:** preflight_passed, checks, blockers, warnings, approval (repo/branch/operation/base_sha/changed_paths/patch_sha256/expires_at), token_file_metadata (exists/mode/size), token_content_read (always false)

**Status fields:** ext_push_preflight_supported, token_file_path

**Safety:** Token content NEVER read during preflight. Token NEVER output. External canary requires user-specified external repo (NOT self repo).

### External Authorized Push Workflow

```
1. User provides external test repo
2. Create approval: --external-approval --approval-action create --approval-repo <ext-repo> ...
3. Human approves: --external-approval --approval-action approve --approval-id <id>
4. Preflight: --ext-push-preflight --approval-id <id>
5. Push via privileged wrapper (outside batch-runner)
6. Verify: fetch remote, check branch + commit
7. Evidence: run-report with all artifacts
```
