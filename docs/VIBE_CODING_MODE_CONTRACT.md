# Vibe Coding Mode Contract

**Version:** 1.0.0
**Effective:** 2026-06-24
**Authority:** Operator-validated, auditable
**Parent Contracts:** [VIBE_CODING_WORKFLOW_CONTRACT.md](./VIBE_CODING_WORKFLOW_CONTRACT.md), [MODEL_POOL_DISTRIBUTION_CONTRACT.md](./MODEL_POOL_DISTRIBUTION_CONTRACT.md)

---

## Purpose

This contract defines the **mandatory, non-bypassable workflow** that activates when an agent enters Vibe Coding mode. Unlike casual conversation, Vibe Coding mode requires a fixed state machine with explicit operator gates at every critical juncture.

**Core principle:** A casual user prompt CANNOT bypass mandatory gates. The agent must automatically execute the full workflow regardless of how the request is phrased.

---

## 1. Mode Entry (mode_entry)

### 1.1 Entry Triggers

The agent enters Vibe Coding mode when ANY of the following conditions are met:

| Trigger Type | Examples | Detection Method |
|---|---|---|
| Explicit entry | "enter vibe coding mode", "start vibe coding" | Keyword match |
| Version execution | "run V1.21.29", "execute version" | Version pattern |
| Cluster operation | "dispatch to nodes", "cluster run" | Cluster keywords |
| Feature request | "implement", "create", "add", "build", "fix" | Action verbs |
| PR operation | "review PR", "merge PR", "create PR" | PR keywords |

### 1.2 Entry Requirements

Upon entering Vibe Coding mode, the agent MUST complete Step 0 before ANY other action:

1. **Acknowledge entry** - Confirm entering Vibe Coding mode
2. **Confirm target repository** - Path, branch, current HEAD SHA
3. **Confirm baseline** - Current main SHA, freeze markers
4. **Confirm local dirt status** - malicious_payload_evidence.json, pilot-prompts/
5. **Confirm operating under this contract** - State explicitly

**The agent MUST NOT begin coding, planning, or execution before completing Step 0.**

### 1.3 Non-Bypassable Rule

A casual user prompt MUST still trigger the full workflow. The agent MUST NOT skip intake, planning, or gates just because the request seems simple.

---

## 2. Mandatory Workflow (mandatory_workflow)

### 2.1 State Machine

| Step | Name | Gate Type | Description |
|---|---|---|---|
| Step 0 | Enter Mode | Auto | Acknowledge, confirm repo/baseline/dirt |
| Step 1 | Intake | Operator | Align on goal, scope, forbidden scope, success criteria |
| Step 2 | Plan Gate | Auto | Technical plan + model pool + role assignment |
| Step 3 | Approval | Operator | Approve plan, roles, scope |
| Step 4 | Execution | Quality | Implement, test, review (within approved scope) |
| Step 5 | Draft PR | Auto | Create Draft PR only, auto-Ready FORBIDDEN |
| Step 6 | Ready | Operator | Authorize Draft to Ready |
| Step 7 | Merge | Operator | Authorize merge execution |
| Step 8 | Freeze | Operator | Authorize cleanup/freeze |
| Step 9 | Complete | Auto | Report, suggest next steps, WAIT |

### 2.2 State Transitions

| From | To | Required |
|---|---|---|
| Step 0 to Step 1 | Agent acknowledges entry | Automatic |
| Step 1 to Step 2 | Operator confirms intake | Operator gate |
| Step 2 to Step 3 | Agent produces plan | Automatic |
| Step 3 to Step 4 | Operator approves plan | Operator gate |
| Step 4 to Step 5 | Tests pass + review passes | Quality gate |
| Step 5 to Step 6 | Agent creates Draft PR | Automatic |
| Step 6 to Step 7 | Operator authorizes Ready | Operator gate |
| Step 7 to Step 8 | Operator authorizes merge | Operator gate |
| Step 8 to Step 9 | Operator authorizes cleanup | Operator gate |

**No state may be skipped. No gate may be bypassed.**

---

## 3. Operator Gates (operator_gates)

### 3.1 Gate Inventory

| Gate | Step | What Operator Must Approve | Blocking? |
|---|---|---|---|
| Plan Gate | Step 3 | Technical plan, role/model assignment, scope | Yes |
| Real Exec Gate | Step 4 | Real model calls, real file modifications | Yes |
| Ready Gate | Step 6 | Draft to Ready conversion | Yes |
| Merge Gate | Step 7 | Merge execution, merge method | Yes |
| Cleanup/Freeze Gate | Step 8 | Branch deletion, freeze marker | Yes |
| Deviation Gate | Any | Scope expansion, model substitution, fallback | Yes |
| Rollback Gate | Any | Reverting changes, resetting state | Yes |

