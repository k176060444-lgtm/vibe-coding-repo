# Blind Review Poller (P0) · 异步跨机盲审

**状态：0.1.0 P0 验证版。** 目标是为 Hermes Coding Pipeline 的 Phase 5.0 提供独立、轻量、可恢复的远端盲审任务执行与轮询回收，不需要改造 Hermes A2A 内核。**尚未在真实 5bao / 9bao / rusty 环境或真实 Codex/OpenCode 模型上验收。**

## 已实现的需求

- 三节点候选池（5bao / 9bao / rusty），任意 **两台不同节点的有效盲审**即满足最低席位，**永不允许单审放行**；最多使用三台，不要求第三台成功。
- 先得到两份验收通过的报告后启动 **600 秒第三席宽限**。第三席及时完成则收三份，否则主动取消并按双审继续。宽限期以第二份报告验收完成为起点。
- **60 秒轮询**与 60 秒远端执行器心跳；无需模型每分钟生成“还活着”消息，轮询本身不消耗 LLM Token。
- 每个作业有固定 Git commit SHA、角色契约文件的 SHA256、任务 ID、经任务配置指定的 Harness/模型。远端克隆其可信配置中的 Git 仓库后再校验 `HEAD`。
- SQLite 持久化 Job ID、排队、运行、终态；**相同 Job ID 幂等**，冲突请求拒绝；本端状态 JSON 原子落盘并能 `--resume` 恢复倒计时。
- Harness 可由固定命令模板启动（无 `shell=True`）。Codex 用 `--output-last-message`；OpenCode `--format json` 的 text 事件可解析为标准报告。
- 取消时终止相应子进程（POSIX 进程组 / Windows `taskkill /T /F`）；独立硬超时避免无限等待。
- 产物必须有有效 verdict、文件/行号或证据位置，以及与请求一致的 Job ID、role、commit。报告 SHA256 在本端重算验证。

## 不在 P0 范围

- P1 所有研发角色的固定契约与任务级审批矩阵、P2 全 14 Phase 硬状态机、Hermes A2A 协议本体修改、生产发布、业务代码变更。
- 无法仅凭 CLI 请求参数证明模型供应商最终使用了哪个实际模型；P1 需要补充对真实调用记录的核验。
- 不保证所有非预期断电/`SIGKILL` 都能可靠终止外部模型服务端请求。发生意外重启时 `RUNNING` 变为 `INTERRUPTED`，**不会自动重复启动**，以防产生双执行；需核实孤儿进程后再重新派单。
- 不把机器上两个不同端口自动视为两个独立物理节点：实际拓扑与不同机器的部署由操作者负责。

## 结构

```text
blindreview/common.py       请求/报告契约与校验
blindreview/store.py        SQLite 任务日志与重启恢复
blindreview/worker.py       远端 HTTP 接单、Git 固定快照、CLI 执行、取消
blindreview/http_client.py  无模型 HTTP 状态/报告查询
blindreview/coordinator.py  2-of-3、第三席宽限、状态保存与回收
blindreview/__main__.py     CLI
examples/                   角色契约及配置样例
tests/                      离线模拟盲审与端到端 HTTP 测试
```

## 环境与安装

Python 3.11+、Git。运行时仅使用 Python 标准库。

```bash
python -m unittest discover -s tests -v
python -m compileall -q blindreview
```

在每台远端机器上复制代码、契约文件，并编辑各自的 worker 配置（样例只给 5bao，9bao/rusty 修改 `node_id`、端口、工作路径等即可）。所有节点部署**同一个字节完全一致的角色契约文件**，在本端任务配置中填写 SHA256。

```bash
# 先生成高强度随机 token，写入环境变量，不要提交到 Git。
export BLIND_REVIEW_WORKER_TOKEN='REPLACE_WITH_32_PLUS_RANDOM_CHARACTERS'
python -m blindreview worker --config examples/worker.5bao.json
```

worker 默认只监听 `127.0.0.1`。跨机建议通过 SSH 隧道、WireGuard 私网或 TLS 反向代理访问，不要直接将明文 HTTP 服务暴露到公网。HTTP Bearer token 用于接口鉴权，但**不能替代链路加密**。

在本端编辑 `examples/coordinator.json`：

- `repository` 是远端 Worker 自己配置的可信仓库别名，**不是任意 URL**。
- `commit_sha` 必须替换为实际 Git commit SHA。
- `contract_sha256` 必须与每个远端角色契约一致，可以用 `sha256sum` 或 Python `hashlib.sha256(Path(...).read_bytes()).hexdigest()` 计算。
- 各节点 `harness` 与 `model` 来自本次已批准的矩阵；**样例模型是占位符，不能直接上线运行**。
- `token_env` 指向本端对应节点的环境变量。需要在各节点设置与 Worker 端一致的随机 token。
- 若通过 SSH 隧道访问，给不同节点映射不同的本地端口，并更新 `url`。

