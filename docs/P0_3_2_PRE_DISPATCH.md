# P0.3.2 — pre-dispatch compatibility and HTTP integrity

Status: **candidate for independent review; not production approved**.

Base commit: `a57bc4b544d0e14c8bf15801a47e596b5bf8f38b`
Branch: `remediation/blind-review-p0-3-2-preflight-20261104`

## Scope

This patch addresses the P0.3.1 independent Windows 10 audit's remaining
P1/P2 findings. It does not change the P1 orchestrator, review policy,
quorum threshold, verdict semantics, or release authority.

## 1. Mandatory all-peer preflight before dispatch

P0.3.1 detected a legacy Worker only after POST /v1/jobs had already run.
That could incur model cost or other Harness side effects even though its
report could not be accepted.

P0.3.2 adds authenticated `GET /v1/version`. The response contains:
- protocol version 3;
- worker version 0.3.2;
- required capability `preflight-before-submit`;
- node ID and physical host declaration;
- the Worker's locally derived OS host fingerprint.

Before any job submission, Coordinator checks **every configured peer**:
- endpoint supports the version handshake;
- protocol version is exactly 3;
- required capability is present;
- node ID, physical host ID and host fingerprint match enrollment.

No job is sent to any peer until all peers pass. A permanent compatibility,
authentication or identity failure produces `FAILED_PROTOCOL_PREFLIGHT`
and leaves all remote job stores untouched. A transient network failure
persists `PENDING`, sends no jobs, and retries on the next step.

P0.2 and P0.3.1 workers do not implement `/v1/version`; their 404 response
is treated as an incompatible peer. This closes the P0.3.1
new-Coordinator-to-old-Worker dispatch-before-rejection path.

This is a compatibility and enrollment check, **not hardware attestation**.
An actively malicious peer can still lie about an OS fingerprint. Existing
separate credentials, trusted enrollment and secure transport requirements
remain.

## 2. State upgrade boundary

Coordinator state is now versioned with the P0.3.2 dispatch policy in its
configuration digest and schema version 3. Existing P0.3.1 state cannot be
silently resumed. Finish, cancel or reconcile old work with the matching
P0.3.1 binaries before upgrading; preserve its receipts and logs. Do not
reuse an old state directory as a P0.3.2 run.

## 3. HTTP response body integrity

ReviewClient now requires a valid Content-Length no larger than 2 MiB and
verifies the exact number of bytes received before JSON parsing. Missing,
invalid, negative, oversized or truncated bodies become TransportError.
The protocol's Worker responses already include Content-Length.

## 4. Windows launcher parent lifetime

The trusted launcher now waits on both the Job-assignment event and a
SYNCHRONIZE-only handle to its Worker parent. If the Worker exits before
releasing the gate, the launcher exits without running the Harness rather
than waiting for the full 30-second fallback timeout. The Harness remains
blocked until successful Job Object assignment.

## 5. Regression commands

```bash
python -m unittest discover -s tests -v
python -m compileall -q blindreview
```

New coverage includes:
- current Worker version endpoint and identity response;
- legacy Worker 404 rejected before any peer receives POST /v1/jobs;
- transient preflight failure retries without partial dispatch;
- P0.3.1 state cannot resume under the new dispatch policy;
- truncated and missing Content-Length rejection;
- Windows launcher exits when its Worker parent dies before gate release;
- the same-host HTTP E2E test uses a bounded but less fragile timeout and
  asserts both Workers received no job.

GitHub Actions remains supporting evidence only. Independent Windows 10
10.0.19044 retesting is required, followed by separately authorized
three-node, real-Harness and network/credential validation.

## Acceptance boundary

A passing unit suite does not authorize production. `QUORUM_MET` still
means only that the configured number of reports passed protocol validation;
it does not mean technical APPROVE, merge permission or release authorization.
