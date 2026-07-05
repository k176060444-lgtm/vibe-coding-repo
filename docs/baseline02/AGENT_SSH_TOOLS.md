# AGENT_SSH_TOOLS — Agent SSH Usage Reference

> **Service Contract**: Baseline02 (Real-Work Validation, RW-1).
> This document is a **docs-only agent tooling reference**. It captures the
> canonical SSH key path and the operational patterns that agent sessions must
> use when reaching 5bao / 9bao / origin. It does **not** modify any system
> state, code, NMC, model pool, runtime, credential, or protected path.

---

## 1. Mainline Statement (Baseline02 Contract)

This file exists to prevent a recurring class of agent failure:
**context drift on the SSH key path**. In previous sessions, the agent
concluded `STOP_AND_REANCHOR` because it assumed the wrong key path
(`~/.vibedev-secrets/id_vibedev_github`, which is **forbidden** for agent
automation). The correct key has always lived under
`%LOCALAPPDATA%\vibedev-tools\ssh\`. This document locks that fact down so
that any future RW-1 / T3 / I23 / agent session can recover from
"SSH failure" without re-investigating from scratch.

**Authority**: operator explicit authorization (`AGENT_SSH_TOOLS_DOC_AUTHORIZED`).
**Scope**: docs/baseline02/AGENT_SSH_TOOLS.md only.
**Does NOT**: change scripts/, tests/, NMC, model_pool, runtime, credential,
SSH config, git config, protected paths, or worker registry.

---

## 2. Canonical SSH Key Path (single source of truth)

```
C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519
```

POSIX form (for git-bash / MSYS):
```
/c/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519
```

Companion public key (safe to inspect):
```
C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519.pub
```

Cross-reference (out of repo, do not edit):
`C:/Users/KK/AppData/Local/vibedev-tools/ssh/CONTROLLER_CREDENTIAL_REGISTRY.md`

---

## 3. Forbidden Default Assumption

> **Never** default to `~/.vibedev-secrets/id_vibedev_github`.
>
> That path is **not** the canonical agent key path. Any agent session that
> opens with that assumption is operating on stale context and will
> mis-classify SSH failures as "private key missing".

Other forbidden keys (per credential registry audit):
- `~/.ssh/id6663` — operator superadmin key, **not for Vibe Agent automation**.
- Any key not under `%LOCALAPPDATA%\vibedev-tools\ssh\`.

If a session sees an existing `id6663` reference in MEMORY.md / agent
context, that reference is a documentation marker, **not** an operational key.

---

## 4. Worker Endpoints

| Node | SSH user | SSH port | SSH endpoint | Default role |
|------|----------|----------|--------------|--------------|
| 5bao | `vibeworker` | `22222` | `vibeworker@192.168.5.6` | implementer |
| 9bao | `vibeworker` | `22222` | `vibeworker@192.168.9.6` | reviewer |
| 21bao | (local-exec) | n/a | `127.0.0.1` | orchestrator + aggregator |

**21bao is a Windows local-exec / control node.** It does not run an SSH
daemon by default. All 21bao work runs in the agent's own terminal on the
controller host. If an SSH endpoint for 21bao ever exists
(`vibeworker@192.168.21.6 -p 22222`), it is **optional** and only used for
manual remote management, not for the canonical 21bao workload.

Canonical SSH command line for 5bao/9bao (always include `-i` + `-o IdentitiesOnly=yes`):
```bash
ssh -i "C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519" \
    -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=no \
    -o ConnectTimeout=6 \
    -p 22222 \
    vibeworker@192.168.5.6 \
    'hostname; pwd; whoami'
```

---

## 5. R5 Origin Push — Canonical Pattern

`origin` is the bare SSH repository on the 5bao host:
```
ssh://vibeworker@192.168.5.6:22222/home/vibeworker/vibedev/repos/vibe-coding-repo.git
```

For any `git fetch` / `git push` against `origin`, use **per-invocation**
`GIT_SSH_COMMAND`. Do not write `~/.ssh/config`; do not modify `.git/config`;
do not add `--global` core.sshCommand.

```bash
export GIT_SSH_COMMAND='ssh -i "C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519" -o IdentitiesOnly=yes -o StrictHostKeyChecking=no'
git ls-remote origin HEAD
git fetch origin main
git push origin main
```

**`github` remote is HTTPS** (`https://github.com/k176060444-lgtm/vibe-coding-repo.git`)
and is driven by `gh auth` — no SSH key needed there.

---

## 6. Health-Check / Worker SSH / SCP Examples

### 6.1 Health check (preferred)
```bash
cd ~/vibe-coding-repo-clean
python scripts/vibe_worker_pool_health.py --json \
    --key "C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519"
```

Expected (all green):
```
"online": 2, "offline": 0
5bao: health=ONLINE
9bao: health=ONLINE
```

### 6.2 Direct SSH sanity
```bash
SSH_KEY="C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519"
ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -p 22222 vibeworker@192.168.5.6 'echo OK'
ssh -i "$SSH_KEY" -o IdentitiesOnly=yes -p 22222 vibeworker@192.168.9.6 'echo OK'
```

### 6.3 SCP into / out of worker
```bash
SSH_KEY="C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519"
scp -i "$SSH_KEY" -P 22222 ./local-file vibeworker@192.168.5.6:/home/vibeworker/inbox/
scp -i "$SSH_KEY" -P 22222 vibeworker@192.168.9.6:/home/vibeworker/outbox/file ./
```

