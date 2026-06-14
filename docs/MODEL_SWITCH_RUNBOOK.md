# Model Switch Runbook

Human-operated runbook for switching models when encountering quota exhaustion, rate limiting, timeouts, or quality issues.

**IMPORTANT**: This runbook describes manual procedures. Do NOT modify Provider secrets or production config without explicit authorization.

## Trigger Conditions

| Condition | Symptom | Action |
|-----------|---------|--------|
| Quota exhausted | HTTP 429, "quota exceeded" | Switch to fallback model |
| Rate limited | HTTP 429, "rate limit" | Wait or switch model |
| Timeout | Tool call timeout, no response | Retry once, then switch |
| Quality issue | Repeated failures, wrong output | Switch to higher-tier model |
| Provider down | Connection refused, 502/503 | Switch to different provider |

## Available Models (as of 2026-06-14)

| Provider | Plan | Model | Tier | Notes |
|----------|------|-------|------|-------|
| DeepSeek | deepseek-plan | deepseek-v4-flash | Fast/Cheap | Default implementer |
| DeepSeek | deepseek-plan | deepseek-v4-pro | Quality | Reviewer fallback |
| Xiaomi | xiaomi-plan | mimo-v2.5 | Fast | Default reviewer |
| Xiaomi | xiaomi-plan | mimo-v2.5-pro | Quality | Implementer fallback |
| Volcengine | volcengine-plan | ark-code-latest | Quality | Code specialist |
| MiniMax | minimax-plan | MiniMax-M3 | Quality | General purpose |

## Switch Procedure (Hermes Agent)

### Step 1: Identify the Issue

Check the error message in the Work Order output:
- `quota_exhausted` → Switch provider
- `rate_limited` → Wait 60s or switch
- `timeout` → Retry once, then switch
- `quality_issue` → Switch to higher tier

### Step 2: Select Fallback Model

Follow the model policy chain:
1. **Implementer primary**: deepseek-v4-flash
   - Fallback: mimo-v2.5-pro
   - Max switches: 1
2. **Reviewer primary**: mimo-v2.5-pro
   - No fallback (retry only)

### Step 3: Execute Switch

**For Hermes Agent (QQ interface)**:
- Tell the agent: "切换到 [model_name]，继续当前任务"
- The agent will use the new model for the next tool call

**For OpenCode Worker**:
- The wrapper handles model switching automatically via `opencode.env`
- Manual switch: update `OPENCODE_DEFAULT_MODEL` in `opencode.env`

### Step 4: Verify

After switching:
1. Confirm the new model responds
2. Re-run the failed step
3. Check output quality

### Step 5: Resume

Continue the Work Order from where it stopped:
1. Check `git status` in the worktree
2. Check `git diff` for any partial changes
3. Re-run tests if applicable
4. Continue from the recorded state

## Emergency Procedures

### All Models Exhausted

If all models in the fallback chain are exhausted:
1. **STOP** the current Work Order
2. Report the situation to the user via QQ
3. Wait for user to:
   - Add credits to the exhausted provider
   - Provide a new API key
   - Authorize a different model

### Provider Outage

If a provider is completely down:
1. Check provider status page (if available)
2. Switch to a different provider's model
3. If no alternatives available, pause and report

## What NOT to Do

- ❌ Do NOT modify `opencode.env` or `vibedev.env` without authorization
- ❌ Do NOT create `auth.json` or use `providers login`
- ❌ Do NOT share or echo API keys
- ❌ Do NOT switch models for HTTP 401 (credential error — fix credentials, not model)
- ❌ Do NOT switch models for configuration errors
- ❌ Do NOT auto-switch without user awareness (report first)

## Model Policy Reference

Current model policy (from Work Order spec):
```
implementer.primary = deepseek-plan/deepseek-v4-flash
implementer.fallback_models = ["xiaomi-plan/mimo-v2.5-pro"]
implementer.max_switches = 1
implementer.switch_triggers = ["quota_exhausted", "rate_limited", "provider_unavailable", "timeout_before_mutation", "tool_unavailable_before_mutation"]
implementer.dirty_worktree_policy = "stop"

reviewer.primary = xiaomi-plan/mimo-v2.5-pro
reviewer.fallback_models = []
reviewer.max_switches = 0
reviewer.switch_triggers = []
reviewer.dirty_worktree_policy = "stop"
```

## Escalation

If model switching doesn't resolve the issue:
1. Generate an Escalation Package (see SOUL.md § GPT Escalation Package)
2. Include: error messages, tried models, current state, specific question
3. Forward to user for GPT consultation
