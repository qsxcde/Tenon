"""JSONL 存储 mixin 组合的宿主属性声明基类。

``JsonFileStore``（``jsonl/store.py``）由写入、索引、读取、恢复与分叉五个 mixin
组合而成。本基类只提供类级类型注解（宿主属性）与 ``Callable`` 注解（跨 mixin
方法），不含任何赋值或方法体；宿主 ``__init__`` 的真实赋值与各 mixin 的真实方法
定义会覆盖这里的声明，因此运行时行为不变。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tenon.session.persistence.index import SessionIndex
    from tenon.session.persistence.locking import PathLock
    from tenon.session.persistence.models import SessionRef


class JsonlStoreHost:
    """声明 mixin 组合宿主 ``JsonFileStore`` 的共享属性与跨 mixin 方法。"""

    # 宿主 ``__init__`` 建立的实例状态。
    _directory: Path
    _index: SessionIndex
    _lock_for: Callable[[str | Path], PathLock]

    # 宿主定义的方法（mixin 通过宿主组合获得，静态检查需要声明）。
    _path: Callable[[str], Path]
    _now: Callable[[], str]
    _chmod_private: Callable[[Path], None]
    _private_dir: Callable[[], None]

    # 定义在其他 mixin 的方法，按调用方视角声明为 Callable。
    _iter_entries: Callable[[Path], Iterator[dict[str, Any]]]
    _scan: Callable[[Path], tuple[dict[str, Any], str, str, str, str, str, bool]]
    _index_path: Callable[[Path], Path]
    _source_fingerprint: Callable[[Path], dict[str, int]]
    _new_index: Callable[[Path, dict[str, Any]], dict[str, Any]]
    _build_index: Callable[[Path], dict[str, Any]]
    _apply_index_record: Callable[[dict[str, Any], Path, dict[str, Any]], dict[str, Any]]
    _apply_index_record_detached: Callable[[dict[str, Any], Path, dict[str, Any]], dict[str, Any]]
    _refresh_index_source: Callable[[Path, dict[str, Any]], dict[str, Any]]
    _read_valid_index: Callable[[Path], dict[str, Any] | None]
    _write_index: Callable[[Path, dict[str, Any]], None]
    _invalidate_index: Callable[[Path], None]
    _safe_write_index: Callable[[Path, dict[str, Any]], None]
    _index_for_read: Callable[[Path], dict[str, Any] | None]
    _ref_from_index: Callable[[dict[str, Any], str], SessionRef]


__all__ = ["JsonlStoreHost"]
