"""Provider-neutral ports for the core runtime.

自研编排(2026-08-14)后端口收敛为模型、工具和运行时契约:
- ``model``:模型端口(实现方在组合根,内部对接 ai 层 ChatClient);
- ``tools``:实现 ``AgentTool`` 的工具列表;
- ``tool_runtime``:受控执行端口,由 core 或组合根提供。

The core layer does not import config, ai, tools, or session. Composition roots
are responsible for adapting those implementations to these ports.
"""

from __future__ import annotations

import asyncio
import enum
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from collections.abc import Mapping
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from codeagent.core.contracts.messages import Message, ToolCall, ToolResult

__all__ = [
    "AgentTool",
    "ApprovalOutcome",
    "ApprovalResult",
    "ModelPort",
    "ModelResponse",
    "PolicyDecision",
    "StreamEvent",
    "Summarizer",
    "ToolDecision",
    "ToolCleanupPort",
    "ToolExecutionRuntimePort",
]


@dataclass
class ModelResponse:
    """模型一次完整生成的结果(非流式路径)。"""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, int] | None = None  # {input_tokens, output_tokens, reasoning_tokens}
    finish_reason: str | None = None
    model: str = ""


@dataclass
class StreamEvent:
    """模型流式产出的统一事件(与 ai 层 SSE 解析同形,core 自有类型)。"""

    type: str  # content | thinking | tool_call_arg | finish | usage
    text: str = ""
    tool_index: int | None = None
    arg_delta: str = ""
    tool_name: str = ""
    tool_id: str = ""
    finish_reason: str | None = None
    usage: dict[str, int] | None = None
    #: Parsed tool arguments supplied by the application model adapter.
    arguments: dict[str, Any] | None = None
    argument_error: str | None = None


@dataclass(frozen=True)
class PolicyDecision:
    """执行前安全策略的决策结果(design security-permissions)。

    - ``action``:allow(直接执行)/ ask(需用户确认)/ deny(拒绝执行);
    - ``reason``:决策原因(拒绝/确认时对模型与用户可见,审计用途);
    - ``warning``:放行但附带提示(如越界读),不影响执行。
    """

    action: str  # "allow" | "ask" | "deny"
    reason: str = ""
    warning: bool = False


class ApprovalPolicy(Protocol):
    """执行前安全策略端口:决定工具调用放行/需确认/拒绝。

    core 只认识决策形态;实现方在组合根(tools 层分类器适配),循环在
    每个工具调用执行前调用;``ask`` 由循环 emit 确认请求并等待会话队列。
    """

    def decide(self, tool_name: str, args: dict) -> PolicyDecision: ...


class ToolExecutionRuntimePort(Protocol):
    """Optional runtime port used by the ReAct loop for controlled execution."""

    async def execute(
        self,
        tool: "AgentTool",
        call: ToolCall,
        timeout: float | None = None,
        operation_id: str | None = None,
        on_update: Callable[[Any], Awaitable[None] | None] | None = None,
        on_start: Callable[[Any], Awaitable[None] | None] | None = None,
    ) -> ToolResult: ...


class Summarizer(Protocol):
    """上下文压缩摘要端口(session-compaction):把被压缩窗口摘要化。

    - ``messages``:被压缩窗口的消息(完整轮次);
    - ``prev_summary``:上一次压缩的摘要(二次压缩增量合并,None = 首次);
    - 返回摘要文本;实现方在组合根(离线测试注入桩,真实实现接 LLM)。
    """

    async def summarize(self, messages: list[Message], prev_summary: str | None) -> str: ...


class ModelPort(Protocol):
    """模型端口:编排循环消费的最小调用面(实现方在组合根)。"""

    @property
    def model_id(self) -> str: ...

    async def generate(
        self,
        messages: list[Message],
        tools: list["AgentTool"] | None = None,
    ) -> ModelResponse: ...

    def stream(
        self,
        messages: list[Message],
        tools: list["AgentTool"] | None = None,
    ) -> AsyncIterator[StreamEvent]: ...


@runtime_checkable
class AgentTool(Protocol):
    """唯一由 Agent Runtime 消费的工具契约。"""

    name: str
    description: str
    parameters: Mapping[str, Any]

    async def execute(
        self,
        tool_call_id: str,
        arguments: dict[str, Any],
        *,
        signal: Any = None,
        on_update: Callable[[Any], Awaitable[None] | None] | None = None,
    ) -> ToolResult: ...


@runtime_checkable
class ToolCleanupPort(Protocol):
    """Optional cleanup port for tools with externally owned resources."""

    async def cleanup(self, operation_id: str) -> bool | None: ...


