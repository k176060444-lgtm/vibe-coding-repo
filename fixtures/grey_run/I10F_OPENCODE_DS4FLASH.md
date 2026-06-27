# Grey-Run Fixture: opencode-ds4flash Canary

> V1.21.33I10F — Controlled grey run fixture for opencode-go canary validation.
> Generated: 2026-06-27T14:53 UTC+8

---

## Work Order

| Field | Value |
|-------|-------|
| **workorder_id** | `wo_i10f_opencode_ds4flash_fixture_001` |
| **approval_id** | `a2b7c9d1e3f5` |
| **runtime_assignment_id** | `ra_opencode_ds4flash_001` |
| **execution_ticket_id** | `et_opencode_ds4flash_001` |
| **model_call_id** | `mc_i10f_001` |
| **scope** | `fixture-only-grey-run` |
| **status** | `completed` |

## Provider / Model

| Field | Value |
|-------|-------|
| **provider** | `opencode-go` |
| **model** | `deepseek-v4-flash` |
| **alias** | `opencode-ds4flash` |
| **cost** | `free` |
| **source** | `hermes_provider_sync` |
| **fallback_policy** | `none` |
| **operator_selection_required** | `true` |

## Grey-Run Linkage

### Preceding phases

| Phase | Verdict | Description |
|-------|---------|-------------|
| I10C | ✅ PASS | Sync 8 opencode-go models into central pool |
| I10D | ✅ PASS | Metadata-only route + resolve + approval dry-run |
| I10E | ✅ LIVE SMOKE PASS | Single real call: `EXACT_STRING: OPENCODE_GO_CANARY_OK` |
| **I10F** | ✅ **GREY RUN PASS** | This fixture — controlled generation via controlled execution chain |

### Execution chain trace

```text
model_pool.yaml (opencode-go-deepseek-v4-flash, enabled=true)
  → model_alias_config.yaml (opencode-ds4flash → opencode-go/deepseek-v4-flash)
    → operator selection (scope: fixture-only-grey-run)
      → approval (frozen scope, fallback_policy=none)
        → runtime_assignment (node: local, alias: opencode-ds4flash)
          → execution_ticket (model_call_id: mc_i10f_001)
            → dispatch/admission → controlled worker gate
              → model call (opencode-go/deepseek-v4-flash)
                → fixture file write (this file)
                → local commit
```

### Constraints verified

| Constraint | Value |
|------------|-------|
| model_call_count | 1 |
| fallback_count | 0 |
| worker_invoked | false |
| ssh_invoked | false |
| changed_files | 1 (this fixture only) |
| route-all 9 roles | unchanged |
| model_pool self-check | 129/129 PASS |
| secret/forbidden/bidi | PASS |

---

*End of fixture — I10F grey run complete.*
