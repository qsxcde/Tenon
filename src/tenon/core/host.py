"""``Agent`` mixin 组合的宿主属性声明基类。

``Agent``（``core/agent.py``）把生命周期观测行为委托给
``LifecycleHookObservationMixin``（``core/observation.py``）。mixin 里访问的宿主
属性对 mypy 不可见，逐条报 ``attr-defined``。本基类只提供类级类型注解，不含
任何赋值或方法体，因此不改变运行时行为；宿主 ``__init__`` 的真实赋值会覆盖
这里的声明。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from tenon.core.contracts.hooks import LifecycleHook

if TYPE_CHECKING:
    from tenon.core.contracts.events import AgentEvent
    from tenon.core.contracts.hooks import HookDiagnostic


class AgentHost:
    """声明 mixin 组合宿主 ``Agent`` 的共享实例属性。"""

    # 宿主 ``__init__`` 建立的实例状态。
    _lifecycle_hooks: tuple[LifecycleHook, ...]
    _listener_errors: list[tuple[AgentEvent, Exception]]
    _hook_diagnostics: list[HookDiagnostic]
    _listener_tasks: set[asyncio.Future[Any]]
