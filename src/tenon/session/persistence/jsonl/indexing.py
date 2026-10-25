"""Index-facing operations for the JSONL file store."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tenon.session.persistence.codec import _derive_title
from tenon.session.persistence.jsonl.host import JsonlStoreHost
from tenon.session.persistence.models import SessionQuery, SessionRef


class JsonlIndexingMixin(JsonlStoreHost):
    """Connect the store to its rebuildable metadata index."""

    def _index_path(self, path: Path) -> Path:
        return self._index._index_path(path)

    def _source_fingerprint(self, path: Path) -> dict[str, int]:
        return self._index._source_fingerprint(path)

    def _new_index(self, path: Path, header: dict[str, Any]) -> dict[str, Any]:
        return self._index.new_index(path, header, source_fingerprint=self._source_fingerprint)

    def _build_index(self, path: Path) -> dict[str, Any]:
        return self._index.build(path, source_fingerprint=self._source_fingerprint)

    def _apply_index_record(
        self,
        index: dict[str, Any],
        path: Path,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        return self._index.apply_record(
            index,
            path,
            record,
            source_fingerprint=self._source_fingerprint,
        )

    def _apply_index_record_detached(
        self,
        index: dict[str, Any],
        path: Path,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        """Apply one record without refreshing the source fingerprint.

        The append path reads the index *before* writing the JSONL line, so the
        fingerprint still describes the pre-append file. Refreshing it there
        would record a stale size and force a full rebuild on the next read;
        the caller refreshes it once the line is durably written.
        """
        return self._index.apply_record(
            index,
            path,
            record,
            source_fingerprint=lambda _path: dict(index.get("source") or {}),
        )

    def _read_valid_index(self, path: Path) -> dict[str, Any] | None:
        return self._index.read_valid(path, source_fingerprint=self._source_fingerprint)

    def _write_index(self, path: Path, index: dict[str, Any]) -> None:
        self._index._write_index(path, index)

    def _refresh_index_source(self, path: Path, index: dict[str, Any]) -> dict[str, Any]:
        """Stamp one index with the current on-disk source fingerprint."""
        index["source"] = self._source_fingerprint(path)
        return index

    def _invalidate_index(self, path: Path) -> None:
        self._index.invalidate(path)

    def _safe_write_index(self, path: Path, index: dict[str, Any]) -> None:
        try:
            self._write_index(path, index)
        except Exception:
            self._invalidate_index(path)

    def _index_for_read(self, path: Path) -> dict[str, Any] | None:
        with self._lock_for(path):
            index = self._read_valid_index(path)
            if index is not None:
                return index
            try:
                index = self._build_index(path)
            except Exception:
                return None
            self._safe_write_index(path, index)
            return index

    def _ref_from_index(self, index: dict[str, Any], session_id: str) -> SessionRef:
        return self._index.ref_from_index(index, session_id)

    def get(self, session_id: str) -> SessionRef | None:
        path = self._path(session_id)
        if not path.exists() or path.is_symlink():
            return None
        index = self._index_for_read(path)
        if index is not None:
            return self._ref_from_index(index, session_id)
        header, first_user, last_name, model, effort, last_activity_at, archived = self._scan(path)
        return SessionRef(
            id=header.get("id", session_id),
            timestamp=header.get("timestamp", ""),
            cwd=header.get("cwd", ""),
            last_activity_at=(
                last_activity_at or header.get("lastActivityAt") or header.get("timestamp", "")
            ),
            parent_session=header.get("parentSession"),
            model=model,
            effort=effort,
            title=_derive_title(last_name, first_user),
            status="idle",
            archived=archived,
        )

    def list(self, query: SessionQuery | None = None) -> list[SessionRef]:
        if not self._directory.exists():
            return []
        refs: list[SessionRef] = []
        effective_query = query or SessionQuery()
        for path in self._directory.glob("*.jsonl"):
            try:
                ref = self.get(path.stem)
            except ValueError:
                continue
            if ref is not None and effective_query.matches(ref):
                refs.append(ref)
        refs.sort(key=lambda ref: (ref.last_activity_at or ref.timestamp, ref.id))
        return refs


__all__ = ["JsonlIndexingMixin"]
