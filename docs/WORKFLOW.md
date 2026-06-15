# Vibe Coding Agent 工作流

## 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                   Windows vibedev                       │
│                   (Orchestrator)                        │
│                                                         │
│   ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│   │  Work Order  │  │  Detached    │  │  Future:      │  │
│   │  前置审批     │  │  Commit      │  │  Push to      │  │
│   │             │  │              │  │  vibedev/     │  │
│   │             │  │              │  │  <job_id>     │  │
│   └─────────────┘  └──────────────┘  └──────────────┘  │
└───────────────────────┬─────────────────────────────────┘
                        │ SSH
┌───────────────────────▼─────────────────────────────────┐
│                   Debian vibeworker                      │
│                   (Execution Node)                       │
│                                                         │
│   ┌─────────────┐  ┌──────────────┐  ┌──────────────┐  │
│   │ implementer  │  │  acceptance  │  │  reviewer    │  │
│   │ 自动执行      │  │  自动验收     │  │  自动审查     │  │
│   └─────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## 流程步骤

### 1. Work Order 前置一次审批

- 用户提交任务（Work Order）后，**不直接执行**。
- 系统将 Work Order 呈现给用户进行 **一次审批确认**。
- 用户确认后，工作流才会进入执行阶段。

### 2. implementer 自动执行

- 审批通过后，`implementer` agent 在 **Debian vibeworker** 上自动执行代码编写任务。
- 实现根据 Work Order 中的需求完成编码。

### 3. acceptance 自动验收

- `implementer` 完成后，`acceptance` agent 自动运行验收测试。
- 验证实现是否满足 Work Order 中定义的需求。
- 验收通过才能继续下一步。

### 4. Detached Commit

- 验收通过后，代码以 **detached HEAD** 状态提交到本地 Git 仓库。
- 不会推送到任何远程分支。
- 提交信息包含 Work Order 的描述和 job_id。

### 5. reviewer 自动审查

- 提交完成后，`reviewer` agent 自动对代码变更进行审查。
- 审查结果输出到工作流日志中。

### 6. Autonomous Merge (推荐)

- **⚠️ 禁止裸 `gh pr merge`**：所有 merge 必须通过 `scripts/vibe_autonomous_merge.py`。
- Wrapper 会自动执行 gate 验证，只有 `allow_merge=true` 时才允许 merge。
- 使用方法：

```bash
# Dry-run 模式（推荐先执行）
python3 scripts/vibe_autonomous_merge.py \
  --repo k176060444-lgtm/vibe-coding-repo \
  --pr <PR_NUMBER> \
  --expected-base-sha <BASE_SHA> \
  --expected-head-sha <HEAD_SHA> \
  --allowed-path <PATH1> \
  --allowed-path <PATH2> \
  --job-id <JOB_ID> \
  --dry-run

# 执行 merge（仅当 dry-run 通过后）
python3 scripts/vibe_autonomous_merge.py \
  --repo k176060444-lgtm/vibe-coding-repo \
  --pr <PR_NUMBER> \
  --expected-base-sha <BASE_SHA> \
  --expected-head-sha <HEAD_SHA> \
  --allowed-path <PATH1> \
  --allowed-path <PATH2> \
  --job-id <JOB_ID>
```

### 7. Post-Merge Freeze

- merge 完成后，必须执行 post-merge freeze：
  1. fetch origin 并验证新 main SHA
  2. 验证 merge commit parents
  3. 验证 changed_paths
  4. 在干净 worktree 上运行测试
  5. 验证 locked job 状态不变
  6. 生成 freeze report

## Queue Advisor

Queue Advisor 提供任务队列的下一步动作建议。

**重要**: Queue Advisor v6 具备 superseded job 检测、non-production 优先级修正和 summary 统计一致性。

### Job Lifecycle Policy

Queue Advisor v6+ classifies each job into a lifecycle state:

| Lifecycle | 说明 | 可清理 |
|-----------|------|--------|
| `tainted_lock` | audit_tainted，必须永久保留 | ❌ |
| `merged` | result_sha 已入 main，已完成 | ✅ (records 可归档) |
| `superseded` | failed 但被后续成功 job 替代 | ✅ |
| `non_production` | smoke/fixture/test/debug/legacy | ✅ |
| `active` | pending/in_progress/review_passed | ❌ |
| `failed` | failed 且未被替代 | ⚠️ 需调查 |
| `unknown` | 缺少 work-order | ⚠️ 需检查 |

**关键规则**：
- `wo-code-repo-status-001` 永久保留为 `tainted_lock`，不得删除 records，不得解除 lock
- `merged`/`superseded`/`non_production` 的 records 可在后续维护任务中归档（需单独授权）
- `failed` 的 job 需调查是否仍有真实阻塞

### Superseded Job Detection

v6 会检测已被后续成功任务替代的 failed job：

- `wo-doc-workflow-001`（failed）→ 被 `wo-doc-workflow-002`（review_passed，已入 main）supersede
- `wo-smoke-001`（failed）→ 被 `wo-smoke-002`（review_passed）supersede

Superseded job 不再列为 HIGH PRIORITY，而是归入 `superseded_jobs` 列表。

