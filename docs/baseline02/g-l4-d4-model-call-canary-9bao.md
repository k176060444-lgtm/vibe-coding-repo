# G-L4 D4 — 9bao Model-Call Canary Evidence

## Status

| Field | Value |
|---|---|
| **Gate ID** | `G-L4-D4-MODEL-CALL-CANARY-9BAO` |
| **Operator Authorization** | `OPERATOR-20260704-G-L4-D4-MODEL-CALL-VERIFY-CANARY-9BAO` |
| **Anchor** | `7fc883b2e376307a704ec9b190c9af2cd7ef6674` |
| **Canary Verdict** | `G_L4_D4_9BAO_CANARY_PASS` (exit=0, marker detected) |
| **Created** | 2026-07-04 |

## Scope

This evidence documents a **bounded single-node model-call canary** on 9bao
(remote SSH Debian worker at 192.168.9.6:22222). It is NOT a G-L4
model_call_verified promotion, NOT readiness, NOT a credential operation,
and NOT an authorization for 21bao/5bao model calls. This is a separate
execution from PR #341 (21bao canary) and PR #342 (5bao canary).

## SSH Transport

| Authority | Value |
|---|---|
| **Node** | `9bao` |
| **Endpoint** | `192.168.9.6:22222` |
| **User** | `vibeworker` |
| **Auth method** | Publickey (debian-vibeworker-ed25519) |
| **Wrapper used** | `~/bin/vibedev-opencode` |
| **Env loading** | Wrapper sources `~/.vibedev-secrets/opencode.env` |
| **Credential status** | `OPENCODE_GO_API_KEY=PRESENT, OPENCODE_GO_BASE_URL=PRESENT` |
| **Remote config modified** | false |
| **Credential values** | NOT printed / redacted |

## Model Call Result

| Field | Value |
|---|---|
| **Canonical model ID** | `opencode-go-deepseek-v4-pro` |
| **Canonical provider** | `opencode-go` |
| **Concrete invocation** | `opencode-go/deepseek-v4-pro` (canonical — no deepseek-plan needed) |
| **Concrete provider** | `opencode-go` |
| **Model** | `deepseek-v4-pro` |
| **Attempt count** | 1 |
| **Fallback used** | false |
| **Model call attempted** | true |
| **Model call succeeded** | **true** |
| **Exit code** | 0 |
| **Expected marker** | `D4_CANARY_OK_9BAO` |
| **Marker detected** | true |
| **Exact match** | true |
| **Duration** | ~3 seconds |
| **Timestamp** | `2026-07-04T07:45:00Z` |
| **Prompt class** | Harmless deterministic minimal |

### Risk Mitigation: `--dangerously-skip-permissions`

The canary call used `~/bin/vibedev-opencode run --dangerously-skip-permissions`
because non-interactive SSH mode rejects permission prompts without this flag.
All mitigations confirmed:

| Mitigation | Status |
|---|---|
| Flag used | `true` |
| Prompt class | Harmless deterministic minimal (`"Output exactly: D4_CANARY_OK_9BAO"`) |
| No repo content / secrets / credentials sent | ✅ |
| No tool execution triggered | ✅ |
| No file / shell / runtime modification | ✅ |
| No extra model calls | ✅ |
| No fallback | ✅ |
| Credential values NOT printed | ✅ |
| Remote SSH config / authorized_keys not modified | ✅ |

### Important Note: opencode-go Provider Availability

**Unlike 21bao and 5bao**, `opencode-go/deepseek-v4-pro` **resolves correctly
on 9bao**. The call used the canonical `opencode-go` provider and `deepseek-v4-pro`
model directly, with no fallback, no alias, no alternative provider.

This is a **critical finding**: the opencode-go ProviderModelNotFoundError
observed on 21bao (PR #341) and 5bao (PR #342) is **node-specific**. 9bao
validates that opencode-go CAN work correctly when properly configured.
The failure on 21bao/5bao is a configuration gap on those nodes, not a
provider-wide limitation.

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
| 21bao/5bao model calls performed | false |
| G-L4 readiness entered | false |
| G-READINESS / G-GRAY / G-D-A/B / PR-7 / Baseline03 / Stage8 entered | false |

## Relationship to PR #341 (21bao) and PR #342 (5bao)

This 9bao canary is a **separate bounded execution** from the 21bao canary
(PR #341) and 5bao canary (PR #342). Unlike the other two nodes, 9bao
succeeds with the canonical `opencode-go` provider directly.

**Key difference:**
| Node | opencode-go/deepseek-v4-pro | Actual invocation | PR |
|:----:|:---------------------------:|:-----------------:|:--:|
| 21bao | ❌ ProviderModelNotFoundError | deepseek-plan/deepseek-v4-pro | #341 |
| 5bao  | ❌ ProviderModelNotFoundError | deepseek-plan/deepseek-v4-pro | #342 |
| 9bao  | ✅ Works directly | opencode-go/deepseek-v4-pro | #343 |

None promotes model_call_verified. All three must complete before NMC
writeback can be considered.

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
- ❌ 21bao or 5bao model call performed
- ❌ NMC writeback performed
- ❌ Node sync performed

## See Also

- `.hermes/evidence/g-l4-d4-model-call-canary-9bao-v1/9bao-receipt.json` — machine-readable receipt
- `.hermes/evidence/g-l4-d4-model-call-canary-21bao-v1/21bao-receipt.json` — PR #341 21bao canary receipt
- `.hermes/evidence/g-l4-d4-model-call-canary-5bao-v1/5bao-receipt.json` — PR #342 5bao canary receipt
- `.hermes/evidence/g-l4-d4-model-call-verification-preflight.json` — G-L4 preflight plan (PR #340)
- `tests/test_g_l4_d4_model_call_canary_9bao.py` — 9bao canary evidence tests
