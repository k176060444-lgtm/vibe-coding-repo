# Model Fallback Evidence Fixture

## 1. Fallback Trigger Conditions

| Condition | Description |
|---|---|
| HTTP 429 | Provider rate limit exceeded |
| HTTP 503 | Provider service unavailable |
| Connection timeout | Configurable threshold, default 30s |
| Model not found | Model absent from provider registry |
| Invalid/expired API key | Key rejected by provider |

## 2. Fallback Chain

1. Log failure reason with ISO-8601 timestamp
2. Query approved model registry for alternatives
3. Select next model by priority order
4. Retry with fallback model
5. Record `fallback_used=true` in evidence

## 3. Non-Fallback Cases (must NOT trigger)

| Condition | Action |
|---|---|
| HTTP 401 (credential error) | Fix credentials, do not fallback |
| Configuration errors | Fix configuration, do not fallback |
| Permission errors | Escalate, do not fallback |
| Git conflicts | Resolve manually, do not fallback |

## 4. Evidence Fixture Example

```json
{
  "job_id": "fb-20260619-143022-7a3f",
  "timestamp": "2026-06-19T14:30:22.000Z",
  "primary_model": "deepseek-plan/deepseek-v4-pro",
  "failure_reason": "HTTP 429: rate_limit_exceeded",
  "fallback_model": "deepseek-plan/deepseek-v4-flash",
  "fallback_used": true,
  "chain": [
    {"step": 1, "action": "log_failure", "detail": "HTTP 429 from provider"},
    {"step": 2, "action": "query_registry", "detail": "found fallback candidate"},
    {"step": 3, "action": "select_model", "detail": "deepseek-v4-flash (priority 1)"},
    {"step": 4, "action": "retry", "result": "success"},
    {"step": 5, "action": "record_evidence", "detail": "fallback_used: true"}
  ]
}
```

## 5. Model Registry (Approved Models)

| Model ID | Provider |
|---|---|
| `deepseek-plan/deepseek-v4-flash` | deepseek-plan |
| `deepseek-plan/deepseek-v4-pro` | deepseek-plan |
| `minimax-plan/MiniMax-M3` | minimax-plan |
| `xiaomi-plan/mimo-v2.5-pro` | xiaomi-plan |
