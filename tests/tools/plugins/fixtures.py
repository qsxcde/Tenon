"""假插件目录构造:离线测试用最小插件模块。"""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PLUGIN_MODULE = """
from pydantic import BaseModel

from codeagent.tools.base import AtomicTool
from codeagent.tools.registry import ToolSpec


class HelloArgs(BaseModel):
    name: str = "world"


class HelloTool(AtomicTool[HelloArgs]):
    name = "hello"
    description = "say hello"
    Args = HelloArgs

    def _invoke(self, args):
        return f"hello {args.name}"


TOOL_SPECS = (
    ToolSpec("hello", lambda context: HelloTool(cwd=context.cwd)),
)
"""


def make_plugin(
    root: Path,
    plugin_id: str,
    *,
    module_text: str = DEFAULT_PLUGIN_MODULE,
    manifest: dict | None = None,
    module_file: str = "plugin.py",
) -> Path:
    """在 root 下构造一个插件目录;manifest 字段可整体覆盖。"""
    plugin_dir = root / plugin_id
    plugin_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": plugin_id,
        "name": plugin_id,
        "version": "0.1.0",
        "module": module_file,
        "tools": ["hello"],
    }
    payload.update(manifest or {})
    (plugin_dir / "codeagent-plugin.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    (plugin_dir / module_file).write_text(module_text, encoding="utf-8")
    return plugin_dir


__all__ = ["DEFAULT_PLUGIN_MODULE", "make_plugin"]
