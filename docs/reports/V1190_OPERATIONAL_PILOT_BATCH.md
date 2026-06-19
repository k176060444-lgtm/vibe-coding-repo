# V1.19.0 Operational Pilot Batch Report

Generated: 2026-06-19
Base: 4f87eaed71d325137eb3c6c18782b75522463d91 (public main)
Updated: 2026-06-19 (review blockers fix)

## Batch Summary

| Metric | Value |
|--------|-------|
| Total jobs | 4 |
| Jobs on 5bao | 2 (job-1, job-3) |
| Jobs on 9bao | 2 (job-2, job-4) |
| Models attempted | deepseek-v4-flash (2 jobs), MiniMax-M3 (2 jobs) |
| Models actually executed | deepseek-v4-flash (4 executions) |
| Fallback events | 2 (MiniMax-M3 -> deepseek-v4-flash) |
| Fallback type | model_behavior_fallback, manual after file absence verification |
| Fallback reason | MiniMax-M3 produced thinking only, no file output |
| All files created | Yes |
| All files ASCII-only | Yes |
| Security scan | PASS (no secrets, no IPs, no paths) |
| Hidden/bidi Unicode warning | NONE (verified on GitHub) |

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
| token_usage | unavailable (no stats cmd) | unavailable | unavailable | unavailable |
| duration | ~11s | ~19s | ~16s | ~11s |
| changed_paths | queue-scheduling-overview.md | worker-evidence-template.md | model-fallback-evidence-fixture.md | active-active-batch-summary.md |
| tests | ASCII-only PASS | ASCII-only PASS | ASCII-only PASS | ASCII-only PASS |
| review_verdict | APPROVED | APPROVED | APPROVED | APPROVED |
| fallback_used | false | true (MiniMax-M3 -> deepseek) | false | true (MiniMax-M3 -> deepseek) |
| final_status | SUCCEEDED | SUCCEEDED | SUCCEEDED | SUCCEEDED |

## Cross-Worker Review Evidence

| Job | Implementer Worker | Reviewer Worker | Reviewer Model | Provider | Review Result | Duration |
|-----|-------------------|-----------------|----------------|----------|---------------|----------|
| job-1 | 5bao | 9bao | deepseek-v4-flash | deepseek-plan | APPROVED | ~12s |
| job-2 | 9bao | 5bao | deepseek-v4-flash | deepseek-plan | APPROVED | ~10s |
| job-3 | 5bao | 9bao | deepseek-v4-flash | deepseek-plan | APPROVED | (same session as job-1) |
| job-4 | 9bao | 5bao | deepseek-v4-flash | deepseek-plan | APPROVED | (same session as job-2) |

Review criteria: ASCII-only, no secrets, no internal IPs, content quality.

## Model Fallback Evidence

### MiniMax-M3 Failure Pattern

MiniMax-M3 was attempted for jobs 2 and 4. In both cases:
- The model produced internal thinking output but did not execute any file write tool
- The process exited with code 0 (no error) but no file was created
- This is a model behavior issue, not a provider/API error

### Fallback Resolution
- Fallback model: deepseek-plan/deepseek-v4-flash
- Fallback triggered: manually after verifying file absence (not automated)
- Fallback logged with reason: "MiniMax-M3_produced_thinking_only_no_file_output"
- Both fallback executions succeeded on first attempt

### Classification
- This is NOT a rate-limit or quota fallback (no HTTP 429/503)
- This is NOT a timeout fallback
- This IS a model behavior fallback (model_behavior_fallback)
- The model produced valid thinking but failed to invoke the write tool
- This is a manual fallback, not fully automated (no code path auto-detected failure)

## Files Generated

| File | Lines | Source | SHA256 |
|------|-------|--------|--------|
| docs/reports/queue-scheduling-overview.md | 59 | job-1 (5bao, deepseek) | 819a5fe4d020f42e1b84f04b3d584057ae5b55bacb3d9004a37153706a529690 |
| docs/reports/worker-evidence-template.md | 41 | job-2 (9bao, deepseek-fallback) | 32950096c44cba69620d28510a2f633589c745226d42da157a8b24971c9ed967 |
| docs/reports/model-fallback-evidence-fixture.md | 57 | job-3 (5bao, deepseek) | ad6db78ade8ca49bc6779ff54121b3dec0e086bb6055f7d198e37eb0dcc53ea1 |
| docs/reports/active-active-batch-summary.md | 41 | job-4 (9bao, deepseek-fallback) | recomputed_at_commit |

## Dirty Worktree Inventory

### PR-Related (collected into PR branch)

| Node | Worktree | Status | Note |
|------|----------|--------|------|
| 5bao | pilot-job1 | untracked docs/reports/ | Files collected to PR |
| 5bao | pilot-job3 | untracked docs/reports/ | Files collected to PR |
| 9bao | pilot-job2 | untracked docs/reports/ | Files collected to PR |
| 9bao | pilot-job4 | untracked docs/reports/ | Files collected to PR |

### Isolated Nonblocking (not related to PR #167)

| Node | Worktree | Status | Note |
|------|----------|--------|------|
| 5bao | wo-v1131-iteration | COMMIT_EDITMSG + __pycache__ | Historical |
| 5bao | wo-v114 | COMMIT_EDITMSG | Historical |
| 5bao | wo-v1142 | COMMIT_EDITMSG | Historical |
| 5bao | v1184-model-egress | modified evidence | Historical |
| 5bao | wo-v1176-runtime-baseline-gate | modified scripts/tests | Historical |
| 5bao | /tmp/v11776-old | detached, evidence changes | Historical |
| 9bao | /tmp/vibedev-ta9-final | detached, evidence changes | Historical |

Cleanup requires operator approval or safe deletion strategy.

## Observations

1. deepseek-v4-flash is reliable for file creation tasks on both nodes
2. MiniMax-M3 has a behavioral issue where it thinks but does not execute tool calls for this workload
3. SSH dispatch to both workers works correctly
4. Worktree isolation provides clean per-job environments
5. Average job duration: ~14s including SSH overhead and OpenCode startup
