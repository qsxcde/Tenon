"""Windows Git Bash 进程策略。"""

from __future__ import annotations

import subprocess
from typing import Any, cast

__all__ = ["WindowsProcessBackend"]


class WindowsProcessBackend:
    """为非交互式 Git Bash 创建进程组并尽力清理整棵进程树。"""

    def spawn_kwargs(self, cwd: str, env: dict[str, str]) -> dict[str, Any]:
        # creationflags 是 Windows 专有常量,typeshed 按运行平台裁剪导致非 Windows
        # 上静态不可见;cast 只影响静态视图,运行时行为不变。
        win_subprocess = cast("Any", subprocess)
        return {
            "cwd": cwd,
            "env": env,
            "creationflags": win_subprocess.CREATE_NEW_PROCESS_GROUP
            | win_subprocess.CREATE_NO_WINDOW,
        }

    def async_spawn_kwargs(self, cwd: str, env: dict[str, str]) -> dict[str, Any]:
        return self.spawn_kwargs(cwd, env)

    def kill_tree(self, pid: int) -> bool:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        # MSYS 子进程可能被重新挂载到运行时进程树之外，不能证明全树已停止。
        return False
