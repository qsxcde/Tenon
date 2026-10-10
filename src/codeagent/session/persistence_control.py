"""会话持久化控制：延迟落盘的 header、消息父链接与元数据写入前置。

`AgentSession` 是公共门面，具体的持久化控制细节按 mixin 分区，避免把存储语义
继续堆叠到门面类里（与 ``SessionEventMixin`` / ``SessionLifecycleMixin`` 同构）。
"""

from __future__ import annotations

from typing import Any

from codeagent.core.contracts.messages import Message
from codeagent.session.host import AgentSessionHost

__all__ = ["SessionPersistenceMixin"]


class SessionPersistenceMixin(AgentSessionHost):
    """Persistence control shared by one stateful session facade."""

    _summary_entry_id: str | None
    _history: list[Message]

    def _link_persistence_parents(self, messages: list[Message]) -> None:
        parent_id = self._summary_entry_id or (self._history[-1].id if self._history else None)
        for message in messages:
            if message.parent_id is None:
                message.parent_id = parent_id
            parent_id = message.id

    def _ensure_persisted(self) -> None:
        self._persistence.ensure_persisted()  # type: ignore[attr-defined]

    def ensure_persisted(self) -> None:
        """Persist a deferred session header before an explicit metadata edit."""
        self._ensure_persisted()

    def update_persistence_options(self, **options: Any) -> None:
        self._persistence.update_options(**options)  # type: ignore[attr-defined]
