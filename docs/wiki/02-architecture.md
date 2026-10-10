# 02 · 整体架构

> 决策背景与收益记录见 [`../design/architecture.md`](../design/architecture.md) 与 [`../design/self-built-orchestration-blueprint.md`](../design/self-built-orchestration-blueprint.md)。本文描述当前代码树的结构事实。

## 1. 两条正交轴

整个结构由两条独立的分离轴合成，不要混淆：

| 轴 | 分的是什么 | 来源 |
| --- | --- | --- |
| **横切轴：依赖方向** | config / 工具 / 编排 / 调用之间谁认识谁 | 端口-适配器（hexagonal） |
| **纵切轴：生命周期** | 装配（Factory）/ 单个对话（Session）/ 会话生命周期（Runtime） | Pi 三层协作 |

- 横切轴解决"零件怎么装"：依赖单向流动，组合根是唯一交汇点。
- 纵切轴解决"装好之后会话怎么活"：三层生命周期不同、变化率不同，不绑在一个类里。

## 2. 双层 loop（另一条正交结构）

| 层 | 位置 | 职责 |
| --- | --- | --- |
| 无状态循环 | `core/orchestration/loop.py` 的 `run_agent_loop` / `run_agent_loop_continue` | 纯函数式驱动：复制 context、迭代 turn、emit 事件、返回新消息 |
| 有状态内存外壳 | `core/agent.py` 的 `Agent` | 持有 `AgentContext`、run_id、订阅者、steer/follow-up 队列、任务句柄 |
| 会话外壳 | `session/session.py` 的 `AgentSession` | 补齐历史提交、落盘、压缩、会话级事件、干预与生命周期 |

循环在 context 的**副本**上工作，成功返回后才提交到 `Agent`；失败/取消天然回滚——这是会话层简单回滚边界的基础。

## 3. 五层结构

```text
┌─────────────────────────────────────────────────────────────────┐
│ app/           入口 + 组合根 + TUI（唯一跨层装配区）              │
│   main.py / headless.py / config.py / container.py              │
│   composition/{model,tools,session,runtime,subagent,tui}        │
│   skills/ tasks/ context/ tui/                                   │
├─────────────────────────────────────────────────────────────────┤
│ session/       会话状态、生命周期、JSONL 持久化、压缩、导航       │
│   session.py / manager/ / persistence/ / compaction/ / runtime/ │
├───────────────┬───────────────────────────┬─────────────────────┤
│ core/         │ ai/                       │ tools/              │
│ Agent Runtime │ 模型基础设施              │ 工具层              │
│ 纯内存/全异步 │ providers/transport/catalog│ atomic/mcp/security │
│ 零外部依赖    │ errors                    │ execution/shared    │
├───────────────┴───────────────────────────┴─────────────────────┤
│ resources/     内建 prompts（system.md）与 skills（*.md）        │
└─────────────────────────────────────────────────────────────────┘
```

## 4. 核心契约（core 认识外部世界的唯一窗口）

### 4.1 AgentLoopConfig

`core/orchestration/config.py` 的 `AgentLoopConfig` 是编排认识外部世界的唯一窗口：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `model` | `ModelPort` | 模型端口（组合根适配 ai 层 `ChatClient`） |
| `tools` | `list[AgentTool]` | 统一工具契约列表 |
| `transform_context` / `context_preparer` / `context_transform_timeout` | 扩展点 | 请求级上下文变换与准备（有超时） |
| `context_budget` / `context_preflight` / `uncertain_budget_policy` | 上下文治理 | 预算提供者、preflight 配置、不确定窗口策略（`allow`/`fail`） |
| `before_tool_call` / `after_tool_call` | 工具 Hook | 执行前后决策（安全策略在此适配） |
| `lifecycle_hooks` | `tuple[LifecycleHook, ...]` | 只读观察者（turn/model/tool scope） |
| `tool_execution` | `"parallel"` \| 顺序 | 工具批次执行方式 |
| `tool_timeout` / `tool_runtime` | 执行控制 | 单工具超时；受控执行端口 |
| `should_stop_after_turn` | 回调 | 自定义停止条件 |
| `steer_queue` | `list[str]` | 运行中注入队列（runtime 持有，Agent 在工具批次后排空） |
| `context_window` / `output_reserve` / `reserve_tokens` / `window_source` | 回退元数据 | 老适配器的预算回退值 |

**为什么 `model` 与 `tools` 分离**：工具列表作为实现 `AgentTool` 的数据传入，编排层不知道工具内部实现；加/换工具时 `core/` 零改动。

