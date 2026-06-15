# Real Feature Demo: From Natural Language to Verified Execution

**Status:** DEMONSTRATION DOCUMENT (not auto-executed)
**Purpose:** Show how to use the current toolchain to go from a natural language requirement to a verified execution trace.
**Scope:** Documentation only — no model calls, no real execution, no side effects.

---

## Scenario

**Requirement:** "Add a --verbose flag to the health check script that shows detailed per-component status."

This document walks through the complete autonomous loop using this requirement as an example.

---

## Step 1: Intake (NL → Draft)

Convert the natural language requirement into a structured workorder draft.

```bash
python3 scripts/vibe_workorder_intake.py "Add a --verbose flag to the health check script that shows detailed per-component status" --json
```

**Expected Output:**
```json
{
  "workorder_id": "wo-code-health-verbose-001",
  "title": "Add --verbose flag to health check",
  "type": "code",
  "risk_level": "low",
  "description": "Add a --verbose flag to vibe_health_check.py that shows detailed per-component status",
  "changed_paths": ["scripts/vibe_health_check.py"],
  "requires_human_approval": false
}
```

---

## Step 2: Validate (Draft → PASS/WARN/FAIL)

Validate the draft against schema and safety rules.

```bash
python3 scripts/vibe_workorder_validator.py /tmp/draft.json --json
```

**Expected Output:**
```json
{
  "verdict": "PASS",
  "errors": [],
  "warnings": []
}
```

---

## Step 3: Package (Draft → Prompt)

Package the validated draft into a structured prompt for the coding agent.

```bash
python3 scripts/vibe_workorder_packager.py /tmp/draft.json --json --compact
```

**Expected Output:**
```json
{
  "workorder_id": "wo-code-health-verbose-001",
  "prompt": "...",
  "segments": 1,
  "total_chars": 1234
}
```

---

## Step 4: Register (Draft → Registry Entry)

Register the workorder in the registry with initial status.

```bash
python3 scripts/vibe_workorder_registry.py register --id wo-code-health-verbose-001 --title "Add --verbose flag" --risk-level low --base-sha <current_main_sha>
```

**Expected Output:**
```
Registered: wo-code-health-verbose-001 (draft)
```

---

## Step 5: Status Update (draft → validated → packaged → approved)

Advance the workorder through the controlled status pipeline.

```bash
# draft → validated
python3 scripts/vibe_workorder_registry.py update-status --id wo-code-health-verbose-001 --status validated --reason "validator PASS"

# validated → packaged
python3 scripts/vibe_workorder_registry.py update-status --id wo-code-health-verbose-001 --status packaged --reason "packager OK"

# packaged → approved
python3 scripts/vibe_workorder_registry.py update-status --id wo-code-health-verbose-001 --status approved --reason "human approved"
```

---

## Step 6: Approval Receipt (Approved → Receipt with Digest)

Create an approval receipt with SHA256 digest for audit trail.

```bash
python3 scripts/vibe_approval_receipt.py create --id wo-code-health-verbose-001 --base-sha <current_main_sha>
```

**Expected Output:**
```json
{
  "receipt_id": "receipt-001",
  "workorder_id": "wo-code-health-verbose-001",
  "base_sha": "<current_main_sha>",
  "digest": "sha256:abc123...",
  "timestamp": "2026-06-15T...",
  "requires_human_approval": false
}
```

---

## Step 7: Execution Gate (Receipt → ALLOW/REVIEW/BLOCK)

Run the 8-condition admission check.

```bash
python3 scripts/vibe_execution_gate.py check --id wo-code-health-verbose-001 --current-main-sha <current_main_sha> --json
```

**Expected Output (for this low-risk task):**
```json
{
  "verdict": "ALLOW",
  "checks": {
    "registry_approved": "PASS",
    "receipt_exists": "PASS",
    "base_sha_match": "PASS",
    "risk_assessment": "PASS",
    "stop_conditions": "PASS",
    "allowed_paths": "PASS",
    "forbidden_high_risk": "PASS",
    "audit_lock": "PASS"
  }
}
```

---

## Step 8: Executor Adapter Plan (ALLOW → Plan)

Generate an execution plan using the adapter contract.

```bash
python3 scripts/vibe_executor_adapter.py plan --adapter dry-run --id wo-code-health-verbose-001 --base-sha <current_main_sha> --json
```