### Non-Production Priority Fix

v5 的优先级顺序中 `failed`（Priority 3）先于 `non_production`（Priority 5），导致 smoke/fixture/test job 的 failed 状态被当作 HIGH PRIORITY。

v6 修正：`non_production` 检查在 `failed` 之前（Priority 3），smoke/fixture/test/debug/legacy job 即使 failed 也归入 informational_jobs，不会触发 HIGH PRIORITY。

### Summary 统计一致性

v6 继承 v5 的一致性保证...

### Summary 统计一致性

v5 保证以下一致性规则：

- `summary.merged_total` = `len(merged_jobs)`（始终成立）
- 默认（merged 隐藏）：`merged_jobs` 列表为空，`summary.hidden_merged` = `merged_total`
- `--include-merged`：`merged_jobs` 列表完整，`summary.hidden_merged` = 0
- `recovered_jobs` 中 `outcome=already_merged` 的 job 是 `merged_jobs` 的**子集**，不重复计数
- 文本输出的 Merged/Recovered/Unresolved 计数与 JSON 完全一致

### Result SHA Recovery

当 review_passed/clean 的 job 缺少 result_sha 时，按优先级恢复：

1. **本地文件**: manifest.json / state.json / approval-snapshot.json / run-record.json / review-record.json
2. **Feature branch**: vibedev/{job_id} 或 vibedev/wo-{job_id} 的 HEAD
3. **PR merge parent**: main 历史中包含 job_id 的 merge commit 的 feature parent

### Result SHA Recovery

当 review_passed/clean 的 job 缺少 result_sha 时，v4 会按优先级尝试恢复：

1. **本地文件**: manifest.json / state.json / approval-snapshot.json / run-record.json / review-record.json
2. **Feature branch**: vibedev/{job_id} 或 vibedev/wo-{job_id} 的 HEAD
3. **PR merge parent**: main 历史中包含 job_id 的 merge commit 的 feature parent

恢复成功后：
- 若 recovered result_sha 已在 main → 标记为 already_merged（不进入 warnings）
- 若不在 main → 标记为 ready_for_merge（附带 result_sha_source）
- 恢复失败 → 输出 warning: review_passed but missing result_sha

### Actionability 规则

Queue Advisor v4 的 ready_for_merge 建议需要同时满足：

1. **真实 Work Order**: job_id 不匹配 smoke/fixture/test/debug/legacy/e2e 模式
2. **审计清洁**: audit_status=clean
3. **已通过审查**: job_status=review_passed
4. **result_sha 存在**: 可验证代码变更（或已恢复）
5. **未合入 main**: result_sha 不在 main 历史中

不满足上述条件的 job 会被归入：
- **blocked_jobs**: audit_tainted job（始终计入 blocked_total）
- **informational_jobs**: smoke/fixture/test/debug/legacy job
- **warnings**: 缺少 work-order 且恢复失败的 job
- **recovered_jobs**: result_sha 已恢复的 job
- **unresolved_jobs**: result_sha 恢复失败的 job

### Actionability 规则

Queue Advisor v3 的 ready_for_merge 建议需要同时满足：

1. **真实 Work Order**: job_id 不匹配 smoke/fixture/test/debug/legacy/e2e 模式
2. **审计清洁**: audit_status=clean
3. **已通过审查**: job_status=review_passed
4. **result_sha 存在**: 可验证代码变更
5. **未合入 main**: result_sha 不在 main 历史中

不满足上述条件的 job 会被归入：
- **blocked_jobs**: audit_tainted job（始终计入 blocked_total）
- **informational_jobs**: smoke/fixture/test/debug/legacy job
- **warnings**: 缺少 work-order 或 result_sha 的 job

**重要**: blocked_total 即使在默认隐藏 tainted job 时也反映真实数量。

### 使用方法

```bash
# 查看所有任务建议（自动排除已合入 main 的任务）
python3 scripts/vibe_queue_advisor.py

# JSON 输出
python3 scripts/vibe_queue_advisor.py --json

# 限制显示数量
python3 scripts/vibe_queue_advisor.py --limit 5

# 包含 audit_tainted 任务
python3 scripts/vibe_queue_advisor.py --include-tainted

# 显示已合入 main 的任务
python3 scripts/vibe_queue_advisor.py --include-merged
```

### Merged-State 检测

Queue Advisor v2 会检查每个 job 的 `result_sha` 是否已在 main 历史中：

- **已合入 main**: 标记为 `merged`，默认不显示在 action items 中
- **未合入**: 正常显示为 `ready_for_merge` 或其他状态
- **缺失 result_sha**: 输出 warning，不误判为 ready_for_merge
- **audit_tainted**: 始终进入 blocked/warnings，从不建议 push/merge

**重要**: 合并必须通过 `scripts/vibe_autonomous_merge.py` wrapper，禁止裸 `gh pr merge`。

### 输出说明

