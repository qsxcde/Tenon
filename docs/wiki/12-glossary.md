# 12 · 术语表、常量与位置速查

> 全 Wiki 的收口页：统一术语、汇总散落各层的默认值/上限、给出"想改某东西去哪找"的定位表。常量以当前源码为准（描述当前树，不写行号）。

## 一、术语表

| 术语 | 含义 |
| --- | --- |
| **两层 loop** | 无状态 `run_agent_loop`（core，纯函数式推进一次请求/工具循环）+ 有状态 `Agent`（core，持有历史与运行状态） |
| **AgentLoopConfig** | core 的运行时契约：模型端口、工具、执行运行时、策略、上下文钩子、steering 队列等的唯一装配载体 |
| **端口-适配器** | 横切轴：core 定义协议（ports），ai/tools/session 提供实现，app/composition 负责适配 |
| **纵切生命周期** | Factory（装配）→ Session（会话状态）→ Runtime（运行资源）三层协作；资源所有权显式 |
| **组合根** | `app/container.py`（façade）、`app/main.py`、`app/composition/**`：唯一允许跨层 import 的地方 |
| **AgentRuntime** | 模型/工具端口的资源所有者，负责幂等关闭与 `_runtime_owner` 锚定 |
| **Turn** | 一次用户输入驱动的完整模型回合（可能含多次模型请求与工具批次） |
| **run_agent_loop** | core 的 ReAct 主循环：准备上下文 → 模型请求 → 工具批次 → 结果回填 → 继续或结束 |
| **tool_call_id** | 工具调用唯一标识，贯穿 queued → running → terminal 生命周期归约与结果回填 |
| **RunPhase** | 运行状态机：IDLE/STARTING/MODEL_WAIT/TOOL_RUNNING/AWAITING_CONFIRMATION/CONTINUING/COMPLETED/FAILED/CANCELLED/FINALIZING |
| **确认（Confirmation）** | 安全策略 ask 档触发的用户批准流程，由 `ConfirmationCoordinator` 承载 |
| **Steering** | 运行中用户干预（插话/打断）经 `steer_queue` 注入循环 |
| **LifecycleHook** | 扩展点：turn/model/tool/session 阶段边界回调（同步/异步），失败被隔离 |
| **RuntimeExtensions** | 组合层扩展容器：上下文变换/准备/预算、工具前后钩子、生命周期 Hook |
| **上下文预算** | `ContextBudgetInput/Snapshot`：按 chars//4 估算输入 token 与 headroom |
| **Preflight** | 请求前预算判定：safe / near_limit / over_limit / uncertain；不确定策略可 allow 或 fail |
| **Governance** | `govern_tool_messages`：请求局部裁剪工具结果，结构化事实保留、持久化历史不被改写 |
| **压缩（Compaction）** | 上下文接近窗口时按 user 边界摘要旧历史；摘要消息 id 前缀 `summary-`，永不落盘 |
| **commit_turn_async** | 会话唯一落盘点：成功才提交；失败/取消按 `before_ids` 内存回滚 |
| **恢复报告** | 会话恢复三态：healthy / degraded / unavailable |
| **Subagent / 委派** | `delegate` 工具触发的子会话：串行、只读、深度 1、白名单工具；规则在 `core/subagent/` |
| **MCP** | Model Context Protocol：外部工具经 `mcp__<server>__<tool>` 命名进入工具集 |
| **AtomicTool** | tools 层的无状态工具基类（装配注入 cwd/ops/资源限制） |
| **TuiBackend** | TUI 引擎端口：视图逻辑只依赖它，Textual 只在适配区 |
| **RuntimeReducer** | TUI 纯归约器：运行事件 → 稳定渲染状态 |
| **RenderCoordinator** | 30fps 渲染协调：合并增量、按帧预算出帧、统计丢帧 |
| **类型棘轮** | mypy 分层错误数只降不升的门禁（`scripts/type_scan.py`） |
| **规模门禁** | 生产层 300 行/文件、80 行/函数（`scripts/scale_scan.py`） |

