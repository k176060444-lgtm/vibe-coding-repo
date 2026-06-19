# V1.19.0 Operational Pilot Batch Report

Generated: 2026-06-19
Base: 4f87eaed71d325137eb3c6c18782b75522463d91 (public main)

## Batch Summary

| Metric | Value |
|--------|-------|
| Total jobs | 4 |
| Jobs on 5bao | 2 (job-1, job-3) |
| Jobs on 9bao | 2 (job-2, job-4) |
| Models used | deepseek-v4-flash (3 jobs), MiniMax-M3 attempted (2 jobs) |
| Fallback events | 1 (MiniMax-M3 -> deepseek-v4-flash on job-4) |
| Fallback reason | MiniMax-M3 produced thinking only, no file output |
| All files created | Yes |
| All files ASCII-only | Yes |
| Security scan | PASS (no secrets, no IPs, no paths) |

## Job Details

| Field | job-1 | job-2 | job-3 | job-4 |
|-------|-------|-------|-------|-------|
| job_id | pilot-v1190-job1 | pilot-v1190-job2 | pilot-v1190-job3 | pilot-v1190-job4 |
| role | implementer | implementer | implementer | implementer |
| worker | 5bao | 9bao | 5bao | 9bao |
| planned_model | deepseek-v4-flash | MiniMax-M3 | deepseek-v4-flash | MiniMax-M3 |
| actual_model | deepseek-v4-flash | deepseek-v4-flash | deepseek-v4-flash | deepseek-v4-flash |
| provider | deepseek-plan | deepseek-plan | deepseek-plan | deepseek-plan |
| call_count | 1 | 1 | 2 (1 bash invalid + 1 write) | 2 (1 bash invalid + 1 write) |
| token_usage | N/A (no stats cmd) | N/A | N/A | N/A |
| duration | ~11s | ~19s | ~16s | ~11s |
| changed_paths | queue-scheduling-overview.md | worker-evidence-template.md | model-fallback-evidence-fixture.md | active-active-batch-summary.md |
| tests | ASCII-only PASS | ASCII-only PASS | ASCII-only PASS | ASCII-only PASS |
| review_verdict | pending | pending | pending | pending |
| fallback_used | false | true (MiniMax-M3 -> deepseek) | false | true (MiniMax-M3 -> deepseek) |
| final_status | SUCCEEDED | SUCCEEDED | SUCCEEDED | SUCCEEDED |

## Model Fallback Evidence

### MiniMax-M3 Failure Pattern

MiniMax-M3 was attempted for jobs 2 and 4. In both cases:
- The model produced internal thinking output but did not execute any file write tool
- The process exited with code 0 (no error) but no file was created
- This is a model behavior issue, not a provider/API error

### Fallback Resolution
- Fallback model: deepseek-plan/deepseek-v4-flash
- Fallback triggered: manually after verifying file absence
- Fallback logged with reason: "MiniMax-M3_produced_thinking_only_no_file_output"
- Both fallback executions succeeded on first attempt

### Classification
- This is NOT a rate-limit or quota fallback (no HTTP 429/503)
- This is NOT a timeout fallback
- This IS a model capability/behavior fallback
- The model produced valid thinking but failed to invoke the write tool

## Files Generated

| File | Lines | Source | SHA256 |
|------|-------|--------|--------|
| docs/reports/queue-scheduling-overview.md | 59 | job-1 (5bao, deepseek) | computed_at_commit |
| docs/reports/worker-evidence-template.md | 41 | job-2 (9bao, deepseek-fallback) | computed_at_commit |
| docs/reports/model-fallback-evidence-fixture.md | 57 | job-3 (5bao, deepseek) | computed_at_commit |
| docs/reports/active-active-batch-summary.md | 39 | job-4 (9bao, deepseek-fallback) | computed_at_commit |

## Review Status

All 4 files are pending independent review. Since this is a pilot batch with docs-only changes, review can be performed as a single pass:
- ASCII-only verification: PASS
- Secret scan: PASS
- Internal IP scan: PASS
- Windows path scan: PASS
- Content quality: concise, structured, within line limits

## Observations

1. **deepseek-v4-flash** is reliable for file creation tasks on both nodes
2. **MiniMax-M3** has a behavioral issue where it thinks but does not execute tool calls for this workload
3. **SSH dispatch** to both workers works correctly
4. **Worktree isolation** provides clean per-job environments
5. **Average job duration**: ~14s including SSH overhead and OpenCode startup
