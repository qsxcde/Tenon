"""Terminal result constructors for the serial Subagent runner."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from codeagent.core.contracts.subagents import (
    SubagentFailure,
    SubagentFailurePhase,
    SubagentReasonCode,
    SubagentResult,
    SubagentStatus,
)
from codeagent.core.subagent.admission import TerminalAttribution, attribute_cancel_reason

from .runner_support import bounded


def attributed_result(active: Any, attribution: TerminalAttribution) -> SubagentResult:
    """Build one failed child result from a core terminal attribution."""
    failure = SubagentFailure(
        reason_code=attribution.reason_code.value,
        message=bounded(attribution.message),
        phase=attribution.phase.value,
    )
    return SubagentResult(
        delegation_id=active.request.delegation_id,
        status=attribution.status,
        child_run_id=active.child_run_id,
        attempt_id=active.attempt_id,
        failure=failure,
        diagnostics=tuple(active.diagnostics),
        cleanup_uncertain=bool(getattr(active, "cleanup_uncertain", False)),
    )


def failure_result(
    active: Any,
    status: SubagentStatus,
    reason: SubagentReasonCode,
    phase: SubagentFailurePhase,
    error: Exception,
) -> SubagentResult:
    failure = SubagentFailure(
        reason_code=reason.value,
        message=bounded(str(error)),
        phase=phase.value,
    )
    return SubagentResult(
        delegation_id=active.request.delegation_id,
        status=status,
        child_run_id=active.child_run_id,
        attempt_id=active.attempt_id,
        failure=failure,
        diagnostics=tuple(active.diagnostics),
        cleanup_uncertain=bool(getattr(active, "cleanup_uncertain", False)),
    )


def rejected_result(request: Any, reason: str, message: str) -> SubagentResult:
    delegation_id = getattr(request, "delegation_id", "invalid") or "invalid"
    return SubagentResult(
        delegation_id=str(delegation_id),
        status=SubagentStatus.REJECTED,
        failure=SubagentFailure(
            reason_code=reason,
            message=bounded(message),
            phase=SubagentFailurePhase.VALIDATION.value,
        ),
    )


def cancelled_result(active: Any) -> SubagentResult:
    return attributed_result(active, attribute_cancel_reason(None))


def timed_out_result(active: Any) -> SubagentResult:
    return attributed_result(
        active,
        attribute_cancel_reason(SubagentReasonCode.TIMEOUT),
    )


def budget_exceeded_result(active: Any) -> SubagentResult:
    return attributed_result(
        active,
        attribute_cancel_reason(
            SubagentReasonCode.BUDGET_EXCEEDED,
            budget_detail=getattr(active, "budget_detail", None),
        ),
    )


def cancellation_result(active: Any) -> SubagentResult:
    """Map an active cancellation reason to its terminal Subagent result."""
    return attributed_result(
        active,
        attribute_cancel_reason(
            getattr(active, "cancel_reason", None),
            budget_detail=getattr(active, "budget_detail", None),
        ),
    )


def finalize_result(result: SubagentResult, active: Any) -> SubagentResult:
    """Attach post-run cleanup facts after all cleanup work has finished."""
    diagnostics = tuple(active.diagnostics)
    if getattr(active, "cleanup_uncertain", False):
        failure = result.failure
        if failure is not None:
            failure = replace(failure, cleanup_uncertain=True)
        return replace(
            result,
            failure=failure,
            cleanup_uncertain=True,
            diagnostics=diagnostics,
        )
    return replace(result, diagnostics=diagnostics)


__all__ = [
    "attributed_result",
    "budget_exceeded_result",
    "cancellation_result",
    "cancelled_result",
    "failure_result",
    "finalize_result",
    "rejected_result",
    "timed_out_result",
]
