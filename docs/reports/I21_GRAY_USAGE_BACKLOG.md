# I21 — Gray Usage Issue Backlog

**Status:** Active backlog — single source of truth for stabilization
**Phase:** v1.21.33I21_GRAY_USAGE_ISSUE_TRIAGE_AND_STABILIZATION_PLAN
**Date:** 2026-06-27
**Author:** VibeDev Orchestrator (post-I15~I20 audit)
**Base HEAD:** `aa18a0014e3a2b0a7b6893aeb786017d3a5c0c6b`

---

## 1. Executive Summary

The VibeDev cluster (5bao/9bao/21bao) has completed I15~I20 infrastructure and RFC phases.
All model pool, worker registry, architecture contract, dispatch governance, and execution
intelligence foundations are frozen on main. The system is **technically operational** but
has never been exercised as a real multi-role runtime — only targeted smoke tests and
live-smoke verifications (I16E, I18).

This backlog captures **all known issues** discovered during I15~I20 audit, organized by
category. It distinguishes between:

| Type | Count | Action |
|------|:----:|--------|
|| **Blockers** (prevents gray usage) | 2 | Fix before first real dispatch |
|| **High priority** (significant risk) | 8 | Fix after blockers, before expansion |
|| **Medium priority** (quality gap) | 12 | Fix during stabilization |
|| **Low priority** (nice to have) | 8 | Fix as time permits |
|| **Technical debt** (no runtime impact) | 5 | Continuous improvement |
|| **Future enhancement** (new feature) | 6 | Deferred — not for current stabilization |
|| **Total (non-enhancement)** | **30** | — |

---

## 2. Issue Catalog

### 2.1 Architecture

| Field | Value |
|-------|-------|
| **issue_id** | ARCH-001 |
| **title** | Architecture contract has no runtime enforcement |
| **description** | `vibe_architecture_contract.py` validates static config (transport, SSH username) but does not audit actual SSH usage at runtime. A rogue agent could bypass the registry and SSH directly with username=kk — no gate prevents this. |
| **current_status** | known |
| **severity** | blocker |
| **reproducibility** | always (missing check) |
| **affected_phase** | I15 |
| **proposed_fix_phase** | I22 |
| **requires_model_call** | no |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | ARCH-002 |
| **title** | 21bao health_status permanently UNKNOWN in route-all |
| **description** | All route-all node_attribution entries show `health_status=UNKNOWN`. No actual health probe runs. 21bao capabilities list exists but no mechanism confirms they're real. |
| **current_status** | open |
| **severity** | medium |
| **reproducibility** | always |
| **affected_phase** | I15 |
| **proposed_fix_phase** | I23 |
| **requires_model_call** | no |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | ARCH-003 |
| **title** | Manual-only worker flag has no enforcement |
| **description** | `vibe_worker_registry.py` supports `manual_only=True` flag but no code path enforces it — a dispatcher can still select a manual-only worker. |
| **current_status** | known |
| **severity** | high |
| **reproducibility** | always (missing gate) |
| **affected_phase** | I15 |
| **proposed_fix_phase** | I22 |
| **requires_model_call** | no |
| **requires_node_change** | no |

---

### 2.2 Worker / Registry

| Field | Value |
|-------|-------|
| **issue_id** | WRKR-001 |
| **title** | Worker registry has no reachability probe |
| **description** | `vibe_worker_registry.py --health-check` validates config but does not test actual SSH reachability to 5bao/9bao or local-exec capability on 21bao. A worker can be marked ONLINE while being unreachable. |
| **current_status** | known |
| **severity** | high |
| **reproducibility** | always |
| **affected_phase** | I15 |
| **proposed_fix_phase** | I22 |
| **requires_model_call** | no |
| **requires_node_change** | yes |

