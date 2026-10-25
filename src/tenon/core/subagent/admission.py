"""Domain-side admission and terminal attribution rules for delegated runs."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from tenon.core.contracts.subagents import (
    SubagentFailurePhase,
    SubagentReasonCode,
    SubagentRequest,
    SubagentStatus,
)

from .policy import SubagentRunPolicy, resolve_budget

__all__ = [
    "AdmissionRejection",
    "TerminalAttribution",
    "admit_request",
    "attribute_cancel_reason",
    "attribute_runner_exception",
    "default_run_policy",
]

_DEFAULT_POLICY = SubagentRunPolicy()


def default_run_policy() -> SubagentRunPolicy:
    """Return the shared MVP policy instance."""
    return _DEFAULT_POLICY


@dataclass(frozen=True, slots=True)
class AdmissionRejection:
    """Why one request must be rejected before any child resource is used."""

    reason_code: SubagentReasonCode
    message: str


@dataclass(frozen=True, slots=True)
class TerminalAttribution:
    """The terminal status, reason and phase one outcome maps to."""

    status: SubagentStatus
    reason_code: SubagentReasonCode
    phase: SubagentFailurePhase
    message: str


def admit_request(
    request: object,
    *,
    policy: SubagentRunPolicy | None = None,
    active_ids: Iterable[str] = (),
    profile_error: str | None = None,
    context_error: str | None = None,
) -> AdmissionRejection | None:
    """Validate a request against domain policy without touching infrastructure.

    The checks run in the order the runner has always used them, so a request
    that would have been rejected mid-flight still reports the same reason code.
    ``profile_error`` and ``context_error`` are supplied by the application layer
    because the profile registry and context size limits are wiring decisions;
    their position in the ordering stays a domain decision owned here.
    """
    run_policy = policy or _DEFAULT_POLICY
    if not isinstance(request, SubagentRequest):
        return AdmissionRejection(SubagentReasonCode.INVALID_REQUEST, "委派请求类型无效")
    if profile_error is not None:
        return AdmissionRejection(SubagentReasonCode.PERMISSION_DENIED, profile_error)
    try:
        resolve_budget(request.budget)
    except ValueError as exc:
        return AdmissionRejection(
            SubagentReasonCode.INVALID_REQUEST,
            f"budget 无效: {exc}",
        )
    if not run_policy.allows_depth(request.depth) or request.depth > request.max_depth:
        return AdmissionRejection(
            SubagentReasonCode.DEPTH_EXCEEDED,
            "子 Agent 深度超过当前 MVP 限制",
        )
    if context_error is not None:
        return AdmissionRejection(SubagentReasonCode.INVALID_REQUEST, context_error)
    if request.delegation_id in set(active_ids):
        return AdmissionRejection(
            SubagentReasonCode.INVALID_REQUEST,
            "委派标识已经处于活动状态",
        )
    return None


def attribute_runner_exception(
    error: BaseException,
    *,
    phase: SubagentFailurePhase = SubagentFailurePhase.RUNNING,
) -> TerminalAttribution:
    """Normalize an unexpected runner failure into one terminal attribution."""
    return TerminalAttribution(
        status=SubagentStatus.FAILED,
        reason_code=SubagentReasonCode.EXECUTION_FAILED,
        phase=phase,
        message=str(error),
    )


def attribute_cancel_reason(
    reason: SubagentReasonCode | None,
    *,
    budget_detail: str | None = None,
) -> TerminalAttribution:
    """Map a cancellation reason onto its terminal status and message."""
    if reason is SubagentReasonCode.TIMEOUT:
        return TerminalAttribution(
            status=SubagentStatus.TIMED_OUT,
            reason_code=SubagentReasonCode.TIMEOUT,
            phase=SubagentFailurePhase.CANCELLING,
            message="子 Agent 达到墙钟时间预算",
        )
    if reason is SubagentReasonCode.BUDGET_EXCEEDED:
        return TerminalAttribution(
            status=SubagentStatus.FAILED,
            reason_code=SubagentReasonCode.BUDGET_EXCEEDED,
            phase=SubagentFailurePhase.CANCELLING,
            message=budget_detail or "子 Agent 达到执行预算",
        )
    return TerminalAttribution(
        status=SubagentStatus.CANCELLED,
        reason_code=SubagentReasonCode.PARENT_CANCELLED,
        phase=SubagentFailurePhase.CANCELLING,
        message="父 Agent 已取消子运行",
    )
