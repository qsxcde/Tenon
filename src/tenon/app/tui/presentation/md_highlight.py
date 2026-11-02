"""轻量代码语法高亮:关键字/字符串/注释/数字,输出受控样式标签。

只做单行词法扫描,不引入解析器或第三方高亮库;未知语言保持纯文本,
保证流式渲染与性能边界可控。
"""

from __future__ import annotations

from .md_inline import merge_spans, wrap_segments
from .primitives import RichLine, Span, _seg, _wrap
from .theme import (
    CODE_BG,
    CODE_COMMENT,
    CODE_KEYWORD,
    CODE_NUMBER,
    CODE_STRING,
    TEXT,
)

__all__ = ["render_code_line"]

_LANG_ALIASES: dict[str, str] = {
    "py": "python",
    "python": "python",
    "js": "javascript",
    "jsx": "javascript",
    "javascript": "javascript",
    "ts": "typescript",
    "tsx": "typescript",
    "typescript": "typescript",
    "json": "json",
    "sh": "bash",
    "shell": "bash",
    "bash": "bash",
    "rs": "rust",
    "rust": "rust",
}

_COMMENT_PREFIX: dict[str, tuple[str, ...]] = {
    "python": ("#",),
    "javascript": ("//",),
    "typescript": ("//",),
    "bash": ("#",),
    "rust": ("//",),
}

_PYTHON_KEYWORDS = frozenset(
    """
    and as assert async await break class continue def del elif else except finally for
    from global if import in is lambda match nonlocal not or pass raise return try yield
    True False None self
    """.split()
)
_JS_KEYWORDS = frozenset(
    """
    async await break case catch class const continue default delete do else export extends
    false finally for from function if import in instanceof let new null of return static
    super switch this throw true try typeof undefined var void while yield
    """.split()
)
_BASH_KEYWORDS = frozenset(
    """
    case do done elif else esac fi for function if in select then time until while
    """.split()
)
_RUST_KEYWORDS = frozenset(
    """
    as async await break const continue crate dyn else enum extern false fn for if impl in
    let loop match mod move mut pub ref return self static struct super trait true type
    unsafe use where while
    """.split()
)

_LANG_KEYWORDS: dict[str, frozenset[str]] = {
    "python": _PYTHON_KEYWORDS,
    "javascript": _JS_KEYWORDS,
    "typescript": _JS_KEYWORDS,
    "json": frozenset({"true", "false", "null"}),
    "bash": _BASH_KEYWORDS,
    "rust": _RUST_KEYWORDS,
}


def normalize_language(info: str) -> str:
    """把围栏语言标记(如 ``python title=x``)归一化为语言名。"""
    token = info.strip().split(" ", 1)[0].lower()
    return _LANG_ALIASES.get(token, "")


def _string_end(text: str, start: int, quote: str) -> int:
    index = start + 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index + 1
        index += 1
    return len(text)  # 未闭合字符串:高亮到行尾(宽容)


def _number_end(text: str, start: int) -> int:
    index = start
    while index < len(text) and (text[index].isdigit() or text[index] == "."):
        index += 1
    return index


def _ident_end(text: str, start: int) -> int:
    index = start
    while index < len(text) and (text[index].isalnum() or text[index] == "_"):
        index += 1
    return index


def _highlight(line: str, language: str) -> list[Span]:
    keywords = _LANG_KEYWORDS.get(language)
    if keywords is None:
        return [_seg(line, fg=TEXT, bg=CODE_BG)]
    comments = _COMMENT_PREFIX.get(language, ())
    spans: list[Span] = []
    plain: list[str] = []
    index = 0

    def flush() -> None:
        if plain:
            spans.append(_seg("".join(plain), fg=TEXT, bg=CODE_BG))
            plain.clear()

    while index < len(line):
        if any(line.startswith(prefix, index) for prefix in comments):
            flush()
            spans.append(_seg(line[index:], fg=CODE_COMMENT, bg=CODE_BG))
            break
        char = line[index]
        if char in "\"'`":
            flush()
            end = _string_end(line, index, char)
            spans.append(_seg(line[index:end], fg=CODE_STRING, bg=CODE_BG))
            index = end
        elif char.isdigit():
            flush()
            end = _number_end(line, index)
            spans.append(_seg(line[index:end], fg=CODE_NUMBER, bg=CODE_BG))
            index = end
        elif char.isalpha() or char == "_":
            flush()
            end = _ident_end(line, index)
            word = line[index:end]
            tag = CODE_KEYWORD if word in keywords else TEXT
            spans.append(_seg(word, fg=tag, bg=CODE_BG))
            index = end
        else:
            plain.append(char)
            index += 1
    flush()
    return merge_spans(spans)


def render_code_line(line: str, width: int, language: str, *, background: bool) -> list[RichLine]:
    """渲染一行代码;``background=False``(流式未闭合)保持纯文本无背景。"""
    if not background:
        return [[_seg(part, fg=TEXT)] for part in _wrap(line, width)]
    return wrap_segments(_highlight(line, normalize_language(language)), width)
