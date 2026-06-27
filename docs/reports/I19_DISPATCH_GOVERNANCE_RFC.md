# I19 — Full-Pool Operator Dispatch Governance RFC

**Status:** RFC (evaluation only, no changes to route-all or model pool)
**Phase:** v1.21.33I19_FULL_POOL_OPERATOR_DISPATCH_GOVERNANCE_RFC
**Date:** 2026-06-27
**Author:** VibeDev Orchestrator (governance analysis)
**Dependencies:** I18 merged, github/main = 5fc7887

---

## 1. Problem Statement

Current VibeDev dispatch architecture delegates significant authority to `route-all` — a machine-generated policy that *recommends* model+node assignments for 9 workflow roles, but whose output can be mistaken for operator-approved configuration. Three specific risks:

1. **No operator approval checkpoint between route-all output and execution** — route-all can change a role's recommended model without explicit operator sign-off.
2. **Planned vs. actual model/node usage is not audited** — if a worker falls back to a different model or node, the system documents it but has no fail-closed enforcement that the fallback was pre-approved.
3. **route-all treats all 9 roles uniformly** — but some roles (git-integrator, reviewer) have different risk profiles than others (implementer, tester), and the governance model should reflect that.

The goal is to evolve from "route-all recommends, operator can override" to an **approved dispatch manifest** system where:
- Operator explicitly approves a phase-specific `role→provider→model→node` assignment.
- Execution is audited against the approved manifest.
- Any deviation (model fallback, node substitution, role degradation) requires either pre-approval in the manifest or explicit operator intervention.

---

## 2. Current State

### 2.1 Central Model Pool

The full pool (`scripts/model_pool.yaml`, 37 models, SHA at base) contains **14 provider families**:

| Provider | Models | Enabled | Key Alias Examples |
|---|---|---|---|
| `anthropic` | 3 | 3 | claude, sonnet, sonnet-4 |
| `dashscope` | 2 | 2 | qwen, qwen-plus, qwen-max |
| `deepseek` | 3 | 3 | deepseek, ds4, deepseek-chat |
| `deepseek-plan` | 1 | 1 | ds-v4-pro, deepseek-v4-pro |
| `google` | 2 | 2 | gemini, gemini-flash, gemini-pro |
| `minimax` | 1 | 1 | minimax, minimax-m2.5 |
| `minimax-plan` | 1 | 1 | minimax-m3, m3 |
| `moonshot` | 1 | 1 | kimi |
| `openai` | 5 | 5 | gpt4o, o1, o3 |
| `opencode` (free/native) | 5 | 0 | opencode-ds4flash-free, big-pickle |
| `opencode-go` | 8 | 2 | opencode-ds4flash, opencode-mimo |
| `volcengine` | 1 | 1 | doubao, doubao-pro |
| `xai` | 1 | 1 | grok, grok-3 |
| `xiaomi` | 3 | 3 | mimo-v2.5, xmipro |

Total: **37 models**, **25 enabled**, **17 aliases with operator selection**.

See `scripts/model_pool.yaml` for full metadata.

### 2.2 Route-All (Current Dispatch)

Current route-all assigns 9 roles to 2 models across 3 physical nodes:

| Role | Recommended Model | Node | Transport |
|---|---|---|---|
| orchestrator | volcengine-doubao | 21bao | local-exec |
| explorer | minimax-m3 | 5bao | ssh |
| planner | volcengine-doubao | 21bao | local-exec |
| implementer | minimax-m3 | 5bao | ssh |
| tester-a | minimax-m3 | 5bao | ssh |
| tester-b | minimax-m3 | 9bao | ssh |
| reviewer-a | minimax-m3 | 9bao | ssh |
| reviewer-b | minimax-m3 | 21bao | local-exec |
| git-integrator | minimax-m3 | 21bao | local-exec |

**Key observations:**
- Only 2 models used across all 9 roles (volcengine-doubao for orchestrator/planner, minimax-m3 for all others).
- 3 physical nodes provide isolation; 21bao (local-exec) hosts 4 roles, 5bao hosts 3, 9bao hosts 2.
- No opencode-go or opencode models in route-all despite 8 opencode-go models being verified (I16E 16/16 PASS).
- Route-all has no operator-approved manifest — it is a machine-generated recommendation only.

