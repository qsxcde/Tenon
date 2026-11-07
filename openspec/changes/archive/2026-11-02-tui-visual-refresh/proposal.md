# TUI 视觉刷新（高对比现代终端风）

## Why

当前 TUI 已具备受控样式标签与统一调色板，但存在三个可改进点：

1. 调色板偏低对比（正文 `#d4d4d4`、次级 `#666666`），工具输出与状态信息层级不够清晰。
2. 适配器层仍硬编码登录/输入区颜色（`#39d9ff`、`#171a1d`、`#5a5a5a`、`#8a9198` 等），换肤需改代码。
3. 动态反馈仅有三帧省略号，状态栏上下文占用与 diff 行的视觉提示较弱。

用户已确认方向：统一配色并换肤、精修核心组件、增加动态细节；风格为“高对比现代终端风”；不做深色/浅色双主题切换。

## What Changes

- **高对比视觉词表**：`theme.py` 替换 `PALETTE` 为高对比配色，新增 composer 分隔线、输入提示符与登录态标签，`__all__` 与 `PALETTE` 同步。
- **适配器去硬编码**：`adapters/textual/widgets.py` 与 `adapters/textual/app.py` 的 composer / 登录态颜色改为引用 `PALETTE`。
- **核心组件视觉层级**：消息提示符、工具状态色、intent diff 连续色带、状态栏上下文占用着色与 composer 分隔线统一取词表标签。
- **低频动态提示**：活动提示改为约 0.45 秒一帧的脉冲字形，隐藏时停止动画任务。
- **测试同步**：颜色断言改为引用 `PALETTE`，新增工具状态色、diff 色带、上下文占用色与活动帧断言。

## Capabilities

### Modified Capabilities

- `tui`：新增「高对比视觉词表」「核心组件视觉层级」「低频动态提示」三项呈现层要求；不改变消息语义、布局契约、交互行为或持久化格式。

## Impact

- 影响文件：`src/tenon/app/tui/presentation/theme.py`、`status_context.py`、`blocks/message_blocks.py`、`blocks/tool_blocks.py`、`adapters/textual/widgets.py`、`adapters/textual/app.py` 与对应测试。
- 不涉及 core、session、ai、tools 层，不改变事件协议与公开接口。

## 非目标

- 不引入深色/浅色双主题、主题切换命令或 CSS 文件。
- 不改变 transcript 行数、状态栏区域宽度、消息纯文本快照、键位和事件协议。
- 不调整 Markdown 解析语义，仅通过调色板提升现有标签的对比度。
