# Blind Review Poller P0 独立代码审计与验证报告

审计时间：2026-11-03，中国标准时间。审计对象：`https://github.com/k176060444-lgtm/vibe-coding-repo`，指定基准和实际 HEAD 均为 `cf35ab01eae63298ff9f2ae9faa4d0012fe73c2c`。远端 HEAD 查询结果同 SHA；审计末尾 `git status --porcelain=v1 --untracked-files=all` 为空。

## 1. 执行摘要、结论及评分

**最终验收结论：FAIL。工程成熟度：31/100。**

本次发现四项 P0 问题：Coordinator 只验证配置声明的节点 ID 和 URL，无法证明两份报告来自不同物理节点；报告中的 `task_id` 与 `contract_sha256` 即使与请求明确冲突，仍可能进入 `QUORUM_MET`；本地 Git 克隆可与源仓库共享可写对象硬链接；排队作业恢复后不重新验证契约，可能在错误契约下完成。本机双 Worker 测试使用真实 HTTP/SQLite/Git，仅对报告换行作 LF 适配；全部报告由模拟程序生成，不是真实模型审查。

还确认多个 P1：HTTP 重定向会转发 Bearer Token；Windows Worker 的报告文件哈希与 Coordinator 计算不一致；报告临时拉取失败可能提前判定席位不足；监控异常会遗留失去跟踪的子进程；Coordinator 在第二份报告后崩溃会重置计时或错误失败；超时与心跳可被阻塞的标准输入写入绕过。详见缺陷清单。

评分由以下五部分相加得到，仅用于表达工程成熟度，不改变 FAIL：门槛与身份正确性 5/25；传输及执行安全 5/20；持久化与故障恢复 9/25；测试与真实集成 6/20；可维护性与文档 6/10。

实际未访问 5bao、9bao、rusty，没有运行真实模型、修改生产配置、提交或推送代码。最终结论是对本次指定 P0 基准的技术审计，不是流水线 Phase 5.3 技术仲裁或 Phase 5.85 合规督察，也不构成发布批准。

## 2. 环境、基准与目录树

- Python 3.11.15，`C:\\Users\\KK\\AppData\\Local\\hermes\\hermes-agent\\venv\\Scripts\\python.exe`。
- Git 2.54.0.windows.1；Windows-10-10.0.19044-SP0。
- 审计目录：`C:/Users/KK/AppData/Local/hermes/profiles/xiaoshitou/cache/scratch/blindreview-audit-cf35-qmvjb205/`。`source/` 是独立克隆；测试脚本、状态和原始输出均在其同级隔离目录。
- 原始源仓库没有改动，目标检出 tracked/untracked 工作树均干净。未安装依赖。

通过 `git ls-tree -r --name-only` 枚举的 19 个文件：

```text
.github/workflows/tests.yml
.gitignore
LICENSE
README.md
blindreview/__init__.py
blindreview/__main__.py
blindreview/common.py
blindreview/coordinator.py
blindreview/http_client.py
blindreview/store.py
blindreview/worker.py
docs/TEST_RESULTS.md
examples/blind-review-contract.md
examples/coordinator.json
examples/worker.5bao.json
pyproject.toml
tests/mock_opencode.py
tests/mock_reviewer.py
tests/test_pipeline.py
```

## 3. 实际调用链与信任边界

`python -m blindreview` 读取 JSON 配置，启动 Coordinator 或 Worker。Coordinator 固化每节点不同的 Job ID，调用 HTTP submit/status/report/cancel；本地 `state.json` 用临时文件、fsync、replace 持久化。Worker 验证请求、仓库别名及本地契约哈希，使用 SQLite 记录作业，在独立目录执行 Git clone、固定 SHA checkout，再启动本地配置的 Harness。报告通过字段检查后存盘，Worker 返回文件 SHA256，Coordinator 再按规范化 JSON 重算哈希，并依据合法报告数量给出 `QUORUM_MET`。

这里存在真实的执行链：已在本机执行 Git、SQLite、HTTP 和模拟子进程；它不是全 Mock。但身份来自配置与服务自报，文件哈希只验证内容一致性，不能证明另一台真实物理机器、真实 Harness、实际模型或审查质量。`QUORUM_MET` 只表示项目实现认定有两份格式报告，并非技术 APPROVE 或发布许可。

## 4. 逐文件静态审查表

