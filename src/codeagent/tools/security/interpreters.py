"""解释器识别:带版本号的名字与组合标志的内联代码判定。

`python3.12 -c ...` 和 `bash -lc '...'` 与 `python -c`、`bash -c` 等价,
但原实现用精确集合匹配首 token、用字面 `-c` 匹配标志,两种写法都会漏判。
本模块只做纯字符串归一化,不涉及执行。
"""

from __future__ import annotations

import re

__all__ = [
    "INTERPRETER_FAMILIES",
    "INLINE_FLAGS",
    "inline_code_index",
    "interpreter_family",
]

#: 家族名 → 该家族接受的内联代码标志(短标志按字符簇匹配)。
INTERPRETER_FAMILIES: dict[str, frozenset[str]] = {
    "bash": frozenset({"c"}),
    "sh": frozenset({"c"}),
    "zsh": frozenset({"c"}),
    "ksh": frozenset({"c"}),
    "dash": frozenset({"c"}),
    "python": frozenset({"c"}),
    "node": frozenset({"e", "p"}),
    "perl": frozenset({"e", "E"}),
    "ruby": frozenset({"e"}),
    "php": frozenset({"r"}),
    "lua": frozenset({"e"}),
    "awk": frozenset({"e"}),
    "gawk": frozenset({"e"}),
    "osascript": frozenset({"e"}),
    "Rscript": frozenset({"e"}),
}

#: 长选项形式的"内联代码"标志。
INLINE_FLAGS: frozenset[str] = frozenset({"--eval", "--execute", "--command"})

_VERSION_SUFFIX = re.compile(r"[0-9]+(?:\.[0-9]+)*$")


def interpreter_family(token: str) -> str | None:
    """返回解释器家族名;不是解释器时返回 `None`。

    去掉目录前缀与版本号后缀:`/usr/bin/python3.12` → `python`,
    `node20` → `node`。
    """
    if not token:
        return None
    name = token.replace("\\", "/").rsplit("/", 1)[-1]
    if name in INTERPRETER_FAMILIES:
        return name
    stripped = _VERSION_SUFFIX.sub("", name)
    if stripped and stripped != name and stripped in INTERPRETER_FAMILIES:
        return stripped
    return None


def inline_code_index(segment: list[str], start: int = 0) -> int | None:
    """返回内联代码参数的下标;没有内联代码标志时返回 `None`。

    `start` 指向解释器自身;其后的标志按"短标志字符簇"匹配(`-lc` 含 `c`),
    长选项按完整匹配。`--` 之后不再视为标志。
    """
    if start >= len(segment):
        return None
    family = interpreter_family(segment[start])
    if family is None:
        return None
    accepted = INTERPRETER_FAMILIES[family]
    for index in range(start + 1, len(segment)):
        token = segment[index]
        if token == "--":
            return None
        if token in INLINE_FLAGS:
            return index + 1 if index + 1 < len(segment) else None
        if not token.startswith("-") or token.startswith("--") or token == "-":
            continue
        cluster = token[1:]
        if any(character in accepted for character in cluster):
            return index + 1 if index + 1 < len(segment) else None
    return None