## 二、关键常量速查

### core

| 常量 | 值 | 位置 |
| --- | --- | --- |
| `DEFAULT_CONTEXT_WINDOW` | 128 000 | `core/context/budget.py` |
| `DEFAULT_OUTPUT_RESERVE` | 4 096 | `core/context/budget.py` |
| `DEFAULT_RESERVE_TOKENS` | 16 384 | `core/context/budget.py` |
| token 估算 | `chars // 4`（最小 1） | `core/context/budget.py` |
| `warning_headroom_tokens` | 2 048 | `core/context/preflight.py` |
| `uncertain_budget_policy` | `allow` / `fail`（默认 allow） | `core/context/preflight.py` |
| Subagent 深度 / 工具白名单 | 1 / read、grep、find、ls、skill（串行只读） | `core/subagent/*` |

### session

| 常量 | 值 | 位置 |
| --- | --- | --- |
| `CURRENT_VERSION`（JSONL 格式） | 1 | `session/persistence/models.py` |
| 压缩 `trigger_ratio` / `target_ratio` | 0.8 / 0.65 | `session/compaction/policy.py` |
| 压缩 `trigger_headroom_tokens` | 2 048 | `session/compaction/policy.py` |
| `max_resident_sessions` | 32（LRU） | `session/manager/manager.py` |
| `recursion_limit` | 50 | `session/manager/manager.py` |
| 磁盘布局 | `~/.codeagent/sessions/<id>.jsonl` + `<id>.index.json` + `.<name>.lock`（权限 600/700） | `session/persistence/*` |

### ai

| 常量 | 值 | 位置 |
| --- | --- | --- |
| `DEFAULT_MAX_RETRIES` / `MAX_RETRIES` | 3 / 5 | `ai/transport/retry.py` |
| `MAX_RETRY_DELAY` | 10.0s | `ai/transport/retry.py` |
| HTTP 超时 | connect 10 / read 120 / write 30 / pool 10（流式 read=None） | `ai/transport/openai_compat.py` |
| `_MAX_DETAIL_LENGTH`（错误详情） | 1 000 | `ai/errors.py` |

### tools

| 常量 | 值 | 位置 |
| --- | --- | --- |
| bash 默认/最大超时 | 120s / 600s | `tools/atomic/bash.py` |
| bash `MAX_OUTPUT_CHARS` | 30 000 | `tools/atomic/bash.py` |
| 输出截断 `DEFAULT_MAX_BYTES` / `DEFAULT_MAX_LINES` | 30 000 / 2000 | `tools/shared/truncate.py` |
| grep / find / ls 默认 limit | 100 / 1000 / 500 | `tools/atomic/{grep,find,ls}.py` |
| read 默认行数 | 2000 | `tools/atomic/read.py` |
| 工具并发 | 4 | `tools/shared/resource_limits.py` |
| `DEFAULT_TOOL_MAX_TIMEOUT` | 600.0s | `tools/shared/resource_limits.py` |
| `DEFAULT_TOOL_MEMORY_BYTES` | 1 048 576 | `tools/shared/resource_limits.py` |
| `DEFAULT_TOOL_CLEANUP_TIMEOUT` | 10.0s | `tools/shared/resource_limits.py` |
| MCP 全局 / 每 server / 描述上限 | 40 / 15 / 200 | `tools/mcp/budget.py` |
| 文件边界工具 | read、write、edit | `tools/security/filesystem.py` |

### app / TUI / 质量门禁

| 常量 | 值 | 位置 |
| --- | --- | --- |
| 配置目录 | `~/.codeagent` | `app/config.py` |
| `approval_mode` 默认（headless） | `deny` | `app/composition/runtime/factory.py` |
| TUI 目标帧率 | 30 fps | `app/tui/rendering/coordinator.py` |
| TUI 恢复后台阈值 | >1000 消息 或 >100k 字符 或 >1MB 工具输出 | `app/tui/session/restore.py` |
| 规模门禁 | 300 行/文件、80 行/函数 | `scripts/scale_scan.py` |
| 格式化行宽 | 100 | `pyproject.toml` |
| 覆盖率硬下限 | 77.9% | CI `--cov-fail-under` |

