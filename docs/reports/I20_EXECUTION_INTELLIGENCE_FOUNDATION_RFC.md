# I20 — Execution Intelligence Foundation RFC

**Status:** RFC (evaluation only — no schema implementation, no algorithm, no dispatch change)
**Phase:** v1.21.33I20_EXECUTION_INTELLIGENCE_FOUNDATION_RFC
**Date:** 2026-06-27
**Author:** VibeDev Orchestrator
**Dependencies:** I19 merged (github/main=76e1e03), I19A PR #257 pending

---

## 1. Problem Statement

VibeDev has accumulated execution evidence across multiple phases — I16E live smoke (16 calls), I17 metadata, I18 enablement, I19 governance, and dozens of phase execution reports. However, this evidence is **dispersed across format boundaries**:

- **Execution reports** embed evidence inline as YAML in chat messages.
- **Worker evidence templates** define fields but no unified schema.
- **Dispatch manifests** (I19) capture planned vs. actual at the phase level but not per-call granularity.
- **Approval receipts** are implicit (operator's NL approval) with no structured record.
- **Test results** verify correctness but don't feed back into model selection intelligence.

Without a unified **Execution Record Schema**, future efforts to:
- Score model reliability across phases
- Rank models for specific task types
- Audit multi-phase trends
- Power a recommendation engine

…will require manual correlation across disparate formats, which is error-prone and non-scalable.

**Goal of I20:** Define a single, provider-agnostic, phase-independent **Execution Record Schema** and a companion **Evaluation Schema** that can unify evidence across all VibeDev activities — without implementing any scoring, recommendation, or dispatch logic.

---

## 2. Existing Artifacts Reviewed

Before designing the schema, this RFC reviewed the following existing structures:

### 2.1 I19 Dispatch Manifest Schema (merged, main)

```json
{
  "manifest_schema_version": "1.0",
  "phase_id": "...",
  "approval_id": "...",
  "source_model_pool_head": "...",
  "scope": {},
  "assignments": [ { "role": "...", "provider": "...", ... } ],
  "execution_result": { "planned_vs_actual_ok": true, "total_calls": N }
}
```

**Gap addressed by I20:** Execution records need per-call granularity (not just phase totals) plus structured fields for tokens, duration, language, task type, and test/merge outcomes.

### 2.2 I19A Dispatch Manifest Enhancement RFC (PR #257)

```json
{
  "recommendation_source": { "recommended_by": "vibedev-route-all", ... },
  "operator_decision": { "decision": "accept", ... },
  "assignments": [ { "recommended": {}, "approved": {}, "operator_match": true } ]
}
```

**Gap addressed by I20:** The manifest captures *who recommended* and *who approved*, but not *what happened during execution* at the individual-evidence level. Execution Records bridge this gap.

### 2.3 Worker Evidence Template (`docs/reports/worker-evidence-template.md`)

```yaml
job_id, worker, task_type, planned_model, actual_model,
provider, call_count, token_usage, duration,
changed_paths, test_result, review_verdict, fallback_used
```

**Gap addressed by I20:** This is the closest existing schema but lacks: phase_id, approval_id, dispatch_manifest_version, role, language, exit_status, operator_result, files_changed, tests_summary, merge_result, evidence_refs, and evaluation fields. I20 unifies and extends this.

### 2.4 Phase Execution Reports (V1.x series, ~20 documents)

Each phase report contains a `final_verdict`, gate results, test evidence, and security checks — but in **free-form YAML** with no fixed schema. I20 does not mandate retrofitting, but provides a `evidence_refs` field to link reports.

### 2.5 Test Files (I16 through I19)

Test files verify assertions about model pool, governance, and metadata — but do **not** produce structured execution records. I20 does not require tests to emit records, but the schema should be compatible with test output formats.

---

## 3. Execution Record Schema

### 3.1 Core Record

Each single execution (one model call within a role within a phase) produces one Execution Record:

```json
{
  "execution_id": "exec_XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX",
  "schema_version": "1.0",
  "created_at": "2026-06-27T12:00:00Z",

  "phase_id": "v1.21.33I16E_OPENCODE_GO_8_MODEL_DUAL_NODE_LIVE_SMOKE",
  "work_order_id": "wo_i16e_001",
  "approval_id": "app_XXXXXXXX",

  "dispatch_manifest_version": "1.0",
  "dispatch_manifest_reference": "docs/manifests/v1.21.33I16E.json",

  "provider": "opencode-go",
  "model_id": "opencode-go-deepseek-v4-flash",
  "model_alias": "opencode-ds4flash",

  "node": "5bao",
  "transport": "ssh",
  "role": "tester-a",
  "task_type": "live-smoke",
  "language": "en",

  "planned_calls": 1,
  "actual_calls": 1,
  "fallback_count": 0,
  "fallback_models_attempted": [],

  "duration_ms": 4523,
  "prompt_tokens": null,
  "completion_tokens": null,
  "total_tokens": null,

  "exit_status": "completed",
  "exit_code": 0,

  "exact_string": "OPENCODE_GO_8MODEL_OK",
  "exact_match": true,

  "review_result": "PASS",
  "operator_result": "approved",
  "operator_notes": null,

  "files_changed": ["scripts/model_pool.yaml"],
  "files_changed_count": 1,
  "tests_summary": {
    "test_files": ["tests/test_i17_opencode_go_metadata.py"],
    "total": 9,
    "passed": 9,
    "failed": 0,
    "skipped": 0
  },
  "merge_result": "merged",
  "merge_commit_sha": "634e6b3bd56535b39d8570ba7774e162159e3b83",

  "evidence_refs": [
    "docs/reports/V1.21.33I16_RUNTIME_SYNC_AUDIT_RECORD.md",
    "docs/reports/I17_ENABLE_STRATEGY_ASSESSMENT.md"
  ],

  "redaction_check": {
    "secret_scan_passed": true,
    "hidden_bidi_scan_passed": true,
    "forbidden_files_check_passed": true
  }
}
```

### 3.2 Field Dictionary

| # | Field | Type | Required | Description |
|---|---|---|---|---|
| 1 | `execution_id` | UUID string | Yes | Unique per-record identifier |
| 2 | `schema_version` | string | Yes | Schema version for compatibility |
| 3 | `created_at` | ISO-8601 | Yes | Record creation timestamp |
| 4 | `phase_id` | string | Yes | Phase that produced this record |
| 5 | `work_order_id` | string | No | Work order reference (if applicable) |
| 6 | `approval_id` | string | No | Links to I19/I19A approval |
| 7 | `dispatch_manifest_version` | string | No | Which manifest version was active |
| 8 | `dispatch_manifest_reference` | string | No | Path to the manifest document |
| 9 | `provider` | string | Yes | Provider name (from central pool) |
| 10 | `model_id` | string | Yes | Model ID (from central pool) |
| 11 | `model_alias` | string | No | Human-friendly alias |
| 12 | `node` | string | Yes | Execution node (5bao/9bao/21bao) |
| 13 | `transport` | string | Yes | ssh / local-exec |
| 14 | `role` | string | Yes | Workflow role |
| 15 | `task_type` | string | Yes | coding / live-smoke / review / test / audit |
| 16 | `language` | string | No | Primary language used |
| 17 | `planned_calls` | int | Yes | Expected number of calls |
| 18 | `actual_calls` | int | Yes | Actual number of calls |
| 19 | `fallback_count` | int | Yes | Number of fallback attempts |
| 20 | `fallback_models_attempted` | string[] | No | Models tried during fallback |
| 21 | `duration_ms` | int | No | Wall-clock execution time |
| 22 | `prompt_tokens` | int/null | No | Prompt token count (null if unavailable) |
| 23 | `completion_tokens` | int/null | No | Completion token count |
| 24 | `total_tokens` | int/null | No | Total token count |
| 25 | `exit_status` | string | Yes | completed / failed / blocked / timeout |
| 26 | `exit_code` | int | Yes | Process exit code (0 = success) |
| 27 | `exact_string` | string | No | Exact match string (for live smoke) |
| 28 | `exact_match` | bool | No | Whether exact string matched |
| 29 | `review_result` | string | No | PASS / REQUEST_CHANGES / BLOCKED |
| 30 | `operator_result` | string | No | approved / rejected / needs-review |
| 31 | `operator_notes` | string/null | No | Free-text operator feedback |
| 32 | `files_changed` | string[] | No | Files modified in this execution |
| 33 | `files_changed_count` | int | No | Number of files changed |
| 34 | `tests_summary` | object | No | Test pass/fail/skip breakdown |
| 35 | `merge_result` | string | No | merged / open / cancelled |
| 36 | `merge_commit_sha` | string | No | SHA if merged |
| 37 | `evidence_refs` | string[] | No | Links to supporting documents |
| 38 | `redaction_check` | object | No | Secret/bidi/forbidden pass flags |

### 3.3 Field Category Groups

| Category | Fields |
|---|---|
| **Identity** | execution_id, schema_version, created_at |
| **Chain of Custody** | phase_id, work_order_id, approval_id |
| **Dispatch Context** | dispatch_manifest_version, dispatch_manifest_reference |
| **Model** | provider, model_id, model_alias |
| **Execution** | node, transport, role, task_type, language |
| **Calls** | planned_calls, actual_calls, fallback_count, fallback_models_attempted |
| **Performance** | duration_ms, prompt_tokens, completion_tokens, total_tokens |
| **Outcome** | exit_status, exit_code, exact_string, exact_match |
| **Review** | review_result, operator_result, operator_notes |
| **Artifacts** | files_changed, files_changed_count, tests_summary |
| **Integration** | merge_result, merge_commit_sha |
| **Traces** | evidence_refs |
| **Safety** | redaction_check |

### 3.4 task_type Enum

| Value | Description | Examples |
|---|---|---|
| `live-smoke` | Exact-string model verification | I16C, I16E |
| `coding` | Code implementation | I10C-I13 |
| `review` | Code review | Reviewer-A/B |
| `test` | Test execution | Tester-A/B |
| `audit` | Audit/report generation | I16F, I19 |
| `governance` | Policy/RFC creation | I19, I19A, this RFC |
| `metadata` | Pool metadata update | I17, I18 |
| `operator-decision` | Operator approval gate | APPROVE_EXEC |
| `merge` | Git merge operation | git-integrator |

---

## 4. Evaluation Schema

### 4.1 Structure

The Evaluation Schema is **purely descriptive**. It defines what a future recommendation engine COULD produce, but I20 does NOT implement any scoring, ranking, or recommendation.

```json
{
  "evaluation_id": "eval_XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX",
  "execution_record_ids": [
    "exec_YYYYYYYY-YYYY-YYYY-YYYY-YYYYYYYYYYYY"
  ],
  "evaluation_version": "1.0",
  "evaluated_at": "2026-06-27T12:00:00Z",

  "quality_score": null,
  "stability_score": null,
  "latency_score": null,
  "overall_score": null,

  "recommended_for": [],
  "not_recommended_for": [],
  "confidence": null,

  "evaluation_source": null,
  "evaluation_notes": null,

  "compatible_task_types": null,
  "compatible_languages": null,

  "status": "schema-defined-not-implemented"
}
```

### 4.2 Field Dictionary

| # | Field | Type | Required | Description |
|---|---|---|---|---|
| 1 | `evaluation_id` | UUID | Yes | Unique per-evaluation identifier |
| 2 | `execution_record_ids` | UUID[] | Yes | Links to source execution records |
| 3 | `evaluation_version` | string | Yes | Version of the evaluation logic |
| 4 | `evaluated_at` | ISO-8601 | Yes | Timestamp of evaluation |
| 5 | `quality_score` | float/null | No | 0.0–1.0: output quality metric (null in I20) |
| 6 | `stability_score` | float/null | No | 0.0–1.0: consistency metric (null in I20) |
| 7 | `latency_score` | float/null | No | 0.0–1.0: speed metric (null in I20) |
| 8 | `overall_score` | float/null | No | 0.0–1.0: aggregate (null in I20) |
| 9 | `recommended_for` | string[] | Yes | Task types this model is suitable for (empty in I20) |
| 10 | `not_recommended_for` | string[] | Yes | Task types this model is unsuitable for (empty in I20) |
| 11 | `confidence` | float/null | No | 0.0–1.0: confidence in the evaluation (null in I20) |
| 12 | `evaluation_source` | string/null | No | Algorithm or policy that produced this (null in I20) |
| 13 | `evaluation_notes` | string/null | No | Free-text notes (null in I20) |
| 14 | `compatible_task_types` | string[]/null | No | Task types compatible with this model (null in I20) |
| 15 | `compatible_languages` | string[]/null | No | Languages compatible (null in I20) |
| 16 | `status` | string | Yes | `schema-defined-not-implemented` for I20 |

### 4.3 What Evaluation Schema Does NOT Cover

The following topics are explicitly **excluded** from the Evaluation Schema in I20:

| Topic | Reason | Future Phase |
|---|---|---|
| **Cost metrics** | Requires real provider pricing data, secret-adjacent | I23+ |
| **Model ranking** | Requires scoring algorithm | I24+ |
| **Automatic recommendation** | Requires recommendation engine | I25+ |
| **User preference learning** | Privacy and audit concerns | I26+ |
| **Real-time scoring** | Requires execution feedback loop | I27+ |

---

## 5. Relationship to I19/I19A Dispatch Manifest

### 5.1 Data Flow

```text
Operator approves
       │
       ▼
APPROVE_EXEC → Freezes DISPATCH MANIFEST (I19/I19A)
       │
       ▼
EXECUTE → Model calls execute
       │
       ▼
Each call → produces EXECUTION RECORD (I20)
       │
       ▼
Phase complete → produces EVALUATION (I20, future)
       │
       ▼
REVIEW → feeds back into future recommendations
```

### 5.2 Key Difference

| Artifact | When Created | Purpose |
|---|---|---|
| **Dispatch Manifest** | APPROVE_EXEC | _What was planned and approved_ |
| **Execution Record** | EXECUTE (per call) | _What actually happened_ |
| **Evaluation** | REVIEW (future) | _How good was it_ |
| **Execution Report** | READY/MERGE | _The full phase summary_ |

### 5.3 Linking Fields

Execution Records link to dispatch manifests via:
- `phase_id` — maps to the phase
- `approval_id` — maps to the approval
- `dispatch_manifest_version` — which schema version was in effect
- `dispatch_manifest_reference` — path to the manifest document

Dispatch manifests link to execution records via:
- `execution_result.total_calls_actual` — aggregate count (records provide detail)
- `evidence_refs` — execution record paths (future)

---

## 6. Migration and Compatibility

### 6.1 Pre-I20 Evidence

For execution evidence generated before I20 (I16E live smoke, I10C-I13 coding, I16F audit):

| Missing Field | Default | Impact |
|---|---|---|
| `execution_id` | `pre-i20-<phase_id>-<index>` | Generated at read time |
| `schema_version` | `"0.9"` (pre-standard) | Noted as legacy |
| `approval_id` | `null` | Not recorded pre-I19 |
| `dispatch_manifest_version` | `"0.9"` | Not recorded |
| `dispatch_manifest_reference` | `null` | No manifest existed |
| `fallback_count` | `0` | Assume 0 (verified by reports) |
| `duration_ms` | `null` | Not recorded |
| `prompt_tokens` | `null` | Not recorded |
| `review_result` | `"PASS"` | Assume PASS per report evidence |
| `operator_result` | `"approved"` | Assume approved (phase completed) |
| `exact_string` | `null` | Not applicable for non-smoke |
| `evidence_refs` | `[]` | Must be manually populated |

### 6.2 Schema Version Policy

| Version | Status | Notes |
|---|---|---|
| `0.9` | Legacy | Pre-I20 evidence (auto-generated defaults) |
| `1.0` | I20 baseline | RFC-defined schema (this document) |
| `1.1+` | Future | Additive changes only (no field removal) |

### 6.3 Backward Compatibility

- A v1.0 parser MUST accept v0.9 records with default filling.
- A v1.0 generator MUST always populate `execution_id`, `provider`, `model_id`, `node`, `role`, `task_type`, `actual_calls`, `fallback_count`, `exit_status`, `exit_code`.
- All other fields are optional and may be `null` if unavailable.
- No field in v0.9 is removed or renamed — only new fields are added.

---

## 7. Provider Scope

The Execution Record Schema is **provider-agnostic**. Every central pool provider family is supported:

```
anthropic, dashscope, deepseek, deepseek-plan, google,
minimax, minimax-plan, moonshot, openai, opencode,
opencode-go, volcengine, xai, xiaomi
```

- No field is specific to `opencode-go`.
- `provider` is a free string that must match the central pool provider name.
- `model_id` must match a model in `scripts/model_pool.yaml` (enforced in future implementation).
- Extra visible models (deepseek-v4-pro, kimi-k2.7-code, etc.) SHOULD NOT appear as `model_id` unless they are added to the central pool.

---

## 8. Non-Goals

This RFC does NOT:

- Implement any Execution Record **generation code** in scripts.
- Implement any Evaluation **scoring algorithm**.
- Make automatic recommendations or modify dispatch.
- Collect cost/provider pricing data.
- Learn user preferences or model usage patterns.
- Retrofit pre-I20 phase reports into the new schema (use default fields).
- Modify route-all, central model pool, node configuration, or secret/env.
- Authorize any model calls or live smoke.
- Replace the operator approval workflow.

---

## 9. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Schema too complex for simple phases | Medium | Low | All fields except 8 core ones are optional/nullable |
| Pre-I20 evidence hard to retroactively fill | High | Low | Use null defaults; document as legacy (schema v0.9) |
| Evaluation Schema unused if recommendation engine never built | Medium | Low | Schema exists as reference; no cost to maintain |
| Schema drift from actual implementation | Medium | Medium | RFC documents intent; implementation phase validates |
| Secret-adjacent fields (tokens) accidentally include key data | Low | High | `prompt_tokens`/`completion_tokens` are integers only — never contain key material |

---

## 10. Open Questions

1. **Who generates Execution Records?** Proposal: Orchestrator (or implementer role) at the end of each phase.
2. **Where are Execution Records stored?** Proposal: `docs/execution-records/<phase_id>.json` with `evidence_refs` linking to reports.
3. **Should Execution Records be committed to the repo or kept externally?** Proposal: Committed to repo for audit trail, same as reports.
4. **How granular should a record be — per-call or per-phase?** Proposal: Per-phase with aggregated call metrics, unless live-smoke requires per-call (then multiple records).
5. **Who validates Execution Records against the schema?** Proposal: Reviewer role, before merge gate.
6. **Should Evaluation Schema include cost fields in future?** Yes — but only when provider pricing data is available and non-credential.

---

## Appendix A: Field Migration from Existing Artifacts

| I19 Manifest Field | I20 Execution Record Field | Relationship |
|---|---|---|
| `phase_id` | `phase_id` | Direct copy |
| `approval_id` | `approval_id` | Direct copy |
| `assignments[].provider` | `provider` | From the role's assignment |
| `assignments[].model_id` | `model_id` | From the role's assignment |
| `assignments[].node` | `node` | From the role's assignment |
| `assignments[].transport` | `transport` | From the role's assignment |
| `assignments[].planned_calls` | `planned_calls` | Direct copy |
| `assignments[].fallback_allowed` | (not in record) | Policy, not execution observation |
| `execution_result.total_calls` | `actual_calls` | Aggregate from phase |
| `execution_result.total_fallback` | `fallback_count` | Aggregate from phase |
| `scope.language` | `language` | From scope (if specified) |

| Worker Evidence Template | I20 Execution Record Field | Relationship |
|---|---|---|
| `job_id` | `work_order_id` | Renamed |
| `worker` | `node` | Renamed |
| `task_type` | `task_type` | Direct copy |
| `planned_model` | (not in record) | Superseded by manifest |
| `actual_model` | `model_id` | Direct copy |
| `provider` | `provider` | Direct copy |
| `call_count` | `actual_calls` | Direct copy |
| `token_usage` | `prompt_tokens`, `completion_tokens`, `total_tokens` | Flattened |
| `duration` | `duration_ms` | Unit changed (seconds → ms) |
| `changed_paths` | `files_changed` | Renamed |
| `test_result` | `tests_summary` | Structured |
| `review_verdict` | `review_result` | Renamed |
| `fallback_used` | `fallback_count` | Bool → int |

## Appendix B: Complete Field Quick Reference

```
execution_id                 (UUID, required)
schema_version              (string, required)
created_at                  (ISO-8601, required)
phase_id                    (string, required)
work_order_id               (string, optional)
approval_id                 (string, optional)
dispatch_manifest_version   (string, optional)
dispatch_manifest_reference (string, optional)
provider                    (string, required)
model_id                    (string, required)
model_alias                 (string, optional)
node                        (string, required)
transport                   (string, required)
role                        (string, required)
task_type                   (string, required)
language                    (string, optional)
planned_calls               (int, required)
actual_calls                (int, required)
fallback_count              (int, required)
fallback_models_attempted   (string[], optional)
duration_ms                 (int, optional)
prompt_tokens               (int|null, optional)
completion_tokens           (int|null, optional)
total_tokens                (int|null, optional)
exit_status                 (string, required)
exit_code                   (int, required)
exact_string                (string, optional)
exact_match                 (bool, optional)
review_result               (string, optional)
operator_result             (string, optional)
operator_notes              (string|null, optional)
files_changed               (string[], optional)
files_changed_count         (int, optional)
tests_summary               (object, optional)
merge_result                (string, optional)
merge_commit_sha            (string, optional)
evidence_refs               (string[], optional)
redaction_check             (object, optional)
```
