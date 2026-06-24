# Vibe Coding Mode Runtime Integration Guide

**Version:** 1.0.0
**Effective:** 2026-06-24
**Parent Contract:** [VIBE_CODING_MODE_CONTRACT.md](./VIBE_CODING_MODE_CONTRACT.md)
**Implementation:** `scripts/conversational_intake_gate.py`

---

## Purpose

This document specifies **how the agent must use the runtime enforcement functions** when entering Vibe Coding mode. The mode contract (§1–§5) defines the rules; this document defines the executable integration.

**Critical:** The agent MUST call these functions before any action. They are not optional diagnostics.

---

## 1. Mode Entry Detection (mandatory)

### 1.1 When to Call

When the agent receives ANY message that could be a mode entry trigger, it MUST call `detect_mode_entry()` BEFORE processing the request as normal conversation.

**The agent MUST NOT proceed with research, code review, implementation, or any other action until `detect_mode_entry()` returns `verdict` and the mode entry workflow is completed.**

### 1.2 Function Signature

```python
detect_mode_entry(text: str) -> dict
# Returns:
#   mode_active: bool       — True if mode entry detected
#   trigger: str or None    — Matched trigger pattern
#   next_action: str        — "INTAKE_REQUIRED" when mode_active
#   verdict: str            — "MODE_ACTIVE" or "NOT_MODE_ENTRY"
```

### 1.3 CLI Usage

```bash
python scripts/conversational_intake_gate.py --json detect-mode --text "现在我们要进入vibe coding模式"
# → {"mode_active": true, "trigger": "进入.*vibe.?coding", "next_action": "INTAKE_REQUIRED", "verdict": "MODE_ACTIVE"}
```

### 1.4 Agent Behavior

| detect_mode_entry() result | Agent action |
|---|---|
| `mode_active=True` | **STOP normal processing.** Enter Step 0 (acknowledge, confirm repo/SHA/dirt). Then proceed to Step 1 (intake). |
| `mode_active=False` | Continue normal conversation processing. |

---

## 2. Cross-Repo Guard (mandatory in mode)

### 2.1 When to Call

After mode entry is confirmed, before any research or action involving external repos (hermes-agent, opencode, etc.), the agent MUST call `check_cross_repo_guard()`.

### 2.2 Function Signature

```python
check_cross_repo_guard(text: str, current_repo: str = "vibe-coding-repo-clean") -> dict
# Returns:
#   guard_passed: bool           — True if within safe scope
#   cross_repo_detected: bool    — True if external repo involved
#   risk_classification: str     — "local_safe" | "cross_repo_grey_use" | "cross_repo_real_grey_use"
#   operator_action_needed: str  — Required operator action
```

### 2.3 Agent Behavior

| guard_passed | Agent action |
|---|---|
| `True` | Continue within local repo scope. |
| `False` | **STOP.** Output `PLAN_APPROVAL_REQUEST` with `risk_classification` from guard result. Do NOT research, clone, install, or modify external repo. |

---

## 3. Casual Prompt Compilation (mandatory in mode)

### 3.1 When to Call

When the user sends a casual/informal request in vibe coding mode (including voice transcription), the agent MUST call `compile_casual_prompt()` to extract structured intake fields. The agent MUST NOT execute the casual prompt directly.

### 3.2 Function Signature

```python
compile_casual_prompt(text: str) -> dict
# Returns:
#   compiled_goal: str          — Extracted goal
#   scope_guess: list[str]      — Detected scope areas
#   risk_classification: str    — Risk level
#   cross_repo_detected: bool   — External repo flag
#   gate_required: bool         — Always True in vibe coding mode
#   forbidden_actions: list[str] — Actions that must NEVER execute
```

### 3.3 Agent Behavior

The agent MUST use `compiled_goal` as the basis for the intake record and PLAN_APPROVAL_REQUEST. The agent MUST NOT bypass gates even when `gate_required` is True.

---

## 4. PLAN_APPROVAL_REQUEST Generation (mandatory before execution)

### 4.1 When to Call

Before any execution action (code_modify, commit, push, PR, etc.), the agent MUST generate a `PLAN_APPROVAL_REQUEST` using `generate_plan_approval_request()`.

### 4.2 Function Signature

```python
generate_plan_approval_request(
    phase_id: str,
    approval_id: str,
    compiled_prompt: dict,
) -> dict
# Returns:
#   phase_id: str
#   approval_id: str
#   request_type: "PLAN_APPROVAL_REQUEST"
#   goal: str
#   risk_classification: str
#   cross_repo_detected: bool
#   cross_repo_target: str or None
#   scope: list[str]
#   forbidden_actions: list[str]
#   role_model_matrix_required: bool  — Always True
#   operator_action_needed: str
#   next_step: str
```

### 4.3 Required Fields

Every `PLAN_APPROVAL_REQUEST` MUST include:
- `phase_id` — Current phase identifier
- `approval_id` — Unique approval identifier
- `request_type` — Must be `"PLAN_APPROVAL_REQUEST"`
- `goal` — From `compile_casual_prompt().compiled_goal`
- `risk_classification` — From cross-repo guard or compile result
- `forbidden_actions` — From compile result
- `role_model_matrix_required` — Must be `True`
- `operator_action_needed` — Based on risk level

---

## 5. Forbidden Actions

The following actions must NEVER execute in any context:

| Action | Description |
|---|---|
| `debug_config_raw_output` | Printing raw opencode/hermes debug config |
| `output_key_value` | Printing API keys, tokens, secrets |
| `output_token` | Printing auth tokens |
| `clean_malicious_payload_evidence` | Deleting malicious_payload_evidence.json |
| `commit_malicious_payload_evidence` | Committing changes to malicious_payload_evidence.json |
| `clean_pilot_prompts` | Deleting pilot-prompts/ directory |
| `commit_pilot_prompts` | Committing pilot-prompts/ to git |

---

## 6. Integration Verification

### 6.1 Self-Check

```bash
python scripts/conversational_intake_gate.py --self-check
```

### 6.2 Regression Tests

```bash
python -m pytest tests/test_mode_runtime_enforcement.py -v
```

### 6.3 Manual Verification

```bash
# Test 1: Mode entry detection
python scripts/conversational_intake_gate.py --json detect-mode --text "进入vibe coding模式"
# Expected: mode_active=true, verdict=MODE_ACTIVE

# Test 2: Cross-repo guard
python scripts/conversational_intake_gate.py --json plan-approval-request --text "修 hermes PR conflict" --phase-id V1.21.30B
# Expected: risk_classification=cross_repo_real_grey_use

# Test 3: Casual prompt gate
python scripts/conversational_intake_gate.py --json compile-prompt --text "直接修完merge"
# Expected: gate_required=true
```
