"""定位 shell 片段真正执行的命令(包装器与赋值前缀的语义跳过)。

危险意图判定必须作用在"实际会运行的那条命令"上,而不是 `segment[0]`。
原实现用一张固定名单跳过首 token,漏掉了 `timeout`/`nice`/`xargs` 等包装器,
而且跳过 `env` 后没有跳过它的参数,导致 `env -i rm -rf /tmp/x` 把 `-i`
当成真正的命令。

本模块只做纯字符串判断,不依赖文件系统、不启动子进程。
"""

from __future__ import annotations

import re

__all__ = [
    "ASSIGNMENT_RE",
    "WRAPPER_COMMANDS",
    "effective_command_index",
    "effective_segment",
]

#: `VAR=value` 前缀(命令前的环境变量赋值,不是命令本身)。
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

#: 会接管并转发执行的 POSIX 包装器。它们自身的参数不是真正的命令。
WRAPPER_COMMANDS: frozenset[str] = frozenset(
    {
        "sudo",
        "env",
        "time",
        "nohup",
        "command",
        "builtin",
        "exec",
        "stdbuf",
        "nice",
        "timeout",
        "xargs",
    }
)

#: 每个包装器中"后面还跟一个参数值"的选项。
_VALUE_OPTIONS: dict[str, frozenset[str]] = {
    "sudo": frozenset(
        {"-u", "-g", "-p", "-C", "-D", "-r", "-t", "-U", "-h", "-R", "-T", "-a", "-c"}
    ),
    "env": frozenset({"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}),
    "stdbuf": frozenset({"-i", "-o", "-e", "--input", "--output", "--error"}),
    "nice": frozenset({"-n", "--adjustment"}),
    "timeout": frozenset({"-s", "--signal", "-k", "--kill-after"}),
    "xargs": frozenset(
        {"-I", "-n", "-P", "-L", "-s", "-d", "-E", "-a", "--max-args", "--max-procs"}
    ),
    "time": frozenset({"-f", "--format", "-o", "--output"}),
}

#: 包装器在命令前额外接收的固定操作数个数(如 timeout 的时长)。
_OPERANDS: dict[str, int] = {"timeout": 1}


def _is_option(token: str) -> bool:
    return token.startswith("-") and token != "-" and token != "--"


def _skip_wrapper(segment: list[str], index: int) -> int | None:
    """跳过一个包装器及其选项/操作数,返回下一个候选下标;None = 无法判定。"""
    wrapper = segment[index]
    if wrapper not in WRAPPER_COMMANDS:
        return index
    cursor = index + 1
    values = _VALUE_OPTIONS.get(wrapper, frozenset())
    while cursor < len(segment):
        token = segment[cursor]
        if token == "--":
            cursor += 1
            break
        if not _is_option(token):
            break
        inline_value = any(token.startswith(option + "=") for option in values)
        cursor += 2 if (token in values or inline_value) and not inline_value else 1
    for _ in range(_OPERANDS.get(wrapper, 0)):
        if cursor < len(segment) and not _is_option(segment[cursor]):
            cursor += 1
    return cursor


def effective_command_index(segment: list[str]) -> int:
    """返回该片段真正执行命令的下标;越界表示"没有可执行命令"。

    无法可靠判定时返回 `len(segment)`,调用方据此按"无命令"处理并由
    危险意图与 ask 规则各自决定是否需要保守拒绝。
    """
    index = 0
    passthrough_seen = 0
    while index < len(segment):
        token = segment[index]
        if ASSIGNMENT_RE.match(token):
            index += 1
            continue
        if token in WRAPPER_COMMANDS:
            following = _skip_wrapper(segment, index)
            if following is None:
                return len(segment)
            if following == index:
                break
            index = following
            passthrough_seen += 1
            if passthrough_seen > len(WRAPPER_COMMANDS) + 1:
                return len(segment)
            continue
        break
    return min(index, len(segment))


def effective_segment(segment: list[str]) -> list[str]:
    """返回包装器与赋值前缀之后的片段(不含这些前导 token)。"""
    return segment[effective_command_index(segment) :]