@dataclass(frozen=True)
class ToolDecision:
    """Generic pre-execution decision returned by an Agent hook.

    `warning` marks an allowed call whose reason must stay visible to the
    model (for example an out-of-workspace read). The loop prefixes the
    reason to the tool result instead of dropping it, so the design intent
    "allow but tell the model" is actually observable.
    """

    action: str
    reason: str = ""
    warning: bool = False

    @classmethod
    def allow(cls, reason: str = "", *, warning: bool = False) -> "ToolDecision":
        return cls("allow", reason, warning)

    @classmethod
    def block(cls, reason: str, *, warning: bool = False) -> "ToolDecision":
        return cls("block", reason, warning)


class ApprovalOutcome(enum.StrEnum):
    """审批流的封闭终态(fail-closed):仅显式放行才可执行。

    封闭集合借鉴 harness 通行做法(allowed-once / rejected / cancelled /
    unavailable),并按本仓库错误语义把「超时」独立出来(区分失败、超时、取消
    与清理不确定)。任何映射都不得超出该集合。
    """

    #: 用户确认放行(一次性授权,不缓存为长期许可)
    ALLOWED_ONCE = "allowed_once"
    #: 用户明确拒绝
    REJECTED = "rejected"
    #: 等待被取消(abort / 会话取消)
    CANCELLED = "cancelled"
    #: 确认请求超时无响应
    TIMED_OUT = "timed_out"
    #: 审批通道不可用(如 headless 无确认通道)
    UNAVAILABLE = "unavailable"


#: fail-closed 的默认拒绝原因:非放行终态必须给出可诊断理由。
_APPROVAL_BLOCK_REASONS: dict[ApprovalOutcome, str] = {
    ApprovalOutcome.REJECTED: "用户拒绝执行",
    ApprovalOutcome.CANCELLED: "确认被取消,未确认不得执行",
    ApprovalOutcome.TIMED_OUT: "确认超时,未确认不得执行",
    ApprovalOutcome.UNAVAILABLE: "审批通道不可用,未确认不得执行",
}


@dataclass(frozen=True)
class ApprovalResult:
    """一次审批的封闭结果:放行判定与终态归因只认这个封闭集合。

    ``to_tool_decision`` / ``to_policy_decision`` 均为 fail-closed 映射:
    只有 ``ALLOWED_ONCE`` 放行,其余终态一律拒绝执行并携带可诊断原因。
    """

    outcome: ApprovalOutcome
    reason: str = ""

    @classmethod
    def from_response(cls, approved: bool, reason: str = "") -> "ApprovalResult":
        """把确认响应(批准/拒绝)映射为封闭终态。"""
        if approved:
            return cls(ApprovalOutcome.ALLOWED_ONCE, reason)
        return cls(
            ApprovalOutcome.REJECTED,
            reason or _APPROVAL_BLOCK_REASONS[ApprovalOutcome.REJECTED],
        )

    @classmethod
    def from_exception(cls, exc: BaseException) -> "ApprovalResult":
        """把等待审批期间的异常归因到封闭终态(取消/超时),其余归为通道不可用。"""
        if isinstance(exc, asyncio.CancelledError):
            return cls(
                ApprovalOutcome.CANCELLED,
                str(exc) or _APPROVAL_BLOCK_REASONS[ApprovalOutcome.CANCELLED],
            )
        if isinstance(exc, TimeoutError):
            return cls(
                ApprovalOutcome.TIMED_OUT,
                str(exc) or _APPROVAL_BLOCK_REASONS[ApprovalOutcome.TIMED_OUT],
            )
        return cls(
            ApprovalOutcome.UNAVAILABLE,
            str(exc) or _APPROVAL_BLOCK_REASONS[ApprovalOutcome.UNAVAILABLE],
        )

    @property
    def is_allowed(self) -> bool:
        return self.outcome is ApprovalOutcome.ALLOWED_ONCE

    def to_tool_decision(self) -> ToolDecision:
        """fail-closed:仅 ALLOWED_ONCE 放行,其余终态映射为工具级拒绝。"""
        if self.is_allowed:
            return ToolDecision.allow(self.reason)
        return ToolDecision.block(self.reason or _APPROVAL_BLOCK_REASONS[self.outcome])

    def to_policy_decision(self) -> PolicyDecision:
        """fail-closed:仅 ALLOWED_ONCE 映射为 allow,其余映射为 deny 且带原因。"""
        if self.is_allowed:
            return PolicyDecision("allow", self.reason)
        return PolicyDecision("deny", self.reason or _APPROVAL_BLOCK_REASONS[self.outcome])
