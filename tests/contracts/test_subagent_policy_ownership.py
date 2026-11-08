"""Contract: the delegate tool must read Subagent limits from core policy.

AGENTS.md assigns subagent budgets, caps, depth and quota to ``core/subagent``
and forbids the application layer from keeping a second copy that can silently
drift. These tests pin that ownership so a future change to
``default_run_policy()`` cannot quietly stop affecting the delegate tool.
"""

from __future__ import annotations

from typing import Any

import pytest

from tenon.app.composition.subagent.delegate_tool import DelegateTool
from tenon.core.contracts.subagents import (
    SubagentBudget,
    SubagentRequest,
    SubagentResult,
)
from tenon.core.subagent import SubagentRunPolicy, default_run_policy

pytestmark = pytest.mark.contract


class _NoopRunner:
    """A runner stub that never executes a child; the tests stay off the loop."""

    async def execute(
        self, request: SubagentRequest, *, on_event: Any = None
    ) -> SubagentResult:  # pragma: no cover - never reached
        raise AssertionError("execute must not be reached")

    async def cancel(self, delegation_id: str) -> bool:  # pragma: no cover
        return False


def _delegate_arguments() -> Any:
    from tenon.app.composition.subagent.delegate_tool import _DelegateArguments

    return _DelegateArguments(
        task="inspect",
        profile="explore",
        context=(),
        budget=SubagentBudget(),
    )


def test_delegate_tool_reads_quota_from_core_policy(monkeypatch) -> None:
    # A policy with a distinctive quota proves the tool consults core, not a copy.
    custom = SubagentRunPolicy(max_children_per_run=7)
    monkeypatch.setattr(
        "tenon.app.composition.subagent.delegate_tool.default_run_policy",
        lambda: custom,
    )

    tool = DelegateTool(_NoopRunner())

    assert tool._max_children_per_run == 7


def test_delegate_tool_reads_depth_ceiling_from_core_policy(monkeypatch) -> None:
    custom = SubagentRunPolicy(max_depth=2)
    monkeypatch.setattr(
        "tenon.app.composition.subagent.delegate_tool.default_run_policy",
        lambda: custom,
    )

    tool = DelegateTool(_NoopRunner()).bind_parent_run_id("parent-run")
    # _build_request is the single place the request's max_depth is set.
    request = tool._build_request(_delegate_arguments())

    assert request.depth == 1
    assert request.max_depth == 2


def test_default_quota_matches_core_policy_value() -> None:
    # Without any override, the default must equal core's policy value.
    tool = DelegateTool(_NoopRunner())

    assert tool._max_children_per_run == default_run_policy().max_children_per_run


def test_explicit_max_children_per_run_still_overrides_core_default() -> None:
    # Construction-time override stays supported, but only on explicit request;
    # the default path is core-owned.
    tool = DelegateTool(_NoopRunner(), max_children_per_run=3)

    assert tool._max_children_per_run == 3