| 文件 | 结论与主要证据 |
|---|---|
| `blindreview/__init__.py` | 版本声明；未发现独立关键逻辑。 |
| `blindreview/__main__.py:25-46` | 实际 CLI 入口存在；配置读取发生在 try 前；异常处理不包含报告 TypeError 或 `http.client.IncompleteRead`。 |
| `blindreview/common.py:46-84` | 请求字段、SHA 和角色有校验；报告仅绑定 job_id/commit_sha/role，不绑定 task/contract；非哈希类型可能触发 TypeError；finding 位置仅检查非空。 |
| `blindreview/coordinator.py:28-33,54-66,71-101,106-165,186-256` | 节点去重只是 ID/URL；无独占锁；报告拉取、持久化恢复、计时、取消及摘要存在下列缺陷。 |
| `blindreview/http_client.py:24-39` | 使用标准 `urlopen` 自动重定向；读取失败异常覆盖不足，跨 origin 转发 Authorization 已实测。 |
| `blindreview/store.py:31-41,55-94,101-113` | 单实例锁下幂等有效；多连接状态迁移非原子；重启将 RUNNING 标记 INTERRUPTED，不自动重跑也不证明孤儿进程已停止。 |
| `blindreview/worker.py:27-29,50-65,76-227,240-269,294-355,371-387` | 实际执行链存在；有输入和大小限制；契约恢复、本地克隆硬链接、子进程异常收尾、队列、stdin、秘密继承、只读检查等存在缺陷。 |
| `tests/test_pipeline.py:24-30,76-165,167-287` | 含真实本地 Git、Worker、HTTP 与模拟 Harness；Coordinator 使用 FakeClient，未做真实 Coordinator→Worker 全链路哈希验证；取消对账测试没有制造网络失败。 |
| `tests/mock_reviewer.py`, `tests/mock_opencode.py` | 明确是 Mock；不能作为真实审查或模型兼容证明。 |
| `examples/coordinator.json`, `examples/worker.5bao.json`, `examples/blind-review-contract.md` | 仅样例；模型占位；OpenCode 角色权限、目标端 Agent 和实际模型需外部核验。样例的明文 HTTP 必须依赖安全隧道，不能视为传输加密。 |
| `README.md`, `docs/TEST_RESULTS.md` | 明确披露真实节点、CLI、Linux/Windows 部分验证缺口及不支持多 Worker 共用工作目录；作者的测试结论本审计不直接采信。 |
| `pyproject.toml`, `.github/workflows/tests.yml`, `.gitignore`, `LICENSE` | 运行时零第三方依赖；CI 只声明 Ubuntu/Python 3.11；忽略规则会影响 `git status` 检测；许可证为 MIT。 |

## 5. 基础测试与适配说明

用户要求原始 `python -m unittest discover -s tests -v`；原测试 `tests/test_pipeline.py:24-30` 会在合成临时仓库中执行 `git commit`，而本次明确禁止提交代码。为遵守该边界，本审计在测试进程中以克隆当前已存在的 SHA 替换该 fixture，未修改原测试文件；另跳过会触发真实子进程终止的 `test_cancel_running_review`。

在上述**非原样**条件下实际运行该命令：`Ran 14 tests in 3.621s`、`OK (skipped=1)`，即 13 通过、1 跳过，进程退出码 0，墙钟 5.357 秒。不能宣称原样 14/14 或完成真实终止验证。原始输出：`evidence/baseline_unittest.log`；进程内适配：`baseline_hooks/sitecustomize.py`。

第一次 `python -m compileall -q blindreview` 因审计设置的 `PYTHONPYCACHEPREFIX` 导致 Windows 路径过长失败，退出码 1，错误在 `evidence/baseline_compileall.log`。后将 7 个 Python 源文件复制到隔离目录、逐个 SHA256 对齐，在该副本执行同一 compileall 命令：退出码 0，0.136 秒，无输出，日志 `evidence/compile_copy.log`。第一次失败是本次测试路径设置导致，不能据此判源码语法失败。

另有 67 条独立对抗测试执行：36 通过、27 FAIL、4 ERROR；其中包含同一个双 Worker 用例在 Windows 原始换行与 LF 模拟下的两次执行。部分测试故意以能够复现的不安全行为为正向观察，因此“通过数”不是安全评分。逐次完整堆栈保存在 `evidence/*.log`。

## 6. 故障注入与恢复矩阵

