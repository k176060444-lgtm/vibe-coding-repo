# Lane B Security Scan Report — V1.18.1 Production Hardening

**Date:** 2026-06-18
**Repository:** k176060444-lgtm/vibe-coding-repo @ HEAD 60409e6
**Scanner:** Lane B automated security scan

---

## 1. Secret Scan — Current Tree

### 1.1 Keyword Scan (api_key, secret_key, password, token, private_key, ssh_key, credential)

| # | File | Line | Keyword | Classification | Notes |
|---|------|------|---------|---------------|-------|
| 1 | `scripts/vibe_job_orchestrator.py` | 119-136 | credential, ssh_key | **FALSE POSITIVE** | Credential enforcement logic (BLOCKED_CREDENTIAL_PATTERNS, credential registry). No actual secret values. |
| 2 | `scripts/vibe_job_orchestrator.py` | 146-273 | credential, ssh_key | **FALSE POSITIVE** | `_resolve_ssh_key()` and `_validate_key_path()` — validation framework, no secrets stored. |
| 3 | `scripts/vibe_batch_runner.py` | 117-234 | token | **FALSE POSITIVE** | Token file metadata checker. Checks existence/mode/size, explicitly NEVER reads content. |
| 4 | `scripts/vibe_batch_runner.py` | 603 | ghp_, github_pat_ | **FALSE POSITIVE** | Token redaction detection pattern list — used to FIND tokens, not store them. |
| 5 | `scripts/vibe_external_authorized_push.py` | 317-502 | credential, token | **FALSE POSITIVE** | Temporary git credential helper creation/cleanup. Token received as function param, never hardcoded. |
| 6 | `scripts/vibe_node_attribution.py` | 152 | ghp_, github_pat_ | **FALSE POSITIVE** | Detection pattern: checks if serialized output contains token patterns. |
| 7 | `scripts/test_toolchain_smoke.py` | 89 | privileged_token | **FALSE POSITIVE** | Self-check: `os.path.isfile()` — checks file existence only, never reads content. |
| 8 | `scripts/test_toolchain_smoke.py` | 2440-5295 | ghp_, github_pat_ | **FALSE POSITIVE** | Test fixture: token redaction detection patterns in string arrays. |
| 9 | `scripts/vibe_executor_sandbox.py` | 43,65 | credentials | **FALSE POSITIVE** | Sandbox path blocking: forbids access to `.env`, `secrets`, `credentials` dirs. |
| 10 | `scripts/vibe_api_fallback_hardening.py` | 20-207 | token | **FALSE POSITIVE** | API call function takes token as parameter, passes via `Authorization` header. No hardcoded values. |
| 11 | `tests/test_vibe_external_authorized_push.py` | 47,290,295,315 | ghp_test_token_1234567890abcdef, ghp_SUPERSECRET_12345 | **FALSE POSITIVE** | Test fixtures with clearly fake token values for redaction testing. |
| 12 | `tests/test_v1131.py` | 105 | ghp_, github_pat | **FALSE POSITIVE** | Test assertion: verifies tokens don't leak in output. |
| 13 | `tests/test_v1142.py` | 85 | ghp_, github_pat | **FALSE POSITIVE** | Test assertion: verifies tokens don't leak in output. |
| 14 | `tests/test_v1143.py` | 155 | ghp_ | **FALSE POSITIVE** | Test assertion: `assert "ghp_" not in output`. |
| 15 | `tests/test_vibe_node_attribution.py` | 64 | ghp_, github_pat_ | **FALSE POSITIVE** | Test assertion: checks for token leakage. |
| 16 | `docs/*.md` (multiple) | various | token, credential, password | **FALSE POSITIVE** | Documentation: describes security policies, workflows, and forbidden patterns. |

### 1.2 Deep Pattern Scan (ghp_, github_pat_, sk-*, AKIA, JWT)

**Result: ZERO TRUE POSITIVES**

All matches are either:
- Detection/redaction patterns (string literals used to SCAN for tokens)
- Test fixtures with obviously fake values (`ghp_test_token_1234567890abcdef`)
- Documentation references
- Function parameters (token passed at runtime, never hardcoded)