- **⛔ BLOCKED JOBS**: audit_tainted 任务，需要人工审查
- **🔴 HIGH PRIORITY**: 失败任务或阻塞任务
- **🟡 MEDIUM PRIORITY**: 待处理任务
- **🟢 LOW PRIORITY**: 已准备好 merge 的任务（排除已合入）
- **📊 MERGED**: 已合入 main 的任务计数（默认不列出详情）
- **⚠️ WARNINGS**: 缺少 work-order 或其他警告

### 与其他工具的关系

- `vibe_repo_status.py`: Job registry 和队列摘要
- `vibe_merge_gate.py`: Merge 前验证
- `vibe_autonomous_merge.py`: 受控 merge wrapper
- `vibe_queue_advisor.py`: 下一步动作建议（含 merged-state 检测）

## Operator Snapshot

Operator Snapshot 提供统一的状态快照，适合 QQ/Hermes 主控直接阅读。

### 使用方法

```bash
# 完整快照（JSON）
python3 scripts/vibe_operator_snapshot.py --json

# 紧凑模式（约 20 行）
python3 scripts/vibe_operator_snapshot.py --compact

# 包含 tainted/merged 信息
python3 scripts/vibe_operator_snapshot.py --include-tainted --include-merged --json
```

### 输出字段

| 字段 | 说明 |
|------|------|
| repo.local_main_sha | 当前本地 main SHA |
| repo.main_consistent | 本地/远端 main 是否一致 |
| jobs_summary | 复用 Queue Advisor v5 统计口径 |
| locks | audit_tainted 锁定 job 列表 |
| recommended_next_action | 建议的下一步操作 |
| warnings | 当前告警列表 |

### 与其他工具的关系

- `vibe_repo_status.py`: Job registry 详情
- `vibe_queue_advisor.py`: 队列建议详情
- `vibe_merge_gate.py`: Merge 前验证
- `vibe_autonomous_merge.py`: 受控 merge wrapper
- `vibe_operator_snapshot.py`: 统一状态快照

## Dispatch Planner

Dispatch Planner 把 Operator Snapshot / Queue Advisor 输出转成下一步 Work Order 建议。

### 使用方法

```bash
# JSON 输出
python3 scripts/vibe_dispatch_planner.py --json

# 紧凑模式
python3 scripts/vibe_dispatch_planner.py --compact
```

### 建议动作

| 动作 | 说明 |
|------|------|
| `hold_due_to_blocker` | 存在 tainted lock，需人工解决 |
| `investigate_failures` | 存在 high priority 失败项 |
| `continue_processing` | 存在 in-progress 任务 |
| `process_merge_queue` | 存在 ready_for_merge 任务 |
| `queue_clean` | 队列清洁，建议下一阶段规划 |

### 与其他工具的关系

- `vibe_operator_snapshot.py`: 状态快照
- `vibe_queue_advisor.py`: 队列建议详情
- `vibe_dispatch_planner.py`: 下一步 Work Order 建议

## 命令速查

详见 [COMMANDS.md](COMMANDS.md)，覆盖 snapshot、queue advisor、failed triage、创建 Work Order、wrapper merge、freeze、只读核验、维护清理。

## 模型切换

详见 [MODEL_SWITCH_RUNBOOK.md](MODEL_SWITCH_RUNBOOK.md)，覆盖额度耗尽、429、timeout、质量不足时的人工切换流程。

## 关键设计决策

| 决策 | 原因 |
|------|------|
| Windows 作为 orchestrator | 开发者在 Windows 上工作，熟悉 Windows 环境 |
| Debian 作为执行节点 | Linux 环境更适合开发工具链，避免 WSL 文件性能问题 |
| 前置审批 | 避免 AI 误判导致的无效工作，节省计算资源 |
| Detached commit | 在审查通过前不影响主分支，保持仓库整洁 |
| Autonomous merge wrapper | 统一 merge 入口，防止裸 gh pr merge，保证 gate 验证 |
| Post-merge freeze | 确保 merge 后状态可审计，锁定 job 不被篡改 |

## Toolchain Smoke Suite

Run all smoke tests before starting Work Orders:

```bash
python3 scripts/test_toolchain_smoke.py
python3 scripts/test_toolchain_smoke.py --json
```

Tests: command router (help, snapshot, advisor, dispatch, batch-plan), health check, operator snapshot, queue advisor, dispatch planner, batch plan.

## Health Check

Verify toolchain health before starting Work Orders:

```bash
python3 scripts/vibe_health_check.py
python3 scripts/vibe_health_check.py --json
```

Checks: py_compile, import, operator snapshot, queue advisor, dispatch planner, batch plan, audit_tainted lock.

## Command Router

Unified CLI entry point for all orchestrator commands:

```bash
python3 scripts/vibe_command_router.py <command> [options]
```

See [COMMANDS.md](COMMANDS.md) for full command reference.

## Autonomous Operation Runbook

For detailed autonomous operation boundaries, stop conditions, and human approval points, see:
- **[AUTONOMOUS_OPERATION_RUNBOOK.md](AUTONOMOUS_OPERATION_RUNBOOK.md)**: Full autonomous operation runbook

## QQ Command Routing Specification

For detailed command specifications, permission boundaries, and prohibited behaviors, see:
- **[QQ_COMMAND_ROUTING.md](QQ_COMMAND_ROUTING.md)**: Full command routing specification

