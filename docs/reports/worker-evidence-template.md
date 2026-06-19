# Worker Job Evidence Template

## Required Fields

| Field           | Type   | Description                             |
|-----------------|--------|-----------------------------------------|
| job_id          | string | Unique identifier for the job           |
| worker          | string | Executor node that ran the job          |
| task_type       | string | e.g. linux-worker, opencode-implement   |
| planned_model   | string | Model intended for this job             |
| actual_model    | string | Model that actually executed            |
| provider        | string | API provider used                       |
| call_count      | int    | Number of LLM API calls made            |
| token_usage     | object | Input / output tokens consumed          |
| duration        | float  | Wall-clock time (seconds) from claim to completion |
| changed_paths   | list   | Files modified during the job           |
| test_result     | string | Pass/fail with summary                  |
| review_verdict  | string | approved / needs_changes / blocked      |
| fallback_used   | bool   | Whether model fallback was triggered    |

## Evidence Bundle

Every job must produce the following evidence bundle:

| Artifact         | Format | Description                |
|------------------|--------|----------------------------|
| Job manifest     | JSON   | Full job specification     |
| Git diff         | patch  | All changes made           |
| Test output log  | text   | Raw test results           |
| Review notes     | text   | Reviewer observations      |

## Quality Gates

Before marking a job complete, verify all of the following:

| Gate                        | Check                                              |
|-----------------------------|----------------------------------------------------|
| Tests pass                  | All tests must pass before completion              |
| No secrets in diff          | Scan diffs for credentials, tokens, keys           |
| No runtime changes          | No runtime code changed without explicit approval  |
| Independent review          | Reviewer must be a different worker than implementer |
