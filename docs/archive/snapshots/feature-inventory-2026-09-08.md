# codeagent 功能点完整清单

> 分析日期：2026-09-08 · 版本：`v0.4.0`（`pyproject.toml`）· 分析范围：`src/codeagent/` 全量 + `tests/` + `scripts/` + `openspec/`
> 数据来源：六个独立调研代理分头逐文件通读 `core/`、`session/`、`ai/`+config、`tools/`、`app/`(非 TUI)、`app/tui/`，以及测试与工程化体系。

---

## 一、项目总览

### 1.1 定位

自研的 **AI 编码代理（coding agent）**：终端内运行的 ReAct 循环代理，能读写文件、执行命令、调用 MCP 工具、派生子代理，并把全过程以 JSONL 追加日志持久化，支持会话树分叉、自动压缩与崩溃恢复。

核心设计取向：**不依赖 langchain 等编排框架**，自研消息模型、工具契约、事件总线与 ReAct 主循环；通过 Protocol（端口）+ 组合根注入实现严格分层。

### 1.2 技术栈

| 项 | 内容 |
|---|---|
| 语言 / 运行时 | Python ≥ 3.12 |
| 依赖（仅 5 个） | `httpx`、`mcp`（官方 SDK）、`pydantic-settings`、`pyyaml`、`textual` |
| 包管理 / 构建 | `uv` + `uv_build` |
| 终端 UI | Textual 2.x |
| 入口 | `codeagent = codeagent.app.main:main` |
| 配置目录 | `~/.codeagent/`（`.env`、`models.json`、`mcp.json`、`skills/`、`packages/`） |

### 1.3 代码规模

| 包 | 文件数 | 行数 | 职责 |
|---|---:|---:|---|
| `app/` | 140 | 15,659 | 组合根、CLI、无头模式、技能、任务校验、TUI（占比最大） |
| `session/` | 63 | 7,609 | 会话状态机、JSONL 持久化、压缩、会话树 |
| `core/` | 40 | 5,130 | 领域模型、协议、ReAct 编排、上下文治理、工具执行运行时 |
| `tools/` | 43 | 4,324 | 8 个内置原子工具、安全策略、命令执行、MCP 客户端 |
| `ai/` | 26 | 1,994 | Provider、OpenAI 兼容传输、SSE 解析、重试、模型目录 |
| **生产代码合计** | **312** | **≈34.7k** | |
| `tests/` | 162 | ≈28k | 1,284 个测试函数 |

### 1.4 分层架构与依赖方向

```
app/          组合根：容器、CLI、TUI、技能、任务校验      ← 唯一允许 import 所有层
  ├── composition/   依赖装配（model/runtime/session/subagent/tools/tui）
  └── tui/           终端 UI（可替换后端）
        ↓
ai/  tools/  session/         外部适配层（互不依赖）
        ↓  注入端口
core/        领域模型 + 协议 + 编排     ← 不 import 任何外层
```

**架构约束**（`AGENTS.md` 明文规定，由 `tests/test_decoupling.py` 用 AST 强制校验）：
- `core/` 不得 import `config` / `ai` / `tools` / `session`
- `session/` 不得 import `ai` / `tools` / `config`
- 依赖只能沿"外 → 内"方向流动；跨层装配必须放 `app/composition/`

---

## 二、功能点清单

### A. Agent 编排核心（core/orchestration、core/agent）

| # | 功能点 | 用途 | 核心逻辑概要 | 代码位置 |
|---|---|---|---|---|
| A1 | **ReAct 主循环** | 驱动"模型生成 → 工具调用 → 结果回填"的完整代理回合 | 自研循环 `for iteration in range(recursion_limit)`，默认上限 50；每轮 `run_turn` 生成消息，无 `tool_calls` 即结束，超限抛 `RecursionLimitError`；全程发 `AGENT_START/TURN_START/TURN_END/AGENT_END` | `core/orchestration/loop.py::run_agent_loop`、`turn.py::run_turn` |
| A2 | **工具批次执行** | 一次模型响应里的多个工具调用并行/串行执行 | `execute_tool_batch` 支持 parallel/serial 配置；parallel 用 `as_completed` 但按模型原始顺序回填 `results[index]` 保序；发 queue/start/update/end 四类事件 | `core/orchestration/batch.py` |
| A3 | **工具调用生命周期** | 统一处理参数错误、未知工具、hook、拒绝、异常 | `new_tool_result` 把所有失败路径归一化为 `ToolResult`；执行 before/after hook，拒绝与异常不污染循环 | `core/orchestration/tool_call.py` |
| A4 | **取消与中断** | 用户 Esc / Ctrl+C 能真正停下手上的活 | 捕获 `asyncio.CancelledError` 发 `ABORTED` 并上抛；`Agent.abort` 取消底层 task；批次内对进行中/排队工具补发 `CANCELLED` 结果 | `core/orchestration/loop.py`、`core/agent.py::Agent.abort` |
| A5 | **有状态 Agent 门面** | 对外暴露对话入口并保证失败可回滚 | `Agent` 持有 `AgentContext`，提供 `prompt`/`continue_`/`abort`/`steer`(运行时注入引导)/`follow_up`(空闲即发、运行中排队)/`subscribe`；**循环在 context 副本上运行，成功后才提交**，天然回滚边界 | `core/agent.py` |
| A6 | **生命周期钩子** | 让外层无侵入地观测/介入代理行为 | `LifecycleHook` 把 core 事件按 (scope, phase) 分类分发；订阅方异常被隔离并收集为 `HookDiagnostic`，不中断主流程 | `core/support/observation.py`、`core/contracts/hooks.py` |

### B. 上下文治理（core/context）

