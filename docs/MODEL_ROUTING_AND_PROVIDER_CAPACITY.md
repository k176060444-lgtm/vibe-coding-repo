# Model Routing and Provider Capacity Policy

Version: V1.20.4
Status: ACTIVE
Enforced by: Orchestrator, Scheduler, Reporter

## 1. Model Tiers

Every model used by the VibeDev cluster is classified into exactly one tier.

| Tier | Description | Smoke Policy | Rate-Limit Expectation |
|------|-------------|-------------|----------------------|
| `free-tier` | Provider-hosted free models | Low frequency; interval >= 30s | Expected; provider may throttle |
| `paid` | Paid API endpoints with explicit billing | Standard frequency | Rare; indicates quota exhaustion |
| `quota-stable` | Models with confirmed stable quota (>= 5 consecutive PASS) | Standard frequency | Unexpected; investigate |
| `quarantined` | Models blocked due to persistent failures | BLOCKED | N/A |

### Tier Assignment Rules

- New models start as `free-tier` unless explicitly promoted.
- Promotion to `quota-stable` requires 5 consecutive calls without rate limit.
- Demotion to `quarantined` requires 3 consecutive failures of the same type.
- Tier changes are recorded in the MODEL_LEDGER with `tier_change=true`.

## 2. Rate-Limit Classification

All provider failures are classified into exactly one category.

| Category | Code | Description | Trigger Rollback |
|----------|------|-------------|-----------------|
| `provider_availability_degraded_transient` | `RL-TRANSIENT` | Provider-side rate limit; binary and config are correct | NO |
| `model_quota_exhausted` | `RL-QUOTA` | Paid model quota exceeded | NO |
| `provider_auth_error` | `AUTH-ERR` | Invalid credentials, revoked key, or permission denied | NO |
| `binary_failure` | `BIN-FAIL` | OpenCode binary crash, segfault, or path mismatch | YES |
| `provider_unavailable` | `PROV-UNAVAIL` | Provider endpoint unreachable (DNS, network, 5xx) | NO |
| `unknown_error` | `UNKNOWN` | Unclassified failure | INVESTIGATE |

### Classification Rules

- `Rate limit exceeded` in error message -> `RL-TRANSIENT`
- `quota` or `billing` in error message -> `RL-QUOTA`
- `401` or `auth` in error message -> `AUTH-ERR`
- `segfault`, `SIGSEGV`, exit code 139 -> `BIN-FAIL`
- `connection refused`, `timeout`, `502/503/504` -> `PROV-UNAVAIL`
- Everything else -> `UNKNOWN`

## 3. Cooldown Rules

| Scenario | Cooldown Duration | Action |
|----------|------------------|--------|
| First rate limit on free-tier model | 30s | Log event; retry after cooldown |
| Second consecutive rate limit (same node, same model) | 120s | Log event; switch node if available |
| Third consecutive rate limit (same node, same model) | 300s | Log event; switch model tier |
| Rate limit on paid model | 60s | Log event; retry after cooldown |
| Binary failure | immediate | BLOCK node; trigger rollback evaluation |

### Cooldown State Machine

```
NORMAL -> RATE_LIMITED_1 (30s) -> RATE_LIMITED_2 (120s) -> RATE_LIMITED_3 (300s) -> QUARANTINED
RECOVERY (5 consecutive PASS) <--------------------------------------------------------+
```

## 4. Fallback Rules

### Required Fields

Every model call must record:

| Field | Required | Description |
|-------|----------|-------------|
| `planned_model` | YES | Model requested by scheduler |
| `actual_model` | YES | Model actually used (may differ if fallback) |
| `fallback_used` | YES | boolean |
| `fallback_from` | IF fallback | Original model that failed |
| `fallback_to` | IF fallback | Model used instead |
| `fallback_reason` | IF fallback | Why fallback occurred |

### Fallback Chain

```
planned_model (free-tier)
  -> rate limited -> fallback_to: same model on other node
  -> both nodes rate limited -> fallback_to: different free-tier model
  -> all free-tier exhausted -> fallback_to: paid model (if configured)
  -> no fallback available -> BLOCK with reason
```

