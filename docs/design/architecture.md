# codeagent 架构设计文档

> 版本: v0.7(扩展与运行期安全落地后的架构校准)
> 适用范围: 自研编排(2026-08-14 起,已弃用 langgraph/langchain)的 Code Agent 项目
> 更新日期: 2026-10-25(合并原 `docs/wiki/02-architecture.md` 的结构事实内容,本文成为架构的唯一权威入口)
> 事实来源: 本文描述当前代码树;演进决策见 [self-built-orchestration-blueprint.md](./self-built-orchestration-blueprint.md)(决策与收益记录)、迭代记录 `docs/iteration/v0.1.md` ~ `v0.7.md`;分层实现细节见 `docs/wiki/` 的 04~12 章

## 1. 背景与目标

本项目是基于**自研编排**的编程 Agent(codeagent)。设计目标:

1. **可演进**:从"单个工具调用型 Agent"平滑演进到多 Agent / 多会话 / 平台部署。
2. **可替换**:更换模型供应商(DeepSeek / OpenAI / Qwen / GLM / Kimi / MiniMax)、更换工具集、更换存储,均不触碰 Agent 编排代码。
3. **可感知**:会话的运行过程以事件流对外暴露,CLI、TUI、测试和 CI 都能订阅,而不是只拿一个最终返回值；Web/HTTP 订阅暂未实现。
4. **可测试**:核心编排层零网络、零密钥即可运行(注入 fake 模型)。

设计参考:Pi-Agent(`earendil-works/pi`)的"三层协作 / 双层 loop / 事件驱动 / 会话即状态"思想。

**编排演进**:v0.1 曾基于 langgraph(StateGraph / ToolNode / checkpointer)。2026-08-14 自研编排落地(`self-built-orchestration` change):自研 ReAct 主循环 + 消息归约 + JSONL 树形会话替换 langgraph,pyproject 移除 langchain-core/langgraph。当前树**无任何 langgraph/langchain 依赖**。

## 2. 设计原则:两条正交轴

整个结构由两条独立的分离轴合成,不要混淆:

| 轴 | 分的是什么 | 来源 |
|---|---|---|
| **横切轴:依赖方向** | config / 工具 / 编排 / 调用 之间谁认识谁 | 端口-适配器(hexagonal) |
| **纵切轴:生命周期** | 装配(Factory) / 单个对话(Session) / 会话生命周期(Runtime) | Pi-Agent 三层协作 |

- **横切轴**解决"零件怎么装":依赖单向流动,组合根是唯一交汇点。
- **纵切轴**解决"装好之后会话怎么活":三层生命周期不同、变化率不同,不该绑在一个类里。

**Loop 双层(无状态循环 / 有状态 Agent)是另一条正交结构**,不要与横切/纵切混淆:

| 层 | 位置 | 职责 |
|---|---|---|
| 无状态循环 | `core/orchestration/loop.py` 的 `run_agent_loop` / `run_agent_loop_continue` | 纯函数式驱动:复制 context、迭代 turn、emit 事件、返回新消息 |
| 有状态内存外壳 | `core/agent.py` 的 `Agent` | 持有 `AgentContext`、run_id、订阅者、steer/follow-up 队列、任务句柄 |
| 会话外壳 | `session/session.py` 的 `AgentSession` | 补齐历史提交、落盘、压缩、会话级事件、干预与生命周期 |

循环在 context 的**副本**上工作,成功返回后才提交到 `Agent`;失败/取消天然回滚——这是会话层简单回滚边界的基础。

## 3. 现状

