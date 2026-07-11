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

This V2 document enters into force **only after** operator (KK) explicitly accepts it in chat.

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

GP-1 / GP-2 / GP-3 interlock with §3, §4.1, §5.7, §7, §9, §10.1. **§9.4 bounded-authorisation packages cannot override these three principles.**

---

## §2. Identity, Decision Authority, Role Positioning

2.1 **Operator (KK, human user)** — sole and final decision maker and sole authoriser.

2.2 **ChatGPT / assistant + orchestrator consultant (AI)** — advisor. Duties: audit, planning, transfer-prompt generation, agent-output review, maintenance of the construction mainline, recommendation of authorisations. **Must not** approve execution, extend existing approvals, or substitute for operator decisions.

2.3 **`vibedev` (Hermes profile on 21bao)** — future VibeCoding-business orchestrator. **Not** the final decision maker for the current "build the VibeCoding micro-cluster" task. `vibedev`'s own `SOUL.md` / `MEMORY.md` / runtime rules are **not** governed by this contract.

2.4 **`小马蹄 Hermes` (independent reviewer profile on 21bao)** — same host as `vibedev`, isolated profile; usable as an external blind reviewer. **Not** part of `vibedev` and **not** a node. Unless operator explicitly designates in chat that for the current task it acts as runtime `reviewer-a` and/or `reviewer-b`, it is **not** equal to runtime `reviewer-a` or `reviewer-b`.

2.5 Profile/node/operator conflation, treating profiles as nodes, or treating operator approvals as orchestrator "completed approvals" → drift; see §10.

---

## §3. Node Architecture, Routing, Transport-Route Failover, Control-Plane Availability

### §3.0 Topology

#### §3.0.1 Topology change control

The current operator-approved canonical topology is **21bao / 5bao / 9bao** — three nodes. This contract does **not** make the topology immutable. **Any** node addition, removal, replacement, address change, transport change, or identity change must be **explicitly approved by operator**, logged in the relevant transport / node registry spec, and validated through the verification chain in §3.3 before the change is allowed to enter production assignments.

### §3.1 Nodes and Transports

#### §3.1.1 Node roles in topology

`21bao` is the **unique control plane** of the current operator-approved canonical topology. It also serves as the local-exec / control node. Its default transport for orchestrator / control is `local-exec`.

5bao is a Debian SSH worker. Its canonical primary transport endpoint is registered in the node registry and named in §3.1.4.

9bao is a Debian SSH worker. Its canonical primary transport endpoint is registered in the node registry and named in §3.1.4.

3.1.2 A node carries exactly one of two availability states: `ACTIVE` or `SUSPENDED_OFFLINE`. `NOT_ASSIGNABLE` is **not** a third availability value; it is a mandatory consequence of `SUSPENDED_OFFLINE` (a SUSPENDED node is not assignable to any role).

3.1.3 A route entry inside a transport route chain carries route-level status (e.g. `qualified` / `unqualified` / `disabled`). It **must not** carry `SUSPENDED` or `NOT_ASSIGNABLE` as a state — those are node-level states.

#### §3.1.4 Canonical primary transports and route chains

Each node's canonical primary transport is registered in the node registry and forms the head of its route chain:

  - **21bao** — orchestrator / control / metadata reads use `local-exec`. Network-service domain chain (ordered): `21bao.kingjinjing.top` → `21bao.kingjinjing.vip`. The local-exec path and the network-service domain chain are **distinct** route chains; local-exec is not part of the domain chain.

  - **5bao** — `vibeworker@192.168.5.6:22222` → `5bao.kingjinjing.top` → `5bao.kingjinjing.vip`.

  - **9bao** — `vibeworker@192.168.9.6:2222` → `9bao.kingjinjing.top` → `9bao.kingjinjing.vip` → `9bao2.kingjinjing.top` → `9bao2.kingjinjing.vip`.

3.1.5 Cross-reference for failover semantics: §3.5.1 – §3.5.12 (governance); **not** §3.7 (which addresses domain endpoint semantics, not failover).

### §3.2 Node Activity and Control-Plane Readiness

3.2.1 The cluster recognises two **node availability** values and one **control-plane readiness** dimension:

  - **node availability** of any node is exactly one of: `ACTIVE` or `SUSPENDED_OFFLINE`. `NOT_ASSIGNABLE` is **not** an availability value; it is the **mandatory scheduling consequence** of `SUSPENDED_OFFLINE` — a SUSPENDED_OFFLINE node is, by definition, not assignable to any role. The two state spaces are independent dimensions, not parallel availability values.
  - **control-plane readiness** applies **only to the unique control-plane node** (`21bao`, per §3.6) and is exactly one of: `CONTROL_PLANE_READY` or `CONTROL_PLANE_UNAVAILABLE`. The other nodes do not carry a control-plane readiness label.

3.2.2 A node labelled `SUSPENDED_OFFLINE` **must not** be recommended, allocated, SSH-ed, model-called, or otherwise executed until operator explicitly approves recovery and re-qualification completes.

