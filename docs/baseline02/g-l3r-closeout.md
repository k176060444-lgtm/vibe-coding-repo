---
anchor:
  main: "d33c4171afdf198c491077bd1a6087946bfd89cf"
  github_main: "d33c4171afdf198c491077bd1a6087946bfd89cf"
  origin_main: "d33c4171afdf198c491077bd1a6087946bfd89cf"
  timestamp: "2026-07-03T18:30:00Z"
phase: "Baseline02"
status: "G_L3R_CLOSEOUT"
d4:
  status: "G_L3R_D4_RUNTIME_VISIBLE_BLOCKER_CLOSED"
  blocker: "CLOSED_BY_5BAO_9BAO"
  reconciliation: "G_L3R_RECONCILIATION_PASS_D4_CLOSED"
  evidence_anchor: "baad421f3213f666ce5b1448e7923b0ad2c640f7"
  basis:
    - "5bao: runtime_visible_observed=true (v3 clean-main sanctioned receipt)"
    - "9bao: runtime_visible_observed=true (v3 clean-main sanctioned receipt)"
    - "21bao: runtime_visible_observed=false (non_blocking_residual)"
  receipts:
    "5bao": "runtime_visible_observed=true"
    "9bao": "runtime_visible_observed=true"
    "21bao": "runtime_visible_observed=false"
  notes: "D4 runtime visibility blocker closed per operator-approved PR #322. 21bao residual accepted as non-blocking per closure evidence."
residuals:
  R1:
    status: "CLOSED"
    resolution: "PR #323 — derive D4 evidence anchor from git rev-parse HEAD (dynamic, not hardcoded)"
  R5:
    status: "CLOSED"
    resolution: "OPS-HYGIENE-001B (detach stale worktree) + OPS-HYGIENE-002 (push PR #324 to origin)"
  R8:
    status: "DOCUMENTED"
    resolution: "PR #324 — docs/baseline02/g-l3r-d4-21bao-namespace-asymmetry.md"
pr_lineage:
  - "PR #319 — stdin-pipe fix for D4 live evidence collector"
  - "PR #320 — PATH/recursive/wrapper_valid fix"
  - "PR #321 — singular section_name fix"
  - "PR #322 — D4 closure evidence (anchor baad421)"
  - "PR #323 — dynamic anchor derivation from git HEAD"
  - "PR #324 — 21bao namespace asymmetry residual documentation"
scope_constraints:
  not_readiness: true
  not_g_l4: true
  not_gray: true
  not_baseline03: true
---

# G-L3R Closeout Status — Baseline02

## 1. Anchor Status

| Anchor | Commit | Status |
|---|---|---|
| HEAD | `d33c4171afdf198c491077bd1a6087946bfd89cf` | active |
| local main | `d33c4171afdf198c491077bd1a6087946bfd89cf` | git status clean |
| github/main | `d33c4171afdf198c491077bd1a6087946bfd89cf` | GitHub truth |
| origin/main | `d33c4171afdf198c491077bd1a6087946bfd89cf` | synced |
| Open PRs | 0 | — |

*All four anchors aligned after OPS-HYGIENE-002.*

## 2. D4 Runtime Visibility Blocker

**Status**: `G_L3R_D4_RUNTIME_VISIBLE_BLOCKER_CLOSED`  
**Blocker**: `CLOSED_BY_5BAO_9BAO`  
**Reconciliation**: `G_L3R_RECONCILIATION_PASS_D4_CLOSED`

The G-L3R D4 runtime visibility blocker was closed via PR #322 based on clean-main sanctioned live evidence collection at anchor `baad421`. The closeout was re-verified after the dynamic anchor fix (PR #323). The stdin-pipe (PR #319), PATH/recursive/wrapper_valid (PR #320), and section_name (PR #321) fixes were all preconditions for clean evidence collection.

## 3. D4 Evidence Anchor

The D4 v3 evidence was collected at anchor:

```
baad421f3213f666ce5b1448e7923b0ad2c640f7
```