- 工具链:`uv` + `src` 布局,Python 3.12。
- 依赖:`httpx`、`mcp`、`pydantic`、`pydantic-settings`、`pyyaml`、`textual`;dev 依赖 `pytest`。**无 langchain/langgraph**。
- 入口:`pyproject.toml` 中 `codeagent = "codeagent.app.main:main"`。
- **已完成(v0.1~v0.5 功能范围)**:
- 密钥外置:固定目录 `~/.codeagent/.env`(首次启动幂等生成模板),**不读取 CWD 下 `.env`**(安全决策 H10);全局 `Settings` 保存 provider 选择和工具资源限制，工具资源由组合根解析为不可变 `ToolResourceLimits`。
- `ai/` 层:模型基础设施(provider / catalog / model / transport / errors),**不负责应用装配**;支持 6 个真实 provider(deepseek / openai / qwen / glm / kimi / minimax)+ 离线 `fake`;模型客户端自研(httpx + 自研 SSE 解析,thinking / usage 全量透传);`errors.py` 统一分类网络、超时、限流、认证、参数、服务端和未知失败并提供脱敏诊断;provider/model/effort 选择位于 `app/composition/model/selection.py`,适配自研循环的 `ChatModelPort` 在组合根。
- 工具层(hexagonal):`AtomicTool` 无状态基类 + `FsOps` 文件系统抽象缝 + cwd 注入;read / write / edit / bash / grep / find / ls / skill / web_fetch / web_search / todo 十一个内建工具(声明式 `BUILTIN_TOOL_SPECS`);MCP 客户端可接入 `tools/list` / `tools/call`，以 `mcp__<server>__<tool>` 命名空间化，并实施全局 / 单 server / 描述长度分组预算;扩展插件经 `tools/plugins/` 以 `ext__<id>__<tool>` 命名注入;`ToolResourceLimits` 在组合根统一注入并发、超时、输出字节/行、预览内存和清理等待上限；`grep`/`find` 只把 `rg`/`fd` 作为不经 shell 的可选加速，失败时回退纯 Python；bash 带危险命令黑名单(字符串正则 + shlex 分词语义级检测)、树级进程击杀、默认 120s 超时(上限 600)、30k 输出截断与三档沙箱(受限策略无后端 fail-closed);`tools/security/` 提供执行前安全分类器(deny > ask > allow，MCP/插件权限同源匹配)，`tools/capabilities.py` 在组合根生成只读环境能力快照；`tools/shared/checkpoints.py` 为 write/edit 提供写前快照与 `codeagent undo`。
- `core/` Agent Runtime:根级 `agent.py` 为运行时外壳，`contracts/`、`context/`、`model/`、`execution/`、`orchestration/`、`observation.py` 和 `support/` 按职责组织纯内存、全异步实现；模块顶层零副作用。
- `session/` 会话层:bus + session + manager + store(JSONL 树形,含 usage 与父级 `subagent` entry)+ compaction + tree;`SessionRef.last_activity_at` 在创建时初始化并随成功消息追加更新,最近会话按该值排序;会话标题支持自动派生和 append-only `name` 元数据重命名;`SessionQuery` 统一标题/id、模型、时间、运行状态和归档范围筛选,管理器为驻留会话叠加只读运行态;归档使用 append-only 元数据,删除由存储边界完成路径保护和索引清理;恢复报告区分 healthy/degraded/unavailable,有效损坏记录局部降级,结构性错误携带可操作建议;父会话通过独立且有界的运行记录保留委派事实，非终态记录重启后转为 `abandoned/process_restarted`，不改变普通消息、标题、最近活动、usage、压缩、fork 或 `/sessions` 子会话列表；`abort()` 运行中断、`steer()` 运行中注入、`followup()` 结束后续跑一轮、成功轮次才落盘、失败/取消内存回滚。
- `app/composition/subagent/` 是 Subagent 的应用装配边界：`profiles.py` 作为唯一 registry 定义 `explore`/`review`（只读）与 `implement`（受限可写，禁 `delegate`/MCP）的角色、输出指导和工具白名单；`delegate_tool.py` 与 `runner.py` 在创建子 Session 前复用同一校验入口，`factory.py` 和 TUI 组合根复用同一装配策略，`subagent_max_concurrency` 控制有界并发（默认 1 = 串行）。`read_only` 只作为历史记录中可能出现的有界文本，不是新的 delegate 输入；`tester` 和命令执行不属于当前能力。
- 会话列表、搜索、筛选和 `continue_recent` 使用派生索引完成候选元数据读取与排序；单个索引缺失、损坏或过期时只对目标会话回源，其它会话不重复扫描 JSONL，最终目标恢复允许单独检查。
- 事件按消息、模型请求、工具生命周期、运行控制和 Subagent 委派分组；模型请求显式发布 `model_request_started / model_request_finished`，工具生命周期包含 `tool_queued / tool_started / tool_progress / tool_finished / tool_result`，Subagent 使用 `subagent_queued / subagent_started / subagent_progress / subagent_finished`，事件通过 `run_id`、`parent_run_id`、`child_run_id`、`delegation_id`、`tool_call_id` 和结构化状态字段关联。完整事件契约见 §5.7。
- 入口形态:`app/main.py` headless 双路径(`--prompt` / stdin)+ `--tui` 交互式终端(斜杠命令 / 模糊补全 / 选择器 / Markdown / 滚动 / `/login` / `/skills` / `/mcp` / `/tree` 等命令体系)；headless 对 Subagent 输出有界 `子Agent状态:` 行，TUI 使用独立委派块和状态栏聚合，不复制 child transcript。
- Skills 系统(v0.3 阶段 1~4):SKILL.md 格式 + 三源发现(内建 `resources/skills/` / 个人 `<config_dir>/skills/` / 项目 `<cwd>/.codeagent/skills/`)+ 渐进式披露(名称/描述入 system prompt,**正文经 `skill` 工具按需获取**)+ TUI `/skills` 手动加载。
- MCP(v0.3 阶段 2):用户级配置发现、工具 schema 适配、权限分类、`/mcp` 可见诊断与分组预算。
- token 用量透明(v0.3 阶段 3):usage 归一、会话级 append-only 落库、`/status` 与 headless CLI 展示输入 / 输出 / 缓存命中（不做费用估算）。
- 会话树(v0.3 阶段 4):`build_tree` 纯函数、`/tree` 导航及 `/sessions list` 父子缩进展示。
- 安全确认环(v0.2):执行前 `ApprovalPolicy`(组合根把 `tools/security/` 分类器适配为端口),`ask` 由循环 emit `confirmation_requested` 并等待会话确认队列;headless 缺省 deny(fail closed),`--yes` 逃生舱。
- 测试基建:`tests/` 按行为域与源码层级分包 + `FakeClient`(离线假模型),`uv run pytest -q` **1870 passed**(2026-10-24,macOS / Python 3.12;此前 v0.5 基线为 1711 passed，v0.5.0 发布记录为 1695 passed，3 skipped / 1698 collected,2026-10-10, Windows);离线评测 `python -m evals` 4/4；本地质量集与既有 CI 分层门禁保持独立，并已接入 Ruff、release check 和 TUI 性能基线。最新门禁结果以 `docs/testing.md` 与 CI 实测为准。
- TUI 性能验收:`benchmark/` 使用 schema v2 的固定离线 fixture 测量提交首帧、首 token、帧 p50/p95、控制延迟、峰值 Python 分配和协调器的 dropped/over-budget 计数；`compare_benchmark.py` 只在 schema、平台、Python、视口和 fixture 一致时比较，`update_tui_baseline.py` 负责生成受约束的 Linux/Python 3.12 候选基线。

**v0.7 当前状态与远期**:V4-01～V4-38、V5-00～V5-10、v0.6 正确性硬化与 v0.7 扩展/运行期安全均已完成实现与验收；发布包版本已提升为 `0.7.0`，v0.6 修复与 v0.7 能力同版交付，CHANGELOG 已收口。当前工程治理已接入覆盖率报告、Ruff（覆盖 `src tests evals scripts`）、构建安装冒烟和 CI 跨平台矩阵；TUI schema v2 的正式 Linux/Python 3.12 基线仍按 CI artifact 与人工复核流程推进，性能暂保持非阻塞。Subagent 已从"串行只读 MVP"扩展为**默认串行、可配置有界并发**，并新增 `implement` 受限可写 profile（工具白名单含 write/edit/bash，禁 `delegate`/MCP，深度仍固定为 1）；插件系统已交付 v1（仅贡献工具、目录即信任、默认需确认）；执行期已有三档沙箱与写前 checkpoint。工作区合并、跨进程恢复与自动重试、长期记忆、费用估算、Web/HTTP 事件流订阅与 Web UI 仍不在范围内。

## 4. 总体结构

