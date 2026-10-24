# 03 · 运行方式与端到端数据流

## 1. 安装与前置

- Python 3.12+，已安装 [uv](https://docs.astral.sh/uv/)。
- 项目采用 `src/` 布局，包名 `codeagent`，构建后端 `uv_build`。

```bash
git clone https://github.com/qsxcde/codeAgent.git && cd codeAgent
uv sync --group dev      # 运行时 + 开发依赖（推荐开发时用）
uv sync                  # 只装运行时依赖
```

## 2. 配置

### 2.1 配置目录 `~/.codeagent`

首次启动由 `app/config.py` 的 `ensure_config_files()` **幂等生成**模板（已存在的文件绝不覆盖）：

| 路径 | 用途 |
| --- | --- |
| `~/.codeagent/.env` | provider 选择与各 provider 密钥（唯一密钥来源） |
| `~/.codeagent/models.json` | 自定义模型元数据，按 `id` 与内置目录 upsert 合并 |
| `~/.codeagent/sessions/` | JSONL 会话存储（`<id>.jsonl` + 索引 + 锁） |
| `~/.codeagent/mcp.json` | MCP server 与权限规则 |
| `~/.codeagent/packages/` + `registry.json` + `skills.lock.json` | Skill Package 存储 / 注册表 / 锁 |
| `~/.codeagent/AGENTS.md` | 全局 AGENTS.md（分层加载的最高层） |

**项目有意不读取当前目录下的 `.env`**（H10 安全决策），避免在任意仓库内运行时被其 `.env` 劫持流量与密钥；`Settings` 会对 CWD `.env` 一次性告警。

### 2.2 `.env` 示例与命名空间

```ini
LLM_PROVIDER=deepseek

DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_REASONING_EFFORT=high
```

| 配置类 | 认的键 | 忽略 |
| --- | --- | --- |
| `Settings`（全局） | `LLM_PROVIDER`、工具资源限制等 | `DEEPSEEK_*` / `OPENAI_*` |
| `DeepSeekConfig` | `DEEPSEEK_*`（env_prefix） | `LLM_PROVIDER` 等 |
| `OpenAIConfig` | `OPENAI_*` | 其它 |

**所有配置类必须设置 `extra="ignore"`**：共享 `.env` 中其它命名空间的键不会导致 `extra_forbidden`（曾实际踩坑，已补回归测试）。

**零配置体验**：`LLM_PROVIDER=fake`（或删掉 key）即可在没有网络与密钥时走完"对话 → 工具调用 → 事件流"闭环。

### 2.3 工具资源限制（`Settings` 字段 → `ToolResourceLimits`）

`tool_max_concurrency`（默认 4）、`tool_timeout`（默认 None）、`tool_max_timeout`（600）、`tool_max_output_bytes`（30 000）、`tool_max_output_lines`（2 000）、`tool_max_memory_bytes`（1 048 576）、`tool_cleanup_timeout`（10.0）。组合根统一解析为不可变 `ToolResourceLimits` 注入工具。

## 3. 启动方式

```bash
# 交互式 TUI
uv run codeagent --tui

# 无头单次执行
uv run codeagent --prompt "梳理登录流程的入口有哪些"

# 从 stdin 逐行读取
echo "列出本目录最大的 5 个文件" | uv run codeagent

# 继续最近会话 / 恢复指定会话
uv run codeagent -c
uv run codeagent --session <id>
```

### 3.1 CLI 参数（`app/main.py`）

| 参数 | 行为 |
| --- | --- |
| `--prompt <文本>` | 一次性输入；不指定则从 stdin 读取 |
| `--tui` | 启动交互式终端 |
| `-c` / `--continue` | 继续最近有活动的会话（无会话时新建） |
| `--session <id>` | 恢复指定会话继续对话 |
| `--list-sessions` | 列出全部会话（id / 时间 / 模型 / 标题） |
| `--context` | 只读显示当前会话的上下文预算与治理诊断 |
| `--yes` | 跳过敏感操作确认、全部放行（显式承担风险）；缺省 headless 下敏感操作一律拒绝 |

### 3.2 退出码

| 码 | 含义 |
| --- | --- |
| `0` | 正常结束 |
| `2` | 会话不可恢复（`SessionRecoveryError`）或 `codeagent skill` 操作失败；stderr 打印恢复报告 |

### 3.3 Skill Package 子命令

```bash
uv run codeagent skill install <source> [--project]
uv run codeagent skill update  <package_id> [--project]
uv run codeagent skill remove  <package_id> [--project]
uv run codeagent skill list    [--project]
uv run codeagent skill reload  [--project]
```

`--project` 作用于当前项目（`<cwd>/.codeagent`），缺省作用于用户级 `~/.codeagent`。实现见 `app/skills/packages/`（`PackageManager`）。

### 3.4 TUI 内命令

`/provider` `/model` `/effort` `/login` `/skills` `/mcp` `/tools` `/status` `/sessions`（含 `search` / `filter` / `archive` / `archived` / `recovery` / `delete`）`/tree` `/fork` `/name` `/context` `/compact` `/output` `/retry` `/continue` `/clear` `/mode` `/ask` `/plan` `/code` `/help` `/quit`；运行中按 `Esc` 打断，空闲按 `Esc` 退出并打印完整会话文档。完整命令表见 [09 · TUI](09-tui-layer.md)。

## 4. 一次对话的完整生命周期

### 4.1 启动阶段

```text
main()
 → ensure_config_files()                    # 幂等生成 ~/.codeagent 模板
 → _prepare_session(args)                   # 无 --continue/--session 时直接建会话
     或 JsonFileStore(CONFIG_DIR/"sessions") + create_session_manager(...)
        → manager.switch(id) / manager.continue_recent()   # 不可恢复 → 报告 + 退出码 2
 → （非健康会话）stderr 打印恢复报告
 → asyncio.run(_headless_once(...)) 或 _headless_loop(...) 或 TUI run_tui()
 → finally: manager.close_sync() / session.close_sync()
```

### 4.2 装配阶段（组合根）

```text
create_agent_session
 → create_agent_config
     → create_llm(provider, model, reasoning_effort) → ai 层 ChatClient
     → _load_skills(cfg) + format_skill_invocation → 渲染技能正文
     → _build_system_prompt(cfg, skills)   # 基础提示词 + 分层 AGENTS.md + bootstrap + skills 段
     → create_tools(cfg, skills)           # 8 原子工具 + MCP 工具（预算裁剪）
     → ChatModelPort(client, system_prompt, budget metadata)
     → _create_policy(approval_mode)       # tools/security 分类器 → ApprovalPolicy
 → AgentSession(config, EventBus(), store, ..., runtime_closer=runtime.close, policy=...)
```

### 4.3 一轮 run（时序）

```text
session.run(text)
 → SessionRunCoordinator._start
     · 重置预算状态、生成 run_id、phase=STARTING
     · emit session_started
     · 构造 history 副本；若有摘要，在头部注入 SUMMARY_PREFIX 消息（带 "summary-" 前缀 id）
 → SessionRuntime.execute
     · 排空 inject_queue（pending steer）
     · 构造 AgentContext + Agent（绑 run_id、注入 before_tool_calls=扩展链 + 策略门禁）
     · await agent.prompt(text)
         → run_agent_loop
             ├─ prepare_context：transform_context → describe_context_budget
             │    → context_preparer（可选）→ govern_tool_messages（请求级工具结果裁剪）
             ├─ evaluate_context_preflight（safe / near_limit / over_limit / uncertain）
             ├─ model.stream → emit text_delta / thinking_delta / usage / tool_call
             ├─ 有 tool_calls → execute_tool_batch
             │     · emit tool_queued（含 queue_position）
             │     · 并行（默认）或串行执行；new_tool_result：
             │        参数错误 → 未知工具 → before_tool_calls 链(改参/门禁) → runtime.execute → after_tool_calls 链
             │     · emit tool_started / tool_progress / tool_finished（保序结果）
             ├─ 排空 steer_queue（用户运行中注入的消息）
             ├─ 无 tool_calls → turn_end → 结束
             └─ 达到 recursion_limit（默认 50）→ RecursionLimitError
 → _commit（仅成功）
     · begin_finalization（关闭输入窗口）
     · 过滤 summary 占位消息；重连 parent_id 链
     · drain_subagent_records（有界委派记录落库）
     · commit_turn_async(new_messages, usage, context_tokens)   # ← 唯一落盘点
     · _maybe_auto_compact（阈值触发）
 → finally _finish：emit 终态事件 + drain lifecycle hooks
```

失败与取消：`Exception` → 按 `before_ids` 回滚历史、`classify_error` 生成 `RuntimeFailure`、emit `error`、`RunOutcome(FAILED, ROLLED_BACK)`；`CancelledError` → emit `run_cancelled`、回滚、re-raise；提交阶段异常不回滚已写入内容（`PERSISTENCE_FAILED`）。

### 4.4 事件消费（headless 示例）

`app/headless.py` 订阅会话事件并聚合：

- `text_delta` / `agent_message` → 追加正文；
- `tool_call` → 清空临时 parts（工具调用会打断当前文本段）；
- `usage` → 累加 input/output/cached；
- `subagent_*` → `SubagentLineProjector` 输出有界（≤240 字符）的 `子Agent状态:` 行，只透传一次终态；
- 任务模式下最后打印 `任务: <status> · <message>` 与 `用量: 输入 X · 输出 Y · 缓存命中约 Z%`。

### 4.5 TUI 事件消费

`TuiApp._on_event` → 事件缓冲区（合并增量）→ 渲染调度（30fps）→ `TuiModel.apply`（runtime 归约 + 块投影）→ `backend.render`。详见 [09 · TUI](09-tui-layer.md)。

## 5. 运行中干预

| 操作 | 语义 | 实现 |
| --- | --- | --- |
| `abort()` | 中断当前 run | `SessionRuntime.abort()`：emit `cancelling`、取消确认等待、`task.cancel()` |
| `steer(text)` | 运行中注入消息 | Agent 运行时直接 `agent.steer`（在下一次模型请求前插入）；否则入 `inject_queue` |
| `followup(text)` | 结束后续跑一轮 | `SessionLifecycleMixin.followup` → `run(text)` |
| `respond_approval(request_id, approved)` | 响应确认请求 | `ConfirmationCoordinator.respond`；超时抛 `ConfirmationTimeoutError(approval_timeout)` |
| `retry()` | 仅重试可重试失败 | 需 `last_failure["retryable"]`；emit `retry_started` |

## 6. 会话管理操作

| 操作 | 入口 | 说明 |
| --- | --- | --- |
| 新建 | `SessionManager.create()` | `defer_persistence=True`，首个成功 turn 才落盘 |
| 切换 | `switch(session_id)` | 先停当前会话，再 adopt 目标 |
| 继续最近 | `continue_recent()` | 空列表则新建；否则按 `last_activity_at` 取最近 |
| 分叉 | `fork(session_id, message_id=None)` | 从 user 消息处分叉；源文件零修改；新 header `parentSession` |
| 重命名 | `rename(session_id, title)` | append-only `name` 元数据；`normalize_title` 上限 20 字符 |
| 列表 / 搜索 | `list(query)` | `SessionQuery`（text/model/after/before/status/archived）；驻留会话叠加运行态 |
| 归档 | `archive` / `unarchive`（含批量） | append-only `archived` 元数据 |
| 删除 | `delete(session_id, confirmed=True)` | 需显式确认；预检保护当前/运行中会话；拒符号链接 |
| 热切换配置 | `replace_config(config, model=..., effort=...)` | `/provider` `/model` `/effort` |

## 7. 验证与质量命令

```bash
uv run pytest -m "unit or contract" -q --strict-markers   # 快速质量集（日常首选）
uv run pytest -q                                          # 全量离线测试
uv run ruff check src tests scripts                       # 正确性静态检查
uv run ruff format src tests scripts                      # 提交前格式化
uv run python scripts/scale_scan.py                       # 规模门禁
uv run python scripts/type_scan.py                        # 类型债务棘轮
openspec validate --specs                                 # 规格校验（25 份）
uv build                                                  # 构建 wheel / sdist
```

CI 分层、marker 约定与发布检查见 [11 · 开发指南](11-development-guide.md)。

上一章：[整体架构](../design/architecture.md) · 下一章：[core 层](04-core-layer.md)。