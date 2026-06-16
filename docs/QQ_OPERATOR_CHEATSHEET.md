# QQ Operator Cheatsheet

> 手机 QQ 操作速查表 — 短命令 + 判断标准

## 每轮开始

```
qg
```

Quality Gate 快速检查。必须显示 `QG PASS` 才能继续。

## 每轮结束

```
rr
```

Run Report 生成执行摘要。查看结论和下一步。

## 常用命令

| 命令 | 别名 | 用途 |
|------|------|------|
| `qg` | `go-no-go` | 质量门禁（必须先跑） |
| `rr` | `handoff` | 执行报告（每轮结束） |
| `smoke` | `sm` | 完整烟雾测试 (75 tests) |
| `snapshot` | `s` | 操作员状态快照 |
| `dashboard` | `dash` | 项目仪表盘 |
| `loop-summary` | `ls` | 循环能力概览 |
| `advisor` | `a` | 队列建议 |
| `batch-plan` | `b` | 批量计划 |
| `health` | `h` | 快速健康检查 |
| `help` | `?` | 帮助信息 |

## PASS / WARN / BLOCK 判断

| Verdict | 含义 | 操作 |
|---------|------|------|
| **PASS** | 全部通过 | ✅ 继续执行 |
| **WARN** | 可接受降级 | ⚠️ 审查后继续 |
| **BLOCK** | 关键失败 | ❌ 停止，排查后再继续 |

### 何时继续
- QG: PASS
- Smoke: 全部通过
- Audit: audit_tainted, push_allowed=false
- Run Report: 下一步 = READY

### 何时暂停
- QG: WARN（需审查原因）
- Smoke: 有 SKIP 但无 FAIL
- Run Report: 下一步 = REVIEW

### 何时升级审批
- QG: BLOCK
- Smoke: 有 FAIL
- Audit lock 异常
- origin/main 不可达
- 需要修改 secrets/CI/Provider/SSH
- 需要进入 Level 5

## 常用短提示词模板

### 开始新任务
```
执行 Work Order：wo-xxx-001。
fetch origin 确认基线。运行 qg。创建 branch。实现改动。运行 smoke。commit + push + PR + wrapper merge。
```

### 只做只读检查
```
只做只读检查。运行 qg、rr、smoke，报告结果。
```

### 查看状态
```
当前状态是什么？运行 snapshot 和 dashboard。
```

### 批量任务
```
执行队列：wo-001、wo-002、wo-003。
每个任务独立 branch + PR + wrapper merge。
完成后运行 rr。
```

### 紧急停止
```
停止所有执行。运行 qg 和 smoke。报告问题。
```

## 决策流程图

```
开始 → qg
  ├─ PASS → 执行任务 → rr → 审查 → 继续/暂停
  ├─ WARN → 审查原因 → 可接受？→ 执行 / 暂停
  └─ BLOCK → 停止 → 排查 → 修复 → qg → 循环
```

---

## 受控推送审批 (Privileged Approval) — V1.2

### 标准链路
```
priv-approval create → 人工批准 → token 预检 → priv-push dry-run → priv-push --push → rr → v1
```

### 发起审批
```
priv-approval create --action-id <id> --repo k176060444-lgtm/vibe-coding-repo --branch <branch> --action push --base-sha <sha> --changed-path <file>
```

### 短授权（仅 1 个 pending 时有效）
```
批准 / 确认 / 同意 / 可以执行 / approve / confirm
```

### Token 预检
```
priv-push --token-preflight
```
检查：文件存在 / owner=vibeworker / mode=600 / size>20。**不读取 token 内容。**

### Push 执行
```
priv-push --action-id <id> --dry-run-push   # 验证约束
priv-push --action-id <id> --push            # 真实 push
```

### 仓库信任策略
- **Self-repo** (`k176060444-lgtm/vibe-coding-repo`): 自动化优先，低风险 push 无需人工批准
- **External repo**: 授权优先，push/PR/merge 必须先批准
- 一句话原则：**VibeCoding 自己仓库自动化优先；其他仓库授权优先。**

### 约束
- Token 永远不输出到 stdout/stderr/log
- Self-repo: 任意分支均可 push（policy gate 通过即可）
- External repo: 必须先 `priv-approval create` + 人工批准
- 禁止: force push / merge / secrets / CI / workflow / deploy / tag / release
- Token 仅在 policy 允许 push/PR-write 时读取

