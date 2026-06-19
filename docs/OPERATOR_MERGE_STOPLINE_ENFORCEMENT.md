# V1.20.10 Operator Merge Stopline Enforcement

Version: V1.20.10
Status: ACTIVE
Enforced by: operator_merge_approval_gate.py, vibe_merge_gate.py

## Overview

Any PR merge operation must have a valid, auditable Operator merge approval record.
Without this record, vibe_merge_gate must fail-closed (allow_merge=false).

## Approval Record Format

```json
{
    "pr_number": 174,
    "approval_status": "APPROVED",
    "approved_by": "operator_kk",
    "approved_at": "2026-06-19T16:00:00Z",
    "approved_head_sha": "8dfcedf9...",
    "approved_base_sha": "b3a59f92...",
    "merge_method_allowed": "merge",
    "approval_scope": "merge"
}
```

## Required Fields

| Field | Description |
|-------|-------------|
| pr_number | PR number being approved |
| approval_status | Must be "APPROVED" |
| approved_by | Operator identifier |
| approved_at | ISO timestamp (expires after 72h) |
| approved_head_sha | Head SHA at approval time |
| approved_base_sha | Base SHA at approval time |
| merge_method_allowed | "merge", "squash", "rebase", or "any" |
| approval_scope | "merge", "full", or "operator_merge_approval" |

## Fail-Closed Rules

allow_merge=true requires ALL of:
1. base merge blockers empty (existing checks pass)
2. model_ledger_gate.checked=true AND result="PASS"
3. operator_merge_approval.checked=true AND result="APPROVED"

BLOCKED states:
- No --approval-file provided
- Approval file not found / not valid JSON
- Missing required fields
- approval_status not "APPROVED"
- Expired approval (>72h)
- approval_scope does not include merge
- Head/base SHA mismatch
- PR number mismatch
- merge_method_allowed invalid

## Usage

```bash
# Self-check
python scripts/operator_merge_approval_gate.py --self-check

# Validate approval
python scripts/operator_merge_approval_gate.py --approval-file approval.json --pr 174 --head SHA --base SHA

# In merge gate
python scripts/vibe_merge_gate.py --repo owner/repo --pr 174 \
    --expected-base-sha SHA --expected-head-sha SHA \
    --report-file report.json --approval-file approval.json
```

## Safety

- workflow_code_changed=true
- runtime_code_changed=false
- No live model calls
- No credential/secret access
