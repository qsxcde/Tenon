"""Skill Package 的错误路径与回滚：缺目录、git 失败、坏记录、安装/删除回滚。

全部在 tmp_path 内完成，git 与注册表写入用桩替换，不联网。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from codeagent.app.skills.packages.manager import (
    PackageManager,
    _remove_path,
    _restore_bytes,
)
from codeagent.app.skills.packages.registry import (
    PackageRegistry,
    PackageValidationError,
)

pytestmark = pytest.mark.unit


def _write_package(root: Path, *, package_id: str = "demo", version: str = "1.0.0") -> Path:
    (root / "skills" / "fmt").mkdir(parents=True)
    (root / "skills" / "fmt" / "SKILL.md").write_text(
        "---\nname: fmt\ndescription: 格式化\n---\n正文", encoding="utf-8"
    )
    (root / "codeagent-package.json").write_text(
        json.dumps(
            {
                "id": package_id,
                "name": "Demo Package",
                "version": version,
                "skills": "skills",
            }
        ),
        encoding="utf-8",
    )
    return root


def _manager(tmp_path: Path) -> PackageManager:
    return PackageManager(tmp_path / "config", tmp_path / "workspace")


# -- 辅助函数 ---------------------------------------------------------------


def test_restore_bytes_removes_file_when_snapshot_missing(tmp_path):
    """无历史快照时恢复等价于删除,不留下半截文件。"""
    target = tmp_path / "state.json"
    target.write_text("stale", encoding="utf-8")

    _restore_bytes(target, None)

    assert not target.exists()


def test_restore_bytes_recreates_parent_directory(tmp_path):
    """有快照时连同父目录一起重建。"""
    target = tmp_path / "deep" / "state.json"

    _restore_bytes(target, b"restored")

    assert target.read_text(encoding="utf-8") == "restored"


def test_remove_path_handles_directory_and_file(tmp_path):
    """目录走 rmtree,普通文件走 unlink,两者都幂等。"""
    directory = tmp_path / "pkg"
    (directory / "skills").mkdir(parents=True)
    single = tmp_path / "file.txt"
    single.write_text("x", encoding="utf-8")

    _remove_path(directory)
    _remove_path(single)
    _remove_path(directory)  # 已不存在:不抛错

    assert not directory.exists()
    assert not single.exists()


# -- 作用域与来源 -----------------------------------------------------------


def test_invalid_scope_rejected(tmp_path):
    """非法 scope 在解析路径阶段直接拒绝。"""
    manager = _manager(tmp_path)

    with pytest.raises(ValueError, match="user 或 project"):
        manager._paths("global")


def test_install_rejects_missing_local_directory(tmp_path):
    """本地源不是目录 → PackageValidationError 指出路径。"""
    manager = _manager(tmp_path)

    with pytest.raises(PackageValidationError, match="本地 Package 目录不存在"):
        manager.install(tmp_path / "missing")


def test_git_clone_failure_reports_stderr(monkeypatch, tmp_path):
    """git clone 返回非零时携带 stderr,便于定位凭据/网络问题。"""
    monkeypatch.setattr(
        "codeagent.app.skills.packages.manager.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args, returncode=128, stdout="", stderr="fatal: denied"
        ),
    )
    manager = _manager(tmp_path)

    with pytest.raises(PackageValidationError, match="Git Package 下载失败: fatal: denied"):
        manager.install("https://example.com/repo.git")


# -- 记录读取与诊断 ---------------------------------------------------------


def _write_registry(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records), encoding="utf-8")


def _record(root: Path, package_id: str = "demo", scope: str = "user") -> dict:
    return {
        "id": package_id,
        "name": "Demo",
        "source": "local:/src",
        "scope": scope,
        "version": "1.0.0",
        "revision": "",
        "root": str(root),
        "skills": str(root / "skills"),
        "status": "installed",
    }


def test_records_skip_invalid_entries(tmp_path):
    """注册表里的坏记录被跳过,不影响其余包。"""
    manager = _manager(tmp_path)
    valid_root = tmp_path / "config" / "packages" / "demo"
    _write_registry(
        tmp_path / "config" / "registry.json",
        [_record(valid_root), {"id": "", "root": "", "skills": ""}],
    )

    records = manager.list(scope="user")

    assert [item.package_id for item in records] == ["demo"]


def test_diagnostics_aggregate_both_scopes(tmp_path):
    """不指定 scope 时合并 user 与 project 两处注册表的诊断。"""
    manager = _manager(tmp_path)
    (tmp_path / "config" / "registry.json").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "config" / "registry.json").write_text("{broken", encoding="utf-8")
    project_registry = tmp_path / "workspace" / ".codeagent" / "registry.json"
    project_registry.parent.mkdir(parents=True, exist_ok=True)
    project_registry.write_text("{broken", encoding="utf-8")

    diagnostics = manager.diagnostics()

    assert len(diagnostics) == 2
    assert all(item.code == "registry_parse_failed" for item in diagnostics)


# -- 安装 / 更新 / 删除 -----------------------------------------------------


def test_install_replaces_existing_package_record(tmp_path):
    """同 id 再装一次覆盖目录与记录,不产生重复条目。"""
    manager = _manager(tmp_path)
    manager.install(_write_package(tmp_path / "v1", version="1.0.0"))

    manager.install(_write_package(tmp_path / "v2", version="2.0.0"))

    records = manager.list(scope="user")
    assert len(records) == 1
    assert records[0].version == "2.0.0"


def test_install_rollback_restores_registry(monkeypatch, tmp_path):
    """注册表写入失败 → 回滚目录与注册表,原状态保持可用。"""
    manager = _manager(tmp_path)
    registry_path = tmp_path / "config" / "registry.json"
    _write_registry(registry_path, [])
    before = registry_path.read_text(encoding="utf-8")

    def failing_save(self, records):
        raise OSError("disk full")

    monkeypatch.setattr(PackageRegistry, "save", failing_save)

    with pytest.raises(OSError, match="disk full"):
        manager.install(_write_package(tmp_path / "pkg"))

    assert registry_path.read_text(encoding="utf-8") == before
    assert not (tmp_path / "config" / "packages" / "demo").exists()


def test_update_unknown_package_raises(tmp_path):
    """更新不存在的 Package → KeyError 指出 id。"""
    manager = _manager(tmp_path)

    with pytest.raises(KeyError, match="Package 不存在: ghost"):
        manager.update("ghost")


def test_update_reinstalls_from_recorded_local_source(tmp_path):
    """update 依据记录的 local: 源重新安装。"""
    manager = _manager(tmp_path)
    source = _write_package(tmp_path / "src", version="1.0.0")
    manager.install(source)

    record = manager.update("demo")

    assert record.package_id == "demo"
    assert record.source.startswith("local:")


def test_remove_deletes_package_and_backup(tmp_path):
    """删除成功时清理备份目录,注册表不再包含该包。"""
    manager = _manager(tmp_path)
    manager.install(_write_package(tmp_path / "pkg"))

    manager.remove("demo")

    assert manager.list(scope="user") == []
    assert not (tmp_path / "config" / "packages" / "demo").exists()


def test_remove_rollback_restores_target(monkeypatch, tmp_path):
    """注册表写入失败 → 把备份目录移回原位,原包仍可用。"""
    manager = _manager(tmp_path)
    manager.install(_write_package(tmp_path / "pkg"))
    target = tmp_path / "config" / "packages" / "demo"

    def failing_save(self, records):
        raise OSError("disk full")

    monkeypatch.setattr(PackageRegistry, "save", failing_save)

    with pytest.raises(OSError, match="disk full"):
        manager.remove("demo")

    assert target.exists()
    assert (target / "codeagent-package.json").exists()


def test_remove_rejects_record_outside_store(tmp_path):
    """注册表记录指向 store 之外 → 拒绝删除,避免误删用户文件。"""
    manager = _manager(tmp_path)
    outside = tmp_path / "outside" / "pkg"
    (outside / "skills").mkdir(parents=True)
    _write_registry(
        tmp_path / "config" / "registry.json",
        [_record(outside.resolve())],
    )

    with pytest.raises(PackageValidationError, match="安装路径越界"):
        manager.remove("demo")

    assert outside.exists()