**`store` 不在端口内**：core 循环从不落盘；成功轮次才写由会话层负责。

### 4.2 端口清单（`core/contracts/ports.py`）

| 端口 | 方法 | 说明 |
| --- | --- | --- |
| `ModelPort` | `model_id` 属性；`generate(messages, tools)`；`stream(messages, tools)` | 编排消费的最小模型调用面 |
| `AgentTool`（`runtime_checkable`） | `name` / `description` / `parameters`；`execute(tool_call_id, arguments, *, signal, on_update)` | 唯一由 Runtime 消费的工具契约 |
| `ToolExecutionRuntimePort` | `execute(tool, call, timeout, operation_id, on_update)` | 受控执行端口 |
| `ToolCleanupPort` | `cleanup(operation_id)` | 外部资源清理端口 |
| `ApprovalPolicy` | `decide(tool_name, args) -> PolicyDecision` | 执行前安全策略（allow/ask/deny） |
| `Summarizer` | `summarize(messages, prev_summary)` | 压缩摘要端口 |
| `PolicyDecision`（frozen dataclass） | `action` / `reason` / `warning` | 安全决策结果 |
| `ToolDecision`（frozen dataclass） | `allow()` / `block(reason)` | Hook 的通用执行前决策 |
| `ModelResponse` / `StreamEvent` | dataclass | 非流式结果 / 流式统一事件（content、thinking、tool_call、finish、usage） |

### 4.3 消息模型（`core/contracts/messages.py`）

| 类型 | 关键字段 |
| --- | --- |
| `Message` | `role`（user/assistant/tool）、`content`、`tool_calls: list[ToolCall]`、`tool_call_id`、`id`（uuid7）、`parent_id`、`tool_output: ToolOutputMetadata` |
| `ToolCall` | `id` / `name` / `args: dict` / `details`（适配器诊断袋） |
| `ToolResult` | `tool_call_id` / `content` / `error` / `name` / `rejected` / `status` / `operation_id` / `cleanup_*` / 输出统计（bytes、lines、truncated_by…）/ `exit_code` / `duration_ms` / `semantic_success` / `output_metadata` |
| `new_id()` | 手写 uuid7（48 位毫秒时间戳 + 版本 + 62 位随机），时间有序，服务 JSONL 排序与按 id 删除 |
| 归约 | `replace_or_append`（同 id 替换否则追加）、`remove_by_id`（按 id 删除） |
| 状态常量 | `ToolExecutionStatus`（completed/failed/rejected/timed_out/cancelled/invalid_arguments/cleanup_uncertain…）、`CleanupStatus`（not_required/pending/confirmed/failed/uncertain/unsupported） |

## 5. 事件驱动

### 5.1 事件流路径

```text
core 循环 emit(AgentEvent)
   → Agent._emit（补 run_id，隔离订阅者异常，通知 lifecycle hooks）
   → session/eventing.py 归一化（补 session_id/run_id/sequence）
   → EventBus.emit（同步扇出，单订阅者异常隔离记录）
   → TUI 事件缓冲区 / headless 聚合 / 测试订阅 / CI
```

### 5.2 事件分组（`core/contracts/events.py` 的 `EventType`）

| 分组 | 事件 |
| --- | --- |
| Agent 生命周期 | `agent_start` `agent_end` `turn_start` `turn_end` `message_start` `message_update` `message_end` `aborted` `error` |
| 模型请求 | `model_request_started` `model_request_finished` `text_delta` `thinking_delta` `agent_message` `usage` |
| 工具生命周期 | `tool_call` `tool_queued` `tool_started` `tool_progress` `tool_finished` `tool_result`（core 侧为 `tool_execution_queued/start/update/end`，session 层映射） |
| 运行控制 | `session_started` `run_cancelled` `cancelling` `retry_started` `confirmation_requested` |
| 上下文治理 | `context_budget` `context_preflight` `compaction_started` `compaction_finished` |
| 会话恢复 | `restore_started` `restore_finished` |
| Subagent | `subagent_queued` `subagent_started` `subagent_progress` `subagent_finished` |

`AgentEvent` 同时携带**类型化关联字段**（`run_id` / `tool_call_id` / `operation_id` / `delegation_id` / `parent_run_id` / `child_run_id` / `sequence` / `status` / `cleanup_*` 等）与 `metadata` 兼容袋；`__post_init__` 保持两者一致。

### 5.3 Subagent 事件关联

父子事件通过 `delegation_id`、`parent_run_id`、`child_run_id`、`attempt_id`、`depth`、`child_sequence`/`parent_sequence` 关联；`subagent_finished` 是唯一终态事件。父级 Subagent 事件在唯一观察点转换为**有界运行记录**异步落库（见 [05](05-session-layer.md)）。

