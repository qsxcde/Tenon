"""自动压缩的预算视图：provider 解析、回退估算与候选预算。

宿主用最小子类构造，不启动会话循环。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from tenon.core.context.budget import ContextBudgetSnapshot
from tenon.core.contracts.messages import Message
from tenon.session.compaction_runtime_budget import SessionCompactionBudgetMixin

pytestmark = pytest.mark.unit


class _BudgetState:
    def __init__(self) -> None:
        self.records: list[ContextBudgetSnapshot] = []

    def record_estimate(self, snapshot: ContextBudgetSnapshot) -> None:
        self.records.append(snapshot)


class _Host(SessionCompactionBudgetMixin):
    """只提供 mixin 需要的宿主状态。"""

    def __init__(
        self,
        *,
        config: Any,
        context_window: int = 100_000,
        history: tuple[Message, ...] = (),
        summary: str | None = None,
        summary_entry_id: str | None = None,
        compact_budget: int | None = None,
    ) -> None:
        self._config = config
        self._context_window = context_window
        self._history = list(history)
        self._summary = summary
        self._summary_entry_id = summary_entry_id
        self._compaction_policy = SimpleNamespace(compact_budget=compact_budget)
        self._budget_state = _BudgetState()


def _snapshot(**overrides: Any) -> ContextBudgetSnapshot:
    base: dict[str, Any] = {
        "context_window": 200_000,
        "output_reserve": 8_192,
        "reserve_tokens": 16_384,
        "input_budget": 175_424,
        "system_prompt_tokens": 100,
        "tool_definitions_tokens": 50,
        "conversation_tokens": 1_000,
        "tool_result_tokens": 0,
        "input_tokens": 1_150,
        "headroom": 174_274,
        "status": "estimate",
        "window_source": "catalog",
    }
    base.update(overrides)
    return ContextBudgetSnapshot(**base)


def _config(**overrides: Any) -> SimpleNamespace:
    base = {
        "model": SimpleNamespace(
            output_reserve=2_000,
            reserve_tokens=3_000,
            _system_prompt="系统提示",
        ),
        "tools": [],
        "context_budget": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_manual_compaction_budget_prefers_explicit_policy():
    """显式 compact_budget 优先于决策目标与默认比例。"""
    host = _Host(config=_config(), compact_budget=4_096)

    assert host._manual_compaction_budget(SimpleNamespace(target_budget=9_000)) == 4_096


def test_manual_compaction_budget_uses_decision_target():
    """无显式预算时采用压缩决策目标。"""
    host = _Host(config=_config())

    assert host._manual_compaction_budget(SimpleNamespace(target_budget=9_000)) == 9_000


def test_manual_compaction_budget_defaults_to_window_ratio():
    """无决策时按窗口 65% 估算下限。"""
    host = _Host(config=_config(), context_window=100_000)

    assert host._manual_compaction_budget(None) == 65_000


def test_fallback_budget_reserves_are_clamped_to_window():
    """预留超过窗口时被裁剪,输入预算不为负。"""
    config = _config(
        model=SimpleNamespace(output_reserve=50_000, reserve_tokens=80_000, _system_prompt="")
    )
    host = _Host(config=config, context_window=100_000)

    snapshot = host._fallback_context_budget([Message(role="user", content="hi")])

    assert snapshot.context_window == 100_000
    assert snapshot.output_reserve == 50_000
    assert snapshot.reserve_tokens == 50_000
    assert snapshot.input_budget == 0
    assert snapshot.window_source == "fallback"


def test_fallback_budget_without_optional_model_attributes():
    """模型端口缺预留属性时按 0 处理,仍能给出估算。"""
    host = _Host(config=_config(model=SimpleNamespace()), context_window=10_000)

    snapshot = host._fallback_context_budget([Message(role="user", content="hi")])

    assert snapshot.output_reserve == 0
    assert snapshot.reserve_tokens == 0
    assert snapshot.input_budget == 10_000


async def test_describe_context_budget_uses_fallback_without_provider():
    """无预算 provider 时回退到本地估算并记录状态。"""
    host = _Host(config=_config(), context_window=50_000)

    snapshot = await host._describe_context_budget([Message(role="user", content="hi")])

    assert snapshot is not None
    assert snapshot.window_source == "fallback"
    assert host._budget_state.records == [snapshot]


async def test_describe_context_budget_accepts_callable_provider():
    """provider 本身可调用时作为 describe 使用。"""
    calls: list[tuple[list[Message], list[Any]]] = []

    def provider(messages, tools):
        calls.append((messages, tools))
        return _snapshot()

    host = _Host(config=_config(context_budget=provider), context_window=100_000)

    snapshot = await host._describe_context_budget([Message(role="user", content="hi")])

    assert snapshot is not None
    assert snapshot.context_window == 100_000  # rebase 到会话窗口
    assert len(calls) == 1


async def test_describe_context_budget_awaits_async_provider():
    """异步 describe 结果会被 await。"""

    class _Provider:
        async def describe_context_budget(self, messages, tools):
            return _snapshot()

    host = _Host(config=_config(context_budget=_Provider()), context_window=100_000)

    snapshot = await host._describe_context_budget([Message(role="user", content="hi")])

    assert snapshot is not None and snapshot.context_window == 100_000


async def test_describe_context_budget_rejects_invalid_provider():
    """provider 既无 describe 又不可调用 → 明确类型错误。"""
    host = _Host(config=_config(context_budget=object()))

    with pytest.raises(TypeError, match="lacks describe_context_budget"):
        await host._describe_context_budget([Message(role="user", content="hi")])


async def test_describe_context_budget_rejects_wrong_return_type():
    """返回非 ContextBudgetSnapshot → 类型错误,避免下游按错误结构读取。"""
    host = _Host(config=_config(context_budget=lambda messages, tools: {"input_budget": 1}))

    with pytest.raises(TypeError, match="must return ContextBudgetSnapshot"):
        await host._describe_context_budget([Message(role="user", content="hi")])


async def test_describe_context_budget_rejects_none_result():
    """provider 返回 None 同样被视为非法返回,而不是静默通过。"""
    host = _Host(config=_config(context_budget=lambda messages, tools: None))

    with pytest.raises(TypeError, match="must return ContextBudgetSnapshot"):
        await host._describe_context_budget([])
    assert host._budget_state.records == []


async def test_estimate_compaction_candidate_requires_budget(monkeypatch):
    """候选预算不可用(宿主返回 None)时抛 ValueError,避免用错误预算压缩。"""
    host = _Host(config=_config())

    async def _no_budget(messages):
        return None

    monkeypatch.setattr(host, "_describe_context_budget", _no_budget)

    with pytest.raises(ValueError, match="压缩候选预算不可用"):
        await host._estimate_compaction_candidate("摘要", [])


async def test_estimate_compaction_candidate_includes_summary_message():
    """候选预算把摘要消息放在最前,便于与保留消息一起估算。"""
    captured: list[list[Message]] = []

    def provider(messages, tools):
        captured.append(list(messages))
        return _snapshot(context_window=100_000, input_budget=90_000, headroom=80_000)

    host = _Host(config=_config(context_budget=provider), context_window=100_000)

    snapshot = await host._estimate_compaction_candidate("压缩要点", [])

    assert snapshot.context_window == 100_000
    assert captured[0][0].content.endswith("压缩要点")


async def test_next_request_budget_prepends_summary():
    """存在摘要时先插入摘要消息再估算。"""
    captured: list[list[Message]] = []

    def provider(messages, tools):
        captured.append(list(messages))
        return _snapshot(context_window=100_000)

    host = _Host(
        config=_config(context_budget=provider),
        context_window=100_000,
        history=(Message(role="user", content="历史"),),
        summary="既有摘要",
        summary_entry_id="entry-9",
    )

    await host._next_request_budget()

    assert "entry-9" in captured[0][0].id
    assert captured[0][1].content == "历史"


def test_rebase_context_window_recomputes_headroom():
    """快照窗口与会话窗口不一致时重算输入预算与余量。"""
    host = _Host(config=_config(), context_window=100_000)
    snapshot = _snapshot(
        context_window=200_000,
        output_reserve=8_192,
        reserve_tokens=16_384,
        input_tokens=1_000,
        input_budget=175_424,
        headroom=174_424,
    )

    rebased = host._rebase_context_window(snapshot)

    assert rebased.context_window == 100_000
    assert rebased.input_budget == 100_000 - 8_192 - 16_384
    assert rebased.headroom == rebased.input_budget - 1_000
