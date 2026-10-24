"""包入口与 TUI 包导出的行为。

覆盖 ``python -m codeagent`` 的退出码透传与 ``app/tui/__init__`` 的延迟导入，
两者都不启动真实 TUI 或模型。
"""

from __future__ import annotations

import runpy

import pytest

import codeagent.app.main as cli
import codeagent.app.tui as tui_pkg
import codeagent.app.tui.main as tui_main

pytestmark = pytest.mark.unit


def test_module_entrypoint_propagates_main_exit_code(monkeypatch):
    """``python -m codeagent`` 用 main() 的返回值作为进程退出码。"""
    monkeypatch.setattr(cli, "main", lambda argv=None: 7)

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("codeagent", run_name="__main__")

    assert excinfo.value.code == 7


def test_tui_package_run_tui_forwards_to_entrypoint(monkeypatch):
    """``codeagent.app.tui.run_tui`` 延迟导入并调用真正的入口函数。"""
    calls: list[str] = []
    monkeypatch.setattr(tui_main, "run_tui", lambda: calls.append("started"))

    tui_pkg.run_tui()

    assert calls == ["started"]
