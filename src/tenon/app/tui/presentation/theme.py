"""app/tui/presentation/theme.py:样式标签词表 + 调色板(hex,非 ANSI)。

设计(design D2):组件只输出**受控样式标签**(数据),不依赖 textual/ANSI;色值
集中在此,后端(textual)把标签映射成 Rich style;换自研引擎只换映射,组件零改动。
测试断言标签序列,不碰 ANSI(spec「样式标签可离线断言」)。

调色板参考 Pi-Agent dark 主题(userMessageBg / toolPendingBg / thinkingText / accent…)。
"""

from __future__ import annotations

__all__ = [
    "PALETTE",
    "TEXT",
    "ACCENT",
    "DIM",
    "TOOL_OUTPUT",
    "SUCCESS",
    "ERROR",
    "WARNING",
    "STATUS_MODEL",
    "STATUS_PATH",
    "USER_BG",
    "USER_PROMPT",
    "ASSISTANT_PROMPT",
    "ACTIVITY",
    "DIFF_ADD",
    "DIFF_REMOVE",
    "DIFF_CONTEXT",
    "BOLD",
    "ITALIC",
    "CODE_BG",
    "HEADING",
    "LIST_BULLET",
    "BLOCK_MARK",
    "QUOTE",
    "LINK",
    "IMAGE",
    "TABLE_BORDER",
    "TABLE_HEADER",
    "CODE_KEYWORD",
    "CODE_STRING",
    "CODE_COMMENT",
    "CODE_NUMBER",
    "COMPOSER_RULE",
    "PROMPT",
    "LOGIN_ACCENT",
    "LOGIN_SURFACE",
    "LOGIN_TEXT",
    "LOGIN_HINT",
]

# -- 样式标签(受控词表) ---------------------------------------------------

TEXT = "text"  # 正文(Agent 回答)
ACCENT = "accent"  # 强调:工具名、输入 ❯、聚焦边框
DIM = "dim"  # 次级:思维标题、参数、footer
TOOL_OUTPUT = "tool_output"  # 工具结果
SUCCESS = "success"  # 成功(工具 ✓ / 空闲状态)
ERROR = "error"  # 错误(工具 ✗ / 错误状态)
WARNING = "warning"  # 警告(已取消 / 运行中状态)
STATUS_MODEL = "status_model"  # 状态栏模型/思考强度
STATUS_PATH = "status_path"  # 状态栏工作目录
USER_BG = "user_bg"  # 用户消息整行背景
USER_PROMPT = "user_prompt"  # 用户消息提示符
ASSISTANT_PROMPT = "assistant_prompt"  # 助手正文提示符
ACTIVITY = "activity"  # 等待动画
DIFF_ADD = "diff_add"  # 差异新增行背景
DIFF_REMOVE = "diff_remove"  # 差异删除行背景
DIFF_CONTEXT = "diff_context"  # 差异上下文
BOLD = "bold"  # Markdown 加粗(引擎映射为字重,色值兜底)
ITALIC = "italic"  # Markdown 斜体(引擎映射为字重,色值兜底)
CODE_BG = "code_bg"  # Markdown 行内代码/代码块背景
HEADING = "heading"  # Markdown 标题
LIST_BULLET = "list_bullet"  # Markdown 列表标记
BLOCK_MARK = "block_mark"  # Markdown 代码块围栏(``` / ~~~)
QUOTE = "quote"  # Markdown 引用块竖线与正文
LINK = "link"  # Markdown 超链接文本(映射为下划线 + OSC 8)
IMAGE = "image"  # Markdown 图片占位
TABLE_BORDER = "table_border"  # Markdown 表格边框/分隔线
TABLE_HEADER = "table_header"  # Markdown 表格表头
CODE_KEYWORD = "code_keyword"  # 代码高亮:关键字
CODE_STRING = "code_string"  # 代码高亮:字符串
CODE_COMMENT = "code_comment"  # 代码高亮:注释
CODE_NUMBER = "code_number"  # 代码高亮:数字/字面量
COMPOSER_RULE = "composer_rule"  # composer 上下分隔线
PROMPT = "prompt"  # composer 输入提示符
LOGIN_ACCENT = "login_accent"  # 登录态强调色(分隔线/KEY 标签)
LOGIN_SURFACE = "login_surface"  # 登录输入条表面色
LOGIN_TEXT = "login_text"  # 登录输入正文
LOGIN_HINT = "login_hint"  # 登录操作提示

#: 标签 → 色值(hex;目前均为前景色,背景色由后端按需使用词表)。
PALETTE: dict[str, str] = {
    TEXT: "#e6edf3",
    ACCENT: "#58a6ff",
    DIM: "#8b949e",
    TOOL_OUTPUT: "#b1bac4",
    SUCCESS: "#3fb950",
    ERROR: "#f85149",
    WARNING: "#d29922",
    STATUS_MODEL: "#79c0ff",
    STATUS_PATH: "#7ee787",
    USER_BG: "#1c2128",
    USER_PROMPT: "#79c0ff",
    ASSISTANT_PROMPT: "#3fb950",
    ACTIVITY: "#d29922",
    DIFF_ADD: "#1b4721",
    DIFF_REMOVE: "#5c1e22",
    DIFF_CONTEXT: "#30363d",
    BOLD: "#ffffff",
    ITALIC: "#e6edf3",
    CODE_BG: "#21262d",
    HEADING: "#d2a8ff",
    LIST_BULLET: "#79c0ff",
    BLOCK_MARK: "#6e7681",
    QUOTE: "#8b949e",
    LINK: "#79c0ff",
    IMAGE: "#d2a8ff",
    TABLE_BORDER: "#6e7681",
    TABLE_HEADER: "#79c0ff",
    CODE_KEYWORD: "#ff7b72",
    CODE_STRING: "#a5d6ff",
    CODE_COMMENT: "#8b949e",
    CODE_NUMBER: "#79c0ff",
    COMPOSER_RULE: "#30363d",
    PROMPT: "#58a6ff",
    LOGIN_ACCENT: "#58a6ff",
    LOGIN_SURFACE: "#161b22",
    LOGIN_TEXT: "#e6edf3",
    LOGIN_HINT: "#8b949e",
}
