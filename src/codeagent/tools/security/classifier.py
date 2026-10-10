"""Bash 与工具统一安全分类器。

判定顺序（deny > ask > allow）属于分类流程；ask 档规则本身拆到
``ask_rules.default_ask_rules``，避免本模块同时承载流程与规则清单。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from codeagent.tools.security.ask_rules import default_ask_rules
from codeagent.tools.security.bash_rules import (
    _dangerous_hit,
    _dangerous_intent,
)
from codeagent.tools.security.decision import ALLOW, ASK, DENY, SecurityDecision
from codeagent.tools.security.filesystem import (
    _BOUNDED_TOOLS,
    _secret_path_hit,
    classify_file,
)
from codeagent.tools.security.mcp import classify_mcp
from codeagent.tools.security.shell_parse import (
    split_segments,
)
from codeagent.tools.shared import resolve_to_cwd

DEFAULT_ALLOWLIST: tuple[str, ...] = (
    "ls",
    "cat",
    "grep",
    "pwd",
    "echo",
    "head",
    "tail",
    "which",
    "git status",
    "git diff",
    "git log",
    "git show",
)


def _split_segments(command: str) -> list[list[str]]:
    """Use the same parser as bash_rules; malformed syntax fails closed there."""

    return split_segments(command) or [[command.strip()]]


def _matches_allowlist(tokens: list[str], allowlist: tuple[str, ...]) -> bool:
    for entry in allowlist:
        entry_tokens = entry.split()
        if len(tokens) >= len(entry_tokens) and tokens[: len(entry_tokens)] == entry_tokens:
            return True
    return False


def _download_to_shell(segments: list[list[str]]) -> bool:
    for index in range(len(segments) - 1):
        if not segments[index] or not segments[index + 1]:
            continue
        if segments[index][0] in ("curl", "wget") and segments[index + 1][0] in (
            "sh",
            "bash",
            "zsh",
        ):
            return True
    return False


def classify_bash(
    command: str,
    *,
    cwd: str | None = None,
    allowlist: tuple[str, ...] | None = None,
    ask_rules: list[tuple[Callable[[list[list[str]]], bool], str]] | None = None,
    exists: Callable[[str], bool] | None = None,
) -> SecurityDecision:
    command = command.strip()
    if not command:
        return SecurityDecision(ALLOW)
    hit = _dangerous_hit(command) or _dangerous_intent(command, cwd)
    if hit is not None:
        return SecurityDecision(DENY, f"命令命中危险模式: {hit}")
    segments = _split_segments(command)
    secret_hit = _secret_path_hit(segments)
    if secret_hit is not None:
        return SecurityDecision(DENY, secret_hit)
    allow = allowlist if allowlist is not None else DEFAULT_ALLOWLIST
    rules = ask_rules if ask_rules is not None else default_ask_rules(exists)
    for segment in segments:
        if not segment:
            continue
        for match, reason in rules:
            if match([segment]):
                return SecurityDecision(ASK, reason)
        if _matches_allowlist(segment, allow):
            continue
    for match, reason in rules:
        if match(segments):
            return SecurityDecision(ASK, reason)
    if _download_to_shell(segments):
        return SecurityDecision(ASK, "网络下载并执行(curl|sh 类)")
    return SecurityDecision(ALLOW)


def classify_tool(
    tool_name: str,
    args: dict,
    *,
    workspace: str | Path,
    cwd: str | None = None,
    exists: Callable[[str], bool] | None = None,
    mcp_rules=None,
) -> SecurityDecision:
    if tool_name == "bash":
        return classify_bash(str(args.get("command", "")), cwd=cwd, exists=exists)
    if tool_name in _BOUNDED_TOOLS:
        raw = str(args.get("file_path", ""))
        if raw:
            return classify_file(tool_name, resolve_to_cwd(raw, cwd), workspace)
    if tool_name.startswith("mcp__"):
        return classify_mcp(tool_name, mcp_rules)
    return SecurityDecision(ALLOW)


__all__ = ["DEFAULT_ALLOWLIST", "classify_bash", "classify_tool"]
