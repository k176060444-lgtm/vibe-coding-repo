# Project Dashboard

**Last Updated**: 2026-06-24
**Baseline**: `github/main = c4b351e520acef39eb7061b8bcd3f2e8f999d715`
**Total PRs Merged**: 217
**Router Version**: v2.17.0

---

## System Status: 🟢 OPERATIONAL

| Metric | Status |
|--------|--------|
| **Main Sync** | ✅ YES (local github/main = remote) |
| **Test Suite** | ✅ 1135 passed / 6 pre-existing failures / 2 xfailed (1149 collected) |
| **Pre-existing Failures** | `scripts/test_ledger_gate_integration.py` (5), `scripts/test_repair_concurrency.py` (1) |
| **Known Flake** | `tests/test_v1172.py::test_corruption_latch_blocks` (ordering-dependent, passes standalone) |

---

## Active Freeze Markers

| Marker | Version | Date |
|--------|---------|------|
| `VIBE_CODING_REPORTING_CONSOLIDATION_MASTER_OK` | V1.21.25A | 2026-06-23 |
| `VIBE_CODING_V12126A_TEST_HARDENING_OK` | V1.21.26A | 2026-06-23 |

---

## Reporting Pipeline (V1.21.21–V1.21.25A)

| Component | Role | Frozen |
|-----------|------|--------|
| `vibe_run_report.py` (677 lines) | Reporting SSOT — single `run_report()` call | V1.21.25A |
| `vibe_report_export.py` (194 lines) | Export layer — reuses `render_dar_section`/`render_vdr_section` | V1.21.25A |
| `vibe_report_schema.py` (187 lines) | Schema validation v1.2.0 | V1.21.24 |
| `vibe_evidence_verifier.py` (433 lines) | 10-check verifier (Check 10: deferred registry) | V1.21.23 |
| `vibe_execution_evidence.py` (326 lines) | Evidence bundle creation | V1.21.22 |
| `vibe_operator_snapshot.py` (293 lines) | Operator-visible snapshot | V1.21.25A (dead-field fix) |

**Key invariant**: `run_report()` is the single source of truth for all reporting. Export, snapshot, and dashboard consume `run_report()` output — no independent re-collection.

---

## Gate Scripts

| Script | Lines | Purpose |
|--------|-------|---------|
| `execution_approval_gate.py` | 1586 | Execution approval binding — enforce explicit approval record |
| `conversational_intake_gate.py` | 1055 | Conversational intake — detect clarification vs approval |
| `git_pr_approval_gate.py` | 1113 | Git/PR state transitions — enforce merge/draft policy |
| `vibe_execution_gate.py` | 338 | Pre-execution admission check (ALLOW/REVIEW/BLOCK) |
| `vibe_report_status_gate.py` | 476 | Report status validation |
| `vibe_role_assignment_gate.py` | 733 | Role assignment enforcement |
| `vibe_merge_gate.py` | 582 | Merge gate precheck |

---

## Test Coverage (37 test files, 1149 tests collected)

| Test File | Tests | Covers |
|-----------|-------|--------|
| `test_execution_approval_gate.py` | 98 | Execution approval binding |
| `test_opencode_model_pool.py` | 96 | Model pool routing |
| `test_conversational_intake_gate.py` | 66 | Conversational intake gate |
| `test_windows_local_runner.py` | 66 | Windows local runner |
| `test_cluster_upgrade_resilience.py` | 58 | Cluster upgrade resilience |
| `test_role_assignment_gate.py` | 58 | Role assignment gate |
| `test_git_pr_approval_gate.py` | 57 | Git/PR approval gate |
| `test_worker_transport_routing.py` | 51 | Worker transport routing |
| `test_run_report_action_specific.py` | 44 | Run report action-specific sections |
| `test_remote_verification_gate.py` | 38 | Remote verification gate |
| `test_v1174.py` | 37 | V1.17.4 wiring evidence |
| `test_v1177_runtime_closure.py` | 36 | V1.17.7 runtime closure |
| `test_operator_snapshot.py` | 29 | **NEW** Operator snapshot (V1.21.26A) |
| `test_delegate_capability_gate.py` | 27 | Delegate capability gate |
| `test_v1172.py` | 27 | V1.17.2 corruption latch |
| `test_evidence_verifier_deferred.py` | 28 | Evidence verifier deferred (V1.21.23 + V1.21.26A edge cases) |
| `test_deferred_action_executor_integration.py` | 24 | Deferred action executor |
| `test_run_report_consolidation.py` | 24 | Run report consolidation (V1.21.25A) |
| `test_role_assignment_gate_integration.py` | 21 | Role assignment integration |
| `test_run_report_verifier_deferred.py` | 21 | Verifier deferred result report (V1.21.24) |
| `test_v1173.py` | 18 | V1.17.3 targeted closure |
| `test_execution_evidence_deferred.py` | 16 | Execution evidence deferred (V1.21.22) |
| `test_report_export_consolidation.py` | 16 | Report export consolidation (V1.21.25A) |
| `test_v1143.py` | 13 | V1.14.3 active-active |
| `test_v1131.py` | 11 | V1.13.1 iteration policy |
| `test_v114.py` | 10 | V1.14 worker lane |
| `test_v1142.py` | 9 | V1.14.2 gateway health |
| `test_report_schema.py` | 5 | Report schema validation |
| `test_vibe_iso_now.py` | 3 | ISO timestamp utility |

---

## Toolchain Scripts (72 total)

### Core Orchestration

