# G-L4 D4 — 5bao Model-Call Canary Evidence

## Status

| Field | Value |
|---|---|
| **Gate ID** | `G-L4-D4-MODEL-CALL-CANARY-5BAO` |
| **Operator Authorization** | `OPERATOR-20260704-G-L4-D4-MODEL-CALL-VERIFY-CANARY-5BAO` |
| **Anchor** | `d78d5463daf84784778051e18578710c042a0093` |
| **Canary Verdict** | `G_L4_D4_5BAO_CANARY_PASS` (exit=0, marker detected) |
| **Created** | 2026-07-04 |

## Scope

This evidence documents a **bounded single-node model-call canary** on 5bao
(remote SSH Debian worker). It is NOT a G-L4 model_call_verified promotion,
NOT readiness, NOT a credential operation, and NOT an authorization for
21bao/9bao model calls. This is a separate execution from PR #341 (21bao canary).

## SSH Transport

| Authority | Value |
|---|---|
| **Node** | `5bao` |
| **Endpoint** | `192.168.5.6:22222` |
| **User** | `vibeworker` |
| **Auth method** | Publickey (debian-vibeworker-ed25519) |
| **Wrapper used** | `~/bin/vibedev-opencode` |
| **Env loading** | Wrapper sources `~/.vibedev-secrets/opencode.env` |
| **Remote config modified** | false |
| **Credential values** | NOT printed / redacted |

## Model Call Result

| Field | Value |
|---|---|
| **Canonical model ID** | `opencode-go-deepseek-v4-pro` |
| **Canonical provider** | `opencode-go` |
| **Concrete invocation** | `deepseek-plan/deepseek-v4-pro` (via `~/bin/vibedev-opencode` wrapper) |
| **Concrete provider** | `deepseek-plan` |
| **Model** | `deepseek-v4-pro` |
| **Attempt count** | 1 |
| **Fallback used** | false |
| **Model call attempted** | true |
| **Model call succeeded** | **true** |
| **Exit code** | 0 |
| **Expected marker** | `D4_CANARY_OK_5BAO` |
| **Marker detected** | true |
| **Exact match** | true |
| **Duration** | ~3 seconds |
| **Timestamp** | `2026-07-04T06:01:57Z` |
| **Prompt class** | Harmless deterministic minimal |

### Risk Mitigation: `--dangerously-skip-permissions`

The canary call used `~/bin/vibedev-opencode run --dangerously-skip-permissions`
because non-interactive SSH mode rejects permission prompts without this flag.
All mitigations confirmed:

| Mitigation | Status |
|---|---|
| Flag used | `true` |
| Prompt class | Harmless deterministic minimal (`"Output exactly: D4_CANARY_OK_5BAO"`) |
| No repo content / secrets / credentials sent | ✅ |
| No tool execution triggered | ✅ |
| No file / shell / runtime modification | ✅ |
| No extra model calls | ✅ |
| No fallback | ✅ |
| Credential values NOT printed | ✅ |
| Remote SSH config / authorized_keys not modified | ✅ |

### Important Note: opencode-go Provider Availability (Namespace Asymmetry)

The `opencode-go/deepseek-v4-pro` model IS listed in the wrapper's model list
(`~/bin/vibedev-opencode models`), but the runtime call fails with
`ProviderModelNotFoundError`. The D4 model was successfully called via
`deepseek-plan/deepseek-v4-pro`.

This is the **same namespace asymmetry pattern observed on 21bao** (PR #341):
the `opencode-go` provider configuration on this node does not correctly resolve
`deepseek-v4-pro` as a callable model, even though the entry exists in
`opencode.jsonc`. This is NOT a fallback, NOT a model switch, NOT provider
drift — it is a documented configuration gap affecting both nodes.

## Post-Call State (No Promotions)

| Field | Status |
|---|---|
| `model_call_verified` promoted | false |
| `operator_approved` promoted | false |
| `env_loaded` promoted | false |
| NMC / model_pool / runtime config modified | false |
| Credential provisioning performed | false |
| Node sync performed | false |
| SSH config / authorized_keys modified | false |
| 21bao/9bao model calls performed | false |
| G-L4 readiness entered | false |
| G-READINESS / G-GRAY / G-D-A/B / PR-7 / Baseline03 / Stage8 entered | false |

## Relationship to PR #341 (21bao Canary)

This 5bao canary is a **separate bounded execution** from the 21bao canary
(PR #341). Both exhibit the same namespace asymmetry (opencode-go provider
configuration issue). Neither promotes model_call_verified.

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
- ❌ 21bao or 9bao model call performed

## See Also

- `.hermes/evidence/g-l4-d4-model-call-canary-5bao-v1/5bao-receipt.json` — machine-readable receipt
- `.hermes/evidence/g-l4-d4-model-call-canary-21bao-v1/21bao-receipt.json` — PR #341 21bao canary receipt
- `.hermes/evidence/g-l4-d4-model-call-verification-preflight.json` — G-L4 preflight plan (PR #340)
- `tests/test_g_l4_d4_model_call_canary_5bao.py` — 5bao canary evidence tests
