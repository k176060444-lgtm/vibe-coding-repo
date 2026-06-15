# V1.2 Privileged Push Workflow

## 概述

V1.2 引入受控的高权限 GitHub token 使用机制。Token 默认不可用，只有经过人工授权后才能执行 push。

## 标准链路

```
创建审批 (priv-approval create)
  → 人工批准 (approve / 批准 / 确认)
    → Token 预检 (priv-push --token-preflight)
      → 约束验证 (priv-push --dry-run-push)
        → 真实 push (priv-push --push)
          → 证据记录 (evidence)
            → Run Report (rr)
              → V1 Freeze 验证 (v1-freeze)
```

## 命令参考

### 创建审批请求
```bash
python3 scripts/vibe_privileged_approval.py --json create \
  --action-id <id> \
  --repo k176060444-lgtm/vibe-coding-repo \
  --branch <branch> \
  --action push \
  --base-sha <sha> \
  --changed-path <path>
```

### 批准（短授权）
```bash
# 仅当恰好 1 个 pending 时有效
python3 scripts/vibe_privileged_approval.py --json short-approve
```

**支持的短授权词：**
- English: approve, approved, confirm, confirmed, yes, ok, go, allow, authorized, proceed, execute
- 中文: 批准, 确认, 同意, 可以执行, 可以, 允许, 执行, 通过, 授权

### Token 预检
```bash
python3 scripts/vibe_privileged_push.py --token-preflight --json
```

检查项：
- 文件存在
- owner = vibeworker
- mode = 600 (owner read/write only)
- size > 20 bytes
- **不读取 token 内容**

### Push 验证（dry-run）
```bash
python3 scripts/vibe_privileged_push.py --json \
  --action-id <id> --dry-run-push
```

### 真实 Push
```bash
python3 scripts/vibe_privileged_push.py --json \
  --action-id <id> --push
```

## 安全约束

| 约束 | 说明 |
|------|------|
| **Token 输出** | 严禁。Token 永远不会出现在 stdout/stderr/log/report |
| **Token 读取** | 仅在 action 已 approved 后读取 |
| **Token 传输** | 通过 stdin 传给 `gh auth login --with-token`，不作为命令参数 |
| **Self-repo only** | 仅允许 push 到 `k176060444-lgtm/vibe-coding-repo` |
| **Test branch only** | 仅允许 push 到 `privileged-smoke/` 前缀分支 |
| **No force push** | `no_force_push=true` 不可覆盖 |
| **No PR merge** | `no_pr_merge=true` 不可覆盖 |
| **No secrets/CI** | `.github/workflows/`, `secrets/`, `.env`, `ssh/` 等路径被禁止 |
| **No deploy/tag/release** | forbidden_actions 中包含 |
| **Sanitized stderr** | push 输出中的 token 字符串会被替换为 `[REDACTED]` |

## 文件结构

```
~/vibedev/privileged-approvals/     # 审批记录目录
  <action-id>.json                  # 单个审批记录

~/.vibedev/secrets/
  github_privileged_token           # GitHub PAT (mode=600, owner=vibeworker)

scripts/
  vibe_privileged_approval.py       # 审批工作流 (create/show/list/approve/expire/short-approve)
  vibe_privileged_push.py           # Push wrapper (preflight/dry-run/push)
```

## 审批记录字段

```json
{
  "action_id": "unique-id",
  "repo": "owner/repo",
  "branch": "target-branch",
  "action": "push",
  "base_sha": "commit-sha",
  "changed_paths": ["file1.py"],
  "forbidden_actions": [],
  "no_force_push": true,
  "no_pr_merge": true,
  "no_secrets_ci_workflow_provider_ssh": true,
  "created_at": 1234567890.0,
  "expires_at": 1234571490.0,
  "status": "pending|approved|expired|blocked",
  "approved_at": null,
  "approved_by": null,
  "digest": "sha256"
}
```

---

*V1.2 Privileged Push Real-Mode Workflow — 2026-06-15*
