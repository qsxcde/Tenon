"""工作区快照对比与验证命令发现。

全部在 tmp_path 内构造项目特征，不执行真实验证命令。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from codeagent.app.tasks.verification.models import WorkspaceSnapshot
from codeagent.app.tasks.verification.workspace import (
    VerificationCommandResolver,
    WorkspaceInspector,
)

pytestmark = pytest.mark.unit


# -- 快照与对比 -------------------------------------------------------------


def test_capture_skips_excluded_directories(tmp_path):
    """默认排除 .git/__pycache__/.venv 等目录。"""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print(1)", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "app.pyc").write_bytes(b"x")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref", encoding="utf-8")

    snapshot = WorkspaceInspector(tmp_path).capture()

    assert set(snapshot.files) == {"src/app.py"}


def test_capture_of_missing_directory_is_empty(tmp_path):
    """工作目录不存在时返回空快照,不抛错。"""
    snapshot = WorkspaceInspector(tmp_path / "missing").capture()

    assert snapshot.files == {}


def test_capture_skips_unreadable_file(monkeypatch, tmp_path):
    """读取失败的文件被跳过,不影响其余文件。"""
    readable = tmp_path / "ok.txt"
    readable.write_text("ok", encoding="utf-8")
    broken = tmp_path / "broken.txt"
    broken.write_text("boom", encoding="utf-8")

    original = Path.read_bytes

    def read_bytes(self):
        if self.name == "broken.txt":
            raise OSError("permission denied")
        return original(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    snapshot = WorkspaceInspector(tmp_path).capture()

    assert set(snapshot.files) == {"ok.txt"}


def test_compare_reports_added_modified_deleted(tmp_path):
    """快照对比给出新增/修改/删除三类变更。"""
    before = WorkspaceSnapshot({"a.txt": "1", "b.txt": "2"}, ())
    after = WorkspaceSnapshot({"b.txt": "9", "c.txt": "3"}, ())

    diff = WorkspaceInspector(tmp_path).compare(before, after)

    assert diff.added == ("c.txt",)
    assert diff.modified == ("b.txt",)
    assert diff.deleted == ("a.txt",)
    assert diff.changed_files == ("a.txt", "b.txt", "c.txt")


def test_excluded_returns_true_for_path_outside_cwd(tmp_path):
    """不属于 cwd 的路径默认排除,避免越界读取。"""
    inspector = WorkspaceInspector(tmp_path)

    assert inspector._excluded(tmp_path.parent / "elsewhere.txt") is True


def test_git_status_tolerates_missing_git(monkeypatch, tmp_path):
    """git 不可用或超时时 git 状态为空,快照其余部分照常返回。"""

    def failing(*args, **kwargs):
        raise OSError("git not found")

    monkeypatch.setattr(subprocess, "run", failing)

    snapshot = WorkspaceInspector(tmp_path).capture()

    assert snapshot.git_status == ()


def test_git_status_ignores_nonzero_exit(monkeypatch, tmp_path):
    """非 git 仓库(git 返回非零)时不记录任何状态行。"""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args, returncode=128, stdout="fatal: not a repo\n", stderr=""
        ),
    )

    snapshot = WorkspaceInspector(tmp_path).capture()

    assert snapshot.git_status == ()


def test_git_status_collects_lines(monkeypatch, tmp_path):
    """git 返回零时按行收集非空状态。"""
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args, returncode=0, stdout=" M a.py\n\n?? b.py\n", stderr=""
        ),
    )

    snapshot = WorkspaceInspector(tmp_path).capture()

    assert snapshot.git_status == (" M a.py", "?? b.py")


# -- 验证命令发现 -----------------------------------------------------------


def _resolver(tmp_path: Path) -> VerificationCommandResolver:
    return VerificationCommandResolver(tmp_path)


def test_resolve_prefers_explicit_command(tmp_path):
    """显式命令优先于配置与自动探测。"""
    resolver = _resolver(tmp_path)

    resolved = resolver.resolve("  make lint  ", configured="npm test")

    assert resolved is not None
    assert (resolved.command, resolved.source) == ("make lint", "explicit")


def test_resolve_uses_configured_command(tmp_path):
    """配置命令优先于项目探测。"""
    resolver = _resolver(tmp_path)
    (tmp_path / "Cargo.toml").write_text("", encoding="utf-8")

    resolved = resolver.resolve(configured="  pytest -q  ")

    assert resolved is not None
    assert (resolved.command, resolved.source) == ("pytest -q", "config")


def test_project_config_from_pyproject_verify(tmp_path):
    """pyproject 的 tool.codeagent.verify 被采纳。"""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.codeagent]\nverify = "uv run pytest -q"\n', encoding="utf-8"
    )

    resolved = _resolver(tmp_path).resolve()

    assert resolved is not None
    assert (resolved.command, resolved.source) == ("uv run pytest -q", "config")


def test_project_config_falls_back_to_test_command(tmp_path):
    """verify 缺失时使用 test_command 键。"""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.codeagent]\ntest_command = "make check"\n', encoding="utf-8"
    )

    resolved = _resolver(tmp_path).resolve()

    assert resolved is not None and resolved.command == "make check"


def test_broken_pyproject_is_ignored(tmp_path):
    """损坏的 pyproject 不影响后续探测。"""
    (tmp_path / "pyproject.toml").write_text("not = [valid", encoding="utf-8")
    (tmp_path / "go.mod").write_text("module x", encoding="utf-8")

    resolved = _resolver(tmp_path).resolve()

    assert resolved is not None
    assert (resolved.command, resolved.source) == ("go test ./...", "detect:go")


def test_package_json_test_script_is_used_as_config(tmp_path):
    """package.json 的 scripts.test 作为配置命令。"""
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8"
    )

    resolved = _resolver(tmp_path).resolve()

    assert resolved is not None
    assert (resolved.command, resolved.source) == ("npm test", "config")


def test_broken_package_json_is_ignored(tmp_path):
    """损坏的 package.json 不影响其它探测。"""
    (tmp_path / "package.json").write_text("{broken", encoding="utf-8")
    (tmp_path / "pom.xml").write_text("<project/>", encoding="utf-8")

    resolved = _resolver(tmp_path).resolve()

    assert resolved is not None and resolved.source == "detect:java"


def test_detect_python_project_prefers_uv(monkeypatch, tmp_path):
    """Python 项目 + tests 目录 → pytest,存在 uv 时用 uv run。"""
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/uv")

    resolved = _resolver(tmp_path).resolve()

    assert resolved is not None
    assert (resolved.command, resolved.source) == ("uv run pytest -q", "detect:python")


def test_detect_python_project_without_uv(monkeypatch, tmp_path):
    """无 uv 时回退 python -m pytest。"""
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "test").mkdir()
    monkeypatch.setattr("shutil.which", lambda name: None)

    resolved = _resolver(tmp_path).resolve()

    assert resolved is not None and resolved.command == "python -m pytest -q"


def test_detect_node_project(tmp_path):
    """无 pyproject 时按 package.json 的 test 脚本识别 Node 项目。"""
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": "vitest run"}}), encoding="utf-8"
    )

    resolved = _resolver(tmp_path).resolve()

    assert resolved is not None
    assert (resolved.command, resolved.source) == ("npm test", "config")


def test_detect_rust_and_java_and_dotnet(tmp_path):
    """各语言标记文件映射到对应测试命令。"""
    for marker, expected in (
        ("Cargo.toml", "cargo test"),
        ("pom.xml", "mvn test"),
    ):
        (tmp_path / marker).write_text("", encoding="utf-8")
        resolved = _resolver(tmp_path).resolve()
        assert resolved is not None and resolved.command == expected
        (tmp_path / marker).unlink()

    (tmp_path / "app.sln").write_text("", encoding="utf-8")
    resolved = _resolver(tmp_path).resolve()
    assert resolved is not None and resolved.command == "dotnet test"


def test_detect_makefile_with_test_target(tmp_path):
    """Makefile 含 test: 目标时才使用 make test。"""
    (tmp_path / "Makefile").write_text("all:\n\techo hi\ntest:\n\tpytest\n", encoding="utf-8")

    resolved = _resolver(tmp_path).resolve()

    assert resolved is not None
    assert (resolved.command, resolved.source) == ("make test", "detect:make")


def test_detect_returns_none_for_unknown_project(tmp_path):
    """没有任何可识别特征时返回 None,由上层决定是否验证。"""
    assert _resolver(tmp_path).resolve() is None


def test_detect_node_when_script_is_not_string(tmp_path):
    """scripts.test 非字符串时配置读取放弃,由探测分支给出 npm test。"""
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"test": {"nested": True}}}), encoding="utf-8"
    )

    resolved = _resolver(tmp_path).resolve()

    assert resolved is not None
    assert (resolved.command, resolved.source) == ("npm test", "detect:node")
