"""Model-facing budget parsing for one application-layer Subagent delegation.

The numeric defaults and hard caps are domain policy and live in
``tenon.core.subagent.policy``; this module only adapts the untrusted
tool-input shape into that policy and keeps the historical import names stable.
"""

from __future__ import annotations

from collections.abc import Mapping

from tenon.core.contracts.subagents import SubagentBudget
from tenon.core.subagent.policy import (  # noqa: F401  (re-exported for callers)
    DEFAULT_MAX_CHILDREN_PER_RUN,
    DEFAULT_MAX_OUTPUT_CHARS,
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_MAX_TURNS,
    DEFAULT_TIMEOUT_SECONDS,
    EffectiveSubagentBudget,
    MAX_MAX_OUTPUT_CHARS,
    MAX_MAX_TOOL_CALLS,
    MAX_MAX_TURNS,
    MAX_TIMEOUT_SECONDS,
    resolve_budget,
)

_BUDGET_FIELDS = frozenset({"max_turns", "max_tool_calls", "timeout_seconds", "max_output_chars"})


def parse_budget(value: object) -> SubagentBudget:
    """Parse the model-facing budget object without silently accepting fields."""
    if value is None:
        return SubagentBudget()
    if not isinstance(value, Mapping):
        raise ValueError("delegate.budget 必须是对象")
    unknown = set(value) - _BUDGET_FIELDS
    if unknown:
        names = ", ".join(sorted(str(item) for item in unknown))
        raise ValueError(f"delegate.budget 包含未知字段: {names}")
    values = {}
    for name in _BUDGET_FIELDS:
        if name not in value:
            continue
        if value[name] is None:
            raise ValueError(f"delegate.budget.{name} 不能为 null")
        values[name] = value[name]
    try:
        budget = SubagentBudget(**values)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"delegate.budget 无效: {exc}") from exc
    effective_budget(budget)
    return budget


def effective_budget(budget: SubagentBudget) -> EffectiveSubagentBudget:
    """Fill defaults and enforce the hard safety caps via core policy."""
    return resolve_budget(budget)


__all__ = [
    "DEFAULT_MAX_CHILDREN_PER_RUN",
    "DEFAULT_MAX_OUTPUT_CHARS",
    "DEFAULT_MAX_TOOL_CALLS",
    "DEFAULT_MAX_TURNS",
    "DEFAULT_TIMEOUT_SECONDS",
    "EffectiveSubagentBudget",
    "MAX_MAX_OUTPUT_CHARS",
    "MAX_MAX_TOOL_CALLS",
    "MAX_MAX_TURNS",
    "MAX_TIMEOUT_SECONDS",
    "effective_budget",
    "parse_budget",
]
