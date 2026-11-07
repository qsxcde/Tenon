# tui Delta Specification

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
