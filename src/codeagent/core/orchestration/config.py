"""Configuration and callback contracts for the in-memory Agent loop."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
import math

from codeagent.core.context.budget import (
    DEFAULT_CONTEXT_WINDOW,
    DEFAULT_OUTPUT_RESERVE,
    DEFAULT_RESERVE_TOKENS,
)
from codeagent.core.context.contracts import (
    AfterToolCall,
    BeforeToolCall,
    ContextBudgetPort,
    ContextPreparer,
    ContextTransformer,
    identity_context,
)
from codeagent.core.context.preflight import ContextPreflightConfig
from codeagent.core.contracts.ports import (
    AgentTool,
    ModelPort,
    ToolExecutionRuntimePort,
)
from codeagent.core.contracts.hooks import LifecycleHook

__all__ = ["AgentLoopConfig"]


@dataclass
class AgentLoopConfig:
    """Configuration for the pure in-memory Agent loop."""

    model: ModelPort
    tools: list[AgentTool] = field(default_factory=list)
    transform_context: ContextTransformer = identity_context
    context_preparer: ContextPreparer | None = None
    #: Maximum wait for each request-local context extension invocation.
    context_transform_timeout: float | None = None
    context_budget: ContextBudgetPort | None = None
    context_preflight: ContextPreflightConfig = field(default_factory=ContextPreflightConfig)
    #: Explicit policy for a fallback/uncertain context window. ``allow``
    #: keeps legacy model adapters usable; ``fail`` makes the boundary hard.
    uncertain_budget_policy: str = "allow"
    #: 有序 pre 钩子链:通知/改参/门禁(见 core.orchestration.tool_hooks)。
    before_tool_calls: tuple[BeforeToolCall, ...] = field(default_factory=tuple)
    #: 有序 post 钩子链:结果变换/脱敏,返回 None 保留当前结果。
    after_tool_calls: tuple[AfterToolCall, ...] = field(default_factory=tuple)
    #: Ordered, read-only observers for core lifecycle events.
    lifecycle_hooks: tuple[LifecycleHook, ...] = field(default_factory=tuple)
    tool_execution: str = "parallel"
    tool_timeout: float | None = None
    should_stop_after_turn: Callable[..., Awaitable[bool] | bool] | None = None
    tool_runtime: ToolExecutionRuntimePort | None = None
    #: Runtime-owned steering queue; Agent drains it between tool batches.
    steer_queue: list[str] = field(default_factory=list)
    #: Fallback metadata for model adapters that predate the budget contract.
    context_window: int = DEFAULT_CONTEXT_WINDOW
    output_reserve: int = DEFAULT_OUTPUT_RESERVE
    reserve_tokens: int = DEFAULT_RESERVE_TOKENS
    window_source: str = "fallback"

    def __post_init__(self) -> None:
        self.lifecycle_hooks = tuple(self.lifecycle_hooks or ())
        self.before_tool_calls = tuple(self.before_tool_calls or ())
        self.after_tool_calls = tuple(self.after_tool_calls or ())
        if self.uncertain_budget_policy not in {"allow", "fail"}:
            raise ValueError("uncertain_budget_policy must be 'allow' or 'fail'")
        timeout = self.context_transform_timeout
        if timeout is not None and (
            type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0
        ):
            raise ValueError("context_transform_timeout must be a finite positive number")
