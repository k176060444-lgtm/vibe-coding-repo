# MODEL_LEDGER Enforcement Gate

Version: V1.20.6
Status: ACTIVE
Enforced by: Orchestrator, Reporter, CI

## Purpose

Upgrade MODEL_LEDGER, NODE_MODEL_SUMMARY, RATE_LIMIT_EVENT_LEDGER,
FALLBACK_DECISION_LEDGER, and COOLDOWN_STATE_SUMMARY from "report requirements"
to automatic validation gates.

Any report claiming terminal status (PASS, MERGE_READY, FREEZE_PASS,
PROMOTION_PASS) MUST pass this gate before the status is accepted.

## Gate Rules

| Rule | ID | Description |
|------|----|-------------|
| 1 | GATE-01 | Terminal status requires complete MODEL_LEDGER |
| 2 | GATE-02 | Each MODEL_LEDGER entry must have all required fields |
| 3 | GATE-03 | No-model-call entries must have call_count=0, planned_model=N/A, token_usage=no_model_call:<reason> |
| 4 | GATE-04 | NODE_MODEL_SUMMARY must exist and cover participating nodes |
| 5 | GATE-05 | rate_limit=true requires RATE_LIMIT_EVENT_LEDGER |
| 6 | GATE-06 | rate limit must not trigger binary rollback (only BIN-FAIL allows rollback) |
| 6b | GATE-06b | exit_code must match error_type (no misclassification: 124=RL-TRANSIENT, 139=BIN-FAIL) |
| 7 | GATE-07 | fallback_used=true requires FALLBACK_DECISION_LEDGER with fallback_from/to/reason |
| 8 | GATE-08 | COOLDOWN_STATE_SUMMARY must exist or provide COOLDOWN_NOT_APPLICABLE_REASON |
| 9 | GATE-09 | token_usage must not be empty/unknown/TBD |
| 10 | GATE-10 | Missing critical fields in any ledger entry -> FAIL |

## Required Fields

### MODEL_LEDGER Entry

| Field | Required | Conditional |
|-------|----------|-------------|
| node | YES | |
| job_id | YES | |
| role | YES | |
| planned_model | YES | |
| actual_model | YES | |
| provider | YES | |
| opencode_provider_alias | YES | |
| fallback_used | YES | |
| fallback_from | | IF fallback_used=true |
| fallback_to | | IF fallback_used=true |
| fallback_reason | | IF fallback_used=true |
| call_count | YES | |
| token_usage_or_unavailable_reason | YES | |
| duration | YES | |
| exit_code | YES | |
| rate_limit | YES | |
| final_status | YES | |

### NODE_MODEL_SUMMARY Entry

| Field | Required |
|-------|----------|
| node | YES |
| opencode_version | YES |
| models_used_this_run | YES |
| total_model_calls | YES |
| successful_model_calls | YES |
| failed_model_calls | YES |
| fallback_count | YES |
| rate_limit_count | YES |
| cooldown_state | YES |

### RATE_LIMIT_EVENT_LEDGER Entry

| Field | Required |
|-------|----------|
| timestamp | YES |
| node | YES |
| affected_model | YES |
| provider | YES |
| error_type | YES |
| exit_code | YES |
| binary_ok | YES |
| rollback_required | YES |
| cooldown_action | YES |
| fallback_action | YES |

### Error Type Classification

| Error Type | Code | Description | Rollback Allowed |
|------------|------|-------------|-----------------|
| RL-TRANSIENT | exit 124 | Provider rate limit | NO |
| RL-QUOTA | | Quota exhausted | NO |
| AUTH-ERR | | Auth error | NO |
| BIN-FAIL | exit 139 | Binary crash | YES |
| PROV-UNAVAIL | | Provider unavailable | NO |
| UNKNOWN | | Unclassified | INVESTIGATE |

## Usage

```bash
# Self-check with fixtures
python scripts/model_ledger_gate.py --self-check

# Validate a report JSON
python scripts/model_ledger_gate.py --validate report.json

# Run fixture validation
python scripts/model_ledger_gate.py --fixture docs/reports/model-ledger-gate-fixture.json
```

## Integration

The gate should be called by:
1. Orchestrator before emitting PASS/MERGE_READY/FREEZE_PASS/PROMOTION_PASS
2. CI pipeline as a validation step
3. Reporter before finalizing any report

A gate failure MUST block the terminal status. The report must be corrected
and re-validated before the status can be emitted.

## Safety

- No live model calls
- No credential/secret access
- No network calls
- Read-only validation
- runtime_code_changed=false (CLI validator only)
