# 08 · app 层：入口、组合根、技能与任务

> app 层是唯一允许"知道所有层"的地方：它负责 CLI/TUI 入口、配置目录、把 core/session/ai/tools 装配成可运行对象（组合根），并承载技能系统、任务模式与诊断展示。app 自身不承载领域规则——subagent 预算、会话提交语义等都在各自领域层。

## 一、层内地图

| 路径 | 职责 |
| --- | --- |
| `app/main.py` | CLI 入口：参数解析、会话准备、headless 运行、`skill` 子命令 |
| `app/headless.py` | 无 TUI 的运行与事件消费（含聚合输出） |
| `app/config.py` | `~/.codeagent` 配置目录、模板生成、`.env` 读写、`Settings` |
| `app/container.py` | 组合根 façade：只导出装配 API，不承载实现 |
| `app/composition/model/*` | 模型端口、预算元数据、能力解析、provider 选择 |
| `app/composition/runtime/*` | `AgentRuntime`、`AgentLoopConfig` 装配、扩展点归一 |
| `app/composition/tools/*` | 工具装配、原子工具→`AgentTool` 适配、MCP 装载 |
| `app/composition/policy.py` | 安全策略装配（core `ApprovalPolicy`） |
| `app/composition/prompts.py` | 系统提示词与技能渲染 |
| `app/composition/session/*` | `AgentSession` / `SessionManager` / `Agent` 工厂 |
| `app/composition/subagent/*` | Subagent 装配：委派工具、runner、活动槽位、生命周期 |
| `app/composition/tui/*` | TUI 装配与候选 provider 解析 |
| `app/context/agents.py` | `AGENTS.md` 发现与系统提示词组装 |
| `app/skills/*` | 技能发现、包管理、提示注入 |
| `app/tasks/*` | 任务模式、监督者、验证循环 |
| `app/errors/reporting.py`、`app/session_recovery.py`、`app/context_diagnostics.py`、`app/subagent_observability.py` | 诊断与展示投影 |
| `app/tui/*` | TUI 全部实现（见 [09-tui-layer.md](./09-tui-layer.md)） |

## 二、CLI 入口（app/main.py）

### 2.1 参数

| 参数 | 行为 |
| --- | --- |
| `--prompt TEXT` | 一次性输入；不指定则从 stdin 逐行读取 |
| `--tui` | 启动交互式终端（转移到 `app.tui.main.run_tui`） |
| `-c` / `--continue` | 继续最近有活动的会话（无会话时新建） |
| `--session ID` | 恢复指定会话继续对话 |
| `--list-sessions` | 列出全部会话（`_list_sessions`） |
| `--context` | 只读显示当前会话的上下文预算与治理诊断 |
| `--yes` | 跳过敏感操作确认全部放行；缺省 headless 下敏感操作一律拒绝 |

### 2.2 启动顺序与退出码

1. 若首个参数是 `skill` → 转入 `_skill_cli`（install / update / remove / list / reload，均支持 `--project` 作用域）。
2. `ensure_config_files()`：首次启动生成 `~/.codeagent` 模板（幂等，不覆盖）。
3. `--tui` / `--list-sessions` 提前返回；否则 `_prepare_session(args)` 创建会话，失败时返回退出码 **2**。
4. 恢复非 healthy 会话时向 stderr 打印 `format_recovery_report(...)`。
5. 执行 headless 运行（一次或循环）；`finally` 中按所有权关闭 manager 或 session。
6. 正常路径返回 **0**。

## 三、配置（app/config.py）

| 项 | 说明 |
| --- | --- |
| `CONFIG_DIR` | `~/.codeagent`（应用有意不读取仓库本地 `.env`） |
| `ensure_config_files(cfg_dir=None)` | 生成 `.env` 模板与 `models.json` 模板等，幂等 |
| `write_env_key(provider, key, env_file=None)` | 安全写入 API key（值带引号转义） |
| `configured_providers(env_file=None)` | 扫描已配置 key 的 provider 集合 |
| `Settings` | pydantic `BaseSettings`，`extra="ignore"`；工具资源字段（`tool_max_concurrency`/`tool_timeout`/`tool_max_output_bytes`/…）由此读取 |
| `warn_cwd_env()` | 检测危险的环境变量用法并告警 |
| `package_paths(...)` | 内置资源（提示词/技能）路径解析 |

