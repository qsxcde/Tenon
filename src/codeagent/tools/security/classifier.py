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
    _READ_TOOLS,
    _SEARCH_TOOLS,
    _secret_path_hit,
    classify_file,
)
from codeagent.tools.security.mcp import classify_mcp
from codeagent.tools.security.shell_parse import (
    split_segments,
)
from codeagent.tools.security.wrappers import effective_segment
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

#: 网络出站工具:出站访问统一进 ask 档(headless 无确认通道时 fail-closed)。
_NETWORK_TOOLS: frozenset[str] = frozenset({"web_fetch", "web_search"})


def _split_segments(command: str) -> list[list[str]]:
    """Use the same parser as bash_rules; malformed syntax fails closed there."""

    return split_segments(command) or [[command.strip()]]


def _rule_candidates(segments: list[list[str]]) -> list[list[str]]:
    """Yield both the raw and the wrapper-stripped view of every segment.

    Ask-tier rules are written against `segment[0]`:

    - `sudo` / `xargs` rules need the **raw** view (the wrapper is the risk);
    - `rm -r` / `git push` rules need the **effective** view, otherwise
      `timeout 5 rm -r` hides the real command behind the wrapper.

    Checking both views keeps existing rules intact and closes the prefix
    bypass without rewriting each rule.
    """
    candidates: list[list[str]] = []
    for segment in segments:
        if segment:
            candidates.append(segment)
        effective = effective_segment(segment)
        if effective and effective != segment:
            candidates.append(effective)
    return candidates


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
    raw_segments = _split_segments(command)
    # 敏感路径检查覆盖原始 token(含包装器参数),避免 `env cat .env` 漏判。
    secret_hit = _secret_path_hit(raw_segments)
    if secret_hit is not None:
        return SecurityDecision(DENY, secret_hit)
    candidates = _rule_candidates(raw_segments)
    allow = allowlist if allowlist is not None else DEFAULT_ALLOWLIST
    rules = ask_rules if ask_rules is not None else default_ask_rules(exists)
    for segment in candidates:
        for match, reason in rules:
            if match([segment]):
                return SecurityDecision(ASK, reason)
    effective_segments = [effective_segment(segment) or segment for segment in raw_segments]
    for match, reason in rules:
        if match(effective_segments) or match(raw_segments):
            return SecurityDecision(ASK, reason)
    if _download_to_shell(candidates):
        return SecurityDecision(ASK, "网络下载并执行(curl|sh 类)")
    if all(
        _matches_allowlist(segment, allow) or _matches_allowlist(effective, allow)
        for segment, effective in zip(raw_segments, effective_segments)
    ):
        return SecurityDecision(ALLOW)
    return SecurityDecision(ALLOW)


def classify_tool(
    tool_name: str,
    args: dict,
    *,
    workspace: str | Path,
    cwd: str | None = None,
    exists: Callable[[str], bool] | None = None,
    mcp_rules=None,
    ext_rules=None,
) -> SecurityDecision:
    if tool_name == "bash":
        return classify_bash(str(args.get("command", "")), cwd=cwd, exists=exists)
    if tool_name in _NETWORK_TOOLS:
        return SecurityDecision(ASK, "网络出站访问(web)")
    if tool_name in _BOUNDED_TOOLS:
        raw = str(args.get("file_path", ""))
        if raw:
            return classify_file(tool_name, resolve_to_cwd(raw, cwd), workspace)
    if tool_name in _SEARCH_TOOLS:
        # 只读搜索工具与 read 共享同一边界:界内放行、界外放行并警告、敏感路径拒绝。
        raw = str(args.get("path") or args.get("file_path") or "")
        if raw:
            return classify_file(tool_name, resolve_to_cwd(raw, cwd), workspace)
    if tool_name.startswith("mcp__"):
        return classify_mcp(tool_name, mcp_rules)
    if tool_name.startswith("ext__"):
        # 插件工具 fail-closed:无显式 allow 规则即需确认(headless 无确认通道时拒绝)。
        decision = ext_rules.decide(tool_name) if ext_rules is not None else None
        if decision == "deny":
            return SecurityDecision(DENY, "插件工具被权限规则拒绝")
        if decision == "allow":
            return SecurityDecision(ALLOW)
        return SecurityDecision(ASK, "插件工具默认需确认(ext)")
    return SecurityDecision(ALLOW)


__all__ = ["DEFAULT_ALLOWLIST", "classify_bash", "classify_tool"]
