"""三级工具权限规则的共享匹配与解析(deny > ask > allow)。

MCP(`mcp__<server>__<tool>`)与插件(`ext__<id>__<tool>`)命名空间共用同一
glob 语义:`<前缀>__*` 前缀族、`a__b` 单层前缀、精确名。
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "ThreeTierPermissionRules",
    "match_tool_rule",
    "normalize_rule",
    "parse_three_tier_block",
]


@dataclass(frozen=True)
class ThreeTierPermissionRules:
    """三级权限规则;decide 返回命中档位,无命中返回 None(fail-closed 由调用方决定)。"""

    deny: tuple[str, ...] = ()
    ask: tuple[str, ...] = ()
    allow: tuple[str, ...] = ()

    @classmethod
    def empty(cls) -> "ThreeTierPermissionRules":
        return cls()

    def decide(self, qualified_name: str) -> str | None:
        normalized = normalize_rule(qualified_name)
        for action in ("deny", "ask", "allow"):
            if any(
                match_tool_rule(normalized, normalize_rule(rule)) for rule in getattr(self, action)
            ):
                return action
        return None


def normalize_rule(text: str) -> str:
    return text.strip().lower().replace("-", "_").replace(".", "_")


def match_tool_rule(name: str, rule: str) -> bool:
    if rule.endswith("__*"):
        prefix = rule[:-3]
        return name.startswith(prefix + "__")
    if rule.count("__") == 1:
        return name.startswith(rule + "__")
    return name == rule


def parse_three_tier_block(permissions: object) -> ThreeTierPermissionRules:
    """从配置中的 permissions 块解析三级规则;缺失或非法返回空规则。"""
    if not isinstance(permissions, dict):
        return ThreeTierPermissionRules.empty()
    rules: dict[str, tuple[str, ...]] = {}
    for action in ("deny", "ask", "allow"):
        entries = permissions.get(action, [])
        if not isinstance(entries, list):
            continue
        rules[action] = tuple(
            entry for entry in entries if isinstance(entry, str) and entry.strip()
        )
    return ThreeTierPermissionRules(
        deny=rules.get("deny", ()),
        ask=rules.get("ask", ()),
        allow=rules.get("allow", ()),
    )