### 3.2 Gate Enforcement

Each gate MUST:
1. **Block** - Agent cannot proceed past the gate without approval
2. **Report** - Agent must present the gate request in structured format
3. **Record** - Approval must be recorded with approval_id
4. **Verify** - Agent must confirm approval before proceeding

### 3.3 Consolidation Rule

The operator MAY consolidate multiple gates into a single message. When consolidated:
- Step 3 (plan approval) is ALWAYS required separately
- Consolidation must be EXPLICIT - agent must not assume
- All consolidated gates are still recorded individually

---

## 4. Non-Bypassable Rules (non_bypassable_rules)

These rules CANNOT be bypassed by any user prompt, no matter how it is phrased:

### 4.1 Test Requirements

| Rule | Description |
|---|---|
| Targeted tests | Every code change MUST have corresponding tests |
| Test execution | Tests MUST be run and pass before commit |
| Test evidence | Test results MUST be included in the execution report |
| Pre-existing failures | Known failures MUST be documented as pre-existing |

### 4.2 Review Requirements

| Rule | Description |
|---|---|
| Mandatory review | Every PR MUST have a review from a different node/model |
| Review verdict | Reviewer MUST output REVIEW_PASS or REVIEW_BLOCKED |
| Review scope | Review covers correctness, safety, style |
| Cross-node review | Implementer and reviewer MUST be different nodes |

### 4.3 Secret Prohibition

| Rule | Description |
|---|---|
| No plaintext keys | API keys, tokens, passwords MUST NEVER appear in files, logs, reports |
| No key output | Agent MUST NEVER print, log, or return actual key values |
| No key in Git | Keys MUST NEVER be committed to any branch |
| No key in PRs | Keys MUST NEVER appear in PR diffs or bodies |
| secret_ref only | Only secret_ref identifiers may be used in configuration |

### 4.4 Debug Raw Prohibition

| Rule | Description |
|---|---|
| No raw debug output | opencode debug config raw output MUST NOT be printed |
| Redacted only | If diagnostics needed, use redacted summary only |
| No key fragments | Partial key patterns MUST NOT appear |

### 4.5 Fallback Prohibition

| Rule | Description |
|---|---|
| No auto-fallback | Agent MUST NOT automatically switch to a different model/provider |
| No provider discovery | Agent MUST NOT run provider discovery without explicit approval |
| Stop on failure | If model call fails, STOP and report - do not retry with different model |
| Operator decides | Model substitution requires explicit operator approval |

### 4.6 Main Protection

| Rule | Description |
|---|---|
| No direct push to main | All changes MUST go through feature branches + PRs |
| No main modification | Execution MUST NOT modify files on main branch |
| Main SHA invariant | main SHA MUST remain unchanged during execution |

### 4.7 Local Dirt Protection

| Rule | Description |
|---|---|
| malicious_payload_evidence.json | MUST exist, MUST be tracked, MUST NOT be cleaned/committed |
| pilot-prompts/ | MUST exist, MUST be untracked, MUST NOT be cleaned/committed |
| No git clean | git clean, git reset --hard MUST NOT be used |
| No checkout overwrite | git checkout, git restore MUST NOT overwrite local dirt |

---

## 5. Report Schema (report_schema)

### 5.1 PLAN_APPROVAL_REQUEST

Presented at Step 3 (Plan Gate). Must include:
- Phase info: phase_id, phase_name, approval_id, workorder_id
- Technical plan: Goal, approach, files to modify, files NOT to modify, test strategy, risk assessment
- Model pool: Available/Non-available tables per MODEL_POOL_DISTRIBUTION_CONTRACT
- Role assignment: Role, Node, Model, Task Scope table
- Scope boundaries: Allowed and forbidden lists
- Operator decision: action_needed (APPROVE_PLAN / REQUEST_REVISION / BLOCK)

### 5.2 EXECUTION_GATE_REPORT