分层边界如下(`app/` 是唯一跨层装配区,`core/` 零外部依赖):

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
│ 纯内存/全异步 │ providers/transport/catalog│ atomic/mcp/plugins  │
│ 零外部依赖    │ shapes/errors             │ security/execution  │
├───────────────┴───────────────────────────┴─────────────────────┤
│ resources/     内建 prompts（system.md）与 skills（*.md）        │
└─────────────────────────────────────────────────────────────────┘
```

### 4.1 目录树

```text
codeagent/
├── pyproject.toml / uv.lock          # 依赖、CLI 入口(codeagent.app.main:main)
├── README.md / AGENTS.md             # 说明 + Agent 工作指南
├── .env.example                      # 密钥模板(不入库;实际密钥在 ~/.codeagent/.env)
├── docs/                             # design/(需求/架构/蓝图)+ wiki/(代码级)+ iteration/(权威)+ benchmarks
├── openspec/                         # OpenSpec 规格与归档变更
│
├── src/codeagent/
│   ├── __init__.py / __main__.py     # 版本 + python -m codeagent
│   │
│   ├── app/                          # [组合根 + 入口] ★ 唯一跨层交汇点
│   │   ├── container.py              #   组合根:create_agent_config / create_agent_session
│   │   │                             #     / create_session_manager / create_tui_app
│   │   ├── main.py                   #   CLI 入口:--prompt / stdin / --tui
│   │   ├── config.py                 #   全局 Settings + ~/.codeagent 模板幂等生成
│   │   ├── context/agents.py         #   AGENTS.md 分层加载 + 基础提示词
│   │   ├── subagent_observability.py #   headless 委派状态行投影(无终端依赖)
│   │   ├── errors/reporting.py       #   安全错误呈现与诊断记录
│   │   ├── skills/                   #   Skill 发现、提示词、运行时与 Package 生命周期
│   │   │   └── packages/             #   Package 清单、注册表和安装
│   │   ├── tasks/                    #   模式、监督、结果和验证工作流
│   │   │   └── verification/         #   工作区快照、验证命令和结果模型
│   │   ├── composition/              #   按模型/runtime/session/tools/TUI 装配分包
│   │   │   ├── model/                #   选择、预算、能力快照、端口和模型工厂
│   │   │   ├── runtime/              #   Agent runtime 资源所有权
│   │   │   ├── session/              #   AgentSession / SessionManager 装配
│   │   │   ├── tools/                #   工具适配与定义
│   │   │   ├── subagent/             #   Subagent profile、runner、工厂和 delegate 适配
│   │   │   └── tui/                  #   TUI 配置与工厂
│   │   └── tui/                      #   [调用层·TUI] 交互式终端 ✅ 已落地
│   │       ├── ports/backend.py      #     Textual-free TuiBackend 端口
│   │       ├── adapters/textual/     #     唯一具体 Textual 适配区
│   │       ├── state/                #     TuiModel、runtime、Transcript、委派投影
│   │       ├── presentation/         #     blocks、状态栏、组件、文本和主题
│   │       ├── commands/             #     解析、补全、分派、能力诊断和命令协调
│   │       ├── session/              #     会话动作、对话和恢复
│   │       ├── rendering/            #     帧调度与渲染协调
│   │       ├── benchmark/            #     离线性能基准与指标
│   │       └── main.py               #     TUI 入口(--tui 转交此处,装配在组合根)
│   │
│   ├── ai/                           # [模型基础设施层]  ← pi-ai ✅ 已落地
│   │   ├── model/                    #   ChatClient / 消息 / 响应 / 工具 / 流事件契约
│   │   ├── catalog/                  #   模型目录与解析
│   │   │   ├── spec.py               #     ModelSpec(不可变值对象)
│   │   │   ├── builtin.py            #     内置模型目录(deepseek/openai/qwen/glm/kimi/minimax)
│   │   │   ├── store.py              #     models.json 读写(upsert 合并)
│   │   │   └── registry.py           #     ModelRegistry 两遍解析(精确 id → 别名)
│   │   ├── transport/                #   OpenAI 兼容传输层
│   │   │   ├── sse.py                 #     SSEParser(thinking/usage 全量透传)
│   │   │   ├── retry.py               #     有界重试次数与退避策略
│   │   │   └── openai_compat.py      #     OpenAICompatClient(httpx,重试/流式)
│   │   ├── errors.py                  #   Provider 错误分类与安全诊断
│   │   └── providers/                #   每 provider 一个文件,配置+工厂自包含
│   │       ├── deepseek.py / openai.py / qwen.py / glm.py / kimi.py / minimax.py
│   │       └── fake.py               #   FakeClient + make_llm(离线测试)
│   │
│   ├── core/                         # [Agent Runtime]  ← pi-agent-core ✅ 已落地
│   │   ├── agent.py                  #   Agent(prompt/continue/abort/steer/follow-up)
│   │   ├── contracts/                #   messages / events / errors / ports
│   │   ├── context/                  #   AgentContext、预算与 preflight
│   │   ├── model/                    #   模型请求准备与流归一化
│   │   ├── execution/                #   工具执行、状态、清理与结果
│   │   ├── orchestration/            #   loop、turn、工具批次/调用与配置
│   │   └── support/                  #   通用同步/异步辅助
│   │
│   ├── session/                      # [Session + Runtime]  ← Pi 核心增量 ✅ 已落地
│   │   ├── session.py                #   AgentSession: run / subscribe / abort / steer / followup
│   │   ├── manager/                  #   SessionManager 外观、操作、注册表
│   │   ├── persistence/              #   通用协议、记录、锁、提交协调
│   │   │   ├── subagent_record_model.py  # 有界委派记录与恢复折叠
│   │   │   ├── subagent_record_codec.py  # 事件/JSONL codec 与 payload 边界
│   │   │   ├── subagent_runtime.py       # 异步观察、顺序写入与诊断
│   │   │   ├── memory_recovery.py    #   MemoryStore 恢复报告
│   │   │   └── jsonl/                #   JSONL store、读取、写入、索引、恢复、分叉
│   │   ├── runtime/                  #   运行控制、确认、事件映射、错误策略
│   │   ├── compaction/               #   上下文压缩策略、摘要和详情
│   │   ├── events/                    #   事件总线
│   │   └── navigation/               #   会话树与分支导航
│   │
│   ├── tools/                        # [工具层] hexagonal ✅ 已落地
│   │   ├── base.py                   #   AtomicTool 实现(由组合根适配为 AgentTool)
│   │   ├── registry.py               #   make_tools 工厂(11 个内建工具,声明式 ToolSpec,cwd/ops/沙箱/快照注入)
│   │   ├── capabilities.py           #   shell/平台/检索器/权限能力只读快照
│   │   ├── security/                  #   执行前安全分类器与 deny/ask/allow 决策(含 MCP/插件权限)
│   │   ├── atomic/                   #   read / write / edit / bash / grep / find / ls / skill / web_fetch / web_search / todo
│   │   ├── mcp/                      #   MCP client / loader / adapter / budget / config
│   │   ├── plugins/                  #   扩展插件 manifest / loader / permissions
│   │   ├── execution/                #   Shell / process / sandbox / optional rg/fd execution boundaries
│   │   └── shared/                   #   FsOps / paths / textfile / truncate / resource_limits / checkpoints / mutation_queue / ignore
│   │
│   └── resources/                    # [资源层]  ← Pi 资源系统(v0.3 已启用 skills)
│       └── skills/ prompts/          #   *.md 技能文件 / 提示词模板
│
└── tests/                            # 按行为域分包(全量离线测试以 CI 实测为准)
    ├── conftest.py / fixtures/       # 全局 marker、隔离环境和共享离线夹具
    ├── contracts/                    # AI、core、session、tools 边界契约
    ├── ai/ / core/ / mcp/            # 模型、编排和 MCP 行为
    ├── app/container/                # 组合根装配与生命周期
    ├── session/store/                 # JSONL、MemoryStore、索引和记录
    │   └── behavior/                 # 运行、恢复、取消、确认、压缩和用量
    ├── tools/atomic/                  # 原子工具；execution/security 保持独立
    └── tui/view/                      # TUI 生命周期、命令、会话、状态和扩展