### Command Summary

| Command | Intent | Risk Level |
|---------|--------|------------|
| /snapshot | Unified status snapshot | Read-only |
| /queue | Queue analysis & lifecycle | Read-only |
| /plan | Dispatch planning | Read-only |
| /next | Next action recommendation | Read-only |
| /workorder | Work Order management | Medium |
| /review | Job review status | Read-only |
| /merge | Wrapper merge execution | High |
| /freeze | Post-merge freeze | Read-only |
| /batch | Batch queue planning | Read-only |


## Batch Queue Plan

Generate batch execution plan for multiple Work Orders:

```bash
python3 scripts/vibe_batch_plan.py --json
python3 scripts/vibe_batch_plan.py --limit 3 --json
```

Output: task_order, risk_level, allowed_paths, stop_conditions, requires_human_approval, expected_reports.

### E2E Test

Run the E2E test to verify the full chain:

=== Batch Plan E2E Test ===
Script dir: /home/vibeworker/vibedev/worktrees/wo-code-batch-plan-e2e-001/scripts
Jobs dir: /home/vibeworker/vibedev/jobs
Fixture dir: /tmp/batch-plan-e2e-5xgnnl39

Created 6 fixture jobs

  PASS: real jobs (queue_clean, 0 tasks)
  PASS: fixture jobs (4 tasks, high risk)
  PASS: --limit 2 (2 tasks)
  PASS: import safety (no IO)
  PASS: stop conditions (7 conditions)
  PASS: expected reports (6 reports)

=== ALL TESTS PASSED ===

Tests:
1. Real jobs: queue_clean scenario (0 tasks)
2. Fixture jobs: mixed scenarios (4 tasks, high risk)
3. --limit flag: limits task count
4. Import safety: no IO on import
5. Risk classification: correct risk levels
6. Stop conditions: all 7 conditions present
7. Expected reports: all 6 reports present
## Recommendation Consistency Rule (v2)

All recommendation tools must produce consistent top-level guidance:

| Scenario | Operator Snapshot | Dispatch Planner | Batch Plan |
|----------|------------------|------------------|------------|
| Queue clean | queue_clean | queue_clean | tasks=0, risk=low |
| Tainted lock | resolve_blocked | hold_due_to_blocker | risk=critical |
| Failed jobs | investigate_failures | investigate_failures | risk=high |
| Ready for merge | process_merge_queue | process_merge_queue | risk=low |
| Superseded only | queue_clean | queue_clean + info | tasks=0 |

**Key invariant**: Superseded jobs are informational (already resolved by later success). They must NOT cause Dispatch Planner to recommend `resolve_superseded` when the queue is otherwise clean.

**Tools**: `vibe_operator_snapshot.py`, `vibe_dispatch_planner.py`, `vibe_batch_plan.py`

**Consistency check**: `test_toolchain_smoke.py` includes `recommendation_consistency` test that verifies all three tools agree on the top-level recommendation.


## Command Router v2 (Enhanced UX)

- Short aliases: s=snapshot, a=advisor, d=dispatch, b=batch-plan, h=health, sm=smoke, ?=help, v=version
- Typo correction: close match suggestions for misspelled commands
- Version info: 
- Smoke suite:  (11 tests)


## Toolchain Freeze (v1)

The toolchain has been frozen as of baseline . See [TOOLCHAIN_FREEZE.md](TOOLCHAIN_FREEZE.md) for the complete freeze document.

Key frozen items:
- 9 scripts, all standard library, import-safe
- 11 smoke tests, all passing
- Recommendation consistency verified (snapshot/dispatch/batch-plan agree)
-  permanently locked as audit_tainted


## Feature Work Order Template

For converting user requirements into executable Work Orders, see [WORK_ORDER_TEMPLATE.md](WORK_ORDER_TEMPLATE.md).

Key features:
- **Structured YAML**: work_order_id, scope, acceptance_criteria, review_criteria
- **Type prefixes**: wo-code-, wo-doc-, wo-maint-, wo-test-, wo-fix-
- **8-phase pipeline**: prepare → implement → test → commit → push → review → wrapper → freeze
- **Failure handling**: stop on blocker, preserve state, escalate if needed
- **QQ/Hermes integration**: user message → structured Work Order → approval → execution → report


## Work Order Intake (v1)

Natural language requirements can be converted to structured Work Order drafts:

```
python scripts/vibe_command_router.py intake
# or directly:
python scripts/vibe_workorder_intake.py 'your requirement here'
```

The intake script:
- Auto-classifies risk level (low/medium/high/critical)
- Auto-detects Work Order type (code/doc/test/fix/maint)
- Infers allowed paths from requirement text
- Generates acceptance test criteria
- Detects forbidden action patterns
- Outputs draft only — never executes

### From Requirement to Execution

1. User provides requirement (text or file)
2. Intake generates draft (Markdown or JSON)
3. Human reviews and approves draft
4. Executor creates Work Order from approved draft
5. Pipeline executes: prepare → implement → test → commit → review → merge


## Smoke Suite v2 (16 tests)

