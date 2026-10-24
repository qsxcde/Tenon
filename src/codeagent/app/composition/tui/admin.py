"""TUI 维护类命令的组合根适配。

把快照存储、运行时重载、委派槽位与模型目录写入收敛到一处,让 ``app/tui`` 只依赖
``TuiAdminPort`` 协议,不直接 import 快照存储或模型目录实现。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

__all__ = ["TuiAdminService", "model_override_record"]


def model_override_record(spec: Any, context_window: int) -> dict[str, Any]:
    """把目录规格转成 models.json 覆盖记录,保留除窗口外的全部元数据。

    ``ModelStore`` 的 upsert 是整体替换,只写 ``id`` 与 ``contextWindow`` 会把该模型
    的 ``maxTokens``/``reasoning``/``aliases`` 清空,因此必须写全已知字段。
    """
    record: dict[str, Any] = {"id": spec.id, "contextWindow": context_window}
    if spec.name:
        record["name"] = spec.name
    if spec.reasoning is not None:
        record["reasoning"] = spec.reasoning
    if spec.max_tokens is not None:
        record["maxTokens"] = spec.max_tokens
    if spec.tool_calling is not None:
        record["toolCalling"] = spec.tool_calling
    if spec.prompt_cache is not None:
        record["promptCache"] = spec.prompt_cache
    if spec.aliases:
        record["aliases"] = list(spec.aliases)
    return record


class TuiAdminService:
    """把组合根能力适配为 ``TuiAdminPort``。"""

    def __init__(
        self,
        *,
        checkpoints_root: Callable[[], Path],
        reload_runtime: Callable[[], Awaitable[tuple[str, str]]],
        subagent_runner: Callable[[], Any],
        set_context_window: Callable[[int], Awaitable[tuple[int, str]]],
        max_concurrency: Callable[[], int],
    ) -> None:
        """保存各能力的延迟解析回调,避免装配期提前创建子运行资源。"""
        self._checkpoints_root = checkpoints_root
        self._reload_runtime = reload_runtime
        self._subagent_runner = subagent_runner
        self._set_context_window = set_context_window
        self._max_concurrency = max_concurrency

    def list_checkpoints(self, limit: int = 20) -> list[Any]:
        from codeagent.tools.shared import CheckpointStore

        return CheckpointStore(self._checkpoints_root()).recent(limit=limit)

    def restore_checkpoint(self) -> Any:
        from codeagent.tools.shared import CheckpointStore

        return CheckpointStore(self._checkpoints_root()).restore_last()

    async def reload_runtime(self) -> tuple[str, str]:
        return await self._reload_runtime()

    def subagent_snapshot(self) -> dict[str, Any]:
        runner = self._subagent_runner()
        active = dict(getattr(runner, "active_delegations", {}) or {}) if runner else {}
        return {
            "max_concurrency": getattr(runner, "max_concurrency", self._max_concurrency()),
            "configured_max_concurrency": self._max_concurrency(),
            "active": active,
        }

    async def cancel_subagent(self, delegation_id: str) -> bool:
        runner = self._subagent_runner()
        if runner is None:
            return False
        return await runner.cancel(delegation_id)

    async def set_context_window(self, tokens: int) -> tuple[int, str]:
        return await self._set_context_window(tokens)