### 2.3 Governance Gaps

| Gap | Severity | Current Mitigation |
|---|---|---|
| Route-all can change without approval | Medium | Operator *can* override, but no hard gate |
| No planned-vs-actual audit | High | Only execution reports document deviations |
| Fallback policy unclear | Medium | auto_switch_policy exists but no pre-approval |
| Node substitution ungoverned | High | Degradation allowed without explicit approval |
| Secret boundary unenforced | Low | Secret check exists pre-PR, but runtime not checked |
| Extra visible models unguarded | Low | Not in central pool, but could be selected by name |

---

## 3. Proposed Terminology

| Term | Definition |
|---|---|
| **Model Pool** | `scripts/model_pool.yaml` — authoritative inventory of all available models, their aliases, metadata, and enabled/disabled/retired lifecycle status. |
| **Dispatch Manifest** | A phase-specific, operator-approved JSON/YAML mapping `role → provider → model → node → transport`, with fallback policy and approval metadata. |
| **Approved Dispatch Plan** | The dispatch manifest for a given phase, signed off by the operator before execution begins. |
| **Planned Assignment** | The `role → {provider, model, node, transport}` entry in the approved dispatch plan. |
| **Actual Assignment** | The model+node+transport actually used during execution (may differ due to fallback, degradation, or node unavailability). |
| **Deviation** | Any difference between planned and actual assignment. |
| **Fail-Closed** | If an actual assignment cannot be reconciled with the approved plan, execution stops and the operator is notified. |
| **Route-All (deprecated)** | The current machine-generated recommendation; will be superseded by dispatch manifests. |

---

## 4. Operator Approval Contract

Every VibeDev phase involving model execution MUST follow this approval flow:

```text
Orchestrator outputs:
  CONFIGURED_NODE_MODEL_CATALOG      ← full inventory of available nodes × models
Planner outputs:
  PLANNER_RECOMMENDED_ROLE_NODE_MODEL_MATRIX  ← recommendation only
Operator selects:
  OPERATOR_SELECTED_ROLE_NODE_MODEL_MATRIX    ← operator decision
Orchestrator freezes:
  ROLE_NODE_MODEL_ASSIGNMENT_REQUEST          ← frozen, immutable for phase
Execution:
  APPROVE_EXEC → EXECUTE → REVIEW → READY/MERGE
```

**Key rules:**
1. Planner MUST NOT decide for the operator. Recommendation only.
2. Orchestrator MUST NOT substitute models/nodes without operator approval.
3. Frozen assignment is immutable for the phase. No runtime deviation without explicit approval.
4. All deviations are recorded in the phase execution report.

---

## 5. Manifest Schema Sketch

Each approved dispatch phase has a JSON manifest that is created during APPROVE_EXEC, frozen, and used as the audit baseline.

```json
{
  "manifest_schema_version": "1.0",
  "phase_id": "v1.21.33IXX_...",
  "approval_id": "<agent-generated>",
  "source_model_pool_head": "5fc7887bc96f7a784bf5c137a201bd48b2e3847a",
  "approved_by_operator": "<operator-identifier>",
  "approved_at": "2026-06-27T11:34:27Z",
  "scope":
```

<｜end▁of▁thinking｜>

<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="write_file">
<｜｜DSML｜｜parameter name="content" string="true"># I19 — Full-Pool Operator Dispatch Governance RFC

**Status:** RFC (evaluation only, no changes to route-all or model pool)
**Phase:** v1.21.33I19_FULL_POOL_OPERATOR_DISPATCH_GOVERNANCE_RFC
**Date:** 2026-06-27
**Author:** VibeDev Orchestrator (governance analysis)
**Dependencies:** I18 merged, github/main = 5fc7887

---

## 1. Problem Statement

Current VibeDev dispatch architecture delegates significant authority to `route-all` — a machine-generated policy that *recommends* model+node assignments for 9 workflow roles, but whose output can be mistaken for operator-approved configuration. Three specific risks:

1. **No operator approval checkpoint between route-all output and execution** — route-all can change a role's recommended model without explicit operator sign-off.
2. **Planned vs. actual model/node usage is not audited** — if a worker falls back to a different model or node, the system documents it but has no fail-closed enforcement that the fallback was pre-approved.
3. **route-all treats all 9 roles uniformly** — but some roles (git-integrator, reviewer) have different risk profiles than others (implementer, tester), and the governance model should reflect that.

