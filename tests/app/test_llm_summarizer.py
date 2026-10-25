"""LlmSummarizer：摘要提示构造、内容回退与客户端释放。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from tenon.app.composition.model.factory import LlmSummarizer

pytestmark = pytest.mark.unit


class _Client:
    def __init__(self, content: Any = "摘要正文", *, close_result: Any = None) -> None:
        self.content = content
        self.calls: list[tuple[list[Any], Any]] = []
        self.closed = 0
        self._close_result = close_result
        self.has_aclose = close_result is not None

    async def generate(self, messages, tools=None):
        self.calls.append((list(messages), tools))
        return SimpleNamespace(content=self.content)

    async def aclose(self):
        self.closed += 1
        return self._close_result


def _message(role: str, content: Any) -> SimpleNamespace:
    return SimpleNamespace(role=role, content=content)


async def test_summarize_builds_prompt_and_returns_content():
    """提示包含角色历史与"无既有摘要"占位,返回模型正文。"""
    client = _Client("新的摘要")

    result = await LlmSummarizer(client).summarize(
        [_message("user", "问题"), _message("assistant", "回答")],
        None,
    )

    assert result == "新的摘要"
    messages, tools = client.calls[0]
    assert tools is None
    assert messages[0].role == "system"
    assert "user: 问题" in messages[1].content
    assert "assistant: 回答" in messages[1].content
    assert "(无)" in messages[1].content


async def test_summarize_keeps_previous_summary():
    """既有摘要必须并入提示,避免压缩丢失历史结论。"""
    client = _Client()

    await LlmSummarizer(client).summarize([_message("user", "x")], "旧摘要内容")

    prompt = client.calls[0][0][1].content
    assert "旧摘要内容" in prompt
    assert "(无)" not in prompt


async def test_summarize_skips_messages_without_content():
    """空内容消息不进入历史,避免提示里出现空行占位。"""
    client = _Client()

    await LlmSummarizer(client).summarize(
        [_message("user", ""), _message("assistant", "有内容"), _message("tool", None)],
        None,
    )

    prompt = client.calls[0][0][1].content
    assert "user: " not in prompt
    assert "assistant: 有内容" in prompt


async def test_summarize_falls_back_to_empty_string():
    """模型返回空 content 时给空摘要而不是 "None"。"""
    client = _Client(None)

    assert await LlmSummarizer(client).summarize([_message("user", "x")], None) == ""


async def test_aclose_releases_client():
    """aclose 透传给客户端,只调用一次。"""
    client = _Client()

    await LlmSummarizer(client).aclose()

    assert client.closed == 1


async def test_aclose_tolerates_client_without_close():
    """客户端没有 aclose 时静默跳过,不影响关闭流程。"""

    class _Bare:
        async def generate(self, messages, tools=None):  # pragma: no cover - 未使用
            return SimpleNamespace(content="")

    await LlmSummarizer(_Bare()).aclose()
