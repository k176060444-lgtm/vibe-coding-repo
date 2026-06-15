# Privileged Push Smoke Test

This file was created as part of `wo-privileged-self-repo-test-branch-push-001`
to verify the privileged push workflow end-to-end.

## Test Details

- **Action ID**: `wo-privileged-self-repo-test-branch-push-001`
- **Repo**: `k176060444-lgtm/vibe-coding-repo`
- **Branch**: `privileged-smoke/wo-privileged-self-repo-test-branch-push-001`
- **Changed paths**: `docs/PRIVILEGED_PUSH_SMOKE.md` (this file only)
- **Purpose**: Verify token-aware push works for self-repo test branches

## Workflow Verified

1. ✅ Create privileged action (`priv-approval create`)
2. ✅ Approve via short-approve (`priv-approval short-approve`)
3. ✅ Token preflight (`priv-push --token-preflight`)
4. ✅ Wrapper validates constraints
5. ✅ Real push to test branch (token via stdin, never output)

## Constraints Tested

- [x] Token only read after approval
- [x] Token NEVER output to stdout/stderr
- [x] Token file: owner=vibeworker, mode=600, size>20
- [x] Self-repo only (k176060444-lgtm/vibe-coding-repo)
- [x] Test branch prefix only (privileged-smoke/)
- [x] No force push
- [x] No PR merge
- [x] No secrets/CI/workflow/provider/SSH paths

---

*Generated: 2026-06-15 | V1.2 Privileged Push Real-Mode Workflow*
