# codeagent Code Wiki

> 面向开发者的代码级 Wiki。描述**当前代码树**（v0.5.0，Python 3.12）的结构、职责与运行方式。
> 架构决策背景见 [`../design/architecture.md`](../design/architecture.md) 与 [`../iteration/`](../iteration/)；本 Wiki 侧重"代码在哪里、由谁负责、怎么跑通"。

## 文档地图

| # | 文档 | 内容 | 主要读者 |
| --- | --- | --- | --- |
| 01 | [项目总览](01-overview.md) | 定位、设计目标、能力与不做、技术栈、版本状态、目录结构 | 所有人 |
| 02 | [整体架构](02-architecture.md) | 两条正交轴、双层 loop、五层边界、核心契约、事件驱动、组合根 | 所有人 |
| 03 | [运行方式与端到端数据流](03-runtime-flow.md) | 安装配置、CLI/TUI 启动、一次对话的完整生命周期、干预与会话管理 | 使用者 / 新成员 |
| 04 | [core 层：Agent Runtime](04-core-layer.md) | 消息模型、端口、ReAct 循环、上下文治理、执行运行时、Subagent 策略 | 核心开发者 |
| 05 | [session 层：会话与持久化](05-session-layer.md) | AgentSession、SessionManager、JSONL 格式、压缩、状态机、事件总线 | 核心开发者 |
| 06 | [ai 层：模型基础设施](06-ai-layer.md) | provider、catalog、transport/SSE、错误分类、fake 模型 | 模型接入开发者 |
| 07 | [tools 层：工具与安全](07-tools-layer.md) | AtomicTool、8 个内建工具、安全分类器、MCP、进程执行、共享设施 | 工具开发者 |
| 08 | [app 层：入口与组合根](08-app-layer.md) | CLI/headless、config、composition 装配、skills、tasks、AGENTS.md | 应用层开发者 |
| 09 | [TUI 层详解](09-tui-layer.md) | 端口-适配器、状态归约、渲染调度、命令体系、展示块 | TUI 开发者 |
| 10 | [依赖关系图](10-dependency-map.md) | 分层 import 矩阵、跨层允许点、外部依赖、资源所有权 | 所有人 |
| 11 | [开发指南与质量门禁](11-development-guide.md) | 测试分层、CI、扩展 recipes（新工具/provider/命令）、编码规范 | 贡献者 |
| 12 | [术语与速查表](12-glossary.md) | 术语表、关键常量、文件位置速查 | 所有人 |

## 推荐阅读路径

- **第一次接触项目**：01 → 02 → 03，然后按需进入分层文档。
- **想改核心编排**：02 → 04 → 05 → 10（先看依赖规则再动手）。
- **想加模型供应商**：06 → 08（组合根装配）→ 10。
- **想加工具**：07 → 08 → 11 的扩展 recipe。
- **想改 TUI**：09 → 10（Textual 只能出现在 `app/tui/adapters/textual/`）。

## 快速事实

| 项 | 值 |
| --- | --- |
| 包名 / 版本 | `codeagent` / `0.5.0` |
| 语言 / 构建 | Python 3.12+ / `uv_build`（`uv` 管理依赖与虚拟环境） |
| CLI 入口 | `codeagent = "codeagent.app.main:main"`（亦支持 `python -m codeagent`） |
| 分层 | `app` / `core` / `session` / `ai` / `tools` / `resources`，依赖单向流动 |
| 编排 | 自研 ReAct（`core/orchestration/loop.py`），无 langchain/langgraph |
| 持久化 | `~/.codeagent/sessions/<id>.jsonl`（JSONL 树形，格式版本 1） |
| 测试基线 | `1711 passed`（无 skipped），覆盖率 86.35%，OpenSpec 24/24（2026-10-18，macOS） |

## 维护约定

- 本 Wiki 描述"当前树"；行为或公共接口变化时同步更新对应章节与 [`AGENTS.md`](../../AGENTS.md)。
- 文档中的代码位置一律写**模块路径**（如 `src/codeagent/core/agent.py`），不写行号，避免漂移。
- 与 `docs/design/` 的分工：设计文档记录"为什么这样决策"，本 Wiki 记录"现在是什么样、怎么用"。