3.2.3 The heading of this section uses the correct spelling. Cross-references in this document use the same spelling.

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

3.4.2 **Precedence of §3.5 over §3.4**: for an `ACTIVE` node that has an operator-approved, registered, and qualified same-node route chain, a transport-path failure matching §3.5.5 **first** enters the §3.5 failover flow. The §3.4 STOP above does not fire on that transport-path failure alone. The §3.4 STOP fires only when the §3.5 path has terminated, namely:

  - the chain has been exhausted (§3.5.9);
  - the failure is a §3.5.6 disallowed trigger class;
  - a proposed or actual route switch violates §3.5.2 or §3.5.11 invariant.

3.4.3 Detailed failure handling is governed by §7. Strictly forbidden at the **assignment level**: automatic fallback, automatic node swap, automatic model swap, lowered independence, scope-shrinking continuation.

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

#### §3.5.4 Excluded routes and chain suspension

A route entry within an active chain is eligible for automatic failover only when all of the following hold:

  - the entry is `qualified` under §3.5.3;
  - the entry is `enabled` and operator-approved;
  - the entry is not `UNKNOWN`, not `unqualified`, not `disabled`, and not revoked.

A route entry is **not** a node, and **must not** carry `SUSPENDED` or `NOT_ASSIGNABLE` as a state — those are node-level states.

If the **owning node** of a route chain is `SUSPENDED_OFFLINE` (and therefore not assignable), the entire chain of that node is suspended: no route in that chain participates in failover. The cluster's failover machinery does not use route chains of SUSPENDED nodes to recover connectivity.

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
  - immediately report to operator with at minimum the **seven minimum information categories**: `node | previous route | active route | failure class | switched_at (UTC) | post-switch health / readiness | affected task / run evidence`. Specific field names and schemas are left to the runtime / evidence spec.

#### §3.5.8 Cascade rules

If the next route is still a transport-path failure, runtime may continue to the next qualified route. If the route is reachable but identity, credential, application readiness, model, gate, receipt, or evidence fails, runtime **must** immediately STOP and **must not** continue switching routes.

#### §3.5.9 Exhaustion = STOP

When all approved and qualified routes in the chain are exhausted, runtime **must** immediately STOP and report per §7.

#### §3.5.10 Chain change control

The chain is ordered and operator-approved. Any of the following changes requires explicit operator approval: route addition, route deletion, route order change, port / address change, DNS primary / secondary change, ISP primary / secondary change.

#### §3.5.11 Categorisation

Transport-route failover is **not** an assignment-level fallback. It does not change node, role, model, assignment, credential identity / scope, task scope, or operator-approved action range. It is a same-node transport-level re-route, and it is **distinct** from the assignment-level fallback prohibited by §7 and §10. Section §3.5.11 itself is **not** a failure class and **must not** be cited as a STOP trigger.

#### §3.5.12 Contract scope

Contract-level minimum report contents for any switch are the seven minimum information categories listed in §3.5.7. Schema, field names, file names (such as `routes.yaml`-style names), script names, receipt / ledger structures, and executor / wrapper internals are out of contract scope and live in the runtime / node-registry / evidence spec.

### §3.6 21bao as the Unique Control Plane

#### §3.6.1 Identity

Within the operator-approved canonical topology (`21bao / 5bao / 9bao`):

  - `21bao` is the **unique** control plane.
  - `vibedev` runs on `21bao`.
  - `21bao` is the operator interaction entry.
  - `21bao` is also the local-exec / control node (per §3.1.1).

#### §3.6.2 Design and operational target label

The design and operational target for `21bao` is the label `ALWAYS_ON_CONTROL_PLANE`. This is an expression of intent and an SLA target — **not** a physical or absolute guarantee.

#### §3.6.3 Verifiable formulation

The correctly-formulated, verifiable statement that operator accepts for `21bao` is:

> In the current operator-approved canonical topology, `5bao` and `9bao` are workers; they do **not** constitute a control-plane fallback for `21bao`. Any role or topology change requires explicit operator approval.

This contract does not assert that `21bao` is impossible to fail. It asserts that **when** `21bao` becomes unavailable — including `21bao` offline, `Hermes` gateway unavailable, `vibedev` unavailable, or `21bao`'s control-plane readiness failing — the system enters `CONTROL_PLANE_UNAVAILABLE / VIBECODING_UNAVAILABLE` and no worker node may take over the control-plane responsibilities.

#### §3.6.4 Unavailability semantics

When the state in §3.6.3 holds:

  - **No** new VibeCoding task may start.
  - **No** running task may be taken over by `5bao` or `9bao`.
  - **`5bao`** / **`9bao`** must **not** self-elect orchestrator.
  - Orchestrator **must not** auto-migrate.
  - A worker **must not** be elevated to control plane.
  - `21bao`'s transport-route failover (§3.5) **must not** be interpreted as control-plane migration, orchestrator migration, node substitution, or operator-entry migration — even when `5bao` / `9bao` are `ACTIVE`.
  - `21bao` local-exec failure, `Hermes` gateway failure, `vibedev` profile failure, or `21bao` control-plane readiness failure **must not** attempt worker takeover; the system goes directly to `CONTROL_PLANE_UNAVAILABLE / VIBECODING_UNAVAILABLE`.

