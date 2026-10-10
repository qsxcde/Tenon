# Changelog

本文件记录面向使用者的版本变化。完整的任务拆分、设计决策与验收证据见
[`docs/iteration/`](docs/iteration/) 下的迭代记录。

## [Unreleased]

暂无已归入下一版本的变更。

## [0.5.0] - 2026-10-10

v0.5.0 完成 V5-00～V5-10，把单 Agent Runtime 扩展为可委派、可治理、可观察的**串行只读 Subagent** 协作形态。功能实现合入于 2026-09-02～09-03，本次补齐版本元数据与发布记录。

### Added

- `delegate` 工具与串行 Subagent 运行时：父 Agent 可把只读子任务委派给独立子 Agent，子 Agent 拥有独立上下文、事件总线、运行身份和资源关闭边界；单次父运行最多接受 4 个子任务，委派深度固定为 `max_depth=1`，子 Agent 不再注入 `delegate`。
- 只读 Subagent Profile registry：`explore` 与 `review` 在同一 registry 中定义正式名称、角色指令、输出指导和只读工具白名单（`read` / `grep` / `find` / `ls` / `skill`），`delegate` schema、runner 校验与子 Session 装配复用同一入口，默认 profile 为 `explore`；`review` 在缺少明确范围或证据时要求报告范围不足，不把父历史当作已审查事实。
- 显式上下文传递与隔离：子 Session 只接收任务及显式选择的事实、约束和输出要求，不继承父历史；非法 profile、未知 context 字段、空值和超限输入在创建子 Session、占用配额或调用模型之前拒绝，context 始终作为数据而不能升级工具权限。
- 有界预算与取消治理：`delegate` 接受有界 budget，缺省 `max_turns=8`、`max_tool_calls=32`、`timeout_seconds=120`、`max_output_chars=8000`（硬上限 `16/64/300/16000`）；墙钟边界覆盖排队、启动、模型/工具执行和确认等待，区分 `parent_cancelled`、`timeout` 与 `budget_exceeded`，无法确认资源停止时保留 `cleanup_uncertain`。
- 结构化结果与证据回传：新增不可变 `SubagentFinding`、`SubagentEvidence`、`SubagentUsage` 和 `SubagentArtifact`，单次结果最多保留 32 条带来源、定位和短摘录的证据及至多一个 artifact 引用；超限、重复 evidence id 和悬空引用由 `invalid_result` 拒绝，自然语言摘要不会被猜测为 finding，父级不接收完整子 transcript。
- 父子事件与运行诊断：新增 `subagent_queued / subagent_started / subagent_progress / subagent_finished`，事件携带 `delegation_id`、父/子运行 ID、各自序列与深度，终态只发布一次；迟到事件、观察者异常和清理不确定均有界记录。
- 父会话有界 `subagent` 运行记录：通过唯一父级事件观察点异步有序追加状态、阶段、终态摘要、reason code 与清理事实，写入失败只形成有限诊断；进程重启时非终态记录折叠为 `abandoned/process_restarted`，不创建子 Session、不产生幽灵运行、不回写原 JSONL。
- TUI 与 headless 可观察性：TUI 使用独立且默认折叠的 `SubagentBlock` 展示状态、阶段、耗时、child run、摘要、错误码、清理状态和结果统计，状态栏在固定槽位聚合运行/等待/失败数量；headless 输出稳定有界的 `子Agent状态:` 行，两者均不复制 child transcript 或无界 payload。
- Subagent 主规格：`subagent-contract`、`subagent-runtime`、`subagent-observability` 和 `subagent-run-records`。

### Changed

- Profile 规范化（V5-10）：`read_only` 不再是 `delegate` 的合法输入并在启动前拒绝且提示迁移，历史 JSONL 中的旧 profile 文本仍可读取和展示且不回写。
- 结构化 Subagent 事件不再嵌套为无界 `tool_progress` payload；子事件跨 child run 转发要求正确的 `parent_run_id`，只分配 `parent_sequence` 而不推进父 `RunPhase`。
- 父级 Subagent 访问门面拆分至 `session/subagent.py`，JSONL 单条 entry 分类从恢复扫描中抽离，使生产模块重新满足 300 行文件与 80 行函数约束。

### Deferred

- 多 Agent 并行协作、子 Agent 写权限与工作区隔离、跨进程自动重试与完整子 transcript 恢复、长期记忆与自动任务调度均不属于 v0.5 范围，见 [`docs/iteration/v0.5.md`](docs/iteration/v0.5.md) §8。

### Verification