| # | 功能点 | 用途 | 核心逻辑概要 | 代码位置 |
|---|---|---|---|---|
| B1 | **上下文预算估算** | 在发请求前知道还剩多少空间 | 按 **字符数 ÷ 4** 估算 token（非真实 tokenizer）；分项统计 system/工具定义/对话/工具结果；`input_budget = context_window − output_reserve − reserve_tokens`；窗口来源不明时状态标 `uncertain`，默认 128k | `core/context/budget.py::estimate_context_budget` |
| B2 | **工具结果裁剪** | 防止单个巨型工具输出撑爆上下文 | 仅对 `role=="tool"` 消息按剩余预算**均分**配额，超限者降级为"元数据摘要 + 截断正文"（保留结构化事实）；返回**只读 detached 视图，不改历史** | `core/context/budget.py::govern_tool_messages` |
| B3 | **上下文预检 Preflight** | 在真正发请求前拦住必然超限的情况 | 无 I/O、不触发压缩；判定 `safe/near_limit/over_limit/uncertain`；`over_limit` 直接抛 `ContextPreflightError` 阻断 | `core/context/preflight.py::evaluate_context_preflight` |
| B4 | **上下文转换扩展点** | 允许外层注入自定义上下文加工 | `invoke_context_extension` 支持同步/异步/线程池执行并带超时，超时转 `ContextTransformTimeoutError`；`materialize_context_messages` 校验返回值为合法 `Message` 集 | `core/context/transform.py` |
| B5 | **上下文诊断快照** | 让用户看到上下文被谁吃掉了 | `ContextDiagnostics` 只读聚合：各组件占比、使用率、压缩次数、工具结果治理、最近失败；供 `--context` 与 TUI `/context` 共用 | `core/context/diagnostics.py`、`app/context_diagnostics.py` |
| B6 | **模型请求准备** | 把"上下文准备"串成一条完整管线 | `prepare_context` 依次执行 transform → budget 描述 → preflight → 裁剪，并广播 `CONTEXT_BUDGET`/`CONTEXT_PREFLIGHT` 事件 | `core/model/request.py::prepare_context` |

### C. 契约与领域模型（core/contracts）

| # | 功能点 | 用途 | 核心逻辑概要 | 代码位置 |
|---|---|---|---|---|
| C1 | **端口协议集** | 定义"核心不依赖任何外部实现"的边界 | `ModelPort`（generate/stream）、`AgentTool`（execute+signal+on_update）、`ToolExecutionRuntimePort`、`ToolCleanupPort`、`Summarizer`、`ApprovalPolicy` | `core/contracts/ports.py` |
| C2 | **自研消息模型** | 替代 langchain 的消息体系 | `Message`/`ToolCall`/`ToolResult`；`new_id` 手写 **uuid7**（时间有序便于排序）；`remove_by_id`/`replace_or_append` 提供归约语义 | `core/contracts/messages.py` |
| C3 | **事件模型** | 全流程可观测的统一载体 | `EventType` 约 40 种 + `AgentEvent`；含 `SUBAGENT_EVENT_TYPES` 子集 | `core/contracts/events.py` |
| C4 | **错误体系** | 用明确异常表达领域错误，不用 `None` 掩盖 | `AgentRuntimeError` 基类 + `ContextPreparationError`/`ContextPreflightError`/`ContextTransformTimeoutError`/`AgentContinueError`/`Subagent*Error` | `core/contracts/errors.py` |
| C5 | **工具输出元数据** | 让模型知道输出是否被截断 | `ToolOutputMetadata`/`OutputCompleteness`、`ToolLifecycleStatus`/`ToolStatusSnapshot`（含归一化与序列化） | `core/contracts/output.py`、`tool_status.py` |
| C6 | **子代理契约群** | 定义子代理的完整数据契约 | `SubagentRequest`/`SubagentResult`/`SubagentState`/`SubagentStatus`(11 态)/`SubagentBudget`/`SubagentFinding`/`SubagentEvidence`；设严格长度上限（summary ≤16k、findings ≤16、evidence ≤32） | `core/contracts/subagents.py`、`subagent_*.py` |

### D. 工具执行与内置工具（core/execution + tools/）

| # | 功能点 | 用途 | 核心逻辑概要 | 代码位置 |
|---|---|---|---|---|
| D1 | **有界工具运行时** | 限制并发、超时、可取消、可清理 | `asyncio.Semaphore(max_concurrency=4)` 限并发；`OperationRegistry` 跟踪活动操作；`asyncio.wait_for` 实现超时；超时/取消均触发 `CleanupTracker.cleanup` | `core/execution/runtime.py::ToolExecutionRuntime` |
| D2 | **清理状态追踪** | 区分"已确认清理"与"清理不确定" | `CleanupTracker` 按保守度排名表取最差状态，输出 `cleanup_confirmed` / `cleanup_uncertain`，避免对用户谎报进程已停 | `core/execution/cleanup.py` |
| D3 | **结果归一化** | 把工具任意返回值变成规范结果 | `normalize_tool_result` 处理 `error`/`status`/`cleanup_confirmed` 推导 | `core/execution/result.py` |
| D4 | **8 个内置原子工具** | 代理的手和脚 | 见下方"能力矩阵 2.1"；均为无状态 `AtomicTool` 子类，依赖注入 `cwd`+`FsOps`+`ToolResourceLimits` | `tools/atomic/*.py`、`tools/registry.py::make_tools` |
| D5 | **命令执行** | 跑 shell 命令并安全收尾 | 每次 `subprocess.Popen([bash,"-lc",cmd])`，**无持久 shell 会话**（非交互、无状态）；输出先写临时文件再物化并支持 tail 截断；超时后 kill 进程树 | `tools/execution/process.py::ProcessRunner`、`shell.py::resolve_bash` |
| D6 | **跨平台进程清理** | 尽可能确保子进程被杀干净 | POSIX：`start_new_session` + `os.killpg` 杀进程组（可确认）；**Windows：`taskkill /T`，源码注释明确"不能证明全树停止"，恒返回 False → 标记 `cleanup_uncertain`** | `tools/execution/posix.py`、`windows.py` |
| D7 | **输出截断** | 防止超长输出冲爆上下文 | 字节 + 行**双重上限**（默认 30,000 B / 2,000 行），head/tail 两种模式 | `tools/shared/truncate.py` |
| D8 | **诊断脱敏** | 错误信息里不泄露密钥 | `redact_metadata_text` 对 key/token/password 等模式脱敏 | `tools/shared/governance.py` |
| D9 | **写串行化** | 避免并行 write/edit 相互覆盖 | `mutation_queue` 按路径加 `threading.Lock` | `tools/shared/mutation_queue.py` |
| D10 | **换行/BOM 保持** | Windows 上 edit 不会把整个文件换行符改写 | edit 前归一 CRLF/BOM → 匹配 → 还原 | `tools/shared/textfile.py` |
| D11 | **检索加速** | 大仓库搜索不慢 | 优先调用 `rg`（ripgrep `--json`）、`fd`，失败回退纯 Python 实现 | `tools/execution/search.py` |
| D12 | **环境能力探测** | 告诉上层"这台机器能干什么" | 只读探测平台、可用 bash/rg/fd、安全策略状态 | `tools/capabilities.py` |

