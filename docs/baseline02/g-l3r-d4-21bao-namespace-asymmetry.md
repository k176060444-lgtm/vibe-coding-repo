# G-L3R D4 — 21bao Provider Namespace Asymmetry Residual

**Status**: NON-BLOCKING RESIDUAL — Recorded for future reference
**Scope**: Baseline02 / G-L3R — D4 runtime visibility evidence phase
**Anchor**: `01c6751e949b4996aeb2b6ba945fbca1b3ff62f8` (PR #323 merge)
**Classification**: `not-readiness / not-G-L4 / not-gray / not-Baseline03`

---

## 1. Background — D4 closure is already complete

G-L3R D4 (`runtime_visible` blocker for `deepseek-v4-pro`) was officially closed
via PR #322 (`evidence: close G-L3R D4 runtime visibility blocker`) and is
recorded as merged in `.hermes/evidence/g-l3r-d4-runtime-visible-blocker-closed.json`.

The closure was based on **2-of-3 nodes** satisfying the D4 visibility gate,
where 5bao and 9bao clean-main sanctioned receipts both show
`runtime_visible_observed=true`:

| Node | `runtime_visible_observed` | `runtime_visible_source`            | Closure role       |
|------|-----------------------------|--------------------------------------|--------------------|
| 5bao | `true`                      | `5bao_ssh_opencode_config`           | closure_evidence   |
| 9bao | `true`                      | `9bao_ssh_opencode_config`           | closure_evidence   |
| 21bao | `false`                    | `21bao_local_nmc`                    | non_blocking_residual |

Closure status fields (PR #322):

- `preflight_verdict`: `G_L3R_D4_PREFLIGHT_PASS_SANCTIONED_EVIDENCE`
- `blocker_status`: `CLOSED_BY_5BAO_9BAO`
- `aggregate_status`: `G_L3R_D4_RUNTIME_VISIBLE_BLOCKER_CLOSED`
- `reconciliation_verdict`: `G_L3R_RECONCILIATION_PASS_D4_CLOSED`

This residual does **not** reopen the D4 closure.

---

## 2. 21bao residual classification

21bao was explicitly classified as `non_blocking_residual` in the closure evidence
with the documented reason:

> "NMC `runtime_visible` is `'unknown'` (string), not `True`. Requires operator
> promotion or NMC update."

The remaining values for 21bao in the D4 receipt are all healthy:

| Field                       | Value         | Notes                                    |
|-----------------------------|---------------|------------------------------------------|
| `runtime_visible_observed`  | `false`       | Driven by NMC `runtime_visible: unknown` |
| `config_visible_observed`   | `true`        | `~/.config/opencode/opencode.jsonc` exists |
| `wrapper_visible_observed`  | `true`        | NMC `wrapper_valid: true`                |
| `env_loaded_observed_enum`  | `config_only` | env files not present, config-only       |
| `collection_status`         | `completed`   | Sanctioned read succeeded                |

---

## 3. Why 21bao shows `runtime_visible=false`

### 3.1 NMC data (primary)

In `scripts/node_model_capability.yaml`, the 21bao matrix entry for
`opencode-go-deepseek-v4-pro` reads:

```yaml
- model_id: opencode-go-deepseek-v4-pro
  canonical_provider: opencode-go
  provider_namespace: opencode-go
  primary_alias: opencode-ds4pro
  runtime_provider: opencode-go
  declared: true
  synced: true
  wrapper_valid: true
  model_call_verified: unknown
  operator_approved: unknown
  runtime_visible: unknown       # <-- string "unknown", not boolean True
  env_loaded: true
```

The D4 collector's logic for 21bao is purely data-driven
(`scripts/worker_attest_layer3_d4_sanctioned_live_evidence.py`,
function `_build_receipt`):

```python
runtime_visible_observed = any(
    e.get("runtime_visible") is True for e in nmc_entries
)
```

The value `"unknown"` is a string and does **not** match `is True`. This is the
single point that causes `runtime_visible_observed=false` on 21bao. The
collector itself is correct; the NMC data is the source of the residual.

### 3.2 21bao local OpenCode config (local namespace reality)

21bao's `~/.config/opencode/opencode.jsonc` (the only config file present;
`opencode.json`, `config.json`, `opencode.env`, and `~/.opencode/bin/opencode`
are all absent) defines four provider blocks:

| Provider block      | Models                                            | Notes                  |
|---------------------|---------------------------------------------------|------------------------|
| `deepseek-plan`     | `deepseek-v4-flash`, `deepseek-v4-pro`            | **D4 model present**   |
| `volcengine-plan`   | `ark-code-latest`                                 | unrelated              |
| `xiaomi-plan`       | `mimo-v2.5`, `mimo-v2.5-pro`                      | unrelated              |
| `minimax-plan`      | `MiniMax-M3`                                      | unrelated              |

**Crucially absent**: there is **no `opencode-go` provider block** on 21bao. The
model `deepseek-v4-pro` is present locally, but it is nested under
`deepseek-plan`, not under `opencode-go`.

### 3.3 Central model_pool canonical namespace (central namespace)

In `scripts/model_pool.yaml`, the canonical entry for the active D4 model is:

```yaml
- id: opencode-go-deepseek-v4-pro
  alias: [opencode-ds4pro, opencode-deepseek-v4-pro]
  provider: opencode-go
  model: deepseek-v4-pro
  enabled: true
  allowed_nodes: [5bao, 9bao, 21bao]
  smoke_results:
    5bao: { status: confirmed, wrapper: ~/bin/vibedev-opencode, invocation: opencode-go/deepseek-v4-pro }
    9bao: { status: confirmed, wrapper: ~/bin/vibedev-opencode, invocation: opencode-go/deepseek-v4-pro }
    # 21bao has NO smoke_results — not tested at the canonical namespace
  lifecycle_status: enabled_assigned
  canonical_provider: opencode-go
  provider_namespace: opencode-go
```

The legacy entry `deepseek-plan-deepseek-v4-pro` exists with `enabled: false`,
`lifecycle_status: candidate`, and `allowed_nodes: [5bao, 9bao]` only — it is
not the active D4 model.

---

## 4. The asymmetry — central namespace vs local namespace

The D4 model `deepseek-v4-pro` is represented under two different provider keys
across the cluster. This is the namespace asymmetry that gives 21bao its
residual status:

| Layer                  | Namespace        | Where it appears                                            |
|------------------------|------------------|-------------------------------------------------------------|
| Central model_pool     | `opencode-go`    | `opencode-go-deepseek-v4-pro` (canonical, enabled)          |
| 21bao local config     | `deepseek-plan`  | `provider.deepseek-plan.models.deepseek-v4-pro`             |
| 5bao/9bao local config | `deepseek-plan`  | `provider.deepseek-plan.models.deepseek-v4-pro` (PR #319 fix) |

`opencode-go` is a **central-only abstract namespace** describing the canonical
provider identity. `deepseek-plan` is a **worker-local namespace alias** that
the opencode runtime on each node uses to map the same model onto its concrete
API endpoint.

The two are not in conflict — they are layers of the same identity — but the D4
collector's 21bao branch reads the NMC's `runtime_visible` field directly without
cross-checking against the local config. Because NMC says `"unknown"` (a
string), the collector reports `false`.

---

## 5. Explicit non-promotion constraints

This residual must NOT be interpreted as:

- a **readiness blocker** — D4 is already closed via 5bao/9bao evidence.
- an **automatic promotion trigger** — `runtime_visible` will not be set to
  `True` on 21bao without explicit operator authorization.
- a **G-L4 advancement** — live inference / model_call_verified is out of
  Baseline02 scope.
- a **gray / readiness acceptance** — these phases are explicitly out of scope.
- a **Baseline03 / Stage8 trigger** — production hardening is out of scope.

The `not_authorized_scope` field of the closure evidence already enumerates
these constraints verbatim; this document simply restates them for the residual.

---

## 6. Why we are NOT modifying NMC or 21bao local config now

### 6.1 NMC data correction would be misleading

The NMC is generated from the central `model_pool.yaml`. If we were to set
21bao's `runtime_visible: true` for `opencode-go-deepseek-v4-pro`, we would be
asserting visibility against the central canonical namespace — but 21bao's local
config does not have an `opencode-go` provider block at all. The assertion would
not be backed by runtime reality and would risk a false-positive promotion that
later phases (G-L4, readiness) might act on without re-verifying.

### 6.2 21bao local config fix would be cosmetic

Adding an `opencode-go` provider block to 21bao's `opencode.jsonc` would not
introduce a working runtime provider. `opencode-go` is currently a
**central-only** namespace; the workers (including 5bao and 9bao) also do not
have an `opencode-go` provider block in their local configs. A cosmetic addition
would not close the asymmetry; it would mask it.

### 6.3 Collector normalization would mask divergence

Adding normalization logic to the D4 collector (e.g. treating
`deepseek-plan.deepseek-v4-pro` as equivalent to
`opencode-go-deepseek-v4-pro`) would change the truth condition of the evidence.
This is a semantic change that requires explicit operator authorization, not an
incidental fix.

---

## 7. Future remediation — gated by operator authorization

If a future operator session decides to elevate 21bao to `runtime_visible=true`,
the following conditions MUST all hold. None of these are met as of this
document's anchor (clean-main = `01c6751`):

1. **Explicit operator authorization** — outside the scope of any Baseline02
   automation; a fresh work order or operator message authorizing the change.
2. **Clean-main sanctioned evidence** — D4 must be re-collected on a clean
   `main` (no dirty working tree, no uncommitted patches) — i.e. a clean-main
   sanctioned evidence pass.
3. **Live verification** — a sanctioned read on 21bao confirming that the
   underlying provider block actually exists and is reachable. No SSH to 21bao
   may be initiated by automation; only an explicit operator-gated session.
4. **Receipt regeneration** — the three D4 receipts and the closure evidence
   must be regenerated and merged through a fresh PR, not by direct write to
   evidence files.
5. **No readiness / G-L4 / gray / Baseline03 / Stage8 progression** — this
   residual must not be used as a stepping stone toward any subsequent phase
   without that phase being independently authorized.

Until all five conditions hold, 21bao's `runtime_visible=false` remains a
`non_blocking_residual`.

---

## 8. Pointer references

| Reference                                                        | Purpose                                          |
|------------------------------------------------------------------|--------------------------------------------------|
| `scripts/model_pool.yaml` (L1241)                                | canonical `opencode-go-deepseek-v4-pro` entry    |
| `scripts/model_pool.yaml` (L549)                                 | legacy `deepseek-plan-deepseek-v4-pro` entry     |
| `scripts/node_model_capability.yaml` (L213)                      | 21bao matrix entry showing `runtime_visible: unknown` |
| `scripts/worker_attest_layer3_d4_sanctioned_live_evidence.py` (L513-520) | collector logic for 21bao `runtime_visible_observed` |
| `.hermes/evidence/g-l3r-d4-receipt-21bao-v3.json`                | 21bao D4 receipt (anchor `baad421`, closed in PR #322) |
| `.hermes/evidence/g-l3r-d4-receipt-5bao-v3.json`                 | 5bao D4 receipt (closure evidence)               |
| `.hermes/evidence/g-l3r-d4-receipt-9bao-v3.json`                 | 9bao D4 receipt (closure evidence)               |
| `.hermes/evidence/g-l3r-d4-runtime-visible-blocker-closed.json`  | D4 closure evidence (PR #322 merge `5a7e894`)    |
| PR #319 (merge `8637e0e`)                                        | stdin-pipe SSH fix on D4 collector               |
| PR #320 (merge `dc15729`)                                        | PATH/recursive/wrapper detection correctness    |
| PR #321 (merge `baad421`)                                        | singular `provider` section_name recognition    |
| PR #322 (merge `5a7e894`)                                        | D4 closure evidence PR                           |
| PR #323 (merge `01c6751`)                                        | dynamic `git rev-parse HEAD` anchor              |

---

## 9. Versioning

- **Created at anchor**: `01c6751e949b4996aeb2b6ba945fbca1b3ff62f8`
- **Phase**: Baseline02 / G-L3R (D4 evidence phase, post-closure)
- **Document type**: docs-only residual record
- **Lifecycle**: live; updated only on operator authorization