| Script | Lines | Purpose |
|--------|-------|---------|
| `vibe_command_router.py` | 642 | Unified CLI entry point (v2.17.0) |
| `vibe_job_orchestrator.py` | 4037 | Job orchestration engine |
| `vibe_toolchain_lifecycle.py` | 3026 | Toolchain lifecycle management |
| `vibe_scheduler_policy.py` | 571 | Scheduler policy |
| `vibe_queue_advisor.py` | 727 | Queue lifecycle analysis |
| `vibe_dispatch_planner.py` | 231 | Dispatch suggestions |
| `vibe_batch_plan.py` | 272 | Batch execution plan |

### Reporting & Evidence

| Script | Lines | Purpose |
|--------|-------|---------|
| `vibe_run_report.py` | 677 | Reporting SSOT |
| `vibe_report_export.py` | 194 | Export layer |
| `vibe_report_schema.py` | 187 | Schema validation v1.2.0 |
| `vibe_evidence_verifier.py` | 433 | 10-check evidence verifier |
| `vibe_execution_evidence.py` | 326 | Evidence bundle creation |
| `vibe_operator_snapshot.py` | 293 | Operator snapshot |
| `vibe_release_notes.py` | 349 | Release notes / progress |

### Gates & Policy

| Script | Lines | Purpose |
|--------|-------|---------|
| `execution_approval_gate.py` | 1586 | Execution approval binding |
| `conversational_intake_gate.py` | 1055 | Conversational intake |
| `git_pr_approval_gate.py` | 1113 | Git/PR state policy |
| `vibe_execution_gate.py` | 338 | Pre-execution admission |
| `vibe_merge_gate.py` | 582 | Merge gate precheck |
| `vibe_report_status_gate.py` | 476 | Report status validation |
| `vibe_role_assignment_gate.py` | 733 | Role assignment |
| `vibe_quality_gate.py` | 348 | Quality gate |
| `vibe_resume_gate.py` | 298 | Resume gate |

### Worker & Executor

| Script | Lines | Purpose |
|--------|-------|---------|
| `vibe_worker_registry.py` | 758 | Worker registry |
| `vibe_worker_resilience.py` | 408 | Worker resilience |
| `vibe_worker_pool_health.py` | 217 | Worker pool health |
| `vibe_worker_capability.py` | 106 | Worker capability |
| `vibe_windows_local_runner.py` | 798 | Windows local runner |
| `vibe_windows_worker_policy.py` | 246 | Windows worker policy |
| `vibe_executor_adapter.py` | 435 | Executor adapter |
| `vibe_executor_sandbox.py` | 326 | Executor sandbox |
| `vibe_executor_recovery.py` | 333 | Executor recovery |
| `vibe_executor_control.py` | 264 | Executor control |
| `vibe_executor_unfreeze_checklist.py` | 328 | Executor unfreeze |

### Work Order & Registry

| Script | Lines | Purpose |
|--------|-------|---------|
| `vibe_workorder_registry.py` | 507 | Work order registry |
| `vibe_workorder_intake.py` | 429 | Work order intake |
| `vibe_workorder_packager.py` | 256 | Work order packager |
| `vibe_workorder_schema.py` | 165 | Work order schema |
| `vibe_workorder_validator.py` | 242 | Work order validator |
| `vibe_wo_compiler.py` | 377 | Work order compiler |
| `vibe_safe_executor.py` | 330 | Safe executor |

### Infrastructure

| Script | Lines | Purpose |
|--------|-------|---------|
| `vibe_external_authorized_push.py` | 752 | External authorized push |
| `vibe_batch_runner.py` | 1479 | Batch runner |
| `vibe_autonomous_merge.py` | 430 | Autonomous merge wrapper |
| `vibe_repo_status.py` | 591 | Repo status / job registry |
| `vibe_gateway_health.py` | 616 | Gateway health |
| `vibe_health_check.py` | 297 | Toolchain health |
| `vibe_health_snapshot.py` | 256 | Health snapshot |

---

## Recent Merges (Last 10)

| PR | Title | Date |
|----|-------|------|
| #217 | test(v1.21.26a): test hardening — operator_snapshot + verifier edge cases | 2026-06-23 |
| #216 | V1.21.25A Reporting Consolidation Master | 2026-06-23 |
| #215 | V1.21.24 Deferred Registry Verifier Result Report Visibility | 2026-06-23 |
| #214 | V1.21.23 Deferred Registry Evidence Verifier Awareness | 2026-06-23 |
| #213 | V1.21.22 Deferred Registry Evidence Export | 2026-06-23 |
| #212 | V1.21.21 Deferred Registry Report Visibility | 2026-06-23 |
| #211 | V1.21.20 Deferred Registry Hardening | 2026-06-23 |
| #210 | V1.21.19 Deferred Action Registry and Dry-Run Integration | 2026-06-23 |
| #209 | V1.21.18 Git PR Gate EAG Persistence and Ignore Policy | 2026-06-23 |
| #208 | V1.21.17 Orchestrator Pipeline Action-Specific Report Injection | 2026-06-23 |

---

## Quick Commands

```
# Morning check
python scripts/vibe_command_router.py snapshot --compact

# Health gate
python scripts/vibe_command_router.py health

# Plan next work
python scripts/vibe_command_router.py dispatch --compact

# Draft new Work Order
python scripts/vibe_command_router.py intake 'your requirement here'

# Progress report
python scripts/vibe_command_router.py release-notes --compact

# Run tests
python -m pytest tests/ -q
```

---

## Next Phase Recommendations

1. **Continue test hardening** for untested scripts (`vibe_queue_advisor.py`, `vibe_dispatch_planner.py`, `vibe_release_notes.py`)
2. **Integration tests** for intake→dispatch→batch-plan chain
3. **CI integration** when GitHub Actions available
4. **Cross-platform test parity** (Windows + Debian)

---

*Auto-generated dashboard. For details, see git log and individual script docstrings.*
