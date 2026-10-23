# 07 · tools 层：内置工具、安全与基础设施

> tools 层是 Agent 与真实世界之间的唯一接口层：11 个原子工具、统一安全分类、MCP 外部工具适配、跨平台进程执行，以及一组可离线测试的共享基础设施。它不 import `core`（由 `tests/test_decoupling.py` 强制），对 core 的适配只发生在 `app/composition/tools/adapter.py`。

## 一、层内地图

| 子包/模块 | 职责 |
| --- | --- |
| `tools/base.py` | `AtomicTool` 抽象基类（无状态、依赖注入） |
| `tools/registry.py` | `make_tools(...)` 工具集工厂 |
| `tools/atomic/*` | read / write / edit / bash / grep / find / ls / skill / web_fetch / web_search / todo 十一个内置工具 |
| `tools/security/*` | 统一安全分类（allow / ask / deny）、危险命令、文件边界、MCP 权限 |
| `tools/mcp/*` | MCP 服务端客户端、工具适配、预算裁剪、加载与收尾 |
| `tools/plugins/*` | 扩展插件：manifest 解析、`TOOL_SPECS` 加载（`ext__<id>__<工具>` 命名）、`extensions.json` 权限规则 |
| `tools/execution/*` | 跨平台进程执行、外部检索器（rg/fd）、bash 解析、沙箱策略（read-only / workspace-write / 三档后端） |
| `tools/shared/*` | FsOps 抽象、路径、忽略策略、文本、截断、资源限制、写串行化、输出治理、写前 checkpoint |
| `tools/capabilities.py` | 只读环境能力探测（平台 / bash / 清理语义 / rg / fd / 安全策略） |

分层约束：`tools` 可用标准库与外部依赖（pydantic），禁止 import `core`/`session`/`ai`/`app`；`shared` 只提供基础设施，不承载业务流程。

## 二、AtomicTool 与工具装配

### 2.1 AtomicTool 契约

`tools/base.py` 的 `AtomicTool` 是无状态工具基类，子类需定义：

| 成员 | 类型 | 说明 |
| --- | --- | --- |
| `name` | `ClassVar[str]` | 模型调用标识 |
| `description` | `ClassVar[str]` | 注入模型提示词的描述（保持精简） |
| `Args` | `ClassVar[type[BaseModel]]` | Pydantic 输入 schema，`args_schema` 属性对外暴露，供模型端口生成 function schema |
| `_invoke(args) -> str` | 方法 | 纯函数式执行，返回回填模型的结果文本；`invoke()` 是校验后的公共入口 |

构造注入（design D2）：`AtomicTool(cwd=None, ops=None, resource_limits=None)`：

- `_cwd`：相对路径解析基准，缺省回退进程启动目录；
- `_ops`：`FsOps` 文件系统抽象，缺省 `LocalFsOps`——工具逻辑不直接触碰文件系统，因此可在内存文件系统（`InMemoryFsOps`）上离线测试；
- `_resource_limits`：不可变的 `ToolResourceLimits`；`output_max_bytes` 返回 `min(max_output_bytes, max_memory_bytes)`（预览内存上限）。

### 2.2 工具集工厂

`tools/registry.py` 的 `make_tools(cfg=None, skills=None, resource_limits=None) -> list[AtomicTool]`：

- `cwd` 从 `cfg.cwd` 读取（否则进程启动目录）；
- `skills` 是"技能名 → 预渲染块"注册表，注入 `SkillTool`；`None` 时 skill 工具返回"未注入"提示；
- 默认返回十一个工具：read / write / edit / bash / grep / find / ls / skill / web_fetch / web_search / todo（声明见 `BUILTIN_TOOL_SPECS`，声明顺序即装配顺序）；
- 无网络、无密钥副作用（web 工具的网络能力经注入，缺省实现不主动出网）；资源限制通过 `ToolResourceLimits.from_config(cfg)` 从应用配置读取。