### 决策流程
```
创建审批 → 批准 → token 预检 → dry-run → push → rr → v1
```

## V1.3 Trusted Self-Repo Auto-Loop

### 常用命令
```
qg                    # Quality Gate 检查
rr                    # Run Report 会话交接
v1                    # V1 Freeze 验证
tl                    # Trusted Loop 合约检查
tl --contract         # 查看完整合约
```

### Trusted Self Repo 自动执行 WO
```
执行 WO：intake → branch → commit → push → PR → wrapper merge → smoke/qg/rr/v1
无需人工 approve，但必须通过 policy gate
```

### External Repo Privileged Approve
```
priv-approval create --action-id <id> --repo <external-repo> ...
批准 / 确认 / approve
priv-push --action-id <id> --push
```

### V1.3 一句话原则
**trusted self repo 低风险自动闭环；protected external repo 写操作人工授权。**

## V1.4 Trusted Self Batch Runner

### 创建 batch
```
准备 batch.json，包含 batch_id、repo、work_orders 数组
br --batch batch.json --dry-run --json   # 先 dry-run 验证
br --batch batch.json --json             # 执行
```

### 查看 batch 状态
```
br --status --json
```

### 停止/恢复策略
```
任一 WO 失败 → 自动停止 → 生成 batch report
暂不支持 resume，必须人工审查后重新创建 batch
```

### V1.4 一句话原则
**trusted self repo 可批次自动执行；任何 blocker 立即停止；external repo 写操作仍需人工授权。**

## V1.5.1 Worker Resilience

### Worker 暂时失联
```
不要重开批次。等待自动重试（每 5 分钟）。
恢复后可发送：继续 V1.5 或 resume batch。
15 分钟收到一次状态报告。
```

### 状态说明
- **WAITING_WORKER_RECOVERY**：不是失败，正在等待恢复
- **RECONCILING**：worker 恢复，正在校验状态
- **BLOCKED_NEEDS_OPERATOR**：超过 75 分钟，需要人工排障

### 命令
```
wr --check              # 检查 worker 可达性
wr --checkpoint cp.json # 创建检查点
wr --resume cp.json     # 从检查点恢复
wr --status-report cp.json # 生成状态报告
```

## V1.5.2 Batch Canary

### 日常用法
```
br --batch plan.json --json       # 执行 batch
br --status --json                # 查看 runner 状态
wr --check --json                 # 检查 worker 可达性
```

### Worker 失联处理
```
WAITING_WORKER_RECOVERY → 等待自动恢复（5 分钟重试）
RECONCILING → 校验状态后 resume
BLOCKED_NEEDS_OPERATOR → 需要人工排障
```

### V1.5.2 原则
**trusted self repo 可自动批量推进；任何 blocker 立即停止；worker 失联进入等待恢复，不算业务失败。**

*V1 Operational Freeze — 2026-06-15*

## V1.6 Operator Control Plane

### 查看 batch 状态
```
bs --json              # 快速查看当前 batch 状态（只读）
breport --json         # 详细 batch 报告（只读）
```

### 暂停/恢复 batch
```
bp --checkpoint cp.json --json      # 在安全点暂停
bresume --checkpoint cp.json --json # 恢复前先 reconcile
```

### 取消/终止 batch
```
bcancel --checkpoint cp.json --json  # 取消（仅 mutation 前）
babort --checkpoint cp.json --json   # 立即终止（不做 destructive cleanup）
```

### 状态说明
- **PAUSED**: 安全点暂停，等待 resume
- **CANCELLED**: mutation 前取消，不可 resume
- **ABORTED**: 立即终止，不可 resume
- **BLOCKED_BASELINE_MISMATCH**: baseline 不匹配，需人工检查
- **BLOCKED_DIRTY_WORKTREE**: worktree 脏，需清理

### 恢复前提条件（reconcile）
1. Worker 可达（SSH 检查）
2. Baseline 匹配 checkpoint
3. Worktree 干净
4. 状态允许 resume

