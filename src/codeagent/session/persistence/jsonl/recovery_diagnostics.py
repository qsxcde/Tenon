"""JSONL 恢复过程中的单项诊断判定。

诊断的"说什么"（错误码、影响面、可操作建议）与"何时触发"（扫描流程）是两种
职责：这里只描述单条 header/记录是否可恢复及其诊断文本，扫描与报告装配留在
``recovery.JsonlRecoveryMixin``。
"""

from __future__ import annotations

from typing import Any

from codeagent.session.persistence.codec import CURRENT_VERSION, _dict_to_message
from codeagent.session.persistence.models import (
    RecoveryDiagnostic,
    SessionRecoveryReport,
)

__all__ = [
    "diagnostic",
    "header_diagnostic",
    "invalid_session_id",
    "message_is_invalid",
    "unavailable",
    "valid_compaction",
]


def diagnostic(code: str, message: str, impact: str, action: str) -> RecoveryDiagnostic:
    """Build one recovery diagnostic entry."""
    return RecoveryDiagnostic(code, message, impact, action)


def unavailable(
    session_id: object,
    recovery_diagnostic: RecoveryDiagnostic,
) -> SessionRecoveryReport:
    """Report a session as unavailable for one structural reason."""
    return SessionRecoveryReport(str(session_id), "unavailable", (recovery_diagnostic,))


def invalid_session_id(session_id: object) -> RecoveryDiagnostic | None:
    """Reject session ids that could escape the store directory."""
    if not isinstance(session_id, str) or not session_id or session_id in {".", ".."}:
        return diagnostic(
            "invalid_session_id",
            "会话 id 格式无效",
            "未读取任何会话数据",
            "请使用列表中的单组件会话 id",
        )
    if "/" in session_id or "\\" in session_id:
        return diagnostic(
            "invalid_session_id",
            "会话 id 不得包含路径分隔符",
            "未读取目标目录之外的文件",
            "请使用列表中的单组件会话 id",
        )
    return None


def header_diagnostic(entry: dict[str, Any]) -> RecoveryDiagnostic | None:
    """Validate the first header record before any message is decoded."""
    if entry.get("type") != "session":
        return diagnostic(
            "missing_header",
            "首条有效记录不是 session header",
            "无法确认会话格式和身份",
            "请先备份文件并升级/迁移，或新建会话",
        )
    if entry.get("version") != CURRENT_VERSION:
        return diagnostic(
            "incompatible_version",
            f"会话版本不兼容: {entry.get('version')}",
            "无法安全解释会话记录",
            "请升级客户端或备份后迁移该会话",
        )
    if not isinstance(entry.get("id"), str) or not entry.get("id"):
        return diagnostic(
            "invalid_header",
            "session header 缺少有效 id",
            "无法确认会话身份",
            "请先备份文件并手工迁移，或新建会话",
        )
    return None


def message_is_invalid(entry: dict[str, Any]) -> bool:
    """Decode a message entry without raising to decide whether it is usable."""
    try:
        _dict_to_message(entry)
    except (KeyError, TypeError, ValueError):
        return True
    return False


def valid_compaction(entry: dict[str, Any]) -> bool:
    """Check that a compaction record carries every field recovery needs."""
    return (
        isinstance(entry.get("id"), str)
        and isinstance(entry.get("firstKeptEntryId"), str)
        and isinstance(entry.get("summary"), str)
        and isinstance(entry.get("details"), dict)
    )
