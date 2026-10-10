# 05 · session 层：会话与持久化

> 目录：`src/codeagent/session/`。定位：**单个对话的有状态外壳 + 会话生命周期 + JSONL 持久化 + 压缩 + 会话树**。不 import `ai` / `tools` / `config`；只依赖 core 的协议与事件。

## 1. 三条核心不变量

1. **成功才落盘**：一轮工作先在历史副本上推进，`commit_turn_async` 是唯一落盘点；失败/取消只留在内存并按 `before_ids` 回滚。
2. **事件即接口**：`subscribe` 返回退订函数；`EventBus` 同步扇出，单个订阅者异常被隔离记录（`emit_errors`），不影响其它订阅者与运行。
3. **恢复永不重写源文件**：损坏记录局部降级（`degraded`），header/版本结构性错误阻止激活（`unavailable`）并保留源 JSONL。

## 2. 文件地图

| 路径 | 职责 |
| --- | --- |
| `session.py` | `AgentSession` 门面（mixin 组合） |
| `lifecycle.py` | `SessionLifecycleMixin`：retry/abort/close/steer/respond_approval/replace_config/run_sync |
| `run_coordinator.py` | `SessionRunCoordinator`：单次 run 的启动/提交/回滚/收尾 |
| `eventing.py` | `SessionEventMixin`：事件归一化、lifecycle hook 分发 |
| `session_persistence.py` | `SessionPersistence`：加载与成功 turn 提交 |
| `persistence_control.py` | `SessionPersistenceMixin`：parent 链、`ensure_persisted` |
| `compaction_runtime.py`（+ `compaction_runtime_budget.py` / `compaction_runtime_events.py`） | `SessionCompactionMixin`：压缩触发与事件 |
| `subagent.py` | `SessionSubagentMixin`：`subagent_records` |
| `constants.py` / `contracts.py` | `SUMMARY_PREFIX` / `SUMMARY_ID_PREFIX="summary-"` / `DEFAULT_CONTEXT_WINDOW=128_000` / `COMPACTION_RESERVE_TOKENS=16_384`；`SessionCloser` 协议 |
| `manager/manager.py` | `SessionManager` 顶层门面 |
| `manager/operations.py` | 创建/切换/继续最近/重命名/分叉/配置替换/关闭 |
| `manager/archive.py` | 归档与受保护删除 |
| `manager/registry.py` | adopt 会话壳、订阅迁移、LRU 驱逐 |
| `persistence/models.py` | `SessionRef` / `SessionQuery` / `SessionStore` 协议 / `CompactionEntry` / `RecoveryDiagnostic` |
| `persistence/records.py` | JSONL 记录 TypedDict 形状 |
| `persistence/codec.py` | 消息/标题/时间编解码、header 校验 |
| `persistence/commit.py` | `SessionCommitter`：turn/compaction/subagent 提交适配 |
| `persistence/jsonl/` | `JsonFileStore` + reading/writing/indexing/recovery/forking mixin |
| `persistence/memory_store.py` | `MemoryStore`（零文件系统，语义对齐） |
| `persistence/index.py` / `index_validation.py` | 派生索引结构与校验 |
| `persistence/locking.py` / `async_boundary.py` | 路径锁（线程 + 进程）与异步持久化边界 |
| `persistence/subagent_record_*.py`、`persistence/subagent_runtime.py` | 有界委派记录模型/codec/协调器 |
| `compaction/policy.py` / `service.py` / `summarizer.py` / `details.py` | 压缩策略、服务、摘要端口、文件操作提取 |
| `navigation/tree.py` | `build_tree` 纯函数 |
| `runtime/controller.py` | `SessionRuntime`：run 状态、注入、确认、取消 |
| `runtime/state.py` / `context_state.py` | `RunPhase` / `CommitStatus` / `RunOutcome` / `RuntimeFailure`；`SessionBudgetState` |
| `runtime/execution.py` | `SessionExecutionMixin.execute`：构造 Agent 并驱动 |
| `runtime/confirmation.py` | `ConfirmationCoordinator` |
| `runtime/event_lifecycle.py` / `event_translation.py` | `EventMapper` 与副作用观察 |
| `runtime/error_classification.py` | `classify_error` / `friendly_error` |
| `events/bus.py` | `EventBus` |

