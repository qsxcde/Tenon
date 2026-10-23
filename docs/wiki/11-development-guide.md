# 11 · 开发指南：测试、门禁与扩展

> 面向本仓库贡献者：环境准备、测试分层、质量门禁、常见扩展点（新增工具 / provider / TUI 命令 / 事件类型）、CI 分层与发布流程。仓库规范以根目录 [`AGENTS.md`](../../AGENTS.md) 为准，本文是其可操作化版本。

## 一、环境准备

```bash
uv sync --group dev                # 运行时 + 开发依赖（CI 用 --locked）
uv run codeagent --prompt "你好"    # 无头 CLI 冒烟
uv run codeagent --tui             # 交互式终端
```

- Python `>=3.12`，构建后端 `uv_build`，包版本 `0.5.0`（与 `pyproject.toml` 单一事实源一致）。
- 测试必须离线：不依赖真实 API key、真实 provider 或用户 `~/.codeagent` 数据；用 `FakeClient`、`tmp_path`、`monkeypatch`、`InMemoryFsOps`。
- 凭据只放 `~/.codeagent/.env`；仓库本地 `.env` 不会被读取。

## 二、测试分层与命令

| marker | 含义 | 日常命令 |
| --- | --- | --- |
| `unit` | 单模块、无外部进程 | `uv run pytest -m "unit or contract" -q --strict-markers` |
| `contract` | 跨实现/架构边界契约 | 同上 |
| `integration` | 组合多模块、文件存储、MCP、subprocess | `uv run pytest -m "integration or e2e or platform or compatibility" -q --strict-markers` |
| `e2e` | 从 CLI/TUI 入口验证完整用户路径 | 同上 |
| `platform` | 平台差异行为 | 同上 |
| `security` | 安全策略、拒绝、确认、文件边界 | 随所属分层运行 |
| `performance` | 性能基线与渲染指标 | 见第九节 |
| `slow` | 常规回归但不宜进快速集 | `uv run pytest -m "not slow" -q`（日常反馈集） |

`tests/conftest.py::pytest_collection_modifyitems` 会为未特别识别的测试补默认 `unit` 分类，并为工具进程测试追加 `platform`、安全测试追加 `security`——新增测试不会因漏写 marker 而从分层命令中消失，但仍应主动声明正确的 marker。

共享夹具（`tests/fixtures/`）：`ai.py`（离线 `FakeClient`）、`filesystem.py`（`InMemoryFsOps`/`memory_fsops`）、`session.py`（默认离线工具集的 `session_factory`）、`resources.py`（后台任务/同步/异步资源的 teardown tracker）。

异步约定：直接 `async def` 测试（`asyncio_mode = "auto"`，超时 120s）；不用固定 `sleep` 等待调度；后台任务/客户端/subprocess 必须在测试结束前关闭或确认取消（autouse fixture 检查 pending task 泄漏）。

## 三、六项质量门禁

| 门禁 | 命令 | 说明 |
| --- | --- | --- |
| 正确性静态检查 | `uv run ruff check src tests scripts` | 仅启用 `E9`（语法错误）、`F821`（未定义名）、`F841`（未使用局部变量） |
| 格式化 | `uv run ruff format --check src tests scripts` | 唯一方案（不引入 Black），行宽 100 |
| 类型棘轮 | `uv run python scripts/type_scan.py` | mypy 按 core/ai/tools/session/app 五层统计，与 `docs/type-baseline.json` 比较，回升即失败；债务下降后用 `--update` 固化基线 |
| 规模门禁 | `uv run python scripts/scale_scan.py` | 生产层单文件 ≤ 300 行、单函数 ≤ 80 行；豁免仅在 `COMPATIBILITY_EXCEPTIONS` 逐项登记 |
| 分层测试 | `uv run pytest -m "unit or contract" -q` | 快速质量集；CI 覆盖率硬下限 **80%**（实测 86.35%） |
| 发布检查 | `uv run python scripts/release_check.py --dist-dir artifacts/dist --output artifacts/release-check.json` | 构建 wheel/sdist、版本/资源/敏感文件检查、干净环境安装 + fake provider CLI 验证 |

禁止为通过门禁放宽配置或扩大基线。完整 Ruff 规则集与 pyright 尚未接入 CI；接入任一门禁时必须同步更新 `pyproject.toml`、CI 与 `AGENTS.md`。

