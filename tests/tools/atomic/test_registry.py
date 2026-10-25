"""registry behavior tests."""

from tests.tools.atomic.fixtures import *  # noqa: F401,F403

from pydantic import BaseModel

from tenon.tools.atomic import SkillTool, TodoTool, WebFetchTool, WebSearchTool
from tenon.tools.registry import (
    BUILTIN_TOOL_SPECS,
    ToolBuildContext,
    ToolSpec,
    builtin_tool_registry,
    make_tools,
)
from tenon.tools.shared import ToolResourceLimits

BUILTIN_ORDER = (
    "read",
    "write",
    "edit",
    "bash",
    "grep",
    "find",
    "ls",
    "skill",
    "web_fetch",
    "web_search",
    "todo",
)
EXPECTED_TOOL_TYPES = (
    ReadTool,
    WriteTool,
    EditTool,
    BashTool,
    GrepTool,
    FindTool,
    LsTool,
    SkillTool,
    WebFetchTool,
    WebSearchTool,
    TodoTool,
)


def _demo_tool(context: ToolBuildContext) -> AtomicTool:
    """最小自定义工具构建器,验证注册表扩展缝隙。"""

    class DemoArgs(BaseModel):
        pass

    class DemoTool(AtomicTool):
        name = "demo"
        description = "demo"
        Args = DemoArgs

        def _invoke(self, _args):
            return "demo"

    return DemoTool(cwd=context.cwd, resource_limits=context.resource_limits)


def test_make_tools_returns_all_atomic_tools():
    tools = create_tools()
    assert isinstance(tools, list)
    assert len(tools) == 11
    names = {t.name for t in tools}
    assert names == {
        "read",
        "write",
        "edit",
        "bash",
        "grep",
        "find",
        "ls",
        "skill",
        "web_fetch",
        "web_search",
        "todo",
    }
    from tenon.tools.base import AtomicTool

    assert all(isinstance(t, AtomicTool) for t in tools)


def test_make_tools_offline(tmp_path):
    """无网络/无密钥副作用。"""
    tools = create_tools()
    assert tools  # 仅断言可装配


def test_dangerous_patterns_nonempty():
    assert DANGEROUS_PATTERNS


def test_builtin_registry_declares_fixed_names_in_order():
    """注册表声明顺序即装配顺序;名称锁定为八个内建工具。"""
    assert [spec.name for spec in BUILTIN_TOOL_SPECS] == list(BUILTIN_ORDER)
    assert builtin_tool_registry().names() == BUILTIN_ORDER


@pytest.mark.contract
def test_make_tools_matches_registry_declarations():
    """契约:make_tools 产出与注册表声明逐项一致(名称、类型、顺序)。"""
    tools = make_tools()
    assert [tool.name for tool in tools] == list(BUILTIN_ORDER)
    assert tuple(type(tool) for tool in tools) == EXPECTED_TOOL_TYPES

    rebuilt = builtin_tool_registry().build(
        ToolBuildContext(cwd=None, skills=None, resource_limits=ToolResourceLimits())
    )
    assert [tool.name for tool in rebuilt] == [tool.name for tool in tools]
    assert tuple(type(tool) for tool in rebuilt) == tuple(type(tool) for tool in tools)
    assert [spec.name for spec in BUILTIN_TOOL_SPECS] == [tool.name for tool in tools]


def test_registry_build_injects_cwd_and_skills(tmp_path):
    """注册表装配把 cwd 注入全部工具、技能表注入 skill 工具(行为级验证)。"""
    (tmp_path / "notes.md").write_text("hello", encoding="utf-8")
    tools = builtin_tool_registry().build(
        ToolBuildContext(
            cwd=str(tmp_path),
            skills={"demo": "SKILL BODY"},
            resource_limits=ToolResourceLimits(),
        )
    )
    by_name = {tool.name: tool for tool in tools}
    assert "hello" in _invoke(by_name["read"], file_path="notes.md")
    assert "SKILL BODY" in _invoke(by_name["skill"], name="demo")


def test_registry_rejects_duplicate_name():
    """重复名称 fail-closed,不静默覆盖既有注册项。"""
    registry = builtin_tool_registry()
    with pytest.raises(ValueError, match="read"):
        registry.register(ToolSpec("read", _demo_tool))


def test_registry_appends_registered_tool_in_order():
    """新注册项按登记顺序排在既有工具之后(扩展缝隙可用)。"""
    registry = builtin_tool_registry()
    registry.register(ToolSpec("demo", _demo_tool))
    assert registry.names() == BUILTIN_ORDER + ("demo",)

    tools = registry.build(
        ToolBuildContext(cwd=None, skills=None, resource_limits=ToolResourceLimits())
    )
    assert [tool.name for tool in tools] == list(BUILTIN_ORDER) + ["demo"]
    assert _invoke(tools[-1]) == "demo"
