"""Provider-neutral token estimation shared by budgeting and compaction.

`len(text) // 4` is an English-centric assumption: one CJK character is
usually one token (sometimes more), so a Chinese-heavy conversation was
estimated at roughly a quarter of its real size, which made preflight
`over_limit` unreachable and compaction targets inaccurate.

Pure-ASCII text keeps the exact legacy arithmetic (`len // 4`, once per
message) so existing budgets and English-heavy tests do not shift; CJK
characters are counted individually and remaining non-ASCII characters at
two per token. Absent a provider tokenizer this stays a deterministic,
documented approximation.
"""

from __future__ import annotations

__all__ = [
    "ASCII_CHARS_PER_TOKEN",
    "WIDE_CHARS_PER_TOKEN",
    "count_tokens",
    "estimate_text_tokens",
    "is_cjk",
]

#: CJK 码点区间:汉字、假名、谚文、CJK 标点与全角形式。
_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x1100, 0x11FF),  # Hangul Jamo
    (0x2E80, 0x2EFF),  # CJK Radicals Supplement
    (0x3000, 0x303F),  # CJK Symbols and Punctuation
    (0x3040, 0x30FF),  # Hiragana + Katakana
    (0x3130, 0x318F),  # Hangul Compatibility Jamo
    (0x3400, 0x4DBF),  # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0xA960, 0xA97F),  # Hangul Jamo Extended-A
    (0xAC00, 0xD7AF),  # Hangul Syllables
    (0xF900, 0xFAFF),  # CJK Compatibility Ideographs
    (0xFF00, 0xFFEF),  # Halfwidth and Fullwidth Forms
    (0x20000, 0x2FA1F),  # CJK Extensions B~F and Compatibility Supplement
)

#: 普通字符每 token 字符数(与历史口径一致)。
ASCII_CHARS_PER_TOKEN = 4
#: 其它非 ASCII 字符每 token 字符数。
WIDE_CHARS_PER_TOKEN = 2


def is_cjk(character: str) -> bool:
    """Return whether one character belongs to a CJK block."""
    code = ord(character)
    return any(start <= code <= end for start, end in _CJK_RANGES)


def count_tokens(characters: int, cjk: int, wide: int = 0) -> int:
    """Combine character counts into an estimate.

    Aggregating first and dividing once keeps pure-ASCII results identical to
    the legacy `len // 4`口径, while CJK characters are charged individually.
    """
    tokens = cjk + characters // ASCII_CHARS_PER_TOKEN + wide // WIDE_CHARS_PER_TOKEN
    return max(1, tokens)


def estimate_text_tokens(value: str) -> int:
    """Estimate tokens for one text, counting CJK characters individually."""
    if not value:
        return 0
    cjk = 0
    wide = 0
    other = 0
    for character in value:
        code = ord(character)
        if code < 0x80:
            other += 1
        elif is_cjk(character):
            cjk += 1
        else:
            wide += 1
    return count_tokens(other, cjk, wide)