| # | 场景与测试方法/输入 | 预期 | 实际、证据及状态 |
|---|---|---|---|
| 1 | 三节点均完成，FakeClient 相同模拟时刻返回有效报告 | 收三份 | 三份均收；`audit_probes` 01。**模拟通过**。 |
| 2 | 一份完成、其余永远 RUNNING，模拟总截止 | 不放行单份 | `FAILED_QUORUM_TIMEOUT`；`audit_probes` 02。**模拟通过**。 |
| 3 | 两份成功、第三份永久 RUNNING，模拟 599/600/601 秒 | 600 秒内停止等待并取消 | 指定恰好步进 599/600/601 时符合；但默认 60 秒轮询加每次 7 秒响应耗时达到 603 秒，400 秒轮询达到 800 秒。`audit_probes` 03/17/27、`default_timing_probes`。**边界失败**。 |
| 4 | 三节点均返回 FAILED；另测传输持续失败 | 不假成功、最终终止 | 前者 `FAILED_INSUFFICIENT_REVIEWERS`，后者总超时；`audit_probes` 04/06。**模拟通过**。 |
| 5 | 第二、第三份同一模拟时刻完成 | 无错误计数 | 收到三份；`audit_probes` 05。**单线程模拟通过；真实跨线程时序未穷举**。 |
| 6 | 本地 HTTP 实测 500、非法 JSON、拒绝连接、延迟、截断 chunk、跨地址重定向和慢速滴流 | 统一转传输失败，保密，整个请求有界 | 500/非法 JSON/拒绝/超时归一化通过；截断 chunk 抛 `IncompleteRead`，重定向泄露合成 Token，0.15 秒 socket 超时配置下慢速响应耗时 0.578 秒；`network_probes`、`followup_probes` 07。**失败**。随机抖动统计未做。 |
| 7 | RUNNING 在模拟时钟推进 421 秒；另用真实测试子进程和大 stdin | 不因 420 秒判死，心跳持续且硬截止生效 | Coordinator 模拟仍 RUNNING；真实 1 秒截止任务在 1.7 秒仍 RUNNING、心跳已 1.91 秒未更新，约 3.88 秒后才终态。`audit_probes` 07、`worker_probes`。**部分通过，硬截止失败**。 |
| 8 | 模拟 Coordinator resume、第二份报告已落盘后崩溃、排队契约变更，SQLite RUNNING→重开恢复 | 计时不重置、不使用错误契约、不自动双执行 | 常规已记录 quorum 时间可保留；在两份报告落盘、quorum 时间未保存时模拟崩溃，恢复使计时重置 601 秒，越过总截止则错误失败；排队任务可在错误契约 B 下完成。`audit_probes` 08/24、`followup_probes` 01-03。**失败**；真实异常杀进程未实测。 |
| 9 | 单 Store 八线程并发同 Job ID；冲突内容重用 ID | 一次创建、其余幂等；冲突拒绝 | 1 次创建、7 次已有，冲突拒绝；`parallel_probes`、`audit_probes` 09。**单 Store 通过**。多 Store 竞态见 #15。 |
| 10 | 错误 SHA/身份/Job ID/报告哈希；报告携带错误 task 和 contract | 拒绝不一致报告 | 前四种模拟拒绝；task 与 contract 都错误仍 `QUORUM_MET`；`audit_probes` 10-14、`contract_probes`。**失败**。 |
| 11 | 本机 Worker+模拟 CLI：缺文件、畸形 stdout、JSONL fenced 格式 | 拒绝并失败，不虚构报告 | 均为 FAILED；`adapter_probes`。**通过**；真实 Codex/OpenCode 模型输出格式未验证。 |
| 12 | 第三席取消响应丢失后重连；取消瞬间第三席返回 COMPLETED；注入 Worker 心跳写入异常 | 对账收敛、不收迟到报告、不遗留无人跟踪的进程 | 模拟丢包后可对账；取消回执为 COMPLETED 时迟到报告被置 `valid=true`；真实本地测试子进程在任务 FAILED 后仍运行且 `_running` 已移除，随后自行退出。`audit_probes` 20/21、`race_probes` 03、`followup_probes` 04。**失败**；真实中断及模型服务端请求未测试。 |
| 13 | 损坏 SQLite/状态 JSON；模拟 fsync `ENOSPC`；模拟最终摘要写失败 | 不假成功，恢复时沿用 ID 并恢复必要产物 | 损坏文件报错，模拟 ENOSPC 后 ID 不变；摘要写失败后恢复返回 `QUORUM_MET` 但 summary 文件仍不存在。`audit_probes` 22-24、`race_probes` 01、`summary_crash_probe`。**部分失败**；没有真实写满磁盘、断电或强杀。 |
| 14 | 599/600/601、总截止先于第三席、响应延迟 | 严格执行最早截止 | 接受总截止时的第三份；默认 60 秒轮询模拟 603 秒，宽限值 1200 秒也被接受；`audit_probes` 16-19/27、`default_timing_probes`。**失败**。 |
| 15 | 单 Worker 两任务并发、八线程重复提交；两个 Store 竞争；两个 Coordinator 同目录初始化；队列阻塞 | 不串任务、不双领、不双派，排队资源有界 | 单 Worker 两任务各完成、八次仅一次创建；双 Store 同一 QUEUED→RUNNING 均返回 True；双 Coordinator 同时创建不同 run ID；capacity=1 时 12 个排队作业产生 12 条线程。`parallel_probes`、`race_probes` 02、`audit_probes` 25、`followup_probes` 08。**部分失败**。项目文档明示不支持多 Worker 共目录，该项按条件性风险报告。 |
| 16 | 本机 Worker HTTP 无 Token、32,769 字节请求体、无效 JSON、无效 UTF-8；本地快退出大输出；本地 Git 硬链接 | 拒绝非法输入、限制资源并隔离可信源仓库 | 401/大请求/无效 JSON 正常拒绝；无效 UTF-8 异常断开；128 字节上限下 2,207 字节日志仍 COMPLETED；本地 Git 对象文件与源仓库共享且测试句柄可写。未写入对象字节。`network_probes`、`resource_probes`、`hardlink_probe`。**失败**。 |
| 17 | Windows 原始 Worker→Coordinator；另对报告写入使用 LF 模拟 Linux | 平台间可回收报告 | Windows 两 Worker 都 COMPLETED，但报告 SHA 与 Coordinator 重算不符，席位不足；LF 模拟后完整本机链路收两席。`two_workers_http_probes`、`linux_newline_realhttp`。**Windows 失败；真实 Linux 及 POSIX/Windows 进程树终止均未实测**。 |

