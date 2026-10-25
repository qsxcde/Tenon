"""``SessionManager`` mixin 组合的宿主属性声明基类。

``SessionManager`` 的行为分散在 ``operations`` / ``registry`` / ``archive`` 三个
mixin 中，mixin 里访问的宿主属性与跨 mixin 方法对 mypy 不可见。本基类只提供
类级类型注解（属性）与 ``Callable`` 注解（跨 mixin 方法），不含任何赋值或方法体，
因此不改变运行时行为；宿主类的真实定义会覆盖这里的声明。
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from tenon.core.contracts.hooks import LifecycleHook
from tenon.core.contracts.ports import ApprovalPolicy
from tenon.core.orchestration.config import AgentLoopConfig

if TYPE_CHECKING:
    from tenon.session.compaction import CompactionPolicyConfig
    from tenon.session.compaction.summarizer import Summarizer
    from tenon.session.contracts import SessionCloser
    from tenon.session.events.bus import Subscriber
    from tenon.session.persistence.models import SessionRef, SessionStore
    from tenon.session.session import AgentSession


class SessionManagerHost:
    """声明 mixin 组合宿主 ``SessionManager`` 的共享属性与跨 mixin 方法。"""

    # 宿主 ``__init__`` 建立的实例状态。
    _config: AgentLoopConfig
    _policy: ApprovalPolicy | None
    _store: SessionStore | None
    _model: str
    _effort: str
    _recursion_limit: int
    _tool_timeout: float | None
    _confirmation_timeout: float | None
    _summarizer: Summarizer | None
    _context_window: int
    _compact_budget: int | None
    _compaction_policy: CompactionPolicyConfig | None
    _runtime_closer: SessionCloser | None
    _session_config_factory: Callable[[SessionRef], AgentLoopConfig] | None
    _lifecycle_hooks: tuple[LifecycleHook, ...]
    _max_resident_sessions: int
    _closed: bool
    _close_task: asyncio.Task[None] | None
    _sessions: dict[str, AgentSession]
    _session_access: dict[str, int]
    _access_counter: int
    _current_id: str | None
    _subscribers: list[tuple[Subscriber, list[Callable[[], None]]]]

    # 宿主以只读 property 暴露的派生属性；mypy 不支持"只读属性"注解，
    # 这里的普通注解会在宿主处产生一条已知的 override 提示，但不改变运行时行为。
    current: AgentSession | None

    # 定义在其他 mixin、但被本组合内多处调用的方法；用 Callable 声明避免
    # 各实现签名差异引发的 override 检查噪声。
    _adopt: Callable[..., AgentSession]
    _halt_current: Callable[[], None]
    _halt_current_and_wait: Callable[[], Awaitable[None]]
    _last_user_message_id: Callable[[str], str]


__all__ = ["SessionManagerHost"]