The smoke suite now includes intake verification:
- Intake basic: markdown draft generation
- Intake JSON: valid JSON with all required fields
- Intake risk: critical requirements require human approval
- Intake type: auto-detects code/doc/test/fix/maint
- Intake router: intake command accessible via router

Run: `python scripts/test_toolchain_smoke.py`


## Release Notes (v1)

Generate progress reports from git history:

```
python scripts/vibe_command_router.py dash
python scripts/vibe_command_router.py notes
# or directly:
python scripts/vibe_release_notes.py --json
python scripts/vibe_command_router.py dash
python scripts/vibe_command_router.py notes
# or directly:
python scripts/vibe_release_notes.py --compact
python scripts/vibe_command_router.py dash
python scripts/vibe_command_router.py notes
# or directly:
python scripts/vibe_release_notes.py --limit 10 --since <SHA>
```

Reports include: merged PRs, capability changes, toolchain status, safety status, and recommended next phase.


## Smoke Suite v3 (20 tests)

Release notes smoke coverage added:
- 17: Release Notes basic compact output
- 18: Release Notes JSON with all required fields
- 19: Release Notes safety status (audit_tainted lock visible)
- 20: Release Notes via router (notes command)

Run: `python scripts/test_toolchain_smoke.py`


## Project Dashboard

The [PROJECT_DASHBOARD.md](PROJECT_DASHBOARD.md) provides a single-page operator view of the entire system:
- Current baseline and sync status
- All available commands and aliases
- Autonomous capability matrix
- Safety and audit status
- Lifecycle summary
- Quick command reference


## Smoke Suite v4 (23 tests)

Dashboard smoke coverage added:
- 21: Dashboard text output via router
- 22: Dashboard JSON output with metadata
- 23: Dashboard aliases (dash, status-page)

Run: `python scripts/test_toolchain_smoke.py`


## Demo Scenarios (v1)

Run repeatable scenario examples to verify the pipeline:

```
python scripts/vibe_demo_scenarios.py --scenario queue-clean
python scripts/vibe_demo_scenarios.py --scenario feature-request --json
python scripts/vibe_demo_scenarios.py --scenario maintenance
```

All scenarios are read-only. No PRs created, no tasks executed.


## Report Export (v1)

Export reports to files for QQ/Hermes delivery or archival:

```
python scripts/vibe_report_export.py --kind snapshot --output-dir /tmp/reports
python scripts/vibe_report_export.py --kind all --output-dir /tmp/reports --json
python scripts/vibe_report_export.py --kind dashboard --dry-run
```

Writes only to --output-dir. Never modifies repo source. Never exports secrets.


## Operator Daily Report (v1)

One-command daily status:

```
python scripts/vibe_daily_report.py --compact
python scripts/vibe_daily_report.py --json
```

Includes: main SHA, router version, smoke/health status, queue status, recent PRs, audit lock, next action.

## Smoke Suite v5 (25 tests)

Daily report smoke coverage added:
- 24: Daily Report text output
- 25: Daily Report JSON with all required fields

Run: `python scripts/test_toolchain_smoke.py`


## Work Order Validator (v1)

Validate intake drafts before execution:

```
python scripts/vibe_workorder_intake.py 'requirement' --json > draft.json
python scripts/vibe_workorder_validator.py draft.json
python scripts/vibe_workorder_validator.py draft.json --json
```

Checks: required fields, type, risk_level, human approval consistency,
allowed_paths safety, forbidden_actions, goal, acceptance_tests,
stop_conditions, draft_only flag, ID format.

Verdict: PASS (all checks) / WARN (warnings only) / FAIL (errors).


## Work Order Packager (v1)

Package validated drafts into execution prompts:

```
python scripts/vibe_workorder_intake.py 'requirement' --json > draft.json
python scripts/vibe_workorder_validator.py draft.json
python scripts/vibe_workorder_packager.py draft.json --compact
python scripts/vibe_workorder_packager.py draft.json --json --max-chars 2000
```

Includes: draft fields, baseline SHA, router version, smoke count, safety rules, execution pipeline.
Supports chunking with --max-chars for large prompts.


## Preflight Check (v1)

End-to-end intake → validate → package chain:

```
python scripts/vibe_command_router.py preflight 'your requirement here'
```

Or step by step:
```
python scripts/vibe_workorder_intake.py 'requirement' --json > draft.json
python scripts/vibe_workorder_validator.py draft.json
python scripts/vibe_workorder_packager.py draft.json --compact
```

## Smoke Suite v6 (28 tests)

Preflight smoke coverage:
- 26: Validator basic validation (intake → validate → PASS)
- 27: Packager basic packaging (intake → package → chars > 0)
- 28: Preflight router chain (preflight command via router)

### Work Order Registry

The registry stores work order metadata locally for tracking intake/validate/packager outputs:

```
intake → validate → registry.register → packager → [human approval] → execute
```

Registry entries track: workorder_id, title, risk_level, status (draft→validated→packaged→approved→executed→blocked), base_sha, source, requires_human_approval.

The registry is read-only by default. Only  subcommand with explicit  writes to the registry.


### Work Order Registry

