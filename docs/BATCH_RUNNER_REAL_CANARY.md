# Batch Runner Real Canary — V1.5.2

## Purpose

Verify that the batch-runner v1.1.0 can execute a real serial batch of
low-risk Work Orders in the trusted self-repo
(`k176060444-lgtm/vibe-coding-repo`) without human approval per-WO.

## Scope

- **Repo**: `k176060444-lgtm/vibe-coding-repo` (trusted-self)
- **Batch size**: 3 Work Orders
- **Execution**: real branch / commit / push / PR / wrapper merge
- **Post-merge**: smoke / QG / V1-freeze / baseline refresh
- **Worker resilience**: preflight reachability check, checkpoint on failure

## Boundaries

| Allowed | Forbidden |
|---------|-----------|
| Low-risk docs/scripts | `.github/workflows/*` |
| Self-repo branches | External repo writes |
| Wrapper merge | Bare `gh pr merge` |
| Policy gate checks | Force push |
| Token read (self-repo only) | Token leak |

## Work Orders

1. `wo-batch-real-canary-doc-001` — this file
2. `wo-batch-real-canary-report-001` — batch runner report enhancement
3. `wo-batch-real-canary-freeze-001` — doc freeze

## Execution Model

```
batch-runner preflight (worker reachability)
  → WO1: branch → commit → push → PR → wrapper merge → smoke/qg → baseline refresh
  → WO2: branch → commit → push → PR → wrapper merge → smoke/qg → baseline refresh
  → WO3: branch → commit → push → PR → wrapper merge → smoke/qg/v1 → baseline refresh
  → batch report
```

## Stop Rules

Any of these stops the batch immediately:
- smoke / QG / V1-freeze fail
- forbidden path in changed_paths
- wrapper merge fail
- worker unreachable (→ WAITING_WORKER_RECOVERY, not business failure)
- baseline mismatch
- dirty worktree

---

*V1.5.2 Resilient Trusted Self Batch Real Canary*