### Fallback Restrictions

- Fallback must not bypass capability filters (e.g. ripgrep requires 9bao).
- Fallback must not use quarantined models.
- Fallback must record the full chain in MODEL_LEDGER.
- Fallback from free-tier to paid requires operator approval if cost > $0.

## 5. Rollback Rules

### Trigger Conditions

| Condition | Rollback Target | Action |
|-----------|----------------|--------|
| Binary crash (exit 139, SIGSEGV) | Previous binary backup | Replace binary, verify SHA256 |
| Path mismatch (active path != expected) | Fix path or restore binary | Reconfigure, verify |
| Secret drift (hash changed) | Restore from backup | BLOCK, investigate |
| Version drift (unexpected version) | Previous version | Replace binary |
| Provider rate limit | N/A | NO rollback; use cooldown |
| Provider auth error | N/A | NO rollback; check credentials |
| Network failure | N/A | NO rollback; check connectivity |

### Rollback Validation

After rollback, all of the following must pass:
- `opencode --version` matches expected version
- `sha256sum` matches expected binary hash
- `readlink -f` matches expected active path
- Secret hash prefix unchanged
- One successful model call

## 6. Node Routing

### Default Routing

- Both nodes are equal weight (100) and max_parallel_jobs=1.
- Scheduler selects node based on capability filter, not model preference.
- Same provider/model can be used on both nodes.

### Rate-Limit Routing

When a node experiences rate limit:
1. Log RATE_LIMIT_EVENT_LEDGER entry.
2. If other node is healthy, route next call to other node.
3. If both nodes rate-limited on same model, enter cooldown.
4. After cooldown, retry with backoff.

### Provider Isolation

- Different providers have independent rate limits.
- Rate limit on provider A does not affect provider B.
- Node routing considers provider independence.

## 7. Report Requirements

### MODEL_LEDGER (every job)

| Field | Type | Required |
|-------|------|----------|
| `node` | string | YES |
| `job_id` | string | YES |
| `role` | string | YES (implement/review/smoke) |
| `planned_model` | string | YES |
| `actual_model` | string | YES |
| `provider` | string | YES |
| `opencode_provider_alias` | string | YES |
| `fallback_used` | boolean | YES |
| `fallback_from` | string | IF fallback |
| `fallback_to` | string | IF fallback |
| `fallback_reason` | string | IF fallback |
| `call_count` | integer | YES |
| `token_usage_or_unavailable_reason` | string | YES |
| `duration` | string | YES |
| `exit_code` | integer | YES |
| `rate_limit` | boolean | YES |
| `final_status` | string | YES (PASS/FAIL/RATE_LIMITED/TIMEOUT) |

### NODE_MODEL_SUMMARY (per patrol/run)

| Field | Type | Required |
|-------|------|----------|
| `node` | string | YES |
| `opencode_version` | string | YES |
| `active_opencode_path` | string | YES |
| `models_used_this_run` | list | YES |
| `total_model_calls` | integer | YES |
| `successful_model_calls` | integer | YES |
| `failed_model_calls` | integer | YES |
| `fallback_count` | integer | YES |
| `rate_limit_count` | integer | YES |
| `cooldown_state` | string | YES |

### RATE_LIMIT_EVENT_LEDGER (per rate-limit event)

| Field | Type | Required |
|-------|------|----------|
| `timestamp` | string (ISO 8601) | YES |
| `node` | string | YES |
| `affected_model` | string | YES |
| `provider` | string | YES |
| `error_type` | string | YES |
| `exit_code` | integer | YES |
| `binary_ok` | boolean | YES |
| `rollback_required` | boolean | YES |
| `cooldown_action` | string | YES |
| `fallback_action` | string | YES |

## 8. V1.20.3 Lessons Applied

- 9bao rate limit on opencode/deepseek-v4-flash-free was correctly classified as provider_availability_degraded_transient.
- Binary was confirmed OK (v1.17.8, session created, model resolved).
- Rollback was NOT triggered (correct behavior).
- High-frequency smoke on free-tier models must be spaced >= 30s apart.
