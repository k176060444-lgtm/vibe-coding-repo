# Feature Work Order Template

**Template Version**: 1.0
**Last Updated**: 2026-06-15
**Purpose**: Convert user requirements into executable Work Orders for the VibeDev autonomous pipeline.

---

## Work Order Structure

```yaml
# work-order.json
work_order_id: wo-{type}-{name}-{seq}
title: "One-line description"
description: |
  Multi-line requirement description.
  What the user wants and why.
priority: low | medium | high | critical
scope:
  allowed_paths:
    - "scripts/new_script.py"
    - "docs/NEW_DOC.md"
  forbidden_paths:
    - ".github/"
    - "secrets/"
    - "*token*"
    - "*secret*"
acceptance_criteria:
  - "Criterion 1: specific, testable"
  - "Criterion 2: specific, testable"
  - "Criterion 3: specific, testable"
review_criteria:
  - "Code quality: standard library only, no new deps"
  - "Import safety: no IO on import"
  - "CLI: --help works, --json if applicable"
  - "Changed paths: strictly within scope"
model_policy:
  implementer:
    primary: "deepseek-plan/deepseek-v4-flash"
    fallback_models: ["xiaomi-plan/mimo-v2.5"]
  reviewer:
    primary: "xiaomi-plan/mimo-v2.5-pro"
    fallback_models: []
stop_conditions:
  - "origin/main SHA changes during execution"
  - "Changed paths exceed declared scope"
  - "py_compile fails"
  - "Smoke suite regression"
  - "Wrapper gate returns allow_merge=false"
  - "audit_tainted lock status changes"
```

---

## Execution Pipeline

### Phase 1: Prepare
1. Verify `origin/main` matches expected `base_sha`
2. Create isolated worktree from `base_sha`
3. Create temporary branch `vibedev/{work_order_id}`
4. Record `base_sha` in job metadata

### Phase 2: Implement
1. Make changes strictly within `allowed_paths`
2. Follow standard library constraint
3. Ensure import safety (no IO on import)
4. Add `--help` and `--json` flags where applicable
5. Run `py_compile` on all modified/created Python files

### Phase 3: Test
1. Run smoke suite: `python scripts/test_toolchain_smoke.py`
2. Run specific tests for changed functionality
3. Verify `--help` output
4. Verify `--json` output is valid JSON
5. Verify no regression in existing tests

### Phase 4: Commit
1. `git add` only files within `allowed_paths`
2. Commit with descriptive message including work_order_id
3. Record `result_sha`

### Phase 5: Push + PR
1. Push branch to origin
2. Create PR with title including work_order_id
3. PR body must include: summary, scope, verification results

### Phase 6: Review
1. Verify changed_paths strictly within scope
2. Run `py_compile` on all Python files
3. Verify smoke suite passes
4. Check for security concerns (secrets, tokens, credentials)
5. Record review verdict: pass | fail

### Phase 7: Wrapper Gate
1. Run dry-run: `vibe_autonomous_merge.py ... --dry-run`
2. Verify `allow_merge=true`
3. Run actual merge: `vibe_autonomous_merge.py ...`
4. Verify `merge_executed=true`

### Phase 8: Post-Merge Freeze
1. Fetch latest `origin/main`
2. Verify new `origin/main` includes the merge commit
3. Update local `main` ref
4. Verify audit_tainted lock unchanged
5. Run smoke suite on new main
6. Clean up worktree and temporary branch

---

## Failure Handling

### At Any Phase
- **STOP** immediately on blocker
- Preserve worktree, diff, logs, job.json
- Report blocker with evidence
- Wait for human decision

### Recovery Options
1. **Fix and retry**: Address the issue in the same worktree
2. **Abort**: Reset worktree to `base_sha`, delete branch
3. **Escalate**: Generate escalation package for human/GPT review

### Escalation Package Fields
- `objective`: What we were trying to achieve
- `problem`: Specific issue encountered
- `work_order_id`: Current work order identifier
- `base_sha`: Git base commit
- `result_sha`: Git result commit (if exists)
- `worktree`: Absolute path to worktree
- `status`: Current phase when blocked
- `reproduction`: Steps to reproduce
- `logs`: Relevant log excerpts
- `diff`: Full or relevant diff excerpt
- `tried`: What has already been attempted
- `excluded`: What has been ruled out

---

## Example: Feature Work Order

### User Requirement
"Add a `--summary` flag to the operator snapshot that shows a one-line status."

### Generated Work Order

```yaml
work_order_id: wo-code-snapshot-summary-001
title: "Add --summary flag to Operator Snapshot"
description: |
  User wants a one-line summary output from the operator snapshot.
  Example: "queue_clean | 26 jobs | 18 merged | 0 actions"
priority: low
scope:
  allowed_paths:
    - "scripts/vibe_operator_snapshot.py"
    - "docs/COMMANDS.md"
  forbidden_paths:
    - ".github/"
    - "secrets/"
acceptance_criteria:
  - "--summary flag exists and shows one-line output"
  - "--summary works with --json (included in JSON)"
  - "py_compile passes"
  - "--help shows --summary"
  - "Smoke suite still passes (11/11)"
review_criteria:
  - "Standard library only"
  - "No new dependencies"
  - "Import safe"
```

---

## Naming Convention

| Type Prefix | Description | Example |
|-------------|-------------|---------|
| `wo-code-` | Code change (script, tool) | `wo-code-snapshot-summary-001` |
| `wo-doc-` | Documentation only | `wo-doc-workflow-update-001` |
| `wo-maint-` | Maintenance (cleanup, triage) | `wo-maint-archive-old-jobs-001` |
| `wo-test-` | Test-only change | `wo-test-e2e-dispatch-001` |
| `wo-fix-` | Bug fix | `wo-fix-advisor-crash-001` |

---

## Integration with QQ/Hermes

### From User Message to Work Order

1. User sends requirement via QQ
2. Hermes parses requirement into structured format
3. Hermes generates work-order.json using this template
4. Hermes shows proposed Work Order to user for approval
5. On approval, Hermes executes the pipeline
6. Hermes reports results via QQ

### QQ Command Flow

```
User: "Add a --summary flag to snapshot that shows one-line status"
Hermes: [Generates Work Order]
Hermes: "Proposed: wo-code-snapshot-summary-001
  Scope: scripts/vibe_operator_snapshot.py, docs/COMMANDS.md
  Acceptance: --summary flag, py_compile, smoke suite
  Approve? [Y/n]"
User: "Y"
Hermes: [Executes pipeline]
Hermes: "✅ Complete. PR #33 merged. main=abc123..."
```