## 三、十一个内置工具

| 工具 | 能力 | 关键默认值 |
| --- | --- | --- |
| `read` | 读取文本文件（含行区间），二进制给有限预览 | 默认最多 2000 行；`BINARY_PREVIEW_BYTES` 预览截断 |
| `write` | 写入/覆盖文件（自动建目录） | 统一输出上限（30 000 字节 / 2000 行） |
| `edit` | 精确字符串替换编辑 | 走路径锁串行化 |
| `bash` | 执行 shell 命令 | 默认超时 120s，硬上限 600s，输出 ≤30 000 字符；沙箱策略默认 `danger-full-access`（受限策略无后端时 fail-closed） |
| `grep` | 内容检索（优先 `rg`，缺省纯 Python fallback） | `DEFAULT_LIMIT = 100` 条匹配 |
| `find` | 文件名/路径检索（优先 `fd`，缺省纯 Python fallback） | `DEFAULT_LIMIT = 1000` |
| `ls` | 列目录 | `DEFAULT_LIMIT = 500` 条 |
| `skill` | 返回已注入技能文档 | 内容由组合根预渲染 |
| `web_fetch` | 抓取 http/https URL 内容 | 网络经注入 fetcher（缺省 urllib，读取 ≤2MB）；出站进 ask 档 |
| `web_search` | 经注入的搜索提供方检索 | 未注入返回不可用提示；`DEFAULT_LIMIT = 5`；出站进 ask 档 |
| `todo` | 整体替换式会话级任务清单 | `MAX_TODOS = 200`；状态经 `TodoState` 注入，仅驻内存 |

- 全部工具输出经 `shared/truncate` 统一截断：任一上限（行/字节）先到即截，且**截断必标记**；`truncate_head` 保留开头（read/grep/find/ls），`truncate_tail` 保留末尾（bash，超时/报错信息通常在末尾）。
- 截断结果承载 `ToolOutputMetadata`（完整性、总字节/行数、截断原因、`continuation` 续读提示等），是会话层归约与 TUI 展示的事实来源。
- 同一消息内多个 tool_call 并行执行时，写类工具（write/edit）按路径经 `shared/mutation_queue.with_path_lock` 的 `threading.Lock` 串行化，避免 write+edit 竞态丢更新；调用方必须先 `resolve_to_cwd` 解析为绝对路径再取锁（锁以路径字符串为键）。

## 四、共享基础设施（tools/shared）

| 模块 | 关键导出 | 说明 |
| --- | --- | --- |
| `fsops.py` | `FsOps`、`LocalFsOps` | 文件系统抽象协议与本地实现（测试有 `InMemoryFsOps`） |
| `paths.py` | `normalize_path`、`resolve_to_cwd` | 路径归一与相对基准解析 |
| `ignore.py` | `NOISE_DIRS`、`prune_noise_dirs` | 常见噪声目录（`.git`/`node_modules` 等）剪枝 |
| `textfile.py` | `detect_line_ending`、`normalize_to_lf`、`restore_line_endings`、`strip_bom` | 保留原始换行风格与 BOM 的处理链 |
| `truncate.py` | 见第三节 | `DEFAULT_MAX_BYTES = 30_000`、`DEFAULT_MAX_LINES = 2000` |
| `resource_limits.py` | `ToolResourceLimits` | 并发 4 / 最大超时 600s / 预览内存 1 048 576 字节 / 清理超时 10s |
| `mutation_queue.py` | `with_path_lock` | 写类工具路径级互斥 |
| `governance.py` | `OutputPolicy`、`govern_text`、`redact_metadata_text` | 有界输出治理与元数据脱敏 |

`ToolResourceLimits` 字段（全部严格校验为正数）：