## 7. 按严重度排序的缺陷清单

以下路径均相对于 `source/`。测试脚本均位于审计目录而不是源仓库；原始输出在同名 `evidence/*.log`。

### P0-01：逻辑身份可冒充物理双席

**位置**：`blindreview/coordinator.py:28-33,106-111,123-130,201-205`；`README.md:20-21` 明确把实际物理拓扑交给操作者。

**触发/证据**：把同一 Windows 主机中的两个本机 HTTP Worker 配置为 `5bao`、`9bao`，监听不同端口，使用同一模拟审查内容，仅按 Job ID 改变报告；LF 写入模拟下经真实 HTTP、SQLite 和 Git 得到 `QUORUM_MET`，两席均接受。完整输出 `evidence/linux_newline_realhttp.log`；无 LF 适配的 Windows 链路被 P1-02 阻断，见对应日志。另有纯 FakeClient 复现 `identity_probe.py`。

**影响**：配置错误、身份冒用或服务被控制时，无法保证两份独立物理审查。此项并不声称真实 5bao/9bao 同机；它说明本软件不验证该条件。

**修复**：将已批准的物理节点清单与每节点独立凭据绑定，双向认证/固定公钥并由可信部署与审计证据核实物理归属；对同源和重复审查内容进行标记或去重，不能只依赖 ID、端口、报告自报或哈希。保留人工与外部节点证明的信任边界。

### P0-02：报告任务与契约冲突仍可达到双席

**位置**：`blindreview/common.py:62-70`，`blindreview/worker.py:108-116,221`，`blindreview/coordinator.py:123-130`。

**触发/证据**：`contract_probes.py` 给两个报告附加 `task_id=OTHER_TASK`、错误 `contract_sha256`，同时其 job/commit/role 和规范哈希正确；结果 `QUORUM_MET`。`validate_report` 只比较 job_id、commit_sha、role，不校验这两个明确冲突字段。Worker 对提交时本地契约有检查，但报告自身没有可验证绑定。

**影响**：报告与任务和角色契约不一致时仍可能被计入正式席位。

**修复**：定义版本化报告 envelope，强制纳入并校验 task ID、contract SHA、配置/矩阵指纹、节点与 Job ID；由可信端签名并验证，冲突或缺失均不得计席。模型实际执行仍需独立调用证据。

### P0-03：本地 Git 克隆与源仓库共享可写对象硬链接

**位置**：`blindreview/worker.py:89-92,215-220`，`examples/worker.5bao.json:8-10`。

**触发/证据**：仓库别名指向本地仓库时，Worker 使用默认 `git clone`；`hardlink_probe.py` 在隔离目录执行同样的本地克隆，源仓库和克隆的三个 pack/index 文件设备号及文件 ID 一致，源文件链接数为 17，且测试副本可打开可写句柄。测试**没有写入任何 Git 对象字节**；随后 `git fsck --full` 成功、工作树干净。原始日志 `evidence/hardlink_probe.log`。

**影响/修复**：若真实部署的 Harness 具备对克隆 `.git/objects` 的写权限，对共享对象的修改会同时影响可信源仓库，可能造成严重数据损坏；此项未在真实节点验证，也没有修改或损坏真实仓库。对本地源使用 `git clone --no-hardlinks` 或 `--no-local`，在独立低权限沙箱中运行，并验证对象不共享硬链接及源仓库 ACL。

### P0-04：排队任务重启后可能使用错误的角色契约

**位置**：`blindreview/worker.py:27-29,50-52,54-64,76-83,107-118`。

**触发/证据**：`followup_probes.py` 测试 01 先用契约 A 提交并保留 QUEUED 作业，在隔离测试文件中将契约换成 B，再重建 Worker；原请求仍记录 A 的哈希，但实际 prompt 使用 B，任务返回 COMPLETED、报告摘要为 `CONTRACT_B`。

**影响/修复**：真实配置漂移加重启即可使作业偏离已批准的角色契约，结合 P0-02 可能被计入双席。本测试未调用真实模型。恢复和执行前重新验证请求中的契约及关键配置指纹，或为作业固定不可变契约快照；不一致应失败关闭且不得启动 Harness。

### P1-01：跨 origin 重定向泄露 Bearer Token

**位置**：`blindreview/http_client.py:24-30`。