### E. 安全策略（tools/security）

| # | 功能点 | 用途 | 核心逻辑概要 | 代码位置 |
|---|---|---|---|---|
| E1 | **三态审批决策** | 每次工具调用先过安全闸门 | `ALLOW` / `ASK` / `DENY`；`classify_tool` 按工具类型分发：bash→`classify_bash`，read/write/edit→`classify_file`，`mcp__*`→`classify_mcp`，其余 ALLOW | `tools/security/decision.py`、`classifier.py:290` |
| E2 | **bash 危险命令识别** | 挡住破坏性命令 | 判定顺序：① `_dangerous_hit` 字面正则 →DENY（仅 6 条：rm -f /、fork bomb、mkfs、dd if=/dev/*、`>/dev/sd*`）；② **`_dangerous_intent` 结构递归分析**（eval、嵌套解释器 `-c`、`rm -rf` 命中 `/`/`~`/cwd、未闭合 `$(...)`）→DENY；③ 敏感路径 →DENY；④ 约 20 条 ASK 规则（`git push`/`reset --hard`/`clean -f`、`sudo`、`chmod -R`、`rm -r`、`find -delete`、`docker` 挂根、`kill`、`curl\|sh` 等）；⑤ 白名单（ls/cat/grep/git status 等）→ALLOW | `tools/security/classifier.py:254`、`bash_rules.py:15` |
| E3 | **敏感文件保护** | 不让代理读到密钥 | 正则已覆盖 `.ssh/.aws/.gnupg/.netrc/.npmrc/.pypirc`、`.env`、`.codeagent`、各类 `id_rsa/ed25519`、`*.pem/*.key/*.pfx`、`credentials`/`secrets`/`tokens` 配置文件 | `tools/security/filesystem.py:11` |
| E4 | **Shell 语法分析** | 为安全判定提供可靠输入 | 基于 `shlex` 分词 + 按管道/控制符分段；**解析失败即拒绝**（fail-closed） | `tools/security/shell_parse.py` |
| E5 | **MCP 工具权限** | 第三方工具也要过审 | `mcp.json` 支持 `deny > ask > allow` 三级通配规则（`mcp__*`、`mcp__<srv>__*`） | `tools/mcp/permissions.py` |

### F. MCP 集成（tools/mcp）

| # | 功能点 | 用途 | 核心逻辑概要 | 代码位置 |
|---|---|---|---|---|
| F1 | **MCP 客户端** | 接入第三方 MCP 服务器提供的工具 | 基于官方 `mcp` SDK 的 `ClientSession`；**仅支持 stdio 传输**（配置只解析 `command/args/env`），无 http/sse | `tools/mcp/client.py`、`server_config.py` |
| F2 | **工具发现与适配** | 把 MCP 工具伪装成内置工具 | 每 server 起独立后台线程 + 事件循环 → `initialize` + `tools/list` → `McpTool` 适配器命名 `mcp__<server>__<tool>`，桥接同步调用 | `tools/mcp/loader.py:49`、`adapter.py` |
| F3 | **工具预算治理** | 防止 MCP 工具定义吃光上下文 | 全局上限 40 个 / 每 server 15 个 / 描述 200 字，超限裁剪并产出可见诊断 | `tools/mcp/adapter.py::apply_budget` |
| F4 | **启动容错** | 单个 MCP server 挂掉不影响整体 | 启动失败仅记录诊断并跳过，不中断启动流程 | `tools/mcp/loader.py` |

### G. 会话与持久化（session/）

| # | 功能点 | 用途 | 核心逻辑概要 | 代码位置 |
|---|---|---|---|---|
| G1 | **JSONL 追加式持久化** | 会话可长期保存、可重建 | 每会话一个 `<id>.jsonl`，append-only；派生索引 `<id>.index.json`；Mixin 组合 Reading/Writing/Forking/Indexing/Recovery | `session/persistence/jsonl/store.py:18` |
| G2 | **记录类型** | 结构化表达会话全过程 | `message`（含 tool_calls/tool_output）、`usage`、`compaction`、`meta`、`model_change`、`subagent` | `session/persistence/records.py` |
| G3 | **原子 turn 提交 + 回滚** | 一次回合要么全写要么不写 | 持锁批量追加后更新索引；异常时 `truncate` 回原始 size 并恢复索引（**已在 v0.4 修为 O(1) 定点截断，不再整文件回滚**） | `session/persistence/jsonl/writing.py:79,107` |
| G4 | **跨进程文件锁** | 多进程/多窗口同时操作不打架 | `PathLock` = 进程内 `threading.RLock` + **OS 咨询锁**（`fcntl.flock` / `msvcrt.locking`），sidecar `.lock` 文件，同进程按路径缓存支持重入，默认超时 30s | `session/persistence/locking.py:23` |
| G5 | **可重建索引** | 列表页不用读全部 JSONL | `SessionIndex` 派生 title/usage/压缩位置；`source` 指纹（size/mtime_ns/ctime_ns）校验过期；写入用临时文件 + `os.replace` 原子替换 | `session/persistence/index.py:19` |
| G6 | **崩溃恢复诊断** | 文件损坏时给可读结论而非崩溃 | `recovery_report` 逐行扫描，产出 `malformed_record`/`invalid_record`/`missing_header`/`incompatible_version`/`index_stale`/`compaction_cut_missing`；状态 healthy/degraded/unavailable | `session/persistence/jsonl/recovery.py:42`、`app/session_recovery.py` |
| G7 | **会话树与分叉** | 支持"从某轮重新来过" | 纯函数 `build_tree` 以 `parent_session` 建树（孤儿作根、环检测降级）；`fork` 复制目标 user 消息之前的窗口到新会话，**原文件零修改** | `session/navigation/tree.py:30`、`persistence/jsonl/forking.py:17` |
| G8 | **多会话管理** | 管理多个并行会话 | 创建/切换/继续最近/改名/换模型配置/归档/删除（删除需 `confirmed=True` 且禁删当前或运行中的会话） | `session/manager/operations.py` |
| G9 | **常驻会话 LRU** | 开很多会话也不爆内存 | 注册表维护有界字典，超 `max_resident_sessions`(默认 32) 淘汰最久未用（保当前） | `session/manager/registry.py:99` |
| G10 | **运行阶段状态机** | 精确表达"这一轮跑到哪了" | `RunState`/`RunPhase` 受限转换 IDLE→STARTING→…→FINALIZING→IDLE，非法跳变抛错 | `session/runtime/state.py:37` |
| G11 | **回合协调器** | 编排一次 run 的完整生命周期 | start→execute→finalize→commit→auto-compact→finish；失败/取消回滚内存历史并产出 `RunOutcome`（commit_status 区分 COMMITTED/ROLLED_BACK/PERSISTENCE_FAILED） | `session/run_coordinator.py:30` |
| G12 | **自动压缩** | 长会话不至于撑爆上下文 | 触发：占比 >0.8 或余量 <2048 tokens（目标 0.65）；以**完整 user-turn 边界**为切点，保留最近 ≥1 轮；注入式 `Summarizer.summarize(window, previous_summary)`；**只追加 compaction 记录、消息物理保留**，因此天然可回退 | `session/compaction/policy.py:156`、`service.py:79` |
| G13 | **文件操作追踪** | 压缩摘要里保留"改过哪些文件" | `extract_file_ops` 从 tool_calls 抽取 read/write/edit 路径累计进 details | `session/compaction/details.py:8` |
| G14 | **确认协调** | 危险操作等用户点头 | 注册/等待/超时/取消审批请求，超时抛 `ConfirmationTimeoutError` | `session/runtime/confirmation.py:23` |
| G15 | **错误分类与友好文案** | 把技术异常翻译成人话 | `classify_error` 映射为稳定 `RuntimeFailure`（含 retryable、副作用状态、预算元数据）+ `friendly_error` | `session/runtime/error_classification.py:23` |
| G16 | **副作用观察** | 判断"工具是否留下了不确定的副作用" | 据工具起止/清理不确定状态推导 `cleanup_uncertain` | `session/runtime/event_translation.py:231` |
| G17 | **同步事件总线** | 解耦 UI 与运行时 | `EventBus.subscribe` 返回取消函数，`emit` 按序扇出并隔离订阅方异常 | `session/events/bus.py:15` |
| G18 | **core→session 事件翻译** | 两套事件体系桥接 | 纯函数映射 `MESSAGE_UPDATE`/`TOOL_EXECUTION_*` → `THINKING_DELTA`/`TOOL_CALL`/`TOOL_STARTED`/`TOOL_RESULT` 等，继承父子字段 | `session/runtime/event_translation.py:10` |
| G19 | **内存存储后端** | 测试与一次性运行不落盘 | `MemoryStore` 提供与 JSONL 相同的事务语义 | `session/persistence/memory_store.py:23` |

### H. 模型接入与配置（ai/ + app/config.py）

| # | 功能点 | 用途 | 核心逻辑概要 | 代码位置 |
|---|---|---|---|---|
| H1 | **7 个 Provider** | 接多家模型厂商 | `deepseek`、`openai`、`qwen`、`glm`、`kimi`、`minimax`、`fake`；**均为 OpenAI 兼容端点**（无 anthropic）；各 provider 独立 `env_prefix` 与默认模型 | `ai/providers/*.py` |
| H2 | **Provider 注册表** | 新增厂商不改核心 | `BUILTIN_PROVIDERS` 元组 + `PROVIDERS` 工厂字典；新增 provider 只需加模块并入元组，core 零改动 | `ai/providers/all.py` |
| H3 | **OpenAI 兼容传输** | 不引重型 SDK | 直接构造 `/chat/completions`（仅 `httpx`）；校验 base_url 禁 query/fragment；复用单一 `AsyncClient` | `ai/transport/openai_compat.py` |
| H4 | **SSE 流式解析** | 支持流式输出与思考链 | 自研 `SSEParser`：`reasoning_content`→thinking、`tool_calls` 按 index 累积参数、`[DONE]` 收尾、usage 透传 | `ai/transport/sse.py` |
| H5 | **重试策略** | 抗网络抖动与限流 | 指数退避 `min(2**attempt, 10s)`，默认 3 次（上限 5）；优先尊重响应头 `Retry-After`；**流式仅在吐出首帧前重试**（避免重复消费）；可重试 = 网络/超时/408/429/5xx | `ai/transport/retry.py`、`streaming.py` |
| H6 | **分级超时** | 既不假死也不误杀慢请求 | 默认 connect=10 / read=120 / write=30 / pool=10；**流式 read=None**（防服务端 accept 后永不返回导致 TUI 假死） | `ai/transport/openai_compat.py` |
| H7 | **错误归一化** | 上层不必认识 httpx | `classify_provider_error` 输出 8 类 `kind`（network/timeout/rate_limit/authentication/invalid_request/unsupported_parameter/server/unknown）+ `retryable` 标志；detail 自动脱敏并提取 `x-request-id` | `ai/errors.py` |
| H8 | **模型能力目录** | 知道每个模型能干什么 | `ModelSpec`（reasoning/max_tokens/context_window/tool_calling/prompt_cache/aliases）frozen 值对象；内置静态目录 + 用户 `~/.codeagent/models.json` 按 id upsert；解析用**两遍法**（先精确 id 再别名）消除顺序依赖 | `ai/catalog/{spec,builtin,store,registry}.py` |
| H9 | **Fake Provider** | 离线可测 | 可脚本化 `response`/`steps`/`tool_calls`/`usage`/`thinking` 的 `FakeClient`，不联网不耗 key | `ai/providers/fake.py` |
| H10 | **安全凭据管理** | 防止在任意仓库被 `.env` 劫持 | 固定 `CONFIG_DIR=~/.codeagent`，**刻意不读仓库本地 `.env`**；`ensure_config_files` 幂等生成模板不覆盖；`write_env_key` 原子行级替换 + 权限 0600 + 防换行注入；`warn_cwd_env` 检测 CWD `.env` 仅告警一次 | `app/config.py` |
| H11 | **全局配置** | Provider 无关的运行时参数 | `llm_provider`(默认 deepseek)、`tool_max_concurrency=4`、`tool_timeout=None`、`tool_max_timeout=600`、`tool_max_output_bytes=30000`、`tool_max_output_lines=2000`、`tool_max_memory_bytes=1MB`、`tool_cleanup_timeout=10`；优先级 **CLI > 环境变量 > `~/.codeagent/.env` > 代码默认** | `app/config.py::Settings` |

### I. 组合根与应用层（app/ 非 TUI）

| # | 功能点 | 用途 | 核心逻辑概要 | 代码位置 |
|---|---|---|---|---|
| I1 | **依赖注入容器** | 集中装配，杜绝全局可变状态 | `container.py` 是纯 façade（71 行），实际装配在 `composition/*`；资源所有权委托 `AgentRuntime`，通过 `setattr(config,"_runtime_owner",self)` 挂在配置上，避免进程级单例 | `app/container.py`、`composition/runtime/factory.py` |
| I2 | **CLI 入口** | 命令行可用 | `--prompt`、`--tui`、`-c/--continue`、`--session <id>`、`--list-sessions`、`--context`（只读诊断）、`--yes`（放行敏感操作，headless 缺省一律 deny）；另有 `codeagent skill` 子命令：`install/update/remove/list/reload`（支持 `--project` 项目级） | `app/main.py` |
| I3 | **无头模式** | 管道化/脚本化调用 | 订阅事件队列与 `TaskSupervisor` 协程竞速，聚合文本增量、usage、子代理状态行；支持单行与 stdin 逐行循环；输出成本透明行（输入/输出/缓存命中率） | `app/headless.py` |
| I4 | **模型端口适配** | 把 ai 层接到 core 端口 | `ChatModelPort` 适配 `ai.ChatClient` → core `ModelPort`（流式、usage 归一、预算估计）；`LlmSummarizer` 复用同一通道做压缩摘要 | `composition/model/{port,factory,budget,capabilities,selection}.py` |
| I5 | **运行时资源所有者** | 统一关闭，不漏资源 | `AgentRuntime` 持有模型客户端 + MCP 工具 + `ToolExecutionRuntime`，统一 `close()`（取消工具→关闭 MCP→释放客户端）；`_Lazy*` 延迟构造 | `composition/runtime/factory.py` |
| I6 | **工具适配** | legacy/MCP 工具统一为 core 契约 | `AgentToolAdapter` 适配取消、结果元数据；`tool_definition_for` 生成供应商中立 schema | `composition/tools/{adapter,definitions}.py` |
| I7 | **技能系统** | 可扩展的能力包 | `SKILL.md` = YAML frontmatter + 正文；五源优先级发现：`~/.codeagent/skills` > user-package > `.codeagent/skills` > project-package > `resources/skills`(builtin)，按名去重并报告 `shadowed`；**只把技能清单注入提示词，模型需要时经 `skill` 工具拉取正文**（省上下文） | `app/skills/{models,discovery,prompt,runtime}.py` |
| I8 | **技能包管理** | 安装第三方技能 | `PackageManager` 支持 git URL 或本地目录安装、更新、删除、列表、重载；`PackageRegistry` JSON 注册表含越界/符号链接校验 | `app/skills/packages/{manager,registry}.py` |
| I9 | **任务模式** | 控制代理能动什么 | `TaskMode(ask/plan/code/auto)` + `/mode` 粘性切换（`//` 转义）；ask/plan 下拒绝变更型工具与变更型 shell 命令 | `app/tasks/modes.py` |
| I10 | **任务监督与自动修复** | 改完代码自动验证、失败自动修 | `TaskSupervisor.run`：基线快照 → Agent 回合 → 工作区 diff → 验证命令 → 失败自动修复；`max_repairs` 默认 1（≤3），用输出指纹去重防死循环 | `app/tasks/supervisor.py`、`lifecycle.py` |
| I11 | **工作区变更检测** | 知道代理到底改了什么 | `WorkspaceInspector` 用文件 sha256 快照对比，内置忽略 `.git`/缓存等 | `app/tasks/verification/workspace.py` |
| I12 | **验证命令自动探测** | 不配置也能跑测试 | 按 `pyproject.toml`/`package.json`/Cargo/Go/Maven/DotNet/Makefile 自动探测，且拒绝变更型命令；结果标准化为 `VERIFIED/FAILED/UNVERIFIED/CANCELLED` | `app/tasks/verification/{resolver,runner}.py` |
| I13 | **分层 AGENTS.md 加载** | 尊重项目规范 | 全局 → cwd 向上遍历祖先，候选 `AGENTS.override.md > AGENTS.md > AGENTS.MD > CLAUDE.md > CLAUDE.MD`；合并为 `<project_instructions>` 段 | `app/context/agents.py` |
| I14 | **异常兜底** | 内部错误不泄露细节给模型 | `report_unexpected_error` 记录完整上下文到日志，只返回安全提示 | `app/errors/reporting.py` |

### J. 子代理（跨 core / app / session）

| # | 功能点 | 用途 | 核心逻辑概要 | 代码位置 |
|---|---|---|---|---|
| J1 | **子代理状态机** | 严格约束子任务流转 | 11 态有限状态机（CREATED→QUEUED→STARTING→RUNNING→…→COMPLETED/FAILED/TIMED_OUT/CANCELLED/REJECTED），`transition` 做合法性守卫 | `core/contracts/subagent_state.py` |
| J2 | **子代理运行体** | 真正跑起一个子会话 | `SerialSubagentRunner` + `make_child_session_factory`（no-recursion、profile 过滤的临时 session）；通过 `DelegateTool` 注入主会话 | `app/composition/subagent/factory.py`、`delegate_tool.py` |
| J3 | **串行并发控制** | 防止子代理打满资源 | `asyncio.Lock` 保证同时至多 1 个子会话；`_quota_lock` + `DEFAULT_MAX_CHILDREN_PER_RUN=4` 限制每父运行子任务数 | `app/composition/subagent/runner.py` |
| J4 | **子代理预算** | 子任务不能失控 | 默认 `max_turns=8 / max_tool_calls=32 / timeout=120s / max_output_chars=8000`，硬上限 16/64/300s/16000；在 `TURN_START` 与工具事件计数，超限即 `abort()`；墙钟用 `asyncio.timeout` | `app/composition/subagent/budget.py`、`runner_execution.py` |
| J5 | **结果抽取与汇总** | 子任务结论回到主会话 | `extract_child_facts` 抽取 evidence/usage/artifact，末条 assistant 文本作 summary，截断至 8000 字回写父 `ToolResult`（含 cleanup 状态） | `app/composition/subagent/runner_execution.py`、`runner_results.py` |
| J6 | **子代理运行记录** | 子任务留痕且可恢复 | `SubagentRunRecord` + `fold_records` 按 delegation_id 折叠（终态优先，存活态标 abandoned）；`SubagentRecordCoordinator` 去重串行落盘 | `session/persistence/subagent_record_model.py:114` |
| J7 | **子代理可观测** | 终端上看到子任务进度 | `SubagentLineProjector` 把 queued/started/progress/finished 事件投影为 bounded 单行状态（id/status/phase/elapsed/tool/reason/summary），按 state 去重、终态后封板 | `app/subagent_observability.py` |

### K. 终端 UI（app/tui/）

| # | 功能点 | 用途 | 核心逻辑概要 | 代码位置 |
|---|---|---|---|---|
| K1 | **三层布局** | 终端主界面 | 聊天区(transcript, 1fr) + 输入区(composer) + 状态栏(status)；Textual `Static`/`VerticalGroup`/`HorizontalGroup`/`TextArea`/`Input` | `app/tui/adapters/textual/app.py:35` |
| K2 | **可替换后端端口** | 换 UI 框架不动业务 | `TuiBackend` Protocol 定义 run/render/set_status/on_*/set_confirmation 等 + 10 个 handler 别名；**换框架只需重实现该接口** | `app/tui/ports/backend.py` |
| K3 | **24 个斜杠命令** | 命令行式交互 | 见"能力矩阵 2.2"；`parse()` 纯函数解析 → `_dispatch_command` 字典路由，异常隔离 | `app/tui/commands/{parser,dispatch}.py` |
| K4 | **模糊补全与选择器** | 命令与参数自动补全 | `match_tier`：精确 > 前缀 > 子串 > 子序列 > 编辑距离 ≤2；无参时自动打开 inline picker 浮层 | `app/tui/commands/fuzzy.py`、`interaction.py` |
| K5 | **流式消息渲染** | 逐字输出不卡顿 | `AssistantBlock` 把流切成"稳定行 + 未闭合尾"，**只重渲新增 stable units**；终态 `finalize` 走完整 Markdown 渲染并缓存 | `app/tui/presentation/blocks/` |
| K6 | **自研 Markdown 渲染** | 不引 Markdown 依赖 | 单遍扫描渲染加粗/行内代码/标题/列表/代码块；未闭合降级；>20,000 字符退化为纯文本 | `app/tui/presentation/md_renderer.py` |
| K7 | **工具调用块** | 直观展示工具在干什么 | `ToolCallBlock` 显示 Codex 风格摘要 + 可折叠 intent diff（edit/write）+ `OutputBuffer` 分页；点击行折叠/展开 | `app/tui/presentation/blocks/` |
| K8 | **输出分页** | 长工具输出可翻阅 | `OutputBuffer` 分页（page_size 40）+ head/tail 预览 + 导出 | `app/tui/presentation/output.py` |
| K9 | **单行状态栏** | 一眼看全局 | 三栏（会话/运行/上下文）按宽度自适应；含时钟、上下文、footer、子代理、工具计数 | `app/tui/presentation/status.py` |
| K10 | **确认弹窗** | 危险操作就地审批 | composer 区渲染「⚠ 需要确认 / 工具 / 原因 / [y]允许 [n]拒绝 [Esc]拒绝并中止」；`y`/`n` 直接回 `session.respond_approval` | `app/tui/session/conversation.py:34` |
| K11 | **状态 reducer** | UI 状态可预测 | `TuiModel` 事件→组件纯映射（时钟注入可测）；`RuntimeReducer` + `RuntimeSnapshot` 状态机，`_belongs_to_snapshot` 防旧事件覆盖新状态 | `app/tui/state/{model,model_events,runtime}.py` |
| K12 | **渲染帧调度** | 高负载下不掉帧 | `FrameScheduler` 30fps + `ResizeDebouncer` 50ms + `TuiEventBuffer` 合并相邻 delta（≤4096 字符）保序 + `render_generation` 丢弃过期帧 | `app/tui/rendering/{scheduler,event_buffer,coordinator}.py` |
| K13 | **渐进式渲染** | 长会话首次加载不阻塞 | 协作式渐进渲染（每 32 单元 yield）+ 布局 LRU 缓存（512 块 × 3 宽度）+ 增量高度索引 | `app/tui/state/transcript*.py` |
| K14 | **会话交互** | 在 TUI 里管理会话 | `/sessions`（search/filter/archived/recovery/archive/unarchive/delete/new/switch）、`/tree`（fork 链可视化 + 切换）、`/fork`、`/compact`、`/retry`、`/continue` | `app/tui/session/{commands,actions,action_runner,restore}.py` |
| K15 | **性能基准套件** | TUI 性能可回归 | `PerformanceRecorder`（含 `tracemalloc` 内存）+ `MetricSummary`(p50/p95) + 5 场景（history/stream/tool-output/restore/scroll-resize）；零终端依赖 | `app/tui/benchmark/*`、`scripts/benchmark_tui.py` |