### 6.4 Run an implementer task on 5bao (no model_call from agent)
The agent **does not** call models for the implementer. The implementer runs
on 5bao. The agent's job is to:
1. SCP source + query into 5bao.
2. SSH into 5bao and trigger the implementer (e.g. via
   `~/.opencode/bin/opencode` or a worker-side runner).
3. SCP result back to controller.
4. Repeat for 9bao (reviewer).

The agent never holds the model API key for the implementer/reviewer; keys
live under `%LOCALAPPDATA%\vibedev-tools\ssh\` and worker-side env only.

---

## 7. Reanchor Checklist (must all pass before RW-1)

```bash
# 7.1 Three-way SHA alignment
cd ~/vibe-coding-repo-clean
echo "local  : $(git rev-parse HEAD)"
GIT_SSH_COMMAND='ssh -i "C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519" -o IdentitiesOnly=yes' \
    sh -c 'git ls-remote origin HEAD'
gh pr list --state all --json number,state | python -c "import json,sys; d=json.load(sys.stdin); print('open:', [p for p in d if p['state']=='OPEN'])"

# 7.2 Working tree clean (only known untracked docs OK)
git status --short

# 7.3 Worker health (must show 2 ONLINE for 5bao/9bao)
python scripts/vibe_worker_pool_health.py --json \
    --key "C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519"

# 7.4 Protected files 0 diff
git diff --stat HEAD -- scripts/ tests/ docs/baseline02/architecture/ docs/baseline02/contracts/
```

If any of the above fails:
- Do **not** invent a result.
- Do **not** start RW-1.
- Report which gate failed with raw command output.
- Wait for operator instruction.

---

## 8. Forbidden Actions

The agent **must not**:
1. `cat` the contents of any private key file (including the canonical key).
2. Copy any private key into the repo (even `.gitignore`d).
3. Write or modify `~/.ssh/config`.
4. Write or modify `.git/config` SSH-related fields.
5. Run `chmod` / `chown` on any SSH key file unless operator explicitly
   authorizes it in writing for that specific file.
6. Add the canonical key to ssh-agent without operator authorization.
7. Modify `~/.vibedev-secrets/` contents (model_pool.secrets only).
8. Echo / log / print the canonical private key contents.
9. Re-route a worker SSH command through `id6663` or any other forbidden key.

These are hard boundaries even when the alternative would "make things work
faster".

---

## 9. Troubleshooting Decision Tree

```
ssh / scp / git fetch fails with "Permission denied (publickey)"
│
├── Q1: Did the command use the canonical key?
│        Yes (proves -i path or GIT_SSH_COMMAND is set)  ─┐
│        No  (used ~/.ssh/id6663 or default)              ─┤
│                                                            │
│   Action for "No": re-run with explicit -i / GIT_SSH_COMMAND pointing to
│                    C:/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519
│                    → stop here, do not escalate further.
│
├── Q2: Is the canonical key file present?
│        ls -la "/c/Users/KK/AppData/Local/vibedev-tools/ssh/debian-vibeworker-ed25519"
│        Yes (file exists, correct size ~432 bytes)  ─┐
│        No  (file missing)                           ─┤
│                                                       │
│   Action for "No": STOP. Do not fabricate "private key missing" report
│                    without first confirming path. Escalate to operator
│                    with: "canonical key file is absent at path X; please
│                    restore from backup".
│
├── Q3: Does the public key match what's authorized on the server?
│        Compare
│            cat .../debian-vibeworker-ed25519.pub
│        to
│            vibeworker@<host>:~/.ssh/authorized_keys
│        (via a successful alternate session, or via the
│         CONTROLLER_CREDENTIAL_REGISTRY.md fingerprint)
│        Match  ─┐
│        Mismatch ─┤
│                   │
│   Action for "Mismatch": key needs to be re-added to server's
│                          authorized_keys. STOP and escalate to operator.
│
└── Q4: GitHub side (only for github remote)
        gh auth status
        If unauthenticated → operator must run `gh auth login` interactively.
        Agent must not run `gh auth login` on operator's behalf.
```

**Anti-pattern the agent MUST avoid**:
- Seeing `Permission denied (publickey)` and immediately concluding
  "the private key file is missing in this session" **without first
  verifying which key the command used**. That was the bug in the previous
  session's reanchor; this doc exists to prevent recurrence.

---

## 10. Operator Verification Reference

The companion file (not in repo, written by operator):
`C:/Users/KK/AppData/Local/vibedev-tools/ssh/CONTROLLER_CREDENTIAL_REGISTRY.md`

It records:
- credential_id = `controller-key-001`
- public_fingerprint = `SHA256:hO9+B7E3oBl9QrkL4pKk06xb1Dog7XwNZAfuH/lS5Kc`
- comment = `vibedev-hermes-to-debian-vibeworker`
- allowed_hosts = `192.168.5.6 (5bao), 192.168.9.6 (9bao)`
- last_verified timestamps

Any agent session can sanity-check the key by reading the `.pub` file
(public, safe) and matching against the registry fingerprint.

---

## 11. Change Log

| Date       | Change                                              | Source                     |
|------------|-----------------------------------------------------|----------------------------|
| 2026-07-06 | Initial agent-facing SSH tools doc                  | `AGENT_SSH_TOOLS_DOC_AUTHORIZED` |