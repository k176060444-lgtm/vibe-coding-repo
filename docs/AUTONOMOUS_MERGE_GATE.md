# Autonomous Merge Gate v1

## Overview

The Autonomous Merge Gate is a pre-merge verification tool for vibedev Hermes. It checks whether a Pull Request meets all criteria for autonomous merge, ensuring auditability and safety.

## Purpose

- Enforce consistent merge criteria across all Work Orders
- Prevent accidental merges of unverified changes
- Maintain audit trail for all merge decisions
- Protect locked jobs from unauthorized changes

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

## CLI Usage

```bash
# Basic usage
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

## Output Format

### Text Mode

```
========================================
  Autonomous Merge Gate v1
========================================
  Result: ✅ ALLOW MERGE
----------------------------------------
  PR Info:
    Number: 6
    Title: Queue / Job Registry Summary v2
    State: OPEN
    ...
========================================
```

### JSON Mode

```json
{
  "allow_merge": true,
  "blockers": [],
  "warnings": ["No checks found"],
  "pr": {
    "number": 6,
    "title": "...",
    "state": "OPEN",
    ...
  },
  "job": {
    "job_id": "wo-code-job-registry-summary-001",
    "job_status": "review_passed",
    "audit_status": "clean",
    "push_allowed": false
  },
  "checks": {
    "status": "no_checks_found",
    "count": 0
  }
}
```

## Prohibited Actions

The merge gate is **read-only**. It must NOT:

- ❌ Modify repository files
- ❌ Execute merge/push/delete operations
- ❌ Read or expose secrets/tokens
- ❌ Modify Provider/secrets/CI/workflow/admin
- ❌ Deploy/tag/release
- ❌ Force/reset/delete
- ❌ Release audit_tainted locks

## Failure Handling

When `allow_merge = false`:

1. Review all blockers in the output
2. Fix the issues that caused the blockers
3. Re-run the gate after fixes
4. Do NOT proceed with merge until all blockers are resolved

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
- All operations are read-only

## See Also

- `scripts/vibe_repo_status.py` - Job registry and queue summary
- `docs/WORKFLOW.md` - Overall workflow documentation