#### §3.6.5 Worker-only status

`5bao` and `9bao`, even when `ACTIVE`, are workers in the current operator-approved canonical topology. They do **not** constitute a control-plane fallback for `21bao` in the current operator-approved topology.

#### §3.6.6 Transport-route failover ≠ control-plane failover

See §3.5.11 and §3.6.4: `21bao`'s same-node transport-route failover is **not** control-plane failover.

#### §3.6.7 Recovery gate (control-plane re-acceptance)

When `21bao` is restored from `CONTROL_PLANE_UNAVAILABLE`, VibeCoding dispatch **must not** be re-opened before **all** of the following checks pass:

  - local control-plane availability;
  - `Hermes` gateway status;
  - `vibedev` profile status;
  - Git working state;
  - GitHub credential binding presence;
  - worker credential binding;
  - Central Model Pool current status;
  - runtime / config integrity;
  - readiness and drift checks.

Only after **every** item above returns PASS may `21bao` be restored to `ACTIVE / CONTROL_PLANE_READY`. Re-opening dispatch before all checks pass is a §9.3 high-risk violation. The post-outage / recovery report captures the minimum semantics: outage / detection / recovery / re-dispatch times, validation outcomes, linked evidence, frozen or not-started tasks. The specific schema lives in the runtime / evidence spec.

**State dimension separation**: recovery of dispatch requires **both** `node availability = ACTIVE` **and** `control-plane readiness = CONTROL_PLANE_READY`. If `21bao`'s node availability was already `ACTIVE` throughout (only the control-plane readiness was `CONTROL_PLANE_UNAVAILABLE`), the recovery transitions only the readiness dimension — it does not change the availability dimension. The two state spaces remain independent per §3.2.1.

### §3.7 Domain Endpoint Semantics

3.7.1 `.top` and `.vip` are **complete** domain suffixes, **not** `top` / `vip` path segments. Same-name `.top` and `.vip` are hosted by **different** DNS providers with expected equal resolution values.

3.7.2 `.top` is primary, `.vip` is fallback.

3.7.3 `9bao` and `9bao2` are two distinct ISP links (primary ↔ secondary). Each link carries its own `.top` / `.vip` redundancy.

3.7.4 §3.1.4 explicitly registers canonical primary transports as governance facts. **Other** implementation-level endpoint parameters (additional ports, internal addresses, proxies, package manager paths, etc.) live in the controlled node registry / runtime spec; this contract does not fix them.

### §3.8 Hermes / OpenCode Version Decoupling and Compatibility Governance

#### §3.8.1 Decoupling principle

`Hermes` and `OpenCode` are maintainable software dependencies of the small cluster. They are **not** immutable infrastructure. Operator may explicitly approve upgrade, downgrade, replacement, or rollback of `Hermes` / `OpenCode` on a designated node or profile.

#### §3.8.2 Architecture-level independence

The cluster's architecture, 9-role pipeline, Central Model Pool, assignment rules, gates, receipts, wrapper, executor, synchronisation, audit, and evidence chain **must not** depend on a single fixed `Hermes` or `OpenCode` version.

#### §3.8.3 Forbidden hard-coding

Core governance and runtime **must not** hard-code, without adaptation:

  - a single version number;
  - CLI parameters that exist only in a specific version;
  - a fixed install path;
  - a fixed configuration format;
  - a fixed output text;
  - a fixed provider / model enumeration behaviour;
  - an authentication, session, plugin, or interface behaviour that applies only to a specific version.

When versions differ, the runtime / node-registry / evidence spec **must** use capability detection, version adapters, schema migration, or compatibility layers. Specific-version behaviour **must not** be treated as a global invariant.

#### §3.8.4 "Version-compatible" engineering definition

"Version-compatible" means:

  - operator chooses the target `Hermes` / `OpenCode` version;
  - the small cluster **must be able** to qualify execution compatibility for the target version;
  - a target version becomes `QUALIFIED_COMPATIBLE` **only after** qualification passes;
  - unverified, failed-qualification, unknown-future, or adapter-missing versions **must** be marked `UNQUALIFIED` / `INCOMPATIBLE` / `UNKNOWN` and **must not** be assumed compatible.

#### §3.8.5 Qualification coverage (at minimum)

  - binary discoverability and version identification;
  - CLI / API capability detection;
  - configuration read, generation, and schema migration;
  - provider namespace, model ID, alias, endpoint, and credential reference;
  - Central Model Pool synchronisation and node-local rendered configuration;
  - wrapper / executor invocation;
  - bounded model-call canary;
  - 9-role assignment and execution chain;
  - gates, receipts, traces, verdicts, and closeout artifacts;
  - Draft PR, Ready, merge checkpoint tooling behaviour;
  - secret non-leakage;
  - rollback feasibility;
  - drift checks.

