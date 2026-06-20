# V1.20.17 Cluster Upgrade Resilience Doctrine Report

**Version:** 1.20.17
**Date:** 2026-06-20
**Status:** Architecture policy + simulation framework
**Main baseline:** f527b36b24b961ea9567f7d4f9ebac8ceef389a1

---

## 1. ARCHITECTURE_SUMMARY

VibeDev 小集群升级/降级鲁棒性架构基础已建立。包含：

| 组件 | 文件 | 作用 |
|---|---|---|
| Doctrine | `docs/CLUSTER_UPGRADE_RESILIENCE_DOCTRINE.md` | 8 条核心原则 + 生命周期 + 反模式 |
| Manifest | `scripts/cluster_component_manifest.py` | 10 组件清单、升级分类、版本化布局 |
| Contract | `scripts/cluster_upgrade_contract.py` | 协议/字段/门禁语义验证，fail-closed |
| Simulator | `scripts/cluster_upgrade_simulate.py` | dry-run promotion/rollback 模拟 |
| Tests | `tests/test_cluster_upgrade_resilience.py` | 58 个测试覆盖所有核心场景 |

## 2. UPGRADE_DOCTRINE

8 条核心原则：
1. **程序与状态分离** — 可替换程序 ≠ 持久状态
2. **版本并行** — releases/current/previous/candidate，不覆盖安装
3. **Promotion Gate** — health+contract+safety 全 PASS 才允许切换
4. **Rollback 安全** — previous/current 可恢复，不丢 evidence/state
5. **Feature Flag/Manual-Only** — 新能力默认 disabled/manual-only
6. **Fail-Closed but Recoverable** — 升级失败不 auto dispatch，但保留 health/rollback
7. **兼容性 Contract** — controller_protocol/registry_schema/runner_protocol/approval_gate/routing_schema
8. **Per-Component 升级分类** — platform/runtime/workflow/config/system

## 3. COMPONENT_UPGRADE_CLASSIFICATION

| 组件 | 升级类 | Rollback | State 路径 |
|---|---|---|---|
| Hermes controller | platform | binary+config backup | $HERMES_PROFILE/ |
| OpenCode engine (5bao) | runtime | previous binary | $WORKER_STATE/5bao/ |
| OpenCode engine (9bao) | runtime | previous binary | $WORKER_STATE/9bao/ |
| OpenCode engine (21bao) | runtime | previous binary | $WORKER_STATE/21bao/ |
| Windows local runner | workflow | git revert | worktrees, evidence, logs |
| Debian SSH runner | workflow | git revert | worktrees, evidence, logs |
| Worker registry | workflow | git revert | in-memory + config |
| Scheduler policy | workflow | git revert | routing + lock state |
| Model provider config | config | env file backup | opencode config |
| Network fallback | config | config file backup | registry config |

## 4. PROGRAM_STATE_SEPARATION_MODEL

```
[Replaceable Programs]          [Persistent State]
├── Hermes binary               ├── ~/.hermes/profiles/
├── OpenCode binary             ├── worktrees/
├── Runner scripts              ├── evidence/
├── Scheduler/Registry code     ├── logs/
└── Runtime deps                ├── approval records
                                ├── config files
                                └── locks/queue
```

**Rule:** 升级只替换程序；状态迁移需要独立 operator approval。

## 5. VERSIONED_RELEASE_LAYOUT_MODEL

```
<component>/
  releases/
    <version>/           # immutable after install
    current -> <version>   # active
    previous -> <version>  # rollback target
    candidate -> <version> # under validation
```

- candidate 验证后 promotion
- promotion: candidate→current, current→previous
- rollback: previous→current

## 6. PROMOTION_AND_ROLLBACK_MODEL

### Promotion Gates

| Gate | 阻断条件 |
|---|---|
| Health PASS | health_probe ≠ PASS |
| Contract PASS | protocol/schema incompatible |
| Safety PASS | secret exposure / unauthorized state mutation |
| Rollback Target | previous missing or corrupt |
| Operator Approval | no valid 40-char SHA approval |

### Rollback Invariants

- Rollback 不得删除 evidence/logs/state/approval
- Rollback target 必须是 known-good version
- Rollback 后保留 re-promote 能力

## 7. FAIL_CLOSED_RECOVERABLE_MODEL

| 失败模式 | 行为 |
|---|---|
| Unknown protocol | REJECT dispatch |
| Missing required field | REJECT |
| Health FAIL | BLOCK promotion |
| Contract FAIL | BLOCK promotion |
| Upgrade crash | Preserve current, log, allow retry |
| Provider unavailable | Log, cooldown, manual override |

**Recoverable:** 任何失败后保留 health/status/reconcile/rollback/manual override。

## 8. COMPATIBILITY_CONTRACT_MODEL

| Contract | 版本 |
|---|---|
| controller_protocol | 1.0 |
| worker_registry_schema | 1.1 |
| runner_protocol | 1.0 |
| approval_gate_semantics | 1.1 |
| scheduler_routing_schema | 1.0 |

Unknown schema/protocol → fail-closed, do not dispatch。

## 9. TEST_MATRIX

