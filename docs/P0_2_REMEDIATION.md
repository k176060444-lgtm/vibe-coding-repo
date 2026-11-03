# P0.2 independent audit remediation candidate

Reference: frozen source `cf35ab01eae63298ff9f2ae9faa4d0012fe73c2c`. Audit evidence commit `40e059d9c7d09cdbcc28b381eea743389aa3f822`; 27 findings. This is a new **candidate**, not production approval. New code requires migrating worker and coordinator configs together (not wire-compatible with P0 report schema or old coordinator states).

## Implemented and tested locally

| Finding | Change | Remaining boundary |
|---|---|---|
| P0-01 | Explicit `physical_host_id` per endpoint, duplicate IDs/physical_host_id/token_env rejected, worker response/report checked against registration | Strings and endpoint credentials do NOT prove physical machine identity. Operator must verify trusted mapping of key/transport to real hosts, on separate physical machines. **Real deployment BLOCKED** until externally attested. |
| P0-02 | Worker-generated complete report envelope; request context required and strictly matched by coordinator; conflicting reviewer metadata rejected | Harness/model *actual provider execution* requires independent CLI evidence; never equate formal quorum with APPROVE |
| P0-03 | `git clone --no-local --no-checkout` for all sources; tests assert no shared local object inode | Read-only command permissions and sandbox still must be configured/verified outside this program |
| P0-04 | Persisted `contract.snapshot` + `execution_binding.json`; pre-execution and restart validation fails queued drift closed | External admin can still edit both mutable job directory and database; protect with OS filesystem permissions |
| P1-01 | Redirects rejected, whole-response deadline checked | HTTPS/SSH-tunnel/WireGuard authentication is a deployment prerequisite; raw HTTP must not be public |
| P1-02, P2-08 | UTF-8 canonical report bytes with LF via `write_bytes`; Coordinator archives exact bytes and verifies on resume | Windows native harness lifecycle must be retested independently |
| P1-03 | Completed-but-uncollected report remains retriable | Real network partition test pending |
| P1-04, P1-10 | Grace maximum 600 seconds; second acceptance and quorum timestamp saved in one state update; recovery reconstructs; per-request deadline budget | OS/process scheduling means absolute cancellation confirmation cannot be guaranteed exactly at 600 seconds; asynchronous reconciliation required |
| P1-05, P1-11 | stdin feeder separated from monitoring; monitoring exceptions attempt to terminate child; unknown liveness becomes INTERRUPTED | Provider-side cancellation and OS-specific process-tree behavior still require independent validation |
| P1-06, P2-05 | Strict report type validation, HTTP transport exception normalization, invalid UTF-8 returns 400 | More fuzzing useful |
| P1-07, P2-04 | OS file locks for Coordinator and Worker workdirs; SQL CAS/atomic submission | Do not share state directories across independent machines or shared filesystems without supported distributed locking |
| P1-08 | Harness env whitelist excluding Worker token, no ambient credential inheritance | Required model credentials must be explicit and scoped; malicious Harness can still print its own credentials |
| P1-09 | Git ignored-file changes now flagged | **Not a strong sandbox:** `.git`, outside paths and external side effects still need native read-only Harness permissions and OS controls |
| P1-12 | Whole HTTP response monotonic deadline with fail-closed streaming | Throughput should be profiled before production |
| P1-13 | Fixed worker pool with bounded outstanding jobs | Persistent queue beyond in-memory window rescheduled upon completed jobs/restart |
| P2-01, P2-02, P2-09 | Cancellation receipts never collect late reports; reconciliation refreshes summary; missing summary rebuilt after resume | Cancel unconfirmed remains a real outstanding dependency |
| P2-03 | Check log size after subprocess exits, not just while running | Real filesystem quotas/out-of-space not simulated |
| P2-06 | `path:line` or `evidence://` location syntax required | Does not prove evidence is true |
| P2-07 | Restore queued jobs only after worker token validated and server port bound | Node auth remains an operational prerequisite |
| P3-01 | Additional real HTTP/adversarial tests; original basic tests retained | No fake test can prove actual model compatibility |

## Important compatibility changes

- Coordinator `nodes[]` requires unique `physical_host_id`, `id`, endpoint and `token_env`; worker requires matching `physical_host_id`.
- Report JSON now includes `task_id`, `contract_sha256`, `harness`, `model`, `node_id`, and `physical_host_id`. Worker attaches these trusted execution-context declarations and rejects conflicting source report values. Report hash covers these fields.
- P0 Coordinator persisted state schema version 1 is **not automatically migrated**; do not resume old live tasks with the new binary. Finish or reconcile old jobs before rollout. Existing SQLite job records that predate snapshots will not execute automatically; this is deliberate fail-closed behavior.
- Worker now requires an explicit `env_allowlist` when model-specific API credential environment variables are needed. They are never inherited unless named; `token_env` is always withheld.
- `physical_host_id` is only an operator-registration value, not cryptographic attestation. Identical IDs are rejected, but **the same machine can lie about two IDs** if it holds both credentials. Require independent device/node credentials, authenticated links and inventory verification before real cross-node acceptance.
- Model runs are NOT launched during local tests. The approval matrix / hardcoded 14-phase state machine remain P1/P2 future work.

## Local test instructions

```sh
python -m unittest discover -s tests -v
python -m compileall -q blindreview
```

Tests include real local Git clone, SQLite, loopback HTTP, mock CLI subprocesses, malicious redirect, slow response, forbidden context changes, same-host declaration rejection, fixed-clone object isolation, process/heartbeat timeouts, and coordinator crash simulations. No real 5bao / 9bao / rusty or provider model runs are part of these tests.

**Never count `QUORUM_MET` as technical APPROVE, CI release authorization or user approval.**
