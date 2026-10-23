"""离线评测框架:用 fake 模型驱动真实 Agent 循环验证端到端可观察行为。

运行:``uv run python -m evals``(不联网、不读用户目录)。
"""

from __future__ import annotations

from evals.cases import CASES, Case
from evals.runner import CaseResult, main, run_all

__all__ = ["CASES", "Case", "CaseResult", "main", "run_all"]