## 四、扩展 recipes

### 4.1 新增内置工具

1. 在 `tools/atomic/<name>.py` 实现 `AtomicTool` 子类：`name`/`description`/`Args`（pydantic）/`_invoke`。
2. 只通过注入的 `self._cwd`/`self._ops`/`self._resource_limits` 访问外部；输出经 `shared/truncate` 或 `govern_text` 截断。
3. 在 `tools/registry.BUILTIN_TOOL_SPECS` 追加 `ToolSpec` 声明（名称 + 构建函数，顺序即装配顺序）。
4. 若涉及写操作：在 `tools/security/ask_rules.py` 增加确认规则；涉及路径边界则在 `filesystem._BOUNDED_TOOLS` 纳入。
5. 补 `tests/tools/` 的 unit 测试与必要的安全测试（`security` marker）。

### 4.2 新增 provider

1. 在 `ai/providers/<name>.py` 定义 `XxxConfig(BaseSettings)`（`env_prefix="XXX_"`，`api_key: SecretStr`、`base_url`、`model`）与 `make_llm` 工厂（缺 key 时报可操作错误）。
2. 在 `ai/catalog/builtin.py` 增加模型目录（`ModelSpec` 必须显式声明能力三态与 `context_window`）。
3. 在 `ai/providers/all.py` 注册 `BUILTIN_PROVIDERS` 与 `PROVIDER_CONFIGS`。
4. 若 provider 有特殊流式形状，补 `ai/transport` 的契约测试；`reasoning_effort` 兼容性未确认时默认 `None` 不发送。
5. 补离线契约测试（`tests/contracts/test_provider_contract.py` 风格），不得依赖真实网络。

### 4.3 新增 TUI 斜杠命令

1. 在 `tui/commands/parser.py` 的 `default_registry()` 注册 `CommandSpec`（`args` 与 `picker` 按需）。
2. 在 `tui/commands/dispatch.py`/`coordinator.py` 实现分发，会话级动作放 `tui/session/actions.py`。
3. 命令实现只依赖 `TuiBackend` 端口；失败必须在 TUI 内反馈，且不得发起模型请求或改写聊天历史。
4. 补 `tests/tui/` 解析/分发/交互测试，注意失败路径与空态。

### 4.4 新增事件类型

1. 在 `core/contracts/events.py` 的 `EventType` 增加枚举与类型化关联字段（如 `run_id`/`delegation_id`）。
2. 发布点只在 core/session 的既有边界；TUI/headless 通过 `RuntimeReducer` 消费（新增归约分支 + `TuiModel`/`Transcript` 展示）。
3. 若事件携带对子会话的关联，遵循 `delegation_id` 关联约定。
4. 补契约测试（事件字段稳定性）与 TUI/headless 消费回归。

### 4.5 新增扩展插件（`~/.codeagent/extensions/`）

1. 建目录 `~/.codeagent/extensions/<id>/`，放 `codeagent-plugin.json`（`id`/`name`/`version`/`module`/`tools`，id 与工具名匹配 `^[a-z][a-z0-9_]*$` 且不含 `__`）与 manifest 声明的 Python 模块（单文件，兄弟 import 不支持）。
2. 模块导出 `TOOL_SPECS: Iterable[ToolSpec]`（与 `BUILTIN_TOOL_SPECS` 同构，`build(ToolBuildContext) -> AtomicTool`）。
3. 装配后工具名为 `ext__<id>__<工具名>`；**目录放置即信任**（插件代码同进程执行，import 期副作用属信任范围），调用层 fail-closed：默认需确认，可在 `~/.codeagent/extensions.json` 的 `permissions.deny/ask/allow` 显式放行/拒绝（glob，deny 优先）。
4. 单插件失败只产生 `plugin_failed:` 诊断并跳过；补离线测试（`tests/tools/plugins/`，tmp_path 假插件目录）。

## 五、编码规范要点

- Python 3.12+、4 空格缩进、完整类型注解；`snake_case`/`PascalCase`/`UPPER_SNAKE_CASE`；布尔用 `is_`/`has_`/`can_` 前缀。
- 注释解释"为什么"（约束、取舍），不复述代码；错误信息含操作、对象、失败原因。
- 使用明确的项目异常；不得无差别捕获 `Exception`；异步中不得直接做阻塞 I/O。
- 外部资源在成功/失败/超时/取消路径都必须释放。
- 规模：接近 300 行/80 行时按职责拆分而不是追加；不复用未登记的豁免。

