"""会话路径锁：重入、越权释放、获取失败回滚与超时。

POSIX 分支用 fcntl 桩模拟竞争，不启动第二个进程。
Windows 专属分支不在本平台执行。
"""

from __future__ import annotations

import errno

import pytest

from tenon.session.persistence import locking
from tenon.session.persistence.locking import PathLock, path_lock

#: fcntl 仅 POSIX 可用;Windows 走 msvcrt 分支,本模块整体跳过。
fcntl = pytest.importorskip("fcntl", reason="fcntl 仅在 POSIX 可用")

pytestmark = pytest.mark.unit


def test_acquire_is_reentrant_and_releases_by_depth(tmp_path):
    """同一线程内重入计数,逐层释放后彻底解锁。"""
    lock = PathLock(tmp_path / "s1.jsonl")

    assert lock.acquire() is True
    assert lock.acquire() is True
    lock.release()
    assert lock._depth == 1
    lock.release()
    assert lock._depth == 0
    assert lock._owner is None


def test_release_unowned_lock_raises(tmp_path):
    """未持有的锁被释放时报错,避免误释放他人持有的文件锁。"""
    lock = PathLock(tmp_path / "s1.jsonl")

    with pytest.raises(RuntimeError, match="unowned"):
        lock.release()


def test_acquire_rolls_back_thread_lock_on_os_failure(monkeypatch, tmp_path):
    """OS 锁失败时释放线程锁,避免同一线程后续永久阻塞。"""
    lock = PathLock(tmp_path / "s1.jsonl")

    def boom(timeout: float) -> None:
        raise OSError("lock failed")

    monkeypatch.setattr(lock, "_acquire_os", boom)

    with pytest.raises(OSError, match="lock failed"):
        lock.acquire()

    # 线程锁已回滚:再次获取会被同一错误拦下而不是死锁
    with pytest.raises(OSError, match="lock failed"):
        lock.acquire()


def test_acquire_timeout_when_lock_is_held(monkeypatch, tmp_path):
    """竞争者持锁(EAGAIN)且超时 → TimeoutError,并关闭 fd。"""
    lock = PathLock(tmp_path / "s1.jsonl")
    closed: list[int] = []

    def busy(fd, operation):
        raise OSError(errno.EAGAIN, "busy")

    monkeypatch.setattr(fcntl, "flock", busy)
    monkeypatch.setattr(locking.os, "close", lambda fd: closed.append(fd))

    with pytest.raises(TimeoutError, match="获取会话锁超时"):
        lock.acquire(timeout=0)

    assert len(closed) == 1


def test_non_retryable_os_error_is_reported_as_timeout(monkeypatch, tmp_path):
    """不可重试的 OS 错误立即失败(统一为获取超时),不会无限重试。"""
    lock = PathLock(tmp_path / "s1.jsonl")
    closed: list[int] = []

    def broken(fd, operation):
        raise OSError(errno.EBADF, "bad fd")

    monkeypatch.setattr(fcntl, "flock", broken)
    monkeypatch.setattr(locking.os, "close", lambda fd: closed.append(fd))

    with pytest.raises(TimeoutError, match="获取会话锁超时"):
        lock.acquire(timeout=1)

    assert len(closed) == 1


def test_retryable_error_retries_until_deadline(monkeypatch, tmp_path):
    """可重试错误在超时前会重试并最终成功。"""
    lock = PathLock(tmp_path / "s1.jsonl")
    attempts: list[int] = []

    def flaky(fd, operation):
        attempts.append(fd)
        if len(attempts) == 1:
            raise OSError(errno.EAGAIN, "busy")

    monkeypatch.setattr(fcntl, "flock", flaky)
    monkeypatch.setattr(locking.time, "sleep", lambda seconds: None)

    assert lock.acquire(timeout=5) is True
    assert len(attempts) == 2  # 第一次 EAGAIN,第二次成功
    lock.release()


def test_release_without_fd_is_noop(tmp_path):
    """未真正持有 OS 锁时释放是空操作。"""
    PathLock(tmp_path / "s1.jsonl")._release_os()


def test_path_lock_returns_stable_instance(tmp_path):
    """同一路径返回同一把锁(进程内共享,支持重入)。"""
    target = tmp_path / "s1.jsonl"

    assert path_lock(target) is path_lock(str(target))
