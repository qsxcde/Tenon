# 10 · 依赖关系与架构边界

> 本文汇总全仓库的依赖方向、允许的跨层点、强制手段（自动化测试与门禁脚本）、外部依赖与资源所有权。它是"改代码前先看这里"的清单。

## 一、层依赖矩阵

行 = 调用方，列 = 被依赖方；`✔` 允许，`✘` 禁止（由自动化测试强制），`—` 无此关系。

| ↓ 依赖 → | core | session | ai | tools | app | 外部库 |
| --- | --- | --- | --- | --- | --- | --- |
| `core/` | — | ✘ | ✘ | ✘ | ✘ | 标准库 |
| `session/` | ✔ | — | ✘ | ✘ | ✘ | 标准库 |
| `ai/` | ✘ | ✘ | — | ✘ | ✘ | httpx、pydantic-settings |
| `tools/` | ✘ | ✘ | ✘ | — | ✘ | pydantic、mcp（可选） |
| `app/`（非 composition/TUI） | ✘ | ✘ | ✘ | ✘ | 同层 | pydantic-settings、textual（仅适配区） |
| `app/composition/` + `app/container.py` + `app/main.py` | ✔ | ✔ | ✔ | ✔ | ✔ | 全部 |
| `app/tui/`（非适配区） | 经端口 | ✘ | ✘ | ✘ | 同层 | 禁止 textual |

精确的禁止前缀来自 [`tests/test_decoupling.py`](../../tests/test_decoupling.py) 的 `_forbidden_for`：

| 所在层 | 禁止 import |
| --- | --- |
| `core/` | `codeagent.config`、`codeagent.tools`、`codeagent.ai`、`codeagent.session` |
| `session/` | `codeagent.ai`、`codeagent.tools`、`codeagent.config` |
| `ai/` | `codeagent.app`、`codeagent.core`、`codeagent.session`、`codeagent.tools` |
| `tools/` | `codeagent.core`、`codeagent.session`、`codeagent.ai`、`codeagent.app` |
| `app/`（根层与子包） | `codeagent.core`、`codeagent.session`、`codeagent.ai`、`codeagent.tools` |
| `app/tui/`（非 `adapters/textual/*`） | 上述 app 禁止项 + `textual` |
| 例外：`app/container.py`、`app/main.py`、`app/composition/**` | 无限制（组合根与入口） |

实现方式：AST 解析源码 import 语句（注释与 docstring 中的字面量不参与判定），按文件所在层匹配禁止前缀；测试代码可跨层 import，不在扫描范围。

## 二、允许的跨层点（唯一清单）

| 跨层点 | 方向 | 内容 |
| --- | --- | --- |
| `app/container.py` | façade | 只导出组合根 API，不承载实现，实现不得反向导入它 |
| `app/main.py` | 入口 | CLI 参数、会话准备、headless 编排 |
| `app/composition/model/port.py` | core ↔ ai | `to_chat_message`：core `Message` → ai `ChatMessage` |
| `app/composition/model/factory.py` | core → ai | `ChatModelPort` 适配、预算元数据、能力解析 |
| `app/composition/tools/adapter.py` | core ← tools | `AtomicTool` → core `AgentTool`（含 MCP / 插件 `ext__*` 工具） |
| `app/composition/policy.py` | core ← tools/security | `SecurityDecision` → core `ApprovalPolicy`（MCP/插件权限规则同源匹配） |
| `app/composition/model/cache.py` | app 内部 | 缓存命中观测与稳定前缀诊断（不依赖 core，避免 app→core 违规） |
| `app/composition/runtime/*` | 全部 | `AgentLoopConfig` 组装与 `AgentRuntime` 所有权 |
| `app/composition/session/*` | core + session | 会话/管理器/Agent 工厂 |
| `app/composition/subagent/*` | core + session | 委派工具、runner、槽位、生命周期装配 |
| `app/composition/tui/*` | app + session + core | TUI 装配器 |

## 三、强制手段（防回归）

| 工具 | 检查内容 |
| --- | --- |
| [`tests/test_decoupling.py`](../../tests/test_decoupling.py) | 上表的层 import 规则；组合根存在性；core 不导出旧入口、core 子包不导入公共 façade；Textual 只在引擎适配区；composition 不导入 container façade；已删除 ai 模块不再被引用 |
| [`tests/contracts/test_app_package_layout.py`](../../tests/contracts/test_app_package_layout.py) | app 包布局：旧平铺模块必须不存在、规范模块可导入；TUI 各子包保持 Textual-free |
| [`tests/contracts/test_tui_boundaries.py`](../../tests/contracts/test_tui_boundaries.py) | TUI 端口/状态/展示/命令边界 |
| [`tests/contracts/test_ai_import_boundaries.py`](../../tests/contracts/test_ai_import_boundaries.py) | ai 层导入边界 |
| [`tests/contracts/test_session_boundaries.py`](../../tests/contracts/test_session_boundaries.py)、`test_session_layout.py` | session 层边界与布局 |
| [`tests/contracts/test_runtime_boundaries.py`](../../tests/contracts/test_runtime_boundaries.py)、`test_lifecycle_hook_boundaries.py` | 运行时与生命周期 Hook 边界（含 core 不导入具体 provider/tools/MCP/Skill/UI） |
| [`tests/contracts/test_scale_limits.py`](../../tests/contracts/test_scale_limits.py) + `scripts/scale_scan.py` | 生产层单文件 ≤ 300 行、单函数 ≤ 80 行；豁免只能在 `COMPATIBILITY_EXCEPTIONS` 逐项登记 |
| `scripts/type_scan.py` + `docs/type-baseline.json` | mypy 按 `core`/`ai`/`tools`/`session`/`app` 五层棘轮，任何一层错误数回升即失败 |

