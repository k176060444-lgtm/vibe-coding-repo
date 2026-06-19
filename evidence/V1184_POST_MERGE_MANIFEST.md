# V1.18.4 Post-Merge Evidence Manifest

## Merge Confirmation

| 属性 | 值 |
|------|-----|
| PR # | 164 |
| Merge Commit | f05f3f9d8e0c3dc6931abae697fb337dff79b685 |
| PR Head | 8412c4a10d04d8a9950ea9f86422d1766a8bfbb8 |
| Base | 4a1b256a468b61e577b87b1bdda2f83d7ad53ef8 |
| Merge Strategy | merge commit (non-squash) |
| Merged At | 2026-06-19T06:40:39Z |
| Commits | 12 |
| Changed Files | 10, +3629/-51 |

## Node HEAD Status

| 节点 | HEAD | 状态 |
|------|------|------|
| Windows main | f05f3f9d8e0c3dc6931abae697fb337dff79b685 | synced |
| 5bao | BLOCKED: SSH key rejected (CREDENTIAL_REMEDIATION_PENDING) | pending |
| 9bao | BLOCKED: SSH key rejected (CREDENTIAL_REMEDIATION_PENDING) | pending |

## Network Approval (已绑定)

| 属性 | 值 |
|------|-----|
| 批准状态 | APPROVED_MODEL_EGRESS_OPERATOR_APPROVED |
| task_type | opencode_implement / opencode_review only |
| provider_model | APPROVED_MODEL_REGISTRY full provider/model strings |
| approval receipt | 10-field binding + digest recompute |
| network namespace | host network |
| domain_allowlist_enforced | ALWAYS FALSE |
| host_network_used | TRUE |
| approved_egress_domains_audit_only | api.deepseek.com, api.minimax.chat, token-plan-cn.xiaomimimo.com |
| 普通shell/任意命令/裸bash/关闭sandbox | 全部禁止 |

## Orchestrator

| 属性 | 值 |
|------|-----|
| 文件 | scripts/vibe_job_orchestrator.py |
| SHA256 | f6348446ffc7475016b676701df525d558c7f601f79d4cb87dc3c200e055955f |

## V1.17.7 Frozen Baseline

| 属性 | 状态 |
|------|------|
| HEAD | 60409e6 untouched |
| Manifest | 3699732c untouched |

## Security Scan

| 检查项 | 结果 |
|--------|------|
| token_leak | false |
| credential_content_exposed | false |
| external_repo_write | self_owned_public_github_repo |
| secret in diff | 0 findings |
| Unicode bidi/control | 0 findings |

## Pending Items

- 5bao/9bao sync: BLOCKED (SSH credential remediation pending)
- Debian post-merge verification: BLOCKED
- CREDENTIAL_REMEDIATION: PENDING_OPERATOR_APPROVAL

## Superseded / Resolved

The BLOCKED and CREDENTIAL_REMEDIATION_PENDING statuses above
were historical intermediate conditions recorded immediately after PR #164 merge,
before SSH credential remediation was completed.

Resolution (2026-06-19):
- 5bao/9bao SSH sync: RESOLVED - all nodes synced to final HEAD a0b8997
- Credential remediation: RESOLVED - dedicated key confirmed, legacy exposure remediated
- Debian post-merge verification: RESOLVED - 161/161 passed on both nodes

See evidence/V118417_PUBLIC_SAFE_ATTESTATION.md for the final attestation.
