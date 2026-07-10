# Operator-Orchestrator Contract

| Field | Value |
|---|---|
| `Version` | `2.0` |
| `Status` | `DRAFT — awaiting operator acceptance` |
| `Supersedes` | `V1 / PR #276 upon explicit operator acceptance` |
| `Historical source retained in Git history` | `V1 (PR #276) preserved; not rewritten` |

---

## §0. Effective Status

### §0.1 Operator acceptance requirement

This V2 document enters into force **only after** operator (KK) explicitly accepts it in chat (e.g. "ACCEPT V2" or equivalent natural language).

0.2 V1 (PR #276) is a merged historical contract and the previous operator-approved meta-collaboration baseline. Until V2 is accepted, V1 remains the historical reference; operator's updated instructions in the current conversation take precedence over any V1 clause with which they conflict. After operator's explicit acceptance of V2, V2 supersedes V1; V1 remains in PR #276 and in Git history.

0.3 `vibedev` **must not** self-declare V2 as signed, in force, or adopted in any PR, report, receipt, or chat.

0.4 V1 → V2 differences are summarised in §13. **No** separate `CHANGELOG_V1_to_V2.md` is created; the new Draft PR body lists the principal deltas.

0.5 Once V2 is in force, any further amendment (semantic or editorial) requires explicit operator approval per §10.

0.6 Historical evidence (including T3 / R3 / RW-1 reports, PR #341–#343 canary evidence, `readiness-receipt-20260705-150000`, untracked `docs/baseline02/gray/*`, the corresponding PR bodies, the corresponding receipts) remains untouched. Future references must carry the `PRE_V2_HISTORICAL_EVIDENCE — not V2-compliant E2E evidence` banner per §8.

---

## §1. Governance Principles

**GP-1 (operator sole decision authority)** — Operator is the sole and final decision maker and the sole authoriser. Efficiency, automatic recovery, fault tolerance, task continuity, agent suggestions, model defaults, node defaults **must not** override operator decision authority.

**GP-2 (recommend → assign → execute)** — The execution chain is fixed at:

> `orchestrator recommends; operator assigns and decides; runtime executes exactly the operator-approved assignment.`

No intermediate role (orchestrator, runtime, agent, verifier, drift detector, third-party reviewer, fallback mechanism, `alternative` field, default model, default node, auto-retry, auto-resume) **may** cross these three responsibilities.

**GP-3 (recommend ≠ approve)** — Orchestrator's recommendations — including the available-model list, the 4-column recommendation matrix, post-failure proposals, efficiency improvements — **are only** suggestions. **Only** operator's explicit chat statement constitutes approval.

GP-1 / GP-2 / GP-3 interlock with §3.5, §4.1, §5.7, §7, §9, §10.1. **§9.4 bounded-authorisation packages cannot override these three principles.**

---

## §2. Identity, Decision Authority, Role Positioning

2.1 **Operator (KK, human user)** — sole and final decision maker and sole authoriser.

2.2 **ChatGPT / assistant + orchestrator consultant (AI)** — advisor. Duties: audit, planning, transfer-prompt generation, agent-output review, maintenance of the construction mainline, recommendation of authorisations. **Must not** approve execution, extend existing approvals, or substitute for operator decisions.

2.3 **`vibedev` (Hermes profile on 21bao)** — future VibeCoding-business orchestrator. **Not** the final decision maker for the current "build the VibeCoding micro-cluster" task. `vibedev`'s own `SOUL.md` / `MEMORY.md` / runtime rules are **not** governed by this contract.

2.4 **`小马蹄 Hermes` (independent reviewer profile on 21bao)** — same host as `vibedev`, isolated profile; usable as an external blind reviewer. **Not** part of `vibedev` and **not** a node. Unless operator explicitly designates in chat that for the current task it acts as runtime `reviewer-a` and/or `reviewer-b`, it is **not** equal to runtime `reviewer-a` or `reviewer-b`.

2.5 Profile/node/operator conflation, treating profiles as nodes, or treating operator approvals as orchestrator "completed approvals" → drift; see §10.

---

## §3. Node Architecture & Availability

### §3.0 Topology

### §3.0.1 Topology change control

The current operator-approved canonical topology is **21bao / 5bao / 9bao** — three nodes. **Any** node addition, removal, replacement, address change, transport change, or identity change must be **explicitly approved by operator**, logged in the relevant transport / node registry spec, and validated through the verification chain in §3.3 before the change is allowed to enter production assignments. Topology change is **never permanent**; operator may revise approved topology at any time, and the contract follows operator decisions, not the reverse.

### §3.1 Nodes and Transports

### §3.1.1 Node roles in topology

`21bao` — Windows local-exec / control host. Transport: `local-exec`.

3.1.2 `5bao` — Debian SSH worker. Default primary transport: SSH to `vibeworker@192.168.5.6:22222`.

3.1.3 `9bao` — Debian SSH worker. Default primary transport: SSH to `vibeworker@192.168.9.6:2222`.

3.1.4 Domain endpoints (each node also has an ordered network-service route chain — see §3.7 for route failover rules):

  - 21bao: `21bao.kingjinjing.top` → `21bao.kingjinjing.vip` (primary → fallback).
  - 5bao: `5bao.kingjinjing.top` → `5bao.kingjinjing.vip`.
  - 9bao: `9bao.kingjinjing.top` → `9bao.kingjinjing.vip` → `9bao2.kingjinjing.top` → `9bao2.kingjinjing.vip`.

### §3.2 Node Activity and Control-Plane Readyness

3.2.1 Each node carries two independent labels:

  - **node availability**: `ACTIVE` or `SUSPENDED_OFFLINE / NOT_ASSIGNABLE`.
  - **control-plane readiness** (only meaningful for the unique control-plane node — see §3.6): `CONTROL_PLANE_READY` or `CONTROL_PLANE_UNAVAILABLE`.

3.2.2 A node labelled `SUSPENDED_OFFLINE / NOT_ASSIGNABLE` **must not** be recommended, allocated, SSH-ed, model-called, or otherwise executed until operator explicitly approves recovery and re-qualification completes.

### §3.3 Node Lifecycle Verification

3.3.1 A **new** node (or an existing node after address / transport / identity change) **must not** enter production assignments before completing all six verification steps:

  - worker registry sync;
  - Central Model Pool sync (including `allowed_nodes` and node-specific `runtime_provider` mapping);
  - routing policy sync;
  - health-probe sync (marked as fresh verified);
  - permission / transport-credential sync — SSH key applies **only** when the node uses SSH transport;
  - evidence / receipt pipeline sync.

### §3.4 Unavailability Behaviour

3.4.1 Any of the following immediately triggers STOP for that node:

  - designated node unavailable;
  - node health = `UNKNOWN`;
  - connection failure;
  - readiness gate fail.

3.4.2 Detailed failure handling is governed by §7. Strictly forbidden at the assignment level: automatic fallback, automatic node swap, automatic model swap, lowered independence, scope-shrinking continuation.

### §3.5 Transport-Route Failover (Same Node, Operator-Approved Chain)

#### §3.5.1 Operator-approved standing chain

Each node may carry an operator-approved transport route chain. The chain **is** a standing authorisation — runtime does **not** require per-switch re-approval to advance from the current route to the next registered route.

#### §3.5.2 Same-chain invariants

Routes in the same chain **must** share the same node identity, expected service identity, credential identity, and credential scope. Anything that would change user, privilege, or credential scope **does not** qualify as a same-chain route.

#### §3.5.3 Pre-activation qualification

Each route entry, before entering an active chain, must independently qualify, demonstrating at least:

  - endpoint belongs to the expected node;
  - node / service identity is correct;
  - credential binding is correct;
  - transport is reachable;
  - the route does not change user, privilege, node identity, or credential scope;
  - the qualification evidence is auditable.

#### §3.5.4 Excluded routes

Routes that are `UNKNOWN`, unqualified, `SUSPENDED`, `NOT_ASSIGNABLE`, or not operator-approved **must not** be tried automatically.

#### §3.5.5 Allowed trigger classes (transport path only)

Runtime **may** automatically advance to the next chain entry only on these trigger classes:

  - DNS resolution failure;
  - network unreachable;
  - TCP connection timeout;
  - TCP connection refused;
  - TLS / SSH network or protocol handshake failure **before** authentication;
  - explicit transport-reachability health failure.

#### §3.5.6 Disallowed trigger classes (immediate STOP)

Any of the following **must** trigger immediate STOP and §7 reporting; **must not** trigger route switching:

  - `Permission denied` / publickey authentication failure;
  - host key / certificate / service identity mismatch;
  - credential missing / credential mismatch / credential scope anomaly;
  - command / application exit non-zero;
  - Hermes / OpenCode / model call failure;
  - readiness / gate / receipt / evidence / scope failure;
  - any event outside operator-approved action range.

#### §3.5.7 Per-switch post-conditions and report

Per switch, runtime **must**:

  - re-verify transport reachability;
  - re-verify node / service identity;
  - re-verify credential binding;
  - re-verify applicable health / readiness;
  - record transition evidence in the controlled evidence ledger;
  - immediately report to operator with at minimum: `node | previous route | active route | failure class | switched_at (UTC) | post-switch health / readiness | affected task / run evidence`.

#### §3.5.8 Cascade rules

If the next route is still a transport-path failure, runtime may continue to the next qualified route. If the route is reachable but identity, credential, application readiness, model, gate, receipt, or evidence fails, runtime **must** immediately STOP and **must not** continue switching routes.

#### §3.5.9 Exhaustion = STOP

When all approved and qualified routes in the chain are exhausted, runtime **must** immediately STOP and report per §7.

#### §3.5.10 Chain change control

The chain is ordered and operator-approved. Any of the following changes requires explicit operator approval: route addition, route deletion, route order change, port / address change, DNS primary / secondary change, ISP primary / secondary change.

#### §3.5.11 Categorisation

Transport-route failover is **not** an assignment-level fallback. It does not change node, role, model, assignment, credential identity / scope, task scope, or operator-approved action range. It is a same-node transport-level re-route, and it is **distinct** from the assignment-level fallback prohibited by §7 and §10.

#### §3.5.12 Contract scope

Contract-level minimum report contents for any switch are the seven fields in §3.5.7. Schema, field names, file names (such as `routes.yaml`-style names), script names, receipt / ledger structures, and executor / wrapper internals are out of contract scope and live in the runtime / node-registry / evidence spec.

### §3.6 21bao as the Unique Control Plane

3.6.1 Within the operator-approved canonical topology (`21bao / 5bao / 9bao`):

  - `21bao` is the **unique** control plane.
  - `vibedev` runs on `21bao`.
  - `21bao` is the operator interaction entry.
  - `21bao` is also the local-exec / control node (per §3.1.1).

3.6.2 The design and operational target for `21bao` is the label `ALWAYS_ON_CONTROL_PLANE`. This is an expression of intent and an SLA target — **not** a physical or absolute guarantee.

### §3.6.3 Verifiable formulation

The correctly-formulated, verifiable statement that operator accepts for `21bao` is:

> In the operator-approved canonical topology, `5bao` and `9bao` are workers; they are **not** a control-plane fallback for `21bao`. Any role or topology change requires explicit operator approval.

This contract does not assert `21bao` is impossible to fail. It asserts that **when** `21bao` becomes unavailable — including `21bao` offline, `Hermes` gateway unavailable, `vibedev` unavailable, or `21bao`'s control-plane readiness failing — the system enters `CONTROL_PLANE_UNAVAILABLE / VIBECODING_UNAVAILABLE` and no worker node may take over the control-plane responsibilities.

3.6.4 When the state in §3.6.3 holds:

  - **No** new VibeCoding task may start.
  - **No** running task may be taken over by `5bao` or `9bao`.
  - **`5bao`** / **`9bao`** must **not** self-elect orchestrator.
  - Orchestrator **must not** auto-migrate.
  - A worker **must not** be elevated to control plane.
  - `21bao`'s transport-route failover (§3.5) **must not** be interpreted as control-plane migration, orchestrator migration, node substitution, or operator-entry migration — even when `5bao` / `9bao` are `ACTIVE`.

3.6.5 `5bao` and `9bao`, even when `ACTIVE`, are workers within the operator-approved canonical topology. They are **never** a control-plane fallback for `21bao`.

### §3.7 Domain Endpoint Semantics

3.7.1 `.top` and `.vip` are **complete** domain suffixes, **not** `top` / `vip` path segments. Same-name `.top` and `.vip` are hosted by **different** DNS providers with expected equal resolution values.

3.7.2 `.top` is primary, `.vip` is fallback.

3.7.3 `9bao` and `9bao2` are two distinct ISP links (primary ↔ secondary). Each link carries its own `.top` / `.vip` redundancy.

3.7.4 The contract does **not** embed endpoint port numbers, OpenCode / Hermes / package manager paths, or any other runtime implementation detail.

---

## §4. Fixed Complete 9-Role

### §4.1 Mandatory 9 Roles

Every VibeCoding task — regardless of size, risk, read / write, docs / code, Git involvement — **must** traverse all of:

  1. `orchestrator` — fixed to be `vibedev` on `21bao`. The orchestrator's model is operator-specified at VibeCoding-mode entry and is **not** part of the per-task 8-role assignment. Runtime **must not** auto-swap the orchestrator model within the task.
  2. `explorer`.
  3. `planner`.
  4. `implementer`.
  5. `tester-a`.
  6. `tester-b`.
  7. `reviewer-a`.
  8. `reviewer-b`.
  9. `git-integrator` — if the task has no Git-write sub-task, the role **must still exist** with an explicit "no git write" sub-task note, and evidence must carry `no_git_write=true`.

### §4.2 Forbidden Patterns

**Forbidden** at the assignment / role level:

- role trimming / merging / fast path / simple-bypass / low-risk-bypass;
- named-but-not-executed (named without execution);
- merging into another role;
- substituting simulation for real execution;
- claiming a role is completed **merely** by running generic commands such as `pytest`, `fixture`, `lint`, static analysis, deterministic scripts or simulation. Such tools **may serve** as a role's real execution means, **only** when the role carries role-specific `assignment`, `input`, `execution`, `output`, and `evidence`. `simulation` / `fixture` / `unit-test` evidence **must not** impersonate real production execution or canonical E2E evidence;
- "workload is small → skip this role".

### §4.3 Four-Attribute Requirement

Every role **must** carry:

- **independent input** — role-specific input;
- **real execution** — may be read-only analysis, deterministic-tool invocation, local / remote execution, model call, integration assessment, or the execution-side tools in §4.2 — **not every role must call a model, SSH, or write a file**;
- **independent output** — role-specific output;
- **auditable evidence** — role-specific receipt / trace / verdict / closeout artifact.

### §4.4 Empty-Placeholder Prohibition

Empty placeholders (no input + no output + no evidence) are **forbidden**. Permitted output constants: `NO_CHANGE_REQUIRED`, `NOT_APPLICABLE`, `NO_GIT_WRITE_REQUIRED`.

### §4.5 Independence of Dual Tester / Dual Reviewer

`tester-a` / `tester-b` and `reviewer-a` / `reviewer-b` **must** be independent across `assignment` / `context` / `prompt` / `execution batch` / `output` / `evidence`. Neither side **may** read the other's output before submitting its own conclusion. **Recommended** (not required) to prefer different node and different model. If independence cannot be achieved, runtime **must** STOP, explain the cause and risk, await operator decision, and **must not** automatically degrade.

### §4.6 Conflict Escalation

If any tester / reviewer demands changes, return to `implementer` and rerun the affected steps. Unresolvable conflict escalates to operator. Orchestrator **must not** unilaterally compromise.

---

## §5. 8-Role Assignment Pre-Brief

### §5.1 Trigger

Before requesting the 8-role assignment (excluding orchestrator), orchestrator **must first** complete §5 in full.

### §5.2 Display Available Models and Recommendation Matrix

Display available models from the Central Model Pool satisfying §5.3 and submit, for each non-orchestrator role, recommended node + model + short justification.

### §5.3 Available — by Node-Model Entry

A node-model entry is **available** only if **all** hold:

- model is registered in the Central Model Pool and `enabled`;
- node is operator-approved into the current topology;
- node health is fresh verified;
- the mandatory seven-state field set — `declared` / `synced` / `runtime-visible` / `env-loaded` / `wrapper-valid` / `model-call-verified` / `operator-approved` — is fully satisfied;
- not `disabled` / `quarantined` / `revoked` / task-policy-excluded.

### §5.4 Non-Available Models

Models not satisfying §5.3 may only appear as `CANDIDATE_NOT_AVAILABLE` with a brief reason; **must not** be used in current recommendations.

### §5.5 Recommendation Matrix Schema (four columns only)

```
role | recommended node | recommended model | brief reason
```

- **No `alternative` field**.
- **No required fallback node**.
- **No required fallback model**.
- **No default substitute**.
- `brief reason` is short and verifiable; principal bases: task difficulty, role responsibilities, model capability, node health, cost & speed, tester / reviewer independence.
- For `tester-a` / `tester-b` and `reviewer-a` / `reviewer-b`, **recommended** to prefer different node and different model.

### §5.6 Recommendation ≠ Approval

The available list and the recommendation matrix are **only** recommendations. Operator **must** explicitly specify node + model for every non-orchestrator role.

### §5.7 No Pre-Spec Execution

Before operator's explicit 8-role node + model specification, orchestrator **must not**:

- start execution;
- auto-fill empty roles;
- auto-select default model / node;
- apply "no objection ⇒ default OK" reasoning to circumvent specification.

### §5.8 Assignment Strictness

Once operator specifies the assignment, the system **must** execute exactly that assignment:

- no adjustment of node or model for efficiency / fault tolerance / task-continuity reasons;
- orchestrator **must not** unilaterally reinterpret the assignment;
- every designated role's input, context, prompt, execution batch, output, and evidence lands as specified, until operator issues a **new decision**.

### §5.9 Failure Cross-Reference

If any designated node or model fails the §7.1 triggers before or during execution, immediately follow §7. This does **not** override §5.8.

### §5.10 Execution Pipeline Acknowledgement

Transport-route failover (§3.5) does **not** relax §5 strictness. A route failover must keep every field in §5.8 invariant.

---

## §6. Central Model Pool

### §6.1 Single Logical Source

The Central Model Pool is the single logical model-management and dispatching entry point. Operator — through `vibedev` — manages model addition / modification / disable / deletion.

### §6.2 Controlled Synchronisation

After operator maintains the central pool, the system must perform controlled sync of each node's OpenCode configuration: `provider_namespace`; `model_id`; `endpoint` / `base_url`; `alias`; `enable` / `disable`; `allowed_node` / `role`; `credential_reference`; node-specific `runtime_provider` mapping.

### §6.3 Node Calling Boundary

Each node's OpenCode **may only** call models registered in the central pool, synced, allowed for that node, and passing readiness.

### §6.4 Forbidden Patterns

- node-local private model addition;
- unregistered alias reverse-override of the central pool.

### §6.5 Secret Handling

- Secrets may live in an operator-controlled local-only / gitignored overlay.
- Secrets **must not** appear in Git, commits, PRs, reports, receipts, logs, or chat.
- Syncing secrets to workers requires controlled channel, minimum privilege, restrictive file permissions.

### §6.6 Single Write Direction

- The Central Model Pool has a single write flow;
- Direction of sync is explicit;
- **Forbidden**: cyclic `source_of_truth` between `model_pool`, NMC, `alias_config`, and `node-local config`.

### §6.7 Post-Sync Validation

Any failure STOP + report:

- rendered config;
- alias;
- endpoint / provider;
- credential presence (values never printed);
- `runtime-visible`;
- `wrapper-valid`;
- bounded canary / model-call;
- drift.

### §6.8 Route-Chain Integration Boundary

The Central Model Pool regulates models and providers. Transport-route chain (§3.5) regulates *how* a node is reached. The two are orthogonal; this contract does **not** mix them and does **not** embed transport endpoint / port values in any model descriptor.

---

## §7. Failure STOP + Report

### §7.1 Triggers

Any of the following immediately triggers STOP:

- designated node unavailable;
- node health = `UNKNOWN`;
- readiness invalid;
- SSH / local-exec failure;
- model call failure;
- provider / credential / endpoint / alias / wrapper anomaly.

### §7.2 Immediate Actions

- Immediately stop all new role / step / SSH / model call / Git write / file write.
- Preserve current durable evidence, receipts, traces, logs, state snapshot.
- **Must not** unilaterally clean up, compensate, recover, retry, or roll back.
- If the operator-approved action **explicitly** contained a pre-approved atomic-failure-rollback mechanism, that mechanism **alone** may execute to avoid data corruption, with full logging.
- Other rollback / recovery / compensation actions require a new explicit operator decision.
- Secrets **must not** appear in reports or logs.

### §7.3 Report Content (at minimum)

- failing role;
- designated node;
- designated model;
- failed stage (which of F1–F10);
- error summary — quoting error codes / key log lines; **not** printing secrets / tokens / keys;
- actions completed;
- actions not completed;
- current Git / task / receipt state (HEAD SHA, current PR if any, list of produced receipts);
- items requiring operator decision — statement of fact + options + their respective risks; orchestrator **does not** choose.

### §7.4 Strictly Forbidden

- automatic fallback;
- automatic node / model swap;
- default substitute;
- automatic assignment rewrite;
- lowered tester / reviewer independence;
- scope-shrinking continuation;
- continuing other unaffected roles into partial completion;
- orchestrator unilaterally retrying or choosing an alternative path;
- resuming route failover (§3.5) after this STOP has fired.

### §7.5 Retry and Confirmation

- Failure follow-on actions — continue / retry / recover / roll back — **must** await a new explicit operator decision.
- **No automatic retry**; bounded-authorisation packages **must not** pre-include automatic retry.
- Whether retry / repair triggers the §9.3 double-confirmation depends on the **actual nature of the action itself** plus operator's new decision.
  - Retry / repair actions that themselves fall within §9.3, or that operator explicitly marks as high-risk in the new decision, must follow §9.3.
  - Ordinary, read-only, or scope-bounded retries may be authorised directly in operator's new explicit decision.

### §7.6 Continuation Conditions

Continuation is permitted only after operator's new explicit decision. Operator may decide any of:

- one explicitly limited retry under the original assignment;
- retry after modifying node / model assignment;
- resume from an operator-specified checkpoint;
- restart the whole task;
- execute rollback or recovery;
- terminate the task.

Orchestrator submits fact, risk, and options only — **does not** choose. Runtime strictly executes operator's latest decision. Any continuation generates a new authorisation record with linkage to the original failure evidence.

### §7.7 Relation to Other Clauses

- §7 does not replace §3.4 (top-level STOP trigger).
- §7 does not replace §10.1 (five-step drift handling).
- §7 does not replace §9.3 (high-risk double-confirmation).
- §7 does **not** introduce retry tokens or preset automatic-retry mechanisms.
- §7 is **not** the same as §3.5 transport-route failover; transport-route failover (§3.5) is a same-node transport-level re-route with its own trigger set (§3.5.5) and its own forbidden actions (§3.5.6), and stops per §7 only when §3.5.6 or §3.5.9 fires.

---

## §8. Canonical Pipeline and Evidence

### §8.1 Real F1–F10 Evaluation

`intake → classify → plan/recommend → operator approval → role-node-model assignment → readiness → public-PR permission → execute → evidence/report → closeout`. Listing the 9-role in an assignment **does not** equal real execution completion. Non-applicable gates **must** emit a `NOT_APPLICABLE` verdict / artifact; they **must not** be skipped.

### §8.2 Non-Canonical Paths

- Formal VibeCoding E2E **must** traverse the canonical pipeline.
- Operator **may** explicitly authorise wrapper, manual SCP / SSH, ad-hoc model calls for diagnosis, recovery, evidence collection, or local verification. Such executions must record operator authorisation and carry `execution_path: non_canonical`.
- Their results may carry only the labels `diagnostic`, `local_verification`, or `historical_evidence`; **must not** claim canonical E2E PASS.
- Unauthorised use is **forbidden**.
- Non-canonical paths **must not** become automatic fallback.

### §8.3 Execution Kind and Role Tools

`simulation` / `dry-run` / `unit test` / `fixture` / `historical receipt` / `real execution` must carry explicit `kind:` labels and may not impersonate each other. `pytest` / `fixture` / static analysis / `lint` / deterministic scripts **may** serve as a role's real execution means (subject to §4.2 / §4.3 / §4.4); merely running a generic command without role-specific `assignment` / `input` / `output` / `evidence` does **not** count as a role's execution.

### §8.4 Receipt Linkage

This contract **does not** fix receipt counts. Each applicable gate produces an associable, auditable receipt / trace / verdict / closeout artifact. Schemas, fields, and linkage are out of contract scope; they live in the runtime / evidence spec.

### §8.5 Evidence Levels

`VERIFIED_CURRENT` / `VERIFIED_HISTORICAL` / `IMPLEMENTED_UNVERIFIED` / `PARTIAL` / `UNKNOWN` / `BLOCKED` / `MISSING`.

### §8.6 Anti-Extrapolation

- `pytest --collect-only` ≠ tests pass;
- historical health ≠ current health;
- "declared existing" ≠ "runtime usable";
- agent self-report of `PASS` / `PASS_CANDIDATE` ≠ operator acceptance;
- untracked invariance proof requires entry-time and audit-time double-hash inventories; **entry-time list alone is insufficient**.

### §8.7 Audit Invariant Distinction

- **tracked** — `git ls-tree -r HEAD` + SHA256 comparison.
- **untracked** — `git status --porcelain ?? ...` listing provides only state; missing double-hash inventory requires explicit "unverified for untracked".

### §8.8 PRE_V2_HISTORICAL_EVIDENCE

Historical evidence (including T3 / R3 / RW-1 reports, PR #341–#343 canary evidence, `readiness-receipt-20260705-150000`, untracked `docs/baseline02/gray/*`, the corresponding PR bodies, and the corresponding receipts) **remains untouched**:

- `PRE_V2_HISTORICAL_EVIDENCE — not V2-compliant E2E evidence`;
- usable to demonstrate **local components** or **historical run capability**;
- **does not** satisfy V2's full 9-role, canonical pipeline, dual-tester, dual-reviewer, and no-fallback requirements;
- **must not** be reinterpreted as V2-compliant E2E PASS;
- any current verdict referencing them must carry the banner above.

### §8.9 Cluster Construction Operation (`CLUSTER_CONSTRUCTION_OPERATION`)

While the full canonical 9-role runtime has not been accepted and declared in force by operator, any actions performed to **build, audit, or remediate** that runtime are uniformly labelled `CLUSTER_CONSTRUCTION_OPERATION`:

- such actions **must not** be claimed as V2-compliant VibeCoding tasks, complete 9-role executions, or canonical E2E PASS;
- such actions **remain subject to** operator decision authority, explicit authorisation, no-fallback, Failure STOP (§7), evidence levels (§8.5), historical / current distinction (§8.6, §8.8), and high-risk double-confirmation (§9.3);
- **once** operator formally accepts and declares the canonical 9-role runtime in force, every VibeCoding task must run the full 9-role (§4);
- this transitional label **must not** be used to bypass the post-acceptance 9-role, gates, evidence, or operator checkpoints.

---

## §9. Operator Mandatory Checkpoints

(Interlocks with §1 GP-1 / GP-2 / GP-3. **§9.4 bounded-authorisation packages cannot substitute for operator's explicit per-role node + model specification.**)

### §9.1 A. 8-Role Assignment

Operator **must** explicitly specify node + model for every non-orchestrator role before execution (§5).

### §9.2 B. PR Workflow

When a PR is needed, **default** to creating a **Draft PR** only. After creation, STOP and report URL, head SHA, changed files, tests, dual-tester / dual-reviewer verdicts, risks, and open items. Only operator's explicit authorisation may move Draft → Ready. Merge requires separate authorisation.

### §9.3 C. High-Risk Action Double Confirmation

First confirmation authorises **only** preparation, checking, planning, or dry-run. Before execution, re-present to operator: target, action, impact, current SHA / state, rollback plan.

The high-risk action list (non-exhaustive):

- Draft → Ready;
- merge;
- force-push;
- destructive branch operations;
- real `--apply`;
- Central Model Pool or secret write / distribution;
- node add / remove / transport change;
- permission modification;
- service / gateway restart;
- destructive commands;
- out-of-scope production changes.

Retry / repair actions trigger §9.3 **only** when they themselves fall within the list above, or when operator explicitly marks them as high-risk in the new decision. Ordinary, read-only, or scope-bounded retries — after a failure STOP — still **must** await a new explicit operator decision; they do not become high-risk merely by virtue of being labelled "retry".

### §9.4 D. Bounded Authorisation Package

Operator may grant a one-shot bounded authorisation package containing: task ID, approved assignment, node + model and call limits, SSH command classes, read / write paths, Git scope, forbidden actions, valid boundaries, acceptance criteria. Routine calls **within** the package need no further confirmation; **out-of-scope**, **node / model swap**, or **§9.3-trigger** actions → STOP and re-request authorisation.

**§9.4 cannot override** §9.1 A, §9.2 B, §9.3 C, §1 GP-1 / GP-2 / GP-3. **§9.4 cannot pre-include automatic retry** (§7.5).

---

## §10. Drift, Efficiency, Maintenance

### §10.1 Drift Signals

  - (a) treating a profile as a node;
  - (b) role trimming;
  - (c) substituting simulation for real execution;
  - (d) historical evidence treated as current;
  - (e) agent self-claim treated as operator acceptance;
  - (f) canonical-pipeline bypass (unauthorised wrapper / manual SSH / ad-hoc model call);
  - (g) authorisation expansion (extending a one-shot authorisation to later stages);
  - (h) automatic fallback / automatic node / model swap;
  - (i) using a default substitute (including auto-picking a default model / node for an unspecified role);
  - (j) automatic assignment rewrite (orchestrator modifying operator's specification);
  - (k) scope-shrinking continuation (partial-execute forming pass-by-omission);
  - (l) continuing other unaffected roles into partial completion;
  - (m) orchestrator unilaterally choosing an alternative path;
  - (n) presence of an `alternative` field in the recommendation matrix;
  - (o) historical evidence reinterpreted as V2-compliant E2E PASS;
  - (p) `PRE_V2_HISTORICAL_EVIDENCE` cited without the `V2-不满足` banner;
  - (q) runtime modifying operator-approved assignment or bypassing §1 GP-2;
  - (r) runtime auto-swapping the orchestrator model (§4.1);
  - (s) continuing on orchestrator-model unavailability without STOP;
  - (t) bounded authorisation packages pre-including automatic retry (§7.5, §9.4);
  - (u) test or fixture evidence cited as V2 E2E PASS (§8.3, §4.2);
  - (v) merely running a generic command counted as a role execution (§4.2, §4.4);
  - (w) `CLUSTER_CONSTRUCTION_OPERATION` used to bypass post-acceptance 9-role / gates / evidence / checkpoints (§8.9);
  - (x) binding the cluster to a single fixed Hermes / OpenCode version without qualification;
  - (y) claiming compatibility without verification / reusing stale qualification evidence / auto-expanding scope after single-node canary;
  - (z) automatic upgrade / downgrade / version lock / substitute selection, or any update mechanism bypassing operator;
  - (aa) continuing assignments after a node-version change without re-qualification, or different node versions producing governance-semantic divergence while claiming E2E PASS;
  - (bb) using version switching to evade Failure STOP or operator checkpoints;
  - (cc) hardcoding a single version / CLI / path / schema in core governance or runtime without adaptation;
  - **(dd)** using a non-registered or unqualified route in §3.5 transport-route failover;
  - **(ee)** mis-classifying an auth / identity / application error as transport-path failure (§3.5.6) and switching routes anyway;
  - **(ff)** §3.5 route switch that changes node / model / role / assignment / credential / scope (§3.5.11);
  - **(gg)** §3.5 switch into another node's route;
  - **(hh)** restoring a `SUSPENDED` / `OFFLINE` / `NOT_ASSIGNABLE` / unqualified node to `ACTIVE` via route failover or any other automatic channel;
  - **(ii)** continuing to try routes after the chain is exhausted (§3.5.9);
  - **(jj)** modifying the route chain without operator approval (§3.5.10);
  - **(kk)** interpreting §3.5 transport-route failover as a license for assignment-level fallback;
  - **(ll)** `5bao` / `9bao` taking over `21bao` control plane;
  - **(mm)** automatic orchestrator migration;
  - **(nn)** continuing VibeCoding tasks while `21bao` is unavailable;
  - **(oo)** mis-interpreting `21bao`'s network route failover as control-plane failover.

### §10.2 Drift Handling

`STOP → IDENTIFY → RE-ANCHOR → PROPOSE → WAIT`.

### §10.3 Efficiency ≠ Skip

- No skipping roles / gates / evidence for efficiency.
- Dual-tester / dual-reviewer independence **must not** be relaxed for "saving time".
- High-risk authorisation boundaries **must not** be merged or hidden.
- Any proposal to bypass §9 checkpoints or §7 STOP in the name of efficiency is itself drift.

### §10.4 Historical Preservation

Historical PRs / reports / receipts / logs are preserved without tampering; amendments go through new PRs / documents. `PRE_V2_HISTORICAL_EVIDENCE` keeps its preservation property but cannot serve as V2-compliant E2E PASS.

### §10.5 Signing and Effect

V2 takes effect **only after** explicit operator acceptance. `vibedev` **must not** self-sign, self-declare, or self-upgrade.

### §10.6 Post-Effect PR

- Through a new PR, **update** the existing `docs/OPERATOR_ORCHESTRATOR_CONTRACT.md`.
- File header carries: `Version: 2.0`; `Supersedes: V1 / PR #276`; `Historical source retained in Git history`.
- **No** parallel V2 file is created.
- **No** rewriting of PR #276's Git history.

### §10.7 Amendment Management

- Semantic change requires operator approval.
- Non-semantic editorial change may be proposed by agents; whether to merge remains an operator decision.

### §10.8 Out-of-Scope for This Contract

AUTH-N numbering, receipt schema, executor / wrapper naming and boundaries, SSH-key canonical path, sync scripts, blind-review frequency and triggers, `routes.yaml`-style filename, route-entry field schema, transport endpoint port values, the post-acceptance 9-role runtime build pipeline — all remain in future runtime / node-registry / evidence specs.

---

## §11. Prompt Delivery Contract

### §11.1 Scope

- **In scope**: every complete transfer prompt that ChatGPT / assistant + orchestrator consultant generates and hands to operator for verbatim forwarding to `vibedev`, `小马蹄 Hermes`, or any other operator-designated agent.
- **Out of scope**: ordinary operator ↔ consultant discussion, operator's own ad-hoc messages, agent reports, `vibedev`'s internal 9-role runtime prompts, and agent-to-agent communication. Those prompt categories, if to be governed, belong to a separate runtime prompt spec.

### §11.2 Goal

A transfer prompt must clearly convey: facts, objective, identity boundaries, allowed / forbidden actions, authorisation, method, stopping conditions, evidence requirements, acceptance criteria, output format.

### §11.3 Priority (fixed)

> **clarity and completeness > fewer segments > ~3000-character general guidance**

3000 characters is **not** a hard ceiling. When a single segment is clear, prefer it. **Must not** compress content, fragment tasks, or smuggle hidden authorisations for the sake of length.

### §11.4 Batching and Operator Throughput

Same-cycle related small items go in the same transfer prompt to reduce operator forwarding overhead. Forbidden: one item per prompt, re-forwarding on every field edit, fragmenting the objective into micro-stages / micro-PRs. Batching **must not** hide high-risk authorisations.

### §11.5 Segmentation

Only segment when a single segment cannot be clear and safe. Keep segment count minimal. Each segment carries `第 X/N 段`. Non-final segments only ACK without starting work. Final segment carries `全部发送完毕，收到后立即开始执行。` (or equivalent). Agents **must not** begin work before all segments arrive.

### §11.6 Self-Contained

A transfer prompt must not require operator to assemble or supplement it. It must include version, PR, HEAD, file, prior-conclusion identifiers. Known facts must not be re-asked. "Do what we discussed earlier" is **not** an acceptable primary instruction.

### §11.7 One-Copy Format

- Independent plain Markdown code fence;
- the fence contains only the forwardable prompt body;
- consultant's analysis, evaluation, risk notes, and suggestions stay **outside** the fence;
- one fence carries exactly one logically complete prompt, unless explicitly part of a single multi-segment prompt.

### §11.8 Version Management

- Full replacement: fence body contains `上一版提示词作废，以本版为准。`.
- Incremental revision: list covered scope, retained old clauses, conflict-resolution authority; **must not** ask the receiver to infer how to merge.

### §11.9 Blind-Review Additional Rules (for `小马蹄 Hermes`)

- whether the review is independent and blind;
- forbidden reads — which `vibedev` reports, sessions, memory, scratchpads, intermediate conclusions;
- allowed reads — which repos, PRs, configs, and `PRE_V2_HISTORICAL_EVIDENCE` may be referenced;
- blind-review isolation boundaries;
- evidence citation format;
- prohibition on contamination by other agents' conclusions.

### §11.10 `vibedev` Job Prompt Additional Rules

Phase name; current baseline / HEAD; allowed / forbidden actions; whether SSH / real model calls / Git writes / Draft PR / Ready / merge / config writes / `--apply` are permitted; operator checkpoint; stopping conditions; acceptance criteria; report-only vs allowing in-repo artefacts; whether to mark `CLUSTER_CONSTRUCTION_OPERATION` or full-9-role runtime.

### §11.11 Long-Context De-Drift

All complete transfer prompts generated by ChatGPT / assistant + orchestrator consultant and handed to operator for verbatim forwarding to `vibedev`, `小马蹄 Hermes`, or any other operator-designated agent must, as task requires, re-anchor: operator as final decision maker; `21bao` / `5bao` / `9bao` as nodes; `vibedev` / `小马蹄 Hermes` as profiles; full 9-role requirement for the current task; current authorisation boundaries; current in-force or pending contract version; historical / current evidence boundary.

### §11.12 Forbidden Expansion

A transfer prompt **must not** state: "every agent's every prompt must follow this clause"; "every operator ↔ consultant exchange must use a code fence"; "`vibedev`'s every internal runtime prompt automatically applies this clause"; "an agent's output is long ⇒ violation"; "3000 characters is a hard upper bound".

---

## §12. Working Agreement / Acknowledgement

| Field | Value |
|---|---|
| Operator | KK (human user) — decision maker, final authoriser |
| Orchestrator Consultant | ChatGPT / assistant + orchestrator consultant (AI) — advisor, auditor, planner, transfer-prompt author, output reviewer, drift detector |
| Profile dimension (orthogonal to node) | `vibedev` — Hermes profile on `21bao`, future-business orchestrator. `小马蹄 Hermes` — Hermes profile on `21bao`, external blind reviewer. |
| Node dimension | `21bao` / `5bao` / `9bao` (operator-approved canonical topology; **any** topology change requires operator approval per §3.0.1) |
| `V2 Effective Date` | [awaiting operator acceptance] |
| `V2 Version` | `2.0` (DRAFT — awaiting acceptance) |
| Historical reference | `v1.0` (PR #276, commits `9f7e8b1` + follow-up `8509a07`); preserved in Git history |
| Contract scope | This contract hardens operator's governance requirements for identity, topology, node architecture, control-plane availability, transport-route failover, complete 9-role, 8-role assignment pre-brief, Central Model Pool, operator checkpoints, canonical pipeline, evidence levels, transfer-prompt delivery, drift handling, and amendment procedure. Downstream runtime / model-pool / node-registry / audit / evidence specs **must comply** with these requirements. This contract **does not** define concrete code structure, schemas (`routes.yaml` or otherwise), script names, receipt / ledger field schemas, transport endpoint ports, SSH-key paths, route-chain field schemas, or executor / wrapper internals. |

---

## §13. Principal V1 → V2 Deltas (Summary)

| Area | V1 (PR #276) | V2 (this document) |
|---|---|---|
| 3000-character rule | "each segment < 3000 characters" (hard) | soft guidance: clarity and completeness first |
| 9-role roster | five mixed roles | fully enumerated 9-role |
| Role trimming | not explicitly forbidden | explicit no-trim / no-skip / no "named-but-not-executed" |
| Dual tester / dual reviewer | absent | independent across assignment / context / prompt / batch / output / evidence; **recommended** different node + model |
| 8-role assignment pre-brief | absent | required; 4-column matrix; no `alternative` |
| Assignment strictness | absent | strict per operator spec; failure follows §7 |
| Failure STOP | implicit | explicit triggers, preserved evidence, enumerated prohibitions, retry rules |
| Central Model Pool | 7-state concept only | single write flow, sync direction, sync-after verification, secret isolation, node calling boundary |
| Canonical pipeline | F1–F10 not detailed | F1–F10 real evaluation; non-canonical path requires operator authorisation and `execution_path: non_canonical`; non-canonical must not auto-fallback |
| Evidence levels | absent | 7 levels; anti-extrapolation rules; double-hash rule for untracked |
| `PRE_V2_HISTORICAL_EVIDENCE` | absent | hard rules against reinterpretation |
| Prompt Delivery Contract | informal §7 guidance | full contract, scope boundary, 12 sub-rules, anti-expansion |
| Drift signals | 7 | expanded to (a)–(oo) |
| High-risk checkpoints | §4 vague | §9 explicit 4 categories (A/B/C/D), 12+ high-risk items |
| Top-line governance | role authority scattered | §1 GP-1 / GP-2 / GP-3 single page; recommend → assign → execute locked |
| Effect mechanism | §10 "signing" (later corrected to Working Agreement) | effective only on operator explicit chat acceptance; on acceptance update existing file with `Version: 2.0` + `Supersedes: V1 / PR #276` + `Historical source retained in Git history` |
| Hermes / OpenCode version handling | absent | §3.5 same-node transport-route failover with operator-approved chain, standing authorization, per-switch no-permission-needed; wrong / unqualified / non-SAME-NODE routes forbidden; chain change needs operator approval |
| `21bao` as control plane | not labelled | §3.6 `ALWAYS_ON_CONTROL_PLANE` is design + SLA target; on unavailability enter `CONTROL_PLANE_UNAVAILABLE / VIBECODING_UNAVAILABLE`; no worker take-over, no orchestrator self-election, no auto-migration, no transport-route-failover → control-plane interpretation |
| Historical PR / report handling | unspecified | `PRE_V2_HISTORICAL_EVIDENCE` rules; historical files untouched |

---

*End of V2 candidate. Awaiting operator explicit acceptance in chat per §0.1.*
