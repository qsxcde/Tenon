"""扩展插件加载:发现 manifest、加载 TOOL_SPECS、命名空间化并装配。

目录放置即信任(与 mcp.json 列出即启动进程的模型一致):插件代码与内建工具
同进程执行,import 期副作用属信任范围;调用层经 ``ext__`` 命名空间 fail-closed
分类(默认需确认)。单插件任何失败只产生诊断并跳过,不阻塞整体装配。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from tenon.tools.base import AtomicTool
from tenon.tools.plugins.manifest import (
    MANIFEST_FILENAME,
    PluginManifest,
    is_valid_plugin_name,
    parse_plugin_manifest,
)
from tenon.tools.registry import ToolBuildContext, ToolRegistry, ToolSpec

__all__ = ["load_extension_tools"]

_FAILURE_PREFIX = "plugin_failed:"
_WARN_PREFIX = "plugin_warn:"


def load_extension_tools(
    extensions_dir: str | Path,
    *,
    build_context: ToolBuildContext,
) -> tuple[list[AtomicTool], list[str]]:
    """装配全部插件工具;目录缺失返回空集,单插件失败仅诊断并跳过。"""
    root = Path(extensions_dir).expanduser()
    if not root.is_dir():
        return [], []
    tools: list[AtomicTool] = []
    diags: list[str] = []
    seen_ids: set[str] = set()
    for plugin_dir in sorted(root.iterdir()):
        if not plugin_dir.is_dir() or not (plugin_dir / MANIFEST_FILENAME).is_file():
            continue
        manifest, manifest_diags = parse_plugin_manifest(plugin_dir)
        diags.extend(manifest_diags)
        if manifest is None:
            continue
        if manifest.plugin_id in seen_ids:
            diags.append(f"{_FAILURE_PREFIX} {manifest.plugin_id}: 重复插件 id,已跳过")
            continue
        seen_ids.add(manifest.plugin_id)
        try:
            specs = _load_tool_specs(plugin_dir, manifest)
            built = [spec.build(build_context) for spec in specs]
            _namespace_tools(manifest, specs, built)
        except Exception as exc:  # noqa: BLE001 - 单插件失败隔离为诊断
            diags.append(f"{_FAILURE_PREFIX} {manifest.plugin_id}: {type(exc).__name__}: {exc}")
            continue
        if manifest.tools and set(manifest.tools) != {spec.name for spec in specs}:
            diags.append(
                f"{_WARN_PREFIX} {manifest.plugin_id}: 声明工具与实际导出不一致"
                f"(声明 {sorted(manifest.tools)},实际 {sorted(spec.name for spec in specs)})"
            )
        tools.extend(built)
    return tools, diags


def _load_tool_specs(plugin_dir: Path, manifest: PluginManifest) -> tuple[ToolSpec, ...]:
    """加载插件模块并校验 TOOL_SPECS 导出(名称合法、无重复)。"""
    module_path = (plugin_dir / manifest.module).resolve()
    if not module_path.is_file():
        raise ValueError(f"module 文件不存在: {manifest.module}")
    module_name = f"tenon_ext_{manifest.plugin_id}_{module_path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"无法加载 module: {manifest.module}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    raw_specs = getattr(module, "TOOL_SPECS", None)
    if raw_specs is None:
        raise ValueError("插件模块缺少 TOOL_SPECS 导出")
    registry = ToolRegistry()
    result: list[ToolSpec] = []
    for entry in raw_specs:
        if not isinstance(entry, ToolSpec):
            raise ValueError(f"TOOL_SPECS 含非法注册项: {type(entry).__name__}")
        if not is_valid_plugin_name(entry.name):
            raise ValueError(f"非法插件工具名: {entry.name!r}")
        registry.register(entry)  # 重复名 fail-closed
        result.append(entry)
    return tuple(result)


def _namespace_tools(
    manifest: PluginManifest,
    specs: tuple[ToolSpec, ...],
    tools: list[AtomicTool],
) -> None:
    """实例级改名为 ``ext__<插件id>__<工具名>``,并校验构建产物形态。"""
    for spec, tool in zip(specs, tools):
        if not isinstance(tool, AtomicTool):
            raise ValueError(f"注册项 {spec.name} 未构建出 AtomicTool: {type(tool).__name__}")
        tool.name = f"ext__{manifest.plugin_id}__{spec.name}"