#### §3.8.6 Audit-grade version inventory

An auditable version inventory and compatibility matrix **must** be maintained, recording at minimum:

`node/profile | component | installed version | detected capabilities | adapter version | qualification status | verified_at | evidence reference`

A bare version number without compatibility status and verification evidence is **not** acceptable.

#### §3.8.7 Mixed versions

Mixed versions across nodes are **not** forbidden in principle, but each component-version combination **must** be independently qualified, and the qualification **must** demonstrate that the compatibility layer yields consistent governance semantics, assignment behaviour, and evidence. Unverified mixed versions **must not** enter production tasks.

#### §3.8.8 Version-change decisions

Version changes are operator decisions:

  - orchestrator may audit and propose upgrades or downgrades;
  - orchestrator **must not** auto-upgrade, auto-downgrade, auto-lock, or auto-select a substitute version;
  - package manager auto-update, self-update, or any other auto mechanism **must not** bypass operator.

#### §3.8.9 High-risk classification

Real upgrade, downgrade, installation, configuration migration, service restart, and production switch are **high-risk actions** under §9.3:

  - first confirmation authorises **only** preparation: version inventory, impact analysis, backup, migration plan, qualification plan, rollback plan;
  - before execution, re-present to operator: target version, target node / profile, exact action, current state, rollback point;
  - execution proceeds only after the second explicit operator confirmation.

#### §3.8.10 Phased qualification

Version changes use phased qualification:

  - record the current version and configuration snapshot;
  - perform the change in the operator-specified scope;
  - run compatibility qualification;
  - after qualification passes, wait for operator decision on scope expansion;
  - **must not** auto-upgrade other nodes merely because a single-node canary passed.

#### §3.8.11 Qualification failure = STOP

If installation fails, capability is missing, configuration is incompatible, model call fails, receipt / gate behaviour changes, or any other qualification step fails, runtime **must** immediately STOP, preserve evidence, and report: affected node / profile, original version, target version, failed item, current state. Auto-rollback, auto-replacement with another version, or auto-expansion of deployment is **forbidden**. Rollback is allowed only through a pre-approved atomic rollback mechanism or a new explicit operator decision.

#### §3.8.12 Immutability of governance semantics

Version compatibility layers **must not** alter the following governance semantics:

  - operator as sole and final decision maker;
  - orchestrator recommends only;
  - runtime executes exactly the operator-approved assignment;
  - no assignment-level fallback;
  - complete 9-role;
  - Draft PR → operator-authorised Ready → independently authorised merge;
  - Failure STOP;
  - Central Model Pool unified management;
  - secret non-leakage into Git, PR, log, receipt, or chat.

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

### §6.5 Secret Handling and Credential Discovery Boundary

  - Secrets may live in an operator-controlled local-only / gitignored overlay.
  - Secrets **must not** appear in Git, commits, PRs, reports, receipts, logs, or chat.
  - Syncing secrets to workers requires controlled channel, minimum privilege, restrictive file permissions.
  - **Credential discovery** (any code, prompt, or report that lists environment variables) **must not** serialise or print a value-bearing environment map. Only the variable **name** and a categorical **presence** state (`PRESENT_NONEMPTY` / `PRESENT_EMPTY` / `ABSENT`) are permitted outputs.
  - **Any** secret-derived fragment (value, prefix, length, hash, or encoding) entering chat, log, or report triggers immediate STOP and an **exposure assessment**. The exposure assessment is **read-only**: it does not rotate, replace, or invalidate the credential automatically.
  - Public-format prefix markers (e.g. token family identifiers that are widely documented for a service) **must not** be treated as the credential value itself; they are still token-derived fragments and the same boundary applies.
  - Until operator explicitly authorises rotation, affected variables are flagged `POTENTIALLY_EXPOSED` and recorded in the controlled exposure inventory.

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

### §7.2 Precedence of §3.5 over §7

For an `ACTIVE` node with an operator-approved, registered, qualified same-node route chain (§3.5), a transport-path failure matching §3.5.5 **first** enters the §3.5 failover flow and **does not** immediately trigger the §7.1 STOP above. The §7.1 STOP fires when the §3.5 path has terminated, namely:

  - the chain has been exhausted (§3.5.9);
  - the failure is a §3.5.6 disallowed trigger class;
  - a proposed or actual route switch violates §3.5.2 or §3.5.11 invariant;
  - the node has no approved same-node route chain.

Local-exec and control-plane failures go directly to §3.6.4 / §3.6.7.

### §7.3 Immediate Actions

- Immediately stop all new role / step / SSH / model call / Git write / file write.
- Preserve current durable evidence, receipts, traces, logs, state snapshot.
- **Must not** unilaterally clean up, compensate, recover, retry, or roll back.
- If the operator-approved action **explicitly** contained a pre-approved atomic-failure-rollback mechanism, that mechanism **alone** may execute to avoid data corruption, with full logging.
- Other rollback / recovery / compensation actions require a new explicit operator decision.
- Secrets **must not** appear in reports or logs.

