# BASELINE01 Freeze Record

**Freeze SHA:** `7dceb8c8012294a1820fa2e59270af128c06d7cb`
**Final Verdict:** `BASELINE01_FINAL_CLOSURE_PASS`
**Frozen At:** 2026-06-30T01:24:30Z (PR #268 merge time)
**Freeze Author:** Operator KK

---

## PR Closure Table

| PR | Merge Commit | Scope | Status |
|---|---|---|---|
| **#265** | `daa1e8b3bc9e8d79b0024f89e17c18c81914159e` | G1 (trusted_self_loop), G2 (privileged_push), G6 (.gitignore) | ✅ MERGED |
| **#266** | `3a974dbd90674050b31aa6be1e11fa662e017547` | G3 (intake fail-closed) | ✅ MERGED |
| **#267** | `aed4921630f25e1b005adbfe6d4306aada741b9a` | G4 (provider layering) | ✅ MERGED |
| **#268** | `7dceb8c8012294a1820fa2e59270af128c06d7cb` | G5 (node model capability matrix) | ✅ MERGED |

---

## Runtime Layer Summary

| Item | Status |
|---|---|
| SOUL.md (vibedev profile) | baseline01 applied, SHA `0a6f4a2a6a43…`, 14 sections, 259 lines |
| MEMORY.md (vibedev profile) | baseline01 marker block appended, `BASELINE01_START` × 1, `BASELINE01_END` × 1 |
| Gateway restart post-replace | Operator performed manual restart of `Hermes_Gateway_vibedev` |

---

## Repo Gap Closure

| Gap | PR | Status |
|---|---|---|
| G1 — trusted_self_loop fail-closed | #265 | ✅ CLOSED |
| G2 — privileged_push self-repo requires approval | #265 | ✅ CLOSED |
| G6 — .gitignore env secrets | #265 | ✅ CLOSED |
| G3 — intake fail-closed | #266 | ✅ CLOSED |
| G4 — provider layering | #267 | ✅ CLOSED |
| G5 — node model capability matrix | #268 | ✅ CLOSED |

---

## Validation Summary

### G3 — Intake Fail-Closed

**8/8 scenarios verified `auto_approve=False` + `requires_approval=True`:**

| Scenario | auto_approve | requires_approval |
|---|---|---|
| read_only, low risk | `False` | `True` |
| read_only, high risk | `False` | `True` |
| external, medium risk | `False` | `True` |
| external, high risk | `False` | `True` |
| multi-WO batch | `False` | `True` |
| self, low risk | `False` | `True` |
| self, medium risk | `False` | `True` |
| catch-all default | `False` | `True` |

All reachable code paths return fail-closed. No auto-approval path exists.

### G4 — Provider Layering

| Check | Result |
|---|---|
| `model_pool.yaml` schema_version | `1.1` |
| `primary_alias` populated | **38/38** |
| `alias_g4` residual | **0** |
| `provider_namespace="unknown"` | **38/38** |
| `model_pool_manifest.json` SHA match | ✅ |
| `model_pool_manifest.json` size match | ✅ |

### G5 — Node Model Capability Matrix

| Check | Result |
|---|---|
| `scripts/node_model_capability.yaml` exists | ✅ |
| Nodes | `21bao`, `5bao`, `9bao` |
| Total entries | **82** |
| Entry-level fields | **12** |
| Node context expression | YAML `nodes.<node>.matrix[]` key |
| Entry-level `node` field | ❌ absent (by design — node via YAML nesting) |
| `synced` = "unknown" | ✅ 82/82 |
| `wrapper_valid` = "unknown" | ✅ 82/82 |
| `model_call_verified` = "unknown" | ✅ 82/82 |
| `operator_approved` = "unknown" | ✅ 82/82 |
| `runtime_visible` = "unknown" | ✅ 82/82 |
| `env_loaded` = "unknown" | ✅ 82/82 |
| Premature bool in runtime fields | **0** |
| Cross-ref: model_id → pool | ✅ 82/82 |
| Cross-ref: canonical_provider | ✅ 82/82 |
| Cross-ref: provider_namespace | ✅ 82/82 |
| Cross-ref: primary_alias | ✅ 82/82 |
| Cross-ref: runtime_provider per node | ✅ 82/82 |
| `G5_ENTRY_FIELDS` constant | ✅ present |
| `G5_13_FIELDS` residual | ❌ absent (renamed in revision) |

### Static Validation Suite

| Check | Result |
|---|---|
| `python -m py_compile scripts/model_pool_manager.py` | ✅ exit 0 |
| `validate-schema` | ✅ ok, v1.1, 38 models |
| `validate-backward-compat` | ✅ ok, legacy fields preserved |
| `validate-node-capability` | ✅ ok, 82 entries, unknown_rv=82, unknown_env=82 |
| `validate-node-capability --cross-full` | ✅ ok, cross-ref errors=0 |
| **`python scripts/test_model_pool_maintenance.py`** | **✅ 22/22 PASS** |

---

## Safety Summary

| Item | Status |
|---|---|
| **secret_safety** | **PASS** — no token, password, API key, SSH key, cookie, or env value in any diff, log, or report across the entire baseline01 cycle |
| Runtime probe | ❌ not performed (baseline01 is schema/registry only) |
| SSH to 5bao/9bao | ❌ not performed |
| Model calls | ❌ not performed |
| Env value reads | ❌ not performed |
| Gateway restart | ❌ not performed (operator manual restart only) |

---

## Non-Blocking Deferred Items

The following are **architectural placeholder states** in the G5 matrix. They are **not** baseline01 blockers:

| Field | Current State | Future Action |
|---|---|---|
| `runtime_visible` | `"unknown"` | Future diagnostic PR: run `list_models()` per node to populate `true`/`false` |
| `env_loaded` | `"unknown"` | Future diagnostic PR: check actual env variable presence per node |
| `operator_approved` | `"unknown"` | Future work: operator explicitly approves each model per node |

These fields are set to `"unknown"` by design to prevent premature `true`/`false` claims without runtime evidence. G5 registry schema is complete; population is deferred to subsequent diagnostic phases.

---

## Final Statement

> **baseline01 is the accepted frozen baseline for the Vibe Coding Agent 小集群.**
>
> All seven remediation points (SOUL/MEMORY runtime + G1 through G6) have been implemented, merged, and verified on `github/main` at SHA `7dceb8c8012294a1820fa2e59270af128c06d7cb`. Subsequent work shall reference this freeze record as the baseline against which changes are measured.
>
> No further modifications to baseline01 scope are permitted without a new operator-approved baseline cycle.
