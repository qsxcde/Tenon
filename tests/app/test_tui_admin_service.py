"""组合根维护端口（TuiAdminService）与模型覆盖记录构造。

这些适配只做委托与兜底，全部离线可测，标记 unit 进入快速质量集。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tenon.ai.catalog.spec import ModelSpec
from tenon.app.composition.tui.admin import TuiAdminService, model_override_record

pytestmark = pytest.mark.unit


class _Runner:
    """记录取消调用的委派执行器桩。"""

    def __init__(self, active: dict[str, str | None] | None = None) -> None:
        self.max_concurrency = 3
        self.active_delegations = {"d-1": "child-1"} if active is None else active
        self.cancelled: list[str] = []

    async def cancel(self, delegation_id: str) -> bool:
        self.cancelled.append(delegation_id)
        return delegation_id in self.active_delegations


def _service(
    *,
    runner: _Runner | None = None,
    checkpoints_root: Path | None = None,
    reload_result: tuple[str, str] = ("m-new", "high"),
    window_result: tuple[int, str] = (131_072, "catalog"),
    max_concurrency: int = 2,
) -> tuple[TuiAdminService, dict[str, Any]]:
    calls: dict[str, Any] = {}
    holder: dict[str, Any] = {"runner": runner}

    async def reload_runtime() -> tuple[str, str]:
        calls["reload"] = calls.get("reload", 0) + 1
        return reload_result

    async def set_context_window(tokens: int) -> tuple[int, str]:
        calls["window"] = tokens
        return window_result

    service = TuiAdminService(
        checkpoints_root=lambda: checkpoints_root or Path("/tmp/cp"),
        reload_runtime=reload_runtime,
        subagent_runner=lambda: holder["runner"],
        set_context_window=set_context_window,
        max_concurrency=lambda: max_concurrency,
    )
    return service, calls


def test_model_override_record_includes_name_when_present():
    """有展示名时一并写回,避免覆盖记录丢失模型名称。"""
    spec = ModelSpec(id="m-1", name="示例模型", context_window=8_000)

    record = model_override_record(spec, 16_000)

    assert record["name"] == "示例模型"
    assert record["contextWindow"] == 16_000
    assert "reasoning" not in record  # 未知能力不写入伪造值


def test_list_checkpoints_delegates_to_store(monkeypatch, tmp_path):
    """快照列表交由 CheckpointStore,并透传根目录与上限。"""
    seen: dict[str, Any] = {}

    class _Store:
        def __init__(self, root: Path) -> None:
            seen["root"] = root

        def recent(self, limit: int = 20) -> list[str]:
            seen["limit"] = limit
            return ["entry-1"]

    monkeypatch.setattr("tenon.tools.shared.CheckpointStore", _Store)
    service, _ = _service(checkpoints_root=tmp_path)

    assert service.list_checkpoints(limit=5) == ["entry-1"]
    assert seen == {"root": tmp_path, "limit": 5}


def test_restore_checkpoint_delegates_to_store(monkeypatch):
    """恢复动作交由 CheckpointStore.restore_last。"""
    marker = object()

    class _Store:
        def __init__(self, root: Path) -> None:
            del root

        def restore_last(self) -> object:
            return marker

    monkeypatch.setattr("tenon.tools.shared.CheckpointStore", _Store)
    service, _ = _service()

    assert service.restore_checkpoint() is marker


async def test_reload_runtime_returns_selection():
    """运行时重载返回生效的 (model, effort)。"""
    service, calls = _service(reload_result=("m-reloaded", "low"))

    assert await service.reload_runtime() == ("m-reloaded", "low")
    assert calls["reload"] == 1


def test_subagent_snapshot_reports_runner_state():
    """有执行器时报告运行期并发上限与活跃委派。"""
    service, _ = _service(runner=_Runner({"d-1": "child-1"}), max_concurrency=4)

    snapshot = service.subagent_snapshot()

    assert snapshot["max_concurrency"] == 3
    assert snapshot["configured_max_concurrency"] == 4
    assert snapshot["active"] == {"d-1": "child-1"}


def test_subagent_snapshot_falls_back_to_configured_limit():
    """执行器尚未创建时用配置值兜底,活跃列表为空。"""
    service, _ = _service(runner=None, max_concurrency=8)

    snapshot = service.subagent_snapshot()

    assert snapshot["max_concurrency"] == 8
    assert snapshot["active"] == {}


async def test_cancel_subagent_without_runner_returns_false():
    """执行器未装配时取消直接返回 False,不抛异常。"""
    service, _ = _service(runner=None)

    assert await service.cancel_subagent("d-1") is False


async def test_cancel_subagent_delegates_to_runner():
    """取消委托交给执行器,并保留其返回值。"""
    runner = _Runner({"d-1": "child-1"})
    service, _ = _service(runner=runner)

    assert await service.cancel_subagent("d-1") is True
    assert await service.cancel_subagent("d-404") is False
    assert runner.cancelled == ["d-1", "d-404"]


async def test_set_context_window_delegates_tokens():
    """窗口写入交给组合根实现,并回传生效窗口与来源。"""
    service, calls = _service(window_result=(65_536, "catalog"))

    assert await service.set_context_window(65_536) == (65_536, "catalog")
    assert calls["window"] == 65_536
