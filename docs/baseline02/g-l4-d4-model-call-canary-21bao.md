# G-L4 D4 — 21bao Model-Call Canary Evidence

## Status

| Field | Value |
|---|---|
| **Gate ID** | `G-L4-D4-MODEL-CALL-CANARY-21BAO` |
| **Operator Authorization** | `OPERATOR-20260704-G-L4-D4-MODEL-CALL-VERIFY-CANARY-21BAO` |
| **Anchor** | `6daa7ee081f610b014f6234c27f45c809f0018fb` |
| **Canary Verdict** | `G_L4_D4_21BAO_CANARY_PASS` (exit=0, marker detected) |
| **Created** | 2026-07-04 |

## Scope

This evidence documents a **bounded single-node model-call canary** on 21bao.
It is NOT a G-L4 model_call_verified promotion, NOT readiness, NOT a
credential operation, and NOT an authorization for 5bao/9bao model calls.

## P16 / BLOCKER-01 Decision

The operator pre-authorized use of the existing 21bao Windows local user env
for this canary call (BLOCKER-01 resolved: accept existing env without wrapper).

| Authority | Value |
|---|---|
| **Authorization ID** | `G-L4-D4-MODEL-CALL-VERIFY-CANARY-21BAO` |
| **Execution class** | `opencode.exe run --dangerously-skip-permissions -m <provider>/<model>` |
| **opencode path** | `C:\Users\KK\AppData\Local\vibedev-tools\opencode\node_modules\opencode-ai\bin\opencode.exe` |
| **opencode version** | `1.17.8` |
| **Config dir** | `~/.config/opencode/opencode.jsonc` |
| **Env loading** | Windows user env vars (inherited by MSYS git-bash session) |
| **Credential status** | `OPENCODE_GO_API_KEY=PRESENT`, `OPENCODE_GO_BASE_URL=PRESENT` |
| **Credential values** | NOT printed / redacted |

## Model Call Result

| Field | Value |
|---|---|
| **Canonical model ID** | `opencode-go-deepseek-v4-pro` |
| **Canonical provider** | `opencode-go` |
| **Concrete invocation** | `deepseek-plan/deepseek-v4-pro` |
| **Concrete provider** | `deepseek-plan` |
| **Model** | `deepseek-v4-pro` |
| **Attempt count** | 1 |
| **Fallback used** | false |
| **Model call attempted** | true |
| **Model call succeeded** | **true** |
| **Exit code** | 0 |
| **Expected marker** | `D4_CANARY_OK` |
| **Marker detected** | true |
| **Exact match** | true |
| **Duration** | ~3 seconds |
| **Timestamp** | `2026-07-04T04:53:07Z` |
| **Prompt class** | Harmless deterministic minimal |

### Risk Mitigation: `--dangerously-skip-permissions`

The canary call used `opencode.exe run --dangerously-skip-permissions` because
non-interactive mode rejects permission prompts without this flag. All
mitigations confirmed:

| Mitigation | Status |
|---|---|
| Flag used | `true` |
| Prompt class | Harmless deterministic minimal (`"Output exactly: D4_CANARY_OK"`) |
| No repo content / secrets / credentials sent | ✅ |
| No tool execution triggered | ✅ |
| No file / shell / runtime modification | ✅ |
| No extra model calls | ✅ |
| No fallback | ✅ |
| git status clean verified | ✅ |
| stdout/stderr redacted | ✅ |
| Credential values NOT printed | ✅ |

This flag was bounded to a single fixed-string prompt with zero dynamic
content, zero file references, and zero environment access. No side effects
observed.

### Important Note: opencode-go Provider Availability

The `opencode-go` provider was **NOT found** on 21bao. The D4 model was
successfully called via the **legacy `deepseek-plan/deepseek-v4-pro`** provider,
which is documented in the PR #340 preflight evidence as the legacy entry.

If the operator requires the `opencode-go` provider to be available on 21bao,
a separate provider configuration session with operator authorization is needed.

## Post-Call State (No Promotions)

| Field | Status |
|---|---|
| `model_call_verified` promoted | false |
| `operator_approved` promoted | false |
| `env_loaded` promoted | false |
| NMC / model_pool / runtime config modified | false |
| Credential provisioning performed | false |
| Node sync performed | false |
| 5bao/9bao model calls performed | false |
| G-L4 readiness entered | false |
| G-READINESS / G-GRAY / G-D-A/B / PR-7 / Baseline03 / Stage8 entered | false |

## Forbidden Claims (NOT in this evidence)

- ❌ G-L4 ready
- ❌ readiness ready
- ❌ model_call_verified ready
- ❌ operator_approved ready
- ❌ gray ready
- ❌ Baseline03 ready
- ❌ Stage8 ready
- ❌ Global `G_L3R_BLOCKED` closed
- ❌ model_call_verified promoted to any node
- ❌ 5bao or 9bao model call performed

## See Also

- `.hermes/evidence/g-l4-d4-model-call-canary-21bao-v1/21bao-receipt.json` — machine-readable receipt
- `.hermes/evidence/g-l4-d4-model-call-verification-preflight.json` — G-L4 preflight plan (PR #340)
- `docs/baseline02/g-l4-d4-model-call-verification-preflight.md` — G-L4 preflight doc
- `tests/test_g_l4_d4_model_call_canary_21bao.py` — canary evidence tests