## 3. AgentSession：单个对话的门面

```python
class AgentSession(SessionEventMixin, SessionLifecycleMixin, SessionCompactionMixin,
                   SessionPersistenceMixin, SessionSubagentMixin): ...
```

构造（`session.py`）关键参数：`config: AgentLoopConfig`、`bus: EventBus`、`store`、`session_id`（缺省 uuid4）、`recursion_limit`、`tool_timeout`、`confirmation_timeout`、`previous_session_id`、`summarizer`、`context_window`、`compact_budget`、`compaction_policy`、`defer_persistence`、`persistence_options`、`runtime_closer`、`transform_context`、`policy`、`lifecycle_hooks`。构造末尾 `_persistence.load()` 恢复历史并订阅事件总线。

内部状态：`_history`、`_summary` / `_summary_entry_id` / `_prev_details`、`_last_input_tokens`、`_budget_state`、压缩指纹与门闩、`_runtime`（`SessionRuntime`）、`_run_coordinator`、`_closed` / `_close_task`。

### 公共 API

| 成员 | 说明 |
| --- | --- |
| `run(text, recursion_limit=None, *, policy=None)` | 驱动一轮对话（委托 run coordinator） |
| `subscribe(fn) -> unsubscribe` | 订阅会话事件 |
| `session_id` / `is_persisted` / `model_id` | 标识与持久化状态 |
| `history` | 历史消息副本 |
| `usage` / `committed_usage` / `run_usage` / `last_actual_usage` | 用量（读自持久化 / 当前轮） |
| `context_budget` / `context_diagnostics` / `context_tokens` / `context_window` | 上下文治理视图 |
| `recovery_report` | 加载时的恢复报告（healthy/degraded/unavailable） |
| `is_running` / `active_run_id` / `last_failure` / `last_outcome` / `summary` / `policy` | 运行态 |
| `retry()` / `abort()` / `wait_for_idle()` / `cancel_and_wait()` | 生命周期干预 |
| `steer(text)` / `followup(text)` / `respond_approval(request_id, approved)` | 运行中干预 |
| `replace_config(config, *, policy=None)` / `set_context_window(n)` | 热切换 |
| `compact(*, trigger="manual", budget_snapshot=None) -> bool` | 手动/自动压缩 |
| `close()` / `close_sync()` / `run_sync(text)` | 资源收尾与同步桥 |
| `subagent_records` | 有界委派记录 |
| `lifecycle_hook_diagnostics` | Hook 诊断 |

## 4. run 生命周期（`SessionRunCoordinator`）

| 阶段 | 行为 |
| --- | --- |
| `_start` | 重置预算状态；`_runtime.start_run()` 生成 run_id、phase=STARTING；emit `session_started`（payload=text，metadata 含 phase / previous_session_id）；构造 history 副本，若有摘要则头部注入 `Message(role="user", content=SUMMARY_PREFIX+summary, id="summary-"+entry_id, parent_id=entry_id)`；返回 `before_ids` |
| `_run_body` | `SessionExecutionMixin.execute`：排空注入队列 → 构造 Agent（绑 run_id、注入 policy 适配的 `before_tool_call`）→ `await agent.prompt(text)` |
| `_commit`（仅成功） | `begin_finalization()` 关闭输入窗口；过滤 `summary-` 前缀消息；`_link_persistence_parents` 重连 `parent_id`；`drain_subagent_records`；`commit_turn_async(new_messages, turn_usage, context_tokens)`；成功后 `self._history = kept_history` |
| `_maybe_auto_compact` | commit 后按阈值触发（可能抛 `PersistenceUncertainError` / 取消） |
| `_finish`（finally） | `finish_run(outcome)`；必要时补发 `turn_end`（metadata 含 terminal_phase / run_outcome / commit_status / post_commit_status / side_effect_state / cleanup_* / error_code）；`drain_subagent_records`；`_drain_lifecycle_hooks` |

### 回滚与提交状态

