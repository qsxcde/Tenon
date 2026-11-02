"""Markdown 行内结构解析与按 cell 宽度换行。

行内结构(加粗/斜体/行内代码/链接/图片/自动链接)统一在这里解析,输出
受控样式标签;块级渲染器只负责组合这些片段。
"""

from __future__ import annotations

from .primitives import RichLine, Span, _cell_width, _seg
from .theme import BOLD, CODE_BG, DIM, IMAGE, ITALIC, LINK, TEXT

__all__ = ["IMAGE_GLYPH", "merge_spans", "parse_inline", "wrap_segments"]

#: 图片占位字形(终端不展示真实图片,只显示替代文本)。
IMAGE_GLYPH = "🖼"


def merge_spans(spans: list[Span]) -> RichLine:
    """把相邻同样式片段合并,避免逐字符段膨胀。"""
    line: RichLine = []
    for span in spans:
        if (
            line
            and line[-1].fg == span.fg
            and line[-1].bg == span.bg
            and line[-1].link == span.link
        ):
            last = line[-1]
            line[-1] = Span(last.text + span.text, fg=last.fg, bg=last.bg, link=last.link)
        else:
            line.append(span)
    return line


def wrap_segments(segs: list[Span], width: int) -> list[RichLine]:
    """按 cell 宽度换行并保留段内样式(断点空白不落行首)。"""
    width = max(1, width)
    chars = [Span(ch, fg=seg.fg, bg=seg.bg, link=seg.link) for seg in segs for ch in seg.text]
    lines: list[RichLine] = []
    current: list[Span] = []
    current_w = 0
    for char in chars:
        char_w = _cell_width(char.text)
        if current and current_w + char_w > width:
            lines.append(merge_spans(current))
            current = []
            current_w = 0
            if char.text == " ":
                continue  # 断点空白不落入行首(近似 drop_whitespace)
        current.append(char)
        current_w += char_w
    if current:
        lines.append(merge_spans(current))
    return lines


def _link_target(raw: str) -> str:
    """去掉可选标题(``url "title"``)后返回链接目标。"""
    return raw.strip().split(" ", 1)[0]


def _parse_image(text: str, start: int) -> tuple[list[Span], int] | None:
    end_alt = text.find("]", start + 2)
    if end_alt == -1 or text[end_alt + 1 : end_alt + 2] != "(":
        return None
    end_url = text.find(")", end_alt + 2)
    if end_url == -1:
        return None
    alt = text[start + 2 : end_alt].strip()
    url = _link_target(text[end_alt + 2 : end_url])
    label = alt or url
    if not label:
        return None
    spans = [_seg(f"{IMAGE_GLYPH} {label}", fg=IMAGE, link=url or None)]
    if alt and url:
        spans.append(_seg(f"  {url}", fg=DIM, link=url))
    return spans, end_url + 1


def _parse_link(text: str, start: int) -> tuple[list[Span], int] | None:
    end_text = text.find("]", start + 1)
    if end_text == -1 or text[end_text + 1 : end_text + 2] != "(":
        return None
    end_url = text.find(")", end_text + 2)
    if end_url == -1:
        return None
    label = text[start + 1 : end_text]
    if not label:
        return None
    url = _link_target(text[end_text + 2 : end_url])
    return [_seg(label, fg=LINK, link=url or None)], end_url + 1


def _italic_end(text: str, start: int) -> int:
    """返回斜体闭合位置;``-1`` 表示不构成斜体(宽容为字面量)。"""
    delim = text[start]
    if start + 1 >= len(text) or text[start + 1].isspace():
        return -1
    if delim == "_" and start > 0 and text[start - 1].isalnum():
        return -1  # snake_case 内的下划线不算强调
    for index in range(start + 1, len(text)):
        if text[index] != delim or text[index - 1].isspace():
            continue
        if delim == "*" and index + 1 < len(text) and text[index + 1] == "*":
            continue
        if delim == "_" and index + 1 < len(text) and text[index + 1].isalnum():
            continue
        if index == start + 1:
            continue  # 空内容不是斜体
        return index
    return -1


def _autolink(text: str, start: int) -> tuple[list[Span], int] | None:
    end = text.find(">", start + 1)
    if end == -1:
        return None
    inner = text[start + 1 : end]
    if not inner.startswith(("http://", "https://")):
        return None
    return [_seg(inner, fg=LINK, link=inner)], end + 1


def parse_inline(text: str) -> list[Span]:
    """单遍扫描行内结构;未闭合结构按字面量宽容渲染。"""
    segs: list[Span] = []
    plain: list[str] = []
    index = 0
    length = len(text)

    def flush() -> None:
        if plain:
            segs.append(_seg("".join(plain), fg=TEXT))
            plain.clear()

    while index < length:
        if text[index] == "`":
            end = text.find("`", index + 1)
            if end == -1:
                break
            flush()
            segs.append(_seg(text[index + 1 : end], fg=TEXT, bg=CODE_BG))
            index = end + 1
        elif text.startswith("![", index):
            parsed = _parse_image(text, index)
            if parsed is None:
                plain.append(text[index])
                index += 1
            else:
                flush()
                segs.extend(parsed[0])
                index = parsed[1]
        elif text[index] == "[":
            parsed = _parse_link(text, index)
            if parsed is None:
                plain.append(text[index])
                index += 1
            else:
                flush()
                segs.extend(parsed[0])
                index = parsed[1]
        elif text.startswith("**", index):
            end = text.find("**", index + 2)
            if end == -1:
                break
            flush()
            segs.append(_seg(text[index + 2 : end], fg=BOLD))
            index = end + 2
        elif text[index] in "*_":
            end = _italic_end(text, index)
            if end == -1:
                plain.append(text[index])
                index += 1
            else:
                flush()
                segs.append(_seg(text[index + 1 : end], fg=ITALIC))
                index = end + 1
        elif text[index] == "<":
            parsed = _autolink(text, index)
            if parsed is None:
                plain.append(text[index])
                index += 1
            else:
                flush()
                segs.extend(parsed[0])
                index = parsed[1]
        else:
            plain.append(text[index])
            index += 1
    plain.append(text[index:])  # 未闭合结构的剩余部分按字面量
    flush()
    return segs
