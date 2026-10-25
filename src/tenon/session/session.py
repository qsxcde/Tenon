"""Stateful session facade assembled from focused session responsibilities."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import is_dataclass, replace
from typing import Any

from tenon.core.context.budget import ContextBudgetSnapshot
from tenon.core.context.contracts import ContextTransformer
from tenon.core.context.diagnostics import ContextDiagnostics
from tenon.core.context.preflight import ContextPreflightResult
from tenon.core.contracts.hooks import (
    HookDiagnostic,
    LifecycleHook,
    LifecycleHookEvent as LifecycleHookEvent,
)
from tenon.core.contracts.ports import ApprovalPolicy
from tenon.core.contracts.messages import Message
from tenon.core.orchestration.config import AgentLoopConfig
from tenon.core.orchestration.loop import DEFAULT_RECURSION_LIMIT
from tenon.session.compaction import CompactionPolicyConfig
from tenon.session.persistence_control import SessionPersistenceMixin
from tenon.session.compaction.summarizer import Summarizer
from tenon.session.constants import (
    COMPACTION_RESERVE_TOKENS,
    DEFAULT_CONTEXT_WINDOW,
    SUMMARY_ID_PREFIX,
    SUMMARY_PREFIX,
)
from tenon.session.contracts import SessionCloser
from tenon.session.eventing import SessionEventMixin
from tenon.session.lifecycle import SessionLifecycleMixin
from tenon.session.persistence.models import SessionRecoveryReport, SessionStore, UsageStats
from tenon.session.runtime.controller import SessionRuntime
from tenon.session.runtime.state import CommitStatus, RunOutcome, SessionBudgetState
from tenon.session.compaction_runtime import SessionCompactionMixin
from tenon.session.run_coordinator import SessionRunCoordinator
from tenon.session.session_persistence import SessionPersistence
from tenon.session.subagent import SessionSubagentMixin
from tenon.session.runtime.error_policy import friendly_error
from tenon.session.events.bus import EventBus, Subscriber


class AgentSession(
    SessionEventMixin,
    SessionLifecycleMixin,
    SessionCompactionMixin,
    SessionPersistenceMixin,
    SessionSubagentMixin,
):
    """Public facade for one stateful agent conversation."""

    def __init__(
        self,
        config: AgentLoopConfig,
        bus: EventBus,
        *,
        store: SessionStore | None = None,
        session_id: str | None = None,
        recursion_limit: int = DEFAULT_RECURSION_LIMIT,
        tool_timeout: float | None = None,
        confirmation_timeout: float | None = None,
        previous_session_id: str | None = None,
        summarizer: Summarizer | None = None,
        context_window: int | None = None,
        compact_budget: int | None = None,
        compaction_policy: CompactionPolicyConfig | None = None,
        defer_persistence: bool = False,
        persistence_options: dict[str, Any] | None = None,
        runtime_closer: SessionCloser | None = None,
        transform_context: ContextTransformer | None = None,
        policy: ApprovalPolicy | None = None,
        lifecycle_hooks: tuple[LifecycleHook, ...] | None = None,
    ) -> None:
        self._lifecycle_hooks = tuple(lifecycle_hooks) if lifecycle_hooks is not None else None
        if self._lifecycle_hooks is not None:
            if not is_dataclass(config):
                getattr(config, "model")
                config = getattr(config, "_real", None)
            if config is None:  # pragma: no cover - defensive lazy-config guard
                raise TypeError("lifecycle hooks require a materialized AgentLoopConfig")
            config = replace(config, lifecycle_hooks=self._lifecycle_hooks)
        self._config = config
        self._policy = policy
        self._bus = bus
        self._recursion_limit = recursion_limit
        self._tool_timeout = tool_timeout
        self._session_id = session_id or str(uuid.uuid4())
        self._previous_session_id = previous_session_id
        self._summarizer = summarizer
        self._context_window = self._resolve_context_window(config, context_window)
        self._runtime_closer = runtime_closer
        self._budget_state = SessionBudgetState()
        self._transform_context = transform_context
        self._closed = False
        self._close_task: asyncio.Task[None] | None = None
        self._lifecycle_hook_tasks: set[asyncio.Task[Any]] = set()
        self._lifecycle_hook_diagnostics: list[HookDiagnostic] = []
        if compaction_policy is None:
            compaction_policy = CompactionPolicyConfig(compact_budget=compact_budget)
        elif compact_budget is not None:
            compaction_policy = replace(compaction_policy, compact_budget=compact_budget)
        self._compaction_policy = compaction_policy
        self._compact_budget = compact_budget
        self._compaction_gate = asyncio.Lock()
        self._last_compaction_fingerprint: tuple[Any, ...] | None = None
        self._last_compaction_failure_fingerprint: tuple[Any, ...] | None = None
        self._pending_compaction_budget: ContextBudgetSnapshot | None = None
        self._last_input_tokens: int | None = None
        self._persistence = SessionPersistence(
            store,
            self._session_id,
            defer_persistence=defer_persistence,
            persistence_options=persistence_options,
        )
        self._runtime = SessionRuntime(
            self._emit,
            self._on_run_event,
            session_id=self._session_id,
            confirmation_timeout=confirmation_timeout,
        )
        self._run_coordinator = SessionRunCoordinator(self)
        restored = self._persistence.load()
        self._history = restored.history
        self._summary: str | None = restored.summary
        self._summary_entry_id: str | None = restored.summary_entry_id
        self._prev_details: dict[str, Any] = restored.details
        self._last_input_tokens = restored.context_tokens
        self._bus.subscribe(self._on_internal_event)

    @staticmethod
    def _resolve_context_window(
        config: AgentLoopConfig,
        context_window: int | None,
    ) -> int:
        if context_window is None:
            model_window = getattr(getattr(config, "model", None), "context_window", None)
            return (
                model_window
                if type(model_window) is int and model_window > 0
                else DEFAULT_CONTEXT_WINDOW
            )
        if type(context_window) is not int or context_window < 1:
            raise ValueError("context_window must be positive")
        return context_window

    @property
    def _current_task(self) -> asyncio.Task[None] | None:
        """Compatibility view; task ownership lives in SessionRuntime."""
        return self._runtime.current_task

    @_current_task.setter
    def _current_task(self, task: asyncio.Task[None] | None) -> None:
        self._runtime.current_task = task

    def subscribe(self, fn: Subscriber) -> Callable[[], None]:
        return self._bus.subscribe(fn)

    @property
    def lifecycle_hook_diagnostics(self) -> list[HookDiagnostic]:
        """Return core and session Hook failures collected in memory."""
        core_diagnostics = getattr(self._runtime, "hook_diagnostics", ())
        return [*core_diagnostics, *self._lifecycle_hook_diagnostics]

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def history(self) -> list[Message]:
        return list(self._history)

    @property
    def usage(self) -> UsageStats:
        return self._persistence.usage

    @property
    def committed_usage(self) -> UsageStats:
        return self._persistence.usage

    @property
    def context_budget(self) -> ContextBudgetSnapshot | None:
        return self._budget_state.latest_estimate

    @property
    def context_diagnostics(self) -> ContextDiagnostics:
        """Return the latest runtime-only context diagnostic snapshot."""
        return self._budget_state.diagnostics

    @property
    def recovery_report(self) -> SessionRecoveryReport:
        """Return the persistence recovery result captured at construction."""
        return self._persistence.recovery_report

    @property
    def model_id(self) -> str | None:
        """Return the configured model id for diagnostic labeling."""
        model = getattr(self._config, "model", None)
        value = getattr(model, "model_id", None) or getattr(model, "id", None)
        return str(value) if value else None

    @property
    def context_preflight(self) -> ContextPreflightResult | None:
        return self._budget_state.latest_preflight

    @property
    def last_actual_usage(self) -> UsageStats | None:
        return self._budget_state.latest_actual_usage

    @property
    def is_persisted(self) -> bool:
        return self._persistence.persisted

    @property
    def is_running(self) -> bool:
        """Return whether this resident session currently owns an active run."""
        return self._runtime.active_run_id is not None

    @property
    def active_run_id(self) -> str | None:
        """Return the current run identifier for parent/child correlation."""
        return self._runtime.active_run_id

    @property
    def context_tokens(self) -> int | None:
        return self._last_input_tokens

    @property
    def context_window(self) -> int:
        return self._context_window

    @property
    def policy(self) -> ApprovalPolicy | None:
        return self._policy

    @property
    def summary(self) -> str | None:
        return self._summary

    @property
    def last_failure(self) -> dict[str, Any] | None:
        failure = self._runtime.last_failure
        return dict(failure) if failure is not None else None

    @property
    def last_outcome(self) -> RunOutcome | None:
        return self._runtime.last_outcome

    async def run(
        self,
        text: str,
        recursion_limit: int | None = None,
        *,
        policy: ApprovalPolicy | None = None,
    ) -> None:
        return await self._run_coordinator.run(text, recursion_limit, policy)

    def _rollback(self, before_ids: set[str]) -> None:
        self._history = [message for message in self._history if message.id in before_ids]

    def _rollback_status(self) -> CommitStatus:
        return (
            CommitStatus.UNCERTAIN if self._runtime.cleanup_uncertain else CommitStatus.ROLLED_BACK
        )

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        return friendly_error(exc)


__all__ = [
    "AgentSession",
    "COMPACTION_RESERVE_TOKENS",
    "DEFAULT_CONTEXT_WINDOW",
    "SUMMARY_ID_PREFIX",
    "SUMMARY_PREFIX",
]