## 6. 组合根：唯一的跨层交汇点

`app/container.py` 是 façade，实现位于 `app/composition/*`：

| 工厂 | 产物 | 说明 |
| --- | --- | --- |
| `create_agent_config(cfg, *, registry, reasoning_effort, provider, model, approval_mode, extensions, ...)` | `AgentLoopConfig` | 装配 client、skills、system prompt、tools、`ChatModelPort` |
| `create_agent_runtime(cfg, ...)` | `AgentRuntime` | 资源所有者（模型客户端、MCP、工具运行时） |
| `create_agent_session(cfg, ...)` | `AgentSession` | 会话外壳（可默认装配 `SerialSubagentRunner`） |
| `create_session_manager(cfg, ...)` | `SessionManager` | 多会话管理 |
| `create_tui_app(cfg, ...)` | `TuiApp` | TUI 装配，`rebuild_ports` 支持热切换 |

要点：

- `approval_mode`：`deny`（headless 缺省，ask 降级 deny，fail closed）/ `interactive`（TUI，ask 走确认条）/ `allow`（`--yes`）。
- `store` 经 `AgentSession` / `SessionManager` 注入，不进 `AgentLoopConfig`。
- `RuntimeExtensions`（frozen）统一承载 ContextTransformer、预算上下文、工具 Hook、生命周期 Hook 与扩展超时；恢复与热切换从同一不可变集合重建配置。

详细装配见 [08 · app 层](08-app-layer.md)。

## 7. 依赖规则

| 模块 | 可以 import | 禁止 import |
| --- | --- | --- |
| `app/config.py` | —（只被 container / ai 读取） | core、session、tools、app/tui |
| `ai/` / `tools/` | config（工具层内部：`shared/`） | core、session |
| `core/` | 只有自身 `ports`/契约 | config、ai、tools、session |
| `session/` | core（ports/loop/events/messages）、事件总线 | ai、tools、config |
| `app/container.py` | 全部（唯一交汇点） | — |
| `app/main.py` | container、session、bus | core、ai、tools（直接） |
| `app/tui/` | session、core(events)、TUI state/presentation | ai、tools、config；textual 仅 `adapters/textual/` |

**解耦判据（泄漏检测）**：

| 变更 | 应动的文件 | 若还动了 | 结论 |
| --- | --- | --- | --- |
| 新增一个 provider | `ai/` + 环境变量 | `session.py` / `core/` | ❌ 泄漏 |
| 新增/更换一个工具 | `tools/` | `core/orchestration/` / `ai/` | ❌ 泄漏 |
| 改编排形状（改循环） | `core/` | `ai/` / `tools/` | ❌ 泄漏 |
| 换会话存储 | `store` + `container` | `app/main.py` / `core/` | ❌ 泄漏 |
| 加会话分叉 | `session/` | `core/` | ❌ 泄漏 |

最严格判据：**`core/` 里 grep 不到 `config / tools / ai / session` 字面量；`session/` 里 grep 不到 `ai / tools / config` 字面量**。

规则由 `tests/test_decoupling.py` 的 AST 扫描强制校验（带 anti-wargaming 守卫）；`tools/` 不 import `core/` 是现行规则——需要 core 契约的 `delegate` 入口属于 `app/composition/subagent/delegate_tool.py`。详见 [10 · 依赖关系图](10-dependency-map.md)。

## 8. 全局不变量（改代码前必读）

1. **成功才落盘**：会话历史在局部副本上推进，`commit_turn_async` 是唯一成功落盘点；失败/取消只留在内存并被回滚。
2. **core 零副作用**：模块顶层不建模型、不发请求、不读 key。
3. **事件即接口**：状态的对外可见性经事件与只读属性暴露，UI 不直接读内部结构。
4. **安全 fail closed**：headless 无 `--yes` 时敏感操作一律拒绝；shell 分词失败按最保守处理。
5. **资源有界**：工具输出、Subagent 预算与输出、诊断、MCP 工具数与描述长度均有硬上限。
6. **恢复不重写源文件**：损坏 JSONL 局部降级；结构性错误阻止激活并保留原文件；非终态 Subagent 记录折叠为 `abandoned/process_restarted`。
7. **门禁可执行**：规模（≤300 行/≤80 行函数）、格式化（ruff format）、类型棘轮（type_scan）是 CI 强制项而非口头约定。

上一章：[项目总览](01-overview.md) · 下一章：[运行方式与端到端数据流](03-runtime-flow.md)。