### L. 工程化与质量体系

| # | 功能点 | 用途 | 核心逻辑概要 | 位置 |
|---|---|---|---|---|
| L1 | **分层测试体系** | 分快慢、可离线 | 9 个 marker：`unit`/`contract`/`integration`/`e2e`/`platform`/`security`/`performance`/`slow`/`compatibility`；**1,284 个测试函数 / 162 文件 / ≈28k 行**；按路径自动归类 | `pyproject.toml`、`tests/conftest.py` |
| L2 | **架构守卫测试** | 分层约束不可被绕过 | `test_decoupling.py` 用 AST 扫描全量源码强制依赖方向；另有 `test_textual_only_in_engine_adapter_zone` 等 | `tests/test_decoupling.py` |
| L3 | **规模守卫** | 文件/函数不失控 | `scale_scan.py` 检查 app 层文件 >300 行、函数 >80 行；`test_core_scale`/`test_app_scale`/`test_session_scale` | `scripts/scale_scan.py`、`tests/contracts/` |
| L4 | **依赖矩阵扫描** | 可视化跨层耦合 | `layer_scan.py` 输出 app/core/session/ai/tools 跨层 import 矩阵 + 第三方依赖 | `scripts/layer_scan.py` |
| L5 | **异步泄漏检测** | 防止 task 泄漏 | autouse 夹具 `_assert_async_tasks_are_clean` 自动让泄漏 asyncio 任务的测试失败 | `tests/conftest.py` |
| L6 | **配置隔离夹具** | 测试不碰真实 `~/.codeagent` | autouse `_isolate_config_dir` 重定向 `CONFIG_DIR` 到 tmp_path | `tests/conftest.py` |
| L7 | **OpenSpec 规格驱动** | 24 份规格覆盖能力域 | 六类：AI/Provider(6)、上下文治理(3)、会话持久化(3)、运行时/子代理(7)、工具/MCP/技能(4)、TUI(1)；CI 跑 `openspec validate --specs` | `openspec/specs/` |
| L8 | **CI 四 Job** | 自动化质量门禁 | `quality-fast`（Ruff E9/F821/F841 + unit/contract + **覆盖率 ≥77.9%** + 版本一致性 + `git diff --check` + openspec 校验）；`test-matrix`（ubuntu/windows/macos 离线，`LLM_PROVIDER=fake`）；`package-smoke`（release_check）；`performance`（continue-on-error） | `.github/workflows/ci.yml` |
| L9 | **发布校验** | 产物可复现、干净 | `release_check.py`：`uv build` → 解包查敏感文件/版本/必需资源 → venv 干净安装 → fake provider 冒烟 → 输出 JSON + sha256 | `scripts/release_check.py`、`package_smoke.py` |
| L10 | **基准回归对比** | 性能不悄悄劣化 | `compare_benchmark.py` 对比两份基准 JSON，默认容忍 20% 回归 | `scripts/compare_benchmark.py` |