### V1.6 一句话原则
**trusted self repo 可安全暂停/恢复；cancel 仅 mutation 前；abort 不做 destructive cleanup；external repo 写操作必须 approve。**

*V1.6 Operator Control Plane — 2026-06-16*

## V1.7 Fast Batch Validation

### 使用 fast 模式
```
br --batch plan.json --validation-mode fast --json   # 快速模式
br --batch plan.json --validation-mode full --json    # 完整模式
br --status --json                                     # 查看支持的模式
```

### Fast 模式说明
- 每个 WO 后运行 7 项快速检查（安全边界不可省略）
- 完整 smoke/QG/v1-freeze 延后到 batch 末尾
- 最终验证失败 → BLOCK，不允许 freeze

### 禁止 fast 模式的场景
- 外部仓库（必须 full）
- 高风险操作（必须 full）
- PR #40457（必须 full + 人工 approve）

### V1.7 一句话原则
**质量验证可合并，安全边界检查不可合并。fast 模式：每 WO 快速检查，batch 末尾完整验证。**

*V1.7 Fast Batch Validation Mode — 2026-06-16*

## V1.8 External Repo Policy

### 查看外部仓库策略
```
br --external-policy --ext-repo org/repo --ext-operation push --json
br --external-policy --ext-repo org/repo --ext-operation fetch --json
```

### 审批流程
```
br --external-approval --approval-action create --approval-repo org/repo --approval-branch main --approval-operation push --approval-base-sha abc123 --json
br --external-approval --approval-action approve --approval-id <id> --json
br --external-approval --approval-action expire --approval-id <id> --json
br --external-approval --approval-action list --json
```

### 信任等级
- `k176060444-lgtm/vibe-coding-repo` = trusted-self（自动允许）
- 其他所有仓库 = protected-external（需授权）

### V1.8 一句话原则
**Self repo 自动化优先；external repo 授权优先。读取不需 token，写入必须 approve，V1.8 只 dry-run。**

*V1.8 External Repo Protected Dry-Run — 2026-06-16*

## V1.9 External Authorized Push Preflight

### 运行 preflight 检查
```
br --ext-push-preflight --approval-id <id> --json
```

### Preflight 检查项
- approval 存在且状态=approved
- approval 未过期
- 操作类型是 write
- changed_paths 无 forbidden path
- token 文件存在且权限正确（不读内容）

### 重要区分
- **trusted-self repo** (`k176060444-lgtm/vibe-coding-repo`) = 自动化，不是 external
- **protected-external repo** = 需要人工 approve
- External canary 必须用户提供外部测试仓库

### V1.9 一句话原则
**External authorized push = 用户指定外部仓库 + 人工 approve + preflight + 受控 push。Self repo 不是 external。**

### 当前状态
- WO1 ✅ preflight 实现完成
- WO2 ⏭️ SKIPPED — 无外部测试仓库
- WO3 ✅ 文档冻结

*V1.9 External Repo Authorized Push Canary — 2026-06-16*


### External Push (ext-auth-push / eap)

```
ext-auth-push 流程:
1. 创建 approval JSON → ~/vibedev/privileged-approvals/
2. 用户 approve
3. eap validate --approval-id <id>    # 验证约束
4. eap dry-run --approval-id <id>     # 验证远端 SHA + 预览
5. eap push --approval-id <id>        # 真实 push (需 approve)
6. 验证: fetch 远端确认 branch SHA
```

**禁止:** direct git push / GitHub API write / github.env / GITHUB_PAT / force push



### Node Attribution

每份报告必须包含 Node / Agent Attribution：
- controller_node: Windows (接收指令/调度/汇总)
- execution_node: Debian (执行 git/test/push)
- git_mutation_node: 哪个节点执行了 git 操作
- token_access_node: 哪个节点读取了 token



### Pytest Harness (v1.1.0)

诊断外部仓库的 pytest 可用性。Import 分类：stdlib（不误报）、repo_internal、third_party、unknown。

```bash
harness diagnose --repo-path /path    # 完整诊断
harness build-cmd --repo-path /path --target tests/x.py  # 构造命令
harness self-check                     # 自检
```

Repo profile: `configs/external_test_profiles/<repo>.json`

关键：gateway 等内部模块通过 PYTHONPATH 解决，不报 missing。依赖安装需单独批准。
