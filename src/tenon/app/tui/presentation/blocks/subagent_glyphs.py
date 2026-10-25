"""Subagent 委派块的状态字形与耗时投影。

这里只描述"某个状态该怎么显示"，事件解析与布局由 ``subagent.SubagentBlock``
负责，便于对终态集合和图标映射做单独回归。
"""

from __future__ import annotations

from ..theme import DIM, ERROR, SUCCESS, WARNING

__all__ = ["TERMINAL_STATES", "elapsed_label", "status_icon"]

TERMINAL_STATES = frozenset(
    {"completed", "failed", "timed_out", "cancelled", "rejected", "abandoned"}
)

_PENDING_STATES = frozenset({"waiting_confirmation", "cancelling"})


def status_icon(status: str) -> tuple[str, str]:
    """Return the marker glyph and theme color for one delegation status."""
    if status == "completed":
        return "✓", SUCCESS
    if status in TERMINAL_STATES:
        return "✗", ERROR
    if status in _PENDING_STATES:
        return "!", WARNING
    return "·", DIM


def elapsed_label(value: int) -> str:
    """Render elapsed milliseconds with a compact unit."""
    return f"{value / 1000:.1f}s" if value >= 1000 else f"{value}ms"
