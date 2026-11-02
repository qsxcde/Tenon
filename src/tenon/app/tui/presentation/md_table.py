"""Markdown 管道表格解析与等宽渲染。

表格按终端可用宽度分配列宽;超出宽度时优先压缩最宽列,仍放不下则退化为
普通文本行,保证不产生横向溢出。
"""

from __future__ import annotations

import re

from .md_inline import parse_inline, wrap_segments
from .primitives import RichLine, Span, _cell_width, _seg, _truncate
from .theme import TABLE_BORDER, TABLE_HEADER, TEXT

__all__ = ["detect_table", "render_table", "split_cells"]

_SEP_CELL_RE = re.compile(r"^:?-+:?$")


def split_cells(raw: str) -> list[str]:
    """拆分一行表格单元格,去掉首尾管道并还原 ``\\|``。"""
    text = raw.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip().replace("\\|", "|") for cell in text.split("|")]


def _alignment(cell: str) -> str:
    cell = cell.strip()
    if cell.startswith(":") and cell.endswith(":"):
        return "center"
    if cell.endswith(":"):
        return "right"
    return "left"


def detect_table(
    lines: list[str], start: int
) -> tuple[list[str], list[str], list[list[str]], int] | None:
    """识别从 ``start`` 开始的表格,返回表头/对齐/数据行与结束下标。"""
    if start + 1 >= len(lines):
        return None
    header = lines[start]
    separator = lines[start + 1]
    if "|" not in header or "|" not in separator:
        return None
    header_cells = split_cells(header)
    separator_cells = split_cells(separator)
    if len(header_cells) != len(separator_cells):
        return None
    if not all(_SEP_CELL_RE.match(cell) for cell in separator_cells):
        return None
    aligns = [_alignment(cell) for cell in separator_cells]
    rows: list[list[str]] = []
    end = start + 2
    while end < len(lines) and lines[end].strip() and "|" in lines[end]:
        rows.append(split_cells(lines[end]))
        end += 1
    return header_cells, aligns, rows, end


def _fit_widths(widths: list[int], budget: int) -> list[int]:
    """把自然列宽压缩到预算内(优先压缩最宽列,最小宽度 1)。"""
    if sum(widths) <= budget:
        return widths
    scale = budget / sum(widths)
    fitted = [max(1, int(width * scale)) for width in widths]
    while sum(fitted) > budget:
        widest = max(range(len(fitted)), key=lambda index: fitted[index])
        if fitted[widest] <= 1:
            break
        fitted[widest] -= 1
    return fitted


def _cell_content(cell: str, width: int, *, header: bool) -> tuple[list[Span], int]:
    """返回单元格内容与可见宽度;超宽时丢弃行内样式并截断。"""
    if header:
        text = _truncate(cell, width)
        return [_seg(text, fg=TABLE_HEADER)], _cell_width(text)
    spans = parse_inline(cell)
    plain = "".join(span.text for span in spans)
    if _cell_width(plain) <= width:
        return spans, _cell_width(plain)
    text = _truncate(plain, width)
    return [_seg(text, fg=TEXT)], _cell_width(text)


def _row_line(cells: list[str], aligns: list[str], widths: list[int], *, header: bool) -> RichLine:
    line: RichLine = [_seg("│", fg=TABLE_BORDER)]
    for index, (cell, align, col_width) in enumerate(zip(cells, aligns, widths)):
        content, used = _cell_content(cell, col_width, header=header)
        pad = max(0, col_width - used)
        before = pad if align == "right" else pad // 2 if align == "center" else 0
        line.append(_seg(" ", fg=TABLE_BORDER))
        if before:
            line.append(_seg(" " * before))
        line.extend(content)
        if pad - before:
            line.append(_seg(" " * (pad - before)))
        line.append(_seg(" ", fg=TABLE_BORDER))
        if index < len(widths) - 1:
            line.append(_seg("│", fg=TABLE_BORDER))
    line.append(_seg("│", fg=TABLE_BORDER))
    return line


def _separator_line(widths: list[int]) -> RichLine:
    line = "├" + "┼".join("─" * (width + 2) for width in widths) + "┤"
    return [_seg(line, fg=TABLE_BORDER)]


def _fallback(header: list[str], rows: list[list[str]], width: int) -> list[RichLine]:
    lines: list[RichLine] = []
    for cells in [header, *rows]:
        lines.extend(wrap_segments(parse_inline(" | ".join(cells)), width))
    return lines


def render_table(
    header: list[str], aligns: list[str], rows: list[list[str]], width: int
) -> list[RichLine]:
    """把表格渲染为等宽边框行;宽度不足时退化为文本行。"""
    columns = len(header)
    if columns == 0:
        return []
    normalized = [
        (row + [""] * columns)[:columns] if len(row) != columns else row for row in [*rows]
    ]
    widths = [
        max(_cell_width(cells[column]) for cells in [header, *normalized])
        for column in range(columns)
    ]
    budget = width - (3 * columns + 1)
    if budget < columns:
        return _fallback(header, normalized, width)
    fitted = _fit_widths(widths, budget)
    lines = [_row_line(header, aligns, fitted, header=True), _separator_line(fitted)]
    lines.extend(_row_line(row, aligns, fitted, header=False) for row in normalized)
    return lines