**复现/证据**：`network_probes.py` 测试 09：一个本地 HTTP 端点重定向到另一端口；第二个端点观测到 Authorization。只使用合成 Token，未读取真实凭据。

**影响/修复**：恶意或被劫持的 Worker/代理可使 Token 发往非原目标。关闭重定向或严格校验 scheme、host、port，跨 origin 不转发 Authorization；使用已认证 TLS 并固定服务身份。

### P1-02：Windows Worker 报告哈希不兼容

**位置**：`blindreview/worker.py:221-224`，`blindreview/coordinator.py:128-131`。

**复现/证据**：`two_workers_http_probes.py` 中两个真实本地 Windows Worker 完成任务，但都得到 `Report SHA256 mismatch`，最终 `FAILED_INSUFFICIENT_REVIEWERS`。实测 report.json 尾部为 CRLF；Coordinator 对 canonical JSON 加 LF 后算哈希。`evidence/two_workers_http_probes.log` 与对应状态文件含完整输出。

**影响/修复**：Windows Worker 正常报告无法被接受。双方明确使用相同 UTF-8 字节规范，二进制写入固定 LF 并对完全相同的 bytes 哈希；增加真实 Windows Worker→Coordinator 回归。

### P1-03：报告瞬时拉取失败会被提前定为终态

**位置**：`blindreview/coordinator.py:112-121,123-131,139-153,217-218`。

**复现/证据**：`audit_probes.py` 测试 15：一份报告已收，另两节点状态 COMPLETED 但首次 report 调用注入 TransportError；首轮即 `FAILED_INSUFFICIENT_REVIEWERS`，并未重试。`_receipt` 先把作业设为 COMPLETED，再尝试 `_collect`；异常后全终态分支提前结束。

**影响/修复**：网络瞬断或 HTTP 500 可使已完成的合法报告永远丢失。区分执行终态与报告回收状态，保留可重试状态，在截止前重取；对明确不可恢复错误单独计入失败。

### P1-04：600 秒宽限和总截止不严格

**位置**：`blindreview/coordinator.py:34-38,186-215,251-256`。

**复现/证据**：`default_timing_probes.py` 用模拟时钟、默认 60 秒轮询、每次第三节点状态耗时 7 秒，记录 603 秒；`audit_probes.py` 测试 17 用 400 秒轮询得到 800 秒；测试 18 接受 1200 秒宽限；测试 19 在第二份已接受后，等待第三状态额外 50 模拟秒才记录 quorum；测试 16 在总截止时仍收第三份。

**影响/修复**：违背第二份后最多 600 秒和总截止约束，可能延长模型运行及费用。对宽限设置硬上限，在第二份报告验收时立即持久化时间，逐请求与休眠前计算最近截止；处理重启和系统时钟回拨。

### P1-05：stdin 写阻塞绕过 Worker 心跳和硬超时

**位置**：`blindreview/worker.py:133-173`。

**复现/证据**：`worker_probes.py` 使用 300,000 字节测试契约和本地 3.5 秒自然结束的 Python 子进程，该子进程不读 stdin；配置硬截止 1 秒。1.7 秒后仍 RUNNING，心跳约 1.91 秒没更新；约 3.88 秒才报告 TIMED_OUT。未调用真实模型。

**影响/修复**：`proc.stdin.write()` 在心跳和超时循环之前阻塞；若子进程持续不读，无法保证及时超时或取消。使用非阻塞输入/受控写线程并让独立 watchdog 负责心跳与时限；限制契约和 prompt 尺寸并关闭管道。

### P1-06：畸形报告和截断 HTTP 可使 Coordinator 异常退出

**位置**：`blindreview/common.py:71,77-79`，`blindreview/http_client.py:30-39`，`blindreview/coordinator.py:139-153`，`blindreview/__main__.py:41-46`。

**复现/证据**：`crash_probes.py` 传 `verdict=[]` 到实际 Coordinator.step，抛 `TypeError: unhashable type: 'list'`；`network_probes.py` 测试 08 的真实本地截断 chunked 响应抛未转换的 `http.client.IncompleteRead`。

**影响/修复**：坏响应可中断轮询和取消收敛。先做严格类型检查并归一为 ProtocolError；将 HTTPException/IncompleteRead 等归一为 TransportError；主循环保证持久状态和必要的取消意图。

### P1-07：两个 Coordinator 可同时创建不同批次

**位置**：`blindreview/coordinator.py:71-101,103-104`。

**复现/证据**：`audit_probes.py` 测试 25，在两个 Coordinator 检查状态文件不存在后用屏障同步落盘；两个 initialize 均成功，生成不同 run ID，最终只有一份 state.json 可见。

**影响/修复**：若两个进程随后分别提交，将创建不同 Job ID，产生双执行/重复计费和状态覆盖风险；本次未实际启动重复模型。用 OS 锁、事务型租约与 fencing token，初始化使用排他创建，恢复也必须取得独占权。

