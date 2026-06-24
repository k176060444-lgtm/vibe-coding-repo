# Vibe Coding Workflow Contract

**Version:** 1.0.0
**Effective:** 2026-06-24
**Authority:** Operator-validated, auditable

---

## Purpose

This document defines the **one and only** workflow for Vibe Coding sessions. It exists because in early grey-scale usage, agents started executing without entering the Vibe Coding role, without intake, without plan alignment, and without model/role/node selection — producing uncontrolled "散装执行" (loose execution).

**After entering Vibe Coding mode, the agent MUST follow this contract. No exceptions.**

---

## Workflow Steps

### Step 0: Enter Vibe Coding Role

When the operator says "进入 Vibe Coding 模式" or equivalent, the agent MUST:

1. Acknowledge entry into Vibe Coding mode
2. Confirm the target repository
3. Confirm the current main SHA / baseline
4. Confirm active freeze markers
5. Confirm local dirt status (malicious_payload_evidence.json, pilot-prompts/)
6. State that it is now operating under this workflow contract

**The agent MUST NOT begin any coding, planning, or execution before completing Step 0.**

---

### Step 1: Requirement Alignment

The Orchestrator (which is the agent's primary role in Vibe Coding) MUST align with the operator on:

| Field | Required | Description |
|-------|----------|-------------|
| **Goal** | Yes | What the operator wants to achieve |
| **Repository** | Yes | Target repo path |
| **Scope** | Yes | What files/areas are in scope |
| **Forbidden scope** | Yes | What must NOT be touched |
| **Success criteria** | Yes | How to know the task is done |
| **Deliverables** | Yes | What artifacts will be produced |
| **Stop conditions** | Yes | When to stop and ask |

**The agent MUST NOT proceed to Step 2 until the operator confirms Step 1.**

---

### Step 2: Technical Plan + Model Pool

The Orchestrator/Planner MUST produce:

#### 2a. Technical Plan

A structured plan covering:
- Approach / architecture decisions
- Files to modify (with rationale)
- Files NOT to modify (with rationale)
- Test strategy
- Risk assessment
- Estimated scope (lines, files, tests)

#### 2b. Model Pool Listing

The Orchestrator MUST produce a **dynamic model pool** at runtime by querying actual
configuration. The model pool is NOT a fixed list — it reflects what is currently
available, enabled, and healthy.

**Discovery sources (at runtime):**
1. User-configured models (opencode.jsonc, env files, manual additions)
2. OpenCode free models (discovered at runtime, availability varies)
3. OpenCode Go models (only if subscribed/enabled/detected)
4. Provider-configured models with valid credentials

**Required output — two sections:**

**A. Available Model Pool** — models currently selectable for execution:

| Field | Required | Description |
|-------|----------|-------------|
| provider | Yes | Provider name (e.g. xiaomi, deepseek, volcengine, minimax) |
| model_id | Yes | Full model identifier |
| alias | Yes | Short name / display name |
| source | Yes | How discovered: user-config / opencode-free / opencode-go / provider |
| plan_type | Yes | deepseek-plan / xiaomi-plan / volcengine-plan / minimax-plan / opencode-free / opencode-go |
| cost_status | Yes | free / paid / mixed |
| node_availability | Yes | Windows / 9bao / 5bao (which nodes can run this model) |
| enabled | Yes | true (must be enabled to be in Available pool) |
| health_status | Yes | healthy / degraded / unknown |
| quarantine_status | Yes | none / quarantined (quarantined models NOT in Available pool) |
| credential_status | Yes | available / redacted / unknown (NEVER expose plaintext) |
| suitable_roles | Yes | Orchestrator / Implementer / Reviewer / Verifier / Reporter |
| limits_or_risks | Yes | Known limitations, rate limits, context window, etc. |
| recommendation_reason | Yes | Why this model is recommended for this task |

**B. Non-available Status Summary** — disabled / unavailable / quarantine / not detected.
For reference only, NOT execution candidates.

**Rules:**
- No fixed model count — the pool reflects actual runtime state
- OpenCode free models enter Available only if discovered and healthy
- OpenCode Go enters Available only if subscribed/enabled/detected; otherwise in Non-available
- User-deleted/disabled/quarantined models go to Non-available, NOT Available
- Orchestrator recommendations MUST come from Available pool only
- If a recommended model is unavailable, BLOCK — do NOT auto-substitute
- Credential values are NEVER exposed (credential_status=available/redacted/unknown only)

#### 2c. Role Assignment Matrix

Each role MUST specify:

| Field | Required | Description |
|-------|----------|-------------|
| **Role** | Yes | Orchestrator/Planner, Implementer, Reviewer, Verifier, Reporter |
| **Node** | Yes | Windows, 9bao, 5bao |
| **Model/Provider** | Yes | Specific model and provider |
| **Task scope** | Yes | What this role does |
| **Write allowed** | Yes | Can this role modify files? |
| **Real execution allowed** | Yes | Can this role trigger real execution? (always NO for now) |
| **Stop point** | Yes | When must this role stop and report? |

**The Orchestrator may RECOMMEND role assignments but MUST NOT finalize them. The operator decides.**

---

### Step 3: Operator Approval

The operator MUST explicitly approve:
1. The technical plan
2. The role/node/model assignment
3. The scope and forbidden scope

**Format:** A structured approval record containing:
- `approval_id`
- `proposal_id` or `proposal_hash`
- `approved_actions` (list of allowed actions)
- `risk_level`
- `role_model_matrix` (approved assignments)
- `operator_confirmation_phrase`
- `timestamp`

**The agent MUST NOT begin execution before receiving Step 3 approval.**

---

### Step 4: Execution

After approval, the small cluster works within the authorized scope:
- Implementer writes code only in authorized files
- Reviewer performs read-only blind review
- Verifier runs tests only
- Reporter summarizes results

**All execution MUST stay within the approved scope. Any scope expansion requires new approval.**

---

### Step 5: PR — Draft Only

- PR creation defaults to **Draft PR**
- **Automatic Ready is FORBIDDEN**
- The agent MUST NOT convert Draft → Ready without explicit operator authorization

---

### Step 6: Ready Authorization

The operator MUST separately authorize:
- Converting Draft → Ready
- This is a distinct approval from Step 3

---

### Step 7: Merge Authorization

The operator MUST separately authorize:
- Merge execution
- Merge method (must be ordinary merge commit, not squash/rebase)

---

### Step 8: Cleanup/Freeze Authorization

The operator MUST separately authorize:
- Branch deletion
- Freeze marker generation
- These are distinct from merge approval

---

### Step 9: Completion

After all steps are complete:
- Report final state
- Suggest next steps
- **Do NOT automatically start a new phase**
- Wait for operator instruction

---

## Approval Consolidation Rule

For low-risk, test-only tasks, the operator MAY consolidate multiple approvals into a single message. For example:

> "批准 implementation + Ready + merge 一步完成"

When consolidated, the agent may execute Steps 4-7 without pausing. But:
- Step 3 (initial plan approval) is ALWAYS required
- Consolidation must be EXPLICIT — the agent must not assume

---

## Forbidden Actions (Always)

These are NEVER allowed without explicit operator authorization:

1. Push directly to main
2. Force push
3. Auto-Ready (converting Draft → Ready without operator approval)
4. Auto-merge (merging without operator approval)
5. Modify secrets/credentials/SSH/gateway/production
6. Trigger real execution (for now — will be enabled in future phases)
7. Expand scope beyond approved plan
8. Start a new phase without operator instruction

---

## Chinese Quick Reference

| 步骤 | 动作 | 谁决定 |
|------|------|--------|
| Step 0 | 进入角色 | Operator 触发 |
| Step 1 | 需求对齐 | Orchestrator 提出，Operator 确认 |
| Step 2 | 技术 plan + 模型池 | Orchestrator 提出 |
| Step 3 | 批准 plan + 角色 | **Operator 签发** |
| Step 4 | 执行 | 小集群按授权作业 |
| Step 5 | 创建 Draft PR | 自动（默认 Draft） |
| Step 6 | Ready | **Operator 单独授权** |
| Step 7 | Merge | **Operator 单独授权** |
| Step 8 | Cleanup/Freeze | **Operator 单独授权** |
| Step 9 | 完成 | 建议下一步，等待 Operator |

---

## Enforcement

This contract is enforced by:
1. `conversational_intake_gate.py` — detects when intake is required
2. `execution_approval_gate.py` — blocks execution without approval
3. `git_pr_approval_gate.py` — enforces PR state transitions
4. `MODEL_POOL_DISTRIBUTION_CONTRACT.md` — model pool governance, schema, and distribution rules
5. This document — the authoritative workflow definition

---

*This contract is the single source of truth for Vibe Coding workflow. If any other document conflicts, this document wins.*