**Expected Output:**
```json
{
  "adapter_name": "dry-run",
  "mode": "dry-run",
  "execution_plan": {
    "steps": [
      {"step": 1, "action": "validate-gate", "description": "Verify gate verdict is ALLOW"},
      {"step": 2, "action": "validate-inputs", "description": "Check required fields present"},
      {"step": 3, "action": "simulate-worktree", "description": "Simulate worktree creation"},
      {"step": 4, "action": "simulate-implementation", "description": "Simulate code changes"},
      {"step": 5, "action": "simulate-commit", "description": "Simulate commit"},
      {"step": 6, "action": "simulate-pr", "description": "Simulate PR creation"},
      {"step": 7, "action": "simulate-merge", "description": "Simulate merge"},
      {"step": 8, "action": "write-transcript", "description": "Write dry-run transcript"}
    ],
    "total_steps": 8
  },
  "refused_actions": ["model_call", "shell_exec", "repo_write", "git_push", "git_merge", "deploy", "tag", "file_delete"]
}
```

---

## Step 9: Transcript (Plan → Append-Only Record)

Record the execution as an append-only transcript.

```bash
python3 scripts/vibe_execution_transcript.py create --id wo-code-health-verbose-001 --adapter dry-run --base-sha <current_main_sha> --json
```

**Expected Output:**
```json
{
  "transcript_id": "txn-001",
  "workorder_id": "wo-code-health-verbose-001",
  "adapter": "dry-run",
  "status": "completed",
  "digest": "sha256:def456...",
  "side_effects": "none"
}
```

---

## Step 10: Execution Evidence (Transcript → Evidence Bundle)

Create an evidence bundle aggregating all execution artifacts.

```bash
python3 scripts/vibe_execution_evidence.py create --id wo-code-health-verbose-001 --base-sha <current_main_sha> --result-sha <result_sha> --json
```

---

## Step 11: Evidence Verifier (Evidence → PASS/WARN/FAIL)

Verify the evidence bundle integrity.

```bash
python3 scripts/vibe_evidence_verifier.py verify --evidence-dir /path --registry-dir /path --evidence-id ev-001 --json
```

**Expected Output:**
```json
{
  "verdict": "PASS",
  "checks": {
    "required_fields": "PASS",
    "digest_match": "PASS",
    "registry_entry": "PASS",
    "approval_receipt": "PASS",
    "sha_present": "PASS",
    "smoke_result": "PASS",
    "job_audit_status": "PASS",
    "changed_paths_scope": "PASS"
  }
}
```

---

## Step 12: Loop Summary (Verify → Summary)

Generate a summary of the complete chain.

```bash
python3 scripts/vibe_loop_summary.py --compact
```

---

## Complete Chain Visualization

```
Natural Language Requirement
    │
    ▼
┌─────────────┐
│   intake    │  NL → structured draft
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  validator  │  draft → PASS/WARN/FAIL
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  packager   │  draft → prompt segments
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  registry   │  register (status: draft)
│             │  update-status: draft→validated→packaged→approved
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  receipt    │  SHA256 digest + approval record
└─────┬───────┘
      │
      ▼
┌─────────────┐
│    gate     │  8-condition check → ALLOW/REVIEW/BLOCK
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  adapter    │  plan (noop/dry-run only, FROZEN)
└─────┬───────┘
      │
      ▼
┌─────────────┐
│ transcript  │  append-only execution record
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  evidence   │  aggregated audit bundle
└─────┬───────┘
      │
      ▼
┌─────────────┐
│  verifier   │  integrity check → PASS/WARN/FAIL
└─────┬───────┘
      │
      ▼
┌─────────────┐
│   summary   │  chain overview + gaps + next steps
└─────────────┘
```

---

## Key Observations

1. **The entire chain is traceable** — every step produces artifacts that the next step can verify.
2. **The executor boundary is frozen** — only noop/dry-run adapters are permitted.
3. **Human approval is the critical checkpoint** — step 7 (gate) requires explicit authorization for real execution.
4. **Audit trail is complete** — registry, receipt, transcript, evidence, and verifier form a closed loop.
5. **No side effects in current mode** — all adapters refuse model_call, shell_exec, repo_write, git_push, git_merge, deploy, tag, file_delete.

---

## Current Limitations

- **No real execution** — the adapter boundary is frozen at noop/dry-run.
- **No real model calls** — cannot generate code changes.
- **No real PR creation** — cannot create GitHub PRs from execution results.
- **No rollback** — no mechanism to undo failed executions.

---

## References

- `docs/EXECUTOR_BOUNDARY_FREEZE.md` — frozen executor boundaries
- `docs/WORKFLOW.md` — complete workflow documentation
- `docs/COMMANDS.md` — all CLI commands and usage
- `scripts/vibe_loop_summary.py` — chain capability overview
- `scripts/test_executor_replay.py` — replay integration tests