### P1-08：Worker 子进程继承服务秘密并可写入日志

**位置**：`blindreview/worker.py:126-136,189-191,371-375`。

**复现/证据**：`resource_probes.py` 测试使用进程内合成 Token；本机假 Harness 读取到该变量，且明文存在 `execution.log`。Popen 未传隔离的 env，实际 Worker 的 Token 也从进程环境获取。未读取、传递或输出真实 Token。

**影响/修复**：受攻击或配置错误的 Harness 可读取服务环境，日志可能留存秘密。采用独立低权限身份和最小环境白名单，服务 Token 不传入模型子进程，凭据按用途隔离，输出脱敏与文件权限受控。

### P1-09：事后 Git 状态检查不能强制只读

**位置**：`blindreview/worker.py:218-220`，`.gitignore:1-2,9-13`，`examples/worker.5bao.json:34-47`。

**复现/证据**：`workspace_probes.py` 运行故意写入工作副本 `.pytest_cache/audit-fixture.txt` 的本地假 Harness；Git 状态为空，Worker 却返回 COMPLETED。

**影响/修复**：被忽略文件、`.git` 和工作区之外的副作用不由此检查覆盖。该测试没有证明真实 Codex/OpenCode 已绕过其各自沙箱；项目也要求外部配置权限。上线需事前只读挂载、隔离低权限执行、受限网络/凭据，并审计被忽略路径与外部副作用。

### P1-10：第二份报告落盘后崩溃会重置计时或错误失败

**位置**：`blindreview/coordinator.py:119-121,133-137,186-205`。

**复现/证据**：`followup_probes.py` 测试 02-03 在两份模拟形式合法报告均保存而 `quorum_at` 尚未保存时注入模拟进程退出。601 秒后恢复，会把计时起点重置到恢复时刻；若恢复时间已超过总截止，则返回 `FAILED_QUORUM_TIMEOUT`，尽管两份模拟报告已在截止前保存。

**影响/修复**：宽限期可被延长，或已满足双席的任务被误判失败。第二份报告持久化与 quorum 时间必须原子提交；恢复时应根据已持久化的第二份 `accepted_at` 重建并在处理总截止前判断。

### P1-11：Worker 监控异常后遗留失去跟踪的子进程

**位置**：`blindreview/worker.py:151-176,225-230`。

**复现/证据**：`followup_probes.py` 测试 04 对真实本地 Worker 注入心跳写入异常；作业标为 FAILED 时，2.5 秒的测试子进程仍存活、且已从 `_running` 移除。测试等待该子进程自行退出，没有运行真实模型。

**影响/修复**：网络费用、CPU/内存及后续重试可能与残留进程重叠。异常路径必须保留进程所有权，受控终止并等待整棵进程树，未确认停止时显式保留待对账状态；POSIX/Windows 真正进程树终止仍需各平台独立实测。

### P1-12：HTTP socket 超时不是整个响应的绝对期限

**位置**：`blindreview/http_client.py:24-39`，`blindreview/coordinator.py:195-200,251-256`。

**复现/证据**：`followup_probes.py` 测试 07 使用本地 HTTP 服务每 0.07 秒发送少量数据；客户端配置 0.15 秒超时，完整响应实际花费 0.578 秒仍被接受。仅验证了有限时长的慢速响应，没有无限等待实验。

**影响/修复**：持续低速发送可使串行轮询错过其他节点的回收与取消时间。为每次完整响应实施绝对截止、限制响应读取速率/字节，并用有界并发隔离单个慢节点。

### P1-13：Worker 排队为每个作业创建线程，缺少队列上限

**位置**：`blindreview/worker.py:37-38,62-78,301-310,379`。

**复现/证据**：`followup_probes.py` 测试 08 将 capacity 设为 1，在受控阻塞下提交 12 个不同 Job ID；产生 12 条排队线程、没有启动 Harness 子进程。持有效 Token 的请求可触发该路径；未认证慢请求的资源消耗只作静态风险提示，未实测。

**影响/修复**：持续提交可耗尽线程和内存，capacity 只限制执行而不限制排队。使用有界持久队列和固定线程池，对并发连接、请求读取期限和单身份速率设置上限。

### P2-01：取消回执中的迟到报告被标记有效

**位置**：`blindreview/coordinator.py:119-121,155-165,201-215`。

**复现/证据**：`race_probes.py` 测试 03：600 秒截止时第三席的 cancel 回执返回 COMPLETED；`accepted_nodes` 仍为两席，但第三作业 `valid=true`。

**影响/修复**：状态、摘要与截止语义不一致，后续使用方可能误读。取消回执仅对账终态，超期后不得按普通 `_receipt` 收取第三份；原子刷新一致的汇总。

### P2-02：取消补偿后 summary 仍是旧状态

**位置**：`blindreview/coordinator.py:167-183,221-249`。

