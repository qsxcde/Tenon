## 1. 调色板与语义标签

- [x] 1.1 `src/tenon/app/tui/presentation/theme.py`：替换 `PALETTE` 为高对比配色，保留全部现有标签键。
- [x] 1.2 `theme.py`：新增 `COMPOSER_RULE`、`PROMPT`、`LOGIN_ACCENT`、`LOGIN_SURFACE`、`LOGIN_TEXT`、`LOGIN_HINT`，并同步 `__all__`。

## 2. 适配器去除硬编码

- [x] 2.1 `adapters/textual/widgets.py`：删除 `_LOGIN_ACCENT`/`_LOGIN_SURFACE`/`_COMPOSER_RULE`，composer 与登录态颜色改取 `PALETTE`。
- [x] 2.2 `adapters/textual/app.py`：删除 `_LOGIN_SURFACE`，登录输入背景改取 `PALETTE[LOGIN_SURFACE]`。

## 3. 组件视觉精修

- [x] 3.1 `blocks/message_blocks.py`：`ActivityBlock` 改为低频脉冲字形序列。
- [x] 3.2 `blocks/tool_blocks.py`：pending 图标改用 `WARNING`；intent diff 行补齐全宽背景色带。
- [x] 3.3 `status_context.py`：上下文占用按使用率映射 `SUCCESS`/`WARNING`/`ERROR`，未知用量保持 `ACCENT`。

## 4. 测试同步

- [x] 4.1 `tests/tui/test_textual_backend.py`：登录态颜色断言改为引用 `PALETTE`。
- [x] 4.2 `tests/tui/test_components.py`：更新活动帧断言；新增 pending 色、diff 色带、上下文占用色断言。
- [x] 4.3 确认工具块与状态栏纯文本快照测试保持不变。

## 5. 验证

- [x] 5.1 运行目标测试：`uv run pytest tests/tui/test_components.py tests/tui/test_textual_backend.py tests/tui/test_semantic_snapshots.py tests/tui/test_status_bar_regression.py -q --basetemp=.pytest-tmp`
- [x] 5.2 运行 TUI 分层测试：`uv run pytest tests/tui -q --basetemp=.pytest-tmp`
- [x] 5.3 运行 `uv run ruff check src tests`。
- [x] 5.4 运行 `uv run ruff format --check src tests`。
- [x] 5.5 运行 `uv run python scripts/scale_scan.py`。
- [x] 5.6 运行 `git diff --check`，并核对无临时文件、无敏感信息。

## 6. 收尾

- [x] 6.1 报告修改文件、验证结论与未验证项（如 Windows 下 type_scan 的已知 POSIX 误报）。
- [x] 6.2 按默认策略不归档本 change、不提交 commit；归档留待用户后续决定。