| 情形 | 行为 | 状态 |
| --- | --- | --- |
| execute 抛 `Exception` | `_rollback(before_ids)` + `classify_error` → `RuntimeFailure` + emit `error` | `FAILED` / `ROLLED_BACK`（cleanup 不确定 → `UNCERTAIN`） |
| `CancelledError` | 默认回滚 + emit `run_cancelled`，re-raise | `CANCELLED` / `ROLLED_BACK` |
| 提交阶段异常 | **不回滚**已写入内容 | `commit_status = PERSISTENCE_FAILED` |
| 提交后压缩失败/取消 | 已提交 | `post_commit_status ∈ {persistence_uncertain, compaction_cancelled, compaction_failed}` |

`commit_turn_async` 经 `AsyncPersistenceBoundary.run` 用 `asyncio.to_thread` 移出事件循环，并以 `shield` 保证取消不放弃持锁写入。

## 5. 运行状态机（`session/runtime/`）

- `RunPhase`（StrEnum）：`IDLE` `STARTING` `MODEL_WAIT` `TOOL_RUNNING` `AWAITING_CONFIRMATION` `CONTINUING` `COMPLETED` `FAILED` `CANCELLED` `FINALIZING`，合法迁移由 `_ALLOWED_TRANSITIONS` 定义。
- `CommitStatus`：`NOT_ATTEMPTED` `COMMITTED` `ROLLED_BACK` `PERSISTENCE_FAILED` `COMPACTION_FAILED` `UNCERTAIN`。
- `RunOutcome(run_id, phase, failure, commit_status, post_commit_status)`；`RuntimeFailure(code, message, phase, retryable, side_effect_state, cleanup_uncertain, operation_id, cause_type, budget_*)` 可转 metadata。
- `SessionRuntime`：`start_run()` / `begin_finalization()` / `finish_run(outcome)` / `record_usage` / `abort()` / `inject(text)` / `respond_approval` / `wait_for_idle` / `cancel_and_wait`；`active_run_id`（IDLE 为 None）。
- `ConfirmationCoordinator`：`register(request_id, timeout)` / `wait` / `respond`（过期或已完成返回 False）/ `cancel_all`；超时抛 `ConfirmationTimeoutError(code="approval_timeout")`。
- `EventMapper`：core 事件 → session 事件（`message_update/end` → `text_delta`/`thinking_delta`/`agent_message`；`tool_execution_*` → `tool_queued`/`tool_started`/`tool_progress`/`tool_finished`/`tool_result`），维护 phase、sequence 与子代理 `parent_sequence` 关联。
- `SideEffectObserver`：追踪 `state ∈ {none, possible, uncertain}` 与清理状态；`classify_error` 仅在可重试 provider 错误且 `side_effect_state=="none"` 且非 cleanup 不确定时标记 `retryable`。

## 6. SessionManager：多会话管理

`SessionManager(SessionManagerOperations, SessionManagerArchiveOperations, SessionManagerRegistry)`，构造参数含 `max_resident_sessions=32`（LRU 驱逐，保留 current）。

| 操作 | 语义 |
| --- | --- |
| `create(*, parent_session=None)` | 停当前会话；`defer_persistence=True`；返回新 `AgentSession` |
| `switch(session_id)` | 停当前会话 → 校验存在性 → `_adopt` |
| `continue_recent()` | 空列表则 `create()`，否则 switch 最近（按 `last_activity_at`） |
| `fork(session_id, message_id=None)` | 缺省分叉点为最后一条 user 消息；`store.fork` 只读源文件；`_adopt` 带 `previous_session_id` |
| `rename(session_id, title)` | `normalize_title`（≤20 字符）写 append-only `name` 元数据 |
| `list(query=None)` | 先按 `query.without_status()` 查存储，再用驻留运行态覆盖 `status`（idle/running/completed/failed/cancelled） |
| `archive` / `unarchive`（含批量） | append-only `archived` 元数据 |
| `delete` / `delete_many` | 需 `confirmed=True`；预检保护当前/运行中会话；拒绝空/`..`/含分隔符 id |
| `replace_config(config, *, model, effort, ...)` | 热切换所有常驻会话；必要时 `append_model_change` |
| `dispose(session_id)` | 移除并 abort |
| `subscribe(fn)` | 订阅会随 adopt 重绑到新会话 |
| `close()` / `close_sync()` | 等待全部会话、关闭 summarizer、runtime_closer |