| Field | Value |
|-------|-------|
| **issue_id** | WRKR-002 |
| **title** | No automated recovery on worker failure |
| **description** | If 5bao or 9bao's SSH connection fails mid-execution, there is no auto-retry, no failover to the other worker, and no notification. The system stalls. |
| **current_status** | known |
| **severity** | high |
| **reproducibility** | not applicable |
| **affected_phase** | I15 |
| **proposed_fix_phase** | I23 |
| **requires_model_call** | no |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | WRKR-003 |
| **title** | SSH credential key path empty in registry |
| **description** | 5bao/9bao entries in `DEFAULT_WORKERS` have `ssh_key_path=""`, relying on SSH config (~/.ssh/config) instead of explicit path. This works but violates auditability requirement. |
| **current_status** | known |
| **severity** | low |
| **reproducibility** | always |
| **affected_phase** | I15 |
| **proposed_fix_phase** | I24 |
| **requires_model_call** | no |
| **requires_node_change** | no |

---

### 2.3 Dispatch

| Field | Value |
|-------|-------|
| **issue_id** | DSP-001 |
| **title** | Dispatch manifest is RFC-only — no executable schema |
| **description** | I19/I19A define dispatch manifest concepts in RFC documents only. There is no `dispatch_manifest_schema.yaml`, no dataclass, no validation code. Every phase re-invents the manifest YAML structure. |
| **current_status** | open |
| **severity** | medium |
| **reproducibility** | always |
| **affected_phase** | I19 |
| **proposed_fix_phase** | I24 |
| **requires_model_call** | no |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | DSP-002 |
| **title** | route-all has no operator-approved checkpoint |
| **description** | route-all output is a machine-generated recommendation. There is no gate that forces operator approval before route-all's output is used for dispatch. An agent can re-run route-all mid-phase and silently change recommendations. |
| **current_status** | open |
| **severity** | blocker |
| **reproducibility** | always (missing gate) |
| **affected_phase** | I19 |
| **proposed_fix_phase** | I22 |
| **requires_model_call** | no |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | DSP-003 |
| **title** | Fallback policy defined but not enforced at runtime |
| **description** | Each model in model_pool.yaml has `fallback_allowed` field, but no runtime code checks this flag when a worker does a model fallback. The execution report may document it, but no gate blocks it. |
| **current_status** | known |
| **severity** | high |
| **reproducibility** | always (missing gate) |
| **affected_phase** | I19 |
| **proposed_fix_phase** | I23 |
| **requires_model_call** | no |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | DSP-004 |
| **title** | No planned-vs-actual audit at execution time |
| **description** | I19's dispatch manifest includes `execution_result.planned_vs_actual_ok` but no code compares planned vs actual. The field is manually set. After execution, there's no automated gate verifying that the manifest matches what happened. |
| **current_status** | open |
| **severity** | medium |
| **reproducibility** | always |
| **affected_phase** | I19 |
| **proposed_fix_phase** | I24 |
| **requires_model_call** | no |
| **requires_node_change** | no |

---

### 2.4 Model Pool

| Field | Value |
|-------|-------|
| **issue_id** | POOL-001 |
| **title** | Extra visible models not blocked from alias resolution |
| **description** | 5 opencode-go extra visible models (deepseek-v4-pro, kimi-k2.7-code, minimax-m2.7, minimax-m3, qwen3.6-plus) exist in provider API output but are NOT in central pool. If a user types `opencode-go-minimax-m3`, the alias resolver could match it even though it's not a controlled model. |
| **current_status** | verified |
| **severity** | high |
| **reproducibility** | always (resolution depends on query) |
| **affected_phase** | I16 |
| **proposed_fix_phase** | I22 |
| **requires_model_call** | no |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | POOL-002 |
| **title** | model_pool.yaml has id field inconsistency |
| **description** | model_pool.yaml uses `id` as key, but some newer test files look for `model_id`. While the field value is the same, the naming inconsistency causes confusion and the YAML lacks a formal schema definition. |
| **current_status** | known |
| **severity** | low |
| **reproducibility** | always |
| **affected_phase** | I15 |
| **proposed_fix_phase** | I24 |
| **requires_model_call** | no |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | POOL-003 |
| **title** | Model pool has no integrity signature |
| **description** | model_pool.yaml can be edited without leaving an audit trail of changes. There's no integrity check (hash/signature) that would detect unauthorized modifications. |
| **current_status** | known |
| **severity** | low |
| **reproducibility** | always |
| **affected_phase** | I15 |
| **proposed_fix_phase** | I25 |
| **requires_model_call** | no |
| **requires_node_change** | no |

