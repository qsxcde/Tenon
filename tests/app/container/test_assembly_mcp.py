"""assembly tests that require a real MCP child process.

从 ``test_assembly.py`` 拆出：该文件整体标 ``contract`` 进入快速质量集，
而本用例会以 ``sys.executable`` 启动 ``tests/mcp/mock_server.py`` 子进程，
必须留在 ``integration`` 批次（跨平台矩阵）执行。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from tests.app.container.fixtures import *  # noqa: F401,F403

pytestmark = pytest.mark.integration


def test_config_append_mcp_tools(tmp_path, monkeypatch):
    """组合根装配:用户级 mcp.json → MCP 工具追加到内建工具之后(命名前缀)。"""
    monkeypatch.chdir(tmp_path)

    mock_server = str(Path(__file__).parents[2] / "mcp" / "mock_server.py")
    (tmp_path / ".tenon").mkdir(exist_ok=True)
    (tmp_path / ".tenon" / "mcp.json").write_text(
        json.dumps(
            {"servers": [{"name": "mock", "command": sys.executable, "args": [mock_server]}]}
        ),
        encoding="utf-8",
    )
    with patch("tenon.app.composition.model.selection.create_llm") as mock_llm:
        from tenon.ai.providers.fake import FakeClient

        mock_llm.return_value = FakeClient(response="测试回复")
        from tenon.app.container import create_agent_config
        from tenon.core import AgentTool

        ports = create_agent_config()
    names = [t.name for t in ports.tools]
    assert all(isinstance(tool, AgentTool) for tool in ports.tools)
    assert names[:8] == ["read", "write", "edit", "bash", "grep", "find", "ls", "skill"]
    assert "mcp__mock__echo" in names and "mcp__mock__fail" in names

    tool = next(t for t in ports.tools if t.name == "mcp__mock__echo")
    result = asyncio.run(tool.execute("mcp-1", {"text": "hi"}))
    assert "echo:" in result.content
    from tenon.tools.mcp.loader import close_mcp_tools

    close_mcp_tools(ports.tools)
