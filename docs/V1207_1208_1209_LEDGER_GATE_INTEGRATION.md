# V1.20.7/8/9 Ledger Gate Integration

Version: V1.20.7_8_9
Status: ACTIVE
Enforced by: Report Status Gate, Merge Readiness Gate

## Overview

Integrates model_ledger_gate into the report/status output and merge readiness paths.

### V1.20.7: Report Status Gate Integration

Any report outputting terminal status (PASS, MERGE_READY, FREEZE_PASS,
PROMOTION_PASS) must first pass model_ledger_gate.

**Entry point:** `scripts/vibe_report_status_gate.py --report REPORT_JSON`

**Behavior:**
- If report has terminal status + gate passes -> STATUS ALLOWED
- If report has terminal status + gate fails -> STATUS BLOCKED
- If report has non-terminal status -> gate not applicable, allowed

### V1.20.8: Merge Gate Integration

PR/merge readiness must include model_ledger_gate result.

**Entry point:** `scripts/vibe_report_status_gate.py --merge-readiness REPORT_JSON`

**Output fields:**
- `merge_ready`: bool (true only if terminal status + gate passed)
- `model_ledger_gate_result`: "PASS" or "FAIL"
- `gate_exit_code`: 0 or 1
- `failure_reasons`: list of gate errors
- `terminal_status_found`: the terminal status found (or null)

### V1.20.9: Failure Injection / Negative Path Validation

Integration tests verify fail-closed behavior:

| Scenario | Expected |
|----------|----------|
| Valid V1.20.5 report (3 live + 2 fixture) | ALLOWED, merge_ready=true |
| Non-terminal status (IN_PROGRESS) | ALLOWED, merge_ready=false |
| Missing MODEL_LEDGER | BLOCKED, merge_ready=false |
| Missing NODE_MODEL_SUMMARY | BLOCKED, merge_ready=false |
| Missing COOLDOWN_STATE_SUMMARY | BLOCKED, merge_ready=false |
| rate_limit=true without RATE_LIMIT_EVENT_LEDGER | BLOCKED, merge_ready=false |
| fallback_used=true without from/to/reason | BLOCKED, merge_ready=false |
| token_usage='unknown' | BLOCKED, merge_ready=false |
| Rate limit misclassified as BIN-FAIL | BLOCKED, merge_ready=false |
| NODE_MODEL_SUMMARY only has node | BLOCKED, merge_ready=false |
| COOLDOWN_STATE_SUMMARY only has node | BLOCKED, merge_ready=false |

## Usage

```bash
# Self-check integration tests
python scripts/vibe_report_status_gate.py --self-check

# Validate a report
python scripts/vibe_report_status_gate.py --report report.json

# Check merge readiness
python scripts/vibe_report_status_gate.py --merge-readiness report.json

# Validate underlying gate
python scripts/model_ledger_gate.py --self-check
python scripts/model_ledger_gate.py --fixture docs/reports/model-ledger-gate-fixture.json
```

## Integration Points

1. **Report export** (`vibe_report_export.py`, `vibe_run_report.py`, `vibe_daily_report.py`)
   - Before emitting PASS/MERGE_READY/FREEZE_PASS/PROMOTION_PASS
   - Call `check_report_status(report)` and block if status_allowed=False

2. **Merge gate** (`vibe_merge_gate.py`)
   - Before allowing merge-ready
   - Call `check_merge_readiness(report)` and block if merge_ready=False

3. **Quality gate** (`vibe_quality_gate.py`)
   - Include gate result in quality checks

## Safety

- No live model calls
- No credential/secret access
- No network calls
- Read-only validation
- workflow_code_changed=true (new integration script)
- runtime_code_changed=false
