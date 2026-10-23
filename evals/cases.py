"""离线评测用例:通过真实 Agent 循环驱动 fake 模型,断言可观察行为。

每个用例是一个 ``(name, runner)``;runner 接收一个临时工作区并发起一次完整
运行,失败时抛 ``AssertionError``。所有用例不联网、不读用户目录。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from codeagent.ai.providers.fake import FakeClient
from codeagent.app.composition.model.port import ChatModelPort
from codeagent.app.composition.tools.adapter import adapt_tools
from codeagent.core.context.model import AgentContext
from codeagent.core.contracts.messages import ToolCall
from codeagent.core.contracts.ports import ToolDecision
from codeagent.core.execution.runtime import ToolExecutionRuntime
from codeagent.core.orchestration.config import AgentLoopConfig
from codeagent.core.orchestration.loop import run_agent_loop
from codeagent.tools.atomic import ReadTool

__all__ = ["CASES", "Case", "run_case"]

CaseRunner = Callable[[Path], Awaitable[None]]


class Case:
    """一个评测用例:稳定名称 + 可等待断言函数。"""

    def __init__(self, name: str, runner: CaseRunner) -> None:
        self.name = name
        self.runner = runner

    async def run(self, workdir: Path) -> None:
        await self.runner(workdir)


def _config(
    steps: list[dict],
    *,
    before=(),
    tools=None,
) -> AgentLoopConfig:
    return AgentLoopConfig(
        model=ChatModelPort(FakeClient(steps=steps)),
        tools=adapt_tools(tools if tools is not None else [ReadTool()]),
        tool_runtime=ToolExecutionRuntime(),
        tool_timeout=10.0,
        before_tool_calls=tuple(before),
    )


def _tool_messages(messages) -> list[str]:
    return [str(message.content) for message in messages if message.role == "tool"]


async def _tool_read_flow(workdir: Path) -> None:
    (workdir / "note.txt").write_text("eval-hello", encoding="utf-8")
    config = _config(
        [
            {"tool_calls": [{"id": "c1", "name": "read", "args": {"file_path": "note.txt"}}]},
            {"content": "完成"},
        ],
        tools=[ReadTool(cwd=str(workdir))],
    )
    messages = await run_agent_loop(AgentContext(), config, "读取 note.txt")
    content = "\n".join(_tool_messages(messages))
    assert "eval-hello" in content, f"工具结果缺少文件内容: {content}"
    assert str(messages[-1].content).startswith("完成")


async def _unknown_tool_reports_error(workdir: Path) -> None:
    config = _config(
        [
            {"tool_calls": [{"id": "c1", "name": "missing_tool", "args": {}}]},
            {"content": "结束"},
        ]
    )
    messages = await run_agent_loop(AgentContext(), config, "调用不存在的工具")
    content = "\n".join(_tool_messages(messages))
    assert "未知工具" in content, f"未报告未知工具: {content}"


async def _approval_block_stops_execution(workdir: Path) -> None:
    def block(call, context):
        return ToolDecision.block("评测策略拒绝")

    config = _config(
        [
            {"tool_calls": [{"id": "c1", "name": "read", "args": {"file_path": "note.txt"}}]},
            {"content": "结束"},
        ],
        before=(block,),
        tools=[ReadTool(cwd=str(workdir))],
    )
    messages = await run_agent_loop(AgentContext(), config, "被拒绝的读取")
    content = "\n".join(_tool_messages(messages))
    assert "被拒绝" in content and "评测策略拒绝" in content
    assert "eval-hello" not in content


async def _argument_rewrite_reaches_tool(workdir: Path) -> None:
    (workdir / "a.txt").write_text("A-content", encoding="utf-8")
    (workdir / "b.txt").write_text("B-content", encoding="utf-8")

    def rewrite(call: ToolCall, context):
        return ToolCall(id=call.id, name=call.name, args={"file_path": "b.txt"})

    config = _config(
        [
            {"tool_calls": [{"id": "c1", "name": "read", "args": {"file_path": "a.txt"}}]},
            {"content": "结束"},
        ],
        before=(rewrite,),
        tools=[ReadTool(cwd=str(workdir))],
    )
    messages = await run_agent_loop(AgentContext(), config, "改参读取")
    content = "\n".join(_tool_messages(messages))
    assert "B-content" in content and "A-content" not in content


CASES: tuple[Case, ...] = (
    Case("tool_read_flow", _tool_read_flow),
    Case("unknown_tool_reports_error", _unknown_tool_reports_error),
    Case("approval_block_stops_execution", _approval_block_stops_execution),
    Case("argument_rewrite_reaches_tool", _argument_rewrite_reaches_tool),
)


async def run_case(case: Case, workdir: Path) -> None:
    await asyncio.wait_for(case.run(workdir), timeout=30.0)
