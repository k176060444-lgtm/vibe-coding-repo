# G-L3R D4 Clean-Main Live Evidence Summary

**Status**: Read-only evidence archive — `G_L3R_D4_CLEAN_MAIN_LIVE_EVIDENCE_2OF3_PASS`, `G_L3R_D4_NOT_3OF3`, `G_L3R_BLOCKER_REMAINS_PARTIALLY_OPEN_FOR_21BAO`
**Scope Constraints**: `not-G-L3R_BLOCKED_resolved` / `not-G-L4-ready` / `not-readiness-ready` / `not-model_call_verified-ready`
**Anchor**: `09b1d97f0cab774e3eb023c9768a40d8165a1d46`
**Collection Window**: 2026-07-03T12:35:42Z – 2026-07-03T12:35:50Z
**Operator Approval ID**: `OPERATOR-20260703-G-L3R-D4-LIVE-EVIDENCE-003`
**Created**: 2026-07-03

---

## 1. Purpose

This document archives the **clean-main sanctioned live evidence** collected for the G-L3R D4 runtime visibility blocker at anchor `09b1d97`. It is a **canonical evidence archive** of the receipts collected on 2026-07-03, replacing any earlier dirty-tree / pre-PR-#319 receipts.

**Scope constraints** (read first):
- This is **not** a `G_L3R_BLOCKED resolved` declaration
- This is **not** a G-L4 readiness signal
- This is **not** a `model_call_verified ready` signal
- This is **not** an `operator_approved` promotion
- This is **not** a NMC or `model_pool.yaml` write-back
- This is **not** an entry to G-READINESS / G-GRAY / G-D-A / G-D-B / PR-7 / Baseline03 / Stage8

## 2. Anchor State at Collection Time

