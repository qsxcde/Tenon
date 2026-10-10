# 04 · core 层：Agent Runtime

> 目录：`src/codeagent/core/`。定位：**纯内存、全异步、零外部依赖**的领域运行时。不 import `config` / `ai` / `tools` / `session`，模块顶层零副作用，平台可直接 import。

## 1. 文件地图

| 路径 | 职责 |
| --- | --- |
| `agent.py` | `Agent`：有状态内存外壳（prompt/continue/abort/steer/follow_up/subscribe） |
| `observation.py` | `LifecycleHookObservationMixin`：生命周期 Hook 快照分发与诊断隔离 |
| `context/model.py` | `AgentContext`（system_prompt / messages / tools） |
| `context/budget.py` | 预算输入/快照模型、估算、`govern_tool_messages` |
| `context/preflight.py` | `ContextPreflightConfig` / `ContextPreflightResult` / `evaluate_context_preflight` |
| `context/transform.py` | ContextTransformer 调用与消息克隆/物化 |
| `context/contracts.py` | `TransformContext` / `ContextPreparer` / `AfterToolCall` / `BeforeToolCall` / `ContextBudgetPort` 等协议 |
| `context/diagnostics.py`、`context/diagnostic_models.py` | 治理诊断模型 |
| `contracts/messages.py` | `Message` / `ToolCall` / `ToolResult` / 状态常量 / uuid7 / 归约函数 |
| `contracts/events.py` | `EventType` 常量、`AgentEvent`、`SUBAGENT_EVENT_TYPES` |
| `contracts/ports.py` | 全部端口协议与决策 dataclass |
| `contracts/errors.py` | `AgentRuntimeError` / `AgentContinueError` / `ContextPreparationError` / `ContextPreflightError` / `ContextTransformTimeoutError` |
| `contracts/hooks.py` | `LifecycleHook` / `LifecycleHookEvent` |
| `contracts/output.py` | `ToolOutputMetadata` / `OutputCompleteness` |
| `contracts/tool_status.py`、`contracts/subagent*.py` | 状态与 Subagent 契约（请求/预算/结果/生命周期） |
| `model/request.py` | 模型请求准备与流归一化（`prepare_context` / `new_model_message`） |
| `orchestration/loop.py` | `run_agent_loop` / `run_agent_loop_continue` / `DEFAULT_RECURSION_LIMIT` |
| `orchestration/turn.py` | `run_turn`：单轮模型请求 + 工具批次 + steer 排空 |
| `orchestration/batch.py` | `execute_tool_batch`：保序执行、并发、取消收尾 |
| `orchestration/tool_call.py` | `new_tool_result`：单个工具调用全流程（参数错误/未知工具/Hook/执行/归一） |
| `orchestration/config.py` | `AgentLoopConfig` |
| `orchestration/errors.py` | `RecursionLimitError` |
| `execution/runtime.py` | `ToolExecutionRuntime`：并发信号量 + 操作注册表 + 清理跟踪 |
| `execution/state.py` | `OperationRegistry` / `ToolOperation` |
| `execution/cleanup.py` | `CleanupTracker` / `CleanupResult` |
| `execution/result.py` | `normalize_tool_result`：任意工具返回值 → `ToolResult` |
| `subagent/policy.py` | 预算默认值与硬上限、`SubagentRunPolicy`、`resolve_budget` |
| `subagent/admission.py` | `admit_request`、终态归因 `attribute_*` |
| `subagent/slots.py` | `SubagentSlotRegistry`：串行槽位登记与重复保护 |
| `support/awaiting.py` | `await_if_needed`：同步/异步统一等待 |
| `model/` | 模型请求准备（见上）与请求内类型 |

## 2. 数据模型

### 2.1 Message / ToolCall / ToolResult

- `Message(role, content, tool_calls, tool_call_id, id, parent_id, tool_output)`：`id` 缺省自动分配 uuid7；`parent_id` 服务 JSONL 树形（同会话内直接前驱）。
- `ToolCall(id, name, args, details)`：`details` 是适配器诊断袋（如 `argument_error`），不进入 core 语义。
- `ToolResult`：字段最多，含错误标记 `error`/`rejected`、执行 `status`、清理 `cleanup_status`/`cleanup_confirmed`/`cleanup_error`、输出事实 `total_bytes`/`total_lines`/`shown_lines`/`truncated_by`/`artifact_path`、命令事实 `exit_code`/`duration_ms`/`semantic_success`，以及结构化 `output_metadata`。`__post_init__` 会从扁平字段物化 `output_metadata` 并保持双向一致；`cleanup_uncertain` 是派生属性（failed/uncertain/unsupported）。
- `new_id()`：手写 uuid7（RFC 9562），跨毫秒严格有序。
- 归约：`replace_or_append`（同 id 替换）、`remove_by_id`（按 id 删除）。工具结果归属靠**写入顺序**，不做插入扫描；不存在"相邻同 role 合并"。

