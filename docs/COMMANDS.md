# Agent Command Cheatsheet

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

