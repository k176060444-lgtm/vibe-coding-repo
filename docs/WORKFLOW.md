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

### 使用方法

```bash
# 查看所有任务建议
python3 scripts/vibe_queue_advisor.py

# JSON 输出
python3 scripts/vibe_queue_advisor.py --json

# 限制显示数量
python3 scripts/vibe_queue_advisor.py --limit 5

# 包含 audit_tainted 任务
python3 scripts/vibe_queue_advisor.py --include-tainted
```

### 输出说明

- **⛔ BLOCKED JOBS**: audit_tainted 任务，需要人工审查
- **🔴 HIGH PRIORITY**: 失败任务或阻塞任务
- **🟡 MEDIUM PRIORITY**: 待处理任务
- **🟢 LOW PRIORITY**: 已准备好 merge 的任务
- **⚠️ WARNINGS**: 缺少 work-order 或其他警告

### 与其他工具的关系

- `vibe_repo_status.py`: Job registry 和队列摘要
- `vibe_merge_gate.py`: Merge 前验证
- `vibe_autonomous_merge.py`: 受控 merge wrapper
- `vibe_queue_advisor.py`: 下一步动作建议

## 关键设计决策

| 决策 | 原因 |
|------|------|
| Windows 作为 orchestrator | 开发者在 Windows 上工作，熟悉 Windows 环境 |
| Debian 作为执行节点 | Linux 环境更适合开发工具链，避免 WSL 文件性能问题 |
| 前置审批 | 避免 AI 误判导致的无效工作，节省计算资源 |
| Detached commit | 在审查通过前不影响主分支，保持仓库整洁 |
| Autonomous merge wrapper | 统一 merge 入口，防止裸 gh pr merge，保证 gate 验证 |
| Post-merge freeze | 确保 merge 后状态可审计，锁定 job 不被篡改 |
