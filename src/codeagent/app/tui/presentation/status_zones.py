"""状态栏三区（session / runtime / context）宽度分配。

宽度分配是纯计算，与 textual 组件渲染无关，单独成模块便于按终端宽度做回归。
"""

from __future__ import annotations

__all__ = ["zone_widths"]


def zone_widths(
    width: int,
    *,
    session_zone: int,
    wide_session_zone: int,
    context_zone: int,
) -> tuple[int, int, int]:
    """Return stable session/runtime/context budgets for one terminal width."""
    width = max(1, width)
    if width >= 120:
        session_width = wide_session_zone
        context_width = context_zone
    elif width >= 88:
        session_width, context_width = session_zone, context_zone
    elif width >= 64:
        session_width, context_width = 14, 24
    elif width >= 56:
        session_width, context_width = 12, 20
    elif width >= 40:
        session_width, context_width = 0, 16
    elif width >= 20:
        session_width, context_width = 0, 12
    else:
        session_width, context_width = 0, min(12, max(0, width // 3))

    separators = (1 if session_width else 0) + (1 if context_width else 0)
    runtime_width = max(0, width - session_width - context_width - separators)
    if runtime_width == 0 and context_width:
        context_width = max(0, context_width - 1)
        separators = (1 if session_width else 0) + (1 if context_width else 0)
        runtime_width = max(0, width - session_width - context_width - separators)
    return session_width, runtime_width, context_width
