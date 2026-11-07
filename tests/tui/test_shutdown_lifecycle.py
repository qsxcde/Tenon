"""TuiShutdownMixin 的退出生命周期单元测试（无 Textual 依赖）。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tenon.app.tui.lifecycle.shutdown import TuiShutdownMixin


class _Transcript:
    def __init__(self) -> None:
        self.iter_widths: list[int] = []

    def iter_lines(self, width: int) -> list[str]:
        self.iter_widths.append(width)
        return ["exit-doc"]


class _Model:
    def __init__(self) -> None:
        self.transcript = _Transcript()


class _Buffer:
    def __init__(self) -> None:
        self.flushes = 0

    def flush(self) -> None:
        self.flushes += 1


class _Backend:
    width = 90

    def __init__(self) -> None:
        self.exit_documents: list[str] | None = None

    def transcript_size(self) -> tuple[int, int]:
        return self.width, 24

    def exit_document(self, lines: list[str]) -> None:
        self.exit_documents = lines


class _Manager:
    def __init__(self, *, async_close: bool = True) -> None:
        self.closed = 0
        self.unsubscribed = 0
        self._async_close = async_close

    def subscribe(self, _fn: Any) -> Any:
        def unsubscribe() -> None:
            raise ValueError("already gone")

        return unsubscribe

    def close(self) -> Any:
        self.closed += 1
        if not self._async_close:
            return None

        async def _close() -> None:
            return None

        return _close()


class _Host(TuiShutdownMixin):
    def __init__(self, manager: _Manager, *, close_runtime: Any = None) -> None:
        self._manager = manager
        self._close_runtime = close_runtime
        self._unsubscribe = manager.subscribe(self)
        self._event_buffer = _Buffer()
        self.model = _Model()
        self._shutdown_task = None
        self._background_tasks = set()
        self._shutdown_started = False
        self._shutdown_complete = False
        self._accepting_input = True
        self._restore_task = None
        self._conversation_task = None
        self._session_action_task = None
        self._package_task = None
        self._task_supervisor = None
        self._backend = _Backend()
        self.activity_stopped = 0

    def _stop_runtime_activity(self) -> None:
        self.activity_stopped += 1

    def _transcript_width(self) -> int:
        width, _ = self._backend.transcript_size()
        return width


async def test_shutdown_cancels_tasks_and_writes_exit_document():
    host = _Host(_Manager())
    stuck = asyncio.create_task(asyncio.sleep(30))
    host._conversation_task = stuck
    host._track_task(stuck)

    await host.shutdown()

    assert stuck.cancelled()
    assert host._shutdown_complete is True
    assert host._accepting_input is False
    assert host.activity_stopped == 1
    assert host._event_buffer.flushes == 1
    assert host._manager.closed == 1
    assert host._backend.exit_documents == ["exit-doc"]
    assert host.model.transcript.iter_widths == [90]


async def test_shutdown_is_idempotent_and_tolerates_unsubscribe_errors():
    host = _Host(_Manager())
    await host.shutdown()
    await host.shutdown()  # 第二次为空操作
    assert host._manager.closed == 1


async def test_shutdown_falls_back_to_close_runtime_when_manager_has_no_close():
    class _Bare:
        closed: bool = False

        def subscribe(self, _fn: Any) -> Any:
            return lambda: None

    runtime_closed = []
    bare = _Bare()
    host = _Host(bare, close_runtime=lambda: runtime_closed.append(True))  # type: ignore[arg-type]
    host._unsubscribe = None
    await host.shutdown()
    assert runtime_closed == [True]


async def test_shutdown_waits_for_sync_manager_close_without_await():
    manager = _Manager(async_close=False)
    host = _Host(manager)
    await host.shutdown()
    assert manager.closed == 1


async def test_track_task_consumes_exception_without_warning():
    host = _Host(_Manager())

    async def _boom() -> None:
        raise RuntimeError("boom")

    task = host._track_task(asyncio.create_task(_boom()))
    await asyncio.sleep(0)  # 让任务完成并触达 done 回调
    await asyncio.sleep(0)
    assert task not in host._background_tasks  # done callback 已清理
    assert task.done()


def test_exit_without_running_loop_uses_asyncio_run(monkeypatch):
    host = _Host(_Manager())
    calls: list[bool] = []

    def _fake_run(coro: Any) -> None:
        calls.append(True)
        coro.close()

    monkeypatch.setattr(asyncio, "run", _fake_run)
    host._exit()
    assert calls == [True]


async def test_exit_schedules_shutdown_on_running_loop():
    host = _Host(_Manager())
    host._exit()
    assert host._shutdown_task is not None
    await host._shutdown_task
    assert host._shutdown_complete is True


async def test_exit_is_noop_after_shutdown_complete():
    host = _Host(_Manager())
    host._shutdown_complete = True
    host._exit()
    assert host._shutdown_task is None


async def test_shutdown_cancels_task_supervisor():
    class _Supervisor:
        cancelled = 0

        def cancel(self) -> None:
            self.cancelled += 1

    host = _Host(_Manager())
    host._task_supervisor = _Supervisor()
    await host.shutdown()
    assert host._task_supervisor.cancelled == 1


async def test_shutdown_awaits_async_close_runtime_without_manager_close():
    class _Bare:
        def subscribe(self, _fn: Any) -> Any:
            return lambda: None

    closed: list[bool] = []

    async def _close_runtime() -> None:
        closed.append(True)

    host = _Host(_Bare(), close_runtime=_close_runtime)  # type: ignore[arg-type]
    host._unsubscribe = None
    await host.shutdown()
    assert closed == [True]


async def test_shutdown_times_out_on_task_ignoring_cancellation(monkeypatch):
    host = _Host(_Manager())

    async def _stubborn() -> None:
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            await asyncio.sleep(30)  # 拒绝退出

    host._conversation_task = asyncio.create_task(_stubborn())
    await asyncio.sleep(0)
    await host.shutdown()
    host._conversation_task.cancel()
