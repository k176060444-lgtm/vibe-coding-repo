# I17 — opencode-go Enable Strategy Assessment

**Date:** 2026-06-27
**Phase:** v1.21.33I17_OPENCODE_GO_METADATA_AND_SELECTION_RFC
**Base HEAD:** `87a365df9db57d6d6a7499c3711814bc24a4d7dc`

## Canary Status (Unchanged — not affected by I17)

The sole currently enabled opencode-go model remains:

| Model | Canary Alias | Enabled | Status |
|-------|-------------|:-------:|:------:|
| `opencode-go-deepseek-v4-flash` | `opencode-ds4flash` | ✅ | Live verified 2/2 |

## Candidate Models for Next Enable

All 8 opencode-go models are live verified (I16E, 16/16 PASS). Below are candidates for
the next model to enable, ranked by recommendation.

### Rank 1: `opencode-go-mimo-v2-5` (alias `opencode-mimo`)

| Criterion | Assessment |
|-----------|-----------|
| Live verified | ✅ 2/2 PASS (5bao + 9bao) |
| Cost | free |
| Capability | coding |
| Weight | 1 (lightweight model, faster responses) |
| Risk | Low — narrowly scoped, well-tested model |
| Use case | Tester-A or Tester-B role candidate; small/fast tasks |
| **Recommendation** | ✅ **Enable next** after operator approval |

**Reasoning:** Mimo-v2.5 is the cheapest, fastest model in the opencode-go pool.
It scored exact match on both nodes with zero fallback. Ideal for tester/reviewer
roles that don't need strong reasoning.

### Rank 2: `opencode-go-qwen3-7-max` (alias `opencode-qwen37max`)

| Criterion | Assessment |
|-----------|-----------|
| Live verified | ✅ 2/2 PASS (5bao + 9bao) |
| Cost | free |
| Capability | strong |
| Use case | Reviewer-B or implementer-small candidate |
| **Recommendation** | ⏳ Wait — evaluate after mimo-v2.5 enable |

### Rank 3: `opencode-go-glm-5-2` / `opencode-go-glm-5-1`

| Criterion | Assessment |
|-----------|-----------|
| Live verified | ✅ 2/2 PASS (5bao + 9bao) |
| Risk | Low — same provider, same API |
| **Recommendation** | ⏳ Wait — lower priority than mimo/qwen |

### Not Recommended for Enable

| Model | Reason |
|-------|--------|
| `opencode-go-kimi-k2-6` | No clear role differentiation |
| `opencode-go-qwen3-7-plus` | Too similar to qwen3.7-max (max is the flagship) |
| `opencode-go-mimo-v2-5-pro` | Higher cost than mimo-v2.5 with marginal gain |

## Enable Procedure (for next phase, not I17)

```yaml
required_operator_approval: true
steps:
  1. Operator selects model to enable
  2. I17-style PR: set enabled=true in model_pool.yaml
  3. Run: model_pool self-check, route-all unchanged, tests, secret check
  4. Push branch, create PR
  5. Merge gate → merge PR
  6. Optional: live re-verify (not required, already verified)
```

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|:-----------:|:------:|------------|
| Model fails at runtime | Low | Medium | Auto-fallback to enabled model; route-all unchanged |
| Cost increase | Low | Low | opencode-go models are free-tier |
| Extra visible models confusion | Low | Low | Documented in I16F audit record; excluded from alias/route |

## Operator Decision Required

**Question:** Which model should be the second enabled opencode-go model?
Options: `opencode-go-mimo-v2-5` (recommended), `opencode-go-qwen3-7-max`, or other.