**复现/证据**：`audit_probes.py` 测试 21：reconcile 后 `state.json` 为 CANCELLED，而 `summary.json` 仍 RUNNING。

**影响/修复**：下游看到过期取消结果。明确 summary 是快照或当前状态并标注版本，补偿成功后原子刷新，避免覆盖原始审计事件。

### P2-03：快速退出可绕过日志大小限制

**位置**：`blindreview/worker.py:152-165,173-191`。

**复现/证据**：`resource_probes.py` 测试 01：设置 128 字节限制，快速退出的本地假 Harness 输出 2,207 字节，Worker 仍 COMPLETED。

**影响/修复**：快速输出可能突破资源预算；循环外需要再次验证大小，使用受限管道/文件系统配额，避免只依赖 0.5 秒轮询。

### P2-04：多 Store 共用 SQLite 时可双重领取

**位置**：`blindreview/store.py:55-71`；`README.md:92` 明确禁止多个 Worker 共用数据库。

**复现/证据**：`race_probes.py` 测试 02 用两个 SQLite 连接同步读同一 QUEUED 后迁移；两次 transition 均返回 True。

**影响/修复**：在文档明示不支持的双 Worker 部署或重复启动条件下，可能双执行。使用条件更新 `WHERE state='QUEUED'` 并检查受影响行数，配合租约和独占运行器锁；同时保留禁止共库部署的运维约束。

### P2-05：无效 UTF-8 请求未正常返回 400

**位置**：`blindreview/worker.py:301-310,319-334`。

**复现/证据**：`network_probes.py` 测试 10 向本机 Worker Handler 发送单字节 `0xff`，服务抛 UnicodeDecodeError，客户端收到 RemoteDisconnected，而非 HTTP 400。

**影响/修复**：错误客户端触发堆栈和异常断连；捕获 UnicodeDecodeError，规范化为 400 并限制请求读取时长。

### P2-06：finding 的位置只要求非空字符串

**位置**：`blindreview/common.py:77-83`。

**复现/证据**：`audit_probes.py` 测试 29 中 `location='not-a-file-or-line'` 被接受。

**影响/修复**：无法保证每条 finding 有可核查的位置或证据。建立明确的文件/行号或证据对象结构，核对工作区范围和存在性；不能仅凭格式推断审查事实真实。

### P2-07：Worker 验证 Token/绑定端口前即启动恢复队列

**位置**：`blindreview/worker.py:42-52,371-379`。

**触发/证据**：源码顺序显示 `Worker(config)` 在校验 Token 长度和绑定服务之前执行，构造函数会对 QUEUED 作业调用 schedule；此项为静态结论，未在本次启动带真实遗留队列的服务验证。

**影响/修复**：缺失 Token 或端口绑定失败时，已有队列仍可能先开始副作用。先完整验证配置、权限、身份和监听资源，再显式启动队列；启动失败时关闭所有已分配资源。

### P2-08：Coordinator 的本地报告文件哈希与记录值不一致，恢复时不重验

**位置**：`blindreview/coordinator.py:54-66,71-78,123-137,186-189`。

**复现/证据**：`followup_probes.py` 测试 05：状态中记录的是紧凑 canonical JSON 加 LF 的 SHA256，而本地报告以缩进 JSON 保存，文件原始字节的 SHA256 与记录值不同。测试 06 在隔离目录改写合成的报告文件，恢复仍直接返回 `QUORUM_MET`，没有重新核对报告。

**影响/修复**：用户不能把记录值直接当作保存文件原始字节哈希，且本地有写权限的进程篡改报告后恢复不会察觉。明确哈希算法并保存同一规范化字节，在恢复前复验报告和状态；此问题以本地写权限为前提。

### P2-09：最终状态已保存但摘要写入失败后无法自动重建

**位置**：`blindreview/coordinator.py:167-184,186-189`。

**复现/证据**：`summary_crash_probe.py` 模拟 `summary.json` 写入异常；重新 resume 后返回 `QUORUM_MET`，但 summary 文件仍不存在。

**影响/修复**：下游按 CLI 输出路径读取摘要会失败。持久化结果与摘要使用可恢复的事务/日志；resume 发现摘要缺失或不一致时重建并核对。

### P3-01：取消补偿测试名高于实际覆盖

**位置**：`tests/test_pipeline.py:272-280`；`docs/TEST_RESULTS.md:8`。

**复现/证据**：名为 `test_reconcile_cancel_after_interrupted_network` 的用例所用 FakeClient.cancel 总是成功，并未注入网络故障。独立 `audit_probes.py` 测试 20 才人为注入回执丢失。

**影响/修复**：测试名称及覆盖描述容易使人高估网络恢复验证；补充真实客户端异常、取消后响应丢失、重启与重复补偿的用例，明确 Mock 边界。

## 8. 安全评估与真实节点部署前阻断项

已确认：HTTP 未授权返回 401，Worker 请求体有 32,768 字节上限；命令使用参数数组，未使用 `shell=True`，Git 来源受 Worker 配置别名约束。均不能替代隔离或链路认证。