- 当前 Windows / Python 3.12 全量离线测试为 `1673 passed，3 skipped`（1676 collected）；快速质量集为 `1503 passed，3 skipped，170 deselected`，覆盖率 `84.29%`（15065/17873 statements，CI 硬下限 77.9%）；跨边界集合（integration / e2e / platform / compatibility）为 `212 passed`。
- `uv run ruff check src tests scripts` 通过；`git diff --check` 通过。
- `openspec validate --specs` 为 **24/24**，`openspec/changes/` 无未归档变更。
- 包版本一致性校验通过：`pyproject.toml` 与 `codeagent.__version__` 均为 `0.5.0`。
- release check（`scripts/release_check.py`）以 `0.5.0` 通过：wheel/sdist 构建、内建资源与敏感文件检查、干净环境安装和 fake provider CLI 冒烟。

## [0.4.0] - 2026-09-01

v0.4.0 完成 V4-01～V4-38，重点将单 Agent Runtime 收敛为可长期使用、可诊断和可扩展的本地运行时。

### Added

- Runtime 生命周期、取消、资源清理和最终化契约，以及可观测 Hook 和 Hook 异常隔离。
- 上下文预算预检、自动压缩、恢复回归、工具结果治理和完整工具状态诊断。
- TUI 长会话渲染、提交即时反馈、状态栏诊断和交互响应性回归。
- 会话标题、搜索筛选、归档删除、恢复诊断和列表索引性能能力。
- 工具能力探测、资源保护、外部检索器 fallback、Provider 错误分类、安全模型重试和模型能力诊断。

### Engineering updates

- 测试按行为域拆分并集中公共契约；v0.4 时点全量验证为 `1532 passed`（2026-08-30，macOS），快速质量集为 `1391 passed，141 deselected`，覆盖率为 `83.61%`。
- CI 增加快速质量检查、Ubuntu/Windows/macOS 离线测试矩阵、release check 和 TUI 性能 artifact。
- 增加 pytest-cov、Ruff 正确性检查、安装后 fake provider CLI 验证、产物完整性报告和性能相对变化报告。
- `openspec validate --specs` 当时为 `20/20`；release check 已验证 wheel/sdist、版本、资源、干净安装和 fake provider CLI。
- 覆盖率硬下限固化为 77.9%；仓库内 TUI schema v1 JSON 作为历史基线保留，Linux/Python 3.12 的 schema v2 候选由 CI 生成并经人工复核，当前继续告警而不阻断普通 PR。

### Verification

- v0.4 发布时的 macOS / Python 3.12 全量离线测试为 `1532 passed`；快速质量集为 `1391 passed，141 deselected`，覆盖率为 `83.61%`。
- 包版本一致性校验通过：`pyproject.toml`、`codeagent.__version__` 和构建产物均为 `0.4.0`。
- release check 已通过 wheel/sdist 构建、资源与敏感文件检查、干净环境安装和 fake provider CLI 冒烟。

## [0.3.0] - 2026-08-22

### Added

- Skills 技能系统：内建、个人、项目三源发现与同名遮蔽诊断
- `skill` 工具与 TUI `/skills` 手动加载
- MCP 客户端最小协议面：`tools/list`、`tools/call`
- MCP 工具命名空间化、分组预算与权限规则
- 输入、输出、推理和缓存命中 token 的归一、落库与展示
- 会话树数据视图、TUI `/tree` 导航和树形 `/sessions list`
- TUI `/mcp`、`/quit` 等命令支持

### Changed

- 会话恢复入口统一为 `/sessions`，支持最近会话继续和交互式切换
- v0.3 以离线可测为验收基线，避免网络和密钥依赖

### Deferred

- 费用估算：当前只统计 token，不维护单价和费用模型
- Web/HTTP API：待出现真实的平台或多端消费者后重估
- 轻量记忆、插件系统、多智能体和自动化任务：保留为远期方向

### Verification

- `uv run pytest -q`: 666 collected, 665 passed, 1 skipped（Windows 无符号链接权限；无失败）
- `openspec validate --specs`: 9 passed
- `git diff --check`: passed

## [0.2.0] - 2026-08-15

### Added

- 自研 ReAct 编排循环和消息归约，移除 LangGraph/LangChain 编排依赖
- JSONL 树形会话持久化、恢复、切换、分叉和上下文压缩
- bash/write 敏感操作确认环与文件访问边界控制
- 全局、项目和子目录级 `AGENTS.md` 指令加载
- TUI 斜杠命令、模糊补全、选择器、Markdown 渲染和滚动交互

### Changed

- `/fork` 取代 `/undo`，以分支会话实现可回退语义
- 事件流继续作为 CLI、TUI 和测试之间的统一运行时接口

## [0.1.0] - 2026-08-14

### Added

- Headless CLI 与交互式 TUI
- 多模型 provider 配置和离线 `fake` provider
- `read`、`write`、`edit`、`bash` 等原子工具
- 异步 ReAct 对话、工具调用和事件流订阅
- 危险命令黑名单、Windows bash 探测和离线测试基线

[Unreleased]: https://github.com/qsxcde/codeAgent/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/qsxcde/codeAgent/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/qsxcde/codeAgent/compare/v0.3.0...v0.4.0