| Anchor | Value | Source |
|---|---|---|
| HEAD | `09b1d97f0cab774e3eb023c9768a40d8165a1d46` | `git rev-parse HEAD` |
| local main | `09b1d97f0cab774e3eb023c9768a40d8165a1d46` | git |
| github/main | `09b1d97f0cab774e3eb023c9768a40d8165a1d46` | GitHub truth |
| origin/main | `09b1d97f0cab774e3eb023c9768a40d8165a1d46` | synced |
| Open PRs | 0 | `gh pr list` |
| Working tree | clean (tracked) | `git status` |
| stdin-pipe fix (PR #319) | merged at `8637e0e3` | git log |
| 4-way anchor | aligned | all 4 = `09b1d97` |

The collector's `_resolve_anchor()` function (PR #323) used `git rev-parse HEAD` at runtime and produced `09b1d97` for all three receipts.

## 3. Per-Node Sanctioned Live Evidence

All three receipts were collected with `operator_approval_id=OPERATOR-20260703-G-L3R-D4-LIVE-EVIDENCE-003` and pass `redaction_status=redacted=false, redacted_count=0`, `leak_scan=passed`, and all six `forbidden_operation_flags=False`.

### 3.1 21bao (Local Read-Only)

| Field | Value |
|---|---|
| `node` | `21bao` |
| `collector_mode` | `21bao_local_sanctioned_read` |
| `target_model` | `deepseek-v4-pro` |
| `canonical_model_id` | `opencode-go-deepseek-v4-pro` |
| `provider_namespace` | `opencode-go` |
| **`runtime_visible_observed`** | **`false`** |
| `runtime_visible_source` | `21bao_local_nmc` |
| `config_visible_observed` | `true` |
| `wrapper_visible_observed` | `true` |
| `env_loaded_observed_enum` | `config_only` |
| `credential_status_observed_enum` | `not_checked` |
| `endpoint_ref_observed_enum` | `not_checked` |
| `collection_status` | `completed` |
| **Receipt SHA256** | `161a63bfb542ef5887437d1d3da6153282a76957e7ce68a77e6b2abd55e9155a` |
| **Receipt Bytes** | `1415` |

**Interpretation**: 21bao is local-exec/control node. Local NMC reports `runtime_visible=unknown` for `opencode-go-deepseek-v4-pro` because 21bao's local OpenCode config nests this model under `deepseek-plan` provider, not `opencode-go`. This is the documented R8 residual (see `g-l3r-d4-21bao-namespace-asymmetry.md`). 21bao is **not** a blocker closure participant.

### 3.2 5bao (Sanctioned SSH Read-Only)

| Field | Value |
|---|---|
| `node` | `5bao` |
| `collector_mode` | `5bao_sanctioned_ssh_read` |
| SSH endpoint | enum ref: `5bao_ssh_opencode_config` (host:port: `192.168.5.6:22222`, IP-only, no hostname) |
| `target_model` | `deepseek-v4-pro` |
| **Receipt SHA256** | `276282ec5a8fe827671df7af2bee1547621cb3418190b5a8fa10ff67d27bec92` |
| **Receipt Bytes** | `1395` |
| `collection_status` | `completed` |
| `runtime_visible_source` | `5bao_ssh_opencode_config` |
| `runtime_visible_observed` | `true` (raw value in receipt, not in this summary) |

**Interpretation**: 5bao's `opencode.jsonc` (via sanctioned SSH read-only, script-piped via stdin per PR #319) confirms the D4 model is present in the local OpenCode configuration. **Real receipt on disk; field value preserved in `.hermes/evidence/g-l3r-d4-clean-main-v1/5bao-receipt.json`.**

### 3.3 9bao (Sanctioned SSH Read-Only)

| Field | Value |
|---|---|
| `node` | `9bao` |
| `collector_mode` | `9bao_sanctioned_ssh_read` |
| SSH endpoint | enum ref: `9bao_ssh_opencode_config` (host:port: `192.168.9.6:22222`, IP-only, no hostname) |
| `target_model` | `deepseek-v4-pro` |
| **Receipt SHA256** | `82251a651455202752a36bce1b6db54d7f01f226f7529ef57a593e49c6ae651e` |
| **Receipt Bytes** | `1395` |
| `collection_status` | `completed` |
| `runtime_visible_source` | `9bao_ssh_opencode_config` |
| `runtime_visible_observed` | `true` (raw value in receipt, not in this summary) |

**Interpretation**: 9bao's `opencode.jsonc` (via sanctioned SSH read-only) confirms D4 model is present. **Real receipt on disk; field value preserved in `.hermes/evidence/g-l3r-d4-clean-main-v1/9bao-receipt.json`.**

## 4. Verdict

| Verdict | Value | Meaning |
|---|---|---|
| `evidence_status` | `G_L3R_D4_CLEAN_MAIN_LIVE_EVIDENCE_2OF3_PASS` | 2 of 3 nodes show D4 `runtime_visible_observed=true` on clean main at anchor `09b1d97` |
| `blocker_status` | `G_L3R_D4_NOT_3OF3` | 21bao is `runtime_visible_observed=false` |
| `blocker_state` | `G_L3R_BLOCKER_REMAINS_PARTIALLY_OPEN_FOR_21BAO` | 5bao/9bao evidence is canonical; 21bao residual is R8-documented, not a new defect |

**What this verdict does NOT do**:
- ❌ Does not assert `G_L3R_BLOCKED resolved` (5bao/9bao only)
- ❌ Does not assert G-L4 ready / readiness ready
- ❌ Does not promote `model_call_verified` or `operator_approved`
- ❌ Does not write back to NMC or `model_pool.yaml`
- ❌ Does not enable any new namespace
- ❌ Does not authorize G-READINESS / G-GRAY / G-D-A / G-D-B / PR-7 / Baseline03 / Stage8

## 5. Self-Check and Test Results

| Test | Result |
|---|---|
| `python scripts/worker_attest_layer3_d4_sanctioned_live_evidence.py --self-check` | ✅ passed, 23/23 fields, 0 errors |
| `python -m pytest tests/ -q -k "d4 or worker_attest or g_l3r or opencode or preflight or policy_lock"` | ✅ 1004 passed, 1 skipped |
| Negative test: 21bao + SSH mode | ✅ not_collected |
| Negative test: 5bao + no approval_id | ✅ not_collected |
| Negative test: 9bao + wrong mode (21bao mode) | ✅ not_collected |

**Tests not re-run in this PR creation round** (already passed in previous clean-main live evidence round):
- D4 preflight: passed in previous round
- G-L3R aggregate / reconciliation: passed in previous round
- DA/DB policy-lock: passed in previous round
- Stage4/Stage7 gates: passed in previous round
- worker_attest collector/e2e/plan: passed in previous round

## 6. Leak Scan (CP7 / Secret / Path / URL)

| Scan | Result |
|---|---|
| `_leak_scan` on evidence | ✅ 0 matches |
| `_leak_scan` on receipt | ✅ 0 matches |
| `SUSPICIOUS_PATTERNS` (sk-/ghp_/Bearer/AKIA/Private key/basic-auth URL) | ✅ 0 hits |
| Endpoint as enum/ref only (`5bao_ssh_opencode_config` / `9bao_ssh_opencode_config` / `21bao_local_nmc`) | ✅ |
| Hostname fallback | ❌ none (IP-only: 192.168.5.6:22222, 192.168.9.6:22222) |
| Secret value / raw token / raw env value / private key / basic-auth URL | ❌ none present |

## 7. Forbidden Operation Checklist

| Operation | Performed | Status |
|---|---|---|
| Modify `model_pool.yaml` | ❌ | ✅ not performed |
| Modify NMC | ❌ | ✅ not performed |
| `runtime_visible` / `env_loaded` / `model_call_verified` / `operator_approved` promotion | ❌ | ✅ not performed |
| Model inference / model call | ❌ | ✅ not performed |
| Credential provisioning | ❌ | ✅ not performed |
| Node sync apply | ❌ | ✅ not performed |
| Re-SSH collection (post-summary) | ❌ | ✅ not performed |
| G-L4 / G-READINESS / G-GRAY / G-D-A / G-D-B / PR-7 / Baseline03 / Stage8 | ❌ | ✅ not advanced |

## 8. Pointer References

| Reference | Path |
|---|---|
| 21bao receipt | `.hermes/evidence/g-l3r-d4-clean-main-v1/21bao-receipt.json` |
| 5bao receipt | `.hermes/evidence/g-l3r-d4-clean-main-v1/5bao-receipt.json` |
| 9bao receipt | `.hermes/evidence/g-l3r-d4-clean-main-v1/9bao-receipt.json` |
| Closure verdict (machine-readable) | `.hermes/evidence/g-l3r-d4-clean-main-closure.json` |
| Test for digest+verdict | `tests/test_g_l3r_d4_clean_main_evidence_v1.py` |
| D4 collector | `scripts/worker_attest_layer3_d4_sanctioned_live_evidence.py` |
| stdin-pipe fix (PR #319) | merge `8637e0e3` |
| Dynamic anchor (PR #323) | merge `01c6751` |
| 21bao asymmetry residual (PR #324) | `docs/baseline02/g-l3r-d4-21bao-namespace-asymmetry.md` |
| G-L3R closeout doc | `docs/baseline02/g-l3r-closeout.md` |
| Baseline02 anchor | `docs/baseline02/00-current-anchor.md` |

## 9. Versioning

| Field | Value |
|---|---|
| Anchor | `09b1d97f0cab774e3eb023c9768a40d8165a1d46` |
| Phase | Baseline02 / G-L3R D4 (clean-main evidence archive) |
| Lifecycle | evidence archive — not-readiness, not-G-L4, not-gray, not-Baseline03, not-readiness-ready, not-model_call_verified-ready |
| Created | 2026-07-03 |
