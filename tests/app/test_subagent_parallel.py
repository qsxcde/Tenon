"""并行 Subagent runner 行为测试(离线:假子 Session,无模型/无网络)。"""

from __future__ import annotations

import asyncio

import pytest

from codeagent.app.composition.subagent.factory import create_subagent_runner
from codeagent.app.composition.subagent.runner import (
    ParallelSubagentRunner,
    SerialSubagentRunner,
)
from codeagent.core.contracts.subagents import SubagentRequest, SubagentStatus


class _FakeChild:
    """最小子 Session:记录并发峰值,阻塞直到测试放行。"""

    def __init__(self, *, release: asyncio.Event, tracker: dict[str, int]) -> None:
        self.session_id = f"child-{len(tracker)}"
        self.history: list = []
        self.last_outcome = None
        self._release = release
        self._tracker = tracker

    def subscribe(self, listener):
        del listener
        return lambda: None

    async def run(self, prompt: str) -> str:
        del prompt
        self._tracker["active"] += 1
        self._tracker["peak"] = max(self._tracker["peak"], self._tracker["active"])
        try:
            await self._release.wait()
        finally:
            self._tracker["active"] -= 1
        return f"done-{self.session_id}"


def _request(delegation_id: str) -> SubagentRequest:
    return SubagentRequest(
        delegation_id=delegation_id,
        parent_run_id="parent-run",
        task="do work",
        profile="explore",
    )


async def _wait_until_started(tracker: dict[str, int], count: int) -> None:
    for _ in range(200):
        if tracker["peak"] >= count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"子 Agent 未达到并发 {count}: {tracker}")


@pytest.mark.contract
async def test_parallel_runner_overlaps_children_up_to_capacity():
    release = asyncio.Event()
    tracker = {"active": 0, "peak": 0}
    runner = ParallelSubagentRunner(
        lambda request: _FakeChild(release=release, tracker=tracker),
        max_concurrency=2,
    )

    tasks = [asyncio.create_task(runner.execute(_request(f"d{index}"))) for index in range(2)]
    await _wait_until_started(tracker, 2)
    assert tracker["peak"] == 2
    assert len(runner.active_delegations) == 2

    release.set()
    results = await asyncio.gather(*tasks)
    assert [result.status for result in results] == [
        SubagentStatus.COMPLETED,
        SubagentStatus.COMPLETED,
    ]
    assert runner.active_delegations == {}


@pytest.mark.contract
async def test_parallel_runner_capacity_is_enforced():
    """容量 2 时第三个子任务排队,峰值不超过 2。"""
    release = asyncio.Event()
    tracker = {"active": 0, "peak": 0}
    runner = ParallelSubagentRunner(
        lambda request: _FakeChild(release=release, tracker=tracker),
        max_concurrency=2,
    )

    tasks = [asyncio.create_task(runner.execute(_request(f"d{index}"))) for index in range(3)]
    await _wait_until_started(tracker, 2)
    await asyncio.sleep(0.05)
    assert tracker["peak"] == 2

    release.set()
    await asyncio.gather(*tasks)
    assert tracker["peak"] == 2


@pytest.mark.contract
async def test_serial_runner_never_overlaps_children():
    release = asyncio.Event()
    tracker = {"active": 0, "peak": 0}
    runner = SerialSubagentRunner(lambda request: _FakeChild(release=release, tracker=tracker))

    tasks = [asyncio.create_task(runner.execute(_request(f"d{index}"))) for index in range(2)]
    await _wait_until_started(tracker, 1)
    await asyncio.sleep(0.05)
    assert tracker["peak"] == 1

    release.set()
    await asyncio.gather(*tasks)


@pytest.mark.unit
def test_create_subagent_runner_selects_by_concurrency():
    factory = lambda request: _FakeChild(release=asyncio.Event(), tracker={})  # noqa: E731
    assert isinstance(create_subagent_runner(factory, max_concurrency=1), SerialSubagentRunner)
    parallel = create_subagent_runner(factory, max_concurrency=3)
    assert isinstance(parallel, ParallelSubagentRunner)
    assert parallel.max_concurrency == 3
    with pytest.raises(ValueError, match="正整数"):
        create_subagent_runner(factory, max_concurrency=0)
    with pytest.raises(ValueError, match="≥ 2"):
        ParallelSubagentRunner(factory, max_concurrency=1)


@pytest.mark.contract
async def test_parallel_runner_cancel_only_affects_target_child():
    """取消一个委派不清空其它活跃子任务。"""
    release = asyncio.Event()
    tracker = {"active": 0, "peak": 0}
    runner = ParallelSubagentRunner(
        lambda request: _FakeChild(release=release, tracker=tracker),
        max_concurrency=2,
    )
    first = asyncio.create_task(runner.execute(_request("d1")))
    second = asyncio.create_task(runner.execute(_request("d2")))
    await _wait_until_started(tracker, 2)

    assert await runner.cancel("d1") is True
    await asyncio.sleep(0.05)
    assert "d2" in runner.active_delegations
    assert "d1" not in runner.active_delegations

    release.set()
    await asyncio.gather(first, second, return_exceptions=True)
