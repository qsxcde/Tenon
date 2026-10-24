# Changelog

本文件记录面向使用者的版本变化。完整的任务拆分、设计决策与验收证据见
[`docs/iteration/`](docs/iteration/) 下的迭代记录。

## [Unreleased]

### Added

- **TUI 维护类命令**：新增 `/undo`（查看/恢复写前快照）、`/export <path>`（导出当前会话文档）、`/subagents`（查看并发上限与活跃委派，`cancel <id>` 终止单个委派）、`/context-window`（读取或写入 `models.json` 的 `contextWindow` 并热切换）；`/mcp reload` 免重启重建 MCP 与工具运行时。这些高权限动作经 `TuiAdminPort` 由组合根实现，视图层不直接触碰快照存储与模型目录。
- **TUI 启动恢复**：`codeagent --tui -c` 恢复最近有活动的会话（此前 TUI 启动固定新建）。

### Fixed

- **完整命令名的斜杠命令在补全浮层下无法提交**：输入 `/status` 等无参命令后按 Enter 只反复确认补全（填入同名文本又使浮层复活），命令始终不执行。现在候选与输入完全一致时直接派发，前缀补全仍保持"填入 → 再提交"的两段式。

## [0.7.0] - 2026-10-24

### Fixed

- **安全分类器可被包装器前缀绕过**：`timeout 5 rm -rf ~`、`nice -n 5 rm -rf ~/d`、`env -i rm -rf /tmp/x`、`stdbuf -oL rm -rf x`、`command rm -rf x`、`bash -lc 'rm -rf ~'`、`foo=$(rm -rf ~)` 此前全部返回 `allow`。现在包装器（`timeout`/`nice`/`env`/`xargs`/`stdbuf`/`time`/`nohup`/`command`/`builtin`/`exec`）按语义消费其选项与操作数后定位真实命令；命令替换在任意位置递归展开；带版本号的解释器名与组合标志（`-lc`）进入确认档；无法可靠展开时保守拒绝。
- **敏感路径判定误杀正常动作**：`echo secret`、`grep -r SECRET src`、`cat .env.example` 此前全部 `deny`。现在凭据类文件名只在 token 具有路径形态时生效，`.env.example`/`.env.sample`/`.env.template`/`.env.dist` 显式放行；`.env`、`~/.ssh/id_rsa`、`*.pem` 等真实目标仍然拒绝。
- **只读搜索工具没有文件边界**：`grep`/`find`/`ls` 与 `read` 采用同一边界结论（界内放行、界外放行并警告、敏感路径拒绝），`grep ~/.ssh` 不再能绕过 `read` 读私钥。
- **越界警告模型看不到**：`ToolDecision` 增加 `warning` 字段，安全策略的越界提示现在以单行 `[安全提示]` 前缀进入模型可见的工具结果。
- **bash 合并输出无上限**：stdout/stderr 各自 30KB 截断后合并可达约 60KB。现在合并后按有效输出上限再截一次，标记 `truncated_by=merged_budget`，保留末尾与原始总量；超时/清理不确定状态不被覆盖。同时删除从未使用的 `MAX_OUTPUT_CHARS` 常量。
- **中文 token 被系统性低估约 4 倍**：50 个中文字符此前估为 12 tokens。新增共享估算器（CJK 按字计价、ASCII 保持 `len // 4`），预算快照与自动压缩切点共用同一实现；工具结果裁剪改为按估算 token 二分收敛，不再用 `allocation * 4` 字符硬折算。
- `prepare_context` 在工具结果被预算裁剪时会重复发布一次 `CONTEXT_BUDGET` 事件（两次 payload 完全相同），导致订阅方（TUI `/context`、headless `--context`）把一次请求的预算变化计成两次。现在每个请求恰好发布一个预算快照，并补充按事件计数的回归测试。
- **会话索引追加退化为 O(n²)**：`_append` 先写 JSONL 再读索引，指纹必然失配，增量分支永不触发。改为写前读索引并应用记录、写后只刷新指纹；1000 次追加由约 7s 降至 0.37s。

### Added（v0.7 扩展与运行期安全）