---

### 2.5 Runtime Sync

| Field | Value |
|-------|-------|
| **issue_id** | RSYNC-001 |
| **title** | Node opencode.jsonc not periodically synced with central pool |
| **description** | After I16A/D/E, node local config was manually synced via SSH. There is no periodic drift detection — if central pool adds/removes a model, node config doesn't auto-update. |
| **current_status** | known |
| **severity** | medium |
| **reproducibility** | always |
| **affected_phase** | I16 |
| **proposed_fix_phase** | I23 |
| **requires_model_call** | no |
| **requires_node_change** | yes |

| Field | Value |
|-------|-------|
| **issue_id** | RSYNC-002 |
| **title** | Rollback requires manual SSH per node |
| **description** | Rollback plan exists as documentation (I16 audit record) but no automated script executes it. Each node rollback requires manual SSH + cp commands. |
| **current_status** | known |
| **severity** | medium |
| **reproducibility** | not applicable |
| **affected_phase** | I16 |
| **proposed_fix_phase** | I23 |
| **requires_model_call** | no |
| **requires_node_change** | yes |

---

### 2.6 OpenCode Runtime

| Field | Value |
|-------|-------|
| **issue_id** | OCR-001 |
| **title** | Only 2/8 opencode-go models enabled — 6 verified but idle |
| **description** | All 8 opencode-go models were live-verified 16/16 PASS (I16E). Only deepseek-v4-flash (canary) and mimo-v2.5 are enabled. The remaining 6 (glm-5-2, glm-5-1, kimi-k2-6, qwen3.7-max, qwen3.7-plus, mimo-v2.5-pro) are fully tested but dormant. |
| **current_status** | open |
| **severity** | low |
| **reproducibility** | always |
| **affected_phase** | I16-I18 |
| **proposed_fix_phase** | I24 |
| **requires_model_call** | yes |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | OCR-002 |
| **title** | 0/5 opencode (free/native) models enabled |
| **description** | The 5 opencode free models (deepseek-v4-flash-free, mimo-v2.5-free, nemotron-3-ultra-free, north-mini-code-free, big-pickle) have never been enabled or tested at runtime. They are defined in central pool with enabled=false but no gate has verified they work. |
| **current_status** | open |
| **severity** | medium |
| **reproducibility** | always |
| **affected_phase** | I15 |
| **proposed_fix_phase** | I24 |
| **requires_model_call** | yes |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | OCR-003 |
| **title** | No runtime model discovery cache |
| **description** | Every `opencode models/list` call hits the provider API. With 3 nodes each potentially calling this on startup, there is no caching layer. This is acceptable at small scale but will become a bottleneck. |
| **current_status** | open |
| **severity** | low |
| **reproducibility** | always |
| **affected_phase** | I16 |
| **proposed_fix_phase** | future |
| **requires_model_call** | no |
| **requires_node_change** | no |

---

### 2.7 Git / PR Workflow

| Field | Value |
|-------|-------|
| **issue_id** | GIT-001 |
| **title** | PR base ref consistently lags behind main |
| **description** | Every PR created during I15~I20 has baseRefOid behind github/main (I20 base=76e1e03 vs main=809fa66). No auto-update workflow exists — requires manual `git merge-tree` verification each time. |
| **current_status** | verified |
| **severity** | medium |
| **reproducibility** | always |
| **affected_phase** | I15-I20 |
| **proposed_fix_phase** | I23 |
| **requires_model_call** | no |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | GIT-002 |
| **title** | No automated branch cleanup after merge |
| **description** | After merge, local and remote PR branches remain indefinitely. No policy or cleanup script removes them. Over time this accumulates stale branches. |
| **current_status** | known |
| **severity** | low |
| **reproducibility** | always |
| **affected_phase** | I15-I20 |
| **proposed_fix_phase** | I25 |
| **requires_model_call** | no |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | GIT-003 |
| **title** | GitHub PR mutation detection is fragile |
| **description** | Current approach uses `git show` from multiple remote refs to detect PR mutation. This is fragile — depends on GitHub's ref update timing. A more robust approach would use `gh pr diff` or API-based checksums. |
| **current_status** | known |
| **severity** | low |
| **reproducibility** | intermittent |
| **affected_phase** | I18 |
| **proposed_fix_phase** | future |
| **requires_model_call** | no |
| **requires_node_change** | no |