| 字段 | 默认值 | 约束 |
| --- | --- | --- |
| `max_concurrency` | 4 | 统一 runtime 的并发闸门 |
| `timeout` | `None` | 允许覆盖默认超时，但不得超过 `max_timeout` |
| `max_timeout` | 600.0s | 硬上限 |
| `max_output_bytes` | 30 000 | 截断字节上限 |
| `max_output_lines` | 2000 | 截断行上限 |
| `max_memory_bytes` | 1 048 576 | 预览物化内存上限（进程完整输出仍在临时文件中） |
| `cleanup_timeout` | 10.0s | 超时/取消后的有限清理等待 |

## 五、安全模型（tools/security）

### 5.1 决策与判定顺序

`SecurityDecision(action, reason, warning)`，`action ∈ {allow, ask, deny}`。分类器入口：`classify_bash`（bash 命令）、`classify_tool`（按工具名分发）、`classify_file`（文件边界）、`classify_mcp`（MCP 工具）。判定顺序固定为 **deny > ask > allow**：

1. **deny**：危险命令意图（`bash_rules._dangerous_intent/_dangerous_hit`）——如递归强删、下载即执行（`curl ... | sh`）等；命中即拒绝，不可被 allowlist 覆盖。
2. **ask**：`ask_rules.default_ask_rules` 的需确认清单（写操作、未知命令等）。
3. **allow**：只读 allowlist（`ls`/`cat`/`grep`/`pwd`/`echo`/`head`/`tail`/`which` 与 `git status/diff/log/show` 等）与已知安全路径。

### 5.2 命令解析与文件边界

- `shell_parse.split_segments`：以 shlex 语义切分复合命令（`;`/`&&`/`||`/管道），**语法非法时 fail closed**（按不可信处理），且逐段分类，避免"前段安全掩盖后段危险"。
- `filesystem._BOUNDED_TOOLS = ("read", "write", "edit")`：这三个工具受工作区边界约束；`within_workspace(path, workspace)` 校验越界；`_secret_path_hit` 拦截凭据类敏感路径（如 `.env`）。越界与敏感路径产生 deny/ask，按规则而定。
- `security/mcp.py`：MCP 工具的权限分类（服务器级/工具级），与内建工具统一进入同一决策面。

安全分类结果最终由 core 的 `ApprovalPolicy` 端口在运行期裁定（自动允许 / 询问用户 / 拒绝），确认交互由会话层的 `ConfirmationCoordinator` 承载。

## 六、MCP 集成（tools/mcp）

| 模块 | 关键内容 |
| --- | --- |
| `server_config.py` | `StdioServerParameters` 等服务器描述 |
| `config.py` | 从配置解析 MCP 服务器清单 |
| `client.py` | `McpServerClient`：stdio 后台线程事件循环；`start(timeout=10.0)` / `tools` / `call_tool` / `submit_tool` / `close` |
| `adapter.py` | `McpTool(AtomicTool)` + `McpArgs`：把远程工具包装为原子工具 |
| `budget.py` | 分组预算：`GLOBAL_TOOL_CAP = 40`、`PER_SERVER_TOOL_CAP = 15`、`DESCRIPTION_CAP = 200` |
| `content.py` | MCP 结果内容归一 |
| `permissions.py` | MCP 服务器/工具权限判定 |
| `loader.py` | `load_mcp_tools`、`close_mcp_tools`、`close_mcp_clients` |

要点：

- **命名空间**：加载后的工具名为 `mcp__<server>__<tool>`，与内建工具在同一注册表中共存（内建工具不参与预算，恒保留）。
- **预算与可见诊断**：超限裁剪是确定性的（每 server 裁尾部；总量超限从最后的 server 逆序释放），且**裁剪必须可见**——`apply_budget` 返回诊断消息列表，不静默丢弃（源自 Qwen 2 连接硬限的用户反噬教训）。
- **生命周期**：客户端在后台线程持有事件循环；`close_*` 是幂等收尾路径，运行期资源所有权归 `AgentRuntime`。

