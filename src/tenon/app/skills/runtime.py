"""Tenon-specific Skill Adapter and Bootstrap lifecycle state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .models import Skill

BOOTSTRAP_TAG = "<tenon_bootstrap>"
ADAPTER_VERSION = "tenon-v1"

#: 未注入工具清单时的保守默认(基础八工具);能力由注入的实际工具名派生,
#: 本模块不 import tools(app/skills 分层约束),清单由组合根传入。
_DEFAULT_TOOL_NAMES = ("read", "write", "edit", "bash", "grep", "find", "ls", "skill")


class TenonAdapter:
    """Translate Superpowers' abstract actions to Tenon capabilities."""

    _TOOLS = (
        ("read files", "read"),
        ("write files", "write"),
        ("edit files", "edit"),
        ("run shell commands", "bash"),
        ("search file contents", "grep"),
        ("find files", "find"),
        ("list files", "ls"),
        ("invoke a skill", "skill"),
        ("fetch web content", "web_fetch"),
        ("search the web", "web_search"),
        ("track task todos", "todo"),
    )

    def __init__(self, tool_names: Iterable[str] | None = None) -> None:
        names = frozenset(_DEFAULT_TOOL_NAMES if tool_names is None else tool_names)
        capabilities = {
            name: name in names
            for name in ("read", "write", "edit", "bash", "grep", "find", "ls", "skill")
        }
        capabilities["subagents"] = True
        capabilities["todo"] = "todo" in names
        capabilities["web"] = {"web_fetch", "web_search"} <= names
        self._capabilities = capabilities

    @property
    def version(self) -> str:
        return ADAPTER_VERSION

    def tool_mapping(self) -> str:
        lines = ["Tenon 工具映射:"]
        lines.extend(f"- {action} -> `{tool}`" for action, tool in self._TOOLS)
        lines.append("- subagent dispatch -> 使用 `delegate` 委派只读任务给独立子 Agent")
        if self._capabilities["todo"]:
            lines.append("- todo/task tracking -> 使用 `todo` 提交完整任务清单(整体替换)")
        else:
            lines.append("- todo/task tracking -> 当前不可用,使用计划或 TODO 文件降级")
        if self._capabilities["web"]:
            lines.append("- web fetch/search -> `web_fetch` 抓取 URL,`web_search` 检索(需用户确认)")
        else:
            lines.append("- web fetch/search -> 当前不可用,不得调用不存在的工具")
        return "\n".join(lines)

    def capabilities(self) -> dict[str, bool]:
        return dict(self._capabilities)

    def select_bootstrap(self, skills: Iterable[Skill]) -> Skill | None:
        return next((skill for skill in skills if skill.bootstrap), None)

    def render_bootstrap(self, skill: Skill) -> str:
        return (
            f"{BOOTSTRAP_TAG}\n"
            f"适配器版本: {self.version}\n"
            f"Bootstrap Skill: {skill.name}\n"
            "以下 Bootstrap 是当前会话的强制工作流入口。\n\n"
            f"{skill.content}\n\n"
            f"{self.tool_mapping()}\n"
            "</tenon_bootstrap>"
        )


def build_bootstrap_prompt(
    base: str, skills: Iterable[Skill], tool_names: Iterable[str] | None = None
) -> str:
    """Append the one selected bootstrap without preloading ordinary skills."""

    adapter = TenonAdapter(tool_names=tool_names)
    bootstrap = adapter.select_bootstrap(skills)
    if bootstrap is None:
        return base
    return f"{base}\n\n{adapter.render_bootstrap(bootstrap)}"


@dataclass
class SkillRuntimeState:
    """Session/context dedup state exposed to status and lifecycle callers."""

    adapter_version: str = ADAPTER_VERSION
    bootstrap_name: str | None = None
    _claimed_contexts: set[str] = field(default_factory=set)

    def claim(self, context_id: str) -> bool:
        if context_id in self._claimed_contexts:
            return False
        self._claimed_contexts.add(context_id)
        return True

    def reset(self, context_id: str | None = None) -> None:
        if context_id is None:
            self._claimed_contexts.clear()
        else:
            self._claimed_contexts.discard(context_id)

    def status(self) -> dict[str, object]:
        return {
            "adapter": self.adapter_version,
            "bootstrap": self.bootstrap_name,
            "contexts": len(self._claimed_contexts),
        }
