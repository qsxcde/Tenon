"""Recovery inspection for JSONL session files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codeagent.session.persistence.models import (
    RecoveryDiagnostic,
    SessionRecoveryReport,
)
from codeagent.session.persistence.subagent_records import record_from_entry
from codeagent.session.persistence.jsonl.host import JsonlStoreHost
from codeagent.session.persistence.jsonl.recovery_diagnostics import (
    diagnostic as _diagnostic,
    header_diagnostic as _header_diagnostic,
    invalid_session_id as _invalid_session_id,
    message_is_invalid as _message_is_invalid,
    unavailable as _unavailable,
    valid_compaction as _valid_compaction,
)


@dataclass(frozen=True)
class _RecoveryScan:
    diagnostics: list[RecoveryDiagnostic]
    valid_message_count: int
    skipped_record_count: int
    message_ids: set[str]
    latest_cut: str | None
    header_seen: bool
    header_error: RecoveryDiagnostic | None = None


@dataclass(frozen=True)
class _EntryScan:
    """Effects from inspecting one valid JSONL entry."""

    valid_message_count: int = 0
    skipped_record_count: int = 0
    message_id: str | None = None
    latest_cut: str | None = None


class JsonlRecoveryMixin(JsonlStoreHost):
    """Inspect a JSONL source without rewriting its authoritative history."""

    def recovery_report(self, session_id: str) -> SessionRecoveryReport:
        invalid = _invalid_session_id(session_id)
        if invalid is not None:
            return _unavailable(session_id, invalid)
        path = self._path(session_id)
        if not path.exists() or path.is_symlink():
            return _unavailable(
                session_id,
                RecoveryDiagnostic(
                    "missing_session",
                    f"会话不存在: {session_id}",
                    "没有可恢复的数据",
                    "请检查会话 id，或新建会话",
                ),
            )

        diagnostics = self._index_diagnostics(path)
        try:
            scan = self._scan_source(path, diagnostics)
        except (OSError, UnicodeError) as exc:
            return _unavailable(
                session_id,
                RecoveryDiagnostic(
                    "unreadable_session",
                    f"会话文件无法读取: {exc}",
                    "无法确认会话内容",
                    "请检查文件权限并先备份原始 JSONL",
                ),
            )
        if scan.header_error is not None:
            return _unavailable(session_id, scan.header_error)
        if not scan.header_seen:
            return _unavailable(
                session_id,
                RecoveryDiagnostic(
                    "missing_header",
                    "会话文件缺少有效 header",
                    "无法确认会话格式和身份",
                    "请先备份文件，升级/迁移可识别的会话，或新建会话",
                ),
            )
        if scan.latest_cut and scan.latest_cut not in scan.message_ids:
            diagnostics.append(
                _diagnostic(
                    "compaction_cut_missing",
                    f"压缩切点消息不存在: {scan.latest_cut}",
                    "恢复回退为全部可解析消息",
                    "请备份文件后继续当前有效历史，必要时重新压缩",
                )
            )
        return SessionRecoveryReport(
            session_id=session_id,
            status="degraded" if diagnostics else "healthy",
            diagnostics=tuple(diagnostics),
            valid_message_count=scan.valid_message_count,
            skipped_record_count=scan.skipped_record_count,
        )

    def _scan_source(self, path: Path, diagnostics: list[RecoveryDiagnostic]) -> _RecoveryScan:
        valid_message_count, skipped_record_count = 0, 0
        message_ids: set[str] = set()
        latest_cut: str | None = None
        header_seen, header_error = False, None
        with self._lock_for(path), path.open("r", encoding="utf-8") as stream:
            for line_number, raw_line in enumerate(stream, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    diagnostics.append(
                        _diagnostic(
                            "malformed_record",
                            f"第 {line_number} 行不是有效 JSON",
                            "该行未参与恢复",
                            "请先备份 JSONL，再继续使用有效历史或手工修复该行",
                        )
                    )
                    skipped_record_count += 1
                    continue
                if not isinstance(entry, dict):
                    diagnostics.append(
                        _diagnostic(
                            "invalid_record",
                            f"第 {line_number} 行不是对象记录",
                            "该行未参与恢复",
                            "请先备份 JSONL，再继续使用有效历史",
                        )
                    )
                    skipped_record_count += 1
                    continue
                if not header_seen:
                    header_error = _header_diagnostic(entry)
                    if header_error is not None:
                        break
                    header_seen = True
                    continue
                result = _scan_entry(entry, line_number, diagnostics)
                valid_message_count += result.valid_message_count
                skipped_record_count += result.skipped_record_count
                if result.message_id is not None:
                    message_ids.add(result.message_id)
                if result.latest_cut is not None:
                    latest_cut = result.latest_cut
        return _RecoveryScan(
            diagnostics,
            valid_message_count,
            skipped_record_count,
            message_ids,
            latest_cut,
            header_seen,
            header_error,
        )

    def _index_diagnostics(self, path: Path) -> list[RecoveryDiagnostic]:
        index_path = self._index_path(path)
        if not index_path.exists():
            return [
                _diagnostic(
                    "index_missing",
                    "会话索引不存在",
                    "索引将从 JSONL 重建",
                    "无需手工修改，可继续使用",
                )
            ]
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            expected = self._source_fingerprint(path)
            if not isinstance(data, dict):
                return [
                    _diagnostic(
                        "index_corrupt",
                        "派生会话索引不是有效对象",
                        "索引将从 JSONL 重建",
                        "系统会自动重建索引",
                    )
                ]
            if data.get("source") != expected:
                code = "index_stale"
                impact = "索引已过期，将从 JSONL 重建"
            elif self._read_valid_index(path) is None:
                code = "index_corrupt"
                impact = "索引不可用，将从 JSONL 重建"
            else:
                return []
            return [_diagnostic(code, "派生会话索引不可用", impact, "系统会自动重建索引")]
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return [
                _diagnostic(
                    "index_corrupt",
                    "派生会话索引无法解析",
                    "索引将从 JSONL 重建",
                    "系统会自动重建索引",
                )
            ]


def _scan_entry(
    entry: dict[str, Any],
    line_number: int,
    diagnostics: list[RecoveryDiagnostic],
) -> _EntryScan:
    entry_type = entry.get("type")
    if entry_type == "message":
        if _message_is_invalid(entry):
            diagnostics.append(
                _diagnostic(
                    "invalid_message",
                    f"第 {line_number} 行消息无法解码",
                    "该消息未进入恢复上下文",
                    "请备份文件后继续有效历史，或手工修复该消息",
                )
            )
            return _EntryScan(skipped_record_count=1)
        message_id = entry.get("id")
        return _EntryScan(
            valid_message_count=1,
            message_id=message_id if isinstance(message_id, str) else None,
        )
    if entry_type == "compaction":
        if not _valid_compaction(entry):
            diagnostics.append(
                _diagnostic(
                    "invalid_compaction",
                    f"第 {line_number} 行压缩记录不完整",
                    "该压缩记录未用于重构上下文",
                    "请备份文件后继续未压缩的有效历史",
                )
            )
            return _EntryScan(skipped_record_count=1)
        return _EntryScan(latest_cut=entry.get("firstKeptEntryId") or None)
    if entry_type == "subagent":
        try:
            record_from_entry(entry)
        except (KeyError, TypeError, ValueError):
            diagnostics.append(
                _diagnostic(
                    "invalid_subagent_record",
                    f"第 {line_number} 行 Subagent 记录不完整",
                    "该委派记录未参与恢复",
                    "请备份 JSONL 后继续使用有效会话历史",
                )
            )
            return _EntryScan(skipped_record_count=1)
    return _EntryScan()


__all__ = ["JsonlRecoveryMixin"]
