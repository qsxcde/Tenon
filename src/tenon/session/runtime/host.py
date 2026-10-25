"""``SessionRuntime`` mixin 组合的宿主属性声明基类。

``SessionRuntime``（``runtime/controller.py``）的行为分散在 ``RuntimeEventMixin``
与 ``SessionExecutionMixin`` 中。本基类只提供类级类型注解与跨 mixin 方法的
``Callable`` 声明，不含赋值或方法体；宿主 ``__init__`` 的真实赋值与方法定义会
覆盖这里的声明，因此运行时行为不变。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tenon.core import Agent
    from tenon.core.contracts.events import AgentEvent
    from tenon.core.contracts.hooks import HookDiagnostic
    from tenon.session.persistence.models import UsageStats
    from tenon.session.runtime.confirmation import ConfirmationCoordinator
    from tenon.session.runtime.controller import AgentFactory
    from tenon.session.runtime.event_mapper import SideEffectObserver
    from tenon.session.runtime.state import RunOutcome, RunPhase, RunState


class SessionRuntimeHost:
    """声明 mixin 组合宿主 ``SessionRuntime`` 的共享属性与跨 mixin 方法。"""

    # 宿主 ``__init__`` 建立的实例状态。
    _emit: Callable[[AgentEvent, str | None], None]
    _event_handler: Callable[[AgentEvent, str], None] | None
    _agent_factory: AgentFactory
    _session_id: str | None
    _confirmation_timeout: float | None
    inject_queue: asyncio.Queue[str]
    confirmation: ConfirmationCoordinator
    current_task: asyncio.Task[None] | None
    _state: RunState
    _side_effects: SideEffectObserver
    last_failure: dict[str, Any] | None
    last_outcome: RunOutcome | None
    turn_usage: UsageStats
    agent: Agent | None
    _hook_diagnostics: list[HookDiagnostic]

    # 宿主以只读 property 暴露的派生属性；mypy 不支持"只读属性"注解，
    # 这里的普通注解会在宿主处产生已知的 override 提示，但不改变运行时行为。
    phase: RunPhase
    active_run_id: str | None

    # 定义在 ``RuntimeEventMixin``、由 ``SessionExecutionMixin`` 调用的方法。
    _handle_event: Callable[[AgentEvent, str], None]


__all__ = ["SessionRuntimeHost"]