凭据只存于 `~/.codeagent/.env`；`Settings` 的工具资源字段经 `ToolResourceLimits.from_config` 形成不可变限制对象注入 tools 层。

## 四、组合根（app/composition）

### 4.1 装配入口表

| 函数 | 产出 |
| --- | --- |
| `create_agent_config(cfg, *, registry, reasoning_effort, provider, model, approval_mode="deny", mcp_diagnostics, uncertain_budget_policy="allow", context_preflight, lifecycle_hooks, extensions, resource_limits, allowed_tool_names, subagent_runner, system_prompt_suffix)` | 完整 `AgentLoopConfig`（模型端口 + 工具 + 执行运行时 + 策略 + 扩展点） |
| `create_agent_runtime(cfg, **kwargs)` | `AgentRuntime`（需要显式生命周期控制时） |
| `create_agent_session(...)` | `AgentSession`（组合 core Agent + session 持久化） |
| `create_session_manager(...)` | `SessionManager` |
| `create_tools(...)` | 应用侧工具集合 |
| `create_tui_app(...)` / `TuiAssembler` | TUI 应用与装配器 |
| `runtime_for_config(config)` / `close_runtime_for_config(_async)` | 按配置解析/关闭其资源所有者 |

`create_agent_config` 的装配顺序：解析工具资源限制 → 归一运行扩展 → 构造模型客户端（`model_selection.create_llm`）→ 加载技能与系统提示词 → 装配工具（`assemble_runtime_tools`，含 MCP 与 subagent 委派工具）→ 创建 `ToolExecutionRuntime` → 组装 `AgentLoopConfig` → 探测工具能力快照（`detect_tool_capabilities`）→ 创建 `AgentRuntime`。

### 4.2 AgentRuntime 资源所有权

`AgentRuntime(config, policy, model_client, mcp_tools, tool_runtime)` 是"一个模型/工具端口集合的资源所有者"：

- 所有权锚定在配置对象上（`setattr(config, "_runtime_owner", self)`），而不是进程级可变全局状态；`runtime_for_config` 兼容 `_LazyConfig` 包装解引用。
- `close()`：幂等（`_close_task` + `asyncio.shield`），关闭序列为 取消全部工具操作 → 关闭 MCP 工具（`asyncio.to_thread`）→ 关闭模型客户端（`aclose`/`close` 自适应）；收尾时解除 `_runtime_owner` 锚定。
- `close_sync()`：无事件循环时直接 `asyncio.run`，有循环时返回可等待任务。

### 4.3 惰性装配包装

| 包装 | 用途 |
| --- | --- |
| `_LazyConfig` | 首次属性访问才构造真实配置（延迟模型客户端与工具创建） |
| `_LazyPolicy` | 会话首次需要时解析组合策略；`decide()` 委托给 runtime.policy |
| `_LazySummarizer` | 首次 `summarize` 才创建摘要器客户端 |

### 4.4 运行扩展（RuntimeExtensions）

`app/composition/runtime/extensions.py` 定义 `RuntimeExtensions`（`transform_context`、`context_preparer`、`context_budget`、`context_transform_timeout`、`before_tool_call`、`after_tool_call`、`lifecycle_hooks`）与 `normalize_runtime_extensions(extensions, lifecycle_hooks)`，把旧式 `lifecycle_hooks` 参数归一进扩展对象；缺省 `transform_context` 为 core 的 `identity_context`。扩展在 session 恢复与 TUI 模型重建时必须保留。

### 4.5 Subagent 装配（app/composition/subagent/）

领域规则（预算/准入/槽位/深度）在 `core/subagent/`；本包只做装配：

| 模块 | 职责 |
| --- | --- |
| `factory.py` | 组装委派运行环境 |
| `delegate_tool.py` | `delegate` 工具（串行只读，白名单 read/grep/find/ls/skill） |
| `profiles.py` | 子代理 profile（提示词/工具白名单/预算） |
| `runner.py` + `runner_*` | 子会话运行、结果提取、终态归因 |
| `active.py` | 活跃委派槽位仲裁 |
| `budget.py` | 预算装配（默认值来自 core，不在此重复声明） |
| `lifecycle.py` | 子会话创建、事件发布、资源收尾 |
| `event_diagnostics.py` | 事件诊断投影 |
| `context.py`、`delegate_result.py` | 上下文与结构化结果 |

## 五、技能系统（app/skills）