The goal is to evolve from "route-all recommends, operator can override" to an **approved dispatch manifest** system where:
- Operator explicitly approves a phase-specific `role→provider→model→node` assignment.
- Execution is audited against the approved manifest.
- Any deviation (model fallback, node substitution, role degradation) requires either pre-approval in the manifest or explicit operator intervention.

---

## 2. Current State

### 2.1 Central Model Pool

The full pool (`scripts/model_pool.yaml`, 37 models at base) contains **14 provider families**:

| Provider | Models | Enabled | Key Alias Examples |
|---|---|---|---|
| `anthropic` | 3 | 3 | claude, sonnet, sonnet-4 |
| `dashscope` | 2 | 2 | qwen, qwen-plus, qwen-max |
| `deepseek` | 3 | 3 | deepseek, ds4, deepseek-chat |
| `deepseek-plan` | 1 | 1 | ds-v4-pro, deepseek-v4-pro |
| `google` | 2 | 2 | gemini, gemini-flash, gemini-pro |
| `minimax` | 1 | 1 | minimax, minimax-m2.5 |
| `minimax-plan` | 1 | 1 | minimax-m3, m3 |
| `moonshot` | 1 | 1 | kimi |
| `openai` | 5 | 5 | gpt4o, o1, o3 |
| `opencode` (free/native) | 5 | 0 | opencode-ds4flash-free, big-pickle |
| `opencode-go` | 8 | 2 | opencode-ds4flash, opencode-mimo |
| `volcengine` | 1 | 1 | doubao, doubao-pro |
| `xai` | 1 | 1 | grok, grok-3 |
| `xiaomi` | 3 | 3 | mimo-v2.5, xmipro |

**Total: 37 models, 25 enabled across 14 provider families.**

### 2.2 Route-All (Current Dispatch)

Current route-all assigns 9 roles to 2 models across 3 physical nodes:

| Role | Recommended | Node | Transport |
|---|---|---|---|
| orchestrator | volcengine-doubao | 21bao | local-exec |
| explorer | minimax-m3 | 5bao | ssh |
| planner | volcengine-doubao | 21bao | local-exec |
| implementer | minimax-m3 | 5bao | ssh |
| tester-a | minimax-m3 | 5bao | ssh |
| tester-b | minimax-m3 | 9bao | ssh |
| reviewer-a | minimax-m3 | 9bao | ssh |
| reviewer-b | minimax-m3 | 21bao | local-exec |
| git-integrator | minimax-m3 | 21bao | local-exec |

**Key observations:**
- Only 2 models used across all 9 roles (volcengine-doubao for orchestrator/planner, minimax-m3 for all others).
- 3 physical nodes (21bao=local-exec, 5bao=ssh, 9bao=ssh).
- No opencode-go or opencode models in route-all.
- Route-all is a machine-generated recommendation only — no operator-approved manifest.

### 2.3 Governance Gaps

| Gap | Severity | Current Mitigation |
|---|---|---|
| Route-all can change without approval | Medium | Operator *can* override, but no hard gate |
| No planned-vs-actual audit | High | Only execution reports document deviations |
| Fallback policy unclear | Medium | auto_switch_policy exists but no pre-approval |
| Node substitution ungoverned | High | Degradation allowed without explicit approval |
| Secret boundary unenforced at runtime | Low | Secret check exists pre-PR only |
| Extra visible models unguarded | Low | Not in central pool, but could be used by name |

---

## 3. Proposed Terminology

| Term | Definition |
|---|---|
| **Model Pool** | `scripts/model_pool.yaml` — authoritative inventory of all available models, aliases, metadata, and lifecycle status (enabled/disabled/retired). |
| **Dispatch Manifest** | A phase-specific, operator-approved mapping `role → provider → model → node → transport` with fallback policy and approval metadata. |
| **Approved Dispatch Plan** | The dispatch manifest for a given phase, signed off by the operator before execution begins. |
| **Planned Assignment** | The `role → {provider, model, node, transport}` entry in the approved dispatch plan. |
| **Actual Assignment** | The model+node+transport actually used during execution (may differ due to fallback, degradation, or node unavailability). |
| **Deviation** | Any difference between planned and actual assignment. |
| **Fail-Closed** | If an actual assignment cannot be reconciled with the approved plan, execution stops and the operator is notified. |
| **Route-All (deprecated)** | The current machine-generated recommendation; to be superseded by dispatch manifests. |