This is the merge base at which the three sanctioned live-receipts were generated. The evidence collector now derives the anchor dynamically from `git rev-parse HEAD` (PR #323), falling closed with `RuntimeError` if git is unavailable.

## 4. D4 Evidence Basis

The closure verdict is based on clean-main sanctioned receipts collected after all fix PRs (#319–#321) were merged:

| Node | runtime_visible_observed | Source |
|---|---|---|
| **5bao** | `true` | v3 clean-main sanctioned receipt |
| **9bao** | `true` | v3 clean-main sanctioned receipt |
| **21bao** | `false` | v3 clean-main sanctioned receipt |

The 5bao and 9bao nodes confirmed model runtime visibility. This satisfied the operator-approved acceptance criteria of 2-of-3 nodes demonstrating `runtime_visible_observed=true`.

## 5. 21bao Residual

**21bao** remains `runtime_visible_observed=false` and is classified as **`non_blocking_residual`**.

The root cause is a **provider namespace asymmetry**: central model pool uses `opencode-go` as the canonical namespace, while 21bao's local OpenCode config (`~/.config/opencode/opencode.jsonc`) nests the `deepseek-v4-pro` model under `deepseek-plan`. There is no `opencode-go` provider block on 21bao. The NMC entry for `opencode-go-deepseek-v4-pro` on 21bao lists `runtime_visible: unknown`.

See [g-l3r-d4-21bao-namespace-asymmetry.md](g-l3r-d4-21bao-namespace-asymmetry.md) (PR #324) for full details and remediation options.

## 6. Residual Register

| ID | Status | Resolution | PR / Action |
|---|---|---|---|
| **R1** | CLOSED | Dynamic anchor derivation | PR #323 |
| **R5** | CLOSED | Worktree detach + origin push | OPS-HYGIENE-001B + OPS-HYGIENE-002 |
| **R8** | DOCUMENTED | Namespace asymmetry documented | PR #324 |

*R1 (hardcoded CURRENT_ANCHOR) was the anchor drift that required the dynamic `_resolve_anchor()` fix in the D4 collector. R5 (origin/main stale) was resolved by SSH worktree detach and push. R8 (21bao provider namespace asymmetry) is documented but not remediated — see §5 above.*

## 7. PR Lineage

All PRs from the G-L3R D4 fix cycle, in dependency order:

| PR | Title | Purpose |
|---|---|---|
| [#319](https://github.com/k176060444-lgtm/vibe-coding-repo/pull/319) | `fix: pipe collector script via SSH stdin` | Prevent multi-line quoting issues in SSH `-c` inline form |
| [#320](https://github.com/k176060444-lgtm/vibe-coding-repo/pull/320) | `fix: PATH, recursive subprocess, wrapper_valid` | Fix SSH PATH, recursive SSH, and wrapper validation |
| [#321](https://github.com/k176060444-lgtm/vibe-coding-repo/pull/321) | `fix: use singular section_name for receipt` | Align receipt section key with collector output |
| [#322](https://github.com/k176060444-lgtm/vibe-coding-repo/pull/322) | `evidence: close G-L3R D4 runtime visibility blocker` | D4 closure evidence with receipts |
| [#323](https://github.com/k176060444-lgtm/vibe-coding-repo/pull/323) | `fix: derive D4 evidence anchor from git HEAD` | Dynamic anchor resolution (fixes R1) |
| [#324](https://github.com/k176060444-lgtm/vibe-coding-repo/pull/324) | `docs: record 21bao namespace residual` | R8 documentation (asymmetry) |

## 8. Scope Constraints

This closeout is explicitly **NOT** any of the following:

- ❌ **not-readiness** — D4 runtime visibility is an infrastructure precondition, not a readiness gate.
- ❌ **not-G-L4** — G-L4 is a subsequent phase not yet authorized.
- ❌ **not-gray** — Gray is separate from this Baseline02 scope.
- ❌ **not-Baseline03** — Baseline03 is a future phase not yet authorized.

The D4 closeout is a **Baseline02 / G-L3R milestone** only. It does not imply readines for or entitlement to any subsequent phase.

## 9. Forbidden Reinterpretation

The following interpretations of this closeout are **explicitly forbidden**:

1. **No automatic readiness elevation**: D4 blocker closed does not mean cluster is ready for G-L4/readiness.
2. **No automatic 21bao promotion**: 21bao `runtime_visible_observed=false` must remain `non_blocking_residual` until a new operator decision authorizes its elevation.
3. **No phase bleed**: This closeout is Baseline02-only. Any attempt to use it to shortcut G-L4/readiness/gray/Baseline03 approval is invalid.
4. **No evidence re-use**: The D4 receipts are specific to the D4 blocker and may not be used as evidence for a different gate unless explicitly re-collected under that gate's sanction.

## 10. Forward Path (for reference, not action)

If future remediation of the 21bao residual is desired, the following conditions must all be satisfied:

1. **Operator authorization** — a new explicit operator decision for the 21bao elevation scope.
2. **Clean-main baseline** — the remediation must be based on a clean main at the time of execution.
3. **Sanctioned live verification** — `runtime_visible_observed` must be re-verified on clean main with a sanctioned evidence collection.
4. **Receipt regeneration** — all three node receipts must be regenerated and the D4 closure evidence updated under the new anchor.
5. **No phase escalation** — the 21bao remediation must not be used to justify or shortcut entry into G-L4/readiness/gray/Baseline03.

## 11. Pointer References

| Reference | Path |
|---|---|
| D4 closure evidence | `.hermes/evidence/g-l3r-d4-runtime-visible-blocker-closed.json` |
| D4 v3 receipt (21bao) | `.hermes/evidence/g-l3r-d4-receipt-21bao-v3.json` |
| D4 v3 receipt (5bao) | `.hermes/evidence/g-l3r-d4-receipt-5bao-v3.json` |
| D4 v3 receipt (9bao) | `.hermes/evidence/g-l3r-d4-receipt-9bao-v3.json` |
| 21bao residual docs | `docs/baseline02/g-l3r-d4-21bao-namespace-asymmetry.md` |
| R1 fix | PR #323 |
| R5 fix | OPS-HYGIENE-001B + OPS-HYGIENE-002 |
| D4 collector | `scripts/worker_attest_layer3_d4_sanctioned_live_evidence.py` |

## 12. Versioning

| Field | Value |
|---|---|
| Anchor | `d33c4171afdf198c491077bd1a6087946bfd89cf` |
| Phase | Baseline02 |
| Lifecycle | closeout — not-readiness, not-G-L4, not-gray, not-Baseline03 |
| Last updated | 2026-07-03T18:30:00Z |
