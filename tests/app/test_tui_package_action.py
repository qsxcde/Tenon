"""TUI `/skills` 的 Package 子命令适配（TuiAssembler.package_action）。

Package 管理器用桩替换,不访问网络或用户目录,标记 unit。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from codeagent.app.composition.tui.factory import TuiAssembler

pytestmark = pytest.mark.unit


class _Record:
    def __init__(self, skills_dir: Path, *, package_id: str = "pkg") -> None:
        self.package_id = package_id
        self.version = "1.2.0"
        self.revision = None
        self.scope = "user"
        self.status = "installed"
        self.skills_dir = skills_dir


class _Packages:
    """记录调用并返回固定结果的管理器桩。"""

    def __init__(
        self,
        *,
        record: _Record | None = None,
        records: list[_Record] | None = None,
        diagnostics: list[Any] | None = None,
    ) -> None:
        self.record = record
        self.records = records or []
        self._diagnostics = diagnostics or []
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.reloaded = False

    def install(self, source: str, *, scope: str = "user") -> _Record:
        self.calls.append(("install", (source,), {"scope": scope}))
        return self.record

    def update(self, package_id: str, *, scope: str = "user") -> _Record:
        self.calls.append(("update", (package_id,), {"scope": scope}))
        return self.record

    def remove(self, package_id: str, *, scope: str = "user") -> None:
        self.calls.append(("remove", (package_id,), {"scope": scope}))

    def reload(self) -> None:
        self.reloaded = True

    def list(self, *, scope: str | None = None) -> list[_Record]:
        self.calls.append(("list", (), {"scope": scope}))
        return self.records

    def diagnostics(self, *, scope: str | None = None) -> list[Any]:
        return self._diagnostics


def _assembler(packages: _Packages) -> TuiAssembler:
    assembler = TuiAssembler(provider="deepseek", model="deepseek-v4-pro")
    assembler.package_manager = packages  # type: ignore[assignment]
    return assembler


def _record_with_skills(tmp_path: Path, count: int = 1) -> _Record:
    skills_dir = tmp_path / "pkg" / "skills"
    for index in range(count):
        skill_dir = skills_dir / f"skill-{index}"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# skill", encoding="utf-8")
    skills_dir.mkdir(parents=True, exist_ok=True)
    return _Record(skills_dir)


def test_install_returns_package_and_scope(tmp_path):
    """install 透传 source 与 scope,并报告版本。"""
    record = _record_with_skills(tmp_path)
    packages = _Packages(record=record)
    assembler = _assembler(packages)

    message = assembler.package_action("install", ("./pkg", "--project"))

    assert "已安装 Package pkg@1.2.0 (project)" == message
    assert packages.calls == [("install", ("./pkg",), {"scope": "project"})]


def test_update_requires_single_argument():
    """update 参数缺失 → 明确的用法错误,不触达管理器。"""
    packages = _Packages()
    assembler = _assembler(packages)

    with pytest.raises(ValueError, match="用法: /skills update"):
        assembler.package_action("update", ())

    assert packages.calls == []


def test_install_reports_usage_with_source_noun():
    """install 缺参数时用法文案给出 git-url|目录 提示。"""
    assembler = _assembler(_Packages())

    with pytest.raises(ValueError, match="git-url\\|目录"):
        assembler.package_action("install", ())


def test_remove_reports_scope(tmp_path):
    """remove 删除指定 Package 并回显 scope。"""
    packages = _Packages()
    assembler = _assembler(packages)

    message = assembler.package_action("remove", ("pkg",))

    assert message == "已删除 Package pkg (user)"
    assert packages.calls == [("remove", ("pkg",), {"scope": "user"})]


def test_remove_requires_argument():
    """remove 缺参数 → 用法错误。"""
    assembler = _assembler(_Packages())

    with pytest.raises(ValueError, match="用法: /skills remove"):
        assembler.package_action("remove", ())


def test_reload_rebuilds_registry_and_config(monkeypatch):
    """reload 重读 Registry 后重建运行时配置。"""
    packages = _Packages()
    assembler = _assembler(packages)
    rebuilt: list[bool] = []
    monkeypatch.setattr(assembler, "rebuild_config", lambda: rebuilt.append(True))

    message = assembler.package_action("reload", ("--project",))

    assert packages.reloaded is True
    assert rebuilt == [True]
    assert "已重新加载 Package Registry" in message
    assert "(project)" in message


def test_list_reports_empty_state():
    """list 无记录 → 显式 (无)。"""
    packages = _Packages()
    assembler = _assembler(packages)

    assert assembler.package_action("list", ()) == "Package: (无)"
    assert packages.calls == [("list", (), {"scope": None})]


def test_list_renders_records_and_diagnostics(tmp_path):
    """list 展示记录摘要,并在有诊断时追加诊断段。"""
    record = _record_with_skills(tmp_path, count=2)
    packages = _Packages(
        records=[record],
        diagnostics=[SimpleNamespace(code="E_SKILL", message="缺少描述")],
    )
    assembler = _assembler(packages)

    message = assembler.package_action("list", ("--project",))

    assert "Package:" in message
    assert "pkg@1.2.0 · user · 2 skills · installed" in message
    assert "诊断:" in message
    assert "E_SKILL: 缺少描述" in message
    assert packages.calls == [("list", (), {"scope": "project"})]


def test_unknown_action_raises():
    """未知子命令 → ValueError,由视图层就地呈现。"""
    assembler = _assembler(_Packages())

    with pytest.raises(ValueError, match="未知 Package 操作"):
        assembler.package_action("explode", ())
