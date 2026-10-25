"""TUI 性能基准场景：串流、工具输出、恢复与窗口变化。

使用离线 fixture，不启动 Textual 引擎，只验证指标被记录且场景分支可达。
"""

from __future__ import annotations

import pytest

from tenon.app.tui.benchmark.fixture import BenchmarkConfig, build_fixture, scenarios
from tenon.app.tui.benchmark.performance import PerformanceRecorder
from tenon.app.tui.benchmark.runner import run_scenario

pytestmark = [pytest.mark.unit, pytest.mark.performance]


def _run(scenario: str, **overrides) -> PerformanceRecorder:
    config = BenchmarkConfig(
        scenario=scenario,
        history_blocks=overrides.get("history_blocks", 6),
        stream_chars=overrides.get("stream_chars", 512),
        tool_output_bytes=overrides.get("tool_output_bytes", 400),
        width=60,
        height=20,
    )
    fixture = build_fixture(config)
    recorder = PerformanceRecorder()
    run_scenario(config, fixture, recorder)
    return recorder


def test_scenarios_cover_all_documented_modes():
    """场景清单稳定:history/stream/tool-output/restore/window-resize。"""
    assert set(scenarios()) == {"history", "stream", "tool-output", "restore", "scroll-resize"}


@pytest.mark.parametrize(
    "scenario", ["history", "stream", "tool-output", "restore", "scroll-resize"]
)
def test_each_scenario_records_frame_metrics(scenario):
    """每个场景至少记录帧耗时,保证基准对比有数据。"""
    recorder = _run(scenario)

    assert recorder.samples("frame_total_ms")


def test_stream_scenario_records_latency_marks():
    """串流场景记录提交、首 token 与 markdown 渲染指标。"""
    recorder = _run("stream")

    assert recorder.samples("first_token_latency_ms")
    assert recorder.samples("submit_latency_ms")
    assert recorder.samples("event_apply_ms")
    assert recorder.samples("markdown_render_ms")


def test_tool_output_scenario_renders_tool_block():
    """工具输出场景产生工具块并渲染一帧。"""
    recorder = _run("tool-output")

    assert recorder.samples("model_render_ms")


def test_restore_scenario_measures_hydration():
    """恢复场景记录整段恢复耗时与首帧渲染。"""
    recorder = _run("restore", history_blocks=12)

    assert recorder.samples("restore_ms")
    assert recorder.samples("frame_total_ms")


def test_resize_scenario_renders_twice_for_window_change():
    """窗口变化场景在两种尺寸下各渲染一帧。"""
    recorder = _run("scroll-resize")

    assert len(recorder.samples("frame_total_ms")) >= 2
