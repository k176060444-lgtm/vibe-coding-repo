# P0.3.1 — A2A reliability hotfix (review candidate)

This change is limited to the independent **P0 A2A blind-review executor**.
It does not change the P1 workflow, gates, model approval, arbitration or release.

## Why this exists

An independent Windows 10 / Python 3.11.15 review of fixed P0.3 commit
`59d655b9d7c5c7b6158641023a3d174c0ef44592` found:
1. Windows Popen followed by AssignProcessToJobObject is racy. A fast Harness
   may spawn grandchildren before the Job captures its root. The 50-test suite
   failed 1/50 locally and the immediate-child test failed in 8/8 repeated
   runs, although Windows CI happened to pass.
2. Deep JSON responses caused uncaught RecursionError in Coordinator.step().
3. A legacy P0.2 Coordinator ignored the P0.3 host_fingerprint when talking
   to an upgraded Worker, allowing a mixed-version identity downgrade.

## Focused remediation

### Windows process start sequence (no delay-based workaround)
1. Worker creates a fresh named Win32 kernel event, initially unsignalled.
2. Worker starts the **trusted** `blindreview/_win_launcher.py` using the
   currently running Python interpreter. It waits for the kernel event
   and **cannot spawn the approved Harness until signalled**.
3. Worker assigns the waiting launcher to a kill-on-close Windows Job Object.
4. Only after successful assignment does Worker signal the kernel event.
5. Launcher starts the approved command without `shell=True`, inheriting
   the approved cwd, restricted environment, and existing stdio handles.
6. When the root exits, times out or is cancelled, Worker closes/terminates
   the Job Object, which includes its descendants.

The event handle stays open until job cleanup, avoiding event destruction
before the launcher has opened it. If the Worker dies, the kernel's
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE closes the process tree. Job assignment
failure must not release the gate.

This prevents the **pre-assignment spawn race**. It is not an OS-proof sandbox
against arbitrary code escaping the Job using privileged mechanisms. Windows
10 on the actual user host needs a repeat-run independent confirmation.

### Malformed HTTP response handling
`ReviewClient` maps JSON depth `RecursionError` to `TransportError`, which
`Coordinator._query_one` already captures as a recoverable per-node error.
Malformed remote JSON must not unwind the entire polling session.

### Mixed-version fail-closed handshake
P0.3.1 `ReviewClient` sends `X-Blind-Review-Protocol: 3` on every request.
P0.3.1 Worker returns HTTP **426** for requests without that exact header.
The old P0.2 Coordinator/client does not send it and therefore cannot submit,
poll, collect or cancel tasks through a P0.3.1 Worker. New Coordinator against
old Worker is rejected because the old response lacks host_fingerprint.

This is a **version compatibility guard, not cryptographic attestation**.
An intentionally modified old client can send the new header. Real device
identity still requires trusted enrollment, separate credentials and secure
peer transport.

## Upgrade and rollback guidance

- **Never hot-swap a running P0.2/P0.3 Worker into a live older Coordinator.**
- Before switching versions, finish old jobs or use the old binary to cancel
  and reconcile them. Preserve job states, logs and receipts for audit.
- Do not reuse an older Coordinator state directory for a new version. The
  configuration hash differs; this is deliberately fail closed.
- Install the matching Coordinator and Worker executables as a set. Prefer
  verifying both sides' versions off-line before starting network requests.
- Enroll the actual 5bao, 9bao and rusty devices from operator-controlled
  hardware inventory, distinct service credentials and `host-id` output.
- First run an authorized three-node test with synthetic/no-cost Harnesses,
  then request separate authorization for real-model billing and cancellation.

## P1-facing interface (unchanged)

`python -m blindreview init|step|status|collect|cancel|reconcile` remains
available with the same machine-readable success JSON. Pending cancellation
must be reconciled; `QUORUM_MET` denotes accepted review slots, **not APPROVE**.

## Regression evidence

```bash
python -m unittest discover -s tests -v
python -m compileall -q blindreview
```

New tests check pre-v3 client rejection, recovery from deeply nested remote
JSON, and repeated immediate grandchildren on native Windows (10 iterations).
GitHub Actions Linux/Windows CI is useful but is **not** a substitute for
the independent Windows 10 19044 environment that exposed the race.

No production hosts or paid models are accessed by this patch.
