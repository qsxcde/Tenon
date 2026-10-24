"""openai provider 工厂：密钥校验、模型规格与思考强度透传。

客户端用桩替换，不创建连接、不联网。
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import SecretStr

from codeagent.ai.providers.openai import OpenAIConfig, make_llm

pytestmark = pytest.mark.unit


def _patch_client(monkeypatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    class _Client:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        "codeagent.ai.transport.openai_compat.OpenAICompatClient",
        _Client,
    )
    return captured


def test_make_llm_requires_api_key():
    """缺少密钥时给出可操作错误,而不是底层 SDK 的 credentials 异常。"""
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        make_llm(OpenAIConfig(api_key=SecretStr("")))


def test_make_llm_uses_builtin_spec_and_explicit_effort(monkeypatch):
    """思维链模型按内置规格传 reasoning_effort。"""
    captured = _patch_client(monkeypatch)

    client = make_llm(
        OpenAIConfig(api_key=SecretStr("sk-test"), model="gpt-5"),
        reasoning_effort="medium",
    )

    assert client is not None
    assert captured["model"] == "gpt-5"
    assert captured["provider"] == "openai"
    assert captured["reasoning_effort"] == "medium"
    assert captured["api_key"] == SecretStr("sk-test")


def test_make_llm_omits_effort_for_non_reasoning_model(monkeypatch):
    """不支持思考的模型不传 reasoning_effort。"""
    captured = _patch_client(monkeypatch)

    make_llm(OpenAIConfig(api_key=SecretStr("sk-test"), model="gpt-5-nano"))

    assert captured["reasoning_effort"] is None


def test_make_llm_falls_back_to_config_effort(monkeypatch):
    """未显式指定强度时沿用配置值。"""
    captured = _patch_client(monkeypatch)

    make_llm(
        OpenAIConfig(
            api_key=SecretStr("sk-test"),
            model="gpt-5",
            reasoning_effort="low",
        )
    )

    assert captured["reasoning_effort"] == "low"


def test_make_llm_accepts_unknown_model_via_bare_spec(monkeypatch):
    """目录外的模型 id 仍可构造,只是没有 reasoning/max_tokens 元数据。"""
    captured = _patch_client(monkeypatch)

    make_llm(OpenAIConfig(api_key=SecretStr("sk-test"), model="custom-model"))

    assert captured["model"] == "custom-model"
    assert captured["reasoning_effort"] is None
    assert captured["max_tokens"] is None


def test_make_llm_prefers_explicit_spec(monkeypatch):
    """显式传入的规格优先于配置里的模型名。"""
    from codeagent.ai.catalog.spec import ModelSpec

    captured = _patch_client(monkeypatch)

    make_llm(
        OpenAIConfig(api_key=SecretStr("sk-test"), model="gpt-5-nano"),
        ModelSpec(id="gpt-5", reasoning=True, max_tokens=4096),
    )

    assert captured["model"] == "gpt-5"
    assert captured["max_tokens"] == 4096
    assert captured["reasoning_effort"] == "high"
