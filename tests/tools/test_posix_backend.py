"""POSIX 进程组策略：独立 session 与 kill 回退链。

仅在有 ``os.killpg`` 的平台有意义，用桩替换系统调用,不真正杀进程。
"""

from __future__ import annotations

import os
import signal

import pytest

from codeagent.tools.execution.posix import PosixProcessBackend

pytestmark = [
    pytest.mark.unit,
    pytest.mark.platform,
    pytest.mark.skipif(not hasattr(os, "killpg"), reason="需要 POSIX 进程组"),
]


def test_spawn_kwargs_use_new_session():
    """子进程独立 session,便于按进程组整体击杀。"""
    backend = PosixProcessBackend()

    assert backend.spawn_kwargs("/tmp", {"A": "1"}) == {
        "cwd": "/tmp",
        "env": {"A": "1"},
        "start_new_session": True,
    }
    assert backend.async_spawn_kwargs("/tmp", {"A": "1"})["start_new_session"] is True


def test_kill_tree_prefers_process_group(monkeypatch):
    """优先对进程组发 SIGKILL。"""
    called: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "getpgid", lambda pid: 42)
    monkeypatch.setattr(os, "killpg", lambda pgid, sig: called.append((pgid, sig)))

    assert PosixProcessBackend().kill_tree(1234) is True
    assert called == [(42, signal.SIGKILL)]


def test_kill_tree_falls_back_when_group_missing(monkeypatch):
    """进程组已消失时回退到单进程 signal。"""
    killed: list[tuple[int, int]] = []

    def missing_group(pgid, sig):
        raise ProcessLookupError("no such group")

    monkeypatch.setattr(os, "getpgid", lambda pid: 7)
    monkeypatch.setattr(os, "killpg", missing_group)
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append((pid, sig)))

    assert PosixProcessBackend().kill_tree(99) is True
    assert killed == [(99, signal.SIGKILL)]


def test_kill_tree_treats_missing_process_as_success(monkeypatch):
    """进程已退出视为清理成功,不抛异常。"""

    def missing(*args, **kwargs):
        raise ProcessLookupError("gone")

    monkeypatch.setattr(os, "getpgid", lambda pid: 7)
    monkeypatch.setattr(os, "killpg", missing)
    monkeypatch.setattr(os, "kill", missing)

    assert PosixProcessBackend().kill_tree(1) is True
