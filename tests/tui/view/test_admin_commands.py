"""维护类 TUI 命令：快照恢复、会话导出、MCP 重载、委派与上下文窗口。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from tenon.ai.catalog.spec import ModelSpec
from tenon.app.composition.tui.admin import model_override_record
from tenon.app.tui.application import TuiApp
from tenon.app.tui.commands.parser import Command
from tenon.app.tui.presentation.primitives import rich_to_plain
from tenon.app.tui.presentation.status import FooterInfo
from tests.fixtures.tui import FakeBackend
from tests.tui.view.fixtures import FakeManager


@dataclass(frozen=True)
class _Entry:
    seq: int
    created_at: str
    path: str
    existed: bool


class FakeAdmin:
    """记录调用并返回固定结果的维护端口桩。"""

    def __init__(self) -> None:
        self.checkpoints = [_Entry(3, "2026-10-25T10:00:00", "/w/a.py", True)]
        self.restored = 0
        self.reloads = 0
        self.cancelled: list[str] = []
        self.window_calls: list[int] = []
        self.active = {"d-1": "child-1"}

    def list_checkpoints(self, limit: int = 20) -> list[_Entry]:
        return self.checkpoints[:limit]

    def restore_checkpoint(self) -> _Entry:
        self.restored += 1
        return self.checkpoints[0]

    async def reload_runtime(self) -> tuple[str, str]:
        self.reloads += 1
        return "m-reloaded", "high"

    def subagent_snapshot(self) -> dict[str, Any]:
        return {
            "max_concurrency": 2,
            "configured_max_concurrency": 4,
            "active": dict(self.active),
        }

    async def cancel_subagent(self, delegation_id: str) -> bool:
        if delegation_id not in self.active:
            return False
        del self.active[delegation_id]
        self.cancelled.append(delegation_id)
        return True

    async def set_context_window(self, tokens: int) -> tuple[int, str]:
        self.window_calls.append(tokens)
        return tokens, "catalog"


def _make_app(admin: Any = None) -> tuple[TuiApp, FakeBackend]:
    backend = FakeBackend()
    app = TuiApp(
        FakeManager(),
        backend,
        admin=admin,
        footer=FooterInfo(model="m", effort="low", cwd="/w"),
    )
    backend.on_submit(app._submit)
    backend.on_interrupt(app._interrupt)
    backend.on_input_changed(app._on_input_changed)
    backend.on_resize(app._schedule_render)
    return app, backend


def _rendered(backend: FakeBackend) -> str:
    return "\n".join("\n".join(rich_to_plain(lines)) for lines in backend.renders)


async def _wait_for(backend: FakeBackend, needle: str, timeout: float = 1.0) -> str:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        text = _rendered(backend)
        if needle in text:
            return text
        await asyncio.sleep(0.01)
    raise AssertionError(f"未渲染出 {needle!r};当前渲染: {_rendered(backend)!r}")


async def test_undo_list_renders_recent_checkpoints():
    """/undo list 列出快照 seq、类型与路径。"""
    admin = FakeAdmin()
    app, backend = _make_app(admin)
    backend.submit("/undo list")
    text = await _wait_for(backend, "写前快照")
    assert "seq=3" in text and "/w/a.py" in text and "改写" in text


async def test_undo_restores_latest_checkpoint():
    """/undo 无参恢复最近快照并提示结果。"""
    admin = FakeAdmin()
    app, backend = _make_app(admin)
    backend.submit("/undo")
    text = await _wait_for(backend, "已恢复")
    assert admin.restored == 1 and "seq=3" in text


async def test_undo_without_admin_reports_unsupported():
    """未注入维护端口时给出可操作提示,而不是静默失败。"""
    app, backend = _make_app(None)
    backend.submit("/undo")
    await _wait_for(backend, "未注入维护端口")


async def test_export_writes_session_document(tmp_path):
    """/export <path> 把当前会话文档写到文件。"""
    app, backend = _make_app(FakeAdmin())
    app.model.append_info("导出内容示例")
    target = tmp_path / "nested" / "session.md"
    backend.submit(f"/export {target}")
    await _wait_for(backend, "已导出")
    written = target.read_text(encoding="utf-8")
    assert "导出内容示例" in written


async def test_export_requires_path():
    """/export 无参只提示用法。"""
    app, backend = _make_app(FakeAdmin())
    backend.submit("/export")
    await _wait_for(backend, "用法: /export <path>")


async def test_mcp_reload_rebuilds_runtime_and_updates_status():
    """/mcp reload 触发运行时重建并采用返回的模型名。"""
    admin = FakeAdmin()
    app, backend = _make_app(admin)
    backend.submit("/mcp reload")
    await _wait_for(backend, "已重载 MCP")
    assert admin.reloads == 1
    assert app.model.status.model == "m-reloaded"


async def test_subagents_lists_active_delegations():
    """/subagents 展示并发上限与活跃委派。"""
    admin = FakeAdmin()
    app, backend = _make_app(admin)
    backend.submit("/subagents")
    text = await _wait_for(backend, "活跃委派")
    assert "d-1" in text and "child-1" in text and "并发上限: 2" in text


async def test_subagents_cancel_invokes_port():
    """/subagents cancel <id> 交给端口取消并反馈。"""
    admin = FakeAdmin()
    app, backend = _make_app(admin)
    backend.submit("/subagents cancel d-1")
    await _wait_for(backend, "已取消委派")
    assert admin.cancelled == ["d-1"]


async def test_subagents_cancel_unknown_id_reports_miss():
    """取消不存在的委派给出明确提示。"""
    app, backend = _make_app(FakeAdmin())
    backend.submit("/subagents cancel d-404")
    await _wait_for(backend, "未找到活跃委派")


async def test_context_window_shows_current_and_usage():
    """/context-window 无参显示当前窗口与用法。"""
    app, backend = _make_app(FakeAdmin())
    backend.submit("/context-window")
    text = await _wait_for(backend, "上下文窗口")
    assert "用法: /context-window" in text


async def test_context_window_accepts_kilobyte_suffix():
    """/context-window 128k 换算为 131072 并写出。"""
    admin = FakeAdmin()
    app, backend = _make_app(admin)
    backend.submit("/context-window 128k")
    await _wait_for(backend, "已设置上下文窗口")
    assert admin.window_calls == [131_072]


async def test_context_window_accepts_grouped_digits():
    """/context-window 131,072 去掉千分位后原样写入。"""
    admin = FakeAdmin()
    app, backend = _make_app(admin)
    backend.submit("/context-window 131,072")
    await _wait_for(backend, "已设置上下文窗口")
    assert admin.window_calls == [131_072]


async def test_context_window_rejects_invalid_value():
    """非法窗口值就地报错,不触达端口。"""
    admin = FakeAdmin()
    app, backend = _make_app(admin)
    backend.submit("/context-window abc")
    await _wait_for(backend, "必须是正整数")
    assert admin.window_calls == []


def test_model_override_record_preserves_metadata():
    """写回 models.json 时保留窗口以外的元数据,避免 upsert 整体替换丢字段。"""
    spec = ModelSpec(
        id="deepseek-v4-pro",
        reasoning=True,
        max_tokens=8192,
        context_window=256_000,
        tool_calling=True,
        prompt_cache=True,
        aliases=("pro",),
    )
    record = model_override_record(spec, 131_072)
    assert record == {
        "id": "deepseek-v4-pro",
        "contextWindow": 131_072,
        "reasoning": True,
        "maxTokens": 8192,
        "toolCalling": True,
        "promptCache": True,
        "aliases": ["pro"],
    }


class FaultyAdmin(FakeAdmin):
    """按开关注入失败与空数据的维护端口变体。"""

    def __init__(self) -> None:
        super().__init__()
        self.checkpoints = []
        self.active = {}
        self.restore_error: Exception | None = None
        self.snapshot_error: Exception | None = None
        self.cancel_error: Exception | None = None
        self.reload_error: Exception | None = None
        self.window_error: Exception | None = None

    def restore_checkpoint(self) -> _Entry:
        if self.restore_error is not None:
            raise self.restore_error
        return super().restore_checkpoint()

    def subagent_snapshot(self) -> dict[str, Any]:
        if self.snapshot_error is not None:
            raise self.snapshot_error
        return super().subagent_snapshot()

    async def cancel_subagent(self, delegation_id: str) -> bool:
        if self.cancel_error is not None:
            raise self.cancel_error
        return await super().cancel_subagent(delegation_id)

    async def reload_runtime(self) -> tuple[str, str]:
        if self.reload_error is not None:
            raise self.reload_error
        return await super().reload_runtime()

    async def set_context_window(self, tokens: int) -> tuple[int, str]:
        if self.window_error is not None:
            raise self.window_error
        return await super().set_context_window(tokens)


def _text(app: TuiApp) -> str:
    return "\n".join(app.model.transcript.all_lines(120))


def test_undo_preview_without_checkpoints():
    """/undo preview 无快照 → 明确提示而不是空消息。"""
    app, _backend = _make_app(FaultyAdmin())

    app._cmd_undo(Command("undo", ("preview",)))

    assert "写前快照: (无)" in _text(app)


def test_undo_preview_lists_target_and_missing_file_note():
    """/undo preview 展示 seq/path,新建文件的快照标注恢复会删除。"""
    admin = FakeAdmin()
    admin.checkpoints = [_Entry(1, "2026-10-25T09:00:00", "/w/new.py", False)]
    app, _backend = _make_app(admin)

    app._cmd_undo(Command("undo", ("preview",)))

    text = _text(app)
    assert "将恢复: /w/new.py (seq=1)" in text
    assert "恢复时会删除" in text


def test_undo_unknown_action_shows_usage():
    """/undo 未知动作 → 用法提示。"""
    app, _backend = _make_app(FakeAdmin())

    app._cmd_undo(Command("undo", ("sideways",)))

    assert "用法: /undo [list|preview]" in _text(app)


def test_undo_restore_failure_reports_reason():
    """/undo 恢复失败(权限/IO)→ 保留错误原因。"""
    admin = FaultyAdmin()
    admin.restore_error = OSError("permission denied")
    app, _backend = _make_app(admin)

    app._cmd_undo(Command("undo", ()))

    assert "快照操作失败:permission denied" in _text(app)


async def test_export_oserror_is_reported(tmp_path):
    """/export 目标不可写 → 提示失败原因。"""
    app, _backend = _make_app(FakeAdmin())

    app._cmd_export(Command("export", (str(tmp_path),)))

    assert "导出失败:" in _text(app)


def test_subagents_without_admin_reports_unsupported():
    """/subagents 未注入维护端口 → 可操作提示。"""
    app, _backend = _make_app(None)

    app._cmd_subagents(Command("subagents", ()))

    assert "不支持委派管理" in _text(app)


def test_subagents_cancel_requires_identifier():
    """/subagents cancel 缺 id → 用法提示,不触达端口。"""
    app, _backend = _make_app(FakeAdmin())

    app._cmd_subagents(Command("subagents", ("cancel",)))

    assert "用法: /subagents cancel <delegation-id>" in _text(app)


def test_subagents_unknown_action_shows_usage():
    """/subagents 未知动作 → 用法提示。"""
    app, _backend = _make_app(FakeAdmin())

    app._cmd_subagents(Command("subagents", ("explode",)))

    assert "用法: /subagents [list|cancel" in _text(app)


def test_subagents_snapshot_failure_reports_reason():
    """读取委派状态失败 → 保留原因。"""
    admin = FaultyAdmin()
    admin.snapshot_error = ValueError("runner 尚未装配")
    app, _backend = _make_app(admin)

    app._cmd_subagents(Command("subagents", ()))

    assert "读取委派状态失败:runner 尚未装配" in _text(app)


def test_subagents_empty_active_lists_none():
    """/subagents 无活跃委派 → 显式 (无) 行。"""
    app, _backend = _make_app(FaultyAdmin())

    app._cmd_subagents(Command("subagents", ()))

    assert "(无)" in _text(app)


async def test_cancel_subagent_failure_reports_diagnostic():
    """取消委派抛异常 → 通用提示,不中断 TUI。"""
    admin = FaultyAdmin()
    admin.cancel_error = RuntimeError("boom")
    app, _backend = _make_app(admin)

    app._cmd_subagents(Command("subagents", ("cancel", "d-1")))
    for _ in range(20):
        await asyncio.sleep(0)

    assert "取消委派失败，请查看日志。" in _text(app)


async def test_reload_failure_reports_diagnostic():
    """/mcp reload 失败 → 通用提示并保留当前状态。"""
    admin = FaultyAdmin()
    admin.reload_error = RuntimeError("boom")
    app, _backend = _make_app(admin)

    app._reload_mcp()
    for _ in range(20):
        await asyncio.sleep(0)

    assert "重载运行时失败，请查看日志。" in _text(app)


def test_context_window_without_admin_reports_unsupported():
    """/context-window 未注入维护端口 → 可操作提示。"""
    app, _backend = _make_app(None)

    app._cmd_context_window(Command("context-window", ()))

    assert "不支持修改上下文窗口" in _text(app)


def test_context_window_shows_numeric_window_and_source():
    """/context-window 无参 → 展示窗口、来源与用法。"""
    app, _backend = _make_app(FakeAdmin())
    app.model.status.model_capabilities = SimpleNamespace(
        context_window=256_000, window_source="catalog"
    )

    app._cmd_context_window(Command("context-window", ()))

    text = _text(app)
    assert "上下文窗口: 256,000 · 来源 catalog" in text
    assert "用法: /context-window <tokens>" in text


async def test_context_window_accepts_megabyte_suffix():
    """/context-window 1m 换算为 1,048,576。"""
    admin = FakeAdmin()
    app, _backend = _make_app(admin)

    app._cmd_context_window(Command("context-window", ("1m",)))
    for _ in range(20):
        await asyncio.sleep(0)

    assert admin.window_calls == [1_048_576]


async def test_context_window_rejects_zero_value():
    """窗口为 0 → 就地报错,不写盘。"""
    admin = FakeAdmin()
    app, _backend = _make_app(admin)

    app._cmd_context_window(Command("context-window", ("0",)))

    assert "必须大于 0" in _text(app)
    assert admin.window_calls == []


def test_undo_list_without_checkpoints():
    """/undo list 无快照 → 明确提示。"""
    app, _backend = _make_app(FaultyAdmin())

    app._cmd_undo(Command("undo", ("list",)))

    assert "写前快照: (无)" in _text(app)


def test_reload_mcp_without_admin_reports_unsupported():
    """/mcp reload 未注入维护端口 → 可操作提示。"""
    app, _backend = _make_app(None)

    app._reload_mcp()

    assert "不支持重载 MCP" in _text(app)


async def test_context_window_value_error_is_reported():
    """窗口写入被端口拒绝 → 呈现业务错误原文。"""
    admin = FaultyAdmin()
    admin.window_error = ValueError("窗口超出模型上限")
    app, _backend = _make_app(admin)

    app._cmd_context_window(Command("context-window", ("200k",)))
    for _ in range(20):
        await asyncio.sleep(0)

    assert "设置上下文窗口失败:窗口超出模型上限" in _text(app)


async def test_context_window_unexpected_error_is_reported():
    """窗口写入抛未预期异常 → 通用提示,不崩溃。"""
    admin = FaultyAdmin()
    admin.window_error = RuntimeError("boom")
    app, _backend = _make_app(admin)

    app._cmd_context_window(Command("context-window", ("64k",)))
    for _ in range(20):
        await asyncio.sleep(0)

    assert "设置上下文窗口失败，请查看日志。" in _text(app)
