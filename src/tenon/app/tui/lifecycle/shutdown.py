"""TUI 退出生命周期：任务跟踪、延迟关闭与资源收尾。

``TuiApp`` 的关闭路径与业务职责无关，单独拆出以保持 ``application.py``
在规模门禁以内。本模块只定义 mixin，宿主负责创建 ``__init__`` 中的状态。
"""

from __future__ import annotations

import asyncio
from typing import Any


class TuiShutdownMixin:
    """在 backend 回调与事件循环之间安全地收尾 TUI 资源。"""

    # 由宿主 ``TuiApp.__init__`` 建立的状态。
    _manager: Any
    _close_runtime: Any
    _unsubscribe: Any
    _event_buffer: Any
    model: Any
    _shutdown_task: asyncio.Task[None] | None
    _background_tasks: set[asyncio.Task[Any]]
    _shutdown_started: bool
    _shutdown_complete: bool
    _accepting_input: bool
    _restore_task: asyncio.Task[None] | None
    _conversation_task: asyncio.Task[None] | None
    _session_action_task: asyncio.Task[None] | None
    _package_task: asyncio.Task[None] | None
    _task_supervisor: Any

    def _exit(self) -> None:
        """Schedule async shutdown from the synchronous backend callback."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.shutdown())
            return
        if not self._shutdown_complete and self._shutdown_task is None:
            self._shutdown_task = self._track_task(loop.create_task(self.shutdown()))

    def _track_task(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        """Register a TUI-owned task so shutdown can await or cancel it."""
        self._background_tasks.add(task)

        def consume_done(done: asyncio.Task[Any]) -> None:
            self._background_tasks.discard(done)
            if done.cancelled():
                return
            try:
                done.exception()
            except BaseException:
                # Retrieving the exception prevents asyncio's orphan-task
                # warning; task bodies render their own operational errors.
                pass

        task.add_done_callback(consume_done)
        return task

    async def shutdown(self) -> None:
        """Stop TUI work, release runtime ownership, then leave the backend."""
        if self._shutdown_complete or self._shutdown_started:
            return
        self._shutdown_started = True
        self._accepting_input = False
        self._stop_runtime_activity()

        tasks = self._pending_tasks()
        current = asyncio.current_task()
        for task in tuple(self._background_tasks):
            if task is not current and not task.done() and task not in tasks:
                tasks.append(task)
        await self._cancel_tasks(tasks)
        self._release_subscription()
        await self._close_owned_runtime()
        self._finish_shutdown()

    # 以下钩子由宿主提供，避免把渲染/确认细节耦合进收尾逻辑。
    def _stop_runtime_activity(self) -> None:
        raise NotImplementedError

    def _transcript_width(self) -> int:
        raise NotImplementedError

    def _pending_tasks(self) -> list[asyncio.Task[Any]]:
        """返回需在关闭时等待退出的前台任务。"""
        return [
            task
            for task in (
                self._restore_task,
                self._conversation_task,
                self._session_action_task,
                self._package_task,
            )
            if task is not None and not task.done()
        ]

    async def _cancel_tasks(self, tasks: list[asyncio.Task[Any]]) -> None:
        if self._task_supervisor is not None:
            self._task_supervisor.cancel()
        for task in tasks:
            task.cancel()
        if tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=1.0)
            except TimeoutError:
                # 忽略拒绝退出的任务；资源收尾由后面的 close 边界兜底。
                pass

    def _release_subscription(self) -> None:
        if self._unsubscribe is None:
            return
        unsubscribe, self._unsubscribe = self._unsubscribe, None
        try:
            unsubscribe()
        except (ValueError, KeyError):
            pass

    async def _close_owned_runtime(self) -> None:
        manager_close = getattr(self._manager, "close", None)
        if callable(manager_close):
            result = manager_close()
            if hasattr(result, "__await__"):
                # The manager owns model/MCP/tool resources. Its async close
                # is the authoritative wait boundary; proceeding after a
                # timeout would allow the TUI to exit while work still holds
                # those resources.
                await result
        elif self._close_runtime is not None:
            result = self._close_runtime()
            if hasattr(result, "__await__"):
                await result

    def _finish_shutdown(self) -> None:
        self._event_buffer.flush()
        width = self._transcript_width()
        self._backend.exit_document(self.model.transcript.iter_lines(width))
        self._shutdown_complete = True

    _backend: Any


__all__ = ["TuiShutdownMixin"]