## 三、位置速查：想改 X 去哪找

| 想改… | 去哪里 |
| --- | --- |
| Agent 主循环 / 回合推进 | `core/orchestration/loop.py`、`turn.py`、`batch.py`、`tool_call.py` |
| 运行时契约字段（新钩子/新开关） | `core/orchestration/config.py` 的 `AgentLoopConfig` |
| 消息模型 / 事件类型 | `core/contracts/messages.py`、`core/contracts/events.py` |
| 上下文预算与预检 | `core/context/{budget,preflight,model}.py` |
| 工具执行并发/超时/清理 | `core/execution/runtime.py` |
| Subagent 预算/准入/槽位 | `core/subagent/{policy,admission,slots}.py` |
| 会话提交/回滚/状态机 | `session/run_coordinator.py`、`session/runtime/*`、`session/session.py` 组合的 mixin |
| JSONL 格式与迁移 | `session/persistence/*`（改格式须升 `CURRENT_VERSION`） |
| 压缩策略 | `session/compaction/policy.py`、`service.py` |
| 会话管理（fork/rename/archive） | `session/manager/*` |
| Provider 配置/默认模型 | `ai/providers/<name>.py` + `ai/catalog/builtin.py` |
| 模型错误分类/脱敏 | `ai/errors.py` |
| 重试与 SSE 解析 | `ai/transport/{retry,sse,streaming}.py` |
| 新增内置工具 | `tools/atomic/<name>.py` + `tools/registry.py` |
| 安全规则（ask/deny/allowlist） | `tools/security/{ask_rules,bash_rules,classifier,filesystem}.py` |
| MCP 预算/命名/加载 | `tools/mcp/{budget,adapter,loader}.py` |
| 工具资源上限 | `tools/shared/resource_limits.py` |
| CLI 参数/退出码 | `app/main.py` |
| 配置目录与 .env 模板 | `app/config.py` |
| 模型端口适配 | `app/composition/model/*` |
| 工具装配与适配 | `app/composition/tools/*`、`policy.py` |
| Runtime 与扩展装配 | `app/composition/runtime/*` |
| Subagent 装配 | `app/composition/subagent/*` |
| 技能发现/包管理 | `app/skills/*` |
| 任务模式/验证 | `app/tasks/*` |
| TUI 命令表 | `app/tui/commands/parser.py` |
| TUI 渲染协调/状态归约 | `app/tui/rendering/*`、`app/tui/state/*` |
| TUI 展示/主题 | `app/tui/presentation/*` |
| 测试分层/marker | `tests/`、`pyproject.toml` 的 `markers` |
| CI 门禁 | `.github/workflows/ci.yml`、`scripts/*` |

## 四、文档地图回顾

| 篇 | 主题 |
| --- | --- |
| [01](./01-overview.md) | 项目概览与目标 |
| [02](./02-architecture.md) | 架构与核心契约 |
| [03](./03-runtime-flow.md) | 运行方式与生命周期 |
| [04](./04-core-layer.md) | core 层 |
| [05](./05-session-layer.md) | session 层 |
| [06](./06-ai-layer.md) | ai 层 |
| [07](./07-tools-layer.md) | tools 层 |
| [08](./08-app-layer.md) | app 层 |
| [09](./09-tui-layer.md) | TUI 层 |
| [10](./10-dependency-map.md) | 依赖与边界 |
| [11](./11-development-guide.md) | 开发指南 |
| [12](./12-glossary.md) | 本页 |

## 相关阅读

- 返回索引：[README.md](./README.md)
- 权威规范：[AGENTS.md](../../AGENTS.md)、[docs/testing.md](../testing.md)、`openspec/`