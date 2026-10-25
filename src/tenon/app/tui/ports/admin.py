"""TUI 维护类操作的端口协议。

这些操作会触碰用户目录(快照恢复)、重载运行时资源或改写模型目录,统一由组合根
实现并通过 ``TuiApp(admin=...)`` 注入;视图层只负责参数校验与结果呈现。
"""

from __future__ import annotations

from typing import Any, Protocol

__all__ = ["TuiAdminPort"]


class TuiAdminPort(Protocol):
    """组合根为 TUI 提供的高权限维护操作。"""

    def list_checkpoints(self, limit: int = 20) -> list[Any]:
        """返回最近的写前快照(新到旧)。"""
        ...

    def restore_checkpoint(self) -> Any:
        """恢复最近一次快照并返回被恢复的条目。"""
        ...

    async def reload_runtime(self) -> tuple[str, str]:
        """重建模型、MCP 与工具运行时,返回生效的 (model, effort)。"""
        ...

    def subagent_snapshot(self) -> dict[str, Any]:
        """返回委派槽位快照:并发上限、已配置上限与活跃委托。"""
        ...

    async def cancel_subagent(self, delegation_id: str) -> bool:
        """取消指定委托;未命中返回 False。"""
        ...

    async def set_context_window(self, tokens: int) -> tuple[int, str]:
        """写入模型上下文窗口并热切换,返回生效的 (窗口, 来源)。"""
        ...
