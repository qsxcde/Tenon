"""默认的 ask 档命令规则：识别需要用户确认的高影响操作。

规则集与分类流程分属两种职责：这里只描述"哪些命令形态需要询问"及其人类可读
理由，判定顺序和 deny 优先级由 ``classifier.classify_bash`` 负责。
"""

from __future__ import annotations

from typing import Callable

from codeagent.tools.security.interpreters import (
    INTERPRETER_FAMILIES,
    inline_code_index,
    interpreter_family,
)

__all__ = ["INTERPRETER_WRAPPERS", "default_ask_rules", "flags_of"]

#: 家族名集合;带版本号的名字由 :func:`interpreter_family` 归一后再判断。
INTERPRETER_WRAPPERS = frozenset(INTERPRETER_FAMILIES)

AskRule = tuple[Callable[[list[list[str]]], bool], str]
SegmentsMatcher = Callable[[list[list[str]]], bool]


def flags_of(tokens: list[str]) -> list[str]:
    """Collect flag tokens of one segment until the ``--`` separator."""
    flags: list[str] = []
    for token in tokens[1:]:
        if token == "--":
            break
        if token.startswith("-"):
            flags.append(token)
    return flags


def _recursive_flag(segment: list[str]) -> bool:
    return any("r" in flag.lstrip("-").lower() for flag in flags_of(segment))


def _matches_git(sub: str, extra: str | None = None) -> SegmentsMatcher:
    def match(segments: list[list[str]]) -> bool:
        segment = segments[-1]
        if len(segment) < 2 or segment[0] != "git" or segment[1] != sub:
            return False
        return extra is None or extra in segment

    return match


def _git_clean(segments: list[list[str]]) -> bool:
    segment = segments[-1]
    if len(segment) < 2 or segment[0] != "git" or segment[1] != "clean":
        return False
    return any("f" in flag.lstrip("-") for flag in flags_of(segment))


def _rm_recursive(segments: list[list[str]]) -> bool:
    segment = segments[-1]
    return bool(segment and segment[0] == "rm") and _recursive_flag(segment)


def _chmod_recursive(segments: list[list[str]]) -> bool:
    segment = segments[-1]
    return bool(segment) and segment[0] in ("chmod", "chown") and _recursive_flag(segment)


def _find_delete_exec(segments: list[list[str]]) -> bool:
    segment = segments[-1]
    return bool(segment) and segment[0] == "find" and ("-delete" in segment or "-exec" in segment)


def _dd_write_device(segments: list[list[str]]) -> bool:
    segment = segments[-1]
    return (
        bool(segment)
        and segment[0] == "dd"
        and any(token.startswith("of=/dev/") for token in segment[1:])
    )


def _sudo(segments: list[list[str]]) -> bool:
    return bool(segments[-1]) and segments[-1][0] == "sudo"


def _kill_process(segments: list[list[str]]) -> bool:
    return bool(segments[-1]) and segments[-1][0] in ("kill", "pkill", "killall")


def _nested_shell(segments: list[list[str]]) -> bool:
    """嵌套 shell:家族名(含版本号)内联代码,如 `bash -lc '...'`。"""
    segment = segments[-1]
    if not segment or interpreter_family(segment[0]) not in {"bash", "sh", "zsh", "ksh", "dash"}:
        return False
    return inline_code_index(segment, 0) is not None


def _interpreter_inline(segments: list[list[str]]) -> bool:
    """任意解释器家族(含版本号)的内联代码,如 `python3.12 -c ...`。"""
    segment = segments[-1]
    if not segment or interpreter_family(segment[0]) is None:
        return False
    return inline_code_index(segment, 0) is not None


def _encoded_pipeline(segments: list[list[str]]) -> bool:
    for index, segment in enumerate(segments[:-1]):
        if not segment or segment[0] != "base64":
            continue
        if not any(flag in {"-d", "--decode"} for flag in segment[1:]):
            continue
        next_segment = segments[index + 1]
        if next_segment and interpreter_family(next_segment[0]) is not None:
            return True
    return False


