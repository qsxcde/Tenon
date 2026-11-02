# TUI 视觉刷新（高对比现代终端风）

## 状态

- 阶段：待批准（Proposed）
- 范围：仅调整 TUI 呈现层视觉与样式词表，不改变消息语义、布局契约、交互行为或持久化格式。
- 关联主规格：`openspec/specs/tui/spec.md`（消息样式区分、终端背景融合、状态栏稳定布局）。

## 背景

当前 TUI 已具备受控样式标签与统一调色板，但存在三个可改进点：

1. 调色板偏低对比（正文 `#d4d4d4`、次级 `#666666`），工具输出与状态信息层级不够清晰。
2. 适配器层仍硬编码登录/输入区颜色（`#39d9ff`、`#171a1d`、`#5a5a5a`、`#8a9198` 等），换肤需改代码。
3. 动态反馈仅有三帧省略号，状态栏上下文占用与 diff 行的视觉提示较弱。

用户已确认方向：统一配色并换肤、精修核心组件、增加动态细节；风格为“高对比现代终端风”；不做深色/浅色双主题切换。

## ADDED Requirements

### Requirement: 高对比视觉词表

TUI 呈现层 SHALL 提供一套高对比现代终端风的受控样式标签与色值；所有组件与 Textual 适配器 SHALL 只引用词表中的标签，不得硬编码 hex 色值。新增标签 SHALL 覆盖 composer 分隔线、输入提示符、登录态强调色/表面色/正文色/提示色。调色板 SHALL 保持现有标签键不变，新增键 SHALL 同时出现在 `__all__` 与 `PALETTE`。

#### Scenario: 样式标签完整覆盖

- **WHEN** 测试遍历 `theme.__all__` 中的样式标签
- **THEN** 每个标签都能在 `PALETTE` 中找到色值，且 `PALETTE` 不含词表外的键

#### Scenario: 适配器无硬编码颜色

- **WHEN** 检查 `adapters/textual/widgets.py` 与 `adapters/textual/app.py`
- **THEN** composer、登录输入与登录提示的颜色均来自 `PALETTE`，不再出现字面量 hex

### Requirement: 核心组件视觉层级

TUI SHALL 在保持现有布局、文本快照与交互行为不变的前提下精修核心组件：

- 用户消息保持全宽连续背景，提示符使用高对比强调色；
- 助手正文提示符使用与用户提示符可区分的强调色；
- 工具调用 pending 图标使用警告色，完成/失败分别使用成功/错误色；
- 编辑/写入的 intent diff 行背景 SHALL 铺满终端宽度，形成连续色带；
- 状态栏上下文占用 SHALL 按使用率着色（低占用成功色、中占用警告色、高占用错误色），未知用量保持强调色；
- composer 分隔线与提示符 SHALL 使用词表中的低对比分隔色和强调色。

#### Scenario: 工具状态色可区分

- **WHEN** 同一行分别渲染 pending、done、error 工具块
- **THEN** 状态图标分别使用 warning、success、error 标签，文字摘要保持既有纯文本快照

#### Scenario: diff 连续色带

- **WHEN** 展开 edit/write 工具块的 intent diff
- **THEN** 新增/删除/上下文行在文本之后补齐同背景色的空格，色带宽度与渲染宽度一致

#### Scenario: 上下文占用着色

- **WHEN** 状态栏渲染已知上下文用量
- **THEN** 使用率低于 60% 使用 success，60% 至 85% 使用 warning，85% 及以上使用 error；未知用量仍使用 accent

### Requirement: 低频动态提示

等待模型/思考阶段的活动提示 SHALL 使用低频脉冲字形动画，保持约 0.45 秒一帧，不引入高频刷新；活动提示隐藏时动画任务 SHALL 停止并释放。动画 SHALL 只改变字形，不改变活动提示的纯文本语义。

#### Scenario: 活动提示逐帧变化

- **WHEN** 连续推进活动帧
- **THEN** 字形按词表顺序变化且始终包含“思考中”

#### Scenario: 隐藏即停止

- **WHEN** `activity_visible` 变为 False
- **THEN** 动画任务停止，后续帧不再触发渲染

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
