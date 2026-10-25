#!/usr/bin/env python3
"""把 ``codeagent`` 一次性重命名为新的项目名。

默认只做 dry-run 并打印完整计划,传 ``--apply`` 才落盘。落盘分三步,顺序不可交换:

1. 文本替换:按原词的大小写风格改写品牌名,保证 ``codeagent`` / ``CodeAgent`` /
   ``CODEAGENT`` 三类变体都收敛到新名的对应形态;
2. 包目录重命名:``src/codeagent`` → ``src/<new>``;
3. 兼容补丁:用精确锚点插入旧配置目录的迁移逻辑,并让敏感路径正则继续覆盖旧名。

改名只做机械替换,不做语义判断。``uv.lock`` 属于生成物,由 ``uv lock`` 重建,
脚本刻意不碰。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: 旧品牌名。大小写变体在替换时保持原有风格。
OLD_NAME = "codeagent"

#: 新名只允许小写字母、数字与下划线:发行名、import 名与 CLI 名三者保持一致。
NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

BRAND_RE = re.compile(re.escape(OLD_NAME), re.IGNORECASE)

#: 版本库、缓存与虚拟环境不参与改名。
SKIP_DIRS = frozenset(
    {
        ".git",
        ".idea",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "venv",
    }
)

#: 只改写已知文本后缀;其余按二进制跳过,避免破坏图片、字体与字节码。
TEXT_SUFFIXES = frozenset({".cfg", ".ini", ".json", ".md", ".py", ".toml", ".txt", ".yaml", ".yml"})

SELF_PATH = Path(__file__).resolve()

#: 明细最多列出的文件数,避免 dry-run 被数百行淹没。
DETAIL_LIMIT = 20

#: 旧配置目录迁移模块。独立成文件,避免 config.py 越过 300 行规模门禁;
#: 目录常量由调用方注入,因此这里不 import config,也不会循环依赖。
MIGRATION_MODULE = '''"""旧配置目录的一次性迁移。

独立成模块是为了让 ``app/config.py`` 维持在规模门禁以内;这里不 import
``config``,目录常量由调用方注入,避免循环依赖。
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path


def migrate_legacy_config(current: Path, legacy: Path) -> Path | None:
    """把 ``legacy`` 整体迁移到 ``current``。

    仅在 ``current`` 不存在且 ``legacy`` 存在时动作;两者并存时保持现状,
    避免覆盖用户已经在新目录下写好的配置;迁移失败只告警,不阻塞启动。
    """
    if current.exists() or not legacy.exists():
        return None
    try:
        shutil.move(str(legacy), str(current))
    except OSError as exc:
        logging.warning("旧配置目录迁移失败 %s: %s", legacy, exc)
        return None
    logging.info("配置目录已迁移: %s -> %s", legacy, current)
    return current
