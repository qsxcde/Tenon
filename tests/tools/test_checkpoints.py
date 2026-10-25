"""文件级 checkpoint 与 `tenon undo` 行为测试(离线,全部走 tmp_path)。"""

from __future__ import annotations

import pytest

from tenon.tools.atomic import EditTool, WriteTool
from tenon.tools.shared import CheckpointStore


def _write(tool: WriteTool, path: str, content: str) -> None:
    tool.invoke(tool.Args(file_path=path, content=content))


def test_capture_and_restore_existing_file(tmp_path):
    target = tmp_path / "note.txt"
    target.write_text("before", encoding="utf-8")
    store = CheckpointStore(tmp_path / "cp")

    entry = store.capture(target)
    assert entry is not None and entry.existed is True
    target.write_text("after", encoding="utf-8")

    restored = store.restore_last()
    assert restored.path == str(target)
    assert target.read_text(encoding="utf-8") == "before"
    assert store.recent() == []


def test_restore_removes_file_that_did_not_exist_before(tmp_path):
    target = tmp_path / "new.txt"
    store = CheckpointStore(tmp_path / "cp")
    entry = store.capture(target)
    assert entry is not None and entry.existed is False
    target.write_text("created", encoding="utf-8")

    store.restore_last()
    assert not target.exists()


def test_restore_is_lifo_and_empty_store_raises(tmp_path):
    target = tmp_path / "f.txt"
    store = CheckpointStore(tmp_path / "cp")
    for content in ("v1", "v2", "v3"):
        target.write_text(content, encoding="utf-8")
        store.capture(target)
    target.write_text("v4", encoding="utf-8")

    assert len(store.recent()) == 3
    store.restore_last()
    assert target.read_text(encoding="utf-8") == "v3"
    store.restore_last()
    assert target.read_text(encoding="utf-8") == "v2"
    store.restore_last()
    assert target.read_text(encoding="utf-8") == "v1"
    with pytest.raises(ValueError, match="没有可恢复"):
        store.restore_last()


def test_store_evicts_oldest_beyond_capacity(tmp_path):
    target = tmp_path / "f.txt"
    store = CheckpointStore(tmp_path / "cp", max_entries=3)
    for index in range(5):
        target.write_text(f"v{index}", encoding="utf-8")
        store.capture(target)
    assert [entry.seq for entry in store.recent()] == [3, 4, 5]


def test_write_tool_records_checkpoint_and_undo_reverts(tmp_path):
    target = tmp_path / "doc.md"
    target.write_text("original", encoding="utf-8")
    store = CheckpointStore(tmp_path / "cp")
    tool = WriteTool(cwd=str(tmp_path), checkpoint=store)

    _write(tool, "doc.md", "overwritten")
    assert target.read_text(encoding="utf-8") == "overwritten"

    store.restore_last()
    assert target.read_text(encoding="utf-8") == "original"


def test_edit_tool_records_checkpoint_and_undo_reverts(tmp_path):
    target = tmp_path / "code.py"
    target.write_text("value = 1\n", encoding="utf-8")
    store = CheckpointStore(tmp_path / "cp")
    tool = EditTool(cwd=str(tmp_path), checkpoint=store)

    tool.invoke(tool.Args(file_path="code.py", old_string="value = 1", new_string="value = 2"))
    assert "value = 2" in target.read_text(encoding="utf-8")

    store.restore_last()
    assert target.read_text(encoding="utf-8") == "value = 1\n"


def test_tools_without_checkpoint_keep_behavior(tmp_path):
    target = tmp_path / "plain.txt"
    target.write_text("a", encoding="utf-8")
    _write(WriteTool(cwd=str(tmp_path)), "plain.txt", "b")
    assert target.read_text(encoding="utf-8") == "b"


def test_capture_failure_does_not_block_write(tmp_path):
    """快照失败不得阻塞正常写入(契约:不改变既有写入语义)。"""

    class BrokenStore(CheckpointStore):
        def _capture(self, path, ops):
            raise OSError("快照目录不可写")

    target = tmp_path / "doc.txt"
    target.write_text("before", encoding="utf-8")
    tool = WriteTool(cwd=str(tmp_path), checkpoint=BrokenStore(tmp_path / "cp"))
    _write(tool, "doc.txt", "after")
    assert target.read_text(encoding="utf-8") == "after"
    assert BrokenStore(tmp_path / "cp").recent() == []


def test_undo_cli_lists_and_restores(tmp_path, capsys):
    from tenon.app.main import _undo_cli

    target = tmp_path / "cli.txt"
    target.write_text("keep", encoding="utf-8")
    CheckpointStore(tmp_path / ".tenon" / "checkpoints").capture(target)
    target.write_text("changed", encoding="utf-8")

    assert _undo_cli(["--list"]) == 0
    listed = capsys.readouterr().out
    assert "cli.txt" in listed and "改写" in listed

    assert _undo_cli(["--dry-run"]) == 0
    assert "将恢复" in capsys.readouterr().out

    assert _undo_cli([]) == 0
    assert "已恢复" in capsys.readouterr().out
    assert target.read_text(encoding="utf-8") == "keep"


def test_undo_cli_without_checkpoints_reports_cleanly(tmp_path, capsys):
    from tenon.app.main import _undo_cli

    assert _undo_cli([]) == 1
    assert "没有可恢复" in capsys.readouterr().err
