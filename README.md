# codeagent

> 本地、单用户、可离线验证的编程 Agent。自研 ReAct 编排，端口-适配器（hexagonal）分层，提供交互式终端（TUI）与无头 CLI 两种形态。

[![CI](https://github.com/qsxcde/codeAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/qsxcde/codeAgent/actions/workflows/ci.yml)
[![Release](https://img.shields.io/badge/release-v0.7.0-blue)](https://github.com/qsxcde/codeAgent/releases/tag/v0.7.0)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

发布说明：[v0.7.0](docs/releases/v0.7.0.md) · 升级指南：[v0.7](docs/releases/v0.7-upgrade.md) · [架构设计](docs/design/architecture.md) · [测试与 CI](docs/testing.md) · [变更日志](CHANGELOG.md)

## 目录

- [项目简介](#项目简介)
- [核心特性](#核心特性)
- [快速开始](#快速开始)
- [使用方式](#使用方式)
- [配置参考](#配置参考)
- [架构与项目结构](#架构与项目结构)
- [开发与测试](#开发与测试)
- [版本与路线图](#版本与路线图)
- [贡献](#贡献)
- [许可证](#许可证)
- [参考](#参考)

## 项目简介

多数 Agent 框架把编排、模型适配、工具实现和持久化揉在同一层：换模型要动业务代码、加工具要动核心循环、出问题只能看最终返回值。`codeagent` 把这四件事拆开——核心层是纯内存、可离线测试的运行时，模型/工具/存储全部通过端口注入，运行过程以事件流对外暴露，任何一层都能替换而不牵动其它层。

设计参考 [earendil-works/pi](https://github.com/earendil-works/pi) 的“三层协作 / 双层 loop / 事件驱动 / 会话即状态”思想，自 2026-08-14 起不再依赖 langgraph / langchain。

| 设计目标 | 含义 |
| --- | --- |
| **可演进** | 从单工具调用 Agent 平滑演进到多 Agent、多会话与平台部署 |
| **可替换** | 换模型供应商、换工具集、换存储后端都不触碰编排代码 |
| **可感知** | 会话过程以事件流暴露，CLI / TUI / 测试 / CI 都能订阅 |
| **可测试** | 核心层零网络、零密钥即可运行，注入 `FakeClient` 即可跑通全量测试 |

当前状态：`v0.7.0` · Python 3.12+ · 全量离线测试 **1870 passed** · 快速质量集 **1718 passed** · OpenSpec **25/25**。

## 核心特性

- **双形态交互**：`--tui` 提供流式正文、可展开工具结果、edit/write 红绿差异、Markdown 渲染、模糊补全与斜杠命令；`--prompt` / stdin 提供无头单次执行。
- **自研 ReAct 编排**：`core/agent.py` 的纯内存 `Agent` 外壳加 `core/orchestration/loop.py` 的“模型 → 工具 → 继续/结束”主循环，不依赖第三方编排框架。
- **11 个内建工具**：`read` `write` `edit` `bash` `grep` `find` `ls` `skill` `web_fetch` `web_search` `todo`。`rg` / `fd` 仅作可选加速，缺失时回退纯 Python；web 工具网络经注入，出站进入确认环。
- **可扩展工具层**：声明式 `ToolSpec` / `ToolRegistry`；MCP 客户端（`mcp__<server>__<tool>`）；扩展插件 v1（`ext__<id>__<tool>`）；Skills 三源发现与渐进式披露。
- **会话层**：JSONL 树形持久化，支持恢复、切换、分叉、归档、删除与压缩；成功轮次才落盘，失败/取消内存回滚；`abort` / `steer` / `followup`。
- **Subagent 委派**：`delegate` 默认串行，配置 `SUBAGENT_MAX_CONCURRENCY>1` 后启用有界并发；`explore` / `review` 只读、`implement` 受限可写，预算与输出有界、深度固定为 1。
- **安全与回退**：审批结果封闭枚举且 fail-closed；三档 bash 沙箱（`read-only` / `workspace-write` / `danger-full-access`）；`write` / `edit` 写前快照，`codeagent undo` 逐级回退。
- **可观测与治理**：token 用量归一见 `/status` 与 CLI；`--context` 输出预算、压缩与缓存命中诊断；离线评测 `python -m evals` 纳入 `contract` 门禁。

## 快速开始

### 环境要求

- Python 3.12 或更高
- [uv](https://docs.astral.sh/uv/)

### 安装

```bash
git clone https://github.com/qsxcde/codeAgent.git
cd codeAgent

uv sync --group dev   # 运行时 + 开发依赖
uv sync               # 仅运行时依赖
```

### 配置模型

密钥只写在固定目录 `~/.codeagent/.env`（首次启动幂等生成模板，已有文件不会被覆盖）。项目**有意不读取**当前目录下的 `.env`，避免在任意仓库运行时被其 `.env` 劫持流量与密钥。

```ini
LLM_PROVIDER=deepseek

DEEPSEEK_API_KEY=sk-你的key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
DEEPSEEK_REASONING_EFFORT=high
```

换其它 provider 只需追加对应的 `*_API_KEY` 等键。自定义模型可编辑 `~/.codeagent/models.json`，按 `id` 与内置目录合并。

> 想零配置跑通？把 `LLM_PROVIDER` 设为 `fake`，即可在没有网络与密钥的情况下走完“对话 → 工具调用 → 事件流”闭环。

### 运行

```bash
uv run codeagent --tui                                  # 交互式 TUI
uv run codeagent --prompt "梳理登录流程的入口有哪些"     # 无头单次执行
echo "列出本目录最大的 5 个文件" | uv run codeagent      # 从 stdin 逐行读取
```

## 使用方式

### 常用参数

| 参数 | 行为 |
| --- | --- |
| `--prompt <文本>` | 一次性输入；不指定则从 stdin 读取 |
| `--tui` | 启动交互式终端 |
| `--continue` / `-c` | 继续最近有活动的会话（无会话时新建） |
| `--session <id>` | 恢复指定会话继续对话（id 见 `--list-sessions`） |
| `--list-sessions` | 列出全部会话 |
| `--context` | 只读显示上下文预算、治理诊断与缓存命中率 |
| `--yes` | 跳过敏感操作确认、全部放行（显式承担风险）；无头模式缺省一律拒绝 |

### 技能包与快照

```bash
uv run codeagent skill install <source>   # 另有 update / remove / list / reload；--project 作用于当前项目
uv run codeagent undo --list              # 查看写前快照
uv run codeagent undo --dry-run           # 预览将恢复的文件
uv run codeagent undo                     # LIFO 逐级恢复最近一次 write/edit 之前的文件
```

### TUI 命令

`/provider` `/model` `/effort` `/login` `/skills` `/mcp` `/tools` `/status` `/sessions`（含 `search` / `filter` / `archive` / `archived` / `recovery` / `delete`）`/tree` `/fork` `/quit`。运行中按 `Esc` 打断，空闲按 `Esc` 退出并打印完整会话文档。

## 配置参考

配置统一来自 `~/.codeagent/.env` 或同名环境变量（无前缀，全大写）。

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_PROVIDER` | `deepseek` | `deepseek` / `openai` / `qwen` / `glm` / `kimi` / `minimax` / `fake` |
| `SANDBOX_POLICY` | `danger-full-access` | bash 沙箱：`read-only` / `workspace-write` / `danger-full-access` |
| `SUBAGENT_MAX_CONCURRENCY` | `1` | `1` 串行；大于 1 启用有界并发 |
| `CHECKPOINTS_ENABLED` | `true` | `write` / `edit` 写前是否记录快照 |
| `TOOL_MAX_CONCURRENCY` | `4` | 同轮工具调用的并发上限 |
| `TOOL_TIMEOUT` / `TOOL_MAX_TIMEOUT` | 无 / `600` | 单次工具超时与硬上限（秒） |

完整迁移与回滚说明见 [v0.7 升级指南](docs/releases/v0.7-upgrade.md)。

## 架构与项目结构

依赖单向流动，跨层 import 只允许发生在组合根，规则由 `tests/test_decoupling.py` 的 AST 扫描强制校验。

| 层 | 职责 | 禁止依赖 |
| --- | --- | --- |
| `app/` | 入口、CLI、TUI、依赖组装（`app/composition/*`） | — |
| `core/` | 领域模型、协议、ReAct 编排、Subagent 策略 | `config` `ai` `tools` `session` |
| `session/` | 会话状态、JSONL 持久化、压缩、会话树 | `ai` `tools` `config` |
| `ai/` | provider、模型目录、transport、错误分类 | `app` `core` `session` `tools` |
| `tools/` | 原子工具、MCP、插件、安全分类、子进程与沙箱 | `core` `session` `ai` `app` |
| `resources/` | 内建 prompts 与 skills | — |

```text
codeAgent/
├── src/codeagent/
│   ├── app/          # 入口、组合根、composition、TUI、skills、context
│   ├── core/         # Agent、contracts、orchestration、context、execution、subagent
│   ├── session/      # 会话生命周期、persistence、compaction、navigation
│   ├── ai/           # providers、catalog、model、transport、errors
│   ├── tools/        # atomic、mcp、plugins、security、execution、shared
│   └── resources/    # 内建 prompts 与 skills
├── tests/            # 按行为域分包，与源码层级对应
├── evals/            # 离线评测框架（python -m evals）
├── scripts/          # scale_scan / type_scan / release_check / benchmark_tui ...
├── openspec/         # 25 份主规格与已归档变更（spec-driven）
├── docs/             # 架构、迭代记录、wiki、基准与发布文档
├── AGENTS.md         # 开发与协作规范
└── CHANGELOG.md      # 面向使用者的版本记录
```

更多设计细节见 [架构设计](docs/design/architecture.md)、[需求基线](docs/design/requirements-analysis.md) 与 [代码级 wiki](docs/wiki/README.md)。

## 开发与测试

```bash
uv run pytest -m "unit or contract" -q --strict-markers   # 快速质量集（日常首选）
uv run pytest -q                                          # 全量离线测试
uv run python -m evals                                    # 离线端到端评测
uv run ruff check src tests evals scripts                 # 正确性静态检查
uv run ruff format --check src tests evals scripts        # 格式化门禁
uv run python scripts/type_scan.py                        # 类型债务棘轮
uv run python scripts/scale_scan.py                       # 规模门禁（文件 ≤300 行 / 函数 ≤80 行）
openspec validate --specs                                 # 规格校验
uv build                                                  # 构建 wheel / sdist
```

CI 由 `quality-fast`（Ruff、快速测试、覆盖率下限 80%、类型棘轮、OpenSpec）、三平台离线测试矩阵、`package-smoke`（构建、干净安装、fake provider CLI 冒烟）与非阻塞性能报告组成。测试标记与分层说明见 [docs/testing.md](docs/testing.md)。

## 版本与路线图

- **已发布**：`v0.1.0` → `v0.7.0`，当前 [v0.7.0 发布说明](docs/releases/v0.7.0.md)。
- **v0.7.0**：工具注册表数据化、审批结果封闭枚举、`web_fetch` / `web_search` / `todo`、工具执行瀑布管线、扩展插件目录、Subagent 有界并发与 `implement` profile、API 形状注册表、三档 bash 沙箱、写前 checkpoint + `undo`、缓存诊断、离线评测框架；同时包含 v0.6 正确性硬化。
- **后续评估**：执行控制（steer 接入 UI、后台作业、事件流导出）、程序化工具编排、跨进程恢复与自动重试、长期记忆、TUI schema v2 正式基线。Web UI 暂不规划。
- **明确不做**：费用估算、Web/HTTP 事件订阅、轻量记忆、自动化任务调度、`tester` profile。

按版本的权威过程记录见 [docs/iteration/](docs/iteration/)。

## 贡献

欢迎提交 Issue 与 Pull Request。开发环境、提交规范、必须通过的门禁与 PR 要求见 [CONTRIBUTING.md](CONTRIBUTING.md)；仓库内的分层约束与编码规范见 [AGENTS.md](AGENTS.md)。

## 许可证

本项目采用 [MIT License](LICENSE)，Copyright (c) 2026 qsxcde。

## 参考

- [earendil-works/pi](https://github.com/earendil-works/pi) — Pi Agent SDK（三层协作 / 双层 loop / 事件驱动 / 会话即状态）
- [learning-pi-agent](https://github.com/yamsfeer/learning-pi-agent) — 架构深度笔记
- [how-pi-agent-works](https://github.com/myxiaoao/how-pi-agent-works) — 中文教学实现
