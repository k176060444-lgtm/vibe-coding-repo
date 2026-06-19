# V1.20.7/8/9 Ledger Gate Integration Report

Generated: 2026-06-19T16:00:00Z
Branch: feat/v1207-1209-ledger-gate-integration
Base SHA: b3a59f9271dcbc320cd79e85d2b4470d79ecd50f
Integration Type: REAL (not helper-only)

## Preflight Results

| Check | Expected | Actual | Status |
|-------|----------|--------|--------|
| Windows HEAD | b3a59f92... | b3a59f9271dcbc320cd79e85d2b4470d79ecd50f | PASS |
| 5bao OpenCode | 1.17.8 | SSH not available (key not on Windows) | UNVERIFIED |
| 9bao OpenCode | 1.17.8 | SSH not available (key not on Windows) | UNVERIFIED |
| Binary SHA256 | ea9f0e72... | Cannot verify without SSH | UNVERIFIED |
| V1.20.6 gate | 13/13 | 13/13 | PASS |
| V1.17.7 freeze | 547da273 | exists | PASS |

Note: 5bao/9bao OpenCode version and binary SHA256 cannot be independently verified
because SSH credentials (debian-vibeworker-ed25519) are not present on the Windows
build machine. The baseline of 1.17.8 is accepted per Operator's trusted baseline declaration.

## Changed Files

| File | Change | Lines |
|------|--------|-------|
| scripts/vibe_run_report.py | v1.0.0 -> v1.1.0: added ledger gate import + check | ~25 added |
| scripts/vibe_merge_gate.py | added ledger gate import + check + output | ~35 added |
| docs/V1207_1208_1209_LEDGER_GATE_INTEGRATION.md | updated for real integration | rewritten |
| docs/reports/V1207_1208_1209_LEDGER_GATE_INTEGRATION_REPORT.md | this report | rewritten |

## Real Integration Details

### vibe_run_report.py (V1.20.7)

- Imports `vibe_report_status_gate.check_report_status`
- After building result dict, if qg_verdict is terminal:
  - Runs `check_report_status(result)`
  - On FAIL: downgrades verdict to `BLOCKED_BY_LEDGER_GATE`
  - On PASS: records `ledger_gate.result = PASS`
- Adds `ledger_gate` section to markdown output
- Fail-closed: missing MODEL_LEDGER -> BLOCKED

### vibe_merge_gate.py (V1.20.8)

- Imports `model_ledger_gate.validate_report`
- Before `allow_merge` determination:
  - If job status is terminal: runs gate validation
  - On FAIL: adds blocker, merge blocked
  - Adds `model_ledger_gate` to result dict
- Fail-closed: missing ledger fields -> merge blocked

## Validation Results

### py_compile: ALL OK

```
scripts/vibe_run_report.py: OK
scripts/vibe_merge_gate.py: OK
scripts/vibe_report_status_gate.py: OK
scripts/model_ledger_gate.py: OK
```

### model_ledger_gate.py --self-check: 13/13 PASSED

### vibe_report_status_gate.py --self-check: 11/11 PASSED

### model_ledger_gate.py --fixture: 13/13 PASSED

## Integration Test Matrix

| ID | Description | Gate | Expected | Status |
|----|-------------|------|----------|--------|
| int-01 | Valid V1.20.5 report (3 live + 2 fixture) | status | ALLOWED, merge=true | PASS |
| int-02 | Non-terminal (IN_PROGRESS) | status | ALLOWED, merge=false | PASS |
| int-03 | Missing MODEL_LEDGER | status | BLOCKED, merge=false | PASS |
| int-04 | Missing NODE_MODEL_SUMMARY | status | BLOCKED, merge=false | PASS |
| int-05 | Missing COOLDOWN_STATE_SUMMARY | status | BLOCKED, merge=false | PASS |
| int-06 | rate_limit without ledger | status | BLOCKED, merge=false | PASS |
| int-07 | fallback without fields | status | BLOCKED, merge=false | PASS |
| int-08 | token_usage='unknown' | status | BLOCKED, merge=false | PASS |
| int-09 | rate-limit as BIN-FAIL | status | BLOCKED, merge=false | PASS |
| int-10 | NODE_SUMMARY only node | status | BLOCKED, merge=false | PASS |
| int-11 | COOLDOWN only node | status | BLOCKED, merge=false | PASS |

## Negative Path Matrix (Fail-Closed)

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

## GitHub Hidden/Bidi Unicode Check

Scanned all changed files (byte-level):
- 0 non-ASCII bytes in both markdown files
- 0 BOM, 0 bidi control chars, 0 zero-width chars
- GitHub PR files page: NO hidden/bidi warnings detected
- GitHub blob API decoded content: 100% ASCII

## Code Classification

| Component | Type | Changed |
|-----------|------|---------|
| vibe_run_report.py | real workflow entry point | MODIFIED (v1.0.0 -> v1.1.0) |
| vibe_merge_gate.py | real workflow entry point | MODIFIED |
| vibe_report_status_gate.py | gate script | UNCHANGED |
| model_ledger_gate.py | underlying gate | UNCHANGED |
| docs/ | documentation | UPDATED |

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
| hidden_bidi_unicode | false (verified) |

## OpenCode Version Note

5bao/9bao OpenCode version (1.17.8) and binary SHA256 (ea9f0e72...) cannot be
independently verified from this build because SSH key (debian-vibeworker-ed25519)
is not present on the Windows machine. These values are accepted from Operator's
trusted baseline declaration. If independent verification is required, Operator
must provide SSH access or verify manually on each node.

## PR Requirements

- Branch: feat/v1207-1209-ledger-gate-integration
- Base SHA: b3a59f9271dcbc320cd79e85d2b4470d79ecd50f
- workflow_code_changed: true
- runtime_code_changed: false
- merge_requires_operator_approval: true