`SessionRef(id, timestamp, cwd, parent_session, model, effort, title, last_activity_at, status, archived)`；`SessionQuery(text, model, after, before, status, archived=False)` 支持标题/id、模型、ISO 时间、状态与归档范围筛选，`matches(ref)` 负责匹配。

## 7. JSONL 持久化

### 7.1 磁盘布局

```text
~/.codeagent/sessions/
├── <session_id>.jsonl        # 权威数据（append-only）
├── <session_id>.index.json   # 派生索引（可重建）
└── .<name>.lock              # 进程 + 线程锁（默认 30s 超时）
```

权限：目录 `700`、JSONL `600`。写入 `append + flush + fsync`；`commit_turn` 记录原始 size/index，任何一步失败即截断回滚。

### 7.2 记录 schema（`persistence/records.py`，格式版本 `CURRENT_VERSION = 1`）

| type | 字段 |
| --- | --- |
| `session`（header，首行） | `type, version, id, parentSession, timestamp, cwd, lastActivityAt`（+ 可选 `model` / `effort`） |
| `message` | `type, id, parentId, role, content, timestamp`（+ `tool_calls[{id,name,args}]` / `tool_call_id` / `tool_output`） |
| `metadata` | `type, key, value, timestamp`（`name` / `archived` / `last_context_tokens` 等，append-only，取最后一次） |
| `usage` | `type, timestamp, input, output, reasoning, cached` |
| `subagent` | `type, id, timestamp, delegationId, parentRunId, childRunId, attemptId, profile, taskLabel, status, phase, summary, reasonCode, diagnostics, cleanupUncertain, result` |
| `model_change` | `type, timestamp, model, effort` |
| `compaction` | `type, id, parentId, firstKeptEntryId, timestamp, summary, details` |

- 恢复时把不可恢复的截断工具输出降级为 `INCOMPLETE, source="restored"`。
- `firstKeptEntryId` 之后的保留消息 + 最新压缩摘要共同重构上下文（见 §8）。
- 索引 `{version, source{fingerprint}, session{...}, meta, usage, lastCompaction}`；单个索引缺失/损坏/过期时只对目标会话回源扫描。

### 7.3 存储协议与双后端

`SessionStore(Protocol)`：`create/get/list/recovery_report/archive/delete/load_messages/load_context/append_message/commit_turn/append_compaction/append_model_change/set_meta/get_meta/append_usage/load_usage/append_subagent_record/load_subagent_records/fork`。

- `JsonFileStore`：`JsonlIndexingMixin + JsonlReadingMixin + JsonlRecoveryMixin + JsonlWritingMixin + JsonlForkingMixin`。
- `MemoryStore`：零文件系统，同语义（含内存事务边界）。
- `fork(session_id, target_message_id, new_session_id)`：分叉点必须是 user 消息；新 header `parentSession=源 id`；复制切点起、目标前的消息（含压缩记录的 `parentId` 修正）；临时文件 + `os.replace`，**原文件零修改**。

### 7.4 恢复报告

| status | 触发 |
| --- | --- |
| `healthy` | 无诊断 |
| `degraded` | 局部可修复：`malformed_record` / `invalid_record` / `invalid_message` / `invalid_compaction` / `invalid_subagent_record` / `compaction_cut_missing` / `index_missing|stale|corrupt` |
| `unavailable` | 结构性错误：`invalid_session_id` / `missing_session` / `unreadable_session` / `missing_header` / `incompatible_version` / `invalid_header` |

`RecoveryDiagnostic(code, message, impact, action)`；`SessionRecoveryReport(session_id, status, diagnostics, valid_message_count, skipped_record_count)`，`can_continue = status != "unavailable"`。CLI/TUI 通过 `app/session_recovery.py` 统一渲染文案。

## 8. 上下文压缩（compaction）

### 8.1 策略（`compaction/policy.py`）

`CompactionPolicyConfig(trigger_ratio=0.8, target_ratio=0.65, trigger_headroom_tokens=2048, min_recent_turns=1, enabled=True, compact_budget=None)`，强制 `target_ratio < trigger_ratio`。

