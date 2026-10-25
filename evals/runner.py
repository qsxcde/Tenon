"""离线评测运行器:逐用例建临时工作区,汇总通过/失败并以退出码表达。"""

from __future__ import annotations

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

from evals.cases import CASES, Case, run_case

__all__ = ["CaseResult", "main", "run_all"]


@dataclass(frozen=True)
class CaseResult:
    name: str
    passed: bool
    error: str = ""


async def run_all(cases: tuple[Case, ...] = CASES) -> list[CaseResult]:
    """串行执行全部用例;单个失败不阻塞其余用例。"""
    results: list[CaseResult] = []
    for case in cases:
        with tempfile.TemporaryDirectory(prefix=f"tenon-eval-{case.name}-") as raw:
            workdir = Path(raw)
            try:
                await run_case(case, workdir)
            except Exception as exc:  # noqa: BLE001 - 评测需要保留任何失败原因
                results.append(CaseResult(case.name, False, f"{type(exc).__name__}: {exc}"))
            else:
                results.append(CaseResult(case.name, True))
    return results


def main() -> int:
    results = asyncio.run(run_all())
    failed = [result for result in results if not result.passed]
    for result in results:
        mark = "PASS" if result.passed else "FAIL"
        suffix = f" · {result.error}" if result.error else ""
        print(f"[{mark}] {result.name}{suffix}")
    print(f"\n{len(results) - len(failed)}/{len(results)} 用例通过")
    return 0 if not failed else 1
