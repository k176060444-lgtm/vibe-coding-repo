# NMC Staleness Analysis — G-L3R D4

## 1. Background

The Node Model Capability (NMC) file `scripts/node_model_capability.yaml` is a generated inventory of model capability per node. It was last generated at:

```
generated_at: 2026-07-01T01:10:40.387122+00:00
```

The G-L3R D4 fix cycle (PRs #319–#327) was executed on **2026-07-03**, approximately 2 days after the NMC was generated. The NMC therefore reflects the cluster state **before** the D4 fixes and live evidence collection.

## 2. D4 Closeout Evidence

The G-L3R D4 runtime visibility blocker was closed per operator-approved PR #322. The closure verdict `BASELINE02_G_L3R_D4_CLOSEOUT_COMPLETE_NOT_READINESS` is based on:

- **Live evidence receipts** collected on **2026-07-03** at clean-main anchor `baad421`
- Not on NMC data

The live evidence showed:

| Node | runtime_visible_observed | Source |
|---|---|---|
| **5bao** | `true` | v3 clean-main sanctioned receipt |
| **9bao** | `true` | v3 clean-main sanctioned receipt |
| **21bao** | `false` | v3 clean-main sanctioned receipt (non_blocking_residual, see R8/PR #324) |

## 3. NMC Coverage Summary (as of 2026-07-01)

All 3 nodes (21bao, 5bao, 9bao) have identical NMC coverage:

| Metric | Count |
|---|---|
| Total entries per node | 25 |
| `runtime_visible=true` | 8 |
| `runtime_visible=false` | 0 |
| `runtime_visible=unknown` | 17 |
| `model_call_verified=true` | 1 |
| `operator_approved=true` | 1 |
| `wrapper_valid=true` | 25 |
| `env_loaded=true` | 11 |
| `env_loaded=unknown` | 14 |

The 8 `runtime_visible=true` models are all `opencode-go-*` models (deepseek-v4-flash, glm-5-1, glm-5-2, kimi-k2-6, mimo-v2-5, mimo-v2-5-pro, qwen3-7-max, qwen3-7-plus).

## 4. Classification of `runtime_visible=unknown` Entries

The 17 unknown entries per node fall into two distinct categories:

### Category A: `declared_enabled_unassigned` (16/17 per node)

These models are declared in the central `model_pool.yaml` with `lifecycle=declared_enabled_unassigned` and `allowed_nodes=[]`. They have not been operator-assigned to any worker node.

| Provider | Models |
|---|---|
| anthropic | claude-3-5-haiku-20241022, claude-opus-4, claude-sonnet-4 |
| dashscope | qwen-max, qwen-plus |
| deepseek | deepseek-coder, deepseek-reasoner |
| google | gemini-2-5-flash, gemini-2-5-pro |
| moonshot | moonshot-v1-128k |
| openai | gpt-4o, o1, o3, o3-mini, o4-mini |
| xai | grok-3 |

**NMC `runtime_visible=unknown` is the correct state** for these models. They have not been assigned to any node, so runtime visibility cannot be verified. Node assignment and operator approval would happen in a future phase (G-D-A/G-D-B).

### Category B: D4 Model (1/17 per node)

| Node | Model | Pool Lifecycle | Allowed |
|---|---|---|---|
| 21bao | `opencode-go-deepseek-v4-pro` | `enabled_assigned` | [5bao, 9bao, 21bao] |
| 5bao | `opencode-go-deepseek-v4-pro` | `enabled_assigned` | [5bao, 9bao, 21bao] |
| 9bao | `opencode-go-deepseek-v4-pro` | `enabled_assigned` | [5bao, 9bao, 21bao] |

This model is `enabled_assigned` (operator-assigned) and explicitly allowed on all 3 nodes. However, the NMC reports `runtime_visible=unknown` for all 3 because:

- **5bao/9bao**: NMC was generated before the D4 live evidence collection. The live receipts showed `runtime_visible_observed=true`, but the NMC has not been regenerated to reflect this.
- **21bao**: The `runtime_visible_observed=false` residual (documented in R8/PR #324) is correct — 21bao has a provider namespace asymmetry (central `opencode-go` vs local `deepseek-plan`).

**This is a known and accepted NMC staleness vs live evidence mismatch.** The D4 closure was correctly based on live evidence, not NMC.

## 5. Cross-Reference: Pool Models Not in NMC

Several models exist in `model_pool.yaml` with `allowed_nodes` set but are **not present** in the NMC matrix:

### Missing from 21bao NMC (3 models)

All are `enabled=false` with `lifecycle=historical` — correctly excluded:

- `xiaomi-mimo-v2-5-payg`
- `xiaomi-mimo-v2-5-pro`
- `xiaomi-mimo-v2-5-pro-payg`

### Missing from 5bao/9bao NMC (13 models)

All are `enabled=false` with lifecycles of `disabled`, `candidate`, `historical`, or `remove_pending` — correctly excluded:

| Model | Lifecycle |
|---|---|
| `deepseek-deepseek-chat` | disabled |
| `deepseek-plan-deepseek-v4-pro` | candidate |
| `minimax-minimax-m2-5` | historical |
| `minimax-plan-minimax-m3` | candidate |
| `opencode-big-pickle` | remove_pending |
| `opencode-deepseek-v4-flash-free` | remove_pending |
| `opencode-mimo-v2-5-free` | remove_pending |
| `opencode-nemotron-3-ultra-free` | remove_pending |
| `opencode-north-mini-code-free` | remove_pending |
| `volcengine-doubao-1-5-pro-256k` | candidate |
| `xiaomi-mimo-v2-5-payg` | historical |
| `xiaomi-mimo-v2-5-pro` | historical |
| `xiaomi-mimo-v2-5-pro-payg` | historical |

No active models are missing from NMC. All absences are consistent with their pool lifecycle status.

## 6. Key Findings

| Finding | Severity | Notes |
|---|---|---|
| NMC generated before D4 fix cycle | Informational | 2026-07-01 vs 2026-07-03 evidence collection |
| 5bao/9bao NMC says unknown, live says true | **Stale — not a defect** | D4 closure used live evidence; NMC needs regeneration |
| 21bao NMC says unknown, live says false | **Known residual (R8)** | Documented provider namespace asymmetry |
| 16/17 unknown = declared_enabled_unassigned | **Expected state** | Correct for unassigned models |
| No active pool models missing from NMC | **Consistent** | All absences explained by lifecycle |

## 7. Scope Constraints

This analysis is explicitly **NOT** any of the following:

- ❌ **not-readiness** — NMC staleness is a documentation observation, not a readiness gate.
- ❌ **not-G-L4** — NMC regeneration or coverage expansion would be a separate phase.
- ❌ **not-gray** — Gray is outside Baseline02 scope.
- ❌ **not-Baseline03** — Baseline03 is a future phase not yet authorized.

## 8. Forbidden Interpretations

1. **NMC staleness does not mean D4 closure failed.** The D4 closeout was correctly based on live evidence, and the verdict `CLOSED_BY_5BAO_9BAO` stands.
2. **Do not auto-promote unknown to true.** Expanding runtime coverage or regenerating NMC requires a new operator decision.
3. **Do not use this analysis as readiness evidence.** Documenting a known gap does not imply the gap has been closed.

## 9. Forward Path (for reference, not action)

If NMC regeneration or runtime coverage expansion is desired in a future operator-authorized phase:

1. **Regenerate NMC** from current `model_pool.yaml` after any evidence collection
2. **Re-collect live evidence** for the specific model(s) being added
3. **Update G-L3R closeout** if necessary
4. **Operator sign-off** for any promotion
5. **No phase escalation** — NMC maintenance is not a substitute for phase authorization

## 10. Pointer References

| Reference | Path |
|---|---|
| NMC source | `scripts/node_model_capability.yaml` |
| Model pool source | `scripts/model_pool.yaml` |
| G-L3R closeout | `docs/baseline02/g-l3r-closeout.md` |
| 21bao asymmetry docs | `docs/baseline02/g-l3r-d4-21bao-namespace-asymmetry.md` |
| D4 closure evidence | `.hermes/evidence/g-l3r-d4-runtime-visible-blocker-closed.json` |
| D4 receipts (21bao/5bao/9bao) | `.hermes/evidence/g-l3r-d4-receipt-*-v3.json` |
| D4 collector | `scripts/worker_attest_layer3_d4_sanctioned_live_evidence.py` |

## 11. Versioning

| Field | Value |
|---|---|
| Anchor | `4bd173e6ec2c3704acbe82e1ba1470bc38dda3e8` |
| Phase | Baseline02 |
| Lifecycle | documentation — not-readiness, not-G-L4, not-gray, not-Baseline03 |
| Last updated | 2026-07-03 |