### §7.4 Report Content (at minimum)

- failing role;
- designated node;
- designated model;
- failed stage (which of F1–F10);
- error summary — quoting error codes / key log lines; **not** printing secrets / tokens / keys;
- actions completed;
- actions not completed;
- current Git / task / receipt state (HEAD SHA, current PR if any, list of produced receipts);
- items requiring operator decision — statement of fact + options + their respective risks; orchestrator **does not** choose.

### §7.5 Strictly Forbidden (assignment-level only)

The list below is the **assignment-level fallback** list. Each item is forbidden at the **assignment** layer, not at the transport layer. §3.5 same-node transport-route failover, which advances within an operator-approved, registered, qualified chain, is **not** an assignment-level fallback and is therefore **not** forbidden by this list. Conversely, no item in this list may be achieved by §3.5 transport failover or by chaining a §3.5 cascade to invoke the same effect.

- assignment-level automatic fallback;
- assignment-level automatic node / model swap;
- default substitute (assignment-level);
- automatic assignment rewrite;
- lowered tester / reviewer independence;
- scope-shrinking continuation;
- continuing other unaffected roles into partial completion;
- orchestrator unilaterally retrying or choosing an alternative path;
- resuming route failover (§3.5) after this STOP has fired.

Once §7 has fired (the **Failure STOP**), the §3.5 route-switching state is **not** resumed; recovery requires a new explicit operator decision.

### §7.6 Retry and Confirmation

- Failure follow-on actions — continue / retry / recover / roll back — **must** await a new explicit operator decision.
- **No automatic retry**; bounded-authorisation packages **must not** pre-include automatic retry.
- Whether retry / repair triggers the §9.3 double-confirmation depends on the **actual nature of the action itself** plus operator's new decision.
  - Retry / repair actions that themselves fall within §9.3, or that operator explicitly marks as high-risk in the new decision, must follow §9.3.
  - Ordinary, read-only, or scope-bounded retries may be authorised directly in operator's new explicit decision.

### §7.7 Continuation Conditions

Continuation is permitted only after operator's new explicit decision. Operator may decide any of:

- one explicitly limited retry under the original assignment;
- retry after modifying node / model assignment;
- resume from an operator-specified checkpoint;
- restart the whole task;
- execute rollback or recovery;
- terminate the task.

Orchestrator submits fact, risk, and options only — **does not** choose. Runtime strictly executes operator's latest decision. Any continuation generates a new authorisation record with linkage to the original failure evidence.

### §7.8 Relation to Other Clauses

- §7 does not replace §3.4 (top-level STOP trigger).
- §7 does not replace §10.1 (five-step drift handling).
- §7 does not replace §9.3 (high-risk double-confirmation).
- §7 does **not** introduce retry tokens or preset automatic-retry mechanisms.
- §7 is **not** the same as §3.5 transport-route failover; transport-route failover (§3.5) is a same-node transport-level re-route with its own trigger set (§3.5.5) and its own forbidden actions (§3.5.6), and stops per §7 only when the §3.5 path has terminated — namely the **exhaustive** STOP conditions shared across §3.4.2, §7.2, and §13:

  - the chain has been exhausted (§3.5.9);
  - the failure is a §3.5.6 disallowed trigger class;
  - the next route is reachable but identity, credential, application readiness, model, gate, receipt, or evidence fails (§3.5.8 post-condition);
  - a proposed or actual route switch violates §3.5.2 or §3.5.11 invariant.

§3.5.11 itself is **not** a failure class and **must not** be cited as a STOP trigger.

---

## §8. Canonical Pipeline and Evidence

### §8.1 Real F1–F10 Evaluation

`intake → classify → plan/recommend → operator approval → role-node-model assignment → readiness → public-PR permission → execute → evidence/report → closeout`. Listing the 9-role in an assignment **does not** equal real execution completion. Non-applicable gates **must** emit a `NOT_APPLICABLE` verdict / artifact; they **must not** be skipped.

### §8.2 Non-Canonical Paths

- Formal VibeCoding E2E **must** traverse the canonical pipeline.
- Operator **may** explicitly authorise wrapper, manual SCP / SSH, ad-hoc model calls for diagnosis, recovery, evidence collection, or local verification. Such executions must record operator authorisation and carry `execution_path: non_canonical`.
- Their results may carry only the labels `diagnostic`, `local_verification`, or `historical_evidence`; **must not** claim canonical E2E PASS.
- Unauthorised use is **forbidden**.
- Non-canonical paths **must not** become assignment-level automatic fallback.

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