'''


@dataclass(frozen=True)
class Patch:
    """一处后置改写。替换型要求锚点恰好命中一次;新建型要求目标文件尚不存在。"""

    path: str
    old: str
    new: str
    reason: str
    create: bool = False


@dataclass
class TextEdit:
    """一个待改写的文件及其命中次数。"""

    path: Path
    count: int
    updated: str


def _pascal(name: str) -> str:
    """``my_tool`` → ``MyTool``。"""
    return "".join(part.capitalize() for part in name.split("_"))


def _rewrite_brand(text: str, new_name: str) -> tuple[str, int]:
    """替换旧品牌名,并按原词形态生成新词。"""
    pascal = _pascal(new_name)

    def _sub(match: re.Match[str]) -> str:
        word = match.group(0)
        if word.isupper():
            return new_name.upper()
        if word[0].isupper():
            return pascal
        return new_name

    return BRAND_RE.subn(_sub, text)


def _iter_text_files(root: Path, excluded: tuple[str, ...]) -> list[Path]:
    """列出参与改写的文本文件,跳过脚本自身与排除前缀。"""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS)
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if path.resolve() == SELF_PATH:
                continue
            relative = path.relative_to(root).as_posix()
            if any(relative.startswith(prefix) for prefix in excluded):
                continue
            if path.suffix.lower() in TEXT_SUFFIXES:
                files.append(path)
    return files


def _config_patches(new_name: str) -> list[Patch]:
    """app/config.py:旧目录常量、迁移模块 import 与首启调用点。"""
    config_path = f"src/{new_name}/app/config.py"
    return [
        Patch(
            config_path,
            "from pydantic_settings import BaseSettings, SettingsConfigDict",
            (
                "from pydantic_settings import BaseSettings, SettingsConfigDict\n"
                "\n"
                "from .config_migration import migrate_legacy_config"
            ),
            "配置迁移逻辑独立成模块,避免 config.py 超出规模门禁",
        ),
        Patch(
            config_path,
            f'CONFIG_DIR = Path.home() / ".{new_name}"\n',
            (
                f'CONFIG_DIR = Path.home() / ".{new_name}"\n'
                "#: 改名前的配置目录:只在首次启动时整体迁移一次,迁移后不再读取。\n"
                f'LEGACY_CONFIG_DIR = Path.home() / ".{OLD_NAME}"\n'
            ),
            "保留旧配置目录常量供一次性迁移",
        ),
        Patch(
            f"src/{new_name}/app/config_migration.py",
            "",
            MIGRATION_MODULE,
            "新增旧配置目录迁移模块",
            create=True,
        ),
        Patch(
            config_path,
            "    cfg_dir = cfg_dir or CONFIG_DIR\n",
            (
                "    if cfg_dir is None:\n"
                "        migrate_legacy_config(CONFIG_DIR, LEGACY_CONFIG_DIR)\n"
                "    cfg_dir = cfg_dir or CONFIG_DIR\n"
            ),
            "首启时先迁移旧目录再生成模板",
        ),
    ]


def _boundary_patches(new_name: str) -> list[Patch]:
    """安全边界正则与 CI 显示名:两者都必须跟随改名。"""
    pascal = _pascal(new_name)
    secret_pattern = r'r"(^|[/\\])(?:\.env|\.' + new_name + r"|\.ssh|\.aws|\.gnupg)(?:$|[/\\])|"
    secret_pattern_with_legacy = (
        r'r"(^|[/\\])(?:\.env|\.'
        + new_name
        + r"|\."
        + OLD_NAME
        + r"|\.ssh|\.aws|\.gnupg)(?:$|[/\\])|"
    )
    return [
        Patch(
            f"src/{new_name}/tools/security/filesystem.py",
            secret_pattern,
            secret_pattern_with_legacy,
            "旧配置目录仍在磁盘上时必须继续按敏感路径拒绝",
        ),
        Patch(
            ".github/workflows/ci.yml",
            "name: CI\n",
            f"name: {pascal} CI\n",
            "工作流显示名跟随项目名",
        ),
    ]


def _test_patches(new_name: str) -> list[Patch]:
    """兼容层的回归测试:旧目录仍被拒绝、迁移语义可验证。"""
    return [
        Patch(
            "tests/tools/test_security.py",
            f'    assert classify_bash("ls ~/.{new_name}").action == DENY',
            (
                f'    assert classify_bash("ls ~/.{new_name}").action == DENY\n'
                "    # 改名兼容:旧配置目录可能仍在磁盘上,必须继续按敏感路径拒绝。\n"
                f'    assert classify_bash("cat ~/.{OLD_NAME}/.env").action == DENY\n'
                f'    assert classify_bash("ls ~/.{OLD_NAME}").action == DENY'
            ),
            "旧配置目录仍需被敏感路径策略拒绝",
        ),
        Patch(
            "tests/test_config.py",
            (
                f"from {new_name}.app.config import (\n"
                "    Settings,\n"
                "    configured_providers,\n"
                "    ensure_config_files,\n"
                "    write_env_key,\n"
                ")"
            ),
            (
                f"from {new_name}.app import config as config_module\n"
                f"from {new_name}.app.config import (\n"
                "    Settings,\n"
                "    configured_providers,\n"
                "    ensure_config_files,\n"
                "    migrate_legacy_config,\n"
                "    write_env_key,\n"
                ")"
            ),
            "迁移测试需要模块对象与函数入口",
        ),
        Patch(
            "tests/test_config.py",
            (
                "def test_configured_providers_missing_file(tmp_path):\n"
                '    """env 文件不存在 → 空集,不抛错。"""\n'
                '    assert configured_providers(tmp_path / ".env") == set()'
            ),
            (
                "def test_configured_providers_missing_file(tmp_path):\n"
                '    """env 文件不存在 → 空集,不抛错。"""\n'
                '    assert configured_providers(tmp_path / ".env") == set()\n'
                "\n"
                "\n"
                "def test_migrate_legacy_config_moves_legacy_dir(tmp_path, monkeypatch):\n"
                '    """旧配置目录在新目录缺失时整体迁移,已有内容原样保留。"""\n'
                '    legacy = tmp_path / ".legacy"\n'
                '    current = tmp_path / ".current"\n'
                "    legacy.mkdir()\n"
                '    (legacy / ".env").write_text("LLM_PROVIDER=fake", encoding="utf-8")\n'
                '    monkeypatch.setattr(config_module, "CONFIG_DIR", current)\n'
                '    monkeypatch.setattr(config_module, "LEGACY_CONFIG_DIR", legacy)\n'
                "\n"
                "    assert migrate_legacy_config(current, legacy) == current\n"
                '    assert (current / ".env").read_text(encoding="utf-8") == "LLM_PROVIDER=fake"\n'
                "    assert not legacy.exists()\n"
                "\n\n"
                "def test_migrate_legacy_config_keeps_existing_current(tmp_path, monkeypatch):\n"
                '    """新旧目录并存时不动作,避免覆盖已经写好的新配置。"""\n'
                '    legacy = tmp_path / ".legacy"\n'
                '    current = tmp_path / ".current"\n'
                "    legacy.mkdir()\n"
                "    current.mkdir()\n"
                '    (legacy / ".env").write_text("old", encoding="utf-8")\n'
                '    (current / ".env").write_text("new", encoding="utf-8")\n'
                '    monkeypatch.setattr(config_module, "CONFIG_DIR", current)\n'
                '    monkeypatch.setattr(config_module, "LEGACY_CONFIG_DIR", legacy)\n'
                "\n"
                "    assert migrate_legacy_config(current, legacy) is None\n"
                '    assert (current / ".env").read_text(encoding="utf-8") == "new"\n'
                '    assert (legacy / ".env").read_text(encoding="utf-8") == "old"'
            ),
            "为旧配置目录迁移补充回归测试",
        ),
    ]


def _build_patches(new_name: str) -> list[Patch]:
    """按职责汇总全部补丁;同类保持相邻,便于排查锚点问题。"""
    return _config_patches(new_name) + _boundary_patches(new_name) + _test_patches(new_name)


def _current_path(root: Path, patch_path: str, new_name: str) -> Path:
    """补丁记录改名后的路径;执行前映射回当前磁盘路径。"""
    legacy = patch_path.replace(f"src/{new_name}/", f"src/{OLD_NAME}/", 1)
    return root / legacy


def _ensure_clean_worktree(root: Path) -> None:
    """改名会触碰数百个文件,要求工作区干净以便随时回滚。"""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return
    if result.returncode == 0 and result.stdout.strip():
        raise SystemExit("工作区有未提交改动。请先提交,或用 --force 跳过该检查。")


def _verify_patches(
    root: Path, patches: list[Patch], staged: dict[Path, str], new_name: str
) -> None:
    """写盘前验证每个锚点恰好命中一次,避免补丁静默失效。"""
    for patch in patches:
        if patch.create:
            if (root / patch.path).exists():
                raise SystemExit(f"新建补丁的目标已存在: {patch.path}")
            continue
        path = _current_path(root, patch.path, new_name)
        text = staged.get(path)
        if text is None:
            if not path.is_file():
                raise SystemExit(f"补丁目标不存在: {path} ({patch.reason})")
            text = path.read_text(encoding="utf-8")
        hits = text.count(patch.old)
        if hits != 1:
            raise SystemExit(f"补丁锚点命中 {hits} 次,应为 1 次: {patch.path} / {patch.reason}")


def _print_plan(
    root: Path,
    new_name: str,
    edits: list[TextEdit],
    total: int,
    old_pkg: Path,
    new_pkg: Path,
    patches: list[Patch],
) -> None:
    print(f"改名计划: {OLD_NAME} -> {new_name}")
    print(f"  仓库根目录 : {root}")
    print(f"  文本改动   : {len(edits)} 个文件, {total} 处")
    print(f"  包目录     : {old_pkg.relative_to(root)} -> {new_pkg.relative_to(root)}")
    print(f"  兼容补丁   : {len(patches)} 处")
    for patch in patches:
        print(f"    - {patch.path}: {patch.reason}")
    print(f"\n  明细, 按命中次数降序, 最多 {DETAIL_LIMIT} 个:")
    for edit in sorted(edits, key=lambda item: item.count, reverse=True)[:DETAIL_LIMIT]:
        print(f"    {edit.count:>4}  {edit.path.relative_to(root).as_posix()}")
    if len(edits) > DETAIL_LIMIT:
        print(f"    ... 其余 {len(edits) - DETAIL_LIMIT} 个文件略")


def _print_followups(new_name: str) -> None:
    print("\n后续必须执行:")
    print("  uv lock                                        # 锁文件里的发行名需要重建")
    print("  uv sync --group dev")
    print("  uv run ruff format src tests evals scripts      # 改名改变行长,必须重新排版")
    print('  uv run pytest -m "unit or contract" -q --strict-markers')
    print("  uv run python scripts/scale_scan.py")
    print("  uv run python scripts/type_scan.py")
    print("\n提醒:")
    print("  - GitHub 仓库改名后,README 徽章与 clone 地址需要同步")
    print(f"  - 旧配置目录 ~/.{OLD_NAME} 会在下次启动时自动迁移到 ~/.{new_name}")
    print("  - uv.lock 与 .gitignore 未参与改写,如有遗漏请手工确认")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"把 {OLD_NAME} 一次性重命名")
    parser.add_argument("--name", default="tenon", help="新项目名,小写字母/数字/下划线")
    parser.add_argument("--root", default=None, help="仓库根目录,默认为脚本上级目录")
    parser.add_argument("--apply", action="store_true", help="真正写入磁盘,默认仅 dry-run")
    parser.add_argument("--force", action="store_true", help="跳过 git 工作区干净检查")
    parser.add_argument("--exclude", action="append", default=[], help="相对路径前缀,可重复")
    args = parser.parse_args(argv)

    new_name = args.name.strip()
    if not NAME_PATTERN.match(new_name):
        print(f"新项目名不合法: {new_name!r} 需匹配 {NAME_PATTERN.pattern}", file=sys.stderr)
        return 2
    if new_name == OLD_NAME:
        print("新项目名与原名称相同,无需改名", file=sys.stderr)
        return 2

    root = Path(args.root).expanduser().resolve() if args.root else SELF_PATH.parents[1]
    old_pkg = root / "src" / OLD_NAME
    new_pkg = root / "src" / new_name

    if new_pkg.exists():
        print(f"目标包目录已存在,拒绝覆盖: {new_pkg}", file=sys.stderr)
        return 2
    if not old_pkg.is_dir():
        print(f"未找到旧包目录: {old_pkg}", file=sys.stderr)
        return 2

    if args.apply and not args.force:
        _ensure_clean_worktree(root)

    edits: list[TextEdit] = []
    staged: dict[Path, str] = {}
    total = 0
    for path in _iter_text_files(root, tuple(args.exclude)):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        updated, count = _rewrite_brand(text, new_name)
        if not count:
            continue
        edits.append(TextEdit(path, count, updated))
        staged[path] = updated
        total += count

    patches = _build_patches(new_name)
    _verify_patches(root, patches, staged, new_name)
    _print_plan(root, new_name, edits, total, old_pkg, new_pkg, patches)

    if not args.apply:
        print("\n[dry-run] 未写入任何文件。确认无误后加 --apply 执行。")
        return 0

    for edit in edits:
        edit.path.write_text(edit.updated, encoding="utf-8")
    old_pkg.rename(new_pkg)

    for patch in patches:
        path = root / patch.path
        if patch.create:
            path.write_text(patch.new, encoding="utf-8")
            continue
        text = path.read_text(encoding="utf-8")
        if text.count(patch.old) != 1:
            raise SystemExit(f"写入后锚点失配,请检查: {path}")
        path.write_text(text.replace(patch.old, patch.new), encoding="utf-8")

    print(f"\n已完成改名: {OLD_NAME} -> {new_name}")
    print(f"  改写文件 {len(edits)} 个, 替换 {total} 处, 补丁 {len(patches)} 处")
    _print_followups(new_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
