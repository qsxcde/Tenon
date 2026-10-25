"""上下文诊断的人类可读渲染：空态、预算、压缩、工具结果与最近失败。

纯函数渲染，只断言稳定字段，不依赖真实 tokenizer 或模型。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from tenon.app.context_diagnostics import format_context_diagnostics

pytestmark = pytest.mark.unit


def _diagnostics(**overrides: Any) -> SimpleNamespace:
    base: dict[str, Any] = {
        "model_id": "deepseek-v4-pro",
        "context_window": 256_000,
        "window_source": "catalog",
        "window_certainty": "known",
        "input_budget": 200_000,
        "input_tokens": 1_000,
        "headroom": 199_000,
        "components": {"system": 500, "history": 500},
        "actual_input_tokens": 1_200,
        "actual_output_tokens": 300,
        "actual_cached_tokens": 600,
        "preflight_status": "ok",
        "preflight_reason": None,
        "compaction": None,
        "tool_results": (),
        "last_failure": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_empty_diagnostics_render_unknown_states():
    """无诊断数据时全部字段给出明确的未知/未发生态。"""
    lines = format_context_diagnostics(None)
    text = "\n".join(lines)

    assert "模型: 未知" in text
    assert "窗口: 未知" in text
    assert "预算: 未知" in text
    assert "预算组成: (未知)" in text
    assert "实际用量: (未发生或未知)" in text
    assert "Preflight: (未发生)" in text
    assert "最近压缩: (未发生)" in text
    assert "工具结果治理: (无)" in text
    assert "最近失败" not in text


def test_window_budget_and_components_are_formatted():
    """窗口三要素(数值/来源/确定性)与预算组成逐项渲染。"""
    text = "\n".join(format_context_diagnostics(_diagnostics()))

    assert "窗口: 256,000 · 来源 catalog · 精确" in text
    assert "预算: 输入 1,000 / 200,000 · 余量 199,000" in text
    assert "预算组成:" in text
    assert "  system: 500" in text
    assert "  history: 500" in text


def test_fallback_window_certainty_label():
    """fallback 窗口标注来源而非伪装成精确值。"""
    text = "\n".join(
        format_context_diagnostics(
            _diagnostics(
                context_window=128_000, window_source="fallback", window_certainty="fallback"
            )
        )
    )

    assert "窗口: 128,000 · 来源 fallback · fallback" in text


def test_actual_usage_includes_cache_ratio():
    """实际用量展示输入/输出/缓存与命中率。"""
    text = "\n".join(format_context_diagnostics(_diagnostics()))

    assert "实际用量: 输入 1,200 · 输出 300 · 缓存 600" in text
    assert "50%" in text


def test_preflight_reason_appended_when_present():
    """Preflight 有原因时追加在状态之后。"""
    text = "\n".join(
        format_context_diagnostics(
            _diagnostics(preflight_status="blocked", preflight_reason="窗口不确定")
        )
    )

    assert "Preflight: blocked · 窗口不确定" in text


def test_compaction_details_render_all_optional_fields():
    """压缩记录逐项展示原因、前后 token、目标与裁剪/保留区间。"""
    compaction = SimpleNamespace(
        status="ready",
        trigger="auto",
        reason_code="budget",
        before_input_tokens=1_000,
        after_input_tokens=200,
        target_tokens=300,
        cropped_range=(1, 3),
        retained_range=(4, 9),
    )

    text = "\n".join(format_context_diagnostics(_diagnostics(compaction=compaction)))

    assert (
        "最近压缩: ready · 触发 auto · 原因 budget · 前 1,000 · 后 200 · "
        "目标 300 · 裁剪 1..3 · 保留 4..9" in text
    )


def test_compaction_without_optional_fields_keeps_minimum():
    """压缩记录缺可选字段时不输出空占位。"""
    compaction = SimpleNamespace(
        status="skipped",
        trigger="manual",
        reason_code=None,
        before_input_tokens=None,
        after_input_tokens=None,
        target_tokens=None,
        cropped_range=None,
        retained_range=None,
    )

    text = "\n".join(format_context_diagnostics(_diagnostics(compaction=compaction)))

    assert "最近压缩: skipped · 触发 manual" in text
    assert "原因" not in text


def test_tool_results_render_call_id_and_bytes():
    """工具结果治理列出 call id、动作、字节与状态。"""
    results = (
        SimpleNamespace(
            tool_call_id="call-1",
            action="truncate",
            shown_bytes=100,
            original_bytes=5_000,
            status="truncated",
        ),
        SimpleNamespace(
            tool_call_id=None,
            action="keep",
            shown_bytes=10,
            original_bytes=10,
            status="ok",
        ),
    )

    text = "\n".join(format_context_diagnostics(_diagnostics(tool_results=results)))

    assert "call-1: truncate · 100 / 5,000 B · truncated" in text
    assert "unknown: keep · 10 / 10 B · ok" in text


def test_last_failure_line_includes_code_message_and_phase():
    """最近失败展示错误码、原因与阶段。"""
    text = "\n".join(
        format_context_diagnostics(
            _diagnostics(
                last_failure={
                    "code": "timeout",
                    "message": "模型请求超时",
                    "phase": "model",
                }
            )
        )
    )

    assert "最近失败: timeout · 模型请求超时 · 阶段 model" in text


def test_last_failure_partial_fields_use_defaults():
    """失败记录只给错误码时,原因与阶段用兜底值,不抛 KeyError。"""
    text = "\n".join(format_context_diagnostics(_diagnostics(last_failure={"code": "timeout"})))

    assert "最近失败: timeout · 未知原因 · 阶段 unknown" in text


def test_last_failure_empty_mapping_is_ignored():
    """空失败记录视为无失败,不渲染多余行。"""
    text = "\n".join(format_context_diagnostics(_diagnostics(last_failure={})))

    assert "最近失败" not in text
