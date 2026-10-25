"""MCP server 客户端的分支：未初始化、调用超时、错误结果与取消清理。

不启动后台线程、不连真实 server，submit 与结果提取用桩替换。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from types import SimpleNamespace
from typing import Any

import pytest

from tenon.tools.mcp import client as client_mod
from tenon.tools.mcp.client import McpServerClient

pytestmark = pytest.mark.unit


def _client() -> McpServerClient:
    return McpServerClient("demo", SimpleNamespace())


class _Loop:
    """只需支持 is_closed 的事件循环桩。"""

    def is_closed(self) -> bool:
        return False


def _initialized() -> McpServerClient:
    client = _client()
    client._loop = _Loop()  # type: ignore[assignment]
    client._session = SimpleNamespace()  # type: ignore[assignment]
    return client


def _future(*, error: bool = False) -> SimpleNamespace:
    return SimpleNamespace(is_error=error)


def test_start_is_idempotent_once_thread_exists():
    """已启动的 client 再次 start 直接返回,不重复建线程。"""
    client = _client()
    client._thread = object()  # type: ignore[assignment]

    client.start()

    assert client._thread is not None


def test_call_requires_initialized_server():
    """未完成 initialize 时调用给出一致错误,避免空指针式失败。"""
    client = _client()

    with pytest.raises(RuntimeError, match="未初始化"):
        client.call_tool("fmt", None)
    with pytest.raises(RuntimeError, match="未初始化"):
        client.call_tool_result("fmt", None)
    with pytest.raises(RuntimeError, match="未初始化"):
        client.submit_tool("fmt", None)


def test_submit_rejects_closed_client():
    """已关闭的 client 不再接受新调用。"""
    client = _initialized()
    client._closed = True

    with pytest.raises(RuntimeError, match="未初始化"):
        client.submit_tool("fmt", None)


def test_call_tool_timeout_cancels_future(monkeypatch):
    """同步调用超时 → 取消 future 并抛 TimeoutError。"""
    client = _initialized()

    class _Future:
        def __init__(self) -> None:
            self.cancelled = False

        def result(self, timeout=None):
            raise concurrent.futures.TimeoutError

        def cancel(self) -> None:
            self.cancelled = True

    future = _Future()
    monkeypatch.setattr(client, "submit_tool", lambda *args, **kwargs: future)

    with pytest.raises(TimeoutError, match="调用超时"):
        client.call_tool("fmt", None, timeout=1.0)

    assert future.cancelled is True


def test_call_tool_result_timeout_cancels_future(monkeypatch):
    """结构化调用超时同样取消 future。"""
    client = _initialized()

    class _Future:
        cancelled = False

        def result(self, timeout=None):
            raise concurrent.futures.TimeoutError

        def cancel(self) -> None:
            self.cancelled = True

    future = _Future()
    monkeypatch.setattr(client, "submit_tool", lambda *args, **kwargs: future)

    with pytest.raises(TimeoutError, match="调用超时"):
        client.call_tool_result("fmt", None, timeout=1.0)

    assert future.cancelled is True


def test_call_tool_surfaces_error_result(monkeypatch):
    """server 标记 is_error 时抛错并带出文本。"""
    client = _initialized()
    message = SimpleNamespace(text="工具执行失败")
    monkeypatch.setattr(client_mod, "extract_result", lambda result: message)
    monkeypatch.setattr(
        client,
        "submit_tool",
        lambda *args, **kwargs: SimpleNamespace(result=lambda timeout: _future(error=True)),
    )

    with pytest.raises(RuntimeError, match="工具执行失败"):
        client.call_tool("fmt", None)


def test_call_tool_returns_text(monkeypatch):
    """正常结果返回提取后的文本。"""
    client = _initialized()
    monkeypatch.setattr(
        client_mod, "extract_result", lambda result: SimpleNamespace(text="ok-output")
    )
    monkeypatch.setattr(
        client,
        "submit_tool",
        lambda *args, **kwargs: SimpleNamespace(result=lambda timeout: _future(error=False)),
    )

    assert client.call_tool("fmt", None) == "ok-output"


async def test_acall_tool_returns_text(monkeypatch):
    """异步桥接把 future 结果转换为文本。"""
    client = _initialized()
    future: concurrent.futures.Future[Any] = concurrent.futures.Future()
    future.set_result(_future())
    monkeypatch.setattr(client, "submit_tool", lambda *args, **kwargs: future)
    monkeypatch.setattr(
        client_mod, "extract_result", lambda result: SimpleNamespace(text="async-out")
    )

    assert await client.acall_tool("fmt", None) == "async-out"


async def test_acall_tool_result_surfaces_error(monkeypatch):
    """结构化异步调用在 is_error 时抛错。"""
    client = _initialized()
    future: concurrent.futures.Future[Any] = concurrent.futures.Future()
    future.set_result(_future(error=True))
    monkeypatch.setattr(client, "submit_tool", lambda *args, **kwargs: future)
    monkeypatch.setattr(
        client_mod, "extract_result", lambda result: SimpleNamespace(text="失败原因")
    )

    with pytest.raises(RuntimeError, match="失败原因"):
        await client.acall_tool_result("fmt", None)


async def test_acall_tool_cancellation_propagates(monkeypatch):
    """取消调用任务时取消底层 future 并抛出 CancelledError。"""
    client = _initialized()
    future: concurrent.futures.Future[Any] = concurrent.futures.Future()
    monkeypatch.setattr(client, "submit_tool", lambda *args, **kwargs: future)

    task = asyncio.create_task(client.acall_tool("fmt", None))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert future.cancelled() is True


def test_close_cancels_active_calls():
    """close 取消所有在途调用,避免后台挂起。"""
    client = _client()
    in_flight: concurrent.futures.Future[Any] = concurrent.futures.Future()
    client._active_calls.add(in_flight)

    client.close()

    assert in_flight.cancelled() is True
    assert client._closed is True