---

## 4. Operator Approval Contract

Every VibeDev phase involving model execution MUST follow this approval flow:

```text
1. Orchestrator outputs CONFIGURED_NODE_MODEL_CATALOG
   → Full inventory of available nodes × models
2. Planner outputs PLANNER_RECOMMENDED_ROLE_NODE_MODEL_MATRIX
   → Recommendation only, no decision authority
3. Operator selects OPERATOR_SELECTED_ROLE_NODE_MODEL_MATRIX
   → Operator decides, agent does not substitute
4. Orchestrator freezes ROLE_NODE_MODEL_ASSIGNMENT_REQUEST
   → Immutable for this phase
5. Execution: APPROVE_EXEC → EXECUTE → REVIEW → READY/MERGE
   → Deviations from frozen assignment require explicit operator approval
```

**Invariant rules:**
1. Planner MUST NOT decide for the operator — recommendation only.
2. Orchestrator MUST NOT substitute models/nodes without operator approval.
3. Frozen assignment is immutable for the phase. No runtime deviation without operator intervention.
4. All deviations are recorded in the phase execution report with planned_vs_actual comparison.
5. The operator approval contract applies to ALL provider families equally — opencode-go is not special.

---

## 5. Manifest Schema Sketch

Each approved dispatch phase should produce a JSON manifest during APPROVE_EXEC. Below is the proposed schema:

```json
{
  "manifest_schema_version": "1.0",
  "phase_id": "v1.21.33IXX_...",
  "approval_id": "<agent-generated>",
  "source_model_pool_head": "5fc7887bc96f7a784bf5c137a201bd48b2e3847a",
  "approved_by_operator": "<operator-identifier>",
  "approved_at": "2026-06-27T11:34:27Z",
  "scope": {
    "allowed_files": ["..."],
    "forbidden_actions": ["push", "merge", "Ready"],
    "node_access_allowed": ["5bao", "9bao", "21bao"],
    "max_model_calls_per_node": 8,
    "enforce_exact_string_live_smoke": true
  },
  "assignments": [
    {
      "role": "tester-a",
      "provider": "minimax",
      "model_id": "minimax-m3",
      "model_alias": "minimax-m3",
      "node": "5bao",
      "transport": "ssh",
      "planned_calls": 1,
      "fallback_allowed": false,
      "fallback_policy": "none",
      "approved_by_operator": true
    },
    {
      "role": "tester-b",
      "provider": "opencode-go",
      "model_id": "opencode-go-deepseek-v4-flash",
      "model_alias": "opencode-ds4flash",
      "node": "9bao",
      "transport": "ssh",
      "planned_calls": 8,
      "fallback_allowed": false,
      "fallback_policy": "none",
      "approved_by_operator": true
    }
  ],
  "execution_result": {
    "planned_vs_actual_ok": true,
    "deviations": [],
    "total_calls": 16,
    "total_fallback": 0
  }
}
```

**Key fields:**
- `phase_id` / `approval_id`: identifiers for traceability
- `source_model_pool_head`: ensures the manifest is anchored to a specific pool state
- `scope`: defines what the phase is allowed to do
- `assignments`: per-role approved dispatch, with `fallback_allowed` boolean
- `execution_result`: populated after phase execution for audit

---

## 6. Planned-vs-Actual Audit

Every execution report MUST include a `dispatch_audit` section comparing planned vs actual:

```yaml
dispatch_audit:
  manifest_head: "5fc7887..."
  assignments:
    - role: tester-a
      planned: {provider: minimax, model: minimax-m3, node: 5bao, transport: ssh}
      actual:  {provider: minimax, model: minimax-m3, node: 5bao, transport: ssh}
      match: true
      fallback: false
    - role: tester-b
      planned: {provider: opencode-go, model: opencode-go-deepseek-v4-flash, node: 9bao, transport: ssh}
      actual:  {provider: opencode-go, model: opencode-go-deepseek-v4-flash, node: 9bao, transport: ssh}
      match: true
      fallback: false
  total_calls_planned: 16
  total_calls_actual: 16
  total_fallback_planned: 0
  total_fallback_actual: 0
  audit_verdict: PASS
```