- `decide_auto_compaction(snapshot, config)`：`trigger_budget = ceil(input_budget * trigger_ratio)`、`target_budget = floor(input_budget * target_ratio)`；比率触发（`input_tokens >= trigger_budget`）或 headroom 触发（`headroom <= trigger_headroom_tokens`）。
- `plan_compaction(messages, target_budget, min_recent_turns)`：按 user 边界反向累积完整 turn，产出 `cut_point` / `summarized_turns` / `kept_turns` / `reason_code ∈ {ready, no_op, no_safe_boundary, oversized_turn}`。
- `estimate_tokens` / `find_cut_point`。

### 8.2 服务（`compaction/service.py`）

`CompactionService(summarizer, budget, append_entry, min_recent_turns=1, candidate_budget=None, enforce_target=True)`：

1. `plan_compaction` 非 `ready` → `skipped`；
2. `await summarizer.summarize(window, previous_summary)`（二次压缩增量合并）；
3. 候选预算超限 → `skipped, reason_code="summary_too_large"`；
4. 持久化 `CompactionEntry(summary, details, parent_id=previous_summary_entry_id or last_history_id, first_kept_entry_id=kept[0].id)`。

`details` 来自 `extract_file_ops(window)`：`read` → `readFiles`，`write`/`edit` → `modifiedFiles`（`dict.fromkeys` 去重），与 `previous_details` 合并。

### 8.3 运行时与恢复

- auto 触发在 commit 之后；手动触发来自 TUI `/compact`；`_compaction_gate` 串行化，指纹去重（`already_compacted` / `cooldown`）。
- 恢复：`load_context` 返回最新压缩的摘要 + 从 `firstKeptEntryId` 起的保留消息；运行时会话在历史头部注入 `SUMMARY_PREFIX + summary` 的 user 消息（id 前缀 `summary-`，提交时被过滤，**永不落盘**）。
- 事件：`compaction_started` / `compaction_finished`（含 skipped 元数据）。

## 9. 会话树导航（`navigation/tree.py`）

`build_tree(refs, *, on_cycle=None) -> list[SessionNode]`：按 `parent_session` 组树；孤儿作根；同级按 `(timestamp, id)` 排序；检测环并通过 `on_cycle` 通知、把环节点降为独立根。`SessionNode(ref, children)` 供 TUI `/tree` 渲染父子缩进。

## 10. Subagent 有界运行记录

| 组件 | 语义 |
| --- | --- |
| `SubagentRunRecord` | `delegation_id / parent_run_id / status / phase / task_label / profile / child_run_id / attempt_id / summary / reason_code / diagnostics / cleanup_uncertain / result / id / timestamp`；`__post_init__` 强制长度上限（如 `MAX_SUMMARY_CHARS=16000`）；`TERMINAL_STATUSES` / `NONTERMINAL_STATUSES` |
| `bounded_result(value)` | 白名单 key（summary/failure/findings/evidence/usage/artifact/cleanup_uncertain），丢弃 prompt/context/history 等，`MAX_RESULT_BYTES=64000` |
| `record_from_event(event, expected_parent_run_id)` | 父 run 校验、事件 → 记录 |
| `SubagentRecordCoordinator(append, can_append)` | `observe`（去重、终态短路、异步 `_persist`）、`drain`、`restore`、`diagnostics`（≤8 条） |
| `fold_records(records)` | 每个 delegation 保留最新；首次终态即定稿；重启后活动记录折叠为 `abandoned/process_restarted` |

父会话只保留**有界委派事实**，不复制 child transcript；不影响普通消息、标题、最近活动、usage、压缩、fork 或 `/sessions` 列表语义。

## 11. 事件总线（`events/bus.py`）

- `EventBus.subscribe(fn) -> unsubscribe`；`emit(event)` 同步按注册顺序扇出；单订阅者异常记录到 `emit_errors` 并继续；`clear()` / `__len__`。
- `SessionEventMixin._emit` 为事件补 `session_id` / `run_id` / `sequence`，先转 `SubagentRecordCoordinator.observe`，再通知 lifecycle hooks，最后 `bus.emit`。
- Hook：同步直调、awaitable 用 `ensure_future` 跟踪；失败进 `_lifecycle_hook_diagnostics`。

上一章：[core 层](04-core-layer.md) · 下一章：[ai 层](06-ai-layer.md)。