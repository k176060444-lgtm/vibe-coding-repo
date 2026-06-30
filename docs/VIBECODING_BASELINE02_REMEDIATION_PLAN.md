# VibeCoding Baseline02 Remediation Plan

## 1. 背景

Baseline01（repo/gate 层面）已通过：PR #265-#275 合并，main 位于 `5cc45fb`。Baseline01 验证了架构规范、审批 gate 和文档一致性。

然而第二次灰度运行暴露了 **runtime flow 缺失**：PR 修好不等于 VibeCoding 流程通过。局部 PR mergeable、单次测试通过、单一阶段完成，不能替代端到端 runtime flow 的完整性。

---

## 2. 总目标

实现 **operator-directed VibeCoding runtime flow**：

```
intake → classify → plan/recommend → operator approval → role-node-model assignment → dispatch → execution → validation → evidence/report
```

每个环节必须有可验证的输入/输出、明确的授权边界和 fail-closed 行为。

---

## 3. 阶段治理原则

| 原则 | 说明 |
|------|------|
| **Stage pre-audit** | 每个阶段开始前，必须对当前状态做只读审计，确认先决条件满足、无残留 drift |
| **Stage acceptance** | 每个阶段完成后，必须通过 stage acceptance 验收，出具验收报告和 final verdict |
| **Sequential progression** | 一个阶段一个阶段推进，未通过验收不得进入下一阶段 |
| **Scope discipline** | 每个阶段有明确的 allowed_scope 和 forbidden_scope |

---

## 4. 阶段划分

### 阶段 0：修正 PR #276 元契约文档

| 属性 | 内容 |
|------|------|
| **pre_audit** | 确认 `docs/OPERATOR_ORCHESTRATOR_CONTRACT.md` 中 ≤ 已改为 <、STOP_AND_REANCHOR 字面量正确、签署措辞已改为 Working Agreement |
| **allowed_scope** | 仅修改 `OPERATOR_ORCHESTRATOR_CONTRACT.md`；新增 `VIBECODING_BASELINE02_REMEDIATION_PLAN.md` |
| **forbidden_scope** | SOUL.md、MEMORY.md、config.yaml、model_pool、tools、scripts、tests、worker、SSH、模型调用、PR merge |
| **deliverables** | PR #276 更新后的文档 + 新增整改计划 |
| **acceptance_criteria** | git status clean；changed_files 仅限上述 2 个 doc；STOP_AND_REANCHOR 字面量正确；不包含法律签署语义 |
| **final_verdict** | OPERATOR_ORCHESTRATOR_CONTRACT_AND_BASELINE02_PLAN_READY |

---

### 阶段 1：BASELINE02 runtime flow 全量只读审计

| 属性 | 内容 |
|------|------|
| **pre_audit** | PR #276 已合并（或至少元契约已定稿） |
| **allowed_scope** | 只读扫描 repo 中所有文件：检查是否存在绕过 role-node-model assignment 的路径 |
| **forbidden_scope** | 任何 git write、SSH、模型调用、配置文件修改 |
| **deliverables** | 审计报告，列出所有 flow gap：哪些 PR/workflow 没有经过 operator approval 的 assignment |
| **acceptance_criteria** | 完整覆盖面；每个 gap 标记 severity；不遗漏 runtime flow 缺失场景 |
| **final_verdict** | BASELINE02_AUDIT_PASS / BASELINE02_AUDIT_PARTIAL / BASELINE02_AUDIT_FAIL |

---

### 阶段 2：固化 VIBECODING_RUNTIME_FLOW_SPEC

| 属性 | 内容 |
|------|------|
| **pre_audit** | 阶段 1 审计通过，gap 清单完整 |
| **allowed_scope** | 新增 `docs/VIBECODING_RUNTIME_FLOW_SPEC.md` |
| **forbidden_scope** | runtime 配置、gateway、model_pool 修改 |
| **deliverables** | runtime flow 规范文档，包含：intake 格式、classify 规则、plan/recommend 模板、approval receipt 格式、role-node-model assignment record 格式、dispatch 协议、execution evidence 格式、validation 标准、report 模板 |
| **acceptance_criteria** | 每个 flow 阶段的 I/O 有明确定义；fail-closed 条件明确；与 §4 权限模型无冲突 |
| **final_verdict** | RUNTIME_FLOW_SPEC_APPROVED / RUNTIME_FLOW_SPEC_BLOCKED |

---

### 阶段 3：实现 role-node-model assignment gate

| 属性 | 内容 |
|------|------|
| **pre_audit** | runtime flow spec 已批准 |
| **allowed_scope** | 实现 assignment gate 代码/配置；修改 SOUL.md 或 MEMORY.md 反映 gate 逻辑（仅限 operator 批准范围内） |
| **forbidden_scope** | 未在 spec 中的 gate 逻辑；自动 bypass operator 的路径 |
| **deliverables** | 可执行的 assignment gate；gate 验证脚本；gate 测试（fail-closed 测试优先） |
| **acceptance_criteria** | 无 operator 批准时 gate 拒绝所有执行请求；operator 批准后 gate 允许仅批准范围内的执行；拒绝场景必须有明确 error message |
| **final_verdict** | ASSIGNMENT_GATE_PASS / ASSIGNMENT_GATE_FAIL |