---

## 2. Secret Scan — Git History

### Method
```
git log --all -p | grep -i -E 'api_key|secret_key|password|token|private_key|ssh_key|credential'
```

### Findings

| # | Commit Context | Pattern | Classification |
|---|---------------|---------|---------------|
| 1 | V1.17.7.14 credential identity closure | credential, ssh_key | **FALSE POSITIVE** — Credential enforcement framework code |
| 2 | V1.17.7.13 repair authority + credential closure | credential, ssh_key | **FALSE POSITIVE** — Credential registry validation logic |
| 3 | V1.17.7.12 transaction integrity + credential binding | credential, fingerprint | **FALSE POSITIVE** — Fingerprint verification code |

### Deep Historical Scan (ghp_, github_pat_, sk-*, AKIA)
**Result: ZERO TRUE POSITIVES**

No actual secret values were ever committed and later removed. All historical changes involve credential enforcement/framework code, not actual credentials.

---

## 3. Unicode Bidi/Control Character Scan

### Method
Python-based scan of all files for U+202A-U+202E, U+2066-U+206F, U+FEFF.

### Result: **CLEAN — Zero bidi/control characters found**

No trojan source or homoglyph attack vectors detected in any file.

---

## 4. Windows Path Investigation (.py files)

### Findings

| # | File | Line | Path Pattern | Classification |
|---|------|------|-------------|---------------|
| 1 | `scripts/vibe_job_orchestrator.py` | 120 | `C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519` | **TRUE POSITIVE** — Windows controller SSH key path |
| 2 | `scripts/vibe_job_orchestrator.py` | 138 | `C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519` | **TRUE POSITIVE** — Credential registry entry |

### Analysis
- Both paths are **Windows-style forward-slash paths** (`C:/Users/KK/...`), NOT MSYS-style (`/c/Users/...`)
- These are **intentional** — they define the controller-side SSH key location
- The `_CREDENTIAL_ROOT` at line 123 is truncated to `...sh` (obfuscated in code)
- No MSYS-style path conversions (`/c/Users/`, `C:\c\Users`) found in any .py file
- **Risk:** Hardcoded Windows username `KK` in paths. If the repo is used by a different user, these paths will fail. However, the credential registry pattern (`_CREDENTIAL_REGISTRY`) is designed to handle this via ref_id mapping.

---

## 5. Credential Remediation Package

### 5.1 Target File: `/home/vibeworker/.vibedev-secrets/debian-vibeworker-ed25519`

**STATUS: FILE DOES NOT EXIST**

The SSH key `debian-vibeworker-ed25519` does NOT exist at `/home/vibeworker/.vibedev-secrets/` on 5bao (192.168.5.6).

#### Files found in `/home/vibeworker/.vibedev-secrets/`:

| File | Mode | Owner | Size | sha256 |
|------|------|-------|------|--------|
| `github.env` | 600 | vibeworker | 105 bytes | `5e6c553f...eec67` |
| `opencode.env` | 600 | vibeworker | 674 bytes | `4f7830e4...98509` |

### 5.2 SSH Keys Found on 5bao (under `/home/vibeworker/.ssh/`)

| File | Mode | Owner | Size | Fingerprint |
|------|------|-------|------|-------------|
| `vibedev-vibe-coding-repo-ed25519` | 600 | vibeworker | 432 bytes | `SHA256:y5b5nEqyeyLS8iCqEbDitVEBnkMJaRIS/jjq+TQku9o` (vibedev-vibe-coding-repo-readonly, ED25519) |
| `authorized_keys` | 600 | vibeworker | 185 bytes | Contains: `ssh-ed25519 AAAA...G04YN vibedev-hermes-to-debian-vibeworker` |

### 5.3 Windows Key (Controller Side)

