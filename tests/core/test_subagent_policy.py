"""Core ownership of Subagent run policy, admission ordering and attribution."""

from __future__ import annotations

import pytest

from codeagent.app.composition.subagent import budget as app_budget
from codeagent.app.composition.subagent import runner_support
from codeagent.core.contracts.subagents import (
    SubagentBudget,
    SubagentFailurePhase,
    SubagentReasonCode,
    SubagentRequest,
    SubagentStatus,
)
from codeagent.core.subagent import (
    DEFAULT_MAX_OUTPUT_CHARS,
    DEFAULT_MAX_TURNS,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_MAX_TURNS,
    SUBAGENT_MVP_MAX_DEPTH,
    SubagentRunPolicy,
    SubagentSlotRegistry,
    TerminalAttribution,
    admit_request,
    attribute_cancel_reason,
    attribute_runner_exception,
    resolve_budget,
)

pytestmark = pytest.mark.contract


def _request(**overrides: object) -> SubagentRequest:
    payload: dict[str, object] = {
        "delegation_id": "del-1",
        "parent_run_id": "run-parent",
        "task": "梳理登录流程入口",
    }
    payload.update(overrides)
    return SubagentRequest(**payload)  # type: ignore[arg-type]


def test_resolve_budget_fills_mvp_defaults_and_exposes_single_source_constants() -> None:
    effective = resolve_budget(SubagentBudget())

    assert effective.max_turns == DEFAULT_MAX_TURNS == 8
    assert effective.max_output_chars == DEFAULT_MAX_OUTPUT_CHARS == 8_000
    assert effective.timeout_seconds == DEFAULT_TIMEOUT_SECONDS == 120.0
    assert app_budget.effective_budget(SubagentBudget()) == effective


def test_resolve_budget_rejects_values_above_hard_caps() -> None:
    with pytest.raises(ValueError, match="max_turns 不得超过 16"):
        resolve_budget(SubagentBudget(max_turns=MAX_MAX_TURNS + 1))


def test_policy_bounds_depth_and_requires_positive_limits() -> None:
    policy = SubagentRunPolicy()

    assert policy.max_depth == SUBAGENT_MVP_MAX_DEPTH == 1
    assert policy.allows_depth(1)
    assert not policy.allows_depth(2)
    assert not policy.allows_depth(-1)
    with pytest.raises(ValueError, match="max_children_per_run"):
        SubagentRunPolicy(max_children_per_run=0)


def test_admission_orders_domain_checks_before_application_errors() -> None:
    # A non-request object is rejected before any other check can fire.
    assert admit_request(object()).reason_code is SubagentReasonCode.INVALID_REQUEST
    # Profile errors outrank budget errors, matching the historical runner order.
    bad = admit_request(
        _request(budget=SubagentBudget(max_turns=99)),
        profile_error="profile 不可用",
    )
    assert bad is not None and bad.reason_code is SubagentReasonCode.PERMISSION_DENIED
    budget_error = admit_request(_request(budget=SubagentBudget(max_turns=99)))
    assert budget_error is not None
    assert budget_error.reason_code is SubagentReasonCode.INVALID_REQUEST
    assert budget_error.message.startswith("budget 无效:")


def test_admission_reports_depth_then_context_then_duplicate() -> None:
    # The contract accepts depth 2 when the request itself allows deeper nesting;
    # the MVP policy owned by core still rejects it.
    deep = admit_request(_request(depth=2, max_depth=3))
    assert deep is not None and deep.reason_code is SubagentReasonCode.DEPTH_EXCEEDED

    context = admit_request(_request(), context_error="context 超过上限")
    assert context is not None and context.message == "context 超过上限"

    duplicate = admit_request(_request(), active_ids=["del-1"])
    assert duplicate is not None
    assert duplicate.message == "委派标识已经处于活动状态"

    assert admit_request(_request(), active_ids=["del-2"]) is None


def test_cancel_reason_attribution_maps_timeout_budget_and_parent() -> None:
    timeout = attribute_cancel_reason(SubagentReasonCode.TIMEOUT)
    assert (timeout.status, timeout.phase) == (
        SubagentStatus.TIMED_OUT,
        SubagentFailurePhase.CANCELLING,
    )
    assert timeout.message == "子 Agent 达到墙钟时间预算"

    budget = attribute_cancel_reason(SubagentReasonCode.BUDGET_EXCEEDED)
    assert budget.status is SubagentStatus.FAILED
    assert budget.message == "子 Agent 达到执行预算"
    detailed = attribute_cancel_reason(
        SubagentReasonCode.BUDGET_EXCEEDED,
        budget_detail="达到工具调用上限",
    )
    assert detailed.message == "达到工具调用上限"

    parent = attribute_cancel_reason(None)
    assert (parent.status, parent.reason_code) == (
        SubagentStatus.CANCELLED,
        SubagentReasonCode.PARENT_CANCELLED,
    )
    assert parent.message == "父 Agent 已取消子运行"


def test_runner_exception_attribution_defaults_to_running_phase() -> None:
    attribution = attribute_runner_exception(RuntimeError("模型连接失败"))

    assert isinstance(attribution, TerminalAttribution)
    assert attribution.status is SubagentStatus.FAILED
    assert attribution.reason_code is SubagentReasonCode.EXECUTION_FAILED
    assert attribution.phase is SubagentFailurePhase.RUNNING
    assert attribution.message == "模型连接失败"


def test_slot_registry_protects_duplicates_and_snapshots_reservation_order() -> None:
    registry: SubagentSlotRegistry[str] = SubagentSlotRegistry()

    assert registry.reserve("del-1", "first")
    assert registry.reserve("del-2", "second")
    assert not registry.reserve("del-1", "again")
    assert not registry.reserve("", "blank")
    assert registry.ids() == ("del-1", "del-2")
    assert registry.items() == (("del-1", "first"), ("del-2", "second"))
    assert registry.get("del-2") == "second"
    assert registry.release("del-1") == "first"
    assert registry.release("missing") is None
    assert len(registry) == 1


def test_slot_registry_capacity_is_opt_in_and_validated() -> None:
    registry: SubagentSlotRegistry[str] = SubagentSlotRegistry(capacity=1)

    assert registry.capacity == 1
    assert registry.reserve("del-1", "only")
    assert registry.is_full()
    assert not registry.reserve("del-2", "overflow")
    with pytest.raises(ValueError, match="capacity 必须为正整数"):
        SubagentSlotRegistry(capacity=0)


def test_application_layer_delegates_limits_and_cleanup_to_core_policy() -> None:
    from codeagent.core.subagent import policy as core_policy

    assert app_budget.EffectiveSubagentBudget is core_policy.EffectiveSubagentBudget
    assert app_budget.effective_budget(SubagentBudget()) == resolve_budget(SubagentBudget())
    assert app_budget.MAX_MAX_TURNS is core_policy.MAX_MAX_TURNS
    assert app_budget.DEFAULT_MAX_CHILDREN_PER_RUN == core_policy.DEFAULT_MAX_CHILDREN_PER_RUN
    assert runner_support.DEFAULT_CLEANUP_TIMEOUT == (core_policy.DEFAULT_CLEANUP_TIMEOUT_SECONDS)
