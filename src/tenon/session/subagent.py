"""Parent-session accessors for bounded Subagent run facts."""

from __future__ import annotations

from tenon.session.host import AgentSessionHost
from tenon.session.persistence.models import SubagentRunRecord


class SessionSubagentMixin(AgentSessionHost):
    """Expose parent-owned Subagent records without owning persistence."""

    @property
    def subagent_records(self) -> list[SubagentRunRecord]:
        """Return persisted and currently observed bounded child-run facts."""
        return self._persistence.subagent_records


__all__ = ["SessionSubagentMixin"]