| File | Fingerprint | sha256 |
|------|-------------|--------|
| `C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519` | `SHA256:hO9+B7E3oBl9QrkL4pKk06xb1Dog7XwNZAfuH/lS5Kc` (vibedev-hermes-to-debian-vibeworker, ED25519) | `68ac4a2d7fa103d9d10034e440e907658950e35ba8279b3eec068c834d4f7f6f` |

### 5.4 Key Relationship Analysis

| Property | Windows Controller Key | 5bao SSH Key |
|----------|----------------------|-------------|
| **Path** | `C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519` | `/home/vibeworker/.ssh/vibedev-vibe-coding-repo-ed25519` |
| **Fingerprint** | `SHA256:hO9+B7E3oBl9QrkL4pKk06xb1Dog7XwNZAfuH/lS5Kc` | `SHA256:y5b5nEqyeyLS8iCqEbDitVEBnkMJaRIS/jjq+TQku9o` |
| **Role** | Controller→Worker auth key | Worker→Repo read-only key |
| **Comment** | `vibedev-hermes-to-debian-vibeworker` | `vibedev-vibe-coding-repo-readonly` |

**These are DIFFERENT keys with DIFFERENT roles:**
- Windows key authenticates Windows controller → 5bao worker (SSH in)
- 5bao key authenticates 5bao worker → GitHub repo (git clone/pull)

The authorized_keys on 5bao contains the Windows controller's public key, confirming the controller→worker SSH relationship.

### 5.5 Remediation Options for `/home/vibeworker/.vibedev-secrets/debian-vibeworker-ed25519`

Since the file **does not exist**, no remediation is needed for this specific path. However:

| Option | Action | Risk | Recommendation |
|--------|--------|------|----------------|
| **A. DELETE** | N/A — file already absent | None | ✅ Current state is clean |
| **B. ROTATE** | N/A — nothing to rotate | N/A | N/A |
| **C. KEEP** | N/A — nothing exists | N/A | N/A |

### 5.6 Active Secrets on 5bao (requiring attention)

| File | Recommendation |
|------|---------------|
| `/home/vibeworker/.vibedev-secrets/github.env` | **KEEP** — Active GitHub token file (105 bytes, mode 600). Used by workflow. Monitor for rotation. |
| `/home/vibeworker/.vibedev-secrets/opencode.env` | **KEEP** — Active OpenCode config (674 bytes, mode 600). Used by worker. Monitor for rotation. |
| `/home/vibeworker/.ssh/vibedev-vibe-coding-repo-ed25519` | **KEEP** — Active read-only deploy key for repo access. |

---

## Summary (总结)

### 总体评估：仓库安全状态良好

1. **密钥扫描（当前代码树）**：**未发现真实密钥泄露**。所有匹配项均为：
   - 检测/脱敏模式字符串（如 `ghp_` 用于扫描而非存储）
   - 测试固件中的假值（如 `ghp_test_token_1234567890abcdef`）
   - 文档引用
   - 函数参数（运行时传入，未硬编码）

2. **密钥扫描（Git 历史）**：**未发现历史密钥泄露**。所有提交变更涉及凭证强制框架代码，无实际凭证值。

3. **Unicode Bidi 控制字符扫描**：**清洁**。未发现任何双向文本控制字符或 Trojan Source 攻击向量。

4. **Windows 路径调查**：
   - 发现 2 处 `C:/Users/KK/...` 硬编码路径（`vibe_job_orchestrator.py` 第120、138行）
   - 这是**有意设计**——定义控制器端 SSH 密钥位置
   - 未发现 MSYS 风格路径转换问题
   - **建议**：未来可考虑将用户名 `KK` 从路径中移除，使用环境变量或注册表模式

5. **凭证修复包**：
   - `/home/vibeworker/.vibedev-secrets/debian-vibeworker-ed25519` **不存在**（目标文件缺失）
   - 5bao 上存在 2 个活跃密钥文件（github.env、opencode.env），权限正确（600）
   - 控制器密钥和 Worker 密钥为**不同密钥、不同角色**，关系清晰

### 风险等级：🟢 LOW
无阻断性安全问题。建议后续关注硬编码 Windows 路径的可移植性。
