"""插件工具装配集成测试(内建+插件合并、诊断、白名单过滤)。"""

from __future__ import annotations

import pytest

from tests.tools.plugins.fixtures import make_plugin

pytestmark = pytest.mark.integration

_BROKEN_MODULE = 'raise RuntimeError("boom")'


def _extensions_dir():
    from tenon.app.config import extensions_dir

    return extensions_dir()


def _assemble(allowed=None):
    from tenon.app.composition.runtime.tool_assembly import assemble_runtime_tools
    from tenon.tools.shared import ToolResourceLimits

    diags: list[str] = []
    tools, mcp_tools = assemble_runtime_tools(
        None,
        [],
        ToolResourceLimits(),
        diags,
        allowed,
        None,
    )
    return tools, diags


def test_extension_tools_join_runtime_after_builtin():
    make_plugin(_extensions_dir(), "demo")
    tools, diags = _assemble()
    names = [tool.name for tool in tools]
    assert diags == []
    assert "ext__demo__hello" in names
    assert names.index("ext__demo__hello") > names.index("skill")


def test_broken_plugin_reports_diagnostic_without_blocking():
    make_plugin(_extensions_dir(), "bad", module_text=_BROKEN_MODULE)
    make_plugin(_extensions_dir(), "good")
    tools, diags = _assemble()
    names = [tool.name for tool in tools]
    assert "ext__good__hello" in names
    assert "ext__bad__hello" not in names
    assert any("plugin_failed: bad" in diag for diag in diags)


def test_allowed_tool_names_filters_ext_tools():
    make_plugin(_extensions_dir(), "demo")
    tools, _ = _assemble(allowed={"read", "ext__demo__hello"})
    assert {tool.name for tool in tools} == {"read", "ext__demo__hello"}