必须阻断真实三节点部署的事项：

1. 修复并重新验证 P0-01 至 P0-04，建立与真实物理节点绑定的独立身份、报告完整上下文、不可变契约及与源仓库隔离的克隆；两份格式报告不能当成代码 APPROVE。
2. 修复重定向凭据泄露、子进程秘密隔离和只读执行边界；所有通信须通过可信加密链路并固定服务身份，端口仅暴露给授权客户端。
3. 修复 Windows 哈希、网络中断异常、报告回收、崩溃恢复、第三席截止、硬超时/心跳、孤儿进程和并发租约；为取消补偿建立实际可运行的对账。
4. 目标环境逐节点核实 Git 固定提交拉取、磁盘权限、进程限制、日志权限、端口、Token 权限以及服务端实际身份。不得将此报告的本地回环测试说成跨机网络验收。
5. 在用户授权下核验真实 Codex/OpenCode 命令、Agent 权限、批准的任务模型矩阵和实际调用日志；P0 README 明确将任务级审批矩阵及模型供应商实用模型核验列在 P1 范围，本报告将其作为**集成阻断项**，不把这些尚未承诺的 P1 功能本身算作 P0 实现缺陷。
6. 明确 Pipeline Phase 5.0 的输入输出契约：当前结果只是报告席位计数，后续审查结论、整改、仲裁与人工发布审批另行执行。

本机本次仅做无模型调用的 `--version` / `--help`：Codex CLI 0.166.0 的 exec 帮助列出 `--sandbox`、`--model`、`--output-last-message`、`-C`；OpenCode 1.19.3 的 run 帮助输出在 stderr，列出 `--model`、`--agent`、`--format`。当前审计进程 PATH 未解析到 `codex`，但直接路径 `D:/codex/codex-agent.exe` 存在并能显示帮助。以上不证明三个远端节点的安装状态、参数兼容、角色权限或实际模型。

## 9. Mock 与真实能力的差距、剩余未验证项

- 项目自带 Coordinator 测试全部使用 FakeClient，因此没有覆盖 Windows Worker 文件哈希与 Coordinator 实际计算之间的差异；本次本机全链路已暴露该问题。
- 假模型输出无法证明真实 CLI 可接受 prompt、按批准矩阵调用对应模型、以只读权限审完整代码、输出预期 JSONL、准确报告发现。
- 未访问真实 5bao、9bao、rusty；因此网络、端口、服务身份、TLS、Git 源、磁盘和节点实际拓扑均**未测试**。
- 未实测 Linux/POSIX `killpg`、Windows `taskkill /T /F` 对进程树的终止行为、真实异常断电或强杀、真实磁盘写满、服务端模型请求停止与计费、进程 PID 复用及长期稳定性。LF 模拟只是 Windows 进程内指定换行，不是 Linux 实测。
- 未运行高费用模型任务，未检验真实 `MODEL_ASSIGNMENT.md` 与实际供应商日志。P0 测试样例和本次审查均不能宣称这部分通过。
- 项目文档承认多 Worker 不得共用目录，且将实际物理节点独立性作为操作者责任；即使按该假设运行，也需要在部署前落实可审计的独立性证明。

## 10. 证据与复现索引

所有证据在审计根目录中：

- `evidence/baseline_unittest.log`：适配后的 14 项发现、13 通过、1 跳过及耗时。
- `evidence/baseline_compileall.log` 与 `evidence/compile_copy.log`：首次路径失败与源码哈希一致副本通过。
- `evidence/audit_probes.log`、`network_probes.log`、`worker_probes.log`、`resource_probes.log`、`race_probes.log`、`parallel_probes.log`、`workspace_probes.log`、`contract_probes.log`、`adapter_probes.log`、`crash_probes.log`、`default_timing_probes.log`、`followup_probes.log`、`hardlink_probe.log`、`summary_crash_probe.log`。
- `evidence/two_workers_http_probes.log`：Windows 原样双 Worker 闭环失败；`evidence/linux_newline_realhttp.log`：仅 LF 写入模拟后的本机双 Worker 计席结果。
- `evidence/codex_version.log`、`codex_exec_help.log`、`opencode_version.log`、`opencode_run_help.log`：本机帮助及版本。
- `evidence/final_git_verification.log`：最终 HEAD、干净状态与 `git fsck --full` 结果。
- 所有同名 `*_probes.py`、`run_probes.py` 为独立临时测试文件，没有更改 `source/`。这些测试会在隔离目录创建文件、监听本地回环并启动受控测试子进程；Worker 原始取消/超时代码可能对其**自身测试子进程**发终止请求。不要对生产 Worker 或真实模型环境直接运行故障注入。

最终判定再次明确：**FAIL**。本报告证明了若干缺陷，也明确列出模拟和未验证范围；它不声称真实三节点环境已经访问或验收。
