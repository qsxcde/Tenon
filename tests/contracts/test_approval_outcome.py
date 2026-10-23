"""审批封闭终态与 fail-closed 映射契约(边界:超时/取消/确认拒绝)。"""

from __future__ import annotations

import asyncio

import pytest

from codeagent.core.contracts.ports import (
    ApprovalOutcome,
    ApprovalResult,
    PolicyDecision,
    ToolDecision,
)

pytestmark = pytest.mark.contract


def test_approval_outcome_is_closed_set():
    """终态集合封闭:映射方与消费方只能取这五个值。"""
    assert [item.value for item in ApprovalOutcome] == [
        "allowed_once",
        "rejected",
        "cancelled",
        "timed_out",
        "unavailable",
    ]


def test_from_response_maps_confirm_and_reject():
    """边界-确认拒绝:拒绝映射 REJECTED,默认原因对模型可见。"""
    assert ApprovalResult.from_response(True).outcome is ApprovalOutcome.ALLOWED_ONCE
    rejected = ApprovalResult.from_response(False)
    assert rejected.outcome is ApprovalOutcome.REJECTED
    assert rejected.reason == "用户拒绝执行"


def test_from_exception_attributes_timeout_and_cancel():
    """边界-超时/取消:超时归 TIMED_OUT,取消归 CANCELLED,其余归 UNAVAILABLE。"""

    class _ConfirmationTimeout(TimeoutError):
        pass

    timed_out = ApprovalResult.from_exception(_ConfirmationTimeout("t"))
    cancelled = ApprovalResult.from_exception(asyncio.CancelledError())
    unavailable = ApprovalResult.from_exception(RuntimeError("通道故障"))
    assert timed_out.outcome is ApprovalOutcome.TIMED_OUT
    assert cancelled.outcome is ApprovalOutcome.CANCELLED
    assert unavailable.outcome is ApprovalOutcome.UNAVAILABLE


@pytest.mark.parametrize("outcome", list(ApprovalOutcome))
def test_fail_closed_only_allowed_once_executes(outcome):
    """fail-closed:仅 ALLOWED_ONCE 放行,其余终态一律拒绝且带可诊断原因。"""
    result = ApprovalResult(outcome)
    tool = result.to_tool_decision()
    policy = result.to_policy_decision()
    assert result.is_allowed is (outcome is ApprovalOutcome.ALLOWED_ONCE)
    if outcome is ApprovalOutcome.ALLOWED_ONCE:
        assert isinstance(tool, ToolDecision) and tool.action == "allow"
        assert isinstance(policy, PolicyDecision) and policy.action == "allow"
    else:
        assert tool.action == "block" and tool.reason
        assert policy.action == "deny" and policy.reason
