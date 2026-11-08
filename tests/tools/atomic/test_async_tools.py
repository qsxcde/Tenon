"""Cancellable async paths for web_fetch / find / grep.

These verify that the three high-risk tools expose a real ``ainvoke`` (so the
runtime treats them as ``supports_cancellation``) and that cancellation reaches
them. All accelerators and network calls are faked; nothing touches the network.
"""

from __future__ import annotations

import asyncio

import pytest

from tenon.tools.atomic import find as find_mod
from tenon.tools.atomic import grep as grep_mod
from tenon.tools.atomic.find import FindTool
from tenon.tools.atomic.grep import GrepTool
from tenon.tools.atomic.web_fetch import WebFetchTool
from tenon.tools.execution.search import ExternalSearchResult

pytestmark = pytest.mark.unit


def _touch(tmp_path, *names: str) -> None:
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x\n", encoding="utf-8")


# -- web_fetch ---------------------------------------------------------------


async def test_web_fetch_ainvoke_uses_async_fetcher():
    calls: list[str] = []

    async def fetch(url: str) -> str:
        calls.append(url)
        return "hello async"

    tool = WebFetchTool(async_fetcher=fetch)

    out = await tool.ainvoke(tool.Args(url="https://example.com"))

    assert "hello async" in out
    assert calls == ["https://example.com"]
    assert out.output_metadata["source"] == "web_fetch"


def test_web_fetch_declares_supports_cancellation():
    assert WebFetchTool().supports_cancellation is True


async def test_web_fetch_ainvoke_wraps_fetcher_error():
    async def fetch(url: str) -> str:
        raise OSError("boom")

    tool = WebFetchTool(async_fetcher=fetch)
    with pytest.raises(ValueError, match="抓取失败"):
        await tool.ainvoke(tool.Args(url="https://example.com"))


async def test_web_fetch_ainvoke_rejects_non_http():
    async def fetch(url: str) -> str:  # pragma: no cover - not reached
        return "x"

    tool = WebFetchTool(async_fetcher=fetch)
    with pytest.raises(ValueError, match="仅支持 http/https"):
        await tool.ainvoke(tool.Args(url="file:///etc/passwd"))


async def test_web_fetch_ainvoke_is_cancellable():
    started = asyncio.Event()

    async def slow(url: str) -> str:
        started.set()
        await asyncio.sleep(30)
        return "never"

    tool = WebFetchTool(async_fetcher=slow)
    task = asyncio.create_task(tool.ainvoke(tool.Args(url="https://example.com")))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# -- find --------------------------------------------------------------------


async def test_find_ainvoke_uses_async_fd(tmp_path, monkeypatch):
    _touch(tmp_path, "a.py", "b.txt")

    async def fake_search(name, args, cwd, **_):
        # fd 输出为 NUL 分隔的相对路径。
        return ExternalSearchResult(stdout=b"a.py\0b.txt\0")

    monkeypatch.setattr(find_mod, "run_optional_search_async", fake_search)
    tool = FindTool(cwd=str(tmp_path))

    out = await tool.ainvoke(tool.Args(pattern="*.py"))

    assert "a.py" in out
    assert "b.txt" not in out


async def test_find_ainvoke_falls_back_to_thread_when_fd_missing(tmp_path, monkeypatch):
    _touch(tmp_path, "a.py")

    async def no_accel(*a, **k):
        return None

    monkeypatch.setattr(find_mod, "run_optional_search_async", no_accel)
    tool = FindTool(cwd=str(tmp_path))

    out = await tool.ainvoke(tool.Args(pattern="*.py"))

    assert "a.py" in out


def test_find_declares_supports_cancellation():
    assert FindTool().supports_cancellation is True


# -- grep --------------------------------------------------------------------


async def test_grep_ainvoke_uses_async_rg(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("needle here\n", encoding="utf-8")

    async def fake_rg(*a, **k):
        return (["a.py:1: needle here"], False)

    monkeypatch.setattr(grep_mod, "run_rg_async", fake_rg)
    tool = GrepTool(cwd=str(tmp_path))

    out = await tool.ainvoke(tool.Args(pattern="needle"))

    assert "a.py:1: needle here" in out


async def test_grep_ainvoke_falls_back_to_thread(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("needle here\n", encoding="utf-8")

    async def no_accel(*a, **k):
        return None

    monkeypatch.setattr(grep_mod, "run_rg_async", no_accel)
    tool = GrepTool(cwd=str(tmp_path))

    out = await tool.ainvoke(tool.Args(pattern="needle"))

    assert "needle here" in out


def test_grep_declares_supports_cancellation():
    assert GrepTool().supports_cancellation is True


# -- runtime integration: cancellation is CONFIRMED, not UNSUPPORTED ----------


async def test_cancelling_async_web_fetch_reports_confirmed_cleanup():
    """A cancellable tool must yield CONFIRMED (not UNSUPPORTED) on cancel.

    This is the behaviour the fix targets: previously web_fetch ran in a thread
    and cancellation degraded to ``unsupported`` / ``cleanup_uncertain``.
    """
    from tenon.app.composition.tools.adapter import adapt_tools
    from tenon.core import ToolCall, ToolExecutionRuntime

    started = asyncio.Event()
    release = asyncio.Event()

    async def blocking(url: str) -> str:
        started.set()
        await release.wait()
        return "late"

    adapted = adapt_tools([WebFetchTool(async_fetcher=blocking)])[0]
    assert adapted.supports_cancellation is True
    runtime = ToolExecutionRuntime()
    task = asyncio.create_task(
        runtime.execute(
            adapted,
            ToolCall("wf-1", "web_fetch", {"url": "https://example.com"}),
            operation_id="op-1",
        )
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await task
        assert runtime.cleanup_status == "confirmed"
        assert runtime.cleanup_uncertain is False
    finally:
        release.set()