---

### 2.8 Windows Compatibility

| Field | Value |
|-------|-------|
| **issue_id** | WIN-001 |
| **title** | python3 not available on Windows — scripts fail |
| **description** | Many scripts and tests use `python3` which does not exist on Windows (only `python`). This causes 13 pre-existing pytest failures. Each new contributor must know to use `python` not `python3`. |
| **current_status** | verified |
| **severity** | high |
| **reproducibility** | always |
| **affected_phase** | I15-I20 |
| **proposed_fix_phase** | I22 |
| **requires_model_call** | no |
| **requires_node_change** | no (local fix) |

| Field | Value |
|-------|-------|
| **issue_id** | WIN-002 |
| **title** | 21bao has no operational worker runtime |
| **description** | 21bao runs the Hermes orchestrator but has never been used as a worker for real opencode tasks. Its capabilities (implementer, reviewer, smoke) are declared but untested. The Windows local runner (`vibe_windows_local_runner.py`) exists but has never been exercised with a real dispatch. |
| **current_status** | open |
| **severity** | high |
| **reproducibility** | not applicable |
| **affected_phase** | I15 |
| **proposed_fix_phase** | I23 |
| **requires_model_call** | yes (test) |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | WIN-003 |
| **title** | MSYS/POSIX path translation issues |
| **description** | Git Bash (MSYS) auto-translates `/c/Users/` paths, causing intermittent failures when Python or scripts expect `C:/Users/` or vice versa. No standardized path handling convention. |
| **current_status** | known |
| **severity** | medium |
| **reproducibility** | intermittent |
| **affected_phase** | I15-I20 |
| **proposed_fix_phase** | I23 |
| **requires_model_call** | no |
| **requires_node_change** | no |

---

### 2.9 Reporting

| Field | Value |
|-------|-------|
| **issue_id** | RPT-001 |
| **title** | Phase reports are free-form YAML — no schema |
| **description** | Every phase report uses different YAML structure. Fields like `final_verdict`, `gate_results`, `secret_check` appear in most reports but with different nesting, field names, and formats. No schema validation exists. |
| **current_status** | known |
| **severity** | medium |
| **reproducibility** | always |
| **affected_phase** | I15-I20 |
| **proposed_fix_phase** | I23 |
| **requires_model_call** | no |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | RPT-002 |
| **title** | Secret check depends on manual regex — easy to bypass |
| **description** | Secret leak check runs inline regex patterns from Python scripts. There is no automated secret scanning tool integrated (e.g., trufflehog, gitleaks). New secret formats are not detected until patterns are manually updated. |
| **current_status** | known |
| **severity** | medium |
| **reproducibility** | always |
| **affected_phase** | I15-I20 |
| **proposed_fix_phase** | I23 |
| **requires_model_call** | no |
| **requires_node_change** | no |

---

### 2.10 Test Infrastructure

| Field | Value |
|-------|-------|
| **issue_id** | TEST-001 |
| **title** | Pre-existing test failures not systematically tracked |
| **description** | 13 pre-existing pytest failures exist on Windows (python3 not found, 21bao no models, flaky timeouts). Each phase report manually exempts them as "pre-existing" but there is no automated classification or regression tracking. |
| **current_status** | verified |
| **severity** | medium |
| **reproducibility** | always (13 tests always fail on Windows) |
| **affected_phase** | I15-I20 |
| **proposed_fix_phase** | I22 |
| **requires_model_call** | no |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | TEST-002 |
| **title** | No runtime/integration test coverage |
| **description** | All existing tests (I15~I20) verify document structure, config, and static properties. There are no integration tests that exercise actual worker dispatch, opencode calls, or multi-node coordination. |
| **current_status** | open |
| **severity** | high |
| **reproducibility** | not applicable |
| **affected_phase** | I15-I20 |
| **proposed_fix_phase** | I23 |
| **requires_model_call** | yes |
| **requires_node_change** | yes |

---

### 2.11 Documentation

