# V1.20.7/8/9 Ledger Gate Integration Report

Generated: 2026-06-19T15:00:00Z
Branch: feat/v1207-1209-ledger-gate-integration
Base SHA: b3a59f9271dcbc320cd79e85d2b4470d79ecd50f

## Preflight Results

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| Windows HEAD | b3a59f92... | b3a59f9271dcbc320cd79e85d2b4470d79ecd50f | PASS |
| 5bao OpenCode | 1.17.8 | 1.17.8 | PASS |
| 9bao OpenCode | 1.17.8 | 1.17.8 | PASS |
| Binary SHA256 (both) | ea9f0e72... | ea9f0e7257bbd3d71b788bca397d3b8d951c101c21d3387ca39ae41b66360ec7 | PASS |
| V1.20.6 gate | 13/13 | 13/13 | PASS |
| V1.17.7 freeze | 547da273 | exists | PASS |

## Deliverables

| File | Description | Status |
|------|-------------|--------|
| scripts/vibe_report_status_gate.py | Report status + merge readiness gate | CREATED |
| docs/V1207_1208_1209_LEDGER_GATE_INTEGRATION.md | Documentation | CREATED |
| docs/reports/V1207_1208_1209_LEDGER_GATE_INTEGRATION_REPORT.md | This report | CREATED |

## Integration Test Results

### Self-check: 11/11 PASSED

| ID | Description | Expected Status | Expected Merge | Actual Status | Actual Merge | Status |
|----|-------------|-----------------|----------------|---------------|--------------|--------|
| int-01 | Valid V1.20.5 report | ALLOWED | true | ALLOWED | true | PASS |
| int-02 | Non-terminal (IN_PROGRESS) | ALLOWED | false | ALLOWED | false | PASS |
| int-03 | Missing MODEL_LEDGER | BLOCKED | false | BLOCKED | false | PASS |
| int-04 | Missing NODE_MODEL_SUMMARY | BLOCKED | false | BLOCKED | false | PASS |
| int-05 | Missing COOLDOWN_STATE_SUMMARY | BLOCKED | false | BLOCKED | false | PASS |
| int-06 | rate_limit without ledger | BLOCKED | false | BLOCKED | false | PASS |
| int-07 | fallback without fields | BLOCKED | false | BLOCKED | false | PASS |
| int-08 | token_usage='unknown' | BLOCKED | false | BLOCKED | false | PASS |
| int-09 | rate-limit as BIN-FAIL | BLOCKED | false | BLOCKED | false | PASS |
| int-10 | NODE_SUMMARY only node | BLOCKED | false | BLOCKED | false | PASS |
| int-11 | COOLDOWN only node | BLOCKED | false | BLOCKED | false | PASS |

### Negative Path Matrix

| Scenario | Gate Result | Merge Ready | Fail-Closed |
|----------|-------------|-------------|-------------|
| Missing MODEL_LEDGER | FAIL | false | YES |
| Missing NODE_MODEL_SUMMARY | FAIL | false | YES |
| Missing COOLDOWN_STATE_SUMMARY | FAIL | false | YES |
| rate_limit=true no ledger | FAIL | false | YES |
| fallback_used=true no fields | FAIL | false | YES |
| token_usage unknown | FAIL | false | YES |
| rate-limit as BIN-FAIL | FAIL | false | YES |
| NODE_SUMMARY only node | FAIL | false | YES |
| COOLDOWN only node | FAIL | false | YES |

### Positive Path Matrix

| Scenario | Gate Result | Merge Ready |
|----------|-------------|-------------|
| Valid V1.20.5 report | PASS | true |
| Non-terminal status | N/A | false |

## Underlying Gate Verification

```
=== model_ledger_gate.py --self-check ===
  Total: 13
  Passed: 13
  Failed: 0
  Self-check: PASSED

=== model_ledger_gate.py --fixture ===
  Scenarios: 13
  Results: 13/13 passed

=== vibe_report_status_gate.py --self-check ===
  Total: 11
  Passed: 11
  Failed: 0
  Self-check: PASSED
```

## Code Classification

| Component | Type | Changed |
|-----------|------|---------|
| vibe_report_status_gate.py | workflow CLI / validator | NEW |
| model_ledger_gate.py | workflow CLI / validator | UNCHANGED |
| docs/ | documentation | NEW |

- workflow_code_changed: true (new vibe_report_status_gate.py)
- runtime_code_changed: false (no runtime service changes)

## Safety Declarations

| Declaration | Value |
|-------------|-------|
| runtime_code_changed | false |
| workflow_code_changed | true |
| credential_modified | false |
| secret_exposed | false |
| internal_ip_in_public_files | false |
| merge_executed | false |
| upgrade_performed | false |

## PR Requirements

- Branch: feat/v1207-1209-ledger-gate-integration
- Base SHA: b3a59f9271dcbc320cd79e85d2b4470d79ecd50f
- workflow_code_changed: true
- runtime_code_changed: false
- merge_requires_operator_approval: true
