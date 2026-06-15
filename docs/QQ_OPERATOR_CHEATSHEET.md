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

*V1 Operational Freeze — 2026-06-15*