```

### 4.2 模块职责一览

| 目录/文件 | 一句话职责 | 关键约束 |
|---|---|---|
| `app/container.py` | 组合根,创建端口 / 会话 / 会话管理器 / TUI 应用 | 全项目唯一 import 所有层的地方 |
| `app/main.py` | CLI 入口(--prompt / stdin / --tui) | 与 container 同为跨层 import 允许点 |
| `app/config.py` | 全局配置(仅 provider 无关字段)+ 模板生成 | 只被 container / ai 读取 |
| `app/context/agents.py` | AGENTS.md 分层加载 + 基础提示词 | 纯函数,可离线测 |
| `app/skills/` | SKILL.md 三源发现、提示词、运行时和 Package 生命周期 | 不持有全局服务状态;三源同名遮蔽 个人>项目>内建 |
| `app/tasks/` | 任务模式、监督、结果和验证工作流 | 验证命令结构化执行且禁止变更型命令 |
| `app/subagent_observability.py` | headless Subagent 状态行的有界投影与终态去重 | 不依赖终端或 core;只消费结构化事件字段 |
| `app/composition/model/` | AI 客户端端口适配、模型选择、能力快照和上下文预算 | 仅组合根跨越 `ai`/`core`;规范模块为唯一模型装配入口 |
| `app/composition/subagent/` | Subagent profile registry、delegate 入口、串行 runner 和子 Session 工厂 | profile 策略只在应用层；Explore/Review 仅允许五个只读工具，子 Session 不递归、不进入普通 store |
| `app/tui/state/` | TUI 事件投影、工具/委派生命周期归约、历史恢复和 Transcript 增量视口布局 | Subagent 先校验父 run;不把 child 事件送入父 runtime |
| `app/tui/session/` | 会话命令、异步动作、对话协调、快照恢复和恢复诊断展示 | 恢复按成本后台化，并校验当前 session，丢弃过期结果；不可恢复目标不替换当前 transcript |
| `app/tui/presentation/` | blocks、组件、Markdown、状态栏、输出和主题 | `SubagentBlock` 默认折叠且所有详情有界;不 import Textual |
| `app/tui/adapters/textual/` | 当前唯一 Textual 引擎实现 | 只能依赖 TUI 端口和纯表现数据 |
| `ai/` | 模型基础设施:模型契约、provider、transport、catalog、错误分类 | 不 import 应用、工具、编排；模型重试只包围完整模型请求 |
| `core/` | 纯内存 Agent Runtime:上下文、循环、工具执行、生命周期状态与事件 | 不 import config / ai / tools / session |
| `session/` | AgentSession 外壳、事件适配、持久化、分支与压缩 | 不 import ai / tools / config；父级 Subagent 记录有界且不复制 child transcript |
| `tools/` | 工具层:原子工具 + 注册表 + 安全分类器 + 能力探测 + 共享设施 | 不 import 模型、编排;`shared/` 只被 tools 内部使用 |
| `app/tui/` | 交互式终端(应用壳/组件/命令/后端端口) | application 只依赖 TuiBackend 端口;禁止 import textual(具体后端除外) |
| `resources/` | 技能 / 提示词按需加载 | v0.3 skills 已启用 |

长会话渲染由 `app/tui/state/transcript_index.py` 维护稳定 block token、revision 和按宽度的累计高度，
`transcript_index_tree.py` 负责固定 chunk 的前缀定位；`transcript_layout.py` 只物化视口及 overscan，
`transcript_progressive.py` 在相同窗口上协作准备。退出文档仍通过 `iter_lines()` 完整生成，工具结果则由
`presentation/output.py` 按页读取，避免普通帧为全部历史或完整工具正文建立临时行列表。

应用层生产文件由 `scripts/scale_scan.py` 统一检查：文件不超过 300 行、函数不超过 80 行。
已迁移的根层、composition 和 TUI 平铺导入路径已删除；生产代码和测试必须使用职责子包中的规范模块，
仅 `main.py`、`container.py`、`config.py` 与 `tui/main.py` 作为稳定入口保留。运行时资源所有权挂在
`AgentLoopConfig._runtime_owner`，不再通过模块级可变 registry 持有。
`tests/contracts/test_app_architecture.py` 同时检查 app 导入图无环和该所有权约束。

会话子模块的规范入口、异步持久化边界和已删除兼容路径见
[`session-layout.md`](session-layout.md)。

### 4.3 配置命名空间(重要)

`~/.codeagent/.env` 是共享文件,但全局 `Settings` 与各 provider 的 `Config` **各自解析、各自只认自己的键**:

| 配置类 | 认的键 | 忽略 |
|---|---|---|
| `Settings`(全局) | `LLM_PROVIDER` 等 | `DEEPSEEK_*` / `OPENAI_*` |
| `DeepSeekConfig` | `DEEPSEEK_*`(env_prefix) | `LLM_PROVIDER` 等 |
| `OpenAIConfig` | `OPENAI_*`(env_prefix) | 其它 |

因此**所有配置类必须设置 `extra="ignore"`**,否则共享 `.env` 中任一命名空间的键都会让其它配置类报 `extra_forbidden`(实现时实际踩过,已修复并补防回归测试)。配置来源固定为 `~/.codeagent/.env`,不读 CWD 相对路径 `.env`(H10)。

## 5. 核心契约

`core/` 认识外部世界的唯一窗口是 `AgentLoopConfig`、`core/contracts/ports.py` 的端口和 `core/contracts/messages.py` 的消息与事件模型;下文按这三类契约组织。

### 5.1 AgentLoopConfig —— 编排认识外部世界的唯一窗口

`core/orchestration/config.py` 的 `AgentLoopConfig` 是编排认识外部世界的唯一窗口:

| 字段 | 类型 | 含义 |
|---|---|---|
| `model` | `ModelPort` | 模型端口(组合根适配 ai 层 `ChatClient`) |
| `tools` | `list[AgentTool]` | 统一工具契约列表 |
| `transform_context` / `context_preparer` / `context_transform_timeout` | 扩展点 | 请求级上下文变换与准备(有超时) |
| `context_budget` / `context_preflight` / `uncertain_budget_policy` | 上下文治理 | 预算提供者、preflight 配置、不确定窗口策略(`allow`/`fail`) |
| `before_tool_calls` / `after_tool_calls` | 工具 Hook 链 | 有序 pre 链(通知/改参/门禁)与 post 链(变换/脱敏);安全策略门禁固定链尾 |
| `lifecycle_hooks` | `tuple[LifecycleHook, ...]` | 只读观察者(turn/model/tool scope) |
| `tool_execution` | `"parallel"` \| 顺序 | 工具批次执行方式 |
| `tool_timeout` / `tool_runtime` | 执行控制 | 单工具超时;受控执行端口 |
| `should_stop_after_turn` | 回调 | 自定义停止条件 |
| `steer_queue` | `list[str]` | 运行中注入队列(runtime 持有,Agent 在工具批次后排空) |
| `context_window` / `output_reserve` / `reserve_tokens` / `window_source` | 回退元数据 | 老适配器的预算回退值 |

**为什么 `model` 与 `tools` 分离**:工具列表作为实现 `AgentTool` 的数据传入,编排层不需要知道工具内部实现;加/换工具时 `core/` 零改动。具体 Atomic/MCP 工具在组合根先经 `AgentToolAdapter` 挂载。

**`store` 不在端口内**:core 循环从不落盘(成功轮次才写由会话层负责),会话存储只经 `AgentSession` / `SessionManager` 注入(`session-manager` change 清理死字段)。

### 5.2 run_agent_loop —— 自研 ReAct 主循环

```python
# core/orchestration/loop.py
async def run_agent_loop(context, config, prompt, *, emit=None, recursion_limit=50) -> list[Message]:
    # for 循环:模型 → 工具 → 继续/结束
    # 模型调用 stream/generate → emit(text_delta / thinking_delta / agent_message)
    # 有 tool_calls → 经 config.before_tool_call 决策 → 执行并回填结果
    # 无 tool_calls → 结束本轮
