| # | ID | Severity | Title | Proposed Fix |
|:-:|---|:--------:|-------|:------------:|
| 1 | ARCH-001 | **Blocker** | Architecture contract has no runtime enforcement | I22 |
| 2 | DSP-002 | **Blocker** | route-all has no operator-approved checkpoint | I22 |
| 3 | ARCH-003 | High | Manual-only worker flag has no enforcement | I22 |
| 4 | WRKR-001 | High | Worker registry has no reachability probe | I22 |
| 5 | WRKR-002 | High | No automated recovery on worker failure | I23 |
| 6 | DSP-003 | High | Fallback policy defined but not enforced at runtime | I23 |
| 7 | POOL-001 | High | Extra visible models not blocked from alias resolution | I22 |
| 8 | WIN-001 | High | python3 not available on Windows — scripts fail | I22 |
| 9 | WIN-002 | High | 21bao has no operational worker runtime | I23 |
| 10 | TEST-002 | High | No runtime/integration test coverage | I23 |
| 11 | ARCH-002 | Medium | 21bao health_status permanently UNKNOWN in route-all | I23 |
| 12 | DSP-001 | Medium | Dispatch manifest is RFC-only — no executable schema | I24 |
| 13 | DSP-004 | Medium | No planned-vs-actual audit at execution time | I24 |
| 14 | RSYNC-001 | Medium | Node opencode.jsonc not periodically synced with central pool | I23 |
| 15 | RSYNC-002 | Medium | Rollback requires manual SSH per node | I23 |
| 16 | OCR-002 | Medium | 0/5 opencode free/native models enabled | I24 |
| 17 | GIT-001 | Medium | PR base ref consistently lags behind main | I23 |
| 18 | WIN-003 | Medium | MSYS/POSIX path translation issues | I23 |
| 19 | RPT-001 | Medium | Phase reports are free-form YAML — no schema | I23 |
| 20 | RPT-002 | Medium | Secret check depends on manual regex — easy to bypass | I23 |
| 21 | TEST-001 | Medium | Pre-existing test failures not systematically tracked | I22 |
| 22 | DOC-001 | Medium | No operator playbook for common scenarios | I24 |
| 23 | WRKR-003 | Low | SSH credential key path empty in registry | I24 |
| 24 | POOL-002 | Low | model_pool.yaml has id field inconsistency | I24 |
| 25 | POOL-003 | Low | Model pool has no integrity signature | I25 |
| 26 | OCR-001 | Low | Only 2/8 opencode-go models enabled — 6 verified but idle | I24 |
| 27 | OCR-003 | Low | No runtime model discovery cache | future |
| 28 | GIT-002 | Low | No automated branch cleanup after merge | I25 |
| 29 | GIT-003 | Low | GitHub PR mutation detection is fragile | future |
| 30 | DOC-002 | Low | Worker evidence template lacks validation | future |
| 31 | ENH-001 | Enhancement | Execution record persistence layer | future |
| 32 | ENH-002 | Enhancement | Cost / pricing registry | future |
| 33 | ENH-003 | Enhancement | Recommendation engine | future |
| 34 | ENH-004 | Enhancement | Cross-model reproducibility hashing | future |
| 35 | ENH-005 | Enhancement | Multi-cluster federation | future |
| 36 | ENH-006 | Enhancement | Automated model ranking / scoring | future |

**Summary:** 2 blockers (must fix before first dispatch), 8 high, 12 medium, 8 low, 6 deferred enhancements — 30 active issues targeting I22 through future phases.