# V1.20.18 21bao Blocklist Gap Fix & Manual-Only Dry-Run Activation Plan

**Version:** 1.20.18
**Date:** 2026-06-20
**Status:** Blocklist fix + plan document only -- NOT enabling 21bao

---

## Safety Declarations

- **This PR does NOT enable 21bao auto-scheduling**
- **This PR does NOT execute any dry-run/no-op/real job**
- **This PR does NOT call OpenCode or any model**
- **This PR does NOT modify any secret/env/credential**
- **This PR does NOT merge to main**
- **This PR only closes the controller repo blocklist gap and provides activation plan documentation**

---

## 1. What This PR Does

### A. Controller Repo Blocklist Gap Fix

**Problem:** `BLOCKED_PREFIXES` only referenced the legacy controller repo path, but the actual controller repo is at a profile-scoped location under the Hermes profile home directory.

**Fix:**
1. Added profile-scoped controller repo path to `BLOCKED_PREFIXES`
2. Added `_canonicalize()` function for safe path comparison:
   - Case-insensitive (Windows)
   - Forward/backward slash normalization
   - Relative path / `..` traversal resolution
   - Trailing slash normalization
   - Symlink/junction resolution via `os.path.realpath`
3. Fail-closed: any path that cannot be canonicalized is rejected

**Bypass prevention matrix:**

| Bypass attempt | Before fix | After fix |
|---|---|---|
| Profile-scoped path | NOT blocked | BLOCKED |
| Case difference | NOT blocked | BLOCKED |
| Forward slashes | NOT blocked | BLOCKED |
| Path traversal (..) | NOT blocked | BLOCKED |
| Trailing slash | NOT blocked | BLOCKED |
| Old legacy path | blocked | still blocked |
| D/E allowlist | allowed | still allowed |

### B. Plan Documentation

Activation design, job specs, rollback plan, operator decision points.

---

## 2. 21bao Status (Unchanged)

| Parameter | Value |
|---|---|
| enabled | **False** |
| manual_only | **True** |
| transport | local-exec |
| auto-scheduled | **NO** |
| active-active capacity | 2 (5bao + 9bao only) |

---

## 3. Activation Design (Future, Requires Separate Operator Approval)

### Target State (NOT this PR)
```
21bao: enabled=True, manual_only=True
```

### Dry-Run Job Spec
```python
JobSpec(job_id="21bao-dry-run-001", branch="feat/test", task="implementer",
        worktree_path="<21bao_worktree_root>/dry-run-001",
        dry_run=True, timeout_s=30)
```
Expected: status=dry_run, exit_code=0, opencode_called=false, model_calls=0

### No-Op Job Spec
```python
JobSpec(job_id="21bao-noop-001", branch="feat/test", task="reviewer",
        worktree_path="<21bao_worktree_root>/noop-001",
        no_op=True, timeout_s=10)
```
Expected: status=no_op, exit_code=0

### Rollback
Revert 21bao enabled to False. Evidence/logs preserved on worker storage drives.

---

## 4. Auto-Scheduling Exclusion Proof

| Evidence | Result |
|---|---|
| manual_only=True in registry | YES |
| scheduler skips manual_only workers | YES |
| get_eligible_candidates() excludes 21bao | YES |
| unknown transport fail-closed | YES |

---

## 5. Operator Decision Points

| Decision | Recommendation |
|---|---|
| Merge this PR? | After review |
| Enable 21bao (enabled=True)? | Separate PR, requires approval |
| Execute dry-run job? | After enabled=True merge, operator trigger |
| Execute no-op job? | After dry-run pass, operator trigger |

---

## 6. Canonicalization Failure Handling

`_canonicalize()` is fail-closed:
- If `os.path.realpath()` or `os.path.abspath()` raises OSError or ValueError, the exception propagates
- `is_path_blocked()` returns True (blocked) on canonicalization failure
- `is_path_allowed()` returns False (not allowed) on canonicalization failure
- `validate_path()` returns (False, reason) on canonicalization failure
- No fallback to `os.path.normpath()` -- if we cannot resolve, we reject

### Limitation: Symlink/Junction Detection

On Windows, `os.path.realpath()` resolves junctions and symlinks. However:
- If the junction target is on a different volume, resolution may fail (fail-closed: blocked)
- If the junction target is the controller repo from a D:/E: path, `realpath` will resolve to the controller repo path, which is then caught by the blocklist
- We do NOT claim to detect all possible reparse points; the defense-in-depth is that D:/E: allowlist already restricts the attack surface

---

*Plan only. No activation, no real job, no merge executed in this document.*
