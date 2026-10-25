"""``AgentSession`` mixin 组合的宿主属性声明基类。

``AgentSession``（``session.py``）是公共门面，行为分散在事件、生命周期、压缩、
持久化控制与 Subagent 等 mixin 中。mixin 里访问的宿主属性与跨 mixin 方法对
mypy 不可见，逐条报 ``attr-defined``。本基类只提供类级类型注解（属性）与
``Callable`` 注解（跨 mixin 方法），不含任何赋值或方法体，因此不改变运行时
行为；宿主 ``__init__`` 的真实赋值与方法定义会覆盖这里的声明。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

from tenon.core.contracts.hooks import LifecycleHook
from tenon.core.contracts.ports import ApprovalPolicy
from tenon.core.orchestration.config import AgentLoopConfig

if TYPE_CHECKING:
    from tenon.core.contracts.events import AgentEvent
    from tenon.core.contracts.hooks import HookDiagnostic
    from tenon.core.contracts.messages import Message
    from tenon.core.context.budget import ContextBudgetSnapshot
    from tenon.core.context.contracts import ContextTransformer
    from tenon.session.compaction import CompactionPolicyConfig
    from tenon.session.compaction.summarizer import Summarizer
    from tenon.session.contracts import SessionCloser
    from tenon.session.events.bus import EventBus
    from tenon.session.runtime.controller import SessionRuntime
    from tenon.session.runtime.state import SessionBudgetState
    from tenon.session.run_coordinator import SessionRunCoordinator
    from tenon.session.session_persistence import SessionPersistence


class AgentSessionHost:
    """声明 mixin 组合宿主 ``AgentSession`` 的共享属性与跨 mixin 方法。"""

    # 宿主 ``__init__`` 建立的实例状态。
    _lifecycle_hooks: tuple[LifecycleHook, ...] | None
    _config: AgentLoopConfig
    _policy: ApprovalPolicy | None
    _bus: EventBus
    _recursion_limit: int
    _tool_timeout: float | None
    _session_id: str
    _previous_session_id: str | None
    _summarizer: Summarizer | None
    _context_window: int
    _runtime_closer: SessionCloser | None
    _budget_state: SessionBudgetState
    _transform_context: ContextTransformer | None
    _closed: bool
    _close_task: asyncio.Task[None] | None
    _lifecycle_hook_tasks: set[asyncio.Task[Any]]
    _lifecycle_hook_diagnostics: list[HookDiagnostic]
    _compaction_policy: CompactionPolicyConfig
    _compact_budget: int | None
    _compaction_gate: asyncio.Lock
    _last_compaction_fingerprint: tuple[Any, ...] | None
    _last_compaction_failure_fingerprint: tuple[Any, ...] | None
    _pending_compaction_budget: ContextBudgetSnapshot | None
    _last_input_tokens: int | None
    _persistence: SessionPersistence
    _runtime: SessionRuntime
    _run_coordinator: SessionRunCoordinator
    _history: list[Message]
    _summary: str | None
    _summary_entry_id: str | None
    _prev_details: dict[str, Any]

    # 宿主以只读 property 暴露的派生属性；mypy 不支持"只读属性"注解，
    # 这里的普通注解会在宿主处产生一条已知的 override 提示，但不改变运行时行为。
    model_id: str | None

    # 定义在其他 mixin（或宿主）、但被多个 mixin 调用的方法。
    _emit: Callable[[AgentEvent, str | None], None]
    run: Callable[..., Coroutine[Any, Any, None]]


__all__ = ["AgentSessionHost"]
