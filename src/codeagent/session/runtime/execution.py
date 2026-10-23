"""Agent execution bridge for the session runtime controller."""

from __future__ import annotations

import uuid
import asyncio
from dataclasses import fields, replace
from typing import Any

from codeagent.core import AgentContext, ToolDecision
from codeagent.core.context.contracts import BeforeToolCall
from codeagent.core.contracts.events import AgentEvent, EventType
from codeagent.core.contracts.messages import Message
from codeagent.core.contracts.ports import ApprovalPolicy, ApprovalResult
from codeagent.core.context.contracts import ContextTransformer
from codeagent.core.orchestration.config import AgentLoopConfig
from codeagent.session.runtime.host import SessionRuntimeHost


class SessionExecutionMixin(SessionRuntimeHost):
    """Create and run one core Agent without owning runtime state."""

    async def execute(
        self,
        config: AgentLoopConfig,
        text: str,
        *,
        history: list[Message],
        recursion_limit: int,
        tool_timeout: float | None,
        policy: ApprovalPolicy | None = None,
        transform_context: ContextTransformer | None = None,
    ) -> list[Message]:
        if self.active_run_id is None:
            raise RuntimeError("run must be started before execution")
        run_id = self.active_run_id
        self.current_task = asyncio.current_task()
        pending_steer = self._take_pending_steer()
        agent_config = self._build_agent_config(
            config,
            run_id,
            tool_timeout,
            policy,
            transform_context,
        )
        context = AgentContext(messages=list(history), tools=list(agent_config.tools))
        self.agent = self._agent_factory(context, agent_config, recursion_limit)
        set_run_id = getattr(self.agent, "set_run_id", None)
        if callable(set_run_id):
            set_run_id(run_id)
        for steer in pending_steer:
            self.agent.steer(steer)
        self.agent.subscribe(lambda event: self._handle_event(event, run_id))
        try:
            return await self.agent.prompt(text)
        finally:
            for diagnostic in getattr(self.agent, "hook_diagnostics", ()):
                if diagnostic.session_id is None:
                    diagnostic = replace(diagnostic, session_id=self._session_id)
                self._hook_diagnostics.append(diagnostic)

    def _take_pending_steer(self) -> list[str]:
        pending: list[str] = []
        while not self.inject_queue.empty():
            pending.append(self.inject_queue.get_nowait())
        return pending

    def _build_agent_config(
        self,
        config: AgentLoopConfig,
        run_id: str,
        tool_timeout: float | None,
        policy: ApprovalPolicy | None,
        transform_context: ContextTransformer | None,
    ) -> AgentLoopConfig:
        values = {item.name: getattr(config, item.name) for item in fields(AgentLoopConfig)}
        values.update(
            {
                "tools": self._bind_run_tools(values["tools"], run_id),
                "before_tool_calls": self._before_tool_calls_factory(
                    run_id, policy, values["before_tool_calls"]
                ),
                "tool_timeout": (
                    tool_timeout if tool_timeout is not None else values["tool_timeout"]
                ),
                "transform_context": transform_context or values["transform_context"],
            }
        )
        return AgentLoopConfig(**values)

    @staticmethod
    def _bind_run_tools(tools: list[Any], run_id: str) -> list[Any]:
        bound: list[Any] = []
        for tool in tools:
            binder = getattr(tool, "bind_parent_run_id", None)
            bound.append(binder(run_id) if callable(binder) else tool)
        return bound

    def _before_tool_calls_factory(
        self,
        run_id: str,
        policy: ApprovalPolicy | None,
        extensions: tuple[BeforeToolCall, ...],
    ) -> tuple[BeforeToolCall, ...]:
        """扩展钩子在前,安全策略门禁固定位于链尾(对改参后的调用判定)。"""

        async def policy_gate(call, _context):
            if policy is None:
                return ToolDecision.allow()
            decision = policy.decide(call.name, call.args)
            if decision.action == "allow":
                # 越界读等"放行但需提示"的判定必须让模型看到原因,否则
                # 安全策略的 warning 通道在适配层被静默丢弃。
                return ToolDecision.allow(decision.reason, warning=decision.warning)
            if decision.action == "deny":
                return ToolDecision.block(decision.reason)
            request_id = str(uuid.uuid4())
            self.confirmation.register(request_id, timeout=self._confirmation_timeout)
            self._handle_event(
                AgentEvent(
                    EventType.CONFIRMATION_REQUESTED,
                    payload={
                        "request_id": request_id,
                        "tool_call_id": call.id,
                        "tool": call.name,
                        "args": call.args,
                        "reason": decision.reason,
                    },
                ),
                run_id,
            )
            approved = await self.confirmation.wait(
                request_id,
                timeout=self._confirmation_timeout,
            )
            # 封闭审批结果 + fail-closed 映射:拒绝原因对模型可见;
            # 超时/取消不在这里截获,保持既有异常语义(confirmation_error / 取消)。
            return ApprovalResult.from_response(approved).to_tool_decision()

        return (*extensions, policy_gate)


__all__ = ["SessionExecutionMixin"]
