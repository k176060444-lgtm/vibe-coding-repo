# I19A — Dispatch Manifest Schema Enhancement RFC

**Status:** RFC (evaluation only, no changes to route-all or model pool)
**Phase:** v1.21.33I19A_DISPATCH_MANIFEST_SCHEMA_ENHANCEMENT_RFC
**Date:** 2026-06-27
**Author:** VibeDev Orchestrator
**Dependencies:** I19 governance concepts (PR #256 pending), I18 merged (github/main=5fc7887)

---

## 1. Problem Statement

The I19 governance RFC established the foundational principle: **operator approves, agent executes**. However, the proposed manifest schema captures only the *final approval result* — it does not preserve the **recommendation trail** or **selection rationale** that led to that result. This creates an audit gap:

1. **Why was this particular model recommended for this role?** — No recommendation source is recorded.
2. **Did the operator accept, reject, or override the recommendation?** — No operator decision metadata.
3. **Which version of the selection policy was active when the recommendation was made?** — No policy version pinning.
4. **Can future audits reconstruct the decision context?** — Not without separate logs that may drift or be lost.

The goal of I19A is to enrich the dispatch manifest schema with **recommendation provenance** and **decision metadata**, without changing any execution logic, route-all assignments, or model pool state.

---

## 2. Current I19 Schema (Baseline)

The I19 manifest schema (as defined in `docs/reports/I19_DISPATCH_GOVERNANCE_RFC.md`, PR #256) contains:

```json
{
  "manifest_schema_version": "1.0",
  "phase_id": "...",
  "approval_id": "...",
  "source_model_pool_head": "...",
  "approved_by_operator": "...",
  "approved_at": "...",
  "scope": { "allowed_files": [], "forbidden_actions": [], ... },
  "assignments": [
    {
      "role": "...",
      "provider": "...",
      "model_id": "...",
      "model_alias": "...",
      "node": "...",
      "transport": "...",
      "planned_calls": N,
      "fallback_allowed": false,
      "fallback_policy": "none",
      "approved_by_operator": true
    }
  ],
  "execution_result": {
    "planned_vs_actual_ok": true,
    "deviations": [],
    "total_calls": N,
    "total_fallback": 0
  }
}
```

**Gaps addressed by I19A:**
- No `recommendation_id` — can't trace which recommendation this approval corresponds to.
- No `recommended_by` — can't tell if the recommendation came from route-all, Hermes, a policy engine, or manual.
- No `recommendation_reason` — no rationale for why this model was recommended.
- No `selection_policy_version` — no pinning to a specific policy snapshot.
- No `recommendation_timestamp` — no temporal anchor for the recommendation.
- No `operator_decision` — can't distinguish "operator accepted recommendation" from "operator overrode".
- No `operator_override_reason` — if the operator chose differently, why?
- No version distinction for `approval` vs `execution` vs `audit` manifests — one structure serves all three purposes.

---

## 3. Enhanced Schema (I19A)

### 3.1 Top-Level Structure

```json
{
  "manifest_schema_version": "2.0",

  "recommendation_id": "rec_a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "approval_id": "app_12345678-abcd-ef90-1234-567890abcdef",

  "source_model_pool_head": "5fc7887bc96f7a784bf5c137a201bd48b2e3847a",
  "source_route_all_head": "5fc7887bc96f7a784bf5c137a201bd48b2e3847a",

  "recommendation_source": {
    "recommended_by": "vibedev-route-all",
    "recommendation_reason": [
      "minimax-m3 recommended for implementer: low cost, high fitness for coding tasks",
      "volcengine-doubao recommended for orchestrator: Chinese language output, planning strength"
    ],
    "selection_policy_version": "v1.21.33I15",
    "recommendation_timestamp": "2026-06-27T10:00:00Z",
    "recommendation_engine": "scripts/vibe_model_routing_policy.py"
  },

  "operator_decision": {
    "decision": "accept",
    "override_assignments": [],
    "override_reason": null,
    "decision_timestamp": "2026-06-27T11:00:00Z",
    "approved_by_operator": "KK"
  },

  "scope": {
    "allowed_files": ["scripts/model_pool.yaml", "tests/..."],
    "forbidden_actions": ["push", "merge", "Ready"],
    "node_access_allowed": ["5bao", "9bao", "21bao"],
    "max_model_calls_per_node": 8,
    "enforce_exact_string_live_smoke": true
  },

  "assignments": [
    {
      "role": "tester-a",
      "recommended": {
        "provider": "minimax",
        "model_id": "minimax-m3",
        "model_alias": "minimax-m3",
        "node": "5bao",
        "transport": "ssh",
        "planned_calls": 1,
        "fallback_allowed": false,
        "fallback_policy": "none"
      },
      "approved": {
        "provider": "minimax",
        "model_id": "minimax-m3",
        "model_alias": "minimax-m3",
        "node": "5bao",
        "transport": "ssh",
        "planned_calls": 1,
        "fallback_allowed": false,
        "fallback_policy": "none"
      },
      "operator_match": true,
      "override_notes": null
    }
  ],

  "execution_result": {
    "planned_vs_actual_ok": true,
    "deviations": [],
    "total_calls_planned": 16,
    "total_calls_actual": 16,
    "total_fallback_planned": 0,
    "total_fallback_actual": 0
  }
}
```

### 3.2 Per-Assignment Structure Detail

| Field | Description | Required |
|---|---|---|
| `role` | Workflow role (orchestrator, implementer, etc.) | Yes |
| `recommended` | Block containing the recommendation before operator review | Yes |
| `recommended.provider` | Provider name | Yes |
| `recommended.model_id` | Model ID from central pool | Yes |
| `recommended.model_alias` | Human-friendly alias | No |
| `recommended.node` | Target execution node | Yes |
| `recommended.transport` | Transport method (ssh, local-exec) | Yes |
| `recommended.planned_calls` | Expected number of model calls | Yes |
| `recommended.fallback_allowed` | Whether fallback is permitted | Yes |
| `recommended.fallback_policy` | Policy identifier | No |
| `approved` | Block containing the operator-approved assignment | Yes |
| `approved.*` | Same sub-fields as `recommended.*` | Yes |
| `operator_match` | `true` if approved == recommended; `false` if operator overrode | Yes |
| `override_notes` | Operator's reason if different; `null` if accepted | No |

### 3.3 Version Tracks

The manifest evolves through three distinct versions during a phase lifecycle:

| Version | Stage | Created By | Purpose |
|---|---|---|---|
| **approval_manifest_version** (v2.0-a) | APPROVE_EXEC | Orchestrator (after operator decision) | Frozen baseline for the phase |
| **execution_manifest_version** (v2.0-e) | EXECUTE | Orchestrator (after execution) | Actual assignment used, including fallback |
| **audit_manifest_version** (v2.0-u) | REVIEW/READY | Reviewer/Git Integrator | Final verified state, compared against approval baseline |

This three-version model ensures:
- The approval baseline is immutable.
- Execution deviations are captured, not hidden.
- The audit trail connects what was approved → what was executed → what was verified.

---

## 4. Recommendation vs. Approval Separation

### Core Principle

**A recommendation must NEVER automatically become an approval.**

The flow is:

```text
Policy Engine / Route-All / Hermes
        │
        ▼
   RECOMMENDATION
   (recommended_by, recommendation_reason,
    selection_policy_version, timestamp)
        │
        ▼
   OPERATOR REVIEW
   (human evaluates recommendation)
        │
        ▼
   APPROVAL or OVERRIDE
   (operator_decision: accept/reject/override,
    override_reason if applicable)
        │
        ▼
   FROZEN DISPATCH MANIFEST
   (immutable for phase, audit baseline)
```

**Invariants:**
1. No `approval_id` exists without a corresponding `recommendation_id`.
2. The `recommended` block is populated before operator review.
3. The `approved` block is populated from operator input, not copied from `recommended` automatically.
4. `operator_match` is computed after both blocks are populated.
5. The manifest is frozen only after `operator_decision` is recorded.

### What This Prevents

- A stale route-all configuration cannot silently change a role's model assignment.
- A policy engine bug cannot propagate to execution without operator awareness.
- An operator override is explicitly documented, not lost in conversation logs.
- Future audits can distinguish "accepted recommendation" from "deliberate override."

---

## 5. Responsibility Boundaries

| Entity | Can Recommend | Can Approve | Can Execute Without Approval |
|---|---|---|---|
| **Route-All** (policy engine) | YES | NO | NO |
| **Hermes Agent** (Orchestrator) | YES (via Planner role) | NO | NO |
| **WebDEV** | YES | NO | NO |
| **Operator (Human)** | NO | YES | YES (after approval) |
| **Planner Role** | YES | NO | NO |

### recommended_by Enum

The `recommended_by` field uses a controlled vocabulary:

| Value | Source | Description |
|---|---|---|
| `vibedev-route-all` | `scripts/vibe_model_routing_policy.py` | Central routing policy engine |
| `vibedev-planner` | Orchestrator's Planner role | Per-phase recommendation from Planner |
| `hermes-agent` | Hermes Agent auto-suggestion | Hermes built-in model selection |
| `manual` | Operator typed directly | Human-specified assignment (bypasses recommendation) |
| `policy-engine-v2` | Future policy engine | Upgraded routing engine (post-I22) |
| `external` | Third-party tool | Not from VibeDev stack |

This enum applies to **all** provider families equally — `opencode-go`, `volcengine`, `minimax`, `xiaomi`, etc. No provider gets special treatment in the recommendation taxonomy.

---

## 6. Selection Policy Version

The `selection_policy_version` field pins the manifest to a specific version of the model selection logic:

```json
"selection_policy_version": "v1.21.33I15"
```

**Rules:**
- Must be a version string from `git tag --list 'v*'` or the phase identifier that established the policy.
- When the policy changes (e.g., via a new I-phase), new manifests MUST use the updated version.
- Old manifests referencing old policy versions remain valid for audit — policy changes are not retroactive.
- If the operator manually specifies all assignments (no recommendation used), set `selection_policy_version: "manual-override"`.

**Current policy versions relevant to this schema:**

| Version | Established By | Change |
|---|---|---|
| `v1.21.33I15` | I15 merge (c775955) | Architecture contract + model pool baseline |
| `v1.21.33I18` | I18 merge (5fc7887) | Enabled opencode-go-mimo-v2-5 |
| `v1.21.33I19A` | This RFC | Schema enhancement (policy version tracking) |

---

## 7. Provider Scope

This enhanced schema applies to **all 14 provider families** in the central model pool:

```
anthropic       (3 models)    — Claude 3.5/4
dashscope       (2 models)    — Qwen
deepseek        (3 models)    — DeepSeek Chat/Coder/Reasoner
deepseek-plan   (1 model)     — DeepSeek v4 Pro
google          (2 models)    — Gemini 2.5 Flash/Pro
minimax         (1 model)     — MiniMax M2.5
minimax-plan    (1 model)     — MiniMax M3
moonshot        (1 model)     — Kimi
openai          (5 models)    — GPT-4o, O1, O3
opencode        (5 models)    — Free/native opencode models
opencode-go     (8 models)    — opencode-go verified models
volcengine      (1 model)     — Doubao
xai             (1 model)     — Grok-3
xiaomi          (3 models)    — Mimo v2.5
```

The manifest schema is **provider-agnostic**. No field limits recommendation provenance to `opencode-go` only; the `recommended_by`, `recommendation_reason`, and `selection_policy_version` fields apply uniformly.

---

## 8. Migration and Compatibility

### Old Manifest Compatibility

When reading a pre-I19A manifest (schema v1.0):

| Missing Field | Default Value | Impact |
|---|---|---|
| `recommendation_id` | `"pre-i19a-<phase_id>"` | Generated at read time |
| `recommended_by` | `"unknown"` (legacy) | No recommendation provenance |
| `recommendation_reason` | `[]` | Empty — reason not recorded |
| `selection_policy_version` | `"pre-i19a"` | Not pinned |
| `recommendation_timestamp` | `null` | Not recorded |
| `operator_decision` | `{"decision": "assumed-accept"}` | Assumed operator accepted |
| `operator_match` | `true` | No override data available |
| `approval_manifest_version` | `"1.0"` | Not version-tracked |

### Schema Version Lifecycle

| Version | Status | Notes |
|---|---|---|
| `1.0` | I19 baseline (PR #256) | Current proposed baseline |
| `2.0` | I19A proposed (this RFC) | Enhanced with recommendation provenance |
| `2.1+` | Future | Backward compatible extensions |

### Conversion Rules

- A v2.0 parser MUST accept v1.0 manifests by filling defaults.
- A v2.0 generator MUST emit canonical `recommendation_source` and `operator_decision` blocks.
- No field in v1.0 is removed — schema evolution is additive only.

---

## 9. Failure Model for Schema Validation

| Schema Issue | Severity | Action |
|---|---|---|
| Missing `recommendation_id` | WARN | Auto-generate from phase_id + hash |
| Missing `approved` block for a role | BLOCKED | Manifest is invalid — stop execution |
| `operator_match=false` but `override_notes` is null | BLOCKED | Incomplete operator decision |
| `selection_policy_version` does not match any known I-phase | WARN | Possible drift from known policy |
| `recommended_by` not in controlled enum | WARN | Unknown recommendation source |
| `approved.*` differs from `recommended.*` but `operator_decision.decision` is "accept" | BLOCKED | Logic contradiction |
| `approval_id` without `recommendation_id` | WARN | Possible governance bypass |

---

## 10. Non-Goals

This RFC does NOT:

- Modify any route-all role assignments (9 roles unchanged, I18 state).
- Enable/disable any model in the central pool (37 models, 26 enabled).
- Change any provider runtime configuration.
- Add extra visible models to the central pool.
- Implement manifest generation or validation code in scripts.
- Change the operator approval workflow (NL approval continues as-is).
- Authorize any model calls or live smoke.
- Modify `scripts/vibe_model_routing_policy.py` or `scripts/model_pool.yaml`.
- Replace or modify the I19 governance principles — only enriches the schema.

---

## 11. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Schema complexity increases friction for simple phases | Medium | Low | Keep `operator_match=true` as fast-path; full schema only when overrides occur |
| Migration of old manifests | Low | Low | Default values handle v1.0 compat |
| `selection_policy_version` drift | Medium | Low | Warn on mismatch, not block |
| Operator forgets to set override_reason | Medium | Low | Schema validation warns, does not block |
| Schema changes before implementation | Low | Low | RFC phase — no code written yet |

---

## 12. Open Questions

1. **Should `recommendation_reason` be structured (enum) or free text?** Proposal: array of strings (both free text and structured).
2. **Who validates the manifest schema at runtime?** Proposal: Orchestrator before freeze, Reviewer post-execution.
3. **Where are manifests stored for long-term audit?** Proposal: `docs/manifests/<phase_id>.json` or inline in phase execution reports.
4. **Should the manifest include secret references?** No — only env var names, never actual values.
5. **When `operator_match=false`, should execution block until override_notes is filled?** Proposal: WARN only (operator intent is clear from `approved` block).

---

## Appendix A: Field Migration Map (v1.0 → v2.0)

| v1.0 Field | v2.0 Location | Status |
|---|---|---|
| `manifest_schema_version` | `manifest_schema_version` | Changed to "2.0" |
| `phase_id` | `phase_id` | Unchanged |
| `approval_id` | `approval_id` | Unchanged |
| `source_model_pool_head` | `source_model_pool_head` | Unchanged |
| — | `recommendation_id` | NEW |
| — | `recommendation_source` | NEW |
| — | `recommendation_source.recommended_by` | NEW |
| — | `recommendation_source.recommendation_reason` | NEW |
| — | `recommendation_source.selection_policy_version` | NEW |
| — | `recommendation_source.recommendation_timestamp` | NEW |
| — | `recommendation_source.recommendation_engine` | NEW |
| — | `operator_decision` | NEW |
| — | `operator_decision.decision` | NEW |
| — | `operator_decision.override_assignments` | NEW |
| — | `operator_decision.override_reason` | NEW |
| — | `operator_decision.decision_timestamp` | NEW |
| `approved_by_operator` | `operator_decision.approved_by_operator` | Moved |
| `approved_at` | `operator_decision.decision_timestamp` | Merged |
| `assignments[].approved_by_operator` | `assignments[].operator_match` | Replaced |
| — | `assignments[].recommended` block | NEW |
| — | `assignments[].approved` block | NEW |
| `assignments[].fallback_allowed` | `assignments[].recommended.fallback_allowed` and `assignments[].approved.fallback_allowed` | Duplicated |
| — | `assignments[].override_notes` | NEW |
| `execution_result.total_calls` | `execution_result.total_calls_planned` + `total_calls_actual` | Split |
| `execution_result.total_fallback` | `execution_result.total_fallback_planned` + `total_fallback_actual` | Split |
