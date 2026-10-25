"""扩展插件子系统:manifest 解析、工具加载与权限规则。

分层约束:本包仅依赖 tools 内部与标准库,禁止 import core/session/ai/app;
插件目录与配置目录路径由调用方注入(组合根解析)。
"""

from tenon.tools.plugins.loader import load_extension_tools
from tenon.tools.plugins.manifest import (
    MANIFEST_FILENAME,
    PluginManifest,
    is_valid_plugin_name,
    parse_plugin_manifest,
)
from tenon.tools.plugins.permissions import parse_extension_permissions

__all__ = [
    "MANIFEST_FILENAME",
    "PluginManifest",
    "is_valid_plugin_name",
    "load_extension_tools",
    "parse_extension_permissions",
    "parse_plugin_manifest",
]
