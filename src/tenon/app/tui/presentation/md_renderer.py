"""app/tui/presentation/md_renderer.py:Markdown 正文渲染入口(无状态纯函数)。

设计(design T-46;spec「Markdown 正文渲染」):
- ``md_renderer(text, width) -> list[RichLine]``:单遍线性扫描,输出受控样式
  标签(theme 词表),不产生 ANSI;
- 块级结构:标题/列表/任务列表/引用/表格/代码块;行内结构:加粗/斜体/行内
  代码/链接/图片/自动链接(由 ``md_inline`` 解析);
- 代码块按围栏语言做轻量高亮(未知语言保持纯文本);
- 宽容策略:未闭合结构按已识别部分渲染(不抛错、不渲染错误背景);代码块以
  「完整块才上背景」为界,流式中间帧显示文本即可,终态自然完整;
- 超长退化:正文超过阈值(可注入)退化为纯文本,保护 NFR-P5 帧率;
- 经 ``AssistantBlock(md_renderer=...)`` 注入(仿 clock 模式),离线测试注入桩
  或直接断言输出标签序列。

分层约束:本模块只 import primitives(数据类型/换行设施)、md_* 子模块与
theme(词表),禁止 import textual/终端;components 对本模块**延迟导入**以避开
循环依赖。
"""

from __future__ import annotations

import re

from .md_blocks import is_quote_line, render_line, render_quote
from .md_highlight import render_code_line
from .md_table import detect_table, render_table
from .primitives import RichLine, _seg, _wrap
from .theme import BLOCK_MARK, TEXT

__all__ = ["md_renderer", "MAX_MD_RENDER_LEN"]

#: 超长退化阈值(字符数):超过即按纯文本渲染(design D3,保护 NFR-P5)。
MAX_MD_RENDER_LEN = 20_000

#: 代码块围栏:行首(允许缩进)的连续反引号/波浪号,后可跟语言名(闭合同样匹配)。
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")


def _fence_language(info: str) -> str:
    """取围栏信息串中的语言标记(忽略附加参数)。"""
    stripped = info.strip()
    return stripped.split(" ", 1)[0] if stripped else ""


def _flush_code(
    out: list[RichLine], buffered: list[str], language: str, width: int, *, background: bool
) -> None:
    for line in buffered:
        out.extend(render_code_line(line, width, language, background=background))
    buffered.clear()


def md_renderer(text: str, width: int, max_len: int = MAX_MD_RENDER_LEN) -> list[RichLine]:
    """把 Agent 正文渲染为受控样式行(单遍线性扫描;宽容 + 超长退化)。"""
    width = max(1, width)
    if not text.strip():
        return []
    if len(text) > max_len:
        return [[_seg(line, fg=TEXT)] for line in _wrap(text, width)]
    lines = text.split("\n")
    out: list[RichLine] = []
    code_buf: list[str] = []
    fence = ""
    language = ""
    index = 0
    while index < len(lines):
        raw = lines[index]
        if fence:
            if _FENCE_RE.match(raw):
                # 闭合:先输出已缓冲的代码行(上背景),再输出闭合围栏。
                _flush_code(out, code_buf, language, width, background=True)
                fence = ""
                language = ""
                out.append([_seg(raw, fg=BLOCK_MARK)])
            else:
                code_buf.append(raw)
            index += 1
            continue
        fence_match = _FENCE_RE.match(raw)
        if fence_match:
            fence = fence_match.group(1)
            language = _fence_language(fence_match.group(2))
            out.append([_seg(raw, fg=BLOCK_MARK)])
            index += 1
            continue
        if is_quote_line(raw):
            quote_lines: list[str] = []
            while index < len(lines) and is_quote_line(lines[index]):
                quote_lines.append(lines[index])
                index += 1
            out.extend(render_quote(quote_lines, width))
            continue
        table = detect_table(lines, index)
        if table is not None:
            header, aligns, rows, end = table
            out.extend(render_table(header, aligns, rows, width))
            index = end
            continue
        out.extend(render_line(raw, width))
        index += 1
    if fence:
        # 流式中间帧:围栏未闭合 → 缓冲行按纯文本渲染,不上背景(design D2)。
        _flush_code(out, code_buf, language, width, background=False)
    return out