## 七、跨平台执行（tools/execution）

| 模块 | 关键内容 |
| --- | --- |
| `process.py` | `ProcessRequest` / `ProcessResult` / `ProcessRunner`：统一进程执行，输出写临时文件后**有界读取**（`_decode_bounded`），内存只保留预览 |
| `posix.py` | POSIX 后端：进程组（`setsid`）支持可确认的进程树清理 |
| `windows.py` | Windows 后端：`taskkill /T` 尽力清理，MSYS 派生孙进程可能残留（能力探测如实标记为 `cleanup_best_effort`） |
| `search.py` | `run_rg` / `run_optional_search`：`rg --json` 解析、`fd` 路径过滤；参数以独立 argv 传递、不经 shell；外部工具缺失时纯 Python fallback，语义（glob、相对路径、上下文、limit）保持一致 |
| `shell.py` | `resolve_bash` / `bash_env` / `is_wsl_shim` / `all_which`：定位可用 bash（含 Windows Git Bash / WSL shim 判断） |

执行语义与 core 的 `ToolExecutionRuntime` 对接：超时、取消、输出上限、清理等待与"清理不确定"状态都在这一层产生结构化事实，由 runtime 决定终态。

## 八、能力探测（tools/capabilities.py）

`detect_tool_capabilities(*, env, os_name, sys_platform, which, shell_resolver, security_policy)` 返回不可变快照 `ToolCapabilities(platform, items)`：

| key | 说明 |
| --- | --- |
| `platform` | 归一后的平台名（windows / macos / linux / freebsd / …） |
| `shell` | bash 可用性；缺失时给出安装建议（Windows 指向 Git for Windows） |
| `process_tree_cleanup` | POSIX = 可确认清理；Windows = `cleanup_best_effort`（不确定即如实标记） |
| `rg` / `fd` | 可选加速器可用性；缺失时说明使用纯 Python 搜索路径 |
| `permissions` | 安全策略三态：已装配 / 未装配 / 未知 |

探测**只做只读的 PATH/配置判断**：不启动外部命令、不触发确认、不写会话；`which` 与 `shell_resolver` 是显式注入点，便于离线测试。快照供 TUI `/status` 与诊断使用。

## 九、与其他层的关系

| 交互 | 位置 | 说明 |
| --- | --- | --- |
| 原子工具 → core `AgentTool` | `app/composition/tools/adapter.py` | 组合根适配，core 不依赖工具实现形态 |
| 安全决策 → 策略端口 | `app/composition/policy.py` | 把 `SecurityDecision` 接入 core `ApprovalPolicy` |
| Resource Limits | `app/config.py` → `ToolResourceLimits.from_config` | 配置注入，工具层无全局状态 |
| MCP 生命周期 | `app/composition/tools/factory.py`（`_load_mcp_tools`） | 装载与收尾挂在应用运行时 |
| skill 内容 | `app/skills/*` → `make_tools(skills=...)` | 组合根预渲染技能块 |

## 十、设计约束

1. **无状态**：工具实例不持有会话/缓存状态，天然可重放、可离线测试。
2. **依赖注入**：`cwd`/`ops`/`resource_limits` 全部构造注入，不读全局环境。
3. **工具层不知道 core**：适配在组合根单点完成（`tests/test_decoupling.py` 强制）。
4. **截断必标记、裁剪必可见**：任何有损行为都必须回传结构化元数据与诊断。
5. **失败关闭（fail closed）**：命令解析失败、安全状态未知时按不可信处理，不猜测放行。
6. **资源有界**：并发、超时、输出、内存、清理等待都有明确上限与终态事实。

## 相关阅读

- core 如何执行工具批次：[04-core-layer.md](./04-core-layer.md)
- 工具结果如何落盘与回填：[05-session-layer.md](./05-session-layer.md)
- 工具如何装配进运行时：[08-app-layer.md](./08-app-layer.md)