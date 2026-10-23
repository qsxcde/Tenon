"""扩展插件 manifest 解析与校验(``codeagent-plugin.json``)。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypeGuard

__all__ = ["MANIFEST_FILENAME", "PluginManifest", "is_valid_plugin_name", "parse_plugin_manifest"]

MANIFEST_FILENAME = "codeagent-plugin.json"

#: 插件 id 与工具名约束:小写下划线命名且禁含 `__`(命名空间分隔符)。
_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def is_valid_plugin_name(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and bool(_NAME_RE.match(value)) and "__" not in value


@dataclass(frozen=True)
class PluginManifest:
    """插件清单:id/name/version/module(插件目录内相对路径)/tools 声明。"""

    plugin_id: str
    name: str
    version: str
    module: str
    tools: tuple[str, ...] = ()


def parse_plugin_manifest(plugin_dir: Path) -> tuple[PluginManifest | None, list[str]]:
    """解析一个插件目录的 manifest;失败返回 (None, 诊断)。"""
    diags: list[str] = []
    path = plugin_dir / MANIFEST_FILENAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"plugin_failed: {plugin_dir.name}: manifest 读取失败: {exc}"]
    if not isinstance(raw, dict):
        return None, [f"plugin_failed: {plugin_dir.name}: manifest 必须是 JSON 对象"]

    plugin_id_value = raw.get("id")
    if not isinstance(plugin_id_value, str) or not is_valid_plugin_name(plugin_id_value):
        return None, [
            f"plugin_failed: {plugin_dir.name}: 非法插件 id: {plugin_id_value!r}"
            "(需匹配 ^[a-z][a-z0-9_]*$ 且不含 __)"
        ]
    plugin_id = plugin_id_value
    module = raw.get("module")
    if not isinstance(module, str) or not module.strip():
        return None, [f"plugin_failed: {plugin_id}: manifest 缺少 module 字段"]
    module_path = (plugin_dir / module).resolve()
    if not module_path.is_relative_to(plugin_dir.resolve()):
        return None, [f"plugin_failed: {plugin_id}: module 越出插件目录: {module}"]

    tools_raw = raw.get("tools", [])
    tools: list[str] = []
    if not isinstance(tools_raw, list):
        diags.append(f"plugin_warn: {plugin_id}: tools 声明必须是数组,已忽略")
    else:
        for entry in tools_raw:
            if not is_valid_plugin_name(entry):
                diags.append(f"plugin_warn: {plugin_id}: 非法工具名声明已忽略: {entry!r}")
            else:
                tools.append(entry)

    manifest = PluginManifest(
        plugin_id=plugin_id,
        name=str(raw.get("name", plugin_id)),
        version=str(raw.get("version", "")),
        module=module,
        tools=tuple(tools),
    )
    return manifest, diags
