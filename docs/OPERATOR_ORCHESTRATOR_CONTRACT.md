# Operator-Orchestrator Contract

| Field | Value |
|---|---|
| `Version` | `2.0` |
| `Status` | `DRAFT — awaiting operator acceptance` |
| `Supersedes` | `V1 / PR #276 upon explicit operator acceptance` |
| `Historical source retained in Git history` | `V1 (PR #276) preserved; not rewritten` |

---

## §0. Effective Status

### §0.1 V2 Baseline / Mainline Positioning

V2 is the operator-owned, operator-reviewed, and operator-accepted governance baseline for the VibeCoding micro-cluster, and the mainline for continuing to build the cluster. V2 simultaneously governs:

  - **Construction-phase** collaboration boundaries (operator ↔ ChatGPT as construction-phase consultant);
  - **Operational-phase** governance boundaries (operator ↔ `vibedev` as VibeCoding operational orchestrator ↔ runtime / roles / workers).

ChatGPT assists operator in maintaining the construction mainline **only** during `CLUSTER_CONSTRUCTION_PHASE`. After `OPERATIONAL_PHASE` begins, ChatGPT does **not** become a runtime participant by virtue of V2.

  - All planning, ChatGPT transfer prompts, agent reviews, runtime / node-registry / model-pool / evidence specs, and subsequent PRs **must** trace to and comply with V2.
  - Agent memory, historical implementation, self-check PASS, or efficiency reasons **must not** override V2.
  - Operator's subsequent explicit instructions have final authority. If they form a semantic change to V2, the change must enter the V2 amendment, review, and operator re-acceptance process (§10).
  - V2 is currently **DRAFT** and **must not** be claimed as accepted or in force.

### §0.2 Operator acceptance requirement

This V2 document enters into force **only after** operator (KK) explicitly accepts it in chat.

0.3 V1 (PR #276) is a merged historical contract and the previous operator-approved meta-collaboration baseline. Until V2 is accepted, V1 remains the historical reference; operator's updated instructions in the current conversation take precedence over any V1 clause with which they conflict. After operator's explicit acceptance of V2, V2 supersedes V1; V1 remains in PR #276 and in Git history.

0.4 `vibedev` **must not** self-declare V2 as signed, in force, or adopted in any PR, report, receipt, or chat.

0.5 V1 → V2 differences are summarised in §13. **No** separate `CHANGELOG_V1_to_V2.md` is created; the new Draft PR body lists the principal deltas.

0.6 Once V2 is in force, any further amendment (semantic or editorial) requires explicit operator approval per §10.

0.7 Historical evidence (including T3 / R3 / RW-1 reports, PR #341–#343 canary evidence, `readiness-receipt-20260705-150000`, untracked `docs/baseline02/gray/*`, the corresponding PR bodies, the corresponding receipts) remains untouched. Future references must carry the `PRE_V2_HISTORICAL_EVIDENCE — not V2-compliant E2E evidence` banner per §8.

---

## §1. Governance Principles

**GP-1 (operator sole decision authority)** — Operator is the sole and final decision maker and the sole authoriser. Efficiency, automatic recovery, fault tolerance, task continuity, agent suggestions, model defaults, node defaults **must not** override operator decision authority.

**GP-2 (recommend → assign → execute)** — The execution chain is fixed at:

  - **Construction phase**: ChatGPT (construction-phase consultant) recommends construction actions / prompts; operator decides and authorises; designated agent executes exactly the forwarded authorisation.
  - **Operational phase**: `vibedev` (VibeCoding operational orchestrator) recommends; operator assigns and decides; runtime executes exactly the operator-approved assignment.

Neither chain may interpret recommendation as approval.

**GP-3 (recommend ≠ approve)** — Recommendations are **only** suggestions. **Only** operator's explicit chat statement constitutes approval.

  - **Construction phase**: ChatGPT (construction-phase consultant) recommendations — including construction plans, transfer-prompt content, agent-output review findings — are advisory. Operator decides and authorises.
  - **Operational phase**: `vibedev` (VibeCoding operational orchestrator) recommendations — including the available-model list, the 4-column recommendation matrix, post-failure proposals, efficiency improvements — are advisory. Operator assigns and decides.

GP-1 / GP-2 / GP-3 interlock with §3, §4.1, §5.7, §7, §9, §10.1. **§9.4 bounded-authorisation packages cannot override these three principles.**

---

## §2. Identity, Decision Authority, Role Positioning — Two Phases

### §2.1 CLUSTER_CONSTRUCTION_PHASE

Current phase. Operator leads construction of the VibeCoding micro-cluster.

- **ChatGPT / assistant + construction-phase orchestrator consultant (AI)** — advisor. Duties: construction planning, Contract V2 maintenance proposals, transfer-prompt generation, agent-output review, construction mainline drift prevention. **Has no operator authority. Is not the future VibeCoding runtime orchestrator. Must not approve, execute, or take over.**
- Construction chain: operator ↔ ChatGPT (discuss construction) → ChatGPT generates advisory transfer prompt → operator reviews and forwards → `vibedev` / designated agent executes construction task → operator receives report, ChatGPT assists review.
- `vibedev` (Hermes profile on 21bao) — executes construction, audit, and remediation tasks as designated by operator. Not yet the VibeCoding operational orchestrator.

### §2.2 OPERATIONAL_PHASE

Enters into force **only after** operator explicitly declares construction complete and performs operational cutover.

- **`vibedev` (Hermes profile on 21bao)** — the **sole VibeCoding operational orchestrator**.
- Operational chain: operator ↔ `vibedev` orchestrator ↔ runtime / roles / workers.
- **ChatGPT exits the default operational control chain.** Does not participate in VIBECODING_MODE entry, sub-mode recommendation, role / node / model assignment, readiness, STOP recovery, version / CMP gates, PR / Ready / merge, or daily operations.
- Workers, reviewers, or ChatGPT **must not** take over `vibedev`'s orchestrator identity.

### §2.3 V2 Compliance

  - V2 does **not** directly replace, edit, or merge `vibedev`'s own `SOUL.md`, `MEMORY.md`, or runtime rules. Those files belong to an independent downstream configuration layer.
  - However, when `vibedev` acts as the VibeCoding orchestrator, its behaviour and the downstream rules it operates under **must comply** with V2.
  - Any conflict between V2 and `vibedev`'s own rules triggers immediate STOP and operator report.
  - `vibedev`'s own memory / runtime rules **must not** override operator authority, the operator-selected execution mode (when `FULL_9_ROLE_VIBECODING` is selected, must not override the complete 9-role requirement), operator-only assignment, Failure STOP, secret handling, PR checkpoints, or any other V2 governance boundary.

### §2.4 `小马蹄 Hermes`

`小马蹄 Hermes` (independent reviewer profile on 21bao) — same host as `vibedev`, isolated profile; usable as an external blind reviewer. **Not** part of `vibedev` and **not** a node. Unless operator explicitly designates in chat that for the current task it acts as runtime `reviewer-a` and/or `reviewer-b`, it is **not** equal to runtime `reviewer-a` or `reviewer-b`.

### §2.5 Profile/node/operator conflation

Treating profiles as nodes, or treating operator approvals as orchestrator "completed approvals" → drift; see §10.

### §2.6 Construction / Operational Cutover

  - Operator acceptance of V2 does **not** equal cluster construction complete and does **not** automatically enter `OPERATIONAL_PHASE`.
  - After V2 acceptance, the cluster remains in `CLUSTER_CONSTRUCTION_PHASE` and continues building per V2.
  - Only operator's future explicit declaration of `construction complete` / `operational cutover` — meeting operator's own requirements — transitions the cluster to `OPERATIONAL_PHASE`.
  - Before cutover, all agent operations continue to be labelled `CLUSTER_CONSTRUCTION_OPERATION` and **must not** impersonate formal `VIBECODING_MODE` E2E.
  - After cutover, ChatGPT exits the default operational control chain by default. Any future operator consultation with ChatGPT is external consultation and does **not** confer cluster control or operational authority.

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

  - **9bao** — `vibeworker@192.168.9.6:22222` → `9bao.kingjinjing.top` → `9bao.kingjinjing.vip` → `9bao2.kingjinjing.top` → `9bao2.kingjinjing.vip`.

3.1.5 The above ports and route order are current operator-approved governance facts. After V2 enters force, any change to canonical transport endpoint, port, route order, DNS, or ISP primary/secondary designation **must** go through a new Draft PR. The PR requires operator review, explicit approval, and separate Draft→Ready and merge authorisations before becoming a new governance fact. The runtime registry **must not** override contract-registered canonical transports.

3.1.6 Cross-reference for failover semantics: §3.5.1 – §3.5.12 (governance); **not** §3.7 (which addresses domain endpoint semantics, not failover).

### §3.2 Node Activity and Control-Plane Readiness

3.2.1 The cluster recognises two **node availability** values and one **control-plane readiness** dimension:

  - **node availability** of any node is exactly one of: `ACTIVE` or `SUSPENDED_OFFLINE`. `NOT_ASSIGNABLE` is **not** an availability value; it is the **mandatory scheduling consequence** of `SUSPENDED_OFFLINE` — a SUSPENDED_OFFLINE node is, by definition, not assignable to any role. The two state spaces are independent dimensions, not parallel availability values.
  - **control-plane readiness** applies **only to the unique control-plane node** (`21bao`, per §3.6) and is exactly one of: `CONTROL_PLANE_READY` or `CONTROL_PLANE_UNAVAILABLE`. The other nodes do not carry a control-plane readiness label.

3.2.2 A node labelled `SUSPENDED_OFFLINE` **must not** be recommended, allocated, SSH-ed, model-called, or otherwise executed until operator explicitly approves recovery and re-qualification completes.

### §3.3 Node Lifecycle Verification

3.3.1 The following **must not** enter production assignments before completing all verification steps:

  - a **new** node;
  - an existing node after address / transport / identity change;
  - an existing node being restored from `SUSPENDED_OFFLINE`.

The verification covers at minimum:

  - connectivity;
  - credential binding;
  - fresh health;
  - readiness;
  - wrapper validity;
  - Central Model Pool sync (including `allowed_nodes` and node-specific `runtime_provider` mapping);
  - model capability and applicable bounded model-call verification;
  - evidence / receipt pipeline qualification;
  - operator explicit approval for recovery.

Until **every** item above returns PASS, the node remains `SUSPENDED_OFFLINE` (and therefore `NOT_ASSIGNABLE`). A node **must not** be restored from `SUSPENDED_OFFLINE` through §3.5 transport-route failover — that mechanism is for same-node transport re-routing, not node-recovery authorisation. Specific commands, schemas, and receipt fields are left to the runtime / node-registry / evidence spec.

### §3.4 Unavailability Behaviour

3.4.1 Any of the following immediately triggers STOP for that node:

  - designated node unavailable;
  - node health = `UNKNOWN`;
  - connection failure;
  - readiness gate fail.

3.4.2 **Precedence of §3.5 over §3.4**: for an `ACTIVE` node that has an operator-approved, registered, and qualified same-node route chain, a transport-path failure matching §3.5.5 **first** enters the §3.5 failover flow. The §3.4 STOP above does not fire on that transport-path failure alone. The §3.4 STOP fires only when the §3.5 path has terminated, namely:

  - the failure is a §3.5.6 disallowed trigger class;
  - the next route is reachable but identity, credential, application readiness, model, gate, receipt, or evidence fails (§3.5.8 post-condition);
  - the chain has been exhausted (§3.5.9);
  - a proposed or actual route switch violates §3.5.2 same-chain constraints or changes an invariant listed in §3.5.11;
  - the node has no approved, registered, and qualified same-node route chain.

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

3.5.7 Per-switch post-conditions and report

Per switch, runtime **must**:

  - re-verify transport reachability;
  - re-verify node / service identity;
  - re-verify credential binding;
  - re-verify applicable health / readiness;
  - record transition evidence in the controlled evidence ledger.

**Successful same-node approved+registered+qualified route fallback**: after all post-switch verifications PASS, the runtime continues the original assignment. The successful fallback does **not** interrupt the current task. The runtime records transition evidence at switch time, but does **not** require operator attention mid-task for a successful fallback.

**After the current task completes and before closeout**, the orchestrator **must** submit a standalone **Transport Fallback Report** to the operator, containing at minimum: `task / run | node | all previous→active route switches | failure class | switched_at (UTC) | post-switch verification results | impact on task | final result | evidence references`. Multiple successful fallbacks within the same task may be consolidated into a single report.

**Immediate STOP** (no auto-retry) applies to: auth / identity / credential binding / application readiness / Hermes / OpenCode / model / gate / receipt / evidence / scope errors, or route chain exhaustion (§3.5.9). These follow §7 Failure STOP.

Specific field names and schemas are left to the runtime / evidence spec.

#### §3.5.8 Cascade rules

If the next route is still a transport-path failure, runtime may continue to the next qualified route. If the route is reachable but identity, credential, application readiness, model, gate, receipt, or evidence fails, runtime **must** immediately STOP and **must not** continue switching routes.

#### §3.5.9 Exhaustion = STOP

When all approved and qualified routes in the chain are exhausted, runtime **must** immediately STOP and report per §7.

#### §3.5.10 Chain change control

The chain is ordered and operator-approved. Any of the following changes requires explicit operator approval: route addition, route deletion, route order change, port / address change, DNS primary / secondary change, ISP primary / secondary change.

#### §3.5.11 Categorisation

Transport-route failover is **not** an assignment-level fallback. It does not change node, role, model, assignment, credential identity / scope, task scope, or operator-approved action range. It is a same-node transport-level re-route, and it is **distinct** from the assignment-level fallback prohibited by §7 and §10. Section §3.5.11 itself is **not** a failure class and **must not** be cited as a STOP trigger.

#### §3.5.12 Contract scope

Contract-level minimum report contents for any switch are the minimum information categories listed in §3.5.7. Schema, field names, file names (such as `routes.yaml`-style names), script names, receipt / ledger structures, and executor / wrapper internals are out of contract scope and live in the runtime / node-registry / evidence spec.

#### §3.5.13 MODEL_QUOTA_EXHAUSTED — error class

`MODEL_QUOTA_EXHAUSTED` is a **model-level failure** class. It includes any provider / account / model response indicating: quota exhausted, usage limit reached, credit exhausted, billing hard limit, daily / monthly allowance exhausted, or any other explicit result that the currently designated model cannot be invoked due to quota reasons.

`MODEL_QUOTA_EXHAUSTED` is **not** a transport-path failure (§3.5.5) and **must not** trigger §3.5 route fallback. It enters §7 Failure STOP directly.

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

### §3.8 HERMES_OPENCODE_VERSION_GOVERNANCE_GATE

This is a **dedicated governance gate** managed uniformly by `vibedev` on `21bao`. It does **not** enter the three VibeCoding execution modes (§4.1) and does **not** trigger FULL 9-role or 8-role assignment. Operator is the sole final decision maker. `vibedev` is responsible for unified inventory, audit, proposal, preparation, approved-scope execution, qualification, and reporting. `vibedev` **must not** self-approve, auto-change, auto-expand, or auto-rollback.

#### §3.8.1 V0 — Scope

Operator specifies the target component(s), node(s) / profile(s), and purpose.

#### §3.8.2 V1 — Inventory

`vibedev` read-only collects: current version, configuration, capability, adapter, qualification status, and evidence for each affected component / node / profile.

#### §3.8.3 V2 — Proposal

`vibedev` submits: target version, impact assessment, compatibility / migration analysis, backup plan, rollback plan, qualification plan, and scope recommendation.

#### §3.8.4 V3 — Preparation Approval

Operator approves preparation only. Allowed: download, checksum verification, backup, dry-run, migration / rollback preparation. **Not** allowed: real install, update, downgrade, config migration, restart, or switch.

#### §3.8.5 V4 — Pre-Execution Checkpoint

`vibedev` presents: target version / action / current state / rollback point / affected scope. Operator reviews.

#### §3.8.6 V5 — Second Confirmation

Real install / update / downgrade / config migration / restart / switch **must** receive a second explicit operator confirmation.

#### §3.8.7 V6 — Exact-Scope Execution

Execute only the operator-approved scope. **Must not** expand to other nodes, profiles, or components.

#### §3.8.8 V7 — Qualification

Verify: binary integrity, capability, configuration, provider, model, CMP sync, wrapper, bounded model call, gate, receipt, evidence, secret boundary, rollback feasibility, drift. All applicable checks must PASS. Non-applicable items must carry explicit `NOT_APPLICABLE` with reason; they **must not** be reported as PASS.

#### §3.8.9 V8 — Closeout

Report: result, version matrix, evidence, and residual risks. Failure triggers immediate STOP. **No** auto-rollback, auto-alternative-version, or auto-scope-expansion unless the operator has pre-approved an atomic rollback plan; such rollback must be executed within the approved scope with full evidence logging.

#### §3.8.10 Decoupling principle

`Hermes` and `OpenCode` are maintainable software dependencies of the small cluster. They are **not** immutable infrastructure. Operator may explicitly approve upgrade, downgrade, replacement, or rollback of `Hermes` / `OpenCode` on a designated node or profile.

#### §3.8.11 Architecture-level independence

The cluster's architecture, operator-approved 9-role roster and governance requirements, Central Model Pool, assignment rules, gates, receipts, wrapper, executor, synchronisation, audit, and evidence chain **must not** depend on a single fixed `Hermes` or `OpenCode` version.

#### §3.8.12 Immutability of governance semantics

Version compatibility layers **must not** alter the following governance semantics:

  - operator as sole and final decision maker;
  - orchestrator recommends only;
  - runtime executes exactly the operator-approved assignment;
  - no assignment-level fallback;
  - in `FULL_9_ROLE_VIBECODING`: complete 9-role; in `LIGHTWEIGHT_OPERATION`: operator-approved actual role set;
  - Draft PR → operator-authorised Ready → independently authorised merge;
  - Failure STOP;
  - Central Model Pool unified management;
  - secret handling: public hard boundary + private single-user boundary (§6.6);

---


#### §3.8.13 Version Governance Object Bindings

The V0–V8 stages defined above are bound to Packet, Artifact, and Receipt objects per §10.3.14. V3 preparation approval must not authorise real installation. V4 checkpoint Packet must be reviewed by operator; the review Receipt must not substitute for V5 authorisation. V5 second confirmation is the point at which the exact version, action, node / profile, backup / rollback point, and qualification plan are authorised. V6 execution must read the V5 frozen Packet only; execution Evidence must be recorded independently and must not write back into the V5 Packet. Any change to target version, component, node / profile, action, backup / rollback point, or qualification plan makes the V5 authorisation stale. Any V4/V5/V6 object conflation triggers `VERSION_GOVERNANCE_STAGE_OBJECT_CONFLATION → STOP`; V7 credential Evidence limited to identity/class/binding, no secret value observation.

## §4. VIBECODING_MODE and Entry Gates

### §4.1 VIBECODING_MODE Entry and Pre-Stage

`vibedev` is the operator's dedicated VibeCoding agent / profile. Ordinary daily chat (non-VibeCoding topics) is handled by the independent XiaoMaTi (小马蹄) Hermes profile and is **outside** all execution domains.

Only the operator may explicitly decide to enter `VIBECODING_MODE`. `vibedev` may analyse, clarify, and recommend, but **must not** self-enter.

Once the operator explicitly enters `VIBECODING_MODE`, VC0–VC8 constitute the shared pre-stage for all three sub-modes. VC0–VC6 occur **before** any sub-mode recommendation; VC7 is the recommendation step; VC8 is the operator selection step:

- **VC0** — Operator explicitly enters `VIBECODING_MODE`.
- **VC1** — Operator ↔ `vibedev` requirement discussion and preliminary alignment.
- **VC2** — `vibedev` proposes a bounded read-only Intake plan.
- **VC3** — Operator approves Intake scope, tools, budget, read-only boundary, and explicit exceptions. `vibedev`'s orchestrator model and node are already operator-preselected in the current `vibedev` session and inherited by the `VIBECODING_MODE` run; VC3 records and references this binding but does **not** re-recommend or re-approve it. If the operator actively changes the orchestrator model, or a quota / provider / qualification anomaly occurs, runtime **must** STOP and await operator re-selection; `vibedev` **must not** self-replace.
- **VC4** — `vibedev` executes the approved read-only Intake.
- **VC5** — `vibedev` submits the Intake report.
- **VC6** — Operator ↔ `vibedev` final requirement alignment based on the Intake report, forming `ALIGNED_REQUIREMENT_SCOPE`, exclusions, and success criteria.
- **VC7** — `vibedev` recommends an internal sub-mode (§4.1.1–§4.1.3) with rationale, reasons why alternative modes do not apply, and estimated roles / permissions / risks.
- **VC8** — Operator selects, modifies, or rejects the sub-mode.

**Intake** is a shared pre-stage inside `VIBECODING_MODE`, common to all three sub-modes. It is **not** a gate outside the mode, **not** a fourth sub-mode, and **not** a VERSION / CMP governance gate. Pre-Intake alignment (VC1–VC2) is for investigation direction only; post-Intake alignment (VC6) forms the formal `ALIGNED_REQUIREMENT_SCOPE`. Without operator confirmation, Intake findings **must not** be automatically added to scope.

Intake is **read-only by default**. It does **not** start `explorer` / `planner` or any other non-orchestrator role, and does **not** prove any non-orchestrator role has been executed. Without explicit operator approval, Intake **must not** write, test, SSH, call workers, Git/PR, `--apply`, read secret values, or expand scope. Out-of-scope findings trigger immediate STOP and request supplementary authorisation.

After VC8, the path depends on the selected sub-mode:

  - `VIBECODING_CONSULTATION_ONLY`: `vibedev` does **not** recommend or create non-orchestrator role assignments; no `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE` is formed. `vibedev` generates a consultation-only Work Order based on `OPERATOR_PRESELECTED_SESSION_BINDING` and `OPERATOR_ALIGNED_TASK_SCOPE` (VC6), recording consultation objective, scope / exclusions, permitted read range, forbidden execution boundary, expected output, current orchestrator binding, and applicable budget. The Work Order **must not** authorise writes, SSH, workers, Git/PR, or additional roles.

  - `LIGHTWEIGHT_OPERATION`: `vibedev` recommends the actual non-orchestrator role set; operator approves item by item, forming `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`. Only then does `vibedev` generate the Work Order.

  - `FULL_9_ROLE_VIBECODING`: `vibedev` recommends all 8 non-orchestrator roles; operator approves item by item, forming `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`. Only then does `vibedev` generate the Work Order.

The Work Order **must not** add, delete, replace, or default-assign unapproved roles / nodes / models, and **must not** present recommendations as approvals.

**Work Order approval = job start.** Once the operator explicitly forms `OPERATOR_APPROVED_WORK_ORDER`, this represents the formal start of the current job. No additional "readiness pass" operator checkpoint is required before execution begins.

  - `LIGHTWEIGHT_OPERATION` and `FULL_9_ROLE_VIBECODING` execute continuously within the approved Work Order: `GLOBAL_READINESS` (§4.10) → per-role `ROLE_ACTIVATION_READINESS` (§4.10) → role execution and approval loop → test / review → git-integrator → commit / push → create or update **Draft PR** → STOP and report. The Draft PR is the default auto endpoint for `LIGHTWEIGHT_OPERATION` and `FULL_9_ROLE_VIBECODING`. `Draft → Ready` and merge each require separate independent operator authorisation (§9.2).
  - `VIBECODING_CONSULTATION_ONLY` does **not** run Git / PR. Its default endpoint is the operator-approved consultation deliverable and report.
  - Readiness does **not** create or expand any authorisation. On any STOP trigger, scope / assignment / Work Order drift, or unauthorised demand, `vibedev` **must** STOP before Draft PR creation (or earlier) and report.

  #### §4.1.1 VIBECODING_CONSULTATION_ONLY

Inside `VIBECODING_MODE`, consultation-only discussion, planning, explanation, or research. Does **not** write to the repo, SSH, call workers, or change state. **Does not** enter 8-role assignment. After VC8, `vibedev` generates a consultation-only Work Order (recording objective, scope / exclusions, permitted read range, forbidden execution boundary, expected output, orchestrator binding, and budget) without forming `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`. The operator **must** review, modify, approve, or reject the Work Order. VC8 sub-mode selection or "go-ahead after classification" does **not** substitute for Work Order approval. Only after `OPERATOR_APPROVED_WORK_ORDER` is formed may `vibedev` proceed.

This sub-mode does **not** include operator↔ChatGPT construction-phase discussion. VC0–VC8 (§4.1) are the shared pre-stage for all three sub-modes; `VIBECODING_CONSULTATION_ONLY` does **not** re-enter VC0–VC8. However, VC1 requirement discussion occurs inside `VIBECODING_MODE` and is **not** "outside" the mode.

#### §4.1.2 LIGHTWEIGHT_OPERATION

A task may be classified as LIGHTWEIGHT only when **all** of the following hold:

  - the task is localised, reversible, low-risk, and has clear boundaries;
  - it does **not** change: code or runtime behaviour; contract / governance / policy semantics; permissions, security, or secrets; node, topology, transport, SSH, or credential; CMP, provider, model, alias, or routing; Hermes or OpenCode version or service;
  - it does **not** execute: production apply, deployment, migration, restart, or destructive action;
  - it does **not** require: canonical E2E, release, or readiness verdict.

Recommended minimum roles for LIGHTWEIGHT:
  - orchestrator (`vibedev`);
  - explorer or implementer;
  - one independent verifier / reviewer;
  - git-integrator (if Git write is involved).

**Actual role set principle.** Explorer, Planner, and Implementer execute **only** if each is operator-approved in the actual role set (`OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`). The Work Order **must not** auto-add roles not in the baseline. §4.15 and §4.16 governance rules apply **only** to the actual approved roles; they do **not** imply that unapproved roles must exist.

If the task produces a tracked diff, the actual role set **must** include:

  - a content-author role (default: implementer) operator-approved to produce the diff;
  - at least one independent tester / verifier / reviewer role, separate from the content-author role;
  - git-integrator (if Git write is involved).

Explorer, tester, reviewer, verifier, and git-integrator **must not** write business content. A role operator-approved as content-author must execute under its own distinct assignment and invocation; the same role identity **must not** simultaneously serve as tester, verifier, or reviewer for its own output. Even when independent Gate roles also exist, content-author self-test invocations, reports, or outputs **must not** be counted into any required Gate. Implementer may perform implementation self-check, but only as implementer evidence — such self-check **must not** form `TEST_GATE`, verification Gate, or review Gate. The FULL fixed-role separation requirement is unchanged; `LIGHTWEIGHT_OPERATION` applies the same boundary.

**Verifier cross-Gate independence.** If the same verifier role is operator-approved to serve multiple required Gates, each Gate **must** use an independent `ROLE_ACTIVATION_READINESS`, independent attempt, independent formal invocation, independent charter, independent `ROLE_COMPLETION_REPORT`, and independent evidence packet. The same invocation, report, or output **must not** satisfy multiple Gates.

After VC8, `vibedev` recommends the actual non-orchestrator role set and each role's node, canonical provider, runtime provider, model, responsibilities, independence requirements, budget, and fallback boundaries. Operator approves item by item, forming `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`. Only then does `vibedev` generate the Work Order. The Work Order **must not** add, delete, replace, or default-assign unapproved roles / nodes / models, and **must not** present recommendations as approvals. The operator **must** then review, modify, approve, or reject the Work Order. Assignment baseline approval (`OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`) is **not** equivalent to Work Order approval. Only after `OPERATOR_APPROVED_WORK_ORDER` is formed may `vibedev` proceed to readiness, role execution, or any execution stage.

In `LIGHTWEIGHT_OPERATION`, each operator-approved role **must** also produce a distinct, attributable, meaningful model invocation using its assigned model. Deterministic steps (scripts, `pytest`, Git, SSH, static analysis) **may** serve as internal tool steps for a role but **must not** substitute for that role's own model invocation.

#### §4.1.3 FULL_9_ROLE_VIBECODING

Any of the following **requires** `vibedev` to recommend the complete 9-role roster (§4.3):

  - executable code / runtime / wrapper / executor / gate / receipt / evidence logic changes;
  - contract / governance / policy / authorisation boundary semantic changes;
  - node / topology / transport / SSH / credential / permission / secret management changes;
  - production apply, deployment, migration, destructive operation;
  - cross-node real execution;
  - canonical E2E / release / readiness / production verdict;
  - failure / drift / incident recovery or high-uncertainty task;
  - operator explicitly requires FULL.

**Hermes / OpenCode version or service changes** and **CMP / provider / model / alias / routing changes** are **not** automatic FULL triggers. They enter the dedicated governance gates (§3.8 HERMES_OPENCODE_VERSION_GOVERNANCE_GATE, §6.9 CENTRAL_MODEL_POOL_GOVERNANCE_GATE).

If the task simultaneously changes business runtime logic (or contains other FULL-scope items) **and** involves Hermes/OpenCode VERSION or CMP/provider/model governance items, the scope **must** be split:

  - The business part may be classified by operator as `FULL_9_ROLE_VIBECODING` at VC8.
  - The VERSION part **must** independently enter `HERMES_OPENCODE_VERSION_GOVERNANCE_GATE`.
  - The CMP part **must** independently enter `CENTRAL_MODEL_POOL_GOVERNANCE_GATE`.
  - Operator's choice of FULL for the business part does **not** absorb the governance parts into the same FULL Work Order, authorisation, or operation. Governance parts retain independent scope, independent authorisation records, and independent operations.

### §4.2 Operator Decision

Operator is the **sole** classifier. The decision is a two-stage process:

1. **VC0** — Operator decides whether to enter `VIBECODING_MODE`. This is a standalone binary decision: enter or not enter. No sub-mode is selected or implied at this stage.

2. **VC8** — After completing VC1–VC6 (pre-stage requirement alignment and Intake), `vibedev` recommends a sub-mode in VC7, and operator selects, modifies, or rejects it in VC8.

Operator may also decide to enter a dedicated governance gate (`HERMES_OPENCODE_VERSION_GOVERNANCE_GATE` §3.8 or `CENTRAL_MODEL_POOL_GOVERNANCE_GATE` §6.9) instead of `VIBECODING_MODE`. The two dedicated gates are **outside** `VIBECODING_MODE`; they are **not** sub-modes of it and do **not** form "five parallel entries" with the three sub-modes.

A dedicated governance gate **must not** be re-classified as `VIBECODING_CONSULTATION_ONLY`, `LIGHTWEIGHT_OPERATION`, or `FULL_9_ROLE_VIBECODING`. A dedicated gate **must not** be re-classified into a `VIBECODING_MODE` sub-mode within a single operation.

If the same requirement simultaneously involves business tasks and version / CMP governance, the scope **must** be split into independent scopes, independent authorisation records, and independent operations. Ordinary single-operation approval does **not** change this structural hierarchy. The only alternative is a future V2 amendment to the governance structure.

Ordinary discussion, `VIBECODING_CONSULTATION_ONLY`, or a dedicated governance gate **must not** be used to bypass the applicable LIGHTWEIGHT / FULL sub-mode, operator assignment, or high-risk checkpoint.

**LIGHTWEIGHT risk escalation STOP.** `LIGHTWEIGHT_OPERATION` is valid only while all conditions in §4.1.2 continuously hold. If at any stage after VC8 a FULL trigger item appears, risk escalates, scope expands, or the original classification basis no longer holds, `vibedev` **must** immediately STOP and preserve all evidence produced so far. `vibedev` **must not** auto-escalate to FULL, auto-add roles, rewrite assignments, or continue execution. `vibedev` reports the triggering facts, affected scope, and current state; operator decides whether to return to VC6 for re-alignment, re-classify via VC7/VC8, or terminate.

### §4.3 Full 9-Role Roster (FULL_9_ROLE_VIBECODING)

When operator selects `FULL_9_ROLE_VIBECODING`, the complete 9-role roster applies:

  1. `orchestrator` — fixed to be `vibedev` on `21bao`. The orchestrator's model is operator-preselected in the current `vibedev` session and inherited by the `VIBECODING_MODE` run (assignment_source=`OPERATOR_PRESELECTED_SESSION_BINDING`). The orchestrator is **not** part of the per-task 8-role assignment. The Work Order records the binding (node `21bao`, current model, provider mapping) as an audit fact; recording does **not** constitute a new recommendation or approval. `vibedev` **must not** self-replace the orchestrator model. If the operator actively changes it, or a quota / provider / qualification anomaly occurs, runtime **must** STOP and await operator re-selection.
  2. `explorer`.
  3. `planner`.
  4. `implementer`.
  5. `tester-a`.
  6. `tester-b`.
  7. `reviewer-a`.
  8. `reviewer-b`.
  9. `git-integrator` — if the task has no Git-write sub-task, the role **must still exist** with an explicit "no git write" sub-task note, and evidence must carry `no_git_write=true`.

The enumeration order above defines the **roster**, not execution order, concurrency, handoff, role re-entry, loop, checkpoint, or completion order. The detailed topology is defined by the future operator-approved operational workflow spec or the task-specific workflow plan; it may be sequential, controlled-parallel, or bounded-loop, but **must not** delete, merge, skip, or substitute any FULL mandatory role. `vibedev` (orchestrator) coordinates throughout the entire run but **must not** substitute for any other role's responsibilities.

In `FULL_9_ROLE_VIBECODING`, the 8 non-orchestrator roles (items 2–9 above) enter the per-role assignment process (§5). The orchestrator is **not** re-recommended or re-approved during assignment. After assignment baseline approval and Work Order generation, the operator **must** review, modify, approve, or reject the Work Order. Assignment baseline approval (`OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`) is **not** equivalent to Work Order approval. Only after `OPERATOR_APPROVED_WORK_ORDER` is formed may `vibedev` proceed to readiness, role execution, or any execution stage.

### §4.4 Forbidden Role-Execution Patterns (FULL and LIGHTWEIGHT modes)

- role trimming / merging / fast path / simple-bypass / low-risk-bypass — the "complete 9-role must not be trimmed" rule applies only to `FULL_9_ROLE_VIBECODING`; `LIGHTWEIGHT_OPERATION` executes the operator-approved actual role set;
- named-but-not-executed (named without execution);
- merging into another role;
- substituting simulation for real execution;
- claiming a role is completed **merely** by running generic commands such as `pytest`, `fixture`, `lint`, static analysis, deterministic scripts or simulation. Deterministic tools **may** serve as a role's internal execution steps, data sources, and evidence, but **must not** be the sole basis for role completion. In both `FULL_9_ROLE_VIBECODING` and `LIGHTWEIGHT_OPERATION`, each actual role must satisfy all of the following: its distinct meaningful model invocation (§4.5), role-specific work product, and completion evidence (§4.8). Generic commands, scripts, or test results alone **cannot** prove a role is complete. The roster enumeration (§4.3) defines the role set, not execution order, concurrency, handoff, re-entry, loop, checkpoint, or completion order;
- "workload is small → skip this role".

### §4.5 Distinct Model Invocation Requirement (FULL and LIGHTWEIGHT modes)

In an operator-approved `FULL_9_ROLE_VIBECODING` run, each of the nine roles **must** execute at least one distinct, attributable, meaningful, evidence-bearing model invocation using the operator-specified model for that role. For the orchestrator, this is the operator-preselected session model (§4.3). For each non-orchestrator role, this is the operator-assigned model from the 8-role assignment (§5).

In `LIGHTWEIGHT_OPERATION`, only the operator-approved actual role set **must** satisfy the same distinct model invocation requirement. `VIBECODING_CONSULTATION_ONLY` does **not** trigger additional execution roles and therefore does **not** require per-role model invocation.

Deterministic tools, scripts, `pytest`, Git, SSH, file reads, and static analysis **may** assist a role's work but **must not** substitute for that role's own model invocation.

The following are **forbidden**:

- a single model call counted toward multiple roles;
- the orchestrator writing output on behalf of another role;
- copying or splitting a single response to impersonate multiple roles;
- ACK-only, empty, template-placeholder, or no-substantive-task invocations;
- executing a generic command and claiming the role is complete.

### §4.6 Empty-Placeholder and Constant-Verdict Prohibition (FULL and LIGHTWEIGHT modes)

Empty placeholders (no input + no output + no evidence) are **forbidden**. Permitted output constants: `NO_CHANGE_REQUIRED`, `NOT_APPLICABLE`, `NO_GIT_WRITE_REQUIRED`.

These constants **may only** appear as a verdict after a substantive model invocation and evidence analysis. Each constant usage **must** be accompanied by:

- reason;
- inspection scope;
- evidence references;
- applicable boundary.

A constant alone does **not** satisfy the substantive work product or role completion requirement (§4.8). This applies to both `FULL_9_ROLE_VIBECODING` (all nine roles) and `LIGHTWEIGHT_OPERATION` (operator-approved actual role set). `NOT_APPLICABLE` **must not** be used to exempt a FULL mandatory role from execution entirely. In `LIGHTWEIGHT_OPERATION`, there are no "default roles" beyond the operator-approved set; constants **must not** be used to fabricate execution of an unapproved role. For `git-integrator` when no Git write is involved, the role **must** still execute a distinct model invocation, produce a no-git-write eligibility check with repo / baseline / diff evidence, and deliver a reasoned verdict.

### §4.7 Model Invocation Evidence (FULL and LIGHTWEIGHT modes)

Each role's model invocation evidence **must** associate at least:

- task / run ID, role, node, operator-specified model (operator-preselected session model for orchestrator, operator-assigned model for non-orchestrator roles);
- canonical provider, runtime provider;
- role invocation ID; provider request ID if available;
- start / end time, success / failure;
- role-specific input summary or prompt digest;
- output summary, response digest, or controlled artifact reference;
- usage / token count if provider provides; otherwise `NOT_AVAILABLE`;
- tool executions, produced artifacts, and verdict references.

In `FULL_9_ROLE_VIBECODING`, all nine roles **must** satisfy this evidence requirement. In `LIGHTWEIGHT_OPERATION`, only the operator-approved actual role set **must** satisfy it. `VIBECODING_CONSULTATION_ONLY` does **not** trigger 8-role assignment and therefore does **not** require per-role invocation evidence.

For the orchestrator role, the operator-approved assignment is satisfied by two independent components:

  a. **`OPERATOR_PRESELECTED_SESSION_BINDING`** — node fixed to `21bao`; current orchestrator model and its provider mapping are operator-preselected in the current `vibedev` session and inherited by the `VIBECODING_MODE` run. This binding does **not** enter the non-orchestrator assignment recommendation or approval process (§4.3).

  b. **`OPERATOR_ALIGNED_TASK_SCOPE`** — task objective, scope, exclusions, and success criteria formed by VC6 final requirement alignment (§4.1). This scope is **not** part of the session binding; it is referenced and solidified by the selected sub-mode, the operator-approved role-node-model assignment baseline, and the Work Order.

The orchestrator's model invocation evidence follows the same schema; its completion evidence is the coordinated run itself and does **not** substitute for any other role's evidence.

### §4.8 Role Completion Criteria (FULL and LIGHTWEIGHT modes)

A successful model invocation alone does **not** equal role completion. A role is complete only when all of the following are satisfied:

1. operator-approved assignment exists;
2. role-specific input and responsibility defined;
3. at least one distinct model invocation as per §4.5;
4. substantive work product produced;
5. acceptance criteria result available;
6. associable evidence with completion status.

Model invocation failure, quota exhaustion, missing or unparseable model output, or unreachable / untrustworthy evidence pipeline or channel — these are **hard failures** and trigger §7 STOP directly. Scripts, other roles, or the orchestrator **must not** substitute for the missing or untrustworthy output. The role **must not** retry, "补报告" (patch the report), or reissue an invocation outside the §4.12 bounded corrective loop just to satisfy criteria 1–6.

By contrast, when the role did produce a real model invocation and a real work product but the `ROLE_COMPLETION_REPORT` has missing fields, recoverable evidence linkage gaps, `FAIL` on acceptance criteria, or a change demand / quality issue, the cross-verification yields `ROLE_COMPLETION_INCOMPLETE` or `ROLE_COMPLETION_REJECTED` (§4.13) and the run is eligible for the §4.12 bounded corrective loop — only if the Work Order's pre-approved path covers that signature. Otherwise STOP.

In `FULL_9_ROLE_VIBECODING`, all nine roles **must** satisfy these criteria. In `LIGHTWEIGHT_OPERATION`, only the operator-approved actual role set **must** satisfy them. `VIBECODING_CONSULTATION_ONLY` does **not** trigger 8-role assignment.

For the orchestrator role, criterion 1 (operator-approved assignment) is satisfied by two independent components:

  a. **`OPERATOR_PRESELECTED_SESSION_BINDING`** — node fixed to `21bao`; current orchestrator model and its provider mapping are operator-preselected in the current `vibedev` session and inherited by the `VIBECODING_MODE` run (§4.3).

  b. **`OPERATOR_ALIGNED_TASK_SCOPE`** — task objective, scope, exclusions, and success criteria formed by VC6 final requirement alignment (§4.1), subsequently referenced and solidified by the selected sub-mode, the operator-approved role-node-model assignment baseline, and the Work Order.

The orchestrator's completion is evidenced by the coordinated run itself; it does **not** substitute for any other role's completion evidence.

### §4.9 Independence of Dual Tester / Dual Reviewer (FULL mode)

The FULL default topology, isolation requirements, and gates are specified in §4.16. The following principles apply to both FULL and LIGHTWEIGHT modes:

`tester-a` / `tester-b` and `reviewer-a` / `reviewer-b` **must** be independent across `assignment` / `context` / `prompt` / `execution batch` / `output` / `evidence`:

- tester-a and tester-b **must** use different role invocation IDs, independent prompts / contexts, independent outputs, and independent evidence;
- reviewer-a and reviewer-b **must** use different role invocation IDs, independent prompts / contexts, independent outputs, and independent evidence;
- neither side **may** share a single model call;
- the later role **must not** merely restate the earlier role's conclusion;
- blind review records allowed reads and forbidden reads.

Different node or different model remains a **recommended** enhancement (not required) unless operator explicitly mandates it, and is **not** the sole independence criterion.

If independence cannot be achieved, runtime **must** STOP, explain the cause and risk, await operator decision, and **must not** automatically degrade.

### §4.10 Dual-Layer Readiness (`GLOBAL_READINESS` + `ROLE_ACTIVATION_READINESS`)

`vibedev` / orchestrator executes both readiness layers. Neither readiness check counts as a target role's distinct model invocation (§4.5) nor substitutes for any role's business execution.

#### §4.10.1 `GLOBAL_READINESS`

Executed **once** immediately after `OPERATOR_APPROVED_WORK_ORDER` is formed, and again whenever an invalidation condition holds. `vibedev` does **not** introduce a separate validator role and does **not** re-confirm with operator; the operator-approved Work Order is the start signal. No sub-mode requires an additional operator "start" confirmation.

At minimum, `GLOBAL_READINESS` checks:

  - Work Order completeness, signature, and consistency with `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE` (where applicable), `OPERATOR_PRESELECTED_SESSION_BINDING`, and `OPERATOR_ALIGNED_TASK_SCOPE` (VC6);
  - `21bao` control plane availability and current `vibedev` session binding continuity;
  - VC6 scope and selected sub-mode (`VIBECODING_CONSULTATION_ONLY` / `LIGHTWEIGHT_OPERATION` / `FULL_9_ROLE_VIBECODING`) still in force; sub-mode drift → STOP;
  - repo / branch / base / HEAD / working tree state and tracked status;
  - all applicable non-orchestrator assignments still valid;
  - node identity and transport baseline (§3.1.4, §3.5, §3.6);
  - CMP / model / provider / alias / credential / wrapper / toolchain readiness;
  - evidence chain integrity;
  - `LIGHTWEIGHT_OPERATION` / `FULL_9_ROLE_VIBECODING` capability to close back to a Draft PR (Git remote, push path, Draft PR endpoint).

Primary outcomes:

  - `GLOBAL_READINESS_PASS`:
    - `VIBECODING_CONSULTATION_ONLY`: `vibedev` / orchestrator directly executes the operator-approved consultation Work Order, produces the consultation deliverable and report. **No** non-orchestrator `ROLE_ACTIVATION_READINESS`, no `ROLE_COMPLETION_REPORT`.
    - `LIGHTWEIGHT_OPERATION` / `FULL_9_ROLE_VIBECODING`: `vibedev` automatically proceeds to the first applicable non-orchestrator role's `ROLE_ACTIVATION_READINESS`.
  - `GLOBAL_READINESS_STOP` → STOP and report. Warnings **must not** silently downgrade to PASS.

A readiness probe verifies callability; it does **not** count as a business role's distinct model invocation and does **not** satisfy any role's work product or completion criterion.

Invalidation conditions:

  - Work Order, VC6 scope, sub-mode, assignment, repo baseline, control plane, node identity, transport, CMP / provider / credential, toolchain, or evidence mechanism undergoes a substantive change;
  - any role's `ROLE_ACTIVATION_READINESS` reveals a global invariant shift.

When invalidated, mark `GLOBAL_READINESS_INVALIDATED` and either re-run `GLOBAL_READINESS` or STOP.

#### §4.10.2 `ROLE_ACTIVATION_READINESS`

Each non-orchestrator role's formal model invocation **must** be preceded by a `ROLE_ACTIVATION_READINESS` check executed by `vibedev` / orchestrator. The orchestrator role itself is covered by `GLOBAL_READINESS` plus necessary continuity checks; it does **not** require a separate Activation check.

At minimum, `ROLE_ACTIVATION_READINESS` checks:

  - the target role's assignment is still operator-approved and not superseded;
  - required input / artifact versions are complete and consistent with current scope;
  - node identity and same-node route (§3.5) currently available;
  - assigned model / provider / alias / credential / quota currently available;
  - tools / permissions / evidence channels match role requirements;
  - scope and `GLOBAL_READINESS` state have not drifted.

Primary outcomes:

  - `ROLE_ACTIVATION_READINESS_PASS` → `vibedev` immediately starts the role's formal model invocation. No additional operator checkpoint.
  - `ROLE_ACTIVATION_READINESS_FAIL` → STOP and report; do **not** start the role.
  - Auto fallback is permitted **only** for the **same node**, operator-approved, registered, and qualified route per §3.5; it does **not** change node / model / assignment / scope.

Activation checks and probes **must not** count as the target role's execution, distinct model invocation, work product, or completion evidence (§4.5, §4.7, §4.8).

#### §4.10.3 Readiness Failure, Invalidation, and Revalidation Policy

The following policy unifies §4.10.1, §4.10.2, §7.1, §7.3, §7.6 and §4.14 and resolves earlier "readiness invalid → STOP" ambiguity.

**Hard failure codes (no revalidation).** Each of the following enters the existing §7 STOP / recovery flow **immediately** and **must not** be hidden behind revalidation, dynamic refresh, or operator-absence waiting:

  - `MODEL_QUOTA_EXHAUSTED` (§3.5.13, §5.10, §7.1);
  - model call failure (§7.1);
  - credential missing / not loaded / auth failure / credential provenance anomaly (§6.6, §7.1);
  - `CONTROL_PLANE_UNAVAILABLE` (§3.6, §7.1) — `21bao` control-plane recovery follows §3.6.7 and **must not** be bypassed by §4.10.3;
  - designated node unavailable / node health = `UNKNOWN` (§3.1, §7.1);
  - `GLOBAL_READINESS_STOP` (whenever the underlying cause is any hard failure code above);
  - `ROLE_ACTIVATION_READINESS_FAIL` (same).

Same-node approved route fallback remains exclusively under §3.5; it is not a §4.10.3 revalidation path.

**Pause-and-revalidate path (bounded).** Applicable **only** when **none** of the hard failure codes above fired, **and** Work Order, VC6 scope, sub-mode, assignment, node / model / provider / credential identity, and permissions are unchanged. Examples include freshness refresh of the node health timestamp, re-collection of read-only state evidence, fresh probe of an already-available route, or other non-identity dynamic evidence whose only defect is staleness — not absence or corruption. Under these conditions `vibedev` may pause dispatch, re-run `GLOBAL_READINESS` (and the affected `ROLE_ACTIVATION_READINESS`), and resume. Operator re-approval is **not** required.

**STOP-back-to-operator path.** When Work Order, VC6 scope, sub-mode, assignment, node / model / provider / credential identity, or permissions change, `vibedev` **must** STOP and return to operator; revalidation alone does **not** authorise continuation.

**Normal CANDIDATE_TRIPLE progression.** Repo baseline progression that is normal, authorised, and within the Work Order (e.g. expected CANDIDATE_TRIPLE / artifact version advance on the working branch) is **not** repo baseline drift. It is handled by the §4.14 dependency-invalidation rules. Only unexpected, external, or out-of-Work-Order changes to branch / base / HEAD / working tree trigger `GLOBAL_READINESS_INVALIDATED` or STOP.

`GLOBAL_READINESS_INVALIDATED` and re-running are recorded in evidence; the result is either `GLOBAL_READINESS_PASS` (continue) or `GLOBAL_READINESS_STOP` (STOP).

### §4.11 Conflict Escalation (FULL and LIGHTWEIGHT modes)

This section applies to:
- in `FULL_9_ROLE_VIBECODING`: tester-a, tester-b, reviewer-a, reviewer-b (§4.16.3–§4.16.5);
- in `LIGHTWEIGHT_OPERATION`: any operator-approved verifier, tester, or reviewer role.

When such a role raises a valid change demand, the current CANDIDATE_TRIPLE **must not** enter PASS, Git integration, or closeout. `vibedev` **must** record the disagreement, affected scope, and evidence.

For FULL tester / reviewer conflicts, follow the `TEST_CONTRADICTION_PACKET` / `REVIEW_CONTRADICTION_PACKET` procedure in §4.16.4 / §4.16.5 respectively. For other roles, which role to return to, which steps to re-run, and whether a new checkpoint is required are determined by the future operator-approved operational workflow spec or the current task-specific workflow plan. If the existing approved plan does not define a recovery path, or the disagreement cannot be resolved, runtime **must** STOP and await operator decision. `vibedev` **must not** unilaterally compromise, ignore a change demand, or invent an unapproved loop.

### §4.12 Work Order Pre-Approved Bounded Corrective Loop

The §4.12 loop addresses **recoverable completion deficiency** only. A role that **never produced a real model invocation**, **produced no parseable output**, or whose evidence pipeline / channel is **unreachable or untrustworthy** has not entered the recoverable-deficiency class — it is a hard failure (§4.8) and **must** trigger §7 STOP. The §4.12 loop **must not** be used to "补报告" (patch the report) over a missing or fabricated invocation, empty output, fabricated evidence, or evidence infrastructure failure.

When `vibedev` (orchestrator) cross-verifies a role completion (§4.8) and reaches `ROLE_COMPLETION_INCOMPLETE` or `ROLE_COMPLETION_REJECTED` (§4.13) on the recoverable-deficiency class, the run **may** return to a relevant role **without** re-asking operator, **only if** the Work Order itself pre-approves the loop path. The Work Order **must** enumerate for each pre-approved path:

  - start role and end role (return-to role);
  - triggering condition (which `ROLE_COMPLETION` verdict or change-demand class triggers this path);
  - mandatory re-run role set;
  - per-path maximum rounds (suggested range: `LIGHTWEIGHT_OPERATION` 3–5 rounds, `FULL_9_ROLE_VIBECODING` 3–5 rounds);
  - global maximum rounds (suggested range: `LIGHTWEIGHT_OPERATION` 4–8 rounds, `FULL_9_ROLE_VIBECODING` 8–12 rounds);
  - required evidence per round;
  - STOP conditions.

Specific values are recommended by `vibedev` and approved by operator in the Work Order. Runtime **must not** raise or lower these budgets without a new operator authorisation.

Each loop round **must** record:

  - loop ID and round number;
  - failure or change-demand signature;
  - return-to role;
  - invalidated artifacts (§4.14);
  - new input set;
  - new artifact version;
  - result and remaining budget.

`LOOP_STAGNATION_DETECTED` fires when **two consecutive rounds** show no effective diff, no new root-cause evidence, no coverage improvement, no change-demand resolution, and no new hypothesis. On detection, STOP and report.

Immediate STOP and report is also required when:

  - per-path or global budget exhausts;
  - quota exhausts;
  - scope / assignment / model / node / provider / credential changes;
  - the run exits the pre-approved path;
  - governance items (VERSION / CMP) appear;
  - no convergence possible.

A loop **must not**:

  - expand scope;
  - add / remove roles;
  - swap node / model / provider;
  - add permissions;
  - auto-escalate `LIGHTWEIGHT_OPERATION` to `FULL_9_ROLE_VIBECODING`;
  - enter a VERSION / CMP governance gate.

Before returning to a role, re-run its `ROLE_ACTIVATION_READINESS` (§4.10). If a global invariant has shifted, mark `GLOBAL_READINESS_INVALIDATED` (§4.10) and re-run `GLOBAL_READINESS` or STOP.

### §4.13 `ROLE_COMPLETION_REPORT` and Cross-Verification

Each non-orchestrator role **must** submit one `ROLE_COMPLETION_REPORT` at the end of each **role execution attempt / activation cycle**. A single attempt may comprise one or more formal, independent, attributable model invocations and authorised tool interactions performed under the same activation; the report aggregates **all** invocations, tools, artifacts, and evidence produced within that attempt.

  - Each role execution attempt carries a distinct `attempt_id` and produces exactly one `ROLE_COMPLETION_REPORT` for that attempt.
  - Readiness probes **must not** be counted into any attempt and **must not** appear inside the report.
  - When a bounded corrective loop (§4.12) reactivates a role, that reactivation creates a **new attempt** with a new `attempt_id` and a new `ROLE_COMPLETION_REPORT`. The previous report remains in evidence but **must not** count toward the new attempt's PASS.
  - Nothing in this section requires or implies that a role may invoke the model only once. The "one model call per role" rule is **not** a contract rule; the rules are distinct model invocation (§4.5) and 6-condition completion (§4.8). An attempt may include multiple formal invocations; only the **final** attempt's complete aggregated report is the completion report for that attempt.
  - Intermediate call outputs **must not** impersonate the final completion report.

The report **must** include at minimum:

  - `attempt_id`, task / run ID, role, node, **`operator-assigned model` (sourced from the operator-approved `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`)**, canonical / runtime provider, formal invocation ID(s), and assignment reference;
  - actual input, scope / exclusions, and prerequisite artifact / version references;
  - distinct meaningful model invocation evidence (§4.5, §4.7) for each invocation in the attempt;
  - tools / commands, return code, outputs, artifacts, and side-effect evidence;
  - role-specific work product;
  - acceptance criteria, each marked `PASS` / `FAIL` / evidence-backed `NOT_APPLICABLE`;
  - blockers, warnings, assumptions, change demands, scope drift;
  - completion claim and status.

`§4.13` applies only to non-orchestrator roles. The model field is unified to `operator-assigned model` referencing the approved assignment baseline; it **must not** be written as the orchestrator's session-preselected model. The orchestrator role does **not** submit a non-orchestrator `ROLE_COMPLETION_REPORT`; the orchestrator's coordination evidence follows §4.7.

The role **must not** self-announce "verified" or "final". `vibedev` (orchestrator) cross-verifies the report against assignment, invocation uniqueness, tool results, artifacts / diff, acceptance evidence, permission scope, and tester / reviewer independence. Cross-verification yields exactly one of:

  - `ROLE_COMPLETION_VERIFIED` — proceed;
  - `ROLE_COMPLETION_INCOMPLETE` — eligible for §4.12 pre-approved return path if the path covers this signature;
  - `ROLE_COMPLETION_REJECTED` — eligible for §4.12 path if covered; otherwise STOP.

Ordinary model output, empty conclusions, or tool success alone do **not** equal role completion. Orchestrator cross-verification does **not** replace tester / reviewer business duties.

### §4.14 Default Return Matrix and Artifact Invalidation

Default rules (Work Order may tighten but **must not** loosen the safety bounds; it does **not** fix a rigid linear role order):

  - explorer evidence insufficient → return to `explorer`; if the explorer fact base materially changes, `planner` and all downstream artifacts are invalidated.
  - planner defect → return to `planner`; if needed, also rerun `explorer` first; if the plan materially changes, `implementer` and all downstream artifacts are invalidated.
  - implementer / CANDIDATE_TRIPLE defect → return to `implementer`; on CANDIDATE_TRIPLE change, dependent tests, all reviewers' outputs, and Git-write evidence are invalidated.
  - tester reports an implementation defect → return to `implementer`; in `FULL_9_ROLE_VIBECODING` any change to implementation code or runtime behaviour defaults to re-running both `tester-a` and `tester-b` and both `reviewer-a` and `reviewer-b`.
  - tester methodology defect → return to the originating tester; if acceptance criteria change, return to `planner` or STOP.
  - reviewer reports an implementation / plan / fact issue → return respectively to `implementer` / `planner` / `explorer`, then re-run affected downstream; in `FULL_9_ROLE_VIBECODING` any implementation change defaults to re-running both testers and both reviewers.
  - pure Git authentication / proxy / transport failure where CANDIDATE_TRIPLE / diff did not change → only `git-integrator` recovery; `git-integrator` **must not** modify business files.
  - diff out-of-scope or CANDIDATE_TRIPLE changed → return to the responsible role and invalidate its downstream evidence.

Artifact status taxonomy: `ARTIFACT_VALID`, `ARTIFACT_INVALIDATED`, `ARTIFACT_SUPERSEDED`, `ARTIFACT_REVALIDATION_REQUIRED`. Each artifact record carries: ID, version, producer, input IDs, CANDIDATE_TRIPLE SHA / digest, and status. Before a loop begins, an explicit invalidation manifest **must** be generated. Old evidence is retained for audit but **must not** count toward current PASS.

### §4.15 Explorer / Planner Independence, Validation, and Plan Checkpoint

**Mode scope.** `FULL_9_ROLE_VIBECODING`: Explorer, Planner, Implementer, and the complete §4.15 validation / checkpoint chain are **mandatory**. `LIGHTWEIGHT_OPERATION`: Explorer, Planner, and Implementer execute **only** if each is operator-approved in the actual role set. §4.15 rules apply to each actually existing role; they do **not** imply that unapproved roles must exist. If LIGHTWEIGHT enables the Plan checkpoint (per Work Order), the actual role set **must** include both Explorer and Planner before the checkpoint, and the full `EXPLORER_VALIDATION_PASS → PLAN_VALIDATION_PASS → operator Plan checkpoint` chain executes. `VIBECODING_CONSULTATION_ONLY`: does **not** apply.

This section hardens the role boundaries, validation gate, and the `IMPLEMENTATION_PLAN_APPROVAL_PACKET` operator checkpoint. It does **not** fix the task-specific linear order beyond the dependencies named here, nor does it fix tester / reviewer concurrency, Git command order, closeout schema, or the complete `VIBECODING_MODE` state machine.

#### §4.15.1 Explorer and Planner as Independent Roles

`explorer` and `planner` are independent roles. Each **must** independently hold:

  - operator-approved assignment entry in `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`;
  - its own `ROLE_ACTIVATION_READINESS` (§4.10.2);
  - at least one distinct meaningful model invocation on the operator-assigned model (§4.5, §4.13);
  - its own `ROLE_COMPLETION_REPORT` (§4.13);
  - attributable artifact / evidence, versioned per §4.14.

Responsibility split (operator-approved Work Order may tighten but **must not** loosen the boundary):

  - `explorer` — fact investigation: findings, root-cause candidates, coverage matrix, alternative hypotheses, unknowns. Output is the **fact base** and **evidence map**.
  - `planner` — requirement traceability, implementation steps, file / module scope, test / review plan, risk register, rollback plan, Draft PR closeout plan. Output is the **plan**, traceable back to `explorer` evidence.

`vibedev` / orchestrator calls, analysis, or summaries **must not** count as `explorer` or `planner` execution. Shared or reused role output across `explorer` and `planner` is forbidden (drift signal `SHARED_OR_REUSED_ROLE_OUTPUT_DETECTED`).

#### §4.15.2 `EXPLORER_VALIDATION` and `PLAN_VALIDATION`

**Mode scope.** `FULL_9_ROLE_VIBECODING`: both validations are **mandatory**. `LIGHTWEIGHT_OPERATION`: applies only if Explorer / Planner are in the actual role set. `VIBECODING_CONSULTATION_ONLY`: does **not** apply.

After the respective role's `ROLE_COMPLETION_REPORT` passes §4.13 cross-verification, `vibedev` (orchestrator) executes the corresponding **independent validation** and produces a separate validation report. Validations do **not** substitute for later `tester` / `reviewer` business duties.

**Hard gate: Explorer PASS before Planner activation.** `planner` **must not** enter `ROLE_ACTIVATION_READINESS` (§4.10.2) or begin a formal model invocation before `EXPLORER_VALIDATION_PASS` is reached. `EXPLORER_VALIDATION_INCOMPLETE` / `REJECTED` must return to `explorer` per the Work Order's pre-approved §4.12 path; the `planner` **must not** start planning on an unvalidated fact base. When a new `explorer` attempt produces a new fact base version that invalidates the prior fact base, any already-produced `planner` artifact is `ARTIFACT_INVALIDATED` / `REVALIDATION_REQUIRED` (§4.14). Task-specific topology **must not** bypass the `EXPLORER_VALIDATION_PASS → planner activation` dependency.

`EXPLORER_VALIDATION` produces an `EXPLORER_VALIDATION_REPORT` checking, at minimum:

  - fact ↔ evidence mapping for each finding (file / symbol / SHA / command / log / artifact);
  - distinction of `OBSERVED_FACT` / `SUPPORTED_INFERENCE` / `ASSUMPTION` / `UNKNOWN`;
  - coverage matrix, alternative hypotheses, and counter-evidence;
  - whether facts materially affecting scope or technical route are backed by sufficient and, where possible, **independent dual sources**;
  - consistency with VC6 scope, `OPERATOR_APPROVED_WORK_ORDER`, sub-mode, and governance boundaries.

Verdict: `EXPLORER_VALIDATION_PASS` / `INCOMPLETE` / `REJECTED`.

`PLAN_VALIDATION` produces a `PLAN_VALIDATION_REPORT` checking, at minimum:

  - every VC6 requirement is covered by a plan item;
  - every plan item references Explorer evidence;
  - scope closure, implementation feasibility, test and dual-review coverage, risk register, rollback plan, and Draft PR closeout plan are complete;
  - no `TBD`, no auto-select, no unapproved assignment / permission change, no VERSION / CMP item sneaked in.

Verdict: `PLAN_VALIDATION_PASS` / `INCOMPLETE` / `REJECTED`.

**Provenance binding.** `EXPLORER_VALIDATION_REPORT` and `PLAN_VALIDATION_REPORT` **must** record the `artifact_id`, `version`, and `digest` of each source artifact they reference. When the originating role produces a new artifact version, the old validation report is automatically `ARTIFACT_INVALIDATED` (§4.14) and must be re-run before downstream steps may proceed.

On `INCOMPLETE` / `REJECTED`, return to the originating role per the Work Order's pre-approved §4.12 path. On scope / sub-mode / assignment / permission drift, STOP and return to operator.

#### §4.15.3 `IMPLEMENTATION_PLAN_APPROVAL_PACKET` and `OPERATOR_APPROVED_IMPLEMENTATION_PLAN`

**Mode scope.** `FULL_9_ROLE_VIBECODING`: the Plan checkpoint is **mandatory**. `LIGHTWEIGHT_OPERATION`: applies only if enabled by the Work Order; if enabled, the actual role set **must** include both Explorer and Planner. `VIBECODING_CONSULTATION_ONLY`: does **not** apply.

`FULL_9_ROLE_VIBECODING` **default** pipeline:

```
EXPLORER_VALIDATION_PASS
  → PLAN_VALIDATION_PASS
  → IMPLEMENTATION_PLAN_APPROVAL_PACKET
  → operator reviews / requests revision / approves / rejects
  → OPERATOR_APPROVED_IMPLEMENTATION_PLAN
  → implementer ROLE_ACTIVATION_READINESS
```

`FULL_9_ROLE_VIBECODING` implementer **must not** start until `OPERATOR_APPROVED_IMPLEMENTATION_PLAN` is formed. `LIGHTWEIGHT_OPERATION` may enable this checkpoint; if enabled by the Work Order, it follows the same flow. If not enabled by the Work Order:

  - **Planner in actual role set**: `PLAN_VALIDATION_PASS` must be reached before implementer activation; CANDIDATE_TRIPLE plan source binding follows §4.16.2 (`LIGHTWEIGHT` without Plan checkpoint, Planner in actual role set).
  - **Planner not in actual role set**: `PLAN_VALIDATION_PASS` **must not** be required. Implementer may advance only when the Work Order explicitly records `direct_to_implementer=true`, the objective / modification boundary / acceptance criteria / test-review requirements / rollback / exclusions are complete, and §4.16.2 provenance is valid.

`VIBECODING_CONSULTATION_ONLY` does **not** apply.

The `IMPLEMENTATION_PLAN_APPROVAL_PACKET` **must** faithfully aggregate:

  - objective, success criteria;
  - Explorer key facts and evidence (with `EXPLORER_VALIDATION_REPORT` verdict);
  - Planner plan items: target files / modules, expected behaviour change;
  - test / review arrangement, risk register, rollback plan, loop budgets, exclusions;
  - `PLAN_VALIDATION_REPORT` verdict and whether the packet is fully consistent with `OPERATOR_APPROVED_WORK_ORDER`.

**Provenance binding.** The `IMPLEMENTATION_PLAN_APPROVAL_PACKET` **must** record the `artifact_id`, `version`, and `digest` of the `EXPLORER_VALIDATION_REPORT`, `PLAN_VALIDATION_REPORT`, and each `planner` artifact it references. When any source artifact produces a new version, the old approval packet is automatically `ARTIFACT_INVALIDATED` (§4.14) and must be regenerated.

**Operator actions at the Plan checkpoint.** The operator **may**: approve the packet as-is; reject it (STOP); request revision (with specific change demands); or add conditions that do **not** expand Work Order scope, permissions, sub-mode, assignment, node / model / provider, or governance boundaries. Any substantive technical plan change — including adding, deleting, or rewriting implementation steps, target files, test plan, risk register, or rollback — **must** be returned to `planner` for a new attempt, new formal model invocation, new artifact version, new `ROLE_COMPLETION_REPORT`, re-run `PLAN_VALIDATION`, and a new approval packet. The operator **must not** directly rewrite a validated planner artifact and allow `implementer` to proceed on it. Scope, permission, sub-mode, assignment, node / model / provider, or governance boundary changes require STOP and return to VC6 / VC7 / VC8, assignment, or Work Order approval.

Operator's Plan approval **only** approves "how to implement". It **must not** expand Work Order scope, permissions, sub-mode, assignment, node / model / provider, or governance boundaries. Any of those changes requires STOP and a return to VC6 / VC7 / VC8, assignment, or Work Order approval.

After Plan approval, the cluster auto-continues under existing authorisations to the Draft PR (§4.1, §9.2). `Draft → Ready` and merge still each require independent operator authorisation.



---

### §4.16 FULL Default Mid-to-Late-Stage Topology: Candidate Freeze, Dual Tester, Test Gate, Dual Reviewer, Review Gate, Git-Integrator

**Mode scope.** `FULL_9_ROLE_VIBECODING`: the FULL topology below is **mandatory** — dual tester, dual reviewer, `TEST_GATE_PASS`, `REVIEW_GATE_PASS`. `LIGHTWEIGHT_OPERATION`: only the operator-approved actual tester / reviewer / verifier roles execute; the Work Order **must not** auto-upgrade to dual tester / dual reviewer. The same independence, CANDIDATE_TRIPLE-freeze, evidence-gate, and invalidation principles apply to the actual role set. `VIBECODING_CONSULTATION_ONLY`: does **not** apply.

This section does **not** fix task-specific command details, workspace implementation, packet/schema fields, Git command-level order, closeout schema, or the complete `VIBECODING_MODE` state machine.

#### §4.16.1 Pipeline Topology (FULL Default)

```
OPERATOR_APPROVED_IMPLEMENTATION_PLAN
  → implementer ROLE_ACTIVATION_READINESS / execution
  → IMPLEMENTATION_CANDIDATE (§4.16.2)
  → CANDIDATE_FROZEN_FOR_TEST (§4.16.2)
  → tester-a || tester-b (§4.16.3)
  → TEST_EVIDENCE_PACKET (§4.16.4)
  → TEST_GATE_PASS (§4.16.4)
  → REVIEW_INPUT_PACKET (§4.16.5)
  → reviewer-a || reviewer-b (§4.16.5)
  → REVIEW_GATE_PASS (§4.16.5)
  → git-integrator ROLE_ACTIVATION_READINESS / formal Git write (§4.16.7)
```

`||` denotes parallel execution with strict isolation (§4.16.3, §4.16.5). This dependency chain and its gates are the FULL default governance baseline. Candidate plan source binding follows §4.16.2 per sub-mode.

#### §4.16.2 `IMPLEMENTATION_CANDIDATE` and `CANDIDATE_FROZEN_FOR_TEST`

When `implementer` completes an attempt and reaches `ROLE_COMPLETION_VERIFIED` (§4.13), a versioned `IMPLEMENTATION_CANDIDATE` is formed. The plan source binding depends on sub-mode:

  - **`FULL_9_ROLE_VIBECODING`**: CANDIDATE_TRIPLE **must** bind both the `IMPLEMENTATION_PLAN_APPROVAL_PACKET` artifact ID / version / digest **and** a non-repudiable reference to the `OPERATOR_APPROVED_IMPLEMENTATION_PLAN` approval record / status. Neither the packet name alone ("approved" in the label) nor orchestrator self-attestation substitutes for operator approval evidence.
  - **`LIGHTWEIGHT_OPERATION` with Plan checkpoint enabled** (per Work Order): same binding as FULL. The actual role set **must** include both Explorer and Planner before the checkpoint.
  - **`LIGHTWEIGHT_OPERATION` without Plan checkpoint, Planner in actual role set**: CANDIDATE_TRIPLE binds the `planner` artifact ID / version / digest that passed `PLAN_VALIDATION_PASS`, the `PLAN_VALIDATION_REPORT` verdict, and the Work Order field explicitly recording "no Plan checkpoint required". Explorer pre-validation (§4.15.2) applies.
  - **`LIGHTWEIGHT_OPERATION` without Plan checkpoint, Planner not in actual role set**: CANDIDATE_TRIPLE binds the `OPERATOR_APPROVED_WORK_ORDER` ID / version / digest, the `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`, and the Work Order field explicitly recording `direct_to_implementer=true` (or equivalent approval field), along with the approved objective, modification boundary, acceptance criteria, test / review requirements, rollback, and exclusions. The orchestrator or implementer **must not** self-authorise scope not in the Work Order.
  - **`VIBECODING_CONSULTATION_ONLY`**: does **not** produce an `IMPLEMENTATION_CANDIDATE`.

All candidates additionally bind:

  - CANDIDATE_TRIPLE ID / version / digest (or immutable tree / snapshot);
  - actual diff, file manifest, build / test entry points, known limitations, `implementer` completion report, and self-verification evidence.

If any source artifact, validation report, or operator approval status is invalidated, the CANDIDATE_TRIPLE and all downstream test, review, and Git evidence are automatically invalidated (§4.14, §4.16.6).

`CANDIDATE_FROZEN_FOR_TEST` does **not** require a pre-commit; formal commit belongs to the `git-integrator` stage (§4.16.7). Once frozen, no role **may** modify this version in-place. If a fix is needed, `implementer` must be re-activated per §4.12, producing a new attempt, new CANDIDATE_TRIPLE version, and new `ROLE_COMPLETION_REPORT`. The old CANDIDATE_TRIPLE is retained for audit; all dependent test, review, and Git evidence is invalidated per §4.14.

#### §4.16.3 Dual Tester Isolation and Charter (FULL Default)

**Mode scope.** `FULL_9_ROLE_VIBECODING`: dual tester (tester-a and tester-b) with the isolation requirements below is **mandatory**. `LIGHTWEIGHT_OPERATION`: the operator-approved actual tester / verifier role set applies; the Work Order **must not** auto-upgrade to dual tester. The same isolation principles apply to each actual tester / verifier.

`tester-a` and `tester-b` **must** each independently hold:

  - operator-approved assignment entry in `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`;
  - its own `ROLE_ACTIVATION_READINESS` (§4.10.2);
  - at least one distinct meaningful model invocation on the operator-assigned model (§4.5, §4.13);
  - independent session / context, prompt / charter, execution batch, workspace or immutable CANDIDATE_TRIPLE snapshot, commands and raw output, artifact, and `ROLE_COMPLETION_REPORT`;
  - its own attributable artifact / evidence, versioned per §4.14.

Before each tester's first report is frozen, it **must not** read the other tester's intermediate work, reports, or conclusions.

Default complementary charter (Work Order may adjust focus but **must not** reduce independence or effective coverage):

  - `tester-a`: normal functional paths, requirement acceptance, regression, compatibility, and deterministic verification;
  - `tester-b`: failure paths, boundary / exceptional input, recovery / concurrency, negative and adversarial verification.

Either tester **may** report any blocking issue; neither **may** merely "agree with the other tester". Testers operate read-only on the frozen CANDIDATE_TRIPLE. Temporary test artifacts may be produced in an isolated workspace, but testers **must not** directly modify the formal CANDIDATE_TRIPLE, business files, or tracked test files. Test changes that must enter the CANDIDATE_TRIPLE are a change demand returned to `implementer` for a new CANDIDATE_TRIPLE version.

#### §4.16.4 `TEST_EVIDENCE_PACKET` and `TEST_GATE`

**Mode scope.** `FULL_9_ROLE_VIBECODING`: `TEST_GATE` is formed by dual tester (tester-a and tester-b) with the rules below. `LIGHTWEIGHT_OPERATION`: the Gate applies to the operator-approved actual tester / verifier role set; the Work Order **must not** auto-upgrade to dual tester. Gate `PASS` requires all actual tester / verifier roles to be independently executed, `ROLE_COMPLETION_VERIFIED`, operating on the same frozen CANDIDATE_TRIPLE, with no unresolved blocker and intact evidence chain. No majority vote.

After both testers (FULL) or all actual tester / verifier roles (LIGHTWEIGHT) complete, `vibedev` performs only §4.13 cross-verification and mechanical indexing, producing a `TEST_EVIDENCE_PACKET` bound to the current CANDIDATE_TRIPLE digest. The packet contains the original reports, invocation / command results, test artifacts, coverage, blockers, and source ID / version / digest references. `vibedev` **must not** perform testing, supplement business conclusions, or choose to believe one tester over the other.

`TEST_GATE_PASS` is formed **only** when **all** of the following hold:

  - all testers / verifiers independently executed a real invocation and are `ROLE_COMPLETION_VERIFIED`;
  - all testers / verifiers operated on the same frozen CANDIDATE_TRIPLE (matching digest);
  - all applicable acceptance criteria pass;
  - no unresolved blocking defect exists;
  - independence and evidence chain are intact.

Majority vote, compromise, or orchestrator override of a `FAIL` are **forbidden**.

**Non-PASS paths:**

  - All testers / verifiers agree on a blocking issue: this is **not** a contradiction, but `TEST_GATE_PASS` **must not** be formed. Return per the Work Order's pre-approved §4.12 loop to the earliest role that can fix the root cause.
  - One or more testers / verifiers are `ROLE_COMPLETION_INCOMPLETE` / `ROLE_COMPLETION_REJECTED`: the Gate **must not** be formed. Handle per §4.12 for role completion first.
  - `TEST_CONTRADICTION_PACKET` applies **only** when two or more testers / verifiers have real, verifiable but mutually conflicting business conclusions.

**Contradiction routing by root cause:**

  - Test execution, test tool, or test methodology defect that does **not** change acceptance criteria → return to the affected tester.
  - Candidate implementation defect → return to `implementer`.
  - Planner test design, coverage, or acceptance mapping defect → return to `planner`, then determine per §4.15.3 whether a new Plan checkpoint is required.
  - Explorer fact base error → return to `explorer`; then `planner`, `PLAN_VALIDATION`, Plan checkpoint (if applicable), and all downstream dependencies re-run.
  - Root cause requires changing VC6 success criteria, scope, sub-mode, assignment, permissions, node / model / provider, or governance boundary → **STOP** and return to operator.

`vibedev` **must not** determine new acceptance criteria, supplement test design, or invent routing not pre-approved in the Work Order. `vibedev` produces only the claims–evidence contradiction packet and executes the existing routing. If the conflict cannot be resolved within budget, runtime **must** STOP.

Any re-activation of a role produces a new attempt, new formal invocation, new report, and new artifact version. When CANDIDATE_TRIPLE or packet evidence changes, §4.16.6 invalidation propagation applies.

#### §4.16.5 Dual Reviewer Isolation and `REVIEW_GATE`

**Mode scope.** `FULL_9_ROLE_VIBECODING`: dual reviewer (reviewer-a and reviewer-b) with the isolation requirements below is **mandatory**. `LIGHTWEIGHT_OPERATION`: the operator-approved actual reviewer / verifier role set applies; the Work Order **must not** auto-upgrade to dual reviewer. The same isolation principles apply to each actual reviewer / verifier.

Formal reviewer invocations **must not** overlap with tester execution. After `TEST_GATE_PASS`, `vibedev` mechanically aggregates and freezes a `REVIEW_INPUT_PACKET` binding at minimum the ID / version / digest of: Work Order / scope, approved plan, validated Explorer / Planner artifacts, current CANDIDATE_TRIPLE / diff, `TEST_EVIDENCE_PACKET`, risk / rollback, and review charter. A substantive change to any source artifact invalidates the old review.

`reviewer-a` and `reviewer-b` operate as **default parallel blind review**:

  - each independently holds assignment, `ROLE_ACTIVATION_READINESS`, distinct meaningful model invocation, independent session / context, prompt / charter, execution batch, output, evidence, and `ROLE_COMPLETION_REPORT`;
  - before each reviewer's first report is frozen, it **must not** read the other reviewer's intermediate work or conclusions.

Default complementary focus (Work Order may adjust):

  - `reviewer-a`: correctness, requirement / design consistency, maintainability, test sufficiency;
  - `reviewer-b`: security, governance boundaries, fail-closed, evidence trustworthiness, operational risk and rollback.

Either reviewer **may** report blocking items; neither **may** merely echo the other or modify the CANDIDATE_TRIPLE.

`REVIEW_GATE_PASS` is formed **only** when **all** of the following hold:

  - all reviewers / verifiers independently executed a real invocation and are `ROLE_COMPLETION_VERIFIED`;
  - all reviewers / verifiers operated on the same `REVIEW_INPUT_PACKET` and CANDIDATE_TRIPLE;
  - no unresolved blocking change demand exists;
  - provenance chain is intact.

Majority vote is **forbidden**. **Non-PASS paths** follow the same principles as §4.16.4: all reviewers / verifiers agreeing on a blocking issue does **not** form `REVIEW_GATE_PASS`; one or more reviewers / verifiers `INCOMPLETE` / `REJECTED` prevents Gate formation; `REVIEW_CONTRADICTION_PACKET` applies only when two or more reviewers / verifiers have real, verifiable but mutually conflicting conclusions. On conflict, `vibedev` produces a `REVIEW_CONTRADICTION_PACKET` listing each reviewer's claims, evidence, and conflict points. The packet is returned per §4.12 to the earliest role that can fix the root cause. If unresolved within budget, runtime declares `UNRESOLVED_REVIEW_DISAGREEMENT` and **must** STOP. `vibedev` **must not** perform review or override an evidence-backed blocking opinion.

#### §4.16.6 Invalidation and Re-Run Propagation

The following rules supplement §4.12 and §4.14:

  - CANDIDATE_TRIPLE code or runtime behaviour materially changes → FULL: both testers, both reviewers, and all Git evidence are invalidated and must be re-run; LIGHTWEIGHT: all actual tester / reviewer / verifier roles and Git evidence are invalidated and must be re-run;
  - CANDIDATE_TRIPLE plan source artifact, validation report, or operator approval status invalidated → CANDIDATE_TRIPLE and all downstream test, review, and Git evidence automatically invalidated (§4.16.2);
  - test methodology materially changes but CANDIDATE_TRIPLE unchanged → the affected tester(s) / verifier(s) re-run; once a new `TEST_EVIDENCE_PACKET` is formed, all reviewers / verifiers re-run;
  - `TEST_EVIDENCE_PACKET` or `REVIEW_INPUT_PACKET` shared evidence materially changes → all dependent gates and reports are invalidated;
  - formatting-only changes with unchanged technical meaning, evidence, and digest → only re-cross-verification is needed;
  - reviewer identifies an implementation / plan / fact defect → return respectively to `implementer` / `planner` / `explorer` per §4.14, following the Plan checkpoint dependency chain (§4.15.3).

#### §4.16.7 Git-Integrator Hard Gate

**Mode scope.** `FULL_9_ROLE_VIBECODING`: `TEST_GATE_PASS` and `REVIEW_GATE_PASS` must both be valid for the current CANDIDATE_TRIPLE before formal Git write. `LIGHTWEIGHT_OPERATION`: all `required_pre_git_gates` listed in the Work Order must be valid; the Work Order **must** explicitly list `required_pre_git_gates` and each Gate's actual role members. For any task producing a tracked diff, `required_pre_git_gates` **must not** be empty, and at least one required Gate **must** be formed and `PASS` by an independent tester / verifier / reviewer role separate from the content-author role. A missing unapproved Gate is **not** a failure, but a Work Order-required Gate **must not** be skipped. `VIBECODING_CONSULTATION_ONLY`: does **not** apply.

`git-integrator` **must not** perform any formal Git write (commit, push, Draft PR create / update) until **all** of the following hold:

  - FULL: `TEST_GATE_PASS` and `REVIEW_GATE_PASS` are both valid for the current CANDIDATE_TRIPLE; LIGHTWEIGHT: all Work Order `required_pre_git_gates` are valid;
  - all source packets and artifacts are valid (not `INVALIDATED` / `SUPERSEDED`);
  - Work Order, scope, and assignment have not drifted;
  - `git-integrator`'s own `ROLE_ACTIVATION_READINESS` (§4.10.2) has passed.

Before this point, only read-only Git capability checks in `GLOBAL_READINESS` (§4.10.1) are permitted. `git-integrator` **must not** modify business files. If the diff is out of scope or the CANDIDATE_TRIPLE requires change, return to the responsible role.

If the task produces a tracked diff but `git-integrator` is not in the actual role set, the Work Order **must** be corrected before execution; runtime **must not** auto-add `git-integrator`.

#### §4.16.8 Default Git Delivery Pipeline (by Mode)

**FULL default chain:**

```
REVIEW_GATE_PASS
  → git-integrator ROLE_ACTIVATION_READINESS (§4.10.2)
  → GIT_INTEGRATION_INPUT_FROZEN (§4.16.9)
  → exact-stage / preflight (§4.16.10)
  → ordinary commit (§4.16.10)
  → COMMIT_TREE_MATCHES_FROZEN_CANDIDATE (§4.16.10)
  → push / remote verification (§4.16.11)
  → Draft PR create-or-update (§4.16.12)
  → DRAFT_PR_DELIVERY_VERIFIED (§4.16.12)
  → STOP
```

**LIGHTWEIGHT:** same chain except `required_pre_git_gates` (per Work Order) replaces FULL dual Gate. All Git delivery principles below apply identically.

**VIBECODING_CONSULTATION_ONLY:** does **not** execute Git / PR.

#### §4.16.9 `GIT_INTEGRATION_INPUT_PACKET` and `INTEGRATION_INPUT_FROZEN`

`git-integrator` **must** version and freeze a `GIT_INTEGRATION_INPUT_PACKET` before any Git write. The packet **must** bind at minimum:

  - Work Order ID / version / digest, `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE` ID / version / digest, and approved plan source (per §4.16.2);
  - current `IMPLEMENTATION_CANDIDATE` ID / version / digest, immutable content manifest (file list, paths, expected tree digest);
  - mode-appropriate Gate verdicts and Test / Review / evidence packet references;
  - expected repository, remote, base branch / base SHA, target branch, expected target head;
  - branch creation permission, commit count / message plan, Draft PR title / body schema;
  - approved push / PR API recovery budget (§4.16.11) and allowed routes;
  - `PUBLIC_SAFE_EVIDENCE_PROJECTION_DRAFT` or equivalent pre-commit evidence draft (§4.16.10).

If any source artifact is invalidated, scope or assignment drifts, or the packet content changes, `INTEGRATION_INPUT_FROZEN` is automatically invalidated and `git-integrator` **must not** proceed.

#### §4.16.10 Git-Integrator Scope and Commit Discipline

`git-integrator` is **limited** to:

  - verifying input integrity and freezing the integration input packet;
  - creating an operator-approved ordinary commit (one commit per CANDIDATE_TRIPLE by default);
  - pushing to the approved remote / branch;
  - creating or updating the single matching Draft PR;
  - verifying local / remote commit, tree, PR state, and evidence;
  - submitting a `GIT_INTEGRATION_COMPLETION_REPORT`.

`git-integrator` **must not**:

  - modify business, test, or configuration files;
  - fix the CANDIDATE_TRIPLE, patch defects, or supplement Test / Review conclusions;
  - change file mode, path, symlink, or submodule pointer;
  - decide on multi-commit splitting at runtime;
  - auto-amend, rebase, reset, force-push, merge, Ready, or delete branch.

If the diff is out of scope, content needs change, or the manifest does not match, return to the responsible role for a new CANDIDATE_TRIPLE and re-run the dependency chain.

**Exact staging.** The CANDIDATE_TRIPLE manifest **must** distinguish:

  - approved existing tracked changes (modifications to tracked files);
  - approved deletions and renames;
  - approved new paths (files that are untracked before staging but approved in the CANDIDATE_TRIPLE manifest).

`git-integrator` **must** stage paths individually per the manifest and verify **before** commit:

  - staged path set matches manifest exactly — neither omitting approved new files nor swallowing extra files;
  - staged diff / tree digest matches CANDIDATE_TRIPLE;
  - deletions, renames, and file modes are correct;
  - no extra tracked modifications exist;
  - no untracked paths outside the manifest are staged — the task entry-time untracked inventory and Work Order-protected paths are the reference; the current construction workspace's specific untracked paths are a historical fact of this PR, **not** a universal runtime constant;
  - `git add .`, `git add -A`, and `git commit -am` are **forbidden**.

**Default: one CANDIDATE_TRIPLE → one ordinary commit.** Multi-commit is allowed **only** when the Work Order and approved Plan explicitly pre-define commit count, file boundaries, order, and messages. The final tree **must** still match the frozen CANDIDATE_TRIPLE. `git-integrator` **must not** decide commit splitting at runtime.

**Commit message evidence consistency (two-phase).** Before committing, `git-integrator` **must** freeze a `PUBLIC_SAFE_EVIDENCE_PROJECTION_DRAFT` (or equivalent pre-commit evidence draft) containing all determinable fields **except** commit SHA / tree and post-push / PR facts. The draft binds:

  - Work Order / task / run / sub-mode, objective, scope / exclusions;
  - base branch / expected base SHA;
  - target branch;
  - CANDIDATE_TRIPLE ID / version / digest, expected tree digest;
  - plan source (mode-appropriate per §4.16.12);
  - actual role set, Gate verdicts, test / review evidence references;
  - changed files, diffstat, behavioural change, explicitly unmodified scope;
  - test commands / return code / pass-fail summary, review verdict, final loop version;
  - risks, limitations, rollback, and open items;
  - explicit `PR remains DRAFT` statement.

`COMMIT_MESSAGE_EVIDENCE_CONSISTENCY_CHECK` runs against this draft, the CANDIDATE_TRIPLE, Gate verdicts, and test evidence — **not** against the final PR body (which does not yet exist).

After commit, `git-integrator` fills in the newly generated commit SHA / tree, remote / PR facts, and other Git-derived fields to form the final `DRAFT_PR_EVIDENCE_BODY` (§4.16.12).

After push / PR, re-verify consistency between commit message, final PR body, diffstat, test numbers, and Gate status. If substantive inconsistency is discovered, **immediate STOP** — operator decides the subsequent scope. Do **not** amend the commit message after commit.

**Candidate–commit tree binding.** After commit, `git-integrator` **must** verify:

  - `final commit tree == frozen CANDIDATE_TRIPLE content tree`.

Only Git metadata (commit SHA, parent, message, author / committer time, signature) may differ. File content, path, additions / deletions, file mode, symlink, line endings / encoding, and submodule pointers **must not** change.

Success: `COMMIT_TREE_MATCHES_FROZEN_CANDIDATE`.
Mismatch: `CANDIDATE_COMMIT_TREE_MISMATCH` — **immediate STOP**. `git-integrator` **must not** self-correct.

#### §4.16.11 Branch / Base / Remote Drift and Bounded Push Recovery

**Pre-write drift check.** Before any Git write, `git-integrator` **must** verify repository, remote, identity, base SHA, target branch / head, worktree, locks, and PR occupancy. The following **must not** be auto-absorbed:

  - base changed;
  - target branch has unknown commits;
  - remote head != expected head;
  - non-fast-forward required;
  - existing PR base / head / task identity conflict;
  - same branch occupied by another task.

States:

  - `REMOTE_BASE_DRIFT` — **immediate STOP**, operator decides new Work Order, re-validation, or termination.
  - `REMOTE_TARGET_HEAD_DRIFT` — **immediate STOP**, same handling.
  - `NON_FAST_FORWARD_REQUIRED` — **immediate STOP**, same handling.

Auto-rebase, merge, reset, or force-push are **forbidden**.

**Bounded push / PR API recovery.** The Work Order may default-approve:

  - push: max 3 attempts;
  - Draft PR create / update API: max 3 attempts;
  - same remote, branch, commit, credential identity only;
  - **proxy bypass budget: across the entire Git delivery operation, at most one command-level `-c http.proxy=""` bypass attempt is permitted.** This single budget is shared by push and all PR-API-related Git / HTTP delivery actions and is **not** renewed per retry;
  - **no** persistent proxy modification, token / account / remote switch, or credential identity change.

The bypass attempt, when used, **must** be recorded: attempt, command class (push / PR API), and result. Budget exhaustion followed by another failure is **immediate STOP**.

On push timeout, TLS disconnect, or indeterminate result, **first** read the remote head:

  - remote head == local commit → `PUSH_DELIVERY_VERIFIED` (delivery confirmed);
  - remote head still == expected old head → one more approved attempt;
  - remote head is another SHA or indeterminate → **immediate STOP**.

Authentication failure, permission denied, credential missing / not loaded, branch protection, remote inconsistency, and non-fast-forward are **hard STOP** — not transport retries.

**PR API recovery.** Before each Draft PR create / update API retry, **first** query the PR by repository, head / base branch, and Work Order / task identity:

  - **create retry:** if a unique OPEN + DRAFT PR already exists with the correct head / base, verify its body and evidence version; if consistent, treat as successful (`PR_DRAFT_CREATED`). If no match yet exists, one more create attempt is permitted. Multiple matches, indeterminate state, or head / base mismatch → **immediate STOP**.
  - **update retry:** if the target PR already reflects the expected body / evidence version, treat as successful (`PR_DRAFT_UPDATED`). If still the verified old version, one more update attempt is permitted. Unexpected version, head / base drift, or indeterminate state → **immediate STOP**.

Blind repeated create / update, duplicate PR creation, or overwriting unknown updates are **forbidden**.

States:

  - `PUSH_TRANSPORT_RECOVERY_IN_PROGRESS`
  - `PUSH_DELIVERY_VERIFIED`
  - `PUSH_RECOVERY_BUDGET_EXHAUSTED`
  - `UNVERIFIED_PR_API_RETRY`
  - `PR_API_RECOVERY_BUDGET_EXHAUSTED` — PR create / update API retry budget (max 3 attempts) exhausted. **Immediate STOP**. No fourth attempt permitted. Distinct from `UNVERIFIED_PR_API_RETRY`, which is retry without prior state query.
  - `PROXY_BYPASS_BUDGET_EXCEEDED` — additional `-c http.proxy=""` bypass attempt beyond the single shared budget for the entire Git delivery operation. **Immediate STOP.**

#### §4.16.12 Draft PR Identification, Public Evidence Body, and Delivery Verification

**PR identification.** Locate the PR by repository, head / base branch, and Work Order / task identity:

  - no match → create Draft PR;
  - single match, OPEN + DRAFT → update;
  - multiple matches, already Ready, closed / merged, base mismatch, or occupied by another task → **immediate STOP**.

**`PUBLIC_SAFE_EVIDENCE_PROJECTION` and `DRAFT_PR_EVIDENCE_BODY`.** The PR body **must** contain:

  - Work Order / task / run / sub-mode, objective, scope / exclusions;
  - base and head branch and SHA;
  - CANDIDATE_TRIPLE ID / version / digest, commit SHA / tree, CANDIDATE_TRIPLE→commit tree consistency;
  - plan source (mode-appropriate): FULL / LIGHTWEIGHT with Plan checkpoint → plan source, approval packet, and `OPERATOR_APPROVED_IMPLEMENTATION_PLAN` reference; LIGHTWEIGHT with Planner but no checkpoint → planner artifact, `PLAN_VALIDATION_REPORT`, and Work Order no-checkpoint approval field; LIGHTWEIGHT direct-to-implementer without Planner → `OPERATOR_APPROVED_WORK_ORDER`, assignment baseline, and `direct_to_implementer=true` provenance. Inapplicable approval types **must not** be fabricated; only the mode-appropriate source is recorded;
  - actual role set, Explorer / Planner validation, FULL dual Gate or LIGHTWEIGHT required Gates;
  - changed files, diffstat, behavioural change, explicitly unmodified scope;
  - test commands / return code / pass-fail summary, review verdict, final loop version;
  - risks, limitations, rollback, and open items;
  - explicit statements: `PR remains DRAFT`, `Draft-to-Ready is not authorised`, `Merge is not authorised`.

**Public safety.**

**`PUBLIC_SAFE_GIT_METADATA_CHECK`.** All public-facing Git metadata **must** pass a public-safety check **before** the action that would make it public:

  - branch name — before creation or first public exposure;
  - commit message — before commit;
  - PR title and the pre-commit `PUBLIC_SAFE_EVIDENCE_PROJECTION_DRAFT` — before PR create / update API call;
  - final `DRAFT_PR_EVIDENCE_BODY` — before API submit and re-verified after submit.

The check covers at minimum: credentials or derived features, tokens / cookies / headers, sensitive env values, internal model prompts, private logs, unapproved public host / IP / username details, local absolute paths, and private data. Any public metadata failing the check **must** trigger **immediate STOP** before the public action; cleaning after commit / push / create / update is **forbidden**. `git-integrator` and `vibedev` **must not** alter technical facts to pass the check.

The PR body **must not** contain: credentials or derived features, tokens / cookies / headers, full private logs, unapproved IP / username / host details, local absolute paths, sensitive env values, internal model raw prompts, or private data. `vibedev` may verify projection fidelity but **must not** fabricate technical conclusions.

**Post-push independent verification.** `git-integrator` **must not** rely on push rc=0 or API success alone. At minimum verify:

  1. remote head == local commit;
  2. remote commit tree == local tree;
  3. commit tree == frozen CANDIDATE_TRIPLE;
  4. remote diff only manifest paths;
  5. PR is OPEN + DRAFT;
  6. PR head SHA == remote head, base correct;
  7. PR body binds current CANDIDATE_TRIPLE / commit / Gate versions (pre-commit draft → post-commit final body);
  8. commit message, final PR body, diffstat, and test numbers consistent (two-phase: pre-commit draft → post-commit final body, re-verified after push/PR);
  9. no Ready, merge, branch deletion, or extra file side effects.

Pass: `DRAFT_PR_DELIVERY_VERIFIED`.

#### §4.16.13 `GIT_INTEGRATION_COMPLETION_REPORT` and Automatic Endpoint

The `GIT_INTEGRATION_COMPLETION_REPORT` **must** record:

  - assignment / Activation, Integration Packet version;
  - CANDIDATE_TRIPLE / manifest / stage verification;
  - commit SHA / tree / parent / message;
  - push and PR API each attempt, classification, remote verification, and proxy bypass;
  - PR number, state, isDraft, base, head, body digest;
  - public-safe evidence check (pre-commit draft + post-commit final body);
  - untouched files, final `git status`, completion claim.

`vibedev` cross-verifies per §4.13. Only after pass:

  - `PR_DRAFT_CREATED` or `PR_DRAFT_UPDATED`
  - `DRAFT_PR_DELIVERY_VERIFIED`
  - `WORK_ORDER_AUTOMATIC_ENDPOINT_REACHED`

Then **immediate STOP**. No further correction, push, Ready, merge, or new loop.

**Draft → Ready boundary (placeholder — see §4.16.14).**

#### §4.16.14 Post-Draft Termination and Operator Decision Space

After the chain `DRAFT_PR_DELIVERY_VERIFIED → WORK_ORDER_AUTOMATIC_ENDPOINT_REACHED → STOP` (§4.16.13), the original Work Order's automatic-execution authority **terminates**. `vibedev` / `git-integrator` **must not** continue:

  - modify the CANDIDATE_TRIPLE;
  - push;
  - update the Draft PR body or evidence;
  - start any role loop;
  - Draft → Ready transition;
  - merge;
  - delete the branch.

Operator viewing the PR, commenting, silence, or general acknowledgement do **not** constitute any subsequent authorisation. Subsequent actions are limited to the operator's explicit choice among:

  - request Draft modification (requires new operator decision and execution scope; artifact invalidation re-runs required roles, Gates, and Git delivery);
  - keep the Draft;
  - close / abandon the task;
  - launch an independent `Draft → Ready` authorisation flow (§4.16.15).

Substantive CANDIDATE_TRIPLE modification after Draft requires a new operator decision and explicit execution scope; artifacts are re-invalidated and required roles / Gates / Git delivery are re-run.

**Body / evidence metadata-only correction** may use an independent `EVIDENCE_METADATA_CORRECTION_OPERATION` and must prove:

  - head SHA and CANDIDATE_TRIPLE unchanged;
  - the correction is grounded in already-trusted factual evidence (no invented technical conclusion);
  - the `PUBLIC_SAFE_GIT_METADATA_CHECK` re-passes;
  - a new body / evidence version is produced.

Any pre-existing Ready / Merge authorisation is **automatically invalidated** by such a correction.

**`POST_DRAFT_GIT_INTEGRATOR_BINDING`.** Each Post-Draft operation (Ready, Merge, Branch Deletion) requires its own executor binding:

  - `OPERATOR_AUTHORIZED_DRAFT_TO_READY`, `OPERATOR_AUTHORIZED_MERGE`, and `OPERATOR_AUTHORIZED_BRANCH_DELETION` **must** each bind a `POST_DRAFT_GIT_INTEGRATOR_BINDING` (or equivalent field);
  - at minimum: original `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE` ID / version / digest; git-integrator role identity; node; model; canonical provider; runtime provider; credential identity; permitted permissions; this operation's type (Ready / Merge / Branch Deletion);
  - reuse of the original git-integrator assignment is permitted **only** when operator explicitly approves reuse and **all** of role identity / node / model / provider / credential identity / permissions are unchanged. The mere termination of the original Work Order **must not** be interpreted as automatic continuation of execution authority;
  - any change to role / node / model / provider / credential identity / permission **immediately invalidates** the authorisation and forces **immediate STOP**; a new operator-approved binding is required;
  - each Post-Draft operation **must** have a new `ROLE_ACTIVATION_READINESS`, a new attempt ID, a formal and attributable role invocation, and an independent completion evidence packet. The Draft delivery attempt and its report **must not** be reused.

#### §4.16.15 Draft → Ready Approval Packet and Authorisation

**Approval packet generation.** `vibedev` read-only generates a versioned `DRAFT_TO_READY_APPROVAL_PACKET` binding at minimum:

  - repository, PR number, OPEN + DRAFT state;
  - base branch / base SHA, head branch / head SHA;
  - PR body / evidence ID / version / digest;
  - CANDIDATE_TRIPLE ID / version / digest and commit-tree consistency;
  - actual role set, FULL dual Gate or LIGHTWEIGHT required Gates;
  - current mergeability / conflict, required checks / CI state;
  - unresolved warnings / blockers, public-safe check result;
  - disclosed construction / runtime deviations and impact analysis;
  - recommendation, risks, and explicitly unexecuted items.

`vibedev` **must only** verify and faithfully aggregate; it **must not** approve Ready on the operator's behalf and **must not** declare that historical deviations do not affect Ready.

**Authorisation binding.** Operator's explicit approval forms `OPERATOR_AUTHORIZED_DRAFT_TO_READY`, binding at minimum:

  - repository, PR number;
  - approved base branch / base SHA;
  - approved head SHA;
  - approved PR body / evidence ID / version / digest;
  - `DRAFT_TO_READY_APPROVAL_PACKET` ID / version / digest;
  - authorization time;
  - operator-explicit `known_deviations_accepted` list; deviations **not** listed are **not** accepted.

Any of the following changes **automatically invalidates** the authorisation:

  - head, base, body / evidence, or approval packet change;
  - Gate / checks / mergeability invalidated or new blocker appears;
  - PR no longer OPEN + DRAFT;
  - remote / branch drift;
  - public evidence safety or consistency failure;
  - operator revokes authorisation.

Historical verbal approval **must not** override version changes.

#### §4.16.16 Ready Execution Chain

**Default chain (Ready — explicit mutually-exclusive branches):**

```
OPERATOR_AUTHORIZED_DRAFT_TO_READY
  (must bind POST_DRAFT_GIT_INTEGRATOR_BINDING)
  → git-integrator ROLE_ACTIVATION_READINESS (§4.10.2)
  → READY_FINAL_PREFLIGHT (§4.16.16)
  → GitHub status change
  → READY_DELIVERY_VERIFICATION (§4.16.16)
  → READY_TRANSITION_COMPLETION_REPORT (§4.16.16)
  → vibedev cross-verification (§4.13)
  → fork (mutually-exclusive):
       PASS_CLAIM branch: PR_READY_VERIFIED → STOP
       FAIL_CLAIM branch: READY_TRANSITION_VERIFICATION_FAIL → STOP
```

The `PASS_CLAIM` branch and the `FAIL_CLAIM` branch are **mutually exclusive**: only one is taken after `vibedev` cross-verification. The chain must not be rendered as a single linear STOP-after-PASS-after-FAIL sequence.

**`READY_FINAL_PREFLIGHT` must re-verify:**

  - authorisation is real, exactly matches, and is not invalidated;
  - PR is still OPEN + DRAFT, head / base / body digest match approved values;
  - CANDIDATE_TRIPLE, Gates, checks, and evidence remain valid;
  - no unresolved blockers or unknown updates;
  - public-safe metadata still passes;
  - no other task occupies or modifies the PR.

Non-PASS states — each **immediate STOP**; may not move to Ready, may not refresh authorisation, may not self-fix:

  - `DRAFT_TO_READY_AUTHORIZATION_STALE`
  - `READY_REMOTE_DRIFT`
  - `READY_CHECKS_INVALIDATED`
  - `READY_BLOCKER_DETECTED`

**Ready API retry.** On indeterminate result, **first** query the PR's actual state before retry:

  - already OPEN with `isDraft=false`, head / base / body match approved → treat as success;
  - still the verified OPEN + DRAFT old state → one more approved retry permitted;
  - any other state or indeterminate → **immediate STOP**.

Default: Ready API max 2 attempts. Blind retry forbidden.

**Post-Ready verification.** Must verify beyond API rc:

  - PR is OPEN and `isDraft=false`;
  - head / base / body unchanged;
  - no commit, push, merge, branch deletion, or other side effects.

After Post-Ready verification completes, only the following may be recorded:

  - raw evidence;
  - observed result;
  - **`READY_TRANSITION_PASS_CLAIM`** or **`READY_TRANSITION_FAIL_CLAIM`** (pending completion report and cross-verification).

The verified endpoint state **must not** be formed at this stage. The next required step is to generate `READY_TRANSITION_COMPLETION_REPORT` (see below) and pass it through `vibedev` cross-verification (§4.13). Ready **never** includes merge authorisation.

**`READY_TRANSITION_COMPLETION_REPORT`.** Must record at minimum:

  - `OPERATOR_AUTHORIZED_DRAFT_TO_READY` ID / version / digest and `POST_DRAFT_GIT_INTEGRATOR_BINDING` ID / version / digest;
  - git-integrator `ROLE_ACTIVATION_READINESS` result and attempt ID;
  - **`READY_TRANSITION_ROLE_INVOCATION` ID / version / digest, formal and attributable git-integrator role invocation evidence, input digest, output digest, timestamp, raw evidence references** (this invocation is **independent** of the Draft delivery invocation and any other Post-Draft invocation; it **must not** be reused);
  - `READY_FINAL_PREFLIGHT` result and version;
  - Ready API attempts: count, each result, indeterminate-result state query, budget consumption;
  - pre-change and post-change PR state / isDraft / head / base / body digest;
  - confirmation: no commit, push, merge, branch deletion, or unknown side effect;
  - `PUBLIC_SAFE_GIT_METADATA_CHECK` result;
  - **PASS / FAIL claim** (`READY_TRANSITION_PASS_CLAIM` or `READY_TRANSITION_FAIL_CLAIM`) and unexecuted operations;
  - final completion claim.

`POST_DRAFT_FORMAL_INVOCATION_EVIDENCE_MISSING` — a Post-Draft `*_COMPLETION_REPORT` lacks the formal and attributable role invocation evidence, or the invocation ID / input / output / timestamp / references cannot be independently verified, or the invocation is reused from Draft delivery or another Post-Draft operation (§4.16.16, §4.16.17). The completion report **must not** pass cross-verification when this drift signal applies. **Immediate STOP.** [signal_kind=DRIFT_STOP]

**Verified endpoint state formation rules.**

  - `READY_TRANSITION_PASS_CLAIM` and the completion report passes `vibedev` cross-verification → `PR_READY_VERIFIED`, then **immediate STOP**.
  - `READY_TRANSITION_FAIL_CLAIM` and the completion report passes `vibedev` cross-verification → `READY_TRANSITION_VERIFICATION_FAIL`, then **immediate STOP**. No success endpoint may be formed.
  - Completion report cannot be produced with credible evidence (e.g. evidence infrastructure failure) → existing hard STOP code path applies; no `PR_READY_VERIFIED` or `READY_TRANSITION_VERIFICATION_FAIL` may be fabricated.

`vibedev` performs only cross-verification (§4.13); it **must not** execute the status change, fabricate missing evidence, fabricate results, or treat missing evidence as PASS. A successful API return or single state query **must not** substitute for the completion report and cross-verification.

`READY_VERIFIED_PREMATURE` — `PR_READY_VERIFIED` formed before `READY_TRANSITION_COMPLETION_REPORT` passes `vibedev` cross-verification (§4.16.16). **Immediate STOP.**

#### §4.16.17 Merge Approval Packet, Authorisation, Execution, and Post-Merge

**Post-Ready boundary.** After `PR_READY_VERIFIED`, runtime **must** wait for operator to re-review the latest Ready PR. The Ready authorisation **must not** be reused for merge. Ready success **must not** be interpreted as merge permission.

**Merge packet generation gate.** `vibedev` **must not** automatically generate `MERGE_APPROVAL_PACKET` after `PR_READY_VERIFIED`. The packet is generated **only** after operator explicitly requests merge assessment / packet preparation and is treated as a fresh, independent decision. Read-only packet generation is **not** an extension of the Ready authorisation and is **not** a merge authorisation. An operator request to generate the packet alone **does not** equal merge authorisation.

**`MERGE_APPROVAL_PACKET`.** `vibedev` read-only generates, binding at minimum:

  - PR number, current head / base SHA, OPEN + Ready state;
  - mergeability / conflict, required checks / CI, Gate / evidence validity;
  - unresolved blockers, diffstat, CANDIDATE_TRIPLE / tree ↔ PR evidence consistency;
  - known deviations, risks, limitations;
  - recommended merge method and rationale;
  - expected result, method-specific verification, post-merge verification plan;
  - `branch deletion=false`.

**`OPERATOR_AUTHORIZED_MERGE`.** Operator approval binds:

  - repository, PR number;
  - approved head / base SHA;
  - explicit merge method;
  - packet ID / version / digest;
  - expected checks state;
  - authorization time;
  - accepted deviations.

Runtime **must not** self-select method; `MERGE_COMMIT` may be recommended, but merge without an explicit operator-approved method is forbidden. Any change to head / base / body / evidence / checks / mergeability / blocker / method / remote state, or operator revocation, invalidates the authorisation.

**Default chain (Merge — explicit mutually-exclusive branches):**

```
OPERATOR_AUTHORIZED_MERGE
  (must bind POST_DRAFT_GIT_INTEGRATOR_BINDING)
  → git-integrator ROLE_ACTIVATION_READINESS (§4.10.2)
  → MERGE_FINAL_PREFLIGHT (§4.16.17)
  → merge API
  → method-specific verification evidence
  → post-merge verification execution / evidence
  → MERGE_COMPLETION_REPORT
  → vibedev cross-verification (§4.13)
  → fork (mutually-exclusive):
       PASS_CLAIM branch: MERGE_DELIVERY_VERIFIED
                            → POST_MERGE_VERIFICATION_PASS
                            → MERGE_OPERATION_ENDPOINT_REACHED → STOP
       FAIL_CLAIM branch: POST_MERGE_VERIFICATION_FAIL → STOP
```

Before `MERGE_COMPLETION_REPORT` passes cross-verification, only `observed result`, `claimed result`, or `raw evidence` may be recorded; `MERGE_DELIVERY_VERIFIED`, `POST_MERGE_VERIFICATION_PASS`, `POST_MERGE_VERIFICATION_FAIL`, and the merge endpoint **must not** be formed prematurely.

The `PASS_CLAIM` branch and the `FAIL_CLAIM` branch are **mutually exclusive**: only one is taken after `vibedev` cross-verification. The chain must not be rendered as a single linear STOP-after-PASS-after-FAIL sequence.

**`MERGE_FINAL_PREFLIGHT` must confirm:**

  - PR still OPEN + Ready;
  - head / base / method / checks / Gate / evidence / authorisation all match;
  - no new blocker, no unknown body change, no target drift.

STOP states (no auto-update-base, rebase, retest-then-continue, or method switch):

  - `MERGE_AUTHORIZATION_STALE`
  - `MERGE_REMOTE_DRIFT`
  - `MERGE_CHECKS_INVALIDATED`
  - `MERGE_BLOCKER_DETECTED`

**Merge API retry.** Default max 2 attempts. On indeterminate result, first query PR and target:

  - already `MERGED` with approved method → verify then treat as success;
  - still the verified old state → one more approved retry;
  - other SHA, unknown state, or unverifiable → **immediate STOP**.

Blind repeated merge is forbidden.

**Method-specific verification:**

  - `MERGE_COMMIT`: parent1 = approved pre-merge base, parent2 = approved PR head, tree = expected merged tree;
  - `SQUASH_MERGE`: target tree, approved message, PR → head traceability;
  - `REBASE_MERGE`: rewritten sequence, target tree, PR traceability; forbidden without explicit selection.

**Post-merge verification.** Verify PR = MERGED, merge commit / target head exist, CANDIDATE_TRIPLE reaches target, no extra files / unknown commits, method-specific verification passes, branch retained, no duplicate PR or unknown side effect. Then execute the post-merge verification pre-listed in the packet.

After Post-merge verification (method-specific + post-merge checks) completes, only the following may be recorded:

  - raw evidence (method-specific verification, post-merge verification plan results, target head / tree, etc.);
  - observed result;
  - **`POST_MERGE_VERIFICATION_PASS_CLAIM`** or **`POST_MERGE_VERIFICATION_FAIL_CLAIM`** (pending completion report and cross-verification).

The verified PASS / FAIL endpoint state **must not** be formed at this stage. The next required step is to generate `MERGE_COMPLETION_REPORT` and pass it through `vibedev` cross-verification (§4.13).

**Verified PASS / FAIL endpoint state formation rules (mutually-exclusive branches).** Only one branch is taken after `vibedev` cross-verification of `MERGE_COMPLETION_REPORT`:

  - **PASS_CLAIM branch** — `POST_MERGE_VERIFICATION_PASS_CLAIM` and the completion report passes `vibedev` cross-verification → `MERGE_DELIVERY_VERIFIED` + `POST_MERGE_VERIFICATION_PASS` → `MERGE_OPERATION_ENDPOINT_REACHED` → **immediate STOP**.
  - **FAIL_CLAIM branch** — `POST_MERGE_VERIFICATION_FAIL_CLAIM` and the completion report passes `vibedev` cross-verification → `POST_MERGE_VERIFICATION_FAIL` → **immediate STOP**. No success endpoint may be formed.
  - **Mutual exclusivity**: PASS and FAIL are **exclusive branches**; FAIL does **not** form `MERGE_DELIVERY_VERIFIED` / `POST_MERGE_VERIFICATION_PASS` / `MERGE_OPERATION_ENDPOINT_REACHED`.
  - **Insufficient evidence**: completion report cannot be produced with credible evidence (e.g. evidence infrastructure failure) → existing hard STOP code path applies; `POST_MERGE_VERIFICATION_FAIL` or any PASS state **must not** be fabricated.

Auto-revert, auto-fix, follow-up commit, or second merge is forbidden regardless of PASS / FAIL outcome.

**`MERGE_COMPLETION_REPORT`.** Must record at minimum:

  - `MERGE_APPROVAL_PACKET` ID / version / digest;
  - `OPERATOR_AUTHORIZED_MERGE` ID / version / digest and `POST_DRAFT_GIT_INTEGRATOR_BINDING` ID / version / digest;
  - git-integrator `ROLE_ACTIVATION_READINESS` result and attempt ID;
  - **`MERGE_ROLE_INVOCATION` ID / version / digest, formal and attributable git-integrator role invocation evidence, input digest, output digest, timestamp, raw evidence references** (this invocation is **independent** of the Draft delivery invocation and any other Post-Draft invocation; it **must not** be reused);
  - `MERGE_FINAL_PREFLIGHT` result and version;
  - merge method, merge API attempts: count, each result, indeterminate-result query, budget consumption;
  - pre-merge base SHA and PR head SHA;
  - merge commit SHA and target head SHA;
  - method-specific verification (parent / tree / sequence, as applicable);
  - **post-merge verification**: `MERGE_APPROVAL_PACKET` pre-approved post-merge verification plan ID / version / digest;
  - **post-merge verification**: actually-executed read-only checks / tests, timestamps, commands or actions, return codes, raw artifact / evidence references;
  - **post-merge verification**: expected target head / tree vs actual target head / tree;
  - **post-merge verification**: method-specific verification results;
  - **post-merge verification**: post-merge acceptance criteria — item-by-item results;
  - **`POST_MERGE_VERIFICATION_PASS_CLAIM` or `POST_MERGE_VERIFICATION_FAIL_CLAIM`** and operations **not** executed (the report records the **CLAIM** only; final `POST_MERGE_VERIFICATION_PASS` / `POST_MERGE_VERIFICATION_FAIL` state names must **not** appear in the report — they are formed only after cross-verification);
  - final PR state = `MERGED`;
  - CANDIDATE_TRIPLE reached target;
  - no extra files / unknown commits;
  - `PUBLIC_SAFE_GIT_METADATA_CHECK` result;
  - source branch retention state;
  - operations **not** executed and final completion claim.

`vibedev` performs only cross-verification (§4.13); it **must not** execute the merge, fabricate missing tests, fabricate results, or treat missing evidence as PASS. The verified PASS / FAIL endpoint state must be formed only after the report passes cross-verification. PASS path yields `MERGE_DELIVERY_VERIFIED` + `POST_MERGE_VERIFICATION_PASS` → `MERGE_OPERATION_ENDPOINT_REACHED`. FAIL path yields `POST_MERGE_VERIFICATION_FAIL`. The two paths are mutually exclusive and both terminate with **immediate STOP**.

**Branch deletion — independent execution chain.**

```
OPERATOR_AUTHORIZED_BRANCH_DELETION
  (must bind POST_DRAFT_GIT_INTEGRATOR_BINDING)
  → ROLE_ACTIVATION_READINESS (§4.10.2)
  → BRANCH_DELETION_FINAL_PREFLIGHT (§4.16.17)
  → delete API
  → post-delete verification evidence
  → BRANCH_DELETION_COMPLETION_REPORT
  → vibedev cross-verification (§4.13)
  → BRANCH_DELETION_VERIFIED
  → BRANCH_DELETION_OPERATION_ENDPOINT_REACHED → STOP
```

Before `BRANCH_DELETION_COMPLETION_REPORT` passes cross-verification, only `observed result`, `claimed result`, or `raw evidence` may be recorded; `BRANCH_DELETION_VERIFIED` and the branch-deletion endpoint **must not** be formed prematurely.

The authorisation **must** bind at minimum: repository, source branch, PR number, merged PR head, merge commit / target head, `POST_DRAFT_GIT_INTEGRATOR_BINDING`, authorization time.

**Default-off policy.** Source branch deletion is **not** performed by default. Deletion requires a separate `OPERATOR_AUTHORIZED_BRANCH_DELETION` explicitly approved by the operator; without this authorisation, no delete API call may be made.

**`BRANCH_DELETION_FINAL_PREFLIGHT` must verify:**

  - PR is `MERGED` and merge / post-merge evidence is valid;
  - source branch still points to the approved merged head;
  - target / merge commit matches the authorisation;
  - branch is not reused, advanced, or occupied by another task.

**Branch deletion API retry.** Default max 2 attempts. On indeterminate result, first query the ref:

  - source ref already gone (verified) → treat as success;
  - still the verified old ref → one more approved retry permitted;
  - other state, unknown, or unverifiable → **immediate STOP**.

**Post-deletion verification.** Verify source ref does not exist, target unchanged, PR / merge record unchanged, no other branch side effects. Deletion of base / target branch is **forbidden**.

**State names:**

  - `BRANCH_DELETION_AUTHORIZATION_STALE` — authorisation no longer matches repo / branch / PR / merged head / merge commit / executor binding / time. **Immediate STOP.**
  - `BRANCH_DELETION_TARGET_MISMATCH` — source branch target / merge commit drift. **Immediate STOP.**
  - `UNVERIFIED_BRANCH_DELETION_RETRY` — retry without prior ref query. **Immediate STOP.**
  - `BRANCH_DELETION_API_RECOVERY_BUDGET_EXHAUSTED` — 2-attempt budget exhausted or status unverifiable. **Immediate STOP.**
  - `BRANCH_DELETION_COMPLETION_UNVERIFIED` — `BRANCH_DELETION_VERIFIED` claimed without passing `BRANCH_DELETION_COMPLETION_REPORT` cross-verification (§4.16.17). **Immediate STOP.**
  - `BRANCH_DELETION_ENDPOINT_PREMATURE` — `BRANCH_DELETION_OPERATION_ENDPOINT_REACHED` formed before `BRANCH_DELETION_COMPLETION_REPORT` passes cross-verification (§4.16.17). **Immediate STOP.**
  - Success: `BRANCH_DELETION_VERIFIED` (only after `BRANCH_DELETION_COMPLETION_REPORT` passes cross-verification), then `BRANCH_DELETION_OPERATION_ENDPOINT_REACHED`, then **immediate STOP**.

**`BRANCH_DELETION_COMPLETION_REPORT`.** Must record at minimum:

  - `OPERATOR_AUTHORIZED_BRANCH_DELETION` ID / version / digest;
  - `POST_DRAFT_GIT_INTEGRATOR_BINDING` ID / version / digest;
  - git-integrator `ROLE_ACTIVATION_READINESS` result and attempt ID;
  - **`BRANCH_DELETION_ROLE_INVOCATION` ID / version / digest, formal and attributable git-integrator role invocation evidence, input digest, output digest, timestamp, raw evidence references** (this invocation is **independent** of the Draft delivery invocation, the Ready invocation, the Merge invocation, and any other Branch Deletion attempt; it **must not** be reused);
  - `BRANCH_DELETION_FINAL_PREFLIGHT` result and version;
  - delete API attempts: count, each result, indeterminate-result prior ref query, budget consumption;
  - pre-delete: source ref, approved head, merge commit / target head;
  - post-delete: source ref does not exist, target unchanged, PR / merge record unchanged;
  - no other branch side effects, base / target branch **not** deleted;
  - `PUBLIC_SAFE_GIT_METADATA_CHECK` result;
  - operations **not** executed and final completion claim.

If any of the formal role invocation fields (`BRANCH_DELETION_ROLE_INVOCATION` ID / version / digest, input digest, output digest, timestamp, raw evidence references) is missing, cannot be independently verified, or is reused from another operation (Draft / Ready / Merge / other Branch Deletion), the report **must not** pass `vibedev` cross-verification.

`vibedev` performs only cross-verification (§4.13); it **must not** execute the delete, fabricate missing tests, fabricate results, or treat missing evidence as PASS. Only after the report passes cross-verification is `BRANCH_DELETION_VERIFIED` formed, followed by `BRANCH_DELETION_OPERATION_ENDPOINT_REACHED` and **immediate STOP**.

**Three Post-Draft operations — unified cross-verification model.** Each Post-Draft operation has its own structured completion report and final endpoint state. The single shared rule across all three is: any **success verified / endpoint** state (e.g. `PR_READY_VERIFIED`, `MERGE_OPERATION_ENDPOINT_REACHED`, `BRANCH_DELETION_VERIFIED`, `BRANCH_DELETION_OPERATION_ENDPOINT_REACHED`) **must not** be formed before the corresponding `*_COMPLETION_REPORT` passes `vibedev` cross-verification. Each operation **must** use its own `POST_DRAFT_GIT_INTEGRATOR_BINDING`, Activation, attempt ID, formal and attributable role invocation, and independent completion evidence; the Draft delivery invocation and any other Post-Draft invocation **must not** be reused.

  - **Ready** uses explicit PASS / FAIL claim + cross-verified PASS / FAIL final states:
    `READY_TRANSITION_PASS_CLAIM` / `READY_TRANSITION_FAIL_CLAIM` → `READY_TRANSITION_COMPLETION_REPORT` → cross-verification → PASS: `PR_READY_VERIFIED` → STOP / FAIL: `READY_TRANSITION_VERIFICATION_FAIL` → STOP.
  - **Merge** uses explicit PASS / FAIL claim + cross-verified PASS / FAIL final states (mutually exclusive):
    `POST_MERGE_VERIFICATION_PASS_CLAIM` / `POST_MERGE_VERIFICATION_FAIL_CLAIM` → `MERGE_COMPLETION_REPORT` → cross-verification → PASS: `MERGE_DELIVERY_VERIFIED` + `POST_MERGE_VERIFICATION_PASS` → `MERGE_OPERATION_ENDPOINT_REACHED` → STOP / FAIL: `POST_MERGE_VERIFICATION_FAIL` → STOP.
  **Branch Deletion — claim model (unified).** Branch Deletion is a **success-only verified endpoint** operation. There is **no** `BRANCH_DELETION_PASS_CLAIM` and **no** cross-verified failure endpoint. The Branch Deletion report may record at most **one** claim: an optional `BRANCH_DELETION_FAIL_CLAIM` (purely informational, capturing observed deletion / post-delete verification failure when a credible report can still be formed). No `PASS` claim is defined.

  - **Pre-delete failure or post-delete failure**: trigger existing hard STOP states (`BRANCH_DELETION_AUTHORIZATION_STALE`, `BRANCH_DELETION_TARGET_MISMATCH`, `UNVERIFIED_BRANCH_DELETION_RETRY`, `BRANCH_DELETION_API_RECOVERY_BUDGET_EXHAUSTED`).
  - **Credible report can be formed**: `BRANCH_DELETION_COMPLETION_REPORT` may record `BRANCH_DELETION_FAIL_CLAIM` inside the report → `vibedev` cross-verification → **STOP** (no `BRANCH_DELETION_VERIFIED`, no `BRANCH_DELETION_OPERATION_ENDPOINT_REACHED`).
  - **No verified-failure endpoint**: `BRANCH_DELETION_FAIL_CLAIM` **must not** form `BRANCH_DELETION_VERIFIED` or any success endpoint, **must not** be treated as "failed deletion = completed deletion", and **must not** auto-trigger any recovery / rollback / follow-up action.
  - **Insufficient evidence to form a credible report**: existing hard STOP code path applies; `BRANCH_DELETION_FAIL_CLAIM` or any other claim **must not** be fabricated.

  There is **no** auto-recovery, rollback, or "verified failure = success" semantics for Branch Deletion.

The Draft delivery attempt and its report **must not** be reused by any Post-Draft operation. Each operation has its own activation, attempt ID, formal invocation, independent completion evidence, and final endpoint state.



### §4.17 Work Order Schema (canonical governance target)

This section codifies the canonical Work Order governance target. It is a future governance target only and **does not** authorise creation, execution, or modification of any real Work Order in this round.

#### §4.17.1 Work Order — positioning and authorisation-object separation

The **Work Order** is the **sole authorisation object** that drives automatic execution after operator approval inside `VIBECODING_MODE`. It is **not** a regular prompt, task description, or execution log. Operator approval binds **exactly** the triple:

  - `work_order_id`
  - `document_version`
  - `work_order_digest`

The Work Order body only stores the **authorisation facts decided before approval**. Anything produced **during** execution — invocations, artifacts, candidates, Gate results, loop records, test / review evidence, Git delivery evidence — is written into a **separate**, versioned `WORK_ORDER_EXECUTION_RECORD` execution record. Execution results **must not** be written back over the Work Order and **must not** be used to expand authorisation scope.

After approval, any change to scope, role, node, model / provider, credential identity, budget, Gate, repository / base / branch, execution graph, permission, or endpoint requires a **new** `document_version` and a **new** `work_order_digest` and **must** receive a **new** operator approval. In-place modification of an already-approved version is forbidden. Work Order approval **is** the formal start authorisation. Upon approval the Work Order immediately enters `OPERATOR_APPROVED_WORK_ORDER` → `WORK_ORDER_ACTIVE` (**distinct** state, not an alias of approved or readiness) → `GLOBAL_READINESS`. `WORK_ORDER_ACTIVE` is an instantaneous, unambiguous transition — no second confirmation or "start now" checkpoint is inserted. If any execution material skips `WORK_ORDER_ACTIVE` (e.g. `OPERATOR_APPROVED_WORK_ORDER → GLOBAL_READINESS` directly), the drift signal `WORK_ORDER_ACTIVE_TRANSITION_OMITTED` fires and execution **must** `STOP`.

`WORK_ORDER_SCHEMA_VALIDATED` — the Work Order passes the schema validation defined below; only a schema-validated Work Order may enter operator review.

#### §4.17.2 Top-level schema fields — mode applicability discriminant

A Work Order **must** contain, at minimum, the following top-level objects. Any missing object, missing required field, or field value that contradicts another field fails schema validation and triggers `WORK_ORDER_SCHEMA_INVALID`:

  - `identity`
  - `mode_and_phase`
  - `authorization_bindings`
  - `task_scope`
  - `repository_scope`
  - `role_topology`
  - `execution_graph`
  - `readiness_policy`
  - `artifact_and_evidence_contract`
  - `gate_contract`
  - `corrective_loop_contract`
  - `budget_contract`
  - `git_delivery_contract`
  - `public_evidence_contract`
  - `stop_and_resumption_policy`
  - `acceptance_contract`
  - `runtime_state_reference`

**Mode applicability discriminant.** All 17 top-level objects exist in every Work Order. Each object carries an explicit `applicability` or `enabled` field whose value is determined by `selected_submode`:

  - `FULL_9_ROLE_VIBECODING` and `LIGHTWEIGHT_OPERATION` use the **execution-type schema**: full repository scope, non-orchestrator assignment baseline, CANDIDATE_TRIPLE freeze, Gate contract, Git delivery, and Draft PR endpoint.
  - `VIBECODING_CONSULTATION_ONLY` uses the **consultation-type schema**: orchestrator-only, read-only. Fields inapplicable to consultation are set to `NOT_APPLICABLE` as directly proven by `selected_submode`. The schema **must not** fabricate assignments, repository work branches, Gates, artifacts, candidates, or Draft PR references for consultation.
  - Dedicated `HERMES_OPENCODE_VERSION_GOVERNANCE_GATE` and `CENTRAL_MODEL_POOL_GOVERNANCE_GATE` operations are **not** Work Order schema instances; they use their own independent governance operation / authorisation record types.

A field whose `applicability` contradicts `selected_submode` triggers `WORK_ORDER_MODE_APPLICABILITY_CONTRADICTION` — **Immediate STOP.**

**`identity`** must include at minimum: `work_order_id`, `schema_version`, `document_version`, `work_order_digest`, `task_title`, `task_class`, `created_at`, `created_by`, `supersedes_work_order_id` (nullable), `supersedes_document_version` (nullable).

#### §4.17.3 `mode_and_phase` and `authorization_bindings`

**`mode_and_phase`** must record which `VIBECODING_MODE` is entered, the selected submode, and whether `HERMES_OPENCODE_VERSION_GOVERNANCE_GATE` and `CENTRAL_MODEL_POOL_GOVERNANCE_GATE` are in scope. VERSION / CMP governance gates live **outside** `VIBECODING_MODE`; a Work Order that mixes business and VERSION / CMP concerns **must** split them into independent scope, independent authorisation, and independent operations.

**VERSION / CMP gate isolation.** Inside a `VIBECODING_MODE` Work Order, the `HERMES_OPENCODE_VERSION_GOVERNANCE_GATE` and `CENTRAL_MODEL_POOL_GOVERNANCE_GATE` fields **must** be fixed to `false` / `OUT_OF_SCOPE`. If either is `true`, the Work Order triggers `VIBECODING_WORK_ORDER_INCLUDES_DEDICATED_GOVERNANCE_GATE` — **Immediate STOP.** VERSION / CMP gates use their own independent governance operation / authorisation record types and **must not** be disguised as a Work Order, a Consultation-only operation, or a sub-stage of either.

**`authorization_bindings`** must bind at minimum, discriminated by `selected_submode`:

  - **`FULL_9_ROLE_VIBECODING`**:
    - `OPERATOR_ALIGNED_TASK_SCOPE` ID / version / digest;
    - operator-selected submode;
    - the orchestrator's existing `OPERATOR_PRESELECTED_SESSION_BINDING`, including `21bao`, role, model, canonical provider, runtime provider;
    - **8 non-orchestrator** `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE` entries, one per role (explorer, planner, implementer, tester-a, tester-b, reviewer-a, reviewer-b, git-integrator), each with ID / version / digest;
    - `IMPLEMENTATION_PLAN_CHECKPOINT_REQUIRED = true` (FULL mode **mandatory**; the checkpoint is not optional);
    - the operator Work Order approval receipt, with approved version and digest.
  - **`LIGHTWEIGHT_OPERATION`**:
    - `OPERATOR_ALIGNED_TASK_SCOPE` ID / version / digest;
    - operator-selected submode;
    - the orchestrator's existing `OPERATOR_PRESELECTED_SESSION_BINDING`;
    - **operator-approved actual non-orchestrator** `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE` entries, one per approved actual role, each with ID / version / digest;
    - `IMPLEMENTATION_PLAN_CHECKPOINT_REQUIRED` as selected by operator; when `true`, the approved actual role set **must** already include Explorer and Planner;
    - the operator Work Order approval receipt, with approved version and digest.
  - **`VIBECODING_CONSULTATION_ONLY`**:
    - `OPERATOR_ALIGNED_TASK_SCOPE` ID / version / digest;
    - operator-selected submode;
    - the orchestrator's existing `OPERATOR_PRESELECTED_SESSION_BINDING`;
    - `nonorchestrator_assignment_baseline_ref = NOT_APPLICABLE` — the baseline **must not** be created;
    - `IMPLEMENTATION_PLAN_CHECKPOINT_REQUIRED = NOT_APPLICABLE`;
    - the operator consultation Work Order approval receipt, with approved version and digest.

A Work Order **must not** self-modify the assignment. The orchestrator **must not** enter the normal per-role recommendation and approval flow.

#### §4.17.4 `task_scope` and `repository_scope`

**`task_scope`** must include at minimum: `objective`, `business_reason`, requirements with **stable IDs**, `acceptance_criteria` with **stable IDs**, `in_scope`, `out_of_scope`, `explicit_prohibitions`, `expected_outputs`, `known_constraints`, operator-accepted pre-start deviations.

The stable-ID namespace must include at minimum: `requirement_id`, `acceptance_criterion_id`, `finding_id`, `plan_item_id`, `artifact_id`, `evidence_ref_id`, `gate_result_id`, `loop_id`, `candidate_id`. References like "the issue above" or "that requirement" are **forbidden**.

**`repository_scope`** — mode-discriminated:

  - **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`** (execution-type): must bind at minimum: `repository`, `remote`, `base_branch`, `approved_base_sha`, `work_branch`, `expected_entry_head`, `allowed_tracked_paths`, `forbidden_tracked_paths`, `allowed_change_types`, `deletions`, `renames`, `protected_untracked_inventory`, `manifest_external_untracked_policy`. Work Order-allowed paths are **only** an authorisation ceiling; the git-integrator may only stage the **exact paths** listed in the frozen CANDIDATE_TRIPLE manifest. Any currently-known protected untracked paths are recorded as a **construction protection fact for this PR only** and **must not** be promoted to a universal Work Order constant.
  - **`VIBECODING_CONSULTATION_ONLY`**: `applicability = NOT_APPLICABLE` or records only operator-approved read-only source / repository references and `permitted_read_range`. The schema **must not** require `work_branch`, `allowed_change_types`, `deletions`, `renames`, `candidate_manifest`, or `git_remote` for consultation. No `git_delivery_contract` fields are required.

#### §4.17.5 `role_topology`

**`FULL_9_ROLE_VIBECODING`** fixes nine roles and all are required: `orchestrator`, `explorer`, `planner`, `implementer`, `tester-a`, `tester-b`, `reviewer-a`, `reviewer-b`, `git-integrator`. None may be deleted, merged, skipped, or substituted.

**`LIGHTWEIGHT_OPERATION`** includes only the actual role set explicitly approved item-by-item by the operator. Any tracked-diff task must include at minimum: `content-author`, an **independent** `verifier / tester / reviewer`, and `git-integrator`. The content-author **must not** verify its own Gate.

**`VIBECODING_CONSULTATION_ONLY`** — `role_topology` contains **only** the orchestrator. No additional roles are created. `git_delivery_contract.enabled=false`, `gate_contract=NOT_APPLICABLE`, `corrective_loop_contract.enabled=false`. No non-orchestrator `ROLE_COMPLETION_REPORT` is required.

**FULL_9_ROLE_VIBECODING** and **LIGHTWEIGHT_OPERATION** — each non-orchestrator actual role gets its own `assignment`, `ROLE_ACTIVATION_READINESS`, attempt, and attributable meaningful model invocation. Forbidden: shared invocation, copy-pasted output standing in for another role, tool-only completion, or orchestrator-written role artifacts.

#### §4.17.6 `execution_graph`

The Work Order **must** explicitly instantiate the task-specific stages, dependencies, concurrency groups, and handoffs. Role ordering alone is insufficient.

Each stage must record at minimum: `stage_id`, `role`, `depends_on`, `entry_criteria`, `Activation` requirements, `input_artifact_refs`, `output_artifacts`, `exit_criteria`, `PASS_next_node`, `FAIL_return_path`, `STOP_conditions`, `invalidated_downstream_artifacts`, concurrency / isolation / workspace requirements.

**`FULL_9_ROLE_VIBECODING` default execution graph (canonical):**

```
OPERATOR_APPROVED_WORK_ORDER
  → WORK_ORDER_ACTIVE
  → GLOBAL_READINESS
  → Explorer / EXPLORER_VALIDATION
  → Planner / PLAN_VALIDATION
  → OPERATOR_IMPLEMENTATION_PLAN_CHECKPOINT (FULL mode: **mandatory**)
  → Implementer
  → frozen CANDIDATE_FROZEN_FOR_TEST
  → tester-a || tester-b (blind, isolated, independent invocation / report)
  → TEST_GATE
  → reviewer-a || reviewer-b (blind, isolated, independent invocation / report)
  → REVIEW_GATE
  → git-integrator / frozen GIT_INTEGRATION_INPUT_FROZEN
  → exact stage / commit / push / Draft PR
  → DRAFT_PR_DELIVERY_VERIFIED
  → WORK_ORDER_AUTOMATIC_ENDPOINT_REACHED
  → STOP
```

The two testers and the two reviewers each run blind, isolated, with independent invocation and report; review execution only starts after `TEST_GATE_PASS` and Review Packet freeze. **`LIGHTWEIGHT_OPERATION`** instantiates the operator-approved role set and required Gates; absent roles or Gates **must not** be fabricated.

**`VIBECODING_CONSULTATION_ONLY` execution graph (read-only, orchestrator-only):**

```
OPERATOR_APPROVED_WORK_ORDER
  → WORK_ORDER_ACTIVE
  → GLOBAL_READINESS
  → orchestrator executes approved read-only consultation scope
  → CONSULTATION_DELIVERABLE + CONSULTATION_REPORT
  → CONSULTATION_OPERATION_ENDPOINT_REACHED
  → STOP
```

Consultation **must not** enter non-orchestrator Activation, `ROLE_COMPLETION_REPORT`, CANDIDATE_TRIPLE freeze, test / review Gate, git-integrator, commit, push, PR, or Post-Draft chain.

#### §4.17.7 `readiness_policy` and `artifact_and_evidence_contract`

**`readiness_policy`** — mode-discriminated:

  - **All modes** require **Global Readiness**, executed by `vibedev` / orchestrator; no validator role. Global Readiness checks only `selected_submode`-applicable objects. `NOT_APPLICABLE` fields are validated for N/A legitimacy (e.g. Git delivery fields in Consultation are confirmed `NOT_APPLICABLE` — no repo/assignment/Git check is performed). Unknown → `STOP`.

    - **`FULL_9_ROLE_VIBECODING` / `LIGHTWEIGHT_OPERATION`**: Global Readiness checks Work Order integrity, control plane, session binding, repository, assignment, node / route, model / provider / credential, toolchain, evidence, and Git delivery.
    - **`VIBECODING_CONSULTATION_ONLY`**: Global Readiness checks Work Order integrity, control plane, orchestrator session binding (`OPERATOR_PRESELECTED_SESSION_BINDING`), approved read-only sources / permitted read range, orchestrator model / provider / credential, consultation evidence and output capability, and secret boundary. Repository / assignment / node / route / toolchain / Git delivery checks are **not** executed for Consultation — their corresponding fields carry `applicability=NOT_APPLICABLE` and Global Readiness verifies that they are correctly N/A.

  - **Role Activation Readiness** — mode-discriminated:
    - **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`**: executed before every non-orchestrator formal attempt and re-executed after every loop return.
    - **`VIBECODING_CONSULTATION_ONLY`**: non-orchestrator Role Activation = `NOT_APPLICABLE`. No fictional Activation is created. The orchestrator is covered by `OPERATOR_PRESELECTED_SESSION_BINDING` and Global Readiness.

A probe does **not** count as a role's formal execution.

**`artifact_and_evidence_contract`** — mode-discriminated:

  - **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`** (execution-type): each non-orchestrator role, for each attempt, must submit a structured `ROLE_COMPLETION_REPORT` containing at minimum: role / assignment, Activation, attempt ID, invocation IDs, input / output artifact references, tools / commands, work product, acceptance results, blockers, completion claim. `vibedev` cross-verifies each report into `VERIFIED` / `INCOMPLETE` / `REJECTED`; `vibedev` **must not** fabricate role judgement.
  - **`VIBECODING_CONSULTATION_ONLY`**: records the consultation deliverable and `CONSULTATION_REPORT` with their ID / version / digest / source references. Non-orchestrator `ROLE_COMPLETION_REPORT` is **not** required.

**Artifact schema** — mode-discriminated:

  - **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`** (execution-type): requires at minimum: `artifact_id`, `type`, `version`, `digest`, `producer_role`, `role_invocation`, `input_refs`, `candidate_digest`, `created_at`, `status`.
  - **`VIBECODING_CONSULTATION_ONLY`** (consultation-type): requires at minimum: `artifact_id`, `artifact_type` (deliverable or report), `version`, `digest`, `producer_role=orchestrator`, `orchestrator_invocation_id/version/digest`, `input_read_source_refs`, `evidence_ref_ids` / raw evidence references, `created_at`, `status`. `candidate_digest` is **not** required. No Gate, non-orchestrator assignment, or Git fields are required.

Permitted status values (all modes): `VALID`, `INVALIDATED`, `SUPERSEDED`, `REVALIDATION_REQUIRED`. Frozen artifacts **must not** be modified in place. Any new content produces a new `version` and `digest`.

#### §4.17.8 `gate_contract`

**`FULL_9_ROLE_VIBECODING`** must define `TEST_GATE` and `REVIEW_GATE`:

  - **Tester pair** (`tester-a`, `tester-b`): same frozen CANDIDATE_TRIPLE, independent charter, independent attempt, independent invocation, independent report. **No majority vote.** Both `VERIFIED` and acceptance criteria passed → `TEST_GATE_PASS`.
  - **Reviewer pair** (`reviewer-a`, `reviewer-b`): same frozen Review Packet, independent blind review, independent report. **No majority vote.** Both `VERIFIED` and no blocker → `REVIEW_GATE_PASS`.
  - **Conflict** → evidence-only contradiction packet (e.g. `TEST_CONTRADICTION_PACKET` / `REVIEW_CONTRADICTION_PACKET`) routed by root cause to the responsible role.

**`LIGHTWEIGHT_OPERATION`** `required_pre_git_gates` must be **non-empty**. Each Gate's members must be non-empty and include at least one verifier **independent** of the content-author. A single role covering multiple Gates must use different Activation / attempt / charter / invocation / report / evidence per Gate. An unavailable, unapproved Gate is `NOT_IN_APPROVED_TOPOLOGY`; it **must not** be falsified as `NOT_APPLICABLE` or as `PASS`.

#### §4.17.9 `corrective_loop_contract` and `budget_contract`

**`corrective_loop_contract`** — mode-discriminated:

  - **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`**: only Work Order pre-approved paths are allowed. Each path records: `from_stage`, `return_role`, `invalidated_artifacts`, `per_path_budget`, `global_budget`. Default recommendations (subject to operator approval): `LIGHTWEIGHT_OPERATION`: per-path 4, global 6; `FULL_9_ROLE_VIBECODING`: per-path 5, global 10. Each loop round records: `loop_id`, `round`, `failure_signature`, `return_role`, `new_diff_or_evidence`, `result`, `remaining_budget`. Two consecutive rounds with the **same** failure signature and **no** effective diff, new root evidence, coverage, change-demand resolution, or new hypothesis trigger `LOOP_STAGNATION_DETECTED → STOP`. Hard `STOP` **must not** be bypassed by loop budget.
  - **`VIBECODING_CONSULTATION_ONLY`**: `corrective_loop_contract.enabled = false`. No loop path, `loop_id`, `return_role`, artifact invalidation, per-path or global loop budget, or `LOOP_STAGNATION_DETECTED` state is created. If consultation conclusions need revision, the Work Order reaches STOP and the operator issues a new decision, new authorisation, or new Work Order version — **not** an automatic corrective loop.

**`budget_contract`** — mode-discriminated:

  - **All modes (common STOP trigger set)**: automatic model substitution, quota retry, and quota-reset wait are all `false`. The following trigger immediate `STOP` for all modes: `MODEL_QUOTA_EXHAUSTED`, credential failure, control-plane failure, evidence forgery, orchestrator session binding (`OPERATOR_PRESELECTED_SESSION_BINDING`) loss or mismatch.
  - **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`**: additionally, non-orchestrator assignment baseline failure, non-orchestrator Activation failure, and Gate / CANDIDATE_TRIPLE / remote / Git / push / PR API / proxy bypass failures trigger immediate `STOP`.
  - **`VIBECODING_CONSULTATION_ONLY`**: must **not** generate non-orchestrator assignment baseline failure or non-orchestrator Activation failure. Corrective loop budget, push budget, PR API budget, and proxy bypass budget fields **must** be `NOT_APPLICABLE` or `disabled / 0`; their presence **must not** be interpreted as Git delivery capability, and a non-zero value triggers `CONSULTATION_GIT_BUDGET_REQUIRED`.

Per-mode budget requirements:

  - **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`**: must include per-role and total model invocation budget, loop budget, push budget, PR API budget, proxy bypass budget.
  - **`VIBECODING_CONSULTATION_ONLY`**: must include orchestrator model / invocation budget, read-source / tool budget, evidence / output capability budget, and operator-approved time / invocation count limits.

#### §4.17.10 `git_delivery_contract` and `public_evidence_contract` — mode-discriminated

**`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`** (execution-type) — `git_delivery_contract` must:

  - name `executor = git-integrator`;
  - enforce CANDIDATE_TRIPLE freeze, exact manifest staging, and `COMMIT_TREE_MATCHES_FROZEN_CANDIDATE`;
  - default to **one** ordinary commit;
  - forbid `git add .`, `git add -A`, `git commit -am`, amend, force, rebase, reset, Ready, merge, branch deletion;
  - require the resulting PR to remain `OPEN + DRAFT`;
  - cap pushes at 3, PR API calls at 3, and the entire Git delivery at **one** shared proxy bypass.

On indeterminate result, query the remote / PR state **first** before deciding whether to retry.

**`VIBECODING_CONSULTATION_ONLY`** — `git_delivery_contract.enabled = false`. No Git delivery fields are required. The public Git metadata / projection fields are `NOT_APPLICABLE`, though secret / public-safety boundaries remain in effect.

**`public_evidence_contract`** — mode-discriminated:

  - **Execution-type** (FULL / LIGHTWEIGHT): requires pre-commit projection draft, post-commit only Git-derived fields, final consistency re-check, and `PUBLIC_SAFE_GIT_METADATA_CHECK`.
  - **Consultation-only**: `applicability = NOT_APPLICABLE`. No Git-derived evidence fields are required.

**Automatic endpoint chain** — mode-discriminated:

  - **Execution-type** (FULL / LIGHTWEIGHT): the Work Order's automatic endpoint chain is fixed at:
    ```
    DRAFT_PR_DELIVERY_VERIFIED → WORK_ORDER_AUTOMATIC_ENDPOINT_REACHED → STOP
    ```
    The Work Order **must** explicitly set:
    - `draft_to_ready = false`
    - `merge = false`
    - `branch_deletion = false`
    and **must not** include any Post-Draft authorisation. Post-Draft operations are independent operator authorisations issued **after** `DRAFT_PR_DELIVERY_VERIFIED`; they are **not** part of the Work Order.

  - **Consultation-only**: the automatic endpoint chain is:
    ```
    CONSULTATION_DELIVERABLE + CONSULTATION_REPORT → CONSULTATION_OPERATION_ENDPOINT_REACHED → STOP
    ```
    The `draft_to_ready / merge / branch_deletion` fields may be present as `false` but **must not** be interpreted as evidence of a Draft PR. No Post-Draft chain exists for consultation.

#### §4.17.11 `stop_and_resumption_policy`

`STOP` covers **every** stage, enabling only the `selected_submode`-applicable STOP classes:

  - **All modes (common)**: Global Readiness failure, quota exhaustion (`MODEL_QUOTA_EXHAUSTED`), control plane failure, evidence forgery, evidence pipeline / channel unreachable or untrustworthy, evidence infrastructure unavailable / failure, orchestrator session binding (`OPERATOR_PRESELECTED_SESSION_BINDING`) loss or mismatch, scope drift, Work Order integrity failure, secret boundary violation, credential failure, operator abort. Without trustworthy evidence, no `ROLE_COMPLETION`, Consultation deliverable / report `VERIFIED` state, Gate `PASS`, or Work Order endpoint state **may** be formed. FULL / LIGHTWEIGHT **may not** patch missing infrastructure via loop budget; Consultation **may not** substitute missing evidence with new analysis content. §4.17.9 only enumerates the budget / runtime hard STOP subset — §4.17.11 is the complete canonical STOP set, and the two sections **must not** be read as mutually covering or as allowing deletions.
  - **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`** additionally: non-orchestrator Activation failure, non-orchestrator assignment baseline failure, role completion failure, Gate failure, CANDIDATE_TRIPLE tree mismatch, remote branch drift, loop stagnation, push / PR API budget exhaustion, proxy bypass budget exhaustion.
  - **`VIBECODING_CONSULTATION_ONLY`**: Consultation **must not** trigger STOP on non-existent CANDIDATE_TRIPLE, Gate, remote branch, loop stagnation, Git budget, or non-orchestrator assignment failure. Consultation remains subject to the "All modes" STOP classes, read-source failure, deliverable / report integrity failure, orchestrator invocation failure, and operator-revocation STOP. If a Consultation Work Order encounters these execution-type-only failure conditions, the correct response is `WORK_ORDER_MODE_APPLICABILITY_CONTRADICTION` (field applicability vs submode) or the appropriate Consultation-specific drift signal — **not** a fabricated execution-type STOP record.

After `STOP`:

  - `automatic_continuation = false`;
  - `automatic_retry = false`;
  - `operator_decision_required = true`;
  - the original Work Order **must not** self-resume;
  - a new, independent authorisation or a new Work Order version / digest is required.

Pre-approved bounded loops **inside** a Work Order and post-`STOP` re-authorisation **outside** the Work Order are strictly distinct.

#### §4.17.12 `acceptance_contract` and `runtime_state_reference`

**`acceptance_contract`** — mode-discriminated:

  - **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`** (execution-type): must map every `requirement_id` to its `acceptance_criterion_id`, the stage that verifies it, the artifact that records it, the Gate that confirms it, and the **final Draft PR evidence** that surfaces it. A criterion with no owner, no verification path, or no evidence reference is invalid.
  - **`VIBECODING_CONSULTATION_ONLY`**: must map every `requirement_id` to its `acceptance_criterion_id`, the approved read source / analysis step that verifies it, the consultation deliverable section that records it, and the **consultation report evidence** that surfaces it. The schema **must not** fabricate Gates, candidates, or Draft PR evidence for consultation. A criterion with no owner, no verification path, or no mode-appropriate evidence reference is schema-invalid.

**`runtime_state_reference`** is read-only and mode-discriminated:

  - **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`**: may reference execution record, current stage, valid artifact / Gate / CANDIDATE_TRIPLE versions, and remaining budgets.
  - **`VIBECODING_CONSULTATION_ONLY`**: may only reference execution record, current consultation stage, approved read-source references, deliverable / report version, orchestrator invocation and evidence, and applicable budgets (orchestrator model / read-source / output). Consultation **must not** create or reference fictional Gate, CANDIDATE_TRIPLE, or Git state.

In any mode, runtime state is **not** an authorisation source and **must not** modify the Work Order. Any inconsistency between runtime state and the approved Work Order triggers immediate `STOP`.

#### §4.17.13 Work Order state machine

Canonical states — **common prefix** (all modes):

  - `WORK_ORDER_DRAFT`
  - `WORK_ORDER_SCHEMA_VALIDATED`
  - `WORK_ORDER_READY_FOR_OPERATOR_REVIEW`
  - `OPERATOR_APPROVED_WORK_ORDER` (operator approval event — **distinct** from active)
  - `WORK_ORDER_ACTIVE` (entered immediately after approval; **not** an alias of `OPERATOR_APPROVED_WORK_ORDER`)
  - `GLOBAL_READINESS`

**`VIBECODING_CONSULTATION_ONLY` success branch:**

```
GLOBAL_READINESS_PASS → orchestrator executes approved read-only consultation scope
  → CONSULTATION_DELIVERABLE + CONSULTATION_REPORT
  → CONSULTATION_OPERATION_ENDPOINT_REACHED
  → STOP
```

**`FULL_9_ROLE_VIBECODING` / `LIGHTWEIGHT_OPERATION` success branch:**

```
GLOBAL_READINESS_PASS → approved role / stage graph
  → DRAFT_PR_DELIVERY_VERIFIED
  → WORK_ORDER_AUTOMATIC_ENDPOINT_REACHED
  → STOP
```

**Hard STOP branch (all modes):**

```
ANY_POST_APPROVAL_ACTIVE_EXECUTION_STATE → hard STOP → WORK_ORDER_STOPPED_PENDING_OPERATOR
```

Where `ANY_POST_APPROVAL_ACTIVE_EXECUTION_STATE` covers all un-terminated stages after `WORK_ORDER_ACTIVE`, including at minimum `WORK_ORDER_ACTIVE`, `GLOBAL_READINESS`, and every execution stage reachable via the mode's execution graph. Hard STOP **must not** be restricted to `WORK_ORDER_ACTIVE` alone; `WORK_ORDER_ACTIVE` is a transient transition, not a long-lived parent state capable of covering all failure points. If any execution material limits hard STOP entry to only `WORK_ORDER_ACTIVE`, the drift signal `WORK_ORDER_HARD_STOP_SOURCE_STATE_INCOMPLETE` fires and execution **must** `STOP`.

Any DRAFT / APPROVED / STOPPED version may be `SUPERSEDED_BY_NEW_VERSION`; old approvals **must not** migrate to the new version. Operator approval **is** the start authorisation; no additional "start now" checkpoint may be inserted.

The `draft_to_ready / merge / branch_deletion` Post-Draft chain applies **only** to execution-type Work Orders (FULL / LIGHTWEIGHT) that actually produce a Draft PR. Consultation-only **must not** be interpreted as having a Draft PR or Post-Draft chain.

## §5. 8-Role Assignment Pre-Brief

### §5.1 Trigger

The complete 8-role assignment pre-brief (excluding orchestrator) is **mandatory only** when operator selects `FULL_9_ROLE_VIBECODING` (§4.1.3). In `LIGHTWEIGHT_OPERATION` (§4.1.2), `vibedev` recommends the actual non-orchestrator role set after VC8; the operator approves item by item forming `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`. `VIBECODING_CONSULTATION_ONLY` (§4.1.1) does not enter any assignment pre-brief; its Work Order is generated without a baseline.

The assignment process (§5.2–§5.14) occurs **after** sub-mode selection (VC8) and **before** Work Order generation, where applicable.

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

The available list and the recommendation matrix are **only** recommendations. Operator **must** explicitly specify node + model for every actual non-orchestrator role in the operator-selected execution mode.

### §5.7 No Pre-Spec Execution

Before operator's explicit node + model specification for the operator-selected execution mode's actual roles, orchestrator **must not**:

- start execution;
- auto-fill empty roles;
- auto-select default model / node;
- apply "no objection ⇒ default OK" reasoning to circumvent specification.

### §5.8 Assignment Strictness

Once operator specifies the assignment, the system **must** execute exactly that assignment:

- no adjustment of node or model for efficiency / fault tolerance / task-continuity reasons;
- orchestrator **must not** unilaterally reinterpret the assignment;
- every designated role's input, context, prompt, execution batch, output, and evidence lands as specified, until operator issues a **new decision**.
- **Model quota exhaustion** (§3.5.13) does **not** authorise automatic model / node / provider / credential substitution. The assignment is **blocked**; only operator may specify a new assignment.

### §5.9 Failure Cross-Reference

If any designated node or model fails the §7.1 triggers before or during execution, immediately follow §7. This does **not** override §5.8.

### §5.10 MODEL_QUOTA_EXHAUSTED — Mandatory Behaviour

When a designated model is confirmed as quota-exhausted before or during a task:

1. **Immediately STOP** the current role and the current task.
2. **Preserve** the last successful checkpoint, partial output, and error evidence.
3. **Mark** the current state as `BLOCKED`, `PARTIAL`, or `OUTPUT_COMPLETE_BUT_UNVERIFIED` (whichever applies); **must not** mark as `PASS`.
4. **Report** to operator and wait for a new decision.

**Strictly forbidden:**

- automatic retry;
- automatic wait for quota recovery and continue;
- automatic route switch;
- automatic model / node / provider / credential / account substitution;
- automatic continuation of subsequent roles;
- automatic scope reduction;
- treating the same model name, another model under the same provider, or a model on another node as fallback.

### §5.11 Orchestrator Model Quota Exhaustion

If `21bao`'s current orchestrator model experiences `MODEL_QUOTA_EXHAUSTED`:

- The **entire current task** immediately STOPs.
- Workers, reviewers, or other business roles **must not** take over the orchestrator.
- `vibedev` may use only deterministic capabilities that do **not** depend on the exhausted model to compile a blocking report.
- Operator must re-specify the orchestrator model before recovery. Recovery proceeds from the operator-specified checkpoint.
- If the new orchestrator model has not completed CMP qualification, it must first enter the `CENTRAL_MODEL_POOL_GOVERNANCE_GATE` (§6.9).

### §5.12 Operator Recovery Options

Only the operator may choose a recovery path. Orchestrator may recommend but **must not** self-select. Available options:

- **A**: Wait for quota recovery, retry from specified checkpoint with the original role / node / model.
- **B**: Re-specify role / node / model and recovery checkpoint.
- **C**: If the new model has not completed CMP registration, sync, qualification, and operator-approved status, first enter `CENTRAL_MODEL_POOL_GOVERNANCE_GATE` (§6.9), then re-assign.
- **D**: Modify scope and form a new explicit authorisation or new run.
- **E**: Terminate the task and preserve `BLOCKED` / `PARTIAL` evidence.

### §5.13 Execution Pipeline Acknowledgement

Transport-route failover (§3.5) does **not** relax §5 strictness. A route failover must keep every field in §5.8 invariant.

### §5.14 Readiness and Quota Boundary

Readiness checks follow the dual-layer model (§4.10): `GLOBAL_READINESS` and `ROLE_ACTIVATION_READINESS`. Readiness checks **may** verify: model enabled, credential presence, provider response, bounded smoke call. A readiness `PASS` proves only that the model was callable at check time; it does **not** constitute a remaining-quota guarantee. Quota status unknown **must not** be reported as quota sufficient.

Readiness **must not** create or expand any authorisation (§4.1, §4.10). Readiness probes are not the target role's distinct model invocation, work product, or completion evidence (§4.5, §4.7, §4.8).

All recovery model calls **must** establish evidence linkage to the original run / checkpoint. Quota exhaustion **must not** be classified as a network, DNS, SSH, or transport fallback event.

---

## §6. Central Model Pool

### §6.1 Unified Management

The Central Model Pool (CMP) is a unified management gate (§6.9 CENTRAL_MODEL_POOL_GOVERNANCE_GATE). It does **not** enter the three VibeCoding execution modes (§4.1) and does **not** trigger FULL 9-role or 8-role assignment.

### §6.2 Single Logical Source

The Central Model Pool is the single logical model-management and dispatching entry point. Operator — through `vibedev` — manages model addition / modification / disable / deletion.

### §6.3 Controlled Synchronisation

After operator maintains the central pool, the system must perform controlled sync of each node's OpenCode configuration: `provider_namespace`; `model_id`; `endpoint` / `base_url`; `alias`; `enable` / `disable`; `allowed_node` / `role`; `credential_reference`; node-specific `runtime_provider` mapping.

### §6.4 Node Calling Boundary

Each node's OpenCode **may only** call models registered in the central pool, synced, allowed for that node, and passing readiness.

### §6.5 Forbidden Patterns

- node-local private model addition;
- unregistered alias reverse-override of the central pool.

### §6.6 Secret Handling and Credential Discovery Boundary

Secrets are classified into two boundaries:

**1. Hard public boundary**: plaintext secret values **must not** enter tracked Git, commits, public PRs / issues, public artifacts, publicly or externally shared reports / logs, or third-party-accessible persistent media.

**2. Private single-user boundary**: operator-personal, operator-only, local-only / gitignored configuration, controlled worker files, and private micro-cluster internal communication **may** contain secrets when operationally necessary. Such internal occurrence does **not** automatically constitute a security incident, does **not** automatically trigger STOP, and does **not** automatically require rotation.

**Default handling**:
  - Prefer credential reference, variable name, or categorical presence state (`PRESENT_NONEMPTY` / `PRESENT_EMPTY` / `ABSENT`) over value-bearing output.
  - Credential discovery (any code, prompt, or report that lists environment variables) **must not** serialise or print a value-bearing environment map. Only variable **name** and categorical **presence** state are permitted outputs.
  - ChatGPT transfer prompts default to **not** embedding secret values. If operator explicitly requires secret embedding in a private-cluster channel, the prompt must document the usage scope and the prohibition against entering Git or public artifacts.

**Exposure classification**:
  - **Private operator-controlled scope only**: record context; operator decides whether to continue or clean up.
  - **Public / external / uncontrolled scope**: STOP, preserve facts, report to operator; operator decides rotation / revocation.
  - Runtime **must not** auto-rotate, auto-revoke, or auto-replace credentials.

### §6.7 Single Write Direction

- The Central Model Pool has a single write flow;
- Direction of sync is explicit;
- **Forbidden**: cyclic `source_of_truth` between `model_pool`, NMC, `alias_config`, and `node-local config`.

### §6.8 Post-Sync Validation

Any failure STOP + report:

- rendered config;
- alias;
- endpoint / provider;
- credential presence (values never printed);
- `runtime-visible`;
- `wrapper-valid`;
- bounded canary / model-call;
- drift.

### §6.9 CENTRAL_MODEL_POOL_GOVERNANCE_GATE

This is a **dedicated governance gate** managed uniformly by `vibedev` on `21bao`. It does **not** enter the three VibeCoding execution modes (§4.1) and does **not** trigger FULL 9-role or 8-role assignment. Operator is the sole final decision maker. `vibedev` is responsible for unified inventory, audit, proposal, preparation, approved-scope execution, qualification, and reporting. `vibedev` **must not** self-approve, auto-change, auto-expand, or auto-rollback.

#### §6.9.1 C0 — Scope

Operator specifies the target CMP change(s), affected node(s) / profile(s), and purpose.

#### §6.9.2 C1 — Audit

`vibedev` read-only collects: current provider / model / alias inventory, allowed node / role mapping, credential reference status, seven-state status per node-model entry, drift from source of truth, and evidence.

#### §6.9.3 C2 — Proposed Delta

`vibedev` submits: exact additions, modifications, and deletions; affected nodes; sync direction; secret scope; verification plan; rollback plan.

#### §6.9.4 C3 — Preparation Approval

Operator approves preparation only. Allowed: render, diff, dry-run, backup, validation plan. **Not** allowed: real CMP write, provider / model / alias / endpoint change, node sync / distribution, secret overlay write or distribution.

#### §6.9.5 C4 — Pre-Execution Checkpoint

`vibedev` presents: target delta / action / current state / rollback point / affected scope. Operator reviews.

#### §6.9.6 C5 — Second Confirmation

Real CMP write, provider / model / alias / endpoint change, node sync / distribution, secret overlay write or distribution **must** receive a second explicit operator confirmation.

#### §6.9.7 C6 — Exact-Scope Apply

Execute only the operator-approved scope. **Must not** expand to other models, nodes, or profiles.

#### §6.9.8 C7 — Post-Apply Qualification

Verify: rendered config, alias / endpoint / provider, credential presence, declared / synced / runtime-visible / env-loaded / wrapper-valid / model-call-verified / operator-approved, drift. All applicable checks must PASS. Non-applicable items must carry explicit `NOT_APPLICABLE` with reason; they **must not** be reported as PASS.

#### §6.9.9 C8 — Closeout

Report: result, model matrix, evidence, and residual risks. Failure triggers immediate STOP. **No** auto-model-change, auto-node-expansion, auto-credential-replacement, or auto-loop of source-of-truth modification. **No** automatic rollback unless operator has pre-approved an atomic failure rollback plan; such rollback must be executed within the approved scope with full evidence logging.

### §6.10 Route-Chain Integration Boundary

The Central Model Pool regulates models and providers. Transport-route chain (§3.5) regulates *how* a node is reached. The two are orthogonal; this contract does **not** mix them and does **not** embed transport endpoint / port values in any model descriptor.

---

## §7. Failure STOP + Report

### §7.1 Triggers

Any of the following immediately triggers STOP:

- designated node unavailable;
- node health = `UNKNOWN`;
- readiness STOP per §4.10.1 / §4.10.2 / §4.10.3 (`GLOBAL_READINESS_STOP` or `ROLE_ACTIVATION_READINESS_FAIL` not eligible for the pause-and-revalidate path);
- SSH / local-exec failure;
- model call failure;
- `MODEL_QUOTA_EXHAUSTED` (§3.5.13);
- provider / credential / endpoint / alias / wrapper anomaly.

`GLOBAL_READINESS_INVALIDATED` itself does **not** always equal STOP — it may trigger revalidation under §4.10.3.

### §7.2 Precedence of §3.5 over §7

For an `ACTIVE` node with an operator-approved, registered, qualified same-node route chain (§3.5), a transport-path failure matching §3.5.5 **first** enters the §3.5 failover flow and **does not** immediately trigger the §7.1 STOP above. The §7.1 STOP fires when the §3.5 path has terminated, namely:

  - the failure is a §3.5.6 disallowed trigger class;
  - the next route is reachable but identity, credential, application readiness, model, gate, receipt, or evidence fails (§3.5.8 post-condition);
  - the chain has been exhausted (§3.5.9);
  - a proposed or actual route switch violates §3.5.2 same-chain constraints or changes an invariant listed in §3.5.11;
  - the node has no approved, registered, and qualified same-node route chain.

Local-exec and control-plane failures go directly to §3.6.4 / §3.6.7.

### §7.3 Immediate Actions

- Immediately stop all new role / step / SSH / model call / Git write / file write.
- Preserve current durable evidence, receipts, traces, logs, state snapshot.
- **Must not** unilaterally clean up, compensate, recover, retry, or roll back.
- If the operator-approved action **explicitly** contained a pre-approved atomic-failure-rollback mechanism, that mechanism **alone** may execute to avoid data corruption, with full logging.
- Other rollback / recovery / compensation actions require new operator authorisation.
- **Secrets**: Failure STOP report **must not** unnecessarily print secrets. Public / external / uncontrolled reports or logs **must not** contain plaintext secrets. Private operator-controlled scope follows §6.6; internal occurrence does **not** trigger automatic STOP or rotation.

### §7.4 Report Content (at minimum)

Report content depends on the applicable entry:

  - `FULL_9_ROLE_VIBECODING` / `LIGHTWEIGHT_OPERATION`: failing role, designated node, designated model, failed stage;
  - `HERMES_OPENCODE_VERSION_GOVERNANCE_GATE` (§3.8): V-stage, component, node / profile;
  - `CENTRAL_MODEL_POOL_GOVERNANCE_GATE` (§6.9): C-stage, target delta, affected node;
  - `VIBECODING_CONSULTATION_ONLY` or non-applicable fields: `NOT_APPLICABLE`.

All entries additionally report:
- error summary — quoting error codes / key log lines; **not** unnecessarily printing secrets / tokens / keys (per §7.3);
- actions completed;
- actions not completed;
- current Git / task / receipt state (HEAD SHA, current PR if any, list of produced receipts);
- items requiring operator decision — statement of fact + options + their respective risks; orchestrator **does not** choose.

When the error class is `MODEL_QUOTA_EXHAUSTED`, the report must additionally include:
- error class = `MODEL_QUOTA_EXHAUSTED`;
- task / run;
- execution mode or dedicated gate;
- current role;
- designated node;
- designated model;
- canonical provider and runtime provider;
- credential reference name or presence state; **must not** output secret value;
- quota impact scope: model-level / provider-level / account-level or `UNKNOWN`;
- last successful checkpoint;
- partial output / evidence status;
- whether other assignments sharing the same provider / account may be affected;
- operator recovery options (A–E per §5.12).

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

**Coordination with §4.12 Work Order pre-approved bounded corrective loop.** §7.6 forbids arbitrary automatic retry. §4.12 separately authorises **pre-approved** bounded corrective loops that the Work Order itself defines (start / end roles, trigger conditions, per-path rounds, global rounds, evidence, STOP conditions). Such pre-approved loops are **not** "arbitrary retry" under §7.6; they are part of the operator-approved Work Order scope. STOP and report immediately if:

  - quota exhausts;
  - scope / assignment / model / node / provider / credential changes;
  - the run exits the pre-approved path;
  - governance items (VERSION / CMP) appear;
  - per-path or global budget exhausts;
  - `LOOP_STAGNATION_DETECTED` (§4.12) fires.

Revalidation under §4.10.3 (pause-and-revalidate path) is **not** a retry; it is a readiness refresh. It does not require a new operator authorisation when the pause-and-revalidate conditions hold (§4.10.3).

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

  - the failure is a §3.5.6 disallowed trigger class;
  - the next route is reachable but identity, credential, application readiness, model, gate, receipt, or evidence fails (§3.5.8 post-condition);
  - the chain has been exhausted (§3.5.9);
  - a proposed or actual route switch violates §3.5.2 same-chain constraints or changes an invariant listed in §3.5.11;
  - the node has no approved, registered, and qualified same-node route chain.

§3.5.11 itself is **not** a failure class and **must not** be cited as a STOP trigger.

---

## §8. Operational Workflow Governance Envelope and Evidence

### §8.1 Confirmed Entry Skeleton

The following entry skeleton is confirmed:

> operator explicitly enters `VIBECODING_MODE` → VC0–VC8 pre-stage (§4.1) → operator selects sub-mode → where applicable, `vibedev` recommends non-orchestrator role assignments → operator approves item by item forming `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE` → `vibedev` generates Work Order (consultation-only Work Order without baseline for `VIBECODING_CONSULTATION_ONLY`) → operator reviews, modifies, approves, or rejects the Work Order → only after `OPERATOR_APPROVED_WORK_ORDER` → `WORK_ORDER_ACTIVE` → `GLOBAL_READINESS` may `vibedev` proceed (§4.10, §4.17.1).

**After `GLOBAL_READINESS_PASS`, the path splits by mode:**

  - **`VIBECODING_CONSULTATION_ONLY`**: orchestrator executes approved read-only consultation scope → `CONSULTATION_DELIVERABLE` + `CONSULTATION_REPORT` → `CONSULTATION_OPERATION_ENDPOINT_REACHED` → STOP. No per-role Activation, no `ROLE_COMPLETION_REPORT`, no test/review Gate, no git-integrator, no Draft PR.
  - **`FULL_9_ROLE_VIBECODING` / `LIGHTWEIGHT_OPERATION`**: per-role `ROLE_ACTIVATION_READINESS` (§4.10) → role execution with `ROLE_COMPLETION_REPORT` and cross-verification (§4.13) → §4.12 pre-approved bounded corrective loop on `INCOMPLETE` / `REJECTED` (if applicable) → test / review → git-integrator → commit / push → create or update **Draft PR** → STOP and report. `Draft → Ready` and merge each require separate independent operator authorisation (§9.2, §10.6).

The following items **remain** to be finalised by operator in the future operator-approved operational workflow spec (these do **not** affect Round-22 readiness / completion / loop governance):

- machine-executable serialisation format for Work Order fields;
- specific field encoding and validator implementation;
- task-specific role linear order, concurrency, and handoff topology;
- task-specific test / review choreography;
- workspace and command implementation;
- packet / receipt physical storage format (logical schema provisionally fixed in §10.3 — `PROVISIONAL_ARTIFACT_EVIDENCE_SCHEMA_PENDING_POST_REMEDIATION_GRAY4_VALIDATION`);
- closeout schema;
- complete `VIBECODING_MODE` state machine.

Already confirmed and **not** subject to the "not yet finalised" label: VC0–VC8 pre-stage; Work Order approval = job start; dual-layer readiness (§4.10); `ROLE_COMPLETION_REPORT` + cross-verification (§4.13); bounded corrective loop governance (§4.12); default return matrix and artifact invalidation (§4.14); `LIGHTWEIGHT_OPERATION` / `FULL_9_ROLE_VIBECODING` default endpoint is Draft PR (§4.1, §9.2); paused-and-revalidate path (§4.10.3); FULL default mid-to-late-stage topology with CANDIDATE_TRIPLE freeze, dual tester, test gate, dual reviewer, review gate, and git-integrator hard gate (§4.16); CANDIDATE_TRIPLE plan source binding per sub-mode (§4.16.2); contradiction routing by root cause (§4.16.4); non-PASS gate paths (§4.16.4, §4.16.5); LIGHTWEIGHT actual role set principle with mode-scoped §4.15/§4.16 governance (§4.1.2, §4.15, §4.16); LIGHTWEIGHT `direct_to_implementer` provenance (§4.16.2); LIGHTWEIGHT `required_pre_git_gates` with non-empty requirement and independent verifier Gate (§4.16.7); verifier cross-Gate independence (§4.1.2); LIGHTWEIGHT no-Planner advance conditions (§4.15.3); mode-aware `PREMATURE_GIT_INTEGRATION` (§10.1); Git delivery pipeline with exact staging (approved new files permitted, manifest-external untracked forbidden, construction-specific paths not a universal constant), CANDIDATE_TRIPLE–commit tree binding, two-phase evidence model (pre-commit `PUBLIC_SAFE_EVIDENCE_PROJECTION_DRAFT` → post-commit `DRAFT_PR_EVIDENCE_BODY`), bounded push/PR API/proxy bypass budgets (§4.16.9); **Work Order canonical schema governance (§4.17) — sole authorisation object, 17 top-level fields with mode applicability discriminant, mode-discriminated authorization_bindings / repository_scope / role_topology / execution_graph / acceptance_contract / git_delivery_contract / endpoint chain, VERSION/CMP gate isolation, state machine with distinct approval→active states and Consultation-only branch**; consultation-only execution graph and endpoint (§4.17.6, §4.17.10, §4.17.13); `CONSULTATION_OPERATION_ENDPOINT_REACHED` as consultation endpoint (§4.17.10, §4.17.13); mode-discriminated acceptance_contract (§4.17.12); `WORK_ORDER_MODE_APPLICABILITY_CONTRADICTION` and 7 additional mode-applicability drift signals (§10.1).

Until the operational workflow is formally accepted and `OPERATIONAL_PHASE` cutover declared, no action may claim V2-compliant formal VibeCoding E2E or canonical pipeline `PASS`.

### §8.2 Non-Canonical Paths

- Operator **may** explicitly authorise wrapper, manual SCP / SSH, ad-hoc model calls for diagnosis, recovery, evidence collection, or local verification. Such executions must record operator authorisation and carry `execution_path: non_canonical`.
- Their results may carry only the labels `diagnostic`, `local_verification`, or `historical_evidence`; **must not** claim canonical E2E PASS.
- Unauthorised use is **forbidden**.
- Non-canonical paths **must not** become assignment-level automatic fallback.

### §8.3 Execution Kind and Role Tools

`simulation` / `dry-run` / `unit test` / `fixture` / `historical receipt` / `real execution` must carry explicit `kind:` labels and may not impersonate each other. `pytest` / `fixture` / static analysis / `lint` / deterministic scripts **may** serve as a role's real execution means (subject to §4.5 distinct model invocation, §4.8 role completion criteria, and §8.3); merely running a generic command without role-specific `assignment` / `input` / `output` / `evidence` does **not** count as a role's execution.

### §8.4 Receipt Linkage

This contract **does not** fix receipt counts. Each applicable gate produces an associable, auditable receipt / trace / verdict / closeout artifact. The canonical governance fields, authority matrix, and lineage rules for Artifact / Evidence / Packet / Receipt objects are provisionally fixed in §10.3 (status: `PROVISIONAL_ARTIFACT_EVIDENCE_SCHEMA_PENDING_POST_REMEDIATION_GRAY4_VALIDATION`). Physical storage, file format, and ledger implementation details live in the runtime / evidence spec.

### §8.5 Evidence Levels

`VERIFIED_CURRENT` / `VERIFIED_HISTORICAL` / `IMPLEMENTED_UNVERIFIED` / `PARTIAL` / `UNKNOWN` / `BLOCKED` / `MISSING` / `OUTPUT_COMPLETE_BUT_UNVERIFIED`.

`OUTPUT_COMPLETE_BUT_UNVERIFIED`: the current role or step has produced output, but due to model quota exhaustion, subsequent verification not yet executed, or another recorded STOP reason, a verified / `PASS` conclusion cannot yet be formed. This status **must not** be interpreted as `PASS`, `VERIFIED_CURRENT`, or task completion. When verification is completed after recovery, the status must be updated through new evidence linked to the original run / checkpoint.

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
- **does not** satisfy the future operator-approved operational workflow, canonical E2E, FULL-mode 9-role, dual-tester / dual-reviewer, and **no-assignment-level-fallback** requirements;
- **must not** be reinterpreted as V2-compliant E2E PASS;
- any current verdict referencing them must carry the banner above.

References to "no-fallback" in this document mean **no assignment-level fallback** (§3.5.11, §7.5). The §3.5 same-node transport-route failover remains a permitted transport behaviour, not an assignment-level fallback.

### §8.9 Cluster Construction Operation (`CLUSTER_CONSTRUCTION_OPERATION`)

Until operator explicitly accepts the canonical runtime and detailed operational workflow, and declares `OPERATIONAL_PHASE` cutover, all **build / audit / remediate / validate** operations are uniformly labelled `CLUSTER_CONSTRUCTION_OPERATION`:

- such actions **must not** be claimed as V2-compliant VibeCoding tasks, complete 9-role executions, or canonical E2E PASS;
- such actions **remain subject to** operator decision authority, explicit authorisation, **no-assignment-level-fallback**, Failure STOP (§7), evidence levels (§8.5), historical / current distinction (§8.6, §8.8), and high-risk double-confirmation (§9.3);
- **after** operator explicitly accepts the canonical runtime/workflow and declares `OPERATIONAL_PHASE` cutover, every VibeCoding task classified as `FULL_9_ROLE_VIBECODING` must run the full 9-role (§4.3); `LIGHTWEIGHT_OPERATION` and `VIBECODING_CONSULTATION_ONLY` follow their respective mode rules;
- this transitional label **must not** be used to bypass the 9-role, gates, evidence, or operator checkpoints that apply after operator accepts the canonical runtime/workflow and declares `OPERATIONAL_PHASE` cutover.

---

## §9. Operator Mandatory Checkpoints

(Interlocks with §1 GP-1 / GP-2 / GP-3. **§9.4 bounded-authorisation packages cannot substitute for operator's explicit per-role node + model specification.**)

### §9.1 A. Role Assignment

Operator **must** explicitly specify node + model for every actual non-orchestrator role in the operator-selected execution mode **after** VC8 sub-mode selection and **before** Work Order generation (§4.1, §5), where applicable.

  - `FULL_9_ROLE_VIBECODING`: operator approves the 8 non-orchestrator roles item by item, forming `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`.
  - `LIGHTWEIGHT_OPERATION`: operator approves the actual non-orchestrator role set item by item, forming `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`.
  - `VIBECODING_CONSULTATION_ONLY` and the two dedicated governance gates (§3.8, §6.9): do **not** enter role assignment; a consultation-only Work Order is generated without a baseline. The operator **must** review, modify, approve, or reject the Work Order. VC8 sub-mode selection does **not** substitute for Work Order approval.

### §9.2 B. PR Workflow

When a PR is needed, **default** to creating a **Draft PR** only. The Draft PR is the default auto endpoint of `LIGHTWEIGHT_OPERATION` and `FULL_9_ROLE_VIBECODING` runs (§4.1). After Draft PR creation or update, STOP and report URL, head SHA, changed files, applicable verification / review verdicts, role completion reports (§4.8, §4.13), risks, and open items. After Draft, original Work Order automatic authority terminates (§4.16.14); `vibedev` / `git-integrator` **must not** continue any action without new operator decision. V2 landing requires **two mandatory independent authorisations**: `Draft → Ready` (`OPERATOR_AUTHORIZED_DRAFT_TO_READY` + `POST_DRAFT_GIT_INTEGRATOR_BINDING` + `READY_TRANSITION_ROLE_INVOCATION` + `READY_TRANSITION_COMPLETION_REPORT` cross-verified → mutually-exclusive PASS_CLAIM branch: `PR_READY_VERIFIED` / FAIL_CLAIM branch: `READY_TRANSITION_VERIFICATION_FAIL`) and `merge` (`OPERATOR_AUTHORIZED_MERGE` + `POST_DRAFT_GIT_INTEGRATOR_BINDING` + `MERGE_ROLE_INVOCATION` + `MERGE_APPROVAL_PACKET` generated only on explicit operator request + `MERGE_COMPLETION_REPORT` cross-verified → mutually-exclusive PASS_CLAIM branch: `MERGE_DELIVERY_VERIFIED` + `POST_MERGE_VERIFICATION_PASS` → `MERGE_OPERATION_ENDPOINT_REACHED` / FAIL_CLAIM branch: `POST_MERGE_VERIFICATION_FAIL`). Branch Deletion is an **optional third Post-Draft operation**, default off, that **does not** block V2 landing and executes only on a separate `OPERATOR_AUTHORIZED_BRANCH_DELETION` (with `POST_DRAFT_GIT_INTEGRATOR_BINDING` + `BRANCH_DELETION_ROLE_INVOCATION` + `BRANCH_DELETION_COMPLETION_REPORT` cross-verified → success-only endpoint `BRANCH_DELETION_VERIFIED` → `BRANCH_DELETION_OPERATION_ENDPOINT_REACHED`). Merge authorisation / success **must not** imply Branch Deletion authorisation. Each Post-Draft operation's `*_COMPLETION_REPORT` must pass `vibedev` cross-verification before the corresponding `*_VERIFIED` and endpoint state may be formed; Ready/Merge PASS / FAIL paths are mutually exclusive and FAIL must not form a success endpoint.

  - `FULL_9_ROLE_VIBECODING`: report dual-tester / dual-reviewer verdicts.
  - `LIGHTWEIGHT_OPERATION`: report the operator-approved actual verifier / reviewer verdicts.
  - Dedicated governance gates (§3.8, §6.9): report the corresponding qualification and closeout results.
  - Items not applicable to the selected entry must carry an explicit `NOT_APPLICABLE` verdict. Dual-tester / dual-reviewer verdicts **must not** be fabricated for entries that do not require them.

Only operator's explicit authorisation may move Draft → Ready. Merge requires separate authorisation.

### §9.3 C. High-Risk Action Double Confirmation

First confirmation authorises **only** preparation, checking, planning, or dry-run. Before execution, re-present to operator: target, action, impact, current SHA / state, rollback plan.

The high-risk action list (non-exhaustive):

- Draft → Ready;
- merge;
- force-push;
- destructive branch operations;
- real `--apply`;
- node add / remove / transport change;
- permission modification;
- service / gateway restart;
- destructive commands;
- out-of-scope production changes;
- `Hermes` / `OpenCode` install, update, downgrade, configuration migration, restart, or version switch (per §3.8 HERMES_OPENCODE_VERSION_GOVERNANCE_GATE);
- Central Model Pool write, provider / model / alias / endpoint change, node sync / distribution, secret overlay write or distribution (per §6.9 CENTRAL_MODEL_POOL_GOVERNANCE_GATE);

Retry / repair actions trigger §9.3 **only** when they themselves fall within the list above, or when operator explicitly marks them as high-risk in the new decision. Ordinary, read-only, or scope-bounded retries — after a failure STOP — still **must** await a new explicit operator decision; they do not become high-risk merely by virtue of being labelled "retry".

`Draft → Ready` and merge are explicitly governed by §4.16.15 / §4.16.16 and §4.16.17 respectively, including exact-binding authorisations, preflight, and post-action STOP endpoints.

**Work Order endpoint constraint (canonical, per §4.17.10).** `OPERATOR_APPROVED_WORK_ORDER` + (optional) `OPERATOR_APPROVED_IMPLEMENTATION_PLAN` are the **only** automatic execution authorisations inside `VIBECODING_MODE`. A Work Order **must not** include any Post-Draft authorisation: `draft_to_ready=false`, `merge=false`, `branch_deletion=false`. The automatic endpoint is mode-discriminated:

  - **Execution-type (FULL / LIGHTWEIGHT)**: `DRAFT_PR_DELIVERY_VERIFIED → WORK_ORDER_AUTOMATIC_ENDPOINT_REACHED → STOP`.
  - **Consultation-only**: `CONSULTATION_DELIVERABLE + CONSULTATION_REPORT → CONSULTATION_OPERATION_ENDPOINT_REACHED → STOP`.

Post-Draft operations (Draft → Ready, Merge, Branch Deletion) require separate independent operator authorisations issued **after** `DRAFT_PR_DELIVERY_VERIFIED`; they are **not** part of the Work Order. Consultation-only **must not** be interpreted as having a Draft PR or Post-Draft chain.

### §9.4 D. Bounded Authorisation Package

Operator may grant a one-shot bounded authorisation package containing: task ID, approved assignment, node + model and call limits, SSH command classes, read / write paths, Git scope, forbidden actions, valid boundaries, acceptance criteria. Routine calls **within** the package need no further confirmation; **out-of-scope**, **node / model swap**, or **§9.3-trigger** actions → STOP and re-request authorisation.

**§9.4 cannot override** §9.1 A, §9.2 B, §9.3 C, §1 GP-1 / GP-2 / GP-3. **§9.4 cannot pre-include automatic retry** (§7.6). A bounded authorisation package **must not** be interpreted as bypassing operator approval for the applicable execution entry's role assignment or gate requirements.

**Coordination with §4.12.** A bounded authorisation package may include a Work Order pre-approved bounded corrective loop (§4.12) only if the loop itself is explicitly enumerated in the package — start / end roles, trigger conditions, per-path rounds, global rounds, evidence, STOP conditions. Generic "bounded retry" wording without such enumeration does **not** authorise a loop.

---

## §10. Drift, Efficiency, Maintenance

### §10.1 Drift / STOP / Audit Signal Catalog

**Canonical signal ID.** Every catalog entry in this section is uniquely identified by its full backtick `signal_id` (uppercase snake_case). The canonical backtick ID is the **only** `drift_signal_id` for authorisation, receipt, validator, audit, report, and cross-reference purposes. Any parenthetical letter / alphanumeric values after the description are `legacy_display_index` metadata, retained one-to-one for historical traceability only; **must not** be used as an ID, validator receipt key, audit ref, report locator, or cross-reference.

**Catalog standard.** Every entry follows the canonical schema:

```
- `SIGNAL_ID` — description [legacy_display_index=(x), signal_kind=KIND]
```

where `KIND` is one of:

  - `DRIFT_STOP` — current-execution drift that triggers immediate STOP;
  - `HARD_STOP` — non-drift hard failure (independently STOP-triggering);
  - `RECOVERY_BUDGET_STOP` — recovery / retry / budget exhaustion STOP;
  - `AUDIT_DEVIATION` — historical audit-trail deviation only; **must not** trigger new execution STOP;
  - `AUDIT_UNKNOWN` — unknown / unverifiable historical audit state; **must not** be claimed as current pass/fail;
  - `FAIL_CLOSED_SUCCESS` — fail-closed stop that is the correct behaviour for the agent; **must not** be treated as a new drift or re-triggered.

Only `DRIFT_STOP`, `HARD_STOP`, and `RECOVERY_BUDGET_STOP` kinds form a current-execution STOP. `AUDIT_DEVIATION`, `AUDIT_UNKNOWN`, and `FAIL_CLOSED_SUCCESS` are historical / protective record states and **must not** be reinterpreted as new drift or success endpoint.

**Machine-parseable rule.** Any entry that is missing the canonical backtick `signal_id` or has its canonical ID determined only by `legacy_display_index` is invalid. After this round the catalog contains exactly 235 top-level entries, 235 unique canonical signal IDs, 56 unique one-to-one legacy indices, 0 duplicate canonical ID, 0 parenthetical-only definition, 0 nonstandard subject definition, and 0 logical-entry content after metadata suffix.
- `PROFILE_TREATED_AS_NODE` — treating a profile as a node; [legacy_display_index=(a), signal_kind=DRIFT_STOP]
- `ROLE_TRIMMING_OR_SUBSTITUTION` — role trimming — trimming the roles / gates required by the operator-selected entry constitutes drift. `FULL_9_ROLE_VIBECODING`: complete 9-role must not be trimmed. `LIGHTWEIGHT_OPERATION`: executes operator-approved actual role set. Named-but-not-executed, no distinct model invocation, shared invocation across roles, multi-role response reuse, and generic-command-only role completion are all drift; [legacy_display_index=(b), signal_kind=DRIFT_STOP]
- `SIMULATION_TREATED_AS_REAL_EXECUTION` — substituting simulation for real execution; [legacy_display_index=(c), signal_kind=DRIFT_STOP]
- `HISTORICAL_EVIDENCE_TREATED_AS_CURRENT` — historical evidence treated as current; [legacy_display_index=(d), signal_kind=DRIFT_STOP]
- `AGENT_SELF_CLAIMED_AS_OPERATOR_ACCEPTANCE` — agent self-claim treated as operator acceptance; [legacy_display_index=(e), signal_kind=DRIFT_STOP]
- `WORKFLOW_BYPASS_UNAUTHORISED_WRAPPER_OR_AD_HOC` — workflow bypass (unauthorised wrapper / manual SSH / ad-hoc model call outside the future operator-approved operational workflow spec); during `CLUSTER_CONSTRUCTION_OPERATION`, judgement follows explicit authorisation, Failure STOP (§7), and evidence boundaries (§8); [legacy_display_index=(f), signal_kind=DRIFT_STOP]
- `AUTHORISATION_EXPANSION` — authorisation expansion (extending a one-shot authorisation to later stages); [legacy_display_index=(g), signal_kind=DRIFT_STOP]
- `ASSIGNMENT_LEVEL_AUTOMATIC_FALLBACK_OR_NODE_MODEL_SWAP` — assignment-level automatic fallback / automatic node / model swap; [legacy_display_index=(h), signal_kind=DRIFT_STOP]
- `DEFAULT_SUBSTITUTE_USED_FOR_UNSPECIFIED_ROLE` — using a default substitute (including auto-picking a default model / node for an unspecified role); [legacy_display_index=(i), signal_kind=DRIFT_STOP]
- `AUTOMATIC_ASSIGNMENT_REWRITE_BY_ORCHESTRATOR` — automatic assignment rewrite (orchestrator modifying operator's specification); [legacy_display_index=(j), signal_kind=DRIFT_STOP]
- `SCOPE_SHRINKING_CONTINUATION` — scope-shrinking continuation (partial-execute forming pass-by-omission); [legacy_display_index=(k), signal_kind=DRIFT_STOP]
- `PARTIAL_EXECUTION_OF_OTHER_ROLES` — continuing other unaffected roles into partial completion; [legacy_display_index=(l), signal_kind=DRIFT_STOP]
- `ORCHESTRATOR_UNILATERAL_PATH_CHOICE` — orchestrator unilaterally choosing an alternative path; [legacy_display_index=(m), signal_kind=DRIFT_STOP]
- `ALTERNATIVE_FIELD_PRESENT_IN_RECOMMENDATION_MATRIX` — presence of an `alternative` field in the recommendation matrix; [legacy_display_index=(n), signal_kind=DRIFT_STOP]
- `HISTORICAL_EVIDENCE_REINTERPRETED_AS_V2_COMPLIANT_PASS` — historical evidence reinterpreted as V2-compliant E2E PASS; [legacy_display_index=(o), signal_kind=DRIFT_STOP]
- `PRE_V2_HISTORICAL_EVIDENCE_BANNER_MISSING` — cited without the banner `PRE_V2_HISTORICAL_EVIDENCE — not V2-compliant E2E evidence` per §8.8; [signal_kind=DRIFT_STOP]
- `RUNTIME_MODIFIED_OPERATOR_ASSIGNMENT_BYPASSING_GP2` — runtime modifying operator-approved assignment or bypassing §1 GP-2; [legacy_display_index=(q), signal_kind=DRIFT_STOP]
- `RUNTIME_AUTO_SWAPPED_ORCHESTRATOR_MODEL` — runtime auto-swapping the orchestrator model (§4.3); [legacy_display_index=(r), signal_kind=DRIFT_STOP]
- `CONTINUED_ON_ORCHESTRATOR_MODEL_UNAVAILABILITY_WITHOUT_STOP` — continuing on orchestrator-model unavailability without STOP; [legacy_display_index=(s), signal_kind=DRIFT_STOP]
- `BOUNDED_AUTHORISATION_PACKAGES_PREINCLUDED_AUTO_RETRY` — bounded authorisation packages pre-including automatic retry (§7.6, §9.4); [legacy_display_index=(t), signal_kind=DRIFT_STOP]
- `TEST_OR_FIXTURE_EVIDENCE_CITED_AS_V2_E2E_PASS` — test or fixture evidence cited as V2 E2E PASS (§8.3, §4.5 distinct model invocation, §4.8 role completion criteria); [legacy_display_index=(u), signal_kind=DRIFT_STOP]
- `GENERIC_COMMAND_ALONE_COUNTED_AS_ROLE_EXECUTION` — merely running a generic command counted as a role execution (§4.5 distinct model invocation, §4.8 role completion criteria); [legacy_display_index=(v), signal_kind=DRIFT_STOP]
- `CONSTRUCTION_PHASE_BYPASS_OF_OPERATIONAL_GOVERNANCE` — used to bypass the 9-role / gates / evidence / checkpoints that apply after operator accepts the canonical runtime/workflow and declares `OPERATIONAL_PHASE` cutover (§8.9); [signal_kind=DRIFT_STOP]
- `BINDING_CLUSTER_TO_SINGLE_FIXED_HERMES_OPENCODE_VERSION` — binding the cluster to a single fixed `Hermes` / `OpenCode` version without qualification (§3.8 HERMES_OPENCODE_VERSION_GOVERNANCE_GATE); [legacy_display_index=(p), signal_kind=DRIFT_STOP]
- `CLAIMING_COMPATIBILITY_WITHOUT_VERIFICATION` — claiming compatibility without verification / reusing stale qualification evidence / auto-expanding scope after single-node canary (§3.8 HERMES_OPENCODE_VERSION_GOVERNANCE_GATE); [legacy_display_index=(y), signal_kind=DRIFT_STOP]
- `GOVERNANCE_GATE_USED_TO_DOWNGRADE_BUSINESS_TASK` — using a dedicated governance gate (§3.8, §6.9) to downgrade a business task, bypass operator, bypass Failure STOP, bypass evidence requirements, bypass public secret boundary, or convert a business task into a governance-only operation (§4.2); [legacy_display_index=(z), signal_kind=DRIFT_STOP]
- `CONTINUING_AFTER_NODE_VERIFICATION_FAILURE_WITHOUT_APPROVAL` — continuing assignments after a node-verification failure without operator approval; [legacy_display_index=(aa), signal_kind=DRIFT_STOP]
- `BARE_CONSTANT_VERDICT_WITHOUT_SUBSTANTIVE_INVOCATION` — bare constant verdict — using `NO_CHANGE_REQUIRED`, `NOT_APPLICABLE`, or `NO_GIT_WRITE_REQUIRED` without a prior substantive model invocation, evidence analysis, reason, scope, and evidence references (§4.6); [legacy_display_index=(bb), signal_kind=DRIFT_STOP]
- `TOOL_ONLY_COMPLETION_WITHOUT_DISTINCT_MODEL_INVOCATION` — tool-only completion — claiming a role is complete based solely on deterministic tools, scripts, `pytest`, Git, SSH, file reads, or static analysis, without the role's own distinct model invocation (§4.4, §4.5); [legacy_display_index=(cc), signal_kind=DRIFT_STOP]
- `HERMES_OPENCODE_VERSION_SWITCH_USED_TO_EVADE_STOP` — using `Hermes` / `OpenCode` version switching to evade Failure STOP or operator checkpoints (§3.8.12); [legacy_display_index=(dd), signal_kind=DRIFT_STOP]
- `HARDCODED_SINGLE_VERSION_CLI_PATH_SCHEMA_IN_GOVERNANCE` — hardcoding a single version / CLI / path / schema in core governance or runtime without adaptation (§3.8.11); [legacy_display_index=(ee), signal_kind=DRIFT_STOP]
- `NON_REGISTERED_OR_UNQUALIFIED_ROUTE_IN_TRANSPORT_FAILOVER` — using a non-registered or unqualified route in §3.5 transport-route failover; [legacy_display_index=(ff), signal_kind=DRIFT_STOP]
- `AUTH_OR_IDENTITY_OR_APP_ERROR_MISCLASSIFIED_AS_TRANSPORT_FAILURE` — mis-classifying an auth / identity / application error as transport-path failure (§3.5.6) and switching routes anyway; [legacy_display_index=(gg), signal_kind=DRIFT_STOP]
- `TRANSPORT_ROUTE_SWITCH_THAT_CHANGES_NODE_OR_MODEL_OR_ASSIGNMENT` — §3.5 route switch that changes node / model / role / assignment / credential / scope (§3.5.11); [legacy_display_index=(hh), signal_kind=DRIFT_STOP]
- `TRANSPORT_ROUTE_SWITCH_INTO_ANOTHER_NODE` — §3.5 switch into another node's route; [legacy_display_index=(ii), signal_kind=DRIFT_STOP]
- `SUSPENDED_OR_OFFLINE_NODE_RESTORED_VIA_ROUTE_FAILOVER` — restoring a `SUSPENDED` / `OFFLINE` / `NOT_ASSIGNABLE` / unqualified node to `ACTIVE` via route failover or any other automatic channel; [legacy_display_index=(jj), signal_kind=DRIFT_STOP]
- `CONTINUED_ROUTE_RETRY_AFTER_CHAIN_EXHAUSTED` — continuing to try routes after the chain is exhausted (§3.5.9); [legacy_display_index=(kk), signal_kind=DRIFT_STOP]
- `ROUTE_CHAIN_MODIFIED_WITHOUT_OPERATOR_APPROVAL` — modifying the route chain without operator approval (§3.5.10); [legacy_display_index=(ll), signal_kind=DRIFT_STOP]
- `TRANSPORT_FAILOVER_INTERPRETED_AS_NODE_OR_MODEL_CHANGE` — interpreting §3.5 transport-route failover as covering node / model / role / assignment / credential / scope changes; [legacy_display_index=(mm), signal_kind=DRIFT_STOP]
- `SSOBAO_OR_9BAO_TAKING_OVER_21BAO_CONTROL_PLANE` — `5bao` / `9bao` taking over `21bao` control plane; [legacy_display_index=(nn), signal_kind=DRIFT_STOP]
- `AUTOMATIC_ORCHESTRATOR_MIGRATION` — automatic orchestrator migration; [legacy_display_index=(oo), signal_kind=DRIFT_STOP]
- `CONTINUING_VIBECODING_WITH_21BAO_UNAVAILABLE` — continuing VibeCoding tasks while `21bao` is unavailable; [legacy_display_index=(pp), signal_kind=DRIFT_STOP]
- `21BAO_NETWORK_FAILOVER_INTERPRETED_AS_CONTROL_PLANE_FAILOVER` — mis-interpreting `21bao`'s network route failover as control-plane failover; [legacy_display_index=(qq), signal_kind=DRIFT_STOP]
- `REOPENING_21BAO_DISPATCH_BEFORE_3_6_7_PASSES` — re-opening `21bao` VibeCoding dispatch before every item in §3.6.7 passes (§3.6.7); [legacy_display_index=(rr), signal_kind=DRIFT_STOP]
- `CREDENTIAL_DISCOVERY_PRINTS_VALUE_OR_OUTPUTS_SECRET_FRAGMENTS` — credential discovery that prints a value-bearing environment map, or outputs secret-derived fragments into public / external / uncontrolled scope, or private operator-controlled output beyond the operator-approved operational scope (§6.6); [legacy_display_index=(ss), signal_kind=DRIFT_STOP]
- `PUBLIC_TOKEN_PREFIX_MARKER_TREATED_AS_CREDENTIAL_VALUE` — treating a public-format token prefix marker as the credential value (§6.6); [legacy_display_index=(tt), signal_kind=DRIFT_STOP]
- `CREDENTIAL_AUTO_ROTATED_OR_REPLACED_WITHOUT_AUTHORISATION` — auto-rotating, auto-replacing, or auto-invalidating a credential without explicit operator authorisation (§6.6); [legacy_display_index=(uu), signal_kind=DRIFT_STOP]
- `MODEL_QUOTA_EXHAUSTED_TREATED_AS_TRANSPORT_FAILURE` — treating `MODEL_QUOTA_EXHAUSTED` as a transport-path failure and triggering route fallback (§3.5.13); [legacy_display_index=(vv), signal_kind=DRIFT_STOP]
- `AUTOMATIC_MODEL_NODE_PROVIDER_CREDENTIAL_SUBSTITUTION_ON_QUOTA` — automatic model / node / provider / credential / account substitution upon quota exhaustion (§5.10); [legacy_display_index=(ww), signal_kind=DRIFT_STOP]
- `AUTOMATIC_RETRY_OR_SCOPE_REDUCTION_ON_QUOTA_EXHAUSTION` — automatic retry, wait, or scope reduction upon quota exhaustion (§5.10); [legacy_display_index=(xx), signal_kind=DRIFT_STOP]
- `CONTINUING_ROLES_AFTER_A_ROLE_MODEL_QUOTA_EXHAUSTED` — continuing subsequent roles after a role's model is quota-exhausted (§5.10); [legacy_display_index=(yy), signal_kind=DRIFT_STOP]
- `ORCHESTRATOR_QUOTA_EXHAUSTION_HANDLED_BY_WORKER_TAKEOVER` — orchestrator model quota exhaustion handled by worker / reviewer takeover (§5.11). [legacy_display_index=(zz), signal_kind=DRIFT_STOP]
- `READINESS_EXPANDING_OR_REPLACING_OPERATOR_AUTHORISATION` — readiness expanding or replacing operator authorisation (§4.1, §4.10, §5.14); [legacy_display_index=(aaa), signal_kind=DRIFT_STOP]
- `READINESS_PROBE_TREATED_AS_ROLE_INVOCATION_OR_EVIDENCE` — treating a readiness probe as a role's distinct model invocation or completion evidence (§4.5, §4.7, §4.8, §4.10); [legacy_display_index=(bbb), signal_kind=DRIFT_STOP]
- `BOUNDED_CORRECTIVE_LOOP_USED_OUTSIDE_PRE_APPROVED_PATH` — using §4.12 bounded corrective loop outside its pre-approved path, exceeding budget, expanding scope, swapping node / model / provider, auto-escalating `LIGHTWEIGHT_OPERATION` to `FULL_9_ROLE_VIBECODING`, or entering a VERSION / CMP gate; [legacy_display_index=(ccc), signal_kind=DRIFT_STOP]
- `LOOP_STAGNATION_CONTINUED_WITHOUT_STOP` — (§4.12) continued without STOP; [signal_kind=DRIFT_STOP]
- `ROLE_SELF_ANNOUNCING_VERIFIED_FINAL_WITHOUT_CROSS_VERIFICATION` — role self-announcing "verified" / "final" without orchestrator cross-verification (§4.13); [legacy_display_index=(eee), signal_kind=DRIFT_STOP]
- `IGNORING_ARTIFACT_INVALIDATION_OR_USING_SUPERSEDED_FOR_PASS` — ignoring artifact invalidation, using superseded or invalidated artifacts as current PASS evidence, or omitting the invalidation manifest (§4.14). [legacy_display_index=(fff), signal_kind=DRIFT_STOP]
- `ORCHESTRATOR_ROLE_SUBSTITUTION_DETECTED` — orchestrator analysis, summary, or call counted as `explorer` or `planner` execution (§4.15.1); [signal_kind=DRIFT_STOP]
- `ORCHESTRATOR_AUTHORED_EXPLORER_FINDING` — orchestrator produced, paraphrased, or completed any `explorer` fact base item **without source attribution, changing meaning, or filling in business conclusions** (§4.15.1). Faithful, traceable summarisation or compression in a validation report or approval packet that references the source artifact ID / version / digest and does **not** add technical meaning does **not** trigger this signal; [signal_kind=DRIFT_STOP]
- `ORCHESTRATOR_AUTHORED_PLAN_ITEM` — orchestrator added or rewrote `planner` implementation steps, file scope, test plan, risk, or rollback **without source attribution, changing meaning, or filling in business plan content** (§4.15.1). Faithful, traceable summarisation or compression in a validation report or approval packet that references the source artifact ID / version / digest and does **not** add technical meaning does **not** trigger this signal; [signal_kind=DRIFT_STOP]
- `ROLE_ARTIFACT_MUTATED_BY_VALIDATOR` — validator (or any party outside the originating role's own reattempt) modified the original Explorer / Planner artifact (§4.15.2); [signal_kind=DRIFT_STOP]
- `VALIDATION_PROVENANCE_VIOLATION` — `EXPLORER_VALIDATION_REPORT` / `PLAN_VALIDATION_REPORT` / `ROLE_COMPLETION_REPORT` / `IMPLEMENTATION_PLAN_APPROVAL_PACKET` referencing an artifact version that does not match the originating role's recorded version (§4.13, §4.15.2, §4.15.3); [signal_kind=DRIFT_STOP]
- `SHARED_OR_REUSED_ROLE_OUTPUT_DETECTED` — single model invocation, response, or summary counted as multiple roles' distinct invocation, or output reused across `explorer` and `planner` (§4.5, §4.15.1); [signal_kind=DRIFT_STOP]
- `IMPLEMENTATION_PLAN_PACKET_EXPANSION_OF_SCOPE` — expanding Work Order scope, permissions, sub-mode, assignment, node / model / provider, or governance boundary (§4.15.3); [signal_kind=DRIFT_STOP]
- `FULL_9_ROLE_IMPLEMENTER_ACTIVATED_BEFORE_PLAN_APPROVAL` — `implementer` activation before `OPERATOR_APPROVED_IMPLEMENTATION_PLAN` (§4.15.3). [signal_kind=DRIFT_STOP]
- `CANDIDATE_MUTATED_AFTER_FREEZE` — any role modifying the frozen `IMPLEMENTATION_CANDIDATE` in-place (§4.16.2); [signal_kind=DRIFT_STOP]
- `DUAL_TESTER_INDEPENDENCE_VIOLATION` — tester-a and tester-b sharing session, context, prompt, invocation, output, or evidence, or one reading the other's intermediate work before its own first report is frozen (§4.16.3); [signal_kind=DRIFT_STOP]
- `DUAL_REVIEWER_INDEPENDENCE_VIOLATION` — reviewer-a and reviewer-b sharing session, context, prompt, invocation, output, or evidence, or one reading the other's intermediate work before its own first report is frozen (§4.16.5); [signal_kind=DRIFT_STOP]
- `GATE_MAJORITY_VOTE_BYPASS` — treating a tester or reviewer `FAIL` as overridden by majority vote, compromise, or orchestrator override (§4.16.4, §4.16.5); [signal_kind=DRIFT_STOP]
- `ORCHESTRATOR_TEST_OR_REVIEW_SUBSTITUTION_DETECTED` — `vibedev` performing testing, supplementing business conclusions, choosing to believe one tester/reviewer over the other, performing review, or overriding an evidence-backed blocking opinion (§4.16.4, §4.16.5); [signal_kind=DRIFT_STOP]
- `PREMATURE_GIT_INTEGRATION` — `git-integrator` performing formal Git write before the mode-appropriate pre-Git gates are all valid for the current CANDIDATE_TRIPLE (§4.16.7): FULL without both `TEST_GATE_PASS` and `REVIEW_GATE_PASS`; LIGHTWEIGHT without all Work Order `required_pre_git_gates` valid, with any Gate member empty, without at least one independent verifier Gate `PASS`, or with any source artifact invalidated. [signal_kind=DRIFT_STOP]
- `CANDIDATE_PLAN_PROVENANCE_MISSING` — `IMPLEMENTATION_CANDIDATE` missing required plan source binding per sub-mode (§4.16.2). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `OPERATOR_PLAN_APPROVAL_BYPASSED` — CANDIDATE_TRIPLE formed without valid operator approval evidence where required (§4.16.2). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `LIGHTWEIGHT_PLAN_SOURCE_MISMATCH` — `LIGHTWEIGHT` CANDIDATE_TRIPLE plan source does not match the Work Order's Plan checkpoint setting (§4.16.2). Return to correct binding; if unresolvable within pre-approved budget, STOP. [signal_kind=DRIFT_STOP]
- `TEST_CONTRADICTION_MISROUTED` — `TEST_CONTRADICTION_PACKET` returned to a role that cannot fix the root cause (§4.16.4). Re-route per §4.16.4 root-cause routing; if unresolvable within pre-approved budget, STOP. [signal_kind=DRIFT_STOP]
- `LIGHTWEIGHT_UNAPPROVED_ROLE_IMPLIED` — §4.15 or §4.16 governance implicitly requiring a role not in the operator-approved actual role set (§4.1.2, §4.15, §4.16). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `LIGHTWEIGHT_DIRECT_IMPLEMENTATION_PROVENANCE_MISSING` — LIGHTWEIGHT without Planner / Plan checkpoint but CANDIDATE_TRIPLE missing `OPERATOR_APPROVED_WORK_ORDER` binding or `direct_to_implementer=true` approval field (§4.16.2). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `LIGHTWEIGHT_REQUIRED_GATE_SET_MISMATCH` — LIGHTWEIGHT pre-Git gate set does not match Work Order `required_pre_git_gates` (§4.16.7). If unresolvable within pre-approved budget, STOP. [signal_kind=DRIFT_STOP]
- `UNAUTHORISED_CONTENT_AUTHOR_ROLE` — explorer, tester, reviewer, verifier, or git-integrator writing business content. Content-author roles must be independently operator-approved as such; the same role identity **must not** simultaneously serve as tester, verifier, or reviewer for its own output. **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CONTENT_AUTHOR_SELF_VALIDATION_COUNTED` — content-author role's self-test invocation, report, or output counted into a required Gate, or implementer self-check used to form `TEST_GATE` / verification Gate / review Gate (§4.1.2). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `GIT_INTEGRATION_INPUT_INVALID` — `GIT_INTEGRATION_INPUT_PACKET` source artifact invalidated, scope/assignment drifted, or packet content changed before Git write (§4.16.9). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `BROAD_STAGE_OPERATION_DETECTED` — `git add .`, `git add -A`, or `git commit -am` used instead of exact staging per CANDIDATE_TRIPLE manifest (§4.16.10). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CANDIDATE_COMMIT_TREE_MISMATCH` — final commit tree does not match frozen CANDIDATE_TRIPLE content tree (§4.16.10). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `COMMIT_MESSAGE_EVIDENCE_MISMATCH` — **pre-commit:** commit message inconsistent with the `PUBLIC_SAFE_EVIDENCE_PROJECTION_DRAFT`, CANDIDATE_TRIPLE, Gate verdicts, diffstat, and test evidence (§4.16.10). **Immediate STOP** — must not commit. **Post-commit / PR update:** commit message inconsistent with the final `DRAFT_PR_EVIDENCE_BODY` non-Git-derived facts, diffstat, test numbers, or Gate status (§4.16.10). **Immediate STOP** — operator decides subsequent scope; do **not** amend. Only Git-derived fields (commit SHA / tree, remote, PR facts) are permitted to differ between draft and final body; [signal_kind=DRIFT_STOP]
- `REMOTE_BASE_DRIFT` — remote base SHA changed from expected value (§4.16.11). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `REMOTE_TARGET_HEAD_DRIFT` — remote target head SHA changed from expected value (§4.16.11). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `UNVERIFIED_PUSH_RETRY` — push retry attempted without first reading remote head to verify delivery state (§4.16.11). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `UNVERIFIED_PR_API_RETRY` — Draft PR create / update API retry attempted without first querying the PR by repository / head / base / Work Order identity to verify actual state (§4.16.11). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `PROXY_BYPASS_BUDGET_EXCEEDED` — additional `-c http.proxy=""` bypass attempt beyond the single shared budget for the entire Git delivery operation (§4.16.11). **Immediate STOP.** [signal_kind=RECOVERY_BUDGET_STOP]
- `PUSH_RECOVERY_BUDGET_EXHAUSTED` — approved push attempts exhausted or delivery remains unverifiable after the final permitted attempt (§4.16.11). **Immediate STOP.** [signal_kind=RECOVERY_BUDGET_STOP]
- `PR_API_RECOVERY_BUDGET_EXHAUSTED` — Draft PR create / update API attempt budget exhausted (§4.16.11). **Immediate STOP.** [signal_kind=RECOVERY_BUDGET_STOP]
- `DUPLICATE_OR_WRONG_PR_TARGET` — multiple PR matches, already Ready/closed/merged, base mismatch, or PR occupied by another task (§4.16.12). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `PUBLIC_EVIDENCE_SECRET_LEAK` — any public-facing Git metadata (branch name, commit message, PR title, `PUBLIC_SAFE_EVIDENCE_PROJECTION_DRAFT`, final `DRAFT_PR_EVIDENCE_BODY`, or other public artefact) contains credentials, tokens, private logs, unapproved host / IP / username details, absolute paths, sensitive env values, or internal model prompts (§4.16.12). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `PUBLIC_GIT_METADATA_SAFETY_CHECK_MISSING` — public-facing Git metadata committed / pushed / created / updated without a `PUBLIC_SAFE_GIT_METADATA_CHECK` run before the public action (§4.16.12). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `DRAFT_PR_DELIVERY_UNVERIFIED` — post-push independent verification incomplete or failed (§4.16.12). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `READY_OR_MERGE_WITHOUT_AUTHORIZATION` — Draft→Ready or merge attempted without operator authorisation, or authorisation invalidated by head/body/evidence change (§4.16.13). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `APPROVED_NEW_FILE_OMITTED_FROM_STAGE` — CANDIDATE_TRIPLE manifest includes approved new paths but `git-integrator` omitted them from staging (§4.16.10). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `UNAPPROVED_UNTRACKED_PATH_STAGED` — any untracked path not in the CANDIDATE_TRIPLE manifest was staged (§4.16.10). Entry-time untracked inventory and Work Order-protected paths are reference information only and do **not** constitute stage permission. Manifest-approved new paths remain permitted. **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CONSTRUCTION_UNTRACKED_LIST_LEAKED_INTO_RUNTIME_POLICY` — a construction-workspace-specific untracked path list treated as a universal runtime constant (§4.16.10). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `MODE_SPECIFIC_PLAN_PROVENANCE_MISMATCH` — Draft PR body plan source does not match the mode-appropriate provenance type (§4.16.12). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `PRECOMMIT_EVIDENCE_DRAFT_MISSING` — commit attempted without freezing a `PUBLIC_SAFE_EVIDENCE_PROJECTION_DRAFT` (§4.16.10). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `POST_DRAFT_AUTOMATION_CONTINUED` — `vibedev` / `git-integrator` continued any action after `WORK_ORDER_AUTOMATIC_ENDPOINT_REACHED` (§4.16.14). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `DRAFT_TO_READY_AUTHORIZATION_STALE` — `OPERATOR_AUTHORIZED_DRAFT_TO_READY` no longer matches PR / head / base / body / evidence / Gate / checks / blockers / mergeability / remote (§4.16.15, §4.16.16). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `READY_WITHOUT_BOUND_AUTHORIZATION` — Draft → Ready attempted without `OPERATOR_AUTHORIZED_DRAFT_TO_READY`, or authorization missing one of the required bindings (§4.16.15). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `READY_OR_MERGE_RETRY_WITHOUT_QUERY` — Ready or Merge API retry attempted without first querying PR / target state (§4.16.16, §4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `MERGE_METHOD_NOT_OPERATOR_APPROVED` — merge attempted without explicit operator-approved method (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `MERGE_AUTHORIZATION_STALE` — `OPERATOR_AUTHORIZED_MERGE` no longer matches PR / head / base / method / checks / Gate / evidence / blocker / remote (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `POST_MERGE_AUTO_REPAIR_OR_REVERT` — auto-revert, auto-fix, follow-up commit, or second merge after `POST_MERGE_VERIFICATION_FAIL` (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `UNAUTHORIZED_BRANCH_DELETION` — source branch deletion without `OPERATOR_AUTHORIZED_BRANCH_DELETION` (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `POST_DRAFT_EXECUTOR_BINDING_MISSING` — `OPERATOR_AUTHORIZED_DRAFT_TO_READY` / `OPERATOR_AUTHORIZED_MERGE` / `OPERATOR_AUTHORIZED_BRANCH_DELETION` lacks `POST_DRAFT_GIT_INTEGRATOR_BINDING` (§4.16.14). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `POST_DRAFT_ASSIGNMENT_REUSE_WITHOUT_AUTHORIZATION` — git-integrator reused original Draft assignment for Post-Draft operation without explicit operator-approved reuse binding (§4.16.14). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `READY_COMPLETION_UNVERIFIED` — `PR_READY_VERIFIED` claimed without passing `READY_TRANSITION_COMPLETION_REPORT` cross-verification (§4.16.16). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `MERGE_PACKET_GENERATED_WITHOUT_OPERATOR_REQUEST` — `MERGE_APPROVAL_PACKET` generated without explicit operator request (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `MERGE_COMPLETION_UNVERIFIED` — merge endpoint state claimed without passing `MERGE_COMPLETION_REPORT` cross-verification (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `MERGE_ENDPOINT_MISATTRIBUTED_TO_WORK_ORDER` — merge endpoint state named as `WORK_ORDER_*` (work-order misattribution); use `MERGE_OPERATION_ENDPOINT_REACHED` (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `READY_API_RECOVERY_BUDGET_EXHAUSTED` — Ready API 2-attempt budget exhausted or status unverifiable (§4.16.16). **Immediate STOP.** [signal_kind=RECOVERY_BUDGET_STOP]
- `MERGE_API_RECOVERY_BUDGET_EXHAUSTED` — merge API 2-attempt budget exhausted or status unverifiable (§4.16.17). **Immediate STOP.** [signal_kind=RECOVERY_BUDGET_STOP]
- `BRANCH_DELETION_API_RECOVERY_BUDGET_EXHAUSTED` — branch deletion API 2-attempt budget exhausted or status unverifiable (§4.16.17). **Immediate STOP.** [signal_kind=RECOVERY_BUDGET_STOP]
- `BRANCH_DELETION_AUTHORIZATION_STALE` — `OPERATOR_AUTHORIZED_BRANCH_DELETION` no longer matches repo / branch / PR / merged head / merge commit / executor binding / time (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `BRANCH_DELETION_TARGET_MISMATCH` — source branch target / merge commit drift during branch deletion (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `UNVERIFIED_BRANCH_DELETION_RETRY` — branch deletion retry attempted without prior ref query (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `PR_METADATA_OR_HEAD_MISMATCH` — local HEAD / remote branch head / PR `headRefOid` / PR body 4-way inconsistency detected before any Git write (§4.16). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `BRANCH_DELETION_COMPLETION_UNVERIFIED` — `BRANCH_DELETION_VERIFIED` claimed without passing `BRANCH_DELETION_COMPLETION_REPORT` cross-verification (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `BRANCH_DELETION_ENDPOINT_PREMATURE` — `BRANCH_DELETION_OPERATION_ENDPOINT_REACHED` formed before `BRANCH_DELETION_COMPLETION_REPORT` passes cross-verification (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `MERGE_VERIFIED_PREMATURE` — `MERGE_DELIVERY_VERIFIED` / `POST_MERGE_VERIFICATION_PASS` / `MERGE_OPERATION_ENDPOINT_REACHED` formed before `MERGE_COMPLETION_REPORT` passes cross-verification (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `ROUND36_INITIAL_PREWRITE_4WAY_VERIFICATION_UNKNOWN` — Round-36 initial pre-write 4-way verification has no recordable evidence; verdict UNKNOWN (§4.16 audit). Do **not** claim PASS. [signal_kind=AUDIT_UNKNOWN]
- `STALE_EXPECTED_HEAD_GUARD_TRIGGERED_CORRECTLY` — agent's pre-write guard correctly stopped on stale `expected current head` value from prompt; this is fail-closed success, **not** a Contract execution deviation (§4.16 audit). Recorded for audit traceability. [signal_kind=FAIL_CLOSED_SUCCESS]
- `READY_VERIFIED_PREMATURE` — `PR_READY_VERIFIED` formed before `READY_TRANSITION_COMPLETION_REPORT` passes `vibedev` cross-verification (§4.16.16). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `READY_FAIL_ENDPOINT_FORMED_AS_SUCCESS` — `READY_TRANSITION_FAIL_CLAIM` cross-verified but a success endpoint (e.g. `PR_READY_VERIFIED`) was formed anyway (§4.16.16). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `MERGE_FAIL_ENDPOINT_FORMED_AS_SUCCESS` — `POST_MERGE_VERIFICATION_FAIL_CLAIM` cross-verified but a success endpoint (`MERGE_DELIVERY_VERIFIED` / `POST_MERGE_VERIFICATION_PASS` / `MERGE_OPERATION_ENDPOINT_REACHED`) was formed anyway (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `POST_DRAFT_FORMAL_INVOCATION_EVIDENCE_MISSING` — a Post-Draft `*_COMPLETION_REPORT` lacks the formal and attributable role invocation evidence, or the invocation ID / input / output / timestamp / references cannot be independently verified, or the invocation is reused from Draft delivery or another Post-Draft operation (§4.16.16, §4.16.17). Report **must not** pass cross-verification. **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `READY_CROSS_VERIFICATION_OMITTED_IN_CHAIN` — Ready default chain or summary omits the `vibedev` cross-verification step between `READY_TRANSITION_COMPLETION_REPORT` and the verified endpoint state (§4.16.16, §13). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `MERGE_FINAL_STATE_PREMATURELY_NAMED_IN_REPORT` — `MERGE_COMPLETION_REPORT` records `POST_MERGE_VERIFICATION_PASS` / `POST_MERGE_VERIFICATION_FAIL` (final state names) instead of `*_CLAIM` (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `READY_CROSS_VERIFICATION_BRANCH_AMBIGUOUS` — Ready default chain or summary rendered as a single linear sequence with `PR_READY_VERIFIED → STOP → READY_TRANSITION_VERIFICATION_FAIL → STOP`, omitting the explicit mutually-exclusive fork (§4.16.16, §13). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `BRANCH_DELETION_CLAIM_MODEL_CONTRADICTION` — Branch Deletion model contains both a "no PASS / FAIL claim" statement and a "report may record `BRANCH_DELETION_FAIL_CLAIM`" statement without unified scope (PASS_claim absent, FAIL_claim informational only) (§4.16.17). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `OPTIONAL_BRANCH_DELETION_TREATED_AS_REQUIRED` — V2 landing or `MERGE_OPERATION_ENDPOINT_REACHED` interpretation, summary, or runtime behaviour treats the optional third Post-Draft operation (Branch Deletion) as required for V2 landing, or auto-implies deletion authorisation from Merge authorisation / success (§10.6, §4.16.17, §13). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_SCHEMA_INVALID` — Work Order fails schema validation: missing top-level object, missing required field, or field value contradicts another field (§4.17.2). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_DIGEST_MISMATCH` — `work_order_digest` does not match the digest of the supplied document body, or the operator approval binding is stale (§4.17.1, §4.17.3). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_MUTATED_AFTER_APPROVAL` — any in-place modification of an already-approved Work Order version, or execution result written back over the Work Order, or scope expanded by execution (§4.17.1). A new `document_version` / `work_order_digest` and a new operator approval are required. **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_MODE_CONTRADICTION` — Work Order `mode_and_phase` mixes business scope with `HERMES_OPENCODE_VERSION_GOVERNANCE_GATE` / `CENTRAL_MODEL_POOL_GOVERNANCE_GATE` scope, or the selected submode contradicts the assignment / readiness / endpoint (§4.17.3, §3.8, §6.9). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_SCOPE_UNBOUNDED` — `task_scope` lacks stable IDs, or any reference uses non-stable wording such as "the issue above" or "that requirement" (§4.17.4). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_ROLE_ASSIGNMENT_INCOMPLETE` — `role_topology` or `authorization_bindings` mode-discriminated check, three independent mode branches without cross-mode conditions: **`FULL_9_ROLE_VIBECODING`**: lacks non-orchestrator `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE` with all 8 non-orchestrator roles, or lacks content-author / independent-verifier / git-integrator (§4.17.3, §4.17.5); **`LIGHTWEIGHT_OPERATION`**: lacks operator-approved actual non-orchestrator roles, or includes roles outside the approved actual role set (§4.17.3, §4.17.5); **`VIBECODING_CONSULTATION_ONLY`**: **not** applicable — `CONSULTATION_WORK_ORDER_REQUIRES_ASSIGNMENT_BASELINE` is the correct signal for baseline violations in Consultation (§4.17.3, §4.17.4, §4.17.5). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_EXECUTION_GRAPH_INCOMPLETE` — `execution_graph` mode-discriminated check: **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`**: lacks stage dependencies, entry / exit criteria, FAIL return path, STOP conditions, invalidated-downstream record, or omits the canonical default graph / role return loop / Gate / CANDIDATE_TRIPLE invalidation stages where applicable (§4.17.6); **`VIBECODING_CONSULTATION_ONLY`**: lacks read-only stages, entry / exit criteria, consultation deliverable / report endpoint, or failure → STOP path. Consultation **must not** require role return loop, Gate, or CANDIDATE_TRIPLE invalidation in its execution graph. **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_GATE_TOPOLOGY_INVALID` — mode-discriminated Gate topology check, strict prohibition of majority vote (§4.17.8): **`FULL_9_ROLE_VIBECODING`** (deterministic checks): `tester-a` / `tester-b` not both bound to the same `CANDIDATE_FROZEN_FOR_TEST` ID, version, and digest; `reviewer-a` / `reviewer-b` not both bound to the same frozen `REVIEW_INPUT_PACKET` ID, version, and digest; Gate members, role, assignment, Activation, attempt, invocation, or report failing to match the operator-approved topology; missing independent invocation or report; Gate members incomplete; or allowed / used a majority vote; **`LIGHTWEIGHT_OPERATION`**: `required_pre_git_gates` empty; Gate members empty; missing verifier independent of content-author; single role covering multiple Gates without distinct Activation / attempt / charter / invocation / report / evidence; or used a majority vote; **`VIBECODING_CONSULTATION_ONLY`**: `gate_contract = NOT_APPLICABLE` — a missing Gate is **not** a violation. If a Consultation Work Order contains a Gate object or requires Gate, the correct signal is `CONSULTATION_GATE_TOPOLOGY_FABRICATED` or `WORK_ORDER_MODE_APPLICABILITY_CONTRADICTION`. **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_LOOP_PATH_UNAPPROVED` — **`FULL_9_ROLE_VIBECODING`** / **`LIGHTWEIGHT_OPERATION`**: corrective loop path not pre-approved in `corrective_loop_contract`, or `LOOP_STAGNATION_DETECTED` bypassed via loop budget (§4.17.9, §4.12). **`VIBECODING_CONSULTATION_ONLY`**: **not** applicable — if a Consultation Work Order contains a corrective loop object, `CONSULTATION_CORRECTIVE_LOOP_FABRICATED` is the correct signal. **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CONSULTATION_GATE_TOPOLOGY_FABRICATED` — a Consultation Work Order creates, references, or requires a Gate object (`gate_contract` ≠ `NOT_APPLICABLE`), or invokes any `TEST_GATE` / `REVIEW_GATE` execution stage (§4.17.8, §4.17.10). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_BUDGET_UNBOUNDED` — `budget_contract` mode-discriminated check, field-by-field alignment with §4.17.9: **All modes (common pre-check)**: any automatic model substitution = `true`, any automatic quota retry = `true`, or any automatic quota-reset wait = `true` triggers immediate STOP. No Work Order in any selected_submode may enable these automated behaviors (§4.17.9). This check is enforced **before** per-mode budget field checks; a Work Order with all required budget fields but enabled automated behaviors still fails this signal; **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`**: missing per-role / total / loop / push / PR API / proxy bypass budgets; **`VIBECODING_CONSULTATION_ONLY`**: missing orchestrator model / invocation budget, missing read-source / tool budget, missing evidence / output capability budget, **or** missing operator-approved time / invocation-count limits. Git / corrective loop / push / PR API / proxy bypass budgets being `NOT_APPLICABLE` or `disabled / 0` is **not** a violation — `CONSULTATION_GIT_BUDGET_REQUIRED` is the correct signal for requiring execution-type budgets in Consultation. **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_REPOSITORY_SCOPE_MISMATCH` — `repository_scope` mode-discriminated check: **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`**: missing `approved_base_sha` / `work_branch` / path policy, or staged paths exceed Work Order-allowed paths, or current PR construction untracked paths promoted to a universal constant (§4.17.4, §4.16.10); **`VIBECODING_CONSULTATION_ONLY`**: checks only `NOT_APPLICABLE` legitimacy or operator-approved read-only source refs / `permitted_read_range`. Missing `work_branch`, `change_types`, or `deletions` is **not** a violation. **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_ENDPOINT_OVERREACH` — mode-discriminated endpoint boundary: **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`**: automatic endpoint extended beyond `DRAFT_PR_DELIVERY_VERIFIED → WORK_ORDER_AUTOMATIC_ENDPOINT_REACHED → STOP`, or includes Post-Draft operations (§4.17.10); **`VIBECODING_CONSULTATION_ONLY`**: endpoint extended beyond `CONSULTATION_OPERATION_ENDPOINT_REACHED → STOP`, or enters Post-Draft / execution-type Git delivery chain. **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_POST_DRAFT_AUTHORITY_INCLUDED` — Work Order carries `draft_to_ready=true`, `merge=true`, or `branch_deletion=true`, or any Post-Draft authorisation (§4.17.10). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_ARTIFACT_SCHEMA_INCOMPLETE` — mode-discriminated artifact schema check, field-by-field alignment with §4.17.7: **`FULL_9_ROLE_VIBECODING`** and **`LIGHTWEIGHT_OPERATION`**: missing any of `artifact_id` / `type` / `version` / `digest` / `producer_role` / `role_invocation` / `input_refs` / `candidate_digest` / `created_at` / `status`; `status` outside `VALID / INVALIDATED / SUPERSEDED / REVALIDATION_REQUIRED`; frozen artifact modified in place; new content without new `version` and `digest` (§4.17.7); **`VIBECODING_CONSULTATION_ONLY`**: missing any of `artifact_id` / `artifact_type` / `version` / `digest` / `producer_role` (must equal `orchestrator`) / `orchestrator_invocation_id/version/digest` / `input_read_source_refs` / `evidence_ref_ids` / raw evidence references / `created_at` / `status`; `status` outside the permitted set; frozen deliverable / report modified in place; new content without new `version` and `digest`. `candidate_digest`, Gate, non-orchestrator assignment, and Git fields are **not** required and **must not** be required. **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_APPROVAL_BINDING_STALE` — operator approval binding does not exactly match `work_order_id + document_version + work_order_digest` (§4.17.1, §4.17.3). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_EXECUTION_RECORD_OVERWROTE_AUTHORIZATION` — `WORK_ORDER_EXECUTION_RECORD` modified the Work Order, or was used to expand authorisation (§4.17.1). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `RUNTIME_STATE_USED_AS_AUTHORIZATION_SOURCE` — `runtime_state_reference` used as an authorisation source, or used to modify the Work Order (§4.17.12). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_MODE_APPLICABILITY_CONTRADICTION` — a schema field's `applicability` contradicts `selected_submode` (§4.17.2). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CONSULTATION_WORK_ORDER_REQUIRES_ASSIGNMENT_BASELINE` — a consultation Work Order is required to have a non-orchestrator assignment baseline, role Gate, or Git delivery field (§4.17.3, §4.17.4, §4.17.5). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CONSULTATION_WORK_ORDER_GIT_ENDPOINT_OVERREACH` — a consultation Work Order is interpreted as having a Draft PR endpoint or Post-Draft chain (§4.17.10, §4.17.13). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CONSULTATION_ACCEPTANCE_MAPPED_TO_DRAFT_PR` — a consultation acceptance criterion is mapped to Draft PR evidence (§4.17.12). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `VIBECODING_WORK_ORDER_INCLUDES_DEDICATED_GOVERNANCE_GATE` — a VIBECODING_MODE Work Order has `HERMES_OPENCODE_VERSION_GOVERNANCE_GATE` or `CENTRAL_MODEL_POOL_GOVERNANCE_GATE` set to `true` / `IN_SCOPE` (§4.17.3). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `FULL_WORK_ORDER_PLAN_CHECKPOINT_OPTIONALIZED` — a FULL-mode Work Order has `IMPLEMENTATION_PLAN_CHECKPOINT_REQUIRED` set to `false` or otherwise optionalised (§4.17.3, §4.17.6). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_STATE_ALIAS_AMBIGUOUS` — `OPERATOR_APPROVED_WORK_ORDER` and `WORK_ORDER_ACTIVE` are treated as the same state or alias (§4.17.13). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `STALE_WORK_ORDER_SCHEMA_STATUS` — the Work Order schema or its canonical governance status is marked as "not yet finalised" or "still to be finalised" when §4.17 has already locked it (§8.1). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_ACTIVE_TRANSITION_OMITTED` — execution material skips `WORK_ORDER_ACTIVE` and transitions directly from `OPERATOR_APPROVED_WORK_ORDER` to `GLOBAL_READINESS` (§4.17.1). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CONSULTATION_ROLE_ACTIVATION_FABRICATED` — a Consultation Work Order creates a non-orchestrator `ROLE_ACTIVATION_READINESS` or extra role activation step (§4.17.7). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CONSULTATION_READINESS_EXECUTION_FIELD_REQUIRED` — a Consultation Global Readiness check requires execution-type fields (repository / assignment / Git delivery) instead of validating them as `NOT_APPLICABLE` (§4.17.7). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CONSULTATION_GIT_BUDGET_REQUIRED` — a Consultation Work Order is required to have execution-type budgets (push / PR API / proxy bypass) present and non-zero (§4.17.9). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CONSULTATION_RUNTIME_STATE_FABRICATED` — a Consultation Work Order's runtime state creates or references fictional Gate, CANDIDATE_TRIPLE, or Git state (§4.17.12). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CONSULTATION_CORRECTIVE_LOOP_FABRICATED` — a Consultation Work Order creates a corrective loop path, loop_id, return_role, artifact invalidation, or `LOOP_STAGNATION_DETECTED` state (§4.17.9). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CONSULTATION_LOOP_STOP_STATE_FABRICATED` — a Consultation execution record records `LOOP_STAGNATION_DETECTED` or any loop-related STOP event (§4.17.11). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `CONSULTATION_NONORCHESTRATOR_ASSIGNMENT_FAILURE_FABRICATED` — a Consultation execution record records a non-orchestrator assignment baseline failure or non-orchestrator Activation failure (§4.17.11). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_HARD_STOP_SOURCE_STATE_INCOMPLETE` — hard STOP entry is restricted to only `WORK_ORDER_ACTIVE` instead of covering all post-approval active execution states (§4.17.13). **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_EVIDENCE_INFRASTRUCTURE_FAILURE_OMITTED` — All-modes hard STOP set (§4.17.11) omits `evidence forgery`, `evidence pipeline / channel unreachable or untrustworthy`, or `evidence infrastructure unavailable / failure`, or allows a mode to form `ROLE_COMPLETION` / deliverable / report `VERIFIED` / Gate `PASS` / endpoint without trustworthy evidence, or allows loop budget / new analysis to substitute missing evidence. **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `WORK_ORDER_COMMON_STOP_SET_CONTRADICTION` — §4.17.9 budget / runtime subset and §4.17.11 canonical STOP set are mutually exclusive, allow deletions, or omit an All-modes hard STOP class. **Immediate STOP.** [signal_kind=DRIFT_STOP]
- `DRIFT_SIGNAL_CANONICAL_ID_AMBIGUOUS` — any catalog canonical-ID integrity violation: the same backtick canonical `drift_signal_id` is defined twice in §10.1; an entry is missing its canonical backtick ID; a single `legacy_display_index` maps to two or more distinct backtick canonical names; runtime / validator / receipt / audit / cross-reference uses a `legacy_display_index` where a canonical backtick ID is required; an entry's `signal_kind` is missing or contradicts the entry's effect; or `STALE_EXPECTED_HEAD_GUARD_TRIGGERED_CORRECTLY` / historical `AUDIT_DEVIATION` / `AUDIT_UNKNOWN` records are reinterpreted as new drift or re-triggered; or any entry uses metadata grammar outside the two allowed forms (`[signal_kind=KIND]` or `[legacy_display_index=(x), signal_kind=KIND]`), has duplicate metadata fields, uses field order / separator that cannot be deterministically parsed, or has any non-whitespace content after the metadata suffix (including continuation lines, sub-bullets, and subsequent paragraphs belonging to the same logical entry). **Immediate STOP.** [legacy_display_index=(x), signal_kind=DRIFT_STOP]
- `OBJECT_ID_COLLISION` — two or more objects share the same `object_id` within the same governance scope; [signal_kind=DRIFT_STOP]
- `OBJECT_DIGEST_MISMATCH` — the declared `canonical_digest` of an object does not match its recomputed digest; [signal_kind=DRIFT_STOP]
- `OBJECT_VERSION_REGRESSION` — a new object version has a lower or equal version number than the object it claims to supersede; [signal_kind=DRIFT_STOP]
- `OBJECT_MUTATED_AFTER_FREEZE` — a frozen object (Packet, frozen Artifact, or Receipt) has been modified in place; [signal_kind=DRIFT_STOP]
- `OBJECT_REFERENCE_INCOMPLETE` — a reference to another object uses fewer than the required `id + version + digest` triple; [signal_kind=DRIFT_STOP]
- `OBJECT_REFERENCE_DIGEST_MISMATCH` — a reference to another object uses a digest that does not match the referenced object's declared digest; [signal_kind=DRIFT_STOP]
- `OBJECT_LINEAGE_CYCLE_DETECTED` — the Artifact / Evidence / Packet / Receipt DAG contains a cycle; [signal_kind=DRIFT_STOP]
- `ARTIFACT_PROVENANCE_INCOMPLETE` — an Artifact is missing required provenance fields (producer role, assignment/Activation/attempt/invocation refs, input refs); [signal_kind=DRIFT_STOP]
- `ARTIFACT_CLAIM_WITHOUT_EVIDENCE` — an Artifact contains a substantive claim (`claim_id`) that is not backed by at least one Evidence record; [signal_kind=DRIFT_STOP]
- `ARTIFACT_VALIDATION_RECEIPT_MISSING` — an Artifact requiring validation has no corresponding `ARTIFACT_VALIDATION_RECEIPT` or equivalent role/Explorer/Plan validation receipt; [signal_kind=DRIFT_STOP]
- `EVIDENCE_SOURCE_UNTRUSTWORTHY` — Evidence is sourced from a trust domain or source identity that is not operator-approved for the current mode; [signal_kind=DRIFT_STOP]
- `EVIDENCE_RAW_PAYLOAD_MISSING` — Evidence record lacks a `raw_payload_ref` / `raw_digest` or the referenced raw payload is inaccessible; [signal_kind=DRIFT_STOP]
- `EVIDENCE_NORMALIZATION_MISMATCH` — the `normalized_observation` in an Evidence record contradicts the raw payload or omits a material fact present in the raw payload; [signal_kind=DRIFT_STOP]
- `EVIDENCE_SENSITIVITY_VIOLATION` — Evidence contains credential values, secret-derived fragments, private host/IP/user/path, internal prompts, or raw private logs in a context that requires public-safe projection; [signal_kind=DRIFT_STOP]
- `PACKET_MEMBERSHIP_DRIFT` — the actual membership of a frozen Packet differs from its declared `deterministic ordered membership`; [signal_kind=DRIFT_STOP]
- `PACKET_FREEZE_RECEIPT_MISSING` — a Packet that is referenced as frozen has no corresponding `PACKET_FREEZE_RECEIPT`; [signal_kind=DRIFT_STOP]
- `PACKET_CONSUMER_BINDING_MISMATCH` — a consumer role or stage binds to a Packet version / digest that does not match the Packet's declared version / digest; [signal_kind=DRIFT_STOP]
- `PACKET_ASSEMBLER_MUTATED_MEMBER` — the Packet assembler rewrote, supplemented, deleted, or changed the meaning of a member object instead of selecting / referencing / ordering / freezing / digesting it; [signal_kind=DRIFT_STOP]
- `PACKET_VERSION_STALE` — a consumer references a Packet version that has been superseded or invalidated; [signal_kind=DRIFT_STOP]
- `RECEIPT_ISSUER_UNAUTHORIZED` — the issuer of a Receipt does not have authority under the Authority Matrix (§10.3.x) to issue that Receipt type; [signal_kind=DRIFT_STOP]
- `RECEIPT_SUBJECT_BINDING_MISMATCH` — the `subject id/version/digest` in a Receipt does not match the actual subject object's identity; [signal_kind=DRIFT_STOP]
- `RECEIPT_PREREQUISITE_MISSING` — a Receipt declares prerequisite receipts that are missing, stale, or do not match the expected decision result; [signal_kind=DRIFT_STOP]
- `RECEIPT_EVIDENCE_INSUFFICIENT` — a Receipt's `evidence_refs` do not collectively support the declared `decision result`; [signal_kind=DRIFT_STOP]
- `RECEIPT_STALE_AFTER_DRIFT` — a drift event occurred that should make a Receipt's effective status `STALE`, but the required `INVALIDATION_RECEIPT` is missing or the system still computes the Receipt as `CURRENT`; [signal_kind=DRIFT_STOP]
- `OPERATOR_RECEIPT_FORGED_OR_SUBSTITUTED` — a Receipt that only the operator may issue (§10.3.x Authority Matrix) was issued by a non-operator entity; [signal_kind=DRIFT_STOP]
- `GATE_RECEIPT_CANDIDATE_MISMATCH` — a Gate receipt references a CANDIDATE_TRIPLE Packet or Artifact that does not match the CANDIDATE_TRIPLE frozen for that Gate; [signal_kind=DRIFT_STOP]
- `PUBLIC_PROJECTION_SOURCE_MISMATCH` — a `PUBLIC_EVIDENCE_PROJECTION` references source Evidence records that do not match its declared `source_refs`; [signal_kind=DRIFT_STOP]
- `PUBLIC_PROJECTION_SAFETY_CHECK_MISSING` — a `PUBLIC_EVIDENCE_PROJECTION` was used without a corresponding public-safe check receipt; [signal_kind=DRIFT_STOP]
- `VERSION_GOVERNANCE_PACKET_BINDING_MISMATCH` — a §3.8 version governance stage references a Packet or Receipt that does not match the current version governance operation's scope; [signal_kind=DRIFT_STOP]
- `VERSION_EXECUTION_AUTHORIZATION_STALE` — a §3.8 V5 second confirmation authorisation has become stale because the target version, component, node/profile, action, backup/rollback point, or qualification plan changed; [signal_kind=DRIFT_STOP]
- `VERSION_GATE_BYPASSED_BY_WORK_ORDER` — a Work Order attempts to perform a Hermes / OpenCode version change that should have been routed through §3.8 HERMES_OPENCODE_VERSION_GOVERNANCE_GATE; [signal_kind=DRIFT_STOP]

- `CONTRACT_SECTION_IDENTIFIER_COLLISION` — two or more sections share the same heading path within the contract; [signal_kind=DRIFT_STOP]
- `OBJECT_IDENTITY_ALIAS_MISMATCH` — a type-specific identity alias (`artifact_id`, `packet_id`, `receipt_id`, `evidence_id`, `evidence_version`, `projection_id`, `projection_digest`, etc.) does not match the corresponding common envelope field; [signal_kind=DRIFT_STOP]
- `CLAIM_REFERENCE_BINDING_INCOMPLETE` — a cross-object Claim reference uses only `claim_id` without the required `containing_artifact_ref + claim_id + claim_digest` triple; [signal_kind=DRIFT_STOP]
- `PUBLIC_PROJECTION_OBJECT_CLASS_UNDEFINED` — a `PUBLIC_EVIDENCE_PROJECTION` is used without being classified as a derived Artifact (`PUBLIC_EVIDENCE_PROJECTION_ARTIFACT`) or other defined object type; [signal_kind=DRIFT_STOP]
- `RECEIPT_LIFECYCLE_MUTATED_IN_PLACE` — a Receipt's `lifecycle_state` was changed in place instead of recording the transition via an independent append-only Receipt; [signal_kind=DRIFT_STOP]
- `RECEIPT_BUSINESS_STATE_LIFECYCLE_CONFLATION` — the business workflow state (`state_created`) is conflated with the Receipt's own lifecycle state; [signal_kind=DRIFT_STOP]
- `CONSULTATION_REQUIRED_EVIDENCE_OR_AUTHORIZATION_OBJECT_FORBIDDEN` — a required common governance object (operator approval Receipt, Evidence, model invocation Evidence, public projection, invalidation/supersession Receipt) is missing in Consultation mode, or a forbidden object (non-orchestrator assignment/Activation, CANDIDATE_TRIPLE, test/review Gate, Integration/Git/Post-Draft) is present; [signal_kind=DRIFT_STOP]
- `VERSION_GOVERNANCE_STAGE_OBJECT_CONFLATION` — a V4/V5/V6 version governance object is used for a purpose that belongs to a different stage (e.g., V4 checkpoint substituting for V5 authorisation, V6 execution evidence written back into V5 Packet); [signal_kind=DRIFT_STOP]
- `EVIDENCE_OBJECT_DIGEST_MISSING` — an Evidence record lacks `evidence_version` or `evidence_digest` (canonical_digest of the Evidence object itself, distinct from `raw_digest`); [signal_kind=DRIFT_STOP]

- `OBJECT_CANONICAL_DIGEST_SELF_REFERENCE` — a canonical payload includes its own digest or its containing parent object's digest, creating a fixed-point self-reference cycle; [signal_kind=DRIFT_STOP]
- `OBJECT_SELF_CERTIFYING_RECEIPT_CYCLE` — a subject object's canonical body embeds a reference (id/version/digest) to a Receipt that certifies, validates, or freezes that same subject object, creating a self-certification cycle; [signal_kind=DRIFT_STOP]
- `RECEIPT_TYPE_REGISTRY_INCOMPLETE` — a Receipt type that is referenced or used in governance logic is missing from the minimum Receipt type registry, or its issuer/authority/prerequisites are ambiguous; [signal_kind=DRIFT_STOP]
- `VERSION_QUALIFICATION_SECRET_EVIDENCE_VIOLATION` — V7 qualification Evidence contains or derives a secret value, hash, length, prefix/suffix, header, token/cookie, or secret-derived fingerprint instead of limiting to credential identity, approved source class, availability/binding verification, and `secret_value_observed=false`; [signal_kind=DRIFT_STOP]
- `LIFECYCLE_STATE_MUTATED_IN_PLACE` — an object's lifecycle state was changed in place on the original object body instead of recording the transition via a new object version or an append-only Receipt; [signal_kind=DRIFT_STOP]

- `RECEIPT_REGISTRY_DUPLICATE_TYPE` — a receipt type appears more than once in the canonical receipt type registry; [signal_kind=DRIFT_STOP]
- `RECEIPT_REGISTRY_FIELD_INCOMPLETE` — a receipt type in the canonical registry is missing one or more required specification fields (issuer class, authority basis, subject class, prerequisite types, required evidence classes, allowed decision results, or `state_created`); [signal_kind=DRIFT_STOP]
- `RECEIPT_TYPE_AND_STATE_CREATED_CONFLATED` — a `state_created` business workflow state (e.g. `OPERATOR_APPROVED_INTAKE_SCOPE`) is used or treated as a receipt type identifier, or vice versa; [signal_kind=DRIFT_STOP]
- `RECEIPT_ISSUER_ROLE_BOUNDARY_CONTRADICTION` — a role issues a receipt type that is outside its authority (e.g. a role issuing `STOP_RECEIPT` or a deleted `ROLE_COMPLETION_RECEIPT`), or an issuer field in the registry contradicts the authority matrix; [signal_kind=DRIFT_STOP]
- `PACKET_EFFECTIVE_STATE_WITHOUT_TRANSITION_RECEIPT` — a Packet effective state (e.g. `CONSUMED`) has no corresponding canonical transition receipt type; [signal_kind=DRIFT_STOP]
- `ARTIFACT_PRODUCER_BINDING_MODE_CONTRADICTION` — an Artifact's `producer_binding` mode does not match its artifact type, execution mode, or the presence/absence of mandatory refs; [signal_kind=DRIFT_STOP]

- `GRAY4_USED_AS_PRECONDITION_TO_COMPLETE_CONTRACT_V2` — Gray4 operational validation is used or treated as a precondition for completing the Contract V2 draft, inverting the correct sequence (V2 draft + operator acceptance → cluster gap assessment → remediation → pre-Gray4 readiness → Gray4); [signal_kind=DRIFT_STOP]
- `CLUSTER_REMEDIATION_STARTED_BEFORE_V2_ACCEPTANCE` — cluster remediation (runtime, SOUL/MEMORY, node registry, CMP, assignment/readiness, Artifact/Evidence/Packet/Receipt, Git/Post-Draft, or any implementation-level change) is started before the operator has accepted Contract V2; [signal_kind=DRIFT_STOP]
- `RECEIPT_TYPE_DECISION_STATE_MISMATCH` — a receipt type's allowed decision results or `state_created` values are inconsistent with the receipt type name (e.g. a `*_PASS_RECEIPT` allowing FAIL as a valid decision, or a `*_FAIL_RECEIPT` creating a PASS state); [signal_kind=DRIFT_STOP]
- `RECEIPT_REGISTRY_PREREQUISITE_EXPRESSION_UNPARSEABLE` — a prerequisite expression in the canonical receipt type registry uses a non-canonical, ambiguous, or unparseable phrase (e.g. "as applicable", "upstream evidence", "packet freeze") without a mode/stage discriminator, preventing deterministic prerequisite resolution; [signal_kind=DRIFT_STOP]

- `RECEIPT_REGISTRY_COUNT_SCOPE_MISMATCH` — a registry verification reports the full-text backtick token count as if it were the canonical receipt type count, without separating canonical registry rows from deleted/noncanonical Receipt tokens and Signal IDs ending in `_RECEIPT`; [signal_kind=DRIFT_STOP]
- `GATE_FAIL_RECEIPT_STAGE_PREREQUISITE_MISMATCH` — a `*_FAIL_RECEIPT` references a stage prerequisite that is inconsistent with the FAIL semantics (e.g. Git Integration FAIL using Review FAIL as prerequisite, or Test/Review FAIL skipping the current stage's input Packet freeze prerequisite); [signal_kind=DRIFT_STOP]
- `RECEIPT_AUTHORITY_MATRIX_REGISTRY_MISMATCH` — the Authority Matrix issuer list diverges from the canonical registry's `Issuer Class` column (a receipt type appears in the registry with an issuer class not present in the Authority Matrix, or vice versa); [signal_kind=DRIFT_STOP]
- `POST_DRAFT_EXECUTION_RECEIPT_OPERATOR_AUTHORIZATION_MISSING` — a Post-Draft execution Receipt (`READY_TRANSITION_RECEIPT`, `MERGE_DELIVERY_RECEIPT`, `BRANCH_DELETION_RECEIPT`) is issued without binding the matching operator authorization Receipt for the current stage (`OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT`, `OPERATOR_MERGE_AUTHORIZATION_RECEIPT`, `OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT`); [signal_kind=DRIFT_STOP]
- `CONSULTATION_FORBIDDEN_OPERATOR_RECEIPT_INSTANTIATED` — a Consultation-only mode run instantiates a non-orchestrator assignment receipt (`OPERATOR_ROLE_NODE_MODEL_ASSIGNMENT_APPROVAL_RECEIPT`), an Activation-stage receipt (`ROLE_ACTIVATION_READINESS_RECEIPT`), or a Post-Draft authorization receipt (`OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT`, `OPERATOR_MERGE_AUTHORIZATION_RECEIPT`, `OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT`); [signal_kind=DRIFT_STOP]

### §10.2 Drift Handling

`STOP → IDENTIFY → RE-ANCHOR → PROPOSE → WAIT`.


### §10.3 Artifact / Evidence / Packet / Receipt Canonical Governance Schema

**Status: `PROVISIONAL_ARTIFACT_EVIDENCE_SCHEMA_PENDING_POST_REMEDIATION_GRAY4_VALIDATION`.** The operator has provisionally accepted this schema design as the Contract V2 DRAFT canonical design baseline, pending exposure in the fourth gray run. This is **not** V2 final acceptance, `OPERATIONAL_PHASE` cutover, or runtime E2E PASS. Runtime must not interpret provisional acceptance as final acceptance, verification waiver, or authorisation expansion. Nothing in this section weakens existing STOP, role invocation, Gate, Git, or Post-Draft boundaries.

#### §10.3.1 Object Separation

Four distinct object types must not be substituted for one another:

- **Artifact**: a work product produced by a role or the orchestrator (plan, report, CANDIDATE_TRIPLE, deliverable).
- **Evidence**: a raw observation that supports facts, actions, invocations, and conclusions (command output, file snapshot, API response, test result, model invocation record).
- **Packet**: a frozen ordered collection of member objects (Artifacts, Evidence, Receipts, or sub-Packets) assembled for a downstream consumer role or stage.
- **Receipt**: an immutable record that an authorisation, verification, Gate, or state transition has occurred.

An Artifact claim is **not** Evidence. An Evidence collection that has not been frozen is **not** a Packet. The existence of a Packet does **not** constitute a Gate PASS. A Receipt must **not** expand Work Order or operator authorisation.

#### §10.3.2 Common Object Envelope

All four governance object types (Artifact, Evidence, Packet, Receipt) share the following common fields:

- `object_id` — unique identifier within governance scope
- `object_type` — type classifier from the applicable type registry
- `schema_version` — version of this schema definition
- `object_version` — version of this specific object (monotonic)
- `canonical_digest` — SHA-256 hex digest of the canonical serialization
- `created_at` — RFC 3339 UTC timestamp
- `producer_or_collector_or_issuer_identity` — role, node, or entity that produced, collected, or issued the object
- `work_order_or_governance_operation_ref` — `id + version + digest` of the governing Work Order or governance operation
- `lifecycle_state_at_creation` — the lifecycle state at object creation, recorded immutably in the canonical digest. The **effective** lifecycle state is computed from the object version chain and the append-only Receipt chain (Invalidation / Supersession / Revocation Receipts); it must not be written back into the object body. Type-specific lifecycle registries: Artifact (§10.3.5), Evidence (§10.3.7), Packet (§10.3.8), Receipt (§10.3.9)
- `supersedes_ref` — `id + version + digest` of the object this one supersedes (or null)
- `execution_record_ref` — `id + version + digest` of the governing execution record (if any). This field is **conditionally required**: post-Activation, when an execution record exists, it must be populated. For pre-execution governance objects (operator approval Receipts, pre-Activation governance objects), the value must be explicitly `NOT_APPLICABLE` with a reason. A fabricated or stale reference is forbidden.

Evidence additionally records:

- `collector_identity` — role or node that collected the evidence
- `collection_method` — how the evidence was collected (command, API call, file read, etc.)
- `source_identity` — the external source (host, URL, file path, process)
- `observed_at` — RFC 3339 UTC timestamp of observation
- `raw_integrity_digest` — SHA-256 hex digest of the raw payload at collection time



Type-specific field aliases (e.g., `artifact_id` / `artifact_version` / `artifact_digest` for Artifact, `packet_id` / `packet_version` / `packet_digest` for Packet, `receipt_id` / `receipt_version` / `receipt_digest` for Receipt, `evidence_id` / `evidence_version` / `evidence_digest` for Evidence) are **mandatory aliases** of the common envelope fields. The following equivalences are enforced:

- `artifact_id == object_id`, `artifact_version == object_version`, `artifact_digest == canonical_digest`
- `packet_id == object_id`, `packet_version == object_version`, `packet_digest == canonical_digest`
- `receipt_id == object_id`, `receipt_version == object_version`, `receipt_digest == canonical_digest`
- `evidence_id == object_id`, `evidence_version == object_version`, `evidence_digest == canonical_digest`

Any alias inconsistency triggers `OBJECT_IDENTITY_ALIAS_MISMATCH → STOP`.

`raw_digest` (in Evidence) is the digest of the raw payload only and must not be conflated with `evidence_digest` / `canonical_digest` of the Evidence object itself.

#### §10.3.3 Object References (Triple Binding)

Every reference from one governance object to another must use the **`id + version + digest`** triple. References using only file name, role name, `latest`, branch name, PR number, title, URL, or an object without a digest are forbidden. PR numbers may appear only as a locator field alongside the required triple.

#### §10.3.4 Canonical Serialization and Immutability

Before computing the `canonical_digest`, the logical object must be deterministically canonicalized:

- UTF-8 encoding, LF line endings, RFC 3339 UTC timestamps
- Canonical JSON or equivalent deterministic serialization
- Fixed key ordering
- Null / default values must not be implicitly omitted
- Floating-point representations that are not deterministically representable are forbidden
- No fields may be appended after the digest is computed

A Markdown or rendered representation may have an independent `rendered_digest`, but authorisation and cross-reference must bind to the `canonical_digest`.

Once an object has been verified, referenced, or frozen, it must not be modified in place. Changes must produce a new `object_version`, new `canonical_digest`, and a `supersedes_ref` or invalidation relationship. The old object must be retained for audit; deletion or hidden history is forbidden.

#### §10.3.5 Artifact Schema

An Artifact must record at least:

- `artifact_id` / `type` / `version` / `digest`
- `producer_binding` — discriminated mode, one of:
  - `ROLE_EXECUTION`: role `assignment_ref` / `activation_ref` / `attempt_ref` / `invocation_ref` all required (`id + version + digest` triples)
  - `ORCHESTRATOR_SESSION`: operator-preselected session `session_ref`, orchestrator `invocation_ref` / `attempt_ref` / `operation_execution_ref` required; `assignment_ref` / `activation_ref` explicitly `NOT_APPLICABLE + reason`
  - `DEDICATED_GOVERNANCE_GATE`: governance operation / stage `governance_operation_ref`, applicable operator Receipt, orchestrator `invocation_ref` / Evidence required; Work Order `work_order_ref` and `assignment_ref` / `activation_ref` explicitly `NOT_APPLICABLE + reason`
  - `DERIVED_PUBLIC_PROJECTION`: source Artifact / Evidence `source_refs` required; projection producer `invocation_ref` / `safety_check_required_flag` required; `assignment_ref` / `activation_ref` / `attempt_ref` explicitly `NOT_APPLICABLE + reason`
- `producer_role` — the role, orchestrator, or gate that produced this artifact
- `producer_binding_refs` — refs according to the `producer_binding` mode above
- `input_artifact_refs` / `input_evidence_refs` / `input_packet_refs` / `input_receipt_refs` — `id + version + digest` triples
- `structured_content` — the substantive content of the artifact
- `rendered_ref` — optional reference to a rendered / Markdown representation
- `requirement_traceability` / `criterion_traceability` / `finding_traceability` / `plan_traceability`
- `claims` — ordered list of embedded canonical Claim subobjects (§10.3.6); each Claim is fully covered by the Artifact's `canonical_digest`; internal lookup uses `claim_id`
- `validation_requirement` — whether this artifact requires a validation receipt
- `lifecycle_state_at_creation` — `VALID` (immutable in canonical digest). Effective states: `VALID`, `INVALIDATED`, `SUPERSEDED`, `REVALIDATION_REQUIRED` — computed from the append-only Receipt chain and Claim invalidation, not from in-place field mutation

Minimum artifact types:

`INTAKE_REPORT`, `EXPLORER_FACT_MAP`, `EXPLORER_ARTIFACT`, `IMPLEMENTATION_PLAN`, `IMPLEMENTATION_REPORT`, `IMPLEMENTATION_CANDIDATE`, `TESTER_A_REPORT`, `TESTER_B_REPORT`, `REVIEWER_A_REPORT`, `REVIEWER_B_REPORT`, `ROLE_COMPLETION_REPORT`, `CONSULTATION_DELIVERABLE`, `CONSULTATION_REPORT`, `GIT_INTEGRATION_REPORT`, `READY_TRANSITION_COMPLETION_REPORT`, `MERGE_COMPLETION_REPORT`, `BRANCH_DELETION_COMPLETION_REPORT`, `STOP_REPORT`.

#### §10.3.6 Claim

Every substantive conclusion in an Artifact must use a stable `claim_id`. Claim is a **canonical embedded subobject** within an Artifact; its full content is covered by the containing Artifact's `canonical_digest`. Each Claim must record at least:

- `claim_id` — unique within the containing Artifact
- `claim_type`
- `statement` — the substantive assertion
- `producer` — role or entity that made the claim
- `containing_artifact_id` / `containing_artifact_version` — local locator fields; the containing Artifact's `canonical_digest` must **not** appear in the Claim payload
- `evidence_refs` — one or more `id + version + digest` Evidence references
- `status` — one of `ASSERTED`, `VERIFIED`, `CONTRADICTED`
- `limitations` — any known limitations, assumptions, or scope restrictions

`claim_digest` is computed from the Claim's own canonical payload, excluding the `claim_digest` field itself and excluding any containing Artifact digest. The containing Artifact's `canonical_digest` covers the Claim as an embedded subobject, but the Claim payload must not contain that digest — a parent digest in its own subobject's payload creates a fixed-point self-reference cycle.

**Cross-object Claim references**: when a Claim is referenced from outside its containing Artifact (from another Artifact, Packet, or Receipt), the reference must use the triple `containing_artifact_ref (id + version + digest) + claim_id + claim_digest`. A bare `claim_id` without the containing Artifact triple is forbidden. The verifier must independently verify: (a) the containing Artifact's `canonical_digest`, (b) the Claim's `claim_digest`, and (c) that the Claim belongs to the stated Artifact. If a Claim is later promoted to an independent object, it must carry the full common envelope (§10.3.2); a `claim_id` alone must not serve as a cross-object reference.

Repo / file state, test results, model invocations, route / node state, CANDIDATE_TRIPLE tree, push / PR / Gate / review / post-merge conclusions must each be bound to at least one Evidence record. A bare "verified / tests pass / remote consistent / no issues" assertion must not form a PASS without supporting Evidence.

#### §10.3.7 Evidence Schema

An Evidence record must record at least:

- `evidence_id` / `type`
- `source_type` / `source_identity` / `source_target` / `trust_domain`
- `collector_role` / `collector_node`
- `collected_at` — RFC 3339 UTC timestamp
- `method` / `command_class` / `exit_code`
- `raw_payload_ref` / `media_type` / `raw_digest`
- `normalized_observation` — the deterministically normalized fact extracted from the raw payload
- `sensitivity_classification`
- `public_projection_allowance` — whether a public-safe projection exists
- `provenance_refs` / `derived_from_refs` — `id + version + digest` triples

Minimum evidence types:

`COMMAND_RESULT`, `FILE_SNAPSHOT`, `GIT_OBJECT`, `REMOTE_API_RESPONSE`, `TEST_RESULT`, `MODEL_INVOCATION_RECORD`, `ROLE_OUTPUT`, `NODE_ROUTE_PROBE`, `READINESS_CHECK`, `PR_METADATA_SNAPSHOT`, `DIFF_MANIFEST`, `TREE_MANIFEST`, `OPERATOR_DECISION_RECORD`, `TIME_SOURCE_RECORD`.

**Raw payload and normalized observation must be separated.** Public metadata may reference only a `PUBLIC_EVIDENCE_PROJECTION` that has passed a public-safe check.

**Public-projectable Evidence — forbidden payloads (complete list):** environment-variable dumps; token, cookie, authorisation, or header values; secret values; secret hash, length, prefix, or suffix; secret-derived fingerprints; unauthorised private host, IP, user, or path; internal prompts; raw private logs.

**Credential Evidence — permitted fields only:** `credential_identity`; `approved_source_class`; `available = true / false`; binding-verification status; `secret_value_observed = false`. No secret value, hash, length, prefix, suffix, header, token, cookie, or secret-derived fingerprint may appear.

**Evidence lifecycle:** `lifecycle_state_at_creation = VALID` (immutable in canonical digest). Effective states: `INVALIDATED`, `SUPERSEDED` — computed from the append-only Receipt chain, not from in-place field mutation.

##### Formal Model Invocation Evidence

Every formal role invocation must produce an independent Evidence record containing:

- `invocation_id` / `role` / `attempt` / `assignment`
- `node` / `canonical_provider` / `runtime_provider`
- `model` / `alias`
- `prompt_digest` — SHA-256 of the prompt sent
- `context_packet_ref` — `id + version + digest` of the input context packet
- `prompt_class`
- `timestamps` — start / end / duration
- `status` — success, failure, partial, quota_exhausted
- `provider_request_ref` — if available
- `quota_status`
- `raw_output_ref` / `output_digest`
- `parse_status`
- `substantive_flag` — whether the invocation produced substantive content

Shell commands, pytest runs, scripts, static analysis, orchestrator summaries, or copied output from another role must not substitute for formal model invocation evidence.

#### §10.3.8 Packet and Freeze

A Packet must record at least:

- `packet_id` / `type` / `version` / `digest`
- `assembler_identity` / `assembler_function`
- `deterministic_ordered_membership` — ordered list of `id + version + digest` triples (members may be Artifact, Evidence, Receipt, or sub-Packet; unapproved object types must not enter membership)
- `freeze_required` — boolean flag indicating that freeze is required before the Packet is considered ready for consumption (the `PACKET_FREEZE_RECEIPT` is an external Receipt that references this Packet's `id + version + digest` triple; it must not be embedded in the Packet canonical body)
- `intended_consumer_role` / `intended_consumer_stage`
- `scope_ref` / `requirement_ref` / `candidate_ref`
- `excluded_objects` — list of objects considered but excluded, with reason
- `sensitivity_classification` / `public_projection_ref`

After freeze, membership and order are immutable. A member version change or member invalidation requires a new Packet version; the old Packet enters `INVALIDATED`. If reassembly is needed, a new Packet version is created and re-frozen / re-validated. The `REVALIDATION_REQUIRED` state is not defined for Packet. A consumer must bind to an exact Packet `id + version + digest` triple; implicit `latest` resolution is forbidden.

The assembler may select, reference, order, freeze, and digest members only. The assembler must not: rewrite a member, supplement a role's conclusion, delete unfavourable Evidence, change the meaning of a Claim, or downgrade a FAIL to a warning.

Minimum packet types:

`INTAKE_SCOPE_PACKET`, `INTAKE_EVIDENCE_PACKET`, `EXPLORER_OUTPUT_PACKET`, `IMPLEMENTATION_PLAN_APPROVAL_PACKET`, `CANDIDATE_FROZEN_FOR_TEST`, `TESTER_A_INPUT_PACKET`, `TESTER_B_INPUT_PACKET`, `TEST_EVIDENCE_PACKET`, `REVIEW_INPUT_PACKET`, `INTEGRATION_INPUT_FROZEN`, `DRAFT_TO_READY_APPROVAL_PACKET`, `MERGE_APPROVAL_PACKET`, `BRANCH_DELETION_APPROVAL_PACKET`.

Tester-A and Tester-B input Packets must bind to the same CANDIDATE_TRIPLE but have different Packet IDs, digests, and charters. Neither may contain the other's output before the first report freeze. A Review Packet may be frozen only after `TEST_GATE_PASS`. An Integration Packet must bind the Work Order, assignment baseline, plan provenance, CANDIDATE_TRIPLE, Gate receipts, exact manifest, repo / base / branch, and commit / PR plan and delivery budgets.

Packet assembly, freeze, and validation each produce a distinct Receipt:

- `PACKET_ASSEMBLY_RECEIPT`
- `PACKET_FREEZE_RECEIPT`
- `PACKET_VALIDATION_RECEIPT` (where applicable)

These three must not be implicitly merged.

#### §10.3.9 Receipt Schema

A Receipt must record at least:

- `receipt_id` / `type` / `version` / `digest`
- `issuer_type` / `issuer_identity` / `authority_basis`
- `subject_id` / `subject_version` / `subject_digest` — `id + version + digest` triple
- `decision_result` — the substantive decision (PASS, FAIL, GRANTED, REVOKED, etc.)
- `state_created` — the **business workflow state** created by this Receipt (e.g., `GLOBAL_READINESS_PASS`, `GATE_PASS`, `AUTHORIZATION_GRANTED`); this is **not** the Receipt's own lifecycle state
- `reason_codes` — one or more reason codes
- `evidence_refs` — one or more `id + version + digest` Evidence references
- `prerequisite_receipts` — `id + version + digest` triples of prerequisite receipts
- `issued_at` — RFC 3339 UTC timestamp
- `expires_on_drift` — whether this receipt becomes stale on drift detection
- `invalidation_conditions` — conditions under which this receipt must be invalidated
- `lifecycle_state_at_creation` — `CURRENT` (immutable; effective status is computed from the append-only Receipt chain)
- `cryptographic_attestation.enabled` — `false` (reserved for future PKI)

The Receipt body and digest are **permanently immutable** from creation. The initial `lifecycle_state_at_creation` is `CURRENT`. Subsequent effective status transitions (`STALE`, `SUPERSEDED`, `REVOKED_BY_OPERATOR`) must be recorded by independent append-only Receipts:

- `INVALIDATION_RECEIPT` — marks a single subject object (Artifact, Evidence, Packet, or Receipt) as invalidated. The subject's effective status is computed as: `STALE` for a Receipt subject; `INVALIDATED` for Artifact, Evidence, or Packet subjects (or `REVALIDATION_REQUIRED` for Artifact). Each `INVALIDATION_RECEIPT` binds exactly one subject `id + version + digest` triple. Batch invalidation of multiple subjects is expressed via independent Receipts linked by a common `cause_ref` or `batch_ref` field (optional).
- `SUPERSESSION_RECEIPT` — marks a single subject Artifact, Evidence, Packet, or Receipt as `SUPERSEDED` and links to the `SUPERSEDING_OBJECT_TRIPLE`; subject and superseding object classes must be compatible.
- `OPERATOR_REVOCATION_RECEIPT` — issued only by the operator; marks a single subject operator-authorisation Receipt as `REVOKED_BY_OPERATOR`.

The authoritative effective status of any Receipt is computed from the immutable Receipt chain, not from in-place field mutation. `state_created` records the business workflow state created by this Receipt (e.g., `GLOBAL_READINESS_PASS`, `GATE_PASS`, `AUTHORIZATION_GRANTED`) and must not be conflated with the Receipt's own lifecycle state.

Receipt lifecycle states: `lifecycle_state_at_creation=CURRENT` (immutable). Effective statuses (computed from the append-only Receipt chain): `CURRENT`, `STALE`, `SUPERSEDED`, `REVOKED_BY_OPERATOR`.

#### §10.3.10 Authority Matrix

Only the operator may issue:

**Operator approval / authorisation receipts.** These Receipt types each carry `state_created` set to the corresponding business workflow state listed here (the backtick state names are **not** receipt type identifiers; they are the `state_created` values of the respective canonical receipt types):

| Receipt Type | `state_created` (business workflow state) |
|---|---|
| `OPERATOR_INTAKE_SCOPE_APPROVAL_RECEIPT` | `OPERATOR_APPROVED_INTAKE_SCOPE` |
| `OPERATOR_SUBMODE_SELECTION_RECEIPT` | `OPERATOR_SELECTED_SUBMODE` |
| `OPERATOR_ROLE_NODE_MODEL_ASSIGNMENT_APPROVAL_RECEIPT` | `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE` |
| `OPERATOR_WORK_ORDER_APPROVAL_RECEIPT` | `OPERATOR_APPROVED_WORK_ORDER` |
| `OPERATOR_IMPLEMENTATION_PLAN_APPROVAL_RECEIPT` | `OPERATOR_APPROVED_IMPLEMENTATION_PLAN` |
| `OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT` | `OPERATOR_AUTHORIZED_DRAFT_TO_READY` |
| `OPERATOR_MERGE_AUTHORIZATION_RECEIPT` | `OPERATOR_AUTHORIZED_MERGE` |
| `OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT` | `OPERATOR_AUTHORIZED_BRANCH_DELETION` |
| `OPERATOR_APPROVED_VERSION_PREPARATION_RECEIPT` | `VERSION_PREPARATION_APPROVED` (§3.8 V3) |
| `VERSION_PRE_EXECUTION_CHECKPOINT_REVIEW_RECEIPT` | `VERSION_CHECKPOINT_REVIEWED` / `VERSION_CHECKPOINT_BLOCKED` (§3.8 V4) |
| `OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT` | `VERSION_EXECUTION_AUTHORIZED` (§3.8 V5) |
| `OPERATOR_REVOCATION_RECEIPT` | `AUTHORISATION_REVOKED` |

Conflating a `state_created` business workflow state (e.g. `OPERATOR_APPROVED_INTAKE_SCOPE`) with a receipt type identifier triggers `RECEIPT_TYPE_AND_STATE_CREATED_CONFLATED → STOP`.

`vibedev` / orchestrator may issue within its authority:

- Global Readiness receipts (`GLOBAL_READINESS_RECEIPT`, `ROLE_ACTIVATION_READINESS_RECEIPT`)
- Activation receipts (role activation readiness)
- Role completion cross-verification receipts (`ROLE_CROSS_VERIFICATION_RECEIPT`)
- Explorer / Plan / Artifact validation receipts (`EXPLORER_VALIDATION_RECEIPT`, `PLAN_VALIDATION_RECEIPT`, `ARTIFACT_VALIDATION_RECEIPT`)
- Packet assembly, freeze, validation, and consumption receipts (`PACKET_ASSEMBLY_RECEIPT`, `PACKET_FREEZE_RECEIPT`, `PACKET_VALIDATION_RECEIPT`, `PACKET_CONSUMPTION_RECEIPT`)
- Gate aggregation and cross-verification receipts (`TEST_GATE_PASS_RECEIPT`, `TEST_GATE_FAIL_RECEIPT`, `REVIEW_GATE_PASS_RECEIPT`, `REVIEW_GATE_FAIL_RECEIPT`, `GIT_INTEGRATION_GATE_PASS_RECEIPT`, `GIT_INTEGRATION_GATE_FAIL_RECEIPT`)
- Ready transition receipt (`READY_TRANSITION_RECEIPT`)
- Post-Draft per-stage binding receipts (`POST_DRAFT_DRAFT_TO_READY_BINDING_RECEIPT`, `POST_DRAFT_MERGE_BINDING_RECEIPT`, `POST_DRAFT_BRANCH_DELETION_BINDING_RECEIPT` — one per stage, NOT a single shared `POST_DRAFT_GIT_INTEGRATOR_BINDING_RECEIPT`, which is deleted)
- Consultation endpoint receipt (`CONSULTATION_ENDPOINT_RECEIPT`)
- Public projection safety check receipt (`PUBLIC_PROJECTION_SAFETY_CHECK_RECEIPT`)
- Transition, invalidation, and supersession receipts (`STOP_RECEIPT`, `INVALIDATION_RECEIPT`, `SUPERSESSION_RECEIPT`)
- Version governance receipts (`VERSION_QUALIFICATION_PASS_RECEIPT`, `VERSION_QUALIFICATION_FAIL_RECEIPT`, `VERSION_GOVERNANCE_CLOSEOUT_RECEIPT`)
- Version inventory validation and proposal validation (§3.8 V1/V2 — via Artifact/validation receipt types)

A role produces only its Artifact (`ROLE_COMPLETION_REPORT`, `STOP_REPORT`) and associated Evidence. The role MUST NOT issue any Receipt type — `ROLE_COMPLETION_RECEIPT` is deleted (not a canonical type); `STOP_RECEIPT` is issued by vibedev/orchestrator only; git-integrator issuer class is a stage controller (NOT a business role producing role-completion Artifacts) and is bound to per-stage operator authorizations (`OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT` / `OPERATOR_MERGE_AUTHORIZATION_RECEIPT` / `OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT`) for the three Post-Draft operation Receipts (`POST_DRAFT_DRAFT_TO_READY_BINDING_RECEIPT`, `POST_DRAFT_MERGE_BINDING_RECEIPT`, `POST_DRAFT_BRANCH_DELETION_BINDING_RECEIPT`). The git-integrator submits only its execution and delivery evidence / claim; the final `VERIFIED` state is formed through the existing cross-verification chain.


#### §10.3.10.0 Closed Prerequisite Expression Grammar

**Every Registry row's `Prerequisite Receipt Types`, `Prerequisite Object Types`, and `Prerequisite Expression` columns must use only the following machine-resolvable DSL.** Any other predicate, operator, or natural-language phrase triggers `RECEIPT_REGISTRY_PREREQUISITE_EXPRESSION_UNPARSEABLE → STOP`.

**Canonical predicates (each with parameter types, return semantics, scope):**

| Predicate | Parameters | Return | scope | subject/object/stage binding | nested? | missing Receipt | CURRENT vs historical | NOT_APPLICABLE vs PASS |
|---|---|---|---|---|---|---|---|---|
| `TRUE` | — | always true | any | — | — | n/a | n/a | n/a |
| `AND(expr...)` | 1+ canonical expressions | logical AND | registry row | inherits row scope | yes | n/a | n/a | n/a |
| `OR(expr...)` | 1+ canonical expressions | logical OR | registry row | inherits row scope | yes | n/a | n/a | n/a |
| `EXACTLY_ONE_OF(expr...)` | 1+ canonical expressions | exactly-one true | registry row | inherits row scope | yes | n/a | n/a | n/a |
| `NOT(expr)` | 1 canonical expression | logical negation | registry row | inherits row scope | yes | n/a | n/a | n/a |
| `CURRENT(RECEIPT_TYPE)` or `CURRENT(RECEIPT_TYPE, INSTANCE_REF)` | canonical Receipt type (1st arg optional canonical object triple) | subject has a CURRENT Receipt of the given type optionally bound to given instance ref (must be a concrete ref from Catalog) | registry row | triple-bound via 2nd arg | no | returns FALSE | CURRENT only (`lifecycle_state_at_creation=CURRENT` AND no effective INVALIDATION/SUPERSESSION/REVOCATION on that subject/object triple); different subject/object triple or different version not CURRENT | NEVER `PASS`; receipts are CURRENT only when `lifecycle_state_at_creation=CURRENT` and not invalidated/superseded/revoked |
| `STATE_CREATED(RECEIPT_TYPE, STATE_VALUE)` | canonical Receipt type, canonical state value | subject's CURRENT Receipt's `state_created` equals value | registry row | last-arg only | no | returns FALSE | CURRENT only | n/a |
| `DECISION(RECEIPT_TYPE, DECISION_VALUE)` | canonical Receipt type, canonical decision value | subject's CURRENT Receipt's `decision` equals value | registry row | last-arg only | no | returns FALSE | CURRENT only | n/a |
| `VALID(OBJECT_TYPE)` | canonical object type | object lifecycle == VALID | registry row | n/a | no | FALSE | always-current validity | n/a |
| `SAME_OBJECT(ref...)` | 1+ canonical refs | all refs point to same object triple | registry row | n/a | yes | FALSE | n/a | n/a |
| `SUBJECT_MATCH(RECEIPT_TYPE, SUBJECT_REF)` | canonical Receipt type, canonical subject ref | subject's CURRENT Receipt subject == SUBJECT_REF | registry row | required | no | FALSE | CURRENT only | n/a |
| `MODE_IS(MODE)` | one of FULL / LIGHTWEIGHT / CONSULTATION_ONLY | execution mode matches | registry row | n/a | no | FALSE | always-current mode | n/a |
| `STAGE_IS(STAGE)` | canonical stage name | execution stage matches | registry row | n/a | no | FALSE | always-current stage | n/a |
| `PLAN_CHECKPOINT_IS(STATE)` | ENABLED / DISABLED | plan checkpoint config matches | LIGHTWEIGHT branch only | n/a | no | FALSE | always-current config | n/a |
| `ROLE_INSTANTIATED(ROLE)` | canonical role name | role instantiated in current scope | row | n/a | no | FALSE | current instantiation only | n/a |
| `DIRECT_TO_IMPLEMENTER_IS(STATE)` | TRUE / FALSE | direct-to-implementer config matches | LIGHTWEIGHT branch only | n/a | no | FALSE | always-current config | n/a |
| `NOT_APPLICABLE_IF(condition, expr)` | 1st: canonical condition; 2nd: canonical expression | three-state: condition TRUE → row NOT_APPLICABLE (no Receipt created, no state); condition FALSE → evaluate expr normally | registry row MUST be outermost | inherits row scope | 1st: no; 2nd: yes | condition TRUE → NOT_APPLICABLE | n/a | NOT_APPLICABLE ≠ PASS ≠ FAIL; NOT_APPLICABLE means row not instantiated; PASS means state created; FAIL means failure state created
| `EVIDENCE_OF(CONDITION, SUBJECT_REF)` | canonical Evidence condition string (1st arg), canonical object/ref triple (2nd arg) | Evidence chain contains matching condition Evidence bound to given subject/ref | registry row | subject-bound via 2nd arg | no | FALSE | always-current Evidence for given ref | n/a |


| `ROW_SUBJECT_IS(OBJECT_REF)` | canonical object ref | current Receipt subject equals OBJECT_REF (no self-reference; verified at issuance check time) | registry row | n/a | no | n/a | n/a | n/a |
| `ROW_OPERATION_IS(OPERATION_REF)` | canonical operation ref | current operation ref equals OPERATION_REF | registry row | n/a | no | n/a | n/a | n/a |
| `SAME_OPERATION(ref...)` | 1+ operation refs | all refs share same operation id/version/digest (different from SAME_OBJECT which tests identical triple) | registry row | n/a | yes | FALSE | current operation only | n/a |

| `OBJECT_CLASS_IS(CLASS)` | one of `ROLE_PRODUCED_ARTIFACT` / `GOVERNANCE_ARTIFACT_OR_APPROVAL` | object class matches current artifact | registry row | n/a | no | FALSE | current object class only | n/a |
| `STATE_CREATED(RECEIPT_TYPE, INSTANCE_REF, STATE)` | canonical Receipt type, concrete INSTANCE_REF from Catalog, canonical state_created value | the specific Receipt INSTANCE has state equal to STATE | registry row | instance-bound via 2nd arg | no | FALSE if no CURRENT instance with that state | CURRENT instance only | n/a |
| `DECISION(RECEIPT_TYPE, INSTANCE_REF, DECISION_VALUE)` | canonical Receipt type, concrete INSTANCE_REF from Catalog, canonical decision value | the specific Receipt INSTANCE has decision equal to DECISION_VALUE | registry row | instance-bound via 2nd arg | no | FALSE if no CURRENT instance with that decision | CURRENT instance only | n/a |
| `CURRENT(RECEIPT_TYPE, INSTANCE_REF)` | canonical Receipt type (1st arg), concrete instance ref (2nd arg) | the specific Receipt INSTANCE is CURRENT | registry row | instance-bound via 2nd arg | no | FALSE if no CURRENT instance | `lifecycle_state_at_creation=CURRENT` AND no effective INVALIDATION/SUPERSESSION/REVOCATION on that instance | n/a |
| `PACKET_CLASS_IS(CLASS)` | one of FULL_EXECUTION / LIGHTWEIGHT_WITH_PLANNER / LIGHTWEIGHT_DIRECT_TO_IMPLEMENTER / VERSION_GOVERNANCE / DRAFT_TO_READY_APPROVAL / MERGE_APPROVAL / BRANCH_DELETION_APPROVAL / CONSULTATION_SOURCE | packet class matches current operation | registry row | n/a | no | FALSE | always-current packet class | n/a |
**Canonical operators:** `AND`, `OR`, `EXACTLY_ONE_OF`, `NOT`. (Implemented as `expr`-list predicates above.)

**Canonical Evidence classes** (only `EVIDENCE_OF` may reference): listed per row in `Required Evidence Classes` column. `DECISION()` first argument is a canonical Receipt type, NEVER `TEST_RESULT` or any Evidence class.

### §10.3.12 Canonical Object / Reference Catalog

All Object Types, concrete refs, role refs, operation refs, and Evidence subject refs used in the Registry. Each entry defines token name, class, identity structure, lifecycle, permissible stage/mode, and whether type-token or concrete-ref.

### §10.3.10.2 Canonical Object / Reference Catalog

All Object Types, concrete refs, role refs, operation refs, and Evidence subject refs used in the Registry. Each entry defines token name, class, identity structure, lifecycle, permissible stage/mode, and whether type-token or concrete-ref.

| Token | Class | Identity (id+version+digest) | Lifecycle | Stage/Mode | Category |
|---|---|---|---|---|---|
| `WORK_ORDER_DECLARATION` | reference triple | declared | n/a (payload) | all modes | type token |
| `SUBMODE_DECLARATION` | reference triple | declared | n/a (payload) | intake | type token |
| `CANDIDATE_TRIPLE` | object triple | id+version+digest | n/a (execution) | TEST, REVIEW, GIT | concrete ref |
| `PR_TRIPLE` | object triple | id+version+digest | n/a (post-Draft) | READY, MERGE | concrete ref |
| `BRANCH_TRIPLE` | object triple | id+version+digest | n/a (post-Draft) | BRANCH_DELETION | concrete ref |
| `SUBJECT_TRIPLE` | object triple | id+version+digest | n/a | INVALIDATION | concrete ref |
| `SUPERSEDING_OBJECT_TRIPLE` | object triple | id+version+digest | n/a | SUPERSESSION | concrete ref |
| `AUTHORISATION_RECEIPT_TRIPLE` | receipt-derived | subject Receipt triple | Receipt lifecycle | operator all | concrete ref |
| `SUBJECT_ARTIFACT_TRIPLE` | artifact triple | id+version+digest | ARTIFACT lifecycle | AV, EXPLORER, PLAN | concrete ref |
| `INTAKE_SCOPE_PACKET` | packet | id+version+digest | PACKET lifecycle | INTAKE | concrete ref |
| `INTAKE_EVIDENCE_PACKET` | packet | id+version+digest | PACKET lifecycle | INTAKE | concrete ref |
| `ROLE_ACTIVATION_PACKET` | packet | id+version+digest | PACKET lifecycle | F, LL | concrete ref |
| `ROLE_COMPLETION_REPORT` | artifact | id+version+digest | ARTIFACT lifecycle | all execution | concrete ref |
| `ROLE_NODE_MODEL_ASSIGNMENT_BASELINE_PACKET` | packet | id+version+digest | PACKET lifecycle | ASSIGNMENT | concrete ref |
| `IMPLEMENTATION_PLAN` | artifact | id+version+digest | ARTIFACT lifecycle | PLAN | concrete ref |
| `IMPLEMENTATION_PLAN_APPROVAL_PACKET` | packet | id+version+digest | PACKET lifecycle | PLAN_APPROVAL | concrete ref |
| `EXPLORER_ARTIFACT` | artifact | id+version+digest | ARTIFACT lifecycle | EXPLORER | concrete ref |
| `GIT_INTEGRATOR_ROLE_TRIPLE` | role-derived | id+version+digest | ROLE lifecycle | GIT | type token |
| `GIT_INTEGRATOR_ACTIVATION_EVIDENCE` | evidence | id+version+digest | EVIDENCE lifecycle | GIT | type token |
| `GIT_INTEGRATOR_ACTIVATION_EVIDENCE_DRAFT_TO_READY` | evidence | id+version+digest | EVIDENCE lifecycle | DRAFT_TO_READY | concrete ref |
| `GIT_INTEGRATOR_ACTIVATION_EVIDENCE_MERGE` | evidence | id+version+digest | EVIDENCE lifecycle | MERGE | concrete ref |
| `GIT_INTEGRATOR_ACTIVATION_EVIDENCE_BD` | evidence | id+version+digest | EVIDENCE lifecycle | BD | concrete ref |
| `SOURCE_EVIDENCE_OBJECTS` | evidence | id+version+digest | EVIDENCE lifecycle | PUBLIC_SAFETY | type token |
| `TESTER_A_INPUT_PACKET` | packet | id+version+digest | PACKET lifecycle | TEST | concrete ref |
| `TESTER_B_INPUT_PACKET` | packet | id+version+digest | PACKET lifecycle | TEST | concrete ref |
| `TEST_EVIDENCE_PACKET` | packet | id+version+digest | PACKET lifecycle | TEST | concrete ref |
| `REVIEW_INPUT_PACKET` | packet | id+version+digest | PACKET lifecycle | REVIEW | concrete ref |
| `INTEGRATION_INPUT_FROZEN` | packet | id+version+digest | PACKET lifecycle | GIT | concrete ref |
| `DRAFT_TO_READY_APPROVAL_PACKET` | packet | id+version+digest | PACKET lifecycle | DRAFT_TO_READY | concrete ref |
| `MERGE_APPROVAL_PACKET` | packet | id+version+digest | PACKET lifecycle | MERGE | concrete ref |
| `BRANCH_DELETION_APPROVAL_PACKET` | packet | id+version+digest | PACKET lifecycle | BD | concrete ref |
| `CONSULTATION_SOURCE_PACKET` | packet | id+version+digest | PACKET lifecycle | CONSULTATION | concrete ref |
| `STOP_REPORT` | artifact | id+version+digest | ARTIFACT lifecycle | STOP | concrete ref |
| `VERSION_GOVERNANCE_SCOPE_PACKET` | packet | id+version+digest | PACKET lifecycle | V0 | concrete ref |
| `VERSION_INVENTORY_ARTIFACT` | artifact | id+version+digest | ARTIFACT lifecycle | V1 | concrete ref |
| `VERSION_CHANGE_PROPOSAL_ARTIFACT` | artifact | id+version+digest | ARTIFACT lifecycle | V2 | concrete ref |
| `VERSION_PREPARATION_PACKET` | packet | id+version+digest | PACKET lifecycle | V3 | concrete ref |
| `VERSION_PRE_EXECUTION_CHECKPOINT_PACKET` | packet | id+version+digest | PACKET lifecycle | V4 | concrete ref |
| `VERSION_EXECUTION_AUTHORIZATION_PACKET` | packet | id+version+digest | PACKET lifecycle | V5 | concrete ref |
| `VERSION_EXECUTION_REPORT` | report | id+version+digest | REPORT lifecycle | V6 | concrete ref |
| `VERSION_EXECUTION_EVIDENCE_PACKET` | packet | id+version+digest | PACKET lifecycle | V6 | concrete ref |
| `VERSION_QUALIFICATION_PACKET` | packet | id+version+digest | PACKET lifecycle | V7 | concrete ref |
| `VERSION_CLOSEOUT_REPORT` | report | id+version+digest | REPORT lifecycle | V8 | concrete ref |
| `TESTER_A_ROLE_TRIPLE` | role-derived | id+version+digest | ROLE lifecycle | TEST | concrete ref |
| `TESTER_B_ROLE_TRIPLE` | role-derived | id+version+digest | ROLE lifecycle | TEST | concrete ref |
| `REVIEWER_A_ROLE_TRIPLE` | role-derived | id+version+digest | ROLE lifecycle | REVIEW | concrete ref |
| `REVIEWER_B_ROLE_TRIPLE` | role-derived | id+version+digest | ROLE lifecycle | REVIEW | concrete ref |
| `VERSION_OPERATION_REF` | operation ref | id+version+digest | n/a (governance) | V0–V8 | concrete ref |
| `READY_TRANSITION_COMPLETION_REPORT` | completion report | id+version+digest | REPORT lifecycle | DRAFT_TO_READY | concrete ref |
| `MERGE_COMPLETION_REPORT` | completion report | id+version+digest | REPORT lifecycle | MERGE | concrete ref |
| `BRANCH_DELETION_COMPLETION_REPORT` | completion report | id+version+digest | REPORT lifecycle | BD | concrete ref |

| `TEST_OPERATION_REF` | operation ref | id+version+digest | n/a (execution) | TEST | concrete ref |
| `REVIEW_OPERATION_REF` | operation ref | id+version+digest | n/a (execution) | REVIEW | concrete ref |
| `GIT_OPERATION_REF` | operation ref | id+version+digest | n/a (execution) | GIT | concrete ref |
| `DRAFT_TO_READY_OPERATION_REF` | operation ref | id+version+digest | n/a (execution) | DRAFT_TO_READY | concrete ref |
| `MERGE_OPERATION_REF` | operation ref | id+version+digest | n/a (execution) | MERGE | concrete ref |
| `BRANCH_DELETION_OPERATION_REF` | operation ref | id+version+digest | n/a (execution) | BD | concrete ref |
| `PACKET_OPERATION_REF` | operation ref | id+version+digest | n/a (execution) | all | concrete ref |
| `GENERIC_PACKET_REF` | packet derived | id+version+digest | PACKET lifecycle | all | concrete ref |
| `TESTER_A_INVOCATION_REF` | invocation ref | id+version+digest | n/a (execution) | TEST | concrete ref |
| `TESTER_B_INVOCATION_REF` | invocation ref | id+version+digest | n/a (execution) | TEST | concrete ref |
| `REVIEWER_A_INVOCATION_REF` | invocation ref | id+version+digest | n/a (execution) | REVIEW | concrete ref |
| `REVIEWER_B_INVOCATION_REF` | invocation ref | id+version+digest | n/a (execution) | REVIEW | concrete ref |
| `DRAFT_TO_READY_INVOCATION_REF` | invocation ref | id+version+digest | n/a (execution) | DRAFT_TO_READY | concrete ref |
| `MERGE_INVOCATION_REF` | invocation ref | id+version+digest | n/a (execution) | MERGE | concrete ref |
| `BRANCH_DELETION_INVOCATION_REF` | invocation ref | id+version+digest | n/a (execution) | BD | concrete ref |

| `TESTER_A_CROSS_VERIFICATION_REF` | cross-verification ref | id+version+digest | n/a | TEST | concrete ref |
| `TESTER_B_CROSS_VERIFICATION_REF` | cross-verification ref | id+version+digest | n/a | TEST | concrete ref |
| `REVIEWER_A_CROSS_VERIFICATION_REF` | cross-verification ref | id+version+digest | n/a | REVIEW | concrete ref |
| `REVIEWER_B_CROSS_VERIFICATION_REF` | cross-verification ref | id+version+digest | n/a | REVIEW | concrete ref |
| `GIT_CROSS_VERIFICATION_REF` | cross-verification ref | id+version+digest | n/a | GIT | concrete ref |
| `READY_CROSS_VERIFICATION_REF` | cross-verification ref | id+version+digest | n/a | DRAFT_TO_READY | concrete ref |
| `MERGE_CROSS_VERIFICATION_REF` | cross-verification ref | id+version+digest | n/a | MERGE | concrete ref |
| `BD_CROSS_VERIFICATION_REF` | cross-verification ref | id+version+digest | n/a | BD | concrete ref |


#### §10.3.10.1 Authority Matrix — Registry Issuer Closure

**Requirement:** `Registry_issuers − Matrix_issuers = 0` AND `Matrix_issuers − Registry_issuers = 0`. Each issuer class must explicitly enumerate: (a) which Receipt types it may sign, (b) at which stage, (c) under what operator authorization.

| Issuer Class | May Sign | Stage | Operator Authorization Required |
|---|---|---|---|
| `operator` | `OPERATOR_INTAKE_SCOPE_APPROVAL_RECEIPT`, `OPERATOR_SUBMODE_SELECTION_RECEIPT`, `OPERATOR_ROLE_NODE_MODEL_ASSIGNMENT_APPROVAL_RECEIPT`, `OPERATOR_WORK_ORDER_APPROVAL_RECEIPT`, `OPERATOR_IMPLEMENTATION_PLAN_APPROVAL_RECEIPT`, `OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT`, `OPERATOR_MERGE_AUTHORIZATION_RECEIPT`, `OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT`, `OPERATOR_APPROVED_VERSION_PREPARATION_RECEIPT`, `VERSION_PRE_EXECUTION_CHECKPOINT_REVIEW_RECEIPT`, `OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT`, `OPERATOR_REVOCATION_RECEIPT` | all stages (intake, submode, assignment, Work Order, plan approval, Draft→Ready authorization, Merge authorization, Branch Deletion authorization, Version Gate V3–V5, revocation) | n/a (operator is the authoriser) |
| `vibedev/orchestrator` | `GLOBAL_READINESS_RECEIPT`, `ROLE_ACTIVATION_READINESS_RECEIPT`, `ROLE_CROSS_VERIFICATION_RECEIPT`, `EXPLORER_VALIDATION_RECEIPT`, `PLAN_VALIDATION_RECEIPT`, `TEST_GATE_PASS_RECEIPT`, `TEST_GATE_FAIL_RECEIPT`, `REVIEW_GATE_PASS_RECEIPT`, `REVIEW_GATE_FAIL_RECEIPT`, `GIT_INTEGRATION_GATE_PASS_RECEIPT`, `GIT_INTEGRATION_GATE_FAIL_RECEIPT`, `READY_TRANSITION_RECEIPT`, `CONSULTATION_ENDPOINT_RECEIPT`, `PUBLIC_PROJECTION_SAFETY_CHECK_RECEIPT`, `STOP_RECEIPT`, `INVALIDATION_RECEIPT`, `SUPERSESSION_RECEIPT`, `VERSION_QUALIFICATION_PASS_RECEIPT`, `VERSION_QUALIFICATION_FAIL_RECEIPT`, `VERSION_GOVERNANCE_CLOSEOUT_RECEIPT`, `PACKET_FREEZE_RECEIPT`, `PACKET_VALIDATION_RECEIPT` | all non-operator-dependent stages | per-row authority basis (operator decision + role approval Receipt) |
| `git-integrator` | `PRE_DRAFT_GIT_INTEGRATOR_BINDING_RECEIPT` (pre-Draft), `POST_DRAFT_DRAFT_TO_READY_BINDING_RECEIPT` (Draft→Ready), `POST_DRAFT_MERGE_BINDING_RECEIPT` (Merge), `POST_DRAFT_BRANCH_DELETION_BINDING_RECEIPT` (BD), `DRAFT_PR_DELIVERY_RECEIPT`, `MERGE_DELIVERY_RECEIPT`, `BRANCH_DELETION_RECEIPT` (7 types, per-stage) | Git Integration stage + per-stage Post-Draft operations | stage-specific: `OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT` for Draft→Ready binding; `OPERATOR_MERGE_AUTHORIZATION_RECEIPT` for Merge binding; `OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT` for Branch Deletion binding |
| `validator per mode` | `ARTIFACT_VALIDATION_RECEIPT` | validator per mode (operator-approved validator mapping determines execution identity per object class) | per artifact class/mode | n/a | |
| `consumer role/stage controller (vibedev/orchestrator)` | `PACKET_CONSUMPTION_RECEIPT` | consumer stage | `PACKET_FREEZE_RECEIPT` + `PACKET_VALIDATION_RECEIPT` (no operator authorization) |
| `assembler (vibedev/orchestrator)` | `PACKET_ASSEMBLY_RECEIPT` | assembly stage | upstream role completion + validation Receipts (no operator authorization at assembly) |

**Business role vs stage controller distinction:** A role produces only `ROLE_COMPLETION_REPORT` Artifact + Evidence (per `ROLE_CROSS_VERIFICATION_RECEIPT` model). The git-integrator is a stage controller under operator authorization, NOT a role producing role-completion Artifacts. The `git-integrator (per-stage, post-Draft re-authorization)` clarification is exhaustively split into three canonical types: `POST_DRAFT_DRAFT_TO_READY_BINDING_RECEIPT`, `POST_DRAFT_MERGE_BINDING_RECEIPT`, `POST_DRAFT_BRANCH_DELETION_BINDING_RECEIPT`. The obsolete generic `POST_DRAFT_GIT_INTEGRATOR_BINDING_RECEIPT` is **deleted** and triggers `RECEIPT_TYPE_AND_STATE_CREATED_CONFLATED` if any operator-facing text references it.

Canonical receipt type registry (10 canonical columns):

| `Receipt Type` | `Issuer Class` | `Authority Basis` | `Subject Class` | `Prerequisite Object Types` | `Prerequisite Receipt Types` | `Prerequisite Expression` | `Required Evidence Classes` | `Decision` | `state_created` |
|---|---|---|---|---|---|---|---|---|---|

| `GLOBAL_READINESS_RECEIPT` | vibedev/orchestrator | operator Work Order approval | scope packet triple | `INTAKE_SCOPE_PACKET`, `INTAKE_EVIDENCE_PACKET`, `WORK_ORDER_DECLARATION` | `OPERATOR_INTAKE_SCOPE_APPROVAL_RECEIPT`, `OPERATOR_SUBMODE_SELECTION_RECEIPT`, `OPERATOR_WORK_ORDER_APPROVAL_RECEIPT` | AND(CURRENT(OPERATOR_INTAKE_SCOPE_APPROVAL_RECEIPT), CURRENT(OPERATOR_SUBMODE_SELECTION_RECEIPT), CURRENT(OPERATOR_WORK_ORDER_APPROVAL_RECEIPT), STATE_CREATED(OPERATOR_WORK_ORDER_APPROVAL_RECEIPT, OPERATOR_APPROVED_WORK_ORDER)) | COMMAND_RESULT, FILE_SNAPSHOT, OPERATOR_DECISION_RECORD | APPROVED / BLOCKED | GLOBAL_READINESS_PASS / GLOBAL_READINESS_FAIL |
| `ROLE_ACTIVATION_READINESS_RECEIPT` | vibedev/orchestrator (FULL/LIGHTWEIGHT only — not Consultation) | Global Readiness + role/node/model assignment approval | activation packet triple | `ROLE_ACTIVATION_PACKET` | `OPERATOR_ROLE_NODE_MODEL_ASSIGNMENT_APPROVAL_RECEIPT`, `GLOBAL_READINESS_RECEIPT` | AND(CURRENT(OPERATOR_ROLE_NODE_MODEL_ASSIGNMENT_APPROVAL_RECEIPT), CURRENT(GLOBAL_READINESS_RECEIPT), STATE_CREATED(GLOBAL_READINESS_RECEIPT, GLOBAL_READINESS_PASS), OR(MODE_IS(FULL), MODE_IS(LIGHTWEIGHT))) | READINESS_CHECK, NODE_ROUTE_PROBE, MODEL_INVOCATION_RECORD | READY / BLOCKED | ROLE_ACTIVATION_READY / ROLE_ACTIVATION_BLOCKED |
| `ROLE_CROSS_VERIFICATION_RECEIPT` | vibedev/orchestrator | role completion report Artifact | ROLE_COMPLETION_REPORT triple | `ROLE_COMPLETION_REPORT` | `GLOBAL_READINESS_RECEIPT` | AND(CURRENT(GLOBAL_READINESS_RECEIPT)) | GIT_OBJECT, TEST_RESULT, MODEL_INVOCATION_RECORD, OPERATOR_DECISION_RECORD | VERIFIED / INCOMPLETE / REJECTED | ROLE_CROSS_VERIFIED / ROLE_CROSS_VERIFICATION_INCOMPLETE / ROLE_CROSS_VERIFICATION_REJECTED |
| `EXPLORER_VALIDATION_RECEIPT` | vibedev/orchestrator | explorer Artifact | EXPLORER_ARTIFACT triple | `EXPLORER_ARTIFACT` | `ROLE_CROSS_VERIFICATION_RECEIPT` | AND(CURRENT(ROLE_CROSS_VERIFICATION_RECEIPT), STATE_CREATED(ROLE_CROSS_VERIFICATION_RECEIPT, ROLE_CROSS_VERIFIED)) | MODEL_INVOCATION_RECORD, FILE_SNAPSHOT | VALID / INVALID | EXPLORER_VALIDATED / EXPLORER_VALIDATION_FAILED |
| `PLAN_VALIDATION_RECEIPT` | vibedev/orchestrator | implementation plan Artifact | IMPLEMENTATION_PLAN triple | `IMPLEMENTATION_PLAN` | `EXPLORER_VALIDATION_RECEIPT` | AND(CURRENT(EXPLORER_VALIDATION_RECEIPT), STATE_CREATED(EXPLORER_VALIDATION_RECEIPT, EXPLORER_VALIDATED)) | MODEL_INVOCATION_RECORD, FILE_SNAPSHOT | VALID / INVALID | PLAN_VALIDATED / PLAN_VALIDATION_FAILED |
| `ARTIFACT_VALIDATION_RECEIPT` | validator per mode (operator-approved mapping decides object class → validator identity) | Artifact type + mode | any Artifact triple | `SUBJECT_ARTIFACT_TRIPLE` | ∅ | EVIDENCE_OF(VALIDATION_EVIDENCE, SUBJECT_ARTIFACT_TRIPLE) | MODEL_INVOCATION_RECORD, FILE_SNAPSHOT | VALID / INVALID | ARTIFACT_VALIDATED / ARTIFACT_INVALID |
| `PACKET_ASSEMBLY_RECEIPT` | assembler (vibedev/orchestrator) | assembly completion | assembled Packet triple , `GENERIC_PACKET_REF`, `PACKET_OPERATION_REF`| ∅ | `EXPLORER_VALIDATION_RECEIPT`, `PLAN_VALIDATION_RECEIPT`, `ARTIFACT_VALIDATION_RECEIPT` | AND(CURRENT(ARTIFACT_VALIDATION_RECEIPT), OR(AND(PACKET_CLASS_IS(FULL_EXECUTION), CURRENT(EXPLORER_VALIDATION_RECEIPT), CURRENT(PLAN_VALIDATION_RECEIPT), STATE_CREATED(PLAN_VALIDATION_RECEIPT, PLAN_VALIDATED)), AND(PACKET_CLASS_IS(LIGHTWEIGHT_WITH_PLANNER), CURRENT(EXPLORER_VALIDATION_RECEIPT), CURRENT(PLAN_VALIDATION_RECEIPT)), AND(PACKET_CLASS_IS(LIGHTWEIGHT_DIRECT_TO_IMPLEMENTER)), AND(PACKET_CLASS_IS(VERSION_GOVERNANCE)), AND(PACKET_CLASS_IS(DRAFT_TO_READY_APPROVAL)), AND(PACKET_CLASS_IS(MERGE_APPROVAL)), AND(PACKET_CLASS_IS(BRANCH_DELETION_APPROVAL)), AND(PACKET_CLASS_IS(CONSULTATION_SOURCE)))) | DIFF_MANIFEST, TREE_MANIFEST | ASSEMBLED | PACKET_ASSEMBLED |
| `PACKET_FREEZE_RECEIPT` | vibedev/orchestrator | Packet assembly | Packet triple | ∅ | `PACKET_ASSEMBLY_RECEIPT` | AND(CURRENT(PACKET_ASSEMBLY_RECEIPT), STATE_CREATED(PACKET_ASSEMBLY_RECEIPT, PACKET_ASSEMBLED)) | FILE_SNAPSHOT, GIT_OBJECT | FROZEN | PACKET_FROZEN |
| `PACKET_VALIDATION_RECEIPT` | vibedev/orchestrator | Packet freeze | Packet triple | ∅ | `PACKET_FREEZE_RECEIPT` | AND(CURRENT(PACKET_FREEZE_RECEIPT), STATE_CREATED(PACKET_FREEZE_RECEIPT, PACKET_FROZEN)) | DIFF_MANIFEST, TREE_MANIFEST, TEST_RESULT | VALIDATED / INVALID | PACKET_VALIDATED / PACKET_VALIDATION_FAILED |
| `PACKET_CONSUMPTION_RECEIPT` | consumer role/stage controller (vibedev/orchestrator) | frozen (optionally validated) Packet | Packet triple | ∅ | `PACKET_FREEZE_RECEIPT`, `PACKET_VALIDATION_RECEIPT` | AND(CURRENT(PACKET_FREEZE_RECEIPT), CURRENT(PACKET_VALIDATION_RECEIPT), STATE_CREATED(PACKET_FREEZE_RECEIPT, PACKET_FROZEN), STATE_CREATED(PACKET_VALIDATION_RECEIPT, PACKET_VALIDATED)) | CONSUMER_EVIDENCE | CONSUMED | PACKET_CONSUMED |
| `TEST_GATE_PASS_RECEIPT` | vibedev/orchestrator | tester-a + tester-b cross-verification + same CANDIDATE_TRIPLE + input Packet freeze + validated CANDIDATE_TRIPLE | test evidence packet triple | `TESTER_A_INPUT_PACKET`, `TESTER_B_INPUT_PACKET`, CANDIDATE_TRIPLE | `ROLE_CROSS_VERIFICATION_RECEIPT`, `PACKET_FREEZE_RECEIPT` | AND(CURRENT(ROLE_CROSS_VERIFICATION_RECEIPT, TESTER_A_ROLE_TRIPLE), CURRENT(ROLE_CROSS_VERIFICATION_RECEIPT, TESTER_B_ROLE_TRIPLE), CURRENT(PACKET_FREEZE_RECEIPT), STATE_CREATED(ROLE_CROSS_VERIFICATION_RECEIPT, ROLE_CROSS_VERIFIED), STAGE_IS(TEST)) | TEST_RESULT, MODEL_INVOCATION_RECORD | PASS | GATE_PASS |
| `TEST_GATE_FAIL_RECEIPT` | vibedev/orchestrator | tester-a or tester-b failure + same CANDIDATE_TRIPLE + input Packet freeze | test evidence packet triple | `TESTER_A_INPUT_PACKET`, `TESTER_B_INPUT_PACKET`, CANDIDATE_TRIPLE | `ROLE_CROSS_VERIFICATION_RECEIPT`, `PACKET_FREEZE_RECEIPT` | AND(CURRENT(ROLE_CROSS_VERIFICATION_RECEIPT, TESTER_A_ROLE_TRIPLE), CURRENT(ROLE_CROSS_VERIFICATION_RECEIPT, TESTER_B_ROLE_TRIPLE), CURRENT(PACKET_FREEZE_RECEIPT), OR(STATE_CREATED(ROLE_CROSS_VERIFICATION_RECEIPT, ROLE_CROSS_VERIFICATION_INCOMPLETE), STATE_CREATED(ROLE_CROSS_VERIFICATION_RECEIPT, ROLE_CROSS_VERIFICATION_REJECTED)), STAGE_IS(TEST)) | TEST_RESULT, MODEL_INVOCATION_RECORD | FAIL | GATE_FAIL |
| `REVIEW_GATE_PASS_RECEIPT` | vibedev/orchestrator | reviewer-a + reviewer-b cross-verification + same Review Packet/CANDIDATE_TRIPLE + TEST_GATE_PASS_RECEIPT + same-stage scope | review input packet triple | `REVIEW_INPUT_PACKET`, CANDIDATE_TRIPLE | `ROLE_CROSS_VERIFICATION_RECEIPT`, `PACKET_FREEZE_RECEIPT`, `TEST_GATE_PASS_RECEIPT` | AND(CURRENT(ROLE_CROSS_VERIFICATION_RECEIPT, REVIEWER_A_ROLE_TRIPLE), CURRENT(ROLE_CROSS_VERIFICATION_RECEIPT, REVIEWER_B_ROLE_TRIPLE), CURRENT(PACKET_FREEZE_RECEIPT), CURRENT(TEST_GATE_PASS_RECEIPT), STATE_CREATED(ROLE_CROSS_VERIFICATION_RECEIPT, ROLE_CROSS_VERIFIED), STATE_CREATED(TEST_GATE_PASS_RECEIPT, GATE_PASS), STAGE_IS(REVIEW)) | MODEL_INVOCATION_RECORD, FILE_SNAPSHOT | PASS | GATE_PASS |
| `REVIEW_GATE_FAIL_RECEIPT` | vibedev/orchestrator | reviewer-a or reviewer-b failure + same Review Packet/CANDIDATE_TRIPLE + TEST_GATE_PASS_RECEIPT | review input packet triple | `REVIEW_INPUT_PACKET`, CANDIDATE_TRIPLE | `ROLE_CROSS_VERIFICATION_RECEIPT`, `PACKET_FREEZE_RECEIPT`, `TEST_GATE_PASS_RECEIPT` | AND(CURRENT(ROLE_CROSS_VERIFICATION_RECEIPT, REVIEWER_A_ROLE_TRIPLE), CURRENT(ROLE_CROSS_VERIFICATION_RECEIPT, REVIEWER_B_ROLE_TRIPLE), CURRENT(PACKET_FREEZE_RECEIPT), CURRENT(TEST_GATE_PASS_RECEIPT), OR(STATE_CREATED(ROLE_CROSS_VERIFICATION_RECEIPT, ROLE_CROSS_VERIFICATION_INCOMPLETE), STATE_CREATED(ROLE_CROSS_VERIFICATION_RECEIPT, ROLE_CROSS_VERIFICATION_REJECTED)), STATE_CREATED(TEST_GATE_PASS_RECEIPT, GATE_PASS), STAGE_IS(REVIEW)) | MODEL_INVOCATION_RECORD, FILE_SNAPSHOT | FAIL | GATE_FAIL |
| `PRE_DRAFT_GIT_INTEGRATOR_BINDING_RECEIPT` | git-integrator | pre-Draft git-integrator binding for Git Integration stage + Draft PR delivery | git-integrator role Assignment + Git Integration Activation Evidence | `GIT_INTEGRATOR_ROLE_TRIPLE`, `GIT_INTEGRATION_ACTIVATION_EVIDENCE` | `ROLE_ACTIVATION_READINESS_RECEIPT` | AND(CURRENT(ROLE_ACTIVATION_READINESS_RECEIPT), STATE_CREATED(ROLE_ACTIVATION_READINESS_RECEIPT, ROLE_ACTIVATION_READY), OR(MODE_IS(FULL), MODE_IS(LIGHTWEIGHT))) | GIT_OBJECT, PR_METADATA_SNAPSHOT, MODEL_INVOCATION_RECORD | BOUND / UNBOUND | GIT_INTEGRATOR_PRE_DRAFT_BOUND / GIT_INTEGRATOR_PRE_DRAFT_UNBOUND |
| `GIT_INTEGRATION_GATE_PASS_RECEIPT` | vibedev/orchestrator | REVIEW_GATE_PASS_RECEIPT + Integration Packet assembly + freeze + validation + PRE_DRAFT_GIT_INTEGRATOR_BINDING | INTEGRATION_INPUT_FROZEN triple | `INTEGRATION_INPUT_FROZEN`, `CANDIDATE_TRIPLE` | `REVIEW_GATE_PASS_RECEIPT`, `PACKET_ASSEMBLY_RECEIPT`, `PACKET_FREEZE_RECEIPT`, `PACKET_VALIDATION_RECEIPT`, `PRE_DRAFT_GIT_INTEGRATOR_BINDING_RECEIPT` | AND(CURRENT(REVIEW_GATE_PASS_RECEIPT), CURRENT(PACKET_ASSEMBLY_RECEIPT), CURRENT(PACKET_FREEZE_RECEIPT), CURRENT(PACKET_VALIDATION_RECEIPT), CURRENT(PRE_DRAFT_GIT_INTEGRATOR_BINDING_RECEIPT), STATE_CREATED(REVIEW_GATE_PASS_RECEIPT, GATE_PASS), STATE_CREATED(PACKET_FREEZE_RECEIPT, PACKET_FROZEN), STATE_CREATED(PACKET_VALIDATION_RECEIPT, PACKET_VALIDATED), STATE_CREATED(PRE_DRAFT_GIT_INTEGRATOR_BINDING_RECEIPT, GIT_INTEGRATOR_PRE_DRAFT_BOUND), STAGE_IS(GIT_INTEGRATION), ROW_SUBJECT_IS(CANDIDATE_TRIPLE)) | GIT_OBJECT, DIFF_MANIFEST, PR_METADATA_SNAPSHOT | PASS | GATE_PASS |
| `GIT_INTEGRATION_GATE_FAIL_RECEIPT` | vibedev/orchestrator | REVIEW_GATE_PASS_RECEIPT + Integration Packet assembly + freeze + validation + PRE_DRAFT_GIT_INTEGRATOR_BINDING + integration-stage stop or rejection Evidence (`ARTIFACT_VALIDATION_RECEIPT` with state INCOMPLETE/REJECTED) | INTEGRATION_INPUT_FROZEN triple | `INTEGRATION_INPUT_FROZEN`, `CANDIDATE_TRIPLE` | `ARTIFACT_VALIDATION_RECEIPT`, `PACKET_ASSEMBLY_RECEIPT`, `PACKET_FREEZE_RECEIPT`, `PACKET_VALIDATION_RECEIPT`, `PRE_DRAFT_GIT_INTEGRATOR_BINDING_RECEIPT`, `REVIEW_GATE_PASS_RECEIPT`, `ROLE_CROSS_VERIFICATION_RECEIPT`| AND(CURRENT(REVIEW_GATE_PASS_RECEIPT), CURRENT(PACKET_ASSEMBLY_RECEIPT), CURRENT(PACKET_FREEZE_RECEIPT), CURRENT(PACKET_VALIDATION_RECEIPT), CURRENT(PRE_DRAFT_GIT_INTEGRATOR_BINDING_RECEIPT), STATE_CREATED(REVIEW_GATE_PASS_RECEIPT, GATE_PASS), STATE_CREATED(PACKET_FREEZE_RECEIPT, PACKET_FROZEN), STATE_CREATED(PACKET_VALIDATION_RECEIPT, PACKET_VALIDATED), OR(STATE_CREATED(ARTIFACT_VALIDATION_RECEIPT, ARTIFACT_INVALID), STATE_CREATED(ROLE_CROSS_VERIFICATION_RECEIPT, ROLE_CROSS_VERIFICATION_INCOMPLETE), STATE_CREATED(ROLE_CROSS_VERIFICATION_RECEIPT, ROLE_CROSS_VERIFICATION_REJECTED)), STAGE_IS(GIT_INTEGRATION), ROW_SUBJECT_IS(CANDIDATE_TRIPLE)) | GIT_OBJECT, DIFF_MANIFEST, PR_METADATA_SNAPSHOT | FAIL | GATE_FAIL |
| `DRAFT_PR_DELIVERY_RECEIPT` | git-integrator | GIT_INTEGRATION_GATE_PASS_RECEIPT + CANDIDATE_TRIPLE + PR | CANDIDATE_TRIPLE + PR triple | `CANDIDATE_TRIPLE`, `PR_TRIPLE` | `GIT_INTEGRATION_GATE_PASS_RECEIPT`, `PRE_DRAFT_GIT_INTEGRATOR_BINDING_RECEIPT` | AND(CURRENT(GIT_INTEGRATION_GATE_PASS_RECEIPT), CURRENT(PRE_DRAFT_GIT_INTEGRATOR_BINDING_RECEIPT), STATE_CREATED(GIT_INTEGRATION_GATE_PASS_RECEIPT, GATE_PASS), STATE_CREATED(PRE_DRAFT_GIT_INTEGRATOR_BINDING_RECEIPT, GIT_INTEGRATOR_PRE_DRAFT_BOUND)) | GIT_OBJECT, PR_METADATA_SNAPSHOT | DELIVERED / FAILED | DRAFT_DELIVERED / DRAFT_DELIVERY_FAILED |
| `POST_DRAFT_DRAFT_TO_READY_BINDING_RECEIPT` | git-integrator (per-stage, post-Draft re-authorization for Draft→Ready operation) | stage-specific post-Draft binding for Draft→Ready operation | `DRAFT_TO_READY_APPROVAL_PACKET` triple + git-integrator stage Activation Evidence | `DRAFT_TO_READY_APPROVAL_PACKET`, `GIT_INTEGRATOR_ACTIVATION_EVIDENCE_DRAFT_TO_READY` | `OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT`, `DRAFT_PR_DELIVERY_RECEIPT`, `ROLE_ACTIVATION_READINESS_RECEIPT` | AND(CURRENT(OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT), CURRENT(DRAFT_PR_DELIVERY_RECEIPT), CURRENT(ROLE_ACTIVATION_READINESS_RECEIPT), STATE_CREATED(OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT, OPERATOR_AUTHORIZED_DRAFT_TO_READY), STATE_CREATED(DRAFT_PR_DELIVERY_RECEIPT, DRAFT_DELIVERED), STATE_CREATED(ROLE_ACTIVATION_READINESS_RECEIPT, ROLE_ACTIVATION_READY), STAGE_IS(DRAFT_TO_READY)) | MODEL_INVOCATION_RECORD (stage-specific), GIT_OBJECT, OPERATOR_DECISION_RECORD | BOUND / UNBOUND | GIT_INTEGRATOR_DRAFT_TO_READY_BOUND / GIT_INTEGRATOR_DRAFT_TO_READY_UNBOUND |
| `READY_TRANSITION_RECEIPT` | vibedev/orchestrator | operator Draft→Ready authorization + DRAFT_PR_DELIVERY + DRAFT_TO_READY_APPROVAL_PACKET assembly + freeze + validation + POST_DRAFT_DRAFT_TO_READY_BINDING + git-integrator completion Evidence + cross-verification + STAGE_IS(DRAFT_TO_READY) (`BRANCH_DELETION_RECEIPT` is terminal post-BD cleanup) | PR triple | `DRAFT_TO_READY_APPROVAL_PACKET`, `PR_TRIPLE` | `OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT`, `DRAFT_PR_DELIVERY_RECEIPT`, `PACKET_ASSEMBLY_RECEIPT`, `PACKET_FREEZE_RECEIPT`, `PACKET_VALIDATION_RECEIPT`, `POST_DRAFT_DRAFT_TO_READY_BINDING_RECEIPT`, `ROLE_CROSS_VERIFICATION_RECEIPT` | AND(CURRENT(OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT), CURRENT(DRAFT_PR_DELIVERY_RECEIPT), CURRENT(PACKET_ASSEMBLY_RECEIPT), CURRENT(PACKET_FREEZE_RECEIPT), CURRENT(PACKET_VALIDATION_RECEIPT), CURRENT(POST_DRAFT_DRAFT_TO_READY_BINDING_RECEIPT), CURRENT(ROLE_CROSS_VERIFICATION_RECEIPT), STATE_CREATED(OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT, OPERATOR_AUTHORIZED_DRAFT_TO_READY), STATE_CREATED(DRAFT_PR_DELIVERY_RECEIPT, DRAFT_DELIVERED), STATE_CREATED(PACKET_FREEZE_RECEIPT, PACKET_FROZEN), STATE_CREATED(PACKET_VALIDATION_RECEIPT, PACKET_VALIDATED), STATE_CREATED(POST_DRAFT_DRAFT_TO_READY_BINDING_RECEIPT, GIT_INTEGRATOR_DRAFT_TO_READY_BOUND), STATE_CREATED(ROLE_CROSS_VERIFICATION_RECEIPT, ROLE_CROSS_VERIFIED), STAGE_IS(DRAFT_TO_READY), EVIDENCE_OF(GIT_INTEGRATOR_ACTIVATION_DRAFT_TO_READY, GIT_INTEGRATOR_ACTIVATION_EVIDENCE_DRAFT_TO_READY), ROW_SUBJECT_IS(PR_TRIPLE)) | PR_METADATA_SNAPSHOT, OPERATOR_DECISION_RECORD | READY / BLOCKED | PR_READY / PR_READY_BLOCKED |
| `POST_DRAFT_MERGE_BINDING_RECEIPT` | git-integrator (per-stage, post-Draft re-authorization for Merge operation) | stage-specific post-Draft binding for Merge operation | `MERGE_APPROVAL_PACKET` triple + git-integrator stage Activation Evidence | `MERGE_APPROVAL_PACKET`, `GIT_INTEGRATOR_ACTIVATION_EVIDENCE_MERGE` | `OPERATOR_MERGE_AUTHORIZATION_RECEIPT`, `READY_TRANSITION_RECEIPT`, `ROLE_ACTIVATION_READINESS_RECEIPT` | AND(CURRENT(OPERATOR_MERGE_AUTHORIZATION_RECEIPT), CURRENT(READY_TRANSITION_RECEIPT), CURRENT(ROLE_ACTIVATION_READINESS_RECEIPT), STATE_CREATED(OPERATOR_MERGE_AUTHORIZATION_RECEIPT, OPERATOR_AUTHORIZED_MERGE), STATE_CREATED(READY_TRANSITION_RECEIPT, PR_READY), STATE_CREATED(ROLE_ACTIVATION_READINESS_RECEIPT, ROLE_ACTIVATION_READY), STAGE_IS(MERGE)) | MODEL_INVOCATION_RECORD (stage-specific), GIT_OBJECT, OPERATOR_DECISION_RECORD | BOUND / UNBOUND | GIT_INTEGRATOR_MERGE_BOUND / GIT_INTEGRATOR_MERGE_UNBOUND |
| `MERGE_DELIVERY_RECEIPT` | git-integrator | operator Merge authorization + READY_TRANSITION_RECEIPT + MERGE_APPROVAL_PACKET assembly + freeze + validation + POST_DRAFT_MERGE_BINDING + git-integrator completion Evidence + STAGE_IS(MERGE) | PR triple | `MERGE_APPROVAL_PACKET`, `PR_TRIPLE` | `OPERATOR_MERGE_AUTHORIZATION_RECEIPT`, `READY_TRANSITION_RECEIPT`, `PACKET_ASSEMBLY_RECEIPT`, `PACKET_FREEZE_RECEIPT`, `PACKET_VALIDATION_RECEIPT`, `POST_DRAFT_MERGE_BINDING_RECEIPT`, `ROLE_CROSS_VERIFICATION_RECEIPT` | AND(CURRENT(OPERATOR_MERGE_AUTHORIZATION_RECEIPT), CURRENT(READY_TRANSITION_RECEIPT), CURRENT(PACKET_ASSEMBLY_RECEIPT), CURRENT(PACKET_FREEZE_RECEIPT), CURRENT(PACKET_VALIDATION_RECEIPT), CURRENT(POST_DRAFT_MERGE_BINDING_RECEIPT), CURRENT(ROLE_CROSS_VERIFICATION_RECEIPT), STATE_CREATED(OPERATOR_MERGE_AUTHORIZATION_RECEIPT, OPERATOR_AUTHORIZED_MERGE), STATE_CREATED(READY_TRANSITION_RECEIPT, PR_READY), STATE_CREATED(PACKET_FREEZE_RECEIPT, PACKET_FROZEN), STATE_CREATED(PACKET_VALIDATION_RECEIPT, PACKET_VALIDATED), STATE_CREATED(POST_DRAFT_MERGE_BINDING_RECEIPT, GIT_INTEGRATOR_MERGE_BOUND), STATE_CREATED(ROLE_CROSS_VERIFICATION_RECEIPT, ROLE_CROSS_VERIFIED), STAGE_IS(MERGE), EVIDENCE_OF(GIT_INTEGRATOR_ACTIVATION_MERGE, GIT_INTEGRATOR_ACTIVATION_EVIDENCE_MERGE), ROW_SUBJECT_IS(PR_TRIPLE)) | GIT_OBJECT, PR_METADATA_SNAPSHOT | MERGED / FAILED | PR_MERGED / MERGE_FAILED |
| `POST_DRAFT_BRANCH_DELETION_BINDING_RECEIPT` | git-integrator (per-stage, post-Draft re-authorization for Branch Deletion operation) | stage-specific post-Draft binding for Branch Deletion operation | `BRANCH_DELETION_APPROVAL_PACKET` triple + git-integrator stage Activation Evidence | `BRANCH_DELETION_APPROVAL_PACKET`, `GIT_INTEGRATOR_ACTIVATION_EVIDENCE_BD` | `OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT`, `MERGE_DELIVERY_RECEIPT`, `ROLE_ACTIVATION_READINESS_RECEIPT` | AND(CURRENT(OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT), CURRENT(MERGE_DELIVERY_RECEIPT), CURRENT(ROLE_ACTIVATION_READINESS_RECEIPT), STATE_CREATED(OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT, OPERATOR_AUTHORIZED_BRANCH_DELETION), STATE_CREATED(MERGE_DELIVERY_RECEIPT, PR_MERGED), STATE_CREATED(ROLE_ACTIVATION_READINESS_RECEIPT, ROLE_ACTIVATION_READY), STAGE_IS(BRANCH_DELETION)) | MODEL_INVOCATION_RECORD (stage-specific), GIT_OBJECT, OPERATOR_DECISION_RECORD | BOUND / UNBOUND | GIT_INTEGRATOR_BRANCH_DELETION_BOUND / GIT_INTEGRATOR_BRANCH_DELETION_UNBOUND |
| `BRANCH_DELETION_RECEIPT` | git-integrator | operator Branch Deletion authorization + MERGE_DELIVERY + BRANCH_DELETION_APPROVAL_PACKET assembly + freeze + validation + POST_DRAFT_BRANCH_DELETION_BINDING + git-integrator completion Evidence + STAGE_IS(BRANCH_DELETION) | branch triple | `BRANCH_DELETION_APPROVAL_PACKET`, `BRANCH_TRIPLE` | `OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT`, `MERGE_DELIVERY_RECEIPT`, `PACKET_ASSEMBLY_RECEIPT`, `PACKET_FREEZE_RECEIPT`, `PACKET_VALIDATION_RECEIPT`, `POST_DRAFT_BRANCH_DELETION_BINDING_RECEIPT`, `ROLE_CROSS_VERIFICATION_RECEIPT` | AND(CURRENT(OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT), CURRENT(MERGE_DELIVERY_RECEIPT), CURRENT(PACKET_ASSEMBLY_RECEIPT), CURRENT(PACKET_FREEZE_RECEIPT), CURRENT(PACKET_VALIDATION_RECEIPT), CURRENT(POST_DRAFT_BRANCH_DELETION_BINDING_RECEIPT), CURRENT(ROLE_CROSS_VERIFICATION_RECEIPT), STATE_CREATED(OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT, OPERATOR_AUTHORIZED_BRANCH_DELETION), STATE_CREATED(MERGE_DELIVERY_RECEIPT, PR_MERGED), STATE_CREATED(PACKET_FREEZE_RECEIPT, PACKET_FROZEN), STATE_CREATED(PACKET_VALIDATION_RECEIPT, PACKET_VALIDATED), STATE_CREATED(POST_DRAFT_BRANCH_DELETION_BINDING_RECEIPT, GIT_INTEGRATOR_BRANCH_DELETION_BOUND), STATE_CREATED(ROLE_CROSS_VERIFICATION_RECEIPT, ROLE_CROSS_VERIFIED), STAGE_IS(BRANCH_DELETION), EVIDENCE_OF(GIT_INTEGRATOR_ACTIVATION_BD, GIT_INTEGRATOR_ACTIVATION_EVIDENCE_BD), ROW_SUBJECT_IS(BRANCH_TRIPLE)) | GIT_OBJECT, PR_METADATA_SNAPSHOT | DELETED / FAILED | BRANCH_DELETED / BRANCH_DELETION_FAILED |
| `CONSULTATION_ENDPOINT_RECEIPT` | vibedev/orchestrator | consultation scope + Work Order + Consultation Work Order (no role assignment) | CONSULTATION_DELIVERABLE triple | `CONSULTATION_SOURCE_PACKET`, `WORK_ORDER_DECLARATION` | `GLOBAL_READINESS_RECEIPT`, `OPERATOR_WORK_ORDER_APPROVAL_RECEIPT` | AND(CURRENT(GLOBAL_READINESS_RECEIPT), CURRENT(OPERATOR_WORK_ORDER_APPROVAL_RECEIPT), STATE_CREATED(GLOBAL_READINESS_RECEIPT, GLOBAL_READINESS_PASS), STATE_CREATED(OPERATOR_WORK_ORDER_APPROVAL_RECEIPT, OPERATOR_APPROVED_WORK_ORDER), MODE_IS(CONSULTATION_ONLY)) | MODEL_INVOCATION_RECORD, OPERATOR_DECISION_RECORD | DELIVERED / FAILED | CONSULTATION_DELIVERED / CONSULTATION_FAILED |
| `PUBLIC_PROJECTION_SAFETY_CHECK_RECEIPT` | vibedev/orchestrator (public-safe verification function) | PUBLIC_EVIDENCE_PROJECTION_ARTIFACT + source Evidence | PUBLIC_EVIDENCE_PROJECTION_ARTIFACT triple | `SOURCE_EVIDENCE_OBJECTS` | `ARTIFACT_VALIDATION_RECEIPT` | AND(CURRENT(ARTIFACT_VALIDATION_RECEIPT), STATE_CREATED(ARTIFACT_VALIDATION_RECEIPT, ARTIFACT_VALIDATED)) | FILE_SNAPSHOT, OPERATOR_DECISION_RECORD | SAFE / UNSAFE | PROJECTION_SAFE / PROJECTION_UNSAFE |
| `STOP_RECEIPT` | vibedev/orchestrator (only) | STOP_REPORT Artifact + Evidence; or hard STOP signal; or operator instruction (`TEST_GATE_FAIL_RECEIPT`, `REVIEW_GATE_FAIL_RECEIPT`, `GIT_INTEGRATION_GATE_FAIL_RECEIPT` trigger STOP) | subject STOP reason triple | `STOP_REPORT` | `ARTIFACT_VALIDATION_RECEIPT` | AND(CURRENT(ARTIFACT_VALIDATION_RECEIPT)) | MODEL_INVOCATION_RECORD, OPERATOR_DECISION_RECORD, STOP signal catalog entry | STOPPED | TASK_STOPPED / WORKFLOW_STOPPED |
| `INVALIDATION_RECEIPT` | vibedev/orchestrator | Evidence of invalidation condition | single Artifact, Evidence, Packet, or Receipt triple | `SUBJECT_TRIPLE` | `ARTIFACT_VALIDATION_RECEIPT` | AND(CURRENT(ARTIFACT_VALIDATION_RECEIPT), STATE_CREATED(ARTIFACT_VALIDATION_RECEIPT, ARTIFACT_VALIDATED)) | COMMAND_RESULT, MODEL_INVOCATION_RECORD, OPERATOR_DECISION_RECORD | INVALIDATED | SUBJECT_INVALIDATED |
| `SUPERSESSION_RECEIPT` | vibedev/orchestrator | Evidence of supersession + superseding-object Receipt triple (canonical object reference; uses `STATE_CREATED(SUPERSESSION_RECEIPT, SUPERSEDED)` downstream) | single Artifact, Evidence, Packet, or Receipt triple | `SUPERSEDING_OBJECT_TRIPLE` | `ARTIFACT_VALIDATION_RECEIPT` | AND(CURRENT(ARTIFACT_VALIDATION_RECEIPT), STATE_CREATED(ARTIFACT_VALIDATION_RECEIPT, ARTIFACT_VALIDATED)) | FILE_SNAPSHOT, GIT_OBJECT | SUPERSEDED | OBJECT_SUPERSEDED |
| `OPERATOR_REVOCATION_RECEIPT` | operator (only) | operator authority | single operator-authorisation Receipt triple | `AUTHORISATION_RECEIPT_TRIPLE` |`OPERATOR_APPROVED_VERSION_PREPARATION_RECEIPT`, `OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT`, `OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT`, `OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT`, `OPERATOR_IMPLEMENTATION_PLAN_APPROVAL_RECEIPT`, `OPERATOR_INTAKE_SCOPE_APPROVAL_RECEIPT`, `OPERATOR_MERGE_AUTHORIZATION_RECEIPT`, `OPERATOR_SUBMODE_SELECTION_RECEIPT`, `OPERATOR_WORK_ORDER_APPROVAL_RECEIPT``| AND(EXACTLY_ONE_OF(CURRENT(OPERATOR_INTAKE_SCOPE_APPROVAL_RECEIPT, AUTHORISATION_RECEIPT_TRIPLE), CURRENT(OPERATOR_SUBMODE_SELECTION_RECEIPT, AUTHORISATION_RECEIPT_TRIPLE), CURRENT(OPERATOR_WORK_ORDER_APPROVAL_RECEIPT, AUTHORISATION_RECEIPT_TRIPLE), CURRENT(OPERATOR_IMPLEMENTATION_PLAN_APPROVAL_RECEIPT, AUTHORISATION_RECEIPT_TRIPLE), CURRENT(OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT, AUTHORISATION_RECEIPT_TRIPLE), CURRENT(OPERATOR_MERGE_AUTHORIZATION_RECEIPT, AUTHORISATION_RECEIPT_TRIPLE), CURRENT(OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT, AUTHORISATION_RECEIPT_TRIPLE), CURRENT(OPERATOR_APPROVED_VERSION_PREPARATION_RECEIPT, AUTHORISATION_RECEIPT_TRIPLE), CURRENT(OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT, AUTHORISATION_RECEIPT_TRIPLE)), ROW_SUBJECT_IS(AUTHORISATION_RECEIPT_TRIPLE)) | OPERATOR_DECISION_RECORD | REVOKED | AUTHORISATION_REVOKED |
| `OPERATOR_INTAKE_SCOPE_APPROVAL_RECEIPT` | operator (only) | operator authority (may be followed by `OPERATOR_REVOCATION_RECEIPT`) | intake scope packet triple | `INTAKE_SCOPE_PACKET` | ∅ | AND(EVIDENCE_OF(OPERATOR_DECISION, INTAKE_SCOPE_PACKET), ROW_SUBJECT_IS(INTAKE_SCOPE_PACKET)) | OPERATOR_DECISION_RECORD | APPROVED | OPERATOR_APPROVED_INTAKE_SCOPE |
| `OPERATOR_SUBMODE_SELECTION_RECEIPT` | operator (only) | operator authority | `SUBMODE_DECLARATION` triple | `SUBMODE_DECLARATION` | `OPERATOR_INTAKE_SCOPE_APPROVAL_RECEIPT` | AND(CURRENT(OPERATOR_INTAKE_SCOPE_APPROVAL_RECEIPT)) | OPERATOR_DECISION_RECORD | SELECTED | OPERATOR_SELECTED_SUBMODE |
| `OPERATOR_ROLE_NODE_MODEL_ASSIGNMENT_APPROVAL_RECEIPT` | operator (only) | operator authority | assignment baseline packet triple | `ROLE_NODE_MODEL_ASSIGNMENT_BASELINE_PACKET` | `OPERATOR_SUBMODE_SELECTION_RECEIPT` | AND(CURRENT(OPERATOR_SUBMODE_SELECTION_RECEIPT)) | OPERATOR_DECISION_RECORD | APPROVED | OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE |
| `OPERATOR_WORK_ORDER_APPROVAL_RECEIPT` | operator (only) | operator authority | Work Order triple | `WORK_ORDER_DECLARATION` | `OPERATOR_INTAKE_SCOPE_APPROVAL_RECEIPT`, `OPERATOR_SUBMODE_SELECTION_RECEIPT` | AND(CURRENT(OPERATOR_INTAKE_SCOPE_APPROVAL_RECEIPT), CURRENT(OPERATOR_SUBMODE_SELECTION_RECEIPT)) | OPERATOR_DECISION_RECORD | APPROVED | OPERATOR_APPROVED_WORK_ORDER |
| `OPERATOR_IMPLEMENTATION_PLAN_APPROVAL_RECEIPT` | operator (only) | operator authority | implementation plan approval packet triple | `IMPLEMENTATION_PLAN_APPROVAL_PACKET` | `OPERATOR_WORK_ORDER_APPROVAL_RECEIPT` | AND(CURRENT(OPERATOR_WORK_ORDER_APPROVAL_RECEIPT)) | OPERATOR_DECISION_RECORD | APPROVED | OPERATOR_APPROVED_IMPLEMENTATION_PLAN |
| `OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT` | operator (only, FULL/LIGHTWEIGHT only — not Consultation) | operator authority | `DRAFT_TO_READY_APPROVAL_PACKET` triple | `DRAFT_TO_READY_APPROVAL_PACKET` | `OPERATOR_WORK_ORDER_APPROVAL_RECEIPT`, `PACKET_FREEZE_RECEIPT`, `PACKET_VALIDATION_RECEIPT`, `GIT_INTEGRATION_GATE_PASS_RECEIPT`, `OPERATOR_IMPLEMENTATION_PLAN_APPROVAL_RECEIPT` | NOT_APPLICABLE_IF(MODE_IS(CONSULTATION_ONLY), AND(CURRENT(OPERATOR_WORK_ORDER_APPROVAL_RECEIPT), CURRENT(PACKET_FREEZE_RECEIPT), CURRENT(PACKET_VALIDATION_RECEIPT), CURRENT(GIT_INTEGRATION_GATE_PASS_RECEIPT), STATE_CREATED(OPERATOR_WORK_ORDER_APPROVAL_RECEIPT, OPERATOR_APPROVED_WORK_ORDER), STATE_CREATED(GIT_INTEGRATION_GATE_PASS_RECEIPT, GATE_PASS), OR(AND(MODE_IS(FULL), CURRENT(OPERATOR_IMPLEMENTATION_PLAN_APPROVAL_RECEIPT)), AND(MODE_IS(LIGHTWEIGHT), PLAN_CHECKPOINT_IS(ENABLED), CURRENT(OPERATOR_IMPLEMENTATION_PLAN_APPROVAL_RECEIPT)), AND(MODE_IS(LIGHTWEIGHT), PLAN_CHECKPOINT_IS(DISABLED)), AND(MODE_IS(LIGHTWEIGHT), DIRECT_TO_IMPLEMENTER_IS(TRUE), NOT(ROLE_INSTANTIATED(PLANNER)))))) | OPERATOR_DECISION_RECORD | AUTHORIZED | OPERATOR_AUTHORIZED_DRAFT_TO_READY |
| `OPERATOR_MERGE_AUTHORIZATION_RECEIPT` | operator (only) | operator authority | `MERGE_APPROVAL_PACKET` triple | `MERGE_APPROVAL_PACKET` | `OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT`, `PACKET_FREEZE_RECEIPT`, `PACKET_VALIDATION_RECEIPT` | AND(CURRENT(OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT), CURRENT(PACKET_FREEZE_RECEIPT), CURRENT(PACKET_VALIDATION_RECEIPT), STATE_CREATED(OPERATOR_DRAFT_TO_READY_AUTHORIZATION_RECEIPT, OPERATOR_AUTHORIZED_DRAFT_TO_READY)) | OPERATOR_DECISION_RECORD | AUTHORIZED | OPERATOR_AUTHORIZED_MERGE |
| `OPERATOR_BRANCH_DELETION_AUTHORIZATION_RECEIPT` | operator (only) | operator authority | `BRANCH_DELETION_APPROVAL_PACKET` triple | `BRANCH_DELETION_APPROVAL_PACKET` | `OPERATOR_MERGE_AUTHORIZATION_RECEIPT`, `PACKET_FREEZE_RECEIPT`, `PACKET_VALIDATION_RECEIPT` | AND(CURRENT(OPERATOR_MERGE_AUTHORIZATION_RECEIPT), CURRENT(PACKET_FREEZE_RECEIPT), CURRENT(PACKET_VALIDATION_RECEIPT), STATE_CREATED(OPERATOR_MERGE_AUTHORIZATION_RECEIPT, OPERATOR_AUTHORIZED_MERGE)) | OPERATOR_DECISION_RECORD | AUTHORIZED | OPERATOR_AUTHORIZED_BRANCH_DELETION |
| `OPERATOR_APPROVED_VERSION_PREPARATION_RECEIPT` | operator (only) | operator authority (§3.8 V3) | VERSION_PREPARATION_PACKET triple | `VERSION_PREPARATION_PACKET` | `PACKET_VALIDATION_RECEIPT` | AND(CURRENT(PACKET_VALIDATION_RECEIPT), STATE_CREATED(PACKET_VALIDATION_RECEIPT, PACKET_VALIDATED)) | OPERATOR_DECISION_RECORD, FILE_SNAPSHOT, GIT_OBJECT | APPROVED | VERSION_PREPARATION_APPROVED |
| `VERSION_PRE_EXECUTION_CHECKPOINT_REVIEW_RECEIPT` | operator (only) | operator checkpoint decision (§3.8 V4) | VERSION_PRE_EXECUTION_CHECKPOINT_PACKET triple | `VERSION_PRE_EXECUTION_CHECKPOINT_PACKET` | `OPERATOR_APPROVED_VERSION_PREPARATION_RECEIPT` | AND(CURRENT(OPERATOR_APPROVED_VERSION_PREPARATION_RECEIPT), STATE_CREATED(OPERATOR_APPROVED_VERSION_PREPARATION_RECEIPT, VERSION_PREPARATION_APPROVED)) | OPERATOR_DECISION_RECORD, FILE_SNAPSHOT, GIT_OBJECT | REVIEWED / BLOCKED | VERSION_CHECKPOINT_REVIEWED / VERSION_CHECKPOINT_BLOCKED |
| `OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT` | operator (only) | operator authority (§3.8 V5) | VERSION_EXECUTION_AUTHORIZATION_PACKET triple | `VERSION_EXECUTION_AUTHORIZATION_PACKET` | `VERSION_PRE_EXECUTION_CHECKPOINT_REVIEW_RECEIPT` | AND(CURRENT(VERSION_PRE_EXECUTION_CHECKPOINT_REVIEW_RECEIPT), STATE_CREATED(VERSION_PRE_EXECUTION_CHECKPOINT_REVIEW_RECEIPT, VERSION_CHECKPOINT_REVIEWED)) | OPERATOR_DECISION_RECORD | AUTHORIZED | VERSION_EXECUTION_AUTHORIZED |
| `VERSION_QUALIFICATION_PASS_RECEIPT` | vibedev/orchestrator | V5 operator authorization + V6 execution Evidence (§3.8 V7) | VERSION_QUALIFICATION_PACKET triple | `VERSION_QUALIFICATION_PACKET` | `OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT` | AND(CURRENT(OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT), STATE_CREATED(OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT, VERSION_EXECUTION_AUTHORIZED)) | FILE_SNAPSHOT, GIT_OBJECT, MODEL_INVOCATION_RECORD, TEST_RESULT | PASS | VERSION_QUALIFICATION_PASS |
| `VERSION_QUALIFICATION_FAIL_RECEIPT` | vibedev/orchestrator | V5 operator authorization + V6 execution Evidence (§3.8 V7) | VERSION_QUALIFICATION_PACKET triple | `VERSION_QUALIFICATION_PACKET` | `OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT` | AND(CURRENT(OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT), STATE_CREATED(OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT, VERSION_EXECUTION_AUTHORIZED)) | FILE_SNAPSHOT, GIT_OBJECT, MODEL_INVOCATION_RECORD, TEST_RESULT | FAIL | VERSION_QUALIFICATION_FAIL |
| `VERSION_GOVERNANCE_CLOSEOUT_RECEIPT` | vibedev/orchestrator | V0–V7 explicit list + lifecycle management (`STOP_RECEIPT`, `INVALIDATION_RECEIPT`, `SUPERSESSION_RECEIPT`, `CONSULTATION_ENDPOINT_RECEIPT`, `PACKET_CONSUMPTION_RECEIPT`, `PUBLIC_PROJECTION_SAFETY_CHECK_RECEIPT`, `VERSION_GOVERNANCE_CLOSEOUT_RECEIPT`) | VERSION_CLOSEOUT_REPORT triple | `VERSION_CLOSEOUT_REPORT`, `VERSION_GOVERNANCE_SCOPE_PACKET`, `VERSION_INVENTORY_ARTIFACT`, `VERSION_CHANGE_PROPOSAL_ARTIFACT`, `VERSION_PREPARATION_PACKET`, `VERSION_PRE_EXECUTION_CHECKPOINT_PACKET`, `VERSION_EXECUTION_AUTHORIZATION_PACKET`, `VERSION_EXECUTION_REPORT`, `VERSION_EXECUTION_EVIDENCE_PACKET`, `VERSION_QUALIFICATION_PACKET` | `OPERATOR_APPROVED_VERSION_PREPARATION_RECEIPT`, `VERSION_PRE_EXECUTION_CHECKPOINT_REVIEW_RECEIPT`, `OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT`, `VERSION_QUALIFICATION_PASS_RECEIPT`, `VERSION_QUALIFICATION_FAIL_RECEIPT`, `PACKET_VALIDATION_RECEIPT`, `ARTIFACT_VALIDATION_RECEIPT, `STOP_RECEIPT` | AND(SAME_OPERATION(VERSION_GOVERNANCE_SCOPE_PACKET, VERSION_INVENTORY_ARTIFACT, VERSION_CHANGE_PROPOSAL_ARTIFACT, VERSION_PREPARATION_PACKET, VERSION_PRE_EXECUTION_CHECKPOINT_PACKET, VERSION_EXECUTION_AUTHORIZATION_PACKET, VERSION_EXECUTION_REPORT, VERSION_EXECUTION_EVIDENCE_PACKET, VERSION_QUALIFICATION_PACKET, VERSION_CLOSEOUT_REPORT), CURRENT(PACKET_VALIDATION_RECEIPT, VERSION_GOVERNANCE_SCOPE_PACKET), CURRENT(ARTIFACT_VALIDATION_RECEIPT, VERSION_INVENTORY_ARTIFACT), CURRENT(ARTIFACT_VALIDATION_RECEIPT, VERSION_CHANGE_PROPOSAL_ARTIFACT), CURRENT(OPERATOR_APPROVED_VERSION_PREPARATION_RECEIPT), CURRENT(VERSION_PRE_EXECUTION_CHECKPOINT_REVIEW_RECEIPT), EXACTLY_ONE_OF(AND(STATE_CREATED(VERSION_PRE_EXECUTION_CHECKPOINT_REVIEW_RECEIPT, VERSION_CHECKPOINT_REVIEWED), CURRENT(OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT), STATE_CREATED(OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT, VERSION_EXECUTION_AUTHORIZED), STATE_CREATED(VERSION_QUALIFICATION_PASS_RECEIPT, VERSION_QUALIFICATION_PASS)), AND(STATE_CREATED(VERSION_PRE_EXECUTION_CHECKPOINT_REVIEW_RECEIPT, VERSION_CHECKPOINT_REVIEWED), CURRENT(OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT), STATE_CREATED(OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT, VERSION_EXECUTION_AUTHORIZED), STATE_CREATED(VERSION_QUALIFICATION_FAIL_RECEIPT, VERSION_QUALIFICATION_FAIL), CURRENT(STOP_RECEIPT)), AND(STATE_CREATED(VERSION_PRE_EXECUTION_CHECKPOINT_REVIEW_RECEIPT, VERSION_CHECKPOINT_BLOCKED)))) | all V0–V7 Evidence classes | CLOSED / CLOSED_AFTER_FAILURE_STOP / CLOSED_BLOCKED | VERSION_GOVERNANCE_CLOSED_PASS / VERSION_GOVERNANCE_CLOSED_AFTER_FAILURE_STOP / VERSION_GOVERNANCE_CLOSED_BLOCKED |

A Receipt is invalid if the issuer lacks authority, or the subject / prerequisite / evidence refs do not match (triggers `RECEIPT_ISSUER_UNAUTHORIZED`, `RECEIPT_SUBJECT_BINDING_MISMATCH`, `RECEIPT_PREREQUISITE_MISSING`, or `RECEIPT_EVIDENCE_INSUFFICIENT` as applicable). A duplicate receipt type in the registry triggers `RECEIPT_REGISTRY_DUPLICATE_TYPE → STOP`. A receipt type missing required registry fields triggers `RECEIPT_REGISTRY_FIELD_INCOMPLETE → STOP`. Conflating a `state_created` business workflow state with a receipt type identifier triggers `RECEIPT_TYPE_AND_STATE_CREATED_CONFLATED → STOP`.


#### §10.3.11 Lineage and Invalidation Propagation

All Artifacts, Evidence, Packets, and Receipts must form a verifiable DAG:

`Evidence → Claim / Artifact → Validation Receipt → Packet → Gate Receipt → downstream Packet → Delivery Receipt`

Cycles are forbidden. A detected cycle triggers `OBJECT_LINEAGE_CYCLE_DETECTED → STOP`.

Invalidation must propagate downstream via append-only Receipts (in-place field mutation is forbidden):

- Evidence invalidated → issue `INVALIDATION_RECEIPT`; dependent Claims / Artifacts have their effective status computed as `REVALIDATION_REQUIRED`
- Artifact invalidated → issue `INVALIDATION_RECEIPT`; containing Packet's effective status computed as `INVALIDATED`
- Packet invalidated → issue `INVALIDATION_RECEIPT`; dependent Receipts' effective status computed as `STALE`
- Receipt stale → downstream Gates and Packets have their effective status computed as invalidated

A CANDIDATE_TRIPLE digest change must invalidate all tester, reviewer, Gate, and Integration objects that reference the prior CANDIDATE_TRIPLE digest. A PR head or body change must make Ready / Merge approval Packets and their authorisation Receipts stale. Old evidence must be retained but must not contribute to a current PASS. All invalidation, staling, supersession, and revocation are expressed via independent append-only Receipts; no lifecycle field is mutated in place on the original object.

Packet lifecycle states (at creation): `ASSEMBLED` (initial immutable state after assembly). Effective states computed from Receipt chain: `FROZEN` (via `PACKET_FREEZE_RECEIPT`), `VALIDATED` (via `PACKET_VALIDATION_RECEIPT`), `CONSUMED` (via `PACKET_CONSUMPTION_RECEIPT`), `INVALIDATED`, `SUPERSEDED`. The Packet body records only `lifecycle_state_at_creation=ASSEMBLED`; subsequent effective states are derived from external Receipts, not from in-place Packet field mutation.

Artifact lifecycle states (at creation): `VALID`. Effective states: `INVALIDATED`, `SUPERSEDED`, `REVALIDATION_REQUIRED` — all computed from the append-only Receipt chain, not from in-place field mutation.

#### §10.3.12 Mode Applicability

**FULL_9_ROLE_VIBECODING**: the full schema applies.

**LIGHTWEIGHT_OPERATION**: only operator-approved roles and Gates are instantiated. A Work Order approval, Global Readiness, Activation, role artifacts / reports, independent verification Gate, Integration Packet, and Draft delivery receipt are still required.

**VIBECODING_CONSULTATION_ONLY**: must not fabricate CANDIDATE_TRIPLE, Gate, or Git objects. Consultation-specific work product and endpoint objects are limited to:

- `CONSULTATION_SOURCE_PACKET`
- `CONSULTATION_DELIVERABLE`
- `CONSULTATION_REPORT`
- `CONSULTATION_ENDPOINT_RECEIPT`

The following common governance objects remain **permitted and required as applicable**:

- Common operator approval Receipts (Intake, sub-mode, Work Order)
- `GLOBAL_READINESS_RECEIPT`
- Evidence records (including formal orchestrator model invocation Evidence)
- `PUBLIC_EVIDENCE_PROJECTION_ARTIFACT`
- `INVALIDATION_RECEIPT` / `SUPERSESSION_RECEIPT`
- `STOP_RECEIPT`

The following are **forbidden** in Consultation mode: non-orchestrator role assignment / Activation, CANDIDATE_TRIPLE objects, test Gate objects, review Gate objects, Integration Packet, Git delivery objects, and Post-Draft objects.

All Consultation objects must still carry `id + version + digest`, source / evidence / invocation bindings.

#### §10.3.13 Public Projection

Internal governance objects must not be directly published in full. `PUBLIC_EVIDENCE_PROJECTION` is a **derived Artifact** (object_type = `PUBLIC_EVIDENCE_PROJECTION_ARTIFACT`) and must carry the full common object envelope (§10.3.2), including `object_id`, `object_version`, and `canonical_digest`. The existing `projection_id` is a mandatory alias of `object_id`; `projection_digest` is a mandatory alias of `canonical_digest`. A `PUBLIC_EVIDENCE_PROJECTION` must contain:

- `source_refs` — `id + version + digest` triples of source Evidence records
- `allowed_fields` / `omitted_fields`
- `public_safe_check_required` — boolean flag; the `PUBLIC_PROJECTION_SAFETY_CHECK_RECEIPT` is an external Receipt that references this Projection's `id + version + digest` triple and must be `CURRENT` before publication; it must not be embedded in the Projection canonical body

PR bodies, commit messages, and public comments may reference only `PUBLIC_EVIDENCE_PROJECTION_ARTIFACT` objects. The following must never appear in a public projection: credential values, private host / IP / user / path, internal prompts, raw private logs, or secret-derived fingerprints. Redaction must not change the technical PASS / FAIL fact.

#### §10.3.14 Version Governance Gate Object Bindings

The existing §3.8 `HERMES_OPENCODE_VERSION_GOVERNANCE_GATE` (V0–V8) is the sole canonical version governance Gate. It is not a VibeCoding role, does not enter Work Order mode stages, and is not a tenth role. The following objects bind to its stages:

| Stage | Object / Receipt |
|---|---|
| V0 — Scope | `VERSION_GOVERNANCE_SCOPE_PACKET` |
| V1 — Inventory | `VERSION_INVENTORY_ARTIFACT` |
| V2 — Proposal | `VERSION_CHANGE_PROPOSAL_ARTIFACT` |
| V3 — Preparation Approval | `VERSION_PREPARATION_PACKET` + `OPERATOR_APPROVED_VERSION_PREPARATION_RECEIPT` |
| V4 — Pre-Execution Checkpoint | `VERSION_PRE_EXECUTION_CHECKPOINT_PACKET` (binding scope/inventory/proposal/preparation evidence, target version/action/node/profile, backup/rollback point, qualification plan, V3 Receipt) + `VERSION_PRE_EXECUTION_CHECKPOINT_REVIEW_RECEIPT` (operator review record; must not substitute for V5) |
| V5 — Second Confirmation | `VERSION_EXECUTION_AUTHORIZATION_PACKET` (frozen) + `OPERATOR_AUTHORIZED_VERSION_EXECUTION_RECEIPT` |
| V6 — Exact-Scope Execution | Execution reads V5 frozen Packet only; actual commands/install/migration/restart/switch results and side effects → independent Evidence + `VERSION_EXECUTION_REPORT` / `VERSION_EXECUTION_EVIDENCE_PACKET` (must not write back into V5 Packet) |
| V7 — Qualification | `VERSION_QUALIFICATION_PACKET` + `VERSION_QUALIFICATION_PASS_RECEIPT` / `VERSION_QUALIFICATION_FAIL_RECEIPT` |
| V8 — Closeout | `VERSION_CLOSEOUT_REPORT` + `VERSION_GOVERNANCE_CLOSEOUT_RECEIPT` |

V3 preparation approval must not authorise real installation. V4 checkpoint Packet must be reviewed by operator; the review Receipt must not substitute for V5 authorisation. V5 second confirmation is the point at which the exact version, action, node / profile, backup / rollback point, and qualification plan are authorised. V6 execution must read the V5 frozen Packet only; execution Evidence must be recorded independently and must not write back into the V5 Packet. Any change to target version, component, node / profile, action, backup / rollback point, or qualification plan makes the V5 authorisation stale. Any V4/V5/V6 object conflation triggers `VERSION_GOVERNANCE_STAGE_OBJECT_CONFLATION → STOP`; V7 credential Evidence limited to identity/class/binding, no secret value observation. V7 must bind: binary / checksum; config / capability / provider / model / CMP / wrapper / bounded-call / Gate Evidence; credential identity, approved source class, availability and binding-verification Evidence (with `secret_value_observed = false`); rollback Evidence; drift Evidence. Failure at V7 triggers immediate STOP; no automatic version substitution, scope expansion, or rollback unless the operator has pre-approved an atomic rollback plan.

#### §10.3.15 Version Gate Trigger Boundary

§3.8 applies to Hermes / OpenCode and their direct service, adapter, config migration, restart, or switch. Ordinary business dependency upgrades proceed under `VIBECODING_MODE`. If a change affects the control plane, Hermes / OpenCode runtime, wrapper / provider compatibility, or a node-wide service, it must be split into §3.8. If a VERSION change and a CMP change occur simultaneously, they must be split into independent operations with independent authorisations; Receipts for one must not substitute for the other.


#### §10.3.16 Efficiency ≠ Skip

- No skipping roles / gates / evidence required by the operator-selected execution mode for efficiency. In `FULL_9_ROLE_VIBECODING`, the complete 9-role roster and dual-tester / dual-reviewer independence **must** be maintained. In `LIGHTWEIGHT_OPERATION`, only the operator-approved actual role set is executed.
- Dual-tester / dual-reviewer independence applies **only** in `FULL_9_ROLE_VIBECODING` or when operator explicitly selects dual tester / dual reviewer. It **must not** be implied for `LIGHTWEIGHT_OPERATION` or dedicated governance gates.
- High-risk authorisation boundaries **must not** be merged or hidden.
- Any proposal to bypass §9 checkpoints or §7 STOP in the name of efficiency is itself drift.

### §10.4 Historical Preservation

Historical PRs / reports / receipts / logs are preserved without tampering; amendments go through new PRs / documents. `PRE_V2_HISTORICAL_EVIDENCE` keeps its preservation property but cannot serve as V2-compliant E2E PASS.

### §10.5 Signing and Effect

V2 takes effect **only after** explicit operator acceptance. `vibedev` **must not** self-sign, self-declare, or self-upgrade.

### §10.6 Post-Effect PR

- V2 enters force **only** when the operator explicitly accepts it in chat (e.g. "ACCEPT V2" or equivalent natural language). vibedev **must not** self-declare V2 as accepted, effective, or adopted.
- The accepted body is applied to the existing contract file through an **operator-authorised PR update**. The current Draft PR (#365, or its successor) may serve as the landing PR **if and only if** its head content is **identical** to the operator-accepted text.
Merge success **must not** be interpreted as branch-deletion permission. The merge endpoint is named `MERGE_OPERATION_ENDPOINT_REACHED` and the branch-deletion endpoint is named `BRANCH_DELETION_OPERATION_ENDPOINT_REACHED` (the legacy `WORK_ORDER_MERGE_ENDPOINT_REACHED` is forbidden and triggers `MERGE_ENDPOINT_MISATTRIBUTED_TO_WORK_ORDER`).
- If the operator-accepted text differs semantically from the current Draft head, a new review cycle and renewed operator acceptance are required before landing.
- **No** parallel V2 file is created.
- **No** rewriting of PR #276's Git history.

**Work Order Schema integration (§4.17).** The Work Order is the **sole authorisation object** driving automatic execution after operator approval inside `VIBECODING_MODE`. Operator approval binds exactly `work_order_id + document_version + work_order_digest`. The Work Order's automatic endpoint is mode-discriminated:

  - **Execution-type (FULL / LIGHTWEIGHT)**: `DRAFT_PR_DELIVERY_VERIFIED → WORK_ORDER_AUTOMATIC_ENDPOINT_REACHED → STOP`; it **must not** include any Post-Draft authorisation (`draft_to_ready=false`, `merge=false`, `branch_deletion=false`). Post-Draft operations require separate independent operator authorisations issued **after** `DRAFT_PR_DELIVERY_VERIFIED`.
  - **Consultation-only**: `CONSULTATION_DELIVERABLE + CONSULTATION_REPORT → CONSULTATION_OPERATION_ENDPOINT_REACHED → STOP`; no Draft PR or Post-Draft chain exists.

Execution results are written into a separate `WORK_ORDER_EXECUTION_RECORD` and **must not** be written back over the Work Order or used to expand authorisation scope.

### §10.7 Amendment Management

- Semantic change requires operator approval.
- Non-semantic editorial change may be proposed by agents; whether to merge remains an operator decision.

### §10.8 Out-of-Scope for This Contract

AUTH-N numbering, receipt schema, executor / wrapper naming and boundaries, SSH-key canonical path, sync scripts, blind-review frequency and triggers, `routes.yaml`-style filename, route-entry field schema — all remain in future runtime / node-registry / evidence specs.

**Exception**: the canonical primary transport ports explicitly registered in §3.1.4 (`5bao` port `22222`, `9bao` port `22222`) are governance facts of this contract. Other ports, addresses, proxies, and implementation-level endpoint parameters live in the node-registry / runtime spec.

---

## §11. Construction-Phase ChatGPT-Authored Transfer Prompt Delivery Contract

This clause applies **only** during `CLUSTER_CONSTRUCTION_PHASE` (§2.1). After operator declares `OPERATIONAL_PHASE` (§2.2), ChatGPT exits the default operational control chain and this clause does **not** govern operator↔`vibedev` operational instructions, `vibedev` internal prompts, or inter-agent communication.

### §11.1 Unique Path

The only path for a transfer prompt governed by this clause is:

> **ChatGPT (construction-phase consultant) authors → operator reviews and forwards → `vibedev` / 小马蹄 Hermes / operator-designated agent executes the construction, audit, remediation, or validation task**

### §11.2 Definition

A **transfer prompt** under this clause is a complete task prompt that ChatGPT / assistant + construction-phase orchestrator consultant generates for the operator, for the operator to review and then forward verbatim to an executing agent.

  - While ChatGPT generates it, it is only a consultant's recommended text.
  - When the operator chooses to forward it, only the permissions explicitly stated in the prompt are activated. Forwarding does **not** expand authorisation and does **not** replace §9 high-risk confirmation.
  - The primary goal is to assist the operator in directing vibedev to build, audit, remediate, and validate the cluster construction, while maintaining the V2 baseline / mainline, identity, authorisation, STOP, and evidence boundaries.

### §11.3 Out of Scope

The following are **not** governed by this clause (they are handled by the runtime prompt spec or the corresponding context):

  - vibedev's self-generated internal 9-role / runtime prompts;
  - prompts generated by vibedev or any other agent and sent to downstream agents;
  - agent-to-agent communication;
  - agent reports;
  - operator's own ad-hoc messages;
  - ordinary operator ↔ ChatGPT discussion.

This clause **must not** be misinterpreted as constraining all prompts generated by vibedev.

### §11.4 One-Copy Format and Writing-Block Prohibition

  1. Each complete transfer prompt that operator forwards **must** be placed in a **plain Markdown fenced code block** with the language tag fixed to `text`. Example: ` ```text `.
  2. **Forbidden** writing-block formats include: rich writing blocks, special writing cards, editable blocks, accordion blocks, tabbed blocks, callout blocks, and any other non-ordinary code-block component that mobile clients cannot one-tap copy.
  3. The code fence contains **only** the forwardable prompt body. Consultant's analysis, evaluation, risk notes, and suggestions stay **outside** the fence.
  4. A single code fence carries exactly one logically complete prompt, unless explicitly part of a single multi-segment prompt.
  5. Each transfer prompt is **self-contained**, **mobile-friendly**, and **one-tap copyable**.
  6. **Batch consolidation**: related items that belong to the same authorisation phase **must** be consolidated into a single complete transfer prompt or a minimal-segment prompt set. Avoid consecutive micro-prompts, patch-style additions, and micro-PRs to reduce the operator's manual forwarding and authorisation burden. Only split into separate prompts or PRs when risk level, authorisation checkpoint, execution phase, or isolation requirements genuinely differ. Clarity and completeness **must not** be sacrificed to reduce segment count.

### §11.5 Length and Segmentation

**Highest principle**: ChatGPT **must** completely, accurately, and unambiguously convey the task, goal, background, permissions, prohibitions, STOP conditions, acceptance criteria, and output requirements in the transfer prompt that the operator will forward to vibedev or a designated agent.

The 3000-character limit is a **per-segment split threshold**, not a total-prompt length cap.

  1. After completing the transfer prompt draft, ChatGPT **must** count the characters of the forwardable body inside each `text` code block.
  2. If the complete prompt body is **≤ 3000 characters**, use a single `text` code block in one segment.
  3. If the complete prompt body **exceeds 3000 characters**, it **must** be split into multiple segments. Each segment's body **must not** exceed 3000 characters.
  4. The number of segments **must** be kept as low as possible while ensuring clarity, completeness, correct ordering, and one-tap copyability, to minimise the operator's manual forwarding effort.
  5. The total prompt **may** exceed 3000 characters based on task complexity, but **must** follow the segmentation rules above.
  6. Do **not** delete background, authorisation boundaries, prohibitions, STOP conditions, acceptance criteria, or output requirements just to compress into a single segment or reduce segment count.
  7. When multi-segment is required, the prompt **must** explicitly instruct the receiver to wait for all segments before starting work. Non-final segments: ACK only, do **not** execute. Only the final segment authorises execution.
  8. The **final** segment **must** end **exactly** with:

   ```
   全部发送完毕，收到后立即开始执行。
   ```

   No "or equivalent" is permitted. The clause is closed at that line.
  9. After the final segment, all preceding segments must have arrived; agents **must not** begin work before every segment is present.
  10. The 3000-character limit applies to the forwardable body inside each code block. Brief explanatory text **outside** the code fence does not count toward the agent instruction body.

### §11.6 Version Management

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

### §11.7 Blind-Review Additional Rules (for `小马蹄 Hermes`)

  - whether the review is independent and blind;
  - forbidden reads — which `vibedev` reports, sessions, memory, scratchpads, intermediate conclusions;
  - allowed reads — which repos, PRs, configs, and `PRE_V2_HISTORICAL_EVIDENCE` may be referenced;
  - blind-review isolation boundaries;
  - evidence citation format;
  - prohibition on contamination by other agents' conclusions.

### §11.8 `vibedev` Job Prompt Additional Rules

Phase name; current baseline / HEAD; allowed / forbidden actions; whether SSH / real model calls / Git writes / Draft PR / Ready / merge / config writes / `--apply` are permitted; operator checkpoint; stopping conditions; acceptance criteria; report-only vs allowing in-repo artefacts. The current agent operation **must** be marked `CLUSTER_CONSTRUCTION_OPERATION`. The prompt **may** describe the future governance target under construction, audit, remediation, or validation (e.g. `FULL_9_ROLE_VIBECODING`, `LIGHTWEIGHT_OPERATION`, `HERMES_OPENCODE_VERSION_GOVERNANCE_GATE`, `CENTRAL_MODEL_POOL_GOVERNANCE_GATE`). A future target is **only** the object of construction — it does **not** mean the current operation has entered formal `VIBECODING_MODE`, the complete 9-role runtime, or an operational-phase dedicated governance gate. Before `OPERATIONAL_PHASE` cutover, no construction operation may be marked as formal FULL runtime or V2-compliant E2E.

### §11.9 Long-Context De-Drift

All complete transfer prompts generated by ChatGPT / assistant + construction-phase orchestrator consultant and handed to operator for verbatim forwarding to `vibedev`, `小马蹄 Hermes`, or any other operator-designated agent must, as task requires, re-anchor:

- current phase: `CLUSTER_CONSTRUCTION_PHASE`;
- current operation: `CLUSTER_CONSTRUCTION_OPERATION`;
- operator as final decision maker;
- current baseline / HEAD;
- allowed / forbidden SSH, model, Git, PR, `--apply`;
- checkpoint / STOP / evidence / acceptance and output requirements.

If the prompt references a future execution sub-mode (`VIBECODING_CONSULTATION_ONLY`, `LIGHTWEIGHT_OPERATION`, `FULL_9_ROLE_VIBECODING`) or dedicated governance gate (`HERMES_OPENCODE_VERSION_GOVERNANCE_GATE`, `CENTRAL_MODEL_POOL_GOVERNANCE_GATE`), it **must** carry the label:

> `future governance target / component under construction or validation`

This label **must not** be interpreted as the current operation's classification or as entry into formal `VIBECODING_MODE`, the complete 9-role runtime, or an operational-phase dedicated governance gate.

### §11.10 Forbidden Expansion

A transfer prompt **must not** state: "every agent's every prompt must follow this clause"; "every operator ↔ consultant exchange must use a code fence"; "`vibedev`'s every internal runtime prompt automatically applies this clause"; "an agent's output is long ⇒ violation".

---

## §12. Working Agreement / Acknowledgement

| Field | Value |
|---|---|
| Operator | KK (human user) — decision maker, final authoriser |
| Orchestrator Consultant | ChatGPT / assistant + construction-phase orchestrator consultant (AI) — advisor, auditor, planner, transfer-prompt author, output reviewer, drift detector; **no operator authority; not the VibeCoding runtime orchestrator** (§2.1) |
| Profile dimension (orthogonal to node) | `vibedev` — Hermes profile on `21bao`: in `CLUSTER_CONSTRUCTION_PHASE` (§2.1), executes construction tasks as designated; in `OPERATIONAL_PHASE` (§2.2), sole VibeCoding operational orchestrator. `小马蹄 Hermes` — Hermes profile on `21bao`, external blind reviewer. |
| Node dimension | `21bao` / `5bao` / `9bao` (operator-approved canonical topology; **any** topology change requires operator approval per §3.0.1) |
| `V2 Effective Date` | [awaiting operator acceptance] |
| `V2 → Gray4 sequence` | `CONTRACT_V2_DRAFT_COMPLETE → OPERATOR_ACCEPTED_V2 → V2_BASED_CLUSTER_GAP_ASSESSMENT → OPERATOR_APPROVED_REMEDIATION → REMEDIATION_EXECUTION_AND_VERIFICATION → PRE_GRAY4_READINESS_PASS → GRAY4_OPERATIONAL_VALIDATION → POST_GRAY4_FINDING_TRIAGE` — Gray4 validates the **post-remediation** cluster; it is **not** a precondition for completing Contract V2. Gray4 used as a precondition to complete V2 triggers `GRAY4_USED_AS_PRECONDITION_TO_COMPLETE_CONTRACT_V2 → STOP`. Remediation started before V2 acceptance triggers `CLUSTER_REMEDIATION_STARTED_BEFORE_V2_ACCEPTANCE → STOP`. |
| `V2 Version` | `2.0` (DRAFT — awaiting acceptance) |
| Historical reference | `v1.0` (PR #276, commits `9f7e8b1` + follow-up `8509a07`); preserved in Git history |
| Contract scope | This contract hardens operator's governance requirements for identity, topology, node architecture, control-plane availability, transport-route failover, execution mode gate (VIBECODING_CONSULTATION_ONLY / LIGHTWEIGHT_OPERATION / FULL_9_ROLE_VIBECODING), dedicated governance gates (HERMES_OPENCODE_VERSION_GOVERNANCE_GATE §3.8, CENTRAL_MODEL_POOL_GOVERNANCE_GATE §6.9), complete 9-role roster, 8-role assignment pre-brief, Central Model Pool, operator checkpoints, workflow governance envelope, evidence levels, transfer-prompt delivery, drift handling, amendment procedure, Git delivery pipeline with CANDIDATE_TRIPLE–commit tree binding, exact staging (approved new files permitted, manifest-external untracked forbidden, construction-specific paths not a universal constant), two-phase evidence model (pre-commit `PUBLIC_SAFE_EVIDENCE_PROJECTION_DRAFT` → post-commit `DRAFT_PR_EVIDENCE_BODY`), bounded push/PR recovery, mode-specific Draft PR plan provenance, Draft PR evidence body, post-push independent verification, completion report, and three-stage Draft→Ready→Merge governance chain with `POST_DRAFT_GIT_INTEGRATOR_BINDING` per Post-Draft operation, exact-binding authorisations, three independent structured completion reports (`READY_TRANSITION_COMPLETION_REPORT` / `MERGE_COMPLETION_REPORT` / `BRANCH_DELETION_COMPLETION_REPORT`) and cross-verification before corresponding `*_VERIFIED` and endpoint states, PASS / FAIL paths mutually exclusive with FAIL → `READY_TRANSITION_VERIFICATION_FAIL` / `POST_MERGE_VERIFICATION_FAIL`, method-level verification, post-merge verification, 2-attempt API budgets each with explicit exhaustion states (§4.16.8–§4.16.17). **Confirmed** in this contract: VC0–VC8 pre-stage; Work Order approval = job start; dual-layer readiness (§4.10); `ROLE_COMPLETION_REPORT` + cross-verification (§4.13); bounded corrective loop governance (§4.12); default return matrix and artifact invalidation (§4.14); paused-and-revalidate path (§4.10.3); `LIGHTWEIGHT_OPERATION` / `FULL_9_ROLE_VIBECODING` default endpoint is Draft PR; FULL default mid-to-late-stage topology with CANDIDATE_TRIPLE freeze, dual tester, test gate, dual reviewer, review gate, and git-integrator hard gate (§4.16). **Still to be finalised by operator in future operator-approved operational workflow spec**: machine-executable serialisation format for Work Order fields, specific field encoding and validator implementation, task-specific role linear order / concurrency / handoff topology, task-specific test / review choreography, workspace and command implementation, packet / receipt physical storage format (logical schema provisionally fixed in §10.3 — `PROVISIONAL_ARTIFACT_EVIDENCE_SCHEMA_PENDING_POST_REMEDIATION_GRAY4_VALIDATION`), closeout schema, complete `VIBECODING_MODE` state machine. Downstream runtime / model-pool / node-registry / audit / evidence specs **must comply** with these requirements. This contract **does not** define concrete code structure, schemas (`routes.yaml` or otherwise), script names, receipt / ledger field schemas, SSH-key paths, route-chain field schemas, or executor / wrapper internals. **Exception**: the canonical primary transport ports explicitly registered in §3.1.4 (`5bao` port `22222`, `9bao` port `22222`) are governance facts of this contract. Other ports, addresses, proxies, and implementation-level endpoint parameters live in the node-registry / runtime spec. |

---

## §13. Principal V1 → V2 Deltas (Summary)

| Area | V1 (PR #276) | V2 (this document) |
|---|---|---|
| 3000-character rule | "each segment < 3000 characters" (hard) | per-segment split threshold: ≤3000 single segment, >3000 split with each segment ≤3000; total prompt may exceed 3000; must not delete content to reduce segment count (§11.5) |
| 9-role roster | five mixed roles | FULL_9_ROLE_VIBECODING: fully enumerated 9-role roster (§4.3); roster enumeration does **not** define execution order, concurrency, or workflow; LIGHTWEIGHT: minimum recommended roles (§4.1.2); VIBECODING_CONSULTATION_ONLY: no 8-role assignment (§4.1.1); FULL nine roles and LIGHTWEIGHT actual roles each require distinct meaningful model invocation (§4.5); tools cannot substitute for a role's own model call |
| Model invocation evidence | absent | FULL nine roles + LIGHTWEIGHT actual roles each require evidence: task/run ID, role, node, model, providers, invocation ID, timestamps, input/output digests, token usage (§4.7); orchestrator evidence via current-session preselected binding (`OPERATOR_PRESELECTED_SESSION_BINDING`, §4.3) |
| Role completion criteria | absent | FULL nine roles + LIGHTWEIGHT actual roles: 6 conditions (assignment, input, model invocation, work product, acceptance criteria, evidence); invocation alone ≠ completion; failure/empty/missing → §7 STOP (§4.8) |
| Role trimming | not explicitly forbidden | FULL mode only: explicit no-trim / no-skip / no "named-but-not-executed" (§4.5); LIGHTWEIGHT executes operator-approved actual role set; named-but-not-executed, no distinct model invocation, shared invocation, multi-role response reuse, generic-command-only, tool-only completion, and bare constant verdict are all drift (§10.1) |
| Dual tester / dual reviewer | absent | independent across assignment / context / prompt / batch / output / evidence; different role invocation IDs; no shared model call; **recommended** different node + model (§4.9) |
| 8-role assignment pre-brief | absent | FULL mode only: required; 4-column matrix; no `alternative` (§5.1, §5.5) |
| Assignment strictness | absent | strict per operator spec; failure follows §7 (§5.8, §5.9) |
| Failure STOP | implicit | explicit triggers, preserved evidence, enumerated prohibitions, retry rules; §3.5.5 transport-path failure first enters §3.5 failover; STOP fires on §3.5.6 disallowed trigger, §3.5.8 post-condition failure, §3.5.9 chain exhaustion, §3.5.2 / §3.5.11 invariant violation, or no approved+qualified same-node route chain (§3.4.2, §7.2, §7.8, §13 all share the same exhaustive 5-condition set); §3.5.11 itself is not a failure class |
| VIBECODING_MODE pre-stage | absent | VC0–VC8: operator entry → discussion → Intake → final alignment → sub-mode recommendation → operator selection (§4.1); Intake is read-only, inside mode, common to all sub-modes, not a fourth sub-mode |
| Execution mode gate | absent | VIBECODING_CONSULTATION_ONLY / LIGHTWEIGHT_OPERATION / FULL_9_ROLE_VIBECODING; operator final classifier after VC8; LIGHTWEIGHT risk escalation = STOP (§4) |
| Orchestrator binding | absent | `vibedev` / `21bao` fixed; model operator-preselected at session level; recorded as `OPERATOR_PRESELECTED_SESSION_BINDING`; not re-recommended or re-approved during assignment (§4.3) |
| Non-orchestrator assignment | absent | FULL: 8 roles item-by-item approval; LIGHTWEIGHT: actual role set item-by-item approval; after VC8, before Work Order; forms `OPERATOR_APPROVED_ROLE_NODE_MODEL_ASSIGNMENT_BASELINE`; VIBECODING_CONSULTATION_ONLY: no assignment, no baseline, consultation-only Work Order instead |
| Dedicated governance gates | absent | HERMES_OPENCODE_VERSION_GOVERNANCE_GATE (§3.8) + CENTRAL_MODEL_POOL_GOVERNANCE_GATE (§6.9); do **not** enter VibeCoding modes; do **not** trigger 8-role / 9-role; outside VIBECODING_MODE (§4.2) |
| Central Model Pool | 7-state concept only | single write flow, sync direction, sync-after verification, secret isolation, node calling boundary, credential discovery boundary; public hard + private single-user boundary (§6.6–§6.9); dedicated governance gate (§6.9) |
| Workflow governance envelope | absent | confirmed entry skeleton (§8.1): VC0–VC8 → sub-mode → assignment (where applicable) → Work Order generation → **operator reviews, modifies, approves, or rejects Work Order** → `OPERATOR_APPROVED_WORK_ORDER` → `WORK_ORDER_ACTIVE` → `GLOBAL_READINESS` → per-role `ROLE_ACTIVATION_READINESS` → role execution with `ROLE_COMPLETION_REPORT` + cross-verification (§4.13) → Explorer `ROLE_COMPLETION_REPORT` → `EXPLORER_VALIDATION` (§4.15.2) — **hard gate: planner must not activate before `EXPLORER_VALIDATION_PASS`** → Planner `ROLE_COMPLETION_REPORT` → `PLAN_VALIDATION` (§4.15.2) → §4.12 pre-approved bounded corrective loop on `INCOMPLETE` / `REJECTED` (recoverable deficiency class only) → `FULL` default `IMPLEMENTATION_PLAN_APPROVAL_PACKET` → operator reviews / requests revision / approves / rejects → `OPERATOR_APPROVED_IMPLEMENTATION_PLAN` → implementer activation (§4.15.3) → `IMPLEMENTATION_CANDIDATE` → `CANDIDATE_FROZEN_FOR_TEST` (§4.16.2) → tester-a || tester-b (§4.16.3) → `TEST_EVIDENCE_PACKET` → `TEST_GATE_PASS` (§4.16.4) → `REVIEW_INPUT_PACKET` (§4.16.5) → reviewer-a || reviewer-b (§4.16.5) → `REVIEW_GATE_PASS` (§4.16.5) → git-integrator ROLE_ACTIVATION_READINESS / `GIT_INTEGRATION_INPUT_FROZEN` (§4.16.9) → exact-stage / preflight (§4.16.10) → `PUBLIC_SAFE_EVIDENCE_PROJECTION_DRAFT` → `COMMIT_MESSAGE_EVIDENCE_CONSISTENCY_CHECK` → ordinary commit → `COMMIT_TREE_MATCHES_FROZEN_CANDIDATE` (§4.16.10) → push / remote verification (§4.16.11) → Draft PR create-or-update with `DRAFT_PR_EVIDENCE_BODY` (§4.16.12) → post-push re-verification → `DRAFT_PR_DELIVERY_VERIFIED` (§4.16.12) → `WORK_ORDER_AUTOMATIC_ENDPOINT_REACHED` → STOP (§4.16.13). After Draft, original Work Order authority terminates (§4.16.14). V2 landing requires **two mandatory independent authorisations**: `Draft → Ready` (`OPERATOR_AUTHORIZED_DRAFT_TO_READY` + `POST_DRAFT_GIT_INTEGRATOR_BINDING` + `READY_FINAL_PREFLIGHT` → Post-Ready verification → `READY_TRANSITION_PASS_CLAIM` / `READY_TRANSITION_FAIL_CLAIM` → `READY_TRANSITION_COMPLETION_REPORT` (records `READY_TRANSITION_ROLE_INVOCATION` evidence) → `vibedev` cross-verification (§4.16.16) → **mutually-exclusive fork** → PASS_CLAIM branch: `PR_READY_VERIFIED` → STOP / FAIL_CLAIM branch: `READY_TRANSITION_VERIFICATION_FAIL` → STOP) and `merge` (`MERGE_APPROVAL_PACKET` only on explicit operator request + `OPERATOR_AUTHORIZED_MERGE` + `POST_DRAFT_GIT_INTEGRATOR_BINDING` + `MERGE_FINAL_PREFLIGHT` → method-specific + post-merge verification → `POST_MERGE_VERIFICATION_PASS_CLAIM` / `POST_MERGE_VERIFICATION_FAIL_CLAIM` → `MERGE_COMPLETION_REPORT` (records `MERGE_ROLE_INVOCATION` evidence; report uses `*_CLAIM` names only, no final state names) → `vibedev` cross-verification (§4.16.17) → **mutually-exclusive fork** → PASS_CLAIM branch: `MERGE_DELIVERY_VERIFIED` + `POST_MERGE_VERIFICATION_PASS` + `MERGE_OPERATION_ENDPOINT_REACHED` → STOP / FAIL_CLAIM branch: `POST_MERGE_VERIFICATION_FAIL` → STOP (legacy `WORK_ORDER_MERGE_ENDPOINT_REACHED` forbidden)). Branch Deletion is an **optional third Post-Draft operation**, default off, not part of V2 landing gate: requires separate `OPERATOR_AUTHORIZED_BRANCH_DELETION` + `POST_DRAFT_GIT_INTEGRATOR_BINDING` + `BRANCH_DELETION_FINAL_PREFLIGHT` + `BRANCH_DELETION_COMPLETION_REPORT` (records `BRANCH_DELETION_ROLE_INVOCATION` evidence; may record optional `BRANCH_DELETION_FAIL_CLAIM` only, no PASS claim) → `vibedev` cross-verification → success-only endpoint: `BRANCH_DELETION_VERIFIED` + `BRANCH_DELETION_OPERATION_ENDPOINT_REACHED` → STOP (§4.16.17). Branch Deletion failure does not block V2 landing and is **not** implied by Merge authorisation / success. All mandatory authorisations are **independent**; none is automatic. Each API has a 2-attempt budget with explicit exhaustion STOP state. Each Post-Draft operation's `*_VERIFIED` and endpoint state **must not** be formed before its `*_COMPLETION_REPORT` passes `vibedev` cross-verification; Ready/Merge PASS / FAIL branches are mutually exclusive; FAIL must not form any success endpoint; each Post-Draft operation records its own formal role invocation (Draft or other Post-Draft invocation/report **must not** be reused). Dual-layer readiness by `vibedev` / orchestrator (§4.10) with hard-failure STOP code set + bounded pause-and-revalidate path (§4.10.3); §4.12 bounded loop addresses recoverable completion deficiency only and **must not** be used to patch over missing / fabricated invocation, empty output, fabricated evidence, or evidence infrastructure failure; §4.15 prohibits orchestrator role substitution and artifact mutation by validator — faithful traceable summarisation in validation reports / approval packets referencing source artifact ID/version/digest does **not** constitute substitution; operator substantive plan revision must return to planner for new attempt and re-validation. Validation reports and approval packets carry provenance binding (artifact ID/version/digest); new source version auto-invalidates old reports/packets. §4.16 establishes FULL default mid-to-late-stage topology: CANDIDATE_TRIPLE freeze, dual tester with strict isolation and complementary charter, `TEST_EVIDENCE_PACKET` / `TEST_GATE_PASS` (no majority vote; `TEST_CONTRADICTION_PACKET` on conflict), dual reviewer with blind parallel review, `REVIEW_INPUT_PACKET` / `REVIEW_GATE_PASS` (no majority vote; `REVIEW_CONTRADICTION_PACKET` on conflict), and git-integrator hard gate (both gates valid before any formal Git write). `LIGHTWEIGHT` applies same independence, freeze, gate, and invalidation principles to its actual role set but **must not** auto-upgrade to dual tester / dual reviewer. §4.16.6 codifies invalidation and re-run propagation. Drift signals `GIT_INTEGRATION_INPUT_INVALID`, `BROAD_STAGE_OPERATION_DETECTED`, `CANDIDATE_COMMIT_TREE_MISMATCH`, `COMMIT_MESSAGE_EVIDENCE_MISMATCH`, `REMOTE_BASE_DRIFT`, `REMOTE_TARGET_HEAD_DRIFT`, `UNVERIFIED_PUSH_RETRY`, `UNVERIFIED_PR_API_RETRY`, `DUPLICATE_OR_WRONG_PR_TARGET`, `PUBLIC_EVIDENCE_SECRET_LEAK`, `PUBLIC_GIT_METADATA_SAFETY_CHECK_MISSING`, `DRAFT_PR_DELIVERY_UNVERIFIED`, `READY_OR_MERGE_WITHOUT_AUTHORIZATION`, `APPROVED_NEW_FILE_OMITTED_FROM_STAGE`, `UNAPPROVED_UNTRACKED_PATH_STAGED`, `CONSTRUCTION_UNTRACKED_LIST_LEAKED_INTO_RUNTIME_POLICY`, `MODE_SPECIFIC_PLAN_PROVENANCE_MISMATCH`, `PRECOMMIT_EVIDENCE_DRAFT_MISSING`, `POST_DRAFT_AUTOMATION_CONTINUED` in §10.1 enforce these boundaries. Work Order Schema (§4.17) codifies the canonical governance target: Work Order is the sole authorisation object, `work_order_id + document_version + work_order_digest` exact binding, post-approval in-place modification forbidden, separate `WORK_ORDER_EXECUTION_RECORD`, 17 top-level fields with mode applicability discriminant, mode-discriminated authorization_bindings / repository_scope / role_topology / execution_graph / acceptance_contract / git_delivery_contract / endpoint chain, VERSION/CMP gate isolation, state machine with distinct `OPERATOR_APPROVED_WORK_ORDER` → `WORK_ORDER_ACTIVE` → `GLOBAL_READINESS` transition, Consultation-only branch and endpoint (`CONSULTATION_OPERATION_ENDPOINT_REACHED`), FULL Plan checkpoint mandatory, Consultation no baseline / no Git / no Draft PR. Execution-type endpoint: `DRAFT_PR_DELIVERY_VERIFIED → WORK_ORDER_AUTOMATIC_ENDPOINT_REACHED → STOP` with `draft_to_ready=false / merge=false / branch_deletion=false`. Post-Draft operations require separate independent operator authorisations issued after `DRAFT_PR_DELIVERY_VERIFIED`. Drift signals `WORK_ORDER_SCHEMA_INVALID`, `WORK_ORDER_DIGEST_MISMATCH`, `WORK_ORDER_MUTATED_AFTER_APPROVAL`, `WORK_ORDER_MODE_CONTRADICTION`, `WORK_ORDER_SCOPE_UNBOUNDED`, `WORK_ORDER_ROLE_ASSIGNMENT_INCOMPLETE`, `WORK_ORDER_EXECUTION_GRAPH_INCOMPLETE`, `WORK_ORDER_GATE_TOPOLOGY_INVALID`, `WORK_ORDER_LOOP_PATH_UNAPPROVED`, `WORK_ORDER_BUDGET_UNBOUNDED`, `WORK_ORDER_REPOSITORY_SCOPE_MISMATCH`, `WORK_ORDER_ENDPOINT_OVERREACH`, `WORK_ORDER_POST_DRAFT_AUTHORITY_INCLUDED`, `WORK_ORDER_ARTIFACT_SCHEMA_INCOMPLETE`, `WORK_ORDER_APPROVAL_BINDING_STALE`, `WORK_ORDER_EXECUTION_RECORD_OVERWROTE_AUTHORIZATION`, `RUNTIME_STATE_USED_AS_AUTHORIZATION_SOURCE` guard schema and mode-applicability violations (§10.1). Detailed workflow still to be finalised: machine-executable serialisation format for Work Order fields, specific field encoding and validator implementation, task-specific command details, workspace implementation, packet/schema fields; closeout schema; complete `VIBECODING_MODE` state machine. Bounded corrective loop budgets (§4.12) recommended by `vibedev`, approved by operator in Work Order |
| Evidence levels | absent | 8 levels; anti-extrapolation rules; double-hash rule for untracked (§8.5, §8.6) |
| `PRE_V2_HISTORICAL_EVIDENCE` | absent | hard rules against reinterpretation; full banner enforced (§8.8) and re-asserted in `PRE_V2_HISTORICAL_EVIDENCE_BANNER_MISSING` (§10.1) |
| Prompt Delivery Contract | informal §7 guidance | full contract: text code fences, writing-block prohibition, per-segment split threshold (≤3000 single segment, >3000 split, each ≤3000, min segments, clarity first), exact closing line, full-replacement and incremental-revision markers, mobile one-tap copy (§11) |
| Drift signals | 7 | expanded to 235-entry canonical signal catalog (31 + 9 + 5 + 6 + 4 + 5 new registry-count-scope / Gate-FAIL-stage / authority-matrix / Post-Draft-auth / Consultation-forbidden signals) |
| High-risk checkpoints | §4 vague | §9 explicit 4 categories (A/B/C/D), 12+ high-risk items, including `Hermes` / `OpenCode` install / update / downgrade / migration / restart / switch (§9.3) |
| Top-line governance | role authority scattered | §1 GP-1 / GP-2 / GP-3 single page; recommend → assign → execute locked |
| Effect mechanism | §10 "signing" (later corrected to Working Agreement) | effective only on operator explicit chat acceptance; on acceptance update existing file with `Version: 2.0` + `Supersedes: V1 / PR #276` + `Historical source retained in Git history` |
| Transport-route failover | absent | §3.5 same-node transport-route failover with operator-approved chain, standing authorization, per-switch no-permission-needed; successful fallback continues the original task (no mid-task interrupt), standalone Transport Fallback Report after task completion; wrong / unqualified / non-SAME-NODE routes forbidden; chain change needs operator approval; matching §3.5.5 transport-path failure first enters §3.5 failover; after the 5 termination conditions (§3.5.6 / §3.5.8 / §3.5.9 / §3.5.2 or §3.5.11 invariant / no approved chain) fire, enters §7 Failure STOP; §3.5.11 itself is not a failure class |
| `21bao` as control plane | not labelled | §3.6 `ALWAYS_ON_CONTROL_PLANE` is design + SLA target; on unavailability enter `CONTROL_PLANE_UNAVAILABLE / VIBECODING_UNAVAILABLE`; no worker take-over, no orchestrator self-election, no auto-migration, no transport-route-failover → control-plane interpretation; §3.6.7 recovery gate |
| `Hermes` / `OpenCode` version handling | absent | §3.8 dedicated governance gate (V0–V8), decoupling, qualification, mixed-version rules, operator-driven changes only, no auto-upgrade, qualification failure = STOP |
| `MODEL_QUOTA_EXHAUSTED` | absent | model-level failure class (§3.5.13); not transport-path failure, no §3.5 route fallback; immediate STOP, preserve checkpoint, mark BLOCKED/PARTIAL/OUTPUT_COMPLETE_BUT_UNVERIFIED; no auto-retry/substitution/continuation; operator-only recovery (A–E); orchestrator model exhaustion → entire task STOP (§5.10–§5.12, §7.1, §7.4, `PUBLIC_TOKEN_PREFIX_MARKER_TREATED_AS_CREDENTIAL_VALUE`, `CREDENTIAL_AUTO_ROTATED_OR_REPLACED_WITHOUT_AUTHORISATION`, `MODEL_QUOTA_EXHAUSTED_TREATED_AS_TRANSPORT_FAILURE`, `AUTOMATIC_MODEL_NODE_PROVIDER_CREDENTIAL_SUBSTITUTION_ON_QUOTA`, `AUTOMATIC_RETRY_OR_SCOPE_REDUCTION_ON_QUOTA_EXHAUSTION` (§10.1 catalog)) |
| Historical PR / report handling | unspecified | `PRE_V2_HISTORICAL_EVIDENCE` rules; historical files untouched |


| Artifact / Evidence / Packet / Receipt schema | absent | §10.3 canonical governance schema (11-field common envelope including execution_record_ref as formal bullet, lifecycle_state_at_creation, type-specific aliases, conditional execution_record_ref, Claim as embedded subobject without parent digest, Public Projection as derived Artifact without embedded safety receipt, authority matrix, lineage with append-only invalidation, append-only Receipt lifecycle with single-subject transition Receipts for all 4 types, complete lifecycle registries for Artifact/Evidence/Packet/Receipt, complete canonical Receipt type registry (44 canonical types: closed DSL only — AND/OR/EXACTLY_ONE_OF/NOT + CURRENT/STATE_CREATED/DECISION/VALID/SAME_OBJECT/SUBJECT_MATCH/MODE_IS/STAGE_IS/PLAN_CHECKPOINT_IS/ROLE_INSTANTIATED/DIRECT_TO_IMPLEMENTER_IS/NOT_APPLICABLE_IF/EVIDENCE_OF/TRUE; cycle-free; per-stage Post-Draft bindings DRAFT_TO_READY/MERGE/BRANCH_DELETION; obsolete POST_DRAFT_GIT_INTEGRATOR_BINDING_RECEIPT deleted; V8 explicit V0–V7 enumerated; Authority Matrix bidirectional closure)); status: `PROVISIONAL_ARTIFACT_EVIDENCE_SCHEMA_PENDING_POST_REMEDIATION_GRAY4_VALIDATION` — not V2 final acceptance, not cluster remediation complete, not Gray4 PASS. Gray4 validates the post-remediation cluster; it is not a precondition for completing Contract V2. |
| Version governance objects | absent | §3.8 V0–V8 bound to Packet / Artifact / Receipt objects (§10.3.14); V3 authorises preparation only, V4 checkpoint Packet + review Receipt (not V5), V5 authorises exact-scope execution via frozen authorization Packet, V6 execution Evidence independent of V5 Packet; V7 qualification failure = STOP; V4/V5/V6 object conflation triggers `VERSION_GOVERNANCE_STAGE_OBJECT_CONFLATION → STOP`; V7 credential Evidence limited to identity/class/binding, no secret value observation |
| Drift signals | 175 | expanded to 235-entry canonical signal catalog (31 + 9 + 5 + 6 + 4 + 5 new registry-count-scope / Gate-FAIL-stage / authority-matrix / Post-Draft-auth / Consultation-forbidden signals) |

---


## §14. GitHub Credential Runtime Reliability Hardening

### §14.1 Scope & Rationale

This section addresses documented runtime risks from rounds 69–70 of the V2 Draft:

- Windows user-level `GH_TOKEN` exists and operator has not modified it, but the Hermes/vibedev agent process does not inherit it (`PROCESS_ENV_STALE`), causing false "token not found" failures and Git push failures.
- Default `git push` does not automatically use `$env:GH_TOKEN`; without a deterministic credential loader and temporary askpass, delivery may fail despite a valid token.
- In FULL-mode Work Orders, an independent `git-integrator` role faces the same process-env staleness problem, and may not discover it until the final commit fails to push.
- Proxy, token, credential injection, repo permission, and remote path issues conflate during diagnosis, causing blind retries and budget exhaustion.

These rules do not modify:

- The nine role definitions, execution order, or role responsibilities (**§5**).
- The 21bao/5bao/9bao topology (**§5.1**).
- Gate ownership or operator permissions (**§9**).

### §14.2 GitHub Credential Runtime Loader Rules

**§14.2.1 Canonical secret source.** The canonical GitHub credential source is the Windows current-user environment variable `GH_TOKEN`. No other parallel canonical source shall be registered. The contract shall name no other user-facing token variable for this repository.

### §14.2.2 Loader distinction — complete credential runtime status truth table.

The canonical secret source is the Windows current-user environment variable `GH_TOKEN` only. The current-process value is a possibly-stale non-canonical cache, not a second authorised source.

Any runtime credential loader must distinguish exactly these five states:

| # | User-level `GH_TOKEN` | Current-process `GH_TOKEN` | Classification | Outcome |
|---|---|---|---|---|
| 1 | non-empty | non-empty, equal | `USER_ENV_TOKEN_READY` | ready — child can use process value directly or re-inject for isolation |
| 2 | non-empty | empty | `PROCESS_ENV_STALE_ABSENT` | observation/recoverable — read from user level, inject into child subprocess, re-auth, ls-remote; success → READY |
| 3 | non-empty | non-empty, different | `PROCESS_ENV_STALE_MISMATCH` | observation/recoverable — process value is stale/different; discard it; use canonical user-level value; re-inject into child; re-auth and ls-remote required; record non-secret mismatch boolean |
| 4 | empty | empty | `TOKEN_SOURCE_MISSING` | terminal failure — STOP |
| 5 | empty | non-empty | `UNTRUSTED_PROCESS_ONLY_TOKEN` | terminal failure — process residue value is not canonical; STOP, do **not** use it as credential |

States are classified into three categories:
- **observation/recoverable condition** (#2, #3): not a failure; recovery via user-level read and child injection is expected; if recovery fails, use `PROCESS_ENV_RECOVERY_FAILED` as terminal failure.
- **readiness outcome** (#1): ready.
- **terminal failure** (#4, #5): STOP, no further action.

`REMOTE_ALREADY_UPDATED` is a success/no-op outcome, not a failure.

If multiple user-level sources are explicitly declared as canonical, classify as `TOKEN_SOURCE_AMBIGUOUS` and STOP. The current contract declares only one canonical source (user-level `GH_TOKEN`); so `TOKEN_SOURCE_AMBIGUOUS` is reserved for future configuration changes and does not apply to process-environment comparison.

**§14.2.3 PROCESS_ENV_STALE handling.** When the user-level token exists but the current process has not inherited it, the loader must:

1. Read the user-level value via a subprocess (e.g., `PowerShell [Environment]::GetEnvironmentVariable("GH_TOKEN","User")`).
2. Inject the value into a controlled subprocess environment variable (e.g., `VIBECODING_GH_TOKEN`).
3. Pass it via a temporary askpass script or equivalent credential channel — **never** embed in the script file.
4. The loader **must not** write the token back to the parent process, any repo or user configuration file, remote URL, log output, Receipt, Evidence, or model context.
5. The loader **must not** report the token value, partial value, reversible encoding, or hash fingerprint that could identify the secret.
6. Report only the classification string and the non-secret evidence items listed in **§14.7**.

**§14.2.4 Multiple source ambiguity.** If more than one candidate variable is non-empty and the values differ, the loader must fail closed and STOP. It must not auto-select or heuristically choose between them.

**§14.2.5 Temporary askpass.** The loader must create a temporary askpass script that:

- Reads the token from a single-use environment variable (e.g., `VIBECODING_GH_TOKEN`) at runtime.
- Does **not** contain the token inside the script file.
- Is created with restrictive ACLs (`chmod 700` or equivalent).
- Is deleted immediately after the Git operation completes.
- Is not retained in any persistent location or backup.

**§14.2.6 No SSH fallback.** The loader shall operate only over the HTTPS transport path. SSH fallback is permanently prohibited for this credential hardening scope.

**§14.2.7 Token secrecy from model context.** The model (orchestrator, git-integrator, or any other role) must never receive the token value, a partial value, a hash, or any encoding from which the token could be derived. The model receives only:

- The credential state classification string (e.g., `PROCESS_ENV_STALE`, `HTTPS_AUTH_AND_NETWORK_READY`).
- Non-secret evidence items listed in **§14.7**.

### §14.3 Two-Level Git Delivery Readiness

For any FULL or LIGHTWEIGHT Work Order that includes a Draft PR Git endpoint, two readiness checks must execute before any Git write.

**§14.3.1 Level 1 — Global Git Delivery Readiness (as part of `GLOBAL_READINESS`).** The state chain is:

`OPERATOR_APPROVED_WORK_ORDER → WORK_ORDER_ACTIVE → GLOBAL_READINESS`

Level 1 executes as a Git Delivery Readiness sub-check of `GLOBAL_READINESS`. The credential loader must verify:

1. Canonical user-level token exists and is unique (`USER_ENV_TOKEN_READY` or `PROCESS_ENV_STALE_*` — both recoverable).
2. A child process can load the token (injection test or equivalent signal).
3. Authenticated GitHub identity matches the expected repository owner/collaborator.
4. Target repository is readable.
5. Repository permission reports `push=true` for the authenticated identity.
6. Remote URL, target branch, and base branch match the approved Work Order.
7. The same Git executable, HTTPS URL, credential injection method, and proxy path that will be used for the actual push successfully execute an authenticated `git ls-remote` against the target.
8. Draft PR endpoint check — applies differently per Work Order `git_delivery_contract` intent:

   a. Intent `CREATE_NEW_DRAFT_PR`:
      - GitHub API reachable.
      - Authenticated identity has permission to create PRs on target repo.
      - Approved base and head branches are valid.
      - No conflicting or duplicate open PR exists for the same base/head pair.
      - Draft PR creation capability is confirmed (e.g., via API metadata or permissions check).

   b. Intent `UPDATE_EXISTING_DRAFT_PR`:
      - The exact PR number exists.
      - PR must be OPEN and DRAFT.
      - PR base and head branches must match the approved Work Order.
      - PR head ref and remote branch state are readable.

If any check fails:

- The Work Order remains `WORK_ORDER_ACTIVE` but `GLOBAL_READINESS` reports failure/blocked.
- No non-orchestrator Role Activation may proceed.
- The approved Work Order is not reverted, revoked, or overridden.
- No push budget may be consumed.
- A structured failure classification (**§14.6**) must be output with STOP evidence.
- The orchestrator must STOP.

CONSULTATION_ONLY mode has no Git endpoint; Level 1 Git Delivery Readiness does not apply.

**§14.3.2 Level 2 — git-integrator Activation Re-verification.** Immediately before a git-integrator model invocation starts Git write operations, the same credential loader and network path must re-verify:

1. `USER_ENV_TOKEN_PRESENT` (re-read from user env).
2. Child process token loaded (re-inject if necessary).
3. Authenticated GitHub identity matches expected identity.
4. Repository push permission.
5. Remote branch current SHA.
6. Authenticated `git ls-remote` succeeds.
7. Target refspec is available for push.
8. Proxy path is available.

If Level 2 re-verification fails:

- The git-integrator must not execute Git write operations.
- The orchestrator must not take over Git writing.
- No new commit may be created.
- Resumption evidence must be returned and the process must STOP.

### §14.4 Git Write Capability Control

**§14.4.1 Read-only interfaces (may be called by orchestrator readiness):**

| Interface | Purpose |
|---|---|
| `credential_source_probe` | Read user-level token presence without exposing value |
| `authenticated_identity_probe` | Verify GitHub authenticated login |
| `repo_permission_probe` | Verify repository push permission |
| `authenticated_ls_remote` | Authenticated `git ls-remote` via inject+askpass |
| `remote_and_pr_state_probe` | Read remote branch SHA and PR headRefOid |

**§14.4.2 Write interfaces (only git-integrator invocation may call):**

| Interface | Purpose |
|---|---|
| `stage_exact_manifest` | `git add` with approved manifest |
| `create_normal_commit` | `git commit` with structured message |
| `push_approved_refspec` | `git push` with approved remote/branch/refspec |
| `create_or_update_draft_pr` | Create or update Draft PR body |
| `verify_local_remote_pr_sha` | Final three-source SHA verification |

### §14.4.3 Git write binding requirements — including Post-Draft operations.

Every Git write call must be bound to its mode-specific authority. Two binding regimes apply:

**A. Draft PR delivery Git write (original git-integrator within Work Order):**
- Work Order ID / version / digest
- git-integrator assignment ID / version / digest
- git-integrator role invocation ID
- git-integrator model invocation ID
- Frozen integration Packet ref
- Candidate ref
- Git operation ref
- Exact staged manifest
- Approved remote, branch, and refspec
- Credential loader execution ID
- Tool invocation ID

**B. Each Post-Draft Git/API write (Ready, Merge, Branch Deletion):**
The original Work Order triple serves as provenance only, not as current authority.
- Current-stage operator authorization Receipt (specific to Ready / Merge / Branch Deletion)
- Current-stage post-Draft git-integrator binding (stage-specific)
- Current-stage role invocation ID
- Current-stage model invocation ID
- Current-stage approval Packet ref
- Current-stage operation ref (e.g., `DRAFT_TO_READY_OPERATION_REF`, `MERGE_OPERATION_REF`, `BRANCH_DELETION_OPERATION_REF`)
- Current-stage PR or branch ref (e.g., `PR_TRIPLE`, `BRANCH_TRIPLE`)
- Credential loader execution ID
- Tool invocation ID

A write call missing any of its regime-specific bindings must be rejected.

Ready, Merge, and Branch Deletion must each use their own credential-readiness evidence, role invocation, and binding. These must not be reused from the original Draft PR delivery or from each other.

### §14.5 Role Boundary Enforcement

- **orchestrator** calls read-only readiness interfaces only (**§14.4.1**). It must not directly perform `git commit`, `git push`, `stage_exact_manifest`, or `create_or_update_draft_pr`.
- **git-integrator** is the sole role authorised to call Git write interfaces (**§14.4.2**), after approved Activation and Level 2 readiness.
- Every Git write must record `caller_role=git-integrator` plus the corresponding role and model invocation IDs.
- If git-integrator fails after Level 2 readiness, the orchestrator must not take over Git writing. The orchestrator may only report the failure and STOP.
- The credential loader is a 21bao tool infrastructure responsibility, not an orchestrator business decision and not a git-integrator model output.

### §14.6 Failure Classification & Retry

**§14.6.1 Failure classes.** All Git runtime failures must be classified into exactly one of:

| Class | Meaning |
|---|---|
| `PROCESS_ENV_STALE` | User-level token exists; parent process missing; child injection recovers |
| `TOKEN_SOURCE_MISSING` | No token at user level or any canonical source |
| `TOKEN_SOURCE_AMBIGUOUS` | Multiple non-empty sources with conflicting values |
| `TOKEN_AUTH_FAILURE` | Token present but GitHub authentication fails |
| `AUTHENTICATED_IDENTITY_MISMATCH` | Authenticated user does not match expected repository collaborator |
| `REPO_PUSH_PERMISSION_FAILURE` | Authenticated identity lacks push permission |
| `PROXY_PATH_FAILURE` | Configured proxy path fails; direct path may be tested |
| `NETWORK_PATH_FAILURE` | Both proxy and direct HTTPS paths fail |
| `REMOTE_PARENT_MISMATCH` | Remote ref does not point at expected parent commit |
| `NON_FAST_FORWARD` | Local commit not a descendant of remote ref |
| `REMOTE_ALREADY_UPDATED` | Push not needed; remote already at target SHA |

**§14.6.2 Classification priority (to avoid double-classification).** When multiple conditions could apply to the same observation, the following priority order decides the single classification:

1. `REMOTE_ALREADY_UPDATED` — check first; if remote is at target SHA, no further classification needed.
2. `TOKEN_SOURCE_AMBIGUOUS` — conflicting canonical sources.
3. `TOKEN_SOURCE_MISSING` / `UNTRUSTED_PROCESS_ONLY_TOKEN` — no valid canonical token.
4. `PROCESS_ENV_STALE_MISMATCH` — user and process tokens differ (recoverable after re-injection and re-auth).
5. `PROCESS_ENV_STALE_ABSENT` — user token exists but process missing (recoverable).
6. `TOKEN_AUTH_FAILURE` — token present but GitHub rejects authentication.
7. `AUTHENTICATED_IDENTITY_MISMATCH` — authenticated user not the expected collaborator.
8. `REPO_PUSH_PERMISSION_FAILURE` — authenticated but no push permission.
9. `PROXY_PATH_FAILURE` — configured proxy path fails; direct path may be tested next.
10. `NETWORK_PATH_FAILURE` — both proxy and direct HTTPS paths fail.
11. `REMOTE_PARENT_MISMATCH` — remote ref points at unexpected parent.
12. `NON_FAST_FORWARD` — local commit not a descendant of remote ref.

Readiness observations (1–6) must not consume push budget.

1. `PROCESS_ENV_STALE_ABSENT` and `PROCESS_ENV_STALE_MISMATCH` must be recovered by user-level read and child-process injection; operator must not be asked to reconfigure the token. If recovery fails, classify as `PROCESS_ENV_RECOVERY_FAILED` and STOP.
2. Readiness failures (Level 1 or Level 2) do not count as push budget consumption.
3. After a push failure, the remote branch SHA and PR headRefOid must be read via authenticated API before any retry decision.
4. If the remote is already updated to the target SHA, no retry push is permitted.
5. A single controlled retry on an alternate HTTPS path is permitted only when:
   - The primary push failed due to transport/proxy failure;
   - The remote has not been updated; and
   - The alternate path has passed a read-only `git ls-remote` test at Level 2.
6. Blind repeated pushes and SSH fallback are permanently prohibited.

### §14.7 Evidence Requirements (Non-Secret)

Every credential loader and Git readiness call must produce evidence containing:

- `credential_source_name`: the canonical variable name
- `user_level_present`: boolean (read via subprocess)
- `current_process_present`: boolean
- `process_env_stale`: boolean (true if user-level present but process missing)
- `child_process_loaded`: boolean
- `authenticated_github_login`: the GitHub login string
- `repo_permission_raw`: the permission string as returned by GitHub (e.g., `admin`, `write`, `read`)
- `repo_push_allowed`: boolean — derived from `repo_permission_raw` mapping (admin/write → true, read → false)
- `remote_url_class`: e.g., `https_github`
- `proxy_path_class`: `git_global_proxy` or `direct`
- `authenticated_ls_remote_result`: `success` or `FAIL_reason`
- `caller_role`: `orchestrator` or `git-integrator`
- `role_invocation_id`: the role invocation identifier
- `model_invocation_id`: the model invocation identifier
- `local_sha`, `remote_sha`, `pr_head_ref_oid`: final three-source values
- `askpass_temporary_file_deleted`: boolean (must be true after every Git operation)
- `token_exposed_to_model_context`: must be false

The evidence must not contain:

- The token value, partial value, hash, fingerprint, or any encoding from which the token could be derived.
- The askpass script content or file path token.
- Any reversible transformation of the credential.

### §14.8 Deterministic Tests

The credential hardening rules must be tested with at least the following scenarios:

1. User-level token present; parent process token absent → classification `PROCESS_ENV_STALE_ABSENT`; child injection and re-auth recover → `READY`.
2. User-level and parent process tokens present and identical → `USER_ENV_TOKEN_READY`.
3. User-level and parent process tokens both present but differ → `PROCESS_ENV_STALE_MISMATCH`; child injection with user-level value + re-auth → `READY`; record mismatch boolean.
4. User-level token absent, parent process non-empty → `UNTRUSTED_PROCESS_ONLY_TOKEN` → STOP.
5. Token present but GitHub authentication fails → `TOKEN_AUTH_FAILURE` → STOP.
6. Authenticated identity lacks repo push permission → `REPO_PUSH_PERMISSION_FAILURE` → STOP.
7. Proxy path ls-remote succeeds; direct path fails → selection of proxy path for push.
8. Level 1 (Global pre-Role-Activation) passes; Level 2 (pre-git-integrator) re-verification fails → git write must not start.
9. Orchestrator attempts to call a write interface → rejection with `caller_role_mismatch`.
10. Git write called without git-integrator model invocation ID → rejection with `missing_binding`.
11. git-integrator uses correct credential injection and askpass; push succeeds; three-source SHA verification passes → `DELIVERY_VERIFIED`.
12. Post-Draft Ready operation reuses Draft PR delivery binding → rejected with `stale_authority`.



*End of V2 CANDIDATE_TRIPLE. Awaiting operator explicit acceptance in chat per §0.1.*
