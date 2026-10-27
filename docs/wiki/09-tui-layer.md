# 09 · TUI 层：终端交互界面

> TUI 是 `app/tui/` 下的完整子系统：端口/适配器隔离引擎（Textual 只出现在 `adapters/textual/`）、单向数据流（事件 → 状态归约 → 渲染）、30fps 渲染协调、命令体系与性能基准。`ports/`、`state/`、`presentation/`、`commands/`、`session/`、`rendering/` 必须保持 Textual-free。

## 一、子包结构与职责

| 子包 | 职责 | Textual 依赖 |
| --- | --- | --- |
| `tui/ports/` | `TuiBackend` 协议 + 处理器类型别名 | 禁止 |
| `tui/adapters/textual/` | 唯一允许 import Textual 的实现：`app.py`（应用）、`backend.py`、`rich.py`、`widgets.py` | 允许 |
| `tui/application.py` | `TuiApp`：视图逻辑，只依赖端口 | 禁止 |
| `tui/main.py` | `run_tui()` 入口 | 仅经由适配器 |
| `tui/state/` | `TuiModel` / `RuntimeReducer` / `Transcript` 等渲染态 | 禁止 |
| `tui/presentation/` | 块模型、Markdown 渲染、状态栏、主题、输出浏览 | 禁止 |
| `tui/commands/` | 斜杠命令解析/分发/模糊补全/交互 | 禁止 |
| `tui/session/` | 会话级动作：发送、恢复、`/fork`、协调 | 禁止 |
| `tui/rendering/` | 渲染协调、事件缓冲、调度、状态计时 | 禁止 |
| `tui/benchmark/` | 5 场景性能基准与 fixture | 禁止 |

边界由 `tests/contracts/test_tui_boundaries.py` 与 `tests/contracts/test_app_package_layout.py` 强制。

## 二、后端端口（TuiBackend）

`ports/backend.py` 定义引擎与视图的解耦缝。视图逻辑只调用端口方法：

| 分类 | 方法 |
| --- | --- |
| 生命周期 | `run()`（进入 alt 屏、阻塞到退出）、`stop()`、`exit_document(lines)`（退出后在主屏打印完整文档） |
| 渲染 | `render(lines)`（transcript 差分渲染）、`transcript_size()`、`set_status(line)`、`set_suggestions(lines)`、`set_confirmation(lines)` |
| 输入框 | `set_input_text`、`set_input_mask`（登录等敏感输入逐字符掩码，提交取原文）、`set_input_placeholder` |
| 输入回调 | `on_submit`、`on_interrupt`（Esc 打断）、`on_quit`（Ctrl+C）、`on_resize`、`on_click`（工具折叠）、`on_scroll`、`on_input_changed`、`on_suggestion_navigate`、`on_suggestion_confirm`、`on_confirmation_response`（y/n） |

当前实现为 Textual 适配器，但"自研引擎实现同一协议即可零改动替换视图"。

## 三、单向数据流

```
会话事件（core/session EventBus）
        │
        ▼
RuntimeReducer.reduce_runtime_event    ← state/runtime.py（纯归约）
        │
        ▼
TuiModel（history / tools / subagents / events 各 mixin）
        │
        ▼
Transcript（布局 / 渐进物化 / 索引）
        │
        ▼
TuiRenderCoordinator（30fps 防抖）→ TuiBackend.render(...) → Textual
```

- `state/runtime.py`：`RuntimeReducer` 把运行事件归约为稳定状态（`RunPhase`、工具生命周期 queued → running → terminal 的单向归约、确认状态），`reduce_runtime_event` 是纯函数入口。
- `state/model.py`：`TuiModel` 由 `ModelHistoryMixin` + `ModelEventMixin` 组合（另见 `model_tools.py`、`model_subagents.py`、`model_history.py`）。
- `state/transcript.py`：`Transcript` 由 `ProgressiveTranscriptMixin` + `TranscriptLayoutMixin` 组合，配合 `transcript_index*.py` 做视口物化与索引扫描，使长会话渲染不随历史线性增长。
- `state/tool_lifecycle.py`：与 core/session 的同一生命周期状态机对齐（`TOOL_FINISHED` 定状态、`TOOL_RESULT` 补输出）。

