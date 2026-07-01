# VibeCoding Runtime Flow Spec

**Status**: Baseline02 · Stage 2 mandatory spec
**Anchor**: main @ `0170ed68a4a8420fab843f35de3d9dcaa271c045` (PR #276 merged)
**Stage**: Baseline02 Stage 2 of 8 (read `docs/VIBECODING_BASELINE02_REMEDIATION_PLAN.md`)
**Supersedes**: none (this is a new mandatory spec, layered on top of all existing contracts)
**Owner**: operator (final decision authority)
**Enforced by**: operator + 5-receipt chain verifier

---

## 1. Purpose

This spec defines the **mandatory runtime flow** for any operator-directed VibeCoding task on the 小集群. It is the **glue contract** binding:

- intake gate (`scripts/conversational_intake_gate.py`)
- approval receipt schema (`scripts/execution_approval_gate.py`, `scripts/git_pr_approval_gate.py`)
- role / node / model assignment gate (`scripts/vibe_role_assignment_gate.py`)
- cluster readiness gate (`scripts/cluster_upgrade_contract.py`, `scripts/cluster_component_manifest.py`)
- central model pool (`scripts/model_pool.yaml`, `scripts/model_pool_manifest.json`)
- node-model matrix 7-state gate (`scripts/node_model_capability.yaml`)
- public-PR permission gate (`scripts/git_pr_approval_gate.py`)
- evidence / report gate (`scripts/vibe_evidence_verifier.py`, `scripts/vibe_report_schema.py`)

This spec **does not replace** any existing contract. It binds them into a single sequential state machine and defines the **5-receipt chain** that must pass before any mutating action or report-close. Existing contracts cited above remain authoritative in their domain; this spec is authoritative in the *interaction order and fail-closed linkage* between them.

If this spec contradicts an existing contract, the **more fail-closed** rule wins. All contradictions must be reported as drift.

---

## 2. Architecture Anchors (non-negotiable)

| Term | Identity | Forbidden confusion |
|------|----------|---------------------|
| `21bao` | **Windows local-exec/control host** (唯一的本地执行/控制入口) | `21bao` ≠ remote SSH worker; `21bao` ≠ 独立 cluster node |
| `vibedev` | **VibeCoding Hermes profile**, runs **on 21bao** (the operator's 主对话 profile) | `vibedev` ≠ 独立 host; `vibedev` ⊂ `21bao`; `vibedev` ≠ `小马蹄 Hermes` |
| `小马蹄 Hermes` | **Independent reviewer profile**, runs **on 21bao** (same host, different Hermes profile) | `小马蹄 Hermes` ≠ `vibedev`; both share `21bao` as host; profiles are isolated at Hermes profile layer |
| `5bao` | **Remote SSH worker** (Debian) | `5bao` ≠ `21bao`; `5bao` 不得在 21bao 上 shim; SSH-only |
| `9bao` | **Remote SSH worker** (Debian) | `9bao` ≠ `21bao`; SSH-only |
| `win + 21bao` | **One node** — `21bao IS` the Windows local host; cannot be split | 拆 win + 21bao = drift signal, 立即 STOP |

**Rules**:

1. Every node-model assignment proposal MUST reference exactly one of `{21bao, 5bao, 9bao}` and MUST NOT propose a `win` node separately from `21bao`.
2. Any task that conflates `vibedev` and `小马蹄 Hermes`, or splits `win+21bao` into two nodes, MUST be STOP_AND_REANCHOR.
3. This spec assumes the architecture freeze recorded in `docs/BASELINE01_FREEZE_RECORD.md` (`7dceb8c` G5 matrix deployment).

---

## 3. End-to-End Runtime Flow (sequential state machine)

The flow is **sequential**. Each stage validates the previous stage's receipts and produces exactly one receipt of its own. The state machine is `F1 → F2 → … → F10`. No stage may start before the previous stage's receipt is present AND verified.

| Stage | Name | Input | Receipt produced | Gate script(s) | Prior receipt(s) |
|-------|------|-------|------------------|----------------|-------------------|
| F1 | Intake | operator / user raw request | (none; produces IntakeRecord) | `scripts/conversational_intake_gate.py`, `scripts/vibe_workorder_intake.py` | none |
| F2 | Classify | IntakeRecord | (none; produces ClassifiedRecord with risk_level) | (intake gate inner) | F1 |
| F3 | Plan / Recommend | ClassifiedRecord + model pool snapshot | (none; produces PlanDraft) | (planner role) | F1, F2 |
| F4 | Operator Approval | PlanDraft + operator raw message | **approval_receipt** | `scripts/execution_approval_gate.py` (EAG v1.4.0, 8 required fields), `scripts/git_pr_approval_gate.py` (35 PASS, PROTECTED_BRANCHES) | F1, F2, F3 |
| F5 | Role-Node-Model Assignment | approval_receipt + model pool + matrix | **assignment_receipt** | `scripts/vibe_role_assignment_gate.py` (RAG 30/30 PASS, 8 required fields, VALID_ROLES=10) + node whitelist + model-pool single source (Stage 3 enforcement) | F4 |
| F6 | Readiness Gate | assignment_receipt + matrix 7-state | **readiness_receipt** | matrix 7-state check + cluster readiness (Stage 5 enforcement) | F4, F5 |
| F7 | Public-PR Permission Gate | readiness_receipt=true + PR metadata | **permission_receipt** | GPAC + public-repo pre-flight (Stage 6 enforcement) | F4, F5, F6 |
| F8 | Execute | all 4 receipts above | (ExecutionTrace) | execution role | F4, F5, F6, F7 |
| F9 | Evidence / Report | ExecutionTrace | **evidence_receipt** (with 5-receipt linkage) | `scripts/vibe_evidence_verifier.py` (9 checks) + report schema v1.2.0 (7 REQUIRED_SECTIONS) + 5-receipt linkage (this spec defines) | F4, F5, F6, F7, F8 |
| F10 | Closeout | evidence_receipt validated | (closeout manifest) | (operator + verifier) | F4-F9 |

**Hard rules**:

- **No parallel branches**. A receipt from stage N cannot start stage N+1.
- **Receipt invalid → return to earliest failing receipt**. The state machine rolls back to the earliest stage whose receipt is missing/failed/unknown.
- **Mid-stage drift detected → STOP_AND_REANCHOR** per `docs/OPERATOR_ORCHESTRATOR_CONTRACT.md` §8.

---

## 4. 5-Class Receipt Schema (mandatory)

Every receipt is a JSON object written by its producing gate. All 5 receipts MUST coexist in the final evidence payload; missing any one → `evidence_receipt.FAIL`.

### 4.1 `approval_receipt` (produced at F4)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `approval_id` | string | yes | ULID; unique per approval |
| `proposal_id` OR `proposal_hash` | string | yes | exactly one of the two; the PlanDraft identifier |
| `approved_actions[]` | array[string] | yes | every L3/L4 action authorized; subset of `{git_checkout, branch_create, file_add, file_modify, commit, push, pr_create, merge, ssh_worker_mutation, ssh_worker_probe, env_probe, wrapper_call, model_call, service_admin_uac, production_gateway_change}` |
| `risk_level` | enum | yes | `low` \| `medium` \| `high`; default `medium` per intake gate |
| `operator_message_raw` | string | yes | the operator's literal approval text (must contain confirmation phrase) |
| `operator_confirmation_phrase` | string | yes | regex anchor; default `批准执行` (or operator-supplied; must appear in `operator_message_raw`) |
| `timestamp` | ISO-8601 UTC | yes | receipt time |
| `approval_scope` | string | yes | free-form text describing scope boundaries (allowed_paths / forbidden_paths) |

**Verified by**: `scripts/execution_approval_gate.py` (EAG v1.4.0) + `scripts/git_pr_approval_gate.py`.

### 4.2 `assignment_receipt` (produced at F5)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `assignment_id` | string | yes | ULID |
| `role` | enum | yes | one of `VALID_ROLES` from `scripts/vibe_role_assignment_gate.py` (10 entries) |
| `node` | enum | yes | `21bao` \| `5bao` \| `9bao` (whitelist enforced at Stage 3) |
| `model` | string | yes | `model_pool.yaml` `model_id` (single-source enforced at Stage 3) |
| `provider` | string | yes | runtime provider name (NOT collapsed with `canonical_provider`) |
| `provider_namespace` | enum | yes | `unknown` \| `opencode` \| `anthropic` \| `xiaomi` \| `volcengine` \| `minimax` \| … (enumerated; unknown forbidden at F6) |
| `call_budget` | integer | yes | max model calls permitted |
| `fallback_policy` | enum | yes | `disabled` \| `same_provider_different_model` \| `operator_selects` |
| `operator_approval_timestamp` | ISO-8601 | yes | copied from approval_receipt.timestamp |
| `operator_approval_signature` | string | yes | SHA256 of (approval_receipt.approval_id + operator_approval_timestamp) for linkage |
| `node_whitelist_verified` | bool | yes | Stage 3 enforces node ∈ {21bao, 5bao, 9bao} |
| `model_pool_source_verified` | bool | yes | Stage 3 enforces model exists in central pool |
| `base_sha` | string | yes | SHA at F5 start (basis for F8 result_sha computation) |

**Verified by**: `scripts/vibe_role_assignment_gate.py` + Stage 3 scripts.

### 4.3 `readiness_receipt` (produced at F6)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `readiness_id` | string | yes | ULID |
| `target_node` | enum | yes | copied from assignment_receipt.node |
| `target_model` | string | yes | copied from assignment_receipt.model |
| `runtime_visible` | bool | yes | matrix field; `unknown` → readiness=FAIL |
| `env_loaded` | bool | yes | matrix field; `unknown` → readiness=FAIL |
| `wrapper_valid` | bool | yes | matrix field; `unknown` → readiness=FAIL |
| `model_call_verified` | bool | yes | matrix field; `unknown` → readiness=FAIL |
| `all_known` | bool | yes | `true` ONLY when all 4 above are explicit `true`/`false`; `unknown` of any → `false` |
| `operator_authorized_runtime_probes` | bool | yes | Stage 5 enforcement: any L3 probe requires operator-task-specific approval |
| `base_sha` | string | yes | SHA at F6 start |
| `timestamp` | ISO-8601 | yes | |

**Fail-closed**: `all_known=false` OR `model_call_verified≠true` → readiness=FAIL → F6 short-circuits to F9 evidence FAIL (no F7 attempted).

### 4.4 `permission_receipt` (produced at F7)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `permission_id` | string | yes | ULID |
| `repo` | string | yes | `owner/name` |
| `repo_is_public` | bool | yes | Stage 6 pre-flight: `gh api /repos/:o/:r { visibility }` |
| `repo_is_fork` | bool | yes | Stage 6 pre-flight |
| `default_branch` | string | yes | usually `main`; verified pre-flight |
| `operator_merge_authorized` | bool | yes | operator must explicitly confirm `yes, merge` for public repos (Stage 6) |
| `remote_verified` | bool | yes | GPAC: `git ls-remote` succeeds against base_sha + head_sha |
| `merge_check_passed` | bool | yes | `gh pr view --json mergeable` was `MERGEABLE` |
| `base_sha` | string | yes | SHA at F7 start |
| `head_sha` | string | yes | local head SHA |
| `timestamp` | ISO-8601 | yes | |

**Fail-closed**: for public non-fork repos, `operator_merge_authorized=false` OR `remote_verified=false` → F7 BLOCKED → no merge. `merge_check_passed=false` → F7 BLOCKED.

### 4.5 `evidence_receipt` (produced at F9)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `evidence_id` | string | yes | ULID |
| `workorder_id` | string | yes | cross-reference to F1 IntakeRecord.id |
| `base_sha` | string | yes | pre-execution SHA |
| `result_sha` | string | yes | post-execution SHA |
| `digest` | string | yes | SHA256 of evidence payload (signing for tamper detection) |
| `nines_checks` | object | yes | the 9 evidence checks: `required_fields`, `digest_match`, `registry_entry`, `approval_receipt`, `shas_present`, `smoke_result`, `job_status`, `audit_status`, `changed_paths` — each `bool` |
| `links.approval_receipt` | string | yes | approval_receipt.approval_id (5-receipt linkage) |
| `links.assignment_receipt` | string | yes | assignment_receipt.assignment_id |
| `links.readiness_receipt` | string | yes | readiness_receipt.readiness_id |
| `links.permission_receipt` | string | yes | permission_receipt.permission_id |
| `report_sections` | object | yes | the 7 required sections from `scripts/vibe_report_schema.py` v1.2.0 |
| `timestamp` | ISO-8601 | yes | |

**5-receipt linkage rule**: any missing `links.*` → evidence_receipt.FAIL → F9 BLOCKED → F10 closeout BLOCKED.

---

## 5. Action Risk Levels (4-tier classification)

Every mutating action is classified at exactly one level. Cross-level batching is forbidden (e.g. an L3 probe may not be hidden inside an L1 task).

| Level | Class | Examples | Authorization required |
|-------|-------|----------|------------------------|
| **L1** | `static-only` | `git status`, `git log`, `git diff`, `git show`, `read`, `grep`, `pytest --collect-only`, `python -c 'import …'`, `yaml.safe_load`, `json.safe_load`, `AST.parse` | **None** — agent runs autonomously inside operator's already-active session |
| **L2** | `local-safe-check` | `python -m py_compile`, `python -m unittest --collect-only`, `pyflakes`, `pyright`, `ruff check`, `python <script> --self-check` (no network, no SSH, no mutation, on 21bao) | **Task-level approval** (covered in approval_receipt scope) |
| **L3** | `runtime-probe` | SSH to `5bao` or `9bao` (read-only commands: `ls`, `cat`, `env \| grep -v SECRETS`, `systemctl status`), `env_probe` on remote, `wrapper_valid` real-call, `model_call_verified` real-call | **Operator-task-specific approval** (separate `operator_confirmation_phrase` block; cannot be merged with L4 approval) |
| **L4** | `mutating-action` | `git checkout -b`, `git commit`, `git push`, `gh pr create`, `gh pr merge`, `file_create` / `file_modify` / `file_delete`, `ssh_worker_mutation`, `service_admin_uac`, `production_gateway_change` | **Complete approval_receipt + full 5-receipt chain (F4-F9) verified before any L4 fires** |

**Cross-level rule**: an approval_receipt that bundles L3 + L4 is **rejected** at verification time. L3 probes MUST appear as their own approval scope with their own confirmation phrase. L1/L2 within an L3/L4 task remain L1/L2 (independently auditable).

**Default-deny**: any action not explicitly authorized at intake time defaults to L4. Workers MAY NOT classify their own actions as L1/L2 to bypass approval.

---

## 6. Fail-Closed Rules (9 rules, mandatory)

These 9 rules apply to every stage and every receipt. Violations are STOP_AND_REANCHOR.

| ID | Rule | Trigger |
|----|------|---------|
| **FCR-1** | `unknown` ≠ `pass` | any matrix/state field = `unknown` → readiness FAIL → no L3/L4 |
| **FCR-2** | `operator_approved = unknown` → no execution | matrix entry not explicit `true` → assign + readiness + permission all BLOCKED; no override |
| **FCR-3** | public-PR `permission_receipt` unverified → no merge | `remote_verified=false` OR `operator_merge_authorized=false` (public repo) → merge BLOCKED |
| **FCR-4** | 5-receipt chain incomplete → no closeout | any of `links.{approval,assignment,readiness,permission,evidence}` missing → evidence FAIL → closeout BLOCKED |
| **FCR-5** | mid-stage drift detected → STOP_AND_REANCHOR | any of the 9 drift triggers in `docs/OPERATOR_ORCHESTRATOR_CONTRACT.md` §8 fires |
| **FCR-6** | `21bao` dispatch never auto | `21bao_enabled_manual_only` from `scripts/cluster_component_manifest.py` enforced; auto-dispatch to 21bao is BLOCKED unless operator issues `enable_21bao_dispatch` for this task only |
| **FCR-7** | cross-gate internal error → block all | any of {intake, EAG, GPAC, RAG, DCG, evidence, permission-pre-flight} returns internal error (not "fail", but "broken") → entire chain BLOCKED; no partial PASS |
| **FCR-8** | local partial-PASS ≠ system PASS | a single gate PASS while cross-gate fields are `unknown` (e.g. L1 intake PASS ≠ F5 node-whitelist verified) → closeout BLOCKED |
| **FCR-9** | no architecture drift | confusing `vibedev` / `小马蹄 Hermes` / `21bao`, or splitting `win+21bao` into 2 nodes → STOP_AND_REANCHOR |

---

## 7. Stage 1 Gap Absorption (mandatory cross-reference)

This spec absorbs the 10 Stage 1 audit gaps (verdict `STAGE1_READONLY_AUDIT_PASS_WITH_GAPS`, operator `ACCEPTED_WITH_GAPS`).

| Gap | What it requires | Enforced where | Enforced when |
|-----|------------------|----------------|---------------|
| **GAP-L3-1** | `node_whitelist_verified`, `model_pool_source_verified` MUST be `true` in assignment_receipt | `scripts/vibe_role_assignment_gate.py` | **Stage 3** |
| **GAP-L5-1** | `provider_namespace` MUST NOT be `unknown` in assignment_receipt | central model pool schema validation | **Stage 4** |
| **GAP-L5-2** | alias uniqueness gate — same alias across 2 models → the second is `enabled=false` | central model pool schema validation | **Stage 4** |
| **GAP-L5-3** | smoke_required=true but no smoke_results → model is `enabled=false` + quarantined until operator approval | central model pool state machine | **Stage 4** |
| **GAP-L6-1** | matrix 6 runtime states MUST be explicit `true`/`false`; `unknown` BLOCKED at readiness | L6 matrix 7-state gate | **Stage 5** |
| **GAP-L6-2** | matrix `operator_approved=true` is required for any new model / new node / new enable — operator approval_receipt required at model pool update | matrix schema + operator_approval linkage | **Stage 5** |
| **GAP-L7-1** | public-PR pre-flight `gh api /repos/:o/:r { permissions }` MUST be called before merge on public repos | `scripts/git_pr_approval_gate.py` + new pre-flight script | **Stage 6** |
| **GAP-L8-1** | 5-class receipt schema (approval, assignment, readiness, permission, evidence) defined here; per-class receipts extend current `scripts/vibe_approval_receipt.py` (currently only 1 class) | receipt schema + verifier | **Stage 2 (this spec); Stage 3/4/5/6 to implement** |
| **GAP-SHARED-1** | runtime 6-state promotion path requires operator-task-specific approval (L3) — never bundled with L4 | readiness_receipt field `operator_authorized_runtime_probes` | **Stage 5** |
| **GAP-SHARED-2** | `21bao_enabled_manual_only` enforced at every dispatch decision | `scripts/cluster_component_manifest.py` invariant + this spec FCR-6 | **Stage 5 (binding to spec FCR-6)** |

**Spec is authoritative for schemas** even where stage implementation is later. Workers implementing Stage 3-6 MUST satisfy the fields/levels defined here.

---

## 8. Cross-Reference to Existing Contracts

| Contract | Relation |
|----------|----------|
| `docs/OPERATOR_ORCHESTRATOR_CONTRACT.md` | drift vocabulary; prompt-writing rules (§6); STOP_AND_REANCHOR semantics (§8) |
| `docs/VIBE_CODING_MODE_CONTRACT.md` | agent-level workflow; this spec is cluster-runtime glue; not duplicated |
| `docs/VIBE_CODING_WORKFLOW_CONTRACT.md` | 10-step developer-side workflow; this spec is operator-orchestrator-cluster glue; not duplicated |
| `docs/MODEL_POOL_DISTRIBUTION_CONTRACT.md` | canonical/runtime provider identity; referenced in assignment_receipt.provider |
| `docs/MODEL_ROUTING_AND_PROVIDER_CAPACITY.md` | provider namespace conventions |
| `docs/OPERATOR_MERGE_STOPLINE_ENFORCEMENT.md` | merge stopline logic; referenced in F7 |
| `docs/V1_2_PRIVILEGED_PUSH_WORKFLOW.md` | push authorization rules; referenced in approval_receipt.approved_actions |
| `docs/OPERATIONAL_READINESS.md` | cluster-level readiness; referenced in readiness_receipt |
| `docs/MODEL_LEDGER_ENFORCEMENT_GATE.md` | gate layer for central model pool |
| `docs/BASELINE01_FREEZE_RECORD.md` | architecture freeze (`7dceb8c` G5); this spec inherits all anchors from this freeze |
| `docs/VIBECODING_BASELINE02_REMEDIATION_PLAN.md` | parent plan; this spec is Stage 2 deliverable |
| `scripts/conversational_intake_gate.py` | F1, F2 gates |
| `scripts/execution_approval_gate.py` | F4 gate (approval_receipt) |
| `scripts/git_pr_approval_gate.py` | F4 + F7 gate |
| `scripts/vibe_role_assignment_gate.py` | F5 gate (assignment_receipt) |
| `scripts/delegate_capability_gate.py` | F8 execution delegation |
| `scripts/cluster_upgrade_contract.py` | F6 helper |
| `scripts/cluster_component_manifest.py` | FCR-6 invariant |
| `scripts/vibe_approval_receipt.py` | receipt storage (currently 1 class; Stage 2+ to extend to 5) |
| `scripts/vibe_evidence_verifier.py` | F9 9-check + 5-receipt linkage |
| `scripts/vibe_report_schema.py` | F9 7-section schema |
| `scripts/remote_verification_gate.py` | F7 remote_verified helper |

---

## 9. Operator / Orchestrator / Worker Triangle

| Actor | Authority |
|-------|-----------|
| **operator** | final role-node-model assignment; final approval; final merge; final override (always returns to F4 on override) |
| **orchestrator (this spec's primary consumer)** | may **recommend** plans, may write PlanDraft, may NOT approve, may NOT execute L4 |
| **planner / explorer / implementer / reviewer / git-integrator / validator** | execution roles; MUST NOT start before F4-F5 chain is complete; F4-F5 chain MUST include operator_approval_signature matching this operator |

**Drift signal**: if any execution role starts before F5 assignment_receipt is verified, STOP_AND_REANCHOR.

---

## 10. Working Agreement / Acknowledgement

By starting any Stage 3-6 implementation work, the actor (operator, orchestrator, worker) acknowledges:

1. This spec is binding from the moment its PR (Stage 2) is merged.
2. Any implementation that contradicts the spec's fail-closed rule priority is BLOCKED at verification time.
3. Cross-stage work (Stage 3 carrying Stage 6 logic, or vice versa) is forbidden; each stage must close independently before the next stage's pre-audit begins.
4. The 5-receipt chain is enforced at evidence_receipt creation time; storing a partial evidence payload is a drift signal.
5. Any revert of the PR merging this spec requires operator `block_runtime_flow_spec_revert` confirmation, and triggers a STOP_AND_REANCHOR for all in-flight Stage 3-6 work.

---

## 11. Versioning

- **v1.0.0** — initial spec, Baseline02 Stage 2 (this PR)
- future versions MUST be appended to this section, MUST NOT remove or weaken any rule in §6, MUST NOT relax any receipt field in §4, MUST NOT add a level between §5 L2/L3 or L3/L4.
- Major version bump required for any change to §3 sequential order, §4 fields, §5 levels, or §6 rules.

---

## 12. Closing

This spec is the runtime contract. Read it before any Stage 3/4/5/6 pre-audit. Verify §2 anchors, §3 flow, §4 receipts, §5 levels, §6 fail-closed rules, §7 gap absorption before drafting implementation.

If anything is unclear → STOP_AND_REANCHOR. Do not improvise around this spec.
