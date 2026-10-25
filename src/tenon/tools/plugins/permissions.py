"""扩展插件工具权限规则(``~/.tenon/extensions.json``)。"""

from __future__ import annotations

import json
from pathlib import Path

from tenon.tools.security.permission_rules import (
    ThreeTierPermissionRules,
    parse_three_tier_block,
)

__all__ = ["parse_extension_permissions"]


def parse_extension_permissions(config_dir: str | Path) -> ThreeTierPermissionRules:
    """读取 ``extensions.json`` 中的 permissions;缺失或非法时返回空规则。

    空规则 = 无显式命中,调用方对 ``ext__`` 工具 fail-closed 判 ask。
    """
    path = Path(config_dir).expanduser() / "extensions.json"
    if not path.is_file():
        return ThreeTierPermissionRules.empty()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ThreeTierPermissionRules.empty()
    return parse_three_tier_block(raw.get("permissions", {}) if isinstance(raw, dict) else {})