### 2.2 ToolExecutionStatus / CleanupStatus

- `ToolExecutionStatus`：`completed` `ok`（归一为 completed）`invalid_arguments` `failed` `rejected` `timed_out` `cancelled` `cleanup_uncertain`。
- `CleanupStatus`：`not_required` `pending` `confirmed` `failed` `uncertain` `unsupported`。

## 3. Agent：有状态内存外壳（`core/agent.py`）

构造 `Agent(context, config, *, recursion_limit=DEFAULT_RECURSION_LIMIT, run_id=None)`：

- 持有 `AgentContext`；`config` 经 `dataclasses.replace` 绑定 `steer_queue` 与默认 `ToolExecutionRuntime`；
- 维护订阅者、`listener_errors`、生命周期 Hook 诊断、`_listener_tasks`、`_task`、`_follow_ups`。

| 成员 | 语义 |
| --- | --- |
| `context` / `is_running` | 只读状态 |
| `set_run_id(run_id)` | 绑定后续 core 事件的关联 id |
| `subscribe(listener) -> unsubscribe` | 幂等退订；订阅者异常被隔离记录，不造成运行失败 |
| `prompt(text)` | 追加 user 消息并跑到 turn 结束，返回本轮新消息 |
| `continue_()` | 从已有 user/tool 尾部继续（`validate_continue` 拒绝空上下文/assistant 尾部） |
| `abort() -> bool` | 取消当前 task |
| `steer(text)` | 入队，在下一轮模型请求前插入 |
| `follow_up(text)` | 空闲直接跑；运行中排队并在 run 收尾时排空（调用方取消会撤回排队项） |
| `listener_errors` / `hook_diagnostics` | 诊断隔离出口 |

`_execute` 的 finally 语义：正常完成排空观察者协程（保障终态事件可观察）；取消时先取消观察者再返回；被取消的 run 不把 steer 泄漏到下一次；未完成的 follow-up 以 `AgentRuntimeError` 失败。

## 4. 编排：ReAct 主循环

### 4.1 `run_agent_loop` / `run_agent_loop_continue`

```python
async def run_agent_loop(context, config, prompt, *, emit=None,
                         recursion_limit=DEFAULT_RECURSION_LIMIT, run_id=None) -> list[Message]
```

流程：

1. 归一化 emit（缺省 no-op）与 run_id（缺省新 uuid7）；
2. 复制 context（`_start_context`）并追加 user prompt，维护 `new_messages`；
3. emit `agent_start`；
4. `for iteration in range(recursion_limit)` 调 `run_turn`，返回 True 即停；循环耗尽抛 `RecursionLimitError`；
5. `CancelledError` → emit `aborted`（附清理元数据）并 re-raise；其它异常 → emit `error`（附错误/预算元数据）并 re-raise；
6. 成功 emit `agent_end`（payload = 本轮新消息）并返回。

`run_agent_loop_continue` 先 `context.validate_continue()` 再走同一内部循环（prompt=None）。

### 4.2 `run_turn`

```python
async def run_turn(config, iteration, is_last, emit, working, new_messages) -> bool
```

1. emit `turn_start`（`turn_index`）；
2. `new_model_message` 调模型流，追加 assistant 消息；
3. 无 `tool_calls` → emit `turn_end`，返回 True；
4. `is_last` 且有 tool_calls → `RecursionLimitError`；
5. `execute_tool_batch` → 追加 tool 消息；
6. 排空 `config.steer_queue`（注入为 user 消息）；
7. emit `turn_end`（payload=assistant，metadata 含 tool_results）；
8. 若有 `should_stop_after_turn`，以其返回值决定是否停止。

### 4.3 `execute_tool_batch`（保序 + 并发 + 取消收尾）

