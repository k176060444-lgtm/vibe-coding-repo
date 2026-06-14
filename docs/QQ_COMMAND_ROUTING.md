# QQ Command Routing Specification

## Unified CLI Entry Point

All commands are accessible via the command router. Short aliases are supported for faster typing:

| QQ Alias | Full Command | Example |
|----------|-------------|---------|
| `/s` | `/snapshot` | `/s --compact` |
| `/a` | `/advisor` | `/a --json` |
| `/d` | `/dispatch` | `/d --compact` |
| `/b` | `/batch-plan` | `/b --json --limit 3` |
| `/h` | `/health` | `/h` |
| `/sm` | `/smoke` | `/sm` |

Typo correction is enabled: misspelled commands get a "Did you mean?" suggestion.

```bash
python3 scripts/vibe_command_router.py <command> [options]
```

Commands:
- `snapshot` - Operator Snapshot
- `advisor` - Queue Advisor
- `dispatch` - Dispatch Planner
- `batch-plan` - Batch Queue Plan
- `health` - Health Check
- `help` - Show help

# QQ Command Routing Specification (Legacy)

Defines command entry points for QQ / Hermes orchestrator. Each command maps to a specific script or workflow step.

## Command Overview

| Command | Intent | Script | Risk Level |
|---------|--------|--------|------------|
| `/snapshot` | Unified status snapshot | `vibe_operator_snapshot.py` | Read-only |
| `/queue` | Queue analysis & lifecycle | `vibe_queue_advisor.py` | Read-only |
| `/plan` | Dispatch planning | `vibe_dispatch_planner.py` | Read-only |
| `/next` | Next action recommendation | `vibe_dispatch_planner.py --compact` | Read-only |
| `/workorder` | Work Order management | Manual + scripts | Medium |
| `/review` | Job review status | `vibe_repo_status.py` | Read-only |
| `/merge` | Wrapper merge execution | `vibe_autonomous_merge.py` | High |
| `/freeze` | Post-merge freeze | Manual verification | Read-only |
| `/batch` | Batch queue planning | `vibe_batch_plan.py` | Read-only |

## Command Specifications

### `/snapshot`

**Intent**: Get unified status snapshot for QQ/Hermes orchestrator.

**Parameters**:
- `--compact` (default): ~16 lines, human-readable
- `--json`: Full JSON output
- `--include-tainted`: Include audit_tainted jobs
- `--include-merged`: Include merged jobs

**Permission Boundary**: Read-only, no modifications allowed.

**Output Format**:
```
════════════════════════════════════════
  📊 Operator Snapshot
════════════════════════════════════════
  Main:     <sha>
  Remote:   <sha>
  Sync:     YES/NO
  Jobs:     <count>
  Merged:   <count>
  Blocked:  <count> (<hidden> hidden)
  Actions:  <count>
  Warnings: <count>
  Lifecycle: <states>
────────────────────────────────────────
  ➡ NEXT: <recommendation>
════════════════════════════════════════
```

**Prohibited Behaviors**:
- No file modifications
- No secret/token exposure
- No push/merge/deploy operations

---

### `/queue`

**Intent**: Analyze job queue with lifecycle classification.

**Parameters**:
- `--json`: JSON output
- `--include-tainted`: Include tainted jobs
- `--include-merged`: Include merged jobs
- `--limit N`: Limit output items

**Permission Boundary**: Read-only.

**Output Format**: JSON with `total_jobs`, `lifecycle_summary`, `action_items`, `blocked_jobs`, `merged_jobs`, `superseded_jobs`, `informational_jobs`, `unresolved_jobs`, `summary`.

**Prohibited Behaviors**:
- No job creation/modification
- No record deletion

---

### `/plan`

**Intent**: Generate next Work Order suggestions based on current state.

**Parameters**:
- `--json`: JSON output
- `--compact`: Compact text output
- `--jobs-dir`: Custom jobs directory

**Permission Boundary**: Read-only.

**Output Format**: JSON with `current_state`, `suggestions`, `recommended_action`, `suggestion_count`.

**Suggestion Priority Order**:
1. `critical`: tainted locks (manual resolution required)
2. `high`: investigation failures
3. `medium`: superseded conflicts, in-progress jobs
4. `low`: ready_for_merge
5. `info`: queue_clean, non-production informational

**Prohibited Behaviors**:
- No automatic Work Order creation
- No shell/git execution

---

### `/next`

**Intent**: Quick next action recommendation (compact format).

**Parameters**: None (uses defaults).

**Permission Boundary**: Read-only.

**Output Format**: Single line recommendation.

