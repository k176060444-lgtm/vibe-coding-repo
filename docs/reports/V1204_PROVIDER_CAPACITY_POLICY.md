# V1.20.4 Provider Capacity and Model Routing Policy Report

Generated: 2026-06-19T13:00:00Z
Branch: policy/v1204-provider-capacity-model-routing-clean
Base SHA: c14d03f8c601eb945871abc58131b492915ead5c
Supersedes: PR #169 (closed, not merged)

## Preflight Results

| Check | Result |
|-------|--------|
| Windows HEAD | c14d03f8c601eb945871abc58131b492915ead5c |
| 5bao OpenCode | 1.17.8 |
| 9bao OpenCode | 1.17.8 |
| Binary SHA256 (both) | ea9f0e7257bbd3d71b788bca397d3b8d951c101c21d3387ca39ae41b66360ec7 |
| Active-active capacity | 2 |
| V1.17.7 freeze | unchanged (547da273) |
| runtime_code_changed | false |

## Policy Coverage

1. Model Tiers: free-tier / paid / quota-stable / quarantined
2. Rate-Limit Classification: 6 categories (RL-TRANSIENT, RL-QUOTA, AUTH-ERR, BIN-FAIL, PROV-UNAVAIL, UNKNOWN)
3. Cooldown Rules: 30s / 120s / 300s escalation with recovery path
4. Fallback Rules: full chain recorded in MODEL_LEDGER
5. Rollback Rules: rate limit does NOT trigger binary rollback
6. Node Routing: provider-aware with independence consideration
7. Report Requirements: MODEL_LEDGER + NODE_MODEL_SUMMARY + RATE_LIMIT_EVENT_LEDGER

## Fixture Scenarios

| ID | Description | Expected Status |
|----|-------------|----------------|
| scenario-01 | 5bao PASS | PASS |
| scenario-02 | 9bao rate limit | RATE_LIMITED (RL-TRANSIENT) |
| scenario-03 | planned = actual | PASS |
| scenario-04 | fallback occurred | PASS |
| scenario-05 | no fallback | PASS |
| scenario-06 | binary failure vs rate limit | FAIL (BIN-FAIL) |
| scenario-07 | auth error | FAIL (AUTH-ERR) |
| scenario-08 | cooldown escalation | RATE_LIMITED (300s cooldown) |

## Model Tier Registry

| Model | Tier | Notes |
|-------|------|-------|
| opencode/deepseek-v4-flash-free | free-tier | Confirmed rate-limited in V1.20.3 |
| opencode/mimo-v2.5-free | free-tier | |
| opencode/nemotron-3-ultra-free | free-tier | |
| opencode/north-mini-code-free | free-tier | |
| opencode/big-pickle | free-tier | |
| ark-code-latest | quarantined | key_format_incorrect |

## Safety Declarations

| Declaration | Value |
|-------------|-------|
| runtime_code_changed | false |
| credential_modified | false |
| secret_exposed | false |
| internal_ip_in_public_files | false |
| merge_executed | false |