The registry stores work order metadata locally for tracking intake/validate/packager outputs:

```
intake → validate → registry.register → packager → [human approval] → execute
```

Registry entries track: workorder_id, title, risk_level, status (draft/validated/packaged/approved/executed/blocked), base_sha, source, requires_human_approval.

The registry is read-only by default. Only `register` subcommand with explicit `--registry-dir` writes to the registry.


### Registry Integration

The Work Order Registry is now accessible via the Command Router:

```
router reg list --json              # List all registry entries
router reg show --id my-wo          # Show specific entry
router reg register --id my-wo      # Register new entry
```

Registry entries track work order lifecycle: draft → validated → packaged → approved → executed → blocked.


### Status Transitions

The registry supports controlled status transitions with append-only history:

```
draft → validated → packaged → approved → executed
  ↓         ↓          ↓         ↓         ↓
blocked   blocked    blocked   blocked   blocked
  ↓
draft (reset from blocked)
```

Each transition requires:
- Valid target status (illegal jumps rejected)
- Reason for audit trail
- Automatic timestamp and history digest

Status history is append-only and includes SHA256 digest for integrity verification.


### Approval Receipts

Approval receipts record human approval decisions with cryptographic integrity:

```
requirement → intake → validate → registry.register → packager → approval-receipt.create → [human approval] → execute
```

Receipts include:
- SHA256 digest of receipt data
- Workorder ID, base SHA, package digest
- Approver label and approval text
- Requires_human_approval flag
- Approved scope (from workorder)
- Stop conditions (from workorder)

Receipts are stored in `receipts/` subdirectory of the registry and do NOT execute Work Orders.


### Router Integration

Status update and approval receipt are now accessible via the Command Router:

```
router ws --id my-wo --status validated --reason "OK"     # Status update
router ar create --id my-wo --base-sha abc123 ...          # Create receipt
router ar list --json                                       # List receipts
```

Router v2.6 adds:
- `wo-status` / `ws` → registry update-status
- `receipt` / `ar` / `approve-receipt` → approval receipt

Smoke suite now 36/36 PASS.


### Execution Evidence

Execution evidence bundles collect all artifacts from a Work Order execution:

```
requirement → intake → validate → registry → packager → approval-receipt
                                                              ↓
                              execution-evidence.create ← [execute]
                                                              ↓
                              evidence includes:
                              - registry entry
                              - approval receipt
                              - base_sha, result_sha, post_merge_sha
                              - PR URL, wrapper results
                              - smoke/health results
                              - implementer/reviewer models
                              - job_status, audit_status
                              - changed_paths
```

Evidence bundles are stored in `evidence/` directory with SHA256 digest for integrity.


### Router Integration (v2.7)

Execution evidence is now accessible via the Command Router:

```
router ev create --id my-wo --base-sha abc123 --result-sha def456 ...  # Create evidence
router ev list --json                                                  # List evidence
router ev show --evidence-id ev-001                                    # Show evidence
```

Router v2.7 adds:
- `evidence` / `ev` / `exec-log` → execution evidence

Smoke suite remains 36/36 PASS.


### Smoke Suite (40 tests)

The smoke suite now includes 40 tests covering:
- Router commands (snapshot, advisor, dispatch, batch-plan, health, smoke)
- Intake (basic, JSON, risk, type, router)
- Release Notes (basic, JSON, safety, router)
- Dashboard (text, JSON, aliases)
- Daily Report (text, JSON)
- Validator (basic)
- Packager (basic)
- Preflight (router)
- Registry (basic, JSON, router, readonly)
- Status Update (valid, invalid)
- Approval Receipt (create/list, router)
- Execution Evidence (basic, JSON, router, readonly)

All tests must PASS for deployment.


### Execution Gate

The execution gate is a machine-checkable admission control before Work Order execution:

```
requirement → intake → validate → registry → packager → approval-receipt
                                                              ↓
                              execution-gate.check ← [before execute]
                                                              ↓
                              verdict: ALLOW / REVIEW / BLOCK
```

Gate checks:
1. Registry status is approved
2. Approval receipt exists and matches
3. Base SHA matches current origin/main
4. Risk level requires human approval if high/critical
5. Stop conditions are defined
6. Allowed paths are specified
7. Forbidden actions include high-risk protections
8. Audit tainted lock is not set

BLOCK verdicts must halt execution. REVIEW verdicts require human decision.


### Router Integration (v2.8)

Execution gate is now accessible via the Command Router:

```
router gate --id my-wo --current-main-sha abc123          # Run gate check
router exec-gate --id my-wo --current-main-sha abc123 --json  # JSON output
router ready-run --id my-wo --current-main-sha abc123     # Alias
```

Router v2.8 adds:
- `exec-gate` / `gate` / `ready-run` → execution gate

Smoke suite remains 40/40 PASS.


### Smoke Suite (44 tests)

