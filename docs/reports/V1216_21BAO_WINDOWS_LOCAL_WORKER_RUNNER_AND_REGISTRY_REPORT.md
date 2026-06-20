# V1.20.16 — 21bao Windows Local Worker Runner and Transport Registry Support

**Date:** 2026-06-20
**Branch:** feat/v1216-21bao-windows-local-worker
**Version:** vibe_worker_registry v1.3.0, vibe_scheduler_policy v1.3.0

## Changed Files

| File | Action | Description |
|------|--------|-------------|
| `scripts/vibe_worker_registry.py` | Modified | Added transport/enabled/manual_only fields to WorkerNode; added 21bao to DEFAULT_WORKERS; added to_dict/from_dict serialization; added manual_only filtering to available_workers/select_worker; bumped to v1.3.0; added self-check scenarios 11-15 |
| `scripts/vibe_scheduler_policy.py` | Modified | Added transport-aware routing (_get_transport_filter, get_eligible_candidates transport filtering); unknown transport fail-closed; manual_only filtering in _filter_by_capabilities; added self-check scenarios 8-10 |
| `scripts/vibe_windows_local_runner.py` | Created | Windows local job runner for 21bao; supports timeout, cancellation (taskkill), dry-run, no-op fixture; path allowlist (D:\\, E:\\ allowed; controller repo blocked); job lock; never writes to controller repo |
| `tests/test_windows_local_runner.py` | Created | Tests for dry-run mode, path allowlist, timeout fixture, evidence/log path separation, no controller repo writes |
| `tests/test_worker_transport_routing.py` | Created | Tests for WorkerNode serialization, transport routing, manual_only filtering, disabled worker filtering, unknown transport fail-closed, 21bao not auto-scheduled |
| `docs/reports/V1216_21BAO_WINDOWS_LOCAL_WORKER_RUNNER_AND_REGISTRY_REPORT.md` | Created | This report |

## Test Matrix

| Test File | Test Class | Tests | Description |
|-----------|------------|-------|-------------|
| `test_windows_local_runner.py` | TestPathAllowlist | 5 | D/E allowed, C blocked, controller repo blocked |
| `test_windows_local_runner.py` | TestDryRunMode | 3 | dry-run returns correct status, paths, no fs changes |
| `test_windows_local_runner.py` | TestNoOpFixture | 3 | no-op status, no writes, serialization |
| `test_windows_local_runner.py` | TestPathSeparation | 4 | worktree/evidence/logs on separate drives |
| `test_windows_local_runner.py` | TestNoControllerRepoWrites | 3 | dry-run/no-op/path-validation block controller |
| `test_windows_local_runner.py` | TestSelfCheck | 1 | self-check function passes all checks |
| `test_worker_transport_routing.py` | TestWorkerNodeSerialization | 5 | SSH/local-exec round-trip, missing fields, unknown fields, JSON |
| `test_worker_transport_routing.py` | TestTransportRouting | 6 | linux-worker→ssh, windows-worker→local-exec, implementer→any |
| `test_worker_transport_routing.py` | TestManualOnlyFiltering | 5 | excluded by default, included when requested, select_worker |
| `test_worker_transport_routing.py` | TestDisabledWorkerFiltering | 2 | disabled excluded, enabled included |
| `test_worker_transport_routing.py` | TestUnknownTransportFailClosed | 3 | unknown transport → no match, local-exec only matches its caps |
| `test_worker_transport_routing.py` | TestDefaultWorkers | 4 | 21bao/5bao/9bao registration, 3 workers total |

**Total: 47 pytest test cases + 35 self-check scenarios = 82 total, all fixture-based (no live model calls)**

## Self-Check Scenarios

### vibe_worker_registry.py --self-check (15 checks)
1. default_workers_defined (3 workers including 21bao)
2. equal_weight
3. select_single_online
4. least_loaded_selection
5. branch_lock_prevents_concurrent
6. merge_lock_prevents_duplicate
7. maintenance_excluded
8. both_offline_returns_none
9. status_report_structure (3 total, 2 available — 21bao manual_only excluded)
10. no_secret_in_output
11. **transport_field** (5bao/9bao=ssh, 21bao=local-exec)
12. **manual_only_filtering** (21bao excluded by default, included when requested)
13. **disabled_worker_excluded** (21bao excluded even without manual_only)
14. **worker_serialization_roundtrip** (to_dict/from_dict preserves all new fields)
15. **select_excludes_manual_only** (only 21bao online but not auto-selected)

