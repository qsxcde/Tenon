"""MCP 工具权限规则解析与匹配。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tenon.tools.security.permission_rules import (
    match_tool_rule,
    normalize_rule,
    parse_three_tier_block,
)


@dataclass(frozen=True)
class McpPermissionRules:
    """三级 MCP 权限规则：deny > ask > allow。"""

    deny: tuple[str, ...] = ()
    ask: tuple[str, ...] = ()
    allow: tuple[str, ...] = ()

    @classmethod
    def empty(cls) -> "McpPermissionRules":
        return cls()

    def decide(self, qualified_name: str) -> str | None:
        normalized = normalize_rule(qualified_name)
        for action in ("deny", "ask", "allow"):
            if any(
                match_tool_rule(normalized, normalize_rule(rule)) for rule in getattr(self, action)
            ):
                return action
        return None


def parse_mcp_permissions(config_dir: str | Path) -> McpPermissionRules:
    """读取 ``mcp.json`` 中的 permissions；缺失或非法时返回空规则。"""
    path = Path(config_dir).expanduser() / "mcp.json"
    if not path.is_file():
        return McpPermissionRules.empty()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return McpPermissionRules.empty()
    parsed = parse_three_tier_block(raw.get("permissions", {}) if isinstance(raw, dict) else {})
    return McpPermissionRules(deny=parsed.deny, ask=parsed.ask, allow=parsed.allow)


__all__ = ["McpPermissionRules", "parse_mcp_permissions"]
