# 01 · 项目总览

## 1. 定位

`tenon` 是一个**本地、单用户、可离线验证**的编程 Agent。它把"编排、模型适配、工具实现、持久化"四件事彻底拆开：

- 核心层是纯内存、全异步、零外部依赖的可测试运行时；
- 模型 / 工具 / 存储全部通过**端口（Protocol）**注入，实现在组合根装配；
- 运行过程以**事件流**对外暴露，CLI / TUI / 测试 / CI 都能订阅，而非只拿最终返回值。

提供两种形态：交互式终端（TUI，`--tui`）与无头 CLI（`--prompt` / stdin 逐行）。

设计参考 [earendil-works/pi](https://github.com/earendil-works/pi) 的"三层协作 / 双层 loop / 事件驱动 / 会话即状态"思想。2026-08-14 起编排自研（ReAct 主循环 + 消息归约 + JSONL 树形会话），依赖中**无 langchain / langgraph**。

## 2. 四条设计目标

| 目标 | 含义 |
| --- | --- |
| **可演进** | 从单工具调用 Agent 平滑演进到多 Agent（v0.5 已交付串行只读委派）、多会话、平台部署 |
| **可替换** | 换模型供应商、换工具集、换存储后端都不触碰编排代码 |
| **可感知** | 会话过程以事件流暴露；TUI / CLI / 测试 / CI 均可订阅 |
| **可测试** | 核心层零网络、零密钥可运行；注入 `FakeClient` 即可离线跑通全量测试 |

## 3. 当前能力（v0.5）

| 能力 | 说明 |
| --- | --- |
| 交互式 TUI | 多行 composer（Enter 提交 / Shift+Enter 换行）、流式正文、可展开工具结果、edit/write 红绿差异、状态栏（model/effort/cwd）、Markdown 渲染、Esc 打断、斜杠命令 + 模糊补全 |
| Headless CLI | `--prompt` 一次性 / stdin 逐行；事件聚合输出最终回复；敏感操作默认 fail closed |
| 自研编排 | `core/agent.py` 有状态外壳 + `core/orchestration/loop.py` ReAct 主循环（模型 → 工具 → 继续/结束） |
| 11 个内建工具 | `read` / `write` / `edit` / `bash` / `grep` / `find` / `ls` / `skill` / `web_fetch` / `web_search` / `todo`；无状态 `AtomicTool` + `FsOps` 抽象缝；`grep`/`find` 把 `rg`/`fd` 当可选加速，失败回退纯 Python；web 工具网络经注入、出站进确认环 |
| MCP 客户端 | 按 `~/.tenon/mcp.json` 接入 `tools/list` / `tools/call`；工具名 `mcp__<server>__<tool>` 命名空间化并实施分组预算 |
| Skills | `SKILL.md` 三源发现（内建 / 个人 / 项目）+ 渐进式披露（描述入 system prompt，正文经 `skill` 工具按需取）；`tenon skill` 子命令管理技能包 |
| 会话层 | JSONL 树形持久化；恢复 / 切换 / 分叉 / 归档 / 删除 / 压缩；标题、搜索、筛选、恢复诊断；成功轮次才落盘；`abort` / `steer` / `followup` |
| Subagent 委派 | `delegate` 默认串行（`subagent_max_concurrency>1` 时启用有界并发）；profile `explore` / `review` 只读、`implement` 受限可写（禁止 `delegate`）；预算与输出有界；深度固定 1；父级收回有界摘要与结构化证据 |
| 安全确认环 | 执行前 `ApprovalPolicy` 三档 deny / ask / allow（危险命令黑名单 + shlex 语义检测 + 文件访问边界） |
| 用量透明 | 归一累计输入 / 输出 / 推理 / 缓存命中 token；`/status` 与 CLI 可见（**不做费用估算**） |
| 上下文治理 | token 预算、preflight、自动压缩与恢复回归；`--context` 只读输出治理诊断（含缓存命中率与冷/暖诊断码） |
| 运行期安全 | 三档 bash 沙箱（默认 `danger-full-access`，受限策略无后端 fail-closed）；写前 checkpoint + `tenon undo` 逐级回退 |
| 离线评测 | `python -m evals` 用 fake 模型驱动真实 Agent 循环，覆盖工具流/未知工具/审批阻断/改参；纳入 `contract` 门禁 |

**明确不做**：费用估算、Web / HTTP 事件订阅、轻量记忆、自动化任务调度、跨进程恢复与自动重试、`tester` profile 与子 Agent 命令执行；**Web UI 暂不规划**（TUI + headless CLI 为唯一交付形态）。已交付但需注意边界的：插件系统（v1 仅贡献工具、同进程执行）、Subagent 有界并发（默认串行）、`implement` 受限可写 profile（禁止 `delegate`/MCP）。

## 4. 技术栈

### 运行时依赖

| 依赖 | 用途 | 使用范围约束 |
| --- | --- | --- |
| `textual` | TUI 后端 | 仅 `app/tui/adapters/textual/` 可 import |
| `httpx` | Provider HTTP 与流式传输（自研 SSE 解析） | `ai/transport/` |
| `mcp` | 官方 MCP SDK（stdio 传输） | `tools/mcp/client.py` |
| `pydantic-settings` | 配置加载；所有配置类 `extra="ignore"` 做命名空间隔离 | `app/config.py` + `ai/providers/*` |
| `pyyaml` | 技能包 frontmatter / manifest 解析 | `app/skills/` |

模型供应商：`deepseek` / `openai` / `qwen` / `glm` / `kimi` / `minimax` 六家 + 离线 `fake`，每个 provider 一个自包含文件（配置 + 工厂）。

### 开发与质量工具链

| 工具 | 作用 | 门禁 |
| --- | --- | --- |
| `pytest`（asyncio/cov/timeout） | 分 marker 的离线测试 | CI `quality-fast` + 跨平台矩阵 |
| `ruff check` | 正确性静态检查（当前仅 `E9` / `F821` / `F841`） | `quality-fast` |
| `ruff format` | 唯一格式化方案，行宽 100 | `quality-fast --check` |
| `mypy` + `scripts/type_scan.py` | 分层类型债务棘轮（对照 `docs/type-baseline.json`） | `quality-fast` |
| `scripts/scale_scan.py` | 规模门禁：单文件 ≤ 300 行、单函数 ≤ 80 行（全部生产层） | `unit or contract` |
| OpenSpec CLI | 规格驱动开发（25 份主规格） | `quality-fast` |
| `scripts/release_check.py` | wheel/sdist 构建、资源/敏感文件检查、干净安装、fake provider 冒烟 | `package-smoke` |

## 5. 版本与迭代状态

- **已发布**：`v0.1.0` → `v0.7.0`（annotated 标签 `v0.4.0` → `b981534`，`v0.5.0` → `7bbc6a7`；`v0.7.0` 对应本次发布提交）。
- **v0.4**：V4-01～V4-38，Runtime 可靠性、上下文治理、TUI/Session 交互、生命周期 Hook、工具与 Provider 稳定性。
- **v0.5**：V5-00～V5-10，串行只读 Subagent 委派、父子事件诊断、有界运行记录与 TUI/headless 可观察性；领域规则下沉 `core/subagent/`。
- **基线**：`1870 passed`（无 skipped），快速质量集 `1718 passed`，OpenSpec 25/25（2026-10-24，macOS / Python 3.12）。此前 v0.5.0 发布记录为 `1695 passed / 3 skipped` / 84.40% / 1525 passed（2026-10-10，Windows / Python 3.12）；覆盖率基线以 CI `quality-fast` 实测为准。
- **v0.6**：三项正确性硬化（安全分类语义化、合并输出上限与 token 估算、会话索引增量）。
- **v0.7**：工具注册表数据化、审批封闭枚举、web/todo 工具、工具执行瀑布管线、扩展插件目录、Subagent 有界并发与 `implement` 可写 profile、API 形状注册表、三档 bash 沙箱、写前 checkpoint/`undo`、缓存诊断与离线评测。
- **后续评估**：程序化工具编排（`run_code` 形态）、执行控制（steer 接入 UI、后台作业、事件流导出）、跨进程恢复与自动重试、长期记忆、TUI schema v2 正式基线替换；Web UI 暂不规划。

## 6. 顶层目录结构

```text
tenon/
├── pyproject.toml / uv.lock     # 依赖、CLI 入口、ruff / mypy / pytest 配置
├── AGENTS.md                    # 仓库开发与协作规范（权威快速参考）
├── CHANGELOG.md                 # 面向使用者的版本记录
├── docs/
│   ├── design/                  # 架构 / 需求 / 自研编排蓝图 / 会话布局
│   ├── iteration/               # v0.1 ~ v0.7 迭代记录（权威过程与验收证据）
│   ├── benchmarks/              # TUI 性能基线与观测记录
│   ├── wiki/                    # ← 本文档集
│   ├── archive/                 # 历史实施计划与时点快照（只读参考）
│   ├── type-baseline.json       # mypy 分层棘轮基线
│   └── testing.md               # 测试分层、目录结构、marker 与命令
├── openspec/                    # 25 份主规格 + 已归档变更
├── evals/                       # 离线评测框架（python -m evals）
├── scripts/                     # scale_scan / type_scan / layer_scan / release_check / benchmark_tui ...
├── src/tenon/
│   ├── app/                     # 入口 + 组合根（唯一跨层装配点）
│   ├── core/                    # 纯内存 Agent Runtime
│   ├── session/                 # 会话状态、持久化、压缩、导航
│   ├── ai/                      # provider、catalog、transport（含 API 形状）、错误分类
│   ├── tools/                   # 原子工具、MCP、插件、安全、执行（含沙箱）、共享设施
│   └── resources/               # 内建 prompts 与 skills
└── tests/                       # 按行为域分包，与源码层级对应
```

分层职责一句话版：

| 层 | 一句话职责 | 禁止依赖 |
| --- | --- | --- |
| `app/` | 入口、CLI、TUI、依赖组装 | — |
| `core/` | 领域模型、协议、ReAct 编排、Subagent 策略 | `config` `ai` `tools` `session` |
| `session/` | 会话状态、生命周期、JSONL 持久化、压缩、会话树 | `ai` `tools` `config` |
| `ai/` | provider、模型目录、transport、错误分类 | `app` `core` `session` `tools` |
| `tools/` | 原子工具、MCP、安全分类、子进程适配 | `core` `session` `ai` `app` |
| `resources/` | 内建 prompts / skills 资源 | — |

下一章：[整体架构](../design/architecture.md) · 运行方式见 [03](03-runtime-flow.md)。