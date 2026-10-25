"""Tests for the canonical session persistence module boundaries."""

from __future__ import annotations

import importlib.util

from tenon.core.contracts.messages import Message
from tenon.session import session as session_module
from tenon.session.persistence import (
    CompactionEntry,
    CompactionState,
    JsonFileStore,
    MemoryStore,
    SessionRef,
    SessionStore,
    UsageStats,
)
from tenon.session.persistence.codec import _dict_to_message, _message_to_dict
from tenon.session.persistence.index import SessionIndex
from tenon.session.persistence.jsonl import JsonFileStore as JsonlStore
from tenon.session.persistence.memory_store import MemoryStore as InMemoryStore
from tenon.session.persistence.models import SessionRef as PersistenceSessionRef
from tenon.session.persistence.protocol import SessionStore as PersistenceSessionStore
from tenon.session.persistence.records import MessageRecord
from tenon.session.runtime import SessionRuntime
from tenon.session.session_persistence import SessionPersistence


LEGACY_MODULES = (
    "tenon.session.bus",
    "tenon.session.json_file_store",
    "tenon.session.memory_store",
    "tenon.session.session_runtime",
    "tenon.session.store",
    "tenon.session.store_codec",
    "tenon.session.store_index",
    "tenon.session.store_models",
    "tenon.session.tree",
)


def test_canonical_persistence_modules_expose_public_symbols() -> None:
    assert JsonFileStore is JsonlStore
    assert MemoryStore is InMemoryStore
    assert SessionRef is PersistenceSessionRef
    assert SessionStore is PersistenceSessionStore
    assert CompactionEntry is not None
    assert CompactionState is not None
    assert UsageStats is not None
    assert SessionIndex is not None
    assert MessageRecord is not None
    assert callable(_dict_to_message)
    assert callable(_message_to_dict)


def test_legacy_session_modules_are_removed() -> None:
    for module_name in LEGACY_MODULES:
        assert importlib.util.find_spec(module_name) is None


def test_persistence_locking_shares_a_lock_per_path() -> None:
    from tenon.session.persistence.locking import path_lock

    assert path_lock("sessions/a.jsonl") is path_lock("sessions/a.jsonl")
    assert path_lock("sessions/a.jsonl") is not path_lock("sessions/b.jsonl")


def test_session_committer_only_writes_explicit_successful_payload() -> None:
    from tenon.session.persistence.commit import SessionCommitter

    store = MemoryStore()
    store.create("committed")
    committer = SessionCommitter(store, "committed")

    committer.turn(
        [Message(role="user", content="hello")],
        UsageStats(input_tokens=2),
        context_tokens=2,
    )

    assert [message.content for message in store.load_messages("committed")] == ["hello"]
    assert store.load_usage("committed").input_tokens == 2


def test_session_facade_keeps_public_constants() -> None:
    assert session_module.AgentSession.__name__ == "AgentSession"
    assert session_module.DEFAULT_CONTEXT_WINDOW > 0


def test_session_runtime_owns_run_control_state() -> None:
    runtime = SessionRuntime(lambda event: None)

    run_id = runtime.start_run()
    runtime.inject("follow-up")
    runtime.respond_approval("request-1", True)

    assert runtime.active_run_id == run_id
    assert runtime.inject_queue.get_nowait() == "follow-up"
    assert runtime.confirm_queue.get_nowait() == ("request-1", True)


def test_session_persistence_defers_creation_until_commit() -> None:
    store = MemoryStore()
    persistence = SessionPersistence(
        store,
        "pending",
        defer_persistence=True,
        persistence_options={"model": "fake"},
    )

    restored = persistence.load()
    assert restored.history == []
    assert not persistence.persisted
    assert store.get("pending") is None

    persistence.commit_turn(
        [Message(role="user", content="hello")],
        UsageStats(input_tokens=3),
        context_tokens=3,
    )

    assert persistence.persisted
    assert store.get("pending") is not None
    assert store.load_messages("pending")[0].content == "hello"
    assert store.get_meta("pending", "last_context_tokens") == 3
