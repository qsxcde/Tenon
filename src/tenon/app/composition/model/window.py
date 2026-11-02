"""模型上下文窗口上限与档位策略。

窗口上限是模型能力声明(``max_context_window``),生效窗口是用户可覆盖的
``context_window``。上限未知时不猜测,保持旧的自由设置行为。
"""

from __future__ import annotations

from typing import Any

from tenon.core.context.window import available_window_presets


def model_window_limit(spec: Any) -> int | None:
    """返回模型声明窗口上限;缺失时用生效窗口兜底,都缺失则未知。"""
    limit = getattr(spec, "max_context_window", None)
    if type(limit) is int and limit > 0:
        return limit
    window = getattr(spec, "context_window", None)
    if type(window) is int and window > 0:
        return window
    return None


def ensure_window_within_limit(tokens: int, spec: Any) -> None:
    """拒绝超过模型声明上限的窗口值;上限未知时不做校验。"""
    limit = model_window_limit(spec)
    if limit is None or tokens <= limit:
        return
    model_id = getattr(spec, "id", "?")
    raise ValueError(f"上下文窗口 {tokens:,} 超过模型 {model_id} 的上限 {limit:,}")


def window_presets_for(spec: Any) -> tuple[tuple[str, int], ...]:
    """返回该模型可选的窗口档位(300k/600k/1m 中不超过上限的部分)。"""
    return available_window_presets(model_window_limit(spec))


__all__ = ["ensure_window_within_limit", "model_window_limit", "window_presets_for"]