On any mismatch:
- If `fallback_allowed=false` → **BLOCKED** — report to operator immediately.
- If `fallback_allowed=true` → **WARN** — operator must review post-phase.
- If node unreachable → **BLOCKED** — operator must approve alternate node.

---

## 7. Failure Policy

| Scenario | Policy | Action |
|---|---|---|
| Model unavailable on assigned node | BLOCKED | Report, do NOT auto-fallback without pre-approval |
| Node unreachable | BLOCKED | Report, operator must approve alternate node |
| fallback_allowed=false + actual fallback | BLOCKED | Execution stops, operator notified |
| fallback_allowed=true + actual fallback | WARN | Exec continues, operator reviews post-phase |
| Provider model not in central pool | BLOCKED | Execution not permitted (prevents extra visible model use) |
| Secret/token in execution output | BLOCKED | Execution stops, operator notified |
| Actual provider/model doesn't match manifest | BLOCKED | Execution stops, operator notified |

---

## 8. Migration Plan (route-all → dispatch manifest)

| Phase | Action | Status |
|---|---|---|
| Current | route-all used as recommendation; operator overrides via NL approval | Active |
| I19 | Governance RFC created, schema defined, tests added | **This PR** |
| I20+ | Implement manifest generation in APPROVE_EXEC stage | Pending |
| I21+ | Add planned-vs-actual audit to EXECUTE stage reports | Pending |
| I22+ | Deprecate route-all as decision mechanism (retain as hint only) | Pending |
| I23+ | Remove route-all auto-dispatch authority | Pending |

The migration intentionally avoids modifying route-all or model pool in this phase. The RFC is informational and governance-only.

---

## 9. Non-Goals

This RFC does NOT:

- Modify route-all assignments (9 roles unchanged, I18 state frozen).
- Enable/disable any model in the pool.
- Change provider runtime configuration.
- Add extra visible models to the central pool.
- Replace the operator approval workflow (NL approval continues).
- Implement manifest generation or audit hooks (future phases).
- Change any node/transport configuration.
- Authorize model calls or live smoke.

---

## 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Migration inertia — route-all remains default | High | Medium | Add manifest generation incrementally |
| Manifest schema changes between phases | Medium | Low | Versioned schema; schema_version field |
| Operator approval becomes bottleneck | Low | Medium | Keep NL approval efficient; manifest auto-generated |
| route-all and manifest diverge during migration | Medium | Medium | Planned-vs-actual audit captures divergence |
| Extra visible models accidentally added to manifest | Low | High | Pre-approval check: model must be in central pool |

---

## 11. Open Questions

1. **Should manifests be per-phase or persisted across phases?** Proposal: per-phase, with ability to copy forward unchanged assignments.
2. **Who validates the manifest schema?** Proposal: Orchestrator validates before freezing.
3. **Where are manifests stored?** Proposal: `docs/manifests/` with `phase_id` naming, OR inline in execution reports.
4. **Should the manifest include secret references?** No — only env var names, never actual values.
5. **What happens when the model pool changes between phases?** The manifest binds to a specific `source_model_pool_head`; if the pool has drifted, operator must re-approve.
6. **Is per-role fallback_allowed set in the manifest or by operator at runtime?** Proposal: operator sets it in the manifest during APPROVE_EXEC.

---

## Appendix A: Current Provider Family Inventory

```
Provider        Models  Enabled
anthropic       3       3
dashscope       2       2
deepseek        3       3
deepseek-plan   1       1
google          2       2
minimax         1       1
minimax-plan    1       1
moonshot        1       1
openai          5       5
opcode (native) 5       0
opcode-go       8       2
volcengine      1       1
xai             1       1
xiaomi          3       3
```

## Appendix B: Current Node Inventory

| Node | Transport | Address | Roles |
|---|---|---|---|
| 21bao (vibedev) | local-exec | 192.168.21.6 | orchestrator, planner, reviewer-b, git-integrator |
| 5bao (worker) | ssh | 192.168.5.6:22222 | explorer, implementer, tester-a |
| 9bao (worker) | ssh | 192.168.9.6:22222 | tester-b, reviewer-a |
