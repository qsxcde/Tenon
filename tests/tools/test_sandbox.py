"""沙箱策略与执行边界测试(离线:不启动真实受限进程)。"""

from __future__ import annotations

import pytest

from tenon.tools.execution.sandbox import (
    SANDBOX_DANGER_FULL_ACCESS,
    SANDBOX_READ_ONLY,
    SANDBOX_WORKSPACE_WRITE,
    plan_sandbox,
)

BASH = "/bin/bash"
WS = "/work/project"


def _which(*available: str):
    return lambda name: f"/usr/bin/{name}" if name in available else None


def test_full_access_keeps_original_command():
    plan = plan_sandbox("echo hi", workspace=WS, bash_path=BASH)
    assert plan.policy == SANDBOX_DANGER_FULL_ACCESS
    assert plan.available is True
    assert plan.executable == BASH
    assert plan.argv_prefix == ()


def test_unknown_policy_fails_closed():
    with pytest.raises(ValueError, match="未知沙箱策略"):
        plan_sandbox("echo hi", workspace=WS, bash_path=BASH, policy="no-such-policy")


def test_macos_workspace_write_builds_seatbelt_plan():
    plan = plan_sandbox(
        "echo hi",
        workspace=WS,
        bash_path=BASH,
        policy=SANDBOX_WORKSPACE_WRITE,
        platform="darwin",
        which=_which("sandbox-exec"),
    )
    assert plan.available is True
    assert plan.executable == "/usr/bin/sandbox-exec"
    profile = plan.argv_prefix[1]
    assert "(deny file-write*)" in profile
    assert f'(subpath "{WS}")' in profile
    assert plan.argv_prefix[-1] == BASH


def test_macos_read_only_has_no_write_allow_rule():
    plan = plan_sandbox(
        "echo hi",
        workspace=WS,
        bash_path=BASH,
        policy=SANDBOX_READ_ONLY,
        platform="darwin",
        which=_which("sandbox-exec"),
    )
    profile = plan.argv_prefix[1]
    assert "(deny file-write*)" in profile
    assert "(allow file-write*" not in profile


def test_macos_missing_backend_is_unavailable():
    plan = plan_sandbox(
        "echo hi",
        workspace=WS,
        bash_path=BASH,
        policy=SANDBOX_WORKSPACE_WRITE,
        platform="darwin",
        which=lambda name: None,
    )
    assert plan.available is False
    assert "sandbox-exec" in plan.diagnostics[0]


def test_linux_workspace_write_binds_workspace_writable():
    plan = plan_sandbox(
        "echo hi",
        workspace=WS,
        bash_path=BASH,
        policy=SANDBOX_WORKSPACE_WRITE,
        platform="linux",
        which=_which("bwrap"),
    )
    assert plan.available is True
    assert plan.executable == "/usr/bin/bwrap"
    prefix = plan.argv_prefix
    assert prefix[:3] == ("--ro-bind", "/", "/")
    assert ("--bind", WS, WS) == prefix[3:6]
    assert prefix[-1] == BASH


def test_linux_read_only_has_no_writable_bind():
    plan = plan_sandbox(
        "echo hi",
        workspace=WS,
        bash_path=BASH,
        policy=SANDBOX_READ_ONLY,
        platform="linux",
        which=_which("bwrap"),
    )
    assert "--bind" not in plan.argv_prefix


def test_unsupported_platform_is_unavailable():
    plan = plan_sandbox(
        "echo hi",
        workspace=WS,
        bash_path=BASH,
        policy=SANDBOX_READ_ONLY,
        platform="win32",
        which=_which("sandbox-exec", "bwrap"),
    )
    assert plan.available is False
    assert "当前平台" in plan.diagnostics[0]


def test_bash_tool_fails_closed_when_backend_missing(monkeypatch, tmp_path):
    """受限策略无后端时在派生子进程前就拒绝,错误可诊断。"""
    from tenon.tools.atomic import bash as bash_module
    from tenon.tools.execution.sandbox import SandboxPlan

    monkeypatch.setattr(
        bash_module,
        "plan_sandbox",
        lambda *args, **kwargs: SandboxPlan(
            SANDBOX_WORKSPACE_WRITE,
            False,
            "",
            diagnostics=("sandbox_unavailable: 未找到 bwrap",),
        ),
    )
    tool = bash_module.BashTool(cwd=str(tmp_path), sandbox_policy=SANDBOX_WORKSPACE_WRITE)
    with pytest.raises(ValueError, match="沙箱策略 workspace-write 无法执行"):
        tool.invoke(tool.Args(command="echo should-not-run"))


def test_bash_tool_default_policy_still_runs(tmp_path):
    """默认 danger-full-access 保持原行为(回归)。"""
    from tenon.tools.atomic import BashTool

    tool = BashTool(cwd=str(tmp_path))
    assert "ok" in tool.invoke(tool.Args(command="echo ok"))


def test_config_choices_match_tool_policies():
    """契约:app/config 的取值清单与 tools 的沙箱策略定义保持一致(防漂移)。"""
    from tenon.app.config import SANDBOX_POLICY_CHOICES
    from tenon.tools.execution.sandbox import SANDBOX_POLICIES

    assert SANDBOX_POLICY_CHOICES == SANDBOX_POLICIES