---

## 三、能力矩阵速查

### 3.1 内置工具（8 个）

| 工具 | 作用 | 实现 |
|---|---|---|
| `read` | 读文件，支持 offset/limit 分页、二进制前缀预览、双上限截断 | `tools/atomic/read.py` |
| `write` | 整文件覆盖写，自动建父目录，恒写 LF，路径锁串行化 | `tools/atomic/write.py` |
| `edit` | old→new 精确字符串替换，保留原换行/BOM，匹配不唯一报错 | `tools/atomic/edit.py` |
| `bash` | 执行 shell，超时/截断/危险命令拒绝/退出码语义（默认 120s，上限 600s） | `tools/atomic/bash.py` |
| `grep` | 正则/字面量搜索，字节级整块匹配，优先 rg | `tools/atomic/grep.py` |
| `find` | glob 文件查找（支持 `**`），优先 fd | `tools/atomic/find.py` |
| `ls` | 列目录，目录带 `/` 后缀，不显隐藏项 | `tools/atomic/ls.py` |
| `skill` | 按名返回已注入的技能渲染块（寻址式，不触文件边界） | `tools/atomic/skill.py` |

> 另由 MCP 动态追加 `mcp__<server>__<tool>` 工具。

### 3.2 TUI 斜杠命令（24 个，dispatch 表约 27 个 handler）