**Prohibited Behaviors**:
- Same as `/plan`

---

### `/workorder`

**Intent**: Work Order lifecycle management.

**Sub-commands**:
- `/workorder list`: List all jobs
- `/workorder show <id>`: Show job details
- `/workorder create <id>`: Create new Work Order (requires confirmation)
- `/workorder status <id>`: Show job status

**Permission Boundary**: 
- Read operations: always allowed
- Create operations: requires human confirmation
- Modify/delete: NEVER allowed (records are append-only)

**Output Format**: JSON or text based on `--json` flag.

**Prohibited Behaviors**:
- No record modification/deletion
- No audit_tainted lock release
- No automatic Work Order execution

---

### `/review`

**Intent**: Review job status and audit state.

**Parameters**:
- `<job_id>`: Specific job to review
- `--json`: JSON output
- `--status <status>`: Filter by status
- `--audit-status <status>`: Filter by audit status

**Permission Boundary**: Read-only.

**Output Format**: Job registry entry with status, audit_status, push_allowed, base_sha, result_sha, changed_paths.

**Prohibited Behaviors**:
- No status modification
- No audit override

---

### `/merge`

**Intent**: Execute wrapper merge for a PR.

**Parameters**:
- `--pr <N>`: PR number
- `--expected-base-sha <sha>`: Expected main SHA
- `--expected-head-sha <sha>`: Expected head SHA
- `--allowed-path <path>`: Allowed changed paths (repeatable)
- `--job-id <id>`: Job ID
- `--dry-run`: Dry-run mode
- `--json`: JSON output

**Permission Boundary**: HIGH RISK - requires human approval for actual merge.

**Execution Flow**:
1. Gate check (vibe_merge_gate.py)
2. PR state validation
3. SHA consistency check
4. Changed paths validation
5. Merge execution (if not dry-run)

**Prohibited Behaviors**:
- No bare `gh pr merge`
- No merge without gate pass
- No merge with mismatched SHAs
- No merge with disallowed changed paths

---

### `/freeze`

**Intent**: Execute post-merge freeze verification.

**Steps**:
1. Fetch and verify new main
2. Check PR state (MERGED)
3. Verify changed paths
4. Compile and test on new main
5. Negative wrapper test
6. Verify wo-code-repo-status-001 lock

**Permission Boundary**: Read-only verification.

**Prohibited Behaviors**:
- No file modifications during freeze
- No lock release

---

### `/batch`

**Intent**: Generate batch queue plan for multiple Work Orders.

**Parameters**:
- `--jobs-dir`: Custom jobs directory
- `--json`: JSON output
- `--limit N`: Max Work Orders in plan

**Permission Boundary**: Read-only (plan generation only).

**Output Format**: JSON with `task_order`, `risk_level`, `allowed_paths`, `stop_conditions`, `requires_human_approval`, `expected_reports`.

**Prohibited Behaviors**:
- No automatic execution
- No shell/git operations
- No file modifications

---

## Global Constraints

### Always Allowed
- Read-only status checks
- JSON/text output generation
- Script compilation verification
- Import safety checks

### Never Allowed
- Secret/token exposure
- Direct push to main
- Bare `gh pr merge`
- Record deletion/modification
- audit_tainted lock release
- Deploy/tag/release without authorization
- File modifications outside declared scope

### Requires Human Approval
- Work Order creation
- Wrapper merge execution
- Remote branch deletion
- Worktree cleanup (except forced)

## Error Handling

| Error | Response |
|-------|----------|
| Script not found | Report error, suggest check path |
| JSON parse error | Report raw output, suggest `--json` flag |
| SHA mismatch | Report expected vs actual, block merge |
| Gate failure | Report blockers, suggest resolution |
| Permission denied | Report constraint violation, block action |

## Integration Points

### QQ Bot Gateway
- Commands received via QQ messages
- Responses sent back to QQ chat
- No direct gateway modification

### Hermes Agent
- Commands processed by vibedev profile
- Results reported to user
- No automatic Work Order execution

### Git/GitHub
- Read-only access for status checks
- Write access only through wrapper merge
- No direct git operations outside declared scope

## References

- `docs/COMMANDS.md`: Command cheatsheet
- `docs/WORKFLOW.md`: Workflow documentation
- `docs/AUTONOMOUS_MERGE_GATE.md`: Merge gate specification
- `scripts/vibe_operator_snapshot.py`: Operator Snapshot script
- `scripts/vibe_queue_advisor.py`: Queue Advisor script
- `scripts/vibe_dispatch_planner.py`: Dispatch Planner script
- `scripts/vibe_autonomous_merge.py`: Merge wrapper script