---

### 阶段 4：中央模型池与 node-model matrix 同步整改

| 属性 | 内容 |
|------|------|
| **pre_audit** | assignment gate 已实现且通过验收 |
| **allowed_scope** | 修改 model_pool 配置；同步 node-model matrix；更新文档 |
| **forbidden_scope** | 引入无法溯源的模型配置；删除 operator 未批准的模型条目 |
| **deliverables** | 中央模型池声明；每个 node 的 node-model matrix（含 7 态：declared/synced/runtime-visible/env-loaded/wrapper-valid/model-call-verified/operator-approved） |
| **acceptance_criteria** | 中央模型池为唯一源；node-model matrix 区分所有 7 态；operator 批准的条目标记 operator-approved |
| **final_verdict** | MODEL_POOL_SYNC_PASS / MODEL_POOL_SYNC_FAIL |

---

### 阶段 5：runtime infrastructure readiness gate

| 属性 | 内容 |
|------|------|
| **pre_audit** | 模型池同步完成 |
| **allowed_scope** | 验证每个 node 的 runtime 环境：SSH reachability、env 加载状态、wrapper 校验、model call 验证（dry-run） |
| **forbidden_scope** | 修改生产配置；实际 production model 调用 |
| **deliverables** | readiness report：每个 node 的 env-loaded / wrapper-valid / model-call-verified 状态 |
| **acceptance_criteria** | 所有启用 node 通过 env-loaded + wrapper-valid；至少 1 个 node 通过 model-call-verified；失败 node 有 root cause |
| **final_verdict** | INFRA_READY / INFRA_PARTIAL / INFRA_FAIL |

---

### 阶段 6：public PR permission gate

| 属性 | 内容 |
|------|------|
| **pre_audit** | infrastructure readiness gate 通过 |
| **allowed_scope** | 实现 PR permission gate：operator 创建 PR 前必须检查公共仓库 merge 权限；公共 PR 必须先过权限 gate 才能创建 |
| **forbidden_scope** | 绕过 gate 直接 push/merge；假定 operator 一定有 merge 权限 |
| **deliverables** | permission gate 配置 + 验证脚本 + 文档 |
| **acceptance_criteria** | 无权限检查时不创建 PR；已知公共仓库无 merge 权限时 gate 阻止 PR；operator 可覆盖但必须有明确记录 |
| **final_verdict** | PERMISSION_GATE_PASS / PERMISSION_GATE_FAIL |

---

### 阶段 7：整改后灰度验收

| 属性 | 内容 |
|------|------|
| **pre_audit** | 阶段 0-6 全部通过 |
| **allowed_scope** | 端到端 runtime flow 灰度验收：从 intake 到 evidence/report 全流程 |
| **forbidden_scope** | merge 正式上线前的 production 暴露 |
| **deliverables** | 灰度验收报告，包含每个 flow 阶段的证据 |
| **acceptance_criteria** | 端到端 flow 完整的 9 步 traceable；无人工介入时 fail-closed 触发；每个输出有 operator approval / assignment / readiness / permission / evidence receipt 记录 |
| **final_verdict** | GRAY_ACCEPTANCE_PASS / GRAY_ACCEPTANCE_PARTIAL / GRAY_ACCEPTANCE_FAIL |

---

## 5. 最终验收标准

以下是 baseline02 整体的最终验收标准（跨阶段）：

| # | 标准 | 验证方式 |
|---|------|----------|
| 1 | 不得把 win+21bao 拆成两个 node | 架构文档一致性检查 |
| 2 | planner/explorer 等角色未获 operator 指定/批准不得启动 | assignment gate 验证 + 授权审计 |
| 3 | 中央模型池为唯一模型源 | model pool 配置审计 |
| 4 | node-model matrix 区分 7 态 | matrix 声明 + 状态逐条验证 |
| 5 | 公共 PR 先做权限 gate | permission gate 测试 |
| 6 | 每次作业输出五份 receipt：approval / assignment / readiness / permission / evidence | runtime flow 灰度验收报告验证 |

---

## 6. 风险管理

| 风险 | 缓解措施 |
|------|----------|
| 阶段间依赖阻塞前序未完成 | 坚持 sequential progression，不接受跳过 |
| 公共仓库权限变化 | permission gate 定期重检 |
| operator 审批疲劳 | 明确 "level 1-4D" 渐进授权，低风险可批 scope |
| 文档与实际行为偏离 | pre-audit 阶段保证文档一致性审计 |
| 模型可用性波动 | model-call-verified 状态定期刷新 |

---

## 7. 附录

### 7.1 与 baseline01 的关系

Baseline01 建立了 repo/gate 层面的规范（架构 taxonomy、role-node-model assignment gate、provider layering、effective model matrix、secrets 管理、gateway 纪律、报告规范、failure semantics、prompt handling）。

Baseline02 在此之上解决 **runtime flow 缺失** 问题，从 PR/gate 规范层推进到可执行的端到端 runtime flow。

### 7.2 版本记录

| 版本 | 日期 | 修改说明 |
|------|------|----------|
| v1.0 | 2026-06-30 | 初始版本，伴随 PR #276 创建 |