Presented at every gate (Steps 4-8). Must include:
- Phase info: phase_id, phase_name, approval_id, operator_action_needed, final_verdict
- PR status: URL, number, state, isDraft, mergedAt, headRefOid, baseRefOid, mergeable, mergeStateStatus
- Scope compliance: Boundary, Expected, Actual, Status table
- Role/model report: Role/Actor, planned_provider_model, actual_provider_model, calls, duration, fallback, usage table
- Tests: Test Suite, Result, Notes table
- Safety checks: key leakage, debug raw output, fallback, local dirt preserved
- Deviations: ID, Description, Risk, Recommendation table
- Final verdict: PASS/BLOCKED

### 5.3 Bilingual Requirement

| Content Type | Language |
|---|---|
| Titles | English + Chinese |
| Long paragraphs | Chinese primarily, with English technical terms |
| Fixed field names | English only (phase_id, approval_id, etc.) |
| Status enums | English only (PASS, BLOCKED, CLEAN, etc.) |
| Risk explanations | Chinese |
| Operator decision explanations | Chinese |

---

## 6. Role/Model Reporting (role_model_reporting)

### 6.1 Mandatory Fields

Every role in every execution MUST report:

| Field | Required | Description |
|---|---|---|
| Role/Actor | Yes | Orchestrator, Implementer, Reviewer, Tester, etc. |
| planned_provider_model | Yes | What model was planned in the approval |
| actual_provider_model | Yes | What model was actually used |
| calls | Yes | Number of model API calls |
| duration | Yes | Total execution time |
| fallback | Yes | Whether fallback occurred (YES/NO) |
| usage/token/cost | Yes | Token counts, cost if available |

### 6.2 No-Call Reporting

If a role made NO model calls (e.g., manual review), report actual_provider_model=N/A, calls=0, and explain why.

### 6.3 Fallback Reporting

If fallback occurred (which requires explicit operator approval), report both planned and actual models with explanation.

---

## 7. Dispatch Policy (dispatch_policy)

### 7.1 Single-Node Dispatch

**When to use:** Simple, low-risk tasks; single file change; no cross-node dependencies
**Requirements:** One implementer; reviewer MUST be different node; tests on same node

### 7.2 Three-Node Dispatch

**When to use:** Medium complexity; multiple files; need parallel implementation + review
**Requirements:** Implementer on one node; reviewer on different node; tester on third node; all nodes online

### 7.3 Parallel Queue Dispatch

**When to use:** Multiple independent tasks; batch processing; maximum throughput
**Requirements:** Each task gets own branch/implementer; cross-review between tasks; independent commit/push/PR; all Draft PRs

### 7.4 Dispatch Selection

The Orchestrator RECOMMENDS dispatch mode based on task complexity, file count, cross-dependencies, risk level, and operator preference. **Operator has final say.**

---

## 8. Deviation Policy (deviation_policy)

### 8.1 Deviation Types

| ID | Type | Description | Risk Level |
|---|---|---|---|
| D1 | Manual Review Fallback | Reviewer uses manual review instead of model | Low |
| D2 | Rate Limit Hit | 429/529 errors during model calls | Low |
| D3 | Scope Expansion | Need to modify files outside approved scope | High |
| D4 | Model Substitution | Need to use different model than planned | Medium |
| D5 | Timeout | Execution exceeds expected duration | Medium |
| D6 | Test Flakiness | Intermittent test failures | Medium |

### 8.2 Deviation Reporting

Every deviation MUST be reported in the EXECUTION_GATE_REPORT with ID, Description, Risk, and Recommendation.

### 8.3 Deviation Approval

| Risk Level | Approval Required |
|---|---|
| Low | Report only, no explicit approval needed |
| Medium | Report + operator acknowledgment |
| High | Explicit operator approval required before proceeding |

### 8.4 Known Deviations (Pre-Approved)

| ID | Condition | Pre-Approval |
|---|---|---|
| D1 | Manual review when opencode config fails | Accept if REVIEW_PASS |
| D2 | 429 rate limit with successful retry | Accept if task completes |
| D3 | Scope expansion | NOT pre-approved - always requires operator |

---

## 9. Cross-Repo Grey-Use Policy (cross_repo_policy)

### 9.1 Scope

This policy applies when using Vibe Coding mode on repositories OTHER than the primary vibe-coding-repo, including Hermes Agent official repository, third-party repositories, and forked repositories.

### 9.2 Isolation Requirements

| Requirement | Description |
|---|---|
| Fork first | Always work on a fork, never directly on upstream |
| Draft PR only | All PRs default to Draft |
| No auto-Ready | Converting Draft to Ready requires explicit operator approval |
| No auto-merge | Merging requires explicit operator approval |
| No auto-push to main | All changes go through feature branches + PRs |

