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

*V1 Operational Freeze — 2026-06-15*
