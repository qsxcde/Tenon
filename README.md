# codeagent

本地、单用户、可离线验证的编程 Agent。自研 ReAct 编排（2026-08-14 起不再依赖 langgraph / langchain），采用端口-适配器（hexagonal）分层，提供交互式终端（TUI）与无头 CLI 两种形态。

`v0.5.0` + v0.6 硬化（未发版） · Python 3.12 · 全量离线测试 **1759 passed** · 快速集覆盖率 **86%** · OpenSpec **24/24**

设计参考 [earendil-works/pi](https://github.com/earendil-works/pi) 的"三层协作 / 双层 loop / 事件驱动 / 会话即状态"思想。架构见 [`docs/design/architecture.md`](docs/design/architecture.md)，需求基线见 [`docs/design/requirements-analysis.md`](docs/design/requirements-analysis.md)，v0.6 硬化路线与实测证据见 [`docs/design/roadmap-v0.6.md`](docs/design/roadmap-v0.6.md)，按版本的权威过程记录见 [`docs/iteration/`](docs/iteration/)。

---

## 一、项目描述

### 它解决什么问题

多数 Agent 框架把编排、模型适配、工具实现和持久化揉在同一层，换模型要动业务代码、加工具要动核心循环、出问题只能看最终返回值。`codeagent` 把这四件事彻底拆开：核心层是纯内存的可测试运行时，模型/工具/存储全部通过端口注入，运行过程以事件流对外暴露，任何一层都能被替换而不牵动其它层。

### 四条设计目标

| 目标 | 含义 |
| --- | --- |
| **可演进** | 从单工具调用 Agent 平滑演进到多 Agent（v0.5 已交付串行只读委派）、多会话、平台部署 |
| **可替换** | 换模型供应商、换工具集、换存储后端都不触碰编排代码 |
| **可感知** | 会话过程以事件流暴露，CLI / TUI / 测试 / CI 都能订阅，而非只拿最终返回值 |
| **可测试** | 核心层零网络、零密钥即可运行，注入 `FakeClient` 离线假模型即可跑通全量测试 |

### 当前能力

- **交互式 TUI**（`--tui`）：无边框多行 composer（Enter 提交 / Shift+Enter 换行）、流式正文、可展开的工具结果与 edit/write 红绿意图差异、model/effort/cwd 状态栏、Markdown 渲染、Esc 运行中打断、斜杠命令体系与模糊补全。
- **Headless CLI**：`--prompt` 一次性输入或 stdin 逐行读取，事件聚合输出最终回复；敏感操作默认 fail closed。
- **自研编排**：`core/agent.py` 纯内存 `Agent` 外壳 + `core/orchestration/loop.py` 的 ReAct 主循环（模型 → 工具 → 继续/结束）。
- **8 个内建工具**：`read` / `write` / `edit` / `bash` / `grep` / `find` / `ls` / `skill`，无状态 `AtomicTool` + `FsOps` 文件系统抽象缝；`grep` / `find` 把 `rg` / `fd` 只当可选加速，失败回退纯 Python。
- **MCP 客户端**：按用户配置接入 `tools/list` / `tools/call`，工具名 `mcp__<server>__<tool>` 命名空间化并实施分组预算。
- **Skills 技能系统**：`SKILL.md` 三源发现（内建 / 个人 / 项目）+ 渐进式披露（描述入 system prompt，正文经 `skill` 工具按需取），`codeagent skill` 子命令管理技能包。
- **会话层**：JSONL 树形持久化，可恢复 / 切换 / 分叉 / 归档 / 删除 / 压缩；标题、搜索、筛选、恢复诊断；成功轮次才落盘，失败与取消内存回滚；`abort` / `steer` / `followup`。
- **Subagent 委派（v0.5）**：`delegate` 工具把只读子任务交给独立子 Agent——串行、`explore` / `review` 两种 profile、工具白名单限 `read`/`grep`/`find`/`ls`/`skill`、预算与输出有界、深度固定 1；父级收回有界摘要与结构化证据而非完整 transcript，委派事实以有界 `subagent` 记录落库。
- **安全确认环**：执行前 `ApprovalPolicy` 三档 deny / ask / allow（危险命令黑名单 + shlex 语义检测 + 文件访问边界）。
- **用量透明**：归一并累计输入 / 输出 / 推理 / 缓存命中 token，`/status` 与 CLI 可见（**不做费用估算**）。
- **上下文治理**：token 预算、preflight、自动压缩与恢复回归，`--context` 只读输出治理诊断。

### 明确不做

费用估算、Web / HTTP 事件订阅、轻量记忆、插件系统、自动化任务调度、并行子 Agent、子 Agent 写权限与工作区合并、跨进程恢复与自动重试、`tester` profile 与子 Agent 命令执行。

---

## 二、项目技术栈

### 运行时与构建

| 项 | 选型 |
| --- | --- |
| 语言版本 | Python 3.12+（[`.python-version`](.python-version)） |
| 包与虚拟环境管理 | [uv](https://docs.astral.sh/uv/)，依赖集中在 `pyproject.toml` 并由 `uv.lock` 锁定 |
| 项目布局 | `src/` layout，包名 `codeagent` |
| 构建后端 | `uv_build`（产出 wheel / sdist） |
| 入口 | `codeagent = "codeagent.app.main:main"`，亦支持 `python -m codeagent` |

### 运行时依赖

| 依赖 | 用途 |
| --- | --- |
| `textual` | 交互式 TUI 后端（仅 `app/tui/adapters/textual/` 可 import） |
| `httpx` | Provider HTTP 与流式传输（自研 SSE 解析） |
| `mcp` | 官方 MCP SDK 客户端（stdio 传输，后台线程 + 独立事件循环） |
| `pydantic-settings` | 配置加载，全部配置类 `extra="ignore"` 做命名空间隔离 |
| `pyyaml` | 技能包元数据解析 |

模型供应商适配：`deepseek` / `openai` / `qwen` / `glm` / `kimi` / `minimax` 六家真实 provider + `fake` 离线假模型，每 provider 一个自包含文件（配置 + 工厂）。

### 开发与质量工具链

| 工具 | 作用 | 门禁位置 |
| --- | --- | --- |
| `pytest`（+ `asyncio` / `cov` / `timeout`） | 分标记的离线测试：`unit` `contract` `integration` `e2e` `platform` `security` `performance` `slow` `compatibility`；显式主分类优先于目录兜底 | `quality-fast`（覆盖率下限 80%）+ 跨平台矩阵 |
| `ruff check` | 正确性静态检查，当前只启用 `E9` / `F821` / `F841` 阻塞级规则 | `quality-fast` |
| `ruff format` | **唯一**格式化方案，行宽 100（不引入 Black） | `quality-fast`（`--check`） |
| `mypy` | 类型债务分层棘轮：`scripts/type_scan.py` 比对 `docs/type-baseline.json`，只降不升（当前 ai 0 / core 0 / tools 0 / session 5 / app 17，合计 22） | `quality-fast` |
| `scripts/scale_scan.py` | 全部生产层规模门禁：单文件 ≤ 300 行、单函数 ≤ 80 行 | `unit or contract` |
| OpenSpec CLI | 规格驱动开发与 `openspec validate --specs`（24 份主规格） | `quality-fast` |
| `scripts/release_check.py` | wheel/sdist 构建、内容与敏感文件检查、干净环境安装、fake provider CLI 冒烟 | `package-smoke` |
| GitHub Actions | `quality-fast` / `test-matrix`(ubuntu, windows, macos) / `package-smoke` / `performance`(非阻塞) | [`.github/workflows/ci.yml`](.github/workflows/ci.yml) |

### 分层架构与依赖方向

依赖单向流动，跨层 import 只发生在组合根。规则由 `tests/test_decoupling.py` 的 AST 扫描强制校验。

| 层 | 职责 | 禁止依赖 |
| --- | --- | --- |
| `app/` | 入口、CLI、TUI、依赖组装（`app/container.py` 为外观，实体在 `app/composition/*`） | — |
| `core/` | 领域模型、协议、ReAct 编排、`core/subagent/` 委派策略 | `config` `ai` `tools` `session` |
| `session/` | 会话状态、生命周期、JSONL 持久化、压缩、会话树 | `ai` `tools` `config` |
| `ai/` | provider、模型目录、transport、错误分类 | `app` `core` `session` `tools` |
| `tools/` | 原子工具、MCP、安全分类、子进程适配 | `core` `session` `ai` `app` |
| `resources/` | 内建 prompts 与 skills 资源 | — |

---

## 三、启动步骤

### 1. 准备前置

- Python 3.12 或更高
- 已安装 [uv](https://docs.astral.sh/uv/)

### 2. 安装依赖

```bash
git clone https://github.com/qsxcde/codeAgent.git && cd codeAgent

uv sync --group dev      # 运行时 + 开发依赖（推荐开发时用这条）
uv sync                  # 只装运行时依赖
```

### 3. 配置模型密钥

密钥只写在**固定目录** `~/.codeagent/.env`（首次启动幂等生成模板，已存在的文件不会被覆盖）。项目**有意不读取**当前目录下的 `.env`，避免在任意仓库内运行时被其 `.env` 劫持流量与密钥。

```ini
# 选择 provider: deepseek / openai / qwen / glm / kimi / minimax / fake
LLM_PROVIDER=deepseek

DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_REASONING_EFFORT=high
```

换其它 provider 只需追加对应的 `*_API_KEY` 等键——全局 `Settings` 与各 provider `Config` 各自只认自己的键。自定义模型可编辑 `~/.codeagent/models.json`，按 `id` 与内置目录 upsert 合并。

> **想先零配置跑通？** 把 `LLM_PROVIDER` 设为 `fake`（或删掉 `.env` 里的 key），即可在没有网络与密钥的情况下走完"对话 → 工具调用 → 事件流"闭环。

### 4. 启动

```bash
# 交互式 TUI
uv run codeagent --tui

# 无头单次执行
uv run codeagent --prompt "梳理登录流程的入口有哪些"

# 从 stdin 逐行读取
echo "列出本目录最大的 5 个文件" | uv run codeagent
```

### 5. 常用参数

| 参数 | 行为 |
| --- | --- |
| `--prompt <文本>` | 一次性输入；不指定则从 stdin 读取 |
| `--tui` | 启动交互式终端 |
| `--continue` / `-c` | 继续最近有活动的会话（无会话时新建） |
| `--session <id>` | 恢复指定会话继续对话（id 见 `--list-sessions`） |
| `--list-sessions` | 列出全部会话 |
| `--context` | 只读显示当前会话的上下文预算与治理诊断 |
| `--yes` | 跳过敏感操作确认、全部放行（显式承担风险）；缺省在无头模式下敏感操作一律拒绝 |

技能包管理走子命令：`uv run codeagent skill install <source>` / `update` / `remove` / `list` / `reload`（`--project` 作用于当前项目）。

TUI 内主要命令：`/provider` `/model` `/effort` `/login` `/skills` `/mcp` `/tools` `/status` `/sessions`（含 `search` / `filter` / `archive` / `archived` / `recovery` / `delete`）`/tree` `/fork` `/quit`；运行中按 `Esc` 打断，空闲按 `Esc` 退出并打印完整会话文档。

### 6. 验证与质量检查

```bash
uv run pytest -m "unit or contract" -q --strict-markers   # 快速质量集（日常首选）
uv run pytest -q                                          # 全量离线测试
uv run ruff check src tests scripts                       # 正确性静态检查
uv run ruff format src tests scripts                      # 提交前格式化
uv run ruff format --check src tests scripts              # CI 的格式化门禁
uv run python scripts/scale_scan.py                       # 规模门禁（也被 contract 测试覆盖）
uv run python scripts/type_scan.py                        # 类型债务棘轮
openspec validate --specs                                 # 规格校验
uv build                                                  # 构建 wheel / sdist
```

CI 分层与测试标记说明见 [`docs/testing.md`](docs/testing.md)。

---

## 四、项目结构

```text
codeAgent/
├── pyproject.toml / uv.lock     # 依赖、CLI 入口、ruff / mypy / pytest 配置
├── AGENTS.md                    # 本仓库开发与协作规范（当前树的权威快速参考）
├── CHANGELOG.md                 # 面向使用者的版本记录
├── docs/
│   ├── design/                  # 架构设计 / 需求分析 / 自研编排蓝图 / 会话布局
│   ├── iteration/               # v0.1 ~ v0.5 迭代记录（权威过程与验收证据）
│   ├── benchmarks/              # TUI 性能基线、边界策略与观测记录
│   ├── wiki/                    # 13 篇代码级文档（结构、分层、开发指南）
│   ├── archive/                 # 历史实施计划与时点快照（只读参考）
│   ├── type-baseline.json       # mypy 分层棘轮基线
│   └── testing.md               # 测试分层、目录结构、marker 与 CI 说明
├── openspec/                    # 24 份主规格 + 已归档变更（spec-driven）
├── scripts/                     # scale_scan / type_scan / layer_scan / release_check / benchmark_tui ...
├── src/codeagent/
│   ├── app/                     # [入口 + 组合根] 唯一允许跨层装配的地方
│   │   ├── main.py / headless.py / config.py
│   │   ├── container.py         #   装配外观（实体在 composition/*）
│   │   ├── composition/         #   model / tools / session / runtime / subagent / tui 工厂与策略
│   │   ├── context/             #   AGENTS.md 分层加载
│   │   ├── skills/              #   技能发现、提示词构建、技能包管理
│   │   ├── tasks/               #   任务模式与验证环
│   │   └── tui/                 #   状态、渲染协调器、命令、presentation、textual 适配器
│   ├── core/                    # [Agent Runtime] 纯内存、全异步、零外部依赖
│   │   ├── agent.py / observation.py
│   │   ├── contracts/           #   messages / events / hooks / errors / ports / subagent*
│   │   ├── orchestration/       #   loop / turn / batch / tool_call / AgentLoopConfig
│   │   ├── context/             #   预算、preflight、transform、诊断
│   │   ├── execution/           #   运行、操作状态、清理与结果归一化
│   │   └── subagent/            #   委派策略：policy / admission / slots
│   ├── session/                 # [会话层] 外壳 + 持久化 + 压缩 + 事件
│   │   ├── session.py / manager/ / lifecycle.py / run_coordinator.py
│   │   ├── persistence/         #   JSONL / MemoryStore / 索引 / 恢复诊断
│   │   ├── compaction/          #   压缩策略与摘要
│   │   └── navigation/          #   会话树与分支导航
│   ├── ai/                      # [模型层] providers / catalog / model / transport / errors
│   ├── tools/                   # [工具层] atomic / mcp / security / execution / shared
│   └── resources/               # [资源层] 内建 prompts 与 skills
└── tests/                       # 按行为域分包，与源码层级对应
```

---

## 五、版本状态与后续

- **已发布**：`v0.1.0` → `v0.5.0`。annotated 标签 `v0.4.0` 指向纯 v0.4 提交 `b981534`，`v0.5.0` 指向发布内容快照 `7bbc6a7`，均已推送。
- **v0.4** 完成 V4-01～V4-38：Runtime 可靠性、上下文治理、TUI / Session 交互、生命周期 Hook、工具与 Provider 稳定性。
- **v0.5** 完成 V5-00～V5-10：串行只读 Subagent 委派、父子事件诊断、有界运行记录与 TUI / headless 可观察性；领域规则已下沉 `core/subagent/`。
- **工程护栏**：格式化与类型棘轮门禁已接入 CI，规模门禁覆盖全部生产层。
- **v0.6 硬化（未发版）**：安全分类语义化（包装器/命令替换/误杀）、只读搜索工具文件边界、越界警告送达模型、bash 合并输出统一上限、中英混合 token 估算、会话索引追加增量更新。详见 [`docs/design/roadmap-v0.6.md`](docs/design/roadmap-v0.6.md)。
- **后续评估**：执行控制（steer 接入 UI、后台作业、事件流导出）、沙箱与程序化工具编排、并行子 Agent 与可写隔离、跨进程恢复与自动重试、长期记忆、TUI schema v2 正式基线替换。

## 参考

- [earendil-works/pi](https://github.com/earendil-works/pi) — Pi Agent SDK（三层协作 / 双层 loop / 事件驱动 / 会话即状态）
- [learning-pi-agent](https://github.com/yamsfeer/learning-pi-agent) — 架构深度笔记
- [how-pi-agent-works](https://github.com/myxiaoao/how-pi-agent-works) — 中文教学实现
