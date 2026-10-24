"""验证命令执行：安全门禁、超时、取消、真实子进程与结果标准化。

真实子进程只跑 python -c 的确定性命令，不触网、不写工作区。
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

import pytest

from codeagent.app.tasks.verification.models import TaskStatus
from codeagent.app.tasks.verification.runner import VerificationRunner

pytestmark = pytest.mark.integration


def _python(code: str) -> str:
    return f'"{sys.executable}" -c "{code}"'


async def test_mutating_command_is_not_executed():
    """命中变更型安全策略的命令直接标记未验证,不启动进程。"""
    runner = VerificationRunner(".", execute=lambda command, timeout: pytest.fail("不应执行"))

    result = await runner.run("rm -rf /tmp/anything")

    assert result.status is TaskStatus.UNVERIFIED
    assert "未执行" in result.output_tail


async def test_timeout_from_executor_marks_failed():
    """执行器抛 TimeoutError → FAILED 且 timed_out。"""

    async def slow(command: str, timeout: float):
        raise asyncio.TimeoutError

    result = await VerificationRunner(".", execute=slow).run("pytest -q")

    assert result.status is TaskStatus.FAILED
    assert result.timed_out is True


async def test_cancellation_from_executor_marks_cancelled():
    """执行器被取消 → CANCELLED 且记录 cancelled 标记。"""

    async def cancelled(command: str, timeout: float):
        raise asyncio.CancelledError

    result = await VerificationRunner(".", execute=cancelled).run("pytest -q")

    assert result.status is TaskStatus.CANCELLED
    assert result.cancelled is True


async def test_sync_executor_result_is_normalized():
    """同步执行器返回值同样被标准化(callable 不必是协程)。"""
    runner = VerificationRunner(
        ".",
        execute=lambda command, timeout: {"status": "completed", "exit_code": 0, "content": "ok"},
    )

    result = await runner.run("pytest -q")

    assert result.status is TaskStatus.VERIFIED
    assert result.exit_code == 0
    assert result.output_tail == "ok"


async def test_real_subprocess_success():
    """真实子进程成功 → VERIFIED 并带回 stdout。"""
    runner = VerificationRunner(".")

    result = await runner.run(_python("print('done')"), source="detect")

    assert result.status is TaskStatus.VERIFIED
    assert result.exit_code == 0
    assert "done" in result.output_tail
    assert result.source == "detect"


async def test_real_subprocess_failure_keeps_exit_code():
    """非零退出码 → FAILED,并保留原始退出码。"""
    runner = VerificationRunner(".")

    result = await runner.run(_python("import sys; sys.exit(3)"))

    assert result.status is TaskStatus.FAILED
    assert result.exit_code == 3


async def test_real_subprocess_timeout_kills_process():
    """进程超时被终止,结果为 timed_out 而不是悬挂。"""
    runner = VerificationRunner(".", timeout=1.0)

    result = await runner.run(_python("import time; time.sleep(30)"), timeout=1.0)

    assert result.status is TaskStatus.FAILED
    assert result.timed_out is True
    assert "超时" in result.output_tail


async def test_real_subprocess_output_is_truncated():
    """输出超过 12k 字符时保留末尾并标记截断。"""
    runner = VerificationRunner(".")

    result = await runner.run(_python("print('x' * 20000)"))

    assert result.status is TaskStatus.VERIFIED
    assert result.output_truncated is True
    assert len(result.output_tail) <= 12_000


async def test_execute_cancellation_kills_child_process():
    """任务被取消时子进程被击杀,不留下孤儿进程。"""
    runner = VerificationRunner(".")

    task = asyncio.create_task(runner._execute(_python("import time; time.sleep(30)"), 60.0))
    await asyncio.sleep(0.2)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


def test_normalize_object_result_reads_attributes():
    """对象型执行结果按属性读取,并换算缺失的耗时。"""
    raw = SimpleNamespace(
        content="out",
        exit_code="0",
        status="",
        duration_ms=0,
        output_truncated=True,
        cleanup_uncertain=True,
    )

    result = VerificationRunner._normalize(raw, "cmd", "explicit", started=0.0)

    assert result.status is TaskStatus.VERIFIED
    assert result.exit_code == 0
    assert result.output_truncated is True
    assert result.cleanup_uncertain is True
    assert result.duration_ms >= 0


def test_normalize_maps_status_strings():
    """status 字符串映射到 timed_out / cancelled 终态。"""

    timed = VerificationRunner._normalize(
        {"status": "timeout", "content": "x"}, "cmd", "explicit", 0.0
    )
    cancelled = VerificationRunner._normalize(
        {"status": "cancelled", "content": "x"}, "cmd", "explicit", 0.0
    )

    assert timed.status is TaskStatus.FAILED and timed.timed_out is True
    assert cancelled.status is TaskStatus.CANCELLED and cancelled.cancelled is True


def test_normalize_non_numeric_exit_code_is_unverified():
    """退出码非数字时判为未验证,而不是伪造成功。"""
    result = VerificationRunner._normalize(
        {"status": "", "exit_code": "n/a", "content": "x"}, "cmd", "explicit", 0.0
    )

    assert result.status is TaskStatus.UNVERIFIED
    assert result.exit_code is None