`/help` `/ask` `/plan` `/code` `/mode` `/clear` `/status` `/name` `/context` `/sessions` `/tree` `/tools` `/provider` `/login` `/model` `/effort` `/fork` `/compact` `/output` `/retry` `/continue` `/skills` `/mcp` `/quit`

- 注册：`app/tui/commands/parser.py:91-137`；分发：`app/tui/commands/dispatch.py:11-21`
- picker 类命令（model/provider/effort/login/sessions）无参时自动弹出候选浮层

### 3.3 快捷键

| 键 | 作用 |
|---|---|
| Enter | 发送（输入区） |
| Shift+Enter / Ctrl+J | 换行 |
| ↑/↓ | 建议导航；Tab 补全/切焦点 |
| Esc | 打断（分级） |
| Ctrl+C / Ctrl+Q | 退出（priority） |
| PageUp / PageDown | 翻页 |
| y / n | 确认弹窗下允许 / 拒绝 |
| 鼠标点击行 | 折叠/展开工具块 |
| 滚轮 | 滚动（±3 行） |

### 3.4 Provider 支持（7 个，均为 OpenAI 兼容）

| Provider | 默认模型 | 备注 |
|---|---|---|
| `deepseek` | `deepseek-v4-flash` | `reasoning_effort="high"` |
| `openai` | — | `reasoning_effort="high"` |
| `qwen` | `qwen3.8-max` | 不发送 reasoning_effort |
| `glm` | `glm-5.2` | 同上 |
| `kimi` | `kimi-k3` | `reasoning_effort="high"` |
| `minimax` | `MiniMax-M3` | 不发送 reasoning_effort |
| `fake` | — | 离线脚本化假模型，用于测试 |