Historical evidence (including T3 / R3 / RW-1 reports, PR #341–#343 canary evidence, `readiness-receipt-20260705-150000`, untracked `docs/baseline02/gray/*`, the corresponding PR bodies, and the corresponding receipts) **remains untouched** and carries the banner:

> `PRE_V2_HISTORICAL_EVIDENCE — not V2-compliant E2E evidence`

Such evidence:

- is usable to demonstrate **local components** or **historical run capability**;
- **does not** satisfy V2's full 9-role, canonical pipeline, dual-tester, dual-reviewer, and **no-assignment-level-fallback** requirements;
- **must not** be reinterpreted as V2-compliant E2E PASS;
- any current verdict referencing them must carry the banner above.

References to "no-fallback" in this document mean **no assignment-level fallback** (§3.5.11, §7.5). The §3.5 same-node transport-route failover remains a permitted transport behaviour, not an assignment-level fallback.

### §8.9 Cluster Construction Operation (`CLUSTER_CONSTRUCTION_OPERATION`)

While the full canonical 9-role runtime has not been accepted and declared in force by operator, any actions performed to **build, audit, or remediate** that runtime are uniformly labelled `CLUSTER_CONSTRUCTION_OPERATION`:

- such actions **must not** be claimed as V2-compliant VibeCoding tasks, complete 9-role executions, or canonical E2E PASS;
- such actions **remain subject to** operator decision authority, explicit authorisation, **no-assignment-level-fallback**, Failure STOP (§7), evidence levels (§8.5), historical / current distinction (§8.6, §8.8), and high-risk double-confirmation (§9.3);
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
- out-of-scope production changes;
- `Hermes` / `OpenCode` install, update, downgrade, configuration migration, restart, or version switch (per §3.8).

Retry / repair actions trigger §9.3 **only** when they themselves fall within the list above, or when operator explicitly marks them as high-risk in the new decision. Ordinary, read-only, or scope-bounded retries — after a failure STOP — still **must** await a new explicit operator decision; they do not become high-risk merely by virtue of being labelled "retry".

### §9.4 D. Bounded Authorisation Package

Operator may grant a one-shot bounded authorisation package containing: task ID, approved assignment, node + model and call limits, SSH command classes, read / write paths, Git scope, forbidden actions, valid boundaries, acceptance criteria. Routine calls **within** the package need no further confirmation; **out-of-scope**, **node / model swap**, or **§9.3-trigger** actions → STOP and re-request authorisation.

**§9.4 cannot override** §9.1 A, §9.2 B, §9.3 C, §1 GP-1 / GP-2 / GP-3. **§9.4 cannot pre-include automatic retry** (§7.6).

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
  - (h) assignment-level automatic fallback / automatic node / model swap;
  - (i) using a default substitute (including auto-picking a default model / node for an unspecified role);
  - (j) automatic assignment rewrite (orchestrator modifying operator's specification);
  - (k) scope-shrinking continuation (partial-execute forming pass-by-omission);
  - (l) continuing other unaffected roles into partial completion;
  - (m) orchestrator unilaterally choosing an alternative path;
  - (n) presence of an `alternative` field in the recommendation matrix;
  - (o) historical evidence reinterpreted as V2-compliant E2E PASS;
  - (p) `PRE_V2_HISTORICAL_EVIDENCE` cited without the banner `PRE_V2_HISTORICAL_EVIDENCE — not V2-compliant E2E evidence` per §8.8;
  - (q) runtime modifying operator-approved assignment or bypassing §1 GP-2;
  - (r) runtime auto-swapping the orchestrator model (§4.1);
  - (s) continuing on orchestrator-model unavailability without STOP;
  - (t) bounded authorisation packages pre-including automatic retry (§7.6, §9.4);
  - (u) test or fixture evidence cited as V2 E2E PASS (§8.3, §4.2);
  - (v) merely running a generic command counted as a role execution (§4.2, §4.4);
  - (w) `CLUSTER_CONSTRUCTION_OPERATION` used to bypass post-acceptance 9-role / gates / evidence / checkpoints (§8.9);
  - (x) binding the cluster to a single fixed `Hermes` / `OpenCode` version without qualification (§3.8);
  - (y) claiming compatibility without verification / reusing stale qualification evidence / auto-expanding scope after single-node canary (§3.8);
  - (z) automatic `Hermes` / `OpenCode` upgrade / downgrade / version lock / substitute selection, or any update mechanism bypassing operator (§3.8.8);
  - (aa) continuing assignments after a node-version change without re-qualification, or different node versions producing governance-semantic divergence while claiming E2E PASS (§3.8.7);
  - (bb) using `Hermes` / `OpenCode` version switching to evade Failure STOP or operator checkpoints (§3.8.12);
  - (cc) hardcoding a single version / CLI / path / schema in core governance or runtime without adaptation (§3.8.3);
  - (dd) using a non-registered or unqualified route in §3.5 transport-route failover;
  - (ee) mis-classifying an auth / identity / application error as transport-path failure (§3.5.6) and switching routes anyway;
  - (ff) §3.5 route switch that changes node / model / role / assignment / credential / scope (§3.5.11);
  - (gg) §3.5 switch into another node's route;
  - (hh) restoring a `SUSPENDED` / `OFFLINE` / `NOT_ASSIGNABLE` / unqualified node to `ACTIVE` via route failover or any other automatic channel;
  - (ii) continuing to try routes after the chain is exhausted (§3.5.9);
  - (jj) modifying the route chain without operator approval (§3.5.10);
  - (kk) interpreting §3.5 transport-route failover as a license for assignment-level fallback;
  - (ll) `5bao` / `9bao` taking over `21bao` control plane;
  - (mm) automatic orchestrator migration;
  - (nn) continuing VibeCoding tasks while `21bao` is unavailable;
  - (oo) mis-interpreting `21bao`'s network route failover as control-plane failover;
  - (pp) re-opening `21bao` VibeCoding dispatch before every item in §3.6.7 passes (§3.6.7);
  - (qq) credential discovery that prints a value-bearing environment map, or outputs secret-derived fragments into chat / log / report (§6.5);
  - (rr) treating a public-format token prefix marker as the credential value (§6.5);
  - (ss) auto-rotating, auto-replacing, or auto-invalidating a credential without explicit operator authorisation (§6.5).

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

- V2 enters force **only** when the operator explicitly accepts it in chat (e.g. "ACCEPT V2" or equivalent natural language). vibedev **must not** self-declare V2 as accepted, effective, or adopted.
- The accepted body is applied to the existing contract file through an **operator-authorised PR update**. The current Draft PR (#365, or its successor) may serve as the landing PR **if and only if** its head content is **identical** to the operator-accepted text.
- The landing PR proceeds through **two independent authorisations**: `Draft → Ready` (operator authorises) and `merge` (operator authorises separately). Neither step is automatic.
- If the operator-accepted text differs semantically from the current Draft head, a new review cycle and renewed operator acceptance are required before landing.
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

This clause governs every complete **transfer prompt** that ChatGPT / assistant + orchestrator consultant generates and hands to operator for verbatim forwarding to `vibedev`, `小马蹄 Hermes`, or any other operator-designated agent.

Out of scope (handled by a separate runtime prompt spec, not by this clause):

- operator ↔ ChatGPT ordinary discussion;
- operator's own ad-hoc messages;
- agent reports;
- `vibedev`'s internal 9-role runtime prompts;
- agent-to-agent communication.

### §11.2 Goal

Each transfer prompt must clearly convey: facts, objective, identity boundaries, allowed / forbidden actions, authorisation, method, stopping conditions, evidence requirements, acceptance criteria, and output format.

### §11.3 One-Copy Format and Writing-Block Prohibition

  1. Each complete transfer prompt that operator forwards **must** be placed in a **plain Markdown fenced code block** with the language tag fixed to `text`. Example: ` ```text `.
  2. **Forbidden** writing-block formats include: rich writing blocks, special writing cards, editable blocks, accordion blocks, tabbed blocks, callout blocks, and any other non-ordinary code-block component that mobile clients cannot one-tap copy.
  3. The code fence contains **only** the forwardable prompt body. Consultant's analysis, evaluation, risk notes, and suggestions stay **outside** the fence.
  4. A single code fence carries exactly one logically complete prompt, unless explicitly part of a single multi-segment prompt.
  5. Each transfer prompt is **self-contained**, **mobile-friendly**, and **one-tap copyable**. Related items are batched; micro-prompts and micro-PRs are forbidden.

### §11.4 Length and Segmentation

  1. A single transfer prompt is a **soft target** of approximately 3000 Chinese characters. This is **not** a hard ceiling; it is also **not** a license to ignore the limit and emit an unboundedly long prompt.
  2. **Clarity and completeness always come first.** A single segment is preferred when it can carry the full prompt clearly. Length is reduced only by improving clarity, not by sacrificing it.
  3. If segmentation is required, each segment goes into its **own** `text` code fence and is labelled `第 X/N 段`.
  4. Every non-final segment **must** explicitly require the receiver to reply `ACK` only and **not** start execution.
  5. The **final** segment **must** end **exactly** with:

   ```
   全部发送完毕，收到后立即开始执行。
   ```

   No "or equivalent" is permitted. The clause is closed at that line.
  6. After the final segment, all preceding segments must have arrived; agents **must not** begin work before every segment is present.

### §11.5 Version Management

  1. **Full replacement** of a previous prompt: the code fence must explicitly contain the line

   ```
   上一版提示词作废，以本版为准。
   ```

  2. **Incremental revision**: the code fence **must** explicitly contain the marker

   ```
   增量补充
   ```

   and **must** list:

   - the scope of the new clause(s);
   - the previous clause(s) that **remain in force**;
   - the resolution authority when new and old clauses conflict.

  3. The receiver **must not** be asked to infer how to merge two conflicting prompts.

### §11.6 Blind-Review Additional Rules (for `小马蹄 Hermes`)

  - whether the review is independent and blind;
  - forbidden reads — which `vibedev` reports, sessions, memory, scratchpads, intermediate conclusions;
  - allowed reads — which repos, PRs, configs, and `PRE_V2_HISTORICAL_EVIDENCE` may be referenced;
  - blind-review isolation boundaries;
  - evidence citation format;
  - prohibition on contamination by other agents' conclusions.

### §11.7 `vibedev` Job Prompt Additional Rules

Phase name; current baseline / HEAD; allowed / forbidden actions; whether SSH / real model calls / Git writes / Draft PR / Ready / merge / config writes / `--apply` are permitted; operator checkpoint; stopping conditions; acceptance criteria; report-only vs allowing in-repo artefacts; whether to mark `CLUSTER_CONSTRUCTION_OPERATION` or full-9-role runtime.

### §11.8 Long-Context De-Drift

All complete transfer prompts generated by ChatGPT / assistant + orchestrator consultant and handed to operator for verbatim forwarding to `vibedev`, `小马蹄 Hermes`, or any other operator-designated agent must, as task requires, re-anchor: operator as final decision maker; `21bao` / `5bao` / `9bao` as nodes; `vibedev` / `小马蹄 Hermes` as profiles; full 9-role requirement for the current task; current authorisation boundaries; current in-force or pending contract version; historical / current evidence boundary.

### §11.9 Forbidden Expansion

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
| 3000-character rule | "each segment < 3000 characters" (hard) | soft guidance: clarity and completeness first (§11.4) |
| 9-role roster | five mixed roles | fully enumerated 9-role (§4.1) |
| Role trimming | not explicitly forbidden | explicit no-trim / no-skip / no "named-but-not-executed" (§4.2) |
| Dual tester / dual reviewer | absent | independent across assignment / context / prompt / batch / output / evidence; **recommended** different node + model (§4.5) |
| 8-role assignment pre-brief | absent | required; 4-column matrix; no `alternative` (§5.5) |
| Assignment strictness | absent | strict per operator spec; failure follows §7 (§5.8, §5.9) |
| Failure STOP | implicit | explicit triggers, preserved evidence, enumerated prohibitions, retry rules; §3.5 transport-path failures go through §3.5 first (§7.2); STOP fires on chain exhaustion (§3.5.9), §3.5.6 disallowed trigger, §3.5.8 post-condition failure, or §3.5.2 / §3.5.11 invariant violation (§3.4.2, §7.2, §7.8, §13 all share the same exhaustive set); §3.5.11 itself is not a failure class |
| Central Model Pool | 7-state concept only | single write flow, sync direction, sync-after verification, secret isolation, node calling boundary, credential discovery boundary (§6.5–§6.8) |
| Canonical pipeline | F1–F10 not detailed | F1–F10 real evaluation; non-canonical path requires operator authorisation and `execution_path: non_canonical`; non-canonical must not become assignment-level automatic fallback (§8.1, §8.2) |
| Evidence levels | absent | 7 levels; anti-extrapolation rules; double-hash rule for untracked (§8.5, §8.6) |
| `PRE_V2_HISTORICAL_EVIDENCE` | absent | hard rules against reinterpretation; full banner enforced (§8.8) and re-asserted in §10.1(p) |
| Prompt Delivery Contract | informal §7 guidance | full contract: text code fences, writing-block prohibition, soft 3000-character target, exact closing line, full-replacement and incremental-revision markers, mobile one-tap copy (§11) |
| Drift signals | 7 | expanded to (a)–(ss) |
| High-risk checkpoints | §4 vague | §9 explicit 4 categories (A/B/C/D), 12+ high-risk items, including `Hermes` / `OpenCode` install / update / downgrade / migration / restart / switch (§9.3) |
| Top-line governance | role authority scattered | §1 GP-1 / GP-2 / GP-3 single page; recommend → assign → execute locked |
| Effect mechanism | §10 "signing" (later corrected to Working Agreement) | effective only on operator explicit chat acceptance; on acceptance update existing file with `Version: 2.0` + `Supersedes: V1 / PR #276` + `Historical source retained in Git history` |
| Transport-route failover | absent | §3.5 same-node transport-route failover with operator-approved chain, standing authorization, per-switch no-permission-needed; wrong / unqualified / non-SAME-NODE routes forbidden; chain change needs operator approval; §3.5 STOP triggers (§3.5.6 / §3.5.8 / §3.5.9) take precedence over §7; §3.5.11 itself is not a failure class |
| `21bao` as control plane | not labelled | §3.6 `ALWAYS_ON_CONTROL_PLANE` is design + SLA target; on unavailability enter `CONTROL_PLANE_UNAVAILABLE / VIBECODING_UNAVAILABLE`; no worker take-over, no orchestrator self-election, no auto-migration, no transport-route-failover → control-plane interpretation; §3.6.7 recovery gate |
| `Hermes` / `OpenCode` version handling | absent | §3.8 decoupling, qualification, mixed-version rules, operator-driven changes only, no auto-upgrade, qualification failure = STOP |
| Historical PR / report handling | unspecified | `PRE_V2_HISTORICAL_EVIDENCE` rules; historical files untouched |

---

*End of V2 candidate. Awaiting operator explicit acceptance in chat per §0.1.*