The smoke suite now includes 44 tests covering:
- Router commands (snapshot, advisor, dispatch, batch-plan, health, smoke)
- Intake (basic, JSON, risk, type, router)
- Release Notes (basic, JSON, safety, router)
- Dashboard (text, JSON, aliases)
- Daily Report (text, JSON)
- Validator (basic)
- Packager (basic)
- Preflight (router)
- Registry (basic, JSON, router, readonly)
- Status Update (valid, invalid)
- Approval Receipt (create/list, router)
- Execution Evidence (basic, JSON, router, readonly)
- Execution Gate (ALLOW, BLOCK, REVIEW, router)

All tests must PASS for deployment.


### Golden Path E2E

The golden path E2E test suite validates the complete Work Order lifecycle:

```
requirement → intake → validate → registry.register → packager
    → registry.update-status (draft → validated → packaged → approved)
    → approval-receipt.create
    → execution-gate.check (ALLOW / REVIEW / BLOCK)
    → evidence.create
```

Three test paths:
1. **ALLOW** — clean workorder, all checks pass, gate allows execution
2. **BLOCK** — base_sha mismatch, gate blocks execution
3. **REVIEW** — stop conditions present, gate requires human review

All tests use temporary directories and do NOT modify repo source code.

### Evidence Verifier

The evidence verifier checks execution evidence bundle integrity:

```
evidence.create → evidence-verifier.verify → PASS / WARN / FAIL
```

Verifies: required fields, digest, registry entry, approval receipt, SHAs, smoke/health, job/audit status, changed_paths scope.

### Safe Executor Stub

The safe executor generates execution plans from ALLOW gate results:

```
execution-gate.check → ALLOW → safe-executor.plan → execution_plan
```

The stub does NOT:
- Execute coding agents
- Call models
- Push, merge, or deploy
- Write to repo source code

Output includes: execution_plan (phases), required_inputs, blocked_if, evidence_expectations.
## Executor Boundary Freeze
See docs/EXECUTOR_BOUNDARY_FREEZE.md for frozen executor boundaries and unfreeze requirements.

## Real Feature Demo
See docs/REAL_FEATURE_DEMO.md for a complete walkthrough from natural language to verified execution.

## Executor Unfreeze Plan
See docs/EXECUTOR_UNFREEZE_PLAN.md for graduated unfreeze levels (0-4).

## Minimal Executor Fixture Spec
See docs/MINIMAL_EXECUTOR_FIXTURE_SPEC.md for Level 1 fixture definition.


## Fixture / Partial Evidence Handling

When the evidence verifier examines evidence from fixture runs, partial executions,
or level-based unfreeze tests, it uses heuristics to detect **fixture mode**:

### Fixture Mode Detection

The verifier considers evidence to be in fixture mode when:
- `workorder_id` contains `fixture`, `level1`, `level2`, `level3`, or `level4`
- Evidence has `wrapper_dry_run` or `wrapper_merge` set (PR workflow)
- `implementer_model` is `none` or empty (no real model invoked)

### Verdict Classification

| Verdict Detail | Meaning | Operator Action |
|----------------|---------|-----------------|
| `PASS` | All checks passed | Proceed |
| `WARN_EXPECTED_FIXTURE_MODE` | Missing fields expected in fixture mode | Acceptable for fixture runs |
| `WARN_UNEXPECTED_MISSING_FIELD` | Missing fields in non-fixture mode | Investigate — normally required |
| `FAIL` | Critical integrity failure | Do NOT proceed |

### Operator Summary

The `operator_summary` field provides a human-readable explanation:
- **Fixture mode**: "Fixture/partial evidence mode detected. Missing fields are expected: [list]."
- **Unexpected**: "UNEXPECTED warnings in non-fixture mode: [list]. Investigate why."
- **Fail**: "CRITICAL: Evidence has integrity failures. Errors: [list]."

### Missing Fields

The `missing_fields` list identifies all absent fields across WARN/FAIL checks.
In fixture mode, expected missing fields include: `registry_entry`, `approval_receipt`, `smoke_result`.


## Workflow Quality Gate

The **quality gate** (`scripts/vibe_quality_gate.py`) provides a single-command
aggregated health check for the entire autonomous loop. Run it before and after
every real executor invocation to verify system readiness.

### Usage

```bash
# Full output
python3 scripts/vibe_quality_gate.py

# JSON for automation
python3 scripts/vibe_quality_gate.py --json

# Compact one-liner
python3 scripts/vibe_quality_gate.py --compact

# Via router
python scripts/vibe_command_router.py qg --json
python scripts/vibe_command_router.py go-no-go
```

### Verdict Rules

| Verdict | Meaning | Operator Action |
|---------|---------|-----------------|
| **PASS** | All core checks passed | Proceed with execution |
| **WARN** | Acceptable degradation | Review warnings, then proceed if justified |
| **BLOCK** | Critical failure | Do NOT proceed — investigate and fix |

### When BLOCK triggers:
- Smoke suite has failures
- origin/main is unreachable or mismatched
- Audit lock (`wo-code-repo-status-001`) is missing or `push_allowed` is not `false`
- Quality gate script itself is missing

### When WARN triggers:
- Loop summary is unavailable
- Evidence verifier is missing
- Router version check failed
- Non-critical component degradation

### Integration with Real Executor

```
Pre-execution:  quality-gate → if PASS/WARN → proceed
Post-execution: quality-gate → verify no regressions
```

