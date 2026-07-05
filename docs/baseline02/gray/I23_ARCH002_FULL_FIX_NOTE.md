# I23 — ARCH-002 Full Fix (companion note to PR #363)

**Date**: 2026-07-05
**Branch**: `fix/i23-arch-002-route-all-health-gate`
**Author**: VibeDev Orchestrator (21bao) under operator authorization `APPROVE_I23_PLAN_TWO_PR` + `APPROVE_PR_363_ONLY`

---

## What changed in PR #363

Two surgical edits, both in `scripts/vibe_model_routing_policy.py`:

1. **New helper `_fresh_probe_all(reg, max_age_sec=300)`** — invoked at the top of `route_all()`. Refreshes any worker's `health_status` whose `last_health_check` is empty, `UNKNOWN`, or > 300 s old. Skip-only-fresh logic preserves fast-path; only stale workers trigger real SSH / hostname probes.

2. **Modified `_resolve_node_for_role()`** — was filtering `health_status == "OFFLINE"` only (allowing UNKNOWN through); now fail-closes on UNKNOWN/empty by routing any such case through a new `HEALTH_UNKNOWN_BLOCKED` error dict that names the blocked nodes and tells the operator how to refresh (`vibe_worker_registry.py --health-check`).

## Sync-back into registry dict

The function `_load_worker_registry()` returns a **dict** (not a live `WorkerRegistry` instance). After `_fresh_probe_all()` runs against a fresh `WorkerRegistry()` instance, the route-all code now **copies** `health_status` + `last_health_check` back into that dict so `_resolve_node_for_role()` sees the freshly probed state on every iteration.

## Effect

Before PR #363:

```bash
$ python scripts/vibe_model_routing_policy.py --json route-all
# node_attribution[implementer].health_status == "UNKNOWN"
# (every node permanently UNKNOWN in registry state)
```

After PR #363:

```bash
$ python scripts/vibe_model_routing_policy.py --json route-all
# _gate_results.arch_002_worker_health_freshness.checked == [stale workers]
# node_attribution[implementer].health_status == "ONLINE"  (after probe)
# OR
# node_attribution.implementer.error == "HEALTH_UNKNOWN_BLOCKED"
#   with blocked_nodes + operator_action_required
```

## Test surface

New `tests/test_arch_002_route_all_health.py` adds 13 tests across 6 TestClass — covers all 6 operator-mandated scenarios plus regression of fresh-skip/empty-trigger/unknown-trigger and other-gates-preserved.

Run:

```bash
pytest tests/test_arch_002_route_all_health.py -v     # 13/13
pytest tests/test_i23_runtime_reliability.py -v       # 24/24 (unchanged)
pytest tests/test_vibe_worker_registry_health_probe.py -v  # 22/22 (unchanged)
```

## Not changed

- NMC / model_pool / apply tool / F6 / Stage4 / Stage7
- operator-approvals / readiness / gray evidence
- worker_registry / runtime_reliability / architecture_contract
- Round 1 / Round 2 evidence files
- `tests/test_i23_runtime_reliability.py` (already covers ARCH-002 layer)

## Next

PR #364 (cross-node evidence schema) is a separate authorization. Do not begin until operator approves.
