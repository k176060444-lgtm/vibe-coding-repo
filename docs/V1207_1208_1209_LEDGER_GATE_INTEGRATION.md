# V1.20.7/8/9 Ledger Gate Integration

Version: V1.20.7_8_9
Status: ACTIVE (REAL INTEGRATION)
Enforced by: Report Status Gate, Merge Readiness Gate, vibe_run_report.py, vibe_merge_gate.py

## Overview

Integrates model_ledger_gate into real report/status output and merge readiness paths.
This is NOT a helper script — it modifies actual workflow entry points.

## Real Integration Points

### V1.20.7: Report Status Gate — vibe_run_report.py (MODIFIED)

`scripts/vibe_run_report.py` v1.1.0 now imports `vibe_report_status_gate` and runs
`check_report_status()` after generating the report dict.

**Behavior:**
- If quality_gate verdict is PASS/MERGE_READY/FREEZE_PASS/PROMOTION_PASS:
  - Run `check_report_status(result)`
  - If gate FAILS: verdict downgraded to `BLOCKED_BY_LEDGER_GATE`
  - If gate PASSES: `ledger_gate.result = PASS`
- If verdict is non-terminal: `ledger_gate.result = N/A`
- If gate import fails: `ledger_gate.result = GATE_UNAVAILABLE`

**Fail-closed:** Terminal verdict without valid MODEL_LEDGER/NODE_MODEL_SUMMARY/COOLDOWN_STATE_SUMMARY -> BLOCKED.

### V1.20.8: Merge Gate — vibe_merge_gate.py (MODIFIED)

`scripts/vibe_merge_gate.py` now imports `model_ledger_gate` and runs `validate_report()`
on job info when job status is terminal.

**Behavior:**
- If job status is terminal (PASS/MERGE_READY/FREEZE_PASS/PROMOTION_PASS):
  - Build gate report from job_info (MODEL_LEDGER, NODE_MODEL_SUMMARY, COOLDOWN_STATE_SUMMARY)
  - Run `validate_report(gate_report)`
  - If errors: add blocker, merge blocked
- If job status is non-terminal: gate not checked
- If gate import fails: result = GATE_UNAVAILABLE

**Output fields:**
- `model_ledger_gate.checked`: bool
- `model_ledger_gate.result`: "PASS" / "FAIL" / "N/A" / "GATE_UNAVAILABLE"
- `model_ledger_gate.errors`: list (if FAIL)

### V1.20.9: Failure Injection / Negative Path Validation

Integration tests verify fail-closed behavior via `vibe_report_status_gate.py --self-check` (11 scenarios).

## Changed Files

| File | Change | Type |
|------|--------|------|
| scripts/vibe_run_report.py | Added ledger gate integration (v1.0.0 -> v1.1.0) | MODIFIED |
| scripts/vibe_merge_gate.py | Added ledger gate integration | MODIFIED |
| scripts/vibe_report_status_gate.py | Report status + merge readiness gate | UNCHANGED |
| scripts/model_ledger_gate.py | Underlying gate (13 rules) | UNCHANGED |
| docs/V1207_1208_1209_LEDGER_GATE_INTEGRATION.md | This doc | UPDATED |
| docs/reports/V1207_1208_1209_LEDGER_GATE_INTEGRATION_REPORT.md | Report | UPDATED |

## Validation Commands

```bash
# Compile check
python -m py_compile scripts/vibe_run_report.py
python -m py_compile scripts/vibe_merge_gate.py
python -m py_compile scripts/vibe_report_status_gate.py
python -m py_compile scripts/model_ledger_gate.py

# Self-checks
python scripts/model_ledger_gate.py --self-check           # 13/13
python scripts/vibe_report_status_gate.py --self-check      # 11/11
python scripts/model_ledger_gate.py --fixture docs/reports/model-ledger-gate-fixture.json  # 13/13
```

## Safety

- No live model calls
- No credential/secret access
- No network calls
- Read-only validation
- workflow_code_changed=true (modified vibe_run_report.py, vibe_merge_gate.py)
- runtime_code_changed=false