---

## 四、已实现 / 未实现对照

| 能力 | 状态 | 说明 |
|---|---|---|
| ReAct 主循环、取消、递归上限 | ✅ 已实现 | core/orchestration |
| 上下文预算 + 预检 + 裁剪 + 自动压缩 | ✅ 已实现 | 估算为字符/4，非真实 tokenizer |
| 会话持久化 / 会话树 / 分叉 / 恢复 | ✅ 已实现 | JSONL + 跨进程锁 + 崩溃诊断 |
| 安全三态审批 | ⚠️ 部分 | DENY 覆盖面偏窄，仍是"默认放行 + 黑名单" |
| MCP 集成 | ⚠️ 部分 | 仅 stdio 传输，无 http/sse；仅客户端角色 |
| 子代理 | ✅ 已实现 | 串行执行（非并发），有预算与状态机 |
| 技能系统 + 包管理 | ✅ 已实现 | 五源发现 + git/本地安装 |
| 任务模式 + 自动验证修复 | ✅ 已实现 | 验证命令自动探测 |
| TUI | ✅ 已实现 | Textual，可替换后端 |
| **成本/费用计算** | ❌ 未实现 | 仅透传 provider 原始 `usage`（token 计数），**无价格表、无金额换算** |
| **真实 tokenizer** | ❌ 未实现 | 上下文估算用字符数 ÷ 4 |
| **持久 shell 会话** | ❌ 未实现 | 每次 `bash -lc` 新起进程，`cd` 等状态不保留 |
| **元工具（todo / plan / 派发）** | ❌ 未实现 | tools 层无此类工具；派发走 `DelegateTool` |
| **Windows 可靠进程树清理** | ❌ 未实现 | 源码注释明示"不能证明全树停止" |
| **MCP 服务端角色** | ❌ 未实现 | 仅作为客户端 |