- 先 emit 全部 `tool_execution_queued`（含 `queue_position`），再开始执行；
- `tool_execution == "parallel"`（默认）用 task 并发；否则顺序执行；
- 结果按**模型给出的顺序**回填（`results[index]`），但事件按完成顺序 emit；
- 取消：取消所有 pending task、等待收尾，为未发出终态且已开始的调用合成 `[工具执行已取消]` 结果（`synthetic_cancelled=True`），再 re-raise；
- 结束统一 emit `tool_execution_end`（携带 status/error/cleanup/output_metadata 全量元数据）。

### 4.4 `new_tool_result`：单个调用全流程

优先级顺序：

1. `call.details["argument_error"]` → `invalid_arguments`；
2. 未知工具 → `[工具执行出错] 未知工具: <name>`；
3. `before_tool_call` Hook：返回 `ToolDecision.action != "allow"` → `rejected` 结果（内容为拒绝原因）；
4. `runtime.execute`（`tool_runtime` 未配置抛 `AgentRuntimeError`）：`on_start` emit `tool_execution_start`；`on_update` 转发 `tool_execution_update`（`subagent_*` 事件原样转发）；
5. 执行异常 → `[工具执行出错] <exc>`（模型可见）；
6. `after_tool_call` Hook 可替换结果；补 operation_id。

## 5. 模型请求准备（`core/model/request.py`）

### 5.1 `prepare_context`（请求级、只读、不落盘）

1. 克隆历史消息；
2. `invoke_context_extension(config.transform_context, ...)`（带 `context_transform_timeout`）；结果须物化为消息列表；
3. 若有 `context_preparer`：先算预算 → emit `context_budget`；不确定窗口且策略为 `fail` → preflight 并抛 `ContextPreflightError`；再以 `ContextPreparationRequest(messages, tools, budget)` 调准备器；
4. 用最终视图重算预算 → `govern_tool_messages`（按预算裁剪工具结果，保留结构化元数据摘要，`truncated_by="request_budget"`）；若视图变化则重算并再 emit；
5. 任何非 `ContextPreparationError` 异常包装为 `ContextPreparationError`。

### 5.2 `new_model_message`

1. emit `model_request_started` + `message_start`；
2. `prepare_context` → `evaluate_context_preflight` → emit `context_preflight`；不允许则抛 `ContextPreflightError`；
3. 取 `model.stream_agent`（优先）或 `model.stream`，逐事件处理：
   - `content` → emit `message_update`；
   - `thinking` → emit `message_update`（`{"type": "thinking_delta", ...}`）；
   - `tool_call` → 组装 `ToolCall`（保留 `argument_error`）并 emit `message_update`；
   - `usage` → emit `usage`；
4. 汇总为 assistant `Message`，emit `message_end`；返回；
5. finally emit `model_request_finished`（`status`：completed/cancelled/failed + error_type）。

## 6. 上下文治理

### 6.1 预算模型（`core/context/budget.py`）

- 常量：`DEFAULT_CONTEXT_WINDOW=128_000`、`DEFAULT_OUTPUT_RESERVE=4_096`、`DEFAULT_RESERVE_TOKENS=16_384`。
- `ContextBudgetInput(context_window, output_reserve, reserve_tokens, system_prompt, tool_definitions, messages, window_source)`：严格校验（正整数、非负、储备不超窗口），深拷贝输入。
- `ContextBudgetSnapshot`：`input_budget = context_window - output_reserve - reserve_tokens`；`input_tokens` 拆分为 system prompt / 工具定义 / 对话 / 工具结果四段；`headroom = input_budget - input_tokens`；`status` 为 `estimate`（window_source ∈ catalog/override/provider）或 `uncertain`。
- 估算口径：`max(1, chars // 4)`，tool_call 参数以排序 JSON 计长。
- `govern_tool_messages`：确定性、请求局部；按剩余工具消息数均分可用 token，超出的替换为"元数据摘要 + 截断正文"，永不修改会话历史。

### 6.2 Preflight（`core/context/preflight.py`）

`ContextPreflightConfig(warning_headroom_tokens=2048 | warning_headroom_ratio)` 二选一；`evaluate_context_preflight` 产出四态：

| status | allowed | 条件 |
| --- | --- | --- |
| `uncertain` | 取决于 `uncertain_budget_policy`（`allow`/`fail`） | 窗口来源不确定 |
| `over_limit` | False | `headroom < 0` |
| `near_limit` | True | `headroom <= warning_boundary` |
| `safe` | True | 其余 |

## 7. 执行运行时（`core/execution/`）

`ToolExecutionRuntime(max_concurrency=4)`：