## Run Report / Session Handoff

The **run report** (`scripts/vibe_run_report.py`) generates a summary of the current
system state after each Work Order execution. Use it to quickly判断是否继续、暂停、升级审批或回滚。

### Usage

```bash
# Markdown (default, QQ-friendly)
python3 scripts/vibe_run_report.py

# JSON for automation
python3 scripts/vibe_run_report.py --json

# Compact one-liner
python3 scripts/vibe_run_report.py --compact

# Via router
python scripts/vibe_command_router.py rr --json
python scripts/vibe_command_router.py handoff --compact
```

### Report Fields

| Field | Description |
|-------|-------------|
| `baseline` | Current origin/main SHA |
| `quality_gate` | Aggregated health check verdict |
| `smoke_status` | Smoke suite result |
| `loop_summary` | Component count and health |
| `audit_lock` | wo-code-repo-status-001 status |
| `pr_summary` | Latest merged PR info |
| `new_freeze_baseline` | Post-merge SHA |
| `next_recommended_action` | What to do next |
| `operator_summary` | Human-readable summary |

### Decision Guide

| Run Report Says | Action |
|-----------------|--------|
| QG:PASS, Audit:intact, Next:READY | Proceed with next Work Order |
| QG:WARN, Audit:intact, Next:REVIEW | Review warnings, then proceed if justified |
| QG:BLOCK, Next:HALT | Investigate and fix before any execution |
| Audit lock missing | STOP — critical security issue |


## V1 Operational Freeze

The V1 workflow is now frozen and operational. See [V1_OPERATIONAL_FREEZE.md](V1_OPERATIONAL_FREEZE.md) for full details.

Key commands before/after every execution:
-  — quality gate (must PASS)
-  — run report (generate summary)
-  — V1 freeze check (verify freeze intact)


## Privileged Push Approval Workflow

High-privilege GitHub keys are controlled via a two-stage approval workflow:

1. **Create approval request**: "priv-approval create --action-id <id> --repo <repo> --branch <branch> --action push --base-sha <sha>"
2. **Human approves**: "approve" / "批准" / "确认" (short approval when exactly 1 pending)
3. **Privileged push (dry-run)**: "priv-push --action-id <id>" — validates constraints, outputs would_push=true/false
4. **Future**: real push only after dry-run PASS + explicit authorization

### Invariants
- Default: no privileged action is available
- Short approval requires exactly 1 pending, non-expired action
- No force push, no PR merge, no secrets/CI/workflow/provider/SSH paths
- All actions are audit-logged in approval-dir






## V1.5.1 Worker Resilience & Resume

**When worker is temporarily unreachable, do NOT restart the batch. Wait for auto-retry.**

### Recovery States
| State | Meaning | Action |
|-------|---------|--------|
| `WAITING_WORKER_RECOVERY` | Worker unreachable, retrying | Wait, no mutation |
| `RECONCILING` | Worker back, verifying state | Check baseline/worktree/remote |
| `BLOCKED_NEEDS_OPERATOR` | Max wait exceeded | Human intervention needed |

### Retry Policy
- Retry interval: 5 minutes
- Max wait: 75 minutes
- Max retries: 15
- Status report: every 15 minutes

### Resume Rules
- `before_any_mutation` → restart WO from scratch
- `after_push` / `after_pr` / `after_merge` → reconcile first, then continue/skip/block
- Baseline mismatch or dirty worktree → BLOCK, do not auto-fix


## V1.4 Trusted Self Batch Runner

**One-line principle: trusted self repo can batch auto-execute; any blocker stops immediately; external repo writes still require human authorization.**

### Batch Execution Chain
```
batch plan → [WO1 → WO2 → ... → WO_N] → batch report
  Each WO: branch → commit → push → PR → wrapper merge → smoke/qg/v1-freeze
  After each WO: refresh baseline before next
  On any failure: STOP, generate batch report, do not continue
```

### Stop Rules
Any of these stops the batch immediately:
- smoke fail, QG fail, V1-freeze fail
- dirty worktree, merge conflict
- forbidden path, token redaction fail
- wrapper merge fail, unexpected changed_paths
- external repo write without approval


## V1.3 Trusted Self-Repo Auto-Loop

**One-line principle: trusted self repo low-risk auto-loop; protected external repo write ops require human authorization.**

### Auto-Loop Chain (trusted-self)
```
intake → branch → commit → push → PR → wrapper merge → smoke/qg/rr/v1-freeze → freeze baseline
```

### Trust Policy
| Repo | Trust Level | Push Requires Approval | Token Read |
|------|-------------|----------------------|------------|
| k176060444-lgtm/vibe-coding-repo | trusted-self | No (policy gate auto) | After policy passes |
| All others | protected-external | Yes (must approve) | After approval |

### Policy Gate (all repos)
- Forbidden paths: `.github/workflows/`, `secrets/`, `.env`, `ssh/`
- No force push, no PR merge, no secrets/CI/workflow/provider/SSH
- Wrapper merge required (`vibe_autonomous_merge.py`)
- No bare `gh pr merge`