---

## 五、已知限制与技术债

依据 [`code-review-2026-08-28.md`](code-review-2026-08-28.md)，并已对代码现状逐条核验：

| 级别 | 项 | 核验结果 |
|---|---|---|
| 高 | 安全分类器 DENY 覆盖面 | ⚠️ **部分修**：已新增 `_dangerous_intent` 结构递归分析，但仍是"默认放行 + 黑名单"；**最小权限白名单未落地** |
| 高 | `asyncio.create_task` 未统一回收 | ⚠️ **部分修**：TUI `application.py` 建了 `_track_task` 登记表，但 `core/agent.py`、`core/orchestration/batch.py`、`app/headless.py`、`runner_execution.py`、`rendering/coordinator.py`、`status_timer.py` 仍直接创建未登记 |
| 高 | Windows 进程树清理不可确认 | ❌ 仍存在（`windows.py` 恒返回 False） |
| 中 | 越界**读取**文件仍为 ALLOW | ❌ 仍存在：写/编辑越界才 ASK，读越界仅带 warning 放行 |
| 已修 | 跨进程文件锁 | ✅ `locking.py` 已加 `fcntl.flock`/`msvcrt.locking` sidecar 锁 |
| 已修 | `commit_turn` 整文件回滚 | ✅ 改为 `stat()` 取原 size + `truncate` 定点回滚（O(1)） |
| 已修 | `compact()` 未挡 `cut >= len(history)` | ✅ `policy.py` 无安全切点返回 0，多处 `return False` |
| 文档明示待办 | — | Windows 文件权限加固；安全策略收敛到最小权限白名单；session facade / turn runner 拆分；TUI、composition 大文件；测试对 bash 完全密闭化 |

**本机环境注意**（非代码缺陷）：Windows 上 `resolve_bash()` 可能选中 PortableGit 的 `bash.exe`（该实例 `/etc/msystem` 缺失，向 stderr 输出噪声且冷启动约 6.5s），导致 `tests/tools/test_execution.py` 两条 5s 超时断言必然失败。

---

## 六、版本演进

| 版本 | 时间 | 主要交付 |
|---|---|---|
| v0.1 | 08-10~14 | 自研编排落地、TUI 恢复、安全权限基础 |
| v0.2 | 08-14~15 | 编排自研路线确定，阶段 1/3/5 落地 |
| v0.3.0 | 08-22 发布 | Skills 三源发现与遮蔽、MCP 最小协议、token 归一、会话树/恢复、TUI 命令 |
| **v0.4.0（当前）** | 09-01 发布 | Agent Runtime 产品化：生命周期/取消/清理契约、上下文预算预检 + 自动压缩 + 恢复回归、TUI 长会话渲染、会话治理、工具能力探测、Provider 错误分类、安全重试 |
| v0.5.0 | 规划中 | Subagent 协作与可验证任务编排（**子代理骨架已先行落地**） |

---

## 七、总体判断

1. **架构纪律强于功能广度**。24 份 OpenSpec + AST 架构守卫 + 规模守卫 + 依赖矩阵扫描，把"分层不被腐蚀"做成了可执行的门禁，这在同类自研项目里不多见。
2. **运行时质量打磨到位**。取消/超时/清理不确定/副作用观察/崩溃恢复/异步泄漏检测——这些"用起来才知道"的部分投入明显，是 v0.4 的核心价值。
3. **功能覆盖已闭环，深度有取舍**。读写改查 + bash + MCP + 技能 + 子代理 + 任务验证 + TUI 全链路可用；但在 tokenizer 精度、成本计算、安全白名单、Windows 进程清理上明确选择了"够用即可"。
4. **UI 是最大的代码资产**（约 15.7k 行 / 45%），自研 Markdown 渲染 + 帧调度 + 渐进渲染 + 性能基准，说明长会话渲染性能被当作一等公民对待。
5. **下一阶段重心**已在 v0.5 明确为子代理协作与可验证任务编排，且子代理的契约、状态机、预算、记录、可观测五件套已提前就位，属于"骨架先于编排"的推进方式。
