"""上下文窗口档位与取值解析。

档位是产品策略而非模型事实：模型只声明窗口上限，可选档位由上限推导，
因此只有上限达到 1M 的模型才会出现 ``1m`` 档。
"""

from __future__ import annotations

# 对外暴露的窗口档位(升序)。只有不超过模型上限的档位才会被下发到用户入口。
CONTEXT_WINDOW_PRESETS: tuple[tuple[str, int], ...] = (
    ("300k", 300 * 1024),
    ("600k", 600 * 1024),
    ("1m", 1024 * 1024),
)


def parse_window_tokens(raw: str) -> int:
    """解析 ``131072`` / ``128k`` / ``1m`` / ``131,072`` 形式的窗口值。"""
    text = raw.strip().replace(",", "").replace("_", "")
    multiplier = 1
    if text.lower().endswith("k"):
        multiplier, text = 1024, text[:-1]
    elif text.lower().endswith("m"):
        multiplier, text = 1024 * 1024, text[:-1]
    if not text.isdigit():
        raise ValueError(f"上下文窗口必须是正整数: {raw}(支持 131072 / 128k)")
    tokens = int(text) * multiplier
    if tokens < 1:
        raise ValueError("上下文窗口必须大于 0")
    return tokens


def try_parse_window_tokens(raw: str) -> int | None:
    """宽松解析：不是窗口写法时返回 ``None``，用于解析模型选择串。"""
    try:
        return parse_window_tokens(raw)
    except ValueError:
        return None


def available_window_presets(max_window: int | None) -> tuple[tuple[str, int], ...]:
    """返回上限内的档位；上限未知时不猜测，返回空。"""
    if type(max_window) is not int or max_window < 1:
        return ()
    return tuple(item for item in CONTEXT_WINDOW_PRESETS if item[1] <= max_window)


def format_window_presets(presets: tuple[tuple[str, int], ...]) -> str:
    """把档位渲染为 ``300k(307,200) / 600k(614,400)`` 一段文本。"""
    return " / ".join(f"{label}({value:,})" for label, value in presets)


__all__ = [
    "CONTEXT_WINDOW_PRESETS",
    "available_window_presets",
    "format_window_presets",
    "parse_window_tokens",
    "try_parse_window_tokens",
]