def _xargs_execution(segments: list[list[str]]) -> bool:
    return bool(segments[-1]) and segments[-1][0] == "xargs"


def _is_system_path(value: str) -> bool:
    return (
        value.replace("\\", "/")
        .lower()
        .startswith(("/etc/", "/boot/", "/sys/", "/usr/", "/var/lib/"))
    )


def _system_redirect(segments: list[list[str]]) -> bool:
    for segment in segments:
        for index, token in enumerate(segment[:-1]):
            if token not in {">", ">>", ">|"}:
                continue
            if _is_system_path(segment[index + 1]):
                return True
    return False


def _tee_system_path(segments: list[list[str]]) -> bool:
    return any(
        segment and segment[0] == "tee" and any(_is_system_path(token) for token in segment[1:])
        for segment in segments
    )


def _volume_value(token: str, following: list[str]) -> str:
    if token in {"-v", "--volume"} and following:
        return following[0]
    if token.startswith("-v") and ":" in token:
        return token[2:].lstrip("=")
    if token.startswith("--volume="):
        return token.split("=", 1)[1]
    if token.startswith("--mount") and "src=/" in token:
        return "/:/"
    return ""


def _docker_root_mount(segments: list[list[str]]) -> bool:
    for segment in segments:
        if not segment or segment[0] != "docker" or "run" not in segment[1:]:
            continue
        for index, token in enumerate(segment[1:], start=1):
            value = _volume_value(token, segment[index + 1 :])
            if value.split(":", 1)[0] in {"/", "\\"}:
                return True
    return False


def _tar_root_extract(segments: list[list[str]]) -> bool:
    return any(
        segment
        and segment[0] == "tar"
        and any(
            token in {"-C", "--directory"} or token.startswith(("-C/", "--directory=/"))
            for token in segment[1:]
        )
        and any(token == "/" or token.endswith("=/") for token in segment[1:])
        for segment in segments
    )


def _awk_system_call(segments: list[list[str]]) -> bool:
    return any(
        segment
        and segment[0] in {"awk", "gawk"}
        and any("system" in token.lower() for token in segment[1:])
        for segment in segments
    )


def _mv_overwrite(exists: Callable[[str], bool] | None) -> SegmentsMatcher:
    def match(segments: list[list[str]]) -> bool:
        segment = segments[-1]
        if not segment or segment[0] != "mv" or exists is None:
            return False
        targets = [token for token in segment[1:] if not token.startswith("-") and token != "--"]
        return len(targets) >= 2 and exists(targets[-1])

    return match


def default_ask_rules(
    exists: Callable[[str], bool] | None,
) -> list[AskRule]:
    """Build the ordered ask-tier rules with their human-readable reasons."""
    return [
        (_matches_git("push"), "推送远程分支"),
        (_matches_git("reset", "--hard"), "丢弃工作区改动(reset --hard)"),
        (_git_clean, "删除未跟踪文件(git clean)"),
        (_sudo, "提权执行(sudo)"),
        (_chmod_recursive, "递归修改权限/属主(-R)"),
        (_rm_recursive, "递归删除(rm -r)"),
        (_find_delete_exec, "find 删除/执行(-delete/-exec)"),
        (_dd_write_device, "写入块设备(dd of=/dev/..." + ")"),
        (_nested_shell, "嵌套 shell 执行(-c)"),
        (_interpreter_inline, "解释器内联代码(-c)"),
        (_encoded_pipeline, "编码数据管道进入解释器"),
        (_xargs_execution, "xargs 间接批量执行"),
        (_system_redirect, "写入系统目录"),
        (_tee_system_path, "tee 写入系统文件"),
        (_docker_root_mount, "容器挂载主机根目录"),
        (_tar_root_extract, "解包覆盖文件系统根目录"),
        (_awk_system_call, "awk 间接执行外部命令"),
        (_kill_process, "终止进程"),
        (_mv_overwrite(exists), "覆盖已有文件(mv)"),
    ]
