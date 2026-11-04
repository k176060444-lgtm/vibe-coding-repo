# P0.3 — Cross-node A2A blind review reliability patch

## Scope
This branch changes the **P0 async remote blind-review executor only**. It does
not implement Hermes's P1 14-phase workflow, approval gates, roles, or release.
P1 may invoke the P0 CLI as an external executable and consume verified reports.
No production machines, paid models, or deployment were used to validate this patch.

## Changes by risk
- **Physical identity**: each Worker derives a stable pseudonymous fingerprint
  from its local OS machine ID; the coordinator requires pinned distinct
  `host_fingerprint` values plus unique auth tokens, and checks every authenticated
  status/report against the enrollment. This rejects the original two-Workers-
  on-one-OS scenario. **This is not remote hardware attestation**. An operator
  must register actual devices and protect each token; two copied host IDs or
  a compromised Worker can still spoof an OS fingerprint.
- **600-second crash recovery**: a per-node durable acceptance receipt contains
  canonical report bytes and accepted-at timestamp in the same atomic write.
  On resume, receipts are verified and rebuilt into the report/state views.
  The grace timer is never restarted merely because a later state write was
  interrupted. Clock rollback fails closed until investigated.
- **Cancellation**: all terminal failure paths request cancellation of running
  remotes, persisting the intent before sending HTTP. `reconcile` retries
  uncertain cancellations. A successful quorum is *not* an approval.
- **Process lifecycle**: Windows uses a kill-on-close Job Object with failure-
  closed assignment; POSIX targets the original process group even after the
  CLI root exits. Terminal completion only follows tree termination attempts.
  OS-level escape or forced worker death still require host-level inspection.
- **Credential isolation**: exclusion of the server token is case-insensitive,
  and Git subprocesses use the same allowlisted environment as the Harness.
  Review CLI and Git credentials must be provisioned explicitly where needed.
- **HTTP deadlines**: entire request, including slow response headers, is
  covered by a wall-time watchdog that shuts down a stalled socket. Redirects
  are not followed.

## Enroll real nodes (manual, authorized step only)
On EACH actual machine run `python -m blindreview host-id`. Verify the three
outputs differ. In `examples/coordinator.json`, replace the sample 64-character
fingerprints with these exact values, and register each physical host's
inventory label and independently generated **different** Bearer token.
Never copy a single Worker config or token to all hosts. Host fingerprint alone
cannot prove physical independence: confirm hardware/topology and token custody.

Each Worker requires a trusted local `physical_host_id` label, `workdir`,
`contract_path`, `repositories`, `harnesses`, and `token_env`.
The Coordinator needs identical approved task/contract/commit and each node's
`host_fingerprint`, URL, token environment name, Harness and model.
Prefer SSH tunnels, WireGuard or mutually authenticated TLS. Do not expose
the plain HTTP worker to the Internet.

## Stable P0 CLI boundary for P1
All commands print machine-readable JSON on stdout; errors use nonzero codes.
These commands are an **executor API**, not workflow arbitration:

```sh
python -m blindreview init --config task.json --state-dir review_state/TASK-001
python -m blindreview step --config task.json --state-dir review_state/TASK-001
python -m blindreview status --state-dir review_state/TASK-001
python -m blindreview collect --config task.json --state-dir review_state/TASK-001
python -m blindreview cancel --config task.json --state-dir review_state/TASK-001
python -m blindreview reconcile --config task.json --state-dir review_state/TASK-001
# Or allow P0 to own the poll loop (60s default):
python -m blindreview coordinate --config task.json --state-dir review_state/TASK-001 --resume
```

`init` creates stable Job IDs without dispatch; `step` submits/polls once.
P1 can schedule `step` at a safe interval, never run two steps concurrently
on the same state directory, and use `reconcile` for unresolved cancellation.
`collect` succeeds only after a verified `QUORUM_MET` and returns report
paths, SHA256 and enrolled host fingerprints. `QUORUM_MET` does not mean
APPROVE, authorized merge, or release.

`status` is a local read-only status snapshot, not evidence of model execution.
After cancellation or quorum, outstanding `pending_cancellations` must be
inspected. A P1 orchestrator must not silently ignore unconfirmed remote
work or failed identity evidence.

## Limitations
- No real 5bao/9bao/rusty connectivity, provider billing, or actual approved
  Codex/OpenCode runtime has been tested for this patch.
- Machine ID fingerprint detects accidental same-host duplication but is
  **not hardware root-of-trust**. Deliberately copied credentials and forged
  Workers require a stronger external enrollment/attestation policy.
- Windows Job Object behavior must be regression-tested on actual Windows.
  POSIX process-group cleanup does not contain a child that deliberately
  escapes its process group.
- A process killed before an atomic acceptance receipt is committed has no
  durable proof of that report's acceptance; it is not counted after resume.
- Cancellation does not prove remote provider stopped billing; reconcile and
  provider-side evidence remain required.

## Automated verification
`python -m unittest discover -s tests -v`
`python -m compileall -q blindreview`

Tests include base and P0.2 regressions plus P0.3 crash-window, cancellation,
identity, credential filtering, HTTP slow headers, and descendant lifecycle
probes. Mock nodes and local HTTP are not real physical-node attestation.
