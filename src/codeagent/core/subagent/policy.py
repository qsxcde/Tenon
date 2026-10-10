"""Core-owned Subagent run policy: budgets, caps and bounded diagnostics.

AGENTS.md assigns domain rules and orchestration to ``core/``. These limits are
domain decisions, not wiring decisions, so the application layer must read them
from here instead of owning a second copy that can silently drift.
"""

from __future__ import annotations

from dataclasses import dataclass

from codeagent.core.contracts.subagents import SubagentBudget

__all__ = [
    "DEFAULT_CLEANUP_TIMEOUT_SECONDS",
    "DEFAULT_MAX_CHILDREN_PER_RUN",
    "DEFAULT_MAX_OUTPUT_CHARS",
    "DEFAULT_MAX_TOOL_CALLS",
    "DEFAULT_MAX_TURNS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DiagnosticLimits",
    "DIAGNOSTIC_LIMITS",
    "MAX_DIAGNOSTIC_CHARS",
    "MAX_MAX_OUTPUT_CHARS",
    "MAX_MAX_TOOL_CALLS",
    "MAX_MAX_TURNS",
    "MAX_DIAGNOSTICS",
    "MAX_TIMEOUT_SECONDS",
    "SUBAGENT_MVP_MAX_DEPTH",
    "SubagentRunPolicy",
    "resolve_budget",
]

DEFAULT_MAX_CHILDREN_PER_RUN = 4
DEFAULT_MAX_TURNS = 8
DEFAULT_MAX_TOOL_CALLS = 32
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_MAX_OUTPUT_CHARS = 8_000
DEFAULT_CLEANUP_TIMEOUT_SECONDS = 10.0

MAX_MAX_TURNS = 16
MAX_MAX_TOOL_CALLS = 64
MAX_TIMEOUT_SECONDS = 300.0
MAX_MAX_OUTPUT_CHARS = 16_000

#: The v0.5 MVP is serial and single-level; children never delegate further.
SUBAGENT_MVP_MAX_DEPTH = 1

MAX_DIAGNOSTICS = 8
MAX_DIAGNOSTIC_CHARS = 2_000


@dataclass(frozen=True, slots=True)
class DiagnosticLimits:
    """Bounds for the diagnostics one delegation may accumulate."""

    max_items: int = MAX_DIAGNOSTICS
    max_chars: int = MAX_DIAGNOSTIC_CHARS


DIAGNOSTIC_LIMITS = DiagnosticLimits()


@dataclass(frozen=True, slots=True)
class SubagentRunPolicy:
    """Immutable domain limits shared by admission and the runner."""

    max_depth: int = SUBAGENT_MVP_MAX_DEPTH
    max_children_per_run: int = DEFAULT_MAX_CHILDREN_PER_RUN
    cleanup_timeout: float = DEFAULT_CLEANUP_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if self.max_depth < 0:
            raise ValueError("max_depth 不能为负数")
        if self.max_children_per_run <= 0:
            raise ValueError("max_children_per_run 必须为正整数")
        if self.cleanup_timeout <= 0:
            raise ValueError("cleanup_timeout 必须为正数")

    def allows_depth(self, depth: int) -> bool:
        """Return whether one more delegation level is permitted."""
        return 0 <= depth <= self.max_depth


@dataclass(frozen=True, slots=True)
class EffectiveSubagentBudget:
    """A fully materialized budget that a child run can rely on."""

    max_turns: int
    max_tool_calls: int
    timeout_seconds: float
    max_output_chars: int


_BUDGET_LIMITS: tuple[tuple[str, str, float], ...] = (
    ("max_turns", "MAX_MAX_TURNS", MAX_MAX_TURNS),
    ("max_tool_calls", "MAX_MAX_TOOL_CALLS", MAX_MAX_TOOL_CALLS),
    ("timeout_seconds", "MAX_TIMEOUT_SECONDS", MAX_TIMEOUT_SECONDS),
    ("max_output_chars", "MAX_MAX_OUTPUT_CHARS", MAX_MAX_OUTPUT_CHARS),
)


def resolve_budget(budget: SubagentBudget | None) -> EffectiveSubagentBudget:
    """Fill MVP defaults and reject values above the hard safety caps."""
    resolved = budget or SubagentBudget()
    if not isinstance(resolved, SubagentBudget):
        raise ValueError("budget 必须是 SubagentBudget")
    effective = EffectiveSubagentBudget(
        max_turns=resolved.max_turns or DEFAULT_MAX_TURNS,
        max_tool_calls=resolved.max_tool_calls or DEFAULT_MAX_TOOL_CALLS,
        timeout_seconds=float(resolved.timeout_seconds or DEFAULT_TIMEOUT_SECONDS),
        max_output_chars=resolved.max_output_chars or DEFAULT_MAX_OUTPUT_CHARS,
    )
    for name, _, cap in _BUDGET_LIMITS:
        value = getattr(effective, name)
        if value > cap:
            raise ValueError(f"{name} 不得超过 {cap}")
    return effective
