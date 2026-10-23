"""离线评测套件的回归门禁:评测用例失败即测试失败。"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.contract


async def test_offline_eval_suite_passes():
    from evals.runner import run_all

    results = await run_all()
    assert results, "评测套件不应为空"
    failures = [f"{result.name}: {result.error}" for result in results if not result.passed]
    assert not failures, "评测失败:\n" + "\n".join(failures)
