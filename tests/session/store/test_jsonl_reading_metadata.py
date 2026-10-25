"""JSONL 读取侧：坏行容错、会话不存在、元数据扫描与压缩切点。

直接写临时 JSONL 文件，不启动会话。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tenon.session.persistence.jsonl import JsonFileStore
from tenon.session.persistence.models import CURRENT_VERSION

pytestmark = pytest.mark.unit


def _header(session_id: str = "s1") -> dict[str, Any]:
    return {
        "type": "session",
        "version": CURRENT_VERSION,
        "id": session_id,
        "timestamp": "2026-10-25T10:00:00",
        "cwd": "/w",
    }


def _write(path: Path, entries: list[Any], *, raw_prefix: str = "") -> None:
    body = "\n".join(
        json.dumps(entry) if not isinstance(entry, str) else entry for entry in entries
    )
    path.write_text(raw_prefix + body + "\n", encoding="utf-8")


def _store(tmp_path: Path) -> JsonFileStore:
    return JsonFileStore(tmp_path)


def test_iter_entries_skips_blank_corrupt_and_non_object_lines(tmp_path):
    """空行、坏 JSON、非对象条目被跳过,合法条目照常产出。"""
    store = _store(tmp_path)
    path = store._path("s1")
    _write(
        path,
        [
            _header(),
            "",
            "{not json",
            "[1, 2]",
            {"type": "message", "id": "m1", "role": "user", "content": "hi"},
        ],
    )

    entries = list(store._iter_entries(path))

    assert [entry.get("type") for entry in entries] == ["session", "message"]


def test_iter_entries_requires_header(tmp_path):
    """缺少 header 的文件视为不可读,抛 ValueError。"""
    store = _store(tmp_path)
    path = store._path("s1")
    _write(path, [{"type": "message", "id": "m1", "role": "user", "content": "hi"}])

    with pytest.raises(ValueError, match="缺少 header"):
        list(store._iter_entries(path))


@pytest.mark.parametrize("method", ["load_messages", "load_subagent_records", "load_context"])
def test_read_methods_reject_missing_session(method, tmp_path):
    """三个读取入口对不存在的会话都给出一致的错误。"""
    store = _store(tmp_path)

    with pytest.raises(ValueError, match="会话不存在"):
        getattr(store, method)("ghost")


def test_scan_collects_metadata_from_mixed_entries(tmp_path):
    """扫描聚合首个用户消息、名称、归档、模型切换与最近活动时间。"""
    store = _store(tmp_path)
    path = store._path("s1")
    _write(
        path,
        [
            _header(),
            {
                "type": "message",
                "id": "m1",
                "role": "user",
                "content": "第一问",
                "timestamp": "2026-10-25T10:01:00",
            },
            {"type": "meta", "key": "name", "value": "会话标题"},
            {"type": "model_change", "model": "deepseek-v4-pro", "effort": "high"},
            {"type": "meta", "key": "archived", "value": True},
            {
                "type": "message",
                "id": "m2",
                "role": "assistant",
                "content": "回答",
                "timestamp": "2026-10-25T10:02:00",
            },
        ],
    )

    header, first_user, last_name, model, effort, last_activity, archived = store._scan(path)

    assert header["id"] == "s1"
    assert first_user == "第一问"
    assert last_name == "会话标题"
    assert model == "deepseek-v4-pro"
    assert effort == "high"
    assert last_activity == "2026-10-25T10:02:00"
    assert archived is True


def test_scan_requires_header(tmp_path):
    """扫描也要求首条是合法 header。"""
    store = _store(tmp_path)
    path = store._path("s1")
    _write(path, [{"type": "meta", "key": "name", "value": "x"}])

    with pytest.raises(ValueError, match="缺少 header"):
        store._scan(path)


def test_scan_ignores_non_string_meta_values(tmp_path):
    """meta 值类型不符时忽略,不写入派生字段。"""
    store = _store(tmp_path)
    path = store._path("s1")
    _write(
        path,
        [
            _header(),
            {"type": "meta", "key": "name", "value": None},
            {"type": "meta", "key": "archived", "value": "yes"},
        ],
    )

    _header_out, _first, last_name, _model, _effort, _activity, archived = store._scan(path)

    assert last_name == ""
    assert archived is False


def test_load_context_uses_compaction_cut_point(tmp_path):
    """存在压缩记录时从 firstKeptEntryId 起加载保留消息。"""
    store = _store(tmp_path)
    path = store._path("s1")
    _write(
        path,
        [
            _header(),
            {"type": "message", "id": "m1", "role": "user", "content": "旧消息"},
            {"type": "message", "id": "m2", "role": "user", "content": "保留消息"},
            {
                "type": "compaction",
                "id": "c1",
                "summary": "摘要",
                "firstKeptEntryId": "m2",
                "details": {"reason": "budget"},
            },
        ],
    )

    state = store.load_context("s1")

    assert state.summary == "摘要"
    assert state.entry_id == "c1"
    assert state.first_kept_entry_id == "m2"
    assert [message.id for message in state.messages] == ["m2"]


def test_load_messages_skips_unparsable_message(monkeypatch, tmp_path):
    """单条消息解析失败时跳过,不让整个会话不可读。"""
    from tenon.session.persistence.jsonl import reading as reading_mod

    store = _store(tmp_path)
    path = store._path("s1")
    _write(
        path,
        [
            _header(),
            {"type": "message", "id": "m1", "role": "user", "content": "ok"},
        ],
    )

    def explode(entry):
        raise ValueError("bad record")

    monkeypatch.setattr(reading_mod, "_dict_to_message", explode)

    assert store.load_messages("s1") == []