| Field | Value |
|-------|-------|
| **issue_id** | DOC-001 |
| **title** | No operator playbook for common scenarios |
| **description** | There is no single document explaining how an operator should handle common scenarios: PR merge gate, live smoke, rollback, node sync, model enable. Each operator must read multiple RFCs and phase reports to reconstruct the workflow. |
| **current_status** | open |
| **severity** | medium |
| **reproducibility** | not applicable |
| **affected_phase** | I15-I20 |
| **proposed_fix_phase** | I24 |
| **requires_model_call** | no |
| **requires_node_change** | no |

| Field | Value |
|-------|-------|
| **issue_id** | DOC-002 |
| **title** | Worker evidence template lacks validation |
| **description** | `docs/reports/worker-evidence-template.md` defines evidence fields but no code validates that submitted evidence conforms to the template. Evidence can be incomplete or malformed. |
| **current_status** | known |
| **severity** | low |
| **reproducibility** | always |
| **affected_phase** | I15 |
| **proposed_fix_phase** | future |
| **requires_model_call** | no |
| **requires_node_change** | no |

---

### 2.12 Future Enhancement (Deferred)

| Field | Value |
|-------|-------|
| **issue_id** | ENH-001 |
| **title** | Execution record persistence layer |
| **description** | I20 defines Execution Record Schema but no writer/reader implementation. |
| **current_status** | open |
| **severity** | low |  | **proposed_fix_phase** | future |

| Field | Value |
|-------|-------|
| **issue_id** | ENH-002 |
| **title** | Cost / pricing registry |
| **description** | No cost tier tracking for models. Cost-aware routing requires this. |
| **current_status** | open |
| **severity** | low |
| **proposed_fix_phase** | future |

| Field | Value |
|-------|-------|
| **issue_id** | ENH-003 |
| **title** | Recommendation engine |
| **description** | Model/role recommendation based on execution history. Requires I20 records. |
| **current_status** | open |
| **severity** | low |
| **proposed_fix_phase** | future |

| Field | Value |
|-------|-------|
| **issue_id** | ENH-004 |
| **title** | Cross-model reproducibility hashing |
| **description** | prompt_hash, input_hash, approval_hash for full reproducibility. |
| **current_status** | open |
| **severity** | low |
| **proposed_fix_phase** | future |

| Field | Value |
|-------|-------|
| **issue_id** | ENH-005 |
| **title** | Multi-cluster federation |
| **description** | Coordinating multiple VibeDev clusters. Out of scope for current deployment. |
| **current_status** | open |
| **severity** | low |
| **proposed_fix_phase** | future |

| Field | Value |
|-------|-------|
| **issue_id** | ENH-006 |
| **title** | Automated model ranking / scoring |
| **description** | I20 Evaluation Schema implementation with real model scoring. |
| **current_status** | open |
| **severity** | low |
| **proposed_fix_phase** | future |

---

## 3. Priority Matrix

```
SEVERITY     | Blockers  | High      | Medium     | Low
-------------|-----------|-----------|------------|-----------
Count        | 2         | 8         | 12         | 8
Types        | ARCH-001  | ARCH-003  | ARCH-002   | WRKR-003
             | DSP-002   | WRKR-001  | DSP-001    | POOL-002
             |           | WRKR-002  | DSP-004    | POOL-003
             |           | DSP-003   | RSYNC-001  | OCR-001
             |           | POOL-001  | RSYNC-002  | OCR-003
             |           | WIN-001   | OCR-002    | GIT-002
             |           | WIN-002   | GIT-001    | GIT-003
             |           | TEST-002  | WIN-003    | DOC-002
             |           |           | RPT-001    |
             |           |           | RPT-002    |
             |           |           | TEST-001   |
             |           |           | DOC-001    |
```

**Known Blockers (must fix before first real dispatch):**
1. **ARCH-001** — Architecture contract has no runtime enforcement
2. **DSP-002** — route-all has no operator-approved checkpoint