- **工具注册表数据化**：`make_tools` 由硬编码列表改为声明式 `ToolSpec` / `ToolRegistry`，新增工具只需追加声明；契约测试锁定名称、类型与顺序。
- **11 个内建工具**：新增 `web_fetch`（http/https、网络经注入、响应有界）、`web_search`（注入式搜索提供方，未配置时明确不可用）、`todo`（整体替换式任务清单，仅驻内存）；web 出站进确认环，headless 下 fail-closed。
- **审批结果封闭枚举**：新增 `ApprovalOutcome`（`allowed_once` / `rejected` / `cancelled` / `timed_out` / `unavailable`）与 fail-closed 映射；确认请求状态由开放字符串收敛为封闭终态。
- **工具执行瀑布管线**：`before_tool_calls` / `after_tool_calls` 有序链——pre 支持通知、改参、门禁短路，post 支持结果变换；安全策略门禁固定链尾并对改参后的调用判定。**BREAKING**：原单值字段改名为复数元组。
- **扩展插件目录（v1）**：`~/.codeagent/extensions/<id>/` + `codeagent-plugin.json`，模块导出 `TOOL_SPECS`，工具名 `ext__<id>__<tool>`；目录放置即信任，调用层默认需确认，`extensions.json` 提供 deny/ask/allow 三级规则（与 MCP 共用匹配语义）。
- **Subagent 有界并发与 `implement` profile**：`subagent_max_concurrency`（默认 1 保持串行）启用有界并发；新增受限可写 `implement`（read/write/edit/bash/grep/find/ls/skill，禁 `delegate`/MCP）。
- **API 形状注册表**：`ai/transport/shapes.py` 与 `ProviderDefinition.api_shape`（未知形状 fail-closed）；新增 `register_provider` / `register_api_shape` 入口，同形状 provider 无需改 transport。
- **三档 bash 沙箱**：`read-only` / `workspace-write` / `danger-full-access`（默认）；macOS Seatbelt、Linux bwrap，受限策略无后端 fail-closed；后端参数以独立 argv 注入。
- **写前 checkpoint 与 `codeagent undo`**：`write` / `edit` 在锁内保存原文，快照有界淘汰，支持 `--list` / `--dry-run` / LIFO 恢复；快照失败不阻塞写入。
- **缓存命中诊断**：`--context` 输出命中率与 `cache_unknown` / `cache_cold` / `cache_effective`；契约测试锁定基础系统提示词前缀不含时间戳/临时目录。
- **离线评测框架**：`evals/` + `python -m evals`，覆盖工具流、未知工具、审批阻断与改参传播；`tests/test_evals.py` 纳入 `contract` 门禁。
- `docs/iteration/v0.7.md`：本批次实现、验证与限制的完整记录。
- 发布文档：[v0.7.0 发布说明](docs/releases/v0.7.0.md) 与 [升级指南](docs/releases/v0.7-upgrade.md)。

### Added（v0.6 正确性硬化）

- `docs/design/roadmap-v0.6.md`：v0.6 硬化路线图与实测证据、后续版本（执行控制 / 沙箱与程序化工具 / 子 Agent 演进 / 对外接口）。
- 三个 OpenSpec 变更并已归档：`security-classification-hardening`、`context-accounting-fidelity`、`session-index-incremental`；主规格 `tools`、`context-budget`、`sessions` 同步更新。
- 新增回归测试：安全绕过/误杀/边界（21 例）、合并输出上限（3 例）、token 估算口径（5 例）、索引增量与追加规模（3 例）。
- 新增模块：`tools/security/wrappers.py`（包装器语义跳过）、`tools/security/interpreters.py`（解释器家族与内联标志）、`tools/shared/merged.py`（合并输出上限）、`core/context/tokens.py`（共享 token 估算）、`core/context/governance.py`（工具结果按预算治理）。

### Changed