## 四、外部依赖

### 4.1 运行时依赖（pyproject.toml）

| 依赖 | 用途 | 出现位置 |
| --- | --- | --- |
| `httpx` | 模型 HTTP 传输与流式 | ai/transport |
| `mcp` | MCP 客户端 SDK | tools/mcp（ImportError 有界处理，属可选边界） |
| `pydantic-settings` | provider 配置与 `Settings` | ai/providers、app/config |
| `pyyaml` | 技能 frontmatter / 配置解析 | app/skills |
| `textual` | TUI 引擎 | 仅 `app/tui/adapters/textual/` |

### 4.2 开发依赖

`mypy`、`pytest`、`pytest-asyncio`、`pytest-cov`、`pytest-timeout`、`ruff`；构建后端 `uv_build`。Python 要求 `>=3.12`。

### 4.3 可选外部可执行文件

`rg`（ripgrep）、`fd`：grep/find 的加速路径，缺失时自动回退纯 Python 实现，语义保持一致；能力探测会把缺失如实上报。

## 五、运行期数据流依赖图

```
CLI / TUI 输入
   │
   ▼
AgentSession（session） ──提交──▶ Agent（core） ──▶ run_agent_loop（core）
   │                                   │
   │                     prepare_context / preflight（core/context）
   │                                   │
   │                          ModelPort（app/composition/model → ai）
   │                                   │
   │                      tool_call/batch（core/orchestration）
   │                                   │
   │                    ToolExecutionRuntime（core/execution）
   │                                   │
   │                    AgentTool（app/composition/tools ← tools/*）
   │                                   │
   │                    安全决策（app/composition/policy ← tools/security）
   ▼
事件（core/contracts/events）→ EventBus（session/events）
   │                                   │
   ▼                                   ▼
JSONL 持久化（session/store）      TUI / headless 消费
```

横切关注点归属：

| 关注点 | 归属 | 说明 |
| --- | --- | --- |
| 上下文预算/预检/治理 | `core/context/*` | provider 中立，纯计算 |
| 压缩策略与执行 | `session/compaction/*` | 落盘与恢复语义 |
| 工具并发/超时/清理 | `core/execution/runtime.py` | 与具体工具解耦 |
| 工具资源限制默认值 | `tools/shared/resource_limits.py` | 组合根注入，不散落 |
| Subagent 预算/准入/槽位/深度 | `core/subagent/*` | app 层不得维护第二份默认值或上限 |
| Subagent 装配 | `app/composition/subagent/*` | 子会话创建、事件发布、资源收尾 |
| 模型错误分类/脱敏 | `ai/errors.py` | 单点实现 |
| 安全规则 | `tools/security/*`（含 `permission_rules.py` 供 MCP/插件共用） | 分类是纯函数，裁定在 core 策略端口 |
| 沙箱策略 | `tools/execution/sandbox.py` | 纯计划函数；受限策略无后端 fail-closed |
| 写前快照 | `tools/shared/checkpoints.py` | 工具层基础设施，不进入会话持久化 |

## 六、资源所有权与生命周期

| 资源 | 所有者 | 关闭路径 |
| --- | --- | --- |
| 模型客户端（含摘要器） | `AgentRuntime` | `close()` / `close_sync()`；`_LazySummarizer.aclose` |
| MCP 客户端 | `AgentRuntime.mcp_tools` | `close_mcp_tools`（`asyncio.to_thread`） |
| 工具执行运行时 | `AgentRuntime.tool_runtime` | `cancel_all()` |
| 会话/管理器 | CLI 或 TUI 组合层 | `SessionManager.close_sync()` / session `close_sync` |
| 所有权锚点 | 配置对象 `config._runtime_owner` | 关闭后解除；`runtime_for_config` 解析（兼容 `_LazyConfig`） |

规则：不把 runtime 状态放进进程级可变全局（`_RUNTIMES_BY_CONFIG` 是显式接受旧写法但不持有状态的兼容索引）。

## 七、配置命名空间

| 命名空间 | 内容 | 读取位置 |
| --- | --- | --- |
| `~/.codeagent/.env` | `<PROVIDER>_API_KEY` / `_BASE_URL` / `_MODEL` / `_REASONING_EFFORT`；工具资源字段 | provider `BaseSettings`、`app/config.Settings` |
| `~/.codeagent/models.json` | 用户模型目录覆盖（camelCase/snake_case 双拼写） | `ai/catalog/store.py` |
| `~/.codeagent/sessions/` | 会话 JSONL + 索引 + 锁 | `session/store` |
| `~/.codeagent/skills/`（及项目级技能） | 技能与安装的 Package | `app/skills` |
| `AGENTS.md` | 仓库/用户级上下文提示 | `app/context/agents.py` |

应用有意不读取仓库本地 `.env`，避免"运行目录决定凭据"的歧义。

## 八、判断"改动是否越界"的三问

1. **方向问**：新增 import 是否出现在允许的跨层点之外？先跑 `tests/test_decoupling.py`。
2. **归属问**：这个默认值/规则/上限是否已有领域归属？在别处维护第二份即违规（典型：subagent 预算、工具资源默认值）。
3. **规模问**：新代码是否让文件逼近 300 行/函数 80 行？越接近越应按职责拆分，而不是登记豁免。

## 相关阅读

- 架构总览与不变量：[02-architecture.md](./02-architecture.md)
- 各层职责入口：[04-core-layer.md](./04-core-layer.md) ~ [09-tui-layer.md](./09-tui-layer.md)
- 门禁命令与扩展流程：[11-development-guide.md](./11-development-guide.md)