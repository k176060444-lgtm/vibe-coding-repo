# V1.20.6 MODEL_LEDGER Enforcement Gate Report

Generated: 2026-06-19T14:30:00Z
Branch: feat/v1206-model-ledger-enforcement-gate
Base SHA: 8536dbd53f7d324101f5d8a6404078d872ae987d
Plan Reference: V1.20.6_MODEL_LEDGER_ENFORCEMENT_GATE

## Preflight Results

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| Windows HEAD | 8536dbd5... | 8536dbd53f7d324101f5d8a6404078d872ae987d | PASS |
| 5bao OpenCode | 1.17.8 | 1.17.8 | PASS |
| 9bao OpenCode | 1.17.8 | 1.17.8 | PASS |
| Binary SHA256 (both) | ea9f0e72... | ea9f0e7257bbd3d71b788bca397d3b8d951c101c21d3387ca39ae41b66360ec7 | PASS |
| V1.17.7 freeze | 547da273 | exists | PASS |
| V1.20.4 policy files | present | present | PASS |
| V1.20.5 E2E report | present | present | PASS |

## Deliverables

| File | Description | Status |
|------|-------------|--------|
| scripts/model_ledger_gate.py | Gate validator (CLI + library) | UPDATED |
| docs/MODEL_LEDGER_ENFORCEMENT_GATE.md | Documentation | UPDATED |
| docs/reports/model-ledger-gate-fixture.json | 13 test scenarios | UPDATED |
| docs/reports/V1206_MODEL_LEDGER_ENFORCEMENT_GATE_REPORT.md | This report | UPDATED |

## Gate Rules Implemented

| Rule | ID | Description | Status |
|------|----|-------------|--------|
| 1 | GATE-01 | Terminal status requires MODEL_LEDGER | IMPLEMENTED |
| 2 | GATE-02 | MODEL_LEDGER entry completeness | IMPLEMENTED |
| 3 | GATE-03 | No-model-call format enforcement | IMPLEMENTED |
| 4 | GATE-04 | NODE_MODEL_SUMMARY required + entry validation | IMPLEMENTED |
| 5 | GATE-05 | rate_limit=true requires RATE_LIMIT_EVENT_LEDGER | IMPLEMENTED |
| 6 | GATE-06 | rate limit must not trigger rollback | IMPLEMENTED |
| 6b | GATE-06b | exit_code vs error_type consistency | IMPLEMENTED |
| 7 | GATE-07 | fallback_used=true requires FALLBACK_DECISION_LEDGER | IMPLEMENTED |
| 8 | GATE-08 | COOLDOWN_STATE_SUMMARY required + entry validation | IMPLEMENTED |
| 9 | GATE-09 | token_usage forbidden values | IMPLEMENTED |
| 10 | GATE-10 | Critical field completeness (all ledgers) | IMPLEMENTED |

## NODE_MODEL_SUMMARY Validation

Each entry must have:
- node (non-empty, not unknown/TBD)
- opencode_version (non-empty, not unknown/TBD)
- models_used_this_run (must be list)
- total_model_calls (non-negative integer)
- successful_model_calls (non-negative integer)
- failed_model_calls (non-negative integer)
- fallback_count (non-negative integer)
- rate_limit_count (non-negative integer)
- cooldown_state (non-empty, not unknown/TBD)

## COOLDOWN_STATE_SUMMARY Validation

Each entry must have:
- node (non-empty, not unknown/TBD)
- model (non-empty, not unknown/TBD)
- consecutive_rate_limits (non-negative integer)
- current_cooldown_seconds (non-negative integer)
- cooldown_action (non-empty, not unknown/TBD)

## Fixture Validation Results

| Scenario | Description | Expected | Actual | Status |
|----------|-------------|----------|--------|--------|
| scenario-01 | Valid full report (3 live + 2 fixture) | PASS | PASS | PASS |
| scenario-02 | Valid no-model-call report | PASS | PASS | PASS |
| scenario-03 | Missing MODEL_LEDGER | FAIL | FAIL | PASS |
| scenario-04 | Missing NODE_MODEL_SUMMARY | FAIL | FAIL | PASS |
| scenario-05 | rate_limit=true without RATE_LIMIT_EVENT_LEDGER | FAIL | FAIL | PASS |
| scenario-06 | fallback_used=true without from/to/reason | FAIL | FAIL | PASS |
| scenario-07 | token_usage='unknown' | FAIL | FAIL | PASS |
| scenario-08 | Rate limit (exit 124) misclassified as BIN-FAIL | FAIL | FAIL | PASS |
| scenario-09 | Incomplete MODEL_LEDGER entry | FAIL | FAIL | PASS |
| scenario-10 | Valid report with fallback documented | PASS | PASS | PASS |
| scenario-11 | Missing COOLDOWN_STATE_SUMMARY | FAIL | FAIL | PASS |
| scenario-12 | NODE_MODEL_SUMMARY only has node | FAIL | FAIL | PASS |
| scenario-13 | COOLDOWN_STATE_SUMMARY only has node | FAIL | FAIL | PASS |

**Result: 13/13 scenarios passed**

## Validation Evidence

```
=== SELF-CHECK ===
  Version: 1.0.0
  Total: 13
  Passed: 13
  Failed: 0
  Self-check: PASSED
```

## py_compile

```
$ python -m py_compile scripts/model_ledger_gate.py
COMPILE_OK
```

## File Quality

- UTF-8 no BOM
- LF only
- No hidden/bidi/zero-width characters
- No secrets/tokens/internal IPs/Windows paths

## Safety Declarations

| Declaration | Value |
|-------------|-------|
| runtime_code_changed | false |
| credential_modified | false |
| secret_exposed | false |
| internal_ip_in_public_files | false |
| merge_executed | false |
| upgrade_performed | false |

## PR Requirements

- Branch: feat/v1206-model-ledger-enforcement-gate
- Base SHA: 8536dbd53f7d324101f5d8a6404078d872ae987d
- Changed files: scripts/model_ledger_gate.py, docs/MODEL_LEDGER_ENFORCEMENT_GATE.md, docs/reports/model-ledger-gate-fixture.json, docs/reports/V1206_MODEL_LEDGER_ENFORCEMENT_GATE_REPORT.md
- runtime_code_changed: false (CLI validator only, no runtime service changes)
- merge_requires_operator_approval: true
