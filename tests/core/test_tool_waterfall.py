"""工具执行瀑布链语义测试(通知/改参/门禁/post 变换,离线)。"""

from __future__ import annotations

import pytest

from codeagent.core.contracts.messages import ToolCall, ToolExecutionStatus, ToolResult
from codeagent.core.contracts.ports import PolicyDecision, ToolDecision
from codeagent.core.context.model import AgentContext
from codeagent.core.execution.runtime import ToolExecutionRuntime
from codeagent.core.orchestration.config import AgentLoopConfig
from codeagent.core.orchestration.tool_call import new_tool_result
from codeagent.core.orchestration.tool_hooks import run_pre_chain


class _EchoTool:
    name = "echo"
    description = "echo"
    parameters = {"type": "object"}

    def __init__(self) -> None:
        self.seen_args: list[dict] = []

    async def execute(self, tool_call_id, arguments, *, signal=None, on_update=None):
        self.seen_args.append(dict(arguments))
        return ToolResult(tool_call_id, f"echo:{arguments.get('text', '')}", name=self.name)


def _config(tool, before=(), after=()):
    return AgentLoopConfig(
        model=object(),
        tools=[tool],
        tool_runtime=ToolExecutionRuntime(),
        before_tool_calls=before,
        after_tool_calls=after,
    )


async def _run(tool, config, call=None):
    call = call or ToolCall(id="c1", name="echo", args={"text": "hi"})
    return await new_tool_result(
        tool,
        call,
        AgentContext(messages=[], tools=[tool]),
        config,
        emit=lambda event: None,
        operation_id="op-1",
    )


async def test_notify_hooks_do_not_disturb_execution():
    order: list[str] = []

    def hook(call, context):
        order.append("hook")
        return None

    tool = _EchoTool()
    result = await _run(tool, _config(tool, before=(hook,)))
    assert order == ["hook"]
    assert result.status == ToolExecutionStatus.COMPLETED
    assert "echo:hi" in result.content


async def test_rewrite_propagates_to_later_hooks_and_execution():
    seen: list[dict] = []

    def rewrite(call, context):
        return ToolCall(id=call.id, name=call.name, args={"text": "rewritten"})

    def observer(call, context):
        seen.append(dict(call.args))
        return None

    tool = _EchoTool()
    result = await _run(tool, _config(tool, before=(rewrite, observer)))
    assert seen == [{"text": "rewritten"}]
    assert tool.seen_args == [{"text": "rewritten"}]
    assert "echo:rewritten" in result.content


async def test_gate_short_circuits_without_tool_or_post_chain():
    order: list[str] = []

    def blocker(call, context):
        order.append("blocker")
        return ToolDecision.block("不放行")

    def never(call, context):
        order.append("never")
        return None

    def post(call, result, context):
        order.append("post")
        return None

    tool = _EchoTool()
    result = await _run(tool, _config(tool, before=(blocker, never), after=(post,)))
    assert order == ["blocker"]
    assert tool.seen_args == []
    assert result.status == ToolExecutionStatus.REJECTED
    assert result.rejected is True
    assert "不放行" in result.content


async def test_warnings_accumulate_in_order_with_single_prefix():
    def first(call, context):
        return ToolDecision.allow("警告一", warning=True)

    def second(call, context):
        return ToolDecision.allow("警告二", warning=True)

    tool = _EchoTool()
    result = await _run(tool, _config(tool, before=(first, second)))
    head = result.content.splitlines()[0]
    assert head == "[安全提示] 警告一; 警告二"
    assert result.content.count("[安全提示] ") == 1


async def test_post_chain_transforms_and_passes_result_on():
    seen: list[str] = []

    def redact(call, result, context):
        return ToolResult(result.tool_call_id, "脱敏后", name=result.name)

    def observer(call, result, context):
        seen.append(result.content)
        return None

    tool = _EchoTool()
    result = await _run(tool, _config(tool, after=(redact, observer)))
    assert result.content == "脱敏后"
    assert seen == ["脱敏后"]


async def test_awaitable_hooks_are_supported():
    async def rewrite(call, context):
        return ToolCall(id=call.id, name=call.name, args={"text": "async"})

    async def post(call, result, context):
        return ToolResult(result.tool_call_id, "post-async", name=result.name)

    tool = _EchoTool()
    result = await _run(tool, _config(tool, before=(rewrite,), after=(post,)))
    assert tool.seen_args == [{"text": "async"}]
    assert result.content == "post-async"


async def test_invalid_hook_return_fails_closed():
    def bad(call, context):
        return "垃圾返回值"

    tool = _EchoTool()
    with pytest.raises(TypeError, match="类型非法"):
        await _run(tool, _config(tool, before=(bad,)))


async def test_policy_gate_receives_rewritten_args():
    """策略门禁位于链尾并对改参后的调用判定(session 装配接线)。"""
    from codeagent.session.runtime.controller import SessionRuntime

    captured: list = []

    class StubAgent:
        is_running = False

        def subscribe(self, listener):
            return lambda: None

        async def prompt(self, text):
            return []

    def rewrite(call, context):
        return ToolCall(id=call.id, name=call.name, args={"text": "rewritten"})

    class StubPolicy:
        def __init__(self) -> None:
            self.received: list[tuple[str, dict]] = []

        def decide(self, tool_name, args):
            self.received.append((tool_name, dict(args)))
            return PolicyDecision("allow")

    policy = StubPolicy()
    runtime = SessionRuntime(
        lambda event, run_id: None,
        agent_factory=lambda context, config, limit: captured.append(config) or StubAgent(),
    )
    runtime.start_run()
    await runtime.execute(
        AgentLoopConfig(model=object(), before_tool_calls=(rewrite,)),
        "hi",
        history=[],
        recursion_limit=1,
        tool_timeout=None,
        policy=policy,
    )

    call = ToolCall(id="c1", name="echo", args={"text": "hi"})
    outcome = await run_pre_chain(
        captured[0].before_tool_calls, call, AgentContext(messages=[], tools=[])
    )
    assert outcome.blocked_reason is None
    assert outcome.call.args == {"text": "rewritten"}
    assert policy.received == [("echo", {"text": "rewritten"})]