| 模块 | 职责 |
| --- | --- |
| `discovery.py` | `discover_skills_in`、`parse_skill_file`（frontmatter 解析）、`builtin_skills_dir`、`package_records`、`path_inside` |
| `models.py` | `Skill` 等领域模型 |
| `prompt.py` | `load_skills`、`build_skills_prompt`、`format_skill_invocation`：渐进披露——系统提示只放技能名与触发说明，正文由 `skill` 工具按需返回 |
| `runtime.py` | `CodeAgentAdapter`、`build_bootstrap_prompt`、`SkillRuntimeState` |
| `packages/manager.py` | 包安装/更新/删除（Git URL 或本地目录；用户级与 `--project` 级） |
| `packages/registry.py` | 已安装包注册表 |

三源发现顺序：内置 `resources/skills`（打包）+ 用户 `~/.codeagent/skills` + 项目级技能（含包管理器安装的）。组合根预渲染技能块注入 `make_tools(skills=...)`，模型通过 `skill` 工具获取正文。

## 六、任务系统（app/tasks）

| 模块 | 关键内容 |
| --- | --- |
| `modes.py` | `TaskMode`（StrEnum，含 `AUTO` 与显式模式）、`parse_mode_input`（`ModeInput`/`ModeParseError`）、`mode_policy(base, mode)` 包装策略；`is_mutating_command` 判定变更类命令 |
| `supervisor.py` | `TaskSupervisor`（`TaskLifecycleMixin`）：`TaskPhase`/`TaskEvent`/`TaskResult` 的阶段推进 |
| `lifecycle.py` | 任务生命周期 mixin |
| `results.py` | 任务结果模型 |
| `verification/` | 验证循环：`models.py`（约束模型）、`runner.py`（执行验证）、`workspace.py`（工作区快照/比对） |

任务模式通过对策略的包装生效：`mode_policy` 在不改动 core 策略端口的前提下叠加模式约束（例如计划模式只读、执行模式放行），验证循环在任务结束后核对结果与约束。

## 七、上下文与诊断

| 模块 | 功能 |
| --- | --- |
| `app/context/agents.py` | `load_agents_files(cwd, config_dir)`：在 cwd 与配置目录中查找 `AGENTS.md`；`build_system_prompt(base, files)` 拼接；`read_base_prompt()` 读内置基础提示词 |
| `app/context_diagnostics.py` | `format_context_diagnostics(diagnostics)`：窗口/预算/实际用量/预检/压缩/工具结果分行展示 |
| `app/session_recovery.py` | `format_recovery_report(report, include_healthy)`：健康/降级/不可用三态报告 |
| `app/errors/reporting.py` | `report_unexpected_error(operation, error)`：统一未预期错误上报文本 |
| `app/subagent_observability.py` | `SubagentLineProjector`：把 subagent 事件投影为 TUI/headless 可展示的行 |

## 八、与其他层的关系

| 方向 | 说明 |
| --- | --- |
| app → core | 组装 `AgentLoopConfig`、实现端口适配；不修改领域规则 |
| app → session | 创建会话/管理器、恢复与关闭；落盘语义在 session 层 |
| app → ai / tools | 选 provider、装工具、装载 MCP；错误分类与截断语义在各自层 |
| core/session/ai/tools → app | **禁止**；解耦由 `tests/test_decoupling.py` 与 `tests/contracts/test_app_package_layout.py` 强制 |

## 九、设计约束

1. **组合根是唯一跨层点**：实现分散在 `app/composition/*`，`container.py` 只导出 façade，实现不得反向导入 façade。
2. **领域规则不下沉也不上浮**：subagent 预算、会话提交、压缩策略只在各自领域层；app 只装配。
3. **资源所有权显式**：模型客户端、MCP 客户端、工具运行时的关闭路径集中在 `AgentRuntime`，幂等且可同步/异步调用。
4. **延迟装配是默认**：TUI 与恢复路径用 `_Lazy*` 避免无谓的模型客户端/摘要器创建。
5. **配置与密钥边界**：凭据只从 `~/.codeagent/.env` 读取；配置模板生成幂等且不覆盖用户文件。

## 相关阅读

- TUI 实现细节：[09-tui-layer.md](./09-tui-layer.md)
- 会话与持久化语义：[05-session-layer.md](./05-session-layer.md)
- 依赖矩阵与解耦检查：[10-dependency-map.md](./10-dependency-map.md)