```

要点:

- 模块顶层**没有任何副作用**(不建模型、不发请求、不读 key),平台可直接 import。
- 循环条件由消息形状驱动(最后一条有没有 `tool_calls`),**不 import 任何具体工具**。
- 事件在循环内**直接 emit**(无翻译层),thinking / usage 事件原生化。
- 观察 Hook 通过 `LifecycleHookEvent(scope, phase, event, run_id, session_id)` 接收脱离主事件的快照；core 只发送 turn/model/tool scope，session 适配层补充 session scope，Hook 返回值不参与控制。
- `app/composition/runtime/extensions.py` 提供不可变的 `RuntimeExtensions` 组合对象，统一承载 ContextTransformer、预算上下文扩展、工具 Hook、生命周期 Hook 和扩展超时；runtime、session 恢复与 TUI 重建复用同一对象，core/session 只消费协议。
- `recursion_limit`(默认 50)是循环计数;`abort()` 抛 CancelledError 自然传播;同步旧工具的 `asyncio.to_thread` 只存在于组合根适配器,core 只看到异步 `AgentTool.execute`。
- 安全策略经 `policy.decide` 在每个工具调用执行前调用。

### 5.3 AgentSession —— 有状态会话壳(单个对话)

```python
# session/session.py
class AgentSession:
    def __init__(self, config, bus, store=None, session_id=None,
                 recursion_limit=50, tool_timeout=None, summarizer=None,
                 lifecycle_hooks=()): ...

    async def run(self, text) -> None: ...    # 直接驱动 run_agent_loop,发布事件,不返回值
    async def steer(self, text) -> None: ...  # 运行中注入消息
    async def followup(self) -> None: ...     # 结束后续跑一轮
    def subscribe(self, fn) -> Callable[[], None]: ...   # 订阅事件,返回退订函数
    def abort(self) -> None: ...              # 取消当前 run
```

- **`run` 发布事件流而不是返回单个回复**——CLI/TUI/测试/CI 都通过 `subscribe` 感知进度。
- **全异步**:`run()` 为 `async def`,直接驱动 `core/orchestration/loop.py` 的 `run_agent_loop`,把循环内事件经 `EventBus` 分发。
- **成功才落盘**:本轮工作在局部历史副本上,`self._history` 仅成功时重赋值,store 循环在其后;失败/取消时内存回滚(历史从未被就地修改,回滚是空操作)。
- **会话历史**:自研 `Message`(role/content/tool_calls/tool_call_id/id/parentId),`id` 用 uuid7;归约按 tool_call_id 归属、按 id 删除。
- **事件类型**按生命周期分组：会话/消息事件、工具生命周期事件（排队、开始、进度、结束、结果）、确认与运行控制事件；工具事件保留类型化状态和 metadata 双重兼容字段。父级 Subagent 事件在唯一观察点转换为独立有界记录并异步追加；记录 drain 在父回合提交和取消/失败收尾前完成，迟到/重复终态按 `delegation_id` 折叠。分组明细见 §5.7。
- **观察 Hook**按注册顺序接收 turn、model、tool、session 的 started/updated/finished 快照；core 与 session 通过 `AgentLoopConfig.lifecycle_hooks` 注入，具体实现仍由组合根提供。同步/异步 Hook 失败和快照复制失败均隔离为运行期 `HookDiagnostic`，可由 `Agent.hook_diagnostics` 与 `AgentSession.lifecycle_hook_diagnostics` 查询，不进入事件递归或会话持久化。
- **上下文压缩**:`summarizer` 端口(session-compaction),自动/手动触发窗口摘要。

### 5.4 SessionManager / SessionStore —— 会话生命周期与持久化

```python
# session/manager.py + store.py
class SessionManager:
    def __init__(self, config, store=None, model="", effort="", ...): ...
    def create(self) -> SessionRef: ...
    def switch(self, session_id) -> None: ...
    def fork(self, session_id) -> SessionRef: ...   # 分支会话(JSONL 树形)
    def rename(self, session_id, title) -> str: ... # 追加显示标题元数据
    def list(self, query=None) -> list[SessionRef]: ... # 只读搜索/筛选并叠加驻留状态
    def dispose(self, session_id) -> None: ...
    def replace_config(self, config, *, model, effort) -> None: ...   # 热切换

class SessionStore:
    # JSONL 树形:每轮 append 一条(含消息),重启可恢复;fork 只读源文件、新文件带 parentId
