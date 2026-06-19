# VibeDev Queue Scheduling Overview

## Queue Architecture

Jobs are submitted to a durable queue backed by **ClaimStore**. Each job record contains:

| Field            | Description                           |
|------------------|---------------------------------------|
| `job_id`         | Unique identifier                     |
| `task_type`      | Type of work (e.g. scan, build)       |
| `required_tools` | Tool dependencies (e.g. ripgrep, curl)|
| `priority`       | Scheduling priority (higher = sooner) |
| `status`         | Current job state                     |

## Capability Selection

The scheduler matches `required_tools` against registered worker capabilities. A worker is only eligible if it has every tool a job requires.

Example: a job requiring `ripgrep` is routed exclusively to workers where `ripgrep` is installed.

## Active-Active Pool

Two Debian executors form a symmetric pool:

| Worker   | Weight | Max Parallel Jobs |
|----------|--------|-------------------|
| 5bao     | 100    | 1                 |
| 9bao     | 100    | 1                 |

Total system capacity: **2 concurrent jobs**.

## Claim Protocol

Claiming uses an atomic file-based lock on the job record in ClaimStore. The first worker to acquire the lock wins; all others back off and retry.

1. Read job record
2. Attempt atomic compare-and-swap (`status: QUEUED -> CLAIMED`)
3. On success, begin execution
4. On conflict, skip to next available job

## Job Lifecycle

```
                   +---> SUCCEEDED
                   |
     QUEUED ---> CLAIMED ---> RUNNING ---+---> FAILED
                   |                     |
                   |                     +---> BLOCKED
                   |                     |
                   |                     +---> CANCELLED
                   |                     |
                   |                     +---> RECOVERY_REQUIRED
                   |
                   +---> CANCELLED (pre-emption)
```

## Capacity Release

On job completion (any terminal state), the worker releases its capacity slot and becomes eligible to claim the next QUEUED job. Capacity is released synchronously as part of the job finalisation routine.