- `asyncio.Semaphore` 限制并发；`OperationRegistry` 登记 `ToolOperation`（operation_id / tool_call_id / tool_name / status / task / cleanup 状态）；
- `execute(tool, call, timeout, operation_id, on_update, on_start)`：
  - 非 `AgentTool` 实例 → 契约错误结果；
  - 槽位内调 `tool.execute`，`timeout` 经 `asyncio.wait_for`；
  - 超时 → `_cleanup_operation` 后返回 `timed_out`（"已清理"或"停止等待但后台清理未确认"）；
  - `CancelledError` → 记录取消、执行清理、re-raise；
  - 其它异常 → `failed` 结果（单调用隔离）；
- `cleanup_status` / `cleanup_error` / `cleanup_uncertain` / `reset_cleanup_diagnostics()`：run 级清理诊断边界；
- `cancel(operation_id)` / `cancel_all()`：取消活动操作并等待收尾。

`normalize_tool_result` 把工具的任意返回值（`GovernedText`、Bash 结果对象等 duck-typed）投影为 `ToolResult`。

## 8. Subagent 领域规则（`core/subagent/`）

| 文件 | 关键内容 |
| --- | --- |
| `policy.py` | 默认值：`DEFAULT_MAX_CHILDREN_PER_RUN=4`、`DEFAULT_MAX_TURNS=8`、`DEFAULT_MAX_TOOL_CALLS=32`、`DEFAULT_TIMEOUT_SECONDS=120.0`、`DEFAULT_MAX_OUTPUT_CHARS=8_000`、`DEFAULT_CLEANUP_TIMEOUT_SECONDS=10.0`；硬上限：`MAX_MAX_TURNS=16`、`MAX_MAX_TOOL_CALLS=64`、`MAX_TIMEOUT_SECONDS=300.0`、`MAX_MAX_OUTPUT_CHARS=16_000`；`SUBAGENT_MVP_MAX_DEPTH=1`；`MAX_DIAGNOSTICS=8` / `MAX_DIAGNOSTIC_CHARS=2_000`；`SubagentRunPolicy`（frozen）、`EffectiveSubagentBudget`、`resolve_budget()`（填默认并拒绝超上限） |
| `admission.py` | `admit_request(request, policy, active_ids, profile_error, context_error)`：固定顺序校验——类型 → profile（应用层提供错误）→ budget → 深度 → context → 重复 delegation_id；`attribute_runner_exception`（FAILED/EXECUTION_FAILED）、`attribute_cancel_reason`（TIMEOUT→TIMED_OUT；BUDGET_EXCEEDED→FAILED；其余→CANCELLED/PARENT_CANCELLED） |
| `slots.py` | `SubagentSlotRegistry`：`reserve/get/release/is_full/ids/items`；`delegation_id` 不允许两个活动子运行；per-parent 配额 `max_children_per_run` 在 `delegate` 工具边界累计计数 |

**归属原则**：这些是**领域决策**（预算与上限、准入顺序、终态归因、槽位仲裁），应用层必须读取 core 常量而非维护第二份；子 Session 创建、事件发布与资源收尾装配留在 `app/composition/subagent/`。

## 9. 生命周期 Hook 与观察（`core/observation.py`）

- `LifecycleHookEvent(scope, phase, event, run_id, session_id)`：scope 为 turn/model/tool（session scope 由 session 适配层补充）；Hook 收到**脱离主事件的快照**，返回值不参与控制。
- 按注册顺序分发；同步/异步 Hook 失败与快照复制失败都隔离为运行期 `HookDiagnostic`（可由 `Agent.hook_diagnostics` / `AgentSession.lifecycle_hook_diagnostics` 查询），不进入事件递归、不参与持久化。

## 10. 设计约束与不变量

1. **零副作用**：模块顶层不建模型、不发请求、不读 key。
2. **循环条件由消息形状驱动**（最后一条有没有 tool_calls），不 import 任何具体工具。
3. **复制-提交模型**：循环在 context 副本上工作，成功才提交，失败/取消天然回滚。
4. **事件原生**：thinking/usage 不做翻译层；run_id/关联字段由 `_emit` 统一补齐。
5. **取消正确性**：`abort()` 抛 `CancelledError` 自然传播；取消路径必须完成工具清理与观察者收尾。
6. **规模约束**：单文件 ≤ 300 行、单函数 ≤ 80 行（`scripts/scale_scan.py` 强制）。

上一章：[运行方式与数据流](03-runtime-flow.md) · 下一章：[session 层](05-session-layer.md)。