```bash
export BLIND_REVIEW_TOKEN_5BAO='...'
export BLIND_REVIEW_TOKEN_9BAO='...'
export BLIND_REVIEW_TOKEN_RUSTY='...'
python -m blindreview coordinate --config examples/coordinator.json --state-dir ./review_state/TASK-001
```

本端被关闭、断线或进程中断后，用同一个任务配置和状态目录恢复：

```bash
python -m blindreview coordinate --config examples/coordinator.json --state-dir ./review_state/TASK-001 --resume
```

如 `summary.json` 显示 `QUORUM_MET`，仅表示 **Phase 5.0 已收到至少两份结构合法、基线一致的独立审查报告**；**不代表技术已 APPROVE，更不代表可部署。** 后续整改/终测/仲裁/人工发布仍按原规程执行。`FAILED_*` 需要停线核查，不允许降为单审。

### 心跳、超时、费用

远端执行器在 `RUNNING` 状态周期性刷新 `heartbeat_at`，`progress_at` 为最后一次观察到执行日志增长的时间；若超过 `stall_warn_seconds`，响应显示 `suspected_stall: true`，**但仅凭静默不能判定模型已卡死**。远端 `max_job_seconds`（例 1800）提供强制截止；本端 `overall_deadline_seconds`（例 3600）限制凑齐两份有效报告的最长等待。两份报告齐后，第三席最多额外等 600 秒，且不会越过总截止时间。

超期或第三席取消会尝试停止远端子进程，但服务端模型计费能否立即终止取决于具体提供商。确认取消是否成功请检查本地 `state.json` 的 `cancel_requested`、`last_error`，以及远端对应 Job 状态。若网络断开导致取消未确认，恢复连通后需要再次对账，不能假设模型已经停了。

## 安全与限制

- `examples/` 为演示模板，不包含真实模型名、密钥、私人路径或真实网络拓扑；先核验 Codex/OpenCode 实际版本的 CLI 参数及角色权限。
- Worker 只允许启动其本地 `harnesses` 配置中的命令模板，不能让请求提供任意 shell 命令。审查角色必须在 Harness 中禁止写源代码及危险工具。
- SQLite 和本地 `state.json`、`reports/` 需要保存在可靠磁盘，不得放入易清理的临时目录。工作目录应按 OS 权限保护，避免非可信进程篡改审核结果。
- Python HTTP API 不提供 TLS、速率限制或多租户访问控制，不要直接暴露公网。仅建议在受信任的私有集群中试运行。
- OpenCode JSONL 解析器只接受独立 JSON 的完整 `text` 事件，不接受 Markdown fenced JSON。不同 CLI 版本需做真实兼容性测试。
- 多个 Worker 进程不要同时使用同一个 SQLite 数据库与工作目录；每个节点运行一个 Worker 服务实例。

## 验收要求（必须在真实节点上补齐）

1. 对同一 commit，确认两节点 SHA 和角色契约 SHA 都一致，并产生可验证审查报告。
2. 制造第三节点执行延迟，第二份报告后 **600 秒准时停止等待并主动取消**；记录终止结果。
3. 审查超过 **420 秒**，确认不会因同步 A2A 调用超时而被本端误判失败。
4. 模拟网络中断、远端重启和本端重启，检查幂等性、持久化、原有 Job 不重复执行及取消对账。
5. 仅一台完成时绝不允许向 Phase 5.1 放行。
6. 实际连接 Codex/OpenCode，检查 CLI 行为、模型绑定、权限与日志；该部分不由离线 mock 测试证明。

## 许可

MIT，详见 LICENSE。

### 失败后补偿取消（避免远端孤儿任务）

如果第三席取消请求当时未获得网络确认，`state.json` 会保留 `cancel_requested` 与错误信息。网络恢复后可以重复执行以下命令；它不会重新派发审查作业：

```bash
python -m blindreview reconcile --config examples/coordinator.json --state-dir ./review_state/TASK-001
```

返回 `pending_cancellations: []` 代表无需再补偿；非空表示仍有未确认项，建议交由外部定时任务在连通恢复后重试。若远端状态已经完成或终止，则会直接确认终态，不再发送无意义的取消。是否已经实际停掉模型服务端请求仍应依据供应商日志判断。
