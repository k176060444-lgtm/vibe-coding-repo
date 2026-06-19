# Active-Active Batch Execution Summary

## Pool Configuration

- Two Debian executor nodes in active-active mode
- Each node: weight=100, max_parallel_jobs=1
- Total pool capacity: 2 concurrent jobs
- Both nodes can serve as implementer or reviewer

## Role Separation Rule

- For any single job, the implementer and reviewer must be different workers
- A worker cannot review its own changes
- Cross-node review ensures independence

## Batch Execution Flow

1. Submit batch of N jobs to queue
2. Scheduler assigns jobs based on capability and capacity
3. Workers claim and execute jobs in parallel (up to 2)
4. Results collected and evidence bundles generated
5. Review phase (different worker reviews each job)
6. Final verification and merge

## Dashboard Metrics

- Total jobs in batch: 4
- Jobs on 5bao: 2
- Jobs on 9bao: 2
- Models attempted: deepseek-v4-flash (2 jobs), MiniMax-M3 (2 jobs)
- Models actually executed: deepseek-v4-flash (4 executions)
- Fallback events: 2 (MiniMax-M3 -> deepseek-v4-flash, model_behavior_fallback)
- Fallback type: manual, after verifying MiniMax-M3 produced thinking-only output
- Average duration: ~14s per job
- All tests passed: yes

## Failure Handling

- If a worker fails mid-job, the claim expires and job returns to queue
- Heartbeat mechanism detects worker liveness
- Stale claims are automatically recovered