**High Priority (significant risk to gray usage):**
1. ARCH-003 — Manual-only worker flag has no enforcement
2. WRKR-001 — Worker registry has no reachability probe
3. WRKR-002 — No automated recovery on worker failure
4. DSP-003 — Fallback policy not enforced at runtime
5. POOL-001 — Extra visible models not blocked from alias resolution
6. WIN-001 — python3 not available on Windows (13 pre-existing failures)
7. WIN-002 — 21bao has no operational worker runtime
8. TEST-002 — No runtime/integration test coverage

---

## 4. Recommended Fix Order

| Priority | Phase | Issues | Category | Effort |
|:--------:|:-----:|--------|----------|:------:|
| 1 | **I22** | ARCH-001, ARCH-003, WRKR-001, DSP-002, POOL-001, WIN-001, TEST-001 | Core gates + hardening | Medium |
| 2 | **I23** | ARCH-002, WRKR-002, DSP-003, RSYNC-001, RSYNC-002, GIT-001, WIN-002, WIN-003, RPT-001, RPT-002, TEST-002 | Runtime + reporting | Large |
| 3 | **I24** | WRKR-003, DSP-001, DSP-004, POOL-002, OCR-001, OCR-002, DOC-001 | Polish + documentation | Medium |
| 4 | **I25** | POOL-003, GIT-002 | Low-priority hardening | Small |
| 5 | **future** | ENH-001 through ENH-006, GIT-003, OCR-003, DOC-002 | New features | Future |

### Phase I22 — Core Stabilization (gates + hardening)
- ARCH-001: Add runtime SSH audit to architecture contract
- ARCH-003: Enforce manual_only flag in dispatcher
- WRKR-001: Add SSH reachability probe to registry health check
- DSP-002: Add operator approval gate before route-all dispatch
- POOL-001: Block extra visible models in alias resolver
- WIN-001: Fix python3→python on Windows (shebang/script fixes)
- TEST-001: Systematically classify pre-existing failures

### Phase I23 — Runtime Reliability
- ARCH-002: Add health probe mechanism for all nodes
- WRKR-002: Implement auto-retry / failover on worker failure
- DSP-003: Enforce fallback_allowed at runtime
- RSYNC-001: Add periodic node config drift detection
- RSYNC-002: Automate rollback script
- GIT-001: Implement auto-update workflow for PR base ref
- WIN-002: Test 21bao as worker with opencode dispatch
- WIN-003: Standardize path handling
- RPT-001: Define phase report schema
- RPT-002: Integrate automated secret scanner
- TEST-002: Add first runtime integration test

### Phase I24 — Polish
- WRKR-003: Set explicit SSH key path in registry
- DSP-001: Formal dispatch manifest schema + validation
- DSP-004: Implement planned-vs-actual audit
- POOL-002: Fix id→model_id consistency
- OCR-001: Enable more opencode-go models
- OCR-002: Verify/smoke-test opencode free models
- DOC-001: Write operator playbook

---

## 5. Technical Debt Summary

| ID | Title | Category | Effort |
|----|-------|----------|:------:|
| POOL-003 | Model pool has no integrity signature | model-pool | Small |
| GIT-002 | No automated branch cleanup | git | Small |
| GIT-003 | GitHub PR mutation detection fragile | git | Medium |
| WIN-003 | MSYS path translation issues | windows | Medium |
| DOC-002 | Worker evidence template lacks validation | docs | Small |

## 6. Future Enhancement Summary

| ID | Title | Category | Effort |
|----|-------|----------|:------:|
| ENH-001 | Execution record persistence layer | execution-intel | Large |
| ENH-002 | Cost / pricing registry | model-pool | Medium |
| ENH-003 | Recommendation engine | dispatch | Large |
| ENH-004 | Cross-model reproducibility hashing | execution-intel | Large |
| ENH-005 | Multi-cluster federation | cluster | Extra Large |
| ENH-006 | Automated model ranking / scoring | execution-intel | Large |
| OCR-003 | Runtime model discovery cache | opencode | Medium |

---

## 7. Backlog Maintenance

This backlog is the **single source of truth** for all ongoing and planned work.
- As issues are fixed, their `current_status` should be updated to `resolved`.
- New issues discovered during gray usage should be added to this document.
- No issue should be removed — resolved issues remain as audit trail.
- The `proposed_fix_phase` is a recommendation only — operator decides actual phase assignment.
