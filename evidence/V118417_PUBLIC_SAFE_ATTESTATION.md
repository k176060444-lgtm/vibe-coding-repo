# V1.18.4 Final Public-Safe Attestation

Generated: 2026-06-19
Task: V1.18.4.17/18 Final Evidence Hygiene + Public/Local Attestation Split

## Status

```
V1.18.4_POST_MERGE_ATTESTATION_PASS
V1.18.4_CONTROLLER_SSH_CREDENTIAL_REFERENCE_HARDENED_PASS
V1.17.7_FREEZE_UNCHANGED
```

## Final HEAD

| Component | HEAD | Status |
|-----------|------|--------|
| Public main | a0b899783044b11dba8e1292a23d7ca757ed6fd8 | PASS |
| Windows controller | a0b899783044b11dba8e1292a23d7ca757ed6fd8 | synced |
| 5bao executor | a0b899783044b11dba8e1292a23d7ca757ed6fd8 | synced |
| 9bao executor | a0b899783044b11dba8e1292a23d7ca757ed6fd8 | synced |

## PR Merge History

| PR | Merge Commit | Status |
|----|-------------|--------|
| #164 | f05f3f9d8e0c3dc6931abae697fb337dff79b685 | merged |
| #165 | a0b899783044b11dba8e1292a23d7ca757ed6fd8 | merged |

## Controller Credential Hardening

| Field | Value |
|-------|-------|
| Status | HARDENED |
| Controller SSH key | Dedicated ED25519 key (controller-key-001) |
| Fingerprint | SHA256:hO9+B7E3oBl9QrkL4pKk06xb1Dog7XwNZAfuH/lS5Kc |
| Operator admin key usage | BLOCKED (not used by Vibe Agent automation) |
| Legacy credential exposure | Remediated |
| Credential registry | Active, with forbidden-key enforcement |
| id6663 in production paths | NONE (confirmed 0 references) |

## Test Results (Post-Merge)

| Node | passed | xfailed | failed | self-check |
|------|--------|---------|--------|------------|
| Windows controller | 159 | 2 | 0 | 34/34 passed |
| 5bao executor | 161 | 0 | 0 | passed |
| 9bao executor | 161 | 0 | 0 | passed |

## Infrastructure

| Component | 5bao | 9bao |
|-----------|------|------|
| bwrap | 0.8.0 PASS | 0.8.0 PASS |
| ripgrep | 13.0.0 PASS | 13.0.0 PASS |
| OpenCode | 1.17.4 PASS | 1.17.4 PASS |
| Sandbox smoke | PASS | PASS |

## Security Scan

| Check | Result |
|-------|--------|
| Secret scan (real tokens) | 0 findings |
| Unicode bidi/control characters | 0 findings |
| token_leak | false |
| credential_content_exposed | false |
| external_repo_write | self_owned_public_github_repo |

## Safety Declarations

| Declaration | Value |
|-------------|-------|
| no_private_key_content | true |
| no_token_content | true |
| no_authorized_keys_content | true |
| private_key_path_in_public | false |
| internal_ip_in_public | false |
| secret_dir_path_in_public | false |
| public_repo_safe | true |

## Orchestrator

| Field | Value |
|-------|-------|
| Version | 3.11.0 |
| SHA256 | 5e820e984ecdcd64e7d1d7b8d0035e1e62d54805ccb6f183d0b30505488861f3 |

## V1.17.7 Frozen Baseline

| Field | Status |
|-------|--------|
| Frozen HEAD | untouched |
| Frozen manifest | untouched |
| Current runtime version | 3.11.0 (expected, post-merge) |

## Resolution Summary

All post-merge items resolved:
- Three-node HEAD synchronization complete
- Controller SSH credential reference hardened to dedicated key
- Operator admin key confirmed not used in any production path
- Legacy credential exposure remediated
- Post-merge test alignment passed (Windows 159+2xf, Debian 161 each)
- Self-check passed on all nodes
- Security scans clean
- V1.17.7 frozen baseline untouched

## Supersedes

This attestation supersedes the pending/blocked status in
evidence/V1184_POST_MERGE_MANIFEST.md.
The BLOCKED and CREDENTIAL_REMEDIATION_PENDING states were historical
intermediate conditions that have since been fully resolved.
