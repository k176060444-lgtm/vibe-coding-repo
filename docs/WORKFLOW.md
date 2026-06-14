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
