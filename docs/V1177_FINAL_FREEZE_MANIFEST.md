# V1.17.7 Final Freeze Manifest

**Generated**: 2026-06-18T15:50:00+08:00
**Status**: FROZEN — no further code changes to V1.17.7

## Frozen HEAD

```
60409e62558bddcdbcbc68b070fa125595ffeb9d
```

## PR History

| PR | Title | Status | Merge SHA |
|----|-------|--------|-----------|
| #159 | fix: V1.17.7.14 immutable repair + credential identity closure | MERGED | 60409e6 |
| #158 | fix: V1.17.7.13 repair authority + credential identity closure | MERGED | 61f2e72 |
| #157 | fix: V1.17.7.12 credential + repair hardening | MERGED | 4ac55b3 |
| #156 | fix: V1.17.7.11 claim store + manifest + heartbeat hardening | MERGED | 8c4083d |
| #155 | fix: V1.17.7.10 runtime drift closure | MERGED | b48cf85 |

## Three-Node HEAD Consistency

| Node | HEAD | Branch | Status |
|------|------|--------|--------|
| Windows (KK-PC-Server) | `60409e6` | main | ✓ clean |
| 5bao (192.168.5.6:22222) | `60409e6` | detached/main | ✓ clean |
| 9bao (192.168.9.6:22222) | `60409e6` | detached/main | ✓ clean |

## OpenCode Runtime

| Node | Version | Binary SHA256 prefix |
|------|---------|---------------------|
| 5bao | 1.17.4 | `922a908d...` |
| 9bao | 1.17.4 | `922a908d...` |

## Test Results (V1.17.7.14 Final)

| Test | Windows | 5bao | 9bao |
|------|---------|------|------|
| Orchestrator self-check (30) | 30/30 | 30/30 | 30/30 |
| Lifecycle self-check (20) | 20/20 | 20/20 | 20/20 |
| pytest (29) | 29/29 | 29/29 | 29/29 |

## Security Scans

| Scan | Result |
|------|--------|
| Unicode bidi/control | CLEAN |
| Secret scan | CLEAN |

## Versions

| Component | Version |
|-----------|---------|
| vibe_toolchain_lifecycle.py | v2.8.0 |
| vibe_job_orchestrator.py | v3.6.0 |

## Reviewer

| Field | Value |
|-------|-------|
| Reviewer model | mimo-v2.5-pro |
| Verdict | APPROVE |
| PR comment | https://github.com/k176060444-lgtm/vibe-coding-repo/pull/159#issuecomment-4739497868 |
| github_formal_review | UNAVAILABLE |

## Approved Baselines

| Item | Value |
|------|-------|
| approved runtime baseline plan digest | `13c70424bc7af317ac0d88b4a34a7c76f156c5fe9c1bd2c536da71d4c4982601` |
| historical code anchor | `547da27317adee5655c479dd73cc6d10690273ef` |
| status | UNCHANGED — not modified by V1.17.7 series |

## Credential Status

```
CREDENTIAL_REMEDIATION_PENDING_OPERATOR_APPROVAL
```

- 5bao controller private key: `/home/vibeworker/.vibedev-secrets/debian-vibeworker-ed25519`
- Status: NOT used, NOT deleted, NOT rotated, NOT modified
- Awaiting independent Operator approval for any action

## OpenCode Runtime Match

```
OPENCODE_RUNTIME_MATCH_CONFIRMED
```

Both nodes: OpenCode 1.17.4, binary SHA256 prefix `922a908d...`

## Freeze Tokens

```
V1.17.7_USABLE_RUNTIME_FREEZE_PASS
V1.17.7_ORCHESTRATOR_RUNTIME_CLOSURE_PASS
V1.17.7_FINAL_FREEZE_RECORDED
```

## V1.18 Production Hardening Backlog

The following items are deferred to V1.18 and must NOT be addressed in V1.17.7:

1. **SSH fault matrix**: Complete timeout/disconnect/controller-crash fault injection testing
2. **Process-group extreme recovery**: Edge cases in PID/PGID management
3. **Credential remediation**: Delete/rotate 5bao controller key (pending Operator approval)
4. **GitHub formal review capability**: Enable real GitHub PR reviews (currently UNAVAILABLE)
5. **Secret history scan**: Scan full git history for leaked secrets
6. **Repair concurrency + fault injection stress test**: Concurrent repair receipt competition under load
7. **GitHub bidi warning vs independent scan discrepancy**: Investigate and resolve
8. **MSYS `/c/Users` path verifier false positive**: Fix file-mutation verifier path handling on Windows

## Evidence Paths

| Evidence | Location |
|----------|----------|
| This manifest | `docs/V1177_FINAL_FREEZE_MANIFEST.md` |
| PR #159 diff | https://github.com/k176060444-lgtm/vibe-coding-repo/pull/159/files |
| PR #159 review comment | https://github.com/k176060444-lgtm/vibe-coding-repo/pull/159#issuecomment-4739497868 |
