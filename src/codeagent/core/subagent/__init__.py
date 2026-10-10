"""Core-owned Subagent domain rules.

This package holds the delegation *policy* (budgets, caps, admission, terminal
attribution and serial slot arbitration). Concrete child-session creation,
event publishing and session cleanup stay in ``app/composition/subagent`` so the
domain layer keeps no dependency on sessions, tools or transports.
"""

from __future__ import annotations

from .admission import (
    AdmissionRejection,
    TerminalAttribution,
    admit_request,
    attribute_cancel_reason,
    attribute_runner_exception,
    default_run_policy,
)
from .policy import (
    DEFAULT_CLEANUP_TIMEOUT_SECONDS,
    DEFAULT_MAX_CHILDREN_PER_RUN,
    DEFAULT_MAX_OUTPUT_CHARS,
    DEFAULT_MAX_TOOL_CALLS,
    DEFAULT_MAX_TURNS,
    DEFAULT_TIMEOUT_SECONDS,
    DIAGNOSTIC_LIMITS,
    MAX_DIAGNOSTICS,
    MAX_DIAGNOSTIC_CHARS,
    MAX_MAX_OUTPUT_CHARS,
    MAX_MAX_TOOL_CALLS,
    MAX_MAX_TURNS,
    MAX_TIMEOUT_SECONDS,
    SUBAGENT_MVP_MAX_DEPTH,
    EffectiveSubagentBudget,
    SubagentRunPolicy,
    resolve_budget,
)
from .slots import SubagentSlotRegistry

__all__ = [
    "AdmissionRejection",
    "DEFAULT_CLEANUP_TIMEOUT_SECONDS",
    "DEFAULT_MAX_CHILDREN_PER_RUN",
    "DEFAULT_MAX_OUTPUT_CHARS",
    "DEFAULT_MAX_TOOL_CALLS",
    "DEFAULT_MAX_TURNS",
    "DEFAULT_TIMEOUT_SECONDS",
    "EffectiveSubagentBudget",
    "DIAGNOSTIC_LIMITS",
    "MAX_DIAGNOSTICS",
    "MAX_DIAGNOSTIC_CHARS",
    "MAX_MAX_OUTPUT_CHARS",
    "MAX_MAX_TOOL_CALLS",
    "MAX_MAX_TURNS",
    "MAX_TIMEOUT_SECONDS",
    "SUBAGENT_MVP_MAX_DEPTH",
    "SubagentRunPolicy",
    "SubagentSlotRegistry",
    "TerminalAttribution",
    "admit_request",
    "attribute_cancel_reason",
    "attribute_runner_exception",
    "default_run_policy",
    "resolve_budget",
]