### vibe_scheduler_policy.py --self-check (10 checks)
1-7. Existing checks (unchanged)
8. **transport_routing_implementer** (IMPLEMENTER routes to ssh workers only when 21bao is manual_only)
9. **21bao_not_auto_scheduled** (21bao is not selected even when only online worker)
10. **transport_filter_helper** (WINDOWS_WORKER→local-exec, LINUX_WORKER→ssh, IMPLEMENTER→None)

### vibe_windows_local_runner.py --self-check (10 checks)
1. path_allowlist_drive_d
2. path_allowlist_drive_e
3. path_blocklist_controller
4. path_blocklist_drive_c
5. dry_run_mode
6. no_op_fixture
7. job_result_serialization
8. constants_correct
9. no_op_no_filesystem
10. version_check

## MODEL_LEDGER

| Field | Value |
|-------|-------|
| Live model calls | 0 |
| Fixture/mock calls | 46 |
| Evidence type | pytest assertions + self-check JSON |
| Reproducibility | All tests run locally with no network/SSH |

## NODE_MODEL_SUMMARY

| Worker | Transport | Node Type | Enabled | Manual Only | Capabilities |
|--------|-----------|-----------|---------|-------------|-------------|
| 5bao | ssh | debian-worker | True | False | linux-worker, read-only, implementer, reviewer, pytest, smoke |
| 9bao | ssh | debian-worker | True | False | linux-worker, read-only, implementer, reviewer, pytest, smoke |
| 21bao | local-exec | windows-worker | False | True | windows-worker, implementer, reviewer, powershell, local-job, opencode |

## Safety Notes

1. **21bao is manual_only=True and enabled=False**: It is NEVER auto-scheduled. It must be explicitly selected with `include_manual_only=True`.

2. **SSH fields optional for local-exec workers**: WorkerNode now defaults ssh_host="", ssh_port=0, ssh_user="", ssh_key_path="" so local-exec workers don't need SSH configuration.

3. **Unknown transport fails closed**: Workers with transport not in {"ssh", "local-exec"} are excluded from all scheduling.

4. **Path allowlist enforcement**: The Windows local runner only allows D:\ and E:\ paths. The controller repo (C:\Users\KK\vibe-coding-repo) is explicitly blocked.

5. **No controller repo writes**: The runner NEVER writes to the controller repo. All evidence and logs go to D:\vibedev-evidence\ and D:\vibedev-logs\.

6. **Timeout + cancellation**: Jobs have a configurable timeout (default 30 min). On timeout, process trees are killed via `taskkill /F /T`.

7. **Job lock**: File-based locking prevents concurrent execution of the same job.

8. **Serialization round-trip**: to_dict/from_dict handles all new fields (transport, enabled, manual_only) and tolerates missing fields for backward compatibility.

## Test Count Reconciliation (V1.20.16B)

| Source | Collected | Passed |
|--------|-----------|--------|
| pytest (test_worker_transport_routing.py) | 25 | 25 |
| pytest (test_windows_local_runner.py) | 22 | 22 |
| **PYTEST_TOTAL** | **47** | **47** |
| self-check (vibe_worker_registry.py) | 15 | 15 |
| self-check (vibe_scheduler_policy.py) | 10 | 10 |
| self-check (vibe_windows_local_runner.py) | 10 | 10 |
| **SELF_CHECK_TOTAL** | **35** | **35** |
| **GRAND_TOTAL** | **82** | **82** |

## Unicode Hardening (V1.20.16B)

All 6 PR files scanned for BOM (U+FEFF), zero-width (U+200B-200F), bidi override (U+202A-202E), isolate controls (U+2066-2069). **Result: 0 dangerous characters found.** GitHub diff warning is a false positive (legitimate CJK text in report).
