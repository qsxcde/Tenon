"""命令执行沙箱策略:read-only / workspace-write / danger-full-access。

沙箱是"进程边界"而非"策略替代":危险命令判定与确认环仍在安全分类器;
本模块只决定如何把已有命令放进受限的 OS 边界。

- macOS:``sandbox-exec``(Seatbelt)按策略生成 profile;
- Linux:``bwrap``(bubblewrap)按策略绑定只读根与可写工作区;
- 其它平台或无可用后端:受限策略 **fail-closed**(明确诊断、拒绝执行),
  ``danger-full-access`` 保持原行为(不包装命令)。
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from collections.abc import Callable

__all__ = [
    "SANDBOX_DANGER_FULL_ACCESS",
    "SANDBOX_POLICIES",
    "SANDBOX_READ_ONLY",
    "SANDBOX_WORKSPACE_WRITE",
    "SandboxPlan",
    "plan_sandbox",
]

SANDBOX_READ_ONLY = "read-only"
SANDBOX_WORKSPACE_WRITE = "workspace-write"
SANDBOX_DANGER_FULL_ACCESS = "danger-full-access"

SANDBOX_POLICIES: tuple[str, ...] = (
    SANDBOX_READ_ONLY,
    SANDBOX_WORKSPACE_WRITE,
    SANDBOX_DANGER_FULL_ACCESS,
)

#: workspace-write 下额外放行的临时目录(macOS /private/tmp /tmp,Linux /tmp)。
_WRITABLE_TMP = ("/private/tmp", "/tmp")


@dataclass(frozen=True)
class SandboxPlan:
    """一次命令执行的实际边界。

    ``executable`` + ``argv_prefix`` 与 ``bash -lc <command>`` 组合成最终 argv;
    ``available=False`` 表示受限策略无可用后端,调用方必须 fail-closed。
    """

    policy: str
    available: bool
    executable: str
    argv_prefix: tuple[str, ...] = ()
    diagnostics: tuple[str, ...] = ()


def plan_sandbox(
    command: str,
    *,
    workspace: str,
    bash_path: str,
    policy: str = SANDBOX_DANGER_FULL_ACCESS,
    platform: str | None = None,
    which: Callable[[str], str | None] | None = None,
) -> SandboxPlan:
    """按策略生成执行边界;未知策略或受限策略无后端时 fail-closed。"""
    if policy not in SANDBOX_POLICIES:
        raise ValueError(f"未知沙箱策略: {policy};可选: {', '.join(SANDBOX_POLICIES)}")
    if policy == SANDBOX_DANGER_FULL_ACCESS:
        return SandboxPlan(policy, True, bash_path)

    detected = platform or _platform()
    lookup = which or shutil.which
    if detected == "darwin":
        return _macos_plan(command, workspace, bash_path, policy, lookup)
    if detected.startswith("linux"):
        return _linux_plan(command, workspace, bash_path, policy, lookup)
    return _unavailable(policy, detected, "当前平台无已接入的沙箱后端")


def _platform() -> str:
    import sys

    return "darwin" if sys.platform == "darwin" else sys.platform


def _macos_plan(
    command: str,
    workspace: str,
    bash_path: str,
    policy: str,
    lookup: Callable[[str], str | None],
) -> SandboxPlan:
    sandbox_exec = lookup("sandbox-exec")
    if not sandbox_exec:
        return _unavailable(policy, "darwin", "未找到 sandbox-exec(Seatbelt)")
    profile = _seatbelt_profile(workspace, policy)
    return SandboxPlan(
        policy,
        True,
        sandbox_exec,
        argv_prefix=("-p", profile, bash_path),
        diagnostics=("macos-seatbelt",),
    )


def _seatbelt_profile(workspace: str, policy: str) -> str:
    rules = ["(version 1)", "(allow default)", "(deny file-write*)"]
    if policy == SANDBOX_WORKSPACE_WRITE:
        paths = [workspace, *_WRITABLE_TMP]
        allowed = " ".join(f'(subpath "{_escape(path)}")' for path in paths)
        rules.append(f"(allow file-write* {allowed})")
    return "\n".join(rules)


def _escape(path: str) -> str:
    return path.replace("\\", "\\\\").replace('"', '\\"')


def _linux_plan(
    command: str,
    workspace: str,
    bash_path: str,
    policy: str,
    lookup: Callable[[str], str | None],
) -> SandboxPlan:
    bwrap = lookup("bwrap")
    if not bwrap:
        return _unavailable(policy, "linux", "未找到 bwrap(bubblewrap)")
    prefix: list[str] = ["--ro-bind", "/", "/"]
    if policy == SANDBOX_WORKSPACE_WRITE:
        prefix += ["--bind", workspace, workspace]
    prefix += [
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--chdir",
        workspace,
        bash_path,
    ]
    return SandboxPlan(policy, True, bwrap, tuple(prefix), ("linux-bwrap",))


def _unavailable(policy: str, platform: str, reason: str) -> SandboxPlan:
    return SandboxPlan(
        policy,
        False,
        "",
        diagnostics=(f"sandbox_unavailable: {reason}(平台 {platform},策略 {policy})",),
    )