```

- `SessionStore`(JSONL 树形,`id`/`parentId`):会话可恢复、可切换、可分叉,并提供结构化 `recovery_report`;MemoryStore 镜像同一语义,两个后端行为一致。坏行/无效消息可局部降级,header/版本结构性错误阻止激活并保留源文件。`subagent` entry 只保存受限运行事实；恢复按最新记录折叠，活动记录转换为 `abandoned/process_restarted`，不启动子运行、不重写原 JSONL。
- `SessionManager` 薄管理器:ports 装配一次共享(模型端口 / 工具无状态,跨会话复用);`rename` 和 archive 只追加规范化元数据,不改变消息、压缩或 fork 父级;`list(query)` 通过索引读取会话元数据并为驻留对象覆盖运行状态,不写 JSONL;delete_many 先执行目标预检并保护当前/运行中会话;`replace_config` 支持 /provider /model /effort 热切换。
- `fork`(v0.2 提前落地):只读源文件、新文件带 `parentSession`,按压缩切点拷贝保留窗口、父链重连。

### 5.5 端口清单(`core/contracts/ports.py`)

| 端口 | 方法 | 说明 |
|---|---|---|
| `ModelPort` | `model_id` 属性；`generate(messages, tools)`；`stream(messages, tools)` | 编排消费的最小模型调用面 |
| `AgentTool`（`runtime_checkable`） | `name` / `description` / `parameters`；`execute(tool_call_id, arguments, *, signal, on_update)` | 唯一由 Runtime 消费的工具契约 |
| `ToolExecutionRuntimePort` | `execute(tool, call, timeout, operation_id, on_update)` | 受控执行端口 |
| `ToolCleanupPort` | `cleanup(operation_id)` | 外部资源清理端口 |
| `ApprovalPolicy` | `decide(tool_name, args) -> PolicyDecision` | 执行前安全策略（allow/ask/deny） |
| `Summarizer` | `summarize(messages, prev_summary)` | 压缩摘要端口 |
| `PolicyDecision`（frozen dataclass） | `action` / `reason` / `warning` | 安全决策结果 |
| `ToolDecision`（frozen dataclass） | `allow()` / `block(reason)` | Hook 的通用执行前决策 |
| `ModelResponse` / `StreamEvent` | dataclass | 非流式结果 / 流式统一事件（content、thinking、tool_call、finish、usage） |

### 5.6 消息模型(`core/contracts/messages.py`)

| 类型 | 关键字段 |
|---|---|
| `Message` | `role`（user/assistant/tool）、`content`、`tool_calls: list[ToolCall]`、`tool_call_id`、`id`（uuid7）、`parent_id`、`tool_output: ToolOutputMetadata` |
| `ToolCall` | `id` / `name` / `args: dict` / `details`（适配器诊断袋） |
| `ToolResult` | `tool_call_id` / `content` / `error` / `name` / `rejected` / `status` / `operation_id` / `cleanup_*` / 输出统计（bytes、lines、truncated_by…）/ `exit_code` / `duration_ms` / `semantic_success` / `output_metadata` |
| `new_id()` | 手写 uuid7（48 位毫秒时间戳 + 版本 + 62 位随机），时间有序，服务 JSONL 排序与按 id 删除 |
| 归约 | `replace_or_append`（同 id 替换否则追加）、`remove_by_id`（按 id 删除） |
| 状态常量 | `ToolExecutionStatus`（completed/failed/rejected/timed_out/cancelled/invalid_arguments/cleanup_uncertain…）、`CleanupStatus`（not_required/pending/confirmed/failed/uncertain/unsupported） |

### 5.7 事件驱动

#### 5.7.1 事件流路径

```text
core 循环 emit(AgentEvent)
   → Agent._emit（补 run_id，隔离订阅者异常，通知 lifecycle hooks）
   → session/eventing.py 归一化（补 session_id/run_id/sequence）
   → EventBus.emit（同步扇出，单订阅者异常隔离记录）
   → TUI 事件缓冲区 / headless 聚合 / 测试订阅 / CI
```

#### 5.7.2 事件分组(`core/contracts/events.py` 的 `EventType`)

| 分组 | 事件 |
|---|---|
| Agent 生命周期 | `agent_start` `agent_end` `turn_start` `turn_end` `message_start` `message_update` `message_end` `aborted` `error` |
| 模型请求 | `model_request_started` `model_request_finished` `text_delta` `thinking_delta` `agent_message` `usage` |
| 工具生命周期 | `tool_call` `tool_queued` `tool_started` `tool_progress` `tool_finished` `tool_result`（core 侧为 `tool_execution_queued/start/update/end`，session 层映射） |
| 运行控制 | `session_started` `run_cancelled` `cancelling` `retry_started` `confirmation_requested` |
| 上下文治理 | `context_budget` `context_preflight` `compaction_started` `compaction_finished` |
| 会话恢复 | `restore_started` `restore_finished` |
| Subagent | `subagent_queued` `subagent_started` `subagent_progress` `subagent_finished` |

`AgentEvent` 同时携带**类型化关联字段**（`run_id` / `tool_call_id` / `operation_id` / `delegation_id` / `parent_run_id` / `child_run_id` / `sequence` / `status` / `cleanup_*` 等）与 `metadata` 兼容袋；`__post_init__` 保持两者一致。

#### 5.7.3 Subagent 事件关联

父子事件通过 `delegation_id`、`parent_run_id`、`child_run_id`、`attempt_id`、`depth`、`child_sequence`/`parent_sequence` 关联；`subagent_finished` 是唯一终态事件。父级 Subagent 事件在唯一观察点转换为**有界运行记录**异步落库（见 `docs/wiki/05-session-layer.md`）。

## 6. 组合根:三层解耦的唯一交汇点

```python
# app/container.py
def create_agent_config(cfg=None, *, registry=None, reasoning_effort=None,
                       provider=None, model=None, approval_mode="deny",
                       extensions=None) -> AgentLoopConfig:
    client = create_llm(cfg, registry=registry, reasoning_effort=reasoning_effort,
                        provider=provider, model=model)               # app.composition.model_selection.create_llm
    skills, _ = _load_skills(cfg)                                     # 技能一次加载两处消费
    rendered = {s.name: format_skill_invocation(s) for s in skills}
    config = AgentLoopConfig(
        model=ChatModelPort(client, system_prompt=_build_system_prompt(cfg, skills)),
        tools=create_tools(cfg, skills=rendered),                     # tools/registry.make_tools
    )
    # policy 由 composition/session 作为 before_tool_call 适配，不进入 core config
    return config

def create_agent_session(cfg=None, *, registry=None, store=None, session_id=None, ...) -> AgentSession:
    config = create_agent_config(cfg, registry=registry, ...)
    return AgentSession(config, EventBus(), store=store, session_id=session_id, ...)

