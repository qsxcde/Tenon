"""TUI 斜杠命令注册表实例。

单独成模块,让补全渲染、分派与交互协调器共享同一份注册表,而不互相 import。
"""

from __future__ import annotations

from .parser import default_registry

__all__ = ["_COMMANDS"]

_COMMANDS = default_registry()
