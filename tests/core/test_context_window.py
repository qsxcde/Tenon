"""上下文窗口档位与取值解析。"""

import pytest

from tenon.core.context.window import (
    CONTEXT_WINDOW_PRESETS,
    available_window_presets,
    format_window_presets,
    parse_window_tokens,
    try_parse_window_tokens,
)

pytestmark = pytest.mark.unit


def test_parse_window_tokens_accepts_plain_k_m_and_grouped_digits():
    """窗口写法覆盖纯数字、k/m 后缀与千分位。"""
    assert parse_window_tokens("131072") == 131_072
    assert parse_window_tokens("128k") == 131_072
    assert parse_window_tokens("1M") == 1_048_576
    assert parse_window_tokens("131,072") == 131_072


def test_parse_window_tokens_rejects_text_and_zero():
    """非数字与 0 都以明确错误拒绝。"""
    with pytest.raises(ValueError, match="正整数"):
        parse_window_tokens("abc")
    with pytest.raises(ValueError, match="大于 0"):
        parse_window_tokens("0")


def test_try_parse_window_tokens_returns_none_for_non_window_text():
    """宽松解析只识别窗口写法,供模型选择串剥离后缀。"""
    assert try_parse_window_tokens("high") is None
    assert try_parse_window_tokens("1m") == 1_048_576


def test_available_window_presets_limited_by_model_capability():
    """1M 档只对上限达到 1M 的模型放行。"""
    assert available_window_presets(None) == ()
    assert available_window_presets(256_000) == ()
    assert available_window_presets(320_000) == (("300k", 307_200),)
    assert available_window_presets(600_000) == (("300k", 307_200),)
    assert available_window_presets(1_048_576) == CONTEXT_WINDOW_PRESETS


def test_format_window_presets_renders_label_and_value():
    """档位文本同时给出简称与精确 token 数。"""
    assert format_window_presets((("300k", 307_200), ("1m", 1_048_576))) == (
        "300k(307,200) / 1m(1,048,576)"
    )