| 测试类 | 数量 | 覆盖范围 |
|---|---|---|
| TestComponentManifest | 10 | 清单完整性、21bao 安全、无 secret/IP/domain |
| TestUpgradeContract | 21 | 字段验证、contract type、gate 语义、SHA binding |
| TestPromotionContract | 6 | promotion 门禁、rollback target、operator approval |
| TestPromotionSimulation | 8 | promotion 模拟、各 gate 阻断、state mutation |
| TestRollbackSimulation | 4 | rollback 模拟、preserve state、missing target |
| Test21baoSafety | 2 | 21bao disabled + manual_only + not auto-scheduled |
| TestApprovalGateSHABinding | 3 | 40-char hex SHA required |
| TestVersionChangeSimulation | 2 | OpenCode/Hermes version change no state mutation |
| TestMaintenanceMode | 2 | maintenance blocks dispatch, health allowed |
| **总计** | **58** | |

### Self-Check Summary

| 脚本 | Self-Check |
|---|---|
| cluster_component_manifest.py | 8/8 PASS |
| cluster_upgrade_contract.py | 14/14 PASS |
| cluster_upgrade_simulate.py | 12/12 PASS |

### Regression (existing)

| 脚本 | Self-Check |
|---|---|
| vibe_worker_registry.py | 15/15 PASS |
| vibe_scheduler_policy.py | 10/10 PASS |
| vibe_windows_local_runner.py | 10/10 PASS |

### Unicode Attestation (V1.20.17B)

| 文件 | BOM | ZWSP/ZWNJ/ZWJ/LRM/RLM | LRE/RLE/PDF/LRO/RLO | LRI/RLI/FSI/PDI | 其他控制符 | 结果 |
|---|---|---|---|---|---|---|
| docs/CLUSTER_UPGRADE_RESILIENCE_DOCTRINE.md | 0 | 0 | 0 | 0 | 0 | CLEAN ✅ |
| scripts/cluster_component_manifest.py | 0 | 0 | 0 | 0 | 0 | CLEAN ✅ |
| scripts/cluster_upgrade_contract.py | 0 | 0 | 0 | 0 | 0 | CLEAN ✅ |
| scripts/cluster_upgrade_simulate.py | 0 | 0 | 0 | 0 | 0 | CLEAN ✅ |
| tests/test_cluster_upgrade_resilience.py | 0 | 0 | 0 | 0 | 0 | CLEAN ✅ |
| docs/reports/V1217_...REPORT.md | 0 | 0 | 0 | 0 | 0 | CLEAN ✅ |
| **总计** | **0** | **0** | **0** | **0** | **0** | **ALL CLEAN** |

> GitHub diff hidden/bidi Unicode warning 为误报（CRLF line endings 触发）。逐文件 codepoint scan 全部 CLEAN。

### Test Count Reconciliation (V1.20.17B)

| 口径 | 值 |
|---|---|
| SELF_CHECK_NEW | 34 (8 + 14 + 12) |
| SELF_CHECK_EXISTING | 35 (15 + 10 + 10) |
| **SELF_CHECK_TOTAL** | **69** |
| **SELF_CHECK_PASSED** | **69** |
| **PYTEST_COLLECTED** | **58** |
| **PYTEST_PASSED** | **58** |
| **GRAND_TOTAL** | **127** |
| **GRAND_PASSED** | **127** |

## 10. SAFETY_SCAN_RESULT

| 检查项 | 结果 |
|---|---|
| 21bao enabled | **False** ✅ |
| 21bao manual_only | **True** ✅ |
| 21bao auto-schedule excluded | **True** ✅ |
| secrets/tokens in new files | CLEAN ✅ |
| private keys | CLEAN ✅ |
| real IP addresses | CLEAN ✅ (alias only) |
| real domains (.top/.vip) | CLEAN ✅ |
| raw opencode.env | CLEAN ✅ |
| Hermes profile mutation | NONE ✅ |
| provider/env mutation | NONE ✅ |
| runtime mutation | NONE ✅ |
| real upgrade executed | NONE ✅ |
| live model calls | NONE ✅ |

## 11. MODEL_LEDGER

| node | planned_model | actual_model | provider | call_count | fallback | rate_limit | exit_code | final_status |
|---|---|---|---|---|---|---|---|---|
| n/a | N/A | N/A | N/A | 0 | false | false | 0 | PASS |

> 注：本轮为纯架构/policy/simulation 代码，无 model calls。

## 12. NODE_MODEL_SUMMARY

| node | opencode_version | total_calls | successful | failed | fallback | rate_limit | cooldown_state |
|---|---|---|---|---|---|---|---|
| n/a | 1.17.8 | 0 | 0 | 0 | 0 | 0 | none |

## 13. RATE_LIMIT_EVENT_LEDGER

（空 — 无 rate limit events）

## 14. NEXT_IMPLEMENTATION_PLAN

| 阶段 | 内容 | 依赖 |
|---|---|---|
| Phase 1 | 集成 cluster_component_manifest 到现有 self-check 流程 | 本 PR merge |
| Phase 2 | 升级/降级 real dry-run with 5bao OpenCode candidate | Operator approval + 5bao access |
| Phase 3 | Promotion gate 集成到 merge gate pipeline | Phase 2 |
| Phase 4 | Rollback 实战演练 (OpenCode 1.17.8→1.17.4→1.17.8) | Phase 3 + Operator approval |
| Phase 5 | 21bao graduation: enabled=true, manual_only=true | Phase 4 + Operator approval |

---

**runtime_code_changed = false** ✅
**workflow_code_changed = true** ✅ (新增 policy/simulation 脚本)
**real_upgrade_executed = false** ✅
**live_model_calls = false** ✅
