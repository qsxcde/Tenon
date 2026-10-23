"""文件级 checkpoint:写/编辑前的原文快照与最近一次恢复。

设计:
- 快照发生在写类工具的路径锁内,保证"快照内容 = 即将被覆盖的内容";
- 索引为 append-only JSONL,内容按序号存为 ``<seq>.bak``;
- 恢复是 LIFO:每恢复一次消耗一条快照,可连续回退;
- 条目数有上限,超出后淘汰最旧快照(磁盘占用有界);
- 仅覆盖工作区文件,不进入会话 JSONL,也不改变既有提交语义。
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from codeagent.tools.shared.fsops import FsOps, LocalFsOps

__all__ = ["CheckpointEntry", "CheckpointStore", "DEFAULT_MAX_CHECKPOINTS"]

#: 保留的快照条数上限(超出淘汰最旧)。
DEFAULT_MAX_CHECKPOINTS = 200

_INDEX_FILE = "index.jsonl"
_lock = threading.Lock()


@dataclass(frozen=True)
class CheckpointEntry:
    """一条写前快照:``existed=False`` 表示写入前文件不存在。"""

    seq: int
    path: str
    existed: bool
    blob: str | None
    created_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "seq": self.seq,
            "path": self.path,
            "existed": self.existed,
            "blob": self.blob,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "CheckpointEntry":
        return cls(
            seq=int(raw["seq"]),
            path=str(raw["path"]),
            existed=bool(raw["existed"]),
            blob=raw.get("blob"),
            created_at=str(raw.get("created_at", "")),
        )


class CheckpointStore:
    """按根目录持久化的写前快照存储。"""

    def __init__(self, root: str | Path, *, max_entries: int = DEFAULT_MAX_CHECKPOINTS) -> None:
        if type(max_entries) is not int or max_entries < 1:
            raise ValueError("max_entries 必须为正整数")
        self._root = Path(root).expanduser()
        self._max_entries = max_entries

    @property
    def root(self) -> Path:
        return self._root

    def capture(self, path: str | Path, ops: FsOps | None = None) -> CheckpointEntry | None:
        """在覆盖/改写前保存原文;任何快照失败都返回 None,不阻塞写入。"""
        try:
            return self._capture(path, ops)
        except OSError:
            return None

    def _capture(self, path: str | Path, ops: FsOps | None) -> CheckpointEntry | None:
        store_ops = ops or LocalFsOps()
        target = Path(path)
        with _lock:
            entries = self._read_entries()
            seq = (entries[-1].seq + 1) if entries else 1
            existed = store_ops.exists(target) and store_ops.is_file(target)
            blob: str | None = None
            if existed:
                data = store_ops.read_bytes(target)
                blob = f"{seq}.bak"
                self._root.mkdir(parents=True, exist_ok=True)
                store_ops.write_bytes(self._root / blob, data)
            else:
                self._root.mkdir(parents=True, exist_ok=True)
            entry = CheckpointEntry(
                seq=seq,
                path=str(target),
                existed=existed,
                blob=blob,
                created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            )
            entries.append(entry)
            self._write_entries(entries)
            return entry

    def recent(self, limit: int = 20) -> list[CheckpointEntry]:
        """按时间正序返回最近快照(最多 ``limit`` 条)。"""
        entries = self._read_entries()
        return entries[-limit:] if limit > 0 else []

    def restore_last(self, ops: FsOps | None = None) -> CheckpointEntry:
        """恢复最近一次快照并消耗它;无快照时返回明确错误。"""
        restore_ops = ops or LocalFsOps()
        with _lock:
            entries = self._read_entries()
            if not entries:
                raise ValueError("没有可恢复的 checkpoint")
            entry = entries.pop()
            target = Path(entry.path)
            if entry.existed and entry.blob is not None:
                blob_path = self._root / entry.blob
                if not blob_path.is_file():
                    raise ValueError(f"checkpoint 内容缺失: {blob_path}")
                restore_ops.mkdir(target.parent, parents=True)
                restore_ops.write_bytes(target, blob_path.read_bytes())
                blob_path.unlink(missing_ok=True)
            elif target.exists():
                target.unlink()
            self._write_entries(entries)
            return entry

    def _read_entries(self) -> list[CheckpointEntry]:
        index = self._root / _INDEX_FILE
        if not index.is_file():
            return []
        entries: list[CheckpointEntry] = []
        for line in index.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(CheckpointEntry.from_dict(json.loads(line)))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return entries

    def _write_entries(self, entries: list[CheckpointEntry]) -> None:
        """原子重写索引,并淘汰超出上限的最旧快照。"""
        dropped = entries[: max(0, len(entries) - self._max_entries)]
        kept = entries[len(dropped) :]
        for entry in dropped:
            if entry.blob:
                (self._root / entry.blob).unlink(missing_ok=True)
        self._root.mkdir(parents=True, exist_ok=True)
        index = self._root / _INDEX_FILE
        tmp = self._root / f"{_INDEX_FILE}.tmp"
        payload = "".join(json.dumps(entry.as_dict(), ensure_ascii=False) + "\n" for entry in kept)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, index)