## 六、提交与 PR

- 提交信息：简短祈使句 + 仓库前缀（`feat:` / `fix:` / `docs:` / `test:` / `ci:`）；一次提交只做一件事；格式化/重命名/无关重构不混入功能提交。
- PR 必须说明：行为变化、影响范围、风险、验证命令、未覆盖部分；TUI 变更附截图或终端录屏。
- 修改前先看 `git status` / `git diff`，保留用户已有修改；不提交密钥、构建产物、用户数据或无关工作区改动。

## 七、CI 分层（.github/workflows/ci.yml）

| 任务 | 内容 |
| --- | --- |
| `quality-fast` | Ruff、unit/contract 测试、覆盖率（`--cov-fail-under=80`）、版本一致性、补丁格式与 OpenSpec 校验 |
| `test-matrix` | Ubuntu / Windows / macOS 上执行 integration/e2e/platform/compatibility（统一 fake provider；失败保留 JUnit） |
| `package-smoke` | release check：构建、产物检查、干净环境安装、CLI 与内建 resources 验证 |
| `performance` | 离线 TUI 基准（5 场景）并上传 JSON；回归只告警，不阻断普通 PR（发布候选用 `--fail-on-regression`） |

当前 `quality-fast` 与平台矩阵存在约 25 个兼容性/平台测试重复执行；不影响正确性，后续需决定保留或调整 marker 分层。

## 八、版本与文档同步

- 行为、配置、公共接口、持久化格式变化必须同步 `docs/` 或 `openspec/` 产物；规格校验：`openspec validate --specs`。
- 测试数量变化需说明：新增覆盖 / 拆分迁移 / 删除过期测试。
- Bug 修复必须带回归测试；异常、取消、重试语义变更必须补边界路径测试。

## 九、性能与发布

```bash
# TUI 基准（单场景示例）
uv run python scripts/benchmark_tui.py --scenario stream --blocks 100 --stream-chars 10000 \
  --tool-output-bytes 20000 --width 80 --height 24 --iterations 3 --output artifacts/tui-benchmark.json
uv run python scripts/compare_benchmark.py artifacts/tui-stream.json docs/benchmarks/tui-baseline.json --max-regression 0.20

# 长会话扩展观察（1000/5000/10000 blocks）
uv run python scripts/benchmark_tui.py --scenario history --blocks 1000 --iterations 1 --output artifacts/tui-history-1000.json

# 发布候选：v2 基线组装与发布检查
uv run python scripts/update_tui_baseline.py --output artifacts/tui-baseline-v2.json --baseline-id linux-py312-tui-v2 <四场景报告...>
uv run python scripts/release_check.py --dist-dir artifacts/dist --output artifacts/release-check.json
```

- 性能双门槛：帧/控制事件/丢帧用硬上限；同环境渲染、恢复与内存指标用 20% 相对回归线。仓库内 `docs/benchmarks/tui-baseline.json` 是 schema v1 历史基线，不能直接与 v2 报告比较。
- 发布前检查：版本号、wheel/sdist、内建资源、变更日志、回滚方案。

## 十、常见陷阱

| 陷阱 | 正确做法 |
| --- | --- |
| 在 core 里 import tools/ai/session | 通过端口 + 组合根适配（`tests/test_decoupling.py` 会失败） |
| 在非适配区 import textual | 只允许 `app/tui/adapters/textual/` 的四个文件 |
| 在 app/composition 里重复声明 subagent 预算默认值 | 默认值与上限只在 `core/subagent/` |
| 让 `app/container.py` 承载实现 | façade 只导出；实现放 `app/composition/*`，且不得反向导入 façade |
| 用固定 `sleep` 等异步稳定 | 用显式事件/受控 clock |
| 静默丢弃超限内容 | 截断必标记、裁剪必可见（返回诊断） |
| 让 `~/.codeagent` 数据进入测试 | 用 `tmp_path` + 注入配置目录 |
| 为通过门禁放宽 mypy/规模配置 | 拆分代码或按流程登记豁免 |

## 相关阅读

- 依赖边界与强制手段：[10-dependency-map.md](./10-dependency-map.md)
- 运行方式与验证命令：[03-runtime-flow.md](./03-runtime-flow.md)
- 术语与常量速查：[12-glossary.md](./12-glossary.md)