def create_session_manager(cfg=None, *, store=None, ...) -> SessionManager: ...
def create_tui_app(cfg=None, *, backend=None, store=None, ...) -> TuiApp: ...
```

`app/container.py` 是 façade,实现位于 `app/composition/*`:

| 工厂 | 产物 | 说明 |
|---|---|---|
| `create_agent_config(cfg, *, registry, reasoning_effort, provider, model, approval_mode, extensions, ...)` | `AgentLoopConfig` | 装配 client、skills、system prompt、tools、`ChatModelPort` |
| `create_agent_runtime(cfg, ...)` | `AgentRuntime` | 资源所有者（模型客户端、MCP、工具运行时） |
| `create_agent_session(cfg, ...)` | `AgentSession` | 会话外壳（可默认装配 `SerialSubagentRunner`） |
| `create_session_manager(cfg, ...)` | `SessionManager` | 多会话管理 |
| `create_tui_app(cfg, ...)` | `TuiApp` | TUI 装配，`rebuild_ports` 支持热切换 |

要点:

- `approval_mode`(`deny` / `interactive` / `allow`):headless 缺省 `deny`(ask 降级 deny,fail closed),TUI 传 `interactive`(ask 由确认条响应),`--yes` 传 `allow`。
- `store` 经 `AgentSession` / `SessionManager` 注入;**不进 `AgentLoopConfig`**(core 循环不落盘)。
- `registry` / `reasoning_effort` / `provider` / `model` 均可注入;`create_tui_app` 的 `rebuild_ports` 回调支持运行时热切换(/provider /model /effort /login)。
- `extensions` 是组合根统一归一的 `RuntimeExtensions`；旧的 `lifecycle_hooks` 参数继续兼容，但恢复、模型切换和 TUI 重建均从同一不可变集合重建配置。
- `create_agent_config` 返回端口(平台 / 测试用);`create_agent_session` 供 CLI 入口消费。

详细装配见 `docs/wiki/08-app-layer.md`。

## 7. 运行时生命周期

```
启动:   app/main.py → ensure_config_files() → create_agent_session()
        → create_agent_config:create_llm + _load_skills + _build_system_prompt + make_tools + _create_policy
        → AgentSession(config, bus, store)

一轮:   session.run(text)   [async]
        → run_agent_loop(config)
            → model.stream → emit(text_delta / thinking_delta / usage)
            → agent_message(有 tool_calls 则继续)
            → 逐个 tool_call → policy.decide(allow/ask/deny) → invoke → emit(tool_call / tool_result)
            → 无 tool_calls → turn_end
        → [成功] store.append(entry)   (失败/取消:内存回滚,不落盘)

TUI:    app/main.py --tui → create_tui_app() → TuiApp.start()
        → 订阅 AgentSession 事件 → TuiModel.apply 更新组件状态 → 合并渲染
        → 提交:session.run(text);Esc:运行中 abort / 空闲退出打印完整文档
        → /provider /model /effort → rebuild_ports() 热切换; /login → save_key() 写 .env + 热切换

干预:   abort() 中断当前 run;steer() 运行中注入消息;followup() 结束后续跑一轮
生命周期: manager.create() / switch() / fork() / dispose()
```

## 8. 依赖规则与全局不变量

### 8.1 依赖规则

| 模块 | 可以 import | 禁止 import |
|---|---|---|
| `app/config.py` | —（只被 container / ai 读取） | core、session、tools、app/tui |
| `ai/` / `tools/` | config（工具层内部：`shared/`） | core、session |
| `core/` | 只有自身 `ports`/契约 | config、ai、tools、session |
| `session/` | core（ports/loop/events/messages）、事件总线 | ai、tools、config |
| `app/container.py` | 全部（唯一交汇点） | — |
| `app/main.py` | container、session、bus | core、ai、tools（直接） |
| `app/tui/` | session、core(events)、TUI state/presentation | ai、tools、config；textual 仅 `adapters/textual/` |

补充说明(2026-10-10 边界校准):

- `tools/` 禁止 import `core/` 是现行规则而非疏漏:具体工具在组合根经 `AgentToolAdapter` 挂载为 `AgentTool`,因此需要 core 契约的委派入口 `delegate` 属于 `app/composition/subagent/delegate_tool.py`,不下沉到 `tools/`。
- Subagent 的**领域规则**位于 `core/subagent/`:`policy.py`(预算默认值与硬上限、深度与配额、诊断上限)、`admission.py`(准入顺序与终态归因)、`slots.py`(委派槽位登记与重复保护)。`app/composition/subagent/` 只保留子 Session 工厂、事件发布与资源收尾装配,并通过 `budget.py` 等模块复用 core 常量,不再维护第二份数值。
- 规模、格式化与类型现在是可执行门禁:`scripts/scale_scan.py` + `tests/contracts/test_scale_limits.py` 覆盖全部生产层(≤300 行文件 / ≤80 行函数),`ruff format --check` 固化唯一格式化方案,`scripts/type_scan.py` + `docs/type-baseline.json` 以分层棘轮约束 mypy 债务。

### 8.2 全局不变量(改代码前必读)

1. **成功才落盘**:会话历史在局部副本上推进,`commit_turn_async` 是唯一成功落盘点;失败/取消只留在内存并被回滚。
2. **core 零副作用**:模块顶层不建模型、不发请求、不读 key。
3. **事件即接口**:状态的对外可见性经事件与只读属性暴露,UI 不直接读内部结构。
4. **安全 fail closed**:headless 无 `--yes` 时敏感操作一律拒绝;shell 分词失败按最保守处理。
5. **资源有界**:工具输出、Subagent 预算与输出、诊断、MCP 工具数与描述长度均有硬上限。
6. **恢复不重写源文件**:损坏 JSONL 局部降级;结构性错误阻止激活并保留原文件;非终态 Subagent 记录折叠为 `abandoned/process_restarted`。
7. **门禁可执行**:规模(≤300 行/≤80 行函数)、格式化(ruff format)、类型棘轮(type_scan)是 CI 强制项而非口头约定。

## 9. 解耦判据(泄漏检测)

分层是否成立,不看文件多整齐,看**改一层要不要动另一层**:

| 变更 | 应动的文件 | 若还动了 | 结论 |
|---|---|---|---|
| 新增一个 provider | `ai/` + 环境变量 | `session.py` / `core/` | ❌ 泄漏 |
| 新增/更换一个工具 | `tools/` | `core/orchestration/` / `ai/` | ❌ 泄漏 |
| 改编排形状(改循环) | `core/` | `ai/` / `tools/` | ❌ 泄漏 |
| 换会话存储 | `store` + `container` | `app/main.py` / `core/` | ❌ 泄漏 |
| 加会话分叉 | `session/` | `core/` | ❌ 泄漏 |

最严格判据:**`core/` 里 grep 不到 `config / tools / ai / session` 字面量 → 横切解耦成立;`session/` 里 grep 不到 `ai / tools / config` → 纵切解耦成立。**

> `tests/test_decoupling.py` 逐文件 AST 扫描强制校验(2026-08-14 重写,断言持续扩充),并带 anti-wargaming 守卫(`test_scan_has_content` / `test_composition_roots_exist` / `test_textual_only_in_engine_adapter_zone`),规则写错或例外文件被删都会被抓住。依赖矩阵与跨层允许点详见 `docs/wiki/10-dependency-map.md`。

## 10. 决策溯源

| 结构 | 对应讨论结论 |
|---|---|
| `app/container.py` + `app/config.py` | 组合根 + 配置层独立(2026-08-13 由顶层迁入 `app/` 包) |
| 自研编排(`core/orchestration/loop.py` + `core/contracts/messages.py`) | 2026-08-14 `self-built-orchestration`:自研 ReAct 主循环 + 消息归约替换 langgraph;删除 `ai/bridge`、`core/state.py`、`core/nodes/`;pyproject 移除 langchain-core/langgraph(决策见 blueprint.md) |
| `core/` 端口(model / tools / policy) | 端口-适配器、编排层独立;`store` 不进端口(会话层负责落盘) |
| `session/`(session/manager/store/bus/compaction) | Pi 三层协作的 Session + Runtime、会话即状态;JSONL 树形(2026-08-14 格式结论) |
| `events.py` + `bus.py` | Pi 事件驱动,替代"返回单个 AIMessage";消息、工具生命周期和运行控制事件 |
| `tools/security/` + `ApprovalPolicy` | 2026-08-15 `security-permissions`:执行前安全策略,ask 确认环 + headless fail closed |
| `tools/`(AtomicTool + FsOps) | 2026-08-13 工具层 hexagonal 重构(E8):文件系统抽象缝 + cwd 注入 + 并发写锁 |
| `app/skills/` + `skill` 工具 | 2026-08-19 `skills-system`:三源发现 + 渐进式披露(描述入 prompt,正文经 skill 工具按需获取) |
| `app/context/agents.py` | AGENTS.md 全局→项目→子目录分层加载(2026-08-15 `agents-md-hierarchy`) |
| `app/tui/`(state/presentation/commands/adapters) | TUI 恢复 MVP(2026-08-13,E9~E11)+ 命令体系 / 补全 / 选择器(2026-08-14)+ /login(2026-08-19) |
| `resources/` | Pi 资源系统（v0.3 skills 已启用；插件系统移出本迭代） |

## 11. 落地路线

| 阶段 | 范围 | 产物 |
|---|---|---|
| **v0.1 最小可跑** | `config + container + ai + tools + core + session + app(main/tui)` | CLI/TUI 可对话、可调用七个工具(当时集;v0.3 加 skill 后为八工具),事件流可订阅(历史记录) |
| **v0.2 会话完善** | 编排自研 + JSONL 树形 `SessionStore` + `SessionManager` + `compaction` + 安全确认环 + AGENTS.md + `/fork` + TUI 命令体系 | 会话可恢复、可切换、可压缩、可分叉;安全确认;命令/补全/选择器 |
| **v0.3 生态成型** | Skills(✅)+ MCP(✅)+ 成本透明(✅)+ 会话树 UI(✅);插件 / 轻量记忆 / Web 经评估移出(见 E5/E4/E12) | 扩展生态、体验差异、平台导航 |
| **v0.4 Runtime 产品化** | Runtime 可靠性、上下文治理、TUI / Session 交互、生命周期 Hook、工具与 Provider 稳定性 | V4-01～V4-38 已完成实现；`0.4.0` 元数据和 `v0.4.0` 标签已固定 |
| **v0.5 Subagent 协作** | 串行只读委派:`delegate` 工具、`explore` / `review` profile registry、显式上下文隔离、有界预算与取消、结构化结果与证据、父子事件诊断、父会话有界运行记录、TUI / headless 可观察性 | V5-00～V5-10 已完成实现与验收;新增 `subagent-contract` / `subagent-runtime` / `subagent-observability` / `subagent-run-records` 主规格;`0.5.0` 元数据与 CHANGELOG 已收口 |
| **v0.6 正确性硬化** | 安全分类语义化、只读搜索边界、合并输出上限、中英 token 估算、会话索引增量 | 已实现;`docs/iteration/v0.6.md` 记录证据 |
| **v0.7 扩展与运行期安全** | 工具注册表数据化、审批封闭枚举、web/todo 工具、工具执行瀑布链、扩展插件目录、Subagent 有界并发与 `implement`、API 形状注册表、三档沙箱、写前 checkpoint/`undo`、缓存诊断、离线评测 | 已实现并推送;详见 `docs/iteration/v0.7.md` |

v0.7 当前进度:V4-01～V4-38、V5-00～V5-10、v0.6 三项硬化与 v0.7 扩展/运行期安全均已落地。2026-10-24(macOS / Python 3.12)复核结果为 `uv run pytest -q` **1870 passed**(无 skipped)、快速质量集 **1718 passed / 152 deselected**、集成层 **931 passed**、`python -m evals` **4/4**、`openspec validate --specs` **25/25**。此前 v0.5 基线为 1711 passed / 86.35% / 24 规格(2026-10-18);覆盖率以 CI `quality-fast` 实测为准。v0.5.0 发布时点为 `1695 passed，3 skipped`(1698 collected)/ 覆盖率 84.40%(2026-10-10,Windows / Python 3.12);v0.4 基线为 1532 passed / 83.61% / 20 规格(2026-08-30,macOS)。仓库内 TUI schema v1 基线保留为历史数据,schema v2 候选由 CI 生成并人工复核,性能暂不启用硬阈值。最新门禁数据请以 `docs/testing.md` 与 CI 实测为准,本文不再逐次校准测试数字。

## 12. 参考

- 编排自研决策与收益:[`self-built-orchestration-blueprint.md`](./self-built-orchestration-blueprint.md)
- 需求基线:[`requirements-analysis.md`](./requirements-analysis.md)(FR / NFR / F-xx 编号出处)
- 代码级 wiki:`docs/wiki/README.md`(分层实现细节、依赖关系图、开发指南与术语表)
- 迭代记录:[`docs/iteration/v0.1.md`](../iteration/v0.1.md) / [`v0.2.md`](../iteration/v0.2.md) / [`v0.3.md`](../iteration/v0.3.md) / [`v0.4.md`](../iteration/v0.4.md)(权威)
- 历史审计结论:2026-08-21 文档漂移、安全与测试基线审计的修复结论已记录在 `docs/iteration/v0.3.md` §6.5；原始审计文件不在当前工作树中。
- [earendil-works/pi](https://github.com/earendil-works/pi) — Pi Agent SDK(三层协作 / 双层 loop / 事件驱动 / 会话即状态)
- [learning-pi-agent](https://github.com/yamsfeer/learning-pi-agent) — 架构深度笔记
- [how-pi-agent-works](https://github.com/myxiaoao/how-pi-agent-works) — 中文教学实现
