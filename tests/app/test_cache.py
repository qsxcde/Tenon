"""上下文缓存观测与稳定前缀诊断测试(纯函数,离线)。"""

from __future__ import annotations

import pytest

from tenon.app.composition.model.cache import (
    CACHE_COLD,
    CACHE_EFFECTIVE,
    CACHE_UNKNOWN,
    CacheObservation,
    is_cache_friendly_prefix,
    volatile_prefix_markers,
)

pytestmark = pytest.mark.unit


def test_observation_accumulates_and_computes_ratio():
    observation = CacheObservation()
    assert observation.hit_ratio == 0.0
    observation = observation.observe({"input_tokens": 100, "cached_tokens": 40})
    observation = observation.observe({"input_tokens": 100, "cached_tokens": 60})
    assert observation.samples == 2
    assert observation.input_tokens == 200
    assert observation.cached_tokens == 100
    assert observation.hit_ratio == 0.5


def test_observation_ignores_missing_or_negative_values():
    observation = CacheObservation().observe({"input_tokens": 50, "cached_tokens": -10})
    assert observation.input_tokens == 50
    assert observation.cached_tokens == 0
    assert CacheObservation().observe(None) == CacheObservation()


def test_diagnosis_requires_min_samples_then_threshold():
    cold = CacheObservation(samples=2, input_tokens=200, cached_tokens=0)
    assert cold.diagnosis() == CACHE_UNKNOWN
    assert cold.diagnosis(min_samples=2) == CACHE_COLD

    warm = CacheObservation(samples=3, input_tokens=300, cached_tokens=120)
    assert warm.diagnosis() == CACHE_EFFECTIVE
    assert warm.as_dict()["hit_ratio"] == 0.4

    zero_input = CacheObservation(samples=5, input_tokens=0, cached_tokens=0)
    assert zero_input.diagnosis() == CACHE_UNKNOWN


def test_volatile_markers_detect_timestamps_and_temp_paths():
    assert volatile_prefix_markers("生成时间 2026-10-24T09:12 结束") == ("2026-10-24T09:12",)
    assert volatile_prefix_markers("路径 /tmp/scratch/x") == ("/tmp/",)
    assert is_cache_friendly_prefix("稳定的系统提示词,无时间与临时路径") is True


@pytest.mark.contract
def test_base_system_prompt_prefix_is_cache_friendly():
    """契约:基础系统提示词不得含时间戳/临时路径(否则缓存永远不命中)。"""
    from tenon.app.context.agents import build_system_prompt, read_base_prompt

    prompt = build_system_prompt(read_base_prompt(), [])
    assert volatile_prefix_markers(prompt) == ()
    assert is_cache_friendly_prefix(prompt) is True
