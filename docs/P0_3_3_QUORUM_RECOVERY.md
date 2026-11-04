# P0.3.3 — quorum-first A2A reliability and ambiguous-submission recovery

**Candidate only. Not deployed. No P1 orchestration changes.**

Base (reviewed) P0.3.2 commit:
`79f34679b1c0d9f85487af4693d2c7e4f4586875`

## Scope and design decision

P0 is an *asynchronous 2-of-3 remote blind-review execution service*.
Atomic all-or-nothing dispatch across independent remote machines is **not**
a protocol guarantee. A transiently disconnected third host must **not**
prevent two trusted independent physical hosts from conducting the review.

Strict multi-host prepare/commit is a different, substantially larger protocol
and still cannot guarantee simultaneous commit/execution after network splits.
It is intentionally not introduced in this focused reliability iteration.

P0 guarantees **fail-closed report validation**, stable job IDs, idempotent
submit retries, bounded deadlines, durable quorum timestamps, and cancellation
reconciliation. It never treats 1 accepted report as a quorum.

## Changed behavior

1. **Two healthy peers are enough to dispatch.** The Coordinator checks
   pinned identity and compatible protocol for every reachable peer. One
   *transiently unreachable* third host is tracked as `PARTIAL` preflight;
   its job is NOT submitted, while the two verified nodes are allowed to run.
   The third is retried on subsequent steps until the existing 600-second
   grace / overall deadline. If an online peer has an invalid identity or
   incompatible protocol, preflight is **REJECTED** and no further dispatch
   occurs. With only two configured peers, both must pass.
2. **Bounded preflight requests.** Each HTTP version request is limited by
   the remaining whole-task and third-seat deadlines.
3. **Uncertain POST is not mistaken for never submitted.** The Coordinator
   persists `submit_attempted=true` before sending any POST. If the response
   is lost, the job remains unconfirmed and a subsequent step retries the
   *same* job ID and immutable request; the Worker uses a SQLite primary key
   to deduplicate.
4. **Cancel tombstones protect late arrivals.** If a cancel request reaches
   the Worker before a delayed POST, the Worker durably stores a cancellation
   tombstone (even for an unknown job ID). A subsequent POST cannot create
   or run that job. If POST was already committed, cancel requests stop the
   queued/running job as before. Uncertain POSTs must be remotely cancelled
   and reconciled on overall cancellation or timeout.
5. **Protocol version 4.** Both Coordinator and Worker must support v4,
   including the new `cancel-tombstone` capability. Older v3 Workers are
   rejected during preflight; older v3 Coordinators are rejected at Worker
   HTTP entry. Worker's `/v1/version` reports version `0.3.3`.
6. **State migration is not implicit.** The Coordinator's versioned config
   digest changes to `0.3.3`; resume older state with its *matching old
   binaries* to finish/cancel/reconcile outstanding work. Retain original
   state, receipt and cancellation evidence. Create a fresh P0.3.3 state
   directory for new work.

## Practical guarantees and non-guarantees

- **Partial dispatch is expected in asynchronous networks.** A peer may
  receive a POST while another returns 503. This is not itself false quorum.
  Assess whether the system eventually obtains two valid reports or performs
  complete cancellation/reconciliation without duplicate job execution.
- Cancellation acknowledgement only proves the Worker has recorded/stopped
  the job as represented by its API. It does not prove vendor billing stopped.
- The pinned OS fingerprint detects ordinary same-host duplicate Workers,
  not malicious hardware identity spoofing. Independent enrollment, separate
  service credentials and trusted transport are deployment prerequisites.
- `QUORUM_MET` means two verified eligible reports; it does **not**
  mean APPROVE, merge authorization, production release or permission to
  bypass P1's human approval gates.

## Focused tests

```bash
python -m unittest discover -s tests -v
python -m compileall -q blindreview
```

Test cases cover:
- one optional peer temporarily unavailable, two healthy complete;
- third recovers before deadline; third never recovers yet quorum finalizes
  after at most 600 additional seconds;
- permanent identity/protocol mismatch still blocks;
- lost POST response followed by same-ID retries and eventual quorum;
- uncertain POST cancellation, including a later-delivered POST and
  persisted SQLite tombstone across Worker restarts;
- P0.3.2 state refusal under the new versioned Coordinator policy.

No real 5bao / 9bao / rusty production access, paid models or deployment is
authorized by this candidate branch. Independently test in Windows 10 first,
then request separate authorization for controlled real-node A2A tests.
