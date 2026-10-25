"""插件工具加载契约测试(离线:tmp_path 假插件目录)。"""

from __future__ import annotations

import pytest

from tenon.tools.plugins.loader import load_extension_tools
from tenon.tools.registry import ToolBuildContext
from tenon.tools.shared import ToolResourceLimits
from tests.tools.plugins.fixtures import make_plugin

pytestmark = pytest.mark.contract

_BAD_MODULE = 'raise RuntimeError("boom")'
_NO_SPECS_MODULE = "VALUE = 1\n"
_DUP_SPECS_MODULE = """
from pydantic import BaseModel
from tenon.tools.base import AtomicTool
from tenon.tools.registry import ToolSpec


class Args(BaseModel):
    pass


class T(AtomicTool[Args]):
    name = "t"
    description = "t"
    Args = Args

    def _invoke(self, args):
        return "t"


TOOL_SPECS = (
    ToolSpec("t", lambda context: T()),
    ToolSpec("t", lambda context: T()),
)
"""
_BAD_NAME_MODULE = """
from tenon.tools.registry import ToolSpec

TOOL_SPECS = (ToolSpec("Bad__Name", lambda context: None),)
"""


def _context() -> ToolBuildContext:
    return ToolBuildContext(cwd=None, skills=None, resource_limits=ToolResourceLimits())


def test_loads_plugin_tools_with_namespace(tmp_path):
    make_plugin(tmp_path, "demo")
    tools, diags = load_extension_tools(tmp_path, build_context=_context())
    assert diags == []
    assert [tool.name for tool in tools] == ["ext__demo__hello"]
    assert tools[0].invoke(tools[0].Args(name="世界")) == "hello 世界"


def test_missing_directory_returns_empty(tmp_path):
    tools, diags = load_extension_tools(tmp_path / "none", build_context=_context())
    assert tools == [] and diags == []


def test_import_failure_is_isolated(tmp_path):
    make_plugin(tmp_path, "bad", module_text=_BAD_MODULE)
    make_plugin(tmp_path, "good")
    tools, diags = load_extension_tools(tmp_path, build_context=_context())
    assert [tool.name for tool in tools] == ["ext__good__hello"]
    assert any("plugin_failed: bad" in diag and "boom" in diag for diag in diags)


def test_missing_tool_specs_reported(tmp_path):
    make_plugin(tmp_path, "nospecs", module_text=_NO_SPECS_MODULE)
    tools, diags = load_extension_tools(tmp_path, build_context=_context())
    assert tools == []
    assert any("缺少 TOOL_SPECS" in diag for diag in diags)


def test_duplicate_spec_names_fail_closed(tmp_path):
    make_plugin(tmp_path, "dup", module_text=_DUP_SPECS_MODULE)
    tools, diags = load_extension_tools(tmp_path, build_context=_context())
    assert tools == []
    assert any("plugin_failed: dup" in diag for diag in diags)


def test_invalid_tool_name_rejected(tmp_path):
    make_plugin(tmp_path, "badname", module_text=_BAD_NAME_MODULE)
    tools, diags = load_extension_tools(tmp_path, build_context=_context())
    assert tools == []
    assert any("非法插件工具名" in diag for diag in diags)


def test_duplicate_plugin_id_skipped(tmp_path):
    make_plugin(tmp_path, "demo")
    make_plugin(tmp_path, "demo-copy", manifest={"id": "demo"})
    tools, diags = load_extension_tools(tmp_path, build_context=_context())
    assert [tool.name for tool in tools] == ["ext__demo__hello"]
    assert any("重复插件 id" in diag for diag in diags)


def test_declared_vs_actual_mismatch_warns(tmp_path):
    make_plugin(tmp_path, "demo", manifest={"tools": ["hello", "ghost"]})
    tools, diags = load_extension_tools(tmp_path, build_context=_context())
    assert [tool.name for tool in tools] == ["ext__demo__hello"]
    assert any("声明工具与实际导出不一致" in diag for diag in diags)


def test_module_escape_is_rejected_without_execution(tmp_path):
    make_plugin(tmp_path, "demo", manifest={"module": "../outside.py"})
    (tmp_path / "outside.py").write_text(_BAD_MODULE, encoding="utf-8")
    tools, diags = load_extension_tools(tmp_path, build_context=_context())
    assert tools == []
    assert any("越出插件目录" in diag for diag in diags)
