"""Cancellable bare-argv subprocess helper for optional external tools.

Unlike ``ProcessRunner`` (which always runs ``bash -lc <command>``), this runs a
literal argv such as ``["rg", "--json", ...]`` so optional accelerators like
``fd``/``rg`` receive their arguments untouched. Cancellation and timeout both
kill the whole process tree through the platform backend.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile

from tenon.tools.execution.process import _ProcessBackend, default_backend

__all__ = ["run_argv_async"]


async def run_argv_async(
    argv: list[str],
    *,
    cwd: str,
    timeout: float,
    max_output_bytes: int,
    cleanup_timeout: float,
    backend: _ProcessBackend | None = None,
) -> tuple[int, bytes, bool]:
    """Run ``argv`` cancellably; return ``(returncode, stdout_bytes, truncated)``.

    On timeout the tree is killed and the (partial) captured stdout returned; on
    cancellation the tree is killed and ``CancelledError`` is re-raised. A killed
    process reports its (negative) returncode, which callers treat as failure.
    """
    process_backend = backend or default_backend()
    out_fd, out_name = tempfile.mkstemp(prefix="tenon-argv-")
    os.close(out_fd)
    try:
        with open(out_name, "wb") as out_file:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=out_file,
                stderr=subprocess.DEVNULL,
                **process_backend.async_spawn_kwargs(cwd, dict(os.environ)),
            )
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.CancelledError:
            process_backend.kill_tree(proc.pid)
            await _settle(proc, cleanup_timeout)
            raise
        except TimeoutError:
            process_backend.kill_tree(proc.pid)
            await _settle(proc, cleanup_timeout)
        with open(out_name, "rb") as out_file:
            raw = out_file.read(max_output_bytes + 1)
        truncated = len(raw) > max_output_bytes
        return proc.returncode or 0, raw[:max_output_bytes], truncated
    finally:
        try:
            os.unlink(out_name)
        except OSError:
            pass


async def _settle(proc: asyncio.subprocess.Process, timeout: float) -> None:
    """Wait for a killed process to be reaped, bounded by ``timeout``."""
    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
    except (TimeoutError, ProcessLookupError):
        pass
