from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tenon.app.tasks.verification.models import TaskStatus, VerificationResult
from tenon.app.tasks.verification import runner as runner_module
from tenon.app.tasks.verification.runner import VerificationRunner
from tenon.app.tasks.verification.workspace import (
    VerificationCommandResolver,
    WorkspaceInspector,
)


def test_workspace_inspector_detects_content_change(tmp_path: Path):
    target = tmp_path / "app.py"
    target.write_text("before", encoding="utf-8")
    inspector = WorkspaceInspector(tmp_path)

    before = inspector.capture()
    target.write_text("after", encoding="utf-8")
    diff = inspector.compare(before, inspector.capture())

    assert diff.changed_files == ("app.py",)
    assert diff.has_changes


def test_verification_command_precedence(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest]\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    resolver = VerificationCommandResolver(tmp_path)

    explicit = resolver.resolve("python -m pytest tests/test_one.py")
    configured = resolver.resolve(None, configured="make verify")

    assert explicit.command == "python -m pytest tests/test_one.py"
    assert explicit.source == "explicit"
    assert configured.command == "make verify"
    assert configured.source == "config"


async def test_verification_runner_returns_structured_failure(tmp_path: Path):
    async def execute(command: str, timeout: float) -> dict:
        return {
            "command": command,
            "exit_code": 2,
            "status": "failed",
            "duration_ms": 12,
            "content": "failure tail",
            "output_truncated": False,
        }

    runner = VerificationRunner(tmp_path, execute=execute)
    result = await runner.run("python -m pytest")

    assert isinstance(result, VerificationResult)
    assert result.status is TaskStatus.FAILED
    assert result.exit_code == 2
    assert result.output_tail == "failure tail"


async def test_verification_runner_reports_cancellation(tmp_path: Path, task_tracker):
    gate = asyncio.Event()
    started = asyncio.Event()

    async def execute(_command: str, _timeout: float) -> dict:
        started.set()
        await gate.wait()
        return {"exit_code": 0, "status": "completed"}

    async def scenario():
        runner = VerificationRunner(tmp_path, execute=execute)
        task = task_tracker(asyncio.create_task(runner.run("pytest")))
        await asyncio.wait_for(started.wait(), timeout=1.0)
        task.cancel()
        return await task

    result = await scenario()
    assert result.status is TaskStatus.CANCELLED
    assert result.cancelled is True


@pytest.mark.unit
async def test_spawn_uses_shell_mode_on_windows(monkeypatch):
    """Windows 必须走 shell 模式,避免 list2cmdline 对引号二次转义。

    回归:exec 模式下含引号的命令被截断,报 not recognized 或
    network path not found,windows-latest 真实子进程测试全部失败。
    """
    captured: dict[str, str] = {}

    async def fake_shell(command: str, **_kwargs) -> None:
        captured["command"] = command
        raise RuntimeError("停在进程创建之前")

    monkeypatch.setattr(runner_module, "_is_windows", lambda: True)
    monkeypatch.setattr(asyncio, "create_subprocess_shell", fake_shell)
    command = '"C:\\py\\python.exe" -c "print(1)"'

    runner = VerificationRunner(".")
    with pytest.raises(RuntimeError):
        await runner._spawn(command)

    assert captured["command"] == command
