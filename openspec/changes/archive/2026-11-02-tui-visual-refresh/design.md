# TUI 视觉刷新设计

## 状态

- 阶段：已完成（已实现并归档）
- 范围：仅调整 TUI 呈现层视觉与样式词表，不改变消息语义、布局契约、交互行为或持久化格式。
- 关联主规格：`openspec/specs/tui/spec.md`（消息样式区分、终端背景融合、状态栏稳定布局）。

## Implementation Plan（决策完成）

### 1. 调色板与标签

文件：`src/tenon/app/tui/presentation/theme.py`

- 保留现有标签常量与 `PALETTE` 键，替换为高对比配色：
  - `TEXT #e6edf3`、`ACCENT #58a6ff`、`DIM #8b949e`、`TOOL_OUTPUT #b1bac4`
  - `SUCCESS #3fb950`、`ERROR #f85149`、`WARNING #d29922`
  - `STATUS_MODEL #79c0ff`、`STATUS_PATH #7ee787`
  - `USER_BG #1c2128`、`USER_PROMPT #79c0ff`、`ASSISTANT_PROMPT #3fb950`
  - `ACTIVITY #d29922`、`DIFF_ADD #1b4721`、`DIFF_REMOVE #5c1e22`、`DIFF_CONTEXT #30363d`
  - `BOLD #ffffff`、`CODE_BG #21262d`、`HEADING #d2a8ff`、`LIST_BULLET #79c0ff`、`BLOCK_MARK #6e7681`
- 新增标签与色值：
  - `COMPOSER_RULE #30363d`
  - `PROMPT #58a6ff`
  - `LOGIN_ACCENT #58a6ff`
  - `LOGIN_SURFACE #161b22`
  - `LOGIN_TEXT #e6edf3`
  - `LOGIN_HINT #8b949e`
- 同步更新 `__all__`。

### 2. 适配器去硬编码

文件：`src/tenon/app/tui/adapters/textual/widgets.py`

- 删除 `_LOGIN_ACCENT`、`_LOGIN_SURFACE`、`_COMPOSER_RULE` 常量，改为导入 `PALETTE` 与新增标签。
- 替换 `Rule` 颜色、`prompt` 颜色、`login_label` 颜色、`key_input` 背景/边框/正文色、`login_hint` 颜色，以及 `set_mask()` 中的强调/恢复颜色。

文件：`src/tenon/app/tui/adapters/textual/app.py`

- 删除模块级 `_LOGIN_SURFACE`，改为 `PALETTE[LOGIN_SURFACE]`。

### 3. 组件精修

文件：`src/tenon/app/tui/presentation/blocks/message_blocks.py`

- `ActivityBlock._FRAMES` 改为脉冲字形序列（`· ✢ ✳ ✶ ✻ ✽ ✻ ✶ ✳ ✢`），`render()` 输出“字形 + 思考中”，两段均使用 `ACTIVITY`。

文件：`src/tenon/app/tui/presentation/blocks/tool_blocks.py`

- pending 图标颜色由 `DIM` 改为 `WARNING`。
- 导入 `_cell_width`；`_intent_diff()` 每行追加与剩余宽度等长的背景补齐段（`bg=DIFF_ADD/DIFF_REMOVE/DIFF_CONTEXT`），保证连续色带。

文件：`src/tenon/app/tui/presentation/status_context.py`

- 新增 `_usage_tag(ratio)`：`<0.60` → `SUCCESS`，`<0.85` → `WARNING`，`>=0.85` → `ERROR`；未知用量仍用 `ACCENT`。
- 所有已有宽度分支的 meter/label 使用该结果。

### 4. 测试

文件：`tests/tui/test_textual_backend.py`

- 登录态颜色断言改为引用 `PALETTE[LOGIN_SURFACE]`、`PALETTE[LOGIN_ACCENT]`、`PALETTE[COMPOSER_RULE]`，避免再次锁定字面量。

文件：`tests/tui/test_components.py`

- 更新 `test_activity_block_has_low_frequency_frames`：断言新字形序列与 `ACTIVITY` 标签。
- 新增 pending 工具图标使用 `WARNING` 的断言。
- 新增 diff 行尾补齐背景段的断言（色带宽度等于渲染宽度）。
- 新增上下文占用在低/中/高比例下的 `SUCCESS`/`WARNING`/`ERROR` 标签断言。

### 5. 验证

```bash
uv run pytest tests/tui/test_components.py tests/tui/test_textual_backend.py tests/tui/test_semantic_snapshots.py tests/tui/test_status_bar_regression.py -q --basetemp=.pytest-tmp
uv run pytest tests/tui -q --basetemp=.pytest-tmp
uv run ruff check src tests
uv run ruff format --check src tests
uv run python scripts/scale_scan.py
git diff --check
```

## 非目标

- 不引入深色/浅色双主题、主题切换命令或 CSS 文件。
- 不改变 transcript 行数、状态栏区域宽度、消息纯文本快照、键位和事件协议。
- 不调整 Markdown 解析语义，仅通过调色板提升现有标签的对比度。
