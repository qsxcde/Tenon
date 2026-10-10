"""任务监督器 mixin 宿主的类型声明基类。

``TaskLifecycleMixin`` 组合进 ``TaskSupervisor`` 后通过 ``self`` 访问宿主
属性与方法;mypy 无法从 mixin 推断宿主成员,故在此集中声明。本文件只含
类级类型注解,不包含默认值、赋值或方法体,运行时行为完全由
``TaskSupervisor`` 提供。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncio
    from collections.abc import Awaitable, Callable
    from typing import Any

    from .modes import TaskMode
    from .results import TaskEvent, TaskResult
    from .verification.models import (
        VerificationResult,
        WorkspaceDiff,
        WorkspaceSnapshot,
    )
    from .verification.workspace import VerificationCommandResolver, WorkspaceInspector


class TaskSupervisorHost:
    """TaskLifecycleMixin 的宿主属性与方法声明(仅类型,无行为)。"""

    session: Any
    inspector: WorkspaceInspector
    resolver: VerificationCommandResolver
    verify_command: str | None
    configured_command: str | None
    max_repairs: int
    _cancelled: bool
    _active_task: asyncio.Task[Any] | None
    _child_task: asyncio.Task[Any] | None
    _emit: Callable[[TaskEvent], None]
    _terminal: Callable[..., TaskResult]
    _capture_baseline: Callable[[TaskMode], Awaitable[WorkspaceSnapshot | None]]
    _run_agent: Callable[[str, TaskMode], Awaitable[None]]
    _verify: Callable[[str, str, int], Awaitable[VerificationResult]]
    _fingerprint: Callable[[VerificationResult, WorkspaceDiff], str]
    _repair_prompt: Callable[[VerificationResult, WorkspaceDiff], str]
