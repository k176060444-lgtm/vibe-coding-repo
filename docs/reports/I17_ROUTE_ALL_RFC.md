# I17 — Route-All opencode-go Evaluation RFC

**Date:** 2026-06-27
**Phase:** v1.21.33I17_OPENCODE_GO_METADATA_AND_SELECTION_RFC
**Base HEAD:** `87a365df9db57d6d6a7499c3711814bc24a4d7dc**

## Current Route-All (9 roles, unchanged)

| Role | Current Model | Current Node |
|------|--------------|:------------:|
| orchestrator | volcengine-doubao | 21bao |
| explorer | minimax-m3 | 5bao |
| planner | volcengine-doubao | 21bao |
| implementer | minimax-m3 | 5bao |
| tester-a | minimax-m3 | 5bao |
| tester-b | minimax-m3 | 9bao |
| reviewer-a | minimax-m3 | 9bao |
| reviewer-b | minimax-m3 | 21bao |
| git-integrator | minimax-m3 | 21bao |

**Note:** `minimax-m3` is the plan-tier `minimax-plan/MiniMax-M3` model,
NOT the extra visible `opencode-go/minimax-m3`.

## Candidate Roles for opencode-go Adoption

### Candidate A: Tester-B → opencode-go/deepseek-v4-flash

| Criterion | Assessment |
|-----------|-----------|
| Current model | `minimax-plan/MiniMax-M3` on 9bao |
| Proposed model | `opencode-go/deepseek-v4-flash` on 9bao |
| Risk | Low — same node (9bao), same transport |
| Benefit | Frees minimax-m3 capacity for other roles |
| Fallback | If opencode-go fails, route back to minimax-m3 |
| **Recommendation** | ⏳ **Consider but wait** — after mimo-v2.5 enable is stable |

**Concerns:**
1. opencode-go is a separate provider (different key/env)
2. Currently relies on correctly injected OPENCODE_GO_API_KEY
3. Already verified working (I16E 2/2 on 9bao)

### Candidate B: Reviewer-A → opencode-go/qwen3.7-max

| Criterion | Assessment |
|-----------|-----------|
| Current model | `minimax-plan/MiniMax-M3` on 9bao |
| Proposed model | `opencode-go/qwen3.7-max` on 9bao |
| Risk | Medium — reviewer role requires reliable output |
| Benefit | Diverse reviewer model (= stronger review quality) |
| **Recommendation** | ⏳ **Wait** — enable opencode-go first, gather telemetry |

### Candidate C: Tester-A → opencode-go/mimo-v2.5

| Criterion | Assessment |
|-----------|-----------|
| Current model | `minimax-plan/MiniMax-M3` on 5bao |
| Proposed model | `opencode-go/mimo-v2.5` on 5bao |
| Risk | Low — lighter model, lower cost |
| Benefit | Faster test execution, lower cost |
| **Recommendation** | ⏳ **Wait** — mimo-v2.5 not yet enabled |

## Rollback Plan

If any role's opencode-go model fails:

```yaml
rollback:
  action: Revert route-all assignment to original model
  method: route-all dry-run with --override + PR
  duration: < 5 minutes (PR + merge)
  fallback_during_rollback: Tester/Reviewer uses minimax-m3
```

## Verification Requirements (for any role change)

1. Route-all dry-run → confirm intended change
2. Live smoke for the specific model on the target node
3. Run test suite with the new route-all assignment
4. Tag-team test: both old and new model produce PASS
5. Operator approval before final switch

## Operator Decision Required

**Question:** Should any route-all role be upgraded to use an opencode-go model?
Options: Keep current (stable), candidate A (tester-b), candidate C (tester-a), or other.