- `tests/session/behavior/test_compaction.py`、`test_context_recovery_regression.py`、`tests/app/container/test_model.py` 的窗口与压缩预算按中英混合估算口径等比放大（中文内容估算值约为旧口径数倍，原参数已小于单轮输入）。
- 测试 marker 分层修正：`tests/conftest.py` 现在让显式主分类（模块级 `pytestmark` 或函数装饰器）优先于目录兜底，同一目录可按真实边界细化。`tests/app/container/test_assembly.py` 整体改标 `contract`（用 fake provider 与 stub backend，不启外部进程），其中真正启动 MCP 子进程的 `test_config_append_mcp_tools` 单独标 `integration`。
  - 效果：`app/composition/policy.py` 的快速口径覆盖率由 **20%** 升至 **84%**，deny / interactive / allow 三个安全决策分支与文件边界回归从此进入每次 `quality-fast`；矩阵批次由 212 降到 161，移出的纯装配用例由快速批次接管。
  - 覆盖率：快速质量集由 `1540 passed` / **84.58%** 变为 `1562 passed` / **86.35%**（15932/18451 statements），CI 硬下限由 77.9% 上调至 **80%**。
- `docs/testing.md`、`README.md`、wiki 与设计文档同步上述口径。
- **v0.7**：CI 的 Ruff 检查与格式化门禁覆盖范围扩展为 `src tests evals scripts`（同步 AGENTS.md、`docs/testing.md` 与 wiki 开发指南）；`docs/wiki/` 与设计文档同步工具数量、Subagent 能力、沙箱/checkpoint/缓存/评测、版本状态与"明确不做"清单；`docs/design/roadmap-v0.6.md` 追加事后状态，说明沙箱、并发 Subagent、插件与回退能力已交付，剩余结构性缺口未变。

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

### Engineering updates

- Subagent 领域规则下沉到 `core/subagent/`（预算默认值与硬上限、深度与配额、准入校验顺序、终态归因、委派槽位登记）；`app/composition/subagent/` 只保留子 Session 创建、事件发布与资源收尾装配，应用层不再维护第二份预算常量。
- 规模约束成为覆盖全部生产层的可执行门禁：`scripts/scale_scan.py` 扫描 `app` / `core` / `session` / `ai` / `tools`（单文件 ≤300 行、单函数 ≤80 行），由新增的 `tests/contracts/test_scale_limits.py` 纳入 `unit or contract` 质量门禁，并收敛原先只覆盖三层的重复测试。
- 为通过规模门禁完成按职责拆分：`tools/security/classifier.py` → `ask_rules.py`，`tools/mcp/client.py` → `content.py`，`session/persistence/jsonl/recovery.py` → `recovery_diagnostics.py`，`session/session.py` → `persistence_control.py` mixin，`app/tui/presentation/status.py` → `status_zones.py`，`app/tui/presentation/blocks/subagent.py` → `subagent_glyphs.py`。外部行为与公共接口未变。
- 统一格式化门禁接入 CI：`ruff format`（行宽 100）成为唯一格式化方案，`quality-fast` 增加 `ruff format --check src tests scripts`；全仓按该方案完成一次格式化。
- 类型门禁以分层棘轮方式接入：`scripts/type_scan.py` 逐层统计 mypy 错误数并与 `docs/type-baseline.json` 比较（接入时基线为 core 15 / ai 14 / tools 24 / session 311 / app 696），任何一层回升即失败，债务下降后用 `--update` 固化基线。dev 依赖新增 `mypy`，`pyproject.toml` 增加 `[tool.mypy]`。
- `AGENTS.md` 与 `docs/design/architecture.md` 同步了新的分层归属、门禁命令与豁免规则。

### Verification

- 当前 Windows / Python 3.12 全量离线测试为 `1695 passed，3 skipped`（1698 collected）；快速质量集为 `1525 passed，3 skipped，170 deselected`，覆盖率 `84.40%`（15232/18048 statements，CI 硬下限 77.9%）；跨边界集合（integration / e2e / platform / compatibility）为 `212 passed`。（**2026-10-18 复核更正**：在 macOS / Python 3.12 上重跑为全量 `1710 passed`、快速质量集 `1540 passed`、覆盖率 `84.58%`、跨边界集合 `212 passed`。全量收集数从 1698 变为 1710 而 `tests/` 自 v0.5.0 发布后未变更，说明原收集数已不可复现；上列原始数字保留为发布时点的历史记录。）
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
