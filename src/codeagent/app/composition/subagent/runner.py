"""Serial application-layer runner for temporary Subagent sessions."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from codeagent.core.contracts.events import AgentEvent
from codeagent.core.contracts.subagents import (
    SubagentReasonCode,
    SubagentRequest,
    SubagentResult,
)
from codeagent.core.subagent import (
    SubagentSlotRegistry,
    admit_request,
    attribute_runner_exception,
)

from .active import ActiveDelegation
from .budget import effective_budget
from .context import validate_context_items
from .event_diagnostics import (
    make_finished_event,
    make_queued_event,
    publish_event,
)
from .lifecycle import commit_terminal, mark_queued
from .profiles import profile_error_message, profile_for
from .runner_execution import run_active
from .runner_results import (
    attributed_result,
    cancellation_result,
    finalize_result,
    rejected_result,
)
from .runner_support import (
    DEFAULT_CLEANUP_TIMEOUT,
    cancel_session,
    close_active,
)

ChildSessionFactory = Callable[[SubagentRequest], Any]


class SerialSubagentRunner:
    """Run at most one isolated child Session at a time.

    Admission ordering, delegation identity arbitration and terminal
    attribution are core policy (``codeagent.core.subagent``); this class only
    wires those decisions onto a real child Session.
    """

    def __init__(
        self,
        child_session_factory: ChildSessionFactory,
        *,
        cleanup_timeout: float = DEFAULT_CLEANUP_TIMEOUT,
    ) -> None:
        if not callable(child_session_factory):
            raise TypeError("child_session_factory must be callable")
        if cleanup_timeout <= 0:
            raise ValueError("cleanup_timeout must be positive")
        self._child_session_factory = child_session_factory
        self._cleanup_timeout = float(cleanup_timeout)
        self._lock = asyncio.Lock()
        self._slots: SubagentSlotRegistry[ActiveDelegation] = SubagentSlotRegistry()

    @property
    def active_delegations(self) -> dict[str, str | None]:
        """Return a read-only diagnostic snapshot of active child identities."""
        return {
            delegation_id: getattr(active.session, "session_id", None)
            for delegation_id, active in self._slots.items()
        }

    async def execute(
        self,
        request: SubagentRequest,
        *,
        on_event: Callable[[AgentEvent], Any] | None = None,
    ) -> SubagentResult:
        rejection = self._validate_request(request)
        if rejection is not None:
            return rejection

        active = ActiveDelegation(request, cleanup_timeout=self._cleanup_timeout)
        active.execution_task = asyncio.current_task()
        active.budget = effective_budget(request.budget)
        if not self._slots.reserve(request.delegation_id, active):
            return rejected_result(
                request,
                SubagentReasonCode.INVALID_REQUEST.value,
                "委派标识已经处于活动状态",
            )
        result: SubagentResult | None = None
        re_raise_cancelled = False
        mark_queued(active)
        try:
            await publish_event(on_event, make_queued_event(active), active)
            timeout_scope = asyncio.timeout(active.budget.timeout_seconds)
            async with timeout_scope:
                result = await run_active(
                    self._lock,
                    self._child_session_factory,
                    active,
                    on_event,
                )
        except asyncio.TimeoutError:
            if not timeout_scope.expired():
                raise
            active.cancel_requested = True
            active.cancel_reason = SubagentReasonCode.TIMEOUT
            await cancel_session(active, timeout=self._cleanup_timeout)
            result = cancellation_result(active)
        except asyncio.CancelledError:
            externally_cancelled = not active.cancel_requested
            active.cancel_requested = True
            active.cancel_reason = active.cancel_reason or SubagentReasonCode.PARENT_CANCELLED
            await cancel_session(active, timeout=self._cleanup_timeout)
            result = cancellation_result(active)
            re_raise_cancelled = externally_cancelled
        except Exception as exc:  # noqa: BLE001 - normalize runner failures
            result = attributed_result(active, attribute_runner_exception(exc))
        finally:
            active.event_forwarding_closed = True
            await close_active(active, timeout=self._cleanup_timeout)
        if result is None:  # pragma: no cover - defensive terminal fallback
            result = attributed_result(
                active,
                attribute_runner_exception(RuntimeError("子 Agent 没有产生终态结果")),
            )
        result = finalize_result(result, active)
        result = commit_terminal(active, result)
        try:
            await publish_event(on_event, make_finished_event(active, result), active)
        finally:
            self._slots.release(request.delegation_id)
        if re_raise_cancelled:
            raise asyncio.CancelledError
        return result

    async def cancel(self, delegation_id: str) -> bool:
        active = self._slots.get(delegation_id)
        if active is None:
            return False
        active.cancel_requested = True
        active.cancel_reason = SubagentReasonCode.PARENT_CANCELLED
        await cancel_session(active, timeout=self._cleanup_timeout)
        return True

    def _validate_request(self, request: Any) -> SubagentResult | None:
        profile_error, context_error = self._collect_application_errors(request)
        rejection = admit_request(
            request,
            active_ids=self._slots.ids(),
            profile_error=profile_error,
            context_error=context_error,
        )
        if rejection is None:
            return None
        return rejected_result(request, rejection.reason_code.value, rejection.message)

    @staticmethod
    def _collect_application_errors(
        request: Any,
    ) -> tuple[str | None, str | None]:
        """Run the application-owned checks, leaving their ordering to core."""
        if not isinstance(request, SubagentRequest):
            return None, None
        profile_error: str | None = None
        try:
            profile_for(request.profile)
        except ValueError:
            profile_error = profile_error_message(request.profile)
        context_error: str | None = None
        try:
            validate_context_items(request.context)
        except ValueError as exc:
            context_error = str(exc)
        return profile_error, context_error


__all__ = ["ChildSessionFactory", "SerialSubagentRunner"]