### 9.3 Hermes Official Repository Grey-Use

When working on the Hermes Agent official repository:

| Rule | Description |
|---|---|
| Isolation | Work only on fork, never push to upstream directly |
| Draft PR | All PRs must be Draft |
| No auto-Ready | Operator must explicitly authorize Ready |
| No auto-merge | Operator must explicitly authorize merge |
| No auto-cleanup | Operator must explicitly authorize cleanup/freeze |
| No production impact | Changes must not affect production Hermes instances |

### 9.4 Grey-Use Readiness Verdict

Before engaging in cross-repo grey-use, the agent MUST:
1. Confirm fork exists and is up-to-date
2. Confirm Draft PR workflow is configured
3. Confirm no auto-Ready/merge is possible
4. Report GREY_USE_READY or GREY_USE_BLOCKED

---

## 10. Rollback Policy

### 10.1 Rollback Triggers

| Trigger | Action |
|---|---|
| Test failure | Revert to last passing commit |
| Review BLOCKED | Revert to last reviewed commit |
| Scope violation | Revert to approved scope |
| Key leakage | IMMEDIATE revert + report |
| Operator instruction | Revert as instructed |

### 10.2 Rollback Procedure

1. **STOP** - Halt all execution immediately
2. **PRESERVE** - Do not delete worktree, logs, or artifacts
3. **REPORT** - Report what happened and why rollback is needed
4. **WAIT** - Wait for operator instruction before proceeding

### 10.3 Rollback Gate

Rollback requires operator approval except for:
- Key leakage (immediate rollback, then report)
- Test failure (automatic revert to last passing, then report)

---

## 11. Enforcement

This contract is enforced by:

1. **conversational_intake_gate.py** - Detects when intake is required
2. **execution_approval_gate.py** - Blocks execution without approval
3. **git_pr_approval_gate.py** - Enforces PR state transitions
4. **VIBE_CODING_WORKFLOW_CONTRACT.md** - Authoritative workflow definition
5. **MODEL_POOL_DISTRIBUTION_CONTRACT.md** - Model pool governance
6. **This contract** - Mandatory mode workflow and non-bypassable rules

---

## 12. Chinese Quick Reference

| Step | Action | Who Decides |
|---|---|---|
| Mode Entry | Any coding request must enter vibe coding mode | Automatic |
| Intake | Goal, scope, forbidden scope, success criteria | Operator confirms |
| Technical Plan | Approach, files, tests, risks | Orchestrator proposes |
| Role Assignment | Node, model, task scope | Operator approves |
| Execution | Code, test, review | Per authorization |
| Draft PR | Default Draft, auto-Ready forbidden | Automatic |
| Ready | Must be separately authorized | Operator |
| Merge | Must be separately authorized | Operator |
| Cleanup/Freeze | Must be separately authorized | Operator |
| Deviation | Report + risk assessment + approval | Operator |
| Rollback | Stop + preserve + report + wait | Operator |

---

## 10. Runtime Enforcement (runtime_enforcement)

### 10.1 Implementation Reference

The runtime enforcement functions are implemented in `scripts/conversational_intake_gate.py` and documented in [VIBE_CODING_MODE_RUNTIME_INTEGRATION.md](./VIBE_CODING_MODE_RUNTIME_INTEGRATION.md).

### 10.2 Mandatory Function Calls

| Function | When to Call | Purpose |
|---|---|---|
| `detect_mode_entry(text)` | Every incoming message | Detect vibe coding mode entry triggers |
| `check_cross_repo_guard(text)` | Before external repo operations | Block cross-repo without PLAN_APPROVAL_REQUEST |
| `compile_casual_prompt(text)` | Every casual/voice request | Convert to structured intake |
| `generate_plan_approval_request(...)` | Before any execution action | Produce operator gate request |

### 10.3 Non-Bypassable Enforcement

The agent MUST call `detect_mode_entry()` before processing any message. If `mode_active=True`, the agent MUST enter the mandatory workflow (Step 0 → Step 1 → ... → Step 9). No exceptions.

The agent MUST NOT:
- Skip `detect_mode_entry()` for any message
- Proceed with research/implementation without PLAN_APPROVAL_REQUEST
- Execute actions in `FORBIDDEN_ACTIONS` set
- Bypass cross-repo guard for external repo operations

---

*This contract is the single source of truth for Vibe Coding mode workflow. If any other document conflicts, this document wins.*
