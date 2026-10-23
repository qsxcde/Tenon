"""Application-layer Subagent runners: serial (default) and bounded-parallel."""

from __future__ import annotations

from .runner_base import BaseSubagentRunner, ChildSessionFactory
from .runner_support import DEFAULT_CLEANUP_TIMEOUT_SECONDS

#: 并行 runner 的保守默认并发:允许重叠子任务,仍远低于父级配额。
DEFAULT_SUBAGENT_CONCURRENCY = 3


class SerialSubagentRunner(BaseSubagentRunner):
    """Run at most one isolated child Session at a time."""

    def __init__(
        self,
        child_session_factory: ChildSessionFactory,
        *,
        cleanup_timeout: float = DEFAULT_CLEANUP_TIMEOUT_SECONDS,
    ) -> None:
        super().__init__(
            child_session_factory,
            max_concurrency=1,
            cleanup_timeout=cleanup_timeout,
        )


class ParallelSubagentRunner(BaseSubagentRunner):
    """Run up to ``max_concurrency`` isolated child Sessions concurrently.

    每个子任务仍保有自己的预算、取消与有界清理;并发只放宽执行槽位,
    不改变准入顺序、终态归因或父级配额。
    """

    def __init__(
        self,
        child_session_factory: ChildSessionFactory,
        *,
        max_concurrency: int = DEFAULT_SUBAGENT_CONCURRENCY,
        cleanup_timeout: float = DEFAULT_CLEANUP_TIMEOUT_SECONDS,
    ) -> None:
        if type(max_concurrency) is not int or max_concurrency < 2:
            raise ValueError("并行 runner 的 max_concurrency 必须 ≥ 2")
        super().__init__(
            child_session_factory,
            max_concurrency=max_concurrency,
            cleanup_timeout=cleanup_timeout,
        )


__all__ = [
    "ChildSessionFactory",
    "DEFAULT_SUBAGENT_CONCURRENCY",
    "ParallelSubagentRunner",
    "SerialSubagentRunner",
]
