"""会话动作命令：压缩、输出分页/导出、重试、继续、分叉与会话动作调度。

补齐 ``session/actions.py`` 与 ``session/action_runner.py`` 的错误与边界路径，
这些分支不发起模型请求，全部离线可测。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from codeagent.app.tui.commands.parser import Command
from codeagent.session.persistence import (
    RecoveryDiagnostic,
    SessionRecoveryError,
    SessionRecoveryReport,
)
from tests.tui.view.fixtures import *  # noqa: F401,F403


def _text(app, width: int = 120) -> str:
    return "\n".join(app.model.transcript.all_lines(width))


# -- /compact ---------------------------------------------------------------


def test_compact_without_current_session():
    """/compact 无当前会话时就地提示,不排队任务。"""
    app, _backend, manager = _make_app()
    manager.current = None

    app._cmd_compact(Command("compact", ()))

    assert "(无当前会话)" in _text(app)
    assert app._session_action_task is None


def test_compact_with_session_lacking_compact_api():
    """/compact 遇到不支持压缩的会话对象时提示不可用。"""
    app, _backend, manager = _make_app()
    manager.current = SimpleNamespace(session_id="s-1")

    app._cmd_compact(Command("compact", ()))

    assert "不支持压缩" in _text(app)


async def test_run_compact_reports_unexpected_failure():
    """压缩抛异常 → 记录完整诊断并给出可操作提示。"""

    class BrokenSession(FakeSession):
        async def compact(self) -> bool:
            raise RuntimeError("boom")

    app, backend, _manager = _make_app()
    backend.on_resize(app._schedule_render)

    await app._run_compact(BrokenSession())

    assert "压缩上下文失败，请查看日志。" in _text(app)


async def test_run_compact_short_context_message():
    """压缩返回 False → 提示上下文较短。"""

    class ShortSession(FakeSession):
        async def compact(self) -> bool:
            return False

    app, backend, _manager = _make_app()
    backend.on_resize(app._schedule_render)

    await app._run_compact(ShortSession())

    assert "上下文较短,无需压缩" in _text(app)


# -- /output ----------------------------------------------------------------


def test_output_next_without_more_pages():
    """/output next 无更多页 → 提示,不改变游标。"""
    app, _backend, _manager = _make_app()
    app.model.page_output = lambda delta, call_id=None: False  # type: ignore[method-assign]

    app._cmd_output(Command("output", ("next",)))

    assert "没有更多输出页" in _text(app)


def test_output_prev_passes_negative_delta():
    """/output prev 用 -1 翻页,并把 tool-call-id 透传。"""
    app, _backend, _manager = _make_app()
    calls: list[tuple[int, str | None]] = []

    def page_output(delta: int, call_id: str | None = None) -> bool:
        calls.append((delta, call_id))
        return True

    app.model.page_output = page_output  # type: ignore[method-assign]

    app._cmd_output(Command("output", ("prev", "call-9")))

    assert calls == [(-1, "call-9")]
    assert "没有更多输出页" not in _text(app)


def test_output_export_requires_path():
    """/output export 缺路径 → 用法提示。"""
    app, _backend, _manager = _make_app()

    app._cmd_output(Command("output", ("export",)))

    assert "用法: /output export <path> [tool-call-id]" in _text(app)


def test_output_export_success_reports_path():
    """/output export 成功 → 反馈导出路径。"""
    app, _backend, _manager = _make_app()
    app.model.export_output = (  # type: ignore[method-assign]
        lambda path, call_id=None: "/tmp/out.txt"
    )

    app._cmd_output(Command("output", ("export", "/tmp/out.txt")))

    assert "已导出工具输出: /tmp/out.txt" in _text(app)


def test_output_export_oserror_is_reported():
    """/output export 写盘失败 → 保留错误原因。"""
    app, _backend, _manager = _make_app()

    def failing_export(path: str, call_id: str | None = None) -> str:
        raise OSError("permission denied")

    app.model.export_output = failing_export  # type: ignore[method-assign]

    app._cmd_output(Command("output", ("export", "/root/x")))

    assert "输出导出失败: permission denied" in _text(app)


def test_output_unknown_action_shows_usage():
    """/output 未知动作 → 用法提示。"""
    app, _backend, _manager = _make_app()

    app._cmd_output(Command("output", ("sideways",)))

    assert "用法: /output next|prev" in _text(app)


# -- /retry -----------------------------------------------------------------


async def test_retry_dispatches_when_failure_is_retryable():
    """/retry 可安全重试 → 排队调用 session.retry()。"""
    app, _backend, manager = _make_app()
    calls: list[str] = []

    async def retry() -> None:
        calls.append("retried")

    manager.current.last_failure = {"retryable": True, "prompt": "p"}
    manager.current.retry = retry  # type: ignore[method-assign]

    app._cmd_retry(Command("retry", ()))
    for _ in range(10):
        await asyncio.sleep(0)

    assert calls == ["retried"]


def test_retry_without_failure_suggests_continue():
    """/retry 无失败记录 → 引导使用 /continue。"""
    app, _backend, manager = _make_app()
    manager.current.last_failure = None

    app._cmd_retry(Command("retry", ()))

    assert "不可安全重试" in _text(app)


async def test_run_retry_reports_value_error_and_unexpected_error():
    """重试失败分两类呈现:业务错误原文与未知异常的可操作提示。"""

    class ValueErrorSession(FakeSession):
        async def retry(self) -> None:
            raise ValueError("没有可重试的失败回合")

    class BrokenSession(FakeSession):
        async def retry(self) -> None:
            raise RuntimeError("boom")

    app, backend, _manager = _make_app()
    backend.on_resize(app._schedule_render)

    await app._run_retry(ValueErrorSession())
    await app._run_retry(BrokenSession())

    text = _text(app)
    assert "没有可重试的失败回合" in text
    assert "重试失败，请查看日志。" in text


# -- /continue --------------------------------------------------------------


def test_continue_requires_message():
    """/continue 无参数 → 用法提示,不发起对话。"""
    app, _backend, manager = _make_app()

    app._cmd_continue(Command("continue", ()))

    assert "用法: /continue <新消息>" in _text(app)
    assert manager.current.run_texts == []


# -- /fork ------------------------------------------------------------------


def test_fork_without_current_session():
    """/fork 无当前会话 → 提示,不调用管理器。"""
    app, _backend, manager = _make_app()
    manager.current = None

    app._cmd_fork(Command("fork", ()))

    assert "(无当前会话)" in _text(app)
    assert manager.fork_calls == []


def test_fork_value_error_is_reported():
    """/fork 失败(会话不存在等)→ 保留异常原文。"""
    app, _backend, manager = _make_app()

    def failing_fork(session_id: str, message_id: str | None = None):
        raise ValueError("消息不存在: m-1")

    manager.fork = failing_fork  # type: ignore[method-assign]

    app._cmd_fork(Command("fork", ("m-1",)))

    assert "消息不存在: m-1" in _text(app)


def test_fork_sync_fallback_keeps_original_and_switch():
    """/fork 无异步 API 时走同步分支:切换并提示原会话保留。"""
    app, _backend, manager = _make_app()
    original = manager.current

    app._cmd_fork(Command("fork", ()))

    assert manager.fork_calls == [(original.session_id, None)]
    assert "原会话保留" in _text(app)


# -- _schedule_session_action ----------------------------------------------


def test_schedule_session_action_without_manager_api_returns_false():
    """管理器无对应方法时由调用方回退同步路径。"""
    app, _backend, _manager = _make_app()

    assert app._schedule_session_action("no_such_method", lambda session: "x") is False


def test_schedule_session_action_without_running_loop_returns_false():
    """同步上下文没有事件循环 → 交回调用方走同步分支。"""
    app, _backend, manager = _make_app()

    async def fork_async(*args):  # pragma: no cover - 不应被调用
        raise AssertionError("同步上下文不应排队异步动作")

    manager.fork_async = fork_async  # type: ignore[method-assign]

    assert app._schedule_session_action("fork_async", lambda session: "x") is False


async def test_schedule_session_action_runs_and_hydrates():
    """异步生命周期 API 成功 → 刷新当前会话并渲染消息。"""
    app, backend, manager = _make_app()
    backend.on_resize(app._schedule_render)

    async def fork_async(session_id: str, message_id: str | None = None):
        return manager.fork(session_id, message_id)

    manager.fork_async = fork_async  # type: ignore[method-assign]

    queued = app._schedule_session_action(
        "fork_async",
        lambda session: f"已分叉 {session.session_id}",
        manager.current.session_id,
        None,
    )
    for _ in range(20):
        await asyncio.sleep(0)

    assert queued is True
    assert "已分叉" in _text(app)
    assert app._session_action_task is None


async def test_schedule_session_action_rejects_concurrent_request():
    """上一个会话动作未结束时只提示,不重复排队。"""
    app, backend, manager = _make_app()
    backend.on_resize(app._schedule_render)
    manager.fork_async = lambda *args: None  # type: ignore[method-assign]

    async def pending() -> None:
        await asyncio.sleep(1)

    app._session_action_task = asyncio.get_running_loop().create_task(pending())
    try:
        queued = app._schedule_session_action("fork_async", lambda session: "x")
        assert queued is True
        assert "正在等待上一个会话操作完成" in _text(app)
    finally:
        app._session_action_task.cancel()
        await asyncio.gather(app._session_action_task, return_exceptions=True)


async def test_schedule_session_action_reports_value_error():
    """管理器拒绝操作(ValueError)→ 呈现业务错误原文。"""
    app, backend, manager = _make_app()
    backend.on_resize(app._schedule_render)

    async def fork_async(*args):
        raise ValueError("会话不存在: s-404")

    manager.fork_async = fork_async  # type: ignore[method-assign]

    app._schedule_session_action("fork_async", lambda session: "x", "s-404", None)
    for _ in range(20):
        await asyncio.sleep(0)

    assert "会话不存在: s-404" in _text(app)


async def test_schedule_session_action_reports_unexpected_error():
    """未预期异常 → 记录诊断并给出通用提示。"""
    app, backend, manager = _make_app()
    backend.on_resize(app._schedule_render)

    async def fork_async(*args):
        raise RuntimeError("boom")

    manager.fork_async = fork_async  # type: ignore[method-assign]

    app._schedule_session_action("fork_async", lambda session: "x")
    for _ in range(20):
        await asyncio.sleep(0)

    assert "会话操作失败，请查看日志。" in _text(app)


async def test_schedule_session_action_formats_recovery_error():
    """SessionRecoveryError → 渲染结构化恢复报告。"""
    report = SessionRecoveryReport(
        "bad",
        "unavailable",
        (
            RecoveryDiagnostic(
                "incompatible_version",
                "会话版本不兼容",
                "无法安全解释会话记录",
                "请升级客户端后迁移",
            ),
        ),
    )
    app, backend, manager = _make_app()
    backend.on_resize(app._schedule_render)

    async def fork_async(*args):
        raise SessionRecoveryError(report)

    manager.fork_async = fork_async  # type: ignore[method-assign]

    app._schedule_session_action("fork_async", lambda session: "x")
    for _ in range(20):
        await asyncio.sleep(0)

    text = _text(app)
    assert "incompatible_version" in text
    assert "请升级客户端后迁移" in text
