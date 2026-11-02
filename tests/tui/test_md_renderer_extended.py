"""扩展 Markdown 结构(斜体/引用/表格/任务列表/高亮/链接/图片)离线断言。"""

import unicodedata

from tenon.app.tui.presentation.md_renderer import md_renderer
from tenon.app.tui.presentation.primitives import Span, rich_to_plain
from tenon.app.tui.presentation.theme import (
    BLOCK_MARK,
    BOLD,
    CODE_BG,
    CODE_COMMENT,
    CODE_KEYWORD,
    CODE_NUMBER,
    CODE_STRING,
    DIM,
    IMAGE,
    ITALIC,
    LINK,
    LIST_BULLET,
    QUOTE,
    SUCCESS,
    TABLE_BORDER,
    TABLE_HEADER,
    TEXT,
)


def _cells(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _spans(lines, fg: str) -> list[Span]:
    return [span for line in lines for span in line if span.fg == fg]


# -- 行内:斜体 / 链接 / 图片 --------------------------------------------------


def test_italic_uses_italic_tag_and_keeps_underscore_words_literal():
    lines = md_renderer("*斜体* 与 _另一处_ 以及 snake_case", 60)
    assert rich_to_plain(lines) == ["斜体 与 另一处 以及 snake_case"]
    italic = _spans(lines, ITALIC)
    assert [span.text for span in italic] == ["斜体", "另一处"]
    assert "snake_case" in "".join(rich_to_plain(lines))


def test_unclosed_italic_renders_literal():
    assert md_renderer("a *b", 60) == [[Span("a *b", fg=TEXT)]]


def test_markdown_link_carries_target_and_link_tag():
    lines = md_renderer("见 [文档](https://example.com/docs)", 60)
    span = next(span for line in lines for span in line if span.text == "文档")
    assert span.fg == LINK
    assert span.link == "https://example.com/docs"
    assert rich_to_plain(lines) == ["见 文档"]


def test_autolink_renders_url_as_clickable_text():
    lines = md_renderer("访问 <https://example.com>", 60)
    span = next(span for line in lines for span in line if span.fg == LINK)
    assert span.text == "https://example.com"
    assert span.link == "https://example.com"


def test_image_renders_placeholder_with_alt_and_url():
    lines = md_renderer("![架构图](https://example.com/a.png)", 60)
    image = _spans(lines, IMAGE)[0]
    assert image.text == "🖼 架构图"
    assert image.link == "https://example.com/a.png"
    url = _spans(lines, DIM)[0]
    assert url.text.strip() == "https://example.com/a.png"
    assert url.link == "https://example.com/a.png"


# -- 块级:引用 / 任务列表 / 表格 -----------------------------------------------


def test_blockquote_renders_bar_and_dims_body():
    lines = md_renderer("> 引用 **重点**", 40)
    assert lines[0][0] == Span("│ ", fg=QUOTE)
    assert [span.text for span in _spans(lines, BOLD)] == ["重点"]
    assert "引用" in "".join(s.text for s in lines[0])


def test_nested_blockquote_adds_bar_per_depth():
    lines = md_renderer("> > 嵌套引用", 40)
    assert lines[0][0].text == "│ │ "


def test_task_list_marks_checked_and_unchecked():
    lines = md_renderer("- [ ] 待办\n- [x] 已完成", 40)
    first, second = lines
    assert first[0] == Span("- ", fg=LIST_BULLET)
    assert first[1] == Span("☐ ", fg=DIM)
    assert second[1] == Span("☑ ", fg=SUCCESS)
    assert rich_to_plain(lines) == ["- ☐ 待办", "- ☑ 已完成"]


def test_pipe_table_renders_header_border_and_alignment():
    lines = md_renderer("| 名称 | 数量 |\n| :--- | ---: |\n| a | 1 |", 24)
    assert rich_to_plain(lines)[0] == "│ 名称 │ 数量 │"
    assert rich_to_plain(lines)[1].startswith("├")
    assert "┼" in rich_to_plain(lines)[1]
    assert _spans(lines, TABLE_HEADER)[0].text == "名称"
    assert _spans(lines, TABLE_BORDER)
    # 右对齐:数字前留白,行尾贴边框
    assert rich_to_plain(lines)[2] == "│ a    │    1 │"


def test_table_never_exceeds_viewport_width():
    body = "| 名称 | 说明 |\n| --- | --- |\n| a | 一段很长很长的说明文本 |"
    for width in (20, 30, 60):
        lines = md_renderer(body, width)
        assert all(
            _cells(rich_to_plain_line) <= width for rich_to_plain_line in rich_to_plain(lines)
        )


def test_table_falls_back_to_text_when_too_narrow():
    lines = md_renderer("| a | b |\n| --- | --- |\n| 1 | 2 |", 6)
    assert all("│" not in line for line in rich_to_plain(lines))


# -- 代码高亮 ----------------------------------------------------------------


def test_python_code_block_highlights_keyword_string_comment_number():
    body = '```python\ndef f(x):\n    # 说明\n    return "ok" + 1\n```'
    lines = md_renderer(body, 60)
    assert lines[0] == [Span("```python", fg=BLOCK_MARK)]
    keywords = {span.text for span in _spans(lines, CODE_KEYWORD)}
    assert {"def", "return"} <= keywords
    assert any(span.text == '"ok"' for span in _spans(lines, CODE_STRING))
    assert any(span.text.startswith("#") for span in _spans(lines, CODE_COMMENT))
    assert any(span.text == "1" for span in _spans(lines, CODE_NUMBER))
    assert all(span.bg == CODE_BG for line in lines[1:-1] for span in line)


def test_unknown_code_language_stays_plain():
    lines = md_renderer("```text\ndef x\n```", 60)
    assert all(span.fg == TEXT for span in lines[1])
    assert all(span.bg == CODE_BG for span in lines[1])


def test_unclosed_code_block_stays_plain_without_background():
    lines = md_renderer("```python\ndef x", 60)
    assert all(span.fg != CODE_KEYWORD for line in lines[1:] for span in line)
    assert all(span.bg is None for line in lines[1:] for span in line)