## 四、渲染协调（tui/rendering）

| 模块 | 职责 |
| --- | --- |
| `coordinator.py` | `TuiRenderCoordinator(target_fps=30.0)`：合并高频增量、按帧预算出帧、统计 `rendered_frames`/`dropped_frames`/`over_budget_frames` |
| `event_buffer.py` | 事件缓冲与合并 |
| `scheduler.py` | 定时调度（替代忙轮询） |
| `status_timer.py` | 状态栏计时（思考耗时等） |

渲染协调是"流式输出不卡顿"的核心：模型增量先入 buffer，协调器按帧节流；超预算帧计数作为性能回归事实上报。

## 五、展示层（tui/presentation）

| 模块 | 职责 |
| --- | --- |
| `primitives.py` | `RichLine` 等富文本原语（端口只用这些类型，不含引擎对象） |
| `blocks/` | 块模型：`message_blocks`、`tool_blocks`、`tool_lifecycle`、`subagent`（含 `subagent_glyphs`）、`errors` |
| `md_renderer.py` | Markdown → 富文本渲染 |
| `output.py` | 工具输出浏览/导出（对应 `/output` 命令） |
| `status*.py` | 状态栏分片：`status.py`、`status_footer`、`status_zones`、`status_context`、`status_clock`、`status_tool_counts`、`status_subagents` |
| `theme.py` | 主题与配色 |
| `subagent_result_stats.py` | Subagent 结果统计展示 |

## 六、命令体系（tui/commands）

- `parser.py`：`CommandSpec`/`Command`/`UnknownCommand`/`Literal` 与 `parse(text, registry)`；`default_registry()` 是命令表唯一事实源；`help_text(registry)` 生成 `/help` 全文。
- `dispatch.py`：命令分发（含 `picker` 类命令的候选列表）。
- `fuzzy.py`：`match_tier`（精确/前缀/子序列/编辑距离分层）与 `fuzzy_rank`，驱动输入框补全。
- `interaction.py`：`/sessions`、`/skills` 等交互式多步命令的状态机。
- `coordinator.py`：命令提交与运行态的协调（空闲/运行中可用命令不同）。
- `model_capabilities.py`、`status.py`、`skills.py`：`/model`、`/status`、`/skills` 的专用逻辑。
- `admin.py`：`/undo`、`/export`、`/subagents`、`/context-window` 与 `/mcp reload`；高权限动作经 `TuiAdminPort`（`ports/admin.py`）交组合根执行。
- `suggestions.py`、`registry.py`：补全浮层渲染与共享命令表实例，避免协调器之间循环 import。

命令总表（`default_registry()`，`*` 表示带交互 picker）：

