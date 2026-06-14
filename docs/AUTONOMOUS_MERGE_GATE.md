# Autonomous Merge Gate v1

## Overview

The Autonomous Merge Gate is a pre-merge verification system for vibedev Hermes. It consists of two components:

1. **`scripts/vibe_merge_gate.py`** - Gate verification (read-only checks)
2. **`scripts/vibe_autonomous_merge.py`** - Controlled merge wrapper (executes merge only when gate passes)

## Purpose

- Enforce consistent merge criteria across all Work Orders
- Prevent accidental merges of unverified changes
- Maintain audit trail for all merge decisions
- Protect locked jobs from unauthorized changes
- **Prevent bare `gh pr merge` calls** - all merges must go through the wrapper

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Hermes Agent                              │
│                        │                                     │
│                        ▼                                     │
│            vibe_autonomous_merge.py                          │
│                        │                                     │
│                        ▼                                     │
│                vibe_merge_gate.py                            │
│                        │                                     │
│         ┌──────────────┼──────────────┐                      │
│         ▼              ▼              ▼                      │
│    PR Checks    Job Registry    Locked Job                   │
│         │              │              │                      │
│         ▼              ▼              ▼                      │
│    gh pr view    jobs/*.json    wo-code-repo-status-001      │
│    gh pr diff                                                        │
│    git ls-remote                                                     │
└─────────────────────────────────────────────────────────────┘
```

## Gate Checks

### PR Checks

| Check | Description | Blocker? |
|-------|-------------|----------|
| PR Exists | PR is accessible via gh CLI | Yes |
| PR Open | PR state must be OPEN | Yes |
| Base Branch | Base must be `main` | Yes |
| Main SHA | Current main matches expected base SHA | Yes |
| Head SHA | PR head matches expected head SHA | Yes |
| Changed Files | All changed files in allowed-path list | Yes |
| Mergeable | PR mergeable state is CLEAN/MERGEABLE | Yes |
| Checks | No failed checks (no_checks_found = warning only) | No |

### Job Registry Checks

| Check | Description | Blocker? |
|-------|-------------|----------|
| Job Exists | Job ID found in jobs directory | Yes |
| Job Status | job_status = review_passed | Yes |
| Audit Status | audit_status = clean | Yes |
| Not Audit Tainted | Job is not audit_tainted | Yes |

### Locked Job Protection

| Check | Description | Blocker? |
|-------|-------------|----------|
| wo-code-repo-status-001 | audit_status = audit_tainted | Yes |
| wo-code-repo-status-001 | push_allowed = false | Yes |

## IMPORTANT: No Bare gh pr merge

**⚠️ PROHIBITED: Direct `gh pr merge` calls are NOT allowed.**

All merges MUST go through `scripts/vibe_autonomous_merge.py`. This ensures:

1. Gate verification is always performed
2. Merge decisions are auditable
3. Locked jobs are protected
4. Merge method is enforced (merge commit only)

**Failure to use the wrapper may result in:**
- Merge of unverified changes
- Audit trail gaps
- Locked job violations
- Inconsistent merge history

## CLI Usage

### Gate Check Only (vibe_merge_gate.py)

```bash
# Basic gate check
python scripts/vibe_merge_gate.py \
  --repo k176060444-lgtm/vibe-coding-repo \
  --pr 6 \
  --expected-base-sha f0366f8b0bfad282eaa4f8b645cc03ef47407e3a \
  --expected-head-sha 14bab123d8f1a696b1888287c4b15d65ee99e0b3 \
  --allowed-path scripts/vibe_repo_status.py

# With job registry check
python scripts/vibe_merge_gate.py \
  --repo k176060444-lgtm/vibe-coding-repo \
  --pr 6 \
  --expected-base-sha f0366f8b0bfad282eaa4f8b645cc03ef47407e3a \
  --expected-head-sha 14bab123d8f1a696b1888287c4b15d65ee99e0b3 \
  --allowed-path scripts/vibe_repo_status.py \
  --job-id wo-code-job-registry-summary-001

# JSON output
python scripts/vibe_merge_gate.py \
  --repo k176060444-lgtm/vibe-coding-repo \
  --pr 6 \
  --expected-base-sha f0366f8b0bfad282eaa4f8b645cc03ef47407e3a \
  --expected-head-sha 14bab123d8f1a696b1888287c4b15d65ee99e0b3 \
  --allowed-path scripts/vibe_repo_status.py \
  --json
```

### Autonomous Merge Wrapper (vibe_autonomous_merge.py)

```bash
# Dry-run mode (check only, no merge)
python scripts/vibe_autonomous_merge.py \
  --repo k176060444-lgtm/vibe-coding-repo \
  --pr 7 \
  --expected-base-sha bbbd5caebc41a98f9028a3d3d9c13b67e1b38b0f \
  --expected-head-sha bf65005976922e9c1b10a2b6c40570d21791f67f \
  --allowed-path scripts/vibe_merge_gate.py \
  --allowed-path docs/AUTONOMOUS_MERGE_GATE.md \
  --job-id wo-code-autonomous-merge-gate-001 \
  --dry-run

# Execute merge (only when gate passes)
python scripts/vibe_autonomous_merge.py \
  --repo k176060444-lgtm/vibe-coding-repo \
  --pr 7 \
  --expected-base-sha bbbd5caebc41a98f9028a3d3d9c13b67e1b38b0f \
  --expected-head-sha bf65005976922e9c1b10a2b6c40570d21791f67f \
  --allowed-path scripts/vibe_merge_gate.py \
  --allowed-path docs/AUTONOMOUS_MERGE_GATE.md \
  --job-id wo-code-autonomous-merge-gate-001

# JSON output with dry-run
python scripts/vibe_autonomous_merge.py \
  --repo k176060444-lgtm/vibe-coding-repo \
  --pr 7 \
  --expected-base-sha bbbd5caebc41a98f9028a3d3d9c13b67e1b38b0f \
  --expected-head-sha bf65005976922e9c1b10a2b6c40570d21791f67f \
  --allowed-path scripts/vibe_merge_gate.py \
  --allowed-path docs/AUTONOMOUS_MERGE_GATE.md \
  --json \
  --dry-run
```

## Output Format

### Text Mode

```
========================================
  Autonomous Merge Wrapper
========================================
  Mode: DRY RUN
  Result: ✅ ALLOW MERGE (dry-run)
----------------------------------------
  PR Info:
    Number: 7
    Title: Autonomous Merge Gate v1
    State: OPEN
    URL: https://github.com/k176060444-lgtm/vibe-coding-repo/pull/7
----------------------------------------
  Merge Command: gh pr merge 7 -R k176060444-lgtm/vibe-coding-repo --merge
========================================
```

### JSON Mode

```json
{
  "allow_merge": true,
  "dry_run": true,
  "merge_executed": false,
  "blockers": [],
  "warnings": ["No checks found"],
  "pr": {
    "number": 7,
    "title": "Autonomous Merge Gate v1",
    "state": "OPEN",
    ...
  },
  "job": {
    "job_id": "wo-code-autonomous-merge-gate-001",
    "job_status": "review_passed",
    "audit_status": "clean",
    "push_allowed": false
  },
  "changed_paths": [
    "scripts/vibe_merge_gate.py",
    "docs/AUTONOMOUS_MERGE_GATE.md"
  ],
  "checks": {
    "status": "no_checks_found",
    "count": 0
  },
  "merge_command_summary": "gh pr merge 7 -R k176060444-lgtm/vibe-coding-repo --merge"
}
```

## Prohibited Actions

The merge system is **controlled**. It must NOT:

- ❌ Execute bare `gh pr merge` without gate verification
- ❌ Modify repository files
- ❌ Read or expose secrets/tokens
- ❌ Modify Provider/secrets/CI/workflow/admin
- ❌ Deploy/tag/release
- ❌ Force/reset/delete
- ❌ Release audit_tainted locks
- ❌ Squash or rebase (merge commit only)

## Failure Handling

When `allow_merge = false`:

1. Review all blockers in the output
2. Fix the issues that caused the blockers
3. Re-run the wrapper after fixes
4. Do NOT proceed with merge until all blockers are resolved

When merge execution fails:

1. Check the error message in blockers
2. Verify PR state and permissions
3. Re-run the wrapper after fixing the issue

Warnings do not block merge but should be reviewed.

## Post-Merge Freeze

After a successful merge, always perform:

1. Fetch origin and verify new main SHA
2. Verify merge commit parents
3. Verify changed_paths in merge diff
4. Run post-merge tests on clean worktree
5. Verify locked job status unchanged
6. Generate freeze report with new baseline

## Implementation Notes

- Standard library only (no new dependencies)
- Import-safe (no IO on import)
- Uses gh CLI for GitHub API access
- Uses git ls-remote for SHA verification
- Merge method: merge commit only (no squash/rebase)
- All gate checks are read-only

## See Also

- `scripts/vibe_merge_gate.py` - Gate verification (read-only)
- `scripts/vibe_repo_status.py` - Job registry and queue summary
- `docs/WORKFLOW.md` - Overall workflow documentation
