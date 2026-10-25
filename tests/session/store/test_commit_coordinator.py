"""SessionCommitter：成功轮次提交、委派记录与旧后端回退。

用记录型 store 桩，不触碰真实 JSONL。
"""

from __future__ import annotations

from typing import Any

import pytest

from tenon.core.contracts.messages import Message
from tenon.session.persistence.commit import SessionCommitter
from tenon.session.persistence.models import UsageStats

pytestmark = pytest.mark.unit


class _Store:
    """记录写入调用的最小 store 桩。"""

    def __init__(self, *, native_commit: bool = False, subagent: bool = False) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.persisted = 0
        if native_commit:
            self.commit_turn = self._commit_turn  # type: ignore[attr-defined]
        if subagent:
            self.append_subagent_record = self._append_subagent  # type: ignore[attr-defined]

    def _commit_turn(self, session_id, messages, usage, *, context_tokens):
        self.calls.append(("commit_turn", (session_id, messages, usage, context_tokens)))

    def _append_subagent(self, session_id, record):
        self.calls.append(("subagent", (session_id, record)))

    def append_message(self, session_id, message):
        self.calls.append(("append_message", (session_id, message)))

    def append_usage(self, session_id, payload):
        self.calls.append(("append_usage", (session_id, payload)))

    def set_meta(self, session_id, key, value):
        self.calls.append(("set_meta", (session_id, key, value)))

    def append_compaction(self, session_id, entry):
        self.calls.append(("compaction", (session_id, entry)))
        return "entry-1"


def _committer(store: _Store) -> tuple[SessionCommitter, list[str]]:
    events: list[str] = []

    def ensure() -> None:
        events.append("ensure")

    return SessionCommitter(store, "s-1", ensure_persisted=ensure), events


def test_turn_without_messages_is_noop():
    """空轮次不触碰存储,也不触发落盘准备。"""
    store = _Store()
    committer, events = _committer(store)

    committer.turn([], UsageStats(), context_tokens=None)

    assert store.calls == []
    assert events == []


def test_turn_prefers_native_commit():
    """后端提供 commit_turn 时走原子提交,不再逐条 append。"""
    store = _Store(native_commit=True)
    committer, events = _committer(store)
    messages = [Message(role="user", content="hi")]

    committer.turn(messages, UsageStats(input_tokens=10), context_tokens=42)

    assert events == ["ensure"]
    assert store.calls == [("commit_turn", ("s-1", messages, UsageStats(input_tokens=10), 42))]


def test_turn_falls_back_to_message_and_usage_appends():
    """旧后端逐条追加消息、用量与上下文 meta。"""
    store = _Store()
    committer, _events = _committer(store)
    messages = [Message(role="user", content="a"), Message(role="assistant", content="b")]
    usage = UsageStats(input_tokens=5, output_tokens=3, cached_tokens=2)

    committer.turn(messages, usage, context_tokens=99)

    kinds = [name for name, _ in store.calls]
    assert kinds == [
        "append_message",
        "append_message",
        "append_usage",
        "set_meta",
    ]
    assert store.calls[2][1][1] == {
        "input_tokens": 5,
        "output_tokens": 3,
        "reasoning_tokens": 0,
        "cached_tokens": 2,
    }
    assert store.calls[3][1] == ("s-1", "last_context_tokens", 99)


def test_turn_skips_usage_when_all_zero():
    """全零用量不写入,避免产生无意义的 usage 记录。"""
    store = _Store()
    committer, _events = _committer(store)

    committer.turn([Message(role="user", content="a")], UsageStats(), context_tokens=1)

    assert [name for name, _ in store.calls] == ["append_message"]


def test_turn_skips_meta_when_context_tokens_unknown():
    """上下文 token 未知时只写用量,不写 meta。"""
    store = _Store()
    committer, _events = _committer(store)

    committer.turn(
        [Message(role="user", content="a")],
        UsageStats(output_tokens=4),
        context_tokens=None,
    )

    assert [name for name, _ in store.calls] == ["append_message", "append_usage"]


def test_subagent_skips_store_without_port():
    """后端不支持委派记录时静默跳过,不影响父回合。"""
    store = _Store()
    committer, events = _committer(store)

    committer.subagent(object())

    assert store.calls == []
    assert events == []


def test_subagent_appends_when_supported():
    """支持委派记录的后端收到有界记录。"""
    store = _Store(subagent=True)
    committer, events = _committer(store)
    record = object()

    committer.subagent(record)

    assert events == ["ensure"]
    assert store.calls == [("subagent", ("s-1", record))]


def test_compaction_returns_entry_id():
    """压缩记录走统一落盘准备并返回 entry id。"""
    store = _Store()
    committer, events = _committer(store)

    entry_id = committer.compaction(object())

    assert entry_id == "entry-1"
    assert events == ["ensure"]
    assert [name for name, _ in store.calls] == ["compaction"]