| 命令 | 说明 |
| --- | --- |
| `/help` | 显示命令帮助 |
| `/ask`、`/plan`、`/code` | 以只读问答 / 只读规划 / 代码模式发送消息 |
| `/mode` | 设置粘性模式（ask/plan/code/auto） |
| `/clear` | 清空聊天区 |
| `/status` | 显示会话状态（含工具能力与模型能力） |
| `/name` | 设置或查看当前会话标题 |
| `/context` | 显示上下文预算与治理诊断 |
| `/sessions *` | 列出 / 搜索 / 筛选 / 归档 / 删除 / 恢复会话 |
| `/tree` | 展示会话 fork 链树；`/tree <id>` 切换 |
| `/tools` | 列出可用工具 |
| `/provider *` | 切换 provider |
| `/login *` | 配置 provider 的 API key 并切换（输入掩码） |
| `/model *` | 切换模型（支持 `model:effort`） |
| `/effort *` | 切换思考强度 |
| `/fork` | 从指定消息（缺省最近用户消息）分叉会话 |
| `/undo` | 查看或恢复写前快照（`list` / `preview`），与 `tenon undo` 同源 |
| `/export <path>` | 导出当前会话完整文档到文件 |
| `/subagents` | 查看并发上限与活跃委派；`cancel <delegation-id>` 终止单个委派 |
| `/context-window` | 查看或设置模型上下文窗口（写入 `models.json` 后热切换） |
| `/compact` | 压缩当前会话上下文 |
| `/output` | 浏览或导出最近工具输出 |
| `/retry` | 安全重试最近一次模型失败 |
| `/continue` | 在失败回合后继续新的消息 |
| `/skills` | 列出/加载技能或管理 Package（install/list/update/remove/reload） |
| `/mcp` | 列出 MCP server 与工具（含诊断）；`/mcp reload` 重建 MCP 与工具运行时 |
| `/quit` | 退出 TUI（等同 Ctrl+C） |

## 七、会话动作（tui/session）

| 模块 | 职责 |
| --- | --- |
| `conversation.py` | 消息提交、斜杠命令绑定、渲染回调 |
| `actions.py` / `action_runner.py` | 用户动作（切换 provider/model、压缩、fork、重试…）的执行与结果反馈 |
| `commands.py` | 会话级命令实现 |
| `coordinator.py` | 运行态与命令可用性的协调 |
| `restore.py` | 会话恢复与**恢复成本阈值** |

恢复成本（`restore.py`）：历史满足 `message_count > 1000`、`text_chars > 100_000` 或 `tool_output_bytes > 1_000_000` 任一条件时走后台恢复（`requires_background`），避免阻塞首帧；恢复过程中断可取消，恢复完成才重建模型视图。会话恢复与 TUI 模型重建不得丢失 `RuntimeExtensions`。

## 八、性能基准（tui/benchmark）

`fixture.py` 定义 5 个标准场景（`_SCENARIOS`）：

| 场景 | 观测目标 |
| --- | --- |
| `history` | 长历史下的视口物化与索引扫描（1000/5000/10000 blocks 扩展观察） |
| `stream` | 流式提交延迟、首 token 延迟、帧 p50/p95 |
| `tool-output` | 大工具输出渲染 |
| `restore` | 会话恢复耗时与内存 |
| `scroll-resize` | 滚动/缩放的控制事件 p95 延迟 |

`runner.py`/`performance.py` 输出 schema v2 报告（含 `blocks_inspected`、`blocks_materialized`、`index_updates`、`cache_entries`、`peak_memory_bytes` 等无内容计数器）。基线比较脚本为 `scripts/benchmark_tui.py`、`scripts/compare_benchmark.py`、`scripts/update_tui_baseline.py`；CI 的 performance 任务当前只告警不阻断。

## 九、设计约束

1. **引擎可替换**：视图逻辑只依赖 `TuiBackend`；Textual 类型只允许出现在 `adapters/textual/`。
2. **单向数据流**：事件 → `RuntimeReducer` → `TuiModel`/`Transcript` → 协调器 → 后端渲染；禁止视图直接修改领域状态。
3. **归约与展示分离**：状态归约是纯逻辑（可离线测试），渲染是投影。
4. **长会话有界**：视口物化 + 索引扫描 + 渐进渲染，基准用计数器而非"感觉"验证。
5. **失败路径可见**：命令失败（如 `/name` 校验失败、`/sessions` 存储失败）必须在 TUI 内反馈，且不得发起模型请求或改写聊天历史。

## 相关阅读

- 事件从哪来：[04-core-layer.md](./04-core-layer.md)、[05-session-layer.md](./05-session-layer.md)
- TUI 如何装配：[08-app-layer.md](./08-app-layer.md)
- 性能门禁与基准策略：[11-development-guide.md](./11-development-guide.md)