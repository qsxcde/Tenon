"""Markdown 行级块渲染:标题、列表、任务列表、引用与普通段落。"""

from __future__ import annotations

import re

from .md_inline import parse_inline, wrap_segments
from .primitives import RichLine, Span, _seg
from .theme import DIM, HEADING, LIST_BULLET, QUOTE, SUCCESS, TEXT

__all__ = ["is_quote_line", "quote_depth", "render_line", "render_quote"]

#: 标题:行首 1~6 个 #(宽容:不要求必须跟空格)。
_HEADING_RE = re.compile(r"^\s*(#{1,6})\s*(.*)$")
#: 列表项:``- `` / ``* `` / ``+ `` / ``1. `` / ``1) ``(数字最多 9 位)。
_LIST_RE = re.compile(r"^\s*([-*+]|\d{1,9}[.)])\s+(.*)$")
#: 任务列表:``- [ ]`` / ``- [x]``。
_TASK_RE = re.compile(r"^\s*([-*+])\s+\[( |x|X)\]\s+(.*)$")


def is_quote_line(raw: str) -> bool:
    """行首(最多 3 个空格)是否为引用标记。"""
    return quote_depth(raw) > 0


def quote_depth(raw: str) -> int:
    """返回引用嵌套深度;0 表示不是引用行。"""
    text = raw.lstrip()
    depth = 0
    while text.startswith(">"):
        depth += 1
        text = text[1:]
        if text.startswith(" "):
            text = text[1:]
    return depth


def _quote_text(raw: str, depth: int) -> str:
    text = raw
    for _ in range(depth):
        stripped = text.lstrip()
        stripped = stripped[1:]
        text = stripped[1:] if stripped.startswith(" ") else stripped
    return text


def _quote_body(text: str) -> list[Span]:
    """引用正文统一压暗,同时保留行内代码/加粗等强调。"""
    return [
        span if span.fg != TEXT else Span(span.text, fg=QUOTE, bg=span.bg, link=span.link)
        for span in parse_inline(text)
    ]


def render_quote(lines: list[str], width: int) -> list[RichLine]:
    """渲染连续引用行:每行一个竖线前缀,正文按可用宽度换行。"""
    rendered: list[RichLine] = []
    for raw in lines:
        depth = max(1, quote_depth(raw))
        prefix = "│ " * depth
        prefix_width = 2 * depth
        body = _quote_text(raw, depth)
        inner_width = max(1, width - prefix_width)
        spans = _quote_body(body)
        wrapped = wrap_segments(spans, inner_width) if spans else [[]]
        for line in wrapped:
            rendered.append([_seg(prefix, fg=QUOTE), *line])
    return rendered


def render_line(raw: str, width: int) -> list[RichLine]:
    """渲染一行非代码围栏/表格/引用的正文。"""
    if not raw.strip():
        return [[]]  # 空行保留占位(与纯文本渲染一致)
    task = _TASK_RE.match(raw)
    if task:
        marker, state, body = task.group(1), task.group(2), task.group(3)
        checked = state.lower() == "x"
        segs = [
            _seg(marker + " ", fg=LIST_BULLET),
            _seg("☑ " if checked else "☐ ", fg=SUCCESS if checked else DIM),
            *parse_inline(body),
        ]
        return wrap_segments(segs, width)
    heading = _HEADING_RE.match(raw)
    if heading:
        return wrap_segments([_seg(heading.group(2), fg=HEADING)], width)
    item = _LIST_RE.match(raw)
    if item:
        segs = [_seg(item.group(1) + " ", fg=LIST_BULLET), *parse_inline(item.group(2))]
        return wrap_segments(segs, width)
    return wrap_segments(parse_inline(raw), width)
