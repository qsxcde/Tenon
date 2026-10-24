"""Subagent 记录协调器：事件转换失败、无事件循环的同步落库与任务收尾诊断。

事件解码用桩替换,不构造真实委派。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from codeagent.core.contracts.events import AgentEvent, EventType
from codeagent.session.persistence import subagent_runtime as runtime_mod
from codeagent.session.persistence.subagent_runtime import SubagentRecordCoordinator

pytestmark = pytest.mark.unit


def _record(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "delegation_id": "d-1",
        "status": "running",
        "phase": "child",
        "child_run_id": "child-1",
        "attempt_id": "a-1",
        "summary": "",
        "reason_code": None,
        "diagnostics": (),
        "cleanup_uncertain": False,
        "result": None,
    }
    base.update(overrides)
    record = SimpleNamespace(**base)
    record.is_terminal = base["status"] in {"completed", "failed", "cancelled"}
    return record


def _coordinator(append) -> SubagentRecordCoordinator:
    return SubagentRecordCoordinator(append, lambda: True)


def test_record_diagnostic_is_bounded():
    """诊断消息公开可写且有上限,避免无限增长。"""
    coordinator = _coordinator(lambda record: None)

    for index in range(10):
        coordinator.record_diagnostic(f"diag-{index}")

    assert len(coordinator.diagnostics) == 8
    assert coordinator.diagnostics[0] == "diag-0"


def test_observe_records_conversion_failure(monkeypatch):
    """事件无法转换时记录诊断并丢弃,不影响后续事件。"""

    def explode(event, expected_parent_run_id):
        raise ValueError("缺少 delegation_id")

    monkeypatch.setattr(runtime_mod, "record_from_event", explode)
    coordinator = _coordinator(lambda record: pytest.fail("不应写入"))

    coordinator.observe(AgentEvent(EventType.SUBAGENT_QUEUED), None)

    assert coordinator.diagnostics == ["事件转换失败: 缺少 delegation_id"]


def test_observe_skips_when_backend_cannot_append(monkeypatch):
    """后端不可写时不缓存记录,也不排队任务。"""
    monkeypatch.setattr(
        runtime_mod, "record_from_event", lambda event, expected_parent_run_id: _record()
    )
    coordinator = SubagentRecordCoordinator(lambda record: pytest.fail("不应写入"), lambda: False)

    coordinator.observe(AgentEvent(EventType.SUBAGENT_QUEUED), None)

    assert coordinator.records == []
    assert coordinator.diagnostics == []


def test_observe_ignores_duplicate_and_terminal_updates(monkeypatch):
    """终态记录不再更新,相同签名的事件被去重。"""
    appended: list[Any] = []
    coordinator = _coordinator(appended.append)
    terminal = _record(status="completed")
    monkeypatch.setattr(
        runtime_mod, "record_from_event", lambda event, expected_parent_run_id: terminal
    )
    coordinator.observe(AgentEvent(EventType.SUBAGENT_FINISHED), None)

    # 终态后再来任何事件都不应覆盖
    monkeypatch.setattr(
        runtime_mod,
        "record_from_event",
        lambda event, expected_parent_run_id: _record(status="running"),
    )
    coordinator.observe(AgentEvent(EventType.SUBAGENT_PROGRESS), None)

    assert coordinator.records == [terminal]


def test_observe_without_running_loop_appends_synchronously(monkeypatch):
    """同步上下文（无事件循环）直接落库,不丢记录。"""
    appended: list[Any] = []
    record = _record()
    monkeypatch.setattr(
        runtime_mod, "record_from_event", lambda event, expected_parent_run_id: record
    )
    coordinator = _coordinator(appended.append)

    coordinator.observe(AgentEvent(EventType.SUBAGENT_QUEUED), None)

    assert appended == [record]
    assert coordinator.records == [record]


def test_observe_sync_append_failure_is_diagnosed(monkeypatch):
    """同步落库失败只记录诊断,父回合继续。"""

    def boom(record):
        raise RuntimeError("disk full")

    monkeypatch.setattr(
        runtime_mod, "record_from_event", lambda event, expected_parent_run_id: _record()
    )
    coordinator = _coordinator(boom)

    coordinator.observe(AgentEvent(EventType.SUBAGENT_QUEUED), None)

    assert coordinator.diagnostics == ["同步写入失败: disk full"]


async def test_persist_records_async_append_failure():
    """异步落库失败记录诊断,不向父回合抛错。"""

    def boom(record):
        raise RuntimeError("disk full")

    coordinator = _coordinator(boom)

    await coordinator._persist(_record())

    assert coordinator.diagnostics == ["异步写入失败: disk full"]


async def test_finish_task_records_unexpected_exception():
    """任务以异常结束时记录诊断,便于排查写入失败。"""
    coordinator = _coordinator(lambda record: None)

    async def boom() -> None:
        raise RuntimeError("write failed")

    task = asyncio.get_running_loop().create_task(boom())
    with pytest.raises(RuntimeError):
        await task

    coordinator._finish_task(task)

    assert coordinator.diagnostics == ["异步写入任务失败: write failed"]


async def test_finish_task_ignores_cancelled_task():
    """被取消的任务不产生诊断噪音。"""
    coordinator = _coordinator(lambda record: None)
    task = asyncio.get_running_loop().create_task(asyncio.sleep(5))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    coordinator._finish_task(task)

    assert coordinator.diagnostics == []
